#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v110_movingtakeover.py -- v1.10: a MOVING family beats a STILL lock.

THE MEASUREMENT THIS FIXES  (2026-09-19 11:30 run, the first run with v1.09's
`[CAM] pub` probe live; every number below is from the log, not inferred)

  * 11:33:15.482  [CAM] #66564 lock RELEASED on the reset edge (was proj00=0.149184)
                  - the next arrival re-acquires
  * the next arrival was proj00=0.8391 at pos=(-243.05,-415.31,118.56).
    That position is SCENE-FIXED: it is the very value the v1.07c note quotes from
    the 23:10 run two days earlier (cameraPos=(-243.049301,-415.311523,118.558205)),
    and clipToPrev[3].w=-195.222366 repeats to the last digit as well.  A live
    camera cannot reproduce another run's position exactly; that is scene geometry.
  * from then on the REAL camera (proj00=1, position walking
    (-125.7,210.8,188.4) -> (255.0,804.7,-94.4)) was refused as "another family"
    ~90x/s, and the accepted stream stayed byte-frozen:
        matChanges = 168 constant over 9 s / ~2100 publishes
        path = 65.41 constant      move = 0.0000      still = 1570/90
  * => frameBufferCopy frozen -> camPrevVP == camCurVP (prevVP=curVP=15.0006,
    prevPos == pos) -> clipToPrevClip == I (clipDev=0.000061)
  * => DLSS-G is told "the camera never moved", so the 3 interpolated frames of
    every present were duplicates -- while the FPS probe reported
        real=9.8  hwMax=6  ask=4  accepted=4
    i.e. 4x WAS running.  "4x 没成功" is really "4x ran and interpolated nothing".

WHY THIS IS NOT THE v0.94 RE-ACQUIRE THAT v1.07b DELETED
  v0.94 re-acquired after kCamStillTol refusals unconditionally, so the 90th
  refusal won by ORDER and a static wrong family could take the anchor (v1.07b's
  own note says it landed on proj00=1 "half the time").  Here the refused family
  must have TRAVELLED >= kCamForeignMoveTol units of its own accord.  A parked or
  stale camera cannot satisfy that.  Order alone is not enough, and the count
  floor (kCamForeignMinRej) is only a guard against jitter.

CONVENTIONS (project iron law -- each one has been violated at least once)
  * dry run by default; --apply writes; --revert undoes
  * anchor count(old) must be exactly 1 else REFUSED, nothing written
  * EOL is decided by the FILE, never by the anchor
  * idempotency: an explicit marker string refuses a second run
  * SPLICE GUARD: the byte before a match must be a newline, a tab, or BOF
  * post-conditions are evaluated on the RESULT text
"""

import io
import os
import sys

F_H = "src/FrameGen.h"
F_CPP = "src/FrameGen.cpp"

MARK = "v1.10: a MOVING family beats a STILL lock"

T = "\t"


# --------------------------------------------------------------------------- #
# edit 1 -- FrameGen.h: the new state
# --------------------------------------------------------------------------- #
H_OLD = (
    '\tfloat snapPubLastMat[4][4] = {};\n'
)

H_NEW = (
    '\tfloat snapPubLastMat[4][4] = {};\n'
    '\n'
    '\t// ---- v1.10: a MOVING family beats a STILL lock ---------------------- \n'
    '\t// The 11:30 run is the measurement this exists for. The reset edge at\n'
    '\t// 11:33:15.482 released the lock and "the next arrival" took it -- and that\n'
    '\t// arrival was proj00=0.8391 at pos (-243.05,-415.31,118.56), a SCENE-FIXED\n'
    '\t// position byte-identical to the cameraPos the 23:10 run recorded two days\n'
    '\t// earlier. The real camera (proj00=1) then walked\n'
    '\t// (-125.7,210.8,188.4) -> (255.0,804.7,-94.4) and was refused ~90 times a\n'
    '\t// second, so frameBufferCopy stayed frozen (matChanges 168 for nine seconds,\n'
    '\t// path 65.41, move 0.0000, still 1570/90) and clipToPrevClip collapsed to I.\n'
    '\t//\n'
    '\t// So the refused stream is allowed to take the anchor -- but only after it\n'
    '\t// has demonstrated travel of its own. kCamStillTol, the threshold v0.94\n'
    '\t// used unconditionally, is a dead constant (v1.09 finding D2): the lock has\n'
    '\t// no release path of its own, which is why 1570 consecutive refusals changed\n'
    '\t// nothing.\n'
    '\tfloat snapForeignMove = 0.0f;      // travel of the CURRENTLY refused family\n'
    '\tbool  snapForeignHave = false;     // the field above has a previous sample\n'
    '\tfloat snapForeignPos[3] = { 0.0f, 0.0f, 0.0f };\n'
    '\tfloat snapForeignProj00 = 0.0f;    // which family the travel belongs to\n'
    '\tstd::uint64_t snapForeignTakeover = 0;  // times a moving family took the anchor\n'
)


# --------------------------------------------------------------------------- #
# edit 2 -- FrameGen.cpp: constants
# --------------------------------------------------------------------------- #
C_OLD = '\t\tconstexpr std::uint32_t kCamStillTol = 90;\n'

C_NEW = (
    '\t\tconstexpr std::uint32_t kCamStillTol = 90;\n'
    '\n'
    '\t\t// ---- v1.10: "a moving family beats a still lock" ---------------------\n'
    '\t\t// Measured 11:30 run: the refused stream moved 640.8 -> 1334.8 units\n'
    '\t\t// between two of its own samples, while the locked stream\'s own travel\n'
    '\t\t// was frozen at 65.41 for nine seconds. 200 units of REFUSED-stream\n'
    '\t\t// travel is unambiguous motion, and still far below kCamJumpTol so a\n'
    '\t\t// single slot jump cannot reach it on its own.\n'
    '\t\tconstexpr float kCamForeignMoveTol = 200.0f;\n'
    '\t\t// Floor on the refusal count so two jittery arrivals cannot take the\n'
    '\t\t// anchor by accident. 30 arrivals is ~0.06 s at the measured 500/s and\n'
    '\t\t// ~0.33 s at the 90/s the world phase actually ran at.\n'
    '\t\tconstexpr std::uint32_t kCamForeignMinRej = 30;\n'
)


# --------------------------------------------------------------------------- #
# edit 3 -- FrameGen.cpp: declare the flag at the top of the lock block
# --------------------------------------------------------------------------- #
B_OLD = (
    '\t\t{\n'
    '\t\t\tbool sameFamily = true;\n'
)

B_NEW = (
    '\t\t{\n'
    '\t\t\tbool sameFamily = true;\n'
    '\t\t\t// v1.10: set when a moving foreign family took the anchor, so the\n'
    '\t\t\t// same-family step-break log below does not describe it wrongly.\n'
    '\t\t\tbool foreignTakeover = false;\n'
)


# --------------------------------------------------------------------------- #
# edit 4 -- FrameGen.cpp: the refusal tail becomes a takeover decision
# --------------------------------------------------------------------------- #
R_OLD = (
    '\t\t\t\t\tif (d2 > kCamJumpTol2) ++snapRejectJump;\n'
    '\t\t\t\t\treturn false;\n'
)

R_NEW = (
    '\t\t\t\t\tif (d2 > kCamJumpTol2) ++snapRejectJump;\n'
    '\t\t\t\t\t// ---- v1.10: a MOVING family beats a STILL lock ----------------\n'
    '\t\t\t\t\t// Rationale and the 11:30 numbers: see FrameGen.h, next to\n'
    '\t\t\t\t\t// snapForeignMove. The refused family must TRAVEL before it may\n'
    '\t\t\t\t\t// take the anchor, so this is not v0.94\'s order-dependent\n'
    '\t\t\t\t\t// re-acquire that v1.07b removed.\n'
    '\t\t\t\t\t{\n'
    '\t\t\t\t\t\tif (proj00 != snapForeignProj00) {\n'
    '\t\t\t\t\t\t\t// a different refused family: this travel is not ours\n'
    '\t\t\t\t\t\t\tsnapForeignProj00 = proj00;\n'
    '\t\t\t\t\t\t\tsnapForeignMove = 0.0f;\n'
    '\t\t\t\t\t\t\tsnapForeignHave = false;\n'
    '\t\t\t\t\t\t}\n'
    '\t\t\t\t\t\tconst float fdx = px - snapForeignPos[0];\n'
    '\t\t\t\t\t\tconst float fdy = py - snapForeignPos[1];\n'
    '\t\t\t\t\t\tconst float fdz = pz - snapForeignPos[2];\n'
    '\t\t\t\t\t\tif (snapForeignHave) {\n'
    '\t\t\t\t\t\t\tconst float fStep = std::sqrt(fdx * fdx + fdy * fdy + fdz * fdz);\n'
    '\t\t\t\t\t\t\t// a camera step is tens of units, a slot jump hundreds:\n'
    '\t\t\t\t\t\t\t// cap one step so a jump cannot fake travel on its own\n'
    '\t\t\t\t\t\t\tif (fStep < kCamJumpTol) snapForeignMove += fStep;\n'
    '\t\t\t\t\t\t}\n'
    '\t\t\t\t\t\tsnapForeignPos[0] = px;\n'
    '\t\t\t\t\t\tsnapForeignPos[1] = py;\n'
    '\t\t\t\t\t\tsnapForeignPos[2] = pz;\n'
    '\t\t\t\t\t\tsnapForeignHave = true;\n'
    '\t\t\t\t\t\tif (snapLockStill >= kCamForeignMinRej &&\n'
    '\t\t\t\t\t\t    snapForeignMove >= kCamForeignMoveTol) {\n'
    '\t\t\t\t\t\t\t++snapForeignTakeover;\n'
    '\t\t\t\t\t\t\tforeignTakeover = true;\n'
    '\t\t\t\t\t\t\tif (snapForeignTakeover <= 5u) {\n'
    '\t\t\t\t\t\t\t\tSKSE::log::info("[CAM] #{} FOREIGN TAKEOVER (v1.10): locked "\n'
    '\t\t\t\t\t\t\t\t\t"proj00={:.6g} has not moved for {} arrivals while the "\n'
    '\t\t\t\t\t\t\t\t\t"refused family proj00={:.6g} travelled {:.1f} units - "\n'
    '\t\t\t\t\t\t\t\t\t"adopting pos=({:.1f},{:.1f},{:.1f})",\n'
    '\t\t\t\t\t\t\t\t\tsnapArrivals,\n'
    '\t\t\t\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f,\n'
    '\t\t\t\t\t\t\t\t\tsnapLockStill, proj00, snapForeignMove, px, py, pz);\n'
    '\t\t\t\t\t\t\t}\n'
    '\t\t\t\t\t\t\tsnapForeignMove = 0.0f;\n'
    '\t\t\t\t\t\t\tsnapForeignHave = false;\n'
    '\t\t\t\t\t\t\t// fall through to the adopt path below; it refreshes\n'
    '\t\t\t\t\t\t\t// snapLockProj00 after the publish (v1.00 block)\n'
    '\t\t\t\t\t\t} else {\n'
    '\t\t\t\t\t\t\treturn false;\n'
    '\t\t\t\t\t\t}\n'
    '\t\t\t\t\t}\n'
)


# --------------------------------------------------------------------------- #
# edit 5 -- FrameGen.cpp: do not call a foreign takeover a "same-family" break
# --------------------------------------------------------------------------- #
S_OLD = (
    '\t\t\t\t++snapLockRelockJump;\n'
    '\t\t\t\tif (snapLockRelockJump <= 5u) {\n'
)

S_NEW = (
    '\t\t\t\t++snapLockRelockJump;\n'
    '\t\t\t\tif (!foreignTakeover && snapLockRelockJump <= 5u) {\n'
)


# --------------------------------------------------------------------------- #
# edit 6 -- FrameGen.cpp: reset the foreign accumulator when the lock changes
# --------------------------------------------------------------------------- #
A_OLD = (
    '\t\t\tif (!snapLockHave) {\n'
    '\t\t\t\t// First arrival, or the locked stream died: acquire.\n'
    '\t\t\t\tsnapLockHave = true;\n'
    '\t\t\t\tsnapLockStill = 0;\n'
)

A_NEW = (
    '\t\t\tif (!snapLockHave) {\n'
    '\t\t\t\t// First arrival, or the locked stream died: acquire.\n'
    '\t\t\t\tsnapLockHave = true;\n'
    '\t\t\t\tsnapLockStill = 0;\n'
    '\t\t\t\t// v1.10: travel accumulated against the OLD anchor is not\n'
    '\t\t\t\t// evidence about the new one\n'
    '\t\t\t\tsnapForeignMove = 0.0f;\n'
    '\t\t\t\tsnapForeignHave = false;\n'
)

RE_OLD = (
    '\t\t\tsnapLockHave = false;\n'
    '\t\t\tsnapLockProjValid = false;\n'
    '\t\t\tsnapHaveLast = false;\n'
    '\t\t\tsnapLockStill = 0;\n'
)

RE_NEW = (
    '\t\t\tsnapLockHave = false;\n'
    '\t\t\tsnapLockProjValid = false;\n'
    '\t\t\tsnapHaveLast = false;\n'
    '\t\t\tsnapLockStill = 0;\n'
    '\t\t\t// v1.10: same reason as the acquire path\n'
    '\t\t\tsnapForeignMove = 0.0f;\n'
    '\t\t\tsnapForeignHave = false;\n'
)


# --------------------------------------------------------------------------- #
# edit 7 -- FrameGen.cpp: make the new state visible on the heartbeat
# --------------------------------------------------------------------------- #
P_OLD = (
    '\t\t\t\t\t\t"proj00={:.6g} famRej={} frozenRep={} ident/diff={}/{} | {}",\n'
    '\t\t\t\t\t\tsnapAccept, px, py, pz, snapAcceptDist, snapPathLen, snapMatChanges,\n'
    '\t\t\t\t\t\tarrPerSec, snapLockPublish, snapLockHold, snapLockRelock, snapLockStill,\n'
    '\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f, snapLockFamilyRej,\n'
)

P_NEW = (
    '\t\t\t\t\t\t"proj00={:.6g} famRej={} frozenRep={} ident/diff={}/{} "\n'
    '\t\t\t\t\t\t"fMove={:.1f} takeover={} | {}",\n'
    '\t\t\t\t\t\tsnapAccept, px, py, pz, snapAcceptDist, snapPathLen, snapMatChanges,\n'
    '\t\t\t\t\t\tarrPerSec, snapLockPublish, snapLockHold, snapLockRelock, snapLockStill,\n'
    '\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f, snapLockFamilyRej,\n'
)

P_TAIL_OLD = (
    '\t\t\t\t\t\tsnapFrozenRepeats, snapIdenticalArrivals, snapDifferentArrivals,\n'
)

P_TAIL_NEW = (
    '\t\t\t\t\t\tsnapFrozenRepeats, snapIdenticalArrivals, snapDifferentArrivals,\n'
    '\t\t\t\t\t\tsnapForeignMove, snapForeignTakeover,\n'
)


PLAN = [
    # (file, label, old, new, must-see-in-result)
    (F_H,   "h_state",     H_OLD,     H_NEW,     "snapForeignTakeover"),
    (F_CPP, "cpp_consts",  C_OLD,     C_NEW,     "kCamForeignMoveTol"),
    (F_CPP, "cpp_flag",    B_OLD,     B_NEW,     "bool foreignTakeover = false;"),
    (F_CPP, "cpp_takeover", R_OLD,    R_NEW,     "FOREIGN TAKEOVER (v1.10)"),
    (F_CPP, "cpp_logfix",  S_OLD,     S_NEW,     "if (!foreignTakeover && snapLockRelockJump"),
    (F_CPP, "cpp_acqreset", A_OLD,    A_NEW,     None),
    (F_CPP, "cpp_relereset", RE_OLD,  RE_NEW,    None),
    (F_CPP, "cpp_probe",   P_OLD,     P_NEW,     'fMove={:.1f} takeover={}'),
    (F_CPP, "cpp_probe2",  P_TAIL_OLD, P_TAIL_NEW, "snapForeignMove, snapForeignTakeover,"),
]


def file_eol(path):
    """EOL comes from the FILE. A single-line anchor contains no newline, so the
    anchor itself can never tell us the convention (v1.09: this mistake wrote 78
    bare LF into a pure-CRLF file and every post-condition still passed)."""
    with open(path, "rb") as f:
        b = f.read()
    crlf = b.count(b"\r\n")
    return "\r\n" if crlf > (b.count(b"\n") - crlf) else "\n"


def splice_ok(text, idx):
    """A match that starts in the middle of a token is not an insertion point.
    v1.09: the anchor `bool SKSEAPI SKSEPlugin_Load(...)` matched inside
    `extern "C" DLLEXPORT bool SKSEAPI ...` and moved `dllexport` onto a static
    function (error C2201)."""
    if idx == 0:
        return True
    return text[idx - 1] in ("\n", "\t")


def main():
    do_apply = "--apply" in sys.argv
    do_revert = "--revert" in sys.argv

    by_file = {}
    for path, label, old, new, want in PLAN:
        by_file.setdefault(path, []).append((label, old, new, want))

    results = []
    for path, edits in by_file.items():
        with open(path, "rb") as f:
            raw = f.read()
        eol = file_eol(path)
        text = raw.decode("utf-8")
        print(f"--- {path}  ({len(raw)} B, eol={eol!r})")

        if not do_revert and MARK in text:
            print(f"    REFUSED: marker already present -- patch already applied")
            return 1

        for label, old, new, want in edits:
            o = old.replace("\n", eol)
            n = new.replace("\n", eol)
            c = text.count(o)
            print(f"    {label:15s} count={c}")
            if c != 1:
                print(f"    REFUSED, nothing written ({label}: want 1)")
                return 2
            if not splice_ok(text, text.index(o)):
                print(f"    REFUSED, nothing written ({label}: splice guard)")
                return 3
            if do_revert:
                if text.count(n) != 1:
                    print(f"    REFUSED, nothing written (revert {label})")
                    return 4
                text = text.replace(n, o, 1)
            else:
                text = text.replace(o, n, 1)
        results.append((path, raw, text, eol, edits))

    # ---- post-conditions on the RESULT text ----
    bad = []
    for path, raw, text, eol, edits in results:
        if do_revert:
            if MARK in text:
                bad.append(f"{path}: marker still present after revert")
            continue
        for label, old, new, want in edits:
            if want and want not in text:
                bad.append(f"{path}:{label} missing {want!r}")
        if text.count(MARK) != 1 and path == F_CPP:
            # the marker appears once as a comment in the takeover block
            bad.append(f"{path}: marker count {text.count(MARK)} != 1")
    print("post-conditions:", "PASS" if not bad else f"FAIL {bad}")
    if bad:
        print("REFUSED, nothing written")
        return 5

    if not do_apply:
        print("DRY RUN ok -- re-run with --apply to write")
        return 0

    for path, raw, text, eol, edits in results:
        out = text.encode("utf-8")
        with open(path, "wb") as f:
            f.write(out)
        print(f"written {path}: {len(raw)} B -> {len(out)} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
