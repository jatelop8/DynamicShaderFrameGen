#!/usr/bin/env python3
"""Append section 14 to the 2026-09-18 daily log (append-only, marker-guarded).

Dry run by default; --apply writes.
"""
import io
import sys

TARGET = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-18.md"
MARKER = "## 14. 23:25–23:32"

SECTION = """

## 14. 23:25–23:32 —— 收尾：我把 16.12 从「已核实为 0」改成「死字段」（差点写错的结论）

### 14.1 起草时写错的那一条

起草 16.12 时我准备写：「**jitter = 0，实测 8 条心跳全为 0，所以这不是待查项**」。
理由听着很顺：`camCurVP` 用 `CameraProj`（jittered）、`curForReproj` 用
`CameraViewProjUnjittered`，本来可以让「静止时 == I」不成立，既然 jitter 是 0，就没差别。

**核过之后结论是反的：那个字段根本没有写者。**

### 14.2 核实过程（可复现）

```bash
cd /d/Modding/DynamicShaderFrameGen
grep -rn "jitterX\\|jitterY" src/ --include=*.cpp --include=*.h | grep -v src/backup-
#   src/FrameGen.h:186:      float jitterX = 0.0f;      <- 唯一一次出现在等号左边
#   src/FrameGen.h:187:      float jitterY = 0.0f;
#   src/Streamline.cpp:1231: c.jitterOffset = { -Get().jitterX, -Get().jitterY };  <- 读
#   src/Streamline.cpp:1386: Get().jitterX, Get().jitterY, ...                     <- 读
```

**⇒ 1 处声明（初值 0）+ 2 处读取 + 0 处写入。** 三处源码自己写着原因：
`src/Streamline.h:62`（"v0.50 removed OnMainUpdateJitter, which was the ONLY writer"）、
`src/FrameGen.h:216`（"Halton jitter 已全部拔掉"）、`src/main.cpp:33`（"保留但不调用"）。

⇒ **8 条心跳全 `(0.0000,0.0000)` 是必然，零信息量。**
**与 16.2(c) 的 `move=0.0000` 同类：坏仪表。**
★ 16.2(c) 已经吃过一次 —— 我拿 `move=0` 推出"发布的相机原地不动"，整章作废。
**同一个错隔几小时又来一遍，只是换了字段名。**

### 14.3 但"记下"不够：它指向一个活着的消费者

`Streamline.cpp:1231` **仍在往 SL 喂 `c.jitterOffset = {0,0}`** —— 死字段在给运行时提供输入。
这正是 v0.50 那个 bug 的形状（唯一写者被删 ⇒ 字段恒为初值 ⇒ `slSetConstants` 每帧被拒 ⇒
每帧重投影都坏）。**同一个错法在同一文件里已经发生过一次，没有理由认为只发生过一次。**

**待查（下一轮）**：两个 provider 用的是两个不同的 jitter 源 ——
`src/FidelityFX.cpp:175-176` 自己算 `gameViewport->projectionPosScaleX/Y`，
SL 路径读的却是死字段。下次运行先看 `mvecScale` **在运动中是否变化**
（它是活的，本条心跳恒 `(1.000,1.000)`），以区分"引擎确实不 jitter"与"这条链也死了"。

### 14.4 判据 3 的阈值：`clipDev < 1e-3`，不写 0

实测下限：`0.000061` 出现 7 次、`0.000023` 出现 2 次；Transfusion 打印的合法 identity 帧
`rows=[0.99999994 …]` 与 1 的偏差是 6e-8 量级 ⇒ identity 的真实下限在 1e-5 量级。

### 14.5 本轮落盘

| 项 | 值 |
|---|---|
| 账本 | `MFG_MASTER_NOTES.md` 80111 → **83051 B**（纯 LF，CRLF=0），新增 16.12 / 16.13 |
| 补齐脚本 | `tools/notes_ch16b_jitter.py`（**重写过**；第一版内容是错的，"anchor unique + marker guard" 12 项后置检查全 OK） |
| 技能 | `framegen-diagnosis/SKILL.md` 第 40 节 **已在**（23:24 落盘，重跑被 marker 拒绝，符合预期） |
| 游戏侧 | **未开游戏**。v1.07c 是否真的不再"来回循环"仍未知 |
| 工作区 MEMORY.md | 已在上一步（sec13）瘦身为 4667 B 索引式，系统那条"超限"提醒是**会话开头**的快照，已过时 |
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    crlf = raw.count(b"\r\n")
    text = raw.decode("utf-8")
    print(f"daily log  {len(raw)} B  CRLF={crlf}")
    if MARKER in text:
        print("REFUSED, nothing written: section 14 already present")
        return 1
    out = text.rstrip("\n") + SECTION
    checks = [
        ("14 present", "## 14. 23:25" in out),
        ("only one 14", out.count("## 14. 23:25") == 1),
        ("13 still present", "### 13.9" in out),
        ("13.9 remains the earlier section",
         out.index("### 13.9") < out.index("## 14. 23:25")),
        ("refutation recorded", "0 处写入" in out),
        ("consumer recorded", "死字段在给运行时提供输入" in out),
        ("threshold recorded", "clipDev < 1e-3" in out),
    ]
    print()
    bad = 0
    for label, ok in checks:
        print(f"  {'OK  ' if ok else 'FAIL'} {label}")
        if not ok:
            bad = 1
    if bad:
        print("\nREFUSED, nothing written (post-condition failed)")
        return 1
    print(f"\nbytes {len(raw)} -> {len(out.encode('utf-8'))}")
    if not apply_changes:
        print("\nDRY RUN - nothing written. Re-run with --apply to write.")
        return 0
    with io.open(TARGET, "wb") as fh:
        fh.write(out.encode("utf-8"))
    r = io.open(TARGET, "rb").read()
    print(f"\nWROTE  {len(r)} B  CRLF={r.count(b'\r\n')}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
