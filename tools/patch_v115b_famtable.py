#!/usr/bin/env python3
"""v1.15b: make the per-family table large enough, and VISIBLE when it fills.

Follow-up to patch_v115_fammotionprobe.py, same run.

Why: the v1.15 census keeps at most kSnapFamMax families, and a family that
arrives when the table is full is silently dropped -- which is precisely the
failure mode that would waste another run, because the one family we are hunting
is the LIVE one and it may be the last to show up.  The menu period of the 21:15
run alone produced four distinct proj00 values (0.149184, 0.8391, 0.888889, 1),
so 8 slots is not a comfortable margin.

Two changes, both diagnostic:
  kSnapFamMax 8 -> 16 (16 x 29 bytes of members, negligible);
  one warning the first time a family cannot be tracked.

Usage
-----
  python tools/patch_v115b_famtable.py            # dry run
  python tools/patch_v115b_famtable.py --apply
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPP = ROOT / "src" / "FrameGen.cpp"
HDR = ROOT / "src" / "FrameGen.h"

MARKER = "v1.15b: never drop a family silently"


def file_eol(path: pathlib.Path) -> bytes:
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    return b"\r\n" if crlf >= bare else b"\n"


OLD_CAP = "\tstatic constexpr std::uint32_t kSnapFamMax = 8;"
NEW_CAP = (
    "\t// v1.15b: 8 slots was not enough of a margin -- the menu period of the\n"
    "\t// 21:15 run alone showed four distinct proj00 values, and a family dropped\n"
    "\t// because the table was full is exactly the one we are hunting.\n"
    "\tstatic constexpr std::uint32_t kSnapFamMax = 16;"
)

OLD_FLAG = (
    "\tstd::uint64_t snapFamLogged = 0;"
)
NEW_FLAG = (
    "\tstd::uint64_t snapFamLogged = 0;\n"
    "\tbool snapFamOverflowLogged = false;"
)

OLD_PLACE = (
    "\t\t\tif (slot < 0) {\n"
    "\t\t\t\tfor (std::uint32_t i = 0; i < kSnapFamMax; ++i) {\n"
    "\t\t\t\t\tif (!snapFamSeen[i]) {\n"
    "\t\t\t\t\t\tsnapFamSeen[i] = true;\n"
    "\t\t\t\t\t\tsnapFamProj[i] = famKey;\n"
    "\t\t\t\t\t\tsnapFamHavePos[i] = false;\n"
    "\t\t\t\t\t\tsnapFamMoved[i] = 0;\n"
    "\t\t\t\t\t\tsnapFamStep[i] = 0.0f;\n"
    "\t\t\t\t\t\tslot = static_cast<std::int32_t>(i);\n"
    "\t\t\t\t\t\tbreak;\n"
    "\t\t\t\t\t}\n"
    "\t\t\t\t}\n"
    "\t\t\t}"
)
NEW_PLACE = (
    "\t\t\tif (slot < 0) {\n"
    "\t\t\t\tfor (std::uint32_t i = 0; i < kSnapFamMax; ++i) {\n"
    "\t\t\t\t\tif (!snapFamSeen[i]) {\n"
    "\t\t\t\t\t\tsnapFamSeen[i] = true;\n"
    "\t\t\t\t\t\tsnapFamProj[i] = famKey;\n"
    "\t\t\t\t\t\tsnapFamHavePos[i] = false;\n"
    "\t\t\t\t\t\tsnapFamMoved[i] = 0;\n"
    "\t\t\t\t\t\tsnapFamStep[i] = 0.0f;\n"
    "\t\t\t\t\t\tslot = static_cast<std::int32_t>(i);\n"
    "\t\t\t\t\t\tbreak;\n"
    "\t\t\t\t\t}\n"
    "\t\t\t\t}\n"
    "\t\t\t\tif (slot < 0 && !snapFamOverflowLogged) {\n"
    "\t\t\t\t\t// v1.15b: never drop a family silently. If this fires, a family is\n"
    "\t\t\t\t\t// going uncounted and its motion is invisible -- raise kSnapFamMax.\n"
    "\t\t\t\t\tsnapFamOverflowLogged = true;\n"
    "\t\t\t\t\tSKSE::log::info(\"[CAM] FAM table full ({} slots): proj00={:.6g} is NOT \"\n"
    "\t\t\t\t\t\t\"being tracked - raise kSnapFamMax\", kSnapFamMax, famKey);\n"
    "\t\t\t\t}\n"
    "\t\t\t}"
)

EDITS = [
    ("hdr: kSnapFamMax 8 -> 16", HDR, OLD_CAP, NEW_CAP, 1),
    ("hdr: overflow flag", HDR, OLD_FLAG, NEW_FLAG, 1),
    ("cpp: warn instead of dropping silently", CPP, OLD_PLACE, NEW_PLACE, 1),
]


def main():
    apply = "--apply" in sys.argv

    src = {}
    for path in (CPP, HDR):
        src[path] = path.read_bytes().decode("utf-8")

    print(f"marker present: {MARKER in src[CPP]}")
    if MARKER in src[CPP]:
        print("REFUSED, nothing written: patch already applied (idempotency guard)")
        return 1

    bad = []
    for name, path, old, new, want in EDITS:
        eol = file_eol(path)
        n = src[path].count(old.replace("\n", eol.decode()))
        print(f"  count={n} (want {want})  {name}  [{path.name}]")
        if n != want:
            bad.append(name)
    if bad:
        print(f"REFUSED, nothing written: non-unique/missing anchors: {bad}")
        return 1

    out = dict(src)
    for name, path, old, new, want in EDITS:
        eol = file_eol(path)
        out[path] = out[path].replace(
            old.replace("\n", eol.decode()), new.replace("\n", eol.decode()))

    cpp, hdr = out[CPP], out[HDR]
    probes = [
        ("marker in cpp", cpp.count(MARKER), 1),
        ("overflow warning string",
         cpp.count('"[CAM] FAM table full ({} slots): proj00={:.6g} is NOT "'), 1),
        ("overflow flag set", cpp.count("snapFamOverflowLogged = true;"), 1),
        ("kSnapFamMax is 16", hdr.count("kSnapFamMax = 16;"), 1),
        ("kSnapFamMax is no longer 8", hdr.count("kSnapFamMax = 8;"), 0),
        ("overflow flag declared", hdr.count("\tbool snapFamOverflowLogged = false;"), 1),
        ("v1.15 marker intact", cpp.count("v1.15 probe: MOTION PER FAMILY"), 1),
    ]
    dead = [f"{name}: got {got}, want {want}" for name, got, want in probes if got != want]
    if dead:
        print("FAIL post-conditions:\n  " + "\n  ".join(dead))
        return 2

    for path in (CPP, HDR):
        a = src[path].encode("utf-8")
        b = out[path].encode("utf-8")
        ca, cb = a.count(b"\r\n"), b.count(b"\r\n")
        ba, bb = a.count(b"\n") - ca, b.count(b"\n") - cb
        sa = "CRLF" if ca >= ba else "LF"
        sb = "CRLF" if cb >= bb else "LF"
        if sa != sb or (sa == "CRLF" and bb != 0) or (sa == "LF" and cb != 0):
            print(f"FAIL eol: {path.name} {sa}->{sb} bareLF {ba}->{bb}")
            return 2
        print(f"  {path.name}: CRLF {ca}->{cb} bareLF {ba}->{bb} bytes {len(a)}->{len(b)}")

    print("all post-conditions OK")
    if not apply:
        print("DRY RUN, nothing written (pass --apply to write)")
        return 0
    for path in (CPP, HDR):
        path.write_bytes(out[path].encode("utf-8"))
    print("APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
