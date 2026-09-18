#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append 2.4 to the 2026-09-19 daily log: the git/autocrlf trap found during the
night audit. Append-only, pure LF.

Dry run by default; --apply writes.
"""
import io
import sys

PATH = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md"

ANCHOR = "**注**：本轮是 v1.07b 以来第一次真正的上机机会 —— 但测的是 v1.08 的**读数**，\n不是「修复」。**修复要等读数出来之后再动**（第 17/18 章的教训）。\n"

BLOCK = """**注**：本轮是 v1.07b 以来第一次真正的上机机会 —— 但测的是 v1.08 的**读数**，
不是「修复」。**修复要等读数出来之后再动**（第 17/18 章的教训）。

### 2.4 又一条静默降级：`core.autocrlf=true` 会让 LF 文件在任何 checkout 时变 CRLF

原本只是顺手查一下行尾，结果查出**仓库没有 `.gitattributes`，而 `core.autocrlf = true`**。
`git ls-files --eol` 实测：

```
i/lf  w/lf    MFG_MASTER_NOTES.md   src/DX12SwapChain.cpp   src/NeuralRendering/*   tools/*.py
i/lf  w/crlf  src/Streamline.cpp    src/FrameGen.cpp
```

- **索引里所有文件都是 `i/lf`**；工作树里的 `w/lf` 只是「上一次直接写入」留下的，**不是 git 保证的**
- ⇒ **任何 `git checkout` / `git reset --hard` / `git stash pop` / 重新 clone 都会把纯 LF 文件写成 CRLF**
- 本项目的补丁脚本靠「锚点必须匹配目标文件行尾」工作：`DX12SwapChain.cpp`、`NeuralRendering/*`、
  工具脚本被翻成 CRLF 时锚点会 `REFUSED`（**响的，还能接受**），但
  **账本与工具脚本自己变 CRLF 是静默的** ⇒ `_fix_eol` 的前提被打破而无任何提示
- 已记入账本 **18.9 E**（含建议的 `.gitattributes` 修法）。**明天可选修，但不要跟待上机二进制混在同一批。**
"""


def main():
    raw = io.open(PATH, "rb").read()
    txt = raw.decode("utf-8")

    if "### 2.4 " in txt:
        print("REFUSED: 2.4 already present")
        return 1
    n = txt.count(ANCHOR)
    print("anchor count =", n)
    if n != 1:
        print("REFUSED, nothing written")
        return 1

    out = txt.replace(ANCHOR, BLOCK, 1)
    checks = [
        ("2.1-2.3 intact", all(k in out for k in ("### 2.1", "### 2.2", "### 2.3"))),
        ("2.4 added", out.count("### 2.4 ") == 1),
        ("has evidence", "ls-files --eol" in out and "i/lf" in out),
        ("points to ledger", "18.9 E" in out),
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
