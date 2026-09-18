#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append section 18.9 to MFG_MASTER_NOTES.md: the hand-off block.

Two things it records that exist nowhere else in the ledger:
  A. every line number in this file is PRE-v1.08. The v1.08 probe inserted
     lines around 757, so references written as "1029-1032" now point at an
     unrelated Chinese comment. That is precisely the failure mode that cost a
     whole day in chapter 17 (reading a comment as code) -- a stale line number
     has the same effect.
  B. the edit that was deliberately NOT made, and why (rebuilding would change
     the md5 of the binary that is waiting for its first run).

Dry run by default. --apply writes. The anchor count must be exactly 1 and the
marker must be absent, otherwise nothing is written.
"""
import io
import sys

PATH = "MFG_MASTER_NOTES.md"
MARKER = "### 18.9 交班"

ANCHOR = (
    "这是 17 章那次一整天白干的直接结论。\n"
    "\n"
    "---\n"
    "\n"
    "---\n"
    "---\n"
    "\n"
    "**本文件维护规则**"
)

BLOCK = """这是 17 章那次一整天白干的直接结论。

### 18.9 交班（v1.08 交付时：仍未做 / 故意不做的事）

#### A. 本文件里所有的行号都是 v1.08 **之前**的

v1.08 的插桩在 757 行附近插了行，其后所有行号整体后移。**照旧行号去 grep，会读到完全不相干的东西**
—— 2026-09-19 00:15 实测，旧引用「1029–1032」那个位置现在是一段讲「按帧维护历史」的中文注释。
**行号过期与注释过期是同一个病**：第 17 章我因为读了一句过期注释，白干一整天。

| 旧引用 | 现位置 | 内容 |
|---|---|---|
| 「1029–1032」 | **1040–1043** | `v0.66..v1.00 stored curForReproj ... which carries NO translation` —— **就是第 17 章里骗到我的那一段** |
| （未记） | **1084–1093** | v1.07c 自己写下的注释（断言两侧相机不同源）—— **已被第 17 章证伪** |
| （未记） | **900–904** | 更早的 `Proj @ View` 顺序 / `c0 == c56` 推导段 |

★ **三段讲的是三件事，而且只有 900–904 那段仍然成立** —— 它说的是**引擎自己**的 ViewProj 无平移，
这一点从头到尾没变。1040–1043 说的是「v0.66..v1.00 存的是引擎矩阵」，而 v0.88 之后
`curForReproj` 早已改成 `useFixed ? fixedViewProj : currViewProjSL`。
**一句话里把「当时」和「现在」混在了一起 —— 这就是它骗到我的方式。**

#### B. 故意没改的欠账（留到下一次真正的代码改动一起做）

1. **两段过期注释**（现 1040–1043 / 1084–1093）：本应改成事实，但改注释要重新编译，
   会破坏**正在等待第一次上机的二进制**的 md5（v1.08 = `0a10b4b6…b613`）⇒ **故意留到下次**。
   ★ 这是 12.13 那条规矩的第一次实际应用：**当二进制本身是交付物时，注释不能单独改。**
2. **第 14.6 节的释放竞态**：故意未修（第 14 章原文）。
3. **`docs/acceptance-v1.07c.html` 保留不删**：它是被证伪那一轮的原始记录，删了就没有对照组。

#### C. 明天开机第一件事（顺序不能换）

1. MO2 **取消勾选 `Modex.dll`**（第三方闪退，今天崩过三次，会掩盖一切结论）
2. 进游戏 → 等 4x 起来 → **站着不动 5 秒** → 走 5 秒并转视角 → 退出
3. `python tools/analyze_session.py` → 五条判据（见 `docs/acceptance-v1.08.html`）
4. 若出现 `[MOTION]` 行 ⇒ 读它自带的 `p00 cur/prev` 与 `mag invSrc` ⇒ **直接判 (a)/(b)**

#### D. 这一轮之后仍然没有答案的问题（别当成已解决）

- `clipToPrevClip[3][3] = -195.22` 的机制 —— **本轮就是去测它**
- 冻结是否真的止住 —— **未知**（我无法运行游戏）
- 性能恶化：FPS 39.7→13.4、1% Low→1.1、真实帧 571ms —— **未解释**
- RTX 20/30 系 —— **一行未写**；DLSS5 —— 代码在，**未上机验证**

"""


def main():
    apply = "--apply" in sys.argv
    raw = io.open(PATH, "rb").read()
    txt = raw.decode("utf-8")

    if MARKER in txt:
        print("REFUSED: marker already present")
        return 1

    n = txt.count(ANCHOR)
    print("anchor count =", n)
    if n != 1:
        print("REFUSED, nothing written (anchor count != 1)")
        return 1

    out = txt.replace(ANCHOR, BLOCK + "---\n\n---\n---\n\n**本文件维护规则**", 1)

    # post-conditions checked on the RESULT, not on the input
    checks = [
        ("18.9 inserted", out.count("### 18.9 交班") == 1),
        ("18.8 still single", out.count("### 18.8 本轮产出") == 1),
        ("18.1 still single", out.count("### 18.1") == 1),
        ("maintenance rule", out.count("**本文件维护规则**") == 1),
        ("ends with rule", out.rstrip().endswith("只在第 9 章与末尾追加。")),
        ("A/B/C/D present", all(k in out for k in
                               ("#### A. 本文件里所有的行号", "#### B. 故意没改的欠账",
                                "#### C. 明天开机第一件事", "#### D. 这一轮之后仍然没有答案"))),
        ("line drift table", "1040–1043" in out and "1084–1093" in out and "900–904" in out),
        ("old anchor consumed", out.count(ANCHOR) == 0),
    ]
    for label, ok in checks:
        print("  [%s] %s" % ("OK " if ok else "FAIL", label))

    if not all(ok for _, ok in checks):
        print("REFUSED, nothing written (post-condition failed)")
        return 1

    if apply:
        io.open(PATH, "wb").write(out.encode("utf-8"))
        print("written: %d -> %d B" % (len(raw), len(out.encode("utf-8"))))
    else:
        print("dry run only - pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
