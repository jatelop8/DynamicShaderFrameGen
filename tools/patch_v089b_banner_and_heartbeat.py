#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v089b_banner_and_heartbeat.py -- fix the two logging defects that made
v0.88 unreadable.

DEFECT 1 -- the "activation fingerprint" is printed at the wrong moment
-----------------------------------------------------------------------
v0.88 added:
    [XRAY] fixed-viewproj v0.88 ACTIVE: reprojSource={} fixedVpDev={:.6g}
but it sits inside the MENU EDGE block, which runs ONCE, when the game boots
into the main menu. At that instant there is no world camera yet, so it always
prints

    reprojSource=0  fixedVpDev=-1

That reads as "the fix is not active", and it is what a reader would conclude
from the 15:02 log. It is an artifact of WHERE the line is, not of whether the
fix works -- the heartbeat in the same run showed `reproj src=fixed` and
`curMag=505`. A diagnostic that cannot tell the truth is worse than none.

Fix: keep the boot banner for the version string only, and move the live
state onto the heartbeat, which is rendered every 30 frames during play.

DEFECT 2 -- the version tag was v0.88 while v0.89 is shipping
------------------------------------------------------------
Same class of mistake as v0.87 claiming v0.86. Bump it.

Guards: dry-run default, unique anchors, marker, brace balance, LF only.
"""

import sys
import pathlib

SRC = pathlib.Path("src/Streamline.cpp")
MARKER = "diag active v0.89"

OLD = ('\t\t\t\tSKSE::log::info("[XRAY] diag active v0.88 (compiled " __DATE__ " " __TIME__ ")");\n'
       '\t\t\t\t// v0.88: state, in the log itself, whether the corrected matrix is\n'
       '\t\t\t\t// what DLSS-G is being fed.  If this line is missing or reprojSource\n'
       '\t\t\t\t// stays 0, the fix is not active and any conclusion about the\n'
       '\t\t\t\t// ping-pong is void -- the run must be thrown away, not explained.\n'
       '\t\t\t\tSKSE::log::info("[XRAY] fixed-viewproj v0.88 ACTIVE: reprojSource={} "\n'
       '\t\t\t\t\t"fixedVpDev={:.6g} (0 => rebuild degenerated to the engine copy; "\n'
       '\t\t\t\t\t"large => translation really is being injected)",\n'
       '\t\t\t\t\tdiag.reprojSource, diag.fixedVpDev);\n')

NEW = ('\t\t\t\tSKSE::log::info("[XRAY] diag active v0.89 (compiled " __DATE__ " " __TIME__ ")");\n'
       '\t\t\t\t// v0.89: the live fix state is reported on the HEARTBEAT, not here.\n'
       '\t\t\t\t// v0.88 printed it at this spot, which runs once at boot before any\n'
       '\t\t\t\t// world camera exists -- it therefore always read reprojSource=0\n'
       '\t\t\t\t// fixedVpDev=-1 and looked like "the fix is dead". It was not; the\n'
       '\t\t\t\t// heartbeat showed src=fixed. A diagnostic printed at the wrong\n'
       '\t\t\t\t// moment is a diagnostic that lies.\n')

# ---- the heartbeat format string: append the fix state ----------------------
OLD_FMT = '"det(min/max)={:.3f}/{:.3f} "'
NEW_FMT = ('"det(min/max)={:.3f}/{:.3f} " \n'
           '\t\t\t\t\t"fix(src={} dev={:.6g}) "')

OLD_ARGS = ('\t\t\t\t\t(diag.detMin > diag.detMax ? 0.0f : diag.detMin),\n'
            '\t\t\t\t\t(diag.detMin > diag.detMax ? 0.0f : diag.detMax),\n')
NEW_ARGS = ('\t\t\t\t\t(diag.detMin > diag.detMax ? 0.0f : diag.detMin),\n'
            '\t\t\t\t\t(diag.detMin > diag.detMax ? 0.0f : diag.detMax),\n'
            '\t\t\t\t\tdiag.reprojSource, diag.fixedVpDev,\n')


def main():
    apply = "--apply" in sys.argv
    text = SRC.read_text(encoding="utf-8")

    if MARKER in text:
        print("REFUSED: marker already present.")
        return 2

    EDITS = [
        ("E1 banner -> v0.89, drop the boot-time fingerprint", OLD, NEW),
        ("E2 heartbeat format gains fix(src= dev=)", OLD_FMT, NEW_FMT),
        ("E3 heartbeat args gain reprojSource/fixedVpDev", OLD_ARGS, NEW_ARGS),
    ]

    new = text
    for label, old, rep in EDITS:
        cnt = new.count(old)
        if cnt != 1:
            print(f"REFUSED: [{label}] anchor occurrences={cnt} (expected 1). Nothing written.")
            return 2
        new = new.replace(old, rep, 1)
        print(f"  [{label}] anchor=1 OK")

    for need in ("diag.reprojSource", "diag.fixedVpDev"):
        if new.count(need) < 2:
            print(f"REFUSED: `{need}` is not consumed by both banner and heartbeat.")
            return 2

    if new.count("{") != new.count("}"):
        print(f"REFUSED: brace imbalance {new.count('{')} vs {new.count('}')}.")
        return 2
    if "\r\n" in new:
        print("REFUSED: CRLF introduced; Streamline.cpp must stay LF.")
        return 2

    print(f"size {len(text)} -> {len(new)} (delta {len(new)-len(text):+d})")
    print(f"braces {new.count('{')}/{new.count('}')}  lines {text.count(chr(10))} -> {new.count(chr(10))}")
    if not apply:
        print("DRY RUN -- nothing written.")
        return 0

    SRC.write_text(new, encoding="utf-8", newline="")
    print("APPLIED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
