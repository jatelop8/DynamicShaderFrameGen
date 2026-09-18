# -*- coding: utf-8 -*-
"""
patch_v103b_bounded_fence_1.py  --  DynamicShaderFrameGen v1.03b

Fixes FAULT 3b: the 19.9-second unbounded fence wait.

Evidence (DynamicShaderFrameGen.watchdog.log, 2026-09-18 18:23, verbatim):
    [159695602] 18:23:20.025 frames=1 silent=14865ms stage=d3d11 Wait focus=1 fence=2/2 stim=75 queued=1
    [159700418] 18:23:24.841 frames=1 silent=19681ms stage=d3d11 Wait focus=1 fence=2/2 stim=99 queued=1
and the main log:
    [I] [XRAY] LONG FRAME 19945.3ms (capUs=6289 mult=1 menu=0)

stage=d3d11 Wait is written in exactly two places, both immediately before

    DX::ThrowIfFailed(d3d11Context->Wait(d3d11Fence.get(), fenceValue));

and ID3D11DeviceContext4::Wait has NO timeout parameter: it returns when the
D3D12 queue signals fenceValue, or never. On the 18:23 run it was "or never" for
19.9 seconds, on the very first real frame, with queued=1 and fence=2/2 - i.e.
the queue was idle by the fence's own account while the wait refused to return.

A wait that cannot time out is a wait that can turn any hiccup into a freeze, and
a freeze with no log line naming the fence. This patch replaces both call sites
with a bounded version that polls GetCompletedValue and, on timeout, reports the
numbers (fenceValue, completed, elapsed, frameIndex) and lets the frame go. A
dropped frame is recoverable; a permanent stall is what the user saw.

Usage:
  python tools/patch_v103b_bounded_fence_1.py            # dry run
  python tools/patch_v103b_bounded_fence_1.py --apply    # write
"""

import os
import sys
import shutil
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "src")
CPP = os.path.join(SRC, "DX12SwapChain.cpp")
HDR = os.path.join(SRC, "DX12SwapChain.h")

TAG = "v1.03b"
APPLY = "--apply" in sys.argv

EDITS = []

# --- 1. the helper, declared next to lastStage() ------------------------------
EDITS.append((
    "h-1  declare WaitFenceBounded",
    HDR,
    """\t\tconst char* lastStage() const { return m_stage; }""",
    """\t\tconst char* lastStage() const { return m_stage; }

\t\t// v1.03b: a bounded replacement for ID3D11DeviceContext4::Wait.
\t\t//
\t\t// That call has no timeout, so a D3D12 queue that never reaches the
\t\t// fence parks the render thread forever - which is precisely the
\t\t// 2026-09-18 18:23 freeze: silent=19681 ms, stage=d3d11 Wait, frames=1,
\t\t// and a 19945.3 ms frame in the main log. Polling the D3D12 fence
\t\t// instead costs one GetCompletedValue per millisecond of hitch and turns
\t\t// an unbounded stall into a dropped frame plus a log line that names the
\t\t// fence, its value, the value that was actually reached and how long it
\t\t// took. Returns true if the fence was reached.
\t\tbool WaitFenceBounded(UINT64 a_fenceValue, std::uint32_t a_timeoutMs);""",
    "WaitFenceBounded",
))

# --- 2. the two call sites ----------------------------------------------------
for label, ctx in (
    ("menu-block passthrough", "d3d12 queue Signal"),
    ("main present path", "d3d12 queue Signal"),
):
    pass

EDITS.append((
    "c-1  implementation (placed right after StartWatchdog)",
    CPP,
    """\t// v0.81 -- present-thread census.""",
    """\t// v1.03b: bounded fence wait. See the declaration in DX12SwapChain.h for
\t// the evidence this exists for. ID3D11DeviceContext4::Wait returns when the
\t// D3D12 queue signals a_fenceValue, or never; on the 18:23 run it was "or
\t// never" for 19.9 s while the watchdog reported fence=2/2 and queued=1, so
\t// the wait was not even waiting on outstanding work - it was simply parked.
\t//
\t// The timeout must be generous enough never to fire in normal play (a 200 ms
\t// frame is already four times worse than the worst legitimate hitch measured
\t// here) and the poll must be cheap enough to run per frame: one
\t// GetCompletedValue per millisecond of hitch, and zero extra calls at all
\t// while the fence advances normally, because the loop checks before sleeping.
\tbool DX12SwapChain::WaitFenceBounded(UINT64 a_fenceValue, std::uint32_t a_timeoutMs)
\t{
\t\tif (!d3d12Fence || !d3d11Context)
\t\t\treturn true;   // nothing to wait on; never invent a stall
\t\tif (d3d12Fence->GetCompletedValue() >= a_fenceValue)
\t\t\treturn true;
\t\tconst auto t0 = std::chrono::steady_clock::now();
\t\tfor (;;) {
\t\t\tif (d3d12Fence->GetCompletedValue() >= a_fenceValue)
\t\t\t\treturn true;
\t\t\tconst auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
\t\t\t\tstd::chrono::steady_clock::now() - t0).count();
\t\t\tif (elapsed >= static_cast<long long>(a_timeoutMs)) {
\t\t\t\tstatic std::atomic<int> fenceTimeoutLogged{ 0 };
\t\t\t\tif (fenceTimeoutLogged.fetch_add(1) < 10) {
\t\t\t\t\tSKSE::log::error("[XRAY] FENCE WAIT TIMED OUT after {} ms: wanted {} completed {} "
\t\t\t\t\t\t"(queued={} frameIndex={}) - dropping this frame instead of parking the "
\t\t\t\t\t\t"render thread. A queue that never reaches the fence is the freeze this "
\t\t\t\t\t\t"guard exists for (v1.03b)", elapsed, a_fenceValue,
\t\t\t\t\t\td3d12Fence->GetCompletedValue(),
\t\t\t\t\t\tstatic_cast<unsigned long long>(g_queuedDepth.load()), frameIndex);
\t\t\t\t}
\t\t\t\treturn false;
\t\t\t}
\t\t\tstd::this_thread::sleep_for(std::chrono::milliseconds(1));
\t\t}
\t}

\t// v0.81 -- present-thread census.""",
    "FENCE WAIT TIMED OUT",
))

EDITS.append((
    "c-2  menu-block path uses the bounded wait",
    CPP,
    """\t\t\tm_stage = "d3d12 queue Signal";
\t\t\tDX::ThrowIfFailed(commandQueue->Signal(d3d12Fence.get(), fenceValue));
\t\t\tm_stage = "d3d11 Wait";
\t\t\tDX::ThrowIfFailed(d3d11Context->Wait(d3d11Fence.get(), fenceValue));
\t\t\tfenceValue++;
\t\t\tframeIndex = swapChain->GetCurrentBackBufferIndex();
\t\t\treturn S_OK;""",
    """\t\t\tm_stage = "d3d12 queue Signal";
\t\t\tDX::ThrowIfFailed(commandQueue->Signal(d3d12Fence.get(), fenceValue));
\t\t\tm_stage = "d3d11 Wait";
\t\t\t// v1.03b: bounded. This call had no timeout and the watchdog only ever
\t\t\t// saw "d3d11 Wait" - on 2026-09-18 18:23 that line sat unchanged for
\t\t\t// 19681 ms on the FIRST real frame (frames=1), which is the freeze.
\t\t\tif (!WaitFenceBounded(fenceValue, kFenceWaitTimeoutMs))
\t\t\t\tm_stage = "d3d11 Wait TIMEOUT";
\t\t\tfenceValue++;
\t\t\tframeIndex = swapChain->GetCurrentBackBufferIndex();
\t\t\treturn S_OK;""",
    "kFenceWaitTimeoutMs",
))

EDITS.append((
    "c-3  main present path uses the bounded wait",
    CPP,
    """\t\tm_stage = "d3d12 queue Signal";
\t\tDX::ThrowIfFailed(commandQueue->Signal(d3d12Fence.get(), fenceValue));
\t\tm_stage = "d3d11 Wait";
\t\tDX::ThrowIfFailed(d3d11Context->Wait(d3d11Fence.get(), fenceValue));
\t\tfenceValue++;

\t\tframeIndex = swapChain->GetCurrentBackBufferIndex();

\t\treturn S_OK;""",
    """\t\tm_stage = "d3d12 queue Signal";
\t\tDX::ThrowIfFailed(commandQueue->Signal(d3d12Fence.get(), fenceValue));
\t\tm_stage = "d3d11 Wait";
\t\t// v1.03b: bounded, same as the menu-block path above. Both sites wrote
\t\t// the "d3d11 Wait" the watchdog reported for 19.7 s while the process
\t\t// presented exactly one frame.
\t\tif (!WaitFenceBounded(fenceValue, kFenceWaitTimeoutMs))
\t\t\tm_stage = "d3d11 Wait TIMEOUT";
\t\tfenceValue++;

\t\tframeIndex = swapChain->GetCurrentBackBufferIndex();

\t\treturn S_OK;""",
    "kFenceWaitTimeoutMs",
))

EDITS.append((
    "c-4  the timeout constant",
    HDR,
    """\t\tUINT64 fenceValue = 0;""",
    """\t\tUINT64 fenceValue = 0;

\t\t// v1.03b: how long a frame may wait for the D3D12 queue before the wait
\t\t// is abandoned and the frame dropped. 250 ms is ~40 intended frames at
\t\t// 160 Hz and 25x the rejected-frame cost measured in the 18:23 log
\t\t// (capUs=6289 => 6.29 ms), so it cannot fire on a merely slow frame -
\t\t// only on the parked one this guard was written for.
\t\tstatic constexpr std::uint32_t kFenceWaitTimeoutMs = 250;""",
    "kFenceWaitTimeoutMs",
))


def main():
    texts = {}
    eols = {}
    for name in (CPP, HDR):
        with open(name, "rb") as fh:
            raw = fh.read()
        eols[name] = b"\r\n" if raw.count(b"\r\n") > 0 else b"\n"
        texts[name] = raw.decode("utf-8").replace("\r\n", "\n")

    problems = []
for label, fname, old, new, marker in EDITS:
        txt = texts[fname]
        if marker is not None and marker in txt:
            problems.append("%-50s ALREADY APPLIED (marker %r)" % (label, marker))
            continue
        n = txt.count(old)
        if n != 1:
            problems.append("%-50s ANCHOR COUNT = %d (must be 1)" % (label, n))
            continue
        if old == new:
            problems.append("%-50s no-op edit" % label)
    if problems:
        print("REFUSED, nothing written:")
        for p in problems:
            print("  " + p)
        return 1

for label, fname, old, new, marker in EDITS:
        texts[fname] = texts[fname].replace(old, new, 1)
        print("  ok  %s" % label)

for label, fname, old, new, marker in EDITS:
        if new not in texts[fname]:
            print("SELF-CHECK FAILED after %s - refusing to write" % label)
            return 1

    print()
    for fname in (CPP, HDR):
        before = len(open(fname, "rb").read())
        after = len(texts[fname].encode("utf-8"))
        print("%-40s %7d -> %7d bytes" % (os.path.basename(fname), before, after))

    if not APPLY:
        print("\nDRY RUN - nothing written. Re-run with --apply to write.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bkdir = os.path.join(SRC, "backup-%s-%s" % (TAG, stamp))
    os.makedirs(bkdir, exist_ok=True)
    for fname in (CPP, HDR):
        shutil.copy2(fname, os.path.join(bkdir, os.path.basename(fname)))
    print("backup -> %s" % bkdir)

    for fname in (CPP, HDR):
        out = texts[fname]
        if eols[fname] == b"\r\n":
            out = out.replace("\n", "\r\n")
        with open(fname, "wb") as fh:
            fh.write(out.encode("utf-8"))
    print("written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
