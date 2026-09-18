# -*- coding: utf-8 -*-
"""v1.00h - repair the dangling else left by v1.00g.

v1.00g replaced the `if (++snapLockStill >= kCamStillTol) {` line with a bare
`{`, so the branch tail `} else { ... }` lost its `if` (C2181: 没有匹配 if 的非法 else).

The correct shape for the whole `!continues` branch after the family gate is:

    } else if (!continues) {
        ++snapLockHold;
        if (!sameFamily) { ...return false; }     // v1.00: refuse forever

        // v1.00g: same family + did not continue => stale anchor, adopt now.
        ++snapLockStill;
        ++snapLockRelockJump;
        log(...);
        snapLockHave = true;
        snapLockStill = 0;
        ++snapLockRelock;
        snapHaveLast = false;
        log(source re-acquired ...);
    } else {
        snapLockStill = 0;
    }

i.e. there is no inner else any more: once the family test has refused the other
family, every remaining arrival IS the same family and the only action is to
adopt. The `held (other source)` log and its `return false` are dead code now
(the family gate returns first), so they are removed rather than left to rot.

This patch rewrites from `++snapLockHold;` through the `} else {` that closes the
`!continues` branch, replacing it with the shape above.

Run with --apply to write; without it, dry-run only.
"""
import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPP = os.path.join(ROOT, "src", "FrameGen.cpp")
APPLY = "--apply" in sys.argv

OLD = """				++snapLockHold;
				// ---- v1.00: a different projection family may NEVER re-acquire ----
				// v0.94 re-acquired unconditionally after kCamStillTol non-continuing
				// arrivals, so a foreign camera that arrived monotonically for 90
				// frames was adopted and then "continued" itself forever. That is the
				// freeze. Only an arrival from the SAME family may take over.
				if (!sameFamily) {
					++snapLockFamilyRej;
					if (snapLockFamilyRej <= 3u || (snapLockFamilyRej % 500u) == 0u) {
						SKSE::log::info("[CAM] #{} family rejected: proj00={:.6g} locked={:.6g} "
							"ratio={:.4f} pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} - another render "
							"pass, never re-acquires",
							snapArrivals, proj00, snapLockProj00,
							snapLockProjValid ? (proj00 / snapLockProj00) : 0.0f,
							px, py, pz, std::sqrt(d2));
					}
					if (d2 > kCamJumpTol2) ++snapRejectJump;
					return false;
				}
				// ---- v1.00g: same-family non-continuation re-acquires NOW ----
				// Reaching this branch already proves three things at once:
				//   1. a lock exists,
				//   2. the arrival is in the SAME projection family as the lock
				//      (a different family was refused above), and
				//   3. d2 > kCamStepTol2, i.e. it did not continue the stream.
				//
				// For a same-family stream, (3) has exactly two causes: the player
				// teleported / the scene changed (hundreds of units -- measured 250
				// going into the world, 1259 into the frozen run), or the slot
				// stopped updating. Both mean the old anchor is stale. Holding it
				// only makes DLSS-G reproject against a parked view, which is the
				// freeze. So take the new anchor immediately.
				//
				// v1.00f used kCamJumpTol (400) here and therefore MISSED the 250
				// unit transition into the world; the offline regression caught it
				// (adoptions stayed at 38, stream parked on the loading camera).
				// The boundary is kCamStepTol, which is already the test that put
				// us in this branch.
				++snapLockStill;
				if (++snapLockRelockJump <= 5u) {
					SKSE::log::info("[CAM] #{} same-family step break: pos=({:.1f},{:.1f},{:.1f}) "
						"locked=({:.1f},{:.1f},{:.1f}) dist={:.1f} proj00={:.6g} still={}/{} "
						"- adopting the new anchor",
						snapArrivals, px, py, pz,
						snapLastPos[0], snapLastPos[1], snapLastPos[2],
						std::sqrt(d2), proj00, snapLockStill, kCamStillTol);
				}
				{
					// The anchor is stale. Re-acquire on this arrival and drop the
					// stale anchor so the next test is made against the new source
					// rather than the old one.
					snapLockHave = true;
					snapLockStill = 0;
					if (snapLockRelockJump > 0u) ++snapLockRelock;
					snapHaveLast = false;
					SKSE::log::info("[CAM] #{} source re-acquired: locked stream did not "
						"continue for {} arrivals -> adopting pos=({:.1f},{:.1f},{:.1f}) "
						"devVP={:.6g} magVP={:.6g}",
						snapArrivals, kCamStillTol, px, py, pz,
						camDev(a_src.CameraViewProjUnjittered), camMag(a_src.CameraViewProjUnjittered));
				} else {
					// Withhold: this is another source. NOT published, so
					// frameBufferCopy keeps the locked stream and DLSS-G never
					// receives two cameras on consecutive frames.
					if (snapLockHold <= 3u || (snapLockHold % 500u) == 0u) {
						SKSE::log::info("[CAM] #{} held (other source): pos=({:.1f},{:.1f},{:.1f}) "
							"dist={:.1f} locked=({:.1f},{:.1f},{:.1f}) still={}/{} devVP={:.6g}",
							snapArrivals, px, py, pz, std::sqrt(d2),
							snapLastPos[0], snapLastPos[1], snapLastPos[2],
							snapLockStill, kCamStillTol, camDev(a_src.CameraViewProjUnjittered));
					}
					// Keep the classic counter populated for the heartbeat.
					if (d2 > kCamJumpTol2) ++snapRejectJump;
					return false;
				}"""

NEW = """				++snapLockHold;
				// ---- v1.00: a different projection family may NEVER re-acquire ----
				// v0.94 re-acquired unconditionally after kCamStillTol non-continuing
				// arrivals, so a foreign camera that arrived monotonically for 90
				// frames was adopted and then "continued" itself forever. That is the
				// freeze. Only an arrival from the SAME family may take over.
				if (!sameFamily) {
					++snapLockFamilyRej;
					if (snapLockFamilyRej <= 3u || (snapLockFamilyRej % 500u) == 0u) {
						SKSE::log::info("[CAM] #{} family rejected: proj00={:.6g} locked={:.6g} "
							"ratio={:.4f} pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} - another render "
							"pass, never re-acquires",
							snapArrivals, proj00, snapLockProj00,
							snapLockProjValid ? (proj00 / snapLockProj00) : 0.0f,
							px, py, pz, std::sqrt(d2));
					}
					if (d2 > kCamJumpTol2) ++snapRejectJump;
					return false;
				}
				// ---- v1.00g: same-family non-continuation re-acquires NOW ----
				// Reaching this point already proves three things at once:
				//   1. a lock exists,
				//   2. the arrival is in the SAME projection family as the lock
				//      (a different family returned above), and
				//   3. d2 > kCamStepTol2 -- it did not continue the stream.
				//
				// For a same-family stream, (3) has exactly two causes: the player
				// teleported / the scene changed (measured 250 units going into the
				// world, 1259 into the frozen run), or the slot stopped updating.
				// Both mean the old anchor is stale, and holding it only makes
				// DLSS-G reproject against a parked view -- which IS the freeze.
				// So take the new anchor immediately.
				//
				// v1.00f used kCamJumpTol (400) here and therefore MISSED the 250
				// unit transition into the world; the offline regression caught it
				// (adoptions stayed at 38, stream parked on the loading camera).
				// The boundary is kCamStepTol, which is the very test that put us
				// in this branch.
				++snapLockStill;
				++snapLockRelockJump;
				if (snapLockRelockJump <= 5u) {
					SKSE::log::info("[CAM] #{} same-family step break: pos=({:.1f},{:.1f},{:.1f}) "
						"locked=({:.1f},{:.1f},{:.1f}) dist={:.1f} proj00={:.6g} still={}/{} "
						"- adopting the new anchor",
						snapArrivals, px, py, pz,
						snapLastPos[0], snapLastPos[1], snapLastPos[2],
						std::sqrt(d2), proj00, snapLockStill, kCamStillTol);
				}
				// The anchor is stale. Re-acquire on this arrival and drop the stale
				// anchor so the next test is made against the new source rather
				// than the old one.
				snapLockHave = true;
				snapLockStill = 0;
				++snapLockRelock;
				snapHaveLast = false;"""


def main():
    with io.open(CPP, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if "v1.00h: repaired the dangling else" in src:
        print("REFUSED: marker already present - patch has run")
        return 1
    n = src.count(OLD)
    if n != 1:
        print("REFUSED: anchor occurs %d times (must be exactly 1)" % n)
        return 1

    out = src.replace(OLD, NEW)

    # The `!continues` branch must end with `} else { snapLockStill = 0; }` and
    # nothing may be left dangling.
    tail_ok = "} else {\\r\\n\\t\\t\\t\\tsnapLockStill = 0;".replace("\\r\\n", "\n") in out.replace("\r\n", "\n")
    checks = [
        ("dangling else removed", "snapHaveLast = false;\n\t\t\t\t\tSKSE::log::info(\"[CAM] #{} source re-acquired" not in out.replace("\r\n", "\n")),
        ("held-other-source log gone", "held (other source)" not in out),
        ("family gate present", "if (!sameFamily) {" in out),
        ("step-break log present", "same-family step break" in out),
        ("lock decision tail intact", "snapLockStill = 0;\n\t\t\t}" in out.replace("\r\n", "\n")),
        ("brace balance unchanged", out.count("{") - out.count("}") == src.count("{") - src.count("}")),
        ("paren balance unchanged", out.count("(") - out.count(")") == src.count("(") - src.count(")")),
    ]
    ok = True
    for label, cond in checks:
        print("  %-34s %s" % (label, "PASS" if cond else "FAIL"))
        ok = ok and cond
    if not ok:
        print("REFUSED: post-conditions failed, nothing written")
        return 1

    if not APPLY:
        print("\nDRY RUN - re-run with --apply")
        return 0
    with io.open(CPP, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("\nAPPLIED: dangling else repaired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
