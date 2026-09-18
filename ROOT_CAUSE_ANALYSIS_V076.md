# DFG 冻结问题 —— 根因分析（v0.76 数据定案）

**日期**：2026-09-18
**构建**：v0.76（build Sep 18 2026 07:34:13，md5 `8428c0f9e793571e481e2ffe0de70813`）
**数据源**：`DynamicShaderFrameGen.watchdog.log`（run #3，470 tick / 95.4 s）+ `DynamicShaderFrameGen.log`

---

## 0. 先纠正我上一轮的判决（错了就说错）

**上一轮我写了什么**：
> "窗口失聪时渲染线程仍在出帧 ⇒ 卡的是**消息线程**（别的插件 / 引擎主线程）。

**错在哪**：我把"`msg=0`"当成了"用户感受到的卡死"的同义词，只看了**首次/末次**两个采样点，没有做分布分析。
做了分布分析（`tools/analyze_msg0.py`）之后，结论**完全不同**。

**正确结论**：`msg=0` 的 115 次 **不是病**，是**正在加载**。而真正的病（`dlssgOk=false`）**被 v0.76 探针测出来了，只是探针标签误导了我**。

---

## 1. 决定性的分布分析

```
[1] Burst structure
    total msg=0 ticks : 115
    number of bursts  : 2                    <-- 只有 2 段！不是散布
    longest burst     : 95 probes

    #    start          end            probes dur(s)  frames     stage(modal)
    0    08:27:35.140   08:27:53.999   95     18.86   1->6       d3d11 Wait
    1    08:28:54.744   08:28:59.356   20     4.61    3530->3792 d3d11 Wait
```

**两个 burst 的特征都是：`sampledLastFrame` 长时间不前进**

| burst | frames 实际推进 | 观察期内帧率 |
|---|---|---|
| #0 | `1 → 6`（95 次探测、18.86 秒） | **0.27 fps** —— 基本零帧 |
| #1 | `3530 → 3792`（20 次探测、4.61 秒） | 57 fps —— **但在切换** |

burst #0 期间看门狗自己的 `silent` 从 932ms 一路涨到 **19591ms** —— 这是**同一个帧被卡了 19.6 秒**，不是渲染线程"健康地出帧"。我上一轮把这个 19591ms 读成了"渲染活的"，是因为我只看末次采样（`silent=13ms`，那已经是 burst #1 的末尾了）。

```
[4] silent 分布 期间 msg=0
    >=1500ms        91   ############################################################
    max silent during msg=0 : 19591ms @ 08:27:53.799
```

**92/115 次 `msg=0` 发生在 silent ≥ 1500ms 的时候** —— 也就是说 `msg=0` 和"渲染线程也停了"是**同一件事的两面**：

> **主线程被加载阻塞 ⇒ 不出帧 ⇒ 消息泵也不轮询 ⇒ `msg=0`**

所以 `msg=0` 是**主线程阻塞的症状**，而主线程阻塞的原因写在主日志里：

```
[08:27:53.909] [XRAY] LONG FRAME 19707.4ms (capUs=6289 mult=1 menu=0)
[08:28:54.627] [XRAY] LONG FRAME  357.2ms (capUs=6289 mult=1 menu=1)
```

**再看 `[3] focus / alive`**：

```
    focus=1 : 115        <-- 窗口是"聚焦"的，只是不应答
    alive=1 : 115        <-- 进程活着
```

⇒ 窗口在，进程在，但**主线程卡在加载里 19.7 秒**。这不是死锁，是**同步加载**。

---

## 2. 修正后的分段判决

| 段 | 时间 | `msg` | `frames` | 真实现象 |
|---|---|---|---|---|
| A | 08:27:34.19 → 08:27:53.85 | **0 ×95** | 1 | **游戏主线程加载 19.7 秒**（`LONG FRAME 19707.4ms`）—— 正常但很慢 |
| B | 08:27:54 → 08:28:53 | 1 ×347 | 1→3530 | 菜单 3D 背景，59 fps，**健康** |
| C | 08:28:54.7 → 08:28:59.4 | **0 ×20** | 3530→3792 | 菜单关闭 → **世界载入**（`LONG FRAME 357ms`、`MENU EDGE open=0`） |
| D | 08:28:59.4 → 08:29:09.7 | 1 | 3792→4314 | 世界内渲染，健康 |

**段 A 和 C 都是"载入"，不是"卡死"。** 而且段 A 的 `focus=1`：Skyrim 在加载时确实会让窗口死掉十几秒（MO2 启动 + 大量 ESP + DynDOLOD 输出），这是**加载时长**问题，不是插件问题。

---

## 3. 真正的病：`dlssgOk=false`（

主日志里 **32 次**：

```
[FrameGen] DLSSG diag: fgOn=true dlssgOk=false token=0x7ffd9ccc9d28 fail=1
```

而 `dlssgOk=true` 只有 **3 次**。

### 3.1 曲线交叉验证 —— 这是决定性的

`FPS probe` 行的 `accepted=` 字段：

| 时间 | `real=` | `accepted=` | 含义 |
|---|---|---|---|
| 08:27:55 – 08:28:53 | 57–58 fps | **`accepted=0`** | **零插值**，一整分钟都是假的 |
| 08:29:01.065 | — | `MFG probe: runtime ACCEPTED 2x` | 只在**退出前 8 秒**才被接受 |
| 08:29:02 – 08:29:04 | 52 / 49 fps | `accepted=2` | **只有这 3 个采样是真的 2x** |

**注意**：`real=58.4` 全程稳定，但 `cap~=116.9 (=real*2, COMPUTED not measured)` —— 日志自己标了 **COMPUTED not measured**。
⇒ 那 58 fps 是**真帧率**，`cap~` 是**乘出来的、没测过的**。玩家看到的"27→107"如果发生过，也不是这段。

### 3.2 为什么被拒

```
[08:29:01.030] [W] MFG probe: runtime REJECTED 4x (result 38 = eErrorInvalidState) -> retrying at 3x next frame
[08:29:01.048] [W] MFG probe: runtime REJECTED 3x (result 38 = eErrorInvalidState) -> retrying at 2x next frame
[08:29:01.065] [I] MFG probe: runtime ACCEPTED 2x (1 interpolated frames) | runtimeReportsMax=2x overrideAsksMax=4x
```

`runtimeReportsMax=2x` ⇒ **Streamline 运行时本身就只支持 2x**。
4x/3x 被 `eErrorInvalidState`（38）拒绝，**并且是在 `MENU EDGE open=0` 之后才第一次被调到梯子逻辑**。

⇒ **`overrideAsksMax=4x` 是无效的**。上一轮我们发现的 DLSSG-Transfusion（`{"multiplier":4,"mode":"fixed"}`）正是**解锁 4x 的那个 kernel unlocker**，而现在它**已被按用户指示移出**。
⇒ **移出 Transfusion = 放弃 4x**。这是当前状态与"27→107"那次运行之间**唯一**的差异。

### 3.3 为什么 `dlssgOk=false` 持续 32 次

`token=0x7ffd9ccc9d28` 每次不同 ⇒ 不是缓存了失败结果。
`fgOn=true` 但 `dlssgOk=false` + `fail=1` ⇒ SetOptions 或 tag 提交环节**每帧都在失败**，且失败**不打断渲染**（段 B 有 3530 帧的健康出帧）。

结合 `[08:28:55.945]` 那行出现在 `MenuDraw entry` 之后、`FPS probe real=48.0`（低于 58）之前 —— 与 `LONG FRAME 357.2ms` 同段 ⇒ **menu 切换期**的失败。

---

## 4. 结论（一句话）

> **没有死锁，也没有渲染侧的 bug。**
> 玩家说的"卡死"= **两段 Skyrim 自身的同步加载**（19.7 秒 + 0.36 秒），窗口在加载期间不应答是对的；
> 而**帧生成从头到尾基本没工作**（`accepted=0`，`dlssgOk=false` ×32），
> 因为**唯一能解锁 4x 的 DLSSG-Transfusion 已被移出**，运行时只接受 2x。

**两条独立的待办**：
1. **4x / MFG**：要 `overrideAsksMax=4x` 生效，必须装回 kernel unlocker（Transfusion 或 dlssg_for_sm86 / MFG Bridge）。这是**用户侧配置选择**，不是代码 bug。
2. **加载时长 19.7 秒**：属于 mod 列表规模问题（775+ mod / DynDOLOD），DFG 改不了。可优化但不属于本插件职责。

---

## 5. 已做的代码改动（v0.76，保留）

| 改动 | 位置 | 作用 | 判定 |
|---|---|---|---|
| `dsync` 方向修正 | `DX12SwapChain.cpp` ~1290 | `real == frameIndex ? 1 : 0`（1=没翻页） | ✅ 数据证明生效（全程 0） |
| `g_probeHwnd` 发布 | `DX12SwapChain.cpp` ~889 | 把 hwnd 给看门狗 | ✅ 生效 |
| 窗口响应探针 | `DX12SwapChain.cpp` ~W2 | `SendMessageTimeoutA(WM_NULL)` | ✅ 生效（但**语义被我误读过**，见 §1） |
| `msg=/alive=` 字段 | 看门狗行 | 区分"窗口死"vs"进程死" | ✅ 生效 |
| RELOCK 报告 | `FrameGen.cpp` ~585 | 打印被接受的那一组相机 | ✅ 生效（`08:28:58.702` 有一次） |

**这 5 处都不用回退** —— 它们让"卡死"变成了可测量的事实。只是 v0.76 的 `part_responsiveness` 文案把 `msg=0` 直接叫"真正的无响应"，**把加载误报成了故障**，这个文案要改。

---

## 6. 下一步

1. **改 `part_responsiveness` 的判据**：`msg=0` 必须与 `silent` 联合判定 ——
   - `msg=0 + silent >= 1500ms` ⇒ **主线程加载/停顿**（不是 DFG 的问题）
   - `msg=0 + silent < 1500ms` ⇒ **消息泵卡而渲染活着**（才是真正可疑的）
   现在的实现把两者都叫"无响应"，必须分开。
2. **把 `accepted=` 与 `dlssgOk=` 加进读取器的判决段** —— 这是本轮唯一真正的"病"，但当前读取器没有为它出结论。
3. **让用户决定**：要不要装回 Transfusion 来拿 4x（并接受双插件冲突），还是接受 2x。

---

## 7. 环境变更恢复指引

已移出（备份在 `D:/Modding/DynamicShaderFrameGen/_removed_transfusion_20260918-074044/`）：

```
dinput8.dll              (540672 B)  = DLSSG-Transfusion v1.4.0-pure-warp
DLSSG-Transfusion.json   {"multiplier":4,"mode":"fixed","blackwellTransfusion":true}
```

恢复（若要 4x）：

```bash
cp "D:/Modding/DynamicShaderFrameGen/_removed_transfusion_20260918-074044/dinput8.dll" \
   "D:/ENB-EJ/Skyrim Special Edition/"
cp "D:/Modding/DynamicShaderFrameGen/_removed_transfusion_20260918-074044/DLSSG-Transfusion.json" \
   "D:/ENB-EJ/Skyrim Special Edition/"
```

> ⚠️ 注意：`dinput8.dll` 与 `DLSSG-Transfusion.json` 都在**游戏根目录**（非 MO2 mod 目录）。
> 用户已明确"本体不需要部署" —— 那么 4x 就**无法达成**，应改为接受 2x 并调整预期。
