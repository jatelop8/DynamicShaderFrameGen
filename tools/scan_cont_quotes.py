# -*- coding: utf-8 -*-
"""Find the REAL hazard layout: a // comment whose NEXT line(s) continue with //.

Only such a block can swallow following code. A single standalone // line with a
quote is harmless (the compiler closes the comment, and the rest of the line is
plain text tokens that are never parsed as code because they are still skipped
as... no -- they ARE parsed. So the real hazard is the reverse: the quote closes
the comment, the tail is parsed, and if the tail happens to be valid-ish the
error shows up FAR away.

Report every // comment that contains a quote AND whose comment text has a
`/` at position 0 of the following line (continuation style).
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
    for n, ln in enumerate(lines):
        c = comment_start(ln)
        if c < 0:
            continue
        if '"' not in ln[c:]:
            continue
        # is the next non-empty line also a comment continuation?
        nxt = lines[n + 1].strip() if n + 1 < len(lines) else ""
        prev = lines[n - 1].strip() if n > 0 else ""
        cont_next = nxt.startswith("//")
        cont_prev = prev.startswith("//")
        if cont_next or cont_prev:
            print("  line %d (prev_cont=%s next_cont=%s)  %s"
                  % (n + 1, cont_prev, cont_next, ln.strip()[:110]))
    print()
