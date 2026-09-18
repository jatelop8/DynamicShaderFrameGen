#!/usr/bin/env python3
"""Two edits to MFG_MASTER_NOTES.md:

  E1 (replace, consumes its anchor -> idempotent by construction): mark the
     probe advice inside 16.12 as void.
  E2 (insert before the maintenance-rule block -> does NOT consume its anchor,
     so a marker guard on "### 16.14" is mandatory): append 16.14..16.17.

Facts behind E2, all verified from disk before writing:
  * deployed INI: RenderResolutionScale=0.44
  * log 23:09:42.659: "Render scale 0.440 -> 1689x950 render / 3840x2160 output"
  * deployed INI comment: "EnableUpscale and PresetDLSS are still PARSED but NOT
    WIRED to anything - DLSS upscaling was removed in v0.48 ... The live
    render-scale control is RenderResolutionScale"
  * deployed INI: MvecScaleOverride=1.00 -> the heartbeat's mvecScale=(1.000,1.000)
    is pinned by config and can never be used as a probe.

Dry run by default; --apply writes.
"""
import io
import sys

TARGET = "MFG_MASTER_NOTES.md"
MARKER = "### 16.14"
E1_OLD = """SL 路径读的却是这个死字段。**下次运行先看 `mvecScale` 在运动中是否变化**
（它是活的，本条心跳恒 `(1.000,1.000)`），用来区分"引擎确实不 jitter"与"这条链也是死的"。"""
E1_NEW = """SL 路径读的却是这个死字段。
**★ 这里我原本留的探针是「下次运行先看 `mvecScale` 在运动中是否变化」—— 那句作废：
`mvecScale` 被 `MvecScaleOverride=1.00` 钉死、恒为 1，不能作门。有效探针见 16.14。**"""
E2_ANCHOR = "\n\n\n---\n\n---\n---\n\n**本文件维护规则**"

E2_ADD = """
### 16.14 16.12 里那段"待查"的**探针选错了** —— 以本节为准

16.12 结尾我写：「下次运行先看 `mvecScale` 在运动中是否变化」。**这个探针无效。**

部署的 INI（`E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini:204`）：

```
MvecScaleOverride=1.00        ; 0.00 = legacy 1/renderScale（默认）  1.00 = identity
```

而且它自带的注释解释了为什么 1.00 是**正确**值（"must keep mvecScale at identity
or DLSS massively over-estimates motion"）。
⇒ `mvecScale=(1.000,1.000)` 是**配置钉死的常量**，运动中也恒为它。
**拿它当探针 = 拿常量当门。** 这正是 16.11/16.12 刚立的那条铁律 —— **我自己在同一小时里又踩了一次。**

**有效探针**（需要一行新日志，不是现有心跳能读到的量）：
把 `CameraProj` 与 `CameraProjUnjittered` **逐元素 diff** 打成一行。
- 恒 0 ⇒ 引擎不做 jitter ⇒ SL 路径喂 `jitterOffset={0,0}` 无害，16.12 那条闭合。
- 非 0 ⇒ 引擎在 jitter 而我们报 0 ⇒ 见 16.15，那是活缺陷。

★ **但不要现在就改这一行**：v1.07c 还没上机验证过，再塞一个变量进去，下次运行又说不清是谁起作用。
**先让 v1.07c 单独跑完。**

### 16.15 ★★★ 超分是**活的** —— 16.12 的 jitter 死链因此是活缺陷，不是理论问题

16.12 我一度按"jitter 无所谓"的方向写，依据是 `main.cpp:33` 与 `FrameGen.h:216` 都写着
"DLSS 超分/DRS/Halton jitter 已全部拔掉"。**部署的 INI 与日志否掉了这个前提：**

```
DynamicShaderFrameGen.ini:  RenderResolutionScale=0.44
[23:09:42.659] [FrameGen] Render scale 0.440 -> 1689x950 render / 3840x2160 output
[23:10:03.658] [XRAY] env: virtual=3840x2160 physical=3840x2160@160Hz render=0.4400
```

**引擎在 1689x950 渲染、放大到 3840x2160。0.44 是很激进的超分比。**
INI 自己的 NOTE 说得更准：**`EnableUpscale` / `PresetDLSS` 才是死键**（"still PARSED but NOT
WIRED to anything"），**真正的活控制是 `RenderResolutionScale`（或 QualityMode）** —— 而它被设成 0.44。

⇒ 帧生成与超分**同时开着**，而这正是最需要 jitter 正确的组合，我们却把 `jitterOffset` 喂成 `{0,0}`。

**但边界要划清（不假装）：** 这只能证明"超分是活的、jitter 值得查"，
**不能证明"喂 0 已经造成可见损伤"** —— 前提是"引擎确实对相机 jitter"，而这一点**目前没有测到**
（`jitterX/jitterY` 是死字段，`CameraProj` 与 `CameraProjUnjittered` 的对应关系也未确认）。
**所以它进 16.6 那张"未解释"表的邻居位，不进"已定案"。**

★★ 这一节的教训是我自己的老账：**"代码里写着已拔掉" ≠ "配置里没打开"。**
`main.cpp:33` 那句注释写在 v0.50，此后 `RenderResolutionScale` 被设成 0.44，**注释没跟着改**。
⇒ **读注释要连同"注释写下之后配置有没有变"一起读。**

### 16.16 顺带：一个会误导读日志的人的过期提示串

```
[23:10:35.546] [Streamline] DLSSG tag dims: hudless/scaling-output=3840x2160 depth=3840x2160
               mvec=3840x2160 - depth/mvec must read 2560x1440 (the real interop buffers)
```

提示语里的 `2560x1440` 是**过期常量**（写它的时候缓冲区是 2560x1440）。
当前 render=1689x950、interop 缓冲=3840x2160，**提示语与实际不符**，
会让人误判"尺寸不匹配"。低优先，**下次碰到这行时改成动态值，或直接删掉括号里的期望值。**

### 16.17 「坏仪表 / 死键」本轮出现了**四次** —— 这是一个类别，不是四次意外

| 处 | 字段 | 形态 |
|---|---|---|
| 16.2(c) | `move=0.0000` / `snapAcceptDist=0` | 探针本身坏（我据此写废了 15.2 一章） |
| 16.12 | `jitter=(0.0000,0.0000)` | 唯一写者 `OnMainUpdateJitter` 于 v0.50 删除，剩初值 |
| 16.14 | `mvecScale=(1.000,1.000)` | 被 `MvecScaleOverride=1.00` 钉死 |
| 16.15 | INI `EnableUpscale` / `PresetDLSS` | "PARSED but NOT WIRED" |

**合并后的读法铁律**（升级 16.11）：

> **在读一个量之前，先证明它在"好/坏"之间会变。不能变的量是仪表或配置，不是数据。**
> 三个动作：① `grep` 它有没有写者；② 在 INI 里 `grep` 有没有 override 键；
> ③ 读它自带的注释（**以及注释写下之后配置有没有变**）。

★ 这条在我这里是**复发型错误**，不是新错误 —— 四次里有两次发生在同一小时。
**下一轮开始把这三步写进分析脚本的注释头，作为读任何字段的前置动作。**
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    crlf = raw.count(b"\r\n")
    text = raw.decode("utf-8")
    print(f"{TARGET}  {len(raw)} B  CRLF={crlf}")
    if crlf > 0:
        print("  !! expected a pure LF file; refusing")
        return 1

    if MARKER in text:
        print("REFUSED, nothing written: 16.14 already present")
        return 1

    n1 = text.count(E1_OLD)
    n2 = text.count(E2_ANCHOR)
    print(f"E1 anchor count: {n1}   (must be exactly 1)")
    print(f"E2 anchor count: {n2}   (must be exactly 1)")
    if n1 != 1 or n2 != 1:
        print("REFUSED, nothing written")
        return 1

    out = text.replace(E1_OLD, E1_NEW)
    if out.count(E1_NEW) != 1:
        print("REFUSED, nothing written: E1 did not land exactly once")
        return 1
    if out.count(E1_OLD) != 0:
        print("REFUSED, nothing written: E1 old text still present")
        return 1

    i = out.index(E2_ANCHOR)
    out = out[:i] + E2_ADD + out[i:]

    checks = [
        ("16.14 present", "### 16.14" in out),
        ("16.17 present", "### 16.17" in out),
        ("only one 16.14", out.count("### 16.14") == 1),
        ("voided probe recorded", "那句作废" in out),
        ("dead mvecScale recorded", "MvecScaleOverride=1.00" in out),
        ("live render scale recorded", "RenderResolutionScale=0.44" in out),
        ("0.44 render ratio recorded", "1689x950" in out),
        ("staleness lesson recorded", "注释写下之后配置有没有变" in out),
        ("stale dims string recorded", "must read 2560x1440" in out),
        ("four occurrences counted", "出现了**四次**" in out),
        ("16.13 kept", "### 16.13" in out),
        ("16.11 kept", "### 16.11" in out),
        ("maintenance rule still last",
         out.rstrip().endswith("只在第 9 章与末尾追加。")),
        ("16.14 sits before the maintenance rule",
         out.index("### 16.14") < out.index("**本文件维护规则**")),
        ("section order 16.11 < 16.12 < 16.13 < 16.14 < 16.15 < 16.16 < 16.17",
         out.index("### 16.11") < out.index("### 16.12")
         < out.index("### 16.13") < out.index("### 16.14")
         < out.index("### 16.15") < out.index("### 16.16") < out.index("### 16.17")),
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
