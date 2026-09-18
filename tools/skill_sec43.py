#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Append section 43 to the framegen-diagnosis skill.

Dry run by default; --apply writes. Anchor must occur exactly once.
The skill is pure LF (324314 B, CRLF=0 as measured 2026-09-19 00:3x).
"""
import io
import sys

SKILL = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
ANCHOR = ("4. 与 §112 的分工：**§112 管对照实验（两支接线要不同），"
          "本节管产品代码本身（改前改后要不同）**\n")
MARKER = "## 43. ★★★★★ 只加读数的「探针」补丁"

SEC43 = """
---

## 43. ★★★★★ 只加读数的「探针」补丁：纯增量的机器证明 + 诊断量的选择 ★2026-09-19 实锤

### 43.1 「只看不改」是声称，不是证据 —— 探针必须被机器证明是纯增量

补丁自述「我只加了读数」时，用两个互补的检查把它变成可重跑的结论：

| 形式 | 做法 | 强度 |
|---|---|---|
| **可逆性** | 对补丁做**逆替换**（new→old），结果必须与改前**逐字节相同** | **最强**：任何功能语句被碰过都不可能过 |
| **新增行审计** | diff 出新增行，逐条匹配白名单（注释 / 声明 / 日志 / 本地测量变量） | 强：能抓住「顺手改了一行没报」 |

本工程样板：`tools/verify_v108_probe_inert.py`（退出码 0）
—— A 段还原出 v1.07c 的 120866 B / 20686 B，B 段给 67 行新增逐条分类，
断言 **无一条落在 `c.*` / `cam*` / `prev*` 上**。

**★ 审计器自己也要自证在工作。** B 段第一次跑就报 FAIL 然后「通过」了一个空结论：
文本模式下 universal newlines 把 `\\r\\n` 吃成 `\\n`，`split("\\r\\n")` 返回**单元素列表**，
于是「遍历新增行」实际遍历了 1 个元素（整个文件），审计退化成空操作。
修法：一律 `io.open(p,"rb").read().decode("utf-8").split("\\r\\n")`，
并加一条 **「拆分后行数必须 > 100」** 的守卫。

> **凡是从「遍历/搜索后没发现问题」得出的结论，先证明遍历真的发生了。**

### 43.2 门控铁律第三条：证明它是「你读它的那一刻」所代表的那一帧

原有两条：① 判据必须会变化；② 用僵死常量当门 = 空操作（v1.02c）。**新增第三条**：

**中间变量会被就地覆盖。在远处读它，读到的可能根本不是你以为的那一帧。**

实例（`Streamline.cpp`）：

```
 748  if (camCurOk) {
 750      s_prevCamProj = a_fb.CameraProj;      ← 本帧值，在这里就被写掉
 ...
1202  diag.clipW = c.clipToPrevClip[3].w;      ← 在这里读，拿到的是「本帧」
```

若在 1202 处把 `s_prevCamProj` 当「上一帧投影」用，比较的两边**都是本帧** ⇒ 恒等 ⇒
**判据永不分歧**。这是 v1.02c「僵死常量」的**镜像**：那次是永不变化，这次是读到的时候已经换了。

**做法**：在覆盖发生**之前**快照到另一个变量，并把**顺序本身**写成断言：

```python
("snapshot taken before overwrite",
 cpp.index("s_probePrevProj = s_prevCamProj;") < cpp.index("s_prevCamProj = a_fb.CameraProj;"))
```

（脚本里已有：插入骨架先用 `# v1.08 PROBE` 之类的**唯一 marker** 做幂等守卫，别只依赖 `count(old)==1`。）

### 43.3 诊断量的选择：**一个候选对一个读数**

加探针之前先列表：

| 候选解释 | 它的**独有**签名 | 用什么读 |
|---|---|---|
| (a) 两侧投影不同 | 两侧**投影**读数不一致 | `Proj[0][0]` 两侧 |
| (b) 投影相同、逆近奇异 | 投影一致而 `mag(inv)` 巨大 | `finiteMagOf(inv)` |

**只有当两个候选只在一个数上分歧时，才加那一个数。** 堆一堆指标的真实代价是：
下一次要花更多时间去判断哪些指标没有意义，而且它们会互相污染判读。

**★ 读数要在正确的抽象层上取。** 本例要判「两侧投影是否同族」，就必须读**投影矩阵**：

```
(P@V)[0][0] = P[0][0] * V[0][0]      ← V[0][0] 是旋转元素，随朝向每帧变
```

若图省事读 ViewProj 的 `[0][0]` 当族指纹 ⇒ 玩家一转视角它就变 ⇒
**把「恒变量的当判据」反过来犯成「拿恒变的量当指纹」。**
（配一个正交/透视判别 `Proj[2][3]`：正交恒 0、透视非 0，两者**互相独立**，
一个用正交投影的 3D 菜单相机会在两个数上同时暴露。）

> **取任何一个量之前先问：它由哪些东西决定？我要测的那一项，是不是其中唯一会变的一项？**

### 43.4 ★★★ 解析器对「无法解析的输入」必须尖叫

```python
re.findall(r"clipDev=([\\d.]+)", line)      # 错：负号不匹配
```

`clipDev` 一旦为负（`-195.22` 这种值真的出现过），**整行**匹配失败 ⇒
该节打印 `NO DATA` ⇒ **一个异常读数被静默翻译成「没有数据」。**

**空集在判读层看起来和「健康」一模一样。** 三条规则：

1. 数值解析一律带符号 `([-\\d.]+)`，**把符号当作可能的信息**，不是噪声；
2. 「解析不到」与「解析到一个正常值」在输出上**必须可区分**（`NO DATA` ≠ `OK`）；
3. 若某个量在数学上不可能为负（如 `max|I - M|`），**负值本身就是一条 findings**：
   单独报「指标本身坏了」，并且**排除出其他分桶** ——
   否则 `-195` 会被算进「接近 0」的桶里，**凭空造出一次假交替**。

本工程这是**第三次**同一类错误：`move=0.0000`（§16.2c）、`jitter=(0,0)`（§16.12）、
`clipDev` 负号。三次的共同形状：**异常输入被静默降级成「无数据 / 正常」。**
（背景：这条是给**读别人的日志**用的 —— 日志字段是版本化的，见 §79。）

### 43.5 新判据上线前，用**合成样本**证明它会分歧（而且走同一套代码）

- 给判读脚本加**路径覆盖参数**（如 `--log PATH`），让回归喂合成日志走**同一套判读代码**；
  **不要复制一份实现** —— 复制的那一刻，你验证的是复制品，不是产品。
- 样本至少覆盖：候选 A 报 A、候选 B 报 B、健康时安静、**字段缺失报 NO DATA 而不是通过**。
- 本工程样板：`tools/regress_v108_p00.py`（CASE A/B/C/D/E，退出码 0）。

**★ 这类回归的真正价值常常不是验证新判据，而是当作判读代码的对抗测试** ——
本例正是那个「必须报 (b)」的样本（CASE B 第一次 FAIL），
逼出了 43.4 那个负号 bug。**一个「应该报错却没报」的输入，比一个「应该通过却通过」的输入有价值得多。**

★ 与 §112（回归脚本先自证两支不同）、技能第 42 节（改 A→B 前先证明 A≠B）同源：
**任何「我验证过了」的结论，都要先回答「如果它是错的，这次的输出会长什么样」。**

### 43.6 落地动作

1. 加探针前先写 **候选→签名 对照表**（43.3）；只加那个能把候选分开的数。
2. 探针落地后立刻跑 **可逆性 + 新增行审计**（43.1），并把断言写进补丁脚本的 post-condition。
3. 判读脚本的**解析正则**按 43.4 三条规则复查一遍（尤其符号、缺字段、不可能值）。
4. 新判据用**合成样本**跑一遍分歧实验（43.5），含一个「字段缺失」样本。
5. 顺序类风险（43.2）写成**索引比较断言**，别写在注释里。
"""


def main() -> int:
    apply = "--apply" in sys.argv
    s = io.open(SKILL, "r", encoding="utf-8", newline="").read()
    raw = s.encode("utf-8")

    print("skill: %d B, %d lines" % (len(raw), s.count("\n")))
    print("marker already present: %d (must be 0)" % s.count(MARKER))
    print("anchor count: %d (must be 1)" % s.count(ANCHOR))
    if s.count(MARKER) != 0:
        print("REFUSED: section 43 already written")
        return 2
    if s.count(ANCHOR) != 1:
        print("REFUSED, nothing written")
        return 3

    out = s.replace(ANCHOR, ANCHOR + SEC43)
    print("would grow %d -> %d B (+%d)"
          % (len(raw), len(out.encode("utf-8")), len(out.encode("utf-8")) - len(raw)))

    if not apply:
        print("(dry run: nothing written)")
        return 0

    io.open(SKILL, "w", encoding="utf-8", newline="").write(out)
    chk = io.open(SKILL, "r", encoding="utf-8", newline="").read()
    rb = chk.encode("utf-8")
    checks = [
        ("marker once", chk.count(MARKER) == 1),
        ("43.1..43.6 present", all(chk.count("### 43.%d" % i) == 1 for i in range(1, 7))),
        ("old tail kept once",
         chk.count("本节管产品代码本身（改前改后要不同）") == 1),
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
