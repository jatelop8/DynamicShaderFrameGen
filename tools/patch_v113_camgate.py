#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.13 -- capture-side content gate: a camera snapshot must LOOK like a camera.

Evidence (18:20 run, the only run that ever reached the world with v1.12 in
place):

  * The perFrame constant buffer is mapped ~22 times per rendered frame
    (591 arrivals/s at ~24 world fps).  The hook has always taken "the last
    writer" (tlsMappedFB is overwritten by every matching Map).
  * In the MENU every write is the camera.  In the WORLD the majority are
    NOT: the captured CameraProj is
        (0,0,1.111111,-0.1111111)/(0,0,0,1)  ==  an ORTHOGRAPHIC projection
        with m22=0.9, m23=0.1 on its inverse  ==  z:[0.1,1] -> [0,1]
    while the real camera write is
        (0,0,1.000733,-15.01099)/(0,0,1,0)   ==  a perspective projection.
    In the same buffer the impostor's CameraView is the exact axis
    permutation [[0,0,1],[0,1,0],[1,0,0]] and CameraPreviousPosAdjust is
    identically (0,0,0,0) for 30 s (in the menu it tracks the live position).

  * Consequence measured on the published stream: matChanges stayed frozen at
    542 / 6171, `path` stayed at 124.92 for 30 s while pos jittered +/- 0.6
    around a parked point, and the lock's anchor went to a non-camera.

Separation used here (one line each, both measured, both exact):

    camera write  : |CameraProj[3][2]| = 1     |CameraProj[3][3]| = 0
    impostor write: |CameraProj[3][2]| = 0     |CameraProj[3][3]| = 1

The gate is a FILTER, not a new camera source: a dropped snapshot is simply
not published, and after kCamCaptureFallbackSkips consecutive drops the gate
stops filtering and behaviour falls back to today's (accept the last writer).
So the worst case is exactly the current build -- never worse.

Usage:
    python tools/patch_v113_camgate.py            # dry run
    python tools/patch_v113_camgate.py --apply    # write
    python tools/patch_v113_camgate.py --revert --apply
"""

import sys
import os

F_CPP = "src/FrameGen.cpp"
F_H = "src/FrameGen.h"

MARK = "v1.13: A CAMERA SNAPSHOT MUST LOOK LIKE A CAMERA"
MARK_C = "cap={}/{}"

# --------------------------------------------------------------------------
# 1) constants -- appended to the thresholds namespace (kCamFrozenTol block)
# --------------------------------------------------------------------------
CONST_OLD = (
    "\t// and changes nothing -- see the [CAM] pub `frozenRep=` field for its value.\r\n"
    "\t}\r\n"
)

CONST_NEW = (
    "\t// and changes nothing -- see the [CAM] pub `frozenRep=` field for its value.\r\n"
    "\r\n"
    "\t// ---- v1.13: how a CAMERA WRITE is told apart from the other writers ----\r\n"
    "\t// The perFrame buffer is mapped ~22 times per rendered frame and only one\r\n"
    "\t// of those writes is the camera; see the gate in AcceptCameraSnapshot for\r\n"
    "\t// the full measurement.  Both numbers come from the 18:20 run and both\r\n"
    "\t// separate the two populations exactly:\r\n"
    "\t//     camera   : |Proj[3][2]| = 1     |Proj[3][3]| = 0\r\n"
    "\t//     impostor : |Proj[3][2]| = 0     |Proj[3][3]| = 1\r\n"
    "\tconstexpr float kCamProjDivideMin = 0.05f;   // |CameraProj[3][2]| -- perspective divide present\r\n"
    "\tconstexpr float kCamProjWMax = 0.05f;        // |CameraProj[3][3]| -- must be 0 for a D3D projection\r\n"
    "\t// ~10 s of drops at the measured ~590 arrivals/s.  Long enough that a\r\n"
    "\t// genuine world camera never trips it, short enough that a machine whose\r\n"
    "\t// camera write fails the test is back on the old behaviour within one run.\r\n"
    "\tconstexpr std::uint64_t kCamCaptureFallbackSkips = 6000;\r\n"
    "\t}\r\n"
)

# --------------------------------------------------------------------------
# 2) the gate itself -- between the `usable` block and the v0.89 shape block
# --------------------------------------------------------------------------
GATE_OLD = (
    "\t\t\treturn false;\r\n"
    "\t\t}\r\n"
    "\r\n"
    "\t\t// ---- v0.89: SHAPE rejection REMOVED (was v0.86) ----------------------\r\n"
)

GATE_NEW = (
    "\t\t\treturn false;\r\n"
    "\t\t}\r\n"
    "\r\n"
    "\t\t// ---- v1.13: A CAMERA SNAPSHOT MUST LOOK LIKE A CAMERA ----------------\r\n"
    "\t\t// This hook captures *every* Map/Unmap of the perFrame constant buffer,\r\n"
    "\t\t// ~22 per rendered frame (measured 18:20 run: 591 arrivals/s at ~24 world\r\n"
    "\t\t// fps), and tlsMappedFB is overwritten by each one -- so the snapshot that\r\n"
    "\t\t// reaches this function is whatever pass wrote LAST, and in the world that\r\n"
    "\t\t// is not the camera.  Measured populations in the world:\r\n"
    "\t\t//\r\n"
    "\t\t//   camera write  : CameraProj row3 = (0,0,1.000733,-15.01099) + (0,0,1,0)\r\n"
    "\t\t//                   -> a perspective projection, CameraPreviousPosAdjust\r\n"
    "\t\t//                      tracks the live position\r\n"
    "\t\t//   impostor write: CameraProj row3 = (0,0,1.111111,-0.1111111) + (0,0,0,1)\r\n"
    "\t\t//                   -> an ORTHOGRAPHIC fullscreen-style projection\r\n"
    "\t\t//                      (m22=0.9, m23=0.1 on its inverse: z:[0.1,1]->[0,1]),\r\n"
    "\t\t//                      CameraView is the exact axis permutation\r\n"
    "\t\t//                      [[0,0,1],[0,1,0],[1,0,0]], and\r\n"
    "\t\t//                      CameraPreviousPosAdjust is identically (0,0,0,0)\r\n"
    "\t\t//\r\n"
    "\t\t// Publishing the impostor IS the freeze: on the published stream\r\n"
    "\t\t// matChanges stopped at 6171, `path` stayed at 124.92 for 30 s while pos\r\n"
    "\t\t// jittered +/- 0.6 around a parked point, and the lock's anchor went to a\r\n"
    "\t\t// non-camera.  So a snapshot that is not a camera must never reach the\r\n"
    "\t\t// lock, frameBufferCopy, or the reprojection.\r\n"
    "\t\t//\r\n"
    "\t\t// ESCAPE HATCH: if NOTHING looks like a camera for kCamCaptureFallbackSkips\r\n"
    "\t\t// consecutive snapshots, the test itself is wrong for this machine and\r\n"
    "\t\t// accepting the last writer -- today's behaviour -- is strictly better than\r\n"
    "\t\t// starving the stream.  The gate then stops filtering for the rest of the\r\n"
    "\t\t// run, so the worst case is the current build, never a worse one.\r\n"
    "\t\t{\r\n"
    "\t\t\tconst bool camShaped =\r\n"
    "\t\t\t\t(std::fabs(a_src.CameraProj.data[3][2]) >= kCamProjDivideMin) &&\r\n"
    "\t\t\t\t(std::fabs(a_src.CameraProj.data[3][3]) <= kCamProjWMax);\r\n"
    "\t\t\tif (!camShaped) {\r\n"
    "\t\t\t\t++snapNonCamera;\r\n"
    "\t\t\t\t++snapSkipsSinceCam;\r\n"
    "\t\t\t\tif (snapNonCamera <= 5u) {\r\n"
    "\t\t\t\t\tSKSE::log::info(\"[CAM] #{} NON-CAMERA write dropped (v1.13): Proj \"\r\n"
    "\t\t\t\t\t\t\"row3=({:.6g},{:.6g},{:.6g},{:.6g}) prevPos=({:.4g},{:.4g},{:.4g}) \"\r\n"
    "\t\t\t\t\t\t\"pos=({:.1f},{:.1f},{:.1f}) magVP={:.6g} - not a camera\",\r\n"
    "\t\t\t\t\t\tsnapArrivals,\r\n"
    "\t\t\t\t\t\ta_src.CameraProj.data[3][0], a_src.CameraProj.data[3][1],\r\n"
    "\t\t\t\t\t\ta_src.CameraProj.data[3][2], a_src.CameraProj.data[3][3],\r\n"
    "\t\t\t\t\t\ta_src.CameraPreviousPosAdjust[0], a_src.CameraPreviousPosAdjust[1],\r\n"
    "\t\t\t\t\t\ta_src.CameraPreviousPosAdjust[2], px, py, pz,\r\n"
    "\t\t\t\t\t\tcamMag(a_src.CameraViewProjUnjittered));\r\n"
    "\t\t\t\t}\r\n"
    "\t\t\t\tif (snapSkipsSinceCam < kCamCaptureFallbackSkips)\r\n"
    "\t\t\t\t\treturn false;\r\n"
    "\t\t\t} else {\r\n"
    "\t\t\t\tsnapSkipsSinceCam = 0;\r\n"
    "\t\t\t}\r\n"
    "\t\t}\r\n"
    "\r\n"
    "\t\t// ---- v0.89: SHAPE rejection REMOVED (was v0.86) ----------------------\r\n"
)

# --------------------------------------------------------------------------
# 3) [CAM] pub -- add the two capture-gate counters
# --------------------------------------------------------------------------
PUB_FMT_OLD = '"fMove={:.1f} takeover={} stalePub={} | {}",'
PUB_FMT_NEW = '"fMove={:.1f} takeover={} stalePub={} cap={}/{} | {}",'

PUB_ARG_OLD = (
    "\t\t\t\t\t\tsnapPubStale,\r\n"
    "\t\t\t\t\t\tsnapMatChanges == 0u"
)
PUB_ARG_NEW = (
    "\t\t\t\t\t\tsnapPubStale,\r\n"
    "\t\t\t\t\t\tsnapNonCamera, snapSkipsSinceCam,\r\n"
    "\t\t\t\t\t\tsnapMatChanges == 0u"
)

# --------------------------------------------------------------------------
# 4) FrameGen.h -- the two counters
# --------------------------------------------------------------------------
H_OLD = (
    "\tstd::uint64_t snapPubStale = 0;\r\n"
    "\tbool  snapPubHaveMat = false;\r\n"
    "\tfloat snapPubLastMat[4][4] = {};\r\n"
)

H_NEW = (
    "\tstd::uint64_t snapPubStale = 0;\r\n"
    "\tbool  snapPubHaveMat = false;\r\n"
    "\tfloat snapPubLastMat[4][4] = {};\r\n"
    "\r\n"
    "\t// ---- v1.13: capture-side content filter ----\r\n"
    "\t// The perFrame constant buffer is mapped ~22 times per rendered frame and\r\n"
    "\t// only one of those writes is the engine's camera.  snapNonCamera counts\r\n"
    "\t// the snapshots dropped because CameraProj is orthographic (no perspective\r\n"
    "\t// divide), snapSkipsSinceCam counts them consecutively and drives the\r\n"
    "\t// fallback that abandons the filter.  Both are printed by [CAM] pub as\r\n"
    "\t// `cap={}/{}`.  A healthy world run looks like cap=~fps/0..30.\r\n"
    "\tstd::uint64_t snapNonCamera = 0;\r\n"
    "\tstd::uint64_t snapSkipsSinceCam = 0;\r\n"
)

# --------------------------------------------------------------------------
# plan: (path, label, old, new, expected_count_of_old)
# --------------------------------------------------------------------------
PLAN = [
    (F_CPP, "constants", CONST_OLD, CONST_NEW, 1),
    (F_CPP, "the gate", GATE_OLD, GATE_NEW, 1),
    (F_CPP, "pub format", PUB_FMT_OLD, PUB_FMT_NEW, 1),
    (F_CPP, "pub args", PUB_ARG_OLD, PUB_ARG_NEW, 1),
    (F_H, "counters", H_OLD, H_NEW, 1),
]


def file_eol(path):
    """Decide the line ending from the FILE, never from the anchor: a
    single-line anchor contains no newline at all, and guessing from it is
    what silently converted FrameGen.cpp to bare LF in v1.09."""
    raw = open(path, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    return "\r\n" if crlf >= lf else "\n"


def post_conditions(path, text):
    bad = []
    if path == F_CPP:
        # Assert on the DECLARATION, not on the identifier: a correct comment is
        # allowed to name a constant (the v1.11 post-condition got this wrong and
        # reported a false failure).  Identifier counts are kept loose.
        for probe, want in [
            ("constexpr float kCamProjDivideMin = 0.05f;", 1),
            ("constexpr float kCamProjWMax = 0.05f;", 1),
            ("constexpr std::uint64_t kCamCaptureFallbackSkips = 6000;", 1),
            ("snapNonCamera", 3),              # ++ / gate log / pub arg
            ("snapSkipsSinceCam", 4),          # ++ / compare / reset / pub arg
            ("NON-CAMERA write dropped", 1),
            (MARK_C, 1),
        ]:
            if text.count(probe) != want:
                bad.append(f"{path}: {probe!r} count={text.count(probe)} want {want}")
        for probe, least in [
            ("kCamProjDivideMin", 2),
            ("kCamProjWMax", 2),
            ("kCamCaptureFallbackSkips", 2),
        ]:
            if text.count(probe) < least:
                bad.append(f"{path}: {probe!r} appears {text.count(probe)}x, want >= {least}")
        if "stalePub={} | {}" in text:
            bad.append(f"{path}: the pub format string was not extended")
    else:
        for probe, want in [
            ("\tstd::uint64_t snapNonCamera = 0;", 1),
            ("\tstd::uint64_t snapSkipsSinceCam = 0;", 1),
            ("kCamCaptureFallbackSkips", 0),
        ]:
            if text.count(probe) != want:
                bad.append(f"{path}: {probe!r} count={text.count(probe)} want {want}")
    return bad


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    print(f"mode        : {'REVERT' if revert else 'PATCH'}{' + APPLY' if apply else ' (dry run)'}")
    print()

    # ---- idempotency guard on the RESULT of a previous run -----------------
    cpp = open(F_CPP, encoding="utf-8", newline="").read()
    if not revert and MARK in cpp:
        print(f"REFUSED, nothing written (already applied: {MARK!r} present)")
        return 1

    edits = {}
    for path, label, old, new, want in PLAN:
        src = edits.get(path) or open(path, encoding="utf-8", newline="").read()
        eol = file_eol(path)
        o = old.replace("\r\n", eol)
        n = new.replace("\r\n", eol)
        if revert:
            o, n = n, o
        cnt = src.count(o)
        ok = (cnt == want)
        print(f"  {path:18s} {label:12s} count(old)={cnt} want={want}  "
              f"{'OK' if ok else '<<< MISMATCH'}")
        if not ok:
            print("\nREFUSED, nothing written (anchor not unique / stale)")
            return 2
        edits[path] = src.replace(o, n, 1)

    print()
    total = 0
    for path, text in edits.items():
        eol = file_eol(path)
        bad = post_conditions(path, text)
        if bad:
            print(f"  {path}: POST-CONDITIONS FAILED")
            for b in bad:
                print(f"      {b}")
            print("REFUSED, nothing written")
            return 3
        nb = text.encode("utf-8")
        total += len(nb)
        print(f"  {path:18s} -> {len(nb)} B, post-conditions PASS")

    if not apply:
        print("\n(dry run: nothing written; pass --apply)")
        return 0

    for path, text in edits.items():
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    print(f"\nAPPLIED (total {total} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
