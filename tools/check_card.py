#!/usr/bin/env python3
"""Validate a self-contained delivery-card HTML before showing it to the user.

Checks, in order:
  1. every tag is closed and closed in the right order (void elements excluded)
  2. no nested <b> (a common hand-written slip that silently drops styling)
  3. no stray Markdown left in the text ("**", "```")
  4. no Korean / Japanese kana characters (signs of an IME slip: measured once
     as a single stray character in a previous card)
  5. unescaped "<" or ">" in prose, which would swallow text
  6. presence counts for the key strings given on the command line (a card is a
     delivery document: the numbers on it must actually be in it)

Usage:  check_card.py <card.html> [key string ...]
Exit 0 = OK, 1 = needs fixing.
"""
import re
import sys
from pathlib import Path

VOID = {"meta", "br", "hr", "img", "input", "link", "area", "base", "col",
        "embed", "source", "track", "wbr"}

TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)([^>]*?)(/?)>", re.S)
TOKEN = re.compile(r"</?b>", re.S)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: check_card.py <card.html> [key string ...]")
        return 2
    path = Path(sys.argv[1])
    keys = sys.argv[2:]
    s = path.read_text(encoding="utf-8")
    ok = True

    print(f"file  {path}")
    print(f"bytes {len(s.encode('utf-8'))}")

    unclosed, bad_close = [], []
    stack = []
    for m in TAG.finditer(s):
        close, name, _attrs, selfc = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if name in VOID or selfc:
            continue
        if close:
            if stack and stack[-1] == name:
                stack.pop()
            else:
                bad_close.append((name, stack[-1] if stack else None))
        else:
            stack.append(name)
    unclosed, bad_close = stack, bad_close
    print(f"unclosed {unclosed}   bad closes {bad_close}")
    if unclosed or bad_close:
        ok = False

    # nested <b>
    nest = 0
    stack = []
    for m in TOKEN.finditer(s):
        if m.group(0) == "<b>":
            if stack:
                nest += 1
            stack.append(m.start())
        elif stack:
            stack.pop()
    print(f"nested <b> {nest}   unclosed <b> {len(stack)}")
    if nest or stack:
        ok = False

    for label, needle in (("markdown **", "**"), ("markdown ```", "```")):
        c = s.count(needle)
        print(f"{label:<14} {c}")
        if c:
            ok = False

    bad = sorted(set(ch for ch in s
                     if "\uac00" <= ch <= "\ud7af"          # Hangul syllables
                     or "\u3040" <= ch <= "\u30ff"))        # hiragana / katakana
    print(f"korean/kana   {bad if bad else 'none'}")
    if bad:
        ok = False

    # an unescaped "<" that is not part of a tag.
    # Strip the prologue and comments FIRST: "<!DOCTYPE html>" and "<!-- -->" are
    # legal HTML but TAG only matches "<name", so both would be reported as stray
    # angle brackets -- a false positive that made a clean card read NEEDS FIX.
    stripped = re.sub(r"<!DOCTYPE[^>]*>", "", s, flags=re.I)
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.S)
    stripped = TAG.sub("", stripped)
    stray = [m.start() for m in re.finditer(r"[<>]", stripped)]
    print(f"stray < or >  {len(stray)}")
    if stray:
        for i in stray[:5]:
            print(f"    ...{stripped[max(0, i-40):i+40]!r}")
        ok = False

    for k in keys:
        c = s.count(k)
        print(f"key {k[:52]!r:<56} {c}")
        if c == 0:
            ok = False

    print("\nRESULT: " + ("OK - safe to view" if ok else "NEEDS FIX"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
