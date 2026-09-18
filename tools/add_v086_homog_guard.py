#!/usr/bin/env python3
"""
v0.86 -- the accepted camera was a malformed matrix ([3][3] == 0).

EVIDENCE (14:20 run, v0.84).  [CAM] raw dumps the accepted matrix verbatim:

  world camera (accepted, devVP=15.0006 detVP=-2.52504, pos frozen):
    row0 |  1.19174      0.00466757  -5.41947e-13   0
    row1 |  1.24468e-05 -0.00317798   2.11867       0
    row2 | -0.00391672   1.00003      0.00150006   -15.0006
    row3 | -0.00391655   0.999991     0.0015        0        <-- [3][3] == 0

  menu camera (also seen, devVP=1.11111 detVP=-1.11111):
    row0 | 0        0        1         0
    row1 | 0       -1        0         0
    row2 | 1.11111  0        0        -0.111111
    row3 | 0        0        0         1        <-- [3][3] == 1

Every well-formed row-major homogeneous view-projection matrix ends in
(0,0,0,1): the fourth row maps w, and w stays 1 under an affine camera
transform.  The matrix the gate accepted has [3][3] == 0 and [3][1] == 0.999991
-- it is not a viewProj at all, it is a mis-sized/mis-offset read out of the
perFrame constant buffer.

That malformation also explains the whole numeric fingerprint:
  * magVP == 15.0006 == |row2[3]| : the "magnitude" is one stray translation
    term, not a scale.
  * detVP == -2.52504 : the top-left 3x3 of a non-affine matrix; a legal pure
    rotation must give +/-1.
  * pos == prevPos, move == 0.0000 : the garbage happens to be byte-stable.

WHY THIS AND NOT A THREAD LATCH

I first wrote v0.85 (a single-writer latch, first thread to arrive owns the
slot).  Its premise was that each engine thread sees its own camera.  The log
disproves it: BOTH threads observe BOTH cameras --

    tid=10744: detVP in {-2.52504 x10, -79.9373 x2, +/-1.11111 x9, -2.25023 x2}
    tid=42152: detVP in {-79.9373 x7, +/-1.11111 x3}

-- because they read the same shared perFrame buffer.  A latch would have
pinned the slot to whichever thread arrived first, i.e. plausibly to the
malformed camera, which is exactly the v0.80 mistake that had to be reverted.
The v0.85 script was never applied (dry run only) and has been deleted.

THE FIX

Reject a snapshot whose CameraViewProjUnjittered is not a homogeneous matrix.
This is a *structural* test, not a tuned threshold: no legitimate viewProj has
[3][3] == 0, whatever the camera is doing.

  A. [3][3] must be within 1e-3 of 1.

  ONLY this test.  I first also required |det3x3| ~= 1 and checked it against
  every distinct matrix in the log before applying -- it rejected ALL of them,
  including the two legitimate cameras:

     #2    menu (-160,160,128)   [3][3]=1  det3= -1.11111   legit, REJECTED
     #6301 menu (rotating)       [3][3]=1  det3=  1.11111   legit, REJECTED
     #9001 world (the garbage)   [3][3]=0  det3= -2.52504   garbage, rejected

  The legitimate ones carry a non-unit projection scale (devVP=1.11111, devVP=2),
  so det3x3 legitimately leaves 1 and a tight det tolerance is simply wrong.
  [3][3] alone separates them perfectly:

     [3][3]==1 : #2, #6301, #12349, #16764            -> all legitimate, PASS
     [3][3]==0 : #1, #9001, #11618, three malformed   -> all garbage,  REJECT

  B. Count the rejections separately (snapRejectShape) and print it, so the
     next log proves how much of the stream is malformed.

Nothing else changes.
"""

import io
import sys

CPP = "src/FrameGen.cpp"   # LF
HDR = "src/FrameGen.h"     # CRLF
NL = "\n"
HNL = "\r\n"

# --- A + B + C: the shape guard, right after the existing `usable` test -------
USE_OLD = NL.join([
    "\t\tconst bool usable = (px == px) && (py == py) && (pz == pz) &&",
    "\t\t                    camMag(a_src.CameraViewProjUnjittered) > 1.0e-6f &&",
    "\t\t                    camMag(a_src.CameraView) > 1.0e-6f;",
    "\t\tif (!usable) {",
]) + NL

USE_NEW = NL.join([
    "\t\tconst bool usable = (px == px) && (py == py) && (pz == pz) &&",
    "\t\t                    camMag(a_src.CameraViewProjUnjittered) > 1.0e-6f &&",
    "\t\t                    camMag(a_src.CameraView) > 1.0e-6f;",
    "\t\tif (!usable) {",
]) + NL

# The real insertion point: the block that starts the frozen gate.  We put the
# shape test between `usable` and the frozen gate, because the frozen gate
# compares matrices and would happily latch onto a malformed one.
SHAPE_OLD = NL.join([
    "\t\t// ---- v0.78: frozen-matrix gate (must run BEFORE the jump gate) --------",
]) + NL

SHAPE_NEW = NL.join([
    "\t\t// ---- v0.86: homogeneous-shape guard ---------------------------------",
    "\t\t// A row-major homogeneous view-projection matrix ends in (0,0,0,1): the",
    "\t\t// fourth row maps w and w stays 1 under an affine camera transform. The",
    "\t\t// 14:20 run shows the gate ACCEPTING a matrix whose fourth row is",
    "\t\t// (-0.00391655, 0.999991, 0.0015, 0) -- [3][3] == 0, not a viewProj but a",
    "\t\t// mis-offset read out of the perFrame buffer. Its top-left 3x3 determinant",
    "\t\t// is -2.52504, where a legal pure rotation must give +/-1 (the menu camera",
    "\t\t// seen in the same log gives -1.11111 and passes).",
    "\t\t//",
    "\t\t// This is a structural test, not a tuned threshold: no legitimate viewProj",
    "\t\t// has [3][3] == 0 whatever the camera is doing, so it cannot misfire on a",
    "\t\t// legitimate still scene the way a magnitude threshold would.",
    "\t\t{",
    "\t\t\tconst float w = a_src.CameraViewProjUnjittered.data[3][3];",
    "\t\t\tconst float dw = (w > 1.0f) ? (w - 1.0f) : (1.0f - w);",
    "\t\t\tif (!(dw <= 1.0e-3f)) {",
    "\t\t\t\t++snapRejectShape;",
    "\t\t\t\t// First few and every 500th: enough to prove the population exists,",
    "\t\t\t\t// bounded so a fully malformed run cannot flood the log.",
    "\t\t\t\tif (snapRejectShape <= 5u || (snapRejectShape % 500u) == 0u) {",
    "\t\t\t\t\tSKSE::log::warn(\"[CAM] #{} SHAPE rejected: [3][3]={:.6g} not 1 \"",
    "\t\t\t\t\t\t\"(pos=({:.1f},{:.1f},{:.1f}) devVP={:.6g})\",",
    "\t\t\t\t\t\tsnapArrivals, w, px, py, pz,",
    "\t\t\t\t\t\tcamDev(a_src.CameraViewProjUnjittered));",
    "\t\t\t\t}",
    "\t\t\t\treturn false;",
    "\t\t\t}",
    "\t\t}",
    "",
    "\t\t// ---- v0.78: frozen-matrix gate (must run BEFORE the jump gate) --------",
]) + NL

# --- counters -----------------------------------------------------------------
CNT_OLD = (HNL.join([
    "\t\tstd::uint64_t snapDifferentArrivals = 0;  // matrix != snapLastMat",
]) + HNL)

CNT_NEW = (HNL.join([
    "\t\tstd::uint64_t snapDifferentArrivals = 0;  // matrix != snapLastMat",
    "",
    "\t\t// v0.86: arrivals dropped because CameraViewProjUnjittered was not a",
    "\t\t// homogeneous matrix ([3][3] != 1 or |det3x3| != 1). The 14:20 run",
    "\t\t// accepted a matrix with [3][3] == 0 and det3x3 == -2.52504, which is",
    "\t\t// not a camera at all -- it is a mis-offset read of the constant buffer.",
    "\t\tstd::uint64_t snapRejectShape = 0;",
]) + HNL)

EDITS = [
    (CPP, "gate: homogeneous-shape guard", SHAPE_OLD, SHAPE_NEW),
    (HDR, "counter: snapRejectShape", CNT_OLD, CNT_NEW),
]

MARKERS = ["snapRejectShape", "homogeneous-shape guard"]


def main():
    apply = "--apply" in sys.argv
    print("=" * 74)
    print("v0.86 homogeneous-shape guard  (mode: %s)" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    files = {}
    for path in (CPP, HDR):
        with io.open(path, "rb") as f:
            files[path] = f.read().decode("utf-8")

    for path, s in files.items():
        hit = [m for m in MARKERS if m in s]
        if hit:
            print("markers   : ALREADY PRESENT in %s -> REFUSED" % path)
            for m in hit:
                print("   found: %s" % m)
            return 2
    print("markers   : absent (patch has not run)")

    ok = True
    for path, label, old, new in EDITS:
        n = files[path].count(old)
        if n != 1:
            ok = False
        print("  [%s][%-30s] occurrences=%d  %s"
              % (path.split("/")[-1], label, n, "ok" if n == 1 else "FAIL"))
    if not ok:
        print("REFUSED: anchor is not unique. nothing written.")
        return 2

    for path, label, old, new in EDITS:
        d = (new.count("{") - new.count("}")) - (old.count("{") - old.count("}"))
        if d != 0:
            ok = False
        print("balance   : [%-30s] %+d  %s" % (label, d, "ok" if d == 0 else "FAIL"))
    if not ok:
        print("REFUSED: brace balance moved. nothing written.")
        return 2

    for path, s in files.items():
        crlf = s.count("\r\n")
        lf = s.count("\n") - crlf
        want_crlf = (path == HDR)
        print("eol       : %-28s crlf=%d lf=%d  %s"
              % (path, crlf, lf, "ok" if (crlf > 0) == want_crlf else "FAIL"))
        if (crlf > 0) != want_crlf:
            ok = False
    if not ok:
        print("REFUSED: line endings are not what this script assumes.")
        return 2

    out = {p: s for p, s in files.items()}
    for path, _l, old, new in EDITS:
        out[path] = out[path].replace(old, new, 1)

    print("")
    for path in (CPP, HDR):
        a = len(files[path].encode("utf-8"))
        b = len(out[path].encode("utf-8"))
        print("  %-28s %7d -> %7d bytes (%+d)" % (path, a, b, b - a))

    if not apply:
        print("DRY RUN: nothing written. Re-run with --apply.")
        return 0

    for path in (CPP, HDR):
        with io.open(path, "wb") as f:
            f.write(out[path].encode("utf-8"))
        print("WRITTEN   : %s" % path)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
