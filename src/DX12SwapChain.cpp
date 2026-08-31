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

#include <SKSE/SKSE.h>

#include "Streamline.h"
#include "FidelityFX.h"
#include "ImguiMenu.h"

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

		for (int i = 0; i < 2; i++) {
			DX::ThrowIfFailed(d3d12Device->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&commandAllocators[i])));
			DX::ThrowIfFailed(d3d12Device->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, commandAllocators[i].get(), nullptr, IID_PPV_ARGS(&commandLists[i])));
			commandLists[i]->Close();
		}
	}

	void DX12SwapChain::CreateSwapChain(IDXGIAdapter* adapter, DXGI_SWAP_CHAIN_DESC a_swapChainDesc, bool a_enableFrameGeneration, bool a_dlssgMode, std::uint32_t a_qualityMode)
	{
		// v0.27：dlssgMode 必须先赋值（CreateD3D12Device 内据此决定是否延迟 slInit）
		dlssgMode = a_dlssgMode;

		CreateD3D12Device(adapter);

		IDXGIFactory4* dxgiFactory;
		DX::ThrowIfFailed(adapter->GetParent(IID_PPV_ARGS(&dxgiFactory)));

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
		{
			const float kUpscaleRatios[5] = { 1.0f, 2.0f / 3.0f, 0.585f, 0.5f, 0.333f };
			const std::uint32_t qm = a_qualityMode < 5 ? a_qualityMode : 0;
			renderScaleX = renderScaleY = kUpscaleRatios[qm];
			renderWidth = static_cast<std::uint32_t>(std::max(1, static_cast<int>(swapChainDesc.Width * renderScaleX)));
			renderHeight = static_cast<std::uint32_t>(std::max(1, static_cast<int>(swapChainDesc.Height * renderScaleY)));
			SKSE::log::info("[FrameGen] Render scale {:.3f} -> {}x{} render / {}x{} output",
				renderScaleX, renderWidth, renderHeight, swapChainDesc.Width, swapChainDesc.Height);
		}

		if (dlssgMode) {
			// v0.3：DLSSG 模式 → 普通 D3D12 swapchain（NVIDIA SL 负责插帧/pacing，不用 FFX）
			DXGI_SWAP_CHAIN_DESC1 desc1{};
			desc1.Width = swapChainDesc.Width;
			desc1.Height = swapChainDesc.Height;
			desc1.Format = swapChainDesc.Format;
			desc1.SampleDesc.Count = 1;
			desc1.BufferUsage = swapChainDesc.BufferUsage;
			desc1.BufferCount = 2;
			// DX12 只支持 FLIP 模型（CreateSwapChainForHwnd 拒绝 DISCARD）——游戏若传
			// DISCARD 会导致创建失败 → 强制 FLIP_DISCARD（DX12 标准，DLSSG 也要求）
			desc1.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
			desc1.Flags = swapChainDesc.Flags;
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

		DX::ThrowIfFailed(swapChain->GetBuffer(0, IID_PPV_ARGS(&swapChainBuffers[0])));
		DX::ThrowIfFailed(swapChain->GetBuffer(1, IID_PPV_ARGS(&swapChainBuffers[1])));

		frameIndex = swapChain->GetCurrentBackBufferIndex();
		SKSE::log::info("[FrameGen] D3D12 FG swapchain created ({}x{}, format {})",
			swapChainDesc.Width, swapChainDesc.Height, static_cast<int>(swapChainDesc.Format));
	}

	void DX12SwapChain::CreateInterop()
	{
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
					dDesc.Format = DXGI_FORMAT_R32_FLOAT;
					dDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;
					depthWrapped = new WrappedResource(dDesc, d3d11Device.get(), d3d12Device.get());
					SKSE::log::info("[FrameGen] DLSSG: depth interop texture created (R32_FLOAT {0}x{1})", dDesc.Width, dDesc.Height);
				}
				auto& mvecTex = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
				if (mvecTex.texture) {
					D3D11_TEXTURE2D_DESC mDesc{};
					static_cast<ID3D11Texture2D*>(mvecTex.texture)->GetDesc(&mDesc);
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

	// v0.7.8：color 采样放大拷贝（超分失败兜底：游戏画面渲染尺寸 → colorOut 4K）
	void DX12SwapChain::CopyColorToShared(ID3D11ShaderResourceView* a_colorSRV, ID3D11RenderTargetView* a_colorRTV)
	{
		if (!colorCopyReady && !colorCopyFailed) {
			try {
				EnsureUpscaleStates();
				if (!copyColorPS) {
					auto psBlob = CompileShaderFromFile(L"Data\\Shaders\\Upscaling\\CopyColorToSharedBufferPS.hlsl", "PSHADER", "ps_5_0");
					DX::ThrowIfFailed(d3d11Device->CreatePixelShader(psBlob->GetBufferPointer(), psBlob->GetBufferSize(), nullptr, copyColorPS.put()));
				}
				colorCopyReady = true;
				SKSE::log::info("[FrameGen] color-copy shaders ready (CopyColorToSharedBufferPS)");
			} catch (const DX::com_exception& e) {
				colorCopyFailed = true;
				SKSE::log::warn("[FrameGen] color-copy shader init failed - fallback copy disabled ({})", e.what());
				return;
			}
		}
		if (!colorCopyReady)
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

		ID3D11ShaderResourceView* srvViews[1] = { a_colorSRV };
		d3d11Context->PSSetShaderResources(0, 1, srvViews);
		ID3D11RenderTargetView* rtvViews[1] = { a_colorRTV };
		d3d11Context->OMSetRenderTargets(1, rtvViews, nullptr);
		d3d11Context->PSSetShader(copyColorPS.get(), nullptr, 0);
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

	HRESULT DX12SwapChain::Present(UINT SyncInterval, UINT Flags)
	{
		auto& fg = Get();

		// v0.7.2：每帧轮询 Home 键（短按切插帧/长按开菜单）——SKSE 输入事件是事件驱动
		// 不支持长按检测，这里直接读硬件状态
		fg.PollHomeKey();

		// v0.26：ForceBorderless 防重置——游戏/INI 若把窗口改回带边框或非全屏
		// （玩家在游戏设置里切窗口模式等），每帧强制恢复无边框铺满（幂等，<1μs）
		fg.EnsureBorderless();

		// v0.7.13：DRS（dynamicResolution）与 DLSS jitter 由 Main_UpdateJitter hook
		// 在渲染前设置（v0.7.11 已验证 kMAIN 2560x1440）；DLSS 超分由
		// MenuManagerDrawInterfaceStart hook 在 UI 绘制前执行（写 kFRAMEBUFFER）。
		// Present 只做：FSR3 FG + 后缓冲 → D3D12 拷贝 + 呈现（纯直通，不覆盖画面）。

		// v0.5.5: stage marker - pinpoint which D3D11/D3D12 call throws (E_INVALIDARG black screen debug)
		m_stage = "enter";

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

		// v0.7.17：恢复 Present 超分（v0.7.12 逻辑）——MenuManager 写 kFRAMEBUFFER 方案在
		// Skyrim SE 上不可行（运行时 kFRAMEBUFFER.texture == nullptr，MenuDraw entry 实锤）。
		// DLSS 输入 = 引擎 kMAIN（DRS 渲染分辨率 1440p）→ colorOut（4K）→ 覆盖后缓冲。
		// UI 是否保留取决于 Skyrim UI 是否画在 kMAIN（实测验证；v0.7.12 未实测 UI 状态）。
		{
			// jitter 已由 Main_UpdateJitter hook 设置（渲染前）✓
			// v0.7.24：enableUpscale=false → 跳过 DLSS（回到纯插帧，帧数最高）
			bool dlssOk = false;
			if (!dlssgMode && fg.fgActive.load() && fg.settings.enableUpscale && fg.streamline.featureDLSS && fg.GetFrameBuffer()) {
				ID3D11Resource* depth11 = nullptr;
				ID3D11Resource* mvec11 = nullptr;
				ID3D11Resource* colorIn11 = swapChainBufferWrapped ? swapChainBufferWrapped->resource11 : nullptr;
				if (auto* renderer = RE::BSGraphics::Renderer::GetSingleton()) {
					auto& depthTex = renderer->GetDepthStencilData().depthStencils[RE::RENDER_TARGETS_DEPTHSTENCIL::kMAIN];
					auto& mvecTex = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
					// v0.7.19：DLSS 输入 = 后缓冲（1440p，含 ENB 后处理 + UI）——kMAIN 是
					// ENB 处理前的 3D 场景，用它覆盖会把 ENB 效果盖掉（用户实测 ENB 没了）
					depth11 = depthTex.texture ? static_cast<ID3D11Resource*>(depthTex.texture) : nullptr;
					mvec11 = mvecTex.texture ? static_cast<ID3D11Resource*>(mvecTex.texture) : nullptr;
					// v0.7.18：extent 用输入纹理实际尺寸（自适应）——kMAIN 应为 1440p（DRS），
					// 用实际尺寸避免放大/裁剪错乱
					std::uint32_t inW = renderWidth;
					std::uint32_t inH = renderHeight;
					if (swapChainBufferWrapped) {
						D3D11_TEXTURE2D_DESC md{};
						static_cast<ID3D11Texture2D*>(swapChainBufferWrapped->resource11)->GetDesc(&md);
						inW = md.Width;
						inH = md.Height;
					}
					// v0.7.18 诊断（节流）：输入实际尺寸 vs 预期 render 尺寸
					// v0.7.23：加 kMAIN 实际尺寸——确认 DRS（NOP 原 DRS 后）是否真降到 1440p
					static std::uint32_t diagFrame = 0;
					if (++diagFrame % 180 == 1) {
						std::uint32_t kMainW = 0, kMainH = 0;
						if (auto* r2 = RE::BSGraphics::Renderer::GetSingleton()) {
							auto& mrt = r2->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMAIN];
							if (mrt.texture) {
								D3D11_TEXTURE2D_DESC kd{};
								static_cast<ID3D11Texture2D*>(mrt.texture)->GetDesc(&kd);
								kMainW = kd.Width;
								kMainH = kd.Height;
							}
						}
						SKSE::log::info("[FrameGen] Upscale diag: backbuffer {}x{} kMAIN {}x{} (expect render {}x{} out {}x{})",
							inW, inH, kMainW, kMainH, renderWidth, renderHeight, swapChainDesc.Width, swapChainDesc.Height);
					}
					dlssOk = fg.streamline.EvaluateDLSS(d3d11Context.get(),
						colorIn11,
						colorOutWrapped ? colorOutWrapped->resource11 : colorIn11,
						depth11, mvec11, inW, inH, *fg.GetFrameBuffer(), fg.settings);
				}
			}
			// 兜底：超分未执行/失败 → 引擎画面拷进 colorOut（同尺寸 4K CopyResource）
			if (!dlssOk && colorOutWrapped && swapChainBufferWrapped)
				d3d11Context->CopyResource(colorOutWrapped->resource11, swapChainBufferWrapped->resource11);
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

		// 等 D3D11 完成
		m_stage = "d3d11 Signal(fence)";
		DX::ThrowIfFailed(d3d11Context->Signal(d3d11Fence.get(), fenceValue));
		m_stage = "d3d12 queue Wait";
		DX::ThrowIfFailed(commandQueue->Wait(d3d12Fence.get(), fenceValue));
		fenceValue++;

		// 新帧，重置命令列表
		m_stage = "allocator Reset";
		DX::ThrowIfFailed(commandAllocators[frameIndex]->Reset());
		m_stage = "cmdlist Reset";
		DX::ThrowIfFailed(commandLists[frameIndex]->Reset(commandAllocators[frameIndex].get(), nullptr));

		// v0.3：DLSSG 模式——NVIDIA 插帧（输入=游戏画面共享纹理，输出=D3D12 backbuffer）
		if (dlssgMode) {
			// v0.31（对齐 open-shaders DX12SwapChain.cpp:365-403）：PCL 完整序列——
			// eSimulationEnd → eRenderSubmitStart 在帧开始发（RSYNC 节奏建立，
			// 缺失 → pacing 乱 → 频闪）。eRenderSubmitEnd 在 ExecuteCommandLists
			// 后、ePresentStart 前（774 行后）。
			fg.streamline.PresentMarkerSimulationEnd();
			fg.streamline.PresentMarkerRenderStart();

			const bool fgOn = fg.fgActive.load();  // Home 键开关
			bool dlssgOk = false;
			// 防刷屏：连续失败计数（static，Present 渲染线程单线程）
			static int dlssgFailCount = 0;
			if (fgOn && fg.streamline.featureDLSSG && fg.GetFrameBuffer()) {
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
			DX::ThrowIfFailed(commandLists[frameIndex]->Close());
			ID3D12CommandList* dlssgLists[] = { commandLists[frameIndex].get() };
			commandQueue->ExecuteCommandLists(1, dlssgLists);
			m_stage = "d3d12 Present(dlssg)";
			// v0.5.22：DLSSG 强制 VSync（SyncInterval=1）——dlss_g 的 RSYNC（vblank 同步器）
			// 强依赖 VSync 建立（日志 "VSync with FG: supported"）；VSync 关 → RSYNC 未初始化
			// → Allocate 时 RSYNC 实例 null → 0xC0000005（SkyrimUpscaler 教程早期版本
			// 同样要求 EnableVsync=true）
			// v0.5.23：Present 前后 PCL marker（RSYNC 节奏建立的必需输入）
			// v0.31：eRenderSubmitEnd 补在 ePresentStart 前（对齐 CS 完整序列）
			fg.streamline.PresentMarkerRenderEnd();
			Get().streamline.PresentMarkerStart();
			DX::ThrowIfFailed(swapChain->Present(1, Flags));
			Get().streamline.PresentMarkerEnd();
			m_stage = "d3d12 queue Signal";
			DX::ThrowIfFailed(commandQueue->Signal(d3d12Fence.get(), fenceValue));
			m_stage = "d3d11 Wait";
			DX::ThrowIfFailed(d3d11Context->Wait(d3d11Fence.get(), fenceValue));
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

		// 呈现
		m_stage = "d3d12 Present";
		// v0.5.22：DLSSG 强制 VSync（同 dlssg 分支，RSYNC 依赖）
		// v0.5.23：PCL marker
		Get().streamline.PresentMarkerStart();
		DX::ThrowIfFailed(swapChain->Present(1, Flags));
		Get().streamline.PresentMarkerEnd();

		// 等 D3D12 完成
		m_stage = "d3d12 queue Signal";
		DX::ThrowIfFailed(commandQueue->Signal(d3d12Fence.get(), fenceValue));
		m_stage = "d3d11 Wait";
		DX::ThrowIfFailed(d3d11Context->Wait(d3d11Fence.get(), fenceValue));
		fenceValue++;

		frameIndex = swapChain->GetCurrentBackBufferIndex();

		return S_OK;
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
