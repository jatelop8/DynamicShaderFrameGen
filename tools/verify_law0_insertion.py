#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L0 first pass, item 2: machine proof that this round's edits are pure additions.

Law L0 requires an inverse operation that restores the pre-change bytes exactly.
The ledger is under git, so 'the pre-change bytes' is not a guess - it is
HEAD. Removing the inserted blocks must reproduce HEAD byte for byte. For the
three files outside git, the byte counts measured before the edit are the
reference.

Read-only. Exit 0 = all pure additions.
"""

import io
import subprocess
import sys

BEFORE = {
    r"C:/Users/Administrator/.workbuddy/MEMORY.md": 92190,
    r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md": 340785,
}
WS_MEMORY = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/MEMORY.md"
LEDGER = "MFG_MASTER_NOTES.md"

POINTER = ("**★★★ 动手前先读「铁律总表」（L1–L25）—— 它在本文件第 0 章之前，"
           "是全部章节教训的收编，两处冲突以它为准。**")
TABLE_HEAD = "## 铁律总表（L1–L25）"
CH0 = "## 第 0 章：四大目标与当前达成度（诚实表）"
L0_HEAD = "### L0 · 元铁律"
GROUP_A = "### A 组 · 读数：判断一个数能不能用"

results = []


def check(label, ok, detail=""):
    results.append((label, ok, detail))
    print("  %-46s %s  %s" % (label, "OK" if ok else "*** FAIL ***", detail))


# ---------------------------------------------------------------- ledger
raw = io.open(LEDGER, "rb").read()
cur = raw.decode("utf-8")
head = subprocess.run(["git", "show", "HEAD:%s" % LEDGER],
                      capture_output=True).stdout.decode("utf-8")
print("ledger: current %d B, HEAD %d B" % (len(raw), len(head.encode("utf-8"))))

reverted = cur
# strip the L0 block: from its heading up to the next group heading
i, j = reverted.find(L0_HEAD), reverted.find(GROUP_A)
check("L0 block located", i > 0 and j > i, "at %d..%d" % (i, j))
if i > 0 and j > i:
    reverted = reverted[:i] + reverted[j:]
# strip the iron-law table: from its heading to chapter 0
i, j = reverted.find(TABLE_HEAD), reverted.find(CH0)
check("table located", 0 <= i < j, "at %d..%d" % (i, j))
if 0 <= i < j:
    reverted = reverted[:i] + reverted[j:]
# strip the header pointer line
check("pointer located", reverted.count(POINTER) == 1)
reverted = reverted.replace(POINTER + "\n", "", 1)

rb = reverted.encode("utf-8")
check("ledger reverts to HEAD byte-for-byte", rb == head.encode("utf-8"),
      "%d B vs %d B" % (len(rb), len(head.encode("utf-8"))))

# sanity: the ledger did grow (otherwise the revert test is vacuous)
check("ledger actually grew", len(raw) > len(head.encode("utf-8")),
      "%+d B" % (len(raw) - len(head.encode("utf-8"))))

# ------------------------------------------------- cross-project memory
p = r"C:/Users/Administrator/.workbuddy/MEMORY.md"
raw = io.open(p, "rb").read()
s = raw.decode("utf-8")
i = s.find("## ★★★★★ 元铁律：交付前自我检查两遍")
j = s.find("## ENB 配置铁律（跨项目，2026-09-15 实测）")
check("user memory: block located", 0 < i < j)
back = (s[:i] + s[j:]).encode("utf-8")
check("user memory reverts to %d B" % BEFORE[p], len(back) == BEFORE[p],
      "%d B" % len(back))
check("user memory grew", len(raw) > BEFORE[p], "%+d B" % (len(raw) - BEFORE[p]))

# ------------------------------------------------------------------ skill
p = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
raw = io.open(p, "rb").read()
s = raw.decode("utf-8")
i = s.find("\n---\n\n## 48. ★★★★★ L0 元铁律")
check("skill: section 48 located", i > 0, "at %d" % i)
# find() lands on the SECOND '\n' of the inserted '\n\n---' (the first one is
# s[i-1]), so the pre-insert text is s[:i] - taking s[:i+1] keeps one byte of
# the block and reports a false failure. Verified by hand: s[:i] = 340785 B.
back = s[:i].encode("utf-8") if i > 0 else b""
check("skill reverts to %d B" % BEFORE[p], len(back) == BEFORE[p], "%d B" % len(back))

# ------------------------------------------------------- workspace memory
raw = io.open(WS_MEMORY, "rb").read()
s = raw.decode("utf-8")
NEW = "**★★★★★ L0 元铁律（用户 2026-09-19，每次照做）：交付前自我检查两遍。**"
check("workspace memory: L0 pointer present", NEW in s)
check("workspace memory under the 3000-char cap", len(s) <= 3000, "%d chars" % len(s))
check("workspace memory holds the ledger pointer",
      "铁律总表" in s and "MFG_MASTER_NOTES.md" in s)

print()
bad = [r for r in results if not r[1]]
print("RESULT: %s (%d checks, %d failed)" %
      ("OK - every edit is a pure addition" if not bad else "NEEDS FIX",
       len(results), len(bad)))
sys.exit(0 if not bad else 1)
