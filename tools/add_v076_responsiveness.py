#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.76: make the next run answer the one question the watchdog cannot answer today.

WHY THIS PATCH EXISTS
---------------------
The 07:28 run (v0.75) produced a *healthy* GPU timeline:
    fence 1 -> 1414 monotonic, queued peak 1, lastPr 0 -> 1366, silent 3 ms.
Yet the user reports "the game froze after entering". Two readings fit that
data and they cannot be told apart with the fields that exist:

  (a) the user killed the process (no DLL_PROCESS_DETACH) while it was alive;
  (b) some *other* thread -- the window/message thread -- stopped responding
      while the render thread kept presenting, which is exactly what Windows
      paints as "Not Responding" and what a player calls a freeze.

Every watchdog field today is sampled from the render thread or from the
display driver. None of them touches the window message pump, so (b) is
invisible. This patch adds the missing probe and fixes one wrong one.

CHANGES
-------
W1  new global g_lastMsgOk / g_lastWinAlive atomic pair, published by the
    watchdog thread (the sampler already parks in the driver; the watchdog is
    the thread that must stay free).
W2  the watchdog now probes the game window every tick with
    SendMessageTimeout(hwnd, WM_NULL, ..., SMTO_ABORTIFHUNG, 200). That is the
    same question USER32 asks before it paints "Not Responding", so msg=0 is
    the user-visible freeze, measured rather than inferred. IsWindow() is
    folded into alive=.
W3  FIX: dsync was computed by comparing GetCurrentBackBufferIndex() *after*
    Present against frameIndex from *before* it. A successful flip advances the
    index by construction, so dsync=1 meant "the flip worked" while the reader
    documented it as "desynced" -- an inverted judgement that produced a false
    positive on every healthy frame (段 #11 291/291). It now means "the flip
    did NOT change the index", which is the state actually worth reporting.
W4  RELOCK is a 12-frame-continuous-rejection escape hatch, and while three
    cameras rotate through one perFrame buffer that hatch fires on a schedule
    and accepts whichever camera happens to be standing there. Log which one
    it took (pos + devVP) instead of accepting it silently.

A patch script that cannot prove its anchors still match is worse than no
patch at all -- every edit asserts count(old) == 1 and refuses to write
otherwise. Dry-run by default; pass --apply to write.
"""
import hashlib
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
CPP = os.path.join(SRC, "DX12SwapChain.cpp")
HDR = os.path.join(SRC, "DX12SwapChain.h")
CAM = os.path.join(SRC, "FrameGen.cpp")

# ---------------------------------------------------------------------------
# anchors: (label, file, old, new)
# every `old` must appear EXACTLY once in its file
# ---------------------------------------------------------------------------
W1_OLD = """	static std::atomic<unsigned long long> g_fenceRaw11{ ~0ull };
	static std::atomic<unsigned long long> g_fenceRaw12{ ~0ull };
"""
W1_NEW = """	static std::atomic<unsigned long long> g_fenceRaw11{ ~0ull };
	static std::atomic<unsigned long long> g_fenceRaw12{ ~0ull };

	// v0.76: the one question every other field here cannot answer.
	// All of them are sampled from the render thread or from the display driver.
	// A window whose message pump has stopped while the render thread keeps
	// presenting reads as perfectly healthy in this file, yet it is exactly
	// what the player calls a freeze and what USER32 paints as "Not Responding".
	// msg=0 -> the window did not answer WM_NULL within 200 ms.
	// alive=0 -> the window itself is gone (the process is on its way out).
	static std::atomic<int> g_lastMsgOk{ 1 };
	static std::atomic<int> g_lastWinAlive{ 0 };
	// v0.76: the hwnd the watchdog should probe, published once by Present.
	// Never read a member from the watchdog thread -- it must not touch
	// anything the render thread may be inside of.
	static std::atomic<std::uintptr_t> g_probeHwnd{ 0 };
"""

W2_OLD = """					const unsigned long long queued = g_queuedDepth.load();
					const unsigned long long lastPr = g_lastPresentCount.load();
					const unsigned long long dsync = g_flipDesync.load();
					std::fprintf(f, "[%lld] %02d:%02d:%02d.%03d frames=%llu silent=%lldms "
						"stage=%s focus=%d fence=%s stim=%llu queued=%llu lastPr=%llu dsync=%llu%s\\n",
						nowMs, wtc.wHour, wtc.wMinute, wtc.wSecond, wtc.wMilliseconds,
						static_cast<unsigned long long>(frames), silent, self.lastStage(),
						g_lastFocus.load(), fenceTxt, stim, queued, lastPr, dsync,
						(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
"""
W2_NEW = """					const unsigned long long queued = g_queuedDepth.load();
					const unsigned long long lastPr = g_lastPresentCount.load();
					const unsigned long long dsync = g_flipDesync.load();
					// v0.76: ask the window the same question USER32 asks before it
					// paints "Not Responding". SMTO_ABORTIFHUNG makes the call return
					// *now* if the target is already hung instead of burning the full
					// timeout, and the timeout bounds the worst case for a watchdog
					// that must never park. A dead window answers nothing at all, so
					// alive= is checked first and msg= is only meaningful when it is 1.
					int msgOk = g_lastMsgOk.load();
					int winAlive = g_lastWinAlive.load();
					if ((tick % 5) == 0) {
						const HWND probe = reinterpret_cast<HWND>(g_probeHwnd.load());
						if (probe && ::IsWindow(probe)) {
							DWORD_PTR res = 0;
							const LRESULT lr = ::SendMessageTimeoutA(probe, WM_NULL, 0, 0,
								SMTO_ABORTIFHUNG | SMTO_BLOCK, 200, &res);
							msgOk = (lr != 0) ? 1 : 0;
							winAlive = 1;
						} else {
							msgOk = 0;
							winAlive = 0;
						}
						g_lastMsgOk.store(msgOk);
						g_lastWinAlive.store(winAlive);
					}
					std::fprintf(f, "[%lld] %02d:%02d:%02d.%03d frames=%llu silent=%lldms "
						"stage=%s focus=%d fence=%s stim=%llu queued=%llu lastPr=%llu dsync=%llu "
						"msg=%d alive=%d%s\\n",
						nowMs, wtc.wHour, wtc.wMinute, wtc.wSecond, wtc.wMilliseconds,
						static_cast<unsigned long long>(frames), silent, self.lastStage(),
						g_lastFocus.load(), fenceTxt, stim, queued, lastPr, dsync,
						msgOk, winAlive,
						(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
"""

W3_OLD = """				const UINT real = swapChain->GetCurrentBackBufferIndex();
				g_flipDesync.store(real == frameIndex ? 0ull : 1ull);"""
W3_NEW = """				// v0.76 FIX: the comparison below was inverted. Present() advances
				// the DXGI back-buffer index by construction on a successful flip,
				// so comparing the post-Present index against the pre-Present
				// frameIndex reported 1 for every *healthy* frame -- the 07:23 run
				// (291/291) read as a total desync while it was in fact flipping
				// perfectly. The state worth reporting is the opposite one: the
				// index did not move, i.e. Present returned success without a flip.
				const UINT real = swapChain->GetCurrentBackBufferIndex();
				g_flipDesync.store(real == frameIndex ? 1ull : 0ull);"""

W4_OLD = """			++snapRelock;
			SKSE::log::warn("[CAM] #{} RELOCK after {} consecutive jumps (teleport / scene change) "
				"-> accepting pos=({:.1f},{:.1f},{:.1f})",
				snapArrivals, snapConsecReject, px, py, pz);"""
W4_NEW = """			++snapRelock;
			// v0.76: this hatch exists for a real teleport / scene change, but it
			// also fires on a schedule when several cameras rotate through one
			// perFrame buffer -- each frame is >400 units from the last accepted
			// one, so after 12 consecutive rejections it accepts whichever camera
			// happens to be standing there. Record *which* camera it took, so a
			// wrong one is visible instead of being silently installed as the
			// world camera for the next 12 frames.
			SKSE::log::warn("[CAM] #{} RELOCK after {} consecutive jumps (teleport / scene change) "
				"-> accepting pos=({:.1f},{:.1f},{:.1f}) devVP={:.6g} magVP={:.6g}",
				snapArrivals, snapConsecReject, px, py, pz,
				camDev(a_src.CameraViewProjUnjittered), camMag(a_src.CameraViewProjUnjittered));"""

EDITS = [
    ("W1 globals", CPP, W1_OLD, W1_NEW),
    ("W2 watchdog probe + line", CPP, W2_OLD, W2_NEW),
    ("W3 dsync direction fix", CPP, W3_OLD, W3_NEW),
    ("W4 relock reports camera", CAM, W4_OLD, W4_NEW),
]

# canaries: strings that must exist afterwards, and how many times
CANARIES = [
    (CPP, "v0.76: the one question every other field here cannot answer", 1),
    (CPP, "g_lastMsgOk.load()", 1),
    (CPP, "SendMessageTimeoutA(probe, WM_NULL", 1),
    (CPP, "msg=%d alive=%d", 1),
    (CPP, "real == frameIndex ? 1ull : 0ull", 1),
    (CPP, "real == frameIndex ? 0ull : 1ull", 0),
    (CAM, "-> accepting pos=({:.1f},{:.1f},{:.1f}) devVP={:.6g} magVP={:.6g}", 1),
]

# markers: if any of these is already present the patch has been applied
MARKERS = [
    "v0.76: the one question every other field here cannot answer",
    "g_lastMsgOk.load()",
    "if ((tick % 5) == 0) {\n\t\t\t\t\t\tconst HWND probe",
]


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def main():
    apply = "--apply" in sys.argv

    # ---- idempotency guard, FIRST (an insertion patch does not consume its
    # ---- anchor, so count(old)==1 alone cannot tell a re-run from a first run)
    for path in (CPP, HDR, CAM):
        text = read(path).decode("utf-8")
        for m in MARKERS:
            if m in text:
                print("REFUSED: marker already present in %s" % os.path.basename(path))
                print("  marker: %r" % m[:70])
                return 2

    texts = {p: read(p).decode("utf-8") for p in (CPP, HDR, CAM)}
    originals = dict(texts)

    # ---- anchor check: every anchor must match exactly once
    ok = True
    for label, path, old, new in EDITS:
        n = texts[path].count(old)
        if n != 1:
            print("REFUSED: %s -- anchor found %d times in %s (need exactly 1)"
                  % (label, n, os.path.basename(path)))
            ok = False
    if not ok:
        print("REFUSED, nothing written.")
        return 1

    # ---- apply
    for label, path, old, new in EDITS:
        texts[path] = texts[path].replace(old, new, 1)
        print("applied: %s" % label)

    # ---- structural check: braces/parens may be ADDED, but they must stay paired.
    #     (Asserting "balance unchanged" is wrong: a patch that adds code is
    #     supposed to add braces. What must never move is the DIFFERENCE between
    #     open and close -- that is what a dropped brace in a replacement string
    #     looks like, and it is invisible to the eye.)
    for path in (CPP, HDR, CAM):
        for pair, nm in ((("{", "}"), "brace"), (("(", ")"), "paren")):
            o, c = pair
            d_open = originals[path].count(o) - texts[path].count(o)
            d_close = originals[path].count(c) - texts[path].count(c)
            if d_open != d_close:
                print("REFUSED: %s imbalance in %s (delta open=%+d close=%+d)"
                      % (nm, os.path.basename(path), -d_open, -d_close))
                return 1

    # ---- canaries
    for path, needle, want in CANARIES:
        got = texts[path].count(needle)
        if got != want:
            print("REFUSED: canary %r found %d times (want %d)"
                  % (needle[:60], got, want))
            return 1

    print("\n--- byte / line deltas ---")
    for path in (CPP, HDR, CAM):
        ob = originals[path].encode("utf-8")
        nb = texts[path].encode("utf-8")
        print("%-22s %7d -> %7d  (%+d bytes), lines %d -> %d"
              % (os.path.basename(path), len(ob), len(nb), len(nb) - len(ob),
                 ob.count(b"\n"), nb.count(b"\n")))

    if not apply:
        print("\nDRY RUN - pass --apply to write.")
        return 0

    # ---- write, preserving each file's own line ending convention
    for path, text in texts.items():
        orig = originals[path]
        crlf = orig.count("\r\n")
        lf_only = orig.count("\n") - crlf
        data = text.encode("utf-8")
        conc = "CRLF" if crlf and not lf_only else ("LF" if lf_only and not crlf else "MIXED")
        with open(path, "wb") as fh:
            fh.write(data)
        print("wrote %s (%s preserved)" % (os.path.basename(path), conc))

    print("\n--- verification (independent re-read from disk) ---")
    bad = 0
    for path, needle, want in CANARIES:
        got = read(path).decode("utf-8").count(needle)
        flag = "OK " if got == want else "BAD"
        if got != want:
            bad += 1
        print("  [%s] %-58s %d (want %d)" % (flag, needle[:58], got, want))
    print("RESULT: %s" % ("OK" if bad == 0 else "%d canary failures" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
