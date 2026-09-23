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
#include <string>

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
			// v1.46：菜单 UI 字体必须能渲染中文。
			//
			// 此前这里用的是 fio.Fonts->AddFontDefault()，而 ImGui 的内置字体
			// (ProggyClean) 只有拉丁字形 —— 菜单里写中文会全部变成空白/方块。
			// 本工程的其它 SKSE 插件同样走 "C:\\Windows\\Fonts\\*.ttf" 这条路
			// （上面的 arialbd.ttf 就是），所以中文也照此办理。
			//
			// 字体选择顺序（simhei.ttf 是单一 TTF；msyh.ttc 是 TTC 集合，ImGui 需要
			// 额外的 FontNo 处理，所以优先用前者）：
			//   simhei.ttf → msyh.ttc → 内置默认（此时中文会显示为方块，但至少不崩）
			//
			// 字形范围用 GetGlyphRangesChineseSimplifiedCommon()（约 2500 常用汉字 +
			// 标点），够覆盖菜单全部文案；不用 GetGlyphRangesChineseFull()——
			// 那会把几万个字形全烘进图集，显存与初始化时间都要涨一个量级。
			ImFont* ui = nullptr;
			{
				ImFontConfig ucfg;
				ucfg.OversampleH = 1;   // 中文点阵下 2x 过采样收益低、图集大 4 倍
				ucfg.OversampleV = 1;
				ucfg.PixelSnapH = true;
				ui = fio.Fonts->AddFontFromFileTTF("C:\\Windows\\Fonts\\simhei.ttf", 16.0f,
					&ucfg, fio.Fonts->GetGlyphRangesChineseSimplifiedCommon());
				if (!ui)
					ui = fio.Fonts->AddFontFromFileTTF("C:\\Windows\\Fonts\\msyh.ttc", 16.0f,
						&ucfg, fio.Fonts->GetGlyphRangesChineseSimplifiedCommon());
			}
			if (ui) {
				fio.FontDefault = ui;
				SKSE::log::info("[ImguiMenu] CJK-capable UI font loaded (bilingual menu available)");
			} else {
				ui = fio.Fonts->AddFontDefault();
				if (ui)
					fio.FontDefault = ui;
				SKSE::log::warn("[ImguiMenu] no CJK font found (simhei.ttf / msyh.ttc missing) - "
					"menu falls back to the built-in font and Chinese text will show as blank boxes");
			}
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
		// v1.35 —— 画到「真正会上屏」的那个表面。菜单和 FPS overlay 走同一条绘制路径、
		// 同一个目标，所以目标一选错，两者一起消失（22:20 局的「按不出菜单」与
		// FpsOverlay=1 却看不见数字，是同一件事）。
		//   DLSS-G（Provider=1）：上屏源是 swapChainBufferWrapped ——
		//     DX12SwapChain.cpp:1985 把它交给 DLSS-G 当 color in，:2052 的 T2 直通拷贝
		//     也从它拷进后缓冲；而 :1984 之后的分支在 :2160 就 return 了，:2171 那条
		//     colorOut→后缓冲 的拷贝根本不会执行。所以 v0.7.17 的「优先 colorOut」在
		//     DLSS-G 下等于把菜单画进一个死表面：Home 长按生效（PollHomeKey 每帧都在
		//     跑、Toggle 被调用），画面却一动不动。
		//   FSR3（Provider=0）：上屏源就是 colorOutWrapped（:2172 那条拷贝的源），
		//     维持 v0.7.17 的行为不变。
		auto* rtWrapped = sc.dlssgMode
			? (sc.swapChainBufferWrapped ? sc.swapChainBufferWrapped : sc.colorOutWrapped)
			: (sc.colorOutWrapped ? sc.colorOutWrapped : sc.swapChainBufferWrapped);
		if (!rtWrapped || !rtWrapped->rtv)
			return;
		// 自证：把「这一帧画去了哪里」写进日志，下一次不必再靠推断（每 300 帧一条）。
		static int s_rtDiag = 0;
		if ((++s_rtDiag % 300) == 1)
			SKSE::log::info("[ImguiMenu] draw target = {} (dlssgMode={} rtv={} menu={} fps={})",
				rtWrapped == sc.colorOutWrapped ? "colorOutWrapped" : "swapChainBufferWrapped",
				sc.dlssgMode ? 1 : 0, rtWrapped->rtv != nullptr ? 1 : 0,
				wantMenu ? 1 : 0, wantFps ? 1 : 0);

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

		// v1.25: keep the two factors visible. `mult` is the runtime's REPORT of how
		// many frames it presented for the last real frame (slDLSSGGetState) and
		// s_fps is the real present rate measured right here, so the product is an
		// inference, not a measurement. On the 01:56 run the read-out jumped from
		// ~50 to ~150 at world entry while an independent reader in the same process
		// (Transfusion's [PERF], 300-frame window) measured 49.3 FPS. Printing the
		// product alone is what makes "4x" look like an observation.
		char buf[64];
		if (mult > 1.0f)
			std::snprintf(buf, sizeof(buf), "%.0f FPS  [%.0f real x%.0f reported]",
				s_fps * mult, s_fps, mult);
		else
			std::snprintf(buf, sizeof(buf), "%.0f FPS%s", s_fps * mult, tag);

		// v1.27 -- how long 4x has actually been running this visit.
		//
		// Five consecutive runs ended 2.1 / 3.0 / 3.2 / 2.5 / 6.1 s after the guard
		// released, so the one question every instrument in this project exists to
		// answer -- does the world respond, and does the picture advance -- has never
		// had a world phase long enough to answer it. The player does not read the log
		// and cannot be blamed for exiting early; they can read the overlay.
		//
		// mult > 1 is MEASURED: it is what the runtime reported for the last real
		// frame, so its rising edge means "4x is running now" and not another name
		// for "the menu guard is up". It is also the only edge in this overlay that
		// comes from the runtime rather than from us.
		static bool s_worldSeen = false;
		static steady_clock::time_point s_worldSince{};
		// v1.28 -- the clock drawn below was never logged, so 'did the overlay
		// actually appear' could not be answered from any artefact. The 03:17 run
		// released the menu guard at 03:17:24.708 and the player still never pressed
		// a movement key (os=0x0 on all 20 [CAM] PC samples), so before the protocol
		// can be blamed the overlay itself has to be visible in the log. Three edges
		// only: this function runs every frame and must not write a line per frame.
		static bool s_worldLogged20 = false;
		if (mult > 1.0f) {
			if (!s_worldSeen) {
				s_worldSeen = true;
				s_worldSince = now;
				s_worldLogged20 = false;
				SKSE::log::info("[OVERLAY] world clock started - the runtime just reported "
					"mult={:.1f} for the last real frame, so 4x is running now. The second "
					"overlay line reads 'KEEP PLAYING, hold W for 10 s'.",
					static_cast<double>(mult));
			} else {
				const double s =
					duration_cast<duration<double>>(now - s_worldSince).count();
				if (!s_worldLogged20 && s >= 20.0) {
					s_worldLogged20 = true;
					SKSE::log::info("[OVERLAY] world clock reached {:.1f} s - the second overlay "
						"line now reads 'enough - you can exit now'. This is the point the run "
						"becomes usable.", s);
				}
			}
		} else {
			s_worldSeen = false;
		}
		char buf2[80];
		buf2[0] = '\0';
		if (s_worldSeen) {
			const double secs =
				duration_cast<duration<double>>(now - s_worldSince).count();
			std::snprintf(buf2, sizeof(buf2), "%.1f s with 4x - %s", secs,
				(secs < 20.0) ? "KEEP PLAYING, hold W for 10 s"
				              : "enough - you can exit now");
		}

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

		// v1.27: the world-phase clock, same outline treatment, smaller and amber so
		// it cannot be mistaken for the frame-rate line above it.
		if (buf2[0] != '\0') {
			const float size2 = size * 0.55f;
			const ImVec2 ts2 = font->CalcTextSizeA(size2, FLT_MAX, 0.0f, buf2);
			const ImVec2 pos2(disp.x - ts2.x - 26.0f, pos.y + ts.y + 8.0f);
			for (int dx = -2; dx <= 2; ++dx)
				for (int dy = -2; dy <= 2; ++dy)
					if (dx * dx + dy * dy <= 8)
						dl->AddText(font, size2, ImVec2(pos2.x + dx, pos2.y + dy),
							IM_COL32(0, 0, 0, 235), buf2);
			dl->AddText(font, size2, pos2, IM_COL32(255, 220, 110, 255), buf2);
		}
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
			// v1.21: this key is READ by LoadConfig and was never WRITTEN here, so
			// one press of Save silently reverted NR to "mutually exclusive with
			// frame generation" on the next launch -- and rewrote the 14,559 B
			// commented template as 517 B. Every key LoadConfig understands has to
			// come out of this function, or the menu is a settings shredder.
			<< "NRAllowWithFrameGen=" << (s.nrAllowWithFrameGen ? 1 : 0) << "\n"
			<< "NRIntensity=" << a_fg.nrTuning.intensity << "\n"
			<< "NRLocalTone=" << a_fg.nrTuning.localToneStrength << "\n"
			<< "NRLocalStructure=" << a_fg.nrTuning.localStructureStrength << "\n"
			<< "NRSkinStructure=" << a_fg.nrTuning.skinStructureStrength << "\n"
			<< "NRStyle=" << a_fg.nrTuning.style << "\n"
			<< "NRAutoMask=" << (a_fg.nrTuning.useAutoMask ? 1 : 0) << "\n"
			<< "NRUICorrection=" << (a_fg.nrTuning.uiCorrection ? 1 : 0) << "\n"
			<< "NRRenderScale=" << std::fixed << std::setprecision(2) << a_fg.nrTuning.renderScale << "\n"
			// v1.45：多层神经渲染层数（整数，不受上面的 fixed/setprecision 影响）
			<< "NRLayers=" << a_fg.nrTuning.layers << "\n"
			<< "FpsOverlay=" << (s.fpsOverlay ? 1 : 0) << "\n"
			<< "QualityMode=" << s.qualityMode << "\n"
			<< "PresetDLSS=" << s.presetDLSS << "\n"
			<< "DLSSGFramesToGenerate=" << s.dlssgFramesToGenerate << "\n"
			<< "MFGMaxFramesOverride=" << s.mfgMaxFramesOverride << "\n"
			// v1.46：MFG 倍率持久化开关（是否允许写第三方 Transfusion json）
			<< "WriteTransfusionConfig=" << s.writeTransfusionConfig << "\n"
			<< "ReflexFpsLimit=" << s.reflexFpsLimit << "\n"
			<< "MenuDisableFrameGen=" << (s.menuDisableFrameGen ? 1 : 0) << "\n"
			<< "InteropFenceWait=" << (s.interopFenceWait ? 1 : 0) << "\n"
			<< "FenceWaitBusy=" << (s.fenceWaitBusy ? 1 : 0) << "\n"
			<< "MenuGuardFader=" << (s.menuGuardFader ? 1 : 0) << "\n"
			<< "PixelProbe=" << (s.pixelProbe ? 1 : 0) << "\n"
			<< "ForceBackBufferCopy=" << (s.forceBackBufferCopy ? 1 : 0) << "\n"
			<< "Sharpness=" << s.sharpness << "\n"
			<< "RenderResolutionScale=" << std::fixed << std::setprecision(2) << s.renderResolutionScale << "\n"
			<< "MvecScaleOverride=" << std::fixed << std::setprecision(2) << s.mvecScaleOverride << "\n"
			<< "StreamlineLogLevel=" << s.streamlineLogLevel << "\n"
			<< "ToggleKey=0x" << std::hex << s.toggleKey << std::dec << "\n";
		ini.close();
		SKSE::log::info("[FrameGen] INI saved: Provider={} DLSSGFramesToGenerate={} MFGMaxFramesOverride={} NR={} NRLayers={}",
			s.provider, s.dlssgFramesToGenerate, s.mfgMaxFramesOverride, s.neuralRenderingEnabled ? 1 : 0,
			a_fg.nrTuning.layers);
		return true;
	}

	// ============================================================================
	// v1.46：把 MFG 倍率写进第三方 mod (DLSSG-Transfusion) 的 json。
	//
	// 为什么需要它（全部实测取证，见账本 §84.25 / §84.28）：
	//   本插件的 DLSSGFramesToGenerate 只被本插件自己读。实际上屏倍率由注入型 mod
	//   DLSSG-Transfusion 决定 —— 它在启动时读一次游戏根目录的 DLSSG-Transfusion.json，
	//   然后钩住 slDLSSGSetOptions / slDLSSGGetState，在渲染线程持续 reapply，覆盖
	//   本插件发出的任何请求。实测四把尺子（本插件 FLIPS / Transfusion [PERF] /
	//   actual presentation count / perf.csv 的 Multiplier 列）在 GUI 请求 2x/6x/3x 时
	//   全部读数恒为 4 —— 就是"菜单改了、日志也打 INI saved、重启后依然是 4x"的成因。
	//
	// 所以"菜单改 -> 重启 -> 生效"只有一条路：写那份 json。但它属于另一个作者，因此：
	//   ① 默认不写（settings.writeTransfusionConfig == 0），必须用户在菜单里显式勾选；
	//   ② 每次写前备份成 *.bak-mult<N>-<时间戳>（沿用本工程既有备份命名）；
	//   ③ 只替换 multiplier 那一个键的值，**其余键逐字保留原样**（含顺序与缩进）。
	//
	// 实现上刻意不做通用 JSON 解析：dlssg 只认 "multiplier": <N>, 这一行，而一个
	// 完整的 JSON 序列化器会把用户手写的注释/顺序全部重排，反而更容易出事。这里做
	// 的是逐行文本替换，改完的行数与其余字节与原文完全一致。
	//
	// 路径解析：游戏根目录 = 进程 CWD。**不能**用 GetModuleFileName 推 —— MO2 的 VFS
	// 会让它返回 D:\...\data\SKSE\Plugins\... 这种实盘不存在的假路径（已实测）。
	// CWD 才是可靠来源：本插件读 INI 用的也是相对路径 "Data/SKSE/Plugins/..."，
	// 而日志里 cwd=D:\ENB-EJ\Skyrim Special Edition 且 INI MISSING 计数为 0 —— 双证。
	namespace
	{
		// v1.46：读 Transfusion json 当前的 multiplier（只读，不写）。
		// 返回 0 = 找不到文件 / 读不出 —— 菜单据此显示"本机没装 Transfusion"而不是报错。
		std::uint32_t ReadTransfusionMultiplier()
		{
			char cwd[MAX_PATH] = {};
			if (!::GetCurrentDirectoryA(MAX_PATH, cwd))
				return 0;
			const std::string jsonPath = std::string(cwd) + "\\DLSSG-Transfusion.json";
			std::ifstream in(jsonPath, std::ios::binary);
			if (!in)
				return 0;
			std::string body((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
			in.close();

			const auto pos = body.find("\"multiplier\"");
			if (pos == std::string::npos)
				return 0;
			const auto colon = body.find(':', pos);
			if (colon == std::string::npos)
				return 0;
			// 冒号后跳过空白（含 CRLF —— 与写入侧用同一套跳过字符集，保持一致）
			std::size_t i = colon + 1;
			while (i < body.size() && (body[i] == ' ' || body[i] == '\t' || body[i] == '\r' || body[i] == '\n'))
				++i;
			std::uint32_t val = 0;
			bool any = false;
			while (i < body.size() && body[i] >= '0' && body[i] <= '9') {
				val = val * 10u + static_cast<std::uint32_t>(body[i] - '0');
				any = true;
				++i;
			}
			return any ? val : 0;
		}

		// 只替换 "multiplier": <数字>, 这一行。返回 true = 文件已改写。
		bool WriteTransfusionMultiplier(std::uint32_t a_mult)
		{
			char cwd[MAX_PATH] = {};
			if (!::GetCurrentDirectoryA(MAX_PATH, cwd)) {
				SKSE::log::error("[MFGPersist] GetCurrentDirectory failed (err={})", ::GetLastError());
				return false;
			}
			const std::string dir(cwd);
			const std::string jsonPath = dir + "\\DLSSG-Transfusion.json";

			// 1) 读原文（二进制读，保住原有行尾；该文件实测是 LF + 末尾有换行）
			std::ifstream in(jsonPath, std::ios::binary);
			if (!in) {
				SKSE::log::warn("[MFGPersist] no {} - Transfusion not installed here, "
				"skipping (this is not an error)", jsonPath);
				return false;
			}
			std::string body((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
			in.close();

			// 2) 逐行找到 multiplier 并替换其值
			const std::string needle = "\"multiplier\"";
			const auto pos = body.find(needle);
			if (pos == std::string::npos) {
				SKSE::log::error("[MFGPersist] {} has no \"multiplier\" key - refusing to "
					"rewrite a file we do not understand", jsonPath);
				return false;
			}
			// 最小侵入：只替换「冒号之后的空白 + 数字」这一段，不整行替换。
			//
			// 起初写的是「取整行再重建」，被构建前预演脚本
			// (tools/_rehearse_transfusion_write.py) 抓到 2 个真 bug：
			//   ① 单行 json（{"multiplier":2,"mode":...}）没有前导 '\n'，整行思路会把
			//      后面所有键一起吃掉；
			//   ② CRLF 文件里 '\n' 前的 '\r' 会残留成孤立字节。
			// 改成只动数字区间后，这两种形态天然正确 —— 因为缩进、逗号、行尾全都在
			// 数字区间之外，一个字节都不碰。
			const auto colon = body.find(':', pos);
			if (colon == std::string::npos) {
				SKSE::log::error("[MFGPersist] {} has \"multiplier\" but no ':' - refusing to "
					"rewrite a file we do not understand", jsonPath);
				return false;
			}
			std::size_t vs = colon + 1;   // 数字起始（先跳过空白）
			while (vs < body.size() && (body[vs] == ' ' || body[vs] == '\t' || body[vs] == '\r' || body[vs] == '\n'))
				++vs;
			// 这里必须真的是数字，否则不认（宁可不动，也不要写坏别人的文件）
			if (vs >= body.size() || body[vs] < '0' || body[vs] > '9') {
				SKSE::log::error("[MFGPersist] {} \"multiplier\" value is not a number - refusing to "
					"rewrite it", jsonPath);
				return false;
			}
			std::size_t ve = vs;
			while (ve < body.size() && body[ve] >= '0' && body[ve] <= '9')
				++ve;
			const std::string oldNum = body.substr(vs, ve - vs);
			const std::string newNum = std::to_string(a_mult);

			if (oldNum == newNum) {
				SKSE::log::info("[MFGPersist] {} already multiplier={}x - nothing to do", jsonPath, a_mult);
				return true;
			}

			// 3) 先备份（带倍率与时间戳，便于肉眼回退）
			SYSTEMTIME st{};
			::GetLocalTime(&st);
			char stamp[64] = {};
			std::snprintf(stamp, sizeof(stamp), "%04d%02d%02d-%02d%02d%02d",
				st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
			char bakPath[MAX_PATH] = {};
			std::snprintf(bakPath, sizeof(bakPath), "%s.bak-mult%u-%s", jsonPath.c_str(), a_mult, stamp);
			{
				std::ofstream bak(bakPath, std::ios::binary);
				if (!bak) {
					SKSE::log::error("[MFGPersist] cannot create backup {} - ABORTING so the "
				"original stays intact", bakPath);
					return false;
				}
				bak.write(body.data(), static_cast<std::streamsize>(body.size()));
				bak.close();
			}

			// 4) 原子写：先写 .tmp，成功后再 rename 覆盖。
			//    直接截断重写的话，进程若在两次写之间死掉，用户会剩下半个 json —— 而
			//    Transfusion 读不动它就 fail-closed 退回原生 2x（它自己的设计）。
			//    拼接只换 [vs, ve) 这段数字，前后所有字节（含缩进、逗号、CRLF）原样保留。
			std::string newBody = body.substr(0, vs) + newNum + body.substr(ve);
			const std::string tmpPath = jsonPath + ".tmp";
			{
				std::ofstream out(tmpPath, std::ios::binary | std::ios::trunc);
				if (!out) {
					SKSE::log::error("[MFGPersist] cannot open {} for writing", tmpPath);
					return false;
				}
				out.write(newBody.data(), static_cast<std::streamsize>(newBody.size()));
				out.close();
			}
			// MoveFileEx 是原子替换；失败则清掉 .tmp 并保留原文件
			if (!::MoveFileExA(tmpPath.c_str(), jsonPath.c_str(),
					MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
				SKSE::log::error("[MFGPersist] MoveFileEx failed (err={}) - original json left "
				"untouched", ::GetLastError());
				::DeleteFileA(tmpPath.c_str());
				return false;
			}

			SKSE::log::info("[MFGPersist] Transfusion json updated: {} -> multiplier={}x | backup={} | {}B -> {}B",
				jsonPath, a_mult, bakPath,
				static_cast<unsigned long long>(body.size()),
				static_cast<unsigned long long>(newBody.size()));
			return true;
		}
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
		ImGui::TextWrapped("帧生成 + DLSS5 神经渲染（可实时调整）");
		ImGui::TextWrapped("Frame Generation + DLSS5 Neural Rendering (live adjust)");
		ImGui::TextDisabled("注意：DLSS 超分已在 v0.48 移除，菜单里没有超分开关。");
		ImGui::TextDisabled("NOTE: DLSS upscaling was removed in v0.48 - there is no DLSS upscale switch.");
		ImGui::Separator();

		ImGui::Checkbox("总开关  |  Enable (master)", &s.enableFrameGen);
		// v0.7.7：FG 开关直接绑定运行时 fgActive——GUI 里点即生效，不再用 Home 短按
		bool fgOn = a_fg.fgActive.load();
		if (ImGui::Checkbox("帧生成 FG  |  Frame Generation (FG)", &fgOn)) {
			a_fg.fgActive.store(fgOn);
			SKSE::log::info("[FrameGen] Frame generation {} (GUI)", fgOn ? "ENABLED" : "DISABLED");
		}
		ImGui::Checkbox("强制启用（<120Hz）  |  Force Enable (<120Hz)", &s.forceEnable);
		ImGui::Checkbox("帧数显示（右上角）  |  FPS Overlay (top-right)", &s.fpsOverlay);

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
		if (ImGui::Combo("帧生成后端  |  Frame Gen Provider", &s.provider, providers, 2)) {
			const bool saved = SaveSettingsToIni(a_fg);
			SKSE::log::info("[FrameGen] Provider -> {} ({}) | {} | RESTART REQUIRED (swapchain path is fixed at creation)",
				s.provider, s.provider == 1 ? "DLSSG" : "FSR3", saved ? "INI saved." : "INI SAVE FAILED.");
		}
		const bool providerPending = sc.providerAtCreate >= 0 && s.provider != sc.providerAtCreate;
		if (providerPending) {
			ImGui::TextColored(ImVec4(1.0f, 0.72f, 0.2f, 1.0f),
				"待重启：当前运行 %s，INI 已改为 %s —— 不重启游戏不会生效",
				sc.providerAtCreate == 1 ? "DLSSG" : "FSR3", s.provider == 1 ? "DLSSG" : "FSR3");
			ImGui::TextColored(ImVec4(1.0f, 0.72f, 0.2f, 1.0f),
				"PENDING RESTART: running %s, INI wants %s - no effect until you relaunch the game",
				sc.providerAtCreate == 1 ? "DLSSG" : "FSR3", s.provider == 1 ? "DLSSG" : "FSR3");
		}
		if (s.provider == 0) {
			ImGui::Text("帧生成后端：FSR3（所有显卡可用）");
			ImGui::Text("FrameGen: FSR3 tech (all GPUs)");
			ImGui::TextDisabled("通用插帧，NVIDIA 与 AMD 都能用");
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
			if (ImGui::Combo("倍率（多倍帧生成）  |  MFG Multiplier (DLSSG)", &mfg, mfgModes, IM_ARRAYSIZE(mfgModes))) {
				s.dlssgFramesToGenerate = static_cast<std::uint32_t>(mfg + 1);
				SaveSettingsToIni(a_fg);
				SKSE::log::info("[FrameGen] MFG multiplier -> {}x (DLSSGFramesToGenerate={})", s.dlssgFramesToGenerate + 1, s.dlssgFramesToGenerate);
				// v1.46：写自己的 INI 只让本插件知道。真正决定上屏倍率的是 Transfusion 的
				// json —— 没勾开关时这里必须留一条日志，否则用户又会遇到"改了、日志也打了、
				// 重启后还是老倍率"（§84.25 的原始症状）。判据在 check_transfusion_mult.py。
				if (s.writeTransfusionConfig) {
					if (WriteTransfusionMultiplier(s.dlssgFramesToGenerate + 1))
						SKSE::log::info("[FrameGen] MFG {}x queued for next launch (Transfusion json written; restart required)",
							s.dlssgFramesToGenerate + 1);
					else
						SKSE::log::warn("[FrameGen] MFG {}x saved to own INI, but writing the Transfusion json FAILED "
							"- next launch will keep the json's value", s.dlssgFramesToGenerate + 1);
				} else {
					SKSE::log::info("[FrameGen] MFG {}x saved to own INI only. Effective multiplier is decided by "
						"DLSSG-Transfusion's json - tick 'Write to Transfusion config' to persist it there, "
						"or use the in-game hotkeys Ctrl+Alt+2..6 for an immediate change.",
						s.dlssgFramesToGenerate + 1);
				}
			}

			// v1.46：MFG 倍率持久化开关。默认关（不动第三方作者的文件）；勾上后 Combo 的每次
			// 改动都会同步写进游戏根目录的 DLSSG-Transfusion.json（写前自动备份）。
			// v1.46：勾选框 + 三态读数的文案全部改为「中文在前 / 英文在后」双语。
			// 中文用 ImGui 能渲染的简体（字体见 Init 里的 CJK 加载），英文保留原样，
			// 便于与日志、账本、N 网描述逐字对照。
			{
				bool wt = s.writeTransfusionConfig != 0;
				if (ImGui::Checkbox("写入 DLSSG-Transfusion.json（需重启）"
						"  |  Write to DLSSG-Transfusion.json (restart required)", &wt)) {
					s.writeTransfusionConfig = wt ? 1u : 0u;
					SaveSettingsToIni(a_fg);
					SKSE::log::info("[FrameGen] WriteTransfusionConfig -> {}", wt ? 1 : 0);
					// 勾上的瞬间就把当前倍率补写一次，省得用户还要再动一下 Combo
					if (wt) {
						if (WriteTransfusionMultiplier(s.dlssgFramesToGenerate + 1))
							SKSE::log::info("[FrameGen] MFG {}x pushed to Transfusion json now (restart required)",
								s.dlssgFramesToGenerate + 1);
					}
				}
				ImGui::TextDisabled("本插件 INI 永远会存这个值。游戏启动时真正读的是那个 json ——\n"
					"它属于 DLSSG-Transfusion，所以只有你勾选后我们才会去动它。\n"
					"每次写入之前都会自动备份。");
				ImGui::TextDisabled("Own INI always stores this. The json is what the game actually reads at "
					"launch - it belongs to DLSSG-Transfusion, so we only touch it when you tick this. "
					"Backed up automatically before every write.");
			}

			// v0.50：上限覆盖（老卡多倍帧生成解锁）。0=跟随硬件上报；1..5=抬到 N 个插帧。
			int ov = static_cast<int>(s.mfgMaxFramesOverride);
			if (ImGui::SliderInt("上限覆盖  |  MFG Max Override", &ov, 0, 5,
				ov == 0 ? "关（跟随硬件上限）  |  Off (hardware max)" : "%d")) {
				s.mfgMaxFramesOverride = static_cast<std::uint32_t>(ov < 0 ? 0 : ov);
				SaveSettingsToIni(a_fg);
				SKSE::log::info("[FrameGen] MFG max override -> {} (1=2x ... 5=6x)", s.mfgMaxFramesOverride);
			}

			const char* archNote = s.mfgMaxFramesOverride > 0
				? "覆盖已开 —— 抬高它只改变我们【请求】多少倍。运行时仍会校验，超出硬件上限\n"
				  "时会以 eErrorInvalidState 拒绝，除非装了外部 MFG 内核解锁器\n"
				  "（DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge）。日志里搜\n"
				  "'MFG probe: runtime REJECTED' 与 'ACCEPTED' 可分辨。\n"
				  "  Override ON - raising this only changes what we REQUEST. The runtime still\n"
				  "  validates it and will reject >hwMax with eErrorInvalidState unless an external MFG\n"
				  "  kernel unlocker (DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge) is installed.\n"
				  "  Check the log for 'MFG probe: runtime REJECTED' vs 'ACCEPTED'."
				: "RTX 50 原生 4x；40/30/20 需要外部内核解锁器。\n"
				  "v0.51 的阶梯探针会把请求逐级降到运行时可接受的值。\n"
				  "  RTX 50 does 4x natively. 40/30/20 need an external kernel unlocker.\n"
				  "  The v0.51 ladder probe steps the request down to whatever the runtime accepts.";
			ImGui::TextDisabled("%s", archNote);
			if (s.provider == 0)
		ImGui::TextDisabled("以上参数只作用于 DLSSG。你现在是 FSR3 —— 值还是会存进 INI，\n"
			"切到 DLSSG 并重启后才生效。");
		ImGui::TextDisabled("These apply to DLSSG. You are on FSR3 now - the values are saved to the INI\nand take effect after you switch Provider and restart.");
		ImGui::TextDisabled("更换后端需要重启游戏。");
		ImGui::TextDisabled("Provider change needs restart.");

			// v1.46：倍率三态读数。以前这里只有"请求值"，用户没法分辨"菜单改了 / 存了 /
			// 实际生效"三件事 —— 这正是"改了没明显感觉"的根源。三个数分别来自：
			//   INI      = 本插件自己的持久化值（重启后本插件用它发请求）
			//   json     = 游戏启动时 Transfusion 真正读的那个值（唯一决定上屏倍率）
			//   session  = 本局实测（Transfusion 的 actual presentation count，没有则显示请求值）
			// json 不启用/不存在时不算错——只说明这台机器没装 Transfusion。
			{
				const std::uint32_t ownMult = s.dlssgFramesToGenerate + 1;
				const std::uint32_t jsonMult = ReadTransfusionMultiplier();
				ImGui::Separator();
				if (jsonMult > 0) {
					const bool mismatch = jsonMult != ownMult;
					ImGui::TextColored(mismatch ? ImVec4(1.0f, 0.72f, 0.2f, 1.0f)
							: ImVec4(0.45f, 0.85f, 0.5f, 1.0f),
						"倍率：本插件 INI %ux ｜ json %ux%s",
						ownMult, jsonMult,
						mismatch ? "  ← 启动时 json 说了算" : "  （一致）");
					if (mismatch && !s.writeTransfusionConfig)
						ImGui::TextDisabled("每次启动真正生效的是 json 里的值。勾上上面的方框让菜单来写它，\n"
							"或者自己手动编辑那个文件。");
				} else {
					ImGui::TextDisabled("倍率：本插件 INI %ux ｜ 没找到 DLSSG-Transfusion.json —— 该 json 是游戏\n"
						"启动时唯一读取的来源，所以本机上没有别的东西能覆盖它。",
						ownMult);
					ImGui::TextDisabled("   (no DLSSG-Transfusion.json found - nothing else can override the multiplier here)");
				}
				// 英文原句保留成一行，便于与日志/账本逐字对照
				ImGui::TextDisabled("   (INI = this plugin's own value | json = what the game reads at launch)");
			}
		}

		// ---- DLSS5 Neural Rendering (NGX Feature 18) ----
		ImGui::Separator();
		ImGui::Text("DLSS5 神经渲染（NGX Feature 18）");
		ImGui::Text("DLSS5 Neural Rendering (NGX Feature 18)");
		bool nrOn = s.neuralRenderingEnabled;
		if (ImGui::Checkbox("启用 DLSS 神经渲染  |  Enable DLSS Neural Rendering", &nrOn)) {
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
			ImGui::SliderFloat("强度  |  Intensity", &t.intensity, 0.0f, 2.0f, "%.2f");
			ImGui::SliderFloat("局部色调  |  Local Tone", &t.localToneStrength, 0.0f, 2.0f, "%.2f");
			ImGui::SliderFloat("局部结构  |  Local Structure", &t.localStructureStrength, 0.0f, 2.0f, "%.2f");
			ImGui::SliderFloat("皮肤结构  |  Skin Structure", &t.skinStructureStrength, 0.0f, 2.0f, "%.2f");
			static const char* nrStyles[] = { "Style 0", "Style 1", "Style 2", "Style 3" };
			int style = static_cast<int>(t.style);
			if (ImGui::Combo("风格  |  Style", &style, nrStyles, IM_ARRAYSIZE(nrStyles)))
				t.style = static_cast<std::uint32_t>(style);
			ImGui::Checkbox("自动遮罩  |  Automatic Mask", &t.useAutoMask);
			ImGui::Checkbox("UI 校正  |  UI Correction", &t.uiCorrection);
			// v0.44：DLSSNR 输入分辨率缩放（性能优化）。低 = 快但细节少。
			if (ImGui::SliderFloat("神经渲染分辨率缩放  |  DLSSNR Render Scale", &t.renderScale, 0.25f, 1.0f, "%.2f"))
				NeuralRendering::Renderer::Instance().ResetHistory();
			ImGui::TextDisabled("越低越快（FP8 运算更少）但细节更少。0.75 ≈ 输入 1080p。");
			ImGui::TextDisabled("Lower = faster (fewer FP8 ops) but less detail. 0.75 = 1080p in.");
			// v1.45：多层神经渲染 —— 同一帧内把神经渲染串联 N 遍。每层是一个独立的
			// NGX Feature 18 实例（各持有自己的时域历史），所以成本与显存都按 N 倍计。
			// 改层数时顺手复位历史：新层首帧本来就会带 Reset=1，复位让所有层同步重新起算。
			int nrLayers = static_cast<int>(t.layers);
			if (ImGui::SliderInt("神经渲染层数  |  DLSS5 Layers", &nrLayers, 1, static_cast<int>(NeuralRendering::kMaxNRLayers))) {
				t.layers = static_cast<std::uint32_t>(nrLayers);
				NeuralRendering::Renderer::Instance().ResetHistory();
				SaveSettingsToIni(a_fg);
				SKSE::log::info("[FrameGen] DLSSNR layers -> {} (GUI) | each layer is one more "
					"Feature 18 evaluate, cost scales with the count", t.layers);
			}
			ImGui::TextDisabled("每个真实帧叠加 N 遍神经渲染。1 = 关闭。不是免费的：成本 ≈ N × 单次 evaluate。");
			ImGui::TextDisabled("Stacked neural passes per real frame. 1 = off. Not free: N x evaluate cost.");
			ImGui::TextDisabled("状态  Status: %s | frames: %llu",
				NeuralRendering::Renderer::Instance().StatusText(),
				static_cast<unsigned long long>(NeuralRendering::Renderer::Instance().SuccessfulFrames()));
		}

		// v0.41：自定义渲染分辨率缩放——引擎渲染分辨率 = 输出 × 比例，DLSS 放大回输出。
		// Auto=跟随 QualityMode 档位表（旧行为）；自定义 0.30-1.00 实时生效（下帧 kMAIN 重建）。
		// 默认 0.70（70% 渲染）：DLSS5/NR 场景下真超分空间 + 帧数大幅提升。
		ImGui::Separator();
		bool autoScale = s.renderResolutionScale <= 0.0f;
		if (ImGui::Checkbox("自动渲染缩放（跟随画质档位）  |  Auto Render Scale (follow Quality Mode)", &autoScale)) {
			s.renderResolutionScale = autoScale ? 0.0f : 0.70f;  // 切自定义默认 70%
			SKSE::log::info("[FrameGen] Render scale mode: {}", autoScale ? "Auto (Quality Mode)" : "Custom 0.70");
		}
		if (!autoScale) {
			if (ImGui::SliderFloat("渲染分辨率缩放  |  Render Resolution Scale", &s.renderResolutionScale, 0.30f, 1.00f, "%.2f")) {
				const float ratio = std::clamp(s.renderResolutionScale, 0.30f, 1.00f);
				sc.renderScaleX = sc.renderScaleY = ratio;
				sc.renderWidth = static_cast<std::uint32_t>(
					std::max(1, static_cast<int>(sc.swapChainDesc.Width * ratio)));
				sc.renderHeight = static_cast<std::uint32_t>(
					std::max(1, static_cast<int>(sc.swapChainDesc.Height * ratio)));
				SKSE::log::info("[FrameGen] Render scale (GUI): {:.2f} -> {}x{}", ratio, sc.renderWidth, sc.renderHeight);
			}
			ImGui::TextDisabled("引擎渲染分辨率 = 输出 × 比例，再由 DLSS 放大回输出。0.70 = 70%%。");
			ImGui::TextDisabled("Engine render = output x scale; DLSS upscales back. 0.70 = 70%%.");
		}

		// v1.44：帧尾栅栏等待放在哪条时间线上——每帧实时生效，不需要重启。
		// 关（0）= 等待排进 D3D11 队列，CPU 立刻返回，于是下一帧能在 GPU 还在跑本帧
		// 时就开始准备（Sep 11 版行为，2K base 56.12）；开（1）= CPU 自己轮询
		// d3d12Fence，等于把渲染线程钉在 GPU 后面（v1.03b..v1.43 行为，base 36.08）。
		// 关掉后若游戏卡死，勾回来即可（无需重编译）——卡死只会发生在 D3D11 队列
		// 等一个永不 signal 的栅栏时（2026-09-18 18:23 那次）。
		ImGui::Separator();
		bool busyWait = s.fenceWaitBusy;
		if (ImGui::Checkbox("Present 里忙等栅栏（CPU 轮询 GPU）  |  Busy-wait fence in Present (CPU polls the GPU)", &busyWait)) {
			s.fenceWaitBusy = busyWait;
			const bool savedWait = SaveSettingsToIni(a_fg);
			SKSE::log::info("[FrameGen] FenceWaitBusy -> {} ({}) | {} | live, no restart needed",
				s.fenceWaitBusy ? 1 : 0,
				s.fenceWaitBusy ? "CPU poll" : "queue-side wait",
				savedWait ? "INI saved." : "INI SAVE FAILED.");
		}
		ImGui::TextDisabled("%s", busyWait
			? "开：CPU 一直阻塞到 GPU 画完本帧 —— CPU 与 GPU 不会重叠。\n"
			  "  ON: CPU blocks until the GPU finishes the frame - no CPU/GPU overlap."
			: "关：等待排到 D3D11 队列上 —— CPU 在 GPU 还在画第 N 帧时就先准备第 N+1 帧（更快）。\n"
			  "  OFF: wait queued on the D3D11 timeline - CPU builds frame N+1 during frame N.");

		ImGui::Separator();
		ImGui::Text("插帧状态  FG active: %s", a_fg.fgActive.load() ? "ON" : "OFF");
		ImGui::Text("DLSS: %s  DLSSG: %s",
			a_fg.streamline.featureDLSS ? "OK" : "-",
			a_fg.streamline.featureDLSSG ? "OK" : "-");
		ImGui::Text("刷新率  Refresh: %.0f Hz  |  %dx%d",
			a_fg.refreshRate, (int)a_fg.screenWidth, (int)a_fg.screenHeight);
		ImGui::Text("热键  Keys: Hold Home = Menu | FG switch in GUI");

		if (ImGui::Button("保存到 INI  |  Save to INI")) {
			// v0.52：改走统一写回函数（与自动保存同一份键表，不再漏键、不再静默失败）。
			const bool saved = SaveSettingsToIni(a_fg);
			if (saved)
				ImGui::TextColored(ImVec4(0.2f, 1.0f, 0.4f, 1.0f),
					"已保存（结果见日志）  |  Saved (see log for result)");
			else
				ImGui::TextColored(ImVec4(1.0f, 0.3f, 0.3f, 1.0f),
					"保存失败 —— 见日志  |  Save FAILED - see log");
		}

		ImGui::End();
	}
}
