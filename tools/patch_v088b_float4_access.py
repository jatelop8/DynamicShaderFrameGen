#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v088b_float4_access.py -- fix the C2676 build errors.

WHAT WENT WRONG
---------------
v0.88's first draft treated sl::float4x4 as a plain 2-D array:
    viewM[r][cix] = vw[r][cix];
    viewM[r][3]   = ...;
That is wrong. Streamline defines
    struct float4  { float x, y, z, w; };          // NO operator[]
    struct float4x4 { float4 row[4]; };            // row[] exists, float4[] does not
so `viewM[r]` yields a float4 and the second subscript is the error.

The correct access pattern was ALREADY IN THE SAME FILE, twenty lines earlier
(the derived-source cross-check block), written component by component:
    derivedViewProj[r].x - currViewProjSL[r].x
I did not read it before writing, assumed the array form, and the compiler
caught it. Ten errors, all C2676, all on four lines.

Fix: rewrite the three loops to assign components explicitly.

Guards: dry-run default, unique anchors, marker, LF-only, brace balance.
"""

import sys
import pathlib

SRC = pathlib.Path("src/Streamline.cpp")
MARKER = "v0.88b: sl::float4 exposes only"

OLD = """\t\t\t// Build [R3 | -R3 @ eye] in ENGINE row-major storage.
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
"""

NEW = """\t\t\t// Build [R3 | -R3 @ eye] in ENGINE row-major storage.
\t\t\t//
\t\t\t// v0.88b: sl::float4 exposes only .x/.y/.z/.w -- there is no subscript
\t\t\t// operator on it. The first draft treated the type as a 2-D array and
\t\t\t// produced ten C2676 errors. The component-wise pattern below is the
\t\t\t// same one the cross-check block above already uses.
\t\t\tfloat vm[3][4] = {};                    // plain array: no SL type involved
\t\t\tfor (int r = 0; r < 3; ++r) {
\t\t\t\tvm[r][0] = vw[r][0];
\t\t\t\tvm[r][1] = vw[r][1];
\t\t\t\tvm[r][2] = vw[r][2];
\t\t\t\tvm[r][3] = -(vw[r][0] * ex + vw[r][1] * ey + vw[r][2] * ez);
\t\t\t}

\t\t\t// Transpose into SL's row-major convention, exactly as the surrounding
\t\t\t// code does for every other engine matrix (s[0]=col0, s[1]=col1, ...).
\t\t\tsl::float4x4 viewSL;
\t\t\tviewSL[0] = sl::float4(vm[0][0], vm[1][0], vm[2][0], 0.0f);
\t\t\tviewSL[1] = sl::float4(vm[0][1], vm[1][1], vm[2][1], 0.0f);
\t\t\tviewSL[2] = sl::float4(vm[0][2], vm[1][2], vm[2][2], 0.0f);
\t\t\tviewSL[3] = sl::float4(vm[0][3], vm[1][3], vm[2][3], 1.0f);

\t\t\t// Projection: c8 CameraProj is the factor the engine actually used in
\t\t\t// its own ViewProj (proven: c8 @ c0 == c24). Transpose it the same way.
\t\t\tconst auto& pj = a_fb.CameraProj.data;
\t\t\tsl::float4x4 projSL;
\t\t\tprojSL[0] = sl::float4(pj[0][0], pj[1][0], pj[2][0], pj[3][0]);
\t\t\tprojSL[1] = sl::float4(pj[0][1], pj[1][1], pj[2][1], pj[3][1]);
\t\t\tprojSL[2] = sl::float4(pj[0][2], pj[1][2], pj[2][2], pj[3][2]);
\t\t\tprojSL[3] = sl::float4(pj[0][3], pj[1][3], pj[2][3], pj[3][3]);
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

    new = text.replace(OLD, NEW, 1)

    # The guard must inspect ONLY the region this patch rewrites. Scanning the
    # whole file is a false positive: the pre-existing transposes elsewhere
    # legitimately use the single-subscript form `viewSL[0] = sl::float4(...)`.
    seg_start = new.find("Build [R3 | -R3 @ eye] in ENGINE row-major storage.")
    seg_end = new.find("// VP = Proj @ View, IN THAT ORDER")
    if seg_start < 0 or seg_end < 0 or seg_end <= seg_start:
        print("REFUSED: could not isolate the rewritten region for inspection.")
        return 2
    segment = new[seg_start:seg_end]
    for bad in ("viewM[", "vm[r][0] * ex ", "projSL[r]", "viewSL[r]"):
        if bad in segment:
            print(f"REFUSED: offending pattern `{bad}` survived in the rewritten region.")
            return 2

    if new.count("{") != new.count("}"):
        print(f"REFUSED: brace imbalance {new.count('{')} vs {new.count('}')}.")
        return 2
    if "\r\n" in new:
        print("REFUSED: CRLF introduced; file must stay LF.")
        return 2

    print(f"anchor=1 OK, size {len(text)} -> {len(new)} (delta {len(new)-len(text):+d})")
    if not apply:
        print("DRY RUN -- nothing written.")
        return 0

    SRC.write_text(new, encoding="utf-8", newline="")
    print("APPLIED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
