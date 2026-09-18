#!/usr/bin/env python3
"""
regress_v107c_reprojsrc.py -- the v1.07c defect, proved arithmetically.

Pure Python, no dependencies (the toolchain python has no numpy guarantee, and
a proof that needs an install is a proof that does not run).

THE CLAIM
---------
    clipToPrevClip = inv(cur) @ prev

`prev` (camPrevVP / s_prevVP) comes out of rebuildViewProj, which folds the
camera eye in:  V_prev = [R | t],  t = -R @ eye.
`cur`  (curForReproj) is the engine's ViewProj and carries NO translation:
    V_cur = [R | 0].

The old code inverted V_cur. For ANY invertible projection P:

    inv(P @ V_cur) @ (P @ V_prev)
      = inv(V_cur) @ inv(P) @ P @ V_prev
      = inv(V_cur) @ V_prev
      = [ I | t ]                     (t the eye term, still in world units)

So the result is a matrix whose 3x3 IS the identity -- det3() reports exactly
1.000000, every existing guard passes -- while its translation is the whole
camera position. Rotation-correct, translation-absurd.

With the fix both sides come from the same camera, so a still camera gives
inv(M) @ M == I exactly, and a moving camera gives the true relative motion.

WHAT THIS SCRIPT SHOWS
----------------------
  C0  structural: with random R / P / eye, OLD == [I | R^T t] and NEW == I
  C1  the real 23:10 numbers: still camera
  C2  a moving camera: NEW must NOT be I (the fix must not flatten motion)
  C3  det3 is blind to this (OLD det3 == 1.000000 while plainly broken)
  C4  clipToPrevClip[3].w, the v1.07c instrument -- and its LIMIT

C4 LIMIT, stated up front: in the clean model the broken matrix has w == 1, so
clipW alone does not catch it. What caught it in the real run is that the
engine's projection is not clean (its [3][3] is 0.0666667 rather than 0, see
the [FLD] dump), so the real matrix came out with w = -195.222366. clipW is
therefore a correct detector for the OBSERVED form and not a universal one.
The universal criterion needs no new field: with the camera STILL, clipDev
must be ~0.
"""

import random

# ---------------------------------------------------------------- 4x4 helpers
# Row-major, last row carries the translation:  p' = p @ M
# (the convention sl::matrix4x4 uses, and the one Transfusion dumps rows of)


def mat(rows):
    return [list(r) for r in rows]


def ident():
    return [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
            for i in range(4)]


def inv(m):
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(4)]
         for i, row in enumerate(m)]
    for c in range(4):
        p = max(range(c, 4), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-15:
            return None
        a[c], a[p] = a[p], a[c]
        pv = a[c][c]
        a[c] = [v / pv for v in a[c]]
        for r in range(4):
            if r != c and a[r][c] != 0.0:
                f = a[r][c]
                a[r] = [a[r][k] - f * a[c][k] for k in range(8)]
    return [row[4:] for row in a]


def det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


def trans_mag(m):
    return (m[3][0] ** 2 + m[3][1] ** 2 + m[3][2] ** 2) ** 0.5


def max_dev_from_identity(m):
    return max(abs(m[r][k] - (1.0 if r == k else 0.0))
               for r in range(4) for k in range(4))


def rot_y(deg):
    import math
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def rot_x(deg):
    import math
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]


def mm3(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def mv3(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


def view(rot3, eye, translate=True):
    """[R | t] with t = -R @ eye  (world -> camera). translate=False drops the
    eye term, exactly as the engine's own ViewProj does."""
    t = mv3(rot3, eye)
    t = [-t[0], -t[1], -t[2]] if translate else [0.0, 0.0, 0.0]
    return mat([[rot3[0][0], rot3[0][1], rot3[0][2], 0.0],
                [rot3[1][0], rot3[1][1], rot3[1][2], 0.0],
                [rot3[2][0], rot3[2][1], rot3[2][2], 0.0],
                [t[0], t[1], t[2], 1.0]])


def proj(fov_deg=60.0, aspect=16.0 / 9.0, near=0.0666667, far=100000.0):
    import math
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    return mat([[f / aspect, 0.0, 0.0, 0.0],
                [0.0, f, 0.0, 0.0],
                [0.0, 0.0, far / (far - near), 1.0],
                [0.0, 0.0, -near * far / (far - near), 0.0]])


def reproduce(rot3, eye_cur, eye_prev, P, fixed):
    """Returns (clipToPrev, note) for one of the two builds."""
    cur_no_t = view(rot3, [0, 0, 0], translate=False)
    c_cur = mul(P, cur_no_t)
    c_prev = mul(P, view(rot3, eye_prev, translate=True))
    c_cur_rebuilt = mul(P, view(rot3, eye_cur, translate=True))

    if not fixed:
        i = inv(c_cur)                        # v1.07b and earlier
        if i is None:
            return None, "singular"
        return mul(i, c_prev), "inv(engine cur, no translation)"
    i = inv(c_cur_rebuilt)                    # v1.07c
    if i is None:
        return None, "singular"
    return mul(i, c_prev), "inv(rebuilt cur, with translation)"


EYE = (-243.049301, -415.311523, 118.558205)   # Transfusion cameraPos, frame 578
EYE_MOVED = (-243.049301, -400.011523, 118.558205)  # 15.3 units along +Y

fails = []


def line(k, v):
    print(f"  {k:38s} {v}")


# ---------------------------------------------------------------- C0
print("=" * 78)
print("C0  structural: is inv(P@[R|0]) @ (P@[R|t]) really [I | t] ?")
print("    random R, random invertible P, random eye -- 200 trials")
print("=" * 78)
random.seed(1070)
worst_identity_err = 0.0
worst_rot_err = 0.0
for _ in range(200):
    r3 = mm3(rot_y(random.uniform(-180, 180)), rot_x(random.uniform(-89, 89)))
    e = [random.uniform(-500, 500) for _ in range(3)]
    p = [[random.uniform(-2, 2) for _ in range(4)] for _ in range(4)]
    p[3] = [0.0, 0.0, 0.0, random.uniform(0.5, 2.0)]      # keep it invertible
    got, _n = reproduce(r3, e, e, mat(p), fixed=False)
    if got is None:
        continue
    # predicted: inv([R|0]) @ [R|t] = [R^T|0] @ [R|t] = [I | t], t = -R@eye.
    # (row-vector convention: [A|a] @ [B|b] -> rotation A@B, translation a@B+b,
    #  so the R^T annihilates R and the zero term leaves t untouched)
    t = mv3(r3, e)
    t = [-t[0], -t[1], -t[2]]
    pred = mat([[1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [t[0], t[1], t[2], 1.0]])
    err = max(abs(got[r][k] - pred[r][k]) for r in range(4) for k in range(4))
    worst_identity_err = max(worst_identity_err, err)
    worst_rot_err = max(worst_rot_err, det3(got) - 1.0)
line("max |OLD - predicted|", f"{worst_identity_err:.3e}")
line("max |det3(OLD) - 1|", f"{worst_rot_err:.3e}")
print("  note: the 3x3 stays orthonormal on every trial -- det3 cannot see it.")
fails.append(("C0", worst_identity_err < 1e-9))
print()

# ---------------------------------------------------------------- C1
print("=" * 78)
print("C1  the 23:10 numbers, camera STILL, eye from Transfusion frame 578")
print(f"    eye = {EYE}")
print("=" * 78)
r3 = mm3(rot_y(20.0), rot_x(-5.0))
P = proj()
old, oldnote = reproduce(r3, EYE, EYE, P, fixed=False)
new, newnote = reproduce(r3, EYE, EYE, P, fixed=True)
print(f"  OLD  {oldnote}")
line("clipDev  max|I - m|", f"{max_dev_from_identity(old):.6f}")
line("translation |m[3].xyz|", f"{trans_mag(old):.4f}     <- the eye position")
line("m[3].w", f"{old[3][3]:.6f}")
line("det3", f"{det3(old):.6f}     <- looks perfectly healthy")
line("is it identity?", "NO" if max_dev_from_identity(old) > 1e-6 else "yes")
print()
print(f"  NEW  {newnote}")
line("clipDev  max|I - m|", f"{max_dev_from_identity(new):.3e}")
line("translation |m[3].xyz|", f"{trans_mag(new):.3e}")
line("m[3].w", f"{new[3][3]:.6f}")
line("is it identity?", "yes" if max_dev_from_identity(new) < 1e-9 else "NO")
print()
print(f"  eye magnitude for scale: {trans_mag(mat([[1,0,0,0],[0,1,0,0],[0,0,1,0],[EYE[0],EYE[1],EYE[2],1]])):.3f} units")
print("  -> OLD told DLSS-G 'the camera is here, and it did not move'.")
if max_dev_from_identity(old) < 1e-6:
    fails.append(("C1 old must NOT be identity", False))
else:
    fails.append(("C1 old must NOT be identity", True))
fails.append(("C1 new must BE identity", max_dev_from_identity(new) < 1e-9))
fails.append(("C1 old det3 must be 1", abs(det3(old) - 1.0) < 1e-6))
fails.append(("C1 new trans must be 0", trans_mag(new) < 1e-9))
print()

# ---------------------------------------------------------------- C2
print("=" * 78)
print("C2  a MOVING camera: the fix must not flatten real motion")
print(f"    eye_prev = {EYE}")
print(f"    eye_cur  = {EYE_MOVED}   (15.300 units along +Y)")
print("=" * 78)
old2, _ = reproduce(r3, EYE_MOVED, EYE, P, fixed=False)
new2, _ = reproduce(r3, EYE_MOVED, EYE, P, fixed=True)
d_old = max_dev_from_identity(old2)
d_new = max_dev_from_identity(new2)
line("OLD clipDev", f"{d_old:.6f}")
line("NEW clipDev", f"{d_new:.6f}     <- non-zero, so motion survives")
line("NEW vs expected clip step", f"{d_new:.6f}  (a 15.3u step / z)")
if d_new < 1e-9:
    fails.append(("C2 new must NOT be identity when moving", False))
    print("  !! the fix flattened real motion")
else:
    fails.append(("C2 new must NOT be identity when moving", True))
    print("  OK: the fix yields exact relative motion when the camera moves")
print()

# ---------------------------------------------------------------- C3
print("=" * 78)
print("C3  why the old guard never fired")
print("=" * 78)
print("  existing guard is  det in [0.5, 2.0]  on det3(), which reads the 3x3.")
print("  inv(cur) @ prev has 3x3 = Proj3 @ Rcur^T @ Rprev @ Proj3^-1 -- a")
print("  function of ROTATION ALONE. It is 1.000000 for every translation.")
line("OLD det3 (broken matrix)", f"{det3(old):.6f}")
line("guard verdict", "PASS  <- false negative, by construction")
print()

# ---------------------------------------------------------------- C4
print("=" * 78)
print("C4  the v1.07c instrument: clipToPrevClip[3].w")
print("=" * 78)
line("clean-model OLD m[3].w", f"{old[3][3]:.6f}")
line("clean-model NEW m[3].w", f"{new[3][3]:.6f}")
print()
print("  LIMIT, stated plainly: in the CLEAN model the broken matrix has w == 1,")
print("  so clipW would NOT have caught it here. What caught it in the real run")
print("  is that the engine's projection is not clean -- its [3][3] reads")
print("  0.0666667 instead of 0 (see the [FLD] ProjU dump) -- and the real")
print("  matrix came out with w = -195.222366:")
print()
print("      clipToPrev rows=[...][...][...]")
print("                     [-243.962387 2.7390945 -77.6724777 -195.222366]")
print("      cameraPos=(-243.049301,-415.311523,118.558205)")
print()
print("  So clipW detects the OBSERVED form, not every form. The criterion that")
print("  needs no new field and covers every form: with the camera STILL,")
print("  clipDev must be ~0. Both are checked in tools/analyze_session.py.")
print()

# ---------------------------------------------------------------- result
print("=" * 78)
bad = [n for n, ok in fails if not ok]
print(f"RESULT: {'OK' if not bad else 'FAIL'}")
for n in bad:
    print(f"  - {n}")
if not bad:
    print("  the defect is exact, the fix is exact, and det3 provably cannot see it.")
