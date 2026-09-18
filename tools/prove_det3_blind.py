#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PROOF (offline, no compiler): det3() is structurally blind to the translation
column of clipToPrevClip, which is precisely the term v0.88 added.

Construct: Proj @ View with View = [R | -R*eye].
  cur  -> eye = e0
  prev -> eye = e1   (camera moved by d = e1 - e0)
clipToPrev = inv(cur) @ prev.

Claim:
  * det3(clipToPrev) == 1.000000 exactly (independent of d)
    => the v0.66 det-guard cannot see the motion,
       and the heartbeat's det(min/max) stays 1.000 while motion exists.
  * the FULL 4x4 deviation from identity DOES depend on d
    => clipDevMax is the metric that actually sees it.
"""
import numpy as np

def view_from(R, eye):
    """Engine row-major view matrix: rows 0..2 = R with translation -R@eye,
    row 3 = (0,0,0,1)."""
    V = np.eye(4)
    V[0:3, 0:3] = R
    V[0:3, 3] = -(R @ eye)
    return V

def det3(M):
    return np.linalg.det(M[0:3, 0:3])

def clip_dev(M):
    return float(np.max(np.abs(M - np.eye(4))))

# a plain perspective-ish projection (any full-rank P works)
P = np.array([
    [1.30, 0.00,  0.00, 0.00],
    [0.00, 2.31,  0.00, 0.00],
    [0.00, 0.00, -1.00, -0.21],
    [0.00, 0.00, -1.00,  0.00],
])

rng = np.random.default_rng(7)
R = np.linalg.qr(rng.normal(size=(3, 3)))[0]      # orthonormal rotation
if np.linalg.det(R) < 0:
    R[:, 0] *= -1
R = R.T                                            # row-major

eye0 = np.array([-505.0, -14.0, 135.0])
print("eye0 =", eye0)
print()
print("%-14s %-18s %-18s" % ("move (units)", "det3(clipToPrev)", "max|I - clip|"))
print("-" * 54)
for dist in [0.0, 0.001, 0.01, 0.1, 0.4, 1.0, 10.0, 400.0]:
    direction = np.array([1.0, 0.0, 0.0])
    eye1 = eye0 + direction * dist
    Vcur = view_from(R, eye0)
    Vprev = view_from(R, eye1)
    cur = P @ Vcur
    prev = P @ Vprev
    clip = np.linalg.inv(cur) @ prev
    print("%-14.3f %-18.9f %-18.9f" % (dist, det3(clip), clip_dev(clip)))

print()
print("INTERPRETATION")
print("  det3 stays 1.000000 for EVERY camera displacement -> the 'det outside")
print("  [0.5,2.0]' guard can never fire on real motion, and the heartbeat's")
print("  det(min/max)=1.000/1.000 is NOT evidence that motion is absent.")
print("  max|I - clip| grows linearly with the displacement -> clipDevMax is the")
print("  metric that carries the signal.")
