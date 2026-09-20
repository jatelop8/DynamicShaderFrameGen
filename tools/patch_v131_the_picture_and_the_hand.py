#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
v1.31 -- two questions, four days old, that no instrument in this project has
ever been able to answer:

  1. WHAT DOES THE PLAYER SEE?  Every field we own is on our side of the fence.
     The 13:26 run is the proof: 4x latched ("MFG probe edge: ... step
     advertised=4x accepted=4x latched=1"), DLSS-G reported "presented per real
     frame = 4", 54 of 66 world frames were presented at 4x, the panel flipped
     139 times a second, and the SCREEN probe read distinct=8/8 in every single
     sample -- including through a five-second load fade, which is what makes
     that field worthless: `distinct` counts distinct hashes in an 8-sample
     RING, and a ring that spans a transition is eight distinct hashes by
     construction.  The only two samples in the world read lum=100.93 and
     lum=100.93 one second apart.

     So stop summarising and save the picture.  Every capture goes to disk as a
     640x360 BMP and the line carries the file name.  A hash cannot say whether
     the image was black, frozen, doubled or torn.  A picture can, and after
     four days of asking the user to describe it, this thing should simply look.

  2. WHO ENDED THE RUN?  Not one of the last twenty runs has a WER report, a
     Crash Logger entry, an nvlddmkm event or a minidump.  The 13:26 run is the
     first that says anything about who: at 13:26:45.648 GetAsyncKeyState saw
     0xA4 (LeftAlt) go down, and at 13:26:46.590 DirectionalMovement wrote
     "[DMK] WM_ACTIVATEAPP: Game lost focus. Clearing inputs." -- and our own
     log stopped inside the same 110 ms.  Alt on its own does not throw focus.

     Two defects hid that.  The witness only sampled at 1 Hz, and its "(2 held)"
     count counts VK_MENU (0x12) and VK_LMENU (0xA4) as two keys when they are
     ONE physical Alt, so the printed chord may have been a single key.  This
     version polls from Present (~35 Hz), collapses the aliases, prints the real
     key set, and NAMES the combination -- because "the process was killed" and
     "the player quit" are different findings and only one of them is our bug.

No frame generation path is touched.  Nothing here changes what the plugin does
to the game; it changes what the plugin can see.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DX = ROOT / "src" / "DX12SwapChain.cpp"
FG = ROOT / "src" / "FrameGen.cpp"

# ---------------------------------------------------------------------------
# DX12SwapChain.cpp
# ---------------------------------------------------------------------------

DX_HELPERS_OLD = """	const char* WatchdogLogPath()
	{
		return g_watchdogLogPath;
	}
"""

DX_HELPERS_NEW = """	const char* WatchdogLogPath()
	{
		return g_watchdogLogPath;
	}

	// ==================== v1.31: THE SCREEN, AS AN IMAGE ====================
	//
	// v1.30 hashed the screen and asked one question -- "did it hold one image
	// while our own image took three" -- and the 13:26 run answered nothing,
	// because `distinct` counts distinct hashes in an 8-sample RING, so a ring
	// that spans a load fade is eight distinct hashes no matter what happened.
	// It printed 8/8 through the fade, 8/8 in the menu and 8/8 in the world, and
	// the only two samples inside the world read lum=100.93 and lum=100.93.
	//
	// A hash answers "did it change".  It cannot answer "is what changed the
	// game", and that question has now cost four days.  So write the pixels out
	// and look at them.  The directory is a rolling ring of 96 files so it never
	// grows without bound, and the log line carries the file name of the capture
	// it describes -- an image nobody can find is the same as no image (L58).
	static char g_screenDumpDir[MAX_PATH * 2] = {};
	static bool g_screenDumpReady = false;

	const char* ScreenDumpDir()
	{
		if (!g_screenDumpReady) {
			g_screenDumpReady = true;
			std::string p;
			char buf[MAX_PATH] = {};
			if (SUCCEEDED(::SHGetFolderPathA(nullptr, CSIDL_PERSONAL, nullptr, 0, buf))) {
				p = buf;
				p += "\\\\My Games\\\\Skyrim Special Edition\\\\SKSE\\\\DFG_screens";
			} else {
				p = "DFG_screens";
			}
			::CreateDirectoryA(p.c_str(), nullptr);
			std::snprintf(g_screenDumpDir, sizeof(g_screenDumpDir), "%s", p.c_str());
		}
		return g_screenDumpDir;
	}

	// 24-bit bottom-up BMP.  The DIB section this reads is 32-bit BGRA top-down,
	// which is why the whole picture is not just an fwrite of the buffer.
	// Returns false unless every byte landed, so a missing file can never read
	// as "the screen was fine".
	bool WriteScreenBmp(const void* a_bits, int a_w, int a_h, unsigned a_idx)
	{
		if (!a_bits || a_w <= 0 || a_h <= 0 || a_w > 2048)
			return false;
		char path[MAX_PATH * 2] = {};
		std::snprintf(path, sizeof(path), "%s\\\\screen_%03u.bmp", ScreenDumpDir(), a_idx % 96u);
		std::FILE* bf = std::fopen(path, "wb");
		if (!bf)
			return false;
		const int rowBytes = a_w * 3;
		const int pad = (4 - (rowBytes % 4)) % 4;
		const unsigned datasize = static_cast<unsigned>((rowBytes + pad) * a_h);
		unsigned char hdr[54] = {};
		const unsigned fsize = 54u + datasize;
		const unsigned off = 54u;
		const unsigned short planes = 1u, bpp = 24u;
		hdr[0] = 'B'; hdr[1] = 'M';
		std::memcpy(hdr + 2, &fsize, 4);
		std::memcpy(hdr + 10, &off, 4);
		std::memcpy(hdr + 14, &a_w, 4);
		std::memcpy(hdr + 18, &a_h, 4);
		std::memcpy(hdr + 26, &planes, 2);
		std::memcpy(hdr + 28, &bpp, 2);
		std::memcpy(hdr + 34, &datasize, 4);
		bool ok = (std::fwrite(hdr, 1, sizeof(hdr), bf) == sizeof(hdr));
		const auto* px = static_cast<const unsigned char*>(a_bits);
		static unsigned char row[4096];
		for (int y = a_h - 1; y >= 0 && ok; --y) {
			const auto* src = px + static_cast<std::size_t>(y) * static_cast<std::size_t>(a_w) * 4u;
			int o = 0;
			for (int x = 0; x < a_w; ++x) {
				row[o++] = src[x * 4 + 0];
				row[o++] = src[x * 4 + 1];
				row[o++] = src[x * 4 + 2];
			}
			for (int i = 0; i < pad; ++i)
				row[o++] = 0;
			if (std::fwrite(row, 1, static_cast<std::size_t>(o), bf) != static_cast<std::size_t>(o))
				ok = false;
		}
		std::fclose(bf);
		return ok;
	}
"""

# flush before the capture
DX_FLUSH_OLD = "					// ========================== v1.30: THE SCREEN =========================="

DX_FLUSH_NEW = """					// v1.31: FLUSH BEFORE THE CAPTURE.  This loop opened the file,
					// wrote every line of the tick, and only flushed at the very end
					// -- and the GDI blit below is the one call in it that can block,
					// precisely when the game window is losing activation.  On 13:26
					// the last line in this file is 110 ms before the game lost focus
					// and the next tick never arrived, so one blocked blit would have
					// discarded that whole tick's readings without a trace.  The lines
					// above are now on disk before anything that can stall is called.
					std::fflush(f);

					// ========================== v1.30: THE SCREEN =========================="""

DX_GATE_OLD = "					if ((tick % 5) == 3) {"

DX_GATE_NEW = """					// v1.31: 1 Hz normally, 2.5 Hz while the flip counter has run
					// away from our own Present count -- the only reading in this file
					// that says frame generation is genuinely live.  Every one of the
					// last eight runs was in the world for 2.0 to 6.1 seconds, so a
					// 1 Hz capture has at most six frames of the only window anybody
					// has ever reported on.
					const bool scrBurst = (frames > 60ull) && (lastPr > frames + 8ull);
					if (((tick % 5) == 3) || (scrBurst && ((tick % 2) == 0))) {"""

DX_DIM_OLD = "						static const int kScrDim = 64;"

DX_DIM_NEW = """						// v1.31: 64x64 was enough for a hash and useless for an eye.
						// 640x360 HALFTONE keeps the layout readable: black load
						// screen, menu, world, and a torn or doubled frame are all
						// distinguishable at this size.
						static const int kScrW = 640;
						static const int kScrH = 360;"""

DX_W_OLD = "								bi.bmiHeader.biWidth = kScrDim;"
DX_W_NEW = "								bi.bmiHeader.biWidth = kScrW;"

DX_H_OLD = "								bi.bmiHeader.biHeight = -kScrDim;   // negative: rows top-down"
DX_H_NEW = "								bi.bmiHeader.biHeight = -kScrH;   // negative: rows top-down"

DX_BLT_OLD = "									? ::StretchBlt(s_scrDc, 0, 0, kScrDim, kScrDim, sd, vx, vy, vw, vh, SRCCOPY)"
DX_BLT_NEW = "									? ::StretchBlt(s_scrDc, 0, 0, kScrW, kScrH, sd, vx, vy, vw, vh, SRCCOPY)"

DX_NPX_OLD = "									const std::size_t nPx = static_cast<std::size_t>(kScrDim) * kScrDim;"
DX_NPX_NEW = "									const std::size_t nPx = static_cast<std::size_t>(kScrW) * static_cast<std::size_t>(kScrH);"

DX_LINE_OLD = """									const HWND probeW = reinterpret_cast<HWND>(g_probeHwnd.load());
									const int isFg = (probeW && ::GetForegroundWindow() == probeW) ? 1 : 0;
									std::fprintf(f, "[%lld] [SCREEN] #%u hash=%016llX lum=%.2f distinct=%u/%u "
										"ours=%016llX ourDistinct=%u fg=%d frames=%llu\\n",
										nowMs, s_scrSeq, static_cast<unsigned long long>(h2),
										static_cast<double>(slum), sDistinct, s_scrFill,
										static_cast<unsigned long long>(g_colorOutHash.load()),
										pDistinct, isFg,
										static_cast<unsigned long long>(frames));"""

DX_LINE_NEW = """									// v1.31: CONSECUTIVE-SAMPLE identity, and the picture
									// itself.  `distinct` is a ring statistic and cannot see
									// a freeze that begins inside the ring -- it read 8/8
									// through a fade, in the menu and in the world alike.
									// same= counts captures IDENTICAL TO THE ONE BEFORE,
									// which is what "the picture stopped" actually means;
									// oursSame= is the same count for our own colorOut, so
									// one number can be read against the other.  dLum= is
									// the magnitude, because a frozen image with a live FPS
									// overlay keeps drifting by a fraction of a level and
									// that fraction is the whole difference between "the
									// game froze" and "only the overlay is moving".
									static std::uint64_t s_scrPrevHash = 0ull;
									static std::uint64_t s_scrPrevOurs = 0ull;
									static float         s_scrPrevLum = -1.0f;
									static std::uint32_t s_scrSame = 0u;
									static std::uint32_t s_scrOursSame = 0u;
									const std::uint64_t oursNow = g_colorOutHash.load();
									const float dLum = (s_scrPrevLum < 0.0f) ? 0.0f : (slum - s_scrPrevLum);
									s_scrSame = (s_scrPrevHash != 0ull && h2 == s_scrPrevHash) ? (s_scrSame + 1u) : 0u;
									s_scrOursSame = (s_scrPrevOurs != 0ull && oursNow == s_scrPrevOurs) ? (s_scrOursSame + 1u) : 0u;
									s_scrPrevHash = h2;
									s_scrPrevOurs = oursNow;
									s_scrPrevLum = slum;
									const bool bmpOk = WriteScreenBmp(s_scrBits, kScrW, kScrH, s_scrSeq);
									const HWND probeW = reinterpret_cast<HWND>(g_probeHwnd.load());
									const int isFg = (probeW && ::GetForegroundWindow() == probeW) ? 1 : 0;
									std::fprintf(f, "[%lld] [SCREEN] #%u hash=%016llX lum=%.2f dLum=%+.2f "
										"same=%u oursSame=%u ring=%u/%u ours=%016llX fg=%d frames=%llu %s\\n",
										nowMs, s_scrSeq, static_cast<unsigned long long>(h2),
										static_cast<double>(slum), static_cast<double>(dLum),
										s_scrSame, s_scrOursSame, sDistinct, s_scrFill,
										static_cast<unsigned long long>(oursNow),
										isFg, static_cast<unsigned long long>(frames),
										bmpOk ? "bmp=ok" : "bmp=FAILED (no file for this line)");"""

DX_STALE_OLD = "									if (s_scrFill >= 8u && sDistinct <= 1u && pDistinct >= 3u && slum > 3.0f) {"

DX_STALE_NEW = """									// v1.31: the verdict is now the consecutive count, not
									// the ring statistic.  s_scrSame >= 7 means seven captures
									// in a row were byte-identical -- seven seconds of one
									// image -- while our own colorOut changed on all of them.
									// The ring version could never fire for the reason above.
									if (s_scrSame >= 7u && s_scrOursSame <= 1u && slum > 3.0f) {"""

DX_FROZEN_OLD = """											pDistinct, static_cast<unsigned long long>(frames));
									}
								}"""

DX_FROZEN_NEW = """											pDistinct, static_cast<unsigned long long>(frames));
									}
									// v1.31: the FROZEN verdict, and the one this whole probe was
									// built for.  Three captures in a row byte-identical while our
									// own image changed on every one of them: the panel is
									// flipping (frames= is still climbing), we are still drawing,
									// and what is on the screen is not any of it.  This is the
									// first criterion in this project that can see the failure
									// the user has been describing since the 15th.
									if (s_scrSame >= 3u && s_scrOursSame <= 1u && slum > 3.0f) {
										std::fprintf(f, "[%lld] [SCREEN] FROZEN for %u captures: the screen is byte-identical "
											"on every one of them (hash=%016llX lum=%.2f dLum=%+.2f) while our own colorOut "
											"changed on all of them and our Present was entered %llu times. The panel is "
											"advancing and the picture in it is not - this is what the player sees.\n",
											nowMs, s_scrSame,
											static_cast<unsigned long long>(h2),
											static_cast<double>(slum), static_cast<double>(dLum),
											static_cast<unsigned long long>(frames));
									}
								}"""

DX_EDITS = [
    ("DX :: screen dump helpers", DX_HELPERS_OLD, DX_HELPERS_NEW),
    ("DX :: flush before the capture", DX_FLUSH_OLD, DX_FLUSH_NEW),
    ("DX :: capture gate 1 Hz / 2.5 Hz", DX_GATE_OLD, DX_GATE_NEW),
    ("DX :: capture dimensions", DX_DIM_OLD, DX_DIM_NEW),
    ("DX :: bmp width", DX_W_OLD, DX_W_NEW),
    ("DX :: bmp height", DX_H_OLD, DX_H_NEW),
    ("DX :: StretchBlt extents", DX_BLT_OLD, DX_BLT_NEW),
    ("DX :: pixel count", DX_NPX_OLD, DX_NPX_NEW),
    ("DX :: the SCREEN line + bmp + same/dLum", DX_LINE_OLD, DX_LINE_NEW),
    ("DX :: STALE criterion", DX_STALE_OLD, DX_STALE_NEW),
    ("DX :: FROZEN verdict", DX_FROZEN_OLD, DX_FROZEN_NEW),
]

# ---------------------------------------------------------------------------
# FrameGen.cpp
# ---------------------------------------------------------------------------

FG_DECL_OLD = "					static int s_inKbHeld = 0;"
FG_DECL_NEW = """					static int s_inKbHeld = 0;
					// v1.31: keys that can actually move the player. "a key was down"
					// and "the player tried to move" are different sentences and only
					// the second one makes a still eyeD an accusation.
					static int s_inMvKeys = 0;"""

FG_SCAN_OLD = """						{
							static int s_kbLast = 0;
							int held = 0;
							int lastVk = 0;
							for (int vk = 1; vk < 256; ++vk) {
								if (::GetAsyncKeyState(vk) & 0x8000) {
									++held;
									lastVk = vk;
								}
							}
							s_inKbHeld = held;
							if (lastVk != s_kbLast) {
								SKSE::log::info("[INPUT] vk 0x{:02X} -> 0x{:02X} ({} held, fg={}) - any line here means the keyboard "
									"reaches this process, so an os=0x0 further down is a measurement and not a blind spot",
									static_cast<unsigned>(s_kbLast), static_cast<unsigned>(lastVk),
									held, s_inFg);
								s_kbLast = lastVk;
							}
						}"""

FG_SCAN_NEW = """						{
							// v1.31: this used to print the HIGHEST vk that was down as
							// "{} held", and the two numbers in that sentence disagreed
							// with each other.  The 13:26 run printed "vk 0x00 -> 0xA4
							// (2 held)" when the only key in the entire session was
							// LeftAlt, because GetAsyncKeyState reports VK_MENU (0x12) and
							// VK_LMENU (0xA4) separately for ONE physical key.  "(2 held)"
							// therefore read as a chord and was not one -- and whether a
							// second key was down is exactly what decides whether the run
							// ended by ALT+F4 or by ALT alone.  Report the set and the
							// physical count, and say which keys could have moved the
							// player.
							static int s_kbLast = 0;
							int raw = 0, phys = 0, mv = 0;
							bool kd[256] = {};
							for (int vk = 1; vk < 256; ++vk) {
								if (::GetAsyncKeyState(vk) & 0x8000) {
									kd[vk] = true;
									++raw;
								}
							}
							phys = raw;
							if ((kd[0xA4] || kd[0xA5]) && kd[0x12]) --phys;
							if ((kd[0xA0] || kd[0xA1]) && kd[0x10]) --phys;
							if ((kd[0xA2] || kd[0xA3]) && kd[0x11]) --phys;
							if (kd['W'] || kd['A'] || kd['S'] || kd['D'] ||
								kd[VK_UP] || kd[VK_DOWN] || kd[VK_LEFT] || kd[VK_RIGHT] || kd[VK_SPACE])
								++mv;
							s_inKbHeld = phys;
							s_inMvKeys += mv;
							if (raw != s_kbLast) {
								SKSE::log::info("[INPUT] key set changed: {} vk down, {} physical keys, {} of them can move "
									"the player (fg={}) - any line here means the keyboard reaches this process, so an "
									"os=0x0 further down is a measurement and not a blind spot",
									raw, phys, s_inMvKeys, s_inFg);
								s_kbLast = raw;
							}
						}"""

FG_VERDICT_OLD = """						(s_inKeys != 0u || s_inMoves != 0u || s_inKbHeld > 0)
							? "INPUT_SEEN - input reached the game, so a still eyeD here is a frozen world"
							: "INPUT_NONE - nothing was pressed this second, so this run cannot say whether input works");"""

FG_VERDICT_NEW = """						// v1.31: this used to accept ANY input as evidence, and on the
						// 13:26 run the only key in the session was LeftAlt -- which does
						// not move a character -- while the line still read "INPUT_SEEN
						// - a still eyeD here is a frozen world".  That is L61 again: a
						// criterion whose conclusion is wider than what it measured.  A
						// movement key was held, or the mouse moved, or the run cannot
						// say.
						(s_inMvKeys > 0 || s_inMoves != 0u)
							? "INPUT_MOVE_SEEN - a movement key was down this second, so a still eyeD here is a frozen world"
							: (s_inKbHeld > 0 || s_inKeys != 0u
								   ? "INPUT_NONMOVE - keys were down but none of them can move the player, so this says nothing about whether the world responds"
								   : "INPUT_NONE - nothing was pressed this second, so this run cannot say whether input works"));"""

FG_RESET_OLD = """					s_inKeys = 0u;
					s_inKbHeld = 0;"""
FG_RESET_NEW = """					s_inKeys = 0u;
					s_inKbHeld = 0;
					s_inMvKeys = 0;"""

FG_HOME_OLD = "		const bool down = (GetAsyncKeyState(VK_HOME) & 0x8000) != 0;"

FG_HOME_NEW = """		// ---- v1.31: WHO ENDED THE LAST RUN ----
		//
		// Twenty runs end 1.5-6 s after the world loads and not one of them carries
		// a WER report, a Crash Logger entry, an nvlddmkm event or a minidump --
		// which is the shape of a process that was QUIT or KILLED and the opposite
		// of a process that crashed.  The 13:26 run is the first whose last second
		// says anything at all: 0xA4 (LeftAlt) went down at 13:26:45.648, and at
		// 13:26:46.590 DirectionalMovement logged "WM_ACTIVATEAPP: Game lost focus.
		// Clearing inputs." and our own log stopped within 110 ms of it.  Alt alone
		// does not throw focus.
		//
		// The 1 Hz witness below cannot settle this: a chord held for a few hundred
		// milliseconds can fall entirely between two samples, and its "held" count
		// counts one physical Alt as two keys.  This runs from Present instead --
		// every frame, ~35 Hz -- collapses the aliases, prints the real key set, and
		// names the combination out loud.  Naming it matters: "the game was killed"
		// and "the player quit" are different findings, and only one is our bug.
		{
			static const char* s_lastCombo = nullptr;
			static unsigned long long s_lastSig = 0ull;
			bool kd[256] = {};
			int raw = 0, phys = 0, lo = 0;
			char list[80] = {};
			unsigned long long sig = 1469598103934665603ull;
			for (int vk = 1; vk < 256; ++vk) {
				if (GetAsyncKeyState(vk) & 0x8000) {
					kd[vk] = true;
					++raw;
					sig ^= static_cast<unsigned long long>(vk);
					sig *= 1099511628211ull;
					if (lo + 4 < static_cast<int>(sizeof(list))) {
						static const char* kHx = "0123456789ABCDEF";
						if (lo)
							list[lo++] = ' ';
						list[lo++] = kHx[(vk >> 4) & 0xF];
						list[lo++] = kHx[vk & 0xF];
						list[lo] = 0;
					}
				}
			}
			phys = raw;
			if ((kd[0xA4] || kd[0xA5]) && kd[0x12]) --phys;
			if ((kd[0xA0] || kd[0xA1]) && kd[0x10]) --phys;
			if ((kd[0xA2] || kd[0xA3]) && kd[0x11]) --phys;
			const bool alt = kd[0x12] || kd[0xA4] || kd[0xA5];
			const bool ctl = kd[0x11] || kd[0xA2] || kd[0xA3];
			const char* combo = nullptr;
			if (alt && kd[VK_F4])          combo = "ALT+F4 (quit)";
			else if (alt && kd[VK_TAB])    combo = "ALT+TAB (unfocus)";
			else if (alt && kd[VK_RETURN]) combo = "ALT+ENTER (exclusive/windowed toggle)";
			else if (alt && kd[VK_ESCAPE]) combo = "ALT+ESC";
			else if (alt && kd[VK_SPACE])  combo = "ALT+SPACE";
			else if (ctl && kd[VK_ESCAPE]) combo = "CTRL+ESC";
			else if (kd[VK_F4] && !alt)    combo = "F4 (alone)";
			if (combo && combo != s_lastCombo) {
				const HWND fw = GetForegroundWindow();
				DWORD fp = 0;
				if (fw)
					GetWindowThreadProcessId(fw, &fp);
				SKSE::log::info("[INPUT] *** {} *** is down at this frame. This is a combination that quits or "
					"unfocuses the game and it is the first thing to check when a run ends with no crash report. "
					"Every key down right now: [{}] ({} vk, {} physical). Our window is foreground: {}",
					combo, list[0] ? list : "none", raw, phys, (fp == GetCurrentProcessId()) ? 1 : 0);
			}
			s_lastCombo = combo;
			if (sig != s_lastSig) {
				s_lastSig = sig;
				SKSE::log::info("[INPUT] key set now [{}] ({} vk down, {} physical keys)", list[0] ? list : "none", raw, phys);
			}
		}

		const bool down = (GetAsyncKeyState(VK_HOME) & 0x8000) != 0;"""

FG_EDITS = [
    ("FG :: s_inMvKeys declaration", FG_DECL_OLD, FG_DECL_NEW),
    ("FG :: 1 Hz witness reports the set", FG_SCAN_OLD, FG_SCAN_NEW),
    ("FG :: verdict requires a movement key", FG_VERDICT_OLD, FG_VERDICT_NEW),
    ("FG :: reset s_inMvKeys", FG_RESET_OLD, FG_RESET_NEW),
    ("FG :: quit-combo detector in PollHomeKey", FG_HOME_OLD, FG_HOME_NEW),
]

# ---------------------------------------------------------------------------


def eol_of(raw: bytes) -> str:
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    cr = raw.count(b"\r")
    if crlf == 0 and cr == 0:
        return "LF"
    if crlf == lf and cr == crlf:
        return "CRLF"
    return "MIXED(%d/%d/%d)" % (crlf, lf, cr)


def main() -> int:
    apply = "--apply" in sys.argv
    plan = [(DX, DX_EDITS), (FG, FG_EDITS)]
    problems = []
    for path, edits in plan:
        raw = path.read_bytes()
        eol = eol_of(raw)
        bom = raw[:3] == b"\xef\xbb\xbf"
        text = raw.decode("utf-8-sig")
        # The anchors below are written with \n only.  A CRLF file needs the
        # newlines translated or every multi-line anchor matches nothing - which
        # is exactly what the first dry run of this script did to FrameGen.cpp.
        if eol == "CRLF":
            edits = [(l, o.replace("\n", "\r\n"), n.replace("\n", "\r\n"))
                     for (l, o, n) in edits]
        print("=== %s : %s, BOM=%s, %d bytes ===" % (path.name, eol, bom, len(raw)))
        for label, old, new in edits:
            n = text.count(old)
            status = "OK" if n == 1 else "*** COUNT=%d ***" % n
            if n != 1:
                problems.append("%s / %s -> count=%d" % (path.name, label, n))
            print("   %-44s count=%d  %s" % (label, n, status))
        if apply and not problems:
            for label, old, new in edits:
                text = text.replace(old, new, 1)
            out = text.encode("utf-8")
            if bom:
                out = b"\xef\xbb\xbf" + out
            path.write_bytes(out)
            raw2 = path.read_bytes()
            print("   -> wrote %d bytes, eol=%s, CR=%d" % (len(raw2), eol_of(raw2), raw2.count(b"\r")))
    if problems:
        print("\nREFUSED, nothing written:")
        for p in problems:
            print("   " + p)
        return 1
    if not apply:
        print("\nDRY RUN OK - rerun with --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
