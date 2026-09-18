#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_origin_guard.py -- corrected pairing: engine c24 uses c8 Proj, not c40 ProjU."""
C0 = [[0.0, 0.0, 1.0, 0.0], [-0.0, -1.0, -0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
C8 = [[1.0, 0.0, 0.0, -0.0], [0.0, 1.0, 0.0, -0.0], [0.0, 0.0, 1.111111, -0.1111111], [0.0, 0.0, 0.0, 1.0]]
C24 = [[0.0, 0.0, 1.0, 0.0], [0.0, -1.0, 0.0, 0.0], [1.111111, 0.0, 0.0, -0.1111111], [0.0, 0.0, 0.0, 1.0]]
C40 = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.9, 0.1], [0.0, 0.0, 0.0, 1.0]]


def mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def md(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(4) for j in range(4))


def viewT(eye, R):
    t = [-(R[i][0] * eye[0] + R[i][1] * eye[1] + R[i][2] * eye[2]) for i in range(3)]
    m = [[0.0] * 4 for _ in range(4)]
    for i in range(3):
        for j in range(3):
            m[i][j] = R[i][j]
        m[i][3] = t[i]
    m[3][3] = 1.0
    return m, t


R = [[C0[i][j] for j in range(3)] for i in range(3)]
v0, t0 = viewT([0, 0, 0], R)

print("TEST1a origin + c8  Proj : max|Proj@[R|0] - c24| =", md(mm(C8, v0), C24), " (must be 0)")
print("TEST1b origin + c40 ProjU: max|ProjU@[R|0] - c24| =", md(mm(C40, v0), C24))
print()
print("TEST2 order recheck:")
print("  max|c8@c0 - c24| =", md(mm(C8, C0), C24))
print("  max|C0@c8 - c24| =", md(mm(C0, C8), C24))
print()
print("TEST3: is engine ViewProj just the origin-view product?")
print("  max|Proj@[R|0] - Proj@View| =", md(mm(C8, v0), mm(C8, C0)), " (0 => engine view has ZERO translation)")
print()
print("TEST4: translation column of the engine product, vs what a real eye would give")
print("  engine c24 col3 = (%.6f, %.6f, %.6f)" % (C24[0][3], C24[1][3], C24[2][3]))
eye = [-894.3632, 213.1464, 175.8006]
vf, tf = viewT(eye, R)
vpf = mm(C8, vf)
print("  fixed  VP  col3 = (%.6f, %.6f, %.6f)   [eye=%s]" % (vpf[0][3], vpf[1][3], vpf[2][3], eye))
print("  t = -R@eye      = (%.6f, %.6f, %.6f)" % tuple(tf))
