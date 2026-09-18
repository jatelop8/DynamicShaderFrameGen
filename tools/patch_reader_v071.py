#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reader v0.71 -- teach tools/read_xray_log.py to see a window-presentation hang.

Three things change on the plugin side that the reader must not silently ignore:

  1. the watchdog line gained a focus= field, so WD_RE no longer matches. A
     parser that stops matching does not fail loudly - section 0 would report
     "no parseable lines" and the whole watchdog story (the only evidence that
     survives a wedged render thread) would be lost. That is exactly the class
     of silent-instrument failure this project keeps hitting.
  2. new log lines: "[XRAY] FOCUS lost/regained" and "[XRAY] DLSSG mode -> OFF".
  3. a new failure MODE that is decidable from files: if the last log line lands
     within a few seconds after "FOCUS lost", the process stopped on the first
     Present after the window lost the foreground. Cross-checked against every
     OTHER plugin's log in the same folder - if several independent loggers stop
     within the same second, the frame loop itself stopped, which rules out
     "one plugin misbehaved".

Guards: dry run by default, idempotency marker first, per-anchor uniqueness,
brace/paren sanity, EOL-adaptive.
"""

import os
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(TOOLS, "read_xray_log.py")

MARKERS = ["4c. 焦点 / Present 死锁", "def _secs(", 'focus=%d stage=%s']

R = []

R.append(("import collections",
          "import collections\nimport time"))

R.append((
    'WD_RE = re.compile(r"^\\[(\\d+)\\]\\s+frames=(\\d+)\\s+silent=(-?\\d+)ms\\s+stage=(.*?)\\s*(<==.*)?$")',
    '# v0.71: focus= was appended to the watchdog line, so the old pattern no\n'
    '# longer matches ANY line. The focus group is optional on purpose: lines\n'
    '# written by earlier builds must still parse, or the cross-run splitting\n'
    '# below (which walks backwards on the frame counter) loses its history.\n'
    'WD_RE = re.compile(r"^\\[(\\d+)\\]\\s+frames=(\\d+)\\s+silent=(-?\\d+)ms\\s+stage=(.*?)"\n'
    '                   r"(?:\\s+focus=(-?\\d+))?\\s*(<==.*)?$")'))

R.append((
    "            recs.append((int(m.group(1)), int(m.group(2)), int(m.group(3)),\n"
    "                         m.group(4), bool(m.group(5))))",
    "            recs.append((int(m.group(1)), int(m.group(2)), int(m.group(3)),\n"
    "                         m.group(4),                                  # stage\n"
    "                         int(m.group(5)) if m.group(5) is not None else -1,  # focus\n"
    "                         bool(m.group(6))))                          # stalled"))

R.append((
    '    print(SEV_INFO + "最后一行：frames=%d silent=%dms stage=%s"\n'
    '          % (recs[-1][1], recs[-1][2], recs[-1][3]))',
    '    focus_txt = ("focus=%d" % recs[-1][4]) if recs[-1][4] >= 0 else "focus=(n/a)"\n'
    '    print(SEV_INFO + "最后一行：frames=%d silent=%dms stage=%s %s"\n'
    '          % (recs[-1][1], recs[-1][2], recs[-1][3], focus_txt))'))

R.append(("    stalled = [r for r in recs if r[4]]",
          "    stalled = [r for r in recs if r[5]]"))

R.append(("        run = [r for r in recs[idx:] if r[4]]",
          "        run = [r for r in recs[idx:] if r[5]]"))

R.append((
    '        print("         最后一帧的帧号 %d 在此之后不再增长（卡死前 %s）"\n'
    '              % (first[1], ("frames=%d stage=%s" % (prev[1], prev[3])) if prev else "-"))\n'
    '        note(SEV_BAD, "渲染线程卡死在 \'%s\'（约 %.1f 秒）——这是本次跑真正的故障点" % (first[3], dur))',
    '        print("         最后一帧的帧号 %d 在此之后不再增长（卡死前 %s）"\n'
    '              % (first[1], ("frames=%d stage=%s" % (prev[1], prev[3])) if prev else "-"))\n'
    '        # v0.71: focus= is the difference between the two ways this can end.\n'
    '        if first[4] == 0:\n'
    '            print(SEV_BAD + "         采样时 focus=0 —— 窗口不在前台。FLIP_DISCARD 交换链"\n'
    '                  "（BufferCount=3）在窗口失焦/被遮挡时 Present 会永久阻塞，而 v0.71 之前"\n'
    '                  "全工程没有一处焦点处理（GetForegroundWindow / IsIconic / ACTIVATEAPP 均 0 处）。")\n'
    '            note(SEV_BAD, "卡死发生在窗口失焦状态（focus=0）—— 焦点 / Present 死锁")\n'
    '        note(SEV_BAD, "渲染线程卡死在 \'%s\'（约 %.1f 秒）——这是本次跑真正的故障点" % (first[3], dur))'))

R.append((
    '        print("    %s frames=%-6d silent=%-8d stage=%s%s"\n'
    '              % (r[0], r[1], r[2], r[3], "  <== 卡死" if r[4] else ""))',
    '        print("    %s frames=%-6d silent=%-8d focus=%-3s stage=%s%s"\n'
    '              % (r[0], r[1], r[2], (r[4] if r[4] >= 0 else "?"), r[3],\n'
    '                 "  <== 卡死" if r[5] else ""))'))

NEW_FUNC = '''# ------------------------------------------- v0.71 focus / present hang
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
        print(SEV_BAD + "  %d 个互不相干的插件日志在同一秒内停摆 ⇒ 整个帧循环停了，"
              "不是某一个插件的问题" % len(same))
        note(SEV_BAD, "%d 个插件的日志同秒停摆 —— 进程级停摆（帧循环卡在 Present）" % len(same))
    else:
        print(SEV_INFO + "  只有 %d 个日志同时停摆 —— 不足以判定进程级停摆" % len(same))


'''

R.append(("def part_verdicts(lines):", NEW_FUNC + "def part_verdicts(lines):"))

R.append(("    part_fixes(lines)\n    part_verdicts(lines)",
          "    part_fixes(lines)\n    part_focus(lines)\n    part_verdicts(lines)"))


def main():
    apply_it = "--apply" in sys.argv
    with open(TARGET, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        text = f.read()

    for m in MARKERS:
        if m in text:
            print("REFUSED -- reader already patched (found %r)" % m)
            return 1

    plan = []
    bad = False
    for old, new in R:
        n = text.count(old)
        if n != 1:
            alt = old.replace("\r\n", "\n") if "\r\n" in old else old.replace("\n", "\r\n")
            if text.count(alt) == 1:
                old, n = alt, 1
        label = old.strip().splitlines()[0][:58]
        print("%-60s anchor x%d" % (label, n))
        if n != 1:
            bad = True
        plan.append((old, new))
    if bad:
        print("REFUSED -- an anchor is missing (0) or ambiguous (>1); nothing written")
        return 1

    s = text
    for old, new in plan:
        assert s.count(old) == 1, "anchor went ambiguous mid-apply"
        eol = "\r\n" if "\r\n" in text else "\n"
        s = s.replace(old, new if eol == "\n" else new.replace("\n", "\r\n"), 1)

    # sanity: the parser fields must line up with the tuple order
    for needle in ("int(m.group(5)) if m.group(5) is not None else -1",
                   "bool(m.group(6))", "stalled = [r for r in recs if r[5]]",
                   "part_focus(lines)"):
        if needle not in s:
            print("REFUSED -- post-condition missing: %s" % needle)
            return 1

    print("%+d bytes" % (len(s) - len(text)))
    if not apply_it:
        print("\nDRY RUN -- nothing written. Re-run with --apply")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    with open(TARGET + ".bak-" + stamp, "w", encoding="utf-8",
              errors="surrogateescape", newline="") as b:
        b.write(text)
    with open(TARGET, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)
    print("wrote %s (backup .bak-%s)" % (TARGET, stamp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
