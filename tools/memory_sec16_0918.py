#!/usr/bin/env python3
"""Append section 16 to the 2026-09-18 daily log (append-only, marker-guarded)."""
import io
import sys

TARGET = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-18.md"
MARKER = "## 16. 23:48"

SECTION = """

## 16. 23:48–00:05 —— 用户一句话逼出的证伪：**v1.07c 的功能改动是空操作**

### 16.1 触发

> **"所以这一次你从代码层面可以确定不会再犯之前得问题了么"**

答：**不能。** 而且按这句话去核代码，第一个发现就是 —— **上一轮那个"修复"改前改后是同一个矩阵。**

### 16.2 判定（`tools/verify_v107c_is_inert.py`，纯 Python、只读、退出码 0）

```
A. rebuildViewProj 860 chars sha1 7fe156da9b20
   fixedViewProj   860 chars sha1 7fe156da9b20   identical: YES   (输入也相同)
   -> camCurVP 与 fixedViewProj 是同一个矩阵
B1. max |inv(P@A)@(P@B) - inv(A)@B| = 2.878e-13      (共用 P 的逆选哪个无所谓)
B2. |old_result - new_result| = 0.000e+00
C. 四条路径穷举：只有 useFixed=false && camCurOk=true 才变；
   而 23:10 日志 `reproj src=fixed` ⇒ useFixed=true ⇒ 正是"空操作"那条
```

前两条锁死结论：
`curForReproj = useFixed ? fixedViewProj : currViewProjSL`，
`diag.reprojSource = useFixed ? 2 : 0`，打印 `==2 → "fixed"`（v1.07b 的 986 行 / 1351 行）。

### 16.3 我错在哪：**把过期注释当代码读**

16.3 节的全部依据是 `Streamline.cpp:1029-1032` 那句
"`curForReproj`, the engine-derived ViewProj, which carries NO translation"。
**那是 v0.66..v1.00 时代写的**（当时它确实是 `currViewProjSL`）。v0.88 改了 984 行、注释没改。
⇒ 我"证明"了一个在这条路径上不存在的缺陷，然后"修复"了它。**代价：一整轮 + 一次未来要跑的游戏。**

### 16.4 那 `-195.22` 呢？（仍未解释）

B3 段证明 `[3][3]` 是**两侧投影的比例**（共用 P ⇒ 恰为 1；另一侧乘 k ⇒ 精确等于 k）。
但已知世界/菜单族投影比 **5.62x** ⇒ 应给 `5.62` 或 `0.178`，**不是 -195.22**。
**所以连"族混用"也不足以解释它。** 可能是 `matrixFullInvert` 收近奇异输入后爆掉，
或守卫把上一帧 `s_lastGoodClip` 顶了上来 —— **这份日志里分不清**。

### 16.5 下一个读数（要改代码，一行）

每帧打 `curProj[0][0]`、`prevProj[0][0]`（`s_prevCamProj`）、`clipToPrevClip[3][3]`，外加两者是否同族。

### 16.6 新铁律（最重要的一条）

> **"修好一个东西"之前，先证明"改前 ≠ 改后"。**

**`tools/verify_v107c_is_inert.py` 是这条的样板**：可重跑、退出码 0/1。
与技能 §112（对照实验要先自证两支不同）是同一件事的两面 —— §112 管实验，本条管**产品代码本身**。

### 16.7 本轮落盘

| 项 | 值 |
|---|---|
| 账本 | `MFG_MASTER_NOTES.md` 87754 → **93931 B**（第 17 章 + 16.4 原位标注作废） |
| 验收卡 | `docs/acceptance-v1.07c.html` 加顶部更正条 / §3 更正 / §5 新增未解释项 / §11 foot 更正 |
| 新脚本 | `tools/verify_v107c_is_inert.py`（可复用自检） |
| 工作区 MEMORY.md | **首条已改写**（原"v1.07c 是真根因"是错的，会误导下个会话） |
| 游戏侧 | **仍未开游戏**；且结论是：跑 v1.07c = 再测一遍 v1.07b |
| 待决策 | (a) 照跑收集数据 vs (b) 先做 16.5 那行诊断 —— **已问用户** |
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    text = raw.decode("utf-8")
    print(f"daily log  {len(raw)} B  CRLF={raw.count(b'\r\n')}")
    if MARKER in text:
        print("REFUSED, nothing written: section 16 already present")
        return 1
    out = text.rstrip("\n") + SECTION
    checks = [
        ("16 present", MARKER in out),
        ("only one 16", out.count(MARKER) == 1),
        ("15 still present", "## 15. 23:33" in out),
        ("order 15 < 16", out.index("## 15. 23:33") < out.index(MARKER)),
        ("hash recorded", "7fe156da9b20" in out),
        ("inert recorded", "0.000e+00" in out),
        ("stale-comment cause recorded", "把过期注释当代码读" in out),
        ("new rule recorded", '先证明"改前 ≠ 改后"' in out),
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
