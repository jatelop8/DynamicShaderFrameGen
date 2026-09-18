#!/usr/bin/env python3
"""
v0.84c -- stamp the build version into the log header.

Every round so far has cost a cycle on "did the new DLL actually load?".
The heartbeat says "diag active v0.61", which has not changed in twenty
revisions, so it cannot answer that question.  Put the real version there.

src/Streamline.cpp is LF.
"""

import io
import sys

CPP = "src/Streamline.cpp"
NL = "\n"

OLD = '				SKSE::log::info("[XRAY] diag active v0.61 (compiled "'
NEW = '				SKSE::log::info("[XRAY] diag active v0.84 (compiled "'

EDITS = [(CPP, "log tag v0.61 -> v0.84", OLD, NEW)]
MARKERS = ["v0.84 (compiled"]


def main():
    apply = "--apply" in sys.argv
    print("=" * 74)
    print("v0.84c log tag  (mode: %s)" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    with io.open(CPP, "rb") as f:
        src = f.read().decode("utf-8")

    hit = [m for m in MARKERS if m in src]
    if hit:
        print("markers   : ALREADY PRESENT -> REFUSED")
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

    out = src
    for _p, _l, old, new in EDITS:
        out = out.replace(old, new, 1)

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
