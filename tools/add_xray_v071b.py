#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.71b -- make FocusAllowsPresenting robust against a wrapper/parent window.

Why this exists: the v0.71 version compared the raw handles,

    return ::GetForegroundWindow() == a_hwnd;

which is wrong whenever the swap chain's OutputWindow is a CHILD of a top-level
wrapper (Windows returns the top-level window from GetForegroundWindow, so the
comparison would be false forever). The consequence would not be a small bug:
focusBlock would be true on every frame for the whole session and frame
generation would never run. Compare the ROOT windows instead, and treat "no
foreground window at all" (lock screen, display mode change) as focused so a
transient state cannot silently disable frame generation.

Guards: dry run by default, idempotency marker first, anchor must occur exactly
once, EOL-adaptive, brace balance checked.
"""

import os
import sys
import time

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
T = "\t"

MARKERS = ["v0.71b: compare roots"]

OLD = (T + "static bool FocusAllowsPresenting(HWND a_hwnd)\n"
       + T + "{\n"
       + T + T + "if (!a_hwnd)\n"
       + T + T + T + "return true;\n"
       + T + T + "if (::IsIconic(a_hwnd))\n"
       + T + T + T + "return false;\n"
       + T + T + "return ::GetForegroundWindow() == a_hwnd;\n"
       + T + "}\n")

NEW = (T + "static bool FocusAllowsPresenting(HWND a_hwnd)\n"
       + T + "{\n"
       + T + T + "if (!a_hwnd)\n"
       + T + T + T + "return true;                 // unknown window: do not change behaviour\n"
       + T + T + "if (::IsIconic(a_hwnd))\n"
       + T + T + T + "return false;\n"
       + T + T + "const HWND fg = ::GetForegroundWindow();\n"
       + T + T + "if (!fg)\n"
       + T + T + T + "return true;                 // lock screen / mode change: transient, not a hang\n"
       + T + T + "// v0.71b: compare roots, not handles. If the swap chain window is a child of a\n"
       + T + T + "// wrapper, GetForegroundWindow() never returns it and a raw == would report\n"
       + T + T + "// \"unfocused\" on every frame of the session - i.e. frame generation off.\n"
       + T + T + "const HWND ourRoot = ::GetAncestor(a_hwnd, GA_ROOT);\n"
       + T + T + "const HWND fgRoot = ::GetAncestor(fg, GA_ROOT);\n"
       + T + T + "if (ourRoot && fgRoot)\n"
       + T + T + T + "return ourRoot == fgRoot;\n"
       + T + T + "return fg == a_hwnd;\n"
       + T + "}\n")

FILES = ["DX12SwapChain.cpp"]


def read_text(p):
    with open(p, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def write_text(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def main():
    apply_it = "--apply" in sys.argv
    texts = {f: read_text(os.path.join(SRC, f)) for f in FILES}

    for m in MARKERS:
        for f in FILES:
            if m in texts[f]:
                print("REFUSED -- %s already contains marker: %s" % (f, m))
                return 1

    f = "DX12SwapChain.cpp"
    eff = OLD
    n = texts[f].count(eff)
    if n != 1:
        alt = eff.replace("\n", "\r\n")
        if texts[f].count(alt) == 1:
            eff, n = alt, 1
    print("%-20s %-42s anchor x%d" % (f, "focus root comparison", n))
    if n != 1:
        print("REFUSED -- anchor missing or ambiguous; nothing written")
        return 1

    if texts[f].count("{") - texts[f].count("}") != 0:
        print("REFUSED -- braces already unbalanced")
        return 1

    eol = "\r\n" if "\r\n" in texts[f] else "\n"
    new_eff = NEW if eol == "\n" else NEW.replace("\n", "\r\n")
    s = texts[f].replace(eff, new_eff, 1)
    bd = s.count("{") - s.count("}")
    if bd != 0:
        print("REFUSED -- brace delta %d after apply" % bd)
        return 1
    print("%-20s %+6d bytes   brace delta %d" % (f, len(s) - len(texts[f]), bd))

    # the rest of v0.71 must still be intact
    for needle in ("const bool focusBlock = !winFocused;",
                   "const HRESULT hrPresent = swapChain->Present(0,",
                   "DXGI_PRESENT_DO_NOT_WAIT"):
        assert s.count(needle) >= 1, "lost v0.71 piece: " + needle

    if not apply_it:
        print("\nDRY RUN -- nothing written. Re-run with --apply")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    p = os.path.join(SRC, f)
    with open(p + ".bak-" + stamp, "w", encoding="utf-8", errors="surrogateescape", newline="") as b:
        b.write(texts[f])
    write_text(p, s)
    print("wrote %s (backup .bak-%s)" % (f, stamp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
