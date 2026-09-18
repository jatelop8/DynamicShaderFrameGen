#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline replay of the v0.94 source lock against the REAL crash-log stream.

Feeds the positions actually observed in the 16:04 log through the same
algorithm the C++ now implements, and reports which source it locks onto and
how many arrivals it publishes. This answers, before deploying:

  1. does the lock hold ONE source (no interleaving)?
  2. does it pick the MOVING camera rather than a constant slot?
  3. is the emit rate high enough for DLSS-G (needs a camera most frames)?
"""
import io, re, math

LOG = "C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.log"
SRC = "C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen_prev.log"

kCamStepTol2 = 50.0 * 50.0
kCamStillTol = 90

# ---- recover the arrival stream in ORDER from the crash log --------------
text = io.open(LOG, encoding="utf-8", errors="replace").read()
arr = []   # (idx, x, y, z, kind)
for line in text.split("\n"):
    m = re.search(r"\[CAM\] #(\d+) (?:RELOCK after \d+ consecutive jumps \(teleport / scene change\) -> accepting|JUMP rejected:)\s*pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)", line)
    if m:
        arr.append((int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)), "gate"))
        continue
    m = re.search(r"\[CAM\] acc #(\d+) pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)", line)
    if m:
        arr.append((int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)), "acc"))
arr.sort(key=lambda r: r[0])
print("recovered arrivals:", len(arr))
if not arr:
    raise SystemExit("no arrivals parsed")

# ---- replay the v0.94 lock ----------------------------------------------
lock_have = False
have_last = False
last = (0.0, 0.0, 0.0)
still = 0
pub = hold = relock = 0
published = []
for idx, x, y, z, kind in arr:
    d2 = 0.0
    if have_last:
        dx, dy, dz = x - last[0], y - last[1], z - last[2]
        d2 = dx * dx + dy * dy + dz * dz
    if not lock_have:
        lock_have = True; still = 0
        if relock > 0 or pub > 0: relock += 1
        pub += 1
        have_last = True; last = (x, y, z); published.append((idx, x, y, z))
        continue
    if d2 > kCamStepTol2:
        hold += 1
        still += 1
        if still >= kCamStillTol:
            still = 0; relock += 1
            have_last = False
            pub += 1
            have_last = True; last = (x, y, z); published.append((idx, x, y, z))
        continue
    still = 0
    pub += 1
    have_last = True; last = (x, y, z); published.append((idx, x, y, z))

print()
print("RESULT of replay")
print("  published = %d / %d  (%.1f%%)" % (pub, len(arr), 100.0 * pub / len(arr)))
print("  held      = %d  (other source, withheld)" % hold)
print("  re-acquire= %d" % relock)

# ---- did it hold ONE source?  cluster published positions ----------------
from collections import Counter
def key(p):
    return (round(p[1]), round(p[2]), round(p[3]))
c = Counter(key(p) for p in published)
print()
print("  distinct published positions: %d" % len(c))
print("  top 6:")
for k, v in c.most_common(6):
    print("    %-28s x%d" % (str(k), v))

# ---- is the published stream CONTINUOUS?  (max step) --------------------
mx = 0.0
for a, b in zip(published, published[1:]):
    dx, dy, dz = a[1] - b[1], a[2] - b[2], a[3] - b[3]
    mx = max(mx, math.sqrt(dx * dx + dy * dy + dz * dz))
print()
print("  max consecutive step in published stream = %.2f units" % mx)
print("  (v0.93 published interleaved sources -> steps of hundreds; that was the CTD)")

# ---- compare against what v0.93 did --------------------------------------
print()
print("COMPARISON")
print("  v0.90 (distance gate, no release) : held ONE constant, rejected the mover")
print("  v0.93 (everything released)       : interleaved -> steps of 100s -> CTD")
print("  v0.94 (source lock)               : %d published, max step %.2f" % (pub, mx))
