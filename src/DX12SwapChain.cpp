// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

// DX12SwapChain.cpp —— D3D12 Proxy（精简自 Community Shaders（GPL-3.0））
// Skyrim 是 DX11，DLSS 帧生成需要 DX12 swapchain。这里：
//  1) D3D12 设备 + 命令队列 + FFX 帧生成 swapchain（AMD FidelityFX SDK 创建，
//     带 FG 支持的 swapchain）
//  2) D3D11 共享纹理（WrappedResource）↔ D3D12 资源互操作
//  3) 每帧：D3D11 画面 Copy 到 D3D12 → Streamline DLSS（超分+插帧）→ D3D12 Present
// 同步：D3D11 Fence + D3D12 Fence 共享句柄，Signal/Wait 双向同步

// 注意：CommonLib 头必须最先（DX12SwapChain.h 含 Windows API 头，REX::W32 要求）
#include "FrameGen.h"

#include "DX12SwapChain.h"

#include <FidelityFX/api/include/dx12/ffx_api_dx12.hpp>
#include <dxgi1_6.h>
#include <d3dcompiler.h>

// v0.62: watchdog needs its own file handle + the Documents path
#include <cstdio>
#include <shlobj.h>

#include <SKSE/SKSE.h>

#include "Streamline.h"
#include "FidelityFX.h"
#include "ImguiMenu.h"
#include "NeuralRendering/Renderer.h"  // DLSS5 Neural Rendering（Present 集成）

namespace FrameGen
{
	// v0.5.7：运行时编译 hlsl（照 CS Util::CompileShader）——深度拷贝 shader 从
	// Data\Shaders\Upscaling\ 加载（vfs 里 mod 的 Shaders/Upscaling/，无 Data 前缀规则）
	winrt::com_ptr<ID3DBlob> CompileShaderFromFile(const wchar_t* a_path, const char* a_defineName, const char* a_profile)
	{
		D3D_SHADER_MACRO defines[2] = {};
		defines[0].Name = a_defineName;
		defines[0].Definition = "1";
		winrt::com_ptr<ID3DBlob> blob;
		winrt::com_ptr<ID3DBlob> errBlob;
		HRESULT hr = D3DCompileFromFile(a_path, defines, nullptr, "main", a_profile,
			D3DCOMPILE_OPTIMIZATION_LEVEL3, 0, blob.put(), errBlob.put());
		if (FAILED(hr)) {
			if (errBlob)
				SKSE::log::error("[FrameGen] Shader compile failed: {}", static_cast<const char*>(errBlob->GetBufferPointer()));
			DX::ThrowIfFailed(hr);
		}
		return blob;
	}
	// ---- AMD FidelityFX loader 动态加载（ffxCreateContext 等，避免静态链接 API 层）----
	// 新版 SDK 的 provider 实现是 AMD 内部包（amdinternal），公开仓库缺失 →
	// 从运行时 amd_fidelityfx_loader_dx12.dll 动态取函数指针（DLL 随插件分发）
	namespace
	{
		HMODULE g_ffxLoader = nullptr;
		PfnFfxCreateContext g_ffxCreateContext = nullptr;

		bool LoadFFXLoader()
		{
			if (g_ffxCreateContext)
				return true;
			// v0.6.1：统一加载完整后端 amd_fidelityfx_framegeneration_dx12.dll（与 FidelityFX::LoadFFX
			// 同源）——ffx API 要求同一进程所有 context 来自同一实现，混用 loader/后端会状态错乱
			g_ffxLoader = LoadLibraryW(L"Data\\Shaders\\Upscaling\\FidelityFX\\amd_fidelityfx_framegeneration_dx12.dll");
			if (!g_ffxLoader) {
				SKSE::log::error("[FrameGen] FFX loader DLL not found - D3D12 FG swapchain disabled");
				return false;
			}
			g_ffxCreateContext = reinterpret_cast<PfnFfxCreateContext>(GetProcAddress(g_ffxLoader, "ffxCreateContext"));
			if (!g_ffxCreateContext) {
				SKSE::log::error("[FrameGen] ffxCreateContext export missing in loader");
				return false;
			}
			SKSE::log::info("[FrameGen] FidelityFX loader loaded (ffxCreateContext resolved)");
			return true;
		}
	}

	void DX12SwapChain::CreateD3D12Device(IDXGIAdapter* a_adapter)
	{
		DX::ThrowIfFailed(D3D12CreateDevice(a_adapter, D3D_FEATURE_LEVEL_12_0, IID_PPV_ARGS(&d3d12Device)));

		// v0.27（DLSSG 频闪修复）：D3D12 设备就绪后立即 slInit（仅 DLSSG 模式）——
		// SL 要求 slSetD3DDevice 紧随设备创建（错误信息原文 "please call slSetD3DDevice
		// immediately after creating desired device"）。slInit 此时拿到正确的 D3D12
		// 设备上下文 → dlss_g 插件正常初始化（消除 "Plugins already initialized but
		// could be using the wrong device" → 插帧正常 → 频闪消除）。
		// FSR3 模式已在 CreateDevice hook 里 slInit（triedInitialization 防重）→ 跳过。
		if (dlssgMode && !Get().streamline.initialized)
			Get().streamline.LoadInterposer(Get().settings);

		// v0.30（DLSS-G NOT available 修复）：**不要 SetD3DDevice(D3D11)**——
		// v0.28 曾加它修 "ID3D11Device does NOT have SL proxy" 日志，但实测（20:12
		// 日志）导致 **DLSS-G is NOT available**（slInit 后先设 D3D11 再设 D3D12 →
		// dlss_g 插件绑定错乱 → feature 检测失败 → 插帧禁用）。该日志在 D3D12
		// 会话下无害（v0.27b 无此注册时 DLSS-G IS available 实锤）。频闪真根因是
		// ENB 绕过（v0.29 已修），与此无关。

		// v0.5.17：在创建 queue 之前告知 SL 设备——d3d12 已恢复静态导入，SL interposer
		// 的 IAT hook 能拦到后续 D3D12CreateCommandQueue 调用并记录 queue（dlss_g 插件
		// 靠它填充内部 queue 槽；之前 delayload d3d12 时 hook 拦不到 → queue null →
		// Allocate 0xC0000005 崩溃，dump 反汇编 [rbx+0x20] 实锤）
		Get().streamline.SetD3D12Device(d3d12Device.get());

		D3D12_COMMAND_QUEUE_DESC queueDesc{};
		queueDesc.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
		queueDesc.Flags = D3D12_COMMAND_QUEUE_FLAG_NONE;
		queueDesc.Priority = D3D12_COMMAND_QUEUE_PRIORITY_NORMAL;
		queueDesc.NodeMask = 0;

		DX::ThrowIfFailed(d3d12Device->CreateCommandQueue(&queueDesc, IID_PPV_ARGS(&commandQueue)));

		for (int i = 0; i < 3; i++) {  // v0.33：三缓冲（DLSSG frameIndex 0-2）
			DX::ThrowIfFailed(d3d12Device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&commandAllocators[i])));
			DX::ThrowIfFailed(d3d12Device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, commandAllocators[i].get(), nullptr, IID_PPV_ARGS(&commandLists[i])));
			commandLists[i]->Close();
		}
	}

	void DX12SwapChain::CreateSwapChain(IDXGIAdapter* adapter, DXGI_SWAP_CHAIN_DESC a_swapChainDesc, bool a_enableFrameGeneration, bool a_dlssgMode, std::uint32_t a_qualityMode)
	{
		// v0.27：dlssgMode 必须先赋值（CreateD3D12Device 内据此决定是否延迟 slInit）
		dlssgMode = a_dlssgMode;

		// v0.52：记录本次构建实际生效的 Provider。Provider 是**一次性**读取的——它决定
		// dlssgMode / BufferCount / D3D12 proxy 路径，全都在这里定型；运行中改 INI 或 GUI
		// 不会走回这里，所以切换注定"没有任何变化"（必须重启）。把值记下来，GUI 与日志
		// 才能明确说出"当前跑的是 X、INI 写的是 Y、需重启"。
		providerAtCreate = Get().settings.provider;
		SKSE::log::info("[FrameGen] Provider in effect this session: {} ({})", providerAtCreate,
			dlssgMode ? "DLSSG" : "FSR3");

		CreateD3D12Device(adapter);

		IDXGIFactory4* dxgiFactory;
		DX::ThrowIfFailed(adapter->GetParent(IID_PPV_ARGS(&dxgiFactory)));

		// v0.33（对齐 open-shaders CreateSwapChainDirect:117-121，**DLSSG 频闪最终根因**）：
		// CreateSwapChainForHwnd 必须走 **SL 升级后的 factory**——否则 Streamline
		// 不识别这个 swapchain（"never recognizes the swap chain as its own"）→
		// slHookPresent 不拦截 → presentCommon 不跑 → 帧号不推进（"frame 1" 警告）
		// + RSYNC pacing 不建立（"sl.reflex has no registered hooks"）→ 频闪。
		// FSR3 链（FFX）不依赖 SL 识别所以一直正常——这就是 FSR3 稳 DLSSG 闪的根因。
		if (dlssgMode && Get().streamline.slUpgradeInterface)
			Get().streamline.slUpgradeInterface(reinterpret_cast<void**>(&dxgiFactory));

		swapChainDesc = {};
		swapChainDesc.Width = a_swapChainDesc.BufferDesc.Width;
		swapChainDesc.Height = a_swapChainDesc.BufferDesc.Height;
		swapChainDesc.Format = a_swapChainDesc.BufferDesc.Format;
		swapChainDesc.SampleDesc.Count = 1;
		swapChainDesc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
		swapChainDesc.BufferCount = 2;
		swapChainDesc.SwapEffect = a_swapChainDesc.SwapEffect;
		swapChainDesc.Flags = a_swapChainDesc.Flags;

		// v0.7.8：渲染分辨率缩放——QualityMode 决定比例（FSR3 upscale ratio，同 CS）：
		// DLAA=1.0 Quality=2/3 Balanced≈0.585 Performance=0.5 UltraPerf≈0.333。
		// 引擎渲染到低分辨率后缓冲 → DLSS 放大回输出分辨率（超分才有效果）。
		// 无降渲染时超分只做重建/锐化，肉眼几乎无感且白付全屏成本（v0.7.6 实测帧数反降）。
		// v0.41：INI RenderResolutionScale >0 时优先用自定义比例（默认 0.70），
		// 0 则回退 QualityMode 档位表（旧行为）。
		{
			const float kUpscaleRatios[5] = { 1.0f, 2.0f / 3.0f, 0.585f, 0.5f, 0.333f };
			const std::uint32_t qm = a_qualityMode < 5 ? a_qualityMode : 0;
			const float customScale = Get().settings.renderResolutionScale;
			renderScaleX = renderScaleY =
				customScale > 0.0f ? std::clamp(customScale, 0.30f, 1.0f) : kUpscaleRatios[qm];
			renderWidth = static_cast<std::uint32_t>(std::max(1, static_cast<int>(swapChainDesc.Width * renderScaleX)));
			renderHeight = static_cast<std::uint32_t>(std::max(1, static_cast<int>(swapChainDesc.Height * renderScaleY)));
			SKSE::log::info("[FrameGen] Render scale {:.3f} -> {}x{} render / {}x{} output",
				renderScaleX, renderWidth, renderHeight, swapChainDesc.Width, swapChainDesc.Height);
		}

		if (dlssgMode) {
			// v0.3：DLSSG 模式 → 普通 D3D12 swapchain（NVIDIA SL 负责插帧/pacing，不用 FFX）
			// v0.33（对齐 open-shaders CreateSwapChainDirect:160-171）：
			// - BufferCount=3：SL pacer 持有一个 buffer 做合成时还有余量翻转插帧帧；
			//   双 buffer 无余量 → 插帧帧被丢 → 闪/卡
			// - 去掉 FRAME_LATENCY_WAITABLE_OBJECT：等待它会把 Present 串行化为
			//   单帧在飞 → SL pacer 丢弃每个插帧帧
			DXGI_SWAP_CHAIN_DESC1 desc1{};
			desc1.Width = swapChainDesc.Width;
			desc1.Height = swapChainDesc.Height;
			desc1.Format = swapChainDesc.Format;
			desc1.SampleDesc.Count = 1;
			desc1.BufferUsage = swapChainDesc.BufferUsage;
			desc1.BufferCount = 3;  // v0.33：SL pacer 余量（原 2）
			// DX12 只支持 FLIP 模型（CreateSwapChainForHwnd 拒绝 DISCARD）——游戏若传
			// DISCARD 会导致创建失败 → 强制 FLIP_DISCARD（DX12 标准，DLSSG 也要求）
			desc1.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
			// v0.33：去 FRAME_LATENCY_WAITABLE_OBJECT（等待会串行化 Present → pacer 丢帧）
			// v0.36：Present(0)（无 VSync，SL pacer 全权）
			// v0.38（黑屏修复）：**必须保留 ALLOW_TEARING**——FLIP model 下 Present(0)
			// 无 VSync 要求 ALLOW_TEARING，否则 DXGI 拒绝 Present → 887A0001 黑屏
			// （21:12 日志实锤）。v0.36b 去掉它是错的（CS 也只去 FLW 保留 tearing）。
			// 撕裂由 SL pacer/RSYNC 管理，ALLOW_TEARING 只是"允许"无 VSync 呈现。
			desc1.Flags = swapChainDesc.Flags & ~DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT;
			IDXGISwapChain1* sc1 = nullptr;
			HRESULT hr = dxgiFactory->CreateSwapChainForHwnd(commandQueue.get(),
				a_swapChainDesc.OutputWindow, &desc1, nullptr, nullptr, &sc1);
			if (FAILED(hr)) {
				SKSE::log::error("[FrameGen] DLSSG: CreateSwapChainForHwnd failed: {:#x}", (unsigned)hr);
				return;
			}
			sc1->QueryInterface(IID_PPV_ARGS(&swapChain));
			sc1->Release();
			SKSE::log::info("[FrameGen] DLSSG: plain D3D12 swapchain created ({}x{})", swapChainDesc.Width, swapChainDesc.Height);
		} else if (a_enableFrameGeneration && LoadFFXLoader()) {
			// FFX SDK：创建支持帧生成的 D3D12 swapchain（FSR3 FG 帧缓冲管理）
			ffxCreateContextDescFrameGenerationSwapChainForHwndDX12 ffxDesc{};
			ffxDesc.header.type = FFX_API_CREATE_CONTEXT_DESC_TYPE_FRAMEGENERATIONSWAPCHAIN_FOR_HWND_DX12;
			ffxDesc.desc = &swapChainDesc;
			ffxDesc.dxgiFactory = dxgiFactory;
			ffxDesc.fullscreenDesc = nullptr;
			ffxDesc.gameQueue = commandQueue.get();
			ffxDesc.hwnd = a_swapChainDesc.OutputWindow;
			ffxDesc.swapchain = &swapChain;

			if (g_ffxCreateContext(&ffxSwapChainContext, &ffxDesc.header, nullptr) != FFX_API_RETURN_OK)
				SKSE::log::error("[FrameGen] Failed to create FFX FG swapchain context");
		} else if (!a_enableFrameGeneration) {
			// FrameGeneration=0：普通 D3D12 swapchain（仅 DLSS 超分/DLAA，无插帧）
			DXGI_SWAP_CHAIN_DESC1 desc1{};
			desc1.Width = swapChainDesc.Width;
			desc1.Height = swapChainDesc.Height;
			desc1.Format = swapChainDesc.Format;
			desc1.SampleDesc.Count = 1;
			desc1.BufferUsage = swapChainDesc.BufferUsage;
			desc1.BufferCount = 2;
			// v0.5：DX12 只支持 FLIP（游戏 DISCARD 会导致创建失败）——与 DLSSG 分支一致
			desc1.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
			desc1.Flags = swapChainDesc.Flags;
			IDXGISwapChain1* sc1 = nullptr;
			HRESULT hr = dxgiFactory->CreateSwapChainForHwnd(commandQueue.get(),
				a_swapChainDesc.OutputWindow, &desc1, nullptr, nullptr, &sc1);
			if (FAILED(hr)) {
				SKSE::log::error("[FrameGen] CreateSwapChainForHwnd failed: {:#x}", (unsigned)hr);
				return;
			}
			sc1->QueryInterface(IID_PPV_ARGS(&swapChain));
			sc1->Release();
			SKSE::log::info("[FrameGen] Normal D3D12 swapchain created (frame generation OFF)");
		} else {
			SKSE::log::error("[FrameGen] No FFX loader - cannot create D3D12 FG swapchain");
		}
		dxgiFactory->Release();  // GetParent 返回的引用用完释放（防泄漏）
		// 防御：swapChain 为空（FFX 失败）→ 直接返回，避免空指针
		if (!swapChain) {
			SKSE::log::error("[FrameGen] D3D12 swapchain not created - frame generation disabled");
			return;
		}

		// v0.33：GetBuffer 按实际 BufferCount（dlssgMode=3 对齐 CS pacer 余量；FSR3=2）
		const UINT bufferCount = dlssgMode ? 3 : 2;
		for (UINT i = 0; i < bufferCount; i++)
			DX::ThrowIfFailed(swapChain->GetBuffer(i, IID_PPV_ARGS(&swapChainBuffers[i])));

		frameIndex = swapChain->GetCurrentBackBufferIndex();
		SKSE::log::info("[FrameGen] D3D12 FG swapchain created ({}x{}, format {})",
			swapChainDesc.Width, swapChainDesc.Height, static_cast<int>(swapChainDesc.Format));
	}

	void DX12SwapChain::CreateInterop()
	{
		// v0.62: start the watchdog as soon as the interop exists - from here on
		// every Present can be attributed to a stage.
		StartWatchdog();

		HANDLE sharedFenceHandle;
		// v0.5：fence 初值 1（首帧 Signal(0)/Wait(0) 无同步——fence 初始即 0 时立即通过）
		DX::ThrowIfFailed(d3d12Device->CreateFence(1, D3D12_FENCE_FLAG_SHARED, IID_PPV_ARGS(&d3d12Fence)));
		DX::ThrowIfFailed(d3d12Device->CreateSharedHandle(d3d12Fence.get(), nullptr, GENERIC_ALL, nullptr, &sharedFenceHandle));
		DX::ThrowIfFailed(d3d11Device->OpenSharedFence(sharedFenceHandle, IID_PPV_ARGS(&d3d11Fence)));
		CloseHandle(sharedFenceHandle);
		fenceValue = 1;

		// v0.5.10（CS 同款，manual hooking 必需）：把 D3D12 swapchain upgrade 为 SL 代理
		// 接口——SL 由此进入呈现路径（每帧调 common 插件 presentCommon），DLSSG 插件才会
		// 注册 evaluateFeature 回调（否则恒 0x0 → slEvaluateFeature 28）。必须在
		// swapChainProxy 创建之前（proxy 包升级后的链，Present 才走 SL 路径）。
		// v0.25.1（用户 2026-08-30"勾选 DLSSG 没生效"实锤修复）：**device 也必须升级**——
		// CS（Upscaling.cpp:131-132）同时 upgrade device + swapchain；我们此前只升级
		// swapchain → presentCommon 链缺 device 环节 → DLSSG evaluateFeature 回调不注册
		// → slEvaluateFeature 28（日志 "Could not find 'evaluateFeature' callbacks for
		// feature 1000"）+ slAllocateResources 714156900。swapchain 手动升级在
		// eUseDXGIFactoryProxy 下 SL 已自动处理（日志 "Upgraded IDXGISwapChain v0 to v4"），
		// 重复手动升级失败（无害，已升级）。
		// v0.25.2（16:27 日志实锤）：**upgrade 必须传 D3D11 device（CS 同款）**——
		// v0.25.1 传 D3D12 device 失败 602942144 + SL 警告 "Plugins already initialized
		// but could be using the wrong device, please call slSetD3DDevice immediately
		// after creating desired device"——slUpgradeInterface 只认 DXGI/D3D11 接口，
		// 不认 D3D12 device。SL 的 presentCommon 链挂 D3D11 device → evaluateFeature
		// 回调注册需要它。D3D12 会话（Provider=1 DLSSG）由后面的 SetD3D12Device 提供。
		{
			ID3D11Device5* devIf = d3d11Device.get();
			Get().streamline.UpgradeInterface(reinterpret_cast<void**>(&devIf));
			if (devIf && devIf != d3d11Device.get())
				d3d11Device.attach(devIf);  // SL 返回新代理接口 → 接管（旧引用 SL proxy 持有）
		}
		Get().streamline.UpgradeInterface(reinterpret_cast<void**>(&swapChain));

		swapChainProxy = new DXGISwapChainProxy(swapChain);
		// v0.7.10：proxy 告知渲染尺寸（GetDesc 用）
		swapChainProxy->renderWidth = renderWidth;
		swapChainProxy->renderHeight = renderHeight;

		// v0.7.21：后缓冲 = 输出分辨率（4K）——Skyrim SE 引擎 composite 的 viewport 固定
		// 4K（screenSize），画到 1440p 后缓冲会裁剪（v0.7.8-20 多版实测：scissor patch
		// 只解决裁剪矩形、viewport 仍 4K → 画面放大 1/4 无解）。后缓冲 4K 时引擎
		// composite 完整（v0.7.15/16 画面正常实锤）。ENB+UI 画在 4K 后缓冲。
		// 低分辨率靠 DRS（kMAIN 1440p 渲染，Main_UpdateJitter hook）——引擎放大到 4K
		// 后缓冲（模糊）→ DLSS 4K 重建 + 锐化（比引擎放大清晰）+ 渲染负载降（帧数↑）。
		D3D11_TEXTURE2D_DESC texDesc11{};
		texDesc11.Width = swapChainDesc.Width;
		texDesc11.Height = swapChainDesc.Height;
		texDesc11.MipLevels = 1;
		texDesc11.ArraySize = 1;
		texDesc11.Format = swapChainDesc.Format;
		texDesc11.SampleDesc.Count = 1;
		texDesc11.SampleDesc.Quality = 0;
		texDesc11.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;

		// 游戏渲染目标（GetBuffer 返回它）——D3D11 共享纹理，D3D12 侧可 Copy
		swapChainBufferWrapped = new WrappedResource(texDesc11, d3d11Device.get(), d3d12Device.get());

		// v0.7.5：DLSS 超分独立输出纹理（CS 同款——超分 colorIn/colorOut 用不同资源，
		// in-place 原地超分效果不可靠）。超分结果写这里，再拷到 D3D12 + 进 FSR3 FG。
		// v0.7.6：colorOut 必须带 UNORDERED_ACCESS——DLSS/NGX 以 UAV 写入输出。
		// 复用 swapChain desc（无 UAV）→ NGX 报 RWFlagMissing → 输出永不被写 → 全黑（黑屏根因）。
		// v0.7.8：colorOut = 输出分辨率（4K）——DLSS 放大目标。
		D3D11_TEXTURE2D_DESC colorOutDesc = texDesc11;
		colorOutDesc.Width = swapChainDesc.Width;
		colorOutDesc.Height = swapChainDesc.Height;
		colorOutDesc.BindFlags = D3D11_BIND_UNORDERED_ACCESS | D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;
		colorOutWrapped = new WrappedResource(colorOutDesc, d3d11Device.get(), d3d12Device.get());

		// v0.8：DLSS-NR 输出纹理（同 colorOut：4K、UAV|RTV|SRV、DXGI NT 共享）。
		// NGX 要求 Color 与 Output 为不同资源（读写分离）；NR 结果写这里，
		// fence 后拷贝到 backbuffer 呈现（NR 开启时）。
		nrOutWrapped = new WrappedResource(colorOutDesc, d3d11Device.get(), d3d12Device.get());

		// v0.3：DLSSG 模式 → 深度/运动矢量共享纹理（每帧从引擎目标拷贝）
		// v0.5.7（CS 官方方案）：引擎深度 D32_FLOAT 不在 DXGI NT 共享白名单 →
		// depth 共享纹理**自建**：kMAIN 尺寸 + R32_FLOAT（可 NT 共享）+ SRV|RTV（shader 拷贝输出）；
		// mvec 引擎格式（R16G16_FLOAT）在共享白名单 → 原样 desc 创建。
		if (dlssgMode) {
			if (auto* renderer = RE::BSGraphics::Renderer::GetSingleton()) {
				auto& main = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMAIN];
				if (main.texture) {
					D3D11_TEXTURE2D_DESC dDesc{};
					static_cast<ID3D11Texture2D*>(main.texture)->GetDesc(&dDesc);
					// v0.56: eager interop texture fixed to the output resolution. It used to
					// inherit the engine kMAIN desc (render resolution), while the lazy path
					// below forces the output resolution - the same buffer came out at two
					// different sizes depending on which path happened to run. FSR3 frame
					// generation requires depth to match the colour input size anyway.
					dDesc.Width = swapChainDesc.Width;
					dDesc.Height = swapChainDesc.Height;
					dDesc.Format = DXGI_FORMAT_R32_FLOAT;
					dDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;
					depthWrapped = new WrappedResource(dDesc, d3d11Device.get(), d3d12Device.get());
					SKSE::log::info("[FrameGen] DLSSG: depth interop texture created (R32_FLOAT {0}x{1}) [output res]", dDesc.Width, dDesc.Height);
				}
				auto& mvecTex = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
				if (mvecTex.texture) {
					D3D11_TEXTURE2D_DESC mDesc{};
					static_cast<ID3D11Texture2D*>(mvecTex.texture)->GetDesc(&mDesc);
					// v0.56: same as depth above - both creation paths now agree.
					mDesc.Width = swapChainDesc.Width;
					mDesc.Height = swapChainDesc.Height;
					mvecWrapped = new WrappedResource(mDesc, d3d11Device.get(), d3d12Device.get());
					SKSE::log::info("[FrameGen] DLSSG: mvec interop texture created (format {0})", static_cast<int>(mDesc.Format));
				}
				SKSE::log::info("[FrameGen] DLSSG: depth/mvec interop textures ready ({}x{})",
					depthWrapped ? "depth ok" : "depth MISSING",
					mvecWrapped ? "mvec ok" : "mvec MISSING");
			}
		}
		SKSE::log::info("[FrameGen] D3D11<->D3D12 interop ready");
	}

	DXGISwapChainProxy* DX12SwapChain::GetSwapChainProxy()
	{
		return swapChainProxy;
	}

	// v0.5.7（CS 方案）：引擎深度 D32_FLOAT → R32_FLOAT 共享纹理的 shader 拷贝。
	// CopyResource 格式不匹配（D32 vs R32），用全屏三角形 PS 读取 depthSRV 写 RTV。
	// 首次调用惰性编译 shader + 建光栅/混合状态；失败只 warn（depth 空 → DLSSG 直通）。
	// v0.7.8：共享 VS/光栅/混合状态抽到 EnsureUpscaleStates（depth/mvec/color 三处共用），
	// PS 各自编译。depth/mvec/color 均为"源渲染尺寸 → 目标输出尺寸"的采样放大拷贝。
	void DX12SwapChain::EnsureUpscaleStates()
	{
		static bool ensured = false;
		static bool failed = false;
		if (ensured || failed)
			return;
		try {
			if (!upscaleVS) {
				auto vsBlob = CompileShaderFromFile(L"Data\\Shaders\\Upscaling\\UpscaleVS.hlsl", "VSHADER", "vs_5_0");
				DX::ThrowIfFailed(d3d11Device->CreateVertexShader(vsBlob->GetBufferPointer(), vsBlob->GetBufferSize(), nullptr, upscaleVS.put()));
			}
			if (!upscaleRasterizerState) {
				D3D11_RASTERIZER_DESC rasterizerDesc = {};
				rasterizerDesc.FillMode = D3D11_FILL_SOLID;
				rasterizerDesc.CullMode = D3D11_CULL_NONE;
				rasterizerDesc.FrontCounterClockwise = false;
				rasterizerDesc.DepthClipEnable = false;
				DX::ThrowIfFailed(d3d11Device->CreateRasterizerState(&rasterizerDesc, upscaleRasterizerState.put()));
			}
			if (!upscaleBlendState) {
				D3D11_BLEND_DESC blendDesc = {};
				blendDesc.AlphaToCoverageEnable = false;
				blendDesc.IndependentBlendEnable = false;
				blendDesc.RenderTarget[0].BlendEnable = false;
				blendDesc.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
				DX::ThrowIfFailed(d3d11Device->CreateBlendState(&blendDesc, upscaleBlendState.put()));
			}
			ensured = true;
		} catch (const DX::com_exception& e) {
			failed = true;
			SKSE::log::warn("[FrameGen] upscale copy states init failed ({})", e.what());
		}
	}

	void DX12SwapChain::CopyDepthToShared(ID3D11ShaderResourceView* a_depthSRV, ID3D11RenderTargetView* a_depthRTV)
	{
		// 失败只重试一次（避免每帧 D3DCompileFromFile 刷屏）
		static bool depthCopyFailed = false;
		if (!depthCopyReady && !depthCopyFailed) {
			try {
				EnsureUpscaleStates();
				if (!copyDepthPS) {
					auto psBlob = CompileShaderFromFile(L"Data\\Shaders\\Upscaling\\CopyDepthToSharedBufferPS.hlsl", "PSHADER", "ps_5_0");
					DX::ThrowIfFailed(d3d11Device->CreatePixelShader(psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, copyDepthPS.put()));
				}
				depthCopyReady = true;
				SKSE::log::info("[FrameGen] depth-copy shaders ready (UpscaleVS + CopyDepthToSharedBufferPS)");
			} catch (const DX::com_exception& e) {
				depthCopyFailed = true;
				SKSE::log::warn("[FrameGen] depth-copy shader init failed - depth stays empty ({})", e.what());
				return;
			}
		}
		if (!depthCopyReady)
			return;

		// 全屏三角形：引擎深度 SRV → R32_FLOAT 共享纹理 RTV（D3D11 队列序，fence Signal 前）
		// v0.7.8：目标 = 输出分辨率（swapChainDesc），PS 采样放大（引擎深度是渲染尺寸）
		D3D11_VIEWPORT viewport = {};
		viewport.TopLeftX = 0.0f;
		viewport.TopLeftY = 0.0f;
		viewport.Width = static_cast<float>(swapChainDesc.Width);
		viewport.Height = static_cast<float>(swapChainDesc.Height);
		viewport.MinDepth = 0.0f;
		viewport.MaxDepth = 1.0f;
		d3d11Context->RSSetViewports(1, &viewport);

		d3d11Context->IASetInputLayout(nullptr);
		d3d11Context->IASetVertexBuffers(0, 0, nullptr, nullptr, nullptr);
		d3d11Context->IASetIndexBuffer(nullptr, DXGI_FORMAT_UNKNOWN, 0);
		d3d11Context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
		d3d11Context->VSSetShader(upscaleVS.get(), nullptr, 0);
		d3d11Context->RSSetState(upscaleRasterizerState.get());
		d3d11Context->OMSetBlendState(upscaleBlendState.get(), nullptr, 0xffffffff);

		ID3D11ShaderResourceView* srvViews[1] = { a_depthSRV };
		d3d11Context->PSSetShaderResources(0, 1, srvViews);
		ID3D11RenderTargetView* rtvViews[1] = { a_depthRTV };
		d3d11Context->OMSetRenderTargets(1, rtvViews, nullptr);
		d3d11Context->PSSetShader(copyDepthPS.get(), nullptr, 0);
		d3d11Context->Draw(3, 0);

		// 清理绑定（防止污染游戏后续渲染状态）
		ID3D11ShaderResourceView* nullSrv[1] = { nullptr };
		d3d11Context->PSSetShaderResources(0, 1, nullSrv);
		d3d11Context->OMSetRenderTargets(0, nullptr, nullptr);
		d3d11Context->PSSetShader(nullptr, nullptr, 0);
		d3d11Context->VSSetShader(nullptr, nullptr, 0);
	}

	// v0.7.8：mvec 采样放大拷贝（引擎 mvec 渲染尺寸 → 4K 共享纹理，FSR3 FG 用）
	void DX12SwapChain::CopyMvecToShared(ID3D11ShaderResourceView* a_mvecSRV, ID3D11RenderTargetView* a_mvecRTV)
	{
		if (!mvecCopyReady && !mvecCopyFailed) {
			try {
				EnsureUpscaleStates();
				if (!copyMvecPS) {
					auto psBlob = CompileShaderFromFile(L"Data\\Shaders\\Upscaling\\CopyMvecToSharedBufferPS.hlsl", "PSHADER", "ps_5_0");
					DX::ThrowIfFailed(d3d11Device->CreatePixelShader(psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, copyMvecPS.put()));
				}
				mvecCopyReady = true;
				SKSE::log::info("[FrameGen] mvec-copy shaders ready (CopyMvecToSharedBufferPS)");
			} catch (const DX::com_exception& e) {
				mvecCopyFailed = true;
				SKSE::log::warn("[FrameGen] mvec-copy shader init failed - mvec stays empty ({})", e.what());
				return;
			}
		}
		if (!mvecCopyReady)
			return;

		D3D11_VIEWPORT viewport = {};
		viewport.TopLeftX = 0.0f;
		viewport.TopLeftY = 0.0f;
		viewport.Width = static_cast<float>(swapChainDesc.Width);
		viewport.Height = static_cast<float>(swapChainDesc.Height);
		viewport.MinDepth = 0.0f;
		viewport.MaxDepth = 1.0f;
		d3d11Context->RSSetViewports(1, &viewport);

		d3d11Context->IASetInputLayout(nullptr);
		d3d11Context->IASetVertexBuffers(0, 0, nullptr, nullptr, nullptr);
		d3d11Context->IASetIndexBuffer(nullptr, DXGI_FORMAT_UNKNOWN, 0);
		d3d11Context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
		d3d11Context->VSSetShader(upscaleVS.get(), nullptr, 0);
		d3d11Context->RSSetState(upscaleRasterizerState.get());
		d3d11Context->OMSetBlendState(upscaleBlendState.get(), nullptr, 0xffffffff);

		ID3D11ShaderResourceView* srvViews[1] = { a_mvecSRV };
		d3d11Context->PSSetShaderResources(0, 1, srvViews);
		ID3D11RenderTargetView* rtvViews[1] = { a_mvecRTV };
		d3d11Context->OMSetRenderTargets(1, rtvViews, nullptr);
		d3d11Context->PSSetShader(copyMvecPS.get(), nullptr, 0);
		d3d11Context->Draw(3, 0);

		ID3D11ShaderResourceView* nullSrv[1] = { nullptr };
		d3d11Context->PSSetShaderResources(0, 1, nullSrv);
		d3d11Context->OMSetRenderTargets(0, nullptr, nullptr);
		d3d11Context->PSSetShader(nullptr, nullptr, 0);
		d3d11Context->VSSetShader(nullptr, nullptr, 0);
	}


	void DX12SwapChain::SetD3D11Device(ID3D11Device* a_d3d11Device)
	{
		DX::ThrowIfFailed(a_d3d11Device->QueryInterface(IID_PPV_ARGS(&d3d11Device)));
	}

	void DX12SwapChain::SetD3D11DeviceContext(ID3D11DeviceContext* a_d3d11Context)
	{
		DX::ThrowIfFailed(a_d3d11Context->QueryInterface(IID_PPV_ARGS(&d3d11Context)));
	}

	// v0.62: 1 Hz watchdog. Writes with fopen/fflush/fclose rather than through
	// SKSE::log, deliberately: if the render thread is blocked the SKSE logger may
	// never flush its tail, and a process that is force-killed loses whatever the
	// sink still buffers. A plain append + flush per tick is the only write that is
	// guaranteed to reach the disk before the process dies, which is exactly the
	// situation this instrument exists for.
		// v0.71: can this window be presented to at all?
	// A FLIP_DISCARD swap chain (BufferCount=3) blocks inside Present() until a
	// queued buffer is released, and DXGI stops releasing buffers for a window that
	// is occluded or in the background. Test the two cheap states that predict it
	// instead of waiting to be told: minimised, or no longer the foreground window.
	// Deliberately conservative -- if the hwnd is unknown we assume focus, because
	// changing behaviour on a guess is worse than leaving the old path alone.
	static std::atomic<int> g_lastFocus{ 1 };          // 1 = foreground (watchdog field)

	// v1.03b: the one definition of the DLSS-G in-call flag declared in the header.
	// Published by the present thread around slDLSSGSetOptions, read by the watchdog
	// so a stall can be attributed to a call by name instead of to "d3d11 Wait".
	std::atomic<int> g_inSetOptions{ 0 };
	// v1.04b: see the header. Stamped immediately before every blocking Present.
	std::atomic<long long> g_presentEnteredMs{ 0 };

	static bool FocusAllowsPresenting(HWND a_hwnd)
	{
		if (!a_hwnd)
			return true;                 // unknown window: do not change behaviour
		if (::IsIconic(a_hwnd))
			return false;
		const HWND fg = ::GetForegroundWindow();
		if (!fg)
			return true;                 // lock screen / mode change: transient, not a hang
		// v0.71b: compare roots, not handles. If the swap chain window is a child of a
		// wrapper, GetForegroundWindow() never returns it and a raw == would report
		// "unfocused" on every frame of the session - i.e. frame generation off.
		const HWND ourRoot = ::GetAncestor(a_hwnd, GA_ROOT);
		const HWND fgRoot = ::GetAncestor(fg, GA_ROOT);
		if (ourRoot && fgRoot)
			return ourRoot == fgRoot;
		return fg == a_hwnd;
	}

	// v0.73: everything the watchdog needs is an atomic it can read without ever
	// entering the driver, a lock, or the CRT.
	static bool g_bypassReported = false;                    // one BYPASS line per focus loss
	static std::atomic<long long> g_lastSilentMs{ -1 };      // published by the watchdog
	static std::atomic<unsigned long long> g_hangFence11{ ~0ull };
	static std::atomic<unsigned long long> g_hangFence12{ ~0ull };
	static std::atomic<unsigned long long> g_samplerTicks{ 0 };
	// v0.74: unconditional sampler. g_lastSilentMs is still published, but no
	// longer used as a gate - see StartGpuSampler() for why that gate is what
	// hid this failure for three rounds.
	static std::atomic<long long> g_gpuSilentMs{ -1 };       // sampler's own view of lastFrameEndMs
	static std::atomic<unsigned long long> g_fenceRaw11{ ~0ull };
	static std::atomic<unsigned long long> g_fenceRaw12{ ~0ull };

	// v0.76: the one question every other field here cannot answer.
	// All of them are sampled from the render thread or from the display driver.
	// A window whose message pump has stopped while the render thread keeps
	// presenting reads as perfectly healthy in this file, yet it is exactly
	// what the player calls a freeze and what USER32 paints as "Not Responding".
	// msg=0 -> the window did not answer WM_NULL within 200 ms.
	// alive=0 -> the window itself is gone (the process is on its way out).
	static std::atomic<int> g_lastMsgOk{ 1 };
	static std::atomic<int> g_lastWinAlive{ 0 };
	// v0.76: the hwnd the watchdog should probe, published once by Present.
	// Never read a member from the watchdog thread -- it must not touch
	// anything the render thread may be inside of.
	static std::atomic<std::uintptr_t> g_probeHwnd{ 0 };

	// v0.73: the watchdog log path, resolved once at plugin load and kept in a plain
	// char buffer. DllMain needs it during process detach, where calling
	// SHGetFolderPath or touching the CRT is not worth the risk.
	static char g_watchdogLogPath[MAX_PATH * 2] = {};

	void InitWatchdogLogPath()
	{
		// Same directory SKSE writes its own logs to, so one folder holds the story.
		std::string p;
		char buf[MAX_PATH] = {};
		if (SUCCEEDED(::SHGetFolderPathA(nullptr, CSIDL_PERSONAL, nullptr, 0, buf))) {
			p = buf;
			p += "\\My Games\\Skyrim Special Edition\\SKSE\\";
		}
		p += "DynamicShaderFrameGen.watchdog.log";
		std::snprintf(g_watchdogLogPath, sizeof(g_watchdogLogPath), "%s", p.c_str());
	}

	const char* WatchdogLogPath()
	{
		return g_watchdogLogPath;
	}

	// v0.73: the only thread allowed to touch the fences besides the render thread,
	// and it does nothing else. It samples ONLY while the render thread has already
	// been silent for over 1.5 s, so ordinary play never has a non-owning thread
	// inside the display driver, and a hang still gets the answer the watchdog
	// cannot produce on its own:
	//   stim keeps climbing -> the GPU timeline is alive, the render thread is
	//                          parked in CPU-side code;
	//   stim frozen while the watchdog keeps writing -> the sampler itself is parked
	//                          in the driver, which is a GPU/driver wedge.
	void DX12SwapChain::StartGpuSampler()
	{
		static std::atomic<bool> started{ false };
		bool expected = false;
		if (!started.compare_exchange_strong(expected, true))
			return;

		std::thread([this]() {
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(200));
				// v0.74: unconditional. v0.73 gated this on silent >= 1500 ms so
				// the sampler never entered the driver during normal play. That
				// gate assumed a GPU stall shows up as a silent render thread -
				// it does not. In the 07:11 run the render thread was finishing a
				// Present every 20 ms while the D3D12 queue never advanced, so the
				// gate held the sampler shut for the entire failure and the one
				// fence sample we have (1/1) is an accident of the first two
				// seconds. Measure always; the cost is one 200 ms thread.
				const unsigned long long f11 = d3d11Fence
					? static_cast<unsigned long long>(d3d11Fence->GetCompletedValue()) : ~0ull;
				const unsigned long long f12 = d3d12Fence
					? static_cast<unsigned long long>(d3d12Fence->GetCompletedValue()) : ~0ull;
				// If this call blocks (device wedged) the sampler stops, and that
				// is itself the reading: stim freezes while frames keeps moving.
				g_fenceRaw11.store(f11);
				g_fenceRaw12.store(f12);
				g_hangFence11.store(f11);
				g_hangFence12.store(f12);
				const long long lastEnd = static_cast<long long>(lastFrameEndMs.load());
				g_gpuSilentMs.store(lastEnd ? -1 : -1);
				g_samplerTicks.fetch_add(1);
			}
		}).detach();
	}

	void DX12SwapChain::StartWatchdog()
	{
		static std::atomic<bool> started{ false };
		bool expected = false;
		if (!started.compare_exchange_strong(expected, true))
			return;

		StartGpuSampler();

		// v0.73: path comes from InitWatchdogLogPath() so DllMain can reuse it.
		const std::string path = WatchdogLogPath();

		std::thread([this, path]() {
			auto& self = *this;
			SKSE::log::info("[XRAY] WATCHDOG started (1 Hz) - file: {} (stage= names the blocking call)", path);
			// v0.71: one 200 ms slice per tick (was 5 x 200 ms = 1 Hz). A hang is only
			// ever localised by the last line the watchdog managed to write, and at 1 Hz
			// that line can sit a whole second -- about 40 frames -- behind the freeze.
			// 200 ms puts it within ~8. STALLED stays at 1 Hz so the file stays readable.
			int tick = 0;
			for (;;) {
				if (self.watchdogStop.load())
					return;
				std::this_thread::sleep_for(std::chrono::milliseconds(200));
				++tick;
				const long long nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
					std::chrono::steady_clock::now().time_since_epoch()).count();
				const std::uint64_t frames = self.frameCounter.load();
				const long long lastEnd = self.lastFrameEndMs.load();
				const long long silent = lastEnd ? (nowMs - lastEnd) : -1;
				g_lastSilentMs.store(silent);   // v0.73: lets the sampler decide when to look
				// v0.63：装载期不是卡死。21:54 那次运行在约 20s 装载里 frames 恒为 1、
				// stage 恒为 "d3d11 Wait"，看门狗连打 19 行 RENDER THREAD STALLED —— 全是
				// 假警报。判据收紧：渲染线程必须"曾经跑顺过"（frames>=60）才允许报卡死，
				// 未达标只记 silent（装载期的正常表现）。
				const bool warm = frames >= 60;
				if (FILE* f = std::fopen(path.c_str(), "a")) {
					// v0.73: the fence values now come from the sampler thread, through
					// atomics. v0.72 read them right here, which put two driver calls in
					// the one thread whose whole job is to keep writing while everything
					// else is stuck - a watchdog that can block is not a watchdog. See
					// StartGpuSampler(): stim=0 means no hang was ever suspected and the
					// field is empty; stim>0 means a hang was under investigation and the
					// numbers are live. UINT64_MAX still means device lost / no fence.
					const unsigned long long fence11 = g_hangFence11.load();
					const unsigned long long fence12 = g_hangFence12.load();
					const unsigned long long stim = g_samplerTicks.load();
					char fenceTxt[48];
					if (fence11 == ~0ull && fence12 == ~0ull)
						std::snprintf(fenceTxt, sizeof(fenceTxt), "-/-");
					else
						std::snprintf(fenceTxt, sizeof(fenceTxt), "%llu/%llu", fence11, fence12);
					// v0.73: wall clock beside the monotonic counter. Lining this file up
					// against the others needed a second log with a matching clock - the
					// absolute time of a freeze was reconstructed by subtraction. One
					// extra field removes that whole class of mistake.
					SYSTEMTIME wtc{};
					::GetLocalTime(&wtc);
					// v0.71: focus belongs in the stamp - focus=0 with a stall is a window
					// that could not present, not a frame loop that died on its own.
					const bool stalled = lastEnd != 0 && warm && silent > 1500;
					// v0.74: the fields that catch a stalled GPU queue under a
					// healthy render thread. queued>3 = CPU ran ahead of the GPU
					// (Present stopped providing backpressure); dsync=1 = our
					// frameIndex no longer matches DXGI's; lastPr not climbing =
					// Present returns success without flipping.
					// v1.28 -- the first reading of this stall that does not come from us
					// or from DXGI. frames/fence/lastPr/presentAge all freeze together
					// (03:17 run: 03:16:50.575 -> 03:17:10.861, 20789 ms) which proves
					// the render thread was not inside our code, but says nothing about
					// what the process was doing instead. cpuD is that process's own
					// user+kernel time over this 200 ms slice:
					//   cpuD ~ 0    -> the process is BLOCKED (IO, a lock, a driver
					//                  wait). Nothing is spinning and no stack is hot.
					//   cpuD ~ 200  -> one thread is burning a full core right now.
					//   cpuD > 200  -> more than one thread is, or the slice overran.
					// GetProcessTimes only reads; it cannot perturb the process.
					unsigned long long cpuMs = 0;
					{
						FILETIME c{}, e{}, k{}, u{};
						if (::GetProcessTimes(::GetCurrentProcess(), &c, &e, &k, &u)) {
							const auto toMs = [](const FILETIME& ft) {
								return (static_cast<unsigned long long>(ft.dwHighDateTime) << 32)
									| static_cast<unsigned long long>(ft.dwLowDateTime);
							};
							cpuMs = (toMs(k) + toMs(u)) / 10000ull;   // 100 ns ticks -> ms
						}
					}
					static unsigned long long s_lastCpuMs = 0;
					const unsigned long long cpuDelta =
						(cpuMs >= s_lastCpuMs) ? (cpuMs - s_lastCpuMs) : 0ull;
					s_lastCpuMs = cpuMs;
					const unsigned long long queued = g_queuedDepth.load();
					const unsigned long long lastPr = g_lastPresentCount.load();
					const unsigned long long dsync = g_flipDesync.load();
					// v0.76: ask the window the same question USER32 asks before it
					// paints "Not Responding". SMTO_ABORTIFHUNG makes the call return
					// *now* if the target is already hung instead of burning the full
					// timeout, and the timeout bounds the worst case for a watchdog
					// that must never park. A dead window answers nothing at all, so
					// alive= is checked first and msg= is only meaningful when it is 1.
					int msgOk = g_lastMsgOk.load();
					int winAlive = g_lastWinAlive.load();
					if ((tick % 5) == 0) {
						const HWND probe = reinterpret_cast<HWND>(g_probeHwnd.load());
						if (probe && ::IsWindow(probe)) {
							DWORD_PTR res = 0;
							const LRESULT lr = ::SendMessageTimeoutA(probe, WM_NULL, 0, 0,
								SMTO_ABORTIFHUNG | SMTO_BLOCK, 200, &res);
							msgOk = (lr != 0) ? 1 : 0;
							winAlive = 1;
						} else {
							msgOk = 0;
							winAlive = 0;
						}
						g_lastMsgOk.store(msgOk);
						g_lastWinAlive.store(winAlive);
					}
					std::fprintf(f, "[%lld] %02d:%02d:%02d.%03d frames=%llu silent=%lldms "
						"stage=%s focus=%d fence=%s stim=%llu queued=%llu lastPr=%llu dsync=%llu "
						"msg=%d alive=%d presentAge=%lldms cpuD=%llums%s\n",
						nowMs, wtc.wHour, wtc.wMinute, wtc.wSecond, wtc.wMilliseconds,
						static_cast<unsigned long long>(frames), silent,
					g_inSetOptions.load() ? "d3d11 SetDLSSGOptions" : self.lastStage(),
						g_lastFocus.load(), fenceTxt, stim, queued, lastPr, dsync,
						msgOk, winAlive,
						(g_presentEnteredMs.load() > 0)
							? (nowMs - g_presentEnteredMs.load())
							: 0LL,
						cpuDelta,
						(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
					std::fflush(f);
					std::fclose(f);
				}
			}
		}).detach();
	}

	// v1.03b: bounded fence wait. ID3D11DeviceContext4::Wait has NO timeout: it
	// returns when the D3D12 queue signals a_fenceValue, or never. On the
	// 2026-09-18 18:23 run it was "or never" for 19.9 s while the watchdog
	// reported fence=2/2 and queued=1 - the queue was idle by the fence's own
	// account while the wait refused to return. A wait that cannot time out is a
	// wait that can turn any hiccup into a freeze, with no log line naming it.
	//
	// Polling GetCompletedValue costs one call per millisecond of hitch and zero
	// extra calls while the fence advances normally, because the loop tests
	// before sleeping. On timeout the numbers are logged and the frame is
	// dropped: a dropped frame is recoverable, a permanent stall is what the
	// user actually saw.
	bool DX12SwapChain::WaitFenceBounded(UINT64 a_fenceValue, std::uint32_t a_timeoutMs)
	{
		if (!d3d12Fence || !d3d11Context)
			return true;   // nothing to wait on; never invent a stall
		if (d3d12Fence->GetCompletedValue() >= a_fenceValue)
			return true;
		const auto t0 = std::chrono::steady_clock::now();
		for (;;) {
			if (d3d12Fence->GetCompletedValue() >= a_fenceValue)
				return true;
			const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
				std::chrono::steady_clock::now() - t0).count();
			if (elapsed >= static_cast<long long>(a_timeoutMs)) {
				static std::atomic<int> fenceTimeoutLogged{ 0 };
				if (fenceTimeoutLogged.fetch_add(1) < 10) {
					SKSE::log::error("[XRAY] FENCE WAIT TIMED OUT after {} ms: wanted {} completed {} "
						"(queued={} frameIndex={}) - dropping this frame instead of parking the render "
						"thread. A queue that never reaches the fence is the freeze this guard exists "
						"for (v1.03b)", elapsed, a_fenceValue, d3d12Fence->GetCompletedValue(),
						static_cast<unsigned long long>(g_queuedDepth.load()), frameIndex);
				}
				return false;
			}
			std::this_thread::sleep_for(std::chrono::milliseconds(1));
		}
	}

	// v0.81 -- present-thread census.
	//
	// Records, per thread id, how many frames that thread actually presented, and
	// reports the first time a second id shows up - with BOTH counts, because the
	// counts are the whole point. "Two thread ids" is not a defect; "the thread
	// that presents every frame differs from the thread that owns the per-frame
	// state" might be. v0.80 could not tell those apart and refused the wrong one.
	void DX12SwapChain::CensusPresentThread()
	{
		const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());
		const long long nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
			std::chrono::steady_clock::now().time_since_epoch()).count();
		++presentCensusFrames;

		// Hot path: the first slot almost always matches, and it needs no lock.
		const int n = presentThreadCount.load(std::memory_order_acquire);
		for (int i = 0; i < n; ++i) {
			if (presentThreads[i].tid == tid) {
				++presentThreads[i].frames;
				presentThreads[i].lastMs = nowMs;
				return;
			}
		}

		// A thread id we have not seen. Rare - at most kPresentThreadMax times.
		if (n >= kPresentThreadMax) {
			if (presentCensusFrames % 2000 == 1)
				SKSE::log::warn("[PRESENT] census: more than {} presenter threads seen; "
					"further ids are not tracked", kPresentThreadMax);
			return;
		}
		auto& slot = presentThreads[n];
		slot.tid = tid;
		slot.frames = 1;
		slot.firstMs = nowMs;
		slot.lastMs = nowMs;
		presentThreadCount.store(n + 1, std::memory_order_release);

		if (n == 0) {
			SKSE::log::info("[PRESENT] census: first presenter tid={} - frames and time span "
				"for every presenter are reported below as they appear", tid);
			return;
		}
		SKSE::log::warn("[PRESENT] census: NEW presenter tid={} - now {} distinct threads have "
			"presented this swap chain. Per-thread frames: {}",
			tid, n + 1, DescribePresentThreads());
	}

	// v0.81 -- one-line census body, separate so both call sites stay short.
	std::string DX12SwapChain::DescribePresentThreads()
	{
		std::string s;
		const int n = presentThreadCount.load(std::memory_order_acquire);
		for (int i = 0; i < n; ++i) {
			if (!s.empty())
				s += " | ";
			s += "tid=" + std::to_string(presentThreads[i].tid) +
				" frames=" + std::to_string(presentThreads[i].frames) +
				" span=" + std::to_string(presentThreads[i].lastMs - presentThreads[i].firstMs) + "ms";
		}
		if (s.empty())
			s = "(none)";
		return s;
	}

	HRESULT DX12SwapChain::Present(UINT SyncInterval, UINT Flags)
	{
		auto& fg = Get();

		// v0.62: stamp every exit path (there are three return S_OK branches). The
		// watchdog compares this against its own clock: a stamp that stops moving
		// while the watchdog keeps ticking is a stalled render thread, and m_stage
		// then says which call it is stalled in.
		struct FrameStamp
		{
			explicit FrameStamp(DX12SwapChain* a_self) : self(a_self) {}
			DX12SwapChain* self;
			~FrameStamp()
			{
				self->lastFrameEndMs.store(std::chrono::duration_cast<std::chrono::milliseconds>(
					std::chrono::steady_clock::now().time_since_epoch()).count());
			}
		} frameStamp(this);
		++frameCounter;
		// v0.74: retire finished frames, so queuedDepth is a live queue depth
		// rather than a counter that only grows. fenceValue is the *next* value
		// to signal, so everything <= what the fence has completed is retired;
		// whatever sits between that and fenceValue-1 is still in flight.
		if (d3d12Fence) {
			const unsigned long long done =
				static_cast<unsigned long long>(d3d12Fence->GetCompletedValue());
			const unsigned long long inFlight =
				(fenceValue > done + 1) ? (fenceValue - 1 - done) : 0;
			g_queuedDepth.store(inFlight);
		}
		m_stage = "present entry";

		// v1.22: sample the content the plugin is about to hand to the swap chain.
		// One call site, on the path all three return branches share, so no branch
		// has to be touched to cover them.
		PixelProbeTick();
		// v0.81 -- who actually presents? Observation only; this never refuses.
		CensusPresentThread();

		// v0.7.2：每帧轮询 Home 键（短按切插帧/长按开菜单）——SKSE 输入事件是事件驱动
		// 不支持长按检测，这里直接读硬件状态
		fg.PollHomeKey();

		// v0.26：ForceBorderless 防重置——游戏/INI 若把窗口改回带边框或非全屏
		// （玩家在游戏设置里切窗口模式等），每帧强制恢复无边框铺满（幂等，<1μs）
		fg.EnsureBorderless();

		// ===== FPS 诊断探针（v0.42）——每 2 秒报告：真实帧率 / 模式 / 倍率 / DLSSG 上限 =====
		{
			static auto probeLast = std::chrono::steady_clock::now();
			static std::uint64_t probeFrames = 0;
			probeFrames++;
			const auto probeNow = std::chrono::steady_clock::now();
			const double elapsed = std::chrono::duration<double>(probeNow - probeLast).count();
			if (elapsed >= 2.0) {
				const double realFps = probeFrames / elapsed;
				// v0.51（诚实上报）：原 `present~=real*mult` 是**算出来的理论上限**，不是测量值；
				// `dlssgMax` 打印的是本地覆盖后的值。两者都会被误读成"插帧已生效"。现在拆开：
				//   cap~     理论呈现上限（= real * factor，明确标注是推算）
				//   ask      本次向运行时请求的插帧数
				//   accepted 运行时**实际接受**的插帧数（0 = 被拒/未知）
				std::uint32_t mult = 1;
				if (dlssgMode)
					mult = fg.streamline.dlssgFramesToGenerate + 1;
				else if (fg.fgActive.load())
					mult = 2;                                          // FSR3 2x
				// v0.52：同时打出「本次运行真正在跑的 Provider」和「INI 里写的 Provider」。
				// 只打前者的话，用户在菜单里切了 Provider 会以为"切了没反应"——其实只是没重启。
				const int cfgProvider = fg.settings.provider;
				SKSE::log::info("[FrameGen] FPS probe: real={:.1f} | {} | cap~={:.1f} (=real*{}, COMPUTED not measured) | "
					"hwMax={} ask={} accepted={} | cfgProvider={}{}",
					realFps, dlssgMode ? "DLSSG" : "FSR3", realFps * mult, mult,
					fg.streamline.dlssgMaxFramesToGenerate + 1, fg.streamline.dlssgFramesToGenerate + 1,
					fg.streamline.dlssgAcceptedFrames ? fg.streamline.dlssgAcceptedFrames + 1 : 0,
					cfgProvider, cfgProvider == providerAtCreate ? "" : " (CHANGED - RESTART REQUIRED)");
				probeFrames = 0;
				probeLast = probeNow;

				// v1.26 -- measured, not computed. DXGI keeps its own present counter for
				// the swap chain, so the ratio of ITS advance to OURS over the same
				// window is the number of flips the chain really did per real frame --
				// from a component neither the plugin nor the second DLSS-G driver in
				// this process controls. On the 02:25 run the watchdog's lastPr/frames
				// pair read 1.00 across the entire loading screen and exactly 4.00 from
				// the frame the guard released onwards. Every other multiplier number
				// this project prints is either our request or the runtime's report.
				{
					static unsigned long long s_lastFlips = 0;
					static unsigned long long s_lastFrames = 0;
					static bool s_haveFlipBase = false;
					const unsigned long long flips = g_lastPresentCount.load();
					const unsigned long long fr = static_cast<unsigned long long>(frameCounter.load());
					if (s_haveFlipBase && fr > s_lastFrames && flips > s_lastFlips) {
						SKSE::log::info("[FrameGen] FLIPS per real frame = {:.2f} "
							"(DXGI lastPresentCount {} -> {}, our Present {} -> {}) - DXGI's own "
							"counter, not the runtime's report and not real*mult",
							static_cast<double>(flips - s_lastFlips) / static_cast<double>(fr - s_lastFrames),
							s_lastFlips, flips, s_lastFrames, fr);
					}
					s_lastFlips = flips;
					s_lastFrames = fr;
					s_haveFlipBase = true;
				}
			}
		}

		// v0.7.13：DRS（dynamicResolution）与 DLSS jitter 由 Main_UpdateJitter hook
		// 在渲染前设置（v0.7.11 已验证 kMAIN 2560x1440）；DLSS 超分由
		// MenuManagerDrawInterfaceStart hook 在 UI 绘制前执行（写 kFRAMEBUFFER）。
		// Present 只做：FSR3 FG + 后缓冲 → D3D12 拷贝 + 呈现（纯直通，不覆盖画面）。

		// v0.5.5: stage marker - pinpoint which D3D11/D3D12 call throws (E_INVALIDARG black screen debug)
		m_stage = "enter";

		// v0.71: focus/occlusion sample, once per frame, BEFORE anything consumes it
		// (lesson 58: a guard whose input is sampled downstream of itself can never be
		// verified). The 23:40:22 session froze 55 ms after "Game lost focus", so this
		// value is the first thing the next hang log will be read for.
		// v0.71c: IDXGISwapChain1::GetHwnd() is the window this swap chain actually
		// presents to. swapChainDesc is a DESC1 here and has no OutputWindow member
		// (using it cost one build: C2039). Null is safe - FocusAllowsPresenting
		// leaves the old behaviour alone when it has no window to judge.
		// v0.71d: IDXGISwapChain1::GetHwnd() is an out-param call returning HRESULT,
		// not a property getter (C2660). A failed call leaves winHwnd null, which
		// FocusAllowsPresenting treats as "nothing to judge, change nothing".
		HWND winHwnd = nullptr;
		if (swapChain)
			swapChain->GetHwnd(&winHwnd);
		const bool winFocused = FocusAllowsPresenting(winHwnd);
		g_lastFocus.store(winFocused ? 1 : 0);
		// v0.76: publish the window so the watchdog can ask it whether it is still
		// answering messages. Stored every frame because the swap chain can be
		// recreated (resolution change, alt-enter) and a stale handle would make
		// the probe report "gone" for a window that is perfectly alive.
		g_probeHwnd.store(reinterpret_cast<std::uintptr_t>(winHwnd));
		{
			static bool focusWasOn = true;
			if (winFocused != focusWasOn) {
				focusWasOn = winFocused;
				g_bypassReported = false;   // v0.73: one BYPASS report per focus loss
				SKSE::log::warn("[XRAY] FOCUS {} hwnd={} foreground={} iconic={} - frame "
					"generation is bypassed and Present runs with DO_NOT_WAIT while the window "
					"cannot be shown", winFocused ? "regained" : "lost",
					static_cast<const void*>(winHwnd),
					static_cast<const void*>(::GetForegroundWindow()),
					winHwnd ? static_cast<int>(::IsIconic(winHwnd)) : -1);
			}
		}
		// v0.72: while the window cannot be shown, touch NOTHING that can block and
		// NOTHING that needs a present to finish. v0.71 tried to be clever here and it
		// made things worse (00:03 run: render thread stalled 2.6 s after the window lost
		// focus, watchdog wrote STALLED for 4.3 s while the process stayed alive):
		//
		//  * it fired slDLSSGSetOptions(mode = eOff) from inside Present - an unsupported
		//    mid-flight mode switch on a pacer that expects one evaluation per frame;
		//  * and it left a focusBlock that skipped slEvaluateDLSSG while the runtime was
		//    still eOn.
		//
		// The real hazard is the fence ping-pong below: every frame queues
		// d3d11 Signal -> d3d12 Wait -> d3d12 Signal -> d3d11 Wait. It assumes the D3D12
		// queue can always finish a frame, which is exactly what a window nobody can
		// present to breaks. So: no interop, no fences, no frame generation while
		// unfocused - one present that cannot wait, then out. This removes the deadlock
		// by construction rather than trying to out-run it.
		if (!winFocused) {
			m_stage = "unfocused bypass";
			// The only place DO_NOT_WAIT is correct: nothing downstream of this present
			// depends on the flip having happened, because nothing downstream exists.
			if (swapChain) {
				const HRESULT hrOff = swapChain->Present(0,
					Flags | static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT));
				// v0.73: no throw here. This runs inside the engine's own Present call
				// frame, which has no handler for our exceptions: throwing out of it ends
				// the process on the spot, with no crash log and no flushed log tail.
				// The worst case for this path is a frame that was not shown, so report
				// it once per focus loss and carry on.
				if (!g_bypassReported) {
					g_bypassReported = true;
					SKSE::log::warn("[XRAY] BYPASS present hr={:#x} ({}) flags={:#x}",
						static_cast<unsigned>(hrOff),
						hrOff == DXGI_ERROR_WAS_STILL_DRAWING
							? "buffer still in use, frame not shown" : "no flip pending",
						Flags);
				}
				// A flip may still have happened, so keep the buffer index honest for the
				// frame that resumes the normal path.
				frameIndex = swapChain->GetCurrentBackBufferIndex();
			}
			return S_OK;   // FrameStamp stamps lastFrameEndMs on the way out
		}

		// v0.56 probe: does the engine hand DXGI_PRESENT_ALLOW_TEARING to Present?
		// Present(0, ALLOW_TEARING) permits genuine tearing; the swap chain keeps the
		// flag only because Present(0) without it was rejected once (v0.38). Printed
		// only when the flag word changes, so it costs nothing per frame.
		{
			static UINT lastPresentFlags = 0xFFFFFFFFu;
			if (Flags != lastPresentFlags) {
				lastPresentFlags = Flags;
				SKSE::log::info("[FrameGen] Present called with SyncInterval={} Flags={:#x}{}", SyncInterval, Flags,
					(Flags & DXGI_PRESENT_ALLOW_TEARING) ? "  [ALLOW_TEARING - tearing permitted]" : "");
			}
		}

		// v0.3：DLSSG 模式 → 深度/运动矢量共享纹理惰性创建（CreateInterop 时引擎渲染目标
		// 可能还没建好——texture 为 null；首次 Present 时必然已就绪）
		// v0.5.6：引擎深度是 D32_FLOAT（mvec R16G16_FLOAT）——不在 DXGI NT 共享格式白名单
		// → CreateSharedHandle/OpenSharedHandle 抛 E_INVALIDARG（黑屏实锤 stage='enter'）。
		// 惰性创建包 try/catch：失败降级直通（无插帧但有画面），不抛异常穿透 Present。
		// v0.5.7（CS 方案）：depth 自建 R32_FLOAT（可共享），mvec 引擎格式原样（可共享）。
		// v0.6：FSR3 FG（Provider=0）也需要 depth/mvec 共享纹理 → 条件去掉 dlssgMode 限制
		if ((dlssgMode || FidelityFX::GetSingleton()->module) && (!depthWrapped || !mvecWrapped)) {
			static bool lazyFailLogged = false;
			try {
				if (auto* renderer = RE::BSGraphics::Renderer::GetSingleton()) {
					auto& main = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMAIN];
					auto& mvecTex = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
					if (!depthWrapped && main.texture) {
						D3D11_TEXTURE2D_DESC dDesc{};
						static_cast<ID3D11Texture2D*>(main.texture)->GetDesc(&dDesc);
						// v0.7.8：depth 共享纹理固定 = 输出分辨率（4K）——FSR3 FG 要求
						// depth 与 color 输入同尺寸；引擎 depth 是渲染尺寸（低），
						// CopyDepthToShared 采样放大到 4K
						dDesc.Width = swapChainDesc.Width;
						dDesc.Height = swapChainDesc.Height;
						dDesc.Format = DXGI_FORMAT_R32_FLOAT;
						dDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;
						depthWrapped = new WrappedResource(dDesc, d3d11Device.get(), d3d12Device.get());
						SKSE::log::info("[FrameGen] depth interop texture created lazily (R32_FLOAT {}x{})", dDesc.Width, dDesc.Height);
					}
					if (!mvecWrapped && mvecTex.texture) {
						D3D11_TEXTURE2D_DESC mDesc{};
						static_cast<ID3D11Texture2D*>(mvecTex.texture)->GetDesc(&mDesc);
						// v0.7.8：mvec 共享纹理固定 = 输出分辨率（4K）——FSR3 FG 要求与 color
						// 同尺寸；CopyMvecToShared 采样放大（引擎 mvec 是渲染尺寸）
						mDesc.Width = swapChainDesc.Width;
						mDesc.Height = swapChainDesc.Height;
						mDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;
						mvecWrapped = new WrappedResource(mDesc, d3d11Device.get(), d3d12Device.get());
						SKSE::log::info("[FrameGen] mvec interop texture created lazily ({}x{})", mDesc.Width, mDesc.Height);
					}
				}
				lazyFailLogged = false;
			} catch (const DX::com_exception& e) {
				if (!lazyFailLogged) {
					SKSE::log::warn("[FrameGen] depth/mvec interop lazy-create failed ({}), passthrough - no frame gen this run", e.what());
					lazyFailLogged = true;
				}
			}
		}

		// v0.3：DLSSG/FSR3 模式 → 先把引擎深度/运动矢量拷贝到共享纹理（D3D11 队列序，fence 前）
		// v0.5.7（CS 方案）：mvec 直接 CopyResource（格式兼容）；depth 必须 shader 拷贝——
		// 引擎 D32_FLOAT → R32_FLOAT 共享纹理，CopyResource 格式不匹配，用全屏三角形 PS 转换。
		// v0.6：FSR3 FG 同样需要 → 条件去掉 dlssgMode 限制
		// v0.7.8：depth/mvec 共享纹理固定 = 输出分辨率（4K，FSR3 FG 要求与 color 同尺寸），
		// 引擎 depth/mvec 是渲染尺寸（低）→ 都走 shader 采样放大（CopyResource 尺寸不匹配）
		if ((dlssgMode || FidelityFX::GetSingleton()->module) && depthWrapped && mvecWrapped) {
			if (auto* renderer = RE::BSGraphics::Renderer::GetSingleton()) {
				auto& depthTex = renderer->GetDepthStencilData().depthStencils[RE::RENDER_TARGETS_DEPTHSTENCIL::kMAIN];
				auto& mvecTex = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
				auto* depth11 = depthTex.texture ? static_cast<ID3D11Texture2D*>(depthTex.texture) : nullptr;
				auto* mvec11 = mvecTex.texture ? static_cast<ID3D11Texture2D*>(mvecTex.texture) : nullptr;
				if (mvec11 && mvecTex.SRV)
					CopyMvecToShared(mvecTex.SRV, mvecWrapped->rtv);
				if (depth11)
					CopyDepthToShared(depthTex.depthSRV, depthWrapped->rtv);
			}
		}

		// v0.48：DLSS 超分已迁到 Main_PostProcessing（ENB 前，见 FrameGen.cpp）。这里只做
		// 兜底拷贝：后缓冲（含 ENB + DLSS 超分结果）→ colorOut，供 DLSSNR + FG 消费。
		if (colorOutWrapped && swapChainBufferWrapped)
			d3d11Context->CopyResource(colorOutWrapped->resource11, swapChainBufferWrapped->resource11);

		// v0.69: NR x frame generation are mutually exclusive again.
		// v0.42 chained them on purpose and wrote the escape hatch into the same
		// comment (ImguiMenu.cpp:373): 若叠加闪烁再回退互斥. The 2026-09-17 23:07
		// run has both live at once -- INI NeuralRenderingEnabled=1 +
		// FrameGeneration=1, [DLSSNR] frames 179->359->539->719 (~50 full-res
		// NR evaluations per second), "D3D12 command contexts saturated", and
		// real fps 53->27 the instant FG engaged. Two temporal processors writing
		// history for the same frame is a direct flicker source: a static scene
		// hides it (both histories agree, which is why the main menu looked fine),
		// anything that moves exposes it (loading-screen model, world camera).
		// Suppress NR whenever frame generation is actually running. Press the
		// toggle key (0xC7) to turn FG off and NR comes straight back -- no second
		// switch, the same NeuralRenderingEnabled flag still governs it.
		// v1.21: the dlssgMode term is gone. With it, nrSuppressed could only ever
		// be true on the DLSSG path, so on Provider=0 (FSR3) NRAllowWithFrameGen=0
		// was silently ignored and DLSS5 NR stacked with FSR3 frame generation
		// regardless -- the 23:38 run's INI asked for no stacking, the log shows
		// "D3D12 command contexts saturated" plus a full-resolution NR pass on
		// every real frame, and the complaint was flicker, which is what two
		// temporal processors writing history for the same frame produce.
		// On the DLSSG path dlssgMode is already true, so removing the term leaves
		// this expression identical there.
		const bool fgGeneratingNow =
			fg.settings.frameGeneration && fg.fgActive.load();
		// ---- v1.01: NR may run IN SERIES with frame generation ----
		// The mutual exclusion above is now a SETTING (NRAllowWithFrameGen,
		// default 0 = unchanged). Rationale and evidence: see the header of
		// tools/patch_v101_nrserial_1.py.
		//
		// The v0.69 conclusion ("stacking is a flicker source") came from a run
		// that also had the v0.63 pacing defect (real fps 53->27 on FG engage)
		// and full-resolution NR (NRRenderScale=1.00, "D3D12 command contexts
		// saturated") live at the same time, so it is confounded and does not by
		// itself justify keeping the feature pair impossible.
		//
		// The ORDER is already right for chaining: with dlssgMode on, nrColor is
		// swapChainBufferWrapped->resource11 (line below), which is exactly the
		// resource EvaluateDLSSG consumes, and the fence at "d3d11 Signal(fence)"
		// orders NR's write before DLSS-G's read. NR runs first, DLSS-G
		// interpolates the neural-rendered frame.
		const bool nrSuppressed = fgGeneratingNow && !fg.settings.nrAllowWithFrameGen;
		if (fg.settings.neuralRenderingEnabled && nrSuppressed) {
			static bool nrStackLogged = false;
			if (!nrStackLogged) {
				nrStackLogged = true;
				SKSE::log::warn("[FrameGen] DLSSNR suppressed: frame generation is active - "
					"NR and DLSS-G are two temporal processors and stacking them is a "
					"direct flicker source (v0.42 note: revert to mutual exclusion if "
					"it flickers). Set NRAllowWithFrameGen=1 to chain them instead "
					"(v1.01), or press the toggle key to disable FG and NR resumes.");
			}
		} else if (fg.settings.neuralRenderingEnabled && fgGeneratingNow) {
			static bool nrChainLogged = false;
			if (!nrChainLogged) {
				nrChainLogged = true;
				SKSE::log::info("[FrameGen] DLSSNR CHAINED with frame generation (v1.01, "
					"NRAllowWithFrameGen=1): NR runs first on the real frame, DLSS-G then "
					"interpolates the neural-rendered result.");
			}
		}
		// v0.46b：回退到 colorOut 输入（DLSS 超分结果，1440p）——上一版 kMAIN subrect
		// 方案在 DRS 失效时（kMAIN 恒 2560x1440，见 Upscale diag）取到的是画面左上角
		// 裁剪，DLSS5 错位无效 + 超级性能冻结。DRS 失效是根因（kMAIN 不降到渲染分辨率），
		// 需单独攻；此处先恢复 colorOut 全分辨率稳定态（DLSS5 有效果）。
		if (fg.settings.neuralRenderingEnabled && !nrSuppressed) {
			ID3D11Resource* nrColor = !dlssgMode
				? (colorOutWrapped ? colorOutWrapped->resource11 : nullptr)
				: (swapChainBufferWrapped ? swapChainBufferWrapped->resource11 : nullptr);
			if (nrColor) {
				if (auto* nrRenderer = RE::BSGraphics::Renderer::GetSingleton()) {
					auto& nrDepth = nrRenderer->GetDepthStencilData().depthStencils[RE::RENDER_TARGETS_DEPTHSTENCIL::kMAIN];
					auto& nrMvec = nrRenderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
					// v0.52（诚实上报）：原诊断打的是**引擎原生** kMAIN depth / kMOTION_VECTOR，
					// 而 Apply() 实际吃的是 depthWrapped/mvecWrapped（采样放大到输出分辨率的那份）
					// ——不是同一个对象，所以原来那条日志无论 NR 有没有跑都显示 true，无法证伪。
					// 现在打真正决定执行的门禁 + NGX 成功帧计数：
					//   inputs = Apply 的输入是否就绪（false = NR 每帧被静默跳过）
					//   frames = 成功评估帧数（0 = 从没跑起来，例如特性/内核不可用）
					const bool nrInputsReady = depthWrapped && mvecWrapped && depthWrapped->srv;
					static std::uint32_t nrDiag = 0;
					if (++nrDiag % 180 == 1) {
						SKSE::log::info("[FrameGen] DLSSNR: color={} engineDepthSRV={} engineMvec={} inputs={} frames={} status={}",
							nrColor != nullptr, nrDepth.depthSRV != nullptr, nrMvec.texture != nullptr, nrInputsReady,
							static_cast<unsigned long long>(NeuralRendering::Renderer::Instance().SuccessfulFrames()),
							NeuralRendering::Renderer::Instance().StatusText());
					}
					static std::uint32_t nrSkip = 0;
					if (!nrInputsReady && ++nrSkip % 300 == 1)
						SKSE::log::warn("[FrameGen] DLSSNR skipped: shared depth/mvec not ready (depthWrapped={} mvecWrapped={} srv={})",
							depthWrapped != nullptr, mvecWrapped != nullptr,
							depthWrapped != nullptr && depthWrapped->srv != nullptr);
					// v0.49j（修重影+光影根因）：DLSSNR 的 depth/mvec 必须与 color(2560 超分后)
					// 对齐。引擎原始 depth/mvec 是 DRS 渲染分辨率(1706)内容（在 2560 纹理左上角），
					// 与 color(2560 全屏)不对齐 → temporal 错乱 → 重影 + 光影不对。改用已 upscale
					// 到 2560 的 depthWrapped/mvecWrapped（CopyDepthToShared/CopyMvecToShared 采样
					// 放大 1706→2560），DLSSNR 1:1（guide=2560）与 colorOut 对齐。
					if (depthWrapped && mvecWrapped && depthWrapped->srv) {
						D3D11_TEXTURE2D_DESC nrCd{};
						static_cast<ID3D11Texture2D*>(nrColor)->GetDesc(&nrCd);
						NeuralRendering::Renderer::Instance().Apply(
							d3d11Device.get(), d3d11Context.get(),
							nrColor, depthWrapped->resource11, depthWrapped->srv, mvecWrapped->resource11, nrColor,
							nrCd.Width, nrCd.Height, nrCd.Width, nrCd.Height,
							static_cast<float>(nrCd.Width), static_cast<float>(nrCd.Height), fg.nrTuning);
					}
				}
			}
		}

		// v0.24.1：游戏内菜单/FPS overlay 绘制——必须在 fence 之前（D3D11 写 colorOut 完成
		// 后随 Signal/Wait 同步，D3D12 拷贝才能稳定读到）。v0.24 把 Draw 放在 fence 之后
		// （原菜单位置）导致 D3D11 写与 D3D12 CopyResource 跨 API 竞争 → FPS/UI 闪烁。
		// v0.30（菜单打不开修复）：去掉 !dlssgMode——DLSSG 模式此前不绘制 ImGui 菜单
		// （Toggle 生效但 Draw 被跳过 → "菜单按不出来"，用户 20:12 实锤）。菜单画在
		// swapChainBufferWrapped（dlssgMode 时 colorOut 为 null 自动回退），随后直通拷贝
		// 上屏。插帧启用时菜单会进 DLSSG 输入（UI 分离未接线，可能轻微模糊——后续优化）。
		if ((ImguiMenu::GetSingleton()->visible || Get().settings.fpsOverlay))
			ImguiMenu::GetSingleton()->Draw(Get());

		// v0.6：FSR3 FG（Provider=0，dlssgMode=false）——每帧 Configure + Dispatch
		// （doodlum/ENBFrameGeneration 移植；depth/mvec 共享纹理在 dlssgMode=false 时
		// 由下面的 FSR3 拷贝块填充——先拷贝后 FG）
		if (!dlssgMode && FidelityFX::GetSingleton()->module) {
			FidelityFX::GetSingleton()->Present(fg.fgActive.load());
		}

		// v0.75: the cycle breaker.
		//
		// This used to be:
		//     d3d11Context->Signal(d3d11Fence, v);
		//     commandQueue->Wait(d3d12Fence, v);        // <-- D3D12 waits on D3D11
		// while the end of the same frame asks the other direction
		//     d3d11Context->Wait(d3d11Fence, v);        // <-- D3D11 waits on D3D12
		//
		// CORRECTION, and it matters. I first wrote here that doodlum's
		// ENBFrameGeneration "uses the same fix". It does NOT - checked in
		// D:/Modding/ENBFrameGeneration-src/src/DX12SwapChain.cpp:127-128 and
		// 167-168, the reference keeps this exact two-way wait and works fine.
		// So the crossing shape is NOT inherently deadlocking and no upstream
		// implementation endorses removing it. Treat the change below as a
		// hypothesis to be refuted, not as a port from a working reference.
		//
		// What is actually known (07:11 run, watchdog segment #10): fence held its
		// initial value 1 for 50 s while frames reached 1614 and silent stayed at
		// 5-27 ms. fenceValue 1 is what CreateInterop sets once, so zero Signals
		// ever completed on the GPU while the CPU kept finishing frames. This
		// chain is the only place where the two engine queues wait on each other,
		// which makes it the first suspect - that is the whole argument.
		//
		// Set back to true to restore the old behaviour exactly, for comparison.
		// v1.21: the withdrawal is a SETTING rather than a constant now, so the
		// two behaviours can be compared without a rebuild and a run that wedges
		// on it is reverted by editing one INI line. What the withdrawal costs
		// is written up in FrameGen.h next to InteropFenceWait.
		const bool kD3D12WaitsOnD3D11 = Get().settings.interopFenceWait;
		if (kD3D12WaitsOnD3D11) {
			m_stage = "d3d11 Signal(fence)";
			DX::ThrowIfFailed(d3d11Context->Signal(d3d11Fence.get(), fenceValue));
			m_stage = "d3d12 queue Wait";
			DX::ThrowIfFailed(commandQueue->Wait(d3d12Fence.get(), fenceValue));
		}
		// fenceValue is still advanced once per frame: the D3D12 side Signals it
		// after Present, and the D3D11 side waits on it. Only the D3D12->D3D11
		// wait is withdrawn.
		fenceValue++;

		// 新帧，重置命令列表
		m_stage = "allocator Reset";
		// v0.75: bounded allocator guard. Reset() on an allocator whose work is
		// still in flight is undefined behaviour, so check instead of assuming -
		// but bound the wait. An unbounded wait here would be the v0.71 mistake
		// again (it traded one hang for another); a bounded one can only convert a
		// silent freeze into a log line and then carry on.
		{
			const UINT64 completed = d3d12Fence
				? static_cast<UINT64>(d3d12Fence->GetCompletedValue()) : 0;
			// fenceValue N is Signalled at the end of every frame, so the last
			// value known to be complete is fenceValue-2 (fenceValue-1 is in flight).
			const UINT64 need = (fenceValue > 2) ? (fenceValue - 2) : 0;
			if (need > completed && d3d12Fence) {
				static bool reported = false;
				HANDLE h = ::CreateEventA(nullptr, FALSE, FALSE, nullptr);
				if (h && d3d12Fence->SetEventOnCompletion(need, h) == S_OK) {
					const DWORD w = ::WaitForSingleObject(h, 50);
					if (w != WAIT_OBJECT_0 && !reported) {
						reported = true;
						SKSE::log::warn("[XRAY] GPU behind at allocator Reset: have {} need {} "
							"(waited 50 ms) - frame {} . If this repeats every frame the D3D12 "
							"queue is wedged.", completed, need, frameIndex);
					}
				}
				if (h) ::CloseHandle(h);
			}
		}
		DX::ThrowIfFailed(commandAllocators[frameIndex]->Reset());
		m_stage = "cmdlist Reset";
		DX::ThrowIfFailed(commandLists[frameIndex]->Reset(commandAllocators[frameIndex].get(), nullptr));

		// v0.3：DLSSG 模式——NVIDIA 插帧（输入=游戏画面共享纹理，输出=D3D12 backbuffer）
		if (dlssgMode) {
			// v0.37（对齐 open-shaders EnsureFrameToken）：帧开头统一获取本帧 token——
			// ReflexSleep/PCL marker/EvaluateDLSSG 全部用同一 token（之前 ReflexSleep
			// 用旧 token、EvaluateDLSSG 才取新 → 同帧 marker 跨 token → RSYNC 错位）。
			// v0.58: the single per-frame advance point. Drives both the
			// new-frame test in EnsureFrameToken and the frame index handed to
			// slGetNewFrameToken. Must run before any SL call of this frame.
			++fg.streamline.frameSerial;
			fg.streamline.EnsureFrameToken();
			// v0.32（对齐 open-shaders Streamline.cpp:890-924）：Reflex sleep 先于
			// PCL marker——RSYNC（vblank 同步 pacing）建立的必需输入。slReflexSleep
			// 内部会休眠到 Reflex 指定的时刻（低延迟），返回后发 eSimulationStart。
			// 缺失 → sl.reflex 无 hooks → RSYNC 无同步 → 插帧 pacing 乱 → 频闪。
			fg.streamline.ReflexSleep();
			// v0.31（对齐 open-shaders DX12SwapChain.cpp:365-403）：PCL 完整序列——
			// eSimulationEnd → eRenderSubmitStart 在帧开始发（RSYNC 节奏建立，
			// 缺失 → pacing 乱 → 频闪）。eRenderSubmitEnd 在 ExecuteCommandLists
			// 后、ePresentStart 前（774 行后）。
			fg.streamline.PresentMarkerSimulationEnd();
			fg.streamline.PresentMarkerRenderStart();

			// v0.70: sample the menu state ONCE PER FRAME, here, BEFORE the guard
			// below consumes it. The guard skips EvaluateDLSSG, and the sample used
			// to be taken inside EvaluateDLSSG - so on every frame the guard engaged,
			// menuFrames / menuEdges / the reset edge stayed frozen and the guard was
			// unverifiable (menu=0 in the heartbeat could not be told apart from
			// "the guard never ran").
			fg.streamline.PollMenuState();
			const bool fgOn = fg.fgActive.load();  // Home 键开关
			bool dlssgOk = false;
			// 防刷屏：连续失败计数。v0.66：Transfusion 侧实测两个 tid 都在调
			// slSetConstants，「Present 渲染线程单线程」的旧假设不成立
			// ⇒ 改原子，消除多线程 ++ 的数据竞争。
			static std::atomic<int> dlssgFailCount{ 0 };
			// v0.63：菜单期间不插帧 —— DLSSGFlags::eEnableFullScreenMenuDetection 的
			// 插件侧替代实现（那个 flag 到不了运行时，见 Streamline::MenuOpenNow）。
			// 菜单是 2D UI，被当 3D 内容插值就是"主菜单画面持续闪"的直接来源。
			// 走下面已有的直通拷回路径（backbuffer = 真实帧），用户 Home 开关意图不变。
			const bool menuBlock =
				fgOn && fg.settings.menuDisableFrameGen && fg.streamline.MenuIsOpen();
			// v0.72: no focus term here any more. An unfocused window never reaches this
			// point - it returns from the dependency-free bypass near the top of Present,
			// before any fence traffic.
			// v0.79 -- ladder runs BEFORE the menu guard.
			// It used to live inside SetDLSSGOptions, which only runs in the else-if
			// below, so a REJECTED multiplier could never step down while a menu was up
			// and the ladder stayed pinned for the whole menu (08:59 run: 18.08 s of
			// menu, generation 0, accept finally logged only at 08:59:49.097 - after the
			// menu). The probe needs the menu time to calibrate: on the frame the world
			// is entered it is already latched at the accepted multiplier.
			if (fgOn && fg.streamline.featureDLSSG) {
				menuBlockedFrames += menuBlock ? 1u : 0u;
				menuUnblockedFrames += menuBlock ? 0u : 1u;
				// v1.03: the governor gates the probe, so a stalled runtime stops
				// being re-armed. It reads the interval of the frame that just
				// elapsed (capUs is already maintained per real frame for Reflex).
				// v1.03: the governor gates the probe, so a stalled runtime stops
				// being re-armed. It measures the interval between successive
				// entries into this function - wall clock, one sample per real
				// frame, which is exactly what "the frame took 19945 ms" means in
				// the XRAY line and what the watchdog's silent= field measures.
				// (diag.reflexCapUs is the limiter's TARGET, not the elapsed time,
				// so it cannot answer this question - and reading a target as a
				// measurement is how a diagnostic starts lying.)
				static std::atomic<long long> lastProbeEntryMs{ 0 };
				const long long nowProbeMs = std::chrono::duration_cast<std::chrono::milliseconds>(
					std::chrono::steady_clock::now().time_since_epoch()).count();
				const long long prevProbeMs = lastProbeEntryMs.exchange(nowProbeMs);
				const std::uint32_t probeFrameUs = (prevProbeMs > 0 && nowProbeMs > prevProbeMs)
					? static_cast<std::uint32_t>(std::min<long long>((nowProbeMs - prevProbeMs) * 1000, 0xFFFFFFFF))
					: 0u;
				if (fg.streamline.MfgStallGovAllow(probeFrameUs)) {
					fg.streamline.ProbeMfgLadder();
				}
				fg.streamline.ProbeMfgLadderNote(menuBlock);
			} else if (fgOn && menuBlock && (++mfgWarned % 600u) == 1u) {
				SKSE::log::warn("[MFG] menu guard is blocking frame gen ({} frames) but featureDLSSG is "
					"false - the ladder cannot be calibrated (feature not loaded this session)", menuBlockedFrames);
			}
			if (menuBlock) {
				// 这是**主动直通**，不是失败。必须清零计数器，否则在菜单里待满 ~2s
				// 就会撞上 dlssgFailCount>120 把插帧整个自动关掉（Home 也救不回）。
				dlssgFailCount = 0;
			} else if (fgOn && fg.streamline.featureDLSSG && fg.GetFrameBuffer()) {
				auto* cmdList = commandLists[frameIndex].get();
				m_stage = "dlssg SetDLSSGOptions";
				fg.streamline.SetDLSSGOptions(swapChainDesc.Width, swapChainDesc.Height,
					swapChainDesc.Width, swapChainDesc.Height, swapChainDesc.Format);
				m_stage = "dlssg EvaluateDLSSG";
				dlssgOk = fg.streamline.EvaluateDLSSG(cmdList,
					swapChainBufferWrapped->resource.get(),
					swapChainBuffers[frameIndex].get(),
					depthWrapped ? depthWrapped->resource.get() : nullptr,
					mvecWrapped ? mvecWrapped->resource.get() : nullptr,
					*fg.GetFrameBuffer());
			}
			// v0.79 -- same pass/fail predicate the auto-disable block uses below,
			// so the number cannot drift from it: a menu frame deliberately skips
			// SetDLSSGOptions/EvaluateDLSSG and resets the failure counter.
			const bool debugOk = dlssgOk || menuBlock;
			if (!debugOk && fgOn && fg.streamline.featureDLSSG) {
				if ((++mfgWarned % 600u) == 1u) {
					// v1.28: the old text printed `menuBlock=0` as a literal and labelled the
					// next argument `frames=`, but that argument is debugOk, not a frame
					// count -- the line named a quantity it was not printing. This branch is
					// only reachable with menuBlock false, so debugOk here IS dlssgOk.
					SKSE::log::warn("[MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu "
						"guard is not engaged (dlssgOk={} blocked={} unblocked={}) - the ladder "
						"cannot be calibrated while this lasts",
						debugOk ? 1u : 0u, menuBlockedFrames, menuUnblockedFrames);
				}
			}
			if (dlssgOk) {
				dlssgFailCount = 0;
			} else {
				// v0.5：仅开启状态计数失败（Home 手动关闭时清零，不误报"自动禁用"）
				if (fgOn) {
					if (++dlssgFailCount > 120) {  // ~2s 持续失败 → 自动关闭插帧（Home 可重开）
						fg.fgActive.store(false);
						dlssgFailCount = 0;
						SKSE::log::warn("[FrameGen] DLSSG failing repeatedly - frame generation auto-disabled (press toggle key to retry)");
					}
				} else {
					dlssgFailCount = 0;
				}
				// 直通兜底：共享纹理 Copy 到 backbuffer（无插帧，防画面冻结）
				auto fakeSwapChain = swapChainBufferWrapped->resource.get();
				auto realSwapChain = swapChainBuffers[frameIndex].get();
				{
					std::vector<D3D12_RESOURCE_BARRIER> barriers;
					barriers.push_back(CD3DX12_RESOURCE_BARRIER::Transition(fakeSwapChain, D3D12_RESOURCE_STATE_COMMON, D3D12_RESOURCE_STATE_COPY_SOURCE));
					barriers.push_back(CD3DX12_RESOURCE_BARRIER::Transition(realSwapChain, D3D12_RESOURCE_STATE_PRESENT, D3D12_RESOURCE_STATE_COPY_DEST));
					commandLists[frameIndex]->ResourceBarrier(static_cast<UINT>(barriers.size()), barriers.data());
				}
				commandLists[frameIndex]->CopyResource(realSwapChain, fakeSwapChain);
				{
					std::vector<D3D12_RESOURCE_BARRIER> barriers;
					barriers.push_back(CD3DX12_RESOURCE_BARRIER::Transition(fakeSwapChain, D3D12_RESOURCE_STATE_COPY_SOURCE, D3D12_RESOURCE_STATE_COMMON));
					barriers.push_back(CD3DX12_RESOURCE_BARRIER::Transition(realSwapChain, D3D12_RESOURCE_STATE_COPY_DEST, D3D12_RESOURCE_STATE_PRESENT));
					commandLists[frameIndex]->ResourceBarrier(static_cast<UINT>(barriers.size()), barriers.data());
				}
			}
			// v0.31b（频闪诊断）：节流打印 DLSSG 运行状态——帧号推进（token 变化）、
			// dlssgOk 是否稳定、失败计数。不依赖 SL_LogLevel（SL SDK 日志常被关闭）。
			// 帧号停滞 → token 不变/每 120 帧相同；插帧交替 → dlssgOk 振荡。
			{
				static std::atomic<int> dlssgDiag{ 0 };
				if (++dlssgDiag % 120 == 0) {
					SKSE::log::info("[FrameGen] DLSSG diag: fgOn={} dlssgOk={} token={:p} fail={}",
						fgOn, dlssgOk, static_cast<const void*>(fg.streamline.frameToken),
						dlssgFailCount.load());  // v0.66: atomic - fmt 不能直接格式化
				}
			}
			DX::ThrowIfFailed(commandLists[frameIndex]->Close());
			ID3D12CommandList* dlssgLists[] = { commandLists[frameIndex].get() };
			commandQueue->ExecuteCommandLists(1, dlssgLists);
			g_queuedDepth.fetch_add(1);   // v0.74: submitted, not yet fence-complete
			m_stage = "d3d12 Present(dlssg)";
			// v0.5.22：DLSSG 强制 VSync（SyncInterval=1）——dlss_g 的 RSYNC（vblank 同步器）
			// 强依赖 VSync 建立（日志 "VSync with FG: supported"）；VSync 关 → RSYNC 未初始化
			// → Allocate 时 RSYNC 实例 null → 0xC0000005（SkyrimUpscaler 教程早期版本
			// 同样要求 EnableVsync=true）
			// v0.5.23：Present 前后 PCL marker（RSYNC 节奏建立的必需输入）
			// v0.31：eRenderSubmitEnd 补在 ePresentStart 前（对齐 CS 完整序列）
			// v0.34：Present 透传 SyncInterval（对齐 CS）——但实测（21:00 日志）：
			// Present(1)（VSync on）+ SL 插帧 = 双重节流 → SL flip 队列每帧堵 30ms
			// （"throttleFlipQueue: no flip-queue slot freed within 30 ms" 每帧刷屏）
			// → 帧率压到 ~33fps → 画面卡顿抖动（用户"闪的厉害"）。
			// v0.36：**DLSSG 强制 Present(0)**——SL pacer 全权管理 pacing/VSync
			//（CS FrameLimiter 注释 "The SL pacer owns presentation when DLSS-G is
			// active"；RSYNC 在内部处理 vblank 同步），宿主不再等 vblank 双重节流。
			fg.streamline.PresentMarkerRenderEnd();
			Get().streamline.PresentMarkerStart();
			// v0.71: never block in Present. SwapEffect=FLIP_DISCARD with BufferCount=3
			// makes Present wait for a queued buffer to be released, and DXGI stops
			// releasing buffers for a window that is occluded or in the background.
			// DO_NOT_WAIT turns that wait into DXGI_ERROR_WAS_STILL_DRAWING, which is the
			// honest outcome for a frame nobody can see - and the difference between one
			// dropped frame and a frozen game.
			// v0.72: plain blocking Present again. With FLIP_DISCARD + 3 buffers this call
			// is what bounds how far the CPU may run ahead of the GPU - and the next thing
			// this function does is reset a command allocator. DO_NOT_WAIT (v0.71) removed
			// that bound; the unfocused case never reaches here any more.
			// v1.04b: stamp the entry so a watchdog tick that lands inside this call
			// can say so. This is the only call between "d3d11 Wait" being written
			// and the next frame's "present entry", so before this change it was
			// invisible: the 19:04 run blamed the fence wait for 19.7 s of stall
			// that belonged here.
			g_presentEnteredMs.store(static_cast<long long>(std::chrono::duration_cast<std::chrono::milliseconds>(
				std::chrono::steady_clock::now().time_since_epoch()).count()));
			const HRESULT hrPresent = swapChain->Present(0, Flags);
			if (hrPresent != DXGI_ERROR_WAS_STILL_DRAWING)
				DX::ThrowIfFailed(hrPresent);
			// v0.74: Present returning S_OK does not mean the screen changed.
			// Under FLIP_DISCARD with no new content DXGI returns success and
			// shows the same buffer, which is exactly how a stalled GPU queue
			// stays invisible: the frame still "presented". Record the counter
			// DXGI keeps for us and whether our index still agrees with its own.
			{
				UINT pc = 0;
				if (SUCCEEDED(swapChain->GetLastPresentCount(&pc)))
					g_lastPresentCount.store(pc);
				// v0.76 FIX: the comparison below was inverted. Present() advances
				// the DXGI back-buffer index by construction on a successful flip,
				// so comparing the post-Present index against the pre-Present
				// frameIndex reported 1 for every *healthy* frame -- the 07:23 run
				// (291/291) read as a total desync while it was in fact flipping
				// perfectly. The state worth reporting is the opposite one: the
				// index did not move, i.e. Present returned success without a flip.
				const UINT real = swapChain->GetCurrentBackBufferIndex();
				g_flipDesync.store(real == frameIndex ? 1ull : 0ull);
			}
			Get().streamline.PresentMarkerEnd();
			m_stage = "d3d12 queue Signal";
			DX::ThrowIfFailed(commandQueue->Signal(d3d12Fence.get(), fenceValue));
			m_stage = "d3d11 Wait";
			// v1.03b: bounded (was ID3D11DeviceContext4::Wait, which cannot time
			// out). The watchdog only ever saw this stage name; on 2026-09-18
			// 18:23 that line sat unchanged for 19681 ms on the FIRST real frame
			// (frames=1), which is the freeze.
			if (!WaitFenceBounded(fenceValue, kFenceWaitTimeoutMs))
				m_stage = "d3d11 Wait TIMEOUT";
			fenceValue++;
			frameIndex = swapChain->GetCurrentBackBufferIndex();
			return S_OK;
		}

		// v0.25：DLSS-NR Evaluate 段已移除（NR 改由外部 ReShade 方案提供）——
		// 拷贝源恒为 colorOut（DLSS 超分结果，失败时 = 引擎画面兜底）
		const bool useNr = false;

		// v0.5：FSR3 超分评估已移到 fence 前（D3D11 队列序正确）
		// v0.7.17：拷贝源 = colorOut（DLSS 超分结果 4K；失败时 = 引擎画面兜底）
		// D3D11 共享纹理 → D3D12 真 swapchain buffer
		{
			auto fakeSwapChain = (useNr && nrOutWrapped ? nrOutWrapped :
				(colorOutWrapped ? colorOutWrapped : swapChainBufferWrapped))->resource.get();
			auto realSwapChain = swapChainBuffers[frameIndex].get();
			{
				std::vector<D3D12_RESOURCE_BARRIER> barriers;
				barriers.push_back(CD3DX12_RESOURCE_BARRIER::Transition(fakeSwapChain, D3D12_RESOURCE_STATE_COMMON, D3D12_RESOURCE_STATE_COPY_SOURCE));
				barriers.push_back(CD3DX12_RESOURCE_BARRIER::Transition(realSwapChain, D3D12_RESOURCE_STATE_PRESENT, D3D12_RESOURCE_STATE_COPY_DEST));
				commandLists[frameIndex]->ResourceBarrier(static_cast<UINT>(barriers.size()), barriers.data());
			}

			commandLists[frameIndex]->CopyResource(realSwapChain, fakeSwapChain);

			{
				std::vector<D3D12_RESOURCE_BARRIER> barriers;
				barriers.push_back(CD3DX12_RESOURCE_BARRIER::Transition(fakeSwapChain, D3D12_RESOURCE_STATE_COPY_SOURCE, D3D12_RESOURCE_STATE_COMMON));
				barriers.push_back(CD3DX12_RESOURCE_BARRIER::Transition(realSwapChain, D3D12_RESOURCE_STATE_COPY_DEST, D3D12_RESOURCE_STATE_PRESENT));
				commandLists[frameIndex]->ResourceBarrier(static_cast<UINT>(barriers.size()), barriers.data());
			}
		}

		DX::ThrowIfFailed(commandLists[frameIndex]->Close());

		ID3D12CommandList* commandListsToExecute[] = { commandLists[frameIndex].get() };
		commandQueue->ExecuteCommandLists(1, commandListsToExecute);
		g_queuedDepth.fetch_add(1);   // v0.74: submitted, not yet fence-complete

		// 呈现
		m_stage = "d3d12 Present";
		// v0.5.22：DLSSG 强制 VSync（同 dlssg 分支，RSYNC 依赖）
		// v0.5.23：PCL marker
		Get().streamline.PresentMarkerStart();
		// v0.71: same guard as the DLSSG branch - an unfocused window must not be able
		// to block the render thread inside Present.
		// v0.72: same as the DLSSG branch - the unfocused path returns above, so this
		// stays a plain blocking present.
		g_presentEnteredMs.store(static_cast<long long>(std::chrono::duration_cast<std::chrono::milliseconds>(
			std::chrono::steady_clock::now().time_since_epoch()).count()));
		const HRESULT hrPresentFsr = swapChain->Present(1, Flags);
		if (hrPresentFsr != DXGI_ERROR_WAS_STILL_DRAWING)
			DX::ThrowIfFailed(hrPresentFsr);
		// v1.26: the DLSS-G branch has recorded GetLastPresentCount since v0.74; this
		// branch never did, so on FSR3 -- the only provider any run has stayed alive
		// on -- the one measurement that does not depend on the runtime's own report
		// was unavailable.
		{
			UINT pc = 0;
			if (SUCCEEDED(swapChain->GetLastPresentCount(&pc)))
				g_lastPresentCount.store(pc);
		}
		Get().streamline.PresentMarkerEnd();

		// 等 D3D12 完成
		m_stage = "d3d12 queue Signal";
		DX::ThrowIfFailed(commandQueue->Signal(d3d12Fence.get(), fenceValue));
		m_stage = "d3d11 Wait";
		// v1.03b: bounded, same as the menu-block path above. Both sites wrote
		// the "d3d11 Wait" the watchdog reported for 19.7 s while the process
		// had presented exactly one frame.
		if (!WaitFenceBounded(fenceValue, kFenceWaitTimeoutMs))
			m_stage = "d3d11 Wait TIMEOUT";
		fenceValue++;

		frameIndex = swapChain->GetCurrentBackBufferIndex();

		return S_OK;
	}

	// ---- v1.22 PIXEL PROBE ----
	// L38: "the counter is climbing" and "the content is changing" are two
	// different facts and each needs its own witness. The 00:30 run has the first
	// in abundance -- 4.00 presents per real frame, dsync = 0 (the back-buffer
	// index really moved), presentAge 5-8 ms -- and no witness at all for the
	// second, which is why a frozen screen and a healthy one produced the same
	// log. A flip is not a picture. This reads the pixels the plugin is about to
	// hand to the swap chain and reports whether they change.
	//
	// Read-only and self-disabling: creation is attempted once, and a failure
	// disables it permanently with one log line. The Map uses DO_NOT_WAIT, so a
	// sample that is not ready is dropped instead of stalling the render thread:
	// the probe can cost a frame's latency, never the frame itself.
		void DX12SwapChain::PixelProbeTick()
	{
		if (pixelProbeDisabled)
			return;

		auto& fg = Get();
		if (!fg.settings.pixelProbe) {
			pixelProbeDisabled = true;
			SKSE::log::info("[PIXEL] probe disabled by INI (PixelProbe=0)");
			return;
		}

		// v1.23 -- TWO-PHASE SAMPLING. This is a bug fix, not a refinement.
		//
		// v1.22 copied with CopySubresourceRegion and then, in the SAME call, asked
		// Map for the staging texture it had just filled. The GPU has not executed
		// that copy yet, so the Map returned DXGI_ERROR_WAS_STILL_DRAWING every
		// single time -- and that path also reset the 1 Hz gate, so the retry
		// happened on EVERY present. Net effect on the 00:58 run: "probe armed" at
		// 00:58:14.810 and not one sample afterwards in 39 s, while a cross-API
		// copy ran inside every frame. The question the probe exists to answer was
		// therefore never measured.
		//
		// Now: harvest what the PREVIOUS tick copied (a full second to land), then
		// issue the next copy. A sample that is still not ready is dropped and
		// counted, never retried inside the same second.
		const auto nowMs = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
			std::chrono::steady_clock::now().time_since_epoch()).count());
		// v1.24: 1 Hz could not reach the verdict threshold in the windows we actually
		// get (three runs ended 2.5/6.1/2.6 s after the guard released). 2 Hz keeps the
		// copy DO_NOT_WAIT and dropped-not-retried, so a tighter interval can only
		// cost samples, never stall the render thread.
		if (pixelProbeLastMs != 0 && nowMs - pixelProbeLastMs < 500)
			return;
		pixelProbeLastMs = nowMs;

		// Which buffer is the picture the player sees? With DLSS-G on, Streamline
		// presents colorOutWrapped, not the engine backbuffer (that one is the
		// HUD-less colour INPUT). Sampling the wrong one would report "a new frame
		// was rendered" while the screen stayed on the same image.
		WrappedResource* srcRes = colorOutWrapped ? colorOutWrapped : swapChainBufferWrapped;
		if (!srcRes || !srcRes->resource11)
			srcRes = swapChainBufferWrapped;

		if (!pixelProbeReady) {
			if (!srcRes || !srcRes->resource11 || !d3d11Device || !d3d11Context) {
				pixelProbeDisabled = true;
				SKSE::log::warn("[PIXEL] probe disabled: the source texture is not up yet on this path");
				return;
			}
			D3D11_TEXTURE2D_DESC src{};
			srcRes->resource11->GetDesc(&src);

			// Centre of the frame: that is where the world is. A corner block would
			// sit on sky or HUD and could be genuinely constant while the world moves.
			const UINT bw = src.Width < 64u ? src.Width : 64u;
			const UINT bh = src.Height < 64u ? src.Height : 64u;
			pixelProbeBox.left = (src.Width - bw) / 2;
			pixelProbeBox.top = (src.Height - bh) / 2;
			pixelProbeBox.front = 0;
			pixelProbeBox.right = pixelProbeBox.left + bw;
			pixelProbeBox.bottom = pixelProbeBox.top + bh;
			pixelProbeBox.back = 1;

			D3D11_TEXTURE2D_DESC st{};
			st.Width = bw;
			st.Height = bh;
			st.MipLevels = 1;
			st.ArraySize = 1;
			st.Format = src.Format;
			st.SampleDesc = src.SampleDesc;
			st.Usage = D3D11_USAGE_STAGING;
			st.BindFlags = 0;
			st.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
			st.MiscFlags = 0;

			const HRESULT hrCreate = d3d11Device->CreateTexture2D(&st, nullptr, pixelProbeStaging.put());
			if (FAILED(hrCreate)) {
				pixelProbeDisabled = true;
				SKSE::log::warn("[PIXEL] probe disabled: CreateTexture2D failed hr=0x{:08X}", static_cast<unsigned>(hrCreate));
				return;
			}
			pixelProbeWidth = bw;
			pixelProbeHeight = bh;
			pixelProbeSrcW = src.Width;
			pixelProbeSrcH = src.Height;
			pixelProbeArmedMs = nowMs;
			pixelProbeReady = true;
			pixelProbeCopyPending = false;
			SKSE::log::info("[PIXEL] probe armed: src={}x{} fmt={} block={}x{} at ({},{}) source={}",
				src.Width, src.Height, static_cast<int>(src.Format), bw, bh,
				pixelProbeBox.left, pixelProbeBox.top,
				(colorOutWrapped && srcRes == colorOutWrapped) ? "colorOut(presented)" : "engineBackbuffer");
		}
		else if (srcRes && srcRes->resource11 && pixelProbeSrcW != 0) {
			// The presented resource changed size: the cached box would then read the
			// wrong region, so re-arm instead of reporting noise as content.
			D3D11_TEXTURE2D_DESC cur{};
			srcRes->resource11->GetDesc(&cur);
			if (cur.Width != pixelProbeSrcW || cur.Height != pixelProbeSrcH) {
				pixelProbeReady = false;
				SKSE::log::warn("[PIXEL] presented image resized to {}x{} - rearming the probe", cur.Width, cur.Height);
				return;
			}
		}

		// ---- phase 2: harvest what the PREVIOUS tick copied ----
		if (pixelProbeCopyPending) {
			D3D11_MAPPED_SUBRESOURCE ms{};
			const HRESULT hrMap = d3d11Context->Map(
				pixelProbeStaging.get(), 0, D3D11_MAP_READ, D3D11_MAP_FLAG_DO_NOT_WAIT, &ms);
			if (hrMap == DXGI_ERROR_WAS_STILL_DRAWING) {
				++pixelProbeDropped;   // dropped, not retried: a dropped sample beats a stall
			} else if (FAILED(hrMap)) {
				pixelProbeDisabled = true;
				SKSE::log::warn("[PIXEL] probe disabled: Map failed hr=0x{:08X}", static_cast<unsigned>(hrMap));
				return;
			} else {
				// Whole rows, padding included: this stays correct for any format because
				// it never has to know the bytes per pixel. Any change inside the block
				// changes the hash; the padding is stable, so it cannot mask one.
				std::uint64_t h = 1469598103934665603ull;   // FNV-1a offset basis
				// v1.26: the block's mean byte alongside the hash. The hash answers
				// "did it change"; the mean answers "did it get brighter or darker",
				// and an oscillation needs the second one. RowPitch padding is stable,
				// so it dilutes the mean by a fixed amount and cannot fake a swing.
				std::uint64_t lumSum = 0;
				std::uint64_t lumN = 0;
				const auto* rows = static_cast<const std::uint8_t*>(ms.pData);
				for (UINT y = 0; y < pixelProbeHeight; ++y) {
					const auto* row = rows + static_cast<std::size_t>(y) * ms.RowPitch;
					for (std::size_t x = 0; x < ms.RowPitch; ++x) {
						h ^= row[x];
						h *= 1099511628211ull;
						lumSum += row[x];
						++lumN;
					}
				}
				const float lum = lumN ? static_cast<float>(lumSum) / static_cast<float>(lumN) : 0.0f;
				d3d11Context->Unmap(pixelProbeStaging.get(), 0);
				pixelProbeCopyPending = false;

				++pixelProbeSamples;
				bool changed = false;
				if (pixelProbeLastHash != 0) {
					changed = (h != pixelProbeLastHash);
					if (changed) {
						++pixelProbeChanged;
						pixelProbeStreak = 0;
					} else {
						++pixelProbeUnchanged;
						++pixelProbeStreak;
						if (pixelProbeStreak > pixelProbeMaxStreak)
							pixelProbeMaxStreak = pixelProbeStreak;
					}
				}
				pixelProbeLastHash = h;

				// v1.26 -- oscillation window. `changed` is incremented whenever this
				// sample differs from the previous one, so an image that alternates
				// A,B,A,B scores a change on every single sample and reads as the
				// healthiest possible picture. The window is what tells the two apart:
				// real content advances through many states, a flicker cycles a few.
				pixelProbeLum = lum;
				pixelProbeRingHash[pixelProbeRingAt] = h;
				pixelProbeRingLum[pixelProbeRingAt] = lum;
				pixelProbeRingAt = (pixelProbeRingAt + 1u) % 8u;
				if (pixelProbeRingFill < 8u)
					++pixelProbeRingFill;
				// v1.28 -- read the window in RING ORDER.  Samples are written at
				// pixelProbeRingHash[pixelProbeRingAt], so slot order is write order
				// rotated by ringAt.  `distinct` survived that mistake because it is
				// order-free; switches/maxRun did not, and the 03:17 run printed
				// maxRun=5 for a window whose tail is six identical samples.
				std::uint64_t ord[8] = {};
				for (std::uint32_t i = 0; i < pixelProbeRingFill; ++i)
					ord[i] = pixelProbeRingHash[(pixelProbeRingAt + i) % 8u];

				// shapeIdx[i] is the index of the first sample in this window that
				// showed the same image, i.e. the state number of sample i.  Printed
				// as shape=[...] so the window's shape needs no arithmetic to read.
				std::uint32_t distinct = 0;
				std::uint32_t shapeIdx[8] = {};
				{
					std::uint64_t seenHash[8] = {};
					for (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
						std::uint32_t k = 0;
						for (; k < distinct; ++k)
							if (seenHash[k] == ord[i]) break;
						if (k == distinct)
							seenHash[distinct++] = ord[i];
						shapeIdx[i] = k;
					}
				}
				float lumLo = 1.0e9f;
				float lumHi = -1.0e9f;
				for (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
					if (pixelProbeRingLum[i] < lumLo) lumLo = pixelProbeRingLum[i];
					if (pixelProbeRingLum[i] > lumHi) lumHi = pixelProbeRingLum[i];
				}
				const float lumSwing = (pixelProbeRingFill >= 8u) ? (lumHi - lumLo) : 0.0f;

				// v1.28 -- counting state changes is still the wrong question, and the
				// 03:17 run proved it twice.  v1.27 required >=3 changes and fired on
				// [96.6][96.6][43.0]x6 and on [43.0]x4[63.8]x3[73.4] -- both ONE-WAY
				// brightness ramps of the loading screen, both with switches=2 in ring
				// order.  (They only fired because the scan was reading the ring out of
				// order, see above.)  The question is not "did it change", it is "did it
				// come BACK".  Collapse the window to its run-length sequence and count
				// how many times a state reappears non-adjacently:
				//   a ramp            [a b c c c c c c] -> [a b c]              -> 0
				//   a light-up        [a a b b b b b b] -> [a b]                -> 0
				//   a flicker         [a b a b a b a b] -> [a b a b a b a b]    -> 12
				// (12 = every non-adjacent pair of equal states in that collapse,
				//  counted by the loop below; a ramp and a light-up both give 0.)
				// rev >= 1 is the gate.  A one-way move can never satisfy it, which is
				// the property v1.26 and v1.27 both lacked.
				std::uint32_t switches = 0;
				std::uint32_t maxRun = 0;
				std::uint32_t runLen = 0;
				for (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
					if (i > 0u && ord[i] != ord[i - 1u]) {
						++switches;
						runLen = 0;
					}
					++runLen;
					if (runLen > maxRun)
						maxRun = runLen;
				}
				std::uint32_t trLen = 0;
				std::uint32_t trIdx[8] = {};
				for (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
					if (trLen == 0u || trIdx[trLen - 1u] != shapeIdx[i])
						trIdx[trLen++] = shapeIdx[i];
				}
				std::uint32_t revisits = 0;
				for (std::uint32_t i = 0; i + 2u < trLen; ++i)
					for (std::uint32_t j = i + 2u; j < trLen; ++j)
						if (trIdx[i] == trIdx[j])
							++revisits;
				char shapeTxt[40] = {};
				{
					int off = 0;
					for (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
						const int wrote = std::snprintf(shapeTxt + off,
							static_cast<std::size_t>(40 - off), (i == 0u) ? "%u" : " %u",
							shapeIdx[i]);
						if (wrote <= 0 || 40 - off - wrote < 4)
							break;
						off += wrote;
					}
				}

				// v1.23: a streak of identical frames only means "frozen" if the camera
				// was moving. With a static camera DLSS-G's interpolated output is
				// legitimately identical to the real frame, so the hash alone cannot
				// distinguish a still picture from a stale one.
				const float cd = fg.lastClipDev.load();
				if (cd > 0.0005f)
					++pixelProbeMovedDuringStreak;
				else
					pixelProbeMovedDuringStreak = 0;

				SKSE::log::info("[PIXEL] #{} hash={:016X} chg={} streak={} clipDev={:.6f} movedThisStreak={} "
					"changed={} unchanged={} maxStreak={} dropped={} "
					"lum={:.2f} seen={}/{} swing={:.1f} sw={} maxRun={} shape=[{}] rev={}",
					pixelProbeSamples, h, changed ? 1 : 0, pixelProbeStreak, static_cast<double>(cd),
					pixelProbeMovedDuringStreak, pixelProbeChanged, pixelProbeUnchanged,
					pixelProbeMaxStreak, pixelProbeDropped,
					static_cast<double>(lum), distinct, pixelProbeRingFill,
					static_cast<double>(lumSwing), switches, maxRun, shapeTxt, revisits);

				// The verdict. Every other witness this file owns can only say that a
				// flip happened; this is the only one that can say the picture moved.
				if (pixelProbeStreak == 6) {
					if (pixelProbeMovedDuringStreak >= 4) {
						SKSE::log::error("[PIXEL] VERDICT: the frame content is byte-identical for 3 "
							"consecutive seconds WHILE the camera was moving (clipDev > 0 on {} of them). "
							"presents, presentAge, dsync and the presented-per-real-frame ratio all report "
							"a healthy flip, so the swap chain is showing the SAME image: what the player "
							"sees is stale.", pixelProbeMovedDuringStreak);
					} else {
						// v1.25: this counter counts the samples on which the camera MOVED, but
						// the old text read "the camera was still on {} of them" and printed
						// that same number -- so the sentence said the opposite of its own
						// value, and a 0 (camera never moved) read as "it moved every time".
						SKSE::log::warn("[PIXEL] {} identical samples in a row, and the camera moved on "
							"only {} of them - a static camera makes interpolated frames "
							"legitimately identical, so this is NOT a frozen-screen verdict. "
							"Hold W for 3 s to make the next streak mean something.",
							pixelProbeStreak, pixelProbeMovedDuringStreak);
					}
				}

				// v1.26 -- the flicker verdict. This one needs no input and no camera
				// motion, which is the point: the input witness has read INPUT_NONE on
				// every movement key in every run since it was added, so a verdict that
				// depends on the player walking has never once been reachable. What the
				// player actually reports is a picture that flickers, and a picture that
				// flickers is exactly what the change counter scores as healthy.
				if (pixelProbeRingFill >= 8u && distinct <= 3u && revisits >= 1u &&
					pixelProbeFlickerFired < 4u) {
					++pixelProbeFlickerFired;
					SKSE::log::error("[PIXEL] FLICKER: the last 8 samples ({:.1f} s) hold only "
						"{} distinct images and the image RETURNED to a state it had already "
						"shown {} times (shape=[{}], {} state changes, longest run {}). That is the "
						"one thing a picture that merely advances can never do: it came back. "
						"Brightness spans {:.0f}/255 (min {:.0f} max {:.0f}); the swing is "
						"reported, not required -- a flicker between two equally bright images "
						"is still a flicker. A picture that CHANGES is not the same as one that "
						"ADVANCES, and the change counter cannot tell them apart: every sample "
						"differs from the previous one while the image cycles a handful of "
						"states. This is the flicker, measured (v1.28: the gate is a revisit, "
						"so a one-way transition such as the loading screen lighting up or a "
						"brightness ramp is rejected by construction).",
						static_cast<double>(pixelProbeRingFill) * 0.5, distinct, revisits,
						shapeTxt, switches, maxRun, static_cast<double>(lumSwing),
						static_cast<double>(lumLo), static_cast<double>(lumHi));
					SKSE::log::info("[PIXEL] FLICKER window (oldest first): "
						"[{:016X} {:.1f}] [{:016X} {:.1f}] [{:016X} {:.1f}] [{:016X} {:.1f}] "
						"[{:016X} {:.1f}] [{:016X} {:.1f}] [{:016X} {:.1f}] [{:016X} {:.1f}]",
						pixelProbeRingHash[(pixelProbeRingAt + 0u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 0u) % 8u]),
						pixelProbeRingHash[(pixelProbeRingAt + 1u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 1u) % 8u]),
						pixelProbeRingHash[(pixelProbeRingAt + 2u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 2u) % 8u]),
						pixelProbeRingHash[(pixelProbeRingAt + 3u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 3u) % 8u]),
						pixelProbeRingHash[(pixelProbeRingAt + 4u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 4u) % 8u]),
						pixelProbeRingHash[(pixelProbeRingAt + 5u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 5u) % 8u]),
						pixelProbeRingHash[(pixelProbeRingAt + 6u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 6u) % 8u]),
						pixelProbeRingHash[(pixelProbeRingAt + 7u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 7u) % 8u]));
				}
			}
		}

		// v1.23 -- the instrument must be able to show that it ran (ledger L39). The
		// v1.22 probe armed and then said nothing for 39 s; the log looked identical
		// to one where the screen was healthy.
		if (pixelProbeSamples == 0 && !pixelProbeSelfWitnessFired &&
			nowMs - pixelProbeArmedMs > 15000u) {
			pixelProbeSelfWitnessFired = true;
			SKSE::log::error("[PIXEL] ERROR: armed {} s ago and produced ZERO samples (dropped={}). The "
				"picture question CANNOT be answered from this run - treat a missing [PIXEL] sample line "
				"as 'no measurement', never as 'the screen was fine'.",
				(nowMs - pixelProbeArmedMs) / 1000u, pixelProbeDropped);
		}

		// ---- phase 1: issue the copy for the NEXT tick ----
		if (srcRes && srcRes->resource11) {
			d3d11Context->CopySubresourceRegion(
				pixelProbeStaging.get(), 0, 0, 0, 0, srcRes->resource11, 0, &pixelProbeBox);
			pixelProbeCopyPending = true;
		}
	}
	HRESULT DX12SwapChain::GetDevice(REFIID uuid, void** ppDevice)
	{
		if (uuid == __uuidof(ID3D11Device) || uuid == __uuidof(ID3D11Device1) || uuid == __uuidof(ID3D11Device2) ||
			uuid == __uuidof(ID3D11Device3) || uuid == __uuidof(ID3D11Device4) || uuid == __uuidof(ID3D11Device5)) {
			*ppDevice = d3d11Device.get();
			d3d11Device->AddRef();  // v0.5：COM 约定返回引用（调用方负责 Release）
			return S_OK;
		}
		return swapChain->GetDevice(uuid, ppDevice);
	}

	HANDLE DX12SwapChain::GetFrameLatencyWaitableObject()
	{
		return swapChain->GetFrameLatencyWaitableObject();
	}

	WrappedResource::WrappedResource(D3D11_TEXTURE2D_DESC a_texDesc, ID3D11Device5* a_d3d11Device, ID3D12Device* a_d3d12Device)
	{
		// D3D11 共享纹理 → 共享句柄 → D3D12 OpenSharedHandle 打开同一资源
		// v0.5：不创建任何视图（深度/typeless 格式建 SRV 会抛异常，且零使用点）；
		// BindFlags 保留调用方传入（swapChainBufferWrapped 需 RENDER_TARGET 供游戏渲染，
		// depth/mvec 只需 SHADER_RESOURCE——DLSSG 在 D3D12 侧自建视图）
		// v0.5.7（CS 方案）：depth 共享纹理用 R32_FLOAT 非深度格式（D32_FLOAT 不在 NT 共享
		// 白名单），按 BindFlags 建 srv/rtv——depth shader 拷贝需要 RTV 输出。
		a_texDesc.MiscFlags |= D3D11_RESOURCE_MISC_SHARED | D3D11_RESOURCE_MISC_SHARED_NTHANDLE;
		DX::ThrowIfFailed(a_d3d11Device->CreateTexture2D(&a_texDesc, nullptr, &resource11));

		winrt::com_ptr<IDXGIResource1> dxgiResource;
		DX::ThrowIfFailed(resource11->QueryInterface(IID_PPV_ARGS(dxgiResource.put())));
		HANDLE sharedHandle = nullptr;
		DX::ThrowIfFailed(dxgiResource->CreateSharedHandle(nullptr, DXGI_SHARED_RESOURCE_READ | DXGI_SHARED_RESOURCE_WRITE, nullptr, &sharedHandle));
		DX::ThrowIfFailed(a_d3d12Device->OpenSharedHandle(sharedHandle, IID_PPV_ARGS(resource.put())));
		CloseHandle(sharedHandle);

		if (a_texDesc.BindFlags & D3D11_BIND_SHADER_RESOURCE) {
			D3D11_SHADER_RESOURCE_VIEW_DESC srvDesc = {};
			srvDesc.Format = a_texDesc.Format;
			srvDesc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
			srvDesc.Texture2D.MostDetailedMip = 0;
			srvDesc.Texture2D.MipLevels = 1;
			DX::ThrowIfFailed(a_d3d11Device->CreateShaderResourceView(resource11, &srvDesc, &srv));
		}
		if (a_texDesc.BindFlags & D3D11_BIND_RENDER_TARGET) {
			D3D11_RENDER_TARGET_VIEW_DESC rtvDesc = {};
			rtvDesc.Format = a_texDesc.Format;
			rtvDesc.ViewDimension = D3D11_RTV_DIMENSION_TEXTURE2D;
			rtvDesc.Texture2D.MipSlice = 0;
			DX::ThrowIfFailed(a_d3d11Device->CreateRenderTargetView(resource11, &rtvDesc, &rtv));
		}
		// v0.7.6：UAV 视图——DLSS 超分输出（colorOut）要求纹理 BindFlags 含
		// UNORDERED_ACCESS 且可拿到 UAV 视图（NGX 以 UAV 写入，否则 RWFlagMissing）
		if (a_texDesc.BindFlags & D3D11_BIND_UNORDERED_ACCESS) {
			D3D11_UNORDERED_ACCESS_VIEW_DESC uavDesc = {};
			uavDesc.Format = a_texDesc.Format;
			uavDesc.ViewDimension = D3D11_UAV_DIMENSION_TEXTURE2D;
			uavDesc.Texture2D.MipSlice = 0;
			DX::ThrowIfFailed(a_d3d11Device->CreateUnorderedAccessView(resource11, &uavDesc, &uav));
		}
	}

	WrappedResource::~WrappedResource()
	{
		if (resource11)
			resource11->Release();
		if (srv)
			srv->Release();
		if (rtv)
			rtv->Release();
		if (uav)
			uav->Release();
	}

	// ---- DXGISwapChainProxy（游戏拿到的假 swapchain，转发到 DX12SwapChain）----

	DXGISwapChainProxy::DXGISwapChainProxy(IDXGISwapChain4* a_swapChain) :
		swapChain(a_swapChain)
	{
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::QueryInterface(REFIID riid, void** ppvObj)
	{
		return swapChain->QueryInterface(riid, ppvObj);
	}

	ULONG STDMETHODCALLTYPE DXGISwapChainProxy::AddRef()
	{
		return swapChain->AddRef();
	}

	ULONG STDMETHODCALLTYPE DXGISwapChainProxy::Release()
	{
		return swapChain->Release();
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::SetPrivateData(_In_ REFGUID Name, UINT DataSize, _In_reads_bytes_(DataSize) const void* pData)
	{
		return swapChain->SetPrivateData(Name, DataSize, pData);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::SetPrivateDataInterface(_In_ REFGUID Name, _In_opt_ const IUnknown* pUnknown)
	{
		return swapChain->SetPrivateDataInterface(Name, pUnknown);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetPrivateData(_In_ REFGUID Name, _Inout_ UINT* pDataSize, _Out_writes_bytes_(*pDataSize) void* pData)
	{
		return swapChain->GetPrivateData(Name, pDataSize, pData);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetParent(_In_ REFIID riid, _COM_Outptr_ void** ppParent)
	{
		return swapChain->GetParent(riid, ppParent);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetDevice(_In_ REFIID riid, _COM_Outptr_ void** ppDevice)
	{
		return Get().dx12SwapChain.GetDevice(riid, ppDevice);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::Present(UINT SyncInterval, UINT Flags)
	{
		// 防御：D3D12 调用异常（设备移除等）不穿过 COM 边界 → 记录并跳帧
		try {
			return Get().dx12SwapChain.Present(SyncInterval, Flags);
		} catch (const DX::com_exception& e) {
			SKSE::log::error("[FrameGen] Present exception at stage '{}': {} - skipping frame", Get().dx12SwapChain.lastStage(), e.what());
			return E_FAIL;
		}
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetBuffer(UINT Buffer, _In_ REFIID riid, _COM_Outptr_ void** ppSurface)
	{
		if (Buffer == 0) {
			// 游戏/ENB 请求 backbuffer 纹理：返回我们的 D3D11 共享纹理（渲染目标）
			if (riid == __uuidof(ID3D11Texture2D) || riid == __uuidof(IDXGISurface)) {
				return Get().dx12SwapChain.swapChainBufferWrapped->resource11->QueryInterface(riid, ppSurface);
			}
		}
		return swapChain->GetBuffer(Buffer, riid, ppSurface);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::SetFullscreenState(BOOL Fullscreen, _In_opt_ IDXGIOutput* pTarget)
	{
		return swapChain->SetFullscreenState(Fullscreen, pTarget);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetFullscreenState(_Out_opt_ BOOL* pFullscreen, _COM_Outptr_opt_result_maybenull_ IDXGIOutput** ppTarget)
	{
		return swapChain->GetFullscreenState(pFullscreen, ppTarget);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetDesc(_Out_ DXGI_SWAP_CHAIN_DESC* pDesc)
	{
		// v0.7.11：回滚 v0.7.10 的"返回渲染尺寸"——实测引擎渲染分辨率不从 GetDesc
		// 初始化（改了仍 1/4），且改它可能干扰引擎窗口/全屏逻辑；DRS 由
		// Main_UpdateJitter hook（渲染前）设置
		return swapChain->GetDesc(pDesc);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::ResizeBuffers(UINT BufferCount, UINT Width, UINT Height, DXGI_FORMAT NewFormat, UINT SwapChainFlags)
	{
		return swapChain->ResizeBuffers(BufferCount, Width, Height, NewFormat, SwapChainFlags);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::ResizeTarget(_In_ const DXGI_MODE_DESC* pNewTargetParameters)
	{
		return swapChain->ResizeTarget(pNewTargetParameters);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetContainingOutput(_COM_Outptr_ IDXGIOutput** ppOutput)
	{
		return swapChain->GetContainingOutput(ppOutput);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetFrameStatistics(_Out_ DXGI_FRAME_STATISTICS* pStats)
	{
		return swapChain->GetFrameStatistics(pStats);
	}

	HRESULT STDMETHODCALLTYPE DXGISwapChainProxy::GetLastPresentCount(_Out_ UINT* pLastPresentCount)
	{
		return swapChain->GetLastPresentCount(pLastPresentCount);
	}
}
