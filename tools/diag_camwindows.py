#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_camwindows.py -- cross-reference clipDevMax per heartbeat window against
whether the ACCEPTED camera actually moved inside that same window.

Why this exists
---------------
clipDevMax == 0 means "clipToPrevClip == identity".  That is the CORRECT answer
when the camera is static, and a BUG when the camera moved.  The plugin resets
clipDevMax every heartbeat, so the only way to tell the two apart is to compare
each heartbeat window's clipDevMax against the movement of the accepted camera
in that same window.  Comparing against the *cumulative* snapPathLen mixes a
whole-run total with a single window and yields a false "camera moved but the
matrix is identity" conclusion.

Usage:
    python diag_camwindows.py <DynamicShaderFrameGen.log>
"""

import re
import sys

RE_TS = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]")
RE_POS = re.compile(r"\[CAM\] acc .*pos=\(([-\d.eE+]+),([-\d.eE+]+),([-\d.eE+]+)\)")


def field(line, name):
    m = re.search(re.escape(name) + r"=([-\d.eE+]+)", line)
    return m.group(1) if m else None


def load(path):
    """-> (heartbeats[(line_idx, cdm, ts)], accepted[(line_idx, x, y, z, ts)])"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    hbs, acc = [], []
    for i, ln in enumerate(lines):
        ts_m = RE_TS.search(ln)
        ts = ts_m.group(1) if ts_m else ""
        if "[XRAY] serial" in ln:
            # hist(hit/miss)=a/b -- how many frames in this window actually had a
            # previous matrix. 0 hits means the reprojection path had no sample at
            # all, so clipDevMax=0 says nothing about the matrix being right or
            # wrong. Without this the very first window (which spans the whole
            # pre-EvaluateDLSSG startup, serial 1..670) always looks like
            # "camera moved but the matrix is identity" - a pure artefact.
            hm = re.search(r"hist\(hit/miss\)=(\d+)/(\d+)", ln)
            hits = int(hm.group(1)) if hm else -1
            hbs.append((i, field(ln, "clipDevMax"), ts, hits))
        m = RE_POS.search(ln)
        if m:
            acc.append((i, float(m.group(1)), float(m.group(2)), float(m.group(3)), ts))
    return hbs, acc


def main():
    if len(sys.argv) < 2:
        print("usage: diag_camwindows.py <log>")
        return 2
    hbs, acc = load(sys.argv[1])
    if not hbs:
        print("no [XRAY] serial heartbeats found")
        return 1

    print("=" * 104)
    print("clipDevMax 逐窗口  vs  同窗口内被接受相机的真实位移")
    print("=" * 104)
    print("窗口  行号     clipDevMax  hist命中  acc条  首末位移  步数>0.5  最大单步  性质   判定")
    print("-" * 104)

    zero_while_moving = 0
    nonzero_while_moving = 0
    skipped = 0
    prev = -1
    for n, (i, cdm, ts, hits) in enumerate(hbs):
        win = [a for a in acc if prev < a[0] <= i]
        prev = i
        steps = []
        for k in range(1, len(win)):
            steps.append(sum((win[k][j] - win[k - 1][j]) ** 2 for j in (1, 2, 3)) ** 0.5)
        span = 0.0
        if len(win) >= 2:
            span = sum((win[-1][j] - win[0][j]) ** 2 for j in (1, 2, 3)) ** 0.5
        big = [s for s in steps if s > 0.5]
        biggest = max(steps) if steps else 0.0
        # A single step carrying (almost) the whole span is a TELEPORT (a camera
        # switch / load transition), not motion. Only continuous motion is a valid
        # premise for "clipDevMax must be > 0". This distinction is the whole point
        # of the tool: without it, a load transition reads as a moving camera and
        # produces a false "the matrix is identity while the camera moved" verdict.
        if span > 0.5 and len(big) <= 1:
            nature = "跳变"
        elif span > 0.5:
            nature = "连续"
        else:
            nature = "静止"
        try:
            cdm_f = float(cdm)
        except (TypeError, ValueError):
            cdm_f = -1.0

        if hits == 0:
            # No reprojection sample in this window: clipDevMax says nothing. The
            # first window spans the whole pre-EvaluateDLSSG startup (serial 1..670)
            # and would otherwise always be reported as a "BUG" - an artefact, not
            # a defect. Require the premise before drawing the conclusion.
            verdict = "无采样（仪表未启动）→ 不可判定"
            nature = "-"
            skipped += 1
        elif nature == "连续" and cdm_f == 0.0:
            verdict = "!! 相机连续运动而矩阵是单位矩阵 = BUG"
            zero_while_moving += 1
        elif nature == "连续" and cdm_f > 0.0:
            verdict = "OK 相机在动，矩阵带运动"
            nonzero_while_moving += 1
        elif nature == "跳变":
            verdict = "跳变（加载/换相机）—— 不能作为判据前提"
        elif cdm_f == 0.0:
            verdict = "静止 + 单位矩阵 = 正确"
        else:
            verdict = "静止但有非零值"
        print("%4d  %6d  %10s  %8s  %6d  %9.2f  %8d  %8.2f  %-6s  %s"
              % (n + 1, i + 1, cdm, hits if hits >= 0 else "-", len(win), span,
                 len(big), biggest, nature, verdict))

    print("-" * 104)
    if skipped:
        print("[信息] %d 个窗口因为 hist(hit/miss) 命中为 0 被跳过 —— 那段时间重投影路径"
              "没有任何样本，clipDevMax=0 说明不了任何事。" % skipped)
    if zero_while_moving:
        print("[严重] %d 个窗口：被接受的相机**连续**移动，但交出的重投影矩阵是单位矩阵。" % zero_while_moving)
        print("       这**就是**闪的成因：DLSS-G 被告知相机没动，却收到动过的历史。")
    elif nonzero_while_moving:
        print("[好] 每个「相机连续在动」的窗口 clipDevMax 都 > 0 —— 重投影确实带相机运动。")
        print("     那么闪的成因不在相机项，要在 NR / 帧生成的时序一侧找。")
    else:
        print("[信息] 没有任何窗口同时满足「相机连续运动」+「有采样」—— 相机项仍未判定。")
        print("       验收必须进世界**持续走动** 20 秒（不是站着），否则这一项永远未采样。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
