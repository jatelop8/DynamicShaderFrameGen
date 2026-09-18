# FIX_XRAY_2145 — 21:40 那次运行的日志判决 + v0.62 诊断加固

时间：2026-09-17 21:45
运行对象：`D:\ENB-EJ\Skyrim Special Edition`（MO2 profile **DIPEI**，不是 JET654）
日志：`…\SKSE\DynamicShaderFrameGen.log`（79 行，21:39:58 → 21:40:44）、
`DLSSG-Transfusion.log`、`DLSSG-Transfusion_perf.csv`、`DLSSG-Transfusion.crash.log`

---

## 一、这次运行证明了什么（逐条有出处）

| # | 结论 | 出处 |
|---|---|---|
| 1 | **游戏确实到了主菜单，DLSS-G 在菜单里真的在出 4 帧/真实帧** | `MENU EDGE open=1`(28.653) 之后紧接 `DLSSG presented per real frame = 4`（28.766/28.791/28.817/28.843/28.869） |
| 2 | **v0.60 这一刀完全没送到 DLSS-G** —— 被中间层剥掉了 | Transfusion：`Option C active: stripped eEnableFullScreenMenuDetection from DLSS-G options (game flags=0x00000010 -> 0x00000010)` |
| 3 | **v0.59 生效**：reset 已从"每帧置位"变成边沿触发 | Transfusion `[MOTION]`：`call=0 reset=1`，随后 `call=1,2,3 reset=0` |
| 4 | **v0.58 仍然有效**：常量不再被拒 | `consts(ok=115 fail=0)`，全场 0 次 27 号错误 |
| 5 | **进程在 21:40:44.4 之后彻底停止写日志** —— DFG 的 2 秒 FPS 探针（下次约 46.3）和 Transfusion 的 5 秒 STARTUP 心跳（下次约 48.9）**同时消失** | 两份日志尾部 |
| 6 | **不是崩溃，是卡死**：Transfusion crash log 无致命记录，只有 NGX 加载期 4 次 first-chance AV（pc 落在 DINPUT8.dll=ENB，属探测性读取） | `DLSSG-Transfusion.crash.log` |
| 7 | **真实帧率被压到 9.75 fps，且极端稳定**：第 12~77 帧间隔恒定 **102.56 ms**（66 帧里波动 < 0.03 ms），`Multiplier=4` ⇒ 上屏只有 **39 fps** | `DLSSG-Transfusion_perf.csv` |
| 8 | **102.56 ms = 4 × 25.641 ms**，而 25.641 ms 正是本插件下发给 Reflex 的上限（39 fps = 160/4） | `Reflex render cap = 39 fps (25641us) - 160Hz / 4x` + csv |
| 9 | 第 77→78 帧之间有 **4.69 秒空档**（27032.73 → 31718.18 ms），之后 csv 就断了 | `perf.csv` |
| 10 | 引擎渲染比例 **0.44**（4K 下只画 1689×950），而 DLSS5-NR 的 `NRRenderScale=1.00`（按 4K 全分辨率分析） | INI + `Render scale 0.440` / `DLSSNR resources guides=3840x2160` |
| 11 | 显示/交换链对齐没问题：`virtual=3840x2160 physical=3840x2160@160Hz swapchain=3840x2160` | `[XRAY] env` |

### 这次**没有**证明的（不要当成结论）

* **闪烁的直接成因**：重投影错 / pacer 失节拍 / 生成帧本身 —— 三者都没被排除。
* **21:40:44.4 之后卡在哪个调用里**：日志什么都没留下，这正是 v0.62 要补的洞。
* **9.75 fps 是"被限速"还是"GPU 真的需要 102 ms"**：两者都符合 102.56 ms 这个数字。
  已知反差：1440p 时代（16:26）上限 60 fps、实测真实帧 17.43 ms ≈ 上限本身；
  现在上限 39 fps、实测却是上限的 **4 倍**，与"纯像素变多"（4K/1440p = 2.25×）对不上。

---

## 二、这次日志里，**我自己的探针**有四处自伤（必须先承认）

| 自伤 | 后果 |
|---|---|
| 心跳节拍 240 帧一次，本次只跑了 119 帧 | **整场只有 1 条心跳**，采样等于零 |
| 心跳块写在 `c.mvecScale` 赋值**之前** | 打出 `mvec=(3.4e38,3.4e38)`（未初始化 FLT_MAX），差点被读成真缺陷 |
| `real=` 用固定 240 做分母、且第一个样本是 `now-now` | `real=0.00ms` |
| `virtual!=physical => DPI-virtualized process` 是写死文案 | 与它自己打印的数值（virtual==physical）互相打脸 |

结论：**上一轮加的"检测机制"因为节奏太粗 + 采样时机错，等于没加。** 这一轮修掉。

---

## 三、v0.62 做了什么（**只加诊断，不改行为**）

1. **心跳**：改为 30 帧或 2 秒（先到者），`mvecScale` 上移到心跳之前，`real=` 按实际 tick 数算并跳过首个样本，env 行改成真实比较。
2. **心跳新增四列**（都在同一行，可互相印证）：
   * `dt min/avg/max=… n=…` —— 真实帧间隔窗口（区分"限速量化"与"GPU 受限"的关键列）
   * `capUs=…` —— 本次真正下发给 Reflex 的上限微秒数
   * `mult(acc/pres)=…/…` —— 接受倍率 / 运行时实测呈现倍率
   * `longFrames=…`
3. **`LONG FRAME` 行**：任何一帧真实间隔 > 300 ms 立刻打一行（载入/卡顿会让画面停在旧帧上，而插帧还在跑）。
4. **看门狗线程（1 Hz）**：写**独立文件**
   `…\SKSE\DynamicShaderFrameGen.watchdog.log`，用 `fopen/fflush/fclose`，
   **故意不走 SKSE 日志**——渲染线程被堵住时 SKSE sink 可能永远不 flush，进程被杀还会丢尾巴。
   每行格式：
   ```
   [单调毫秒] frames=<已完成帧号> silent=<距上一帧毫秒>ms stage=<Present 停在哪个阶段>  [<== RENDER THREAD STALLED]
   ```
   `stage=` 复用早就存在、但此前只被异常路径读过的 `DX12SwapChain::lastStage()`。
   下一次卡死，这行会直接说出**卡在哪个调用**（`dlssg SetDLSSGOptions` / `dlssg EvaluateDLSSG` / `d3d12 Present(dlssg)` / `d3d11 Wait` / `d3d12 queue Wait` …）。
   卡死行还带 `<== RENDER THREAD STALLED`，一眼可辨。

### 关键实现点（踩过才知道）

* `m_stage` 是 `const char*` 指向字符串字面量，跨线程读安全；用 RAII `FrameStamp` 覆盖 Present 的**三条 return 分支**。
* 看门狗用 `std::atomic<bool> watchdogStop` + 200 ms 分片睡眠，方便退出。
* **独立文件而不是 SKSE 日志**：这是"进程被杀也要留下证据"的唯一可靠写法。

---

## 四、下次怎么跑（一次跑完，读取器给结论）

1. 双击 `D:\Modding\DynamicShaderFrameGen\read_log.bat`（读上一次运行，所以先跑游戏）。
2. 跑游戏：**主菜单停 10 秒** → 按回车尝试进世界 **30 秒** → 退出（卡住就直接杀）。
3. 再跑 `read_log.bat`。新增第 0 节与第 8 节：
   * **第 0 节** 看门狗：直接给「渲染线程卡在 `<stage>`，约 N 秒」；
   * **第 4 节** 现在会有 `dt min/avg/max` + `capUs`，读取器会自己算
     「帧间隔是上限的几倍、抖动多少%」并给出 `限速量化` / `GPU 受限` 的判定；
   * **第 8 节** 解析 `perf.csv` 给 DeltaMs 的 min/中位/max 与长帧位置。

### 一次就能分开两种可能的 A/B（改一行 INI，**不需要重新编译**）

日志已经给出两个互斥假设：

* **H1 GPU 受限**：4K + DLSS5-NR(全分辨率) + ENB + 4x 插帧，一帧真实帧真的要 102 ms。
* **H2 限速被多算一次倍率**：Reflex 上限本意是"渲染 39 fps ⇒ 上屏 156 fps"，
  实际变成"上屏 39 fps ⇒ 渲染 9.75 fps"。

**判别实验（二选一，都是可逆的一行）**

| 实验 | 改哪里 | 若真实帧率明显上去 | 若没变 |
|---|---|---|---|
| A：上限按"上屏帧率"给 | `…\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini` → `ReflexFpsLimit=156` | **H2 成立** → 代码里 `capFps` 的算法要改（把倍率从"除"改成"不除"） | **H1 成立** → 去减负载 |
| B：把倍率降到 2x | `D:\ENB-EJ\Skyrim Special Edition\DLSSG-Transfusion.json` → `"multiplier": 2` | 插帧成本是主因 | 负载在别处（NR / ENB） |

> 注意：该项目 `build_vs.bat` 的 POST_BUILD 会把工程里的 INI 覆盖回 mod 目录。
> **要 A/B 就先别重新编译**，或把值同时写进工程 INI。

### 如果 H1 成立，减负载的顺序（成本从低到高）

1. `NRRenderScale` 1.00 → **0.75**（DLSS5-NR 分析分辨率，对观感影响最小）
2. `DLSSGFramesToGenerate` / Transfusion `multiplier` **4x → 2x**
3. `RenderResolutionScale` 0.44 → 0.55~0.60（引擎渲染比例，画面变清晰、成本上升，慎）
4. Transfusion JSON `"blackwellTransfusion": true` —— Ada 卡上走 Blackwell 路径，值得单独 A/B

---

## 五、部署与校验

| 产物 | 路径 | md5 |
|---|---|---|
| v0.62 DLL（1 249 792 B） | `E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.dll` | `9d1db4e3b3b37f5a30230348870c83a1` |
| 同源构建产物 | `D:\Modding\DynamicShaderFrameGen\build\NINJA\DynamicShaderFrameGen.dll` | 同上（POST_BUILD 已自动拷贝） |

* MO2 profile **DIPEI** 中仅 `+DynamicShaderFrameGen` 启用；另两个同名副本
  （`DynamicShaderFrameGenDlss5-v047b-20260911`、`DynamicShaderFrameGenNR`）均为 `-`，不参与。
* 源码改动 4 个文件 15 处，全部经断言式脚本落盘（`count(old)==1`）、备份、回读校验；
  备份为 `src\*.bak-20260917-214836`。
* 顺带发现：本工程 `.h` 是 CRLF、`.cpp` 是 LF（混合行尾），补丁脚本已按文件自适应。

## 六、新增/改动文件清单

```
src/Streamline.h          +Diag 字段（capUs / 帧间隔窗口 / longFrames）
src/Streamline.cpp        心跳节拍、mvecScale 上移、real= 修正、心跳新增 4 列、
                          LONG FRAME 行、ReflexSleep 里累计真实帧间隔
src/DX12SwapChain.h       +<atomic>/<thread>、frameCounter/lastFrameEndMs/watchdogStop、StartWatchdog()
src/DX12SwapChain.cpp     +cstdio/shlobj、CreateInterop 启动看门狗、StartWatchdog 实现、Present 帧戳
tools/add_xray_v062.py    断言式补丁脚本（默认干跑）
tools/read_xray_log.py    读取器升级：第 0 节看门狗 + 第 8 节 perf.csv + 新字段 + 限速/负载判定
build_vs.sh               等价于 build_vs.bat 的 bash 版（沙箱内 cmd.exe 被拦）
```
