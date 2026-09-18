# 冻结根因分析 v0.79 —— 纠正 v0.78，并给出真机制

更新时间：2026-09-18 09:12
分析对象：`DynamicShaderFrameGen.log`（08:58:59.556 启动的那次运行，45.1 s / 1403 帧）
用户报告：**"还是卡死 冻结"**

---

## §0 先说结论，以及我上一轮错在哪

### v0.78 的结论（**部分错误，本文件纠正**）

> "捕获层接受了逐字节冻结的相机矩阵。"

**矩阵逐字节相同是事实。但这个"事实"的成因被完全判错了。**

### v0.79 的真正结论

> **同一个 swapchain 的 Present 路径被两个不同的引擎线程在跑。**
> 两个线程各自维护一份相机、各自计数、各自写日志，**互不知情**。
> 日志里看起来像"一个相机冻结了 2.3 秒"，实际是**两个相机被混进了一条流里比较**。

### 为什么两轮都没找到

| 轮次 | 我用了什么判据 | 判据的毛病 |
|---|---|---|
| v0.65–v0.76 | 心跳里的 `engPrevEqCur` / `clipDevMax` | 这些计数器**就在被污染的同一条路径上**，量的是故障产物 |
| v0.77 | `snap` 计数 + 相机 `path` | 判据本身没错，但**读 `path` 时算错了**（把累计值当瞬时值，78 倍超速是伪警报） |
| **v0.78** | `[CAM] raw` 两条矩阵**逐字节比较** | **前提不成立**：两条行的 `#序号` 是**各自线程内的序号**，不是全局帧号 |
| v0.79 | **线程 ID 分组** | ✓ 生产者 identity 是唯一能区分"冻结"和"混合"的东西 |

★ 我在整整 7 轮里都看着 `[17568]` / `[32096]` 这两个数字，**从来没有把它们当成线索**。

---

## §1 决定性证据

### 1.1 日志里有两个生产者

```
$ grep -o "\[[0-9]\{5\}\]" DynamicShaderFrameGen.log | sort | uniq -c | sort -rn
    278 [17568]
    116 [32096]
      4 [41852]
      1 [20028]
```

**两个线程在跑引擎，各带一套完全不同的相机：**

| | 生产者 A `[17568]` | 生产者 B `[32096]` |
|---|---|---|
| 相机位置 | `pos=(-243.05,-415.31,118.56)` | `pos=(-50.00,619.31,107.04)` |
| `devVP`（ViewProj 范数） | `15.0006` | `15.011` |
| `detVP` | `-2.52504` | `-79.9373` |
| `move`（每帧位移） | `0.0000` / `260–820`（跳变） | `0.0425–0.0476`（平滑连续） |
| 起始序号 | `#9107`（首条 CAM） | `#1`（首条 CAM） |
| 行数 | 169 条 CAM | 88 条 CAM |

`devVP=15.0006` 与 `devVP=15.011` 是**两个不同投影矩阵的范数**——
同一个相机不可能在同一个会话里拥有两个不同的投影。

### 1.2 同一逻辑事件被两个线程各报一次

```
[08:59:29.020] [32096] [XRAY] MENU EDGE open=1 serial=2  presentedBefore=0
[08:59:47.505] [17568] [XRAY] MENU EDGE open=0 serial=1049 presentedBefore=0
```

`MENU EDGE` 本应只在**状态边沿**打印。这里"打开"由 B 报、"关闭"由 A 报——
**这不是一个菜单开合，是两个线程各自报了自己的状态。**

### 1.3 序号空间不连续 = 换了生产者

```
[08:59:28.980] [32096] [CAM] raw #1     ViewProjUnj | -6.70312 0 0 0 | ...
[08:59:44.956] [32096] [CAM] raw #9001  ViewProjUnj | -6.70312 -1.14286e-06 0 0 | ...
[08:59:45.075] [32096] [FrameGen] FPS probe: real=57.9 ... accepted=0     ← B 最后一次发言
[08:59:45.207] [17568] [CAM] #9107 RELOCK after 12 consecutive jumps ...  ← A 首次出现
[08:59:47.505] [17568] [XRAY] MENU EDGE open=0 serial=1049
[08:59:47.505] [17568] [XRAY] diag active v0.61 (compiled Sep 18 2026 07:34:13)  ← A 打印"初始化"横幅
```

★ **`diag active` 是初始化横幅，本应只在会话开头出现一次，却出现在会话中途。**
这是重复实例/重复路径的教科书信号。

★ 中间有 **132 ms**（08:59:45.075 → 08:59:45.207）无人发言。

### 1.4 由此被解释掉的三个"伪现象"

| v0.78 的判读 | v0.79 的真相 |
|---|---|
| `raw #17101 == #19801` 逐字节相同 ⇒ 捕获层冻结 | **跨线程比较**。两个 `#` 是各自线程的序号；两条行来自不同的引擎状态 |
| `clipDevMax=0.0000` 恒为 0（含走动中） | 两个相机在同一个 `prev`/`cur` 对里**交替** ⇒ `inv(cur)×prev` 算出一个恒定且无意义的值 |
| `menu=1047 world=334` 但 `serial=1381` | **两个线程各自的计数器**；`1047+334=1381` 只是巧合地相加成立 |

### 1.5 第三个独立证据：DLSS-G 在多数时间**根本没有生成帧**

```
$ grep -o "DLSSG presented per real frame = [0-9]" log | sort | uniq -c
    8 ... = 1
    2 ... = 2
```

全日志**只有 10 条** `presented` 记录。`1` = **没有任何插帧**。

时间分布：
```
[08:59:47.540]  presented = 1
[08:59:47.609]  presented = 1
...  （连续 6 条 = 1）
[08:59:47.701]  presented = 2
                    ← 空档 5.93 秒 →
[08:59:53.632]  presented = 2
```

**08:59:47.701 → 08:59:53.632 之间 5.93 秒没有一条产出记录。**
心跳同期却在稳定打印（`dt avg=20.2–20.5ms`、`serial` 稳定 +30/次）——
即**渲染循环在跑，DLSS-G 不产出**。

⇒ 用户感受到的"冻结"= **画面在走但插帧没生成**，而 `Mult(acc/pres)=2/2`
已把 Reflex 的 flip 预算设成 2 个/真实帧 ⇒ **上屏节拍与实际产出错配**。

---

## §2 已实施的修复（v0.79，已构建已部署）

### A. INI 天花板回归硬件真值

`tools/patch_ini_v078_mfg_ceiling.py`（带断言守卫，默认干跑）

| 键 | 旧 | 新 | 理由 |
|---|---|---|---|
| `MFGMaxFramesOverride` | 3 | **0** | 0 = 完全跟随硬件上报 |
| `DLSSGFramesToGenerate` | 3 | **1** | 1 = 2x，Ada 可用的上限 |

**INI 自己第 72–80 行就写着**：

> "Without such an unlocker a high multiplier has no kernel to run and the result
> is a black screen or a hang."

而 **DLSSG-Transfusion 已在本轮被移出**（`_removed_transfusion_20260918-074044/`）。
日志实锤：`runtimeReportsMax=2x overrideAsksMax=4x` + `eErrorInvalidState(38)`。

- 源 `SKSE/Plugins/DynamicShaderFrameGen.ini` 与部署版**都已改**（部署注记要求改源，
  否则重新构建会覆盖回去）
- 两处 md5 `23cb5adb0a7852e18809d5302fa5c51a`，**一致**
- 行尾保持 CRLF：`201 CRLF / 0 lone_LF`，大小 10262 → 10997 B
- 备份：两处各一个 `.bak-20260918-090627`

### B. 阶梯解耦出菜单守卫

`tools/add_v079_ladder_menu_guard.py`（4 文件 / 13 处锚点，全唯一命中）

**缺陷**：`DX12SwapChain.cpp:1228` 的 `menuBlock` 分支跳过 `SetDLSSGOptions()`，
而倍率阶梯只在该函数内推进 ⇒ 菜单期间阶梯**卡在被拒的档位**，
`dlssgAcceptedFrames` 保持 0 ⇒ `ReflexSleep()` 的 `capMult` 回退到 INI 值。

**修复**：新增 `Streamline::ProbeMfgLadder()`，在 `Present()` 里
**先于 `menuBlock` / `else-if` 分支无条件调用**。

| 文件 | 行尾 | 大小变化 |
|---|---|---|
| `src/Streamline.h` | CRLF | 15277 → 16243 B |
| `src/Streamline.cpp` | LF | 79016 → 83491 B |
| `src/DX12SwapChain.h` | CRLF | 10595 → 10968 B |
| `src/DX12SwapChain.cpp` | LF | 84020 → 85689 B |

**编译期踩坑（记录）**：
- `Streamline` **没有** `settings` 成员（`LoadInterposer` 只接 `const Settings&`）
  ⇒ 必须 `Get().settings`
- `dx12SwapChain` 是 `FrameGen` 的成员 ⇒ 必须 `Get().dx12SwapChain`
- `SetDLSSGOptions` 是 **6 参数**（第 5 个 `DXGI_FORMAT`），首版只传 4 个 → `C2660`

**构建结果**：`BUILD SUCCESS`
- DLL 1299968 → **1304576 B**
- md5 **`e7523b7a902735525fbdbec2f89eed05`**，源与部署**一致**
- 备份：4 个 `src/*.bak-20260918-090839`

### 运行时新增判据

```
[MFG] probe RUNS while the menu guard skips DLSS-G: the ladder is calibrated on
      the frame the world is entered (v0.79). step advertised=Nx accepted=Nx latched=0/1
[MFG] probe edge: menu guard released, SetDLSSGOptions resumes on this frame. ...
[MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu guard is not
      engaged (menuBlock=0 frames=N blocked=N unblocked=N) ...
```

---

## §3 v0.80 判决错误（已作废）—— 我造成了新的冻结

> **本节是纠错。v0.80 的"双线程抢 Present ⇒ 要加门闩"是错误设计，
> 而且它的门闩把真正干活的线程拒绝了 300 次，直接造成了 09:31 那次的冻结。**
> 门闩已回退，v0.81 改为纯观察。

### 3.1 我错在哪

v0.79 我观察到"日志里有两个线程 ID"，就直接推断成
**"两个 presenter 在抢一个 swapchain"**。这是**过度推断**：

* 我从未证明这两个线程是**同一角色**（两个生产者）
* 我只证明了它们是**两个不同的 tid**

用户回复 **"还是冻结"**（08:59 的运行）之后，09:31 的运行日志给出了判决。

### 3.2 09:31 运行日志（v0.80 生效）—— 决定性证据

```
[09:31:42.466] [5008 ] [PRESENT] first presenter tid=5008 - this thread owns the swap chain (v0.80)
[09:32:02.266] [18984] [PRESENT] SECOND presenter tid=18984 (owner=5008) - ...
[09:32:02.266] [18984] [PRESENT] LATCH ARMED after 19800 ms: owner=5008 (frames=1), foreign=18984 (frames=1)
[09:32:02.266] [18984] [PRESENT] REFUSED foreign presenter tid=18984 (owner=5008) - skipped 1 frame(s)
...
[09:32:07.199] [18984] [PRESENT] tid census #300: owner=5008 frames=1 | foreign=18984 frames=300 changes=300
```

| 线程 | Present 次数 | 真实角色 | 判定依据 |
|---|---|---|---|
| `5008` | **1**（09:31:42.466，仅初始化那一次） | **插件 / init 线程** —— 跑全部 per-frame 插件逻辑 | 206 行日志；心跳 `serial` 274→484；`[CAM] acc`；`DLSSG diag` |
| `18984` | **300+**（每帧） | **引擎渲染线程** —— 每帧调 Present | 89 行日志，**0 条心跳** |
| `44300` / `19264` | 1 / 4 | watchdog / FrameGen 初始化 | `WATCHDOG started` |

★ **这两个不是"两个竞争的生产者"，而是「init 线程」与「渲染线程」的正常分工。**

### 3.3 冻结是我造成的（自我归因）

```
[MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu guard is
      not engaged (menuBlock=0 frames=0 blocked=270 unblocked=1)
```

* **`unblocked=1`** —— 插帧路径整轮**只跑了 1 次**
* `grep "Present called with SyncInterval"` 全日志**只有 1 次**（`5008`，09:31:42.466）

⇒ **画面停住，是我把每帧真正 Present 的渲染线程拒绝了 300 次，
只留了一个只进过一次 Present 的 init 线程。**

### 3.4 处置

1. `cp src/DX12SwapChain.{h,cpp}.bak-20260918-092612 …` 回退到 v0.79 状态
   * 已核实：v0.80 标记 `ClaimPresentThread` / `REFUSED foreign presenter` / `LATCH ARMED`
     **全部 grep 计数 = 0**；v0.79 的 `ProbeMfgLadder` 完好（+.cpp 2 处）
   * 文件大小回到 `85689` / `10968` B
2. **v0.80 的门闩设计错误根因**：`ClaimPresentThread()` 用
   **"谁先到谁是 owner"** 判定。`5008` 在初始化时先 Present 了 1 次就被锁成 owner；
   `18984` 是之后每帧进来的真渲染线程，被判为"外来者"。
   **"先到"与"是主角"是两件事 —— 这是判据的前提错了。**

---

## §3b v0.81（已构建已部署）：present-thread census —— 只观察，绝不拒绝

**定位**：v0.81 **不修冻结**。它只用来取一条我现在没有的证据 ——
**每个线程各自 Present 了多少帧**。我已连续两轮把根因判错，
在没有这条数据之前不再动行为。

### 实现

`tools/add_v081_present_census.py`（4 处锚点全唯一，花括号增量 0）

**头文件**（`src/DX12SwapChain.h`，CRLF）：

```cpp
// v0.81: std::string is used as a return type by DescribePresentThreads().
#include <string>

static constexpr int kPresentThreadMax = 8;
struct PresentThreadStat {
    std::uint32_t tid = 0;
    std::uint64_t frames = 0;
    long long firstMs = 0;
    long long lastMs = 0;
};
PresentThreadStat presentThreads[kPresentThreadMax]{};
std::atomic<int> presentThreadCount{ 0 };
std::atomic<std::uint64_t> presentCensusFrames{ 0 };
void CensusPresentThread();
std::string DescribePresentThreads();
```

**实现**（`src/DX12SwapChain.cpp`，LF）：热路径第一槽几乎总是命中，无需锁；
只有**没见过的 tid** 才加锁登记，最多 `kPresentThreadMax` 个。

```cpp
void DX12SwapChain::CensusPresentThread()
{
    const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());
    const long long nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
    ++presentCensusFrames;
    const int n = presentThreadCount.load(std::memory_order_acquire);
    for (int i = 0; i < n; ++i) {
        if (presentThreads[i].tid == tid) {
            ++presentThreads[i].frames;
            presentThreads[i].lastMs = nowMs;
            return;
        }
    }
    if (n >= kPresentThreadMax) { /* 打印溢出告警，不再登记 */ return; }
    auto& slot = presentThreads[n];
    slot.tid = tid; slot.frames = 1; slot.firstMs = nowMs; slot.lastMs = nowMs;
    presentThreadCount.store(n + 1, std::memory_order_release);
    if (n == 0) {
        SKSE::log::info("[PRESENT] census: first presenter tid={} - ...", tid);
        return;
    }
    SKSE::log::warn("[PRESENT] census: NEW presenter tid={} - now {} distinct threads "
        "have presented this swap chain. Per-thread frames: {}",
        tid, n + 1, DescribePresentThreads());
}
```

**`Present()` 入口**：只加一行 `CensusPresentThread();`，**没有 return，不碰任何状态**。

### 构建与部署

| 项 | 值 |
|---|---|
| `src/DX12SwapChain.h` | 10968 → **12044 B**（CRLF，`lone_LF=0`） |
| `src/DX12SwapChain.cpp` | 85689 → **88230 B**（LF，`lone_LF=1692` = 全 LF） |
| 构建 | `BUILD SUCCESS`（7/7，一次通过） |
| DLL | 1304576 → **1310208 B**，md5 **`e89889002a4b3333d39dcf2e6f4c7faa`** |
| 部署 | `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/`，源/部署 **md5 一致** |
| 备份 | `src/DX12SwapChain.{h,cpp}.bak-20260918-092612`（= 回退点） |

### v0.81 要看什么

```
[PRESENT] census: first presenter tid=A - this thread ... 
[PRESENT] census: NEW presenter tid=B - now 2 distinct threads have presented ...
          Per-thread frames: tid=A frames=N age=...ms | tid=B frames=M age=...ms
```

**判据**：
* 若 `A` 帧数远大于 `B` ⇒ **A 是主角，上一轮我把角色分配判反了**（大概率）
* 若两者帧数相当 ⇒ 确实有两个 presenter，才谈得上"抢"
* 若只有 1 个 tid ⇒ 双线程这一整条线是伪命题，必须换方向

---

## §3c 尚未修复：当前最强的真根因线索

09:31 日志里三条**跨两个线程都成立**的干净新信号：

| 判据 | 值 | 含义 |
|---|---|---|
| `engPrevZero` | **211** | 引擎的 previous 相机**恒为零矩阵** |
| `prevPos` | `(0.0,0.0,0.0)` 恒为 | 插件侧 previous 位置也恒为零 |
| `clipDev` | `0.000000`（全部样本） | 重投影对齐偏差恒为 0 |
| `curVP / prevVP` | `2.0000 / 1.0000`（**不相等**） | v0.78 里两者恒等，现已解耦 |
| `VERDICT` | `PROBLEM the perFrame buffer carries TWO cameras: accepted 2216 / jump-rejected 3858 (relock 1)` | 插件自己判定 perFrame 缓冲区里混了两套相机 |

⇒ `inv(cur) × prev` 里 `prev` 是零矩阵 ⇒ 重投影矩阵无意义 ⇒
DLSS-G 拿不到有效重投影输入 ⇒ **不产出**（`presented = 1`）。
这与用户感受到的"冻结"（画面停住）方向一致。

**但**：`accepted 2216 / jump-rejected 3858` 仍是**跨线程混流**的产物；
`engPrevZero` 是不是也有跨线程成分，必须先拿到 v0.81 的每线程帧数才能定案。

---

## §4 验证方法

**改完后请这样测（一次到位）：**

1. **开游戏，在主菜单停 20 秒**
   → 新日志应出现 `[MFG] probe RUNS while the menu guard skips DLSS-G`
   → 且这 20 秒内 `MFG probe: runtime ACCEPTED 2x` 已经打出（不再等到进世界）

2. **进世界，走动 30 秒**
   → `DLSSG presented per real frame` 应稳定为 **2**（修复前是 1 或长时间无输出）
   → 心跳 `mult(acc/pres)` 应稳定 `2/2`

3. **贴回 `DynamicShaderFrameGen.log`**
   → 我按线程 ID 分组重跑分析，看 `[FATAL] Present entered from TWO threads` 是否出现

**最重要的单条判据**：

> **`DLSSG presented per real frame` = 2，而不是 1。**
> 修复前全日志 8 条是 1、只有 2 条是 2。

---

## §5 附：本次全部产出清单

| 类型 | 路径 |
|---|---|
| 补丁脚本（INI） | `tools/patch_ini_v078_mfg_ceiling.py` |
| 补丁脚本（阶梯解耦） | `tools/add_v079_ladder_menu_guard.py` |
| 构建产物 | `build/NINJA/DynamicShaderFrameGen.dll`（1304576 B, md5 `e7523b7a…`） |
| 部署 DLL | `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.dll`（同 md5） |
| 部署 INI | `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini`（md5 `23cb5adb…`） |
| 备份 | `src/*.bak-20260918-090839` ×4、`src/*.bak-20260918-090415` ×2、INI `.bak-20260918-090627` ×2 |
| 记忆 | `.workbuddy/memory/2026-09-18.md` |
| 技能 | `~/.workbuddy/skills/framegen-diagnosis/SKILL.md` §99 |
