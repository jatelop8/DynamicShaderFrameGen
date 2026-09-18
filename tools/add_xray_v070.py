#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_xray_v070.py -- v0.70: make the menu guard observable.

What this fixes, and the evidence for each edit
-----------------------------------------------
1) Streamline.cpp / .h -- hoist the menu sample.
   `isMenuOpen` used to be computed inside CheckFrameConstants, which is only
   reached from EvaluateDLSSG. `menuBlock` (DX12SwapChain) SKIPS EvaluateDLSSG.
   So on every frame the guard engaged, nothing updated diag.menuOpenNow,
   menuFrames, menuEdges, or the menu-edge reset.
   Consequence: `menu=0 world=151` in the 23:07 heartbeat cannot be told apart
   from "the guard engaged for all 151 frames" - the guard was unverifiable, and
   the reset edge could never fire on the frame it was meant to.
   Fix: sample once per frame in PollMenuState(), called from the Present path
   BEFORE the guard, and let every consumer read that one value.

2) Streamline.cpp -- ProbeMenuNamesOnce early return.
   `if (!ui || !is) return;` sat BEFORE `done = true`, so a null singleton made
   the probe print nothing at all. A silent instrument cannot be told apart from
   a probe that was never reached. Set done first and report which is null.

3) DX12SwapChain.cpp -- poll before the guard; the guard reads the sample.

Usage:
    python add_xray_v070.py            # dry run (default)
    python add_xray_v070.py --apply    # write
"""

import hashlib
import os
import shutil
import sys
import time

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/src"


def src(*lines):
    """Join source lines that already carry their own trailing newline."""
    return "".join(lines)


TA = "\t\t"                # two tabs
TA3 = "\t\t\t"             # three tabs
TA4 = "\t\t\t\t"           # four tabs

MARKERS = [
    "v0.70: sample the menu state ONCE PER FRAME",
    "v0.70: read the menu state that PollMenuState() already sampled",
    "v0.70: set done FIRST, and say which one is null",
]

REPLACES = [

    # ---------------- Streamline.h : public declarations ------------------
    ("Streamline.h", "H1: declare PollMenuState/MenuIsOpen",
     src(TA + "bool MenuOpenNow();\n"),
     src(TA + "bool MenuOpenNow();\n",
         "\n",
         TA + "// v0.70: sample \"is a game menu up\" once per frame, BEFORE the guard\n"
              + TA + "// that consumes it, and let every consumer read that one sample.\n"
              + TA + "// Returns the sampled state. The old in-CheckFrameConstants placement\n"
              + TA + "// made the guard unverifiable - see PollMenuState() in Streamline.cpp.\n",
         TA + "bool PollMenuState();\n",
         TA + "bool MenuIsOpen() const;\n")),

    # ---------------- Streamline.h : state members -----------------------
    ("Streamline.h", "H2: add menuWasOpen/menuResetPending",
     src(TA + "Diag diag;\n"),
     src(TA + "Diag diag;\n",
         "\n",
         TA + "// v0.70: state, not statistics, so they live outside Diag. menuWasOpen is\n"
              + TA + "// the previous frame's sample; menuResetPending is set when a menu opens\n"
              + TA + "// and consumed by CheckFrameConstants, which may run a frame later (it\n"
              + TA + "// does not run at all while the guard is engaged).\n",
         TA + "bool menuWasOpen = false;\n",
         TA + "bool menuResetPending = false;\n")),

    # ---------------- Streamline.cpp : PollMenuState + MenuIsOpen --------
    ("Streamline.cpp", "C1: PollMenuState + MenuIsOpen",
     src("\tbool Streamline::MenuOpenNow()\n",
         "\t{\n",
         TA + "ProbeMenuNamesOnce();\n",
         TA + "return GameMenuOpenNow();\n",
         "\t}\n"),
     src("\tbool Streamline::MenuOpenNow()\n",
         "\t{\n",
         TA + "ProbeMenuNamesOnce();\n",
         TA + "return GameMenuOpenNow();\n",
         "\t}\n",
         "\n",
         "\t// v0.70: sample the menu state ONCE PER FRAME, before anything consumes it, so\n"
         + "\t// that the guard (DX12SwapChain's menuBlock), the frame counters and the reset\n"
         + "\t// edge all read the same value. The old placement was inside\n"
         + "\t// CheckFrameConstants, which only runs from EvaluateDLSSG - and the guard skips\n"
         + "\t// EvaluateDLSSG. So on every frame the guard engaged, menuOpenNow/menuFrames/\n"
         + "\t// menuEdges stayed frozen and the reset edge could not fire. Evidence: the run\n"
         + "\t// at 2026-09-17 23:07 reported menu=0 world=151, which was read as \"no menu was\n"
         + "\t// ever detected\" when it equally meant \"the counter never ran\".\n",
         "\tbool Streamline::PollMenuState()\n",
         "\t{\n",
         TA + "if (!initialized)\n",
         TA3 + "return false;\n",
         TA + "ProbeMenuNamesOnce();\n",
         TA + "const bool isMenuOpen = GameMenuOpenNow();\n",
         TA + "diag.menuOpenNow = isMenuOpen;\n",
         TA + "// Count each real frame exactly once for the menu/world split. Guarded by\n"
              + TA + "// frameSerial so a second call inside the same frame cannot double-count.\n",
         TA + "if (frameSerial != diag.lastCountedSerial) {\n",
         TA3 + "diag.lastCountedSerial = frameSerial;\n",
         TA3 + "if (isMenuOpen)\n",
         TA4 + "++diag.menuFrames;\n",
         TA3 + "else\n",
         TA4 + "++diag.worldFrames;\n",
         TA + "}\n",
         TA + "if (isMenuOpen != menuWasOpen) {\n",
         TA3 + "++diag.menuEdges;\n",
         TA3 + "// Logged at the moment of the transition, with the multiplier that was\n"
              + TA3 + "// in effect just before it - that pair is what tells whether the menu\n"
              + TA3 + "// handling actually engages.\n",
         TA3 + "SKSE::log::info(\"[XRAY] MENU EDGE open={} serial={} presentedBefore={} "
              + "consts(ok={} fail={})\",\n",
         TA4 + "isMenuOpen ? 1 : 0, frameSerial, diag.presentedPrev,\n",
         TA4 + "diag.constsOk, diag.constsFail);\n",
         TA3 + "if (isMenuOpen)\n",
         TA4 + "menuResetPending = true;   // consumed by CheckFrameConstants\n",
         TA + "}\n",
         TA + "menuWasOpen = isMenuOpen;\n",
         TA + "return isMenuOpen;\n",
         "\t}\n",
         "\n",
         "\t// v0.70: the state PollMenuState() last sampled. Present-path callers use this\n"
         + "\t// instead of re-querying, so the guard and the diagnostics cannot disagree.\n",
         "\tbool Streamline::MenuIsOpen() const\n",
         "\t{\n",
         TA + "return diag.menuOpenNow;\n",
         "\t}\n")),

    # ---------------- Streamline.cpp : CheckFrameConstants ---------------
    ("Streamline.cpp", "C2: CheckFrameConstants consumes the sample",
     src(TA + "const bool isMenuOpen = GameMenuOpenNow();\n",
         TA + "thread_local bool s_wasMenuOpen = false;   // v0.66：共享会让边沿误触发\n",
         TA + "const bool menuEdgeUp = isMenuOpen && !s_wasMenuOpen;\n",
         TA + "const bool menuEdgeDown = !isMenuOpen && s_wasMenuOpen;\n",
         TA + "// v0.64：相机数据断裂与菜单边沿同类 —— 基于旧矩阵建立的重投影历史已经无效，\n",
         TA + "// 丢一次即可（边沿，不是每帧，v0.59 的教训）。\n",
         TA + "thread_local bool s_wasCamValid = true;    // v0.66：同上\n",
         TA + "const bool camEdgeDown = !camValid && s_wasCamValid;\n",
         TA + "s_wasCamValid = camValid;\n",
         TA + "c.reset = (menuEdgeUp || camEdgeDown) ? sl::Boolean::eTrue : sl::Boolean::eFalse;\n",
         TA + "s_wasMenuOpen = isMenuOpen;\n",
         TA + "diag.menuOpenNow = isMenuOpen;\n",
         TA + "if (c.reset == sl::Boolean::eTrue)\n",
         TA3 + "++diag.resetTrue;\n",
         TA + "// Count each real frame exactly once for the menu/world split. Guarded by\n",
         TA + "// frameSerial so a second call inside the same frame cannot double-count.\n",
         TA + "if (frameSerial != diag.lastCountedSerial) {\n",
         TA3 + "diag.lastCountedSerial = frameSerial;\n",
         TA3 + "if (isMenuOpen)\n",
         TA4 + "++diag.menuFrames;\n",
         TA3 + "else\n",
         TA4 + "++diag.worldFrames;\n",
         TA + "}\n",
         TA + "if (menuEdgeUp || menuEdgeDown) {\n",
         TA3 + "++diag.menuEdges;\n",
         TA3 + "// Logged at the moment of the transition, with the multiplier that was in\n",
         TA3 + "// effect just before it - that pair is what tells whether the menu\n",
         TA3 + "// handling actually engages.\n",
         TA3 + "SKSE::log::info(\"[XRAY] MENU EDGE open={} serial={} presentedBefore={} "
              + "reset={} consts(ok={} fail={})\",\n",
         TA4 + "isMenuOpen ? 1 : 0, frameSerial, diag.presentedPrev,\n",
         TA4 + "static_cast<int>(c.reset), diag.constsOk, diag.constsFail);\n",
         TA + "}\n"),
     src(TA + "// v0.70: read the menu state that PollMenuState() already sampled for THIS\n",
         TA + "// frame. It is no longer computed here, because this function only runs from\n",
         TA + "// EvaluateDLSSG - which the menu guard itself skips - so while a menu was\n",
         TA + "// open none of this ran and the guard left no trace to verify.\n",
         TA + "const bool isMenuOpen = diag.menuOpenNow;\n",
         TA + "const bool menuEdgeUp = menuResetPending;\n",
         TA + "menuResetPending = false;\n",
         TA + "// v0.64：相机数据断裂与菜单边沿同类 —— 基于旧矩阵建立的重投影历史已经无效，\n",
         TA + "// 丢一次即可（边沿，不是每帧，v0.59 的教训）。\n",
         TA + "thread_local bool s_wasCamValid = true;    // v0.66：同上\n",
         TA + "const bool camEdgeDown = !camValid && s_wasCamValid;\n",
         TA + "s_wasCamValid = camValid;\n",
         TA + "c.reset = (menuEdgeUp || camEdgeDown) ? sl::Boolean::eTrue : sl::Boolean::eFalse;\n",
         TA + "if (c.reset == sl::Boolean::eTrue)\n",
         TA3 + "++diag.resetTrue;\n")),

    # ---------------- Streamline.cpp : probe -----------------------------
    ("Streamline.cpp", "C3: probe early return",
     src(TA3 + "if (!ui || !is)\n",
         TA4 + "return;\n",
         TA3 + "done = true;\n"),
     src(TA3 + "if (!ui || !is) {\n",
         TA4 + "// v0.70: set done FIRST, and say which one is null. The old order\n"
              + TA4 + "// returned before done = true, so a null singleton made the probe print\n"
              + TA4 + "// nothing at all - indistinguishable from \"never reached\". A silent\n"
              + TA4 + "// instrument is worse than no instrument.\n",
         TA4 + "done = true;\n",
         TA4 + "SKSE::log::warn(\"[XRAY] MENU PROBE unavailable: ui={} istrings={} -> menu \"\n",
         TA4 + "\"detection is limited to whichever path is left; if menuEdges stays 0 \"\n",
         TA4 + "\"then the singletons, not the menu names, are what is broken\",\n",
         TA4 + "static_cast<const void*>(ui), static_cast<const void*>(is));\n",
         TA4 + "return;\n",
         TA3 + "}\n",
         TA3 + "done = true;\n")),

    # ---------------- DX12SwapChain.cpp : poll before the guard ----------
    ("DX12SwapChain.cpp", "D1: poll menu state before the guard",
     src(TA3 + "const bool fgOn = fg.fgActive.load();  // Home 键开关\n",
         TA3 + "bool dlssgOk = false;\n"),
     src(TA3 + "// v0.70: sample the menu state ONCE PER FRAME, here, BEFORE the guard\n"
              + TA3 + "// below consumes it. The guard skips EvaluateDLSSG, and the sample used\n"
              + TA3 + "// to be taken inside EvaluateDLSSG - so on every frame the guard engaged,\n"
              + TA3 + "// menuFrames / menuEdges / the reset edge stayed frozen and the guard was\n"
              + TA3 + "// unverifiable (menu=0 in the heartbeat could not be told apart from\n"
              + TA3 + "// \"the guard never ran\").\n",
         TA3 + "fg.streamline.PollMenuState();\n",
         TA3 + "const bool fgOn = fg.fgActive.load();  // Home 键开关\n",
         TA3 + "bool dlssgOk = false;\n")),

    # ---------------- DX12SwapChain.cpp : guard reads the sample ---------
    ("DX12SwapChain.cpp", "D2: guard reads the sampled state",
     src(TA3 + "const bool menuBlock =\n",
         TA4 + "fgOn && fg.settings.menuDisableFrameGen && fg.streamline.MenuOpenNow();\n"),
     src(TA3 + "const bool menuBlock =\n",
         TA4 + "fgOn && fg.settings.menuDisableFrameGen && fg.streamline.MenuIsOpen();\n")),
]


def read_text(p):
    with open(p, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def write_text(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def brace_delta(s):
    return s.count("{") - s.count("}")


def main():
    apply = "--apply" in sys.argv
    files = sorted({f for f, _, _, _ in REPLACES})
    texts = {f: read_text(os.path.join(SRC, f)) for f in files}

    # ---- EOL adaptation ---------------------------------------------------
    # Streamline.h is CRLF (285 CRLF), the .cpp files are LF. The anchors above
    # are written with bare \n, so convert per file. Verified 2026-09-17: an
    # LF-only anchor silently matches ZERO times in a CRLF file, which is exactly
    # what the first dry run reported.
    eol = {}
    for f in files:
        eol[f] = "\r\n" if "\r\n" in texts[f] else "\n"
        print("%-22s EOL=%s" % (f, "CRLF" if eol[f] == "\r\n" else "LF"))
    ops = []
    for f, label, old, new in REPLACES:
        e = eol[f]
        ops.append((f, label, old.replace("\n", e), new.replace("\n", e)))
    print()

    # ---- guard 1: idempotency markers, checked FIRST ----------------------
    for m in MARKERS:
        for f in files:
            if m in texts[f]:
                print("REFUSED -- %s already contains marker: %s" % (f, m))
                return 1

    # ---- guard 2: every anchor must occur exactly once -------------------
    bad = False
    for f, label, old, new in ops:
        n = texts[f].count(old)
        print("%-22s %-46s anchor x%d" % (f, label, n))
        if n != 1:
            bad = True
    if bad:
        print("REFUSED -- an anchor is missing (0) or ambiguous (>1); nothing written")
        return 1

    # ---- guard 3: braces already balanced --------------------------------
    for f in files:
        if brace_delta(texts[f]) != 0:
            print("REFUSED -- %s: braces already unbalanced" % f)
            return 1

    for f in files:
        s = texts[f]
        before = len(s)
        for ff, label, old, new in ops:
            if ff == f:
                s = s.replace(old, new, 1)
        bd = brace_delta(s)
        if bd != 0:
            print("REFUSED after apply -- %s: brace delta %d" % (f, bd))
            return 1
        texts[f] = s
        print("%-22s %+6d bytes  brace delta %d" % (f, len(s) - before, bd))

    # ---- guard 4: line-split fingerprints (the classic failure) ----------
    # Only real damage signatures. NOTE: "5 tabs + const bool" was tried here and
    # removed - it already occurs once in the untouched DX12SwapChain.cpp, so it
    # is a false positive, not a damage marker.
    for f in files:
        flat = texts[f].replace("\r\n", "\n")
        for fp in ("au\tProbe", "\nto* ui", "Streamline::  "):
            if fp in flat:
                print("REFUSED -- %s: line-split fingerprint %r" % (f, fp))
                return 1

    # ---- guard 5: the v0.69 edits must still be there --------------------
    # v0.70 touches the same two functions v0.69 touched. Assert the v0.69 work
    # survived, instead of assuming it did.
    d12 = texts["DX12SwapChain.cpp"]
    for needle, label in (
            ("v0.69: NR x frame generation are mutually exclusive again.", "v0.69 NR comment"),
            ("const bool fgGeneratingNow =", "v0.69 fgGeneratingNow"),
            ("fg.settings.neuralRenderingEnabled && !fgGeneratingNow", "v0.69 NR gate")):
        if d12.count(needle) != 1:
            print("REFUSED -- DX12SwapChain.cpp: lost %s (x%d)" % (label, d12.count(needle)))
            return 1
    print("v0.69 assertions OK (NR comment / fgGeneratingNow / NR gate each x1)")

    sl = texts["Streamline.cpp"]
    if "auto* ui = RE::UI::GetSingleton();" not in sl:
        print("REFUSED -- Streamline.cpp: lost 'auto* ui = RE::UI::GetSingleton();'")
        return 1
    if sl.count("bool Streamline::PollMenuState()") != 1:
        print("REFUSED -- Streamline.cpp: PollMenuState definition not exactly once")
        return 1
    if sl.count("bool Streamline::MenuIsOpen() const") != 1:
        print("REFUSED -- Streamline.cpp: MenuIsOpen definition not exactly once")
        return 1
    # the old in-function sample must be gone. NOTE: the string
    # "const bool isMenuOpen = GameMenuOpenNow();" legitimately appears ONCE
    # afterwards - inside PollMenuState, which is where the sample moved to - so
    # the check is on the old thread_local edge state, not on that line.
    if sl.count("const bool isMenuOpen = diag.menuOpenNow;") != 1:
        print("REFUSED -- Streamline.cpp: the hoisted read is not in place")
        return 1
    if sl.count("s_wasMenuOpen") != 0:
        print("REFUSED -- Streamline.cpp: the old thread_local menu edge state survived")
        return 1
    if texts["DX12SwapChain.cpp"].count("fg.streamline.PollMenuState();") != 1:
        print("REFUSED -- DX12SwapChain.cpp: PollMenuState call not exactly once")
        return 1

    if not apply:
        print("\nDRY RUN OK - nothing written. Re-run with --apply to write.")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    for f in files:
        bak = os.path.join(SRC, f + ".bak-" + stamp)
        shutil.copy2(os.path.join(SRC, f), bak)
        write_text(os.path.join(SRC, f), texts[f])
        h = hashlib.md5(texts[f].encode("utf-8", "surrogateescape")).hexdigest()
        print("WROTE %-22s md5=%s  backup=%s" % (f, h, os.path.basename(bak)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
