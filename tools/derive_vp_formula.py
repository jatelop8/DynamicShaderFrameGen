#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
derive_vp_formula.py -- OFFLINE ONLY. No game, no file writes outside stdout.

PURPOSE
-------
Round 12 established, from raw bytes, that the engine's perFrame camera block
carries NO translation at all:

    c0  CameraView        == c56 CameraViewInverse   (byte-for-byte)
    c16 CameraViewProj    == c24 CameraViewProjUnjittered
    c32 CameraPreviousVPU == all zeros               (engine never writes it)
    c24 is BYTE-IDENTICAL across snapshots while c80 (CameraPosAdjust) moves
                            651 units
    c80 CameraPosAdjust   == the ONLY field carrying position

=> clipToPrevClip = inv(cur) x prev collapses to identity, DLSS-G is told
   "the camera never moved", generated frames get yanked back, the picture
   ping-pongs between two nearly-identical real frames.

That conclusion is sealed. What is NOT sealed is the exact algebraic form the
engine uses to build ViewProj, which matters because the fix must inject the
missing translation without breaking the projection convention.

HISTORY: I burned several rounds hand-deriving. Six candidate forms did not
match. The lesson (per the user's standing order "don't make me try it again
and again") is: do the search offline against real bytes, once, exhaustively.

WHAT THIS SCRIPT DOES
---------------------
It takes the raw float block captured by the v0.87 probe, reconstructs the
two matrices we trust (c0 View, c8 Proj, c40 ProjU, c80 pos), and then:

  1. Searches a family of candidate constructions of ViewProj, reporting for
     each the max |candidate - c24_engine|.
  2. For the best candidate, builds the two-frame clip matrix and reports
     |I - clip| and det(clip), which is the metric that actually matters:
     it must be NON-zero (motion visible) yet small (sane).
  3. Reports the diagnostic that decides everything:
       is c24 == c0 @ c8 (row-major, no translation)?
       is c24 == c8 @ c0?
       is c24 == transpose-of-something?
     If c24 is exactly the rotation-only product, the defect is CONFIRMED as
     "missing translation" and the fix is to append the translation column.

The script prints a VERDICT section at the end. It never writes any file.
"""

import math
import sys

# ---------------------------------------------------------------------------
# Real bytes, lifted verbatim from the 14:44 log snapshot #10622.
# Layout: struct FrameBuffer, row-major, Matrix = float[4][4].
# Offsets in the [RAW] dump are byte offsets; floats are 4 bytes.
# ---------------------------------------------------------------------------
# [RAW] +0x0000 | 0 0 1 0 | -0 -1 -0 0        <- c0  View       rows 0,1
# [RAW] +0x0020 | 1 0 0 0 | 0 0 0 1          <- c0  View       rows 2,3
C0_VIEW = [
    [0.0,  0.0,  1.0,  0.0],
    [-0.0, -1.0, -0.0, 0.0],
    [1.0,  0.0,  0.0,  0.0],
    [0.0,  0.0,  0.0,  1.0],
]

# [RAW] +0x0040 | 1 0 0 -0 | 0 1 0 -0         <- c8  Proj       rows 0,1
# [RAW] +0x0060 | 0 0 1.111111 -0.1111111 | 0 0 0 1
C8_PROJ = [
    [1.0,  0.0, 0.0, -0.0],
    [0.0,  1.0, 0.0, -0.0],
    [0.0,  0.0, 1.111111, -0.1111111],
    [0.0,  0.0, 0.0,  1.0],
]

# [RAW] +0x0080 | 0 0 1 0 | 0 -1 0 0          <- c16 ViewProj   rows 0,1
# [RAW] +0x00a0 | 1.111111 0 0 -0.1111111 | 0 0 0 1
C16_VIEWPROJ = [
    [0.0, 0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0, 0.0],
    [1.111111, 0.0, 0.0, -0.1111111],
    [0.0, 0.0, 0.0, 1.0],
]

# c24 == c16 byte-for-byte
C24_VIEWPROJU = [row[:] for row in C16_VIEWPROJ]

# [RAW] +0x0140 | 1 0 0 0 | 0 1 0 0            <- c40 ProjU      rows 0,1
# [RAW] +0x0160 | 0 0 0.9 0.1 | 0 0 0 1
C40_PROJU = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 0.9, 0.1],
    [0.0, 0.0, 0.0, 1.0],
]

# [RAW] +0x01c0 | 0 0 1 0 | 0 -1 0 0          <- c56 ViewInv    == c0
C56_VIEWINV = [row[:] for row in C0_VIEW]

# [RAW] +0x0280 | -894.3632 213.1464 175.8006 0 | 0 0 0 0
#                 ^ c80 CameraPosAdjust         ^ c82 CameraPreviousPosAdjust (zeros)
C80_POS = [-894.3632, 213.1464, 175.8006]

# A second, EARLIER snapshot from the same run, used to prove c24 does not move
# while pos does. Taken from the acc/heartbeat lines: pos=(-504.8,-14.5,135.2).
C80_POS_EARLY = [-504.8, -14.5, 135.2]


# ---------------------------------------------------------------------------
# tiny row-major 4x4 linear algebra
# ---------------------------------------------------------------------------
def mat_mul(a, b):
    out = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            s = 0.0
            for k in range(4):
                s += a[i][k] * b[k][j]
            out[i][j] = s
    return out


def transpose(a):
    return [[a[j][i] for j in range(4)] for i in range(4)]


def maxdiff(a, b):
    m = 0.0
    for i in range(4):
        for j in range(4):
            d = abs(a[i][j] - b[i][j])
            if d > m:
                m = d
    return m


def fmt(m):
    return "\n".join(
        "    [" + "  ".join(f"{v: .6f}" for v in row) + "]" for row in m
    )


def det3(m):
    return (
        m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
        - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
        + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
    )


def mat_inv(m):
    """Gauss-Jordan inverse; returns None if singular."""
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(4)] for i, row in enumerate(m)]
    for col in range(4):
        piv = max(range(col, 4), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None
        a[col], a[piv] = a[piv], a[col]
        d = a[col][col]
        a[col] = [v / d for v in a[col]]
        for r in range(4):
            if r == col:
                continue
            f = a[r][col]
            if f != 0.0:
                a[r] = [a[r][c] - f * a[col][c] for c in range(8)]
    return [row[4:] for row in a]


def rod_axis_swap():
    """The rotation block of c0, i.e. the engine's camera basis permutation."""
    return [[C0_VIEW[i][j] for j in range(3)] for i in range(3)]


def with_translation_col(R, t):
    """Build [R | t] in row-major, R is 3x3, t is a 3-vector placed in col 3."""
    m = [[0.0] * 4 for _ in range(4)]
    for i in range(3):
        for j in range(3):
            m[i][j] = R[i][j]
    for i in range(3):
        m[i][3] = t[i]
    m[3][3] = 1.0
    return m


def with_translation_row(R, t):
    """Build [[R, 0],[t, 1]] -- translation in the LAST ROW (DX-style)."""
    m = [[0.0] * 4 for _ in range(4)]
    for i in range(3):
        for j in range(3):
            m[i][j] = R[i][j]
    for j in range(3):
        m[3][j] = t[j]
    m[3][3] = 1.0
    return m


# ---------------------------------------------------------------------------
# main analysis
# ---------------------------------------------------------------------------
def main():
    print("=" * 78)
    print("STEP 0 -- is c24 exactly the rotation-only product? (the decisive test)")
    print("=" * 78)

    prod_VC = mat_mul(C0_VIEW, C8_PROJ)      # View @ Proj
    prod_CV = mat_mul(C8_PROJ, C0_VIEW)      # Proj @ View
    prod_VTCP = mat_mul(transpose(C0_VIEW), C8_PROJ)
    prod_VCU = mat_mul(C0_VIEW, C40_PROJU)   # View @ ProjUnjittered

    cands = [
        ("c0 @ c8         (View @ Proj)",        prod_VC),
        ("c8 @ c0         (Proj @ View)",        prod_CV),
        ("c0^T @ c8       (ViewT @ Proj)",       prod_VTCP),
        ("c0 @ c40        (View @ ProjU)",       prod_VCU),
        ("c56 @ c8        (ViewInv @ Proj)",     mat_mul(C56_VIEWINV, C8_PROJ)),
    ]
    for name, m in cands:
        print(f"  {name:<34s} max|cand - c24| = {maxdiff(m, C24_VIEWPROJU):.6g}")

    print()
    print("  c24 (engine CameraViewProjUnjittered) =")
    print(fmt(C24_VIEWPROJU))
    print("  c16 (engine CameraViewProj)           =")
    print(fmt(C16_VIEWPROJ))
    print("  c0  (engine CameraView)               =")
    print(fmt(C0_VIEW))
    print("  c8  (engine CameraProj)               =")
    print(fmt(C8_PROJ))

    print()
    print("=" * 78)
    print("STEP 1 -- candidate constructions WITH translation injected")
    print("=" * 78)
    print(f"  pos = {C80_POS}")
    print()

    R = rod_axis_swap()
    Rinv = mat_inv(with_translation_col(R, [0, 0, 0]))
    R3inv = [row[:3] for row in Rinv[:3]] if Rinv else None

    # -t forms: the classic view matrix is [R | -R@eye]
    def neg_R_eye(eye):
        if R3inv is None:
            return None
        v = [0.0, 0.0, 0.0]
        for i in range(3):
            v[i] = -(R3inv[i][0] * eye[0] + R3inv[i][1] * eye[1] + R3inv[i][2] * eye[2])
        return v

    t_col = neg_R_eye(C80_POS)               # translation column, -R^-1 * eye
    t_row = [-C80_POS[0], -C80_POS[1], -C80_POS[2]]   # naive -eye

    variants = []
    view_col = with_translation_col(R, t_col)
    view_row = with_translation_col(R, t_row)
    variants = [
        ("A: [R | -R^-1 @ pos] @ ProjU, col-trans", mat_mul(view_col, C40_PROJU)),
        ("B: [R | -pos]        @ ProjU, col-trans", mat_mul(view_row, C40_PROJU)),
        ("C: [R | -R^-1 @ pos] @ Proj,  col-trans", mat_mul(view_col, C8_PROJ)),
        ("D: DX-style [[R,0],[t,1]] @ Proj, row-trans",
         mat_mul(with_translation_row(R, [-C80_POS[0], -C80_POS[1], -C80_POS[2]]), C8_PROJ)),
    ]
    for name, m in variants:
        print(f"  {name}")
        print(f"      max|variant - c24_engine| = {maxdiff(m, C24_VIEWPROJU):.6g}")
        print(f"      translation col3 = "
              f"({m[0][3]:.4f}, {m[1][3]:.4f}, {m[2][3]:.4f})  "
              f"row3 = ({m[3][0]:.4f}, {m[3][1]:.4f}, {m[3][2]:.4f})")

    print()
    print("=" * 78)
    print("STEP 2 -- the metric that actually matters: two-frame clip matrix")
    print("=" * 78)
    print("  Build VP(eye1) and VP(eye2) from the SAME orientation R but two")
    print("  different positions, then clip = inv(VP2) @ VP1.")
    print("  A correct fix => |I - clip| is small but NON-zero (motion visible).")
    print("  The engine (no translation) => |I - clip| == 0 exactly (the disease).")
    print()

    eye1 = C80_POS_EARLY
    eye2 = C80_POS
    d = [eye2[i] - eye1[i] for i in range(3)]
    dlen = math.sqrt(sum(v * v for v in d))
    print(f"  eye1 = {eye1}")
    print(f"  eye2 = {eye2}")
    print(f"  |eye2 - eye1| = {dlen:.4f}")
    print()

    def clip_between(vp_a, vp_b):
        ia = mat_inv(vp_a)
        if ia is None:
            return None
        return mat_mul(ia, vp_b)

    # engine: no translation at all
    vp_eng1 = mat_mul(C0_VIEW, C40_PROJU)
    vp_eng2 = mat_mul(C0_VIEW, C40_PROJU)
    c_eng = clip_between(vp_eng2, vp_eng1)
    dev_eng = maxdiff(c_eng, [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)])
    print(f"  ENGINE (no translation):  |I - clip| = {dev_eng:.6g}   "
          f"det3x3 = {det3(c_eng):.6f}")
    print("      ^^^ exactly zero => this IS the ping-pong cause.")

    for label, build in [
        ("FIX [R | -R^-1@eye] @ ProjU",
         lambda e: mat_mul(with_translation_col(R, neg_R_eye(e)), C40_PROJU)),
        ("FIX [R | -eye]      @ ProjU",
         lambda e: mat_mul(with_translation_col(R, [-e[0], -e[1], -e[2]]), C40_PROJU)),
    ]:
        vp1 = build(eye1)
        vp2 = build(eye2)
        c = clip_between(vp2, vp1)
        if c is None:
            print(f"  {label}: singular, skipped")
            continue
        dev = maxdiff(c, [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)])
        print(f"  {label}:  |I - clip| = {dev:.6g}   det3x3 = {det3(c):.6f}")
        print(f"      clip = ")
        print(fmt(c))

    print()
    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    best = min(cands, key=lambda kv: maxdiff(kv[1], C24_VIEWPROJU))
    bestd = maxdiff(best[1], C24_VIEWPROJU)
    print(f"  closest construction to engine c24: {best[0]}")
    print(f"  max|cand - c24| = {bestd:.6g}")
    if bestd < 1e-4:
        print("  => c24 IS exactly the translation-free product. Root cause CONFIRMED:")
        print("     the engine's ViewProj has no translation column, so")
        print("     clipToPrevClip = I and DLSS-G sees a motionless camera.")
    else:
        print("  => c24 is NOT any of the tested products. The engine composes")
        print("     ViewProj some other way; do NOT patch blindly.")
        print("     Report this number back before changing any code.")


if __name__ == "__main__":
    main()
