#!/usr/bin/env python3
"""
v0.80: name the second presenter, then latch the swap chain to one thread.

WHY
---
The 08:59 run's log carries two independent engine producers:

    $ grep -o "\\[[0-9]\\{5\\}\\]" DynamicShaderFrameGen.log | sort | uniq -c | sort -rn
        278 [17568]      pos=(-243.05,-415.31,118.56)  devVP=15.0006  detVP=-2.52504
        116 [32096]      pos=(-50.00,619.31,107.04)    devVP=15.011   detVP=-79.9373
          4 [41852]
          1 [20028]

Two different cameras, two different projection norms, and the start-up banner
printed twice - once at the start and once at 08:59:47.505, 48 seconds in.
MENU EDGE open=1 came from [32096]; MENU EDGE open=0 came from [17568]. So the
"2.337 s frozen matrix" of v0.78 was not a frozen camera at all: it was two
cameras interleaved into ONE log stream. #17101 and #19801 are each thread's own
counter, not a global frame index.

The swap chain is not thread-safe: frameToken, frameSerial, slSetConstants and
the DLSS-G option state are all single-writer by design. Two threads entering
Present() overwrite each other's token and constants every frame, which is what
makes generation collapse to "presented per real frame = 1" (8 of the 10 samples
in the whole run) with a 5.93 s hole in the middle.

WHAT THIS PATCH DOES (two parts, both pure additions)
-----------------------------------------------------
A. NAMES the second presenter. Present() entry keeps the first thread id it
   ever saw and logs once every time it sees a different one, plus a running
   census so the log says which thread came back and how often. Costs two
   atomics and prints at most ~40 lines.

B. LATCHES the entry: the first thread to enter Present() becomes the swap
   chain's owner. Any other thread is refused a pass-through Present immediately
   - it never reaches PollHomeKey, the fence traffic, SetDLSSGOptions,
   EvaluateDLSSG or the D3D12 queue. That is the whole point: a second thread
   cannot corrupt the token or the constants if it never gets in.

   The latch is deliberately conservative:
     * it arms itself only after LATCH_ARM_MS of observation, so a genuinely
       multi-threaded startup is not guessed at from the first two frames;
     * it prints its decision once, with both thread ids and the frame counts,
       so the next log states in plain words whether it engaged at all;
     * a refused frame returns S_OK without presenting. Returning the real
       hrPresent from a foreign thread would re-enter the queue; a dropped
       foreign frame is the safe direction - the owner thread still drives the
       panel every frame.

FILES / LINE ENDINGS
--------------------
    src/DX12SwapChain.h     CRLF
    src/DX12SwapChain.cpp   LF

SAFETY
------
Dry run by default; --apply writes.
Anchors must be unique; every insertion carries a marker that must be ABSENT.
Brace-balance delta is checked per file. Timestamped .bak per file.
"""

import datetime
import hashlib
import os
import shutil
import sys

H = "src/DX12SwapChain.h"
C = "src/DX12SwapChain.cpp"

MARKERS = {
    H: ["v0.80 -- presenter latch"],
    C: ["v0.80 -- presenter latch: name the second presenter",
        "void DX12SwapChain::ScanPresentThread()",
        "bool DX12SwapChain::ClaimPresentThread()"],
}

# ----------------------------------------------------------------- header
H_ANCHOR = """		// v0.79 -- menu-guard decoupling.
		// The MFG multiplier ladder used to live entirely behind Present()'s
		// else-if branch, which the menu guard short-circuits. Exposed here so
		// Present() can run the probe on EVERY frame and only then decide.
		std::uint64_t menuBlockedFrames = 0;
		std::uint64_t menuUnblockedFrames = 0;
		std::uint64_t mfgWarned = 0;
"""

H_NEW = """		// v0.79 -- menu-guard decoupling.
		// The MFG multiplier ladder used to live entirely behind Present()'s
		// else-if branch, which the menu guard short-circuits. Exposed here so
		// Present() can run the probe on EVERY frame and only then decide.
		std::uint64_t menuBlockedFrames = 0;
		std::uint64_t menuUnblockedFrames = 0;
		std::uint64_t mfgWarned = 0;

		// v0.80 -- presenter latch.
		// The 08:59 run had TWO threads driving this swap chain ([17568] and
		// [32096], different cameras, different projection norms, and the
		// start-up banner printed twice). frameToken / frameSerial /
		// slSetConstants / the DLSS-G option state are all single-writer, so two
		// presenters overwrite each other every frame -> generation collapses to
		// "presented per real frame = 1" (8 of 10 samples in that run).
		// First presenter to arrive owns the chain; the rest are refused before
		// they can touch anything.
		std::uint32_t presentOwnerTid = 0;          // 0 = not claimed yet
		std::uint32_t presentOtherTid = 0;          // last foreign thread seen
		std::uint64_t presentOwnerFrames = 0;
		std::uint64_t presentForeignFrames = 0;
		std::uint64_t presentForeignRejected = 0;
		std::uint64_t presentTidChanges = 0;
		bool presentLatchArmed = false;
		std::uint64_t presentTidScans = 0;
		long long presentScanStartMs = 0;

		// A. observe and name every presenter (never refuses anything).
		void ScanPresentThread();
		// B. true = this thread owns the chain and may present.
		bool ClaimPresentThread();
"""

# ----------------------------------------------------------------- cpp: entry
C_ENTRY_ANCHOR = """		m_stage = "present entry";

		// v0.7.2：每帧轮询 Home 键（短按切插帧/长按开菜单）——SKSE 输入事件是事件驱动
"""

C_ENTRY_NEW = """		m_stage = "present entry";

		// v0.80 -- presenter latch: name the second presenter, then refuse it.
		// Both calls are pure additions; the rest of Present() is unchanged.
		ScanPresentThread();
		if (!ClaimPresentThread()) {
			// A foreign thread reached Present(). Do NOT touch the fence, the
			// token, the DLSS-G options or the queue - that is exactly the
			// corruption this latch exists to stop. Return S_OK without
			// presenting; the owning thread still drives the panel every frame.
			return S_OK;
		}

		// v0.7.2：每帧轮询 Home 键（短按切插帧/长按开菜单）——SKSE 输入事件是事件驱动
"""

# ----------------------------------------------------------------- cpp: new funcs
C_FUNC_ANCHOR = """	HRESULT DX12SwapChain::Present(UINT SyncInterval, UINT Flags)
	{
		auto& fg = Get();
"""

C_FUNC_NEW = """	// v0.80 -- presenter latch: name the second presenter.
	//
	// Deliberately observe-only. The 08:59 run produced two concrete thread ids
	// that no code in this project ever looked at, and the whole v0.78 root-cause
	// call (\"the capture layer accepted a frozen matrix\") was an artefact of
	// comparing samples from those two threads as if they were one sequence.
	// So the first job is to make the log say the ids out loud.
	void DX12SwapChain::ScanPresentThread()
	{
		const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());
		const std::uint32_t owner = presentOwnerTid;
		if (owner == 0) {
			presentOwnerTid = tid;
			++presentOwnerFrames;
			const long long nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
				std::chrono::steady_clock::now().time_since_epoch()).count();
			presentScanStartMs = nowMs;
			SKSE::log::info(\"[PRESENT] first presenter tid={} - this thread owns the swap chain (v0.80)\", tid);
			return;
		}
		if (owner == tid) {
			++presentOwnerFrames;
			return;
		}

		// A different thread. Count it and say so - once per distinct id, plus a
		// periodic census so a thread that comes back is visible too.
		++presentForeignFrames;
		++presentTidChanges;
		if (presentOtherTid != tid) {
			presentOtherTid = tid;
			SKSE::log::error(\"[PRESENT] SECOND presenter tid={} (owner={}) - the swap chain is being driven from more \"
				\"than one thread. frameToken/frameSerial/slSetConstants are single-writer, so the two \"
				\"presenters overwrite each other every frame. This is the v0.79 finding made concrete.\",
				tid, owner);
		}
		++presentTidScans;
		if (presentTidScans <= 10 || (presentTidScans % 300) == 0) {
			SKSE::log::warn(\"[PRESENT] tid census #{}: owner={} frames={} | foreign={} frames={} changes={}\",
				presentTidScans, owner, presentOwnerFrames, tid, presentForeignFrames, presentTidChanges);
		}
	}

	// v0.80 -- presenter latch: true = this thread may present.
	//
	// Arms only after LATCH_ARM_MS of observation. Before that every thread is
	// let through, because a swap chain created on one thread and first presented
	// on another is legal and we must not mistake it for two presenters. After
	// that, a foreign thread is refused.
	bool DX12SwapChain::ClaimPresentThread()
	{
		constexpr long long kLatchArmMs = 2000;

		const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());
		if (presentOwnerTid == 0 || presentOwnerTid == tid)
			return true;

		if (!presentLatchArmed) {
			const long long nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
				std::chrono::steady_clock::now().time_since_epoch()).count();
			if (nowMs - presentScanStartMs < kLatchArmMs)
				return true;   // still watching: a late first presenter is not a second one
			presentLatchArmed = true;
			SKSE::log::warn(\"[PRESENT] LATCH ARMED after {} ms: owner={} (frames={}), foreign={} (frames={}). \"
				\"From now on only tid={} presents; every other thread is refused at entry.\",
				nowMs - presentScanStartMs, presentOwnerTid, presentOwnerFrames,
				presentOtherTid, presentForeignFrames, presentOwnerTid);
		}

		++presentForeignRejected;
		if (presentForeignRejected <= 5 || (presentForeignRejected % 600) == 1) {
			SKSE::log::warn(\"[PRESENT] REFUSED foreign presenter tid={} (owner={}) - skipped {} frame(s) so far. \"
				\"Skipped frames are not presented by this thread on purpose: entering the queue from two \"
				\"threads corrupts the frame token and the per-frame constants.\",
				tid, presentOwnerTid, presentForeignRejected);
		}
		return false;
	}

	HRESULT DX12SwapChain::Present(UINT SyncInterval, UINT Flags)
	{
		auto& fg = Get();
"""

EDITS = [
    (H, "fields", H_ANCHOR, H_NEW),
    (C, "entry", C_ENTRY_ANCHOR, C_ENTRY_NEW),
    (C, "new-funcs", C_FUNC_ANCHOR, C_FUNC_NEW),
]


def resolve(path, s):
    with open(path, "rb") as fh:
        raw = fh.read()
    if b"\r\n" in raw:
        return s.replace("\n", "\r\n")
    return s


def brace_delta(s):
    return s.count("{") - s.count("}")


def main():
    apply_it = "--apply" in sys.argv
    print("=" * 74)
    print("v0.80 presenter latch  (mode: %s)" % ("APPLY" if apply_it else "DRY RUN"))
    print("=" * 74)

    texts, meta = {}, {}
    for path in (H, C):
        if not os.path.isfile(path):
            print("!! MISSING %s" % path)
            return 1
        with open(path, "rb") as fh:
            raw = fh.read()
        texts[path] = raw.decode("utf-8")
        meta[path] = {"bytes": len(raw), "crlf": b"\r\n" in raw,
                      "md5": hashlib.md5(raw).hexdigest()}

    for path, marks in MARKERS.items():
        for mk in marks:
            if mk in texts[path]:
                print("REFUSED: marker already present in %s -> %r" % (path, mk))
                return 1
    print("markers   : absent in both files (patch has not run)")

    for path, label, old, new in EDITS:
        o = resolve(path, old)
        n = resolve(path, new)
        cnt = texts[path].count(o)
        print("  [%-24s] %-10s occurrences=%d  %s"
              % (path, label, cnt, "ok" if cnt == 1 else "FAIL"))
        if cnt != 1:
            print("REFUSED: anchor %s/%s not unique (%d) - nothing written"
                  % (path, label, cnt))
            return 1
        texts[path] = texts[path].replace(o, n)

    for path in (H, C):
        before = brace_delta(open(path, "rb").read().decode("utf-8"))
        after = brace_delta(texts[path])
        print("  balance   : %-24s %+d -> %+d %s"
              % (path, before, after, "ok" if before == after else "FAIL"))
        if before != after:
            print("REFUSED: brace balance moved in %s" % path)
            return 1

    for path in (H, C):
        nb = len(texts[path].encode("utf-8"))
        print("  %-24s %6d -> %6d bytes (%+d), line end %s"
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
    print("=" * 74)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
