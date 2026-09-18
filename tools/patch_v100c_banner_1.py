# -*- coding: utf-8 -*-
"""v1.00c - bump the diagnostic banner to v1.00 so the next log is unambiguous.

The banner is the only reliable way to tell which build produced a log (this
project has already been misled once by reading a log from an older DLL).
Bump it in the same commit as the behaviour change.
"""
import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SL = os.path.join(ROOT, "src", "Streamline.cpp")
APPLY = "--apply" in sys.argv

OLD = 'SKSE::log::info("[XRAY] diag active v0.94 (compiled " __DATE__ " " __TIME__ ")");'
NEW = 'SKSE::log::info("[XRAY] diag active v1.00 (compiled " __DATE__ " " __TIME__ ")");'


def main():
    with io.open(SL, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if "diag active v1.00" in src:
        print("REFUSED: already at v1.00")
        return 1
    n = src.count(OLD)
    if n != 1:
        print("REFUSED: anchor occurs %d times (must be exactly 1)" % n)
        return 1

    out = src.replace(OLD, NEW)
    checks = [
        ("banner now v1.00", "diag active v1.00" in out),
        ("no v0.94 banner left", "diag active v0.94" not in out),
        ("file length delta = 0", len(out) == len(src)),
    ]
    ok = True
    for label, cond in checks:
        print("  %-30s %s" % (label, "PASS" if cond else "FAIL"))
        ok = ok and cond
    if not ok:
        print("REFUSED: post-conditions failed")
        return 1

    if not APPLY:
        print("\nDRY RUN - re-run with --apply")
        return 0
    with io.open(SL, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("\nAPPLIED: banner bumped to v1.00")
    return 0


if __name__ == "__main__":
    sys.exit(main())
