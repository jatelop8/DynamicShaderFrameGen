"""Find the MOST ROBUST discriminator, ranked by semantic-independence.

The devVP=1.11111 cluster is safe in THIS log, but it is a magic number.  A
better rule rests on a property that must hold for any non-world camera:

  1. The world camera's view-projection must contain a TRANSLATION of the world
     origin -- the player is at (-50,600,80)-ish, far from origin.  Its matrix
     magnitude is large (magVP=15.011).
  2. A UI/menu camera that renders a flat 2D overlay operates near the origin,
     so its matrix magnitude is small (magVP=1.11111 ~ identity).

Also test the cleanest one: the pair members differ in devVP AND magVP by the
same factor, so `magVP` alone separates them.

Finally, the strongest structural rule: the menu pass is the FIRST of the two
writes and the world pass is the SECOND (pattern "MW" 768/769).  Order is a
property of the engine's draw sequence, not of any value -- so it cannot be
broken by an unusual scene.  Test how reliable order alone is.
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
                            float(m.group(4)), float(m.group(5))))

    print(f"arrivals with both devVP and magVP: {len(arr)}")

    # 1) do devVP and magVP agree on the classification?
    disagree = 0
    for t, p, dev, mag in arr:
        a = dev < 3.0
        b = mag < 3.0
        if a != b:
            disagree += 1
    print(f"devVP<3 vs magVP<3 disagreements: {disagree}")

    # 2) magVP histogram
    print("\nmagVP histogram:")
    b = Counter()
    for t, p, dev, mag in arr:
        for lo, name in [(0, "<0.5"), (0.5, "0.5-0.9"), (0.9, "0.9-1.05"),
                         (1.05, "1.05-1.5"), (1.5, "1.5-3.0"), (3.0, "3.0-8.0"),
                         (8.0, "8.0-20.0"), (20.0, ">=20")]:
            pass
    for t, p, dev, mag in arr:
        if mag < 0.5:
            b["<0.5"] += 1
        elif mag < 0.9:
            b["0.5-0.9"] += 1
        elif mag < 1.05:
            b["0.9-1.05"] += 1
        elif mag < 1.5:
            b["1.05-1.5"] += 1
        elif mag < 3.0:
            b["1.5-3.0"] += 1
        elif mag < 8.0:
            b["3.0-8.0"] += 1
        elif mag < 20.0:
            b["8.0-20.0"] += 1
        else:
            b[">=20"] += 1
    for k in ["<0.5", "0.5-0.9", "0.9-1.05", "1.05-1.5", "1.5-3.0", "3.0-8.0", "8.0-20.0", ">=20"]:
        print(f"  {k:10s}: {b.get(k,0)}")

    # 3) ORDER rule: within one Unmap call, is the world camera always LAST?
    groups = []
    cur = [arr[0]]
    for it in arr[1:]:
        if abs(it[0] - cur[-1][0]) < 1e-9:
            cur.append(it)
        else:
            groups.append(cur)
            cur = [it]
    groups.append(cur)

    def is_world(it):
        # tuple is (t, pos, devVP, magVP)
        return it[3] >= 3.0

    two = [g for g in groups if len(g) == 2]
    mw = sum(1 for g in two if (not is_world(g[0])) and is_world(g[1]))
    wm = sum(1 for g in two if is_world(g[0]) and (not is_world(g[1])))
    print(f"\nORDER rule on {len(two)} two-member calls:")
    print(f"  menu-first / world-second : {mw}")
    print(f"  world-first / menu-second : {wm}")
    print(f"  -> order alone is {'RELIABLE' if wm <= 1 else 'NOT reliable'}")

    # 4) single-member calls -- what were they?
    singles = [g[0] for g in groups if len(g) == 1]
    sc = Counter("world" if is_world(i) else "menu" for i in singles)
    print(f"\nsingle-member calls: {len(singles)}  {dict(sc)}")
    # were the singles interleaved with pairs?
    seq = []
    for g in groups:
        if len(g) == 1:
            seq.append("S" if is_world(g[0]) else "s")
        else:
            seq.append("P")
    print(f"  sequence sample (P=pair, S=world-single, s=menu-single): {''.join(seq[:80])}")

    # 5) is the world camera's POSITION the same in consecutive pairs?
    wp = [i for g in groups for i in g if is_world(i)]
    same = 0
    diff = 0
    for a, bb in zip(wp, wp[1:]):
        if a[1] == bb[1]:
            same += 1
        else:
            diff += 1
    print(f"\nworld positions: identical-consecutive={same} changed={diff}")
    print("  (the constant (-50,600,80) repeated 551x means the player was")
    print("   standing still during most of the log -- a menu/loading scene)")


if __name__ == "__main__":
    sys.exit(main())
