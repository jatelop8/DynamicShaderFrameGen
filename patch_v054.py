#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.54 patch: derive the Reflex render frame rate cap from the monitor refresh rate
and the frame-generation multiplier instead of hardcoding 1000000/60.

Why: with a 2560x1440 @ 160Hz panel and 4x, the hardcoded 60fps render cap made
DLSSG present 57.4 x 4 = 229.6 fps at a 160Hz panel -> 43% over-submission ->
present queue backs up -> SL pacer rhythm breaks -> continuous flicker.

Assertion policy (same as every other patch in this repo):
  * every (old -> new) pair must match EXACTLY ONCE  (0 = stale anchor, >1 = ambiguous)
  * a marker string guards against a re-run inserting a second copy
  * dry run by default; pass --apply to write
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

H = "src/FrameGen.h"
CPP = "src/FrameGen.cpp"
SL = "src/Streamline.cpp"
GUI = "src/ImguiMenu.cpp"
INI = "SKSE/Plugins/DynamicShaderFrameGen.ini"
RC = "src/version.rc"
LOG = "CHANGELOG.md"

# ---------------------------------------------------------------- FrameGen.h
H_OLD = (
    "\t\tstd::uint32_t mfgMaxFramesOverride = 0;  // INI MFGMaxFramesOverride\n"
    "\t\tint  presetDLSS = 0;           // DLSS 模型预设：0=Auto 1=J 2=K 3=L 4=M\n"
)
H_NEW = (
    "\t\tstd::uint32_t mfgMaxFramesOverride = 0;  // INI MFGMaxFramesOverride\n"
    "\t\t// v0.54：Reflex 渲染帧率上限（0 = 自动：显示器刷新率 / 帧生成总倍数 - 1）。\n"
    "\t\t// DLSSG 多倍帧生成时 present 帧率 = 渲染帧率 x 倍数，一旦超过显示器刷新率就会\n"
    "\t\t// 超发：present 队列积压、SL pacer 节奏崩 → 画面持续闪烁（v0.53 实测 160Hz 屏\n"
    "\t\t// + 4x + 写死 60fps 渲染 = 229.6 present fps，超发 43%）。非 0 时直接作为\n"
    "\t\t// 渲染帧率上限（fps），覆盖自动计算。\n"
    "\t\tint  reflexFpsLimit = 0;       // INI ReflexFpsLimit\n"
    "\t\tint  presetDLSS = 0;           // DLSS 模型预设：0=Auto 1=J 2=K 3=L 4=M\n"
)

# -------------------------------------------------------------- FrameGen.cpp
CPP_OLD = (
    "\t\t\telse if (key == \"MFGMaxFramesOverride\")\n"
    "\t\t\t\tsettings.mfgMaxFramesOverride = std::clamp(readInt(line, 0), 0, 5);\n"
)
CPP_NEW = (
    "\t\t\telse if (key == \"MFGMaxFramesOverride\")\n"
    "\t\t\t\tsettings.mfgMaxFramesOverride = std::clamp(readInt(line, 0), 0, 5);\n"
    "\t\t\t// v0.54：Reflex 渲染帧率上限（0 = 自动按 刷新率/总倍数 计算；见 Streamline::ReflexSleep）\n"
    "\t\t\telse if (key == \"ReflexFpsLimit\")\n"
    "\t\t\t\tsettings.reflexFpsLimit = std::clamp(readInt(line, 0), 0, 480);\n"
)

# ------------------------------------------------------------ Streamline.cpp
SL_OLD = (
    "\t\tsl::ReflexOptions opts{};\n"
    "\t\topts.mode = sl::ReflexMode::eLowLatency;  // DLSSG 要求至少 eLowLatency\n"
    "\t\topts.frameLimitUs = 1000000 / 60;         // CS 默认 reflexFPSLimit=60 限帧\n"
    "\t\topts.useMarkersToOptimize = featurePCL;   // PCL marker 优化（Reflex 激活必需）\n"
)
SL_NEW = (
    "\t\tsl::ReflexOptions opts{};\n"
    "\t\topts.mode = sl::ReflexMode::eLowLatency;  // DLSSG 要求至少 eLowLatency\n"
    "\t\t// v0.54（闪烁根因修复）：渲染帧率上限必须与\"显示器刷新率 / 帧生成总倍数\"配比。\n"
    "\t\t// 旧代码写死 opts.frameLimitUs = 1000000/60（从 CS 抄来的 reflexFPSLimit=60），\n"
    "\t\t// Reflex 会如实把**渲染**帧率压在 60fps。2026-09-17 16:26 实测（2560x1440@160Hz）：\n"
    "\t\t//   日志 Reflex options applied (frameLimitUs=16666)；perf.csv DeltaMs=17.43(=57.4fps)\n"
    "\t\t//   且 Multiplier=4 -> present = 57.4 x 4 = 229.6fps 灌进 160Hz 屏 = 超发 43%。\n"
    "\t\t// present 队列积压 -> SL pacer 节奏崩 -> 画面持续闪烁（fixed 模式不自动降档）。\n"
    "\t\t// 帧生成只有在\"渲染帧率 x 倍数 <= 刷新率\"时才成立，故改为按刷新率反推：\n"
    "\t\t//   自动 = 刷新率 / 总倍数 - 1fps（留余量避免顶到刷新率边缘）\n"
    "\t\t//   160Hz / 4x -> 39fps 渲染 -> 156 present fps，刚好在面板之下。\n"
    "\t\t// 倍率优先取运行时**实际接受**值（阶梯探测降档后能自动重算，不会再超发）；\n"
    "\t\t// 探测 latch 前回退到请求值。INI ReflexFpsLimit>0 时直接用它，跳过自动。\n"
    "\t\tstd::uint32_t capFps = 0;\n"
    "\t\tstd::uint32_t capMult = 1;\n"
    "\t\t{\n"
    "\t\t\tconst auto& s = Get().settings;\n"
    "\t\t\tif (s.reflexFpsLimit > 0) {\n"
    "\t\t\t\tcapFps = static_cast<std::uint32_t>(s.reflexFpsLimit);\n"
    "\t\t\t} else if (Get().refreshRate > 0.0) {\n"
    "\t\t\t\tconst std::uint32_t mfg = dlssgAcceptedFrames\n"
    "\t\t\t\t\t? dlssgAcceptedFrames\n"
    "\t\t\t\t\t: std::max<std::uint32_t>(1u, s.dlssgFramesToGenerate);\n"
    "\t\t\t\tcapMult = std::max<std::uint32_t>(1u, mfg + 1u);\n"
    "\t\t\t\tconst double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;\n"
    "\t\t\t\tcapFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);\n"
    "\t\t\t} else {\n"
    "\t\t\t\t// 刷新率读不到时不能再默默写死一个值（旧 60fps 就是这么来的 bug）——\n"
    "\t\t\t\t// 留 0 = 不限帧，并明确告警。\n"
    "\t\t\t\tSKSE::log::warn(\"[Streamline] Reflex render cap auto: DISABLED (refresh rate unknown) - over-submit is possible\");\n"
    "\t\t\t}\n"
    "\t\t\topts.frameLimitUs = capFps ? (1000000u / capFps) : 0u;\n"
    "\t\t\tstatic std::uint32_t lastCapFps = 0;\n"
    "\t\t\tstatic std::uint32_t lastCapMult = 0;\n"
    "\t\t\tif (capFps != lastCapFps || capMult != lastCapMult) {\n"
    "\t\t\t\tSKSE::log::info(\"[Streamline] Reflex render cap = {} fps ({}us) - {}Hz / {}x => ~{} present fps{}\",\n"
    "\t\t\t\t\tcapFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps * capMult,\n"
    "\t\t\t\t\tcapFps ? \"\" : \"  [UNLIMITED - over-submit possible]\");\n"
    "\t\t\t\tlastCapFps = capFps;\n"
    "\t\t\t\tlastCapMult = capMult;\n"
    "\t\t\t}\n"
    "\t\t}\n"
    "\t\topts.useMarkersToOptimize = featurePCL;   // PCL marker 优化（Reflex 激活必需）\n"
)

# -------------------------------------------------------------- ImguiMenu.cpp
GUI_OLD = (
    "\t\t\t<< \"MFGMaxFramesOverride=\" << s.mfgMaxFramesOverride << \"\\n\"\n"
    "\t\t\t<< \"Sharpness=\" << s.sharpness << \"\\n\"\n"
)
GUI_NEW = (
    "\t\t\t<< \"MFGMaxFramesOverride=\" << s.mfgMaxFramesOverride << \"\\n\"\n"
    "\t\t\t<< \"ReflexFpsLimit=\" << s.reflexFpsLimit << \"\\n\"\n"
    "\t\t\t<< \"Sharpness=\" << s.sharpness << \"\\n\"\n"
)

# --------------------------------------------------------------------- INI
INI_OLD = "MFGMaxFramesOverride=3\n"
INI_NEW = (
    "MFGMaxFramesOverride=3\n"
    "; ---------------------------------------------------------------------------\n"
    "; v0.54 - Render frame rate cap handed to Reflex (0 = auto).\n"
    ";\n"
    "; Multi-frame generation presents (render fps x multiplier) frames per second. If\n"
    "; that product is above the monitor refresh rate the frames are OVER-SUBMITTED: the\n"
    "; present queue backs up, the SL pacer loses its rhythm and the picture flickers\n"
    "; continuously. Frame generation is only correct when the product lands on the\n"
    "; panel:\n"
    ";\n"
    ";     render fps x multiplier <= refresh rate\n"
    ";\n"
    "; Auto (0) = (refresh rate / total multiplier) - 1 fps. On a 2560x1440 @ 160Hz\n"
    "; panel with 4x that is 39fps render => ~156 presented fps, just under the panel.\n"
    "; Too low = stutter, too high = flicker. The chosen value is logged whenever it\n"
    "; changes:  [Streamline] Reflex render cap = 39 fps (25641us) - 160Hz / 4x => ...\n"
    "; Set an explicit fps here to override the automatic value.\n"
    "; ---------------------------------------------------------------------------\n"
    "ReflexFpsLimit=0\n"
)

# -------------------------------------------------------------- version.rc
RC_EDITS = [
    ("FILEVERSION 0,53,0,0", "FILEVERSION 0,54,0,0"),
    ("PRODUCTVERSION 0,53,0,0", "PRODUCTVERSION 0,54,0,0"),
    ('VALUE "FileVersion", "0.53.0.0', 'VALUE "FileVersion", "0.54.0.0'),
    ('VALUE "ProductVersion", "0.53.0.0', 'VALUE "ProductVersion", "0.54.0.0'),
]

# -------------------------------------------------------------- CHANGELOG.md
LOG_OLD = "# v0.53 - the FPS number stops lying, and MFG gets a measurement\n"
LOG_NEW = (
    "# v0.54 - flicker: the render frame rate was pinned to 60fps regardless of the panel\n"
    "\n"
    "Reported: \"it flickers constantly.\"\n"
    "\n"
    "Root cause - measured, not guessed. Streamline::ReflexSleep() pushed a hardcoded\n"
    "reflex frame limit of 1000000/60 us (inherited from Community Shaders' default), and\n"
    "Reflex dutifully enforced it on the RENDER frame rate:\n"
    "\n"
    "    [16:24:47.175] [Streamline] Reflex options applied (mode=1 frameLimitUs=16666 ...)\n"
    "    DLSSG-Transfusion_perf.csv: DeltaMs=17.43 (=57.4 render fps), Multiplier=4\n"
    "\n"
    "57.4 render fps x 4 = 229.6 presented fps, pushed at a 2560x1440 @ 160Hz panel.\n"
    "That is 43% over-submission: the present queue backs up, the SL pacer loses its\n"
    "rhythm, and the picture flickers continuously. Transfusion was in `fixed` mode, so\n"
    "it never backed the multiplier off.\n"
    "\n"
    "Frame generation is only correct when the product lands on the panel:\n"
    "\n"
    "    render fps x multiplier <= refresh rate\n"
    "\n"
    "So the cap is now derived instead of hardcoded:\n"
    "\n"
    "    auto: (refreshRate / totalMultiplier) - 1 fps\n"
    "          160Hz / 4x -> 39fps -> ~156 presented fps, just under the panel\n"
    "    ReflexFpsLimit=N  (new INI key) overrides it with an explicit render fps cap\n"
    "\n"
    "The multiplier used is the runtime-ACCEPTED one (dlssgAcceptedFrames), falling back\n"
    "to the requested DLSSGFramesToGenerate before the staircase probe latches - so a\n"
    "stepped-down request re-derives the cap instead of over-submitting again. The value\n"
    "is logged whenever it changes:\n"
    "\n"
    "    [Streamline] Reflex render cap = 39 fps (25641us) - 160Hz / 4x => ~156 present fps\n"
    "\n"
    "If the refresh rate cannot be read the cap is left at 0 (unlimited) and a warning is\n"
    "logged - silently substituting some made-up number is exactly what caused this bug.\n"
    "\n"
    "This also explains why the FPS counter sat at ~57 no matter what was requested: the\n"
    "render side was pinned, so the generated side could never track the panel.\n"
    "\n"
    "\n"
) + LOG_OLD


EDITS = [
    (H, "reflexFpsLimit", [(H_OLD, H_NEW)]),
    (CPP, 'key == "ReflexFpsLimit"', [(CPP_OLD, CPP_NEW)]),
    (SL, "Reflex render cap", [(SL_OLD, SL_NEW)]),
    (GUI, '"ReflexFpsLimit="', [(GUI_OLD, GUI_NEW)]),
    (INI, "ReflexFpsLimit=", [(INI_OLD, INI_NEW)]),
    (RC, "FILEVERSION 0,54,0,0", RC_EDITS),
    (LOG, "# v0.54 - flicker", [(LOG_OLD, LOG_NEW)]),
]


def main():
    apply = "--apply" in sys.argv
    problems = []
    pending = []

    for rel, marker, subs in EDITS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            problems.append("MISSING FILE: {}".format(rel))
            continue
        raw = io.open(path, "rb").read().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        src = raw.replace("\r\n", "\n")

        # idempotency guard FIRST (an insert-style patch does not consume its anchor)
        if marker in src:
            problems.append("ALREADY APPLIED (marker {!r} present): {}".format(marker, rel))
            continue

        out = src
        for old, new in subs:
            n = out.count(old)
            if n != 1:
                problems.append("ANCHOR {} times (need exactly 1) in {} :: {!r}...".format(
                    n, rel, old[:70].replace("\n", "\\n")))
                continue
            out = out.replace(old, new)
        if out == src:
            problems.append("NO CHANGE in {} (all anchors failed)".format(rel))
            continue
        pending.append((rel, path, out, nl, len(src), len(out)))

    if problems:
        print("=== REFUSED, nothing written ===")
        for p in problems:
            print("  ! " + p)
        return 1

    print("=== dry run OK: {} file(s), all anchors unique ===".format(len(pending)))
    for rel, _p, _o, nl, a, b in pending:
        print("  {}  {} -> {} bytes".format(rel, a, b))

    if not apply:
        print("\n(dry run - pass --apply to write)")
        return 0

    for rel, path, out, nl, _a, _b in pending:
        io.open(path, "wb").write(out.replace("\n", nl).encode("utf-8"))
        print("  written: {}".format(rel))
    print("\n=== APPLIED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
