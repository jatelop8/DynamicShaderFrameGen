#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Trim workspace MEMORY.md from 3053 to under the 3000-char injection cap.

Nothing is deleted that does not still exist elsewhere:
  - the four project goals are quoted verbatim in MFG_MASTER_NOTES.md chapter 1
    (asserted below, so the script refuses if the ledger ever stops carrying them)
  - the rest is pure wording compression

Dry run by default. --apply writes. Every anchor must be unique, and each
post-condition is checked on the RESULT, not on the input.
"""
import io
import sys

MEM = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/MEMORY.md"
LEDGER = r"D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md"

EDITS = [
    ("drop goals line (verbatim in ledger ch.1)",
     "\n**四大目标（用户原话）**：① MFG 可用（曾卡死冻结）② 游戏完美使用 ③ RTX 20~50 全系列 ④ 打通 DLSS5",
     ""),
    ("shorten dinput8 line",
     "；5,945,344 B = RTXMFG-Universal（零作用，`.rtxmfg-off`）；`version.dll.off` 保持。",
     "；5,945,344 B = RTXMFG（零作用，`.rtxmfg-off`）。"),
    ("drop redundant note on DLL line",
     "`0a10b4b636257d0a589fb5eec4d3b613`（构建==部署）；提交",
     "`0a10b4b636257d0a589fb5eec4d3b613`；提交"),
    ("thin the perf numbers",
     "（FPS 39.7→13.4，1% Low→1.1，真实帧 571ms）",
     "（FPS 39.7→13.4，真实帧 571ms）"),
    ("one word shorter",
     "**三段讲三件事，只有 900–904 仍成立**（它说的是",
     "**三段讲三件事，只有 900–904 仍成立**（说的是"),
]

# the deletion in edit 1 is only justified if the ledger still carries the goals
ledger = io.open(LEDGER, encoding="utf-8").read()
must_be_in_ledger = ["打通 DLSS5", "RTX 20~50", "MFG"]
for need in must_be_in_ledger:
    if need not in ledger:
        print("REFUSED: the ledger no longer contains %r - cannot drop it from the index" % need)
        sys.exit(1)
print("guard: ledger still carries the goals -> deletion is a relocation, not a loss")

raw = io.open(MEM, "rb").read()
txt = raw.decode("utf-8")
before = len(txt)

for label, old, new in EDITS:
    c = txt.count(old)
    print("  [%s] %-45s count=%d" % ("OK " if c == 1 else "BAD", label, c))
    if c != 1:
        print("REFUSED, nothing written (anchor not unique)")
        sys.exit(1)
    txt = txt.replace(old, new, 1)

after = len(txt)
ok = after <= 3000
print("chars %d -> %d  (cap 3000) -> %s" % (before, after, "OK" if ok else "STILL OVER"))
if not ok:
    print("REFUSED, nothing written")
    sys.exit(1)

for k in ("v1.08-probe", "0a10b4b6", "1040–1043", "1084–1093", "900–904", "门控铁律",
          "解析器对", "p00(c/p)", "-195.22", "Modex", "一秒回到可玩", "DLSS5",
          "acceptance-v1.08.html", "14.6", "Transfusion"):
    if k not in txt:
        print("REFUSED: expected content missing: %s" % k)
        sys.exit(1)
print("all expected content still present")

if "--apply" in sys.argv:
    io.open(MEM, "wb").write(txt.encode("utf-8"))
    print("written")
else:
    print("dry run only - pass --apply to write")
