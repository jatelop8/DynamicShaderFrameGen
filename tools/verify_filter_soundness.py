"""CRITICAL CHECK before trusting the magVP filter.

The filter passes EVERYTHING with magVP >= 3.0.  If more than one distinct
position carries magVP >= 3.0, the filter does not isolate a single source and
the every-frame camera switch (the v0.93 CTD) comes back.

The log shows two positions that could both be world cameras:
    (-50, 600, 80)   551 times, magVP = 15.011, pos NEVER changes
    (-50, 900->894, 96)  the smoothly gliding one

Are those two different sources, or the SAME source at different times?
The answer decides whether "magVP >= 3.0" is sufficient.

Method: reconstruct the accepted stream that the filter WOULD produce, then
measure its continuity.  If the constant and the glider alternate, the filter
fails (max step will be hundreds).  If the constant simply precedes the glider
in time and they never interleave, the filter is sound.
"""
import re
import sys
from collections import Counter

LOG = r"C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.log"
TS = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\.(\d\d\d)\] \[(\d+)\]")
ACC = re.compile(r"accepting pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\) devVP=([\d.eE+-]+) magVP=([\d.eE+-]+)")


def parse_ts(line):
    m = TS.match(line)
    if not m:
        return None
    h, mi, s, ms = (int(m.group(i)) for i in range(1, 5))
    return h * 3600.0 + mi * 60.0 + s + ms / 1000.0


def main():
    arr = []
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            t = parse_ts(ln)
            if t is None:
                continue
            m = ACC.search(ln)
            if m:
                arr.append((t, (float(m.group(1)), float(m.group(2)), float(m.group(3))),
                            float(m.group(4)), float(m.group(5)), ln))

    # group into Unmap calls
    groups = []
    cur = [arr[0]]
    for it in arr[1:]:
        if abs(it[0] - cur[-1][0]) < 1e-9:
            cur.append(it)
        else:
            groups.append(cur)
            cur = [it]
    groups.append(cur)

    # what the filter would publish: every member with magVP >= 3
    # tuple layout: (t, pos, devVP, magVP, raw_line)
    published = []
    for g in groups:
        for it in g:
            if it[3] >= 3.0:
                published.append(it)

    print(f"published by filter: {len(published)}")

    # distinct published positions, ordered by first appearance
    seen = {}
    order = []
    for it in published:
        k = (round(it[1][0]), round(it[1][1]), round(it[1][2]))
        if k not in seen:
            seen[k] = (it[0], 0)
            order.append(k)
        seen[k] = (seen[k][0], seen[k][1] + 1)

    print(f"distinct published positions: {len(seen)}")
    print("\nfirst 20 distinct, by first-seen time:")
    for k in order[:20]:
        t0, n = seen[k]
        print(f"  t={t0:.3f}  {k}  x{n}")

    # THE DECISIVE TEST: continuity of the published stream
    steps = []
    for a, b in zip(published, published[1:]):
        d = sum((a[1][i] - b[1][i]) ** 2 for i in range(3)) ** 0.5
        steps.append((d, a, b))
    if steps:
        dvals = sorted(s[0] for s in steps)
        print(f"\npublished-stream step: n={len(dvals)} median={dvals[len(dvals)//2]:.3f} "
              f"p90={dvals[int(len(dvals)*0.9)]:.3f} max={dvals[-1]:.3f}")
        big = [(d, a, b) for d, a, b in steps if d > 50]
        print(f"  steps > 50 units: {len(big)} / {len(steps)}")
        print("\n  WORST 10 transitions:")
        for d, a, b in sorted(steps, reverse=True)[:10]:
            print(f"    step={d:8.2f}  ({a[1][0]:.0f},{a[1][1]:.0f},{a[1][2]:.0f})"
                  f"  ->  ({b[1][0]:.0f},{b[1][1]:.0f},{b[1][2]:.0f})")

    # is the constant ever interleaved with a DIFFERENT position?
    const = (-50, 600, 80)
    approx = [(-50, 900, 96), (-50, 898, 96), (-50, 880, 94)]
    seq = []
    for it in published:
        k = (round(it[1][0]), round(it[1][1]), round(it[1][2]))
        seq.append("C" if k == const else "G")
    s = "".join(seq)
    print(f"\npublished sequence (C=const -50,600,80 ; G=anything else), first 200:")
    print("  " + s[:200])
    runs = Counter()
    cur = None
    n = 0
    for ch in s:
        if ch == cur:
            n += 1
        else:
            if cur is not None:
                runs[(cur, n)] += 1
            cur = ch
            n = 1
    if cur is not None:
        runs[(cur, n)] += 1
    print(f"  run histogram: {sorted(runs.items())[:14]}")
    print(f"  C count={s.count('C')}  G count={s.count('G')}")


if __name__ == "__main__":
    sys.exit(main())
