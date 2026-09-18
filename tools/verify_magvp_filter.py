"""Verify: if we accept ONLY arrivals with magVP >= 3.0 (the world camera), does
every frame of the game get an accepted snapshot?

This is the make-or-break question for the v0.95 design. The v0.93 CTD came from
withholding snapshots that SHOULD have been published: SetMappedFrameBuffer()
only runs on accept, so a withheld frame leaves mappedFrameBuffer stale and
Present skips SetDLSSGOptions. If the magVP filter ever withholds a frame that
has no following world arrival, we reintroduce exactly that bug.

Method: replay every Unmap call in the log. For each call, count how many
members pass the filter. Report:
  - calls with 0 world members  (would starve -> dangerous)
  - calls with 1 world member   (perfect)
  - calls with >1 world member  (ambiguous)
  - the length of any consecutive run of worthless calls
"""
import re
import sys
from collections import Counter

LOG = r"C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.log"
TS = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\.(\d\d\d)\] \[(\d+)\]")
ACC = re.compile(r"accepting pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\) devVP=([\d.eE+-]+) magVP=([\d.eE+-]+)")
ACCN = re.compile(r"\[CAM\] acc #(\d+) pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\) move=([\d.]+) path=([\d.]+)")


def parse_ts(line):
    m = TS.match(line)
    if not m:
        return None
    h, mi, s, ms = (int(m.group(i)) for i in range(1, 5))
    return h * 3600.0 + mi * 60.0 + s + ms / 1000.0


def main():
    # An "accepted" arrival is one that PASSED the gate. In the 16:04 log the
    # gate was v0.93 (no vetoes) so every ACCEPTING line is really an arrival.
    arrivals = []
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            t = parse_ts(ln)
            if t is None:
                continue
            m = ACC.search(ln)
            if m:
                arrivals.append((t, float(m.group(4)), float(m.group(5)),
                                 (float(m.group(1)), float(m.group(2)), float(m.group(3)))))
                continue
            # acc # lines carry no magVP; they are the summary heartbeat, skip the
            # ones that duplicate an accepting line at the same timestamp.
            m = ACCN.search(ln)
            if m:
                pass

    print(f"accepting arrivals: {len(arrivals)}")

    # group into Unmap calls
    groups = []
    cur = [arrivals[0]]
    for it in arrivals[1:]:
        if abs(it[0] - cur[-1][0]) < 1e-9:
            cur.append(it)
        else:
            groups.append(cur)
            cur = [it]
    groups.append(cur)
    print(f"Unmap calls: {len(groups)}")

    for TH in (3.0, 5.0, 8.0):
        counts = Counter()
        for g in groups:
            n = sum(1 for it in g if it[2] >= TH)
            counts[min(n, 3)] += 1
        starve = counts[0]
        print(f"\n=== threshold magVP >= {TH} ===")
        print(f"  calls with 0 world members (STARVE): {starve}")
        print(f"  calls with 1 world member          : {counts[1]}")
        print(f"  calls with >=2 world members       : {counts[2] + counts[3]}")

    # worst-case starvation run at threshold 3.0
    TH = 3.0
    seq = [1 if any(it[2] >= TH for it in g) else 0 for g in groups]
    runs = []
    n = 0
    for v in seq:
        if v == 0:
            n += 1
        else:
            if n:
                runs.append(n)
            n = 0
    if n:
        runs.append(n)
    print(f"\nstarvation runs at threshold 3.0: n={len(runs)} max={max(runs) if runs else 0}")
    print(f"  histogram: {sorted(Counter(runs).items())}")

    # time span covered by starvation runs
    if runs:
        # find positions of starve groups
        pos = [i for i, v in enumerate(seq) if v == 0]
        if pos:
            t_first, t_last = groups[pos[0]][0][0], groups[pos[-1]][0][0]
            print(f"  starve groups span {t_first:.3f} .. {t_last:.3f}")

    # Also: what did the accepted stream look like at the time of the crash?
    # The last 10 calls of the log:
    print("\nlast 12 Unmap calls:")
    for g in groups[-12:]:
        parts = [f"mag={it[2]:.5g} pos=({it[3][0]:.0f},{it[3][1]:.0f},{it[3][2]:.0f})"
                 for it in g]
        print(f"  t={g[0][0]:.3f} n={len(g)}: " + " | ".join(parts))


if __name__ == "__main__":
    sys.exit(main())
