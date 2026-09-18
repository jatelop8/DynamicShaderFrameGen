#!/usr/bin/env python3
"""
v0.82 -- surface the two new counters in the [XRAY] heartbeat.

Adds `seed={} missGood={}` right after `hist(hit/miss)={}/{}` so the next log
shows, in the same line as everything else, whether the v0.82 fix is doing work:

  seed    = prevSeededFromEngine   (prev missing -> engine prev used)
  missGood= prevMissUsedLastGood   (prev missing -> legal last clip reused)

Both being 0 for a whole run means the no-history branch is still writing
identity, i.e. the fix is not reaching the failing path.
"""

import io
import sys

CPP = "src/Streamline.cpp"

FMT_ANCHOR = '"clipDevMax={:.4f} hist(hit/miss)={}/{} det(min/max)={:.3f}/{:.3f} "'
FMT_NEW = ('"clipDevMax={:.4f} hist(hit/miss)={}/{} seed={} missGood={} "'
           ' \n\t\t\t\t\t"det(min/max)={:.3f}/{:.3f} "')

ARG_ANCHOR = "\t\t\t\t\tdiag.prevHistoryHits, diag.prevHistoryMiss,\n"
ARG_NEW = ("\t\t\t\t\tdiag.prevHistoryHits, diag.prevHistoryMiss,\n"
           "\t\t\t\t\tdiag.prevSeededFromEngine, diag.prevMissUsedLastGood,\n")

MARKERS = ["seed={} missGood={}", "diag.prevSeededFromEngine, diag.prevMissUsedLastGood,"]


def main():
    apply = "--apply" in sys.argv
    with io.open(CPP, "rb") as f:
        src = f.read().decode("utf-8")

    print("=" * 74)
    print("v0.82 heartbeat counters  (mode: %s)" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    found = [m for m in MARKERS if m in src]
    if found:
        print("markers   : ALREADY PRESENT -> REFUSED, nothing written")
        for m in found:
            print("   found: %s" % m)
        return 2
    print("markers   : absent (patch has not run)")

    ok = True
    for label, old in (("fmt anchor", FMT_ANCHOR), ("arg anchor", ARG_ANCHOR)):
        n = src.count(old)
        if n != 1:
            ok = False
        print("  [%-26s] occurrences=%d  %s" % (label, n, "ok" if n == 1 else "FAIL"))
    if not ok:
        print("REFUSED: anchor not unique. nothing written.")
        return 2

    # The format string gains two {} placeholders, and so does the argument list.
    # Count them explicitly: a mismatch is a compile-time error at best, a
    # misaligned varargs read at worst.
    f_add = FMT_NEW.count("{}") - FMT_ANCHOR.count("{}")
    a_add = ARG_NEW.count("diag.") - ARG_ANCHOR.count("diag.")
    print("  [%-26s] format +%d  args +%d  %s"
          % ("placeholder balance", f_add, a_add, "ok" if f_add == a_add else "FAIL"))
    if f_add != a_add:
        print("REFUSED: placeholder/argument count mismatch. nothing written.")
        return 2

    out = src.replace(FMT_ANCHOR, FMT_NEW, 1).replace(ARG_ANCHOR, ARG_NEW, 1)

    print("")
    print("  %-28s %7d -> %7d bytes (%+d)" % (CPP, len(src.encode("utf-8")),
                                               len(out.encode("utf-8")),
                                               len(out.encode("utf-8")) - len(src.encode("utf-8"))))
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
