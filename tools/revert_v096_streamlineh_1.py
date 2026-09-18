"""Revert Streamline.h from v0.96 back to v0.95.

Why this exists: the v0.96 backup set covered four files but NOT Streamline.h.
That omission is a process failure of its own -- it must not be repeated.  This
script reconstructs v0.95 by removing exactly the two v0.96 insertions, leaving
every other byte (including the pre-existing quote characters and the file's
CRLF endings) untouched.

Safety: dry run unless --apply; each block must occur exactly once; read-back
proves both v0.96 markers are gone.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HDR = ROOT / "src" / "Streamline.h"

CRLF = b"\r\n"

# The two blocks v0.96 inserted. Each is uniquely identifiable by its comment.
BLOCK_DIAG = (
    b"\t\t\t// v0.96: which menu name the guard matched on the last sample, and\r\n"
    b"\t\t\t// how many frames that name has been responsible for. Without this\r\n"
    b"\t\t\t// the 1336-frame lock at 16:24 could not be attributed to any menu.\r\n"
    b"\t\t\tconst char* menuHitName = nullptr;\r\n"
    b"\t\t\tstd::uint64_t menuHitFrames = 0;\r\n"
)
BLOCK_DECL = (
    b"\t\t// v0.96: which menu name the guard matched, and how often. The 16:24\r\n"
    b"\t\t// run locked the guard on for 1336 frames and the log could not say\r\n"
    b"\t\t// which of the six candidate names was responsible -- the MENU PROBE\r\n"
    b"\t\t// only tests three of them and all three read false. Recording the\r\n"
    b"\t\t// hit removes the guesswork: \"Fader Menu\" is the screen fade the\r\n"
    b"\t\t// engine uses while the world loads, and it is no longer counted.\r\n"
    b"\t\tconst char* menuHitName() const;\r\n"
    b"\t\tstd::uint64_t menuHitCount() const;\r\n"
)

REMOVALS = [
    ("Streamline.h: drop Diag::menuHitName / menuHitFrames", BLOCK_DIAG),
    ("Streamline.h: drop the two accessor declarations", BLOCK_DECL),
]


def main() -> int:
    apply = "--apply" in sys.argv

    data = HDR.read_bytes()
    print(f"before: bytes={len(data)} CRLF={data.count(CRLF)} LF={data.count(b'\\n')}")

    # Idempotency: if neither block is present the file is already reverted.
    present = [(label, blk) for label, blk in REMOVALS if data.count(blk) > 0]
    if not present:
        print("[SKIP] neither v0.96 block present - already at v0.95")
        return 0

    new = data
    for label, blk in REMOVALS:
        hits = new.count(blk)
        if hits != 1:
            print(f"[FAIL] {label}: count = {hits}, expected exactly 1")
            print("REFUSED, nothing written")
            return 2
        new = new.replace(blk, b"", 1)
        print(f"[OK]   {label}")

    if not apply:
        print(f"\nafter (dry): bytes={len(new)} (delta {len(new)-len(data):+d})")
        print("DRY RUN -- pass --apply to write.")
        return 0

    HDR.write_bytes(new)
    print(f"WROTE Streamline.h: bytes={len(new)} CRLF={new.count(CRLF)} LF={new.count(b'\\n')}")

    print("\n--- read-back ---")
    back = HDR.read_bytes()
    checks = [
        ("Diag block gone", back.count(BLOCK_DIAG) == 0),
        ("decl block gone", back.count(BLOCK_DECL) == 0),
        ("no menuHitName left", back.count(b"menuHitName") == 0),
        ("no menuHitCount left", back.count(b"menuHitCount") == 0),
        ("no menuHitFrames left", back.count(b"menuHitFrames") == 0),
    ]
    ok = True
    for name, cond in checks:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond
    print("RESULT:", "OK" if ok else "NEEDS FIX")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
