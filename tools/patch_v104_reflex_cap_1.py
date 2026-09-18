#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.04 -- Reflex flip-cap must never be computed from an unconfirmed multiplier.

ROOT CAUSE (proved from the 2026-09-18 19:04 run, not guessed):

  DynamicShaderFrameGen.log:29
      DLSS-G supports up to 2x frame generation (1 interpolated frames per real frame)
  DynamicShaderFrameGen.log:30
      MFG multiplier handed to the external unlocker ... (INI asked for 4x, runtime reports 2x)
  DynamicShaderFrameGen.log:38
      Reflex FLIP cap = 159 fps (6289us) - panel 160Hz, 4 flips per real frame

  At that instant dlssgAcceptedFrames == 0 (the probe latches later -- it ran at
  19:04:38.603 and logged "latched=0"). So Streamline.cpp:1988 fell through the
  `dlssgAcceptedFrames ? ... : s.dlssgFramesToGenerate` ternary and used the INI
  *intent* (DLSSGFramesToGenerate=3 -> mfg=3 -> capMult=4).

  Reflex was therefore told the pipeline emits 4 flips per real frame while
  DLSS-G actually emits 2. The pacer budgets vblank slots for 4 flips, is handed
  2, and waits for a flip-queue slot that never frees. The render thread parks
  inside swapChain->Present(0) -- exactly what the watchdog recorded:
  "stage=d3d11 Wait" frozen while silent climbed to 19792 ms, because m_stage was
  last written at line 1533 (before Present) and is not written again until the
  next Present entry at line 928, which never came.

  "d3d11 Wait" was a red herring: WaitFenceBounded returns immediately
  (fence=2/2). The stall is Present(), and the cap that caused it came from a
  number nobody confirmed.

FIX:
  capMult uses ONLY a runtime-confirmed value. Two sources qualify:
    (a) dlssgAcceptedFrames != 0  -- the probe observed the runtime accept it
    (b) the unlocker owns the multiplier -- the runtime's own reported maximum
        (dlssgMaxFramesToGenerate) is then the truthful figure, NOT the INI request
  When neither is available capMult = 2 (1 real + 1 interpolated), the floor
  every DLSS-G-capable runtime honours. Under-estimating under-throttles and
  costs frames; over-estimating costs the entire session.
"""

import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src", "Streamline.cpp")

OLD_CAP = (
    "\t\t\t\t// v0.79: same correction as the ladder. s comes from\n"
    "\t\t\t\t// Streamline::settings (written by LoadInterposer); the old\n"
    "\t\t\t\t// Get().settings read FrameGen::settings, which is never assigned\n"
    "\t\t\t\t// in this tree and therefore always yielded 1 - so capMult was\n"
    "\t\t\t\t// right only through the accepted-frames branch.\n"
    "\t\t\t\tconst std::uint32_t mfg = dlssgAcceptedFrames\n"
    "\t\t\t\t\t? dlssgAcceptedFrames\n"
    "\t\t\t\t\t: std::max<std::uint32_t>(1u, s.dlssgFramesToGenerate);\n"
    "\t\t\t\tcapMult = std::max<std::uint32_t>(1u, mfg + 1u);"
).replace("\n", "\r\n")

NEW_CAP = (
    "\t\t\t\t// v1.04: capMult must come from a CONFIRMED multiplier only.\n"
    "\t\t\t\t//\n"
    "\t\t\t\t// v0.79 fell back to the INI value when the probe had not latched\n"
    "\t\t\t\t// yet. On the 2026-09-18 19:04 run that fallback produced\n"
    "\t\t\t\t// \"4 flips per real frame\" while line 29 of the same log said the\n"
    "\t\t\t\t// runtime \"supports up to 2x\" -- Reflex then throttled the render\n"
    "\t\t\t\t// side to 159/4 while DLSS-G emitted only 2 flips, the pacer waited\n"
    "\t\t\t\t// for a flip slot that never freed, and the render thread parked\n"
    "\t\t\t\t// inside Present(0) for the whole session (watchdog: 19792 ms\n"
    "\t\t\t\t// silent, with the stage name stale on \"d3d11 Wait\").\n"
    "\t\t\t\t//\n"
    "\t\t\t\t// A number the user asked for in the INI is an INTENT, not a\n"
    "\t\t\t\t// capability. Only two sources count as confirmed:\n"
    "\t\t\t\t//   (a) dlssgAcceptedFrames -- the runtime accepted it, observed;\n"
    "\t\t\t\t//   (b) the unlocker owns the multiplier -- the runtime's own\n"
    "\t\t\t\t//       reported maximum is then the truthful figure.\n"
    "\t\t\t\t// If neither is available, assume the universal floor of 2x\n"
    "\t\t\t\t// (1 real + 1 interpolated).\n"
    "\t\t\t\tstd::uint32_t mfg = 0;\n"
    "\t\t\t\tif (dlssgAcceptedFrames) {\n"
    "\t\t\t\t\tmfg = dlssgAcceptedFrames;\n"
    "\t\t\t\t} else if (mfgUnlockerOwnsMultiplier && dlssgMaxFramesToGenerate > 0) {\n"
    "\t\t\t\t\tmfg = dlssgMaxFramesToGenerate;\n"
    "\t\t\t\t}\n"
    "\t\t\t\tif (mfg == 0) {\n"
    "\t\t\t\t\tmfg = 1;\n"
    "\t\t\t\t\tstatic std::atomic<int> unconfirmedCapLogged{ 0 };\n"
    "\t\t\t\t\tif (unconfirmedCapLogged.fetch_add(1) == 0) {\n"
    "\t\t\t\t\t\tSKSE::log::warn(\"[Streamline] Reflex cap: no confirmed multiplier yet \"\n"
    "\t\t\t\t\t\t\t\"(accepted={} hwMax={} unlocker={} INI asked {}x) - assuming the \"\n"
    "\t\t\t\t\t\t\t\"2x floor so the pacer cannot be told to expect flips that \"\n"
    "\t\t\t\t\t\t\t\"never arrive (v1.04)\",\n"
    "\t\t\t\t\t\t\tdlssgAcceptedFrames, dlssgMaxFramesToGenerate,\n"
    "\t\t\t\t\t\t\tmfgUnlockerOwnsMultiplier ? 1 : 0,\n"
    "\t\t\t\t\t\t\ts.dlssgFramesToGenerate + 1);\n"
    "\t\t\t\t\t}\n"
    "\t\t\t\t}\n"
    "\t\t\t\tcapMult = std::max<std::uint32_t>(1u, mfg + 1u);"
).replace("\n", "\r\n")

OLD_LOG = (
    "\t\t\t\tSKSE::log::info(\"[Streamline] Reflex FLIP cap = {} fps ({}us) - panel {}Hz, {} flips per real frame => ~{} presented fps (real = cap/flips){}\",\n"
    "\t\t\t\t\tcapFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps * capMult,\n"
    "\t\t\t\t\tcapFps ? \"\" : \"  [UNLIMITED - over-submit possible]\");"
).replace("\n", "\r\n")

NEW_LOG = (
    "\t\t\t\tconst bool capConfirmed = (dlssgAcceptedFrames != 0) ||\n"
    "\t\t\t\t\t(mfgUnlockerOwnsMultiplier && dlssgMaxFramesToGenerate > 0);\n"
    "\t\t\t\tSKSE::log::info(\"[Streamline] Reflex FLIP cap = {} fps ({}us) - panel {}Hz, {} flips per real frame => ~{} presented fps (real = cap/flips){}{}\",\n"
    "\t\t\t\t\tcapFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps * capMult,\n"
    "\t\t\t\t\tcapFps ? \"\" : \"  [UNLIMITED - over-submit possible]\",\n"
    "\t\t\t\t\tcapConfirmed ? \"\" : \"  [UNCONFIRMED - using the 2x floor, v1.04]\");"
).replace("\n", "\r\n")

OLD_BANNER = 'SKSE::log::info("[XRAY] diag active v1.03 (compiled " __DATE__ " " __TIME__ ")");'
NEW_BANNER = 'SKSE::log::info("[XRAY] diag active v1.04 (compiled " __DATE__ " " __TIME__ ")");'

EDITS = [
    ("capMult-from-confirmed-multiplier-only", OLD_CAP, NEW_CAP),
    ("log-flag-unconfirmed-cap", OLD_LOG, NEW_LOG),
    ("banner-v1.04", OLD_BANNER, NEW_BANNER),
]


def main():
    apply = "--apply" in sys.argv
    with open(SRC, "r", encoding="utf-8", newline="") as f:
        text = f.read()

    crlf = text.count("\r\n")
    lf = text.count("\n")
    print(f"file      : {os.path.normpath(SRC)}")
    print(f"size      : {len(text)} bytes")
    print(f"lineends  : CRLF={crlf} total_LF={lf} bare_LF={lf - crlf}")
    print(f"mode      : {'APPLY' if apply else 'DRY RUN'}")
    print()

    ok = True
    for label, old, new in EDITS:
        n = text.count(old)
        if n != 1:
            ok = False
        print(f"[{'OK' if n == 1 else 'FAIL'}] {label}: anchor count = {n} (need exactly 1)")
        if n == 1:
            text = text.replace(old, new)

    print()
    if not ok:
        print("REFUSED, nothing written")
        return 1

    for label, _, new in EDITS:
        if text.count(new) != 1:
            print(f"GUARD FAILED after replace: {label} -> new text appears "
                  f"{text.count(new)} times; REFUSED")
            return 1

    if apply:
        with open(SRC, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print(f"WROTE {len(text)} bytes")
    else:
        print(f"would write {len(text)} bytes (dry run, --apply to commit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
