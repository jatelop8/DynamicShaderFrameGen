#!/usr/bin/env python3
"""Append chapter 16 to MFG_MASTER_NOTES.md (pure LF file).

Dry run by default; --apply writes. Anchor must occur exactly once, and a
marker guard keeps a re-run from appending twice (an insert-type patch does
not consume its anchor).
"""
import io
import sys

TARGET = "MFG_MASTER_NOTES.md"
MARKER = "## 第 16 章"

ANCHOR = (
    "---\n"
    "---\n"
    "\n"
    "**本文件维护规则**"
)

CHAPTER = """## 第 16 章：v1.07c —— 重投影矩阵的逆取自一台**没有平移**的相机（2026-09-18 23:22）

### 16.1 用户这一句把案子翻过来了

> **"这次只有4帧，我发现画面是来回循环得，由于帧数低了，所以看的比较清楚，帧数高就觉得这个循环比较快，看着像卡了"**

"来回循环"和"静止不动"是两种不同的机械故障。第 15 章我按"静止"（clipToPrev == I）解释冻结，
那条路解释不了"来回"。而"帧率越高越像卡住、帧率越低越看清是循环"这一句，
只有一个机制能同时满足：**画面在以很少几帧为周期循环，且循环频率随帧率上升。**

### 16.2 23:10 那次运行（v1.07b）的日志，三条硬数据

第一次拿到 v1.07b 的完整实测（23:10:03–23:10:53，50 秒，23:10:34 进世界）。

**(a) 相机链是"好坏交替"，既不是"静止"也不是"完好"**

同一个会话里相邻心跳的 `clipDev`：

| 时间 | clipDev | 读法 |
|---|---|---|
| 23:10:50.746 | 0.000023 | identity |
| 23:10:51.414 | 0.000023 | identity |
| 23:10:51.982 | 0.348060 | 正常量级 |
| 23:10:52.440 | **28.772085** | 荒谬 |
| 23:10:52.905 | 4.549722 | 荒谬 |
| 23:10:53.383 | **18.569712** | 荒谬 |

全局 `min=0.000061 max=243.962387`。**同一个会话里 identity 与"几百单位"交替出现。**
这不是一台在动的相机（那会单调），这是**两个不同的矩阵在交替**。

★★ 第 15 章说"相机链是好的（判据 A）"，依据是 `clipDev max=243.96 明显 > 0`。
**那条判据本身是错的**：clipDev 会随帧时间和相机速度增长，"大"不证明健康。
正确读法是**看它是否交替**。

**(b) Transfusion 把我们发出去的矩阵原样打了出来**

`DLSSG-Transfusion.log`，frame 578，23:10:35.543：

```
[MOTION] route=slSetConstants call=0 ... clipToPrev=non-identity prevToClip=non-identity
         projection=non-identity reset=1 cameraIncluded=1
[MOTION] clipToPrev rows=[0.999993265 4.5692791e-06 -0.00143783959 -0.00143777835]
                         [2.57021884e-06 2.25002486e-06 0.999290824 -0.000707997533]
                         [-0.00171347801 -0.0015000155 0.473518044 0.471998006]
                         [-243.962387 2.7390945 -77.6724777 -195.222366]
         cameraPos=(-243.049301,-415.311523,118.558205)
```

对照同一探针在 identity 时的样子（call=1）：

```
[MOTION] clipToPrev rows=[0.99999994 ... 0][... 1 0 0][... 0.99999994 0]
                         [0 5.78165054e-06 -6.10351562e-05 0.99999994]
```

**⇒ 打印是行主序，平移在最后一行，合法仿射阵的 `[3][3]` == 1。**
**⇒ 而 call=0 的 `row3[3] = -195.222366`。这个矩阵连仿射都不是。**

**(c) `[CAM] acc` 的 pos 在匀速前进，`cameraPos` 却在窗口内恒定**

时间窗重叠处（23:10:35–39）两者一致 `(-243.05,-415.31,118.56)`，
**所以不是"两个缓冲"的问题**。15.2 的"被发布的相机原地不动"只在那 4 秒成立；
之后 `pos` 一路走到 `(-189.28,18.88,149.47)`。

★★ `move=0.0000` 恒定的原因是**仪表坏了**，不是相机不动：`snapAcceptDist` 恒 0，
而 `pos`/`path` 是好的 —— `path` 的增量精确等于 `pos` 的差
（132.15→149.69 对应 `|(-15.25, 6.59, 5.65)| = 17.55`）。**15.2 完全建立在坏仪表上。**

### 16.3 缺陷：`inv(cur)` 与 `prev` 不是同一台相机

`src/Streamline.cpp`（v1.07b 行号 1073）：

```cpp
sl::matrixFullInvert(invCurrViewProj, curForReproj);
sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);
```

- `prevForReproj` = `camPrevVP` 或 `s_prevVP`，两者都出自 `rebuildViewProj`，
  **把 eye 折进去了**：`V_prev = [R | -R@eye]`
- `curForReproj` = 引擎自己的 ViewProj。**同一文件 1029–1032 行的注释就写着它
  "carries NO translation"**（引擎构造的 `Proj @ [R|0]` 把平移项丢了）

对任意可逆投影 `P`：

```
inv(P @ [R|0]) @ (P @ [R|-R@eye])
  = inv([R|0]) @ inv(P) @ P @ [R|-R@eye]
  = [R^T|0] @ [R|-R@eye]
  = [R^T R | -R^T R @ eye]
  = [ I | -eye ]
```

**旋转精确等于单位阵，平移是整个相机位置。**

⇒ `det3()` 只读 3×3 ⇒ 报 `1.000000` ⇒ v0.92 的 guard 永不触发。
⇒ `camCurOk` 逐帧翻转 ⇒ 走重建路径的帧给出错误矩阵、走 fallback 的帧给出 identity
⇒ **这就是 (a) 那个"identity ↔ 荒谬"的交替。**

**★ 为什么实测 `row3` 是 `(-243.96, 2.74, -77.67, -195.22)`，而模型给 `[I | -eye]`（平移 495.59）？**
因为引擎的投影不干净：`[FLD]` dump 里 `ProjU` 的 `[3][3]` 是 `0.0666667` 而非 0，
`inv(P) @ P` 因此不精确抵消，w 被污染成 `-195.22`。**两者是同一缺陷的两种形态。**

### 16.4 v1.07c 的改动（3 处）

1. **取逆的源与 `prev` 同构**（唯一的功能修复）：
   ```cpp
   const sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;
   sl::matrixFullInvert(invCurrViewProj, reprojInvSrc);
   ```
   `camCurOk` 为假时 `prev` 也只能是 `curForReproj`（同帧或上一帧），仍然同构。
2. **新仪表 `diag.clipW = clipToPrevClip[3].w`** + 偏离 1 时告警。
   它是这里**唯一不随帧时间增长的**相机侧判据。
3. 横幅 `v1.07b` → **`v1.07c`**

### 16.5 离线证明（`tools/regress_v107c_reprojsrc.py`，纯 Python 无依赖）

```
C0  200 组随机 R / P / eye：max |OLD - [I | -R@eye]| = 2.910e-11
    max |det3(OLD) - 1| = 3.425e-12   ← 3x3 始终正交，det3 结构性看不见
C1  真实 eye，静止相机
    OLD  clipDev=403.398109  平移=495.5933  w=1.000000  det3=1.000000   != identity
    NEW  clipDev=5.551e-14   平移=7.695e-14 w=1.000000  == identity
C2  移动 15.3 单位
    NEW  clipDev=15.241779   ← 运动保留，修复没有把矩阵拍成常量
C3  OLD det3=1.000000，guard 判 PASS ← 假阴性，by construction
C4  clipW 的**局限**（诚实写下来）：干净模型下坏矩阵的 w 也是 1，
    所以 clipW 抓的是**实测形态**，不是所有形态。覆盖所有形态的判据是
    「相机静止时 clipDev 必须 ≈ 0」，不需要新字段。
RESULT: OK
```

### 16.6 这一轮**没有**解释的东西（不假装）

| 现象 | 数据 | 状态 |
|---|---|---|
| 性能单调恶化 | Transfusion FPS 39.7 → 25.4 → 17.3 → 13.4；1% Low 30.5 → **1.1**；jitter 37 → 190ms；真实帧 571ms | **未解释**。可能是本缺陷的后果（每帧喂给 DLSS-G 一个非仿射重投影矩阵，遮挡/去遮挡判断失效），也可能是独立缺陷。下次运行判定 |
| 两个线程 present 同一 swap chain | `[PRESENT] census: NEW presenter tid=43404 - now 2 distinct threads` | **未调查** |
| `blocked=574 unblocked=1` | stall governor 在帧超 150ms 预算时停 MFG probe 24 帧，而帧是 300–1000ms | 是慢帧的**结果**，不是原因 |
| 族锁仍停在 `proj00=0.8391` | release 触发 3 次 | v1.07b 已记录；**已证明它不是画面静止的原因**（`pub=4631`，发布通道一直是通的） |
| `[FLD]`：`ProjU [3][3]=0.0666667`、`PrevVPU` 全零 | 23:10:03.584 | 记下，未处理 |

### 16.7 下次运行的验收判据（三条，一条命令）

```
"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe" tools/analyze_session.py
```

| # | 判据 | 合格 | 不合格意味着 |
|---|---|---|---|
| 1 | 横幅 | `v1.07c`（`EXPECTED_BUILD` 已改为硬比对） | DLL 没换上去，后面都不作数 |
| 2 | `clipW` | `1.000000` | 逆与 `prev` 仍不同构 |
| 3 | **站立不动**时的 `clipDev` | ≈ 0 | 仍有假运动 |

★ 第 3 条必须**站着不动**测：那是不依赖任何新字段、且不受帧时间影响的唯一绝对判据。

### 16.8 第 15 章 A/B/C 三条判据的结论

第 15 章留了一个实验（进游戏走 10 秒）。**这次的数据已经回答了它，答案是 A 的加强版：**

- `clipDev` 能到 28.77 / 243.96，`camPrev used=21/22` ⇒ **相机链在动** ⇒ 不是 B（捕获层不跟玩家）
- 但 `clipToPrevClip` 的**形状**是坏的 ⇒ 不是"重建成常量"，是**重建的两端不同构**

所以 15.5 那张表作废，判据改用本章 16.7 的三条。

### 16.9 提交与验证

| 项 | 值 |
|---|---|
| 提交 | `27a8cb1` |
| tag | `v1.07c` |
| DLL | 1,326,592 B / md5 `c58c87209c4939fa9d342f1b65da8015` |
| 构建 == 部署 | `cmp` IDENTICAL |
| DLL 字符串 | `diag active v1.07c`=1，`v1.07b`=0，`clipToPrevClip[3].w=`=1，`clipW={:.6f}`=1，`lock RELEASED on the reset edge`=1 |
| 回归 | `tools/regress_v107c_reprojsrc.py` → **OK** |
| 源码行尾 | `Streamline.cpp` 2298 CRLF / bare_LF 0；`Streamline.h` 389 CRLF / bare_LF 0 |
| 备份 | `src/backup-v1.07c-final-20260918-232126/`（含 MANIFEST.txt） |

**仍未验证：我无法运行游戏。画面是否真的不再来回，只有下次运行知道。**

### 16.10 本轮踩到的两个 harness bug（记下来）

1. **`norm()` 二次展开**：后置检查的 needle 里写了 `\\r\\n`，而 `norm()` 又把 `\\n` 展开成
   `\\r\\n` ⇒ 变成 `\\r\\r\\n`，永远匹配不到。**教训：needle 一律写 `\\n`。**
   断言本身是对的 —— 它抓的是我自己的检查代码，不是产品代码。
2. **fmt 的编译期格式串校验（C7595）**：`clipW={:.6f}` 在格式串**前半**，
   而我把 `diag.clipW,` 插在参数列表**后半**（`diag.clipDevMax,` 之后）⇒
   fmt 常量表达式检查失败。**参数顺序必须镜像说明符顺序。**
   处置：`git checkout --` 回滚两文件（核对 md5 与基线一致）后重打。

### 16.11 一条可复用的判据设计原则

**能作判据的量，必须在"坏"和"好"之间有单调、单一含义。**
`clipDev` 不满足：它同时受相机速度和帧时间影响，"大"既可能是修复成功也可能是缺陷。
`clipW` 满足（必须是 1），但只在特定形态上成立。
「静止时 `clipDev ≈ 0`」满足且不依赖新字段 —— **下次找判据时先问这一句。**

---

"""


def main(apply_changes):
    raw = io.open(TARGET, "rb").read()
    crlf = raw.count(b"\r\n")
    bare_lf = raw.count(b"\n") - crlf
    text = raw.decode("utf-8")
    print(f"{TARGET}  {len(raw)} B  lines={text.count(chr(10))}  "
          f"CRLF={crlf} bare_LF={bare_lf}")
    if crlf > 0:
        print("  !! this file is meant to be pure LF; refusing")
        return 1

    print(f"marker present: {MARKER in text}   (must be False or the patch ran)")
    if MARKER in text:
        print("REFUSED, nothing written: chapter 16 already present")
        return 1

    n = text.count(ANCHOR)
    print(f"anchor count: {n}   (must be exactly 1)")
    if n != 1:
        print("REFUSED, nothing written")
        return 1

    out = text.replace(ANCHOR, CHAPTER + ANCHOR, 1)

    checks = [
        ("chapter 16 present", "## 第 16 章" in out),
        ("chapter 15 kept", "## 第 15 章" in out),
        ("chapter 14 kept", "## 第 14 章" in out),
        ("chapter 12 kept", "## 第 12 章" in out),
        ("the maintenance rule is still last",
         out.rstrip().endswith("**不覆盖历史章节**，只在第 9 章与末尾追加。")),
        ("only one chapter 16", out.count("## 第 16 章") == 1),
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
    print(f"\nWROTE {TARGET}  {len(r)} B  CRLF={c} bare_LF={r.count(chr(10).encode()) - c}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
