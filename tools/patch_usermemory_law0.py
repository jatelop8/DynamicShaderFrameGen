#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add the meta-law to the cross-project user-level memory, at the very top.

User instruction, 2026-09-19 09:40, verbatim:
  "每次你看完日志改完要自我检查两遍 再给我 不要每次骗我 这个是铁律 记住 每次照做"

This file is CRLF (992 CRLF / 0 bare LF as measured). Anchors are converted to
the file's own eol before matching. Dry run by default; --apply writes.
"""

import io
import sys

PATH = r"C:/Users/Administrator/.workbuddy/MEMORY.md"
MARKER = "## ★★★★★ 元铁律：交付前自我检查两遍"
ANCHOR = "## ENB 配置铁律（跨项目，2026-09-15 实测）"

BLOCK = r"""## ★★★★★ 元铁律：交付前自我检查两遍（用户 2026-09-19 原话，跨项目，每次照做）

> 「每次你看完日志改完要自我检查两遍 再给我 不要每次骗我 这个是铁律 记住 每次照做」

用户说的「骗」= **未经证实的断言**。判据不是"有没有撒谎"，而是"**手里有没有证据**"。
没有证据只能写「未证」；不确定必须说「不确定」。**先给结论、后补验证 = 骗。**

**第一遍 · 手脚 —— 我改的东西真的落盘/生效了吗**

1. 逐符号 `grep` 回读（`--apply` 报成功但文件未变，已实测发生过）
2. **逆操作还原 → 与改前逐字节相同**（纯增量证明）
3. 行尾 CRLF/LF 计数 + stray = 0
4. 构建通过（便宜但有盲区：**丢失的改动照样能编译通过**）
5. 双份 md5（构建产物 == 实际部署处）+ 二进制内字符串版本号

**第二遍 · 脑子 —— 我说的结论真的站得住吗**

1. ★ **反向假设**：若结论是反的，日志会长什么样？**我看到的能不能排除它？**
2. 这个量有写者吗 / 配置有没有 override / 注释是否过期
3. 这条代码路径**真的会被走到**吗（探针挂在永不执行的分支上，已发生三次）
4. 「改 A 为 B」之前先证明 **A ≠ B**（否则是空操作，用户白跑一趟）
5. **同时发生 ≠ 因果**（分不开就写「未证」）
6. 空集 / 异常值会不会被静默当成「健康」
7. **用户会不会因此白跑一趟**

**交付时把两遍的结果一并列出**（逐条给结果，不是"我检查过了"）。

---

"""


def main():
    apply = "--apply" in sys.argv
    raw = io.open(PATH, "rb").read()
    s = raw.decode("utf-8")
    eol = "\r\n" if raw.count(b"\r\n") > raw.count(b"\n") - raw.count(b"\r\n") else "\n"
    print("file: %s\n  %d B  chars=%d  CRLF=%d  bare_LF=%d  -> eol=%s" %
          (PATH, len(raw), len(s), raw.count(b"\r\n"),
           raw.count(b"\n") - raw.count(b"\r\n"), "CRLF" if eol == "\r\n" else "LF"))

    if MARKER in s:
        print("REFUSED: marker already present (idempotence guard).")
        return 2

    anchor = ANCHOR
    if eol != "\n":
        anchor = ANCHOR          # single line, no embedded newline: eol-agnostic
    n = s.count(anchor)
    print("  anchor count=%d %s" % (n, "OK" if n == 1 else "*** REFUSED ***"))
    if n != 1:
        print("REFUSED, nothing written.")
        return 2

    block = BLOCK if eol == "\n" else BLOCK.replace("\n", eol)
    out = s.replace(anchor, block + anchor, 1)

    checks = [
        ("meta-law present once", out.count(MARKER) == 1),
        ("user words quoted", out.count("不要每次骗我 这个是铁律 记住 每次照做") == 1),
        ("pass 1 present", "第一遍 · 手脚" in out),
        ("pass 2 present", "第二遍 · 脑子" in out),
        ("ENB section intact", out.count(ANCHOR) == 1),
        ("head intact", out.startswith("# 用户级长期记忆")),
        ("no escaped-newline corruption", "\\n" not in BLOCK and "/r/n" not in BLOCK),
        ("every line ends the same way",
         (out.count("\r\n") == out.count("\n") if eol == "\r\n"
          else out.count("\r\n") == 0)),
    ]
    ok = True
    for label, good in checks:
        print("  post %-34s %s" % (label, "OK" if good else "*** FAIL ***"))
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
