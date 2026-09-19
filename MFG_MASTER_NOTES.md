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
