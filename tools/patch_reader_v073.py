"""v0.73 reader update: understand the new watchdog fields, and read the exit probe.

The watchdog line gained a wall clock, the fence field moved to the sampler and
gained `stim=`, and the plugin now writes an `[exit] DLL_PROCESS_DETACH` line when
the process leaves through the loader. A parser that does not know a field does
not complain - it just stops matching, and every section above it goes quiet.
That has happened three times in this project, so the line format and the parser
move together in the same change.

The two hand-maintained watchdog regexes are also merged into one parser here,
for the same reason: v0.71 added focus=, v0.73 adds wall clock / fence / stim,
and each addition has to be made in two places or one of them silently dies.

Dry run by default; --apply writes.
"""

import hashlib
import os
import shutil
import sys
import time

ROOT = r"D:/Modding/DynamicShaderFrameGen"
TARGET = os.path.join(ROOT, "tools/read_xray_log.py")
STAMP = time.strftime("%Y%m%d-%H%M%S")

MARKERS = ["def parse_wd_line(", "def part_exit():", "0c. 上一个进程是怎么结束的"]

# ---------------------------------------------------------------------------
# R1: one parser for the watchdog line, replacing the first of the two regexes
# ---------------------------------------------------------------------------

R1_OLD = '''WD_RE = re.compile(r"^\\[(\\d+)\\]\\s+frames=(\\d+)\\s+silent=(-?\\d+)ms\\s+stage=(.*?)"
                   r"(?:\\s+focus=(-?\\d+))?\\s*(<==.*)?$")
'''

R1_NEW = '''# v0.73: field history. Every field after stage= is optional on purpose, because
# records from older builds must still parse - the cross-run split below walks
# backwards on the frame counter and dies without the history.
#   v0.62  [mono] frames= silent=ms stage=
#   v0.71  ... focus=
#   v0.72  ... fence=a/b
#   v0.73  [mono] hh:mm:ss.mmm frames= silent=ms stage= focus= fence=a/b|-/- stim=n
# `stim` is the sampler thread's tick count: 0 means no hang was ever suspected and
# the fence field is therefore empty. At a hang, climbing stim means the GPU
# timeline is alive (the render thread is parked in CPU code) and frozen stim means
# the sampler itself is parked in the driver (a GPU/driver wedge).
WD_RE = re.compile(
    r"^\\[(?P<ms>\\d+)\\]\\s+"
    r"(?:(?P<hh>\\d\\d):(?P<mm>\\d\\d):(?P<ss>\\d\\d)\\.(?P<msec>\\d{3})\\s+)?"
    r"frames=(?P<frames>\\d+)\\s+silent=(?P<silent>-?\\d+)ms\\s+stage=(?P<stage>.*?)"
    r"(?:\\s+focus=(?P<focus>-?\\d+))?"
    r"(?:\\s+fence=(?P<f11>\\d+|~0|-)/(?P<f12>\\d+|~0|-))?"
    r"(?:\\s+stim=(?P<stim>\\d+))?"
    r"\\s*(?P<stalled><==.*)?$")


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
'''

# ---------------------------------------------------------------------------
# R2: part_watchdog parses through the shared parser (tuple shape preserved for
# indices 0..5, new fields appended at 6.. so nothing downstream shifts)
# ---------------------------------------------------------------------------

R2_OLD = '''    recs = []
    for ln in text.replace("\\r\\n", "\\n").split("\\n"):
        m = WD_RE.match(ln.strip())
        if m:
            recs.append((int(m.group(1)), int(m.group(2)), int(m.group(3)),
                         m.group(4),                                  # stage
                         int(m.group(5)) if m.group(5) is not None else -1,  # focus
                         bool(m.group(6))))                          # stalled
'''

R2_NEW = '''    recs = []
    for ln in text.replace("\\r\\n", "\\n").split("\\n"):
        r = parse_wd_line(ln)
        if r:
            # Indices 0..5 keep their old meaning; v0.73 fields go on the end so
            # nothing that reads this tuple has to be renumbered.
            recs.append((r["ms"], r["frames"], r["silent"], r["stage"], r["focus"],
                         r["stalled"], r["wall"], r["stim"], r["f11"], r["f12"]))
'''

# ---------------------------------------------------------------------------
# R3: show the new fields in the two places part_watchdog prints records
# ---------------------------------------------------------------------------

R3_OLD = '''    focus_txt = ("focus=%d" % recs[-1][4]) if recs[-1][4] >= 0 else "focus=(n/a)"
    print(SEV_INFO + "最后一行：frames=%d silent=%dms stage=%s %s"
          % (recs[-1][1], recs[-1][2], recs[-1][3], focus_txt))
'''

R3_NEW = '''    focus_txt = ("focus=%d" % recs[-1][4]) if recs[-1][4] >= 0 else "focus=(n/a)"
    wall_txt = ("%s " % recs[-1][6]) if recs[-1][6] else "(无墙钟：DLL 早于 v0.73) "
    print(SEV_INFO + "最后一行：%sframes=%d silent=%dms stage=%s %s"
          % (wall_txt, recs[-1][1], recs[-1][2], recs[-1][3], focus_txt))
'''

R4_OLD = '''    print("  最后 10 个 tick：")
    for r in recs[-10:]:
        print("    %s frames=%-6d silent=%-8d focus=%-3s stage=%s%s"
              % (r[0], r[1], r[2], (r[4] if r[4] >= 0 else "?"), r[3],
                 "  <== 卡死" if r[5] else ""))
'''

R4_NEW = '''    print("  最后 10 个 tick（墙钟 / frames / silent / focus / stage / fence / stim）：")
    for r in recs[-10:]:
        fen = ("%s/%s" % (r[8], r[9])) if r[8] is not None else "-"
        print("    %-12s fields=%-6d silent=%-8d focus=%-3s fence=%-12s stim=%-5s stage=%s%s"
              % (r[6] or "?:?:?.???", r[1], r[2], (r[4] if r[4] >= 0 else "?"), fen,
                 (r[7] if r[7] is not None else "-"), r[3],
                 "  <== 卡死" if r[5] else ""))
'''

# ---------------------------------------------------------------------------
# R5: _parse_wd becomes a thin wrapper over the shared parser
# ---------------------------------------------------------------------------

R5_OLD = '''def _parse_wd(path):
    """Parse the whole watchdog file, fence field optional (v0.72 added it)."""
    out = []
    try:
        raw = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return out
    for ln in raw:
        m = re.match(r"^\\[(\\d+)\\]\\s+frames=(\\d+)\\s+silent=(-?\\d+)ms\\s+stage=(.*?)"
                     r"(?:\\s+focus=(-?\\d+))?(?:\\s+fence=(\\d+)/(\\d+))?\\s*(<==.*)?$", ln)
        if not m:
            continue
        out.append({
            "ms": int(m.group(1)),
            "frames": int(m.group(2)),
            "silent": int(m.group(3)),
            "stage": m.group(4),
            "focus": int(m.group(5)) if m.group(5) is not None else -1,
            "f11": int(m.group(6)) if m.group(6) is not None else None,
            "f12": int(m.group(7)) if m.group(7) is not None else None,
            "stalled": bool(m.group(8)),
        })
    return out
'''

R5_NEW = '''def _parse_wd(path):
    """v0.73: the second copy of the watchdog regex is gone - both sections now use
    parse_wd_file(). Two hand-maintained regexes meant every field added to the
    line had to be added twice, and a missed one fails silently."""
    return parse_wd_file(path)
'''

# ---------------------------------------------------------------------------
# R6: part_stalls -- report the sampler, so a stall says GPU or CPU
# ---------------------------------------------------------------------------

R6_OLD = '''        # fence values are the discriminator: frozen queues vs a CPU-side block
        fa = [x["f11"] for x in r[idx:] if x["f11"] is not None]
        fb = [x["f12"] for x in r[idx:] if x["f12"] is not None]
        if fa and fb:
            if fa[0] == fa[-1] and fb[0] == fb[-1]:
                print(SEV_BAD + "         GPU 围栏在整个卡死期间没有推进（fence %d/%d）"
                      " ⇒ 队列停了：跨队列/驱动级卡死" % (fa[0], fb[0]))
            else:
                print(SEV_INFO + "         GPU 围栏仍在推进（fence %d→%d）⇒ GPU 没停，"
                      "是渲染线程在 CPU 侧被挡住" % (fa[0], fa[-1]))
        else:
            print("         （该段没有 fence= 字段：DLL 早于 v0.72，无法区分 GPU/CPU）")
'''

R6_NEW = '''        # fence values are the discriminator: frozen queues vs a CPU-side block
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
'''

# ---------------------------------------------------------------------------
# R7: the new section -- how the previous process actually ended
# ---------------------------------------------------------------------------

R7_ANCHOR = '''def part_verdicts(lines):
'''

R7_NEW = '''def part_exit():
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
        m = re.search(r"(\\d\\d:\\d\\d:\\d\\d\\.\\d{3})", exit_line)
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


def part_verdicts(lines):
'''

# ---------------------------------------------------------------------------
# R8: wire the new section into main()
# ---------------------------------------------------------------------------

R8_OLD = '''    part_watchdog()
    part_stalls()
'''

R8_NEW = '''    part_watchdog()
    part_stalls()
    part_exit()
'''

EDITS = [
    ("R1 one watchdog parser + exit helpers", R1_OLD, R1_NEW),
    ("R2 part_watchdog uses the shared parser", R2_OLD, R2_NEW),
    ("R3 last line shows the wall clock", R3_OLD, R3_NEW),
    ("R4 last 10 ticks show wall/fence/stim", R4_OLD, R4_NEW),
    ("R5 _parse_wd becomes a wrapper", R5_OLD, R5_NEW),
    ("R6 stalls report the sampler", R6_OLD, R6_NEW),
    ("R7 new section: part_exit", R7_ANCHOR, R7_NEW),
    ("R8 call part_exit from main", R8_OLD, R8_NEW),
]

# (text, minimum count) -- the parser must not have lost the older fields
SURVIVORS = [
    ("focus", 5),
    ("parse_wd_line", 4),
]


def match_anchor(text, old, new):
    if text.count(old) == 1:
        return old, new, 1
    if "\\r\\n" not in old:
        swapped = old.replace("\\n", "\\r\\n")
        if text.count(swapped) == 1:
            return swapped, new.replace("\\n", "\\r\\n"), 1
    else:
        swapped = old.replace("\\r\\n", "\\n")
        if text.count(swapped) == 1:
            return swapped, new.replace("\\r\\n", "\\n"), 1
    return None, None, text.count(old) + text.count(swapped)


def brace_delta(text):
    return text.count("(") - text.count(")")


def main():
    apply = "--apply" in sys.argv
    text = open(TARGET, "r", encoding="utf-8", newline="").read()

    for m in MARKERS:
        if m in text:
            print("REFUSED -- already applied: %r" % m)
            return 1

    plan = []
    bad = 0
    for label, old, new in EDITS:
        anchor, repl, n = match_anchor(text, old, new)
        if anchor is None:
            print("REFUSED -- %-42s anchor x%d (want 1)" % (label, n))
            bad += 1
            continue
        plan.append((label, anchor, repl))
        print("ok       %-42s anchor x1" % label)
    if bad:
        print("REFUSED, nothing written")
        return 1

    out = text
    for label, anchor, repl in plan:
        assert out.count(anchor) == 1, label
        out = out.replace(anchor, repl, 1)

    checks = [
        ("regex has named groups", out.count('(?P<stim>'), 1),
        ("one parser definition", out.count("def parse_wd_line("), 1),
        ("_parse_wd delegates", out.count("return parse_wd_file(path)"), 1),
        ("exit section exists", out.count("def part_exit():"), 1),
        ("exit section wired in", out.count("    part_exit()"), 1),
        # Raw literals on purpose: the first draft doubled every backslash, so these
        # two negative probes searched for a string that never exists and reported
        # "0 (want 0)" -- a pass that proves nothing. A negative check that cannot
        # fail is worse than no check.
        ("old WD_RE gone", out.count(r'r"^\[(\d+)\]\s+frames='), 0),
        ("old _parse_wd regex gone", out.count(r"fence=(\d+)/(\d+)"), 0),
    ]
    ok = True
    for label, got, want in checks:
        good = got == want
        if not good:
            ok = False
        print("%s     %-38s %d (want %d)" % ("ok  " if good else "FAIL", label, got, want))

    for s, want in SURVIVORS:
        got = out.count(s)
        good = got >= want
        if not good:
            ok = False
        print("%s     survivor %-30s %d (want >=%d)" % ("ok  " if good else "FAIL", s, got, want))

    d = brace_delta(out) - brace_delta(text)
    print("%s     paren delta %d" % ("ok  " if d == 0 else "FAIL", d))
    if d != 0:
        ok = False

    if not ok:
        print("REFUSED, nothing written")
        return 1

    if not apply:
        print("\nDRY RUN ok -- %d edits; re-run with --apply" % len(plan))
        return 0

    bak = TARGET + ".bak-" + STAMP
    shutil.copy2(TARGET, bak)
    with open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    back = open(TARGET, "r", encoding="utf-8", newline="").read()
    b = back.encode("utf-8")
    lone = back.count("\\r") - back.count("\\r\\n")
    print("wrote %s  backup %s" % (os.path.basename(TARGET), os.path.basename(bak)))
    print("readback: %d B md5=%s roundtrip=%s lone_CR=%d"
          % (len(b), hashlib.md5(b).hexdigest()[:12],
             "ok" if back == out else "MISMATCH", lone))
    return 0 if back == out and lone == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
