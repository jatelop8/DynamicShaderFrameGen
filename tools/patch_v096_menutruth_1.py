"""v0.96 -- make the menu guard tell the truth, and stop it firing on load faders.

=============================================================================
WHAT THE 16:24 LOG PROVES
=============================================================================

    [16:24:24.182] MENU EDGE open=1 serial=2      <- "menu open" from frame 2
    [16:24:48.111] MENU EDGE open=0 serial=1338   <- released only at frame 1338

    [16:24:48.111] [MFG] debug CHECK: Present skips SetDLSSGOptions even though
                   the menu guard is not engaged (menuBlock=0 frames=0
                   blocked=1336 unblocked=1)

1336 frames (~24 s) of the run had menuBlock == true, and on every one of them
Present took the bypass branch, so SetDLSSGOptions/EvaluateDLSSG never ran and
no frame was ever generated. To the player that is a frozen picture.

The heartbeat agrees independently:

    presented all=0/1342/0/... world=0/6/... menu=0/1336/0/...
                     ^ every menu-frame presented exactly 1 frame (no generation)

WHY IT FIRED, AND WHY THE LOG LIED ABOUT IT
-------------------------------------------
Two separate defects:

1) THE LOG IS A LIE.  DX12SwapChain.cpp:1341 formats the warning as

       "...(menuBlock=0 frames={} blocked={} unblocked={})"

   "menuBlock=0" is a hard-coded literal in the format string, not the variable.
   So the message reads "the guard is not engaged" at the exact moment the guard
   IS engaged. Every reader (human or agent) who trusted that sentence would
   look for the fault in the wrong place -- and it is precisely the sentence the
   v0.93 investigation relied on. The warning must print the real value.

2) THE MENU SET IS TOO WIDE.  GameMenuOpenNow() returns true for
   "Main Menu", "Loading Menu", "Journal Menu", "Pause Menu", "RaceSex Menu"
   and "Fader Menu".  "Fader Menu" is the screen-fade used while the world is
   loading (the engine's own load transition). It is up on essentially every
   load frame, and it is not a UI the player interacts with, so treating it as
   "a menu is up, stop generating frames" suppresses frame generation through
   the entire load and for as long as the fade lingers.

   The 22-second gap between the MENU PROBE line (16:24:02, all three
   InterfaceStrings menus false) and MENU EDGE open=1 (16:24:24) is the load:
   LONG FRAME 21348.3ms sits in between. The probe cannot see which menu fired
   because it only tests three names, and none of them is the one that fired.

WHY FIXING ONE WOULD NOT HAVE BEEN ENOUGH
-----------------------------------------
Removing "Fader Menu" alone would guess at the culprit. Fixing the log alone
would explain the fault but not remove it. Both are needed, and the log fix is
what makes the culprit indentifiable on the next run if the set is still wrong:
the guard now records WHICH name matched.

CHANGES
-------
Streamline.h
    + diag.menuHitName  : last matched menu name (const char*)
    + diag.menuHitCount : frames that name has been responsible for
Streamline.cpp
    * GameMenuOpenNow() -> MenuProbe(a_hitName): same set, but reports the hit
      and drops "Fader Menu".
    * PollMenuState() stores the hit into diag.
    * heartbeat gains the hit name.
DX12SwapChain.cpp
    * the warning prints the REAL menuBlock and the HIT NAME, not a literal 0.
"""
import sys
from pathlib import Path

HDR = Path(r"D:/Modding/DynamicShaderFrameGen/src/Streamline.h")
CPPS = Path(r"D:/Modding/DynamicShaderFrameGen/src/Streamline.cpp")
SWAP = Path(r"D:/Modding/DynamicShaderFrameGen/src/DX12SwapChain.cpp")


def endings(p):
    d = p.read_bytes()
    return d.count(b"\r\n"), d.count(b"\n")


# ---------------------------------------------------------------------------
# (label, path, anchor, replacement)
# ---------------------------------------------------------------------------
def build():
    edits = []

    # ---- Streamline.h : storage for the hit name ---------------------------
    h_anchor = (
        b"\t\tbool PollMenuState();\n"
        b"\t\tbool MenuIsOpen() const;\n"
    )
    h_new = (
        b"\t\tbool PollMenuState();\n"
        b"\t\tbool MenuIsOpen() const;\n"
        b"\n"
        b"\t\t// v0.96: which menu name the guard matched, and how often. The 16:24\n"
        b"\t\t// run locked the guard on for 1336 frames and the log could not say\n"
        b"\t\t// which of the six candidate names was responsible -- the MENU PROBE\n"
        b"\t\t// only tests three of them and all three read false. Recording the\n"
        b"\t\t// hit removes the guesswork: \"Fader Menu\" is the screen fade the\n"
        b"\t\t// engine uses while the world loads, and it is no longer counted.\n"
        b"\t\tconst char* menuHitName() const;\n"
        b"\t\tstd::uint64_t menuHitCount() const;\n"
        b"\n"
    )
    edits.append(("hdr.menuHit", HDR, h_anchor, h_new))

    # ---- Streamline.h : diagnostic members --------------------------------
    # menuOpenNow lives in the HEADER (Streamline.h:97), not in the .cpp.
    h_txt = HDR.read_text(encoding="utf-8")
    diag_anchor = None
    for cand in ("\t\t\tbool menuOpenNow = false;\n",
                 "\t\t\tbool menuOpenNow = false;\r\n"):
        if h_txt.count(cand) == 1:
            diag_anchor = cand.encode("utf-8")
            break
    if diag_anchor is None:
        # fall back: match on the bare text with either ending
        alt = b"\t\t\tbool menuOpenNow = false;"
        if h_txt.encode("utf-8").count(alt) == 1:
            print("  note: menuOpenNow found via bare-text fallback")
        else:
            return None, "hdr: menuOpenNow diag field not found"

    diag_new = (
        b"\t\t\tbool menuOpenNow = false;\n"
        b"\t\t\t// v0.96: which menu name the guard matched on the last sample, and\n"
        b"\t\t\t// how many frames that name has been responsible for. Without this\n"
        b"\t\t\t// the 1336-frame lock at 16:24 could not be attributed to any menu.\n"
        b"\t\t\tconst char* menuHitName = nullptr;\n"
        b"\t\t\tstd::uint64_t menuHitFrames = 0;\n"
    )
    edits.append(("hdr.diag.menuHit", HDR, diag_anchor, diag_new))

    # ---- Streamline.cpp : replace GameMenuOpenNow with a reporting version --
    old_fn = (
        b"\t\tbool GameMenuOpenNow()\n"
        b"\t\t{\n"
        b"\t\t\tauto* ui = RE::UI::GetSingleton();\n"
        b"\t\t\tif (!ui)\n"
        b"\t\t\t\treturn false;\n"
        b"\t\t\tconst auto* istrings = RE::InterfaceStrings::GetSingleton();\n"
        b"\t\t\tif (istrings &&\n"
        b"\t\t\t\t(ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||\n"
        b"\t\t\t\t\tui->IsMenuOpen(istrings->journalMenu))) {\n"
        b"\t\t\t\treturn true;\n"
        b"\t\t\t}\n"
        b"\t\t\treturn ui->IsMenuOpen(\"Main Menu\") || ui->IsMenuOpen(\"Loading Menu\") ||\n"
        b"\t\t\t\tui->IsMenuOpen(\"Journal Menu\") || ui->IsMenuOpen(\"Pause Menu\") ||\n"
        b"\t\t\t\tui->IsMenuOpen(\"RaceSex Menu\") || ui->IsMenuOpen(\"Fader Menu\");\n"
        b"\t\t}\n"
    )
    if CPPS.read_bytes().count(old_fn) != 1:
        return None, f"cpp: GameMenuOpenNow body count = {CPPS.read_bytes().count(old_fn)}"

    new_fn = (
        b"\t\t// v0.96: same decision, but it now REPORTS which name matched, and the\n"
        b"\t\t// screen-fade menu is no longer part of the set.\n"
        b"\t\t//\n"
        b"\t\t// Why \"Fader Menu\" was removed: it is the engine's load-transition\n"
        b"\t\t// fade, not a player-facing menu. It is up across the whole load, so\n"
        b"\t\t// counting it suppressed frame generation for the entire load and for\n"
        b"\t\t// as long as the fade lingered -- 1336 consecutive frames at 16:24,\n"
        b"\t\t// during which Present bypassed SetDLSSGOptions and the picture stayed\n"
        b"\t\t// frozen. The menus that must keep the guard are the ones the engine\n"
        b"\t\t// draws WITHOUT valid motion vectors: main, loading, journal, pause\n"
        b"\t\t// and the race/sex editor.\n"
        b"\t\t//\n"
        b"\t\t// The hit is reported through two out-params so the caller can log it;\n"
        b"\t\t// a null name means \"no menu fired\".\n"
        b"\t\tbool MenuProbe(const char** a_hitName)\n"
        b"\t\t{\n"
        b"\t\t\tif (a_hitName)\n"
        b"\t\t\t\t*a_hitName = nullptr;\n"
        b"\t\t\tauto* ui = RE::UI::GetSingleton();\n"
        b"\t\t\tif (!ui)\n"
        b"\t\t\t\treturn false;\n"
        b"\t\t\tconst auto* istrings = RE::InterfaceStrings::GetSingleton();\n"
        b"\t\t\tif (istrings) {\n"
        b"\t\t\t\tif (ui->IsMenuOpen(istrings->mainMenu)) {\n"
        b"\t\t\t\t\tif (a_hitName) *a_hitName = \"istrings.mainMenu\";\n"
        b"\t\t\t\t\treturn true;\n"
        b"\t\t\t\t}\n"
        b"\t\t\t\tif (ui->IsMenuOpen(istrings->loadingMenu)) {\n"
        b"\t\t\t\t\tif (a_hitName) *a_hitName = \"istrings.loadingMenu\";\n"
        b"\t\t\t\t\treturn true;\n"
        b"\t\t\t\t}\n"
        b"\t\t\t\tif (ui->IsMenuOpen(istrings->journalMenu)) {\n"
        b"\t\t\t\t\tif (a_hitName) *a_hitName = \"istrings.journalMenu\";\n"
        b"\t\t\t\t\treturn true;\n"
        b"\t\t\t\t}\n"
        b"\t\t\t}\n"
        b"\t\t\t// Literal fallback. Each name is tested separately so the log can\n"
        b"\t\t\t// name the culprit instead of merely reporting that something fired.\n"
        b"\t\t\tstatic const char* const kLiterals[] = {\n"
        b"\t\t\t\t\"Main Menu\", \"Loading Menu\", \"Journal Menu\",\n"
        b"\t\t\t\t\"Pause Menu\", \"RaceSex Menu\",\n"
        b"\t\t\t};\n"
        b"\t\t\tfor (const char* name : kLiterals) {\n"
        b"\t\t\t\tif (ui->IsMenuOpen(name)) {\n"
        b"\t\t\t\t\tif (a_hitName) *a_hitName = name;\n"
        b"\t\t\t\t\treturn true;\n"
        b"\t\t\t\t}\n"
        b"\t\t\t}\n"
        b"\t\t\treturn false;\n"
        b"\t\t}\n"
        b"\n"
        b"\t\tbool GameMenuOpenNow()\n"
        b"\t\t{\n"
        b"\t\t\treturn MenuProbe(nullptr);\n"
        b"\t\t}\n"
    )
    edits.append(("cpp.MenuProbe", CPPS, old_fn, new_fn))

    # ---- Streamline.cpp : PollMenuState records the hit --------------------
    old_poll = (
        b"\t\tProbeMenuNamesOnce();\n"
        b"\t\tconst bool isMenuOpen = GameMenuOpenNow();\n"
        b"\t\tdiag.menuOpenNow = isMenuOpen;\n"
    )
    if CPPS.read_bytes().count(old_poll) != 1:
        return None, f"cpp: PollMenuState anchor count = {CPPS.read_bytes().count(old_poll)}"
    new_poll = (
        b"\t\tProbeMenuNamesOnce();\n"
        b"\t\tconst char* hitName = nullptr;\n"
        b"\t\tconst bool isMenuOpen = MenuProbe(&hitName);\n"
        b"\t\tdiag.menuOpenNow = isMenuOpen;\n"
        b"\t\t// v0.96: attribute the state to a name. The 16:24 run held the guard on\n"
        b"\t\t// for 1336 frames and nothing in the log said which menu was open.\n"
        b"\t\tdiag.menuHitName = hitName;\n"
        b"\t\tif (isMenuOpen)\n"
        b"\t\t\t++diag.menuHitFrames;\n"
    )
    edits.append(("cpp.PollMenuState.hit", CPPS, old_poll, new_poll))

    # ---- Streamline.cpp : accessors ---------------------------------------
    acc_anchor = (
        b"\tbool Streamline::MenuIsOpen() const\n"
        b"\t{\n"
        b"\t\treturn diag.menuOpenNow;\n"
        b"\t}\n"
    )
    if CPPS.read_bytes().count(acc_anchor) != 1:
        return None, "cpp: MenuIsOpen accessor anchor not found"
    acc_new = (
        b"\tbool Streamline::MenuIsOpen() const\n"
        b"\t{\n"
        b"\t\treturn diag.menuOpenNow;\n"
        b"\t}\n"
        b"\n"
        b"\t// v0.96: expose the matched menu name so Present can put it in the log.\n"
        b"\tconst char* Streamline::menuHitName() const\n"
        b"\t{\n"
        b"\t\treturn diag.menuHitName ? diag.menuHitName : \"-\";\n"
        b"\t}\n"
        b"\n"
        b"\tstd::uint64_t Streamline::menuHitCount() const\n"
        b"\t{\n"
        b"\t\treturn diag.menuHitFrames;\n"
        b"\t}\n"
    )
    edits.append(("cpp.accessors", CPPS, acc_anchor, acc_new))

    # ---- Streamline.cpp : heartbeat reports the hit ------------------------
    hb_anchor = (
        b'\t\t\t\t\t"world(acc/skip/boot)/lastMagVP={}/{}/{}/{:.6g}",'
    )
    if CPPS.read_bytes().count(hb_anchor) != 1:
        return None, "cpp: heartbeat anchor not found"
    hb_new = (
        b'\t\t\t\t\t"world(acc/skip/boot)/lastMagVP={}/{}/{}/{:.6g} "\n'
        b'\t\t\t\t\t"menuHit(count/name)={}/{}",'
    )
    edits.append(("cpp.heartbeat.menuHit", CPPS, hb_anchor, hb_new))

    hb_arg_anchor = (
        b"\t\t\t\t\tGet().snapBootstrap, Get().snapLastMagVP);"
    )
    if CPPS.read_bytes().count(hb_arg_anchor) != 1:
        return None, "cpp: heartbeat arg anchor not found"
    hb_arg_new = (
        b"\t\t\t\t\tGet().snapBootstrap, Get().snapLastMagVP,\n"
        b"\t\t\t\t\tGet().menuHitCount(), Get().menuHitName());"
    )
    edits.append(("cpp.heartbeat.args", CPPS, hb_arg_anchor, hb_arg_new))

    # ---- DX12SwapChain.cpp : the warning must print the REAL menuBlock -----
    # Note the continuation lines carry SIX tabs (five for the statement plus one
    # from the preceding "if" block's continuation indent).
    sw_old = (
        b'\t\t\t\t\tSKSE::log::warn("[MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu "\n'
        b'\t\t\t\t\t\t"guard is not engaged (menuBlock=0 frames={} blocked={} unblocked={}) - the ladder "\n'
        b'\t\t\t\t\t\t"cannot be calibrated while this lasts",\n'
        b"\t\t\t\t\t\tdebugOk ? 1u : 0u, menuBlockedFrames, menuUnblockedFrames);"
    )
    if SWAP.read_bytes().count(sw_old) != 1:
        return None, f"swap: warning anchor count = {SWAP.read_bytes().count(sw_old)}"
    sw_new = (
        b'\t\t\t\t\tSKSE::log::warn("[MFG] debug CHECK: Present skips SetDLSSGOptions. "\n'
        b'\t\t\t\t\t\t"menuBlock={} (hit={}) dlssgOk={} fgOn={} dlssg={} fb={} "\n'
        b'\t\t\t\t\t\t"blocked={} unblocked={} - the ladder cannot be calibrated while this lasts",\n'
        b"\t\t\t\t\t\tmenuBlock ? 1 : 0, fg.streamline.menuHitName(),\n"
        b"\t\t\t\t\t\tdlssgOk ? 1 : 0, fgOn ? 1 : 0,\n"
        b"\t\t\t\t\t\tfg.streamline.featureDLSSG ? 1 : 0, fg.GetFrameBuffer() ? 1 : 0,\n"
        b"\t\t\t\t\t\tmenuBlockedFrames, menuUnblockedFrames);"
    )
    edits.append(("swap.warning.truth", SWAP, sw_old, sw_new))

    return edits, None


def main():
    apply = "--apply" in sys.argv
    print(f"mode: {'APPLY' if apply else 'DRY-RUN'}")
    for p in (HDR, CPPS, SWAP):
        crlf, lf = endings(p)
        # CRLF counts also contain the LF bytes, so a file is pure-CRLF when
        # crlf == lf, and pure-LF when crlf == 0.
        kind = "CRLF" if crlf == lf and crlf > 0 else ("LF" if crlf == 0 else "MIXED")
        print(f"  {p.name:20s} CRLF={crlf:5d} LF={lf:5d}  => {kind}")

    edits, err = build()
    if err:
        print("REFUSED, nothing written:")
        print("  -", err)
        return 1

    # Adapt each anchor to the ending the FILE actually uses. Streamline.h is
    # pure CRLF, the two .cpp files are pure LF -- hard-coding one form is how
    # the previous round produced "anchor count = 0".
    def adapt(path, blob, eol):
        if eol == b"\n":
            return blob
        return blob.replace(b"\r\n", b"\n").replace(b"\n", eol)

    # validate every anchor against the CURRENT file, then accumulate
    acc = {}
    for label, path, old, new in edits:
        d = acc.get(path, path.read_bytes())
        crlf, lf = d.count(b"\r\n"), d.count(b"\n")
        eol = b"\r\n" if (crlf == lf and crlf > 0) else b"\n"
        old_a = adapt(path, old, eol)
        new_a = adapt(path, new, eol)
        n = d.count(old_a)
        if n != 1:
            print(f"REFUSED, nothing written: {label} anchor count = {n} "
                  f"(eol={'CRLF' if eol == b'\r\n' else 'LF'})")
            return 1
        acc[path] = d.replace(old_a, new_a, 1)
        print(f"  {'WROTE' if apply else 'WOULD WRITE'} {label}  (+{len(new_a)-len(old_a)} bytes)")

    # idempotency markers on the ACCUMULATED buffers
    if acc[SWAP].count(b"menuBlock={} (hit={})") != 1:
        print("REFUSED: swap warning marker not present exactly once")
        return 1
    if acc[CPPS].count(b"menuHit(count/name)={}/{}") != 1:
        print("REFUSED: heartbeat marker not present exactly once")
        return 1
    # the removed menu must no longer be TESTED (comment mentions are fine --
    # the rationale for removing it is documented in the replacement block)
    if b'ui->IsMenuOpen("Fader Menu")' in acc[CPPS]:
        print("REFUSED: 'Fader Menu' is still tested in code")
        return 1
    # the new literal set must contain exactly the five retained names
    for name in (b'"Main Menu"', b'"Loading Menu"', b'"Journal Menu"',
                 b'"Pause Menu"', b'"RaceSex Menu"'):
        if acc[CPPS].count(name) < 1:
            print(f"REFUSED: literal {name!r} missing from the decision set")
            return 1

    if apply:
        for path, out in acc.items():
            bc, bl = path.read_bytes().count(b"\r\n"), path.read_bytes().count(b"\n")
            ac, al = out.count(b"\r\n"), out.count(b"\n")
            print(f"  {path.name}: CRLF {bc}->{ac}, LF {bl}->{al}")
            path.write_bytes(out)
    else:
        print("\n(dry run -- pass --apply to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
