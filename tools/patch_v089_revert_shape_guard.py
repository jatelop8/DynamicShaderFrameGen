#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v089_revert_shape_guard.py -- REVERT the v0.86 homogeneous-shape guard.

WHAT THE GUARD DOES TODAY
-------------------------
    const float w = a_src.CameraViewProjUnjittered.data[3][3];
    if (!(fabs(w - 1.0f) <= 1e-3f)) { ++snapRejectShape; return false; }

Any snapshot whose c24[3][3] is not 1 is thrown away, and because the caller
only publishes a snapshot when this function returns true...

    if (fg.AcceptCameraSnapshot(*tlsMappedFB))
        fg.SetMappedFrameBuffer(&fg.frameBufferCopy);

...a rejected snapshot never reaches DLSS-G. DLSS-G then keeps reprojecting
with the previous accepted snapshot.

WHY IT IS WRONG (15:02 run, 2026-09-18)
---------------------------------------
The guard rejected 80.6% of all arrivals: acc=2100..13380 vs shape=8734.

The rejected population is not garbage. Its positions move smoothly and
monotonically across consecutive samples:

    #6988  pos=(-50.0, 880.7, 94.3)
    #7612  pos=(-49.9, 860.4, 92.6)
    #8238  pos=(-49.7, 840.4, 90.8)
    #8862  pos=(-49.5, 821.6, 89.2)      <- a real camera, gliding

Garbage does not glide. That is live gameplay camera motion, and the guard is
discarding it. The v0.86 rationale assumed a view-projection matrix must be
affine (last row (0,0,0,1)); this engine's block demonstrably carries a
perspective term, so [3][3] == 0 is LEGAL here. The guard's premise was never
verified -- it was inferred from one odd-looking dump.

Meanwhile the snapshots that DO pass have a FROZEN position:
    acc #1135 .. #1553, pos=(-160.00,160.00,128.00), move=0.0000, path=0.00

So the pipeline feeds DLSS-G an unchanging camera while throwing away the
moving one. That is exactly the reported symptom: geometry and characters sit
pinned to one stale view while only engine-native particles (fire) keep
animating -- "the fire and people sway back and forth".

THE REVERT
----------
Delete the rejection. Do NOT delete the observation: keep counting and, for
the first few plus every 500th, LOG the full last row and the 3x3 determinant
instead of rejecting. That way the next run shows what these matrices actually
are, with no run wasted.

This is deliberately narrow: it restores the pre-v0.86 acceptance behaviour and
adds only logging.

Guards: dry-run default, unique anchor, marker, brace balance, LF only.
"""

import sys
import pathlib

SRC = pathlib.Path("src/FrameGen.cpp")
MARKER = "v0.89: SHAPE rejection REMOVED"

OLD = """\t\t// ---- v0.86: homogeneous-shape guard ---------------------------------
\t\t// A row-major homogeneous view-projection matrix ends in (0,0,0,1): the
\t\t// fourth row maps w and w stays 1 under an affine camera transform. The
\t\t// 14:20 run shows the gate ACCEPTING a matrix whose fourth row is
\t\t// (-0.00391655, 0.999991, 0.0015, 0) -- [3][3] == 0, not a viewProj but a
\t\t// mis-offset read out of the perFrame buffer. Its top-left 3x3 determinant
\t\t// is -2.52504, where a legal pure rotation must give +/-1 (the menu camera
\t\t// seen in the same log gives -1.11111 and passes).
\t\t//
\t\t// This is a structural test, not a tuned threshold: no legitimate viewProj
\t\t// has [3][3] == 0 whatever the camera is doing, so it cannot misfire on a
\t\t// legitimate still scene the way a magnitude threshold would.
\t\t{
\t\t\tconst float w = a_src.CameraViewProjUnjittered.data[3][3];
\t\t\tconst float dw = (w > 1.0f) ? (w - 1.0f) : (1.0f - w);
\t\t\tif (!(dw <= 1.0e-3f)) {
\t\t\t\t++snapRejectShape;
\t\t\t\t// First few and every 500th: enough to prove the population exists,
\t\t\t\t// bounded so a fully malformed run cannot flood the log.
\t\t\t\tif (snapRejectShape <= 5u || (snapRejectShape % 500u) == 0u) {
\t\t\t\t\tSKSE::log::warn("[CAM] #{} SHAPE rejected: [3][3]={:.6g} not 1 "
\t\t\t\t\t\t"(pos=({:.1f},{:.1f},{:.1f}) devVP={:.6g})",
\t\t\t\t\t\tsnapArrivals, w, px, py, pz,
\t\t\t\t\t\tcamDev(a_src.CameraViewProjUnjittered));
\t\t\t\t}
\t\t\t\treturn false;
\t\t\t}
\t\t}
"""

NEW = """\t\t// ---- v0.89: SHAPE rejection REMOVED (was v0.86) ----------------------
\t\t// The v0.86 guard threw away every snapshot whose c24[3][3] != 1, on the
\t\t// theory that a view-projection matrix must be affine. Measured cost:
\t\t//
\t\t//     acc=13380  shape(rejected)=8734   -> 80.6% of arrivals discarded
\t\t//
\t\t// And the discarded population was NOT garbage. Its positions glide:
\t\t//
\t\t//     #6988  pos=(-50.0, 880.7, 94.3)
\t\t//     #7612  pos=(-49.9, 860.4, 92.6)
\t\t//     #8238  pos=(-49.7, 840.4, 90.8)
\t\t//     #8862  pos=(-49.5, 821.6, 89.2)
\t\t//
\t\t// while the snapshots that DID pass were frozen at
\t\t// pos=(-160.00,160.00,128.00) with move=0.0000, path=0.00 for 400+ frames.
\t\t//
\t\t// Since AcceptCameraSnapshot() gates SetMappedFrameBuffer(), a rejection
\t\t// means DLSS-G never sees that snapshot and reprojects with the previous
\t\t// accepted one. Feeding it a parked camera while discarding the moving one
\t\t// reproduces the exact symptom: geometry and characters pinned to one
\t\t// stale view while only engine-native particles (fire) keep animating.
\t\t//
\t\t// The premise was never verified -- it was inferred from a single odd dump
\t\t// and treated as structural. This engine's camera block demonstrably
\t\t// carries a perspective term, so [3][3] == 0 is legal here.
\t\t//
\t\t// The guard is removed. The OBSERVATION is kept, now non-destructive:
\t\t// count the population and log the full last row plus the 3x3 determinant
\t\t// for the first few and every 500th, so the next run can show what these
\t\t// matrices are without costing a run.
\t\t{
\t\t\tconst float w = a_src.CameraViewProjUnjittered.data[3][3];
\t\t\tconst float dw = (w > 1.0f) ? (w - 1.0f) : (1.0f - w);
\t\t\tif (!(dw <= 1.0e-3f)) {
\t\t\t\t++snapRejectShape;              // kept as a COUNTER only
\t\t\t\tif (snapRejectShape <= 5u || (snapRejectShape % 500u) == 0u) {
\t\t\t\t\tconst auto& d = a_src.CameraViewProjUnjittered.data;
\t\t\t\t\tSKSE::log::info("[CAM] #{} non-affine w={:.6g} ACCEPTED (v0.89) "
\t\t\t\t\t\t"row3=({:.6g},{:.6g},{:.6g},{:.6g}) det3={:.6g} "
\t\t\t\t\t\t"pos=({:.1f},{:.1f},{:.1f})",
\t\t\t\t\t\tsnapArrivals, w, d[3][0], d[3][1], d[3][2], d[3][3],
\t\t\t\t\t\tcamDet3(a_src.CameraViewProjUnjittered), px, py, pz);
\t\t\t\t}
\t\t\t\t// NO return false: the snapshot is published as before v0.86.
\t\t\t}
\t\t}
"""


def main():
    apply = "--apply" in sys.argv
    text = SRC.read_text(encoding="utf-8")

    if MARKER in text:
        print("REFUSED: marker already present.")
        return 2

    n = text.count(OLD)
    if n != 1:
        print(f"REFUSED: anchor occurrences={n} (expected 1).")
        return 2

    # precondition: the guard must actually contain a rejection today
    if "++snapRejectShape;" not in OLD or "return false;" not in OLD:
        print("REFUSED: anchor does not contain the expected rejection statements.")
        return 2

    new = text.replace(OLD, NEW, 1)

    # Postcondition, checked on the EXACT replaced regions rather than a
    # character window. A window is a false-positive factory: the file has two
    # other `return false;` statements (the `usable` branch above, the frozen
    # gate below) that sit within a few hundred bytes of this block.
    if OLD.count("return false;") != 1:
        print(f"REFUSED: OLD block has {OLD.count('return false;')} `return false;` (expected 1).")
        return 2
    if NEW.count("return false;") != 0:
        print(f"REFUSED: NEW block still has {NEW.count('return false;')} `return false;`.")
        return 2
    if "++snapRejectShape;" not in NEW:
        print("REFUSED: NEW block lost the counter; the log would stop reporting the population.")
        return 2
    # The whole file must have lost exactly one `return false;`.
    if new.count("return false;") != text.count("return false;") - 1:
        print(f"REFUSED: file-wide `return false;` went {text.count('return false;')} -> "
              f"{new.count('return false;')}; expected exactly -1.")
        return 2

    if new.count("{") != new.count("}"):
        print(f"REFUSED: brace imbalance {new.count('{')} vs {new.count('}')}.")
        return 2
    if "\r\n" in new:
        print("REFUSED: CRLF introduced; FrameGen.cpp must stay LF.")
        return 2

    print(f"anchor=1 OK, size {len(text)} -> {len(new)} (delta {len(new)-len(text):+d})")
    print(f"braces {new.count('{')}/{new.count('}')}   lines {text.count(chr(10))} -> {new.count(chr(10))}")
    if not apply:
        print("DRY RUN -- nothing written.")
        return 0

    SRC.write_text(new, encoding="utf-8", newline="")
    print("APPLIED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
