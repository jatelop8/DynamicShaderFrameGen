// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

// 注意：CommonLib 头必须最先（Streamline.h 含 Windows API 头）
#include "FrameGen.h"

#include "Streamline.h"

#include <dxgi.h>
#include <dxgi1_3.h>

#include <SKSE/SKSE.h>

namespace FrameGen
{
	void StreamlineLogCallback(sl::LogType a_type, const char* a_msg)
	{
		switch (a_type) {
		case sl::LogType::eInfo:
			SKSE::log::info("[StreamlineSDK] {}", a_msg);
			break;
		case sl::LogType::eWarn:
			SKSE::log::warn("[StreamlineSDK] {}", a_msg);
			break;
		case sl::LogType::eError:
			SKSE::log::error("[StreamlineSDK] {}", a_msg);
			break;
		}
	}

	void Streamline::LoadInterposer(const Settings& a_settings)
	{
		// 防御：防重复初始化（D3D11CreateDeviceAndSwapChain 钩子理论上只调一次，
		// 但引擎若多次创建设备会重复 slInit → 状态错乱）
		if (triedInitialization)
			return;
		triedInitialization = true;

		std::wstring interposerPath = std::wstring(Streamline::PluginDir) + L"\\sl.interposer.dll";
		interposer = LoadLibraryW(interposerPath.c_str());
		if (!interposer) {
			SKSE::log::info("[Streamline] Failed to load interposer (error {:#x}) - DLSS frame generation disabled", GetLastError());
			return;
		}
		SKSE::log::info("[Streamline] Interposer loaded from {}", stl::utf16_to_utf8(interposerPath).value_or("?"));
		if (auto ver = stl::utf16_to_utf8(Streamline::PluginDir); ver) {
			SKSE::log::info("[Streamline] Plugin dir: {}", *ver);
		}

		sl::Preferences pref;
		// v0.3：DLSSG 模式（provider=1）加载 DLSSG + Reflex（DLSSG 运行时要求 Reflex 激活）；
		// FSR3 模式（provider=0）保持仅 DLSS 超分。DLSSG 只支持 D3D12 → renderAPI 按模式切换。
		sl::Feature featuresDLSS[] = { sl::kFeatureDLSS };
		// v0.5.9（参考 SkyrimUpscaler：DLSS 超分 + DLSSG 同时加载）：DLSSG 帧生成依赖
		// DLSS 超分上下文（dlss_g 插件初始化验证 kFeatureDLSS context，缺失 → 不注册
		// evaluateFeature 回调 → slEvaluateFeature failed 28。实测：features 只有
		// [DLSS_G, Reflex] 时日志 "kFeatureDLSS' context is missing" + Callback 0x0）
		sl::Feature featuresDLSSG[] = { sl::kFeatureDLSS, sl::kFeatureDLSS_G, sl::kFeatureReflex };
		// v0.8.35：DLSS-NR feature id = 1004（sl.dlss_nr.dll 代码区 7 处引用 1004 实锤；
		// SL SDK 头文件无此枚举，运行时插件注册）。必须加进 featuresToLoad，
		// sl.interposer 才会加载 sl.dlss_nr.dll 插件并注册 NR 函数
		// （NGX_D3D12_CREATE_DLSSNR_EXT 等，经 slGetFeatureFunction 查询）。
		// 注：kFeatureDirectSR=1003、NvPerf=1002、DLSS_RR=1001、DLSS_G=1000——
		// 1004 是 NR 的相邻新枚举（dlss5-dx11-bridge 同源 SDK 版本验证）。
		sl::Feature featuresNR[] = { sl::kFeatureDLSS, sl::kFeatureDLSS_G, sl::kFeatureReflex, 1004 };
		// v0.24.2：恢复 D3D11 DLSS 超分——v0.8.20 为 NR 验证强制 D3D12，导致
		// EvaluateDLSS 跳过、DLSS feature 永不创建 → bridge（DLSS5 外挂 ReShade）
		// 拦不到 CreateFeature → NR 无输入失效（用户实测 00:52）。
		// provider=0（FSR3）→ D3D11 会话（DLSS 超分可用，bridge 可拦）；
		// provider=1（DLSSG）→ D3D12（保留 NR 1004 注册，DLSSG 需要 D3D12）。
		useD3D12 = a_settings.provider == 1;
		pref.featuresToLoad = useD3D12 ? featuresNR : featuresDLSS;
		pref.numFeaturesToLoad = useD3D12 ? _countof(featuresNR) : _countof(featuresDLSS);

		switch (a_settings.streamlineLogLevel) {
		case 2:
			pref.logLevel = sl::LogLevel::eVerbose;
			break;
		case 1:
			pref.logLevel = sl::LogLevel::eDefault;
			break;
		default:
			pref.logLevel = sl::LogLevel::eOff;
			break;
		}
		pref.logMessageCallback = StreamlineLogCallback;
		pref.showConsole = false;
		pref.engine = sl::EngineType::eCustom;
		pref.engineVersion = "1.0.0";
		pref.projectId = "f8776929-c969-43bd-ac2b-294b4de58aac";  // 与 CS 相同（Streamline 注册项目）
		pref.renderAPI = useD3D12 ? sl::RenderAPI::eD3D12 : sl::RenderAPI::eD3D11;
		// v0.5.11：eUseFrameBasedResourceTagging（frame-based tagging）——
		// slSetTag 已弃用，dlss_g 插件要求 slSetTagForFrame + 此 flag
		// v0.5.24：去掉 eUseManualHooking——SL 自动 hook 模式
		// v0.5.26：加 eUseDXGIFactoryProxy——SL 代理 DXGI factory 拦截 swapchain 创建
		// （SkyrimUpscaler 8-13 日志 hk_IDXGIFactory_CreateSwapChain 同思路）→ SL 自动
		// 记录 swapchain/queue 上下文 → 插件内部槽填充（allocate 不再 null）
		pref.flags = sl::PreferenceFlags::eUseFrameBasedResourceTagging | sl::PreferenceFlags::eUseDXGIFactoryProxy;

		slInit = reinterpret_cast<PFun_slInit*>(GetProcAddress(interposer, "slInit"));
		slShutdown = reinterpret_cast<PFun_slShutdown*>(GetProcAddress(interposer, "slShutdown"));
		slIsFeatureSupported = reinterpret_cast<PFun_slIsFeatureSupported*>(GetProcAddress(interposer, "slIsFeatureSupported"));
		slIsFeatureLoaded = reinterpret_cast<PFun_slIsFeatureLoaded*>(GetProcAddress(interposer, "slIsFeatureLoaded"));
		slEvaluateFeature = reinterpret_cast<PFun_slEvaluateFeature*>(GetProcAddress(interposer, "slEvaluateFeature"));
		slFreeResources = reinterpret_cast<PFun_slFreeResources*>(GetProcAddress(interposer, "slFreeResources"));
		slAllocateResources = reinterpret_cast<PFun_slAllocateResources*>(GetProcAddress(interposer, "slAllocateResources"));
		slSetTag = reinterpret_cast<PFun_slSetTag*>(GetProcAddress(interposer, "slSetTag"));
		slSetTagForFrame = reinterpret_cast<PFun_slSetTagForFrame*>(GetProcAddress(interposer, "slSetTagForFrame"));
		slSetConstants = reinterpret_cast<PFun_slSetConstants*>(GetProcAddress(interposer, "slSetConstants"));
		slGetFeatureFunction = reinterpret_cast<PFun_slGetFeatureFunction*>(GetProcAddress(interposer, "slGetFeatureFunction"));
		slGetNewFrameToken = reinterpret_cast<PFun_slGetNewFrameToken*>(GetProcAddress(interposer, "slGetNewFrameToken"));
		slSetD3DDevice = reinterpret_cast<PFun_slSetD3DDevice*>(GetProcAddress(interposer, "slSetD3DDevice"));
		slUpgradeInterface = reinterpret_cast<PFun_slUpgradeInterface*>(GetProcAddress(interposer, "slUpgradeInterface"));

		if (SL_FAILED(result, slInit(pref, sl::kSDKVersion))) {
			SKSE::log::error("[Streamline] slInit failed: {}", (int)result);
		} else {
			initialized = true;
			SKSE::log::info("[Streamline] Initialized OK");
		}
	}

	void Streamline::CheckFeatures(IDXGIAdapter* a_adapter)
	{
		if (!initialized)
			return;
		DXGI_ADAPTER_DESC adapterDesc;
		a_adapter->GetDesc(&adapterDesc);

		sl::AdapterInfo adapterInfo;
		adapterInfo.deviceLUID = reinterpret_cast<std::uint8_t*>(&adapterDesc.AdapterLuid);
		adapterInfo.deviceLUIDSizeInBytes = sizeof(LUID);

		slIsFeatureLoaded(sl::kFeatureDLSS, featureDLSS);
		if (featureDLSS) {
			featureDLSS = slIsFeatureSupported(sl::kFeatureDLSS, adapterInfo) == sl::Result::eOk;
			// 40 系以下 RTX → DLSS 4.0，否则 4.5（仅影响预设选择）
			if (adapterDesc.VendorId == 0x10DE &&
				((adapterDesc.DeviceId >= 0x1E00 && adapterDesc.DeviceId <= 0x1FFF) ||
					(adapterDesc.DeviceId >= 0x2200 && adapterDesc.DeviceId <= 0x2600)))
				isRTXBelow40series = true;
		}
		SKSE::log::info("[Streamline] DLSS {} available", featureDLSS ? "IS" : "is NOT");

		// v0.3：DLSSG 检测（provider=1 时）
		if (useD3D12) {
			bool loaded = false;
			slIsFeatureLoaded(sl::kFeatureDLSS_G, loaded);
			if (loaded)
				featureDLSSG = slIsFeatureSupported(sl::kFeatureDLSS_G, adapterInfo) == sl::Result::eOk;
			SKSE::log::info("[Streamline] DLSS-G {} available", featureDLSSG ? "IS" : "is NOT");
		}
	}

	void Streamline::PostDevice()
	{
		if (!initialized)
			return;
		if (featureDLSS) {
			slGetFeatureFunction(sl::kFeatureDLSS, "slDLSSSetOptions", reinterpret_cast<void*&>(slDLSSSetOptions));
		}
		// v0.3：DLSSG + Reflex 函数绑定（provider=1）
		if (useD3D12 && featureDLSSG) {
			slGetFeatureFunction(sl::kFeatureDLSS_G, "slDLSSGSetOptions", reinterpret_cast<void*&>(slDLSSGSetOptions));
			slGetFeatureFunction(sl::kFeatureReflex, "slReflexSetOptions", reinterpret_cast<void*&>(slReflexSetOptions));
			// v0.5.23：PCL marker 从 interposer 导出加载（RSYNC 依赖）
			slPCLSetMarker = reinterpret_cast<PFun_slPCLSetMarker*>(GetProcAddress(interposer, "slPCLSetMarker"));
			SKSE::log::info("[Streamline] DLSSG/Reflex functions bound");
		}
	}

	void Streamline::SetD3DDevice(ID3D11Device* a_device)
	{
		if (!initialized)
			return;
		slSetD3DDevice(a_device);
		SKSE::log::info("[Streamline] D3D11 device set");
	}

	void Streamline::SetD3D12Device(ID3D12Device* a_device)
	{
		if (!initialized)
			return;
		slSetD3DDevice(a_device);
		SKSE::log::info("[Streamline] D3D12 device set");
	}

	// v0.5.10：manual hooking 模式必须 upgrade 接口（swapchain 必调）——
	// SL 通过升级后的链进入呈现路径，每帧调 common 插件 presentCommon()，
	// 否则 DLSSG 插件 evaluateFeature 回调不注册（0x0）→ slEvaluateFeature 恒失败 28。
	void Streamline::UpgradeInterface(void** a_ppInterface)
	{
		if (!initialized || !slUpgradeInterface || !a_ppInterface || !*a_ppInterface)
			return;
		sl::Result r = slUpgradeInterface(a_ppInterface);
		if (SL_FAILED(r, r))
			SKSE::log::error("[Streamline] slUpgradeInterface failed: {}", (int)r);
		else
			SKSE::log::info("[Streamline] Interface upgraded (presentCommon path active)");
	}

	void Streamline::CheckFrameConstants(const FrameBuffer& a_fb, float a_aspect, float a_near, float a_far)
	{
		if (!initialized)
			return;

		// v0.5：frameToken 失败保护（失败 → 置空 → 调用方跳过本帧 SL 调用，防空指针解引用）
		frameToken = nullptr;
		if (SL_FAILED(r, slGetNewFrameToken(frameToken, nullptr))) {
			SKSE::log::error("[Streamline] slGetNewFrameToken failed: {}", (int)r);
			return;
		}
		if (!frameToken)
			return;

		sl::Constants c{};
		c.cameraAspectRatio = a_aspect;
		c.cameraFOV = Get().GetVerticalFOVRad();  // v0.4.4：DLSSG 相机常量校验需要（默认 INVALID_FLOAT）
		c.cameraNear = a_near;
		c.cameraFar = a_far;

		// 视图矩阵：CameraViewInverse 转置 → SL 期望 row-major 视图（cameraRight/Up/Fwd/Pos）
		// 引擎矩阵是 row-major，CameraViewInverse 存的是视图逆（camera-to-world）。
		// SL 的 cameraRight/Up/Fwd/Pos 来自 view 矩阵（world-to-camera）的行。
		// CS: GetCameraViewInverse(0).Transpose() → 取行做 cameraRight/Up/Fwd，
		// 且 viewMatrix._11.._13 是转置后的第 1 行 = 原矩阵第 1 列。
		// 这里与 CS 完全一致（引擎 worldToCam 转置 = 原矩阵列）。
		const auto& inv = a_fb.CameraViewInverse.data;
		// CameraViewInverse 转置 → SL 期望 row-major 视图矩阵
		sl::float4x4 viewInvT;
		viewInvT[0] = sl::float4(inv[0][0], inv[1][0], inv[2][0], inv[3][0]);
		viewInvT[1] = sl::float4(inv[0][1], inv[1][1], inv[2][1], inv[3][1]);
		viewInvT[2] = sl::float4(inv[0][2], inv[1][2], inv[2][2], inv[3][2]);
		viewInvT[3] = sl::float4(inv[0][3], inv[1][3], inv[2][3], inv[3][3]);
		c.cameraRight = sl::float3(viewInvT[0].x, viewInvT[0].y, viewInvT[0].z);
		c.cameraUp = sl::float3(viewInvT[1].x, viewInvT[1].y, viewInvT[1].z);
		c.cameraFwd = sl::float3(viewInvT[2].x, viewInvT[2].y, viewInvT[2].z);
		c.cameraPos = *(sl::float3*)&a_fb.CameraPosAdjust;

		// 投影矩阵（未抖动）转置
		const auto& proj = a_fb.CameraProjUnjittered.data;
		sl::float4x4 projT;
		projT[0] = sl::float4(proj[0][0], proj[1][0], proj[2][0], proj[3][0]);
		projT[1] = sl::float4(proj[0][1], proj[1][1], proj[2][1], proj[3][1]);
		projT[2] = sl::float4(proj[0][2], proj[1][2], proj[2][2], proj[3][2]);
		projT[3] = sl::float4(proj[0][3], proj[1][3], proj[2][3], proj[3][3]);
		c.cameraViewToClip = projT;
		// v0.5：clipToCameraView 标必填（默认 INVALID_FLOAT）——投影逆矩阵
		sl::matrixFullInvert(c.clipToCameraView, c.cameraViewToClip);
		c.cameraMotionIncluded = sl::Boolean::eTrue;
		c.cameraPinholeOffset = { 0.f, 0.f };

		// prev 帧矩阵（引擎提供的 prev viewproj）——值拷贝避免引用推导歧义
		const Matrix curVP = a_fb.CameraViewProjUnjittered;
		const Matrix prevVP = a_fb.CameraPreviousViewProjUnjittered;
		sl::float4x4 currViewProjSL;
		currViewProjSL[0] = sl::float4(curVP.data[0][0], curVP.data[1][0], curVP.data[2][0], curVP.data[3][0]);
		currViewProjSL[1] = sl::float4(curVP.data[0][1], curVP.data[1][1], curVP.data[2][1], curVP.data[3][1]);
		currViewProjSL[2] = sl::float4(curVP.data[0][2], curVP.data[1][2], curVP.data[2][2], curVP.data[3][2]);
		currViewProjSL[3] = sl::float4(curVP.data[0][3], curVP.data[1][3], curVP.data[2][3], curVP.data[3][3]);
		sl::float4x4 prevViewProjSL;
		prevViewProjSL[0] = sl::float4(prevVP.data[0][0], prevVP.data[1][0], prevVP.data[2][0], prevVP.data[3][0]);
		prevViewProjSL[1] = sl::float4(prevVP.data[0][1], prevVP.data[1][1], prevVP.data[2][1], prevVP.data[3][1]);
		prevViewProjSL[2] = sl::float4(prevVP.data[0][2], prevVP.data[1][2], prevVP.data[2][2], prevVP.data[3][2]);
		prevViewProjSL[3] = sl::float4(prevVP.data[0][3], prevVP.data[1][3], prevVP.data[2][3], prevVP.data[3][3]);
		sl::float4x4 invCurrViewProj;
		sl::matrixFullInvert(invCurrViewProj, currViewProjSL);
		sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevViewProjSL);
		sl::matrixFullInvert(c.prevClipToClip, c.clipToPrevClip);

		c.jitterOffset = { 0.f, 0.f };  // v1：不接入 TAA 抖动
		c.reset = sl::Boolean::eFalse;
		c.mvecScale = { 1.0f, 1.0f };
		c.motionVectors3D = sl::Boolean::eFalse;
		c.motionVectorsInvalidValue = FLT_MIN;
		c.orthographicProjection = sl::Boolean::eFalse;
		c.motionVectorsDilated = sl::Boolean::eFalse;
		c.motionVectorsJittered = sl::Boolean::eFalse;
		c.depthInverted = sl::Boolean::eFalse;

		if (SL_FAILED(r, slSetConstants(c, *frameToken, viewport)))
			SKSE::log::error("[Streamline] slSetConstants failed: {}", (int)r);
	}

	void Streamline::SetDLSSOptions(std::uint32_t a_outputWidth, const Settings& a_settings)
	{
		sl::DLSSOptions opts{};
		switch (a_settings.qualityMode) {
		case 1:
			opts.mode = sl::DLSSMode::eMaxQuality;
			break;
		case 2:
			opts.mode = sl::DLSSMode::eBalanced;
			break;
		case 3:
			opts.mode = sl::DLSSMode::eMaxPerformance;
			break;
		case 4:
			opts.mode = sl::DLSSMode::eUltraPerformance;
			break;
		default:
			opts.mode = sl::DLSSMode::eDLAA;
			break;
		}

		opts.outputWidth = a_outputWidth;
		opts.outputHeight = static_cast<std::uint32_t>(Get().screenHeight);

		// HDR 检测：kMAIN 格式
		bool isHDR = false;
		if (auto* renderer = RE::BSGraphics::Renderer::GetSingleton()) {
			auto& main = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMAIN];
			if (main.texture) {
				D3D11_TEXTURE2D_DESC desc{};
				static_cast<ID3D11Texture2D*>(main.texture)->GetDesc(&desc);
				isHDR = desc.Format != DXGI_FORMAT_R8G8B8A8_UNORM;
			}
		}
		opts.colorBuffersHDR = isHDR ? sl::Boolean::eTrue : sl::Boolean::eFalse;
		opts.useAutoExposure = sl::Boolean::eTrue;

		// 预设（DLSS 模型选择）
		auto applyPreset = [&](sl::DLSSPreset p) {
			opts.dlaaPreset = p;
			opts.ultraQualityPreset = p;
			opts.qualityPreset = p;
			opts.balancedPreset = p;
			opts.performancePreset = p;
			opts.ultraPerformancePreset = p;
		};
		switch (a_settings.presetDLSS) {
		case 1:
			applyPreset(sl::DLSSPreset::ePresetJ);
			break;
		case 2:
			applyPreset(sl::DLSSPreset::ePresetK);
			break;
		case 3:
			applyPreset(sl::DLSSPreset::ePresetL);
			break;
		case 4:
			applyPreset(sl::DLSSPreset::ePresetM);
			break;
		default:
			if (isRTXBelow40series) {
				opts.dlaaPreset = sl::DLSSPreset::ePresetJ;
				opts.ultraQualityPreset = sl::DLSSPreset::ePresetJ;
				opts.qualityPreset = sl::DLSSPreset::ePresetJ;
				opts.balancedPreset = sl::DLSSPreset::ePresetJ;
				opts.performancePreset = sl::DLSSPreset::ePresetJ;
				opts.ultraPerformancePreset = sl::DLSSPreset::ePresetM;
			} else {
				opts.dlaaPreset = sl::DLSSPreset::ePresetJ;
				opts.ultraQualityPreset = sl::DLSSPreset::ePresetJ;
				opts.qualityPreset = sl::DLSSPreset::ePresetM;
				opts.balancedPreset = sl::DLSSPreset::ePresetM;
				opts.performancePreset = sl::DLSSPreset::ePresetM;
				opts.ultraPerformancePreset = sl::DLSSPreset::ePresetL;
			}
			break;
		}

		opts.preExposure = 1.0f;
		opts.sharpness = a_settings.sharpness;  // v0.6.3：INI 可调锐化（0=关闭）

		if (SL_FAILED(r, slDLSSSetOptions(viewport, opts)))
			SKSE::log::error("[Streamline] slDLSSSetOptions failed: {}", (int)r);
	}

	// v0.3：DLSSG 选项（NVIDIA 插帧）——Provider=1 时每帧调用
	void Streamline::SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,
		std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat)
	{
		if (!initialized || !featureDLSSG || !slDLSSGSetOptions)
			return;
		sl::DLSSGOptions opts{};
		opts.mode = sl::DLSSGMode::eOn;
		opts.numFramesToGenerate = 1;  // 2x 插帧（每 1 个真实帧生成 1 个插帧）
		opts.numBackBuffers = 3;  // v0.5.25：对齐 SkyrimUpscaler（proxy BufferCount=3，8-13 日志实锤）
		opts.colorWidth = a_width;
		opts.colorHeight = a_height;
		opts.mvecDepthWidth = a_mvecDepthW;
		opts.mvecDepthHeight = a_mvecDepthH;
		opts.colorBufferFormat = static_cast<std::uint32_t>(a_colorFormat);
		opts.hudLessBufferFormat = static_cast<std::uint32_t>(a_colorFormat);
		// v0.5：mvec/depth 格式从引擎渲染目标取（DLSSG 需要精确格式解码运动矢量/深度）
		// v0.5.14：depth 声明必须与实际喂给 DLSSG 的共享纹理格式一致——引擎深度是 D32_FLOAT，
		// 但共享 depth 纹理是自建的 R32_FLOAT（DX12SwapChain CreateInterop）；声明 D32 实际 R32
		// 会让 NGX 内部按错格式初始化 → sl.dlss_g.dll 在 Allocate 时 0xC0000005 崩溃（dump 实锤）
		if (auto* renderer = RE::BSGraphics::Renderer::GetSingleton()) {
			auto& mvecTex = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
			if (mvecTex.texture) {
				D3D11_TEXTURE2D_DESC d{};
				static_cast<ID3D11Texture2D*>(mvecTex.texture)->GetDesc(&d);
				opts.mvecBufferFormat = static_cast<std::uint32_t>(d.Format);
			}
		}
		opts.depthBufferFormat = static_cast<std::uint32_t>(DXGI_FORMAT_R32_FLOAT);
		// v1：UI 重合成未接入（无 UI 分离）→ HUD 在插帧时可能模糊/重影（已知限制）
		opts.enableUserInterfaceRecomposition = sl::Boolean::eFalse;
		if (SL_FAILED(r, slDLSSGSetOptions(viewport, opts)))
			SKSE::log::error("[Streamline] slDLSSGSetOptions failed: {}", (int)r);
	}

	// v0.3：DLSSG 每帧评估（D3D12 路径）——游戏画面在共享纹理，插帧输出到 D3D12 backbuffer
	bool Streamline::EvaluateDLSSG(ID3D12GraphicsCommandList* a_cmdList,
		ID3D12Resource* a_colorIn, ID3D12Resource* a_colorOut,
		ID3D12Resource* a_depth, ID3D12Resource* a_motionVectors,
		const FrameBuffer& a_fb)
	{
		if (!initialized || !featureDLSSG || !a_colorIn || !a_colorOut || !a_depth || !a_motionVectors)
			return false;
		// v0.5.20：首 2 帧直通（不调 DLSSG）——给 presentCommon/pacer 建立窗口
		static int fgFrames = 0;
		if (fgFrames < 2) {
			fgFrames++;
			return false;
		}
		auto& fg = Get();
		const float aspect = fg.screenHeight > 0 ? fg.screenWidth / fg.screenHeight : 16.0f / 9.0f;
		const float nearZ = fg.cameraNear ? *fg.cameraNear : 1.0f;
		const float farZ = fg.cameraFar ? *fg.cameraFar : 10000.0f;
		// v0.5.21：slSetConstants 提前到 allocate 之前——RSYNC pacer 在
		// SetConstants（含 frame 时间/Reflex 数据）时创建；allocate 读 pacer context，
		// 之前顺序 SetOptions→allocate→SetConstants 导致 allocate 时 pacer 未建 → null → 崩
		CheckFrameConstants(a_fb, aspect, nearZ, farZ);

		// v0.5.19：显式 slAllocateResources（传 cmdList）——DLSSG（feature 1000）不走惰性初始化
		static bool dlssgAllocTried = false;
		if (!dlssgAllocTried && slAllocateResources) {
			dlssgAllocTried = true;
			sl::ViewportHandle vp(viewport);
			sl::Result ar = slAllocateResources(reinterpret_cast<sl::CommandBuffer*>(a_cmdList), sl::kFeatureDLSS_G, vp);
			if (SL_FAILED(ar, ar))
				SKSE::log::error("[Streamline] slAllocateResources(DLSS_G) failed: {} - DLSSG disabled (check NGX model cache), passthrough", (int)ar);
			else
				SKSE::log::info("[Streamline] DLSSG resources allocated (feature context created)");
		}

		sl::Resource colorInRes = { sl::ResourceType::eTex2d, a_colorIn, 0 };
		sl::Resource colorOutRes = { sl::ResourceType::eTex2d, a_colorOut, 0 };
		sl::Resource depthRes = { sl::ResourceType::eTex2d, a_depth, 0 };
		sl::Resource mvecRes = { sl::ResourceType::eTex2d, a_motionVectors, 0 };

		const std::uint32_t w = fg.dx12SwapChain.swapChainDesc.Width;
		const std::uint32_t h = fg.dx12SwapChain.swapChainDesc.Height;
		sl::Extent extent{ 0, 0, w, h };
		sl::ResourceTag tags[] = {
			{ &colorInRes, sl::kBufferTypeHUDLessColor, sl::ResourceLifecycle::eOnlyValidNow, &extent },
			{ &colorOutRes, sl::kBufferTypeScalingOutputColor, sl::ResourceLifecycle::eOnlyValidNow, &extent },
			{ &depthRes, sl::kBufferTypeDepth, sl::ResourceLifecycle::eValidUntilPresent, &extent },
			{ &mvecRes, sl::kBufferTypeMotionVectors, sl::ResourceLifecycle::eValidUntilPresent, &extent },
		};
		// v0.5.11：slSetTagForFrame（frame-based tagging）替代弃用的 slSetTag——
		// 需 eUseFrameBasedResourceTagging flag + frameToken（DLSS-G 指南 306-339 全用此 API）
		if (!frameToken) {
			SKSE::log::error("[Streamline] slSetTagForFrame skipped - null frameToken");
			return false;
		}
		slSetTagForFrame(*frameToken, viewport, tags, _countof(tags), a_cmdList);

		sl::ViewportHandle view(viewport);
		const sl::BaseStructure* inputs[] = { &view };
		if (SL_FAILED(r, slEvaluateFeature(sl::kFeatureDLSS_G, *frameToken, inputs, _countof(inputs), a_cmdList))) {
			SKSE::log::error("[Streamline] slEvaluateFeature(DLSSG) failed: {}", (int)r);
			return false;
		}
		return true;
	}

	// v0.3：DLSSG 运行时要求 Reflex 激活（DLSSGStatus eFailReflexNotDetectedAtRuntime）
	void Streamline::ActivateReflex()
	{
		if (!initialized || !slReflexSetOptions)
			return;
		sl::ReflexOptions opts{};
		opts.mode = sl::ReflexMode::eLowLatency;  // 新版 ReflexMode：eOff/eLowLatency/eLowLatencyWithBoost
		if (SL_FAILED(r, slReflexSetOptions(opts)))
			SKSE::log::error("[Streamline] slReflexSetOptions failed: {}", (int)r);
		else
			SKSE::log::info("[Streamline] Reflex activated (DLSSG requirement)");
	}

	// v0.5.23：PCL marker（RSYNC 建立节奏的必需输入，DLSS-G 指南 8.0）
	void Streamline::PresentMarkerStart()
	{
		if (!initialized || !slPCLSetMarker || !frameToken)
			return;
		slPCLSetMarker(sl::PCLMarker::ePresentStart, *frameToken);
	}

	void Streamline::PresentMarkerEnd()
	{
		if (!initialized || !slPCLSetMarker || !frameToken)
			return;
		slPCLSetMarker(sl::PCLMarker::ePresentEnd, *frameToken);
	}

	bool Streamline::EvaluateDLSS(ID3D11DeviceContext* a_ctx,
		ID3D11Resource* a_colorIn, ID3D11Resource* a_colorOut,
		ID3D11Resource* a_depth, ID3D11Resource* a_motionVectors,
		std::uint32_t a_renderWidth, std::uint32_t a_renderHeight,
		const FrameBuffer& a_fb, const Settings& a_settings)
	{
		// v0.8.20：SL 强制 D3D12 后，D3D11 超分不再可用（feature 是 D3D12 的，
		// 用 D3D11 ctx 调 slEvaluateFeature 类型不匹配）。直接跳过 → 调用方兜底
		// （colorOut = 引擎画面拷贝），NR 验证阶段优先。
		if (useD3D12)
			return false;
		if (!initialized || !featureDLSS)
			return false;

		auto& fg = Get();
		const float aspect = fg.screenHeight > 0 ? fg.screenWidth / fg.screenHeight : 16.0f / 9.0f;
		const float nearZ = fg.cameraNear ? *fg.cameraNear : 1.0f;
		const float farZ = fg.cameraFar ? *fg.cameraFar : 10000.0f;

		CheckFrameConstants(a_fb, aspect, nearZ, farZ);
		// 输出分辨率（4K）——DLSS 放大目标；screenWidth 为 float（窗口尺寸）
		SetDLSSOptions(static_cast<std::uint32_t>(fg.screenWidth) > 0 ? static_cast<std::uint32_t>(fg.screenWidth) : a_renderWidth, a_settings);

		sl::Resource colorInRes = { sl::ResourceType::eTex2d, a_colorIn, 0 };
		sl::Resource colorOutRes = { sl::ResourceType::eTex2d, a_colorOut, 0 };
		sl::Resource depthRes = { sl::ResourceType::eTex2d, a_depth, 0 };
		sl::Resource mvecRes = { sl::ResourceType::eTex2d, a_motionVectors, 0 };

		// v0.7.8：输入 extent = 渲染分辨率（低），输出 extent = 输出分辨率（4K）——
		// DLSS 把渲染分辨率画面放大到输出分辨率（超分才有意义）
		const std::uint32_t inW = std::max(1u, a_renderWidth);
		const std::uint32_t inH = std::max(1u, a_renderHeight);
		const std::uint32_t outW = std::max(1u, static_cast<std::uint32_t>(fg.screenWidth));
		const std::uint32_t outH = std::max(1u, static_cast<std::uint32_t>(fg.screenHeight));
		sl::Extent extentIn{ 0, 0, inW, inH };
		sl::Extent extentOut{ 0, 0, outW, outH };

		sl::ResourceTag tags[] = {
			{ &colorInRes, sl::kBufferTypeScalingInputColor, sl::ResourceLifecycle::eOnlyValidNow, &extentIn },
			{ &colorOutRes, sl::kBufferTypeScalingOutputColor, sl::ResourceLifecycle::eOnlyValidNow, &extentOut },
			{ &depthRes, sl::kBufferTypeDepth, sl::ResourceLifecycle::eValidUntilPresent, &extentIn },
			{ &mvecRes, sl::kBufferTypeMotionVectors, sl::ResourceLifecycle::eValidUntilPresent, &extentIn },
		};

		// v0.7.4：超分路径改用 slSetTagForFrame（v0.5.11 只改了 DLSSG，这里漏改）——
		// flag 已设 eUseFrameBasedResourceTagging，要求 frame-based tagging；旧 slSetTag
		// 弃用后 tags 不生效 → slEvaluateFeature 报 20（eErrorMissingInputParameter）
		if (!frameToken) {
			SKSE::log::warn("[Streamline] slSetTagForFrame skipped (DLSS) - null frameToken");
			return false;
		}
		slSetTagForFrame(*frameToken, viewport, tags, _countof(tags), a_ctx);

		sl::ViewportHandle view(viewport);
		const sl::BaseStructure* inputs[] = { &view };

		if (SL_FAILED(r, slEvaluateFeature(sl::kFeatureDLSS, *frameToken, inputs, _countof(inputs), a_ctx))) {
			SKSE::log::error("[Streamline] slEvaluateFeature failed: {}", (int)r);
			return false;
		}
		return true;
	}

	void Streamline::DestroyResources()
	{
		if (!initialized)
			return;
		// 防御：DLSSG 模式下 slDLSSSetOptions 未绑定（null）——不能裸调
		if (slDLSSSetOptions) {
			sl::DLSSOptions opts{};
			opts.mode = sl::DLSSMode::eOff;
			slDLSSSetOptions(viewport, opts);
		}
		if (slFreeResources)
			slFreeResources(useD3D12 ? sl::kFeatureDLSS_G : sl::kFeatureDLSS, viewport);
		if (slShutdown)
			slShutdown();
	}
}
