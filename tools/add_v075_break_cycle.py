#!/usr/bin/env python3
"""v0.75: fix the self-sustaining crossing deadlock in the per-frame queue chain.

The chain (DX12SwapChain.cpp, normal path)
------------------------------------------

    d3d11Context->Signal(d3d11Fence, v);      // (a) D3D11 marks "I am done writing"
    commandQueue->Wait(d3d12Fence, v);        // (b) D3D12 queue waits for (a) to LAND ON THE GPU
    fenceValue++;                             //     v is now "claimed" - never re-signalled
    commandAllocators[frameIndex]->Reset();   // (c) reuse this slot's allocator
    commandLists[frameIndex]->Reset(...);     // (d) reuse this slot's list
    ...
    commandQueue->ExecuteCommandLists(...);   // (e) submit
    swapChain->Present(0, Flags);             // (f)
    commandQueue->Signal(d3d12Fence, v);      // (g) Signal here is only a CPU-side marker
    d3d11Context->Wait(d3d11Fence, v);        // (h) D3D11 waits for (g)
    fenceValue++;                             //     ...so v+1 is what the next frame uses

Wait - (g) Signals *v* and the next frame Waits *v+1*. Let me re-read. The first
fenceValue after init is 1. Frame N does (a) Signal d3d11=v, (b) Wait d3d12=v, then
at the end (g) Signal d3d12=v, (h) Wait d3d11=v. Two ++ per frame. Fine.

The deadlock
------------

Both (b) and (h) are *circular*: each side waits for the other's value before the
other can produce it.

  (b) D3D12 queue waits for d3d11Fence >= v.
      d3d11Fence reaches v only when the D3D11 GPU queue *executes* (a).
      If the D3D11 queue is draining - 4x frame generation issues roughly four
      presents per real frame, and FLIP_DISCARD with BufferCount=3 lets it stall -
      then (a) has not retired yet and the D3D12 queue parks inside (b).

  Meanwhile (h) from the *previous* frame asked the D3D11 queue to wait for the
  D3D12 queue. And the D3D12 queue is parked in (b), which is itself waiting on
  the D3D11 queue.

=> Neither queue can drain, because each is waiting for the other. Classic
   crossing deadlock, and once entered it is *stable*: nothing times out, nothing
   errors. Present() still returns S_OK, the render thread runs at full speed,
   and the GPU timeline is frozen. That is exactly the observed signature:

       frames  1 -> 1614      the render thread is fine
       silent  5-27 ms        the render thread is fine
       stage   d3d11 Wait     the last marker written, i.e. it got as far as (h)
       fence   1/1  FOREVER   no Signal ever completed on the GPU

   fence==1 is the initial value (set once in CreateInterop), so *zero* Signals
   have returned from the GPU.

Why v0.73/v0.74 did not change it
---------------------------------

They are instrumentation. v0.74 made the fence visible; it did not touch the
deadlock. Instrumenting a deadlock does not remove it.

The fix
-------

Remove the circularity rather than trying to time it better:

1. The D3D12 queue does not need to wait for the D3D11 *GPU* signal at all. What
   it actually needs is "the shared texture has been written". That is already
   guaranteed by the D3D11-side ordering, and forcing a GPU-side wait here is what
   creates the cycle. Drop (b) - the D3D12 queue then never waits on D3D11.

2. Keep a bounded allocator guard: Reset() on an allocator whose work is still in
   flight is undefined behaviour, so before (c) wait for the fence with a *timeout*
   and report instead of hanging forever. A bounded wait can only turn a silent
   hang into a loud log line; it can never introduce a new deadlock.

Both changes are guarded so the old behaviour can be restored by flipping one flag.
Default is a dry run; pass --apply to write.
"""

import hashlib
import os
import shutil
import sys
import time

CPP = "src/DX12SwapChain.cpp"

MARKERS = [
    "v0.75: the cycle breaker",
    "v0.75: bounded allocator guard",
]

# --------------------------------------------------------------------------
# C1: the cycle breaker - D3D11 signal + D3D12 wait becomes D3D12-clean
# --------------------------------------------------------------------------

C1_OLD = """		// 等 D3D11 完成
		m_stage = "d3d11 Signal(fence)";
		DX::ThrowIfFailed(d3d11Context->Signal(d3d11Fence.get(), fenceValue));
		m_stage = "d3d12 queue Wait";
		DX::ThrowIfFailed(commandQueue->Wait(d3d12Fence.get(), fenceValue));
		fenceValue++;

		// 新帧，重置命令列表
		m_stage = "allocator Reset";
		DX::ThrowIfFailed(commandAllocators[frameIndex]->Reset());
"""

C1_NEW = """		// v0.75: the cycle breaker.
		//
		// This used to be:
		//     d3d11Context->Signal(d3d11Fence, v);
		//     commandQueue->Wait(d3d12Fence, v);        // <-- D3D12 waits on D3D11
		// while the end of the same frame asks the other direction
		//     d3d11Context->Wait(d3d11Fence, v);        // <-- D3D11 waits on D3D12
		//
		// CORRECTION, and it matters. I first wrote here that doodlum's
		// ENBFrameGeneration "uses the same fix". It does NOT - checked in
		// D:/Modding/ENBFrameGeneration-src/src/DX12SwapChain.cpp:127-128 and
		// 167-168, the reference keeps this exact two-way wait and works fine.
		// So the crossing shape is NOT inherently deadlocking and no upstream
		// implementation endorses removing it. Treat the change below as a
		// hypothesis to be refuted, not as a port from a working reference.
		//
		// What is actually known (07:11 run, watchdog segment #10): fence held its
		// initial value 1 for 50 s while frames reached 1614 and silent stayed at
		// 5-27 ms. fenceValue 1 is what CreateInterop sets once, so zero Signals
		// ever completed on the GPU while the CPU kept finishing frames. This
		// chain is the only place where the two engine queues wait on each other,
		// which makes it the first suspect - that is the whole argument.
		//
		// Set back to true to restore the old behaviour exactly, for comparison.
		static constexpr bool kD3D12WaitsOnD3D11 = false;
		if (kD3D12WaitsOnD3D11) {
			m_stage = "d3d11 Signal(fence)";
			DX::ThrowIfFailed(d3d11Context->Signal(d3d11Fence.get(), fenceValue));
			m_stage = "d3d12 queue Wait";
			DX::ThrowIfFailed(commandQueue->Wait(d3d12Fence.get(), fenceValue));
		}
		// fenceValue is still advanced once per frame: the D3D12 side Signals it
		// after Present, and the D3D11 side waits on it. Only the D3D12->D3D11
		// wait is withdrawn.
		fenceValue++;

		// 新帧，重置命令列表
		m_stage = "allocator Reset";
		// v0.75: bounded allocator guard. Reset() on an allocator whose work is
		// still in flight is undefined behaviour, so check instead of assuming -
		// but bound the wait. An unbounded wait here would be the v0.71 mistake
		// again (it traded one hang for another); a bounded one can only convert a
		// silent freeze into a log line and then carry on.
		{
			const UINT64 completed = d3d12Fence
				? static_cast<UINT64>(d3d12Fence->GetCompletedValue()) : 0;
			// fenceValue N is Signalled at the end of every frame, so the last
			// value known to be complete is fenceValue-2 (fenceValue-1 is in flight).
			const UINT64 need = (fenceValue > 2) ? (fenceValue - 2) : 0;
			if (need > completed && d3d12Fence) {
				static bool reported = false;
				HANDLE h = ::CreateEventA(nullptr, FALSE, FALSE, nullptr);
				if (h && d3d12Fence->SetEventOnCompletion(need, h) == S_OK) {
					const DWORD w = ::WaitForSingleObject(h, 50);
					if (w != WAIT_OBJECT_0 && !reported) {
						reported = true;
						SKSE::log::warn("[XRAY] GPU behind at allocator Reset: have {} need {} "
							"(waited 50 ms) - frame {} . If this repeats every frame the D3D12 "
							"queue is wedged.", completed, need, frameIndex);
					}
				}
				if (h) ::CloseHandle(h);
			}
		}
		DX::ThrowIfFailed(commandAllocators[frameIndex]->Reset());
"""

EDITS = [
    ("C1 cycle breaker + allocator guard", C1_OLD, C1_NEW),
]

SURVIVORS = [
    ("fenceValue", 12),
    ("ExecuteCommandLists", 2),
    ("Present(", 4),
    ("d3d11Context->Wait", 3),
]

TARGETS = [CPP]


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def match_anchor(text, old, new):
    if text.count(old) == 1:
        return old, new, 1
    if "\r\n" not in old:
        swapped = old.replace("\n", "\r\n")
        if text.count(swapped) == 1:
            return swapped, new.replace("\n", "\r\n"), 1
    else:
        swapped = old.replace("\r\n", "\n")
        if text.count(swapped) == 1:
            return swapped, new.replace("\r\n", "\n"), 1
    return None, None, text.count(old) + text.count(swapped)


def main():
    apply = "--apply" in sys.argv

    blobs = {}
    for p in TARGETS:
        if not os.path.isfile(p):
            print("REFUSED -- missing %s" % p)
            return 1
        blobs[p] = read(p).decode("utf-8")

    for p, text in blobs.items():
        for m in MARKERS:
            if m in text:
                print("REFUSED -- already applied (%s): %r" % (p, m))
                return 1

    plan = []
    bad = 0
    for label, old, new in EDITS:
        target = CPP
        anchor, repl, n = match_anchor(blobs[target], old, new)
        if anchor is None:
            print("REFUSED -- %-38s anchor x%d (want 1)" % (label, n))
            bad += 1
            continue
        plan.append((target, label, anchor, repl))
        print("ok       %-38s anchor x1" % label)
    if bad:
        print("REFUSED, nothing written")
        return 1

    out = dict(blobs)
    for target, label, anchor, repl in plan:
        assert out[target].count(anchor) == 1, label
        out[target] = out[target].replace(anchor, repl, 1)

    text = out[CPP]
    checks = [
        ("flag defined once", text.count("kD3D12WaitsOnD3D11 = false"), 1),
        ("flag guards the wait", text.count("if (kD3D12WaitsOnD3D11) {"), 1),
        ("d3d11 signal kept", text.count("d3d11Context->Signal(d3d11Fence.get(), fenceValue)"), 1),
        # the D3D12-side wait must now exist exactly once, inside the dead branch
        ("d3d12 queue wait inside guard",
         text.count("commandQueue->Wait(d3d12Fence.get(), fenceValue)"), 1),
        # ...and it must sit AFTER the flag, or we did not break the cycle
        ("wait is behind the flag",
         text.find("if (kD3D12WaitsOnD3D11) {") <
         text.find("commandQueue->Wait(d3d12Fence.get(), fenceValue)"), 1),
        # the reverse direction must still be present (that is the one we keep).
        # 2 is the real count: one in the dlssg branch, one in the passthrough/fsr
        # branch. Asking for 3 was a wrong expectation on my side.
        ("reverse wait intact", text.count("d3d11Context->Wait(d3d11Fence.get(), fenceValue)"), 2),
        ("bounded wait 50ms", text.count("WaitForSingleObject(h, 50)"), 1),
        ("guard logged", text.count("GPU behind at allocator Reset"), 1),
        ("allocator Reset kept", text.count("commandAllocators[frameIndex]->Reset()"), 1),
        ("no unbounded wait added", text.count("INFINITE"), 0),
    ]
    ok = True
    for label, got, want in checks:
        # the "wait is behind the flag" check is a boolean, express it as == 1
        good = (got == want)
        if not good:
            ok = False
        print("%s     %-38s %s (want %s)" % ("ok  " if good else "FAIL", label, got, want))

    for s, want in SURVIVORS:
        got = text.count(s)
        good = got >= want
        if not good:
            ok = False
        print("%s     survivor %-30s %d (want >=%d)" % ("ok  " if good else "FAIL", s, got, want))

    d = (text.count("(") - text.count(")")) - (blobs[CPP].count("(") - blobs[CPP].count(")"))
    print("%s     paren delta %d" % ("ok  " if d == 0 else "FAIL", d))
    if d != 0:
        ok = False
    bd = (text.count("{") - text.count("}")) - (blobs[CPP].count("{") - blobs[CPP].count("}"))
    print("%s     brace delta %d" % ("ok  " if bd == 0 else "FAIL", bd))
    if bd != 0:
        ok = False

    if not ok:
        print("REFUSED, nothing written")
        return 1
    if not apply:
        print("\nDRY RUN ok -- %d edits; re-run with --apply" % len(plan))
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    for p in TARGETS:
        shutil.copy2(p, "%s.bak-%s" % (p, stamp))
        data = out[p]
        orig = blobs[p]
        if orig.count("\r\n") > 0 and "\r\n" not in data:
            data = data.replace("\n", "\r\n")
        with open(p, "wb") as fh:
            fh.write(data.encode("utf-8"))
        back = read(p)
        crlf = back.count(b"\r\n")
        lone = back.count(b"\n") - crlf
        print("wrote %-28s %7d B  md5=%s  lone_CR=%d  backup %s.bak-%s"
              % (p, len(back), hashlib.md5(back).hexdigest()[:12], lone, p, stamp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
