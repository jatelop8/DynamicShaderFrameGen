#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append section 48 to the framegen-diagnosis skill: the L0 meta-law, executable.

User instruction, 2026-09-19 09:40, verbatim:
  "每次你看完日志改完要自我检查两遍 再给我 不要每次骗我 这个是铁律 记住 每次照做"

Sections 40-47 record what went wrong in this project. Section 48 records the
procedure that is supposed to catch it before the user ever sees it.

Dry run by default; --apply writes. Idempotent (marker guard).
"""

import io
import re
import sys

PATH = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
MARKER = "## 48. ★★★★★ L0 元铁律"

ANCHOR = ("★ 推论三：探针的价值**不在于它读什么**，而在于**它什么时候被读到**。\n"
          "  挂错分支的探针会给出一份漂亮的、完全无关的数据 —— 比没有探针更危险。")

BLOCK = r"""

---

## 48. ★★★★★ L0 元铁律：交付前自我检查两遍（用户 2026-09-19 明确要求，每次照做）

> 用户原话：「每次你看完日志改完要自我检查两遍 再给我 不要每次骗我 这个是铁律 记住 每次照做」

**「骗」的判据不是"有没有撒谎"，而是"手里有没有证据"。**
未经证实的断言，在用户那里与欺骗等价 —— 他要花时间去跑、去试、去发现是空的。
**没有证据只能写「未证」；不确定必须说「不确定」。先给结论、后补验证 = 骗。**

前 40 多节记的是"哪里错过"。本节记的是**交付前必须走完的动作**，它存在的意义就是
让那些错误在用户看到之前被拦下。

### 48.1 第一遍 · 手脚 —— 我改的东西真的落盘/生效了吗

| # | 动作 | 为什么必须做 |
|---|---|---|
| 1 | **逐符号 `grep` 回读**改动位置 | `--apply` 报成功而文件未变是实测发生过的（本会话就在账本上撞到一次：命令返回空输出，我把"没有输出"当成了"成功"，直到回读字节数才发现仍是 123605 B） |
| 2 | **逆操作还原 → 与改前逐字节相同** | 这是"纯增量"的最强证明：把补丁反过来跑，`sha1` 必须回到原值。做不到就说明改动不止你以为的那些 |
| 3 | **行尾核对**：CRLF / bare_LF 计数 + stray = 0 | 锚点是按行尾匹配的；行尾一漂，下一轮的补丁全部 `REFUSED` 或错位 |
| 4 | **构建通过** | 最便宜的验证器 —— 但**不是唯一**的：丢失的改动照样能编译通过（`Edit` 静默丢改已多次实测），所以第 1 条不能省 |
| 5 | **双份 md5**：构建产物 == 实际部署处 | 只核构建目录 = 没核部署。MO2 会优先游戏本体 `data/`，还要确认那里无残留副本 |
| 6 | **二进制内字符串版本号** | 横幅 / 新字段名的 `grep -F` 计数，确认跑的是这一版而不是上一版 |
| 7 | **锚点 `count(old) == 1`**；`post-condition` 检查**结果文本** | 检查输入文本会误报成功（曾踩） |

### 48.2 第二遍 · 脑子 —— 我说的结论真的站得住吗

| # | 动作 | 真实的代价 |
|---|---|---|
| 1 | ★ **反向假设**：若结论是反的，日志会长什么样？**我手上的证据能不能排除它？** | 第 17 章：把过期注释当代码，证明了一个在这条路径上不存在的缺陷，"修"了它一整个版本 —— 用户白跑一趟 |
| 2 | 这个量**有没有写者** / 配置**有没有 override** / 注释**是否过期** | 三项各让一个探针失效（`mvecScale`、`jitter`、`carries NO translation`） |
| 3 | 这条**代码路径真的会被走到**吗 | 探针三连空（`mvecScale` / `path` 窗口 / `[MOTION]`） |
| 4 | 「改 A 为 B」之前证明 **A ≠ B** | 两构造器 `sha1` 相同 ⇒ 改动是空操作 |
| 5 | **同时发生 ≠ 因果**，分不开就写「未证」 | 4x 启动 ⊥ `CameraPosAdjust` 变值，差约 900 单位、无过渡帧 |
| 6 | **空集 / 异常值会不会被静默当成「健康」** | 负号使整行心跳失配 ⇒ 该节打 `NO DATA`，看起来像"没数据"而不是"指标坏了" |
| 7 | **用户会不会因此白跑一趟** | 判据 0 先决条件：`N = 0` 即白跑。凑不齐信息量就不要让他开游戏 |

### 48.3 交付格式（不做这一步 = 没做检查）

回复里**逐条列出两遍的结果**，不是写一句"我已检查过"：

```
第一遍·手脚
  ✓ 回读：<符号/文件> 落地，字节 X→Y
  ✓ 逆操作还原：sha1 与改前一致（纯增量）
  ✓ 行尾：账本纯 LF / 源码纯 CRLF，stray=0
  ✓ 构建：退出码 0；md5 双份一致 = <hash前12>
第二遍·脑子
  ✓ 反向假设：若 <结论> 是反的，应看到 <X>；实测 <Y>，排除
  ✓ A≠B：已用 <证据> 证明两者不同
  ! 未证：<某项> 仍无法判定，写"未证"
```

★ **列出"未证"项不是示弱，是这条铁律的核心** —— 用户要的是能据此行动的信息，不是好看。

### 48.4 什么时候可以跳过

只有一种情况：**纯查询、无改动、无结论**（读一个已确认过的值）。
一旦涉及"看完日志"或"改完代码"，两遍都必须走。
"""


def main():
    apply = "--apply" in sys.argv
    raw = io.open(PATH, "rb").read()
    s = raw.decode("utf-8")
    eol = "\r\n" if raw.count(b"\r\n") > raw.count(b"\n") - raw.count(b"\r\n") else "\n"
    print("file: %s\n  %d B  CRLF=%d  bare_LF=%d  eol=%s" %
          (PATH, len(raw), raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n"),
           "CRLF" if eol == "\r\n" else "LF"))

    if MARKER in s:
        print("REFUSED: marker already present.")
        return 2

    # the anchor spans two lines and the file is LF, so normalise the anchor's
    # own eol to the file's before matching
    anchor = ANCHOR if eol == "\n" else ANCHOR.replace("\n", eol)
    n = s.count(anchor)
    print("  anchor count=%d %s" % (n, "OK" if n == 1 else "*** REFUSED ***"))
    if n != 1:
        print("REFUSED, nothing written.")
        return 2

    block = BLOCK if eol == "\n" else BLOCK.replace("\n", eol)
    out = s.replace(anchor, anchor + block, 1)

    checks = [
        ("section 48 present once", out.count(MARKER) == 1),
        ("user words quoted", out.count("不要每次骗我 这个是铁律 记住 每次照做") == 1),
        ("pass 1 table", "### 48.1 第一遍 · 手脚" in out),
        ("pass 2 table", "### 48.2 第二遍 · 脑子" in out),
        ("report format", "### 48.3 交付格式" in out),
        ("skip rule", "### 48.4 什么时候可以跳过" in out),
        ("anchor intact", out.count(anchor) == 1),
        # Match at LINE START: "## 40." also appears inside cross-references in
        # the body, so a plain substring count is 12 for section 40, not 1.
        ("sections 39-47 intact",
         all(re.search(r"^## %d\." % i, out, re.M) for i in range(39, 48))),
        ("no escaped-newline corruption", "\\n" not in BLOCK and "/r/n" not in BLOCK),
    ]
    ok = True
    for label, good in checks:
        print("  post %-30s %s" % (label, "OK" if good else "*** FAIL ***"))
        ok = ok and good
    if not ok:
        print("REFUSED, nothing written.")
        return 2

    import hashlib
    print("  new sha1 %s" % hashlib.sha1(out.encode("utf-8")).hexdigest()[:12])
    print("  bytes %d -> %d  (%+d)" % (len(raw), len(out.encode("utf-8")),
                                       len(out.encode("utf-8")) - len(raw)))
    if not apply:
        print("DRY RUN - pass --apply to write.")
        return 0
    io.open(PATH, "wb").write(out.encode("utf-8"))
    print("WROTE %s" % PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
