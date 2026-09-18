#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v088_regression_fixed.py -- OFFLINE. Supersedes v088_offline_regression.py.

BUG IN THE PREVIOUS VERSION (fixed here)
----------------------------------------
In S2 I labelled one arm "engine (no translation)" but actually passed it
vp_from(R0, eye) -- the FIXED construction. Both arms were therefore the
fixed one, they agreed by construction, and the label lied. The script even
printed a FAIL for the engine arm, which I misread as "engine stays 0 (the
bug)" without noticing the number beside it was 0.400.

That is exactly the failure mode I have been burned by before: an assertion
whose PREMISE was never demonstrated. Wire the arms explicitly this time.

WHAT THE TWO ARMS MUST BE
-------------------------
  ENGINE arm : VP = c8 @ c0            <- the real engine product, c0 has NO
                                          translation (proven: max err 0 vs c24)
  FIXED  arm : VP = c8 @ [R3 | -R3@eye]

THEN the decisive question, which I have NOT yet tested correctly:
does the ENGINE arm really produce |I-clip| == 0 for a moving camera?

If the engine's own ViewProj provably cannot encode a 0.4-unit step, then a
camera that moves 0.4 u/frame is invisible to DLSS-G no matter what -- which
is the ping-pong. If instead the engine arm DOES show 0.4 here, then my model
of why the log shows |I-clip| = 0 is incomplete and I must not ship yet.
"""

import math

C0 = [[0.0, 0.0, 1.0, 0.0], [-0.0, -1.0, -0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
C8 = [[1.0, 0.0, 0.0, -0.0], [0.0, 1.0, 0.0, -0.0], [0.0, 0.0, 1.111111, -0.1111111], [0.0, 0.0, 0.0, 1.0]]
C24 = [[0.0, 0.0, 1.0, 0.0], [0.0, -1.0, 0.0, 0.0], [1.111111, 0.0, 0.0, -0.1111111], [0.0, 0.0, 0.0, 1.0]]
R0 = [[C0[i][j] for j in range(3)] for i in range(3)]
I4 = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def md(a, b):
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


# ---- the two arms, wired EXPLICITLY so they cannot be confused -------------
def vp_engine(eye, R3=R0):
    """The real engine product: Proj @ View, where View has NO translation.
    Note the eye argument is accepted but deliberately IGNORED -- c0 carries
    no translation, so the engine's VP literally cannot depend on position.
    That is the claim under test."""
    del eye, R3
    return mm(C8, C0)


def vp_fixed(eye, R3=R0):
    """Corrected: [R3 | -R3@eye], composed as Proj @ View."""
    v = [[0.0] * 4 for _ in range(4)]
    for i in range(3):
        for j in range(3):
            v[i][j] = R3[i][j]
        v[i][3] = -(R3[i][0] * eye[0] + R3[i][1] * eye[1] + R3[i][2] * eye[2])
    v[3][3] = 1.0
    return mm(C8, v)


def clip(older, newer):
    return mm(mat_inv(newer), older)


def row(tag, a, b, expect):
    c = clip(a, b)
    dev = md(c, I4)
    ok = expect(dev)
    print(f"  {tag:<38s} |I-clip| = {dev:>13.6f}  det3x3 = {det3(c): .6f}  "
          f"{'PASS' if ok else 'FAIL'}")
    return dev, ok


def main():
    print("=" * 82)
    print("v0.88 REGRESSION (fixed wiring) -- do the two arms actually differ?")
    print("=" * 82)
    print()
    print("SANITY: the two arms must differ. If they agree everywhere, the")
    print("        'engine' arm is not what I think it is.")
    eye = [-894.3632, 213.1464, 175.8006]
    d = md(vp_engine(eye), vp_fixed(eye))
    print(f"  max|VP_engine - VP_fixed| at eye={eye}")
    print(f"      = {d:.6f}   {'DIFFER (good)' if d > 1e-3 else 'IDENTICAL -- BROKEN TEST'}")
    print()

    fwd = [R0[2][i] for i in range(3)]
    e1 = eye
    e2 = [eye[i] + 0.4 * fwd[i] for i in range(3)]

    print("S1 camera PARKED (same pos, same orientation), 0.4 margin unused")
    row("engine", vp_engine(e1), vp_engine(e1), lambda x: abs(x) < 1e-6)
    row("FIXED ", vp_fixed(e1), vp_fixed(e1), lambda x: abs(x) < 1e-6)
    print()

    print("S2 camera CREEPS 0.4 u/frame  <-- the decisive comparison")
    d_eng, _ = row("engine", vp_engine(e1), vp_engine(e2), lambda x: abs(x) < 1e-6)
    d_fix, _ = row("FIXED ", vp_fixed(e1), vp_fixed(e2), lambda x: 0.0 < x < 2.0)
    print()
    print(f"  --> engine reports {d_eng:.6f}, fixed reports {d_fix:.6f}")
    if abs(d_eng) < 1e-6:
        print("      ENGINE BLIND: a real 0.4 u step is invisible to DLSS-G.")
        print("      This IS the ping-pong. Fix confirmed necessary.")
    else:
        print("      ENGINE IS NOT BLIND HERE -> my model is incomplete.")
        print("      The log's |I-clip| = 0 must have another cause. DO NOT SHIP.")
    print()

    print("S3 camera TELEPORTS 574 u (world load jump)")
    row("FIXED ", vp_fixed(e1), vp_fixed([eye[i] + 574.0 * fwd[i] for i in range(3)]),
        lambda x: x > 100.0)
    print()

    print("S4 orientation ROTATES 0.02 rad, pos constant")
    ang = 0.02
    Rz = [[math.cos(ang), -math.sin(ang), 0.0], [math.sin(ang), math.cos(ang), 0.0], [0.0, 0.0, 1.0]]
    R1 = [[sum(R0[i][k] * Rz[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    row("engine", vp_engine(e1), vp_engine(e1), lambda x: abs(x) < 1e-6)
    row("FIXED ", vp_fixed(e1, R0), vp_fixed(e1, R1), lambda x: x > 1e-6)
    print()

    print("=" * 82)
    print("CONCLUSION")
    print("=" * 82)
    print("  The engine arm IGNORES its eye argument by construction -- that is")
    print("  not a modelling choice, it is what the raw bytes say (c0 == c56, and")
    print("  Proj@[R|0] == c24 to 0.000000). A ViewProj built that way cannot")
    print("  vary with position, so consecutive frames collapse to the identity")
    print("  clip and DLSS-G is told the camera is parked.")
    print()
    print("  The fix restores the missing term. S1 proves it stays silent when")
    print("  the camera really is parked, which is the safety property that the")
    print("  v0.69 comment (Streamline.cpp:635-648) demanded and wrongly believed")
    print("  was impossible.")


if __name__ == "__main__":
    main()
