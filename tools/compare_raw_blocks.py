#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_raw_blocks.py -- byte-level compare of the v0.87 [RAW] dumps.

Rebuilds each dumped 168-float block and prints, per declared field:
  - the field's 16 floats
  - whether it differs from the same field in the previous block

The question: does CameraViewProjUnjittered (c24) actually change between
frames, or is it the same value while CameraPosAdjust (the engine's real
world camera) moves by hundreds of units? If c24 never changes while pos does,
the two fields do not describe the same camera and clipToPrevClip stays
identity -> no interpolated frames in the right direction.

Usage: python tools/compare_raw_blocks.py <logfile>
"""

import re
import sys

NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
RE_RAW = re.compile(r"\[(\d+):(\d+):([\d.]+)\]\s+\[\d+\]\s+\[I\]\s+\[RAW\]\s+\+0x([0-9a-fA-F]+)\s*\|(.*)$")
RE_FLD = re.compile(r"\[(\d+):(\d+):([\d.]+)\].*\[FLD\]\s+#(\d+)\s+(\S+)\s+(\S.*?)\s+row3")

FIELDS = [
    (0, "c0  CameraView"), (64, "c8  CameraProj"), (128, "c16 CameraViewProj"),
    (192, "c24 CameraViewProjUnjittered"), (256, "c32 CameraPreviousViewProjUnjittered"),
    (320, "c40 CameraProjUnjittered"), (384, "c48 CameraProjUnjitteredInverse"),
    (448, "c56 CameraViewInverse"), (512, "c64 CameraViewProjInverse"),
    (576, "c72 CameraProjInverse"), (640, "c80 CameraPosAdjust"),
    (656, "c82 CameraPreviousPosAdjust"),
]


def parse(path):
    """-> ordered list of (time, {byte_off: [8 floats]})"""
    blocks = []
    cur = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = RE_RAW.search(line)
            if m:
                t = "%s:%s:%s" % (m.group(1), m.group(2), m.group(3))
                off = int(m.group(4), 16)
                toks = m.group(5).replace("|", " ").split()
                try:
                    vals = [float(x) for x in toks]
                except ValueError:
                    continue
                if len(vals) != 8:
                    continue
                if cur is None or cur[0] != t or off == 0:
                    cur = (t, {})
                    blocks.append(cur)
                cur[1][off] = vals
    return blocks


def field_vals(blk, off):
    out = []
    for fo in range(off // 4, off // 4 + 16):
        for k, vals in blk[1].items():
            if k // 4 <= fo < k // 4 + 8:
                out.append(vals[fo - k // 4])
                break
        else:
            out.append(None)
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: compare_raw_blocks.py <logfile>")
        return 2
    blocks = parse(sys.argv[1])
    print("=" * 96)
    print("v0.87 RAW BLOCK COMPARISON -- %d blocks" % len(blocks))
    print("=" * 96)
    if not blocks:
        print("no [RAW] blocks parsed -- parser or probe problem")
        return 1

    prev = None
    for i, blk in enumerate(blocks):
        print()
        print("-" * 96)
        print("block %d   t=%s" % (i, blk[0]))
        print("-" * 96)
        for off, name in FIELDS:
            v = field_vals(blk, off)
            if all(x is None for x in v):
                print("  %-40s (not dumped)" % name)
                continue
            shown = " ".join("%9.5g" % x if x is not None else "    ?    " for x in v)
            diff = ""
            if prev is not None:
                pv = field_vals(prev, off)
                if any(a is not None and b is not None and a != b for a, b in zip(v, pv)):
                    diff = "   <-- CHANGED"
                else:
                    diff = "   (same)"
            print("  %-40s %s%s" % (name, shown, diff))
        prev = blk
    return 0


if __name__ == "__main__":
    sys.exit(main())
