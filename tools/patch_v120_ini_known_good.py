#!/usr/bin/env python3
"""v1.20-INI: reproduce the LEDGER's own documented known-good configuration.

Why: the 23:22 run PROVED that NR is not the cause (NRAllowWithFrameGen=0 took
effect -- the log says "DLSSNR suppressed: frame generation is active" -- and the
freeze persisted). The ledger (MFG_MASTER_NOTES / MEMORY.md) has said all along:

    "一秒回到可玩：Provider=0 + MFGMaxFramesOverride=0（只改 INI，不改代码）"

That combination has never actually been tried. This script applies exactly it,
plus restores NRAllowWithFrameGen=1 so the result is the configuration the user
already had working before the MFG branch existed (FSR3 2x + DLSS5).

Three edits, CRLF preserved, every anchor asserted to occur exactly once.
Dry-run by default; pass --apply to write.
"""

import sys
import hashlib
from pathlib import Path

INI = Path(r"E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini")
MARKER = b"v1.20-INI known-good control"

CRLF = b"\r\n"

EDITS = [
    (
        "Provider 1 -> 0 (FSR3 instead of DLSS-G)",
        CRLF + b"Provider=1" + CRLF,
        CRLF + b"Provider=0" + CRLF,
    ),
    (
        "MFGMaxFramesOverride 3 -> 0 (stop raising the ceiling; 0 = follow hw)",
        CRLF + b"MFGMaxFramesOverride=3" + CRLF,
        CRLF + b"MFGMaxFramesOverride=0" + CRLF,
    ),
    (
        "NRAllowWithFrameGen 0 -> 1 (restore the user's known-good DLSS5 combo)",
        CRLF + b"NRAllowWithFrameGen=0" + CRLF,
        CRLF + b"NRAllowWithFrameGen=1" + CRLF,
    ),
]

# Post-conditions on the RESULT text (not the input).
POST_PRESENT = [
    CRLF + b"Provider=0" + CRLF,
    CRLF + b"MFGMaxFramesOverride=0" + CRLF,
    CRLF + b"NRAllowWithFrameGen=1" + CRLF,
]
POST_ABSENT = [
    CRLF + b"Provider=1" + CRLF,
    CRLF + b"MFGMaxFramesOverride=3" + CRLF,
    CRLF + b"NRAllowWithFrameGen=0" + CRLF,
]


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def main() -> int:
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    if not INI.exists():
        print("REFUSED: %s does not exist" % INI)
        return 1

    src = INI.read_bytes()
    print("file   : %s" % INI)
    print("size   : %d B" % len(src))
    print("md5    : %s" % md5(src))
    print("CRLF   : %d" % src.count(CRLF))
    print("bareLF : %d" % (src.count(b"\n") - src.count(CRLF)))
    print()

    if MARKER in src and not revert:
        print("REFUSED: already applied (marker present)")
        return 1

    if revert:
        # undo by swapping the applied values back
        cur = src
        for label, old, new in EDITS:
            if cur.count(new) != 1:
                print("REFUSED: revert anchor %r count=%d" % (new, cur.count(new)))
                return 1
            cur = cur.replace(new, old)
        cur = cur.replace(CRLF + b"; " + MARKER + CRLF, b"")
        print("reverted %d edits" % len(EDITS))
        if apply:
            INI.write_bytes(cur)
            print("written")
        else:
            print("(dry run)")
        return 0

    for label, old, new in EDITS:
        n = src.count(old)
        flag = "OK " if n == 1 else "BAD"
        print("[%s] count(old)=%d  %s" % (flag, n, label))
        if n != 1:
            print("REFUSED, nothing written")
            return 1

    out = src
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)

    # append the marker as a comment line so re-runs are refused
    out = out + CRLF + b"; " + MARKER + CRLF

    print()
    for pat in POST_PRESENT:
        n = out.count(pat)
        print("[%s] present  %r x%d" % ("OK " if n == 1 else "BAD", pat.strip(), n))
        if n != 1:
            print("REFUSED, nothing written")
            return 1
    for pat in POST_ABSENT:
        n = out.count(pat)
        print("[%s] absent   %r x%d" % ("OK " if n == 0 else "BAD", pat.strip(), n))
        if n != 0:
            print("REFUSED, nothing written")
            return 1

    print()
    print("size   : %d B  (was %d, delta %+d)" % (len(out), len(src), len(out) - len(src)))
    print("CRLF   : %d" % out.count(CRLF))
    print("bareLF : %d" % (out.count(b"\n") - out.count(CRLF)))
    print("md5    : %s" % md5(out))

    if not apply:
        print()
        print("DRY RUN - nothing written. Pass --apply to write.")
        return 0

    INI.write_bytes(out)
    back = INI.read_bytes()
    print()
    if back == out:
        print("VERIFIED: read back identical, %d B, md5 %s" % (len(back), md5(back)))
    else:
        print("ERROR: read back differs!")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
