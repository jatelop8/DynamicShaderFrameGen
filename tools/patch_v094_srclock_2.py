#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.94 stage 2: replace the distance gate with the source lock in
AcceptCameraSnapshot().

Replaces the block from the `// v0.93: gates observe` comment through the
`} else { snapConsecReject = 0; }` that follows the RELOCK log, with:

  * a CONTINUITY test (small step from the last PUBLISHED position)
  * lock acquisition / hold / re-acquisition
  * the publish itself, which now happens only for the locked stream

Assertions: marker first, exactly-one anchor, dry-run default.
"""
import io, sys, hashlib

PATH = "src/FrameGen.cpp"
MARKER = "v0.94: source lock (replaces the distance gate)"

OLD = """		// v0.93: gates observe, they do not discard.
		//
		// The jump test below is unchanged as an OBSERVATION: it still counts
		// (snapRejectJump) and still logs. What is gone is its power to veto the
		// publish. Evidence it was vetoing the real camera:
		//   #9015 JUMP rejected: pos=(-1101.1,880.9,114.0)
		//                        dist=1185.5 last=(-160.0,160.0,128.0)
		//   #9019 JUMP rejected: pos=( -865.8,657.2,285.8)
		//                        dist= 777.1 last=(-504.7,-14.3,135.3)
		// Those rejected positions are ordinary Skyrim world coordinates; the
		// anchor is the frozen (-160,160,128) pose. kCamJumpTol=400 units cannot
		// tell a legitimate cell transition from a second camera interleaved
		// into the same perFrame buffer.
		if (snapHaveLast && d2 > kCamJumpTol2) {
			if (snapConsecReject < kCamRelockAfter) {
				++snapConsecReject;
				++snapRejectJump;
				// v0.69: throttled. v0.67 logged every rejection -- 2862 lines in 42 s
				// (71 lines/s), 3111 of the file's 3222 lines. The log became the dominant
				// cost and buried everything else. Totals stay in the heartbeat
				// (snap acc/jmp/re/zero/arr), so only the first few and a slow periodic
				// sample are printed here.
				if (snapRejectJump <= 3u || (snapRejectJump % 250u) == 0u) {
					DumpCameraSnapshot(a_src, snapArrivals, 3);
					SKSE::log::info("[CAM] #{} JUMP rejected: pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} "
						"last=({:.1f},{:.1f},{:.1f}) consec={}",
						snapArrivals, px, py, pz, std::sqrt(d2),
						snapLastPos[0], snapLastPos[1], snapLastPos[2], snapConsecReject);
					(void)snapFrozenReject;
				}
				// v0.93: no return false here -- see the note above the test.
				// snapLastPos is advanced below like any other arrival, so the
				// jump detector compares against the newest camera instead of
				// latching onto one stale anchor.
			}
			++snapRelock;
			// v0.76: this hatch exists for a real teleport / scene change, but it
			// also fires on a schedule when several cameras rotate through one
			// perFrame buffer -- each frame is >400 units from the last accepted
			// one, so after 12 consecutive rejections it accepts whichever camera
			// happens to be standing there. Record *which* camera it took, so a
			// wrong one is visible instead of being silently installed as the
			// world camera for the next 12 frames.
			SKSE::log::warn("[CAM] #{} RELOCK after {} consecutive jumps (teleport / scene change) "
				"-> accepting pos=({:.1f},{:.1f},{:.1f}) devVP={:.6g} magVP={:.6g}",
				snapArrivals, snapConsecReject, px, py, pz,
				camDev(a_src.CameraViewProjUnjittered), camMag(a_src.CameraViewProjUnjittered));
			snapConsecReject = 0;
		} else {
			snapConsecReject = 0;
		}

		frameBufferCopy = a_src;
		++snapAccept;"""

NEW = """		// ---- v0.94: source lock (replaces the distance gate) ------------------
		//
		// WHY THE DISTANCE GATE HAD TO GO
		//
		// v0.67..v0.93 decided which arrival to publish by distance: "a camera
		// cannot move 400 units in one frame, so a far arrival is a different
		// source -- reject it". That test cannot work, because the two things it
		// tries to separate are NOT separated by distance:
		//
		//   - the real camera, moving smoothly, and
		//   - two CONSTANT slots re-read every frame,
		//
		// all coexist in one perFrame buffer, and the distance between them
		// changes as the player walks. Worse, it never re-asks the question: it
		// locks onto whichever source it saw first and then rejects the others
		// forever. The 16:04 log shows exactly that -- it held (-160,160,128),
		// a CONSTANT, while rejecting the smoothly moving (-50,900->894,96):
		//
		//     #9015 JUMP rejected: pos=(-1101.1,880.9,114.0) last=(-160.0,160.0,128.0)
		//     accepting      pos=(-160.0,160.0,128.0)   <- 806 times, CONSTANT
		//
		// WHY RELEASING EVERYTHING (v0.93) WAS WORSE
		//
		// v0.93 removed the veto entirely, so all sources took turns owning
		// frameBufferCopy. Consecutive frames handed DLSS-G cameras hundreds of
		// units apart, every frame, and the game CTD'd:
		//
		//     #7818 RELOCK after 1 consecutive jumps -> pos=(-1101.1,880.9,114.0)
		//     #7824 RELOCK after 1 consecutive jumps -> pos=( -126.3,211.2,188.9)
		//     #7837 RELOCK after 1 consecutive jumps -> pos=(    0.0,  0.0,  1.0)
		//     path=845264.19 -> 864056.62
		//
		// THE ACTUAL QUESTION
		//
		// Not "is this arrival far", but "does it CONTINUE the stream I am
		// already publishing?". A real camera advances by a small step between
		// consecutive arrivals; a stale slot is either constant or unrelated. So:
		//
		//   - while locked, publish ONLY arrivals that step <= kCamStepTol from
		//     the last published position (that is the same source continuing);
		//   - count the rest; if the locked stream does not continue for
		//     kCamStillTol arrivals in a row, the stream is gone (scene change,
		//     loading screen) and the next arrival re-acquires the lock.
		//
		// The lock guarantees exactly one source is published at a time, which is
		// what DLSS-G needs, and it never relies on a teleport heuristic.
		{
			const bool continues = snapLockHave && snapHaveLast && (d2 <= kCamStepTol2);
			if (!snapLockHave) {
				// First arrival, or the locked stream died: acquire.
				snapLockHave = true;
				snapLockStill = 0;
				if (snapLockRelock > 0u || snapAccept > 0u)
					++snapLockRelock;
			} else if (!continues) {
				// A different source showed up. Hold it; do not publish, and do
				// not let it move the anchor. If the locked stream keeps failing
				// to continue, it is genuinely gone and we re-acquire below.
				++snapLockHold;
				if (++snapLockStill >= kCamStillTol) {
					// The locked stream has not continued for ~1.5 s at 60 Hz, so
					// it is dead (loading screen / scene change). Re-acquire on
					// this arrival and drop the stale anchor so the next test is
					// made against the new source rather than the old one.
					snapLockHave = true;
					snapLockStill = 0;
					++snapLockRelock;
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
				}
			} else {
				snapLockStill = 0;
			}
			++snapLockPublish;
		}

		frameBufferCopy = a_src;
		++snapAccept;"""

data = io.open(PATH, "r", encoding="utf-8", newline="").read()

if MARKER in data:
    print("REFUSED: v0.94 stage 2 already applied."); sys.exit(0)

c = data.count(OLD)
print("anchor count =", c)
if c != 1:
    print("REFUSED: anchor count=%d (need exactly 1). nothing written." % c); sys.exit(1)

new = data.replace(OLD, NEW)
assert new != data
print("line endings CRLF %d -> %d | chars %d -> %d (delta %+d)" % (
    data.count("\r\n"), new.count("\r\n"), len(data), len(new), len(new) - len(data)))
if "\r\n" in data and new.count("\r\n") == 0:
    print("REFUSED: would destroy CRLF."); sys.exit(1)
print("return false;  %d -> %d" % (data.count("return false;"), new.count("return false;")))

if "--apply" not in sys.argv:
    print("\nDRY RUN - nothing written.")
    sys.exit(0)
io.open(PATH, "w", encoding="utf-8", newline="").write(new)
back = io.open(PATH, "r", encoding="utf-8", newline="").read()
print("\napplied. chars =", len(back), "| marker:", MARKER in back)
print("return false; =", back.count("return false;"))
print("md5 =", hashlib.md5(back.encode("utf-8")).hexdigest())
