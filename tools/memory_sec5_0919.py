#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append section 5 to today's work log: the L0 meta-law and the iron-law table.

Append-only. Idempotent (marker guard). Dry run by default; --apply writes.
"""

import io
import re
import sys

PATH = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md"
MARKER = "## 5. 09:40"

BLOCK = r"""
## 5. 09:40　用户立 L0 元铁律：交付前自我检查两遍

**用户原话（09:40，逐字）**：
> 「我说的是每次你看完日志改完要自我检查两遍 再给我 不要每次骗我 这个是铁律 记住 每次照做」

**理解**：这不是又一条代码规则，是**约束我交付行为的元规则**。
用户说的「骗」= **未经证实的断言**——判据不是"我有没有撒谎"，而是"我手里有没有证据"。
前几轮我给的"修复"是空操作（第 17 章）、探针挂在永不执行的分支上（第 20 章）、
判据方向写反（第 19 章）——每一次我都以为是成果，用户都要花时间去撞。
**先给结论、后补验证，在用户那里与欺骗等价。**

**落地四处（内容按入口长度递减，避免长到没人读）**

| 位置 | 内容 | 字节 |
|---|---|---|
| `MFG_MASTER_NOTES.md` | **L0（元铁律）** + **「铁律总表」L1–L25**（收编原来散在 6 处的旧铁律） | 123605 → **131828** |
| `~/.workbuddy/MEMORY.md` | 同一份，放**第 3 行**（跨项目习惯，每次会话注入） | 92190 → **93843**（CRLF 保持） |
| 工作区 `memory/MEMORY.md` | 压成 3 行（手脚 / 脑子 / 交付要求） | 2683 → **2947** chars |
| 技能 `framegen-diagnosis` **§48** | 可执行版：48.1 手脚 / 48.2 脑子 / 48.3 交付格式 / 48.4 唯一可跳过的情形 | 340785 → **345030** |

**两遍的定义**（这是关键：铁律必须可执行、可外部验证）

- **第一遍 · 手脚**：逐符号回读落盘 / **逆操作还原逐字节相同** / 行尾计数 / 构建 /
  双份 md5 + 版本号字符串 / 锚点 `count==1` + `post-condition` 查**结果文本**
- **第二遍 · 脑子**：★**反向假设**（若结论是反的，日志长什么样？我看到的能否排除它）/
  这个量有没有写者、配置有没有 override、注释是否过期 / 这条路径真会走到吗 /
  `A≠B` / 同时发生≠因果 / 空集是否被当成健康 / **用户会不会因此白跑一趟**

**交付时逐条列出两遍结果**，不写"我已检查过"——用户要的是能据此行动的信息。

### 5.1 铁律总表（L1–L25）的收编来源

原来散在六处、每轮各自升级，从来没有单一出口：
1.3（只有 `dlssgAcceptedFrames` 是测量值）｜第 6 章（环境）｜13.1（只有实测字段能当结论）｜
13.4（名字会骗人）｜15.1（发布计数是最便宜的反证）｜16.11–16.16（读量三问）｜18.3（门控第三条）。
分组：A 读数 / B 判据 / C 动代码前 / D 下结论前 / **E 与用户的接口** / F 环境。
**原文一律不动**，总表只做收编，冲突以总表为准（表里写明）。

### 5.2 ★ 这条铁律在它诞生的同一次操作里就拦下了一次

写入铁律总表时，第一次 `--apply` **返回空输出**，我把它当成了成功。
实际**没有生效**——账本仍是 123605 B、总表计数 0。是回读抓到的。
⇒ 这件事当场写成了 **L0 第一遍第 1 条**的注脚（"`--apply` 报成功而文件未变是实测发生过的"）。
**这不是举例，是刚发生的事故。**

### 5.3 首次执行双检（机器证据）

`tools/verify_law0_insertion.py`（只读，退出码 0，**13/13**）：
- 账本删除插入块后 **与 git HEAD 逐字节相同**（123605 B）——
  "改前状态"不是猜测，**就是 HEAD**
- 用户级记忆还原 = 92190 B ✓｜技能还原 = 340785 B ✓
- 工作区记忆 2947 chars 未超 3000 ✓

★ 这个验证脚本**第一次运行时自己错了**：技能差 1 字节，原因是我切片写成 `s[:i+1]`，
而 `find()` 落在插入块 `\n\n---` 的**第二个** `\n` 上，多保留了 1 字节。
**是验证器错了，不是文件错了**——L10「判读代码自己也要被测」当场应验在自己身上。

**本轮未让用户做任何事**（无上机、无游戏），`src/` 未动，DLL 仍 `0a10b4b6…b613`，构建==部署。

**未证**：① 我无法自证"以后每次都真的会照做"——只能靠**交付时逐条列出两遍结果**做到外部可验证；
② 这条铁律能否真的减少返工，需要后续几轮检验。

---
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

    block = BLOCK if eol == "\n" else BLOCK.replace("\n", eol)
    out = s + block

    checks = [
        ("section 5 present once", out.count(MARKER) == 1),
        ("user words quoted", out.count("不要每次骗我 这个是铁律 记住 每次照做") == 1),
        ("pass definitions", ("第一遍 · 手脚" in out) and ("第二遍 · 脑子" in out)),
        ("the live accident recorded", "第一次 `--apply` **返回空输出**" in out),
        ("verifier's own bug recorded", "是验证器错了，不是文件错了" in out),
        ("unproven items listed", "**未证**：" in out),
        # Line start only: "### 4.9" contains the substring "## 4.", so a plain
        # count would be >1 for section 4.
        ("previous sections intact",
         all(re.search(r"^## %d\." % i, out, re.M) for i in range(1, 6))),
        # Only the escaped-heredoc corruption form is checked. The literal "\n"
        # IS intentionally quoted inside this block - it describes that very bug.
        ("no escaped-newline corruption", "/r/n" not in BLOCK),
    ]
    ok = True
    for label, good in checks:
        print("  post %-32s %s" % (label, "OK" if good else "*** FAIL ***"))
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
