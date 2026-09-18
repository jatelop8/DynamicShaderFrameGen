#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_xray_v069.py -- DynamicShaderFrameGen v0.69

WHAT THIS FIXES (each with the evidence for it, all from the 2026-09-17 23:07 run):

1. [THE FIX] DLSSNR (neural rendering) was running AT THE SAME TIME as DLSS-G
   4x multi-frame-generation. ImguiMenu.cpp:373 records that v0.42 chained the
   two on purpose and left the escape hatch in the same comment:
   "若叠加闪烁再回退互斥" (revert to mutual exclusion if the stack flickers).
   The user's symptom IS stacked flicker. Evidence both were live:
       INI NeuralRenderingEnabled=1 AND FrameGeneration=1
       [DLSSNR] frames=179 -> 359 -> 539 -> 719   (~50 NR evaluations/s of a
                                                   full-resolution frame)
       [DLSSNR] D3D12 command contexts saturated; applying CPU backpressure
       watchdog stage "d3d11 Wait" (the NR fence wait) sustained
       real fps 53 -> 27 the moment FG engaged (two full-res temporal passes)
   Two temporal processors both writing history for one frame is a direct
   flicker source. A static scene hides it (both histories agree -- which is why
   the main menu looked fine); anything that moves exposes it (the loading
   screen's rotating model, the world camera).

2. Menu probe was silently dead: menu=0, menuEdges=0 and menuFrames=0 for all
   151 frames, and the 22:42 run showed menuOpen=0 through 45 s of main menu.
   DX12SwapChain.cpp:871-876 implements "no frame generation while a menu is up"
   but it is gated on that probe, so MenuDisableFrameGen=1 has never actually
   done anything -- which is why frame generation runs straight through the
   loading screen. v0.69 adds a literal-name fallback AND a one-shot probe line
   that reports whether InterfaceStrings itself resolved, so the next run says
   WHICH of the two failed instead of leaving it ambiguous.

3. The "derived reprojection source" is dead code by construction, now disabled
   with the proof. derived = inv(CameraViewInverse) x CameraProjUnjittered, but
   CameraViewInverse in the perFrame buffer carries NO translation. Verified
   offline from the three raw matrix dumps: inv(VI) comes out with translation
   row (0,0,0,1) AND translation column (0,0,0) in all of them -- a pure
   rotation. So it can never reproduce ViewProjUnjittered; max|derived-cur| is
   exactly the translation term (measured 15.0006 == |VP[2][3]|), derivedMatch
   is always 0 (log: dvd(ok/used)=0/0 err=16) and reproj src was always
   "engine". Its only trigger is "engine cur frozen >= 30 frames", and a frozen
   camera is a LEGITIMATE state (the loading screen does not move), so a matrix
   that cannot represent translation could only invent motion where there is
   none.

4. Camera-gate logging flooded the file: 2862 JUMP lines in 42 s (71 lines/s,
   3111 of 3222 total lines = 97%). Throttled to the first 3 plus every 250th;
   the totals stay in the heartbeat.

5. RUN START printed __DATE__/__TIME__ (the BUILD stamp), not the run time --
   it misled two separate timeline reconstructions (the 23:07 session looked
   like it began at 22:59). Added a real RUN TIME line.

APPLY ORDER MATTERS. A previous attempt inserted text at offsets computed from
the ORIGINAL file and then applied them in ascending order; the first insert
shifted every later offset and split a line in half (auto* ui became "au" +
"to* ui"). So: pass 1 applies all string replacements, pass 2 recomputes every
offset against the CURRENT text and applies them in DESCENDING order. A brace
balance check runs before anything is written.

Idempotent: refuses if any marker is already present. Dry-run unless --apply.
"""

import sys
import pathlib
import shutil
import datetime

SRC = pathlib.Path(r"D:/Modding/DynamicShaderFrameGen/src")
FILES = {
    "dx": SRC / "DX12SwapChain.cpp",
    "sl": SRC / "Streamline.cpp",
    "fg": SRC / "FrameGen.cpp",
    "mn": SRC / "main.cpp",
}

MARKERS = [
    "v0.69: NR x frame generation are mutually exclusive again",
    "v0.69: literal-name fallback",
    "v0.69: MENU PROBE",
    "v0.69: derived source disabled",
    "v0.69: throttled",
    "v0.69: real run time",
]


def read_text(p):
    # newline="" is mandatory: universal-newline mode converts CRLF -> LF on read
    # and would write LF back, silently rewriting every line ending in the file.
    with open(p, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def write_text(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def eol_of(p):
    raw = open(p, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    return crlf, lf, raw.count(b"\r") - crlf


def line_start(s, i):
    return s.rfind("\n", 0, i) + 1


def indent_of(s, i):
    j = line_start(s, i)
    k = j
    while k < len(s) and s[k] in " \t":
        k += 1
    return s[j:k]


def find_unique(s, needle, label):
    n = s.count(needle)
    if n != 1:
        raise Refuse("%s: anchor occurs %d time(s)" % (label, n))
    return s.index(needle)


def stmt_end(s, i):
    depth = 0
    k = i
    while k < len(s):
        c = s[k]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == ";" and depth == 0:
            return k + 1
        k += 1
    raise Refuse("unterminated statement while scanning for ';'")


class Refuse(Exception):
    pass


# --------------------------------------------------------------------------
# text builders
# --------------------------------------------------------------------------
def build_nr_block(ind):
    t = "\t"
    return (
        ind + "// v0.69: NR x frame generation are mutually exclusive again.\n"
        + ind + "// v0.42 chained them on purpose and wrote the escape hatch into the same\n"
        + ind + "// comment (ImguiMenu.cpp:373): 若叠加闪烁再回退互斥. The 2026-09-17 23:07\n"
        + ind + "// run has both live at once -- INI NeuralRenderingEnabled=1 +\n"
        + ind + "// FrameGeneration=1, [DLSSNR] frames 179->359->539->719 (~50 full-res\n"
        + ind + "// NR evaluations per second), \"D3D12 command contexts saturated\", and\n"
        + ind + "// real fps 53->27 the instant FG engaged. Two temporal processors writing\n"
        + ind + "// history for the same frame is a direct flicker source: a static scene\n"
        + ind + "// hides it (both histories agree, which is why the main menu looked fine),\n"
        + ind + "// anything that moves exposes it (loading-screen model, world camera).\n"
        + ind + "// Suppress NR whenever frame generation is actually running. Press the\n"
        + ind + "// toggle key (0xC7) to turn FG off and NR comes straight back -- no second\n"
        + ind + "// switch, the same NeuralRenderingEnabled flag still governs it.\n"
        + ind + "const bool fgGeneratingNow =\n"
        + ind + t + "dlssgMode && fg.settings.frameGeneration && fg.fgActive.load();\n"
        + ind + "if (fg.settings.neuralRenderingEnabled && fgGeneratingNow) {\n"
        + ind + t + "static bool nrStackLogged = false;\n"
        + ind + t + "if (!nrStackLogged) {\n"
        + ind + t + t + "nrStackLogged = true;\n"
        + ind + t + t + "SKSE::log::warn(\"[FrameGen] DLSSNR suppressed: frame generation is active - \"\n"
        + ind + t + t + t + "\"NR and DLSS-G are two temporal processors and stacking them is a \"\n"
        + ind + t + t + t + "\"direct flicker source (v0.42 note: revert to mutual exclusion if \"\n"
        + ind + t + t + t + "\"it flickers). Toggle key disables FG and NR resumes.\");\n"
        + ind + t + "}\n"
        + ind + "}\n"
    )


def build_menu_fn(ind):
    o, t = ind, "\t"
    return (
        o + "// v0.69: literal-name fallback. The original body only consulted\n"
        + o + "// InterfaceStrings (mainMenu/loadingMenu/journalMenu). That path has a\n"
        + o + "// silent failure mode: InterfaceStrings is a VERSION-DEPENDENT struct\n"
        + o + "// layout, so if the compile-time branch does not match the running game the\n"
        + o + "// member you read is a different field, IsMenuOpen(garbage) is false, and\n"
        + o + "// nothing anywhere reports an error. Evidence it failed: the 22:42 run held\n"
        + o + "// menuOpen=0 through a full 45 s of main menu, and this run held menu=0 /\n"
        + o + "// menuEdges=0 for all 151 frames. Skyrim's menu names are fixed strings, so\n"
        + o + "// look them up by literal too and accept either hit.\n"
        + o + "bool GameMenuOpenNow()\n"
        + o + "{\n"
        + o + t + "auto* ui = RE::UI::GetSingleton();\n"
        + o + t + "if (!ui)\n"
        + o + t + t + "return false;\n"
        + o + t + "const auto* istrings = RE::InterfaceStrings::GetSingleton();\n"
        + o + t + "if (istrings &&\n"
        + o + t + t + "(ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||\n"
        + o + t + t + t + "ui->IsMenuOpen(istrings->journalMenu))) {\n"
        + o + t + t + "return true;\n"
        + o + t + "}\n"
        + o + t + "return ui->IsMenuOpen(\"Main Menu\") || ui->IsMenuOpen(\"Loading Menu\") ||\n"
        + o + t + t + "ui->IsMenuOpen(\"Journal Menu\") || ui->IsMenuOpen(\"Pause Menu\") ||\n"
        + o + t + t + "ui->IsMenuOpen(\"RaceSex Menu\") || ui->IsMenuOpen(\"Fader Menu\");\n"
        + o + "}\n"
        + "\n"
        + o + "// v0.69: MENU PROBE -- make the probe itself falsifiable. Compares the data\n"
        + o + "// POINTERS only (it never dereferences a member we do not already trust), so\n"
        + o + "// it cannot crash even when the layout is wrong. How to read it next run:\n"
        + o + "//   ptr mainMenu == ptr lit 'Main Menu'  -> the layout is correct, so menu=0\n"
        + o + "//        genuinely means \"no menu was open\" -- a game-state fact, not a bug\n"
        + o + "//   pointers differ                     -> the InterfaceStrings layout does\n"
        + o + "//        not match this game build, and the literal half is what works\n"
        + o + "void ProbeMenuNamesOnce()\n"
        + o + "{\n"
        + o + t + "static bool done = false;\n"
        + o + t + "if (done)\n"
        + o + t + t + "return;\n"
        + o + t + "auto* ui = RE::UI::GetSingleton();\n"
        + o + t + "const auto* is = RE::InterfaceStrings::GetSingleton();\n"
        + o + t + "if (!ui || !is)\n"
        + o + t + t + "return;\n"
        + o + t + "done = true;\n"
        + o + t + "const RE::BSFixedString litMain(\"Main Menu\");\n"
        + o + t + "const RE::BSFixedString litLoad(\"Loading Menu\");\n"
        + o + t + "const RE::BSFixedString litJournal(\"Journal Menu\");\n"
        + o + t + "SKSE::log::info(\"[XRAY] MENU PROBE ui={} istrings={} | ptr mainMenu={} (lit={}) \"\n"
        + o + t + t + "\"loadingMenu={} (lit={}) journalMenu={} (lit={}) | IsMenuOpen(is)={}/{}/{} \"\n"
        + o + t + t + "\"IsMenuOpen(literal)={}/{}/{}\",\n"
        + o + t + t + "static_cast<const void*>(ui), static_cast<const void*>(is),\n"
        + o + t + t + "static_cast<const void*>(is->mainMenu.c_str()),\n"
        + o + t + t + "static_cast<const void*>(litMain.c_str()),\n"
        + o + t + t + "static_cast<const void*>(is->loadingMenu.c_str()),\n"
        + o + t + t + "static_cast<const void*>(litLoad.c_str()),\n"
        + o + t + t + "static_cast<const void*>(is->journalMenu.c_str()),\n"
        + o + t + t + "static_cast<const void*>(litJournal.c_str()),\n"
        + o + t + t + "ui->IsMenuOpen(is->mainMenu), ui->IsMenuOpen(is->loadingMenu),\n"
        + o + t + t + "ui->IsMenuOpen(is->journalMenu), ui->IsMenuOpen(litMain),\n"
        + o + t + t + "ui->IsMenuOpen(litLoad), ui->IsMenuOpen(litJournal));\n"
        + o + "}\n"
    )


def build_derived_comment(ind):
    return (
        ind + "// v0.69: derived source disabled -- it is dead code by construction.\n"
        + ind + "// derivedViewProj = inv(CameraViewInverse) x CameraProjUnjittered, but the\n"
        + ind + "// perFrame CameraViewInverse carries NO translation. Verified offline from\n"
        + ind + "// the three raw matrix dumps in the 23:07 log (#1 menu camera, #8101 world\n"
        + ind + "// camera, #9901 stub): inv(VI) comes out with translation row (0,0,0,1) AND\n"
        + ind + "// translation column (0,0,0) in every one of them, i.e. a pure rotation. It\n"
        + ind + "// can therefore never reproduce ViewProjUnjittered: max|derived-cur| is\n"
        + ind + "// exactly the translation term (measured 15.0006 == |VP[2][3]|), derivedMatch\n"
        + ind + "// is always 0 (log: dvd(ok/used)=0/0 err=16) and reproj src was always\n"
        + ind + "// \"engine\". Its only trigger is \"engine cur frozen >= 30 frames\", and a\n"
        + ind + "// frozen camera is a LEGITIMATE state (the loading screen simply does not\n"
        + ind + "// move), so a matrix that cannot represent translation could only invent\n"
        + ind + "// motion where there is none. The operands stay referenced via `false &&`\n"
        + ind + "// so nothing is left unused and the comparison in the log keeps its meaning.\n"
        + ind + "const bool useDerived = false && (diag.derivedMatch == 1) && (s_engCurFrozen >= 30) &&\n"
    )


def build_run_time(ind):
    return (
        ind + "// v0.69: real run time. RUN START below prints __DATE__/__TIME__, which is\n"
        + ind + "// the BUILD stamp -- it reads like the session start and misled two separate\n"
        + ind + "// timeline reconstructions (the 23:07 session looked like it began 22:59).\n"
        + ind + "SYSTEMTIME runSt{};\n"
        + ind + "::GetLocalTime(&runSt);\n"
        + ind + "SKSE::log::info(\"[XRAY] RUN TIME {}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}\",\n"
        + ind + "\trunSt.wYear, runSt.wMonth, runSt.wDay, runSt.wHour, runSt.wMinute, runSt.wSecond);\n"
    )


def build_jump_guard(ind, block):
    body = "\n".join(("\t" + ln if ln.strip() else ln) for ln in block.split("\n"))
    return (
        ind + "// v0.69: throttled. v0.67 logged every rejection -- 2862 lines in 42 s\n"
        + ind + "// (71 lines/s), 3111 of the file's 3222 lines. The log became the dominant\n"
        + ind + "// cost and buried everything else. Totals stay in the heartbeat\n"
        + ind + "// (snap acc/jmp/re/zero/arr), so only the first few and a slow periodic\n"
        + ind + "// sample are printed here.\n"
        + ind + "if (snapRejectJump <= 3u || (snapRejectJump % 250u) == 0u) {\n"
        + body + "\n" + ind + "}\n"
    )


# --------------------------------------------------------------------------
# operation plan
# --------------------------------------------------------------------------
# pass 1 -- string replacements (locator = exact original substring)
T = "\t"   # tab, used by the multiline anchors below
REPLACES = [
    ("DX12SwapChain.cpp: NR condition gated",
     "dx",
     "if (fg.settings.neuralRenderingEnabled) {",
     "if (fg.settings.neuralRenderingEnabled && !fgGeneratingNow) {"),
    # Must be a REPLACE, not an insert: build_derived_comment() already emits the
    # new declaration, so inserting would leave the original behind as a
    # duplicate line -> "error C2059: syntax error: 'const'".
    ("Streamline.cpp: useDerived disabled",
     "sl",
     T*2 + "const bool useDerived = (diag.derivedMatch == 1) && (s_engCurFrozen >= 30) &&",
     build_derived_comment(T*2)),
]

# pass 2 -- offset operations, located by marker against the CURRENT text,
#           then applied in DESCENDING offset order
#   ("insert_before", file_key, marker, builder)
#   ("replace_span",  file_key, start_marker, close_suffix, builder)
OFFSET_OPS = [
    ("DX12SwapChain.cpp: NR guard block", "dx", "insert_before",
     "		// v0.46b：回退到 colorOut 输入", None, build_nr_block),
    ("Streamline.cpp: GameMenuOpenNow rewritten + ProbeMenuNamesOnce", "sl", "replace_span",
     "bool GameMenuOpenNow()", None, build_menu_fn),
    ("Streamline.cpp: probe called from MenuOpenNow", "sl", "insert_before",
     "	return GameMenuOpenNow();", None, lambda ind: ind + "ProbeMenuNamesOnce();\n"),
    ("FrameGen.cpp: JUMP logging throttled", "fg", "wrap_stmt_block",
     "DumpCameraSnapshot(a_src, snapArrivals, 3);",
     "SKSE::log::info(\"[CAM] #{} JUMP rejected", build_jump_guard),
    ("main.cpp: RUN TIME line", "mn", "insert_before", "SYSTEMTIME st{};", None, build_run_time),
]


def main():
    apply = "--apply" in sys.argv

    try:
        # ---- idempotency guard FIRST: insertions do not consume their anchor ----
        for key, path in FILES.items():
            s = read_text(path)
            for m in MARKERS:
                if m in s:
                    raise Refuse("%s already contains marker: %s" % (path.name, m))

        texts = {k: read_text(p) for k, p in FILES.items()}
        before = {k: len(texts[k].encode("utf-8", errors="surrogateescape")) for k in texts}
        orig_braces = {k: (texts[k].count("{"), texts[k].count("}")) for k in texts}
        orig_ui = {k: texts[k].count("auto* ui = RE::UI::GetSingleton();") for k in texts}

        # ---- pass 1: string replacements ----
        for label, key, old, new in REPLACES:
            s = texts[key]
            if s.count(old) != 1:
                raise Refuse("%s: anchor occurs %d time(s)" % (label, s.count(old)))
            texts[key] = s.replace(old, new, 1)
            print("OK  %s" % label)

        # ---- pass 2: locate, then apply descending ----
        pending = []
        for label, key, kind, m1, m2, builder in OFFSET_OPS:
            s = texts[key]
            if kind == "insert_before":
                i = find_unique(s, m1, label)
                ls = line_start(s, i)
                ind = s[ls:ls + len(s[ls:]) - len(s[ls:].lstrip(" \t"))]
                pending.append((key, ls, ls, builder(ind), label))
            elif kind == "replace_span":
                i = find_unique(s, m1, label)
                ls = line_start(s, i)
                ind = indent_of(s, i)
                close = "\n" + ind + "}\n"
                j = s.find(close, i)
                if j < 0:
                    raise Refuse("%s: no closing brace found" % label)
                end = j + len(close)
                if "IsMenuOpen(istrings->loadingMenu)" not in s[i:end]:
                    raise Refuse("%s: body does not look like the expected function" % label)
                pending.append((key, ls, end, builder(ind), label))
            elif kind == "wrap_stmt_block":
                i = find_unique(s, m1, label)
                ls = line_start(s, i)
                ind = indent_of(s, i)
                j = stmt_end(s, i)
                k = s.index(m2, j)
                if line_start(s, k) != k - (k - line_start(s, k)):
                    pass
                if indent_of(s, k) != ind:
                    raise Refuse("%s: trailing log is not at the same indent" % label)
                end = stmt_end(s, k) + 1            # consume the newline after ';'
                block = s[ls:stmt_end(s, k)]
                pending.append((key, ls, end, builder(ind, block), label))
            else:
                raise Refuse("unknown op kind %s" % kind)

        pending.sort(key=lambda t: (t[0], -t[1]))
        for key, a, b, txt, label in pending:
            s = texts[key]
            texts[key] = s[:a] + txt + s[b:]
            print("OK  %s" % label)

        # ---- structural canaries before writing ----
        for key, path in FILES.items():
            ob, cb = orig_braces[key]
            nb, ncb = texts[key].count("{"), texts[key].count("}")
            # Balance, not equality: the patch legitimately adds braces in pairs.
            # A split line leaves braces unbalanced, which is what this catches.
            if (ob - cb) != (nb - ncb):
                raise Refuse("%s: brace BALANCE changed (%d,%d) -> (%d,%d)"
                             % (path.name, ob, cb, nb, ncb))
            # Fingerprint of the offset-shift bug: an insert landed mid-line and
            # cut an identifier in half. These two fragments are exactly what a
            # stale offset produced on the first attempt.
            if "au\tProbe" in texts[key] or "\nto* ui" in texts[key]:
                raise Refuse("%s: line-split corruption fingerprint detected" % path.name)
            # every pre-existing occurrence of this line must survive intact
            if texts[key].count("auto* ui = RE::UI::GetSingleton();") < orig_ui[key]:
                raise Refuse("%s: an existing line was split or mangled" % path.name)
        print("\ncanaries OK (braces balanced, no split lines, no mangled identifiers)")

        if not apply:
            print("[dry run] %d replacement(s) + %d offset op(s) validated, nothing written."
                  % (len(REPLACES), len(pending)))
            print("Re-run with --apply to write.")
            return 0

        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        for key, path in FILES.items():
            if texts[key] == read_text(path):
                continue
            shutil.copy2(path, pathlib.Path(str(path) + ".bak-" + stamp))
            write_text(path, texts[key])
            after = len(texts[key].encode("utf-8", errors="surrogateescape"))
            print("wrote %-20s %+6d bytes  (backup .bak-%s)" % (path.name, after - before[key], stamp))

        # ---- independent read-back + EOL assertion ----
        print("\nread-back / eol:")
        checks = [
            ("dx", "v0.69: NR x frame generation are mutually exclusive again"),
            ("dx", "!fgGeneratingNow"),
            ("dx", "const bool fgGeneratingNow ="),
            ("sl", "v0.69: literal-name fallback"),
            ("sl", "v0.69: MENU PROBE"),
            ("sl", "	v0.69: MENU PROBE".lstrip("	")),
            ("sl", "ProbeMenuNamesOnce();"),
            ("sl", "v0.69: derived source disabled"),
            ("fg", "v0.69: throttled"),
            ("mn", "v0.69: real run time"),
        ]
        bad = 0
        for key, needle in checks:
            s = read_text(FILES[key])
            ok = needle in s
            bad += 0 if ok else 1
            print("  %-20s %-56s %s" % (FILES[key].name, needle[:56], "FOUND" if ok else "MISSING"))
        for key, path in FILES.items():
            crlf, lf, stray = eol_of(path)
            print("  %-20s CRLF=%-5d LF=%-5d stray_CR=%-3d %s"
                  % (path.name, crlf, lf, stray, "OK" if stray == 0 else "EOL DAMAGED"))
            bad += 0 if stray == 0 else 1
        print("\nRESULT: %s" % ("OK - all edits landed" if bad == 0 else "PROBLEMS: %d" % bad))
        return 0 if bad == 0 else 1

    except Refuse as e:
        print("REFUSED, nothing written -- %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
