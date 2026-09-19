#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.17 -- make the live player camera the AUTHORITY, not just a selector.

Why
---
The 22:22 run (v1.16 on the machine) settled the source question with ground
truth: RE::PlayerCamera::cameraRoot->world.translate reads
(-243.049,-415.315,118.624) while the proj00=0.8391 arrival reads
(-243.0493,-415.3115,118.5582) -- 0.00 units apart, 397 times a second.
So 0.8391 IS the player camera, and 0.149184 (which the whole v1.00..v1.15
line locked onto) is not.

v1.16 used that reference only to DROP a lock sitting on another family. Two
paths still let a non-camera arrival take the anchor afterwards:

  * the free-slot acquire (`if (!snapLockHave)`), which is the path that gave
    the 22:02 run its proj00=0.149184 lock at the reset edge, and
  * v1.00g's same-family step break, which re-anchors on ANY same-family
    arrival whose step exceeds kCamStepTol. Bucket proj00=1 of the 22:22 run
    shows how reachable that is: span (974.8,901.5,86.7), stepSum 542149.

What it does
------------
While the reference is demonstrably arriving (a kPcRefHoldSec-second latch set
on every match), an arrival that is not within kPcMatchTol of the live camera
may neither anchor nor be published. If the reference stops matching the latch
expires and the pre-v1.17 behaviour returns, so the gate cannot wedge the lock.

Also removes v1.16b's refusal, which hung off the "no PlayerCamera" arm and
therefore could only run while the reference was UNAVAILABLE -- snapPcReject
stayed 0 through the whole 22:22 run, which is how the mistake was caught.

And adds the motion witness `eyeD` (travel of the LIVE camera over the last
second) to the [CAM] PC line, because "the player is standing still" and "the
lock is on a parked writer" are otherwise the same shape in the log.

Usage
-----
    python tools/patch_v117_pcauthority.py            # dry run
    python tools/patch_v117_pcauthority.py --apply    # write
    python tools/patch_v117_pcauthority.py --revert   # undo (needs the same anchors)
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPP = ROOT / "src" / "FrameGen.cpp"
HDR = ROOT / "src" / "FrameGen.h"


def load(p):
    # read_bytes/decode, NOT read_text: read_text applies universal-newline
    # translation and silently turns every CRLF anchor into a LF anchor.
    return p.read_bytes().decode("utf-8")


def save(p, s):
    p.write_bytes(s.encode("utf-8"))


def eol_of(p):
    b = p.read_bytes()
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    if crlf and lf:
        raise SystemExit("REFUSED: %s is MIXED (CRLF=%d LF=%d)" % (p.name, crlf, lf))
    return "\r\n" if crlf else "\n"


def to_eol(text, eol):
    return text.replace("\r\n", "\n").replace("\n", eol)


# ---------------------------------------------------------------- edits ----

E1_OLD = """\tconstexpr float kSnapFamKeyTol = 1.0e-4f;
"""

E1_NEW = """\tconstexpr float kSnapFamKeyTol = 1.0e-4f;
\t// ---- v1.17: the reference is the authority, not only a selector -------
\t// v1.16 used RE::PlayerCamera only to DROP a lock that sat on another
\t// family. Two paths still let a non-camera arrival take the anchor after
\t// that: the free-slot acquire, which is what gave the 22:02 run its
\t// proj00=0.149184 lock at the reset edge, and v1.00g's same-family step
\t// break, which re-anchors on ANY same-family arrival over kCamStepTol.
\t// Bucket proj00=1 of the 22:22 run shows how reachable that is: span
\t// (974.8,901.5,86.7) and stepSum 542149, so it can satisfy
\t// kCamForeignMoveTol (200) with no camera motion at all.
\t//
\t// While the reference is demonstrably arriving it alone may anchor or be
\t// published. The latch below expires if the reference stops matching, so
\t// the gate cannot wedge the lock.
\tconstexpr std::uint32_t kPcRefHoldSec = 2;
"""

E2_OLD = """\t\tconst bool projOk = (proj00 == proj00) && (proj00 > 1.0e-6f);
"""

E2_NEW = """\t\tconst bool projOk = (proj00 == proj00) && (proj00 > 1.0e-6f);
\t\t// v1.17: written by the ground-truth block below and read by the accept
\t\t// path. pcIsThis -- THIS arrival is the live camera; pcKnown -- the
\t\t// reference matched at least once within the last kPcRefHoldSec seconds.
\t\t// pcKnown is sampled before the block, so the very arrival that
\t\t// establishes the reference is itself published normally.
\t\tbool pcIsThis = false;
\t\tconst bool pcKnown = snapPcRefSeen > 0u;
"""

E3_OLD = """\t\t\t\t\t++snapPcMatch;
\t\t\t\t\tsnapPcEverMatched = true;
"""

E3_NEW = """\t\t\t\t\t++snapPcMatch;
\t\t\t\t\tsnapPcEverMatched = true;
\t\t\t\t\t// v1.17: latch the reference as live for the next few seconds
\t\t\t\t\tsnapPcRefSeen = kPcRefHoldSec;
\t\t\t\t\tpcIsThis = true;
"""

E4_OLD = """\t\t\t} else if (snapPcEverMatched && snapLockHave &&
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
"""

E4_NEW = """\t\t\t// v1.16b put its refusal HERE, hanging off the "no PlayerCamera" arm of
\t\t\t// the block above, so it could only ever run while the reference was
\t\t\t// UNAVAILABLE -- and snapPcReject stayed 0 through the whole 22:22 run,
\t\t\t// which is how the mistake was caught. It also duplicated the
\t\t\t// !sameFamily refusal two blocks down, which returns false for a
\t\t\t// foreign family unconditionally. Removed. v1.17 refuses instead at
\t\t\t// the one place a non-camera arrival could still take the anchor:
\t\t\t// the guard in front of the acquire, just below.
\t\t\t}
"""

E5_OLD = """\t\t\tconst bool continues = snapLockHave && snapHaveLast && (d2 <= kCamStepTol2);
\t\t\tif (!snapLockHave) {
"""

E5_NEW = """\t\t\t// ---- v1.17: while the reference is live, only the camera may publish ----
\t\t\t// This single guard covers all three ways an arrival can take the
\t\t\t// anchor: the free-slot acquire, the foreign-family fall-through, and
\t\t\t// v1.00g's same-family step break. Any of them handing the anchor to a
\t\t\t// writer that is not the camera is the freeze -- the published
\t\t\t// clipToPrevClip then reprojects against the wrong view. Returning
\t\t\t// false leaves snapLastPos / snapHaveLast untouched, so the next
\t\t\t// arriving camera continues the stream without a discontinuity.
\t\t\tif (pcKnown && !pcIsThis) {
\t\t\t\t++snapPcReject;
\t\t\t\treturn false;
\t\t\t}
\t\t\tconst bool continues = snapLockHave && snapHaveLast && (d2 <= kCamStepTol2);
\t\t\tif (!snapLockHave) {
"""

E7_OLD = """\t\t\t\t\t// v1.16: the ground-truth comparison, per second. If `best` stays in the
\t\t\t\t\t// hundreds through the world, no arrival is the camera and the source
\t\t\t\t\t// has to change; if it drops to a few units, PC TAKEOVER above fired.
\t\t\t\t\tSKSE::log::info("[CAM] PC v1.16: read={} match={} adopt={}/{} best={:.2f} "
\t\t\t\t\t\t"at proj00={:.6g} eye=({:.2f},{:.2f},{:.2f})",
\t\t\t\t\t\tsnapPcRead, snapPcMatch, snapPcAdoptSec, snapPcAdopt,
\t\t\t\t\t\tsnapPcSawAny ? snapPcBestDist : -1.0f, snapPcBestProj,
\t\t\t\t\t\tsnapPcLast[0], snapPcLast[1], snapPcLast[2]);
\t\t\t\t\tsnapPcRead = 0;
\t\t\t\t\tsnapPcMatch = 0;
\t\t\t\t\tsnapPcAdoptSec = 0;
\t\t\t\t\tsnapPcBestDist = 1.0e38f;
\t\t\t\t\tsnapPcBestProj = 0.0f;
\t\t\t\t\tsnapPcSawAny = false;
"""

E7_NEW = """\t\t\t\t\t// v1.17: the motion witness. eyeD is how far the LIVE player camera
\t\t\t\t\t// travelled during the last second. Without it "the player is standing
\t\t\t\t\t// still" and "the lock is on a parked writer" are the same shape in the
\t\t\t\t\t// log, which is exactly why the 22:22 run could not be settled: world
\t\t\t\t\t// segment 2.2 s, eye byte-identical at 2 decimals, family span 0.07
\t\t\t\t\t// units (idle sway only).
\t\t\t\t\tif (snapPcEyeHave) {
\t\t\t\t\t\tconst float pdx = snapPcLast[0] - snapPcPrevEye[0];
\t\t\t\t\t\tconst float pdy = snapPcLast[1] - snapPcPrevEye[1];
\t\t\t\t\t\tconst float pdz = snapPcLast[2] - snapPcPrevEye[2];
\t\t\t\t\t\tsnapPcEyeStep = std::sqrt(pdx * pdx + pdy * pdy + pdz * pdz);
\t\t\t\t\t}
\t\t\t\t\tSKSE::log::info("[CAM] PC v1.17: read={} match={} adopt={}/{} rej={} ref={} "
\t\t\t\t\t\t"best={:.2f} at proj00={:.6g} eye=({:.2f},{:.2f},{:.2f}) eyeD={:.2f} {}",
\t\t\t\t\t\tsnapPcRead, snapPcMatch, snapPcAdoptSec, snapPcAdopt, snapPcReject,
\t\t\t\t\t\tsnapPcRefSeen,
\t\t\t\t\t\tsnapPcSawAny ? snapPcBestDist : -1.0f, snapPcBestProj,
\t\t\t\t\t\tsnapPcLast[0], snapPcLast[1], snapPcLast[2], snapPcEyeStep,
\t\t\t\t\t\tsnapPcEyeStep <= kCamMoveEps
\t\t\t\t\t\t\t? "PC_STILL - the live camera did not move: an unchanged picture is CORRECT here"
\t\t\t\t\t\t\t: "PC_MOVING - the live camera is walking");
\t\t\t\t\tsnapPcRead = 0;
\t\t\t\t\tsnapPcMatch = 0;
\t\t\t\t\tsnapPcAdoptSec = 0;
\t\t\t\t\tsnapPcBestDist = 1.0e38f;
\t\t\t\t\tsnapPcBestProj = 0.0f;
\t\t\t\t\tsnapPcSawAny = false;
\t\t\t\t\tsnapPcPrevEye[0] = snapPcLast[0];
\t\t\t\t\tsnapPcPrevEye[1] = snapPcLast[1];
\t\t\t\t\tsnapPcPrevEye[2] = snapPcLast[2];
\t\t\t\t\tsnapPcEyeHave = true;
\t\t\t\t\tif (snapPcRefSeen > 0u)
\t\t\t\t\t\t--snapPcRefSeen;
"""

H1_OLD = """\tbool snapPcSawAny = false;
"""

H1_NEW = """\tbool snapPcSawAny = false;
\t// ---- v1.17: the reference as authority, not only as a selector ---------
\t// snapPcRefSeen is a latch measured in seconds: set to kPcRefHoldSec on
\t// every match, decremented once per second by the [CAM] PC dump. While it is
\t// non-zero the reference is demonstrably arriving, so a non-camera arrival
\t// may neither anchor nor be published. If the reference stops matching the
\t// latch expires and the pre-v1.17 behaviour returns, which is what keeps this
\t// gate from being able to wedge the lock.
\tstd::uint32_t snapPcRefSeen = 0;
\t// v1.17: the motion witness, printed as eyeD on the [CAM] PC line.
\tfloat snapPcEyeStep = 0.0f;
\tfloat snapPcPrevEye[3] = {};
\tbool snapPcEyeHave = false;
"""

H3_OLD = """\tstd::uint64_t snapPcReject = 0;   // v1.16b: refused because it is not the camera
\tbool snapPcEverMatched = false;   // v1.16b: the reference proved itself
"""

H3_NEW = """\tstd::uint64_t snapPcReject = 0;   // v1.17: refused because it is not the camera
\tbool snapPcEverMatched = false;   // the reference proved itself at least once
"""

H2_OLD = """\t// path 65.41, move 0.0000, still 1570/90) and clipToPrevClip collapsed to I.
"""

H2_NEW = """\t// path 65.41, move 0.0000, still 1570/90) and clipToPrevClip collapsed to I.
\t//
\t// CORRECTION (v1.17, 22:22 run): "the real camera (proj00=1)" above is
\t// WRONG and was never measured -- it was inferred from travel, which is the
\t// same inference the whole v1.00..v1.15 line rested on. The v1.16 ground
\t// truth settled it: RE::PlayerCamera::cameraRoot->world.translate reads
\t// (-243.049,-415.315,118.624) while the proj00=0.8391 arrival reads
\t// (-243.0493,-415.3115,118.5582) -- 0.00 units apart, 397 times a second.
\t// 0.8391 IS the player camera. proj00=1 sits at (-126.2,211.5,189.2) with
\t// span (974.8,901.5,86.7) and stepSum 542149, i.e. a bucket of at least two
\t// writers ~1000 units apart -- an offscreen/orthographic pass, not a walking
\t// camera. Every conclusion v1.10..v1.15 drew from "the refused arriving
\t// family is the camera" is therefore inverted. Kept as the record of how the
\t// inversion happened; the v1.17 guard above does not depend on it.
"""

EDITS = [
    (CPP, "E1  kPcRefHoldSec constant", E1_OLD, E1_NEW, "kPcRefHoldSec"),
    (CPP, "E2  pcIsThis / pcKnown", E2_OLD, E2_NEW, "bool pcIsThis = false;"),
    (CPP, "E3  latch on match", E3_OLD, E3_NEW, "snapPcRefSeen = kPcRefHoldSec;"),
    (CPP, "E4  drop v1.16b dead branch", E4_OLD, E4_NEW, None),
    (CPP, "E5  v1.17 authority guard", E5_OLD, E5_NEW,
     "v1.17: while the reference is live"),
    (CPP, "E7  PC dump + eyeD", E7_OLD, E7_NEW, None),
    (HDR, "H1  new members", H1_OLD, H1_NEW, "snapPcEyeStep"),
    (HDR, "H3  counter comments", H3_OLD, H3_NEW, None),
    (HDR, "H2  v1.10 correction note", H2_OLD, H2_NEW, "CORRECTION (v1.17"),
]


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    # preflight: every anchor must match exactly once in the target file
    pre = {}
    for path, label, old, new, marker in EDITS:
        if path not in pre:
            pre[path] = load(path)
        src = pre[path]
        eol = eol_of(path)
        a = to_eol(old, eol)
        n = src.count(a)
        if n != 1:
            print("REFUSED, nothing written: %s anchor count = %d (must be 1)" % (label, n))
            return 1
        if marker and marker in src:
            print("REFUSED, nothing written: %s marker %r already present"
                  % (label, marker))
            return 1

    if not apply and not revert:
        print("dry run OK: %d/%d anchors unique in %d files"
              % (len(EDITS), len(EDITS), len(pre)))
        for path, label, _o, _n, _m in EDITS:
            print("  would patch %-10s %s" % (path.name, label))
        return 0

    out = {p: s for p, s in pre.items()}
    for path, label, old, new, marker in EDITS:
        eol = eol_of(path)
        a = to_eol(old, eol)
        b = to_eol(new, eol)
        if revert:
            a, b = b, a
        s = out[path]
        if s.count(a) != 1:
            print("REFUSED, nothing written: %s reverse anchor count = %d"
                  % (label, s.count(a)))
            return 1
        out[path] = s.replace(a, b, 1)
        print("  %-10s %s" % ("REVERT" if revert else "patched", label))

    if revert:
        for p, s in out.items():
            save(p, s)
            print("reverted %s" % p.relative_to(ROOT))
        return 0

    # post-conditions on the RESULT text, never on the input
    cpp = out[CPP]
    hdr = out[HDR]
    checks = [
        ("cpp kPcRefHoldSec const", cpp.count("constexpr std::uint32_t kPcRefHoldSec = 2;"), 1),
        ("cpp pcIsThis decl", cpp.count("bool pcIsThis = false;"), 1),
        ("cpp pcKnown decl", cpp.count("const bool pcKnown = snapPcRefSeen > 0u;"), 1),
        ("cpp latch on match", cpp.count("snapPcRefSeen = kPcRefHoldSec;"), 1),
        ("cpp authority guard", cpp.count("if (pcKnown && !pcIsThis) {"), 1),
        ("cpp v1.16b branch gone", cpp.count("} else if (snapPcEverMatched && snapLockHave &&"), 0),
        ("cpp v1.16 dump gone", cpp.count("[CAM] PC v1.16: read={} match={}"), 0),
        ("cpp v1.17 dump present", cpp.count('[CAM] PC v1.17: read={} match={} adopt={}/{} rej={}'), 1),
        ("cpp eyeD present", cpp.count("snapPcEyeStep = std::sqrt(pdx * pdx + pdy * pdy + pdz * pdz);"), 1),
        ("cpp latch decay", cpp.count("if (snapPcRefSeen > 0u)"), 1),
        ("hdr snapPcRefSeen", hdr.count("std::uint32_t snapPcRefSeen = 0;"), 1),
        ("hdr snapPcEyeStep", hdr.count("float snapPcEyeStep = 0.0f;"), 1),
        ("hdr correction note", hdr.count("CORRECTION (v1.17, 22:22 run)"), 1),
        ("hdr old snapPcReject comment gone", hdr.count("// v1.16b: refused because it is not the camera"), 0),
    ]
    bad = [(n, got, want) for n, got, want in checks if got != want]
    if bad:
        for n, got, want in bad:
            print("POST-CONDITION FAIL: %s = %d, wanted %d" % (n, got, want))
        print("REFUSED, nothing written")
        return 1

    for p, s in out.items():
        eol = eol_of(p)
        if "\n" in s.replace(eol, ""):
            print("REFUSED, nothing written: %s would contain a stray newline" % p.name)
            return 1
        save(p, s)
        print("wrote %s (%d bytes)" % (p.relative_to(ROOT), len(s.encode())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
