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
#include "NeuralRendering/Renderer.h"  // DLSSNR 状态显示

#include <imgui.h>
#include <imgui_impl_dx11.h>
#include <imgui_impl_win32.h>

#include <SKSE/SKSE.h>

#include <cstdio>
#include <fstream>
#include <iomanip>

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

		// v0.53: honesty fix. This line hardcoded x2 whenever frame generation was on.
		// Two consequences: it could never show 3x/4x, so switching from FSR3 2x to
		// DLSSG MFG looked like "nothing changed any more"; and it printed a doubled
		// number even when the runtime had rejected the request. The factor now comes
		// from what the runtime actually reported doing, and nothing is inflated when
		// nothing is generated.
		float mult = 1.0f;
		const char* tag = "";
		if (a_fg.dx12SwapChain.dlssgMode) {
			// dlssgFramesPresentedLast = frames the runtime really presented for the last
			// real frame. >1 is measured evidence of multi-frame generation; <=1 means
			// DLSSG is not generating, so the number must NOT be doubled.
			const std::uint32_t presented = a_fg.streamline.dlssgFramesPresentedLast;
			if (presented > 1u)
				mult = static_cast<float>(presented);
			else
				tag = " (MFG off)";
		} else if (a_fg.fgActive.load()) {
			mult = 2.0f;  // FSR3 generates exactly one frame (verified by the dispatch probe)
		}

		char buf[32];
		std::snprintf(buf, sizeof(buf), "%.0f FPS%s", s_fps * mult, tag);

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

	// v0.52：INI 写回统一入口（"Save to INI" 按钮 + 改动即存共用）。
	// ① 写侧路径必须与 LoadConfig 的读取路径**逐字一致**（LoadConfig 用
	//    "Data/SKSE/Plugins/..."）。旧版写侧用反斜杠，且失败只改按钮文字、不写日志
	//    ——用户改了开关、重启后配置没变，日志里也查不到任何痕迹，表现就是
	//    "切换了没有任何变化"。
	// ② 必须写全 LoadConfig 认识的**每一个**键。旧版只写 17 个，文件是截断重写，
	//    于是点一次 Save 就把 QualityMode / RenderResolutionScale / Sharpness /
	//    FpsOverlay / EnableUpscale / PresetDLSS 整行删掉（自定义渲染比例被静默重置）。
	// 注意：MO2 下对 mod 提供的文件写入会被重定向到 overwrite（优先级高于 mods），
	// 这是预期行为——写进 overwrite 的那份会盖住 mod 里的模板，下次启动即生效。
	static bool SaveSettingsToIni(FrameGen& a_fg)
	{
		auto& s = a_fg.settings;
		const char* iniPath = "Data/SKSE/Plugins/DynamicShaderFrameGen.ini";
		std::ofstream ini(iniPath);
		if (!ini) {
			SKSE::log::error("[FrameGen] INI save FAILED: cannot open {} (CWD must be the game dir)", iniPath);
			return false;
		}
		ini << "[FrameGeneration]\n"
			<< "Enable=" << (s.enableFrameGen ? 1 : 0) << "\n"
			<< "ForceEnable=" << (s.forceEnable ? 1 : 0) << "\n"
			<< "ForceBorderless=" << (s.forceBorderless ? 1 : 0) << "\n"
			<< "Provider=" << s.provider << "\n"
			<< "FrameGeneration=" << (s.frameGeneration ? 1 : 0) << "\n"
			<< "EnableUpscale=" << (s.enableUpscale ? 1 : 0) << "\n"
			<< "NeuralRenderingEnabled=" << (s.neuralRenderingEnabled ? 1 : 0) << "\n"
			<< "NRIntensity=" << a_fg.nrTuning.intensity << "\n"
			<< "NRLocalTone=" << a_fg.nrTuning.localToneStrength << "\n"
			<< "NRLocalStructure=" << a_fg.nrTuning.localStructureStrength << "\n"
			<< "NRSkinStructure=" << a_fg.nrTuning.skinStructureStrength << "\n"
			<< "NRStyle=" << a_fg.nrTuning.style << "\n"
			<< "NRAutoMask=" << (a_fg.nrTuning.useAutoMask ? 1 : 0) << "\n"
			<< "NRUICorrection=" << (a_fg.nrTuning.uiCorrection ? 1 : 0) << "\n"
			<< "NRRenderScale=" << std::fixed << std::setprecision(2) << a_fg.nrTuning.renderScale << "\n"
			<< "FpsOverlay=" << (s.fpsOverlay ? 1 : 0) << "\n"
			<< "QualityMode=" << s.qualityMode << "\n"
			<< "PresetDLSS=" << s.presetDLSS << "\n"
			<< "DLSSGFramesToGenerate=" << s.dlssgFramesToGenerate << "\n"
			<< "MFGMaxFramesOverride=" << s.mfgMaxFramesOverride << "\n"
			<< "Sharpness=" << s.sharpness << "\n"
			<< "RenderResolutionScale=" << std::fixed << std::setprecision(2) << s.renderResolutionScale << "\n"
			<< "StreamlineLogLevel=" << s.streamlineLogLevel << "\n"
			<< "ToggleKey=0x" << std::hex << s.toggleKey << std::dec << "\n";
		ini.close();
		SKSE::log::info("[FrameGen] INI saved: Provider={} DLSSGFramesToGenerate={} MFGMaxFramesOverride={} NR={}",
			s.provider, s.dlssgFramesToGenerate, s.mfgMaxFramesOverride, s.neuralRenderingEnabled ? 1 : 0);
		return true;
	}

	void ImguiMenu::DrawMenu(FrameGen& a_fg)
	{
		auto& s = a_fg.settings;
		auto& sc = a_fg.dx12SwapChain;

		ImGui::SetNextWindowSize(ImVec2(400, 0), ImGuiCond_FirstUseEver);
		if (!ImGui::Begin("DynamicShaderFrameGen", nullptr,
				ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings)) {
			ImGui::End();
			return;
		}

		// v0.52：标题别再写 "DLSS Upscaling"——超分在 v0.48 已移除，否则用户会一直找那个
		// 不存在的开关（"切换 DLSS 没反应"的一部分就来自这类过期文案）。
		ImGui::TextWrapped("Frame Generation + DLSS5 Neural Rendering (live adjust)");
		ImGui::TextDisabled("NOTE: DLSS upscaling was removed in v0.48 - there is no DLSS upscale switch.");
		ImGui::Separator();

		ImGui::Checkbox("Enable (master)", &s.enableFrameGen);
		// v0.7.7：FG 开关直接绑定运行时 fgActive——GUI 里点即生效，不再用 Home 短按
		bool fgOn = a_fg.fgActive.load();
		if (ImGui::Checkbox("Frame Generation (FG)", &fgOn)) {
			a_fg.fgActive.store(fgOn);
			SKSE::log::info("[FrameGen] Frame generation {} (GUI)", fgOn ? "ENABLED" : "DISABLED");
		}
		ImGui::Checkbox("Force Enable (<120Hz)", &s.forceEnable);
		ImGui::Checkbox("FPS Overlay (top-right)", &s.fpsOverlay);

		// v0.25：DLSS-NR 菜单项已移除（NR 改由外部 ReShade 方案提供）

		ImGui::Separator();
		// v0.42：恢复 Provider 选项（DLSSG 4x MFG）——Provider 决定 swapchain 路径，
		// 运行时切换需重启游戏生效（重建 D3D12 proxy）。
		const char* providers[] = { "FSR3 (2x, all GPUs)", "DLSSG (NVIDIA, 4x MFG)" };
		// v0.52：Provider 只在 DX12SwapChain::CreateSwapChain 里被消费一次（决定 dlssgMode /
		// BufferCount / D3D12 proxy 路径），**运行中切换不会有任何即时变化**——这是结构性的，
		// 没有热切方案。所以要保证两点：① 改动立刻写回 INI（否则重启后读回旧值，表现就是
		// "切了跟没切一样"）；② 明确记录日志 + 界面提示需重启，不再让用户对着一个"没反应"
		// 的下拉框猜。
		if (ImGui::Combo("Frame Gen Provider", &s.provider, providers, 2)) {
			const bool saved = SaveSettingsToIni(a_fg);
			SKSE::log::info("[FrameGen] Provider -> {} ({}) | {} | RESTART REQUIRED (swapchain path is fixed at creation)",
				s.provider, s.provider == 1 ? "DLSSG" : "FSR3", saved ? "INI saved." : "INI SAVE FAILED.");
		}
		const bool providerPending = sc.providerAtCreate >= 0 && s.provider != sc.providerAtCreate;
		if (providerPending) {
			ImGui::TextColored(ImVec4(1.0f, 0.72f, 0.2f, 1.0f),
				"PENDING RESTART: running %s, INI wants %s - no effect until you relaunch the game",
				sc.providerAtCreate == 1 ? "DLSSG" : "FSR3", s.provider == 1 ? "DLSSG" : "FSR3");
		}
		if (s.provider == 0) {
			ImGui::Text("FrameGen: FSR3 tech (all GPUs)");
			ImGui::TextDisabled("Universal frame interpolation - works on NVIDIA & AMD");
		}

		// v0.52：DLSSG 参数不再藏在 provider==1 后面——在 FSR3 下也能先设好（否则"切了没反应"
		// 时根本无从判断到底改没改），改动立即持久化，不必再记得按 Save to INI。
		{
			// v0.50：2x..6x（1=2x 2=3x 3=4x 4=5x 5=6x）
			const char* mfgModes[] = { "2x", "3x", "4x", "5x", "6x" };
			int mfg = static_cast<int>(s.dlssgFramesToGenerate) - 1;
			if (mfg < 0) mfg = 0;
			if (mfg > 4) mfg = 4;
			if (ImGui::Combo("MFG Multiplier (DLSSG)", &mfg, mfgModes, IM_ARRAYSIZE(mfgModes))) {
				s.dlssgFramesToGenerate = static_cast<std::uint32_t>(mfg + 1);
				SaveSettingsToIni(a_fg);
				SKSE::log::info("[FrameGen] MFG multiplier -> {}x (DLSSGFramesToGenerate={})", mfg + 1, s.dlssgFramesToGenerate);
			}

			// v0.50：上限覆盖（老卡多倍帧生成解锁）。0=跟随硬件上报；1..5=抬到 N 个插帧。
			int ov = static_cast<int>(s.mfgMaxFramesOverride);
			if (ImGui::SliderInt("MFG Max Override", &ov, 0, 5,
				ov == 0 ? "Off (hardware max)" : "%d")) {
				s.mfgMaxFramesOverride = static_cast<std::uint32_t>(ov < 0 ? 0 : ov);
				SaveSettingsToIni(a_fg);
				SKSE::log::info("[FrameGen] MFG max override -> {} (1=2x ... 5=6x)", s.mfgMaxFramesOverride);
			}

			const char* archNote = s.mfgMaxFramesOverride > 0
				? "Override ON - raising this only changes what we REQUEST. The runtime still\nvalidates it and will reject >hwMax with eErrorInvalidState unless an external MFG\nkernel unlocker (DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge) is installed.\nCheck the log for 'MFG probe: runtime REJECTED' vs 'ACCEPTED'."
				: "RTX 50 does 4x natively. 40/30/20 need an external kernel unlocker.\nThe v0.51 ladder probe steps the request down to whatever the runtime accepts.";
			ImGui::TextDisabled("%s", archNote);
			if (s.provider == 0)
				ImGui::TextDisabled("These apply to DLSSG. You are on FSR3 now - the values are saved to the INI\nand take effect after you switch Provider and restart.");
			ImGui::TextDisabled("Provider change needs restart.");
		}

		// ---- DLSS5 Neural Rendering (NGX Feature 18) ----
		ImGui::Separator();
		ImGui::Text("DLSS5 Neural Rendering (NGX Feature 18)");
		bool nrOn = s.neuralRenderingEnabled;
		if (ImGui::Checkbox("Enable DLSS Neural Rendering", &nrOn)) {
			s.neuralRenderingEnabled = nrOn;
			// v0.42：DLSSNR 与 FG 串联（不再互斥）——DLSSNR 处理画面后 FG 在结果上插帧。
			// 若叠加闪烁再回退互斥。开 DLSSNR 不再自动关 FG。
			// v0.52：改动立即持久化；日志带上运行时真实状态与成功帧数——"切了到底有没有
			// 生效"以前完全看不出来（旧日志只记 enabled/disabled，无法证伪）。
			SaveSettingsToIni(a_fg);
			SKSE::log::info("[FrameGen] DLSSNR {} (GUI) | runtime status={} frames={}",
				nrOn ? "enabled" : "disabled",
				NeuralRendering::Renderer::Instance().StatusText(),
				static_cast<unsigned long long>(NeuralRendering::Renderer::Instance().SuccessfulFrames()));
		}
		if (s.neuralRenderingEnabled) {
			auto& t = a_fg.nrTuning;
			ImGui::SliderFloat("Intensity", &t.intensity, 0.0f, 2.0f, "%.2f");
			ImGui::SliderFloat("Local Tone", &t.localToneStrength, 0.0f, 2.0f, "%.2f");
			ImGui::SliderFloat("Local Structure", &t.localStructureStrength, 0.0f, 2.0f, "%.2f");
			ImGui::SliderFloat("Skin Structure", &t.skinStructureStrength, 0.0f, 2.0f, "%.2f");
			static const char* nrStyles[] = { "Style 0", "Style 1", "Style 2", "Style 3" };
			int style = static_cast<int>(t.style);
			if (ImGui::Combo("Style", &style, nrStyles, IM_ARRAYSIZE(nrStyles)))
				t.style = static_cast<std::uint32_t>(style);
			ImGui::Checkbox("Automatic Mask", &t.useAutoMask);
			ImGui::Checkbox("UI Correction", &t.uiCorrection);
			// v0.44：DLSSNR 输入分辨率缩放（性能优化）。低 = 快但细节少。
			if (ImGui::SliderFloat("DLSSNR Render Scale", &t.renderScale, 0.25f, 1.0f, "%.2f"))
				NeuralRendering::Renderer::Instance().ResetHistory();
			ImGui::TextDisabled("Lower = faster (fewer FP8 ops) but less detail. 0.75 = 1080p in.");
			ImGui::TextDisabled("Status: %s | frames: %llu",
				NeuralRendering::Renderer::Instance().StatusText(),
				static_cast<unsigned long long>(NeuralRendering::Renderer::Instance().SuccessfulFrames()));
		}

		// v0.41：自定义渲染分辨率缩放——引擎渲染分辨率 = 输出 × 比例，DLSS 放大回输出。
		// Auto=跟随 QualityMode 档位表（旧行为）；自定义 0.30-1.00 实时生效（下帧 kMAIN 重建）。
		// 默认 0.70（70% 渲染）：DLSS5/NR 场景下真超分空间 + 帧数大幅提升。
		ImGui::Separator();
		bool autoScale = s.renderResolutionScale <= 0.0f;
		if (ImGui::Checkbox("Auto Render Scale (follow Quality Mode)", &autoScale)) {
			s.renderResolutionScale = autoScale ? 0.0f : 0.70f;  // 切自定义默认 70%
			SKSE::log::info("[FrameGen] Render scale mode: {}", autoScale ? "Auto (Quality Mode)" : "Custom 0.70");
		}
		if (!autoScale) {
			if (ImGui::SliderFloat("Render Resolution Scale", &s.renderResolutionScale, 0.30f, 1.00f, "%.2f")) {
				const float ratio = std::clamp(s.renderResolutionScale, 0.30f, 1.00f);
				sc.renderScaleX = sc.renderScaleY = ratio;
				sc.renderWidth = static_cast<std::uint32_t>(
					std::max(1, static_cast<int>(sc.swapChainDesc.Width * ratio)));
				sc.renderHeight = static_cast<std::uint32_t>(
					std::max(1, static_cast<int>(sc.swapChainDesc.Height * ratio)));
				SKSE::log::info("[FrameGen] Render scale (GUI): {:.2f} -> {}x{}", ratio, sc.renderWidth, sc.renderHeight);
			}
			ImGui::TextDisabled("Engine render = output x scale; DLSS upscales back. 0.70 = 70%%.");
		}

		ImGui::Separator();
		ImGui::Text("FG active: %s", a_fg.fgActive.load() ? "ON" : "OFF");
		ImGui::Text("DLSS: %s  DLSSG: %s",
			a_fg.streamline.featureDLSS ? "OK" : "-",
			a_fg.streamline.featureDLSSG ? "OK" : "-");
		ImGui::Text("Refresh: %.0f Hz  |  %dx%d",
			a_fg.refreshRate, (int)a_fg.screenWidth, (int)a_fg.screenHeight);
		ImGui::Text("Keys: Hold Home = Menu | FG switch in GUI");

		if (ImGui::Button("Save to INI")) {
			// v0.52：改走统一写回函数（与自动保存同一份键表，不再漏键、不再静默失败）。
			const bool saved = SaveSettingsToIni(a_fg);
			if (saved)
				ImGui::TextColored(ImVec4(0.2f, 1.0f, 0.4f, 1.0f), "Saved (see log for result)");
			else
				ImGui::TextColored(ImVec4(1.0f, 0.3f, 0.3f, 1.0f), "Save FAILED - see log");
		}

		ImGui::End();
	}
}
