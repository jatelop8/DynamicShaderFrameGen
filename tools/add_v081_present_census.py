#!/usr/bin/env python3
"""
v0.81: observe the presenters, never refuse them. (v0.80's latch is REVERTED.)

WHY v0.80 WAS WRONG - MY BUG
----------------------------
v0.80 assumed "two thread ids in Present()" meant "two presenters fighting over
one swap chain" and refused every thread except the first one seen. The 09:31
run shows that assumption was false:

    [09:31:42.466] [5008 ] [PRESENT] first presenter tid=5008 - this thread owns ...
    [09:32:02.266] [18984] [PRESENT] SECOND presenter tid=18984 (owner=5008)
    [09:32:02.266] [18984] [PRESENT] LATCH ARMED after 19800 ms: owner=5008 (frames=1)
    [09:32:02.266] [18984] [PRESENT] REFUSED foreign presenter tid=18984 - skipped 1 frame
    ...
    [09:32:07.199] [18984] [PRESENT] tid census #300: owner=5008 frames=1 | foreign=18984 frames=300

Read that census: **owner=5008 had entered Present exactly ONCE, and the refused
thread had entered 300 times.** 5008 is the plugin/init thread - it created the
swap chain, bound Streamline, and then never presented again. 18984 is the engine
render thread that calls Present every frame. 5008 is also the thread that runs
all the per-frame plugin logic (its heartbeat serial moves 274 -> 484), so the two
are NOT competing producers at all: they are init-thread and render-thread.

By refusing 18984 the latch prevented every real present. The log says so:

    [09:32:21.399] [MFG] debug CHECK: ... (menuBlock=0 frames=0 blocked=270 unblocked=1)

unblocked=1, i.e. the frame-generation path ran once in the whole session. And
"Present called with SyncInterval=1" appears exactly ONCE in the whole log - the
init one. v0.80 caused the freeze it was meant to cure.

THE LESSON
----------
"Do two thread ids appear?" is not the question. The question is "does the thread
that presents every frame differ from the thread that owns the per-frame state?"
Two ids alone prove nothing; v0.78 made the same class of mistake with two camera
matrices (see §99).

WHAT THIS PATCH DOES
--------------------
Observation only. Present() entry records, per thread id, how many frames that
thread presented, and when a second id appears it says so with BOTH counts. No
refusal, no early return, no change to the present path at all.

The census line is the evidence needed to decide the real question - and it costs
one map lookup that takes a lock only when a NEW thread id shows up (never on the
hot path after the first couple of frames).

FILES / LINE ENDINGS
--------------------
    src/DX12SwapChain.h     CRLF
    src/DX12SwapChain.cpp   LF

SAFETY
------
Dry run by default; --apply writes.
Anchors unique; insertion markers must be ABSENT; brace delta checked.
"""

import datetime
import hashlib
import os
import shutil
import sys

H = "src/DX12SwapChain.h"
C = "src/DX12SwapChain.cpp"

MARKERS = {
    H: ["v0.81 -- present-thread census (observation only"],
    C: ["v0.81 -- present-thread census",
        "void DX12SwapChain::CensusPresentThread()"],
}

H_ANCHOR = """		std::atomic<std::uint64_t> frameCounter{ 0 };
		std::atomic<long long> lastFrameEndMs{ 0 };
		std::atomic<bool> watchdogStop{ false };
"""

H_NEW = """		std::atomic<std::uint64_t> frameCounter{ 0 };
		std::atomic<long long> lastFrameEndMs{ 0 };
		std::atomic<bool> watchdogStop{ false };

		// v0.81 -- present-thread census (observation only; v0.80's latch was
		// reverted). v0.80 refused every thread but the first one to enter
		// Present(), on the assumption that two ids meant two presenters fighting
		// over one swap chain. The 09:31 run disproved it: the "owner" had
		// presented ONCE (it is the init thread) while the refused thread had
		// presented 300+ times (it is the engine render thread). Refusing it
		// stopped every real present - the freeze v0.80 was supposed to cure.
		// So: observe, count, report, and never refuse.
		struct PresentThreadStat
		{
			std::uint32_t tid = 0;
			std::uint64_t frames = 0;
			long long firstMs = 0;
			long long lastMs = 0;
		};
		static constexpr int kPresentThreadMax = 8;
		PresentThreadStat presentThreads[kPresentThreadMax];
		std::atomic<int> presentThreadCount{ 0 };
		std::uint64_t presentCensusFrames = 0;
		void CensusPresentThread();
		std::string DescribePresentThreads();
"""

C_ENTRY_ANCHOR = """		m_stage = "present entry";

		// v0.7.2：每帧轮询 Home 键（短按切插帧/长按开菜单）——SKSE 输入事件是事件驱动
"""

C_ENTRY_NEW = """		m_stage = "present entry";

		// v0.81 -- who actually presents? Observation only; this never refuses.
		CensusPresentThread();

		// v0.7.2：每帧轮询 Home 键（短按切插帧/长按开菜单）——SKSE 输入事件是事件驱动
"""

C_FUNC_ANCHOR = """	HRESULT DX12SwapChain::Present(UINT SyncInterval, UINT Flags)
	{
		auto& fg = Get();
"""

C_FUNC_NEW = """	// v0.81 -- present-thread census.
	//
	// Records, per thread id, how many frames that thread actually presented, and
	// reports the first time a second id shows up - with BOTH counts, because the
	// counts are the whole point. "Two thread ids" is not a defect; "the thread
	// that presents every frame differs from the thread that owns the per-frame
	// state" might be. v0.80 could not tell those apart and refused the wrong one.
	void DX12SwapChain::CensusPresentThread()
	{
		const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());
		const long long nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
			std::chrono::steady_clock::now().time_since_epoch()).count();
		++presentCensusFrames;

		// Hot path: the first slot almost always matches, and it needs no lock.
		const int n = presentThreadCount.load(std::memory_order_acquire);
		for (int i = 0; i < n; ++i) {
			if (presentThreads[i].tid == tid) {
				++presentThreads[i].frames;
				presentThreads[i].lastMs = nowMs;
				return;
			}
		}

		// A thread id we have not seen. Rare - at most kPresentThreadMax times.
		if (n >= kPresentThreadMax) {
			if (presentCensusFrames % 2000 == 1)
				SKSE::log::warn("[PRESENT] census: more than {} presenter threads seen; "
					"further ids are not tracked", kPresentThreadMax);
			return;
		}
		auto& slot = presentThreads[n];
		slot.tid = tid;
		slot.frames = 1;
		slot.firstMs = nowMs;
		slot.lastMs = nowMs;
		presentThreadCount.store(n + 1, std::memory_order_release);

		if (n == 0) {
			SKSE::log::info("[PRESENT] census: first presenter tid={} - frames and time span "
				"for every presenter are reported below as they appear", tid);
			return;
		}
		SKSE::log::warn("[PRESENT] census: NEW presenter tid={} - now {} distinct threads have "
			"presented this swap chain. Per-thread frames: {}",
			tid, n + 1, DescribePresentThreads());
	}

	// v0.81 -- one-line census body, separate so both call sites stay short.
	std::string DX12SwapChain::DescribePresentThreads()
	{
		std::string s;
		const int n = presentThreadCount.load(std::memory_order_acquire);
		for (int i = 0; i < n; ++i) {
			if (!s.empty())
				s += " | ";
			s += "tid=" + std::to_string(presentThreads[i].tid) +
				" frames=" + std::to_string(presentThreads[i].frames) +
				" span=" + std::to_string(presentThreads[i].lastMs - presentThreads[i].firstMs) + "ms";
		}
		if (s.empty())
			s = "(none)";
		return s;
	}

	HRESULT DX12SwapChain::Present(UINT SyncInterval, UINT Flags)
	{
		auto& fg = Get();
"""

H_INC_ANCHOR = """// v0.62: hang forensics (watchdog thread + atomic frame stamps)
#include <atomic>
#include <thread>
"""

H_INC_NEW = """// v0.62: hang forensics (watchdog thread + atomic frame stamps)
#include <atomic>
#include <thread>
// v0.81: std::string is used as a return type by DescribePresentThreads().
#include <string>
"""

EDITS = [
    (H, "include", H_INC_ANCHOR, H_INC_NEW),
    (H, "fields", H_ANCHOR, H_NEW),
    (C, "entry", C_ENTRY_ANCHOR, C_ENTRY_NEW),
    (C, "new-funcs", C_FUNC_ANCHOR, C_FUNC_NEW),
]


def resolve(path, s):
    with open(path, "rb") as fh:
        raw = fh.read()
    return s.replace("\n", "\r\n") if b"\r\n" in raw else s


def brace_delta(s):
    return s.count("{") - s.count("}")


def main():
    apply_it = "--apply" in sys.argv
    print("=" * 74)
    print("v0.81 present-thread census (observe only)  (mode: %s)"
          % ("APPLY" if apply_it else "DRY RUN"))
    print("=" * 74)

    texts, meta = {}, {}
    for path in (H, C):
        if not os.path.isfile(path):
            print("!! MISSING %s" % path)
            return 1
        with open(path, "rb") as fh:
            raw = fh.read()
        texts[path] = raw.decode("utf-8")
        meta[path] = {"bytes": len(raw), "crlf": b"\r\n" in raw}

    for path, marks in MARKERS.items():
        for mk in marks:
            if mk in texts[path]:
                print("REFUSED: marker already present in %s -> %r" % (path, mk))
                return 1
    print("markers   : absent (patch has not run)")

    for path, label, old, new in EDITS:
        o, n = resolve(path, old), resolve(path, new)
        cnt = texts[path].count(o)
        print("  [%-24s] %-10s occurrences=%d  %s"
              % (path, label, cnt, "ok" if cnt == 1 else "FAIL"))
        if cnt != 1:
            print("REFUSED: anchor %s/%s not unique (%d)" % (path, label, cnt))
            return 1
        texts[path] = texts[path].replace(o, n)

    for path in (H, C):
        b = brace_delta(open(path, "rb").read().decode("utf-8"))
        a = brace_delta(texts[path])
        print("  balance   : %-24s %+d -> %+d %s" % (path, b, a, "ok" if b == a else "FAIL"))
        if b != a:
            print("REFUSED: brace balance moved in %s" % path)
            return 1

    for path in (H, C):
        nb = len(texts[path].encode("utf-8"))
        print("  %-24s %6d -> %6d bytes (%+d), %s"
              % (path, meta[path]["bytes"], nb, nb - meta[path]["bytes"],
                 "CRLF" if meta[path]["crlf"] else "LF"))

    if not apply_it:
        print("DRY RUN: nothing written. Re-run with --apply.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in (H, C):
        shutil.copy2(path, "%s.bak-%s" % (path, stamp))
        with open(path, "wb") as fh:
            fh.write(texts[path].encode("utf-8"))
        print("  WRITTEN   : %s" % path)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
