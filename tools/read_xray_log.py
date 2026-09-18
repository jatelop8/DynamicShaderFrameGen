#!/usr/bin/env python3
"""Translate a DynamicShaderFrameGen log into a verdict.

Reads the [XRAY] instrumentation (v0.61, extended in v0.62) and prints what the
run actually proved, so a single launch answers "where does the flicker come
from" without re-deriving it by hand from interleaved probe lines.

v0.62 additions:
  * section 0 reads the watchdog file. The watchdog thread writes one line per
    second with its own fopen/fflush/fclose, so it keeps producing evidence when
    the render thread is blocked and when the SKSE sink never flushes its tail -
    that is the case the 21:40 run died in (nothing was written after 21:40:44.4).
  * the heartbeat now carries the real-frame interval window (dt min/avg/max/n),
    the Reflex cap this build programmed (capUs) and the long-frame count, so
    "is the frame rate limiter-quantised or GPU-bound" is decidable from one line.

Usage:
    python read_xray_log.py                     # default DFG log
    python read_xray_log.py <log path>
    python read_xray_log.py --transfusion <path>

Exit code: 0 = no defect flagged, 1 = something flagged, 2 = log unreadable.
"""

import os
import re
import sys
import collections
import time

DFG_LOG = os.path.join(
    os.path.expanduser("~"), "Documents", "My Games", "Skyrim Special Edition",
    "SKSE", "DynamicShaderFrameGen.log")
WATCHDOG_LOG = os.path.join(
    os.path.expanduser("~"), "Documents", "My Games", "Skyrim Special Edition",
    "SKSE", "DynamicShaderFrameGen.watchdog.log")
TRANSFUSION_LOG = r"D:\ENB-EJ\Skyrim Special Edition\DLSSG-Transfusion.log"

SEV_OK = "  [OK]  "
SEV_WARN = "  [注意]"
SEV_BAD = "  [问题]"
SEV_INFO = "  [信息]"

findings = []          # (severity, text)


def note(sev, text):
    findings.append((sev, text))


def read(path):
    if not os.path.isfile(path):
        return None
    raw = open(path, "rb").read()
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


LINE_RE = re.compile(r"^\[(\d\d:\d\d:\d\d\.\d\d\d)\]\s*\[\d+\]\s*\[(\w)\]\s?(.*)$")


def parse_lines(text):
    out = []
    for ln in text.replace("\r\n", "\n").split("\n"):
        m = LINE_RE.match(ln)
        if m:
            out.append((m.group(1), m.group(2), m.group(3).rstrip()))
        elif ln.strip():
            out.append(("", "?", ln.rstrip()))
    return out


def section(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def grab(pat, lines):
    rx = re.compile(pat)
    return [l for l in lines if rx.search(l[2])]


def last(pat, lines):
    hits = grab(pat, lines)
    return hits[-1] if hits else None


# ------------------------------------------------------------------ watchdog
# v0.71: focus= was appended to the watchdog line, so the old pattern no
# longer matches ANY line. The focus group is optional on purpose: lines
# written by earlier builds must still parse, or the cross-run splitting
# below (which walks backwards on the frame counter) loses its history.
# v0.73: field history. Every field after stage= is optional on purpose, because
# records from older builds must still parse - the cross-run split below walks
# backwards on the frame counter and dies without the history.
#   v0.62  [mono] frames= silent=ms stage=
#   v0.71  ... focus=
#   v0.72  ... fence=a/b
#   v0.73  [mono] hh:mm:ss.mmm frames= silent=ms stage= focus= fence=a/b|-/- stim=n
#   v0.74  ... queued=N lastPr=N dsync=0|1
# `stim` is the sampler thread's tick count. v0.73 gated the sampler on
# silent >= 1500 ms, which turned out to hide exactly the failure it was built
# for (see the v0.74 notes below); v0.74 samples unconditionally, so stim now
# climbs during ordinary play and only stops if the sampler itself blocks.
# The three v0.74 fields judge the GPU timeline, which no other field can:
#   queued  frames submitted but not yet retired by the fence (>3 = the CPU is
#           running ahead of the GPU, i.e. Present lost its backpressure)
#   lastPr  swap chain present counter - flat while frames still climbs means
#           Present returns success without flipping the screen
#   dsync   v0.76 CHANGED MEANING. Up to v0.75: 1 = the index after Present
#           differed from frameIndex before it - which is what a SUCCESSFUL flip
#           does, so healthy runs read as desynced. From v0.76: 1 = the index did
#           NOT move, i.e. Present returned success without flipping the screen.
# v0.76 also adds msg/alive: the watchdog asking the game window whether it is
# still answering messages (SendMessageTimeout WM_NULL). msg=0 is the same
# condition USER32 paints as "Not Responding" - the user-visible freeze.
WD_RE = re.compile(
    r"^\[(?P<ms>\d+)\]\s+"
    r"(?:(?P<hh>\d\d):(?P<mm>\d\d):(?P<ss>\d\d)\.(?P<msec>\d{3})\s+)?"
    r"frames=(?P<frames>\d+)\s+silent=(?P<silent>-?\d+)ms\s+stage=(?P<stage>.*?)"
    r"(?:\s+focus=(?P<focus>-?\d+))?"
    r"(?:\s+fence=(?P<f11>\d+|~0|-)/(?P<f12>\d+|~0|-))?"
    r"(?:\s+stim=(?P<stim>\d+))?"
    r"(?:\s+queued=(?P<queued>\d+))?"
    r"(?:\s+lastPr=(?P<lastpr>\d+))?"
    r"(?:\s+dsync=(?P<dsync>\d+))?"
    r"(?:\s+msg=(?P<msg>\d+))?"
    r"(?:\s+alive=(?P<alive>\d+))?"
    r"\s*(?P<stalled><==.*)?$")


def _wd_num(v):
    """Fence text to int, or None for the placeholders older/newer builds emit."""
    if v is None:
        return None
    return int(v) if v.lstrip("-").isdigit() else None


def parse_wd_line(ln):
    """One watchdog record as a dict, or None if the line is not one."""
    m = WD_RE.match(ln.strip())
    if not m:
        return None
    g = m.groupdict()
    return {
        "ms": int(g["ms"]),
        "wall": ("%s:%s:%s.%s" % (g["hh"], g["mm"], g["ss"], g["msec"])) if g["hh"] else None,
        "frames": int(g["frames"]),
        "silent": int(g["silent"]),
        "stage": g["stage"],
        "focus": int(g["focus"]) if g["focus"] is not None else -1,
        "f11": _wd_num(g["f11"]),
        "f12": _wd_num(g["f12"]),
        "stim": int(g["stim"]) if g["stim"] is not None else None,
        # v0.74: the GPU-timeline fields. None (not 0) when absent, so a reader
        # can tell "this build never wrote it" from "it wrote a real zero".
        "queued": int(g["queued"]) if g.get("queued") is not None else None,
        "lastpr": int(g["lastpr"]) if g.get("lastpr") is not None else None,
        "dsync": int(g["dsync"]) if g.get("dsync") is not None else None,
        # v0.76: window responsiveness. None when the build predates the probe.
        "msg": int(g["msg"]) if g.get("msg") is not None else None,
        "alive": int(g["alive"]) if g.get("alive") is not None else None,
        "stalled": bool(g["stalled"]),
    }


def parse_wd_file(path):
    """Every parsable watchdog record, in file order."""
    try:
        raw = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return []
    return [r for r in (parse_wd_line(ln) for ln in raw) if r]


def last_run_exit(path):
    """(index of the last tick line, the [exit] line after it or None).

    Position rather than timestamp: the file is append-only across runs, so an
    [exit] written by an earlier session must not be credited to this one.
    """
    try:
        raw = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return -1, None
    last_tick = -1
    for i, ln in enumerate(raw):
        if parse_wd_line(ln):
            last_tick = i
    if last_tick < 0:
        return -1, None
    for ln in raw[last_tick:]:
        if "DLL_PROCESS_DETACH" in ln:
            return last_tick, ln.strip()
    return last_tick, None


def part_watchdog():
    section("0. 看门狗（独立文件，渲染线程卡住时唯一还写得动的东西）")
    text = read(WATCHDOG_LOG)
    if text is None:
        print(SEV_WARN + "没有 %s" % WATCHDOG_LOG)
        print("          → 本次跑的 DLL 早于 v0.62，或者根本没进到 CreateInterop")
        note(SEV_WARN, "看门狗文件缺失 —— 无法判定渲染线程是否卡死")
        return

    recs = []
    for ln in text.replace("\r\n", "\n").split("\n"):
        r = parse_wd_line(ln)
        if r:
            # Indices 0..5 keep their old meaning; v0.73 fields go on the end so
            # nothing that reads this tuple has to be renumbered.
            recs.append((r["ms"], r["frames"], r["silent"], r["stage"], r["focus"],
                         r["stalled"], r["wall"], r["stim"], r["f11"], r["f12"],
                         r["queued"], r["lastpr"], r["dsync"]))
    if not recs:
        print(SEV_WARN + "看门狗文件存在但没有可解析的行：")
        for ln in text.strip().split("\n")[-5:]:
            print("         " + ln)
        return

    # 看门狗文件是**跨运行追加**的，而且没有运行分隔符 —— 这一点已经造成过一次
    # 误判：2026-09-17 22:40 读到的 19 行 "RENDER THREAD STALLED"（全部 frames=1）
    # 其实是 21:54 那次运行的残留（boot 相对时刻 859xxxxx），而 22:42 这次运行在
    # 888xxxxx、frames 一路涨到 732、**零 STALLED**。把旧运行的记录算到当次头上，
    # 会直接把结论指向一个不存在的故障点。
    # 故：按「帧号回退」切分运行，只看**最后一段**。
    seg_start = 0
    for _i in range(1, len(recs)):
        if recs[_i][1] < recs[_i - 1][1]:
            seg_start = _i
    skipped = seg_start
    recs = recs[seg_start:]
    if skipped:
        print(SEV_INFO + "看门狗文件是跨运行追加的：已跳过前 %d 个 tick（旧运行的残留），"
              "下面只看本次运行那一段。" % skipped)

    t0, t1 = recs[0][0], recs[-1][0]
    print(SEV_INFO + "共 %d 个 tick，覆盖 %.1f 秒（%d → %d ms 单调时钟）"
          % (len(recs), (t1 - t0) / 1000.0, t0, t1))
    focus_txt = ("focus=%d" % recs[-1][4]) if recs[-1][4] >= 0 else "focus=(n/a)"
    wall_txt = ("%s " % recs[-1][6]) if recs[-1][6] else "(无墙钟：DLL 早于 v0.73) "
    print(SEV_INFO + "最后一行：%sframes=%d silent=%dms stage=%s %s"
          % (wall_txt, recs[-1][1], recs[-1][2], recs[-1][3], focus_txt))

    stalled = [r for r in recs if r[5]]
    if not stalled:
        print(SEV_OK + "反复采样到新帧，渲染线程没有卡死（本次跑是正常退出或被杀）")
    else:
        # The first stalled tick names the stage the render thread entered and
        # never left: the frame counter stops advancing from here on.
        first = stalled[0]
        idx = recs.index(first)
        prev = recs[idx - 1] if idx > 0 else None
        run = [r for r in recs[idx:] if r[5]]
        dur = (run[-1][0] - (prev[0] if prev else first[0])) / 1000.0
        print(SEV_BAD + "渲染线程卡死：约 %.1f 秒没有完成任何一帧" % dur)
        print("         卡在 stage = '%s'" % first[3])
        print("         最后一帧的帧号 %d 在此之后不再增长（卡死前 %s）"
              % (first[1], ("frames=%d stage=%s" % (prev[1], prev[3])) if prev else "-"))
        # v0.71: focus= is the difference between the two ways this can end.
        if first[4] == 0:
            print(SEV_BAD + "         采样时 focus=0 —— 窗口不在前台。FLIP_DISCARD 交换链"
                  "（BufferCount=3）在窗口失焦/被遮挡时 Present 会永久阻塞，而 v0.71 之前"
                  "全工程没有一处焦点处理（GetForegroundWindow / IsIconic / ACTIVATEAPP 均 0 处）。")
            note(SEV_BAD, "卡死发生在窗口失焦状态（focus=0）—— 焦点 / Present 死锁")
        note(SEV_BAD, "渲染线程卡死在 '%s'（约 %.1f 秒）——这是本次跑真正的故障点" % (first[3], dur))

    print()
    print("  最后 10 个 tick（墙钟 / frames / silent / focus / stage / fence / stim）：")
    for r in recs[-10:]:
        fen = ("%s/%s" % (r[8], r[9])) if r[8] is not None else "-"
        print("    %-12s fields=%-6d silent=%-8d focus=%-3s fence=%-12s stim=%-5s stage=%s%s"
              % (r[6] or "?:?:?.???", r[1], r[2], (r[4] if r[4] >= 0 else "?"), fen,
                 (r[7] if r[7] is not None else "-"), r[3],
                 "  <== 卡死" if r[5] else ""))


# ------------------------------------------------------------------ identity
def part_identity(lines):
    section("1. run identity - which build / which ini / which dll")

    for l in grab(r"RUN START", lines)[:1]:
        print(SEV_INFO + l[2])
    for l in grab(r"diag active", lines)[:1]:
        print(SEV_INFO + l[2])
    for l in grab(r"\[XRAY\] INI", lines)[:1]:
        print(SEV_INFO + l[2])
    else_hits = grab(r"\[XRAY\] INI MISSING", lines)
    for l in else_hits[:1]:
        print(SEV_BAD + l[2])
        note(SEV_BAD, "INI 没读到 —— 全部参数都是默认值，日志与你的配置无关")

    # build identity: which generation of probes is present
    if grab(r"\[XRAY\] WATCHDOG started", lines):
        print(SEV_INFO + "v0.62 看门狗已启动（可从独立文件判定渲染线程是否卡死）")
    else:
        print(SEV_WARN + "日志里没有 WATCHDOG started → 跑的不是 v0.62")
        note(SEV_WARN, "不是 v0.62 —— 卡死时不会留下任何证据")

    stale = []
    for name in ("MOTION probe", "RESET probe", "[Streamline] constants: ok="):
        if grab(re.escape(name), lines):
            stale.append(name)
    if stale:
        print(SEV_BAD + "日志里出现了更早版本的探针串 " + ", ".join(stale))
        note(SEV_BAD, "旧 DLL 仍在生效（检查部署副本）")

    if not grab(r"RUN START", lines):
        note(SEV_WARN, "没有 RUN START 行 —— 插件版本早于 v0.61，下面的判据可能不全")


# ------------------------------------------------------------------ env
def part_env(lines):
    section("2. 显示 / DPI 对齐（Independent Flip 的硬前提）")
    l = last(r"\[XRAY\] env:", lines)
    if not l:
        if grab(r"ForceBorderless: window", lines):
            print(SEV_WARN + "无 [XRAY] env 行，但有旧版 ForceBorderless 行：")
            for x in grab(r"ForceBorderless: window", lines)[:1]:
                print("         " + x[2])
            note(SEV_WARN, "无法判定 swapchain/显示模式是否对齐 —— 需要 v0.61 的 env 行")
        return
    print(SEV_INFO + l[2])

    def num(pat):
        m = re.search(pat, l[2])
        return int(m.group(1)) if m else None

    vw, vh = num(r"virtual=(\d+)x(\d+)"), num(r"virtual=\d+x(\d+)")
    pw, ph = num(r"physical=(\d+)x(\d+)"), num(r"physical=\d+x(\d+)")
    sw, sh = num(r"swapchain=(\d+)x(\d+)"), num(r"swapchain=\d+x(\d+)")
    aware = num(r"dpiAware=(\d)")
    rend = re.search(r"render=([\d.]+)", l[2])
    rend = float(rend.group(1)) if rend else None

    if None in (pw, ph, sw, sh):
        return
    if (sw, sh) != (pw, ph):
        print(SEV_BAD + "swapchain %dx%d != 显示模式 %dx%d → 破坏 Independent Flip，pacer 失节拍，必然闪"
              % (sw, sh, pw, ph))
        note(SEV_BAD, "swapchain/显示模式不一致 → 呈现链问题（不是帧生成本身）")
    else:
        print(SEV_OK + "swapchain == 显示模式（%dx%d）→ Independent Flip 前提成立" % (pw, ph))

    if (vw, vh) != (pw, ph):
        print(SEV_WARN + "进程是 DPI 虚拟化的（virtual=%dx%d physical=%dx%d, dpiAware=%s）"
              % (vw, vh, pw, ph, aware))
        print("          → 日志里任何 window/rect/GetSystemMetrics 数值都是缩放后的；"
              "不要直接拿来和 swapchain 比大小")
    else:
        print(SEV_OK + "无 DPI 缩放（进程看到的尺寸 == 物理尺寸）")

    if rend:
        print(SEV_INFO + "渲染分辨率比例 = %.4f（引擎按此比例渲染，再放大到输出）" % rend)
        if rend < 0.5:
            print(SEV_WARN + "渲染比例低到 %.2f —— 4K 下等于引擎只画 %dx%d，"
                  "插帧还要按 4K 生成，GPU 成本会被插帧放大" % (rend, int((pw or 0) * rend), int((ph or 0) * rend)))


# ------------------------------------------------------------------ menu
def part_menu(lines):
    section("3. 菜单切换时间线")
    edges = grab(r"\[XRAY\] MENU EDGE", lines)
    if not edges:
        print(SEV_WARN + "没有 MENU EDGE 行（菜单从未切换，或版本早于 v0.61）")
        note(SEV_WARN, "菜单没被采样到 —— 至少在主菜单停 10 秒再进游戏")
        return
    for l in edges[:20]:
        print("  %s  %s" % (l[0], l[2]))
    if len(edges) > 20:
        print("  ... 共 %d 条" % len(edges))
    menus = [e for e in edges if "open=1" in e[2]]
    if not menus:
        print(SEV_WARN + "从未检测到菜单打开 —— 停在主菜单更久一点，否则菜单路径无法判定")


# ------------------------------------------------------------------ heartbeat
HB_FIELDS = [
    ("serial", r"serial=(\d+)"),
    ("menu", r"menu=(\d+)"),
    ("world", r"world=(\d+)"),
    ("edges", r"edges=(\d+)"),
    ("resetTrue", r"resetTrue=(\d+)"),
    ("menuOpen", r"menuOpen=(\d)"),
    ("reset", r" reset=(\d)"),
    ("constsOk", r"consts ok=(\d+)"),
    ("constsFail", r"consts fail=(\d+)"),
    ("lastR", r"lastR=(-?\d+)"),
    ("mvecScale", r"mvecScale=\(([-\d.]+),([-\d.]+)\)"),
    ("flags", r"flags=(0x[0-9a-fA-F]+)"),
    ("jitter", r"jitter=\(([-\d.]+),([-\d.]+)\)"),
    ("clipDev", r"clipDev=([-\d.]+)"),
    ("realMs", r"real=([-\d.]+)ms"),
    ("curVP", r"curVP=([-\d.]+)"),
    ("prevVP", r"prevVP=([-\d.]+)"),
    ("pos", r"pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)"),
    ("prevPos", r"prevPos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)"),
    # ---- v0.62 ----
    ("dtMin", r"dt min/avg/max=([-\d.]+)/"),
    ("dtAvg", r"dt min/avg/max=[-\d.]+/([-\d.]+)/"),
    ("dtMax", r"dt min/avg/max=[-\d.]+/[-\d.]+/([-\d.]+)ms"),
    ("winN", r"ms n=(\d+)"),
    ("capUs", r"capUs=(\d+)"),
    ("multAcc", r"mult\(acc/pres\)=(\d+)/"),
    ("multPres", r"mult\(acc/pres\)=\d+/(\d+)"),
    ("longFrames", r"longFrames=(\d+)"),
    # ---- v0.64 ----
    ("camOk", r"cam\(ok/inv\)=(\d+)/"),
    ("camInv", r"cam\(ok/inv\)=\d+/(\d+)"),
    # ---- v0.65: reprojection source ----
    ("reprojSource", r"reproj src=(\w+)"),
    ("engPrevEq", r"engPrevEqCur=(\d+)/"),
    ("engPrevTot", r"engPrevEqCur=\d+/(\d+)"),
    ("engPrevZero", r"engPrevZero=(\d+)"),
    ("frozen", r"frozen=(\d+)"),
    ("dvdOk", r"dvd\(ok/used\)=(\d+)/"),
    ("dvdUsed", r"dvd\(ok/used\)=\d+/(\d+)"),
    ("dvdErr", r"err=([-\d.eE+]+)"),
    ("curMag", r"curMag=([-\d.eE+]+)"),
    ("engPrevMag", r"engPrevMag=([-\d.eE+]+)"),
    ("clipDevMax", r"clipDevMax=([-\d.]+)"),
    ("histHit", r"hist\(hit/miss\)=(\d+)/"),
    ("histMiss", r"hist\(hit/miss\)=\d+/(\d+)"),
    ("tid", r"tid=(0x[0-9a-fA-F]+)"),        # legacy (pre-v0.66) sentinel
    # ---- v0.66: determinant guard + per-tid call counting ----
    ("detMin", r"det\(min/max\)=([-\d.eE+]+)/"),
    ("detMax", r"det\(min/max\)=[-\d.eE+]+/([-\d.eE+]+)"),
    ("detGuard", r"detGuard=(\d+)"),
    # ---- v0.67: camera snapshot continuity gate ----
    ("detHold", r"detHold=(\d+)"),
    ("snapAcc", r"snap\(acc/jmp/re/zero/arr\)=(\d+)/"),
    ("snapJmp", r"snap\(acc/jmp/re/zero/arr\)=\d+/(\d+)/"),
    ("snapRelock", r"snap\(acc/jmp/re/zero/arr\)=\d+/\d+/(\d+)/"),
    ("snapZero", r"snap\(acc/jmp/re/zero/arr\)=\d+/\d+/\d+/(\d+)/"),
    ("snapArr", r"snap\(acc/jmp/re/zero/arr\)=\d+/\d+/\d+/\d+/(\d+)"),
    ("snapDistLast", r"dist\(last/acc\)=([-\d.]+)/"),
    ("snapDistAcc", r"dist\(last/acc\)=[-\d.]+/([-\d.]+)"),
    ("tidA", r"tid\(a/b/c\)=(0x[0-9a-fA-F]+)/"),
    ("tidB", r"tid\(a/b/c\)=0x[0-9a-fA-F]+/(0x[0-9a-fA-F]+)"),
    ("tidCallsA", r"calls=(\d+)/"),
    ("tidCallsB", r"calls=\d+/(\d+)/"),
]
HB_HIST = [
    ("presentedAll", r"presented all=([\d/]+)"),
    ("presentedWorld", r"world=([\d/]+) menu="),
    ("presentedMenu", r"menu=([\d/]+) \|"),
]


def parse_hist(s):
    return [int(x) for x in s.split("/")]


def mode_of(h):
    best = 0
    for i, v in enumerate(h):
        if v > h[best]:
            best = i
    return best


def part_heartbeat(lines):
    section("4. 心跳（run 内的样本）")
    hbs = grab(r"\[XRAY\] serial=", lines)
    if not hbs:
        print(SEV_BAD + "没有任何 [XRAY] 心跳行")
        note(SEV_BAD, "心跳缺失 —— 说明帧生成路径根本没走到 slSetConstants（或版本早于 v0.61）")
        return
    print(SEV_INFO + "共 %d 个样本，下面是最后一个：" % len(hbs))
    l = hbs[-1]
    print("         " + l[2])

    # v0.69: cross-reference how far the captured camera actually moved, so the
    # two verdicts below cannot fire on a LEGITIMATELY frozen camera.
    #   clipDevMax is max|clipToPrevClip - I|. An identity matrix means "the
    #   camera did not move", which is CORRECT when it genuinely did not, so the
    #   number alone is not a defect signal -- it only means something once the
    #   camera is known to be moving. Same for "engine viewProj frozen".
    #   The [CAM] acc lines are printed >= 0.25 s apart and carry the accepted
    #   camera's world position, so the distance between the last two is the
    #   travel over that interval. A walking player covers ~100 units/s, so
    #   0.5 units per 0.25 s window is a safe "essentially stationary" line.
    # 2026-09-17 23:07: the reader reported both as problems while the camera had
    # moved 0.05 units across the whole logged window -- both were false alarms.
    cam_step = None
    _accs = [ln for _t, _v, ln in lines if "[CAM] acc" in ln]
    if len(_accs) >= 2:
        def _pos(ln):
            m = re.search(r"pos=\(([-\d.]+),([-\d.]+),([-\d.]+)\)", ln)
            return tuple(float(m.group(i)) for i in (1, 2, 3)) if m else None
        a, b = _pos(_accs[-2]), _pos(_accs[-1])
        if a and b:
            cam_step = sum((b[i] - a[i]) ** 2 for i in range(3)) ** 0.5
    cam_static = (cam_step is not None and cam_step < 0.5)

    vals = {}
    for name, pat in HB_FIELDS:
        m = re.search(pat, l[2])
        if not m:
            continue
        g = m.groups()
        vals[name] = g[0] if len(g) == 1 else g

    for name, pat in HB_HIST:
        m = re.search(pat, l[2])
        if m:
            vals[name] = parse_hist(m.group(1))

    print()
    print("  ``` 解析结果")
    for k in ("serial", "menu", "world", "edges", "resetTrue", "menuOpen", "reset",
              "constsOk", "constsFail", "lastR", "mvecScale", "flags", "jitter",
              "realMs", "clipDev", "curVP", "prevVP", "pos", "prevPos",
              "dtMin", "dtAvg", "dtMax", "winN", "capUs", "multAcc", "multPres",
              "longFrames", "camOk", "camInv",
              "reprojSource", "engPrevEq", "engPrevTot", "engPrevZero", "frozen",
              "dvdOk", "dvdUsed", "dvdErr", "curMag", "engPrevMag", "clipDevMax",
              "histHit", "histMiss", "tid",
              "detMin", "detMax", "detGuard",
              "tidA", "tidB", "tidCallsA", "tidCallsB"):
        if k in vals:
            print("    %-12s %s" % (k, vals[k]))

    # histogram table
    if "presentedAll" in vals:
        allh = vals["presentedAll"]
        wh = vals.get("presentedWorld", [0] * 8)
        mh = vals.get("presentedMenu", [0] * 8)
        print()
        print("    presented-per-real-frame 直方图（索引=每真实帧实际呈现的帧数）")
        print("      %-6s %-10s %-10s %-10s" % ("value", "all", "world", "menu"))
        for i in range(8):
            if allh[i] or wh[i] or mh[i]:
                print("      %-6d %-10d %-10d %-10d" % (i, allh[i], wh[i], mh[i]))

    # ---- derived checks
    print()
    cf, co = vals.get("constsFail"), vals.get("constsOk")
    if cf is not None:
        if cf == 0:
            print(SEV_OK + "constants 全部被接受（ok=%s fail=0）→ 帧令牌在推进" % co)
        else:
            print(SEV_BAD + "constants 有 %s 次被拒（lastR=%s）→ 每帧常量没刷新"
                  % (cf, vals.get("lastR")))
            if vals.get("lastR") == "27":
                print("         lastR=27 = eErrorDuplicatedConstants → 帧槽不推进（孤儿帧号/令牌）")
            note(SEV_BAD, "slSetConstants 被拒 → 生成帧用过期相机/抖动重投影 → 闪")

    rt, edges = vals.get("resetTrue"), vals.get("edges")
    if rt is not None and edges is not None:
        try:
            if int(rt) <= int(edges) + 2:
                print(SEV_OK + "reset 是边沿触发（resetTrue=%s，菜单切换 %s 次）" % (rt, edges))
            else:
                print(SEV_BAD + "reset 疑似每帧置位（resetTrue=%s >> 切换 %s 次）→ v0.59 未生效"
                      % (rt, edges))
                note(SEV_BAD, "reset 每帧置位 → DLSS-G 每帧丢历史 → 静止画面也闪")
        except ValueError:
            pass

    # ---- v0.62: pacing / limiter discriminator
    try:
        dtmin, dtavg, dtmax = (float(vals.get("dtMin", 0)), float(vals.get("dtAvg", 0)),
                               float(vals.get("dtMax", 0)))
        cap = int(vals.get("capUs", 0))
        n = int(vals.get("winN", 0))
    except (TypeError, ValueError):
        dtmin = dtavg = dtmax = 0.0
        cap = 0
        n = 0

    if n and dtavg > 0:
        print()
        print(SEV_INFO + "真实帧间隔窗口：min=%.2f avg=%.2f max=%.2f ms（%d 帧）"
              % (dtmin, dtavg, dtmax, n))
        spread = (dtmax - dtmin) / dtavg if dtavg else 0.0
        # v0.63: the limiter paces PRESENTED (flip) frames, so the value that matters
        # is not "dt / cap" (that integer is just the flips-per-real-frame count and
        # is 4 both before and after the fix). What matters is whether the cap itself
        # is the right size: it must be 1000000/(refresh-1). A cap that is ~multiplier
        # times too large means the multiplier was divided out twice and the render
        # side collapses to refresh / multiplier^2.
        refresh_hz = 0.0
        cap_variant = ""
        _hit = last(r"Reflex (FLIP|render) cap =", lines)
        if _hit:
            m = re.search(r"Reflex (FLIP|render) cap = (\d+) fps \((\d+)us\)\s*-\s*"
                          r"(?:panel\s*)?([\d.]+)Hz", _hit[2])
            if m:
                cap_variant = m.group(1)
                refresh_hz = float(m.group(4))

        if cap > 0:
            capms = cap / 1000.0
            capfps = 1000000.0 / cap
            flips = vals.get("multPres") or vals.get("multAcc")
            flips = int(flips) if flips not in (None, "") else 0
            realfps = (1000.0 / dtavg) if dtavg else 0.0
            presfps = realfps * flips if flips else realfps
            print(SEV_INFO + "下发上限 = %.2f ms/flip（capUs=%d = %.1f fps），每真实帧 %s 个 flip"
                  % (capms, cap, capfps, flips or "?"))
            print(SEV_INFO + "反推：真实 %.2f fps → 上屏 %.2f fps（窗口抖动 %.1f%%）"
                  % (realfps, presfps, spread * 100))
            if cap_variant == "render":
                print(SEV_WARN + "日志里是旧字样 'Reflex render cap' → 这是 v0.54~v0.62 的 build，"
                      "上限是按'渲染帧率'反推的（已修）")
            if refresh_hz > 0:
                expect = 1000000.0 / (refresh_hz - 1.0)
                if cap > expect * 1.5:
                    print(SEV_BAD + "上限 %d us，但正确值应是 %d us（= 1000000/(%.0fHz−1)）"
                          "→ 大了 %.1f 倍 ≈ 倍率 ⇒ **倍率被除了两次**"
                          % (cap, round(expect), refresh_hz, cap / expect))
                    print("         限速器限的是上屏 flip 节拍，每真实帧要发 %s 个 flip，"
                          "所以真实帧率 = 刷新率 / 倍率² = %.2f fps" % (flips or "N", realfps))
                    note(SEV_BAD, "真实帧率塌成 刷新率/倍率² ⇒ 把 ReflexFpsLimit 设为 刷新率−1"
                         "（或 0 让它自动算）后重跑")
                else:
                    print(SEV_OK + "上限 %d us ≈ 正确值 %d us（1000000/(%.0fHz−1)）"
                          % (cap, round(expect), refresh_hz))
                    if realfps < (refresh_hz / (flips or 1)) * 0.6 and spread < 0.05:
                        print(SEV_BAD + "上限值正确，但真实帧率 %.2f fps 远低于应有值 %.2f fps"
                              "（=%.0fHz/%s）且抖动≈0 → 还有别的节流点"
                              % (realfps, refresh_hz / (flips or 1), refresh_hz, flips or "N"))
                    elif spread >= 0.10:
                        print(SEV_WARN + "真实帧率 %.2f fps 低于应有值 %.2f fps，但帧间隔在波动"
                              "（%.1f%%）→ 这一次是负载吃了时间（GPU/ENB），不是硬限速"
                              % (realfps, refresh_hz / (flips or 1), spread * 100))
                    else:
                        print(SEV_OK + "真实帧率 %.2f fps（应有 %.2f fps）在合理范围"
                              % (realfps, refresh_hz / (flips or 1)))
            elif spread < 0.05 and realfps and capfps and abs(presfps - capfps) < capfps * 0.15:
                print(SEV_WARN + "读不到刷新率，无法判定上限是否偏大；但上屏 %.2f fps ≈ 上限 %.2f fps"
                      " 且抖动 %.1f%% ⇒ 节拍由限速器主导" % (presfps, capfps, spread * 100))
        else:
            print(SEV_INFO + "没有下发 Reflex 上限（capUs=0）")
        if dtmax > 300.0:
            print(SEV_WARN + "窗口内最长一帧 %.1f ms —— 载入或卡顿，画面会停在旧帧上" % dtmax)

    lf = vals.get("longFrames")
    if lf is not None and int(lf) > 0:
        print(SEV_WARN + "本窗口有 %s 帧超过 300ms（详见 LONG FRAME 行：那是「画面冻结但插帧还在跑」的来源）" % lf)
        note(SEV_WARN, "存在 >300ms 的长帧 —— 冻结帧期间 DLSS-G 仍在输出插帧")

    ma, mp = vals.get("multAcc"), vals.get("multPres")
    if ma and mp:
        print(SEV_INFO + "倍率：请求接受=%s，运行时实测呈现=%s" % (ma, mp))

    # frame time
    ms = vals.get("realMs")
    if ms is not None:
        try:
            msf = float(ms)
            print()
            print(SEV_INFO + "真实帧耗时（窗口平均）= %.2f ms" % msf)
            cdv = vals.get("clipDev")
            if cdv is not None:
                if float(cdv) < 1e-4:
                    print(SEV_WARN + "clipDev≈0 → 相机项被丢弃：静止或菜单里属正常；"
                          "移动中仍为 0 则是相机矩阵没喂进去")
                else:
                    print(SEV_OK + "clipDev=%.4f → 相机矩阵是活的" % float(cdv))
        except ValueError:
            pass

    # v0.65: 重投影数据源 —— 这一节回答"DLSS-G 到底有没有收到相机运动"
    eq = vals.get("engPrevEq")
    tot2 = vals.get("engPrevTot")
    zero = vals.get("engPrevZero")
    frozen = vals.get("frozen")
    src = vals.get("reprojSource")
    dvdok = vals.get("dvdOk")
    dvdused = vals.get("dvdUsed")
    dvderr = vals.get("dvdErr")
    cdmax = vals.get("clipDevMax")
    hit = vals.get("histHit")
    miss = vals.get("histMiss")

    if eq is not None and tot2 is not None:
        e2, t2 = int(eq), int(tot2)
        z = int(zero) if zero is not None else 0
        print()
        print(SEV_INFO + "重投影数据源：本帧 src=%s | 引擎 prev 累计 ==cur %d 次 / 共 %d 次观测；零矩阵 %d 次"
              % (src, e2, t2, z))
        if t2 > 0 and e2 == t2 and z == 0:
            print(SEV_BAD + "引擎的 CameraPreviousViewProjUnjittered 与当前 viewProj **完全相同** —— "
                  "它不是「上一帧」，引擎根本没在维护它")
            print("          ⇒ clipToPrevClip = inv(cur)×prev = 单位矩阵 ⇒ DLSS-G 被反复告知「相机没动」")
            print("          ⇒ 菜单（相机静止）正常、一进世界（相机开始动）就闪 —— 这就是本轮根因")
            note(SEV_BAD, "引擎 prev viewProj 恒等于 cur（%d/%d）：相机运动信息丢失；"
                 "v0.65 已改为自维护上一帧 viewProj 历史" % (e2, t2))
        elif z == t2:
            print(SEV_WARN + "引擎的 prev viewProj 全程是零矩阵 —— 无效输入，v0.65 同样不再采信它")
            note(SEV_BAD, "引擎 prev viewProj 全为零矩阵（%d 次）" % z)

    if vals.get("curMag"):
        print(SEV_INFO + "curMag=%s  engPrevMag=%s （矩阵幅度；零矩阵会 ~0）"
              % (vals.get("curMag"), vals.get("engPrevMag")))

    if frozen is not None:
        fr = int(frozen)
        if fr > 120 and cam_static:
            print(SEV_INFO + "引擎 viewProj 连续 %d 帧位级不变 —— 但捕获到的相机在这段时间"
                  "**确实静止**（窗口内位移 %.2f 单位），冻结是正确状态（加载界面 / 菜单 / 站住不动）。"
                  % (fr, cam_step))
        elif fr > 120:
            print(SEV_BAD + "引擎 CameraViewProjUnjittered 连续 %d 帧位级不变（冻结）" % fr)
            print("          派生源：校验=%s 匹配=%s 已用=%s 帧 (err=%s)"
                  % ("是" if dvdok else "否", dvdok, dvdused, dvderr))
            if int(dvdused or 0) == 0:
                note(SEV_BAD, "引擎 viewProj 冻结 %d 帧且派生源未启用 —— 重投影仍是单位矩阵" % fr)
            else:
                print(SEV_OK + "已切到派生源（inv(CameraViewInverse)×CameraProjUnjittered）")
        else:
            print(SEV_INFO + "引擎 viewProj 最长连续不变 %d 帧（<30 视为活的；>=30 会切派生源）" % fr)

    if cdmax is not None:
        cdm = float(cdmax)
        print()
        if cdm < 1e-6 and cam_static:
            print(SEV_INFO + "本窗口 clipDevMax = %.6f —— 单位矩阵，但捕获到的相机在这段时间"
                  "**确实静止**（窗口内位移 %.2f 单位）⇒ 这是正确结果，不是缺陷。" % (cdm, cam_step))
            print("          该判据只在相机真的在动时才有意义；要复现缺陷必须进世界走一走再退出。")
        elif cdm < 1e-6:
            print(SEV_BAD + "本窗口 clipDevMax = %.6f ⇒ 交给 DLSS-G 的重投影矩阵恒为单位矩阵" % cdm)
            print("          ⇒ 相机项被丢掉，而相机确实在动 —— 还没修好。")
            note(SEV_BAD, "clipDevMax≈0 且相机在动：重投影矩阵无相机运动")
        elif cdm < 0.01:
            print(SEV_WARN + "本窗口 clipDevMax = %.6f —— 偏小；静止时正常，移动中则说明运动量没进来" % cdm)
        else:
            print(SEV_OK + "本窗口 clipDevMax = %.6f ⇒ 重投影矩阵真的带相机运动（DLSS-G 能跟随移动）" % cdm)
            note(SEV_OK, "clipDevMax=%.6f：重投影带真实相机运动（v0.65 生效）" % cdm)

    if hit is not None and miss is not None:
        h2, m2 = int(hit), int(miss)
        t3 = h2 + m2
        if t3 > 0:
            print(SEV_INFO + "自维护历史：命中 %d / 缺失 %d（缺失 %.1f%%）" % (h2, m2, 100.0 * m2 / t3))
            if m2 * 4 > t3:
                print(SEV_BAD + "缺失占比 %.1f%% 偏高 —— cur 没能每帧提供有效矩阵" % (100.0 * m2 / t3))
                note(SEV_BAD, "自维护重投影历史缺失 %.1f%%" % (100.0 * m2 / t3))

    # ---- v0.66：行列式守卫 + per-tid 计数（取代旧的哨兵语义）----
    dg = vals.get("detGuard")
    ca, cb = vals.get("tidCallsA"), vals.get("tidCallsB")
    if ca is not None and cb is not None:
        ca, cb = int(ca), int(cb)
        ta, tb = vals.get("tidA"), vals.get("tidB")
        print()
        # 判据修正（v0.69）：并发 = **两个线程各自都在持续调用**。
        # 只要有一方调用次数极少（<=10），那它就是初始化期的一次性线程交接，
        # 不是并发 —— 旧判据只看 b 的次数，会把「1 次交接 + 150 次持续」误报成并发。
        both_live = ca > 10 and cb > 10
        handoff = (ca <= 10 < cb) or (cb <= 10 < ca)
        if both_live:
            print(SEV_BAD + "两个线程都在持续调 slSetConstants（a=%s 调 %d 次，b=%s 调 %d 次）"
                  " ⇒ 共享静态历史会被交错污染（v0.66 已把历史改成 thread_local）" % (ta, ca, tb, cb))
            note(SEV_BAD, "多线程持续调用 slSetConstants（a=%d, b=%d）" % (ca, cb))
        elif handoff:
            print(SEV_INFO + "线程 %s 调 %d 次、线程 %s 调 %d 次 —— 少数派是**初始化期的一次性"
                  "线程交接**（当前线程只出现在启动阶段），不是并发；持续调用的是单一线程。"
                  "（旧哨兵探针会把它误报成多线程）" % (ta, ca, tb, cb))
            print("          注：一次性交接线程仍会在同帧内与 Present 线程交替取 frame token，"
                  "这会影响 marker/Evaluate 的 token 配对，但**不是** slSetConstants 的并发污染。")
        elif cb > 0 or ca > 0:
            print(SEV_OK + "只有单线程调用 slSetConstants（%s，%d 次）—— 无并发污染" % (ta, ca))
    if dg is not None:
        dg = int(dg)
        dmin, dmax = vals.get("detMin"), vals.get("detMax")
        if dmin is not None and dmax is not None:
            print(SEV_INFO + "clipToPrev 行列式范围 = %s .. %s（合法重投影必须 ≈ 1）" % (dmin, dmax))
        if dg > 0:
            print(SEV_BAD + "有 %d 帧的重投影矩阵在数学上非法（det 不在 [0.5,2.0]）"
                  " ⇒ v0.66 已把它们钳成单位矩阵" % dg)
            note(SEV_BAD, "clipToPrev 行列式越界 %d 帧：矩阵不是合法变换，DLSS-G 收到错误位移" % dg)
        else:
            print(SEV_OK + "无非法的重投影矩阵（detGuard=0）")

    # 旧日志（v0.65 及以前）的 tid 是哨兵语义
    tid = vals.get("tid")
    if tid and tid.lower() == "0xffffffff":
        print(SEV_WARN + "[旧日志] tid=0xFFFFFFFF 是 v0.65 的哨兵，分不清交接与并发 —— "
              "v0.66 起改 per-tid 计数")

    # v0.64 的 cam(ok/inv) 现在语义是「cur 矩阵是否可用」，正常应接近 0 无效。
    co, ci = vals.get("camOk"), vals.get("camInv")
    if co is not None and ci is not None:
        co2, ci2 = int(co), int(ci)
        if co2 + ci2 > 0:
            if vals.get("reprojSource") is None:
                print(SEV_INFO + "[旧版日志] cam(ok/inv)=%d/%d 的语义是「引擎 prev 矩阵可用性」；"
                      "v0.64 的钳制把它换成单位矩阵，等价于「相机没动」——所以那时修不好闪"
                      % (co2, ci2))
            else:
                print(SEV_INFO + "cur 矩阵可用性：有效 %d / 无效 %d（v0.65 起这是「当前帧矩阵」的可用性，"
                      "不再是 prev 的）" % (co2, ci2))

    # what multiplier the runtime accepted (from the 2 s FPS probe)
    want = None
    fp = grab(r"FPS probe", lines)
    if fp:
        m = re.search(r"accepted=(\d+)", fp[-1][2])
        if m:
            want = max(1, int(m.group(1)))
        print(SEV_INFO + "最后一次 FPS 探针：%s" % fp[-1][2])

    if "presentedWorld" in vals and "presentedAll" in vals:
        wh = vals["presentedWorld"]
        mh = vals["presentedMenu"]
        wm, mm = mode_of(wh), mode_of(mh)
        nw, nm = sum(wh), sum(mh)
        print()
        print(SEV_INFO + "世界帧 %d 个，众数 = %d 帧/真实帧；菜单帧 %d 个，众数 = %d" % (nw, wm, nm, mm))
        if want:
            print(SEV_INFO + "本次运行时被接受（accepted）= %d" % want)
        if nw > 60 and want and wm != want:
            print(SEV_BAD + "世界里只跑出 %d 帧/真实帧，而接受了 %d → 多倍帧生成没真正输出"
                  % (wm, want))
            note(SEV_BAD, "世界中的实际倍率 != 接受值 → MFG 没在输出")
        elif nw > 60:
            print(SEV_OK + "世界倍率符合请求")
        if nm > 20:
            if want and mm >= want and want > 1:
                print(SEV_BAD + "菜单里仍在生成 %d 帧/真实帧 → 菜单没有被节流（v0.60 那一刀无效）" % mm)
                note(SEV_BAD, "菜单未被节流 → 菜单 UI 被当 3D 内容插值")
            else:
                print(SEV_OK + "菜单已被节流（众数 %d）" % mm)
        else:
            print(SEV_WARN + "菜单只采到 %d 帧 → 判定不了，请在主菜单多停 10 秒" % nm)


# ------------------------------------------------------------------ verdicts
def part_cam(lines):
    """v0.67: per-arrival camera snapshot gate -- is the snapshot stream ONE camera?"""
    events, raws, accs, lastHB = [], [], [], None
    for ts, _lv, ln in lines:
        if "[CAM]" in ln:
            m = re.search(r"\[CAM\] #(\d+) (JUMP rejected|RELOCK|rejected)(.*)$", ln)
            if m:
                events.append((ts, int(m.group(1)), m.group(2), m.group(3).strip()))
            elif "[CAM] acc" in ln:
                accs.append(ln[ln.index("[CAM] acc"):].strip())
            elif "[CAM] raw" in ln:
                raws.append(ln[ln.index("[CAM] raw"):].strip())
        if "[XRAY] serial" in ln:
            lastHB = ln
    if not events and not raws and not accs:
        return
    section("相机快照闸门（v0.67）")
    n_jump = sum(1 for e in events if e[2] == "JUMP rejected")
    n_relock = sum(1 for e in events if e[2] == "RELOCK")
    n_bad = sum(1 for e in events if e[2] == "rejected")
    print(SEV_INFO + "到达快照事件：JUMP 拒绝 %d / RELOCK %d / 空快照 %d"
          % (n_jump, n_relock, n_bad))
    if n_jump > 0:
        # 措辞修正（v0.69）：实测证明 raw 采样只有三个**常量桩**与真实相机交错，
        # 而被 AcceptedSnapshot 闸门接受的快照是**时间连续的真实相机**
        # （[CAM] acc 的 pos 连续变化、path 持续增长）。所以 JUMP 拒绝数大
        # 不代表"快照流是两个相机"，恰恰相反 —— 闸门正在把常量桩挡在外面。
        print(SEV_INFO + "闸门拒绝了 %d 份非连续快照。" % n_jump)
        print("         这些被拒的是**常量桩**（菜单 3D 背景相机 / UI 正交相机 / 无平移的"
              "遗留矩阵），它们与真实相机在同一个 perFrame 缓冲里**交错**出现 ——")
        print("         这正是闸门存在的意义。被接受的快照是连续的真实相机，"
              "（判据：看 [CAM] acc 的 pos 是否跨窗口连续变化 + path 是否增长，"
              "不要只看 move 字段，它只反映与上一份被接受快照的差）。")
        for ts, n, kind, rest in events[:5]:
            print("         %s #%d %s%s" % (ts, n, kind, rest[:110]))
        note(SEV_INFO, "闸门拒绝了 %d 份常量桩快照（不是「两组相机」——被接受的快照是连续的）"
             % n_jump)
    elif n_relock == 0 and n_bad == 0:
        print(SEV_OK + "没有出现相机跳变 —— 快照流是单一相机（闸门未触发）")
    if lastHB:
        vals = {}
        for name, pat in HB_FIELDS:
            m = re.search(pat, lastHB)
            if m:
                vals[name] = m.group(1)
        sa, sj = vals.get("snapAcc"), vals.get("snapJmp")
        if sa is not None and sj is not None:
            sa, sj = int(sa), int(sj)
            arr = vals.get("snapArr")
            print(SEV_INFO + "闸门计数：接受 %d / JUMP 拒绝 %d / 到达 %s%s"
                  % (sa, sj, arr, "（含被丢弃的）" if arr else ""))
            if sa > 0 and sj == 0:
                print(SEV_OK + "每一份到达的快照都被接受 -> cur/prev 来自同一相机，"
                      "det 应当回到 1.000")
            elif sj > 0 and sj >= sa:
                print(SEV_INFO + "拒绝数（%d）>= 接受数（%d）：被拒的常量桩到达频率高于真实相机。"
                      % (sj, sa))
                print("         这不是「闸门锁定了两个来源」—— 真实相机仍在被接受；"
                      "要去 [CAM] raw 看那几个**常量值**（pos=(-50,600,80) / (-160,160,128) / "
                      "(0,0,1)）就知道桩是哪几个。")
        dm, dh = vals.get("detMin"), vals.get("detMax")
        dg, dhold = vals.get("detGuard"), vals.get("detHold")
        if dg is not None:
            print(SEV_INFO + "守卫：det 范围 %s .. %s，触发 %s 次，其中 %s 次复用上一帧合法矩阵"
                  % (dm, dh, dg, dhold))
            if dg == "0":
                # det 判据修正（v0.69）：det(inv(cur) x prev) == 1 是**恒等式**，
                # 当 cur == prev 时恒成立，与单位矩阵、与真实两帧投影都成立。
                # 所以 detGuard=0 只能说明「守卫从未触发」，**不能**证明矩阵带真实运动。
                print(SEV_INFO + "det 全程在 [0.5,2.0] 内 —— 但注意：det(inv(cur) x prev)==1 "
                      "在 cur==prev 时是**恒等式**，单位矩阵与真实投影都满足。")
                print("         所以 det=1 不能区分「矩阵带运动」与「矩阵是单位矩阵」；"
                      "要判后者必须用 clipDevMax，且先证明相机在动。")
    if raws:
        print()
        print(SEV_INFO + "原始矩阵采样（共 %d 行，这里列前 12 行）：" % len(raws))
        for r in raws[:12]:
            print("         " + r[:200])
    if accs:
        print()
        print(SEV_INFO + "捕获层运动轨迹（[CAM] acc 共 %d 行；判定「被捕获的相机是否跟着玩家动」）"
              % len(accs))
        moves, paths = [], []
        for a in accs:
            m = re.search(r"move=([-\d.eE+]+) path=([-\d.eE+]+)", a)
            if not m:
                continue
            try:
                moves.append(float(m.group(1)))
                paths.append(float(m.group(2)))
            except ValueError:
                pass
        for a in accs[:3]:
            print("         前：" + a[:190])
        if paths:
            print(SEV_INFO + "move 最大 %.4f / path 最终 %.2f（单位：Skyrim world unit，人高约 100）"
                  % (max(moves), paths[-1]))
            for a in accs[-2:]:
                print("         后：" + a[:190])
            if paths[-1] < 0.5 and len(accs) >= 5:
                print(SEV_BAD + "被接受的相机在整场里累计只走了 %.2f 单位 —— 快照里的相机**不跟随玩家**。"
                      % paths[-1])
                print("         ⇒ 这是**捕获层**缺陷（读到的 perFrame 相机数据不是当前视角相机）。"
                      "重投影侧的任何修法（det 守卫 / 连续性闸门 / 换取源）都救不了它。")
                note(SEV_BAD, "捕获层缺陷：接受的快照累计位移仅 %.2f 单位（相机没跟着玩家动）" % paths[-1])
            else:
                print(SEV_OK + "被接受的相机累计走了 %.2f 单位 —— 快照的相机确实在动。"
                      % paths[-1])
                print("         此时若 clipDevMax 仍为 0.0000，问题才在重投影取源一侧。")


# --------------------------------------- v0.69 / v0.70 fix engagement
def part_fixes(lines):
    """Did the v0.69 / v0.70 fixes actually engage on this run?

    Both fixes are SUPPRESSIONS, so they are proven by what stops appearing.
    Each check below therefore also states the counter-evidence, otherwise the
    section would be unfalsifiable. The single most decisive pair is
    presentedMenu vs presentedWorld in the heartbeat (section 4): if the menu
    guard engages, presentedMenu collapses to 1 while presentedWorld stays at
    the accepted multiplier.
    """
    section("4b. v0.69 / v0.70 修复是否生效")

    # --- 1. NR x frame generation mutual exclusion (v0.69) ---------------
    sup = grab(r"DLSSNR suppressed", lines)
    # NOTE the real spelling: the running frame count is on the
    # "[FrameGen] DLSSNR: ... frames=N status=..." line, while the "[DLSSNR]"
    # prefix is only used by the interop/resource/saturation lines. A regex
    # looking for "[DLSSNR] frames=" matches nothing and reports "NR never ran",
    # which is the opposite of the truth. Both spellings are accepted here.
    nr_frames = []
    for ts, _lv, ln in lines:
        m = re.search(r"DLSSNR[:].*?\bframes=(\d+)", ln)
        if m:
            nr_frames.append((ts, int(m.group(1))))
    sat = grab(r"command contexts saturated", lines)

    if sup:
        print(SEV_OK + "NR×FG 互斥已生效（[FrameGen] DLSSNR suppressed 出现）：")
        print("         " + sup[-1][2][:200])
        if nr_frames:
            print(SEV_WARN + "  但之后仍有 [DLSSNR] frames 行（%d）—— 说明 FG 一度没在跑"
                  "（首帧 fgActive 还是 false），NR 抓住那个窗口跑了。正常，可忽略。" % nr_frames[-1][1])
    elif nr_frames:
        print(SEV_BAD + "NR×FG 互斥**没有**生效：[DLSSNR] frames 从 %d 涨到 %d，"
              "而 FG 同时在插帧。" % (nr_frames[0][1], nr_frames[-1][1]))
        print("         两个 temporal 处理器为同一帧写历史 = 直接闪烁源（v0.42 的退路就是回退互斥）。")
        note(SEV_BAD, "NR 与 FG 仍在串联（[DLSSNR] frames=%d）" % nr_frames[-1][1])
    else:
        print(SEV_INFO + "本次没有任何 [DLSSNR] 行 —— NR 全程未运行"
              "（互斥生效，或 NR 本来就是关的）")
    if sat:
        print(SEV_WARN + "NR 侧命令上下文饱和 x%d（NR 在跟 FG 抢 D3D12 上下文）" % len(sat))

    # --- 2. engine motion vectors: mv3D=0 is NOT a defect ----------------
    mv = grab(r"engineMvec=", lines)
    if mv:
        has_mv = "engineMvec=true" in mv[-1][2]
        if has_mv:
            print(SEV_OK + "引擎运动矢量可用（engineMvec=true）")
            print("         Transfusion [MOTION] 里的 mv3D=0 是**设计如此**，不是缺陷：插件把 mvec 当")
            print("         纹理参数传给 slEvaluateDLSSG，没有走 constants.motionVectors3D，所以那行必然是 0。")
            print("         判定运动矢量要认 engineMvec / mvecWrapped，不要认 mv3D。")
        else:
            print(SEV_BAD + "引擎运动矢量纹理没找到（engineMvec=false）→ 插帧只能靠相机重投影")
            note(SEV_BAD, "引擎 mvec 纹理不可用（engineMvec=false）")

    # --- 3. menu probe + guard observability (v0.70) --------------------
    probe = grab(r"MENU PROBE", lines)
    if probe:
        raw = probe[-1][2]
        print(SEV_INFO + "MENU PROBE：")
        print("         " + raw[raw.index("MENU PROBE"):][:230])
        m = re.search(r"ptr mainMenu=(\S+) \(lit=(\S+)\)", raw)
        if m:
            if m.group(1) == m.group(2):
                print(SEV_OK + "  InterfaceStrings 布局正确（mainMenu 指针 == 字面 \"Main Menu\" 的指针）")
                print("         ⇒ 若菜单开合边沿仍是 0，那是**真的没有菜单打开**，不是探针坏了。")
            else:
                print(SEV_WARN + "  InterfaceStrings 布局不匹配（两个指针不同）")
                print("         ⇒ 只有字面名那一半有效；v0.70 的双条件正是为这种情况准备的。")
        # v0.71e: "ui=0" is a PREFIX of "ui=0x7ff7..." -- the old test declared
        # every non-null singleton to be null (2026-09-17: the log printed
        # ui=0x7ff745c3ceb0 and the reader still said "RE::UI 单例为空", right
        # above its own line saying the layout was correct). Parse the value.
        mu = re.search(r"\bui=(0x[0-9a-fA-F]+|\d+)", raw)
        if mu is not None and int(mu.group(1), 0) == 0:
            print(SEV_BAD + "  RE::UI 单例为空 → 菜单检测整体失效，这是 CommonLib 地址/版本问题")
            note(SEV_BAD, "RE::UI 单例为空：菜单守卫不可能生效")
        elif mu is not None:
            print(SEV_OK + "  RE::UI 单例有效（ui=%s）—— 菜单检测可用" % mu.group(1))
    else:
        print(SEV_WARN + "没有 MENU PROBE 行 —— 探针没跑到，或 DLL 仍是 v0.69 以前的版本")
        note(SEV_WARN, "菜单探针无输出：菜单检测无从判定")

    edges = grab(r"MENU EDGE", lines)
    if edges:
        print(SEV_OK + "MENU EDGE x%d（菜单开合边沿有记录）" % len(edges))
        for e in edges[:6]:
            print("         %s %s" % (e[0], e[2][e[2].index("MENU EDGE"):][:120]))
    else:
        print(SEV_INFO + "没有 MENU EDGE 行 —— 本次运行菜单开合边沿为 0")

    run = grab(r"RUN TIME", lines)
    if run:
        print(SEV_INFO + "真实运行时间：" + run[-1][2].split("RUN TIME", 1)[-1].strip())


# ------------------------------------------------------------------ verdicts
# ------------------------------------------- v0.71 focus / present hang
def _secs(ts):
    """'HH:MM:SS.mmm' -> seconds, or None. Local to this section on purpose."""
    try:
        h, m, s = ts.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (ValueError, AttributeError):
        return None


def part_focus(lines):
    """v0.71: did this run end in a window-presentation hang?

    The 2026-09-17 23:40 session froze 55 ms after DirectionalMovement's WndProc
    logged "WM_ACTIVATEAPP: Game lost focus" - and that line is the LAST line in
    ANY log of that session. Five independent loggers stop in the same instant,
    audio keeps playing, and there is no crash, no WER report and no TDR (so no
    GPU reset). That combination is a Present() that never returns.

    Two file-level facts make it decidable without a debugger:
      * here: the last timestamp of this log vs the last "FOCUS lost" timestamp;
      * and the last write time of every OTHER plugin's log in the same folder.
        If several independent loggers stop within the same second, the frame
        loop itself stopped - which rules out "one plugin misbehaved".
    """
    section("4c. 焦点 / Present 死锁（v0.71）")

    foc = []
    for ts, _lv, ln in lines:
        if "[XRAY] FOCUS" in ln:
            foc.append((ts, ln[ln.index("[XRAY] FOCUS"):]))
    for ts, ln in foc:
        print(SEV_INFO + "%s %s" % (ts, ln[:170]))
    if not foc:
        print(SEV_INFO + "没有 FOCUS 行 —— 全程保持前台，或 DLL 早于 v0.71")
    else:
        lost = [f for f in foc if "lost" in f[1]]
        regained = [f for f in foc if "regained" in f[1]]
        if lost and len(lost) > len(regained):
            print(SEV_WARN + "失焦 %d 次、回到前台 %d 次 —— 结束在失焦状态。"
                  % (len(lost), len(regained)))

    off = grab(r"DLSSG mode -> OFF", lines)
    if off:
        print(SEV_OK + "失焦时已通知运行时停机（这是 DLSS-G 的硬性要求）：")
        print("         " + off[-1][2][:170])
    elif foc:
        print(SEV_WARN + "有 FOCUS 行但没有 'DLSSG mode -> OFF' —— 焦点停机没生效")

    # ---- 本日志是否在一行 FOCUS lost 之后戛然而止 ------------------------
    lost_ts = [f[0] for f in foc if "lost" in f[1]]
    if lost_ts and lines:
        gap = _secs(lines[-1][0]) - _secs(lost_ts[-1])
        if gap is not None and 0 <= gap <= 3.0:
            print(SEV_BAD + "日志在 FOCUS lost（%s）之后 %.2f 秒就结束了，最后一行是 %s"
                  % (lost_ts[-1], gap, lines[-1][0]))
            print("         ⇒ 渲染线程很可能卡死在失焦后的第一个 Present 上。")
            note(SEV_BAD, "本次以「失焦 → 日志停止」结束（%.2f 秒内）—— 焦点 / Present 死锁" % gap)

    # ---- 跨插件交叉验证：进程级停摆 vs 单个插件出问题 -------------------
    folder = os.path.dirname(WATCHDOG_LOG)
    rows = []
    try:
        for n in os.listdir(folder):
            if not n.lower().endswith((".log", ".txt")):
                continue
            if n.startswith("DynamicShaderFrameGen"):
                continue
            p = os.path.join(folder, n)
            try:
                rows.append((os.path.getmtime(p), n))
            except OSError:
                pass
    except OSError:
        rows = []
    print()
    if not rows:
        print(SEV_INFO + "读不到同目录其它插件的日志，跳过跨插件交叉验证")
        return
    rows.sort()
    newest = rows[-1][0]
    same = [r for r in rows if newest - r[0] <= 1.5]
    print("  同目录其它插件的日志最后写入时刻（独立线程 / 独立文件）：")
    for m_, n in rows[-6:]:
        mark = "   <<< 与最新同秒" if newest - m_ <= 1.5 else ""
        print("    %s  %s%s" % (time.strftime("%H:%M:%S", time.localtime(m_)), n, mark))
    if len(same) >= 3:
        print(SEV_BAD + "  %d 个互不相干的插件日志在同一秒内停摆 ⇒ 停的是整个进程的"
              "帧循环，不是某一个插件的问题" % len(same))
        print("         注意：这只说明「所有写日志的东西同时停了」，不说明为什么停。")
        print("         停在哪里、是 GPU 还是 CPU —— 看 0b 段的运行段表。")
        note(SEV_BAD, "%d 个插件的日志同秒停摆 —— 进程级停摆（原因见 0b 段的运行段表）" % len(same))
    else:
        print(SEV_INFO + "  只有 %d 个日志同时停摆 —— 不足以判定进程级停摆" % len(same))


def _parse_wd(path):
    """v0.73: the second copy of the watchdog regex is gone - both sections now use
    parse_wd_file(). Two hand-maintained regexes meant every field added to the
    line had to be added twice, and a missed one fails silently."""
    return parse_wd_file(path)


def _split_wd_runs(recs):
    """A new run = the frame counter went backwards."""
    runs = []
    cur = [recs[0]]
    for r in recs[1:]:
        if r["frames"] < cur[-1]["frames"] - 10:
            runs.append(cur)
            cur = [r]
        else:
            cur.append(r)
    runs.append(cur)
    return runs


def part_stalls():
    """v0.72: every run the watchdog ever saw, tabulated.

    This is the section that finds a freeze the frozen run's own log can no longer
    prove - the watchdog file is append-only, the plugin log is not.
    """
    section("0b. 全部运行段（看门狗是跨运行追加的，故障形状都在这里）")
    recs = _parse_wd(WATCHDOG_LOG)
    if not recs:
        print(SEV_WARN + "看门狗文件没有可解析的行")
        return
    runs = _split_wd_runs(recs)
    print(SEV_INFO + "共 %d 行 / %d 个运行段" % (len(recs), len(runs)))
    print()
    print("  %-3s %-7s %-8s %-10s %8s %8s %-6s %-16s %s"
          % ("#", "ticks", "dur_s", "lastFrame", "lastSil", "maxSil", "focus", "lastStage", "STALL"))
    for i, r in enumerate(runs):
        dur = (r[-1]["ms"] - r[0]["ms"]) / 1000.0
        maxsil = max(x["silent"] for x in r)
        stall = sum(1 for x in r if x["stalled"])
        flag = "   <<< 真的停过" if stall else ""
        print("  %-3d %-7d %-8.1f %-10d %8d %8d %-6d %-16s %-5d%s"
              % (i, len(r), dur, r[-1]["frames"], r[-1]["silent"], maxsil,
                 r[-1]["focus"], r[-1]["stage"][:16], stall, flag))

    # ---- the freeze shape, for the runs that actually stalled ------------
    for i, r in enumerate(runs):
        if not any(x["stalled"] for x in r):
            continue
        first = next(x for x in r if x["stalled"])
        idx = r.index(first)
        prev = r[idx - 1] if idx > 0 else None
        print()
        print(SEV_BAD + "运行段 #%d 卡死：" % i)
        if prev and prev["frames"] < 60:
            # v0.63 tightened the rule to frames>=60 for exactly this reason: the game
            # does not call Present at all during the initial load, so silent climbs for
            # ~20 s with frames pinned at 1. That is a load, not a freeze. Only a build
            # older than v0.63 (no warm gate) writes STALLED here.
            print("         （该段的 frames 只有 %d —— 装载期，游戏还没进帧循环。"
                  "v0.63 起判据要求 frames>=60，这是旧 build 的假警报，不是卡死）"
                  % prev["frames"])
        if prev:
            print("         最后一帧 %d（%s）→ 之后 silent 一直涨，%d 个 tick 报了 STALLED"
                  % (prev["frames"], prev["stage"][:24], sum(1 for x in r if x["stalled"])))
        print("         停止时 focus=%d（0 = 窗口不在前台），最后 stage=%s"
              % (first["focus"], first["stage"]))
        # fence values are the discriminator: frozen queues vs a CPU-side block
        fa = [x["f11"] for x in r[idx:] if x["f11"] is not None]
        fb = [x["f12"] for x in r[idx:] if x["f12"] is not None]
        stim = [x["stim"] for x in r[idx:] if x["stim"] is not None]
        if stim and stim[-1] > 0:
            # v0.73: the sampler only runs once a hang is suspected, so stim>0 means
            # these numbers are live samples taken during the stall itself.
            if stim[0] == stim[-1]:
                print(SEV_BAD + "         采样线程的 tick 在卡死期间没有增长（stim %d）"
                      " ⇒ **采样线程自己停在驱动调用里** = GPU/驱动级卡死" % stim[0])
            else:
                print(SEV_INFO + "         采样线程仍在推进（stim %d→%d）⇒ GPU 时间线是活的，"
                      "渲染线程卡在 CPU 侧代码" % (stim[0], stim[-1]))
            if fa and fb:
                print("         GPU 围栏 %d/%d → %d/%d（采样线程读到的值）"
                      % (fa[0], fb[0], fa[-1], fb[-1]))
        elif fa and fb:
            if fa[0] == fa[-1] and fb[0] == fb[-1]:
                print(SEV_BAD + "         GPU 围栏在整个卡死期间没有推进（fence %d/%d）"
                      " ⇒ 队列停了：跨队列/驱动级卡死" % (fa[0], fb[0]))
            else:
                print(SEV_INFO + "         GPU 围栏仍在推进（fence %d→%d）⇒ GPU 没停，"
                      "是渲染线程在 CPU 侧被挡住" % (fa[0], fa[-1]))
        else:
            print("         （该段没有 stim= / fence= 字段：DLL 早于 v0.73，"
                  "无法区分 GPU/CPU）")
        print("         ⇒ 进程当时还活着（看门狗还在写），所以这是「帧循环停了」，"
              "不是崩溃/挂起。")


def part_exit():
    """v0.73: did the last process quit, or was it killed?

    Every run in this investigation ended with a healthy last tick and then total
    silence, and that signature is also what a normal quit looks like - so the
    watchdog alone could never tell the two apart. The plugin now writes a line
    from DllMain(DLL_PROCESS_DETACH), which runs when the process leaves through
    the loader (ExitProcess: a normal quit, or a crash that reached the
    unhandled-exception filter) and does NOT run when the process is killed from
    outside by TerminateProcess.
    """
    section("0c. 上一个进程是怎么结束的（v0.73 退出探针）")
    recs = parse_wd_file(WATCHDOG_LOG)
    if not recs:
        print(SEV_WARN + "看门狗文件没有可解析的行")
        note(SEV_WARN, "退出判定缺失 —— 看门狗文件不可解析")
        return
    last = recs[-1]
    if last["wall"] is None:
        print(SEV_WARN + "末行没有墙钟字段 ⇒ 那次运行用的 DLL 早于 v0.73，"
              "没有退出探针，本节无法判定。")
        print("         要拿到「退出还是被杀」的答案，需要用 v0.73+ 再跑一次。")
        note(SEV_WARN, "退出判定缺失 —— DLL 早于 v0.73")
        return

    idx, exit_line = last_run_exit(WATCHDOG_LOG)
    print(SEV_INFO + "最后一段末行：%s frames=%d silent=%dms stage=%s focus=%d"
          % (last["wall"], last["frames"], last["silent"], last["stage"], last["focus"]))
    stim_end = last["stim"] if last["stim"] is not None else 0
    print("         采样线程 tick=%d（0 = 全程没触发过卡死采样，属正常）" % stim_end)

    # A stall that the watchdog kept writing through is a different animal from
    # silence: check whether records exist *after* the last one for the same run.
    after = recs[idx + 1:] if idx >= 0 else []
    same_run = [r for r in after if r["frames"] >= last["frames"] - 10]

    if exit_line:
        stamp = ""
        m = re.search(r"(\d\d:\d\d:\d\d\.\d{3})", exit_line)
        if m:
            stamp = m.group(1) + " "
        print(SEV_OK + "找到退出探针：%s%s" % (stamp, exit_line[:150]))
        print("         ⇒ 进程是**从 loader 正常退出**的：游戏自己退出（Alt+F4 / 菜单退出），"
              "或者崩溃后走到了未处理异常过滤器。")
        print("           两种情况怎么分：看 CrashLogger 日志 / WER 记录 —— 有就是崩溃，"
              "没有就是游戏自己退的。")
        note(SEV_INFO, "上一个进程从 loader 正常退出 —— 不是被外部结束")
    else:
        print(SEV_BAD + "看门狗文件里**没有** DLL_PROCESS_DETACH 行，而本次 DLL 是 v0.73+"
              "（末行带墙钟）⇒ 这个进程不是从 loader 退出的：")
        print("         ⇒ 被外部 TerminateProcess 结束（任务管理器 / MO2 的「结束进程」），"
              "或死在 loader 拿到控制权之前。")
        note(SEV_BAD, "上一个进程不是正常退出 —— 被外部结束或硬崩（日志无法再区分）")

    if same_run:
        print(SEV_BAD + "另外：末行之后还有 %d 个同段 tick ⇒ 渲染线程当时是卡住的"
              "（帧循环停了、进程还活着）" % len(same_run))
        note(SEV_BAD, "末行之后仍有看门狗 tick —— 帧循环卡死而非进程退出")
    else:
        print(SEV_INFO + "末行之后没有同段 tick ⇒ 所有线程在同一瞬间停止（进程退出），"
              "不是帧循环卡死。")


def part_responsiveness():
    """v0.76: did the window itself stop answering? Separates the two readings
    that the 07:28 run could not tell apart - 'the user killed a live process'
    from 'the message thread hung while the render thread kept presenting'."""
    print()
    print("=" * 78)
    print("0e. Window responsiveness (v0.77: msg= / alive=, classified)")
    print("=" * 78)

    recs = parse_wd_file(WATCHDOG_LOG)
    if not recs:
        print(SEV_INFO + "没有看门狗记录，跳过。")
        return
    runs = _split_wd_runs(recs)
    if not runs:
        print(SEV_INFO + "看门狗文件里没有记录。")
        return
    cur = runs[-1]
    have = [r for r in cur if r.get("msg") is not None]
    if not have:
        print("  [信息]本次运行段 {} 个 tick 全都没有 msg=/alive= 字段".format(len(cur)))
        print("         => 这次跑的不是 v0.76+。（该字段由 v0.76 引入，")
        print("            判据：需 v0.76+ 再跑一次才能给出结论。）")
        return

    dead = [r for r in have if r.get("alive") == 0]
    hung = [r for r in have if r.get("alive") == 1 and r.get("msg") == 0]
    ok = [r for r in have if r.get("alive") == 1 and r.get("msg") == 1]
    print("  [信息]本次运行段 {} 个 tick，其中 {} 个带窗口探测".format(len(cur), len(have)))
    print("         alive=1 且 msg=1（窗口在应答）：{}".format(len(ok)))
    print("         alive=1 且 msg=0（窗口不应答，需进一步分类）：{}".format(len(hung)))
    print("         alive=0（还没拿到 hwnd，无法探测）：{}".format(len(dead)))

    # v0.77: alive=0 has TWO meanings and the summary used to conflate them.
    # The hwnd is published by the first Present, so every probe before that
    # frame reports alive=0. Only alive=0 AFTER the window has been seen at
    # least once means the window really went away.
    saw_alive = False
    dead_late = []
    dead_early = 0
    for r in have:
        if r.get("alive") == 1:
            saw_alive = True
        elif saw_alive:
            dead_late.append(r)
        else:
            dead_early += 1
    if dead_early:
        print("         其中 {} 次发生在**首个 Present 之前**（hwnd 还没发布，不是窗口消失）".format(dead_early))
    if dead_late:
        print("         {} 次发生在窗口已出现过之后 ⇒ 这一次才是真的窗口消失".format(len(dead_late)))

    # ---- v0.77: msg=0 must never be judged on its own -------------------
    # msg=0 has two completely different causes and the watchdog line alone
    # cannot tell them apart. Group the ticks into bursts first: the watchdog
    # probes every 5 ticks, so a probe gap > 5 means the pump came back and
    # then went deaf again = a separate event.
    LOAD_STALL_MS = 1500

    def _bursts(seq):
        out = []
        run = []
        for r in seq:
            if run and (r["stim"] - run[-1]["stim"]) > 5:
                out.append(run)
                run = []
            run.append(r)
        if run:
            out.append(run)
        return out

    classes = []
    if hung:
        for b in _bursts(hung):
            frames_left = b[0]["frames"]
            frames_right = b[-1]["frames"]
            max_sil = max(x["silent"] for x in b)
            # A burst whose frame counter barely moved while silent is huge is
            # the game sitting in a synchronous load; msg=0 there is a symptom,
            # not the disease.
            load_like = (max_sil >= LOAD_STALL_MS) and (frames_right - frames_left) <= max(8, len(b) // 4)
            classes.append({
                "burst": b,
                "load": load_like,
                "max_sil": max_sil,
                "frames": (frames_left, frames_right),
            })

        n_load = sum(1 for c in classes if c["load"])
        n_wedge = len(classes) - n_load
        print("  [信息]msg=0 共 {} 次，聚成 {} 段（探针间隔>5 tick 视为新的一段）".format(
            len(hung), len(classes)))
        print("         {:<44} {:>3} 段".format("① 载入停顿（silent>=1500ms 且几乎不出帧）", n_load))
        print("         {:<44} {:>3} 段".format("② 消息泵卡死（silent<1500ms，渲染仍在出帧）", n_wedge))
        print()
        for i, c in enumerate(classes):
            b = c["burst"]
            st = {}
            for x in b:
                st[x["stage"]] = st.get(x["stage"], 0) + 1
            modal = sorted(st.items(), key=lambda kv: -kv[1])[0][0]
            tag = "①载入停顿" if c["load"] else "②消息泵卡死"
            print("         #{:<3} {}  {} -> {}  {:>2} 探测 {:>5.2f}s  帧 {:>5}->{:<5} "
                  "maxSil={:<6}ms  stage={}".format(
                      i, tag, b[0]["wall"][:12], b[-1]["wall"][:12], len(b),
                      b[-1]["ms"] / 1000.0 - b[0]["ms"] / 1000.0,
                      c["frames"][0], c["frames"][1], c["max_sil"], modal))

        # ---------------- verdict, per class ----------------
        print()
        for i, c in enumerate(classes):
            b = c["burst"]
            if c["load"]:
                # Find the LONG FRAME line that owns this burst, if the caller
                # has already parsed the main log; otherwise just quote silent.
                print("  [信息]段 #{} 是**载入停顿**：{} -> {}，期间只走了 {} 帧，"
                      "silent 峰值 {}ms。".format(
                          i, b[0]["wall"], b[-1]["wall"],
                          c["frames"][1] - c["frames"][0], c["max_sil"]))
                print("         窗口在载入期间不应答是**游戏自身同步加载**的正常表现，")
                print("         与 DFG 无关（渲染线程也停着，因为主线程没在喂它）。")
                print("         判据：silent>=1500ms 且帧数几乎不动 => 载入，不是卡死。")
            else:
                print("  [问题]段 #{} 是**消息泵卡死**：{} -> {}，帧 {:}->{} 仍在推进、"
                      "silent 只有 {}ms。".format(
                          i, b[0]["wall"], b[-1]["wall"],
                          c["frames"][0], c["frames"][1], c["max_sil"]))
                print("         ⇒ 渲染路径活着而窗口失聪 => 卡的是消息线程。")
                print("            这一条是渲染侧任何改法都修不到的，必须查谁在占用主线程。")

        if n_wedge == 0:
            print("  [OK] 没有任何一段属于「消息泵卡死」类 ⇒ msg=0 全部可由载入解释，")
            print("       DFG 侧无需改动（要缩短它只能减少 mod / 加快 IO）。")
        else:
            print("  [问题]存在 {} 段「消息泵卡死」⇒ 这一类才是真正需要查的。".format(n_wedge))
    else:
        print("  [OK] 全程窗口都在应答消息 ⇒ 用户看到的不是「无响应」型卡死。")

    if dead_late:
        print("  [信息]窗口在 frames={} 之后消失".format(dead_late[0]["frames"]))
    else:
        print("  [信息]窗口全程存在（{} 次 alive=0 全在首个 Present 之前）".format(dead_early))
        print("         ⇒ 看门狗文件只是**在窗口仍活着时停止了追加**。")
        print("            这通常意味着进程在记录点之后才被结束/退出 —— 结合主日志的时刻判读，")
        print("            不要仅凭 alive 推断是被 TerminateProcess 杀掉的。")


def part_gpu_timeline():
    """v0.74: did the GPU timeline actually move while the game was running?

    This is the section the 07:11 run needed. Everything else in this report
    reads CPU-side state, and in that run every CPU-side number was healthy
    (silent 5-27 ms, frames 1 -> 1614) while the D3D12 queue never advanced
    once: fence stayed at its initial value of 1 for the whole 50 s.
    """
    section("0d. GPU timeline (v0.74: queued / lastPr / dsync)")
    path = WATCHDOG_LOG
    recs = parse_wd_file(path)
    if not recs:
        print(SEV_INFO + "没有看门狗记录，跳过。")
        return
    if recs[-1].get("queued") is None:
        print(SEV_INFO + "末行没有 queued=/lastPr=/dsync= 字段 ⇒ 那次运行用的 DLL 早于 v0.74。")
        print("         本节需要 v0.74+ 再跑一次；在旧数据上不做判断。")
        return

    runs = _split_wd_runs(recs)
    cur = runs[-1] if runs else []
    cur = [r for r in cur if r.get("queued") is not None]
    if not cur:
        print(SEV_INFO + "本次运行段里没有 v0.74 字段。")
        return

    f_first = cur[0]["f11"]
    f_last = cur[-1]["f11"]
    print(SEV_INFO + "本次运行段 %d 个 tick，fence 从 %s 到 %s"
          % (len(cur), f_first, f_last))

    # ---- 1. did the fence ever move? (the decisive reading) ----
    fences = [r["f11"] for r in cur if r.get("f11") is not None]
    moved = len(set(fences)) > 1
    if not moved and fences:
        print(SEV_BAD + "fence 恒为 %s，**一次都没有前进** ⇒ D3D12 队列从未推进："
              "commandQueue->Signal() 的值从未在 GPU 上完成。" % fences[0])
        print("         这是「渲染线程健康但画面冻结」的直接签名 —— 引擎每帧跑完 Present()，"
              "但屏幕上永远是同一帧。")
        note(SEV_BAD, "fence 恒定不动 —— GPU 队列未推进（画面冻结的根本判据）")
    elif fences:
        print(SEV_OK + "fence 在推进（%s → %s）⇒ GPU 队列活着。" % (fences[0], fences[-1]))
        note(SEV_OK, "fence 单调推进 —— GPU 队列正常")

    # ---- 2. queue depth (backpressure) ----
    qs = [r["queued"] for r in cur if r.get("queued") is not None]
    if qs:
        qmax = max(qs)
        qavg = sum(qs) / float(len(qs))
        if qmax > 3:
            print(SEV_BAD + "queued 峰值 %d（均值 %.1f）> 3 ⇒ **Present 的背压丢了**："
                  "CPU 已经跑到 GPU 前面去，而 Reset 命令分配器紧跟在 Present 后面。"
                  % (qmax, qavg))
            note(SEV_BAD, "queued 峰值 %d（>3）—— Present 背压失效，CPU 跑到 GPU 前面" % qmax)
        else:
            print(SEV_OK + "queued 峰值 %d（均值 %.1f，应 <=3）⇒ 背压正常。"
                  % (qmax, qavg))
            note(SEV_OK, "queued 峰值 %d（<=3）—— 背压正常" % qmax)

    # ---- 3. Present counter ----
    prs = [r["lastpr"] for r in cur if r.get("lastpr") is not None]
    if prs:
        if len(set(prs)) == 1:
            print(SEV_BAD + "lastPr 恒为 %d ⇒ Present **没有翻页**：它返回了成功，"
                  "但屏幕内容没有变（FLIP 模型下这是合法返回，所以 Present 自己不会报错）。"
                  % prs[0])
            note(SEV_BAD, "lastPr 恒定 —— Present 静默不翻页")
        else:
            print(SEV_OK + "lastPr 在推进（%d → %d）⇒ Present 真的在翻页。"
                  % (prs[0], prs[-1]))
            note(SEV_OK, "lastPr 递增 —— Present 真的在翻页")

    # ---- 4. frame index desync ----
    ds = [r["dsync"] for r in cur if r.get("dsync") is not None]
    if ds:
        n = sum(1 for d in ds if d)
        if n:
            print(SEV_WARN + "dsync=1 出现 %d/%d 次 ⇒ frameIndex 与 "
                  "GetCurrentBackBufferIndex() 不一致（旁路期翻页脱节，v0.72 踩过）。"
                  % (n, len(ds)))
            note(SEV_WARN, "dsync 出现 %d 次 —— frameIndex 与 DXGI 索引脱节" % n)
        else:
            print(SEV_OK + "dsync 全程为 0 ⇒ frameIndex 与 DXGI 索引一致。")

    # ---- 5. the combined verdict ----
    if not moved and fences:
        print()
        print(SEV_BAD + "综合判决：**GPU 队列停止推进**（不是帧循环卡死、不是进程退出）")
        print("         渲染线程仍在跑（frames/silent 健康），但 GPU 一条命令都没执行完。")
        print("         下一步看 queued / lastPr / dsync 三个字段判断走的是哪条路径。")


def part_dlssg_health(lines):
    """v0.77: did frame generation actually produce frames?

    Everything else in this report measures the *conditions* for DLSS-G
    (matrices, swapchain, threads). This section measures the *outcome*. The
    08:27 run had every condition healthy and `accepted=0` for a full minute,
    which no other section reported.
    """
    print()
    print("=" * 78)
    print("9x. DLSS-G 实际产出（v0.77：accepted= / dlssgOk= / MFG 梯子）")
    print("=" * 78)

    # ---- 1. the accepted= field from the 2 s FPS probe ----
    # NOTE: `lines` holds (timestamp, thread, text) tuples, not raw strings.
    probes = []
    for _ts, _tid, ln in lines:
        if "[FrameGen] FPS probe:" not in ln:
            continue
        wall = _ts or "?"
        mr = re.search(r"real=([0-9.]+)", ln)
        ma = re.search(r"accepted=(\d+)", ln)
        mh = re.search(r"hwMax=(\d+)", ln)
        mask = re.search(r"ask=(\d+)", ln)
        if ma and mr:
            probes.append({
                "wall": wall,
                "real": float(mr.group(1)),
                "accepted": int(ma.group(1)),
                "hwMax": int(mh.group(1)) if mh else None,
                "ask": int(mask.group(1)) if mask else None,
            })
    if not probes:
        print(SEV_INFO + "没有 FPS probe 行，跳过。")
        return

    n0 = sum(1 for p in probes if p["accepted"] == 0)
    nge = len(probes) - n0
    print("  [信息]FPS 探针 %d 次" % len(probes))
    print("         其中 accepted=0（帧生成**没有输出任何插值帧**）：%d 次" % n0)
    print("         accepted>=1（真的在插帧）：%d 次" % nge)
    first_on = next((p for p in probes if p["accepted"] > 0), None)
    if first_on:
        print("         首次真正生效：%s（accepted=%d）" % (first_on["wall"], first_on["accepted"]))

    # ---- 2. duration of the dead window ----
    if n0:
        bad = [p for p in probes if p["accepted"] == 0]
        print()
        print("  [问题]帧生成在 %s .. %s 之间全程为 0（%d 个连续探针）"
              % (bad[0]["wall"], bad[-1]["wall"], len(bad)))

    # ---- 3. the self-labelling "COMPUTED not measured" ----
    comp = [t for _ts, _tid, t in lines if "COMPUTED not measured" in t]
    if comp:
        print()
        print("  [信息]日志自己把倍率标为 COMPUTED not measured 的行：%d 条" % len(comp))
        print("         ⇒ `cap~=real*2` 是**算出来的**，不是测出来的。")
        print("            所以日志里的 fps 不能当作「插帧真的跑起来了」的证据；")
        print("            唯一可信的产出判据是 accepted= 与实际呈现统计。")

    # ---- 4. the MFG ladder ----
    rej = [t for _ts, _tid, t in lines if "MFG probe: runtime REJECTED" in t]
    acc = [t for _ts, _tid, t in lines if "MFG probe: runtime ACCEPTED" in t]
    rmax = [t for _ts, _tid, t in lines if "runtimeReportsMax=" in t]
    print()
    print("  [信息]MFG 梯子：拒绝 %d 次 / 接受 %d 次" % (len(rej), len(acc)))
    for ln in rej[-4:]:
        print("         %s" % ln.strip())
    for ln in acc[-2:]:
        print("         %s" % ln.strip())

    runtime_max = None
    if rmax:
        m = re.search(r"runtimeReportsMax=(\d+)x", rmax[-1])
        if m:
            runtime_max = int(m.group(1))
        ask = re.search(r"overrideAsksMax=(\d+)x", rmax[-1])
        print("         运行时自报上限 = %sx，我们请求 = %s"
              % (runtime_max, ask.group(1) if ask else "?"))

    # ---- 5. verdict ----
    print()
    if runtime_max == 2:
        print("  [问题]运行时自报上限只有 2x —— 4x/3x 被 eErrorInvalidState(38) 拒绝。")
        print("         4x 需要外部 kernel unlocker（DLSSG-Transfusion / dlssg_for_sm86 /")
        print("         MFG Bridge）在场。若它已被移出，则 overrideAsksMax=4x **永远不可能生效**。")
        print("         这不是 DFG 的代码缺陷，是**运行时能力上限**。")
        note(SEV_BAD, "运行时只支持 2x（4x 需要外部 unlocker）")
    if n0 and not nge:
        print("  [问题]整场 accepted 恒为 0 ⇒ 帧生成**从未输出**过一帧插值。")
        print("         用户看到的流畅度改善不可能来自本次运行。")
        note(SEV_BAD, "帧生成全程未输出（accepted=0）")
    elif n0:
        ratio = 100.0 * n0 / len(probes)
        print("  [问题]帧生成有 %.0f%% 的时间是关闭的（accepted=0）。" % ratio)
        note(SEV_BAD, "帧生成 %.0f%% 时间未输出" % ratio)
    else:
        print("  [OK] 帧生成全程有输出。")


def part_verdicts(lines):
    section("5. 插件自己给出的结论（[XRAY] VERDICT）")
    vs = grab(r"\[XRAY\] VERDICT", lines)
    if not vs:
        print(SEV_WARN + "没有 VERDICT 行")
        return
    counts = collections.Counter(v[2] for v in vs)
    for text, n in counts.most_common():
        print("  x%-4d %s" % (n, text))
    lastv = vs[-1][2]
    print()
    if "PROBLEM" in lastv:
        print(SEV_BAD + "最新判定：" + lastv.split("VERDICT:", 1)[-1].strip())
        note(SEV_BAD, "插件自判：" + lastv.split("VERDICT:", 1)[-1].strip())
    elif "inconclusive" in lastv:
        print(SEV_WARN + "采样不足：" + lastv.split("VERDICT:", 1)[-1].strip())
    else:
        print(SEV_OK + "最新判定：" + lastv.split("VERDICT:", 1)[-1].strip())


# ------------------------------------------------------------------ errors
def part_errors(lines):
    section("6. 已知错误签名扫描")
    sigs = [
        (r"slSetConstants FAILED", "常量被拒（详见第 4 节）"),
        (r"frame generation auto-disabled", "帧生成被自动禁用（连续失败超阈值）"),
        (r"slDLSSGGetState failed", "状态查询失败"),
        (r"DLSSG skipped", "DLSSG 被跳过（共享纹理未就绪）"),
        (r"passthrough", "直通模式（无插帧）"),
        (r"MFG probe: runtime REJECTED", "多倍倍率被运行时拒绝，逐级降档"),
        (r"MFG probe: runtime rejects even 2x", "连 2x 都不被接受 → 没有可用 DLSS-G 内核"),
        (r"has no registered hooks", "某 SL 插件未注册钩子（Reflex/RSYNC 相关）"),
        (r"\[E\]", "error 级日志"),
    ]
    any_hit = False
    for pat, desc in sigs:
        hits = grab(pat, lines)
        if hits:
            any_hit = True
            sev = SEV_BAD if pat not in (r"passthrough", r"has no registered hooks") else SEV_WARN
            print("%s %-46s x%d" % (sev, desc, len(hits)))
            print("         最后一条：%s %s" % (hits[-1][0], hits[-1][2][:120]))
    if not any_hit:
        print(SEV_OK + "未命中任何已知错误签名")


def part_transfusion(path):
    section("7. Transfusion 侧交叉验证")
    text = read(path)
    if text is None:
        print(SEV_INFO + "没有找到 %s（可选）" % path)
        return
    lines = parse_lines(text)
    # The wrapper can strip flags the game sets - that silently voids any change
    # made on the game side, so it is reported first.
    for l in grab(r"stripped|Option [A-Z] active|OPTIONS\] Game DLSS-G options", lines)[-6:]:
        print(SEV_INFO + l[2][:180])
    if grab(r"stripped eEnableFullScreenMenuDetection", lines):
        print(SEV_BAD + "包装层把 eEnableFullScreenMenuDetection 从选项里剥掉了 → "
              "游戏侧设置这个标志不会有任何效果")
        note(SEV_BAD, "菜单检测标志被 Transfusion 剥掉（游戏侧设了也白设）")
    mot = grab(r"\[MOTION\]", lines)
    if mot:
        print(SEV_INFO + "最后一条 [MOTION]：")
        print("         " + mot[-1][2][:200])
        rs = re.findall(r"reset=(\d)", " ".join(m[2] for m in mot[-8:]))
        if rs:
            print(SEV_INFO + "最近 8 帧 reset 序列：" + " ".join(rs))
            if all(x == "1" for x in rs):
                print(SEV_BAD + "reset 连续为 1 → 每帧都在重置 DLSS-G 历史")
                note(SEV_BAD, "Transfusion 观测到 reset 恒 1（v0.59 未生效）")
            elif all(x == "0" for x in rs):
                print(SEV_OK + "reset 已回归 0（v0.59 生效）")
        m = re.search(r"clipToPrev=(\w+)", mot[-1][2])
        if m and m.group(1) == "identity":
            print(SEV_WARN + "clipToPrev=identity → 相机重投影被丢弃（静止时正常，移动中则为问题）")
    jit = grab(r"\[PERF\]", lines)
    if jit:
        print(SEV_INFO + "最后一条 [PERF]：%s" % jit[-1][2][:160])
    if not grab(r"\[MOTION\]", lines) and not jit:
        print(SEV_INFO + "Transfusion 日志存在，但没有 [MOTION]/[PERF] 行")


def part_transfusion_csv():
    section("8. Transfusion perf.csv（每真实帧的间隔与倍率）")
    path = r"D:\ENB-EJ\Skyrim Special Edition\DLSSG-Transfusion_perf.csv"
    text = read(path)
    if text is None:
        print(SEV_INFO + "没有找到 %s（可选）" % path)
        return
    rows = []
    for ln in text.replace("\r\n", "\n").split("\n")[1:]:
        p = ln.strip().split(",")
        if len(p) >= 5:
            try:
                rows.append((int(p[0]), float(p[1]), float(p[2]), int(p[3]), p[4]))
            except ValueError:
                pass
    if not rows:
        print(SEV_WARN + "csv 没有可解析的行")
        return
    d = [r[2] for r in rows if r[2] > 0]
    print(SEV_INFO + "共 %d 帧，时间跨度 %.1f 秒" % (len(rows), (rows[-1][1] - rows[0][1]) / 1000.0))
    if d:
        sd = sorted(d)
        print(SEV_INFO + "DeltaMs：min=%.2f 中位=%.2f max=%.2f" % (sd[0], sd[len(sd) // 2], sd[-1]))
    gaps = [(rows[i][0], rows[i - 1][2]) for i in range(1, len(rows)) if rows[i - 1][2] > 300]
    if gaps:
        print(SEV_WARN + "有 %d 处 >300ms 的长帧，最大 %.1f ms（帧号 %s）"
              % (len(gaps), max(g[1] for g in gaps), max(gaps, key=lambda g: g[1])[0]))
    mults = collections.Counter(r[3] for r in rows)
    print(SEV_INFO + "Multiplier 分布：%s" % dict(mults))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else DFG_LOG
    text = read(path)
    if text is None:
        print("找不到日志：%s" % path)
        return 2
    lines = parse_lines(text)
    print("日志：%s" % path)
    print("行数：%d   首个时间戳：%s   最后一个：%s"
          % (len(lines), lines[0][0] if lines else "-", lines[-1][0] if lines else "-"))

    part_watchdog()
    part_stalls()
    part_exit()
    part_gpu_timeline()
    part_responsiveness()
    part_identity(lines)
    part_env(lines)
    part_menu(lines)
    part_heartbeat(lines)
    part_cam(lines)
    part_fixes(lines)
    part_focus(lines)
    part_dlssg_health(lines)
    part_verdicts(lines)
    part_errors(lines)
    part_transfusion(TRANSFUSION_LOG)
    part_transfusion_csv()

    section("总结")
    bad = [t for s, t in findings if s == SEV_BAD]
    warn = [t for s, t in findings if s == SEV_WARN]
    if not findings:
        print(SEV_OK + "没有发现缺陷（采样足够的前提下）")
    for t in bad:
        print(SEV_BAD + t)
    for t in warn:
        print(SEV_WARN + t)
    print()
    print("判据（主观）：静止在主菜单是否还闪 / 进世界后移动是否还闪")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
