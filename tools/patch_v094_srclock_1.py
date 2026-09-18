#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.94: replace distance-gating (v0.67-v0.93) with SOURCE LOCKING.

WHY v0.93 WAS WRONG (it caused a CTD -- my own regression):

  v0.93 removed the `return false` from the frozen and jump gates on the theory
  that "withholding a publish only removes data". That was right about ONE
  source and catastrophically wrong about SEVERAL. The 16:04 crash log shows
  what the perFrame buffer actually carries:

      accepting pos=(-50.0,600.00,80.00)   551 times, CONSTANT
      accepting pos=(-160.0,160.00,128.00) 806 times, CONSTANT
      accepting pos=(-50.0,899.6,96.0)
                   (-50.0,899.5,96.0)
                   (-50.0,899.2,95.9) ...  <- a SMOOTHLY MOVING camera

  With every arrival published, those sources take turns owning
  frameBufferCopy, so consecutive frames hand DLSS-G cameras at
  (-50,900,96) then (-160,160,128) then (-50,600,80) -- hundreds of units
  apart, every frame. Consequence in the same log:

      [CAM] #7818 RELOCK after 1 consecutive jumps
      [CAM] #7824 RELOCK after 1 consecutive jumps
      [CAM] #7837 RELOCK after 1 consecutive jumps
      ... one RELOCK per arrival, and path=845264.19 -> 864056.62

  plus a published pos=(0.0,0.0,1.0) (a unit vector, not a position).
  Interleaved cameras at 30 Hz is a direct CTD, not a flicker.

WHY THE OLD DISTANCE GATE WAS ALSO WRONG:

  It assumed "the camera moves < 400 units/frame" and used that to pick ONE
  source. It picks whichever source it saw first and rejects every other --
  and the crash log shows it locked onto (-160,160,128), a CONSTANT, while
  rejecting the smooth (y: 900->894->...) camera. So it was simultaneously
  (a) discarding the real camera and (b) never re-evaluating. Both v0.89's
  "release everything" and v0.67's "reject the far one" are wrong because
  neither asks the right question.

THE RIGHT QUESTION: is this arrival part of the SAME TEMPORAL STREAM as the
one I am already publishing?

  A real camera stream is CONTINUOUS: each arrival is a small step from the
  previous one *of the same source*. A garbage slot is CONSTANT or jumps
  without a path. So:

    * Lock onto a source (identified by its own recent behaviour).
    * Publish an arrival only if it CONTINUES the locked stream.
    * Re-lock only when the locked stream has visibly STOPPED (so a scene
      change / loading screen can move us to the new camera), never merely
      because a different value showed up.

  Concretely, an arrival CONTINUES the stream when its position is a small
  step (<= kCamStepTol) from the last published one. An arrival is a NEW
  CANDIDATE when it repeats an identical value (a constant slot) - constants
  are what a stale slot looks like, and a moving camera never repeats exactly.

  This keeps ONE source published, which is what DLSS-G needs, and it never
  needs a 400-unit teleport heuristic.

Assertions: marker first, then exactly-one anchors, dry-run default.
"""
import io, sys, hashlib

PATH = "src/FrameGen.cpp"
HDR = "src/FrameGen.h"
MARKER = "v0.94: source locking"

# ---------------- FrameGen.h : new state ----------------
HOLD = """		bool  snapSawDifferentSinceRepeat = false;"""
HNEW = """		bool  snapSawDifferentSinceRepeat = false;
		// ---- v0.94: source locking (replaces the distance gate) --------------
		// The 16:04 CTD proved one perFrame buffer carries SEVERAL cameras that
		// take turns: two CONSTANT slots (-50,600,80) and (-160,160,128), plus a
		// smoothly moving one (-50, 900->894, 96). Publishing all of them hands
		// DLSS-G a camera hundreds of units from the last one every frame.
		//
		// v0.67 tried to pick one by distance (<400 units = same camera) and
		// locked onto a CONSTANT slot while rejecting the moving one. The test
		// asks the wrong question: not "is it far" but "does it CONTINUE the
		// stream I am already publishing".
		//
		// An arrival continues the stream when it is a SMALL STEP from the last
		// published position. A constant slot is recognisable because it repeats
		// an exactly identical value, which a moving camera never does.
		std::uint64_t snapLockPublish = 0;    // arrivals published onto the stream
		std::uint64_t snapLockHold = 0;       // arrivals withheld (other source)
		std::uint64_t snapLockRelock = 0;     // times the stream was re-acquired
		std::uint32_t snapLockStill = 0;      // consecutive non-continuing arrivals
		bool  snapLockHave = false;           // a stream is locked"""

# ---------------- FrameGen.cpp : constants ----------------
COLD = """		constexpr float kCamJumpTol = 400.0f;
		constexpr float kCamJumpTol2 = kCamJumpTol * kCamJumpTol;
		constexpr std::uint32_t kCamRelockAfter = 12;"""
CNEW = """		constexpr float kCamJumpTol = 400.0f;
		constexpr float kCamJumpTol2 = kCamJumpTol * kCamJumpTol;
		constexpr std::uint32_t kCamRelockAfter = 12;

		// ---- v0.94: source locking thresholds ---------------------------------
		// A real camera advances by a SMALL step per arrival. The crash log's
		// genuine stream moved 900 -> 894 over ~50 arrivals, i.e. well under one
		// unit per arrival; the interleaved constants differed by hundreds. 50
		// units is two orders of magnitude above the real step and two orders
		// below the inter-source gap, so it separates them with no ambiguity.
		constexpr float kCamStepTol = 50.0f;
		constexpr float kCamStepTol2 = kCamStepTol * kCamStepTol;
		// How many consecutive non-continuing arrivals before the locked stream
		// is declared dead and a new source may be acquired. 90 arrivals is ~1.5 s
		// at 60 Hz: long enough that an interleaved slot cannot steal the lock
		// (it never gets 90 in a row while the real camera keeps arriving),
		// short enough that a genuine scene change re-locks promptly.
		constexpr std::uint32_t kCamStillTol = 90;"""

data = io.open(PATH, "r", encoding="utf-8", newline="").read()
hdr = io.open(HDR, "r", encoding="utf-8", newline="").read()

if MARKER in data or MARKER in hdr:
    print("REFUSED: v0.94 already applied. nothing written."); sys.exit(0)

EDITS = [
    ("hdr state", hdr, HOLD, HNEW),
    ("cpp consts", data, COLD, CNEW),
]
for label, text, old, newv in EDITS:
    c = text.count(old)
    print("anchor '%-12s' count = %d" % (label, c))
    if c != 1:
        print("REFUSED: anchor '%s' count=%d (need exactly 1)." % (label, c)); sys.exit(1)

hdr_new = hdr.replace(HOLD, HNEW)
data_new = data.replace(COLD, CNEW)

if "--apply" not in sys.argv:
    print("\nDRY RUN (stage 1 of 2). nothing written.")
    sys.exit(2)
io.open(HDR, "w", encoding="utf-8", newline="").write(hdr_new)
io.open(PATH, "w", encoding="utf-8", newline="").write(data_new)
print("stage 1 applied.")
