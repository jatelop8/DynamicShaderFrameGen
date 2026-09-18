#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.71c -- take the focus window from the swap chain, not from the desc.

Build error this fixes (DX12SwapChain.cpp:707):

    error C2039: "OutputWindow": 不是 "DXGI_SWAP_CHAIN_DESC1" 的成员

DX12SwapChain's member is a DXGI_SWAP_CHAIN_DESC1 (v0.3 switched to
CreateSwapChainForHwnd), and DESC1 has no OutputWindow - only the older
DXGI_SWAP_CHAIN_DESC does. IDXGISwapChain1::GetHwnd() is the correct source and
follows the swap chain if the game ever recreates it against another window.
Null is safe: FocusAllowsPresenting() leaves behaviour unchanged when it has no
window to judge.
"""

import os
import sys
import time

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
T = "\t"

MARKERS = ["v0.71c: GetHwnd"]

OLD = (T + T + "const bool winFocused = FocusAllowsPresenting(swapChainDesc.OutputWindow);\n"
       + T + T + "g_lastFocus.store(winFocused ? 1 : 0);\n"
       + T + T + "{\n"
       + T + T + T + "static bool focusWasOn = true;\n"
       + T + T + T + "if (winFocused != focusWasOn) {\n"
       + T + T + T + T + "focusWasOn = winFocused;\n"
       + T + T + T + T + "SKSE::log::warn(\"[XRAY] FOCUS {} hwnd={} foreground={} iconic={} - frame \"\n"
       + T + T + T + T + T + "\"generation is bypassed and Present runs with DO_NOT_WAIT while the window \"\n"
       + T + T + T + T + T + "\"cannot be shown\", winFocused ? \"regained\" : \"lost\",\n"
       + T + T + T + T + T + "static_cast<const void*>(swapChainDesc.OutputWindow),\n"
       + T + T + T + T + T + "static_cast<const void*>(::GetForegroundWindow()),\n"
       + T + T + T + T + T + "swapChainDesc.OutputWindow ? static_cast<int>(::IsIconic(swapChainDesc.OutputWindow)) : -1);\n"
       + T + T + T + "}\n"
       + T + T + "}\n")

NEW = (T + T + "// v0.71c: IDXGISwapChain1::GetHwnd() is the window this swap chain actually\n"
       + T + T + "// presents to. swapChainDesc is a DESC1 here and has no OutputWindow member\n"
       + T + T + "// (using it cost one build: C2039). Null is safe - FocusAllowsPresenting\n"
       + T + T + "// leaves the old behaviour alone when it has no window to judge.\n"
       + T + T + "const HWND winHwnd = swapChain ? swapChain->GetHwnd() : nullptr;\n"
       + T + T + "const bool winFocused = FocusAllowsPresenting(winHwnd);\n"
       + T + T + "g_lastFocus.store(winFocused ? 1 : 0);\n"
       + T + T + "{\n"
       + T + T + T + "static bool focusWasOn = true;\n"
       + T + T + T + "if (winFocused != focusWasOn) {\n"
       + T + T + T + T + "focusWasOn = winFocused;\n"
       + T + T + T + T + "SKSE::log::warn(\"[XRAY] FOCUS {} hwnd={} foreground={} iconic={} - frame \"\n"
       + T + T + T + T + T + "\"generation is bypassed and Present runs with DO_NOT_WAIT while the window \"\n"
       + T + T + T + T + T + "\"cannot be shown\", winFocused ? \"regained\" : \"lost\",\n"
       + T + T + T + T + T + "static_cast<const void*>(winHwnd),\n"
       + T + T + T + T + T + "static_cast<const void*>(::GetForegroundWindow()),\n"
       + T + T + T + T + T + "winHwnd ? static_cast<int>(::IsIconic(winHwnd)) : -1);\n"
       + T + T + T + "}\n"
       + T + T + "}\n")

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
    eff, n = OLD, texts[f].count(OLD)
    if n != 1:
        alt = OLD.replace("\n", "\r\n")
        if texts[f].count(alt) == 1:
            eff, n = alt, 1
    print("%-20s %-42s anchor x%d" % (f, "focus sample uses GetHwnd", n))
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

    # The desc must no longer be consulted for a window handle, and v0.71 must
    # survive. NOTE: test the exact call, not the bare substring - the FFX path
    # legitimately contains "a_swapChainDesc.OutputWindow", which also matches
    # "swapChainDesc.OutputWindow" and turned a correct patch into a false refusal.
    if "FocusAllowsPresenting(swapChainDesc" in s or "IsIconic(swapChainDesc" in s:
        print("REFUSED -- the focus sample still reads the swap chain desc")
        return 1
    if s.count("const HWND winHwnd = swapChain ? swapChain->GetHwnd() : nullptr;") != 1:
        print("REFUSED -- GetHwnd line not present exactly once")
        return 1
    for needle in ("const bool focusBlock = !winFocused;",
                   "const HRESULT hrPresent = swapChain->Present(0,",
                   "const HRESULT hrPresentFsr = swapChain->Present(1,",
                   "return ourRoot == fgRoot;"):
        assert s.count(needle) == 1, "lost earlier piece: " + needle

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
