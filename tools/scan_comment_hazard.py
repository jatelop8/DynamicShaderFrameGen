# -*- coding: utf-8 -*-
"""Determine whether a quoted // comment is HARMFUL.

A // comment containing an ASCII '"' has its quote close the comment early.
The remainder of the line then becomes real code.

It is harmless IF AND ONLY IF the remainder still lexes as a comment, i.e. the
remainder contains another '//' before the quote. Otherwise the tail becomes
code, and any quote inside it opens a string that runs across lines until the
next quote -- swallowing everything in between, including format strings.

Model: for each offending line, print the text BEFORE the first quote (kept as
comment) and the text AFTER it (which becomes code).
"""
import io

FILES = ["src/Streamline.cpp", "src/FrameGen.cpp", "src/Streamline.h", "src/FrameGen.h"]

for path in FILES:
    raw = io.open(path, "rb").read()
    text = raw.decode("utf-8", errors="replace")
    lines = text.split("\n")

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

    print("=== %s ===" % path)
    for n, ln in enumerate(lines, 1):
        c = comment_start(ln)
        if c < 0 or '"' not in ln[c:]:
            continue
        q = ln.index('"', c)
        tail = ln[q:]
        # does the tail close as a comment again, and is the quote pair
        # fully "absorbed" by it?
        if '//' in tail:
            verdict = "SAFE (tail re-commented)"
        else:
            nq = tail.count('"')
            verdict = "DANGER (tail leaks as code, quotes=%d)" % nq
        print("  line %-5d %-34s %s" % (n, verdict, ln.strip()[:96]))
    print()
