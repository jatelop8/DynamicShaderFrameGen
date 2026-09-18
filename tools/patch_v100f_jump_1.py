# -*- coding: utf-8 -*-
"""
v1.00f - same-family teleport must re-acquire, not hold.

Offline regression (tools/regress_v100_family.py) showed the v1.00 family lock
correctly blocks the menu camera, but it also left the stream parked on the
LOADING camera:

    final owner   : world_loading
    family rejects: 400
    adoptions     : 38

The 38 adoptions are the loading samples. The moment the player enters the world
the camera teleports 250 units (pos (-50,600,80) -> (-60,849.98,80)), which is
> kCamStepTol (50), so `continues` is false. The v0.94 logic then holds and
waits kCamStillTol (90) arrivals before re-acquiring -- by which time the walk
samples have also been withheld, and the lock is still parked on the loading
camera. Nothing freezes any more (the menu camera is refused), but DLSS-G is
fed a stale parked camera, so the frame is still wrong.

The distinction the lock needs, but never had:

    SAME family + large jump  -> the player moved/teleported. RE-ACQUIRE now.
    OTHER family              -> a different render pass. REFUSE, forever.

The family test already separates those two cases, so the same-family branch can
re-acquire immediately on a jump instead of counting to kCamStillTol. The
counter is kept for the no-jump case (a genuinely stalled same-family stream,
e.g. a loading screen that stops updating).

Threshold: kCamJumpTol (400) is reused. It is already the "this cannot be one
frame of walking" bound used everywhere else in this file, and a real scene
change is hundreds of units, so 400 is the natural cut.

Run with --apply to write; without it, dry-run only.
"""
import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPP = os.path.join(ROOT, "src", "FrameGen.cpp")
APPLY = "--apply" in sys.argv

OLD = """				if (++snapLockStill >= kCamStillTol) {
					// The locked stream has not continued for ~1.5 s at 60 Hz, so
					// it is dead (loading screen / scene change) AND the arrival
					// belongs to the same projection family. Re-acquire on this
					// arrival and drop the stale anchor so the next test is made
					// against the new source rather than the old one.
					snapLockHave = true;
					snapLockStill = 0;
					++snapLockRelock;
					snapHaveLast = false;"""

NEW = """				// ---- v1.00f: same-family jump re-acquires immediately ----
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


def main():
    with io.open(CPP, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if "v1.00f: same-family jump re-acquires immediately" in src:
        print("REFUSED: marker already present - patch has run")
        return 1
    n = src.count(OLD)
    if n != 1:
        print("REFUSED: anchor occurs %d times (must be exactly 1)" % n)
        return 1

    out = src.replace(OLD, NEW)

    checks = [
        ("jump branch present", "const bool sameFamJump = (d2 > kCamJumpTol2);" in out),
        ("jump re-acquires", "if (sameFamJump || ++snapLockStill >= kCamStillTol)" in out),
        ("still path keeps its counter", "if (!sameFamJump) ++snapLockRelock;" in out),
        ("jump counter declared", "snapLockRelockJump" in out),
        ("brace balance unchanged", out.count("{") - out.count("}") == src.count("{") - src.count("}")),
        ("family gate still there", "if (!sameFamily) {" in out),
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
    print("\nAPPLIED: same-family jump re-acquires immediately")
    return 0


if __name__ == "__main__":
    sys.exit(main())
