#!/usr/bin/env python3
"""Exact end-of-line census for a file.

Why this exists: `grep -c $'\\r$'` and `grep -c '[^\\r]$'` can both return
non-zero on a pure-CRLF file (grep's `$` anchor and the shell's handling of
the literal CR disagree), which makes the two counts look like they overlap.
This counts bytes directly, so it cannot lie about what is on disk.

Usage:
    python tools/eol_census.py <file> [<file> ...]
"""
import sys
from pathlib import Path


def census(data: bytes) -> dict:
    crlf = data.count(b"\r\n")
    # every \n that is not part of a \r\n
    bare_lf = data.count(b"\n") - crlf
    # \r that is not followed by \n
    lone_cr = data.count(b"\r") - crlf
    return {
        "bytes": len(data),
        "crlf": crlf,
        "bare_lf": bare_lf,
        "lone_cr": lone_cr,
        "has_bom": data.startswith(b"\xef\xbb\xbf"),
    }


def verdict(c: dict) -> str:
    if c["crlf"] and not c["bare_lf"] and not c["lone_cr"]:
        return "PURE CRLF"
    if c["bare_lf"] and not c["crlf"] and not c["lone_cr"]:
        return "PURE LF"
    if not c["crlf"] and not c["bare_lf"] and not c["lone_cr"]:
        return "NO NEWLINES"
    return "MIXED"


def main() -> int:
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    for p in paths:
        path = Path(p)
        if not path.is_file():
            print(f"MISSING  {p}")
            continue
        c = census(path.read_bytes())
        print(
            f"{c['bytes']:>9} B  crlf={c['crlf']:<6} bare_lf={c['bare_lf']:<6} "
            f"lone_cr={c['lone_cr']:<4} bom={int(c['has_bom'])}  {verdict(c):<10} {p}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
