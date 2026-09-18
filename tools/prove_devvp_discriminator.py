"""Is devVP a SAFE discriminator between the menu background camera and the
world camera?  Test it against every arrival in the log, including the hostile
tail where the game transitions (scene change, loading, unit-vector matrix).

Danger to rule out: the world camera itself could legitimately have a small
devVP (e.g. a perfect identity-ish view-projection early in load, or in a
menu-heavy scene).  If so, devVP would classify the real camera as menu and we
would publish the wrong one forever.

Also checks the 4 "other" MENU-class positions seen once each
(-1101,881,114) / (-694,528,111) / (-952,886,103) / (-126,211,189): are they
really menu, or world cameras that devVP misclassified?
"""
import re
import sys
from collections import Counter, defaultdict

LOG = r"C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.log"
TS = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\.(\d\d\d)\] \[(\d+)\]")
ACC = re.compile(r"accepting pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\) devVP=([\d.eE+-]+) magVP=([\d.eE+-]+)")
ACCN = re.compile(r"\[CAM\] acc #(\d+) pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\) move=([\d.]+) path=([\d.]+) devVP=([\d.eE+-]+)")


def parse_ts(line):
    m = TS.match(line)
    if not m:
        return None
    h, mi, s, ms = (int(m.group(i)) for i in range(1, 5))
    return h * 3600.0 + mi * 60.0 + s + ms / 1000.0


def main():
    devs = []
    rows = []
    with open(LOG, "r", encoding="utf-8", errors="replace") as f:
        for ln in f:
            t = parse_ts(ln)
            if t is None:
                continue
            m = ACC.search(ln)
            if m:
                x, y, z = float(m.group(1)), float(m.group(2)), float(m.group(3))
                dev = float(m.group(4))
                devs.append(dev)
                rows.append((t, (x, y, z), dev))
            m = ACCN.search(ln)
            if m:
                dev = float(m.group(6))
                devs.append(dev)

    print(f"total devVP samples: {len(devs)}")
    dv = sorted(devs)
    print(f"min={dv[0]:.6g}  p1={dv[len(dv)//100]:.6g}  median={dv[len(dv)//2]:.6g} "
          f" p99={dv[int(len(dv)*0.99)]:.6g}  max={dv[-1]:.6g}")

    # histogram of the LOW end -- this is the discriminating region
    print("\nlow-end histogram (the discriminating region):")
    buckets = Counter()
    for d in devs:
        if d < 0.5:
            buckets["<0.5"] += 1
        elif d < 0.9:
            buckets["0.5-0.9"] += 1
        elif d < 1.05:
            buckets["0.9-1.05"] += 1
        elif d < 1.5:
            buckets["1.05-1.5"] += 1
        elif d < 3.0:
            buckets["1.5-3.0"] += 1
        elif d < 8.0:
            buckets["3.0-8.0"] += 1
        elif d < 20.0:
            buckets["8.0-20.0"] += 1
        else:
            buckets[">=20"] += 1
    for k in ["<0.5", "0.5-0.9", "0.9-1.05", "1.05-1.5", "1.5-3.0", "3.0-8.0", "8.0-20.0", ">=20"]:
        print(f"  {k:10s}: {buckets.get(k,0)}")

    # the exact devVP values in the 1.0-1.5 window -- is it a single spike?
    spike = Counter()
    for d in devs:
        if 1.0 <= d < 1.5:
            spike[round(d, 5)] += 1
    print(f"\ndistinct devVP values in [1.0,1.5): {len(spike)}")
    for k, v in spike.most_common(10):
        print(f"  devVP={k}: {v}")

    # GAP CHECK: is there a clear valley between the spike and the world cluster?
    print("\n--- gap check ---")
    in_lo = [d for d in devs if 1.0 <= d < 1.5]
    in_mid = [d for d in devs if 1.5 <= d < 13.0]
    in_hi = [d for d in devs if d >= 13.0]
    print(f"  [1.0,1.5)  : {len(in_lo)}")
    print(f"  [1.5,13.0) : {len(in_mid)}   <-- VALLEY: if ~0, threshold is safe")
    print(f"  [13.0,inf) : {len(in_hi)}")
    if in_mid:
        print(f"  valley samples: {sorted(set(round(d,4) for d in in_mid))[:20]}")

    # the four one-off MENU positions -- what devVP did they carry?
    print("\n--- the odd one-off positions ---")
    odd = {(-1101, 881, 114), (-694, 528, 111), (-952, 886, 103), (-126, 211, 189), (0, 0, 1)}
    for t, p, dev in rows:
        k = (round(p[0]), round(p[1]), round(p[2]))
        if k in odd:
            print(f"  t={t:.3f} pos={k} devVP={dev}")

    # and the true moving world camera: what devVP range does IT use?
    print("\n--- moving world camera (pos changes) devVP range ---")
    move_devs = []
    prev = None
    for t, p, dev in rows:
        if prev is not None and sum((p[i]-prev[i])**2 for i in range(3)) > 0.5**2:
            move_devs.append(dev)
        prev = p
    if move_devs:
        mv = sorted(move_devs)
        print(f"  n={len(mv)} min={mv[0]:.6g} median={mv[len(mv)//2]:.6g} max={mv[-1]:.6g}")
        print(f"  of these, how many < 1.5? {len([d for d in mv if d < 1.5])}")


if __name__ == "__main__":
    sys.exit(main())
