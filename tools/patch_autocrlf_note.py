#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Record the git/autocrlf trap found during the night audit, in two places:
  A. MFG_MASTER_NOTES.md  -> new section 18.9 E (evidence + suggested fix)
  B. workspace MEMORY.md  -> one warning line, paid for by trimming three
                             wordier spots so the file stays under 3000 chars

Evidence (git ls-files --eol):
    i/lf w/lf    MFG_MASTER_NOTES.md  src/DX12SwapChain.cpp  src/NeuralRendering/*  tools/*.py
    i/lf w/crlf  src/Streamline.cpp   src/FrameGen.cpp
core.autocrlf = true and there is no .gitattributes, so the LF worktree state is
an accident of direct writes, not something git guarantees.

Dry run by default; --apply writes both files.
"""
import io
import sys

LEDGER = r"D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md"
MEM = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/MEMORY.md"

LEDGER_ANCHOR = (
    "- RTX 20/30 系 —— **一行未写**；DLSS5 —— 代码在，**未上机验证**\n"
    "\n"
    "---\n"
    "\n"
    "---\n"
    "---\n"
    "\n"
    "**本文件维护规则**"
)

LEDGER_BLOCK = """- RTX 20/30 系 —— **一行未写**；DLSS5 —— 代码在，**未上机验证**

#### E. 顺带查出的一个 git 陷阱（下一轮可选修，**今晚不动**）

睡眠审计时顺手查的，**有证据**（`git ls-files --eol`，2026-09-19 00:40 实测）：

```
i/lf  w/lf    MFG_MASTER_NOTES.md        src/DX12SwapChain.cpp
i/lf  w/lf    src/NeuralRendering/*      tools/*.py
i/lf  w/crlf  src/Streamline.cpp         src/FrameGen.cpp
```

- **索引里所有文件都是 `i/lf`** —— 因为 `git config core.autocrlf = true`，而且仓库**没有 `.gitattributes`**。
- 工作树里那些 `w/lf`（账本、`DX12SwapChain.cpp`、`NeuralRendering/*`、工具脚本）
  是**上一次直接写入留下的产物**，**不是 git 保证的状态**。
- ⇒ **任何 `git checkout` / `git reset --hard` / `git stash pop` / 重新 clone，都会把工作树的纯 LF 文件写成 CRLF。**

**为什么危险**：本项目的补丁脚本靠「锚点必须匹配目标文件的行尾」工作（`.h`=CRLF，先 `_fix_eol`）。
git 一旦悄悄把 `DX12SwapChain.cpp` / `NeuralRendering/*` / 工具脚本翻成 CRLF，
锚点会 `REFUSED` —— **这个是响的，还行**；但**账本与工具脚本自己变成 CRLF 是静默的**，
`_fix_eol` 的前提被打破却没有任何提示。**又一次「静默降级」。**

**建议修法（下一轮做，不要跟待上机二进制混在同一批）**：加 `.gitattributes` 把意图写死，
而不是继承全局设置：

```
* text=auto eol=lf
src/Streamline.cpp text eol=crlf
src/Streamline.h   text eol=crlf
```

★ 加 `.gitattributes` 本身**不会改动已有的工作树文件**（除非跑 `git add --renormalize .`），
所以它是纯保护性的；但「加配置」与「改代码」仍不应混在同一批。

"""

MEM_EDITS = [
    ("trim the ledger preamble",
     "动手前先读，每轮改后追写（只追加、写原文证据）。本文件只是索引。",
     "动手前先读，每轮改后追写。本文件只是索引。"),
    ("trim the Modex note",
     "（第三方闪退，崩过三次，会掩盖一切结论）",
     "（第三方闪退，会掩盖结论）"),
    ("trim the dinput8 line",
     "`dinput8.dll`：540,672 B = Transfusion（生效，4x）；5,945,344 B = RTXMFG（零作用，`.rtxmfg-off`）。",
     "`dinput8.dll`：540,672 B=Transfusion（4x）；5,945,344 B=RTXMFG（零作用）。"),
]

MEM_ANCHOR = "**行尾每次开工实测**：`Streamline.cpp`/`.h` 纯 **CRLF**；账本/技能/脚本纯 **LF**。"

MEM_INSERT = (
    MEM_ANCHOR
    + "\n⚠ `core.autocrlf=true` 且无 `.gitattributes`"
    + " ⇒ **`git checkout/reset/stash` 会把纯 LF 翻成 CRLF**。"
)


def main():
    apply = "--apply" in sys.argv
    fails = []

    # ---------------- ledger ----------------
    raw = io.open(LEDGER, "rb").read()
    txt = raw.decode("utf-8")
    if "#### E. 顺带查出的一个 git 陷阱" in txt:
        print("REFUSED: ledger section E already present")
        return 1
    n = txt.count(LEDGER_ANCHOR)
    print("ledger anchor count =", n)
    if n != 1:
        print("REFUSED, nothing written")
        return 1
    new_led = txt.replace(LEDGER_ANCHOR,
                          LEDGER_BLOCK + "---\n\n---\n---\n\n**本文件维护规则**", 1)
    for label, ok in [
        ("18.9 E added", new_led.count("#### E. 顺带查出的一个 git 陷阱") == 1),
        ("A/B/C/D intact", all(k in new_led for k in
                               ("#### A. 本文件里所有的行号", "#### B. 故意没改的欠账",
                                "#### C. 明天开机第一件事", "#### D. 这一轮之后仍然没有答案"))),
        ("rule single", new_led.count("**本文件维护规则**") == 1),
        ("no CR introduced", "\r" not in new_led),
    ]:
        print("  [%s] %s" % ("OK " if ok else "FAIL", label))
        if not ok:
            fails.append(label)

    # ---------------- memory ----------------
    mraw = io.open(MEM, "rb").read()
    mtxt = mraw.decode("utf-8")
    for label, old, new in MEM_EDITS:
        c = mtxt.count(old)
        print("  [%s] mem %-28s count=%d" % ("OK " if c == 1 else "BAD", label, c))
        if c != 1:
            fails.append(label)
        else:
            mtxt = mtxt.replace(old, new, 1)
    c = mtxt.count(MEM_ANCHOR)
    print("  [%s] mem insert anchor          count=%d" % ("OK " if c == 1 else "BAD", c))
    if c != 1:
        fails.append("mem insert")
    else:
        mtxt = mtxt.replace(MEM_ANCHOR, MEM_INSERT, 1)

    print("MEMORY.md chars %d -> %d (cap 3000)" % (len(mraw.decode("utf-8")), len(mtxt)))
    if len(mtxt) > 3000:
        fails.append("memory still over cap")
    for k in ("core.autocrlf", "v1.08-probe", "1040–1043", "\u2014\u2014"):
        if k not in mtxt:
            print("  [BAD] memory missing %r" % k)
            fails.append("missing " + k)

    if fails:
        print("REFUSED, nothing written. failures:", fails)
        return 1

    if apply:
        io.open(LEDGER, "wb").write(new_led.encode("utf-8"))
        io.open(MEM, "wb").write(mtxt.encode("utf-8"))
        print("written: ledger %d -> %d B ; MEMORY.md -> %d chars"
              % (len(raw), len(new_led.encode("utf-8")), len(mtxt)))
    else:
        print("dry run only - pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
