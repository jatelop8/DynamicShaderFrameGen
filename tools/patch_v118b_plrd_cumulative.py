#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.18b: make plrD cumulative, so it means what the field says.

Caught by the L0 second pass on v1.18 before the run, not by the compiler.

`s_plrStep` was assigned on every arrival (`s_plrStep = sqrt(...)`), while the
two witnesses next to it are accumulated and reset once a second: `s_inKeys |=`
and `s_inDist +=`. `AcceptCameraSnapshot` runs ~400 times a second, so the
assignment made `plrD` the distance travelled in the ~2.5 ms between two
arrivals -- about 7 mm for a walking player -- under a field name and a comment
that both say "this second".

The criterion `plrD > 0` still worked, which is exactly why this would have
survived: a broken number that happens to be non-zero still answers the
yes/no question. But it would answer "how fast" wrongly, and this project has
already lost two runs to a field that measured something other than its label.

So: `+=` instead of `=`, and reset it with its two siblings in the per-second
block. Zero behaviour change -- this is still read-only instrumentation.

Dry run by default; --apply writes.
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPP = ROOT / "src" / "FrameGen.cpp"

T5 = "\t" * 5
T8 = "\t" * 8


def L(*ls):
    return "".join(l + "\n" for l in ls)


E1_OLD = L(
    T8 + "s_plrStep = std::sqrt(qx * qx + qy * qy + qz * qz);",
)

E1_NEW = L(
    T8 + "// v1.18b: +=, not =. This runs on every arrival (~400/s), so an",
    T8 + "// assignment here would make plrD the distance travelled in the ~2.5 ms",
    T8 + "// between two arrivals (about 7 mm for a walking player) under a name",
    T8 + "// that says \"this second\". The yes/no criterion survives that; the",
    T8 + "// number does not, and this project has already lost two runs to a field",
    T8 + "// that measured something other than its label.",
    T8 + "s_plrStep += std::sqrt(qx * qx + qy * qy + qz * qz);",
)

E2_OLD = L(
    T5 + "s_inMoves = 0u;",
)

E2_NEW = L(
    T5 + "s_inMoves = 0u;",
    T5 + "s_plrStep = 0.0f;",
)

EDITS = [
    ("E1  plrD accumulates instead of overwriting", E1_OLD, E1_NEW),
    ("E2  plrD joins the per-second reset", E2_OLD, E2_NEW),
]

MARK = "s_plrStep += std::sqrt"


def eol_of(path):
    b = path.read_bytes()
    return "\r\n" if b.count(b"\r\n") > 0 else "\n"


def load(path):
    return path.read_bytes().decode("utf-8")


def save(path, s):
    path.write_bytes(s.encode("utf-8"))


def to_eol(text, eol):
    return text.replace("\n", eol)


def main():
    apply = "--apply" in sys.argv
    eol = eol_of(CPP)
    src = load(CPP)

    if MARK in src:
        print("REFUSED: already patched (marker present)")
        return 1

    prepared = []
    for label, old, new in EDITS:
        o = to_eol(old, eol)
        n = to_eol(new, eol)
        c = src.count(o)
        if c != 1:
            print("REFUSED, nothing written: %s anchor count = %d (must be exactly 1)" % (label, c))
            return 1
        prepared.append((label, o, n))

    if not apply:
        print("dry run OK: %d/%d anchors unique in %s" % (len(EDITS), len(EDITS), CPP.name))
        for label, _o, _n in prepared:
            print("  would patch " + label)
        return 0

    out = src
    for label, o, n in prepared:
        out = out.replace(o, n, 1)
        print("  patched " + label)

    def delta(t):
        return out.count(t) - src.count(t)

    checks = [
        ("plrD accumulates", delta(MARK), 1),
        ("old assignment gone", out.count("s_plrStep = std::sqrt"), 0),
        ("plrD reset added", delta("s_plrStep = 0.0f;"), 1),
        ("s_inKeys untouched", delta("s_inKeys"), 0),
        ("s_inDist untouched", delta("s_inDist = 0.0f;"), 0),
        ("PC line untouched", delta("[CAM] PC v1.18: read="), 0),
    ]
    bad = [(n, g, w) for n, g, w in checks if g != w]
    if bad:
        for n, g, w in bad:
            print("POST-CONDITION FAIL: %s = %d, wanted %d" % (n, g, w))
        return 1

    save(CPP, out)
    print("wrote %s (%d bytes, was %d)" % (CPP.name, len(out.encode()), len(src.encode())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
