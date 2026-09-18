#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyse_v087_dump.py -- turn the v0.87 raw dump into a verdict.

Reads the [RAW] and [FLD] lines produced by the v0.87 probe and answers one
question: WHERE, if anywhere, does the engine actually store a usable
view-projection matrix?

Method
------
1. Rebuild each dumped block's 168 floats from the [RAW] lines (+0000 .. +0170).
2. Slide a 4x4 window over the whole 168-float buffer, at every float offset,
   and score each candidate as a "camera matrix":
       - row3 must be ~(0,0,0,1)            (the w row of a homogeneous map)
       - the top-left 3x3 should be a rotation (det ~ +/-1) for a View, or a
         plausible projection for a Proj (det != 0)
   Report every offset whose row3 test passes.
3. Cross-check against the declared field offsets: for each of the 10 declared
   fields (c0,c8,...,c72 -> struct offsets 0,64,...,576) report whether the
   window at that offset passes.
4. Compare with the [FLD] lines so the printed verdict double-checks the probe.

Output: a table of every offset that passes the row3 test, plus a verdict
naming the true stride / true offset.

Usage: python tools/analyse_v087_dump.py <logfile>
"""

import re
import sys

NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
RE_RAW = re.compile(r"\[RAW\]\s+\+0x([0-9a-fA-F]+)\s*\|(.*)$")
RE_FLD = re.compile(
    r"\[FLD\]\s+#(\d+)\s+(\S+)\s+(\S.*?)\s+row3=\(\s*(" + NUM + r")\s*,\s*(" + NUM + r")"
    r"\s*,\s*(" + NUM + r")\s*,\s*(" + NUM + r")\s*\)\s+\[3\]\[3\]=(" + NUM + r")"
    r"\s+dev=(" + NUM + r")\s+det=(" + NUM + r")\s+mag=(" + NUM + r")\s+(\S+)")

FIELD_OFFSETS = [
    (0, "c0  CameraView"),
    (64, "c8  CameraProj"),
    (128, "c16 CameraViewProj"),
    (192, "c24 CameraViewProjUnjittered"),
    (256, "c32 CameraPreviousViewProjUnjittered"),
    (320, "c40 CameraProjUnjittered"),
    (384, "c48 CameraProjUnjitteredInverse"),
    (448, "c56 CameraViewInverse"),
    (512, "c64 CameraViewProjInverse"),
    (576, "c72 CameraProjInverse"),
    (640, "c80 CameraPosAdjust"),
    (656, "c82 CameraPreviousPosAdjust"),
]


def parse_log(path):
    """-> {arrival_index: {'raw': {byte_off: [floats]}, 'fld': [...]}}"""
    blocks = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = RE_RAW.search(line)
            if m:
                off = int(m.group(1), 16)
                toks = m.group(2).replace("|", " ").split()
                try:
                    vals = [float(t) for t in toks]
                except ValueError:
                    continue
                if len(vals) == 8:
                    # [RAW] lines carry no arrival id; they follow the [CAM] raw
                    # #N lines of the same dump. Use the last seen id.
                    blocks.setdefault(_last_id[0], {"raw": {}, "fld": []})
                    blocks[_last_id[0]]["raw"][off] = vals
                continue
            m2 = re.search(r"\[CAM\]\s+raw\s+#(\d+)", line)
            if m2:
                _last_id[0] = int(m2.group(1))
                blocks.setdefault(_last_id[0], {"raw": {}, "fld": []})
                continue
            m3 = RE_FLD.search(line)
            if m3:
                blocks.setdefault(int(m3.group(1)), {"raw": {}, "fld": []})
                blocks[int(m3.group(1))]["fld"].append((
                    m3.group(2), float(m3.group(8)), float(m3.group(9)),
                    float(m3.group(10)), m3.group(11)))
    return blocks


_last_id = [0]


def flatten(raw_map):
    """byte_off -> 8 floats, into a flat float list indexed by float offset."""
    if not raw_map:
        return []
    n = max(raw_map) + 32
    buf = [None] * (n // 4)
    for off, vals in raw_map.items():
        for i, v in enumerate(vals):
            idx = off // 4 + i
            if 0 <= idx < len(buf):
                buf[idx] = v
    return buf


def row3_ok(buf, fo):
    """fo = float offset of a candidate 4x4 matrix."""
    if fo + 15 >= len(buf):
        return None
    r = buf[fo + 12:fo + 16]
    if any(v is None for v in r):
        return None
    if abs(r[0]) > 1e-3 or abs(r[1]) > 1e-3 or abs(r[2]) > 1e-3:
        return False
    return abs(r[3] - 1.0) <= 1e-3


def det3(buf, fo):
    m = [buf[fo + i] for i in (0, 1, 2, 4, 5, 6, 8, 9, 10)]
    if any(v is None for v in m):
        return None
    a, b, c, d, e, f, g, h, i = m
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)


def main():
    if len(sys.argv) < 2:
        print("usage: analyse_v087_dump.py <logfile>")
        return 2
    blocks = parse_log(sys.argv[1])
    usable = {k: v for k, v in blocks.items() if v["raw"]}
    print("=" * 92)
    print("v0.87 RAW-DUMP ANALYSIS")
    print("=" * 92)
    print("blocks with raw data : %d" % len(usable))
    if not usable:
        print()
        print("No [RAW] lines found. Either the probe DLL was not loaded, or")
        print("DumpCameraSnapshot never fired (arrivals <= 2 and no verdict flip).")
        return 1
    print()

    for idx in sorted(usable):
        blk = usable[idx]
        buf = flatten(blk["raw"])
        print("-" * 92)
        print("#%d  (%d floats dumped)" % (idx, len([v for v in buf if v is not None])))
        # every offset whose row3 test passes
        hits = []
        for fo in range(0, max(0, len(buf) - 15)):
            r = row3_ok(buf, fo)
            if r:
                d = det3(buf, fo)
                hits.append((fo, fo * 4, d))
        if hits:
            print("  window offsets passing the row3 == (0,0,0,1) test:")
            for fo, bo, d in hits:
                print("    float[%3d] = byte +%#06x   det3=%s" % (
                    fo, bo, ("%.6g" % d) if d is not None else "?"))
            stride = None
            if len(hits) >= 2:
                diffs = [hits[i + 1][0] - hits[i][0] for i in range(len(hits) - 1)]
                if diffs and len(set(diffs)) == 1:
                    stride = diffs[0]
            if stride:
                print("  => CONSTANT STRIDE between hits: %d floats = %d bytes = %d c-registers"
                      % (stride, stride * 4, stride * 4 // 16))
            else:
                print("  => no constant stride between hits")
        else:
            print("  NO offset in the buffer satisfies row3 == (0,0,0,1)")
        # declared fields
        print("  declared fields:")
        for off, name in FIELD_OFFSETS:
            fo = off // 4
            r = row3_ok(buf, fo)
            if r is None:
                print("    %-38s byte +%#06x  (out of dumped range)" % (name, off))
                continue
            d = det3(buf, fo)
            print("    %-38s byte +%#06x  row3-test=%s det3=%s" % (
                name, off, "PASS" if r else "fail",
                ("%.6g" % d) if d is not None else "?"))
        if blk["fld"]:
            print("  probe [FLD] self-report:")
            for name, w, dev, det, verdict in blk["fld"]:
                print("    %-14s [3][3]=%-10.6g dev=%-10.6g det=%-10.6g %s" % (
                    name, w, dev, det, verdict))
        print()

    print("=" * 92)
    print("HOW TO READ THIS")
    print("=" * 92)
    print("If the only offsets passing the row3 test are the declared ones, the")
    print("struct layout is right and the malformed viewProj is a value problem.")
    print("If some OTHER constant stride shows up, the engine's real layout differs")
    print("and the struct in FrameGen.h must be re-laid-out to match it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
