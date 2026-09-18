#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append section 44 to the framegen-diagnosis skill: two forms of "stale" and one
more form of "silent degradation", both found on 2026-09-19.

Pure LF file, appended at the end. Dry run by default; --apply writes.
"""
import io
import sys

PATH = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
MARKER = "## 44. ★★★★"

ANCHOR = ("5. 顺序类风险（43.2）写成**索引比较断言**，别写在注释里。\n")

BLOCK = """5. 顺序类风险（43.2）写成**索引比较断言**，别写在注释里。

## 44. ★★★★ 两种「过期」与又一种「静默」：行号、注释、git

### 44.1 过期行号与过期注释是同一个病

笔记（本技能、账本）里写 `Streamline.cpp:1029-1032`，在插入型改动之后指向**完全不相干的代码**
（实测：那段位置现在是一段讲「按帧维护历史」的中文注释）。
第 17 章我因**读了一句过期注释**白干一整天；**过期行号会以完全相同的方式骗人**。

⇒ 规则：**笔记里不要只写行号，至少同时抄一句能 grep 动的锚点原文。**
本仓库 v1.08 之后实测：`1029–1032` → **1040–1043**；另外两段是 **1084–1093**、**900–904**。

### 44.2 `core.autocrlf=true` + 没有 `.gitattributes` ⇒ LF 状态是假象

- `git ls-files --eol` 实测：**索引里所有文件都是 `i/lf`**；
  工作树里的 `w/lf` 只是「上一次直接写入」留下的产物，**不是 git 保证的状态**
- ⇒ 任何 `git checkout` / `git reset --hard` / `git stash pop` / 重新 clone，
  都会把纯 LF 文件写成 **CRLF**
- 后果分级：锚点不匹配会 `REFUSED`（**响的，可接受**）；
  但**账本与工具脚本自己变成 CRLF 是静默的** —— `_fix_eol` 的前提被打破而无任何提示
- 修法：`.gitattributes` 把意图写死（`* text=auto eol=lf` + 逐文件 `eol=crlf`）；
  **加文件本身不改现有工作树**，所以是纯保护性的；**不要**顺手跑 `git add --renormalize`

### 44.3 通用规则（本项目第三次同类）

**「静默降级」又一种形态：不是把异常读数变成 0，而是把依赖的前提悄悄换掉。**
凡是脚本或笔记依赖「某种状态成立」——行尾、行号、字段有写者、常量会变化、快照早于覆盖——
**都要有一条能在前提被破坏时响起来的检查**，否则它坏掉的样子和「健康」一模一样。
"""


def main():
    raw = io.open(PATH, "rb").read()
    txt = raw.decode("utf-8")

    if MARKER in txt:
        print("REFUSED: section 44 already present")
        return 1
    n = txt.count(ANCHOR)
    print("anchor count =", n)
    if n != 1:
        print("REFUSED, nothing written")
        return 1

    out = txt.replace(ANCHOR, BLOCK, 1)
    checks = [
        ("43 intact", out.count("## 43. ★★★★★") == 1),
        ("44 added", out.count("## 44. ★★★★") == 1),
        ("three subsections", all(k in out for k in ("### 44.1", "### 44.2", "### 44.3"))),
        ("has evidence", "ls-files --eol" in out and "i/lf" in out),
        ("no stray CR", "\r" not in out),
    ]
    for label, ok in checks:
        print("  [%s] %s" % ("OK " if ok else "FAIL", label))
    if not all(ok for _, ok in checks):
        print("REFUSED, nothing written (post-condition failed)")
        return 1

    if "--apply" in sys.argv:
        io.open(PATH, "wb").write(out.encode("utf-8"))
        print("written: %d -> %d B" % (len(raw), len(out.encode("utf-8"))))
    else:
        print("dry run only - pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
