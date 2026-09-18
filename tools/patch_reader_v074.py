#!/usr/bin/env python3
"""Reader v0.74: parse queued= / lastPr= / dsync= and judge the GPU timeline.

The watchdog line becomes:
    [mono] hh:mm:ss.mmm frames= silent=ms stage= focus= fence=a/b stim=n \
           queued=N lastPr=N dsync=0|1

Why these three fields exist: the 07:11 run held fence=1/1 for 50 s while
frames climbed 1 -> 1614 and silent stayed at 5-27 ms. Every CPU-side field
was healthy; only the fence showed that the D3D12 queue never advanced.
These fields say WHICH of the three candidate paths did it:

  queued > 3        the CPU ran ahead of the GPU -> Present lost backpressure
  dsync = 1         frameIndex disagrees with DXGI's back buffer index
  lastPr not moving Present returns success without flipping

Default is a dry run. Pass --apply to write.
"""

import hashlib
import os
import shutil
import sys
import time

TARGET = "tools/read_xray_log.py"

MARKERS = [
    "def part_gpu_timeline(",
    "queued=%s lastPr=%s dsync=%s",
    "0d. GPU timeline",
]

# --------------------------------------------------------------------------
# R1: regex + record fields
# --------------------------------------------------------------------------

R1_OLD = '''#   v0.73  [mono] hh:mm:ss.mmm frames= silent=ms stage= focus= fence=a/b|-/- stim=n
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
'''

R1_NEW = '''#   v0.73  [mono] hh:mm:ss.mmm frames= silent=ms stage= focus= fence=a/b|-/- stim=n
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
#   dsync   1 when frameIndex no longer matches GetCurrentBackBufferIndex()
WD_RE = re.compile(
    r"^\\[(?P<ms>\\d+)\\]\\s+"
    r"(?:(?P<hh>\\d\\d):(?P<mm>\\d\\d):(?P<ss>\\d\\d)\\.(?P<msec>\\d{3})\\s+)?"
    r"frames=(?P<frames>\\d+)\\s+silent=(?P<silent>-?\\d+)ms\\s+stage=(?P<stage>.*?)"
    r"(?:\\s+focus=(?P<focus>-?\\d+))?"
    r"(?:\\s+fence=(?P<f11>\\d+|~0|-)/(?P<f12>\\d+|~0|-))?"
    r"(?:\\s+stim=(?P<stim>\\d+))?"
    r"(?:\\s+queued=(?P<queued>\\d+))?"
    r"(?:\\s+lastPr=(?P<lastpr>\\d+))?"
    r"(?:\\s+dsync=(?P<dsync>\\d+))?"
    r"\\s*(?P<stalled><==.*)?$")
'''

R2_OLD = '''        "stim": int(g["stim"]) if g["stim"] is not None else None,
        "stalled": bool(g["stalled"]),
    }
'''

R2_NEW = '''        "stim": int(g["stim"]) if g["stim"] is not None else None,
        # v0.74: the GPU-timeline fields. None (not 0) when absent, so a reader
        # can tell "this build never wrote it" from "it wrote a real zero".
        "queued": int(g["queued"]) if g.get("queued") is not None else None,
        "lastpr": int(g["lastpr"]) if g.get("lastpr") is not None else None,
        "dsync": int(g["dsync"]) if g.get("dsync") is not None else None,
        "stalled": bool(g["stalled"]),
    }
'''

# --------------------------------------------------------------------------
# R3: tuple in part_watchdog carries the new fields (indices 0..5 unchanged)
# --------------------------------------------------------------------------

R3_OLD = '''            recs.append((r["ms"], r["frames"], r["silent"], r["stage"], r["focus"],
                         r["stalled"], r["wall"], r["stim"], r["f11"], r["f12"]))
'''

R3_NEW = '''            recs.append((r["ms"], r["frames"], r["silent"], r["stage"], r["focus"],
                         r["stalled"], r["wall"], r["stim"], r["f11"], r["f12"],
                         r["queued"], r["lastpr"], r["dsync"]))
'''

# --------------------------------------------------------------------------
# R4: new section - judge the GPU timeline
# --------------------------------------------------------------------------

R4_ANCHOR = '''def part_verdicts(lines):
'''

R4_NEW = '''def part_gpu_timeline():
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


def part_verdicts(lines):
'''

# --------------------------------------------------------------------------
# R5: wire into main()
# --------------------------------------------------------------------------

R5_OLD = '''    part_watchdog()
    part_stalls()
    part_exit()
'''

R5_NEW = '''    part_watchdog()
    part_stalls()
    part_exit()
    part_gpu_timeline()
'''

EDITS = [
    ("R1 regex + field history", R1_OLD, R1_NEW),
    ("R2 record carries the fields", R2_OLD, R2_NEW),
    ("R3 tuple carries the fields", R3_OLD, R3_NEW),
    ("R4 new section: gpu timeline", R4_ANCHOR, R4_NEW),
    ("R5 call part_gpu_timeline", R5_OLD, R5_NEW),
]

SURVIVORS = [
    ("parse_wd_line", 4),
    # 2 is the real count (definition + the call in main()); asking for 3 was a
    # wrong expectation on my side, not a missing symbol.
    ("part_watchdog", 2),
    ("_split_wd_runs", 2),
    ("last_run_exit", 2),
]


def match_anchor(text, old, new):
    if text.count(old) == 1:
        return old, new, 1
    if "\r\n" not in old:
        swapped = old.replace("\n", "\r\n")
        if text.count(swapped) == 1:
            return swapped, new.replace("\n", "\r\n"), 1
    else:
        swapped = old.replace("\r\n", "\n")
        if text.count(swapped) == 1:
            return swapped, new.replace("\r\n", "\n"), 1
    return None, None, text.count(old) + text.count(swapped)


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(TARGET):
        print("REFUSED -- missing %s" % TARGET)
        return 1
    text = open(TARGET, encoding="utf-8").read()

    for m in MARKERS:
        if m in text:
            print("REFUSED -- already applied: %r" % m)
            return 1

    plan = []
    bad = 0
    for label, old, new in EDITS:
        anchor, repl, n = match_anchor(text, old, new)
        if anchor is None:
            print("REFUSED -- %-38s anchor x%d (want 1)" % (label, n))
            bad += 1
            continue
        plan.append((label, anchor, repl))
        print("ok       %-38s anchor x1" % label)
    if bad:
        print("REFUSED, nothing written")
        return 1

    out = text
    for label, anchor, repl in plan:
        assert out.count(anchor) == 1, label
        out = out.replace(anchor, repl, 1)

    checks = [
        ("regex has dsync", out.count("(?P<dsync>"), 1),
        ("regex has queued", out.count("(?P<queued>"), 1),
        ("record reads queued", out.count('r["queued"] if r.get("queued")'), 0),
        ("record field queued", out.count('"queued": int(g["queued"])'), 1),
        ("record field lastpr", out.count('"lastpr": int(g["lastpr"])'), 1),
        ("record field dsync", out.count('"dsync": int(g["dsync"])'), 1),
        ("tuple extends to 13", out.count('r["queued"], r["lastpr"], r["dsync"]))'), 1),
        ("section defined", out.count("def part_gpu_timeline():"), 1),
        ("section called", out.count("    part_gpu_timeline()"), 1),
        ("section titled 0d", out.count("0d. GPU timeline"), 1),
        ("fence-moved judgement", out.count("fence 恒为 %s"), 1),
        ("old WD_RE gone", out.count(r'r"^\[(\d+)\]\s+frames='), 0),
        ("old dup regex gone", out.count(r"fence=(\d+)/(\d+)"), 0),
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

    d = (out.count("(") - out.count(")")) - (text.count("(") - text.count(")"))
    print("%s     paren delta %d" % ("ok  " if d == 0 else "FAIL", d))
    if d != 0:
        ok = False

    if not ok:
        print("REFUSED, nothing written")
        return 1
    if not apply:
        print("\nDRY RUN ok -- %d edits; re-run with --apply" % len(plan))
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(TARGET, "%s.bak-%s" % (TARGET, stamp))
    with open(TARGET, "wb") as fh:
        fh.write(out.encode("utf-8"))
    back = open(TARGET, "rb").read()
    crlf = back.count(b"\r\n")
    lone = back.count(b"\n") - crlf
    print("wrote %-28s %7d B  md5=%s  lone_CR=%d  backup %s.bak-%s"
          % (TARGET, len(back), hashlib.md5(back).hexdigest()[:12], lone, TARGET, stamp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
