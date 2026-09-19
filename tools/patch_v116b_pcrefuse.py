#!/usr/bin/env python3
"""v1.16b: let the ground truth also refuse, not only adopt.

Without this, the v1.16 takeover can still churn. Arrival order within a frame is
fixed by the render pass order, so if the camera is written before a parked pass
the sequence is: camera -> PC TAKEOVER drops the lock -> the parked pass arrives
and the normal acquire path locks and PUBLISHES it -> the camera arrives and the
lock is dropped again. That publishes a parked matrix every other arrival, which
is exactly the interleaved-source stream of v0.93 that crashed the game
(#7818/#7824/#7837 RELOCK, path=845264).

So once the reference has proved itself -- one arrival has actually landed within
kPcMatchTol of the live player camera -- an arrival that is far from it AND
belongs to a different projection family than the lock may not take the lock.
Everything is gated on snapPcEverMatched: if the reference never matches, this
adds exactly nothing and the build behaves as v1.16 did.

Usage as for patch_v116_pctakeover.py.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPP = ROOT / "src" / "FrameGen.cpp"
HDR = ROOT / "src" / "FrameGen.h"

MARKER = "v1.16b"

H_OLD = """\tfloat snapPcBestDist = 1.0e38f;"""

H_NEW = """\tbool snapPcEverMatched = false;   // v1.16b: the reference proved itself
\tfloat snapPcBestDist = 1.0e38f;"""

C_OLD = """\t\t\t\tif (pcDist <= kPcMatchTol) {
\t\t\t\t\t++snapPcMatch;
\t\t\t\t\tconst bool lockOnOther ="""

C_NEW = """\t\t\t\tif (pcDist <= kPcMatchTol) {
\t\t\t\t\t++snapPcMatch;
\t\t\t\t\tsnapPcEverMatched = true;
\t\t\t\t\tconst bool lockOnOther ="""

C2_OLD = """\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}

\t\t{
\t\t\tbool sameFamily = true;"""

C2_NEW = """\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t}
\t\t\t} else if (snapPcEverMatched && snapLockHave &&
\t\t\t           !(snapLockProjValid &&
\t\t\t             std::fabs(proj00 - snapLockProj00) <=
\t\t\t                 std::fabs(snapLockProj00) * kSnapFamKeyTol + 1.0e-6f)) {
\t\t\t\t// v1.16b: the reference has proved itself, so an arrival that is far
\t\t\t\t// from the live camera AND in a different family than the lock may
\t\t\t\t// not take the lock. Without this, a parked pass arriving right after
\t\t\t\t// a takeover would be published once per camera arrival -- the v0.93
\t\t\t\t// interleaved-source stream that crashed the game.
\t\t\t\t++snapPcReject;
\t\t\t\treturn false;
\t\t\t}
\t\t}

\t\t{
\t\t\tbool sameFamily = true;"""

H2_OLD = """\tstd::uint64_t snapPcAdoptSec = 0;"""

H2_NEW = """\tstd::uint64_t snapPcAdoptSec = 0;
\tstd::uint64_t snapPcReject = 0;   // v1.16b: refused because it is not the camera"""

EDITS = [
    ("H everMatched", HDR, H_OLD, H_NEW),
    ("H reject counter", HDR, H2_OLD, H2_NEW),
    ("cpp set everMatched", CPP, C_OLD, C_NEW),
    ("cpp refuse branch", CPP, C2_OLD, C2_NEW),
]


def eol_of(path):
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    return b"\r\n" if crlf >= bare else b"\n"


def to_eol(text, eol):
    return text.replace("\r\n", "\n").replace("\n", eol.decode())


def main():
    apply = "--apply" in sys.argv
    eol = {CPP: eol_of(CPP), HDR: eol_of(HDR)}
    src = {p: p.read_bytes().decode("utf-8") for p in (CPP, HDR)}

    print("-- preflight --")
    ok = True
    for name, path, old, new in EDITS:
        n = src[path].count(to_eol(old, eol[path]))
        print(f"  {'OK ' if n == 1 else '** '}{name}: count={n} want=1")
        ok &= (n == 1)
    if MARKER in src[CPP]:
        print("REFUSED, nothing written: marker present")
        return 1
    if not ok:
        print("REFUSED, nothing written")
        return 1

    out = {p: src[p] for p in (CPP, HDR)}
    for name, path, old, new in EDITS:
        out[path] = out[path].replace(to_eol(old, eol[path]), to_eol(new, eol[path]))

    print("\n-- post-conditions --")
    bad = []
    def pc(label, got, want):
        nonlocal bad
        if got != want:
            bad.append(f"{label}: got {got}, want {want}")
        print(f"  {'OK ' if got == want else '** '}{label}: {got} (want {want})")

    c, h = out[CPP], out[HDR]
    pc("cpp refuse branch", c.count("++snapPcReject;"), 1)
    pc("cpp everMatched set", c.count("snapPcEverMatched = true;"), 1)
    pc("cpp everMatched gate", c.count("snapPcEverMatched && snapLockHave &&"), 1)
    pc("cpp marker comment", c.count("v1.16b: the reference has proved itself"), 1)
    pc("cpp lock anchor intact", c.count("bool sameFamily = true;"), 1)
    pc("cpp usable intact", c.count("const bool usable = (px == px)"), 1)
    pc("cpp pc line intact", c.count('"[CAM] PC v1.16: read={}'), 1)
    pc("hdr everMatched decl", h.count("bool snapPcEverMatched = false;"), 1)
    pc("hdr reject decl", h.count("std::uint64_t snapPcReject = 0;"), 1)

    if bad:
        print("\nFAIL post-conditions:\n  " + "\n  ".join(bad))
        return 2

    if not apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply.")
        return 0

    for p in (CPP, HDR):
        p.write_bytes(out[p].encode("utf-8"))
        raw = out[p].encode("utf-8")
        crlf = raw.count(b"\r\n")
        print(f"wrote {p.name}: {len(raw)} bytes, CRLF={crlf}, bareLF={raw.count(b'\n') - crlf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
