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

## 第 12 章：v1.06 —— "4x 一开始就冻结"的两个真凶

**用户原话**：「能进游戏，但是进入游戏一旦开始 4 倍帧生成就出现冻结，
左上角有帧数显示」。

**这三个字是全部线索**：**有帧数显示 ⇒ 主循环没死**。所以这不是 hang，
是"帧在跑、画面不走"。watchdog 完全证实：`presentAge max=557ms`、
`fence 1/1 -> 3214/3214`、`alive=1`、`silent max(聚焦后)=555ms`。

### 12.1 真凶一：Reflex 帧率上限丢了除数（这是"冻结"的直接机制）

**v0.54 的原始公式（79a0ea4），以及一直到 2a2b592 的每一个提交：**

```cpp
const double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;
```

**v0.54 自己的注释写着这条公式的来历：**

```
// 帧生成只有在"渲染帧率 x 倍数 <= 刷新率"时才成立，故改为按刷新率反推：
//   自动 = 刷新率 / 总倍数 - 1fps（留余量避免顶到刷新率边缘）
//   160Hz / 4x -> 39fps 渲染 -> 156 present fps，刚好在面板之下。
```

**而 v1.00 的源码备份（09-18 17:56）开始，公式是：**

```cpp
const double want = Get().refreshRate - 1.0;        // 除数没了
```

**逐提交核对（`git show <c>:src/Streamline.cpp | grep "const double want"`）：**

| 提交 | 时间 | 公式 |
|---|---|---|
| `79a0ea4` v0.54 | 09-17 16:32 | `/ capMult - 1.0` ✅ |
| `d781672` v0.55 | 09-17 16:46 | `/ capMult - 1.0` ✅ |
| `135c4e4` v0.56 | 09-17 17:01 | `/ capMult - 1.0` ✅ |
| `4770fae` v0.57 | 09-17 17:14 | `/ capMult - 1.0` ✅ |
| `2a2b592` | 09-17 17:18 | `/ capMult - 1.0` ✅ |
| **`backup-v100-20260918-175628`** | **09-18 17:56** | **`- 1.0`** ❌ |
| `62505c5` v1.05 | 09-18 19:31 | `- 1.0` ❌ |

⇒ **回归发生在一个未提交的改动里（v0.58–v1.00 之间），v1.05 把它一并继承了。**

**实测后果（21:27 会话，面板 160Hz，日志原文）：**

```
Reflex FLIP cap = 159 fps (6289us) - panel 160Hz, 4 flips per real frame => ~636 presented fps
```

**159 × 4 = 636 present fps 对着 160Hz 面板 ⇒ 超发 298%。**
present 队列积压 ⇒ SL pacer 节奏崩 ⇒ **画面不再推进，而帧计数照涨**。
这正是"4x 一开始就冻结 + 左上角有帧数"。

**为什么 2x 是"闪烁"、4x 是"冻结"**：2x 超发 98%，4x 超发 298%。
同一个 bug，倍率放大它。**也解释了 v1.04 的"修了 capMult 却照旧冻结" —— v1.04 改的是 capMult 的
来源，而 capFps 里根本没有 capMult。**

### 12.2 真凶二：v1.02c 的相机历史有读端、没有写端

```cpp
// 声明（Streamline.cpp，紧邻读端）
static Matrix s_prevCamView{};
static Matrix s_prevCamProj{};
static float  s_prevCamEye[3] = { 0.0f, 0.0f, 0.0f };
static bool   s_hasPrevCam = false;

// 读端
if (camCurOk && s_hasPrevCam) {
    camPrevOk = rebuildViewProj(s_prevCamView, s_prevCamEye, s_prevCamProj, camPrevVP) && ...;
}
```

**全文只有这两处。`s_prevCamView` / `s_prevCamProj` / `s_prevCamEye` 从未被赋值，
`s_hasPrevCam` 从未被设为 true。**

⇒ `camPrevOk` 每一帧、每一次运行都是 false。
⇒ 日志实证（不是推理）：`cam(ok/inv)=121/0` 健康，而 `camPrev(ok/used)=0/0` 全零。

**修法**：在 `camPrevOk` 计算之后写入历史（读在前、写在后，顺序正确）：

```cpp
if (camCurOk) {
    s_prevCamView = a_fb.CameraView;
    s_prevCamProj = a_fb.CameraProj;
    s_prevCamEye[0] = a_fb.CameraPosAdjust[0];
    s_prevCamEye[1] = a_fb.CameraPosAdjust[1];
    s_prevCamEye[2] = a_fb.CameraPosAdjust[2];
    s_hasPrevCam = true;
}
```

### 12.3 附带修正：仓库 INI 模板还是 v1.03 的"让权"契约

`SKSE/Plugins/DynamicShaderFrameGen.ini`（仓库模板）停在 v1.03，
而部署副本是 v1.05 的正确契约。**CMakeLists:105-121 每次链接后
`copy_if_different` 会把模板推回部署目录** ⇒ 下一次构建就会把正确说明覆盖成
"unlocker 在场时本插件停止写入"的错误指导。

**已核对：两者【值行差异 = 0】（48 行值完全相同，只差注释），
所以同步不改变任何实际配置。** 模板已同步为 v1.05 文案（md5 `ed9655ad`）。

### 12.4 v1.06 改动清单

| 文件 | 改动 |
|---|---|
| `Streamline.cpp` | 公式恢复 `/ static_cast<double>(capMult)` + 新增超发自检 warn |
| `Streamline.cpp` | 新增相机历史写入端（6 行）+ 逐字说明注释 |
| `Streamline.cpp` | banner `v1.05` → `v1.06` |
| `SKSE/Plugins/*.ini` | 仓库模板同步为 v1.05 契约（值行不变）|
| `tools/patch_v106_capfps.py` | 新增，带断言 + 幂等守卫 + post-condition |
| `tools/analyze_session.py` | 新增，一键日志三诊 |

**产物**：`Streamline.cpp` 115,550 → 117,845 B（2241 CRLF / 0 bare）
**DLL**：1,326,080 B，md5 `54cdc904abaef3fabd4a18bf23a2afb8`（**build == MO2 部署一致**）
**DLL 内校验**：`diag active v1.06`=1、`diag active v1.05`=**0**、
`Reflex cap OVER-SUBMIT`=1（自检断言）；`handed to the external unlocker`=0

### 12.5 ★ 修复的预期效果（可对照验证）

| | 修复前 | 修复后 |
|---|---|---|
| `Reflex FLIP cap` 日志行 | `159 fps (6289us)` | **`39 fps (25641us)`** |
| present fps | 636 | **156** |
| 对 160Hz 面板 | 超发 298% | **余量 4 fps ✅** |

**⇒ 用户下次开游戏，只看这一行就知道修复有没有生效：**
```
[Streamline] Reflex FLIP cap = 39 fps (25641us) - panel 160Hz, 4 flips per real frame => ~156 presented fps
```
**如果这一行还是 159 ⇒ DLL 没换上去。**

### 12.6 一条命令看懂日志（新增工具）

```
python tools/analyze_session.py
```

五项检查，全部取日志原文数字：

1. **REFLEX CAP** —— `capFps × mult` 是否超过面板刷新率
2. **PRESENT** —— `presentAge` / 聚焦后的 `silent`（自动排除聚焦前的等待）
3. **GPU PROGRESS** —— `fence` 是否推进
4. **CAMERA MOTION** —— `clipDev`（**看最后一个心跳，不看最大值**）+
   `camPrev(ok/used)`
5. **MULTIPLIER** —— `mult(acc/pres)` 是否自洽

**跑在 21:27 那份日志上，它自己就报出了三个问题**（超发 298% / 后期 clipDev 回落
到 identity / camPrev 未填充）—— 也就是说这份日志本身已经说了全部答案，
只是没有人用对的判据去读。

### 12.7 两个"差点又犯"的判据错误（记下来）

1. **用 `max(clipDev)` 判断相机是否在动是错的。** 21:27 的 `max=243.96`，
   但**最后三个心跳全是 0.000061** —— 用 max 会判"健康"，实际是"后期冻结"。
   **判据必须取最后一次采样。**
2. **用整个 watchdog 判断 stall 是错的。** 它是追加式的，跨所有启动；
   `presentAge=19400ms` 属于 19:16 那次。**必须先切出最后一次运行**
   （最后一个 `frames=1` 之后）。
3. **`silent` 在获得焦点那一刻必然很大**（累积了聚焦前的等待），
   21:27 那条是 `stage=enter frames=2 silent=21031ms`。
   **必须要求"前一条也是 focus=1"。**

### 12.8 仍未解决 / 未验证（不假装）

- **修复是否真的止住冻结：未验证**（我无法运行游戏）。判据是 12.5 那一行。
- **`famRej=418`（source-lock 族指纹的永久拒绝）**：2.1% 的到达被拒，
  `lock(pub/hold/re/still)=19445/4338/3920/0`（`still=0` ⇒ 从未触发"流断了"）。
  它是否会锁死错误族，需要一次"玩家确实在移动"的运行才能判定。
  **未改动** —— v1.00 写它是为了修 v0.93 的 CTD，动它有风险。
- **Modex 闪退**：必须在 MO2 GUI 手动取消勾选，我无法操作。
- **RTX 20/30 系**：一行未写。
- **DLSS5**：一行未改。

### 12.9 v1.06 的提交与验证（2026-09-18 21:47）

**提交** `c0f8422`，tag `v1.06`。

| 校验项 | 结果 |
|---|---|
| `build/NINJA/DynamicShaderFrameGen.dll` | 1,326,080 B，md5 `54cdc904abaef3fabd4a18bf23a2afb8` |
| `E:/EJ/mod/mods/.../SKSE/Plugins/…dll` | 1,326,080 B，md5 `54cdc904abaef3fabd4a18bf23a2afb8` |
| `cmp` 逐字节 | **IDENTICAL**（build == 部署）|
| DLL 内 `diag active v1.06` / `v1.05` | **1 / 0** |
| DLL 内 `Reflex cap OVER-SUBMIT` | **1**（自检已进产物）|
| DLL 内 `handed to the external unlocker` | **0**（v1.03 让权代码确已清除）|
| INI（仓库模板 vs 部署） | 字节相同，md5 `ed9655ad2bd0d2576d7f7e9d200a3f4c` |
| 游戏本体 `data/SKSE/Plugins/` | **无任何 DFG 文件**（只部署在 MOD 文件夹）|
| 工作区未跟踪文件 | **0**（`.bak-*` / `reports/` / `_removed_*/` 已入 `.gitignore`）|
| v1.06 落盘位置 | `Streamline.cpp:2106`（除数）、`Streamline.cpp:742`（相机写端）|

**备份** `src/backup-v1.06-final-20260918-2147/`（`MANIFEST.txt` 内含上述全部 md5，
以及两处修复的行号与原文）。

**★ 交付时仍未验证的**：冻结是否真的止住。我无法运行游戏。
唯一判据是 12.5 的那一行日志 —— `Reflex FLIP cap = 39 fps (25641us)`。

---

## 第 13 章：速查表（2026-09-18 从工作区 MEMORY.md 迁入，原处已超限）

**迁入原因**：工作区 `MEMORY.md` 涨到 16,545 字符（上限 3,000），被系统截断。
按它自己第 3 行的设计「本 MEMORY.md 只留速查」，**速查内容全部落到这里**，
MEMORY.md 收缩为索引 + 最高优先级事实。以下内容与 MEMORY.md 原有条目逐条等价。

### 13.1 XRAY 心跳字段速查（`DynamicShaderFrameGen.log` 里的 `[XRAY]` 行）

| 字段 | 含义 | 健康判据 |
|---|---|---|
| `lock(pub/hold/re/still)` | source-lock 发布/持有/重采/静默计数 | `still` 上涨 = 流断了；恒 0 = 从未触发该分支 |
| `proj00=` / `famRej=` | 当前锁定族的投影指纹 / 被拒异族数 | `proj00=0.149184` 是 WORLD 族；`0.8391` 是 MENU 族 |
| `cam(ok/inv)` | 相机数据有效/无效帧数 | `inv` 上涨 = 数据源问题 |
| `camPrev(ok/used)` | v1.02c 重建的 prev 可用数 / 实际使用数 | **`0/0` = 写端缺失（v1.06 修）；`used` 应接近 `ok`** |
| `clipDev` / `clipDevMax` | `max|I - clipToPrevClip|` | **运动中必须明显 >0；恒 0.000061 = 相机项被丢（identity）** |
| `engPrevEqCur=N/N` + `engPrevDiffers=N` | 引擎 prev 与 cur 的比较计数 | **两值同步增长到同一数字 = 引擎 prev 是僵死常量** |
| `det(min/max)` | `det3(clipToPrev)` | `0.001` = 菜单族，`→1` = 同族 |
| `reproj src=` | 重投影来源 | `fixed` = v0.88 重建（正常）/ `derived` / `engine` |
| `blocked=` / `unblocked=` | `SetDLSSGOptions` 被跳过/执行的帧数 | `blocked` 应 ≈ 0 |
| `mult(acc/pres)` | 实测接受倍数 / 上报倍数 | 两者应自洽 |
| `snapArrivals` / `frameSerial` | 到达次数 / 帧序号 | 比率 >1 说明同一 perFrame 缓冲每帧被多相机重复写入（21:27 = 12.3） |

**★ 判据铁律：只有实测字段能当结论。** `mult(pres)` 是"请求"，`mult(acc)` 才是"事实"。

### 13.2 source-lock 的判据边界

| 常量 | 值 | 含义 |
|---|---|---|
| `kCamStillTol` | 90 | 判定"相机停住"的阈值 |
| `kCamStepTol` | 50 | 判定"相机移动"的阈值 —— 即 `!continues` 的边界 |
| 族指纹比值窗 | ±2% | 同量级时用 `ratio ∈ (0.98, 1.02)`；量级不同直接判异族 |

异族分支**永久拒绝、无夺回机制**（`FrameGen.cpp:886-898`，`return false`）。

### 13.3 历史根因清单（我已犯过、别重复）

| 版本 | 根因 |
|---|---|
| v0.83 / v0.84 | `snapFrozenRepeats` 只 `++` 没有 `=0` |
| v0.88 | 引擎 view 矩阵无平移项 |
| v0.89 | 误把"shape 拒绝"当拦截器（`// NO return false`，它只是计数器）|
| v0.91 | C7595 |
| v0.92 | `det3` 结构性盲区（只读 3×3 = 只看旋转，看不见平移）|
| v0.93 | 闸门只计数不否决 |
| v0.94 | source-lock 无条件 re-acquire ⇒ 菜单相机夺流 |
| v0.95 | world-camera 过滤器失败 |
| v0.96 | 移除 `Fader Menu` 导致**进不去游戏**（已回退，**别删**）|
| v1.00 | 族指纹定案（菜单/世界两族）|
| v1.02c | 重建 prev（但**只写了读端**）|
| v1.03 | 让权给外部解锁器（零初始化 `max` = 写常量 ⇒ 每帧覆盖 4x）|
| v1.04 | 修 `capMult` 来源（真修了，但**不是正在追的问题**）|
| **v1.06** | **Reflex cap 丢除数 + 相机历史无写端** |

### 13.4 两条"名字会骗人"的诊断铁律

1. **`stage=` 是「最后写入的名字」，不是「卡住的位置」。**
   watchdog 显示 `d3d11 Wait` 达 19.7 秒，实际阻塞在它之后的 `Present(0)` ——
   `m_stage` 写在阻塞调用**之前**，下一次写要等下一帧入口（永不到来）。
   ⇒ 用 `g_presentEnteredMs` + watchdog `presentAge=` 按**时间戳年龄**归因，不看名字。
2. **头文件 `extern` 只能放命名空间级。** 放类内 ⇒ `error C2071: 格式错误的存储类`。
   全部编译单元一起 FAILED 时**先查头文件**。

### 13.5 备份里可能有"你以为丢了的"配置

`DLSSG-Transfusion.json` 曾在当前部署里不存在，但在 6 个备份目录里都有。
**⇒ 文件"消失"时先翻 `/d/workbuddy2/backup/`，不要凭空重建。**
相关：`transfusion_proxy_dup_20260917_182050`（含代理 dll + json）、
`transfusion_uir_off_20260917_193147`、`transfusion_flipmetering`。

### 13.6 v1.06 终版备份位置

`src/backup-v1.06-final-20260918-2147/`（含 `MANIFEST.txt` + `built_DLL.bin` +
`deployed_DLL.bin` + `deployed.ini` + 三个源文件 + 补丁脚本 + 分析脚本）。

## 第 14 章：v1.07b —— 第三成因：相机族锁**没有释放路径**（2026-09-18 22:24）

### 14.1 先确认 v1.06 的两处修复**真的生效了**（22:02 日志实锤）

在追第三成因之前必须先排除"v1.06 没修好"。22:02 那份日志逐字证明**两处都生效**：

```
[22:02:00.649] [XRAY] diag active v1.06 (compiled Sep 18 2026 21:38:18)
[22:02:00.676] [Streamline] Reflex FLIP cap = 39 fps (25641us) - panel 160Hz, 4 flips per real frame => ~156 presented fps
camPrev(ok/used)=1/90
Transfusion: DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
```

- `39 fps / 156 presented` ⇒ 反射率除数回来了，相对 160Hz 面板还有 4fps 余量（v1.05 曾是 `159 fps / 636`）。
- `camPrev(ok/used)=1/90` ⇒ v1.06 补的相机历史**写端**在工作（v1.05 是 `0/0`）。
- `presentation count: 4x` ⇒ 4 倍帧生成**确实在跑**。

⇒ **"没有出现 4 倍" 是错觉；4 倍在跑，是画面没动。** 所以一定存在第三条成因。

### 14.2 第三成因：族锁只有赋值，没有任何一处清零

`snapLockHave` / `snapLockProjValid` / `snapLockProj00` 三个状态**全项目只被赋 true，没有一处赋 false**：

```
grep -rn 'snapLockHave\|snapLockProjValid\|snapLockProj00' src/FrameGen.cpp
-> snapLockHave      置 true（v1.07b 后 :894 / :981）          无 false
-> snapLockProjValid 置 true（:996）                          无 false
-> snapLockProj00    赋值（:995）                              无重置
```

而 v1.00 的注释自己写着「**异族永不 re-acquire**」（`FrameGen.cpp:903-908`）——
于是这个状态机**没有出锁转换**。一旦锁落到错的族，整局都出不来。

### 14.3 走锁的棘轮：v1.03 的"量级逃逸"

`FrameGen.cpp` v1.03 在比率测试**之前**加了一条：

```cpp
const bool unitProj  = 0.995f < proj00         && proj00         < 1.005f;
const bool lockUnit  = 0.995f < snapLockProj00 && snapLockProj00 < 1.005f;
if (unitProj != lockUnit) sameFamily = true;      // <-- 一整类的到达被无条件放行
```

再叠上 accept 处的刷新（`:995-996  snapLockProj00 = proj00;`）⇒ **锁会"走"**。
22:02 日志逐字记录了这次行走：

```
#1  acquire  proj00=0.149184                -> lock 0.149184   （世界相机抢到了第一把）
#2  esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
#4  esc 0.149184 vs locked 1.0      -> adopt -> lock 0.149184
#11 esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
#13 esc 0.149184 vs locked 1.0      -> adopt -> lock 0.149184
#20 esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
...                                          -> lock 0.8391    （3D 菜单族）
```

锁读到 1.0（单位投影）时，**任何非单位到达都算"合法第二相机"**，包括 0.8391。
锁一旦变成 0.8391，比率就是 `0.149184/0.8391 = 0.178` ⇒ 世界相机**永久被拒**。
日志尾部的证据：`lock(pub/hold/re/still)=11821/2725/2416/0  proj00=0.8391  famRej=309`，
且 `menu=857 world=94` —— **已经在世界里渲染了，锁还在菜单族手上。**

**注意 `still=0` 这个数字**：异族分支在 `return false` 之前**完全不计数**
（`snapLockStill` 只在同族步进断裂那条路加），所以"锁死了多久"这个量在日志里读不出来。
这是本轮顺手修掉的**仪表**缺陷，不是主因。

### 14.4 v1.07b 的改动（两处交付 + 一处**写出来又丢掉**）

| # | 位置 | 改动 | 定性 |
|---|---|---|---|
| 1 | `FrameGen.cpp:862-888` | **删除 v1.03 量级逃逸**，`±2%` 比率测试独立成立 | **承重** |
| 2 | `Streamline.cpp:507` / `:1217` 抬高，`FrameGen.cpp:838-851` 消费 | 新增 **reset-edge 释放**：菜单开/关边沿把族锁清掉 | 补救 |
| 3 | — | still 阈值重采 —— **写过、量过、丢掉** | 见 14.5 |
| 4 | `FrameGen.cpp:915` | 异族分支补 `++snapLockStill`，让 `still=N/M` 报真话 | 仪表 |
| 5 | `Streamline.cpp:1577` | 横幅 `v1.06` → **`v1.07b`** | 仪表 |
| 6 | `FrameGen.h:336-337` | 新增 `snapLockReleasePending` / `snapLockReleased` | 支撑 2 |

**edit 1 为什么是承重的**：22:02 的 `#1 acquire proj00=0.149184` 说明**锁本来就在世界族手里**，
是逃逸把它走掉的。删掉逃逸，锁**根本到不了 0.8391**。
回归 C1 直接证明：只删逃逸、**不带任何释放路径**，结果就已经是 `proj00=0.149184`、
`world-refusals=0` —— 释放对这份日志**零贡献**。

**edit 2 为什么还是要留**：它治的是**另一条入口**——"开局第一把锁就被菜单族拿到"。
那条路上 v1.03..v1.06 永远出不来（v1.00 明令异族不得 re-acquire）。回归 C2 里
只删逃逸的表现是 `pub=0 world-refusals=744`（**一个快照都发布不出去**），加上释放后恢复。

### 14.5 ★★ 被丢掉的 edit 3：still 阈值重采（附回归量化）

我第一版 v1.07 还加了第三条释放路径：异族连续失败 `kCamStillTol(90)` 次就释放并采纳当前到达。
**回归量出它不是修复**：

```
[C2b] 被弃草稿（隔离，无边缘）    locked proj00=1         pub=700  released=1  world-refusals=744
```

`proj00=1` —— 它**采纳了单位正交族**。原因很直白：那条分支采纳的是
"**恰好第 90 次**非连续的那个到达"，而 A/B 两个异族交替到达时，第 90 次是 A 还是 B
**取决于到达顺序**。⇒ 它只是**用错族换错族**，而单位正交族的 `clipToPrev` 是 identity，
**恰恰就是冻结本身**。

更要命的是它**重开了 v1.00 故意关上的门**（`FrameGen.cpp:903-908` 原文）：

> v0.94 re-acquired unconditionally after kCamStillTol non-continuing arrivals, so a
> foreign camera that arrived monotonically for 90 frames was adopted and then
> "continued" itself forever. **That is the freeze.** Only an arrival from the SAME
> family may take over.

⇒ 按用户"**哪些已经出错了 就不要再犯**"的要求，edit 3 **已撤回**（`patch_v107b_dropstill.py`），
只在回归里留作**反证**，防止下次有人再把它加回来。
**有边缘时**的两个数字恰好量化了它的害处：`pub=700`（草稿）vs `372`（v1.07b），
差值 **328 帧**就是"单位族在边沿之前一直占着 `frameBufferCopy`"。

### 14.6 残留：释放后的竞态（**已知，故意不修**）

释放是"清锁 → 让**下一个到达者**建立新族"。若菜单族在释放后**先到**，锁又回到 0.8391：

```
[C3] NEW 菜单族先到且持续到达   locked proj00=0.8391  famrej=1488  released=1  world-refusals=744
```

而且**任何**"异族持锁太久就释放"的设计都救不了它——异族自己位置恒定 ⇒ `continues` 恒真
⇒ `still` 每帧被清零，阈值永远到不了。

**要真关掉这个竞态，需要的是"属性判据"而不是"顺序"**：例如"某个指纹一旦被判为菜单族，
在没有菜单打开的帧里就不许发布"。**本轮故意不做**——v1.07b 已经修掉的是
**22:02 实际发生的那一个**（日志 `#1` 是世界族夺锁），再叠一个未验证的判据就是又一次赌博。
日志里 `proj00=` 这一行**一行就能判定**是否落进这个残留。

**不要拿 `w != 1`（non-affine）做判据**：v0.89 的注释（`FrameGen.cpp:654-683`）已经实测过——
被 `[3][3] != 1` 丢掉的那一族定位**在 glide**（`pos=(-50.0,880.7,94.3)`，正是世界相机），
而通过的是**冻结在 `(-160,160,128)`** 的单位族。世界相机与菜单族**都是非仿射**，`w` 区分不了。

### 14.7 v1.07b 的提交与验证表

| 项 | 值 |
|---|---|
| 提交 | `01ce63c` |
| tag | `v1.07b` |
| DLL | 1,325,568 B，md5 `ae44a128c07f02d7d6d70f2a1c76452d` |
| 构建 == 部署 | `cmp` IDENTICAL（`build/NINJA/` 与 `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/`）|
| 备份 | `src/backup-v1.07b-20260918-222454/` |
| 编译 | `BUILD SUCCESS`，无 `error C/LNK` |

DLL 内字符串（**"删掉的串必须为 0"，不只验证"加的串存在"**）：

| 串 | 计数 | 含义 |
|---|---|---|
| `diag active v1.07b` | 1 | 横幅已升 |
| `diag active v1.07 ` | **0** | 旧横幅已不存在 |
| `lock RELEASED on the reset edge` | 1 | 边沿释放已进产物 |
| `lock RELEASED after` | **0** | still 重采**已不在产物里** |
| `magnitude classes differ` | **0** | 量级逃逸**已不在产物里** |
| `non-affine w=` | 1 | v0.89 的非破坏性观测仍在 |

离线回归 `tools/regress_v107_lockrelease.py`：**RESULT OK**

| 用例 | locked `proj00` | world-refusals | released | pub |
|---|---|---|---|---|
| C1 OLD v1.03..v1.06 | **0.8391** | 743 | 0 | 1489 |
| C1 只删逃逸 | **0.149184** | **0** | 0 | 744 |
| C1 NEW v1.07b | 0.149184 | 0 | 1 | 744 |
| C2 只删逃逸（菜单族预置持锁） | 0.8391 | 744 | 0 | **0** |
| C2 NEW v1.07b | 0.149184 | 372 | 1 | 372 |
| C2b 被弃草稿（隔离） | **1** | 744 | 1 | 700 |
| C3 NEW 菜单族持续到达 | 0.8391 | 744 | 1 | 744 |
| C4 连续世界流 200 帧 | 0.149184 | 0 | 0 | 200 |
| C5a 仅 A/B，只删逃逸 | 0.149184 | 0 | 0 | 6 |
| C5b 仅 A/B，OLD | **1** | 0 | 0 | 12 |

C5 是**逃逸就是行走器**的最干净证明：完全不引入菜单族，只让 A/B 交替到达，
逃逸就把锁翻到单位族（`A/B only, OLD -> proj00=1`）。

### 14.8 本轮新增/修改的工具

- **新增** `tools/patch_v107_lockrelease.py` —— v1.07（含已弃用的 edit 3）的补丁脚本，
  逐条锚点 `count==1`、幂等标记、行尾归一化、9 项 post-condition、落盘后回读。
- **新增** `tools/patch_v107b_dropstill.py` —— 撤回 edit 3 的补丁脚本（8 项 post-condition）。
- **新增** `tools/regress_v107_lockrelease.py` —— 建模 A(world 0.149184, glide) /
  B(unit 1.0, 恒定) / C(menu 0.8391, 恒定) 三个族，C1–C5 五组用例，
  `OLD` / `ESCAPE_GONE` / `NEW` / `DRAFT_STILL` 四种构建组合。
- **修改** `tools/analyze_session.py`：
  1. **版本横幅改成硬比对**（`EXPECTED_BUILD`）。旧正则 `v[\d.]+` **连 `v1.07b` 都匹配不到**——
     它只吃数字和小数点。现在 `v[\d.a-z]+`，且与期望版本不一致直接报 PROBLEM。
  2. **第 4 项 CAMERA MOTION 剔除 `frames=1` 首个样本**：日志原本把开机加载
     `presentAge=19199ms` 报成 "a real hang"，修后报
     `presentAge max=432ms ... the render loop never stalled`。
  3. **第 6 项 CAMERA FAMILY LOCK 判据改写**：旧判据要求 `still==0`，
     而 `still` 只在 v1.06（一个从不加它的版本）里恒 0；v1.07b 里它会涨。
     新判据：`famRej` 大 + **世界族持锁** = **健康**（不变式在工作）；
     `famRej` 大 + **0 次释放** + 确有菜单→世界转换 = 问题。
     另新增 `menuFrames` 输出与释放事件回显。

### 14.9 一行命令自检（下次开游戏**只看这个**）

```
python tools/analyze_session.py
```

判据（三条，缺一不可）：

1. `build  v1.07b`，**不是** `PROBLEM: this log was written by ...`
2. 第 6 项 `proj00=` 是 **`0.149184`**（世界族持锁）——**不是 `0.8391`**
3. 第 6 项 `release events: N` 中 **N ≥ 1**（菜单→世界转换触发了释放）

若第 2 条是 `0.8391` ⇒ 落进了 14.6 的残留（或 DLL 没换上去）。
若第 1 条报版本不符 ⇒ **DLL 根本没换上去**，后面所有结论都不作数。

### 14.10 仍未验证（不假装）

- **v1.07b 是否真止住冻结**：**未知**。我无法运行游戏。
- **§14.6 的竞态**：故意未修。
- **Modex 闪退**（第三方 `Modex::UIManager::MainWndProc`）：须在 MO2 GUI 手动取消勾选；
  **验证冻结前必须隔离它**，否则结论不可信。
- **RTX 20/30 系**：一行未写（`grep -i xess` = 0，需 sm86/sm75 内核）。
- **DLSS5**：代码在 `src/NeuralRendering/`（NGX Feature 18，自有实现），**未上机验证**。

### 14.11 ★ 一个长期误判的根因：`core.autocrlf=true`

我在本文件第 6 章写过"12 个源文件行尾各不相同"。**这个结论部分是我自己造成的**：

- 仓库 **`core.autocrlf=true`**，且**没有 `.gitattributes`**；
- ⇒ `git checkout --` 会把仓库里的 LF 规范形式**在落盘时转成 CRLF**；
- 于是"实测行尾"其实是「git 规范化」+「补丁脚本按探测结果插入」共同作用的**动态**结果。
- 实证：`git checkout -- src/FrameGen.cpp` 后，该文件从 **LF（1364 bare_LF）**
  变成 **CRLF（1364 CRLF）**，md5 从 `0363c183…` 变成 `d5c4cf34…`，
  而 `git status` 认为工作树**干净**。
- 2026-09-18 22:24 实测（当前真实值）：
  `FrameGen.cpp` **CRLF 1414 / bare_LF 0**、`FrameGen.h` CRLF 366、`Streamline.cpp` CRLF 2254、
  `Streamline.h` CRLF 384、**`DX12SwapChain.cpp` 纯 LF 1806**、`main.cpp` MIXED(162/7)。

**结论：行尾永远逐文件实测，补丁脚本必须自动探测，不要凭记忆也不要写死。**

---

## 第 15 章：22:02 日志重读 —— 第 14 章的结论被它自己的日志否掉了一半

这一章不是新发现，是**自检**。用户问“到底能不能解决”，于是我把 22:02 那份日志按
**冻结的机械成因**（而不是按我上一轮的假设）重新走了一遍。结果：第 14 章把族锁当成第三成因，
**这个断言被日志自己的计数否掉了**。

### 15.1 第一件：族锁在 22:02 **没有** 堵住发布通道

锁确实在致病路径上 —— `FrameGen.cpp:991` 的 `frameBufferCopy = a_src` 是**唯一**
向 DLSS-G 发布相机的写入点，而锁块内的 `return false`（当前在 `FrameGen.cpp:947`）
会绕过它。所以锁调度的是“哪一帧的相机被发布”，而不是反投影路径本身
（`Streamline.cpp:666` 的注释就是这个意思：反投影不再查询它）。

**但 22:02 的计数说明发布通道是开的**：

```
snap(acc/jmp/re/zero/arr/frozen/shape/rejPct)=11821/309/0/0/12130/0/9196 75.8%
```

12130 次到达，**11821 次被发布（97%）**，只有 309 次被拒。而那 309 次正是**做对了事**：

```
[22:02:21] [CAM] #8048 family rejected: proj00=0.8391 locked=0.149184 ratio=5.6246 \
             pos=(-243.0,-415.3,118.6) dist=1258.1 - another render pass, never re-acquires
```

锁在**世界族 0.149184**，拒掉菜单族 0.8391 —— 这正是 v1.00 想要的行为。

> **方法论铁律（新）：一个状态机的输出被计数证明是通的，和“这个状态机是故障点”
> 不能同时成立。发布计数是最便宜的反证。**

### 15.2 第二件：被发布的相机**原地不动**

```
[CAM] acc #10255 pos=(-243.05,-415.31,118.56) move=0.0000 path=72.92
[CAM] acc #10783 pos=(-243.05,-415.31,118.56) move=0.0000 path=72.92
[CAM] acc #11541 pos=(-285.88,-410.36,96.87)  move=0.0000 path=121.33
[CAM] acc #11801 pos=(-285.88,-410.36,96.87)  move=0.0000 path=121.33
```

- `move`（逐帧位移）连续为 **0.0000**；`pos` 在 1e-2 精度下**几十秒不变**；
- `path` 只从 72.92 爬到 136.60（跨几十秒），**全部增量来自两次槽位切换**
  （`#10255→#10976` 与 `#11366→#11996`），不是连续运动；
- `cur == prev` ⇒ `clipToPrev = I`（心跳 `clipDev=0.000015`、`clipDevMax=0.0000`）
  ⇒ **DLSS-G 生成的帧是当前帧的副本 ⇒ 画面不可能前进。这就是“冻结”的机械定义。**
- 心跳 `pos == prevPos` 逐字相同，与之一致。

### 15.3 第三件：那份相机矩阵**形状是坏的**

`[CAM] raw #10801` 原文（未删节）：

```
ProjUnj      | 0.8391 -0 0 0 | -0 0.471993 0 0 | 0 0 0 1 | 0 0 -0.0666638 0.0666667
ViewProjUnj  | 1.19174 0.00466757 -5.41947e-13 0
             | 1.24468e-05 -0.00317798 2.11867 0
             | -0.00391672 1.00003 0.00150006 -15.0006
             | -0.00391655 0.999991 0.0015 0
ViewInv      | 0.999992 5.87483e-06 -0.00391655 -0
             | 0.00391656 -0.00149999 0.999991 -0
             | -4.54747e-13 0.999999 0.0015 -0
             | -0 -0 -0 1
```

自洽性检查（这段数字是我算的，不是我记的结论）：

- `ProjUnj[0][0] / ProjUnj[1][1] = 0.8391 / 0.471993 = 1.7775 = 16/9`
  ⇒ **`ProjUnj` 是一个干净的真投影**（宽高比对得上 3840x2160）。
- 但 `ProjUnj[3][3] = 0.0666667 = 1/15.0006`，而真透视投影的 `[3][3]` 应为 **0**；
  `[2][2]` 应为 `f/(f-n)` 却是 **0**。⇒ 矩阵即使是真的，**存储布局也和读取方假设对不上**。
- `ViewProjUnj` 的 w 行是 `(-0.00391655, 0.999991, 0.0015, 0)`，**不是 `[0,0,0,1]`**；`detProj = 0`。
- 逐元素对照：`ViewProjUnj` 第 3 行 **等于 `View`（即 `ViewInv` 的逆）的第 2 行**；
  `ViewProjUnj[2][3] = -15.0006` 而 `View` 该位为 0。
  它既不是 `Proj @ View`，也不是 `View @ Proj`，也不是两者的转置（三种我都算过）。
- **`FrameGen.h:326-332` 的 v0.86 注释早就写下了同一段数字**：
  > `row3=(-0.00391655,0.999991,0.0015,0) ... not a camera at all, but a
  >  mis-offset read of the perFrame constant buffer`
  **我把它记进了 header，然后在它上面继续叠启发式（族指纹、量级逃逸、释放路径），
  从来没去查那个读。**

### 15.4 但 15.2 / 15.3 **不能定案** —— 缺的是一个数据点，不是又一个猜想

`move=0.0000` **只有在玩家在走的时候才是错误**。这份日志里玩家几乎没动
（`path` 跨几十秒只涨了 63.7，且全部由槽位切换贡献）。

`FrameGen.cpp:1001-1003`（v0.68 埋的探针）注释原文就是为这一刻写的：

> “若玩家在走而这里 move/path 恒为 0.000，则根因在捕获层
> （读到的相机数据不跟踪真实相机），任何重投影侧的修法都救不了。”

**⇒ 这份日志恰好没有回答它。缺的不是又一个猜想，是一个数据点。**

### 15.5 唯一缺的实验（10 秒，一次）与三条判据

进游戏 → 4x 跑起来 → **按住 W 走约 10 秒并转视角** → 退出。只看三行：

| 判据 | 读数 | 根因 | 下一步 |
|---|---|---|---|
| **A** | `move` 明显非 0 且 `clipDev` 明显 > 0 | 相机链是好的 | 冻结在呈现/配速侧（pacer / Present），去查那条 |
| **B** | 在走但 `move`≈0、`path`≈0 | **捕获层**读到的相机不跟玩家 | 查 perFrame 镜像的偏移/布局（15.3 的 `[3][3]=0.0667`、w 行不是 `[0,0,0,1]` 就是线索） |
| **C** | `move` 大但 `clipToPrev`≈I | 重建/历史把运动丢了 | 查 `rebuildViewProj`（`Streamline.cpp:629`）与 `s_prevVP` 推进（`1022-1050`） |

三种结果对应三个**不同的**根因，每一种都直接指向一个具体例程，不需再猜。

### 15.6 对第 14 章的正式更正

第 14 章把“族锁无释放路径”列为第三条成因，并据此发布 v1.07b。**更正如下**：

| 14 章的说法 | 更正后 |
|---|---|
| 删除 v1.03 量级逃逸 | **仍然正确且必要**。它确实是那把锁被“走”到 0.8391 的棘轮，逼近过程有逐帧日志为证（`#2 esc 1.0 → adopt`、`#4 esc 0.149184 → adopt`） |
| 新增 reset-edge 释放 | **无害但未证明承重**（C1 回归里只删逃逸就已经终于 0.149184） |
| “族锁 = 22:02 冻结的成因” | **被日志自己否掉**：11821/12130 发布成功，309 次拒绝全部是对菜单族的正确拒绝 |

**⇒ v1.07b 保留（它修的是真 bug），但不能再声称它修的是冻结。**

### 15.7 四条可复用的方法论

1. **“修了一个真错误” ≠ “修的是正在追的问题”。**（v1.04 已建，本章再次验证）
2. **状态机的输出计数是它最便宜的反证。**发布计数通着，就不能说它堵住了下游。
3. **一个探针只能在它的前提成立时读。**`move=0` 的诊断价值完全取决于“玩家在不在走”——
   而这个前提本身**必须从日志里读出来**，不能假设。
4. **读到一个被反复记录的异常数字，先查它的来源，不要在它上面叠启发式。**
   `[3][3]=0.0667` / w 行 ≠ `[0,0,0,1]` 已经被 v0.86 记了一次，我在它上面叠了三代启发式。


## 第 16 章：v1.07c —— 重投影矩阵的逆取自一台**没有平移**的相机（2026-09-18 23:22）

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

1. ~~**取逆的源与 `prev` 同构**（唯一的功能修复）~~ **★ 第 17 章已证明这是一次空操作，本条作废**：
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

1. **`norm()` 二次展开**：后置检查的 needle 里写了 `\r\n`，而 `norm()` 又把 `\n` 展开成
   `\r\n` ⇒ 变成 `\r\r\n`，永远匹配不到。**教训：needle 一律写 `\n`。**
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

### 16.12 起草时我差点写错的一条：「jitter 已核实为 0，不是待查项」

起草版想当然地把心跳里的 `jitter=` 当成"实测引擎 jitter，8 条全 0 ⇒ 与 jitter 无关，闭环"。
**按 16.11 刚立的原则回头一查，结论相反：那不是读数，是死字段的初始值。**

全工程非备份源码里搜这两个符号：

```
$ grep -rn "jitterX\|jitterY" src/ --include=*.cpp --include=*.h | grep -v src/backup-
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
SL 路径读的却是这个死字段。
**★ 这里我原本留的探针是「下次运行先看 `mvecScale` 在运动中是否变化」—— 那句作废：
`mvecScale` 被 `MvecScaleOverride=1.00` 钉死、恒为 1，不能作门。有效探针见 16.14。**

### 16.13 判据 3 的阈值取 `1e-3`，不要取 0

判据 3 不能写"≈0"。日志实测下限：`clipDev=0.000061` 出现 7 次、`0.000023` 出现 2 次；
而 Transfusion 打印的合法 identity 帧 `rows=[0.99999994 …]` 与 1 的偏差是 6e-8 量级
⇒ **identity 的真实下限在 1e-5 量级**。验收写 **`clipDev < 1e-3`** 即为通过，
不需要新字段。（这条是 16.5 的 C4 直接推出来的，不是新主张。）
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

## 第 17 章：v1.07c 的功能改动是**空操作** —— 我把「注释」当成了「代码」（2026-09-18 23:55）

### 17.1 起因：用户问了一句我一直回避的话

> **"所以这一次你从代码层面可以确定不会再犯之前得问题了么"**

**不能。** 而且按这句话去核代码，第一件事就发现：**上一轮那个"修复"在这条路径上什么都不改。**

### 17.2 机器判定的证据（`tools/verify_v107c_is_inert.py`，纯 Python 无依赖，只读）

```
=== A. same construction? ===
  rebuildViewProj   860 chars  sha1 7fe156da9b20
  fixedViewProj     860 chars  sha1 7fe156da9b20
  identical: YES
  rebuildViewProj inputs: a_fb.CameraView,a_fb.CameraPosAdjust,a_fb.CameraProj
  inline block inputs:    a_fb.CameraView, a_fb.CameraPosAdjust, a_fb.CameraProj   (same)

=== B1. same P on both sides ===
  max |inv(P@A)@(P@B)  -  inv(A)@B| = 2.878e-13   over 200 random rotation pairs

=== B2. what v1.07c actually moved ===
  |old_result - new_result| = 0.000e+00

=== C. path enumeration ===
  case                             old                new                        verdict
  useFixed=true,  camCurOk=true    fixedViewProj      camCurVP                   same matrix -> NO EFFECT
  useFixed=true,  camCurOk=false   fixedViewProj      curForReproj=fixedViewProj same matrix -> NO EFFECT
  useFixed=false, camCurOk=true    currViewProjSL     camCurVP                   >>> THE ONLY PATH THAT CHANGES <<<
  useFixed=false, camCurOk=false   currViewProjSL     curForReproj=currViewProjSL same matrix -> NO EFFECT
RESULT: OK（退出码 0）
```

**A 段是判定性的**：`rebuildViewProj`（629–664）与 `fixedViewProj` 的内联构造（917–960）
把注释、NaN 守卫、`.data` 写法、形参绑定全部归一化之后，**哈希完全相同**。
⇒ **`camCurVP` 与 `fixedViewProj` 是同一个矩阵（逐位）。**

而 `curForReproj = useFixed ? fixedViewProj : currViewProjSL`（984 行，v1.07b 与 v1.07c 一字不差），
`diag.reprojSource = useFixed ? 2 : 0`，打印 `==2 → "fixed"`，23:10 那份日志写的是 **`reproj src=fixed`**
⇒ **`useFixed == true` ⇒ 那次运行的 `curForReproj` 就是 `fixedViewProj` = `camCurVP`。**

⇒ 把取逆的源从 `curForReproj` 改成 `camCurVP`，**改前改后是同一个矩阵**。
**v1.07c 在它自己被诊断出来的那次运行上，是 0 效果。**

### 17.3 我错在哪（一句话）

第 16.3 节的**全部依据**是 `Streamline.cpp:1029-1032` 的这段注释：

> "v0.66..v1.00 stored `curForReproj`, the engine-derived ViewProj, **which carries NO translation**"

**那句注释是 v0.66..v1.00 时代写的，当时 `curForReproj` 确实是 `currViewProjSL`。**
v0.88 引入 `fixedViewProj`、984 行把它改成 `useFixed ? fixedViewProj : currViewProjSL` —— **注释没跟着改。**
**我把注释当成代码读了，于是"证明"了一个在这条路径上不存在的缺陷，并且"修复"了它。**

⇒ 这是技能 §110（因果倒置的注释）与 §41（过期注释）的**又一次复发**，而且是代价最大的一次：**一整轮**。

### 17.4 代数没错，只是被用在了没有这个输入的路径上

`inv(P @ [R|0]) @ (P @ [R | -R@eye]) = [ I | -eye ]` 这个恒等式**是对的**
（16.5 的 C0，200 组随机样本偏差 2.9e-11，也是对的）。
**它需要一个"无平移"的 `P@[R|0]` 当输入才能触发 —— 而实测走的路径上，两侧都没有这个输入。**
（`fixedViewProj` 与 `rebuildViewProj` 都在 929–933 / 643–647 行显式地写了 `-(m0*ex+m1*ey+m2*ez)`，即**带平移**。）

### 17.5 那 `row3[3] = -195.22` 到底是什么？（诚实：**仍未解释**）

B3 段证明：`inv(cur)@prev` 的 `[3][3]` 是**两侧投影的比例**——
共用同一个 P 时恰为 1.000000；把 `prev` 那一侧的投影整体乘 k，`[3][3]` 就精确等于 k。

```
prev 侧投影乘 k =    +1.00  ->  row3[3] =    +1.000000
prev 侧投影乘 k =    +0.50  ->  row3[3] =    +0.500000
prev 侧投影乘 k =  -195.22  ->  row3[3] =  -195.220000
```

**所以"世界族 / 菜单族投影不同"这个解释（本账本沿用多轮的那个）也不够：**
族投影比是 **5.62x**，它应该给出 `5.62` 或 `0.178`，**不是 `-195.22`**。

⇒ **`-195.22` 是一个还没有机制解释的读数。它进 16.6 那张"未解释"表。**
（也可能是 `matrixFullInvert` 收到近奇异输入后爆掉，或者守卫把上一帧的 `s_lastGoodClip` 顶了上来 ——
两者都能造出任意大的数。**在这份日志里分不清**，这正是需要下一个读数的原因。）

### 17.6 下一个读数（要改代码，一行）

每帧打三个数：**`curProj[0][0]`、`prevProj[0][0]`（`s_prevCamProj`）、`clipToPrevClip[3][3]`**，
外加 `cur`/`prev` 是否同族。判据：**凡是 `[3][3] != 1` 的帧，看两侧投影是否不同。**

### 17.7 由此引出的一个决定（交给用户）

**v1.07c 与 v1.07b 在这条路径上功能完全相同** ⇒ 原计划的"v1.07c 验收运行"，
实际上是**再测一遍 v1.07b**。两条路：

| | 做法 | 代价 / 收获 |
|---|---|---|
| **(a) 照跑** | 按验收卡跑一次 | 拿到 `clipW` 基线、交替 `clipDev` 的第二份样本、六个小时后第一次实测 —— **不是零价值，但不验证任何修复** |
| **(b) 跳过** | 先做 17.6 那一行诊断，编译部署，一次跑到位 | 省一趟游戏，但改完仍是"没验过就上机" |

**我倾向 (b)。但游戏是你的时间，你定。**

### 17.8 这一轮真正的产物

**「修好一个东西」之前，先证明「改前 ≠ 改后」。**

- `tools/verify_v107c_is_inert.py` 是这次的**具体**证明（可重跑、退出码 0/1）
- 通用动作进技能（§42）：**任何"把 A 换成 B"的补丁，先跑一遍证明 `A != B`，
  再谈它修了什么** —— 否则你连"没效果"和"有效果但不够"都分不开

★ 这条和 §112（"回归脚本必须先自证两支不同"）是同一件事的两面：
**§112 管的是对照实验，本章管的是产品代码本身。**



---

---
---

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

（B 段第一次跑是 FAIL，但那是**脚本自己的 bug**：文本模式下 universal newlines 把 `\r\n` 换成 `\n`，
`split("\r\n")` 返回**单元素列表**，整个审计变成空操作却照样报结论。
已改为二进制读取，并加了一条「拆分后行数必须 > 100」的守卫 ——
**这正是「审计器自身必须先自证在工作」的第 N 次实例。**）

### 18.5 顺带抓出的真 bug：分析脚本会吞掉整行心跳

为了喂合成样本，给 `analyze_session.py` 加了 `--log/--watchdog` 覆盖参数，于是发现：

```python
hb = re.findall(r"\[XRAY\].*?clipDev=([\d.]+).*?cam\(ok/inv\)=(\d+)/(\d+)")     # 旧
```

`([\d.]+)` **不含负号**。而 `clipDev` 一旦为负（这个案子里 `-195.22` 这种值出现过），
**整行心跳匹配失败** ⇒ 第 4 节直接打印 `NO DATA` ⇒
**一个「异常读数」被静默翻译成「没有数据」。**

```python
hb = re.findall(r"\[XRAY\].*?clipDev=([-\d.]+).*?cam\(ok/inv\)=(\d+)/(\d+)")    # 新
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

---

---
---

**本文件维护规则**：每次改动后追写「本轮改动 / 验证结果 / 新证据 / 新错误」，
**不覆盖历史章节**，只在第 9 章与末尾追加。
