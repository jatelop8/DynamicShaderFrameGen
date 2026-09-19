#!/usr/bin/env python3
"""v1.16: select the camera write against ground truth, and make the census honest.

Two changes, both justified by the 22:02 run.

(1) BEHAVIOUR -- ground-truth takeover.
    Every gate in AcceptCameraSnapshot decides *which writer to believe* by
    looking at the writers themselves. The 22:02 run shows where that ends: at
    the world edge the lock released and re-acquired the FIRST arrival after it,
    that arrival was a parked pass (pos=(0,0,1), path frozen at 54.99 for the
    whole world), and because a parked family can never satisfy the v1.11
    moving-foreign takeover, the real camera was refused for the rest of the run
    (famRej 1114 -> 2671, 390/s).
    The engine can simply be asked: RE::PlayerCamera::cameraRoot is the live
    camera node, its world.translate is the eye position, and CameraPosAdjust
    carries the same quantity. An arrival within kPcMatchTol of it IS the camera
    write -- measured, not inferred. When one arrives while the lock sits on a
    different projection family, drop the lock so the normal acquire path takes
    it. Nothing else is touched; if the reference is unreadable, or no arrival is
    near it, this block does nothing at all.

(2) DIAGNOSTIC -- the census key was wrong and its budget was spent too early.
    v1.15 bucketed families with a 2% tolerance, so two writers with slightly
    different projections shared a bucket and their interleaved positions read as
    enormous motion (FAM[1]: moved=765, stepSum=318990 while nothing moved). Its
    per-motion log also had a 60-line budget that the menu consumed before the
    world began, so the world segment -- the only one that mattered -- produced no
    detail. v1.16 keys families at 0.01%, counts arrivals per family, and reports
    the per-axis span of the positions seen each second. span 0 = parked;
    span small with moved ~= arr = live camera; span hundreds = a merged bucket.

Usage:
    python tools/patch_v116_pctakeover.py            # dry run
    python tools/patch_v116_pctakeover.py --apply    # write
    python tools/patch_v116_pctakeover.py --revert   # undo the .cpp edits
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPP = ROOT / "src" / "FrameGen.cpp"
HDR = ROOT / "src" / "FrameGen.h"

MARKER = "v1.16: GROUND-TRUTH TAKEOVER"

# ---------------------------------------------------------------------------
# E1 -- FrameGen.h members
# ---------------------------------------------------------------------------
H_OLD = """\tstd::uint64_t snapFamLogged = 0;
\tbool snapFamOverflowLogged = false;
"""

H_NEW = """\tstd::uint64_t snapFamLogged = 0;
\tbool snapFamOverflowLogged = false;

\t// ---- v1.16: selection against the live player camera -------------------
\t// read/match/adopt are per-second counters reset by the [CAM] PC dump;
\t// snapPcAdopt is the cumulative total.
\tstd::uint64_t snapPcRead = 0;
\tstd::uint64_t snapPcMatch = 0;
\tstd::uint64_t snapPcAdopt = 0;
\tstd::uint64_t snapPcAdoptSec = 0;
\tfloat snapPcBestDist = 1.0e38f;
\tfloat snapPcBestProj = 0.0f;
\tfloat snapPcLast[3] = {};
\tbool snapPcSawAny = false;
\t// ---- v1.16: census detail, per family, per second ----------------------
\tstd::uint32_t snapFamArrSec[kSnapFamMax] = {};
\tstd::uint32_t snapFamSpanN[kSnapFamMax] = {};
\tfloat snapFamMinP[kSnapFamMax][3] = {};
\tfloat snapFamMaxP[kSnapFamMax][3] = {};
"""

# ---------------------------------------------------------------------------
# E2 -- constants
# ---------------------------------------------------------------------------
C_OLD = "\tconstexpr float kCamMoveEps = 0.05f;"

C_NEW = """\tconstexpr float kCamMoveEps = 0.05f;

\t// ---- v1.16: select the camera write by ground truth, not by inference ----
\t// PlayerCamera::cameraRoot->world.translate is the live eye position and
\t// CameraPosAdjust carries the same quantity, so an arrival within this many
\t// units of it is the camera write. Measured separations between the writers
\t// sharing this buffer are in the hundreds, so the boundary is not delicate.
\tconstexpr float kPcMatchTol = 20.0f;
\t// v1.16: family buckets are keyed on CameraProjUnjittered[0][0]. v1.15 used
\t// 2%, which merged distinct writers and made their interleaved positions read
\t// as motion (FAM[1]: moved=765 stepSum=318990 with nothing moving).
\tconstexpr float kSnapFamKeyTol = 1.0e-4f;"""

# ---------------------------------------------------------------------------
# E3 -- census block, spliced between two anchors
# ---------------------------------------------------------------------------
CENSUS_START = "\t\t// ---- v1.15 probe: MOTION PER FAMILY"
CENSUS_END = "\t\tconst bool usable = (px == px) && (py == py) && (pz == pz) &&"

CENSUS_NEW = """\t\t// ---- v1.16 probe: MOTION PER FAMILY, with a key that does not merge ----
\t\t// v1.15 bucketed families by ProjUnj[0][0] with a 2% tolerance. Two
\t\t// writers whose projection differed slightly therefore shared a bucket, and
\t\t// their interleaved positions produced enormous bogus steps: the 22:02 run
\t\t// reports FAM[1] proj00=1 moved=765 stepSum=318990 while nothing in the
\t\t// world was moving. Its per-motion log also had a 60-line budget that the
\t\t// menu consumed before the world began, so the world -- the only segment
\t\t// that mattered -- produced no detail at all, and the judgement table was
\t\t// read off a defective instrument.
\t\t//
\t\t// v1.16 keys families tightly (kSnapFamKeyTol: 0.01% instead of 2%), counts
\t\t// arrivals per family, and reports the per-axis SPAN of the positions seen
\t\t// within each second. That one number separates the three populations:
\t\t//   span 0.0000, moved 0        -> a parked writer
\t\t//   span small, moved ~= arr    -> a live camera
\t\t//   span hundreds               -> a bucket that has merged two writers
\t\t{
\t\t\tconst float famKey = a_src.CameraProjUnjittered.data[0][0];
\t\t\tstd::int32_t slot = -1;
\t\t\tfor (std::uint32_t i = 0; i < kSnapFamMax; ++i) {
\t\t\t\tif (snapFamSeen[i] &&
\t\t\t\t    std::fabs(snapFamProj[i] - famKey) <=
\t\t\t\t        std::fabs(famKey) * kSnapFamKeyTol + 1.0e-6f) {
\t\t\t\t\tslot = static_cast<std::int32_t>(i);
\t\t\t\t\tbreak;
\t\t\t\t}
\t\t\t}
\t\t\tif (slot < 0) {
\t\t\t\tfor (std::uint32_t i = 0; i < kSnapFamMax; ++i) {
\t\t\t\t\tif (!snapFamSeen[i]) {
\t\t\t\t\t\tsnapFamSeen[i] = true;
\t\t\t\t\t\tsnapFamProj[i] = famKey;
\t\t\t\t\t\tsnapFamHavePos[i] = false;
\t\t\t\t\t\tsnapFamMoved[i] = 0;
\t\t\t\t\t\tsnapFamStep[i] = 0.0f;
\t\t\t\t\t\tsnapFamArrSec[i] = 0;
\t\t\t\t\t\tsnapFamSpanN[i] = 0;
\t\t\t\t\t\tslot = static_cast<std::int32_t>(i);
\t\t\t\t\t\tbreak;
\t\t\t\t\t}
\t\t\t\t}
\t\t\t\tif (slot < 0 && !snapFamOverflowLogged) {
\t\t\t\t\t// v1.15b: never drop a family silently. If this fires, a family is
\t\t\t\t\t// going uncounted and its motion is invisible -- raise kSnapFamMax.
\t\t\t\t\tsnapFamOverflowLogged = true;
\t\t\t\t\tSKSE::log::info("[CAM] FAM table full ({} slots): proj00={:.6g} is NOT "
\t\t\t\t\t\t"being tracked - raise kSnapFamMax", kSnapFamMax, famKey);
\t\t\t\t}
\t\t\t}
\t\t\tif (slot >= 0) {
\t\t\t\tconst auto s = static_cast<std::uint32_t>(slot);
\t\t\t\tif (snapFamHavePos[s]) {
\t\t\t\t\tconst float mdX = px - snapFamPos[s][0];
\t\t\t\t\tconst float mdY = py - snapFamPos[s][1];
\t\t\t\t\tconst float mdZ = pz - snapFamPos[s][2];
\t\t\t\t\tconst float mstep = std::sqrt(mdX * mdX + mdY * mdY + mdZ * mdZ);
\t\t\t\t\tsnapFamStep[s] += mstep;
\t\t\t\t\tsnapFamStepTotal += mstep;
\t\t\t\t\tif (mstep > kCamMoveEps) {
\t\t\t\t\t\t++snapFamMoved[s];
\t\t\t\t\t\t++snapFamMovedTotal;
\t\t\t\t\t}
\t\t\t\t}
\t\t\t\tsnapFamPos[s][0] = px;
\t\t\t\tsnapFamPos[s][1] = py;
\t\t\t\tsnapFamPos[s][2] = pz;
\t\t\t\tsnapFamHavePos[s] = true;
\t\t\t\t++snapFamArrSec[s];
\t\t\t\tif (snapFamSpanN[s] == 0u) {
\t\t\t\t\tsnapFamMinP[s][0] = snapFamMaxP[s][0] = px;
\t\t\t\t\tsnapFamMinP[s][1] = snapFamMaxP[s][1] = py;
\t\t\t\t\tsnapFamMinP[s][2] = snapFamMaxP[s][2] = pz;
\t\t\t\t} else {
\t\t\t\t\tsnapFamMinP[s][0] = (std::min)(snapFamMinP[s][0], px);
\t\t\t\t\tsnapFamMinP[s][1] = (std::min)(snapFamMinP[s][1], py);
\t\t\t\t\tsnapFamMinP[s][2] = (std::min)(snapFamMinP[s][2], pz);
\t\t\t\t\tsnapFamMaxP[s][0] = (std::max)(snapFamMaxP[s][0], px);
\t\t\t\t\tsnapFamMaxP[s][1] = (std::max)(snapFamMaxP[s][1], py);
\t\t\t\t\tsnapFamMaxP[s][2] = (std::max)(snapFamMaxP[s][2], pz);
\t\t\t\t}
\t\t\t\t++snapFamSpanN[s];
\t\t\t}
\t\t}

"""

# ---------------------------------------------------------------------------
# E4 -- ground-truth takeover, inserted before the lock block
# ---------------------------------------------------------------------------
LOCK_ANCHOR = """\t\t{
\t\t\tbool sameFamily = true;
\t\t\t// v1.10: set when a moving foreign family took the anchor, so the
"""

LOCK_NEW = """\t\t// ---- v1.16: GROUND-TRUTH TAKEOVER ------------------------------------
\t\t// Every gate below decides which writer to believe by looking at the
\t\t// writers. The 22:02 run shows where that ends: at the world edge the lock
\t\t// released and re-acquired the FIRST arrival after it (v1.07b), that
\t\t// arrival was a parked pass -- pos=(0,0,1), path frozen at 54.99 for the
\t\t// whole world -- and because a parked family can never satisfy the v1.11
\t\t// moving-foreign takeover, the real camera was refused for the rest of the
\t\t// run (famRej 1114 -> 2671, 390/s).
\t\t//
\t\t// So do not infer. RE::PlayerCamera::cameraRoot is the live camera node and
\t\t// its world translation is the eye position; CameraPosAdjust carries the
\t\t// same quantity. An arrival within kPcMatchTol units of it IS the camera
\t\t// write. When one arrives while the lock sits on a DIFFERENT projection
\t\t// family, drop the lock and let the normal acquire path take this arrival.
\t\t// The "different family" test matters: without it the lock would be dropped
\t\t// once per arrival forever once the camera is locked, and v0.93 already
\t\t// measured what lock churn costs (CTD, path=845264).
\t\t{
\t\t\tconst auto* pc = RE::PlayerCamera::GetSingleton();
\t\t\tif (pc && pc->cameraRoot) {
\t\t\t\tconst auto& eye = pc->cameraRoot->world.translate;
\t\t\t\tconst float ex = px - eye.x;
\t\t\t\tconst float ey = py - eye.y;
\t\t\t\tconst float ez = pz - eye.z;
\t\t\t\tconst float pcDist = std::sqrt(ex * ex + ey * ey + ez * ez);
\t\t\t\t++snapPcRead;
\t\t\t\tsnapPcLast[0] = eye.x;
\t\t\t\tsnapPcLast[1] = eye.y;
\t\t\t\tsnapPcLast[2] = eye.z;
\t\t\t\tsnapPcSawAny = true;
\t\t\t\tif (pcDist < snapPcBestDist) {
\t\t\t\t\tsnapPcBestDist = pcDist;
\t\t\t\t\tsnapPcBestProj = proj00;
\t\t\t\t}
\t\t\t\tif (pcDist <= kPcMatchTol) {
\t\t\t\t\t++snapPcMatch;
\t\t\t\t\tconst bool lockOnOther =
\t\t\t\t\t    !(snapLockProjValid &&
\t\t\t\t\t      std::fabs(proj00 - snapLockProj00) <=
\t\t\t\t\t          std::fabs(snapLockProj00) * kSnapFamKeyTol + 1.0e-6f);
\t\t\t\t\tif (lockOnOther) {
\t\t\t\t\t\tsnapLockHave = false;
\t\t\t\t\t\tsnapHaveLast = false;
\t\t\t\t\t\t++snapPcAdopt;
\t\t\t\t\t\t++snapPcAdoptSec;
\t\t\t\t\t\tif (snapPcAdopt <= 5u || (snapPcAdopt % 500u) == 0u) {
\t\t\t\t\t\t\tSKSE::log::info("[CAM] #{} PC TAKEOVER (v1.16): this arrival is "
\t\t\t\t\t\t\t\t"{:.2f} units from the live player camera pos=({:.3f},{:.3f},{:.3f}) "
\t\t\t\t\t\t\t\t"pc=({:.3f},{:.3f},{:.3f}) proj00={:.6g} - dropping the lock so "
\t\t\t\t\t\t\t\t"it re-acquires on this arrival",
\t\t\t\t\t\t\t\tsnapArrivals, pcDist, px, py, pz,
\t\t\t\t\t\t\t\teye.x, eye.y, eye.z, proj00);
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t}

""" + LOCK_ANCHOR

# ---------------------------------------------------------------------------
# E5 -- per-second dump
# ---------------------------------------------------------------------------
DUMP_OLD = """\t\t\t\t\t// v1.15: the per-family census, one line per family per second. This is
\t\t\t\t\t// the block that decides the next repair: a family whose `moved` climbs
\t\t\t\t\t// is a LIVE camera reaching this hook, so the fix belongs in the accept
\t\t\t\t\t// rules; if every family shows moved=0, nothing here is alive and the
\t\t\t\t\t// source has to change.
\t\t\t\t\tfor (std::uint32_t fi = 0; fi < kSnapFamMax; ++fi) {
\t\t\t\t\t\tif (!snapFamSeen[fi])
\t\t\t\t\t\t\tcontinue;
\t\t\t\t\t\tSKSE::log::info("[CAM] FAM[{}] proj00={:.6g} moved={} stepSum={:.2f}",
\t\t\t\t\t\t\tfi, snapFamProj[fi], snapFamMoved[fi], snapFamStep[fi]);
\t\t\t\t\t}
"""

DUMP_NEW = """\t\t\t\t\t// v1.16: the per-family census, one line per family per second. Each line
\t\t\t\t\t// carries the arrival count, the number of steps over 5 cm, the total
\t\t\t\t\t// step, the per-axis span of the positions seen in that second and the
\t\t\t\t\t// last position. That is what decides the next repair: a parked writer
\t\t\t\t\t// spans 0.0000, a live camera spans a little and moves on most arrivals,
\t\t\t\t\t// and a bucket that merged two writers spans hundreds.
\t\t\t\t\tfor (std::uint32_t fi = 0; fi < kSnapFamMax; ++fi) {
\t\t\t\t\t\tif (!snapFamSeen[fi])
\t\t\t\t\t\t\tcontinue;
\t\t\t\t\t\tSKSE::log::info("[CAM] FAM[{}] proj00={:.6g} arr={} moved={} stepSum={:.2f} "
\t\t\t\t\t\t\t"span=({:.4f},{:.4f},{:.4f}) last=({:.4f},{:.4f},{:.4f})",
\t\t\t\t\t\t\tfi, snapFamProj[fi], snapFamArrSec[fi], snapFamMoved[fi], snapFamStep[fi],
\t\t\t\t\t\t\tsnapFamSpanN[fi] ? (snapFamMaxP[fi][0] - snapFamMinP[fi][0]) : 0.0f,
\t\t\t\t\t\t\tsnapFamSpanN[fi] ? (snapFamMaxP[fi][1] - snapFamMinP[fi][1]) : 0.0f,
\t\t\t\t\t\t\tsnapFamSpanN[fi] ? (snapFamMaxP[fi][2] - snapFamMinP[fi][2]) : 0.0f,
\t\t\t\t\t\t\tsnapFamPos[fi][0], snapFamPos[fi][1], snapFamPos[fi][2]);
\t\t\t\t\t\tsnapFamArrSec[fi] = 0;
\t\t\t\t\t\tsnapFamSpanN[fi] = 0;
\t\t\t\t\t}
\t\t\t\t\t// v1.16: the ground-truth comparison, per second. If `best` stays in the
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

EDITS = [
    ("H members", HDR, H_OLD, H_NEW),
    ("constants", CPP, C_OLD, C_NEW),
    ("census block", CPP, None, None),   # spliced, handled separately
    ("pc takeover", CPP, LOCK_ANCHOR, LOCK_NEW),
    ("per-second dump", CPP, DUMP_OLD, DUMP_NEW),
]

POST = [
    ("marker in cpp", None, None),
]


def eol_of(path: pathlib.Path) -> bytes:
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    return b"\r\n" if crlf >= bare else b"\n"


def to_eol(text: str, eol: bytes) -> str:
    return text.replace("\r\n", "\n").replace("\n", eol.decode())


def check(text: str, needle: str, want: int, label: str) -> bool:
    got = text.count(needle)
    flag = "OK " if got == want else "** "
    print(f"  {flag}{label}: count={got} want={want}")
    return got == want


def main() -> int:
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    eol_cpp = eol_of(CPP)
    eol_hdr = eol_of(HDR)
    print(f"EOL: cpp={eol_cpp!r} hdr={eol_hdr!r}")

    for p in (CPP, HDR):
        raw = p.read_bytes()
        crlf = raw.count(b"\r\n")
        bare = raw.count(b"\n") - crlf
        print(f"  {p.name}: {len(raw)} bytes, CRLF={crlf}, bareLF={bare}")

    # NOTE: read/write as BYTES. Path.read_text() applies universal-newline
    # translation, which silently turns the CRLF text into LF; every anchor then
    # stops matching and -- worse -- write_text would rewrite the whole file in
    # LF. Both were caught by the post-conditions on the first dry run.
    def load(p: pathlib.Path) -> str:
        return p.read_bytes().decode("utf-8")

    def save(p: pathlib.Path, text: str) -> None:
        p.write_bytes(text.encode("utf-8"))

    src = {CPP: load(CPP), HDR: load(HDR)}

    if revert:
        text = src[CPP]
        if MARKER not in text:
            print("REFUSED, nothing written: marker absent, nothing to revert")
            return 1
        for name, path, old, new in EDITS:
            if new is None:
                continue
            if path is not CPP or text.count(new) != 1:
                continue
            text = text.replace(new, old)
        save(CPP, text)
        print("REVERTED src/FrameGen.cpp (FrameGen.h members are inert and left in place)")
        return 0

    print("\n-- preflight --")
    ok = True
    ok &= check(src[HDR], to_eol(H_OLD, eol_hdr), 1, "H anchor")
    ok &= check(src[CPP], to_eol(C_OLD, eol_cpp), 1, "const anchor")
    ok &= check(src[CPP], to_eol(LOCK_ANCHOR, eol_cpp), 1, "lock anchor")
    ok &= check(src[CPP], to_eol(DUMP_OLD, eol_cpp), 1, "dump anchor")
    ok &= check(src[CPP], to_eol(CENSUS_START, eol_cpp), 1, "census start anchor")
    ok &= check(src[CPP], to_eol(CENSUS_END, eol_cpp), 1, "census end anchor")
    ok &= check(src[CPP], MARKER, 0, "marker must be absent")
    for name, path, old, new in EDITS:
        if new is not None and path is CPP and new.count(MARKER) > 0:
            print(f"  note: {name} carries the marker")
    if not ok:
        print("REFUSED, nothing written: a non-unique or missing anchor")
        return 1

    # ---- build the new texts ----
    out = {}
    out[HDR] = src[HDR].replace(to_eol(H_OLD, eol_hdr), to_eol(H_NEW, eol_hdr))
    t = src[CPP]
    t = t.replace(to_eol(C_OLD, eol_cpp), to_eol(C_NEW, eol_cpp))
    t = t.replace(to_eol(LOCK_ANCHOR, eol_cpp), to_eol(LOCK_NEW, eol_cpp))
    t = t.replace(to_eol(DUMP_OLD, eol_cpp), to_eol(DUMP_NEW, eol_cpp))

    # splices last, on the already-modified text
    i0 = t.find(to_eol(CENSUS_START, eol_cpp))
    i1 = t.find(to_eol(CENSUS_END, eol_cpp))
    if i0 < 0 or i1 < 0 or i1 <= i0:
        print(f"REFUSED, nothing written: splice bounds i0={i0} i1={i1}")
        return 1
    t = t[:i0] + to_eol(CENSUS_NEW, eol_cpp) + t[i1:]
    out[CPP] = t

    # ---- post-conditions on the RESULT text ----
    print("\n-- post-conditions --")
    rcpp, rhdr = out[CPP], out[HDR]
    bad = []
    def pc(label, got, want, op="=="):
        nonlocal bad
        good = (got == want) if op == "==" else (got >= want)
        if not good:
            bad.append(f"{label}: got {got}, want {op}{want}")
        print(f"  {'OK ' if good else '** '}{label}: {got} (want {op}{want})")

    pc("cpp marker", rcpp.count(MARKER), 1)
    pc("cpp kPcMatchTol decl", rcpp.count("constexpr float kPcMatchTol = 20.0f;"), 1)
    pc("cpp kSnapFamKeyTol decl", rcpp.count("constexpr float kSnapFamKeyTol = 1.0e-4f;"), 1)
    pc("cpp PC TAKEOVER log", rcpp.count("PC TAKEOVER (v1.16)"), 1)
    pc("cpp [CAM] PC line", rcpp.count('"[CAM] PC v1.16: read={}'), 1)
    pc("cpp snapPcAdopt use", rcpp.count("snapPcAdopt"), 4, ">=")
    pc("cpp census legend", rcpp.count("a bucket that has merged two writers"), 1)
    pc("cpp v1.15 census gone", rcpp.count("v1.15 probe: MOTION PER FAMILY"), 0)
    pc("cpp v1.15 dump gone", rcpp.count("v1.15: the per-family census"), 0)
    pc("cpp MOTION fam log gone", rcpp.count('"[CAM] MOTION fam={:.6g}'), 0)
    pc("cpp usable line intact", rcpp.count("const bool usable = (px == px)"), 1)
    pc("cpp lock anchor intact", rcpp.count("bool sameFamily = true;"), 1)
    pc("cpp frameBufferCopy publish point", rcpp.count("frameBufferCopy = a_src;"), 1)
    pc("hdr snapPcRead", rhdr.count("std::uint64_t snapPcRead = 0;"), 1)
    pc("hdr snapFamArrSec", rhdr.count("std::uint32_t snapFamArrSec[kSnapFamMax] = {};"), 1)
    pc("hdr snapFamMinP", rhdr.count("float snapFamMinP[kSnapFamMax][3] = {};"), 1)

    if bad:
        print("\nFAIL post-conditions:\n  " + "\n  ".join(bad))
        return 2

    if not apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply.")
        return 0

    save(HDR, out[HDR])
    save(CPP, out[CPP])
    for p in (CPP, HDR):
        raw = p.read_bytes()
        crlf = raw.count(b"\r\n")
        bare = raw.count(b"\n") - crlf
        print(f"wrote {p.name}: {len(raw)} bytes, CRLF={crlf}, bareLF={bare}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
