#!/usr/bin/env python3
"""
v0.82 -- add the two diagnostic counters used by add_v082_prev_history_shared.py.

  prevSeededFromEngine  : how many times the missing self-maintained prev was
                          seeded from the engine's CameraPreviousViewProjUnjittered.
  prevMissUsedLastGood  : how many times the no-history branch reused a legal
                          previous clipToPrevClip instead of writing identity.

Both are reported in the heartbeat next to prevHistoryMiss, so the next log can
show directly whether the fix is doing anything.
"""

import io
import sys

HDR = "src/Streamline.h"

T = "\t" * 3   # indentation actually used in the header
NL = "\r\n"    # Streamline.h is CRLF

ANCHOR = (T + "std::uint64_t prevHistoryHits = 0;" + NL
          + T + "std::uint64_t prevHistoryMiss = 0;" + NL)

ADD = (ANCHOR
       + T + "// v0.82: no self-maintained history -> seed from the engine's prev." + NL
       + T + "// This build reports the engine prev as an all-zero matrix" + NL
       + T + "// (engPrevZero=241), so a value that stays 0 means the seed never took." + NL
       + T + "std::uint64_t prevSeededFromEngine = 0;" + NL
       + T + "// v0.82: no-history branch reused a legal previous clipToPrevClip instead" + NL
       + T + "// of writing identity. Identity means 'camera did not move' to DLSS-G." + NL
       + T + "std::uint64_t prevMissUsedLastGood = 0;" + NL)

MARKERS = [
    "v0.82: no self-maintained history -> seed from the engine's prev.",
    "v0.82: no-history branch reused a legal previous clipToPrevClip instead",
]


def main():
    apply = "--apply" in sys.argv
    with io.open(HDR, "rb") as f:
        src = f.read().decode("utf-8")

    print("=" * 74)
    print("v0.82 diag counters  (mode: %s)" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    found = [m for m in MARKERS if m in src]
    if found:
        print("markers   : ALREADY PRESENT -> REFUSED, nothing written")
        for m in found:
            print("   found: %s" % m)
        return 2
    print("markers   : absent (patch has not run)")

    n = src.count(ANCHOR)
    print("  [%-26s] occurrences=%d  %s" % ("counters anchor", n, "ok" if n == 1 else "FAIL"))
    if n != 1:
        print("REFUSED: anchor is not unique. nothing written.")
        return 2

    d = (ADD.count("{") - ADD.count("}")) - (ANCHOR.count("{") - ANCHOR.count("}"))
    print("balance   : %-26s %+d  %s" % ("counters", d, "ok" if d == 0 else "FAIL"))
    if d != 0:
        print("REFUSED: brace balance moved. nothing written.")
        return 2

    out = src.replace(ANCHOR, ADD, 1)
    print("")
    print("  %-28s %7d -> %7d bytes (%+d)" % (HDR, len(src.encode("utf-8")),
                                               len(out.encode("utf-8")),
                                               len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    if not apply:
        print("DRY RUN: nothing written. Re-run with --apply.")
        return 0

    with io.open(HDR, "wb") as f:
        f.write(out.encode("utf-8"))
    print("WRITTEN   : %s" % HDR)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
