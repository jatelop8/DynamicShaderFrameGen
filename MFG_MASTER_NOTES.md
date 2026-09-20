# MFG 记忆总纲 —— 多倍帧生成 + DLSS5 的完整账本

**建立时间**：2026-09-18 19:40
**建立原因**：用户指出「一直压缩上下文 导致这两天我们只做多倍帧生成的记忆出现了严重缺陷」。
本文件**不做概括、不做摘要**，是把散落在 20+ 个文档里的**结论、证据、我犯过的错**一次性钉死在磁盘上。
**每次改动后必须追写本文件**，它比对话历史权威。
**★★★ 动手前先读「铁律总表」（L1–L25）—— 它在本文件第 0 章之前，是全部章节教训的收编，两处冲突以它为准。**

---

## 铁律总表（L1–L25）—— 违反一次就白干一轮

**用户 2026-09-19 09:34 原话：「这是铁律」。**
本表是全文沉淀出的**操作层最高约束**。散落在各章的旧铁律（1.3 / 第 6 章 / 13.1 / 13.4 /
15.1 / 16.11–16.16 / 18.3）**原文一律不动**，此处只做收编与升级；两处冲突以本表为准。
每条后面是**真实代价**——没有代价的条目不该进来。

### L0 · 元铁律 —— 交付前必须自我检查两遍（2026-09-19 09:40 用户原话）

> 「每次你看完日志改完要自我检查两遍 再给我 不要每次骗我 这个是铁律 记住 每次照做」

**"骗"的定义**：我从未故意说假话，但**未经证实的断言在用户眼里就是骗**。
所以判据不是"我有没有撒谎"，而是"**我手里有没有证据**"。
没有证据的结论只能写"未证"，不许写成结论；不确定就必须说"不确定"。

**第一遍 · 手脚（我改的东西，真的改对了吗）**

1. 逐符号 `grep` 回读 —— 改动是否真的落盘（本会话已当场撞到一次：
   `--apply` 那次命令返回空输出、我误以为成功，实测账本字节数未变）
2. **逆操作还原 → 与改前逐字节相同**（纯增量证明）；插入型改动必须有幂等守卫
3. 行尾核对（CRLF / LF 计数 + stray = 0）
4. 构建通过（编译器是最便宜的验证器，但**不是唯一**的 —— 丢失的改动照样能编译通过）
5. **双份 md5**（build == MO2 部署）+ DLL 内字符串版本号 + 确认游戏本体无残留副本
6. 补丁锚点 `count(old) == 1`；`post-condition` 检查**结果文本**，不是输入文本

**第二遍 · 脑子（我说的结论，真的站得住吗）**

1. ★ **反向假设**：若结论是反的，日志会长什么样？**我看到的能不能排除它？**
   （第 17 章就是缺这一步 —— 空操作被当成了修复，用户白跑一趟游戏）
2. 读量三问（有无写者 / 有无 override / 注释是否过期）……L2
3. 这条路径真的会被走到吗（探针三连空）……L12
4. **A≠B 证了吗**（空操作修复）……L11
5. 同时发生 ≠ 因果，分不开就写"未证"……L18
6. 空集 / 异常读数会不会被当成"健康"……L3
7. **用户会不会因此白跑一趟**……L22
8. 有没有把"未证"写成了结论、把推断写成了事实

**交付时必须把两遍的结果一并给出**（各一两行），让检查看得见 —— 不是"我检查过了"，而是
逐条列出检查了什么、结果是什么。第 17 章与第 20 章那两次返工，**第二遍都能当场拦下**。

### A 组 · 读数：判断一个数能不能用

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L1** | **只有实测字段能当结论。** `dlssgMaxFramesToGenerate`（STOCK 上报）、`dlssgEffectiveMax`（我的请求）、`mult(pres)` 全是**声明**；事实只有 `dlssgAcceptedFrames` 与 `mult(acc)`。 | 1.3、13.1 |
| **L2** | **读任何量之前三问**：① 有没有写者（`grep`）② INI 有没有 override 键 ③ 注释是否过期。**不能变的量是仪表或配置，不是数据。** | 16.11 → 16.16，升级于 16.16 末 |
| **L3** | **解析器对无法解析的输入必须尖叫。** 打 `NO DATA` / 静默跳过 = 把异常翻译成"健康"，而空集在判读层和健康长得一样。 | `clipDev=([\d.]+)` 无负号；横幅 `\(compiled` 被 `(probe build, compiled` 打破 |
| **L4** | **名字会骗人，必须读定义。** `stage=` 是"最后写入的名字"不是"卡住的位置"；`camPrev(ok/used)` 的 ok 是**布尔**不是计数器；`CameraProj`(c8) ≠ `CameraProjUnjittered`(c40)。 | 13.4、19 章、20 章 |
| **L5** | **"这是个死仪表"的判定本身要复核。** `move=0.0000` 被我判为死字段，实为**相机真没动**（`move`=`snapAcceptDist` 瞬量，实测 0.5179/0.4637/…）。 | 19–20 章订正，一度误导 |

### B 组 · 判据：判断一条判据会不会响

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L6** | **判据必须会变化。** 拿僵死常量当门 = 空操作。 | v1.02c（`sameCamera` 恒真 ⇒ 每帧 identity） |
| **L7** | **证明它是你读它那一刻所代表的那一帧。** 会被覆盖的变量先快照，并把顺序写成索引断言。 | 18.3（`s_prevCamProj` 在 750 被覆盖 → 757 先快照） |
| **L8** | **累计量不能做窗口边界。** `path>0` 一旦涨上去就恒真 ⇒ 窗口盖满全局、**结论反向**。窗口边界必须是瞬量（`move`）。 | 19 章（错报 `8 of 8`，正确是 `0 of 8`） |
| **L9** | **回归必须在合成样本上自证会分歧**；最有力的是"两份样本只差一个变量，判据必须给相反结论"。 | CASE F / G |
| **L10** | **判读代码自己也要被测。** 回归脚本的真正价值常常不是验证新判据，而是对判读层做对抗测试。 | 一个"必须报 (b)"的样本逼出了负号 bug |

### C 组 · 动代码之前

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L11** | **改 A→B 之前先证明 A≠B。** 空操作修复 = 白干一轮 **+ 让用户白跑一趟游戏**。 | 第 17 章（把过期注释当代码，两构造器 `sha1` 相同） |
| **L12** | **插桩之前先证明那条路径会被走到。** | 探针三连空：`mvecScale`（INI 钉死）、`path`（累计量）、`[MOTION]`（0 行） |
| **L13** | **修一个真实错误 ≠ 修的是正在追的问题。** 修复生效而症状照旧 ⇒ 另有根因，不许收工。 | v1.04（`capMult` 真修好，冻结照旧） |
| **L14** | **"锚点唯一"与"只跑一次"是两件事。** 插入型补丁天然不消耗锚点，必须另有幂等守卫。 | 两次重复插入（`patch_design18b` / `patch_skill8`） |
| **L15** | **改后逐符号回读**；`post-condition` 检查**结果文本**，不是输入文本。 | 曾因检查输入而误报成功 |

### D 组 · 下结论之前

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L16** | **"输出被计数证明是通的" ≠ "这个状态机不是故障点"。** 发布计数是最便宜的反证。 | 15.1 |
| **L17** | **跨进程独立证据 > 自证。** 别的程序在 hook 点看到的同一份数据，比我的日志硬。 | 第 20 章（Transfusion `[MOTION]` 才是决定性证据） |
| **L18** | **同时发生 ≠ 因果。** 分不开就写"未证"，不许升格成结论。 | 4x 启动 ⊥ `CameraPosAdjust` 变值（差约 900 单位、无过渡帧） |
| **L19** | **一行未做的东西不许说做了。** 第 0 章的诚实表就是为此存在。 | 20/30 系一行未写；DLSS5 代码在、未上机 |

### E 组 · 与用户的接口（最贵的一组）

| # | 铁律 | 出处 / 代价 |
|---|---|---|
| **L20** | **先把手上的可玩状态还给用户，再谈诊断。** | 09:05 改 INI（`Provider=0` + `MFGMaxFramesOverride=0`，带备份） |
| **L21** | **用户的症状描述是最高优先级证据，不许用我的假设覆盖它。** "画面是来回循环的"、"进不去游戏、只有音乐"两次把案子整个翻过来。 | 第 16 章、第 20 章 |
| **L22** | **让用户进游戏之前，先离线证明这趟运行有信息量。** 否则就是白跑：v1.07c 那次功能为空操作；07:37 那次心跳全落在停下之后（判据 0 先决条件：`heartbeats inside the moving window: N of M`，**`N=0` 即白跑**）。 | 第 17、19 章 |

### F 组 · 环境（正文见第 6 章）

| # | 铁律 |
|---|---|
| **L23** | **行尾逐文件实测**（改前实测、改后核对）。本工程：`Streamline.cpp` / `.h` 纯 CRLF；账本 / 技能 / 工具脚本纯 LF；`FrameGen.h`、`main.cpp` 混合。 |
| **L24** | **`core.autocrlf=true` 且无 `.gitattributes`** ⇒ 任何 `git checkout / reset / stash` 会把纯 LF 文件翻成 CRLF。**修法已写（18.9 E），未落地。** |
| **L25** | **构建即部署**；改后核**双份 md5**（build == MO2 部署）+ DLL 内字符串 `grep` 确认版本号 + 确认游戏本体 `data/` 无残留副本。 |

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

### 18.9 交班（v1.08 交付时：仍未做 / 故意不做的事）

#### A. 本文件里所有的行号都是 v1.08 **之前**的

v1.08 的插桩在 757 行附近插了行，其后所有行号整体后移。**照旧行号去 grep，会读到完全不相干的东西**
—— 2026-09-19 00:15 实测，旧引用「1029–1032」那个位置现在是一段讲「按帧维护历史」的中文注释。
**行号过期与注释过期是同一个病**：第 17 章我因为读了一句过期注释，白干一整天。

| 旧引用 | 现位置 | 内容 |
|---|---|---|
| 「1029–1032」 | **1040–1043** | `v0.66..v1.00 stored curForReproj ... which carries NO translation` —— **就是第 17 章里骗到我的那一段** |
| （未记） | **1084–1093** | v1.07c 自己写下的注释（断言两侧相机不同源）—— **已被第 17 章证伪** |
| （未记） | **900–904** | 更早的 `Proj @ View` 顺序 / `c0 == c56` 推导段 |

★ **三段讲的是三件事，而且只有 900–904 那段仍然成立** —— 它说的是**引擎自己**的 ViewProj 无平移，
这一点从头到尾没变。1040–1043 说的是「v0.66..v1.00 存的是引擎矩阵」，而 v0.88 之后
`curForReproj` 早已改成 `useFixed ? fixedViewProj : currViewProjSL`。
**一句话里把「当时」和「现在」混在了一起 —— 这就是它骗到我的方式。**

#### B. 故意没改的欠账（留到下一次真正的代码改动一起做）

1. **两段过期注释**（现 1040–1043 / 1084–1093）：本应改成事实，但改注释要重新编译，
   会破坏**正在等待第一次上机的二进制**的 md5（v1.08 = `0a10b4b6…b613`）⇒ **故意留到下次**。
   ★ 这是 12.13 那条规矩的第一次实际应用：**当二进制本身是交付物时，注释不能单独改。**
2. **第 14.6 节的释放竞态**：故意未修（第 14 章原文）。
3. **`docs/acceptance-v1.07c.html` 保留不删**：它是被证伪那一轮的原始记录，删了就没有对照组。

#### C. 明天开机第一件事（顺序不能换）

1. MO2 **取消勾选 `Modex.dll`**（第三方闪退，今天崩过三次，会掩盖一切结论）
2. 进游戏 → 等 4x 起来 → **站着不动 5 秒** → 走 5 秒并转视角 → 退出
3. `python tools/analyze_session.py` → 五条判据（见 `docs/acceptance-v1.08.html`）
4. 若出现 `[MOTION]` 行 ⇒ 读它自带的 `p00 cur/prev` 与 `mag invSrc` ⇒ **直接判 (a)/(b)**

#### D. 这一轮之后仍然没有答案的问题（别当成已解决）

- `clipToPrevClip[3][3] = -195.22` 的机制 —— **本轮就是去测它**
- 冻结是否真的止住 —— **未知**（我无法运行游戏）
- 性能恶化：FPS 39.7→13.4、1% Low→1.1、真实帧 571ms —— **未解释**
- RTX 20/30 系 —— **一行未写**；DLSS5 —— 代码在，**未上机验证**

#### E. 顺带查出的一个 git 陷阱（下一轮可选修，**今晚不动**）

睡眠审计时顺手查的，**有证据**（`git ls-files --eol`，2026-09-19 00:40 实测）：

```
i/lf  w/lf    MFG_MASTER_NOTES.md        src/DX12SwapChain.cpp
i/lf  w/lf    src/NeuralRendering/*      tools/*.py
i/lf  w/crlf  src/Streamline.cpp         src/FrameGen.cpp
```

- **索引里所有文件都是 `i/lf`** —— 因为 `git config core.autocrlf = true`，而且仓库**没有 `.gitattributes`**。
- 工作树里那些 `w/lf`（账本、`DX12SwapChain.cpp`、`NeuralRendering/*`、工具脚本）
  是**上一次直接写入留下的产物**，**不是 git 保证的状态**。
- ⇒ **任何 `git checkout` / `git reset --hard` / `git stash pop` / 重新 clone，都会把工作树的纯 LF 文件写成 CRLF。**

**为什么危险**：本项目的补丁脚本靠「锚点必须匹配目标文件的行尾」工作（`.h`=CRLF，先 `_fix_eol`）。
git 一旦悄悄把 `DX12SwapChain.cpp` / `NeuralRendering/*` / 工具脚本翻成 CRLF，
锚点会 `REFUSED` —— **这个是响的，还行**；但**账本与工具脚本自己变成 CRLF 是静默的**，
`_fix_eol` 的前提被打破却没有任何提示。**又一次「静默降级」。**

**建议修法（下一轮做，不要跟待上机二进制混在同一批）**：加 `.gitattributes` 把意图写死，
而不是继承全局设置：

```
* text=auto eol=lf
src/Streamline.cpp text eol=crlf
src/Streamline.h   text eol=crlf
```

★ 加 `.gitattributes` 本身**不会改动已有的工作树文件**（除非跑 `git add --renormalize .`），
所以它是纯保护性的；但「加配置」与「改代码」仍不应混在同一批。

---

## 第 19 章 2026-09-19 07:37 —— v1.08 探针构建的第一次上机：**运行有效，但这一趟测不到冻结**

本章每一条都出自 `DynamicShaderFrameGen.log` 的**这一段**运行
（`RUN START 07:36:58.442` → 最后一条 `07:38:10.028`），全部经
`tools/analyze_session.py` 判读。**二进制未改动**，DLL 仍
`0a10b4b637eb…b613`（1,329,664 B，构建 == MO2 部署）。

### 19.1 加载与帧生成：全绿，没有疑问

| 项 | 实测 |
|---|---|
| 横幅 | `[XRAY] diag active v1.08 (probe build, compiled Sep 19 2026 00:06:10)` |
| 启动 | `RUN START 07:36:58` `dll=…\data\SKSE\Plugins\DynamicShaderFrameGen.dll size=1329664B` |
| 帧生成 | `mult(acc/pres)=4/4`、`mfg(hwMax/reqMax/rungsSkipped)=5/5/0` |
| Reflex | `capFps=39`、`panel=160Hz`、4x ⇒ `~156 presented fps` |
| GPU | `fence 2/2 -> 2080/2080`，`submitted == completed` |
| 渲染循环 | `presentAge max=594ms`，无 stall |

**⇒ v1.08 的探针代码确实被加载并执行了。** 这是本次上机首先确认的事。

### 19.2 ★★★★★ 这一趟**测不到冻结**：心跳与相机运动在时间上完全错开

这是本章最重要的一条，也是 `analyze_session.py` 之前会**误判**的地方。

相机真的动过。`[CAM] acc` 行里的 `path=`（`snapPathLen`，累计路径长）从
`0.00` 涨到 **`153.78`**：

```
07:37:33  move=0.0000  path=0.00    devVP=15.011   ← 静止
07:37:46  move=0.5179  path=5.20    devVP=15.011   ← 开始走
07:37:48  move=0.4637  path=44.63   devVP=15.011
07:37:50  move=0.4465  path=81.26   devVP=15.011
07:37:52  move=0.4107  path=115.05  devVP=15.011
07:37:54  move=0.3751  path=146.05  devVP=15.011   ← 停止
07:37:58  move=0.0000  path=153.78  devVP=2.0001   ← 停住之后
```

**运动窗口 = `07:37:46` – `07:37:54`（约 8 秒）。**

而 8 条完整心跳的时间是：

```
07:37:57  07:37:59  07:38:01  07:38:02  07:38:04  07:38:05  07:38:07  07:38:08
```

**⇒ 一条都不在运动窗口内。全部落在玩家已经停下之后。**

`clipDev` 这 8 条全是 `0.000000` —— 而**相机静止时，identity 就是正确答案**。
所以这 8 个 0 **既不能证明修好了，也不能证明没修好；它们不含关于冻结的信息。**

★ 判读代码原本会把它报成
`PROBLEM: clipToPrevClip was the identity for the WHOLE session`
—— 把一次**成功的静止**读成了**最严重的那种冻结**。已修，见 19.6。

**⇒ 下一次运行的要求：走起来，并且让心跳落在走动的**那几秒**里。**
心跳只在 `world` 帧打，而 `world` 计数从 `07:37:57` 才开始
（`serial=907 menu=903 world=4`）⇒ **玩家进世界后还要再走 10 秒以上，心跳才会覆盖运动。**

### 19.3 ★★★★ 新发现：相机矩阵在 `07:37:54 → 07:37:58` 之间**塌缩**

上表最后两列：`devVP` 从 **15.011** 掉到 **2.0001**，`detVP` 从 **-79.9373**
掉到 **-2.25023**，`magVP` 从 **15.011** 掉到 **2**。

`devVP = camDev(CameraViewProjUnjittered) = max|M - I|`。三个指标同时变小 7 倍。

**⇒ 引擎的 `CameraViewProjUnjittered`（c24）在那一刻换成了另一个矩阵，而且之后
11 秒（124 帧）一直是 `devVP=2.0001`，再没回来。**

**同一秒还发生了两件事（同时，未证明因果）：**

1. `[XRAY] serial=907` 里 `resetTrue=1`、`reset=1`（本次运行唯一的 reset）
2. 两次 `lock RELEASED on the reset edge`：
   ```
   #9907  (was proj00=0.149184 famRej=3681)
   #9954  (was proj00=0.888889 famRej=3724)
   ```
   —— **相邻 116 ms 内族指纹从 `0.149184` 换成了 `0.888889`。**

**★ 这一条仍是「待查」，不是「结论」。**需要下一次运行看：`devVP=2.0001` 是不是
每次进世界都会出现、以及它与 `world` 帧计数、`reset` 的先后关系。**不要拿它当根因。**

### 19.4 ★★★★ 记忆订正：`move=` **不是**死仪表

记忆里把 `move=0.0000` 与 `jitter=(0,0)`、`snapAcceptDist=0` 并列，归为
「无写者的死字段」。**实测这次它有非零值**：`0.5179 / 0.4637 / 0.4465 / 0.4107 / 0.3751`。

代码证据（`src/FrameGen.cpp:999` 附近）：

```cpp
snapAcceptDist = snapHaveLast ? std::sqrt(d2) : 0.0f;
snapPathLen += snapAcceptDist;
...
SKSE::log::info("[CAM] acc #{} pos=({:.2f},{:.2f},{:.2f}) move={:.4f} path={:.2f} ...",
                snapAccept, px, py, pz, snapAcceptDist, snapPathLen, ...);
```

**⇒ `move` = `snapAcceptDist` = 与**上一次被接受的**相机样本的距离（**瞬时**步长）。
`path` = `snapPathLen` = 累计路径长。**

而 `src/FrameGen.cpp:1000` 的自带注释正是为这件事写的：

> v0.68：捕获层的**运动轨迹**。这是判定「被捕获的相机到底有没有跟着玩家动」的
> 那一行 —— 若玩家在走而这里 move/path 恒为 0.000，则根因在捕获层，任何重投影
> 侧的修法都救不了。

**⇒ 本次实测：捕获层跟着玩家动了（`path` 0 → 153.78）。**
**⇒ 所以「捕获层不跟踪真实相机」这个假设被**排除**了，问题在重投影侧。**

★ **订正后的死仪表名单**：`jitter=(0,0)`（写者 v0.50 删除）、`mvecScale=1`
（被 `MvecScaleOverride=1.00` 钉死）、INI `EnableUpscale`/`PresetDLSS`
（PARSED but NOT WIRED）。**`move` 不在其中** —— 它之前显示 0 是因为**当时相机确实没动**。

### 19.5 ★★★★ 探针读错了抽象层：`CameraProj`(c8) 不是族锁的 `ProjUnj`(c40)

v1.08 的探针读 `a_fb.CameraProj.data[0][0]`（c8），给出 **`p00(c/p)=1.1250/1.1250`**。

而族锁报的是 `proj00=0.888889`，并且 `[CAM] raw #1 ProjUnj` 打印
`ProjUnj[0][0] = 0.149184`（世界族）。

**两者关系：`1 / 1.1250 = 0.888889`（精确到 6 位有效数字）。**

**⇒ `CameraProj`(c8) 与 `CameraProjUnjittered`(c40) 在同一帧上是**互为倒数**的，
不是同一个矩阵的两个版本。** 探针读出来的数因此**不能**与 0.149184 / 0.8391 那张
族指纹表比对。

**★ 这是 §43.3「一个读数只对应一个候选，而且要选对抽象层」的第四次违反 —— 而且是在立下这条规矩的同一轮里。**

**⇒ 待办（要重编译，故未在本轮做）**：探针改读 `CameraProjUnjittered`(c40)，
并在心跳里补打 `P23`（透视/正交判别），让 `p00` 与族锁同源。

**★ 顺带澄清**：本轮 `p00` 的 8/8 两侧一致仍然有意义 —— 它说明**两侧取自同一矩阵**
（对候选 (a)「两侧投影不同」不利）。但因为 `clipW` 全程 = 1，本来也不需要判 (a)/(b)。

### 19.6 判读层修掉两个缺陷（都在 `tools/analyze_session.py`）

**(1) 横幅正则被 v1.08 自己打破。** 正则要求 `\(compiled`，而 v1.08 的横幅是
`(probe build, compiled …)` ⇒ **匹配失败**，输出
`build (no [XRAY] banner found)` + `PROBLEM: no banner at all`。
**⇒ 一次成功的加载被报成失败。** 已改为 `\((?:[^)]*?)compiled ([^)]+)\)`。
`EXPECTED_BUILD` 同时从 `v1.07c` 更新为 `v1.08`。

**(2) `clipDev == 0` 缺少前提。** 见 19.2。新增：从 `[CAM] acc` 行取 `move=` 建
**运动窗口**，与心跳时间戳求交。

★ **这里又踩了一个坑，值得单独记：第一版用 `path=`（累计值）建窗口。累计量单调
递增、永不回落 ⇒ `path > 0` 恒真 ⇒ 窗口一直盖到日志末尾 ⇒ 报「8 of 8 心跳在运动窗口内」，
**恰好把结论反过来了**。改用 `move=`（瞬时）后正确报「0 of 8」。**
**⇒ 通用规则：用累计量做时间窗口的边界，必然恒真。窗口要用**瞬时**量建。**

现在的三种结局互斥：

| 条件 | 判读 |
|---|---|
| 相机从未移动 | `NO DATA: … that is the correct answer, not a finding` |
| 移动过，但心跳全在窗口外 | `NO DATA: … cannot tell a freeze from a standstill` |
| 移动过，且窗口内有心跳 | `PROBLEM: pinned at identity for the whole run` ← **真缺陷** |

回归 `tools/regress_v108_p00.py` 新增 **CASE F / CASE G** —— 两份日志**只差心跳时间**，
判据必须给出相反结论。5 个旧 CASE + 2 个新 CASE 全部 PASS。

### 19.7 本次运行里还没有解释的计数（原样记录，不解释）

| 字段 | 值 | 说明 |
|---|---|---|
| `engPrevZero` | **121** | 引擎的 `CameraPreviousViewProjUnjittered` 全程是**零矩阵** ⇒ 与 16.x 的「引擎 prev 是僵死常量」一致，**但这次是"零"不是"等于 cur"** |
| `famRej` | 6330 | 族拒绝数；`lock(pub/hold/re/still)=6452/6331/4/2` |
| `shapeRej` | 9480（**74.2%**） | `snap(shapeRej)` 比例 |
| `resets` / `frozenRep` | **8036 / 4746** | `gate(resets/frozenRep)` —— 插件**自己**判定的「冻结重复」有 4746 次 |
| `hist(hit/miss)` | 120/1 | 相机历史命中 120、未命中 1 ⇒ **历史是活的** |
| `camPrev(ok/used)` | 1/120 | `camPrevOk` 是**每帧布尔**（`Streamline.cpp:704` `bool camPrevOk = false;`），1 = 本帧有；120 = 累计使用 ⇒ **正常**，不是缺陷 |
| `clipDevMax` | 0.0000 | 全程 0 |

★ **`resets=8036` 与 `frozenRep=4746` 与「相机静止 11 秒」是矛盾的量级**（总帧仅 1027）
—— 这两个计数器数的是**相机块**不是帧。**下次带上 `[CAM] acc` 的 `#N` 与心跳 `serial`
一起对齐，才能确定它们的单位。**

### 19.8 下一次运行：照旧四步，但把走动放到**心跳开始之后**

1. MO2 取消勾选 `Modex.dll`
2. 进游戏，**等到确认已进入世界**（横幅已有 v1.08，看画面上 4x 已在跑）
3. **先站着不动约 10 秒**（让心跳先跑起来）→ **然后持续走动 + 转视角 10 秒以上**
   → 再站住 5 秒
4. 退出，`python tools/analyze_session.py`

**判据（这一版）：**
- ① 横幅 `v1.08`
- ② `clipW == 1.000000`
- ③ **第 4 节必须打出 `heartbeats inside the moving window: N of M` 且 `N > 0`**
  —— 这是这一趟能不能得出结论的**先决条件**，不是结论本身
- ④ 若 ③ 满足且 `clipDev` 仍全 0 ⇒ **真缺陷实锤**
- ⑤ 若出现 `[MOTION]` 行 ⇒ 读其 `p00 cur/prev` + `mag invSrc` 判 (a)/(b)
  （**但注意 19.5：那个 p00 来自 c8，本轮不能与族表比对**）

★ **仍未动二进制**：以上全部是工具与文档改动。DLL 保持 `0a10b4b6…b613`。

---

## 第 20 章：4x 启动之后，重投影矩阵恒为单位变换 —— Transfusion 独立作证（2026-09-19 07:36 运行）

### 20.0 用户报告（原话，不改写）

> 游戏都进不去你让我怎么跑 直接加载界面结束进入游戏就不能动了 只有音乐

### 20.1 先排除一件事：这不是崩溃

watchdog 全程 `alive=1 focus=1`，`frames` 从 963 单调涨到 1041，
`stage` 在 `d3d11 Wait` / `cmdlist Reset` / `dlssg EvaluateDLSSG` 之间正常轮转，
`fence` 1924/1924 → 2080/2080 逐帧对齐，`queued` 交替 0/1。

崩溃转储为空：`SKSE/Crashlogs` 空、`NetScriptFramework/Crash` 不存在。
`DLSSG-Transfusion.crash.log` 29313 B 里**只有 1 条非 MODULE 行**，
而且它开头自己就写着：

    First-chance records are observations, not proof of a fatal crash.

**⇒ 用户的"不能动"是画面静止，不是进程挂起。** 这一点决定了后面整条推理的方向。

### 20.2 Transfusion 的独立证词 —— 本轮最硬的一条

`D:/ENB-EJ/Skyrim Special Edition/DLSSG-Transfusion.log`，07:37:57.364，tid=21204：

    [MOTION] route=slSetConstants call=0 viewport=0 transforms=game-preserved
             clipToPrev=identity prevToClip=identity projection=non-identity
             reset=1 cameraIncluded=1
    [MOTION] clipToPrev rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1] cameraPos=(0,0,1.00001001)

call=1 / call=2 / call=3 逐条相同（`rows[0][0]` = 0.99999994）。

**⇒ 送达 Streamline 的 `clipToPrevClip` 就是单位矩阵。**
这不是我对自家日志的解读 —— 是另一个进程在 hook 点上看到的同一份数据。
**⇒ 同时 `cameraPos=(0,0,1.00001001)`：位置字段在这条路径上恒为 `(0,0,1)`。**

### 20.3 同一时刻发生了什么：4x 真的启动了，然后帧率一路塌

    07:37:53.999  [PERF] 0x | FPS: 39.1 (25.55ms) | 1% Low: 38.9
    07:37:57.527  DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
    07:37:59.053  [PERF] 4x | FPS: 34.3 (29.15ms) | 1% Low:  9.8
    07:38:04.079  [PERF] 4x | FPS: 24.0 (41.63ms) | 1% Low:  9.7
    07:38:09.105  [PERF] 4x | FPS: 18.5 (54.11ms) | 1% Low:  9.7

**⇒ 4x 之前稳定 39 FPS；4x 之后 34.3 → 24.0 → 18.5，还在往下掉，1% Low 钉在 9.7。**

生成确实在执行（presentation count 4x），但输入的位移是单位矩阵
⇒ **生成的是上一帧的复制**；开销照付，收益为零 ⇒ 帧率单调下降。

**这就是"画面不动、声音照放"的完整机制。** 不是崩溃，是 4x 在做无效功。

### 20.4 `CameraPosAdjust` 的两个取值（同一个字段，两种状态）

来源已核实（不是推测）：

    src/FrameGen.cpp:640-642   const float px = a_src.CameraPosAdjust[0]; ...
    src/FrameGen.cpp:1012-1014 [CAM] acc 行的 pos= 就是它

**走动期间（07:37:46.334，[RAW] +0x0280 原文）：**

    [RAW] +0x0280 | -49.99428 891.753 95.28526 0 | -49.99497 892.2664 95.32975 0
    [CAM] raw #4501 pos=(-49.9943,891.7530,95.2853,0.0000) prevPos=(-49.9950,892.2664,95.3298,0.0000)

c80(cur) 与 c82(prev) **不同** ⇒ 位置是活的。

**4x 启动之后（07:38:06 起的每一条心跳）：**

    [CAM] acc #6407 pos=(0.00,0.00,1.00) move=0.0000 path=153.78 devVP=2.0001
    心跳：pos=(0.0,0.0,1.0) prevPos=(0.0,0.0,0.0)

125 条 `[CAM] acc` 的 pos 取值分布：`(0.00,0.00,1.00)` 42 次、
`(-50.00,600.00,80.00)`（菜单相机）47 次、其余为走动中的连续坐标。

**⇒ 它不是在"静止时自然落到 (0,0,1)"**：`(-49.99,891.75,95.29)` 与 `(0,0,1)`
相差约 900 单位，中间**没有任何过渡帧**。它是被换掉了，不是停下来了。

★ **因果边界**：4x 启动（07:37:57）与位置字段变 `(0,0,1)` **同时发生**。
本日志**不能区分**"4x 导致"与"同一事件的两个后果"。作为线索记录，**不作结论**。

### 20.5 我插的 v1.08 探针第三次打空

`[MOTION]` **0 行** —— 那条分支一次都没走到。
真正输出 w 的是 `src/FrameGen.cpp:691` 的另一条路径，共 24 条，从第 1 帧起就有：

    [07:37:33.141] [CAM] #1    non-affine w=0 ACCEPTED (v0.89) row3=(0,-0.991228,-0.132164,0) det3=-79.9373 pos=(-50.0,600.0,80.0)
    [07:38:08.706] [CAM] #12818 non-affine w=0 ACCEPTED (v0.89) row3=(-0.00391655,0.999991,0.0015,0) det3=-2.52504 pos=(-243.0,-415.3,118.6)

**⇒ 探针挂在了错误的触发条件上。** 这与 16.12 的 `mvecScale`、19.x 的 `path` 窗口
是同一类错误：**我按"我以为会走的路径"插桩，没有先证明那条路径真的会被走到。**

★ 注意 `w=0` 本身**不是缺陷**：`src/FrameGen.cpp:673-676` 已写明本引擎的相机块
携带透视项，`[3][3]==0` 合法。探针的用途是比对**两侧投影**，不是给 w 定罪。

### 20.6 与第 19 章结论的关系（修正一次口径）

19.x 说"8 条心跳全在 07:37:57 之后，运动窗口内 0 条"—— 那条**仍然成立**，
但当时的含义我写窄了。完整时间线是：

    07:37:33–45    主菜单（menu=903），pos=(-50,600,80)，move 恒 0.0000
    07:37:45.917   same-family step break dist=300.4 ⇒ 进入游戏世界
    07:37:46–54    走动，path 5.20 → 146.05，pos 连续变化
    07:37:57.364   4x 启动，同一刻 clipToPrev 变单位阵、cameraPos 变 (0,0,1)
    07:37:57–38:10 134 条 clipGate，clipDev 全 0.000000，det3 全 1.000000

**⇒ 那 134 条全 0 覆盖的是「4x 时段」，不是「静止时段」。**
它是 4x 路径上的读数 —— **恰恰是坏的那条路径**。
19.x 把它读成"静止所以正确"，**那是错的**。

### 20.7 立即恢复可玩（只改 INI，不动二进制）

    E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini
        Provider=0
        MFGMaxFramesOverride=0

依据是 Transfusion 自己记的：4x 之前的四条 `[PERF]` 是
**40.3 / 39.3 / 38.9 / 39.1 FPS，1% Low 38.9–39.0** —— 没有帧生成的 39 FPS 是稳的。
若仍不动，再在 MO2 取消勾选 `DynamicShaderFrameGen`，切到"无本插件"基线。

### 20.8 下一轮的第一件事（不是猜，是量）

在重投影之前，把**每一帧**的 c80/c82 与 CameraView/CameraProj 的指纹打进日志，
覆盖 4x 启动**前后各一秒**。要回答的只有一个问题：

> 4x 启动后的 `(0,0,1)` 是「引擎不再更新这个字段」，还是「我们读了另一份帧缓冲」？

判据：
- 若 c82 也变 `(0,0,0)` 而 c24 仍在变 ⇒ **字段停更**（引擎侧）；
- 若 c24 也冻结 ⇒ **我们读的不是引擎正在渲染的那份**（捕获侧）。

★ 以上全部是文档改动，**二进制未动**：DLL 仍为 `0a10b4b6…b613`。

---
---

**本文件维护规则**：每次改动后追写「本轮改动 / 验证结果 / 新证据 / 新错误」，
**不覆盖历史章节**，只在第 9 章与末尾追加。

## 21. 冻结的完整因果链（2026-09-19 10:59，全部来自源码行号 + 日志原文）

### 21.1 机制（已确证，非推断）
DLSS-G 收到 `clipToPrevClip` = 单位矩阵 ⇒ 它判定「相机没动」
⇒ 生成帧 = 上一帧复制 ⇒ 屏幕冻结、逻辑与音频照跑。
证据：Transfusion 自己的 dump `07:37:57.364 [MOTION] clipToPrev rows=[1 0 0 0][...] cameraPos=(0,0,1.00001001)`。

### 21.2 生产链（每一环都有行号）
```
引擎 perFrame 缓冲
  │ Map/Unmap hook           src/FrameGen.cpp:540-592（tlsMappedFB 407）
  ├─ AcceptCameraSnapshot     src/FrameGen.cpp:636  ← 族锁闸门，拒绝时 return false
  │    └─ frameBufferCopy = a_src    src/FrameGen.cpp:991  ← **唯一写入点**
  └─ SetMappedFrameBuffer(&frameBufferCopy)  src/FrameGen.cpp:587  ← 仅在 586 返回真时
       │
GetFrameBuffer()            src/FrameGen.h:236   ⇐ 返回 mappedFrameBuffer（即 &frameBufferCopy）
  │
EvaluateDLSSG(..., *fg.GetFrameBuffer())   src/DX12SwapChain.cpp:1428
  │
CheckFrameConstants(a_fb, ...)             src/Streamline.cpp:2027
  ├─ c.cameraPos = a_fb.CameraPosAdjust      src/Streamline.cpp:553   ← cameraPos 唯一来源
  └─ c.clipToPrevClip = inv(camCurVP) @ camPrevVP   src/Streamline.cpp:1109
       │
slSetConstants(c, ...)                     src/Streamline.cpp:1578
```
`s_prevCam*` 推进在 src/Streamline.cpp:752-766（无条件，只需 camCurOk）。

### 21.3 两个断点候选（各有证据，尚未分辨）

**断点 A —— 族锁闸门 latch 后世界帧再不通过**
- 日志实测：`family rejected` = **238** 次，**全部**是 `proj00=1`（正交/阴影相机）被 `locked=0.149184`（世界族）拒绝，`ratio=6.7031`。
- `pos=(-160.0,160.0,128.0) dist=456.1` 在 238 次里**逐字节相同** ⇒ 同一块从不更新的缓冲。
- `lock RELEASED` = **0** 次。
- `proj00` 全部取值：`1`×123、`0.8391`×99（菜单族）、`0.888889`×16、**`0.149184`×1** ⇒ **世界相机整个会话只到达过 1 次**。

**断点 B —— 跳线程 Map/Unmap 不配对**
- `tlsMappedFB` 是 `thread_local`（src/FrameGen.cpp:407）。
- 同一处注释自己写着：「这个钩子实测被不止一个线程命中
  （Transfusion [MOTION] 的 tid 在 40760 / 3508 之间交替），共享成员会被交叉覆盖。」
- ⇒ Map 在 A 线程、Unmap 在 B 线程时，B 的 tls 为 nullptr ⇒ `AcceptCameraSnapshot` 不被调用
  ⇒ `SetMappedFrameBuffer` 不装配 ⇒ frameBufferCopy 不更新。
- v0.65 为何选 thread_local：为了修「共享成员被交叉覆盖」。**两难**：
  共享会交叉覆盖，thread_local 会跳线程漏配。**唯一正确的第三种做法：按缓冲地址配对**。

### 21.4 ★ 为什么两天读日志读不出东西（本轮新发现，也是本人失职）
心跳（`mapHit(perFrame/unmap)`、`lock(pub/hold/re/still)`、`clipDev`）的唯一执行点在
`CheckFrameConstants` 内（src/Streamline.cpp:1325-1540），而它**只在 DLSSG 路（Provider=1）被调用**
（调用点 src/Streamline.cpp:2027，在 EvaluateDLSSG 内）。
**实测：09:55 那份日志（Provider=0 / FSR3）`mapHit` = 0 条。**
⇒ **那份日志根本没有仪器输出**，两天的「三个候选」是在无数据下推理出来的。

### 21.5 判据（不需要走动、不需要判断画面、30 秒必出答案）
`Provider=1` 下跑一次，心跳自动打印（每 30 帧或每 2 秒，
src/Streamline.cpp:1341），看一个字段：

    mapHit(perFrame/unmap)=N/M

| 观测 | 结论 |
|---|---|
| N 涨、M 不涨（或 M << N） | **断点 B**：跳线程漏配 |
| N、M 同步涨 | **断点 A**：族锁闸门 latch |

### 21.6 两个断点的修法（预告，待 21.5 定性后再落盘）
- **B**：`tlsMappedFB` 改为**按缓冲地址配对**（以 `pMappedResource->pData` 为键）。
  既不交叉覆盖、也不跳线程漏配 —— 这是唯一正确的第三种做法。
- **A**：同族 + 不再运动应允许 re-acquire；或在入口就把 `proj00=1`（正交/阴影）排除在闸门计数之外。

### 21.7 本轮未改任何代码
DLL 仍 `0a10b4b6...b613`（v1.08-probe）。INI 已切 `Provider=1 + MFGMaxFramesOverride=3 + NRAllowWithFrameGen=1`
（备份 `.bak_before_4x_20260919_1015`）。待上机取 `mapHit` 判据。

## 22. 第 22 章  v1.09-diag：为什么两天读不出结论（2026-09-19 11:1x）

### 22.1 直接回答「跑通了吗」
没有，而且现在连「跑过」都还没发生：
DFG 日志 mtime = **10:04:39**，INI 落盘 mtime = **10:56:31**
⇒ 切回 4x 之后游戏从未启动。本轮所有结论都来自 09:55 那局（Provider=0）。

### 22.2 冻结机制（确证，非推断）
`clipToPrevClip` = 单位阵 ⇒ DLSS-G 判定相机未动 ⇒ 插帧 = 复制上一帧。
证据：Transfusion 自己 dump `07:37:57.364 [MOTION] clipToPrev rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1] cameraPos=(0,0,1.00001001)`。

### 22.3 本轮新增：被发布相机是「死的」的直接证据（以及一次自我推翻）
`[CAM] raw` 全矩阵转储，`#1`（09:55:50）与 `#86401`（09:58:55）**逐字节相同**：

```
ViewProjUnj | -6.70312 0 0 0 | 0 -1.57495 11.8121 0 | 0 -0.991954 -0.132261 -15.011 | 0 -0.991228 -0.132164 0
ProjUnj     | 0.149184 -0 0 0 | -0 0.0839162 0 0 | 0 0 0 1 | 0 0 -0.0666178 0.0666667
ViewInv     | -1 -0 -0 -0 | -0 -0.132164 -0.991228 0 | -0 0.991228 -0.132164 -0 | 0 -0 0 1
pos=(-50.0000,600.0000,80.0000,0.0000)  prevPos=(-50.0000,600.0000,80.0000,0.0000)
```

`[CAM] acc` 同样：`#1` 到 `#19288` 连续接受全部 `pos=(-50.00,600.00,80.00)`
`move=0.0000 path=0.00 devVP=15.011 detVP=-79.9373` —— 逐字节相同。

**★ 但我随后推翻了自己的第一个结论。** 用 `family rejected` 的 `dist=` 反推被接受位置：

| 日志 | 被拒相机 | `dist=` | 反推被接受位置 |
|---|---|---|---|
| 10:01 | `(-160,160,128)` | 456.1 | `(-50,600,80)` ✓ 精确吻合 |
| 10:02:15 | `(0,0,1)` | 834.8 | ≈`(-50,834,90)` |
| 10:04:36 | `(-24,-221.2,111)` | 1050.3 | ≈`(-50,829,90)` |

⇒ 闸门在 10:02 之后换成了会漂移的活相机，
前 3 分钟静止是**加载/未取得控制权**，不是缺陷。
**这局没有复现冻结**，不能拿它当证据。（这是 L0 第二遍反向假设拦下的第二次。）

### 22.4 ★★ 三个确定的代码缺陷（行号 + 日志数字）

**D1 —— 到达率标定错 8.2 倍**
`#148576`(10:01:00.699) → `#149188`(10:01:01.941) = Δ612 / 1.242 s = **493/s**；
`#149798`(10:01:03.183) → `#150410`(10:01:04.403) = Δ612 / 1.220 s = **502/s**；
`FPS probe: real=41.4` ⇒ **约 12 次 Map/Unmap 每渲染帧**。
而 `kCamStillTol = 90` 的注释写「90 arrivals is ~1.5 s at 60 Hz」（90/60），
`kCamFrozenTol = 600` 写「120 frames is 2 s at 60 fps」。
⇒ 90 实际 **0.18 s**；600 实际 **1.2 s**。**本文件每个「连续 N 次」阈值都带同一个错。**

**D2 —— ★ `kCamStillTol` 是死常量**
全工程 grep：它只出现在 定义(621)、注释(814/904/926/935)、
日志参数(921/976)——**没有任何比较点**。
⇒ 注释里承诺的「连续 90 次未继续就释放」不存在。
而 `snapLockStill` 每次 accept 都被清零(986)，日志实测 `still=2/90` 全程不增。
`lock RELEASED` 行 = 0（且只打印前 5 次，所以这个 0 **不能**证明没发生）。
v1.07b 注释自己写着「reset edge 是唯一释放路径」。
⇒ **锁一旦到手就没有自己的释放路径。**

**D3 —— `continues` 绕过族指纹**
族判定(855–889)只在 `!continues` 分支(898) 被使用；
`continues`(891, d2 ≤ 50²) 直接走 985 的 `else` 接受。
⇒ **一个静止相机 d2=0 天然「继续」自己，能永久占住锁**，
并把 `snapLockProj00` 刷成自己(994)。日志实锤 19,288 次连续接受同一位置。
这与 FrameGen.h:284-289 记录的 22:02（v1.06）那局同症：锁落在
「mis-offset read of the perFrame constant buffer, not a camera」的矩阵上，
`clipToPrev` 横为 identity，画面不前进。

### 22.5 ★★★ 为什么两天读不出东西（结构性原因，不是分析能力问题）

**E1 —— 心跳只在 DLSSG 路。**
心跳（`mapHit` / `lock(...)` / `clipDev` / `frozen`）唯一执行点在
`CheckFrameConstants`，它在 `EvaluateDLSSG`(行2027)内，
而 `EvaluateDLSSG` 只在 `featureDLSSG` 为真时被调用
（`DX12SwapChain.cpp:1419`）。⇒ Provider=0 那局 **`mapHit` = 0 条、`XRAY` 心跳 = 0 条**。
**我两天的「三个候选」是在零仪器输出上推理出来的。**

**E2 —— 闸门窗口太窄。**
闸门两条路都跑（它在 Map/Unmap hook 里），但 `[CAM] acc`
有 **200 行上限 + 0.25 s 节流**＝只覆盖前 50 秒；
而 `snapAccept` 数的是**发布次数不是变化次数**
⇒ 19288 次逐字节相同的发布，看起来像「很健康的忙碌捕获层」。

**E3 —— ★ 证据被我销毁。**
SKSE sink 开档即截断；能看见冻结的 07:36 那局日志被 09:55 那局冲掉，
且 SKSE 目录里 **没有任何轮转副本**（已 `ls` 确认）。

### 22.6 本轮改动（只加读数，零行为改动）
- **A** `main.cpp` `ArchivePreviousLog()`：在 `SKSE::Init` 之前把上一局日志复制为
  `DynamicShaderFrameGen.<YYYYMMDD>-<HHMMSS>.log`，按 **7 天龄**删除，只匹配
  `DynamicShaderFrameGen.20*.log`（不会碰 watchdog 日志，不会碰别的插件）。
- **B** `FrameGen.h/.cpp`：新增 `snapMatChanges`（发布矩阵与上一次发布不同的次数）；
  `[CAM] acc` 去掉 200 行上限、节流 0.25 → **1.0 s**（全程 1 Hz）；
  新增 `[CAM] pub` 行，打印
  `matChanges / arrivalsPerSec / lock(pub/hold/re/still) / proj00 / famRej / frozenRep / ident/diff`。
- **C** 仅注释：D1、D2 写进 `kCamStillTol` / `kCamFrozenTol` 处。

**锁状态机一行未改。** 先拿到数据再动它。

### 22.7 判据（可玩配置下即可定性）
`[CAM] pub` 是带 provider 无关的（闸门在 Map/Unmap hook）。走动 30 s 以后看：

| 观测 | 结论 |
|---|---|
| `matChanges` 持续增 + `pos` 跟随玩家 | 捕获/发布层是活的 ⇒ 冻结在 DLSSG 路的 clipToPrev 构造/历史 |
| `pos` 不跟玩家 / `matChanges` 停滞而人在走 | 捕获层 / 字段偏移是根因（即 FrameGen.h:284-289 记录的 mis-offset） |
| `arrivalsPerSec` | 顺便实测确认 D1 |

### 22.8 状态
`v1.09-diag`，DLL **1,335,296 B**，md5 **`57122e95…`**（build == MO2 部署，双份一致）。
commit **`506b5b4`**，tag **`v1.09`**。INI 仍是 `Provider=1 / MFGMaxFramesOverride=3 / NRAllowWithFrameGen=1`
（备份 `.bak_before_4x_20260919_1015`）。
路径核实：游戏本体 `Data\SKSE\Plugins\` 下**没有** INI/DLL，
日志报的是 MO2 虚拟路径 ⇒ 改 mod 目录的 INI 有效。

---

## 23. 第 23 章　v1.09 交付前的 L0 第二遍：线上 INI 少了一个键（2026-09-19 11:25）

### 23.1 我在第 22 章里写了假话
- 第 22 章正文（本文件 **2450 行**、**2559 行**）**两次**写「INI 仍是
  `Provider=1 / MFGMaxFramesOverride=3 / NRAllowWithFrameGen=1`」。
- **实测（2026-09-19 11:25，只读）**：线上
  `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini`
  **第 222 行是 `NRAllowWithFrameGen=0`**。
- 判定不是"我看错"：`tools/patch_ini_4x_run.py:47-52` 自己声明了后置条件，跑在线上文件上得 **False**：

```
count(Provider=1)              = 1
count(MFGMaxFramesOverride=3)  = 1
count(NRAllowWithFrameGen=1)   = 0     <-- 它自己的脚本要求恰好 1
PATCH-POSTCONDITION SATISFIED: False
```

- 且改动前的线上 INI md5 `ed9655ad2bd0d2576d7f7e9d200a3f4c`，
  **与 `ini.bak_20260919_090521` 逐字节相同**（14525 B，CRLF 259 / 裸 LF 0）
  ⇒ 11:17:57 那次写入是**把 10:56 的成果回退成了 09:05 的旧状态**，
  **不是"我从来没改对"**。至于是谁写的（我 / 用户）——**未证，不猜**。

### 23.2 后果：如果就这样起游戏，DLSS5 一定不跑
`DX12SwapChain.cpp` 同一条链上三行，全部已回读确认：

| 行 | 代码 | 代入现值 |
|---|---|---|
| `:1161` | `fgGeneratingNow = dlssgMode && fg.settings.frameGeneration && fg.fgActive` | `Provider=1`+`FrameGeneration=1` ⇒ **true** |
| `:1179` | `nrSuppressed = fgGeneratingNow && !fg.settings.nrAllowWithFrameGen` | ⇒ **true** |
| `:1203` | `if (fg.settings.neuralRenderingEnabled && !nrSuppressed) { …NR 真正执行… }` | ⇒ **整段跳过** |

⇒ **4x 会跑，DLSS5 静默不跑** —— 正好是用户目标的相反面，又是一趟白跑。
`:1180` 那个分支只会打一行 `DLSSNR suppressed` 警告，不会自愈。

### 23.3 处置（已落盘）
`NRAllowWithFrameGen 0 → 1`。断言脚本：锚点 `\r\nNRAllowWithFrameGen=0\r\n` 的 `count==1`，
先备份 `.bak_before_nrchain_20260919_112507`，等长替换（14525 B 不变），
纯 CRLF **259** / 裸 LF **0** 保住，后置条件查结果文本，新 md5
**`a19307d47caeb513b9ef6a16c4a83a42`**。

> 注：这个 md5 与第 22 章记的那一个**一致** ⇒ 反过来证明 10:56 那次内容确实是对的，
> 是后来被回退的，而不是我没改成。

### 23.4 ★ 新铁律 L26（对 L0 第二遍的加强）
**「INI 写对了」≠「代码执行了」。**
`NRAllowWithFrameGen=1` 只是**允许**链式执行；真正证明 DLSS5 与 FG 同时在跑的**唯一**证据，
是日志里这一行：

```
[FrameGen] DLSSNR CHAINED with frame generation (v1.01, NRAllowWithFrameGen=1)
```

**它不出现 ⇒ 别读后面的日志，先回来查这一行。**

**推论（这条是本章真正的收获）：**
L0 第二遍里「用户会不会白跑一趟」这一问，**必须落到配置文件的实际字节上核**，
不能凭"我这轮改过它"的记忆。
**记忆不是证据；后置条件跑在文件上才是。**

---

## 24. 第 24 章　2026-09-19 11:30 那局：**第一次拿到 4x 的实测值**，也是第一次把冻结链指到具体族

### 24.1 这一局的身份
- 11:30:56 启动，DLL = v1.09 构建（`mtime=2026-09-19 03:17` UTC = 本地 11:17，size=1335296B）。
- 11:31:27 第一个相机快照；11:33:15.6 进世界；11:33:25 结束。
- **`DynamicShaderFrameGen.20*.log` = 0 个** —— v1.09 的归档**一次都没跑**（见 24.9）。

### 24.2 ★★★ 4x 是**实测**成功的，而且 hwMax=6（推翻旧记忆）
```
[Streamline] DLSS-G supports up to 6x frame generation (5 interpolated frames per real frame)
[Streamline] MFG override 3 <= hardware max 5 - no change needed
11:33:16.432  FPS probe: real=25.4 | DLSSG | cap~=101.6 | hwMax=6 ask=4 accepted=4
11:33:18.483  FPS probe: real=9.7  | DLSSG | cap~=39.0  | hwMax=6 ask=4 accepted=4
11:33:24.637  FPS probe: real=9.8  | DLSSG | cap~=39.0  | hwMax=6 ask=4 accepted=4
```
- `accepted=4` 是 `dlssgAcceptedFrames+1`，**测量值**（`DX12SwapChain.cpp:968-973`）。
- `hwMax=6` = `dlssgMaxFramesToGenerate+1` ⇒ **运行时自报支持 6x（5 个插帧）**。
- 呈现直方图：`presented all=… world=0/12/0/0/174/…` ⇒ 世界里 **174 次 present 各出 4 个 flip**；`menu=0/371/…` ⇒ 菜单里 FG 关（`MenuDisableFrameGen=1`）。

**⇒ 结论一：4x 从来没有被上限卡住。旧记忆里「Ada 只能 2x / `dlssgMaxFramesToGenerate`=1」是错的。**
**⇒ 结论二：用户的「4x 没成功」不是"没插帧"，是"插了但没有画面推进"（见 24.3）。**

### 24.3 但画面不推进：`clipToPrevClip` = 单位阵
```
11:33:15.546 [MOTION] clipToPrevClip[3].w=-195.222366 (must be 1) - the inverse and the
             previous matrix came from different cameras
serial=399   clipDev=243.962387 clipW=-195.222366 p00(c/p)=1.1918/0.0000
稳态          clipDev=0.000061 clipW=1.000000 p00(c/p)=1.1918/1.1918
             curVP=15.0006 prevVP=15.0006 | pos=(-243.0,-415.3,118.6) prevPos=(-243.0,-415.3,118.6)
```
`prevVP == curVP` 且 `prevPos == pos` ⇒ `inv(cur)×prev = I` ⇒ DLSS-G 被告知"相机没动"
⇒ **每 4 个呈现帧里有 3 个是复制品**。

### 24.4 v1.09 的探针把"发布流冻结"变成了数字
`[CAM] pub` 第一次有输出（115 行）。首尾：
```
#52989 (11:33:15.482) pos=(-243.05,-415.31,118.56) move=0.0000 path=65.41 matChanges=168 proj00=0.8391 famRej=13575
#54489 (11:33:24.725) pos=(-243.05,-415.31,118.56) move=0.0000 path=65.41 matChanges=168 proj00=0.8391 famRej=14475
```
**`matChanges` 在 9.2 秒 / ≈2100 次发布里冻结在 168**，`path` 冻结在 65.41，`famRej` +900。
（菜单阶段则相反：`matChanges=1` 冻结、`famRej` 增长，因为相机真的静止。）
**⇒ 我们发布出去的快照是"逐字节冻结"的。这是 v1.09 探针要回答的问题，它回答了。**

### 24.5 ★★★ 锁拿着的是"场景固定的相机"，不是玩家相机
判据不是估值、不是直觉，是**跨运行的数字恒等**：
- 被锁住的位置 `(-243.05,-415.31,118.56)`，与 `Streamline.cpp` v1.07c 注释里引用的 **23:10 那局**（两天前）
  `cameraPos=(-243.049301,-415.311523,118.558205)`、`clipToPrev[3].w=-195.222366` **逐位相同**。
- 活着的相机不可能精确复现另一局的坐标 ⇒ 这组值是**场景几何**（3D 菜单 / 载入画面相机）。

而真正的活相机以 `proj00=1` 到达，**位置在走**：
```
[CAM] #67695 family rejected: proj00=1 locked=0.8391 ratio=1.1918 pos=(-125.7,210.8,188.4) dist=640.8
[CAM] #69020 family rejected: proj00=1 locked=0.8391 ratio=1.1918 pos=(255.0,804.7,-94.4)  dist=1334.8
```
反证：菜单阶段同一个 `proj00=1` 在 `pos=(-160.0,160.0,128.0)` 上**逐字节恒定**（238 条拒绝全同）
⇒ 它的行为与"活相机"完全一致：**菜单里静止、世界里走动**。

### 24.6 触发点：reset edge 把锁交给了"下一个到达"，而那一个是假的
```
11:33:15.482 [CAM] #66564 lock RELEASED on the reset edge (was proj00=0.149184 famRej=13575)
11:33:15.482 [CAM] pub #52989 ... proj00=0.8391
11:33:15.482 [CAM] #66564 -> 立即 re-acquire 成 0.8391
```
v1.07b 的注释自己写着：release 之后 "hands the lock to the first arrival after it,
**which is the world camera whenever the menu has closed**"。
**这条假设是错的** —— 重置边之后第一个到达的是场景固定的 `0.8391`。

### 24.7 而且没有任何东西能把它放掉（D2 由日志证实，不只是 grep）
```
[CAM] #66488 family rejected: proj00=0.8391 locked=0.149184 ratio=5.6246 pos=(-243.0,-415.3,118.6) still=1570/90
```
**连续 1570 次拒绝、阈值 90、什么都没发生。** `lock RELEASED` 全程 3 条，全部是 `on the reset edge`。
⇒ 与第 22 章 D2 完全一致：锁没有自己的释放路径。

### 24.8 ★ 我自己读错的两处（写下来避免再犯）
**(a) `[MFG] debug CHECK: ... blocked=396 unblocked=1` 不是缺陷。**
我第一遍读成"我们跳过了 396 次 SetDLSSGOptions"。读 `DX12SwapChain.cpp:1372-1439`：
`blocked/unblocked` 数的是 **`menuBlock`**，即菜单守卫帧数。396 = 菜单开着 396 帧；
警告之所以打，是因为**唯一那一个非菜单帧**的 `EvaluateDLSSG` 返回了 false。不是 bug。
**(b) `camPrev(ok/used)=1/90` 不是"90 次里只成功 1 次"。**
`Streamline.cpp:1002` 是 `diag.camPrevOk = camPrevOk ? 1 : 0;` —— **赋值，瞬时标志**；只有
`camPrevUsed` 是累加。它读作"此刻重建成功，且已被使用 90 次"。

### 24.9 v1.10 改了什么（已构建 = 已部署）
- `FrameGen.h`：新增 `snapForeignMove` / `snapForeignHave` / `snapForeignPos[3]` /
  `snapForeignProj00` / `snapForeignTakeover`。
- `FrameGen.cpp`：新增 `kCamForeignMoveTol=200.0f`、`kCamForeignMinRej=30`；
  **`!sameFamily` 分支尾部不再无条件 `return false`**，而是累计"被拒族自己的位移"，
  当 `still >= 30 && travel >= 200` 时**接管 anchor**（落到已有的 adopt 路径）；
  `foreignTakeover` 抑制那条会误述的 `same-family step break` 日志；
  acquire / reset-edge 两个入口都清零累计器；`[CAM] pub` 增加 `fMove=` 与 `takeover=`。
- `main.cpp`：`InitWatchdogLogPath()` **移到 `ArchivePreviousLog()` 之前**。
  v1.09 把两者写反了：归档函数从 `WatchdogLogPath()` 取目录，而那个缓冲区当时还是空的，
  于是它在第一个 guard 就返回 —— **11:30 那局一个归档文件都没有**。
- **为什么这不是 v1.07b 删掉的那个 v0.94 re-acquire**：v0.94 是"谁排在第 90 个谁赢"（只看顺序），
  所以一个静止的错族也能靠顺序夺锁（v1.07b 注释说它有一半概率落到 `proj00=1`）。
  这里被拒族**必须自己走出 ≥200 单位**才可能接管 —— 静止或陈旧的相机不可能满足。计数下限只防抖动。
- **没改**：`kCamStillTol` 依然是死常量。现在 v1.10 这条接管路径是锁唯一的自驱动释放通道。
  记为已知缺口。

### 24.10 仍未定 / 下一步
1. **真实帧率从 58（菜单）塌到 9.8（世界）**。首要嫌疑：`NRRenderScale=1.00` ⇒ 每个真实帧做一遍
   **3840×2160** 的神经渲染，而渲染分辨率只有 1689×950（INI 自己的注释就写着 "the expensive part"）。
   **未测**，一次纯 INI 改动就能界定。
2. `proj00=1` 到底是玩家相机还是"随玩家移动的非游戏相机"：**由 v1.10 的接管自己回答** ——
   改后若 `matChanges` 开始增长、`clipDev` 变成非零，它就是相机。
3. 判据（下一局）：
   - 出现 `FOREIGN TAKEOVER (v1.10)` 且随后 `matChanges` 持续增长 ⇒ 链修对了；
   - `clipDev` 在走动时明显 > 0（不再恒 0.000061）⇒ `clipToPrevClip` 有运动了；
   - `SKSE/DynamicShaderFrameGen.20*.log` 出现 ⇒ 归档修对了。

### 24.11 ★★★ L27：改部署目录的 INI 是白改 —— **部署源在仓库里**

**怎么发现的**：交付前的 L0 第二遍，我按惯例复核"用户起游戏时读到的 INI"，第 222 行又是
`NRAllowWithFrameGen=0`。而我 11:25 明明把它改成了 1，md5 也验过是 `a19307d4`。

**根因（`CMakeLists.txt` POST_BUILD，逐行读出来的）：**
```cmake
add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_SOURCE_DIR}/SKSE/Plugins/DynamicShaderFrameGen.ini"
        "${PLUGIN_DEPLOY_DIR}/SKSE/Plugins/DynamicShaderFrameGen.ini" )
```
**仓库里的那一份才是部署源。** 手工改部署目录 = 下一次构建被覆盖回去。

**md5 实证（2026-09-19 11:48）：**
```
repo     SKSE/Plugins/DynamicShaderFrameGen.ini        ed9655ad2bd0d2576d7f7e9d200a3f4c   NRAllowWithFrameGen=0
deployed E:/EJ/mod/mods/.../DynamicShaderFrameGen.ini  ed9655ad2bd0d2576d7f7e9d200a3f4c   NRAllowWithFrameGen=0
```
两份**逐字节相同**，且都还是 0 ⇒ 11:25 那次修复（`a19307d4`）被 11:45 的构建盖掉了。
**这也解释了当天 11:17:57 的那次"神秘回退"**：`ini.bak_20260919_090521` 的 md5 `ed9655ad`
之所以与当时的部署文件相同，不是因为"我从来没改对"，而是因为**构建把仓库那份复制了过来**，
而仓库那份一直没动。

**第二个坑（同一次踩到）：`copy_if_different` 只在 DLL 重新链接时才执行。**
我改完仓库 INI 后跑 `build_vs.sh`，DLL 是最新的 ⇒ ninja 不重新链接 ⇒ **POST_BUILD 不跑** ⇒
部署目录仍是旧 md5 `ed9655ad`。**"我构建了" ≠ "INI 重新部署了"。**

**处置：**
1. 仓库 INI `NRAllowWithFrameGen 0→1`（锚点 count==1、等长替换 14525 B、纯 CRLF 259/0、
   备份 `.bak_before_nrchain_20260919_114858`），md5 → **`a19307d47caeb513b9ef6a16c4a83a42`**。
2. 新增 `tools/deploy_ini.sh`：无条件复制 + **核 md5 一致** + 逐条打印决定 4x/DLSS5 的键。
   **改 INI 后必须跑它，不许只跑构建。**
3. 复核结果：repo 与 deployed 均为 `a19307d4`，`Provider=1 / FrameGeneration=1 /
   NeuralRenderingEnabled=1 / DLSSGFramesToExecute=3 / MFGMaxFramesOverride=3 /
   NRAllowWithFrameGen=1`。

**⇒ 新铁律 L27：部署源在仓库，不在部署目录。判据永远是 `md5(repo) == md5(deployed)`，
不是"我改过"。**

## 25. 第 25 章　v1.11 —— 接管门的计数器被它要检测的故障清零（2026-09-19 14:20 那局）

### 25.1 这一章只讲一件事
v1.10 的「会动的族可以接管静止的锁」机制**本身是对的**，但它的**门**是 `snapLockStill >= 30`，
而 `snapLockStill` 被**每一次 accept** 清零。冻结族恰好在 `d2 == 0` 上到达自己的上一个到达点，
所以它 `continues`、所以它被接受、所以计数器回零。**门永远打不开。**

### 25.2 14:20 那局的证据（全部读自 DynamicShaderFrameGen.log，无一推测）
这局是 v1.10 第一次上机，也是第一次有 `[CAM] pub` 探针。

    14:20:33.718  build Sep 19 2026 11:46:58  dll size=1337856B  Provider=1
    14:21:03.345  DLSSNR CHAINED with frame generation (v1.01, NRAllowWithFrameGen=1)
    14:21:03.697  [XRAY] MENU EDGE open=1 serial=2 presentedBefore=0
    14:21:03.697  [XRAY] LONG FRAME 20206.7ms (capUs=12658 mult=1 menu=0)     <- 载入存档
    14:21:03.300  [CAM] raw #1  ... ProjUnj[0][0]=0.149184   pos=(-50.0000,600.0000,80.0000)
    14:24:26.030  [CAM] raw #86401 ... 与 #1 逐字节相同（这 3.5 分钟在主菜单，相机确实静止）
    14:27:38-14:28:08  real=39.0 稳定  hwMax=6 ask=4 accepted=4
    14:28:01.109  FOCUS lost    14:28:11.999  FOCUS regained   (用户切出去 10.9 秒)
    14:28:11.972  [CAM] #181702 FOREIGN TAKEOVER (v1.10): locked proj00=0.149184 has not
                  moved for 30 arrivals while the refused family proj00=1 travelled 255.4
                  units - adopting pos=(-125.8,211.4,189.1)
    14:28:11.973  [CAM] pub #148521 pos=(-125.79,211.45,189.11) matChanges=2  takeover=1
    14:28:12.001  [XRAY] LONG FRAME 10916.8ms           <- 切回来那一下，与 bug 无关
    14:28:12.816  [CAM] MenuDraw entry: ... kMAIN=true kFRAMEBUFFER=false
    14:28:14.271  [XRAY] MENU EDGE open=0 serial=16308   <- 7 分 11 秒后终于进世界
    14:28:14.278  [CAM] #183318 lock RELEASED on the reset edge (was proj00=1    famRej=34258)
    14:28:14.346  [MOTION] clipToPrevClip[3].w=-195.222366 (must be 1)
                  v1.08 PROBE: p00 cur=1.1918 prev=0.0000 | mag invSrc=203.9 prevSrc=15
    14:28:14.412  [CAM] #183366 lock RELEASED on the reset edge (was proj00=0.8391 famRej=34276)
    14:28:15.015  [CAM] pub #149316 pos=(-243.05,-415.31,118.56) move=0.0000 path=151.05
                  matChanges=542 | lock(pub/hold/re/still)=149316/34681/274/0
                  proj00=0.8391 famRej=34411 | fMove=0.0 takeover=1 | ok
    14:28:15.926  [CAM] #183951 family rejected: proj00=1 locked=0.8391 ratio=1.1918
                  pos=(-865.8,657.2,285.8) dist=1251.4 still=8/90
    14:28:18.479  日志停止；watchdog 同时停止，但最后一行 alive=1 presentAge=102ms

### 25.3 从这些数字里能**推出**什么（以及不能）
**能推出**
- 两次 release 相隔 134 ms，中间的 acquire 抓到了 `proj00=0.8391`，此后**再没变过**。
- `matChanges` 从 2 涨到 542 用了 3 秒 —— 这 3 秒里**接管确实让发布流活了**。**机制有效。**
- 之后 `matChanges` 冻结在 542 直到日志结束；`clipDev=0.000061`；`prevPos == pos`。
- `famRej` 从 34276 涨到 34681（<1 s，~100/s），而 `still` 只在 3–8。
- `still` 上不去的原因看代码就明白：`:1073`（`continues` 分支）、`:1069`（step break）、`:933`（acquire）
  三处都写 `snapLockStill = 0`，而 `:1014` 的门要 `>= 30`。
**不能推出**
- 世界内是不是真的"动不了" —— world 只有 34 帧、日志在进世界 4 秒后就停了，用户随后退出。
  watchdog 证明进程活着、帧数在涨、`presentAge=102ms`（≈10 fps）。**"卡死"没有证据，"极慢且画面静止"有。**

### 25.4 修法（v1.11，唯一一处行为改动）
门改盯**发布流的直接测量**，而不是到达侧的代理计数：

    FrameGen.h   新增  std::uint64_t snapPubStale = 0;
    FrameGen.cpp 发布点： if (!same) { ++snapMatChanges; snapPubStale = 0; }
                        else     { ++snapPubStale; }
                 常数：  constexpr std::uint64_t kCamPubStaleTol = 200;   // 替换 kCamForeignMinRej
                 门：    if (snapPubStale >= kCamPubStaleTol &&
                             snapForeignMove >= kCamForeignMoveTol) { ...接管... }
                 心跳：  [CAM] pub ... fMove={} takeover={} stalePub={} | {}
                 verdict：stalePub 超阈时输出 "PROBLEM the published camera has been
                          byte-identical for a long run"

**为什么 200**：冻结族 ~150 次发布/s（14:28:15→18 是 450 次/3 s）⇒ 200 ≈ 1.3 秒的
**可证死**发布流。**第二条件一个字没动**，它仍然是安全性的来源：停住的族贡献不了位移，
所以"玩家本来就站着不动"（此时 identity 的 clipToPrev **是对的**）永远夺不走 anchor。

**为什么只留一个清零点**：补丁里加了断言 `snapPubStale = 0;` 全文**必须恰好出现 1 次**。
第二个写者（accept / release / 定时器）会让停滞自己擦掉自己的证据 —— 那正是这一版要消灭的缺陷。

### 25.5 这一版**没有**做什么
锁状态机、族指纹、release 路径、step-break 逻辑**一行未改**。
唯一的行为差别是"哪个数字开门"，而这个数字从"被故障重置的代理量"变成了"故障本身的直接测量"。
**"为什么接管前会锁到场景固定相机"仍未证** —— v1.11 只保证锁能自愈（~1.3 秒内），不解释它怎么锁错的。

### 25.6 L28（本轮新增）
**「被检测的故障本身会把这个检测器的计数清零」—— 用任何计数器做门之前，先证明这个故障不会重置它。**
判据不是"这个门看起来合理"，而是"走一遍故障路径，看这个计数器还在不在"。

## 26. 第 26 章 v1.12 —— 限速器的量子是 flip，不是渲染帧

### 26.1 这一局（2026-09-19 14:55:21，v1.11，build 14:34:24）

先说结论：**v1.11 的接管触发了，但画面依旧像冻住 —— 因为游戏在世界里只跑 9.74 fps。**

| 时刻 | 事实（全部读自日志） |
|---|---|
| 14:55:21.817 | v1.11 载入，`Provider=1`，`Refresh rate: 160 Hz` |
| 14:55:51.670 | `DLSSNR CHAINED with frame generation (NRAllowWithFrameGen=1)` —— DLSS5 与 FG 同时在线 |
| 14:55:51.626 | `[CAM] pub #1 pos=(-50.00,600.00,80.00) proj00=0.149184` 首次发布 |
| 14:55:52.039 | `MENU EDGE open=1 serial=2` 进主菜单；`real=39.0` 稳定 |
| 14:56:04.143 | `MENU EDGE open=0 serial=435` 进世界 |
| 14:56:04.745 | **`#5507 FOREIGN TAKEOVER (v1.11)`** —— v1.11 的门开了，`stalePub=211` |
| 14:56:04.765 | `[MOTION] clipToPrevClip[3].w=167.815231`（最后一次非仿射告警） |
| 14:56:05.159 | `#3069 matChanges=213 ... stalePub=0 | ok` —— **之后 `clipW=1.000000`，非仿射告警不再出现** |
| 14:56:18.281 | watchdog 最后一 tick `frames=583` |

**v1.11 起作用的直接证据**：接管后 `clipDev` 开始摆动（0.011 ~ 0.547），不再是恒定
`0.000061`；`clipW=1.000000`；`[MOTION]` 告警停在 14:56:04.765 不再增长。
⇒ `clipToPrevClip` 不再是单位阵，重投影**有**运动了。

**但** `dt min/avg/max = 100.95/102.63/104.26ms`，watchdog 独立复核
`frames 535 -> 583 / 4.926 s = 9.74 fps`。**画面动不了不是因为相机冻住，是因为真的只有 10 帧。**

### 26.2 根因：限速器的量子作用在 flip 上（不是渲染帧率）

`Streamline::ReflexSleep`（`src/Streamline.cpp`，v0.63 注释块之后）：

```cpp
const double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;
capFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);
...
opts.frameLimitUs = capFps ? (1000000u / capFps) : 0u;
```

`refreshRate=160`、`capMult=4` ⇒ `want = 39` ⇒ `frameLimitUs = 25641 us`。
而 `frameLimitUs` 是**每个上屏 flip 的量子**：39 flip/s，每真实帧要 4 个 flip
⇒ 渲染侧被压成 `39/4 = 9.75 fps`。

### 26.3 四项独立印证（全部来自同一份日志，全部复现 1e6/(160/capMult-1)）

| 观测 | 日志值 | 反推 |
|---|---|---|
| `capUs`（capMult 还是 2 时） | `12658` | `1e6/(160/2-1) = 1e6/79` = 12658 ✓ |
| `capUs`（capMult 变 4 之后） | `25641` | `1e6/(160/4-1) = 1e6/39` = 25641 ✓ |
| 真实帧间隔 `dt` | `102.56 ms` | `4 x 25641 us = 102564 us` ✓（五位有效数字）|
| 真实帧率（watchdog 复核） | `9.74 fps` | `39/4 = 9.75` ✓ |
| 菜单真实帧率 | `real=39.0` | 菜单 1 flip/帧 ⇒ `39/1 = 39` ✓（GPU 受限不会恰好压在 39.0）|

`LONG FRAME 365.2ms (capUs=25641 mult=4 menu=1)` 也印着同一个 25641。
`dt` 的离散度只有 0.02 ms —— **限速器的量子是平的，GPU 受限的帧会飘。**

### 26.4 为什么之前两轮没找到

`src/Streamline.cpp` 里有一段 v0.63 注释，**把这个问题诊断得完全正确**：

> v0.54 按"渲染帧率"反推（刷新率 / 总倍数 - 1），等于把 flip 节流到 39/s；
> 而 DLSS-G 每真实帧要发 4 个 flip ⇒ 渲染侧被压成 39/4 = 9.75fps。
> 实测（2026-09-17 21:54）... 102.56 / 25.641 = 4.0000（5 位有效数字）
> 现在：cap = 刷新率 - 1 ... 倍率只用于日志里算"每真实帧几个 flip"，不再参与上限计算。

**而紧下面还有一段 v1.06 注释，把同一行改了回去**，理由是"dropping the divisor
causes 636 present fps -> the 21:27 freeze"。这个推理把 flip 上限当成了渲染上限：
若 `frameLimitUs` 是渲染上限，`capFps - 1` 才会超发；但本局的实测（`dt` = 4 倍量子、
`real` = capFps/4）**证明它是 flip 上限**，所以 v1.06 的因果是反的。
两段注释互相矛盾，代码执行的是 v1.06 那一版。

**教训：同一个文件里两段互相矛盾的注释，本身就是"这里被改坏过"的信号；
不要只看最新那段，要看哪一段能被测量证实。**

### 26.5 v1.12 改了什么（`tools/patch_v112_flipcap.py`）

1. **行为**：`want = Get().refreshRate - 1.0;`（去掉 `/capMult`）⇒ `capFps=159`、
   `frameLimitUs=6289 us`（与工程内既有注释 `capUs=6289` 一致）。flip 节流 159/s < 160Hz，
   渲染侧 `159/4 ≈ 39.75 fps`。
2. **断言**：`capFps * capMult > refreshRate` 是 v1.06 的误读，改为
   `capFps > refreshRate`（flip 上限不能超面板），并新增一行
   `Reflex cap check (v1.12): {} flip fps on a {}Hz panel = {:.1f} rendered fps at {}x`。
3. **日志**：`Reflex FLIP cap` 行不再打印 `capFps * capMult`（那会印出 636 假超发），
   改为 `~{} presented fps, ~{:.1f} rendered fps (v1.12: the cap is the FLIP rate)`。

`capMult=1`（无 FG）时改动前后都是 159，**行为不变** —— 这一步只影响多倍帧生成。
INI `ReflexFpsLimit>0` 的旁路未动：**改一行 `ReflexFpsLimit=40` 就能退回今天的行为**，
这是本改动的逃生门。

### 26.6 L0 两遍

**第一遍·手脚**：干跑 3/3 锚点 `count==1` → `--apply`；重跑被幂等 marker
（`v1.12 -- THE DIVISOR WAS THE BUG`）`REFUSED`(exit=1)；`capFps * capMult` 归零、
旧算式归零；`Streamline.cpp` 123094 → 124710 B，CRLF 2340 → 2366、裸 LF **0**；
`BUILD SUCCESS`；DLL 1,338,880 B、md5 `b51ef90b...`（build == 部署一致）；
DLL 内新串各 1 次、旧串 `presented fps (real = cap/flips)` 0 次；
仓库 INI == 部署 INI（md5 `a19307d4`），五键 `Provider=1 / FrameGeneration=1 /
NeuralRenderingEnabled=1 / MFGMaxFramesOverride=3 / NRAllowWithFrameGen=1`。

**第二遍·脑子**：
- 「`frameLimitUs` 是 flip 上限」不是假设，是**本局量出来的**（`dt`=4 倍量子、`real`=capFps/4）。
- **残余风险**：若世界里 GPU 本来就跑不到 39 fps，真实帧率会低于 39 —— 但那时
  `dt` 会**飘**而不是钉在 102.56ms。**「钉死 vs 飘动」就是区分节流与 GPU 受限的判据。**
- 本轮**没有**动锁/族指纹/接管：真实帧率变 4 倍后，接受的节拍整体改变，
  **必须先在新节拍下重测**，再决定要不要碰锁。这是纪律，不是回避。
- `docs/runlogs/`：本局日志与 watchdog 已手动存档（自动归档仍未产出文件，
  见 26.8），下一局实验不会再销毁这一局的证据。

### 26.7 下一局只看三样

| 看到什么 | 结论 |
|---|---|
| `[XRAY] serial=... capUs=6289`（不再是 25641） | 限速器修对了 |
| `dt min/avg/max` 落在 ~25ms 且**开始飘** | 渲染侧回到 ~39 fps；飘 = 真的 GPU 受限 |
| `FPS probe: real=` 从 9.8 跳到 ~39 | 合成确认，四倍帧生成第一次有可用的呈现节奏 |
| `dt` 仍钉在 102.56ms、`capUs` 仍 25641 | 说明还有第二处在写同一个上限 |

### 26.8 仍未解 / 未做

- **自动归档没产出文件**（`ArchivePreviousLog()` 调用顺序已对：`InitWatchdogLogPath()`
  → `ArchivePreviousLog()` → `SKSE::Init()`，`DynamicShaderFrameGen.%04d%02d%02d`
  串在 DLL 里存在）。静态检查找不到原因，**本轮不猜、不改**，先用 `docs/runlogs/`
  手工存档顶住。
- **发布出去的相机族仍可能被锁在陈旧的一族上**：本局 `[CAM] pub` 的 `pos` 冻在
  `(-952.21,886.25,103.16)` 达 12 秒，而 `[CAM] raw #8101` 读到的是活的
  `(-126.8871,-190.8163,186.3070)`。但 `matChanges` 每秒 +80、`clipDev` 非零
  ⇒ **发布的矩阵在变、`CameraPosAdjust` 这个字段不动** —— 这两件事的含义不同，
  不能在 10 fps 的节拍下下结论。**留到 v1.12 的 39 fps 环境再测。**
- **世界内 10 fps 之外的性能**：`RenderResolutionScale=0.44`（渲染 1689x950）配
  `NRRenderScale=1.00`（每个真实帧做一遍 3840x2160 的 DLSS5）仍是嫌疑，未测。
## 27. 第 27 章 v1.13 —— 那个「相机」根本不是相机：同一个 CB 每帧被写 20 多次

（2026-09-19 18:20 那局，v1.12 上机。证据全部是日志原文 + 源码行号。）

### 27.1 先说结论

**hook 抓的不是「引擎的相机」，而是「这个 ID3D11Buffer 最后一次被写的那个 pass」。**
那个 buffer 每渲染帧被 Map 二十多次，其中只有一次写的是相机。取「最后一个写者」
就等于取「最后一个 pass」，而世界里最后写它的那个 pass 是**一个正交全屏投影**。

### 27.2 先说 v1.12 生效了（这条是净收益，别丢）

```
[18:20:52.273] [Streamline] Reflex cap check (v1.12): 159 flip fps on a 160Hz panel = 79.5 rendered fps at 2x
[18:20:52.273] [Streamline] Reflex FLIP cap = 159 fps (6289us) - panel 160Hz, 2 flips per real frame => ~159 presented fps, ~79.5 rendered fps (v1.12: the cap is the FLIP rate)
[18:21:14.242] [XRAY] LONG FRAME 21969.0ms (capUs=6289 mult=1 menu=0)
[18:21:32.503] [XRAY] LONG FRAME 809.0ms (capUs=6289 mult=4 menu=1)
FPS probe: real=48.3 | DLSSG | cap~=193.4 (=real*4, COMPUTED not measured) | hwMax=6 ask=4 accepted=4 | cfgProvider=1
```
`capUs` 从 25641 变 6289，**真实帧率从 9.74 变成 48.3（菜单）/ 24.3（世界）**。
v1.12 的那一行除法确实修对了。

### 27.3 菜单期：捕获层是活的，而且是**真相机**

```
[CAM] pub #6724  pos=(-60.00,849.98,80.00)  move=0.0000 path=0.00  matChanges=2   ... proj00=0.149184
[CAM] pub #7116  pos=(-58.35,833.53,80.00)  move=0.3401 path=16.53 matChanges=51  ... proj00=0.149184
[CAM] pub #9852  pos=(-48.30,732.97,80.00)  move=0.2444 path=117.60 matChanges=393 ... proj00=0.149184
[FLD] #1 c8  Proj    row3=(0,0,1,0) [3][3]=0 dev=15.011 det=79.9373 mag=15.011 BAD
[FLD] #1 c16 ViewProj row3=(0,-0.991228,-0.132164,0) [3][3]=0 dev=15.011 det=-79.9373 mag=15.011 BAD
[CAM] raw #9001  pos=(-57.9856,829.8564,80.0000,0.0000) prevPos=(-58.0176,830.1761,80.0000,0.0000) devVP=15.011
[CAM] raw #11701 pos=(-49.8816,748.8160,80.0000,0.0000) prevPos=(-49.9048,749.0475,80.0000,0.0000) devVP=15.011
```
`prevPos` **紧贴 pos**（差 0.1~0.3），`path` 单调增长，`move` 0.24~0.34/帧 —— 这是真相机的签名。

把菜单的两个矩阵按「读出来的行列」重建，**`ViewProj = Proj · View` 精确成立**（手算过），
而且 `c8 Proj` 分解为 **D3D 无穷远投影**：`m22≈1`、`m23=-zn`、`m32=1`、`m33=0`，反解出 **zn=15.011**。
⇒ **字段偏移是对的**，结构体布局没问题。

### 27.4 世界期：同一个结构体里，**十个字段全是平凡矩阵**

```
[FLD] #31501 c0  View       row3=(0,0,0,1)   dev=1      det=-1      mag=1
[FLD] #31501 c8  Proj       row3=(0,0,0,1)   dev=0.111111 det=1.11111  mag=1.11111
[FLD] #31501 c16 ViewProj   row3=(0,0,0,1)   dev=1.11111  det=-1.11111 mag=1.11111
[FLD] #31501 c24 ViewProjU  row3=(0,0,0,1)   dev=1.11111  det=-1.11111 mag=1.11111
[FLD] #31501 c32 PrevVPU    全零                                                                  BAD
[FLD] #31501 c40 ProjU      det=0.9
[FLD] #31501 c48 ProjUInv   det=1.11111
[FLD] #31501 c56 ViewInv    row3=(-0,-0,-0,1) dev=1      det=-1      mag=1
[FLD] #31501 c64 ViewProjInv det=-0.9
[FLD] #31501 c72 ProjInv     det=0.9
[RAW] +0x0000 | 0 0 1 0 | 0 1 0 0
[RAW] +0x0020 | 1 0 0 0 | 0 0 0 1
[RAW] +0x0040 | 1 0 0 -0 | 0 1 0 -0
[RAW] +0x0060 | 0 0 1.111111 -0.1111111 | 0 0 0 1
[RAW] +0x0080 | 0 0 1 0 | 0 1 0 0
[RAW] +0x00a0 | 1.111111 0 0 -0.1111111 | 0 0 0 1
[RAW] +0x00c0 | 0 0 1 0 | 0 1 0 0
[RAW] +0x00e0 | 1.111111 0 0 -0.1111111 | 0 0 0 1
[RAW] +0x0100 | 0 0 0 0 | 0 0 0 0
[RAW] +0x0280 | -464.5398 349.1476 101.2857 0 | 0 0 0 0
```

把它读成矩阵：

- `c0 View = [[0,0,1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]]` —— **精确的轴交换置换阵**（det=-1）
- `c8 Proj = [[1,0,0,0],[0,1,0,0],[0,0,1.111111,-0.1111111],[0,0,0,1]]`
  反解：`m22 = zf/(zf-zn)`、`m23 = -zn·zf/(zf-zn)`，且 **`m32=0`、`m33=1` ⇒ 没有透视除法**。
  令 zf=1、zn=0.1：`z' = (z-0.1)/0.9 = 1.1111z - 0.1111` ✓ **逐位吻合**。
  ⇒ **这是一个 [0.1,1] 深度范围的正交投影（全屏 pass 的投影）。**
- `c40 ProjU = [[1,0,0,0],[0,1,0,0],[0,0,0.9,0.1],[0,0,0,1]]` = 上式的**逆**（`z'=0.9z+0.1`）

**旁证（独立、且不依赖矩阵）**：`CameraPreviousPosAdjust` 在世界里**恒为 (0,0,0,0) 整整 30 秒**，
而菜单里它紧贴 pos。写相机的那段引擎代码不可能把 prev 留成 0。

### 27.5 后果：发布流冻住

```
[CAM] pub #10085 pos=(-243.05,-415.31,118.56) move=0.0000 path=124.92 matChanges=422  lock(...)=10085/4158/3/0  proj00=0.8391 famRej=4157
[CAM] pub #16042 pos=(-381.34,208.40,187.07)  move=0.0000 path=124.92 matChanges=6171 lock(...)=16042/18667/2879/0 proj00=1    famRej=15792 ... stalePub=0 | ok
```
30 秒里 `path` 卡在 **124.92**，`pos` 只在小数点后抖动 ±0.6，
而 `matChanges` 每秒 +40 —— 因为发布序列在「真相机（~24/s，逐帧一变）」与
「恒定假相机（~500/s）」之间交替：真相机那一份被紧接着的假相机覆盖掉。

进世界那一刻的连环动作（全部同一秒）：
```
[18:21:43.686] MENU EDGE open=0 serial=1329 presentedBefore=1
[18:21:43.692] [CAM] #14242 lock RELEASED on the reset edge (was proj00=0.149184 famRej=4157)
[18:21:43.764] [MOTION] clipToPrevClip[3].w=-195.222366 (must be 1)  ... p00 cur=1.1918 prev=0.0000
[18:21:43.832] [CAM] #14289 lock RELEASED on the reset edge (was proj00=0.8391 famRej=4177)
[18:21:44.338] [CAM] #14583 FOREIGN TAKEOVER (v1.11): locked proj00=0.8391 has gone 208 publishes with an unchanged matrix while the refused family proj00=1 travelled 289.8 units - adopting pos=(-464.8,349.9,100.5)
[18:21:44.338] [CAM] #14585 same-family step break: pos=(-126.2,210.8,189.1) locked=(-464.8,349.9,100.5) dist=376.6 proj00=1 still=1/90
[18:21:44.357] [XRAY] clipGate v0.92: det3=267.144165 ... clipDev=70992.125000 finite=1
[18:21:44.369] [CAM] #14603 same-family step break: pos=(-381.4,208.6,187.6) locked=(-126.2,210.8,189.1) dist=255.2 proj00=1 still=17/90
[18:21:44.369] [CAM] #14605 same-family step break: pos=(-693.5,527.5,111.4) locked=(-381.4,208.6,187.6) dist=452.7 proj00=1 still=1/90
```
31 毫秒内 anchor 连跳 4 次、每次 255~453 单位 —— 这在游戏里不是相机，是**多个 pass 的假相机在抢同一个槽**。

### 27.6 量化：每帧 20 多次写，只有一次是相机

`arrivalsPerSec=591`，世界内 `FPS probe: real≈24` ⇒ **每渲染帧 ~22 次 Map/Unmap**。
`matChanges` 每秒 +40 ≈ `2 × 24`，正是「真相机 24/s 与恒定假相机交替」应有的计数（每次交替两变）。

### 27.7 v1.13 的改动（唯一一处行为改动）

判据（两群样本精确分离，取自同一局日志）：

| | `|CameraProj[3][2]|` | `|CameraProj[3][3]|` |
|---|---|---|
| 相机写 | **1** | **0** |
| 假相机写 | **0** | **1** |

```cpp
constexpr float kCamProjDivideMin = 0.05f;   // 有透视除法的才是相机
constexpr float kCamProjWMax = 0.05f;
constexpr std::uint64_t kCamCaptureFallbackSkips = 6000;   // ~10 s

const bool camShaped =
    (std::fabs(a_src.CameraProj.data[3][2]) >= kCamProjDivideMin) &&
    (std::fabs(a_src.CameraProj.data[3][3]) <= kCamProjWMax);
if (!camShaped) {
    ++snapNonCamera; ++snapSkipsSinceCam;
    if (snapNonCamera <= 5u) { ...一行日志，打印 row3/prevPos/pos/magVP... }
    if (snapSkipsSinceCam < kCamCaptureFallbackSkips) return false;
} else { snapSkipsSinceCam = 0; }
```

- **逃生门**：连续 6000 次都不像相机 ⇒ 判据在这台机器上不成立 ⇒ 退回「接受最后写者」（= 今天的行为）。
  **最坏情况 = 当前版本，不会更坏。**
- `[CAM] pub` 增 `cap={}/{}`（drop 数 / 连续 drop 数）。
- **锁、族指纹、release、step-break 一行未改** —— 先把输入弄干净，再看锁。

### 27.8 L30（本轮的方法论）

> **同一个槽位被多个来源共享时，「谁最后写」不是选源依据；选源必须用内容里可判定的特征。**

配套：新判据必须带**逃生门**（退化成旧行为），否则判据错了就是把「不好」换成「更糟」；
以及**先测出两群样本的分离量再写判据**（这里 1 vs 0，不是估值）。

### 27.8b 交付物

`BUILD SUCCESS` · DLL 1,340,928 B · md5 `4b34118e…`（build == 部署）· commit `9e6ac64` · tag `v1.13`。
改前存档 `src/backup-v1.13-20260919-182918/`；本局日志 `docs/runlogs/2026-09-19-1820-v1.12-world-impostor.log`
（+ `.watchdog.log`）。INI 两份 md5 `a19307d4…` 一致，六键全对：
`Provider=1 / FrameGeneration=1 / NeuralRenderingEnabled=1 / DLSSGFramesToGenerate=3 /
MFGMaxFramesOverride=3 / NRAllowWithFrameGen=1`。

### 27.9 下一局的判据

| 看到什么 | 说明什么 |
|---|---|
| `cap=` 左边 ≈ 帧率（~24/s），右边 0~30 | **修对了**：捕获层只收相机 |
| `path` 开始增长、走动时 `clipDev` 明显 >0 | 发布流是活的，重投影有内容 |
| `[CAM] NON-CAMERA write dropped (v1.13)` 有输出且 row3 是 `(0,0,0,1)` | 假相机确实存在（判据选对了） |
| `cap=` 左边 **一直是 0**、右边涨到 6000 | 世界里**没有**相机写 ⇒ 必须换源（`RE::PlayerCamera`），逃生门已自动退回旧行为 |
| 又冻结但 `cap=` 左边在涨 | **第一次能定性的复现**，这一跑就够下结论 |


### 27.10 ★ L0 第二遍（过脑子）翻出来的两条更正 + 一条独立证据链

写卡片的最后一步我按 L0 回去做「反向假设」，把日志又翻了一遍。
**翻出两个我自己写错的数字，和一个此前被我判为「未证」其实已经证了的事实。**
记在这里，因为这正是 L0 第二遍存在的理由 —— 第一遍（手脚）全部通过，错的是脑子。

#### 27.10.1 更正①：`matChanges` 的增速是 +195/s，不是 +40/s

我之前写「`matChanges` +40/s = 2×24 ⇒ 真相机 24/s 与恒定假相机交替」。**错的。**

实测采样（同一份 18:20 日志，`[CAM] pub` 行）：

| 时刻 | `matChanges` |
|---|---|
| `18:22:11.115` | `5571` |
| `18:22:12.142` | `5771` |
| `18:22:13.164` | `5971` |
| `18:22:14.191` | `6171` |

⇒ `600 / 3.076 s =` **+195/s**，即 `arrivalsPerSec(591)` 的 **33%**。
按真实帧率 24 折算 ⇒ **每渲染帧约 8 个互不相同的矩阵**被写进这个缓冲。

**教训**：`2×24` 那套算术是我**先有结论再去凑数字**（"交替 ⇒ 应该是 2 倍"），
而不是从采样点直接算。**报任何一个速率之前，先把两个采样点的时间戳和数值并排写下来。**

#### 27.10.2 更正②：「世界内有没有相机写」——已证：有

上一版我写「世界内到底有没有相机写仍未证」。**已经证了，而且证据早就在日志里。**

`v1.08` 时代留下的 `[MOTION]` 告警里带着 `p00 / p23` 探针 —— 它当时是为查「矩阵非仿射」插的，
**与本次推理没有任何关系，所以它是一条干净的独立证人**：

```
[18:21:43.764]  p00 cur=1.1918  prev=0.0000 | p23 cur=-15.000636 prev=0.000000
[18:21:44.357]  p00 cur=1.0000  prev=1.1918 | p23 cur=-0.111111  prev=-15.000636
```

- `p00=1.1918, p23=-15.000636` ⇒ **真实相机**（`p23 = -zn`，`zn = 15.000636`，
  与菜单期手算的 `15.011` 同源）。
- `p00=1.0000, p23=-0.111111` ⇒ **正交冒牌货**（`-0.111111` 与 §27.4 反解出的
  `z' = 1.1111z - 0.1111` 是同一个数）。

**★ 两条独立证据链给出同一个 `-0.111111`**（FLD 转储 vs MOTION 探针），
并且第二条是**为别的问题写的**，不可能被我这一轮的推理污染。

⇒ 世界内确实有真相机写进这个 CB，且我们的 hook 在 `18:21:43.764`
（`MENU EDGE open=0` 之后 21 毫秒）**确实抓到了它**。
⇒ 「世界里根本没有相机写」这个最坏分支**排除**。v1.13 的闸门撞上它的概率很高。

#### 27.10.3 顺带查出：v1.11 的接管判据当时挑错了族

```
[CAM] #14583 FOREIGN TAKEOVER (v1.11): locked proj00=0.8391 has gone 208 publishes with an
unchanged matrix while the refused family proj00=1 travelled 289.8 units
- adopting pos=(-464.8,349.9,100.5)
```

它把「锁着的族不动」读成"这是菜单相机"、把「被拒的族在动」读成"这才是玩家"。
在那一刻这个推理是合理的 —— **但被拒的族 `proj00=1` 恰恰就是正交冒牌货**
（采纳的 `pos=(-464.8,349.9,100.5)` 与 `[CAM] raw #31501` 读到的
`(-464.5398,349.1476,101.2857)` 是同一个点）。
接管之后 `proj00=1` 占住锁、`famRej` 从 `4157` 涨到 `15792`，**真相机被当异族拒掉**。

**本轮按纪律不改接管判据**（一次只动一处可证伪的东西）。
内容门比改判据更稳的地方正在这里：正交写进不到发布 ⇒ 接管**没有机会**再采纳它。

#### 27.10.4 ★ L30 补充：两条独立证据链，才敢把「未证」改成「已证」

> **一条证据链只能产生一个结论，不能产生一个置信度。**
> 把「未证」改写成「已证」之前，必须找到**第二条来源不同**的证据，
> 且最好是**为别的问题而插的**探针 —— 那种探针不可能被当前的推理污染。

配套的自我检查：**翻完一条链就下结论，是"先有结论再找证据"的伪装。**
本条更正就是活例子：第一条链（FLD）我读了两遍都只得出"那不是相机"，
直到我去翻 MOTION 探针才同时拿到「世界里有真相机写」这个正面事实。


### 27.11 19:39 那局（v1.13 上机）：闸门修对了，但世界段换上一个「恒定的透视相机」

日志 `docs/runlogs/2026-09-19-1939-v1.13-gate-works-static-camera.log`（build `Sep 19 2026 18:29:59`
= v1.13；跑 2 分 41 秒，菜单 1 分 59 秒，**世界段只 11.5 秒 / 274 帧**）。

#### 27.11.1 v1.13 的靶子打中了（五条硬证据）

| # | 证据 | 日志原文 |
|---|---|---|
| 1 | 正交写被丢弃 **13,804** 次，右边**恒 0** ⇒ 真相机一直在到达，**逃生门（6000）没有触发** | `cap=13804/0` |
| 2 | 世界段 `c8 Proj` 从上一局的「正交 `row3=(0,0,0,1) [3][3]=1 magVP=1.11111`」变成「**透视** `row3=(0,0,1,0) [3][3]=0 dev=15.0006`」 | `[FLD] #68401 c8 Proj` |
| 3 | **非仿射告警消失**：世界段 `clipW=1.000000` 全程；全日志只剩 1 条 `[MOTION]`，在 `MENU EDGE open=0` 后 78 ms（首帧 prev 未建立）。对照上一局世界段反复 `w=170.324310` | `[MOTION]` 只剩 1 条 |
| 4 | 丢弃的确实是正交族 | `#2 NON-CAMERA write dropped: Proj row3=(0,0,0,1) pos=(-160.0,160.0,128.0) magVP=1.11111` |
| 5 | v1.12 的限速器修复仍在；4x 仍在跑 | `Reflex FLIP cap = 159 fps (6289us)` / `mult(acc/pres)=4/4` |

#### 27.11.2 但画面仍不动 —— 这次是纯测量，不需要推断

世界段 11.4 秒里喂给 DLSS-G 的相机**逐字节不变**：

| 字段 | 世界段实测 |
|---|---|
| `a_fb.CameraPosAdjust` | `(-243.05,-415.31,118.56)` 冻结 |
| `a_fb.CameraPreviousPosAdjust` | **与上面逐位相同**（"上一帧位置" == 本帧位置）|
| `move` / `path` | `0.0000` / 冻在 `63.91` |
| `curVP` vs `prevVP` | 同值（`15.0006`）|
| `clipDev` | `0.000061`（地板，274 帧不动）|
| `frozen` | 与世界帧数 1:1（120→270）|
| `snapIdenticalArrivals / Different` | `54117 / 880` ⇒ 整局只有 **1.6%** 的写入与前一次不同 |

⇒ `clipToPrevClip = inv(cur)×prev = I` ⇒ DLSS-G 判"相机没动" ⇒ 插帧=复制上一帧。

#### 27.11.3 ★ 一个新发现：`CameraProj` 与 `CameraProjUnjittered` 不可能是一对「抖动/去抖动」

`CheckFrameConstants` 里两条链取的是**同一个结构体的不同字段**：
- `camCurVP`（→ `clipToPrevClip`）用 `a_fb.CameraProj`
- `c.cameraViewToClip`（→ 喂给 DLSS-G 的投影）用 `a_fb.CameraProjUnjittered`

| 样本 | `CameraProj[0][0]` | `CameraProjUnjittered[0][0]` | 关系 |
|---|---|---|---|
| 19:39 世界 | `1.1918` | `0.8391` | **1/1.1918 = 0.83907** |
| 18:20 世界（正交） | `1` | `1` | 1/1 = 1 |

而且 18:20 世界那份**可整行验证互逆**：`ProjUnj` 把 z 从 `[0,1]` 映到 `[0.1,1]`（`z'=0.9z+0.1`），
`Proj` 是 `z'=1.1111z-0.1111` —— **精确互逆**。

> **抖动是亚像素级，只改 `[0][0]/[1][1]` 的千分之几；这里差 42% 且成互逆关系。
> ⇒ 两个字段不属于"同一台相机的抖动/去抖动"。**
> **本局不据此改代码**：存储序（行/列主序）在日志里有歧义，先把它变成可测量的探针。

#### 27.11.4 ★ 一处读数更正（回代码才发现的）

`camPrev(ok/used)=1/270` 我曾读成「ok 只 1 次却用了 270 次」的矛盾。
回代码：`diag.camPrevOk = camPrevOk ? 1 : 0;` 是**赋值**不是自增 ⇒ 它是布尔快照，
`1/270` = 「此刻有效 + 累计用了 270 次」，**正常**。这条读法作废。

#### 27.11.5 下一局：纯增量探针 v1.14（写者普查）

`tools/patch_v114_writercensus.py`，4 处改动，**只加计数与日志、零行为改动**：

- `AcceptCameraSnapshot` 在闸门**之前**维持一张最多 8 条 `(pos)` 签名表，遇到新签名就
  `[CAM] WRITER #N NEW pos=(...) proj00=... row3_2=... row3_3=... prevPos=(...) arr#...`（上限 80 行）
- `[CAM] pub` 增 `cen={}/{}`（= `snapCensusNew / snapCensusCount`）

**判据表（一次读数定案）**：

| `cen=` 读数 | 结论 | 下一步 |
|---|---|---|
| 左边停在 **2~3** 一整天 | **这个世界里没有任何写者的位置在动** ⇒ hook 根本看不见相机 | **换源**：`RE::PlayerCamera`（`GetSingleton()->cameraRoot->world.translate`，CS 参照 `Hooks.cpp:719-722`）|
| 左边**几百**、右边顶到 8 | 有**在动**的写者，只是被接受规则拒了 | **改接受规则**（v1.11 的接管判据当时挑错了族）|

前提：进世界后**真的走动 10 秒以上**。19:39 那局世界段只有 11.5 秒且 `pos` 全程不动，
**"玩家站着没动"与"锁在固定相机上"在日志里同形**，这是唯一无法消歧的点。

### 27.12 21:15 那局（v1.14probe 上机）：探针先把自己测出了缺陷

日志 `docs/runlogs/2026-09-19-2115-v1.14probe-static-refused-family.log`（build `Sep 19 2026 19:45:58`
= v1.14probe）。整局 48 秒，**世界段只有 3.4 秒**（`MENU EDGE open=0` 在 `21:15:09.552`，
日志止于 `21:15:12.917`）。watchdog 全程 `alive=1`、`presentAge=46ms` ⇒ **不是崩溃，是正常退出**。

#### 27.12.1 一条正面结论：v1.13 的闸门在世界段一次都没开火

`cap=2296/0` —— **右边恒 0**（一次没丢），逃生门（6000）没触发。世界段的每一个到达在 v1.13 的
内容判据眼里**都是相机长相**。**问题不在内容门。**

#### 27.12.2 ★ 头号发现：v1.14 的 `cen` 探针有设计缺陷，这局的读数作废

`cen` 数的不是「不同的位置」，而是「与**最初见到的那 8 个**位置相差 > 1 单位」的到达次数 ——
因为 `kSnapCensusMax = 8` 的表**满了就不再写入、也不淘汰**，而 `++snapCensusNew` 照样执行。

铁证在日志里：

```
[CAM] WRITER #9  NEW pos=(-49.995,892.661,95.364) prevPos=(-49.996,893.077,95.400) arr#3645
[CAM] WRITER #10 NEW pos=(-49.995,892.661,95.364) prevPos=(-49.996,893.077,95.400) arr#3648
```

`#9` 与 `#10` 的 `pos` 与 `prevPos` **逐位相同**却都被判为 NEW —— 表里装的是更早的 8 个，
`#9` 自己没进表（满了），所以 `#10` 只能与那 8 个旧值比较。

⇒ **一个停着的写者也能让 `cen` 无限增长。`cen=5077/8` 不能读成「有 5077 个在动的位置」。**
**这局回答不了 v1.14 想问的问题，而错不在日志，在探针。**

**L31：任何「我见过几个不同的 X」计数器，必须先定义「X 的表满了怎么办」。**
不限制容量的「新值计数」把**从未见过**和**在变化**混为一谈 —— 与 L28（用会被故障重置的计数器做门）
是同一族错误的两端：一个是门被重置，一个是表被撑爆。

#### 27.12.3 世界段的实测（全部是本节的新读数）

| 量 | 世界段实测 | 读法 |
|---|---|---|
| 发布的位置 | `pos=(0.00,0.00,1.00)` | 不是相机位置 |
| `path` / `move` | `82.39` 冻住 / `0.0000` | 发布流静止 |
| `stalePub` | `0 → 80`，每秒 +26 | 连续 80 次发布的矩阵逐字节相同 |
| 锁定族 | `proj00=0.888889` | 进世界后换上的 |
| 被拒族 | `proj00=0.8391`，`pos=(-243.0,-415.3,118.6)` | 菜单相机，**位置恒定** |
| `famRej` / `hold` | 各每秒 +390 | 几乎每个到达都被族门拒 |
| `arrivalsPerSec` | `620` | 与 19:39 局一致 |

#### 27.12.4 ★ 死锁确证：接管门的**两个**条件同时不满足

v1.11 接管门的条件（`FrameGen.cpp:1143`）：

```cpp
if (snapPubStale >= kCamPubStaleTol && snapForeignMove >= kCamForeignMoveTol)
```

| 条件 | 阈值 | 世界段实测 | 结论 |
|---|---|---|---|
| `snapPubStale` | `kCamPubStaleTol = 200` | `80`，每秒 +26 | 需 **7.7 秒**，世界段只 3.4 秒 |
| `snapForeignMove` | `kCamForeignMoveTol = 200` | **恒 0** | 被拒族位置恒定 ⇒ `fStep = 0` ⇒ 永不累计 |

⇒ **第二个条件是结构性的**：`snapForeignMove` 的累计（`FrameGen.cpp:1127-1139`）只在
「被拒族自己**在走**」时才增长。世界里被拒的是**停着的菜单相机**，所以它永远不会满足。
而且这个死锁是**安全的**（不会让菜单相机夺流）—— 这就是它一直没被发现的原因。

#### 27.12.5 锁在 124 ms 内被释放两次

```
[21:15:09.557] lock RELEASED on the reset edge (was proj00=0.149184 famRej=1095)
[21:15:09.681] lock RELEASED on the reset edge (was proj00=0.888889 famRej=1122)
```

进世界后 124 ms 内两次「重置边缘释放」，每次都由**释放后的第一个到达者**接管 ⇒ 两次都撞上
`0.888889` 族。**「释放后第一个到达」是一个没有准入检查的选择规则** —— 记在这里，本局不改。

#### 27.12.6 一条排除项：`non-affine w=0 ACCEPTED (v0.89)` 不是根因

```
[21:15:09.425] [CAM] #7148 non-affine w=0 ACCEPTED (v0.89)
  row3=(-0.00391655,0.999991,0.0015,0) det3=-2.52504 pos=(-243.0,-415.3,118.6)
```

回代码（`FrameGen.cpp:842-857`）：它打印的是 `CameraViewProjUnjittered`（**不是** `CameraProj`），
块尾是 `// NO return false` —— **只是计数器与日志，不改变任何控制流**；而 v1.13 的闸门查
`CameraProj.data[3][2]/[3][3]`（不同字段、不同条件）。**排除。**

#### 27.12.7 v1.15 的改动（纯诊断，零行为改动）

`tools/patch_v115_fammotionprobe.py` + `tools/patch_v115b_famtable.py`：

1. **删掉 v1.14 的 census**，换成**按族测位移**：16 个族槽，每槽记 `(proj00, lastPos, moved, stepSum)`，
   比较**相邻两次到达**的步长，`> kCamMoveEps(0.05)` 才计一次「在动」。
2. 每秒一条 `[CAM] FAM[n] proj00=… moved=… stepSum=…`。
3. `family rejected` 行：`pos` 精度 `{:.1f}` → `{:.4f}`，并加 `prevPos` 与 `row3` ——
   **1 位小数下「停着」和「在滑」看不出区别**，这正是 27.12.3 那条读不准的原因。
4. `[CAM] MOTION fam=… step=…` 打印前 60 次真实位移。
5. 族表满时**打印一次告警**（v1.15b），不再静默丢弃 —— 被丢的那个族很可能就是活相机。

#### 27.12.8 下一局的判据（一次读数定案）

| `[CAM] FAM` 读数 | 结论 | 修法 |
|---|---|---|
| 有族的 `moved` **持续增长** | 活相机**正在到达**这个 hook | 修**接受规则**（族锁 / 接管门），不改源 |
| 所有族 `moved=0` | 到达这个 hook 的**没有活相机** | 改**源**：`RE::PlayerCamera` |
| `[CAM] MOTION` 一行都没有 | 同上，更硬 | 同上 |
| `[CAM] FAM table full` 出现 | 有族没被统计 | 提高 `kSnapFamMax` |

**前置条件（不满足就是又白跑一局）：进世界后停留 15 秒以上，并且真的走动。**
19:39 与 21:15 两局的世界段分别只有 11.5 秒与 3.4 秒；`stalePub` 需要 7.7 秒才够阈值。

#### 27.12.9 交付物

DLL **1,349,120 B**、md5 `1178525c…`（build == 部署）；commit `8e28f05`、tag `v1.15probe`；
回退件 `src/backup-v1.15-20260919-211959/`（内含 **v1.14probe** 的 `built_DLL.bin`，md5 `39a41225…`）；
本局日志存 `docs/runlogs/2026-09-19-2115-*`。


## 28. 22:02 那局 + v1.16：不再推断，直接问引擎

### 28.1 22:02 那局：内容门是对的，4x 也是真的

构建 `Sep 19 2026 21:21:37`（v1.15b）。跑 53 秒：启动 22:01:48，菜单 22:02:22–22:02:37（15 s），
世界 22:02:37–22:02:41.8（**只有 4.5 s**），随后玩家退出。watchdog 尾：`frames=765 alive=1
presentAge=17ms silent=6ms`——**没有挂起、没有崩溃**，渲染循环一直是健康的。

| 项 | 实测 | 含义 |
|---|---|---|
| `DLSSG presented per real frame = 4 (status=0)` @22:02:37.524 | **4** | **4x 真的在产出**（菜单期是 1 = 不插帧，符合菜单门） |
| `real=38.25` fps | 38 | 帧率没问题 |
| `Reflex FLIP cap = 159 fps (6289us)` | 6289 | v1.12 的收益仍在 |
| `cap=2560/0` | 左涨右 0 | v1.13 内容门照常在丢弃正交写，逃生门未触发 |
| 菜单期发布流 | `pub #4495 pos=(-50.00,618.10,105.33) move=0.0562 path=54.89 frozenRep=0 stalePub=0 \| ok` | **相机链在菜单里是活的**（path 从 0 涨到 54.89） |
| `FAM[0] proj00=0.149184 moved=169 stepSum=54.99` | 菜单期逐秒增长 | 唯一会动的族是 0.149184（加载/主菜单的慢漂） |

### 28.2 但世界段：锁在一个恒定写者上，且接管门再次死锁

世界段四条 `[CAM] acc` **逐字节相同**：

    [CAM] acc #4572/#4598/#4625/#4652 pos=(0.00,0.00,1.00) move=0.0000 path=54.99
                                        devVP=2.0001 detVP=-2.25023 magVP=2 consecJmp=0

心跳：`frozen` 与世界帧数 1:1（29/30、59/64、89/94）、`clipDev=0.000000`、`clipW=1.000000`
⇒ `clipToPrevClip = I` ⇒ 插帧退化成复制。

过程的两次释放：

    #7343 lock RELEASED on the reset edge (was proj00=0.149184 famRej=1111)
    #7390 lock RELEASED on the reset edge (was proj00=0.8391  famRej=1114)

⇒ v1.07b 的"释放后由第一个到达者重采"在世界里**采到的是停车写者**（先 0.8391，再 0.888889）。
而被拒的族 `0.8391` 位置**恒定** `(-243.0493,-415.3115,118.5582)`，`still=4..1000/90`，
`famRej 1114 → 2671`（+390/s）⇒ **v1.11 的"移动的异族才能接管"永远不成立**（停车族的位移恒 0）。
死锁第二次被确证。

### 28.3 ★ 我自己的探针是坏的（两处），上一轮那张判据表不可信

1. **族键容差 2%**：两个投影略有差异的写者被并进同一个桶，它们的到达交错 ⇒ 位置读成巨大位移。
   铁证：`FAM[1] proj00=1 moved=765 stepSum=318990`，而世界段**没有任何东西在动**（平均 417 单位/步）。
2. **MOTION 明细行只有 60 行预算**，被菜单期 0.149184 的慢漂全部吃掉 ⇒ 世界段**一条明细都没有**。

⇒ 上一轮"所有族 moved=0 ⇒ 换源"是从**坏仪器**上读出来的判据，不能作数。
**L31：自造的量表凡是带容差，就可能把两个不同样本并成一个；读数一旦不代表任何单一对象，
就不能用来做判据。**

### 28.4 参考实现（CS）逐行对照：差异**不在**钩子，在 helper

- CS `src/Globals.cpp:217-265` 的 Map/Unmap 钩子与我们**逐字相同**：同一 REL ID `524768/411384`、
  同一对槽 14/15、同样是"记下最近一次匹配的 Map 指针，在 Unmap 时拷走再置空"。
  ⇒ **"取最后一个写者"不是我们独有的缺陷，CS 也这么做。**
- CS `src/Features/Upscaling/Streamline.cpp:235-264`：`cameraRight/Up/Fwd` ← `CameraViewInverse.Transpose()`，
  `cameraPos` ← `CameraPosAdjust`，`cameraViewToClip` ← `CameraProjUnjittered.Transpose()`
  —— **这三项和我们完全一样**。
- **真正的差异**：CS 在 flat（非 VR）分支调用 **Streamline 官方 helper `recalculateCameraMatrices(slConstants)`**
  （`extern/Streamline/include/sl_matrix_helpers.h:178`），由它重算 `clipToCameraView` / `clipToPrevClip` /
  `prevClipToClip`，并**自己维护上一帧的相机位姿**（`static cameraViewToWorldPrev` / `cameraViewToClipPrev`）。
  只有 VR 分支才自己算（因为 helper 的 prev 只有单槽）。
- 该 helper 通过 `calcCameraToPrevCamera`（同文件 154 行）**先把当前相机平移到世界原点再求逆乘**，
  注释明说这样是为了避开"大平移相加导致 fp32 精度崩塌"；而我们一直用 `inv(curVP) × prevVP`
  —— **正是它警告的那件事**（18:20 世界段的 `clipToPrevClip[3].w=170.324310`、22:02 的 `-195.222366`
  大概就是这个代价）。
⇒ **下一轮候选改动：flat 路径也交给官方 helper。**

### 28.5 为什么下一步是"问引擎"而不是"再猜一族"

我们每一道门都在**从写者身上推断**哪个是相机：族指纹、步长、冻结、接管……22:02 证明这条路会走进死锁。
而引擎可以**直接问**：`RE::PlayerCamera::GetSingleton()->cameraRoot->world.translate` 是活的相机眼位
（CS `src/Hooks.cpp:711-722` 就是这么取水面反射的相机位置用的），`CameraPosAdjust` 装的是同一个量。
⇒ 落在它 `kPcMatchTol = 20` 单位内的到达者，**就是**相机写。这是可判定的（L30），不是推断。

### 28.6 v1.16 改动（+ v1.16b 安全补丁）

`tools/patch_v116_pctakeover.py`（5 处，行为 1 + 诊断 4）+ `tools/patch_v116b_pcrefuse.py`（4 处）。

1. **行为**：`AcceptCameraSnapshot` 在锁块**之前**新增 ground-truth 块。读 PlayerCamera；每个到达者算
   `pcDist`；当 `pcDist <= 20` **且锁在另一个族上** ⇒ `snapLockHave = false; snapHaveLast = false`，
   让紧接着的正常 acquire 路径接纳它并发布，锁的族随之刷新成相机族。
   - "另一个族"这一条是防抖：否则相机锁上以后每来一个到达者都会掉锁，
     而 v0.93 已实测过掉锁的代价（`#7818/#7824/#7837 RELOCK`，`path=845264`，CTD）。
2. **v1.16b**：同一参考也用来**拒绝**——`snapPcEverMatched`（参考已自证：真有到达者落在 20 单位内）
   为真、`pcDist > 20`、且族与锁不同 ⇒ `return false`。没有这一条，当相机写在前、停车写在后时，
   每帧会发布一次停车矩阵 = v0.93 的交错源流。全部以 `snapPcEverMatched` 为门：
   **参考若永不匹配，这一版与上一版行为完全一致。**
3. **诊断**：每秒一行 `[CAM] PC v1.16: read= match= adopt=sec/total best= at proj00= eye=(x,y,z)`；
   族普查键收紧到 0.01%，每条加 `arr=`、`span=(x,y,z)`、`last=`。
   `span` 一个数就能分开三种群体：`0.0000` = 停车写者；小且 `moved≈arr` = 活相机；几百 = 合并过的桶。

### 28.7 下一局判据（一次读数定案）

| 看到什么 | 结论 | 下一步 |
|---|---|---|
| `[CAM] PC` 的 `best` 掉到几单位内、`adopt` 开始增长 | 相机写**确实在这个 CB 里**，v1.16 抓住了 | 看 `path`/`clipDev` 是否活了 |
| `best` 全程几百~上千、`match=0`、`adopt=0` | **相机写根本不在这个 CB 里** | 用 PlayerCamera 的位姿**合成**相机（pos=eye，right/up/fwd 取 `cameraRoot->world.rotate`，投影取已到达的族），并接官方 helper |
| `PC TAKEOVER` 出现但 `path` 仍不涨 | 源对了、装配有问题 | 换官方 helper（28.4） |
| `best` 在几百但 `read=0` | PlayerCamera 读不到（时序/线程） | 移到 Present 侧取参考 |

**前置条件：进世界后停留 15 秒以上并真的走动。** 22:02 世界段只有 4.5 s，与 19:39 的 11.5 s、21:15 的 3.4 s 一样，
**"玩家没动"和"锁在固定相机上"在日志里同形**，这是唯一无法从数据消歧的点。

### 28.8 交付物

DLL **1,352,192 B**、md5 `b21bd0f3be23b396c1f5ec0534447188`（build == 部署）、commit `437fadc`、
tag `v1.16`、回退件 `src/backup-v1.16-20260919-221351/`（内置 DLL md5 `1178525c…` = 跑过 22:02 那局的 v1.15b）。
本局日志 `docs/runlogs/2026-09-19-2202-v1.15probe-world-no-live-family.log`。

### 28.9 L0 两遍自检

**第一遍·手脚**：8/8 锚点 `count==1`；两个补丁脚本重跑都 `REFUSED`(exit 1)；
`FrameGen.cpp` 1887 CRLF / 裸 LF 0，`FrameGen.h` 473 / 0；`BUILD SUCCESS` 无 `error C*`/`LNK`；
DLL 双份 md5 一致；新串各 1 次；两条旧串（`[CAM] MOTION fam={:.6g}`、`cen={}/{}`）**0** 次；
关键旧串（v1.13 闸门、v1.12 限速器、DLSSNR CHAINED）各 1 次。

**第二遍·脑子**：本轮我自己踩了三个坑，全被断言/后置条件挡住，**没有一个落盘**——
1. `Path.read_text()` 会做通用换行转换 ⇒ CRLF 文本变 LF，锚点全部失配；
   更危险的是 `write_text` 会把整份文件写成 LF。干跑的后置条件抓到（未落盘）。
2. 预检用 LF 锚点去数 CRLF 文件 ⇒ 计数 0。**"行尾要按文件取"这条铁律又救一次。**
3. 我断言 `frameBufferCopy = a_src;` 出现 ≥2 次，实际**只有 1 次**——是断言写错，不是代码错。
   已改成 `==1`（发布点是唯一的）。

另外更正两处上一轮的叙述：①"最后写者"并非我们独有的缺陷（CS 同款钩子，见 28.4）；
②上一轮的判据表读自坏探针（28.3）。

## 29. 第 29 章　22:22 那局 + v1.17：**方向是反的——整整两天锁的是菜单相机**

### 29.1 那局的骨架（构建 Sep 19 2026 22:15:25 = v1.16）

| 时刻 | 事件 |
|---|---|
| 22:22:25 | 进程起 |
| 22:22:33 | Map/Unmap 钩子装好 |
| **22:22:56.967** | `LONG FRAME 20582.9ms` —— 载入的单帧卡了 20.6 秒 |
| 22:22:56.967 | `MENU EDGE open=1 serial=2` —— 主菜单出现 |
| 22:22:57→22:23:12 | 菜单期，668 帧，约 15 秒 |
| **22:23:12.473** | `MENU EDGE open=0 serial=670` —— 进世界 |
| 22:23:14.665 | 最后一行日志，**世界段只有 2.2 秒 / 34 帧** |

无崩溃转储，无 error/exception；最后 80 ms 还有 5 行正常帧日志
（`Reflex cap check` / `clipGate v0.92` 每秒两轮）⇒ **游戏到最后一刻都在正常渲染，
是用户主动退出的，不是崩溃。**

`mapHit(perFrame/unmap)=8303/8303` —— 钩子配对，没有丢 Unmap。

### 29.2 ★★★★★ 真值判据给出了**两个方向相反的判决**

v1.16 插的探针每秒打一行：

```
[CAM] PC v1.16: read=… match=… adopt=… best=… at proj00=… eye=(…)
```

| 时刻 | read | match | best | proj00 | eye |
|---|---|---|---|---|---|
| 22:23:02–08 | 74→392 | **0** | **603.99 → 835.51** | 0.149184 | (0.00,0.00,128.00) |
| 22:23:09 | 384 | 0 | 797.67 | 0.149184 | **(-243.05,-415.31,118.62)** |
| **22:23:10** | 366 | **154** | **0.00** | **0.8391** | (-243.05,-415.31,118.56) |
| 22:23:11–14 | 408–493 | 380–456 | **0.00** | **0.8391** | 同上 |

`best=0.00` 的含义：**`RE::PlayerCamera::cameraRoot->world.translate`
与那个到达者的 `CameraPosAdjust` 相距 0.00 单位**，而且是一秒 397 次。

三条 `PC TAKEOVER` 原文（第一次）：

```
[CAM] #5842 PC TAKEOVER (v1.16): this arrival is 0.00 units from the live player
camera pos=(-243.049,-415.315,118.624) pc=(-243.049,-415.315,118.624) proj00=0.8391
- dropping the lock so it re-acquires on this arrival
```

**⇒ `proj00=0.8391` 就是玩家相机。**
**⇒ `proj00=0.149184`（被真值判为 604～836 单位远）不是玩家相机。**

### 29.3 ★★★★★ 这是整个案件的根因，而且方向与 v1.00–v1.15 的结论**完全相反**

两天来我一直把 `0.149184` 当作「世界相机」、把 `0.8391` 当作「停着的 3D 菜单相机」。
真值说反了。逐条对照：

| 读数 | 我此前的解释 | 真值判决 |
|---|---|---|
| `0.8391` @ `(-243.0493,-415.3115,118.5582)` | 「场景固定的菜单机位」 | **玩家相机**（距真值 0.00，397 次/秒）|
| `0.149184` @ `(-50, 600→848, 65→69)` | 「世界相机 / 跟着玩家」 | 主菜单相机（离玩家 604～836 单位）|
| `0.8391` 的「不动」 | 「停着的写者」 | **玩家站着不动** |

`FrameGen.h` 里 v1.10 那条注释白纸黑字写着
**"The real camera (proj00=1) then walked (-125.7,210.8,188.4) -> (255.0,804.7,-94.4)"**
—— 那也是**推断**出来的，不是测出来的。已在该处插入 `CORRECTION (v1.17, 22:22 run)` 标注。

**★ 教训（写进 L32）：`proj00=1` 那个桶根本不是相机。**
22:22 局 `FAM[1] proj00=1 arr=500 moved=500 stepSum=542149.75 span=(974.79,901.49,86.68)
last=(-126.89,210.43,189.29)` —— 四秒内 `last` 只挪了 1.9 单位，`stepSum` 却累积 54 万。
⇒ 一个桶里至少装了**两个相距约 1000 单位的写者**，互相跳。
`kSnapFamKeyTol=1e-4` 对 `proj00 == 1.0` 是**精确相等** ⇒ 所有单位投影都并桶。
这个桶**能满足 v1.11 的 `kCamForeignMoveTol(200)`**，而它连相机都不是。
v1.00g 的同族 step-break 会**因为它的跳变**把锚交给它 —— v1.17 就是来堵这个洞的。

### 29.4 4x 与 DLSS5 的现场读数（都还在）

```
[FrameGen] FPS probe: real=25.9 | DLSSG | cap~=103.4 (=real*4, COMPUTED not measured)
           | hwMax=6 ask=4 accepted=4 | cfgProvider=1
[Streamline] Reflex cap check (v1.12): 159 flip fps on a 160Hz panel = 39.8 rendered fps at 4x
[XRAY] presented all=0/630/0/0/54/0/0/0   world=0/12/0/0/54/0/0/0   ⇒ 桶 4 有 54 帧
[FrameGen] DLSSNR: color=true engineDepthSRV=true engineMvec=true inputs=true
           frames=719 status=initialized
```
`real=25.9ms`（25.9 fps 渲染）× 4 ≈ 103 fps 呈现。**v1.12 的限速收益与 DLSS5 注册都还在。**

### 29.5 ★ 这一局**不能**判定冻结是否修好，原因是可测量的

世界段 4 条 `[CAM] acc` **逐字节相同**：

```
[CAM] acc #6093 pos=(-243.05,-415.31,118.56) move=0.0000 path=71.82
       devVP=15.0006 detVP=-2.52504 magVP=15.0006 consecJmp=0
```

心跳：`frozen=30/34`、`clipDev=0.000061`、`clipW=1.000000`、`det3=1.000000` ⇒ `clipToPrevClip = I`。

**但这一次 `I` 是正确的** —— 相机真值 `eye=(-243.05,-415.31,118.56)` 在
22:23:10→14.5 的五次采样里字节不变。相机没动，`clipToPrevClip` 就该是单位阵。

唯一的「动」是 `FAM[2] span=(0.0005,0.0036,0.0712)` —— z 方向 7 厘米，即**待机呼吸**。
⇒ **玩家站着没动，或者动不了。这两件事在日志里是同一个形状。**

### 29.6 ★ L32：我引入的 v1.16b 分支是死代码，是日志抓出来的

v1.16b 的拒收是这么挂的：

```cpp
if (pc && pc->cameraRoot) {
    ... 匹配 / 接管 ...
} else if (snapPcEverMatched && snapLockHave && <异族>) {   // ← 挂在 else 上
    ++snapPcReject; return false;
}
```

`else if` 挂在 **"没有 PlayerCamera"** 那条臂上 ⇒ **只有参考不可用时才会执行**，
而参考一直是可用的。证据：整局 `PC REFUSE` 计数 = **0**（`grep -ac "PC REFUSE"` = 0，
`rej` 在 v1.16 的 dump 里没打印，但 `snapPcReject` 从未增长）。

它还与下面 `!sameFamily` 那条**无条件 `return false`** 重复 ⇒ 就算挂对了也是多余。
**v1.17 把它删了**，改到唯一还有洞的地方（见 29.7）。

★ **教训：写 `else if` 之前先问「这个 else 属于哪个 if」。**
一个分支挂错父节点，行为 = 不存在，而它**看起来**像在保护什么。

### 29.7 v1.17 的改动（唯一行为改动：一处守卫）

真实漏洞有两条路，都通到「把锚交给非相机写者」：

1. **空槽获取** `if (!snapLockHave)` —— 22:02 局就是在 reset edge 之后由它拿到 `0.149184`；
2. **v1.00g 同族 step-break** —— 任何同族、步长超 `kCamStepTol` 的到达者都能重新拿锚，
   而 `proj00=1` 那个装着两个写者的桶正好满足（29.3）。

v1.17 在 acquire 之前放**一道守卫**，同时盖住三条路（空槽获取 / 异族下坠 / 同族 step-break）：

```cpp
bool pcIsThis = false;                      // 这一个到达者就是活相机
const bool pcKnown = snapPcRefSeen > 0u;    // 参考在最近 kPcRefHoldSec 秒内匹配过

// ... 真值块内，命中时：
snapPcRefSeen = kPcRefHoldSec;              // = 2
pcIsThis = true;

// ... accept 路径最前：
if (pcKnown && !pcIsThis) { ++snapPcReject; return false; }
```

**`snapPcRefSeen` 是秒级闩锁**：每次命中置 2，`[CAM] PC` 每秒减 1。
⇒ 参考一旦不再匹配，闩锁 2 秒内失效，**退回 v1.17 之前的行为** ⇒ **这道门不可能把锁锁死。**
（`return false` 不碰 `snapLastPos`/`snapHaveLast`，所以下一帧相机到达时流是连续的。）

**另加运动见证 `eyeD`**：`[CAM] PC` 末尾打印活相机在过去一秒走了多少单位，并给出判决词：

```
eyeD=… PC_STILL - the live camera did not move: an unchanged picture is CORRECT here
eyeD=… PC_MOVING - the live camera is walking
```

**这是为了让下一局无法再含糊** —— 「玩家没动」与「锁在停着的写者上」从此可分。

### 29.8 产物与回退

| 项 | 值 |
|---|---|
| DLL | 1,353,728 B，md5 `91493b4d2c5d7eaf89761e1b1f01eb3d`（build == 部署）|
| 源码 | `FrameGen.cpp` 95,713 B / 1939 CRLF / 裸 LF 0；`FrameGen.h` 27,564 B / 498 / 0 |
| commit / tag | `c36c693` / `v1.17` |
| 补丁脚本 | `tools/patch_v117_pcauthority.py`（9 条锚点全 count==1，干跑默认，重跑 REFUSED exit 1）|
| 回退 v1.16 | `src/backup-v1.17-20260919-222922/`（`built_DLL.bin` = `b21bd0f3…`）|
| 本局日志 | `docs/runlogs/2026-09-19-2222-v1.16-pc-takeover-works-world-2s-static.log` |

### 29.9 ★ 下一局的判据表（全部换成可判定的）

**前置条件（不满足就是白跑）：进世界后停留 ≥15 秒，并且真的走路。**

| 看到 | 结论 | 下一步 |
|---|---|---|
| `PC_MOVING` + `eyeD` 明显 > 0，且 `path`/`matChanges` 同步增长 | **源与装配都对，冻结已修** | 进下一步：DLSS5 上屏验证、20/30 系 |
| `PC_MOVING` 但 `path` 仍冻（`move=0.0000`） | 源对了、**装配**错了 | 换官方 `recalculateCameraMatrices()` / `calcCameraToPrevCamera()`（原点平移消 fp32 精度）|
| `PC_STILL`（`eyeD≈0`） | **这一局作废**，不是 bug | 重跑，必须走动 |
| `rej` 暴涨且 `ref` 长期为 0 | 参考不可用 ⇒ 闩锁失效、退回旧行为 | 看 `best=` 是否恒几百 ⇒ 相机不在 CB 里，改用 PlayerCamera 位姿自建 |

### 29.10 仍未证 / 未做的事（别假装做了）

- **冻结是否修好**：**未证**。22:22 局相机没动，无法判定。
- **DLSS5 输出上屏**：`status=initialized frames=719` 只证**在跑**，**未证上屏**。
- **RTX 20/30**：`grep -i xess` = 0，一行未写。
- **`CameraProj[0][0]` 与 `CameraProjUnjittered[0][0]` 互为倒数**（`1.1918`↔`0.8391`、
  `6.70312`↔`0.149184`、`1`↔`1`）：**仍未解释**。抖动只改 `[0][0]/[1][1]` 千分之几，
  不可能产生倒数关系 ⇒ 同一结构体里两条链取了两台不同相机的矩阵，或字段偏移是错的。
  它**不影响**族键（同族内两个值都自洽），但是个潜在雷。**先做成探针再改。**

## 30. 第 30 章　22:38 那局 + v1.18：**选源结了，但两天来第一次「没有可修的 bug」**

跑的是 **v1.17**（DLL `91493b4d2c5d7eaf89761e1b01eb3d`，1,353,728 B）。
开局 22:38:15，加载吃掉 21 秒（`LONG FRAME 20997.2ms`），菜单 22:38:47–22:39:01，
**世界段 22:39:01–22:39:03（约 2 秒 / 64 帧）**，用户在 22:39:03 退出。
日志 220,166 B / 1,804 行。归档 `docs/runlogs/2026-09-19-2238-v1.17-source-fixed-world-2s-no-input.log`。

### 30.1 ★★★ 选源问题终结：锁第一次站在活相机上

```
[22:38:59.586] [CAM] PC v1.17: read=389 match=289 adopt=1/1 rej=28 ref=2
               best=0.00 at proj00=0.8391 eye=(-243.05,-415.31,118.56) eyeD=0.07 PC_MOVING
[22:39:00.588] [CAM] PC v1.17: read=482 match=444 adopt=0/1 rej=66 ref=2
               best=0.00 at proj00=0.8391 eye=(-243.05,-415.31,118.56) eyeD=0.00 PC_STILL
[22:39:03.630] [CAM] PC v1.17: read=423 match=397 adopt=0/3 rej=152 ref=2
               best=0.00 at proj00=0.8391 eye=(-243.05,-415.31,118.56) eyeD=0.00 PC_STILL
```

`match/read ≈ 94%`、`best=0.00` 从 22:38:59 起每一秒都成立、`rej` 每秒 +30。
心跳 `lock(pub/hold/re/still)=5938/1/5/0 proj00=0.8391 famRej=0`。

**⇒ v1.00 的族指纹、v1.07b 的第一个到达者、v1.11 的接管门、v1.13 的内容判据、
v1.16 的夺锁 —— 全部是在错误的一侧修。v1.17 把 `RE::PlayerCamera` 从「选源依据」
升格为「唯一权威」之后，锁在 60 帧里**没有一帧**落在非相机族上。**
**⇒ 这是两天来第一个确定性成果，而且它是可测的（`match`/`best`/`rej` 三个数）。**

三次夺锁原文（`proj00` 都是 `0.8391`）：

```
[22:38:58.846] [CAM] #4988 PC TAKEOVER (v1.16): this arrival is 0.00 units from the live
               player camera pos=(-243.049,-415.315,118.624) pc=(-243.049,-415.315,118.624)
               proj00=0.8391 - dropping the lock so it re-acquires on this arrival
[22:39:01.188] [CAM] #6633 PC TAKEOVER ... pos=(-243.049,-415.312,118.558) pc=(同左)
[22:39:01.305] [CAM] #6681 PC TAKEOVER ... 同上
```

### 30.2 ★★ 族普查终于可信（v1.16 的 `kSnapFamKeyTol=1e-4` 生效）

```
FAM[0] proj00=0.149184 arr=376 moved=191 stepSum=376.23   span=(0.21,17.71,1.54)  last=(-49.50,824.49,89.46)
FAM[1] proj00=1        arr=216 moved=532 stepSum=332103   span=(980.84,530.17,11.28) last=(-952.21,886.25,103.16)
FAM[2] proj00=0.8391   arr=397 moved=0   stepSum=0.08     span=(0.0000,0.0000,0.0000) last=(-243.0493,-415.3115,118.5582)
FAM[3] proj00=0.888889 arr=26  moved=0   stepSum=0.00     span=(0,0,0)              last=(0.0000,0.0000,1.0000)
```

- **`FAM[1] proj00=1` 是两天来见过最凶的假写者**：`span x=980.84`（桶内至少两个写者，
  相距约 980 单位）、`stepSum` 每秒 +67,500、`last` 恒定 `(-952.2053,886.2523,103.1622)`、
  **`moved=532 > arr=216`**。它能满足 v1.11 的 `kCamForeignMoveTol(200)`，
  v1.00g 的同族 step-break 也会因为它的跳变把锚交给它 —— **v1.17 的门现在挡着它（`rej` +30/s）。**
- **`FAM[2]`（活相机）`moved=0`、`stepSum=0.08`、`span=(0,0,0)`** ⇒ 5 秒里累计只走 8 厘米。
  与 `eye` 逐字不变、`eyeD=0.00` 三处互相印证。
- `FAM[0]`（`0.149184`，主菜单相机）在世界段 `arr=0` —— **它已经不写了**，
  与 30.1 的结论一致。

**注意 `arr=` 是每秒值、`moved=`/`stepSum=` 是累计值**（`snapFamArrSec`/`snapFamSpanN`
每秒清零，`snapFamMoved`/`snapFamStep` **不清零**）。`moved > arr` 不是 bug，是两种量纲。

### 30.3 ★★★ 三个「差点误判」——L0 第二遍当场救回来三次

这一局我三次把**瞬时值**当成**累计值**，三次都推出完全相反的结论，三次都被回读代码推翻：

| 字段 | 我以为 | 实际 | 若没查会得出 |
|---|---|---|---|
| `inSetOptions={}` | 累计调用数 ⇒ 世界段从没调 `SetDLSSGOptions` | `g_inSetOptions.store(1/0)`（`Streamline.cpp:1981/1983`）⇒ **「此刻是否在函数内」** | 「DLSSG 没被喂」→ 去修一个不存在的问题 |
| `menuUnblockedFrames` | 总共只 unblocked 1 次 | `unblocked=1` 是**第一次 unblocked**（`DX12SwapChain.cpp:1386`，进入世界那一帧） | 「进世界后 `featureDLSSG` 掉了」→ 去修另一个不存在的问题 |
| `camPrev(ok/used)=1/60` | 重建 prev 只成功 1 次、失败 59 次 | `diag.camPrevOk` 是**赋值**（瞬时，`Streamline.cpp:1002`），`camPrevUsed` 是 `++`（累计，`:1063`） | 「prev 重建坏了」→ 第三趟白修 |

**⇒ 三者实际全部健康**：`camPrev` 60/60 全用、`featureDLSSG` 全程 true、
`SetDLSSGOptions` 无异常证据。**这一局日志里没有任何故障证据，每个指标都自洽。**

**⇒ 方法论（并入 L33）：一个「累计 / 瞬时」看错的字段，会凭空造出一个不存在的 bug。**
**声称某个计数器证明了什么之前，先去源头看它是 `= x` 还是 `++x`。**

### 30.4 ★★★★★ L33：判据只建在故障的下游，就无法命名故障

三次局面都一样、三次都读不出结论，根因不是代码，是**仪器的位置**：

```
[22:38:59.586] eye=(-243.05,-415.31,118.56) eyeD=0.07  PC_MOVING    ← 进世界那一秒
[22:39:00.588] eye=(-243.05,-415.31,118.56) eyeD=0.00  PC_STILL
[22:39:01.590] eye=(-243.05,-415.31,118.56) eyeD=0.00  PC_STILL
[22:39:02.619] eye=(-243.05,-415.31,118.56) eyeD=0.00  PC_STILL
[22:39:03.630] eye=(-243.05,-415.31,118.56) eyeD=0.00  PC_STILL
```

心跳三连：`frozen=60`（世界帧 64）、`clipDev=0.000061`、`clipW=1.000000`、
`curVP=15.0006 prevVP=15.0006`、`engPrevEqCur=61/61` ⇒ **`clipToPrevClip = I`**。
`det3=1.000000`，`[XRAY] clipGate v0.92: ... (rotation-only, expected ~1)`。
watchdog 全程 `alive=1 focus=1 presentAge` 个位数 ms、`dsync=0`、无崩溃转储
⇒ **游戏在正常出帧，没有死锁、没有崩溃。**

于是：

```
玩家站着不动      ⇒ 相机不动 ⇒ clipToPrevClip = I    ⇒ 画面不变【正确】
世界被引擎冻住    ⇒ 相机不动 ⇒ clipToPrevClip = I    ⇒ 画面不变【就是故障】
```

**两种世界，日志逐字节相同。** `eye` 是相机的**原点**，纯转视角不改它；
`matChanges` 60 帧只涨 2；`FAM[2]` 累计只走 8 厘米 —— 这些**都是下游量**，
它们只能证明「相机的输出没变」，**永远不能证明「是谁让它没变」**。

**⇒ 这就是两天读不出结论的唯一原因，而且不是代码问题。**
**⇒ 修法不是再调一个门，是换一个上游的见证。**

### 30.5 v1.18：四个上游见证（零行为改动）

`src/FrameGen.cpp` 的 `[CAM] PC` 行加 `in(keys= dc=/ fg=) plr=(…) plrD=`，
全部**在游戏之外**或在**玩家身上**，与相机链无因果关系：

| 见证 | 来源 | 能回答什么 |
|---|---|---|
| `keys` | `GetAsyncKeyState`（W/A/S/D/SPACE/SHIFT/LMB/RMB），每次到达采样、**按秒 OR** | 这一秒有没有输入进窗口 |
| `dc` / `{}` | `GetCursorPos` 的每秒累计距离 / 变动次数（`ClipCursor` 下系统光标仍在裁剪矩形内移动） | 有没有转视角（**`eye` 是原点，转视角不动它**） |
| `fg` | `GetForegroundWindow()` 的 PID 与本进程比对 | **Skyrim 失焦会暂停世界** ⇒ `fg=0` 直接就是答案 |
| `plrD` | `RE::PlayerCharacter::GetSingleton()->GetPosition()` 每秒位移 | 玩家本体有没有动（既非相机也非输入） |

判据词从 1 个变 2 个，日志自己给出结论：

```
PC_STILL INPUT_NONE  ⇒ 玩家没动，本局不判定任何东西，重跑（必须走动）
PC_STILL INPUT_SEEN  ⇒ 输入到了窗口而世界没动 ⇒ 真故障
PC_MOVING …          ⇒ 正常
```

**⇒ 这一局如果是 `PC_STILL INPUT_NONE`，那就是「本局作废」，而不是「还没修好」——
这是两天来第一次能把这两件事分开。**

### 30.6 下一局判定表

| 看到 | 结论 | 下一步 |
|---|---|---|
| `fg=0` | 窗口失焦 ⇒ 世界暂停（朴素解释，插件无责） | 查 ForceBorderless/焦点抢占 |
| `PC_STILL INPUT_SEEN` | 输入到达但世界冻结 | 查引擎暂停态（菜单/控制台/加载） |
| `PC_MOVING` + `path`/`matChanges` 同步涨 | **源与装配都对，冻结已修** | 转 DLSS5 上屏 + 20/30 系 |
| `PC_MOVING`（或 `plrD>0`）但 `eyeD=0` 且 `clipDev=0` | **源对了、装配错了** | 换官方 `recalculateCameraMatrices()`（原点平移消 fp32 精度塌陷，见 §29.6） |
| `PC_STILL INPUT_NONE` | **本局作废，不是 bug** | 重跑，**停留 ≥15 秒并真的走路** |

### 30.7 仍未解释（不动它，先做探针）

`CameraProj[0][0]` 与 `CameraProjUnjittered[0][0]` **互为倒数**：`1.1918`↔`0.8391`、
`6.70312`↔`0.149184`。抖动只改千分之几，**不可能产生倒数关系**。
族键不受影响（同族内两个值自洽），但这是个潜在雷。**先做成探针再改。**

### 30.8 产物与回退

| 项 | 值 |
|---|---|
| DLL | 1,356,800 B，md5 `03b8e540cc9e0e91f9a280afd5db57fa`（build == MO2 部署） |
| 源码 | `src/FrameGen.cpp` 95,713 → **99,492 B**，CRLF 2,027 / 裸 LF **0** |
| 补丁 | `tools/patch_v118_inputwitness.py`（4 锚点，干跑 → `--apply`，重跑 REFUSED） |
| git | commit `c940ef9`，tag **`v1.18`** |
| 回退 DLL | `src/backup-v1.18-20260919-224153/built_DLL.bin`（= v1.17，1,353,728 B） |
| 回退源码 | `git checkout v1.17 -- src/FrameGen.cpp` |
| 判据表作废 | **无**（v1.18 只加读取，不改任何门） |

### 30.9 v1.18b：`plrD` 的语义修正（**L0 第二遍抓到，编译器抓不到**）

v1.18 落盘并提交之后、交给用户之前，第二遍自检发现 `s_plrStep` 是**每次到达赋值**：

```cpp
s_plrStep = std::sqrt(qx * qx + qy * qy + qz * qz);   // v1.18，错
```

而它**旁边两个见证都是累计 + 每秒重置**（`s_inKeys |= keys;`、`s_inDist += cstep;`），
`AcceptCameraSnapshot` 每秒跑约 400 次 ⇒ **`plrD` 实际是「两次到达之间（约 2.5 ms）的位移」**，
走动时约 **7 毫米** —— 而字段名、卡片、账本 §30.5 都写着「每秒」。

**⇒ 判据 `plrD > 0` 仍然成立，所以这个错会一直活着**：一个量错了区间的数仍然能回答
「玩家动了没有」，只在回答「多快」时出错。**但这正是 L33 的同一个病**——
§30.3 已经记了三次「慢性/瞬时看错」，这里是第四次，只不过这次是在**改动刚落盘、用户还没跑**时被抓到。

**⇒ 改的是字段，不是注释**（v1.18b 把 `=` 改成 `+=`，并把 `s_plrStep = 0.0f;` 加进每秒重置块）。

| 项 | v1.18 | v1.18b |
|---|---|---|
| DLL | 1,356,800 B `03b8e540cc9e0e91f9a280afd5db57fa` | 1,356,800 B **`944408598434db4c00ec0aef4c93aa94`** |
| `FrameGen.cpp` | 99,492 B（CRLF 2,027） | **99,971 B（CRLF 2,034 / 裸 LF 0）** |
| commit / tag | `c940ef9` / `v1.18` | **`81b73ec` / `v1.18b`** |
| 补丁 | `patch_v118_inputwitness.py` | + **`patch_v118b_plrd_cumulative.py`**（2 锚点，重跑 REFUSED） |

**回退到 v1.18**：`git checkout c940ef9 -- src/FrameGen.cpp`（DLL 回 v1.17 用
`src/backup-v1.18-20260919-224153/built_DLL.bin`）。
**⇒ 交付给用户的版本是 v1.18b，`docs/diagnosis-20260919-2238-v118-*.html` 的页脚已同步。**

### 30.10 一条给下一局的备注：`fg` 只在「有到达」时更新

`fg`（前台窗口 PID）的采样点在 `AcceptCameraSnapshot` 里，所以**它只在捕获到相机到达时才更新**。
若游戏**彻底失焦到不再产生到达**，`[CAM] PC` 行本身也不会打 ⇒ **`fg=0` 这种情况下看不到。**
**⇒ 那种情形看 watchdog 的 `focus=` 字段**（它独立于本插件，每秒一行）—— 两者互补，别只看一个。

## 31. 第 31 章　22:54 那局 + v1.19：**用户一句「怎么动啊」把两天的问题换掉了**

### 31.1 决定性的一句

问用户「你说的『卡』，画面到底是哪一种」，四个选项里他选了 **「画面完全定死」**；
问「那 7 秒内你有没有按过键盘」——**「画面卡死了，怎么动啊？」**

**⇒ 这一句把 v1.18 的整个前提推翻了。** 22:02 / 22:22 / 22:38 / 22:54 四局，
世界段分别只有 4.5 / 2.2 / 2 / 6.8 秒、`keys=0x0`、`dc=0`、`plrD≈0` ——
**那不是「玩家站着不动」，是「画面从进世界那一刻就定死，用户看了一眼就强退」。**
`keys=0x0` 是**结果**，不是证据：一张不变的脸不会让人想去按键。

**⇒ v1.18 加的那四个「上游见证」回答的是一个没人问的问题。**
L33 描写的那层含糊（「玩家没动」与「世界冻结」同形）消失了，
换上来一层更利的：**渲染循环活着，画面不活。**

### 31.2 新判据表：这一层含糊住在「游戏边界」的两侧

| 事实 | 来源 | 说明 |
|---|---|---|
| `watchdog: alive=1 focus=1 presentAge=13/0/1/36ms frames 528→643 dsync=0` | 独立线程 | **渲染循环全程活着**，30 帧/秒 |
| 日志在 `22:55:06.773` **句中截断**，无 shutdown、无崩溃转储 | 两个日志文件 | **进程是被强杀/卡死后杀掉的** |
| `eye=(-243.05,-415.31,118.56)` 逐字不变 | 相机链 | 相机不动（但那是结果） |
| `clipDev=0.000061 clipW=1.000000` ⇒ `clipToPrevClip=I` | 相机链 | 画面＝重复上一帧 |
| `DLSSG presented per real frame = 4 (status=0)`、`mult(acc/pres)=4/4` | 插帧 | **4x 一直在产出** |
| `DLSSNR frames=539 status=initialized version=310.8.0.0` | DLSS5 | **NR 一直在跑** |

**⇒ 渲染线程活着 + 画面定死 + 每一个真实帧都被 4x 复制** = 只有一种形状：
**喂给 DLSS-G 的那张彩色缓冲是陈旧的。**

### 31.3 ★★★ INI 自己写明了机制（这是本轮最重的一条）

`DynamicShaderFrameGen.ini` 第 214–222 行，v1.01 自己的注释：

```
; 1 = NR runs first on the real frame and DLSS-G then interpolates the
;     neural-rendered result. The order is already correct in Present()
;     (NR writes swapChainBufferWrapped, which is what EvaluateDLSSG reads,
;      with the D3D11->D3D12 fence between them).
; Start at 0 if the picture flickers; raise NRRenderScale cost awareness
; first - full-resolution NR on every frame is the expensive part.
NRAllowWithFrameGen=1
```

**「NR 写 `swapChainBufferWrapped`，而 `EvaluateDLSSG` 读的就是它」** ——
**NR 的写入如果不落地（fence/互操作失败），DLSS-G 每个真实帧读到的都是同一张陈旧缓冲
⇒ 画面完全定死，而 `Present` 一直成功、`presentAge` 一直正常。**

**⇒ 这正是观测到的形状。而且 `NRAllowWithFrameGen` 是 v1.01 才有的，
它之前的任何版本都没有这条串联——与「冻结从 MFG 这条支线开始出现」完全吻合。**

### 31.4 v1.19 做了什么（零行为改动，只读）

| 见证 | 取法 | 能回答 |
|---|---|---|
| `hrsD` | `RE::Calendar::GetSingleton()->GetHoursPassed()` 的每秒增量 | **游戏逻辑在不在跑** |
| `rawD` | `Calendar->rawDaysPassed * 24` 的每秒增量 | 同上，**另一条路**取同一个量 |
| `paused` | `RE::UI::GetSingleton()->GameIsPaused()` | 游戏自己说暂停没有 |
| `ld` / `fade` | `IsMenuOpen("Loading Menu")` / `("Fader Menu")` | 卡在加载/黑屏淡入淡出没有 |

**两个时钟是有意取两条路**：`GetHoursPassed()` 走 `gameDaysPassed` 这个 TESGlobal，
`rawDaysPassed` 是引擎自己累加的裸 float。**任一个在动就是证明；两个同时不动才是结论。**

**⇒ 判据：**
- `hrsD > 0` 而画面仍定死 ⇒ **游戏在模拟，陈旧的帧是我们的**（⇒ 查 NR→DLSSG 的交接）。
- `hrsD == 0` 而 watchdog 仍在出帧 ⇒ **游戏被暂停** ⇒ 那么「两天在追的
  `clipToPrevClip=I`」只是**症状**，不是病。

### 31.5 两处我自己的错（都在落盘/编译阶段被拦住，没进游戏）

**① `GetKeyboard()` 拖垮链接（14 个 LNK2001）。** 引擎侧按键见证
（`RE::BSInputDeviceManager::GetSingleton()->GetKeyboard()->IsPressed(...)`）
会让链接器从 `CommonLibSSE.lib` 里拖出 `BSWin32KeyboardDevice.cpp.obj` 与
`BSKeyboardDevice.cpp.obj`，这两个 TU 引用了 14 个 `RE::BSInputDevice` 的虚函数，
而预编译库里没有它们的定义。**⇒ 整个见证删掉**（OS 侧 `GetAsyncKeyState` 已经回答了
「有没有按键」，它是四个里最不重要的一个）。

**② 我把 `L(...)` 的闭合括号写成了字符串。** 手写 `Edit` 时把

```python
    "\t\t\t\t\tstatic bool  s_liveRawHave = false;",
)
```

写成了 `")"` ——**闭合括号变成了一个字符串**，于是 `L(` 永不闭合，
`ast.parse` 报 `'(' was never closed line 52`，而**词法器扫描显示「未闭合的括号在第 52 行」**，
肉眼看那一行完全正常。

**⇒ 新增强制步骤：任何补丁脚本，在运行它之前先 `ast.parse` 它自己。**
```bash
python -c "import ast;ast.parse(open('tools/patch_xxx.py',encoding='utf-8').read());print('syntax OK')"
```
**⇒ 根因是同一类：我手写补丁文本。凡是手写的，必须先过机器（词法器/编译器）再看结果。**

### 31.6 ★ L35：v1.18b「修」了一个不存在的 bug

v1.18b 把 `s_plrStep = sqrt(...)` 改成 `+=`，理由写在 commit 里：
「`AcceptCameraSnapshot` 每秒跑约 400 次，所以赋值让 `plrD` 变成两次到达之间（~2.5ms）的位移」。

**⇒ 这个前提是错的。** `AcceptCameraSnapshot` **函数**确实每秒被调用约 400 次，
但那段见证代码在**每秒执行一次的块**里（与 `snapPcRead = 0;`、pub 行、FAM 普查同块）。
实测佐证：日志里 `[CAM] PC` 每秒恰好一行，`read=425` 是「这一秒内读了几次」。

**⇒ `=` 与 `+=` 在这个位置等价**（一秒只加一次）。v1.18b 无害，但它是**多余的**。

**⇒ L35 = L34 的第三种形态：L34 是「读错了字段的语义」，
L35 是「读错了代码的位置」——**同一个我在同一天里第三次拿「函数」当「代码块」**。
**⇒ 强制检查项：给别人报一个数值的量纲之前，先确认那段代码在**哪个块**里，而不是它在哪个函数里。**

### 31.7 本轮的 Experiment（INI，一行，可秒退）

```ini
NRAllowWithFrameGen=1   →   NRAllowWithFrameGen=0
```
- 备份：`src/backup-ini-20260919-2310/DynamicShaderFrameGen.ini.bak`（md5 `a19307d47caeb513b9ef6a16c4a83a42`）
- 改后：md5 `ed9655ad2bd0d2576d7f7e9d200a3f4c`（CRLF 259 / 裸 LF 0，14,525 B）
- 一行还原：`cp src/backup-ini-20260919-2310/DynamicShaderFrameGen.ini.bak "<MO2>/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini"`

**为什么这一行值得先试**：v1.19 是**零行为改动**，所以这一次的运行里
「若画面活过来 ⇒ 一定是 NR↔DLSSG 串联这条」是**无歧义**的；
「若还是定死 ⇒ 不是它」，同时我们拿到了 v1.19 的存活数据。
**两种结果都有信息，没有白跑的可能。**

### 31.8 版本

| 项 | 值 |
|---|---|
| DLL | 1,357,824 B md5 `df726bcd8ce70d800b9d01fc6f45c06f`（build == MO2 部署）|
| `FrameGen.cpp` | 99,971 → **102,934 B**（CRLF 2,098 / 裸 LF 0）|
| commit / tag | `dd1b004` / **`v1.19`** |
| 补丁 | `tools/patch_v119_liveness.py`（4 锚点，干跑默认，重跑 REFUSED）|
| 归档 | `docs/runlogs/2026-09-19-2254-v1.18b-hard-freeze-from-world-entry.*` |
| 回 v1.18b | `git checkout v1.18b -- src/FrameGen.cpp` |
---

# 32. 23:22 那局：NR 结案、4x 证实、以及我回去跑了两天前就该跑的那一步

**运行**：`2026-09-19 23:22:33` 起 · 构建 `Sep 19 2026 22:31:04`（v1.19）· DLL 1,357,824 B `df726bcd8ce70d800b9d01fc6f45c06f`（build == MO2 部署）
**INI**：`Provider=1` · `MFGMaxFramesOverride=3` · `NRAllowWithFrameGen=0`（v1.19 实验值）
**归档**：`docs/runlogs/2026-09-19-2322-v1.19-nr-exonerated-known-good-control.{log,watchdog.log,transfusion.log,transfusion-crash.log}`

## 32.1 ★ NR 被排除（第 31 章的头号嫌疑作废）

日志原文：

```
[23:22:45.050] [FrameGen] DLSSNR: color=true engineDepthSRV=false engineMvec=false inputs=false frames=0 status=not-probed
[23:22:45.050] [W] [FrameGen] DLSSNR skipped: shared depth/mvec not ready (depthWrapped=false mvecWrapped=false srv=false)
[23:23:04.966] [W] [FrameGen] DLSSNR suppressed: frame generation is active -
               NR and DLSS-G are two temporal processors and stacking them is a
               direct flicker source (v0.42 note: revert to mutual exclusion if it f...)
```

⇒ `NRAllowWithFrameGen=0` **确实生效**（NR 被完全压制），用户反馈**「还是老样子」**。
**⇒ 第 31 章第 3 节的「NR 写 swapChainBufferWrapped，DLSS-G 读它」这条链不是冻结原因。结案。**

**方法论**：一个「INI 自己写明的机制」听起来再合理，也只是**假设**；只有把开关真的翻过去、再拿到同样的故障，才能把它变成**否定**。这次翻对了。

## 32.2 ★★ 三件被证实的好事（其中之一推翻用户自己的判断）

| 事实 | 原文 | 含义 |
|---|---|---|
| **游戏时钟在走** | `LIVE ... hrsD=0.005342 → 0.005466 → 0.005376 → 0.005613 → 0.005609` | 0.0055 游戏小时/秒 × 3600 = **19.8 游戏秒/真实秒 = timescale 20**。游戏在**正常模拟** |
| 三个开关同时为假 | `paused=0 ld=0 fade=0 menuOpen=0` | 没暂停、没卡 Loading Menu、淡入淡出已结束 |
| **渲染循环健康** | `real=25.51ms`、`dt min/avg/max=23.73/25.54/30.10ms`、`longFrames=0`、无崩溃转储 | ~39 真实帧/秒，零长帧 |
| **4x 真的在产出** | DFG：`presented per real frame = 4 (status=0)`、`mult(acc/pres)=4/4`<br>Transfusion：`DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)` | **两个独立插件互相印证 4x 成立** |
| 解锁器是活的 | `Intercepted slDLSSGSetOptions`、`Active DLSS-G wrapper provider: patched=1`、arch gates `0x1b0 -> 0x190 (Ada)`、`Kernel: Ada`、`D157 midpoint fix: ... redirected 8 dlfg_kernel descriptor(s) ... (127200 bytes)` | Transfusion hook 正常 |

**⇒ 用户「四倍帧生成感觉也没成功」这一条被**硬证据否定**：4x 成功。感觉不到是因为画面不动。**

**⇒ `hrsD` 是本项目第一个「与用户手指无关」的存活见证，它把第 30 章的「引擎半死」分支也否掉了。**

## 32.3 ★★ 两件被证实的坏事，以及一个新的独立证人

| 事实 | 原文 |
|---|---|
| 进世界后相机一帧没动 | `frozen=30/30 → 60/60 → 90/90`、`clipDev=0.000061`、`eyeD=0.00`、`pos == prevPos` |
| 玩家坐标也没动 | `plr=(-250.3,-360.4,-0.0) plrD=0.00`，秒秒逐字相同 |
| **第二个独立证人** | Transfusion 自己的运动追踪：`[MOTION] route=slSetConstants call=1..3 clipToPrev=identity prevToClip=identity` ⇔ DFG 的 `clipDev=0.000061` |
| 世界段只有 4.5 秒 | 进世界 `23:23:30.518` → 日志断在 `23:23:34.948`（句中截断，无 shutdown 行） |
| 这 4.5 秒 OS 层面零输入 | `in(os=0x0 dc=0/0 fg=1)` 全程 |

**★ 新的交叉验证价值**：Transfusion 是**第三方独立实现**，它也独立算出「clipToPrev = identity」。
**两条独立的代码路径得出同一结论 ⇒ 「相机静止」这个事实本身是可靠的，不是我的代码算错。**

**★ 但 `frozen`/`clipDev`/`clipToPrev` 三者都**源自相机** ⇒ 它们**永远无法区分**
「相机静止（画面本来就该静止）」和「画面陈旧（相机在动也看不到）」。
**这是一整类见证的结构性盲区：全部由一个上游量派生，就没有独立性可言。**
（第 31 章记过同构的错误：「用僵死常量做门 = 空操作」。这次是「用单源派生量做结论 = 无法证伪」。）

## 32.4 ★★★ 我回去跑了账本自己写着的「一秒回到可玩」

账本从两天前就写着：

```
一秒回到可玩：Provider=0 + MFGMaxFramesOverride=0（只改 INI，不改代码）
```

**我从未让用户试过。** 两天里我一直在给 v1.07 → v1.19 堆见证，而没有先回到已知良好基线。

现在应用（`tools/patch_v120_ini_known_good.py`，三行，锚点 count==1，CRLF 261 / 裸 LF 0）：

| 键 | 改动 | 依据 |
|---|---|---|
| `Provider` | `1` → `0` | INI 注释：`0 = FSR3 tech - universal, works on ALL GPUs (NVIDIA & AMD) - default, most stable` |
| `MFGMaxFramesOverride` | `3` → `0` | INI 注释：`0 = off, follow the hardware report exactly (default, always safe)` |
| `NRAllowWithFrameGen` | `0` → `1` | 把 DLSS5 让回来，凑成用户自己说过「已经做到了」的那套 |

⇒ **现在的配置 = 「FSR3 两倍帧生成 + DLSS5」—— 用户明确说过这是他之前已经跑成过的组合。**
这是一次**已知良好配置的复现**，不是新猜测。

备份 `src/backup-ini-20260919-2327/DynamicShaderFrameGen.ini.bak`（原 md5 `ed9655ad2bd0d2576d7f7e9d200a3f4c`）
改后 md5 `478bb555acd84b1e5c101a098c0607f0`（14,559 B）。

**⚠ 注意**：`Provider=0` 后 FSR3 的 `numGeneratedFrames` 是硬编码 1 ⇒ 这次是 **2x，不是 4x**。这是**诊断用的对照组**，不是目标配置。

## 32.5 下一次运行的读法（一刀两半）

| 看到 | 结论 | 下一步 |
|---|---|---|
| 画面活了、能走 | 冻结是 **DLSS-G / 多倍** 支线独有（与「v0.39–v0.50 正常，MFG 引入故障」吻合） | 回 `Provider=1`，只在 MFG 分支内二分 |
| 还是定死 | 冻结**不在**帧生成这条路上 ⇒ 插件之外（ENB / 其他模组 / 存档 / 驱动） | 停手改插件 |
| `os=0x…` 有值 且 `plrD>0` | 输入通路通，之前「卡」是 4 秒的印象 | 继续玩看极限 |
| `os=0x…` 有值 但 `plrD=0.00` | 键按到了 OS，游戏不收 ⇒ 输入被拦 | 查拦截者 |
| 按住 W 仍 `os=0x0` | **探针本身坏了** | 换探针，别再拿它当证据 |

**运行协议（必须）**：① 进世界站着不动 15 秒；② 再按住 W 走 5 秒以上；③ 再退。
上次世界段只有 4.5 秒 + 零输入 ⇒ 我分不清「没按」和「按了没进去」。

## 32.6 还没解释的一条（记下，不硬凑）

Transfusion 的 `[PERF]` 行里 `Jitter`：加载期 `6.41 → 2.53 → 1.43 → 1.67ms`，
世界加载前后变成 **`51.14ms` → `51.26ms`** —— 抖动量放大约 30 倍并**停在那里**。
可能只是加载余波，也可能是呈现路径在抖。**无证据说它是原因。**

`DLSSG-Transfusion.crash.log` 于本轮被写出（29,526 B，23:23），但**只有 213 行模块表、零条异常记录** ⇒
**这一局没有 first-chance 异常**。已排除。

## 32.7 家族普查（本轮新增一列观察）

```
FAM[0] proj00=0.149184 arr=0   moved=225 stepSum=315.32   last=(-53.5172,785.1725,80.0000)
FAM[1] proj00=1        arr=320 moved=868 stepSum=515194.00 span=(719.5,895.6,171.8)
FAM[2] proj00=0.8391   arr=550 moved=0   stepSum=0.08     last=(-243.0493,-415.3115,118.5582)   <- 锁定目标
FAM[3] proj00=0.888889 arr=74  moved=0   stepSum=0.00
```

一秒之间：`FAM[1] stepSum 420391 → 515194`（**+94,803/秒**，即 ~592 单位/步）——**噪声族**，
不是相机。`FAM[2]`（锁定目标）`stepSum` 不变。
**`FAM[0] (0.149184) arr=0`** —— 上一局那个在动的相机（y 900→807）这一局**彻底不再提交**。

**⇒ 上一局 `proj00=0.149184` 被我记作「WORLD 族（随玩家动）」，现在看这个标注站不住：**
本局 `0.149184` 出现在 **`eye=(0.00,0.00,128.00)`**（加载期空相机）上，`best=603.99`（远离地面真值）。
**⇒ 旧族标签需要重标，别再拿「0.149184 = 世界相机」当前提。**

---

# 33. v1.21 — 「4x 的请求从来没有被发出去过」

一句话：**22:54 那局 4x 之所以没有出现，不是运行时拒绝了它，而是我们一帧都没往 DLSS-G 递。**
两条独立机制，各自有自己的日志原文；外加一条把用户配置吃掉的写盘缺陷。

## 33.1 先把提供者切开（本轮唯一的新对照）

| 时间 | Provider | NR | 画面 | 插帧实测 |
|---|---|---|---|---|
| 22:54 | 1 DLSSG | chained | **完全定死** | 尾段 `presented per real frame = 4` |
| 23:22 | 1 DLSSG | suppressed | **仍然定死** | `4x`（Transfusion 互证）|
| 23:38 | **0 FSR3** | chained | **活了**（闪烁、~60 显示帧）| `numGeneratedFrames=1 outputsFilled=1/4` |

⇒ **冻结是 DLSS-G 这条支线独有**，不是「帧生成」这件事本身的属性。
⇒ 同时把上一章的头号嫌疑（NR↔DLSS-G 串联）和「引擎半死」两条线正式封棺。

**23:38 局的第一手数字（v1.19 见证，全部只读）**：
```
hrsD=0.004220 → 0.005553 → 0.005707 → 0.005929 → 0.006657 …（每秒）
paused=0 ld=0 fade=1  menuOpen 无
[W] [DLSSNR] D3D12 command contexts saturated; applying CPU backpressure
[FrameGen] DLSSNR: frames=179 → 359 → 539 → 719 → 899 …（每 180 帧一条，≈36/s）
[FrameGen] FPS probe: real=27.8 | FSR3 | cap~=55.6 (=real*2, COMPUTED not measured)
[FidelityFX] FG dispatch desc: numGeneratedFrames=1 outputsFilled=1/4 frameID=0,300,…,1500
```
- `hrsD×3600 = 19.8 游戏秒/真实秒` ⇒ **timescale 20，游戏在正常模拟**。
- `frameID` 41 秒走 1500 ⇒ FSR3 **每个真实帧都 dispatch**，而 `numGeneratedFrames=1` 是**后端填的**，
  我们只读不写（`FidelityFX.cpp:121-136` 的注释就是为这件事写的）⇒ **FSR3 天花板就是 2x，这是 API 事实不是 bug**。
- `outputsFilled=1/4` 是 FidelityFX 后端只给了 1 个 output，与上一条同源。

## 33.2 机制一：**菜单闸门被「淡出菜单」永久按住**（这是 4x 不出现的直接原因）

22:54 局自己的日志，三行放在一起读：

```
[22:54:56.062] [MFG] stall governor: frame took 346 ms ... step held at 4x, accepted 4x
[22:55:04.060] [MFG] probe edge: menu guard released, SetDLSSGOptions resumes on this frame
[22:55:04.060] [MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu guard
               is not engaged (menuBlock=0 frames=0 blocked=571 unblocked=1)
[22:55:04.324] [Streamline] DLSSG presented per real frame = 4 (status=0)
```

- **`blocked=571 / unblocked=1`** ⇒ `menuBlock` 在 572 帧里真了 **571** 帧。
- 这条 `if` 链（`DX12SwapChain.cpp:1413-1429`）：`menuBlock==true` ⇒ **`SetDLSSGOptions` 与
  `EvaluateDLSSG` 都不调用** ⇒ `dlssgOk=false` ⇒ 走「直通兜底」拷贝。
- 结果是 `presented per real frame = 1`（全程）——**没有插帧**。
- **闸门一放开，0.3 秒后同一份日报告诉我们 `4`。** 因果链就在这一行里。

那到底是什么菜单？22:54 的 MENU PROBE：

```
[XRAY] MENU PROBE ... IsMenuOpen(is)=false/false/false IsMenuOpen(literal)=false/false/false
[XRAY] MENU EDGE open=1 serial=2 presentedBefore=0 consts(ok=0 fail=0)
[XRAY] MENU EDGE open=0 serial=573 …
```
⇒ **serial 2 那一刻，所有真实菜单都是关的**，而闸门是开的 ⇒
`GameMenuOpenNow()`（`Streamline.cpp:386-405`）里唯一能成立的就是**最后那一项 `IsMenuOpen("Fader Menu")`**。

而 23:38 局（v1.19 埋的 `fade`）证明**淡出菜单在玩家位于世界时全程为真**：
`fade=1` 连续 40+ 秒，同时 `paused=0 ld=0` 且时钟在走。

**⇒ 一句话结论：`MenuDisableFrameGen=1` + 把 `Fader Menu` 当菜单 ⇒ 在世界里闸门是永久的 ⇒
DLSS-G 从来拿不到帧。** 用户那句「四倍帧生成感觉也没成功」——**在这一局里是准确的**。

### 为什么不能直接把 `Fader Menu` 删掉
账本 `v0.96` 记着：删掉它**进不去游戏**（已回退）。22:54 的 PROBE 解释了为什么：
**它就是启动期的唯一保护**（serial 2 只有它在开）。
⇒ v1.21 的规则：**淡出菜单只在「我们还不该在世界里」时算菜单**——
`Loading Menu` 开着，或进程前 90 秒。真实菜单（Main/Loading/Journal/Pause/RaceSex）照旧照算。

## 33.3 机制二：**v0.75 拆掉的那道跨 API 围栏**

22:54 的看门狗尾部（每 0.2 秒一条）：

```
22:55:04.415 frames=581 … lastPr=584
22:55:04.616 frames=586 … lastPr=604     ← 开始分叉
22:55:05.017 frames=597 … lastPr=648
22:55:06.858 frames=643 … lastPr=832     ← 68 个真实帧，多了 190 次 present
dsync=0（全程）
```
- `lastPr` = DXGI 自己的 present 计数，`frames` = 我们的真实帧计数。
  **差值在 2.5 秒内从 3 长到 189** ⇒ **4x 真的在上屏**（同时 `dsync=0`，说明后缓冲索引在推进）。
- **可是画面不动。** ⇒ 推的是**同一张内容**。

`DX12SwapChain.cpp:1289`：

```cpp
static constexpr bool kD3D12WaitsOnD3D11 = false;   // v0.75 拆掉的
```
- 被拆掉的是 `d3d11Context->Signal(d3d11Fence, v)` + `commandQueue->Wait(d3d12Fence, v)`。
- 拆它的理由是「07:11 那局 fence 50 秒停在初值 1」——**而没有 Signal 的 fence 看上去就是这样。**
- 代价：D3D12 队列读 `swapChainBufferWrapped` / `colorOutWrapped`（**都是 D3D11 写的**）时**没有任何定序**，
  而 `DX12SwapChain.cpp:1248-1250` 的注释至今仍写着「必须在 fence 之前（D3D11 写 colorOut 完成后随
  Signal/Wait 同步，D3D12 拷贝才能稳定读到）」⇒ **同一条注释依赖的定序被 v0.75 拿掉了。**
- 更糟的是 v0.75 自己的注释写着：**「doodlum 的 ENBFrameGeneration 保留了这个双向等待并且工作正常……
  把它当作待否证的假设，而不是从可用参照移植来的做法。」** ⇒ 现在有证据可以否证了：见 §33.1 的两局对照。

**⇒ 症状吻合：present 一直在推进（`lastPr` 跑飞），内容却是陈旧的 ⇒ 就是「喂给 DLSS-G 的彩色缓冲是陈旧的」。**

## 33.4 机制三：写盘路径——**用户的配置被菜单吃掉了**

23:39 那局的日志：

```
[FrameGen] INI saved: Provider=1 DLSSGFramesToGenerate=3 MFGMaxFramesOverride=0 NR=1
[FrameGen] Provider -> 1 (DLSSG) | INI saved. | RESTART REQUIRED
```
盘上结果：**`E:/EJ/mod/mods/.../DynamicShaderFrameGen.ini` 从 14,559 B 变成 517 B**（md5 `23071f…`）。
- `SaveSettingsToIni`（`ImguiMenu.cpp:237-280`）写了 27 个键，**没有 `NRAllowWithFrameGen`**——
  而 `LoadConfig`（`FrameGen.cpp:164`）**读它**。⇒ 按一次 Save，下次启动 NR 静默变回「与帧生成互斥」。
- 这正是 `ImguiMenu.cpp:232-234` 注释里说已经修过一次的同一类缺陷，**回退了**。
- **并且：构建即部署，`CMakeLists.txt:107-113` 的 POST_BUILD 把源树的
  `SKSE/Plugins/DynamicShaderFrameGen.ini` 拷进 mod 目录。** ⇒ 23:52 那次编译把 517 B 那份直接盖回成模板。
  **⇒ 要改的永久位置是源树那份模板，不是部署出来的那份。**

## 33.5 v1.21 改了什么（四处）

| # | 位置 | 改动 | 依据 |
|---|---|---|---|
| 1 | `Streamline.cpp` `GameMenuOpenNow()` | `Fader Menu` 只在 `Loading Menu` 开着或前 90 秒算菜单（INI `MenuGuardFader`，默认 1） | §33.2 |
| 2 | `DX12SwapChain.cpp:1289` | `kD3D12WaitsOnD3D11` 从常量变成 `Get().settings.interopFenceWait`（默认 1 = 恢复定序） | §33.3 |
| 3 | `FrameGen.h/.cpp` | 上面两个键的字段 + 读取 | — |
| 4 | `ImguiMenu.cpp` | 补写 `NRAllowWithFrameGen`（本来漏了）+ 两个新键 | §33.4 |
| 5 | `DX12SwapChain.cpp` `fgGeneratingNow` | 去掉 `dlssgMode &&` —— FSR3 路上 `NRAllowWithFrameGen` 以前**完全无效**，NR 无条件叠加 | 23:38 局 `command contexts saturated` + 满分辨率 NR 每帧跑，而 INI 明写着 0 |

**第 5 条的边界（写死了，别忘）**：DLSSG 路上 `dlssgMode` 本来就为真，
**去掉它对该路的表达式逐字等价** ⇒ 不可能污染 Provider=1 的实验。

## 33.6 本轮实验的判据（下一局）

INI = `Provider=1` + `DLSSGFramesToGenerate=3` + `MFGMaxFramesOverride=3`
+ `NRAllowWithFrameGen=0`（NR 先请出去）+ `MenuDisableFrameGen=1`（**保留**，闸门已经修好）
+ `MenuGuardFader=1` + `InteropFenceWait=1`。

| 看到 | 结论 |
|---|---|
| **进世界就 `presented per real frame = 4`** | §33.2 成立：以前是**请求没发出去**，不是运行时拒绝 |
| 画面继续动（走动时 `clipDev` 明显 >0、`plrD>0`） | §33.3 成立：围栏是根因 |
| 还是定死，且 `LIVE hrsD` **仍在走** | 冻结在**呈现路径**，不在游戏逻辑；下一步做**像素探针**（读回 back buffer 几个像素并记录，这是唯一能把「世界在动」和「屏幕是陈旧的」分开的仪器）|
| 还是定死，且 `hrsD==0` | 游戏时钟停了 ⇒ 冻结**在游戏里**（模态状态/输入死锁），插件不背这口锅 |
| `MenuGuardFader=1` 反而进不去游戏 | v0.96 复现 ⇒ 改 `MenuGuardFader=0` 只测围栏，或把 90 秒改长 |
| `InteropFenceWait=1` 卡住（`stage=` 停在 `d3d12 queue Wait`）| 拆围栏是必需 ⇒ 改回 0（两键都只需改 INI，不必重编译）|

## 33.7 本轮的两条方法论

- **L37：一个「开关」如果只在一条分支上被查询，它就不是开关，是装饰。**
  `NRAllowWithFrameGen` 存在了两天、INI 里有专门注释写着「如果画面闪烁就设 0」，
  而 FSR3 路上 `fgGeneratingNow` 恒假 ⇒ 那个 0 从来没被读过。
  **判据：给一个配置项写文档之前，先 grep 它在几条路径上被消费。**
- **L38：观测到「计数在涨」与「内容在变」是两件事，必须各有一个见证。**
  `lastPr=832 vs frames=643` 证明 present 在发生，`clipDev/det3` 全部由相机派生
  证明不了屏幕内容。**下一件仪器必须是直接读屏幕内容的东西（像素探针），不是又一个相机派生量。**

## 33.8 L39：验证工具本身会造假阴性 —— `strings` 在这个环境里根本不存在

本轮核「新 INI 键名有没有真的编进 DLL」，执行的是：

```
for s in InteropFenceWait MenuGuardFader NRAllowWithFrameGen; do
    printf "%-28s " "$s"; strings -a build/NINJA/DynamicShaderFrameGen.dll | grep -a -c "$s"
done
```

三行输出全是 `0`。**如果就此收工，结论会是「补丁没编进去」—— 完全错误，而且会直接导致我推翻一个已经验证过的改动。**

真实原因：`which strings` → `no strings in (...)`。这个 Git Bash 里**没有安装 binutils，没有 `strings`**。
`strings` 一失败，管道左侧就没有任何输出，`grep -c` 于是老老实实数到 0，
**退出码 1 又被 `for` 循环吞掉**。⇒ **「工具没能运行」被伪装成了「结果为空」。**

改成 `grep -a -c "$s" <dll>` 直接搜二进制之后：

| 键名 | DLL 内出现次数 |
|---|---|
| `InteropFenceWait` | 2 |
| `MenuGuardFader` | 2 |
| `NRAllowWithFrameGen` | 3 |

（2 次 = 窄字符 + 宽字符各一份字面量，符合静态库字符串常量的预期。）

**L39：任何「计数为 0」的断言，先证明产生这个计数的那个工具跑起来了。**
判据三连：① `which <tool>` 先确认存在；② 必须有一个**必然存在的串做阳性对照**
（例如 `grep -a -c DynamicShaderFrameGen <dll>` 必须 >0）；③ 看退出码，
别把 `command not found` 读成「没找到目标」。

**「阴性结果」与「仪器坏了」在输出上长得一模一样，这是所有验证里最贵的一类假阴性 ——
它不产生噪声，它直接产生一个错误结论，且这个结论看起来是「有证据的」。**

## 33.9 本轮收尾状态（供下一局对照）

| 项 | 值 |
|---|---|
| DLL | 1,358,336 B，md5 `60378778d6171d3e2651ff3758b47fcb`（build == MO2 部署一致）|
| INI | md5 `4dabf3bdee6633400ff4cccff70871e4`（源树模板 == 部署一致），19,761 B，CRLF 343 / bareLF 0 |
| INI 关键 6 键 | `Provider=1`、`DLSSGFramesToGenerate=3`、`MFGMaxFramesOverride=3`、`MenuGuardFader=1`、`NRAllowWithFrameGen=0`、`InteropFenceWait=1` |
| git | HEAD `c79c644`（交付卡 + 本节），上一提交 `741fbe8`，tag `v1.21`，`git status --short` 空 |
| 交付卡 | `docs/diagnosis-20260919-2338-v121-the-4x-request-was-never-sent.html`，16,050 B |
| 本轮新增方法论 | L37（开关只在一条分支被查询 ⇒ 是装饰）、L38（计数在涨 ≠ 内容在变）、L39（阴性断言先证明仪器跑起来）|

**未做 / 未证（别假装做了）**：机制②（互操作围栏）只是**症状吻合 + 头号嫌疑**，不是已证结论；
DLSS5 的**屏幕输出**仍未证实；RTX 20/30 系一行未动。

---

# 34. v1.22 —— 4x 请求第一次真的发出去了；fader 按住了世界入口；装上像素探针

## 34.1 这一局的第一个真进展：请求发出且被接受（v1.21 局，00:30）

上一章的结论是「4x 的请求从来没被发出去」。v1.21 那一局（`docs/runlogs/2026-09-20-0031-v1.21-4x-still-frozen.log`，
00:30:10.395 → 00:31:07.259，共 57 s）**推翻了这一条的一半**：

| 指标 | 本局读数 | 含义 |
|---|---|---|
| `FPS probe` 行 | `ask=4 accepted=4 cap~=200.5 (=real*4)` | 请求发出去了，**运行时也接受了** |
| 看门狗逐秒比值 | `00:31:05 → 4.00`、`00:31:06 → 4.00` | **4 个 present / 每个真实帧**，插帧真的在上屏 |
| `presentAge` | 5 / 11 / 69 ms | 呈现及时，不是卡死 |
| `hrsD` | 0.0038 → 0.0058 /秒 | timescale 20，游戏在模拟 |

⇒ **4x 通了。** v1.21 那道闸门修对了。用户报告的「依旧卡住冻结」发生在 4x 已经生效的
那 2.36 秒里（00:31:04.898 → 00:31:07.259），**所以冻结还有第二个成因**。

★ 这一局还有一个必须先说的事实：**用户在世界里只待了 4.3 秒**（00:31:02.935 → 00:31:07.259），
`plrD=0.00` 全程、`INPUT_NONE` 全程 —— 没有按过 W。日志**没有关闭序列**，
最后一行 00:31:07.259，看门狗最后一条 `alive=1 presentAge=69ms`（由 5ms 爬上来）。
⇒ 这一局是**被强杀/硬挂**的，不是正常退出。

## 34.2 A 改动：`fader` 按住的是「能不能进世界」，不是「能不能玩」

同一份日志，四项字段取自**同一条** `[CAM] PC v1.19` 行：

| 时刻 | paused | ld | fade | hrsD | presents/real frame |
|---|---|---|---|---|---|
| 00:31:02.935 | **0** | **0** | **1** | 0.003807 | ~1 |
| 00:31:03.935 | 0 | 0 | 1 | 0.005663 | 1.00 |
| 00:31:04.943 | 0 | 0 | **0** | 0.005501 | **4.00** |

- 世界在 **00:31:02.935 就活了**：`paused=0`、`ld=0`、日历以 timescale 20 在走，
  而且 v1.16 的 `PC TAKEOVER` 恰好落在这一采样上（`best=0.00 proj00=0.8391`）；
- 但闸门又多按了 **2 秒**，因为 `IsMenuOpen("Fader Menu")` 仍为真；
- `[XRAY] MENU EDGE open=0 serial=653` 发生在 **00:31:04.683**，
  严格落在 `fade=1` 采样与 `fade=0` 采样**之间**；
- **90 秒兜底不可能解释它**：日志起于 00:30:10.395，释放时整局才 54.3 s，
  `s_faderT0` 只会比这更晚。

**这不是空操作（A≠B 已证）**：`paused=0` 与 `fade=1` 在两个采样上**同时**成立。
`GameIsPaused()` 在世界之前 13 个采样上全是 1（v0.96 的保护完好），
接管之后 5 个采样全是 0。`Loading Menu` 的提前返回**独立**覆盖加载窗口
（`ld=1` 从 00:30:57.684 到 00:31:01.919，那一段 `paused` 也全是 1）。

**改法**：`return ui->IsMenuOpen("Fader Menu") && faderUpSec < 90;`
→ `return ui->GameIsPaused() && faderUpSec < 90;`

★ **诚实边界**：A 只收回世界入口那 1.75–2 秒的死窗口。它**解释不了** 4x 已生效的
那 2.36 秒里的冻结 —— 那正是 B 存在的原因。

## 34.3 B 改动：像素探针（L38 的那个缺失见证）

本项目已有的**每一个**见证 —— `Present` 的返回值、`presentAge`、`dsync`、
`presented per real frame` 比值 —— 都只能报「**发生了一次 flip**」。
**没有一个能看见「同一张画面被翻了两次」**。这就是为什么 00:30 那一局
（ratio 4.00、dsync 0、presentAge 5–8 ms）读起来是健康的，而用户看到的是冻结。
**flip 不是画面。**

探针从**插件交给交换链的那张纹理**的正中央取 64×64 块，1 Hz，记录它有没有变：
- 只读、自禁用；`Map` 用 `D3D11_MAP_FLAG_DO_NOT_WAIT`，取不到样本就丢掉，**不阻塞渲染线程**；
- 连续 10 秒逐字节相同 ⇒ 打 `[PIXEL] VERDICT`（这是唯一能说「画面没动」的仪器）；
- INI `PixelProbe=1`（默认开），`0` 关掉、无需重编译。

**两个"探针挂在死分支上"的历史坑，这次都先排掉了：**
1. 调用点插在 `m_stage = "present entry";` 之后 —— 那是 `Present()` 三个返回分支**共用**的
   那条路。**可证伪检查**：看门狗里 `stage=present entry` 出现 **47 次** ⇒ 这条路真的在跑。
2. `CreateInterop()`（`swapChainBufferWrapped` 在那儿创建）在 `hk_IDXGIFactory_CreateSwapChain`
   里**无条件**调用，顺序是 `SetD3D11Device`(1764) → `SetD3D11DeviceContext`(1770)
   → `CreateSwapChain`(1797) → `CreateInterop()`(1798)，**全部早于任何一次 `Present`**
   ⇒ 探针不会因为"纹理还没就绪"在第一次 tick 就自禁用。

## 34.4 L40：锚点要整行；后置条件必须有一条只有"真改过"才满足

本轮补丁在 `.ini` 上连挂两次，两次都是好事：

1. 第一版锚点用 `MenuGuardFader=1`（裸串）。**它在这份 INI 里出现 2 次** ——
   第 22 行的**文档注释**里也提了这个键名。断言拦住：`count=2`。
2. 改成 `"\nMenuGuardFader=1"` 想去整行锚定。**这条路走不通**：
   `line_indent()` 用 `text.rfind("\n", 0, i)` 求缩进，而针**本身以 `\n` 开头** ⇒
   i 指向那个换行符 ⇒ 求出的是**上一行的内容**（`"B\r"`）当缩进 ⇒
   拼出来的 old 是 `"B\r\r\nMenuGuardFader=1\r\n"`，`count=0`。
   `.ini` 无缩进，所以我给补丁加了一个 **`afterline`** 模式：
   按 EOL 切行、要求**恰好一行**等于该针、否则 `REFUSED`。

**L40：给"没有缩进"的文件（ini/csv/json）做锚点时，用整行匹配，不要用"前缀换行"去凑唯一性。**
并且：**后置条件里必须有一条，是"什么都没改"无法满足的**。
本轮的 `POST_GONE`：结果文本里 `IsMenuOpen("Fader Menu") && faderUpSec < 90` 出现次数必须为 **0**。
（这是 33 章那次"散文满足断言"事故的正面做法 —— 断言只能由真东西满足。）

## 34.5 L41：方法名不是字符串 —— 用修饰符号证明调用进了二进制

核 A 改动有没有编进 DLL 时，`grep -a -c GameIsPaused <dll>` = **0**。
**这个 0 是对的，但如果按 L39 的直觉直接下结论就会误判。** 做对照：

| 查的串 | DLL 内计数 | 性质 |
|---|---|---|
| `GetSingleton` | 0 | 方法名（调用） |
| `Calendar` | 0 | 类名（调用） |
| `InterfaceStrings` | 0 | 类名（调用） |
| `GameIsPaused` | 0 | 方法名（调用） |
| `IsMenuOpen` | 1 | **格式串字面量**（MENU PROBE 的日志文本） |
| `Fader Menu` | 1 | 真字面量 |
| `PixelProbe` | 3 | 真字面量（窄+宽+日志） |

⇒ **方法/类名以"调用"形式存在，不以字符串形式存在。字符串计数根本不该拿来验证它们。**

真凭据要另找。本轮用的是**目标文件符号**：
```
build/NINJA/CMakeFiles/DynamicShaderFrameGen.dir/src/Streamline.cpp.obj
  → ?GameIsPaused@UI@RE@@QEAA_NXZ      （1 处，修饰符号）
git show HEAD:src/Streamline.cpp | grep -c GameIsPaused   → 0
```
时间戳链：源码 00:52:23 → obj 00:52:44 → DLL 00:52:47。
改前源码里**零**出现 ⇒ obj 里这一处**只可能**来自本次改动。

**L41：要证明一次调用改动进了二进制，用 `grep -a <修饰名> <obj>`（或看反汇编），
不要用字符串搜索 —— 后者对方法名恒为 0，是结构性假阴性。**

## 34.6 收尾状态与下一局判据

| 项 | 值 |
|---|---|
| DLL | 1,362,944 B，md5 `5f1793d921493f1e94fc23aad4a8b390`（build == MO2 部署）|
| INI | md5 `efce89119d840670e519d219749a6476`（源树 == 部署），PURE CRLF 358 行 |
| INI 关键键 | `Provider=1`、`DLSSGFramesToGenerate=3`、`MFGMaxFramesOverride=3`、`MenuDisableFrameGen=1`、`MenuGuardFader=1`、`InteropFenceWait=1`、`NRAllowWithFrameGen=0`、**`PixelProbe=1`** |
| git | HEAD `f7fe9b7`，tag `v1.22`，`git status --short` 空 |
| 行尾 | `DX12SwapChain.cpp` 纯 LF（bare_lf 1810→1960）；`Streamline.cpp` CRLF+BOM；INI 纯 CRLF（343→358）；全库 `lone_cr=0` |

**下一局这么跑**：① 进世界**站着不动 15 秒** → ② **按住 W 走 5 秒以上** → ③ 再退。

**日志里看三样：**

| 看什么 | 命令 | 判据 |
|---|---|---|
| 4x 是不是从进世界就生效 | `grep -a "presented per real frame" <log>` | 出现 `= 4` |
| **画面到底动没动** | `grep -a "\[PIXEL\]" <log>` | 每秒一行 `chg=`；`VERDICT` = 陈旧缓冲已证 |
| 呈现健康度 | `python tools/wd_ratio.py <watchdog.log> 10` | ratio ≈ 4 且 presentAge 小 |

**A 的回退**：这个改动在代码里，不是 INI 开关 ——
`git checkout v1.21 -- src/Streamline.cpp` 再 `./build_vs.sh`。
（`MenuGuardFader=0` 不是它的回退键：那个值是 v0.96 的"fader 永不算菜单"，会进不去游戏。）

**未证 / 未做（别假装做了）**：机制②（互操作围栏）仍是症状吻合 + 头号嫌疑；
冻结的**存在性**本轮仍未被独立见证 —— 这正是要 `[PIXEL]` 的原因；
DLSS5 屏幕输出未证；RTX 20/30 未动。

---

# 35. v1.23 —— 像素探针从来没采到一个样本；零矩阵被当成合法 clipToPrevClip

日志：`docs/runlogs/2026-09-20-0058-v1.22-loadscreen-freeze.log`（00:58:00.284 → 00:58:54.206，54 s，
v1.22 build `Sep 20 2026 00:52:35`）。用户原话：
**「这次游戏都没进去，直接在加载界面就卡死闪烁了」**。

## 35.1 这一局到底发生了什么（时间线全部取自日志原文）

| 时刻 | 证据 | 含义 |
|---|---|---|
| 00:58:14.743–14.810 | `D3D12 FG swapchain created (3840x2160)`、`interop ready`、`[PIXEL] probe armed` | 装置就位 |
| 00:58:35.782 | `MENU EDGE open=1 serial=2`、`paused=1 ld=1 fade=1`、`hrs=0.0`、`eye=(0,0,0)` | 闸门按在**第 2 帧** |
| 00:58:35.783 | `[MFG] probe RUNS while the menu guard skips DLSS-G: step advertised=4x accepted=4x` | 阶梯在跑，但 `SetDLSSGOptions` 被跳 |
| 00:58:37.772 | `FPS probe: real=45.7 … ask=4 accepted=4` | 4x 已被运行时接受 |
| 00:58:41.753–46.789 | `proj00=0.149184 eye=(0,0,128)`、`hrs=32.0`、`plr=(2048,2048,0)` | **加载期空相机**（既有的加载指纹） |
| 00:58:44.761 | `plr=(-250.3,-360.4,0.1) plrD=3329.08`、`hrs=12.31110` | 玩家被传送到世界坐标 |
| 00:58:48.150 | `MENU EDGE open=0 serial=566` ⇒ `blocked=564 unblocked=1` | 闸门放开（世界入口） |
| 00:58:48.807 | `paused=0 ld=0 best=0.00 proj00=0.8391 eyeD=0.07 hrsD=0.003136` | **世界真的进去了** |
| 00:58:48.641 / 49.694 / 53.959 | `DLSSG presented per real frame = 4` | 4x 上屏 |
| 00:58:49–53 | 看门狗逐秒 `ratio = 4.00`、`dsync=0`、`presentAge 0–18 ms` | 呈现链路**每一项都健康** |
| 00:58:54.206 | 最后一行；**无关闭序列**；看门狗 `alive=1` | 被强杀/硬挂 |

**加载耗时 13.1 秒，与上一局（v1.21，00:31）的 12.3 秒同量级** ⇒ v1.22 没有让加载变慢。

**A≠B：两局逐项对照**（指纹计数）

| 指纹 | v1.21（00:31） | v1.22（00:58） |
|---|---|---|
| `stall governor` | 2 | 2（最大 346 ms → **822 ms**）|
| `flicker cause` / `USELESS` | 3 | 1 |
| `MOTION` | 1 | 1 |
| `non-affine` | 20 | 21 |
| `presented per real frame = 4` | 1 | 3 |
| `presented per real frame = 1` | 10 | 9 |
| `debug CHECK` / `probe RUNS while` | 1 / 1 | 1 / 1 |
| **`second thread PERSISTENTLY`** | **0** | **6** |
| **`[PIXEL]`** | n/a | **1（只有 armed，0 个样本）** |

⇒ **v1.22 在可观测行为上几乎没有改变任何东西。** 用户感到"这次更糟"，但日志是同一种局：
加载 → 进世界 → 4x 生效 → 5 秒后被杀。**唯一新增的两条：探针没出数据，以及那条被我自己的阈值误报的 verdict。**

★ 用户说"没进去"，日志说"进去了"（`paused=0 ld=0`、真玩家相机 `best=0.00 proj00=0.8391`、
`hrsD≈0.0057`＝timescale 20）。两者可以同时为真：**世界在跑，屏幕没显示它。** 这正是 L38。

## 35.2 探针是死的 —— 这是我 v1.22 的 bug，不是环境的

```
[PIXEL] probe armed: src=3840x2160 fmt=28 block=64x64 at (1888,1048)   00:58:14.810
[PIXEL] <没有下一行>                                        00:58:14.811 … 00:58:54.206
```

**39 秒、0 个样本。** 根因在 v1.22 的代码里：`CopySubresourceRegion` 与 `Map` 在**同一次调用**里，
所以 `Map` 永远在问一张 GPU 还没写完的 staging 纹理 ⇒ 恒返回
`DXGI_ERROR_WAS_STILL_DRAWING`；而那条分支还写了 `pixelProbeLastMs = 0`，
**把 1 Hz 节流给废掉了** ⇒ 重试发生在**每一帧**。两个后果：

1. 唯一能回答"画面到底动没动"的仪器**一个数据点都没产出** —— 而这一局恰恰需要它；
2. **它把一次跨 API 拷贝塞进了每一帧**（从 D3D12 拥有的共享后备缓冲拷到 D3D11 staging）。
   这是 v1.22 里**唯一**改动渲染热路径的东西。最大帧时间从 346 ms 涨到 **822 ms**。

**★ 诚实边界**：822 ms 这个数字**不能**证明是探针造成的（`stall governor` 在 v1.21 也触发过 2 次）。
它被移除的理由是**它是缺陷**，不是因为已证它是成因。下一局如果加载顺了，那条因果仍只是**嫌疑**，
要另设对照才能定案。

修法：**两相采样** —— 这一秒收割"上一秒发出的拷贝"（有整整一秒落地），再发下一次拷贝；
取不到样本就**丢弃并计数**，绝不在同一秒里重试。

## 35.3 零矩阵被当成合法的 clipToPrevClip（真缺陷，已证）

同一条日志，加载→世界的**交界处**：

```
[W] [MOTION] clipToPrevClip[3].w=-68.073540 (must be 1) - the inverse and the previous
    matrix came from different cameras … v1.08 PROBE: p00 cur=6.7031 prev=0.0000 |
    p23 cur=-15.010994 prev=0.000000 | mag invSrc=68.54 prevSrc=15.01
[FLD] #1 c32 PrevVPU row3=(0,0,0,0) [3][3]=0 dev=1 det=0 mag=0 BAD
```

`prevForReproj` 是**零矩阵** ⇒ `inv(cur) × 0 = 0`。而代码里唯一的合法性判据是：

```cpp
const bool clipFinite = clipMagAll < 1.0e30f;   // rejects NaN / Inf
if (clipFinite) { s_lastGoodClip = c.clipToPrevClip; s_hasLastGoodClip = true; }
```

**零矩阵的 mag = 0，"小于 1e30"完全成立** ⇒ 它被当成合法矩阵，**并且被写进
`s_lastGoodClip`** —— 也就是后续帧在守卫触发时回退用的那份"上一帧合法位移"。
**污染是不可逆的：一个 0 会作为"好值"被反复重放。**

`clipDev` 那一侧同样会骗人：零矩阵的 `max|I − 0| = 1.0`，**看起来像"动了很远"**，
实际是一个退化矩阵。

修法：判据加下界 —— `clipMagAll < 1.0e30f && clipMagAll > 1.0e-6f`。
单位阵（真正静止的相机）mag = 4.0，任何真实运动都维持在 4 附近，**只有退化矩阵会掉下 1e-6**。
失败的那一帧现在保持上一份合法矩阵（没有就退回单位阵），不再把"相机没动"这句假话发给 DLSS-G。

## 35.4 两条自伤诊断（都在这一轮浪费了我的时间）

1. **verdict 阈值与它宣称区分的东西不匹配。** 判定链把
   `else if (diag.tidCallsB > 10)`（"第二个线程在持续调用 slSetConstants"）排在所有检查**之前**，
   而日志显示 `a=1`：**第一个调用者只调了一次就再没回来**（这正是世界入口处一次性调用的样子），
   `b=30→180` 只是渲染线程在正常每帧调用。⇒ **它一条危害都证明不了。**
   改为 `tidCallsB > 10 && tidCallsA > 10`（两个线程都真的在活跃）。
   ★ 这是 **L37 的近亲**：条件写了，但它选中的是**另一类样本**。
2. **陈旧断言。** `- depth/mvec must read 2560x1440 (the real interop buffers)`
   打印时三个 extent 全是 `3840x2160`，而这些 extent 就在**上面几行**从 interop 资源本身读出来的
   （v0.56 就是为修那个 1.5× 错配才改成从资源取）。**这条消息是这一局日志里唯一能把我引向
   "分辨率不匹配"这个不存在的方向的东西** —— 它确实短暂地骗了我。
   改成比较 depth 与 mvec（唯一会失败的检查）。

## 35.5 方法论

- **L42：仪器必须自证运行过（L39 用在自己代码上）。** 只在成功路径上打日志的探针，
  **失败时和"一切正常"在日志里长得一模一样**。必须有一条**独立的**"我没跑起来"的告警。
  本轮落地：armed 后 15 秒仍 0 样本 ⇒ `log::error`，并在文本里写死
  **「没有 [PIXEL] 采样行 = 没测量，绝不等于画面正常」**。
- **L43：跨 tick 的生产/消费不能塞进同一个调用。** `Copy` 与 `Map` 同调用 ⇒ 消费者必然
  等不到生产者。任何"生产-消费"设计都要先问：**消费者需要等待生产者吗？**
  要，就必须跨帧；不要，才允许同调用。这也是"DO_NOT_WAIT 便宜"这个想法的反面 ——
  DO_NOT_WAIT 只是让**失败**变便宜，它不会让**成功**出现。
- **L44：一个量只有在"反例下会变"时才是见证。** 哈希连续相同，只有在**相机在动**时才等于
  "画面陈旧"；相机静止时插帧输出**本来就该**和真实帧一致。本轮把 `clipDev` 与哈希并排记录，
  并规定只有 10 秒里 ≥5 秒相机在动才报 VERDICT —— **否则探针会对着站桩的玩家喊"冻结"**，
  再浪费一局。

## 35.6 收尾状态与下一局判据

| 项 | 值 |
|---|---|
| DLL | 1,368,576 B，md5 `83e84a781bf645ec3363b58c5fb671ec`（build == MO2 部署）|
| INI | md5 `efce89119d840670e519d219749a6476`（源树 == 部署）—— 本轮**无新键**，无需改 |
| INI 关键键 | `Provider=1`、`DLSSGFramesToGenerate=3`、`MFGMaxFramesOverride=3`、`MenuDisableFrameGen=1`、`MenuGuardFader=1`、`InteropFenceWait=1`、`NRAllowWithFrameGen=0`、`PixelProbe=1` |
| git | HEAD `2acd52f`，tag `v1.23`，`git status --short` 空 |
| 行尾 | `DX12SwapChain.cpp` 纯 LF（bare_lf 1819→2035）；`Streamline.cpp` CRLF+BOM（2392→2423）；两个头文件纯 CRLF；全库 `lone_cr=0` |
| 补丁 | `tools/patch_v123_probe_fix.py`（9 条编辑 / 4 文件；干跑默认；funcspan 模式按签名+花括号定位函数；重跑 `REFUSED`）+ `tools/v123_pixelprobe_impl.txt` |

**下一局这么跑**：① 进世界**站着不动 15 秒** → ② **按住 W 走 10 秒以上** → ③ 再退。
（第二步从 5 秒改成 **10 秒**：VERDICT 需要连续 10 秒的样本，而且要求其中 ≥5 秒相机在动。）

| 日志里看什么 | 命令 | 判据 |
|---|---|---|
| 探针有没有在采样 | `grep -a "\[PIXEL\]" <log>` | 每秒一行 `#N … chg= clipDev= movedThisStreak=` |
| 探针**没**在采样 | 同上 | 出现 `[PIXEL] ERROR: armed N s ago and produced ZERO samples` ⇒ 仪器坏了，**不要**读成画面正常 |
| 画面是不是真的陈旧 | 同上 | `[PIXEL] VERDICT`（连续 10 秒同哈希且相机在动）|
| 站桩时的同哈希 | 同上 | `10 identical seconds, but the camera was still` ⇒ **预期行为，不是冻结** |
| 4x 有没有生效 | `grep -a "presented per real frame" <log>` | 出现 `= 4` |
| 加载为什么慢 | `grep -a "stall governor" <log>` | 帧时间是否仍 > 800 ms |
| 零矩阵还在不在 | `grep -a "\[MOTION\]" <log>` | 修订后应**消失**（或伴随 `detGuard` 计数）|

**回退**：探针 `PixelProbe=0`（只改 INI）；围栏 `InteropFenceWait=0`（只改 INI）；
零矩阵那条与 fader 那条在**代码**里 ⇒ `git checkout v1.22 -- src/` 再 `./build_vs.sh`。

**未证 / 未做（别假装做了）**：v1.22 的每帧跨 API 拷贝**与加载卡死之间的关系未证**；
机制②互操作围栏仍是**症状吻合 + 头号嫌疑**；冻结的**存在性**至今**仍无独立见证**
（`[PIXEL]` 从未成功采样过任何一局）；DLSS5 屏幕输出未证；RTX 20/30 未动。

---

# 36. 进程里有两个 DLSS-G 驱动 —— 12 局日志把冻结切给了 DLSS-G 支线

日志：`docs/runlogs/*.log`（12 局，09-19 14:55 → 09-20 00:58），外加第三方驱动自己的四份文件
`DLSSG-Transfusion.{log,crash.log}` / `_perf.csv` / `DLSSG-Transfusion.json`。
触发：用户重启电脑后要求继续推进「多倍帧生成」（v1.23 已构建部署但**尚未运行过任何一局**）。

## 36.1 12 局对照：切分点不在倍数，在「DLSS-G 有没有参与」

| 局 | Provider | ask/accepted | Transfusion 施加 4x | 画面 |
|---|---|---|---|---|
| 09-19 14:55 → 22:38（7 局，v1.11–v1.17）| DLSSG | 4/4 | 是 | 冻结 |
| 09-19 22:54 v1.18b | DLSSG | 4/4 | 是 | **硬冻结** |
| 09-19 23:22 v1.19 | DLSSG | 4/4 | 是 | **硬冻结** |
| **09-19 23:38 v1.19** | **FSR3** | **2/0** | **从未** | **活了** |
| 09-20 00:31 v1.21 | DLSSG | 4/4 | 是 | 冻结 |
| 09-20 00:58 v1.22 | DLSSG | 4/4 | 是 | 冻结 |

**11/11 局 DLSSG 都是 `ask=4 accepted=4`。** ⇒ 第 34 章那句「4x 请求从来没被发出去」
**只对 22:54 那一局的 571/572 帧成立**；对请求路径而言，它早已通了。

**★ 22:54 那一局还否掉了「倍数太高」这条线**：那局全程 `presented per real frame = 1`（**一帧都没插**），
画面照样定死。⇒ 冻结与「有没有生成帧」无关。

**⇒ 剩下的唯一切分：DLSS-G 这条支线参与 ⟺ 冻结。**

## 36.2 第二个驱动：DLSSG-Transfusion（游戏根目录的 `dinput8.dll`）

它自己写的身份（`DLSSG-Transfusion.log:1-16`，00:58:00.077）：

```
DLSSG-Transfusion (Universal Blackwell Transfusion & Multi-Game Edition)
Build: v1.4.0-pure-warp (Sep 14 2026 18:42:03)
Loaded as: dinput8.dll
Proxied system DLL: C:\WINDOWS\system32\dinput8.dll
Module Path: D:\ENB-EJ\Skyrim Special Edition\DINPUT8.dll      （540,672 B，Sep 18 19:44）
Initial control: mode=fixed multiplier=4x ... blackwellTransfusion=1 disableMenuDetection=1
```

**它 Direct Detours 的是同一批入口**（00:58:11.622）：

```
(slGetFeatureFunction, slInit, slSetD3DDevice, slSetVulkanInfo,
 slSetData, slSetConstants, slSetTag, slSetTagForFrame)
```

其中 `slSetConstants`（我们发布 `clipToPrevClip` 的地方）、`slSetTag`、`slSetTagForFrame`、`slSetData`
**六个和我们插件钩的是同一个函数**。

**它还在改 DLSS-G 运行时的二进制**（每次启动都做）：

```
00:58:12.802  HUDless UIR patch applied in E:\EJ\mod\mods\DynamicShaderFrameGen\Shaders\Upscaling\Streamline\nvngx_dlssg.dll
00:58:12.840  ... in C:\ProgramData\NVIDIA\NGX\models\dlssg\versions\0\files/160_876232C.bin
00:58:12.881  ... in C:\ProgramData\NVIDIA\NGX\models\dlssg\versions\0\files/160_E658703.bin
00:58:13.772  ... 同上一份，再来一次
```

改动覆盖 **①我们 mod 目录里的 `nvngx_dlssg.dll`** 与 **②全局 NVIDIA 模型缓存**（会影响其它游戏）。
`blackwellTransfusion=1` 开在一张 **Ada（RTX 40）** 卡上，而它自己打印的内核就是 `Kernel: Ada`。

**它这一侧的 4x 没坏**：

```
00:58:35.782  Applied fixed multiplier: 4x, result=0 (eOk)
00:58:48.641  DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
00:58:51.551  [PERF] 4x | Kernel: Ada | FPS: 40.2 (24.85ms)
```

而 INI 里被记为「4x 真的能用」的 09-18 07:29 局是 `4x | Kernel: Ada | FPS: 39.6 (25.28ms)` ——
**两次数字几乎完全一致**。⇒ **Transfusion 的生成侧与"验证成功"时逐项相同。**

**但它不是全程都在生成**（`_perf.csv`，650 帧）：

```
Multiplier = 0 : 548 帧
Multiplier = 4 : 102 帧        ← frame 549 处从 0 跳到 4
```

## 36.3 时间戳级同现：闸门与它落在同一毫秒

| 时刻 | 来源 | 事件 |
|---|---|---|
| 00:58:35.782 | 我们 | `[XRAY] MENU EDGE open=1 serial=2` —— 闸门在第 **2** 帧就按住 |
| 00:58:35.782 | Transfusion | `[OPTIONS] Game DLSS-G options: mode=eOn frames=3 … flags=0x00000010` |
| 00:58:35.782 | Transfusion | `Applied fixed multiplier: 4x` + `stripped eEnableFullscreenMenuDetection (0x10 -> 0x00)` |
| 00:58:35.783 | 我们 | `[MFG] probe RUNS while the menu guard skips DLSS-G … advertised=4x accepted=4x` |
| 00:58:48.150 | 我们 | `MENU EDGE open=0 serial=566`、`blocked=564 unblocked=1` —— **13 秒后才放开** |

**这 13 秒里**：我们插件（`MenuDisableFrameGen=1`）对 `SetDLSSGOptions`/`EvaluateDLSSG` 一次都不调；
Transfusion 把 `eEnableFullscreenMenuDetection` 从选项里**剥掉**，让运行时不知道菜单开着。
**两边都不告诉运行时"现在是菜单/加载画面"。**

这不是新问题 —— v1.05 的 INI 笔记就记过同源事故：
「Transfusion set 4x, this plugin set 2x, the pacer never converged, and the frame ended inside Present()」，
那次读数是 **一帧 19480.5 ms**。区别只在于当时两边写的值不同，现在两边"同时不说话"。

## 36.4 判据与下一局

**决定性实验（单变量、可秒回退）：** 把游戏根目录的 `dinput8.dll` 改名。

```
D:\ENB-EJ\Skyrim Special Edition\DINPUT8.dll
   →  DINPUT8.dll.transfusion-off
```

★ **名字必须用 `.transfusion-off`，不能用 `.disabled`** —— 该目录里**已经**有
`dinput8.dll.disabled`（5,945,344 B，另一个 DLL）与 `dinput8.dll.rtxmfg-off`（同尺寸，Sep 18 18:01），
用 `.disabled` 会**撞名覆盖一个不相干的 5.9 MB 文件**。参照用户自己的 `.rtxmfg-off` 命名法。

**这一局会发生什么（先说清，免得白跑）：** 没有内核解锁器 ⇒ 我们插件读到
`kernelUnlocker=false`（`Streamline.cpp:265-269` 读 `GetModuleHandleA("dinput8.dll")`）⇒ 请求被夹到硬件上报的 **2x**。
**这一局不是去拿 4x，是去拿一个干净的基线** —— 而「我们的插件 + DLSS-G 2x + 无第二个驱动」**至今没跑过一局**。

| 看到 | 结论 |
|---|---|
| `[PIXEL]` 每秒一行、`chg=1`，画面能走 | 第二个驱动被证实是并因 ⇒ 回头修协同，不再改围栏 |
| 仍冻结但 `presented per real frame` 正常 | 第二个驱动被洗清 ⇒ 冻结在我们自己的 DLSS-G 呈现路径，围栏是下一个目标 |
| `[PIXEL] ERROR: … produced ZERO samples` | 仪器又坏了 ⇒ 先修仪器 |
| `hrsD == 0` | 游戏时钟停了 ⇒ 冻结在游戏里 |

**备选（想留住 4x 再测）**：只改 `DLSSG-Transfusion.json` 一个键 `"disableMenuDetection": 1 -> 0`。
但**它不能用来隔离变量**：4x 仍在，若画面依旧冻结，分不清是 4x 本身还是协同。

## 36.5 方法论

- **L45：相关性要能落成"实验可以推翻它的形式"，否则它只是故事。**
  本轮拿到 12/12 的切分（DLSS-G 参与 ⟺ 冻结）和一次**时间戳级**同现，全部是**相关性**。
  它足以把下一个实验设计成单变量隔离，**不足以**写成因果。
  判据：**如果我的结论是错的，哪个读数会不一样？** 本轮答案是「去掉第二个驱动后画面会不会活」。
- **L46：改文件名前先 `ls` 目标目录。** 我第一版卡里写 `dinput8.dll.disabled`，
  而那个名字**已被另一个 5.9 MB 的文件占用** —— 按这个操作会覆盖一个不相干的 DLL。
  **"用户会不会因此白跑或受损"这一问必须在给出指令之前问，不是之后。**
- **L39 复现**：`grep -c` 返 0 匹配 ⇒ 退出码 1 ⇒ `&&` 链断 ⇒ 后面的检查根本没跑，
  而输出看起来"只是没打印"。**这次因为我已经知道要看退出码，没有误判。**

## 36.6 收尾状态

| 项 | 值 |
|---|---|
| DLL | 1,368,576 B，md5 `83e84a781bf645ec3363b58c5fb671ec`（build == MO2 部署）|
| INI | md5 `efce89119d840670e519d219749a6476`（源树 == 部署），8 键：`Provider=1`/`DLSSGFramesToGenerate=3`/`MFGMaxFramesOverride=3`/`MenuDisableFrameGen=1`/`MenuGuardFader=1`/`InteropFenceWait=1`/`NRAllowWithFrameGen=0`/`PixelProbe=1` |
| 本轮有无新局 | **没有。** 最后一份日志仍是 00:58（v1.22），**v1.23 尚未运行** |
| 交付卡 | `docs/diagnosis-20260920-0115-two-dlssg-drivers-in-one-process.html`（15.7 KB）|
| 工具 | `tools/check_card.py` 修了 DOCTYPE 假阳性（`<!DOCTYPE html>` 被当成杂散尖括号）|

**未证 / 不说满**：Transfusion 与冻结之间是 **12/12 相关 + 一次时间戳同现，不是已证的因果**；
它 patch NGX 运行时与全局模型缓存**是否**参与冻结，未证；`blackwellTransfusion=1` 用在 Ada 上**是否不当**，未证；
`[PIXEL]` 至今**从未产出过一个样本**，「画面到底是不是陈旧」目前仍只有间接证据；
DLSS5 屏幕输出未证；RTX 20/30 一行未动。

## 36.7 A≠B：改 NGX 二进制与冻结**无关**，可以划掉

把三局的 Transfusion 活动量逐项数出来：

| 局 | `HUDless UIR patch` | `[OPTIONS]` 拦截 | `Applied fixed` | `[PERF]` | 画面 |
|---|---|---|---|---|---|
| 09-19 23:38 | **14** | 0 | 0 | 0 | **活了** |
| 09-20 00:31 | 10 | 1 | 1 | 4 | 冻结 |
| 09-20 00:58 | 8 | 1 | 1 | 4 | 冻结 |

**NGX 二进制 patch 在活着的那一局也发生了 14 次** ⇒ **它不是并因。**
真正与冻结同现的是「**Transfusion 真的拦截并驱动了 DLSS-G**」（活局全 0）。

★ **但必须先说清一个分不开的混淆**：归档里「Transfusion 驱动了 DLSS-G」与「DLSS-G 支线被用到」**完全共线**
（活局用的是 FSR3，DLSS-G 本来就没启用）。**仅凭归档无法把两者分开 —— 这就是隔离实验的全部理由**，也是为什么
36.1 的「DLSS-G 参与 ⟺ 冻结」这条切分不能直接写成因果（L45）。

## 36.8 本轮给用户的指令已做前置核查

给出「改 `DINPUT8.dll` 文件名」之前，已实测：

1. 目标目录 `ls`：确认 `dinput8.dll`（540,672 B，Sep 18 19:44）是当前生效的那个，
   且 `.disabled`（5,945,344 B）与 `.rtxmfg-off`（5,945,344 B）**已被占用** ⇒ 目标名改用 `.transfusion-off`（L46）。
2. 该局只到 2x 的说法有代码依据：`Streamline.cpp:278-288`，`kernelUnlocker` 为假时
   `diag.reqStepMax = max(1, a_hwMax)` 并**提前 return**，不越过硬件上报值。
   （INI 亦记：Ada 的 `numFramesToGenerateMax` 原生为 1 = 2x；本盘 12 局的 `hwMax=6` 是 Transfusion 抬上去的。）
3. 之前 12 局的 `ask=4 accepted=4` 全部依赖 Transfusion 抬高上报值 ⇒ **「无 Transfusion 的 2x」这一配置从未跑过**。

---

# 第 37 章 · v1.24：4x 是在淡入（fade）还挂着的时候打开的

归档 `docs/runlogs/2026-09-20-0130-v1.23-loadscreen-freeze-4x-visible.*`
（`.log` / `.watchdog.log` / `.transfusion.log` / `.transfusion.perf.csv`）
交付卡 `docs/diagnosis-20260920-0145-v124-the-4x-was-granted-under-the-fade.html`
补丁 `tools/patch_v124_fade_guard.py`

## 37.0 本局基本盘

- **v1.23 首次真正运行**（`build Sep 20 2026 01:06:38`，`size=1368576B`，游戏实际加载
  `D:\ENB-EJ\Skyrim Special Edition\data\SKSE\Plugins\DynamicShaderFrameGen.dll`，mtime 17:06）。
  此前 36 章写「v1.23 尚未运行过任何一局」，本条成立前提已消失。
- 时长 61 s：01:29:54.159 启动 → 01:30:13.805 D3D12 proxy active → 01:30:29.785 进加载
  → **01:30:53.130 闸门释放** → 01:30:55.623 日志结束。
- **加载 23.3 s，闸门释放后只跑了 2.5 s。**
- **v1.23 的探针修复生效**：`[PIXEL] #1` … `#26`，**历史上第一批真实样本**（此前 0 个）。
- 隔离实验（`DINPUT8.dll` → `.transfusion-off`）**仍未做**：`dinput8.dll` 仍是 540,672 B（Sep 18 19:44）。

## 37.1 「4x 没成功」这条线判死：9-19 以来 11/13 局都有 presented=4

同一口径数每一局的 `DLSSG presented per real frame = 4` 行数：

| 局 | 加载 | 释放后跑了多久 | presented=4 |
|---|---|---|---|
| v1.11 14:55 | 12.1 s | 14.1 s | 2 |
| v1.12 18:20 | 29.4 s | 30.6 s | 6 |
| v1.13 19:39 | 119.3 s | 11.7 s | 3 |
| v1.14 21:15 | 14.7 s | 3.4 s | 1 |
| v1.15 22:02 | 15.2 s | 4.5 s | 1 |
| v1.16 22:22 | 15.5 s | 2.2 s | 1 |
| v1.17 22:38 | 13.6 s | 2.6 s | 2 |
| v1.18b 22:54 | 13.7 s | 2.7 s | 2 |
| v1.19 23:22 | 27.1 s | 2.9 s | 2 |
| v1.19 FSR3 23:38 | （无 MENU EDGE） | — | **0**（Provider=0，DLSS-G 未启用）|
| v1.21 00:31 | 14.9 s | 2.6 s | 1 |
| v1.22 00:58 | 12.4 s | 6.1 s | 3 |
| **v1.23 01:30** | 23.3 s | **2.5 s** | 2 |

**⇒ 运行时从来没有拒绝过 4x。** 「请求没发出去」「倍数太高被拒」两条假设从 v1.11 起就不成立
（22:54 局 `presented=1` 是闸门按住导致的，见 36 章）。
**⇒ 用户看到的「帧数变 4 倍」是真实的请求结果。**

★ 顺带纠正本轮的一个错误结论：我一度写「v1.23 首次 4x 上屏」。**错。** v1.11 起就有。
这条是我只看了 v1.22/v1.23 两局就下的判断 —— 又一次「样本不足 + 结论先行」。

## 37.2 游戏没死：三份互相独立的证据

```
[N] 01:30:55.637 frames=1237 silent=2ms stage=d3d11 Wait focus=1 fence=2463/2463
    stim=237 queued=1 lastPr=1451 dsync=0 msg=1 alive=1 presentAge=14ms
```

1. **窗口是响应的**：`msg=1` 来自 `SendMessageTimeoutA(probe, WM_NULL, SMTO_ABORTIFHUNG, 200)`。
   操作系统**没有**把窗口判为 hung。`alive=1 focus=1`。
2. **没有崩溃**：Windows `Application` 事件日志（近 40 分钟）**无** `Application Error` /
   `Application Hang` 记录 ⇒ 是正常退出，不是 crash。Transfusion 的 crash.log 只记
   `FIRST_CHANCE_EXCEPTION`（3 处，first-chance = 多半被游戏/驱动处理掉）。
3. **游戏时钟在走**：`hrsD=0.006651` / `0.005666`（timescale 下逐秒推进）⇒ 世界逻辑未冻。

配套：`queued=1`（有 backpressure）、`dsync=0`、`lastPr` 1161→1451 单调增、`presentAge=5~28ms`。
**⇒ 「引擎半死」「Present 不翻转」「DXGI 失步」三条都被本局读数否掉。**

## 37.3 闸门释放的那一刻，fade 还立着（本局的核心异常）

原始时间线（每条都可 grep 到）：

```
[01:30:53.130] [XRAY] MENU EDGE open=0 serial=1158 presentedBefore=1 consts(ok=0 fail=0)
[01:30:53.130] [MFG] probe edge: menu guard released, SetDLSSGOptions resumes on this frame.
[01:30:53.130] [W] [MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu guard
               is not engaged (menuBlock=0 frames=0 blocked=1156 unblocked=1)
[01:30:53.365] [CAM] PC v1.19: ... paused=0 ld=0 fade=1 hrsD=0.000326 ... PC_STILL INPUT_NONE
[01:30:53.494] [Streamline] DLSSG presented per real frame = 4 (status=0)
[01:30:53.494] (Transfusion) DLSS-G actual presentation count: 4x (maximum generated frames=5)
[01:30:54.373] [CAM] PC v1.19: ... paused=0 ld=0 fade=1 hrsD=0.006651 ... PC_MOVING INPUT_NONE
[01:30:55.379] [CAM] PC v1.19: ... paused=0 ld=0 fade=1 hrsD=0.005666 ... PC_STILL INPUT_NONE
[01:30:55.623] 日志结束（用户退出）
```

**释放的判据是 `GameIsPaused()`**（v1.22 改成 `return ui->GameIsPaused() && faderUpSec < 90;`，
见 `src/Streamline.cpp:449`）。释放时：
- `consts(ok=0)` ⇒ **一帧相机常量都还没喂过**；
- `fade=1` ⇒ 屏幕上还是淡入遮罩；
- 0.364 s 后 4x 生效 ⇒ **4x 开在了淡入上。**

★ `faderUpSec` 是**从进程启动**算的（`static const auto s_faderT0`）。本局启动 01:29:54，
90 秒上限要到 01:31:24 才可能触发，而用户在 01:30:55 就退了 ⇒ **那 90 秒上限在本局根本没起作用，
释放是 `GameIsPaused()` 干的。**（避免把它当成"上限保护在起作用"。）

★ v1.22 的推理本身没错：00:30 局实测 `fade=1` 时 `hrsD>0`，世界是活的，fader 不构成"菜单"证据；
23:38 局 fade 卡 40+ 秒确实会把 4x 永久 parked 住。**但它顺手把"淡入阶段"也一起放过了** ——
而淡入正是屏幕上**没有世界可插帧**的窗口。

## 37.4 输入见证：26/26 全是 INPUT_NONE ⇒ 本局定不了"卡"的性质

```
01:30:29.715 ... in(os=0x0 dc=0/0    fg=1) plr=(0.0,0.0,0.0) plrD=0.00 PC_STILL  INPUT_NONE
01:30:31.734 ... in(os=0x0 dc=1957/1 fg=1) plr=(0.0,0.0,0.0) plrD=0.00 PC_STILL  INPUT_SEEN
01:30:52.362 ... eye=(-243.05,-415.31,118.62) eyeD=481.30 plr=(-250.3,-360.4,0.1) ... PC_MOVING INPUT_NONE
01:30:54.373 ... eyeD=0.07  ... PC_MOVING INPUT_NONE
01:30:55.379 ... eyeD=0.00  ... PC_STILL  INPUT_NONE
```

- 26 条全部 `INPUT_NONE`（`os=0x0`、`plrD=0.00`）⇒ **键盘（W/A/S/D/空格/Shift/LButton）一次都没采到按下。**
- 只有 01:30:31.734 一条 `INPUT_SEEN`，靠 `dc=1957/1`（鼠标位移）触发。
- `eyeD=0.07` 级别的 PC_MOVING ⇒ 相机只有毫米级抖动（静止）。

**⇒ 本局无法区分「世界冻了」与「玩家没操作」。** 这正是 v1.18 提交信息里写过的那句话
（"the camera cannot tell an idle player from a frozen world"），而复现它只需要用户<b>不按键</b>。

★ 注意 1 Hz 采样 + 短按会漏：`INPUT_NONE` ≠ "用户从没碰键盘"，只能说"没有持续按住"。
**⇒ 下一局的协议必须包含「按住 W 走 10 秒以上」，否则这一格永远空着。**

## 37.5 覆盖层那行「4 倍帧数」是计算值，不是实测

```
[FrameGen] FPS probe: real=37.1 | DLSSG | cap~=148.5 (=real*4, COMPUTED not measured)
           | hwMax=6 ask=4 accepted=4 | cfgProvider=1
```

- 代码自己标了 `COMPUTED not measured` ⇒ 覆盖层 = 引擎帧率 × 倍数。
- 独立仪器同期：`[PERF] 4x | Kernel: Ada | FPS: 43.8 (22.83ms) | Jitter: 8.70ms | 1% Low: 27.3 FPS`；
  而它的逐帧 CSV 全程 `DeltaMs≈29.6 ms`（1209 帧，稳定）。
- **两个口径无法互相验证**（一个是"引擎真实帧间隔"，一个是"它自己 hook 的 present 速率"）。
  ⇒ **"屏幕上每秒到底呈现多少帧"至今没有实测值。** 留到 v1.25（覆盖层改成数真实 Present 次数）。

## 37.6 v1.24 改了什么（两处）

### A. fader 重新参与守卫，带 8 秒上限 —— `src/Streamline.cpp` `GameMenuOpenNow()`

```cpp
static std::atomic<long long> s_faderOpenSinceMs{ 0 };
...
if (ui->IsMenuOpen("Fader Menu")) {
    const auto nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    long long t0 = s_faderOpenSinceMs.load();
    if (t0 == 0) { s_faderOpenSinceMs.store(nowMs); t0 = nowMs; }
    if (nowMs - t0 < 8000) return true;          // 守住：淡入期间不开 4x
} else {
    s_faderOpenSinceMs.store(0);
}
return ui->GameIsPaused() && faderUpSec < 90;    // v1.22 的原行为，超过 8 s 后回落到这里
```

- 计时器用 `std::atomic<long long>`：这条函数会被 present 线程与常量线程同时走到
  （本局 tid 2088 与 14480 都写过 `MENU EDGE`）。**不用裸 static**（L41 的教训同类）。
- 8 秒是**有界**的：fader 永不落下（23:38 局那 40 秒）不会把闸门永久 parked住。

### B. 像素探针 1 Hz → 2 Hz，判据 10 s → 3 s —— `src/DX12SwapChain.cpp`

- `pixelProbeLastMs` 门限 `1000` → `500`。
- VERDICT 条件 `pixelProbeStreak == 10` → `== 6`（3 秒），`MovedDuringStreak >= 5` → `>= 4`。
- 理由：v1.23 修好探针后判据是"连续 10 秒同哈希"，而最近三局闸门释放后只跑了
  2.5 / 6.1 / 2.6 秒 ⇒ **判据永远够不到**。
- 风险控制：跨 API 拷贝仍是 `DO_NOT_WAIT`、拿不到就 `++pixelProbeDropped` 丢弃、不重试。
  **扫描更密只会让样本变少，不会阻塞渲染线程**（v1.22 那个"每帧拷贝"的教训）。

## 37.7 未证清单（本轮新增）

| 说法 | 状态 | 依据/缺口 |
|---|---|---|
| fade 期间开 4x 是"卡+闪"的原因 | **未证** | 同现 0.364 s ⇒ 同时≠因果；且没有 INPUT_SEEN 样本，连"卡"是什么都没定住 |
| 画面内容陈旧 | **只有 1 秒证据** | `[PIXEL] #24`：`clipDev=3053.296631` 而 hash 不变（`6AD5178233020383`）；`#18–#23`/`#25–#26` `clipDev≈0` ⇒ 按 L44 **不算** |
| 本局加载 23.3 s 比前两局慢是 v1.23 引入 | **未证** | 单局样本；v1.23 的改动是**移除**每帧拷贝，方向上更快 |
| 4x 实际呈现帧率 | **无实测** | 覆盖层是计算值；CSV 只记真实帧 |
| Transfusion 与冻结的关系 | **仍未证** | 12/12 相关 + 一次毫秒同现；**本局未隔离** |
| `[MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu guard is not engaged` | **未解释** | 释放那一帧出现一次（`blocked=1156 unblocked=1`），后续 `consts ok=60` 正常，暂无后果 |

## 37.8 方法论增量（写进 L 表）

- **L47（本轮最贵的一条）：换掉一个判据之前，先枚举它原来覆盖的<b>所有</b>窗口，逐个判断新判据是否也覆盖。**
  v1.22 换掉 fader 判据时只论证了"游玩阶段 fader 不算菜单证据"，没有枚举"淡入阶段"。
  结果 4x 被开在了淡入上。**判据不是布尔值，它是一张覆盖表。**
- **L48：只看"最后两局"就下"首次发生"的结论 = 骗。**
  本轮我一度写「v1.23 首次 4x 上屏」，实际 v1.11 起就有。**"首次"这类断言必须全归档扫描
  （`grep -c` 每一局），不能靠相邻两局。** 这与 L0 的「反向假设」是同一件事的另一个切面。
- **L49：判据里的时间常量要看它的零点在哪。**
  `faderUpSec` 从**进程启动**算（函数内 `static s_faderT0`），不是从 fader 立起算。
  本局启动→退出只有 61 s，所以"90 秒上限"这个保护<b>从未参与</b>。**写"有上限保护"之前先算零点。**

## 37.9 收尾状态

- 代码：`src/Streamline.cpp` + `src/DX12SwapChain.cpp`，补丁 `tools/patch_v124_fade_guard.py`。
- 构建：`BUILD SUCCESS`（12 s）。DLL `f845e7654dd2cae4db57fe994cc5b034` · 1,369,088 B
  · build == MO2 mod 目录（`E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/`）。
- INI：源树 == 部署 `efce89119d840670e519d219749a6476`，纯 CRLF 358 行，**8 键不变（v1.24 零新键）**。
  关键值：`Provider=1` `MFGMaxFramesOverride=3` `MenuGuardFader=1` `PixelProbe=1` `InteropFenceWait=1`
  `NRAllowWithFrameGen=0` `MenuDisableFrameGen=1` `DLSSGFramesToGenerate=3`。
- 行尾：`Streamline.cpp` CRLF 2447 / lone_LF 0 / BOM 保留；`DX12SwapChain.cpp` lone_LF 2039 / CRLF 0。
- 补丁幂等：重跑 ⇒ `REFUSED, nothing written`。
- **下一局协议（必须照做，否则又是白跑）**：进世界 → 站 15 s → **按住 W 走 10 s 以上** → 松开站 10 s → 退出。

# 第 38 章：4x 是在加载屏幕上被武装的，而世界入口那帧的反投影矩阵不是仿射的（v1.25）

**局**：2026-09-20 01:55:25.480 → 01:56:20.077（55 s），v1.24 首跑。
归档 `docs/runlogs/2026-09-20-0156-v1.24-fade-guard-freeze.*`（含 transfusion.log / perf.csv / crash.log）。
世界段 = 释放后 **3.0 s**，用户退出。**这一局同样没有输入**（21 条 `[CAM] PC`，20 条 `INPUT_NONE`）。

## 38.1 先否掉一条：那 20.6 秒不是 MFG 造成的

本局看门狗在 `frames=1` 处只有 **一次**停顿：`silent=20590ms stage=d3d12 Present(dlssg) msg=0 alive=1`，
起于 01:55:39、止于 01:55:59.4 —— 进程的**第一次 Present** 就压了 20.6 秒，`msg=0`
（`SendMessageTimeoutA(SMTO_ABORTIFHUNG)` 返回 0 = 窗口被 USER32 判为未响应）。

**把 13 份看门狗归档全扫一遍**，每局都恰好有一次这样的停顿：

| 局 | 停顿 | 起于 frames | stage | msg |
|---|---|---|---|---|
| v1.11 08:27 | 19.6 s | 1 | d3d11 Wait | 0 |
| v1.13 19:39 | — | 1 | | |
| v1.17 22:38 | 21.0 s | 1 | d3d11 Wait | 0 |
| v1.18b 22:54 | 20.0 s | 1 | d3d11 Wait | 0 |
| **v1.19 23:38（FSR3，你说"活"的那局）** | **23.0 s** | **1** | **d3d11 Wait** | **0** |
| v1.21 00:31 | 22.9 s | 1 | unfocused | 0 |
| v1.22 00:58 | 20.8 s | 1 | d3d11 Wait | 0 |
| v1.23 01:30 | 21.6 s | 1 | d3d11 Wait | 0 |
| v1.24 01:56 | 20.6 s | 1 | d3d12 Present(dlssg) | 0 |

13/13，**包括那局唯一存活的 FSR3**。⇒ **加载期这一次 20 秒停顿与 MFG 无关**，是这套整合包加载时的固有行为。
「加载界面最后就卡住」如果指的是这 20 秒，那它不在本插件里。

## 38.2 4x 是在加载屏幕上被武装的（v1.24 声称修掉了，没修掉）

本局 Transfusion 的日志（**别的模块写的，不是我们的回声**）全程只有一次 DLSS-G 选项下发：

```
[2026-09-20 01:55:59.490] [tid=7244] [OPTIONS] Game DLSS-G options: structVersion=5 mode=eOn frames=3 uir=0 color=3840x2160 flags=0x00000010
[2026-09-20 01:55:59.490] [tid=7244] Applied fixed multiplier: 4x, result=0 (eOk)
```

这一毫秒同时发生三件事：
- 我方 `[XRAY] MENU EDGE open=1 serial=2`（**闸门在这一帧合上**）
- 我方 `[MFG] probe RUNS while the menu guard skips DLSS-G: step advertised=4x accepted=4x latched=1`
- Transfusion `Applied fixed multiplier: 4x`

那一帧的上下文：`consts(ok=0 fail=0)`（**一帧相机常量都没喂**）、`hrs=0.0`、`fade=1`、`[CAM] PC` 打出 `eye=(0,0,0) read=0`。
**这是加载屏幕。** 此后到 01:56:17.044 世界入口，17.5 秒里运行时一直被留在 4x 上。

**为什么 v1.24 没挡住**：v1.24 把 fader 加回了 `GameMenuOpenNow()`，但**武装不走那条路**。
`ProbeMfgLadder()`（`src/Streamline.cpp:2042`）按 v0.79 的设计**故意跑在菜单闸门之前**，
而它在 `DX12SwapChain.cpp:1412` 的调用条件只有 `fgOn && featureDLSSG` —— **没有 menuBlock 项**。
于是它是整个进程里唯一一条「闸门合上时仍在和运行时说话」的路径。
**判据不是布尔值，是一张覆盖表（L47）**：v1.24 数了 Present 那张，没数阶梯那张。

## 38.3 世界入口那一帧，交给 DLSS-G 的反投影矩阵不是仿射的

**两个独立来源给出同一条错矩阵。**

我方 `[XRAY] serial=848`（01:56:17.103，释放后 59 ms）：
```
clipDev=243.962387 clipW=-195.222366 p00(c/p)=1.1918/0.0000
reproj src=fixed engPrevEqCur=1/1 engPrevZero=0 frozen=0
cam(ok/inv)=1/0 camPrev(ok/used)=0/0 hist(hit/miss)=1/0 seed=1 missGood=0
fix(src=2 dev=414.178)
```
Transfusion 同一毫秒（01:56:17.103）：
```
[MOTION] clipToPrev rows=[0.999993265 ...][...][...][-243.962387 2.7390945 -77.6724777 -195.222366]
         cameraPos=(-243.049286,-415.311523,118.558205)
```

**机理**（读代码即得，不是猜）：`prevForReproj` 有三个候选，分属**两个家族**——
`camPrevVP` / `s_prevVP` 是「从 R + eye 重建的相机」（**带平移**），
`engPrevViewProjSL` 是「引擎自己的副本」（**无平移**）。
但取逆的那个表达式是 `camCurOk ? camCurVP : curForReproj` —— **按当前帧选的，不是按 prev 的家族选的**。
世界入口那一帧 `s_hasPrevVP` 还是 false（整段加载 `curOk` 都是 false），而 `camCurOk` 已经是 true：
`inv(带平移) × 无平移` ⇒ 不可取消 ⇒ `w = -195`。

三个计数器把这条路径钉死了：`seed=1`（prev 来自引擎种子）、`camPrev(ok/used)=0/0`（重建的 prev 没用上）、
`cam(ok/inv)=1/0`（当前帧是有效的）。

**而且这条错矩阵被用了，不只是被警告了。** 文件里早就算了 `clipW` 并在注释里写明「w 必须等于 1」，
但接受判据只有 `clipMagAll < 1e30 && > 1e-6` —— **只测量级，不测仿射性**。
于是 `w=-195` 通过、被写进 `s_lastGoodClip`、被交给 DLSS-G。Transfusion 的 row dump 就是它真的到了运行时的证据。

**为什么这条线比别的嫌疑更像"和 4x 绑在一起"**：全归档扫描，
MOTION 警告 13 局 12 局各 1 条，**唯一 0 条的就是 FSR3 那局（Provider=0，DLSS-G 没启用）**。

## 38.4 覆盖层的「4 倍帧数」是算的，而且和一个独立读数差 3.6 倍

我方 FPS probe：`real=50.3 → 53.3 → … → 39.0 → 33.4`，`cap~=real*4`。
同一进程里 Transfusion 的 `[PERF]`（300 帧窗口，自己的读数）：

| 时刻 | 我方 overlay 会显示 | Transfusion 实测 |
|---|---|---|
| 01:56:15.870 | real=44.7 → **179（=44.7×4）** | **49.3 FPS**（1% low 29.1）|
| 01:56:10.852 | real=52.4 → 210 | 52.4 FPS |

**Transfusion 的 49.3 ≈ 我方的 real 44.7，不是 real×4。**
`dlssgFramesPresentedLast` 是 `slDLSSGGetState` 的**回报**，`s_fps` 是这里实测的呈现间隔，两者相乘是**推断**。
⇒ **呈现帧率至今没有实测值**，三个口径互不一致（回报 4×／Transfusion 49.3／我方 dt 30 ms）。
你说「看到左上角得帧数变成4倍」—— 那个数字就是这么来的，它不能当作「4x 生效了」的证据。

**加载期它反而是对的**：`DLSSG presented per real frame = 1` 出现 10 次（全在闸门内），
换到世界后 2 次 `= 4`。所以那 5 分钟里运行时确实没插帧。

## 38.5 像素探针的判据说反了自己

本局 01:56:14.377 打出了 v1.24 新写的 3 秒判据，原文：

```
[PIXEL] 3 identical seconds, but the camera was still on 0 of them - ...
```

`pixelProbeMovedDuringStreak` 数的是**相机在动的样本数**，而句子把它念成「相机静止的样本数」——
**数字 0 被念成了它自己的反义**（0 = 一次都没动过，句子读起来却是"一次都没静止过"）。
这条文案会让人把「站桩」读成「陈旧已证」。探针本身读数：`#40 changed=20 unchanged=19 maxStreak=7 dropped=0`。

## 38.6 v1.25 改了什么（四处，都有上面那几条读数兜底）

| # | 位置 | 改动 | 兜底证据 |
|---|---|---|---|
| A1 | `Streamline.cpp` | 给 `prevForReproj` 加家族标记（`prevIsRebuilt` / `s_prevVPIsRebuilt`），取逆按**同家族**选 | `seed=1` + `camPrev=0/0` + `cam(ok)=1` + `w=-195`（我方与 Transfusion 双侧）|
| A2 | `Streamline.cpp` | 接受判据加**仿射闸**：`|w-1| <= 0.01`，不过则退回 last-good / 单位阵 | 同 38.3；阈值用的是文件自己已有的 `wDev > 0.01` 判废线 |
| B | `Streamline.cpp` `ProbeMfgLadder()` | 闸门合上时**不碰运行时**（连 setOptions 都不发），边沿各打一行 | Transfusion `[OPTIONS] frames=3` 全程仅 1 次、且落在 serial=2 / fade=1 |
| C | `DX12SwapChain.cpp` | 像素判据文案改成数它真正数的东西 | 38.5 |
| D | `ImguiMenu.cpp` | 覆盖层拆开显示两个因子：`156 FPS  [39 real x4 reported]` | 38.4 的 3.6 倍分歧 |

**B 的安全性**：它替代的正是 Present 的 `menuDisableFrameGen && MenuIsOpen()`（`DX12SwapChain.cpp:1392` 的 `menuBlock`），
而 Present 在这个窗口里本来就不生成（`presentedMenu=0/819/0/…`）⇒ **不会少掉任何一帧本可生成的帧**。
判据与 Present 逐字对齐（都含 `menuDisableFrameGen`），否则 `MenuDisableFrameGen=0` 的用户会被这个守卫误伤。

## 38.7 交付与未证

构建 `BUILD SUCCESS`；DLL **1,369,600 B md5 `7cb1e6546857e120f4a242d99d986d82`**，**build == MO2 部署目录**；
`Streamline.cpp.obj` 02:05:13 < DLL 02:05:16；DLL 内新串各 1、旧串各 0；INI **未动** `efce89119d840670e519d219749a6476`（8 键、零新键）。
补丁 `tools/patch_v125_affinity_and_ladder_guard.py`（9 处锚点各 count==1，干跑默认，重跑逐条 REFUSED）。
行尾：Streamline CRLF 2532 / lone_LF 0 / BOM 保留；DX12SwapChain 纯 LF 2044；ImguiMenu CRLF。

**未证，不许当成已修**：
1. 那**一帧**的非仿射矩阵是不是"卡死"的原因 —— 未证。它只坏了一帧（`hist 31/0` 之后即恢复），1 帧不一定冻屏。
2. 「加载期武装 4x」是不是原因 —— 未证。加载期本来就没插帧（`presentedMenu` 全 1）。
3. DLSSG-Transfusion 与冻结 —— 仍是 **12/12 相关 + 两次时间戳同现**，**未证**。隔离实验（`DINPUT8.dll` → `DINPUT8.dll.transfusion-off`）**至今没跑过**。
4. 世界是否响应输入 —— 本局 20/21 `INPUT_NONE`，**这格还是空的**。
5. 呈现帧率 —— 仍无实测值（38.4）。

# 第 39 章：4x 是实测的 4.00；而"活着"那局和冻结局，我们的见证读数完全一样（v1.26）

局：**2026-09-20 02:24:11 → 02:25:20（69 s）**，v1.25 首跑。
归档 `docs/runlogs/2026-09-20-0225-v1.25-affinity-gate.*`（含 transfusion.log / perf.csv / crash.log）。
DLL `7cb1e6546857e120f4a242d99d986d82` 1,369,600 B —— 已核对部署副本 md5 一致（build == MO2）。
★ 日志里 `loaded (build Sep 20 2026 01:06:38)` 是 **FrameGen.cpp 的 `__DATE__ __TIME__`**，本轮只改了
  Streamline/DX12SwapChain/ImguiMenu ⇒ 那个 TU 没重编，时间戳停在 v1.23。**别拿它当版本判据**，
  版本判据只能是 md5 + 二进制内新串。

## 时间线（本局全部关键事件）

| 时刻 | 事件 |
|---|---|
| 02:24:11.111 | 插件加载 |
| 02:24:29.2 | 两条 swapchain 建好、探针 armed、`[PRESENT] census: first presenter tid=22736` |
| **02:24:29.3 → 02:24:59.3** | **30.0 s：`frames` 冻在 1，`msg=0`**（见下"修正一"） |
| 02:24:59.306 | 第一批相机常量到达；`MENU EDGE open=1 serial=2 consts(ok=0)`；**`[MFG] ladder held back`** |
| 02:24:59.4 → 02:25:17.5 | 加载界面在渲染：frames 1 → 862（≈48 fps），`ask=4 accepted=0` |
| 02:25:09.322 | `stall governor: frame took 535 ms` |
| 02:25:17.498 | `MENU EDGE open=0 serial=862`；`ladder resumed`；**全进程唯一一次** DLSS-G 选项下发 `frames=3` → `Applied fixed multiplier: 4x` |
| 02:25:17.711 | `DLSS-G actual presentation count: 4x` |
| 02:25:17.5 → 02:25:20.7 | 世界段 3.2 s：相机静止、输入 21/22 `INPUT_NONE`、`hrsD≈0.0057`、`[PIXEL]` 每次样本都变 |
| 02:25:20.7 | 用户退出（`msg=1 alive=1` 到最后一行） |

## 一、v1.25 的两项修复，均已由"别人写的"日志验证

1. **A（家族匹配取逆 + 仿射闸）成立**：全档 `MOTION` 计数 = **0**（此前 13 局里 12 局各 1 条），
   我方 `clipW` 全档只有 `1.000000`（此前世界入口那帧是 `-195.222366`）。
   Transfusion 同一毫秒的 `[MOTION] clipToPrev rows` 变成
   `[0.99999994 9.45e-14 …][…][…][-1.53e-05 5.78e-06 -6.10e-05 0.99999994]` —— **w≈1，仿射了**。
   （call=0 那帧 rows=identity 且 `reset=1`，那是世界入口的重置帧，合法。）
2. **B（阶梯不碰运行时）成立**：Transfusion 全档 `[OPTIONS]` **只有 1 条**，时间 **02:25:17.498**，
   正是闸门释放那一毫秒。加载期 17.5 s 内运行时**一次都没被碰过**。
   对照 v1.24 那局：唯一一次下发落在 **02:24:59.490 的加载屏幕**（serial=2）—— v1.24 声称修了但没修，
   v1.25 真修掉了。

## 二、新硬结论：**4x 是实测的 4.00**

看门狗里有两个独立计数：`frames`（我方 `Present()` 调用数）与 `lastPr`（DXGI 自己的
`GetLastPresentCount`）。两者同窗相除 = **swapchain 每真实帧真正翻转了几次**。

| 时刻 | frames | lastPr | ΔlastPr/Δframes |
|---|---|---|---|
| 02:25:17.396（闸门未开） | 857 | 857 | **1.00** |
| 02:25:18.013 | 879 | 906 | **4.00** |
| 02:25:19.043 | 913 | 1042 | **4.00** |
| 02:25:20.674 | 968 | 1262 | **4.00** |

- 加载全程 = **1.00**（v1.25 B 的直接证据）；
- 闸门释放之后 = **4.00**，一直到最后一行。
★ 这是 **DXGI 自己**的数 —— 既不是"我方向运行时要的数"，也不是"运行时回报的数"。
**「呈现帧率无实测值」这条挂了二十个版本的未证项，到此结案：4x 是真的，实测 4.00。**
同时它也解释了那个三方分歧：Transfusion `[PERF] FPS: 34.7` 量的是**真实帧率**
（我方同刻 `real=33.4`，两者一致），不是呈现翻转率。翻转率 ≈ 33.4×4 ≈ 134 /s（160 Hz 面板内）。

## 三、★★★★★ 重大修正：**"活着"那局和冻结局，我们的见证读数完全一样**

把活着那局 **23:38（v1.19 FSR3）** 的世界段拉出来与 02:25 逐字对照：

| 读数 | 23:38 那局（用户说"画面活了"） | 02:25 这局（用户说卡死） |
|---|---|---|
| `eye` | `(-242.80,-415.30,118.60)` **全程不变** | `(-243.05,-415.31,118.56)` **全程不变** |
| `eyeD` | **0.00**（38 条里 38 条） | **0.00** |
| `plr` | `(-250.3,-360.4,-0.0)` | `(-250.3,-360.4,-0.0)` |
| `plrD` | 0.00 | 0.00 |
| `hrsD` | 0.00563 ~ 0.00581（在走） | 0.00574 ~ 0.00605（在走） |
| 输入键位 `os` | **0x0**（全档没按过 W/A/S/D/空格/Shift/鼠标键） | **0x0** |
| 形态 | `PC_STILL` | `PC_STILL` |

⇒ **我们手上没有任何一个量能把"用户说活着"和"用户说冻了"分开。**
所以之前几轮里我说的"相机静止 ⇒ 世界冻了"，**没有依据** —— 它在活局里同样静止。
`hrsD>0` 只证明游戏循环在跑（这个一直成立），`eyeD=0` 只证明相机没动（这个也一直成立）。

**这直接决定了下一件该测什么**：用户报的是**画面闪烁**，而"闪烁"恰恰是现有像素探针
**结构性看不见**的东西 —— 振荡的画面每个样本都和上一个不同 ⇒ `chg=1` ⇒ 读成最健康。
（02:25 世界段 7 个样本 7 个 `chg=1`，`clipDev=0.000061` 相机根本没动。）

## 四、v1.26 改了两处（都是仪器，不是功能）

**A. `PixelProbeTick()` 加"振荡（闪烁）"检测**
- 采样块同时算**平均字节亮度** `lum`（沿原 FNV 循环顺手累加，`RowPitch` 填充是稳定的，
  只会把均值稀释一个固定量，造不出假摆动）。
- 保留最近 **8 个** `(hash, lum)`。判据：8 个样本里**不同 hash 数 ≤ 3** 且**亮度摆幅 > 40/255**
  ⇒ 打 `[PIXEL] FLICKER` 并附上整个 8 窗口。样本行加 `lum= seen=/{}/ swing=`。
- 这条判据**不需要输入、不需要相机移动** —— 而依赖"玩家走路"的旧判据，自加入以来一次都没可能触发。

**B. FPS 探针加一行"实测倍率"**
`[FrameGen] FLIPS per real frame = X.XX (DXGI lastPresentCount a -> b, our Present c -> d)`，
每 2 s 与 FPS probe 同行输出。**并给 FSR3 分支补上 `GetLastPresentCount`**（v0.74 起只有
DLSS-G 分支记录它）—— FSR3 是唯一活过的 provider，这个不依赖运行时的读数在那儿原本是缺的。

## 五、两条否定（A≠B）

1. **first-chance 访问违例与本故障无关**。本局 crash log 有 3 条
   （`code=0xC0000005`，faulting module = `D:\ENB-EJ\Skyrim Special Edition\DINPUT8.dll`
   = Transfusion 本身，`rva=0x7B9D`，读 `C:\ProgramData\NVIDIA\NGX\models\dlssg\…\160_876232C.bin`
   的 MZ 头，`Rax=0x5A4D` —— 它在扫 NGX 的 dlssg 模型 blob）。
   但**逐局计数是 3 / 0 / 3 / 0 / 3**（00:31=3、00:58=0、01:30=3、01:56=0、02:25=3）
   ⇒ **既出现在冻结局，也出现在没有的局** ⇒ 与冻结无相关。划掉。
2. **"加载期武装 4x 有害"** 这条仍然没有被本局推翻也没有坐实，但本局加载期的
   `lastPr/frames` 恒为 **1.00**，说明那 30 秒里没有任何多余翻转。

## 六、修正一：那 30 秒停顿**不在我方 `Present()` 里面**

我上一轮说"停顿的 stage 是 `d3d11 Wait`，那是我们的围栏等待"。**这个读法是错的**：
- 那段里 `frames`（= `++frameCounter`，写在 `Present()` 第 921 行、**在任何调用之前**）从 1 不动
  ⇒ **渲染线程 30 秒里一次都没再进过 `Present()`**；
- `presentAge` 也是**陈旧的**：它量的是 `nowMs - g_presentEnteredMs`，而 `g_presentEnteredMs`
  停在 02:24:29.309（第一帧那次）没更新过 ⇒ 26 s 的 `presentAge` 是同一枚旧时间戳；
- 所以 `stage=d3d11 Wait` 是**上一帧结束时留下的名字**，不是当前所在位置。

⇒ 结论只能是：**渲染线程卡在我们看不见的地方（引擎侧）**，看门狗没有能力给它命名。
这条要把"看门狗的 stage 名"降级为"最后一次写下的名字"，不能当"当前所在调用"读。

## 七、v1.26 未证（不装懂）

- **闪烁是否真实存在** —— 未证。用户从 23:38 那局起就一直在说"闪烁"，但**至今没有任何一个
  仪器量过它**。v1.26 A 就是为它造的，**它是否触发，要看下一局**。
- 那 30 秒停顿是不是病态 —— 未证。13/13 局都有（含 FSR3 活局 23.0 s），本局 30.0 s 是最长的一次。
- 世界段 3.2 秒、`INPUT_NONE` 21/22 —— **本局又一次答不了"世界响应输入吗"**。
- Transfusion 与冻结 —— 仍 **12/12 相关**，**隔离实验（`DINPUT8.dll` 改名）至今一次都没跑**。

# 第 40 章：v1.26 的闪烁判据第一次运行就报了假阳性；而加载那 27.8 秒有了四重独立证据（v1.27）

**局**：2026-09-20 02:38:48.520 启动 → 02:39:31.667 停顿结束 → 02:39:47.359 闸门放开 → 02:39:49.464 结束（61 s）。
**世界段只有 2.1 秒**，输入见证 18 条（5 条 `INPUT_SEEN` 全部由鼠标位移 `dc=` 判定，**`os=0x0` 全程**）。
归档 `docs/runlogs/2026-09-20-0239-v1.26-flicker-probe.*`。
（★ 日志里那行 `loaded (build Sep 20 2026 02:30:46)` 是 `__DATE__ __TIME__`，只改 DX12SwapChain/ImguiMenu 时
`FrameGen.cpp` 不重编 ⇒ **版本判据只能靠 md5 + 二进制内新串**。）

## 一、★ 我上一轮造的闪烁判据，第一次运行就是**假阳性**

v1.26 B 触发了 2 次（02:39:35.210 / 02:39:35.716），窗口内容逐字是：

```
[BE7FB0911BE00383 0.0] [BE7FB0911BE00383 0.0] [203DB5612A786408 104.0] x6
```

= **黑、黑、亮 ×6**。这是**一次单调转变**（加载屏幕由黑变亮），**不是振荡**。
配套证据：`[PIXEL] #9 … chg=0 streak=6` —— `streak=6` 说明**连续 6 个样本 hash 相同**，
即窗口末端是**稳定的**，一个真正的振荡不会连 6 个样本不动。

而 v1.26 的判据是 `distinct <= 3 && swing > 40` —— **"一次转变"两条全满足**：
落在 2 个状态上、摆幅 104/255。⇒ **判据缺的是"它回来了没有"。**

⇒ **已在 v1.27 修**：加 `switches`（窗口内相邻 hash 不同的次数）与 `maxRun`（最长同 hash 连续段），
判据改为 `fill>=8 && distinct<=3 && switches>=3`（至少 A→B→A→B），**swing 不再作闸、只打印**
（两个亮度几乎相同的画面来回跳，仍是闪烁，用 40/255 卡会漏掉它）。

★ 由此得到 **L53**：**新判据的第一次运行要按"校准"读，不能按"证据"读。**
我上一轮把 `[PIXEL] FLICKER` 称作"闪烁第一次被测到"，**那是错的** —— 判据自己还没被验证过。

## 二、★ 那 27.8 秒停顿：四重独立读数，且都不支持"卡在我们代码里"

| 读数 | 停顿期间（02:39:04 → 02:39:31.5） | 恢复那一瞬（02:39:31.747） |
|---|---|---|
| `frames`（`++frameCounter`，DX12SwapChain.cpp:921，Present 入口） | 一直 **1** | **4**（201 ms 内 +3） |
| `fence`（`fenceValue`，只在 Present 里 ++） | 一直 **2/2** | **18/18** |
| `lastPr`（**DXGI 自己的** `GetLastPresentCount`） | 一直 **1** | **4** |
| `presentAge`（`now - g_presentEnteredMs`，:788-789） | 305 ms → **27809 ms** | 13 ms |

**`presentAge` 的定义是"距上次*进入* Present 的时间"** ⇒ 它涨到 27809 ms 就是
**27.8 秒没有进入过 `Present()`** 的直接读数，不需要任何推断。
`fenceValue` 也冻在 2 ⇒ 不是"进了但卡在中间"。

旁证：我方日志 **02:39:03.737 → 02:39:31.601 整整 28 秒零输出**；
Transfusion 同期只有每 5 秒一次的 `[STARTUP] worker alive` 心跳；
**`lastPr` 冻在 1 = DXGI 一次翻转都没有 ⇒ 屏幕 27.8 秒没有任何新画面。**

**⇒ 14/14 局都有这个停顿**（此前 13 局 19.4–23.0 s ＋ 本局 27.8 s，本局是最长的一次），
**包括 23:38 那局 FSR3（画面被报告为"活的"）**。
⇒ 它**不是 4x 造成的**，也**不是本插件造成的**。

## 三、v1.25 两处修复：由"别人写的"日志独立确认

- **A（家族匹配取逆 + 仿射闸）**：Transfusion `[MOTION]` 的 rows 全部 w≈1
  （`[…][…][…][-1.52587891e-05 5.78165054e-06 -6.10351562e-05 0.99999994]`），
  **世界入口那帧再没出现过 `-195.222366`**。
- **B（闸门合上时连 setOptions 都不发）**：Transfusion 全档 `[OPTIONS]` **只有 1 条**，
  落在 **02:39:47.359** —— 正是 `MENU EDGE open=0 serial=682` 那一毫秒。
  加载的 15.7 秒里**运行时一次都没被碰过**。
  ⇒ 三局连续对照：v1.24 落在**加载屏幕**（声称修了其实没修）→ v1.25 落在**闸门放开那毫秒** → v1.26 **同样**。

## 四、本局排除的三条（都用已有数据，零成本）

1. **`[CAM] #1 non-affine w=0 ACCEPTED (v0.89)` 不是漏网**。
   `FrameGen.cpp:928-943` 的注释原文："The guard is **removed**. The OBSERVATION is kept,
   now non-destructive"，`// NO return false: the snapshot is published as before v0.86`。
   它喂的是**相机快照**（`CameraViewProjUnjittered`）；DLSS-G 的反投影在**另一条**路径
   （`Streamline.cpp:1260` 的 `clipAffine`）。而且 `pos=(-50,600,80)` + `proj00=0.149184`
   是**加载期空相机**的已知特征。
2. **Reflex cap 的倍数是对的**：世界段 66 条 `… = 39.8 rendered fps at 4x`，
   加载段 682 条 `… = 79.5 rendered fps at 2x` ⇒ 会正确切换，不是 bug。
3. **两个 present 线程与冻结无关**：**16/16 局**（含 23:38 FSR3 活局、含 v1.11 以来每一局）
   都有 `census: NEW presenter tid=… now 2 distinct threads`。
   本局 PIXEL 行的 tid 分布还显示**不是逐帧交替，是分段接力**（31920 ×14 → 10692 ×2 → 31920 ×11 → 10692 ×8），
   但既然 16/16 都有（含活局），它**不是切分变量**。

## 五、v1.27 两处

- **A** `src/DX12SwapChain.cpp`：闪烁判据加"必须回来"（`switches >= 3`），`swing` 降级为打印；
  PIXEL 行新增 `sw=` / `maxRun=`，FLICKER 文案写明"单向转变不算"。
- **B** `src/ImguiMenu.cpp` 覆盖层加**世界段计时**：以 `mult > 1`（**运行时回报**的上升沿，不是我们的名字）
  为起点，`< 20 s` 显示 `KEEP PLAYING, hold W for 10 s`，`>= 20 s` 显示 `enough - you can exit now`。
  要解决的是一个具体浪费：**最近 5 局的世界段是 2.1 / 3.0 / 3.2 / 2.5 / 6.1 秒**，
  而本项目所有仪器要回答的那个问题（世界响应输入吗、画面在推进吗）**从来没有过够长的世界段**。

## 六、方法论

- **L53（本轮最贵）**：**新判据的第一次运行要按"校准"读，不能按"证据"读。**
  「少数状态 + 大差异」**同时**被"一次转变"和"来回振荡"满足 ⇒ 判据里必须有"**它回来了**"这一条
  （数变化次数），不能只数"有几个状态"和"差多少"。
- **L54**：`frameCounter` 只数"进入过几次"，**分不出"从未进入"与"进入后卡住"**；
  分辨要靠"距上次进入的时间"（本文件已有 `g_presentEnteredMs` / `presentAge`）。
- **L55**：post-check 里"旧锚点应消失"对**追加型**锚点**恒失败**（`new` 包含 `old`）。
  判据要写成 `old in raw and old not in new`。**（L51 的第二次踩 —— 这次是检查器自己的 bug。）**

## 七、未证（不装懂）

- **闪烁是否真实存在** —— **仍未证**。v1.26 B 的两次报告都是假阳性；v1.27 修好之后**还没跑过**。
- **那 27.8 秒里引擎在做什么** —— 未证。双方日志都静默，唯一的硬读数是 **DXGI 零翻转**；
  要往下走需要栈采样，现有仪器做不到。
- **4x + DLSS5 同时**（总目标）—— 未成功。
- **Transfusion 隔离实验**（`DINPUT8.dll` → `DINPUT8.dll.transfusion-off`）—— **至今一次都没跑**。
- 覆盖层的 `s_worldSeen` / `s_worldSince` 是**函数内 static、非原子**，
  假设 ImGui 绘制是单线程。若两个 present 线程都会走到这里，计时可能闪出一个异常值（只影响显示，不影响日志）。


# 第 41 章：世界第一次真的活了 —— 4x 实测 4.00、相机链路打通；而我的闪烁判据第二次误报，同一个环里藏着两个 bug（v1.28）

**局**：2026-09-20 03:16:37.626 启动 → 03:16:50.575~03:17:10.861 停顿 **20.8 s** → 03:17:24.708 闸门放开
→ 03:17:30.4 结束（53 s）。**世界段 5.7 秒**，20 条 `[CAM] PC` 全部 `os=0x0`。
跑的是 **v1.27**（dll 1,379,328 B，md5 `28fdec107d605defae6b4707e2e56da3`）。
归档 `docs/runlogs/2026-09-20-0317-v127-first-live-world-4x-measured.*`。

## 一、★ 15 局里第一次：相机链路、世界时钟、4x 三者同时是活的

| 量 | 之前所有局（含 FSR3 活局） | **本局** |
|---|---|---|
| `[CAM] PC` 的 `read=` | **0**（读不到相机） | **512 / 528 / 608 / 672** |
| `match=` / `adopt=` | `0` / `0` | **480 / `1/1`**（`rej=267`） |
| `eye=` | `(0.00,0.00,0.00)`，`proj00=0` | **`(-243.05,-415.31,118.56)`，`proj00=0.8391`** |
| `plr=` | `(0.0,0.0,0.0)` 或占位 `(2048,2048,0)` | **`(-250.3,-360.4,-0.0)`**（真实坐标） |
| `paused= / ld=` | `1 / 1` 全程 | **`0 / 0`**（第 13 条起） |
| `hrsD`（游戏时钟） | `0.000000`（不动） | **`0.004723 → 0.005799`** |
| `presented all=` | 几乎只有 `2x` 槽 | **`0/14/0/0/292/0/0/0`**（4x 槽 292 帧） |
| `mult(acc/pres)` | `4/1` | **`4/4`** |

- **4x 是实测的**：`FLIPS per real frame` 在闸门放开前一直是 **1.00**，03:17:26.972 起 **3.95**、
  03:17:28.976 起 **4.00**（DXGI 自己的 `GetLastPresentCount` 673→926→1178，我方 Present 674→738→801）。
- 旁证（"别人写的"日志）：Transfusion `[PERF] 4x | Kernel: Ada | FPS: 34.1`，
  `DLSS-G actual presentation count: 4x`，`Applied fixed multiplier: 4x, result=0 (eOk)`。
- 世界段健康：watchdog 尾行 `frames=846 silent=18ms ... fence=1680/1680 lastPr=1362 presentAge=1ms alive=1`，
  整段 `silent` 都在 3~35 ms，`presentAge` 个位数~35 ms。
- **v1.25 的两处修复继续成立**：Transfusion 全档 `[OPTIONS]` **只有 1 条**（03:17:24.717，闸门放开那一毫秒）；
  `[MOTION]` 第一条 `reset=1` 是 identity，其后 3 条是近单位阵 `[0.99999994 9.45e-14 ...]`，
  **`-195.222366` 没有再出现**。

⇒ **"进不去世界 / 世界是死的"这个说法，本局被推翻了**：至少有一局，世界、时钟、相机、4x 四件事同时在工作。

## 二、★ 闪烁判据第二次误报，而且同一个环里藏着两个 bug

v1.27（`switches >= 3`）在本局触发 **2 次**（03:17:21.617 / 03:17:24.659），两次窗口逐字是：

```
[3D2ED0A433B46771 96.6] [AEAB5E65C0210DFE 96.6] [6AD5178233020383 43.0] x6
[6AD5178233020383 43.0] x4 [5F9EB3FEDCEF8383 63.8] x3 [7DDF048D32FCE9A5 73.4]
```

**两条都是单向亮度渐变**（加载屏幕由亮转暗 / 由暗渐亮），**没有一次回返**。两次都发生在**世界进入前后**。

**为什么 v1.27 会放它们过去 —— 两个 bug 叠在一起：**

1. **环形缓冲被当成普通数组扫描。** 样本写在 `pixelProbeRingHash[pixelProbeRingAt]`，
   所以槽位顺序 = 写入顺序被 `ringAt` 旋转过。`distinct` 侥幸没坏（它与顺序无关），
   `switches` / `maxRun` **全错**。铁证：`#21` 打出 `sw=3 maxRun=5`，而该窗口尾部是
   **6 个完全相同的样本**（`6AD5178233020383` × 6）⇒ `maxRun` 只能是 6。
2. **"数变化次数"本身不是"回返"的正确表达。** 一个渐变序列也能让变化次数很高；
   反过来，靠 bug 1 抬高的 `switches` 把一个单向转变抬过了 3 的闸门。

⇒ v1.28 的判据换成**折叠后的回返**：把窗口压成"相邻去重后的状态序列"，只要其中**任何状态出现两次
（非相邻）**就算回返。一个单向转变**在构造上**就不可能满足它。

```
单向渐变   [a b c c c c c c] -> [a b c]            -> rev=0   不触发
加载亮起   [a a b b b b b b] -> [a b]              -> rev=0   不触发
真振荡     [a b a b a b a b] -> [a b a b a b a b]  -> rev=12  触发
```

同一处还新增 **`shape=[...]`**：把窗口按状态编号打印，**肉眼可读**，不再需要拿哈希去推：

```
shape=[0 1 2 2 2 2 2 2]   <- 单向，一眼是单向
shape=[0 0 1 1 1 1 1 1]   <- 亮起，一眼是单向
shape=[0 1 0 1 0 1 0 1]   <- 振荡
```

`shape` 是给下一轮**校准**用的（L53）：判据第一次跑不能当证据读，但形状可以当校准读。

## 三、那 20.8 秒停顿第四次以同样的四重读数出现（**15/15 局**）

```
[7487445] 03:16:50.575 frames=1 silent=519ms  stage=d3d11 Wait fence=2/2 lastPr=1 alive=0 presentAge=523ms
[7493268] 03:16:56.398 frames=1 silent=6342ms stage=d3d11 Wait fence=2/2 lastPr=1 alive=1 presentAge=6346ms
...                                                                （一直涨到）
[7493268] 03:17:10.861 ... frames=1 silent=20789ms ... lastPr=1 presentAge=20789ms
```

- `frames` **恒为 1**、`lastPr`（**DXGI 自己的**）**恒为 1**、`fence` **恒为 2/2**、`presentAge` 涨到 **20789 ms**。
- 独立佐证：XRAY `dt min/avg/max=17.46/52.04/20827.56ms`；我方日志 **20.8 秒零输出**；
  `[PIXEL]` 探针 03:16:50.032 armed 到 03:17:10.862 第一个样本 ⇒ **中间一个采样都没有**。
- 与第 40 章那 27.8 s **逐字同形**，只是短了 7 秒。**15/15 局都有**（含 FSR3 活局）。
- 停顿结束后**一切正常**（本局第一节）。⇒ 停顿与"世界是死的"**不是同一件事**。

## 四、v1.27 的覆盖层计时，在任何归档里都不存在

v1.27 B 给覆盖层加了世界段计时（`KEEP PLAYING, hold W for 10 s` / `enough - you can exit now`，
`src/ImguiMenu.cpp:241-278`）。本局 `mult=4` 从 03:17:26 起成立，按代码它**应该**在屏幕上。

但 `grep -F "KEEP PLAYING"` 在**整份日志里 0 条** —— 因为那段代码**只画不打日志**。
于是"用户到底看没看到提示"这个问题，**用现有归档无法回答**；而本局 20 条 `[CAM] PC` 仍然 `os=0x0`
（一个移动键都没按过）。**在把"玩家没照协议做"当成解释之前，得先能证明提示出现过。**

## 五、v1.28 三处（`src/DX12SwapChain.cpp` 纯 LF；`src/ImguiMenu.cpp` 纯 CRLF）

- **A**：像素窗口改按**环序**读取（修 `switches`/`maxRun` 的顺序 bug）；判据换成
  `fill>=8 && distinct<=3 && revisits>=1`；PIXEL 行新增 `shape=[...]` / `rev=`；FLICKER 文案改写。
- **B**：watchdog 行新增 **`cpuD=`**（本进程 user+kernel 时间在这 200 ms 里的增量）。
  这是这条停顿上**第一个不来自我们、也不来自 DXGI** 的读数：
  `cpuD≈0` ⇒ 进程在**阻塞**（IO / 锁 / 驱动等待）；`cpuD≈200` ⇒ 有一个线程在**烧满一个核**；
  `cpuD>200` ⇒ 多线程在跑。`GetProcessTimes` 只读，不可能扰动进程。
- **C**：`[MFG] debug CHECK` 的文案（`menuBlock=0 frames={}`）**名实不符** ——
  `menuBlock=0` 是写死的字面量，而 `frames=` 印的其实是 `debugOk`。改成 `dlssgOk={}`。
  （**这是 L50 的又一次踩**：文案必须和它打印的那个量同名。）

## 六、方法论

- **L56（本轮最贵）**：**同一段代码里的两个 bug 会互相掩护。** 我用"窗口是单向的"去判断判据对不对，
  而 `switches` 这个数本身就是被顺序 bug 抬高的 —— 我拿一个坏掉的数去验另一个坏掉的判据。
  **改判据时必须把同一段代码里这个数是怎么算的读一遍**，不能只看它的名字。
- **L57**：**"它回来了"不能用"变化了几次"表达。** 任何 N 个状态的序列都能让变化次数很高；
  正确表达只有一个：**折叠后的序列里出现重复元素**。
- **L58**：**只在屏幕上显示的东西，在任何归档里都不存在。** 一条提示如果只画不打日志，
  那么"用户没看到 / 看到了没照做"这两件事**无法区分** —— 而这恰好是下一局要不要白跑的前提。

## 七、未证（不装懂）

- **闪烁是否真实存在** —— **仍未证**。v1.26 判据的两次报告是假阳性，v1.27 判据的两次报告**也是**
  （见第二节）。本局 500 ms 采样只看到加载屏幕的单向亮度渐变。**v1.28 的判据还没跑过。**
- **500 ms 的采样率够不够** —— 未证。若闪烁是"整屏闪黑一帧"（16 ms 量级），2 Hz 采样**抓不到**。
  本局没有任何证据能排除这种闪烁。**下一轮若要动，只动这一个变量（提频）。**
- **那 20.8 秒里进程在做什么** —— 未证，但 v1.28 B 的 `cpuD=` 就是为它准备的第一个 OS 侧读数。
- **4x + DLSS5 同时**（总目标）—— 未成功。本局 `presented all=0/14/0/0/292/...` 只有 2x/4x 槽有数。
- **Transfusion 隔离实验**（`DINPUT8.dll` → `DINPUT8.dll.transfusion-off`）—— **仍然一次都没跑**。
- **crash log**：本局 1 次 first-chance（`code=0xC0000005`，`Rax=0x5A4D`，读
  `nvngx_dlssg.dll` 的 MZ 头），与第 39 章的 3/0/3/0/3 同形 ⇒ 仍与冻结无相关。


## 八、附：`core.autocrlf=true` 是一把对着行尾铁律的枪（本轮新发现）

本工程有一条行尾铁律（`src/DX12SwapChain.cpp` 纯 LF；`src/ImguiMenu.cpp` / `src/Streamline.cpp`
纯 CRLF+BOM；账本 / 记忆 / 日记纯 LF）。本轮提交时 git 打出了这条警告：

```
warning: in the working copy of 'src/DX12SwapChain.cpp', LF will be replaced by CRLF
         the next time Git touches it
```

查证：`git config core.autocrlf` = **true**，仓库里**没有 `.gitattributes`**。

```
$ git ls-files --eol src/*.cpp
i/lf   w/lf     src/DX12SwapChain.cpp    <- 工作区 LF（对），index 里也是 LF
i/lf   w/crlf   src/ImguiMenu.cpp        <- 工作区 CRLF（对），index 里却是 LF
i/lf   w/crlf   src/Streamline.cpp
$ git show HEAD:src/DX12SwapChain.cpp | byte counts -> CRLF=0 LF=2254
$ git show HEAD:src/ImguiMenu.cpp     | byte counts -> CRLF=0 LF=533
```

**读法**：`autocrlf=true` 在 **add 时把工作区的 CRLF 规范化成 LF 存进 index**，
在 **checkout 时再把 LF 还原成 CRLF**。于是同一份配置对两个文件的效果正好相反：

- `src/ImguiMenu.cpp`（工作区 CRLF、index LF）：checkout 后**仍是 CRLF** ⇒ **侥幸**符合铁律。
- `src/DX12SwapChain.cpp`（工作区 LF、index LF）：checkout 后变成 **CRLF** ⇒ **违反铁律**。

⇒ **一条 `git restore src/DX12SwapChain.cpp` 就能把 LF 文件变成 CRLF，而且事后用 grep 看语法
没有任何异常**。它至今没被触发，只是因为本工程**一直只 commit、从不 checkout**。

**处置（本轮只记录，不改任何配置）**：

| 方案 | 后果 | 结论 |
|---|---|---|
| `git config core.autocrlf false` | `ImguiMenu.cpp` / `Streamline.cpp` 下次 checkout 会变 **LF**（**反向破坏**） | 否决 |
| 新增 `.gitattributes`（`text eol=...`） | index 里全部文件按新规则规范化 ⇒ **一次性巨大 diff**，污染全部历史对比 | 否决 |
| `*.cpp -text` | index 从 LF 改成 CRLF ⇒ 同样是一次性全文件 diff | 否决 |
| **只记录 + 加硬性规则** | 零风险 | **采用** |

⇒ 新增硬性规则（与行尾铁律同级）：

> **永远不要对本工程做 `git checkout` / `git restore` / `git stash pop` 之类会写回工作区的操作。**
> 若万不得已做了，**事后立刻**跑 `python tools/eol_census.py <四个文件>` 复查，因为 git 会静默改行尾。

（**L59**：**"只 commit 不 checkout"是一个没写在规则里的前提。** 一个工程能长期遵守行尾铁律，
可能不是因为铁律被守住了，而是因为**那条会破坏它的命令从来没被用过**。
凡是"一直以来都对"的东西，都要问一句：**它靠什么维持**。）
# 第 42 章：12:26 局是第二次「世界活了」；「21 秒零 Present」原来早有答案；而我两个「边沿」检测器其实是撕裂的（v1.29）

**局：2026-09-20 12:26:56 - 12:29:35（跑 v1.28，DLL md5 `4184e1c898c1a188a3899358857d7194`）**
归档 `docs/runlogs/2026-09-20-1226-v128-tbd.*`（5 件）。

## 一、先把时间线钉死（每一条都有时间戳）

| 时刻 | 事件 | 证据 |
|---|---|---|
| 12:26:56.508 | SKSE 加载 DLL | log 头 |
| 12:27:08.5 | swapchain / interop ready | `D3D12 FG swapchain created` |
| 12:27:08.6 | 最后一次进入我方 Present（本段共 1 次） | `frames=1` |
| 12:27:08.6 -> 12:27:30.0 | **21.4 秒无 Present** | `dt max=21426.80ms`（见第二节） |
| 12:27:30.003 | `MENU EDGE open=1 serial=2`；PIXEL 开始采样；frames 从 1 跳到 135 | watchdog 12:27:32.775 |
| 12:27:30 -> 12:29:30 | **加载屏 2 分钟**，2x，4822 帧，全程无停顿 | `at 2x` x 4822 |
| 12:29:30.928 | `MENU EDGE open=0 serial=4822` 闸门释放 | 同毫秒 `Applied fixed multiplier: 4x (eOk)` |
| 12:29:31.133 | **`DLSSG presented per real frame = 4`** | Transfusion + 我方双份 |
| 12:29:31.163 | `[OVERLAY] world clock started` | v1.28 新加的覆盖层计时 |
| 12:29:32.598 | `FLIPS per real frame = 3.03` | DXGI 自己的计数 |
| 12:29:34.609 | **`FLIPS per real frame = 4.00`** | DXGI `lastPresentCount 5021->5297` vs 我方 Present `4878->4947` |
| **12:29:34.991** | **全部日志在此瞬间停止** | 5 份日志最后一行都落在 12:29:34.9~35.0 |

**世界段 = 12:29:30.928 -> 12:29:34.991 约 4.06 秒；其中 4x 真正生效 = 12:29:31.133 -> 12:29:34.991 约 3.86 秒。**

**结论：这一段的仪器读数全部正常** —— `hrsD=0.0056`（游戏时钟在走）、`paused=0 ld=0 fade=0`、
`read=553 match=518`、watchdog `silent` 全程 1~30 ms、DXGI 137 翻转/秒。
**没有任何一处显示卡死。** 日志**瞬间**停止且没有任何 shutdown/dtor 行 ⇒ **进程是被强制结束的**。

## 二、「21 秒零 Present」不是谜 —— 答案在第 719 行，我自己写的

watchdog 的 warm 判据注释（`src/DX12SwapChain.cpp:719-722`，v0.63 写的原文）：

> 21:54 那次运行在约 20s 装载里 frames 恒为 1、stage 恒为 "d3d11 Wait"，看门狗连打 19 行
> RENDER THREAD STALLED —— 全是假警报。判据收紧：渲染线程必须「曾经跑顺过」（frames>=60）
> 才允许报卡死，未达标只记 silent（装载期的正常表现）。

⇒ **装载期 `frames=1` + `stage="d3d11 Wait"` 是已知的正常现象**，并且当时就已经处理了
（`warm = frames >= 60`）。

本轮新拿到的那条硬证据，第一次把这个现象**量化**：

```
[XRAY] ... dt min/avg/max=17.74/29.53/21426.80ms n=4823
```

**一帧耗时 21426.80 ms。** 不是「20 秒没进 Present」，是「有一帧真的跑了 21.4 秒」。

⇒ 第 40 章把这段写成「未解之谜 / 唯一硬读数是 DXGI 零翻转」是**过头了**。
零翻转只说明「我们的 FG swapchain 还没被用上」（装载期游戏走原生 D3D11 swapchain），
不是「引擎卡住」。而且 **`frames` 从 1 跳到 135 发生在 `MENU EDGE open=1` 的同一秒**，
说明链路是**跟着菜单打开的**，不是自己恢复的。

**下次不要再花一局去查这件事。**

## 三、12:26 局与 03:17 局（第一次活的世界）逐字段相同

| 量 | 03:17（v1.27） | 12:26（v1.28） |
|---|---|---|
| `[CAM] PC` read/match/adopt | 512 / 480 / 1:1 | 553 / 518 / 0:3 |
| `eye` | (-243.05,-415.31,118.56) | **同一个坐标** |
| `proj00` | 0.8391 | 0.8391 |
| `paused= / ld= / fade=` | 0/0/1 | 0/0/0 |
| `hrsD` | 0.0056 | 0.0056 |
| `FLIPS per real frame` | **4.00** | **4.00** |
| 世界段 PIXEL shape | `sw=7 maxRun=1`（每样本都不同） | `sw=7 maxRun=1` |
| 世界段长度 | 5.7 s | **4.1 s** |
| `os=` | `0x0` | `0x0` |

⇒ **两局在仪器上无法区分。「世界活了 / 4x 生效」已经复现两次，不是侥幸。**

## 四、v1.29 修的：两个「边沿」检测器其实是撕裂的

### 4.1 `Reflex cap check` 在一个加载屏上打了 4823 行，而它的值一次都没变

```
[Streamline] Reflex cap check (v1.12): 159 flip fps on a 160Hz panel = 79.5 rendered fps at 2x
```

**这一行打了 4822 次，每一次的数值都字面相同**（加载屏全程 2x / 159）。

判据在 `src/Streamline.cpp:2410`：

```cpp
static std::uint32_t lastCapFps = 0;
static std::uint32_t lastCapMult = 0;
if (capFps != lastCapFps || capMult != lastCapMult) { ... log ...; lastCapFps = capFps; lastCapMult = capMult; }
```

**两个 plain static + 两个线程**（本插件 Present 路径两个 tid 都走；Transfusion 自己的 trace
也显示两个 tid 到达姊妹调用）。**两个字宽的写不是原子的**：一个线程写 `lastCapFps` 的
同时另一个读 `lastCapMult`，两边都「看到变化」⇒ **边沿检测器退化成每帧触发**。

**修法**：`(capFps << 4) | (capMult & 0xF)` 打包成一个 `std::atomic<uint32_t>`，
用 `exchange` 比较 —— **一次真边沿只有一个线程能拿到旧值**。

### 4.2 `Reflex options applied` 打了 4896 行，而这次它决定的是「要不要调用」

```cpp
static sl::ReflexOptions lastOpts{};
static bool lastValid = false;
if (!lastValid || std::memcmp(&lastOpts, &opts, sizeof(opts)) != 0) { slReflexSetOptions(opts); ... }
```

**同一个撕裂缺陷，但严重一档：这个判据决定 `slReflexSetOptions` 是否被调用**，
所以它让运行时**每帧被重新配置一次**，全程（加载屏 + 世界）都是。

打印出来的三个字段 `mode=1 frameLimitUs=6289 markers=true` 同样**从未变过**。

**修法**：只比较这个函数真正设置的三个字段（已 grep 确认 `opts` 只有这三处赋值：
`mode` / `frameLimitUs` / `useMarkersToOptimize`），打包成 `std::atomic<uint64_t>`，`exchange` 比较。

**这不是改变设计，是恢复设计** —— 原注释（v0.35）写的就是「选项变化才 slReflexSetOptions
（缓存比较，CS 同款）」。**缓存比较从未生效过。**

## 五、v1.29 修的仪器：输入见证只能证明「不是那八个键」

`src/FrameGen.cpp:1583-1590` 的输入见证扫八个键：`W A S D Space Shift LMB RMB`。

**16 局连续打出 `os=0x0`，而每一局都被读成「用户没碰过键盘」。**

**但那个掩码只能证明否定命题「不是那八个键」。** 一个觉得画面卡死的玩家，
**最先按的是 ESC 或 Alt+F4 —— 两个都不在掩码里。** 于是「不是这八个」被静默升级成
「完全没有输入」，而整个输入见证的结论就架在这个越界推论上。

**修法**：每秒扫全 `vk 1..255`（255 次 `GetAsyncKeyState` 相对 4K 帧是免费的），
`kb=` 打印当前按住的键数，并在**任何键变化**时打一条 `[INPUT] vk 0x.. -> 0x.. (N held, fg=1)`。

**已写明的局限**：这是 1 Hz 采样，**两次采样之间按一下就松开的键会被漏掉**。
协议要求的「按住 W 十秒」漏不掉。

## 六、v1.29 加的仪器：屏幕上到底有没有新帧

`frames=` 数的是**我们的** Present 进入次数，`lastPr=` 数的是**我们的** swapchain 翻转次数 ——
**两个都在我们这一侧。** 12:26 局两者都在涨（2.86 秒里 98 次进入、392 次翻转 = 137 翻转/秒 = 正好 4x），
而用户说画面是卡死的。

⇒ 加两条：

1. `[XRAY] 4x SNAPSHOT t=0` —— 倍数落到 4x 的那一 tick（判据 `frames>200 && lastPr>frames*3`，
   登录界面 `lastPr≈2*frames` 达不到，不会误触），随后 3 秒内每 5 tick 一条 `4x probe`，
   带**实测面板翻转率**。**这段时间正是用户唯一在报告的窗口** —— 最近 6 局每一局都在
   世界时间 6 秒内结束，所以「一分钟才打一次」的速率等于从未被看到过。
2. `[XRAY] FLIP COUNTER FROZEN for N ticks` —— `lastPr` 连续 5 tick 不涨而 `frames` 仍在涨。

## 七、方法论

**L60（本轮最有用）**：**一行日志如果把自己的值一起打出来，那么当它带着同样的值重复时，
它就自我否证了 —— 坏的是判据，不是值。** 这次两个「边沿」检测器都是这样被抓出来的：
4823 行 `at 2x`、4896 行 `mode=1 frameLimitUs=6289`。
**下次看到一个「变化才打」的日志在刷屏，第一件事是把它打印的值读出来，而不是去查它测的东西。**

**L61（本轮最贵）**：**判据的推论范围不能超出它测量的范围。**
`os` 测的是八个键，结论却是「没有任何输入」。**16 局都架在这个越界推论上。**
修法不是「多测几个键」，而是**把能测的全测**（255 个 VK），因为**你不知道用户会按哪个键**。

**L62**：**「已知的正常现象」会被自己重新发现成「未解之谜」。**
第 40 章把装载期 21 秒写成「未证」，而这个现象的说明就写在同一工程第 719 行的注释里，
连处理方式（`warm = frames >= 60`）都已经实现了。**查未证清单之前，先搜一遍源码里
有没有人已经回答过。**

## 八、仍未证（不许假装已修）

- **v1.29 一局都没跑过。** 上面四条改动**全部只有静态验证**（构建 + 二进制串 + 行尾），
  没有任何运行读数。`kb=` / `[INPUT]` / `4x SNAPSHOT` / `FLIP COUNTER FROZEN`
  **四个新读数一个都没出现过。**
- **「4x 导致卡死」仍未证，而且这一局是反证**：4x 生效后的 3.86 秒里，
  DXGI 实测 137 翻转/秒、silent <= 30 ms、画面每 500 ms 完全不同。
  只有在 2x 对照局（`MFGMaxFramesOverride=0`）也复现同样现象之后，才能说 4x 无关；
  **这个对照局一次都没跑过。**
- **用户看到的画面内容 —— 仍然没有任何仪器覆盖。** PIXEL 读的是我们的
  `colorOut(presented)`，不是屏幕。两台仪器都在栅栏的这一侧。
- **Transfusion 隔离实验**（`DINPUT8.dll` -> `DINPUT8.dll.transfusion-off`）**一次都没跑**。
# 第 43 章：不是崩溃，是被终止 —— 而「屏幕上是什么」终于有了仪器（v1.30）

局：2026-09-20 13:12:00 -> 13:12:46.86，跑 v1.29（首跑）。归档
`docs/runlogs/2026-09-20-1312-v129-terminated-not-crashed-4x-lived-2-seconds.*`。
本局 46 秒，世界段 2.0 秒 —— 但这一次，「2 秒」不再是一个含糊的说法。

## 43.1 先把用户的话对齐到毫秒

用户原话：「还是卡在游戏刚进去两秒，只要开始四倍帧生成，就卡死。」

Transfusion 侧（`DLSSG-Transfusion.log`）：

- `13:12:44.551 [OPTIONS] Game DLSS-G options: ... frames=3`
- `13:12:44.551 Option C active: stripped eEnableFullscreenMenuDetection ...`
- `13:12:44.551 Applied fixed multiplier: 4x, result=0 (eOk)`
- `13:12:44.747 DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)`
- `13:12:45.454 [PERF] 4x | Kernel: Ada | FPS: 33.3 (30.08ms) | Jitter: 7.87ms | 1% Low: 32.2`

我方 `[XRAY] MENU EDGE open=0 serial=631`（世界入口）= `13:12:44.551`，
即 **4x 生效与世界入口是同一毫秒**。我方日志最后一行 `13:12:46.855`，
watchdog 最后一行 `13:12:46.759`。

把 watchdog 末尾两个计数拿出来除：

| 时刻 | frames（我方 Present 入口） | lastPr（DXGI 自己的计数） |
|---|---|---|
| 13:12:44.931 | 643 | 658 |
| 13:12:46.759 | 705 | 906 |
| 差值 | **+62** | **+248** |

248 / 62 = **4.00**。**4x 第三次被实测到，而且是精确的 4.00。**

分钟级别的主日志最后一条 `FLIPS per real frame = 3.57` —— 那个窗口
（13:12:44.508 -> 46.526）**跨在 4x 生效的前后**，所以被 1x 的部分稀释了。
这是把「速率」用「窗口」去量时的必然误差，不是异常。

进程消失的时刻 = 4x 生效 **2.21 秒**之后。用户说的「刚进去两秒」，
与日志逐字段吻合。

## 43.2 这一局不是崩溃 —— 两条独立证据

**证据一（WER / 事件日志）**：`Get-WinEvent` 查 13:10-13:20 的 Application 日志，
没有任何 Application Error / AppHang 事件。WER 的 `ReportArchive` 里
`AppCrash_SkyrimSE.exe` 有三份，**全部是 9 月 18 日的**，9 月 20 日零份。
这个目录对 SkyrimSE.exe 是有效的（否则不会有那三份）。

**证据二（Crash Logger SSE）**：`Documents\My Games\Skyrim Special Edition\SKSE\crash-*.log`
共 20 个（`Max Crash Logs = 20`，旧的已被轮转掉），最后五个是
`09-18 16:04 / 18:23 / 19:04 / 19:16 / 19:34`。
**9 月 19 日和 9 月 20 日一个都没有。**

⇒ 两天里所有「卡死」，游戏**一次都没崩**。进程是被**终止**的
（`TerminateProcess` 不留 WER 报告、不留 crash log、不调用任何析构）。

## 43.3 那不是卡死 —— 但也不是「正常」

watchdog 最后一行：

```
[43243629] 13:12:46.759 frames=705 silent=5ms stage=d3d11 Wait focus=1 fence=1401/1401
           stim=179 queued=1 lastPr=906 dsync=0 msg=1 alive=1 presentAge=-12ms cpuD=156ms
```

`silent=5ms` —— 渲染线程在进程消失前 5 毫秒还在正常跑。全程 `silent`
2~27 ms、`presentAge` ±27 ms、`fence` 两侧相等、`msg=1 alive=1`。
**没有任何一行读数像「卡住」。**

`presentAge` 的负值（-4 / -16 / -12 ms）是**看门狗自己的测量伪影**：
`nowMs` 在循环顶部取一次，而 `SendMessageTimeoutA(..., 200ms)` 在写这一行
之前跑，最长 200 ms ⇒ `nowMs` 相对 `g_presentEnteredMs` 是过期的。
**名字叫 age，参考点却是旧的。** 记下来，别再当异常读。

`stage=d3d11 Wait` 仍然是「最后写下的名字」，不是「当前调用」。

## 43.4 v1.29 的四台仪器：两台按构造就不可能触发

**这是本轮最该记住的技术教训。**

v1.29 加的 `4x SNAPSHOT` / `4x probe` / `FLIP COUNTER FROZEN`，前提条件是：

```cpp
const bool warm4x = frames > 200ull && lastPr > frames * 3ull;
```

这是**累积比**。而 `lastPr` 只有在 4x 活着的时候才会跑到 `frames` 前面，
所以「累积比 > 3」等价于要求「4x 已经活了整个会话的大部分时间」。
本局末态 `lastPr=906` / `frames=705`，测试要 `lastPr > 2115` ——
**它要的那 2115 次翻转，在这个 2 秒的窗口里根本不存在。**

四个读数一个都没出现，**四个零全是仪器，不是现象**。

修法：把定义改回它本来该有的样子 —— **速率**。
`dFlips / dFrames >= 3` 在最近 200 ms 的切片上（34 次入口/秒 ⇒ 切片内约 7 帧，
取 >=3 是保守的，且装载期比值是 1.00，不可能误触发）。
`FLIP COUNTER FROZEN` 顺便**去掉对 live4x 的依赖**：
它要问的是「我方 Present 在跑而翻转计数没动」，一个要求「4x 必须活着」的
前置条件，恰好会藏住「4x 被请求了但没到」这一种情况。

**L66（本轮）：一个仪器如果要求「我要测的那个现象已经成立」才启动，
那它就永远测不到那个现象。**

## 43.5 第三条误报：0.9/255 的抖动不算「回来了」

v1.28 的回访判据（`revisits >= 1`）本局触发 **4 次**，窗口逐字：

```
shape=[0 0 1 1 1 1 2 1]   亮度 0.0 / 0.0 / 104.0 x4 / 104.9 / 104.0
```

这是**加载屏由黑转亮的一次单向渐变**，加上**一个比邻居亮 0.9/255 的样本**。
`revisits` 数的是折叠序列里所有非相邻的相等对：一次真实的
A,B,A,B,A,B,A,B 得 12，而单个毛刺得 1。所以门槛抬到 **2** 即可分开，
且不动真正需要的灵敏度。

**★ 这是同一个探针的第三次误报**（v1.26 一次、v1.27 一次、v1.28 一次），
而**它一次真阳性都没有过**。它读的是 `colorOut` —— 交给 DLSS-G 的**输入**，
所以它从原理上看不见插帧之后的画面。它的正当用途只剩「我方这一侧有没有动」。

## 43.6 盲点有了准确的名字，而且比之前说的更大

本工程（v1.30 之前）拥有的每一个读数，都在栅栏的**我们这一侧**：

| 读数 | 它到底测什么 |
|---|---|
| `frames=` | 我们自己的 Present 被进入了多少次 |
| `lastPr=` | 我们自己的 swapchain 翻转了多少次 |
| `[PIXEL]` | 我们交给 DLSS-G 的 D3D11 纹理（**输入**）的哈希 |
| `cpuD=` | 我们整个进程的 CPU 时间 |
| `silent=` / `presentAge=` | 我们自己函数调用之间的间隔 |

**没有任何一个读屏幕。** 而且 `lastPr` 上涨**连「面板动了」都证明不了**：
FLIP 模型下有翻转队列，Present 可以在任何东西扫出之前就返回。

⇒ 「DXGI 报 137 翻转/秒」从来不是「画面在动」的证据。
这条我上一轮说得比实际强，纠正。

**所以 v1.30 加了屏幕探针**：在 watchdog 线程里每秒一次
`GetDC(NULL)` + `StretchBlt` 到 64x64 DIB（`HALFTONE`，最近邻会在 4K->64
的降采样里只采到 1/60 的像素，可能整片漏掉真实变化），算哈希与平均亮度，
并与**我们自己 `colorOut` 的哈希**并排保存；窗口按**写序**读（v1.28 在
环形缓冲上犯过这个错）。

判据只有一条，而且是这个工程里第一条关于**屏幕**而不是关于**我们**的判据：

```
窗口内 sDistinct <= 1 && pDistinct >= 3   ->  [SCREEN] STALE
```

屏幕 8 秒只有一张图，而我们自己的 `colorOut` 取过 3 个以上的值。

两条自证：捕获创建失败打 `[SCREEN] ERROR`；连续十次全黑打 `[SCREEN] BLIND`
（独占全屏会让桌面捕获什么都看不到，而**沉默会被读成健康**）。

**★ 顺带排除一条假设（不需要跑一局）**：`DX12SwapChain.cpp:206/241` 里
`CreateSwapChainForHwnd(commandQueue.get(), a_swapChainDesc.OutputWindow, ...)`
用的是**游戏自己的窗口**，所以「FG swapchain 建在一个隐形窗口上」不成立。

## 43.7 输入见证：换一个问法

本局 16 行 `[CAM] PC` 全是 `kb=0`（255 个 VK 全扫），
而同一行的 `dc=`（鼠标位移/事件数）读到 `2006/1`、`2155/1`、`2132/1`。
⇒ 鼠标到了，键盘没有。

但「255 个键此刻都没按下」和「用户什么都没做」仍然是两句不同的话，
而且 1 Hz 采样本身有 1 秒的洞。

v1.30 加 `GetLastInputInfo`（`ai=<距上次输入 ms>`）：
它问的是「这个会话里有没有任何输入」，**与是哪个键无关** ——
这正是 L61 要的答案。它返回时间戳而不是状态，所以 1 Hz 够用。

## 43.8 v1.30 改动清单（不碰帧生成路径）

`tools/patch_v130_the_screen_and_the_dead_4x_test.py`，7 个锚点各 `count==1`：

1. `[SCREEN]` 探针（上述）——新增。
2. `live4x` 改速率定义；`FLIP COUNTER FROZEN` 去掉 live4x 前提。
3. 闪烁门槛 `revisits >= 1u` -> `>= 2u`。
4. `ai=`（`GetLastInputInfo`）+ `[INPUT] system input ... ms ago`。

另有两处读数窗口收紧（`Edit` 工具，逐符号回读 + 行尾复查）：

5. `DLSSG diag` 每 120 次 -> **每 20 次**。旧节奏在 34 入口/秒下是 3.5 秒，
   而 13:12 局 4x 只活了 2.2 秒 —— **下一个读数排在进程已经死掉之后**。
6. `[MFG] debug CHECK` 每 600 帧 -> **每 120 帧**（同上理由）。

**这两条本身就是 L47 的一个新例子：为装载屏选的节奏，在用户真正报告的那个
窗口里等于零。**

## 43.9 第一遍（手脚）

- 7 个锚点干跑全 `count==1`；`--apply` 后 post-check：新串在、旧串（
  `revisits >= 1u` / `lastPr > frames * 3ull` / `warm4x`）计数为 **0**。
- 行尾：`src/DX12SwapChain.cpp` **CRLF=0 CR=0**（纯 LF）；
  `src/FrameGen.cpp` **CRLF==LF==CR**（纯 CRLF）。`Edit` 工具两次改动后复查，未被转成 CRLF。
- 构建 `BUILD SUCCESS`，0 error 0 warning。
- DLL **1,389,056 B** md5 `40704c8cc78466a77884ccee3f9f4414`，**build == MO2 部署目录**。
- 二进制内新串 4/4 在（`ai={}` / `[SCREEN] STALE over` / `live4x: +%llu flips` /
  `system input {} ms ago`）。
- INI **未动**：`efce89119d840670e519d219749a6476`，20658 B，358 行 CRLF，源树 == 部署。

## 43.10 第二遍（脑子）

- **反向假设**：如果那两条「边沿」日志的值真的变了，日志文本会不同 ——
  本局 `Reflex cap check` 709 行里 **631 行是 `at 2x`、78 行是 `at 4x`**，
  也就是说这一行的值是**跟着倍数在切的**（它本来就是每帧行，不是边沿行）；
  而 `Reflex options applied` 从 4896 行掉到 **1 行**、`Reflex FLIP cap` 只打 **2 行**
  （正好在 2x->4x 那一个边沿）。
  ⇒ **v1.29 对 `slReflexSetOptions` 那个门做的原子修复生效了**，
  这是本轮唯一一处「上一版的修复被本局证实」。
- **A ≠ B**：`revisits >= 1` 与 `>= 2` 在同一段日志上判据相反（1 vs 1）——
  实测对照，不是推理。
- **这条路径真会走到吗**：`[SCREEN]` 挂在 watchdog 的 `(tick % 5) == 3` 上，
  与 `SendMessageTimeoutA` 的 `(tick % 5) == 0` **错开**，避免两件慢事叠在同一次。
- **空集不能当健康**：`[SCREEN] ERROR` / `[SCREEN] BLIND` 就是为这一条写的。
- **用户会不会白跑**：**会** —— 而这是本轮唯一没能解决的问题。
  屏幕探针要求世界段足够长（8 秒窗口才出 STALE），而最近 8 局的
  世界段是 2.1 / 3.0 / 3.2 / 2.5 / 6.1 / 5.7 / 4.1 / **2.0** 秒。

## 43.11 未证 / 下一步

- **屏幕上到底是什么 —— 仍然未证**，但从 v1.30 起有仪器了。
  首跑按「校准」读（L53）：先确认 `[SCREEN]` 每秒在打、`distinct` 不是恒为 1、
  不是连续十次全黑。
- **「4x 导致卡死」仍未证**。而且现在多了一条更强的说明：
  **4x 之后进程是被终止的，不是崩的，日志里没有任何一行像卡死。**
  2x 对照局（`MFGMaxFramesOverride=0`）**仍然一次都没跑过**。
- **Transfusion 隔离实验**（`DINPUT8.dll` -> `DINPUT8.dll.transfusion-off`，
  **绝不能用 `.disabled`**）**仍然一次都没跑过**。
- **`[MFG] debug CHECK` 在本局报了 `dlssgOk=0`**，落在解除守卫后的**第一帧**；
  下一帧起是否恢复，旧节奏（600 帧）让它排在进程死亡之后 ⇒ 本局**读不到**。
  v1.30 收紧到 120 帧。


# 第 44 章 13:26 局（v1.30 首跑）：4x 真的上台了，然后游戏丢失了焦点

## 44.1 这一局推翻了本章之前所有关于「进程被终止」的推论方向

本局 13:25:16 启动，13:25:48 进主菜单，13:26:37.5 按回车（读档/新游戏），
13:26:45.052 `MENU EDGE open=0`（进世界），13:26:46.6 全部日志停止 —— 世界段 1.5 秒。
再一次「刚进去两秒」。

但本局第一次同时拿到了三条此前从未同框的证据：

1. **4x 确实在跑，而且是在呈现的。**
   `[MFG] probe edge: menu guard released, SetDLSSGOptions resumes on this frame.
   step advertised=4x accepted=4x latched=1`
   `[Streamline] MFG probe: runtime ACCEPTED 4x (3 interpolated frames) | runtimeReportsMax=6x`
   `[Streamline] DLSSG presented per real frame = 4 (status=0)`
   `[CAM] PC` 世界段 `mult(acc/pres)=4/4`
   `[XRAY] serial=2427 ... presented all=0/12/0/0/54/0/0/0 world=0/12/0/0/54/0/0/0`
   ⇒ 世界段 66 帧里有 **54 帧是在 4x 槽上呈现的**。
   `[XRAY] 4x SNAPSHOT t=0 frames=2406 lastPr=2418 (live4x: +19 flips for +6 Present entries)`
   `[XRAY] 4x probe +446ms frames=2422 lastPr=2482 panel=139 flips/s live4x=1`
   ⇒ **v1.30 修掉的那个「按构造不可能触发」的累积比判据，首跑就触发了。**
   Transfusion 独立佐证：`DLSS-G actual presentation count: 4x (maximum generated frames=5)`、
   `[PERF] 4x | Kernel: Ada | FPS: 34.4`。

2. **`[SCREEN]` 活了，74 个采样。** 但它的判据是错的（见 44.3）。

3. **死亡前 0.95 秒有一次 LeftAlt，死亡那一刻游戏「丢失焦点」。**
   `[13:26:45.648] [INPUT] vk 0x00 -> 0xA4 (2 held, fg=1)`
   `[13:26:46.590] [DMK] WM_ACTIVATEAPP: Game lost focus. Clearing inputs.`（DirectionalMovement）

## 44.2 「不是崩溃」现在有三条互相独立的证据（此前两条）

| 来源 | 9/18 | 9/19 | 9/20 |
|---|---|---|---|
| WER `AppCrash_SkyrimSE.exe` | 3 份 | 0 | 0 |
| Crash Logger `SKSE/crash-*.log` | 最后 5 份全是 | 0 | 0 |
| **`%LOCALAPPDATA%\CrashDumps\SkyrimSE.exe.*.dmp`**（本章新增） | 3 份 18:23/19:04/19:16 | 0 | 0 |
| **System 日志 `nvlddmkm` 错误（TDR）**（本章新增） | — | — | **最近一次是 9/15** |
| Application 日志 1000/1002 | — | — | 13:10–13:35 **零条** |

⇒ 两天里所有「卡死」，游戏**一次都没崩、一次都没 TDR**。
新查询方式（`wevtutil`，PowerShell 在本机对这些查询静默返回空，已弃用）：
`wevtutil qe System /q:"*[System[Provider[@Name='nvlddmkm']]]" /c:10 /rd:true /f:text`

## 44.3 我的 `[SCREEN]` 判据是错的 —— 用 `distinct` 数「屏幕有没有变」在原理上不成立

本局 74 个采样，**每一个**都是 `distinct=8/8`：加载淡出时 8/8、菜单里 8/8、世界里 8/8。
原因：`distinct` 数的是**8 个环样本里有几个不同的哈希**，而一个横跨任何转变的环，
按构造就是 8 个不同哈希。它实际上在回答「最近八秒里发生过任何事吗」，
而不是「屏幕有没有变」。真正重要的两个采样是：

```
[44082295] [SCREEN] #73 hash=899CCF386BE74EC8 lum=100.93 distinct=8/8 ours=A4110C0648902D2C ourDistinct=5
[44083350] [SCREEN] #74 hash=C0A1CFCA8D01D28C lum=100.93 distinct=8/8 ours=EDCD53D17F0537A5 ourDistinct=6
```

**lum 一模一样（100.93），哈希不同。** 这既可能是「画面在动」，也可能是
「世界冻了、只有左上角 FPS 覆盖层在跳」—— 一个哈希分不出来。**这正是判据必须换成
连续样本同一性 + 亮度差幅度的原因。**（L60：一行日志把自己的值一起打出来时，
它带着同样的值重复就自我否证了。）

另一半：`[SCREEN] STALE` 要求 `sDistinct<=1`，而 `sDistinct` 永远到不了 1 ⇒
**这条判据在世界上一次都不可能触发。** 第四个「按构造不可能触发」的仪器。

## 44.4 `[INPUT]` 的「(2 held)」是我自己的扫描在重复计数同一次按键

`GetAsyncKeyState` 对**同一个物理 Alt** 会同时报告 `VK_MENU (0x12)` 和
`VK_LMENU (0xA4)`。Shift（0x10/0xA0/0xA1）、Ctrl（0x11/0xA2/0xA3）同理。
⇒ 打印 `2 held` 时，实际可能只有 **一个** 键。
而「第二个键在不在」恰恰决定这一局是 **ALT+F4 退出** 还是 **ALT 单独按下**。
这又是一个 L61：判据的推论范围超出了它测量的范围。

## 44.5 另一条被忽略的读数：`hrsD` 在走，`eyeD=0.00`，`paused=0`

`[13:26:45.648] [CAM] PC v1.19: read=592 match=555 adopt=2/3 ... paused=0 ld=0 fade=0
hrs=12.32800 hrsD=0.005469 ... PC_STILL INPUT_SEEN - input reached the game, so a still
eyeD here is a frozen world`

**`INPUT_SEEN` 是错的**：这一局唯一的键是 LeftAlt，它不能移动角色。
画面「冻住」和「玩家没动」在这里又混成了一句 —— 而 `fade=0` 说明淡入刚好在这一刻结束。

## 44.6 v1.31 改了什么（`patch_v131_the_picture_and_the_hand.py`，16 锚点 count==1）

**不碰帧生成路径。**

1. **★ 屏幕存成图片。** 每次采样写一个 640×360 24-bit BMP 到
   `<我的文档>\My Games\Skyrim Special Edition\SKSE\DFG_screens\screen_NNN.bmp`，
   环形 96 个文件（自覆盖，不无限增长），日志行带上文件名。
   理由：哈希回答「变了没有」，回答不了「变出来的是不是游戏」—— 而后者已经花掉四天。
   **一张没人找得到的图等于没有图（L58），所以文件名必须进日志。**
2. **判据换成连续样本同一性。** 行上新增 `same=`（与上一张**逐字节相同**的连续次数）、
   `oursSame=`（我们自己 colorOut 的同项）、`dLum=`（亮度差幅度）。
   `same>=7 && oursSame<=1` ⇒ `[SCREEN] STALE`；`same>=3 && oursSame<=1` ⇒
   **`[SCREEN] FROZEN`（本项目第一条能看见用户从 15 号起就在描述的那个故障的判据）**。
   为什么 `oursSame` 是必须的：菜单里我们的 colorOut 哈希会连续重复十几次
   （`1C6B76BA62059E4D` 在 13:25:48–13:26:44 之间出现 11 次），没有它就会在菜单里误报。
3. **采样节奏 1 Hz → 有 4x 时 2.5 Hz**（`(frames>60 && lastPr>frames+8)` 时 `tick%2==0`）。
   最近八局世界段 2.0/2.1/2.5/3.0/3.2/4.1/5.7/6.1 秒 ⇒ 1 Hz 只有 2~6 张。`same>=3` 需要至少 3 张。
4. **flush 提到捕获之前。** 原来一 tick 的行全部先写、`fflush` 在循环末尾，
   而 GDI blit 是这个循环里唯一会阻塞的调用 —— **一次阻塞的 blit 会静默吃掉整个 tick 的读数。**
   本局本文件最后一行在游戏丢焦点前 110 ms，下一个 tick 从未到达，正是这个形状。
5. **`PollHomeKey` 里加逐帧（~35 Hz）按键组合检测**：展开别名、打印真实键集、
   点名 `ALT+F4 (quit)` / `ALT+TAB (unfocus)` / `ALT+ENTER` / `ALT+ESC` / `CTRL+ESC` / `F4`。
   理由：**「进程被杀」和「玩家自己退出」是两个不同的结论，只有一个是我们的 bug。**
6. **`INPUT_SEEN` 判据收窄成 `INPUT_MOVE_SEEN`**（必须有能移动角色的键，或鼠标动过），
   否则 `INPUT_NONMOVE` —— 不再拿 Alt 当「世界没响应」的证据。

**验证**：16 锚点 count==1｜构建 0 error（第一次编译失败：补丁脚本里 `\n` 写成 `\n` 前少了一层转义，
字符串常量里进了真换行，已修）｜DLL **1,394,176 B · `e02600bb0c5d94226df78d84acf6dec6`**，
**build == MO2 部署**｜11 个新串在、2 个旧串消失｜INI 未动（`efce8911…`，358 行 CRLF，双份一致）｜
行尾 DX 纯 LF / FG 纯 CRLF。

## 44.7 下一局要读的四件事

| 看到 | 结论 |
|---|---|
| `[INPUT] *** ALT+F4 (quit) ***` 且键集含 `73` | **这一局是用户自己退的** —— 「进程被终止」从此有主语 |
| `[INPUT] *** ALT+TAB (unfocus) ***` | 游戏被切到后台，Skyrim 会停渲染 ⇒ **「卡死」可能是切出去造成的** |
| 键集只有 `[12 A4]`（Alt 单独） | 焦点丢失不是 Alt 干的 ⇒ 继续查外部 |
| `[SCREEN] FROZEN for N captures` | **★ 四天来第一次真正量到用户说的冻结**，且有图可看 |
| `DFG_screens\screen_*.bmp` | 直接看图：黑 / 冻 / 撕裂 / 重影，一眼可见 |

## 44.8 仍未证（不许假装）

- **「4x 导致卡死」仍未证**，而且本局是**反证**：4x 上台后 panel 139 flips/s、real 34.4 fps、
  `hrsD` 在走、`paused=0`，日志里没有任何一行像卡死。
- **2x 对照局（`MFGMaxFramesOverride=0`）仍然一次都没跑过** —— 四天里最大的方法论缺口。
- **那 1.5~2 秒之后到底发生了什么仍未证**：本局只有「丢焦点」+「Alt 按下」两个读数，
  谁先谁后、是否有第二个键，都要等 v1.31 的逐帧键集。
- **Transfusion 隔离实验**（`DINPUT8.dll` -> `DINPUT8.dll.transfusion-off`，**不能用 `.disabled`**）
  仍然一次都没跑过。
- `WriteScreenBmp` 与 `s_scrSame`/`FROZEN` **一局都没跑过** ⇒ 首跑按「校准」读（L53）。

## 44.9 补记（v1.31 归档时回读到、44.8 漏掉的一条读数）

`[MFG] debug CHECK` 本局（13:26）**全日志只有 1 行**，就在世界入口那一毫秒：

```
[13:26:45.052] [28008] [W] [MFG] debug CHECK: Present skips SetDLSSGOptions even though the
menu guard is not engaged (dlssgOk=0 blocked=2393 unblocked=1) - the ladder cannot be
calibrated while this lasts
```

**同一毫秒**里 `[MFG] probe edge: menu guard released, SetDLSSGOptions resumes on this frame.
step advertised=4x accepted=4x latched=1` 也在打 —— 两行在同 1 ms 内表面矛盾
（一行说「跳过 SetDLSSGOptions」、一行说「本帧恢复」），**谁先谁后未证**。

v1.30 已把 `debug CHECK` 的节奏从每 600 帧改到 **每 120 帧**（L47 的修法），
但 120 帧 ≈ 3.5 s @34 real fps，而本局世界段只有 1.5 s ⇒ **下一个读数仍排在进程死后**
⇒ `dlssgOk` 是否在下一帧恢复，**到现在仍未读**。44.8 漏了这条，此处补上。

**教训（L47/L58 一族的又一小例）**：把节奏调快不一定等于「下一局就能读到」——
还要**世界段活得够长**。改节奏和改运行协议必须一起改。

# 第 45 章 13:47 局（v1.31 首跑）：ALT+F4 有主语了，世界冻了，而我们这一侧一切正常

## 45.1 这一局给了三样此前一个都没有的东西

本局 13:47:09 装载（v1.31，13:37 构建），13:47:40.295 进主菜单（`MENU EDGE open=1`），
13:48:23.7–24.4 连按回车（`vk 0x0D`）读档，**13:48:30.991 `MENU EDGE open=0` 进世界**，
**13:48:33.346 `ALT+F4` 被检测到**，13:48:33.347 全部日志停止 —— 世界段 **2.36 秒**。

1. **★ 「进程被终止」第一次有了主语：ALT+F4**（45.2）。
2. **★ 屏幕第一次被存成图片，共 71 张，而且第一次读出「世界冻住」**（45.3）。
3. **★ 我们自己这一侧一切正常：4x 精确 4.00、无停顿、焦点在**（45.5）。

## 45.2 ALT+F4：四天来「谁结束的」第一次有答案

```
[13:48:33.346] [INPUT] *** ALT+F4 (quit) *** is down at this frame. This is a combination
that quits or unfocuses the game and it is the first thing to check when a run ends with no
crash report. Every key down right now: [12 73 A4] (3 vk, 2 physical). Our window is foreground: 1
[13:48:33.346] [INPUT] key set now [12 73 A4] (3 vk down, 2 physical keys)
```

`[12 73 A4]` 折叠别名后 = **2 个物理键 = Alt + F4**（0x12 与 0xA4 是同一个物理 Alt，见 45.6）。
`Our window is foreground: 1` ⇒ 按下时游戏在前台。**下一行日志在 1 ms 后停止。**

**本局「不是崩溃」五来源复核（全部指向 9/19 及更早）**：

| 来源 | 9/20 这一份 | 最近的一条 |
|---|---|---|
| WER `AppCrash_SkyrimSE` | 无 | 9/19（且是别的程序的 AppHang） |
| Crash Logger `SKSE/crash-*.log` | 无 | **9/18 19:34** |
| `%LOCALAPPDATA%` 下 `CrashDumps` 的 `SkyrimSE.exe.*.dmp` | 无 | **9/18 19:16** |
| Application 1000/1002 | 无 | **9/19 09:56Z** |
| System `nvlddmkm`（TDR） | 无 | **9/15 22:15Z** |

⇒ **ALT+F4 + 五来源零记录 = 这一局是「被按键结束的」，不是崩的，也不是 TDR。**
★ **谁按的仍未证**（时序上像是用户看到画面不动之后自己按的 —— 这正是用户说的「卡住」，
但这是推测，不是证据）。**「被终止」这件事本身从此不是谜。**

## 45.3 ★★★★★ 屏幕第一次读出「世界冻住」：世界区 2 秒内只有 2 个取值

71 个采样**全部** `bmp=ok`（仪器自证运行过，L42）。把每张图**按行分区**后：

| 采样（世界段） | 世界区（第 13–359 行） | 顶部条带（0–12 行） |
|---|---|---|
| #67 13:48:31.63 | `18e6f2fbe1e5` | `da8fa621c8ad` |
| #68 | `2df168849af1` | `77130311f39f` |
| #69 | `2df168849af1` ← **与上一张逐字节相同** | `9e6367a08e55` |
| #70 | `18e6f2fbe1e5` | `6b671824a4d9` |
| #71 13:48:33.03 | `18e6f2fbe1e5` ← **与上一张逐字节相同** | `d08262e72c0d` |

- **世界区在 1.40 秒里只有 2 个取值**；`#67` 与 `#71` 差异 **564 像素、全部落在顶部 12 行内**。
- **顶部条带每一张都不同** —— 那正是我们自己的 ImGui 覆盖层（右上 fps 读数）。
- 逐像素：`#68→#69` 与 `#70→#71` 在世界区**差异为 0 像素**。
- 对照：`#60→#71`（跨约 4 秒）差异 **222053/222080** 像素 —— 那是加载黑屏→世界的**淡入**，不是世界在动。

画面里有**一堆火**、一个会走的 **NPC**、一件 **SMP 毛皮斗篷**。250~500 ms 的间隔里
**火一个像素都没动** ⇒ **世界没有在推进**。火是逐帧动画，活着就不可能逐字节不变。

证据图（A=`#67`、B=+1.40 s 的 `#71`、C= |A−B|×8）：
`docs/runlogs/2026-09-20-1347-v131-world-frozen-altf4/PROOF_world_frozen_067_vs_071.png`
—— **C 格里除了顶部 12 行是全黑的。**

## 45.4 ★★★★ 我自己的判据为什么没报：`same` 把覆盖层也算进去了

71 个采样，**`same=0` 出现在每一个上**，`FROZEN` 一次没触发。
原因不是世界在动，而是**我们自己的覆盖层每一张都在变**（右上 fps 数字），
而 `same` 数的是**整帧**逐字节相同 ⇒ 这个数**在原理上永远到不了 3**。

**这是第五个「按构造不可能看见它」的仪器**，而且和前四个不同：前四个是判据写错，
**这一个把测量对象和被测物放进了同一张图**。

⇒ v1.32 把哈希改成**只覆盖世界区**（去掉顶部 16% 与底部 12%），并把打印字段
`hash=`/`same=` 改名成 `band=`/`bandSame=`，让读数自己说明它测的是什么（L50）。

## 45.5 我们这一侧：一切正常，而且是精确的 4.00

最后两个 tick：

```
[45389898] 13:48:33.028 frames=2122 lastPr=2308 silent=23ms stage=d3d11 Wait focus=1
           fence=4238/4238 queued=1 alive=1 presentAge=6ms
[45390141] 13:48:33.270 frames=2130 lastPr=2340 silent=24ms stage=d3d11 Wait focus=1
           fence=4252/4252 queued=1 alive=1 presentAge=7ms
```

242 ms 内 `frames` +8、`lastPr` **+32** ⇒ **32/8 = 4.00**，一直跑到 ALT+F4 前 **76 ms**。
另有 `[XRAY] 4x SNAPSHOT t=0 … (live4x: +28 flips for +7 Present entries)`、
`[XRAY] 4x probe +937ms … panel=149 flips/s live4x=1`、
`[CAM] PC` 世界段 `eye=(-243.05,-415.31,118.56) proj00=0.8391 hrsD=0.005731 paused=0 fade=0`。

⇒ **游戏循环在跑（时钟在走）、我们的 Present 每 24 ms 进一次、4x 在 4.00 倍上呈现 —— 而画面不动。**
这是本项目第一次把「面板在推进、画面没在推进」用数字分开。

屏幕内容本身也正常（`screen_071.png`）：一间木屋里的第三人称视角，毛皮斗篷、铁盔、
右侧一个 NPC、左侧一堆火，**而左上角四条加载通告仍然挂着**
（`Apply Actor SMP Physics List done` / `CBPC 3BA Physics Manager - load done` / …）。
**「加载通告没消掉」与「世界没在推进」同时成立，这条值得下一局专门看一眼。**

## 45.6 别名折叠：`[12 73 A4]` 是 2 个键，不是 3 个

`GetAsyncKeyState` 对**同一个物理 Alt** 同报 `VK_MENU (0x12)` 与 `VK_LMENU (0xA4)`
（Shift：0x10/0xA0/0xA1；Ctrl：0x11/0xA2/0xA3）。v1.31 的折叠生效了：`3 vk, 2 physical`
—— 正好把「Alt+F4」与「Alt 单独」分开，本局落在前者。（v1.30 那局的 `(2 held)`
是我自己的重复计数，见 44.4。）

## 45.7 ★ 另一个必须记住的坑：watchdog 日志**跨启动追加**

该文件里同时有 13:26 局（74 行，v1.30 格式 `distinct=`）与 13:47 局（71 行，v1.31 格式 `bmp=`）。
`grep -c "[SCREEN]"` = **145 = 74 + 71**。**读 watchdog 日志前必须先找到当前局的边界**
（v1.30 的行没有 `bmp=`、v1.31 的有，再往后靠时间戳）。
而主日志 `DynamicShaderFrameGen.log` 是**每次启动覆盖**的。**两者规则不同，别混。**

## 45.8 v1.32 改了什么（`patch_v132_the_header_and_the_band.py`，6 锚点 count==1）

两个缺陷都是**由 13:47 局自己的输出暴露的**：

1. **BMP 头从来没写 `biSize`** ⇒ 其后每个字段都早了一格（宽度落在 14 位置即 `biSize` 处、
   高度落在 18、`biHeight` 留 0），71 个文件**没有一个能被普通程序打开**
   （PIL：`Unsupported BMP header type (640)`）。
   修法：补 `const unsigned dibSize = 40u;` 并写进偏移 14，宽度移到 18、高度移到 22。
   **离线实测**：按新布局拼出的文件 PIL 打开为 640×360 RGB；按旧布局拼出的被拒。
2. **屏幕哈希只覆盖世界区**（顶部 16% / 底部 12% 不计入），打印字段改名
   `band=`/`bandSame=`（见 45.4）。

**验证**：6 锚点 count==1（干跑先通过）｜构建 `BUILD SUCCESS`｜DLL **1,394,688 B ·
`92789663936404e3f1b54e301b3064a6`**，**build == MO2 部署**（双份一致）｜
二进制内 4 个新串在、2 个旧串消失｜行尾 DX 纯 LF（CR=0）。

## 45.9 仍未证（不许假装）

- **「世界为什么冻」仍未证。** 已排除的是「我们这一侧不健康」（45.5）。
  未测的是**把帧生成关掉之后画面会不会动** —— 这是唯一能分开「4x 干的」与
  「游戏自己冻的」的实验，而它**到今天仍然一次都没跑过**。
- **2x 对照局（`MFGMaxFramesOverride=0`）** 仍未跑；**Transfusion 隔离实验**仍未跑。
- **谁按的 ALT+F4** 仍未证。
- v1.32 **一局都没跑** ⇒ `band=`/`bandSame=` 首跑按校准读（L53）。

# 第 46 章 · 14:03 局（v1.32 首跑）：世界在光天化日之下没动，而我们的 4x 一直在走

> 这是本项目**第一次**用两块互相独立的仪器同时量到「我们这一侧每一帧都在推进，玩家看到的那块画面 14.8 秒里一个字节没变」。
> v1.32 的两个新读数（`band=`、可直接打开的 BMP）在这一局全部第一次出现，并且**两个缺陷都被证实修好了**。

## 46.1 这一局是什么

| | |
|---|---|
| 版本 | **v1.32**（DLL `92789663936404e3f1b54e301b3064a6`，1,394,688 B，build == MO2 部署） |
| 启动 | `14:03:04.610` |
| 进菜单 | `14:03:36.442`（`MENU EDGE open=1`） |
| **进世界** | **`14:03:58.455`**（`MENU EDGE open=0 serial=932`） |
| **结束** | **`14:04:13.911` ALT+F4（前台，2 个物理键 `[12 73 A4]`）** |
| **世界段** | **15.456 s —— 近十局里最长的一局**（此前 2.0/2.1/2.5/3.0/3.2/4.1/5.7/6.1/2.36） |
| 屏幕采样 | 80 张，`#1`–`#80`，**`bmp=ok` 80/80** |
| 崩溃 | **无**（ALT+F4 是最后一行；五来源零记录） |

## 46.2 v1.32 的两个修复，在真实数据上验证通过

**① BMP 头（v1.31 的 `biSize` 从来没写）**：抽样 12 张（#45/#70–#80）全部被 PIL **直接打开为 640×360 RGB**。
对照：v1.31 写的旧布局被 PIL 拒绝。⇒ 修好，且是真数据上验证的。

**② `band=` 的世界区哈希**：我用 Python 独立重算（FNV-1a over BMP 第 57–315 行）与插件读数逐样本对插：

| 插件 `band=` | 我手算 | 样本 |
|---|---|---|
| `68A9790A00777FA5` | `F31CE3A1C308AF93` | #45 |
| `533A2F28880801B2` | `C4499BE3A746FE36` | #67 |
| `807C2959A1C4FC8B` | `43CCE8831C71B9D1` | #68 #69 #73 |
| `7BB57A2E3F385015` | `53E71374A20F16B5` | #70 #71 #74 #75 #78 #79 #80 |
| `43C2C790FEBB6720` | `CEF2F34CC92EB966` | #72 |
| `8F0101B3A63B3CD7` | `AC724EC6E2CF62E5` | #76 #77 |

**绝对值不同（插件哈希 BGRA 4 字节/像素，我哈希 BGR 3 字节），但分组 6/6 完全一一对应。**
⇒ `band=` 可信，且**不用信我们的代码也能从文件复现**。

★ **`kScrBandY0 = 360*16/100 = 57`、`kScrBandY1 = 360*88/100 = 316`**（`DX12SwapChain.cpp:1058-1059`），
DIB 是 BGRA top-down；BMP 与哈希来自**同一次捕获**（`WriteScreenBmp(s_scrBits, ...)` 紧跟哈希之后）。

## 46.3 世界段：40 个采样、6 张不同画面、3 张占绝大多数

进世界后（`lum≈101.7`）40 个采样，跨度 **14.80 s**（379 ms/采样），`frames` 从 942 涨到 1449：

| band 值 | 张数 |
|---|---|
| `7BB57A2E3F385015` | 16 |
| `807C2959A1C4FC8B` | 11 |
| `8F0101B3A63B3CD7` | 10 |
| `68A9790A00777FA5` / `533A2F28880801B2` / `43C2C790FEBB6720` | 各 1 |

换图间隔全部落在 **244 / 448 / 469 ms** 的量化格上（采样节奏所致），换图之间 `bandSame` 到过 **2**。

## 46.4 ★ 决定性的那张对比：#41 与 #80 相隔 14.8 秒

| | |
|---|---|
| 整图不同像素 | **572 / 230400 = 0.248%** |
| 其中 >16 级 | 283（0.12%） |
| **这 572 个像素的行分布** | **只在第 0–11 行**（`rows {0:5, 1:22, 2:27, 3:27, 4:24, 5:79, 6:78, 7:78, 8:79, 9:79, 10:69, 11:5}`） |
| 列分布 | 第 1–63 列（124 px）+ 第 512–609 列（448 px） |

⇒ **世界区（第 13–359 行）在第 0 与第 14.80 秒之间逐字节完全相同。**
唯一在动的是两块**文字**：左上角的游戏载入通告，和右上角一个**第三方 OSD**（`FPS 39 | CPU 61% | GPU 10 | 延迟 …ms`）。

**我做过并否定的两个替代解释**：
- **不是整体位移**：把 #80 与 #77 做 5×5 整数位移补偿，`(0,0)` 残差最优（mean 3.333 / 2166 px>16），
  任一非零位移都更差（mean 8.5–19.7）。⇒ 不是缩放/相位抖动。
- **不是撕裂**：差异是弥散小振幅（每行 >16 的像素只有 10–35 个，共 315 行），没有水平接缝。

## 46.5 ★★ `[SCREEN] ours=` 就是 `[PIXEL] hash=` —— 我在 v1.31 把同一个量当成了两个

同一时刻的两个读数：

```
[SCREEN] #59 band=… ours=329B6FF11315AAF7        (watchdog, 14:04:06.7)
[PIXEL]  #59 hash=329B6FF11315AAF7 chg=1 …       (main log,  14:04:06.7)
```

⇒ `ours=` **不是覆盖层哈希**。它是 `g_colorOutHash`（`DX12SwapChain.cpp:621` 注释：
"the hash of the image we hand to DLSS-G, published by PixelProbeTick"），
而 `PixelProbeTick()`（`2155`）采的是 **`colorOutWrapped` 的中心 64×64**
（`2191-2197`，注释明写「With DLSS-G on, Streamline presents colorOutWrapped, not the engine backbuffer」）。

**v1.31 的文档把 `ours=` 写成「我们自己的 colorOut」并解释成覆盖层——错。正确语义 = 呈现给玩家的那张纹理的中心块。**
本局它 `chg=1` **80/80**（哈希每 500 ms 都不同），`changed` 从 28 一路加到 41。

**⇒ 两个仪器对同一件事给出了相反的答案**：
- `[PIXEL]`（全分辨率、中心 64×64、读的是 `colorOutWrapped`）：**每 500 ms 都在变**
- `[SCREEN]`（桌面 3840×2160 六倍下采样到 640×360，读的是 DWM 合成出来的屏幕）：**14.8 秒不变**

**这条矛盾本身是本局最有价值的读数**，它把故障夹在「`colorOutWrapped` 的内容」与「屏幕上的像素」之间。
两个候选：(a) DLSS-G 的输出在几张近乎相同的图之间循环（世界根本没推进）；
(b) 纹理在变，但合成的屏幕没跟上。

## 46.6 我们这一侧：精确 4.00，一直走到 ALT+F4 前 76 ms

```
[46330465] 14:04:13.595 frames=1449 lastPr=2979 … focus=1 alive=1 presentAge=4ms
[46330708] 14:04:13.837 frames=1457 lastPr=3011 … focus=1 alive=1 presentAge=11ms
```
242 ms 内 `+8 frames / +32 flips` ⇒ **4.00**。

**三个互不相同的来源同时说 4x**：

| 来源 | 读数 |
|---|---|
| 我方 DXGI | `frames 942→1449`（507 次 Present / 14.8 s = **34.3/s**）、`lastPr` 恰 4 倍 |
| 我方探针 | `[FrameGen] FPS probe: real=34.2 \| DLSSG \| cap~=136.7 (=real*4, COMPUTED not measured) \| hwMax=6 ask=4 accepted=4 \| cfgProvider=1` |
| Transfusion（驱动侧） | `DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)`；`[PERF] 4x \| Kernel: Ada \| FPS: 34.5`；perf.csv 末行 `376,53965.62,30.49,4,Ada` |
| 我方 XRAY | `4x SNAPSHOT … (live4x: +36 flips for +9 Present entries over the last 200 ms slice)`；`panel=132 flips/s` |

**`hwMax=6 ask=4 accepted=4`** —— 请求被接受（对照 9/19 22:54 局：请求根本没发出去）。

## 46.7 «不是崩溃» 与本局一起成立的「游戏是活的」

- **五来源零记录**：WER / Crash Logger / CrashDumps / `nvlddmkm` / Application 1000-1002 —— 本局无一条；结束时是 **ALT+F4（前台）**，日志 1 ms 后停。
- **第三方模组在最后一秒还在写日志**：`ShadowLimitFix.log` 14:04:13.811/.896、`DynamicSnow.log` 14:04:13.190。
- **游戏钟以恰好 20× 走**：`hrs 12.34650 → 12.40909`（11.116 s 内涨 0.06259 h = 225.3 游戏秒 ⇒ 20.27×，正是默认 timescale）。
- `paused=0`、`ld=0`、`fade=0`。

⇒ **主循环活着、钟在走、渲染在出帧（34 fps），但世界内容不推进。** 这两件事必须同时成立才是本局的形状。

## 46.8 `debug CHECK` 本局 **0 次** —— 44.9 的悬案部分落定

本局全日志 `[MFG] debug CHECK` = **0 行**，而主日志有：
`[FrameGen] DLSSG diag: fgOn=true dlssgOk=true token=0x7ffa981a9d88 fail=0`。
⇒ 13:26 局那条 `dlssgOk=0 blocked=2393 unblocked=1` **不是常驻的**；本局没有出现。

## 46.9 右上角那个 OSD 不是我们的（顺便纠正一条）

它写的是 `FPS 39 \| CPU 61% \| GPU 10 \| 延迟 …ms`。当前源码里**没有任何一条字符串常量包含 `CPU` 或 `GPU %`**
（`grep -E '"(FPS\|CPU\|GPU)'` 在 `src/*.cpp` 只命中注释与备份目录）。我们的覆盖层只打
`"%.0f FPS  [%.0f real x%.0f reported]"`（`ImguiMenu.cpp:217`）。
⇒ 那块 OSD 是**第三方**（RTSS/NVIDIA 之类，含中文「延迟」标签）。

而且我们的 ImGui 覆盖层**画在 `swapChainBufferWrapped` 上、在 fence 之前**，
注释原话：「插帧启用时菜单会进 DLSSG 输入」（`DX12SwapChain.cpp:1740-1746`）
⇒ **它和世界一起冻结是必然的**，与「覆盖层还在动所以画面没死」不能互证。

## 46.10 9/19 那次对照其实早就跑过 —— 就写在 INI 自己的表头里

`DynamicShaderFrameGen.ini` 第 7–11 行（v1.21 时期写下的）：

```
;   22:54  Provider=1, 4x requested   picture completely fixed, game unplayable
;   23:22  Provider=1, NR suppressed  same freeze (so NR is not the cause)
;   23:38  Provider=0 (FSR3)          picture alive, 2x only, flicker
; => the freeze belongs to the DLSSG path, not to frame generation as such.
```

并且第 24–27 行已经点出机制候选：
「dlssg 4x presented **while the image did not change**，D3D12 队列读 `swapChainBufferWrapped`，
而引擎是从 D3D11 写它的，两者之间没有任何定序 —— **That is a stale-colour-buffer mechanism.**」

⇒ **本局的形状与这段 9/19 的记录完全一致**，而 `InteropFenceWait=1` 已经在生效。
所以要么这条定序没真的起作用，要么还有第三个机制。

## 46.11 本局的动作：把 4x 与 DLSSG 拆开（四天来第一次做这个 2x 对照）

已知 (a) 冻结属于 DLSSG 路径（9/19）、(b) 4x 的请求确实被接受。
还缺最后一步：**冻结是「DLSSG 本身」还是「4x（Transfusion 提供的 Ada 内核）」？**

INI 已改（带备份、只改 1 行、CRLF 保持）：

| 键 | 前 | 后 |
|---|---|---|
| `Provider` | 1 | **1**（不动） |
| `DLSSGFramesToGenerate` | 3 | **3**（不动） |
| **`MFGMaxFramesOverride`** | **3** | **0** |

`0 = off, follow the hardware report exactly`（INI 第 98 行）⇒ Ada 上硬件自报 1 ⇒ **2x，原生 DLSS-G，不需要外部内核**。
备份：`DynamicShaderFrameGen.ini.bak-control-2x-20260920-141141`（**已验证与改前逐字节相同**）。
INI md5：`efce89119d840670e519d219749a6476` → `c44d97096ea82b765fac7c10c7ef9068`。

**判据（写在这里，方便下一局照读）**：

| 看到的 | 结论 |
|---|---|
| 2x 局画面**活了**（世界区每次采样都变） | 冻结在 **4x / Transfusion 内核**，不在 DLSSG 本身 → 下一步隔离 Transfusion |
| 2x 局画面**仍死**（世界区仍旧不动） | 冻结在 **DLSSG 路径本身** → 下一步查 D3D11↔D3D12 定序与 `colorOutWrapped` |

## 46.12 本局新增的方法论

- **L68**：**两个仪器对同一现象给出相反读数时，先查它们测的是不是同一个对象、同一个分辨率，再决定信谁。**
  本局 `[PIXEL]`（全分辨率、中心 64×64、读 `colorOutWrapped`）说「每 500 ms 都在变」，
  `[SCREEN]`（六倍下采样、读 DWM 合成结果）说「14.8 s 没变」。这不是噪声，是**故障被夹在两者之间**。
- **L69**：**从未在「已知活着」的配置上校准过的仪器，不能用来宣布「死了」。**
  `band=` 到今天为止见过的唯一世界状态就是「不动」；**必须**在某一局里亲眼看到它随玩家移动而变，
  这句话才成立。这就是为什么下一局的协议里加了「走两步」。
- **L70**：**一次运行可以同时回答两个独立问题**，只要它们在时间上可分离
  （先站着 15 s 答「2x 会不会冻」，再走 10 s 答「仪器认不认得动」）。
- **L71**：**同一个量在两处打印时，先确认它们是不是同一个量**。`ours=` 与 `hash=` 同值这件事，
  v1.31 的文档解释错了整整一轮（把 DLSS-G 输出的中心块当成了自己的覆盖层）。

## 46.13 还没证的（不要假装）

- **「世界为什么不动」仍未证。** 本局只证明：我方 Present 每帧在推进、4x 精确、游戏主循环活着、世界内容不推进。
- **2x 对照局一次都没跑过**（INI 刚改好，下一局才是它）。
- **`band=` 从未在画面确实在动的状态被校准过**（L69）。
- Transfusion 隔离（`DINPUT8.dll` → `DINPUT8.dll.transfusion-off`）一次没跑。

# 第 47 章 14:17 局（v1.32 第二跑）：`FROZEN` 首次触发 —— 以及我上一轮改错了键

**结论先行**：这一局的价值有一半来自它「不是对照」这件事。`FROZEN` 首次触发并得到
**双向验证**（L73）；同时我上一轮当作「2x 对照」的那次 INI 改动是**空操作**，
用户为它白跑了一趟 —— 这是 L0 脑子检查第 4 条（改 A 为 B 前先证明 A ≠ B）的一次实证违反，
已记为 **L72**。

## 47.1 ★ 我改错了键：`MFGMaxFramesOverride` 在这里是空操作

14:03 局之后我把 INI 的 `MFGMaxFramesOverride` 从 `3` 改成 `0`，并在交付里说「这就是 2x 对照」。
根据是 INI 第 95 行的注释：「The Streamline runtime reports numFramesToGenerateMax=1 on Ada」。
**那一行注释是过期的。** 本局日志第 30 行写的是：

```
[14:17:42.163] [Streamline] MFG override disabled (INI MFGMaxFramesOverride=0) - hardware max 6x
```

硬件上报的是 **6x**，不是 1。于是 `ask=4` 原样通过：

```
[FrameGen] FPS probe: real=33.4 | DLSSG | cap~=133.5 (=real*4, COMPUTED not measured) | hwMax=6 ask=4 accepted=4 | cfgProvider=1
[XRAY] 4x SNAPSHOT ... (live4x: +28 flips for +7 Present entries over the last 200 ms
DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
perf.csv 末行  198,39786.53,30.47,4,Ada
```

⇒ **本局仍是 4x。`0` 和 `3` 在这台机器上是同一个结果**（`0` = 跟随报告 6x，`3` = 覆盖成 4x 上限，
而请求本来就是 4x，两边都落到 `ask=4 accepted=4`）。

**真正决定倍数的键是 `DLSSGFramesToGenerate`**（INI 第 88–92 行：`1=2x, 2=3x, 3=4x, 4=5x, 5=6x`）。
`MFGMaxFramesOverride` 只抬/降**上报上限**，改它只有在「上限低于请求」时才有效果。

**为什么这个错误特别值得记**：它不是读错日志，也不是写错代码 —— 它是我**读了一段注释就当成了事实**，
而且**没有做那个唯一能证伪它的动作：在本局日志里找这个开关实际生效的那一行**。
14:03 局的日志里本来就有 `MFG override ... hardware max Nx` 这一行，我没去读。
⇒ **L72：一个语义键（"off" / "follow the hardware"）的效果取决于运行时上报值；
判断它有没有生效，只能读它自己打印的那一行，不能读 INI 的注释。注释是历史文档，会过期。**

**改对了的键**：本局之后 INI 改为 `DLSSGFramesToGenerate=1`（=2x），备份
`…ini.bak-control-2x-real-20260920-142041`（与改前逐字节相同），md5
`c44d97096ea82b765fac7c10c7ef9068` → **`f5c7f5d9707a7dcc4eee52b086732d83`**，只改 1 行，纯 CRLF 保持。
**回退 = 该行改回 3。**
★ 注意这是**推断**（INI 的语义表 + 实测 `3 ⇒ ask=4` 的线性关系），
`ask=2 accepted=2` 本身**未被实测过** ⇒ 首跑按校准读（L53）。

## 47.2 ★ `FROZEN` 第一次触发，五次

```
[SCREEN] #32 band=F8832F973D7AE6C3 lum=101.34 dLum=+76.97 bandSame=0 oursSame=0 ring=8/8
[SCREEN] #33 band=F8832F973D7AE6C3 lum=101.34 dLum=-0.00 bandSame=1 oursSame=1
[SCREEN] #34 band=F8832F973D7AE6C3 lum=101.35 dLum=+0.00 bandSame=2 oursSame=0
[SCREEN] #35 band=F8832F973D7AE6C3 lum=101.35 dLum=+0.00 bandSame=3 oursSame=0
[SCREEN] FROZEN for 3 captures: the world band (overlay excluded) is byte-identical on
         every one of them (hash=F8832F973D7AE6C3 lum=101.35 dLum=+0.00) while our own
         colorOut changed on all of them and our Present was entered 683 times.
```

本局五次：`#33–#35`（band `F8832F97…`）、`#37–#39`（`2A9D08CF…`）、`#40`（第 4 张）、
`#43–#45`（`F8832F97…`）、`#46`（第 4 张）。**第五个「按构造不可能触发的仪器」修好了，
而且首跑即触发**（v1.31 的 `same=` 是整图哈希，被我们自己的覆盖层永远打断 ⇒ 全 0；
v1.32 改成只哈希世界区，见 46.x 与 `kScrBandY0=57`/`kScrBandY1=316`）。

## 47.3 ★ 判据的双向验证（L73 的实例）

`FROZEN` 说的是「band 相同 ⇒ 世界区逐字节相同」，而 band 只覆盖图像的第 57–315 行
（内存是 top-down：`biHeight = -kScrH`，所以 `by*kScrW*4` 的第 57 行就是**图像顶部往下第 57 行**）。
把它拿到 BMP 上逐行分区，两组预测都必须成立：

| 配对 | `band=` | band 内差异 | band 外差异 |
|---|---|---|---|
| #33 vs #34 | 相同 | **0** | 183（行 0–7…） |
| #34 vs #35 | 相同 | **0** | **0** |
| #37 vs #38 | 相同 | **0** | 66（行 5–10） |
| #43 vs #44 | 相同 | **0** | 60（行 5–10） |
| #44 vs #45 | 相同 | **0** | 91（行 1–8…） |
| #45 vs #46 | 相同 | **0** | 119（行 1–8…） |
| #35 vs #39 | **不同** | 81177 | 23915 |
| #39 vs #41 | **不同** | 92846 | 27385 |
| #35 vs #41 | **不同** | 80785 | 24576 |

**6/6 band 内为 0，3/3 band 不同时 band 内数万字节不同** —— 两个方向都成立。
⇒ `band=` 确实在说它说的话，`FROZEN` 成立。**这是第一次我们能指着屏幕说「世界区冻了」而判据受过双向检验。**

★ 另注：`band=` 相同但**整图**哈希不同（#33/#34/#35 的 SHA1 各不同）—— 两者不矛盾，
差异全部落在 band 之外的行（顶部通告 + 第三方 OSD）。这正是 46 章要的「把我们的覆盖层排除在测量之外」。

## 47.4 世界段与结束方式（与 14:03 局同构）

- 启动 `14:17:32.182`；`MENU EDGE open=1 serial=2` `14:18:01.852`；
  `MENU EDGE open=0 serial=639` **`14:18:15.994`**（同一毫秒
  `[MFG] probe edge: ... step advertised=4x accepted=4x latched=1`）；
  `ALT+F4 (quit)` **`14:18:23.399`**（`[12 73 A4]` = 折叠别名后 **2 个物理键**，`foreground: 1`）。
- **世界段 7.405 秒**（上一局 15.456 s）。**仍短于 8 秒** ⇒ 仍看不到趋势，只够看冻结。
- 五来源崩溃复核全为零：WER `AppCrash` 最新 **9/18 19:16**；Crash Logger **9/18 19:34**；
  `CrashDumps\*.dmp` **9/18 19:16**；`nvlddmkm` TDR 无新记录；Application 1000/1002 无输出。
  ⇒ **与前两局相同：被终止，不是崩的，不是 TDR。**

## 47.5 两块仪器的矛盾重现（L68）

- `[PIXEL]`：47 行，`chg=1` **47/47**，hash 每次都不同（`ACB44CDA…`→`B4ED25EC…`），
  `movedThisStreak=0 seen=8/8 maxStreak=7`。它读的是 `colorOutWrapped` 中心 64×64。
- `[SCREEN] band=`：14.8 s（上一局）/ 本局约 8 s 内只在 **3 个值之间循环**。

⇒ 与 14:03 局同构：**全分辨率下那块在变，六倍下采样后的 DWM 合成结果不变。**
L68 的处置仍然适用：先确认两者测的是不是同一个对象、同一个分辨率 —— 不是。
**故障被夹在这两者之间，这一点现在是两局一致的。**

## 47.6 本局新增的可疑与未证

- **`ask=2 accepted=2` 未实测** ⇒ 2x 对照本身仍未跑（这是本局之后才改好的）。
- 世界段 7.405 s ⇒ `band=` 这台仪器**仍未在「画面确实在动」的状态下被校准过**（L69）。
  它至今只见过两种状态：载入/菜单的巨变，和世界段的冻结。**没有一次是「世界在动」。**
- 底部 316–359 行（12%）不在 band 内 ⇒ 若冻结的差异只出现在屏幕下部，`band=` 看不到。**限度照写。**
- `[MFG] debug CHECK` 本局 **0 行**（与 14:03 局一致；13:26 局那条 `dlssgOk=0 blocked=2393`
  不是常驻）。`dlssgOk` 是否会在下一帧恢复，**仍未读**。

## 47.7 补：世界区的「不同」是小振幅抖动，不是推进 —— 两局合起来才说清

47.3 的表只说了 band 不同时有 **81177 / 92846 / 80785** 个字节不同，没说**幅度**。
把 `|#35 − #39|` 放大 3 倍看，差异图仍然是暗的（见
`docs/runlogs/2026-09-20-1417-v132-frozen-verified/PROOF_band_verification.png` 下排中格）；
而三个「同一场景」的样本（#34/#35/#36）并排看**完全一样**：同一个玩家背影、同一堆火、
同一个 NPC，位置姿态都没动。

⇒ 准确的说法是：**本局世界区在 2–3 个「几乎一样的画面」之间做低振幅抖动，
而不是推进。** 与 14:03 局的差别只是量级：

| 局 | 世界区在 14.8 s / 8 s 内的行为 |
|---|---|
| 14:03（v1.32 首跑） | **逐字节完全相同**（整图差异 572 px 全在第 0–11 行） |
| 14:17（本局） | 在 3 个值之间循环，**值间差异幅度小到 x3 放大仍暗** |

**两局不矛盾，指向同一件事**：没有 NPC 走位、没有动画帧推进、没有场景变化。
本局多出来的那点低振幅抖动，来源未证 —— 候选是 DLSS-G 插值每次结果略有不同，
或捕获时序抖动；**未做实验，写「未证」**。

★ 这也是 L61 的又一例：「世界冻了」这句话必须带**范围**（哪些行、什么幅度、多长窗口）。
只写「不同」会让人以为场景变了；只写「相同」会漏掉这层抖动。
