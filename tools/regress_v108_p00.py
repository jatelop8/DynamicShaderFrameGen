#!/usr/bin/env python3
"""
Offline regression for the v1.08 probe's judgement (analyze_session.py 4b/4c).

A metric that cannot disagree with itself is worthless (SKILL 40.11: the
criterion must be monotonic / must actually fire). This feeds SYNTHETIC logs
through the REAL analyze_session.py via its --log override, and asserts that
section 4c separates the two competing explanations of a bad clipW:

  CASE A  the two sides carry different projections  -> explanation (a)
  CASE B  same projection, near-singular inverse     -> explanation (b)
  CASE C  healthy run                                -> no complaint
  CASE D  p00 flips between two families mid-run     -> family-switch problem

Also asserts 4c degrades to NO DATA on a pre-v1.08 log, so a missing field can
never be read as a pass. Same class of proof as tools/prove_det3_blind.py.

Run:  python tools/regress_v108_p00.py
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PY = sys.executable
HERE = Path(__file__).resolve().parent
ANALYZE = HERE / "analyze_session.py"

fails = 0


def report(ok, label, detail=""):
    global fails
    print("  %s %s%s" % ("OK  " if ok else "FAIL", label, ("  " + detail) if detail else ""))
    if not ok:
        fails += 1


def hb(clipdev, clipw, p00c, p00p, serial=1):
    """One synthetic [XRAY] heartbeat, carrying every field section 4 reads."""
    return (
        "[00:00:%02d] [info] [XRAY] serial=%d menu=0 world=1 edges=0 resetTrue=0 "
        "menuOpen=0 reset=0 | consts ok=1 fail=0 lastR=0 | presented all=4 world=4 menu=0 | "
        "real=16.67ms | mvecScale=(1.000,1.000) flags=0x0 | jitter=(0.0000,0.0000) "
        "clipDev=%s clipW=%s p00(c/p)=%s/%s curVP=0.0000 prevVP=0.0000 | "
        "pos=(0.0,0.0,0.0) prevPos=(0.0,0.0,0.0) | "
        "dt min/avg/max=16.00/16.67/17.00ms n=240 capUs=16666 mult(acc/pres)=4/4 "
        "longFrames=0 cam(ok/inv)=240/0 camPrev(ok/used)=1/239 | "
        "reproj src=fixed engPrevEqCur=0/240 engPrevZero=241 frozen=0 "
        "dvd(ok/used)=239/239 err=1e-06 curMag=1.2 engPrevMag=0 "
        "clipDevMax=0.0100 hist(hit/miss)=239/1 seed=1 missGood=0 det(min/max)=1.000/1.000 "
        "fix(src=0 dev=0) detGuard=0 detHold=0 tid(a/b/c)=0x1/0x2/0x3 calls=1/2/3 | "
        "snap(acc/jmp/re/zero/arr/frozen/shape/rejPct)=0/0/0/0/0/0/0 0.0%% shapeRej(own)=0.0%% "
        "gate(sawDiff/consecRej/frozenRep/resets/id/diff)=0:0/0/0/0/0 "
        "mapHit(perFrame/unmap)=239/0 dist(last/acc)=0.0/0.0 | "
        "lock(pub/hold/re/still)=1/0/0/239 proj00=0.149184 famRej=0 | "
        "mfg(hwMax/reqMax/rungsSkipped)=1/3/0 inSetOptions=240"
        % (serial % 60, serial, clipdev, clipw, p00c, p00p)
    )


def motion(p00c, p00p, p23c, p23p, inv_mag, prev_mag):
    """One synthetic Transfusion [MOTION] warning, with the v1.08 probe tail."""
    return ("[00:00:30] [warning] [MOTION] clipToPrevClip[3].w=-195.222366 (must be 1) - "
            "the inverse and the previous matrix came from different cameras; DLSS-G is "
            "reprojecting with a non-affine matrix. v1.08 PROBE: p00 cur=%s prev=%s | "
            "p23 cur=%s prev=%s | mag invSrc=%s prevSrc=%s"
            % (p00c, p00p, p23c, p23p, inv_mag, prev_mag))


CASES = {
    # name: (log lines, list of (must_appear, label))
    "A": (
        [hb("28.772085", "5.620000", "0.8391", "0.1492", i) for i in range(1, 6)]
        + [motion("0.8391", "0.1492", "0.000000", "1.000000", "1.234", "1.111")],
        [("explanation (a)", "different projections -> (a)"),
         ("DIFFERENT projections (ratio", "reports the ratio")],
    ),
    "B": (
        [hb("-195.222366", "-195.222366", "0.1492", "0.1492", i) for i in range(1, 6)]
        + [motion("0.1492", "0.1492", "1.000000", "1.000000", "4.2e+05", "12.5")],
        [("explanation (b)", "same projection, huge inverse -> (b)"),
         ("mag(invSrc)=4.2e+05", "prints the inverse magnitude")],
    ),
    "C": (
        [hb("0.010000", "1.000000", "0.1492", "0.1492", i) for i in range(1, 6)],
        [("affine, [3].w == 1", "healthy w"),
         ("p00 is one family", "healthy single family"),
         ("no [MOTION] non-affine warning", "no warning")],
    ),
    "D": (
        [hb("0.010000", "1.000000", ("0.1492" if i % 2 else "0.8391"), "0.1492", i)
         for i in range(1, 6)],
        [("SWITCHES during", "family switch detected"),
         ("projection family switches mid-run", "recorded as a problem")],
    ),
}

print("=" * 78)
print("v1.08 probe judgement -- does 4c actually disagree with itself?")
print("=" * 78)

tmp = Path(tempfile.mkdtemp(prefix="dfg_p00_"))
for name, (lines, expects) in CASES.items():
    p = tmp / ("case_%s.log" % name)
    p.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    r = subprocess.run([PY, str(ANALYZE), "--log", str(p), "--watchdog", str(tmp / "none.log")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    print("\nCASE %s" % name)
    for needle, label in expects:
        report(needle in out, label, "(looking for %r)" % needle if needle not in out else "")
    # a synthetic run must never crash the analyzer
    report(r.returncode == 0, "analyzer exit code 0", "rc=%d" % r.returncode)

# --- the field must be ABSENT-able: a pre-v1.08 log must say NO DATA ---------
print("\nCASE E (pre-v1.08 log, no p00 field)")
old = "\r\n".join(hb("0.000061", "", "X", "X", i).replace("p00(c/p)=X/X ", "")
                  for i in range(1, 5)) + "\r\n"
p = tmp / "case_E.log"
p.write_bytes(old.encode("utf-8"))
r = subprocess.run([PY, str(ANALYZE), "--log", str(p), "--watchdog", str(tmp / "none.log")],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
out = (r.stdout or "") + (r.stderr or "")
report("NO DATA" in out and "predates the v1.08 probe" in out,
       "missing p00 reads as NO DATA, never as a pass")
report(r.returncode == 0, "analyzer exit code 0", "rc=%d" % r.returncode)

print("\n" + "=" * 78)
if fails == 0:
    print("RESULT: PASS - 4c fires on (a), fires on (b), stays quiet when healthy,")
    print("        flags a family switch, and refuses to read a missing field as a pass.")
else:
    print("RESULT: %d CHECK(S) FAILED" % fails)
print("=" * 78)
sys.exit(0 if fails == 0 else 1)
