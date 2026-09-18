#!/usr/bin/env python3
"""v0.62 - make the diagnostics survive a hang, and stop them starving.

Why, from the 2026-09-17 21:40 run:

  * The [XRAY] heartbeat printed exactly ONE line in the whole run (119 real
    frames, cadence was 240) -> zero usable samples.
  * That single line read mvec=(3.4e38,3.4e38) because the heartbeat block sits
    ABOVE the mvecScale assignment: it printed an uninitialised float.
  * real=0.00ms, because the first delta is (now - now) by construction.
  * "virtual!=physical => DPI-virtualized process" was hardcoded text and
    contradicted its own numbers (virtual == physical == 3840x2160).
  * Then the run went silent at 21:40:44.4. The 2 s FPS probe, the plugin's
    heartbeat AND Transfusion's 5 s startup heartbeat all stopped together, and
    nothing in the log says which call the render thread was parked in. That is
    the one question this build has to be able to answer.

What this patch does (diagnostics only - no behaviour change):

  1. Heartbeat fires every 30 frames OR 2 s; mvecScale is computed above it, so
     the number on the line is the value actually submitted this frame.
  2. real= divides by the ticks actually elapsed and skips its first sample.
  3. The heartbeat carries the real-frame interval window (min/avg/max/n), the
     Reflex cap this build programmed (capUs) and the long-frame count. 21:40
     perf.csv showed frames 12..77 at a rock-steady 102.56 ms = 4 x the 25.641 ms
     cap: min/avg/max on one line decides limiter-quantised vs GPU-bound.
  4. A >300 ms real frame prints immediately (that is the load/stall that freezes
     the picture while DLSS-G keeps presenting interpolated frames).
  5. A watchdog thread writes 1 Hz to its own file with fopen/fflush/fclose, so
     liveness is provable even when the render thread is blocked and even if the
     SKSE logger never flushes its tail. It prints the Present() stage the render
     thread last entered (DX12SwapChain::lastStage already existed, but was only
     ever used in exception messages).

Usage:
    python tools/add_xray_v062.py            # dry run, prints the plan
    python tools/add_xray_v062.py --apply    # backs up, writes, verifies
"""

import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MARKER = "[XRAY] WATCHDOG started (1 Hz)"
WATCHDOG_FILE = "DynamicShaderFrameGen.watchdog.log"

# --------------------------------------------------------------------- new text

H_ATOMIC_INCLUDE = """#include <wrl/wrappers/corewrappers.h>

// v0.62: hang forensics (watchdog thread + atomic frame stamps)
#include <atomic>
#include <thread>"""

H_MEMBERS = """		const char* m_stage = "init";
		const char* lastStage() const { return m_stage; }

		// v0.62: hang forensics. The 21:40 run stopped writing at 21:40:44.4 -
		// the [XRAY] heartbeat, the 2 s FPS probe and Transfusion's 5 s startup
		// heartbeat all went silent together - and no line said WHICH call the
		// render thread was parked in. The watchdog keeps writing from outside the
		// render thread, and lastStage() names the call it is stuck on.
		// lastStage() already existed (v0.5.5) but was only ever read by an
		// exception handler, so a hang produced nothing at all.
		std::atomic<std::uint64_t> frameCounter{ 0 };
		std::atomic<long long> lastFrameEndMs{ 0 };
		std::atomic<bool> watchdogStop{ false };
		void StartWatchdog();"""

CPP_INCLUDES = """#include <FidelityFX/api/include/dx12/ffx_api_dx12.hpp>
#include <dxgi1_6.h>
#include <d3dcompiler.h>

// v0.62: watchdog needs its own file handle + the Documents path
#include <cstdio>
#include <shlobj.h>"""

CPP_CREATEINTEROP = """	void DX12SwapChain::CreateInterop()
	{
		// v0.62: start the watchdog as soon as the interop exists - from here on
		// every Present can be attributed to a stage.
		StartWatchdog();

		HANDLE sharedFenceHandle;"""

CPP_WATCHDOG = """	// v0.62: 1 Hz watchdog. Writes with fopen/fflush/fclose rather than through
	// SKSE::log, deliberately: if the render thread is blocked the SKSE logger may
	// never flush its tail, and a process that is force-killed loses whatever the
	// sink still buffers. A plain append + flush per tick is the only write that is
	// guaranteed to reach the disk before the process dies, which is exactly the
	// situation this instrument exists for.
	void DX12SwapChain::StartWatchdog()
	{
		static std::atomic<bool> started{ false };
		bool expected = false;
		if (!started.compare_exchange_strong(expected, true))
			return;

		// Same directory SKSE writes its own logs to, so one folder holds the story.
		std::string path;
		{
			char buf[MAX_PATH] = {};
			if (SUCCEEDED(::SHGetFolderPathA(nullptr, CSIDL_PERSONAL, nullptr, 0, buf))) {
				path = buf;
				path += "\\\\My Games\\\\Skyrim Special Edition\\\\SKSE\\\\";
			}
			path += "MARKER_WATCHDOG_FILE";
		}

		std::thread([this, path]() {
			auto& self = *this;
			SKSE::log::info("MARKER_WATCHDOG - file: {} (stage= names the blocking call)", path);
			for (;;) {
				for (int i = 0; i < 5; ++i) {   // 200 ms slices so stop is honoured quickly
					if (self.watchdogStop.load())
						return;
					std::this_thread::sleep_for(std::chrono::milliseconds(200));
				}
				const long long nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
					std::chrono::steady_clock::now().time_since_epoch()).count();
				const std::uint64_t frames = self.frameCounter.load();
				const long long lastEnd = self.lastFrameEndMs.load();
				const long long silent = lastEnd ? (nowMs - lastEnd) : -1;
				if (FILE* f = std::fopen(path.c_str(), "a")) {
					std::fprintf(f, "[%lld] frames=%llu silent=%lldms stage=%s%s\\n",
						nowMs, static_cast<unsigned long long>(frames), silent, self.lastStage(),
						(lastEnd != 0 && silent > 1500) ? "   <== RENDER THREAD STALLED" : "");
					std::fflush(f);
					std::fclose(f);
				}
			}
		}).detach();
	}

	HRESULT DX12SwapChain::Present(UINT SyncInterval, UINT Flags)
	{
		auto& fg = Get();

		// v0.62: stamp every exit path (there are three return S_OK branches). The
		// watchdog compares this against its own clock: a stamp that stops moving
		// while the watchdog keeps ticking is a stalled render thread, and m_stage
		// then says which call it is stalled in.
		struct FrameStamp
		{
			explicit FrameStamp(DX12SwapChain* a_self) : self(a_self) {}
			DX12SwapChain* self;
			~FrameStamp()
			{
				self->lastFrameEndMs.store(std::chrono::duration_cast<std::chrono::milliseconds>(
					std::chrono::steady_clock::now().time_since_epoch()).count());
			}
		} frameStamp(this);
		++frameCounter;
		m_stage = "present entry";"""

CPP_FRAMESTAMP_ANCHOR = """	HRESULT DX12SwapChain::Present(UINT SyncInterval, UINT Flags)
	{
		auto& fg = Get();"""

SL_H_DIAG = """			std::uint32_t lastCountedSerial = 0xFFFFFFFFu;
			bool menuOpenNow = false;

			// v0.62: pacing / limiter evidence. reflexCapUs is the cap this build
			// actually handed to Reflex; the win* fields are the real-frame interval
			// window (measured in ReflexSleep, which runs exactly once per real
			// frame). 2026-09-17 21:40 perf.csv: frames 12..77 arrived at a
			// rock-steady 102.56 ms = 4 x the 25.641 ms cap, and the panel got 39
			// presented fps instead of the intended 156. min/avg/max on the same
			// line is what separates "the limiter is applied 4x too hard"
			// (quantised) from "the GPU genuinely needs 102 ms" (wanders).
			std::uint32_t reflexCapUs = 0;
			double winMinMs = 0.0;
			double winMaxMs = 0.0;
			double winSumMs = 0.0;
			std::uint64_t winN = 0;
			std::uint32_t longFrames = 0;
		};"""

SL_MVEC_BLOCK = """		{
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
		}"""

SL_HB_ANCHOR = """		// ===== [XRAY] heartbeat (v0.61) ====="""

SL_REFLEX_TAIL = """		opts.useMarkersToOptimize = featurePCL;   // PCL marker 优化（Reflex 激活必需）"""

SL_REFLEX_WINDOW = SL_REFLEX_TAIL + """

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
		}"""


# --------------------------------------------------------------------- edits
# (label, old, new) - applied in order; every `old` must occur EXACTLY once at
# the moment it is applied. Delete-before-insert where the same text moves.

EDITS = {}

EDITS["src/Streamline.h"] = [
    (
        "Diag: pacing + long-frame counters",
        """			std::uint32_t lastCountedSerial = 0xFFFFFFFFu;
			bool menuOpenNow = false;
		};""",
        SL_H_DIAG,
    ),
]

EDITS["src/Streamline.cpp"] = [
    # ---- 1. mvecScale moves ABOVE the heartbeat (delete here, insert below) ----
    (
        "mvecScale block: remove from its old position",
        SL_MVEC_BLOCK + """
		c.motionVectors3D = sl::Boolean::eFalse;""",
        """		c.motionVectors3D = sl::Boolean::eFalse;""",
    ),
    (
        "mvecScale block: insert above the heartbeat",
        SL_HB_ANCHOR,
        """		// v0.62: mvecScale is computed HERE, above the heartbeat, because the
		// heartbeat used to print c.mvecScale before the assignment below had run -
		// the 21:40 run's only sample therefore read mvec=(3.4e38,3.4e38), i.e.
		// uninitialised FLT_MAX, and would have been read as a real defect. Order
		// matters for a diagnostic line.
""" + SL_MVEC_BLOCK + """

""" + SL_HB_ANCHOR,
    ),
    # ---- 2. cadence ----
    (
        "heartbeat cadence 240 -> 30 frames or 2 s",
        """			static std::uint32_t xrayTick = 0;
			if (++xrayTick % 240 == 1) {""",
        """			static std::uint32_t xrayTick = 0;
			// v0.62: 30 frames OR 2 s, whichever comes first. The 240-frame cadence
			// produced exactly ONE heartbeat in the entire 21:40 run (119 real
			// frames), so that run answered none of the questions it was
			// instrumented for.
			static auto xrayLastPrint = std::chrono::steady_clock::now();
			const bool xrayTimeUp = std::chrono::duration<double>(
				std::chrono::steady_clock::now() - xrayLastPrint).count() >= 2.0;
			if (++xrayTick % 30 == 1 || xrayTimeUp) {
				xrayLastPrint = std::chrono::steady_clock::now();""",
    ),
    # ---- 3. real= seeding ----
    (
        "real= : divide by elapsed ticks, skip the first sample",
        """				static auto xrayPrev = std::chrono::steady_clock::now();
				const auto xrayNow = std::chrono::steady_clock::now();
				const double realMs =
					std::chrono::duration<double, std::milli>(xrayNow - xrayPrev).count() / 240.0;
				xrayPrev = xrayNow;""",
        """				// v0.62: divide by the ticks actually elapsed instead of the
				// hardcoded 240, and skip the first sample - its delta is (now - now)
				// by construction, which is why 21:40 reported "real=0.00ms".
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
				xrayPrevValid = true;""",
    ),
    # ---- 4. heartbeat line: add dt window / cap / mult / long frames ----
    (
        "heartbeat line: append dt window, capUs, mult, longFrames",
        """					"real={:.2f}ms | mvec=({:.3f},{:.3f}) flags={:#x} | jitter=({:.4f},{:.4f}) "
					"clipDev={:.6f} curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) "
					"prevPos=({:.1f},{:.1f},{:.1f})",""",
        """					"real={:.2f}ms | mvecScale=({:.3f},{:.3f}) flags={:#x} | jitter=({:.4f},{:.4f}) "
					"clipDev={:.6f} curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) "
					"prevPos=({:.1f},{:.1f},{:.1f}) | dt min/avg/max={:.2f}/{:.2f}/{:.2f}ms n={} "
					"capUs={} mult(acc/pres)={}/{} longFrames={}",""",
    ),
    (
        "heartbeat args: append the new fields",
        """					a_fb.CameraPreviousPosAdjust[0], a_fb.CameraPreviousPosAdjust[1],
					a_fb.CameraPreviousPosAdjust[2]);""",
        """					a_fb.CameraPreviousPosAdjust[0], a_fb.CameraPreviousPosAdjust[1],
					a_fb.CameraPreviousPosAdjust[2],
					diag.winMinMs, diag.winN ? (diag.winSumMs / static_cast<double>(diag.winN)) : 0.0,
					diag.winMaxMs, diag.winN, diag.reflexCapUs,
					dlssgAcceptedFrames + 1, diag.presentedPrev, diag.longFrames);""",
    ),
    # ---- 5. reset the window after each heartbeat ----
    (
        "reset the dt window after each heartbeat",
        """				SKSE::log::info("[XRAY] VERDICT: {}", vd);
			}
		}""",
        """				SKSE::log::info("[XRAY] VERDICT: {}", vd);
				// The window describes exactly one heartbeat interval.
				diag.winMinMs = 0.0;
				diag.winMaxMs = 0.0;
				diag.winSumMs = 0.0;
				diag.winN = 0;
				diag.longFrames = 0;
			}
		}""",
    ),
    # ---- 6. env line ----
    (
        "env line: make the comparison real instead of hardcoded",
        """					"render={:.4f} dpiAware={} | virtual!=physical => DPI-virtualized process",
					vw, vh, pw, ph, hz, a_width, a_height, sc.renderScaleX,
					::IsProcessDPIAware() ? 1 : 0);""",
        """					"render={:.4f} dpiAware={} | {}",
					vw, vh, pw, ph, hz, a_width, a_height, sc.renderScaleX,
					::IsProcessDPIAware() ? 1 : 0,
					(vw == pw && vh == ph) ? "virtual==physical (no DPI scaling)"
					                       : "virtual!=physical => DPI-virtualized process");""",
    ),
    # ---- 7. ReflexSleep: cap + interval window ----
    (
        "ReflexSleep: record cap + real-frame interval window + long frames",
        SL_REFLEX_TAIL,
        SL_REFLEX_WINDOW,
    ),
]

EDITS["src/DX12SwapChain.h"] = [
    (
        "includes: atomic + thread for the watchdog",
        """#include <wrl/wrappers/corewrappers.h>""",
        H_ATOMIC_INCLUDE,
    ),
    (
        "members + StartWatchdog()",
        """		const char* m_stage = "init";
		const char* lastStage() const { return m_stage; }""",
        H_MEMBERS,
    ),
]

EDITS["src/DX12SwapChain.cpp"] = [
    (
        "includes: cstdio + shlobj",
        """#include <FidelityFX/api/include/dx12/ffx_api_dx12.hpp>
#include <dxgi1_6.h>
#include <d3dcompiler.h>""",
        CPP_INCLUDES,
    ),
    (
        "CreateInterop: start the watchdog",
        """	void DX12SwapChain::CreateInterop()
	{
		HANDLE sharedFenceHandle;""",
        CPP_CREATEINTEROP,
    ),
    (
        "StartWatchdog() definition + per-frame stamp",
        CPP_FRAMESTAMP_ANCHOR,
        CPP_WATCHDOG,
    ),
]

# Placeholders substituted after the edits are declared, so no fragile string
# concatenation sneaks into the C++ text above.
SUBST = {
    "MARKER_WATCHDOG_FILE": WATCHDOG_FILE,
    "MARKER_WATCHDOG": MARKER,
}


def detect_eol(text):
    """Return the file's dominant line ending ('\\r\\n' or '\\n').

    Do NOT assume: an earlier check of these files reported "all CRLF" because
    `grep -c $'\\r'` had silently received an empty pattern and matched every
    line. Verified byte-wise instead (cat -A shows no ^M), and the patch then
    refused until this was fixed. Anchors must be built in the file's own ending
    or every multi-line anchor fails with count == 0.
    """
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def clean(text, eol):
    """Normalise a patch snippet written with \\n into the file's ending."""
    return text.replace("\r\n", "\n").replace("\n", eol)


def sub(text):
    for k, v in SUBST.items():
        text = text.replace(k, v)
    return text


def path_of(rel):
    return os.path.join(ROOT, rel.replace("/", os.sep))


def main():
    apply = "--apply" in sys.argv

    # Idempotency guard FIRST. "The anchor is unique" does NOT prove "the patch
    # has not already run" - this marker is produced only by this script.
    for rel in EDITS:
        p = path_of(rel)
        if not os.path.isfile(p):
            print("REFUSED: missing file %s" % p)
            return 2
        if MARKER in open(p, "rb").read().decode("utf-8", "replace"):
            print("REFUSED: %s already carries the v0.62 marker - nothing written" % rel)
            return 2

    plans = []
    for rel, edits in EDITS.items():
        p = path_of(rel)
        raw = open(p, "rb").read().decode("utf-8")
        before = os.path.getsize(p)
        eol = detect_eol(raw)
        text = raw
        for label, old, new in edits:
            o, n = clean(sub(old), eol), clean(sub(new), eol)
            c = text.count(o)
            if c != 1:
                print("REFUSED: [%s] %s -> anchor occurs %d times (must be 1)" % (rel, label, c))
                print("--------- anchor as searched ---------")
                print(o[:500])
                return 2
            text = text.replace(o, n, 1)
        plans.append((rel, p, text, before, len(edits), eol))

    print("plan OK - %d file(s), %d edit(s)"
          % (len(plans), sum(x[4] for x in plans)))
    for rel, p, text, before, n, eol in plans:
        raw = text.encode("utf-8")
        print("  %-24s %2d edits  EOL=%s  lines=%d  %d -> %d bytes"
              % (rel, n, "CRLF" if eol == "\r\n" else "LF",
                 text.count("\n"), before, len(raw)))
    print("  marker : %s" % MARKER)
    print("  watchdog file: %s" % WATCHDOG_FILE)

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    for rel, p, text, _, _, eol in plans:
        bak = "%s.bak-%s" % (p, stamp)
        shutil.copy2(p, bak)
        with open(p, "wb") as f:
            f.write(text.encode("utf-8"))
        back = open(p, "rb").read().decode("utf-8")
        if back != text:
            print("REFUSED-FINISH: readback differs on %s - restore from %s" % (rel, bak))
            return 2
        if detect_eol(back) != eol:
            print("REFUSED-FINISH: line ending changed on %s - restore from %s" % (rel, bak))
            return 2
        print("WROTE  %-24s backup=%s" % (rel, os.path.basename(bak)))

    print("\nOK - all files written, readback identical, line endings preserved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
