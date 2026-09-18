# ROOT_CAUSE_ANALYSIS — 冻结问题全面重查

日期：2026-09-18
数据来源：`watchdog.log` 段 #10（07:11:45 → 07:12:35，v0.73 DLL 首次上机）+ `DynamicShaderFrameGen.log`（07:11:32 → 07:12:35）
结论状态：**根因已定案，且与前三轮归因都不同**

---

## 0. 一句话结论

**`fenceValue` 在整段 50 秒运行里恒为 `1`（初值），从未前进过 —— 这意味着 `commandQueue->Signal()` 的值从来没有在 GPU 上被完成过，即 `ExecuteCommandLists()` 提交的命令从未真正执行。**

而同一时间：`frames` 从 1 涨到 1614（约 32 fps）、`silent` 维持在 5–27ms、`focus` 正常。
⇒ **渲染线程在"空转"：每帧都跑完 `Present()`，但 GPU 侧一条命令也没执行，屏幕上是冻结的最后一帧。**

这就是"有声音、画面冻结、不崩溃、不 TDR、CPU 侧看起来还活着"的**完整成因**。

---

## 1. 判决性证据（互相独立的四条）

### 证据 A：`fence=1/1` 恒定 50 秒

看门狗段 #10 全部 252 个 tick，`fence` 字段**每一行都是 `1/1`**：

```
[119402204] 07:11:46.626 frames=1    silent=1755ms  stage=unfocused bypass  focus=0 fence=1/1 stim=1
[119421565] 07:12:05.988 frames=8    silent=17ms    stage=unfocused bypass  focus=0 fence=1/1 stim=97
[119434810] 07:12:19.233 frames=782  silent=4ms     stage=d3d11 Wait         focus=1 fence=1/1 stim=97
[119451063] 07:12:35.486 frames=1614 silent=43ms    stage=d3d11 Wait         focus=1 fence=1/1 stim=97
```

而 `fenceValue` 的定义是：

| 位置 | 代码 |
|---|---|
| `DX12SwapChain.h:137` | `UINT64 fenceValue = 0;` |
| `DX12SwapChain.cpp:282` | `fenceValue = 1;`（`CreateInterop` 里，**只设这一次**） |
| `DX12SwapChain.cpp:1045 / 1192 / 1249` | `fenceValue++;`（每帧一次） |

⇒ **`fence=1` 就是 `CreateInterop` 设的初值。**
`fenceValue++` 确实每帧在跑（否则 `frames` 不会推进到 1614），所以是被读的那根围栏
**从来没有完成到 1 以上**。

### 证据 B：`Signal` 在两条分支里都会执行

我逐行核对了 `Present()` 的控制流 —— 无论 `dlssgOk` 是真是假，`Signal` 都在：

| 分支 | 代码位置 | `Signal` 是否执行 |
|---|---|---|
| `dlssgOk == true` | 1114 → 1155–1157 `Close`+`Execute` → **1184 `Present`** → **1189 `Signal`** → 1191 `d3d11 Wait` | **是** |
| `dlssgOk == false` | 1127–1143 passthrough `CopyResource` → 1155–1157 `Close`+`Execute` → **1184 `Present`** → **1189 `Signal`** | **是** |

⇒ `fence` 恒为 1 **不能**用"某条分支跳过了 Signal"解释。
唯一的解释是 **`commandQueue->Signal()` 排进去的值在 GPU 上永远完不成**，
而它前面的 `ExecuteCommandLists` 同样永远执行不完 —— **GPU 队列没在推进**。

### 证据 C：焦点与旁路的时间线被两处独立仪表对齐

| 墙钟 | 来源 | 内容 |
|---|---|---|
| 07:11:44.868 | 主日志 | `[XRAY] FOCUS lost` |
| 07:11:46.626 | 看门狗 | `stage=unfocused bypass focus=0`，`silent=1755ms` → **stim 开始计数（=1）** |
| **07:12:19.098** | 主日志 | **`[XRAY] FOCUS regained`** |
| **07:12:19.233** | 看门狗 | **`focus` 翻到 1**（两者差 135ms，互相吻合） |
| 07:12:19.098 | 主日志 | `Present called with SyncInterval=1 Flags=0x0` ← **回到正常路径后的第一个 Present** |
| 07:12:19.098 → 07:12:35.486 | 看门狗 | `frames` 782 → 1614，`fence` **仍然恒为 1/1** |

⇒ 旁路持续了 **33 秒**（不是 5 秒），恢复后**又正常跑了 16 秒**，
而 **fence 在这 16 秒里一次也没有前进过**。

### 证据 D：感知层与仪表层完全一致 —— 它"能跑但没画面"

```
07:12:11.908  FPS probe: real=58.0  | DLSSG | ask=2 accepted=0
07:12:27.961  FPS probe: real=57.4  | DLSSG | ask=2 accepted=0
```

- `real=58` fps ⇒ 渲染线程**一点没卡**，帧循环健康；
- `accepted=0` **从头到尾 0** ⇒ DLSS-G **从来没有接受过插帧**；
- 看门狗 `frames` 每秒推进约 50 ⇒ 与 `real=58` 同量级（差值来自旁路期的计数方式）。

⇒ **`Present` 一直返回成功，但呈现的永远是同一帧。** 用户看到的就是"冻住了"。

---

## 2. 之前方案为什么没解决问题

### 2.1 三轮归因全部指向错误的层

| 版本 | 归因 | 实际 |
|---|---|---|
| v0.71 | 失焦 → `Present` 阻塞死锁 | `DO_NOT_WAIT` **拆掉了** `FLIP_DISCARD` 的 CPU 背压（`FLIP_DISCARD`+`BufferCount=3` 下 `Present` 阻塞是唯一刹车，且紧后面就 `Reset` 分配器） |
| v0.72 | 失焦期间不排任何工作 | 失焦链**确实修好了**（26 秒 → 33 秒旁路都正常），**但冻结与失焦无关** —— fence 恒 1 从 `frames=1` 就开始了 |
| v0.73 | 加退出探针，让"卡死 vs 退出"可判定 | 探针**工作正常**（本节数据就是它给的），但**判定完才发现根本没有"退出"这回事** —— 进程一直活着 |

**共同错误：一直在"失焦 / 退出 / 死锁"这条线上找，而这三次都不是。**

### 2.2 为什么前三轮看不到真相

**第一，`stage=` 骗了三轮人。** `m_stage` 是"**最后被写进去的标记**"，不是"卡在哪"。
`Present()` 每帧正常跑完，所以 `stage` 每帧都被刷成一个健康的值（`d3d11 Wait` / `cmdlist Reset`）。
**一个健康的 `stage` 完全掩盖了"GPU 一条命令都没执行"这件事** —— 因为 GPU 状态**没有任何字段反映**。

**第二，`silent` 是好值。** 渲染线程每 20ms 真的在跑 `Present()`，所以 `silent=5~27ms` 再正常不过。
`silent` 只测"渲染线程活不活"，**不测"GPU 活不活"，也不测"画面有没有变"**。

**第三，`fence=` 是 v0.72 才加的字段，而 v0.73 是我第一次拿到它的原始数据。**
前两轮的看门狗行里**没有 `fence=`**（段 #0–#9 全是 `None`）。
⇒ **判决所需的那一个数，前两轮根本不存在。** 我上一轮说"看门狗单靠自己永远分不清"，
**其实是我当时把 `fence=` 放在了会阻塞的线程里（v0.72），以及更早根本没有这个字段。**

### 2.3 我在 v0.73 里犯的一个设计错误（必须记下）

我把 `fence=` 的取值做成"**只在 `silent >= 1500ms` 时才采样**"（`StartGpuSampler`，`636` 行）：

```cpp
if (g_lastSilentMs.load() < 1500)
    continue;   // no suspected hang: stay out of the driver
```

理由是"会阻塞的看门狗不是看门狗"。**这个理由是对的，但触发条件错了** ——
本次故障里 `silent` **永远是好的**（5–27ms），所以采样线程**只在最初那两秒进过驱动一次**
（`stim` 到 97 就永久冻结，`fence` 定格在 `1/1`）。

**⇒ 我是靠"stim 冻结在 97"这个副作用，才知道 `fence=1/1` 是从头到尾的恒定值。**
如果 `silent` 在某一刻恶化，fence 反而会被采样、反而能看到它前进。
**这是运气，不是设计。** 正确做法见 §4.1。

---

## 3. 为什么会走到"GPU 队列不推进"

### 3.1 直接机制

`Present()` 每帧的跨队列链是：

```
d3d11Context->Signal(d3d11Fence, v)      // 1042   D3D11 侧登记"我写完了"
commandQueue->Wait(d3d12Fence, v)        // 1044   D3D12 队列等这个值
...录命令...
commandQueue->ExecuteCommandLists(...)   // 1157
swapChain->Present(0, Flags)             // 1184
commandQueue->Signal(d3d12Fence, v)      // 1189   ← 这个值永远完不成
d3d11Context->Wait(d3d11Fence, v)        // 1191   ← 等它
```

`fence` 恒为 1 说明**整条链的第一个环节就已经断了**：

- 若 `ExecuteCommandLists` 执行了 ⇒ `Signal` 会完成 ⇒ `fence` 会涨到 2、3、4…
- `fence` 始终 1 ⇒ **`ExecuteCommandLists` 提交的包从未被 GPU 取走。**

而 `Present()` 仍然每帧返回成功，是因为：
- `hrPresent` 只检查 `!= DXGI_ERROR_WAS_STILL_DRAWING`（`1185`）；
- **而 `Present` 在没有新内容时本来就返回 `S_OK`** —— 显示的是同一个 backbuffer，
  它自己无法察觉"内容没更新"。

### 3.2 三条候选路径（按可能性排序，附区分方法）

| # | 路径 | 为什么可能 | 怎么证实/否证 |
|---|---|---|---|
| **A** | **`RenderResolutionScale=0.44`（1689x950）与 D3D12 资源尺寸不匹配** | 日志：`Render scale 0.440 -> 1689x950 render / 3840x2160 output`。`colorOutWrapped`/`depthWrapped`/`mvecWrapped` 按 **3840x2160** 建（`339-347`、`364-378`），而 D3D11 侧每帧 `CopyResource(colorOutWrapped, swapChainBufferWrapped)`（`947`）—— **两个都按 swapChainDesc 建，尺寸一致**，但 `CopyDepthToShared` 的 viewport（`460-461`）用 4K 去画 1689x950 的内容。**尺寸链可疑但未证实。** | 打印三个 wrapper 与 `swapChainBuffers[frameIndex]` 的 `GetDesc()` 尺寸，逐帧比对 |
| **B** | **`frameIndex` 与实际 backbuffer 索引脱节** | `frameIndex` 在 `265` 初始化、`860`（旁路）与 `1193`（正常）更新。旁路期间用 `DO_NOT_WAIT` **可能没翻页**，`GetCurrentBackBufferIndex()` 返回旧值 ⇒ 恢复后 `commandAllocators[frameIndex]` 可能仍在**在飞帧**的分配器上 `Reset()`（`1049`）⇒ **这正是 v0.72 警告过的"重置仍在执行的分配器"** | 打印 `frameIndex` vs `GetCurrentBackBufferIndex()` 每帧对比 |
| **C** | **`Present` 静默失败（内容不更新）** | `FLIP_DISCARD` + `ALLOW_TEARING` + `Present(0)` 组合下，若 `DWM` 判定窗口不可呈现，`Present` 返回 `S_OK` 但不翻页 | 记录 `GetLastPresentCount()`（`1435` 已有实现，**从未接线**）每帧是否递增 |

**最重要的一条前置事实**：`fence=1/1` **从 `frames=1`（旁路第一帧）就是 1**，
而**旁路路径根本不碰 fence**（`838-863` 直接 `return S_OK`）。
⇒ **fence 在旁路之前就已经是 1 且不再前进**，即**故障不是旁路造成的**。

### 3.3 这与用户症状的对应

| 用户描述 | 对应机制 |
|---|---|
| "程序存在冻结（卡死、无响应）" | GPU 队列不推进，屏幕停在最后一帧 |
| "有声音" | 引擎主循环、音频线程都正常（渲染线程也确实在跑） |
| "无响应" 但没崩溃 | `Present` 每帧返回 `S_OK`，没有异常抛出，没有 TDR |
| "画面冻结" 而非黑屏 | 最后成功的那一帧留在 backbuffer 上 |

---

## 4. 修复方案

### 4.1 先修仪表（**这一步不做，后面全是猜**）

当前 `fence=` 只在 `silent >= 1500ms` 时采样 —— 本次故障 `silent` 全程正常，采样几乎没跑。
**仪表必须与"疑似卡死"解耦。**

**改法：让采样线程无条件常采样，但用"非阻塞读"取代 `GetCompletedValue()`。**

```cpp
// 关键认识：GetCompletedValue() 在设备挂起时会阻塞，这正是它不能进看门狗的原因。
// 但"每 200ms 采一次"和"卡住时看门狗还能写"是两件事——把采样放独立线程，
// 即使它真的阻塞，看门狗也只是失去 fence 数据，不会失去自己的心跳。
// 所以正确设计是：常采样 + 独立线程 + 不加 silent 门槛。
std::thread([this]() {
    for (;;) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        const unsigned long long f11 = d3d11Fence ? d3d11Fence->GetCompletedValue() : ~0ull;
        const unsigned long long f12 = d3d12Fence ? d3d12Fence->GetCompletedValue() : ~0ull;
        g_hangFence11.store(f11);
        g_hangFence12.store(f12);
        g_samplerTicks.fetch_add(1);          // 这个也可能停——那本身就是 GPU 挂起的信息
    }
}).detach();
```

代价：常驻一个 200ms 的线程读驱动。可接受 —— 它在自己的线程里，阻塞不影响看门狗。

**同时新增三个字段（这次要一次性加够）：**

| 字段 | 取法 | 判什么 |
|---|---|---|
| `fidx=` | `frameIndex` 与 `swapChain->GetCurrentBackBufferIndex()` | 两者不等 = 旁路期翻页脱节（路径 B） |
| `lastPr=` | `swapChain->GetLastPresentCount()` | 不涨 = `Present` 静默失败（路径 C） |
| `queued=` | 自己维护的"已提交未完成帧数"（`ExecuteCommandLists` 时 +1，`fence` 完成到该值时 −1） | **>3 就是队列真的排满了**（背压失控的直接证据） |

### 4.2 修真正的故障：`Reset` 分配器的前置条件

不管路径 A/B/C 哪条成立，**`commandAllocators[frameIndex]->Reset()`（`1049`）都有一个硬性前置条件：
该分配器上所有命令必须已经执行完毕。当前代码只靠"`fence` 等待"来保证，而 `fence` 一旦失效就完全失控。**

**改法：Reset 前显式检查，把"假设"变成"检查"。**

```cpp
// 分配器复用必须自证：这个 frameIndex 的上一轮工作确实完成了。
// 当前靠 fenceValue 等待，但如果 Signal 侧出问题，等待会静默失效。
const UINT64 completed = d3d12Fence->GetCompletedValue();
if (completed + 1 < fenceValue) {
    // GPU 还没追上：宁可等一次，也不要 Reset 一个在飞的分配器
    m_stage = "allocator reuse wait";
    if (d3d12Fence->SetEventOnCompletion(fenceValue - 1, h)) {
        ::WaitForSingleObject(h, 100);   // 有上限：等不到就当故障上报，不无限等
    }
}
```

`WaitForSingleObject` **必须带上限**，否则就是把 v0.71 的"无限等"换成另一个无限等。

### 4.3 恢复 `Present` 的背压（撤销 v0.71 的破坏）

`Present` 的阻塞是 `FLIP_DISCARD`+`BufferCount=3` 下**唯一的 CPU 背压**。
v0.72 只在**旁路路径**保留了 `DO_NOT_WAIT`（`843-844`）—— 这个位置是**可以接受的**（旁路路径下游什么都不依赖）。
但 `hlPresent`（`1184`）与 `hrPresentFsr`（`1239`）的**普通阻塞必须保留**（v0.72 已恢复，确认勿再改）。

**新增一条**：`Present` 返回后**核对背压是否还活着** ——

```cpp
// 如果 Present 不再阻塞，CPU 就会跑到 GPU 前面去，队列深度会失控。
// 用"已提交未完成帧数"做哨兵（4.1 的 queued=）。
if (queuedDepth > 3) {
    SKSE::log::warn("[XRAY] present backpressure LOST: {} frames queued but unfinished "
                    "(GPU timeline fence={})", queuedDepth, completed);
}
```

### 4.4 修复优先级

| 顺序 | 动作 | 理由 |
|---|---|---|
| **1** | **4.1 仪表常采样 + 三新字段** | **不知道 `queued` 和 `fidx` 是多少，4.2/4.3 就是盲改** |
| 2 | 4.2 Reset 前置检查 + 有上限等待 | 消除"Reset 在飞分配器"这个确定性缺陷 |
| 3 | 4.3 背压哨兵 | 把"背压失效"变成一条日志 |
| 4 | §3.2 路径 A/B/C 逐条证实后针对性修 | 前三步拿到数据后再做 |

**不要跳过第 1 步。** 前三轮的教训就是"在弱证据上动手"（技能 §74）。
这次新仪表上机一次，`fidx=` 与 `queued=` 会直接把 A/B/C 收窄到一条。

---

## 5. 修复后如何验证"冻结问题已彻底解决"

### 5.1 判据（必须全部满足）

| # | 字段 | 期望 | 含义 |
|---|---|---|---|
| 1 | `fence=` | **随 `frames` 单调递增**（不再恒定） | GPU 队列在推进 —— **这是本次的根因判据** |
| 2 | `queued=` | 稳定在 **≤3** | 背压正常，CPU 没跑到 GPU 前面 |
| 3 | `fidx=` | 恢复后 `frameIndex == GetCurrentBackBufferIndex()` | 旁路期翻页没脱节 |
| 4 | `lastPr=` | 每次 `Present` 后**递增** | `Present` 真的在翻页，不是静默成功 |
| 5 | `accepted=` | **> 0** | DLSS-G 真的接受了插帧（不再恒 0） |
| 6 | `silent=` | 全程 `< 150ms` | 帧循环没有停 |
| 7 | `STALL` | 本次运行段 **= 0** | 看门狗没报过卡死 |
| 8 | `0c.` | 有 `[exit]` 行 | 进程从 loader 正常退出 |

### 5.2 验证步骤（照做，别改）

1. **进世界，正常走动 20 秒** —— 观察 `real=` 与 `cap~=` 是否接近（接近 = 插帧生效）。
2. **Alt+Tab 出去 5 秒再回来** —— 观察 `FOCUS lost` / `FOCUS regained` 是否成对，
   以及**恢复后 `fence=` 是否继续递增**（这一条最关键：当前故障正是"恢复后 fence 仍不动"）。
3. **再走动 10 秒**，**故意在菜单里停 10 秒**（触发 `menuBlock` 路径）。
4. **用游戏菜单正常退出** → `read_log.bat`。
5. 把 `0b.` 段的运行段表发我。

### 5.3 "彻底解决"的判定标准

**不是"这次没卡"。** 判定标准是：

- **§5.1 的 8 条判据全部满足**，且
- **连续 3 次运行**（含至少 1 次"失焦 30 秒以上再回来"、1 次"菜单停留 + 快速移动"）都满足，且
- **`fence=` 在三段运行里都单调递增**。

只满足一次不足以说明 —— 本次故障的表现是"能跑 50 秒完全看不出问题"，
**单次通过可能只是恰好没触发那条路径。**

---

## 6. 诚实边界

1. **我已定案的是**：`fence` 恒为 `1`、GPU 队列不推进、渲染线程空转、画面冻结。
   这四条有直接读数支撑。
2. **我未定案的是**：**为什么** GPU 队列不推进（§3.2 的 A/B/C）。
   现有字段不足以区分 —— **这正是 §4.1 要先修仪表的原因**。
3. **§4.2/4.3 是"消除确定性缺陷"的改动，不是"针对根因"的改动。**
   它们即使全部落地也可能不解决冻结；但它们是**已知的、独立的、必须修的缺陷**。
4. **前三轮的补丁（v0.71/v0.72/v0.73）中，只有 v0.71 是有害的**（已由 v0.72 回退），
   v0.72 的旁路与 v0.73 的探针**都是有效的**，本轮数据全靠它们才拿到。
   **这不是"前三轮全白做"，而是"前三轮修的不是这个病"。**
5. **`TdrDelay=30` 仍是 30**：GPU 若真挂起，头 30 秒不留系统痕迹。
   `fence` 恒定恰好是**绕过 TDR 才能看到**的那类证据。
6. **加载画面闪烁**（v0.63–v0.70 老问题）与本次冻结**是两件事**，本轮完全未触及。
