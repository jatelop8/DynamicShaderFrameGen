# MFG 记忆总纲 —— 多倍帧生成 + DLSS5 的完整账本

**建立时间**：2026-09-18 19:40
**建立原因**：用户指出「一直压缩上下文 导致这两天我们只做多倍帧生成的记忆出现了严重缺陷」。
本文件**不做概括、不做摘要**，是把散落在 20+ 个文档里的**结论、证据、我犯过的错**一次性钉死在磁盘上。
**每次改动后必须追写本文件**，它比对话历史权威。

---

## 第 0 章：四大目标与当前达成度（诚实表）

| # | 目标（用户原话） | 当前状态 | 卡在哪 |
|---|---|---|---|
| 1 | **多倍帧生成做出来** | ⚠️ 代码能请求 4x（v1.05 已恢复），**从未在游戏里成功跑出稳定的 >2x** | 请求层已通；执行层（内核）与节奏层（pacer）反复出错 |
| 2 | **游戏完美使用多倍帧生成** | ❌ **从未达到**。当前状态是"冻结"→"闪退" | 见第 5 章：冻结有 3 条独立成因，已被我逐个搞错 |
| 3 | **支持 RTX 20~50 全系列** | ❌ **一行未做**。20/30 系需要 `dlssg_for_sm86/sm75` 内核，代码里只有模块名检测 | 未实现任何 20/30 系专用路径 |
| 4 | **打通 DLSS5** | ⚠️ **曾经有过**（NGX Feature 18，`src/NeuralRendering/`，v0.48），**但 DLL 现在是否启用未验证** | 需要一次上机确认 `sl.dlss_nr` 是否注册 |

**★ 最重要的自我判断：这四项目标的优先级被我自己搞乱了。**
我一直在冲刺 #1/#2，而 #2 的失败原因**每次都不是多倍帧生成的逻辑**，而是
**我为了让多倍帧生成工作而加的"保护机制"本身**（让权、闸门、门闩、上限、cap）。
**这条规律在下面第 5 章会以时间线形式重复三次。**

---

## 第 1 章：代码是怎么写的（逐函数，行号是当前 v1.05 实际值）

### 1.1 三条 Provider 路径

| Provider | 实现文件 | 状态 |
|---|---|---|
| `0` = FSR3.1 FG | `src/FidelityFX.cpp` | **代码注释标注为"默认、最稳定"**，历史上真正正常跑过 |
| `1` = DLSSG | `src/Streamline.cpp` + `src/DX12SwapChain.cpp` | 本轮全部工作都在这条路上 |
| `2` = XeSS | **不存在** | 全项目 `grep -i xess` = 0 |

**★ Provider 只在 `DX12SwapChain::CreateSwapChain()` 被消费一次**（决定 `dlssgMode` /
`BufferCount` / D3D12 proxy 路径）。运行中改它**零效果**，必须重启。这是结构性的，无热切方案。

### 1.2 DLSSG 数据流（从申请到上屏）

```
[启动] Streamline.cpp:201-213
        slDLSSGGetState(viewport, state, nullptr)
        hwMax = max(1, state.numFramesToGenerateMax)      ← Ada 上报 1
        dlssgMaxFramesToGenerate = hwMax                  ← v0.51 起不再被改写（只读真值）
        ApplyMfgOverride(hwMax)                           ← line 223

[启动] Streamline.cpp:223 ApplyMfgOverride
        want = INI.MFGMaxFramesOverride
        want == 0  → dlssgEffectiveMax = hwMax            ← 完全跟随硬件
        want <= hwMax → dlssgEffectiveMax = hwMax
        want >  hwMax:
            kernelUnlocker == false → dlssgEffectiveMax = hwMax  ← 拒绝，买不到被拒的多秒帧
            kernelUnlocker == true  → dlssgEffectiveMax = max(a_hwMax, clamped)   ← v1.05
              (v1.03 这里错写成 hwMax，导致 ladder 永远够不到 4x)

[每帧] Streamline.cpp:1802 ProbeMfgLadder()   ← v0.79 起从 Present 无条件调用（先于 menu guard）
        mfgProbeStep 阶梯：被拒就逐帧降档并锁存
        MfgStallGovAllow()：>150ms 的帧 ⇒ 探测冷却 24 帧（杜绝停顿自我喂食）

[每帧] Streamline.cpp:1470 SetDLSSGOptions(...)
        effectiveMax = max(1, dlssgEffectiveMax)                    :1553
        mfgProbeStep 与 effectiveMax 取 min                          :1557
        dlssgFramesToGenerate = mfgProbeStep                         :1559
        opts.numFramesToGenerate = dlssgFramesToGenerate             :1588  ← v1.05 恢复无条件写
        opts.numBackBuffers = 3                                      :1589
        opts.mvecDepthWidth/Height ← 从真实 interop 资源反推          :1599-1614
        r = slDLSSGSetOptions(viewport, opts)
        → dlssgAcceptedFrames = 结果里报的 numFramesToGenerate（实测值）

[每帧] Streamline.cpp:1994 ReflexSleep()
        capMult 从 dlssgAcceptedFrames 取（v1.05：无则 2x 地板）      :2043-2067
        capFps  = refreshRate - 1                                    :2068
        opts.frameLimitUs = 1000000 / capFps                         :2075
        → 写进 Reflex 的 FLIP cap（"每真实帧发几个 flip 给面板"）

[每帧] DX12SwapChain.cpp Present()
        CensusPresentThread()                                        ← v0.81 观察用
        g_presentEnteredMs.store(now)                                ← v1.04b 时间戳
        swapChain->Present(0, Flags)                                 ← ★ 冻结发生地
```

### 1.3 三个上限变量的语义（**极易混，我已混过**）

| 变量 | 位置 | 含义 | 谁写 |
|---|---|---|---|
| `dlssgMaxFramesToGenerate` | `Streamline.h:238` | **运行时上报的 STOCK 上限**。Ada = 1。**只读真值，永不被覆盖改写** | 仅启动时一次 |
| `dlssgEffectiveMax` | `Streamline.h` | **本插件允许自己请求的上限** | `ApplyMfgOverride` |
| `dlssgAcceptedFrames` | `Streamline.h` | **实测值**：运行时实际接受了几个插帧 | `SetDLSSGOptions` 结果 |

**★ 铁律：只有 `dlssgAcceptedFrames` 是测量值，另两个都是声明值。**
任何"我们成功了几倍"的结论**必须**来自 `dlssgAcceptedFrames`。

### 1.4 DLSS5（NGX Feature 18 = Neural Rendering）

- 代码：`src/NeuralRendering/`（`Runtime.cpp` / `Renderer.cpp` / `D3D12Interop.cpp`）
- 运行库：`nvngx_dlssnr.dll`（158 MB）+ `sl.dlss_nr.dll`
- 挂载方式：Streamline feature id **1004**（`kFeatureDLSS_NR`）
- 历史：v0.48 建成 → v0.25 曾**整段删除**（DMCA 风险）→ 后又恢复为自有实现
- **v1.02 之后代码一行未改**，本轮完全没碰
- INI：`NeuralRenderingEnabled=1`、`NRRenderScale=1.00`

**★ 关键交互（用户问"怎么才能又有多倍又有 DLSS5"）**：
两者**不冲突**，但**共享显存与 D3D12 命令队列**。已知风险记录在 9-17 记忆：
> 4x 显存（README 明确警告；本机同时载入 `nvngx_dlssnr.dll` 158MB + dlss + dlssg + FSR3，且 Edge 全程在跑）

⇒ **DLSS5 打开时，多倍帧生成的显存余量显著变小。** 这是"又有多倍又有 DLSS5"的真实约束，
不是代码冲突。

---

## 第 2 章：没有多倍帧生成的时候是怎么做的（历史基线）

### 2.1 时间线（git 提交为证）

| 版本 | 提交 | 做了什么 |
|---|---|---|
| v0.48 | `d0292a8` | DLSS 5 Neural Rendering 内置（NGX Feature 18）+ DLSS 超分移到 ENB 之前 |
| v0.39 | `6c04406` | **移除 DLSSG，只留 FSR3** —— 用户决定："N 卡 FSR3 工作完美" |
| v0.50 | `6729bcd` | **MFG max-frames override** —— 多倍帧生成第一次出现 |
| v0.51 | `44591b7` | 回退到 `Provider=0` + 诚实 MFG 报告 + 安全阶梯探测 |
| v0.52–v0.57 | 多个 | 频繁切换修复、探针、mvecScale |
| v0.79–v1.05 | 本轮 | **全部是冻结/闪退修复，无一是 MFG 功能推进** |

### 2.2 ★★ 这个表说明了什么（最重要的历史结论）

**v0.39 到 v0.50 之间，这个模组是"正常工作"的 —— 工作方式是 FSR3 2x。**

- v0.39 的提交信息：`remove DLSSG - FSR3 only (user decision, N-card FSR3 works perfectly)`
- v0.50 之前的所有版本：**没有 MFG，没有 unlocker，没有让权，没有阶梯，没有 capMult**
- 那时**没有冻结，没有闪退**

**⇒ 这两天的"冻结/闪退"100% 是多倍帧生成这条支线引入的，不是原有问题。**
**⇒ 回归基线永远是 `Provider=0`（FSR3）+ `MFGMaxFramesOverride=0`。**
**⇒ 任何时候我改坏了，用户能一秒回到可玩状态的方法就是这两行。**

### 2.3 用户的原话（第 2 章的直接依据）

> **"什么鬼 我们之前的帧生成模组就是有dlss5的 我们之前已经确定了xess的多倍帧生成内容 你怎么了？"**
> **"啊？我们之前不是已经做到了4倍了吗？就是transfusion 你失忆了？"**

**核对结果：用户两句话都对，但我都没接住。**

| 用户说 | 事实 | 我的问题 |
|---|---|---|
| "我们之前就是有 DLSS5 的" | ✅ v0.48 就有，`src/NeuralRendering/` 一直在 | 我说过"DLSS5 本轮完全未碰"，**没告诉用户它其实已经在了** |
| "之前已经做到 4 倍" | ✅ `DLSSG-Transfusion.log` 07:29 实锤 4x 成功 | 我把它当成"未验证的目标"，**没当成"已完成的基线"** |
| "xess 的多倍帧生成内容确定了" | ⚠️ 查证：`grep -i xess` = 0，**代码里没有** | 需要跟用户核实指的是"方案已定"还是"代码已写" |

**★ 这一章的核心：我把"已经做到过的东西"当成了"还没做到的东西"，于是从零开始重新发明，
把原本能跑的东西改坏了。**

---

## 第 3 章：RTX 20 / 30 / 40 / 50 各系怎么才能有多倍帧生成

### 3.1 物理约束（不可绕过）

多倍帧生成 = **真实帧 + N 个生成帧**。生成帧由 `nvngx_dlssg.dll` 里的
**架构专属内核（kernel，即 cubin）**产出。

| 架构 | 系 | 原生 `numFramesToGenerateMax` | `nvngx_dlssg.dll` 里有无该架构内核 |
|---|---|---|---|
| Turing | RTX 20 | **无 DLSSG 硬件支持** | ❌ 没有 |
| Ampere | RTX 30 | 报 1（2x），实际**无内核** | ❌ 没有（sm_86 不在支持列表） |
| Ada | RTX 40 | **报 1（2x）** | ✅ 有（但只给 2x） |
| Blackwell | RTX 50 | 报 3（4x） | ✅ 有（给到 4x+） |

**⇒ Ada 报 1 是"驱动策略锁"，不是"没内核"。** Transfusion 07:29 的日志证明了这点：
```
Applied fixed multiplier: 4x, result=0 (eOk)
DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
[PERF] 4x | Kernel: Ada | FPS: 39.6 (25.28ms)
```
注意 **`Kernel: Ada`** —— 它用的就是 Ada 自己的内核，只是把"策略锁"拆了。

### 3.2 三条可行路径

| # | 路径 | 覆盖 | 原理 | 本项目状态 |
|---|---|---|---|---|
| **A** | **DLSSG-Transfusion** | **RTX 40** | hook `slGetFeatureFunction`，在返回函数指针前把 `slDLSSGSetOptions` 换成自己的包装，强制 `multiplier=4` | ✅ 已实测成功（07:29）。文件 `D:/ENB-EJ/Skyrim Special Edition/dinput8.dll`（5,945,344 B） |
| **B** | **dlssg_for_sm86 / sm89** | RTX 30 / 40 | 自带 DLSSG 310.1 运行时 + 老架构内核 | ❌ 未部署。代码里只有 `GetModuleHandleA` 检测 |
| **C** | **NVIDIA MFG Bridge** | RTX 20/30 | `nvngx.dll` proxy，转发到自带内核 | ❌ 未部署 |

**★ 关键认识：这三条都是"外部 DLL"，不是本项目能自己写出来的东西。**
本项目能做的是：**① 正确检测它、② 把请求上限抬高到它能力范围、③ 不和它抢同一个字段。**

### 3.3 ★ 本项目过去在这件事上犯的**方向性错误**（必须记住）

**v1.03 的错误推理链**：
1. 观察到 Transfusion 替换了 `slDLSSGSetOptions` 的函数指针
2. 推断"它才是倍率的合法写者，我不该写"
3. ⇒ 让权：不写 `opts.numFramesToGenerate`，并且**把自己的请求上限砍回 hwMax**

**错在哪（两条，第二条是致命的）**：
- **(a)** Transfusion 是**包装器（wrapper）**不是**替代器（replacer）**。
  它拿到你传进去的 `opts`，改它想改的字段，再调用原始的 `slDLSSGSetOptions`。
  **"它写"≠"我不该写"**。
- **(b) ★ 让权那段代码是个恒等假动作**：
  ```cpp
  opts.numFramesToGenerate = std::max<std::uint32_t>(1, opts.numFramesToGenerate);
  ```
  `opts` 是**每次调用新建的零初始化局部对象**。所以这行**恒等于** `max(1, 0)` = **1 = 2x**。
  它看起来像"保留 unlocker 写的值"，实际是**每帧把 unlocker 的 4x 覆盖成 2x**。
  ⇒ Transfusion 设 4x → 我覆盖成 2x → 下一帧再设 4x → 我再覆盖成 2x → **pacer 永不收敛** →
  渲染线程停在 `swapChain->Present(0)` → **19.9 秒冻结**。

**★★ 这是本项目的头号教训：**
> **在一个"看起来应该保留外部写入"的位置上，用零初始化结构体做 `max(1, x)`，
> 得到的不是"保留"，是"写入一个常量"。**
> **让权设计必须先证明"第二写者存在且能赢"，否则让权 = 我把值改坏。**

---

## 第 4 章：DLSS5 与多倍帧生成能否共存

### 4.1 技术上：能，且不冲突

- **DLSS5（NR，feature 1004）** 跑在 `sl.dlss_nr.dll` + `nvngx_dlssnr.dll`，是**分析/重投影**阶段
- **DLSSG** 跑在 `nvngx_dlssg.dll`，是**插帧**阶段
- 两者在 Streamline 里是**不同 feature**，各自独立注册与评估

用户报告"我们之前就是有 dlss5 的" ⇒ **历史上两者是同时开着的**（v0.48 之后）。

### 4.2 真实的约束是资源，不是代码

| 资源 | 说明 |
|---|---|
| **显存** | `nvngx_dlssnr.dll` = **158 MB 常驻**；4x 帧生成需要额外 backbuffer；本机还有 FSR3 + Edge 在跑 |
| **D3D12 命令队列** | 两者都提交命令。日志出现过 `[DLSSNR] D3D12 command contexts saturated` |
| **渲染分辨率** | `RenderResolutionScale=0.44`（1689x950）而 `NRRenderScale=1.00`（NR 按 4K 分析）→ **NR 比渲染重得多** |

**⇒ "又有多倍又有 DLSS5"的正确做法：**
1. 先把 **MFG 单独跑稳**（本轮目标，尚未达成）
2. 再开 DLSS5，观察是否出现 `command contexts saturated`
3. 若饱和 ⇒ 降 `NRRenderScale` 到 0.5，或降倍率到 3x
4. **不要同时调这两个变量** —— 否则出问题无法归因

---

## 第 5 章：我犯过的错（完整清单，含根因/判据/处置）

### 5.1 冻结/闪退的**假根因**清单（我逐个宣布过"已定案"，随后被推翻）

| 轮次 | 我宣布的根因 | 被什么推翻 |
|---|---|---|
| v0.71 | 失焦 → `Present` 阻塞死锁 | 我加的 `DO_NOT_WAIT` 拆了 `FLIP_DISCARD` 的 CPU 背压，**是我造成的** |
| v0.72 | 失焦期间不排工作 | 旁路确实修好了（26s→33s），**但 fence 恒 1 从 frames=1 就开始了，与失焦无关** |
| v0.73 | 需要区分"卡死 vs 退出" | 判定完发现**根本没有退出这回事**，进程一直活着 |
| v0.74 | fence 恒为初值 = GPU 队列不推进 | 这是**真读数**，但"为什么"未定案（A/B/C 三条路径都没证实） |
| v0.76 | 两个帧生成插件在同一条 Streamline 上打架 | 部分成立，但当时没有可用的区分判据 |
| v0.77 | 帧生成失效根因（8x/9x 段） | 我被"日志本身在说谎"误导 |
| v0.78 | 捕获层接受了逐字节冻结的相机矩阵 | **前提不成立**：两条行的 `#序号` 是各自线程内的序号，不是全局帧号 |
| v0.79 | 两个线程抢同一个 swapchain Present | 过度推断：只证明了"两个 tid"，没证明"同一角色" |
| v0.80 | 加门闩拒绝外来 presenter | **把真正干活的渲染线程拒绝了 300 次，直接造成 09:31 冻结** |
| v0.82 | thread_local prev 历史 | 生效了但假设错了 |
| v0.84 | `snapFrozenRepeats` 从不重置 | 真实缺陷，但**不是**本次冻结主因 |
| v0.86 | 世界相机矩阵畸形（[3][3]=0） | 解释是错的（数据自身矛盾更上游） |
| v1.00 | 菜单相机夺流 | 真实缺陷，已修，但冻结仍在 |
| v1.02c | 引擎 prev 字段是死的 | 真实缺陷，已修，但冻结仍在 |
| **v1.03** | **让权给 Transfusion** | **★ 让权表达式恒等于写 2x，是 19.9s 冻结的直接成因 —— 我造成的** |
| **v1.04** | **Reflex flip cap 用了未确认倍率** | **capMult 修复生效（4flips→2flips）但冻结依旧 ⇒ 并存异常 ≠ 根因** |
| **v1.05** | **让权表达式读零初始化结构体（本轮）** | 待验证 |

### 5.2 三条**已用日志定案**的冻结机制（互不排斥，可能同时存在）

| # | 机制 | 证据 | 状态 |
|---|---|---|---|
| **A** | **下界**：`mfgProbeStep` 停在 `dlssgEffectiveMax` 下界（日志 `mfg(hwMax/reqMax)=2/1`），`dlssgAcceptedFrames=0` 每帧 | `DLSS-G supports up to 2x` + `accepted=0` 全程 | 机制确认；v1.05 已把上限抬高 |
| **B** | **重投影 identity**：`clipDev=0.000000` 恒为 0 ⇒ `clipToPrevClip` 恒为单位阵 ⇒ DLSS-G 无有效重投影输入 ⇒ 不产出 | `clipDev=0.000000` 全部样本 + `engPrevZero=211` | v1.00 + v1.02c 已修两轮，**未验收** |
| **C** | **pacer 错配**：capMult 与 DLSS-G 实发 flip 数不一致 ⇒ 等一个永不释放的 slot | 19:04/19:16 `LONG FRAME 19xxx ms` + `presentAge=19400ms` | v1.04 已修 capMult（4→2 生效），**冻结仍在 ⇒ 不完全** |

**★ 机制 A + C 的组合就是 19:16 那次：**
上限被砍到 2x（A）→ Transfusion 装 4x → 我的让权代码写 2x → 双方拉锯（C）→ pacer 不收敛 → Present 卡死。

### 5.3 我犯的**工程性**错误（非推理类）

| 错误 | 后果 | 教训 |
|---|---|---|
| `extern` 放类内 | `error C2071`，**全部 7 个编译单元 FAILED** | 头文件报错会污染所有 TU，全部 FAILED 时先查头文件 |
| 凭记忆假设行尾 | CRLF 替换打到 LF 文件上，**幸好断言挡住** | **行尾必须逐文件实测**（同工程内混用！见 §6） |
| 补丁脚本锚点缩进猜错 | `count=0`，断言挡下 | 锚点必须**从文件实际字节现取** |
| 计数预期写错 | 断言失败但**未落盘** | 断言的价值在"错时不落盘" |
| 把 Python 换行当 C++ 换行写进补丁脚本 | 源码出现**字面 `/r/n` 与 `/t`**（Python 里 `'\r\n'` 在**单引号 heredoc 未转义**时被当字面量） | **补丁脚本里的换行必须用真实控制字符，不能写字面转义**；本次已用 `bytes.replace` 通用清理 |
| 注释行尾部换行丢失，与下一条语句粘连 | `// ...there.		if (!kernelUnlocker) {` ⇒ 语法错误 | 替换注释块时必须**显式补行尾** |
| 备份命令 `mkdir -p` 与 `cp` 同行 | `target ... is not a directory` | 显式变量、分两步 |

### 5.4 ★★ 方法论层面最大的错：**"并存异常 ≠ 根因"**

v1.04 我修 `capMult` 时，日志实锤 `4 flips` → `2 flips`（我的修复**生效了**），
**但冻结依旧**。我却已经把"capMult"宣布为根因。

> **修一个真实存在的错误，不代表修的是你正在追的那个问题。**
> **宣布根因前，必须证明"修了它，症状就消失"。修完症状还在 ⇒ 它不是根因，只是并存的异常。**

这条应作为本项目**所有诊断的第一检查项**。

---

## 第 6 章：环境铁律（违反必踩）

### 6.1 行尾 —— **同一工程内混用，必须逐文件实测**

| 文件 | 行尾 |
|---|---|
| `src/Streamline.cpp` | **CRLF**（2197 CRLF / 0 LF） |
| `src/Streamline.h` | **CRLF**（384 / 0） |
| `src/DX12SwapChain.h` | **CRLF**（276 / 0） |
| `src/FidelityFX.cpp` / `.h` | **CRLF** |
| `src/ImguiMenu.cpp` / `.h` | **CRLF** |
| `src/resource.h` | **CRLF** |
| **`src/DX12SwapChain.cpp`** | **★ 纯 LF**（0 CRLF / 1806 LF） |
| **`src/FrameGen.cpp`** | **★ 纯 LF**（0 / 1364） |
| `src/FrameGen.h` | **混合！**（310 CRLF / 33 LF） |
| `src/main.cpp` | **混合！**（162 CRLF / 7 LF） |
| `src/NeuralRendering/*` | **全部纯 LF** |

**⇒ 改任何文件前先 `count('\r\n')` 实测，不要凭记忆，也不要看扩展名。**

### 6.2 构建

```bash
cd /d/Modding/DynamicShaderFrameGen && ./build_vs.sh > /tmp/build.log 2>&1
tr -d '\000' < /tmp/build.log | grep -a -E "error C[0-9]+|error LNK|FAILED|BUILD SUCCESS"
```
- 输出**含 NUL**，`grep` 前必须 `tr -d '\000'`
- 工具链：MSVC `14.50.35717`、SDK `10.0.26100.0`、`ninja`、`-std:c++latest`、
  vcpkg `E:/vcpkg-full/installed/x64-windows-static-md`
- **`VsDevCmd.bat` 内部调 `reg.exe` 被安全策略拦截** ⇒ 必须手动设 `INCLUDE`/`LIB`/`PATH`
  （`float.h` 在 SDK ucrt 目录，不在 MSVC 目录）
- **构建即部署**：`CMakeLists.txt` POST_BUILD `copy_if_different` →
  `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/`
- **★ 构建会把 `SKSE/Plugins/` 整个同步过去，包括 INI 模板** ⇒
  改部署 INI 后一编译就被仓库模板冲回。**必须改仓库模板**才是源头

### 6.3 部署与验证

- **只部署在 MOD 文件夹**：`E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/`
- **游戏本体 `D:/ENB-EJ/Skyrim Special Edition/Data/SKSE/Plugins/` 不要放**
  （MO2 会优先本体，导致改的不生效）
- 校验必须**双份 md5 一致 + DLL 内字符串**：
  ```bash
  md5sum build/NINJA/DynamicShaderFrameGen.dll "E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.dll"
  ```
- 日志（**两份**）：
  - `C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.log`（覆盖式）
  - 同目录 `DynamicShaderFrameGen.watchdog.log`（**追加式**）
- 崩溃：同目录 `crash-YYYY-MM-DD-HH-MM-SS.log`
- Transfusion：`DLSSG-Transfusion.log` / `perf.csv`（游戏根目录）

### 6.4 补丁脚本约定（强制）

1. **默认干跑，`--apply` 才落盘**
2. 每条锚点 `count(old)` **必须恰好等于 1**，否则 `REFUSED, nothing written`
3. **插入型改动必须另有幂等守卫**（marker 字符串检查）——
   「锚点唯一」≠「只跑一次」，插入不消耗锚点，重跑会重复插入（**已踩两次**）
4. `new_string` 必须**完整包含** `old_string` 中要保留的行
5. 锚点**从文件实际字节现取**，不手写缩进
6. 改后**逐符号 grep 回读** + 核 md5 + 核行尾（`bare` 必须为 0）
7. **★ 换行在补丁脚本里必须写真实控制字符**（`\r\n` 经 shell heredoc 可能变字面 `/r/n`）

---

## 第 7 章：还剩多少次才能做好（诚实评估）

### 7.1 我必须先说清楚的前提

**我无法运行游戏。** 每一轮"是否修好"都必须由用户上机验证。
过去 20+ 轮里，我**至少 16 次**宣布"根因已定案"，随后被下一轮日志推翻。
**这不是"还有几轮"的算术问题，而是"我是否停止猜测"的问题。**

### 7.2 ★ 真正的收敛路径（我建议的，需要用户同意）

**当前打法（每轮改代码 + 上机）已被证明是发散（oscillating）的。** 建议改为：

**阶段 0：隔离（1 次上机，不改代码）**
- MO2 里**临时取消勾选 Modex** → 跑一次
- 理由：三次崩溃（18:23 / 19:04 / 19:16）**全部**是 `Modex.dll Modex::UIManager::MainWndProc`，
  地址族 `0x0000FFFF1xxx`，uptime ~32s，**本插件一行都不在栈上**。
  **19:04 那次发生在我改 v1.04 之前。**
- **Modex 崩溃会掩盖一切验证结果** —— 我无法判断"冻结修好了没有"，因为进程先被 Modex 干掉了。

**阶段 1：回到已知可玩基线（1 次上机，改 INI 不改代码）**
- `Provider=0`（FSR3）+ `MFGMaxFramesOverride=0`
- 确认：**不冻结、不闪退、能正常游戏**
- 目的：证明"我的代码改动是可回退的"，而不是"整个模组坏了"

**阶段 2：单变量推进（每次 1 次上机，只动一个变量）**

| 步 | 变量 | 期望判据 |
|---|---|---|
| 2a | `Provider=1` + `MFGMaxFramesOverride=0` + `DLSSGFramesToGenerate=1` | `DLSSG presented per real frame = 2`，不冻结 |
| 2b | 保持 2a，改 `MFGMaxFramesOverride=3` | 日志 `MFG unlocker detected` + `ACCEPTED 4x` 或 `REJECTED`（两者都是**有效信息**） |
| 2c | 保持 2b，装 Transfusion（`dinput8.dll`） | `DLSSG presented per real frame = 4` |
| 2d | 保持 2c，开 DLSS5（`NeuralRenderingEnabled=1`） | 无 `command contexts saturated` |

**★ 每一步只动一个变量。** 我过去最大的问题就是一次改 3-5 处，
出问题后**无法归因是哪一处**（19:04 与 19:16 的对比就是活证据）。

### 7.3 我的诚实估计

| 目标 | 还需上机轮次 | 前提 |
|---|---|---|
| 消除冻结 | **2–3 次** | 必须先隔离 Modex；且必须停止"一次改多处" |
| 稳定 4x（RTX 40） | **2–4 次** | Transfusion 已证明可行，缺的是"不打架" |
| RTX 20/30 支持 | **未评估** | 需要先确认用户手上有哪些卡；代码路径完全没写 |
| 打通 DLSS5 | **1–2 次** | 代码已在，只需验证 + 资源调优 |

**总计：乐观 6 次上机，现实 10–12 次。**
**★ 但前提是我必须改变打法。** 如果继续"改 5 处 + 上机 + 又被推翻"，
那**不是次数问题，是方法问题** —— 再来 20 次也一样。

---

## 第 8 章：改动策略（用户明确要求）

### 8.1 "每次做完单独备份代码" —— 已采纳，规则如下

**每次改动前**：
```bash
cd /d/Modding/DynamicShaderFrameGen
D="src/backup-v<版本>-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$D"
cp src/Streamline.cpp src/Streamline.h src/DX12SwapChain.cpp src/DX12SwapChain.h "$D/"
```
（`mkdir` 与 `cp` **必须分两步**，同行会报 `target ... is not a directory`）

**已建立的备份目录**：

| 目录 | 内容 |
|---|---|
| `src/backup-v1.03-20260918-185331/` | 4 文件 |
| `src/backup-v1.03b-20260918-185335/` | DX12SwapChain.cpp/h |
| `src/backup-v1.04-20260918-190701/` | 4 文件 + `.pre-v104b` 后缀版 |
| `src/backup-v1.05-20260918-191842/` | 4 文件（v1.05 改动前） |
| `src/backup-v1.05-final-20260918-1924xx/` | 4 文件（v1.05 改动后） |

**另外**：项目根 `git` 仓库已有完整历史（`b463b09` 为最新提交）。
**但注意：工作区有 9 个已修改文件从未提交过。**
⇒ **我的改动只存在于磁盘，不在 git 里。** 这本身是风险。

**★ 建议（需用户同意）**：每完成一个可验证的版本，做一次 `git commit`，
tag 用 `v<版本>-<日期>`。这样"单独备份"就有两级保障（目录 + git）。

### 8.2 "不要压缩上下文" —— 已采纳，规则如下

**本文件（`MFG_MASTER_NOTES.md`）是抗压缩的载体。**
- **每轮改动后必须追写**：新结论、新证据、新错误
- **不写摘要，写原文证据**（日志行、代码行号、md5）
- 对话历史可以压缩，**本文件不能**

**已同步更新的记忆位置**：
- `C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-18.md`
- `C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/MEMORY.md`
- `~/.workbuddy/skills/framegen-diagnosis/SKILL.md`

---

## 第 9 章：v1.05 本轮的最终状态（截至 19:40）

### 9.1 源码改动（4 处，全部已落盘并编译通过）

| # | 文件 | 位置 | 改动 |
|---|---|---|---|
| 1 | `Streamline.cpp` | ~226-316 `ApplyMfgOverride` | 有 unlocker 时上限 = `max(1, max(a_hwMax, clamped))`（**v1.03 的 hwMax 封顶已撤销**）；新增 `MFG unlocker detected` warn |
| 2 | `Streamline.cpp` | ~1588 `SetDLSSGOptions` | **恢复无条件写** `opts.numFramesToGenerate = dlssgFramesToGenerate` |
| 3 | `Streamline.cpp` | ~1802 `ProbeMfgLadder` | 撤销 v1.03 的让权跳过（恢复探测）+ 修复字面 `/n` 损坏行 |
| 4 | `Streamline.cpp` | ~2043-2067 `ReflexSleep` | `capMult` 只信 `dlssgAcceptedFrames`，无则 2x 地板；**移除 `dlssgMaxFramesToGenerate` 兜底** |
| 5 | `Streamline.h` | — | **删除** `mfgUnlockerOwnsMultiplier` 字段及全部引用 |
| 6 | `Streamline.cpp` | banner | `diag active v1.04` → **`v1.05`** |
| 7 | 部署 INI | ~line 80 | v1.03 的让权说明块 → **v1.05 契约说明**（含"零初始化导致恒等于 2x"的完整交代） |

### 9.2 构建与部署验证（全部通过）

| 项 | 值 |
|---|---|
| 源码大小 | `Streamline.cpp` = **115550 B**（2196 CRLF / 0 bare）；`Streamline.h` = 20365 B |
| 编译 | `BUILD SUCCESS`（`[2/2] Linking CXX shared library DynamicShaderFrameGen.dll`），**0 error / 0 warning** |
| DLL | **1,324,032 B**，md5 **`543e1ecf472e0d3de5f937eb97e4413c`** |
| 部署 | `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.dll`，**同 md5** ✅ |
| INI | `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini` = 14525 B（242 CRLF / 0 bare），备份 `.bak-v105` |

### 9.3 DLL 内字符串校验（证明改动真的进了产物）

| 字符串 | 计数 | 期望 |
|---|---|---|
| `diag active v1.05` | 1 | ✅ |
| `MFG unlocker detected` | 1 | ✅ |
| `no confirmed multiplier yet` | 1 | ✅ |
| `stockMax` | 1 | ✅ |
| `presentAge=%lldms` | 1 | ✅ |
| `FENCE WAIT TIMED OUT` | 1 | ✅ |
| `UNCONFIRMED - using the 2x floor` | 1 | ✅ |
| `handed to the external unlocker` | **0** | ✅ **v1.03 遗留已消失** |
| `mfgUnlockerOwnsMultiplier` | **0** | ✅ **字段已删除** |
| `hwMax={} unlocker={}` | **0** | ✅ 旧格式已消失 |

### 9.4 ★ v1.05 仍**未验证**（我不会假装它修好了）

- 冻结是否真修好：**未知**（我无法运行游戏）
- 闪退：**未处理**（是 Modex 的，不是本插件的）
- 4x 能否真跑出来：**未知**
- DLSS5：**一行未改**

---

## 第 10 章：下一步（请用户决策）

**我建议的第一步不是改代码，而是做隔离验证 —— 但需要你先做一件事：**

**在 MO2 里临时取消勾选 `【前置】Modex模组浏览器-Modex - A Mod Explorer Menu`，然后正常进游戏。**

理由（三重证据）：
1. 三次崩溃全部是 `Modex.dll Modex::UIManager::MainWndProc`，本插件不在栈上
2. 崩溃点 `0x0000FFFF1xxx` 是 `Add [rax], al` 类野指针执行，与 GPU/帧生成无关
3. **19:04:38 那次崩溃早于我的 v1.04 改动** ⇒ 不是我改出来的
4. **不隔离它，任何"冻结修好了没有"的结论都不可信** —— 进程会先被它干掉

跑完把 `DynamicShaderFrameGen.log` + `.watchdog.log` + 新的 `crash-*.log` 发我。

**同时，请你确认三件事：**
1. **你手上有哪些显卡**（20/30/40/50 系各几块？）—— 决定我是否要写 20/30 系路径
2. **"我们之前已经确定了 xess 的多倍帧生成内容"** —— 指的是"方案讨论过"还是"代码写过"？
   （我查了：全项目 `grep -i xess` = **0**，代码里确实没有）
3. **是否同意我按第 7.2 章的"单变量推进"打法定**（每次只动一个变量 + 每次单独备份 + 每步 commit）

---

## 第 11 章：19:40–19:50 —— 真凶落网：场上一直有**两个**解锁器

### 11.1 是什么东西在改 `dinput8.dll`

```
D:\ENB-EJ\Skyrim Special Edition\dinput8.dll
  5,945,344 B   09-18 18:01   md5 f6fe4caa46e090375803c73257ee038a
  内部字符串: "RTXMFG" × 8   ← 不是 Transfusion
```

**`RTXMFG-Universal` 是第二个 MFG 解锁器，此前从未被识别。** 证据是它每局游戏都在
游戏根目录写一份状态文件 `RTXMFG-Universal.<pid>.status.json`（6,942 B），现存 5 份：

```
21972  09-18 19:34
31920  09-18 19:04
39080  09-18 18:23
45732  09-18 19:16
37064  09-11 02:14
```

### 11.2 ★ 五次运行，RTXMFG 一次都没成功过

逐份提取（字段在五份之间**完全一致**）：

```
slInitCalls              = 0
setOptionsCalls          = 0
actualFramesPresented    = 0
applied                  = false
activeWrapperPatched     = false   ← 想 patch sl.dlss_g.dll，没 patch 上
universalRouteFailure    = 2
universalRouteFailureReason = "active wrapper unpatched"
```

而它的 hook **全部安装成功**（`slInitEntryDetourInstalled=true`、`setOptionsEntryDetourInstalled=true`、
`getState/ngxCreate/ngxEvaluate` 同理，`*EntryDetourCurrent=true`）。
⇒ **hook 装好了，但入口一次都没被调用** ⇒ 纯占用，零作用，只是每局写 6,942 B 垃圾。

它自报的目标：
```
activeWrapperPath = D:\ENB-EJ\Skyrim Special Edition\data\Shaders\Upscaling\Streamline\sl.dlss_g.dll
```
**这个目录不存在**（游戏本体 `Data/Shaders/` 为空；MO2 实际用的是
`E:/EJ/mod/mods/DynamicShaderFrameGen/Shaders/Upscaling/Streamline/sl.dlss_g.dll`）。
⇒ **路径不一致极可能就是 `unpatched` 的直接原因。**

### 11.3 时间线闭合（每一步都有时间戳）

| 时间 | 事件 | 证据 |
|---|---|---|
| 09-11 02:11 | `dinput8.dll` = RTXMFG（5,945,344 B）| 现存 `dinput8.dll.disabled` 同尺寸同 md5 |
| 09-11 02:14 | RTXMFG 写了状态文件（那时它就已经零作用）| `RTXMFG-Universal.37064.status.json` |
| 09-17 14:09 | Transfusion 部署为 `version.dll` + `dinput8.dll`（两份**同 md5** `c048b46e`）| 备份 `transfusion_proxy_dup_20260917_182050/` |
| 09-17 18:23 | 两个 patch worker 互撞 → 崩溃（写 `E9` 进 `sl.interposer.dll+0xB750`）| commit `b463b09` |
| 09-17 18:23 | 修法：`version.dll` → `version.dll.off`（只留 dinput8）| commit `b463b09` |
| **09-18 07:29** | **Transfusion 用 dinput8 跑出 4x**（`presentation count: 4x`, `Kernel: Ada`, 39.6 FPS）| `DLSSG-Transfusion.log` |
| **09-18 18:01** | **`dinput8.dll` 被换成 RTXMFG**（`f6fe4caa`）| 文件时间戳 + 内部字符串 |
| 09-18 18:23 / 19:04 / 19:16 / 19:34 | 四次运行：RTXMFG 零作用 + 冻结 + 闪退 | 4 份状态文件全部 `applied=false` |
| 09-18 07:29 之后 | **Transfusion 日志再无新行** ⇒ 它再也没被加载 | `DLSSG-Transfusion.log` mtime = 07:29 |

**⇒ 4x 成功（07:29）发生在 RTXMFG 上场（18:01）之前。18:01 之后 Transfusion 失去注入点。**
**这就是"昨天做到了 4x，今天全是冻结"的完整机制。**

### 11.4 本轮采取的行动

```
1. dinput8.dll            -> dinput8.dll.rtxmfg-off     （撤下 RTXMFG）
2. version.dll.off        -> dinput8.dll                （md5 c048b46e，还原 Transfusion）
3. version.dll.off 保持 .off                            （避免重演 b463b09 的重复部署）
4. DLSSG-Transfusion.json 从备份重建（原本不存在）
```

备份：`/d/workbuddy2/backup/unlocker_decision_20260918_194424/`

### 11.5 ★★ `DLSSG-Transfusion.json` 的正确内容（锁定）

现存的六份备份里，这个文件有**两种互相矛盾**的组合：

| 备份时间 | `patchFlipMetering` | `forceUiRecomposition` |
|---|---|---|
| 09-17 16:39 | **true** | **false** |
| 09-17 19:19 | **false** | **true** |

经 `VERIFY_proxy_dupfix.md:94` 与 `REPAIR_1934.md:8` 两份记录交叉确认，**正确组合是**：

```json
{
  "multiplier": 4, "mode": "fixed", "dynamicTargetFrameRate": 0,
  "dynamicExperimental56": false, "forceOTA": false,
  "patchFlipMetering": false,      // v1.4.1 官方默认；true 会在 NGX 初始化路径
                                   // 装递归 NVAPI 解析钩子，而 18:05 卡死的正是 slSetD3DDevice
  "blackwellTransfusion": true,
  "qualityValidWarp": true,
  "disableMenuDetection": true,
  "disableMvDilation": false,
  "forceUiRecomposition": false,   // 我 19:31 曾误改 true，REPAIR_1934 已纠正
                                   // DFG 是 Preset A（日志 uiFmt=0 = DXGI_FORMAT_UNKNOWN）
  "showOverlay": true, "logPerformance": true
}
```

已写入游戏根目录并逐字段断言通过（13/13 `MATCH`）。

### 11.6 ★★ 一次**被自己拦住**的误修（必须记）

我看到部署 INI 里 `MvecScaleOverride=1.00`，一度判定为"v1.03 遗留错误"，
准备改回 `0.00`。**在读 INI 自带的说明段后撤回。**

INI 原文写得很清楚：
```
;   0.00 = legacy 1/renderScale (default, behaviour unchanged)
;   1.00 = identity, the reference-implementation value
```
且 `FIX_FRAMESERIAL_2115.md:148` 记录：
> 本次已核对两份 INI md5 相同（`f7115e5e`，`MvecScaleOverride=1.00` / `RenderResolutionScale=0.44`），不会回退。

**⇒ `1.00` 是有意选择且有外部证据支持（NVIDIA 指南 + open-shaders：全帧路径应为 identity）。
`0.00` 的 `1/renderScale`（=2.27 @ renderScale 0.44）才被三方反驳为过估计。未改动。**

**教训（第三次触发）**：**改动前必须先读该配置项自带的说明与被引用文档，不能凭"它和默认值不同"就判为错误。**

### 11.7 本轮**未**做的（别假装做了）

- 冻结是否修好：**未知**（无法运行游戏）
- Modex 闪退：**未处理**（必须在 MO2 GUI 里手动取消勾选，我无法操作 GUI）
- 20/30 系路径：**一行未写**
- DLSS5：**一行未改**

---

**本文件维护规则**：每次改动后追写「本轮改动 / 验证结果 / 新证据 / 新错误」，
**不覆盖历史章节**，只在第 9 章与末尾追加。
