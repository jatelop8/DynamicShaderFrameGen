#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_skill50_gate.py -- fix the §49 heading level and append §50 (L28) to the
`framegen-diagnosis` skill.

Why: the skill's convention is `## N. Title` + `### N.x`, but §49 was appended as
three bare `## 49.x` headings with no parent -- so it reads as three top-level
sections. Fixed here, and the new root cause ㉑ goes in as a proper §50.

Same conventions as the rest of this project: dry run by default, --apply writes,
anchor count must be exactly 1, idempotency marker, post-conditions on the RESULT.
"""
import sys

SKILL = ("C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md")

MARK = "## 50. \u6839\u56e0\u3251"

# ---- edit 1..3: demote the three orphan ## 49.x headings ------------------- #
H49_PARENT_OLD = "## 49.1 \u6839\u56e0\u2472"
H49_PARENT_NEW = (
    "## 49. 2026-09-19 新增：部署源、4x 的真假、L0 的两个新检查项\n"
    "\n"
    "### 49.1 \u6839\u56e0\u2472"
)

H49_2_OLD = "## 49.2 \u6839\u56e0\u2473"
H49_2_NEW = "### 49.2 \u6839\u56e0\u2473"

H49_3_OLD = "## 49.3 L0 第二遍的两个新检查项"
H49_3_NEW = "### 49.3 L0 第二遍的两个新检查项"


S50 = """

---

## 50. 根因\u3251 ★★★★★ 「门」被它要检测的故障本身清零（L28，2026-09-19 14:20 那局）

**症状**：`matChanges` 冻在一个常数、`clipDev=0.000061`、`prevPos == pos` —— 即
**发布出去的相机不变** ⇒ `clipToPrevClip` = I ⇒ 插的 3 帧是复制品。画面静止，帧数照涨。

**判据链（一条一条读，不要跳）**

1. `presented world=0/10/0/0/56/0/0/0` 配 `hwMax=6 ask=4 accepted=4` ⇒ **4x 真的在插**。
   `accepted` 是 `dlssgAcceptedFrames+1`（测量值）。**"4x 没成功"和"插了但插的是复制品"是两件事。**
2. `matChanges` 长期不变而 `famRej` 持续上涨 ⇒ **发布流死了，到达流是活的**。
3. `lock(pub/hold/re/still)=149766/34951/274/0` —— `hold ≈ famRej` 正常，
   但 **`still` 停在个位数（3~8）就是本根因的指纹**：它本该累积到阈值却一直归零。
4. 冻结族的 `pos` 与**两天前另一局**的 `cameraPos` 逐位相同 ⇒ 那是**场景固定相机**，不是玩家相机。
   活相机（`proj00=1`）以 ~100/s 被拒。

**根因**：接管门写成 `snapLockStill >= 30`，而 `snapLockStill` 被**每一次 accept** 清零
（`FrameGen.cpp:1073` 的 `continues` 分支 / `:1069` step break / `:933` acquire）。
静止族以 `d2 == 0` 到达自己的上一个到达点 ⇒ `continues` 真 ⇒ 被接受 ⇒ 计数归零。
**故障把检测它的那个计数器擦掉了，于是门永远打不开。**

**修法（v1.11）** —— 门改盯**发布流的直接测量**，不再用到达侧的代理计数：

```cpp
// FrameGen.h
std::uint64_t snapPubStale = 0;                 // 连续多少次发布矩阵逐字节相同
// 发布点：全文唯一的清零点
if (!same) { ++snapMatChanges; snapPubStale = 0; }
else       { ++snapPubStale; }
// 门
if (snapPubStale >= kCamPubStaleTol &&          // 200 ≈ 1.3 s 的"可证死"流
    snapForeignMove >= kCamForeignMoveTol) {    // 第二条件不变：停住的族没有位移
```

**为什么第二条件一个字不能改**：它才是安全性来源。停住的族贡献不了位移，
所以"玩家本来就站着不动"（此时 identity 的 `clipToPrev` **是对的**）永远夺不走 anchor。

**L28 通用形式 —— 写任何"门"之前先问：**

> **被检测的故障本身，会不会把这个检测器的计数清零？**
>
> 判据不是"这个门看起来合理"，而是**走一遍故障路径，看这个计数器还在不在**。
> 操作化两条：
> 1. 在补丁脚本里**断言清零语句在全文恰好出现 1 次**；
> 2. 断言那个唯一的清零点落在**健康事件**分支上（矩阵真的变了 / 流真的在前进），
>    而不是落在"这一帧看起来正常"的分支上。

**别把"接管门"和"释放路径"混为一谈**：`release`（reset / menu 边）本身是好的；
问题在它把锁交给**"下一个到达"**，而下一个到达可能是静止的错族。
所以要修的不是 release，而是**让锁在 ~1.3 秒内自愈**。

**残余风险（未证）**：`snapPubStale` 在菜单里理论上也可能爆表并把 anchor 交给菜单相机；
只是那时还需要"被拒族自己走出 ≥200 单位"同时成立，而菜单里玩家相机本身在动，不容易触发。
"""

PLAN = [
    (H49_PARENT_OLD, H49_PARENT_NEW, "## 49. 2026-09-19 新增"),
    (H49_2_OLD, H49_2_NEW, "### 49.2 根因\u2473"),
    (H49_3_OLD, H49_3_NEW, "### 49.3 L0 第二遍"),
]


def main():
    do_apply = "--apply" in sys.argv
    with open(SKILL, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    if raw.count(b"\r\n"):
        eol = "\r\n"
    else:
        eol = "\n"
    print(f"--- {SKILL}  ({len(raw)} B, eol={eol!r})")

    if not do_apply:
        if MARK in text:
            print("    REFUSED: section 50 already present")
            return 1
    elif MARK in text:
        print("    REFUSED: section 50 already present")
        return 1

    for old, new, want in PLAN:
        o = old.replace("\n", eol)
        n = new.replace("\n", eol)
        c = text.count(o)
        print(f"    {want[:34]:36s} count={c}")
        if c != 1:
            print(f"    REFUSED, nothing written (want 1)")
            return 2
        text = text.replace(o, n, 1)

    payload = S50.replace("\n", eol)
    if not text.endswith(eol):
        payload = eol + payload
    text = text + payload

    # ---- post-conditions on the RESULT ----
    bad = []
    if MARK not in text:
        bad.append("section 50 missing")
    for w in ["### 49.1", "### 49.2", "### 49.3", "## 49. 2026-09-19 新增"]:
        if w not in text:
            bad.append(f"missing {w!r}")
    # NOTE a SUBSTRING test is the wrong tool here: the string "### 49.1"
    # CONTAINS "## 49.1" (the match starts at index 1), so `"## 49.1" in text`
    # reports a false positive on the very heading this patch just creates.
    # A heading check must be line-anchored:
    for ln in text.split(eol):
        if (ln.startswith("## 49.") and not ln.startswith("### ")
                and not ln.startswith("## 49. 2026-09-19 新增")):
            bad.append(f"orphan heading survived: {ln[:40]!r}")
    if "L28" not in text:
        bad.append("L28 absent")
    out = text.encode("utf-8")
    if eol == "\r\n" and (out.count(b"\n") - out.count(b"\r\n")) != (
            raw.count(b"\n") - raw.count(b"\r\n")):
        bad.append("EOL convention changed")
    print("post-conditions:", "PASS" if not bad else f"FAIL {bad}")
    if bad:
        print("REFUSED, nothing written")
        return 3

    if not do_apply:
        print("DRY RUN ok -- re-run with --apply to write")
        return 0

    with open(SKILL, "wb") as f:
        f.write(out)
    print(f"written: {len(raw)} B -> {len(out)} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
