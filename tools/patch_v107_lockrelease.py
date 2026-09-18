#!/usr/bin/env python3
"""v1.07 - give the camera-family lock a RELEASE PATH.

WHY
---
v1.00 added the projection-family fingerprint and wrote, in its own comment,
"a different projection family may NEVER re-acquire". That fixed the v0.93 CTD
but produced a state machine with no transition out of the locked state:

    grep -rn 'snapLockHave\\|snapLockProjValid\\|snapLockProj00' src/FrameGen.cpp
    -> snapLockHave      set true at 872, 931;  never false
    -> snapLockProjValid set true at 946;       never false
    -> snapLockProj00    assigned at 945;       never reset

So whichever family got locked held the stream until the process exited.

WHAT THE 22:02 (v1.06) RUN SHOWED
---------------------------------
    serial=861  menu=857 world=4   proj00=0.8391   <- heartbeat proj00 is
    serial=951  menu=857 world=94  proj00=0.8391      snapLockProj00 (line 1371)
    lock(pub/hold/re/still)=11821/2725/2416/0  famRej=309
    clipDev=0.000015  curVP=15.0006 prevVP=15.0006     <- clipToPrev = identity

    [CAM] #8048 family rejected: proj00=0.8391 locked=0.149184 ratio=5.6246
          pos=(-243.0,-415.3,118.6) - another render pass, never re-acquires
    [CAM] #8058 non-affine w=0 ACCEPTED row3=(-0.00391655,0.999991,0.0015,0)
          det3=-2.52504 pos=(-243.0,-415.3,118.6)

row3=(-0.00391655,0.999991,0.0015,0) with [3][3]==0 is the exact matrix
FrameGen.h:326-332 already identified in v0.86 as "not a camera at all, but a
mis-offset read of the perFrame constant buffer". It is what owns the lock at
the end of the run. The world camera (0.149184) arrived every frame and was
refused 309 times; still=0 proves the release threshold was unreachable.

HOW IT GOT THERE - the v1.03 magnitude-class escape is a one-way ratchet
-----------------------------------------------------------------------
    if (unitProj != lockUnit) sameFamily = true;      // FrameGen.cpp:842-852

combined with the accept-site refresh

    if (projOk) { snapLockProj00 = proj00; }          // FrameGen.cpp:944-947

walks the lock. From the log, in order:

    #1  acquire  proj00=0.149184                          -> lock 0.149184
    #2  esc 1.0       vs locked 0.149184 -> adopt          -> lock 1.0
    #4  esc 0.149184  vs locked 1.0      -> adopt          -> lock 0.149184
    #11 esc 1.0       vs locked 0.149184 -> adopt          -> lock 1.0
    #13 esc 0.149184  vs locked 1.0      -> adopt          -> lock 0.149184
    #20 esc 1.0       vs locked 0.149184 -> adopt          -> lock 1.0

`[CAM] projection family: magnitude classes differ (proj00=1 locked=0.149184)
- treating as a legal second camera, not a render pass (v1.03)` is logged
exactly once - the escape fired. While the lock reads 1.0 (a unit projection)
EVERY non-unit arrival is a "legal second camera", including 0.8391. Once the
lock reads 0.8391 the ratio test refuses the world camera
(0.149184/0.8391 = 0.178) and the old code returned false forever.

The escape was a workaround for the missing release path, not a
classification. With a release path it is both unnecessary and the thing that
walks the lock into the wrong family, so it goes.

THE RELEASE - and it is already computed
----------------------------------------
Streamline computes c.reset = (menuEdgeUp || camEdgeDown) and passes it to
DLSS-G as "discard your history". The reprojection history AND the locked
camera belong to the world that just went away, but the lock never heard about
it. The 22:02 log confirms the edge fires exactly where it is needed:
Transfusion's [MOTION] dump on frame 861 (one frame after the main menu closed
at menu=857) shows `reset=1` on call=0.

Two things raise the request:
  1. the menu open/close transition, at the point menuEdges is incremented -
     deterministic, does not depend on when the pending flag is consumed;
  2. c.reset itself, which also covers the camera-discontinuity edge.

This patch also counts foreign-family arrivals toward snapLockStill. Before
this they returned without touching it, which is why `still` printed 0 for a
whole run with famRej=309. It is a secondary trigger - in the stuck case the
wrong family keeps "continuing" itself and resets the counter, so the reset
edge is the load-bearing part - but it is correct to count them and the
`still={}/{}` field will show the real number next run.

Default is a dry run. Pass --apply to write.
"""

import sys
import hashlib
from pathlib import Path

ROOT = Path(r"D:/Modding/DynamicShaderFrameGen")
APPLY = "--apply" in sys.argv

FG_C = ROOT / "src" / "FrameGen.cpp"
FG_H = ROOT / "src" / "FrameGen.h"
SL_C = ROOT / "src" / "Streamline.cpp"


def eol_of(path: Path) -> bytes:
    b = path.read_bytes()
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    return b"\r\n" if crlf > lf else b"\n"


def norm(chunk, eol: bytes):
    """Rewrite a \\n-delimited anchor into the target file's EOL.

    The anchors above are written with \\n for readability. Streamline.cpp is
    pure CRLF, so an un-normalised anchor matches 0 times - which is exactly
    what the first dry run reported. Accepts bytes or a list of byte-lines.
    """
    if isinstance(chunk, list):
        return [norm(c, eol) for c in chunk]
    return chunk.replace(b"\r\n", b"\n").replace(b"\n", eol)


def eol_after(path: Path, anchor: bytes) -> bytes:
    """The EOL actually used by the line that contains `anchor`."""
    b = path.read_bytes()
    i = b.find(anchor)
    if i < 0:
        raise SystemExit(f"REFUSED: anchor not found for eol probe: {anchor[:60]!r}")
    j = b.find(b"\n", i)
    if j < 0:
        raise SystemExit("REFUSED: anchor is on the last line, cannot probe eol")
    return b"\r\n" if b[j - 1:j] == b"\r" else b"\n"


def insert_after(src: bytes, anchor: bytes, lines: list, eol: bytes) -> bytes:
    """Insert `lines` immediately AFTER the LAST line of `anchor`.

    Two harness defects were found here, both by the assertions in the caller
    rather than by reading the code:

    1. `find(b"\\n", i)` locates the newline of the anchor's FIRST line, so a
       multi-line anchor got split. With

           if (isMenuOpen)\\n\\t\\t\\t\\tmenuResetPending = true;   // consumed ...

       the block landed BETWEEN the `if` and its statement, leaving
       menuResetPending unconditional and the indentation broken. The anchor's
       own end (`i + len(anchor)`) is the correct place to look.

    2. The inserted lines need a TRAILING terminator and no leading one.
       `eol + ln` left the last line unterminated and glued the next source
       statement onto it; `eol + ln + eol` inserted a blank line before every
       line (343 -> 389 lines where 366 was expected).
    """
    i = src.find(anchor)
    assert i >= 0, "anchor not found"
    j = src.find(b"\n", i + len(anchor) - 1)
    assert j >= 0, "anchor ends on the last line, no newline to insert after"
    add = b"".join(ln + eol for ln in lines)
    return src[:j + 1] + add + src[j + 1:]


# ---------------------------------------------------------------- FrameGen.h
H_ANCHOR = b"\tstd::uint64_t snapLockFamilyRej = 0;  // arrivals refused for being another family"
H_NEW = [
    b"\t// ---- v1.07: the family lock gets a RELEASE PATH ----",
    b"\t// v1.00 wrote \"a different projection family may NEVER re-acquire\" and",
    b"\t// stopped there. The result is a state machine with no transition out of",
    b"\t// the locked state: snapLockHave / snapLockProjValid / snapLockProj00 are",
    b"\t// only ever SET, never cleared. Whichever family got locked held the",
    b"\t// stream until the process exited, and the real camera was refused",
    b"\t// forever.",
    b"\t//",
    b"\t// 22:02 run (v1.06): the world camera ProjUnj[0][0]=0.149184 arrived",
    b"\t// every frame and was rejected 309 times as \"another render pass\"; the",
    b"\t// lock ended on 0.8391 - pos (-243.0,-415.3,118.6), whose row3",
    b"\t// (-0.00391655,0.999991,0.0015,0) is the matrix v0.86 had already",
    b"\t// identified as a mis-offset read of the perFrame constant buffer, not a",
    b"\t// camera. lock(hold/re)=2725/2416 with still=0: the release threshold",
    b"\t// was unreachable. clipToPrev stayed identity, so the picture did not",
    b"\t// advance while 4x presented.",
    b"\t//",
    b"\t// The caller already computes the edge that belongs here - c.reset, the",
    b"\t// menu open/close and camera-discontinuity edge - and uses it to tell",
    b"\t// DLSS-G to discard its history. The locked camera is part of that same",
    b"\t// history. It hears about it now.",
    b"\tbool snapLockReleasePending = false;  // raised by the reset/menu edge",
    b"\tstd::uint64_t snapLockReleased = 0;   // times the family lock was released",
]

# ------------------------------------------------------------- Streamline.cpp
SL_ANCHOR1 = b"\t\t\tif (isMenuOpen)\n\t\t\t\tmenuResetPending = true;   // consumed by CheckFrameConstants"
SL_NEW1 = [
    b"\t\t\t// v1.07: the camera-family lock has no release path of its own.",
    b"\t\t\t// This transition is the one place it must move - leaving a menu",
    b"\t\t\t// means the locked camera describes a world that is gone. Raised on",
    b"\t\t\t// BOTH edges rather than relying on when menuResetPending is later",
    b"\t\t\t// consumed, because the consumer (CheckFrameConstants) is skipped",
    b"\t\t\t// for as long as the menu is open.",
    b"\t\t\tGet().snapLockReleasePending = true;",
]

SL_ANCHOR2 = (
    b"\t\tif (c.reset == sl::Boolean::eTrue)\n"
    b"\t\t\t++diag.resetTrue;"
)
SL_NEW2 = (
    b"\t\tif (c.reset == sl::Boolean::eTrue) {\n"
    b"\t\t\t++diag.resetTrue;\n"
    b"\t\t\t// v1.07: hand the same edge to the camera lock. c.reset already\n"
    b"\t\t\t// tells DLSS-G to discard its history; the locked camera family is\n"
    b"\t\t\t// part of that history. This also covers camEdgeDown, which the\n"
    b"\t\t\t// menu transition above does not.\n"
    b"\t\t\tGet().snapLockReleasePending = true;\n"
    b"\t\t}"
)

# -------------------------------------------------------------- FrameGen.cpp
FG_ANCHOR1 = (
    b"\t\tstatic bool snapLockAltFamilyLogged = false;\n"
    b"\n"
    b"\t\t{\n"
    b"\t\t\tbool sameFamily = true;"
)
FG_NEW1 = (
    b"\t\tstatic bool snapLockAltFamilyLogged = false;\n"
    b"\n"
    b"\t\t// ---- v1.07: consume a release raised by the reset / menu edge ---------\n"
    b"\t\t// The edge is computed in Streamline and already tells DLSS-G to discard\n"
    b"\t\t// its reprojection history. The locked camera family is part of that\n"
    b"\t\t// same history, and until v1.07 it had no way to hear about it - which\n"
    b"\t\t// is why the 22:02 run kept publishing the 3D-menu family after the\n"
    b"\t\t// main menu had closed and the world had started.\n"
    b"\t\tif (snapLockReleasePending) {\n"
    b"\t\t\tsnapLockReleasePending = false;\n"
    b"\t\t\t++snapLockReleased;\n"
    b"\t\t\tif (snapLockReleased <= 5u) {\n"
    b"\t\t\t\tSKSE::log::info(\"[CAM] #{} lock RELEASED on the reset edge (was \"\n"
    b"\t\t\t\t\t\"proj00={:.6g} famRej={}) - the next arrival re-acquires\",\n"
    b"\t\t\t\t\tsnapArrivals, snapLockProjValid ? snapLockProj00 : 0.0f,\n"
    b"\t\t\t\t\tsnapLockFamilyRej);\n"
    b"\t\t\t}\n"
    b"\t\t\tsnapLockHave = false;\n"
    b"\t\t\tsnapLockProjValid = false;\n"
    b"\t\t\tsnapHaveLast = false;\n"
    b"\t\t\tsnapLockStill = 0;\n"
    b"\t\t}\n"
    b"\n"
    b"\t\t{\n"
    b"\t\t\tbool sameFamily = true;"
)

FG_ANCHOR2 = (
    b"\t\t\t\tconst bool unitProj = (proj00 > 0.995f) && (proj00 < 1.005f);\n"
    b"\t\t\t\tconst bool lockUnit = (snapLockProj00 > 0.995f) && (snapLockProj00 < 1.005f);\n"
    b"\t\t\t\tif (unitProj != lockUnit) {\n"
    b"\t\t\t\t\t// Different magnitude classes: a DIFFERENT camera, but a legal\n"
    b"\t\t\t\t\t// one. The lock must be allowed to move to it, otherwise a unit\n"
    b"\t\t\t\t\t// projection seen once pins the lock for good and every real\n"
    b"\t\t\t\t\t// frame is rejected forever. Only a 2D render pass would be a\n"
    b"\t\t\t\t\t// genuine intruder, and none has ever been observed at\n"
    b"\t\t\t\t\t// |proj00| == 1.0; admitting one costs a lock refresh, while\n"
    b"\t\t\t\t\t// refusing a legal camera costs the whole feature.\n"
    b"\t\t\t\t\tsameFamily = true;\n"
    b"\t\t\t\t\tif (!snapLockAltFamilyLogged) {\n"
    b"\t\t\t\t\t\tsnapLockAltFamilyLogged = true;\n"
    b"\t\t\t\t\t\tSKSE::log::info(\"[CAM] projection family: magnitude classes differ \"\n"
    b"\t\t\t\t\t\t\t\"(proj00={:.6g} locked={:.6g}) - treating as a legal second \"\n"
    b"\t\t\t\t\t\t\t\"camera, not a render pass (v1.03)\", proj00, snapLockProj00);\n"
    b"\t\t\t\t\t}\n"
    b"\t\t\t\t} else {\n"
    b"\t\t\t\t\tconst float ratio = proj00 / snapLockProj00;\n"
    b"\t\t\t\t\t// +-2%: two cameras of the SAME magnitude class sit far enough\n"
    b"\t\t\t\t\t// apart to separate cleanly (the two real world families are\n"
    b"\t\t\t\t\t// 5.62x apart) while tolerating float drift and a\n"
    b"\t\t\t\t\t// resolution/FOV nudge.\n"
    b"\t\t\t\t\tsameFamily = (ratio > 0.98f) && (ratio < 1.02f);\n"
    b"\t\t\t\t}"
)
FG_NEW2 = (
    b"\t\t\t\t// v1.07: the v1.03 magnitude-class escape is GONE.\n"
    b"\t\t\t\t//\n"
    b"\t\t\t\t// It admitted any arrival whenever exactly one of the two\n"
    b"\t\t\t\t// projections was a unit projection:\n"
    b"\t\t\t\t//     if (unitProj != lockUnit) sameFamily = true;\n"
    b"\t\t\t\t// and because the accept path then refreshed snapLockProj00 to\n"
    b"\t\t\t\t// the newly accepted arrival, the escape could never settle. The\n"
    b"\t\t\t\t// 22:02 log is that walk, verbatim:\n"
    b"\t\t\t\t//\n"
    b"\t\t\t\t//   #1  acquire  proj00=0.149184                -> lock 0.149184\n"
    b"\t\t\t\t//   #2  esc 1.0      vs locked 0.149184 -> adopt  -> lock 1.0\n"
    b"\t\t\t\t//   #4  esc 0.149184 vs locked 1.0      -> adopt  -> lock 0.149184\n"
    b"\t\t\t\t//   #11 esc 1.0      vs locked 0.149184 -> adopt  -> lock 1.0\n"
    b"\t\t\t\t//   #13 esc 0.149184 vs locked 1.0      -> adopt  -> lock 0.149184\n"
    b"\t\t\t\t//\n"
    b"\t\t\t\t// While the lock reads 1.0 (a unit projection) EVERY non-unit\n"
    b"\t\t\t\t// arrival counts as a legal second camera - including 0.8391,\n"
    b"\t\t\t\t// the 3D-menu family. Once the lock reads 0.8391 the ratio test\n"
    b"\t\t\t\t// refuses the world camera (0.149184/0.8391 = 0.178) and the old\n"
    b"\t\t\t\t// code returned false forever.\n"
    b"\t\t\t\t//\n"
    b"\t\t\t\t// The escape was a workaround for the missing release path, not\n"
    b"\t\t\t\t// a classification. With the release added above it is both\n"
    b"\t\t\t\t// unnecessary and the thing that walks the lock into the wrong\n"
    b"\t\t\t\t// family, so the ratio test stands alone again.\n"
    b"\t\t\t\tconst float ratio = proj00 / snapLockProj00;\n"
    b"\t\t\t\tsameFamily = (ratio > 0.98f) && (ratio < 1.02f);"
)

FG_ANCHOR3 = (
    b"\t\t\t\tif (!sameFamily) {\n"
    b"\t\t\t\t\t++snapLockFamilyRej;\n"
    b"\t\t\t\t\tif (snapLockFamilyRej <= 3u || (snapLockFamilyRej % 500u) == 0u) {\n"
    b"\t\t\t\t\t\tSKSE::log::info(\"[CAM] #{} family rejected: proj00={:.6g} locked={:.6g} \"\n"
    b"\t\t\t\t\t\t\t\"ratio={:.4f} pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} - another render \"\n"
    b"\t\t\t\t\t\t\t\"pass, never re-acquires\",\n"
    b"\t\t\t\t\t\t\tsnapArrivals, proj00, snapLockProj00,\n"
    b"\t\t\t\t\t\t\tsnapLockProjValid ? (proj00 / snapLockProj00) : 0.0f,\n"
    b"\t\t\t\t\t\t\tpx, py, pz, std::sqrt(d2));\n"
    b"\t\t\t\t\t}\n"
    b"\t\t\t\t\tif (d2 > kCamJumpTol2) ++snapRejectJump;\n"
    b"\t\t\t\t\treturn false;\n"
    b"\t\t\t\t}"
)
FG_NEW3 = (
    b"\t\t\t\tif (!sameFamily) {\n"
    b"\t\t\t\t\t++snapLockFamilyRej;\n"
    b"\t\t\t\t\t// v1.07: this branch used to return WITHOUT touching snapLockStill,\n"
    b"\t\t\t\t\t// so `still` stayed 0 for a whole run and the release below could\n"
    b"\t\t\t\t\t// never be reached from here. The 22:02 run printed\n"
    b"\t\t\t\t\t// lock(pub/hold/re/still)=11821/2725/2416/0 with famRej=309 - 309\n"
    b"\t\t\t\t\t// refusals and not one of them counted.\n"
    b"\t\t\t\t\t++snapLockStill;\n"
    b"\t\t\t\t\tif (snapLockFamilyRej <= 3u || (snapLockFamilyRej % 500u) == 0u) {\n"
    b"\t\t\t\t\t\tSKSE::log::info(\"[CAM] #{} family rejected: proj00={:.6g} locked={:.6g} \"\n"
    b"\t\t\t\t\t\t\t\"ratio={:.4f} pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} still={}/{}\",\n"
    b"\t\t\t\t\t\t\tsnapArrivals, proj00, snapLockProj00,\n"
    b"\t\t\t\t\t\t\tsnapLockProjValid ? (proj00 / snapLockProj00) : 0.0f,\n"
    b"\t\t\t\t\t\t\tpx, py, pz, std::sqrt(d2), snapLockStill, kCamStillTol);\n"
    b"\t\t\t\t\t}\n"
    b"\t\t\t\t\tif (snapLockStill < kCamStillTol) {\n"
    b"\t\t\t\t\t\tif (d2 > kCamJumpTol2) ++snapRejectJump;\n"
    b"\t\t\t\t\t\treturn false;\n"
    b"\t\t\t\t\t}\n"
    b"\t\t\t\t\t// v1.07: the locked family has failed to continue kCamStillTol\n"
    b"\t\t\t\t\t// times in a row, which is the same evidence v0.94 used to\n"
    b"\t\t\t\t\t// re-acquire. v1.00 refused this because a foreign camera arriving\n"
    b"\t\t\t\t\t// monotonically would adopt itself forever - but with the v1.03\n"
    b"\t\t\t\t\t// escape removed above, reaching here requires 90 consecutive\n"
    b"\t\t\t\t\t// non-continuations, which a live single-source stream reset every\n"
    b"\t\t\t\t\t// frame never produces. Secondary trigger only: in the stuck case\n"
    b"\t\t\t\t\t// the wrong family keeps continuing itself and resets the counter,\n"
    b"\t\t\t\t\t// so the reset edge above is the load-bearing part. Counting them\n"
    b"\t\t\t\t\t// is still correct, and the still={}/{} field now reports the truth.\n"
    b"\t\t\t\t\tSKSE::log::info(\"[CAM] #{} lock RELEASED after {}/{} non-continuations - \"\n"
    b"\t\t\t\t\t\t\"locked proj00={:.6g} is dead, adopting proj00={:.6g} \"\n"
    b"\t\t\t\t\t\t\"pos=({:.1f},{:.1f},{:.1f}) dist={:.1f}\",\n"
    b"\t\t\t\t\t\tsnapArrivals, snapLockStill, kCamStillTol,\n"
    b"\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f,\n"
    b"\t\t\t\t\t\tproj00, px, py, pz, std::sqrt(d2));\n"
    b"\t\t\t\t\t++snapLockReleased;\n"
    b"\t\t\t\t\tsnapLockHave = false;\n"
    b"\t\t\t\t\tsnapLockProjValid = false;\n"
    b"\t\t\t\t\tsnapHaveLast = false;\n"
    b"\t\t\t\t\tsnapLockStill = 0;\n"
    b"\t\t\t\t\t// falls through into the re-adopt below: this arrival establishes\n"
    b"\t\t\t\t\t// the new lock. The \"same-family step break\" line below is reused\n"
    b"\t\t\t\t\t// for it and prints the real proj00, so the log stays honest.\n"
    b"\t\t\t\t}"
)


def main():
    files = {}
    for p in (FG_H, SL_C, FG_C):
        files[p] = p.read_bytes()

    before = {p: hashlib.md5(b).hexdigest() for p, b in files.items()}

    # Anchors are authored with \n; convert them to each target's real EOL.
    eol_c = eol_of(FG_C)   # LF
    eol_sl = eol_of(SL_C)  # CRLF

    def n_c(b):
        return norm(b, eol_c)

    def n_sl(b):
        return norm(b, eol_sl)

    edits = [
        ("FrameGen.h", FG_H, files[FG_H], H_ANCHOR, H_NEW, None, "insert"),
        ("Streamline.cpp/menu-edge", SL_C, files[SL_C], n_sl(SL_ANCHOR1), n_sl(SL_NEW1), None, "insert"),
        ("Streamline.cpp/reset-edge", SL_C, files[SL_C], n_sl(SL_ANCHOR2), n_sl(SL_NEW2), None, "replace"),
        ("FrameGen.cpp/release-consume", FG_C, files[FG_C], n_c(FG_ANCHOR1), n_c(FG_NEW1), None, "replace"),
        ("FrameGen.cpp/kill-escape", FG_C, files[FG_C], n_c(FG_ANCHOR2), n_c(FG_NEW2), None, "replace"),
        ("FrameGen.cpp/foreign-release", FG_C, files[FG_C], n_c(FG_ANCHOR3), n_c(FG_NEW3), None, "replace"),
    ]

    # Guards: idempotence markers per target file.
    markers = {
        FG_H: b"snapLockReleasePending = false;  // raised by the reset/menu edge",
        SL_C: b"Get().snapLockReleasePending = true;",
        FG_C: b"if (snapLockReleasePending) {",
    }

    ok = True
    for p, m in markers.items():
        if m in files[p]:
            print(f"REFUSED: {p.name}: MARKER ALREADY PRESENT - patch has already run")
            ok = False

    for label, path, src, old, new, _g, mode in edits:
        n = src.count(old)
        status = "OK" if n == 1 else "REFUSED"
        print(f"[{label}] count(old) = {n}  ({status})")
        if n != 1:
            ok = False

    if not ok:
        print("\nREFUSED, nothing written")
        return 1

    # Apply, chaining in memory so a dry run reports the COMBINED result.
    #
    # The first version re-read path.read_bytes() here. In --apply mode that is
    # correct (it also proves the previous write landed), but in dry-run mode
    # nothing is ever written, so every edit for the same file started from the
    # ORIGINAL bytes and silently discarded the one before it. The post-condition
    # block then inspected a text that contained only the last edit, and the
    # assertions failed for the right reason while pointing at the wrong cause:
    #   AssertionError: post-condition missing in FrameGen.cpp:
    #   'if (snapLockReleasePending) {'
    # Chaining from files[path] makes the dry run and the apply path agree.
    for label, path, _src, old, new, _g, mode in edits:
        cur = files[path]
        assert cur.count(old) == 1, f"lost anchor after earlier edit: {label}"
        n_before = cur.count(b"\n")
        if mode == "replace":
            cur = cur.replace(old, new, 1)
            # A replacement must add exactly the lines the new text has.
            expect = n_before + new.count(b"\n") - old.count(b"\n")
        else:
            e = eol_after(path, old)
            cur = insert_after(cur, old, new, e)
            # An insert must add exactly len(new) lines - each with its own
            # terminator. If the last one is unterminated the count comes out
            # one short and the next source line gets glued on.
            expect = n_before + len(new)
        n_after = cur.count(b"\n")
        if n_after != expect:
            raise SystemExit(
                f"REFUSED, nothing written: {label}: line count {n_before} -> "
                f"{n_after}, expected {expect} (insert/replace EOL bug)")
        if mode == "insert":
            # The anchor must survive the insert as one contiguous run. This is
            # what catches an insert landing in the MIDDLE of a multi-line
            # anchor - the line count is identical, so only this test sees it.
            if cur.count(old) != 1:
                raise SystemExit(
                    f"REFUSED, nothing written: {label}: the anchor was split by "
                    f"the insert (found {cur.count(old)} occurrences after, expected 1)")
        files[path] = cur
        if APPLY:
            path.write_bytes(cur)
            print(f"  wrote {path.name} -> {len(cur)} bytes, lines +{n_after - n_before}")

    if not APPLY:
        print("\nDRY RUN OK - rerun with --apply to write")
        # post-conditions that must hold in the new text (checked on result)
        res = files[FG_C].decode("utf-8", "replace")
        for need in ("if (snapLockReleasePending) {",
                     "++snapLockStill;",
                     "snapLockStill < kCamStillTol",
                     "snapLockProjValid = false;",
                     "lock RELEASED after",
                     "adopting proj00="):
            assert need in res, f"post-condition missing in FrameGen.cpp: {need!r}"
        # Check the CODE form, not the bare identifier: FG_NEW2's comment quotes
        # "if (unitProj != lockUnit) sameFamily = true;" to explain what was
        # removed, so a substring test on "unitProj" reports a false failure.
        assert "const bool unitProj" not in res, \
            "post-condition: the v1.03 escape still present in FrameGen.cpp"
        assert "const bool lockUnit" not in res, \
            "post-condition: the v1.03 escape still present in FrameGen.cpp"
        res_sl = files[SL_C].decode("utf-8", "replace")
        assert res_sl.count("Get().snapLockReleasePending = true;") == 2, "expected 2 raise sites in Streamline.cpp"
        res_h = files[FG_H].decode("utf-8", "replace")
        assert "snapLockReleased = 0;" in res_h, "member missing in FrameGen.h"
        print("post-conditions: 7/7 OK")
        return 0

    print("\nPost-conditions (on written files):")
    res = FG_C.read_bytes().decode("utf-8", "replace")
    checks = [
        ("FrameGen.cpp release consumer present", "if (snapLockReleasePending) {" in res),
        ("FrameGen.cpp foreign branch counts still", "++snapLockStill;" in res),
        ("FrameGen.cpp clears snapLockHave", "snapLockHave = false;" in res),
        ("FrameGen.cpp clears snapLockProjValid", "snapLockProjValid = false;" in res),
        ("FrameGen.cpp clears snapHaveLast", "snapHaveLast = false;" in res),
        ("FrameGen.cpp escape REMOVED", "const bool unitProj" not in res),
        ("FrameGen.cpp release log present", "lock RELEASED" in res),
        ("Streamline.cpp 2 raise sites", SL_C.read_bytes().count(b"Get().snapLockReleasePending = true;") == 2),
        ("FrameGen.h new members", b"snapLockReleasePending = false;" in FG_H.read_bytes()),
    ]
    bad = 0
    for name, okk in checks:
        print(f"  {'OK  ' if okk else 'FAIL'} {name}")
        if not okk:
            bad += 1

    print("\nEOL regression:")
    for p in (FG_H, SL_C, FG_C):
        b = p.read_bytes()
        crlf = b.count(b"\r\n")
        bare = b.count(b"\n") - crlf
        print(f"  {p.name:16s} {len(b):7d} B  CRLF={crlf:5d} bare_LF={bare:5d}")

    print(f"\nmd5 before -> after:")
    for p in (FG_H, SL_C, FG_C):
        print(f"  {p.name:16s} {before[p]} -> {hashlib.md5(p.read_bytes()).hexdigest()}")

    print("\nRESULT: " + ("FAIL" if bad else "OK"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
