#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.93: decouple snapshot PUBLISHING from the continuity GATES.

ROOT CAUSE (established from the 15:02 run log, not inferred):

  All three gates in AcceptCameraSnapshot() end in `return false`. That return
  value is the PUBLISH VETO at the one call site that matters:

      FrameGen.cpp:583
          if (fg.AcceptCameraSnapshot(*tlsMappedFB))
              fg.SetMappedFrameBuffer(&fg.frameBufferCopy);

  So a rejected snapshot leaves mappedFrameBuffer at its previous value -- and
  before the first accept, at nullptr. FrameGen.h:231 GetFrameBuffer() returns
  exactly that pointer, and DX12SwapChain.cpp:1322 needs it non-null to reach
  SetDLSSGOptions(). The log states the resulting damage numerically:

      [MFG] debug CHECK: ... blocked=483 unblocked=1

  483 Present calls skipped SetDLSSGOptions out of 484. No options were ever
  set, so DLSS-G had nothing to generate with: "dlssgOk=false fail=1" all run.

  And the population being discarded is the REAL camera:
      #9015 JUMP rejected: pos=(-1101.1,880.9,114.0) dist=1185.5 last=(-160.0,160.0,128.0)
      #9019 JUMP rejected: pos=( -865.8,657.2,285.8) dist= 777.1 last=(-504.7,-14.3,135.3)
  (-1101,880,114) / (-865,657,285) are ordinary Skyrim world coordinates. The
  anchor (-160,160,128) is the frozen pose the v0.89 note documented as bogus.
  kCamJumpTol = 400 units cannot distinguish a cell transition from a second
  camera interleaved into the same perFrame buffer.

  v0.89 already reached this conclusion for the SHAPE gate (see the in-tree
  comment "Since AcceptCameraSnapshot() gates SetMappedFrameBuffer(), a
  rejection means DLSS-G never sees that snapshot...") and removed that
  gate's `return false`. The other two were left in place. This completes it.

FIX: all gates keep counting + logging (the observation is the point) but no
longer veto the publish. The self-maintained prev history in Streamline.cpp
supplies the previous frame independently, so withholding a publish only ever
REMOVED data from DLSS-G.

Assertions: marker first, then exactly-one anchors, dry-run default.
"""
import io, sys, hashlib

PATH = "src/FrameGen.cpp"
MARKER = "v0.93: gates observe, they do not discard"

# ---------- edit 1: frozen gate -- drop the veto ----------
OLD1 = """				if (snapFrozenRepeats > kCamFrozenTol) {
					++snapFrozenReject;
					// Keep snapLastMat untouched: the slot is still suspected stale, and
					// the next arrival must be compared against the same reference.
					return false;
				}"""

NEW1 = """				if (snapFrozenRepeats > kCamFrozenTol) {
					++snapFrozenReject;
					// v0.93: gates observe, they do not discard.
					//
					// Keeping snapLastMat untouched is still correct (the slot is
					// still suspected stale, so the next arrival must be compared
					// against the same reference), but the snapshot is no longer
					// withheld from DLSS-G.
					//
					// Why the old `return false` was fatal: SetMappedFrameBuffer()
					// runs ONLY on accept (FrameGen.cpp:583), so a rejection left
					// mappedFrameBuffer null, GetFrameBuffer() null, and Present
					// skipped SetDLSSGOptions altogether. Log: blocked=483 vs
					// unblocked=1. v0.89 removed this same return from the shape
					// gate after proving 80.6% of the discarded population was the
					// real moving camera; the two other gates were left alone.
				}"""

# ---------- edit 2: jump gate -- publish regardless ----------
OLD2 = """		if (snapHaveLast && d2 > kCamJumpTol2) {
			if (snapConsecReject < kCamRelockAfter) {
				++snapConsecReject;
				++snapRejectJump;"""

NEW2 = """		// v0.93: gates observe, they do not discard.
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
				++snapRejectJump;"""

# ---------- edit 3: the jump gate's own `return false` ----------
OLD3 = """				}
				return false;
			}
			++snapRelock;"""
NEW3 = """				}
				// v0.93: no return false here -- see the note above the test.
				// snapLastPos is advanced below like any other arrival, so the
				// jump detector compares against the newest camera instead of
				// latching onto one stale anchor.
			}
			++snapRelock;"""

data = io.open(PATH, "r", encoding="utf-8", newline="").read()

if MARKER in data:
    print("REFUSED: v0.93 already applied. nothing written."); sys.exit(0)

EDITS = [("frozen gate veto", OLD1, NEW1),
         ("jump gate header", OLD2, NEW2),
         ("jump gate veto", OLD3, NEW3)]
for label, old, newv in EDITS:
    c = data.count(old)
    print("anchor '%-18s' count = %d" % (label, c))
    if c != 1:
        print("REFUSED: anchor '%s' count=%d (need exactly 1). nothing written." % (label, c))
        sys.exit(1)

new = data
for label, old, newv in EDITS:
    new = new.replace(old, newv)
assert new != data

print("line endings CRLF %d -> %d | chars %d -> %d (delta %+d)" % (
    data.count("\r\n"), new.count("\r\n"), len(data), len(new), len(new) - len(data)))
if "\r\n" in data and new.count("\r\n") == 0:
    print("REFUSED: would destroy CRLF."); sys.exit(1)

before_false = data.count("return false;")
after_false = new.count("return false;")
print("return false; %d -> %d" % (before_false, after_false))

if "--apply" not in sys.argv:
    print("\nDRY RUN - nothing written. re-run with --apply.")
    sys.exit(0)

io.open(PATH, "w", encoding="utf-8", newline="").write(new)
back = io.open(PATH, "r", encoding="utf-8", newline="").read()
print("\napplied. readback chars =", len(back))
print("marker present:", MARKER in back, "| return false; =", back.count("return false;"))
print("md5 =", hashlib.md5(back.encode("utf-8")).hexdigest())
