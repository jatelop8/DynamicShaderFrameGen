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

#include <detours/detours.h>

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
		// v0.25.4（Bug2 修复）：v0.25 已移除 DLSS-NR（NGXNR）并删除 sl.dlss_nr.dll，
		// 但这里还残留 featuresNR（含 1004 NR feature）——provider=1（DLSSG）用它 →
		// slInit 尝试加载 NR 插件（DLL 不存在）→ slInit 失败 → Streamline 未初始化 →
		// DLSSG 打不开（"FSR 切 DLSS 后打不开"实锤）。DLSSG 统一用 featuresDLSSG。
		// 注：kFeatureDirectSR=1003、NvPerf=1002、DLSS_RR=1001、DLSS_G=1000——
		// 1004 是 NR 的相邻新枚举（dlss5-dx11-bridge 同源 SDK 版本验证），已随 NR 移除。
		// v0.24.2：恢复 D3D11 DLSS 超分——v0.8.20 为 NR 验证强制 D3D12，导致
		// EvaluateDLSS 跳过、DLSS feature 永不创建 → bridge（DLSS5 外挂 ReShade）
		// 拦不到 CreateFeature → NR 无输入失效（用户实测 00:52）。
		// provider=0（FSR3）→ D3D11 会话（DLSS 超分可用，bridge 可拦）；
		// provider=1（DLSSG）→ D3D12（DLSSG 需要 D3D12）。
		useD3D12 = a_settings.provider == 1;
		pref.featuresToLoad = useD3D12 ? featuresDLSSG : featuresDLSS;
		pref.numFeaturesToLoad = useD3D12 ? _countof(featuresDLSSG) : _countof(featuresDLSS);

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
		slSetFeatureLoaded = reinterpret_cast<PFun_slSetFeatureLoaded*>(GetProcAddress(interposer, "slSetFeatureLoaded"));  // v0.32
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
			// v0.31（对齐 open-shaders Streamline.cpp:300-320）：slDLSSGGetState 查询
			// 硬件多倍帧生成上限（numFramesToGenerateMax）——RTX 50 系支持 2-3 倍
			slGetFeatureFunction(sl::kFeatureDLSS_G, "slDLSSGGetState", reinterpret_cast<void*&>(slDLSSGGetState));
			// v0.32（对齐 open-shaders BindReflexAndPCL）：Reflex/PCL 可用性在设备
			// 绑定后可能变化 → 显式请求加载 + 绑定 slReflexSleep（RSYNC 必需）。
			// SL 日志 "Plugin 'sl.reflex' has no registered hooks" = Reflex 未激活
			// → RSYNC pacing 无同步 → 插帧频闪。此前只绑 slReflexSetOptions，漏 sleep。
			if (slSetFeatureLoaded) {
				slSetFeatureLoaded(sl::kFeatureReflex, true);
				slSetFeatureLoaded(sl::kFeaturePCL, true);
			}
			slGetFeatureFunction(sl::kFeatureReflex, "slReflexSetOptions", reinterpret_cast<void*&>(slReflexSetOptions));
			slGetFeatureFunction(sl::kFeatureReflex, "slReflexSleep", reinterpret_cast<void*&>(slReflexSleep));
			featureReflex = slReflexSetOptions && slReflexSleep;
			slGetFeatureFunction(sl::kFeaturePCL, "slPCLSetMarker", reinterpret_cast<void*&>(slPCLSetMarker));
			featurePCL = slPCLSetMarker != nullptr;
			// v0.5.23：PCL marker 从 interposer 导出加载（RSYNC 依赖）
			if (!slPCLSetMarker)
				slPCLSetMarker = reinterpret_cast<PFun_slPCLSetMarker*>(GetProcAddress(interposer, "slPCLSetMarker"));
			SKSE::log::info("[Streamline] DLSSG/Reflex functions bound (reflex={} pcl={})", featureReflex, featurePCL);

			// v0.45：多倍帧生成上限查询（原生，不再 hook/骗上限）。50 系（Blackwell）
			// 原生 numFramesToGenerateMax=3（支持 4x）；40 系（Ada）锁 1（只能 2x）。
			// numFramesToGenerate 由 SetDLSSGOptions 按此上限 clamp（50 系可选 4x）。
			// v0.50：MFG 上限覆盖——驱动把 Ada 及更早架构的 numFramesToGenerateMax 锁 1。
			// INI MFGMaxFramesOverride>0 时把上报上限抬到该值，让高倍率请求真正下发。
			// 前提：外部内核解锁器（DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge）
			// 已提供该架构的内核；否则请求的倍率无内核可执行。
			if (slDLSSGGetState) {
				sl::DLSSGState state{};
				if (SL_FAILED(r, slDLSSGGetState(viewport, state, nullptr))) {
					SKSE::log::warn("[Streamline] slDLSSGGetState failed querying numFramesToGenerateMax: {}", (int)r);
					dlssgMaxFramesToGenerate = 1;
				} else {
					const std::uint32_t hwMax = std::max<std::uint32_t>(1, state.numFramesToGenerateMax);
					dlssgMaxFramesToGenerate = hwMax;
					SKSE::log::info("[Streamline] DLSS-G supports up to {}x frame generation ({} interpolated frames per real frame)",
						hwMax + 1, hwMax);
					ApplyMfgOverride(hwMax);
				}
			}
		}
	}

	// v0.50：MFG 上限覆盖 + 能力守卫。
	// 动机：驱动/运行时把 Ada 及更早架构的 numFramesToGenerateMax 锁在 1（只能 2x）。
	// 外部内核解锁器（DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge）能补上内核，
	// 但本插件仍按硬件上报的 1 去 clamp -> 高倍率永远下发不出去。此函数在探测到
	// 覆盖配置时抬高上报上限，使 SetDLSSGOptions 真正请求 >1 个插帧。
	// 安全：覆盖值超过原生上限时只抬上限、不改 fallback；一旦运行时失败由调用方退回。
	void Streamline::ApplyMfgOverride(std::uint32_t a_hwMax)
	{
		const std::uint32_t want = Get().settings.mfgMaxFramesOverride;
		dlssgEffectiveMax = std::max<std::uint32_t>(1, a_hwMax);   // v0.51：默认 = 运行时上限
		if (want == 0) {
			SKSE::log::info("[Streamline] MFG override disabled (INI MFGMaxFramesOverride=0) - hardware max {}x", a_hwMax + 1);
			return;
		}
		const std::uint32_t clamped = std::clamp<std::uint32_t>(want, 1u, 5u);
		if (clamped <= a_hwMax) {
			SKSE::log::info("[Streamline] MFG override {} <= hardware max {} - no change needed", clamped, a_hwMax);
			return;
		}
		// v0.51：只抬高**请求**上限，不改 dlssgMaxFramesToGenerate（那是运行时上报的真值）。
		// 运行时仍会用自己的能力校验，被拒时由 SetDLSSGOptions 的阶梯探测逐级下探。
		dlssgEffectiveMax = clamped;
		SKSE::log::warn("[Streamline] MFG override REQUEST: will ask the runtime for {}x (runtime reports {}x). "
			"The runtime will REJECT this unless an external MFG kernel unlocker "
			"(DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge) is installed; the ladder probe in "
			"SetDLSSGOptions steps back down to whatever the runtime actually accepts.",
			clamped + 1, a_hwMax + 1);
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
		// v0.25.4：SL_FAILED(r, r) 的第二个 r 遮蔽局部变量（C4456）——宏第一个参数
		// 是输出、第二个是调用；这里直接判断返回值
		if (r != sl::Result::eOk)
			SKSE::log::error("[Streamline] slUpgradeInterface failed: {}", (int)r);
		else
			SKSE::log::info("[Streamline] Interface upgraded (presentCommon path active)");
	}

	// v0.37（对齐 open-shaders EnsureFrameToken:411-426）：每帧统一 frame token。
	// 本帧第一次调用 → slGetNewFrameToken（帧号推进）；同帧后续调用 → 复用已有
	// token（IsNewFrame 判断）。所有 PCL marker/ReflexSleep/SetTag 必须用同一帧
	// token——之前 ReflexSleep/marker 用旧 token（上一帧）、EvaluateDLSSG 才取新
	// token → 同一帧 marker 跨两个 token → RSYNC 帧节奏标记错位 → pacing 乱 → 频闪。
	// v0.37b（审查修正）：IsNewFrame 必须用**引擎帧号**判断（每帧不变）——之前用
	// 内部递增计数器，第二次调用时已 +1 → 误判"新帧" → 每帧取两次 token（SL
	// "Repeated" 警告回归）。引擎帧号由 OnMainUpdateJitter 更新到 engineFrameCount。
	bool Streamline::EnsureFrameToken()
	{
		if (!initialized || !slGetNewFrameToken)
			return false;
		static std::uint32_t s_lastFrame = UINT32_MAX;
		const std::uint32_t frame = Get().engineFrameCount;
		if (frame == s_lastFrame)  // 同帧 → 复用已有 token
			return frameToken != nullptr;
		s_lastFrame = frame;
		frameToken = nullptr;
		if (SL_FAILED(r, slGetNewFrameToken(frameToken, &frame))) {
			SKSE::log::error("[Streamline] slGetNewFrameToken failed: {}", (int)r);
			return false;
		}
		return frameToken != nullptr;
	}

	void Streamline::CheckFrameConstants(const FrameBuffer& a_fb, float a_aspect, float a_near, float a_far)
	{
		if (!initialized)
			return;

		// v0.5：frameToken 失败保护（失败 → 置空 → 调用方跳过本帧 SL 调用，防空指针解引用）
		// v0.31：slGetNewFrameToken 必须传帧计数（nullptr → 帧号停滞 "frame 1"）。
		// v0.37：统一走 EnsureFrameToken（每帧一次，同帧复用）。
		if (!EnsureFrameToken())
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

		// v0.56 probe: DLSS-G reprojects each generated frame with clipToPrevClip.
		// Transfusion's log shows clipToPrev=identity for the first frames of the run,
		// which is correct on a loading screen but catastrophic during gameplay - an
		// identity matrix tells DLSS-G the camera never moved, so the camera part of
		// the reprojection is silently dropped. This settles which it is: run, walk
		// around, and read maxDevFromIdentity. Near 0 while moving = the matrix is not
		// live and the previous view-projection is not being updated.
		{
			static std::uint32_t motionProbe = 0;
			if (++motionProbe % 600 == 1) {
				float dev = 0.0f;
				for (int row = 0; row < 4; ++row) {
					const sl::float4 r = c.clipToPrevClip[row];
					const float v[4] = { r.x, r.y, r.z, r.w };
					for (int col = 0; col < 4; ++col) {
						const float id = (row == col) ? 1.0f : 0.0f;
						const float d = v[col] - id;
						const float a = d < 0.0f ? -d : d;
						if (a > dev)
							dev = a;
					}
				}
				const sl::float4 r3 = c.clipToPrevClip[3];
				SKSE::log::info("[Streamline] MOTION probe: clipToPrevClip maxDevFromIdentity={:.6f} "
					"r3=({:.5f} {:.5f} {:.5f}) - ~0 while the player is moving means the camera "
					"matrix is NOT live (DLSS-G loses camera reprojection)",
					dev, r3.x, r3.y, r3.z);
			}
		}

		c.jitterOffset = { -Get().jitterX, -Get().jitterY };  // v0.34：DLSS Halton jitter（对齐 CS，之前恒 0）
		// v0.34（对齐 CS Streamline.cpp:484-488）：菜单打开时运动矢量无效 → reset 让
		// DLSSG 不用旧数据插帧（用户"停在菜单背景"——菜单帧插错 = 视觉错乱）。
		// 菜单检测：主菜单/加载菜单/暂停菜单（BGSM 菜单 UI 绘制时无运动矢量）。
		c.reset = sl::Boolean::eFalse;
		if (auto* ui = RE::UI::GetSingleton()) {
			const auto* istrings = RE::InterfaceStrings::GetSingleton();
			if (ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||
				ui->IsMenuOpen(istrings->journalMenu) || ui->IsMenuOpen("PauseMenu"))
				c.reset = sl::Boolean::eTrue;
		}
		// v0.49k（修重影）：真超分（DRS）下引擎 TAA 生成 mvec 用 screenSize(2560) 常量
		// 算 UV（不随 DRS viewport 缩放，Skyrim DRS 只缩 viewport 不缩 screenSize），而
		// DLSS 期望 mvec 归一化基准是渲染分辨率(1706)。引擎 mvec=位移/2560，DLSS 期望
		// 位移/1706 → 差 1/renderScale 倍，需放大补偿，否则 temporal 重投影错 → 重影。
		// v0.57: the 1/renderScale compensation below is the ONE value in this file
		// that both the field's own definition and the reference implementation
		// disagree with, and it is fed to DLSS-G every frame - a wrong value puts
		// wrong motion into every generated frame.
		//
		//   sl_consts.h: "scale factors used to normalize motion vectors (so the
		//   values are in [-1,1] range)"
		//   ProgrammingGuideDLSS_G.md: "values in {-1,1} range -> scale factor
		//   should be {1,1}"; not in range -> "adjusted so that values end up in
		//   [-1,1] range"
		//   open-shaders Streamline.cpp: "The standard full-frame DLSS path ...
		//   must keep mvecScale at identity or DLSS massively over-estimates motion"
		//
		// The v0.49k comment states its own premise - "engine mvec = displacement/2560"
		// - and a value reaching 1.0 for a full-screen pan is already inside [-1,1],
		// so that premise argues for identity. But 1.5 was tuned in-game against a
		// different defect (the depth/mvec extent that v0.56 removed), so it is not
		// discarded on inference alone: it becomes one INI line, defaulted to the old
		// behaviour, so the A/B costs no rebuild.
		{
			const auto& sc = Get().dx12SwapChain;
			const float ov = Get().settings.mvecScaleOverride;
			const float mvsX = (ov > 0.0f) ? ov : (1.0f / sc.renderScaleX);
			const float mvsY = (ov > 0.0f) ? ov : (1.0f / sc.renderScaleY);
			c.mvecScale = { mvsX, mvsY };
			static bool mvecScaleLogged = false;
			if (!mvecScaleLogged) {
				mvecScaleLogged = true;
				SKSE::log::info("[Streamline] mvecScale = {{ {:.4f}, {:.4f} }} "
					"(renderScale={:.4f} override={:.2f}) - 1.0 means already in [-1,1]",
					mvsX, mvsY, sc.renderScaleX, ov);
			}
		}
		c.motionVectors3D = sl::Boolean::eFalse;
		c.motionVectorsInvalidValue = FLT_MIN;
		c.orthographicProjection = sl::Boolean::eFalse;
		c.motionVectorsDilated = sl::Boolean::eFalse;
		c.motionVectorsJittered = sl::Boolean::eFalse;
		c.depthInverted = sl::Boolean::eFalse;

		if (SL_FAILED(r, slSetConstants(c, *frameToken, viewport)))
			SKSE::log::error("[Streamline] slSetConstants failed: {}", (int)r);
	}

	// v0.3：DLSSG 插帧（D3D12 路径）——设置选项（多倍帧生成 clamp 到硬件上限）
	void Streamline::SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,
		std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat)
	{
		if (!initialized || !featureDLSSG || !slDLSSGSetOptions)
			return;
		sl::DLSSGOptions opts{};
		opts.mode = sl::DLSSGMode::eOn;
		// v0.31（对齐 open-shaders ConfigureDLSSG）：多倍帧生成——
		// numFramesToGenerate = clamp(INI DLSSGFramesToGenerate, 1, 硬件上限)。
		// v0.50 上限：effectiveMax = max(硬件上限, 覆盖值)。
		// overrides==0 -> 完全跟随硬件上报（50 系仍可 4X，零功能倒退）；
		// overrides>0 -> 抬到覆盖值（老卡解锁路径，由外部内核解锁器提供内核）。
		const std::uint32_t effectiveMax = std::max<std::uint32_t>(1, dlssgEffectiveMax);
		// v0.51：阶梯探测——首帧按配置请高倍率，被拒就下一帧降一档，直到运行时接受（锁定）
		// 或降到 1（说明该架构没有可用内核）。绝不把"请求"当"生效"。
		if (mfgProbeStep == 0 || mfgProbeStep > effectiveMax)
			mfgProbeStep = std::clamp<std::uint32_t>(Get().settings.dlssgFramesToGenerate, 1, effectiveMax);
		dlssgFramesToGenerate = mfgProbeStep;   // = 本次请求值（是否被接受见下方结果处理）
		opts.numFramesToGenerate = dlssgFramesToGenerate;  // 1=2x 2=3x 3=4x 插帧
		opts.numBackBuffers = 3;
		opts.colorWidth = a_width;
		opts.colorHeight = a_height;
		// v0.56 (fix: declared != actual). sl_dlss_g.h defines mvecDepthWidth/Height as
		// "Expected width/height of the input render targets (depth, motion-vector
		// buffers etc)" - the size of THOSE buffers, not the swap chain. The caller
		// passed swapChainDesc, which agrees with the lazy-created interop textures
		// (2560x1440) but would NOT agree if CreateInterop's eager path had won (it
		// reads the engine kMAIN desc = render resolution). Derive both from the
		// resource that is actually handed to DLSS-G so they cannot drift apart.
		std::uint32_t mvecDepthW = a_mvecDepthW;
		std::uint32_t mvecDepthH = a_mvecDepthH;
		{
			auto& dx = Get().dx12SwapChain;
			WrappedResource* mvSrc = (dx.depthWrapped && dx.depthWrapped->resource11)
				? dx.depthWrapped
				: dx.mvecWrapped;
			if (mvSrc && mvSrc->resource11) {
				D3D11_TEXTURE2D_DESC rd{};
				mvSrc->resource11->GetDesc(&rd);
				mvecDepthW = rd.Width;
				mvecDepthH = rd.Height;
			}
		}
		opts.mvecDepthWidth = mvecDepthW;
		opts.mvecDepthHeight = mvecDepthH;
		{
			static bool optDimsLogged = false;
			if (!optDimsLogged) {
				optDimsLogged = true;
				SKSE::log::info("[Streamline] DLSSG options dims: color={}x{} mvecDepth={}x{} "
					"(mvecDepth must equal the real depth/MV interop buffers)",
					a_width, a_height, mvecDepthW, mvecDepthH);
			}
		}
		opts.colorBufferFormat = static_cast<std::uint32_t>(a_colorFormat);
		opts.hudLessBufferFormat = static_cast<std::uint32_t>(a_colorFormat);
		if (auto* renderer = RE::BSGraphics::Renderer::GetSingleton()) {
			auto& mvecTex = renderer->GetRuntimeData().renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
			if (mvecTex.texture) {
				D3D11_TEXTURE2D_DESC d{};
				static_cast<ID3D11Texture2D*>(mvecTex.texture)->GetDesc(&d);
				opts.mvecBufferFormat = static_cast<std::uint32_t>(d.Format);
			}
		}
		opts.depthBufferFormat = static_cast<std::uint32_t>(DXGI_FORMAT_R32_FLOAT);
		opts.enableUserInterfaceRecomposition = sl::Boolean::eFalse;
		// v0.51：处理结果——接受则锁定，被拒则降档。原实现只打一条 error 就继续，
		// 于是每帧都按被拒的倍率呈现（6671 条/场，画面频闪）。
		// v0.51b：必须自己声明——原 SL_FAILED(r,...) 宏会声明 r，改成裸赋值后 r 未声明；
		// 用独立名字避免与下方 line 466 处 SL_FAILED 再次声明 r 造成的遮蔽。
		const sl::Result setOptRes = slDLSSGSetOptions(viewport, opts);
		if (setOptRes == sl::Result::eOk) {
			if (!mfgProbeLatched || dlssgAcceptedFrames != mfgProbeStep) {
				SKSE::log::info("[Streamline] MFG probe: runtime ACCEPTED {}x ({} interpolated frames) | "
					"runtimeReportsMax={}x overrideAsksMax={}x",
					mfgProbeStep + 1, mfgProbeStep, dlssgMaxFramesToGenerate + 1, effectiveMax + 1);
			}
			mfgProbeLatched = true;
			dlssgAcceptedFrames = mfgProbeStep;
		} else {
			dlssgAcceptedFrames = 0;
			const std::uint32_t rejected = mfgProbeStep;
			if (mfgProbeStep > 1) {
				mfgProbeStep--;
				static std::uint32_t lastRejectedStep = 0xFFFFFFFFu;
				if (lastRejectedStep != rejected) {
					lastRejectedStep = rejected;
					SKSE::log::warn("[Streamline] MFG probe: runtime REJECTED {}x (result {} = eErrorInvalidState) "
						"-> retrying at {}x next frame", rejected + 1, (int)setOptRes, mfgProbeStep + 1);
				}
			} else {
				static bool loggedFloor = false;
				if (!loggedFloor) {
					loggedFloor = true;
					SKSE::log::error("[Streamline] MFG probe: runtime rejects even 2x (result {}). No usable DLSS-G "
						"kernel for this adapter -> set Provider=0 (FSR3 2x) until an MFG unlocker is installed.",
						(int)setOptRes);
				}
			}
		}

		if (slDLSSGGetState) {
			sl::DLSSGState state{};
			if (SL_FAILED(r, slDLSSGGetState(viewport, state, &opts))) {
				static int stateFail = 0;
				if (++stateFail % 60 == 1)
					SKSE::log::warn("[Streamline] slDLSSGGetState failed {} times: {}", stateFail, (int)r);
			} else {
				static sl::DLSSGStatus lastStatus = sl::DLSSGStatus::eOk;
				static std::uint32_t lastFrames = 0;
				if (state.status != lastStatus || (state.status != sl::DLSSGStatus::eOk && state.numFramesActuallyPresented == lastFrames)) {
					lastStatus = state.status;
					lastFrames = state.numFramesActuallyPresented;
					SKSE::log::info("[Streamline] DLSSG state: status={} framesPresented={}",
						static_cast<int>(state.status), state.numFramesActuallyPresented);
				}
				// v0.53: publish the runtime's own measurement. numFramesActuallyPresented counts
				// frames presented since the PREVIOUS slDLSSGGetState call, and this function runs
				// once per real frame - so the value is the effective multiplier of that frame.
				// 1 means no interpolation happened at all, whatever we asked for. The overlay uses
				// it, and the periodic line below is the evidence that MFG really runs (or not).
				dlssgFramesPresentedLast = state.numFramesActuallyPresented;
				static std::uint32_t presentedLog = 0;
				static std::uint32_t lastPresentedLogged = 0xFFFFFFFFu;
				static std::uint32_t presentedChanges = 0;
				++presentedLog;
				// v0.55: sample early AND on every change. The old '% 240 == 1' interval needed
				// ~6s of play before the first reading - longer than the debug sessions we have,
				// so the value was never actually measured. A 1 -> 4 transition, or a 1/4
				// oscillation (what two pacers fighting over one swap chain looks like), now
				// shows up within a single frame. Instrumentation only - no behaviour change.
				const bool presentedChanged = (dlssgFramesPresentedLast != lastPresentedLogged);
				if (presentedLog <= 8 || (presentedChanged && presentedChanges < 200) || presentedLog % 300 == 0) {
					if (presentedChanged) { lastPresentedLogged = dlssgFramesPresentedLast; ++presentedChanges; }
					SKSE::log::info("[Streamline] DLSSG presented per real frame = {} (status={}) - 1 means NO interpolation",
						dlssgFramesPresentedLast, static_cast<int>(state.status));
				}
				if (state.status != sl::DLSSGStatus::eOk && state.status != lastStatus) {
					lastStatus = state.status;
					SKSE::log::warn("[Streamline] DLSS-G not generating frames this session: status={}", static_cast<int>(state.status));
				}
			}
		}
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

		// v0.25.3（用户 2026-08-30"勾选 DLSSG 没生效"——16:35 日志实锤）：**DLSS-G
		// 不做显式 slAllocateResources / slEvaluateFeature**——与 CS 完全一致（CS 只对
		// kFeatureDLSS 超分调 slEvaluateFeature，对 DLSS_G 从不调）：
		//   1. sl.dlss_g 插件的 evaluateFeature 回调恒 0x0（正常）——DLSSG 通过
		//      Present 钩子（slHookPresent/slHookPresent1，已注册 OK）在 presentCommon
		//      时自动插帧（16:35 presentCommon 每帧在跑 = 链已通）
		//   2. 显式 slEvaluateFeature(DLSS_G) 恒 28（eErrorMissingOrInvalidAPI）→
		//      触发上方 auto-disable（>120 次）→ 帧生成被自己禁用 → "没效果"
		//   3. 显式 slAllocateResources 失败 -572052636——DLSSG 的资源由 Present
		//      钩子路径自动分配（sl.dlss_g 有 slAllocateResources 回调 0x7ffd...）
		//   我们只负责：setConstants + slSetTagForFrame 标记资源（Present 钩子消费）。
		//   若 tag 失败（frameToken null）→ 返回 false 走 passthrough 兜底。

		sl::Resource colorInRes = { sl::ResourceType::eTex2d, a_colorIn, 0 };
		sl::Resource colorOutRes = { sl::ResourceType::eTex2d, a_colorOut, 0 };
		sl::Resource depthRes = { sl::ResourceType::eTex2d, a_depth, 0 };
		sl::Resource mvecRes = { sl::ResourceType::eTex2d, a_motionVectors, 0 };

		const std::uint32_t w = fg.dx12SwapChain.swapChainDesc.Width;
		const std::uint32_t h = fg.dx12SwapChain.swapChainDesc.Height;
		// v0.56 (flicker root cause, proven). sl.h defines ResourceTag::extent as
		// "The area of the tagged resource to use (if using the entire resource leave
		// as null)". Declaring 1706x960 therefore told DLSS-G to use only the top-left
		// 1706x960 of a 2560x1440 buffer - a 1.5x spatial mismatch against a colour
		// buffer of 2560x1440, which corrupts the motion input of EVERY generated
		// frame. The old renderExtent dates from v0.34, when the interop textures were
		// still render resolution; v0.7.8 resized them to the output resolution and
		// the tag was never updated (Transfusion's MOTION-TAG log in the 16:34 run
		// shows exactly this: hudless/scaling-output 2560x1440, depth/motion 1706x960).
		// Take the extent from the resource itself - correct by construction.
		const D3D12_RESOURCE_DESC depthDesc = a_depth->GetDesc();
		const D3D12_RESOURCE_DESC mvecDesc = a_motionVectors->GetDesc();
		sl::Extent extent{ 0, 0, w, h };
		sl::Extent depthExtent{ 0, 0,
			static_cast<std::uint32_t>(depthDesc.Width), static_cast<std::uint32_t>(depthDesc.Height) };
		sl::Extent mvecExtent{ 0, 0,
			static_cast<std::uint32_t>(mvecDesc.Width), static_cast<std::uint32_t>(mvecDesc.Height) };
		sl::ResourceTag tags[] = {
			{ &colorInRes, sl::kBufferTypeHUDLessColor, sl::ResourceLifecycle::eOnlyValidNow, &extent },
			{ &colorOutRes, sl::kBufferTypeScalingOutputColor, sl::ResourceLifecycle::eOnlyValidNow, &extent },
			{ &depthRes, sl::kBufferTypeDepth, sl::ResourceLifecycle::eValidUntilPresent, &depthExtent },
			{ &mvecRes, sl::kBufferTypeMotionVectors, sl::ResourceLifecycle::eValidUntilPresent, &mvecExtent },
		};
		{
			static bool tagDimsLogged = false;
			if (!tagDimsLogged) {
				tagDimsLogged = true;
				SKSE::log::info("[Streamline] DLSSG tag dims: hudless/scaling-output={}x{} depth={}x{} mvec={}x{} "
					"- depth/mvec must read 2560x1440 (the real interop buffers)",
					extent.width, extent.height, depthExtent.width, depthExtent.height,
					mvecExtent.width, mvecExtent.height);
			}
		}
		// v0.5.11：slSetTagForFrame（frame-based tagging）替代弃用的 slSetTag——
		// 需 eUseFrameBasedResourceTagging flag + frameToken（DLSS-G 指南 306-339 全用此 API）
		if (!frameToken) {
			SKSE::log::error("[Streamline] slSetTagForFrame skipped - null frameToken");
			return false;
		}
		slSetTagForFrame(*frameToken, viewport, tags, _countof(tags), a_cmdList);
		// v0.25.3：DLSSG 评估交给 SL Present 钩子（presentCommon 自动），不再显式
		// slEvaluateFeature——此处仅返回 true 表示"已标记资源"。
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
	// v0.32（对齐 open-shaders Streamline.cpp:890-924）：Reflex sleep + eSimulationStart——
	// 每帧在模拟开始前调用（Present 开头）。slReflexSleep 让 Reflex 引擎建立 RSYNC
	// 节奏（vblank 同步的帧 pacing）；缺失 → sl.reflex 不注册 hooks → RSYNC 无同步
	// → 插帧 pacing 乱 → 频闪（SL 日志 "Plugin 'sl.reflex' has no registered hooks"
	// + dlss_g 每帧 "frame 1" 警告实锤）。返回后发 eSimulationStart（模拟开始）。
	// v0.35（对齐 CS applyReflexOptionsIfChanged:850-900）：**每帧先设置完整
	// ReflexOptions 再 sleep**——useMarkersToOptimize（PCL marker 优化）+ frameLimitUs
	// 是 Reflex 运行时激活的必需；之前只设 mode → DLSSG 运行时检测不到 Reflex →
	// eDLSSGStatusFailReflexNotDetectedAtRuntime（status=2，20:51 日志实锤）→ 插帧
	// 被拒 → 频闪。选项变化才 slReflexSetOptions（缓存比较，CS 同款）。
	void Streamline::ReflexSleep()
	{
		if (!initialized || !slReflexSleep || !featureReflex)
			return;
		if (!frameToken)
			return;

		sl::ReflexOptions opts{};
		opts.mode = sl::ReflexMode::eLowLatency;  // DLSSG 要求至少 eLowLatency
		// v0.54（闪烁根因修复）：渲染帧率上限必须与"显示器刷新率 / 帧生成总倍数"配比。
		// 旧代码写死 opts.frameLimitUs = 1000000/60（从 CS 抄来的 reflexFPSLimit=60），
		// Reflex 会如实把**渲染**帧率压在 60fps。2026-09-17 16:26 实测（2560x1440@160Hz）：
		//   日志 Reflex options applied (frameLimitUs=16666)；perf.csv DeltaMs=17.43(=57.4fps)
		//   且 Multiplier=4 -> present = 57.4 x 4 = 229.6fps 灌进 160Hz 屏 = 超发 43%。
		// present 队列积压 -> SL pacer 节奏崩 -> 画面持续闪烁（fixed 模式不自动降档）。
		// 帧生成只有在"渲染帧率 x 倍数 <= 刷新率"时才成立，故改为按刷新率反推：
		//   自动 = 刷新率 / 总倍数 - 1fps（留余量避免顶到刷新率边缘）
		//   160Hz / 4x -> 39fps 渲染 -> 156 present fps，刚好在面板之下。
		// 倍率优先取运行时**实际接受**值（阶梯探测降档后能自动重算，不会再超发）；
		// 探测 latch 前回退到请求值。INI ReflexFpsLimit>0 时直接用它，跳过自动。
		std::uint32_t capFps = 0;
		std::uint32_t capMult = 1;
		{
			const auto& s = Get().settings;
			if (s.reflexFpsLimit > 0) {
				capFps = static_cast<std::uint32_t>(s.reflexFpsLimit);
			} else if (Get().refreshRate > 0.0) {
				const std::uint32_t mfg = dlssgAcceptedFrames
					? dlssgAcceptedFrames
					: std::max<std::uint32_t>(1u, s.dlssgFramesToGenerate);
				capMult = std::max<std::uint32_t>(1u, mfg + 1u);
				const double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;
				capFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);
			} else {
				// 刷新率读不到时不能再默默写死一个值（旧 60fps 就是这么来的 bug）——
				// 留 0 = 不限帧，并明确告警。
				SKSE::log::warn("[Streamline] Reflex render cap auto: DISABLED (refresh rate unknown) - over-submit is possible");
			}
			opts.frameLimitUs = capFps ? (1000000u / capFps) : 0u;
			static std::uint32_t lastCapFps = 0;
			static std::uint32_t lastCapMult = 0;
			if (capFps != lastCapFps || capMult != lastCapMult) {
				SKSE::log::info("[Streamline] Reflex render cap = {} fps ({}us) - {}Hz / {}x => ~{} present fps{}",
					capFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps * capMult,
					capFps ? "" : "  [UNLIMITED - over-submit possible]");
				lastCapFps = capFps;
				lastCapMult = capMult;
			}
		}
		opts.useMarkersToOptimize = featurePCL;   // PCL marker 优化（Reflex 激活必需）

		// 缓存比较：选项变化才下发（CS applyReflexOptionsIfChanged 同款）
		static sl::ReflexOptions lastOpts{};
		static bool lastValid = false;
		if (!lastValid || std::memcmp(&lastOpts, &opts, sizeof(opts)) != 0) {
			if (SL_FAILED(r, slReflexSetOptions(opts)))
				SKSE::log::warn("[Streamline] slReflexSetOptions failed: {}", (int)r);
			else
				SKSE::log::info("[Streamline] Reflex options applied (mode={} frameLimitUs={} markers={})",
					static_cast<int>(opts.mode), opts.frameLimitUs, opts.useMarkersToOptimize);
			lastOpts = opts;
			lastValid = true;
		}

		if (SL_FAILED(r, slReflexSleep(*frameToken)))
			SKSE::log::warn("[Streamline] slReflexSleep failed: {}", (int)r);
		if (slPCLSetMarker)
			slPCLSetMarker(sl::PCLMarker::eSimulationStart, *frameToken);
	}

	void Streamline::PresentMarkerSimulationEnd()
	{
		if (!initialized || !slPCLSetMarker || !frameToken)
			return;
		slPCLSetMarker(sl::PCLMarker::eSimulationEnd, *frameToken);
	}

	void Streamline::PresentMarkerRenderStart()
	{
		if (!initialized || !slPCLSetMarker || !frameToken)
			return;
		slPCLSetMarker(sl::PCLMarker::eRenderSubmitStart, *frameToken);
	}

	void Streamline::PresentMarkerRenderEnd()
	{
		if (!initialized || !slPCLSetMarker || !frameToken)
			return;
		slPCLSetMarker(sl::PCLMarker::eRenderSubmitEnd, *frameToken);
	}

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
