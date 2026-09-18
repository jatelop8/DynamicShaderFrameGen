# -*- coding: utf-8 -*-
"""
v1.01 - align the MFG request with the Transfusion kernel unlocker (4x).

State before this patch (both INIs, source and deployed):
    DLSSGFramesToGenerate=1     (2x)
    MFGMaxFramesOverride=0      (follow the hardware report -> Ada clamps to 2x)

Those values were set at v0.78 for a good reason: DLSSG-Transfusion had been
removed, so there was no Ada kernel for 3x/4x, and asking for 4x came back as
eErrorInvalidState(38). The v0.78 note in the INI says exactly that, and says how
to undo it: "Raise these again only AFTER an unlocker is back and the log shows
runtimeReportsMax = 4x".

Transfusion is now back in place:
    D:/ENB-EJ/Skyrim Special Edition/dinput8.dll   (restored, md5 f6fe4caa...)
and its own log from the last 4x run recorded:
    Initial control: mode=fixed multiplier=4x ... blackwellTransfusion=1
    Applied fixed multiplier: 4x, result=0 (eOk)
    DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
    [PERF] 4x | Kernel: Ada | FPS: 39.6 (25.28ms)
    perf.csv: Multiplier column = 4 for the whole steady stretch

So the precondition the v0.78 note demanded is satisfied.

WHAT THIS PATCH CHANGES (INI only, no code):
    DLSSGFramesToGenerate   1 -> 3   (4x)
    MFGMaxFramesOverride    0 -> 3   (4x ceiling)

WHY IT SHOULD BE SAFE TO ASK FOR 4x NOW
Transfusion is a proxy that intercepts slDLSSGSetOptions itself ("Intercepted
slDLSSGSetOptions for live multiplier control") and applies its own fixed 4x, so
the plugin's request is not the only actor. Aligning the two removes the
request/mismatch that produced eErrorInvalidState in the first place, and makes
runtimeReportsMax agree with what is actually generated.

HOW TO REVERT: set both back to 1 / 0, or run this script's --revert. No rebuild
is needed for an INI change, but the deployed copy must be edited too (the build
step copies the source INI over it, so editing the source is what survives).

Run with --apply to write; without it, dry-run only.
"""
import io
import re
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INIS = [
    os.path.join(ROOT, "SKSE", "Plugins", "DynamicShaderFrameGen.ini"),
    "E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini",
]
APPLY = "--apply" in sys.argv
REVERT = "--revert" in sys.argv

TARGET = ("1", "0") if REVERT else ("3", "3")


def patch(text, nl):
    out = []
    changed = {"dlssg": 0, "mfg": 0}
    for line in text.split("\n"):
        stripped = line.rstrip("\r")
        if not stripped.lstrip().startswith(";"):
            m = re.match(r"^(\s*DLSSGFramesToGenerate\s*=\s*)(\d+)(\s*)$", stripped)
            if m:
                out.append(m.group(1) + TARGET[0] + m.group(3))
                changed["dlssg"] += 1
                continue
            m = re.match(r"^(\s*MFGMaxFramesOverride\s*=\s*)(\d+)(\s*)$", stripped)
            if m:
                out.append(m.group(1) + TARGET[1] + m.group(3))
                changed["mfg"] += 1
                continue
        out.append(line)
    return "\n".join(out), changed


def main():
    ok = True
    for p in INIS:
        if not os.path.exists(p):
            print("  MISSING %s" % p)
            ok = False
            continue
        with io.open(p, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        nl = "\r\n" if "\r\n" in text else "\n"
        out, changed = patch(text, nl)

        cur_d = re.search(r"^DLSSGFramesToGenerate\s*=\s*(\d+)", out, re.M)
        cur_m = re.search(r"^MFGMaxFramesOverride\s*=\s*(\d+)", out, re.M)
        good = (changed["dlssg"] == 1 and changed["mfg"] == 1
                and cur_d and cur_d.group(1) == TARGET[0]
                and cur_m and cur_m.group(1) == TARGET[1])
        print("  %-58s dlssg=%s mfg=%s  %s"
              % (os.path.basename(os.path.dirname(os.path.dirname(p))) + "/" + os.path.basename(p),
                 cur_d.group(1) if cur_d else "?", cur_m.group(1) if cur_m else "?",
                 "OK" if good else "FAIL"))
        if not good:
            ok = False
            continue
        if APPLY:
            with io.open(p, "w", encoding="utf-8", newline="") as f:
                f.write(out)

    if not ok:
        print("REFUSED: post-conditions failed")
        return 1
    if not APPLY:
        print("\nDRY RUN - re-run with --apply (or --apply --revert to go back)")
        return 0
    print("\nAPPLIED: MFG request aligned to %sx" % ("4" if TARGET[0] == "3" else "2"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
