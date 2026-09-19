#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.19: the liveness witnesses (game clock, pause state, engine key state).

The user's answer to "what does it look like" is "the picture is completely
frozen, how am I supposed to move" -- for every run, from the moment the world
loads.  So the 2-5 second world segments were never an idle player; they were a
frozen picture and a force-quit.  keys=0x0 and dc=0 are the consequence.

v1.18's witnesses therefore answered a question nobody was asking.  The sharp
question is now different: the present loop is demonstrably alive (watchdog
alive=1 focus=1 presentAge single-digit ms, frames advancing) and the image is
not.  Those four new witnesses live in the GAME, not the renderer:

    hrsD / rawD   the game clock's advance this second -> is the game logic alive
    paused        RE::UI::GameIsPaused()
    ld / fade     Loading Menu / Fader Menu open

Read-only.  Nothing here gates, selects, publishes or blocks.

Dry run by default.  --apply writes.  --revert restores the anchors.
Every anchor must occur exactly once, and the marker makes a second run a no-op.
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPP = ROOT / "src" / "FrameGen.cpp"

MARK = "v1.19: THE LIVENESS WITNESSES"


def load(p):
    # read_text() applies universal-newline translation and would silently turn
    # every CRLF anchor into an LF one (and rewrite the whole file as LF).
    b = p.read_bytes()
    return b.decode("utf-8"), b


def eol_of(p):
    b = p.read_bytes()
    return "\r\n" if b"\r\n" in b else "\n"


def L(*lines):
    return "\n".join(lines)


# ---------------------------------------------------------------- E1: statics
E1_OLD = "\t\t\t\t\tstatic float s_plrStep = 0.0f;"

E1_NEW = L(
    "\t\t\t\t\tstatic float s_plrStep = 0.0f;",
    "\t\t\t\t\t",
    "\t\t\t\t\t// ---- " + MARK + " ----",
    "\t\t\t\t\t//",
    "\t\t\t\t\t// The 22:54 run settles what the four witnesses above could not: asked",
    "\t\t\t\t\t// what the freeze looks like, the answer is \"the picture is completely",
    "\t\t\t\t\t// frozen, how am I supposed to move\" -- every run, from the moment the",
    "\t\t\t\t\t// world loads. keys=0x0 and dc=0 are a consequence of that, not evidence",
    "\t\t\t\t\t// against it: an image that never changes gives no reason to press",
    "\t\t\t\t\t// anything, and a game that takes no input shows no reason either.",
    "\t\t\t\t\t//",
    "\t\t\t\t\t// So the ambiguity L33 was written about is gone and a sharper one takes",
    "\t\t\t\t\t// its place. The present loop is alive the whole time -- the watchdog",
    "\t\t\t\t\t// reports alive=1 focus=1, presentAge in single-digit ms, frames",
    "\t\t\t\t\t// advancing 30/s -- and the image is not. These witnesses are read from",
    "\t\t\t\t\t// the GAME, not from the renderer, so they split that pair:",
    "\t\t\t\t\t//",
    "\t\t\t\t\t//   hrsD > 0    the game clock runs     -> the game logic is alive, and",
    "\t\t\t\t\t//                                          the stale image is ours",
    "\t\t\t\t\t//   hrsD == 0   the game clock is stopped -> the game is paused, and the",
    "\t\t\t\t\t//                                          frozen image is a symptom",
    "\t\t\t\t\t//",
    "\t\t\t\t\t// paused / ld / fade name the pause directly.",
    "\t\t\t\t\tstatic bool  s_livePaused  = false;",
    "\t\t\t\t\tstatic bool  s_liveLd      = false;",
    "\t\t\t\t\tstatic bool  s_liveFade    = false;",
    "\t\t\t\t\tstatic float s_liveHrs     = 0.0f;",
    "\t\t\t\t\tstatic float s_liveHrsD    = 0.0f;",
    "\t\t\t\t\tstatic bool  s_liveHrsHave = false;",
    "\t\t\t\t\tstatic float s_liveRaw     = 0.0f;",
    "\t\t\t\t\tstatic float s_liveRawD    = 0.0f;",
    "\t\t\t\t\tstatic bool  s_liveRawHave = false;",
)

# E2 (engine key state via RE::BSInputDeviceManager::GetKeyboard()) was written and
# REMOVED: calling GetKeyboard() pulls BSWin32KeyboardDevice.cpp.obj and
# BSKeyboardDevice.cpp.obj out of CommonLibSSE.lib, and those translation units
# reference fourteen RE::BSInputDevice virtuals that the prebuilt library does not
# define, so the link dies with fourteen LNK2001s. The OS probe above already
# answers "was a key pressed"; this one was the least of the four witnesses.

# ------------------------------------------------- E3: pause / clock witnesses
E3_OLD = "\t\t\t\t\tif (snapPcEyeHave) {"

E3_NEW = L(
    "\t\t\t\t\t// v1.19: the game's own clock and its own pause state, read-only.",
    "\t\t\t\t\t// hrs / raw are the same quantity from two sources: GetHoursPassed()",
    "\t\t\t\t\t// goes through the gameDaysPassed TESGlobal, rawDaysPassed is the plain",
    "\t\t\t\t\t// float the engine accumulates. Either one advancing proves the game",
    "\t\t\t\t\t// loop is running; both frozen at once, with the watchdog still",
    "\t\t\t\t\t// presenting, is a game that is not simulating.",
    "\t\t\t\t\t{",
    "\t\t\t\t\t\tauto* ui = RE::UI::GetSingleton();",
    "\t\t\t\t\t\tif (ui) {",
    "\t\t\t\t\t\t\ts_livePaused = ui->GameIsPaused();",
    "\t\t\t\t\t\t\ts_liveLd     = ui->IsMenuOpen(\"Loading Menu\");",
    "\t\t\t\t\t\t\ts_liveFade   = ui->IsMenuOpen(\"Fader Menu\");",
    "\t\t\t\t\t\t}",
    "\t\t\t\t\t\tauto* cal = RE::Calendar::GetSingleton();",
    "\t\t\t\t\t\tif (cal) {",
    "\t\t\t\t\t\t\tconst float h = cal->GetHoursPassed();",
    "\t\t\t\t\t\t\tif (s_liveHrsHave && h > s_liveHrs)",
    "\t\t\t\t\t\t\t\ts_liveHrsD += (h - s_liveHrs);",
    "\t\t\t\t\t\t\ts_liveHrs = h;",
    "\t\t\t\t\t\t\ts_liveHrsHave = true;",
    "\t\t\t\t\t\t\tconst float r = cal->rawDaysPassed * 24.0f;",
    "\t\t\t\t\t\t\tif (s_liveRawHave && r > s_liveRaw)",
    "\t\t\t\t\t\t\t\ts_liveRawD += (r - s_liveRaw);",
    "\t\t\t\t\t\t\ts_liveRaw = r;",
    "\t\t\t\t\t\t\ts_liveRawHave = true;",
    "\t\t\t\t\t\t}",
    "\t\t\t\t\t}",
    "\t\t\t\t\tif (snapPcEyeHave) {",
)

# ------------------------------------------------------------- E4: the log line
E4_OLD = L(
    "\t\t\t\t\tSKSE::log::info(\"[CAM] PC v1.18: read={} match={} adopt={}/{} rej={} ref={} \"",
    "\t\t\t\t\t\t\"best={:.2f} at proj00={:.6g} eye=({:.2f},{:.2f},{:.2f}) eyeD={:.2f} \"",
    "\t\t\t\t\t\t\"in(keys=0x{:x} dc={:.0f}/{} fg={}) plr=({:.1f},{:.1f},{:.1f}) plrD={:.2f} {} {}\",",
    "\t\t\t\t\t\tsnapPcRead, snapPcMatch, snapPcAdoptSec, snapPcAdopt, snapPcReject,",
    "\t\t\t\t\t\tsnapPcRefSeen,",
    "\t\t\t\t\t\tsnapPcSawAny ? snapPcBestDist : -1.0f, snapPcBestProj,",
    "\t\t\t\t\t\tsnapPcLast[0], snapPcLast[1], snapPcLast[2], snapPcEyeStep,",
    "\t\t\t\t\t\ts_inKeys, s_inDist, s_inMoves, s_inFg,",
    "\t\t\t\t\t\ts_plrPos[0], s_plrPos[1], s_plrPos[2], s_plrStep,",
    "\t\t\t\t\t\tsnapPcEyeStep <= kCamMoveEps ? \"PC_STILL\" : \"PC_MOVING\",",
    "\t\t\t\t\t\t(s_inKeys != 0u || s_inMoves != 0u)",
    "\t\t\t\t\t\t\t? \"INPUT_SEEN - input reached the window, so eyeD 0 here means a frozen world, not an idle player\"",
    "\t\t\t\t\t\t\t: \"INPUT_NONE - no key and no mouse motion this second, so an idle player and a frozen world still read the same: re-run and MOVE\");",
)

E4_NEW = L(
    "\t\t\t\t\tSKSE::log::info(\"[CAM] PC v1.19: read={} match={} adopt={}/{} rej={} ref={} \"",
    "\t\t\t\t\t\t\"best={:.2f} at proj00={:.6g} eye=({:.2f},{:.2f},{:.2f}) eyeD={:.2f} \"",
    "\t\t\t\t\t\t\"in(os=0x{:x} dc={:.0f}/{} fg={}) \"",
    "\t\t\t\t\t\t\"plr=({:.1f},{:.1f},{:.1f}) plrD={:.2f} \"",
    "\t\t\t\t\t\t\"LIVE paused={} ld={} fade={} hrs={:.5f} hrsD={:.6f} rawD={:.6f} {} {}\",",
    "\t\t\t\t\t\tsnapPcRead, snapPcMatch, snapPcAdoptSec, snapPcAdopt, snapPcReject,",
    "\t\t\t\t\t\tsnapPcRefSeen,",
    "\t\t\t\t\t\tsnapPcSawAny ? snapPcBestDist : -1.0f, snapPcBestProj,",
    "\t\t\t\t\t\tsnapPcLast[0], snapPcLast[1], snapPcLast[2], snapPcEyeStep,",
    "\t\t\t\t\t\ts_inKeys, s_inDist, s_inMoves, s_inFg,",
    "\t\t\t\t\t\ts_plrPos[0], s_plrPos[1], s_plrPos[2], s_plrStep,",
    "\t\t\t\t\t\ts_livePaused ? 1 : 0, s_liveLd ? 1 : 0, s_liveFade ? 1 : 0,",
    "\t\t\t\t\t\ts_liveHrs, s_liveHrsD, s_liveRawD,",
    "\t\t\t\t\t\tsnapPcEyeStep <= kCamMoveEps ? \"PC_STILL\" : \"PC_MOVING\",",
    "\t\t\t\t\t\t(s_inKeys != 0u || s_inMoves != 0u)",
    "\t\t\t\t\t\t\t? \"INPUT_SEEN - input reached the game, so a still eyeD here is a frozen world\"",
    "\t\t\t\t\t\t\t: \"INPUT_NONE - nothing was pressed this second, so this run cannot say whether input works\");",
)

# ----------------------------------------------------------------- E5: resets
E5_OLD = L(
    "\t\t\t\t\ts_inKeys = 0u;",
    "\t\t\t\t\ts_inDist = 0.0f;",
    "\t\t\t\t\ts_inMoves = 0u;",
    "\t\t\t\t\ts_plrStep = 0.0f;",
)

E5_NEW = L(
    "\t\t\t\t\ts_inKeys = 0u;",
    "\t\t\t\t\ts_inDist = 0.0f;",
    "\t\t\t\t\ts_inMoves = 0u;",
    "\t\t\t\t\ts_plrStep = 0.0f;",
    "\t\t\t\t\ts_liveHrsD = 0.0f;",
    "\t\t\t\t\ts_liveRawD = 0.0f;",
)

EDITS = [
    ("E1  statics",   E1_OLD, E1_NEW),
    ("E3  clock+pause", E3_OLD, E3_NEW),
    ("E4  log line",  E4_OLD, E4_NEW),
    ("E5  resets",    E5_OLD, E5_NEW),
]

# token -> how many MORE times it must appear in the RESULT than in the input.
# These are DELTAS on purpose: several of the tokens already exist in the file
# (RE::BSInputDeviceManager::GetSingleton() at line 312, for one), so an
# absolute count would be thrown off by text this patch never touched.
#
# Every value below was counted by hand against the three blocks that mention
# the name (declaration / assignment / log argument), because the first draft
# of this table was wrong in seven places and the post-conditions correctly
# refused to write the file.
POST = [
    ("[CAM] PC v1.19",              1),
    ("s_livePaused",                3),   # E1 decl + E3 assign + E4 arg
    ("s_liveLd",                    3),
    ("s_liveFade",                  3),
    ("s_liveHrsD",                  4),   # + E5 reset
    ("s_liveRawD",                  4),
    ("RE::Calendar::GetSingleton()", 1),
    ("cal->GetHoursPassed()",       1),
    ("cal->rawDaysPassed",          1),
    ("ui->GameIsPaused()",          1),
    ("IsMenuOpen(\"Loading Menu\")", 1),
    ("IsMenuOpen(\"Fader Menu\")",   1),
    (MARK,                          1),
]

# text that the patch REMOVES -> must be gone afterwards
POST_GONE = [
    "[CAM] PC v1.18",
    "an idle player and a frozen world still read the same: re-run and MOVE",
]


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    src, raw = load(CPP)
    eol = eol_of(CPP)

    if revert:
        if MARK not in src:
            print("nothing to revert (marker absent)")
            return 0
        out = src
        for label, old, new in reversed(EDITS):
            o = new.replace("\n", eol)
            r = old.replace("\n", eol)
            if out.count(o) != 1:
                print("REFUSED, nothing written: revert %s count = %d" % (label, out.count(o)))
                return 1
            out = out.replace(o, r, 1)
        CPP.write_bytes(out.encode("utf-8"))
        print("reverted %d edits" % len(EDITS))
        return 0

    if MARK in src:
        print("REFUSED: already applied (marker present)")
        return 1

    for label, old, new in EDITS:
        o = old.replace("\n", eol)
        n = src.count(o)
        if n != 1:
            print("REFUSED, nothing written: %s anchor count = %d (must be 1)" % (label, n))
            return 1

    if not apply:
        print("dry run OK: %d/%d anchors unique in src/FrameGen.cpp" % (len(EDITS), len(EDITS)))
        for label, _o, _n in EDITS:
            print("  would patch " + label)
        return 0

    out = src
    for label, old, new in EDITS:
        o = old.replace("\n", eol)
        r = new.replace("\n", eol)
        out = out.replace(o, r, 1)
        print("  patched " + label)

    # post-conditions are measured on the RESULT text, and as DELTAS against the
    # input, because a plain count is thrown off by strings the file already had.
    bad = []
    for token, want in POST:
        got = out.count(token) - src.count(token)
        if got != want:
            bad.append((token, got, want))
    for token in POST_GONE:
        if out.count(token) != 0:
            bad.append((token + " (must be gone)", out.count(token), 0))
    # each edit's new block must be present exactly once, which also proves the
    # splice did not land twice and did not land nowhere
    for label, _old, new in EDITS:
        r = new.replace("\n", eol)
        if out.count(r) != 1:
            bad.append((label + " (new block count)", out.count(r), 1))
    if bad:
        for tok, got, want in bad:
            print("POST-CONDITION FAIL: %s = %d, wanted %d" % (tok, got, want))
        return 1

    if "\n" in out.replace(eol, ""):
        print("REFUSED, nothing written: result would contain a stray newline")
        return 1

    CPP.write_bytes(out.encode("utf-8"))
    print("wrote src/FrameGen.cpp (%d bytes, was %d)" % (len(out.encode("utf-8")), len(raw)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
