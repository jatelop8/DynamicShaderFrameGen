#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append section 2 to the 2026-09-19 daily log: the hand-off audit done while the
user was going to sleep. Pure LF file, appended at the end.

Dry run by default; --apply writes.
"""
import io
import sys

PATH = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md"

ANCHOR = "本轮刻意未修任何功能 —— 在读数本身不可信时不加猜测式修复。\n"

BLOCK = """本轮刻意未修任何功能 —— 在读数本身不可信时不加猜测式修复。

## 2. 00:14–00:45 交班：记忆审计 + 行号漂移订正（用户去睡觉，要求不留遗漏）

用户原话：「你做好笔记记录，明天我们继续工作，记忆写清楚，不要遗漏重要的内容」。
做了三件事，**没有动代码、没有动二进制**（v1.08 仍 `0a10b4b6…b613`，等第一次上机）。

### 2.1 查出三个账本外的遗漏（都已补）

1. **★★ 账本里所有的行号都过期了** —— v1.08 在 757 行附近插了行，其后行号整体后移。
   旧写「1029–1032」（第 16.3 / 17.3 节反复引用）现在指向的是一段讲「按帧维护历史」的**中文注释**。
   ⇒ **行号过期与注释过期是同一个病**：第 17 章就是读了一句过期注释，白干一整天。
   实测现位置：**1040–1043**（"carries NO translation"，就是第 17 章骗到我的那段）、
   **1084–1093**（v1.07c 自写、已被证伪的注释）、**900–904**（更早的 `Proj @ View` 推导段，**仍成立**）。
2. **★★ 故意没改的欠账之前没进账本** —— 两段过期注释本应改成事实，但改注释要重新编译，
   会破坏**待上机二进制**的 md5 ⇒ 故意留到下次真正的代码改动。已连同第 14.6 节竞态、
   `acceptance-v1.07c.html`（保留作对照组）一起记入账本 18.9。
3. **账本缺一个「明天第一件事」的交班块** —— 已补 18.9 §C/D：四步顺序 + 四个仍无答案的问题。

### 2.2 落盘

| 项 | 值 |
|---|---|
| 账本 | `MFG_MASTER_NOTES.md` 101960 → **104835 B**（新增 18.9 交班：行号漂移表 / 欠账 / 明天四步 / 仍无答案） |
| 补丁脚本 | `tools/notes_ch18b_handoff.py`（8 条 post-condition，含「旧锚点被消耗」） |
| MEMORY.md | 3397 → **2936 chars**（压到 3000 上限以内；**唯一删除项「四大目标」在账本第 1 章有逐字原文**，脚本用守卫断言了这一点） |
| 补丁脚本 | `tools/patch_memory_0919.py`（5 条锚点各 count==1；改后重查 15 个关键串仍在） |

### 2.3 明天（2026-09-19 白天）第一件事

1. MO2 **取消勾选 `Modex.dll`**
2. 进游戏 → 等 4x → **站着不动 5 秒** → 走 5 秒转视角 → 退出
3. `python tools/analyze_session.py` → 五条判据（`docs/acceptance-v1.08.html`）
4. 出现 `[MOTION]` 行 ⇒ 读 `p00 cur/prev` + `mag invSrc` ⇒ **判 (a) 两侧投影不同 / (b) 投影相同而逆近奇异**

**注**：本轮是 v1.07b 以来第一次真正的上机机会 —— 但测的是 v1.08 的**读数**，
不是「修复」。**修复要等读数出来之后再动**（第 17/18 章的教训）。
"""


def main():
    raw = io.open(PATH, "rb").read()
    txt = raw.decode("utf-8")

    if "## 2. 00:14" in txt:
        print("REFUSED: section 2 already present")
        return 1
    if txt.count(ANCHOR) != 1:
        print("REFUSED, nothing written (anchor count = %d)" % txt.count(ANCHOR))
        return 1

    out = txt.replace(ANCHOR, BLOCK, 1)

    checks = [
        ("sec1 intact", out.count("## 1. 00:04") == 1),
        ("sec2 added", out.count("## 2. 00:14") == 1),
        ("line drift recorded", "1040–1043" in out and "1084–1093" in out and "900–904" in out),
        ("debt recorded", "刻意没改的欠账" in out or "故意没改的欠账" in out),
        ("tomorrow steps", "Modex.dll" in out and "analyze_session.py" in out),
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
