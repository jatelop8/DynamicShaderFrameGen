#!/usr/bin/env python3
"""Append section 40 to the framegen-diagnosis skill (pure LF file).

Dry run by default; --apply writes. Marker guard prevents a double append.
"""
import io
import sys

TARGET = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
MARKER = "## 40. ★★★★★ v1.07c"

SECTION = """
## 40. ★★★★★ v1.07c：重投影矩阵的逆取自一台**没有平移**的相机 —— 「来回循环」的机制 ★2026-09-18 实锤

### 40.1 用户的观察把案子翻过来了

> "这次只有4帧，我发现画面是来回循环得，由于帧数低了，所以看的比较清楚，帧数高就觉得这个循环比较快，看着像卡了"

**"来回循环"和"静止不动"是两种不同的故障。** 我前面几轮都在按"静止"（`clipToPrev == I`）
解释冻结 —— 那条路解释不了"来回"。而"帧率越高越像卡住、越低越看清是循环"这一句，
**只有一个机制能同时满足：画面在以很少几帧为周期循环，且循环频率随帧率上升。**

★ **从用户的现象描述反推机制**，是这一轮唯一有效的动作。用户的定性观察（"来回"、
"两帧反复"、"火焰和人在动"）比任何单一日志字段更早指出方向。

### 40.2 症状的日志指纹：判据在 identity 和荒谬之间**交替**

23:10 运行（v1.07b）同一个会话里的相邻心跳：

```
23:10:50.746 clipDev=0.000023     identity
23:10:51.414 clipDev=0.000023     identity
23:10:51.982 clipDev=0.348060     正常量级
23:10:52.440 clipDev=28.772085    荒谬
23:10:52.905 clipDev=4.549722     荒谬
23:10:53.383 clipDev=18.569712    荒谬
min=0.000061 max=243.962387
```

**⇒ 这不是一台在动的相机（那会单调），这是两个不同的矩阵在交替。**

★★★ **`clipDev` 单独一个数不能作判据。** 它同时受相机速度和帧时间影响，
"大"既可能是修复成功（真有平移）也可能是缺陷（假平移）。
**能作判据的量必须在"坏/好"之间单调、单一含义。**
本项目历史上我据此误判过一次（把 `max=243.96` 读成"相机链是好的"）。

### 40.3 缺陷：`inv(cur)` 与 `prev` 不是同一台相机

```cpp
// src/Streamline.cpp（v1.07b 行号 1073）
sl::matrixFullInvert(invCurrViewProj, curForReproj);               // 无平移
sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);   // 含平移
```

- `prevForReproj` = `camPrevVP` / `s_prevVP`，都出自 `rebuildViewProj`，**把 eye 折进去**
- `curForReproj` = 引擎自己的 ViewProj，**同文件 1029–1032 行的注释就写着它
  "carries NO translation"**

对任意可逆 `P`：

```
inv(P @ [R|0]) @ (P @ [R|-R@eye])
  = inv([R|0]) @ inv(P) @ P @ [R|-R@eye]
  = [R^T|0] @ [R|-R@eye]
  = [ I | -eye ]
```

**旋转精确等于单位阵，平移是整个相机位置。**

**为什么它躲过了所有 guard：** `det3()` 只读 3×3，而该乘积的 3×3 =
`Proj3 @ Rcur^T @ Rprev @ Proj3^-1` —— **只是旋转的函数**。
⇒ 报 `1.000000` ⇒ v0.92 的 `det in [0.5,2.0]` 永不触发。

**为什么同一个会话里会交替：** `camCurOk` 逐帧翻转。
走重建路径的帧给出错误矩阵，走 fallback 的帧给出 identity ⇒ §40.2 的交替。

### 40.4 实测证据 —— 用 Transfusion 的 `[MOTION]` dump 证明"我们实际发了什么"

```
frame 578, 23:10:35.543
[MOTION] route=slSetConstants call=0 ... clipToPrev=non-identity reset=1 cameraIncluded=1
[MOTION] clipToPrev rows=[0.999993265 4.5692791e-06 -0.00143783959 -0.00143777835]
                         [2.57021884e-06 2.25002486e-06 0.999290824 -0.000707997533]
                         [-0.00171347801 -0.0015000155 0.473518044 0.471998006]
                         [-243.962387 2.7390945 -77.6724777 -195.222366]
         cameraPos=(-243.049301,-415.311523,118.558205)
```

对照 identity 时的样子（call=1）：`row3 = [0 5.78e-06 -6.10e-05 0.99999994]`

**⇒ 行主序、平移在最后一行、合法仿射阵的 `[3][3] == 1`。**
**⇒ 这一帧 `row3[3] = -195.222366`：连仿射都不是。**

★ **诊断优先级：`DLSSG-Transfusion.log` 的 `[MOTION]` 是唯一能证明"我们实际发了什么"的
探针。** 本插件自己的心跳只能说"我以为我发了什么" —— 两者不一致时，
以 Transfusion 侧为准（它在 `slSetConstants` 的入口打印，就在数据进入运行库之前）。

### 40.5 修法（单点）

```cpp
const sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;
sl::matrixFullInvert(invCurrViewProj, reprojInvSrc);
```

`camCurOk` 为假时 `prev` 也只能是 `curForReproj`（同帧或上一帧），**仍然同构** ✓

### 40.6 离线证明（纯 Python，无依赖）

`tools/regress_v107c_reprojsrc.py`：

```
C0  200 组随机 R/P/eye：max |OLD - [I|-R@eye]| = 2.910e-11
    max |det3(OLD) - 1| = 3.425e-12         <- 3x3 始终正交
C1  真实 eye、静止相机
    OLD  clipDev=403.398109  平移=495.5933  w=1.000000  det3=1.000000  != identity
    NEW  clipDev=5.551e-14   平移=7.695e-14 w=1.000000  == identity
C2  相机移 15.3 单位 => NEW clipDev=15.241779  <- 修复没有把真实运动拍平
C3  OLD det3=1.000000 => 旧 guard 判 PASS（假阴性，by construction）
C4  clipW 的局限（见 40.7）
RESULT: OK
```

★★ **"反向用例"必须有**：证明修复不是把矩阵变成常量。
只证明"坏的情况变好了"不够，还要证明"好的情况没被弄坏"。

### 40.7 新仪表 `clipW` 与它的**局限**（诚实写下来）

`diag.clipW = clipToPrevClip[3].w`，合法仿射阵必须 == 1。
它是这里**唯一不随帧时间增长的**相机侧判据。

**局限：** 干净模型下坏矩阵的 w **也是 1**（因为 `[I | -eye]` 的 `[3][3]` 就是 1）。
实测之所以是 `-195.22`，是因为引擎的投影不干净 ——
`[FLD]` dump 里 `ProjU` 的 `[3][3]` 是 `0.0666667` 而非 0，`inv(P) @ P` 不精确抵消。
**⇒ `clipW` 抓的是实测形态，不是所有形态。**

**覆盖所有形态、且不需要新字段的判据：相机静止时 `clipDev` 必须 ≈ 0。**

### 40.8 验收（下次开游戏一条命令）

```
"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe" tools/analyze_session.py
```

| # | 判据 | 合格 |
|---|---|---|
| 1 | 横幅（`EXPECTED_BUILD` 硬比对） | `v1.07c` |
| 2 | `clipW` | `1.000000` |
| 3 | **站着不动**时的 `clipDev` | ≈ 0 |

工具已加两条自动检查：
- `clipW` 偏离 1 ⇒ PROBLEM
- **`clipDev` 在一个会话内同时落在 ≤1e-4 和 >10 两侧 ⇒ PROBLEM**（"交替"指纹）
  ★ 用 23:10 那份 v1.07b 日志回放，工具**自动报出**了这条，无需人工提示。

### 40.9 本轮**没有**解释的（别把它们算进这次修复）

| 现象 | 数据 | 状态 |
|---|---|---|
| 性能单调恶化 | Transfusion FPS `39.7 → 25.4 → 17.3 → 13.4`，1% Low `30.5 → 1.1`，jitter `37 → 190ms`，真实帧 `571ms` | **未解释**。可能是本缺陷的后果（每帧喂给 DLSS-G 非仿射重投影 ⇒ 遮挡/去遮挡判断失效），也可能独立 |
| 两个线程 present 同一 swap chain | `[PRESENT] census: NEW presenter tid=43404` | 未调查 |
| `blocked=574 unblocked=1` | stall governor 对 300–1000ms 慢帧的反应 | 是**结果**不是原因 |
| 族锁仍 `proj00=0.8391` | release 触发 3 次 | 已证**不是**画面静止的原因（`pub=4631`，通道一直通） |
| `[FLD]`：`ProjU [3][3]=0.0666667`、`PrevVPU` 全零 | 23:10:03.584 | 记下，未处理 |

### 40.10 本轮两个 harness bug（通用，跨项目）

1. **`norm()` 二次展开**：后置检查的 needle 里写 `\\r\\n`，`norm()` 又把 `\\n` 展开成 `\\r\\n`
   ⇒ 变 `\\r\\r\\n`，永不匹配。**needle 一律写 `\\n`，让 norm 去展开。**
2. **fmt 在编译期校验格式串与参数序列**：把新参数插在参数列表里与说明符**不对应**的位置
   ⇒ `error C7595 "call to immediate function is not a constant expression"`。
   **加格式说明符时，参数必须插在镜像位置。**
   处置：`git checkout --` 回滚 → 核对 md5 与基线一致 → 重打补丁。

### 40.11 可复用的判据设计原则（本节最重要的一条）

> **能作判据的量，必须在"坏"和"好"之间单调、单一含义。**

- `clipDev` **不满足**：同时受相机速度与帧时间影响
- `clipW` **部分满足**：只在特定形态上
- 「静止时 `clipDev ≈ 0`」**满足**：不需要新字段

配套两条：
- **改状态机的输出计数是它最便宜的反证**（发布计数通着，就不能说它堵住了下游）
- **一个探针只能在其前提成立时读**（`move=0.0000` 的诊断价值取决于"玩家在不在走"，
  而那个前提必须**从日志里读出来**，不能假设 —— 本项目为此误判过整节结论）
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
        print("REFUSED, nothing written: section 40 already present")
        return 1

    ok = "## 39." in text
    print(f"section 39 present: {ok}   (must be True)")
    if not ok:
        print("REFUSED, nothing written")
        return 1

    out = text
    if not out.endswith("\n"):
        out += "\n"
    out += SECTION

    checks = [
        ("section 40 present", "## 40. " in out),
        ("only one section 40", out.count("## 40. ") == 1),
        ("section 39 kept", "## 39. " in out),
        ("section 38 kept", "## 第 38 节" in out),
        ("ends with the probe-precondition note",
         out.rstrip().endswith("本项目为此误判过整节结论）")),
    ]
    print()
    bad = 0
    for label, ok2 in checks:
        print(f"  {'OK  ' if ok2 else 'FAIL'} {label}")
        if not ok2:
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
