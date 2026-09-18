#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Correct skill section 40: its conclusion was machine-refuted on 2026-09-19.

Section 40 states that v1.07c's invert-site change IS the mechanism of the
back-and-forth loop. Chapter 17 of MFG_MASTER_NOTES.md refutes that: the two
candidate matrices are the same object, so the edit is a no-op on the live
path. Leaving the section uncorrected would mislead the next session, so the
correction is inserted directly UNDER the heading, before the old body, which
is preserved verbatim (never delete evidence, always annotate it).

Dry run by default; --apply writes. Anchors must occur exactly once.
"""
import io
import sys

SKILL = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
ANCHOR = ("## 40. ★★★★★ v1.07c：重投影矩阵的逆取自一台**没有平移**的相机 —— "
          "「来回循环」的机制 ★2026-09-18 实锤\n")
MARKER = "**⚠ 2026-09-19 更正：本节结论已被机器证伪"

FIX = MARKER + """，请不要按它动手。**

> **`tools/verify_v107c_is_inert.py`（退出码 0）证明：v1.07c 唯一的功能改动是空操作。**
> 那一步「换个矩阵取逆」的两个候选 —— `curForReproj`（即 `fixedViewProj`）与 `camCurVP` ——
> **归一化后 sha1 完全相同（`7fe156da9b20`），输入也相同**，是同一个对象；而那次运行的日志写的
> 是 `reproj src=fixed` ⇒ 走的正是这条路径。代数上也一致：`inv(P@A)@(P@B) = inv(A)@B`，
> 两侧共用同一个 P 时取哪个的逆**根本无所谓**（200 组随机样本偏差 `2.9e-13`）。
>
> **错因**：本节的依据是 `Streamline.cpp:1029-1032` 那句注释「carries NO translation」，
> 它写于 v0.66..v1.00；**v0.88 已把 984 行改成 `useFixed ? fixedViewProj : currViewProjSL`，
> 注释没跟着改。** 我把过期注释当成了代码。
>
> ⇒ 本节保留作为**证据**，但**不是结论**。正确的教训见 **§42**（改 A→B 前先证明 A≠B），
> 以及账本第 17 章。**当前对 `clipToPrevClip[3][3] = -195.22` 仍无解释**，
> 判它的读数见 **§43.3**（v1.08 的 `p00(c/p)` 探针）。

---
"""


def main() -> int:
    apply = "--apply" in sys.argv
    s = io.open(SKILL, "r", encoding="utf-8", newline="").read()
    raw = s.encode("utf-8")

    print("skill: %d B" % len(raw))
    print("marker already present: %d (must be 0)" % s.count(MARKER))
    print("anchor count: %d (must be 1)" % s.count(ANCHOR))
    if s.count(MARKER) != 0:
        print("REFUSED: correction already inserted")
        return 2
    if s.count(ANCHOR) != 1:
        print("REFUSED, nothing written")
        return 3

    out = s.replace(ANCHOR, ANCHOR + FIX)
    print("would grow %d -> %d B (+%d)"
          % (len(raw), len(out.encode("utf-8")), len(out.encode("utf-8")) - len(raw)))
    if not apply:
        print("(dry run: nothing written)")
        return 0

    io.open(SKILL, "w", encoding="utf-8", newline="").write(out)
    chk = io.open(SKILL, "r", encoding="utf-8", newline="").read()
    rb = chk.encode("utf-8")
    checks = [
        ("correction once", chk.count(MARKER) == 1),
        ("heading still once", chk.count(ANCHOR) == 1),
        ("43.3 forward-ref present", chk.count("§43.3") >= 1),
        ("no CRLF introduced", rb.count(b"\r\n") == 0),
    ]
    bad = 0
    for name, cond in checks:
        print("  %s %s" % ("OK  " if cond else "FAIL", name))
        if not cond:
            bad += 1
    print("final size: %d B  RESULT: %s" % (len(rb), "OK" if bad == 0 else "%d FAILED" % bad))
    return 0 if bad == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
