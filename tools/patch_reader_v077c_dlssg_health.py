#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.77 part 3: add part_dlssg_health() to read_xray_log.py.

WHY THIS IS THE MOST IMPORTANT SECTION IN THE REPORT
----------------------------------------------------
Five rounds of diagnosis looked for a crash / deadlock / stall. The 08:27 run
finally answers the actual question, and the answer is not a crash:

    [FrameGen] DLSSG diag: fgOn=true dlssgOk=false token=0x... fail=1      x32
    [FrameGen] DLSSG diag: dlssgOk=true                                    x3
    [Streamline] MFG probe: runtime REJECTED 4x (result 38 = eErrorInvalidState)
    [Streamline] MFG probe: runtime REJECTED 3x (result 38 = eErrorInvalidState)
    [Streamline] MFG probe: runtime ACCEPTED 2x | runtimeReportsMax=2x
    FPS probe: real=58.4 ... accepted=0        <- for a full minute
    FPS probe: real=52.6 ... accepted=2        <- only after 08:29:01

So frame generation was OFF for almost the entire session, and NOTHING in the
current report says so. Every existing section reads camera matrices, swapchain
state, and thread health - all of which were fine. This section is the one that
answers "did the thing we are trying to build actually run?".

It also cross-references:
  - the `cap~=N (=real*2, COMPUTED not measured)` self-labelling, which proves
    the fps numbers in the log are NOT measurements of generated frames;
  - the MFG ladder, to show where the runtime's ceiling actually is.

Dry run by default; --apply to write.
"""
import os
import sys
import shutil
import datetime
import ast

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, "read_xray_log.py")

# Insert the new section right before part_verdicts' definition.
ANCHOR_FN = "def part_verdicts(lines):"

NEW_FN = '''def part_dlssg_health(lines):
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
    probes = []
    for ln in lines:
        if "[FrameGen] FPS probe:" not in ln:
            continue
        m = re.search(r"\\[([0-9:.]+)\\]", ln)
        wall = m.group(1) if m else "?"
        mr = re.search(r"real=([0-9.]+)", ln)
        ma = re.search(r"accepted=(\\d+)", ln)
        mh = re.search(r"hwMax=(\\d+)", ln)
        mask = re.search(r"ask=(\\d+)", ln)
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
    comp = [ln for ln in lines if "COMPUTED not measured" in ln]
    if comp:
        print()
        print("  [信息]日志自己把倍率标为 COMPUTED not measured 的行：%d 条" % len(comp))
        print("         ⇒ `cap~=real*2` 是**算出来的**，不是测出来的。")
        print("            所以日志里的 fps 不能当作「插帧真的跑起来了」的证据；")
        print("            唯一可信的产出判据是 accepted= 与实际呈现统计。")

    # ---- 4. the MFG ladder ----
    rej = [ln for ln in lines if "MFG probe: runtime REJECTED" in ln]
    acc = [ln for ln in lines if "MFG probe: runtime ACCEPTED" in ln]
    rmax = [ln for ln in lines if "runtimeReportsMax=" in ln]
    print()
    print("  [信息]MFG 梯子：拒绝 %d 次 / 接受 %d 次" % (len(rej), len(acc)))
    for ln in rej[-4:]:
        print("         %s" % ln.strip())
    for ln in acc[-2:]:
        print("         %s" % ln.strip())

    runtime_max = None
    if rmax:
        m = re.search(r"runtimeReportsMax=(\\d+)x", rmax[-1])
        if m:
            runtime_max = int(m.group(1))
        ask = re.search(r"overrideAsksMax=(\\d+)x", rmax[-1])
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


'''

EDITS = [
    ("insert part_dlssg_health()", ANCHOR_FN, NEW_FN + ANCHOR_FN),
    ("call it from main()", "    part_verdicts(lines)",
     "    part_dlssg_health(lines)\n    part_verdicts(lines)"),
]

CANARIES = [
    ("def part_dlssg_health(lines):", 1),
    ("    part_dlssg_health(lines)", 1),
    ("def part_verdicts(lines):", 1),
    ("9x. DLSS-G 实际产出", 1),
]

MARKERS = [
    "v0.77: did frame generation actually produce frames?",
    "9x. DLSS-G 实际产出（v0.77：accepted= / dlssgOk= / MFG 梯子）",
]


def main():
    apply = "--apply" in sys.argv
    src = open(READER, "r", encoding="utf-8", newline="").read()
    for m in MARKERS:
        if m in src:
            print("REFUSED: marker already present -> already applied: %r" % m)
            return 2

    text = src
    for label, old, new in EDITS:
        n = text.count(old)
        if n != 1:
            print("REFUSED: anchor for %r found %d times (want exactly 1)" % (label, n))
            return 2
        text = text.replace(old, new)

    for c, want in CANARIES:
        n = text.count(c)
        if n != want:
            print("REFUSED: canary %r found %d times (want %d)" % (c, n, want))
            return 2

    for m in MARKERS:
        if m not in text:
            print("REFUSED: marker missing after patch: %r" % m)
            return 2

    try:
        ast.parse(text)
    except SyntaxError as e:
        print("REFUSED: not parseable after patch: %s" % e)
        return 2

    if ("\r\n" in src) != ("\r\n" in text):
        print("REFUSED: line-ending style changed")
        return 2

    if not apply:
        print("[dry-run] anchors unique, canaries OK, ast.parse OK")
        print("[dry-run] bytes %d -> %d (%+d)" % (len(src), len(text), len(text) - len(src)))
        print("[dry-run] re-run with --apply to write")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-%s" % (READER, stamp)
    shutil.copy2(READER, bak)
    with open(READER, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("applied to %s" % READER)
    print("backup: %s" % bak)
    print("bytes %d -> %d (%+d)" % (len(src), len(text), len(text) - len(src)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
