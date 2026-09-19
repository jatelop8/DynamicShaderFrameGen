// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

#include "FrameGen.h"

#include <SKSE/SKSE.h>
#include <RE/Skyrim.h>
#include <detours/detours.h>  // v0.7.15：MenuManagerDrawInterfaceStart 函数 detour（CS 同款）

#include <Windows.h>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <chrono>
#include "FidelityFX.h"
#include "ImguiMenu.h"
#include "NeuralRendering/Renderer.h"  // DLSS5 Neural Rendering（内置 NGX Feature 18）

namespace FrameGen
{
	// CS 同款 trampoline 工具（Community Shaders include/PCH.h）：write_thunk_call
	// 把引擎内 call 指令重定向到 T::thunk，原函数地址存 T::func。
	namespace stl_ext
	{
		template <class T, std::size_t Size = 5>
		void write_thunk_call(std::uintptr_t a_src)
		{
			// v0.7.14：trampoline 空间从 14 → 128——三个 hook（PollInputDevices、
			// Main_UpdateJitter 各 write_thunk_call + MenuManagerDrawInterfaceStart
			// write_branch）共需 ~42+ 字节；14 不够 → write_branch 分配失败 → 闪退
			// （AllocTrampoline 幂等扩容，多次调用无害）
			SKSE::AllocTrampoline(128);
			auto& trampoline = SKSE::GetTrampoline();
			if constexpr (Size == 6) {
				T::func = *(uintptr_t*)trampoline.write_call<6>(a_src, T::thunk);
			} else {
				T::func = trampoline.write_call<Size>(a_src, T::thunk);
			}
		}
	}

	// v0.7.3：菜单打开时吞掉设备输入事件（鼠标/键盘）→ 游戏视角冻结（CS 同款）。
	// 必须定义在命名空间作用域（局部类的 static 成员非法）。
	struct BSInputDeviceManager_PollInputDevices
	{
		static void thunk(RE::BSTEventSource<RE::InputEvent*>* a_dispatcher, RE::InputEvent* const* a_events)
		{
			if (ImguiMenu::GetSingleton()->visible) {
				constexpr RE::InputEvent* const dummy[] = { nullptr };
				func(a_dispatcher, dummy);
				return;
			}
			func(a_dispatcher, a_events);
		}
		static inline REL::Relocation<decltype(thunk)> func;
	};

	FrameGen& Get()
	{
		static FrameGen instance;
		return instance;
	}

	// 引擎 per-frame 常量缓冲指针（REL ID：SE/AE）
	ID3D11Buffer** FrameGen::GetPerFrameBuffer()
	{
		static REL::Relocation<ID3D11Buffer**> perFrame{ REL::RelocationID(524768, 411384) };
		return perFrame.get();
	}

	void FrameGen::LoadConfig()
	{
		// 手动解析 INI（与 DynamicSnow 同款，无额外依赖）
		auto readBool = [](const std::string& a_line, bool a_default) {
			const auto eq = a_line.find('=');
			if (eq == std::string::npos)
				return a_default;
			std::string v = a_line.substr(eq + 1);
			// 去掉空格/回车
			while (!v.empty() && (v.back() == ' ' || v.back() == '\r' || v.back() == '\n'))
				v.pop_back();
			if (v == "1" || v == "true" || v == "True" || v == "TRUE" || v == "yes")
				return true;
			if (v == "0" || v == "false" || v == "False" || v == "FALSE" || v == "no")
				return false;
			return a_default;
		};
		auto readInt = [](const std::string& a_line, int a_default) {
			const auto eq = a_line.find('=');
			if (eq == std::string::npos)
				return a_default;
			try {
				return std::stoi(a_line.substr(eq + 1));
			} catch (...) {
				return a_default;
			}
		};
		auto readFloat = [](const std::string& a_line, float a_default) {
			const auto eq = a_line.find('=');
			if (eq == std::string::npos)
				return a_default;
			try {
				return std::stof(a_line.substr(eq + 1));
			} catch (...) {
				return a_default;
			}
		};

		std::ifstream f("Data/SKSE/Plugins/DynamicShaderFrameGen.ini");
		if (!f.is_open()) {
			char cwdMissing[MAX_PATH] = {};
			::GetCurrentDirectoryA(MAX_PATH, cwdMissing);
			SKSE::log::warn("[FrameGen] No INI found, using defaults (Enable={})", settings.enableFrameGen);
			SKSE::log::warn("[XRAY] INI MISSING: cwd={} expected={}\\Data\\SKSE\\Plugins\\DynamicShaderFrameGen.ini",
				cwdMissing, cwdMissing);
			return;
		}
		// v0.61: name the file that actually won. The path is relative to the process
		// CWD (the game directory) and a whole debug round was lost to “which copy of
		// the ini is the game reading“ - resolved path + size is the only proof.
		{
			char cwd[MAX_PATH] = {};
			::GetCurrentDirectoryA(MAX_PATH, cwd);
			f.seekg(0, std::ios::end);
			const auto iniSize = static_cast<long long>(f.tellg());
			f.clear();
			f.seekg(0, std::ios::beg);
			SKSE::log::info("[XRAY] INI: cwd={} file={}\\Data\\SKSE\\Plugins\\DynamicShaderFrameGen.ini size={}B",
				cwd, cwd, iniSize);
		}
		std::string line;
		while (std::getline(f, line)) {
			if (line.empty() || line[0] == ';' || line[0] == '#')
				continue;
			// v0.5：键名精确匹配（“Enable” 子串会误吞 “ForceEnable” 行——Enable 分支在前时
			// ForceEnable 永远不执行且 enableFrameGen 被误置）
			const auto eq = line.find('=');
			if (eq == std::string::npos)
				continue;
			std::string key = line.substr(0, eq);
			while (!key.empty() && key.back() == ' ')
				key.pop_back();
			if (key == "Enable")
				settings.enableFrameGen = readBool(line, false);
			else if (key == "ForceEnable")
				settings.forceEnable = readBool(line, false);
			else if (key == "ForceBorderless")
				settings.forceBorderless = readBool(line, true);   // v0.26：强制无边框窗口化
			else if (key == "Provider")
				settings.provider = std::clamp(readInt(line, 0), 0, 1);
			else if (key == "FrameGeneration")
				settings.frameGeneration = readBool(line, true);
			else if (key == "EnableUpscale")
				settings.enableUpscale = readBool(line, true);   // v0.7.24：DLSS 超分开关
			// DLSS5 Neural Rendering（内置 NGX Feature 18）——与帧生成互斥
			else if (key == "NeuralRenderingEnabled")
				settings.neuralRenderingEnabled = readBool(line, false);
			// v1.01：允许 DLSS5 NR 与帧生成串联（默认 0 = 保持 v0.69 的互斥）
			else if (key == "NRAllowWithFrameGen")
				settings.nrAllowWithFrameGen = readBool(line, false);
			// DLSSNR 调优（GUI 滑块，INI 持久化；对齐 CS FoveatedRender）
			else if (key == "NRIntensity")
				nrTuning.intensity = std::clamp(readFloat(line, 0.8f), 0.0f, 2.0f);
			else if (key == "NRLocalTone")
				nrTuning.localToneStrength = std::clamp(readFloat(line, 0.75f), 0.0f, 2.0f);
			else if (key == "NRLocalStructure")
				nrTuning.localStructureStrength = std::clamp(readFloat(line, 0.9f), 0.0f, 2.0f);
			else if (key == "NRSkinStructure")
				nrTuning.skinStructureStrength = std::clamp(readFloat(line, 0.9f), 0.0f, 2.0f);
			else if (key == "NRStyle")
				nrTuning.style = std::clamp(static_cast<std::uint32_t>(readInt(line, 3)), 0u, 3u);
			else if (key == "NRAutoMask")
				nrTuning.useAutoMask = readBool(line, true);
			else if (key == "NRUICorrection")
				nrTuning.uiCorrection = readBool(line, false);
			// v0.44：DLSSNR 输入分辨率缩放（性能优化）。1.0=全分辨率；0.5=半分辨率
			// （FP8 计算量减 ~75%）。0.5~0.75 推荐，越低越快但细节越少。
			else if (key == "NRRenderScale")
				nrTuning.renderScale = std::clamp(readFloat(line, 1.0f), 0.25f, 1.0f);
			// v0.25：EnableDLSSNR/NRDirectTest/NR* 已移除（NR 改走 ReShade 外挂方案）
			else if (key == "FpsOverlay")
				settings.fpsOverlay = readBool(line, true);      // v0.24：FPS 显示器（默认开）
 else if (key == "QualityMode")
				settings.qualityMode = std::clamp(readInt(line, 1), 0, 4);
			else if (key == "PresetDLSS")
				settings.presetDLSS = std::clamp(readInt(line, 0), 0, 4);
			else if (key == "DLSSGFramesToGenerate")
				settings.dlssgFramesToGenerate = std::clamp(readInt(line, 1), 1, 5);   // v0.50：多倍帧生成（1=2x 2=3x 3=4x 4=5x 5=6x）
			// v0.50：MFG 上限覆盖（老卡多倍帧生成解锁）。0=不覆盖（跟随硬件上报，默认安全）；
			// 1..5 = 抬高上报上限到 N 个插帧（1=2x ... 5=6x）。需要外部内核解锁器提供
			// Ada/Ampere/Turing 内核，否则高倍率请求无内核可执行 -> 黑屏/卡死。
			else if (key == "MFGMaxFramesOverride")
				settings.mfgMaxFramesOverride = std::clamp(readInt(line, 0), 0, 5);
			// v0.54：Reflex 渲染帧率上限（0 = 自动按 刷新率/总倍数 计算；见 Streamline::ReflexSleep）
			else if (key == "ReflexFpsLimit")
				settings.reflexFpsLimit = std::clamp(readInt(line, 0), 0, 480);
			// v0.63：菜单期间不插帧（1=开，默认；0=旧行为，菜单也插帧 -> 菜单画面持续闪）
			else if (key == "MenuDisableFrameGen")
				settings.menuDisableFrameGen = readBool(line, true);
			else if (key == "Sharpness") {
				// v0.6.3：DLSS 超分锐化（0-1，0=关闭）
				try {
					std::string v = line.substr(eq + 1);
					while (!v.empty() && (v.back() == ' ' || v.back() == '\r' || v.back() == '\n'))
						v.pop_back();
					settings.sharpness = std::clamp(std::stof(v), 0.0f, 1.0f);
				} catch (...) {}
			}
			else if (key == "RenderResolutionScale") {
				// v0.41：自定义渲染分辨率缩放（0=Auto 跟随 QualityMode 档位表；>0 自定义 0.30-1.00）
				try {
					std::string v = line.substr(eq + 1);
					while (!v.empty() && (v.back() == ' ' || v.back() == '\r' || v.back() == '\n'))
						v.pop_back();
					settings.renderResolutionScale = std::clamp(std::stof(v), 0.0f, 1.0f);
				} catch (...) {}
			}
			else if (key == "MvecScaleOverride") {
				// v0.57：mvecScale 覆盖（单变量 A/B：0=旧行为 1.0=identity）
				try {
					std::string v = line.substr(eq + 1);
					while (!v.empty() && (v.back() == ' ' || v.back() == '\r' || v.back() == '\n'))
						v.pop_back();
					settings.mvecScaleOverride = std::clamp(std::stof(v), 0.0f, 4.0f);
				} catch (...) {}
			}
			else if (key == "StreamlineLogLevel")
				settings.streamlineLogLevel = std::clamp(readInt(line, 0), 0, 2);
			else if (key == "ToggleKey") {
				// 十六进制虚拟键码（如 0x24 = Home）
				try {
					std::string v = line.substr(eq + 1);
					while (!v.empty() && (v.back() == ' ' || v.back() == '\r' || v.back() == '\n'))
						v.pop_back();
					settings.toggleKey = static_cast<std::uint32_t>(std::stoul(v, nullptr, 0));
				} catch (...) {}
			}
		}
		// v0.45：provider 尊重 INI（0=FSR3 默认稳定，1=DLSSG 供 50 系 MFG）。
		// DLSSG 多倍帧生成只服务 50 系（Blackwell 原生 numFramesToGenerateMax=3），
		// 40 系会被 SetDLSSGOptions 按真实上限 clamp 到 1（2x）。不再有任何
		// 40 系解锁 hack（AdaMidpointFix/NgxMfgHook/MFGUnlock 已删除）。
		// v0.48：DLSS5 Neural Rendering 由 INI/GUI 控制（NeuralRenderingEnabled）。
		// renderScale 默认保持 1.0（全分辨率，DLSS5 完整效果）——降分辨率虽提帧数，
		// 但神经网络在低分辨率上分析会导致脸部重光照细节减少（“没效果”）。性能优化
		// 交给 GUI 滑块由用户自行权衡，不再默认降。
		SKSE::log::info("[FrameGen] Config loaded: Enable={} ForceEnable={} ForceBorderless={} Provider={} FrameGeneration={} EnableUpscale={} QualityMode={} PresetDLSS={} SL_LogLevel={} ToggleKey={:#x} FpsOverlay={}",
			settings.enableFrameGen, settings.forceEnable, settings.forceBorderless, settings.provider, settings.frameGeneration,
			settings.enableUpscale, settings.qualityMode, settings.presetDLSS, settings.streamlineLogLevel, settings.toggleKey,
			settings.fpsOverlay);
	}

	// ---- 输入：Home 键（短按切插帧 / 长按开菜单）----
	// v0.7.2：SKSE InputEvent 是事件驱动（按下/抬起才回调，按住不持续）→ 长按检测必须在
	// 每帧轮询（PollHomeKey 在 Present 里调，GetAsyncKeyState 直接读硬件状态，最可靠）。
	// InputEventHandler 只保留 ImGui 键盘事件转发（菜单内导航）。
	namespace
	{
		struct ToggleInputHandler : RE::BSTEventSink<RE::InputEvent*>
		{
			RE::BSEventNotifyControl ProcessEvent(RE::InputEvent* const* a_event, RE::BSTEventSource<RE::InputEvent*>*) override
			{
				if (!a_event || !*a_event)
					return RE::BSEventNotifyControl::kContinue;
				for (auto* evn = *a_event; evn; evn = evn->next) {
					if (evn->GetEventType() != RE::INPUT_EVENT_TYPE::kButton)
						continue;
					auto* btn = evn->AsButtonEvent();
					if (!btn || btn->GetDevice() != RE::INPUT_DEVICE::kKeyboard)
						continue;
					// 键盘事件转发给 ImGui（菜单内交互；按下+抬起都发）
					if (ImguiMenu::GetSingleton()->visible)
						ImguiMenu::GetSingleton()->OnKeyEvent(btn->GetIDCode(), btn->IsPressed());
				}
				return RE::BSEventNotifyControl::kContinue;
			}
		};
		ToggleInputHandler g_toggleHandler;
	}

	void FrameGen::PollHomeKey()
	{
		static bool held = false;
		static std::chrono::steady_clock::time_point pressTime;
		static bool longFired = false;

		const bool down = (GetAsyncKeyState(VK_HOME) & 0x8000) != 0;
		if (down) {
			if (!held) {
				held = true;
				pressTime = std::chrono::steady_clock::now();
				longFired = false;
			} else if (!longFired &&
				std::chrono::duration_cast<std::chrono::milliseconds>(
					std::chrono::steady_clock::now() - pressTime).count() > 400) {
				longFired = true;
				ImguiMenu::GetSingleton()->Toggle();
			}
	} else if (held) {
		// v0.7.7：短按不再切插帧——开关统一在 GUI 菜单里操作
		held = false;
	}
}

	void FrameGen::InstallInputHook()
	{
		auto* mgr = RE::BSInputDeviceManager::GetSingleton();
		if (mgr) {
			mgr->AddEventSink(&g_toggleHandler);
			SKSE::log::info("[FrameGen] Input toggle hook installed (key {:#x})", settings.toggleKey);
		} else {
			SKSE::log::error("[FrameGen] BSInputDeviceManager unavailable - toggle key disabled");
		}

		// v0.7.3：菜单打开时吞掉设备输入事件（CS 同款）——鼠标移动不再控制游戏视角，
		// 只操作菜单。Home 长按检测走硬件轮询（GetAsyncKeyState）不受影响。
		// 注意：菜单开时键盘事件也被吞（ImGui 键盘导航失效），鼠标操作完全正常。
		stl_ext::write_thunk_call<BSInputDeviceManager_PollInputDevices>(
			REL::RelocationID(67315, 68617).address() + REL::Relocate(0x7B, 0x7B, 0x81));
		SKSE::log::info("[FrameGen] PollInputDevices hook installed (menu freezes game input)");
	}


	// v0.7.13：MenuManagerDrawInterfaceStart hook（CS 同款 detour）——引擎 UI 绘制
	// 开始前回调。Skyrim 的 UI（准星/字幕/菜单）画在 kFRAMEBUFFER（最终帧缓冲），
	// 若在 Present 覆盖后缓冲会把 UI 抹掉；必须在 UI 绘制前把 DLSS 超分结果写进
	// kFRAMEBUFFER（4K），UI 随后叠加 → 后缓冲 = 超分画面 + UI。
	// REL 79947/82084 已确认在 1.6.1170 库中（offset 0xef88a0/0xfa3dc0）。
	struct MenuManagerDrawInterfaceStartHook
	{
		static void thunk(int64_t a1)
		{
			Get().OnMenuDrawStart();
			func(a1);
		}
		static inline REL::Relocation<decltype(thunk)> func;
	};

	void FrameGen::InstallMenuHook()
	{
		// v0.7.15：Detours detour（CS detour_thunk 同款）——函数开头安全 detour，
		// DetourAttach 自动复制原指令到 trampoline。v0.7.13 用 write_branch<5> 是
		// “重定向现有 jmp/call”的语义（返回值 = 原跳转目标），直接 patch 函数开头
		// 会丢原指令 → 首帧执行野地址 → 崩溃（crash-02-05-52 实锤）
		MenuManagerDrawInterfaceStartHook::func = REL::RelocationID(79947, 82084).address();
		DetourTransactionBegin();
		DetourUpdateThread(GetCurrentThread());
		DetourAttach(reinterpret_cast<PVOID*>(&MenuManagerDrawInterfaceStartHook::func),
			reinterpret_cast<PVOID>(&MenuManagerDrawInterfaceStartHook::thunk));
		const LONG res = DetourTransactionCommit();
		if (res == NO_ERROR) {
			SKSE::log::info("[FrameGen] MenuManagerDrawInterfaceStart hook installed (upscale before UI, detours)");
		} else {
			SKSE::log::error("[FrameGen] MenuManagerDrawInterfaceStart detour failed ({}) - upscale before UI disabled", res);
		}
	}

	// 每帧 UI 绘制前：DLSS 超分 kMAIN（渲染分辨率）→ colorOut（4K）→ 写引擎 kFRAMEBUFFER
	void FrameGen::OnMenuDrawStart()
	{
		auto* renderer = RE::BSGraphics::Renderer::GetSingleton();
		// v0.7.16 入口诊断（节流 60 帧）：无条件打印条件状态——定位提前 return 的环节
		static std::uint32_t entryDiag = 0;
		if (++entryDiag % 60 == 1) {
			bool hasMain = false;
			bool hasFb = false;
			if (renderer) {
				auto& rt = renderer->GetRuntimeData();
				hasMain = rt.renderTargets[RE::RENDER_TARGETS::kMAIN].texture != nullptr;
				hasFb = rt.renderTargets[RE::RENDER_TARGETS::kFRAMEBUFFER].texture != nullptr;
			}
			SKSE::log::info("[FrameGen] MenuDraw entry: dlssg={} fg={} dlss={} fbBuf={} colorOut={} ctx={} renderer={} kMAIN={} kFRAMEBUFFER={}",
				dx12SwapChain.dlssgMode, fgActive.load(), streamline.featureDLSS, GetFrameBuffer() != nullptr,
				dx12SwapChain.colorOutWrapped != nullptr, dx12SwapChain.d3d11Context != nullptr,
				renderer != nullptr, hasMain, hasFb);
		}

		// v0.50：DLSS 超分已拔掉（kFRAMEBUFFER 方案在 Skyrim SE 恒 null，早已是死代码）。
		// DLSS5 Neural Rendering 在 DX12SwapChain::Present 里跑（后缓冲作 color 输入）。
	}

	// CS 同款（Skyrim-Upscaler）：FOV 基数 REL ID → 垂直 FOV（弧度）
	// https://github.com/PureDark/Skyrim-Upscaler/blob/fa057bb088cf399e1112c1eaba714590c881e462/src/SkyrimUpscaler.cpp#L88
	float FrameGen::GetVerticalFOVRad()
	{
		static REL::Relocation<float> fovBase{ REL::RelocationID(513786, 388785) };
		const float base = fovBase.get();
		const float x = base / 1.30322540f;
		const float aspect = screenHeight > 0 ? screenWidth / screenHeight : 16.0f / 9.0f;
		return 2.0f * std::atan(x / aspect);
	}

	// ---- ID3D11DeviceContext::Map/Unmap 钩子（偷看引擎 perFrame 常量缓冲）----
	// perFrame 缓冲含相机矩阵（CameraViewProj 等），DLSS 每帧需要。引擎每帧 Map
	// 该缓冲写常量，我们在 Unmap 前拷贝一份。

	namespace
	{
		// v0.65: 每个线程各自的“当前已映射的 perFrame 指针”。这个钩子实测被
		// 不止一个线程命中（Transfusion [MOTION] 的 tid 在 40760 / 3508 之间
		// 交替），共享成员会被交叉覆盖，Unmap 时就会拷到别的线程的内存。
		thread_local FrameBuffer* tlsMappedFB = nullptr;

		// v0.67: camera snapshot continuity gate
		// 取证用的小工具。矩阵是引擎的行主序 float[4][4]（FrameGen.h:73）。
		inline float camDev(const Matrix& m)
		{
			float mx = 0.0f;
			for (int r = 0; r < 4; ++r)
				for (int c = 0; c < 4; ++c) {
					float d = m.data[r][c] - (r == c ? 1.0f : 0.0f);
					if (!(d == d)) return 1.0e30f;   // NaN
					if (d < 0.0f) d = -d;
					if (d > mx) mx = d;
				}
			return mx;
		}
		inline float camMag(const Matrix& m)
		{
			float mx = 0.0f;
			for (int r = 0; r < 4; ++r)
				for (int c = 0; c < 4; ++c) {
					float v = m.data[r][c];
					if (!(v == v)) return 1.0e30f;
					if (v < 0.0f) v = -v;
					if (v > mx) mx = v;
				}
			return mx;
		}
		inline float camDet3(const Matrix& m)
		{
			const float a = m.data[0][0], b = m.data[0][1], c = m.data[0][2];
			const float d = m.data[1][0], e = m.data[1][1], f = m.data[1][2];
			const float g = m.data[2][0], h = m.data[2][1], i = m.data[2][2];
			return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
		}
		// v0.68：**触发规则本身是缺陷，必须修**（这不是加诊断，是修诊断）。v0.67 写成
		// 「每 300 个到达打一次」，但到达计数是**整场累计**的：22:42 那次 45 秒主菜单
		// （~600 到达）之后才进世界 3 秒（~90 到达）⇒ 取样点 1/301/601 全部落在菜单里，
		// **世界阶段一条原始矩阵都看不到** —— 恰恰是最需要它的那一段。改为：
		//   · 前 2 个到达必打；
		//   · 判定翻转（接受 <-> 拒绝）时打，两次之间至少隔 0.5 s；
		//   · 每 900 个到达兜底一次；
		//   · 全场最多 80 组。
		// “两组相机交替”这个事件的签名就是判定翻转，所以它必然被采到，日志量仍有上界。
		inline void DumpCameraSnapshot(const FrameBuffer& b, std::uint64_t a_n, int a_verdict)
		{
			static int lastVerdict = -1;
			static auto lastDump = std::chrono::steady_clock::now() - std::chrono::seconds(30);
			static std::uint32_t dumps = 0;
			const bool flip = (a_verdict != lastVerdict);
			lastVerdict = a_verdict;
			if (dumps >= 80u)
				return;
			const auto now = std::chrono::steady_clock::now();
			const bool gapOk = std::chrono::duration<double>(now - lastDump).count() >= 0.5;
			if (!((a_n <= 2u) || ((a_n % 900u) == 1u) || (flip && gapOk)))
				return;
			lastDump = now;
			++dumps;
			const Matrix* ms[3] = { &b.CameraViewProjUnjittered, &b.CameraProjUnjittered, &b.CameraViewInverse };
			const char* nm[3] = { "ViewProjUnj", "ProjUnj", "ViewInv" };
			for (int k = 0; k < 3; ++k) {
				const auto& d = ms[k]->data;
				SKSE::log::info("[CAM] raw #{} {} | {:.6g} {:.6g} {:.6g} {:.6g} | {:.6g} {:.6g} {:.6g} {:.6g} "
					"| {:.6g} {:.6g} {:.6g} {:.6g} | {:.6g} {:.6g} {:.6g} {:.6g}",
					a_n, nm[k],
					d[0][0], d[0][1], d[0][2], d[0][3],
					d[1][0], d[1][1], d[1][2], d[1][3],
					d[2][0], d[2][1], d[2][2], d[2][3],
					d[3][0], d[3][1], d[3][2], d[3][3]);
			}

			// ---- v0.87b: all ten fields, with a [3][3] verdict per field ----
			// The three matrices above contradict each other: in block #1 the
			// ProjUnj fourth row is a textbook perspective projection and ViewInv
			// is a clean rotation, yet ViewProjUnj's fourth row carries ViewInv
			// data -- impossible for View x Proj. So we now walk EVERY declared
			// field and print its fourth row plus [3][3]. That single line says
			// which offsets the engine actually populates: a real viewProj must
			// end in (0,0,0,1). If c16 (CameraViewProj) is healthy while c24
			// (CameraViewProjUnjittered) is not, the field is simply not written
			// at the offset we assume, and no gate can repair that.
			{
				struct { const Matrix* m; const char* n; } all[10] = {
					{ &b.CameraView,                    "c0  View"        },
					{ &b.CameraProj,                    "c8  Proj"        },
					{ &b.CameraViewProj,                "c16 ViewProj"    },
					{ &b.CameraViewProjUnjittered,      "c24 ViewProjU"   },
					{ &b.CameraPreviousViewProjUnjittered, "c32 PrevVPU"  },
					{ &b.CameraProjUnjittered,          "c40 ProjU"       },
					{ &b.CameraProjUnjitteredInverse,   "c48 ProjUInv"    },
					{ &b.CameraViewInverse,             "c56 ViewInv"     },
					{ &b.CameraViewProjInverse,         "c64 ViewProjInv" },
					{ &b.CameraProjInverse,             "c72 ProjInv"     },
				};
				for (int k = 0; k < 10; ++k) {
					const auto& d = all[k].m->data;
					const float w = d[3][3];
					SKSE::log::info("[FLD] #{} {:<14s} row3=({:.6g},{:.6g},{:.6g},{:.6g}) "
						"[3][3]={:.6g} dev={:.6g} det={:.6g} mag={:.6g} {}",
						a_n, all[k].n,
						d[3][0], d[3][1], d[3][2], d[3][3],
						w, camDev(*all[k].m), camDet3(*all[k].m), camMag(*all[k].m),
						(std::fabs(w - 1.0f) <= 1.0e-3f) ? "OK" : "BAD");
				}
			}
			SKSE::log::info("[CAM] raw #{} pos=({:.4f},{:.4f},{:.4f},{:.4f}) prevPos=({:.4f},{:.4f},{:.4f},{:.4f}) "
				"devVP={:.6g} detVP={:.6g} detProj={:.6g} magVP={:.6g}",
				a_n, b.CameraPosAdjust[0], b.CameraPosAdjust[1], b.CameraPosAdjust[2], b.CameraPosAdjust[3],
				b.CameraPreviousPosAdjust[0], b.CameraPreviousPosAdjust[1], b.CameraPreviousPosAdjust[2],
				b.CameraPreviousPosAdjust[3],
				camDev(b.CameraViewProjUnjittered), camDet3(b.CameraViewProjUnjittered),
				camDet3(b.CameraProjUnjittered), camMag(b.CameraViewProjUnjittered));

			// ---- v0.87: raw byte dump (diagnostic only) -------------------
			// Emit the raw float stream from the FrameBuffer base so the true
			// layout can be measured offline. Rationale in
			// tools/add_v087_rawdump.py: the dumped matrices contradict each
			// other. In the 14:20 log, block #1 has a ProjUnj whose fourth row
			// is (0, 0, -0.0666178, 0.0666667) -- a textbook perspective
			// projection -- and a ViewInv that is a clean rotation, yet its
			// ViewProjUnj fourth row is (0, -0.991228, -0.132164, 0), which is
			// ViewInv data. View x Proj cannot have that fourth row. Either the
			// field offsets are wrong or the struct stride is wrong; both make
			// every offset wrong at once, so no gate can fix it.
			//
			// Bounds: sizeof(FrameBuffer) is 672 B. Dump exactly that much so the
			// read can never leave the mapped region (a_src points at the live
			// D3D11 mapping; a longer read could touch an unmapped page).
			{
				constexpr int kFloatCount =
					static_cast<int>(sizeof(FrameBuffer) / sizeof(float));   // 168
				const float* raw = reinterpret_cast<const float*>(&b);
				for (int off = 0; off < kFloatCount; off += 8) {
					SKSE::log::info("[RAW] +{:#06x} | {:.7g} {:.7g} {:.7g} {:.7g} | {:.7g} {:.7g} {:.7g} {:.7g}",
						off * 4,
						raw[off + 0], raw[off + 1], raw[off + 2], raw[off + 3],
						raw[off + 4], raw[off + 5], raw[off + 6], raw[off + 7]);
				}
			}
		}

		struct ID3D11DeviceContext_Map
		{
			static HRESULT thunk(ID3D11DeviceContext* This, ID3D11Resource* pResource, UINT Subresource,
				D3D11_MAP MapType, UINT MapFlags, D3D11_MAPPED_SUBRESOURCE* pMappedResource)
			{
				HRESULT hr = func(This, pResource, Subresource, MapType, MapFlags, pMappedResource);
				// 防御：perFrame 缓冲指针判空（引擎加载早期可能未初始化）；
				// 只记录指针，内容在 Unmap 时拷贝（Map 时引擎可能还没写完）
				tlsMappedFB = nullptr;
				if (SUCCEEDED(hr) && pMappedResource) {
					auto* perFrame = FrameGen::GetPerFrameBuffer();
					if (perFrame && *perFrame == pResource && pMappedResource->pData) {
						tlsMappedFB = static_cast<FrameBuffer*>(pMappedResource->pData);
						// v0.83: does the engine still write this buffer after entering
						// the world? If this stops rising, the loss is upstream of the gate.
						++Get().mapPerFrameHits;
					}
				}
				return hr;
			}
			static inline REL::Relocation<decltype(thunk)> func;
		};

		struct ID3D11DeviceContext_Unmap
		{
			static void thunk(ID3D11DeviceContext* This, ID3D11Resource* pResource, UINT Subresource)
			{
				// v0.65：拷贝必须发生在**原始 Unmap 之前**。旧版在 func() 之后才读
				// pData —— 那时已经解映射，驱动可以立刻回收/复用这块内存，实测约
				// 45% 的帧因此读到全零（心跳 prevVP 恰好 = 1.0000 = 零矩阵指纹）。
				if (tlsMappedFB) {
					auto& fg = Get();
					++fg.unmapPerFrameHits;   // v0.83: arrivals that DO reach the gate
					// v0.67：只接受「与上一次接受的快照时间连续」的相机数据。
					// 同一个 perFrame 缓冲每帧写入两组不同相机（菜单 3D 背景 + 世界）
					// 时，后写的那组会把先写的冲掉 —— 闸门挡住它，frameBufferCopy 与
					// 自维护 prev 历史才可能是同一来源（det(inv(cur) x prev)=1）。
					if (fg.AcceptCameraSnapshot(*tlsMappedFB))
						fg.SetMappedFrameBuffer(&fg.frameBufferCopy);
					tlsMappedFB = nullptr;
				}
				func(This, pResource, Subresource);
			}
			static inline REL::Relocation<decltype(thunk)> func;
		};
	}

	// v0.67: camera snapshot continuity gate
	// 判定量 = CameraPosAdjust（相机世界位置，心跳 pos= 与 Transfusion
	// [MOTION] cameraPos= 打的是同一个值）。Skyrim 人物高约 100 单位，真实相机
	// 一帧移动顶多几十单位；实测两组数据相差 1300+ 单位 —— 那不可能是同一个相机。
	// 被拒绝的快照**不写入** frameBufferCopy，于是 cur/prev 恒定来自同一来源，
	// det(inv(cur) x prev) 才会是 1。
	namespace
	{
		constexpr float kCamJumpTol = 400.0f;
		constexpr float kCamJumpTol2 = kCamJumpTol * kCamJumpTol;
		constexpr std::uint32_t kCamRelockAfter = 12;

		// ---- v0.94: source locking thresholds ---------------------------------
		// A real camera advances by a SMALL step per arrival. The crash log's
		// genuine stream moved 900 -> 894 over ~50 arrivals, i.e. well under one
		// unit per arrival; the interleaved constants differed by hundreds. 50
		// units is two orders of magnitude above the real step and two orders
		// below the inter-source gap, so it separates them with no ambiguity.
		constexpr float kCamStepTol = 50.0f;
		constexpr float kCamStepTol2 = kCamStepTol * kCamStepTol;
		// How many consecutive non-continuing arrivals before the locked stream
		// is declared dead and a new source may be acquired. 90 arrivals is ~1.5 s
		// at 60 Hz: long enough that an interleaved slot cannot steal the lock
		// (it never gets 90 in a row while the real camera keeps arriving),
		// short enough that a genuine scene change re-locks promptly.
		//
		// v1.09 -- THIS THRESHOLD IS NOT CONSUMED ANYWHERE.
		// A whole-project grep finds kCamStillTol in exactly four places: this
		// definition, three comments, and two log-format argument lists. There is
		// no comparison against it, so the release that the comment above promises
		// does not exist. The v1.07b note at the same site says the reset edge is
		// "the ONLY release path", and snapLockStill is reset to 0 by every accept
		// (so `still=2/90` never grows). Observed consequence: the lock has no
		// release of its own, so whichever family wins the first acquire keeps the
		// stream until the process exits.
		//
		// v1.09 -- AND THE NUMBER IS WRONG BY 8x.
		// 90 arrivals is not "~1.5 s at 60 Hz", it is 0.18 s: the Map/Unmap hook
		// fires 493-502 times per second (measured: 612 arrivals per 1.22 s, at
		// 41.4 rendered fps, i.e. ~12 maps per frame). Every arrival-count
		// threshold in this file carries the same 8.2x error.
		constexpr std::uint32_t kCamStillTol = 90;

		// ---- v1.10: "a moving family beats a still lock" ---------------------
		// Measured 11:30 run: the refused stream moved 640.8 -> 1334.8 units
		// between two of its own samples, while the locked stream's own travel
		// was frozen at 65.41 for nine seconds. 200 units of REFUSED-stream
		// travel is unambiguous motion, and still far below kCamJumpTol so a
		// single slot jump cannot reach it on its own.
		constexpr float kCamForeignMoveTol = 200.0f;
		// ---- v1.11: snapLockStill is not a liveness measure -------------------
		// v1.10 gated the takeover below on
		//     snapLockStill >= kCamForeignMinRej (= 30)
		// and that gate is dead by construction: snapLockStill is reset to 0 by
		// EVERY accepted arrival, and a frozen family arrives at d2 == 0 against
		// its own previous arrival, so `continues` is true, so it is accepted,
		// so the counter goes back to zero. The 14:20 run is the measurement:
		// 81.6% of 184 000 arrivals were published, the frozen family dominated
		// them, and `still` never left the 3..8 band while famRej climbed past
		// 34 000. The one takeover that DID fire (14:28:11.972) fired because a
		// release had just cleared snapHaveLast for an unrelated reason -- and
		// it worked: matChanges went 2 -> 542 in three seconds.
		//
		// So gate on what we actually care about, measured at the publish site
		// instead of the arrival site: how many consecutive publishes carried a
		// byte-identical matrix. 200 publishes is ~0.6 s of a provably dead
		// published stream at the measured ~330/s.
		//
		// The SECOND condition is unchanged and is still what makes this safe: a
		// parked or stale family contributes no travel, so a legitimately still
		// player -- where an identity clipToPrev is CORRECT -- can never hand the
		// anchor away. Only a family that has walked >= kCamForeignMoveTol on its
		// own can take it.
		constexpr std::uint64_t kCamPubStaleTol = 200;

	// v0.78: how many consecutive identical-matrix arrivals (with a different
	// matrix seen in between) before we call the slot stale. The 08:59 run showed
	// 4196 repeats in 2.34 s, so 120 trips in well under one frame at that rate
	// and cannot misfire on a legitimate still period that later resumes moving.
	//
	// v0.84: raised 120 -> 600, and the counter is now actually reset when a
	// different matrix arrives (v0.78 only incremented it). 120 frames is 2 s
	// at 60 fps, which a legitimate still scene reaches trivially -- a menu, a
	// forge, reading a book. A false positive froze the picture permanently,
	// while a late detection costs one stale frame, so the trade is lopsided.
	constexpr std::uint32_t kCamFrozenTol = 600;
	// v1.09: 600 arrivals is 1.2 s at the measured 493-502 arrivals/s, not the
	// 10 s this comment describes. The gate itself was downgraded to a counter
	// in v0.93 ("gates observe, they do not discard"), so this detector fires
	// and changes nothing -- see the [CAM] pub `frozenRep=` field for its value.

	// ---- v1.13: how a CAMERA WRITE is told apart from the other writers ----
	// The perFrame buffer is mapped ~22 times per rendered frame and only one
	// of those writes is the camera; see the gate in AcceptCameraSnapshot for
	// the full measurement.  Both numbers come from the 18:20 run and both
	// separate the two populations exactly:
	//     camera   : |Proj[3][2]| = 1     |Proj[3][3]| = 0
	//     impostor : |Proj[3][2]| = 0     |Proj[3][3]| = 1
	constexpr float kCamProjDivideMin = 0.05f;   // |CameraProj[3][2]| -- perspective divide present
	constexpr float kCamProjWMax = 0.05f;        // |CameraProj[3][3]| -- must be 0 for a D3D projection
	// ~10 s of drops at the measured ~590 arrivals/s.  Long enough that a
	// genuine world camera never trips it, short enough that a machine whose
	// camera write fails the test is back on the old behaviour within one run.
	constexpr std::uint64_t kCamCaptureFallbackSkips = 6000;
	}

	bool FrameGen::AcceptCameraSnapshot(const FrameBuffer& a_src)
	{
		++snapArrivals;

		const float px = a_src.CameraPosAdjust[0];
		const float py = a_src.CameraPosAdjust[1];
		const float pz = a_src.CameraPosAdjust[2];

		// ---- v1.14 probe: a census of the WRITERS -- who writes this buffer, and
		// does any of them MOVE?  Purely additive and placed BEFORE the gate, so it
		// sees the whole cast.
		// The 19:39 run proved the v1.13 gate works (the orthographic writer is
		// dropped 13,804 times, cap=13804/0) but the published camera stayed
		// byte-identical for the whole 11.4 s world session.  "The player was
		// standing still" and "we are locked on a parked camera" call for two very
		// different repairs, and only a census of the actual writers separates
		// them: if snapCensusNew stays at 2-3 for a whole session, NO writer moves
		// and the source itself has to change.
		{
			bool known = false;
			for (std::uint32_t i = 0; i < snapCensusCount && !known; ++i) {
				known = (std::fabs(snapCensus[i][0] - px) +
				         std::fabs(snapCensus[i][1] - py) +
				         std::fabs(snapCensus[i][2] - pz)) < 1.0f;
			}
			if (!known) {
				if (snapCensusCount < kSnapCensusMax) {
					snapCensus[snapCensusCount][0] = px;
					snapCensus[snapCensusCount][1] = py;
					snapCensus[snapCensusCount][2] = pz;
					++snapCensusCount;
				}
				++snapCensusNew;
				if (snapCensusLogged < 80u) {
					++snapCensusLogged;
					SKSE::log::info("[CAM] WRITER #{} NEW pos=({:.3f},{:.3f},{:.3f}) proj00={:.6g} "
						"row3_2={:.6g} row3_3={:.6g} prevPos=({:.3f},{:.3f},{:.3f}) arr#{}",
						snapCensusNew, px, py, pz,
						a_src.CameraProj.data[0][0],
						a_src.CameraProj.data[3][2], a_src.CameraProj.data[3][3],
						a_src.CameraPreviousPosAdjust[0], a_src.CameraPreviousPosAdjust[1],
						a_src.CameraPreviousPosAdjust[2], snapArrivals);
				}
			}
		}

		const bool usable = (px == px) && (py == py) && (pz == pz) &&
		                    camMag(a_src.CameraViewProjUnjittered) > 1.0e-6f &&
		                    camMag(a_src.CameraView) > 1.0e-6f;
		if (!usable) {
			++snapRejectZero;
			DumpCameraSnapshot(a_src, snapArrivals, 2);
			SKSE::log::warn("[CAM] #{} rejected: empty/garbage snapshot (magVP={:.6g} devVP={:.6g})",
				snapArrivals, camMag(a_src.CameraViewProjUnjittered), camDev(a_src.CameraViewProjUnjittered));
			return false;
		}

		// ---- v1.13: A CAMERA SNAPSHOT MUST LOOK LIKE A CAMERA ----------------
		// This hook captures *every* Map/Unmap of the perFrame constant buffer,
		// ~22 per rendered frame (measured 18:20 run: 591 arrivals/s at ~24 world
		// fps), and tlsMappedFB is overwritten by each one -- so the snapshot that
		// reaches this function is whatever pass wrote LAST, and in the world that
		// is not the camera.  Measured populations in the world:
		//
		//   camera write  : CameraProj row3 = (0,0,1.000733,-15.01099) + (0,0,1,0)
		//                   -> a perspective projection, CameraPreviousPosAdjust
		//                      tracks the live position
		//   impostor write: CameraProj row3 = (0,0,1.111111,-0.1111111) + (0,0,0,1)
		//                   -> an ORTHOGRAPHIC fullscreen-style projection
		//                      (m22=0.9, m23=0.1 on its inverse: z:[0.1,1]->[0,1]),
		//                      CameraView is the exact axis permutation
		//                      [[0,0,1],[0,1,0],[1,0,0]], and
		//                      CameraPreviousPosAdjust is identically (0,0,0,0)
		//
		// Publishing the impostor IS the freeze: on the published stream
		// matChanges stopped at 6171, `path` stayed at 124.92 for 30 s while pos
		// jittered +/- 0.6 around a parked point, and the lock's anchor went to a
		// non-camera.  So a snapshot that is not a camera must never reach the
		// lock, frameBufferCopy, or the reprojection.
		//
		// ESCAPE HATCH: if NOTHING looks like a camera for kCamCaptureFallbackSkips
		// consecutive snapshots, the test itself is wrong for this machine and
		// accepting the last writer -- today's behaviour -- is strictly better than
		// starving the stream.  The gate then stops filtering for the rest of the
		// run, so the worst case is the current build, never a worse one.
		{
			const bool camShaped =
				(std::fabs(a_src.CameraProj.data[3][2]) >= kCamProjDivideMin) &&
				(std::fabs(a_src.CameraProj.data[3][3]) <= kCamProjWMax);
			if (!camShaped) {
				++snapNonCamera;
				++snapSkipsSinceCam;
				if (snapNonCamera <= 5u) {
					SKSE::log::info("[CAM] #{} NON-CAMERA write dropped (v1.13): Proj "
						"row3=({:.6g},{:.6g},{:.6g},{:.6g}) prevPos=({:.4g},{:.4g},{:.4g}) "
						"pos=({:.1f},{:.1f},{:.1f}) magVP={:.6g} - not a camera",
						snapArrivals,
						a_src.CameraProj.data[3][0], a_src.CameraProj.data[3][1],
						a_src.CameraProj.data[3][2], a_src.CameraProj.data[3][3],
						a_src.CameraPreviousPosAdjust[0], a_src.CameraPreviousPosAdjust[1],
						a_src.CameraPreviousPosAdjust[2], px, py, pz,
						camMag(a_src.CameraViewProjUnjittered));
				}
				if (snapSkipsSinceCam < kCamCaptureFallbackSkips)
					return false;
			} else {
				snapSkipsSinceCam = 0;
			}
		}

		// ---- v0.89: SHAPE rejection REMOVED (was v0.86) ----------------------
		// The v0.86 guard threw away every snapshot whose c24[3][3] != 1, on the
		// theory that a view-projection matrix must be affine. Measured cost:
		//
		//     acc=13380  shape(rejected)=8734   -> 80.6% of arrivals discarded
		//
		// And the discarded population was NOT garbage. Its positions glide:
		//
		//     #6988  pos=(-50.0, 880.7, 94.3)
		//     #7612  pos=(-49.9, 860.4, 92.6)
		//     #8238  pos=(-49.7, 840.4, 90.8)
		//     #8862  pos=(-49.5, 821.6, 89.2)
		//
		// while the snapshots that DID pass were frozen at
		// pos=(-160.00,160.00,128.00) with move=0.0000, path=0.00 for 400+ frames.
		//
		// Since AcceptCameraSnapshot() gates SetMappedFrameBuffer(), a rejection
		// means DLSS-G never sees that snapshot and reprojects with the previous
		// accepted one. Feeding it a parked camera while discarding the moving one
		// reproduces the exact symptom: geometry and characters pinned to one
		// stale view while only engine-native particles (fire) keep animating.
		//
		// The premise was never verified -- it was inferred from a single odd dump
		// and treated as structural. This engine's camera block demonstrably
		// carries a perspective term, so [3][3] == 0 is legal here.
		//
		// The guard is removed. The OBSERVATION is kept, now non-destructive:
		// count the population and log the full last row plus the 3x3 determinant
		// for the first few and every 500th, so the next run can show what these
		// matrices are without costing a run.
		{
			const float w = a_src.CameraViewProjUnjittered.data[3][3];
			const float dw = (w > 1.0f) ? (w - 1.0f) : (1.0f - w);
			if (!(dw <= 1.0e-3f)) {
				++snapRejectShape;              // kept as a COUNTER only
				if (snapRejectShape <= 5u || (snapRejectShape % 500u) == 0u) {
					const auto& d = a_src.CameraViewProjUnjittered.data;
					SKSE::log::info("[CAM] #{} non-affine w={:.6g} ACCEPTED (v0.89) "
						"row3=({:.6g},{:.6g},{:.6g},{:.6g}) det3={:.6g} "
						"pos=({:.1f},{:.1f},{:.1f})",
						snapArrivals, w, d[3][0], d[3][1], d[3][2], d[3][3],
						camDet3(a_src.CameraViewProjUnjittered), px, py, pz);
				}
				// NO return false: the snapshot is published as before v0.86.
			}
		}

		// ---- v0.78: frozen-matrix gate (must run BEFORE the jump gate) --------
		// A stale perFrame slot passes `usable` (non-zero, non-NaN) and produces
		// d2 == 0, so the jump gate below can never see it. Detect it by matrix
		// identity instead: an identical matrix arriving after a *different* one
		// cannot be a still scene.
		{
			const Matrix& m = a_src.CameraViewProjUnjittered;
			bool identical = false;
			if (snapHaveLastMat) {
				identical = true;
				for (int r = 0; r < 4 && identical; ++r) {
					for (int k = 0; k < 4; ++k) {
						if (snapLastMat[r][k] != m.data[r][k]) { identical = false; break; }
					}
				}
			}
			// v0.83: split the two populations so the log shows how much of the
			// stream is byte-identical (a stale slot) vs genuinely changing.
			if (identical)
				++snapIdenticalArrivals;
			else
				++snapDifferentArrivals;

			if (identical && snapSawDifferentSinceRepeat) {
				// Same matrix as last time, but we saw a different camera in
				// between => this is a stale slot being re-read, not a still scene.
				++snapFrozenRepeats;
				// v0.84: reject only after kCamFrozenTol *consecutive* identical
				// arrivals. The counter is reset below as soon as a different matrix
				// shows up (v0.78 never reset it, so it grew without bound and the
				// gate latched on permanently -- see add_v084_gate_reset.py header).
				if (snapFrozenRepeats > kCamFrozenTol) {
					++snapFrozenReject;
					// v0.93: gates observe, they do not discard.
					//
					// Keeping snapLastMat untouched is still correct (the slot is
					// still suspected stale, so the next arrival must be compared
					// against the same reference), but the snapshot is no longer
					// withheld from DLSS-G.
					//
					// Why the old `return false` was fatal: SetMappedFrameBuffer()
					// runs ONLY on accept (FrameGen.cpp:583), so a rejection left
					// mappedFrameBuffer null, GetFrameBuffer() null, and Present
					// skipped SetDLSSGOptions altogether. Log: blocked=483 vs
					// unblocked=1. v0.89 removed this same return from the shape
					// gate after proving 80.6% of the discarded population was the
					// real moving camera; the two other gates were left alone.
				}
			} else if (!identical) {
				snapSawDifferentSinceRepeat = true;
				// v0.84: a genuinely different matrix proves the stream is alive, so
				// the stale-slot run is over and the consecutive count restarts.
				// This reset is the actual fix: without it the count only ever grows,
				// so past kCamFrozenTol every identical frame is refused forever.
				snapFrozenRepeats = 0;
				++snapFrozenResets;
			}
			for (int r = 0; r < 4; ++r)
				for (int k = 0; k < 4; ++k)
					snapLastMat[r][k] = m.data[r][k];
			snapHaveLastMat = true;
		}

		float d2 = 0.0f;
		if (snapHaveLast) {
			const float dx = px - snapLastPos[0];
			const float dy = py - snapLastPos[1];
			const float dz = pz - snapLastPos[2];
			d2 = dx * dx + dy * dy + dz * dz;
		}
		snapLastDist = snapHaveLast ? std::sqrt(d2) : 0.0f;

		// ---- v0.94: source lock (replaces the distance gate) ------------------
		//
		// WHY THE DISTANCE GATE HAD TO GO
		//
		// v0.67..v0.93 decided which arrival to publish by distance: "a camera
		// cannot move 400 units in one frame, so a far arrival is a different
		// source -- reject it". That test cannot work, because the two things it
		// tries to separate are NOT separated by distance:
		//
		//   - the real camera, moving smoothly, and
		//   - two CONSTANT slots re-read every frame,
		//
		// all coexist in one perFrame buffer, and the distance between them
		// changes as the player walks. Worse, it never re-asks the question: it
		// locks onto whichever source it saw first and then rejects the others
		// forever. The 16:04 log shows exactly that -- it held (-160,160,128),
		// a CONSTANT, while rejecting the smoothly moving (-50,900->894,96):
		//
		//     #9015 JUMP rejected: pos=(-1101.1,880.9,114.0) last=(-160.0,160.0,128.0)
		//     accepting      pos=(-160.0,160.0,128.0)   <- 806 times, CONSTANT
		//
		// WHY RELEASING EVERYTHING (v0.93) WAS WORSE
		//
		// v0.93 removed the veto entirely, so all sources took turns owning
		// frameBufferCopy. Consecutive frames handed DLSS-G cameras hundreds of
		// units apart, every frame, and the game CTD'd:
		//
		//     #7818 RELOCK after 1 consecutive jumps -> pos=(-1101.1,880.9,114.0)
		//     #7824 RELOCK after 1 consecutive jumps -> pos=( -126.3,211.2,188.9)
		//     #7837 RELOCK after 1 consecutive jumps -> pos=(    0.0,  0.0,  1.0)
		//     path=845264.19 -> 864056.62
		//
		// THE ACTUAL QUESTION
		//
		// Not "is this arrival far", but "does it CONTINUE the stream I am
		// already publishing?". A real camera advances by a small step between
		// consecutive arrivals; a stale slot is either constant or unrelated. So:
		//
		//   - while locked, publish ONLY arrivals that step <= kCamStepTol from
		//     the last published position (that is the same source continuing);
		//   - count the rest; if the locked stream does not continue for
		//     kCamStillTol arrivals in a row, the stream is gone (scene change,
		//     loading screen) and the next arrival re-acquires the lock.
		//
		// The lock guarantees exactly one source is published at a time, which is
		// what DLSS-G needs, and it never relies on a teleport heuristic.
		// ---- v1.00: projection-family fingerprint ----
		// ProjUnj[0][0] identifies the projection kind. Compare it against the
		// family currently locked, with a RELATIVE tolerance so the test does
		// not depend on the resolution / FOV this run happens to use.
		//
		// v1.00b: these two live OUTSIDE the block below, because the accept path
		// (which refreshes snapLockProj00) sits after the block has closed.
		const float proj00 = a_src.CameraProjUnjittered.data[0][0];
		const bool projOk = (proj00 == proj00) && (proj00 > 1.0e-6f);
		// v1.03: one line the first time the magnitude-class escape is used, so
		// "the escape fired" can be told apart from "the ratio test passed".
		static bool snapLockAltFamilyLogged = false;

		// ---- v1.07: consume a release raised by the reset / menu edge ---------
		// The edge is computed in Streamline and already tells DLSS-G to discard
		// its reprojection history. The locked camera family is part of that
		// same history, and until v1.07 it had no way to hear about it - which
		// is why the 22:02 run kept publishing the 3D-menu family after the
		// main menu had closed and the world had started.
		if (snapLockReleasePending) {
			snapLockReleasePending = false;
			++snapLockReleased;
			if (snapLockReleased <= 5u) {
				SKSE::log::info("[CAM] #{} lock RELEASED on the reset edge (was "
					"proj00={:.6g} famRej={}) - the next arrival re-acquires",
					snapArrivals, snapLockProjValid ? snapLockProj00 : 0.0f,
					snapLockFamilyRej);
			}
			snapLockHave = false;
			snapLockProjValid = false;
			snapHaveLast = false;
			snapLockStill = 0;
			// v1.10: same reason as the acquire path
			snapForeignMove = 0.0f;
			snapForeignHave = false;
		}

		{
			bool sameFamily = true;
			// v1.10: set when a moving foreign family took the anchor, so the
			// same-family step-break log below does not describe it wrongly.
			bool foreignTakeover = false;
			if (projOk && snapLockProjValid) {
				// v1.03 used to put a magnitude-class escape in front of this
				// test: proj00 == 1.0 is a unit / orthographic projection, so it
				// was admitted as "a legal second camera" instead of being
				// refused as another render pass, and +-2% only ran when both
				// sides were in the same magnitude class. v1.07 removed it.
				//
				// v1.07: the v1.03 magnitude-class escape is GONE.
				//
				// It admitted any arrival whenever exactly one of the two
				// projections was a unit projection:
				//     if (unitProj != lockUnit) sameFamily = true;
				// and because the accept path then refreshed snapLockProj00 to
				// the newly accepted arrival, the escape could never settle. The
				// 22:02 log is that walk, verbatim:
				//
				//   #1  acquire  proj00=0.149184                -> lock 0.149184
				//   #2  esc 1.0      vs locked 0.149184 -> adopt  -> lock 1.0
				//   #4  esc 0.149184 vs locked 1.0      -> adopt  -> lock 0.149184
				//   #11 esc 1.0      vs locked 0.149184 -> adopt  -> lock 1.0
				//   #13 esc 0.149184 vs locked 1.0      -> adopt  -> lock 0.149184
				//
				// While the lock reads 1.0 (a unit projection) EVERY non-unit
				// arrival counts as a legal second camera - including 0.8391,
				// the 3D-menu family. Once the lock reads 0.8391 the ratio test
				// refuses the world camera (0.149184/0.8391 = 0.178) and the old
				// code returned false forever.
				//
				// The escape was a workaround for the missing release path, not
				// a classification. With the release added above it is both
				// unnecessary and the thing that walks the lock into the wrong
				// family, so the ratio test stands alone again.
				const float ratio = proj00 / snapLockProj00;
				sameFamily = (ratio > 0.98f) && (ratio < 1.02f);
			}

			const bool continues = snapLockHave && snapHaveLast && (d2 <= kCamStepTol2);
			if (!snapLockHave) {
				// First arrival, or the locked stream died: acquire.
				snapLockHave = true;
				snapLockStill = 0;
				// v1.10: travel accumulated against the OLD anchor is not
				// evidence about the new one
				snapForeignMove = 0.0f;
				snapForeignHave = false;
				if (snapLockRelock > 0u || snapAccept > 0u)
					++snapLockRelock;
			} else if (!continues) {
				// A different source showed up. Hold it; do not publish, and do
				// not let it move the anchor. If the locked stream keeps failing
				// to continue, it is genuinely gone and we re-acquire below.
				++snapLockHold;
				// ---- v1.00: a different projection family may NEVER re-acquire ----
				// v0.94 re-acquired unconditionally after kCamStillTol non-continuing
				// arrivals, so a foreign camera that arrived monotonically for 90
				// frames was adopted and then "continued" itself forever. That is the
				// freeze. Only an arrival from the SAME family may take over.
				if (!sameFamily) {
					++snapLockFamilyRej;
					// v1.07: this branch used to return WITHOUT touching snapLockStill,
					// so `still` stayed 0 for a whole run and the release below could
					// never be reached from here. The 22:02 run printed
					// lock(pub/hold/re/still)=11821/2725/2416/0 with famRej=309 - 309
					// refusals and not one of them counted.
					++snapLockStill;
					if (snapLockFamilyRej <= 3u || (snapLockFamilyRej % 500u) == 0u) {
						SKSE::log::info("[CAM] #{} family rejected: proj00={:.6g} locked={:.6g} "
							"ratio={:.4f} pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} still={}/{}",
							snapArrivals, proj00, snapLockProj00,
							snapLockProjValid ? (proj00 / snapLockProj00) : 0.0f,
							px, py, pz, std::sqrt(d2), snapLockStill, kCamStillTol);
					}
					// v1.07b: do NOT re-acquire here.
					//
					// The first v1.07 draft let this branch re-adopt after
					// kCamStillTol consecutive family rejections. The offline
					// regression showed that is not a repair: the branch adopts
					// whichever arrival happens to BE the 90th non-continuation,
					// and with two foreign families arriving it lands on the unit
					// orthographic projection half the time - proj00=1, which is
					// just a different wrong family, and one whose clipToPrev is
					// an identity, i.e. exactly the freeze.
					//
					// It also re-opened the door v1.00 closed two lines up the
					// block: v0.94's unconditional kCamStillTol re-acquire IS the
					// documented freeze, and "only a same-family arrival may take
					// over" is the invariant that fixed it. So the refusal is
					// unconditional again.
					//
					// The reset-edge release above remains the ONLY release path.
					// It is deterministic rather than order-dependent: it fires at
					// a menu transition and hands the lock to the first arrival
					// after it, which is the world camera whenever the menu has
					// closed. The counter below is untouched, so still=N/M keeps
					// reporting how long the locked family has been failing.
					if (d2 > kCamJumpTol2) ++snapRejectJump;
					// ---- v1.10: a MOVING family beats a STILL lock ----------------
					// Rationale and the 11:30 numbers: see FrameGen.h, next to
					// snapForeignMove. The refused family must TRAVEL before it may
					// take the anchor, so this is not v0.94's order-dependent
					// re-acquire that v1.07b removed.
					{
						if (proj00 != snapForeignProj00) {
							// a different refused family: this travel is not ours
							snapForeignProj00 = proj00;
							snapForeignMove = 0.0f;
							snapForeignHave = false;
						}
						const float fdx = px - snapForeignPos[0];
						const float fdy = py - snapForeignPos[1];
						const float fdz = pz - snapForeignPos[2];
						if (snapForeignHave) {
							const float fStep = std::sqrt(fdx * fdx + fdy * fdy + fdz * fdz);
							// a camera step is tens of units, a slot jump hundreds:
							// cap one step so a jump cannot fake travel on its own
							if (fStep < kCamJumpTol) snapForeignMove += fStep;
						}
						snapForeignPos[0] = px;
						snapForeignPos[1] = py;
						snapForeignPos[2] = pz;
						snapForeignHave = true;
						// v1.11: was snapLockStill >= kCamForeignMinRej, which the
						// frozen family reset to 0 on every one of its own accepts.
						// See the kCamPubStaleTol comment for the 14:20 numbers.
						if (snapPubStale >= kCamPubStaleTol &&
						    snapForeignMove >= kCamForeignMoveTol) {
							++snapForeignTakeover;
							foreignTakeover = true;
							if (snapForeignTakeover <= 5u) {
								SKSE::log::info("[CAM] #{} FOREIGN TAKEOVER (v1.11): locked "
									"proj00={:.6g} has gone {} publishes with an unchanged "
									"matrix while the refused family proj00={:.6g} travelled "
									"{:.1f} units - adopting pos=({:.1f},{:.1f},{:.1f})",
									snapArrivals,
									snapLockProjValid ? snapLockProj00 : 0.0f,
									snapPubStale, proj00, snapForeignMove, px, py, pz);
							}
							snapForeignMove = 0.0f;
							snapForeignHave = false;
							// fall through to the adopt path below; it refreshes
							// snapLockProj00 after the publish (v1.00 block)
						} else {
							return false;
						}
					}
				}
				// ---- v1.00g: same-family non-continuation re-acquires NOW ----
				// Reaching this point already proves three things at once:
				//   1. a lock exists,
				//   2. the arrival is in the SAME projection family as the lock
				//      (a different family returned above), and
				//   3. d2 > kCamStepTol2 -- it did not continue the stream.
				//
				// For a same-family stream, (3) has exactly two causes: the player
				// teleported / the scene changed (measured 250 units going into the
				// world, 1259 into the frozen run), or the slot stopped updating.
				// Both mean the old anchor is stale, and holding it only makes
				// DLSS-G reproject against a parked view -- which IS the freeze.
				// So take the new anchor immediately.
				//
				// v1.00f used kCamJumpTol (400) here and therefore MISSED the 250
				// unit transition into the world; the offline regression caught it
				// (adoptions stayed at 38, stream parked on the loading camera).
				// The boundary is kCamStepTol, which is the very test that put us
				// in this branch.
				++snapLockStill;
				++snapLockRelockJump;
				if (!foreignTakeover && snapLockRelockJump <= 5u) {
					SKSE::log::info("[CAM] #{} same-family step break: pos=({:.1f},{:.1f},{:.1f}) "
						"locked=({:.1f},{:.1f},{:.1f}) dist={:.1f} proj00={:.6g} still={}/{} "
						"- adopting the new anchor",
						snapArrivals, px, py, pz,
						snapLastPos[0], snapLastPos[1], snapLastPos[2],
						std::sqrt(d2), proj00, snapLockStill, kCamStillTol);
				}
				// The anchor is stale. Re-acquire on this arrival and drop the stale
				// anchor so the next test is made against the new source rather
				// than the old one.
				snapLockHave = true;
				snapLockStill = 0;
				++snapLockRelock;
				snapHaveLast = false;
			} else {
				snapLockStill = 0;
			}
			++snapLockPublish;
		}

		frameBufferCopy = a_src;
		++snapAccept;
		// v1.09: how often the matrix we PUBLISH actually changes. `snapAccept`
		// alone cannot answer that -- 19 288 consecutive accepts at a byte-identical
		// matrix is exactly what the freeze looks like from this side.
		{
			bool same = snapPubHaveMat;
			if (same) {
				for (int r = 0; r < 4 && same; ++r) {
					for (int k = 0; k < 4; ++k) {
						if (snapPubLastMat[r][k] != a_src.CameraViewProjUnjittered.data[r][k]) {
							same = false;
							break;
						}
					}
				}
			}
			if (!same) {
				++snapMatChanges;
				// v1.11: the published stream moved, so the lock is demonstrably
				// alive. THIS IS THE ONLY WRITE THAT CLEARS THE COUNTER -- a
				// second writer (an accept, a release, a timer) would let the
				// stagnation erase the evidence of itself, which is exactly the
				// defect this release removes.
				snapPubStale = 0;
			} else {
				// v1.11: the SAME matrix went out again. The direct measurement of
				// "the published stream is dead" -- snapMatChanges can only report
				// that it is dead on average over a whole run.
				++snapPubStale;
			}
			for (int r = 0; r < 4; ++r)
				for (int k = 0; k < 4; ++k)
					snapPubLastMat[r][k] = a_src.CameraViewProjUnjittered.data[r][k];
			snapPubHaveMat = true;
		}

		// ---- v1.00: remember which family owns the stream ----
		if (projOk) {
			snapLockProj00 = proj00;
			snapLockProjValid = true;
		}
		snapAcceptDist = snapHaveLast ? std::sqrt(d2) : 0.0f;
		snapPathLen += snapAcceptDist;
		DumpCameraSnapshot(a_src, snapArrivals, 1);
		// v0.68：捕获层的**运动轨迹**。这是判定「被捕获的相机到底有没有跟着玩家动」
		// 的那一行 —— 若玩家在走而这里 move/path 恒为 0.000，则根因在捕获层（读到的
		// 相机数据不跟踪真实相机），任何重投影侧的修法都救不了。节流 0.25 s，最多 200 行。
		{
			static auto lastAccLog = std::chrono::steady_clock::now() - std::chrono::seconds(30);
			static std::uint64_t accLogs = 0;
			const auto now = std::chrono::steady_clock::now();
			if (snapAccept == 1u || std::chrono::duration<double>(now - lastAccLog).count() >= 1.0) {
				lastAccLog = now;
				++accLogs;
				SKSE::log::info("[CAM] acc #{} pos=({:.2f},{:.2f},{:.2f}) move={:.4f} path={:.2f} "
				"devVP={:.6g} detVP={:.6g} magVP={:.6g} consecJmp={}",
				snapAccept, px, py, pz, snapAcceptDist, snapPathLen,
				camDev(a_src.CameraViewProjUnjittered), camDet3(a_src.CameraViewProjUnjittered),
				camMag(a_src.CameraViewProjUnjittered), snapConsecReject);
				// v1.09: the published-stream trace.
				//
				// `matChanges` counts publishes whose matrix differed from the one
				// published before it. A stream that stops changing while the player
				// walks IS the freeze -- clipToPrev collapses to identity and DLSS-G
				// repeats the previous frame -- and no other line shows it directly.
				//
				// `arrivals/s` settles the calibration defect: every "consecutive
				// arrivals" threshold in this file was written for 60 arrivals/s
				// (kCamStillTol = "~1.5 s at 60 Hz"), while the hook is measured at
				// 493-502/s because the engine maps the perFrame buffer ~12 times per
				// rendered frame. Each of those thresholds therefore fires about
				// eight times earlier than its comment intends.
				{
					static std::uint64_t rateLastArrivals = 0;
					static std::uint64_t rateLastTick = 0;
					const std::uint64_t tickNow = ::GetTickCount64();
					float arrPerSec = 0.0f;
					if (rateLastTick != 0u && tickNow > rateLastTick) {
						arrPerSec = static_cast<float>(snapArrivals - rateLastArrivals) * 1000.0f /
							static_cast<float>(tickNow - rateLastTick);
					}
					rateLastArrivals = snapArrivals;
					rateLastTick = tickNow;
					SKSE::log::info("[CAM] pub #{} pos=({:.2f},{:.2f},{:.2f}) move={:.4f} path={:.2f} "
						"matChanges={} arrivalsPerSec={:.0f} | lock(pub/hold/re/still)={}/{}/{}/{} "
						"proj00={:.6g} famRej={} frozenRep={} ident/diff={}/{} "
						"fMove={:.1f} takeover={} stalePub={} cap={}/{} cen={}/{} | {}",
						snapAccept, px, py, pz, snapAcceptDist, snapPathLen, snapMatChanges,
						arrPerSec, snapLockPublish, snapLockHold, snapLockRelock, snapLockStill,
						snapLockProjValid ? snapLockProj00 : 0.0f, snapLockFamilyRej,
						snapFrozenRepeats, snapIdenticalArrivals, snapDifferentArrivals,
						snapForeignMove, snapForeignTakeover,
						snapPubStale,
						snapNonCamera, snapSkipsSinceCam, snapCensusNew, snapCensusCount,
						snapMatChanges == 0u
							? "PROBLEM nothing has ever been published with a changed matrix"
							: (snapPubStale >= kCamPubStaleTol
								   ? "PROBLEM the published camera has been byte-identical for a long run"
								   : "ok"));
				}

			}
		}
		snapLastPos[0] = px;
		snapLastPos[1] = py;
		snapLastPos[2] = pz;
		snapHaveLast = true;
		return true;
	}

	void FrameGen::InstallContextHooks(ID3D11DeviceContext* a_context)
	{
		detour_vfunc<14, ID3D11DeviceContext_Map>(a_context);
		detour_vfunc<15, ID3D11DeviceContext_Unmap>(a_context);
		SKSE::log::info("[FrameGen] D3D11 DeviceContext Map/Unmap hooks installed (per-frame camera cache)");
	}

	// ---- D3D11 设备创建钩子 ----

	using CreateDeviceAndSwapChainFn = HRESULT(WINAPI*)(IDXGIAdapter*, D3D_DRIVER_TYPE, HMODULE, UINT,
		const D3D_FEATURE_LEVEL*, UINT, UINT, DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**, ID3D11Device**,
		D3D_FEATURE_LEVEL*, ID3D11DeviceContext**);
	CreateDeviceAndSwapChainFn g_originalCreateDevice = nullptr;

	// ---- v0.6.2（ENB 共存）----
	// FSR3 模式改调原始 D3D11CreateDeviceAndSwapChain（= ENB 代理入口，ENB 链正常创建），
	// 再 hook IDXGIFactory::CreateSwapChain（vtable 槽 10）拦截 ENB 内部创建 swapchain 的
	// 调用 → 建 FFX D3D12 链 + proxy 返回。游戏/ENB 拿到的链是 ENB 包装的 proxy →
	// ENB Present 注入照常 → ENB 效果保留（方案对齐 doodlum/ENBFrameGeneration，288K 验证）。
	using CreateSwapChainFn = HRESULT(WINAPI*)(IDXGIFactory*, IUnknown*, DXGI_SWAP_CHAIN_DESC*, IDXGISwapChain**);
	CreateSwapChainFn g_originalCreateSwapChain = nullptr;
	bool g_factoryHookInstalled = false;

	HRESULT WINAPI hk_IDXGIFactory_CreateSwapChain(IDXGIFactory2* This, ID3D11Device* a_device,
		DXGI_SWAP_CHAIN_DESC* pDesc, IDXGISwapChain** ppSwapChain)
	{
		auto& fg = Get();

		// 防御：proxy 已激活（二次创建）→ 调原始（不重复接管）
		if (fg.d3d12SwapChainActive)
			return g_originalCreateSwapChain(This, a_device, pDesc, ppSwapChain);

		// DX12 只支持 FLIP 模型——游戏/ENB 传 DISCARD 会导致 FFX swapchain 创建失败
		pDesc->SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;

		// ALLOW_TEARING（无边框窗口可用）
		IDXGIFactory5* f5 = nullptr;
		if (SUCCEEDED(This->QueryInterface(IID_PPV_ARGS(&f5)))) {
			BOOL tearing = FALSE;
			if (SUCCEEDED(f5->CheckFeatureSupport(DXGI_FEATURE_PRESENT_ALLOW_TEARING, &tearing, sizeof(tearing))) && tearing)
				pDesc->Flags |= DXGI_SWAP_CHAIN_FLAG_ALLOW_TEARING;
			f5->Release();
		}

		// ENB 内部创建链时传入的 D3D11 设备 → 存下来（interop/GetDevice 用）
		fg.dx12SwapChain.SetD3D11Device(a_device);
		ID3D11DeviceContext* ctx = nullptr;
		a_device->GetImmediateContext(&ctx);
		// v0.6.2.1：必须 SetD3D11DeviceContext（QI 持有引用）——Present 里 d3d11Context->Signal
		// 用 DX12SwapChain::d3d11Context，漏设则 null → 首帧 Present 0xC0000005（实锤）
		if (ctx) {
			fg.dx12SwapChain.SetD3D11DeviceContext(ctx);
			// GetImmediateContext 返回借用指针（不保证 AddRef），不 Release——避免引用计数误减
			fg.OnD3D11Created(a_device, ctx);
		}
		// v0.7：游戏内菜单初始化（ImGui + D3D11 后端；窗口句柄从 swapchain desc 拿）
		if (ctx)
			ImguiMenu::GetSingleton()->Init(a_device, ctx, pDesc->OutputWindow);

		// D3D12 设备 + FFX FG swapchain（device → adapter）
		IDXGIDevice* dxgiDevice = nullptr;
		if (SUCCEEDED(a_device->QueryInterface(__uuidof(IDXGIDevice), (void**)&dxgiDevice))) {
			IDXGIAdapter* adapter = nullptr;
			dxgiDevice->GetAdapter(&adapter);
			if (adapter) {
				fg.screenWidth = static_cast<float>(pDesc->BufferDesc.Width);
				fg.screenHeight = static_cast<float>(pDesc->BufferDesc.Height);
				// v0.6.3：DLSS 超分初始化（156952 组合：DLSS 超分 + FSR3 FG）——共存路径此前
				// 漏了 Streamline 初始化 → featureDLSS=false → Present 里 EvaluateDLSS 跳过。
				// provider=0 时 features=[kFeatureDLSS]，D3D11 渲染 API，模型缓存已就绪
				// （dlss/versions/0/files/160_E658703.bin = 74MB 超分真模型）。
				if (fg.settings.provider == 0) {
					// v0.25：dlssnr 准备已移除（NR 走 ReShade 外挂方案）
					fg.streamline.LoadInterposer(fg.settings);
					fg.streamline.SetD3DDevice(a_device);
					fg.streamline.CheckFeatures(adapter);
					fg.streamline.PostDevice();
				}
				fg.dx12SwapChain.CreateSwapChain(adapter, *pDesc, fg.settings.frameGeneration, fg.settings.provider == 1, fg.settings.qualityMode);
				fg.dx12SwapChain.CreateInterop();
				// v0.29（DLSSG ENB 兼容）：provider=1 的 SL 初始化已在 CreateSwapChain →
				// CreateD3D12Device 内延迟完成（v0.27 slInit + v0.28 SetD3DDevice(D3D11) +
				// SetD3D12Device）——此处补 feature 检测 + 函数绑定（漏则 featureDLSSG
				// 恒 false → 插帧不工作；PostDevice 不调 → slDLSSGSetOptions 空指针）。
				if (fg.settings.provider == 1) {
					fg.streamline.CheckFeatures(adapter);
					fg.streamline.PostDevice();
				}
				// v0.25：NGXNR 初始化已移除（NR 改由外部 ReShade dlss5 方案提供）
				adapter->Release();
			}
			dxgiDevice->Release();
		}

		*ppSwapChain = fg.dx12SwapChain.GetSwapChainProxy();
		SKSE::log::info("[FrameGen] ENB-compatible D3D12 proxy created ({}x{})", pDesc->BufferDesc.Width, pDesc->BufferDesc.Height);

		// v0.6.2.2：FSR3 FG 初始化（旧裸建分支有，新共存路径漏了——module null → Present 不插帧）
		// LoadFFX 从运行时 DLL 取函数表；SetupFrameGeneration 建 FG context（需 swapChainDesc/d3d12Device）
		auto ffx = FidelityFX::GetSingleton();
		if (!ffx->module)
			ffx->LoadFFX();
		if (ffx->module)
			ffx->SetupFrameGeneration();

		return S_OK;
	}

	static void InstallFactoryHook(IDXGIFactory* a_factory)
	{
		if (g_factoryHookInstalled || g_originalCreateSwapChain)
			return;
		auto vtable = *reinterpret_cast<uintptr_t**>(a_factory);
		// IDXGIFactory vtable：IUnknown(3)+IDXGIObject(4)+EnumAdapters/MakeWindowAssociation/
		// GetWindowAssociation(3) → CreateSwapChain 在 0-based 槽 10（ENBFrameGeneration 同款）
		g_originalCreateSwapChain = reinterpret_cast<CreateSwapChainFn>(vtable[10]);
		if (!g_originalCreateSwapChain)
			return;
		DWORD oldProtect = 0;
		VirtualProtect(&vtable[10], sizeof(uintptr_t), PAGE_READWRITE, &oldProtect);
		vtable[10] = reinterpret_cast<uintptr_t>(&hk_IDXGIFactory_CreateSwapChain);
		VirtualProtect(&vtable[10], sizeof(uintptr_t), oldProtect, &oldProtect);
		g_factoryHookInstalled = true;
		SKSE::log::info("[FrameGen] IDXGIFactory::CreateSwapChain vtable hook installed (ENB compatible)");
	}

	// ---- v0.26：强制无边框窗口化（borderless fullscreen）----
	// 帧生成硬性要求 Windowed swapchain（全屏独占 → 不代理 → 插帧不生效）。
	// ForceBorderless=1 时把游戏窗口强制成无边框铺满所在显示器（视觉等同全屏），
	// 并在 CreateDevice hook 里把 swapchain desc 强制 Windowed=TRUE → 激活判定
	// 一定通过。幂等：已满足则直接返回（每帧调用开销 <1μs）。
	void FrameGen::EnsureBorderless()
	{
		if (!settings.forceBorderless)
			return;
		const HWND h = hwnd;
		if (!h || !IsWindow(h))
			return;

		// 1) 样式检测：无边框（无 WS_CAPTION/WS_THICKFRAME）→ 尺寸也全屏则跳过
		const auto style = GetWindowLongPtrA(h, GWL_STYLE);
		if (style == 0)
			return;
		const bool hasFrame = (style & (WS_CAPTION | WS_THICKFRAME)) != 0;

		RECT rc{};
		if (!GetWindowRect(h, &rc))
			return;

		// 目标：窗口所在显示器全屏区域（多显示器正确）
		const HMONITOR mon = MonitorFromWindow(h, MONITOR_DEFAULTTONEAREST);
		MONITORINFO mi{ sizeof(mi) };
		if (!GetMonitorInfoA(mon, &mi))
			return;
		const int tw = mi.rcMonitor.right - mi.rcMonitor.left;
		const int th = mi.rcMonitor.bottom - mi.rcMonitor.top;
		const bool notFull = (rc.right - rc.left) != tw || (rc.bottom - rc.top) != th;

		if (!hasFrame && !notFull)
			return;  // 已是无边框全屏

		// 2) 应用：去边框（WS_POPUP）+ 铺满屏幕 + 还原边框重算客户区
		SetWindowLongPtrA(h, GWL_STYLE, WS_POPUP | WS_VISIBLE | WS_CLIPSIBLINGS | WS_CLIPCHILDREN);
		SetWindowPos(h, HWND_TOP, mi.rcMonitor.left, mi.rcMonitor.top, tw, th,
			SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_SHOWWINDOW);
		SKSE::log::info("[FrameGen] ForceBorderless: window {}x{} @ ({},{}) - borderless fullscreen applied",
			tw, th, mi.rcMonitor.left, mi.rcMonitor.top);
	}

	HRESULT WINAPI hk_D3D11CreateDeviceAndSwapChain(
		IDXGIAdapter* pAdapter, D3D_DRIVER_TYPE DriverType, HMODULE Software, UINT Flags,
		const D3D_FEATURE_LEVEL* pFeatureLevels, UINT FeatureLevels, UINT SDKVersion,
		DXGI_SWAP_CHAIN_DESC* pSwapChainDesc, IDXGISwapChain** ppSwapChain,
		ID3D11Device** ppDevice, D3D_FEATURE_LEVEL* pFeatureLevel, ID3D11DeviceContext** ppImmediateContext)
	{
		auto& fg = Get();

		// 防御：proxy 已激活（引擎二次创建设备/swapchain）→ 不再接管，走标准路径
		// （避免二次 CreateD3D12Proxy 覆盖状态 + 泄漏）
		if (fg.d3d12SwapChainActive)
			return g_originalCreateDevice(pAdapter, DriverType, Software, Flags, pFeatureLevels,
				FeatureLevels, SDKVersion, pSwapChainDesc, ppSwapChain, ppDevice, pFeatureLevel, ppImmediateContext);

		// v0.26：ForceBorderless——在激活判定之前强制窗口化 + 无边框铺满屏幕。
		// 帧生成硬性要求 Windowed swapchain；玩家若设了全屏独占（Windowed=false）
		// 则 shouldProxy=false → 插帧不生效（用户/发布反馈的常见“打不开”原因）。
		// 强制后：swapchain 为 windowed → 激活判定通过；窗口无边框铺满 → 视觉
		// 等同全屏。Present 每帧 EnsureBorderless 防游戏/INI 改回。
		if (fg.settings.forceBorderless && pSwapChainDesc && pSwapChainDesc->OutputWindow) {
			fg.hwnd = pSwapChainDesc->OutputWindow;
			pSwapChainDesc->Windowed = TRUE;
			SKSE::log::info("[FrameGen] ForceBorderless: swapchain desc forced Windowed=TRUE");
			fg.EnsureBorderless();
		}

		// 激活判定（与 CS 一致）：非 VR + 窗口化 + (≥120Hz 或强制) + 总开关
		// v0.5：pSwapChainDesc 判空（API 允许 null = 只创建设备）
		bool shouldProxy = fg.settings.enableFrameGen && pSwapChainDesc && pSwapChainDesc->Windowed;
		if (shouldProxy) {
			// 刷新率检测
			DEVMODEA dm{};
			dm.dmSize = sizeof(dm);
			if (EnumDisplaySettingsA(nullptr, ENUM_CURRENT_SETTINGS, &dm) && dm.dmDisplayFrequency > 0)
				fg.refreshRate = dm.dmDisplayFrequency;
			else
				fg.refreshRate = 0;
			fg.lowRefreshRate = fg.refreshRate < 120;
			if (fg.lowRefreshRate && !fg.settings.forceEnable)
				shouldProxy = false;
			SKSE::log::info("[FrameGen] Refresh rate: {} Hz (low={}, force={})",
				fg.refreshRate, fg.lowRefreshRate, fg.settings.forceEnable);
		}

		// v0.6.2（ENB 共存）：调原始函数（= ENB 代理入口，ENB 链正常创建）。
		// ENB 内部创建 swapchain 时被 factory vtable hook 拦截 → 建 D3D12 链 + proxy；
		// 游戏/ENB 拿到的链是 ENB 包装的 proxy → ENB 渲染注入与 Present 照常 → ENB 效果保留。
		// v0.29（DLSSG ENB 兼容修复）：**两模式统一走此路径**——DLSSG 原来直接
		// D3D11CreateDevice + 自建 D3D12 链，完全绕过 ENB → ENB 不加载 + 画面异常
		// （用户 20:07 实锤 “改成 DLSS 后 ENB 也不加载了，菜单按不出来，只有 FSR 有用”）。
		// hk_IDXGIFactory_CreateSwapChain 已按 provider 传 dlssgMode（581 行），
		// 拦截 ENB 的 CreateSwapChain → 建 DLSSG/FSR3 D3D12 链 + proxy。
		if (shouldProxy && pAdapter) {
			IDXGIFactory4* dxgiFactory = nullptr;
			pAdapter->GetParent(IID_PPV_ARGS(&dxgiFactory));
			if (dxgiFactory) {
				InstallFactoryHook(dxgiFactory);
				dxgiFactory->Release();
			}
			HRESULT hr = g_originalCreateDevice(pAdapter, DriverType, Software, Flags, pFeatureLevels,
				FeatureLevels, SDKVersion, pSwapChainDesc, ppSwapChain, ppDevice, pFeatureLevel, ppImmediateContext);
			if (SUCCEEDED(hr) && fg.dx12SwapChain.GetSwapChainProxy()) {
				fg.d3d12SwapChainActive = true;
				fg.fgActive.store(true);
				SKSE::log::info("[FrameGen] D3D12 proxy active (ENB compatible) - frame generation ENABLED");
			}
			return hr;
		}

		if (shouldProxy) {
			// 预加载 Streamline（slInit）。v0.5：feature 检测移到设备设置后
			//（SL 的 slIsFeatureSupported 要求 device 已设，设备前检测可能误判不支持）。
			// 这里只要求 SL 初始化成功即可建 proxy；具体 feature 不支持时 Present 直通兜底。
			// v0.25：dlssnr 准备已移除（NR 走 ReShade 外挂方案）
			// v0.27（DLSSG 频闪修复）：provider=1（DLSSG）**不在此提前 slInit**——
			// SL 错误 “Plugins already initialized but could be using the wrong device,
			// please call slSetD3DDevice immediately after creating desired device“
			// （dlss_g 插件 slInit 时 D3D12 设备还不存在 → 用错误上下文初始化 → 插帧
			// 异常 → 频闪进不去游戏，19:47 SL 日志实锤）。DLSSG 的 slInit 挪到
			// CreateD3D12Device 内（D3D12 设备创建后、SetD3D12Device 前）。
			// provider=0（FSR3）保持原状（只 DLSS 超分，D3D11 会话初始化不受影响）。
			if (fg.settings.provider != 1)
				fg.streamline.LoadInterposer(fg.settings);
			// v0.27（DLSSG 延迟 slInit）：provider=1 时这里的 initialized 恒 false 是
			// **正常状态**（slInit 在 CreateD3D12Device 内、D3D12 设备就绪后才执行）——
			// 不能当失败走标准路径（否则 DLSSG 永不启动。19:54 实锤：“Streamline init
			// failed - using standard path“ + proxy 未激活 + DRS 1.0 无插帧）。
			// provider=0（FSR3）保持原逻辑：SL 超分初始化失败才走标准路径。
			if (fg.settings.provider != 1 && !fg.streamline.initialized) {
				SKSE::log::warn("[FrameGen] Streamline init failed - using standard path");
			} else {
				SKSE::log::info("[FrameGen] Streamline initialized - creating D3D12 proxy (feature check after device setup)");

				// 只创建 D3D11 设备（不建 swapchain——由我们的 D3D12 proxy 接管）
				const D3D_FEATURE_LEVEL featureLevel = D3D_FEATURE_LEVEL_11_1;
				HRESULT hr = D3D11CreateDevice(pAdapter, DriverType, Software, Flags,
					&featureLevel, 1, SDKVersion, ppDevice, pFeatureLevel, ppImmediateContext);
				if (SUCCEEDED(hr)) {
					fg.OnD3D11Created(*ppDevice, *ppImmediateContext);
					try {
						fg.CreateD3D12Proxy(pAdapter, *pSwapChainDesc);
					} catch (...) {
						// 防御：D3D12 调用抛异常（设备移除/不支持/bad_alloc 等）会穿过 COM 边界 → 崩溃
						// 清空半创建状态 → 回退标准路径
						SKSE::log::error("[FrameGen] D3D12 proxy exception - falling back to standard path");
						fg.d3d11Device = nullptr;
						fg.d3d11Context = nullptr;
						fg.dx12SwapChain.swapChain = nullptr;
						fg.dx12SwapChain.swapChainProxy = nullptr;
						return g_originalCreateDevice(pAdapter, DriverType, Software, Flags, pFeatureLevels,
							FeatureLevels, SDKVersion, pSwapChainDesc, ppSwapChain, ppDevice, pFeatureLevel, ppImmediateContext);
					}
					// 防御：proxy 创建失败（swapchain null）→ 回退标准路径，避免把 null
					// swapchain 交给游戏（崩溃）。original 会重建 device+swapchain 覆盖指针。
					if (!fg.dx12SwapChain.GetSwapChainProxy()) {
						SKSE::log::error("[FrameGen] Proxy creation failed - falling back to standard path");
						fg.d3d11Device = nullptr;
						fg.d3d11Context = nullptr;
						return g_originalCreateDevice(pAdapter, DriverType, Software, Flags, pFeatureLevels,
							FeatureLevels, SDKVersion, pSwapChainDesc, ppSwapChain, ppDevice, pFeatureLevel, ppImmediateContext);
					}
					*ppSwapChain = fg.dx12SwapChain.GetSwapChainProxy();
					fg.d3d12SwapChainActive = true;
					// proxy 就绪 → 帧生成默认开启（Home 键可切换）；feature 不支持时
					// CreateD3D12Proxy 内已把 fgActive 置 false（直通模式）
					fg.fgActive.store(true);
					SKSE::log::info("[FrameGen] D3D12 proxy active - frame generation ENABLED");
					return S_OK;
				}
				SKSE::log::error("[FrameGen] D3D11CreateDevice failed: {:#x}", (unsigned)hr);
			}
		} else {
			SKSE::log::info("[FrameGen] Proxy not activated (enable={}, windowed={})", fg.settings.enableFrameGen,
				pSwapChainDesc ? pSwapChainDesc->Windowed : 0);
		}

		// 标准路径
		return g_originalCreateDevice(pAdapter, DriverType, Software, Flags, pFeatureLevels,
			FeatureLevels, SDKVersion, pSwapChainDesc, ppSwapChain, ppDevice, pFeatureLevel, ppImmediateContext);
	}

	void FrameGen::OnD3D11Created(ID3D11Device* a_device, ID3D11DeviceContext* a_context)
	{
		d3d11Device = a_device;
		d3d11Context = a_context;

		// 相机 near/far（REL ID：引擎全局常量）
		static REL::Relocation<void*> camBase{ REL::RelocationID(517032, 403540) };
		cameraNear = static_cast<float*>(camBase.get()) + 0x40 / 4;
		cameraFar = static_cast<float*>(camBase.get()) + 0x44 / 4;

		// v0.3：FSR3 模式 → D3D11 设备设 SL（feature 检测/函数绑定在 CreateD3D12Proxy 统一做）
		if (settings.provider == 0)
			streamline.SetD3DDevice(a_device);

		// 上下文钩子（perFrame 相机缓存）——两模式都要
		InstallContextHooks(a_context);
	}

	void FrameGen::CreateD3D12Proxy(IDXGIAdapter* a_adapter, const DXGI_SWAP_CHAIN_DESC& a_swapChainDesc)
	{
		screenWidth = static_cast<float>(a_swapChainDesc.BufferDesc.Width);
		screenHeight = static_cast<float>(a_swapChainDesc.BufferDesc.Height);

		dx12SwapChain.SetD3D11Device(d3d11Device);
		dx12SwapChain.SetD3D11DeviceContext(d3d11Context);
		dx12SwapChain.CreateSwapChain(a_adapter, a_swapChainDesc, settings.frameGeneration, settings.provider == 1, settings.qualityMode);
		// 防御：swapchain 创建失败（FFX loader 缺失等）→ 不建 interop，避免空指针
		if (!dx12SwapChain.swapChain) {
			SKSE::log::error("[FrameGen] Swap chain creation failed - proxy disabled");
			return;
		}
		dx12SwapChain.CreateInterop();

		// v0.5：feature 检测移到设备设置后（SL 要求 device 已设——设备前检测会误判不支持）
		// v0.27：SetD3D12Device 已在 CreateD3D12Device 内（设备创建后立即）调用——
		// 此处重复调用会触发 SL “Plugins already initialized but could be using the
		// wrong device“（19:47 日志 ”D3D12 device set“ ×2 实锤），已删除。
		streamline.CheckFeatures(a_adapter);
		streamline.PostDevice();

		// v0.25：DLSS-NR（NGX 直调）已移除——NR 改由外部 ReShade 方案提供

		// v0.6：FSR3 FG（Provider=0）——加载 AMD 模块 + 创建 FG context
		// （移植自 doodlum/ENBFrameGeneration；dlssgMode=false 时 CreateSwapChain 已建 ffxSwapChainContext）
		if (settings.provider == 0) {
			FidelityFX::GetSingleton()->LoadFFX();
			FidelityFX::GetSingleton()->SetupFrameGeneration();
		}

		// v0.25.4（Bug1 修复）：两模式按各自插帧引擎的可用性判断——
		// provider=0（FSR3）用 **AMD FSR3 模块**（module 加载成功 = FG 可用），
		// **不再用 featureDLSS（DLSS 超分）判断**——AMD 显卡没有 DLSS → 旧逻辑
		// featureDLSS=false → FSR3 插帧被误关 → “很多电脑装后打不开”。
		// provider=1（DLSSG）用 featureDLSSG。
		const bool featureOk = settings.provider == 1 ?
			streamline.featureDLSSG :
			(FidelityFX::GetSingleton()->module != nullptr);
		if (!featureOk) {
			SKSE::log::warn("[FrameGen] {} not available - passthrough mode (no interpolation)",
				settings.provider == 1 ? "DLSS-G" : "FSR3 FG");
			fgActive.store(false);
			return;
		}
		// v0.3：DLSSG 运行时要求 Reflex 激活
		if (settings.provider == 1)
			streamline.ActivateReflex();
	}

	// 安装 D3D11CreateDeviceAndSwapChain IAT 钩子（SKSE::PatchIAT）
	void FrameGen::InstallCreateDeviceHook()
	{
		*(uintptr_t*)&g_originalCreateDevice =
			(uintptr_t)SKSE::PatchIAT(hk_D3D11CreateDeviceAndSwapChain, "d3d11.dll", "D3D11CreateDeviceAndSwapChain");
		if (g_originalCreateDevice)
			SKSE::log::info("[FrameGen] D3D11CreateDeviceAndSwapChain IAT hook installed");
		else
			SKSE::log::error("[FrameGen] Failed to patch IAT for D3D11CreateDeviceAndSwapChain");
	}
}
