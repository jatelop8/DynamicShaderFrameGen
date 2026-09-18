# -*- coding: utf-8 -*-
"""v1.00e - fix the C7595 in the heartbeat: one placeholder was left unfilled.

v1.00d changed the format tail from

    lock(pub/hold/re/still)={}/{}/{}/{}          (4 placeholders)
to
    lock(pub/hold/re/still/fam)={}/{}/{}/{}/{} proj00={:.6g} famRej={}
                                                 (4 + 1 + 1 + 1 = 7 placeholders)

but added only TWO arguments (proj00, famRej). The `fam` group needs its own
value: the locked family's identity in a readable form. Use the ratio of the
current frame's projection to the locked one is misleading here, so emit the
locked family's ProjUnj[0][0] TWICE is silly -- instead emit the fingerprint
state as a 0/1 flag plus keep proj00/famRej as the two values.

Simplest correct fix: drop the extra `{}` from the group label, i.e. revert the
group to 4 slots and keep the two new named fields. That is 6 placeholders and
6 arguments, which is what the call site provides.

Run with --apply to write; without it, dry-run only.
"""
import io
import re
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SL = os.path.join(ROOT, "src", "Streamline.cpp")
APPLY = "--apply" in sys.argv

OLD = '"lock(pub/hold/re/still/fam)={}/{}/{}/{}/{} proj00={:.6g} famRej={}",'
NEW = '"lock(pub/hold/re/still)={}/{}/{}/{} proj00={:.6g} famRej={}",'


def main():
    with io.open(SL, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if 'lock(pub/hold/re/still)={}/{}/{}/{} proj00={:.6g}' in src:
        print("REFUSED: already fixed")
        return 1
    n = src.count(OLD)
    if n != 1:
        print("REFUSED: anchor occurs %d times (must be exactly 1)" % n)
        return 1

    out = src.replace(OLD, NEW)

    # Count placeholders in the heartbeat line and arguments after it, and
    # compare. The heartbeat is one SKSE::log::info(...) call. Every string
    # literal up to the first argument (`frameSerial`) belongs to the format.
    hb_start = out.index("[XRAY] serial={}")
    hb_end = out.index(");", out.index("snapLockFamilyRej", hb_start))
    call = out[hb_start:hb_end]
    k = call.index("frameSerial")
    placeholders = len(re.findall(r"\{[^{}]*\}", call[:k]))
    args_text = call[k:]
    depth = 0
    commas = 1
    for ch in args_text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            commas += 1

    print("  format placeholders in heartbeat : %d" % placeholders)
    print("  top-level arguments              : %d" % commas)

    checks = [
        ("new fmt present", 'proj00={:.6g} famRej={}' in out),
        ("4-slot group", 'lock(pub/hold/re/still)={}/{}/{}/{}' in out),
        ("two new args present",
         "Get().snapLockProjValid ? Get().snapLockProj00 : 0.0f" in out
         and "Get().snapLockFamilyRej)" in out),
        ("brace balance unchanged", out.count("{") - out.count("}") == src.count("{") - src.count("}")),
    ]
    ok = all(c for _, c in checks)
    for label, cond in checks:
        print("  %-30s %s" % (label, "PASS" if cond else "FAIL"))

    if placeholders != commas:
        print("  MISMATCH: %d placeholders vs %d arguments" % (placeholders, commas))
        ok = False

    if not ok:
        print("REFUSED: post-conditions failed, nothing written")
        return 1

    if not APPLY:
        print("\nDRY RUN - re-run with --apply")
        return 0
    with io.open(SL, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("\nAPPLIED: heartbeat placeholder/argument counts now agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
