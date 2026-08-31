// DynamicShaderFrameGen (https://github.com/jatelop8/DynamicShaderFrameGen)
// Licensed under GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception.
// Derived from open-source projects (all GPL-3.0):
//   - Skyrim Community Shaders (https://github.com/doodlum/skyrim-community-shaders)
//   - ENBFrameGeneration (https://github.com/doodlum/ENBFrameGeneration)
// Other components: Dear ImGui / CommonLibSSE-NG / Microsoft Detours (MIT).

// Note: CommonLib headers must come first (ImguiMenu.h includes d3d11.h, REX::W32 requirement)
#include "FrameGen.h"

#include "ImguiMenu.h"
#include "DX12SwapChain.h"

#include <imgui.h>
#include <imgui_impl_dx11.h>
#include <imgui_impl_win32.h>

#include <SKSE/SKSE.h>

#include <cstdio>
#include <fstream>

namespace FrameGen
{
	// v0.7: in-game settings menu (Dear ImGui) - writes Settings live, effective next frame;
	// INI untouched (Save button writes back). Menu = Home long-press.

	void ImguiMenu::Init(ID3D11Device* a_device, ID3D11DeviceContext* a_context, HWND a_hwnd)
	{
		if (initialized)
			return;
		hwnd = a_hwnd;

		IMGUI_CHECKVERSION();
		ImGui::CreateContext();
		auto& io = ImGui::GetIO();
		io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
		io.IniFilename = nullptr;  // no imgui.ini (window pos resets, no Data dir pollution)

		ImGui::StyleColorsDark();
		ImGuiStyle& style = ImGui::GetStyle();
		style.WindowRounding = 6.0f;
		style.FrameRounding = 4.0f;

		// v0.24: FPS overlay font - bold large (Windows system Arial Bold), fallback default
		{
			auto& fio = ImGui::GetIO();
			fio.Fonts->Clear();
			ImFont* bold = fio.Fonts->AddFontFromFileTTF(
				"C:\\Windows\\Fonts\\arialbd.ttf", 36.0f, nullptr,
				fio.Fonts->GetGlyphRangesDefault());
			if (!bold)
				bold = fio.Fonts->AddFontFromFileTTF(
					"C:\\Windows\\Fonts\\impact.ttf", 36.0f, nullptr,
					fio.Fonts->GetGlyphRangesDefault());
			if (!bold) {
				ImFontConfig cfg;
				cfg.SizePixels = 36.0f;  // ImGui 1.92: SizePx renamed to SizePixels
				bold = fio.Fonts->AddFontDefault(&cfg);
			}
			fontFps = bold;
			// menu UI keeps the small default font
			ImFont* ui = fio.Fonts->AddFontDefault();
			if (ui)
				fio.FontDefault = ui;
		}

		if (!ImGui_ImplWin32_Init(hwnd)) {
			SKSE::log::error("[ImguiMenu] ImGui_ImplWin32_Init failed");
			return;
		}
		if (!ImGui_ImplDX11_Init(a_device, a_context)) {
			SKSE::log::error("[ImguiMenu] ImGui_ImplDX11_Init failed");
			return;
		}

		initialized = true;
		SKSE::log::info("[ImguiMenu] ImGui initialized (menu key END/Home)");
	}

	void ImguiMenu::Shutdown()
	{
		if (!initialized)
			return;
		ImGui_ImplDX11_Shutdown();
		ImGui_ImplWin32_Shutdown();
		ImGui::DestroyContext();
		initialized = false;
	}

	void ImguiMenu::OnKeyEvent(std::uint32_t a_key, bool a_pressed)
	{
		if (!initialized)
			return;
		// Keyboard events fed to ImGui (menu nav) - vkey to ImGuiKey mapping
		ImGuiKey key = ImGuiKey_None;
		if (a_key >= 'A' && a_key <= 'Z')
			key = static_cast<ImGuiKey>(ImGuiKey_A + (a_key - 'A'));
		else if (a_key >= '0' && a_key <= '9')
			key = static_cast<ImGuiKey>(ImGuiKey_0 + (a_key - '0'));
		else if (a_key == VK_TAB)
			key = ImGuiKey_Tab;
		else if (a_key == VK_RETURN)
			key = ImGuiKey_Enter;
		else if (a_key == VK_ESCAPE)
			key = ImGuiKey_Escape;
		else if (a_key == VK_SPACE)
			key = ImGuiKey_Space;
		else if (a_key == VK_UP)
			key = ImGuiKey_UpArrow;
		else if (a_key == VK_DOWN)
			key = ImGuiKey_DownArrow;
		else if (a_key == VK_LEFT)
			key = ImGuiKey_LeftArrow;
		else if (a_key == VK_RIGHT)
			key = ImGuiKey_RightArrow;
		if (key != ImGuiKey_None)
			ImGui::GetIO().AddKeyEvent(key, a_pressed);
	}

	void ImguiMenu::Draw(FrameGen& a_fg)
	{
		if (!initialized)
			return;
		const bool wantMenu = visible;
		const bool wantFps = a_fg.settings.fpsOverlay;
		if (!wantMenu && !wantFps)
			return;

		auto& sc = a_fg.dx12SwapChain;
		// v0.7.17：菜单画在 colorOut（DLSS 超分输出 4K，随后拷贝到 backbuffer 呈现）
		auto* rtWrapped = sc.colorOutWrapped ? sc.colorOutWrapped : sc.swapChainBufferWrapped;
		if (!rtWrapped || !rtWrapped->rtv)
			return;

		ImGui_ImplDX11_NewFrame();
		ImGui_ImplWin32_NewFrame();
		auto& io = ImGui::GetIO();

		// v0.25.4（Bug3 修复）：菜单关闭时必须复位 ImGui 光标开关——旧代码只在
		// wantMenu 分支里设 MouseDrawCursor=true，关闭菜单后 io 状态保持 true →
		// FPS overlay 每帧绘制时 ImGui 小光标一直残留（"打开菜单后小鼠标不消失"）。
		io.MouseDrawCursor = wantMenu;

		if (wantMenu) {
			// v0.7.5: menu visible -> ImGui draws its own cursor (game hides the
			// system cursor in first-person; ImGui cursor follows manual MousePos)
			// Manual mouse input (no WndProc hook needed)
			POINT pt{};
			GetCursorPos(&pt);
			if (hwnd)
				ScreenToClient(hwnd, &pt);
			io.AddMousePosEvent(static_cast<float>(pt.x), static_cast<float>(pt.y));
			io.AddMouseButtonEvent(0, (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0);
			io.AddMouseButtonEvent(1, (GetAsyncKeyState(VK_RBUTTON) & 0x8000) != 0);
			io.AddMouseButtonEvent(2, (GetAsyncKeyState(VK_MBUTTON) & 0x8000) != 0);
		}

		ImGui::NewFrame();
		if (wantFps)
			DrawFps(a_fg);
		if (wantMenu)
			DrawMenu(a_fg);
		ImGui::Render();

		// Draw onto upscaled output RTV - then copied to D3D12 backbuffer for FSR3 FG
		ID3D11DeviceContext* ctx = sc.d3d11Context.get();
		ctx->OMSetRenderTargets(1, &rtWrapped->rtv, nullptr);
		ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
	}

	void ImguiMenu::DrawFps(FrameGen& a_fg)
	{
		using namespace std::chrono;
		static auto s_last = steady_clock::now();
		static float s_fps = 60.0f;
		const auto now = steady_clock::now();
		const float dt = duration_cast<duration<float>>(now - s_last).count();
		s_last = now;
		if (dt > 0.0f && dt < 1.0f) {
			const float inst = 1.0f / dt;
			s_fps = s_fps * 0.92f + inst * 0.08f;  // EMA smoothing
		}

		// Frame generation active -> show on-screen (displayed) fps (FSR3/DLSSG are 2x)
		const float mult = a_fg.fgActive.load() ? 2.0f : 1.0f;

		char buf[32];
		std::snprintf(buf, sizeof(buf), "%.0f FPS", s_fps * mult);

		ImFont* font = fontFps ? fontFps : ImGui::GetFont();
		const float size = font->LegacySize;  // font size passed to AddFont* (36.0f)
		const ImVec2 disp = ImGui::GetIO().DisplaySize;
		const ImVec2 ts = font->CalcTextSizeA(size, FLT_MAX, 0.0f, buf);
		const ImVec2 pos(disp.x - ts.x - 26.0f, 16.0f);

		ImDrawList* dl = ImGui::GetBackgroundDrawList();
		// black outline around the white text (bold look + readable on any background)
		for (int dx = -2; dx <= 2; ++dx)
			for (int dy = -2; dy <= 2; ++dy)
				if (dx * dx + dy * dy <= 8)
					dl->AddText(font, size, ImVec2(pos.x + dx, pos.y + dy),
						IM_COL32(0, 0, 0, 235), buf);
		dl->AddText(font, size, pos, IM_COL32(255, 255, 255, 255), buf);
	}

	void ImguiMenu::DrawMenu(FrameGen& a_fg)
	{
		auto& s = a_fg.settings;

		ImGui::SetNextWindowSize(ImVec2(400, 0), ImGuiCond_FirstUseEver);
		if (!ImGui::Begin("DynamicShaderFrameGen", nullptr,
				ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings)) {
			ImGui::End();
			return;
		}

		ImGui::TextWrapped("Frame Generation + DLSS Upscaling (live adjust)");
		ImGui::Separator();

		ImGui::Checkbox("Enable (master)", &s.enableFrameGen);
		// v0.7.7：FG 开关直接绑定运行时 fgActive——GUI 里点即生效，不再用 Home 短按
		bool fgOn = a_fg.fgActive.load();
		if (ImGui::Checkbox("Frame Generation (FG)", &fgOn)) {
			a_fg.fgActive.store(fgOn);
			SKSE::log::info("[FrameGen] Frame generation {} (GUI)", fgOn ? "ENABLED" : "DISABLED");
		}
		// v0.7.24：DLSS 超分开关——4K 下 DLAA 重建 ~3-5ms/帧；关掉回到纯插帧（帧数最高）
		ImGui::Checkbox("DLSS Upscale (DLAA rebuild)", &s.enableUpscale);
		ImGui::Checkbox("Force Enable (<120Hz)", &s.forceEnable);
		ImGui::Checkbox("FPS Overlay (top-right)", &s.fpsOverlay);

		// v0.25：DLSS-NR 菜单项已移除（NR 改由外部 ReShade 方案提供）

		ImGui::Separator();
		// v0.39（用户决定）：DLSSG 已移除——仅 FSR3 帧生成（N 卡也完美，+DLSS 超分）。
		// Provider 选项移除，避免用户误开 DLSSG（复杂环境频闪/黑屏不稳定）。
		ImGui::Text("Frame generation: FSR3 (AMD FG, all GPUs)");
		ImGui::TextDisabled("DLSSG removed - FSR3 is stable & universal");

		ImGui::Separator();
		const char* qualityModes[] = { "DLAA", "Quality", "Balanced", "Performance", "Ultra Performance" };
		ImGui::Combo("DLSS Quality Mode", &s.qualityMode, qualityModes, 5);
		const char* presets[] = { "Auto", "J", "K", "L", "M" };
		ImGui::Combo("DLSS Preset", &s.presetDLSS, presets, 5);
		ImGui::SliderFloat("Sharpness", &s.sharpness, 0.0f, 1.0f, "%.2f");

		ImGui::Separator();
		ImGui::Text("FG active: %s", a_fg.fgActive.load() ? "ON" : "OFF");
		ImGui::Text("DLSS: %s  DLSSG: %s",
			a_fg.streamline.featureDLSS ? "OK" : "-",
			a_fg.streamline.featureDLSSG ? "OK" : "-");
		ImGui::Text("Refresh: %.0f Hz  |  %dx%d",
			a_fg.refreshRate, (int)a_fg.screenWidth, (int)a_fg.screenHeight);
		ImGui::Text("Keys: Hold Home = Menu | FG switch in GUI");

		if (ImGui::Button("Save to INI")) {
			// Write back INI (relative path, CWD=game dir, no Data prefix)
			std::ofstream ini("Data\\SKSE\\Plugins\\DynamicShaderFrameGen.ini");
			if (ini) {
				ini << "[FrameGeneration]\n"
					<< "Enable=" << (s.enableFrameGen ? 1 : 0) << "\n"
					<< "ForceEnable=" << (s.forceEnable ? 1 : 0) << "\n"
					<< "Provider=" << s.provider << "\n"
					<< "FrameGeneration=" << (s.frameGeneration ? 1 : 0) << "\n"
					<< "EnableUpscale=" << (s.enableUpscale ? 1 : 0) << "\n"
					<< "QualityMode=" << s.qualityMode << "\n"
					<< "PresetDLSS=" << s.presetDLSS << "\n"
					<< "Sharpness=" << s.sharpness << "\n"
					<< "StreamlineLogLevel=" << s.streamlineLogLevel << "\n"
					<< "ToggleKey=0x" << std::hex << s.toggleKey << std::dec << "\n";
				ini.close();
				ImGui::TextColored(ImVec4(0.2f, 1.0f, 0.4f, 1.0f), "Saved");
			} else {
				ImGui::TextColored(ImVec4(1.0f, 0.3f, 0.3f, 1.0f), "Save failed");
			}
		}

		ImGui::End();
	}
}
