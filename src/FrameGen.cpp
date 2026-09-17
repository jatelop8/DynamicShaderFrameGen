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
			SKSE::log::warn("[FrameGen] No INI found, using defaults (Enable={})", settings.enableFrameGen);
			return;
		}
		std::string line;
		while (std::getline(f, line)) {
			if (line.empty() || line[0] == ';' || line[0] == '#')
				continue;
			// v0.5：键名精确匹配（"Enable" 子串会误吞 "ForceEnable" 行——Enable 分支在前时
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
		// 但神经网络在低分辨率上分析会导致脸部重光照细节减少（"没效果"）。性能优化
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
		// "重定向现有 jmp/call"的语义（返回值 = 原跳转目标），直接 patch 函数开头
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
		struct ID3D11DeviceContext_Map
		{
			static HRESULT thunk(ID3D11DeviceContext* This, ID3D11Resource* pResource, UINT Subresource,
				D3D11_MAP MapType, UINT MapFlags, D3D11_MAPPED_SUBRESOURCE* pMappedResource)
			{
				HRESULT hr = func(This, pResource, Subresource, MapType, MapFlags, pMappedResource);
				// 防御：perFrame 缓冲指针判空（引擎加载早期可能未初始化）；
				// 只记录指针，内容在 Unmap 时拷贝（Map 时引擎可能还没写完）
				if (SUCCEEDED(hr) && pMappedResource) {
					auto* perFrame = FrameGen::GetPerFrameBuffer();
					if (perFrame && *perFrame == pResource && pMappedResource->pData)
						Get().SetMappedFrameBuffer(static_cast<FrameBuffer*>(pMappedResource->pData));
				}
				return hr;
			}
			static inline REL::Relocation<decltype(thunk)> func;
		};

		struct ID3D11DeviceContext_Unmap
		{
			static void thunk(ID3D11DeviceContext* This, ID3D11Resource* pResource, UINT Subresource)
			{
				func(This, pResource, Subresource);
				// v0.5：Unmap 时内容完整 → 值拷贝到自有缓冲（Present 线程读稳定副本，
				// 消除跨线程读半写 UB；同时让 Unmap 钩子有意义）
				auto* perFrame = FrameGen::GetPerFrameBuffer();
				if (perFrame && *perFrame == pResource) {
					auto& fg = Get();
					if (fg.GetFrameBuffer()) {
						fg.frameBufferCopy = *fg.GetFrameBuffer();
						fg.SetMappedFrameBuffer(&fg.frameBufferCopy);
					}
				}
			}
			static inline REL::Relocation<decltype(thunk)> func;
		};
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
		// 则 shouldProxy=false → 插帧不生效（用户/发布反馈的常见"打不开"原因）。
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
		// （用户 20:07 实锤 "改成 DLSS 后 ENB 也不加载了，菜单按不出来，只有 FSR 有用"）。
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
			// SL 错误 "Plugins already initialized but could be using the wrong device,
			// please call slSetD3DDevice immediately after creating desired device"
			// （dlss_g 插件 slInit 时 D3D12 设备还不存在 → 用错误上下文初始化 → 插帧
			// 异常 → 频闪进不去游戏，19:47 SL 日志实锤）。DLSSG 的 slInit 挪到
			// CreateD3D12Device 内（D3D12 设备创建后、SetD3D12Device 前）。
			// provider=0（FSR3）保持原状（只 DLSS 超分，D3D11 会话初始化不受影响）。
			if (fg.settings.provider != 1)
				fg.streamline.LoadInterposer(fg.settings);
			// v0.27（DLSSG 延迟 slInit）：provider=1 时这里的 initialized 恒 false 是
			// **正常状态**（slInit 在 CreateD3D12Device 内、D3D12 设备就绪后才执行）——
			// 不能当失败走标准路径（否则 DLSSG 永不启动。19:54 实锤："Streamline init
			// failed - using standard path" + proxy 未激活 + DRS 1.0 无插帧）。
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
		// 此处重复调用会触发 SL "Plugins already initialized but could be using the
		// wrong device"（19:47 日志 "D3D12 device set" ×2 实锤），已删除。
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
		// featureDLSS=false → FSR3 插帧被误关 → "很多电脑装后打不开"。
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
