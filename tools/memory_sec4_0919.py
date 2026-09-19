#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append section 4 to memory/2026-09-19.md (append-only daily log).

Also annotates 3.5, whose premise is now out of date: the run did NOT fail
because the heartbeats missed the moving window - it failed because the 4x
path hands Streamline an identity reprojection matrix.

Dry run by default; --apply writes.
"""
import io
import sys

LOG = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md"
MARKER = "## 4. 09:05"

BLOCK = """## 4. 09:05　用户报告「进游戏不能动」—— 查到 4x 启动后重投影恒为单位阵

### 4.1 用户原话（不改写）

> 游戏都进不去你让我怎么跑 直接加载界面结束进入游戏就不能动了 只有音乐

**我上一轮的问法错了。** 我问的是「走动那 8 秒画面有没有来回循环」，而用户的症状是
「根本不能动」。日志里 08:00 之后没有任何文件被写过 ⇒ 用户说的就是 **07:36 那一次**运行。

### 4.2 先排除崩溃（结论：不是崩溃）

watchdog 全程 `alive=1 focus=1`，`frames` 963 → 1041 单调增长，
`stage` 在 `d3d11 Wait` / `cmdlist Reset` / `dlssg EvaluateDLSSG` 之间正常轮转，
`fence` 1924/1924 → 2080/2080 逐帧对齐，`queued` 交替 0/1。
`SKSE/Crashlogs` 空、`NetScriptFramework/Crash` 不存在；
`DLSSG-Transfusion.crash.log`（29313 B）**只有 1 条非 MODULE 行**，且它自己声明
"First-chance records are observations, not proof of a fatal crash"。
⇒ 是**画面静止**，不是进程挂起。

### 4.3 最硬的一条：Transfusion 独立作证

`D:/ENB-EJ/Skyrim Special Edition/DLSSG-Transfusion.log`，07:37:57.364，tid=21204：

```
[MOTION] route=slSetConstants call=0 viewport=0 transforms=game-preserved
         clipToPrev=identity prevToClip=identity projection=non-identity
         reset=1 cameraIncluded=1
[MOTION] clipToPrev rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1] cameraPos=(0,0,1.00001001)
```

call=1/2/3 逐条相同。⇒ **送达 Streamline 的 `clipToPrevClip` 就是单位矩阵**，
而且 `cameraPos=(0,0,1.00001001)`。这不是我读自家日志，是另一个进程在 hook 点看到的同一份数据。

### 4.4 FPS 同时塌陷

```
07:37:53.999  [PERF] 0x | FPS: 39.1 (25.55ms) | 1% Low: 38.9
07:37:57.527  DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
07:37:59.053  [PERF] 4x | FPS: 34.3 (29.15ms) | 1% Low:  9.8
07:38:04.079  [PERF] 4x | FPS: 24.0 (41.63ms) | 1% Low:  9.7
07:38:09.105  [PERF] 4x | FPS: 18.5 (54.11ms) | 1% Low:  9.7
```

⇒ 生成在执行，但位移是单位阵 ⇒ **生成的是上一帧的复制**；开销照付、收益为零 ⇒ 帧率单调下降。
**这就是「画面不动、声音照放」。**

### 4.5 `CameraPosAdjust`(c80) 的两种取值

来源已核实：`src/FrameGen.cpp:640-642  const float px = a_src.CameraPosAdjust[0];`
（`[CAM] acc` 行的 `pos=` 就是它）。

- **走动期间**（`[RAW] +0x0280 原文`）：`-49.99428 891.753 95.28526 0 | -49.99497 892.2664 95.32975 0`
  —— c80 与 c82 **不同** ⇒ 位置是活的。
- **4x 启动后**：每一条心跳都是 `pos=(0.0,0.0,1.0) prevPos=(0.0,0.0,0.0)`。

`(-49.99,891.75,95.29)` 与 `(0,0,1)` 相差约 900 单位，**中间没有任何过渡帧** ⇒ 是被换掉了，不是停下来了。
★ **因果边界**：4x 启动与变值**同时发生**，本日志**不能**区分「4x 导致」与「同一事件的两个后果」。**记为线索，不作结论。**

### 4.6 我插的 v1.08 探针第三次打空

`[MOTION]` **0 行**。真实输出 w 的是 `src/FrameGen.cpp:691` 的另一条路径，共 24 条，从第 1 帧起就有：

```
[07:37:33.141] [CAM] #1     non-affine w=0 ACCEPTED (v0.89) row3=(0,-0.991228,-0.132164,0) det3=-79.9373 pos=(-50.0,600.0,80.0)
[07:38:08.706] [CAM] #12818 non-affine w=0 ACCEPTED (v0.89) row3=(-0.00391655,0.999991,0.0015,0) det3=-2.52504 pos=(-243.0,-415.3,118.6)
```

⇒ **探针挂在了错误的触发条件上**。与 16.12 的 `mvecScale`、19.x 的 `path` 窗口同类：
**插桩前没有先证明那条路径真的会被走到。**
★ `w=0` 本身**不是缺陷**：`FrameGen.cpp:673-676` 写明本引擎相机块带透视项，`[3][3]==0` 合法。

### 4.7 已改用户环境（让他先能玩）

```
E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini
    Provider=1 → 0
    MFGMaxFramesOverride=3 → 0
备份：DynamicShaderFrameGen.ini.bak_20260919_090521
```

字节数不变（14525 → 14525），行尾纯 CRLF 保持（259 CRLF / 0 bare LF）。
依据：**4x 之前的 39 FPS 是稳的**。

### 4.8 下一轮的第一件事（不是猜，是量）

把**每一帧**的 c80/c82 与 CameraView/CameraProj 指纹打进日志，覆盖 4x 启动**前后各一秒**。只回答一个问题：

> 4x 启动后的 `(0,0,1)` 是「引擎不再更新这个字段」，还是「我们读了另一份帧缓冲」？

判据：c82 也变 `(0,0,0)` 而 c24 仍在变 ⇒ **字段停更**；c24 也冻结 ⇒ **读的不是引擎正在渲染的那份**。

### 4.9 对 3.5 的更正（保留原文，标注作废）

3.5 说「`N = 0` 即这趟白跑」—— 那个前提**不完整**。
真正的问题是 **134 条 `clipGate` 的 `clipDev` 全为 0，而它们全部落在 4x 时段**（07:37:57 起）。
19.x 把这批读数读成「静止所以正确」，**错了**：它们是 **4x 那条坏路径**上的读数。
所以第 19 章关于「这趟测不到」的结论方向对、口径要改。详见账本第 20 章。

---
"""


def main():
    apply = "--apply" in sys.argv
    raw = io.open(LOG, "rb").read()
    src = raw.decode("utf-8")

    if MARKER in src:
        print("REFUSED: section 4 already present")
        return 1
    if raw.count(b"\r\n") != 0:
        print("REFUSED: log is no longer pure LF")
        return 1
    anchor = "`N = 0` 即这趟白跑。**\n"
    if src.count(anchor) != 1:
        print("REFUSED: anchor count = %d" % src.count(anchor))
        return 1

    out = src.replace(anchor, anchor + "\n" + BLOCK, 1)

    checks = [
        ("section 4 header", out.count(MARKER) == 1),
        ("user quote", "只有音乐" in out),
        ("transfusion rows", "rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1]" in out),
        ("fps ladder", "FPS: 18.5 (54.11ms)" in out),
        ("c80 raw", "-49.99428 891.753 95.28526 0" in out),
        ("ini change", "Provider=1 → 0" in out),
        ("probe miss", "第三次打空" in out),
        ("3.5 correction", "对 3.5 的更正" in out),
        ("no CRLF", "\r" not in out),
        ("old text intact", out.count("即这趟白跑") == 2),
    ]
    bad = [c for c, ok in checks if not ok]
    for c, ok in checks:
        print("  %-24s %s" % (c, "OK" if ok else "FAIL"))
    if bad:
        print("REFUSED: %s" % ", ".join(bad))
        return 1

    print()
    print("  %d B -> %d B (+%d)" % (len(raw), len(out.encode()), len(out.encode()) - len(raw)))
    if not apply:
        print("DRY RUN - nothing written")
        return 0
    io.open(LOG, "wb").write(out.encode("utf-8"))
    print("APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
