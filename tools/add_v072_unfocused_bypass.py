#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.72: undo the harmful half of v0.71 and replace it with a bypass that cannot wedge.

WHY (all of it from the 00:03 run's watchdog file, which is append-only and therefore
still holds the evidence):

    run 7: 175 ticks / 34.9 s,  last frames=275,  max silent=25814 ms,
           last silent=4318 ms, focus=0, 3x "RENDER THREAD STALLED"

The render thread genuinely stopped and the process stayed alive long enough for the
watchdog to keep writing STALLED lines - that is "sound keeps playing, picture frozen".

What the stall line tells us: m_stage was "d3d11 Wait" - the last stage a *completed*
frame sets (it is set at the very end of Present and never reset). And
ID3D11DeviceContext4::Wait is documented as "equivalent to the Direct3D 12
ID3D12CommandQueue::Wait member function" - a GPU-side queued wait, it does not block
the CPU. So the frame finished; the thread then stopped somewhere in the engine.

Which leaves the two things v0.71 added, both wrong:

  1) DXGI_PRESENT_DO_NOT_WAIT on the normal path. This design DEPENDS on Present
     blocking. FLIP_DISCARD + BufferCount=3 means a full flip queue is what stops the
     CPU from running ahead of the GPU; DO_NOT_WAIT removes that back-pressure, and the
     very next thing this code does is reset a command allocator. Keeping the CPU
     bounded here is not an optimisation, it is the synchronisation.

  2) A mid-flight slDLSSGSetOptions(mode = eOff) fired from inside Present on the focus
     edge, plus a focusBlock that skips slEvaluateDLSSG while leaving the runtime in
     eOn for as long as the window stays unfocused. Both are unsupported mid-frame
     manipulations of a pacer that expects one evaluation per frame.

THE REPLACEMENT: while the window cannot be shown, do NOTHING that can block and NOTHING
that needs a present to complete. No interop copy, no slEvaluateDLSSG, no cross-queue
fence ping-pong - one present that must not wait, then return. Nobody can see those
frames, and with no work queued the pacer has nothing to wait for. This removes the
deadlock by construction instead of trying to out-run it.

Also added: the GPU-side fence completion values in the watchdog line. That is the one
number that separates "the queues stopped (wedge)" from "the GPU is fine, the render
thread is blocked in code" - next time there will be no guessing.

LF file, EOL-adaptive anchors. Dry run by default; --apply writes.
"""

import os
import shutil
import sys
import time

TARGET = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "src", "DX12SwapChain.cpp")

MARKERS = [
    "v0.72: while the window cannot be shown",
    "v0.72: the GPU-side timeline position",
    "unfocused bypass",
]

# ------------------------------------------------------------------ E1
E1_OLD = '''\t\tif (!winFocused) {
\t\t\t// Exactly once per focus loss: stop the runtime before the queue fills up.
\t\t\t// Restoring is free - the normal path re-sends eOn on the next focused frame.
\t\t\tif (!g_focusOffSent.exchange(true) && dlssgMode)
\t\t\t\tfg.streamline.SetDLSSGOptions(swapChainDesc.Width, swapChainDesc.Height,
\t\t\t\t\tswapChainDesc.Width, swapChainDesc.Height, swapChainDesc.Format, false);
\t\t} else {
\t\t\tg_focusOffSent.store(false);
\t\t}
'''

E1_NEW = '''\t\t// v0.72: while the window cannot be shown, touch NOTHING that can block and
\t\t// NOTHING that needs a present to finish. v0.71 tried to be clever here and it
\t\t// made things worse (00:03 run: render thread stalled 2.6 s after the window lost
\t\t// focus, watchdog wrote STALLED for 4.3 s while the process stayed alive):
\t\t//
\t\t//  * it fired slDLSSGSetOptions(mode = eOff) from inside Present - an unsupported
\t\t//    mid-flight mode switch on a pacer that expects one evaluation per frame;
\t\t//  * and it left a focusBlock that skipped slEvaluateDLSSG while the runtime was
\t\t//    still eOn.
\t\t//
\t\t// The real hazard is the fence ping-pong below: every frame queues
\t\t// d3d11 Signal -> d3d12 Wait -> d3d12 Signal -> d3d11 Wait. It assumes the D3D12
\t\t// queue can always finish a frame, which is exactly what a window nobody can
\t\t// present to breaks. So: no interop, no fences, no frame generation while
\t\t// unfocused - one present that cannot wait, then out. This removes the deadlock
\t\t// by construction rather than trying to out-run it.
\t\tif (!winFocused) {
\t\t\tm_stage = "unfocused bypass";
\t\t\t// The only place DO_NOT_WAIT is correct: nothing downstream of this present
\t\t\t// depends on the flip having happened, because nothing downstream exists.
\t\t\tif (swapChain) {
\t\t\t\tconst HRESULT hrOff = swapChain->Present(0,
\t\t\t\t\tFlags | static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT));
\t\t\t\tif (hrOff != DXGI_ERROR_WAS_STILL_DRAWING)
\t\t\t\t\tDX::ThrowIfFailed(hrOff);
\t\t\t\t// A flip may still have happened, so keep the buffer index honest for the
\t\t\t\t// frame that resumes the normal path.
\t\t\t\tframeIndex = swapChain->GetCurrentBackBufferIndex();
\t\t\t}
\t\t\treturn S_OK;   // FrameStamp stamps lastFrameEndMs on the way out
\t\t}
'''

# ------------------------------------------------------------------ E2
E2_OLD = '''\t\t\tconst HRESULT hrPresent = swapChain->Present(0,
\t\t\t\tFlags | (winFocused ? 0u : static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT)));
'''

E2_NEW = '''\t\t\t// v0.72: plain blocking Present again. With FLIP_DISCARD + 3 buffers this call
\t\t\t// is what bounds how far the CPU may run ahead of the GPU - and the next thing
\t\t\t// this function does is reset a command allocator. DO_NOT_WAIT (v0.71) removed
\t\t\t// that bound; the unfocused case never reaches here any more.
\t\t\tconst HRESULT hrPresent = swapChain->Present(0, Flags);
'''

# ------------------------------------------------------------------ E3
E3_OLD = '''\t\tconst HRESULT hrPresentFsr = swapChain->Present(1,
\t\t\tFlags | (winFocused ? 0u : static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT)));
'''

E3_NEW = '''\t\t// v0.72: same as the DLSSG branch - the unfocused path returns above, so this
\t\t// stays a plain blocking present.
\t\tconst HRESULT hrPresentFsr = swapChain->Present(1, Flags);
'''

# ------------------------------------------------------------------ E4
E4_OLD = '''\t\t\t// v0.71: an unfocused/minimised window is the flip-model deadlock case, so it
\t\t\t// gets the same treatment as a menu: no frame generation, straight passthrough.
\t\t\t// The fail counter is cleared here too - otherwise a long alt-tab would hit
\t\t\t// dlssgFailCount > 120 and silently disable frame generation for the session.
\t\t\tconst bool focusBlock = !winFocused;
\t\t\tif (menuBlock || focusBlock) {
'''

E4_NEW = '''\t\t\t// v0.72: no focus term here any more. An unfocused window never reaches this
\t\t\t// point - it returns from the dependency-free bypass near the top of Present,
\t\t\t// before any fence traffic.
\t\t\tif (menuBlock) {
'''

# ------------------------------------------------------------------ E5
E5_OLD = '''\t\t\t\t\t// v0.71: focus belongs in the stamp. A last line reading focus=0 is a
\t\t\t\t\t// window-presentation hang (see FocusAllowsPresenting), not a frame-loop stall.
\t\t\t\t\tconst bool stalled = lastEnd != 0 && warm && silent > 1500;
\t\t\t\t\tstd::fprintf(f, "[%lld] frames=%llu silent=%lldms stage=%s focus=%d%s\\n",
\t\t\t\t\t\tnowMs, static_cast<unsigned long long>(frames), silent, self.lastStage(),
\t\t\t\t\t\tg_lastFocus.load(),
\t\t\t\t\t\t(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
'''

E5_NEW = '''\t\t\t\t\t// v0.72: the GPU-side timeline position. Two read-only queries, safe
\t\t\t\t\t// from this thread. They are what separates the two ways a stall can end:
\t\t\t\t\t//   both numbers frozen -> the queues stopped (cross-queue / driver wedge)
\t\t\t\t\t//   both numbers moving -> the GPU is fine, the render thread is blocked
\t\t\t\t\t//                          in CPU-side code
\t\t\t\t\t// UINT64_MAX means the device is lost / the fence is gone.
\t\t\t\t\tconst unsigned long long fence11 = self.d3d11Fence
\t\t\t\t\t\t? static_cast<unsigned long long>(self.d3d11Fence->GetCompletedValue()) : ~0ull;
\t\t\t\t\tconst unsigned long long fence12 = self.d3d12Fence
\t\t\t\t\t\t? static_cast<unsigned long long>(self.d3d12Fence->GetCompletedValue()) : ~0ull;
\t\t\t\t\t// v0.71: focus belongs in the stamp - focus=0 with a stall is a window
\t\t\t\t\t// that could not present, not a frame loop that died on its own.
\t\t\t\t\tconst bool stalled = lastEnd != 0 && warm && silent > 1500;
\t\t\t\t\tstd::fprintf(f, "[%lld] frames=%llu silent=%lldms stage=%s focus=%d "
\t\t\t\t\t\t"fence=%llu/%llu%s\\n",
\t\t\t\t\t\tnowMs, static_cast<unsigned long long>(frames), silent, self.lastStage(),
\t\t\t\t\t\tg_lastFocus.load(), fence11, fence12,
\t\t\t\t\t\t(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
'''

# ------------------------------------------------------------------ E6
E6_OLD = '''\tstatic std::atomic<bool> g_focusOffSent{ false };  // DLSS-G off sent for this focus loss
'''

E6_NEW = ''  # v0.72: the only callers were the v0.71 focus path, now gone.

EDITS = [
    ("E1 unfocused bypass replaces the DLSS-G off-send", E1_OLD, E1_NEW),
    ("E2 dlssg Present: plain blocking Present", E2_OLD, E2_NEW),
    ("E3 FSR Present: plain blocking Present", E3_OLD, E3_NEW),
    ("E4 menu guard: drop focusBlock", E4_OLD, E4_NEW),
    ("E5 watchdog: GPU fence values", E5_OLD, E5_NEW),
    ("E6 drop g_focusOffSent", E6_OLD, E6_NEW),
]

POST = [
    ("DXGI_PRESENT_DO_NOT_WAIT", 1),     # only the bypass present
    ("swapChain->Present(", 3),           # bypass + dlssg + fsr
    # NOTE: assert on the CODE, not on the bare word. The E1 comment explains why
    # focusBlock was removed, so "focusBlock" itself legitimately survives once -
    # a canary that also matches your own explanation is a canary that always fires.
    ("const bool focusBlock = !winFocused;", 0),
    ("if (menuBlock || focusBlock) {", 0),
    ("g_focusOffSent", 0),
    ("unfocused bypass", 1),
    ("fence11", 2),
    ("swapChain->Present(0, Flags)", 1),
    ("swapChain->Present(1, Flags)", 1),
]

# the earlier rounds must still be alive
SURVIVE = [
    ("v0.70: sample the menu state ONCE PER FRAME", "v0.70 menu sample"),
    ("fg.streamline.PollMenuState();", "PollMenuState call"),
    ("fg.settings.neuralRenderingEnabled && !fgGeneratingNow", "v0.69 NR gate"),
    ("++fg.streamline.frameSerial;", "v0.58 per-frame serial"),
    ("focus=%d", "v0.71 focus field"),
    ("static bool FocusAllowsPresenting(HWND a_hwnd)", "v0.71 focus helper"),
]


def eol_fit(anchor, text):
    if anchor in text:
        return anchor
    for a, b in (("\r\n", "\n"), ("\n", "\r\n")):
        if anchor.replace(a, b) in text:
            return anchor.replace(a, b)
    return None


def main():
    apply_it = "--apply" in sys.argv

    with open(TARGET, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"

    print("target: %s" % TARGET)
    print("bytes before: %d  (EOL=%s)" % (len(raw), "CRLF" if eol == "\r\n" else "LF"))
    print()

    for m in MARKERS:
        if m in text:
            print("REFUSED -- already applied (marker %r)" % m)
            return 2

    for needle, label in SURVIVE:
        c = text.count(needle)
        if c != 1:
            print("REFUSED -- earlier round missing: %s (%r x%d)" % (label, needle, c))
            return 2

    # brace balance BEFORE
    b0 = text.count("{") - text.count("}")
    n_present_before = text.count("swapChain->Present(")

    planned = []
    ok = True
    for label, old, new in EDITS:
        o = old.replace("\n", eol)
        n = text.count(o)
        if n != 1:
            print("%-52s anchor x%d  <== REFUSED" % (label, n))
            ok = False
            continue
        planned.append((label, o, new.replace("\n", eol)))
        print("%-52s anchor x1" % label)

    if not ok:
        print("\nREFUSED, nothing written.")
        return 2

    out = text
    for _l, o, n in planned:
        out = out.replace(o, n, 1)

    bad = []
    for needle, want in POST:
        got = out.count(needle)
        if got != want:
            bad.append("%r count=%d want=%d" % (needle, got, want))
    b1 = out.count("{") - out.count("}")
    if b1 != b0:
        bad.append("brace delta %d -> %d" % (b0, b1))
    if bad:
        print()
        for b in bad:
            print("POST FAIL: %s" % b)
        print("REFUSED, nothing written.")
        return 2

    # ordering: the bypass must be reachable before any fence traffic
    i_byp = out.index("unfocused bypass")
    i_sig = out.index('m_stage = "d3d11 Signal(fence)"')
    i_pres = out.index("swapChain->Present(0, Flags)")
    if not (i_byp < i_sig < i_pres):
        print("ORDER FAIL: bypass %d, d3d11 Signal %d, present %d" % (i_byp, i_sig, i_pres))
        return 2

    print()
    print("brace delta %d (0 expected) | ordering OK: bypass < Signal(fence) < Present" % (b1 - b0))
    print("post-conditions: %d checks OK" % len(POST))
    print("%+d bytes" % (len(out.encode("utf-8")) - len(raw)))

    if not apply_it:
        print()
        print("DRY RUN -- nothing written. Re-run with --apply")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = TARGET + ".bak-" + stamp
    shutil.copy2(TARGET, backup)
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))

    # read back from disk; never trust the in-memory copy
    back = open(TARGET, "rb").read().decode("utf-8")
    for needle, want in POST:
        got = back.count(needle)
        if got != want:
            print("READBACK FAIL: %r count=%d want=%d" % (needle, got, want))
            return 3
    bb = open(TARGET, "rb").read()
    crlf = bb.count(b"\r\n")
    lone_lf = bb.count(b"\n") - crlf
    lone_cr = bb.count(b"\r") - crlf
    print("readback OK | CRLF=%d lone_LF=%d lone_CR=%d" % (crlf, lone_lf, lone_cr))
    print("wrote %s (backup %s)" % (TARGET, os.path.basename(backup)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
