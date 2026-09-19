#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append sections 46-47 to the framegen-diagnosis skill (pure LF file).

46: cross-process corroboration - find a witness that is NOT in your system
47: the three-times-empty probe - prove a path is walked before instrumenting it

Dry run by default; --apply writes.
"""
import io
import sys

SKILL = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"

ANCHOR = ("**⇒ 改任何日志格式串（横幅、字段名、分隔符）时，同步 grep 全部消费方**："
          "分析脚本、回归样本、\n技能里的示例、账本里的引文。**这些都不是编译器会替你检查的。**\n")

BLOCK = """
## 46. ★★★★★ 找一个「不在你系统里」的证人：跨进程交叉验证

当自家日志的读数有疑问时，最有价值的一步**不是再插一个探针**，
而是找**另一个进程**写下的、关于**同一份数据**的记录。

本项目的现成例子：`D:/ENB-EJ/Skyrim Special Edition/DLSSG-Transfusion.log`
（连同 `.crash.log`、`_perf.csv`）位于游戏根目录，由 `dinput8.dll`（Transfusion）写。
它 hook 了 `slDLSSGSetOptions` / `slSetConstants`，所以**它在 hook 点看到的，
就是我们真正交出去的那份数据** —— 不是我们以为自己交出去的数据。

2026-09-19 那趟，它把结论直接写了出来：

    [MOTION] clipToPrev=identity prevToClip=identity projection=non-identity reset=1 cameraIncluded=1
    [MOTION] clipToPrev rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1] cameraPos=(0,0,1.00001001)

同一份日志还自带测量：

    07:37:53.999  [PERF] 0x | FPS: 39.1 (25.55ms) | 1% Low: 38.9
    07:37:57.527  DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
    07:37:59.053  [PERF] 4x | FPS: 34.3 (29.15ms) | 1% Low:  9.8
    07:38:09.105  [PERF] 4x | FPS: 18.5 (54.11ms) | 1% Low:  9.7

**为什么它比自家日志更可信**：自家日志记的是"我打算送出去什么"，
它记的是"我在 hook 点实际收到了什么"。**两者不一致时，缺陷就在两者之间。**

**固定检查顺序**：
1. `<游戏根>/DLSSG-Transfusion.log` —— 找 `[MOTION]` / `[PERF]` / `[STARTUP]` / `[LOAD]`
2. `<游戏根>/DLSSG-Transfusion.crash.log` —— **先读第 2 行**：
   `First-chance records are observations, not proof of a fatal crash.`
   只有事件行才算事件；本次 29313 B 里只有 1 条 ⇒ 等于"没有崩溃"
3. `<游戏根>/DLSSG-Transfusion_perf.csv` —— 帧时间序列
4. **游戏根目录的时间戳本身也是证据**：哪个文件在运行中被写、写到几点

★ **通用规则：一个读数只要在自家系统里有疑问，就去它的下游找一个不在自家系统里的记录者。**
外部 hook、外部进程、被它消耗的文件、隔壁目录的日志 —— 至少有一个是别人写的。

## 47. ★★★★★ 探针三连空：插桩之前先证明那条路径会被走到

同一个错误在本项目犯了**三次**，三次都是「我以为会走那条路」：

| 探针 | 挂在哪 | 为什么是空的 |
|---|---|---|
| 16.12 `mvecScale` | 心跳字段 | 被 INI `MvecScaleOverride=1.00` 钉死，永远不会变 |
| 19.x 运动窗口 | `[CAM] acc path=` | **累计量**，`path>0` 恒真，窗口盖满全日志 |
| v1.08 投影探针 | `[MOTION]` 警告行 | **那条分支 0 行**；真实输出走 `FrameGen.cpp:691` 的 `non-affine`（24 条） |

**⇒ 加任何插桩前，先做这三步（顺序不能换）**：
1. **grep 打印点**，确认它属于哪条分支、触发条件是什么；
2. **在旧日志里 grep 该标记**，确认它在历史上**真的出现过**（次数 > 0）；
3. 若历史上从未出现 ⇒ 要么先让那条路径可达，要么**把探针挂到一定会走的分支上**。

★ 推论一：**在正确的分支上多插一个字段，胜过在新分支上插十个。**
★ 推论二：**触发条件本身就是判据**。0 行不等于"没问题"，而是"没测"。
  要把"没测"写进判据（参见 §41 读量三问、§45 的「`N = 0` 即白跑」）。
★ 推论三：探针的价值**不在于它读什么**，而在于**它什么时候被读到**。
  挂错分支的探针会给出一份漂亮的、完全无关的数据 —— 比没有探针更危险。
"""


def main():
    apply = "--apply" in sys.argv
    raw = io.open(SKILL, "rb").read()
    src = raw.decode("utf-8")

    if "## 46." in src:
        print("REFUSED: section 46 already present")
        return 1
    if raw.count(b"\r\n") != 0:
        print("REFUSED: skill file is no longer pure LF (%d CRLF)" % raw.count(b"\r\n"))
        return 1
    n = src.count(ANCHOR)
    if n != 1:
        print("REFUSED: anchor count = %d (must be 1)" % n)
        return 1

    out = src.replace(ANCHOR, ANCHOR + BLOCK, 1)

    checks = [
        ("section 46", out.count("## 46. ★★★★★") == 1),
        ("section 47", out.count("## 47. ★★★★★") == 1),
        ("witness rows quoted", "rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1]" in out),
        ("fps ladder quoted", "FPS: 18.5 (54.11ms)" in out),
        ("three probes table", out.count("v1.08 投影探针") == 1),
        ("crashlog caveat", "not proof of a fatal crash" in out),
        ("no CRLF", "\r" not in out),
        ("sections 40-45 intact", all(("## %d." % i) in out for i in range(40, 46))),
        ("old anchor text present", out.count("这些都不是编译器会替你检查的") == 1),
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
    io.open(SKILL, "wb").write(out.encode("utf-8"))
    print("APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
