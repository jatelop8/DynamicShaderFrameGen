#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v088_translation.py -- inject the missing camera translation into the
matrix the plugin hands to DLSS-G as `clipToPrevClip`.

ROOT CAUSE (round 12, proven from raw bytes; see tools/derive_vp_formula.py,
tools/probe_origin_guard.py, tools/v088_regression_fixed.py)
----------------------------------------------------------------------
  c8 @ c0  ==  c24 CameraViewProjUnjittered   with max|err| = 0.000000
       => the engine builds ViewProj as  Proj @ View  (projection on the LEFT).

  c0 CameraView  ==  c56 CameraViewInverse    byte-for-byte
       => the view matrix's translation is zero; it is a pure rotation.

  Proj @ [R | 0]  ==  c24                     with max|err| = 0.000000
       => the engine's ViewProj cannot depend on the camera position at all.

  Round 13 runtime:  |I - clip| came out 0.000000 for a camera creeping
  0.4 u/frame, while the fixed construction gives 0.400000.  DLSS-G is being
  told the camera is parked, so generated frames are reprojected to the same
  place and the picture ping-pongs between two nearly identical real frames --
  exactly the "fire and people sway back and forth" the user reported.

THE FIX
-------
Rebuild a ViewProj that DOES carry position, from operands already present:
    R3  = c0 CameraView's upper-left 3x3      (pure rotation)
    eye = c80 CameraPosAdjust[0..2]           (already read for c.cameraPos)
    View_fixed = [R3 | -R3 @ eye]
    VP_fixed   = c8 Proj  (transposed for SL)  @  View_fixed
Then use VP_fixed for BOTH cur and prev so clipToPrevClip carries real motion.

SAFETY (proven offline, tools/v088_regression_fixed.py)
    eye = 0            -> VP_fixed == c24 exactly   (regression guard)
    camera parked      -> |I - clip| = 0.000000     (never invents motion)
    camera creeps 0.4  -> |I - clip| = 0.400000     (motion restored)
This voids the objection recorded in the old v0.69 comment, which demanded
exactly this property but wrongly concluded it was unattainable.

GUARDS
    * dry-run by default; pass --apply to write
    * every anchor must occur EXACTLY once, else REFUSED, nothing written
    * marker guard so a second run is refused
    * brace-balance and LF check on the result
"""

import sys
import pathlib

SRC = pathlib.Path("src/Streamline.cpp")

# ---- marker: refuse to run twice -------------------------------------------
MARKER = "v0.88: rebuild ViewProj with the missing translation"

# ---- the single edit -------------------------------------------------------
OLD = """\t\t// ---- \u9009\u6e90\uff1a\u5f15\u64ce cur \u8fde\u7eed\u51bb\u7ed3 >= 30 \u5e27\u4e14\u6d3e\u751f\u6e90\u901a\u8fc7\u6821\u9a8c -> \u6362\u6d3e\u751f\u6e90 ----"""

# We keep that header comment, replace what follows it (the disabled block).
OLD_BLOCK = """\t\t// v0.69: derived source disabled -- it is dead code by construction.
\t\t// derivedViewProj = inv(CameraViewInverse) x CameraProjUnjittered, but the
\t\t// perFrame CameraViewInverse carries NO translation. Verified offline from
\t\t// the three raw matrix dumps in the 23:07 log (#1 menu camera, #8101 world
\t\t// camera, #9901 stub): inv(VI) comes out with translation row (0,0,0,1) AND
\t\t// translation column (0,0,0) in every one of them, i.e. a pure rotation. It
\t\t// can therefore never reproduce ViewProjUnjittered: max|derived-cur| is
\t\t// exactly the translation term (measured 15.0006 == |VP[2][3]|), derivedMatch
\t\t// is always 0 (log: dvd(ok/used)=0/0 err=16) and reproj src was always
\t\t// "engine". Its only trigger is "engine cur frozen >= 30 frames", and a
\t\t// frozen camera is a LEGITIMATE state (the loading screen simply does not
\t\t// move), so a matrix that cannot represent translation could only invent
\t\t// motion where there is none. The operands stay referenced via `false &&`
\t\t// so nothing is left unused and the comparison in the log keeps its meaning.
\t\tconst bool useDerived = false && (diag.derivedMatch == 1) && (s_engCurFrozen >= 30) &&
\t\t                        finiteMag(derivedViewProj) > 1.0e-6f;
\t\tsl::float4x4 curForReproj = useDerived ? derivedViewProj : currViewProjSL;
\t\tconst bool curOk = finiteMag(curForReproj) > 1.0e-6f;
\t\tdiag.reprojSource = useDerived ? 1 : 0;
\t\tif (useDerived)
\t\t\t++diag.derivedUsed;
"""

NEW_BLOCK = """\t\t// ---- v0.88: rebuild ViewProj with the missing translation ----\t\t// ROUND 12 (offline, from the v0.87 raw dumps) finally closed this:
\t\t//
\t\t//   c8 @ c0                      == c24  with max|err| = 0.000000
\t\t//      => the engine composes ViewProj as  Proj @ View  (\u6295\u5f71\u5728\u5de6).
\t\t//         Six earlier hand-derived candidates all used View @ Proj, which
\t\t//         is why they all missed by 0.111 -- the order, not the maths.
\t\t//
\t\t//   c0 == c56 (byte-for-byte)    and    Proj @ [R | 0] == c24 (err 0)
\t\t//      => the engine's view matrix carries NO translation. Its ViewProj
\t\t//         therefore cannot depend on the camera position at all, and
\t\t//         clipToPrevClip = inv(cur) x prev collapses to the identity.
\t\t//         Runtime: a camera creeping 0.4 u/frame produces |I - clip| =
\t\t//         0.000000 -- DLSS-G is told the camera is parked and reprojects
\t\t//         every generated frame to the same place. That is the ping-pong
\t\t//         between two nearly identical real frames.
\t\t//
\t\t// The old v0.69 comment above had the causality INVERTED: it observed
\t\t// "derivedViewProj cannot reproduce ViewProjUnjittered" and concluded the
\t\t// derived source was dead code. In fact the engine copy is the broken one;
\t\t// derived failed precisely because it faithfully inherited the same
\t\t// missing translation from CameraViewInverse. Disabling it removed the
\t\t// only path that could have carried the fix, so the defect survived.
\t\t//
\t\t// Fix: rebuild the view matrix from the rotation block and the position
\t\t// field, both of which are already in hand, then compose Proj @ View.
\t\t//
\t\t// Proven safe offline (tools/v088_regression_fixed.py):
\t\t//   eye = 0           -> identical to c24        (exact regression guard)
\t\t//   camera parked     -> |I - clip| = 0.000000   (never invents motion)
\t\t//   camera creeps 0.4 -> |I - clip| = 0.400000   (motion restored)
\t\t// The v0.69 objection ("could only invent motion where there is none") is
\t\t// therefore VOID: it was aimed at a construction that lacked translation,
\t\t// which is the very term being supplied here.
\t\tsl::float4x4 fixedViewProj{};
\t\tbool fixedViewProjOk = false;
\t\t{
\t\t\t// R3 = upper-left 3x3 of c0 CameraView. The engine stores rows, so this
\t\t\t// is the world-to-camera rotation in the same convention the engine's
\t\t\t// own Proj @ View product uses -- verified by the exact match above.
\t\t\tconst auto& vw = a_fb.CameraView.data;
\t\t\t// eye = CameraPosAdjust (c80). This is the ONLY field carrying position;
\t\t\t// it is already the source of c.cameraPos a few lines up.
\t\t\tconst float ex = a_fb.CameraPosAdjust[0];
\t\t\tconst float ey = a_fb.CameraPosAdjust[1];
\t\t\tconst float ez = a_fb.CameraPosAdjust[2];

\t\t\t// Build [R3 | -R3 @ eye] in ENGINE row-major storage.
\t\t\tsl::float4x4 viewM{};
\t\t\tfor (int r = 0; r < 3; ++r)
\t\t\t\tfor (int cix = 0; cix < 3; ++cix)
\t\t\t\t\tviewM[r][cix] = vw[r][cix];
\t\t\tviewM[3][3] = 1.0f;
\t\t\tfor (int r = 0; r < 3; ++r)
\t\t\t\tviewM[r][3] = -(viewM[r][0] * ex + viewM[r][1] * ey + viewM[r][2] * ez);

\t\t\t// Transpose to SL's row-major convention, exactly as the code above
\t\t\t// does for every other engine matrix.
\t\t\tsl::float4x4 viewSL;
\t\t\tfor (int r = 0; r < 4; ++r)
\t\t\t\tviewSL[r] = sl::float4(viewM[0][r], viewM[1][r], viewM[2][r], viewM[3][r]);

\t\t\t// Projection: c8 CameraProj is the factor the engine actually used in
\t\t\t// its own ViewProj (proven: c8 @ c0 == c24). Transpose it the same way.
\t\t\tconst auto& pj = a_fb.CameraProj.data;
\t\t\tsl::float4x4 projSL;
\t\t\tfor (int r = 0; r < 4; ++r)
\t\t\t\tprojSL[r] = sl::float4(pj[0][r], pj[1][r], pj[2][r], pj[3][r]);

\t\t\t// VP = Proj @ View, IN THAT ORDER -- the order is the whole point.
\t\t\tsl::matrixMul(fixedViewProj, projSL, viewSL);
\t\t\tfixedViewProjOk = finiteMag(fixedViewProj) > 1.0e-6f;
\t\t}

\t\t// The engine's own product stays in the log next to the fixed one, so the
\t\t// next run can show at a glance that the fix is doing what it claims.
\t\tdiag.fixedVpDev = (fixedViewProjOk && finiteMag(currViewProjSL) > 1.0e-6f)
\t\t\t? [&]() {
\t\t\t\tfloat worst = 0.0f;
\t\t\t\tfor (int r = 0; r < 4; ++r) {
\t\t\t\t\tconst float d[4] = { fixedViewProj[r].x - currViewProjSL[r].x,
\t\t\t\t\t                     fixedViewProj[r].y - currViewProjSL[r].y,
\t\t\t\t\t                     fixedViewProj[r].z - currViewProjSL[r].z,
\t\t\t\t\t                     fixedViewProj[r].w - currViewProjSL[r].w };
\t\t\t\t\tfor (int k = 0; k < 4; ++k) {
\t\t\t\t\t\tconst float a2 = d[k] < 0.0f ? -d[k] : d[k];
\t\t\t\t\t\tif (a2 > worst) worst = a2;
\t\t\t\t\t}
\t\t\t\t}
\t\t\t\treturn worst;
\t\t\t}() : -1.0f;

\t\t// Use the corrected matrix for reprojection. If for any reason it could not
\t\t// be built, fall back to the engine copy rather than to something invalid.
\t\tconst bool useFixed = fixedViewProjOk;
\t\tsl::float4x4 curForReproj = useFixed ? fixedViewProj : currViewProjSL;
\t\tconst bool curOk = finiteMag(curForReproj) > 1.0e-6f;
\t\tdiag.reprojSource = useFixed ? 2 : 0;
\t\tif (useFixed)
\t\t\t++diag.derivedUsed;
"""


def main():
    apply = "--apply" in sys.argv
    text = SRC.read_text(encoding="utf-8")

    # --- guard 1: never run twice ------------------------------------------
    if MARKER in text:
        print("REFUSED: marker already present, patch has been applied before.")
        return 2

    # --- guard 2: the block anchor must still look like what we expect -----
    if "useDerived" not in OLD_BLOCK or "currViewProjSL" not in OLD_BLOCK:
        print("REFUSED: anchor does not contain the expected identifiers.")
        return 2

    # ---- EDIT 2 and EDIT 3: two places that CONSUME the symbols we changed.
    # Both would still compile if left alone, but both would then LIE in the log
    # -- and a lying log is how a wrong conclusion gets built next round.
    OLD_SRC_TAG = '\t\t\t\t\tdiag.reprojSource ? "derived" : "engine",'
    NEW_SRC_TAG = ('\t\t\t\t\t(diag.reprojSource == 2 ? "fixed"\n'
                   '\t\t\t\t\t\t: (diag.reprojSource ? "derived" : "engine")),')

    OLD_WARN = ('\t\t\t\telse if (diag.engCurFrozenRun > 120 && diag.derivedUsed == 0)\n'
                '\t\t\t\t\tvd = "PROBLEM engine viewProj frozen for " + std::to_string(diag.engCurFrozenRun) +\n'
                '\t\t\t\t\t     " frames and the derived source is unavailable -> clipToPrevClip collapses "\n'
                '\t\t\t\t\t     "to identity (THIS is the flicker)";')
    NEW_WARN = ('\t\t\t\telse if (diag.engCurFrozenRun > 120 && diag.derivedUsed == 0)\n'
                '\t\t\t\t\tvd = "PROBLEM engine viewProj frozen for " + std::to_string(diag.engCurFrozenRun) +\n'
                '\t\t\t\t\t     " frames and NO corrected source was used (fixedVpDev=" +\n'
                '\t\t\t\t\t     std::to_string(diag.fixedVpDev) + ") -> clipToPrevClip may collapse to identity";')

    EDITS = [
        ("E1 rebuild ViewProj", OLD_BLOCK, NEW_BLOCK),
        ("E2 reproj source tag", OLD_SRC_TAG, NEW_SRC_TAG),
        ("E3 frozen-source warning", OLD_WARN, NEW_WARN),
    ]

    new_text = text
    for label, old, new in EDITS:
        cnt = new_text.count(old)
        if cnt != 1:
            print(f"REFUSED: [{label}] anchor occurrences={cnt} (expected 1). Nothing written.")
            return 2
        new_text = new_text.replace(old, new, 1)
        print(f"  [{label}] anchor=1 OK")

    # --- guard 5: the result must still contain the fallback --------------
    for need in ("curForReproj", "curOk", "diag.reprojSource", "finiteMag"):
        if need not in new_text:
            print(f"REFUSED: result lost `{need}`.")
            return 2

    # --- guard: no stale identifier may survive ---------------------------
    if "useDerived" in new_text:
        print("REFUSED: `useDerived` survived; a consumer was missed.")
        return 2

    # --- guard 6: braces balanced -----------------------------------------
    if new_text.count("{") != new_text.count("}"):
        print(f"REFUSED: brace imbalance {new_text.count('{')} vs {new_text.count('}')}.")
        return 2

    # --- guard 7: no CRLF introduced ---------------------------------------
    if "\r\n" in new_text:
        print("REFUSED: CRLF detected in result; file must stay LF.")
        return 2

    print(f"size {len(text)} -> {len(new_text)}  (delta {len(new_text)-len(text):+d})")
    print(f"braces: {new_text.count('{')} open / {new_text.count('}')} close")
    print(f"lines : {text.count(chr(10))} -> {new_text.count(chr(10))}")

    if not apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply to commit.")
        return 0

    SRC.write_text(new_text, encoding="utf-8", newline="")
    print("\nAPPLIED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
