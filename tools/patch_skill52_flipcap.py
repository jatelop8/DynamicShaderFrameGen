#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append section 52 to the framegen-diagnosis skill (LF-only file).

Numbering note: the file already contains a bare '## 51' near line 2022 (an
older section) as well as the '## 50.' added on 2026-09-19, so a new section
must not be called 51. LF-only: the appended text must use LF, and the
assertion is that bare-LF grows by exactly the number of lines added while
CRLF does not grow at all.
"""
import sys

S = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
MARK = "## 52. 根因㉒"

BODY = """## 52. 根因㉒ ★★★★★ 限速器的量子是 flip，不是渲染帧 —— 世界里只有 10 fps（L29，2026-09-19 14:55 那局）

### 52.1 症状与日志指纹

用户报"还是老样子 / 卡住 / 动不了"，但 watchdog 显示 `alive=1`、帧号在涨。
**先量真实帧率，再谈冻结。** 这一局：`frames 535→583 / 4.926 s = 9.74 fps`。

★ **四个数字就能定案，全部来自同一份日志，全部复现 `1e6/(refresh/capMult - 1)`：**

| 观测 | 日志值 | 反推 |
|---|---|---|
| `capUs`（倍数还没确认、capMult=2 时） | `12658` | `1e6/(160/2-1) = 1e6/79` |
| `capUs`（capMult=4 之后） | `25641` | `1e6/(160/4-1) = 1e6/39` |
| 真实帧间隔 `dt` | `102.56 ms` | `4 × 25641 us` |
| 真实帧率 | `9.74 fps` | `39/4` |
| 菜单里 `real` | `39.0` | 菜单 1 flip/帧 ⇒ `39/1` |

★ **判据「钉死 vs 飘动」**：限速器的量子是平的（`dt` 离散度 0.02 ms）；GPU 真的算不动时会飘几毫秒。
**钉死 ⇒ 人为节流；飘动 ⇒ GPU 受限。** 这条判据是区分二者唯一需要看的东西。

### 52.2 根因

`src/Streamline.cpp` → `ReflexSleep()`：

```cpp
const double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;  // ← 这个除法
opts.frameLimitUs = 1000000u / capFps;   // 160/4-1 = 39 => 25641 us
```

`frameLimitUs` 是**每个上屏 flip** 的量子。每真实帧要发 `capMult` 个 flip
⇒ 渲染侧被压成 `capFps / capMult`。**它不是 GPU 慢，是一道闸。**
正确写法：`want = refreshRate - 1.0` ⇒ `capFps=159`、`frameLimitUs=6289`
（工程内既有注释 `capUs=6289` 正是这个值）。

**逃生门**：INI `ReflexFpsLimit>0` 优先级高于公式，写 `40` 即可精确退回节流行为，不用换 DLL。

### 52.3 ★ L29 方法论：同一个函数里两段互相矛盾的注释 = 这里被改坏过

`Streamline.cpp` 的 **v0.63 注释**把上面这条根因诊断得**完全正确**（连 `102.56/25.641=4.0000`
都写出来了，并明确"倍率不再参与上限计算"）；紧下面的 **v1.06 注释**把同一行改了回去，
理由是"去掉除数是 636 present fps ⇒ 21:27 冻结" —— 那个推理把 **flip 上限当成了渲染上限**，
因果是反的。**执行的是 v1.06 那一版，两轮排查都从这段注释下方读过去，谁也没回头比对。**

> **判据不是"哪段注释更新"，而是"哪一段能被测量证实"。**
> 看到自相矛盾的注释：立刻把两段的预测都写成**可测量的判据**（这里是"`real` = capFps 还是 capFps/capMult"），
> 让日志裁决；不要靠注释的版本号排序。

### 52.4 修复后必须重测的相邻结论

真实帧率从 9.75 变成 ~39.7（4 倍）后，**所有以"到达次数"为单位的门和阈值的时间含义整体改变**
（例如 `kCamStillTol=90` 的墙钟时长）。所以：

> **改节拍的那一版，不要同时改锁/族指纹/接管逻辑。** 先在新节拍下重跑一局，
> 再决定那些结论还成不成立。一次只动一处可证伪的东西。

### 52.5 这一条和「冻结」的关系

节流本身就会**看起来像冻结**：4 个呈现帧摊在 102 ms 上，每个插帧要跨越 100 ms 的世界运动去重投影，
DLSS-G 做不到 ⇒ 插帧退化成复制品、输入延迟 100 ms+ ⇒ 用户说"卡住、动不了"。
**所以排查冻结之前，先把真实帧率量出来。** 这一局的 `clipDev` 已经非零（0.011~0.547）、
`clipW=1.000000`，说明重投影本身有运动 —— 冻结感来自节流，不是来自相机链。
"""


def main():
    apply = "--apply" in sys.argv
    raw = open(S, "rb").read()
    crlf0 = raw.count(b"\r\n")
    lf0 = raw.count(b"\n") - crlf0
    print(f"skill: {len(raw)} B  CRLF={crlf0}  bareLF={lf0}  (expect LF-only)")
    if crlf0:
        print("REFUSED, nothing written (file is not LF-only; decide the EOL again)")
        return 1
    text = raw.decode("utf-8")
    if MARK in text:
        print(f"REFUSED, nothing written (marker {MARK!r} already present)")
        return 1
    if "## 52." in text:
        print("REFUSED, nothing written ('## 52.' already used)")
        return 1
    add = "\n" + BODY.rstrip("\n") + "\n"
    out = (text + add).encode("utf-8")
    crlf1 = out.count(b"\r\n")
    lf1 = out.count(b"\n") - crlf1
    n = add.count("\n")
    if crlf1 != crlf0 or lf1 - lf0 != n:
        print(f"REFUSED, nothing written (EOL accounting: crlf {crlf0}->{crlf1} "
              f"lf {lf0}->{lf1}, expected +{n} LF)")
        return 1
    # Post-conditions must be scoped to the ADDED text: a probe like
    # "ReflexFpsLimit" already exists in the skill, so counting it across the
    # whole file reports a false failure. (A whole-file ==1 assertion is only
    # valid for strings the patch itself introduces, e.g. the marker.)
    for probe in (MARK, "52.3 ★ L29", "capUs=6289", "want = refreshRate - 1.0"):
        if add.count(probe) != 1:
            print(f"REFUSED, nothing written (post-condition: {probe!r} not exactly "
                  f"once in the added text)")
            return 1
    if out.decode("utf-8").count(MARK) != 1:
        print("REFUSED, nothing written (marker not exactly once in the result)")
        return 1
    print(f"post-conditions: PASS   {len(raw)} B -> {len(out)} B  (+{n} LF lines)")
    if not apply:
        print("DRY RUN -- nothing written. Re-run with --apply.")
        return 0
    open(S, "wb").write(out)
    print(f"WRITTEN {S}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
