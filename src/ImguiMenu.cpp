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
		if (!initialized || !visible)
			return;

		auto& sc = a_fg.dx12SwapChain;
		// v0.7.17：菜单画在 colorOut（DLSS 超分输出 4K，随后拷贝到 backbuffer 呈现）
		auto* rtWrapped = sc.colorOutWrapped ? sc.colorOutWrapped : sc.swapChainBufferWrapped;
		if (!rtWrapped || !rtWrapped->rtv)
			return;

		ImGui_ImplDX11_NewFrame();
		ImGui_ImplWin32_NewFrame();
		auto& io = ImGui::GetIO();
		// v0.7.5: menu visible -> ImGui draws its own cursor (game hides the
		// system cursor in first-person; ImGui cursor follows manual MousePos)
		io.MouseDrawCursor = true;

		// Manual mouse input (no WndProc hook needed)
		POINT pt{};
		GetCursorPos(&pt);
		if (hwnd)
			ScreenToClient(hwnd, &pt);
		io.AddMousePosEvent(static_cast<float>(pt.x), static_cast<float>(pt.y));
		io.AddMouseButtonEvent(0, (GetAsyncKeyState(VK_LBUTTON) & 0x8000) != 0);
		io.AddMouseButtonEvent(1, (GetAsyncKeyState(VK_RBUTTON) & 0x8000) != 0);
		io.AddMouseButtonEvent(2, (GetAsyncKeyState(VK_MBUTTON) & 0x8000) != 0);

		ImGui::NewFrame();
		DrawMenu(a_fg);
		ImGui::Render();

		// Draw onto upscaled output RTV - then copied to D3D12 backbuffer for FSR3 FG
		ID3D11DeviceContext* ctx = sc.d3d11Context.get();
		ctx->OMSetRenderTargets(1, &rtWrapped->rtv, nullptr);
		ImGui_ImplDX11_RenderDrawData(ImGui::GetDrawData());
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

		// v0.8：DLSS-NR（神经渲染）——NGX 直调，RTX 50 系专属。
		// 未初始化/不支持（4080 无 sm_120 cubin、缺 nvngx_dlssnr.dll）→ 灰掉不崩
		ImGui::Separator();
		const bool nrAvailable = a_fg.ngxNR.initialized && a_fg.ngxNR.supported;
		if (!nrAvailable) {
			ImGui::TextColored(ImVec4(0.8f, 0.6f, 0.2f, 1.0f), "DLSS-NR: unavailable");
			if (ImGui::IsItemHovered())
				ImGui::SetTooltip("Requires RTX 50-series (sm_120 kernel) + nvngx_dlss.dll + nvngx_dlssnr.dll\nin Data/Shaders/Upscaling/Streamline/ (not redistributed).");
			ImGui::BeginDisabled();
		}
		ImGui::Checkbox("DLSS-NR (Neural Rendering)", &s.enableDLSSNR);
		ImGui::SliderFloat("NR Intensity", &s.nrIntensity, 0.0f, 1.0f, "%.2f");
		ImGui::SliderFloat("NR Style", &s.nrStyle, 0.0f, 1.0f, "%.2f");
		ImGui::SliderFloat("NR Local Tone", &s.nrLocalTone, 0.0f, 1.0f, "%.2f");
		ImGui::SliderFloat("NR Skin Structure", &s.nrSkinStructure, 0.0f, 1.0f, "%.2f");
		if (!nrAvailable)
			ImGui::EndDisabled();
		if (a_fg.ngxNR.lastEvaluateOk)
			ImGui::TextColored(ImVec4(0.2f, 1.0f, 0.4f, 1.0f), "NR: running (eval ok)");
		else if (s.enableDLSSNR)
			ImGui::TextColored(ImVec4(1.0f, 0.3f, 0.3f, 1.0f), "NR: failed (rc=%08x)", a_fg.ngxNR.lastEvaluateResult);

		ImGui::Separator();
		ImGui::Text("Provider (change needs restart)");
		const char* providers[] = { "FSR3 (AMD FG)", "DLSSG (NVIDIA FG)" };
		ImGui::Combo("Provider", &s.provider, providers, 2);

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
					<< "EnableDLSSNR=" << (s.enableDLSSNR ? 1 : 0) << "\n"
					<< "NRIntensity=" << s.nrIntensity << "\n"
					<< "NRStyle=" << s.nrStyle << "\n"
					<< "NRLocalTone=" << s.nrLocalTone << "\n"
					<< "NRSkinStructure=" << s.nrSkinStructure << "\n"
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
