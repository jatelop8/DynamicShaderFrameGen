#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Append chapter 18 (v1.08 probe build) to MFG_MASTER_NOTES.md.

Dry run by default; --apply writes. Anchor must occur exactly once.
The ledger is pure LF (93931 B, CRLF=0 as measured 2026-09-19 00:2x), so the
inserted text is LF too.
"""
import io
import sys

LEDGER = "MFG_MASTER_NOTES.md"
ANCHOR = "\n---\n\n---\n---\n\n**本文件维护规则**"
MARKER = "## 第 18 章"

CH18 = """
---

## 第 18 章　v1.08 探针构建：把「-195.22 是什么」变成一次可判定的测量

**日期**：2026-09-19 00:04–00:30
**前提**：第 17 章已证明 v1.07c 的功能改动在实跑路径（`src=fixed`）上是**空操作**。
**决定**：用户选 **(b)** —— 跳过那次实际只是在复测 v1.07b 的验收运行，先补上缺失的诊断再跑。

### 18.1 要判什么

`clipToPrevClip[3].w = -195.222366`（23:10 Transfusion dump，frame 578）**仍无解释**。
16.4 已排除「族混用」的**简单标量形式**：两侧共用 P ⇒ 恰为 1；另一侧乘 k ⇒ 精确等于 k。
已知族比 **5.62x** ⇒ 应得 `5.62` 或 `0.178`，**不是 -195.22**。

剩下两个候选，互斥：

| 候选 | 机制 | 签名 |
|---|---|---|
| **(a)** 两侧投影不同 | `inv(Pc@Vc) @ (Pp@Vp)` 不是仿射，`[3].w` 可以取任意有限值 | 两侧**投影**不同 |
| **(b)** 投影相同、逆近奇异 | `matrixFullInvert` 收到 det≈0.001 的矩阵，元素放大千倍 | 两侧投影**相同**，而 `mag(inv)` 巨大 |

**这两个候选只在一个数上分歧：两侧投影是否相同。** 所以本轮只加这一个读数，不加第二个猜测。

### 18.2 读什么，为什么不读 ViewProj

插桩读的是**投影矩阵**的 `[0][0]`，不是 ViewProj 的：

```
(P@V)[0][0] = P[0][0] * V[0][0]          ← V[0][0] 是旋转元素，随相机朝向变
```

用 ViewProj 的 `[0][0]` 当族指纹 ⇒ 玩家每转一次视角它都变 ⇒
**这是「拿恒变量当判据」的镜像错误：拿一个恒变的量当族指纹。**

投影矩阵的 `[0][0]` 只随投影族变（`0.149184` 世界 / `0.8391` 菜单），**与朝向无关**。

另外取 `[2][3]` 作**透视/正交判别**：正交投影恒为 0，透视非 0。
它与 `[0][0]` **互相独立** —— 一个用正交投影的 3D 菜单相机，会在**两个数上同时**暴露。

### 18.3 避开的陷阱：`s_prevCamProj` 在本帧就被覆盖

`Streamline.cpp`：

```
 748   if (camCurOk) {
 750       s_prevCamProj = a_fb.CameraProj;        ← 本帧值，在这里就被写掉
 ...
1202   diag.clipW = c.clipToPrevClip[3].w;        ← 在这里读 s_prevCamProj 拿到的是「本帧」
```

⇒ 若直接在 1202 处读 `s_prevCamProj` 当「上一帧投影」，比较的两边**都是本帧** ⇒ 恒等 ⇒ **判据永不分歧**。
这与 **v1.02c 的「用僵死常量当门」是同一个错法的镜像**：那次是「永不变化」，这次是「读的时候已经被换成本帧」。
**门控铁律要加一条：除了证明它会变，还要证明它是你读它的那一刻所代表的那一帧。**

修法：在 750 **之前**快照（`s_probePrevProj`，757 行），并机器断言 `757 < 761`。
`tools/patch_v108_probe.py` 的 post-condition 里就是这么写的：

```
("C++: snapshot taken before overwrite",
 cpp.index("s_probePrevProj = s_prevCamProj;") < cpp.index("s_prevCamProj = a_fb.CameraProj;"))
```

### 18.4 机器判定：插桩是纯增量

`tools/verify_v108_probe_inert.py`，**退出码 0**：

| 检查 | 结果 |
|---|---|
| **A** 反向应用补丁后与备份逐字节比对 | **完全相同**（`Streamline.cpp` 120866 B、`Streamline.h` 20686 B） |
| **B** 新增 47 + 20 = 67 行逐条分类 | 注释 35 / 日志 12 / 声明 9 / `diag.probe*` 写入 6 / 括号 2 / 快照 1 / 空 2 —— **无一条落在 `c.*`、`cam*`、`prev*` 上** |

**A 段是最强形式**：把补丁撤掉必须还原成一模一样的 v1.07c 字节。
这同时是 18.3 那个「读错帧」风险的反证 —— 如果插桩动过任何功能语句，A 段不可能逐字节相同。

（B 段第一次跑是 FAIL，但那是**脚本自己的 bug**：文本模式下 universal newlines 把 `\\r\\n` 换成 `\\n`，
`split("\\r\\n")` 返回**单元素列表**，整个审计变成空操作却照样报结论。
已改为二进制读取，并加了一条「拆分后行数必须 > 100」的守卫 ——
**这正是「审计器自身必须先自证在工作」的第 N 次实例。**）

### 18.5 顺带抓出的真 bug：分析脚本会吞掉整行心跳

为了喂合成样本，给 `analyze_session.py` 加了 `--log/--watchdog` 覆盖参数，于是发现：

```python
hb = re.findall(r"\\[XRAY\\].*?clipDev=([\\d.]+).*?cam\\(ok/inv\\)=(\\d+)/(\\d+)")     # 旧
```

`([\\d.]+)` **不含负号**。而 `clipDev` 一旦为负（这个案子里 `-195.22` 这种值出现过），
**整行心跳匹配失败** ⇒ 第 4 节直接打印 `NO DATA` ⇒
**一个「异常读数」被静默翻译成「没有数据」。**

```python
hb = re.findall(r"\\[XRAY\\].*?clipDev=([-\\d.]+).*?cam\\(ok/inv\\)=(\\d+)/(\\d+)")    # 新
```

同时修正分箱：`lo = [v for v in cd if 0.0 <= v <= 1.0e-4]` ——
否则一个 `-195` 会被算进「identity 样本」，**凭空造出一次「交替」**（假阳性）。
并新增：`clipDev` 为负就直接报「**指标本身坏了**」，而不是当成一个小值咽下去。

★ 这是**第三次**同一类错误：**读数异常被静默降级成「无数据 / 正常」。**
前两次分别是 `move=0.0000`（16.2c）与 `jitter=(0,0)`（16.12）。
**推论**：任何解析器都必须对「无法解析的输入」显式尖叫，而不是返回空集 ——
**空集在判读层看起来和「健康」一模一样。**

### 18.6 判据必须先在离线样本上分歧

`tools/regress_v108_p00.py` 走 `--log` 喂**合成日志**，用的是**同一套判读代码**（不是复制实现）：

| 样本 | 内容 | 期望 | 结果 |
|---|---|---|---|
| **A** | 两侧投影 0.8391 / 0.1492，clipW=5.62 | 报 (a) + 打印比值 | OK |
| **B** | 两侧投影相同、`mag(invSrc)=4.2e+05` | 报 (b) + 打印量级 | OK |
| **C** | 健康：clipW=1、单族 | 三处 OK、无投诉 | OK |
| **D** | `p00` 在 0.1492 / 0.8391 间交替 | 报族切换并计入 problems | OK |
| **E** | 无 `p00` 字段（v1.07 老日志） | `NO DATA`，**绝不当作通过** | OK |

**CASE B 第一次是 FAIL —— 正是它把 18.5 那个负号 bug 逼出来的。**
一个回归脚本不只是「验证新判据」，它同时是**判读代码的对抗测试**：
你给它一个必须报 (b) 的输入，它反而证明了自己读不到任何东西。

### 18.7 一次跑，五条判据

进游戏 → 等 4x 起来 → **站着不动 5 秒** → 走 5 秒并转视角 → 退出 → `python tools/analyze_session.py`

| # | 判据 | 通过条件 | 说明 |
|---|---|---|---|
| 1 | 横幅 | `diag active v1.08 (probe build …)` | 证明加载的是本次构建 |
| 2 | `clipW` | `1.000000` | 绝对判据，不随帧时间变 |
| 3 | 静止时 `clipDev` | `< 1e-3` | 运动中必须明显 > 0；恒 0 = 相机项被丢 |
| 4 | `p00(c/p)` | 世界内为**单族**（≈0.1492），且两侧一致 | 出双族 = 菜单相机仍在夺流 |
| 5 | `[MOTION]` 若出现 | 看它自带的 `p00 cur/prev` 与 `mag invSrc` | **直接读出是 (a) 还是 (b)** |

**判据 5 是本轮的全部意义**：它把「-195.22 到底是什么」从「下一轮再猜」变成「看一眼就知道」。
验证前仍须在 MO2 取消勾选 `Modex.dll`（第三方闪退，会掩盖一切结论）。

### 18.8 本轮产出

- 源码：`Streamline.cpp` 120866 → **123094 B**，`Streamline.h` 20686 → **21676 B**（**纯增量**）
- 新增回归：`tools/verify_v108_probe_inert.py`、`tools/regress_v108_p00.py`
- 判读升级：`tools/analyze_session.py` 新增 4c、修负号 bug、加 `--log` 覆盖
- DLL：`0a10b4b636257d0a589fb5eec4d3b613`，1,329,664 B，**构建 == MO2 部署**（双份 md5 一致）
- 备份：`src/backup-v1.08-20260919-000410/`
- 提交 `bf7e402`，tag `v1.08-probe`
- 既有回归全过：`v107c_reprojsrc` OK、`v107_lockrelease` OK、`v100_family` PASS、`v102_camprev` PASS

**★ 本轮刻意没有修任何东西。** 在一个「读数本身不可信」的状态下，
再加一层猜测式修复只会增加下一轮必须撤销的东西 ——
这是 17 章那次一整天白干的直接结论。
"""


def main() -> int:
    apply = "--apply" in sys.argv
    s = io.open(LEDGER, "r", encoding="utf-8", newline="").read()
    raw = s.encode("utf-8")

    print("ledger: %d B" % len(raw))
    print("marker already present: %d (must be 0)" % s.count(MARKER))
    print("anchor count: %d (must be 1)" % s.count(ANCHOR))
    if s.count(MARKER) != 0:
        print("REFUSED: chapter 18 already written")
        return 2
    if s.count(ANCHOR) != 1:
        print("REFUSED, nothing written")
        return 3

    out = s.replace(ANCHOR, "\n---\n\n---\n---\n\n" + CH18.strip("\n") + "\n\n---\n\n---\n---\n\n**本文件维护规则**")
    print("would grow %d -> %d B (+%d)" % (len(raw), len(out.encode("utf-8")), len(out.encode("utf-8")) - len(raw)))

    if not apply:
        print("(dry run: nothing written)")
        return 0

    io.open(LEDGER, "w", encoding="utf-8", newline="").write(out)
    chk = io.open(LEDGER, "r", encoding="utf-8", newline="").read()
    rb = chk.encode("utf-8")
    ok = (chk.count(MARKER) == 1
          and chk.count("**本文件维护规则**") == 1
          and chk.count("### 18.1") == 1 and chk.count("### 18.8") == 1
          and rb.count(b"\r\n") == 0
          and chk.rstrip().endswith("只在第 9 章与末尾追加。"))
    print("post-check: marker=%d rules=%d 18.1=%d 18.8=%d CRLF=%d tail_ok=%s"
          % (chk.count(MARKER), chk.count("**本文件维护规则**"), chk.count("### 18.1"),
             chk.count("### 18.8"), rb.count(b"\r\n"),
             chk.rstrip().endswith("只在第 9 章与末尾追加。")))
    print("final size: %d B  RESULT: %s" % (len(rb), "OK" if ok else "FAILED"))
    return 0 if ok else 4


if __name__ == "__main__":
    sys.exit(main())
