#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.25 patch -- two defects proven from the 01:56 run, plus two instrument fixes.

Everything below is anchored on exact bytes (line endings included) and refuses
to write unless every anchor occurs EXACTLY once on the unmodified file.

  A. Streamline.cpp -- the reprojection matrix handed to DLSS-G at world entry is
     non-affine (clipToPrevClip[3].w = -195) because the inverse comes from our
     rebuilt camera while `prev` comes from the engine's translation-less copy.
     The file already computes clipW and says w must be 1 -- but the acceptance
     gate only tests magnitude, so the bad matrix is USED and STORED.
     Fix: track the family of `prev`, invert the matching family, and gate on
     affinity (|w-1| <= 0.01).

  B. Streamline.cpp ProbeMfgLadder() -- arming bypasses the menu guard, so 4x is
     pushed to the runtime on the loading screen (Transfusion's log: the only
     DLSS-G option call in the whole process, at serial=2, fade=1). v1.24 added
     the fader to the guard to prevent exactly that and could not, because the
     arming does not go through the guarded path.
     Fix: do not touch the runtime while the guard is up.

  C. DX12SwapChain.cpp -- the pixel-probe message printed "the camera was still
     on {N} of them" where N counts samples the camera MOVED on. It says the
     opposite of its own number.

  D. ImguiMenu.cpp -- the FPS overlay multiplies the measured real rate by the
     runtime's REPORTED presented count and prints the product as if measured.
     Show both factors.

Usage:  python tools/patch_v125_affinity_and_ladder_guard.py [--apply]
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPLY = "--apply" in sys.argv

CRLF = "\r\n"

# --------------------------------------------------------------------------
# A/B -- Streamline.cpp  (CRLF)
# --------------------------------------------------------------------------
SL_EDITS = []

SL_EDITS.append((
    "SL-A1 declare the prev family",
    "".join([
        "\t\tstatic sl::float4x4 s_prevVP{};" + CRLF,
        "\t\tstatic bool s_hasPrevVP = false;" + CRLF,
        "\t\tsl::float4x4 prevForReproj{};" + CRLF,
        "\t\tbool havePrev = false;" + CRLF,
    ]),
    "".join([
        "\t\tstatic sl::float4x4 s_prevVP{};" + CRLF,
        "\t\tstatic bool s_hasPrevVP = false;" + CRLF,
        "\t\t// v1.25: which FAMILY s_prevVP belongs to. camCurVP is the camera rebuilt" + CRLF,
        "\t\t// from R + eye (translation included); curForReproj is the engine's own" + CRLF,
        "\t\t// ViewProj, which carries NO translation. Inverting one and multiplying by" + CRLF,
        "\t\t// the other cannot cancel -- see the v1.07c derivation at the invert site." + CRLF,
        "\t\tstatic bool s_prevVPIsRebuilt = false;" + CRLF,
        "\t\tsl::float4x4 prevForReproj{};" + CRLF,
        "\t\tbool havePrev = false;" + CRLF,
        "\t\tbool prevIsRebuilt = false;   // v1.25: family of prevForReproj" + CRLF,
    ]),
))

SL_EDITS.append((
    "SL-A2 history carries its family",
    "".join([
        "\t\t\tif (s_hasPrevVP) {" + CRLF,
        "\t\t\t\tprevForReproj = s_prevVP;" + CRLF,
        "\t\t\t\thavePrev = true;" + CRLF,
        "\t\t\t}" + CRLF,
        "\t\t\ts_prevVP = advance;" + CRLF,
        "\t\t\ts_hasPrevVP = true;" + CRLF,
    ]),
    "".join([
        "\t\t\tif (s_hasPrevVP) {" + CRLF,
        "\t\t\t\tprevForReproj = s_prevVP;" + CRLF,
        "\t\t\t\thavePrev = true;" + CRLF,
        "\t\t\t\tprevIsRebuilt = s_prevVPIsRebuilt;" + CRLF,
        "\t\t\t}" + CRLF,
        "\t\t\ts_prevVP = advance;" + CRLF,
        "\t\t\ts_prevVPIsRebuilt = camCurOk;" + CRLF,
        "\t\t\ts_hasPrevVP = true;" + CRLF,
    ]),
))

SL_EDITS.append((
    "SL-A3 camPrevVP is the rebuilt family",
    "".join([
        "\t\tif (camPrevOk) {" + CRLF,
        "\t\t\tprevForReproj = camPrevVP;" + CRLF,
        "\t\t\thavePrev = true;" + CRLF,
        "\t\t\t++diag.camPrevUsed;" + CRLF,
        "\t\t}" + CRLF,
    ]),
    "".join([
        "\t\tif (camPrevOk) {" + CRLF,
        "\t\t\tprevForReproj = camPrevVP;" + CRLF,
        "\t\t\thavePrev = true;" + CRLF,
        "\t\t\tprevIsRebuilt = true;   // v1.25: rebuilt from R + eye" + CRLF,
        "\t\t\t++diag.camPrevUsed;" + CRLF,
        "\t\t}" + CRLF,
    ]),
))

SL_EDITS.append((
    "SL-A4 the engine seed is the OTHER family",
    "".join([
        "\t\tif (!havePrev && curOk && finiteMag(engPrevViewProjSL) > 1.0e-6f) {" + CRLF,
        "\t\t\tprevForReproj = engPrevViewProjSL;" + CRLF,
        "\t\t\thavePrev = true;" + CRLF,
        "\t\t\t++diag.prevSeededFromEngine;" + CRLF,
        "\t\t}" + CRLF,
    ]),
    "".join([
        "\t\tif (!havePrev && curOk && finiteMag(engPrevViewProjSL) > 1.0e-6f) {" + CRLF,
        "\t\t\tprevForReproj = engPrevViewProjSL;" + CRLF,
        "\t\t\thavePrev = true;" + CRLF,
        "\t\t\tprevIsRebuilt = false;   // v1.25: engine copy, no translation" + CRLF,
        "\t\t\t++diag.prevSeededFromEngine;" + CRLF,
        "\t\t}" + CRLF,
    ]),
))

SL_EDITS.append((
    "SL-A5 invert the same family as prev",
    "\t\t\tconst sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;" + CRLF,
    "".join([
        "\t\t\t// v1.25: the inverse MUST be the same FAMILY as `prev`." + CRLF,
        "\t\t\t//" + CRLF,
        "\t\t\t// The 01:56 run reached the mismatch here and nowhere else. At world entry" + CRLF,
        "\t\t\t// s_hasPrevVP was still false (curOk had been false for the whole loading" + CRLF,
        "\t\t\t// screen), so prevForReproj came from the engine seed while camCurOk was" + CRLF,
        "\t\t\t// already true: inv(rebuilt-with-translation) x engine-without-translation." + CRLF,
        "\t\t\t// Both sides of the log agree on what that produced -- ours:" + CRLF,
        "\t\t\t//   clipW=-195.222366 clipDev=243.962387 p00(c/p)=1.1918/0.0000" + CRLF,
        "\t\t\t// and Transfusion's own [MOTION] row dump, written by a different module:" + CRLF,
        "\t\t\t//   clipToPrev rows=[...][-243.962387 2.7390945 -77.6724777 -195.222366]" + CRLF,
        "\t\t\t// Because both `prev` candidates are built the same way, matching the" + CRLF,
        "\t\t\t// families also fixes it: the engine prev equals the engine cur on that" + CRLF,
        "\t\t\t// frame (engPrevEqCur=1/1), so the one frame that used to be absurd now" + CRLF,
        "\t\t\t// reads as 'the camera did not move', which is what it was." + CRLF,
        "\t\t\tconst sl::float4x4& reprojInvSrc =" + CRLF,
        "\t\t\t\t(prevIsRebuilt && camCurOk) ? camCurVP : curForReproj;" + CRLF,
    ]),
))

SL_EDITS.append((
    "SL-A6 gate on affinity, not only on magnitude",
    "\t\t\tconst bool clipFinite = clipMagAll < 1.0e30f && clipMagAll > 1.0e-6f;" + CRLF,
    "".join([
        "\t\t\t// v1.25: AFFINITY GATE. The block above already computes clipW and states" + CRLF,
        "\t\t\t// in plain words that w must be 1 -- but nothing gated on it, so a matrix" + CRLF,
        "\t\t\t// with w = -195 was ACCEPTED, written into s_lastGoodClip, and handed to" + CRLF,
        "\t\t\t// DLSS-G. Transfusion's [MOTION] dump is the proof it reached the runtime." + CRLF,
        "\t\t\t//" + CRLF,
        "\t\t\t// A clip-space -> clip-space reprojection is affine, so its last row is" + CRLF,
        "\t\t\t// (tx,ty,tz,1). Unlike clipDev this test does not grow with camera speed" + CRLF,
        "\t\t\t// or frame time, so it cannot reject legitimate motion -- identity scores" + CRLF,
        "\t\t\t// 0 and any real displacement keeps w at exactly 1." + CRLF,
        "\t\t\t// (wAffDev, not wDev: the v1.08 probe block below already owns wDev in a" + CRLF,
        "\t\t\t//  nested scope.)" + CRLF,
        "\t\t\tconst float wAffDev = c.clipToPrevClip[3].w - 1.0f;" + CRLF,
        "\t\t\tconst float wAbs = wAffDev < 0.0f ? -wAffDev : wAffDev;" + CRLF,
        "\t\t\tconst bool clipAffine = wAbs <= 0.01f;" + CRLF,
        "\t\t\tconst bool clipFinite = clipMagAll < 1.0e30f && clipMagAll > 1.0e-6f && clipAffine;" + CRLF,
    ]),
))

SL_EDITS.append((
    "SL-B do not arm MFG while the guard is up",
    "".join([
        "\t\tmfgInSetOptions = true;" + CRLF,
        "\t\tg_inSetOptions.store(1);" + CRLF,
        "\t\tSetDLSSGOptions(cw, ch, cw, ch, dx.swapChainDesc.Format);" + CRLF,
        "\t\tg_inSetOptions.store(0);" + CRLF,
        "\t\tmfgInSetOptions = false;" + CRLF,
        "\t}" + CRLF,
    ]),
    "".join([
        "\t\t// v1.25: do NOT talk to the runtime while the loading/fade guard is up." + CRLF,
        "\t\t//" + CRLF,
        "\t\t// v0.79 lifted this probe out of SetDLSSGOptions so a rejected rung could" + CRLF,
        "\t\t// still step down while a menu was open. The side effect was never stated:" + CRLF,
        "\t\t// this became the ONLY path that arms frame generation while the guard" + CRLF,
        "\t\t// blocks Present. Evidence, from the 01:56 run, and taken from Transfusion's" + CRLF,
        "\t\t// log rather than ours -- a different module, so this is not our echo:" + CRLF,
        "\t\t//   [01:55:59.490] [OPTIONS] Game DLSS-G options: structVersion=5" + CRLF,
        "\t\t//                  mode=eOn frames=3 uir=0 color=3840x2160 flags=0x00000010" + CRLF,
        "\t\t//   [01:55:59.490] Applied fixed multiplier: 4x, result=0 (eOk)" + CRLF,
        "\t\t// That is the ONLY DLSS-G option call in the entire process, it lands on" + CRLF,
        "\t\t// serial=2 with consts ok=0 / hrs=0 / fade=1 -- the loading screen -- and the" + CRLF,
        "\t\t// multiplier then stays at 4x for the 17.5 s that remain before the world is" + CRLF,
        "\t\t// entered. v1.24 added the fader to the guard to stop exactly this and did" + CRLF,
        "\t\t// not, because the arming never goes through the guarded path." + CRLF,
        "\t\t//" + CRLF,
        "\t\t// Skipping the call entirely -- rather than sending a smaller step -- leaves" + CRLF,
        "\t\t// the runtime exactly as the last unguarded frame left it, and cannot pin a" + CRLF,
        "\t\t// rejected rung: the ladder resumes, and can still step down, on the first" + CRLF,
        "\t\t// unguarded frame." + CRLF,
        "\t\t{" + CRLF,
        "\t\t\tstatic bool s_ladderHeldBack = false;" + CRLF,
        "\t\t\tif (GameMenuOpenNow()) {" + CRLF,
        "\t\t\t\tif (!s_ladderHeldBack) {" + CRLF,
        "\t\t\t\t\ts_ladderHeldBack = true;" + CRLF,
        "\t\t\t\t\tSKSE::log::info(\"[MFG] ladder held back: the loading/fade guard is up, so the \" " + CRLF,
        "\t\t\t\t\t\t\"runtime is left untouched for this frame (step would have been {}x). \" " + CRLF,
        "\t\t\t\t\t\t\"Present skips DLSS-G here anyway; arming it only leaves the \" " + CRLF,
        "\t\t\t\t\t\t\"multiplier set across the whole load.\", mfgProbeStep + 1);" + CRLF,
        "\t\t\t\t}" + CRLF,
        "\t\t\t\treturn;" + CRLF,
        "\t\t\t}" + CRLF,
        "\t\t\tif (s_ladderHeldBack) {" + CRLF,
        "\t\t\t\ts_ladderHeldBack = false;" + CRLF,
        "\t\t\t\tSKSE::log::info(\"[MFG] ladder resumed on the first unguarded frame: step {}x\"," + CRLF,
        "\t\t\t\t\tmfgProbeStep + 1);" + CRLF,
        "\t\t\t}" + CRLF,
        "\t\t}" + CRLF,
        "\t\tmfgInSetOptions = true;" + CRLF,
        "\t\tg_inSetOptions.store(1);" + CRLF,
        "\t\tSetDLSSGOptions(cw, ch, cw, ch, dx.swapChainDesc.Format);" + CRLF,
        "\t\tg_inSetOptions.store(0);" + CRLF,
        "\t\tmfgInSetOptions = false;" + CRLF,
        "\t}" + CRLF,
    ]),
))

# --------------------------------------------------------------------------
# C -- DX12SwapChain.cpp  (pure LF)
# --------------------------------------------------------------------------
DX_EDITS = [(
    "DX-C pixel message counted the wrong thing",
    "".join([
        "\t\t\t\t\t} else {\n",
        "\t\t\t\t\t\tSKSE::log::warn(\"[PIXEL] 3 identical seconds, but the camera was still on {} of \"\n",
        "\t\t\t\t\t\t\t\"them - a static camera makes interpolated frames legitimately identical, so \"\n",
        "\t\t\t\t\t\t\t\"this is NOT a frozen-screen verdict. Move for 3 s to make the next streak \"\n",
        "\t\t\t\t\t\t\t\"mean something.\", pixelProbeMovedDuringStreak);\n",
        "\t\t\t\t\t}\n",
    ]),
    "".join([
        "\t\t\t\t\t} else {\n",
        "\t\t\t\t\t\t// v1.25: this counter counts the samples on which the camera MOVED, but\n",
        "\t\t\t\t\t\t// the old text read \"the camera was still on {} of them\" and printed\n",
        "\t\t\t\t\t\t// that same number -- so the sentence said the opposite of its own\n",
        "\t\t\t\t\t\t// value, and a 0 (camera never moved) read as \"it moved every time\".\n",
        "\t\t\t\t\t\tSKSE::log::warn(\"[PIXEL] {} identical samples in a row, and the camera moved on \"\n",
        "\t\t\t\t\t\t\t\"only {} of them - a static camera makes interpolated frames \"\n",
        "\t\t\t\t\t\t\t\"legitimately identical, so this is NOT a frozen-screen verdict. \"\n",
        "\t\t\t\t\t\t\t\"Hold W for 3 s to make the next streak mean something.\",\n",
        "\t\t\t\t\t\t\tpixelProbeStreak, pixelProbeMovedDuringStreak);\n",
        "\t\t\t\t\t}\n",
    ]),
)]

# --------------------------------------------------------------------------
# D -- ImguiMenu.cpp  (CRLF)
# --------------------------------------------------------------------------
IM_EDITS = [(
    "IM-D overlay must not print an inference as a measurement",
    "".join([
        "\t\tchar buf[32];" + CRLF,
        "\t\tstd::snprintf(buf, sizeof(buf), \"%.0f FPS%s\", s_fps * mult, tag);" + CRLF,
    ]),
    "".join([
        "\t\t// v1.25: keep the two factors visible. `mult` is the runtime's REPORT of how" + CRLF,
        "\t\t// many frames it presented for the last real frame (slDLSSGGetState) and" + CRLF,
        "\t\t// s_fps is the real present rate measured right here, so the product is an" + CRLF,
        "\t\t// inference, not a measurement. On the 01:56 run the read-out jumped from" + CRLF,
        "\t\t// ~50 to ~150 at world entry while an independent reader in the same process" + CRLF,
        "\t\t// (Transfusion's [PERF], 300-frame window) measured 49.3 FPS. Printing the" + CRLF,
        "\t\t// product alone is what makes \"4x\" look like an observation." + CRLF,
        "\t\tchar buf[64];" + CRLF,
        "\t\tif (mult > 1.0f)" + CRLF,
        "\t\t\tstd::snprintf(buf, sizeof(buf), \"%.0f FPS  [%.0f real x%.0f reported]\"," + CRLF,
        "\t\t\t\ts_fps * mult, s_fps, mult);" + CRLF,
        "\t\telse" + CRLF,
        "\t\t\tstd::snprintf(buf, sizeof(buf), \"%.0f FPS%s\", s_fps * mult, tag);" + CRLF,
    ]),
)]

FILES = [
    ("src/Streamline.cpp", SL_EDITS),
    ("src/DX12SwapChain.cpp", DX_EDITS),
    ("src/ImguiMenu.cpp", IM_EDITS),
]


def main():
    failed = False
    plan = []
    orig_sizes = {}
    for rel, edits in FILES:
        p = ROOT / rel
        raw = p.read_bytes()
        orig_sizes[rel] = len(raw)
        text = raw.decode("utf-8")
        for label, old, new in edits:
            # Insertion-type edits embed their own anchor in the replacement, so
            # "count == 1" alone is not enough to make them idempotent: the anchor
            # survives the first run and a second run would insert the block twice.
            # Refuse on that directly.
            if new in text:
                print(f"REFUSED [{rel}] {label}: replacement already present (already applied)")
                failed = True
                continue
            n = text.count(old)
            if n != 1:
                print(f"REFUSED [{rel}] {label}: anchor count == {n} (must be 1)")
                failed = True
                continue
            text = text.replace(old, new, 1)
            plan.append((rel, label, old, new))

    if failed:
        print("\nREFUSED, nothing written")
        return 1

    print(f"all {len(plan)} anchors matched exactly once")
    if not APPLY:
        for rel, label, *_ in plan:
            print(f"  would edit {rel}: {label}")
        print("\nDRY RUN - pass --apply to write")
        return 0

    for rel, edits in FILES:
        p = ROOT / rel
        text = p.read_bytes().decode("utf-8")
        for label, old, new in edits:
            text = text.replace(old, new, 1)
        p.write_bytes(text.encode("utf-8"))
        print(f"wrote {rel}: {len(text.encode('utf-8'))} bytes")

    new_sizes = {rel: (ROOT / rel).stat().st_size for rel in orig_sizes}

    # Post-conditions. A negative test ("the old anchor is gone") is NOT usable
    # here: SL-B's new block deliberately embeds the old block, so that anchor
    # must still be found. Assert on positive witnesses instead -- strings that
    # only the patched code contains -- plus "the file actually changed".
    MARKERS = {
        "src/Streamline.cpp": [
            "static bool s_prevVPIsRebuilt = false;",
            "prevIsRebuilt = s_prevVPIsRebuilt;",
            "prevIsRebuilt = true;   // v1.25: rebuilt from R + eye",
            "prevIsRebuilt = false;   // v1.25: engine copy, no translation",
            "(prevIsRebuilt && camCurOk) ? camCurVP : curForReproj;",
            "const bool clipAffine = wAbs <= 0.01f;",
            "\"[MFG] ladder held back: the loading/fade guard is up, so the \"",
            "\"[MFG] ladder resumed on the first unguarded frame: step {}x\"",
        ],
        "src/DX12SwapChain.cpp": [
            "\"[PIXEL] {} identical samples in a row, and the camera moved on \"",
        ],
        "src/ImguiMenu.cpp": [
            "\"%.0f FPS  [%.0f real x%.0f reported]\"",
        ],
    }
    for rel, markers in MARKERS.items():
        raw = (ROOT / rel).read_bytes().decode("utf-8")
        for m in markers:
            if m not in raw:
                print(f"POST-CHECK FAILED: marker missing in {rel}: {m}")
                return 3
    if orig_sizes == new_sizes:
        print("POST-CHECK FAILED: no file changed size")
        return 3
    print("post-check OK: every marker present, every file grew")
    return 0


if __name__ == "__main__":
    sys.exit(main())
