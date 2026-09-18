# -*- coding: utf-8 -*-
"""v1.00d - add the family-lock counters to the heartbeat line.

Without these the next log cannot show whether the v1.00 fingerprint lock is
doing anything. Adds two numbers to the existing `lock(...)` group and appends
the locked family's ProjUnj[0][0] after `lastMagVP`.

Format string and argument list must stay in lockstep -- this project already
lost a run to a missing argument (C7595).
"""
import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SL = os.path.join(ROOT, "src", "Streamline.cpp")
APPLY = "--apply" in sys.argv

OLD_FMT = '''					"lock(pub/hold/re/still)={}/{}/{}/{}",'''
NEW_FMT = '''					"lock(pub/hold/re/still/fam)={}/{}/{}/{}/{} proj00={:.6g} famRej={}",'''

OLD_ARG = '''					Get().snapLockPublish, Get().snapLockHold,
					Get().snapLockRelock, Get().snapLockStill);'''
NEW_ARG = '''					Get().snapLockPublish, Get().snapLockHold,
					Get().snapLockRelock, Get().snapLockStill,
					Get().snapLockProjValid ? Get().snapLockProj00 : 0.0f,
					Get().snapLockFamilyRej);'''


def main():
    with io.open(SL, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if "lock(pub/hold/re/still/fam)" in src:
        print("REFUSED: marker already present - patch has run")
        return 1

    for label, old in (("fmt", OLD_FMT), ("arg", OLD_ARG)):
        n = src.count(old)
        if n != 1:
            print("REFUSED: anchor '%s' occurs %d times (must be exactly 1)" % (label, n))
            return 1

    out = src.replace(OLD_FMT, NEW_FMT).replace(OLD_ARG, NEW_ARG)

    # format-spec / argument balance: every {} in the new fragment needs a value.
    import re
    seg_start = out.index("lock(pub/hold/re/still/fam)")
    seg_end = out.index(");", seg_start)
    fmt_seg = out[out.rindex('"', 0, seg_start) + 1:seg_end]
    placeholders = len(re.findall(r"\{[^}]*\}", fmt_seg))
    checks = [
        ("new fmt present", "lock(pub/hold/re/still/fam)" in out),
        ("proj00 emitted", "proj00={:.6g}" in out),
        ("famRej emitted", "famRej={}" in out),
        ("args: proj00 guard", "snapLockProjValid ? Get().snapLockProj00 : 0.0f" in out),
        ("args: famRej", "Get().snapLockFamilyRej)" in out),
        ("brace balance unchanged", out.count("{") - out.count("}") == src.count("{") - src.count("}")),
        ("paren balance unchanged", out.count("(") - out.count(")") == src.count("(") - src.count(")")),
    ]
    ok = True
    for label, cond in checks:
        print("  %-30s %s" % (label, "PASS" if cond else "FAIL"))
        ok = ok and cond
    if not ok:
        print("REFUSED: post-conditions failed, nothing written")
        return 1

    if not APPLY:
        print("\nDRY RUN - re-run with --apply")
        return 0
    with io.open(SL, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("\nAPPLIED: heartbeat carries family lock counters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
