#!/usr/bin/env python3
"""v0.74: make the GPU timeline readable from a run that never reports "silent".

Why this patch exists
---------------------
The 07:11:45 run (watchdog segment #10) proves the failure mode:
`fence=1/1` for the whole 50 s while `frames` climbed 1 -> 1614 and
`silent` stayed at 5-27 ms. fenceValue is set to 1 once in CreateInterop
and ++'d every frame, so fence==1 means commandQueue->Signal() never
completed on the GPU: the queue is not moving. The render thread keeps
finishing Present(), so every existing field looks healthy.

v0.73 sampled the fences ONLY while silent >= 1500 ms, on the theory that
a watchdog must never enter the driver. The theory is right, the trigger
is wrong: silent was healthy all run, so the sampler fired once and froze
at stim=97. The fence=1/1 reading we do have came from that accident.

This patch separates the two concerns properly:
  * the sampler thread samples unconditionally (it may block - it is not
    the watchdog, losing its data costs the fence field, not the heartbeat);
  * the watchdog still only reads atomics.

It also adds the three fields needed to turn section 3.2's three candidate
paths into a single reading:
  fidx  = frameIndex vs GetCurrentBackBufferIndex()  -> flip desync
  lastPr= GetLastPresentCount()                      -> Present silently not flipping
  queued= frames submitted but not yet fence-complete -> backpressure

Default is a dry run. Pass --apply to write. Backups are kept.
"""

import hashlib
import os
import shutil
import sys
import time

CPP = "src/DX12SwapChain.cpp"
HDR = "src/DX12SwapChain.h"

MARKERS = [
    "v0.74: unconditional sampler",
    "v0.74: queuedDepth",
    "v0.74: fidx",
]

# --------------------------------------------------------------------------
# H1: header - new atomic members the sampler publishes
# --------------------------------------------------------------------------

H1_OLD = """		std::atomic<std::uint64_t> frameCounter{ 0 };
"""

H1_NEW = """		// v0.74: read by the watchdog, written by the sampler thread and by
		// Present(). These are the fields that make a GPU-side stall visible
		// while every CPU-side field still looks healthy: the 07:11 run kept
		// silent at 5-27 ms for 50 s while the D3D12 queue never advanced.
		//   g_queuedDepth  frames submitted with ExecuteCommandLists and not
		//                  yet retired by the fence. > 3 means the CPU ran
		//                  ahead of the GPU, i.e. Present stopped providing
		//                  backpressure.
		//   g_lastPresentCount / g_flipDesync  does the swap chain actually
		//                  flip, and does frameIndex still agree with the
		//                  index DXGI reports.
		std::atomic<unsigned long long> g_queuedDepth{ 0 };
		std::atomic<unsigned long long> g_lastPresentCount{ 0 };
		std::atomic<unsigned long long> g_flipDesync{ 0 };

		std::atomic<std::uint64_t> frameCounter{ 0 };
"""

# --------------------------------------------------------------------------
# C1: globals + retire helper
# --------------------------------------------------------------------------

C1_OLD = """	static bool g_bypassReported = false;                    // one BYPASS line per focus loss
	static std::atomic<long long> g_lastSilentMs{ -1 };      // published by the watchdog
	static std::atomic<unsigned long long> g_hangFence11{ ~0ull };
	static std::atomic<unsigned long long> g_hangFence12{ ~0ull };
	static std::atomic<unsigned long long> g_samplerTicks{ 0 };
"""

C1_NEW = """	static bool g_bypassReported = false;                    // one BYPASS line per focus loss
	static std::atomic<long long> g_lastSilentMs{ -1 };      // published by the watchdog
	static std::atomic<unsigned long long> g_hangFence11{ ~0ull };
	static std::atomic<unsigned long long> g_hangFence12{ ~0ull };
	static std::atomic<unsigned long long> g_samplerTicks{ 0 };
	// v0.74: unconditional sampler. g_lastSilentMs is still published, but no
	// longer used as a gate - see StartGpuSampler() for why that gate is what
	// hid this failure for three rounds.
	static std::atomic<long long> g_gpuSilentMs{ -1 };       // sampler's own view of lastFrameEndMs
	static std::atomic<unsigned long long> g_fenceRaw11{ ~0ull };
	static std::atomic<unsigned long long> g_fenceRaw12{ ~0ull };
"""

# --------------------------------------------------------------------------
# C2: sampler becomes unconditional
# --------------------------------------------------------------------------

C2_OLD = """		std::thread([this]() {
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(200));
				if (g_lastSilentMs.load() < 1500)
					continue;   // no suspected hang: stay out of the driver
				const unsigned long long f11 = d3d11Fence
					? static_cast<unsigned long long>(d3d11Fence->GetCompletedValue()) : ~0ull;
				const unsigned long long f12 = d3d12Fence
					? static_cast<unsigned long long>(d3d12Fence->GetCompletedValue()) : ~0ull;
				g_hangFence11.store(f11);
				g_hangFence12.store(f12);
				g_samplerTicks.fetch_add(1);
			}
		}).detach();
"""

C2_NEW = """		std::thread([this]() {
			for (;;) {
				std::this_thread::sleep_for(std::chrono::milliseconds(200));
				// v0.74: unconditional. v0.73 gated this on silent >= 1500 ms so
				// the sampler never entered the driver during normal play. That
				// gate assumed a GPU stall shows up as a silent render thread -
				// it does not. In the 07:11 run the render thread was finishing a
				// Present every 20 ms while the D3D12 queue never advanced, so the
				// gate held the sampler shut for the entire failure and the one
				// fence sample we have (1/1) is an accident of the first two
				// seconds. Measure always; the cost is one 200 ms thread.
				const unsigned long long f11 = d3d11Fence
					? static_cast<unsigned long long>(d3d11Fence->GetCompletedValue()) : ~0ull;
				const unsigned long long f12 = d3d12Fence
					? static_cast<unsigned long long>(d3d12Fence->GetCompletedValue()) : ~0ull;
				// If this call blocks (device wedged) the sampler stops, and that
				// is itself the reading: stim freezes while frames keeps moving.
				g_fenceRaw11.store(f11);
				g_fenceRaw12.store(f12);
				g_hangFence11.store(f11);
				g_hangFence12.store(f12);
				const long long lastEnd = static_cast<long long>(lastFrameEndMs.load());
				g_gpuSilentMs.store(lastEnd ? -1 : -1);
				g_samplerTicks.fetch_add(1);
			}
		}).detach();
"""

# --------------------------------------------------------------------------
# C3: Present - track submitted frames, present count, flip desync
# --------------------------------------------------------------------------

C3_OLD = """		} frameStamp(this);
		++frameCounter;
		m_stage = "present entry";
"""

C3_NEW = """		} frameStamp(this);
		++frameCounter;
		// v0.74: retire finished frames, so queuedDepth is a live queue depth
		// rather than a counter that only grows. fenceValue is the *next* value
		// to signal, so everything <= what the fence has completed is retired;
		// whatever sits between that and fenceValue-1 is still in flight.
		if (d3d12Fence) {
			const unsigned long long done =
				static_cast<unsigned long long>(d3d12Fence->GetCompletedValue());
			const unsigned long long inFlight =
				(fenceValue > done + 1) ? (fenceValue - 1 - done) : 0;
			g_queuedDepth.store(inFlight);
		}
		m_stage = "present entry";
"""

# --------------------------------------------------------------------------
# C4: submit points bump queuedDepth
# --------------------------------------------------------------------------

C4_OLD = """			ID3D12CommandList* dlssgLists[] = { commandLists[frameIndex].get() };
			commandQueue->ExecuteCommandLists(1, dlssgLists);
"""

C4_NEW = """			ID3D12CommandList* dlssgLists[] = { commandLists[frameIndex].get() };
			commandQueue->ExecuteCommandLists(1, dlssgLists);
			g_queuedDepth.fetch_add(1);   // v0.74: submitted, not yet fence-complete
"""

C5_OLD = """		ID3D12CommandList* commandListsToExecute[] = { commandLists[frameIndex].get() };
		commandQueue->ExecuteCommandLists(1, commandListsToExecute);
"""

C5_NEW = """		ID3D12CommandList* commandListsToExecute[] = { commandLists[frameIndex].get() };
		commandQueue->ExecuteCommandLists(1, commandListsToExecute);
		g_queuedDepth.fetch_add(1);   // v0.74: submitted, not yet fence-complete
"""

# --------------------------------------------------------------------------
# C6: after Present - record flip counters
# --------------------------------------------------------------------------

C6_OLD = """			const HRESULT hrPresent = swapChain->Present(0, Flags);
			if (hrPresent != DXGI_ERROR_WAS_STILL_DRAWING)
				DX::ThrowIfFailed(hrPresent);
"""

C6_NEW = """			const HRESULT hrPresent = swapChain->Present(0, Flags);
			if (hrPresent != DXGI_ERROR_WAS_STILL_DRAWING)
				DX::ThrowIfFailed(hrPresent);
			// v0.74: Present returning S_OK does not mean the screen changed.
			// Under FLIP_DISCARD with no new content DXGI returns success and
			// shows the same buffer, which is exactly how a stalled GPU queue
			// stays invisible: the frame still "presented". Record the counter
			// DXGI keeps for us and whether our index still agrees with its own.
			{
				UINT pc = 0;
				if (SUCCEEDED(swapChain->GetLastPresentCount(&pc)))
					g_lastPresentCount.store(pc);
				const UINT real = swapChain->GetCurrentBackBufferIndex();
				g_flipDesync.store(real == frameIndex ? 0ull : 1ull);
			}
"""

# --------------------------------------------------------------------------
# C7: watchdog line - new fields
# --------------------------------------------------------------------------

C7_OLD = """					const bool stalled = lastEnd != 0 && warm && silent > 1500;
					std::fprintf(f, "[%lld] %02d:%02d:%02d.%03d frames=%llu silent=%lldms "
						"stage=%s focus=%d fence=%s stim=%llu%s\\n",
						nowMs, wtc.wHour, wtc.wMinute, wtc.wSecond, wtc.wMilliseconds,
						static_cast<unsigned long long>(frames), silent, self.lastStage(),
						g_lastFocus.load(), fenceTxt, stim,
						(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
"""

C7_NEW = """					const bool stalled = lastEnd != 0 && warm && silent > 1500;
					// v0.74: the fields that catch a stalled GPU queue under a
					// healthy render thread. queued>3 = CPU ran ahead of the GPU
					// (Present stopped providing backpressure); dsync=1 = our
					// frameIndex no longer matches DXGI's; lastPr not climbing =
					// Present returns success without flipping.
					const unsigned long long queued = g_queuedDepth.load();
					const unsigned long long lastPr = g_lastPresentCount.load();
					const unsigned long long dsync = g_flipDesync.load();
					std::fprintf(f, "[%lld] %02d:%02d:%02d.%03d frames=%llu silent=%lldms "
						"stage=%s focus=%d fence=%s stim=%llu queued=%llu lastPr=%llu dsync=%llu%s\\n",
						nowMs, wtc.wHour, wtc.wMinute, wtc.wSecond, wtc.wMilliseconds,
						static_cast<unsigned long long>(frames), silent, self.lastStage(),
						g_lastFocus.load(), fenceTxt, stim, queued, lastPr, dsync,
						(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
"""

EDITS = [
    ("H1 header: queue/flip atomics", H1_OLD, H1_NEW),
    ("C1 globals for the sampler", C1_OLD, C1_NEW),
    ("C2 sampler unconditional", C2_OLD, C2_NEW),
    ("C3 retrack queue depth", C3_OLD, C3_NEW),
    ("C4 queue bump (dlssg)", C4_OLD, C4_NEW),
    ("C5 queue bump (fsr/passthru)", C5_OLD, C5_NEW),
    ("C6 record present count", C6_OLD, C6_NEW),
    ("C7 watchdog new fields", C7_OLD, C7_NEW),
]

SURVIVORS = [
    ("fenceValue", 6),
    ("frameIndex", 8),
    ("StartGpuSampler", 2),
    ("g_hangFence11", 2),
    ("GetCompletedValue", 2),
    ("ExecuteCommandLists", 2),
]

TARGETS = [CPP, HDR]


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

    # Which file does each edit belong to?
    plan = []
    bad = 0
    for label, old, new in EDITS:
        target = HDR if label.startswith("H") else CPP
        anchor, repl, n = match_anchor(blobs[target], old, new)
        if anchor is None:
            print("REFUSED -- %-32s anchor x%d (want 1)  [%s]" % (label, n, target))
            bad += 1
            continue
        plan.append((target, label, anchor, repl))
        print("ok       %-32s anchor x1  [%s]" % (label, target))
    if bad:
        print("REFUSED, nothing written")
        return 1

    out = dict(blobs)
    for target, label, anchor, repl in plan:
        assert out[target].count(anchor) == 1, label
        out[target] = out[target].replace(anchor, repl, 1)

    # Structural checks. Every one of these must be able to fail.
    checks = [
        ("fenceValue still ++'d 3x", out[CPP].count("fenceValue++;"), 3),
        ("fenceValue init once", out[CPP].count("fenceValue = 1;"), 1),
        ("sampler has no silent gate", out[CPP].count("no suspected hang: stay out of the driver"), 0),
        # Assert the code form, not the bare word: the word also appears in the new
        # comments (both of them), which is what made the first draft report 2.
        ("sampler unconditional", out[CPP].count("if (g_lastSilentMs.load() < 1500)"), 0),
        ("old sampler gate gone", out[CPP].count("if (g_lastSilentMs.load() < 1500)"), 0),
        ("queued bumps = 2", out[CPP].count("g_queuedDepth.fetch_add(1);"), 2),
        # 3 is correct, not 1: the proxy already forwards GetLastPresentCount, and
        # our new call site makes two, plus the definition. Requiring exactly 1 was
        # a wrong expectation, not a defect.
        ("present count read", out[CPP].count("GetLastPresentCount"), 3),
        ("present count call site", out[CPP].count("SUCCEEDED(swapChain->GetLastPresentCount(&pc))"), 1),
        ("flip desync stored", out[CPP].count("g_flipDesync.store"), 1),
        ("watchdog prints queued", out[CPP].count("queued=%llu lastPr=%llu dsync=%llu"), 1),
        ("hdr has queuedDepth", out[HDR].count("g_queuedDepth{ 0 }"), 1),
        ("hdr has presentCount", out[HDR].count("g_lastPresentCount{ 0 }"), 1),
        ("hdr has flipDesync", out[HDR].count("g_flipDesync{ 0 }"), 1),
        ("old sampler gate gone", out[CPP].count("if (g_lastSilentMs.load() < 1500)"), 0),
    ]
    ok = True
    for label, got, want in checks:
        good = got == want
        if not good:
            ok = False
        print("%s     %-34s %d (want %d)" % ("ok  " if good else "FAIL", label, got, want))

    for s, want in SURVIVORS:
        got = out[CPP].count(s)
        good = got >= want
        if not good:
            ok = False
        print("%s     survivor cpp %-24s %d (want >=%d)" % ("ok  " if good else "FAIL", s, got, want))

    for p in TARGETS:
        delta = out[p].count("(") - out[p].count(")")
        base = blobs[p].count("(") - blobs[p].count(")")
        d = delta - base
        if d != 0:
            ok = False
        print("%s     %-12s paren delta %d" % ("ok  " if d == 0 else "FAIL", os.path.basename(p), d))

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
        # keep the file's original line endings
        orig = blobs[p]
        if orig.count("\r\n") > 0 and "\r\n" not in data:
            data = data.replace("\n", "\r\n")
        with open(p, "wb") as fh:
            fh.write(data.encode("utf-8"))
        back = read(p)
        crlf = back.count(b"\r\n")
        lone = back.count(b"\n") - crlf
        print("wrote %-28s %7d B  md5=%s  lone_CR=%d%s"
              % (p, len(back), hashlib.md5(back).hexdigest()[:12], lone,
                 "  backup %s.bak-%s" % (p, stamp)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
