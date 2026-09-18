#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.71 -- stop the unfocused-window Present deadlock.

THE FINDING (2026-09-17 23:40:22 session)
-----------------------------------------
The last line in ANY log of that session is, in DirectionalMovement's log:

    [23:40:22.221] [31204] [I] [DMK] WM_ACTIVATEAPP: Game lost focus. Clearing inputs.

ShadowLimitFix's per-frame logging stopped at 23:40:22.166 -- 55 ms earlier.
Five independent loggers stop in the same instant (DynamicSnow, ShadowLimitFix,
DirectionalMovement, our own log, our own watchdog thread). Audio keeps playing.
No crash log, no WER report, no TDR (Display driver did not reset), no
DXGI_ERROR_DEVICE_REMOVED. That combination is a Present() that never returns:

    desc1.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
    desc1.BufferCount = 3;
    DX::ThrowIfFailed(swapChain->Present(0, Flags));     // no DO_NOT_WAIT

Flip-model Present blocks until a queued buffer is released, and DXGI stops
releasing buffers for a window that is occluded or in the background. With
multi-frame generation the app hands 4 frames per real frame to that 3-deep
queue, so it lives permanently at the edge of "queue full" -- on focus loss the
very next Present wedges instead of merely being late.

The plugin had ZERO focus handling: no GetForegroundWindow, no IsIconic, no
WM_ACTIVATEAPP, no DXGI_PRESENT_DO_NOT_WAIT anywhere in src/.

WHAT THIS PATCH DOES
--------------------
1. FocusAllowsPresenting(hwnd) + one per-frame sample (g_lastFocus for the watchdog).
2. On the focus-loss edge, tell DLSS-G mode=Off once (SetDLSSGOptions(..., false))
   so the runtime stops holding the swap chain; the normal per-frame
   SetDLSSGOptions(eOn) restores it when focus returns.
3. Unfocused frame = same passthrough as the menu path (no SetDLSSGOptions, no
   EvaluateDLSSG), and the fail counter is cleared so the ~2 s auto-disable
   cannot fire during a long alt-tab.
4. Both Present() calls pass DXGI_PRESENT_DO_NOT_WAIT while unfocused and treat
   DXGI_ERROR_WAS_STILL_DRAWING as "frame not shown", not as a failure.
5. Watchdog: 200 ms ticks (was 1 Hz) + a focus= field, so the next hang is
   localised to ~8 frames and says whether it was a focus hang.

Guards: dry run by default (--apply to write), idempotency markers checked
FIRST, every anchor must occur exactly once (EOL-adaptive), brace balance
preserved, previous versions' changes asserted to survive.
"""

import os
import sys
import time

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

T = "\t"

# ---------------------------------------------------------------- idempotency
MARKERS = [
    "FocusAllowsPresenting",
    "v0.71: focus/occlusion sample",
    "v0.71: never block in Present",
    "v0.71: an unfocused/minimised window",
    "v0.71: one 200 ms slice per tick",
    "v0.71: a_enable=false tells the runtime",
    "v0.71: same guard as the DLSSG branch",
]

REPLACES = []

# =========================== Streamline.h ==================================
REPLACES.append(("Streamline.h", "H1: a_enable parameter on SetDLSSGOptions",
    T + T + "void SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,\n"
    + T + T + T + "std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat);\n",

    T + T + "// v0.71: a_enable=false tells the runtime to stop frame generation without\n"
    + T + T + "// touching any other option. Required when the window is not in the\n"
    + T + T + "// foreground: DLSS-G keeps presenting into the swap chain, and a\n"
    + T + T + "// FLIP_DISCARD swap chain whose buffers nobody releases blocks Present().\n"
    + T + T + "void SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,\n"
    + T + T + T + "std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat,\n"
    + T + T + T + "bool a_enable = true);\n"))

# =========================== Streamline.cpp ================================
REPLACES.append(("Streamline.cpp", "C1: definition + the off path",
    T + "void Streamline::SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,\n"
    + T + T + "std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat)\n"
    + T + "{\n"
    + T + T + "if (!initialized || !featureDLSSG || !slDLSSGSetOptions)\n"
    + T + T + T + "return;\n"
    + T + T + "sl::DLSSGOptions opts{};\n"
    + T + T + "opts.mode = sl::DLSSGMode::eOn;\n",

    T + "void Streamline::SetDLSSGOptions(std::uint32_t a_width, std::uint32_t a_height,\n"
    + T + T + "std::uint32_t a_mvecDepthW, std::uint32_t a_mvecDepthH, DXGI_FORMAT a_colorFormat,\n"
    + T + T + "bool a_enable)\n"
    + T + "{\n"
    + T + T + "if (!initialized || !featureDLSSG || !slDLSSGSetOptions)\n"
    + T + T + T + "return;\n"
    + T + T + "// v0.71: the \"window cannot be shown\" path. Mode only, and an early return:\n"
    + T + T + "// the multiplier ladder below must not run here, or every alt-tab would\n"
    + T + T + "// consume probe steps and log false rejections. Called on the focus edge\n"
    + T + T + "// only, never per frame.\n"
    + T + T + "if (!a_enable) {\n"
    + T + T + T + "sl::DLSSGOptions off{};\n"
    + T + T + T + "off.mode = sl::DLSSGMode::eOff;\n"
    + T + T + T + "const sl::Result offRes = slDLSSGSetOptions(viewport, off);\n"
    + T + T + T + "SKSE::log::warn(\"[XRAY] DLSSG mode -> OFF (result {}): the window is not in \"\n"
    + T + T + T + T + "\"the foreground, so frame generation stops and Present uses DO_NOT_WAIT \"\n"
    + T + T + T + T + "\"until it comes back\", static_cast<int>(offRes));\n"
    + T + T + T + "return;\n"
    + T + T + "}\n"
    + T + T + "sl::DLSSGOptions opts{};\n"
    + T + T + "opts.mode = sl::DLSSGMode::eOn;\n"))

# =========================== DX12SwapChain.cpp =============================
REPLACES.append(("DX12SwapChain.cpp", "D1: focus helpers + globals",
    "void DX12SwapChain::StartWatchdog()\n",

    T + "// v0.71: can this window be presented to at all?\n"
    + T + "// A FLIP_DISCARD swap chain (BufferCount=3) blocks inside Present() until a\n"
    + T + "// queued buffer is released, and DXGI stops releasing buffers for a window that\n"
    + T + "// is occluded or in the background. Test the two cheap states that predict it\n"
    + T + "// instead of waiting to be told: minimised, or no longer the foreground window.\n"
    + T + "// Deliberately conservative -- if the hwnd is unknown we assume focus, because\n"
    + T + "// changing behaviour on a guess is worse than leaving the old path alone.\n"
    + T + "static std::atomic<int> g_lastFocus{ 1 };          // 1 = foreground (watchdog field)\n"
    + T + "static std::atomic<bool> g_focusOffSent{ false };  // DLSS-G off sent for this focus loss\n"
    + "\n"
    + T + "static bool FocusAllowsPresenting(HWND a_hwnd)\n"
    + T + "{\n"
    + T + T + "if (!a_hwnd)\n"
    + T + T + T + "return true;\n"
    + T + T + "if (::IsIconic(a_hwnd))\n"
    + T + T + T + "return false;\n"
    + T + T + "return ::GetForegroundWindow() == a_hwnd;\n"
    + T + "}\n"
    + "\n"
    + "void DX12SwapChain::StartWatchdog()\n"))

REPLACES.append(("DX12SwapChain.cpp", "D2: per-frame focus sample + off edge",
    T + T + "// v0.5.5: stage marker - pinpoint which D3D11/D3D12 call throws (E_INVALIDARG black screen debug)\n"
    + T + T + "m_stage = \"enter\";\n",

    T + T + "// v0.5.5: stage marker - pinpoint which D3D11/D3D12 call throws (E_INVALIDARG black screen debug)\n"
    + T + T + "m_stage = \"enter\";\n"
    + "\n"
    + T + T + "// v0.71: focus/occlusion sample, once per frame, BEFORE anything consumes it\n"
    + T + T + "// (lesson 58: a guard whose input is sampled downstream of itself can never be\n"
    + T + T + "// verified). The 23:40:22 session froze 55 ms after \"Game lost focus\", so this\n"
    + T + T + "// value is the first thing the next hang log will be read for.\n"
    + T + T + "const bool winFocused = FocusAllowsPresenting(swapChainDesc.OutputWindow);\n"
    + T + T + "g_lastFocus.store(winFocused ? 1 : 0);\n"
    + T + T + "{\n"
    + T + T + T + "static bool focusWasOn = true;\n"
    + T + T + T + "if (winFocused != focusWasOn) {\n"
    + T + T + T + T + "focusWasOn = winFocused;\n"
    + T + T + T + T + "SKSE::log::warn(\"[XRAY] FOCUS {} hwnd={} foreground={} iconic={} - frame \"\n"
    + T + T + T + T + T + "\"generation is bypassed and Present runs with DO_NOT_WAIT while the window \"\n"
    + T + T + T + T + T + "\"cannot be shown\", winFocused ? \"regained\" : \"lost\",\n"
    + T + T + T + T + T + "static_cast<const void*>(swapChainDesc.OutputWindow),\n"
    + T + T + T + T + T + "static_cast<const void*>(::GetForegroundWindow()),\n"
    + T + T + T + T + T + "swapChainDesc.OutputWindow ? static_cast<int>(::IsIconic(swapChainDesc.OutputWindow)) : -1);\n"
    + T + T + T + "}\n"
    + T + T + "}\n"
    + T + T + "if (!winFocused) {\n"
    + T + T + T + "// Exactly once per focus loss: stop the runtime before the queue fills up.\n"
    + T + T + T + "// Restoring is free - the normal path re-sends eOn on the next focused frame.\n"
    + T + T + T + "if (!g_focusOffSent.exchange(true) && dlssgMode)\n"
    + T + T + T + T + "fg.streamline.SetDLSSGOptions(swapChainDesc.Width, swapChainDesc.Height,\n"
    + T + T + T + T + T + "swapChainDesc.Width, swapChainDesc.Height, swapChainDesc.Format, false);\n"
    + T + T + "} else {\n"
    + T + T + T + "g_focusOffSent.store(false);\n"
    + T + T + "}\n"))

REPLACES.append(("DX12SwapChain.cpp", "D3: watchdog 200 ms ticks",
    T + T + T + "for (;;) {\n"
    + T + T + T + T + "for (int i = 0; i < 5; ++i) {   // 200 ms slices so stop is honoured quickly\n"
    + T + T + T + T + T + "if (self.watchdogStop.load())\n"
    + T + T + T + T + T + T + "return;\n"
    + T + T + T + T + T + "std::this_thread::sleep_for(std::chrono::milliseconds(200));\n"
    + T + T + T + T + "}\n",

    T + T + T + "// v0.71: one 200 ms slice per tick (was 5 x 200 ms = 1 Hz). A hang is only\n"
    + T + T + T + "// ever localised by the last line the watchdog managed to write, and at 1 Hz\n"
    + T + T + T + "// that line can sit a whole second -- about 40 frames -- behind the freeze.\n"
    + T + T + T + "// 200 ms puts it within ~8. STALLED stays at 1 Hz so the file stays readable.\n"
    + T + T + T + "int tick = 0;\n"
    + T + T + T + "for (;;) {\n"
    + T + T + T + T + "if (self.watchdogStop.load())\n"
    + T + T + T + T + T + "return;\n"
    + T + T + T + T + "std::this_thread::sleep_for(std::chrono::milliseconds(200));\n"
    + T + T + T + T + "++tick;\n"))

REPLACES.append(("DX12SwapChain.cpp", "D4: watchdog line gains focus=",
    T + T + T + T + "if (FILE* f = std::fopen(path.c_str(), \"a\")) {\n"
    + T + T + T + T + T + "std::fprintf(f, \"[%lld] frames=%llu silent=%lldms stage=%s%s\\n\",\n"
    + T + T + T + T + T + T + "nowMs, static_cast<unsigned long long>(frames), silent, self.lastStage(),\n"
    + T + T + T + T + T + T + "(lastEnd != 0 && warm && silent > 1500) ? \"   <== RENDER THREAD STALLED\" : \"\");\n"
    + T + T + T + T + T + "std::fflush(f);\n"
    + T + T + T + T + T + "std::fclose(f);\n"
    + T + T + T + T + "}\n",

    T + T + T + T + "if (FILE* f = std::fopen(path.c_str(), \"a\")) {\n"
    + T + T + T + T + T + "// v0.71: focus belongs in the stamp. A last line reading focus=0 is a\n"
    + T + T + T + T + T + "// window-presentation hang (see FocusAllowsPresenting), not a frame-loop stall.\n"
    + T + T + T + T + T + "const bool stalled = lastEnd != 0 && warm && silent > 1500;\n"
    + T + T + T + T + T + "std::fprintf(f, \"[%lld] frames=%llu silent=%lldms stage=%s focus=%d%s\\n\",\n"
    + T + T + T + T + T + T + "nowMs, static_cast<unsigned long long>(frames), silent, self.lastStage(),\n"
    + T + T + T + T + T + T + "g_lastFocus.load(),\n"
    + T + T + T + T + T + T + "(stalled && (tick % 5) == 0) ? \"   <== RENDER THREAD STALLED\" : \"\");\n"
    + T + T + T + T + T + "std::fflush(f);\n"
    + T + T + T + T + T + "std::fclose(f);\n"
    + T + T + T + T + "}\n"))

REPLACES.append(("DX12SwapChain.cpp", "D5: guard consumes focus",
    T + T + T + "const bool menuBlock =\n"
    + T + T + T + T + "fgOn && fg.settings.menuDisableFrameGen && fg.streamline.MenuIsOpen();\n"
    + T + T + T + "if (menuBlock) {\n",

    T + T + T + "const bool menuBlock =\n"
    + T + T + T + T + "fgOn && fg.settings.menuDisableFrameGen && fg.streamline.MenuIsOpen();\n"
    + T + T + T + "// v0.71: an unfocused/minimised window is the flip-model deadlock case, so it\n"
    + T + T + T + "// gets the same treatment as a menu: no frame generation, straight passthrough.\n"
    + T + T + T + "// The fail counter is cleared here too - otherwise a long alt-tab would hit\n"
    + T + T + T + "// dlssgFailCount > 120 and silently disable frame generation for the session.\n"
    + T + T + T + "const bool focusBlock = !winFocused;\n"
    + T + T + T + "if (menuBlock || focusBlock) {\n"))

REPLACES.append(("DX12SwapChain.cpp", "D6: dlssg Present DO_NOT_WAIT",
    T + T + T + "fg.streamline.PresentMarkerRenderEnd();\n"
    + T + T + T + "Get().streamline.PresentMarkerStart();\n"
    + T + T + T + "DX::ThrowIfFailed(swapChain->Present(0, Flags));\n"
    + T + T + T + "Get().streamline.PresentMarkerEnd();\n",

    T + T + T + "fg.streamline.PresentMarkerRenderEnd();\n"
    + T + T + T + "Get().streamline.PresentMarkerStart();\n"
    + T + T + T + "// v0.71: never block in Present. SwapEffect=FLIP_DISCARD with BufferCount=3\n"
    + T + T + T + "// makes Present wait for a queued buffer to be released, and DXGI stops\n"
    + T + T + T + "// releasing buffers for a window that is occluded or in the background.\n"
    + T + T + T + "// DO_NOT_WAIT turns that wait into DXGI_ERROR_WAS_STILL_DRAWING, which is the\n"
    + T + T + T + "// honest outcome for a frame nobody can see - and the difference between one\n"
    + T + T + T + "// dropped frame and a frozen game.\n"
    + T + T + T + "const HRESULT hrPresent = swapChain->Present(0,\n"
    + T + T + T + T + "Flags | (winFocused ? 0u : static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT)));\n"
    + T + T + T + "if (hrPresent != DXGI_ERROR_WAS_STILL_DRAWING)\n"
    + T + T + T + T + "DX::ThrowIfFailed(hrPresent);\n"
    + T + T + T + "Get().streamline.PresentMarkerEnd();\n"))

REPLACES.append(("DX12SwapChain.cpp", "D7: non-dlssg Present DO_NOT_WAIT",
    T + T + "Get().streamline.PresentMarkerStart();\n"
    + T + T + "DX::ThrowIfFailed(swapChain->Present(1, Flags));\n"
    + T + T + "Get().streamline.PresentMarkerEnd();\n",

    T + T + "Get().streamline.PresentMarkerStart();\n"
    + T + T + "// v0.71: same guard as the DLSSG branch - an unfocused window must not be able\n"
    + T + T + "// to block the render thread inside Present.\n"
    + T + T + "const HRESULT hrPresentFsr = swapChain->Present(1,\n"
    + T + T + T + "Flags | (winFocused ? 0u : static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT)));\n"
    + T + T + "if (hrPresentFsr != DXGI_ERROR_WAS_STILL_DRAWING)\n"
    + T + T + T + "DX::ThrowIfFailed(hrPresentFsr);\n"
    + T + T + "Get().streamline.PresentMarkerEnd();\n"))


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def write_text(path, s):
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def brace_delta(s):
    return s.count("{") - s.count("}")


def match_anchor(text, old):
    """Anchor matching that does not depend on guessing the file's line ending.

    Lesson 60: a bare \\n anchor silently matches 0 times in a CRLF file, and a
    bare \\r\\n anchor matches 0 times in an LF file. Try the literal first, then
    the swapped form, and report the count honestly if neither is unique.
    """
    if text.count(old) == 1:
        return old, 1
    alt = old.replace("\r\n", "\n") if "\r\n" in old else old.replace("\n", "\r\n")
    if text.count(alt) == 1:
        return alt, 1
    return old, text.count(old)


def main():
    apply_it = "--apply" in sys.argv
    files = sorted({f for f, _, _, _ in REPLACES})
    texts = {f: read_text(os.path.join(SRC, f)) for f in files}

    # ---- guard 1: idempotency, checked FIRST ------------------------------
    for m in MARKERS:
        for f in files:
            if m in texts[f]:
                print("REFUSED -- %s already contains marker: %s" % (f, m))
                return 1

    # ---- guard 2: every anchor unique -------------------------------------
    plan = []   # (file, label, old_effective, new)
    bad = False
    for f, label, old, new in REPLACES:
        eff, n = match_anchor(texts[f], old)
        print("%-20s %-42s anchor x%d" % (f, label, n))
        if n != 1:
            bad = True
        plan.append((f, label, eff, new))
    if bad:
        print("REFUSED -- an anchor is missing (0) or ambiguous (>1); nothing written")
        return 1

    # ---- guard 3: braces balanced before ---------------------------------
    for f in files:
        if brace_delta(texts[f]) != 0:
            print("REFUSED -- %s: braces already unbalanced (%d)" % (f, brace_delta(texts[f])))
            return 1

    # ---- guard 4: this patch needs exactly two swapChain->Present() sites -
    n_present = texts["DX12SwapChain.cpp"].count("swapChain->Present(")
    print("%-20s %-42s sites x%d" % ("DX12SwapChain.cpp", "swapChain->Present( sites", n_present))
    if n_present != 2:
        print("REFUSED -- expected exactly 2 Present() call sites, found %d" % n_present)
        return 1

    # ---- apply ------------------------------------------------------------
    for f in files:
        s = texts[f]
        before = len(s)
        for ff, label, old, new in plan:
            if ff != f:
                continue
            eol = "\r\n" if "\r\n" in texts[f] else "\n"
            new_eff = new if (eol == "\n") else new.replace("\n", "\r\n")
            assert s.count(old) == 1, "%s / %s: anchor went ambiguous mid-apply" % (f, label)
            s = s.replace(old, new_eff, 1)
        bd = brace_delta(s)
        if bd != 0:
            print("REFUSED after apply -- %s: brace delta %d" % (f, bd))
            return 1
        texts[f] = s
        print("%-20s %+6d bytes   brace delta %d" % (f, len(s) - before, bd))

    # ---- guard 5: line-split fingerprints + previous fixes must survive ---
    for f in files:
        flat = texts[f]
        for fp in ("au\tProbe", "\nto* ui", "Streamline::  "):
            if fp in flat:
                print("REFUSED -- %s: line-split fingerprint %r" % (f, fp))
                return 1

    dc = texts["DX12SwapChain.cpp"]
    for needle, label in (
            ("v0.69: NR x frame generation are mutually exclusive again.", "v0.69 NR comment"),
            ("const bool fgGeneratingNow =", "v0.69 fgGeneratingNow"),
            ("fg.settings.neuralRenderingEnabled && !fgGeneratingNow", "v0.69 NR gate"),
            ("fg.streamline.PollMenuState();", "v0.70 poll call"),
            ("v0.70: sample the menu state ONCE PER FRAME", "v0.70 poll comment")):
        assert dc.count(needle) == 1, "lost previous fix: " + label

    sl = texts["Streamline.cpp"]
    for needle, label in (
            ("bool Streamline::PollMenuState()", "v0.70 PollMenuState"),
            ("v0.69: literal-name fallback", "v0.69 marker"),
            ("const bool useDerived = false &&", "v0.69 derived off")):
        assert sl.count(needle) == 1, "lost previous fix: " + label

    # ---- guard 6: ordering - the sample must precede its consumer ---------
    i_sample = dc.index("const bool winFocused = FocusAllowsPresenting")
    i_guard = dc.index("const bool focusBlock = !winFocused;")
    i_present = dc.index("const HRESULT hrPresent = swapChain->Present(0,")
    if not (i_sample < i_guard < i_present):
        print("REFUSED -- ordering wrong: sample=%d guard=%d present=%d" % (i_sample, i_guard, i_present))
        return 1
    print("ordering OK: sample < guard < present")

    if not apply_it:
        print("\nDRY RUN -- nothing written. Re-run with --apply")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    for f in files:
        p = os.path.join(SRC, f)
        with open(p + ".bak-" + stamp, "w", encoding="utf-8", errors="surrogateescape", newline="") as b:
            b.write(read_text(p))
        write_text(p, texts[f])
        print("wrote %s (backup .bak-%s)" % (f, stamp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
