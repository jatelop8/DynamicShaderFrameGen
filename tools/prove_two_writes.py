"""Prove the 'two writes per frame' hypothesis.

The v0.94 evidence shows:
  - arrivals come in PAIRS with dt = 0.0 ms (inside one Unmap call)
  - the two members of a pair are always (-160,160,128) and a world camera
  - cadence per position is 17 ms (i.e. ~58 fps), NOT 8.5 ms

If the perFrame buffer is written twice per frame (menu background camera +
world camera), then the correct unit of analysis is the FRAME, not the arrival,
and the correct rule is "pick one of the two slots deterministically", not
"pick whoever is continuous".

This script tests that by:
  1. grouping arrivals into 'Unmap calls' (dt == 0 -> same call)
  2. checking whether every group has exactly 2 members with the same tag pair
  3. computing, per frame, the ORDER of the pair members
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
                x, y, z = float(m.group(1)), float(m.group(2)), float(m.group(3))
                arr.append((t, (x, y, z), m.group(4)))

    print(f"arrivals: {len(arr)}")

    # group by identical timestamp -> one Unmap call
    groups = []
    cur = [arr[0]]
    for item in arr[1:]:
        if abs(item[0] - cur[-1][0]) < 1e-9:
            cur.append(item)
        else:
            groups.append(cur)
            cur = [item]
    groups.append(cur)

    print(f"Unmap-call groups: {len(groups)}")
    gc = Counter(len(g) for g in groups)
    print(f"group sizes: {sorted(gc.items())}")

    # classify each member as MENU (devVP ~ 1.11111) or WORLD (devVP > 5)
    def cls(item):
        dev = float(item[2])
        return "MENU" if dev < 3.0 else "WORLD"

    pats = Counter()
    for g in groups:
        s = "".join(cls(i)[0] for i in g)
        pats[s] += 1
    print(f"\nper-call member pattern (M=MENU bg cam, W=world cam):")
    for k, v in pats.most_common(15):
        print(f"  {k}: {v}")

    # full sequences of length 2 only
    two = [g for g in groups if len(g) == 2]
    print(f"\ngroups of exactly 2: {len(two)}")
    p2 = Counter("".join(cls(i)[0] for i in g) for g in two)
    print(f"  pattern: {sorted(p2.items())}")

    # is MENU always the same constant?
    menu_pos = Counter()
    world_pos = Counter()
    for g in groups:
        for i in g:
            if cls(i) == "MENU":
                menu_pos[(round(i[1][0]), round(i[1][1]), round(i[1][2]))] += 1
            else:
                world_pos[(round(i[1][0]), round(i[1][1]), round(i[1][2]))] += 1
    print(f"\nMENU-class distinct positions: {len(menu_pos)}  top: {menu_pos.most_common(5)}")
    print(f"WORLD-class distinct positions: {len(world_pos)}  top: {world_pos.most_common(5)}")

    # world-camera continuity: consecutive WORLD arrivals across frames
    world_ts = [i for g in groups for i in g if cls(i) == "WORLD"]
    print(f"\nWORLD arrivals in order: {len(world_ts)}")
    steps = []
    for a, b in zip(world_ts, world_ts[1:]):
        d = sum((a[1][k] - b[1][k]) ** 2 for k in range(3)) ** 0.5
        steps.append(d)
    if steps:
        st = sorted(steps)
        print(f"  WORLD->WORLD step: n={len(st)} median={st[len(st)//2]:.3f} "
              f"p90={st[int(len(st)*0.9)]:.3f} max={st[-1]:.3f}")
        big = [s for s in steps if s > 50]
        print(f"  steps > 50 units: {len(big)} / {len(steps)}")
        big2 = [s for s in steps if s > 5]
        print(f"  steps >  5 units: {len(big2)} / {len(steps)}")

    # with dt filter: only WORLD arrivals that are >5ms after previous WORLD
    print("\nWORLD arrivals with own-cadence filter (dt>5ms):")
    wf = [i for i in world_ts]
    filt = []
    for i in wf:
        if not filt or (i[0] - filt[-1][0]) > 0.005:
            filt.append(i)
    steps2 = []
    for a, b in zip(filt, filt[1:]):
        d = sum((a[1][k] - b[1][k]) ** 2 for k in range(3)) ** 0.5
        steps2.append(d)
    if steps2:
        st = sorted(steps2)
        print(f"  filtered n={len(filt)} steps n={len(st)} median={st[len(st)//2]:.3f} "
              f"max={st[-1]:.3f}  >50: {len([s for s in steps2 if s>50])}")


if __name__ == "__main__":
    sys.exit(main())
