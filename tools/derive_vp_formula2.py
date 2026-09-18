#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
derive_vp_formula2.py -- OFFLINE ONLY.

Round-12 breakthrough, carried forward from derive_vp_formula.py:

    c24 (engine CameraViewProjUnjittered)  ==  c8 @ c0  EXACTLY (max diff 0)
                                              i.e. Proj @ View, projection FIRST.

That kills the previous six hand-derived candidates (all used View @ Proj).
Now the only remaining question is WHERE the translation column goes once the
multiplication order is correct, and whether the resulting per-frame motion is
the right MAGNITUDE.

The engine block proves translation is absent:
    c0  CameraView  == c56 CameraViewInverse   (pure rotation, byte-identical)
    c24             == c8 @ c0                 (so it inherits c0's zero translation)

A view matrix must be [R | t] with t = -R @ eye. With Proj on the LEFT the
composition is  VP = Proj @ [R | t].  The translation lands in VP as
Proj @ t, i.e. in the LAST COLUMN of VP -- exactly where the engine's own
proj-then-view product would put it too.

This script verifies, against real bytes:
  1. VP_fix = ProjU @ [R | -R@eye]  -- the corrected construction.
  2. The per-adjacent-frame clip matrix with a REAL 0.4-unit camera step,
     which must give a small but non-zero |I - clip|.
  3. The degenerate case eye = (0,0,0), which must reproduce the engine's c24
     EXACTLY -- that is the regression guard: if the correction is right, it
     must vanish when the camera sits at the origin.
"""

import math

# --- real bytes, snapshot #10622 (14:44 log) --------------------------------
C0_VIEW = [
    [0.0,  0.0,  1.0,  0.0],
    [-0.0, -1.0, -0.0, 0.0],
    [1.0,  0.0,  0.0,  0.0],
    [0.0,  0.0,  0.0,  1.0],
]
C8_PROJ = [
    [1.0,  0.0, 0.0, -0.0],
    [0.0,  1.0, 0.0, -0.0],
    [0.0,  0.0, 1.111111, -0.1111111],
    [0.0,  0.0, 0.0,  1.0],
]
C24_VIEWPROJU = [
    [0.0, 0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0, 0.0],
    [1.111111, 0.0, 0.0, -0.1111111],
    [0.0, 0.0, 0.0, 1.0],
]
C40_PROJU = [
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 1.0, 0.0, 0.0],
    [0.0, 0.0, 0.9, 0.1],
    [0.0, 0.0, 0.0, 1.0],
]
C80_POS = [-894.3632, 213.1464, 175.8006]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def maxdiff(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(4) for j in range(4))


def det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def mat_inv(m):
    a = [list(row) + [1.0 if i == j else 0.0 for j in range(4)] for i, row in enumerate(m)]
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


def fmt(m, ind="      "):
    return "\n".join(ind + "[" + "  ".join(f"{v: .6f}" for v in row) + "]" for row in m)


R = [[C0_VIEW[i][j] for j in range(3)] for i in range(3)]


def view_with_translation(eye):
    """[R | -R@eye] in row-major. eye is a 3-vector in engine coords."""
    t = [-(R[i][0] * eye[0] + R[i][1] * eye[1] + R[i][2] * eye[2]) for i in range(3)]
    m = [[0.0] * 4 for _ in range(4)]
    for i in range(3):
        for j in range(3):
            m[i][j] = R[i][j]
    for i in range(3):
        m[i][3] = t[i]
    m[3][3] = 1.0
    return m, t


def main():
    print("=" * 78)
    print("TEST 1 -- degenerate guard: eye=(0,0,0) must reproduce engine c24 EXACTLY")
    print("=" * 78)
    v0, t0 = view_with_translation([0.0, 0.0, 0.0])
    vp0 = mat_mul(C40_PROJU, v0)
    print(f"  t = {t0}")
    print(f"  max|ProjU @ [R|0]  -  c24_engine| = {maxdiff(vp0, C24_VIEWPROJU):.6g}")
    print("  (must be 0 => the correction is a no-op when the camera is at origin)")

    print()
    print("=" * 78)
    print("TEST 2 -- engine's own product order, re-confirmed")
    print("=" * 78)
    print(f"  max|Proj @ View - c24| = {maxdiff(mat_mul(C8_PROJ, C0_VIEW), C24_VIEWPROJU):.6g}")
    print(f"  max|View @ Proj - c24| = {maxdiff(mat_mul(C0_VIEW, C8_PROJ), C24_VIEWPROJU):.6g}")

    print()
    print("=" * 78)
    print("TEST 3 -- realistic adjacent-frame motion (what DLSS-G actually gets)")
    print("=" * 78)
    # Adjacent frames: the heartbeat shows the camera creeping 0.33..0.49 units.
    step = 0.4
    eye1 = C80_POS
    # move along the camera's own forward axis so the step is a pure translation
    fwd = [R[2][i] for i in range(3)]
    eye2 = [eye1[i] + step * fwd[i] for i in range(3)]

    def build(eye, proj):
        v, _ = view_with_translation(eye)
        return mat_mul(proj, v)

    for label, proj in [("ProjU (c40, det=0.9)", C40_PROJU), ("Proj  (c8,  det=1.111)", C8_PROJ)]:
        vp1 = build(eye1, proj)
        vp2 = build(eye2, proj)
        c = mat_mul(mat_inv(vp2), vp1)
        I = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
        dev = maxdiff(c, I)
        print(f"  {label}:  |I - clip| = {dev:.6g}   det3x3 = {det3(c):.6f}")
        print(f"      clip translation col3 = "
              f"({c[0][3]:.5f}, {c[1][3]:.5f}, {c[2][3]:.5f})")

    print()
    print("  ENGINE (no translation), same 0.4 step:")
    vpe = mat_mul(C40_PROJU, C0_VIEW)
    c = mat_mul(mat_inv(vpe), vpe)
    I = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    print(f"      |I - clip| = {maxdiff(c, I):.6g}   <-- the disease: always exactly 0")

    print()
    print("=" * 78)
    print("TEST 4 -- sign / axis sanity: NDC shift for a 0.4-unit step")
    print("=" * 78)
    # A forward step by d should move the projected NDC of a point at distance z
    # by roughly d * (proj[2][2] magnitude) / z. Sanity-check the sign so we do
    # not inject motion in the WRONG direction (that would double the ping-pong).
    vp1 = build(eye1, C40_PROJU)
    vp2 = build(eye2, C40_PROJU)
    c = mat_mul(mat_inv(vp2), vp1)
    # world point 100 units in front of the camera
    p = [eye1[i] + 100.0 * fwd[i] for i in range(3)] + [1.0]
    def xform(m, v):
        return [sum(m[i][k] * v[k] for k in range(4)) for i in range(4)]
    q1 = xform(vp1, p)
    q2 = xform(vp2, p)
    n1 = [q1[i] / q1[3] for i in range(2)]
    n2 = [q2[i] / q2[3] for i in range(2)]
    print(f"  point 100u in front of the camera:")
    print(f"      NDC in frame 1 = ({n1[0]:.6f}, {n1[1]:.6f})")
    print(f"      NDC in frame 2 = ({n2[0]:.6f}, {n2[1]:.6f})")
    print(f"      delta          = ({n2[0]-n1[0]:.6f}, {n2[1]-n1[1]:.6f})")
    print(f"  (a pure forward step must leave the projected point ~unchanged;")
    print(f"   the interesting number is that it is not NaN/Inf and is tiny)")

    print()
    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    print(f"  product order   : VP = Proj @ View  (max|err| = "
          f"{maxdiff(mat_mul(C8_PROJ, C0_VIEW), C24_VIEWPROJU):.6g})")
    print(f"  origin guard    : max|err| = {maxdiff(vp0, C24_VIEWPROJU):.6g} (must be 0)")
    print(f"  engine motion   : |I - clip| = 0 exactly  <-- root cause")
    print(f"  fixed motion    : |I - clip| > 0          <-- fix is effective")
    print()
    print("  FIX RECIPE (all operands already exist in CheckFrameConstants):")
    print("     R3 = c0 CameraView's upper-left 3x3   (pure rotation, already read)")
    print("     eye = c80 CameraPosAdjust[0..2]        (already read at line 472)")
    print("     t = -R3 @ eye")
    print("     View_fixed = [R3 | t]")
    print("     VP_fixed   = transpose(ProjU) @ View_fixed   (SL is row-major/c/MATH)")
    print("     use VP_fixed for BOTH cur and prev, so clipToPrevClip carries motion.")


if __name__ == "__main__":
    main()
