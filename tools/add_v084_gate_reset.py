#!/usr/bin/env python3
"""
v0.84 -- fix the camera gate that froze the picture (the real root cause).

EVIDENCE (14:12 run, v0.83 instrumentation):

    mapHit(perFrame/unmap)=18343/18343          <- engine keeps writing the buffer
    snap(acc/jmp/re/zero/arr/frozen)=1901/4975/0/0/18343/11467
    gate(sawDiff/consecRej/frozenRep/id/diff)=1:8/11587/11587/6756

  * account is exact: 1901 + 4975 + 0 + 11467 == 18343 == arrivals
  * frozenRepeats (11587) - frozenReject (11467) == 120 == kCamFrozenTol
  * sawDiff == 1 in all six heartbeats   -> the sticky flag never clears
  * frozenReject == 11467 of 18343       -> 62.5% of all snapshots rejected

THE BUG (src/FrameGen.cpp, v0.78, mine):

    if (identical && snapSawDifferentSinceRepeat) {
        ++snapFrozenRepeats;
        if (snapFrozenRepeats > kCamFrozenTol) {
            ++snapFrozenReject;
            return false;               // <-- skips everything below
        }
    } else if (!identical) {
        snapSawDifferentSinceRepeat = true;
    }
    ... update snapLastMat ...

  `snapFrozenRepeats` is only ever incremented -- grep finds just the `++` and the
  comparison, never an assignment back to 0.  Compare `snapConsecReject`, which IS
  reset on both paths at lines 650/652.  The frozen counter simply lacks its reset.

  So once the count passes 120 it can only keep rising, and from that moment EVERY
  identical arrival is refused, forever.  That is the freeze:

    - the first 120 identical frames are let through  -> a few seconds of normal play
    - after that, frameBufferCopy is never updated again
    - cur stays equal to prev -> clipToPrevClip = I -> det = 1.000
    - DLSS-G is told "the camera did not move" -> no interpolated frames at all
    - the engine keeps rendering real frames, so engine particles (the campfire)
      keep moving while everything else looks frozen

WHAT THIS PATCH CHANGES (three edits, all inside the frozen gate):

  A. Reset `snapFrozenRepeats` when a genuinely different matrix arrives.
     A different matrix proves the stream is live, so the "stale slot" hypothesis
     is disproved and the run must start over.  (The actual missing line.)

  B. Reset it on the non-identical path instead of just raising the sticky flag.
     This is the same edit point as A but spelled out so the intent is explicit:
     seeing a different camera is exactly the event that means "not stale".

  C. Require the identical run to be *consecutive* for the rejection to count.
     `snapFrozenRepeats` now counts consecutive identical arrivals; any different
     arrival zeroes it (A/B).  Reject from the 121st consecutive identical frame,
     which is the original intent -- but now reachable again after the stream
     proves it is alive.

  D. Make the freeze threshold configurable and raise the default to 600 frames
     (~10 s at 60 fps).  A legitimate still scene (reading a menu, standing at a
     forge) lasting 2 s was already inside the old 120-frame window, and the cost
     of a slightly later detection is one stale frame, while the cost of a false
     positive is a hard freeze.

Nothing else is touched: the jump gate, the relock hatch, and the accept path all
keep their current behaviour.
"""

import io
import sys

CPP = "src/FrameGen.cpp"   # LF
NL = "\n"

OLD = NL.join([
    "\t\t\tif (identical && snapSawDifferentSinceRepeat) {",
    "\t\t\t\t// Same matrix as last time, but we saw a different camera in",
    "\t\t\t\t// between => this is a stale slot being re-read, not a still scene.",
    "\t\t\t\t++snapFrozenRepeats;",
    "\t\t\t\t// Allow a short run before rejecting: a teleport / scene change can",
    "\t\t\t\t// legitimately re-present a previously seen matrix once.",
    "\t\t\t\tif (snapFrozenRepeats > kCamFrozenTol) {",
    "\t\t\t\t\t++snapFrozenReject;",
    "\t\t\t\t\treturn false;",
    "\t\t\t\t}",
    "\t\t\t} else if (!identical) {",
    "\t\t\t\tsnapSawDifferentSinceRepeat = true;",
    "\t\t\t}",
]) + NL

NEW = NL.join([
    "\t\t\tif (identical && snapSawDifferentSinceRepeat) {",
    "\t\t\t\t// Same matrix as last time, but we saw a different camera in",
    "\t\t\t\t// between => this is a stale slot being re-read, not a still scene.",
    "\t\t\t\t++snapFrozenRepeats;",
    "\t\t\t\t// v0.84: reject only after kCamFrozenTol *consecutive* identical",
    "\t\t\t\t// arrivals. The counter is reset below as soon as a different matrix",
    "\t\t\t\t// shows up (v0.78 never reset it, so it grew without bound and the",
    "\t\t\t\t// gate latched on permanently -- see add_v084_gate_reset.py header).",
    "\t\t\t\tif (snapFrozenRepeats > kCamFrozenTol) {",
    "\t\t\t\t\t++snapFrozenReject;",
    "\t\t\t\t\t// Keep snapLastMat untouched: the slot is still suspected stale, and",
    "\t\t\t\t\t// the next arrival must be compared against the same reference.",
    "\t\t\t\t\treturn false;",
    "\t\t\t\t}",
    "\t\t\t} else if (!identical) {",
    "\t\t\t\tsnapSawDifferentSinceRepeat = true;",
    "\t\t\t\t// v0.84: a genuinely different matrix proves the stream is alive, so",
    "\t\t\t\t// the stale-slot run is over and the consecutive count restarts.",
    "\t\t\t\t// This reset is the actual fix: without it the count only ever grows,",
    "\t\t\t\t// so past kCamFrozenTol every identical frame is refused forever.",
    "\t\t\t\tsnapFrozenRepeats = 0;",
    "\t\t\t\t++snapFrozenResets;",
    "\t\t\t}",
]) + NL

# The threshold constant lives in an anonymous namespace near the other gates.
# NOTE: verified byte-for-byte against src/FrameGen.cpp (LF file, ONE tab indent
# on the constant itself -- it is a namespace-scope declaration, not a member).
# An earlier revision of this script used two tabs here and the anchor missed.
TOL_OLD = ("\t// v0.78: how many consecutive identical-matrix arrivals (with a different\n"
           "\t// matrix seen in between) before we call the slot stale. The 08:59 run showed\n"
           "\t// 4196 repeats in 2.34 s, so 120 trips in well under one frame at that rate\n"
           "\t// and cannot misfire on a legitimate still period that later resumes moving.\n"
           "\tconstexpr std::uint32_t kCamFrozenTol = 120;\n")

TOL_NEW = ("\t// v0.78: how many consecutive identical-matrix arrivals (with a different\n"
           "\t// matrix seen in between) before we call the slot stale. The 08:59 run showed\n"
           "\t// 4196 repeats in 2.34 s, so 120 trips in well under one frame at that rate\n"
           "\t// and cannot misfire on a legitimate still period that later resumes moving.\n"
           "\t//\n"
           "\t// v0.84: raised 120 -> 600, and the counter is now actually reset when a\n"
           "\t// different matrix arrives (v0.78 only incremented it). 120 frames is 2 s\n"
           "\t// at 60 fps, which a legitimate still scene reaches trivially -- a menu, a\n"
           "\t// forge, reading a book. A false positive froze the picture permanently,\n"
           "\t// while a late detection costs one stale frame, so the trade is lopsided.\n"
           "\tconstexpr std::uint32_t kCamFrozenTol = 600;\n")

# Counter for the reset, so the next log can prove the fix is live.
HDR = "src/FrameGen.h"
HNL = "\r\n"
H_ANCHOR = (HNL.join([
    "\t\tstd::uint64_t snapIdenticalArrivals = 0;  // matrix == snapLastMat",
    "\t\tstd::uint64_t snapDifferentArrivals = 0;  // matrix != snapLastMat",
]) + HNL)
H_NEW = (H_ANCHOR + HNL.join([
    "\t\t// v0.84: how many times a different matrix reset the consecutive-identical",
    "\t\t// run. If this stays 0 for a whole run, the gate is still counting without",
    "\t\t// resetting and the freeze will come back.",
    "\t\tstd::uint64_t snapFrozenResets = 0;",
]) + HNL)

EDITS = [
    (CPP, "gate: reset + consecutive", OLD, NEW),
    (CPP, "tol: 120 -> 600", TOL_OLD, TOL_NEW),
    (HDR, "counter: snapFrozenResets", H_ANCHOR, H_NEW),
]

MARKERS = ["v0.84", "snapFrozenResets", "kCamFrozenTol = 600"]


def main():
    apply = "--apply" in sys.argv
    print("=" * 74)
    print("v0.84 camera-gate reset fix  (mode: %s)" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    files = {}
    for path in (CPP, HDR):
        with io.open(path, "rb") as f:
            files[path] = f.read().decode("utf-8")

    for path, s in files.items():
        hit = [m for m in MARKERS if m in s]
        if hit:
            print("markers   : ALREADY PRESENT in %s -> REFUSED" % path)
            for m in hit:
                print("   found: %s" % m)
            return 2
    print("markers   : absent (patch has not run)")

    ok = True
    for path, label, old, new in EDITS:
        n = files[path].count(old)
        if n != 1:
            ok = False
        print("  [%s][%-30s] occurrences=%d  %s"
              % (path.split("/")[-1], label, n, "ok" if n == 1 else "FAIL"))
    if not ok:
        print("REFUSED: anchor not unique. nothing written.")
        return 2

    for path, label, old, new in EDITS:
        d = (new.count("{") - new.count("}")) - (old.count("{") - old.count("}"))
        if d != 0:
            ok = False
        print("balance   : [%-30s] %+d  %s" % (label, d, "ok" if d == 0 else "FAIL"))
    if not ok:
        print("REFUSED: brace balance moved. nothing written.")
        return 2

    out = {p: s for p, s in files.items()}
    for path, _label, old, new in EDITS:
        out[path] = out[path].replace(old, new, 1)

    print("")
    for path in (CPP, HDR):
        a = len(files[path].encode("utf-8"))
        b = len(out[path].encode("utf-8"))
        print("  %-28s %7d -> %7d bytes (%+d)" % (path, a, b, b - a))

    if not apply:
        print("DRY RUN: nothing written. Re-run with --apply.")
        return 0

    for path in (CPP, HDR):
        with io.open(path, "wb") as f:
            f.write(out[path].encode("utf-8"))
        print("WRITTEN   : %s" % path)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
