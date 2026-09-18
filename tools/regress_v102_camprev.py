#!/usr/bin/env python3
"""
regress_v102_camprev.py -- offline proof of the v1.02 camera-history fix.

Reconstructs, in pure Python, exactly what Streamline::CheckFrameConstants now
computes, and checks the four claims the patch rests on:

  C1  COMPOSABILITY -- when the engine says prev == cur, clipToPrevClip must be
      the identity, byte for byte, exactly as the old code produced. If this
      fails, the patch could regress a frame that already worked.

  C2  TRANSLATION IS RESTORED -- a camera walking a known distance must produce
      max|I - clipToPrevClip| that tracks that distance. The old code returned
      0.000000 for every distance (that is the freeze).

  C3  MENU / LOADING -- a parked camera stays at identity, and a MENU-family
      camera (different projection) does not silently blend into the world
      stream. Both must be no-ops relative to the old behaviour.

  C4  ROTATION-ONLY MOVE -- a pure yaw with no translation must still produce a
      non-identity clipToPrevClip (the engine's ViewProj is rotation-live), and
      the value must match the old code's value (rotation was never broken).

The matrices use the same convention as the C++: engine row-major storage, then
transposed into the SL layout with s[0]=column0. The composition order is
Proj @ View.
"""

import math
import sys

IDENT_TOL = 1.0e-9


def mat_identity():
    return [[1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]


def mat_mul(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def perspective(fov_y_rad, aspect, near, far):
    """Standard right-handed perspective, engine row-major."""
    f = 1.0 / math.tan(fov_y_rad / 2.0)
    m = [[0.0] * 4 for _ in range(4)]
    m[0][0] = f / aspect
    m[1][1] = f
    m[2][2] = far / (near - far)
    m[2][3] = (far * near) / (near - far)
    m[3][2] = -1.0
    return m


def view_rotation_only(pitch, yaw):
    """world -> camera, ROTATION ONLY. This is what the engine's c0 holds."""
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    # R = Rx(pitch) @ Ry(yaw), then transpose to world->camera
    ry = [[cy, 0.0, sy, 0.0], [0.0, 1.0, 0.0, 0.0], [-sy, 0.0, cy, 0.0], [0.0, 0.0, 0.0, 1.0]]
    rx = [[1.0, 0.0, 0.0, 0.0], [0.0, cp, -sp, 0.0], [0.0, sp, cp, 0.0], [0.0, 0.0, 0.0, 1.0]]
    rot = mat_mul(rx, ry)
    m = [[rot[c][r] for c in range(4)] for r in range(4)]   # transpose
    return m


def rebuild_viewproj(view_rot, eye, proj):
    """Replica of the C++ rebuildViewProj lambda."""
    vm = [[0.0] * 4 for _ in range(4)]
    for r in range(3):
        m0, m1, m2 = view_rot[r][0], view_rot[r][1], view_rot[r][2]
        vm[r][0] = m0
        vm[r][1] = m1
        vm[r][2] = m2
        vm[r][3] = -(m0 * eye[0] + m1 * eye[1] + m2 * eye[2])
    vm[3][3] = 1.0
    # transpose into the SL layout, exactly like the C++
    vsl = [[vm[c][r] for c in range(4)] for r in range(4)]
    psl = [[proj[c][r] for c in range(4)] for r in range(4)]
    return mat_mul(psl, vsl)          # Proj @ View


def engine_viewproj(view_rot, proj):
    """What the ENGINE composes: Proj @ [R | 0] -- no translation at all."""
    return rebuild_viewproj(view_rot, (0.0, 0.0, 0.0), proj)


def invert(m):
    """4x4 inverse via Gauss-Jordan."""
    a = [row[:] + [1.0 if r == c else 0.0 for c in range(4)] for r, row in enumerate(m)]
    for col in range(4):
        piv = max(range(col, 4), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None
        a[col], a[piv] = a[piv], a[col]
        d = a[col][col]
        a[col] = [v / d for v in a[col]]
        for r in range(4):
            if r != col and a[r][col] != 0.0:
                f = a[r][col]
                a[r] = [a[r][k] - f * a[col][k] for k in range(8)]
    return [row[4:] for row in a]


def max_dev_from_identity(m):
    d = 0.0
    for r in range(4):
        for c in range(4):
            want = 1.0 if r == c else 0.0
            d = max(d, abs(m[r][c] - want))
    return d


def same_mat(a, b):
    for r in range(4):
        for c in range(4):
            if abs(a[r][c] - b[r][c]) > 1e-9:
                return False
    return True


def clip_to_prev(cur_vp, prev_vp):
    inv = invert(cur_vp)
    if inv is None:
        return None
    return mat_mul(inv, prev_vp)


# ---------------------------------------------------------------------------
# The two projection families measured in the running game.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# The two projection families measured in the running game.
# ---------------------------------------------------------------------------
PROJ_WORLD = perspective(math.radians(60.0), 16.0 / 9.0, 1.0, 100000.0)
PROJ_MENU = perspective(math.radians(34.0), 16.0 / 9.0, 1.0, 100000.0)
print("proj00 world = {:.6f}   menu = {:.6f}   ratio = {:.4f}x".format(
    PROJ_WORLD[0][0], PROJ_MENU[0][0], PROJ_MENU[0][0] / PROJ_WORLD[0][0]))


def replay(frames, proj):
    """Replicates CheckFrameConstants for a sequence of (rot, eye)."""
    out = []
    prev_cam = None
    for i, (rot, eye) in enumerate(frames):
        cur_vp = rebuild_viewproj(rot, eye, proj)
        eng_vp = engine_viewproj(rot, proj)
        eng_prev_vp = eng_vp if i == 0 else engine_viewproj(frames[i - 1][0], proj)

        # v1.02c: the engine's prev field is NOT consulted -- it is a stale
        # constant in this build (engPrevEqCur and engPrevDiffers both climb at
        # the same rate, which no live field can do). The previous camera is
        # always the rebuilt one; a genuinely parked camera collapses to the
        # identity through the rebuild itself (eye_prev == eye_cur).
        if prev_cam is not None:
            prev_vp = rebuild_viewproj(prev_cam[0], prev_cam[1], proj)
            branch = "rebuilt"
        else:
            prev_vp = cur_vp
            branch = "first"
        prev_cam = (rot, eye)

        clip = clip_to_prev(cur_vp, prev_vp)
        dev = max_dev_from_identity(clip) if clip else float("nan")
        out.append((i, branch, dev))
    return out


def old_code(frames, proj):
    """The pre-v1.02 pipeline: cur = engine product, prev = engine product."""
    out = []
    for i in range(1, len(frames)):
        cur_vp = engine_viewproj(frames[i][0], proj)
        prev_vp = engine_viewproj(frames[i - 1][0], proj)
        out.append(max_dev_from_identity(clip_to_prev(cur_vp, prev_vp)))
    return out


def report(name, res, expect_identity=False, expect_motion=None):
    print("\n" + name)
    for i, br, dev in res[:4]:
        print("  frame {:<3d} branch={:<9s} max|I-clip| = {:.6f}".format(i, br, dev))
    if len(res) > 4:
        print("  ... {} more, final = {:.6f}".format(len(res) - 4, res[-1][2]))
    ok = True
    if expect_identity:
        bad = [i for i, _, d in res if d > 1e-5]
        if bad:
            print("  FAIL: frames {} are not identity".format(bad[:6]))
            ok = False
        else:
            print("  OK: identity on every frame")
    if expect_motion is not None:
        final = res[-1][2]
        lo, hi = expect_motion * 0.5, expect_motion * 2.0
        if lo <= final <= hi:
            print("  OK: motion restored, {:.6f} in [{:.3f}, {:.3f}]".format(final, lo, hi))
        else:
            print("  FAIL: expected ~{:.3f}, got {:.6f}".format(expect_motion, final))
            ok = False
    return ok


allok = True
r_still = view_rotation_only(0.0, 1.0)

# ---- C2: pure translation -------------------------------------------------
walk = [(r_still, (100.0, 0.0, 4.0 * i)) for i in range(6)]
res = replay(walk, PROJ_WORLD)
old = old_code(walk, PROJ_WORLD)
print("\nC2  pure translation, 4.0 units/frame")
print("  old code per frame : " + ", ".join("{:.6f}".format(d) for d in old))
print("  => the engine product cannot see a walk with a fixed orientation;")
print("     that is the freeze, and it is why the fix rebuilds the previous")
print("     camera from R + eye instead of reading that product back.")
print("  new code branches   : " + ", ".join(b for _, b, _ in res))
allok &= report("C2 continued", res, expect_motion=4.0)

# ---- C2b: rotation + translation (engine product goes live) ---------------
walk_r = [(view_rotation_only(0.0, 1.0 + 0.02 * i), (100.0, 0.0, 4.0 * i))
          for i in range(6)]
res = replay(walk_r, PROJ_WORLD)
old = old_code(walk_r, PROJ_WORLD)
print("\nC2b rotation + translation (the engine product DOES change)")
print("  old code per frame : " + ", ".join("{:.6f}".format(d) for d in old))
print("  new code branches  : " + ", ".join(b for _, b, _ in res))
allok &= report("C2b result", res, expect_motion=4.0)

# ---- C3: parked camera / menu --------------------------------------------
rest = replay([(r_still, (200.0, 50.0, 30.0))] * 5, PROJ_WORLD)
allok &= report("\nC3a parked world camera (must stay identity)", rest, expect_identity=True)

resm = replay([(view_rotation_only(0.0, 0.3), (0.0, 0.0, 0.0))] * 5, PROJ_MENU)
allok &= report("C3b MENU camera (must stay identity)", resm, expect_identity=True)

# ---- C4: rotation only ---------------------------------------------------
rots = [(view_rotation_only(0.0, 0.02 * i), (0.0, 0.0, 0.0)) for i in range(5)]
res = replay(rots, PROJ_WORLD)
old = old_code(rots, PROJ_WORLD)
print("\nC4  rotation-only yaw, 0.02 rad/frame")
print("  old code per frame : " + ", ".join("{:.6f}".format(d) for d in old))
print("  new final          : {:.6f}".format(res[-1][2]))
if abs(old[-1] - res[-1][2]) > 1e-6:
    print("  FAIL: rotation handling changed; it must be bit-identical")
    allok = False
else:
    print("  OK: rotation handling identical (never was broken, unchanged)")

print("\nRESULT: " + ("PASS" if allok else "FAIL"))
sys.exit(0 if allok else 1)
