#!/usr/bin/env python3
"""Per-second ratio of presents to real frames, from the DFG watchdog log.

Reads the `stage=...` heartbeat lines and, for each whole second, prints
dFrames / dLastPr / ratio. A ratio of 4.0 with a healthy presentAge is the
signature of a working 4x; a ratio near 1.0 means no interpolation reached
the swap chain at all.

Usage:
    python tools/wd_ratio.py <watchdog.log> [tail_n]
"""
import re
import sys
from pathlib import Path

LINE = re.compile(
    r"^\[(?P<tick>\d+)\]\s+(?P<clock>\d\d:\d\d:\d\d)\.\d+\s+"
    r"frames=(?P<frames>\d+).*?lastPr=(?P<lastPr>\d+).*?"
    r"dsync=(?P<dsync>\d+).*?presentAge=(?P<age>\d+)ms"
)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    tail_n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    if not path.is_file():
        print(f"REFUSED: no such file: {path}")
        return 2

    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE.match(line)
        if m:
            rows.append(m.groupdict())

    if not rows:
        print("REFUSED: no heartbeat lines matched the pattern")
        return 1

    # one sample per second: the last sample whose clock differs
    per_sec = []
    seen = None
    for r in rows:
        if r["clock"] != seen:
            seen = r["clock"]
            per_sec.append(r)

    print(f"{'second':>10}  {'dFrames':>8}  {'dLastPr':>8}  {'ratio':>6}  {'age_ms':>7}  dsync")
    for a, b in zip(per_sec, per_sec[1:]):
        df = int(b["frames"]) - int(a["frames"])
        dl = int(b["lastPr"]) - int(a["lastPr"])
        ratio = (dl / df) if df > 0 else float("nan")
        print(
            f"{a['clock']:>10}  {df:>8}  {dl:>8}  {ratio:>6.2f}  "
            f"{b['age']:>7}  {b['dsync']}"
        )

    print()
    print(f"samples={len(rows)}  seconds={len(per_sec)}")
    last = per_sec[-1]
    print(
        f"last: {last['clock']} frames={last['frames']} lastPr={last['lastPr']} "
        f"dsync={last['dsync']} age={last['age']}ms"
    )

    # the only ratio that counts: the healthy tail
    tail = [r for r in per_sec[-(tail_n + 1) :]]
    tot_df = int(tail[-1]["frames"]) - int(tail[0]["frames"])
    tot_dl = int(tail[-1]["lastPr"]) - int(tail[0]["lastPr"])
    if tot_df > 0:
        print(f"TAIL ratio (last {tail_n}s): {tot_dl}/{tot_df} = {tot_dl / tot_df:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
