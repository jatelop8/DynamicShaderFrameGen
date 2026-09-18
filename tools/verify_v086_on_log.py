#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_v086_on_log.py -- offline exhaustive verification of the v0.86 guard.

Real log format (single line per matrix, rows separated by '|'):
   [14:21:25.725] [42152] [I] [CAM] raw #1 ViewProjUnj | -6.70312 0 0 0 | 0 -1.57495 11.8121 0 | 0 -0.991954 -0.132261 -15.011 | 0 -0.991228 -0.132164 0
   [14:21:25.725] [42152] [I] [CAM] raw #1 ProjUnj     | ...  (4 rows)
   [14:21:25.725] [42152] [I] [CAM] raw #1 ViewInv     | ...  (4 rows)
   [14:21:25.725] [42152] [I] [CAM] raw #1 pos=(x,y,z,w) prevPos=(...) devVP=.. detVP=.. detProj=.. magVP=..

So one dump block = 4 physical lines, identifying ViewProjUnj / ProjUnj / ViewInv
plus a summary line carrying the scalars.

Usage: python tools/verify_v086_on_log.py <logfile>
"""

import re
import sys
from collections import Counter, OrderedDict

NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"

RE_MAT = re.compile(
    r"\[CAM\]\s+raw\s+#(\d+)\s+(ViewProjUnj|ProjUnj|ViewInv)\s*\|(.*)$")
RE_SUM = re.compile(
    r"\[CAM\]\s+raw\s+#(\d+)\s+pos=\(\s*(" + NUM + r")\s*,\s*(" + NUM + r")\s*,\s*(" + NUM + r")"
    r"\s*,\s*(" + NUM + r")\s*\)"
    r".*?devVP=(" + NUM + r")\s+detVP=(" + NUM + r")"
    r"\s+detProj=(" + NUM + r")\s+magVP=(" + NUM + r")")


def parse_rows(payload):
    """'| a b c d | e f g h | ...' -> [[a,b,c,d],[e,f,g,h],...] or None."""
    parts = [p.strip() for p in payload.split("|")]
    parts = [p for p in parts if p]
    if len(parts) != 4:
        return None
    rows = []
    for p in parts:
        toks = p.split()
        if len(toks) != 4:
            return None
        try:
            rows.append([float(t) for t in toks])
        except ValueError:
            return None
    return rows


def parse(path):
    blocks = OrderedDict()   # idx -> dict
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = RE_MAT.search(line)
            if m:
                idx = int(m.group(1))
                blk = blocks.setdefault(idx, {"idx": idx, "mats": {}})
                rows = parse_rows(m.group(3))
                if rows:
                    blk["mats"][m.group(2)] = rows
                continue
            s = RE_SUM.search(line)
            if s:
                idx = int(s.group(1))
                blk = blocks.setdefault(idx, {"idx": idx, "mats": {}})
                blk["pos"] = tuple(float(s.group(i)) for i in (2, 3, 4))
                blk["w"] = float(s.group(5))
                blk["dev"] = float(s.group(6))
                blk["det"] = float(s.group(7))
                blk["detProj"] = float(s.group(8))
                blk["mag"] = float(s.group(9))
    return [b for b in blocks.values() if "pos" in b and "ViewProjUnj" in b.get("mats", {})]


def main():
    if len(sys.argv) < 2:
        print("usage: verify_v086_on_log.py <logfile>")
        return 2
    path = sys.argv[1]
    blocks = parse(path)

    print("=" * 100)
    print("v0.86 HOMOGENEOUS-SHAPE GUARD -- OFFLINE VERIFICATION")
    print("=" * 100)
    print("log    : %s" % path)
    print("blocks : %d  (each carries a ViewProjUnj matrix + scalars)" % len(blocks))
    print()

    hdr = "%-7s %-24s %-11s %-11s %-11s %-11s %s" % (
        "#", "pos", "devVP", "detVP", "VP[3][3]", "Proj[3][3]", "v0.86")
    print(hdr)
    print("-" * 100)

    passed = 0
    rejected = 0
    fam_rej = Counter()
    fam_acc = Counter()

    for b in blocks:
        vp = b["mats"]["ViewProjUnj"]
        pj = b["mats"].get("ProjUnj")
        w = vp[3][3]
        ok = abs(w - 1.0) <= 1.0e-3
        ws = "%.6g" % w
        ps = ("%.6g" % pj[3][3]) if pj else "n/a"
        verdict = "PASS" if ok else "REJECT"
        if ok:
            passed += 1
            fam_acc["(%.0f,%.0f,%.0f)" % b["pos"]] += 1
        else:
            rejected += 1
            fam_rej["(%.0f,%.0f,%.0f)" % b["pos"]] += 1
        print("%-7d %-24s %-11.6g %-11.6g %-11s %-11s %s" % (
            b["idx"], "(%.1f,%.1f,%.1f)" % b["pos"], b["dev"], b["det"], ws, ps, verdict))

    print("-" * 100)
    print("PASS (counted as a camera)  : %d" % passed)
    print("REJECT (dropped)            : %d" % rejected)
    print()
    print("PASS family by pos   :", dict(fam_acc) or "{}")
    print("REJECT family by pos :", dict(fam_rej) or "{}")
    print()
    print("=" * 100)
    print("VERDICT")
    print("=" * 100)
    if passed == 0:
        print("FAIL -- nothing survives; the picture would go black.")
        return 1
    if rejected == 0:
        print("SUSPECT -- nothing is rejected in this log; v0.86 would be a no-op here.")
        return 0
    print("PASS -- the guard separates two families cleanly.")
    print("       accepted: %d   rejected: %d" % (passed, rejected))
    return 0


if __name__ == "__main__":
    sys.exit(main())
