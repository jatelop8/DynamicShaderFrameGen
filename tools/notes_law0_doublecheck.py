#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Insert L0, the meta-law, at the top of the iron-law table.

User instruction, 2026-09-19 09:40, verbatim:
  "每次你看完日志改完要自我检查两遍 再给我 不要每次骗我 这个是铁律 记住 每次照做"

L0 is different in kind from L1..L25: it does not constrain the code, it
constrains what I am allowed to hand over. It is placed directly under the table
heading so it is read before every other entry.

Dry run by default; --apply writes. Idempotent (marker guard).
"""

import io
import sys

PATH = "MFG_MASTER_NOTES.md"
MARKER = "### L0 · 元铁律"

ANCHOR = "### A 组 · 读数：判断一个数能不能用"

BLOCK = r"""### L0 · 元铁律 —— 交付前必须自我检查两遍（2026-09-19 09:40 用户原话）

> 「每次你看完日志改完要自我检查两遍 再给我 不要每次骗我 这个是铁律 记住 每次照做」

**"骗"的定义**：我从未故意说假话，但**未经证实的断言在用户眼里就是骗**。
所以判据不是"我有没有撒谎"，而是"**我手里有没有证据**"。
没有证据的结论只能写"未证"，不许写成结论；不确定就必须说"不确定"。

**第一遍 · 手脚（我改的东西，真的改对了吗）**

1. 逐符号 `grep` 回读 —— 改动是否真的落盘（本会话已当场撞到一次：
   `--apply` 那次命令返回空输出、我误以为成功，实测账本字节数未变）
2. **逆操作还原 → 与改前逐字节相同**（纯增量证明）；插入型改动必须有幂等守卫
3. 行尾核对（CRLF / LF 计数 + stray = 0）
4. 构建通过（编译器是最便宜的验证器，但**不是唯一**的 —— 丢失的改动照样能编译通过）
5. **双份 md5**（build == MO2 部署）+ DLL 内字符串版本号 + 确认游戏本体无残留副本
6. 补丁锚点 `count(old) == 1`；`post-condition` 检查**结果文本**，不是输入文本

**第二遍 · 脑子（我说的结论，真的站得住吗）**

1. ★ **反向假设**：若结论是反的，日志会长什么样？**我看到的能不能排除它？**
   （第 17 章就是缺这一步 —— 空操作被当成了修复，用户白跑一趟游戏）
2. 读量三问（有无写者 / 有无 override / 注释是否过期）……L2
3. 这条路径真的会被走到吗（探针三连空）……L12
4. **A≠B 证了吗**（空操作修复）……L11
5. 同时发生 ≠ 因果，分不开就写"未证"……L18
6. 空集 / 异常读数会不会被当成"健康"……L3
7. **用户会不会因此白跑一趟**……L22
8. 有没有把"未证"写成了结论、把推断写成了事实

**交付时必须把两遍的结果一并给出**（各一两行），让检查看得见 —— 不是"我检查过了"，而是
逐条列出检查了什么、结果是什么。第 17 章与第 20 章那两次返工，**第二遍都能当场拦下**。

"""


def main():
    apply = "--apply" in sys.argv
    raw = io.open(PATH, "rb").read()
    s = raw.decode("utf-8")
    eol = "\r\n" if raw.count(b"\r\n") else "\n"
    print("file: %s  %d B  CRLF=%d  bare_LF=%d" %
          (PATH, len(raw), raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")))

    # L14: an insertion does not consume its anchor, so count==1 alone would
    # still pass on a second run. A marker guard is mandatory.
    if MARKER in s:
        print("REFUSED: %s already present" % MARKER)
        return 2

    n = s.count(ANCHOR)
    print("  anchor '### A 组' count=%d %s" % (n, "OK" if n == 1 else "*** REFUSED ***"))
    if n != 1:
        print("REFUSED, nothing written.")
        return 2

    out = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    if eol != "\n":
        out = out.replace("\n", eol)

    checks = [
        ("L0 present exactly once", out.count(MARKER) == 1),
        ("L0 quotes the user", out.count("不要每次骗我 这个是铁律 记住 每次照做") == 1),
        ("two passes named", ("第一遍 · 手脚" in out) and ("第二遍 · 脑子" in out)),
        ("table heading intact", out.count("## 铁律总表（L1–L25）") == 1),
        ("all 25 law rows intact", out.count("| **L") == 25),
        ("group A..F intact", all(out.count("### %s 组" % g) == 1 for g in "ABCDEF")),
        ("chapter 0 intact", out.count("## 第 0 章") == 1),
        ("maintenance rule intact", out.count("**本文件维护规则**") == 1),
        ("no escaped-newline corruption", "\\n" not in BLOCK and "/r/n" not in BLOCK),
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
