#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Promote every scattered 'iron law' in MFG_MASTER_NOTES.md into one top-level table.

User instruction, 2026-09-19 09:34, verbatim: "这是铁律".

The ledger currently keeps its laws in six different places (1.3, chapter 6,
13.1, 13.4, 15.1, 16.11-16.16, 18.3) and each round adds another upgrade.
Nothing is deleted: the originals stay where they are, and this table collects
and supersedes them. Inserted between the header block and chapter 0 so that a
fresh session reads it before anything else.

Dry run by default; --apply writes. Every anchor must occur exactly once.
"""

import io
import sys

PATH = "MFG_MASTER_NOTES.md"
MARKER = "## 铁律总表（L1–L25）"

ANCHOR_HEAD = "**每次改动后必须追写本文件**，它比对话历史权威。"

POINTER = ("**★★★ 动手前先读「铁律总表」（L1–L25）—— 它在本文件第 0 章之前，"
           "是全部章节教训的收编，两处冲突以它为准。**")

ANCHOR_CH0 = "## 第 0 章：四大目标与当前达成度（诚实表）"

TABLE = r"""## 铁律总表（L1–L25）—— 违反一次就白干一轮

**用户 2026-09-19 09:34 原话：「这是铁律」。**
本表是全文沉淀出的**操作层最高约束**。散落在各章的旧铁律（1.3 / 第 6 章 / 13.1 / 13.4 /
15.1 / 16.11–16.16 / 18.3）**原文一律不动**，此处只做收编与升级；两处冲突以本表为准。
每条后面是**真实代价**——没有代价的条目不该进来。

### A 组 · 读数：判断一个数能不能用

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L1** | **只有实测字段能当结论。** `dlssgMaxFramesToGenerate`（STOCK 上报）、`dlssgEffectiveMax`（我的请求）、`mult(pres)` 全是**声明**；事实只有 `dlssgAcceptedFrames` 与 `mult(acc)`。 | 1.3、13.1 |
| **L2** | **读任何量之前三问**：① 有没有写者（`grep`）② INI 有没有 override 键 ③ 注释是否过期。**不能变的量是仪表或配置，不是数据。** | 16.11 → 16.16，升级于 16.16 末 |
| **L3** | **解析器对无法解析的输入必须尖叫。** 打 `NO DATA` / 静默跳过 = 把异常翻译成"健康"，而空集在判读层和健康长得一样。 | `clipDev=([\d.]+)` 无负号；横幅 `\(compiled` 被 `(probe build, compiled` 打破 |
| **L4** | **名字会骗人，必须读定义。** `stage=` 是"最后写入的名字"不是"卡住的位置"；`camPrev(ok/used)` 的 ok 是**布尔**不是计数器；`CameraProj`(c8) ≠ `CameraProjUnjittered`(c40)。 | 13.4、19 章、20 章 |
| **L5** | **"这是个死仪表"的判定本身要复核。** `move=0.0000` 被我判为死字段，实为**相机真没动**（`move`=`snapAcceptDist` 瞬量，实测 0.5179/0.4637/…）。 | 19–20 章订正，一度误导 |

### B 组 · 判据：判断一条判据会不会响

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L6** | **判据必须会变化。** 拿僵死常量当门 = 空操作。 | v1.02c（`sameCamera` 恒真 ⇒ 每帧 identity） |
| **L7** | **证明它是你读它那一刻所代表的那一帧。** 会被覆盖的变量先快照，并把顺序写成索引断言。 | 18.3（`s_prevCamProj` 在 750 被覆盖 → 757 先快照） |
| **L8** | **累计量不能做窗口边界。** `path>0` 一旦涨上去就恒真 ⇒ 窗口盖满全局、**结论反向**。窗口边界必须是瞬量（`move`）。 | 19 章（错报 `8 of 8`，正确是 `0 of 8`） |
| **L9** | **回归必须在合成样本上自证会分歧**；最有力的是"两份样本只差一个变量，判据必须给相反结论"。 | CASE F / G |
| **L10** | **判读代码自己也要被测。** 回归脚本的真正价值常常不是验证新判据，而是对判读层做对抗测试。 | 一个"必须报 (b)"的样本逼出了负号 bug |

### C 组 · 动代码之前

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L11** | **改 A→B 之前先证明 A≠B。** 空操作修复 = 白干一轮 **+ 让用户白跑一趟游戏**。 | 第 17 章（把过期注释当代码，两构造器 `sha1` 相同） |
| **L12** | **插桩之前先证明那条路径会被走到。** | 探针三连空：`mvecScale`（INI 钉死）、`path`（累计量）、`[MOTION]`（0 行） |
| **L13** | **修一个真实错误 ≠ 修的是正在追的问题。** 修复生效而症状照旧 ⇒ 另有根因，不许收工。 | v1.04（`capMult` 真修好，冻结照旧） |
| **L14** | **"锚点唯一"与"只跑一次"是两件事。** 插入型补丁天然不消耗锚点，必须另有幂等守卫。 | 两次重复插入（`patch_design18b` / `patch_skill8`） |
| **L15** | **改后逐符号回读**；`post-condition` 检查**结果文本**，不是输入文本。 | 曾因检查输入而误报成功 |

### D 组 · 下结论之前

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L16** | **"输出被计数证明是通的" ≠ "这个状态机不是故障点"。** 发布计数是最便宜的反证。 | 15.1 |
| **L17** | **跨进程独立证据 > 自证。** 别的程序在 hook 点看到的同一份数据，比我的日志硬。 | 第 20 章（Transfusion `[MOTION]` 才是决定性证据） |
| **L18** | **同时发生 ≠ 因果。** 分不开就写"未证"，不许升格成结论。 | 4x 启动 ⊥ `CameraPosAdjust` 变值（差约 900 单位、无过渡帧） |
| **L19** | **一行未做的东西不许说做了。** 第 0 章的诚实表就是为此存在。 | 20/30 系一行未写；DLSS5 代码在、未上机 |

### E 组 · 与用户的接口（最贵的一组）

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L20** | **先把手上的可玩状态还给用户，再谈诊断。** | 09:05 改 INI（`Provider=0` + `MFGMaxFramesOverride=0`，带备份） |
| **L21** | **用户的症状描述是最高优先级证据，不许用我的假设覆盖它。** "画面是来回循环的"、"进不去游戏、只有音乐"两次把案子整个翻过来。 | 第 16 章、第 20 章 |
| **L22** | **让用户进游戏之前，先离线证明这趟运行有信息量。** 否则就是白跑：v1.07c 那次功能为空操作；07:37 那次心跳全落在停下之后（判据 0 先决条件：`heartbeats inside the moving window: N of M`，**`N=0` 即白跑**）。 | 第 17、19 章 |

### F 组 · 环境（正文见第 6 章）

| # | 铁律 |
|---|---|
| **L23** | **行尾逐文件实测**（改前实测、改后核对）。本工程：`Streamline.cpp` / `.h` 纯 CRLF；账本 / 技能 / 工具脚本纯 LF；`FrameGen.h`、`main.cpp` 混合。 |
| **L24** | **`core.autocrlf=true` 且无 `.gitattributes`** ⇒ 任何 `git checkout / reset / stash` 会把纯 LF 文件翻成 CRLF。**修法已写（18.9 E），未落地。** |
| **L25** | **构建即部署**；改后核**双份 md5**（build == MO2 部署）+ DLL 内字符串 `grep` 确认版本号 + 确认游戏本体 `data/` 无残留副本。 |

---

"""


def main():
    apply = "--apply" in sys.argv
    raw = io.open(PATH, "rb").read()
    s = raw.decode("utf-8")
    eol = "\r\n" if raw.count(b"\r\n") else "\n"
    print("file: %s  %d B  CRLF=%d  bare_LF=%d" %
          (PATH, len(raw), raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")))

    # idempotence guard: an insertion does not consume its anchor, so count==1
    # would still pass on a second run. L14 is the law that says so.
    if MARKER in s:
        print("REFUSED: %s already present (marker found)" % MARKER)
        return 2

    edits = [
        ("header pointer", ANCHOR_HEAD, ANCHOR_HEAD + eol + POINTER),
        ("ironclad table", ANCHOR_CH0, TABLE + ANCHOR_CH0),
    ]

    out = s
    for label, old, new in edits:
        n = out.count(old)
        print("  anchor %-16s count=%d %s" % (label, n, "OK" if n == 1 else "*** REFUSED ***"))
        if n != 1:
            print("REFUSED, nothing written.")
            return 2
        out = out.replace(old, new, 1)

    # the table is LF-only text; convert to the file's own eol if it ever needs it
    if eol != "\n":
        out = out.replace("\n", eol)

    # post-conditions on the RESULT text, not the input (L15)
    checks = [
        ("table present", out.count(MARKER) == 1),
        ("pointer present", out.count(POINTER) == 1),
        ("chapter 0 still here", out.count(ANCHOR_CH0) == 1),
        ("all 25 law rows present", out.count("| **L") == 25),
        ("chapters 1..20 intact", all(out.count("## 第 %d 章" % i) >= 1 for i in range(0, 21))),
        ("maintenance rule intact", out.count("**本文件维护规则**") == 1),
        # Only the INSERTED text is checked: the ledger legitimately mentions the
        # literal "/r/n" elsewhere (it is the escaped-heredoc trap this project
        # already recorded), so scanning the whole file would always fail.
        ("no backslash corruption in insert",
         "\\n" not in TABLE and "/r/n" not in TABLE and "/r/n" not in POINTER),
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
