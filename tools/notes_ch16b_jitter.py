#!/usr/bin/env python3
"""Insert 16.12 / 16.13 after the 16.11 closing line in MFG_MASTER_NOTES.md.

REWRITTEN 2026-09-18: the first draft of 16.12 claimed "jitter was verified zero,
not an open item". Verification of the evidence refuted it -- jitterX/jitterY have
NO writer anywhere in the non-backup sources, so the heartbeat value is a member
initializer, not a measurement (same class as the broken `move=0.0000` gauge in
16.2(c)). 16.12 now records the refutation; 16.13 pins the acceptance threshold.

Insert-after does not consume its anchor, so a marker guard is mandatory
(the "anchor unique" and "only runs once" properties are independent).

Dry run by default; --apply writes.
"""
import io
import sys

TARGET = "MFG_MASTER_NOTES.md"
MARKER = "### 16.12"
ANCHOR = "**下次找判据时先问这一句。**"

ADD = """

### 16.12 起草时我差点写错的一条：「jitter 已核实为 0，不是待查项」

起草版想当然地把心跳里的 `jitter=` 当成"实测引擎 jitter，8 条全 0 ⇒ 与 jitter 无关，闭环"。
**按 16.11 刚立的原则回头一查，结论相反：那不是读数，是死字段的初始值。**

全工程非备份源码里搜这两个符号：

```
$ grep -rn "jitterX\\|jitterY" src/ --include=*.cpp --include=*.h | grep -v src/backup-
src/FrameGen.h:186:      float jitterX = 0.0f;     <- 声明 + 初值，唯一一次出现在等号左边
src/FrameGen.h:187:      float jitterY = 0.0f;
src/Streamline.cpp:1231: c.jitterOffset = { -Get().jitterX, -Get().jitterY };   <- 读
src/Streamline.cpp:1386: Get().jitterX, Get().jitterY, ...                     <- 读
```

**⇒ 1 处声明（初值 0）+ 2 处读取 + 0 处写入。** 三处源码各自写明原因：

| 位置 | 原文 |
|---|---|
| `src/Streamline.h:62` | "v0.50 removed OnMainUpdateJitter, which was the ONLY writer of engineFrameCount" |
| `src/FrameGen.h:216` | "v0.50：DLSS 超分/DRS/Halton jitter 已全部拔掉（引擎回到 2560 原生渲染）" |
| `src/main.cpp:33` | "无 DRS、无 DLSS 超分、无 Halton jitter …… jitter 相关代码保留但**不调用**" |

⇒ **8 条心跳全 `(0.0000,0.0000)` 是必然，零信息量。**
**与 16.2(c) 的 `move=0.0000` 同类：坏仪表。**（16.2(c) 已经吃过一次 —— 我拿 `move=0` 推出
"被发布的相机原地不动"，整章作废。**同一个错，隔几小时又来一次，只是换了字段名。**）

★★ **但"记下"不够 —— 它指向一个活着的消费者：**
`Streamline.cpp:1231` 仍在往 SL 喂 `c.jitterOffset = {0,0}`，即 **一个死字段在给运行时提供输入**。
这正是 v0.50 那个 bug 的形状（`Streamline.h:62` 自己记着：唯一写者被删 ⇒ 字段恒为初值 ⇒
`slSetConstants` 每帧被拒 ⇒ 每帧重投影都坏）。**同一个错法在同一文件里已经发生过一次，
没有理由认为它只发生过一次。**

**待查（下一轮，本轮不动）**：两个 provider 用的是**两个不同的 jitter 源** ——
FidelityFX 路径自己算 `gameViewport->projectionPosScaleX/Y`（`src/FidelityFX.cpp:175-176`），
SL 路径读的却是这个死字段。**下次运行先看 `mvecScale` 在运动中是否变化**
（它是活的，本条心跳恒 `(1.000,1.000)`），用来区分"引擎确实不 jitter"与"这条链也是死的"。

### 16.13 判据 3 的阈值取 `1e-3`，不要取 0

判据 3 不能写"≈0"。日志实测下限：`clipDev=0.000061` 出现 7 次、`0.000023` 出现 2 次；
而 Transfusion 打印的合法 identity 帧 `rows=[0.99999994 …]` 与 1 的偏差是 6e-8 量级
⇒ **identity 的真实下限在 1e-5 量级**。验收写 **`clipDev < 1e-3`** 即为通过，
不需要新字段。（这条是 16.5 的 C4 直接推出来的，不是新主张。）
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    crlf = raw.count(b"\r\n")
    text = raw.decode("utf-8")
    print(f"{TARGET}  {len(raw)} B  CRLF={crlf}")
    if crlf > 0:
        print("  !! expected a pure LF file; refusing")
        return 1

    print(f"marker present: {MARKER in text}   (must be False or it ran)")
    if MARKER in text:
        print("REFUSED, nothing written: 16.12 already present")
        return 1

    n = text.count(ANCHOR)
    print(f"anchor count: {n}   (must be exactly 1)")
    if n != 1:
        print("REFUSED, nothing written")
        return 1

    i = text.index(ANCHOR) + len(ANCHOR)
    out = text[:i] + ADD + text[i:]

    checks = [
        ("16.12 present", "### 16.12" in out),
        ("only one 16.12", out.count("### 16.12") == 1),
        ("16.13 present", "### 16.13" in out),
        ("17 not accidentally started", "### 17" not in out),
        ("16.11 kept", "### 16.11" in out),
        ("16.5 regression table kept", "C0  200 组随机" in out),
        ("maintenance rule still last",
         out.rstrip().endswith("只在第 9 章与末尾追加。")),
        ("refutation recorded (0 writers)", "0 处写入" in out),
        ("dead-field consumer recorded",
         "一个死字段在给运行时提供输入" in out),
        ("threshold recorded", "`clipDev < 1e-3`" in out),
        ("it sits right after 16.11",
         out.index("### 16.12") > out.index("### 16.11")),
        ("and before the maintenance rule",
         out.index("### 16.12") < out.index("**本文件维护规则**")),
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
