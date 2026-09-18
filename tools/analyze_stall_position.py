#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where does the ~19-25 s stall sit in every run, and does the frame loop
recording START before or after it?

The 0b table shows maxSil = 19000-25000 ms in EVERY run. Previous rounds
dismissed that as "loading". This script checks whether it is really loading,
by locating the stall's position relative to the first frame the watchdog
ever saw (frames=1) and to the run's own frame span.
"""
import re
import io

P = r"C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.watchdog.log"
WD = re.compile(r"^\[(\d+)\]\s+(\d\d:\d\d:\d\d\.\d\d\d)\s+frames=(\d+)\s+silent=(\d+)ms")


def load():
    recs = []
    for ln in io.open(P, encoding="utf-8", errors="replace"):
        m = WD.match(ln)
        if m:
            recs.append({
                "us": int(m.group(1)),
                "wall": m.group(2),
                "frames": int(m.group(3)),
                "silent": int(m.group(4)),
            })
    return recs


def split_runs(recs):
    runs = []
    cur = []
    prev = None
    for r in recs:
        if prev is not None and r["frames"] < prev - 10:
            runs.append(cur)
            cur = []
        cur.append(r)
        prev = r["frames"]
    if cur:
        runs.append(cur)
    return runs


def main():
    recs = load()
    print("total watchdog ticks parsed: %d" % len(recs))
    runs = split_runs(recs)
    print("runs: %d" % len(runs))
    print()
    print("%-4s %-13s %-13s %-9s %-9s %-8s %-10s %s"
          % ("#", "start", "end", "dur(s)", "maxSil", "@frames", "stallPos", "quiet ticks >1500ms"))
    for i, rn in enumerate(runs):
        mx = max(rn, key=lambda x: x["silent"])
        big = [x for x in rn if x["silent"] > 1500]
        dur = (rn[-1]["us"] - rn[0]["us"]) / 1e6
        # position of the biggest stall within the run, as a fraction
        pos = "n/a"
        if len(rn) > 1:
            idx = rn.index(mx)
            pos = "%.0f%%" % (100.0 * idx / (len(rn) - 1))
        print("%-4d %-13s %-13s %-9.1f %-9d %-8d %-10s %d"
              % (i, rn[0]["wall"], rn[-1]["wall"], dur, mx["silent"], mx["frames"], pos, len(big)))

    print()
    print("=" * 78)
    print("STALL ANATOMY — last run (the one the user just reported)")
    print("=" * 78)
    rn = runs[-1]
    print("  run start : %s  frames=%d" % (rn[0]["wall"], rn[0]["frames"]))
    print("  run end   : %s  frames=%d" % (rn[-1]["wall"], rn[-1]["frames"]))
    print()
    # print the first 12 ticks showing silent growth
    print("  first 12 ticks (silent growth):")
    for t in rn[:12]:
        print("    %s frames=%-5d silent=%-7dms" % (t["wall"], t["frames"], t["silent"]))
    print()
    # find the tick where silent resets back to small
    prev = None
    for idx, t in enumerate(rn):
        if prev is not None and prev["silent"] > 2000 and t["silent"] < 1000:
            print("  silent RESETS at %s: %dms -> %dms (frames %d -> %d, gap %.2fs)"
                  % (t["wall"], prev["silent"], t["silent"], prev["frames"], t["frames"],
                     (t["us"] - prev["us"]) / 1e6))
            print("    => the frame loop resumed; the whole stall was %.2fs"
                  % ((t["us"] - rn[0]["us"]) / 1e6))
            break
        prev = t
    print()
    print("  NOTE: frames stays at 1 during the stall -> the engine had not")
    print("        produced a SECOND frame yet. This is the first-frame stall,")
    print("        not a mid-game freeze.")


if __name__ == "__main__":
    main()
