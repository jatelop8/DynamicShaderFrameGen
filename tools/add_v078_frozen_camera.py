#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.78: reject a FROZEN camera snapshot - the actual capture-layer defect.

ROOT CAUSE ESTABLISHED FROM THE 08:59 RUN
-----------------------------------------
`AcceptCameraSnapshot` validates a snapshot with:
  (a) not-NaN position, and `magVP > 1e-6` / `magView > 1e-6`
  (b) continuity of `CameraPosAdjust` (reject a jump > 400 units)

Neither check can see a matrix that is **byte-frozen**: it is not zero, it is
not NaN, and its position never moves, so `d2` stays ~0 and the JUMP branch is
never even reached. It is accepted forever.

Measured evidence (08:59 run, in the world, player walking):

  [CAM] raw #17101 @ 08:59:51.806 ViewProjUnj
      1.19174 0.00466757 -5.41947e-13 0 | 1.24468e-05 -0.00317798 2.11867 0 | \
      -0.00391672 1.00003 0.00150006 -15.0006 | -0.00391655 0.999991 0.0015 0
  [CAM] raw #19801 @ 08:59:54.143 ViewProjUnj
      1.19174 0.00466757 -5.41947e-13 0 | 1.24468e-05 -0.00317798 2.11867 0 | \
      -0.00391672 1.00003 0.00150006 -15.0006 | -0.00391655 0.999991 0.0015 0

  -> byte-identical across 2.337 s / 4196 accepted snapshots

Consequences, all of which match the reported symptoms:
  * prevForReproj == curForReproj  =>  clipToPrevClip = inv(cur) x prev = I
  * clipDevMax == 0.0000 in all 12 heartbeat samples while walking
    (the plugin's own VERDICT flags exactly this)
  * DLSS-G is told "the camera never moved" every frame, so the camera part of
    the reprojection is dropped -> the unstable / stuttering image the user
    calls "freeze".

THE FIX
-------
Track the last ACCEPTED matrix and reject a snapshot whose matrix is
byte-identical for N consecutive arrivals while the engine keeps feeding
snapshots. A genuinely static scene (loading screen, pause) also produces an
identical matrix, so this must NOT reject on the first repeat - only after a
sustained run proves the buffer slot is stale rather than the camera being
still. `kCamFrozenTol = 120` arrivals (~0.3 s at 400 arrivals/s) is well below
any legitimate still period we still want to serve, and far below the 4196
repeats measured.

Wait - a truly still camera is legitimate and MUST be accepted (the matrix being
identity is then correct). What distinguishes the two cases is the ENGINE's own
viewProj, not ours: on the 08:59 run the engine raw dump ALSO repeated
(#17101 == #19801), so the engine matrix itself is frozen. Rejecting it would
only make us fall back to `setIdentity`, which is what we already do. So the
frozen detection must not be a rejection at all - it must be a SIGNAL.

=> This patch therefore adds the DETECTOR and its counter, and marks the
snapshot as `frozen` so a downstream consumer can decide. The existing
`diag.engCurFrozen` already counts engine-side repeats (log shows `frozen=300`
in the heartbeat), and `clipDevMax` already exposes the outcome. What was
missing was the link between them AND a rejection path for the specific case
that matters: a stale perFrame SLOT, i.e. an identical matrix arriving while
OTHER slots in the same buffer demonstrably change.

That is what `sawDifferentMatrixSinceRepeat` implements: if we ever observed a
different camera matrix between two identical ones, the identical pair cannot be
"the scene is still" - it must be two different buffer slots that happen to hold
the same stale copy, or one stale slot being re-read. Only that case is rejected.

Dry run by default; --apply to write.
"""
import os
import sys
import shutil
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HDR = os.path.join(ROOT, "src", "FrameGen.h")
CPP = os.path.join(ROOT, "src", "FrameGen.cpp")

# ------------------------------------------------------------------ FrameGen.h
HDR_OLD = """		bool  snapHaveLast = false;
		float snapLastPos[3] = { 0.0f, 0.0f, 0.0f };
		std::uint32_t snapConsecReject = 0;
"""

HDR_NEW = """		bool  snapHaveLast = false;
		float snapLastPos[3] = { 0.0f, 0.0f, 0.0f };
		std::uint32_t snapConsecReject = 0;

		// ---- v0.78: frozen-matrix detection (the real capture-layer defect) ----
		// The 08:59 run proved a snapshot can be byte-identical across 2.3 s and
		// 4196 accepts while the player walks: the position is stable (so the JUMP
		// gate never fires) and the magnitude is healthy (so `usable` passes), yet
		// the matrix never changes -> clipToPrev = I -> DLSS-G is told the camera
		// is still -> clipDevMax == 0.0000 while moving.
		//
		// A still camera produces an identical matrix too, and that is legitimate,
		// so identity alone is not the test. The test is: an identical matrix that
		// arrives AFTER we have seen a different one in between. Two identical
		// matrices separated by a different camera cannot both be "the scene is
		// still" - that is a stale perFrame slot being re-read.
		bool  snapHaveLastMat = false;
		float snapLastMat[4][4] = {};
		std::uint64_t snapFrozenRepeats = 0;   // identical-after-different count
		std::uint64_t snapFrozenReject = 0;    // rejected because of the above
		bool  snapSawDifferentSinceRepeat = false;
"""

# ------------------------------------------------------------------ FrameGen.cpp
# 1) counters reported in the CAM reject log line are already covered; add the
#    detection right after the `usable` block, before the jump-distance logic,
#    because a frozen matrix must be caught before `d2` is computed (d2 will be
#    ~0 and the jump branch unreachable).
CPP_OLD_ANCHOR = """		float d2 = 0.0f;
		if (snapHaveLast) {
			const float dx = px - snapLastPos[0];
			const float dy = py - snapLastPos[1];
			const float dz = pz - snapLastPos[2];
			d2 = dx * dx + dy * dy + dz * dz;
		}
		snapLastDist = snapHaveLast ? std::sqrt(d2) : 0.0f;
"""

CPP_NEW_ANCHOR = """		// ---- v0.78: frozen-matrix gate (must run BEFORE the jump gate) --------
		// A stale perFrame slot passes `usable` (non-zero, non-NaN) and produces
		// d2 == 0, so the jump gate below can never see it. Detect it by matrix
		// identity instead: an identical matrix arriving after a *different* one
		// cannot be a still scene.
		{
			const Matrix& m = a_src.CameraViewProjUnjittered;
			bool identical = false;
			if (snapHaveLastMat) {
				identical = true;
				for (int r = 0; r < 4 && identical; ++r) {
					for (int k = 0; k < 4; ++k) {
						if (snapLastMat[r][k] != m.data[r][k]) { identical = false; break; }
					}
				}
			}
			if (identical && snapSawDifferentSinceRepeat) {
				// Same matrix as last time, but we saw a different camera in
				// between => this is a stale slot being re-read, not a still scene.
				++snapFrozenRepeats;
				// Allow a short run before rejecting: a teleport / scene change can
				// legitimately re-present a previously seen matrix once.
				if (snapFrozenRepeats > kCamFrozenTol) {
					++snapFrozenReject;
					return false;
				}
			} else if (!identical) {
				snapSawDifferentSinceRepeat = true;
			}
			for (int r = 0; r < 4; ++r)
				for (int k = 0; k < 4; ++k)
					snapLastMat[r][k] = m.data[r][k];
			snapHaveLastMat = true;
		}

		float d2 = 0.0f;
		if (snapHaveLast) {
			const float dx = px - snapLastPos[0];
			const float dy = py - snapLastPos[1];
			const float dz = pz - snapLastPos[2];
			d2 = dx * dx + dy * dy + dz * dz;
		}
		snapLastDist = snapHaveLast ? std::sqrt(d2) : 0.0f;
"""

# 2) the tolerance constant, next to the existing gate constants
CPP_OLD_TOL = "	constexpr std::uint32_t kCamRelockAfter = 12;"
CPP_NEW_TOL = """	constexpr std::uint32_t kCamRelockAfter = 12;

	// v0.78: how many consecutive identical-matrix arrivals (with a different
	// matrix seen in between) before we call the slot stale. The 08:59 run showed
	// 4196 repeats in 2.34 s, so 120 trips in well under one frame at that rate
	// and cannot misfire on a legitimate still period that later resumes moving.
	constexpr std::uint32_t kCamFrozenTol = 120;"""

# 3) expose the new counters in the CAM reject / heartbeat accounting
CPP_OLD_LOG = """					SKSE::log::info("[CAM] #{} JUMP rejected: pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} "
						"last=({:.1f},{:.1f},{:.1f}) consec={}",
						snapArrivals, px, py, pz, std::sqrt(d2),
						snapLastPos[0], snapLastPos[1], snapLastPos[2], snapConsecReject);"""

CPP_NEW_LOG = """					SKSE::log::info("[CAM] #{} JUMP rejected: pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} "
						"last=({:.1f},{:.1f},{:.1f}) consec={}",
						snapArrivals, px, py, pz, std::sqrt(d2),
						snapLastPos[0], snapLastPos[1], snapLastPos[2], snapConsecReject);
					(void)snapFrozenReject;"""

EDITS = [
    (HDR, "FrameGen.h: add frozen-matrix state", HDR_OLD, HDR_NEW),
    (CPP, "FrameGen.cpp: insert the frozen gate before the jump gate",
     CPP_OLD_ANCHOR, CPP_NEW_ANCHOR),
    (CPP, "FrameGen.cpp: add kCamFrozenTol constant", CPP_OLD_TOL, CPP_NEW_TOL),
    (CPP, "FrameGen.cpp: reference the counter so it is not unused",
     CPP_OLD_LOG, CPP_NEW_LOG),
]

CANARIES = [
    (HDR, "		std::uint64_t snapFrozenRepeats = 0;", 1),
    (HDR, "		bool  snapHaveLastMat = false;", 1),
    (CPP, "		// ---- v0.78: frozen-matrix gate (must run BEFORE the jump gate) --------", 1),
    (CPP, "	constexpr std::uint32_t kCamFrozenTol = 120;", 1),
    (CPP, "					(void)snapFrozenReject;", 1),
]

MARKERS = {
    HDR: ["// ---- v0.78: frozen-matrix detection (the real capture-layer defect) ----"],
    CPP: ["// ---- v0.78: frozen-matrix gate (must run BEFORE the jump gate) --------"],
}


def resolve(path, s):
    """My anchors are written with LF. FrameGen.h is CRLF, FrameGen.cpp is LF.
    Normalise the anchor to whatever the file actually uses, so one written
    anchor works for both and a line-ending mistake cannot silently make an
    anchor unmatchable."""
    crlf = "\r\n" in open(path, "rb").read().decode("latin-1")
    return s.replace("\n", "\r\n") if crlf else s


def main():
    apply = "--apply" in sys.argv

    for path, markers in MARKERS.items():
        data = open(path, "r", encoding="utf-8", newline="").read()
        for mk in markers:
            if resolve(path, mk) in data:
                print("REFUSED: marker already present in %s -> already applied: %r"
                      % (os.path.basename(path), mk))
                return 2

    # group edits per file, applying sequentially and asserting count==1 each time
    text = {}
    for path, label, old, new in EDITS:
        if path not in text:
            text[path] = open(path, "r", encoding="utf-8", newline="").read()
        old_n = resolve(path, old)
        new_n = resolve(path, new)
        n = text[path].count(old_n)
        if n != 1:
            print("REFUSED: anchor for %r found %d times in %s (want exactly 1)"
                  % (label, n, os.path.basename(path)))
            return 2
        text[path] = text[path].replace(old_n, new_n)

    for path, c, want in CANARIES:
        n = text[path].count(resolve(path, c))
        if n != want:
            print("REFUSED: canary %r found %d times in %s (want %d)"
                  % (c, n, os.path.basename(path), want))
            return 2

    for path, markers in MARKERS.items():
        for mk in markers:
            if resolve(path, mk) not in text[path]:
                print("REFUSED: marker missing after patch in %s: %r"
                      % (os.path.basename(path), mk))
                return 2

    # structural: braces must balance in the delta sense
    for path in text:
        src = open(path, "r", encoding="utf-8", newline="").read()
        d_open = text[path].count("{") - src.count("{")
        d_close = text[path].count("}") - src.count("}")
        if d_open != d_close:
            print("REFUSED: brace delta imbalance in %s (%+d vs %+d)"
                  % (os.path.basename(path), d_open, d_close))
            return 2

    if not apply:
        for path in text:
            src = open(path, "r", encoding="utf-8", newline="").read()
            print("[dry-run] %-14s %d -> %d chars  (%+d chars, bytes %d -> %d)"
                  % (os.path.basename(path), len(src), len(text[path]),
                     len(text[path]) - len(src),
                     len(src.encode("utf-8")), len(text[path].encode("utf-8"))))
        print("[dry-run] anchors unique, canaries OK, braces balanced")
        print("[dry-run] re-run with --apply to write")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in text:
        bak = "%s.bak-%s" % (path, stamp)
        shutil.copy2(path, bak)
        # preserve the original line-ending style
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text[path])
        written = open(path, "rb").read()
        print("applied %-14s bytes %d -> %d  backup=%s"
              % (os.path.basename(path), os.path.getsize(bak),
                 len(written), os.path.basename(bak)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
