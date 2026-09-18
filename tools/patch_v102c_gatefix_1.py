#!/usr/bin/env python3
"""
patch_v102c_gatefix_1.py -- v1.02c: drop the engine-prev gate in the v1.02 path.

WHY
===
v1.02 chose the previous camera like this:

    if (sameCamera(prevVP, curVP))  camPrevVP = camCurVP;   // identity
    else                            camPrevVP = rebuild(s_prevCam*);

That gate came from the old `engPrevEqCur` detector, on the assumption that
"the engine's prev equals cur" means "the camera did not move". The last run
proves that assumption is FALSE in this build:

    engPrevEqCur=331/331   engPrevDiffers=331   engPrevZero=0

Both counters grow at the same rate. That is only possible if
CameraPreviousViewProjUnjittered is a matrix that (a) never equals
CameraViewProjUnjittered -- so "differs" ticks -- and (b) never changes either,
so the log's `prevVP` column reads the same value as `curVP` at every heartbeat
(precision in that column is 4 decimals; the two matrices differ below it).

So the engine's prev field in this build is a STALE CONSTANT, most likely still
the menu camera. Gating on it means the identity branch fires on every frame and
v1.02 changes nothing -- exactly what the offline replay showed.

WHAT CHANGES
============
`sameCamera` stops being a gate and becomes an OBSERVATION. The previous camera
is always the rebuilt one. The still-camera case is then handled by the rebuild
itself, exactly:

    eye_prev == eye_cur  ->  prevView == curView  ->  camPrevVP == camCurVP
                                                        -> identity clip

so a genuinely parked camera still yields the identity, and no motion is
invented. The only difference from the gated version is that a camera which
moved while the engine's prev field stayed frozen now produces real motion
instead of the identity -- which is the entire point of the patch.

The counters are kept and renamed so the next run can confirm the engine's prev
field is indeed dead: engPrevEqCur / engPrevDiffers / engPrevZero are unchanged
and still print on the heartbeat.

Guards: --apply to write, exact-once anchors, post-conditions, eol preserved.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SL_CPP = os.path.join(ROOT, "src", "Streamline.cpp")


E1_OLD = (
    "\t\tsl::float4x4 camPrevVP{};\n"
    "\t\tbool camPrevOk = false;\n"
    "\t\tif (camCurOk && s_hasPrevCam) {\n"
    "\t\t\tif (sameCamera(prevVP, curVP)) {\n"
    "\t\t\t\tcamPrevVP = camCurVP;      // engine says still -> identity, as before\n"
    "\t\t\t\tcamPrevOk = true;\n"
    "\t\t\t} else {\n"
    "\t\t\t\tcamPrevOk = rebuildViewProj(s_prevCamView, s_prevCamEye,\n"
    "\t\t\t\t                            s_prevCamProj, camPrevVP) &&\n"
    "\t\t\t\t            finiteMagOf(camPrevVP) > 1.0e-6f;\n"
    "\t\t\t}\n"
    "\t\t}\n"
)

E1_NEW = (
    "\t\tsl::float4x4 camPrevVP{};\n"
    "\t\tbool camPrevOk = false;\n"
    "\t\tif (camCurOk && s_hasPrevCam) {\n"
    "\t\t\t// ---- v1.02c: the engine's prev field is NOT a motion sensor ------\n"
    "\t\t\t//\n"
    "\t\t\t// The previous run reported, on every heartbeat,\n"
    "\t\t\t//\n"
    "\t\t\t//     engPrevEqCur=331/331  engPrevDiffers=331  engPrevZero=0\n"
    "\t\t\t//\n"
    "\t\t\t// Both the \"equal\" and the \"differs\" counter climbed at the same\n"
    "\t\t\t// rate. That is impossible for a field that tracks the camera: it is\n"
    "\t\t\t// only possible if CameraPreviousViewProjUnjittered is a matrix that\n"
    "\t\t\t// never equals cur AND never changes -- a stale constant, in all\n"
    "\t\t\t// likelihood the menu camera left over from the 3D main menu.\n"
    "\t\t\t//\n"
    "\t\t\t// The heartbeat confirms it: prevVP reads equal to curVP to the four\n"
    "\t\t\t// decimals it prints, while clipDev sits at 0.000061 -- identity --\n"
    "\t\t\t// for every frame of a run in which the player was walking.\n"
    "\t\t\t//\n"
    "\t\t\t// So this field cannot decide anything. The still-camera case is\n"
    "\t\t\t// handled by the rebuild itself, exactly:\n"
    "\t\t\t//\n"
    "\t\t\t//     eye_prev == eye_cur -> prevView == curView -> camPrevVP == camCurVP\n"
    "\t\t\t//                         -> clipToPrevClip == I\n"
    "\t\t\t//\n"
    "\t\t\t// A parked camera therefore still yields identity, and a moving one\n"
    "\t\t\t// finally yields motion. `sameCamera` is left in place as the\n"
    "\t\t\t// documented predicate behind the engPrev* counters on the heartbeat.\n"
    "\t\t\tcamPrevOk = rebuildViewProj(s_prevCamView, s_prevCamEye,\n"
    "\t\t\t                            s_prevCamProj, camPrevVP) &&\n"
    "\t\t\t            finiteMagOf(camPrevVP) > 1.0e-6f;\n"
    "\t\t}\n"
)


E2_OLD = (
    "\t\t// The engine said \"the camera did not move\".\n"
    "\t\t//\n"
    "\t\t// This mirrors what the engine's prev used to express (prev == cur <=>\n"
    "\t\t// identity clipToPrevClip) and is deliberate for MENU / LOADING, where the\n"
    "\t\t// v0.69 note is explicit that identity is CORRECT. With the v1.02 prev now\n"
    "\t\t// carrying translation, a still camera would otherwise leave a one-frame\n"
    "\t\t// lag in the history that is indistinguishable from the\n"
    "\t\t// camera-retreats-from-eye defect the 3D map already exhibited. Choosing\n"
    "\t\t// identity here forecloses that regression by construction.\n"
    "\t\tauto sameCamera = [](const Matrix& a, const Matrix& b) -> bool {\n"
)

E2_NEW = (
    "\t\t// v1.02c: OBSERVATION ONLY -- feeds the engPrev* heartbeat counters and\n"
    "\t\t// documents why the engine's prev field is unusable as a motion source\n"
    "\t\t// (it never changes, so \"prev == cur\" and \"prev != cur\" are both noise).\n"
    "\t\t// The reprojection path does NOT consult it any more; see camPrevVP below.\n"
    "\t\tauto sameCamera = [](const Matrix& a, const Matrix& b) -> bool {\n"
)


E3_OLD = (
    "\t\t// The CURRENT camera, rebuilt. This is what becomes \"previous\" at the end\n"
    "\t\t// of the frame, so the history always carries a position.\n"
)

E3_NEW = (
    "\t\t// The CURRENT camera, rebuilt. This is what becomes \"previous\" at the end\n"
    "\t\t// of the frame, so the history always carries a position.\n"
    "\t\t// It is also the only motion source available: the engine's own prev and\n"
    "\t\t// cur ViewProj are both translation-free, and its prev field is frozen\n"
    "\t\t// outright (v1.02c evidence above).\n"
)


EDITS = [
    ("camPrevVP: drop the dead engine-prev gate", E1_OLD, E1_NEW),
    ("sameCamera -> observation only", E2_OLD, E2_NEW),
    ("note on the only motion source", E3_OLD, E3_NEW),
]

POST = [
    ("gate removed", "camPrevOk = rebuildViewProj(s_prevCamView"),
    ("observation comment", "v1.02c: OBSERVATION ONLY"),
    ("sameCamera still exists", "auto sameCamera = []"),
    ("rebuild still present", "auto rebuildViewProj = [&]"),
    ("diag counters intact", "diag.camPrevOk = camPrevOk ? 1 : 0;"),
    ("history uses rebuilt", "const sl::float4x4& advance = camCurOk ? camCurVP"),
    ("prev preferred", "prevForReproj = camPrevVP;"),
    ("engine prev converted", "engPrevViewProjSL[3] = sl::float4(prevVP.data[0][3]"),
]

# must NOT appear any more
ABSENT = [
    ("dead gate call", "if (sameCamera(prevVP, curVP)) {"),
    ("dead identity comment", "engine says still"),
]


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "\r\n" if crlf > lf else "\n"
    return raw.decode("utf-8"), eol


def fix_eol(s, eol):
    if eol == "\r\n":
        return s.replace("\r\n", "\n").replace("\n", "\r\n")
    return s.replace("\r\n", "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    text, eol = read_text(SL_CPP)
    print("Streamline.cpp: {} chars, eol={}".format(len(text), repr(eol)))

    bad = False
    for i, (label, old, new) in enumerate(EDITS, 1):
        n = text.count(fix_eol(old, eol))
        print("  [{}] {:2d}. {:<44} count={}".format("OK " if n == 1 else "BAD", i, label, n))
        if n != 1:
            bad = True
    if bad:
        print("REFUSED: anchor missing or not unique; nothing written.")
        return 2

    out = text
    for label, old, new in EDITS:
        out = out.replace(fix_eol(old, eol), fix_eol(new, eol), 1)

    ok = True
    for label, needle in POST:
        n = out.count(needle)
        print("  [{}] {:<40} count={}".format("OK " if n == 1 else "BAD", label, n))
        if n != 1:
            ok = False
    for label, needle in ABSENT:
        n = out.count(needle)
        print("  [{}] {:<40} count={}".format("OK " if n == 0 else "BAD", label, n))
        if n != 0:
            ok = False
    if not ok:
        print("REFUSED: post-conditions failed; nothing written.")
        return 3

    if not args.apply:
        print("DRY RUN: {} -> {} chars. Pass --apply to write.".format(len(text), len(out)))
        return 0

    bak = SL_CPP + ".bak-v102c"
    if not os.path.exists(bak):
        with open(bak, "wb") as f:
            f.write(text.encode("utf-8"))
    with open(SL_CPP, "wb") as f:
        f.write(out.encode("utf-8"))
    print("APPLIED: v1.02c gate removal ({} -> {} chars)".format(len(text), len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
