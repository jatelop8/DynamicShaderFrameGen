# -*- coding: utf-8 -*-
"""
add_xray_v063.py -- DynamicShaderFrameGen v0.63 patch

Root cause fixed here (evidence: 2026-09-17 21:54 run)
------------------------------------------------------
The Reflex frame limiter paces PRESENTED (flip) frames, not rendered frames.

  * [XRAY] heartbeat, every sample:  capUs=25641  (constant)
  * dt min/avg/max                  = 102.10/102.57/103.12 ms
  * 102.56 / 25.641                 = 4.0000   (5 significant figures)
  * DLSSG: "presented per real frame = 4"
  * perf.csv, 65 consecutive frames: 102.55 / 102.56 / 102.57  (spread 0.02 ms)

A 4K + ENB + neural-render frame cannot land on 4.0000x a 25.641 ms quantum by
chance, and a GPU-bound frame wanders by milliseconds instead of 0.02 ms. The
25.641 ms quantum IS the frameLimitUs this build handed to Reflex, and there are
exactly 4 flips per real frame, so the limiter throttled flips to 39/s and the
render side collapsed to 39/4 = 9.75 fps.

v0.54 computed the cap as refreshRate / multiplier - 1 ("39 fps render => 156
presented"), i.e. it divided by the multiplier. Because the limiter is on the
flip side, that division was applied a second time. v0.63 removes it: the cap
describes the flip schedule, so it must be just under the panel rate.

Consequence of the old value, and why it read as "flicker that gets worse":
only 1 of every 4 displayed frames was real, and the 3 fabricated ones had to
reproject across up to 102 ms of world motion. Standing still in a menu that is
a mild shimmer; moving in the world it collapses.

Also included
-------------
* VERDICT no longer re-fires "menu still generates 4 frames/real frame" forever
  after the menu is closed (the counters it reads are cumulative).
* Watchdog no longer reports RENDER THREAD STALLED during the ~20 s load, where
  frames legitimately stays at 1. It now requires frames >= 60 first.
* Menu guard: the plugin stops submitting work to DLSS-G while a game menu is
  up. This is what DLSSGFlags::eEnableFullScreenMenuDetection would have done,
  but Transfusion strips that flag before the runtime sees it
  (2026-09-17 21:54:06.810: "stripped eEnableFullscreenMenuDetection from
  DLSS-G options (game flags=0x00000010 -> 0x00000010)" - identical before and
  after, so it never reached DLSS-G). INI key MenuDisableFrameGen=0 reverts it
  without a rebuild.

Usage
-----
  python tools/add_xray_v063.py            # dry run
  python tools/add_xray_v063.py --apply    # write
"""

import io
import os
import re
import sys
import shutil
import hashlib
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPLY = "--apply" in sys.argv
STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

FILES = {
    "sl_cpp": os.path.join(ROOT, "src", "Streamline.cpp"),
    "sl_h": os.path.join(ROOT, "src", "Streamline.h"),
    "sc_cpp": os.path.join(ROOT, "src", "DX12SwapChain.cpp"),
    "fg_h": os.path.join(ROOT, "src", "FrameGen.h"),
    "fg_cpp": os.path.join(ROOT, "src", "FrameGen.cpp"),
    "gui_cpp": os.path.join(ROOT, "src", "ImguiMenu.cpp"),
    "ini": os.path.join(ROOT, "SKSE", "Plugins", "DynamicShaderFrameGen.ini"),
}


def detect_eol(text):
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


# ---------------------------------------------------------------- edit helpers

def sub_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(
            "REFUSED at [%s]: anchor occurs %d times (must be exactly 1)\n"
            "--- anchor ---\n%s\n--------------" % (label, n, old[:400])
        )
    return text.replace(old, new, 1)


def sub_regex_once(text, pattern, new, label, flags=0):
    hits = list(re.finditer(pattern, text, flags))
    if len(hits) != 1:
        raise SystemExit(
            "REFUSED at [%s]: regex matched %d times (must be exactly 1)\n"
            "--- pattern ---\n%s\n---------------" % (label, len(hits), pattern[:400])
        )
    m = hits[0]
    return text[:m.start()] + new + text[m.end():]


# --------------------------------------------------------------------- anchors

# 1. pacing: remove the division by the multiplier
A_WANT = "const double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;"
N_WANT = "const double want = Get().refreshRate - 1.0;"

# 2. log format string (argument list left untouched: still 6 placeholders)
A_LOGFMT = '"[Streamline] Reflex render cap = {} fps ({}us) - {}Hz / {}x => ~{} present fps{}",'
N_LOGFMT = ('"[Streamline] Reflex FLIP cap = {} fps ({}us) - panel {}Hz, {} flips per real frame '
            '=> ~{} presented fps (real = cap/flips){}",')

# 3. the v0.54 explanation block -> v0.63
A_CMT_START = "\t\t// v0.54（闪烁根因修复）：渲染帧率上限必须与"
A_CMT_END = "\t\t// 探测 latch 前回退到请求值。INI ReflexFpsLimit>0 时直接用它，跳过自动。"

N_CMT = """\t\t// v0.63（限速器作用面搞错了 —— 真正根因）：这个上限描述的是**上屏 flip 节拍**，
\t\t// 不是渲染帧率。v0.54 按"渲染帧率"反推（刷新率 / 总倍数 - 1），等于把 flip 节流
\t\t// 到 39/s；而 DLSS-G 每真实帧要发 4 个 flip ⇒ 渲染侧被压成 39/4 = 9.75fps。
\t\t// 实测（2026-09-17 21:54，3840x2160）：
\t\t//   心跳每帧 capUs=25641 恒定；dt min/avg/max = 102.10/102.57/103.12ms；
\t\t//   102.56 / 25.641 = 4.0000（5 位有效数字）；presented per real frame = 4；
\t\t//   perf.csv 连续 65 帧 102.55/102.56/102.57（离散度 0.02ms）。
\t\t// 4K + ENB + 神经渲染不可能恰好落在 25.641ms 量子的整 4 倍上，而且 GPU 受限的帧
\t\t// 会飘几毫秒而不是 0.02ms ⇒ 这是限速器的量子，被多除了一次。
\t\t// 后果：每 4 个上屏帧只有 1 个是真的，另 3 个要跨越最长 102ms 的世界运动去重投影
\t\t// ⇒ 站在菜单里只是轻微微闪，一动起来就崩（用户："越来越闪"）。
\t\t// 现在：cap = 刷新率 - 1（留 1Hz 余量避免顶到面板），flip 节流在 159/s < 160Hz，
\t\t// 既不超发（v0.54 的初衷仍然满足），渲染侧又回到 ~159/4 ≈ 39.75fps。
\t\t// 倍率只用于日志里算"每真实帧几个 flip"，不再参与上限计算。
\t\t// INI ReflexFpsLimit>0 时直接用它（fps 单位，同样是 flip 上限），跳过自动。"""

# 4. VERDICT: stop re-firing after the menu closes
A_VD_GATE = "else if (diag.menuFrames > 60 && mm >= want)"
N_VD_GATE = "else if (diag.menuOpenNow && diag.menuFrames > 60 && mm >= want)"

A_VD_MSG = 'vd = "PROBLEM menu still generates " + std::to_string(mm) +'
N_VD_MSG = 'vd = "PROBLEM menu OPEN RIGHT NOW generates " + std::to_string(mm) +'

A_VD_MSG2 = '" frames/real frame -> eEnableFullscreenMenuDetection NOT honoured";'
N_VD_MSG2 = '" frames/real frame -> menu guard NOT effective (flag stripped by the shim?)";'

# 5. expose the menu probe to the Present path
A_ANON_END = '''\t\t\t\tui->IsMenuOpen(istrings->journalMenu) || ui->IsMenuOpen("PauseMenu");
\t\t}
\t}
'''
N_ANON_END = A_ANON_END + '''
\t// v0.63：Present 路径（DX12SwapChain.cpp）要用同一个菜单判断，去自行实现
\t// DLSSGFlags::eEnableFullScreenMenuDetection —— Transfusion 会在提交给运行时之前
\t// 把这个 flag 从 DLSS-G options 里剥掉（2026-09-17 21:54:06.810：
\t// "stripped eEnableFullscreenMenuDetection ... 0x10 -> 0x10"，剥前剥后完全相同
\t// = 运行时从来没收到过），所以插件侧必须自己关。
\tbool Streamline::MenuOpenNow()
\t{
\t\treturn GameMenuOpenNow();
\t}
'''

# 6. Streamline.h: declare it
A_SL_H = '''\t\t// 释放
\t\tvoid DestroyResources();

\tprivate:'''
N_SL_H = '''\t\t// 释放
\t\tvoid DestroyResources();

\t\t// v0.63：游戏菜单是否打开。与 CheckFrameConstants 内部用的是同一份实现
\t\t// （GameMenuOpenNow），Present 路径用它自行实现 eEnableFullscreenMenuDetection
\t\t// —— Transfusion 会把该 flag 从 DLSS-G options 里剥掉，运行时收不到。
\t\tbool MenuOpenNow();

\tprivate:'''

# 7. DX12SwapChain.cpp: menu guard + do not count it as a failure
A_SC_MAIN = '''\t\t\tconst bool fgOn = fg.fgActive.load();  // Home 键开关
\t\t\tbool dlssgOk = false;
\t\t\t// 防刷屏：连续失败计数（static，Present 渲染线程单线程）
\t\t\tstatic int dlssgFailCount = 0;
\t\t\tif (fgOn && fg.streamline.featureDLSSG && fg.GetFrameBuffer()) {'''
N_SC_MAIN = '''\t\t\tconst bool fgOn = fg.fgActive.load();  // Home 键开关
\t\t\tbool dlssgOk = false;
\t\t\t// 防刷屏：连续失败计数（static，Present 渲染线程单线程）
\t\t\tstatic int dlssgFailCount = 0;
\t\t\t// v0.63：菜单期间不插帧 —— DLSSGFlags::eEnableFullScreenMenuDetection 的
\t\t\t// 插件侧替代实现（那个 flag 到不了运行时，见 Streamline::MenuOpenNow）。
\t\t\t// 菜单是 2D UI，被当 3D 内容插值就是"主菜单画面持续闪"的直接来源。
\t\t\t// 走下面已有的直通拷回路径（backbuffer = 真实帧），用户 Home 开关意图不变。
\t\t\tconst bool menuBlock =
\t\t\t\tfgOn && fg.settings.menuDisableFrameGen && fg.streamline.MenuOpenNow();
\t\t\tif (menuBlock) {
\t\t\t\t// 这是**主动直通**，不是失败。必须清零计数器，否则在菜单里待满 ~2s
\t\t\t\t// 就会撞上 dlssgFailCount>120 把插帧整个自动关掉（Home 也救不回）。
\t\t\t\tdlssgFailCount = 0;
\t\t\t} else if (fgOn && fg.streamline.featureDLSSG && fg.GetFrameBuffer()) {'''

# 8. watchdog: loading is not a stall
A_WD_F = "\t\t\t\tif (FILE* f = std::fopen(path.c_str(), \"a\")) {"
N_WD_F = '''\t\t\t\t// v0.63：装载期不是卡死。21:54 那次运行在约 20s 装载里 frames 恒为 1、
\t\t\t\t// stage 恒为 "d3d11 Wait"，看门狗连打 19 行 RENDER THREAD STALLED —— 全是
\t\t\t\t// 假警报。判据收紧：渲染线程必须"曾经跑顺过"（frames>=60）才允许报卡死，
\t\t\t\t// 未达标只记 silent（装载期的正常表现）。
\t\t\t\tconst bool warm = frames >= 60;
\t\t\t\tif (FILE* f = std::fopen(path.c_str(), "a")) {'''

A_WD_MARK = "(lastEnd != 0 && silent > 1500) ? \"   <== RENDER THREAD STALLED\" : \"\");"
N_WD_MARK = "(lastEnd != 0 && warm && silent > 1500) ? \"   <== RENDER THREAD STALLED\" : \"\");"

# 9. FrameGen.h: new setting
A_FG_H = "\t\tint  reflexFpsLimit = 0;       // INI ReflexFpsLimit"
N_FG_H = '''\t\tint  reflexFpsLimit = 0;       // INI ReflexFpsLimit
\t\t// v0.63：菜单期间不插帧（DLSSGFlags::eEnableFullScreenMenuDetection 的插件侧
\t\t// 替代实现 —— Transfusion 会把那个 flag 从 DLSS-G options 里剥掉）。菜单是 2D
\t\t// UI，被当 3D 内容插值 = 主菜单画面持续闪。0 = 旧行为（菜单也插帧）。
\t\tbool menuDisableFrameGen = true;  // INI MenuDisableFrameGen'''

# 10. FrameGen.cpp: parse it
A_FG_CPP = '''\t\t\telse if (key == "ReflexFpsLimit")
\t\t\t\tsettings.reflexFpsLimit = std::clamp(readInt(line, 0), 0, 480);'''
N_FG_CPP = A_FG_CPP + '''
\t\t\t// v0.63：菜单期间不插帧（1=开，默认；0=旧行为，菜单也插帧 -> 菜单画面持续闪）
\t\t\telse if (key == "MenuDisableFrameGen")
\t\t\t\tsettings.menuDisableFrameGen = readBool(line, true);'''

# 11. ImguiMenu.cpp: persist it
A_GUI = '\t\t\t<< "ReflexFpsLimit=" << s.reflexFpsLimit << "\\n"'
N_GUI = A_GUI + '\n\t\t\t<< "MenuDisableFrameGen=" << (s.menuDisableFrameGen ? 1 : 0) << "\\n"'

# 12. INI: new semantics + new key
A_INI = "; v0.54 - Render frame rate cap handed to Reflex (0 = auto)."
N_INI = """; v0.63 - Frame limiter value handed to Reflex (0 = auto). Unit: fps.
;
; NAME CHANGED ON PURPOSE (v0.54 -> v0.63): this value limits the rate at which
; frames are PRESENTED to the panel (flips), not the rate the engine renders at.
; v0.54 divided the refresh rate by the multiplier ("39 fps render => 156
; presented") on the assumption that the limiter sits on the render side. It does
; not, so the division landed twice and the render side collapsed.
;
;   measured 2026-09-17 21:54 run, 3840x2160, multiplier 4:
;     heartbeat capUs = 25641 for every sample        (25.641 ms = 39.0 fps)
;     real frame interval = 102.56 ms                 (4.0000 x 25641 us)
;     65 consecutive perf.csv frames: 102.55/102.56/102.57  (spread 0.02 ms)
;     DLSSG: "presented per real frame = 4"
;   => 4 flips per real frame at a 25.641 ms flip budget = 102.56 ms per real
;      frame = 9.75 real fps. Standing in a menu that is a mild shimmer; the
;      3 fabricated frames of every 4 have to reproject across up to 102 ms of
;      motion, so it falls apart as soon as the camera moves.
;
; Auto (0) = refresh rate - 1 fps, i.e. the flip schedule sits just under the
; panel. On a 160Hz panel that is 159 fps => 159/4 = ~39.75 real fps.
; Because the cap is below the refresh rate, over-submission (the thing v0.54 was
; trying to fix) still cannot happen.
; Logged whenever it changes:
;   [Streamline] Reflex FLIP cap = 159 fps (6289us) - panel 160Hz, 4 flips per
;   real frame => ~159 presented fps (real = cap/flips)
;
; Set an explicit fps here to override the automatic value. 0 = auto.
; ---------------------------------------------------------------------------
ReflexFpsLimit=0

; v0.63 - Do not submit frames to DLSS-G while a game menu is open.
; 1 = menus are not interpolated (default; a menu is 2D UI and interpolating it
;     shows up as a continuously flickering menu screen).
; 0 = old behaviour (menus are interpolated too).
; This is the plugin-side replacement for DLSSGFlags::eEnableFullScreenMenuDetection:
; the shim strips that flag from the DLSS-G options before the runtime sees it
; (log line "Option C active: stripped eEnableFullscreenMenuDetection from
; DLSS-G options (game flags=0x00000010 -> 0x00000010)" - identical before and
; after), so the flag can never take effect and the plugin does it itself.
; The Home/toggle key is unaffected.
MenuDisableFrameGen=1"""


EDIT_PLAN = [
    ("sl_cpp", A_WANT, N_WANT, "sub"),
    ("sl_cpp", A_LOGFMT, N_LOGFMT, "sub"),
    ("sl_cpp", (A_CMT_START, A_CMT_END), N_CMT, "block"),
    ("sl_cpp", A_VD_GATE, N_VD_GATE, "sub"),
    ("sl_cpp", A_VD_MSG, N_VD_MSG, "sub"),
    ("sl_cpp", A_VD_MSG2, N_VD_MSG2, "sub"),
    ("sl_cpp", A_ANON_END, N_ANON_END, "sub"),
    ("sl_h", A_SL_H, N_SL_H, "sub"),
    ("sc_cpp", A_SC_MAIN, N_SC_MAIN, "sub"),
    ("sc_cpp", A_WD_F, N_WD_F, "sub"),
    ("sc_cpp", A_WD_MARK, N_WD_MARK, "sub"),
    ("fg_h", A_FG_H, N_FG_H, "sub"),
    ("fg_cpp", A_FG_CPP, N_FG_CPP, "sub"),
    ("gui_cpp", A_GUI, N_GUI, "sub"),
    ("ini", A_INI, N_INI, "iniblock"),
]

# every edit carries this token, so the second run of the script is refused
MARKER = "v0.63"


def block_replace(text, start_anchor, end_anchor, new, label, indent):
    """Replace start_anchor..end_anchor (whole lines) with `new` (already indented)."""
    lines = text.split("\n")
    si = ei = -1
    for i, ln in enumerate(lines):
        if si < 0 and start_anchor.strip() in ln:
            si = i
        if si >= 0 and end_anchor.strip() in ln:
            ei = i
            break
    if si < 0 or ei < 0 or ei < si:
        raise SystemExit("REFUSED at [%s]: block anchors not found (si=%d ei=%d)" % (label, si, ei))
    out = lines[:si] + new.split("\n") + lines[ei + 1:]
    return "\n".join(out)


def ini_block_replace(text, start_anchor, new):
    lines = text.split("\n")
    # the block ends at the first ReflexFpsLimit= line at or after the anchor
    si = -1
    for i, ln in enumerate(lines):
        if ln.strip().startswith("; v0.54 - Render frame rate cap"):
            si = i
            break
    if si < 0:
        raise SystemExit("REFUSED at [ini]: v0.54 comment block not found")
    ei = -1
    for j in range(si, len(lines)):
        if lines[j].strip() == "ReflexFpsLimit=0":
            ei = j
            break
    if ei < 0:
        raise SystemExit("REFUSED at [ini]: ReflexFpsLimit=0 terminator not found")
    return "\n".join(lines[:si] + new.split("\n") + lines[ei + 1:])


def main():
    # ---- idempotency guard FIRST (an insert-type edit does not consume its anchor)
    for key, path in FILES.items():
        txt = read(path)
        if MARKER in txt:
            raise SystemExit("REFUSED: '%s' already contains '%s' - patch already applied" %
                             (path, MARKER))

    originals = {}
    results = {}
    for key, path in FILES.items():
        txt = read(path)
        originals[key] = (txt, detect_eol(txt))
        # anchors are written with LF; this repo mixes CRLF (.h) and LF (.cpp),
        # so normalise in memory and restore the original EOL on write.
        results[key] = txt.replace("\r\n", "\n")

    for key, a, b, kind in EDIT_PLAN:
        txt = results[key]
        if kind == "sub":
            results[key] = sub_once(txt, a, b, "%s:%.60s" % (key, a))
        elif kind == "block":
            results[key] = block_replace(txt, a[0], a[1], b, key, "\t\t")
        elif kind == "iniblock":
            results[key] = ini_block_replace(txt, a, b)

    # ---- report / write
    for key, path in FILES.items():
        orig, eol = originals[key]
        new = results[key]
        if eol != "\n":
            # results are pure LF at this point
            new = new.replace("\n", eol)
        print("%-8s %-46s %7d -> %7d bytes  eol=%s" %
              (key, os.path.basename(path), len(orig), len(new),
               "CRLF" if eol != "\n" else "LF"))

        if APPLY:
            bak = path + ".bak-" + STAMP
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
            with io.open(path, "w", encoding="utf-8", newline="") as f:
                f.write(new)
            # read back and verify byte-for-byte
            chk = read(path)
            if chk != new:
                raise SystemExit("VERIFY FAILED after writing %s" % path)
            if detect_eol(chk) != eol:
                raise SystemExit("VERIFY FAILED: EOL changed in %s" % path)
            print("           written, read-back identical, backup=%s" %
                  os.path.basename(bak))

    if not APPLY:
        print("\nDRY RUN - nothing written. Re-run with --apply")
    else:
        print("\nDONE. Applied %d edits across %d files. Marker '%s' now present "
              "(a second run will be refused)." % (len(EDIT_PLAN), len(FILES), MARKER))


if __name__ == "__main__":
    main()
