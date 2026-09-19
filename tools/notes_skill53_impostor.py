#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append SKILL section 53 (root cause #23 + L30) to the framegen-diagnosis skill.

Idempotency guard: refuses when the section header is already present.
The skill file is PURE LF (6715 lines, 0 CRLF as of 2026-09-19 18:50) -- append LF only.

Usage:
    python tools/notes_skill53_impostor.py            # dry run
    python tools/notes_skill53_impostor.py --apply    # write
"""
import sys
import pathlib

SKILL = pathlib.Path(r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md")

MARKER = "## 53. 根因㉓"

BODY = """## 53. 根因㉓ ★★★★★ 那个「相机」根本不是相机：同一个 CB 每渲染帧被写 20 多次（L30，2026-09-19 18:20 那局）

### 53.1 症状与日志指纹

上一版（v1.12）已经把真实帧率从 `9.74 fps` 修到 `24.3 fps`（世界）/ `48.3 fps`（菜单）
并且 `DLSSNR CHAINED with frame generation` 在线，DLSS-G 也自报 `ask=4 accepted=4`
—— **功能全在跑，画面依旧不动**。这类"全绿但不动"必须换一种读法：

| 观测 | 日志值 | 含义 |
|---|---|---|
| `arrivalsPerSec` | `591` | 每秒对同一个 perFrame CB 的 Map 次数 |
| `real`（世界） | `~24` | 真实渲染帧率 |
| `591 / 24` | **≈ 22** | ★ 每渲染帧这个缓冲被写 20 多次 |
| `matChanges` | `+40/s` | 正好 `2 × 24` ⇒ 两个来源在抢同一个槽 |
| `path` | 卡在 `124.92` 三十秒 | 发布出去的矩阵不动了 |
| `same-family step break` | 31 ms 内 4 次（376.6 / 255.2 / 452.7） | 多个 pass 的假相机在互相抢锁 |

### 53.2 根因：hook 取的是「最后一个写者」，不是「相机」

Map/Unmap 钩子（槽 14/15）为每个匹配的 Map 记下 `tlsMappedFB`，**被下一次匹配的 Map 覆盖**。
一个渲染帧里同一个缓冲被写 22 次 ⇒ 我们拿到的永远是**最后一个 pass** 写进去的内容。
在世界里，最后一个 pass 是**一个正交全屏投影**（UI / 后处理类），不是相机。

**解剖那一群样本（十个字段全部退化成平凡矩阵）：**

```
c0  View  = [[0,0,1],[0,1,0],[1,0,0]]        ← 精确的轴交换置换阵
c8  Proj  = diag 到 [[1,0,0,0],[0,1,0,0],[0,0,1.111111,-0.1111111],[0,0,0,1]]
c40 ProjU = 上面那个的精确逆（det 0.9 ↔ 1.11111）
c32 PrevVPU = 全零
```

按 D3D 投影格式反解 `c8`：`m22 = zf/(zf-zn) = 1.111111`、`m23 = -zn·zf/(zf-zn) = -0.1111111`，
且 **`m32 = 0, m33 = 1`（没有透视除法）**。令 `zf = 1, zn = 0.1` 得
`z' = (z-0.1)/0.9 = 1.1111z - 0.1111` —— **逐位吻合**。
⇒ 这是把 `[0.1, 1]` 映到 `[0, 1]` 的**全屏正交投影**。

**三条独立旁证**（不是同一证据的复述）：

1. `CameraPreviousPosAdjust` 在世界里**恒为 (0,0,0,0) 整整三十秒**；菜单期它紧贴 `pos`。
   一个"上一帧相机位置"不可能是零向量。
2. **`m32=0` 是结构性判据**：真实相机投影必然 `m32=1, m33=0`。
3. 到达率 ÷ 帧率 ≈ 22，与 CS 的 hook（同 REL ID `524768/411384`、同槽 14/15）机制完全一致。

### 53.3 ★ 反证：字段偏移是对的（不要误改偏移）

同一局**主菜单那七分钟**，十个字段全是真相机：`path` 0→117.60 单调、`prevPos` 紧贴 `pos`（差 0.1~0.3）、
`Proj row3 = (0,0,1,0)`、`det=79.9373 mag=15.011`（手算分解出无穷远投影 `zn=15.011`）。
并且 **`ViewProj = Proj · View` 精确成立**（不是近似）。

> **不要因为世界期读数是垃圾就去改字段偏移。** 先证「同一套偏移在另一段时间里是对的」，
> 把问题从「读错字段」区分为「读错人」。

### 53.4 修法：捕获侧内容门 + 逃生门

```cpp
const bool camShaped =
    (std::fabs(a_src.CameraProj.data[3][2]) >= 0.05f) &&   // 透视除法在
    (std::fabs(a_src.CameraProj.data[3][3]) <= 0.05f);     // 齐次 w 分量归一
if (!camShaped) {
    ++snapNonCamera; ++snapSkipsSinceCam;
    if (snapSkipsSinceCam < kCamCaptureFallbackSkips)   // 6000
        return false;                    // 不发布
}
```

判据是 **`1 vs 0`** 而不是估值：相机写 `|Proj[3][2]|=1, |Proj[3][3]|=0`；
假相机写**恰好反过来**。阈值 `0.05` 只是浮点余量，两群之间差整整 1.0。

`[CAM] pub` 行尾追加 `cap={}/{}`：左边 = 被丢弃的非相机写次数，右边 = 距上次成功捕获的连续跳过数。

### 53.5 ★ L30：共享槽位的选源铁律

> **同一个槽位被多个来源共享时，「谁最后写」不是选源依据。**
> 选源必须用**内容里可判定的特征**（这里是 `m32/m33` 的透视除法）。

配套两条，缺一不可：

1. **新判据必须带逃生门**：连续 N 次（这里 6000）不匹配就**自动退回旧行为** ⇒
   最坏情况 = 改动前的行为，**这一趟不会比现在更糟**。这是敢于上机的唯一理由。
2. **先测出两群样本的分离量再写判据**：分离量 1.0 和 0.01 是两种完全不同的可信度。
   分离量是 1.0 才敢写硬阈值。

### 53.6 下一局的判据表

| 看到什么 | 结论 |
|---|---|
| `cap=` 左边 ≈ 帧率（每秒涨 ~24）、右边稳步回落到 0 | 判据生效，世界里**确实有**相机写 |
| `path` 开始增长；走动时 `clipDev` 明显 > 0（不再恒 `0.000061`） | 重投影拿到真实运动 ⇒ 插帧第一次有内容 |
| `matChanges` 不再有 `2×fps` 的固定倍率 | 抢槽的双写者被清掉了 |
| `cap=` 左边**恒 0**、右边一路涨到 6000 且旧行为自动恢复 | ★ 世界内根本没有相机写这个 CB ⇒ 换 `RE::PlayerCamera` 源（`cameraRoot->world.translate` 取眼位，CS 参照 `Hooks.cpp:719-722`） |

### 53.7 与前面各条的关系

- 与 §52 的区别：§52 是「真实帧率被闸住」（`dt` 钉死），本条是「帧率正常但重投影恒等」。
  **两者都会让用户说"卡住、动不了"** —— 排查顺序永远是：先量真实帧率（§52），再查重投影（本条）。
- 与 §40 的区别：§40 是 `prev` 取自一台没有平移的相机（**我读错了字段语义**）；
  本条是 `prev/cur` 都取自一个**根本不是相机的写者**（**我读错了人**）。层次不同，症状相同。
"""


def main() -> int:
    apply = "--apply" in sys.argv
    if not SKILL.exists():
        print(f"REFUSED: skill not found: {SKILL}")
        return 1

    raw = SKILL.read_bytes()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    if crlf != 0:
        print(f"REFUSED: expected a PURE LF file, found {crlf} CRLF (bare LF {bare})")
        return 1

    text = raw.decode("utf-8")

    # --- idempotency guard: the anchor rule "count(old)==1" does NOT prove "never ran" ---
    if MARKER in text:
        print(f"REFUSED, nothing written: {MARKER!r} already present")
        return 1

    # --- splice guard: append at EOF, separated by exactly one blank line ---
    if not text.endswith("\n"):
        print("REFUSED: file does not end with a newline; inspect before appending")
        return 1
    tail = text[-3:]
    if tail.endswith("\n\n\n"):
        print("REFUSED: file already ends with two blank lines; inspect before appending")
        return 1

    out = text + "\n" + BODY + "\n"

    # --- post-conditions on the RESULT text ---
    probes = [
        ("section header once", out.count(MARKER), 1),
        ("L30 label once", out.count("L30：共享槽位的选源铁律"), 1),
        ("arrivalsPerSec evidence", out.count("`arrivalsPerSec`"), 1),
        ("camShaped snippet", out.count("kCamCaptureFallbackSkips"), 1),
        ("escape-hatch rule", out.count("自动退回旧行为"), 1),
    ]
    bad = [f"{name}: got {got}, want {want}" for name, got, want in probes if got != want]
    if bad:
        print("FAIL post-conditions:\n  " + "\n  ".join(bad))
        return 2

    new_crlf = out.encode("utf-8").count(b"\r\n")
    if new_crlf != 0:
        print(f"FAIL: result would contain {new_crlf} CRLF (file must stay pure LF)")
        return 2

    if not apply:
        print("DRY RUN OK (nothing written)")
        print(f"  would grow: {len(raw)} -> {len(out.encode('utf-8'))} bytes")
        print(f"  lines: {text.count(chr(10))} -> {out.count(chr(10))}")
        print("  re-run with --apply to write")
        return 0

    SKILL.write_bytes(out.encode("utf-8"))
    print("APPLIED")
    print(f"  bytes: {len(raw)} -> {len(out.encode('utf-8'))}")
    print(f"  lines: {text.count(chr(10))} -> {out.count(chr(10))}")
    print(f"  CRLF: 0 (pure LF preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
