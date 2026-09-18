#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.72 reader: add a CROSS-RUN STALL TABLE, and stop the 4c section from asserting
a mechanism it cannot know.

Why this is the important reader change
---------------------------------------
The 00:03 diagnosis was not made from the frozen run's main log - that file is
overwritten every run and was already gone. It was made from the watchdog file,
which is append-only and therefore still held every run's shape. Splitting it into
runs and tabulating "ticks / duration / frames at end / max silent / focus / last
stage / STALLED count" turned an invisible freeze into an obvious one:

    #   ticks  dur_s  lastFrame  lastSil  maxSil  focus  lastStage      STALLED
    6   54     53.2   1493       22       25017   -1     cmdlist Reset  0
    7   175    34.9   275        4318     25814   0      d3d11 Wait     3     <== the freeze
    8   261    52.2   1701       11       19198   1      d3d11 Wait     0

Run 7 is the freeze: the loop stopped at frame 275, silent climbed past 4.3 s, the
window was unfocused, and the watchdog kept writing - i.e. the process was alive and
only the frame loop had stopped. That is "sound keeps playing, picture frozen".

Doing this by hand once was worth more than every single-run section in this file, so
it belongs in the reader permanently.

Also: section 4c used to conclude "帧循环卡在 Present" from "several logs stopped in
the same second". That is an overreach - a stopped log says the writers stopped, not
why. It is now worded as what it is (a process-level stop) and points at the stall
table for the mechanism.

Reads/writes UTF-8 (the file is a UTF-8 .py, not an ENB ini). Dry run by default.
"""

import os
import shutil
import sys
import time

TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "read_xray_log.py")

MARKERS = [
    "def part_stalls(",
    "def _split_wd_runs(",
    "4c. 焦点 / Present 死锁（v0.71）",  # must still exist as a heading
]

# ---------------------------------------------------------------- R1
R1_OLD = '''def part_verdicts(lines):
'''

R1_NEW = '''def _parse_wd(path):
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
        if prev:
            print("         最后一帧 %d（%s）→ 之后 silent 一直涨，%d 个 tick 报了 STALLED"
                  % (prev["frames"], prev["stage"][:24], sum(1 for x in r if x["stalled"])))
        print("         停止时 focus=%d（0 = 窗口不在前台），最后 stage=%s"
              % (first["focus"], first["stage"]))
        # fence values are the discriminator: frozen queues vs a CPU-side block
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
        print("         ⇒ 进程当时还活着（看门狗还在写），所以这是「帧循环停了」，"
              "不是崩溃/挂起。")


def part_verdicts(lines):
'''

# ---------------------------------------------------------------- R2
R2_OLD = '''    part_watchdog()
'''
R2_NEW = '''    part_watchdog()
    part_stalls()
'''

# ---------------------------------------------------------------- R3
R3_OLD = '''        print(SEV_BAD + "  %d 个互不相干的插件日志在同一秒内停摆 ⇒ 整个帧循环停了，"
              "不是某一个插件的问题" % len(same))
        note(SEV_BAD, "%d 个插件的日志同秒停摆 —— 进程级停摆（帧循环卡在 Present）" % len(same))
'''
R3_NEW = '''        print(SEV_BAD + "  %d 个互不相干的插件日志在同一秒内停摆 ⇒ 停的是整个进程的"
              "帧循环，不是某一个插件的问题" % len(same))
        print("         注意：这只说明「所有写日志的东西同时停了」，不说明为什么停。")
        print("         停在哪里、是 GPU 还是 CPU —— 看 0b 段的运行段表。")
        note(SEV_BAD, "%d 个插件的日志同秒停摆 —— 进程级停摆（原因见 0b 段的运行段表）" % len(same))
'''

EDITS = [
    ("R1 add _parse_wd/_split_wd_runs/part_stalls", R1_OLD, R1_NEW),
    ("R2 call part_stalls() from main", R2_OLD, R2_NEW),
    ("R3 4c stops asserting 'Present' as the mechanism", R3_OLD, R3_NEW),
]

POST = [
    ("def part_stalls():", 1),
    ("def _split_wd_runs(recs):", 1),
    ("part_stalls()", 2),          # definition + call
    ("帧循环卡在 Present", 0),
    ("fence=(\\d+)/(\\d+)", 1),
]


def main():
    apply_it = "--apply" in sys.argv
    with open(TARGET, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    eol = "\r\n" if "\r\n" in text else "\n"

    print("target: %s" % TARGET)
    print("bytes before: %d (EOL=%s)" % (len(raw), "CRLF" if eol == "\r\n" else "LF"))
    print()

    if "def part_stalls(" in text:
        print("REFUSED -- already applied")
        return 2
    for m in ("4c. 焦点 / Present 死锁（v0.71）", "def _secs(", "WD_RE = re.compile"):
        if m not in text:
            print("REFUSED -- expected v0.71 reader not found (%r)" % m)
            return 2

    planned = []
    ok = True
    for label, old, new in EDITS:
        o = old.replace("\n", eol)
        n = text.count(o)
        if n != 1:
            print("%-46s anchor x%d  <== REFUSED" % (label, n))
            ok = False
            continue
        planned.append((label, o, new.replace("\n", eol)))
        print("%-46s anchor x1" % label)
    if not ok:
        print("\nREFUSED, nothing written.")
        return 2

    out = text
    for _l, o, n in planned:
        out = out.replace(o, n, 1)

    bad = []
    for needle, want in POST:
        got = out.count(needle)
        if got != want:
            bad.append("%r count=%d want=%d" % (needle, got, want))
    if bad:
        print()
        for b in bad:
            print("POST FAIL: %s" % b)
        print("REFUSED, nothing written.")
        return 2

    print()
    print("post-conditions: %d checks OK" % len(POST))
    print("%+d bytes" % (len(out.encode("utf-8")) - len(raw)))

    if not apply_it:
        print("\nDRY RUN -- nothing written. Re-run with --apply")
        return 0

    backup = TARGET + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(TARGET, backup)
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))
    back = open(TARGET, "rb").read().decode("utf-8")
    for needle, want in POST:
        if back.count(needle) != want:
            print("READBACK FAIL: %r" % needle)
            return 3
    print("readback OK | wrote %s (backup %s)" % (TARGET, os.path.basename(backup)))
    return 0


if __name__ == "__main__":
    # the reader uses `re` at module level; this script only needs it for its own
    # verification, so nothing to import beyond the stdlib above.
    import re  # noqa: F401  (kept for symmetry with the file it edits)
    sys.exit(main())
