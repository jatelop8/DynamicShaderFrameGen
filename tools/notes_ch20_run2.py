#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append chapter 20 to MFG_MASTER_NOTES.md (pure LF file).

Why this chapter exists: the user reported, in their own words, that the game
"cannot be entered" and that once the loading screen ends the picture will not
move while the music keeps playing. This chapter records what the 07:36 run
actually contains, with the raw lines, and is careful to mark the one causal
link the log cannot settle.

Dry run by default; --apply writes.
"""
import io
import sys

NOTES = "MFG_MASTER_NOTES.md"

ANCHOR = "\n\n---\n\n---\n---\n\n**本文件维护规则**"

CHAPTER = """---

## 第 20 章：4x 启动之后，重投影矩阵恒为单位变换 —— Transfusion 独立作证（2026-09-19 07:36 运行）

### 20.0 用户报告（原话，不改写）

> 游戏都进不去你让我怎么跑 直接加载界面结束进入游戏就不能动了 只有音乐

### 20.1 先排除一件事：这不是崩溃

watchdog 全程 `alive=1 focus=1`，`frames` 从 963 单调涨到 1041，
`stage` 在 `d3d11 Wait` / `cmdlist Reset` / `dlssg EvaluateDLSSG` 之间正常轮转，
`fence` 1924/1924 → 2080/2080 逐帧对齐，`queued` 交替 0/1。

崩溃转储为空：`SKSE/Crashlogs` 空、`NetScriptFramework/Crash` 不存在。
`DLSSG-Transfusion.crash.log` 29313 B 里**只有 1 条非 MODULE 行**，
而且它开头自己就写着：

    First-chance records are observations, not proof of a fatal crash.

**⇒ 用户的"不能动"是画面静止，不是进程挂起。** 这一点决定了后面整条推理的方向。

### 20.2 Transfusion 的独立证词 —— 本轮最硬的一条

`D:/ENB-EJ/Skyrim Special Edition/DLSSG-Transfusion.log`，07:37:57.364，tid=21204：

    [MOTION] route=slSetConstants call=0 viewport=0 transforms=game-preserved
             clipToPrev=identity prevToClip=identity projection=non-identity
             reset=1 cameraIncluded=1
    [MOTION] clipToPrev rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1] cameraPos=(0,0,1.00001001)

call=1 / call=2 / call=3 逐条相同（`rows[0][0]` = 0.99999994）。

**⇒ 送达 Streamline 的 `clipToPrevClip` 就是单位矩阵。**
这不是我对自家日志的解读 —— 是另一个进程在 hook 点上看到的同一份数据。
**⇒ 同时 `cameraPos=(0,0,1.00001001)`：位置字段在这条路径上恒为 `(0,0,1)`。**

### 20.3 同一时刻发生了什么：4x 真的启动了，然后帧率一路塌

    07:37:53.999  [PERF] 0x | FPS: 39.1 (25.55ms) | 1% Low: 38.9
    07:37:57.527  DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
    07:37:59.053  [PERF] 4x | FPS: 34.3 (29.15ms) | 1% Low:  9.8
    07:38:04.079  [PERF] 4x | FPS: 24.0 (41.63ms) | 1% Low:  9.7
    07:38:09.105  [PERF] 4x | FPS: 18.5 (54.11ms) | 1% Low:  9.7

**⇒ 4x 之前稳定 39 FPS；4x 之后 34.3 → 24.0 → 18.5，还在往下掉，1% Low 钉在 9.7。**

生成确实在执行（presentation count 4x），但输入的位移是单位矩阵
⇒ **生成的是上一帧的复制**；开销照付，收益为零 ⇒ 帧率单调下降。

**这就是"画面不动、声音照放"的完整机制。** 不是崩溃，是 4x 在做无效功。

### 20.4 `CameraPosAdjust` 的两个取值（同一个字段，两种状态）

来源已核实（不是推测）：

    src/FrameGen.cpp:640-642   const float px = a_src.CameraPosAdjust[0]; ...
    src/FrameGen.cpp:1012-1014 [CAM] acc 行的 pos= 就是它

**走动期间（07:37:46.334，[RAW] +0x0280 原文）：**

    [RAW] +0x0280 | -49.99428 891.753 95.28526 0 | -49.99497 892.2664 95.32975 0
    [CAM] raw #4501 pos=(-49.9943,891.7530,95.2853,0.0000) prevPos=(-49.9950,892.2664,95.3298,0.0000)

c80(cur) 与 c82(prev) **不同** ⇒ 位置是活的。

**4x 启动之后（07:38:06 起的每一条心跳）：**

    [CAM] acc #6407 pos=(0.00,0.00,1.00) move=0.0000 path=153.78 devVP=2.0001
    心跳：pos=(0.0,0.0,1.0) prevPos=(0.0,0.0,0.0)

125 条 `[CAM] acc` 的 pos 取值分布：`(0.00,0.00,1.00)` 42 次、
`(-50.00,600.00,80.00)`（菜单相机）47 次、其余为走动中的连续坐标。

**⇒ 它不是在"静止时自然落到 (0,0,1)"**：`(-49.99,891.75,95.29)` 与 `(0,0,1)`
相差约 900 单位，中间**没有任何过渡帧**。它是被换掉了，不是停下来了。

★ **因果边界**：4x 启动（07:37:57）与位置字段变 `(0,0,1)` **同时发生**。
本日志**不能区分**"4x 导致"与"同一事件的两个后果"。作为线索记录，**不作结论**。

### 20.5 我插的 v1.08 探针第三次打空

`[MOTION]` **0 行** —— 那条分支一次都没走到。
真正输出 w 的是 `src/FrameGen.cpp:691` 的另一条路径，共 24 条，从第 1 帧起就有：

    [07:37:33.141] [CAM] #1    non-affine w=0 ACCEPTED (v0.89) row3=(0,-0.991228,-0.132164,0) det3=-79.9373 pos=(-50.0,600.0,80.0)
    [07:38:08.706] [CAM] #12818 non-affine w=0 ACCEPTED (v0.89) row3=(-0.00391655,0.999991,0.0015,0) det3=-2.52504 pos=(-243.0,-415.3,118.6)

**⇒ 探针挂在了错误的触发条件上。** 这与 16.12 的 `mvecScale`、19.x 的 `path` 窗口
是同一类错误：**我按"我以为会走的路径"插桩，没有先证明那条路径真的会被走到。**

★ 注意 `w=0` 本身**不是缺陷**：`src/FrameGen.cpp:673-676` 已写明本引擎的相机块
携带透视项，`[3][3]==0` 合法。探针的用途是比对**两侧投影**，不是给 w 定罪。

### 20.6 与第 19 章结论的关系（修正一次口径）

19.x 说"8 条心跳全在 07:37:57 之后，运动窗口内 0 条"—— 那条**仍然成立**，
但当时的含义我写窄了。完整时间线是：

    07:37:33–45    主菜单（menu=903），pos=(-50,600,80)，move 恒 0.0000
    07:37:45.917   same-family step break dist=300.4 ⇒ 进入游戏世界
    07:37:46–54    走动，path 5.20 → 146.05，pos 连续变化
    07:37:57.364   4x 启动，同一刻 clipToPrev 变单位阵、cameraPos 变 (0,0,1)
    07:37:57–38:10 134 条 clipGate，clipDev 全 0.000000，det3 全 1.000000

**⇒ 那 134 条全 0 覆盖的是「4x 时段」，不是「静止时段」。**
它是 4x 路径上的读数 —— **恰恰是坏的那条路径**。
19.x 把它读成"静止所以正确"，**那是错的**。

### 20.7 立即恢复可玩（只改 INI，不动二进制）

    E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini
        Provider=0
        MFGMaxFramesOverride=0

依据是 Transfusion 自己记的：4x 之前的四条 `[PERF]` 是
**40.3 / 39.3 / 38.9 / 39.1 FPS，1% Low 38.9–39.0** —— 没有帧生成的 39 FPS 是稳的。
若仍不动，再在 MO2 取消勾选 `DynamicShaderFrameGen`，切到"无本插件"基线。

### 20.8 下一轮的第一件事（不是猜，是量）

在重投影之前，把**每一帧**的 c80/c82 与 CameraView/CameraProj 的指纹打进日志，
覆盖 4x 启动**前后各一秒**。要回答的只有一个问题：

> 4x 启动后的 `(0,0,1)` 是「引擎不再更新这个字段」，还是「我们读了另一份帧缓冲」？

判据：
- 若 c82 也变 `(0,0,0)` 而 c24 仍在变 ⇒ **字段停更**（引擎侧）；
- 若 c24 也冻结 ⇒ **我们读的不是引擎正在渲染的那份**（捕获侧）。

★ 以上全部是文档改动，**二进制未动**：DLL 仍为 `0a10b4b6…b613`。
"""


def main():
    apply = "--apply" in sys.argv
    raw = io.open(NOTES, "rb").read()
    src = raw.decode("utf-8")

    if "## 第 20 章" in src:
        print("REFUSED: chapter 20 already present")
        return 1
    n = src.count(ANCHOR)
    if n != 1:
        print("REFUSED: anchor count = %d (must be 1)" % n)
        return 1
    if raw.count(b"\r\n") != 0:
        print("REFUSED: file is no longer pure LF (%d CRLF)" % raw.count(b"\r\n"))
        return 1

    out = src.replace(ANCHOR, "\n\n" + CHAPTER + "\n---\n---\n\n**本文件维护规则**", 1)

    # post-conditions on the RESULT, not the input
    checks = [
        ("chapter 20 present", out.count("## 第 20 章") == 1),
        ("all sections", all(("### 20.%d" % i) in out for i in range(1, 9))),
        ("0.0 report quoted", "只有音乐" in out),
        ("transfusion rows quoted", "rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1]" in out),
        ("fps ladder", "FPS: 18.5 (54.11ms)" in out),
        ("c80 raw line", "-49.99428 891.753 95.28526 0" in out),
        ("probe miss recorded", "[MOTION]` **0 行**" in out),
        ("maintenance rule intact", out.count("**本文件维护规则**") == 1),
        ("no CRLF introduced", "\r" not in out),
        ("chapter 19 intact", out.count("## 第 19 章") == 1),
        ("chapter 18 intact", out.count("## 第 18 章") == 1),
    ]
    bad = [c for c, ok in checks if not ok]
    for c, ok in checks:
        print("  %-28s %s" % (c, "OK" if ok else "FAIL"))
    if bad:
        print("REFUSED: post-condition(s) failed: %s" % ", ".join(bad))
        return 1

    print()
    print("  old size %d B -> new size %d B (+%d)"
          % (len(raw), len(out.encode()), len(out.encode()) - len(raw)))
    if not apply:
        print("DRY RUN - nothing written (pass --apply)")
        return 0
    io.open(NOTES, "wb").write(out.encode("utf-8"))
    print("APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
