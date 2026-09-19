#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_run_1130.py -- parse the 2026-09-19 11:30:56 run of DynamicShaderFrameGen.

Why a parser instead of grep: this log has ~3000 lines and ~10 different
one-line diagnostic formats.  Eyeballing a handful of them is how the previous
three rounds produced wrong conclusions.  This script extracts every format
into one timeline so that "did X happen while the camera was moving" can be
answered mechanically.

Outputs a plain-text timeline, nothing is modified.
"""

import re
import sys

LOG = ("C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/"
       "DynamicShaderFrameGen.log")

TS = r"\[(\d\d:\d\d:\d\d\.\d+)\]"

# ---- fps probe -------------------------------------------------------------
RE_FPS = re.compile(TS + r".*FPS probe: real=([\d.]+) \| (\w+) \| cap~=([\d.]+) "
                    r".*hwMax=(\d+) ask=(\d+) accepted=(\d+) \| cfgProvider=(\d+)")

# ---- the big serial line ---------------------------------------------------
RE_SER = re.compile(TS + r".*\[XRAY\] serial=(\d+) menu=(\d+) world=(\d+) edges=(\d+) "
                    r"resetTrue=(\d+) menuOpen=(\d+) reset=(\d+)")
def grab(pat, s, default="?"):
    m = re.search(pat, s)
    return m.group(1) if m else default

# ---- per-entry [CAM] lines -------------------------------------------------
RE_PUB = re.compile(TS + r".*\[CAM\] pub #(\d+) pos=\(([^)]*)\) move=([\d.]+) path=([\d.]+) "
                    r"matChanges=(\d+) arrivalsPerSec=(\d+) \| "
                    r"lock\(pub/hold/re/still\)=(\d+)/(\d+)/(\d+)/(\d+) proj00=([\d.]+) "
                    r"famRej=(\d+) frozenRep=(\d+) ident/diff=(\d+)/(\d+)")
RE_PUB2 = re.compile(TS + r".*\[CAM\] pub #(\d+) .*\| (ok|BAD)")
RE_ACC = re.compile(TS + r".*\[CAM\] acc #(\d+) pos=\(([^)]*)\) move=([\d.]+) path=([\d.]+) "
                    r"devVP=([\d.]+) detVP=([-\d.]+) magVP=([\d.]+) consecJmp=(\d+)")
RE_REJ = re.compile(TS + r".*\[CAM\] #(\d+) family rejected: proj00=([\d.]+) locked=([\d.]+) "
                    r"ratio=([\d.]+) pos=\(([^)]*)\) dist=([\d.]+) still=(\d+)/(\d+)")
RE_STEP = re.compile(TS + r".*\[CAM\].*step break.*")
RE_REL = re.compile(TS + r".*\[CAM\].*(lock RELEASED|RELEASE).*")
RE_SHAPE = re.compile(TS + r".*\[CAM\] #(\d+) non-affine w=(\d+) ACCEPTED.*")

# ---- other milestones ------------------------------------------------------
RE_MOTION = re.compile(TS + r".*\[MOTION\].*")
RE_NR = re.compile(TS + r".*\[(FrameGen|DLSSNR)\].*(CHAINED|suppressed|DLSSNR:) .*")
RE_WARN = re.compile(TS + r".*\[(W|E)\].*")


def main():
    with open(LOG, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", "replace")
    lines = text.split("\n")

    out = []
    def add(kind, t, msg):
        out.append((t, kind, msg))

    for ln in lines:
        m = RE_FPS.search(ln)
        if m:
            t, real, prov, cap, hw, ask, acc, cfg = m.groups()
            add("FPS", t, f"real={real}/s ({float(real):.1f})  prov={prov} cap~={cap} "
                          f"hwMax={hw} ask={ask} ACCEPTED={acc}  <-- accepted is the measured one")
            continue
        m = RE_SER.search(ln)
        if m:
            t, ser, menu, world, edges, rt, mo, reset = m.groups()
            add("SER", t,
                f"serial={ser} menu={menu} world={world} edges={edges} resetTrue={rt} reset={reset} | "
                f"presented ALL={grab(r'presented all=([\d/]+) ', ln)} "
                f"world={grab(r'presented all=[\d/]+ world=([\d/]+) ', ln)} "
                f"menu={grab(r'presented all=[\d/]+ world=[\d/]+ menu=([\d/]+) ', ln)} | "
                f"real={grab(r'real=([\d.]+)ms', ln)}ms "
                f"clipDev={grab(r'clipDev=([-\d.]+) clipW', ln)} clipW={grab(r'clipW=([-\d.]+)', ln)} "
                f"p00(c/p)={grab(r'p00\(c/p\)=([\d./]+)', ln)} "
                f"curVP={grab(r'curVP=([\d.]+)', ln)} prevVP={grab(r'prevVP=([\d.]+)', ln)} "
                f"curMag={grab(r'curMag=([\d.-]+)', ln)} engPrevMag={grab(r'engPrevMag=([\d.-]+)', ln)} | "
                f"pos={grab(r'pos=\(([^)]*)\)', ln)} prevPos={grab(r'prevPos=\(([^)]*)\)', ln)} | "
                f"mult(acc/pres)={grab(r'mult\(acc/pres\)=([\d/]+)', ln)} "
                f"camPrev(ok/used)={grab(r'camPrev\(ok/used\)=([\d/]+)', ln)} "
                f"frozen={grab(r' frozen=(\d+) ', ln)} "
                f"clipDevMax={grab(r'clipDevMax=([-\d.]+)', ln)} "
                f"det(min/max)={grab(r'det\(min/max\)=([\d./]+)', ln)} "
                f"dvd(ok/used)={grab(r'dvd\(ok/used\)=([\d/]+)', ln)} err={grab(r'err=(\d+)', ln)} | "
                f"rejPct={grab(r'([\d.]+)% shapeRej', ln)}% "
                f"id/diff={grab(r'gate\(sawDiff/consecRej/frozenRep/resets/id/diff\)=[\d:]+/(\d+)/(\d+)/(\d+)', ln)} "
                f"mapHit={grab(r'mapHit\(perFrame/unmap\)=([\d/]+)', ln)} "
                f"mfg={grab(r'mfg\(hwMax/reqMax/rungsSkipped\)=([\d/]+)', ln)} "
                f"inSetOptions={grab(r'inSetOptions=(\d+)', ln)}")
            continue
        m = RE_PUB.search(ln)
        if m:
            (t, n, pos, move, path, mats, aps, pub, hold, re_, still, p00, fam, fz, idn, dif) = m.groups()
            flag = "ok" if "| ok" in ln else "!!"
            add("PUB", t, f"#{n:>6} pos={pos:<28} move={move:>7} path={path:>7} "
                          f"matChanges={mats:>4} arr/s={aps:>4} | lock(pub/hold/re/still)="
                          f"{pub}/{hold}/{re_}/{still} proj00={p00} famRej={fam} "
                          f"frozenRep={fz} ident/diff={idn}/{dif} | {flag}")
            continue
        m = RE_REJ.search(ln)
        if m:
            t, n, p00, lk, ratio, pos, dist, st, tol = m.groups()
            add("REJ", t, f"#{n:>6} family rejected proj00={p00} locked={lk} ratio={ratio} "
                          f"pos={pos} dist={dist} still={st}/{tol}")
            continue
        m = RE_MOTION.search(ln)
        if m:
            add("MOTION", m.group(1), ln.split("] ", 2)[-1].strip())
            continue
        if RE_STEP.search(ln):
            t = RE_STEP.search(ln).group(1)
            add("STEP", t, ln.split("] ", 2)[-1].strip())
            continue
        if RE_REL.search(ln):
            add("RELEASE", RE_REL.search(ln).group(1), ln.split("] ", 2)[-1].strip())
            continue
        m = RE_NR.search(ln)
        if m:
            t = m.group(1)
            add("NR", t, ln.split("] ", 2)[-1].strip()[:180])
            continue
        m = RE_WARN.search(ln)
        if m:
            t = m.group(1)
            add("WARN", t, ln.split("] ", 2)[-1].strip()[:180])

    out.sort(key=lambda x: x[0])
    with open("tools/_run_1130_timeline.txt", "w", encoding="utf-8") as f:
        for t, k, msg in out:
            f.write(f"{t} {k:8s} {msg}\n")

    # summary
    from collections import Counter
    c = Counter(k for _, k, _ in out)
    print("events:", dict(c))
    print("timeline written to tools/_run_1130_timeline.txt")
    print()
    print("=== 前 30 条 ===")
    for t, k, msg in out[:30]:
        print(f"{t} {k:8s} {msg[:170]}")
    print()
    print("=== 后 30 条 ===")
    for t, k, msg in out[-30:]:
        print(f"{t} {k:8s} {msg[:170]}")


if __name__ == "__main__":
    main()
