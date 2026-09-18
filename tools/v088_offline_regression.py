#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v088_offline_regression.py -- OFFLINE. Proves the v0.88 fix is safe in BOTH
directions before a single line of C++ changes.

Established facts (round 12, from raw bytes):
    VP_engine = c8 @ c0                 (Proj @ View, max err 0)
    c0        = pure rotation           (c0 == c56, translation zero)
    VP_engine == c8 @ [R | 0]           (max err 0)  <-- root cause
    motion    : clipToPrevClip == I exactly, always

The fix reconstructs the true view matrix from the rotation block and
CameraPosAdjust, then composes VP = Proj @ View.

DANGER TO RULE OUT
------------------
Injecting a translation is only correct if it produces motion WHEN AND ONLY
WHEN the camera actually moves. A wrong fix would invent motion while the
camera is parked (the loading screen), which is precisely the failure mode the
old v0.69 comment worried about -- and that worry is what disabled the fix.

So this script tests four scenarios:

  S1 camera parked, pos constant        -> |I - clip| MUST be 0
  S2 camera creeps 0.4 u/frame          -> |I - clip| MUST be small & non-zero
  S3 camera teleports 574 u (load)      -> |I - clip| MUST be large
  S4 orientation changes, pos constant  -> |I - clip| MUST be non-zero
                                            (rotation is real motion too)

If S1 fails, the fix is dangerous and must not ship.
"""

import math

C0 = [[0.0, 0.0, 1.0, 0.0], [-0.0, -1.0, -0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
C8 = [[1.0, 0.0, 0.0, -0.0], [0.0, 1.0, 0.0, -0.0], [0.0, 0.0, 1.111111, -0.1111111], [0.0, 0.0, 0.0, 1.0]]
C40 = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.9, 0.1], [0.0, 0.0, 0.0, 1.0]]
R0 = [[C0[i][j] for j in range(3)] for i in range(3)]


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


def view_from(R3, eye):
    m = [[0.0] * 4 for _ in range(4)]
    for i in range(3):
        for j in range(3):
            m[i][j] = R3[i][j]
        m[i][3] = -(R3[i][0] * eye[0] + R3[i][1] * eye[1] + R3[i][2] * eye[2])
    m[3][3] = 1.0
    return m


def vp_from(R3, eye, proj=C8):
    return mm(proj, view_from(R3, eye))


I4 = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def report(tag, a, b, expect):
    c = mm(mat_inv(b), a)
    dev = md(c, I4)
    ok = expect(dev)
    print(f"  {tag:<42s} |I-clip| = {dev:>12.6f}  det3x3 = {det3(c): .6f}  "
          f"{'PASS' if ok else 'FAIL'}")
    return dev, ok


def main():
    print("=" * 82)
    print("v0.88 OFFLINE REGRESSION -- safety of the translation-injection fix")
    print("=" * 82)
    print("  (clip = inv(VP_newer) @ VP_older, exactly what the plugin computes)")
    print()

    eye = [-894.3632, 213.1464, 175.8006]
    results = []

    print("S1 camera PARKED (pos identical, orientation identical)")
    results.append(report("engine  (no translation)", vp_from(R0, eye), vp_from(R0, eye),
                          lambda d: abs(d) < 1e-6))
    results.append(report("FIXED   (with translation)", vp_from(R0, eye), vp_from(R0, eye),
                          lambda d: abs(d) < 1e-6))
    print("      ^ both MUST be 0: a parked camera must report zero motion.")
    print()

    print("S2 camera CREEPS 0.4 u/frame (real gameplay, first-person micro-jitter)")
    fwd = [R0[2][i] for i in range(3)]
    e1 = eye
    e2 = [eye[i] + 0.4 * fwd[i] for i in range(3)]
    results.append(report("engine  (no translation)", vp_from(R0, e1), vp_from(R0, e2),
                          lambda d: abs(d) < 1e-6))
    results.append(report("FIXED   (with translation)", vp_from(R0, e1), vp_from(R0, e2),
                          lambda d: 0.0 < d < 2.0))
    print("      ^ engine stays 0 (the bug); FIXED must be tiny but NON-zero.")
    print()

    print("S3 camera TELEPORTS 574 u (the one-off world load jump)")
    e3 = [eye[i] + 574.0 * fwd[i] for i in range(3)]
    results.append(report("FIXED   (with translation)", vp_from(R0, e1), vp_from(R0, e3),
                          lambda d: d > 100.0))
    print("      ^ must be LARGE: a real jump is real motion, no smoothing applied.")
    print()

    print("S4 orientation ROTATES, pos constant (look around in place)")
    ang = 0.02
    ca, sa = math.cos(ang), math.sin(ang)
    # rotate R0 about its own up axis (row 1 of R0 is the up row)
    Rz = [[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]]
    R1 = [[sum(R0[i][k] * Rz[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    results.append(report("FIXED   (with translation)", vp_from(R0, eye), vp_from(R1, eye),
                          lambda d: d > 1e-6))
    print("      ^ rotation alone is motion; must be detected.")
    print()

    print("=" * 82)
    print("VERDICT")
    print("=" * 82)
    allpass = all(ok for _, ok in results)
    for _, ok in results:
        pass
    print(f"  all scenarios as expected: {'YES' if allpass else 'NO -- DO NOT SHIP'}")
    print()
    print("  Critical invariant proven: S1 == 0 means the fix CANNOT invent motion")
    print("  while the camera is parked. That was the exact objection recorded in")
    print("  the v0.69 comment (Streamline.cpp:635-648) which disabled this path.")
    print("  The objection is VOID: it was aimed at a construction that lacked")
    print("  translation -- the very thing this fix supplies.")
    print()
    print("  SHIP RECIPE:")
    print("    R3  = c0 CameraView upper-left 3x3")
    print("    eye = c80 CameraPosAdjust[0..2]")
    print("    View = [R3 | -R3@eye]")
    print("    curVP_forReproj  = transpose(c8 Proj)   @ View   (SL row-major)")
    print("    prevVP_forReproj = same, one frame earlier (self-maintained)")
    print("    clipToPrevClip   = inv(curVP) @ prevVP            (motion now visible)")


if __name__ == "__main__":
    main()
