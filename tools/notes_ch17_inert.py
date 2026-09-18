#!/usr/bin/env python3
"""Chapter 17 + void marker on 16.4's fix bullet.  Pure LF file.

E1 (replace, consumes its anchor -> idempotent) : mark 16.4 item 1 as void.
E2 (insert before the maintenance rule -> the anchor is NOT consumed, so a
    marker guard on "## 第 17 章" is mandatory).

Dry run by default; --apply writes.
"""
import io
import sys

TARGET = "MFG_MASTER_NOTES.md"
MARKER = "## 第 17 章"

E1_OLD = "1. **取逆的源与 `prev` 同构**（唯一的功能修复）："
E1_NEW = ("1. ~~**取逆的源与 `prev` 同构**（唯一的功能修复）~~ "
          "**★ 第 17 章已证明这是一次空操作，本条作废**：")

E2_ANCHOR = "\n\n\n---\n\n---\n---\n\n**本文件维护规则**"

E2_ADD = """
## 第 17 章：v1.07c 的功能改动是**空操作** —— 我把「注释」当成了「代码」（2026-09-18 23:55）

### 17.1 起因：用户问了一句我一直回避的话

> **"所以这一次你从代码层面可以确定不会再犯之前得问题了么"**

**不能。** 而且按这句话去核代码，第一件事就发现：**上一轮那个"修复"在这条路径上什么都不改。**

### 17.2 机器判定的证据（`tools/verify_v107c_is_inert.py`，纯 Python 无依赖，只读）

```
=== A. same construction? ===
  rebuildViewProj   860 chars  sha1 7fe156da9b20
  fixedViewProj     860 chars  sha1 7fe156da9b20
  identical: YES
  rebuildViewProj inputs: a_fb.CameraView,a_fb.CameraPosAdjust,a_fb.CameraProj
  inline block inputs:    a_fb.CameraView, a_fb.CameraPosAdjust, a_fb.CameraProj   (same)

=== B1. same P on both sides ===
  max |inv(P@A)@(P@B)  -  inv(A)@B| = 2.878e-13   over 200 random rotation pairs

=== B2. what v1.07c actually moved ===
  |old_result - new_result| = 0.000e+00

=== C. path enumeration ===
  case                             old                new                        verdict
  useFixed=true,  camCurOk=true    fixedViewProj      camCurVP                   same matrix -> NO EFFECT
  useFixed=true,  camCurOk=false   fixedViewProj      curForReproj=fixedViewProj same matrix -> NO EFFECT
  useFixed=false, camCurOk=true    currViewProjSL     camCurVP                   >>> THE ONLY PATH THAT CHANGES <<<
  useFixed=false, camCurOk=false   currViewProjSL     curForReproj=currViewProjSL same matrix -> NO EFFECT
RESULT: OK（退出码 0）
```

**A 段是判定性的**：`rebuildViewProj`（629–664）与 `fixedViewProj` 的内联构造（917–960）
把注释、NaN 守卫、`.data` 写法、形参绑定全部归一化之后，**哈希完全相同**。
⇒ **`camCurVP` 与 `fixedViewProj` 是同一个矩阵（逐位）。**

而 `curForReproj = useFixed ? fixedViewProj : currViewProjSL`（984 行，v1.07b 与 v1.07c 一字不差），
`diag.reprojSource = useFixed ? 2 : 0`，打印 `==2 → "fixed"`，23:10 那份日志写的是 **`reproj src=fixed`**
⇒ **`useFixed == true` ⇒ 那次运行的 `curForReproj` 就是 `fixedViewProj` = `camCurVP`。**

⇒ 把取逆的源从 `curForReproj` 改成 `camCurVP`，**改前改后是同一个矩阵**。
**v1.07c 在它自己被诊断出来的那次运行上，是 0 效果。**

### 17.3 我错在哪（一句话）

第 16.3 节的**全部依据**是 `Streamline.cpp:1029-1032` 的这段注释：

> "v0.66..v1.00 stored `curForReproj`, the engine-derived ViewProj, **which carries NO translation**"

**那句注释是 v0.66..v1.00 时代写的，当时 `curForReproj` 确实是 `currViewProjSL`。**
v0.88 引入 `fixedViewProj`、984 行把它改成 `useFixed ? fixedViewProj : currViewProjSL` —— **注释没跟着改。**
**我把注释当成代码读了，于是"证明"了一个在这条路径上不存在的缺陷，并且"修复"了它。**

⇒ 这是技能 §110（因果倒置的注释）与 §41（过期注释）的**又一次复发**，而且是代价最大的一次：**一整轮**。

### 17.4 代数没错，只是被用在了没有这个输入的路径上

`inv(P @ [R|0]) @ (P @ [R | -R@eye]) = [ I | -eye ]` 这个恒等式**是对的**
（16.5 的 C0，200 组随机样本偏差 2.9e-11，也是对的）。
**它需要一个"无平移"的 `P@[R|0]` 当输入才能触发 —— 而实测走的路径上，两侧都没有这个输入。**
（`fixedViewProj` 与 `rebuildViewProj` 都在 929–933 / 643–647 行显式地写了 `-(m0*ex+m1*ey+m2*ez)`，即**带平移**。）

### 17.5 那 `row3[3] = -195.22` 到底是什么？（诚实：**仍未解释**）

B3 段证明：`inv(cur)@prev` 的 `[3][3]` 是**两侧投影的比例**——
共用同一个 P 时恰为 1.000000；把 `prev` 那一侧的投影整体乘 k，`[3][3]` 就精确等于 k。

```
prev 侧投影乘 k =    +1.00  ->  row3[3] =    +1.000000
prev 侧投影乘 k =    +0.50  ->  row3[3] =    +0.500000
prev 侧投影乘 k =  -195.22  ->  row3[3] =  -195.220000
```

**所以"世界族 / 菜单族投影不同"这个解释（本账本沿用多轮的那个）也不够：**
族投影比是 **5.62x**，它应该给出 `5.62` 或 `0.178`，**不是 `-195.22`**。

⇒ **`-195.22` 是一个还没有机制解释的读数。它进 16.6 那张"未解释"表。**
（也可能是 `matrixFullInvert` 收到近奇异输入后爆掉，或者守卫把上一帧的 `s_lastGoodClip` 顶了上来 ——
两者都能造出任意大的数。**在这份日志里分不清**，这正是需要下一个读数的原因。）

### 17.6 下一个读数（要改代码，一行）

每帧打三个数：**`curProj[0][0]`、`prevProj[0][0]`（`s_prevCamProj`）、`clipToPrevClip[3][3]`**，
外加 `cur`/`prev` 是否同族。判据：**凡是 `[3][3] != 1` 的帧，看两侧投影是否不同。**

### 17.7 由此引出的一个决定（交给用户）

**v1.07c 与 v1.07b 在这条路径上功能完全相同** ⇒ 原计划的"v1.07c 验收运行"，
实际上是**再测一遍 v1.07b**。两条路：

| | 做法 | 代价 / 收获 |
|---|---|---|
| **(a) 照跑** | 按验收卡跑一次 | 拿到 `clipW` 基线、交替 `clipDev` 的第二份样本、六个小时后第一次实测 —— **不是零价值，但不验证任何修复** |
| **(b) 跳过** | 先做 17.6 那一行诊断，编译部署，一次跑到位 | 省一趟游戏，但改完仍是"没验过就上机" |

**我倾向 (b)。但游戏是你的时间，你定。**

### 17.8 这一轮真正的产物

**「修好一个东西」之前，先证明「改前 ≠ 改后」。**

- `tools/verify_v107c_is_inert.py` 是这次的**具体**证明（可重跑、退出码 0/1）
- 通用动作进技能（§42）：**任何"把 A 换成 B"的补丁，先跑一遍证明 `A != B`，
  再谈它修了什么** —— 否则你连"没效果"和"有效果但不够"都分不开

★ 这条和 §112（"回归脚本必须先自证两支不同"）是同一件事的两面：
**§112 管的是对照实验，本章管的是产品代码本身。**
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    text = raw.decode("utf-8")
    print(f"{TARGET}  {len(raw)} B  CRLF={raw.count(b'\r\n')}")
    if raw.count(b"\r\n") > 0:
        print("  !! expected a pure LF file; refusing")
        return 1
    if MARKER in text:
        print("REFUSED, nothing written: chapter 17 already present")
        return 1

    n1, n2 = text.count(E1_OLD), text.count(E2_ANCHOR)
    print(f"E1 anchor count: {n1}   (must be exactly 1)")
    print(f"E2 anchor count: {n2}   (must be exactly 1)")
    if n1 != 1 or n2 != 1:
        print("REFUSED, nothing written")
        return 1

    out = text.replace(E1_OLD, E1_NEW)
    if out.count(E1_NEW) != 1 or out.count(E1_OLD) != 0:
        print("REFUSED, nothing written: E1 did not land cleanly")
        return 1
    i = out.index(E2_ANCHOR)
    out = out[:i] + E2_ADD + out[i:]

    checks = [
        ("17 present", MARKER in out),
        ("only one 17", out.count(MARKER) == 1),
        ("16.4 voided in place", "本条作废" in out),
        ("16.4 vanished once", out.count(E1_OLD) == 0),
        ("hash equality recorded", "7fe156da9b20" in out),
        ("inert measurement recorded", "0.000e+00" in out),
        ("path table recorded", "THE ONLY PATH THAT CHANGES" in out),
        ("-195.22 still unexplained", "仍未解释" in out and "不是 `-195.22`" in out),
        ("next reading specified", "clipToPrevClip[3][3]" in out),
        ("16.11 kept", "### 16.11" in out),
        ("16.17 kept", "### 16.17" in out),
        ("chapter order 16 < 17", out.index("### 16.11") < out.index(MARKER)),
        ("maintenance rule still last",
         out.rstrip().endswith("只在第 9 章与末尾追加。")),
        ("17 sits before the maintenance rule",
         out.index(MARKER) < out.index("**本文件维护规则**")),
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
    print(f"\nWROTE  {len(r)} B  CRLF={r.count(b'\r\n')} bare_LF={r.count(chr(10).encode()) - r.count(b'\r\n')}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
