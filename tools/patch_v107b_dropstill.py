#!/usr/bin/env python3
"""v1.07b: drop the still-threshold re-adopt from FrameGen.cpp.

WHY
---
The first v1.07 draft added two release paths. The offline regression
(tools/regress_v107_lockrelease.py) then showed they are not equivalent:

    C1  escape deleted only        -> proj00=0.149184  world-refusals=0
    C2  escape deleted only        -> proj00=0.8391    world-refusals=744  (stuck)
        + edge release             -> proj00=0.149184  world-refusals=372  (recovered)
        still-threshold only       -> proj00=1         world-refusals=744  (WRONG family)

The still-threshold path adopts whichever arrival happens to be the 90th
non-continuation. With two foreign families arriving that is the unit
projection half the time - i.e. it swaps one wrong family for another. And it
re-opens exactly the door v1.00 closed on purpose:

    FrameGen.cpp:903-908   "v0.94 re-acquired unconditionally after kCamStillTol
                            non-continuing arrivals, so a foreign camera that
                            arrived monotonically for 90 frames was adopted and
                            then 'continued' itself forever. That is the freeze.
                            Only an arrival from the SAME family may take over."

So this patch restores that invariant and keeps only:
  edit 1  the v1.03 magnitude-class escape stays DELETED
  edit 2  the reset-edge release stays (deterministic: it fires at a menu
          transition and hands the lock to the first arrival after it, which is
          the world camera whenever the menu has closed)
and removes:
  edit 3  the still-threshold re-adopt

The `++snapLockStill` instrumentation added next to the family rejection stays -
it is what makes the log's still=N/M field report the truth instead of a
constant 0.

Run:
    python tools/patch_v107b_dropstill.py            # dry run, writes nothing
    python tools/patch_v107b_dropstill.py --apply    # write
"""

import io
import sys

TARGET = "src/FrameGen.cpp"
MARKER = "v1.07b: do NOT re-acquire here"

EOL_OVERRIDE = None   # detect from the file


def eol_of(src: bytes) -> bytes:
    crlf = src.count(b"\r\n")
    lf = src.count(b"\n") - crlf
    return b"\r\n" if crlf >= lf else b"\n"


def norm(chunk: bytes, eol: bytes) -> bytes:
    """Rewrite chunk's newlines to `eol` (accepts str or list)."""
    if isinstance(chunk, list):
        chunk = b"".join(x + eol for x in chunk)
    if isinstance(chunk, str):
        chunk = chunk.encode("utf-8")
    return chunk.replace(b"\r\n", b"\n").replace(b"\n", eol)


OLD = [
    b"\t\t\t\t\tif (snapLockStill < kCamStillTol) {",
    b"\t\t\t\t\t\tif (d2 > kCamJumpTol2) ++snapRejectJump;",
    b"\t\t\t\t\t\treturn false;",
    b"\t\t\t\t\t}",
    b"\t\t\t\t\t// v1.07: the locked family has failed to continue kCamStillTol",
    b"\t\t\t\t\t// times in a row, which is the same evidence v0.94 used to",
    b"\t\t\t\t\t// re-acquire. v1.00 refused this because a foreign camera arriving",
    b"\t\t\t\t\t// monotonically would adopt itself forever - but with the v1.03",
    b"\t\t\t\t\t// escape removed above, reaching here requires 90 consecutive",
    b"\t\t\t\t\t// non-continuations, which a live single-source stream reset every",
    b"\t\t\t\t\t// frame never produces. Secondary trigger only: in the stuck case",
    b"\t\t\t\t\t// the wrong family keeps continuing itself and resets the counter,",
    b"\t\t\t\t\t// so the reset edge above is the load-bearing part. Counting them",
    b"\t\t\t\t\t// is still correct, and the still={}/{} field now reports the truth.",
    b'\t\t\t\t\tSKSE::log::info("[CAM] #{} lock RELEASED after {}/{} non-continuations - "',
    b'\t\t\t\t\t\t"locked proj00={:.6g} is dead, adopting proj00={:.6g} "',
    b'\t\t\t\t\t\t"pos=({:.1f},{:.1f},{:.1f}) dist={:.1f}",',
    b"\t\t\t\t\t\tsnapArrivals, snapLockStill, kCamStillTol,",
    b"\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f,",
    b"\t\t\t\t\t\tproj00, px, py, pz, std::sqrt(d2));",
    b"\t\t\t\t\t++snapLockReleased;",
    b"\t\t\t\t\tsnapLockHave = false;",
    b"\t\t\t\t\tsnapLockProjValid = false;",
    b"\t\t\t\t\tsnapHaveLast = false;",
    b"\t\t\t\t\tsnapLockStill = 0;",
    b"\t\t\t\t\t// falls through into the re-adopt below: this arrival establishes",
    b"\t\t\t\t\t// the new lock. The \"same-family step break\" line below is reused",
    b"\t\t\t\t\t// for it and prints the real proj00, so the log stays honest.",
]

NEW = [
    b"\t\t\t\t\t// v1.07b: do NOT re-acquire here.",
    b"\t\t\t\t\t//",
    b"\t\t\t\t\t// The first v1.07 draft let this branch re-adopt after",
    b"\t\t\t\t\t// kCamStillTol consecutive family rejections. The offline",
    b"\t\t\t\t\t// regression showed that is not a repair: the branch adopts",
    b"\t\t\t\t\t// whichever arrival happens to BE the 90th non-continuation,",
    b"\t\t\t\t\t// and with two foreign families arriving it lands on the unit",
    b"\t\t\t\t\t// orthographic projection half the time - proj00=1, which is",
    b"\t\t\t\t\t// just a different wrong family, and one whose clipToPrev is",
    b"\t\t\t\t\t// an identity, i.e. exactly the freeze.",
    b"\t\t\t\t\t//",
    b"\t\t\t\t\t// It also re-opened the door v1.00 closed two lines up the",
    b"\t\t\t\t\t// block: v0.94's unconditional kCamStillTol re-acquire IS the",
    b"\t\t\t\t\t// documented freeze, and \"only a same-family arrival may take",
    b"\t\t\t\t\t// over\" is the invariant that fixed it. So the refusal is",
    b"\t\t\t\t\t// unconditional again.",
    b"\t\t\t\t\t//",
    b"\t\t\t\t\t// The reset-edge release above remains the ONLY release path.",
    b"\t\t\t\t\t// It is deterministic rather than order-dependent: it fires at",
    b"\t\t\t\t\t// a menu transition and hands the lock to the first arrival",
    b"\t\t\t\t\t// after it, which is the world camera whenever the menu has",
    b"\t\t\t\t\t// closed. The counter below is untouched, so still=N/M keeps",
    b"\t\t\t\t\t// reporting how long the locked family has been failing.",
    b"\t\t\t\t\tif (d2 > kCamJumpTol2) ++snapRejectJump;",
    b"\t\t\t\t\treturn false;",
]


def main():
    apply = "--apply" in sys.argv
    raw = io.open(TARGET, "rb").read()
    eol = EOL_OVERRIDE or eol_of(raw)
    src = raw.decode("utf-8-sig")
    text = norm(src, eol).decode("utf-8")

    old_s = norm(OLD, eol).decode("utf-8")
    new_s = norm(NEW, eol).decode("utf-8")

    n = text.count(old_s)
    eol_name = "CRLF" if eol == b"\r\n" else "LF"
    print(f"file          : {TARGET}")
    print(f"eol           : {eol_name}")
    print(f"anchor count  : {n}   (must be exactly 1)")
    print(f"marker present: {MARKER in text}   (must be False or the patch ran)")

    if n != 1:
        print("REFUSED, nothing written (anchor not unique / not found)")
        return 2
    if MARKER in text:
        print("REFUSED, nothing written (already applied - marker found)")
        return 2

    res = text.replace(old_s, new_s, 1)

    # post-condition on the RESULT text, not the input
    eol_s = "\r\n" if eol == b"\r\n" else "\n"
    refusal = (eol_s.join([
        "\t\t\t\t\tif (d2 > kCamJumpTol2) ++snapRejectJump;",
        "\t\t\t\t\treturn false;",
    ]) + eol_s)
    checks = [
        ("the old release log line is gone",
         "lock RELEASED after" not in res),
        ("the kCamStillTol early-return is gone",
         "if (snapLockStill < kCamStillTol)" not in res),
        ("the marker is present",
         MARKER in res),
        ("the unconditional refusal is present",
         refusal in res),
        ("the v1.00 invariant comment is still there",
         "a different projection family may NEVER re-acquire" in res),
        ("the escape deletion comment is still there",
         "the v1.03 magnitude-class escape is GONE" in res),
        ("the edge-release consumer is still there",
         "if (snapLockReleasePending) {" in res),
        ("the escape itself stays deleted",
         "const bool unitProj" not in res and "const bool lockUnit" not in res),
    ]
    bad = [label for label, ok in checks if not ok]
    for label, ok in checks:
        print(f"  [{'ok ' if ok else 'BAD'}] {label}")
    if bad:
        print("REFUSED, nothing written (post-condition failed)")
        return 3

    # line-count sanity: the block shrinks, it must not collapse
    n_old_lines = old_s.count(eol_s)
    n_new_lines = new_s.count(eol_s)
    print(f"line delta    : {n_new_lines - n_old_lines:+d} "
          f"({n_old_lines} -> {n_new_lines})")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    data = res.encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        data = b"\xef\xbb\xbf" + data
    io.open(TARGET, "wb").write(data)

    # read back from disc and re-verify, never trust the in-memory result
    back = io.open(TARGET, "rb").read().decode("utf-8-sig")
    assert MARKER in back, "read-back: marker missing"
    assert "lock RELEASED after" not in back, "read-back: old log line still present"
    assert "if (snapLockStill < kCamStillTol)" not in back, "read-back: old guard still present"
    print("\nAPPLIED and verified by read-back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
