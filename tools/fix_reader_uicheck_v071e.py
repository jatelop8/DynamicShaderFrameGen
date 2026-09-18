#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.71e: fix a FALSE verdict in tools/read_xray_log.py.

The menu-probe section decided "RE::UI singleton is null" with

    if "ui=0" in raw or "ui=0x0" in raw:

which is a substring test.  Every non-null pointer the probe prints starts with
the characters "ui=0" -- the 2026-09-17 23:40 log contains

    MENU PROBE ui=0x7ff745c3ceb0 istrings=0x7ff745c71150 | ptr mainMenu=...

so the reader reported "RE::UI singleton is null -> the menu guard cannot work,
this is a CommonLib address/version problem" and pushed the same line into the
summary -- while the very next line it printed said the InterfaceStrings layout
was correct (pointers equal).  Self-contradictory output that would send the
next debugging round chasing a non-existent CommonLib problem.

The rule this violates: a canary must be the *damage pattern*, never a string
that also occurs in healthy output.  Compare the value, not its prefix.

Reads and writes as UTF-8: the anchors contain Chinese, and a latin-1 round
trip turns them into mojibake so nothing ever matches (first draft of this
script did exactly that and reported "anchor x0").  A latin-1 round trip is for
files with legacy non-ASCII comments (ENB ini), not for UTF-8 Python sources.
Dry run by default; --apply writes.  Refuses outright if any anchor is missing
or ambiguous, or if the change is already present.
"""

import os
import shutil
import sys
import time

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "read_xray_log.py")

# ---------------------------------------------------------------- idempotency
# "anchor unique" and "already applied" are two different questions: this edit
# does NOT consume its anchor (the anchor text is the thing being replaced, so
# it is consumed -- but keep the marker check anyway, it is the cheap one).
MARKERS = [
    "v0.71e:",
    "mu = re.search(r\"\\bui=(0x[0-9a-fA-F]+|\\d+)\", raw)",
]

OLD = '''        if "ui=0" in raw or "ui=0x0" in raw:
            print(SEV_BAD + "  RE::UI 单例为空 → 菜单检测整体失效，这是 CommonLib 地址/版本问题")
            note(SEV_BAD, "RE::UI 单例为空：菜单守卫不可能生效")
'''

NEW = '''        # v0.71e: "ui=0" is a PREFIX of "ui=0x7ff7..." -- the old test declared
        # every non-null singleton to be null (2026-09-17: the log printed
        # ui=0x7ff745c3ceb0 and the reader still said "RE::UI 单例为空", right
        # above its own line saying the layout was correct). Parse the value.
        mu = re.search(r"\\bui=(0x[0-9a-fA-F]+|\\d+)", raw)
        if mu is not None and int(mu.group(1), 0) == 0:
            print(SEV_BAD + "  RE::UI 单例为空 → 菜单检测整体失效，这是 CommonLib 地址/版本问题")
            note(SEV_BAD, "RE::UI 单例为空：菜单守卫不可能生效")
        elif mu is not None:
            print(SEV_OK + "  RE::UI 单例有效（ui=%s）—— 菜单检测可用" % mu.group(1))
'''

EDITS = [
    ("ui emptiness test becomes a value test", OLD, NEW),
]

# after the edit, these must be exactly true
POST = [
    ('mu = re.search(r"\\bui=(0x[0-9a-fA-F]+|\\d+)", raw)', 1),
    ('if "ui=0" in raw or "ui=0x0" in raw:', 0),
    ("RE::UI 单例有效", 1),
]


def match_anchor(text, anchor):
    """Return the anchor as it actually appears (EOL-adaptive), or None."""
    if anchor in text:
        return anchor
    for a, b in (("\r\n", "\n"), ("\n", "\r\n")):
        swapped = anchor.replace(a, b)
        if swapped in text:
            return swapped
    return None


def main():
    apply_it = "--apply" in sys.argv

    with open(TARGET, "rb") as f:
        raw_bytes = f.read()
    text = raw_bytes.decode("utf-8")

    for m in MARKERS:
        if m in text:
            print("REFUSED -- already applied (marker present: %r)" % m)
            return 2

    print("target: %s" % TARGET)
    print("bytes before: %d" % len(raw_bytes))
    print()

    planned = []
    ok = True
    for label, old, new in EDITS:
        n = text.count(old)
        anchor = match_anchor(text, old)
        if n != 1 or anchor is None:
            print("%-46s anchor x%d  <== REFUSED" % (label, n))
            ok = False
            continue
        planned.append((label, anchor, new))
        print("%-46s anchor x1" % label)

    if not ok:
        print()
        print("REFUSED, nothing written.")
        return 2

    out = text
    for _label, anchor, new in planned:
        line_ending = "\r\n" if "\r\n" in anchor else "\n"
        out = out.replace(anchor, new.replace("\n", line_ending), 1)

    # ---- post-conditions on the RESULT, not on the intent ----------------
    bad = []
    for needle, want in POST:
        got = out.count(needle)
        if got != want:
            bad.append("%r count=%d want=%d" % (needle, got, want))
    if bad:
        print()
        for b in bad:
            print("POST FAIL: %s" % b)
        print("REFUSED, nothing written.")
        return 2

    delta = len(out.encode("utf-8")) - len(raw_bytes)
    print()
    print("post-conditions: %d checks OK" % len(POST))
    print("%+d bytes" % delta)

    if not apply_it:
        print()
        print("DRY RUN -- nothing written. Re-run with --apply")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = TARGET + ".bak-" + stamp
    shutil.copy2(TARGET, backup)
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))

    # read back from disk, never trust the in-memory copy
    back = open(TARGET, "rb").read().decode("utf-8")
    for needle, want in POST:
        got = back.count(needle)
        if got != want:
            print("READBACK FAIL: %r count=%d want=%d" % (needle, got))
            return 3
    crlf = back.count("\r\n")
    lone = back.count("\r") - crlf
    print("readback OK | CRLF=%d LF=%d loneCR=%d" % (crlf, back.count("\n") - crlf, lone))
    print("wrote %s (backup %s)" % (TARGET, os.path.basename(backup)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
