#!/usr/bin/env python3
"""v1.15 probe: measure MOTION per projection family.

Why this patch exists
---------------------
The v1.14 census counted DISTINCT positions against an 8-entry table that never
evicted.  Once those eight slots had filled with the first arrivals, every later
arrival differing from them by more than 1 unit incremented snapCensusNew -- so a
PARKED writer and a MOVING one produced the same rising number.

The 21:15 run read cen=5077/8 while every refused arrival in the world sat at the
same position (-243.0,-415.3,118.6), with only 1 decimal printed.  The counter was
measuring "differs from the first eight seen", not "moves".  So that run cannot
decide between the two repairs, and the probe has to be replaced rather than
re-read.

This patch measures the step between CONSECUTIVE arrivals, bucketed by proj00, and
reports it once a second.  That separates the two live hypotheses directly:

  some family accumulates moves -> the live camera IS reaching this hook, and the
    repair belongs in the accept rules (family lock / v1.11 takeover);
  no family accumulates moves  -> nothing that reaches this hook is a live camera,
    and the SOURCE has to change (RE::PlayerCamera).

Purely additive diagnostics: no accept/reject decision changes.  The family
rejected line gains precision (pos 1 -> 4 decimals, plus prevPos and row3) which is
the cheapest way to see whether a refused family is parked or moving.

Usage
-----
  python tools/patch_v115_fammotionprobe.py            # dry run
  python tools/patch_v115_fammotionprobe.py --apply    # write
  python tools/patch_v115_fammotionprobe.py --revert   # undo (cpp only)
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPP = ROOT / "src" / "FrameGen.cpp"
HDR = ROOT / "src" / "FrameGen.h"

MARKER = "v1.15 probe: MOTION PER FAMILY"


def file_eol(path: pathlib.Path) -> bytes:
    """Line ending decided from the FILE, never from the anchor."""
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    return b"\r\n" if crlf >= bare else b"\n"


OLD_CONST = (
    "\tconstexpr std::uint64_t kCamCaptureFallbackSkips = 6000;"
)

NEW_CONST = OLD_CONST + (
    "\n"
    "\n"
    "\t// ---- v1.15: the smallest pos delta that counts as a real camera step ----\n"
    "\t// The hook sees the same writer several times per frame, so a live camera\n"
    "\t// produces multi-unit steps between consecutive arrivals while a parked one\n"
    "\t// only produces float noise far below this. 0.05 units = 5 cm.\n"
    "\tconstexpr float kCamMoveEps = 0.05f;"
)

OLD_CENSUS_HEAD = (
    "\t\t// ---- v1.14 probe: a census of the WRITERS -- who writes this buffer, and"
)

OLD_CENSUS = (
    "\t\t// ---- v1.14 probe: a census of the WRITERS -- who writes this buffer, and\n"
    "\t\t// does any of them MOVE?  Purely additive and placed BEFORE the gate, so it\n"
    "\t\t// sees the whole cast.\n"
    "\t\t// The 19:39 run proved the v1.13 gate works (the orthographic writer is\n"
    "\t\t// dropped 13,804 times, cap=13804/0) but the published camera stayed\n"
    "\t\t// byte-identical for the whole 11.4 s world session.  \"The player was\n"
    "\t\t// standing still\" and \"we are locked on a parked camera\" call for two very\n"
    "\t\t// different repairs, and only a census of the actual writers separates\n"
    "\t\t// them: if snapCensusNew stays at 2-3 for a whole session, NO writer moves\n"
    "\t\t// and the source itself has to change.\n"
    "\t\t{\n"
    "\t\t\tbool known = false;\n"
    "\t\t\tfor (std::uint32_t i = 0; i < snapCensusCount && !known; ++i) {\n"
    "\t\t\t\tknown = (std::fabs(snapCensus[i][0] - px) +\n"
    "\t\t\t\t         std::fabs(snapCensus[i][1] - py) +\n"
    "\t\t\t\t         std::fabs(snapCensus[i][2] - pz)) < 1.0f;\n"
    "\t\t\t}\n"
    "\t\t\tif (!known) {\n"
    "\t\t\t\tif (snapCensusCount < kSnapCensusMax) {\n"
    "\t\t\t\t\tsnapCensus[snapCensusCount][0] = px;\n"
    "\t\t\t\t\tsnapCensus[snapCensusCount][1] = py;\n"
    "\t\t\t\t\tsnapCensus[snapCensusCount][2] = pz;\n"
    "\t\t\t\t\t++snapCensusCount;\n"
    "\t\t\t\t}\n"
    "\t\t\t\t++snapCensusNew;\n"
    "\t\t\t\tif (snapCensusLogged < 80u) {\n"
    "\t\t\t\t\t++snapCensusLogged;\n"
    "\t\t\t\t\tSKSE::log::info(\"[CAM] WRITER #{} NEW pos=({:.3f},{:.3f},{:.3f}) proj00={:.6g} \"\n"
    "\t\t\t\t\t\t\"row3_2={:.6g} row3_3={:.6g} prevPos=({:.3f},{:.3f},{:.3f}) arr#{}\",\n"
    "\t\t\t\t\t\tsnapCensusNew, px, py, pz,\n"
    "\t\t\t\t\t\ta_src.CameraProj.data[0][0],\n"
    "\t\t\t\t\t\ta_src.CameraProj.data[3][2], a_src.CameraProj.data[3][3],\n"
    "\t\t\t\t\t\ta_src.CameraPreviousPosAdjust[0], a_src.CameraPreviousPosAdjust[1],\n"
    "\t\t\t\t\t\ta_src.CameraPreviousPosAdjust[2], snapArrivals);\n"
    "\t\t\t\t}\n"
    "\t\t\t}\n"
    "\t\t}"
)

NEW_CENSUS = (
    "\t\t// ---- v1.15 probe: MOTION PER FAMILY ----------------------------------\n"
    "\t\t// v1.14 counted DISTINCT positions against an 8-entry table that never\n"
    "\t\t// evicted.  Once those eight slots filled with the first arrivals, every\n"
    "\t\t// later arrival differing from them by >1 unit incremented the counter --\n"
    "\t\t// so a PARKED writer and a MOVING one produced the same rising number.\n"
    "\t\t// The 21:15 run duly read cen=5077/8 while every refused arrival in the\n"
    "\t\t// world sat at the same position: the counter was measuring \"differs from\n"
    "\t\t// the first eight seen\", not \"moves\".\n"
    "\t\t//\n"
    "\t\t// Measure the step between CONSECUTIVE arrivals instead, bucketed by\n"
    "\t\t// proj00, because the question that decides the repair is not \"do arrivals\n"
    "\t\t// move\" but \"does a MOVING family reach this hook\":\n"
    "\t\t//   some family accumulates moves -> the live camera is arriving, and the\n"
    "\t\t//     repair belongs in the accept rules (family lock / v1.11 takeover);\n"
    "\t\t//   no family accumulates moves  -> no live camera reaches this hook, and\n"
    "\t\t//     the SOURCE has to change (RE::PlayerCamera).\n"
    "\t\t{\n"
    "\t\t\tconst float famKey = a_src.CameraProjUnjittered.data[0][0];\n"
    "\t\t\tstd::int32_t slot = -1;\n"
    "\t\t\tfor (std::uint32_t i = 0; i < kSnapFamMax; ++i) {\n"
    "\t\t\t\tif (snapFamSeen[i] &&\n"
    "\t\t\t\t    std::fabs(snapFamProj[i] - famKey) <= std::fabs(famKey) * 0.02f + 1.0e-6f) {\n"
    "\t\t\t\t\tslot = static_cast<std::int32_t>(i);\n"
    "\t\t\t\t\tbreak;\n"
    "\t\t\t\t}\n"
    "\t\t\t}\n"
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
    "\t\t\t}\n"
    "\t\t\tif (slot >= 0) {\n"
    "\t\t\t\tconst auto s = static_cast<std::uint32_t>(slot);\n"
    "\t\t\t\tif (snapFamHavePos[s]) {\n"
    "\t\t\t\t\tconst float mdX = px - snapFamPos[s][0];\n"
    "\t\t\t\t\tconst float mdY = py - snapFamPos[s][1];\n"
    "\t\t\t\t\tconst float mdZ = pz - snapFamPos[s][2];\n"
    "\t\t\t\t\tconst float mstep = std::sqrt(mdX * mdX + mdY * mdY + mdZ * mdZ);\n"
    "\t\t\t\t\tsnapFamStep[s] += mstep;\n"
    "\t\t\t\t\tsnapFamStepTotal += mstep;\n"
    "\t\t\t\t\tif (mstep > kCamMoveEps) {\n"
    "\t\t\t\t\t\t++snapFamMoved[s];\n"
    "\t\t\t\t\t\t++snapFamMovedTotal;\n"
    "\t\t\t\t\t\tif (snapFamLogged < 60u) {\n"
    "\t\t\t\t\t\t\t++snapFamLogged;\n"
    "\t\t\t\t\t\t\tSKSE::log::info(\"[CAM] MOTION fam={:.6g} #{} step={:.4f} \"\n"
    "\t\t\t\t\t\t\t\t\"pos=({:.4f},{:.4f},{:.4f}) prevPos=({:.4f},{:.4f},{:.4f}) \"\n"
    "\t\t\t\t\t\t\t\t\"Proj row3=({:.6g},{:.6g},{:.6g},{:.6g}) arr#{}\",\n"
    "\t\t\t\t\t\t\t\tfamKey, snapFamMoved[s], mstep, px, py, pz,\n"
    "\t\t\t\t\t\t\t\tsnapFamPos[s][0], snapFamPos[s][1], snapFamPos[s][2],\n"
    "\t\t\t\t\t\t\t\ta_src.CameraProjUnjittered.data[3][0],\n"
    "\t\t\t\t\t\t\t\ta_src.CameraProjUnjittered.data[3][1],\n"
    "\t\t\t\t\t\t\t\ta_src.CameraProjUnjittered.data[3][2],\n"
    "\t\t\t\t\t\t\t\ta_src.CameraProjUnjittered.data[3][3], snapArrivals);\n"
    "\t\t\t\t\t\t}\n"
    "\t\t\t\t\t}\n"
    "\t\t\t\t}\n"
    "\t\t\t\tsnapFamPos[s][0] = px;\n"
    "\t\t\t\tsnapFamPos[s][1] = py;\n"
    "\t\t\t\tsnapFamPos[s][2] = pz;\n"
    "\t\t\t\tsnapFamHavePos[s] = true;\n"
    "\t\t\t}\n"
    "\t\t}"
)

OLD_FAMREJ = (
    "\t\t\t\t\t\tSKSE::log::info(\"[CAM] #{} family rejected: proj00={:.6g} locked={:.6g} \"\n"
    "\t\t\t\t\t\t\t\"ratio={:.4f} pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} still={}/{}\",\n"
    "\t\t\t\t\t\t\tsnapArrivals, proj00, snapLockProj00,\n"
    "\t\t\t\t\t\t\tsnapLockProjValid ? (proj00 / snapLockProj00) : 0.0f,\n"
    "\t\t\t\t\t\t\tpx, py, pz, std::sqrt(d2), snapLockStill, kCamStillTol);"
)

NEW_FAMREJ = (
    "\t\t\t\t\t\t// v1.15: pos at 4 decimals plus prevPos and row3. \"Parked\" and\n"
    "\t\t\t\t\t\t// \"gliding\" are indistinguishable at 1 decimal, and that distinction\n"
    "\t\t\t\t\t\t// is what decides whether this refused family could ever satisfy\n"
    "\t\t\t\t\t\t// kCamForeignMoveTol on the v1.11 takeover.\n"
    "\t\t\t\t\t\tSKSE::log::info(\"[CAM] #{} family rejected: proj00={:.6g} locked={:.6g} \"\n"
    "\t\t\t\t\t\t\t\"ratio={:.4f} pos=({:.4f},{:.4f},{:.4f}) \"\n"
    "\t\t\t\t\t\t\t\"prevPos=({:.4f},{:.4f},{:.4f}) dist={:.1f} still={}/{} \"\n"
    "\t\t\t\t\t\t\t\"row3=({:.6g},{:.6g},{:.6g},{:.6g})\",\n"
    "\t\t\t\t\t\t\tsnapArrivals, proj00, snapLockProj00,\n"
    "\t\t\t\t\t\t\tsnapLockProjValid ? (proj00 / snapLockProj00) : 0.0f,\n"
    "\t\t\t\t\t\t\tpx, py, pz,\n"
    "\t\t\t\t\t\t\ta_src.CameraPreviousPosAdjust[0],\n"
    "\t\t\t\t\t\t\ta_src.CameraPreviousPosAdjust[1],\n"
    "\t\t\t\t\t\t\ta_src.CameraPreviousPosAdjust[2],\n"
    "\t\t\t\t\t\t\tstd::sqrt(d2), snapLockStill, kCamStillTol,\n"
    "\t\t\t\t\t\t\ta_src.CameraProjUnjittered.data[3][0],\n"
    "\t\t\t\t\t\t\ta_src.CameraProjUnjittered.data[3][1],\n"
    "\t\t\t\t\t\t\ta_src.CameraProjUnjittered.data[3][2],\n"
    "\t\t\t\t\t\t\ta_src.CameraProjUnjittered.data[3][3]);"
)

OLD_PUB_TAIL = (
    "\t\t\t\t\t\t\"fMove={:.1f} takeover={} stalePub={} cap={}/{} cen={}/{} | {}\",\n"
    "\t\t\t\t\t\tsnapAccept, px, py, pz, snapAcceptDist, snapPathLen, snapMatChanges,\n"
    "\t\t\t\t\t\tarrPerSec, snapLockPublish, snapLockHold, snapLockRelock, snapLockStill,\n"
    "\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f, snapLockFamilyRej,\n"
    "\t\t\t\t\t\tsnapFrozenRepeats, snapIdenticalArrivals, snapDifferentArrivals,\n"
    "\t\t\t\t\t\tsnapForeignMove, snapForeignTakeover,\n"
    "\t\t\t\t\t\tsnapPubStale,\n"
    "\t\t\t\t\t\tsnapNonCamera, snapSkipsSinceCam, snapCensusNew, snapCensusCount,\n"
    "\t\t\t\t\t\tsnapMatChanges == 0u\n"
    "\t\t\t\t\t\t\t? \"PROBLEM nothing has ever been published with a changed matrix\"\n"
    "\t\t\t\t\t\t\t: (snapPubStale >= kCamPubStaleTol\n"
    "\t\t\t\t\t\t\t\t   ? \"PROBLEM the published camera has been byte-identical for a long run\"\n"
    "\t\t\t\t\t\t\t\t   : \"ok\"));"
)

NEW_PUB_TAIL = (
    "\t\t\t\t\t\t\"fMove={:.1f} takeover={} stalePub={} cap={}/{} mv={} step={:.1f} | {}\",\n"
    "\t\t\t\t\t\tsnapAccept, px, py, pz, snapAcceptDist, snapPathLen, snapMatChanges,\n"
    "\t\t\t\t\t\tarrPerSec, snapLockPublish, snapLockHold, snapLockRelock, snapLockStill,\n"
    "\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f, snapLockFamilyRej,\n"
    "\t\t\t\t\t\tsnapFrozenRepeats, snapIdenticalArrivals, snapDifferentArrivals,\n"
    "\t\t\t\t\t\tsnapForeignMove, snapForeignTakeover,\n"
    "\t\t\t\t\t\tsnapPubStale,\n"
    "\t\t\t\t\t\tsnapNonCamera, snapSkipsSinceCam,\n"
    "\t\t\t\t\t\tsnapFamMovedTotal, snapFamStepTotal,\n"
    "\t\t\t\t\t\tsnapMatChanges == 0u\n"
    "\t\t\t\t\t\t\t? \"PROBLEM nothing has ever been published with a changed matrix\"\n"
    "\t\t\t\t\t\t\t: (snapPubStale >= kCamPubStaleTol\n"
    "\t\t\t\t\t\t\t\t   ? \"PROBLEM the published camera has been byte-identical for a long run\"\n"
    "\t\t\t\t\t\t\t\t   : \"ok\"));\n"
    "\t\t\t\t\t// v1.15: the per-family census, one line per family per second. This is\n"
    "\t\t\t\t\t// the block that decides the next repair: a family whose `moved` climbs\n"
    "\t\t\t\t\t// is a LIVE camera reaching this hook, so the fix belongs in the accept\n"
    "\t\t\t\t\t// rules; if every family shows moved=0, nothing here is alive and the\n"
    "\t\t\t\t\t// source has to change.\n"
    "\t\t\t\t\tfor (std::uint32_t fi = 0; fi < kSnapFamMax; ++fi) {\n"
    "\t\t\t\t\t\tif (!snapFamSeen[fi])\n"
    "\t\t\t\t\t\t\tcontinue;\n"
    "\t\t\t\t\t\tSKSE::log::info(\"[CAM] FAM[{}] proj00={:.6g} moved={} stepSum={:.2f}\",\n"
    "\t\t\t\t\t\t\tfi, snapFamProj[fi], snapFamMoved[fi], snapFamStep[fi]);\n"
    "\t\t\t\t\t}"
)

OLD_HDR = "\tstd::uint64_t snapCensusLogged = 0;"

NEW_HDR = (
    "\tstd::uint64_t snapCensusLogged = 0;\n"
    "\n"
    "\t// ---- v1.15: motion measured per projection family --------------------\n"
    "\t// v1.14's census counted \"positions differing from the first eight seen\",\n"
    "\t// which a single PARKED writer also increments without bound. These count\n"
    "\t// the step between CONSECUTIVE arrivals, bucketed by proj00, so a live\n"
    "\t// family is separable from a parked one by reading `moved` on [CAM] FAM.\n"
    "\tstatic constexpr std::uint32_t kSnapFamMax = 8;\n"
    "\tbool snapFamSeen[kSnapFamMax] = {};\n"
    "\tfloat snapFamProj[kSnapFamMax] = {};\n"
    "\tfloat snapFamPos[kSnapFamMax][3] = {};\n"
    "\tbool snapFamHavePos[kSnapFamMax] = {};\n"
    "\tstd::uint64_t snapFamMoved[kSnapFamMax] = {};\n"
    "\tfloat snapFamStep[kSnapFamMax] = {};\n"
    "\tstd::uint64_t snapFamMovedTotal = 0;\n"
    "\tfloat snapFamStepTotal = 0.0f;\n"
    "\tstd::uint64_t snapFamLogged = 0;"
)

EDITS = [
    ("cpp: add kCamMoveEps", CPP, OLD_CONST, NEW_CONST, 1),
    ("cpp: replace the v1.14 census with per-family motion", CPP, OLD_CENSUS, NEW_CENSUS, 1),
    ("cpp: family-rejected line gains pos precision + prevPos + row3", CPP, OLD_FAMREJ, NEW_FAMREJ, 1),
    ("cpp: pub line + per-family report", CPP, OLD_PUB_TAIL, NEW_PUB_TAIL, 1),
    ("hdr: per-family motion members", HDR, OLD_HDR, NEW_HDR, 1),
]


def build(text, path, old, new):
    eol = file_eol(path)
    return text.replace(
        old.replace("\n", eol.decode()),
        new.replace("\n", eol.decode()),
    ), eol


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    src = {}
    for path in (CPP, HDR):
        raw = path.read_bytes()
        src[path] = raw.decode("utf-8")

    if revert:
        text = src[CPP]
        if MARKER not in text:
            print("REFUSED, nothing written: marker absent, nothing to revert")
            return 1
        for name, path, old, new in EDITS:
            if path is not CPP:
                continue
            eol = file_eol(path)
            n = text.count(new.replace("\n", eol.decode()))
            if n != 1:
                print(f"REFUSED (revert): anchor for {name} appears {n}x, want 1")
                return 1
            text = text.replace(new.replace("\n", eol.decode()), old.replace("\n", eol.decode()))
        CPP.write_bytes(text.encode("utf-8"))
        print("REVERTED src/FrameGen.cpp (FrameGen.h members are inert and were left)")
        return 0

    print(f"marker present: {MARKER in src[CPP]}")
    if MARKER in src[CPP]:
        print("REFUSED, nothing written: patch already applied (idempotency guard)")
        return 1

    bad = []
    for name, path, old, new, want in EDITS:
        eol = file_eol(path)
        n = src[path].count(old.replace("\n", eol.decode()))
        print(f"  count={n} (want {want})  {name}  [{path.name} eol={'CRLF' if eol == b'\r\n' else 'LF'}]")
        if n != want:
            bad.append(name)
    if bad:
        print(f"REFUSED, nothing written: non-unique/missing anchors: {bad}")
        return 1

    out = dict(src)
    for name, path, old, new, want in EDITS:
        out[path], _ = build(out[path], path, old, new)

    # ---- post-conditions on the RESULT text, not the input ----
    cpp, hdr = out[CPP], out[HDR]
    probes = [
        ("marker in cpp", cpp.count(MARKER), 1),
        ("MOTION log string", cpp.count('"[CAM] MOTION fam={:.6g} #{} step={:.4f} "'), 1),
        ("FAM report string", cpp.count('"[CAM] FAM[{}] proj00={:.6g} moved={} stepSum={:.2f}"'), 1),
        ("kCamMoveEps declaration", cpp.count("constexpr float kCamMoveEps = 0.05f;"), 1),
        ("pub uses mv/step", cpp.count("cap={}/{} mv={} step={:.1f} | {}"), 1),
        ("old cen= format gone", cpp.count("cen={}/{}"), 0),
        ("old v1.14 WRITER string gone", cpp.count("[CAM] WRITER #{} NEW pos="), 0),
        ("famrej has prevPos", cpp.count('"prevPos=({:.4f},{:.4f},{:.4f}) dist={:.1f} still={}/{} "'), 1),
        ("snapFamMovedTotal used", cpp.count("snapFamMovedTotal"), 2),
        ("hdr kSnapFamMax", hdr.count("static constexpr std::uint32_t kSnapFamMax = 8;"), 1),
        ("hdr moved array", hdr.count("std::uint64_t snapFamMoved[kSnapFamMax] = {};"), 1),
        ("hdr legacy census kept", hdr.count("std::uint64_t snapCensusNew = 0;"), 1),
    ]
    dead = [f"{name}: got {got}, want {want}" for name, got, want in probes if got != want]
    if dead:
        print("FAIL post-conditions:\n  " + "\n  ".join(dead))
        return 2

    for path in (CPP, HDR):
        raw = src[path].encode("utf-8")
        outb = out[path].encode("utf-8")
        crlf_a, crlf_b = raw.count(b"\r\n"), outb.count(b"\r\n")
        bare_a = raw.count(b"\n") - crlf_a
        bare_b = outb.count(b"\n") - crlf_b
        style_a = "CRLF" if crlf_a >= bare_a else "LF"
        style_b = "CRLF" if crlf_b >= bare_b else "LF"
        if style_a != style_b or (style_a == "CRLF" and bare_b != 0) or (style_a == "LF" and crlf_b != 0):
            print(f"FAIL eol: {path.name} {style_a}({crlf_a}/{bare_a}) -> {style_b}({crlf_b}/{bare_b})")
            return 2
        print(f"  {path.name}: CRLF {crlf_a}->{crlf_b} bareLF {bare_a}->{bare_b} "
              f"bytes {len(raw)}->{len(outb)}")

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
