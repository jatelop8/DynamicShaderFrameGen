#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Correct the inverted camera-family claims in the framegen-diagnosis skill.

SKILL.md is LF-only. Dry run by default; --apply writes. Every anchor must
occur exactly once, and the correction marker makes a second run a no-op.
"""
import sys, pathlib

P = pathlib.Path("C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md")
MARK = "CORRECTION（22:22 真值）"

SK1_OLD = """判据：`world` 在涨（已经在世界里渲染）**而 `proj00` 是 0.8391** ⇒
DLSS-G 拿到的是"给一个已经不存在的世界"的相机 ⇒ **画面冻、帧数活**。
"""

SK1_NEW = """判据：`world` 在涨（已经在世界里渲染）**而 `proj00` 是 0.8391** ⇒
DLSS-G 拿到的是"给一个已经不存在的世界"的相机 ⇒ **画面冻、帧数活**。

> **★ CORRECTION（22:22 真值）——上面这条判据的结论是反的。**
> `proj00=0.8391` **就是玩家相机**。真值证据见 39.2 的更正表。
> 当时把「谁在动」当成了「谁是相机」，而那个判据在整条 v1.00–v1.15 支线里都成立、
> 都指向了错的一侧。
"""

SK2_OLD = """| 族 | `ProjUnj[0][0]` | 位置特征 | 是不是相机 |
|---|---|---|---|
| **A 世界（玩家）** | `0.149184` | 随玩家 glide（`(-50,600,80)` 起） | **是** |
| B 单位/正交 | `1.0` | `(-160,160,128)` 恒定 | 否 |
| **C 3D 菜单** | `0.8391` | `(-243.05,-415.31,118.56)` 恒定 | **否** |

A 与 C 相差 **5.62x**，所以 `±2%` 相对比率测试**足以判别**。C 的证据在 `FrameGen.h`
（row3 `(-0.00391655,0.999991,0.0015,0)`，「not a camera at all, but a mis-offset read of the
perFrame constant buffer」）。
"""

SK2_NEW = """| 族 | `ProjUnj[0][0]` | 位置特征 | 是不是相机 |
|---|---|---|---|
| ~~A 世界（玩家）~~ | `0.149184` | 菜单期在动（`(-50,600,80)` 起） | ~~是~~ **否** |
| B 单位/正交 | `1.0` | 至少两个写者并桶，`span≈(975,901,87)` | 否 |
| ~~C 3D 菜单~~ | `0.8391` | `(-243.05,-415.31,118.56)` | ~~否~~ **是** |

> **★★★ CORRECTION（22:22 真值）——这张表原来的 A 与 C 是反的，整整两天所有结论都建立在它上面。**
>
> 真值来自 `RE::PlayerCamera::GetSingleton()->cameraRoot->world.translate`（v1.16 探针，每秒一行）：
>
> | 时刻 | `match` | `best` | 那个到达者的 `proj00` |
> |---|---|---|---|
> | 菜单期 | **0** | 603.99 → 835.51 | `0.149184` |
> | 进世界后 | **154 → 456** | **0.00** | **`0.8391`** |
>
> `best=0.00` = 到达者的 `CameraPosAdjust` 与活相机眼睛**相距 0.00 单位**，每秒 397 次。
> 三条 `PC TAKEOVER ... 0.00 units from the live player camera ... proj00=0.8391`。
>
> ⇒ **`0.8391` 是玩家相机；`0.149184` 是主菜单相机**（离玩家 604–836 单位）。
> ⇒ `0.8391` 昨天被当成"停着的写者"，其实那是**玩家站着不动**。
> ⇒ `proj00=1` 的 `(-160,160,128)` 并不是相机：那个桶里至少两个写者互相跳
> （`span=(974.79,901.49,86.68)`、`stepSum=542149.75`，而 `last` 四秒只挪 1.9）。
>
> ★ **方法论**：从写者身上**推断**「谁是相机」这条路，两天里给出的**每一个**结论都错了。
> 选源必须用**可判定的真值**（引擎自己的活相机节点），不能靠"谁在动""谁最后写""谁量级不同"。
"""

SK3_OLD = """   活相机（`proj00=1`）以 ~100/s 被拒。
"""

SK3_NEW = """   ~~活相机（`proj00=1`）以 ~100/s 被拒。~~ **★ CORRECTION（22:22 真值）**：`proj00=1` **不是**相机
   —— 那个桶里至少两个相距约 1000 单位的写者并桶（`span=(974.8,901.5,86.7)`、`stepSum=542149`），
   是正交/离屏通道。**玩家相机是 `proj00=0.8391`**，而 `0.149184` 是主菜单相机。
"""

EDITS = [
    ("SK1  39.1 判据更正", SK1_OLD, SK1_NEW),
    ("SK2  39.2 族表更正", SK2_OLD, SK2_NEW),
    ("SK3  判据链第 4 条更正", SK3_OLD, SK3_NEW),
]

def main():
    apply = "--apply" in sys.argv
    b = P.read_bytes()
    if b"\r\n" in b:
        print("REFUSED: SKILL.md is not LF-only"); return 1
    s = b.decode("utf-8")
    if MARK in s:
        print("REFUSED: already corrected (marker present)"); return 1
    for label, old, new in EDITS:
        n = s.count(old)
        if n != 1:
            print("REFUSED, nothing written: %s anchor count = %d (must be 1)" % (label, n))
            return 1
    if not apply:
        print("dry run OK: %d/%d anchors unique in SKILL.md" % (len(EDITS), len(EDITS)))
        for label, _o, _n in EDITS:
            print("  would patch " + label)
        return 0
    for label, old, new in EDITS:
        s = s.replace(old, new, 1)
        print("  patched " + label)
    checks = [
        ("CORRECTION marker", s.count(MARK), 3),
        ("old A row gone", s.count("| **A 世界（玩家）** | `0.149184`"), 0),
        ("old C row gone", s.count("| **C 3D 菜单** | `0.8391`"), 0),
        ("ground truth line", s.count("cameraRoot->world.translate"), 1),
        ("best=0.00 stated", s.count("`best=0.00`"), 1),
    ]
    bad = [(n, g, w) for n, g, w in checks if g != w]
    if bad:
        for n, g, w in bad:
            print("POST-CONDITION FAIL: %s = %d, wanted %d" % (n, g, w))
        return 1
    P.write_bytes(s.encode("utf-8"))
    print("wrote SKILL.md (%d bytes, was %d)" % (len(s.encode()), len(b)))
    return 0

if __name__ == "__main__":
    sys.exit(main())
