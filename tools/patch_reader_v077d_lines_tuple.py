#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.77 part 4: fix part_dlssg_health() - it treated `lines` as a list of raw
strings, but parse_lines() yields (timestamp, thread, text) tuples, so every
`... in ln` test was false and the section printed "没有 FPS probe 行".

Also route the MFG ladder print through the same tuple form.
"""
import os
import sys
import shutil
import datetime
import ast

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, "read_xray_log.py")

OLD_BLOCK = '''    # ---- 1. the accepted= field from the 2 s FPS probe ----
    probes = []
    for ln in lines:
        if "[FrameGen] FPS probe:" not in ln:
            continue
        m = re.search(r"\\[([0-9:.]+)\\]", ln)
        wall = m.group(1) if m else "?"
        mr = re.search(r"real=([0-9.]+)", ln)
        ma = re.search(r"accepted=(\\d+)", ln)
        mh = re.search(r"hwMax=(\\d+)", ln)
        mask = re.search(r"ask=(\\d+)", ln)
        if ma and mr:
            probes.append({
                "wall": wall,
                "real": float(mr.group(1)),
                "accepted": int(ma.group(1)),
                "hwMax": int(mh.group(1)) if mh else None,
                "ask": int(mask.group(1)) if mask else None,
            })
    if not probes:
        print(SEV_INFO + "没有 FPS probe 行，跳过。")
        return
'''

NEW_BLOCK = '''    # ---- 1. the accepted= field from the 2 s FPS probe ----
    # NOTE: `lines` holds (timestamp, thread, text) tuples, not raw strings.
    probes = []
    for _ts, _tid, ln in lines:
        if "[FrameGen] FPS probe:" not in ln:
            continue
        wall = _ts or "?"
        mr = re.search(r"real=([0-9.]+)", ln)
        ma = re.search(r"accepted=(\\d+)", ln)
        mh = re.search(r"hwMax=(\\d+)", ln)
        mask = re.search(r"ask=(\\d+)", ln)
        if ma and mr:
            probes.append({
                "wall": wall,
                "real": float(mr.group(1)),
                "accepted": int(ma.group(1)),
                "hwMax": int(mh.group(1)) if mh else None,
                "ask": int(mask.group(1)) if mask else None,
            })
    if not probes:
        print(SEV_INFO + "没有 FPS probe 行，跳过。")
        return
'''

# The three later list comprehensions over `lines` have the same defect.
OLD_COMP = '''    comp = [ln for ln in lines if "COMPUTED not measured" in ln]'''
NEW_COMP = '''    comp = [t for _ts, _tid, t in lines if "COMPUTED not measured" in t]'''

OLD_LADDER = '''    rej = [ln for ln in lines if "MFG probe: runtime REJECTED" in ln]
    acc = [ln for ln in lines if "MFG probe: runtime ACCEPTED" in ln]
    rmax = [ln for ln in lines if "runtimeReportsMax=" in ln]'''
NEW_LADDER = '''    rej = [t for _ts, _tid, t in lines if "MFG probe: runtime REJECTED" in t]
    acc = [t for _ts, _tid, t in lines if "MFG probe: runtime ACCEPTED" in t]
    rmax = [t for _ts, _tid, t in lines if "runtimeReportsMax=" in t]'''

EDITS = [
    ("probes loop: unpack the tuple", OLD_BLOCK, NEW_BLOCK),
    ("COMPUTED list: unpack the tuple", OLD_COMP, NEW_COMP),
    ("MFG ladder lists: unpack the tuple", OLD_LADDER, NEW_LADDER),
]

CANARIES = [
    ("    for _ts, _tid, ln in lines:", 1),
    ('    comp = [t for _ts, _tid, t in lines if "COMPUTED not measured" in t]', 1),
    ('    rej = [t for _ts, _tid, t in lines if "MFG probe: runtime REJECTED" in t]', 1),
    ('    acc = [t for _ts, _tid, t in lines if "MFG probe: runtime ACCEPTED" in t]', 1),
    ('    rmax = [t for _ts, _tid, t in lines if "runtimeReportsMax=" in t]', 1),
]

MARKERS = [
    "NOTE: `lines` holds (timestamp, thread, text) tuples, not raw strings.",
]


def main():
    apply = "--apply" in sys.argv
    src = open(READER, "r", encoding="utf-8", newline="").read()
    for m in MARKERS:
        if m in src:
            print("REFUSED: marker already present -> already applied: %r" % m)
            return 2

    text = src
    for label, old, new in EDITS:
        n = text.count(old)
        if n != 1:
            print("REFUSED: anchor for %r found %d times (want exactly 1)" % (label, n))
            return 2
        text = text.replace(old, new)

    # no stale iteration over raw `lines` may remain inside the new section
    stale = text.count("for ln in lines")
    if stale:
        print("REFUSED: %d remaining 'for ln in lines' loops (should have been rewritten)" % stale)
        return 2

    for c, want in CANARIES:
        n = text.count(c)
        if n != want:
            print("REFUSED: canary %r found %d times (want %d)" % (c, n, want))
            return 2

    for m in MARKERS:
        if m not in text:
            print("REFUSED: marker missing after patch: %r" % m)
            return 2

    try:
        ast.parse(text)
    except SyntaxError as e:
        print("REFUSED: not parseable after patch: %s" % e)
        return 2

    if ("\r\n" in src) != ("\r\n" in text):
        print("REFUSED: line-ending style changed")
        return 2

    if not apply:
        print("[dry-run] 3 anchors unique, no stale loops, canaries OK, ast OK")
        print("[dry-run] bytes %d -> %d (%+d)" % (len(src), len(text), len(text) - len(src)))
        print("[dry-run] re-run with --apply to write")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-%s" % (READER, stamp)
    shutil.copy2(READER, bak)
    with open(READER, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("applied to %s" % READER)
    print("backup: %s" % bak)
    print("bytes %d -> %d (%+d)" % (len(src), len(text), len(text) - len(src)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
