#!/usr/bin/env python3
"""
v0.84b -- expose snapFrozenResets in the heartbeat.

A counter nobody prints is a counter nobody can trust: the last two rounds both
ended with "I changed it, but I cannot see whether it ran".  Print the reset
count next to the frozen counters, and print the reject ratio, so the next log
answers the question by itself:

  * frozenResets stays 0        -> the reset never fires, freeze will return
  * frozenResets == frozenRep   -> every identical run was bracketed by a
                                   different matrix (healthy stream)
  * rejPct high and not moving  -> the gate is still eating frames

Nothing else is touched.
"""

import io
import sys

CPP = "src/Streamline.cpp"   # LF
NL = "\n"

FMT_OLD = NL.join([
    '\t\t\t\t\t"snap(acc/jmp/re/zero/arr/frozen)={}/{}/{}/{}/{}/{} "',
    '\t\t\t\t\t"gate(sawDiff/consecRej/frozenRep/id/diff)={}:{}/{}/{}/{} "',
]) + NL

FMT_NEW = NL.join([
    '\t\t\t\t\t"snap(acc/jmp/re/zero/arr/frozen/rejPct)={}/{}/{}/{}/{}/{} {:.1f}% "',
    '\t\t\t\t\t"gate(sawDiff/consecRej/frozenRep/resets/id/diff)={}:{}/{}/{}/{}/{} "',
]) + NL

ARG_OLD = NL.join([
    "\t\t\t\t\tGet().snapRejectZero, Get().snapArrivals, Get().snapFrozenReject,",
    "\t\t\t\t\tGet().snapSawDifferentSinceRepeat ? 1 : 0, Get().snapConsecReject,",
    "\t\t\t\t\tGet().snapFrozenRepeats,",
    "\t\t\t\t\tGet().snapIdenticalArrivals, Get().snapDifferentArrivals,",
]) + NL

ARG_NEW = NL.join([
    "\t\t\t\t\tGet().snapRejectZero, Get().snapArrivals, Get().snapFrozenReject,",
    "\t\t\t\t\tGet().snapArrivals",
    "\t\t\t\t\t\t? 100.0 * static_cast<double>(Get().snapFrozenReject)",
    "\t\t\t\t\t\t\t/ static_cast<double>(Get().snapArrivals)",
    "\t\t\t\t\t\t: 0.0,",
    "\t\t\t\t\tGet().snapSawDifferentSinceRepeat ? 1 : 0, Get().snapConsecReject,",
    "\t\t\t\t\tGet().snapFrozenRepeats, Get().snapFrozenResets,",
    "\t\t\t\t\tGet().snapIdenticalArrivals, Get().snapDifferentArrivals,",
]) + NL

EDITS = [
    (CPP, "heartbeat: format adds rejPct/resets", FMT_OLD, FMT_NEW),
    (CPP, "heartbeat: args add ratio/resets", ARG_OLD, ARG_NEW),
]

MARKERS = ["snapFrozenResets,", "rejPct"]


def main():
    apply = "--apply" in sys.argv
    print("=" * 74)
    print("v0.84b heartbeat exposure  (mode: %s)" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    with io.open(CPP, "rb") as f:
        src = f.read().decode("utf-8")

    hit = [m for m in MARKERS if m in src]
    if hit:
        print("markers   : ALREADY PRESENT -> REFUSED")
        for m in hit:
            print("   found: %s" % m)
        return 2
    print("markers   : absent (patch has not run)")

    ok = True
    for path, label, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            ok = False
        print("  [%-30s] occurrences=%d  %s" % (label, n, "ok" if n == 1 else "FAIL"))
    if not ok:
        print("REFUSED: anchor not unique. nothing written.")
        return 2

    print("  format placeholders: old=%d new=%d args: old=%d new=%d"
          % (EDITS[0][2].count("{}") + EDITS[0][2].count("{:.1f}"),
             EDITS[0][3].count("{}") + EDITS[0][3].count("{:.1f}"),
             EDITS[1][2].count(","), EDITS[1][3].count(",")))

    out = src
    for _p, _l, old, new in EDITS:
        out = out.replace(old, new, 1)

    print("  %-28s %7d -> %7d bytes (%+d)"
          % (CPP, len(src.encode()), len(out.encode()), len(out.encode()) - len(src.encode())))

    if not apply:
        print("DRY RUN: nothing written. Re-run with --apply.")
        return 0

    with io.open(CPP, "wb") as f:
        f.write(out.encode("utf-8"))
    print("WRITTEN   : %s" % CPP)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
