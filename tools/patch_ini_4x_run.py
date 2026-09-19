#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_ini_4x_run.py - switch the deployed INI back to the DLSSG multi-frame path
for ONE diagnostic run, with DLSS5 kept alive alongside it.

Why three keys and not one:
  Provider=1            -> dlssgMode = true, i.e. the only path that can do 3x/4x
  MFGMaxFramesOverride=3-> raise the request ceiling to 4x (Transfusion is present
                           and already forces multiplier=4x)
  NRAllowWithFrameGen=1 -> REQUIRED, not optional. In DX12SwapChain.cpp:1161,
                           fgGeneratingNow = dlssgMode && frameGeneration && fgActive.
                           With Provider=1 that is true, so the default (0) would
                           SUPPRESS DLSS5. Today DLSS5 only ran because the FSR3
                           path leaves dlssgMode==false. Flipping Provider alone
                           would trade "frozen" for "frozen and no DLSS5".

Not touched on purpose (each would add a variable to the run):
  DLSSGFramesToGenerate stays 3 (=4x request), NRRenderScale stays 1.00,
  NRIntensity / NRLocalTone / ... untouched.

Usage:
  python patch_ini_4x_run.py            # dry run, writes nothing
  python patch_ini_4x_run.py --apply    # write
"""
import sys
import os
import hashlib

INI = r"E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini"

# (label, old, new) - anchors are FULL LINES including their CRLF, so neither the
# transform nor the check can be fooled by the same string appearing inside a
# comment. That is not hypothetical: the v1.05 comment block at line 95 contains
# "MFGMaxFramesOverride=3 could not reach 4x by construction", so a bare substring
# count returns 2 and the post-condition fails. Line-anchored counts return 1.
NL = "\r\n"
EDITS = [
    ("provider",            "Provider=0",             "Provider=1"),
    ("mfg_ceiling",         "MFGMaxFramesOverride=0", "MFGMaxFramesOverride=3"),
    ("nr_chain_with_dlssg", "NRAllowWithFrameGen=0",  "NRAllowWithFrameGen=1"),
]
EDITS = [(lbl, NL + o + NL, NL + n + NL) for lbl, o, n in EDITS]

# Post-conditions are checked on the RESULT text, not on the input.
POST = [
    ("Provider=1",             1),
    ("MFGMaxFramesOverride=3", 1),
    ("NRAllowWithFrameGen=1",  1),
    ("Provider=0",             0),
    ("MFGMaxFramesOverride=0", 0),
    ("NRAllowWithFrameGen=0",  0),
]
POST = [(NL + k + NL, v) for k, v in POST]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(INI):
        print("REFUSED: INI not found: %s" % INI)
        return 2

    raw = open(INI, "rb").read()
    eol = ("CRLF=%d LF=%d bare_lf=%d"
           % (raw.count(b"\r\n"), raw.count(b"\n"),
              raw.count(b"\n") - raw.count(b"\r\n")))
    text = raw.decode("utf-8")

    print("file      : %s" % INI)
    print("before    : %d bytes  md5=%s  %s"
          % (len(raw), hashlib.md5(raw).hexdigest(), eol))
    print("mode      : %s" % ("APPLY" if apply else "DRY RUN (nothing written)"))

    # ---- assertion phase: every anchor must occur exactly once ----
    ok = True
    for label, old, new in EDITS:
        n = text.count(old)
        flag = "OK " if n == 1 else "BAD"
        print("  [%s] %-20s count(%s) = %d" % (flag, label, old, n))
        if n != 1:
            ok = False
    if not ok:
        print("REFUSED, nothing written")
        return 1

    # ---- transform ----
    out = text
    for label, old, new in EDITS:
        out = out.replace(old, new)

    # ---- post-condition phase: check the RESULT ----
    ok = True
    for needle, want in POST:
        n = out.count(needle)
        flag = "OK " if n == want else "BAD"
        print("  post [%s] count(%s) = %d (want %d)" % (flag, needle, n, want))
        if n != want:
            ok = False
    if not ok:
        print("REFUSED, nothing written")
        return 1

    # line count and EOL must be untouched
    if out.count("\n") != text.count("\n"):
        print("REFUSED: line count changed (%d -> %d)"
              % (text.count("\n"), out.count("\n")))
        return 1
    if out.count("\r\n") != text.count("\r\n"):
        print("REFUSED: CRLF count changed (%d -> %d)"
              % (text.count("\r\n"), out.count("\r\n")))
        return 1

    nb = out.encode("utf-8")
    print("after     : %d bytes  md5=%s  (delta %+d)"
          % (len(nb), hashlib.md5(nb).hexdigest(), len(nb) - len(raw)))
    print("lines     : %d  CRLF=%d  (unchanged)"
          % (out.count("\n"), out.count("\r\n")))

    if not apply:
        print("DRY RUN done - nothing written. Re-run with --apply to write.")
        return 0

    open(INI, "wb").write(nb)
    back = open(INI, "rb").read()
    print("readback  : %d bytes  md5=%s  %s"
          % (len(back), hashlib.md5(back).hexdigest(),
             "MATCH" if back == nb else "MISMATCH"))
    return 0 if back == nb else 3


if __name__ == "__main__":
    sys.exit(main())
