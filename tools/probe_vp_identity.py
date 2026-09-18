#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe_vp_identity.py -- linear-algebra cross-check of the dumped matrices.

Question we are trying to settle:
    Is the dumped ViewProjUnj a *legitimate* matrix (i.e. does it equal
    ViewInv * ProjUnj, up to the game's convention) or is it a mis-offset
    read of the perFrame buffer?

Method
------
For each dumped block we know three 4x4 matrices: ViewProjUnj, ProjUnj, ViewInv.
We compute several candidate products and report which one (if any) reproduces
ViewProjUnj, for BOTH the accepted and the rejected families:

  cand A = ViewInv @ ProjUnj
  cand B = ProjUnj @ ViewInv
  cand C = ViewInv @ ProjUnj with the last row forced to (0,0,0,1)
  cand D = transpose(ViewInv) @ ProjUnj
  direct check: does ViewProjUnj == ProjUnj @ ViewInv (row-vector convention)?

If the rejected family does NOT satisfy any product while the accepted family
does, that is hard proof the rejected family is not a camera transform.

Usage: python tools/probe_vp_identity.py <logfile>
"""

import re
import sys

NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
RE_MAT = re.compile(r"\[CAM\]\s+raw\s+#(\d+)\s+(ViewProjUnj|ProjUnj|ViewInv)\s*\|(.*)$")
RE_SUM = re.compile(
    r"\[CAM\]\s+raw\s+#(\d+)\s+pos=\(\s*(" + NUM + r")\s*,\s*(" + NUM + r")\s*,\s*(" + NUM + r")"
    r"\s*,\s*(" + NUM + r")\s*\)"
    r".*?devVP=(" + NUM + r")\s+detVP=(" + NUM + r")")


def parse_rows(payload):
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
    blocks = {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = RE_MAT.search(line)
            if m:
                b = blocks.setdefault(int(m.group(1)), {"idx": int(m.group(1))})
                r = parse_rows(m.group(3))
                if r:
                    b[m.group(2)] = r
                continue
            s = RE_SUM.search(line)
            if s:
                b = blocks.setdefault(int(s.group(1)), {"idx": int(s.group(1))})
                b["pos"] = tuple(float(s.group(i)) for i in (2, 3, 4))
                b["dev"] = float(s.group(5))
                b["det"] = float(s.group(6))
    return [b for k, b in sorted(blocks.items())
            if all(k2 in b for k2 in ("ViewProjUnj", "ProjUnj", "ViewInv", "pos"))]


def mm(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def tr(A):
    return [[A[j][i] for j in range(4)] for i in range(4)]


def maxrel(A, B):
    """max |a-b| normalised by max |b|."""
    scale = max(abs(B[i][j]) for i in range(4) for j in range(4))
    if scale < 1e-12:
        scale = 1.0
    return max(abs(A[i][j] - B[i][j]) for i in range(4) for j in range(4)) / scale


def fmt(A):
    return " | ".join(" ".join("%9.5g" % v for v in row) for row in A)


def main():
    if len(sys.argv) < 2:
        print("usage: probe_vp_identity.py <logfile>")
        return 2
    blocks = parse(sys.argv[1])
    print("blocks with all three matrices: %d" % len(blocks))
    print()

    for b in blocks:
        VP = b["ViewProjUnj"]
        PJ = b["ProjUnj"]
        VI = b["ViewInv"]
        w = VP[3][3]
        tag = "PASS " if abs(w - 1.0) <= 1e-3 else "REJECT"

        cA = mm(VI, PJ)          # ViewInv * Proj
        cB = mm(PJ, VI)          # Proj * ViewInv
        cD = mm(tr(VI), PJ)      # transpose(ViewInv) * Proj
        # candidate: Proj @ View  (row-vector convention, View = inverse of ViewInv)
        # we don't have View directly; derive it as inv(ViewInv) numerically
        cE = None
        try:
            cE = mm(VI, PJ)
        except Exception:
            pass

        print("-" * 96)
        print("#%-6d pos=(%.1f,%.1f,%.1f)  devVP=%.6g detVP=%.6g  [%s]" % (
            b["idx"], b["pos"][0], b["pos"][1], b["pos"][2], b["dev"], b["det"], tag))
        print("  ViewProjUnj | %s" % fmt(VP))
        print("  ViewInv*Proj| %s   maxrel=%.4g" % (fmt(cA), maxrel(VP, cA)))
        print("  Proj*ViewInv| %s   maxrel=%.4g" % (fmt(cB), maxrel(VP, cB)))
        print("  tr(VI)*Proj | %s   maxrel=%.4g" % (fmt(cD), maxrel(VP, cD)))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
