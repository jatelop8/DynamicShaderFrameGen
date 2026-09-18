#!/usr/bin/env python3
"""Append section 15 to the 2026-09-18 daily log (append-only, marker-guarded).

Dry run by default; --apply writes.
"""
import io
import sys

TARGET = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-18.md"
MARKER = "## 15. 23:33"

SECTION = """

## 15. 23:33–23:42 —— 反转：「超分已拔掉」是**过期注释**，实际 render scale = 0.44

### 15.1 起因：我在 16.12 里留的那个探针是坏的

我写「下次运行先看 `mvecScale` 在运动中是否变化」。落盘前按项目铁律（**改配置项前先读它自带的说明**）
去读 INI，读到：

```ini
MvecScaleOverride=1.00        ; 0.00 = legacy 1/renderScale（默认）  1.00 = identity
;   注释原文：open-shaders 说 "must keep mvecScale at identity or DLSS massively over-estimates motion"
```

⇒ `mvecScale=(1.000,1.000)` 是**配置钉死的常量**，运动中也恒为它。**拿常量当门 = 空操作。**
**我在同一小时里第二次踩同一条铁律。** 已在账本 16.12 原位标注作废、16.14 给替代探针。

### 15.2 顺着读下去，翻出一个更大的案

INIT 里紧挨着的 NOTE 写着：

> "NOTE (v0.52): **EnableUpscale and PresetDLSS are still PARSED but NOT WIRED to anything** —
>  DLSS upscaling was removed in v0.48 … **The live render-scale control is `RenderResolutionScale`**"

⇒ **`EnableUpscale=1` 是死键**（读但不接线）。活的那把被设成了：

```
DynamicShaderFrameGen.ini:  RenderResolutionScale=0.44
[23:09:42.659] [FrameGen] Render scale 0.440 -> 1689x950 render / 3840x2160 output
[23:10:03.658] [XRAY] env: virtual=3840x2160 physical=3840x2160@160Hz render=0.4400
```

**引擎在 1689x950 渲染、放大到 3840x2160。0.44 是很激进的超分比。**
而 `main.cpp:33` / `FrameGen.h:216` 两处注释都说"超分/DRS/Halton jitter 已全部拔掉" ——
**那两句是 v0.50 写的，此后配置改了 0.44，注释没跟着改。**

⇒ **帧生成 + 超分是同时开着的**，这是最需要 jitter 正确的组合，而我们仍在
`Streamline.cpp:1231` 喂 `jitterOffset = {0,0}`（死字段）。

★ 教训（我自己的老账）：**"代码里写着已拔掉" ≠ "配置里没打开"。**
**读注释要连同"注释写下之后配置有没有变"一起读。**

### 15.3 但边界必须划清（不假装）

只证明了"**超分是活的、jitter 值得查**"，**没有**证明"喂 0 已造成可见损伤" ——
前提是"引擎确实对相机 jitter"，而这一点**目前测不到**（`jitterX/jitterY` 是死字段；
`CameraProj` 与 `CameraProjUnjittered` 的对应关系未确认），**需要一行新日志**：
把这两个矩阵**逐元素 diff** 打出来。恒 0 ⇒ 闭合；非 0 ⇒ 活缺陷。

★★ **但不要现在改代码。** v1.07c 还没上机验证过，再塞一个变量进去，下次运行又说不清谁起作用。
**先让 v1.07c 单独跑完**（判据见 16.7）。

### 15.4 「坏仪表 / 死键」本轮四次 —— 这是类别，不是四次意外

| 处 | 字段 | 形态 |
|---|---|---|
| 16.2(c) | `move=0.0000` / `snapAcceptDist=0` | 探针本身坏（据此写废了 15.2 整章） |
| 16.12 | `jitter=(0.0000,0.0000)` | 唯一写者 `OnMainUpdateJitter` 于 v0.50 删除，剩初值 |
| 16.14 | `mvecScale=(1.000,1.000)` | 被 `MvecScaleOverride=1.00` 钉死 |
| 16.15 | INI `EnableUpscale` / `PresetDLSS` | "PARSED but NOT WIRED" |

**铁律升级（合并 16.11）：读一个量之前，先证明它在"好/坏"之间会变。
不能变的量是仪表或配置，不是数据。** 三个动作：① `grep` 有没有写者；
② INI 里 `grep` 有没有 override 键；③ 读它自带的注释（**以及注释写下之后配置有没有变**）。

### 15.5 本轮落盘

| 项 | 值 |
|---|---|
| 账本 | `MFG_MASTER_NOTES.md` 83051 → **87754 B**（纯 LF，CRLF=0）：16.12 原位标注作废 + 新增 16.14/16.15/16.16/16.17 |
| 补齐脚本 | `tools/notes_ch16d_layout.py`（双改动：E1 替换型**天然幂等**，E2 插入型带 marker 守卫；15 项后置检查全 OK） |
| 顺带发现 | 一条**过期提示串**：`DLSSG tag dims … must read 2560x1440` 而实际 buffer 是 3840x2160 —— 会误导读日志的人（16.16，低优先） |
| 游戏侧 | **仍未开游戏**。v1.07c 是否真的不再"来回循环"仍未知 |
| 结论 | **下一轮第一步不变**：先让用户跑一次 v1.07c，再 `python tools/analyze_session.py` |
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    text = raw.decode("utf-8")
    print(f"daily log  {len(raw)} B  CRLF={raw.count(b'\r\n')}")
    if MARKER in text:
        print("REFUSED, nothing written: section 15 already present")
        return 1
    out = text.rstrip("\n") + SECTION
    checks = [
        ("15 present", "## 15. 23:33" in out),
        ("only one 15", out.count("## 15. 23:33") == 1),
        ("14 still present", "## 14. 23:25" in out),
        ("order 14 < 15", out.index("## 14. 23:25") < out.index("## 15. 23:33")),
        ("render scale recorded", "RenderResolutionScale=0.44" in out),
        ("overdue comment lesson", "代码里写着已拔掉" in out),
        ("dead keys recorded", "PARSED but NOT WIRED" in out),
        ("boundary kept", "不要现在改代码" in out),
    ]
    print()
    bad = 0
    for label, ok in checks:
        print(f"  {'OK  ' if ok else 'FAIL'} {label}")
        if not ok:
            bad = 1
    if bad:
        print("\nREFUSED, nothing written (post-condition failed)")
        return 1
    print(f"\nbytes {len(raw)} -> {len(out.encode('utf-8'))}")
    if not apply_changes:
        print("\nDRY RUN - nothing written. Re-run with --apply to write.")
        return 0
    with io.open(TARGET, "wb") as fh:
        fh.write(out.encode("utf-8"))
    r = io.open(TARGET, "rb").read()
    print(f"\nWROTE  {len(r)} B  CRLF={r.count(b'\r\n')}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
