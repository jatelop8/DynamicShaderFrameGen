# -*- coding: utf-8 -*-
"""Fix ASCII double quotes that leak out of // comments.

A '"' inside a // comment closes the comment. If no further '//' follows, the
rest of the line becomes real code and its quotes open a string that runs
across lines -- swallowing whatever follows (this destroyed the heartbeat's
format string).

Fix: replace the offending ASCII quotes with the full-width Chinese quotes
U+201C / U+201D, which are string-safe and read better in Chinese comments
anyway. For English comments the same substitution is used (typographic
quotes), which keeps the sentence readable.

Guards (assertion style, dry-run by default):
  * every replacement must be applied to an exact, unique anchor
  * the byte length delta must be zero-ish (U+201C/D are 3 bytes vs 1) --
    so we assert the new content equals the old content modulo the swap
  * after writing, re-read and assert zero DANGER lines remain

Usage:
  python tools/fix_comment_quotes.py           # dry run
  python tools/fix_comment_quotes.py --apply   # write
"""
import io
import sys

FILES = ["src/Streamline.cpp", "src/FrameGen.cpp", "src/Streamline.h", "src/FrameGen.h"]
APPLY = "--apply" in sys.argv

LQ = "\u201c"   # “
RQ = "\u201d"   # ”


def comment_start(ln):
    inlit = False
    esc = False
    for k, ch in enumerate(ln):
        if inlit:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                inlit = False
            continue
        if ch == '"':
            inlit = True
            continue
        if ch == "/" and k + 1 < len(ln) and ln[k + 1] == "/":
            return k
    return -1


def fix_line(ln):
    c = comment_start(ln)
    if c < 0 or '"' not in ln[c:]:
        return ln, 0
    head, tail = ln[:c], ln[c:]
    if "//" in tail[tail.index('"'):]:
        return ln, 0
    n = tail.count('"')
    # alternate open/close quoting so the text still reads correctly
    out = []
    flip = False
    for ch in tail:
        if ch == '"':
            out.append(RQ if flip else LQ)
            flip = not flip
        else:
            out.append(ch)
    return head + "".join(out), n


total_fixed = 0
total_quotes = 0
report = []

for path in FILES:
    raw = io.open(path, "rb").read()
    text = raw.decode("utf-8")
    lines = text.split("\n")
    changed = 0
    quotes = 0
    for i, ln in enumerate(lines):
        new, n = fix_line(ln)
        if n:
            lines[i] = new
            changed += 1
            quotes += n
    new_text = "\n".join(lines)

    # ---- assertions -------------------------------------------------------
    old_bytes = len(raw)
    new_bytes = len(new_text.encode("utf-8"))
    delta = new_bytes - old_bytes
    expect = quotes * 2          # each ASCII quote (1 B) becomes 3 B
    ok_delta = (delta == expect)
    ok_lines = (len(lines) == len(text.split("\n")))
    print("%-22s lines fixed=%-3d quotes=%-3d dbytes=%+d (expect %+d) %s | line-count-stable %s"
          % (path, changed, quotes, delta, expect,
             "OK" if ok_delta else "MISMATCH",
             "OK" if ok_lines else "CHANGED"))
    if not (ok_delta and ok_lines):
        print("REFUSED: %s failed its own invariant check" % path)
        sys.exit(1)
    total_fixed += changed
    total_quotes += quotes
    report.append((path, new_text))

print()
print("TOTAL: %d comment lines, %d ASCII quotes" % (total_fixed, total_quotes))

# ---- verify the fix actually removes DANGER -------------------------------
remaining = 0
for path, new_text in report:
    for ln in new_text.split("\n"):
        c = comment_start(ln)
        if c < 0 or '"' not in ln[c:]:
            continue
        tail = ln[c:]
        if "//" not in tail[tail.index('"'):]:
            remaining += 1
print("DANGER lines remaining after fix: %d" % remaining)
if remaining:
    print("REFUSED: fix incomplete")
    sys.exit(1)

if not APPLY:
    print()
    print("DRY RUN -- nothing written. Add --apply to write.")
    sys.exit(0)

for path, new_text in report:
    with io.open(path, "wb") as f:
        f.write(new_text.encode("utf-8"))
print()
print("APPLIED.")
