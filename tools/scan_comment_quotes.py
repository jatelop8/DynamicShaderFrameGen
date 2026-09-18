# -*- coding: utf-8 -*-
"""Scan every // comment line for ASCII double quotes.

An ASCII '"' inside a // comment line CLOSES the comment (quotes win over //).
If the same comment uses a backslash-continuation or a second // on the next
line, the rest of the block silently becomes code -- which is how the heartbeat
format string got swallowed.

Reports: file, line number, column of each offending quote, plus the raw line.
"""
import io
import sys

FILES = [
    "src/Streamline.cpp",
    "src/Streamline.h",
    "src/FrameGen.cpp",
    "src/FrameGen.h",
]

bad_total = 0
for path in FILES:
    try:
        raw = io.open(path, "rb").read()
    except IOError:
        print("SKIP %s (not found)" % path)
        continue
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")
    n_bad = 0
    for n, ln in enumerate(lines, 1):
        # find '//' that starts a comment: not inside a string literal
        inlit = False
        esc = False
        cpos = -1
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
                cpos = k
                break
        if cpos < 0:
            continue
        comment = ln[cpos:]
        if '"' in comment:
            cols = [cpos + j + 1 for j, ch in enumerate(comment) if ch == '"']
            n_bad += 1
            bad_total += 1
            print("%s:%d  cols=%s" % (path, n, cols))
            print("    %s" % ln.strip()[:160])
    print("%-22s comment-lines with ASCII quote: %d" % (path, n_bad))

print()
print("TOTAL OFFENDING LINES: %d" % bad_total)
