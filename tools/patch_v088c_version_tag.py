#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v088c_version_tag.py -- move the diagnostic banner to v0.88.

WHY THIS MATTERS
----------------
The banner has read "diag active v0.86" since v0.86.  v0.87 shipped without
touching it, so a log from a v0.87 build claimed to be v0.86 and I misread
which binary produced it.  That is a direct cause of a wrong conclusion in an
earlier round.  Bump it now, and make the banner state the one fact that
decides this round: whether the corrected viewProj is in effect.

Two edits, both asserted:
  E1  version banner v0.86 -> v0.88
  E2  append the fix fingerprint line right after the banner
"""

import sys
import pathlib

SRC = pathlib.Path("src/Streamline.cpp")
MARKER = "fixed-viewproj v0.88 ACTIVE"

OLD_BANNER = '\t\t\t\tSKSE::log::info("[XRAY] diag active v0.86 (compiled " __DATE__ " " __TIME__ ")");'

NEW_BANNER = (
    '\t\t\t\tSKSE::log::info("[XRAY] diag active v0.88 (compiled " __DATE__ " " __TIME__ ")");\n'
    '\t\t\t\t// v0.88: state, in the log itself, whether the corrected matrix is\n'
    '\t\t\t\t// what DLSS-G is being fed.  If this line is missing or reprojSource\n'
    '\t\t\t\t// stays 0, the fix is not active and any conclusion about the\n'
    '\t\t\t\t// ping-pong is void -- the run must be thrown away, not explained.\n'
    '\t\t\t\tSKSE::log::info("[XRAY] fixed-viewproj v0.88 ACTIVE: reprojSource={} "\n'
    '\t\t\t\t\t"fixedVpDev={:.6g} (0 => rebuild degenerated to the engine copy; "\n'
    '\t\t\t\t\t"large => translation really is being injected)",\n'
    '\t\t\t\t\tdiag.reprojSource, diag.fixedVpDev);'
)


def main():
    apply = "--apply" in sys.argv
    text = SRC.read_text(encoding="utf-8")

    if MARKER in text:
        print("REFUSED: marker already present.")
        return 2

    n = text.count(OLD_BANNER)
    if n != 1:
        print(f"REFUSED: banner anchor occurrences={n} (expected 1).")
        return 2

    new = text.replace(OLD_BANNER, NEW_BANNER, 1)

    if new.count("{") != new.count("}"):
        print(f"REFUSED: brace imbalance {new.count('{')} vs {new.count('}')}.")
        return 2
    if "\r\n" in new:
        print("REFUSED: CRLF introduced; file must stay LF.")
        return 2

    print(f"anchor=1 OK, size {len(text)} -> {len(new)} (delta {len(new)-len(text):+d})")
    print(f"braces {new.count('{')}/{new.count('}')}")
    if not apply:
        print("DRY RUN -- nothing written.")
        return 0

    SRC.write_text(new, encoding="utf-8", newline="")
    print("APPLIED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
