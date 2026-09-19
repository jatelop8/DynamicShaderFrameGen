#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.18: the input witness and the foreground witness.

WHY THIS PATCH EXISTS
---------------------
Three runs in a row (22:02, 22:22, 22:38) ended with the same shape and could
not be settled: a world segment a couple of seconds long, the live player camera
byte-identical at two decimals, `clipToPrevClip` collapsing to identity. Every
field on the `[CAM] PC` line is downstream of the camera, so

    the player is standing still      -> identity, and identity is CORRECT
    the world is frozen by the engine -> identity, and identity is the freeze

produce byte-identical logs. Both readings fit the data; the criterion cannot
separate them. That is L33: a criterion measured only downstream of the fault
cannot name the fault.

The 22:38 run made this sharper than ever, because for the first time the source
was provably right: `[CAM] PC v1.17 ... match=397/read=423 best=0.00 at
proj00=0.8391`, and the family census agreed (`FAM[2] proj00=0.8391 arr=397
moved=0 stepSum=0.08 span=(0,0,0)`). The lock sat on the live camera for 60
frames and the picture still did not move -- because the camera did not move.

WHAT THIS ADDS
--------------
Four witnesses upstream of the game entirely, so they can separate the two
readings where the camera cannot:

  keys   Win32 key state (W A S D SPACE SHIFT LMB RMB), sampled on every arrival
         and OR-ed across the second. Non-zero with eyeD == 0 means the input
         reached the window and the world did not move.

  dc     cursor distance travelled this second, plus the count of arrivals that
         saw cursor motion. Skyrim reads the mouse through raw input, but
         ClipCursor still moves the system cursor inside the clip rect, so a
         look-around moves this even when eyeD is 0 -- eye is the camera ORIGIN
         and a pure turn does not move it.

  fg     the foreground window's process id against our own. Skyrim pauses the
         world when it loses focus, so fg=0 with a frozen eye completely
         explains "the picture is stuck" and needs no repair in this plugin.

  plrD   how far RE::PlayerCharacter travelled this second. The one witness
         that is neither camera nor input: a player who moves while the camera
         does not localises the fault to this plugin; a player who does not move
         means the run cannot answer the question and must be repeated.

The judgement word becomes two words, so the log states the reading instead of
leaving it to the reader:

  PC_STILL INPUT_NONE   -> idle player; the run cannot decide anything
  PC_STILL INPUT_SEEN   -> input arrived and the world did not move; REAL FAULT
  PC_MOVING ...         -> normal

Zero behaviour change: nothing here gates, selects or publishes. It only reads.

Dry run by default; --apply writes. Every anchor must occur exactly once, and
the marker makes a second run a no-op.
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CPP = ROOT / "src" / "FrameGen.cpp"

MARK = "v1.18: THE INPUT WITNESS"

T5 = "\t" * 5
T6 = "\t" * 6
T7 = "\t" * 7


def L(*ls):
    """Join lines with LF. One argument per line -- an adjacency mistake is
    impossible here, which is the whole reason this helper exists: the first
    draft of this script wrote `T5 + "a"` / `T5 + "b"` on consecutive lines and
    Python read it as two adjacent expressions, not a concatenation."""
    return "".join(l + "\n" for l in ls)


# ------------------------------------------------------------------ E1 anchors
E1_OLD = L(
    T5 + "if (snapPcEyeHave) {",
    T6 + "const float pdx = snapPcLast[0] - snapPcPrevEye[0];",
)

E1_NEW = L(
    T5 + "// ---- v1.18: THE INPUT WITNESS + THE FOREGROUND WITNESS ----",
    T5 + "//",
    T5 + "// Three runs (22:02, 22:22, 22:38) could not be settled, and the 22:38",
    T5 + "// run is the clearest of them: the lock provably sat on the live camera",
    T5 + "// (match=397/read=423, best=0.00, proj00=0.8391) and the family census",
    T5 + "// agreed (FAM[2] moved=0 stepSum=0.08 span=(0,0,0)) -- and the picture",
    T5 + "// still did not move, because the camera did not move.",
    T5 + "//",
    T5 + "// Every field that existed until now is DOWNSTREAM of the camera, so two",
    T5 + "// opposite worlds print the same line:",
    T5 + "//",
    T5 + "//   the player is standing still   -> identity, and identity is CORRECT",
    T5 + "//   the world is frozen by the game -> identity, and identity IS the freeze",
    T5 + "//",
    T5 + "// The four witnesses below are upstream of the game, so they separate the",
    T5 + "// two readings that the camera cannot. That is L33: a criterion measured",
    T5 + "// only downstream of the fault cannot name the fault.",
    T5 + "static std::uint32_t s_inKeys = 0u;",
    T5 + "static std::uint32_t s_inMoves = 0u;",
    T5 + "static float s_inDist = 0.0f;",
    T5 + "static float s_inCurPrev[2] = { 0.0f, 0.0f };",
    T5 + "static bool s_inCurHave = false;",
    T5 + "static int s_inFg = -1;",
    T5 + "static float s_plrPos[3] = { 0.0f, 0.0f, 0.0f };",
    T5 + "static float s_plrPrev[3] = { 0.0f, 0.0f, 0.0f };",
    T5 + "static bool s_plrHave = false;",
    T5 + "static float s_plrStep = 0.0f;",
    T5 + "",
    T5 + "{",
    T6 + "std::uint32_t keys = 0u;",
    T6 + "if (::GetAsyncKeyState('W') & 0x8000) keys |= 1u;",
    T6 + "if (::GetAsyncKeyState('A') & 0x8000) keys |= 2u;",
    T6 + "if (::GetAsyncKeyState('S') & 0x8000) keys |= 4u;",
    T6 + "if (::GetAsyncKeyState('D') & 0x8000) keys |= 8u;",
    T6 + "if (::GetAsyncKeyState(VK_SPACE) & 0x8000) keys |= 16u;",
    T6 + "if (::GetAsyncKeyState(VK_SHIFT) & 0x8000) keys |= 32u;",
    T6 + "if (::GetAsyncKeyState(VK_LBUTTON) & 0x8000) keys |= 64u;",
    T6 + "if (::GetAsyncKeyState(VK_RBUTTON) & 0x8000) keys |= 128u;",
    T6 + "s_inKeys |= keys;",
    T6 + "",
    T6 + "POINT pt{};",
    T6 + "if (::GetCursorPos(&pt)) {",
    T7 + "if (s_inCurHave) {",
    T7 + "\tconst float cdx = static_cast<float>(pt.x) - s_inCurPrev[0];",
    T7 + "\tconst float cdy = static_cast<float>(pt.y) - s_inCurPrev[1];",
    T7 + "\tconst float cstep = std::sqrt(cdx * cdx + cdy * cdy);",
    T7 + "\ts_inDist += cstep;",
    T7 + "\tif (cstep > 0.0f)",
    T7 + "\t\t++s_inMoves;",
    T7 + "}",
    T7 + "s_inCurPrev[0] = static_cast<float>(pt.x);",
    T7 + "s_inCurPrev[1] = static_cast<float>(pt.y);",
    T7 + "s_inCurHave = true;",
    T6 + "}",
    T6 + "",
    T6 + "const HWND fwnd = ::GetForegroundWindow();",
    T6 + "DWORD fpid = 0;",
    T6 + "if (fwnd)",
    T7 + "::GetWindowThreadProcessId(fwnd, &fpid);",
    T6 + "s_inFg = (fwnd && fpid == ::GetCurrentProcessId()) ? 1 : 0;",
    T5 + "}",
    T5 + "{",
    T6 + "const auto* plr = RE::PlayerCharacter::GetSingleton();",
    T6 + "if (plr) {",
    T7 + "const auto& pp = plr->GetPosition();",
    T7 + "s_plrPos[0] = pp.x;",
    T7 + "s_plrPos[1] = pp.y;",
    T7 + "s_plrPos[2] = pp.z;",
    T7 + "if (s_plrHave) {",
    T7 + "\tconst float qx = s_plrPos[0] - s_plrPrev[0];",
    T7 + "\tconst float qy = s_plrPos[1] - s_plrPrev[1];",
    T7 + "\tconst float qz = s_plrPos[2] - s_plrPrev[2];",
    T7 + "\ts_plrStep = std::sqrt(qx * qx + qy * qy + qz * qz);",
    T7 + "}",
    T7 + "s_plrHave = true;",
    T7 + "s_plrPrev[0] = s_plrPos[0];",
    T7 + "s_plrPrev[1] = s_plrPos[1];",
    T7 + "s_plrPrev[2] = s_plrPos[2];",
    T6 + "}",
    T5 + "}",
    T5 + "",
    T5 + "if (snapPcEyeHave) {",
    T6 + "const float pdx = snapPcLast[0] - snapPcPrevEye[0];",
)

# ------------------------------------------------------------------ E2 anchors
E2_OLD = L(
    T5 + 'SKSE::log::info("[CAM] PC v1.17: read={} match={} adopt={}/{} rej={} ref={} "',
    T6 + '"best={:.2f} at proj00={:.6g} eye=({:.2f},{:.2f},{:.2f}) eyeD={:.2f} {}",',
)

E2_NEW = L(
    T5 + 'SKSE::log::info("[CAM] PC v1.18: read={} match={} adopt={}/{} rej={} ref={} "',
    T6 + '"best={:.2f} at proj00={:.6g} eye=({:.2f},{:.2f},{:.2f}) eyeD={:.2f} "',
    T6 + '"in(keys=0x{:x} dc={:.0f}/{} fg={}) plr=({:.1f},{:.1f},{:.1f}) plrD={:.2f} {} {}",',
)

# ------------------------------------------------------------------ E3 anchors
E3_OLD = L(
    T6 + "snapPcLast[0], snapPcLast[1], snapPcLast[2], snapPcEyeStep,",
    T6 + "snapPcEyeStep <= kCamMoveEps",
    T7 + '? "PC_STILL - the live camera did not move: an unchanged picture is CORRECT here"',
    T7 + ': "PC_MOVING - the live camera is walking");',
)

E3_NEW = L(
    T6 + "snapPcLast[0], snapPcLast[1], snapPcLast[2], snapPcEyeStep,",
    T6 + "s_inKeys, s_inDist, s_inMoves, s_inFg,",
    T6 + "s_plrPos[0], s_plrPos[1], s_plrPos[2], s_plrStep,",
    T6 + 'snapPcEyeStep <= kCamMoveEps ? "PC_STILL" : "PC_MOVING",',
    T6 + "(s_inKeys != 0u || s_inMoves != 0u)",
    T7 + '? "INPUT_SEEN - input reached the window, so eyeD 0 here means a frozen world, not an idle player"',
    T7 + ': "INPUT_NONE - no key and no mouse motion this second, so an idle player and a frozen world still read the same: re-run and MOVE");',
)

# ------------------------------------------------------------------ E4 anchors
E4_OLD = L(
    T5 + "snapPcRead = 0;",
    T5 + "snapPcMatch = 0;",
    T5 + "snapPcAdoptSec = 0;",
)

E4_NEW = L(
    T5 + "s_inKeys = 0u;",
    T5 + "s_inDist = 0.0f;",
    T5 + "s_inMoves = 0u;",
    T5 + "snapPcRead = 0;",
    T5 + "snapPcMatch = 0;",
    T5 + "snapPcAdoptSec = 0;",
)

EDITS = [
    ("E1  readers (keys / cursor / foreground / player)", E1_OLD, E1_NEW),
    ("E2  PC line header -> v1.18 + new fields", E2_OLD, E2_NEW),
    ("E3  arguments + two judgement words", E3_OLD, E3_NEW),
    ("E4  per-second reset", E4_OLD, E4_NEW),
]


def eol_of(path):
    b = path.read_bytes()
    return "\r\n" if b.count(b"\r\n") > 0 else "\n"


def load(path):
    # Never Path.read_text(): it applies universal-newline translation and would
    # silently turn every CRLF anchor into LF, so all anchors miss.
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

    # Post-conditions on the RESULT text, never on the input.
    #
    # Absolute counts are wrong here: FrameGen.cpp already contains three
    # GetAsyncKeyState calls of its own, so "8" failed on the first run and the
    # write was refused. Count the DELTA this patch contributed instead -- that
    # is what the patch is responsible for and it cannot drift with the file.
    def delta(t):
        return out.count(t) - src.count(t)

    checks = [
        ("new PC header", out.count("[CAM] PC v1.18: read="), 1),
        ("old PC header gone", out.count("[CAM] PC v1.17: read="), 0),
        ("keys sampled (+8)", delta("GetAsyncKeyState"), 8),
        ("cursor probed (+1)", delta("::GetCursorPos"), 1),
        ("foreground probed (+1)", delta("::GetForegroundWindow()"), 1),
        ("player probed (+1)", delta("RE::PlayerCharacter::GetSingleton()"), 1),
        ("INPUT_SEEN word (+1)", delta("INPUT_SEEN"), 1),
        ("INPUT_NONE word (+1)", delta("INPUT_NONE"), 1),
        ("marker (+1)", delta(MARK), 1),
        ("s_inKeys (+5)", delta("s_inKeys"), 5),
        ("s_plrStep (+3)", delta("s_plrStep"), 3),
    ]
    bad = [(n, g, w) for n, g, w in checks if g != w]
    if bad:
        for n, g, w in bad:
            print("POST-CONDITION FAIL: %s = %d, wanted %d" % (n, g, w))
        return 1

    if "\n" in out.replace(eol, ""):
        print("REFUSED, nothing written: the result would contain a stray newline")
        return 1

    save(CPP, out)
    print("wrote %s (%d bytes, was %d)" % (CPP.name, len(out.encode()), len(src.encode())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
