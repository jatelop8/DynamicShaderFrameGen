#!/usr/bin/env python3
"""Append section 41 to the framegen-diagnosis skill (pure LF file).

Dry run by default; --apply writes. Marker guard prevents a double append.
"""
import io
import sys

TARGET = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
MARKER = "## 41. ★★★★★ 「代码里写着已拔掉」"

SECTION = """
## 41. ★★★★★ 「代码里写着已拔掉」≠「配置里没打开」—— 读任何数值之前的**三问** ★2026-09-18 实锤

### 41.1 触发场景

日志里有一个看起来很干净、很稳定、正好符合你期望的读数，于是你把它当成"事实"写进结论。
**在本项目里，这类读数有四次是假的，而且每一次都推着我写废一整章。**

### 41.2 三问（对**任何**要当作证据的值，逐条跑）

```bash
# 问 1：它有写者吗？（0 写者 = 它是初始值，不是测量值）
grep -rn "字段名" src/ --include=*.cpp --include=*.h | grep -v "src/backup-"
#   数一数：几处出现在等号**左边**？0 处 ⇒ 这个值永远等于它的初始化值。

# 问 2：INI 里有 override / 死键吗？（override = 它被配置钉死，运动中也恒定）
#   在部署的那份 INI 里搜字段名 + 搜 Override/Scale/Enable 系列键

# 问 3：它自带的注释是否过期？（注释写下之后配置变过吗）
#   读 INI 里那一行上下 10 行；读源码里引用它的那段注释
```

**判别式**：
- 值**恒定不变** ⇒ 它**不能**用作判据或探针（无论它看起来多合理）
- 值会变，但变化**恰好符合你的假设** ⇒ 先跑问 1～3 再引用

### 41.3 本次实锤（三个连着的坑，一次踩全）

**(a) `jitter=(0.0000,0.0000)` —— 唯一写者被删**

```bash
$ grep -rn "jitterX\\|jitterY" src/ --include=*.cpp --include=*.h | grep -v src/backup-
src/FrameGen.h:186:      float jitterX = 0.0f;     <- 唯一一次出现在等号左边
src/FrameGen.h:187:      float jitterY = 0.0f;
src/Streamline.cpp:1231: c.jitterOffset = { -Get().jitterX, -Get().jitterY };   <- 读
src/Streamline.cpp:1386: Get().jitterX, Get().jitterY, ...                     <- 读
```

⇒ **1 声明 + 2 读 + 0 写。** 原因写在源码注释里：`OnMainUpdateJitter` 于 v0.50 被删，
它是唯一的写者。**8 条心跳全 0 是必然，零信息量。**
★ 而 `Streamline.cpp:1231` **仍在拿它喂 SL** —— 死字段在给运行时提供输入。
这是"孤儿变量"的第二种形态：不只探针坏了，**产品代码还在消费它**。

**(b) `mvecScale=(1.000,1.000)` —— 被 INI 钉死**

```ini
MvecScaleOverride=1.00        ; 0.00 = legacy 1/renderScale（默认）  1.00 = identity
```
⇒ 运动中也恒为 1.00。**拿它当"这条链还活着吗"的探针 = 拿常量当门。**

**(c) 最贵的一个：`main.cpp` 注释说"超分已拔掉"，配置里渲染比是 0.44**

```
main.cpp:33 / FrameGen.h:216  :  "DLSS 超分/DRS/Halton jitter 已全部拔掉"（v0.50 写下）
DynamicShaderFrameGen.ini     :  RenderResolutionScale=0.44
[日志] [FrameGen] Render scale 0.440 -> 1689x950 render / 3840x2160 output
```

**引擎一直在低分辨率渲染再放大。** 而 INI 自己那段 NOTE 说得最准：

> `EnableUpscale` / `PresetDLSS` **still PARSED but NOT WIRED to anything**（v0.48 起）
> —— **真正的活控制是 `RenderResolutionScale`（或 `QualityMode`）**。

⇒ **`EnableUpscale=1` 是死键**（显示"开启"但什么都不做）。
只看 INI 里那个 `=1` 会得出完全相反的结论。

### 41.4 类别表：「死仪表 / 死键」的四种形态

| 形态 | 例子 | 怎么认 |
|---|---|---|
| 探针本身坏（从来没被写过） | `snapAcceptDist=0` ⇒ `move=0.0000` | 问 1：0 写者 |
| 唯一写者被移除，剩初值 | `jitter=(0,0)`（v0.50 删 `OnMainUpdateJitter`） | 问 1 + 读源码注释 |
| 被配置钉死的常量 | `mvecScale=(1,1)`（`MvecScaleOverride`） | 问 2 |
| 解析但不接线的配置键 | `EnableUpscale` / `PresetDLSS` | 问 3：读 INI 自带 NOTE |

★ 第三、四种**看起来最像真的**：一个在日志里"稳定合理"，一个在配置里"明明写着 1"。

### 41.5 边界（别过度引用）

问 1～3 只能证明"**这个读数不可信**"，**不能**证明"它指向的缺陷是真的"。
- `jitter` 死字段 ⇒ 只能推出"**jitter 值得查**"，推不出"喂 0 已经造成可见损伤" ——
  那还取决于"引擎是否对相机 jitter"，需要**另加一行日志**把
  `CameraProj` 与 `CameraProjUnjittered` 逐元素 diff 出来才知道。
- **推论：不要把"发现一个死仪表"写成"找到一个根因"。**

### 41.6 落地动作

1. 读任何字段前先跑三问（尤其在你**准备把它写进结论**的时候）
2. 发现死字段时，**同时搜"谁还在消费它"** —— 消费方才可能是真 bug 所在
3. 读代码注释时**顺带看一眼配置**：注释写于哪个版本？此后配置动过吗？
   **因果倒置的过期注释，比没有注释更危险**（本工程 §110 已记过一次）
4. **一次只动一个变量**：已经有一个改动在等上机验证时，**不要把新发现顺手塞进同一批** ——
   否则下次运行说不清是谁起作用
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    crlf = raw.count(b"\r\n")
    text = raw.decode("utf-8")
    print(f"SKILL.md  {len(raw)} B  lines={text.count(chr(10))}  CRLF={crlf}")
    if crlf > 0:
        print("  !! expected a pure LF file; refusing")
        return 1

    print(f"marker present: {MARKER in text}   (must be False or it ran)")
    if MARKER in text:
        print("REFUSED, nothing written: section 41 already present")
        return 1

    out = text.rstrip("\n") + "\n" + SECTION

    checks = [
        ("41 present", MARKER in out),
        ("only one 41", out.count(MARKER) == 1),
        ("40 kept", "## 40. ★★★★★ v1.07c" in out),
        ("41 after 40", out.index("## 40. ★★★★★") < out.index(MARKER)),
        ("three questions recorded", "问 1：它有写者吗" in out),
        ("jitter case recorded", "1 声明 + 2 读 + 0 写" in out),
        ("mvecScale case recorded", "MvecScaleOverride=1.00" in out),
        ("0.44 case recorded", "RenderResolutionScale=0.44" in out),
        ("dead-key table recorded", "解析但不接线的配置键" in out),
        ("boundary recorded", "写成\"找到一个根因\"" in out),
        ("one-variable rule recorded", "一次只动一个变量" in out),
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
    c = r.count(b"\r\n")
    print(f"\nWROTE  {len(r)} B  CRLF={c} bare_LF={r.count(chr(10).encode()) - c}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
