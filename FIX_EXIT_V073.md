# FIX_EXIT_V073 — 让「卡死还是退出」变成可判定

日期：2026-09-18
上一次交付：v0.72（失焦旁路）
本次交付：**v0.73（退出探针 + 采样线程 + 墙钟）**

---

## 0. 先更正我上一轮的结论 —— 我错了

上一轮（23:40 那次冻结）我给出的归因是：

> 失焦 → `Present` 阻塞 → FLIP 模型 Present 死锁

并据此交付了 v0.72：失焦时两处 `Present` 改走 `DXGI_PRESENT_DO_NOT_WAIT`、在 `Present` 中途切 DLSS-G 模式、加 `focusBlock` 跳过 `slEvaluateDLSSG`。

**本轮 06:47 那次运行的数据把这个归因推翻了**，而且更糟：**我上一轮加的"修复"本身就是新一轮卡死的根因。**

### 推翻它的三条证据

1. **失焦那条链是好的。** 06:48:19.07 `[XRAY] FOCUS lost` → 06:48:20.788 `[XRAY] FOCUS regained`，**1.7 秒就切回来了**，之后帧循环又正常跑了 **21 秒**（看门狗 frames 802 → 1822）。v0.72 的 unfocused bypass 生效且恢复成功。
2. **卡死与失焦无关。** 末次看门狗 tick 是 `focus=1`（窗口在前台）。
3. **死时 GPU 时间线是活的。** 末次 tick：`silent=39ms`、`fence=3642/3642`（两个围栏相等，且 3612→3628→3642 一直在推进）⇒ 不是 GPU 卡住。

### 我的 v0.72 为什么反而有害

- **`Present` 的阻塞是"刹车"，不是"故障"。** `FLIP_DISCARD` + `BufferCount=3` 下，翻页队列满时 `Present` 阻塞是"CPU 不许跑到 GPU 前面"的**唯一**同步机制；而我在 `Present` **紧后面**就 `Reset` 命令分配器。把 `Present` 拆成不等待 ⇒ 分配器在 GPU 还在用的时候被重置。
- **中途切 DLSS-G 模式违反 pacer 契约。** pacer 期望"每帧一次评估"，我在 `Present` 中途改 `eOff`，等于一帧内改两次状态。
- 结论：**我在正常路径上拆掉了同步机制。** v0.72 已整体回退。

### 另外两处语义误读（必须写下来，否则还会再犯）

| 我当时的理解 | 事实 |
|---|---|
| `stage=d3d11 Wait` = 线程**阻塞在** d3d11 Wait | `stage=` 是**帧完成时**才推进的"最后一个被设置的标记"，卡死时它显示的是**上一帧的落点**，不是当前阻塞点 |
| `ID3D11DeviceContext4::Wait` 会**阻塞 CPU** | 它是 **GPU 侧排队等待**（等价 `ID3D12CommandQueue::Wait`），**不阻塞 CPU** |

---

## 1. 06:47 那次运行的完整时间线（v0.72 DLL）

日志：`C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`
行数 449，首个时间戳 06:47:31.877，最后一个 06:48:41.575。
看门狗本次段：289 个 tick，覆盖 57.8 秒。

| 墙钟 | 事件 | 判读 |
|---|---|---|
| 06:47:31 | 游戏启动；DLL = v0.72（1292288 B，md5 `cfc8b08d013c…`） | — |
| 06:48:05 | `MENU EDGE open=1 serial=2`；`DLSSNR suppressed` | v0.69 互斥生效 |
| 06:48:11 | `Data loaded - frame generation plugin ready` | — |
| 06:48:19.070 | **`[XRAY] FOCUS lost`** | 玩家 Alt+Tab 出去 |
| 06:48:19–20.8 | `stage=unfocused bypa focus=0`，frames 冻在 **802**，silent 涨到 1607ms，**未报 STALLED** | bypass 工作正常，只是没显示 |
| 06:48:20.788 | **`[XRAY] FOCUS regained`** | **1.7 秒就切回来了** |
| 06:48:21.7 起 | 帧循环恢复，frames **808 → 1822** | **失焦链已修好，且恢复成功** |
| 06:48:41.674 | `[DMKUpdate] Received type=LeftAlt value=1` | 按下 Alt |
| **06:48:41.718** | **`[DMK] WM_ACTIVATEAPP: Game lost focus`** ← **全日志语料最后一行** | 触发点 |
| ~06:48:41.74 | 最后一次 `Present()` 返回（在飞帧完成） | — |
| ~06:48:41.78 | 最后一次看门狗 tick，**健康的**：`frames=1822 silent=39ms stage=d3d11 Wait focus=1 fence=3642/3642` | GPU 时间线活着 |
| ~06:48:41.9 | **一切停止**：`DynamicShaderFrameGen.log` 06:48:41.575 / `DynamicSnow.log` 06:48:41.575 / `ShadowLimitFix.log` 06:48:41.635 / `DirectionalMovement.log` 06:48:41.718；五个日志器 mtime 同为 06:48:41 | 同瞬间停止 |
| 06:48:41 | MO2 usvfs 日志出现 `11 releases values 16..6` + 独立一行 `5 users left` —— 该形状**历次会话结束都出现** | = 游戏进程退出 |

### 已排除的原因

| 方向 | 证据 |
|---|---|
| 崩溃 | `CrashLogger.log` 仅启动 4 行；`Transfusion.crash.log` 仅 first-chance 观察 + MODULE 清单，**无异常记录** |
| WER | `ReportArchive` 只有 09-17 20:19 系统更新 + 09-17 23:52/23:53 **explorer.exe** AppHang（与我们无关） |
| TDR | `Display` 提供商历史 25 条**全是 id=4125**（自动 HDR 提示），无 4101/4102；`nvlddmkm` 最近为 09-15 |
| Defender / 代码完整性 | `Operational` 仅心跳与特征库更新 |
| MO2 崩溃 | MO2 crashDumps 仅 08-28 / 09-04；MO2 主进程 PID 43400 **全程存活** |

### 定案不到的地方（必须诚实）

进程是"自己退的"还是"被杀的"，**看门狗单靠自己永远分不清**：
`silent=39ms` + 健康围栏 + usvfs 的"退出形状"，**三者同时兼容两种解释**。

唯一的外部判据是 **`DLL_PROCESS_DETACH`**：

- `DLL_PROCESS_DETACH`（且 `a_reserved != nullptr`）= 进程**从 loader 正常退出**（ExitProcess：游戏自己退 / 崩溃后走到未处理异常过滤器）
- `TerminateProcess`（任务管理器 / MO2「结束进程」）**不会触发**

所以 v0.73 装了这个探针。

---

## 2. v0.73 逐处改动

### 源码（3 文件 / 12 处，脚本 `tools/add_v073_exitprobe.py`）

| 组 | 文件 | 改动 |
|---|---|---|
| C1 | `DX12SwapChain.cpp` | 焦点助手后加全局簿记：`g_bypassReported` / `g_lastSilentMs` / `g_hangFence11` / `g_hangFence12` / `g_samplerTicks` / `g_watchdogLogPath` + `InitWatchdogLogPath()` / `WatchdogLogPath()` |
| C2 | 同上 | 新增 **`StartGpuSampler()`**：独立线程，每 200ms 醒一次，**只在 `g_lastSilentMs >= 1500`（已怀疑卡死）时才**去读 `GetCompletedValue()`；`StartWatchdog()` 里启动它并使用缓存路径 |
| C3 | 同上 | 看门狗算出 `silent` 后 `g_lastSilentMs.store(silent)` 发布给采样线程 |
| C4 | 同上 | **看门狗内删掉两次驱动调用**，改读原子值 + 取墙钟 |
| C5 | 同上 | 行格式：`[mono] hh:mm:ss.mmm frames= silent=ms stage= focus= fence=a/b\|-/- stim=n` |
| C6 | 同上 | 焦点变化时清 `g_bypassReported`（每次失焦只报一行 BYPASS） |
| C7 | 同上 | 旁路**不再抛异常**（v0.72 的 `DX::ThrowIfFailed(hrOff)` 已移除） |
| H1 | `DX12SwapChain.h` | `class DX12SwapChain` 前声明两个自由函数 |
| H2 | 同上 | 加 `void StartGpuSampler();` |
| M1 | `main.cpp` | `#include <Windows.h>` 后加 `#include <cstdio>` |
| M2 | 同上 | `SKSE::Init(a_skse);` 后加 `FrameGen::InitWatchdogLogPath();` |
| M3 | 同上 | 新增 **`DllMain` 退出探针**：`DLL_PROCESS_DETACH && a_reserved != nullptr` 时往看门狗文件写 `[exit] DLL_PROCESS_DETACH hh:mm:ss.mmm reserved=…` |

### 为什么看门狗的两次驱动查询必须搬走

> **会阻塞的看门狗不是看门狗。**

v0.72 把 `d3d11Fence->GetCompletedValue()` / `d3d12Fence->GetCompletedValue()` 放进**看门狗线程**。这两个调用**可能阻塞**——一旦驱动卡住，看门狗自己也卡住，于是"唯一还写得动的东西"失效，卡死现场就没有记录了。

v0.73 把它们移给**专用采样线程**，并且**只在已怀疑卡死时才采样**（正常跑的时候完全不进驱动）。代价是 fence 值可能比 tick 晚最多 200ms，这在"判定卡死"这个问题上无关紧要。

### 读取器（`tools/read_xray_log.py`，脚本 `tools/patch_reader_v073.py`，8 处）

| 组 | 改动 |
|---|---|
| R1 | 旧 `WD_RE` → **单一命名组正则** + `_wd_num()` / `parse_wd_line()` / `parse_wd_file()` / `last_run_exit()`。`[exit]` 按**位置**归段（不按时钟），所以上一轮会话的 `[exit]` 不会被算到这一次头上 |
| R2 | `part_watchdog` 改走共享解析器；元组扩到 10 元，**下标 0..5 含义不变**（`wall/stim/f11/f12` 追加在 6..） |
| R3/R4 | 末行与最后 10 tick 打印加墙钟 / fence / stim |
| R5 | **`_parse_wd` 变成一行委托** `return parse_wd_file(path)` —— 删掉第二份手写正则（每加一个字段要改两处，漏一处就静默失败） |
| R6 | `part_stalls` 按 **`stim`** 分流：`stim` 不动 ⇒ 采样线程自己卡在驱动 = GPU/驱动级；`stim` 在涨 ⇒ CPU 侧被挡。无 `stim` 时回退旧 `fence` 判据 |
| R7 | 新增 **`0c. 上一个进程是怎么结束的（v0.73 退出探针）`** 段 |
| R8 | `main()` 里接入 `part_exit()` |

**`0c` 段的三分支**：

- 末行**无墙钟** ⇒ 那次运行 DLL 早于 v0.73 ⇒ 输出「需要 v0.73+ 再跑」，**不给假结论**
- 有 `[exit]` ⇒ `[正常]` 从 loader 正常退出
- 无 `[exit]` 且有墙钟 ⇒ `[问题]` 被外部 `TerminateProcess` 结束，或死在 loader 拿到控制权之前
- 附加：末行之后仍有同段 tick ⇒ 帧循环卡死而非进程退出

---

## 3. 本次改动的方法学（含一处我自己抓到的假检查）

`patch_reader_v073.py` 第一版干跑时，8 处锚点全 `x1`，但两类问题暴露：

1. **后置检查写错**：`out.count("    part_exit()\\n")` —— 源码里 `\\n` 是**字面反斜杠 + n**，永远匹配不到 ⇒ 报告 `0 (want 1)`。
2. **两条负向检查是假通过**：`old WD_RE gone` / `old _parse_wd regex gone` 用了**四重反斜杠**，实际搜索串是双反斜杠版本（`r"^\\[(\d+)\\]\\s+frames="`），而文件里是单反斜杠版本 ⇒ 恒为 `0`，而检查恰好要 `0` ⇒ **"通过"了，但什么都没证明**。

> **一条不可能失败的负向检查，比没有检查更糟。**

修法：
- 改用 **raw 字面量**（`r'...'`）消除转义歧义；
- **先证明探针能命中**再信它：实测补丁前 probe A = **2**（`WD_RE` + `_parse_wd` 两份）、probe B = **1**，所以它们具备失败能力；
- 独立回读（不靠脚本自报）：`grep -c` 旧正则 = 0/0，新函数在位，`main()` 调用序 `part_watchdog → part_stalls → part_exit` 正确。

**其余守卫**：幂等 marker 4 条（含源码注释里的独有短语）、行尾自适应（本工程 `DX12SwapChain.cpp`=LF、`.h`/`main.cpp`=CRLF）、替换文本与锚点做**同样的**行尾转换、`count(old) == 1` 断言、`--apply` 才落盘（默认干跑）。

---

## 4. 本次交付物与校验

| 产物 | 事实 |
|---|---|
| `src/DX12SwapChain.cpp` | 75383 B，LF，md5 `5dc2b62c81ce…` |
| `src/DX12SwapChain.h` | 9697 B，CRLF，md5 `d2b7d620d996…` |
| `src/main.cpp` | 7007 B，CRLF，md5 `d2598ac90e2e…` |
| 源码备份 | `*.bak-20260918-065932` |
| `build/NINJA/DynamicShaderFrameGen.dll` | 1295360 B，md5 **`d575200f6d3efb394581193fd956bf63`** |
| 部署副本 `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/` | **md5 一致**（POST_BUILD 同步成功） |
| `tools/read_xray_log.py` | 71290 B，LF，md5 `783a380a723e…`；备份 `read_xray_log.py.bak-20260918-070308` |

**二进制特征串抽检**（8/9 命中）：`DLL_PROCESS_DETACH`、`[exit] `、`stim=%llu`、`fence=%s`、`BYPASS present hr=`、`frames=%llu silent=%lldms`、`%02d:%02d:%02d.%03d` 全在。唯一未命中是源码**注释** `// v0.73: samples the GPU timeline from its own thread` —— 注释不进二进制，属**预期**。

**构建**：第一次失败于 `fatal error C1083: 无法打开编译器生成的文件: … Permission denied`（2 个 obj）。**不是代码问题**：同一目录同一时刻另 4 个 obj 写入成功，且这两个目标文件**根本不存在**（= 创建被拒）；枚举进程确认无 `cl.exe`/`ninja` 残留 ⇒ 判为**并发写同一路径的共享冲突**（cl 把 sharing violation 报成 Permission denied）。重跑即 `BUILD SUCCESS`，零告警。

**读取器冒烟**（对现有 v0.72 日志）：10 个运行段全部解析，旧格式字段（frames/silent/focus/stage/fence）完整保留，新字段优雅降级为 `-` / `?:?:?.???`；`0c` 段正确输出「需要 v0.73+ 再跑」而未给假结论。

---

## 5. 下跑验收字段表

跑法：**进世界走 20 秒 → Alt+Tab 出去 5 秒再回来 → 再走 10 秒 → 用游戏菜单正常退出（千万别用任务管理器结束）→ `read_log.bat`**。跑游戏期间**不要编译**（POST_BUILD 会覆盖 mod 目录 INI）。

| # | 看哪里 | 期望 | 含义 |
|---|---|---|---|
| 1 | `0b. 全部运行段` 本次段 `STALL` | **0** | 帧循环没停过 |
| 2 | `0c. 上一个进程是怎么结束的` | `[正常] 找到退出探针…从 loader 正常退出` | 进程自己退的 |
| 2b | 同上 | `[问题] 没有 DLL_PROCESS_DETACH` | **卡死是被外部结束的** ⇒ 直接指向"谁在杀进程" |
| 3 | 看门狗末行 | 带墙钟 `hh:mm:ss.mmm`、`focus=`、`fence=`、`stim=0` | v0.73 真的装上了 |
| 4 | `0c` 附加行 | 末行之后**无**同段 tick | 所有线程同瞬间停止 = 进程退出，不是帧循环卡死 |
| 5 | `DLSSNR suppressed` / `MENU EDGE` | 存在 | v0.69/v0.70 验收项（**一直还没做**，一并看） |

**如果这次又卡死**，`0c` 的那一行会把可能性从两种收窄到一种 —— 这就是 v0.73 的全部目的。

---

## 6. 诚实边界

1. **v0.73 不修任何 bug，它只让"卡死 vs 退出"变成可判定。** 这是刻意的：上一轮我在没有判据的情况下猜了原因，猜错了，而且"修复"造成了新故障。
2. **`[exit]` 探针也有盲区**：进程死在 loader 拿到控制权之前（例如死在 DLL 加载期）不会有 `[exit]`，会与"被外部结束"撞在一起。真撞上要靠 `usvfs` 日志与 `[XRAY]` 首行之间的空隙来分。
3. **`DllMain` 里用 `CreateFileA/WriteFile`** 是在 loader lock 里做事，理论上不推荐；这里只做一次追加写，且失败即静默返回 `TRUE`，不会挂住进程。
4. **`main.cpp` 有 7 行裸 LF**（第 91–97 行，`RUN TIME` 那段）。这是 **v0.69 留下的**（上一版备份里就已经是 7 行），v0.73 **没有新增**。MSVC 能编译，属遗留外观债。
5. **`TdrDelay = 30` / `TdrDdiDelay = 30`**（默认 2）仍在生效 ⇒ GPU 卡死在头 30 秒内不留系统痕迹。**不要盲目改回 2**，那会把"卡 30 秒后复位"变成"2 秒就复位"，反而掩盖问题；等判定权拿到手再谈。
6. **仍未定案**：`dvd(ok/used)=0/0 err=16` 三字段矛盾；`countedFrameIndex` 与 DLSS-G 同步；菜单期 PCL marker；`mv3D=0` 通路。
7. **加载画面闪烁**（v0.63–v0.70 的老问题）本次**完全没有触及**，不要以为改好了。
