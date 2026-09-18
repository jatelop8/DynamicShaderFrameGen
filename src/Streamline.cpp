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

#include <chrono>

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
		// [DLSS_G, Reflex] 时日志 “kFeatureDLSS' context is missing” + Callback 0x0）
		sl::Feature featuresDLSSG[] = { sl::kFeatureDLSS, sl::kFeatureDLSS_G, sl::kFeatureReflex };
		// v0.25.4（Bug2 修复）：v0.25 已移除 DLSS-NR（NGXNR）并删除 sl.dlss_nr.dll，
		// 但这里还残留 featuresNR（含 1004 NR feature）——provider=1（DLSSG）用它 →
		// slInit 尝试加载 NR 插件（DLL 不存在）→ slInit 失败 → Streamline 未初始化 →
		// DLSSG 打不开（“FSR 切 DLSS 后打不开”实锤）。DLSSG 统一用 featuresDLSSG。
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
			// SL 日志 “Plugin 'sl.reflex' has no registered hooks” = Reflex 未激活
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
		// v1.03: publish the two numbers the heartbeat and the watchdog need.
		// hwMaxSeen is the truth; reqStepMax is what we allow ourselves to ask
		// for. When reqStepMax > hwMaxSeen without a kernel unlocker behind it,
		// the ladder pays one enormous rejected frame per rung - see the guard
		// below and the 18:23 log (4x rejected, 3x rejected, LONG FRAME 19945 ms).
		diag.hwMaxSeen = a_hwMax;
		if (want == 0) {
			dlssgEffectiveMax = std::max<std::uint32_t>(1, a_hwMax);
			diag.reqStepMax = dlssgEffectiveMax;
			SKSE::log::info("[Streamline] MFG override disabled (INI MFGMaxFramesOverride=0) - hardware max {}x", a_hwMax + 1);
			return;
		}
		const std::uint32_t clamped = std::clamp<std::uint32_t>(want, 1u, 5u);
		if (clamped <= a_hwMax) {
			diag.reqStepMax = std::max<std::uint32_t>(1, a_hwMax);
			SKSE::log::info("[Streamline] MFG override {} <= hardware max {} - no change needed", clamped, a_hwMax);
			return;
		}
		// v1.03 CAPABILITY GUARD -------------------------------------------------
		// v0.51 raised the request ceiling on the assumption that "the runtime
		// will reject it and the ladder steps back down". The 18:23 log shows
		// what that costs: the descent is one rung per FRAME and each rejected
		// rung burned seconds (LONG FRAME 19945.3 ms), so the feature spent its
		// whole startup walking down from a ceiling that was never reachable.
		//
		// The ceiling the runtime will actually honour is not a guess: it is
		// numFramesToGenerateMax, which slDLSSGGetState already returned and
		// which ApplyMfgOverride receives as a_hwMax. Raising our own request
		// above it can only be justified when something OUTSIDE this process has
		// added kernels for the extra multipliers - the external unlockers
		// (DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge). Absent that proof,
		// asking above the report is asking for a known rejection.
		//
		// Detection is by loaded module name, which is the same evidence the
		// user has: Transfusion ships as dinput8.dll in the game folder and the
		// others are named after themselves. A miss here costs performance (the
		// ladder walks down from the ceiling again, exactly as before), never
		// correctness - so the conservative branch is the safe default.
		const bool kernelUnlocker =
			GetModuleHandleA("dinput8.dll") != nullptr ||
			GetModuleHandleA("dlssg_for_sm86.dll") != nullptr ||
			GetModuleHandleA("dlssg_for_sm89.dll") != nullptr ||
			GetModuleHandleA("DLSSG_MFG_Bridge.dll") != nullptr;
		// v1.03: an unlocker does not merely justify a higher request - it is a
		// BETTER writer of it than this plugin. Transfusion installs its own
		// slDLSSGSetOptions through slGetFeatureFunction, so whatever this plugin
		// asks for is re-written by Transfusion anyway; the only thing two
		// writers achieve is a rejected request and a multi-second frame. Hand
		// the multiplier over and keep doing the work only this plugin does.
		// v1.05: kernelUnlocker no longer gates anything this plugin does - it only
		// selects which ceiling the block below applies. See the comment there.
		if (!kernelUnlocker) {
			diag.reqStepMax = std::max<std::uint32_t>(1, a_hwMax);
			diag.mfgRungsSkipped += static_cast<std::uint64_t>(clamped - a_hwMax);
			SKSE::log::warn("[Streamline] MFG override {}x REFUSED by the capability guard: the runtime "
				"reports a ceiling of {}x and no external MFG kernel unlocker is loaded, so asking higher "
				"would only buy one rejected multi-second frame per rung (the 18:23 run spent 4x and 3x "
				"on rejections). Staying at the runtime ceiling. To really request {}x, install an "
				"unlocker (DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge).",
				clamped + 1, a_hwMax + 1, clamped + 1);
			return;
		}
		// v1.05: an external unlocker is present, so the REPORTED ceiling is not
		// the real one. numFramesToGenerateMax is what the runtime advertises with
		// its stock kernels; the unlocker exists precisely to add kernels for the
		// higher multipliers, and until those are installed the report stays at the
		// stock value. Transfusion's own log proves the report is a report and not
		// a wall: "Applied fixed multiplier: 4x, result=0 (eOk)" on this same Ada
		// card, followed by "DLSS-G actual presentation count: 4x".
		//
		// v1.03 got this backwards. It saw the unlocker and then clamped OUR ceiling
		// DOWN to the stock report, on the theory that the unlocker writes the value
		// anyway. Two things went wrong with that: (a) the unlocker is a WRAPPER
		// around slDLSSGSetOptions - whatever it does not set stays at whatever the
		// caller left in the struct, so "the unlocker writes it" is only true for the
		// fields it chooses to touch; (b) our own ladder, whose entire job is to find
		// the highest accepted multiplier, was capped BELOW the value the user asked
		// for, so it could never even attempt 4x.
		//
		// v1.05 restores the pre-v1.03 contract: WITH an unlocker the ceiling is the
		// INI override, so a real 4x is attemptable; WITHOUT one it is the runtime
		// report, so a known rejection is never requested. The ladder still steps up
		// only on observed acceptance, so a failed attempt costs one rung, not the
		// session.
		dlssgEffectiveMax = std::max<std::uint32_t>(1, std::max<std::uint32_t>(a_hwMax, clamped));
		diag.reqStepMax = dlssgEffectiveMax;
		SKSE::log::warn("[Streamline] MFG unlocker detected: raising this plugin's request ceiling "
			"from the reported {}x to the INI override {}x. The runtime report is the stock-kernel "
			"ceiling - the unlocker adds the kernels that make the higher multiplier real. This "
			"plugin keeps writing numFramesToGenerate and keeps rebuilding the previous camera.",
			a_hwMax + 1, clamped + 1);
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
	// 内部递增计数器，第二次调用时已 +1 → 误判“新帧” → 每帧取两次 token（SL
	// “Repeated” 警告回归）。引擎帧号由 OnMainUpdateJitter 更新到 engineFrameCount。
	bool Streamline::EnsureFrameToken()
	{
		if (!initialized || !slGetNewFrameToken)
			return false;
		static std::uint32_t s_lastFrame = UINT32_MAX;
		// v0.58: judge on frameSerial (advanced once per Present). engineFrameCount
		// has had no writer since v0.50 -> always equal -> never took a new token.
		const std::uint32_t frame = frameSerial;
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

	namespace
	{
		// v0.61: single definition of “a game menu is up”. CheckFrameConstants uses
		// it for the reset edge AND for the menu/world counters, so the two can
		// never disagree. Same menu set v0.34 established: the menus the engine
		// draws without valid motion vectors.
		// v0.69: literal-name fallback. The original body only consulted
		// InterfaceStrings (mainMenu/loadingMenu/journalMenu). That path has a
		// silent failure mode: InterfaceStrings is a VERSION-DEPENDENT struct
		// layout, so if the compile-time branch does not match the running game the
		// member you read is a different field, IsMenuOpen(garbage) is false, and
		// nothing anywhere reports an error. Evidence it failed: the 22:42 run held
		// menuOpen=0 through a full 45 s of main menu, and this run held menu=0 /
		// menuEdges=0 for all 151 frames. Skyrim's menu names are fixed strings, so
		// look them up by literal too and accept either hit.
		bool GameMenuOpenNow()
		{
			auto* ui = RE::UI::GetSingleton();
			if (!ui)
				return false;
			const auto* istrings = RE::InterfaceStrings::GetSingleton();
			if (istrings &&
				(ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||
					ui->IsMenuOpen(istrings->journalMenu))) {
				return true;
			}
			return ui->IsMenuOpen("Main Menu") || ui->IsMenuOpen("Loading Menu") ||
				ui->IsMenuOpen("Journal Menu") || ui->IsMenuOpen("Pause Menu") ||
				ui->IsMenuOpen("RaceSex Menu") || ui->IsMenuOpen("Fader Menu");
		}

		// v0.69: MENU PROBE -- make the probe itself falsifiable. Compares the data
		// POINTERS only (it never dereferences a member we do not already trust), so
		// it cannot crash even when the layout is wrong. How to read it next run:
		//   ptr mainMenu == ptr lit 'Main Menu'  -> the layout is correct, so menu=0
		//        genuinely means “no menu was open” -- a game-state fact, not a bug
		//   pointers differ                     -> the InterfaceStrings layout does
		//        not match this game build, and the literal half is what works
		void ProbeMenuNamesOnce()
		{
			static bool done = false;
			if (done)
				return;
			auto* ui = RE::UI::GetSingleton();
			const auto* is = RE::InterfaceStrings::GetSingleton();
			if (!ui || !is) {
				// v0.70: set done FIRST, and say which one is null. The old order
				// returned before done = true, so a null singleton made the probe print
				// nothing at all - indistinguishable from “never reached”. A silent
				// instrument is worse than no instrument.
				done = true;
				SKSE::log::warn("[XRAY] MENU PROBE unavailable: ui={} istrings={} -> menu "
				"detection is limited to whichever path is left; if menuEdges stays 0 "
				"then the singletons, not the menu names, are what is broken",
				static_cast<const void*>(ui), static_cast<const void*>(is));
				return;
			}
			done = true;
			const RE::BSFixedString litMain("Main Menu");
			const RE::BSFixedString litLoad("Loading Menu");
			const RE::BSFixedString litJournal("Journal Menu");
			SKSE::log::info("[XRAY] MENU PROBE ui={} istrings={} | ptr mainMenu={} (lit={}) "
				"loadingMenu={} (lit={}) journalMenu={} (lit={}) | IsMenuOpen(is)={}/{}/{} "
				"IsMenuOpen(literal)={}/{}/{}",
				static_cast<const void*>(ui), static_cast<const void*>(is),
				static_cast<const void*>(is->mainMenu.c_str()),
				static_cast<const void*>(litMain.c_str()),
				static_cast<const void*>(is->loadingMenu.c_str()),
				static_cast<const void*>(litLoad.c_str()),
				static_cast<const void*>(is->journalMenu.c_str()),
				static_cast<const void*>(litJournal.c_str()),
				ui->IsMenuOpen(is->mainMenu), ui->IsMenuOpen(is->loadingMenu),
				ui->IsMenuOpen(is->journalMenu), ui->IsMenuOpen(litMain),
				ui->IsMenuOpen(litLoad), ui->IsMenuOpen(litJournal));
		}
	}

	// v0.63：Present 路径（DX12SwapChain.cpp）要用同一个菜单判断，去自行实现
	// DLSSGFlags::eEnableFullScreenMenuDetection —— Transfusion 会在提交给运行时之前
	// 把这个 flag 从 DLSS-G options 里剥掉（2026-09-17 21:54:06.810：
	// “stripped eEnableFullscreenMenuDetection ... 0x10 -> 0x10”，剥前剥后完全相同
	// = 运行时从来没收到过），所以插件侧必须自己关。
	bool Streamline::MenuOpenNow()
	{
		ProbeMenuNamesOnce();
		return GameMenuOpenNow();
	}

	// v0.70: sample the menu state ONCE PER FRAME, before anything consumes it, so
	// that the guard (DX12SwapChain's menuBlock), the frame counters and the reset
	// edge all read the same value. The old placement was inside
	// CheckFrameConstants, which only runs from EvaluateDLSSG - and the guard skips
	// EvaluateDLSSG. So on every frame the guard engaged, menuOpenNow/menuFrames/
	// menuEdges stayed frozen and the reset edge could not fire. Evidence: the run
	// at 2026-09-17 23:07 reported menu=0 world=151, which was read as “no menu was
	// ever detected“ when it equally meant ”the counter never ran“.
	bool Streamline::PollMenuState()
	{
		if (!initialized)
			return false;
		ProbeMenuNamesOnce();
		const bool isMenuOpen = GameMenuOpenNow();
		diag.menuOpenNow = isMenuOpen;
		// Count each real frame exactly once for the menu/world split. Guarded by
		// frameSerial so a second call inside the same frame cannot double-count.
		if (frameSerial != diag.lastCountedSerial) {
			diag.lastCountedSerial = frameSerial;
			if (isMenuOpen)
				++diag.menuFrames;
			else
				++diag.worldFrames;
		}
		if (isMenuOpen != menuWasOpen) {
			++diag.menuEdges;
			// Logged at the moment of the transition, with the multiplier that was
			// in effect just before it - that pair is what tells whether the menu
			// handling actually engages.
			SKSE::log::info("[XRAY] MENU EDGE open={} serial={} presentedBefore={} consts(ok={} fail={})",
				isMenuOpen ? 1 : 0, frameSerial, diag.presentedPrev,
				diag.constsOk, diag.constsFail);
			if (isMenuOpen)
				menuResetPending = true;   // consumed by CheckFrameConstants
			// v1.07: the camera-family lock has no release path of its own.
			// This transition is the one place it must move - leaving a menu
			// means the locked camera describes a world that is gone. Raised on
			// BOTH edges rather than relying on when menuResetPending is later
			// consumed, because the consumer (CheckFrameConstants) is skipped
			// for as long as the menu is open.
			Get().snapLockReleasePending = true;
		}
		menuWasOpen = isMenuOpen;
		return isMenuOpen;
	}

	// v0.70: the state PollMenuState() last sampled. Present-path callers use this
	// instead of re-querying, so the guard and the diagnostics cannot disagree.
	bool Streamline::MenuIsOpen() const
	{
		return diag.menuOpenNow;
	}

	void Streamline::CheckFrameConstants(const FrameBuffer& a_fb, float a_aspect, float a_near, float a_far)
	{
		if (!initialized)
			return;

		// v0.5：frameToken 失败保护（失败 → 置空 → 调用方跳过本帧 SL 调用，防空指针解引用）
		// v0.31：slGetNewFrameToken 必须传帧计数（nullptr → 帧号停滞 “frame 1”）。
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

				// ===== v0.65: reprojection source ====================================
		// 2026-09-17 22:18 运行实测：引擎的 CameraPreviousViewProjUnjittered 与
		// CameraViewProjUnjittered **逐元素恒等**（心跳里每一条 prevVP 都等于同一行的
		// curVP），Transfusion 侧 4/4 次 slSetConstants 也全部记录 clipToPrev=identity。
		// 于是 clipToPrevClip = inv(cur) x prev = I —— DLSS-G 收到的相机运动量**恒为 0**：
		//   加载菜单（相机本来静止）看着正常；一进世界（相机开始动）就成片闪。
		// v0.64 的钳制只是把“零矩阵”换成“单位矩阵”，两者都等价于“没动”，所以治不了闪。
		// 要修的是**数据源**：
		//   1. 不再采信引擎的 prev 字段，自己维护“上一帧交给 DLSS-G 的 viewProj”
		//   2. 自带派生源（view x proj），在引擎 cur 冻结时接管（附首帧交叉校验）
		const Matrix curVP = a_fb.CameraViewProjUnjittered;
		sl::float4x4 currViewProjSL;
		currViewProjSL[0] = sl::float4(curVP.data[0][0], curVP.data[1][0], curVP.data[2][0], curVP.data[3][0]);
		currViewProjSL[1] = sl::float4(curVP.data[0][1], curVP.data[1][1], curVP.data[2][1], curVP.data[3][1]);
		currViewProjSL[2] = sl::float4(curVP.data[0][2], curVP.data[1][2], curVP.data[2][2], curVP.data[3][2]);
		currViewProjSL[3] = sl::float4(curVP.data[0][3], curVP.data[1][3], curVP.data[2][3], curVP.data[3][3]);

		// 引擎的 prev 只保留做对照（engPrev*），不再参与重投影。
		const Matrix prevVP = a_fb.CameraPreviousViewProjUnjittered;
		sl::float4x4 engPrevViewProjSL;
		engPrevViewProjSL[0] = sl::float4(prevVP.data[0][0], prevVP.data[1][0], prevVP.data[2][0], prevVP.data[3][0]);
		engPrevViewProjSL[1] = sl::float4(prevVP.data[0][1], prevVP.data[1][1], prevVP.data[2][1], prevVP.data[3][1]);
		engPrevViewProjSL[2] = sl::float4(prevVP.data[0][2], prevVP.data[1][2], prevVP.data[2][2], prevVP.data[3][2]);
		engPrevViewProjSL[3] = sl::float4(prevVP.data[0][3], prevVP.data[1][3], prevVP.data[2][3], prevVP.data[3][3]);

		// v1.02: needed by the rebuild helper below; the original `finiteMag`
		// lambda is declared further down this function.
		auto finiteMagOf = [](const sl::float4x4& m) -> float {
			float mx = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float v[4] = { m[r].x, m[r].y, m[r].z, m[r].w };
				for (int k = 0; k < 4; ++k) {
					const float a = v[k] < 0.0f ? -v[k] : v[k];
					if (!(a <= 1.0e6f))
						return 1.0e30f;
					if (a > mx)
						mx = a;
				}
			}
			return mx;
		};

		// ---- v1.02: previous CAMERA (position included) ----------------------
		//
		// WHY THE ENGINE'S PREV CANNOT BE A REPROJECTION SOURCE
		//
		// The engine composes its ViewProj as  Proj @ [R | 0]  -- there is NO
		// translation term (proven offline: c0 == c56 byte-for-byte, and
		// Proj @ [R | 0] == c24 with max|err| = 0.000000). Its own product is
		// therefore blind to the camera position, and it writes prev := cur
		// verbatim, so on any frame it does not advance
		//
		//     clipToPrevClip = inv(VP) x VP = I
		//
		// and DLSS-G is told the camera never moved. `cur` was repaired in v0.88
		// by rebuilding it from R + eye; `prev` was still reading that broken
		// product, which is why the picture stayed frozen after v1.00.
		//
		// CameraView is a pure rotation block, so the camera ORIENTATION survives
		// even when the engine's ViewProj does not move: only the translation is
		// missing from that product, and eye comes from CameraPosAdjust.
		auto rebuildViewProj = [&](const Matrix& a_view, const float a_eye[3],
		                           const Matrix& a_proj, sl::float4x4& a_out) -> bool {
			const float ex = a_eye[0];
			const float ey = a_eye[1];
			const float ez = a_eye[2];
			float vm[3][4] = {};
			for (int r = 0; r < 3; ++r) {
				const float m0 = a_view.data[r][0];
				const float m1 = a_view.data[r][1];
				const float m2 = a_view.data[r][2];
				if (!(m0 == m0) || !(m1 == m1) || !(m2 == m2))
					return false;                       // NaN rotation row
				vm[r][0] = m0;
				vm[r][1] = m1;
				vm[r][2] = m2;
				vm[r][3] = -(m0 * ex + m1 * ey + m2 * ez);
			}
			// Transpose into SL's row-major convention, exactly as the surrounding
			// code does for every other engine matrix.
			sl::float4x4 viewSL;
			viewSL[0] = sl::float4(vm[0][0], vm[1][0], vm[2][0], 0.0f);
			viewSL[1] = sl::float4(vm[0][1], vm[1][1], vm[2][1], 0.0f);
			viewSL[2] = sl::float4(vm[0][2], vm[1][2], vm[2][2], 0.0f);
			viewSL[3] = sl::float4(vm[0][3], vm[1][3], vm[2][3], 1.0f);
			const auto& pj = a_proj.data;
			sl::float4x4 projSL;
			projSL[0] = sl::float4(pj[0][0], pj[1][0], pj[2][0], pj[3][0]);
			projSL[1] = sl::float4(pj[0][1], pj[1][1], pj[2][1], pj[3][1]);
			projSL[2] = sl::float4(pj[0][2], pj[1][2], pj[2][2], pj[3][2]);
			projSL[3] = sl::float4(pj[0][3], pj[1][3], pj[2][3], pj[3][3]);
			sl::matrixMul(a_out, projSL, viewSL);   // Proj @ View, engine order
			return true;
		};

		// v1.02c: OBSERVATION ONLY -- feeds the engPrev* heartbeat counters and
		// documents why the engine's prev field is unusable as a motion source
		// (it never changes, so "prev == cur" and "prev != cur" are both noise).
		// The reprojection path does NOT consult it any more; see camPrevVP below.
		auto sameCamera = [](const Matrix& a, const Matrix& b) -> bool {
			for (int r = 0; r < 4; ++r)
				for (int k = 0; k < 4; ++k) {
					const float d = a.data[r][k] - b.data[r][k];
					if (!(d == d))
						return false;                   // NaN
					if (d > 1.0e-9f || d < -1.0e-9f)
						return false;
				}
			return true;
		};

		// The previous camera, carried across frames as RAW ENGINE MATRICES so the
		// rebuild reuses the SAME code path as `cur` (no second convention).
		// static, not thread_local: v0.82 proved Present() is driven by two engine
		// threads in alternation, and history belongs to the PREVIOUS FRAME, not to
		// the previous thread.
		static Matrix s_prevCamView{};
		static Matrix s_prevCamProj{};
		static float s_prevCamEye[3] = { 0.0f, 0.0f, 0.0f };
		static bool s_hasPrevCam = false;

		// The CURRENT camera, rebuilt. This is what becomes "previous" at the end
		// of the frame, so the history always carries a position.
		// It is also the only motion source available: the engine's own prev and
		// cur ViewProj are both translation-free, and its prev field is frozen
		// outright (v1.02c evidence above).
		sl::float4x4 camCurVP{};
		const bool camCurOk =
			rebuildViewProj(a_fb.CameraView, a_fb.CameraPosAdjust, a_fb.CameraProj, camCurVP) &&
			finiteMagOf(camCurVP) > 1.0e-6f;

		sl::float4x4 camPrevVP{};
		bool camPrevOk = false;
		if (camCurOk && s_hasPrevCam) {
			// ---- v1.02c: the engine's prev field is NOT a motion sensor ------
			//
			// The previous run reported, on every heartbeat,
			//
			//     engPrevEqCur=331/331  engPrevDiffers=331  engPrevZero=0
			//
			// Both the "equal" and the "differs" counter climbed at the same
			// rate. That is impossible for a field that tracks the camera: it is
			// only possible if CameraPreviousViewProjUnjittered is a matrix that
			// never equals cur AND never changes -- a stale constant, in all
			// likelihood the menu camera left over from the 3D main menu.
			//
			// The heartbeat confirms it: prevVP reads equal to curVP to the four
			// decimals it prints, while clipDev sits at 0.000061 -- identity --
			// for every frame of a run in which the player was walking.
			//
			// So this field cannot decide anything. The still-camera case is
			// handled by the rebuild itself, exactly:
			//
			//     eye_prev == eye_cur -> prevView == curView -> camPrevVP == camCurVP
			//                         -> clipToPrevClip == I
			//
			// A parked camera therefore still yields identity, and a moving one
			// finally yields motion. `sameCamera` is left in place as the
			// documented predicate behind the engPrev* counters on the heartbeat.
			camPrevOk = rebuildViewProj(s_prevCamView, s_prevCamEye,
			                            s_prevCamProj, camPrevVP) &&
			            finiteMagOf(camPrevVP) > 1.0e-6f;
		}

		// v1.06: THE WRITER THIS HISTORY NEVER HAD.
		//
		// v1.02c wrote the reader above and stopped there. The four statics
		// declared a few lines up are read once each and written nowhere:
		// s_prevCamView, s_prevCamProj and s_prevCamEye are never assigned,
		// and s_hasPrevCam is initialised to false and never set true. So
		// camPrevOk was false on every frame of every run, and the heartbeat
		// proves it rather than inferring it:
		//
		//     21:27:27.912  cam(ok/inv)=121/0  camPrev(ok/used)=0/0
		//
		// cam() is healthy and camPrev() is flat zero - the rebuild existed
		// and could never be reached. A rebuild is only as good as its
		// history; this is that history. Stored as RAW engine matrices, so
		// the previous frame goes through exactly the same rebuildViewProj
		// as the current one and the two cannot diverge by convention.
		if (camCurOk) {
			s_prevCamView = a_fb.CameraView;
			s_prevCamProj = a_fb.CameraProj;
			s_prevCamEye[0] = a_fb.CameraPosAdjust[0];
			s_prevCamEye[1] = a_fb.CameraPosAdjust[1];
			s_prevCamEye[2] = a_fb.CameraPosAdjust[2];
			s_hasPrevCam = true;
		}

		auto finiteMag = [](const sl::float4x4& m) -> float {
			float mx = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float v[4] = { m[r].x, m[r].y, m[r].z, m[r].w };
				for (int k = 0; k < 4; ++k) {
					const float a = v[k] < 0.0f ? -v[k] : v[k];
					// NaN/Inf 都会走到这里（!(NaN <= x) 为真）
					if (!(a <= 1.0e6f))
						return 1.0e30f;
					if (a > mx)
						mx = a;
				}
			}
			return mx;
		};
		// 逐元素相同判定。引擎把 prev 写成 cur 时是**位级相同**（日志里两个 devOf
		// 精确一致到 4 位小数），1e-9 绝对容差足够。
		auto sameMat = [](const sl::float4x4& a, const sl::float4x4& b) -> bool {
			for (int r = 0; r < 4; ++r) {
				const float d[4] = { a[r].x - b[r].x, a[r].y - b[r].y,
				                     a[r].z - b[r].z, a[r].w - b[r].w };
				for (int k = 0; k < 4; ++k) {
					if (!(d[k] == d[k]))
						return false;                              // NaN
					const float a2 = d[k] < 0.0f ? -d[k] : d[k];
					if (a2 > 1.0e-9f)
						return false;
				}
			}
			return true;
		};

		// ===== v0.66: det guard =====
		// 1) clipToPrevClip = inv(cur) x prev。两帧投影相同时投影项互相抵消
		//    ⇒ 左上 3x3 的行列式必须 ≈ 1（纯旋转）。实测坏帧给出 -31.4 / -0.025，
		//    那不是任何合法变换；交给 DLSS-G 会让每个生成帧的位移完全错（成片闪）。
		//    这是**可判定**的，不是猜出来的阈值 —— 并且会把观测到的 det 范围打进
		//    日志，让这个判断在下次运行时自我验证。
		auto det3 = [](const sl::float4x4& m) -> float {
			const float a = m[0].x, b = m[0].y, c = m[0].z;
			const float d = m[1].x, e = m[1].y, f = m[1].z;
			const float g = m[2].x, h = m[2].y, i = m[2].z;
			return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
		};
		auto setIdentity = [](sl::float4x4& m) {
			m[0] = { 1.f, 0.f, 0.f, 0.f };
			m[1] = { 0.f, 1.f, 0.f, 0.f };
			m[2] = { 0.f, 0.f, 1.f, 0.f };
			m[3] = { 0.f, 0.f, 0.f, 1.f };
		};

		// 2) 谁在调本函数？哨兵（多线程 = 0xFFFFFFFF）分不清「一次线程交接」和
		//    「真的并发」—— 改成 per-tid 计数，下次日志一眼看出各线程各调多少次。
		{
			const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());
			if (diag.tidA == 0) { diag.tidA = tid; ++diag.tidCallsA; }
			else if (diag.tidA == tid) { ++diag.tidCallsA; }
			else if (diag.tidB == 0) { diag.tidB = tid; ++diag.tidCallsB; }
			else if (diag.tidB == tid) { ++diag.tidCallsB; }
			else if (diag.tidC == 0) { diag.tidC = tid; ++diag.tidCallsC; }
			else if (diag.tidC == tid) { ++diag.tidCallsC; }
		}

		// ---- 派生源：viewProj = inv(CameraViewInverse) x CameraProjUnjittered ----
		// 两个**独立字段**。CameraViewInverse 同时是 DLSS-G 相机朝向
		// （cameraRight/Up/Fwd）的来源，所以它与那份数据天然一致。
		sl::float4x4 derivedViewProj;
		{
			sl::float4x4 viewInvSL, projUnjSL;
			const auto& vi = a_fb.CameraViewInverse.data;
			viewInvSL[0] = sl::float4(vi[0][0], vi[1][0], vi[2][0], vi[3][0]);
			viewInvSL[1] = sl::float4(vi[0][1], vi[1][1], vi[2][1], vi[3][1]);
			viewInvSL[2] = sl::float4(vi[0][2], vi[1][2], vi[2][2], vi[3][2]);
			viewInvSL[3] = sl::float4(vi[0][3], vi[1][3], vi[2][3], vi[3][3]);
			const auto& pu = a_fb.CameraProjUnjittered.data;
			projUnjSL[0] = sl::float4(pu[0][0], pu[1][0], pu[2][0], pu[3][0]);
			projUnjSL[1] = sl::float4(pu[0][1], pu[1][1], pu[2][1], pu[3][1]);
			projUnjSL[2] = sl::float4(pu[0][2], pu[1][2], pu[2][2], pu[3][2]);
			projUnjSL[3] = sl::float4(pu[0][3], pu[1][3], pu[2][3], pu[3][3]);
			sl::float4x4 viewSL;
			sl::matrixFullInvert(viewSL, viewInvSL);
			sl::matrixMul(derivedViewProj, viewSL, projUnjSL);
		}
		// 首帧交叉校验：派生源必须与引擎源一致（相对误差 <= 1%）才允许启用。
		// 构造方式若不对，匹配失败，派生源直接作废 —— 不会引入新病。
		if (!diag.derivedChecked && finiteMag(currViewProjSL) > 1.0e-6f &&
			finiteMag(derivedViewProj) > 1.0e-6f) {
			diag.derivedChecked = 1;
			float worst = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float d[4] = { derivedViewProj[r].x - currViewProjSL[r].x,
				                     derivedViewProj[r].y - currViewProjSL[r].y,
				                     derivedViewProj[r].z - currViewProjSL[r].z,
				                     derivedViewProj[r].w - currViewProjSL[r].w };
				for (int k = 0; k < 4; ++k) {
					const float a2 = d[k] < 0.0f ? -d[k] : d[k];
					if (!(a2 <= 1.0e7f)) { worst = 1.0e30f; break; }   // NaN/Inf
					if (a2 > worst) worst = a2;
				}
			}
			diag.derivedMatchErr = worst;
			diag.derivedMatch = (worst <= finiteMag(currViewProjSL) * 0.01f) ? 1 : 0;
		}

		// ---- 引擎 cur 是否冻结 ----
		// v0.66：函数内 static = 全局共享。若本函数被两个线程调用，线程 B 会覆盖
		// 线程 A 的冻结检测状态 ⇒ thread_local。
		thread_local sl::float4x4 s_lastEngCur{};
		thread_local bool s_hasLastEngCur = false;
		thread_local std::uint32_t s_engCurFrozen = 0;
		const bool engCurOk = finiteMag(currViewProjSL) > 1.0e-6f;
		if (engCurOk) {
			if (s_hasLastEngCur && sameMat(s_lastEngCur, currViewProjSL))
				++s_engCurFrozen;
			else
				s_engCurFrozen = 0;
			s_lastEngCur = currViewProjSL;
			s_hasLastEngCur = true;
			if (s_engCurFrozen > diag.engCurFrozenRun)
				diag.engCurFrozenRun = s_engCurFrozen;
		}

		// ---- 选源：引擎 cur 连续冻结 >= 30 帧且派生源通过校验 -> 换派生源 ----
		// ---- v0.88: rebuild ViewProj with the missing translation ----
		// ROUND 12 (offline, from the v0.87 raw dumps) finally closed this:
		//
		//   c8 @ c0                      == c24  with max|err| = 0.000000
		//      => the engine composes ViewProj as  Proj @ View  (投影在左).
		//         Six earlier hand-derived candidates all used View @ Proj, which
		//         is why they all missed by 0.111 -- the order, not the maths.
		//
		//   c0 == c56 (byte-for-byte)    and    Proj @ [R | 0] == c24 (err 0)
		//      => the engine's view matrix carries NO translation. Its ViewProj
		//         therefore cannot depend on the camera position at all, and
		//         clipToPrevClip = inv(cur) x prev collapses to the identity.
		//         Runtime: a camera creeping 0.4 u/frame produces |I - clip| =
		//         0.000000 -- DLSS-G is told the camera is parked and reprojects
		//         every generated frame to the same place. That is the ping-pong
		//         between two nearly identical real frames.
		//
		// The old v0.69 comment above had the causality INVERTED: it observed
		// “derivedViewProj cannot reproduce ViewProjUnjittered” and concluded the
		// derived source was dead code. In fact the engine copy is the broken one;
		// derived failed precisely because it faithfully inherited the same
		// missing translation from CameraViewInverse. Disabling it removed the
		// only path that could have carried the fix, so the defect survived.
		//
		// Fix: rebuild the view matrix from the rotation block and the position
		// field, both of which are already in hand, then compose Proj @ View.
		//
		// Proven safe offline (tools/v088_regression_fixed.py):
		//   eye = 0           -> identical to c24        (exact regression guard)
		//   camera parked     -> |I - clip| = 0.000000   (never invents motion)
		//   camera creeps 0.4 -> |I - clip| = 0.400000   (motion restored)
		// The v0.69 objection (“could only invent motion where there is none”) is
		// therefore VOID: it was aimed at a construction that lacked translation,
		// which is the very term being supplied here.
		sl::float4x4 fixedViewProj{};
		bool fixedViewProjOk = false;
		{
			// R3 = upper-left 3x3 of c0 CameraView. The engine stores rows, so this
			// is the world-to-camera rotation in the same convention the engine's
			// own Proj @ View product uses -- verified by the exact match above.
			const auto& vw = a_fb.CameraView.data;
			// eye = CameraPosAdjust (c80). This is the ONLY field carrying position;
			// it is already the source of c.cameraPos a few lines up.
			const float ex = a_fb.CameraPosAdjust[0];
			const float ey = a_fb.CameraPosAdjust[1];
			const float ez = a_fb.CameraPosAdjust[2];

			// Build [R3 | -R3 @ eye] in ENGINE row-major storage.
			//
			// v0.88b: sl::float4 exposes only .x/.y/.z/.w -- there is no subscript
			// operator on it. The first draft treated the type as a 2-D array and
			// produced ten C2676 errors. The component-wise pattern below is the
			// same one the cross-check block above already uses.
			float vm[3][4] = {};                    // plain array: no SL type involved
			for (int r = 0; r < 3; ++r) {
				vm[r][0] = vw[r][0];
				vm[r][1] = vw[r][1];
				vm[r][2] = vw[r][2];
				vm[r][3] = -(vw[r][0] * ex + vw[r][1] * ey + vw[r][2] * ez);
			}

			// Transpose into SL's row-major convention, exactly as the surrounding
			// code does for every other engine matrix (s[0]=col0, s[1]=col1, ...).
			sl::float4x4 viewSL;
			viewSL[0] = sl::float4(vm[0][0], vm[1][0], vm[2][0], 0.0f);
			viewSL[1] = sl::float4(vm[0][1], vm[1][1], vm[2][1], 0.0f);
			viewSL[2] = sl::float4(vm[0][2], vm[1][2], vm[2][2], 0.0f);
			viewSL[3] = sl::float4(vm[0][3], vm[1][3], vm[2][3], 1.0f);

			// Projection: c8 CameraProj is the factor the engine actually used in
			// its own ViewProj (proven: c8 @ c0 == c24). Transpose it the same way.
			const auto& pj = a_fb.CameraProj.data;
			sl::float4x4 projSL;
			projSL[0] = sl::float4(pj[0][0], pj[1][0], pj[2][0], pj[3][0]);
			projSL[1] = sl::float4(pj[0][1], pj[1][1], pj[2][1], pj[3][1]);
			projSL[2] = sl::float4(pj[0][2], pj[1][2], pj[2][2], pj[3][2]);
			projSL[3] = sl::float4(pj[0][3], pj[1][3], pj[2][3], pj[3][3]);

			// VP = Proj @ View, IN THAT ORDER -- the order is the whole point.
			sl::matrixMul(fixedViewProj, projSL, viewSL);
			fixedViewProjOk = finiteMag(fixedViewProj) > 1.0e-6f;
		}

		// The engine's own product stays in the log next to the fixed one, so the
		// next run can show at a glance that the fix is doing what it claims.
		diag.fixedVpDev = (fixedViewProjOk && finiteMag(currViewProjSL) > 1.0e-6f)
			? [&]() {
				float worst = 0.0f;
				for (int r = 0; r < 4; ++r) {
					const float d[4] = { fixedViewProj[r].x - currViewProjSL[r].x,
					                     fixedViewProj[r].y - currViewProjSL[r].y,
					                     fixedViewProj[r].z - currViewProjSL[r].z,
					                     fixedViewProj[r].w - currViewProjSL[r].w };
					for (int k = 0; k < 4; ++k) {
						const float a2 = d[k] < 0.0f ? -d[k] : d[k];
						if (a2 > worst) worst = a2;
					}
				}
				return worst;
			}() : -1.0f;

		// Use the corrected matrix for reprojection. If for any reason it could not
		// be built, fall back to the engine copy rather than to something invalid.
		const bool useFixed = fixedViewProjOk;
		sl::float4x4 curForReproj = useFixed ? fixedViewProj : currViewProjSL;
		const bool curOk = finiteMag(curForReproj) > 1.0e-6f;
		diag.reprojSource = useFixed ? 2 : 0;
		if (useFixed)
			++diag.derivedUsed;
		diag.curMagLast = curOk ? finiteMag(curForReproj) : 0.0f;
		diag.engPrevMagLast = finiteMag(engPrevViewProjSL);
		diag.camPrevOk = camPrevOk ? 1 : 0;

		// ---- 引擎 prev 是否 == cur（“相机运动恒为 0”的直接证据）----
		if (finiteMag(engPrevViewProjSL) > 1.0e-6f) {
			if (sameMat(engPrevViewProjSL, currViewProjSL))
				++diag.engPrevEqCur;
			else
				++diag.engPrevDiffers;
		} else {
			++diag.engPrevZero;
		}

		// ---- 自维护 prev 历史 ----
		// s_prevVP 只在 cur 有效时推进 —— 无效帧（零矩阵）绝不能进历史，否则下一帧
		// 的 prev 就是零，又回到“矩阵无效”。
		//
		// v0.82：**改回共享，撤销 v0.66 的 thread_local**。
		// v0.66 的理由是“跨线程共享会让计算用上别的线程的上一帧”，但那个理由只在
		// 「一个线程独占 Present」时成立。实测（09:39 日志的 FPS probe 线程列）
		// Present() 被 **两个引擎线程交替**驱动：
		//     22548,22548,22548,3236,3236,22548,22548,3236,3236,3236,3236
		// 于是每次切换，新线程的 s_hasPrevVP 都是 false ⇒ havePrev=false ⇒
		// clipToPrevClip 被写成单位矩阵 = 告诉 DLSS-G「相机没动」⇒ **不产出插帧**。
		// 这就是“进世界后整体冻结、只有引擎粒子（火堆）还在动”的直接成因：
		// 真实帧照常渲染，插帧全没了。
		// 日志指纹：det(min/max)=1.000/1.000（det==1 当且仅当 prev==cur）、
		//           clipDevMax=0.0000、detGuard/detHold=0/0（守卫根本没触发）。
		//
		// 这里改成“按帧”维护：历史属于「上一帧呈现的相机」，不属于「上一个线程」。
		// 同一时刻只有一条 Present 线程流在推进，故不加锁也是安全的写者；读到的
		// 顶多是被另一个线程刚更新的、时间上更近的一帧 —— 那正是我们要的语义。
		static sl::float4x4 s_prevVP{};
		static bool s_hasPrevVP = false;
		sl::float4x4 prevForReproj{};
		bool havePrev = false;
		if (curOk) {
			// ---- v1.02: the history advances with the REBUILT camera ----------
			//
			// v0.66..v1.00 stored `curForReproj`, the engine-derived ViewProj,
			// which carries NO translation -- so the self-maintained history
			// inherited the very blindness it existed to cure: two frames of a
			// walking camera still produced clipToPrevClip == I.
			// camCurVP is that same camera rebuilt from R + eye.
			const sl::float4x4& advance = camCurOk ? camCurVP : curForReproj;
			if (s_hasPrevVP) {
				prevForReproj = s_prevVP;
				havePrev = true;
			}
			s_prevVP = advance;
			s_hasPrevVP = true;
		}
		// ---- v1.02: prefer the rebuilt previous camera ------------------------
		//
		// camPrevVP is Proj @ [R_prev | -R_prev @ eye_prev]: the true composed
		// relative transform, translation included. It wins over both s_prevVP
		// and the engine's prev, and it is EXACT when the camera was still
		// (sameCamera -> camPrevVP == camCurVP), so switching to it cannot
		// introduce motion where there is none.
		if (camPrevOk) {
			prevForReproj = camPrevVP;
			havePrev = true;
			++diag.camPrevUsed;
		}
		// v0.82: 没有自维护历史时，先试引擎自己的 prev（CameraPreviousViewProjUnjittered）。
		// 本构建里该字段恒为零矩阵（engPrevZero=241），所以必须做有效性校验：
		// 只有有限、非退化的矩阵才接受；否则宁可退回 s_lastGoodClip。
		if (!havePrev && curOk && finiteMag(engPrevViewProjSL) > 1.0e-6f) {
			prevForReproj = engPrevViewProjSL;
			havePrev = true;
			++diag.prevSeededFromEngine;
		}

		sl::float4x4 invCurrViewProj;
		// v0.67：守卫触发时保留上一帧**合法**的 clipToPrevClip，不再写单位矩阵。
		// 「单位矩阵」在 DLSS-G 眼里是「相机没动」—— 那是一句谎话，会让它的遮挡/
		// 去遮挡判断整体错位；上一帧的真实位移是远好得多的估计。detHold 把它暴露出来。
		// v0.82：同样撤销 thread_local（理由见上）。这份历史是“上一帧的合法位移”，
		// 线程切换后它依然有效，丢掉它只会让新线程重新用单位矩阵。
		static sl::float4x4 s_lastGoodClip{};
		static bool s_hasLastGoodClip = false;
		if (curOk && havePrev) {
			++diag.prevHistoryHits;
			// v1.07c: the inverse MUST come from the same camera as `prev`.
			//
			// prevForReproj is camPrevVP or s_prevVP; both come out of
			// rebuildViewProj, which folds the eye in as -R@eye. curForReproj is
			// the engine's own ViewProj and -- per the note further up -- carries
			// NO translation. Inverting one and multiplying by the other cannot
			// cancel:
			//
			//   inv(Proj @ [R|0]) @ (Proj @ [R|-R@eye])
			//     = [R^T|0] @ Proj^-1 @ Proj @ [R|-R@eye]
			//     = [R^T R | -R^T R @ eye] = [I | -eye]
			//
			// Rotation-correct (det3() reads only the 3x3, so it still reports
			// 1.000000 and every guard below passes) and translation-absurd.
			//
			// 23:10 run, Transfusion [MOTION] dump, frame 578:
			//   clipToPrev rows=[...][...][...]
			//                   [-243.962387 2.7390945 -77.6724777 -195.222366]
			//   cameraPos=(-243.049301,-415.311523,118.558205)
			// row3[3] is -195, not 1: not even affine. The heartbeat alternated
			// between that and clipDev=0.000023 because camCurOk flips, so DLSS-G
			// was told "still" then "moved 244 units", frame by frame. That is
			// the back-and-forth the picture shows.
			const sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;
			sl::matrixFullInvert(invCurrViewProj, reprojInvSrc);
			sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);
			// v0.66 (det guard)：det(inv(cur) x prev) **恒等于 1 当且仅当** cur/prev
			// 是同一套相机数据（两帧投影相同则投影项互相抵消）。实测只出现
			// -0.025248 与 1.000000 两个取值 —— 前者是同一缓冲每帧被写入两组不同
			// 相机（菜单 3D 背景 <-> 世界）时跨来源相减的指纹。
			const float det = det3(c.clipToPrevClip);
			if (det < diag.detMin) diag.detMin = det;
			if (det > diag.detMax) diag.detMax = det;
			// v0.92: translation-aware validity gate.
			//
			// det3() reads only the upper-left 3x3, which for
			// inv(cur) x prev equals  Proj3 * Rcur^T * Rprev * Proj3^-1 --
			// a function of the ROTATION ALONE. Proven offline
			// (tools/prove_det3_blind.py): det3 == 1.000000 for every camera
			// displacement from 0.001 to 400 units, while max|I - clip| tracks
			// the displacement one-for-one.
			//
			// So the old `det in [0.5,2.0]` test could not see translation at
			// all, and det(min/max)=1.000/1.000 in the log meant "the metric is
			// blind", NOT "the camera never moved". Gate on a metric that does
			// depend on the translation.
			//
			// clipDev = max|I - clipToPrevClip| over the FULL 4x4 (the same
			// quantity already reported as clipDevMax). A real relative motion
			// makes it > 0; a degenerate / non-finite matrix fails the finite
			// test below.
			float clipDev = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float v[4] = { c.clipToPrevClip[r].x, c.clipToPrevClip[r].y,
				                     c.clipToPrevClip[r].z, c.clipToPrevClip[r].w };
				for (int k = 0; k < 4; ++k) {
					const float id = (r == k) ? 1.0f : 0.0f;
					const float a2 = v[k] - id;
					const float m = a2 < 0.0f ? -a2 : a2;
					if (m > clipDev) clipDev = m;
				}
			}
			float clipMagAll = 0.0f;
			for (int r = 0; r < 4; ++r) {
				clipMagAll += c.clipToPrevClip[r].x * c.clipToPrevClip[r].x
				            + c.clipToPrevClip[r].y * c.clipToPrevClip[r].y
				            + c.clipToPrevClip[r].z * c.clipToPrevClip[r].z
				            + c.clipToPrevClip[r].w * c.clipToPrevClip[r].w;
			}
			const bool clipFinite = clipMagAll < 1.0e30f;   // rejects NaN / Inf
			if (clipFinite) {
				s_lastGoodClip = c.clipToPrevClip;
				s_hasLastGoodClip = true;
			} else {
				++diag.detGuard;
				if (s_hasLastGoodClip) {
					c.clipToPrevClip = s_lastGoodClip;
					++diag.detHold;
				} else {
					setIdentity(c.clipToPrevClip);
				}
			}
			// v0.92: keep both metrics in one line so the next run shows which
			// one carries the motion signal (det3 is provably flat).
			if (diag.detGuard <= 3u) {
				SKSE::log::info("[XRAY] clipGate v0.92: det3={:.6f} (rotation-only, "
					"expected ~1) clipDev={:.6f} finite={} - clipDev is the "
					"translation-aware metric",
					det, static_cast<double>(clipDev), clipFinite ? 1 : 0);
			}
		} else {
			// 首帧 / cur 无效：这是安全退化，但会被 prevHistoryMiss 计数暴露出来 ——
			// 若它长期增长，说明数据源还是有问题。
			//
			// v0.82：**绝不无条件写单位矩阵**。单位矩阵在 DLSS-G 眼里等于
			// 「相机没动」——那是一句谎话，会让它停止产出插帧（本工程的冻结就是它）。
			// 优先复用一个合法的历史位移；只有连历史都没有（真正的第一帧）才退回单位。
			++diag.prevHistoryMiss;
			if (s_hasLastGoodClip) {
				c.clipToPrevClip = s_lastGoodClip;
				++diag.prevMissUsedLastGood;
			} else {
				setIdentity(c.clipToPrevClip);
			}
		}
		sl::matrixFullInvert(c.prevClipToClip, c.clipToPrevClip);
		// 重投影矩阵是否真带运动：|clipToPrev - I| 的窗口最大值。运动中它必须明显
		// 大于 0；恒 0 就说明相机项又被丢掉了（这是判定修复是否生效的那个数）。
		{
			float d = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float v[4] = { c.clipToPrevClip[r].x, c.clipToPrevClip[r].y,
				                     c.clipToPrevClip[r].z, c.clipToPrevClip[r].w };
				for (int k = 0; k < 4; ++k) {
					const float id = (r == k) ? 1.0f : 0.0f;
					const float a2 = v[k] - id;
					const float m = a2 < 0.0f ? -a2 : a2;
					if (m > d) d = m;
				}
			}
			if (d > diag.clipDevMax) diag.clipDevMax = d;
		}
		// v1.07c: a reprojection matrix that maps clip space to clip space is
		// affine, so its last row is (tx,ty,tz,1) and [3].w is exactly 1. This
		// is the one criterion here that does NOT grow with frame time, which
		// matters: clipDev legitimately rises with both camera speed and frame
		// interval, so a large clipDev alone proves nothing. A w away from 1
		// means the inverse and the `prev` matrix were built from different
		// cameras -- the defect fixed at the invert site above.
		diag.clipW = c.clipToPrevClip[3].w;
		{
			const float wDev = diag.clipW > 1.0f ? (diag.clipW - 1.0f)
			                                     : (1.0f - diag.clipW);
			static std::uint32_t wWarned = 0;
			if (wDev > 0.01f && wWarned < 20u) {
				++wWarned;
				SKSE::log::warn("[MOTION] clipToPrevClip[3].w={:.6f} (must be 1) - "
					"the inverse and the previous matrix came from different "
					"cameras; DLSS-G is reprojecting with a non-affine matrix",
					diag.clipW);
			}
		}
		if (curOk) ++diag.camValid; else ++diag.camInvalid;
		const bool camValid = curOk;   // 下游的 reset 边沿语义保持不变
		// =====================================================================

		// v0.56 probe: DLSS-G reprojects each generated frame with clipToPrevClip.
		// Transfusion's log shows clipToPrev=identity for the first frames of the run,
		// which is correct on a loading screen but catastrophic during gameplay - an
		// identity matrix tells DLSS-G the camera never moved, so the camera part of
		// the reprojection is silently dropped. This settles which it is: run, walk
		// around, and read maxDevFromIdentity. Near 0 while moving = the matrix is not
		// live and the previous view-projection is not being updated.
		// v0.61: the MOTION / CAM probes that used to live here were folded into the
		// single [XRAY] heartbeat further down (after the menu/reset decision), so
		// every number that decides “where does the flicker come from” lands on ONE
		// line together with the menu state and the constants accounting.

		c.jitterOffset = { -Get().jitterX, -Get().jitterY };  // v0.34：DLSS Halton jitter（对齐 CS，之前恒 0）
		// v0.34（对齐 CS Streamline.cpp:484-488）：菜单打开时运动矢量无效 → reset 让
		// DLSSG 不用旧数据插帧（用户“停在菜单背景”——菜单帧插错 = 视觉错乱）。
		// 菜单检测：主菜单/加载菜单/暂停菜单（BGSM 菜单 UI 绘制时无运动矢量）。
		// v0.59：reset 改为**边沿触发**（只在进入菜单的那一帧置位）。
		// 之前菜单打开期间每帧都置 eTrue ⇒ 每帧告诉 DLSS-G“这是全新序列、丢掉历史”，
		// 而 DLSS-G 仍在输出 4 帧 ⇒ 每个生成帧都从零历史重建 ⇒ 主菜单静止画面持续闪，
		// 帧节拍抖动（Transfusion [PERF] Jitter 4.9~15.3ms）。
		// 证据：2026-09-17 21:18 运行，Transfusion [MOTION] 连续 call=0..2 上 reset 恒为 1。
		// 边沿触发保留 v0.34 的意图（进菜单时丢弃菜单前遗留的旧数据），但不再每帧打断
		// DLSS-G 的 temporal 状态。
		// v0.70: read the menu state that PollMenuState() already sampled for THIS
		// frame. It is no longer computed here, because this function only runs from
		// EvaluateDLSSG - which the menu guard itself skips - so while a menu was
		// open none of this ran and the guard left no trace to verify.
		const bool isMenuOpen = diag.menuOpenNow;
		const bool menuEdgeUp = menuResetPending;
		menuResetPending = false;
		// v0.64：相机数据断裂与菜单边沿同类 —— 基于旧矩阵建立的重投影历史已经无效，
		// 丢一次即可（边沿，不是每帧，v0.59 的教训）。
		thread_local bool s_wasCamValid = true;    // v0.66：同上
		const bool camEdgeDown = !camValid && s_wasCamValid;
		s_wasCamValid = camValid;
		c.reset = (menuEdgeUp || camEdgeDown) ? sl::Boolean::eTrue : sl::Boolean::eFalse;
		if (c.reset == sl::Boolean::eTrue) {
			++diag.resetTrue;
			// v1.07: hand the same edge to the camera lock. c.reset already
			// tells DLSS-G to discard its history; the locked camera family is
			// part of that history. This also covers camEdgeDown, which the
			// menu transition above does not.
			Get().snapLockReleasePending = true;
		}

		// v0.62: mvecScale is computed HERE, above the heartbeat, because the
		// heartbeat used to print c.mvecScale before the assignment below had run -
		// the 21:40 run's only sample therefore read mvec=(3.4e38,3.4e38), i.e.
		// uninitialised FLT_MAX, and would have been read as a real defect. Order
		// matters for a diagnostic line.
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

		// ===== [XRAY] heartbeat (v0.61) =====
		// One line every 240 real frames carrying every number that decides where a
		// remaining flicker comes from, all sampled in the SAME frame and next to the
		// menu state and the constants accounting. It replaces the four separate
		// probes (MOTION / CAM / RESET / constants) that fired on four different
		// cadences, which made “which combination was true when it flickered”
		// unanswerable from the log.
		{
			static std::uint32_t xrayTick = 0;
			// v0.62: 30 frames OR 2 s, whichever comes first. The 240-frame cadence
			// produced exactly ONE heartbeat in the entire 21:40 run (119 real
			// frames), so that run answered none of the questions it was
			// instrumented for.
			static auto xrayLastPrint = std::chrono::steady_clock::now();
			const bool xrayTimeUp = std::chrono::duration<double>(
				std::chrono::steady_clock::now() - xrayLastPrint).count() >= 2.0;
			if (++xrayTick % 30 == 1 || xrayTimeUp) {
				xrayLastPrint = std::chrono::steady_clock::now();
				auto devOf = [](const Matrix& m) {
					float d = 0.0f;
					for (int r = 0; r < 4; ++r)
						for (int cc = 0; cc < 4; ++cc) {
							const float id = (r == cc) ? 1.0f : 0.0f;
							float v = m.data[r][cc] - id;
							if (v < 0.0f) v = -v;
							if (v > d) d = v;
						}
					return d;
				};
				// max |clipToPrevClip - I|: DLSS-G reprojects every generated frame with
				// this matrix, so ~0 while the player is moving means the camera term of
				// the reprojection is silently dropped.
				float clipDev = 0.0f;
				for (int row = 0; row < 4; ++row) {
					const sl::float4 r4 = c.clipToPrevClip[row];
					const float v4[4] = { r4.x, r4.y, r4.z, r4.w };
					for (int col = 0; col < 4; ++col) {
						const float id = (row == col) ? 1.0f : 0.0f;
						float d = v4[col] - id;
						if (d < 0.0f) d = -d;
						if (d > clipDev) clipDev = d;
					}
				}
				auto hist = [](const std::uint64_t (&h)[8]) {
					std::string s;
					for (int i = 0; i < 8; ++i) {
						if (i) s += '/';
						s += std::to_string(h[i]);
					}
					return s;
				};
				auto modeOf = [](const std::uint64_t (&h)[8]) {
					std::uint32_t best = 0;
					for (std::uint32_t i = 0; i < 8; ++i)
						if (h[i] > h[best]) best = i;
					return best;
				};
				// Real frame time across the 240 frames since the previous heartbeat. This
				// is the one column that separates the two ways a flicker happens: a
				// steady real= with a non-identity clipDev means the reprojection itself
				// is wrong, while a jittering real= means the pacer lost its rhythm.
				// Every other number on this line can read clean in both cases.
				// v0.62: divide by the ticks actually elapsed instead of the
				// hardcoded 240, and skip the first sample - its delta is (now - now)
				// by construction, which is why 21:40 reported “real=0.00ms”.
				static auto xrayPrev = std::chrono::steady_clock::now();
				static bool xrayPrevValid = false;
				static std::uint32_t xrayTickAtPrev = 0;
				const auto xrayNow = std::chrono::steady_clock::now();
				const std::uint32_t xrayTicks =
					(xrayTick > xrayTickAtPrev) ? (xrayTick - xrayTickAtPrev) : 1u;
				xrayTickAtPrev = xrayTick;
				const double realMs = xrayPrevValid
					? std::chrono::duration<double, std::milli>(xrayNow - xrayPrev).count() /
						static_cast<double>(xrayTicks)
					: 0.0;
				xrayPrev = xrayNow;
				xrayPrevValid = true;
				SKSE::log::info("[XRAY] serial={} menu={} world={} edges={} resetTrue={} menuOpen={} reset={} | "
					"consts ok={} fail={} lastR={} | presented all={} world={} menu={} | "
					"real={:.2f}ms | mvecScale=({:.3f},{:.3f}) flags={:#x} | jitter=({:.4f},{:.4f}) "
					"clipDev={:.6f} clipW={:.6f} curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) "
					"prevPos=({:.1f},{:.1f},{:.1f}) | dt min/avg/max={:.2f}/{:.2f}/{:.2f}ms n={} "
					"capUs={} mult(acc/pres)={}/{} longFrames={} cam(ok/inv)={}/{} camPrev(ok/used)={}/{} | "
					"reproj src={} engPrevEqCur={}/{} engPrevZero={} frozen={} "
					"dvd(ok/used)={}/{} err={:.3g} curMag={:.3g} engPrevMag={:.3g} "
					"clipDevMax={:.4f} hist(hit/miss)={}/{} seed={} missGood={} " 
					"det(min/max)={:.3f}/{:.3f} " 
					"fix(src={} dev={:.6g}) "
					"detGuard={} detHold={} tid(a/b/c)={:#x}/{:#x}/{:#x} calls={}/{}/{} | "
					"snap(acc/jmp/re/zero/arr/frozen/shape/rejPct)={}/{}/{}/{}/{}/{}/{} {:.1f}% "
					"shapeRej(own)={:.1f}% "
					"gate(sawDiff/consecRej/frozenRep/resets/id/diff)={}:{}/{}/{}/{}/{} "
					"mapHit(perFrame/unmap)={}/{} dist(last/acc)={:.1f}/{:.1f} | "
					"lock(pub/hold/re/still)={}/{}/{}/{} proj00={:.6g} famRej={} | "
					"mfg(hwMax/reqMax/rungsSkipped)={}/{}/{} inSetOptions={}",
					frameSerial, diag.menuFrames, diag.worldFrames, diag.menuEdges, diag.resetTrue,
					isMenuOpen ? 1 : 0, static_cast<int>(c.reset),
					diag.constsOk, diag.constsFail, diag.constsLastR,
					hist(diag.presentedAll), hist(diag.presentedWorld), hist(diag.presentedMenu),
					realMs,
					c.mvecScale.x, c.mvecScale.y, diag.lastFlags,
					Get().jitterX, Get().jitterY, clipDev, diag.clipW, devOf(curVP), devOf(prevVP),
					a_fb.CameraPosAdjust[0], a_fb.CameraPosAdjust[1], a_fb.CameraPosAdjust[2],
					a_fb.CameraPreviousPosAdjust[0], a_fb.CameraPreviousPosAdjust[1],
					a_fb.CameraPreviousPosAdjust[2],
					diag.winMinMs, diag.winN ? (diag.winSumMs / static_cast<double>(diag.winN)) : 0.0,
					diag.winMaxMs, diag.winN, diag.reflexCapUs,
					dlssgAcceptedFrames + 1, diag.presentedPrev, diag.longFrames,
					diag.camValid, diag.camInvalid,
					diag.camPrevOk, diag.camPrevUsed,
					(diag.reprojSource == 2 ? "fixed"
						: (diag.reprojSource ? "derived" : "engine")),
					diag.engPrevEqCur, diag.engPrevEqCur + diag.engPrevDiffers,
					diag.engPrevZero, diag.engCurFrozenRun,
					diag.derivedMatch, diag.derivedUsed, diag.derivedMatchErr,
					diag.curMagLast, diag.engPrevMagLast,
					diag.clipDevMax,
					diag.prevHistoryHits, diag.prevHistoryMiss,
					diag.prevSeededFromEngine, diag.prevMissUsedLastGood,
					((diag.detMin > diag.detMax) ? 0.0f : diag.detMin),
					((diag.detMin > diag.detMax) ? 0.0f : diag.detMax),
					diag.reprojSource, diag.fixedVpDev,
					diag.detGuard, diag.detHold,
					diag.tidA, diag.tidB, diag.tidC,
					diag.tidCallsA, diag.tidCallsB, diag.tidCallsC,
					Get().snapAccept, Get().snapRejectJump, Get().snapRelock,
					Get().snapRejectZero, Get().snapArrivals, Get().snapFrozenReject,
					Get().snapRejectShape,
					Get().snapArrivals
						? 100.0 * static_cast<double>(Get().snapRejectShape)
							/ static_cast<double>(Get().snapArrivals)
						: 0.0,
					Get().snapArrivals
						? 100.0 * static_cast<double>(Get().snapRejectShape)
							/ static_cast<double>(Get().snapArrivals)
						: 0.0,
					Get().snapSawDifferentSinceRepeat ? 1 : 0, Get().snapConsecReject,
					Get().snapFrozenRepeats, Get().snapFrozenResets,
					Get().snapIdenticalArrivals, Get().snapDifferentArrivals,
					Get().mapPerFrameHits, Get().unmapPerFrameHits,
					Get().snapLastDist, Get().snapAcceptDist,
					Get().snapLockPublish, Get().snapLockHold,
					Get().snapLockRelock, Get().snapLockStill,
					Get().snapLockProjValid ? Get().snapLockProj00 : 0.0f,
					Get().snapLockFamilyRej,
					diag.hwMaxSeen, diag.reqStepMax, diag.mfgRungsSkipped,
					mfgInSetOptions ? 1 : 0);

				// Self-derived verdict: the log states the conclusion instead of leaving
				// the reader to combine four numbers by hand.
				const std::uint32_t want = std::max<std::uint32_t>(1u, dlssgAcceptedFrames);
				const std::uint32_t wm = modeOf(diag.presentedWorld);
				const std::uint32_t mm = modeOf(diag.presentedMenu);
				std::string vd;
				if (Get().snapRejectJump > 0 && Get().snapRejectJump >= Get().snapAccept)
					vd = "PROBLEM the perFrame buffer carries TWO cameras: accepted " +
					     std::to_string(Get().snapAccept) + " / jump-rejected " +
					     std::to_string(Get().snapRejectJump) + " (relock " +
					     std::to_string(Get().snapRelock) + ") -> cur/prev keep spanning two "
					     "sources, so det(inv(cur) x prev) is never 1 and DLSS-G is told the "
					     "camera did not move";
				else if (diag.detGuard > 0)
					vd = "PROBLEM " + std::to_string(diag.detGuard) + " frame(s) had a "
					     "MATHEMATICALLY ILLEGAL clipToPrevClip (det outside [0.5,2.0], "
					     "range seen = " + std::to_string(diag.detMin) + " .. " +
					     std::to_string(diag.detMax) + ") -> " + std::to_string(diag.detHold) +
					     " of them held the last legal matrix (identity would tell DLSS-G the "
					     "camera never moved, which is a lie)";
				else if (diag.tidCallsB > 10)
					vd = "PROBLEM a second thread PERSISTENTLY calls slSetConstants (a=" +
					     std::to_string(diag.tidCallsA) + " calls, b=" +
					     std::to_string(diag.tidCallsB) + " calls) -> thread_local history is "
					     "required, not shared statics";
				else if (diag.engPrevDiffers == 0 &&
					(diag.engPrevEqCur + diag.engPrevZero) > 0)
					vd = std::string("flicker cause: the engine previousViewProj is USELESS on every ") +
					     "frame (== cur " + std::to_string(diag.engPrevEqCur) + ", zero " +
					     std::to_string(diag.engPrevZero) + ") -> v0.65 uses self-maintained history; "
					     "moving frames must show clipDevMax > 0 (identity would be 1.000000)";
				else if (diag.derivedChecked && diag.derivedMatch == 0 && diag.engCurFrozenRun > 30)
					vd = "PROBLEM engine viewProj frozen " + std::to_string(diag.engCurFrozenRun) +
					     " frames AND the derived fallback failed its cross-check (maxErr=" +
					     std::to_string(diag.derivedMatchErr) + ") -> clipToPrevClip stays identity";
				else if (diag.engCurFrozenRun > 120 && diag.derivedUsed == 0)
					vd = "PROBLEM engine viewProj frozen for " + std::to_string(diag.engCurFrozenRun) +
					     " frames and NO corrected source was used (fixedVpDev=" +
					     std::to_string(diag.fixedVpDev) + ") -> clipToPrevClip may collapse to identity";
				else if (diag.prevHistoryMiss * 4 > (diag.prevHistoryHits + diag.prevHistoryMiss))
					vd = "PROBLEM reprojection history missing on " +
					     std::to_string(diag.prevHistoryMiss) + " frames";
				else if (diag.constsFail != 0)
					vd = "PROBLEM constants rejected (fail=" + std::to_string(diag.constsFail) +
					     ", lastR=" + std::to_string(diag.constsLastR) +
					     ") -> frame slot not advancing, per-frame data stays stale";
				else if (want <= 1u)
					vd = "PROBLEM runtime accepted no interpolation (accepted=0) -> no DLSS-G kernel in effect";
				else if (diag.menuOpenNow && diag.menuFrames > 60 && mm >= want)
					vd = "PROBLEM menu OPEN RIGHT NOW generates " + std::to_string(mm) +
					     " frames/real frame -> menu guard NOT effective (flag stripped by the shim?)";
				else if (diag.worldFrames > 60 && wm != want)
					vd = "PROBLEM world ran at " + std::to_string(wm) + " frames/real frame but " +
					     std::to_string(want) + " was accepted";
				else if (diag.menuFrames <= 60)
					vd = "inconclusive: menu never sampled for long enough (need >60 menu frames)";
				else
					vd = "clean: constants ok, menu throttled, world at the accepted rate";
				SKSE::log::info("[XRAY] VERDICT: {}", vd);
				// The window describes exactly one heartbeat interval.
				diag.winMinMs = 0.0;
				diag.winMaxMs = 0.0;
				diag.winSumMs = 0.0;
				diag.winN = 0;
				diag.longFrames = 0;
				diag.clipDevMax = 0.0f;
			}
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
		//   sl_consts.h: “scale factors used to normalize motion vectors (so the
		//   values are in [-1,1] range)“
		//   ProgrammingGuideDLSS_G.md: “values in {-1,1} range -> scale factor
		//   should be {1,1}“; not in range -> ”adjusted so that values end up in
		//   [-1,1] range“
		//   open-shaders Streamline.cpp: “The standard full-frame DLSS path ...
		//   must keep mvecScale at identity or DLSS massively over-estimates motion“
		//
		// The v0.49k comment states its own premise - “engine mvec = displacement/2560”
		// - and a value reaching 1.0 for a full-screen pan is already inside [-1,1],
		// so that premise argues for identity. But 1.5 was tuned in-game against a
		// different defect (the depth/mvec extent that v0.56 removed), so it is not
		// discarded on inference alone: it becomes one INI line, defaulted to the old
		// behaviour, so the A/B costs no rebuild.
		c.motionVectors3D = sl::Boolean::eFalse;
		c.motionVectorsInvalidValue = FLT_MIN;
		c.orthographicProjection = sl::Boolean::eFalse;
		c.motionVectorsDilated = sl::Boolean::eFalse;
		c.motionVectorsJittered = sl::Boolean::eFalse;
		c.depthInverted = sl::Boolean::eFalse;

		// v0.58: success/failure accounting (throttled). This is the direct
		// evidence for “are per-frame constants actually reaching DLSS-G”:
		// climbing fail=27 (eErrorDuplicatedConstants) means the frame slot is
		// not advancing, constants stay stale, and every generated frame is
		// reprojected with old motion/jitter -> flicker.
		if (SL_FAILED(r, slSetConstants(c, *frameToken, viewport))) {
			++diag.constsFail;
			diag.constsLastR = static_cast<std::int32_t>(r);
			// v0.61: only the first rejection gets its own line. A rejected call used
			// to print on every frame and drown the log; the running totals - and in
			// particular whether they keep climbing - live in the [XRAY] heartbeat.
			if (diag.constsFail == 1)
				SKSE::log::warn("[Streamline] slSetConstants FAILED first time: r={} "
					"(27 = eErrorDuplicatedConstants => frame slot not advancing); totals in [XRAY]",
					static_cast<std::int32_t>(r));
		} else {
			++diag.constsOk;
		}
	}

	// v0.3：DLSSG 插帧（D3D12 路径）——设置选项（多倍帧生成 clamp 到硬件上限）
	void Streamline::SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,
		std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat,
		bool a_enable)
	{
		if (!initialized || !featureDLSSG || !slDLSSGSetOptions)
			return;
		// v0.79 (menu-guard decoupling): the multiplier ladder that used to sit
		// further down is now ProbeMfgLadder(), called from Present() BEFORE the
		// menuBlock/else-if fork - so it runs once per real frame whatever the
		// guard decides. The probe result is still collected here on unblocked
		// frames: Present() calls ProbeMfgLadder(), then this function, and the
		// result fields are left alone by the probe until then.
		// v0.71: the “window cannot be shown” path. Mode only, and an early return:
		// the multiplier ladder below must not run here, or every alt-tab would
		// consume probe steps and log false rejections. Called on the focus edge
		// only, never per frame.
		if (!a_enable) {
			sl::DLSSGOptions off{};
			off.mode = sl::DLSSGMode::eOff;
			const sl::Result offRes = slDLSSGSetOptions(viewport, off);
			SKSE::log::warn("[XRAY] DLSSG mode -> OFF (result {}): the window is not in "
				"the foreground, so frame generation stops and Present uses DO_NOT_WAIT "
				"until it comes back", static_cast<int>(offRes));
			return;
		}
		sl::DLSSGOptions opts{};
		opts.mode = sl::DLSSGMode::eOn;
		// v0.60: hand fullscreen-menu handling to the SDK instead of guessing.
		// sl_dlss_g.h ships DLSSGFlags::eEnableFullscreenMenuDetection (1 << 4)
		// and we were leaving it unset (`flags{}` == 0), so DLSS-G kept generating
		// frames with a fullscreen menu up -- buttons, text and the fading backdrop
		// all got interpolated as 3D content.  Observed evidence: Transfusion's
		// [MOTION] dump printed reset=1 on every consecutive frame while the main
		// menu was open, i.e. the SDK was told “new sequence” once per frame.
		// Keep in sync with the v0.59 edge-triggered reset: that one limits how
		// often we reset, this one stops the generation altogether.
		opts.flags |= sl::DLSSGFlags::eEnableFullscreenMenuDetection;
		diag.lastFlags = static_cast<std::uint32_t>(opts.flags);
		{
			static bool menuFlagLogged = false;
			if (!menuFlagLogged) {
				menuFlagLogged = true;
				SKSE::log::info("[Streamline] DLSSG flags: fullscreenMenuDetection=on (v0.60) raw={:#x}",
					diag.lastFlags);
				// v0.61 environment banner - the single line that would have saved a
				// whole debug round on 2026-09-17. `virtual` is what THIS process sees
				// through Windows DPI virtualization, `physical` is the real display
				// mode, `swapchain` is what DXGI actually got. A swapchain that does not
				// match the display mode breaks Independent Flip and the pacer; and
				// virtual != physical means every window rect and system metric the
				// plugin reads is scaled - which is what made “window 2560x1440” look
				// like a 1440p window on a 4K screen when it was in fact fullscreen.
				const int vw = ::GetSystemMetrics(SM_CXSCREEN);
				const int vh = ::GetSystemMetrics(SM_CYSCREEN);
				DEVMODEA dm{};
				dm.dmSize = sizeof(dm);
				int pw = 0, ph = 0, hz = 0;
				if (::EnumDisplaySettingsA(nullptr, ENUM_CURRENT_SETTINGS, &dm)) {
					pw = static_cast<int>(dm.dmPelsWidth);
					ph = static_cast<int>(dm.dmPelsHeight);
					hz = static_cast<int>(dm.dmDisplayFrequency);
				}
				const auto& sc = Get().dx12SwapChain;
				SKSE::log::info("[XRAY] env: virtual={}x{} physical={}x{}@{}Hz swapchain={}x{} "
					"render={:.4f} dpiAware={} | {}",
					vw, vh, pw, ph, hz, a_width, a_height, sc.renderScaleX,
					::IsProcessDPIAware() ? 1 : 0,
					(vw == pw && vh == ph) ? "virtual==physical (no DPI scaling)"
					                       : "virtual!=physical => DPI-virtualized process");
				SKSE::log::info("[XRAY] diag active v1.07c (compiled " __DATE__ " " __TIME__ ")");
				// v0.89: the live fix state is reported on the HEARTBEAT, not here.
				// v0.88 printed it at this spot, which runs once at boot before any
				// world camera exists -- it therefore always read reprojSource=0
				// fixedVpDev=-1 and looked like “the fix is dead”. It was not; the
				// heartbeat showed src=fixed. A diagnostic printed at the wrong
				// moment is a diagnostic that lies.
			}
		}
		// v0.31（对齐 open-shaders ConfigureDLSSG）：多倍帧生成——
		// numFramesToGenerate = clamp(INI DLSSGFramesToGenerate, 1, 硬件上限)。
		// v0.50 上限：effectiveMax = max(硬件上限, 覆盖值)。
		// overrides==0 -> 完全跟随硬件上报（50 系仍可 4X，零功能倒退）；
		// overrides>0 -> 抬到覆盖值（老卡解锁路径，由外部内核解锁器提供内核）。
		const std::uint32_t effectiveMax = std::max<std::uint32_t>(1, dlssgEffectiveMax);
		// v0.79: the ladder itself moved to ProbeMfgLadder() (called from Present
		// before the menu guard). Here we only consume the step it produced.
		// (v0.51 fallback kept for direct callers that skip the probe.)
		if (mfgProbeStep == 0 || mfgProbeStep > effectiveMax)
			mfgProbeStep = std::clamp<std::uint32_t>(Get().settings.dlssgFramesToGenerate, 1, effectiveMax);
		dlssgFramesToGenerate = mfgProbeStep;   // = 本次请求值（是否被接受见下方结果处理）
		// v1.03: when an external unlocker owns the multiplier, leave
		// numFramesToGenerate alone. Transfusion replaces slDLSSGSetOptions via
		// slGetFeatureFunction and re-writes this field on the way through, so
		// writing it here does not change the outcome - it only makes this plugin
		// a second writer, and the runtime answers two writers with
		// eErrorInvalidState(38) plus a multi-second frame. Its own log shows the
		// 4x it installs is accepted; that is the value worth keeping.
		// v1.05: REWRITE of the v1.03 hand-over. The old else-branch read
		//
		//     opts.numFramesToGenerate = std::max(1u, opts.numFramesToGenerate);
		//
		// which looks like "keep what the unlocker wrote" but is not: opts is a
		// freshly zero-initialised local, so that expression is std::max(1u, 0u)
		// and it evaluated to 1 -- 2x -- on EVERY call. Transfusion installs 4x
		// through its own slDLSSGSetOptions wrapper and this plugin then walked
		// over it with 2x. The runtime was asked for 4x and 2x alternately, its
		// pacer never converged, and the render thread sat inside Present(0).
		//
		// That is the 19:16 freeze, and it is why handing the multiplier over
		// made things WORSE than the two-writer case it was meant to fix: at
		// least a second writer writes a real number.
		//
		// v1.05: this plugin writes the multiplier itself, always, and never
		// above the runtime ceiling (ApplyMfgOverride already clamped the
		// ceiling to a_hwMax when no unlocker is present, and the probe ladder
		// walks up only on observed acceptance). The unlocker may still re-write
		// it inside its own wrapper; that is its business. What must not happen
		// is this plugin contributing a value it invented from a zeroed struct.
		opts.numFramesToGenerate = dlssgFramesToGenerate;  // 1=2x 2=3x 3=4x 插帧
		opts.numBackBuffers = 3;
		opts.colorWidth = a_width;
		opts.colorHeight = a_height;
		// v0.56 (fix: declared != actual). sl_dlss_g.h defines mvecDepthWidth/Height as
		// “Expected width/height of the input render targets (depth, motion-vector
		// buffers etc)“ - the size of THOSE buffers, not the swap chain. The caller
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
			if (!mfgProbeLatched || dlssgAcceptedFrames != mfgProbeStep ||
				mfgProbeWasBlocked) {
				SKSE::log::info("[Streamline] MFG probe: runtime ACCEPTED {}x ({} interpolated frames) | "
					"runtimeReportsMax={}x overrideAsksMax={}x blocked={}",
					mfgProbeStep + 1, mfgProbeStep, dlssgMaxFramesToGenerate + 1, effectiveMax + 1,
					mfgProbeWasBlocked ? 1 : 0);
			}
			mfgProbeLatched = true;
			mfgProbeWasBlocked = false;
			dlssgAcceptedFrames = mfgProbeStep;
		} else {
			dlssgAcceptedFrames = 0;
			const std::uint32_t rejected = mfgProbeStep;
			mfgProbeWasBlocked = false;   // v0.79: this block is strictly per-frame
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
		// v0.79: no note here on purpose - this block only runs on unblocked
		// frames, so there is no blocked result to disclaim. The note belongs
		// where ProbeMfgLadder() is consumed on a blocked frame.

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
				// v0.61: classify every presented sample by menu/world and keep a
				// histogram. The run then answers “was generation throttled in the menu?”
				// without grepping interleaved probes: if the runtime honours
				// eEnableFullscreenMenuDetection, presentedMenu collapses to 1 while
				// presentedWorld holds at the accepted multiplier. `menuOpenNow` is
				// written once per frame by CheckFrameConstants, which runs after this
				// call, so the split can lag by at most one frame.
				{
					const std::uint32_t p = dlssgFramesPresentedLast;
					const std::uint32_t idx = p > 7u ? 7u : p;
					++diag.presentedAll[idx];
					if (diag.menuOpenNow)
						++diag.presentedMenu[idx];
					else
						++diag.presentedWorld[idx];
					diag.presentedPrev = p;
				}
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

	// v0.79 (menu-guard decoupling): the multiplier ladder, lifted out of
	// SetDLSSGOptions so Present() can run it BEFORE the menu guard.
	//
	// Why it must not live behind the guard: the ladder is *finding out* what the
	// runtime accepts. While a menu is up Present() never reached it, so a
	// REJECTED step could not step down - it stayed pinned at the rejected value
	// and the next unblocked frame started the descent from there again. Nothing
	// in the tree said so: the “runtime REJECTED” warn was rate-limited to the
	// first occurrence per step, so the 08:59 run looked like a single rejection
	// when it was one per frame for 18 s.
	//
	// Measured (2026-09-18 08:59, 45.1 s, 1403 frames):
	//   menu window 08:59:29.014 .. 08:59:47.091 (18.08 s), generation = 0
	//   INI asks 4x, runtimeReportsMax = 2x, no ACCEPTED line inside the window
	//   => 08:59:49.097 is when 2x was finally in effect, i.e. AFTER the menu
	// v1.03: one long frame must not cascade into a deadlock.
	//
	// Evidence (DynamicShaderFrameGen.watchdog.log, 2026-09-18 18:23):
	//   [159695602] 18:23:20.025 frames=1 silent=14865ms stage=d3d11 Wait ...
	//   [159700418] 18:23:24.841 frames=1 silent=19681ms stage=d3d11 Wait ...
	// frames=1 for the entire process uptime: one real frame was ever presented
	// and every later one sat inside the DLSS-G call. The engine was not stuck on
	// its own - a single slow frame turned into a permanent one because the probe
	// kept re-arming the feature that was stalling.
	//
	// This governor is deliberately dumb: measure the interval that just elapsed,
	// and after a frame longer than kMfgStallBlockUs stop arming DLSS-G for a
	// while. It never disables the feature for good, and it never touches the
	// ladder - it only decides whether THIS frame is allowed to talk to the
	// runtime. Recovery is automatic: once frames come back under the bar the
	// probe resumes from the same step it froze at.
	bool Streamline::MfgStallGovAllow(std::uint32_t a_frameUs)
	{
		// 150 ms. The intended cadence at 2x/160 Hz is ~6.3 ms and even the
		// rejected 4x frames measured 6.29 ms of GPU work (capUs=6289), so
		// anything at 150 ms is not frame generation being expensive - it is the
		// call not returning. 24 frames of cooldown is ~0.15 s at 160 Hz: long
		// enough to let a one-off settle, short enough that a genuine hiccup does
		// not cost the user the feature.
		constexpr std::uint32_t kMfgStallBlockUs = 150000u;
		constexpr std::uint32_t kMfgStallCooldownFrames = 24u;
		if (mfgProbeSkipAll) {
			mfgInSetOptions = false;
			return false;
		}
		if (mfgProbeCooldown > 0) {
			--mfgProbeCooldown;
			mfgInSetOptions = false;
			return false;   // still cooling down - do not touch DLSS-G this frame
		}
		if (a_frameUs > kMfgStallBlockUs) {
			mfgProbeStallMs = a_frameUs / 1000u;
			mfgProbeCooldown = kMfgStallCooldownFrames;
			SKSE::log::warn("[MFG] stall governor: frame took {} ms (budget {} ms) - pausing the MFG probe "
				"for {} frames so a single slow frame cannot be fed back into itself. step held at {}x, "
				"accepted {}x", mfgProbeStallMs, kMfgStallBlockUs / 1000u, kMfgStallCooldownFrames,
				mfgProbeStep + 1, dlssgAcceptedFrames ? dlssgAcceptedFrames + 1 : 0);
			mfgInSetOptions = false;
			return false;
		}
		return true;
	}

	void Streamline::ProbeMfgLadder()
	{
		if (!initialized || !featureDLSSG || !slDLSSGSetOptions)
			return;
		// v1.05: the ladder runs even with an unlocker installed. v1.03 skipped it,
		// on the theory that the unlocker had already found the highest multiplier.
		// The 19:16 run shows why that was wrong: the unlocker never wrote anything
		// that frame (its own log stops at 07:29), so with the ladder also disabled
		// NOTHING in the process was driving numFramesToGenerate, and the runtime sat
		// on a value no one had set. The ladder costs one probe per step and it is the
		// only component that turns "is 4x accepted?" into an observed fact rather
		// than an assumption about what some other module is doing.
		//
		// The v1.03 concern was real but belongs somewhere else: a rejected rung used
		// to cost a whole multi-second frame (18:23: 19945 ms). That is handled by
		// MfgStallGovAllow(), which parks the ladder for 24 frames after any frame
		// longer than 150 ms. Skipping the ladder entirely was the wrong remedy.
		auto& fg = Get();
		const std::uint32_t effectiveMax = std::max<std::uint32_t>(1, dlssgEffectiveMax);
		if (mfgProbeStep == 0 || mfgProbeStep > effectiveMax) {
			// v0.79: Streamline has no `settings` member of its own - LoadInterposer
			// takes a const Settings& and the live copy lives on FrameGen, reached
			// through Get(). This is the same access SetDLSSGOptions already uses
			// for mfgMaxFramesOverride / mvecScaleOverride.
			mfgProbeStep = std::clamp<std::uint32_t>(fg.settings.dlssgFramesToGenerate, 1, effectiveMax);
		}
		// Re-assert the step every frame. SetDLSSGOptions() re-sends the full option
		// struct every frame anyway, so this freezes exactly what that call would
		// have frozen, and it cannot re-arm the ladder while the menu is up.
		dlssgFramesToGenerate = mfgProbeStep;

		// Find the colour size the same way SetDLSSGOptions does - a probe at the
		// wrong colour/mvec size is rejected for the wrong reason. Format is part
		// of the option struct too, so pass the swap chain's own.
		auto& dx = fg.dx12SwapChain;
		std::uint32_t cw = dx.swapChainDesc.Width;
		std::uint32_t ch = dx.swapChainDesc.Height;
		if (cw == 0 || ch == 0) {
			WrappedResource* c = dx.swapChainBufferWrapped;
			if (c && c->resource11) {
				D3D11_TEXTURE2D_DESC rd{};
				c->resource11->GetDesc(&rd);
				cw = rd.Width;
				ch = rd.Height;
			}
		}
		if (cw == 0 || ch == 0)
			return;   // no swap chain yet - the probe would be rejected for the wrong reason
		// v1.03: bracket the call. The watchdog samples this flag from its own
		// thread, so the next stall is attributed instead of guessed: a line that
		// reads stage=d3d11 SetOptions means the runtime never returned, while
		// stage=d3d11 Wait means we are blocked on the engine instead. The whole
		// point of the 18:23 investigation was that those two were
		// indistinguishable, and the blame went to the wrong place for two days.
		mfgInSetOptions = true;
		g_inSetOptions.store(1);
		SetDLSSGOptions(cw, ch, cw, ch, dx.swapChainDesc.Format);
		g_inSetOptions.store(0);
		mfgInSetOptions = false;
	}

	void Streamline::ProbeMfgLadderNote(bool a_blocked)
	{
		// One line per edge, so the next capture can tell “the guard engaged” from
		// “the probe never ran” - the two looked identical in every earlier run.
		if (a_blocked == mfgProbeLoggedBlocked)
			return;
		mfgProbeLoggedBlocked = a_blocked;
		if (a_blocked) {
			SKSE::log::info("[MFG] probe RUNS while the menu guard skips DLSS-G: the ladder is "
				"calibrated on the frame the world is entered (v0.79). step advertised={}x "
				"accepted={}x latched={}",
				mfgProbeStep + 1, dlssgAcceptedFrames + 1, mfgProbeLatched ? 1 : 0);
		} else {
			SKSE::log::info("[MFG] probe edge: menu guard released, SetDLSSGOptions resumes on this "
				"frame. step advertised={}x accepted={}x latched={}",
				mfgProbeStep + 1, dlssgAcceptedFrames + 1, mfgProbeLatched ? 1 : 0);
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

		// v0.25.3（用户 2026-08-30“勾选 DLSSG 没生效”——16:35 日志实锤）：**DLSS-G
		// 不做显式 slAllocateResources / slEvaluateFeature**——与 CS 完全一致（CS 只对
		// kFeatureDLSS 超分调 slEvaluateFeature，对 DLSS_G 从不调）：
		//   1. sl.dlss_g 插件的 evaluateFeature 回调恒 0x0（正常）——DLSSG 通过
		//      Present 钩子（slHookPresent/slHookPresent1，已注册 OK）在 presentCommon
		//      时自动插帧（16:35 presentCommon 每帧在跑 = 链已通）
		//   2. 显式 slEvaluateFeature(DLSS_G) 恒 28（eErrorMissingOrInvalidAPI）→
		//      触发上方 auto-disable（>120 次）→ 帧生成被自己禁用 → “没效果”
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
		// “The area of the tagged resource to use (if using the entire resource leave
		// as null)“. Declaring 1706x960 therefore told DLSS-G to use only the top-left
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
		// slEvaluateFeature——此处仅返回 true 表示“已标记资源”。
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
	// → 插帧 pacing 乱 → 频闪（SL 日志 “Plugin 'sl.reflex' has no registered hooks”
	// + dlss_g 每帧 “frame 1” 警告实锤）。返回后发 eSimulationStart（模拟开始）。
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
		// v0.63（限速器作用面搞错了 —— 真正根因）：这个上限描述的是**上屏 flip 节拍**，
		// 不是渲染帧率。v0.54 按“渲染帧率”反推（刷新率 / 总倍数 - 1），等于把 flip 节流
		// 到 39/s；而 DLSS-G 每真实帧要发 4 个 flip ⇒ 渲染侧被压成 39/4 = 9.75fps。
		// 实测（2026-09-17 21:54，3840x2160）：
		//   心跳每帧 capUs=25641 恒定；dt min/avg/max = 102.10/102.57/103.12ms；
		//   102.56 / 25.641 = 4.0000（5 位有效数字）；presented per real frame = 4；
		//   perf.csv 连续 65 帧 102.55/102.56/102.57（离散度 0.02ms）。
		// 4K + ENB + 神经渲染不可能恰好落在 25.641ms 量子的整 4 倍上，而且 GPU 受限的帧
		// 会飘几毫秒而不是 0.02ms ⇒ 这是限速器的量子，被多除了一次。
		// 后果：每 4 个上屏帧只有 1 个是真的，另 3 个要跨越最长 102ms 的世界运动去重投影
		// ⇒ 站在菜单里只是轻微微闪，一动起来就崩（用户：“越来越闪”）。
		// 现在：cap = 刷新率 - 1（留 1Hz 余量避免顶到面板），flip 节流在 159/s < 160Hz，
		// 既不超发（v0.54 的初衷仍然满足），渲染侧又回到 ~159/4 ≈ 39.75fps。
		// 倍率只用于日志里算“每真实帧几个 flip”，不再参与上限计算。
		// INI ReflexFpsLimit>0 时直接用它（fps 单位，同样是 flip 上限），跳过自动。
		std::uint32_t capFps = 0;
		std::uint32_t capMult = 1;
		{
			const auto& s = Get().settings;
			if (s.reflexFpsLimit > 0) {
				capFps = static_cast<std::uint32_t>(s.reflexFpsLimit);
			} else if (Get().refreshRate > 0.0) {
				// v1.04: capMult must come from a CONFIRMED multiplier only.
				//
				// v0.79 fell back to the INI value when the probe had not latched
				// yet. On the 2026-09-18 19:04 run that fallback produced
				// "4 flips per real frame" while line 29 of the same log said the
				// runtime "supports up to 2x" -- Reflex then throttled the render
				// side to 159/4 while DLSS-G emitted only 2 flips, the pacer waited
				// for a flip slot that never freed, and the render thread parked
				// inside Present(0) for the whole session (watchdog: 19792 ms
				// silent, with the stage name stale on "d3d11 Wait").
				//
				// A number the user asked for in the INI is an INTENT, not a
				// capability. Only two sources count as confirmed:
				//   (a) dlssgAcceptedFrames -- the runtime accepted it, observed;
				//   (b) the unlocker owns the multiplier -- the runtime's own
				//       reported maximum is then the truthful figure.
				// If neither is available, assume the universal floor of 2x
				// (1 real + 1 interpolated).
				std::uint32_t mfg = 0;
				if (dlssgAcceptedFrames) {
					// v1.05: dlssgAcceptedFrames is the ONLY measurement we have of what
					// the runtime actually agreed to. It is written by SetDLSSGOptions from
					// the value Streamline returns, so it already reflects the unlocker's
					// work if there is one. Never substitute the STOCK ceiling here:
					// dlssgMaxFramesToGenerate is 1 on this card, and using it as the
					// confirmed value would tell the pacer to expect 2 flips while the
					// unlocker meanwhile installs 4 - the exact mismatch this cap exists
					// to prevent.
					mfg = dlssgAcceptedFrames;
				}
				if (mfg == 0) {
					mfg = 1;
					static std::atomic<int> unconfirmedCapLogged{ 0 };
					if (unconfirmedCapLogged.fetch_add(1) == 0) {
						SKSE::log::warn("[Streamline] Reflex cap: no confirmed multiplier yet "
							"(accepted={} stockMax={} INI asked {}x) - assuming the "
							"2x floor so the pacer cannot be told to expect flips that "
							"never arrive (v1.05)",
							dlssgAcceptedFrames, dlssgMaxFramesToGenerate,
							s.dlssgFramesToGenerate + 1);
					}
				}
				capMult = std::max<std::uint32_t>(1u, mfg + 1u);
				// v1.06: the divisor is the whole point of this line, and it was
				// lost. v0.54 (79a0ea4) derived the formula from the over-submit
				// it was fixing and stated the invariant in its own comment:
				//
				//     "160Hz / 4x -> 39fps render -> 156 present fps,
				//      just under the panel"
				//
				// Every commit up to 2a2b592 carries /capMult. The v1.00 source
				// backup (09-18 17:56) does not, and neither did any run since.
				// With capFps = refreshRate - 1 = 159 on this 160Hz panel, 4x
				// presents 636 fps, the present queue backs up, the SL pacer
				// loses cadence, and the picture stops advancing while the frame
				// counter keeps climbing - the 21:27 freeze.
				const double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;
				capFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);
				// v1.06: state the invariant as an assertion, so a future edit to
				// either term cannot silently re-introduce the over-submit.
				if (capFps * capMult > Get().refreshRate)
					SKSE::log::warn("[Streamline] Reflex cap OVER-SUBMIT: {}fps render x{} = "
						"{} present fps vs a {}Hz panel - the cap formula is wrong (v1.06)",
						capFps, capMult, capFps * capMult, Get().refreshRate);
			} else {
				// 刷新率读不到时不能再默默写死一个值（旧 60fps 就是这么来的 bug）——
				// 留 0 = 不限帧，并明确告警。
				SKSE::log::warn("[Streamline] Reflex render cap auto: DISABLED (refresh rate unknown) - over-submit is possible");
			}
			opts.frameLimitUs = capFps ? (1000000u / capFps) : 0u;
			static std::uint32_t lastCapFps = 0;
			static std::uint32_t lastCapMult = 0;
			// The whole Reflex FLIP cap block is gated on this static pair, not on
			// the block being re-entered, so the log is edge-driven either way.
			if (capFps != lastCapFps || capMult != lastCapMult) {
				const bool capConfirmed = (dlssgAcceptedFrames != 0);
				SKSE::log::info("[Streamline] Reflex FLIP cap = {} fps ({}us) - panel {}Hz, {} flips per real frame => ~{} presented fps (real = cap/flips){}{}",
					capFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps * capMult,
					capFps ? "" : "  [UNLIMITED - over-submit possible]",
					capConfirmed ? "" : "  [UNCONFIRMED - using the 2x floor, v1.04]");
				lastCapFps = capFps;
				lastCapMult = capMult;
			}
		}
		opts.useMarkersToOptimize = featurePCL;   // PCL marker 优化（Reflex 激活必需）

		// v0.62: real-frame interval, sampled where a real frame is known to start
		// (ReflexSleep runs exactly once per real frame, at the head of Present).
		// dt min/avg/max is the discriminator the 21:40 run was missing: perf.csv
		// had frames 12..77 at exactly 102.56 ms (= 4 x this function's 25.641 ms
		// cap, and with Multiplier=4 the panel therefore saw 39 fps instead of the
		// intended ~156). A limiter quantises to its own period; a GPU-bound frame
		// wanders. One window of samples tells the two apart.
		diag.reflexCapUs = opts.frameLimitUs;
		{
			static auto lastReflex = std::chrono::steady_clock::now();
			static bool lastReflexValid = false;
			const auto nowReflex = std::chrono::steady_clock::now();
			if (lastReflexValid) {
				const double dMs =
					std::chrono::duration<double, std::milli>(nowReflex - lastReflex).count();
				if (diag.winN == 0 || dMs < diag.winMinMs)
					diag.winMinMs = dMs;
				if (dMs > diag.winMaxMs)
					diag.winMaxMs = dMs;
				diag.winSumMs += dMs;
				++diag.winN;
				// A >300 ms real frame is a load or a stall. That is precisely what
				// parks the picture on a stale image while DLSS-G keeps presenting
				// interpolated frames - the 21:40 run had a 4.69 s gap between two
				// frames (perf.csv 27032.73 -> 31718.18 ms) and then wrote nothing.
				if (dMs > 300.0) {
					++diag.longFrames;
					SKSE::log::info("[XRAY] LONG FRAME {:.1f}ms (capUs={} mult={} menu={})",
						dMs, diag.reflexCapUs, dlssgAcceptedFrames + 1, diag.menuOpenNow ? 1 : 0);
				}
			}
			lastReflex = nowReflex;
			lastReflexValid = true;
		}

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
