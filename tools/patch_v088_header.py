#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v088_header.py -- add the `fixedVpDev` diagnostic field used by the
v0.88 translation fix in Streamline.cpp.

LINE ENDING (verified with a byte count, not assumed):
    src/Streamline.h    CRLF=326  bare_LF=0    -> this file is CRLF
    src/FrameGen.h      CRLF=304  bare_LF=0    -> CRLF
    src/Streamline.cpp  CRLF=0    bare_LF=1672 -> LF
    src/FrameGen.cpp    CRLF=0    bare_LF=1180 -> LF

The first draft of this script asserted "refuse if CRLF appears", which would
have rejected its own correct output and blamed the anchor. The guard is
therefore inverted: this header must STAY CRLF, so refuse any bare LF.

Guards: dry-run by default, unique anchor, marker guard, line-ending check.
"""

import sys
import pathlib

SRC = pathlib.Path("src/Streamline.h")
MARKER = "fixedVpDev"

# NOTE: explicit \r\n -- this file is CRLF, the anchor must match byte for byte.
OLD = ("\t\t\tfloat derivedMatchErr = 0.0f;\r\n"
       "\t\t\tfloat clipDevMax = 0.0f;\r\n")

NEW = ("\t\t\tfloat derivedMatchErr = 0.0f;\r\n"
       "\t\t\tfloat clipDevMax = 0.0f;\r\n"
       "\t\t\t// v0.88: max |fixedViewProj - engineViewProj|. Non-zero proves the\r\n"
       "\t\t\t// rebuilt matrix really carries the translation the engine omits;\r\n"
       "\t\t\t// -1 means the rebuild was unavailable this frame.\r\n"
       "\t\t\tfloat fixedVpDev = -1.0f;\r\n")


def main():
    apply = "--apply" in sys.argv
    raw = SRC.read_bytes()

    # byte-level facts first
    crlf_before = raw.count(b"\r\n")
    bare_before = raw.count(b"\n") - crlf_before
    print(f"before: CRLF={crlf_before} bare_LF={bare_before} size={len(raw)}")
    if bare_before != 0:
        print("REFUSED: file is not pure CRLF before the edit; investigate first.")
        return 2

    text = raw.decode("utf-8")

    if MARKER in text:
        print("REFUSED: marker already present.")
        return 2

    n = text.count(OLD)
    if n != 1:
        print(f"REFUSED: anchor occurrences={n} (expected 1).")
        return 2

    new = text.replace(OLD, NEW, 1)

    if new.count("{") != new.count("}"):
        print("REFUSED: brace imbalance.")
        return 2

    # this header must remain pure CRLF: no bare LF may be introduced
    nb = new.encode("utf-8")
    crlf_after = nb.count(b"\r\n")
    bare_after = nb.count(b"\n") - crlf_after
    print(f"after : CRLF={crlf_after} bare_LF={bare_after} size={len(nb)}")
    if bare_after != 0:
        print("REFUSED: bare LF introduced; this header must stay CRLF.")
        return 2
    # 4 new lines: 3 comment lines + the `float fixedVpDev = -1.0f;` declaration.
    if crlf_after != crlf_before + 4:
        print(f"REFUSED: expected +4 CRLF lines, got {crlf_after - crlf_before}.")
        return 2

    print(f"anchor OK (1), delta {len(nb)-len(raw):+d} bytes")
    if not apply:
        print("DRY RUN -- nothing written. Re-run with --apply.")
        return 0

    SRC.write_bytes(nb)
    print("APPLIED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
