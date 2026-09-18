# DFG 冻结/卡死 —— 真根因定案（v0.78）

**日期**：2026-09-18 09:05
**被分析运行**：v0.76，08:59:09 – 08:59:54（45.1 s / 1403 帧 / 222 tick）
**结论**：**捕获层接受了「逐字节冻结」的相机矩阵** —— 这是真正的根因，前 6 轮全部没找到。

---

## 0. 三轮判断的演变（每次都是我自己错）

| 轮次 | 我的结论 | 错在哪 |
|---|---|---|
| 第 5 轮 | "卡的是消息线程" | 只看 `msg=0` 首/末采样点，没做分布分析。实际 115 次聚成 2 段，段 #0 里 `silent=19591ms`、`frames 1→6` ⇒ **渲染线程也停着** |
| 第 6 轮 | "没有 DFG 导致的卡死；帧生成 89% 没输出（阶梯被菜单挡住）" | 阶梯问题**真实存在**并已修，但它**不是**卡死的原因。我当时说"不存在 DFG 导致的卡死"——**错了** |
| 第 7 轮（本轮） | **捕获层矩阵冻结** | —— |

**教训**：我前一轮用 `[CAM] acc` 的 `pos` 字段判断"相机没跟随玩家"，但 `pos` 在冻结时**本来就不会变**（它就是冻结的那个值）。用**故障本身的产物**当判据 = 循环论证。

---

## 1. 真根因：冻结的相机矩阵被闸门放行

### 1.1 决定性证据 —— 逐字节恒等

```
[CAM] raw #17101 @ 08:59:51.806 ViewProjUnj
  1.19174 0.00466757 -5.41947e-13 0 | 1.24468e-05 -0.00317798 2.11867 0 |
  -0.00391672 1.00003 0.00150006 -15.0006 | -0.00391655 0.999991 0.0015 0

[CAM] raw #19801 @ 08:59:54.143 ViewProjUnj
  1.19174 0.00466757 -5.41947e-13 0 | 1.24468e-05 -0.00317798 2.11867 0 |
  -0.00391672 1.00003 0.00150006 -15.0006 | -0.00391655 0.999991 0.0015 0
```

**2.337 秒、2700 个快照、4196 次接受之后，矩阵一个字节都没变。**

而同期 `#17816`、`#18548` 是**完全不同的相机**（UI 正交 `-0.111111` 等）——
⇒ perFrame 缓冲**有**在写不同相机，只是**被接受的那一个**是冻结的复本。

### 1.2 后果链条（与症状完全吻合）

```
prevForReproj == curForReproj   (逐字节相等)
        ↓
clipToPrevClip = inv(cur) × prev = I   (单位矩阵)
        ↓
DLSS-G 被每帧告知「相机没动」
        ↓
重投影的相机项被静默丢弃
        ↓
画面不稳 / 抖动 / 冻结
```

数字佐证：**`clipDevMax=0.0000` 在全部 12 个心跳样本里**（玩家正在走动），
而插件自己的 VERDICT 早就写在日志里：
> `flicker cause: the engine previousViewProj is USELESS on every frame ... moving frames must show clipDevMax > 0 (identity would be 1.000000)`

**这个 VERDICT 从第 5 轮就一直在日志里，我没当回事。它是对的。**

### 1.3 为什么闸门放行了

`AcceptCameraSnapshot`（`FrameGen.cpp:539`）的两道检查都**看不见冻结**：

| 检查 | 代码 | 为什么漏 |
|---|---|---|
| ① 可用性 | `magVP > 1e-6 && magView > 1e-6`，非 NaN | 冻结矩阵**非零、非 NaN**，健康 |
| ② 连续性 | `d2 = |pos − snapLastPos|²`，`> kCamJumpTol²` 才拒 | 冻结矩阵的 `pos` **恒定** ⇒ `d2 ≈ 0` ⇒ **连 JUMP 分支都进不去** |

⇒ 冻结矩阵是**永久自洽**的，两道门都拦不住。
统计：`snap(acc/jmp/re/zero/arr)=13575/5010/1/0/18585` —— 27% 因 JUMP 被拒，
**但冻结的那个被接受了 4196 次**。

---

## 2. 修复（v0.78）

### 2.1 判据设计：为什么不能只判"矩阵相同"

**静止的相机也会产生相同矩阵，而且那是合法的**（加载屏、暂停、站着不动）。
判据必须是：

> **一个相同矩阵，出现在一个「不同矩阵」之后** ⇒ 不可能两者都是"场景静止"。

两个逐字节相同的矩阵被一个不同的相机隔开，只可能是
**同一个陈旧的 perFrame 槽位被重复读取**。

```cpp
bool identical = (snapLastMat == m);           // 逐元素逐位比较
if (identical && snapSawDifferentSinceRepeat) {
    ++snapFrozenRepeats;
    if (snapFrozenRepeats > kCamFrozenTol) { ++snapFrozenReject; return false; }
} else if (!identical) {
    snapSawDifferentSinceRepeat = true;        // 见过不同的 ⇒ 武装
}
```

* `kCamFrozenTol = 120`：08:59 那次 **2.34 秒内重复 4196 次**，120 次远小于一个真实静止期，
  且不会对"短暂静止后恢复运动"误判。
* 位置在 **JUMP 闸门之前** —— 因为冻结矩阵 `d2≈0`，放在后面永远执行不到。

### 2.2 改动清单

| 文件 | 改动 |
|---|---|
| `src/FrameGen.h` | +5 字段：`snapHaveLastMat` / `snapLastMat[4][4]` / `snapFrozenRepeats` / `snapFrozenReject` / `snapSawDifferentSinceRepeat` |
| `src/FrameGen.cpp` | `kCamFrozenTol = 120` 常量 |
| `src/FrameGen.cpp` | 冻结闸门（插在 `float d2 = 0.0f;` 之前） |
| `src/FrameGen.cpp` | 在 JUMP 拒绝分支引用计数器（避免 unused 警告） |

字节：`FrameGen.h` 13548→14635，`FrameGen.cpp` 48396→50078。
行尾保持（`.h`=CRLF、`.cpp`=LF），UTF-8 完好。

**补丁脚本**：`tools/add_v078_frozen_camera.py`（干跑默认，`--apply` 才写；
锚点唯一性 + canary + 花括号增量平衡 + marker 幂等守卫，全部通过）。

### 2.3 附带发现（本轮排除的误判）

我曾一度认为 `path` 有 78 倍超速问题（`path` 在 0.771 s 内涨 19323）。
**这是我自己读错**：`path` 是**整个会话累计**（`snapPathLen += snapAcceptDist`，永不重置），
而该日志行被节流到 0.25 s —— 两行之间隔了 **586 次接受**。
19323 ÷ 586 = **33 单位/帧**，正常步行速度。**写进文档前核实掉了。**

---

## 3. 仍然待办（阶梯问题，已诊断未修代码）

上一轮找到的**阶梯被菜单挡住**问题是**真实且独立**的，不是本轮根因但也没修（只改了 INI 建议）：

* `menuBlock` 分支跳过 `SetDLSSGOptions()` ⇒ 阶梯不推进
* 08:59 那次：菜单期 `08:59:29.014 .. 08:59:47.091`（**18 秒**）帧生成为 0
* 运行时自报上限 2x，INI 请求 4x（`MFGMaxFramesOverride=3`）

**建议**：INI `MFGMaxFramesOverride` 3→**0**、`DLSSGFramesToGenerate` 3→**1**。

---

## 4. 验证方法

```bash
"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe" \
  D:/Modding/DynamicShaderFrameGen/tools/read_xray_log.py
```

**核心判据（一条即可定案）**：

> **进世界，走动 30 秒，看心跳里的 `clipDevMax`。**
> * 修复前：`clipDevMax=0.0000`（全部 12 样本）
> * 修复后：**必须 > 0**（运动中单位矩阵是不可能的）

辅助判据：
1. `snapFrozenReject` 增长（新增计数器，日志里的 `[CAM]` 拒绝数应上升）
2. `[CAM] raw` 里连续两次 `ViewProjUnj` 不再逐字节相同
3. 心跳 `frozen=` 下降（引擎侧冻结计数）
4. 画面稳定性主观确认（`clipDevMax > 0` 是客观前提）

**回归测试**：
* "主菜单停 30 秒"（验证阶梯问题，与本次修复独立）
* "进世界走动 30 秒"（验证本次修复）

---

## 5. 构建记录

```
FrameGen.h   13548 → 14635 bytes   backup=FrameGen.h.bak-20260918-090415
FrameGen.cpp 48396 → 50078 bytes   backup=FrameGen.cpp.bak-20260918-090415
```

回滚：
```bash
cp D:/Modding/DynamicShaderFrameGen/src/FrameGen.h.bak-20260918-090415 \
   D:/Modding/DynamicShaderFrameGen/src/FrameGen.h
cp D:/Modding/DynamicShaderFrameGen/src/FrameGen.cpp.bak-20260918-090415 \
   D:/Modding/DynamicShaderFrameGen/src/FrameGen.cpp
```

---

## 6. 为什么前 6 轮都没找到

1. **没有把 VERDICT 当结论**：`clipDevMax=0 while moving` 从第 5 轮就在日志里，
   我每轮都读到了它，但每轮都在找"更根本"的东西（GPU、线程、加载、阶梯）。
2. **判据取错了字段**：用 `[CAM] acc` 的 `pos` 判断"相机是否跟随玩家"，
   而 `pos` 在冻结时**恒定**——用故障的产物当判据。
3. **没有做逐字节比较**：一直在看"矩阵幅度是否为零"（`curMag=15`，健康），
   从没比较过"两帧矩阵是否相同"。冻结矩阵的幅度是**健康**的。
4. **被"条件全绿"骗了**：`fence` 单调、`lastPr` 增长、`silent` 毫秒级 —— 这些**都是前提**，
   不是"重投影正确"的证明。（见技能 §97）
