# -*- coding: utf-8 -*-
"""
regress_v103_family.py -- offline regression for the v1.03 camera-family fix.

The bug (verified in the 18:23 log):
    [CAM] #2 family rejected: proj00=1 locked=0.149184 ratio=6.7031 pos=(-160.0,160.0,128.0) dist=456.1

The old rule was a pure ratio test: sameFamily = (ratio in 0.98 .. 1.02).
For proj00 == 1.0 against a locked 0.149184 that yields ratio 6.7031 -> a
"different family", and because the same flag also gates re-acquisition u
legal camera could pin the lock forever.

The new rule classifies by MAGNITUDE first:
    unitProj = proj00 near 1.0        lockUnit = locked near 1.0
    unitProj != lockUnit  -> sameFamily = true (a legal second camera)
    else                  -> ratio test as before

This script replays both rules over the scenarios that matter and prints a
verdict per row, so "the fix works" is a table and not an opinion.

Usage:  python tools/regress_v103_family.py
"""

import sys


def old_rule(proj00, locked):
    if not (proj00 == proj00 and proj00 > 1.0e-6):
        return True
    ratio = proj00 / locked
    return 0.98 < ratio < 1.02


def new_rule(proj00, locked):
    if not (proj00 == proj00 and proj00 > 1.0e-6):
        return True
    unit = 0.995 < proj00 < 1.005
    lock_unit = 0.995 < locked < 1.005
    if unit != lock_unit:
        return True                       # legal second camera
    ratio = proj00 / locked
    return 0.98 < ratio < 1.02


# (label, proj00, locked, expected_same_family)
CASES = [
    ("world camera, tiny FOV drift  ", 0.149100, 0.149184, True),
    ("world camera, resolution nudge", 0.149184, 0.149184, True),
    ("world -> menu (5.62x apart)    ", 0.839100, 0.149184, False),
    ("menu  -> world (1/5.62)        ", 0.149184, 0.839100, False),
    ("THE 18:23 CASE: unit vs world  ", 1.000000, 0.149184, True),
    ("world vs unit (reverse)        ", 0.149184, 1.000000, True),
    ("menu vs unit                   ", 0.839100, 1.000000, True),
    ("unit vs menu                   ", 1.000000, 0.839100, True),
    ("unit vs unit, drift            ", 1.001000, 1.000000, True),
    ("two world families, 4% apart   ", 0.155000, 0.149184, False),
]


def main():
    print("%-32s %10s %10s  %-10s %-10s %s" %
          ("scenario", "proj00", "locked", "old", "new", "verdict"))
    print("-" * 92)
    bad = 0
    for label, p, lk, expect in CASES:
        o = old_rule(p, lk)
        n = new_rule(p, lk)
        ok = n == expect
        if not ok:
            bad += 1
        mark = "PASS" if ok else "FAIL"
        if o != expect:
            mark += "  (old was wrong)"
        print("%-32s %10.6f %10.6f  %-10s %-10s %s" %
              (label, p, lk, "same" if o else "DIFF", "same" if n else "DIFF", mark))
    print("-" * 92)
    print()
    if bad:
        print("RESULT: %d FAILED" % bad)
        return 1
    old_wrong = sum(1 for _, p, lk, e in CASES if old_rule(p, lk) != e)
    print("RESULT: OK - new rule matches every expectation")
    print("        the old rule got %d of %d rows wrong (including the one that "
          "caused the freeze)" % (old_wrong, len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
