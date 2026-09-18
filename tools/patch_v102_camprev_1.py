#!/usr/bin/env python3
"""
patch_v102_camprev_1.py -- v1.02: self-maintained CAMERA history (position included).


WHY THIS PATCH EXISTS
=====================
v1.00 stopped the MENU camera from owning `frameBufferCopy` (proved by the
offline regression). The freeze has a SECOND, independent arm that no gate in
FrameGen.cpp can reach:

    clipToPrevClip = inv(cur) x prev

`cur` is rebuilt with translation (v0.88, `fixedViewProj`). But `prev` is the
*previous accepted frame* re-read from `frameBufferCopy`, i.e. the raw engine
CameraViewProjUnjittered -- and the engine composes THAT **without
translation** (c0 carries no translation block; c8 @ c0 == c24 with
max|err| = 0.000000, proven offline in v0.87).

Consequence on a frozen frame: the engine writes prev == cur byte-for-byte, so

    clipToPrevClip = inv(VP) x VP = I        (identity, on every frame)

DLSS-G is told "the camera did not move" -> every generated frame reprojects to
the same place -> the picture freezes while engine-native particles (fire) keep
animating. That is exactly the reported symptom
("基本上是冻结得，只有火还会一跳跳").


THE FIX
=======
Do not read `prev` from the engine's broken product. Rebuild the previous
camera from its own parts -- rotation AND position:

    prevView = [ R_prev | -R_prev @ eye_prev ]         (world -> camera)
    prevProj = CameraProj of the previous frame
    prevVP   = prevProj @ prevView                     (engine composition order)

`CameraView` is a pure rotation block, so the camera ORIENTATION is always
recoverable from it even when the engine's ViewProj product is frozen: only the
translation is missing from that product, and eye comes from CameraPosAdjust.


COMPOSABILITY -- THIS PATCH CANNOT REGRESS A FRAME THAT ALREADY WORKED
=====================================================================
The engine-prev detector is preserved exactly, by construction:

    sameCamera(A, B)  on the (engPrev, engCur) pair
        == the old `sameMat(engPrevViewProjSL, currViewProjSL)`

and the rebuild is exact when the previous camera was not moving:

    eye_prev == eye_cur   ->  prevView == curView   ->  prevVP == camCurVP
    eye_prev == 0         ->  prevView == [R | 0]   ->  prevVP == engine c24

(the second is the v0.88 offline regression condition). So:

  * engine prev == cur (frozen / menu / loading) -> identity, exactly as before
  * engine prev != cur (real motion)             -> was: a matrix harvested from
                                                    the menu-gimbal -> world
                                                    transition (garbage);
                                                    now: the actual composed
                                                    relative transform

`camCurVP` is the same camera the v0.88 `fixedViewProj` builds, so the frame
that already worked keeps working; `camPrevVP` only replaces the PREVIOUS half
of the pair, which is the half that was structurally blind to position.


GUARDS
======
* `--apply` required to write; the default is a dry run.
* Every anchor must occur EXACTLY once, or nothing is written (`REFUSED`).
* Post-conditions are asserted against the in-memory result before writing.
* The file's line endings are detected and preserved.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SL_CPP = os.path.join(ROOT, "src", "Streamline.cpp")


# ===========================================================================
# Edit 1 -- hoist finiteMagOf, then rebuild the previous camera.
# ===========================================================================
E1_OLD = (
    "\t\tengPrevViewProjSL[3] = sl::float4(prevVP.data[0][3], prevVP.data[1][3], "
    "prevVP.data[2][3], prevVP.data[3][3]);\n"
)

E1_NEW = (
    "\t\tengPrevViewProjSL[3] = sl::float4(prevVP.data[0][3], prevVP.data[1][3], "
    "prevVP.data[2][3], prevVP.data[3][3]);\n"
    "\n"
    "\t\t// v1.02: needed by the rebuild helper below; the original `finiteMag`\n"
    "\t\t// lambda is declared further down this function.\n"
    "\t\tauto finiteMagOf = [](const sl::float4x4& m) -> float {\n"
    "\t\t\tfloat mx = 0.0f;\n"
    "\t\t\tfor (int r = 0; r < 4; ++r) {\n"
    "\t\t\t\tconst float v[4] = { m[r].x, m[r].y, m[r].z, m[r].w };\n"
    "\t\t\t\tfor (int k = 0; k < 4; ++k) {\n"
    "\t\t\t\t\tconst float a = v[k] < 0.0f ? -v[k] : v[k];\n"
    "\t\t\t\t\tif (!(a <= 1.0e6f))\n"
    "\t\t\t\t\t\treturn 1.0e30f;\n"
    "\t\t\t\t\tif (a > mx)\n"
    "\t\t\t\t\t\tmx = a;\n"
    "\t\t\t\t}\n"
    "\t\t\t}\n"
    "\t\t\treturn mx;\n"
    "\t\t};\n"
    "\n"
    "\t\t// ---- v1.02: previous CAMERA (position included) ----------------------\n"
    "\t\t//\n"
    "\t\t// WHY THE ENGINE'S PREV CANNOT BE A REPROJECTION SOURCE\n"
    "\t\t//\n"
    "\t\t// The engine composes its ViewProj as  Proj @ [R | 0]  -- there is NO\n"
    "\t\t// translation term (proven offline: c0 == c56 byte-for-byte, and\n"
    "\t\t// Proj @ [R | 0] == c24 with max|err| = 0.000000). Its own product is\n"
    "\t\t// therefore blind to the camera position, and it writes prev := cur\n"
    "\t\t// verbatim, so on any frame it does not advance\n"
    "\t\t//\n"
    "\t\t//     clipToPrevClip = inv(VP) x VP = I\n"
    "\t\t//\n"
    "\t\t// and DLSS-G is told the camera never moved. `cur` was repaired in v0.88\n"
    "\t\t// by rebuilding it from R + eye; `prev` was still reading that broken\n"
    "\t\t// product, which is why the picture stayed frozen after v1.00.\n"
    "\t\t//\n"
    "\t\t// CameraView is a pure rotation block, so the camera ORIENTATION survives\n"
    "\t\t// even when the engine's ViewProj does not move: only the translation is\n"
    "\t\t// missing from that product, and eye comes from CameraPosAdjust.\n"
    "\t\tauto rebuildViewProj = [&](const Matrix& a_view, const float a_eye[3],\n"
    "\t\t                           const Matrix& a_proj, sl::float4x4& a_out) -> bool {\n"
    "\t\t\tconst float ex = a_eye[0];\n"
    "\t\t\tconst float ey = a_eye[1];\n"
    "\t\t\tconst float ez = a_eye[2];\n"
    "\t\t\tfloat vm[3][4] = {};\n"
    "\t\t\tfor (int r = 0; r < 3; ++r) {\n"
    "\t\t\t\tconst float m0 = a_view.data[r][0];\n"
    "\t\t\t\tconst float m1 = a_view.data[r][1];\n"
    "\t\t\t\tconst float m2 = a_view.data[r][2];\n"
    "\t\t\t\tif (!(m0 == m0) || !(m1 == m1) || !(m2 == m2))\n"
    "\t\t\t\t\treturn false;                       // NaN rotation row\n"
    "\t\t\t\tvm[r][0] = m0;\n"
    "\t\t\t\tvm[r][1] = m1;\n"
    "\t\t\t\tvm[r][2] = m2;\n"
    "\t\t\t\tvm[r][3] = -(m0 * ex + m1 * ey + m2 * ez);\n"
    "\t\t\t}\n"
    "\t\t\t// Transpose into SL's row-major convention, exactly as the surrounding\n"
    "\t\t\t// code does for every other engine matrix.\n"
    "\t\t\tsl::float4x4 viewSL;\n"
    "\t\t\tviewSL[0] = sl::float4(vm[0][0], vm[1][0], vm[2][0], 0.0f);\n"
    "\t\t\tviewSL[1] = sl::float4(vm[0][1], vm[1][1], vm[2][1], 0.0f);\n"
    "\t\t\tviewSL[2] = sl::float4(vm[0][2], vm[1][2], vm[2][2], 0.0f);\n"
    "\t\t\tviewSL[3] = sl::float4(vm[0][3], vm[1][3], vm[2][3], 1.0f);\n"
    "\t\t\tconst auto& pj = a_proj.data;\n"
    "\t\t\tsl::float4x4 projSL;\n"
    "\t\t\tprojSL[0] = sl::float4(pj[0][0], pj[1][0], pj[2][0], pj[3][0]);\n"
    "\t\t\tprojSL[1] = sl::float4(pj[0][1], pj[1][1], pj[2][1], pj[3][1]);\n"
    "\t\t\tprojSL[2] = sl::float4(pj[0][2], pj[1][2], pj[2][2], pj[3][2]);\n"
    "\t\t\tprojSL[3] = sl::float4(pj[0][3], pj[1][3], pj[2][3], pj[3][3]);\n"
    "\t\t\tsl::matrixMul(a_out, projSL, viewSL);   // Proj @ View, engine order\n"
    "\t\t\treturn true;\n"
    "\t\t};\n"
    "\n"
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
    "\t\t\tfor (int r = 0; r < 4; ++r)\n"
    "\t\t\t\tfor (int k = 0; k < 4; ++k) {\n"
    "\t\t\t\t\tconst float d = a.data[r][k] - b.data[r][k];\n"
    "\t\t\t\t\tif (!(d == d))\n"
    "\t\t\t\t\t\treturn false;                   // NaN\n"
    "\t\t\t\t\tif (d > 1.0e-9f || d < -1.0e-9f)\n"
    "\t\t\t\t\t\treturn false;\n"
    "\t\t\t\t}\n"
    "\t\t\treturn true;\n"
    "\t\t};\n"
    "\n"
    "\t\t// The previous camera, carried across frames as RAW ENGINE MATRICES so the\n"
    "\t\t// rebuild reuses the SAME code path as `cur` (no second convention).\n"
    "\t\t// static, not thread_local: v0.82 proved Present() is driven by two engine\n"
    "\t\t// threads in alternation, and history belongs to the PREVIOUS FRAME, not to\n"
    "\t\t// the previous thread.\n"
    "\t\tstatic Matrix s_prevCamView{};\n"
    "\t\tstatic Matrix s_prevCamProj{};\n"
    "\t\tstatic float s_prevCamEye[3] = { 0.0f, 0.0f, 0.0f };\n"
    "\t\tstatic bool s_hasPrevCam = false;\n"
    "\n"
    "\t\t// The CURRENT camera, rebuilt. This is what becomes \"previous\" at the end\n"
    "\t\t// of the frame, so the history always carries a position.\n"
    "\t\tsl::float4x4 camCurVP{};\n"
    "\t\tconst bool camCurOk =\n"
    "\t\t\trebuildViewProj(a_fb.CameraView, a_fb.CameraPosAdjust, a_fb.CameraProj, camCurVP) &&\n"
    "\t\t\tfiniteMagOf(camCurVP) > 1.0e-6f;\n"
    "\n"
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


# ===========================================================================
# Edit 2 -- diagnostics counter.
# ===========================================================================
E2_OLD = (
    "\t\tdiag.curMagLast = curOk ? finiteMag(curForReproj) : 0.0f;\n"
    "\t\tdiag.engPrevMagLast = finiteMag(engPrevViewProjSL);\n"
)

E2_NEW = (
    "\t\tdiag.curMagLast = curOk ? finiteMag(curForReproj) : 0.0f;\n"
    "\t\tdiag.engPrevMagLast = finiteMag(engPrevViewProjSL);\n"
    "\t\tdiag.camPrevOk = camPrevOk ? 1 : 0;\n"
)


# ===========================================================================
# Edit 3 -- history advances with the REBUILT camera, and camPrevVP wins.
# ===========================================================================
E3_OLD = (
    "\t\tstatic sl::float4x4 s_prevVP{};\n"
    "\t\tstatic bool s_hasPrevVP = false;\n"
    "\t\tsl::float4x4 prevForReproj{};\n"
    "\t\tbool havePrev = false;\n"
    "\t\tif (curOk) {\n"
    "\t\t\tif (s_hasPrevVP) {\n"
    "\t\t\t\tprevForReproj = s_prevVP;\n"
    "\t\t\t\thavePrev = true;\n"
    "\t\t\t}\n"
    "\t\t\ts_prevVP = curForReproj;\n"
    "\t\t\ts_hasPrevVP = true;\n"
    "\t\t}\n"
)

E3_NEW = (
    "\t\tstatic sl::float4x4 s_prevVP{};\n"
    "\t\tstatic bool s_hasPrevVP = false;\n"
    "\t\tsl::float4x4 prevForReproj{};\n"
    "\t\tbool havePrev = false;\n"
    "\t\tif (curOk) {\n"
    "\t\t\t// ---- v1.02: the history advances with the REBUILT camera ----------\n"
    "\t\t\t//\n"
    "\t\t\t// v0.66..v1.00 stored `curForReproj`, the engine-derived ViewProj,\n"
    "\t\t\t// which carries NO translation -- so the self-maintained history\n"
    "\t\t\t// inherited the very blindness it existed to cure: two frames of a\n"
    "\t\t\t// walking camera still produced clipToPrevClip == I.\n"
    "\t\t\t// camCurVP is that same camera rebuilt from R + eye.\n"
    "\t\t\tconst sl::float4x4& advance = camCurOk ? camCurVP : curForReproj;\n"
    "\t\t\tif (s_hasPrevVP) {\n"
    "\t\t\t\tprevForReproj = s_prevVP;\n"
    "\t\t\t\thavePrev = true;\n"
    "\t\t\t}\n"
    "\t\t\ts_prevVP = advance;\n"
    "\t\t\ts_hasPrevVP = true;\n"
    "\t\t}\n"
    "\t\t// ---- v1.02: prefer the rebuilt previous camera ------------------------\n"
    "\t\t//\n"
    "\t\t// camPrevVP is Proj @ [R_prev | -R_prev @ eye_prev]: the true composed\n"
    "\t\t// relative transform, translation included. It wins over both s_prevVP\n"
    "\t\t// and the engine's prev, and it is EXACT when the camera was still\n"
    "\t\t// (sameCamera -> camPrevVP == camCurVP), so switching to it cannot\n"
    "\t\t// introduce motion where there is none.\n"
    "\t\tif (camPrevOk) {\n"
    "\t\t\tprevForReproj = camPrevVP;\n"
    "\t\t\thavePrev = true;\n"
    "\t\t\t++diag.camPrevUsed;\n"
    "\t\t}\n"
)


EDITS = [
    ("hoist finiteMagOf + rebuild prev camera", E1_OLD, E1_NEW),
    ("diag.camPrevOk", E2_OLD, E2_NEW),
    ("history uses rebuilt camera; camPrevVP wins", E3_OLD, E3_NEW),
]

POST = [
    ("rebuildViewProj lambda", "auto rebuildViewProj = [&]"),
    ("sameCamera lambda", "auto sameCamera = []"),
    ("finiteMagOf hoisted", "auto finiteMagOf = [](const sl::float4x4& m) -> float"),
    ("prev camera rebuilt", "camPrevOk = rebuildViewProj(s_prevCamView"),
    ("still-camera identity", "camPrevVP = camCurVP;"),
    ("history uses rebuilt", "const sl::float4x4& advance = camCurOk ? camCurVP"),
    ("prev preferred", "prevForReproj = camPrevVP;"),
    ("diag ok counter", "diag.camPrevOk = camPrevOk ? 1 : 0;"),
    ("diag used counter", "++diag.camPrevUsed;"),
    ("engine-prev compat kept", "if (sameCamera(prevVP, curVP)) {"),
    ("engine prev STILL converted", "engPrevViewProjSL[3] = sl::float4(prevVP.data[0][3]"),
]


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "\r\n" if crlf > lf else "\n"
    return raw.decode("utf-8"), eol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    text, eol = read_text(SL_CPP)
    print("Streamline.cpp: {} chars, eol={}".format(len(text), repr(eol)))

    bad = False
    for i, (label, old, new) in enumerate(EDITS, 1):
        n = text.count(old)
        print("  [{}] {:2d}. {:<48} count={}".format("OK " if n == 1 else "BAD", i, label, n))
        if n != 1:
            bad = True
    if bad:
        print("REFUSED: anchor missing or not unique; nothing written.")
        return 2

    out = text
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)

    print("post-conditions:")
    ok = True
    for label, needle in POST:
        n = out.count(needle)
        print("  [{}] {:<40} count={}".format("OK " if n == 1 else "BAD", label, n))
        if n != 1:
            ok = False
    nconv = out.count("sl::float4x4 engPrevViewProjSL;")
    print("  [{}] {:<40} count={}".format("OK " if nconv == 1 else "BAD",
                                          "engPrevViewProjSL declared once", nconv))
    if nconv != 1:
        ok = False
    if not ok:
        print("REFUSED: post-conditions failed; nothing written.")
        return 3

    if eol == "\r\n":
        out = out.replace("\r\n", "\n").replace("\n", "\r\n")

    if not args.apply:
        print("DRY RUN: {} -> {} chars. Pass --apply to write.".format(len(text), len(out)))
        return 0

    backup = SL_CPP + ".bak-v102"
    if not os.path.exists(backup):
        with open(backup, "wb") as f:
            f.write(text.encode("utf-8"))
        print("backup: " + os.path.basename(backup))
    with open(SL_CPP, "wb") as f:
        f.write(out.encode("utf-8"))
    print("APPLIED: v1.02 camera-history patch ({} -> {} chars)".format(len(text), len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
