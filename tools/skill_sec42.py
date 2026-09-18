#!/usr/bin/env python3
"""Append section 42 to the framegen-diagnosis skill (pure LF file).

Dry run by default; --apply writes. Marker guard prevents a double append.
"""
import io
import sys

TARGET = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
MARKER = "## 42. ★★★★★ 「把 A 换成 B」之前先证明 `A != B`"

SECTION = """
## 42. ★★★★★ 「把 A 换成 B」之前先证明 `A != B` —— **空操作补丁**的自检三件套 ★2026-09-18 实锤

### 42.1 症状：一个"修好了"的补丁，改前改后是同一个值

```cpp
- sl::matrixFullInvert(invCurrViewProj, curForReproj);
+ const sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;
+ sl::matrixFullInvert(invCurrViewProj, reprojInvSrc);
```

**在这条实跑路径上，`camCurVP` 与 `curForReproj` 是同一个矩阵** ⇒ 这个改动**什么都没改**。
而它凑齐了所有"看起来成功了"的信号：

- 编译通过、无警告
- 离线回归脚本全绿（因为回归脚本**测试的是它自己的数学模型**，不是产品代码的接线）
- 代码 diff 读起来完全像"改对了"（把错的源换成对的源）
- 日志里出现了一个新仪表、版本横幅更新了

★ **回归脚本绿，只证明"我写的那套代数是对的"，不证明"产品走的是那套代数"。**

### 42.2 自检三件套（任何"换一个来源/换一个变量"的补丁，逐条跑）

**(1) 结构等价性断言 —— 两个候选输入是不是同一个东西**

把两个构造点各自的代码块抽出来，**归一化**（去注释 / 去守卫 / 去返回 / `x.data`→`x` /
把**调用点实参代进形参**），然后比哈希。**形参不代入是最常见的假阳性来源**：
拿 `f(a_fb.X)` 与直接写 `a_fb.X` 比，看起来不同，其实是同一个。

```
$ python tools/verify_v107c_is_inert.py
  rebuildViewProj   860 chars  sha1 7fe156da9b20
  fixedViewProj     860 chars  sha1 7fe156da9b20
  identical: YES
```

**(2) 代数层面：哪些量会被约掉**

两侧都带同一个 `P` 时：

```
inv(P@A) @ (P@B)  ==  inv(A) @ B      (200 组随机样本偏差 2.878e-13)
```

⇒ **换掉那个 `P` 的载体，在数学上不可能有效果。** 只要先写出这一步，就不必去写补丁了。

**(3) 路径穷举 —— 只有"改前 ≠ 改后"的分支才可能有效果**

| case | 旧 | 新 | 结论 |
|---|---|---|---|
| `useFixed=true, camCurOk=true` | `fixedViewProj` | `camCurVP` | 同矩阵 → **无效** |
| `useFixed=true, camCurOk=false` | `fixedViewProj` | `curForReproj=fixedViewProj` | 同矩阵 → **无效** |
| `useFixed=false, camCurOk=true` | `currViewProjSL` | `camCurVP` | **唯一会变的分支** |
| `useFixed=false, camCurOk=false` | `currViewProjSL` | `curForReproj=currViewProjSL` | 同矩阵 → **无效** |

**然后再确认"实跑走的是哪一条分支"** —— 这里的答案写在日志里：
`diag.reprojSource = useFixed ? 2 : 0`，打印 `==2 → "fixed"`，实测日志 `reproj src=fixed`
⇒ **走的正是"无效"那条**。

★★ **判据：一个修复只有在"实跑走的那个分支上 `旧 != 新`"时才可能有效。
否则它只是把仪表和横幅更新了一遍。**

### 42.3 附带教训：前提来自注释时，注释必须与它描述的代码同版本

这次的错误前提完全来自一段注释：

> "`curForReproj`, the engine-derived ViewProj, **which carries NO translation**"

**注释写于 v0.66..v1.00（当时是对的）；v0.88 改了赋值行，注释没改。**
⇒ **任何以注释为依据的推理，先确认"这段注释描述的是当前这一行吗"**
（做法：看赋值行附近有没有更晚版本的 `vX.YZ` 标记；`git log -L` 或 `git blame` 那一行）。
这是 §41（过期注释）与 §110（因果倒置的注释）的**第三次复发**，也是代价最大的一次。

### 42.4 落地动作

1. **写补丁之前**跑 (1)(2)；**写完补丁之后**跑 (3) + 确认实跑分支
2. 把这三步做成一个**可重跑、带退出码**的脚本（本工程的样板：
   `tools/verify_v107c_is_inert.py`），不要只在脑子里过一遍
3. 结论写进账本时，**"没效果"和"有效果但不够"必须分开写** ——
   没有 (1)~(3)，这两者从日志上无法区分
4. 与 §112 的分工：**§112 管对照实验（两支接线要不同），本节管产品代码本身（改前改后要不同）**
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    crlf = raw.count(b"\r\n")
    text = raw.decode("utf-8")
    print(f"SKILL.md  {len(raw)} B  lines={text.count(chr(10))}  CRLF={crlf}")
    if crlf > 0:
        print("  !! expected a pure LF file; refusing")
        return 1
    if MARKER in text:
        print("REFUSED, nothing written: section 42 already present")
        return 1

    out = text.rstrip("\n") + "\n" + SECTION
    checks = [
        ("42 present", MARKER in out),
        ("only one 42", out.count(MARKER) == 1),
        ("41 kept", "## 41. ★★★★★ 「代码里写着已拔掉」" in out),
        ("42 after 41", out.index("## 41. ★★★★★") < out.index(MARKER)),
        ("three-part self-check recorded", "自检三件套" in out),
        ("hash evidence recorded", "7fe156da9b20" in out),
        ("path table recorded", "唯一会变的分支" in out),
        ("comment-version lesson recorded", '注释必须与它描述的代码同版本' in out),
        ("112 split recorded", "§112 管对照实验" in out),
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
