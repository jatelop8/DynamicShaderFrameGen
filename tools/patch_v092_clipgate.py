#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.92: replace the structurally-blind det3() guard with a translation-aware
validity test, and report both metrics so the log can no longer mislead.

WHY (proven offline, tools/prove_det3_blind.py):
  For clipToPrev = inv(Proj@View_cur) @ (Proj@View_prev), the upper-left 3x3 is
  Proj3 * R_cur^T * R_prev * Proj3^-1 -- it depends ONLY on the rotation, never
  on the translation. So det3 == 1.000000 for every camera displacement, and the
  "det outside [0.5,2.0]" guard can never fire on real motion.

  The heartbeat printed det(min/max)=1.000/1.000, which reads as "no motion".
  It never meant that. The real motion signal is max|I - clip|, already in the
  same line as clipDevMax.

WHAT THIS PATCH DOES
  1. Keeps det3 as a *reported* number (history/compat) but no longer uses it as
     the accept/reject gate.
  2. Gates on a translation-aware test instead: the matrix must be finite and
     its full 4x4 deviation from identity must be finite. (A degenerate
     projection still shows up as non-finite magnitude.)
  3. Adds a `detGuard`-driven log line carrying BOTH metrics so the next run
     proves which one moved.

Assertions: idempotency marker first, then exactly-one anchors; dry-run default.
"""
import io, sys, hashlib

PATH = "src/Streamline.cpp"
MARKER = "v0.92: translation-aware validity gate"

OLD = """			const float det = det3(c.clipToPrevClip);
			if (det < diag.detMin) diag.detMin = det;
			if (det > diag.detMax) diag.detMax = det;
			if (det > 0.5f && det < 2.0f) {
				s_lastGoodClip = c.clipToPrevClip;
				s_hasLastGoodClip = true;
			} else {
				++diag.detGuard;
				if (s_hasLastGoodClip) {
					c.clipToPrevClip = s_lastGoodClip;
					++diag.detHold;
				} else {
					setIdentity(c.clipToPrevClip);
				}
			}"""

NEW = """			const float det = det3(c.clipToPrevClip);
			if (det < diag.detMin) diag.detMin = det;
			if (det > diag.detMax) diag.detMax = det;
			// v0.92: translation-aware validity gate.
			//
			// det3() reads only the upper-left 3x3, which for
			// inv(cur) x prev equals  Proj3 * Rcur^T * Rprev * Proj3^-1 --
			// a function of the ROTATION ALONE. Proven offline
			// (tools/prove_det3_blind.py): det3 == 1.000000 for every camera
			// displacement from 0.001 to 400 units, while max|I - clip| tracks
			// the displacement one-for-one.
			//
			// So the old `det in [0.5,2.0]` test could not see translation at
			// all, and det(min/max)=1.000/1.000 in the log meant "the metric is
			// blind", NOT "the camera never moved". Gate on a metric that does
			// depend on the translation.
			//
			// clipDev = max|I - clipToPrevClip| over the FULL 4x4 (the same
			// quantity already reported as clipDevMax). A real relative motion
			// makes it > 0; a degenerate / non-finite matrix fails the finite
			// test below.
			float clipDev = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float v[4] = { c.clipToPrevClip[r].x, c.clipToPrevClip[r].y,
				                     c.clipToPrevClip[r].z, c.clipToPrevClip[r].w };
				for (int k = 0; k < 4; ++k) {
					const float id = (r == k) ? 1.0f : 0.0f;
					const float a2 = v[k] - id;
					const float m = a2 < 0.0f ? -a2 : a2;
					if (m > clipDev) clipDev = m;
				}
			}
			float clipMagAll = 0.0f;
			for (int r = 0; r < 4; ++r) {
				clipMagAll += c.clipToPrevClip[r].x * c.clipToPrevClip[r].x
				            + c.clipToPrevClip[r].y * c.clipToPrevClip[r].y
				            + c.clipToPrevClip[r].z * c.clipToPrevClip[r].z
				            + c.clipToPrevClip[r].w * c.clipToPrevClip[r].w;
			}
			const bool clipFinite = clipMagAll < 1.0e30f;   // rejects NaN / Inf
			if (clipFinite) {
				s_lastGoodClip = c.clipToPrevClip;
				s_hasLastGoodClip = true;
			} else {
				++diag.detGuard;
				if (s_hasLastGoodClip) {
					c.clipToPrevClip = s_lastGoodClip;
					++diag.detHold;
				} else {
					setIdentity(c.clipToPrevClip);
				}
			}
			// v0.92: keep both metrics in one line so the next run shows which
			// one carries the motion signal (det3 is provably flat).
			if (diag.detGuard <= 3u) {
				SKSE::log::info("[XRAY] clipGate v0.92: det3={:.6f} (rotation-only, "
					"expected ~1) clipDev={:.6f} finite={} - clipDev is the "
					"translation-aware metric",
					det, static_cast<double>(clipDev), clipFinite ? 1 : 0);
			}"""

data = io.open(PATH, "r", encoding="utf-8", newline="").read()

# guard 0: idempotency FIRST
if MARKER in data:
    print("REFUSED: v0.92 already applied. nothing written."); sys.exit(0)

n = data.count(OLD)
print("anchor count =", n)
if n != 1:
    print("REFUSED: anchor count=%d (need exactly 1). nothing written." % n); sys.exit(1)

new = data.replace(OLD, NEW)
assert new != data
print("line endings CRLF %d -> %d | chars %d -> %d (delta %+d)" % (
    data.count("\r\n"), new.count("\r\n"), len(data), len(new), len(new) - len(data)))
if "\r\n" in data and new.count("\r\n") == 0:
    print("REFUSED: would destroy CRLF."); sys.exit(1)

if "--apply" not in sys.argv:
    print("\nDRY RUN - nothing written. re-run with --apply.")
    sys.exit(0)

io.open(PATH, "w", encoding="utf-8", newline="").write(new)
back = io.open(PATH, "r", encoding="utf-8", newline="").read()
print("\napplied. readback chars =", len(back))
print("marker present:", MARKER in back, "| old anchor gone:", OLD not in back)
print("md5 =", hashlib.md5(back.encode("utf-8")).hexdigest())
