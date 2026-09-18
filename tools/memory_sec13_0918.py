#!/usr/bin/env python3
"""Append section 13 to the 2026-09-18 daily memory log (pure LF file).

Append-only. Dry run by default; --apply writes. Marker guard prevents a
double append.
"""
import io
import sys

TARGET = (r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48"
          r"/.workbuddy/memory/2026-09-18.md")
MARKER = "## 13. v1.07c"

SECTION = """
---

## 13. v1.07c —— 重投影矩阵的逆取自一台没有平移的相机（23:22）

### 13.1 用户的关键观察（把案子翻过来的那句话）

> "这次只有4帧，我发现画面是来回循环得，由于帧数低了，所以看的比较清楚，帧数高就觉得这个循环比较快，看着像卡了"

"来回循环" ≠ "静止不动"。第 12 节（以及账本第 15 章）我按"静止"解释冻结，
解释不了"来回"。而"帧率越高越像卡住、越低越看清是循环"这一句，
只有一个机制能同时满足：**画面在以很少几帧为周期循环，循环频率随帧率上升。**

### 13.2 23:10 运行（v1.07b）的日志 —— 三条硬数据

**(a) `clipDev` 在同一个会话里于 identity 和"几百单位"之间交替**

```
23:10:50.746 clipDev=0.000023
23:10:51.414 clipDev=0.000023
23:10:51.982 clipDev=0.348060
23:10:52.440 clipDev=28.772085
23:10:52.905 clipDev=4.549722
23:10:53.383 clipDev=18.569712
min=0.000061 max=243.962387
```

★ 第 12 节写的"判据 A：clipDev 大 ⇒ 相机链是好的" —— **那条判据是错的**。
clipDev 同时受相机速度和帧时间影响，"大"不证明健康。**正确读法是看它是否交替。**

**(b) Transfusion 把我们发出去的矩阵原样打印**（frame 578，23:10:35.543）：

```
clipToPrev rows=[0.999993265 4.5692791e-06 -0.00143783959 -0.00143777835]
                [2.57021884e-06 2.25002486e-06 0.999290824 -0.000707997533]
                [-0.00171347801 -0.0015000155 0.473518044 0.471998006]
                [-243.962387 2.7390945 -77.6724777 -195.222366]
cameraPos=(-243.049301,-415.311523,118.558205)
```

对照 identity 时的 `row3 = [0 5.78e-06 -6.10e-05 0.99999994]`
⇒ **合法仿射阵的 `[3][3] == 1`**；而这一帧 `row3[3] = -195.222366` ⇒ **连仿射都不是。**

**(c) `[CAM] acc` 的 `pos` 在匀速前进**（y 每步 +69），`cameraPos` 只在窗口内恒定。
`move=0.0000` 是**仪表坏了**（`snapAcceptDist` 恒 0），不是相机不动 ——
`path` 的增量精确等于 `pos` 的差（132.15→149.69 对应 `|(-15.25,6.59,5.65)|=17.55`）。
★ 12.2 的"被发布的相机原地不动"完全建立在坏仪表上。

### 13.3 缺陷

`Streamline.cpp:1073`：

```cpp
sl::matrixFullInvert(invCurrViewProj, curForReproj);               // 无平移的引擎矩阵
sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);   // 含平移的重建矩阵
```

`prevForReproj`（camPrevVP / s_prevVP）出自 `rebuildViewProj`，**把 eye 折进去**；
`curForReproj` 是引擎自己的 ViewProj，**同文件 1029–1032 行的注释就写着它
"carries NO translation"**。对任意可逆 P：

```
inv(P @ [R|0]) @ (P @ [R|-R@eye]) = [R^T|0] @ [R|-R@eye] = [ I | -eye ]
```

**旋转精确等于单位阵，平移是整个相机位置。**
⇒ `det3()` 只读 3×3 ⇒ 报 `1.000000` ⇒ v0.92 的 guard 永不触发
⇒ `camCurOk` 逐帧翻转 ⇒ 重建路径给错误矩阵、fallback 给 identity ⇒ **(a) 的交替**

### 13.4 v1.07c 交付

1. 取逆改用与 `prev` 同构的源：
   `const sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;`
2. 新仪表 `diag.clipW = clipToPrevClip[3].w` + 偏离 1 时告警
   （**唯一不随帧时间增长的相机侧判据**）
3. 横幅 `v1.07b` → `v1.07c`

| 项 | 值 |
|---|---|
| DLL | 1,326,592 B / md5 `c58c87209c4939fa9d342f1b65da8015` |
| 构建 == 部署 | `cmp` IDENTICAL |
| 提交 / tag | `27a8cb1` / `v1.07c` |
| 备份 | `src/backup-v1.07c-final-20260918-232126/` |
| 回归 | `tools/regress_v107c_reprojsrc.py` → **OK** |

回归要点：C0 用 200 组随机 R/P/eye 证明恒等式（残差 `2.9e-11`）；
C1 用真实 eye，OLD 平移 `495.593`（= `|eye|`）而 det3 仍是 `1.000000`，
NEW 精确 identity（`5.6e-14`）；C2 相机移 15.3 单位时 NEW `clipDev=15.241779`，
**证明修复没有把真实运动拍平**。

### 13.5 clipW 的局限（诚实记下来）

干净模型下坏矩阵的 w **也是 1**，所以 clipW 抓的是**实测形态**
（引擎投影不干净，`[FLD]` 里 `ProjU [3][3]=0.0666667` 导致 w 被污染成 `-195.22`），
不是所有形态。覆盖所有形态、且不需要新字段的判据是：
**相机静止时 `clipDev` 必须 ≈ 0。**

### 13.6 未解释 / 未验证

- **性能单调恶化未解释**：Transfusion FPS `39.7 → 25.4 → 17.3 → 13.4`，
  1% Low `30.5 → 1.1`，jitter `37 → 190ms`，真实帧 `571ms`。
  可能是本缺陷的后果（每帧喂给 DLSS-G 非仿射重投影），也可能独立。下次运行判定。
- **两个线程 present 同一 swap chain**（tid=45300 / 43404）—— 未调查。
- `blocked=574 unblocked=1` 是 stall governor 对 300–1000ms 慢帧的**反应**，不是原因。
- **画面是否真的不再来回：未知（我无法运行游戏）。**

### 13.7 下次验收（一条命令，三条判据）

```
"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe" tools/analyze_session.py
```

1. 横幅 `v1.07c` —— 不符 ⇒ DLL 没换上去，后面都不作数
2. `clipW` == `1.000000`
3. **站着不动**时 `clipDev` ≈ 0

★ 新判据已进工具：`clipDev` 在一个会话内同时落在 ≤1e-4 和 >10 两侧 ⇒ PROBLEM。
用 23:10 那份 v1.07b 日志回放，工具**自动报出**了这条，无需我提示。

### 13.8 两个 harness bug（记下来）

1. **`norm()` 二次展开**：后置检查的 needle 里写了 `\\r\\n`，而 `norm()` 又把 `\\n`
   展开成 `\\r\\n` ⇒ 变成 `\\r\\r\\n`，永远匹配不到。**needle 一律写 `\\n`。**
2. **fmt 编译期校验（C7595）**：`clipW={:.6f}` 在格式串**前半**，而 `diag.clipW,`
   被我插在参数列表**后半**（`diag.clipDevMax,` 之后）⇒ 编译失败。
   **参数顺序必须镜像格式串说明符顺序。** 处置：`git checkout --` 回滚两文件后重打
   （回滚后核对 md5 与基线一致：`Streamline.cpp` = `0687096e728518f98d2526363e69d1a6`）。

### 13.9 一条判据设计原则（新）

**能作判据的量，必须在"坏"和"好"之间单调、单一含义。**
`clipDev` 不满足（同时受相机速度与帧时间影响，大既可能是修好也可能是缺陷）；
`clipW` 满足但只在特定形态上；「静止时 `clipDev ≈ 0`」满足且不需新字段。
**下次找判据先问这一句。**
"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    crlf = raw.count(b"\r\n")
    text = raw.decode("utf-8")
    print(f"{TARGET.split('/')[-1]}  {len(raw)} B  lines={text.count(chr(10))}  "
          f"CRLF={crlf}")
    if crlf > 0:
        print("  !! expected a pure LF file; refusing")
        return 1

    print(f"marker present: {MARKER in text}   (must be False or it ran)")
    if MARKER in text:
        print("REFUSED, nothing written: section 13 already present")
        return 1

    checks_ok = "## 12. " in text
    print(f"section 12 present: {checks_ok}   (must be True)")
    if not checks_ok:
        print("REFUSED, nothing written")
        return 1

    out = text
    if not out.endswith("\n"):
        out += "\n"
    out += SECTION

    checks = [
        ("section 13 present", "## 13. v1.07c" in out),
        ("only one section 13", out.count("## 13. v1.07c") == 1),
        ("section 12 kept", "## 12. " in out),
        ("section 11 kept", "## 11.1 " in out),
        ("ends with the design rule",
         out.rstrip().endswith("**下次找判据先问这一句。**")),
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

    print(f"\nlines {text.count(chr(10))} -> {out.count(chr(10))}")
    print(f"bytes {len(raw)} -> {len(out.encode('utf-8'))}")

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
