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
			else if (key == "Provider")
				settings.provider = std::clamp(readInt(line, 0), 0, 1);
			else if (key == "FrameGeneration")
				settings.frameGeneration = readBool(line, true);
			else if (key == "EnableUpscale")
				settings.enableUpscale = readBool(line, true);   // v0.7.24：DLSS 超分开关
			// v0.25：EnableDLSSNR/NRDirectTest/NR* 已移除（NR 改走 ReShade 外挂方案）
			else if (key == "FpsOverlay")
				settings.fpsOverlay = readBool(line, true);      // v0.24：FPS 显示器（默认开）
 else if (key == "QualityMode")
				settings.qualityMode = std::clamp(readInt(line, 1), 0, 4);
			else if (key == "PresetDLSS")
				settings.presetDLSS = std::clamp(readInt(line, 0), 0, 4);
			else if (key == "Sharpness") {
				// v0.6.3：DLSS 超分锐化（0-1，0=关闭）
				try {
					std::string v = line.substr(eq + 1);
					while (!v.empty() && (v.back() == ' ' || v.back() == '\r' || v.back() == '\n'))
						v.pop_back();
					settings.sharpness = std::clamp(std::stof(v), 0.0f, 1.0f);
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
		SKSE::log::info("[FrameGen] Config loaded: Enable={} ForceEnable={} Provider={} FrameGeneration={} EnableUpscale={} QualityMode={} PresetDLSS={} SL_LogLevel={} ToggleKey={:#x} FpsOverlay={}",
			settings.enableFrameGen, settings.forceEnable, settings.provider, settings.frameGeneration,
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

	// v0.7.11：Main_UpdateJitter hook（CS 同款）——引擎每帧渲染前回调，参数 State*。
	// 用 State* 在渲染前设置引擎 DRS（dynamicResolution）——引擎读后重建 kMAIN 为渲染
	// 分辨率（v0.7.9 在 Present 帧尾设置时序不对/未触发重建 → kMAIN 仍 4K → 画面 1/4）。
	// REL ID 75460/77245 已确认在 1.6.1170 Address Library 库中（offset 0xdf5480/0xe43450）。
	struct MainUpdateJitterHook
	{
		static void thunk(RE::BSGraphics::State* a_state)
		{
			func(a_state);
			Get().OnMainUpdateJitter(a_state);
		}
		static inline REL::Relocation<decltype(thunk)> func;
	};

	// v0.7.20：SetScissorRect detour（CS 同款）——DRS 下引擎 scissor 矩形是输出分辨率
	// 坐标，画到渲染分辨率（1440p）目标会裁剪（画面 1/4 放大）；按 DRS ratio 缩放。
	// REL 75564/77365 已确认在 1.6.1170 库（0xdfa550/0xe49cb0）。
	struct SetScissorRectHook
	{
		static void thunk(RE::BSGraphics::Renderer* a_this, int a_left, int a_top, int a_right, int a_bottom)
		{
			if (auto* st = RE::BSGraphics::State::GetSingleton()) {
				auto& rd = st->GetRuntimeData();
				if (!rd.dynamicResolutionLock) {
					a_left = static_cast<int>(a_left * rd.dynamicResolutionWidthRatio);
					a_right = static_cast<int>(a_right * rd.dynamicResolutionWidthRatio);
					a_top = static_cast<int>(a_top * rd.dynamicResolutionHeightRatio);
					a_bottom = static_cast<int>(a_bottom * rd.dynamicResolutionHeightRatio);
				}
			}
			func(a_this, a_left, a_top, a_right, a_bottom);
		}
		static inline REL::Relocation<decltype(thunk)> func;
	};

	void FrameGen::InstallDRSHook()
	{
		// CS: stl::write_thunk_call<Main_UpdateJitter>(REL::RelocationID(75460, 77245).address()
		//   + REL::Relocate(0xE5, isGOG ? 0x133 : 0xE2, 0x104));  // SE / AE(Steam) / VR
		const std::uintptr_t target =
			REL::RelocationID(75460, 77245).address() + REL::Relocate(0xE5, 0xE2, 0x104);
		// 防御：目标必须是 call 指令（0xE8）；不是则跳过（Present 帧尾设置保底）
		if (*(std::uint8_t*)target != 0xE8) {
			SKSE::log::warn("[FrameGen] Main_UpdateJitter hook target not a call (byte {:#x} at {:#x}) - DRS hook skipped, Present fallback",
				*(std::uint8_t*)target, target);
			return;
		}
		stl_ext::write_thunk_call<MainUpdateJitterHook>(target);
		SKSE::log::info("[FrameGen] Main_UpdateJitter hook installed (DRS + jitter, render-time)");

		// v0.7.20：SetScissorRect detour（CS 同款）——DRS 下 scissor 缩放（防裁剪/放大）
		SetScissorRectHook::func = REL::RelocationID(75564, 77365).address();
		DetourTransactionBegin();
		DetourUpdateThread(GetCurrentThread());
		DetourAttach(reinterpret_cast<PVOID*>(&SetScissorRectHook::func),
			reinterpret_cast<PVOID>(&SetScissorRectHook::thunk));
		const LONG scRes = DetourTransactionCommit();
		if (scRes == NO_ERROR) {
			SKSE::log::info("[FrameGen] SetScissorRect hook installed (DRS scissor scale)");
		} else {
			SKSE::log::error("[FrameGen] SetScissorRect detour failed ({})", scRes);
		}

		// v0.7.20：NOP 原 DRS 系统（CS 同款）——引擎 DRS 会重置/干扰我们设的 ratio/lock
		// REL 35556/36555 已验证在 1170 库（36555 -> 0x643300）；0x2D 偏移 CS 用（1.6.1170）
		REL::safe_write(
			REL::RelocationID(35556, 36555).address() + REL::Relocate(0x2D, 0x2D, 0x25),
			REL::NOP5, sizeof(REL::NOP5));
		SKSE::log::info("[FrameGen] Vanilla DRS system disabled (NOP @ 36555+0x2D)");
	}

	void FrameGen::OnMainUpdateJitter(RE::BSGraphics::State* a_state)
	{
		if (!a_state)
			return;
		// CS ConfigureUpscaling 同款：设 DRS ratio + lock（引擎渲染前 → 重建 kMAIN）
		auto& rt = a_state->GetRuntimeData();
		rt.dynamicResolutionPreviousWidthRatio = rt.dynamicResolutionWidthRatio;
		rt.dynamicResolutionPreviousHeightRatio = rt.dynamicResolutionHeightRatio;
		rt.dynamicResolutionWidthRatio = dx12SwapChain.renderScaleX;
		rt.dynamicResolutionHeightRatio = dx12SwapChain.renderScaleY;
		rt.dynamicResolutionLock = 1;

		// v0.7.18 诊断（节流）：确认 DRS hook 每帧活跃 + 实际 ratio
		static std::uint32_t drsDiag = 0;
		if (++drsDiag % 180 == 1) {
			SKSE::log::info("[FrameGen] DRS hook active: set ({:.3f},{:.3f}) readback ({:.3f},{:.3f})",
				dx12SwapChain.renderScaleX, dx12SwapChain.renderScaleY,
				rt.dynamicResolutionWidthRatio, rt.dynamicResolutionHeightRatio);
		}

		// DLSS jitter（Halton 2,3，渲染分辨率下）——CS GetJitterOffset 同款
		if (dx12SwapChain.renderWidth == 0)
			return;
		const float basePhase = 8.0f;
		const int32_t phaseCount = int32_t(basePhase * pow(
			float(dx12SwapChain.swapChainDesc.Width) / float(dx12SwapChain.renderWidth), 2.0f));
		const int32_t idx = (int32_t)(a_state->frameCount % (uint32_t)std::max(1, phaseCount)) + 1;
		float hx = 0.0f, hy = 0.0f, f = 1.0f;
		for (int32_t i = idx; i > 0;) {
			f /= 2.0f;
			hx += f * float(i % 2);
			i = int32_t(floorf(float(i) / 2.0f));
		}
		f = 1.0f;
		for (int32_t i = idx; i > 0;) {
			f /= 3.0f;
			hy += f * float(i % 3);
			i = int32_t(floorf(float(i) / 3.0f));
		}
		const float jx = hx - 0.5f;
		const float jy = hy - 0.5f;
		a_state->projectionPosScaleX = -2.0f * jx / float(dx12SwapChain.renderWidth);
		a_state->projectionPosScaleY = 2.0f * jy / float(dx12SwapChain.renderHeight);
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

		if (dx12SwapChain.dlssgMode || !fgActive.load() || !streamline.featureDLSS || !GetFrameBuffer())
			return;
		if (!dx12SwapChain.colorOutWrapped || !dx12SwapChain.d3d11Context)
			return;
		if (!renderer)
			return;
		auto& rt = renderer->GetRuntimeData();
		auto& mainRT = rt.renderTargets[RE::RENDER_TARGETS::kMAIN];
		auto& fbRT = rt.renderTargets[RE::RENDER_TARGETS::kFRAMEBUFFER];
		auto& depthTex = renderer->GetDepthStencilData().depthStencils[RE::RENDER_TARGETS_DEPTHSTENCIL::kMAIN];
		auto& mvecTex = rt.renderTargets[RE::RENDER_TARGETS::kMOTION_VECTOR];
		if (!mainRT.texture || !fbRT.texture)
			return;

		ID3D11Resource* depth11 = depthTex.texture ? static_cast<ID3D11Resource*>(depthTex.texture) : nullptr;
		ID3D11Resource* mvec11 = mvecTex.texture ? static_cast<ID3D11Resource*>(mvecTex.texture) : nullptr;

		bool ok = streamline.EvaluateDLSS(dx12SwapChain.d3d11Context.get(),
			static_cast<ID3D11Resource*>(mainRT.texture),
			dx12SwapChain.colorOutWrapped->resource11,
			depth11, mvec11, dx12SwapChain.renderWidth, dx12SwapChain.renderHeight,
			*GetFrameBuffer(), settings);

		// 超分结果（4K）写入引擎 kFRAMEBUFFER——CopyResource 要求同格式同尺寸
		// （colorOut = swapchain R8G8B8A8 4K；kFRAMEBUFFER = 后缓冲格式 4K）
		if (ok) {
			dx12SwapChain.d3d11Context->CopyResource(fbRT.texture, dx12SwapChain.colorOutWrapped->resource11);
		}
		// 诊断（节流）：kFRAMEBUFFER 尺寸/格式 + 超分是否执行
		static std::uint32_t diagFrame = 0;
		if (++diagFrame % 180 == 1) {
			D3D11_TEXTURE2D_DESC fbDesc{};
			static_cast<ID3D11Texture2D*>(fbRT.texture)->GetDesc(&fbDesc);
			D3D11_TEXTURE2D_DESC coDesc{};
			static_cast<ID3D11Texture2D*>(dx12SwapChain.colorOutWrapped->resource11)->GetDesc(&coDesc);
			SKSE::log::info("[FrameGen] MenuDraw: upscale {} kMAIN {}x{} kFRAMEBUFFER {}x{} fmt {} colorOut {}x{} fmt {}",
				ok ? "OK" : "SKIP", dx12SwapChain.renderWidth, dx12SwapChain.renderHeight,
				fbDesc.Width, fbDesc.Height, static_cast<int>(fbDesc.Format),
				coDesc.Width, coDesc.Height, static_cast<int>(coDesc.Format));
		}
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

		// v0.6.2（ENB 共存，FSR3 模式）：调原始函数（= ENB 代理入口，ENB 链正常创建）。
		// ENB 内部创建 swapchain 时被 factory vtable hook 拦截 → 建 FFX D3D12 链 + proxy；
		// 游戏/ENB 拿到的链是 ENB 包装的 proxy → ENB 渲染注入与 Present 照常 → ENB 效果保留。
		if (shouldProxy && fg.settings.provider == 0) {
			if (!pAdapter) {
				SKSE::log::warn("[FrameGen] ENB-compat: pAdapter null - falling back to standard path");
			} else {
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
		}

		if (shouldProxy) {
			// 预加载 Streamline（slInit）。v0.5：feature 检测移到设备设置后
			//（SL 的 slIsFeatureSupported 要求 device 已设，设备前检测可能误判不支持）。
			// 这里只要求 SL 初始化成功即可建 proxy；具体 feature 不支持时 Present 直通兜底。
			// v0.25：dlssnr 准备已移除（NR 走 ReShade 外挂方案）
			fg.streamline.LoadInterposer(fg.settings);
			if (!fg.streamline.initialized) {
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
		if (settings.provider == 1)
			streamline.SetD3D12Device(dx12SwapChain.d3d12Device.get());
		streamline.CheckFeatures(a_adapter);
		streamline.PostDevice();

		// v0.25：DLSS-NR（NGX 直调）已移除——NR 改由外部 ReShade 方案提供

		// v0.6：FSR3 FG（Provider=0）——加载 AMD 模块 + 创建 FG context
		// （移植自 doodlum/ENBFrameGeneration；dlssgMode=false 时 CreateSwapChain 已建 ffxSwapChainContext）
		if (settings.provider == 0) {
			FidelityFX::GetSingleton()->LoadFFX();
			FidelityFX::GetSingleton()->SetupFrameGeneration();
		}

		// 两模式按各自 feature 支持情况决定插帧是否可用（不可用 → 直通，fgActive=false）
		const bool featureOk = settings.provider == 1 ? streamline.featureDLSSG : streamline.featureDLSS;
		if (!featureOk) {
			SKSE::log::warn("[FrameGen] {} not supported on this GPU - passthrough mode (no interpolation)",
				settings.provider == 1 ? "DLSS-G" : "DLSS");
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
