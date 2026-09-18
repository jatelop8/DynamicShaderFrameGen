# -*- coding: utf-8 -*-
"""v1.00g - same-family non-continuation re-acquires immediately.

v1.00f used kCamJumpTol (400) as the same-family jump threshold. The offline
regression showed that is WRONG for this stream: the transition into the world
moves the camera 250 units ((-50,600,80) -> (-60,849.98,80)), which is
    > kCamStepTol   (50)   so `continues` is false
    < kCamJumpTol   (400)  so the jump branch never fired
and the lock fell through to the kCamStillTol (90) counter instead, leaving the
stream parked on the loading camera (adoptions stayed at 38).

The correct boundary is kCamStepTol itself, not kCamJumpTol. Inside the
`!continues` branch `d2 > kCamStepTol2` ALREADY holds by construction, so once
the family test has confirmed the arrival is the SAME kind of camera, there is
nothing left to distinguish: walking steps by ~0.27 units, a scene transition
by hundreds, and the family is identical. Re-acquire immediately.

Cross-family arrivals are unaffected: they are refused before reaching here.

Run with --apply to write; without it, dry-run only.
"""
import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPP = os.path.join(ROOT, "src", "FrameGen.cpp")
APPLY = "--apply" in sys.argv

OLD = """				// ---- v1.00f: same-family jump re-acquires immediately ----
				// A same-family arrival that is more than kCamJumpTol away cannot be
				// one frame of walking: it is a teleport / scene change, and the
				// family test has already proven it is the SAME kind of camera. Hold
				// only makes DLSS-G reproject against a stale parked view, so take
				// the new anchor now. The kCamStillTol path below still covers a
				// same-family stream that merely stops updating.
				const bool sameFamJump = (d2 > kCamJumpTol2);
				if (sameFamJump && ++snapLockRelockJump <= 5u) {
					SKSE::log::info("[CAM] #{} same-family jump: pos=({:.1f},{:.1f},{:.1f}) "
						"locked=({:.1f},{:.1f},{:.1f}) dist={:.1f} proj00={:.6g} - re-acquiring",
						snapArrivals, px, py, pz,
						snapLastPos[0], snapLastPos[1], snapLastPos[2],
						std::sqrt(d2), proj00);
				}
				if (sameFamJump || ++snapLockStill >= kCamStillTol) {
					// The anchor is stale: either the player teleported (same family,
					// far away) or the locked stream has not continued for ~1.5 s at
					// 60 Hz (loading screen / scene change). Re-acquire on this
					// arrival and drop the stale anchor so the next test is made
					// against the new source rather than the old one.
					snapLockHave = true;
					snapLockStill = 0;
					if (!sameFamJump) ++snapLockRelock;
					snapHaveLast = false;"""

NEW = """				// ---- v1.00g: same-family non-continuation re-acquires NOW ----
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
					snapHaveLast = false;"""


def main():
    with io.open(CPP, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if "v1.00g: same-family non-continuation re-acquires NOW" in src:
        print("REFUSED: marker already present - patch has run")
        return 1
    n = src.count(OLD)
    if n != 1:
        print("REFUSED: anchor occurs %d times (must be exactly 1)" % n)
        return 1

    out = src.replace(OLD, NEW)

    checks = [
        ("g comment present", "v1.00g: same-family non-continuation" in out),
        ("f threshold gone", "sameFamJump" not in out),
        ("kCamJumpTol2 no longer gates the lock",
         "const bool sameFamJump" not in out),
        ("relock counter still incremented", "++snapLockRelock;" in out),
        ("family gate still there", "if (!sameFamily) {" in out),
        ("brace balance unchanged", out.count("{") - out.count("}") == src.count("{") - src.count("}")),
    ]
    ok = True
    for label, cond in checks:
        print("  %-38s %s" % (label, "PASS" if cond else "FAIL"))
        ok = ok and cond
    if not ok:
        print("REFUSED: post-conditions failed, nothing written")
        return 1

    if not APPLY:
        print("\nDRY RUN - re-run with --apply")
        return 0
    with io.open(CPP, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("\nAPPLIED: same-family non-continuation re-acquires immediately")
    return 0


if __name__ == "__main__":
    sys.exit(main())
