#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-analyse the msg=0 ticks in the DFG watchdog log.

Goal: answer "who is blocking the window message thread?"
by mapping every msg=0 tick onto:
  - wall-clock time (are they clustered in bursts, or scattered?)
  - stage=            (d3d11 Wait / dxgi Present / other -> which pin the stall sits in)
  - focus=            (is the window blurred at the time?)
  - menu=/world=       (main log; is it a loading screen / menu transition?)
  - frames / silent   (render thread health at that instant)

Run:  python tools/analyze_msg0.py
"""
import re
import os
import sys
from collections import Counter, defaultdict

WATCHDOG = r"C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.watchdog.log"
MAINLOG = r"C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.log"

# [124045299] 08:29:09.722 frames=4314 silent=4ms stage=d3d11 Wait focus=1 fence=8616/8616 stim=477 queued=1 lastPr=4729 dsync=0 msg=1 alive=1
WD_RE = re.compile(
    r"^\[(?P<us>\d+)\]\s+(?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})\.(?P<ms>\d{3})\s+"
    r"frames=(?P<frames>\d+)\s+silent=(?P<silent>\d+)ms\s+stage=(?P<stage>.+?)\s+"
    r"focus=(?P<focus>\d+)\s+fence=(?P<fence>\d+)/(?P<fence2>\d+)\s+stim=(?P<stim>\d+)"
    r"(?:\s+queued=(?P<queued>\d+)\s+lastPr=(?P<lastPr>\d+)\s+dsync=(?P<dsync>\d+))?"
    r"(?:\s+msg=(?P<msg>\d+)\s+alive=(?P<alive>\d+))?\s*$"
)


def _secs(hh, mm, ss, ms):
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def parse_wd(path):
    recs = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            m = WD_RE.match(ln.rstrip("\r\n"))
            if not m:
                continue
            d = m.groupdict()
            r = {
                "us": int(d["us"]),
                "t": _secs(d["hh"], d["mm"], d["ss"], d["ms"]),
                "clock": "%s:%s:%s.%s" % (d["hh"], d["mm"], d["ss"], d["ms"]),
                "frames": int(d["frames"]),
                "silent": int(d["silent"]),
                "stage": d["stage"].strip(),
                "focus": int(d["focus"]),
                "fence": int(d["fence"]),
                "stim": int(d["stim"]),
                "queued": int(d["queued"]) if d["queued"] else None,
                "lastPr": int(d["lastPr"]) if d["lastPr"] else None,
                "dsync": int(d["dsync"]) if d["dsync"] else None,
                "msg": int(d["msg"]) if d["msg"] is not None else None,
                "alive": int(d["alive"]) if d["alive"] is not None else None,
            }
            recs.append(r)
    return recs


def split_runs(recs):
    """A new run starts whenever the frame counter goes backwards."""
    runs = []
    cur = []
    prev = None
    for r in recs:
        if prev is not None and r["frames"] < prev:
            runs.append(cur)
            cur = []
        cur.append(r)
        prev = r["frames"]
    if cur:
        runs.append(cur)
    return runs


def fmt(ts):
    h = int(ts // 3600)
    m = int((ts % 3600) // 60)
    s = ts % 60
    return "%02d:%02d:%06.3f" % (h, m, s)


def main():
    if not os.path.exists(WATCHDOG):
        print("MISSING watchdog: %s" % WATCHDOG)
        return 2
    recs = parse_wd(WATCHDOG)
    runs = split_runs(recs)
    print("watchdog lines parsed : %d" % len(recs))
    print("runs detected         : %d" % len(runs))
    for i, rn in enumerate(runs):
        msg_n = sum(1 for r in rn if r["msg"] == 0)
        span = rn[-1]["t"] - rn[0]["t"]
        print("  run #%-2d ticks=%-5d span=%6.1fs frames %d->%d  msg=0 x%d"
              % (i, len(rn), span, rn[0]["frames"], rn[-1]["frames"], msg_n))

    # focus on the last run (the v0.76 run)
    run = runs[-1]
    print()
    print("=" * 78)
    print("LAST RUN DETAIL  (%s .. %s)" % (run[0]["clock"], run[-1]["clock"]))
    print("=" * 78)

    bad = [r for r in run if r["msg"] == 0]
    if not bad:
        print("no msg=0 ticks in last run")
        return 0

    # ---- 1. burst structure: consecutive msg=0 runs, separated by msg=1 ----
    print()
    print("[1] Burst structure (msg=0 = window not answering WM_NULL)")
    bursts = []
    cur = [bad[0]]
    for r in bad[1:]:
        if r["stim"] - cur[-1]["stim"] <= 5:      # watchdog probes every 5 ticks
            cur.append(r)
        else:
            bursts.append(cur)
            cur = [r]
    bursts.append(cur)
    print("    total msg=0 ticks : %d" % len(bad))
    print("    number of bursts  : %d" % len(bursts))
    print("    longest burst     : %d probes" % max(len(b) for b in bursts))
    print()
    print("    %-4s %-14s %-14s %-6s %-7s %-9s %s"
          % ("#", "start", "end", "probes", "dur(s)", "frames", "stage(modal)"))
    for i, b in enumerate(bursts):
        st = Counter(x["stage"] for x in b).most_common(1)[0][0]
        print("    %-4d %-14s %-14s %-6d %-7.2f %-9s %s"
              % (i, b[0]["clock"], b[-1]["clock"], len(b),
                 b[-1]["t"] - b[0]["t"],
                 "%d->%d" % (b[0]["frames"], b[-1]["frames"]), st))

    # ---- 2. stage distribution ----
    print()
    print("[2] stage=<x> distribution  (msg=0 vs msg=1 vs all)")
    allc = Counter(r["stage"] for r in run)
    okc = Counter(r["stage"] for r in run if r["msg"] == 1)
    print("    %-24s %8s %8s %8s" % ("stage", "msg=0", "msg=1", "all"))
    for st, n in allc.most_common():
        print("    %-24s %8d %8d %8d" % (st, Counter(x["stage"] for x in bad)[st], okc[st], n))

    # ---- 3. focus / alive ----
    print()
    print("[3] focus / alive cross-tab")
    print("    focus=1 : %d" % sum(1 for r in bad if r["focus"] == 1))
    print("    focus=0 : %d" % sum(1 for r in bad if r["focus"] == 0))
    print("    alive=1 : %d" % sum(1 for r in bad if r["alive"] == 1))
    print("    alive=0 : %d" % sum(1 for r in bad if r["alive"] == 0))

    # ---- 4. silent distribution during msg=0 ----
    print()
    print("[4] silent  (render-thread heartbeat gap) during msg=0")
    buckets = [(0, 10), (10, 30), (30, 100), (100, 500), (500, 1500), (1500, 10 ** 9)]
    for lo, hi in buckets:
        n = sum(1 for r in bad if lo <= r["silent"] < hi)
        if hi > 10 ** 8:
            lab = ">=%dms" % lo
        else:
            lab = "%d-%dms" % (lo, hi)
        print("    %-12s %5d   %s" % (lab, n, "#" * min(60, n)))
    mx = max(bad, key=lambda r: r["silent"])
    print("    max silent during msg=0 : %dms @ %s" % (mx["silent"], mx["clock"]))

    # ---- 5. relation to frames / probe cadence ----
    print()
    print("[5] msg=0 vs probe cadence")
    d = [bad[i + 1]["stim"] - bad[i]["stim"] for i in range(len(bad) - 1)]
    gap5 = sum(1 for x in d if x == 5)
    print("    consecutive probe gaps == 5 (i.e. two msg=0 back to back): %d/%d" % (gap5, len(d)))
    print("    probe gap histogram (top 8): %s"
          % Counter(d).most_common(8))

    # ---- 6. does the render thread keep advancing during msg=0? ----
    print()
    print("[6] render-thread progress during msg=0")
    fps_all = (run[-1]["frames"] - run[0]["frames"]) / max(0.001, run[-1]["t"] - run[0]["t"])
    f0, f1 = bad[0]["frames"], bad[-1]["frames"]
    t0, t1 = bad[0]["t"], bad[-1]["t"]
    print("    overall    : %d frames in %.1fs = %.1f fps" % (run[-1]["frames"] - run[0]["frames"],
                                                              run[-1]["t"] - run[0]["t"], fps_all))
    print("    msg=0 span : %d frames in %.1fs = %.1f fps" % (f1 - f0, t1 - t0, (f1 - f0) / max(0.001, t1 - t0)))
    print("    fence      : %d -> %d  (monotonic: %s)"
          % (bad[0]["fence"], bad[-1]["fence"], bad[-1]["fence"] > bad[0]["fence"]))
    print("    lastPr     : %s -> %s" % (bad[0]["lastPr"], bad[-1]["lastPr"]))
    ds = set(r["dsync"] for r in bad if r["dsync"] is not None)
    print("    dsync      : %s  (0 = frameIndex matches DXGI == healthy)" % (sorted(ds) or "n/a"))

    # ---- 7. first / last ----
    print()
    print("[7] first / last msg=0")
    for tag, r in (("first", bad[0]), ("last", bad[-1])):
        print("    %-5s %s frames=%d silent=%dms stage=%s focus=%d fence=%d stim=%d"
              % (tag, r["clock"], r["frames"], r["silent"], r["stage"], r["focus"],
                 r["fence"], r["stim"]))

    # ---- 8. mega-gap: what happened in the biggest silent? ----
    print()
    print("[8] top-5 largest silent in the whole run")
    for r in sorted(run, key=lambda x: -x["silent"])[:5]:
        print("    %s frames=%-5d silent=%-6dms stage=%-14s msg=%s alive=%s fence=%d"
              % (r["clock"], r["frames"], r["silent"], r["stage"], r["msg"], r["alive"], r["fence"]))

    return 0


if __name__ == "__main__":
    sys.exit(main())
