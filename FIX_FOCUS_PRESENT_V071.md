# fix: 失焦（Alt+Tab）→ Present 死锁 — v0.71

日期：2026-09-17
触发场景：进世界成功（v0.69/v0.70 修复到位），但**画面冻结、声音继续**。
结论：这不是"闪"，是**交换链在窗口失去前台时 `Present()` 永久阻塞**。本插件在此之前**全工程一处焦点处理都没有**。

---

## 1. 证据链（全部来自日志与系统记录，不靠现象描述）

### 1.1 冻结时刻 == 失焦时刻

| 时刻 | 文件 | 最后一行 / 事件 |
|---|---|---|
| 23:40:22.221 | `DirectionalMovement.log` | `[DMK] WM_ACTIVATEAPP: Game lost focus. Clearing inputs.` ← **全日志语料的最后一行** |
| 23:40:22.166 | `ShadowLimitFix.log` | 逐帧日志停止（早 55 ms） |
| 23:40:22.09x | `DynamicShaderFrameGen.log` | 心跳 `serial=1504` 停止 |
| 23:40:21 | `DynamicShaderFrameGen.watchdog.log` | 最后一个 tick |
| 23:40:21.918 | `DynamicSnow.log` | 停止 |

同刻 `LeftAlt` 从 1 变 0 —— 一次 Alt+Tab 的落点。

**判别关键**：这五个日志器分属**五个互不相干的插件 / 线程 / 文件**（三个是别人写的插件，两个是本插件主线程 + 看门狗线程）。它们在同一秒停摆 ⇒ **停的是整个帧循环，不是某一个插件出问题**。跨插件日志的 mtime 是手边最便宜的"进程级探针"。

### 1.2 排除项（都查了，都不是）

| 可能 | 查法 | 结果 |
|---|---|---|
| 崩溃 | `CrashLogger.log` | 只有启动 5 行，无崩溃记录 |
| 挂起进程 | WER `ReportArchive` / `ReportQueue` | 只有 20:19 的系统更新项，本时段无 |
| GPU 复位 | 事件日志 `Display` 提供商 | 只有 id=4125 自动 HDR 提示，**无 4101/4102（TDR）** |
| 设备丢失 | 插件日志 | 无 `DXGI_ERROR_DEVICE_REMOVED` |
| 双线程并发 Present | 心跳行 `tid=` | 世界阶段全为单线程 `31204`，`serial` 增速 == 真实帧率 |

### 1.3 机理

```
交换链：DXGI_SWAP_EFFECT_FLIP_DISCARD + BufferCount=3
Present： Present(0, Flags)   ← 没有 DXGI_PRESENT_DO_NOT_WAIT
```

翻页模型下 `Present` 会**阻塞**，直到一个已排队的缓冲被释放；
而 DXGI 对一个**被遮挡 / 后台**的窗口会**停止释放缓冲** ⇒ `Present` 永不返回 ⇒ 渲染线程卡死，音频线程照常跑（**有声音、画面冻结**）。

MFG 4x 让这件事变成"一失焦就死"而不是"晚一点死"：每真实帧交 **4 帧**给 **3 深**队列，本来就贴着"队列满"的边缘，失焦后下一个 `Present` 立刻楔死。

---

## 2. 改动清单（v0.71 / 071b / 071c / 071d）

| 文件 | 处 | 改动 |
|---|---|---|
| `src/DX12SwapChain.cpp` | D1 | `FocusAllowsPresenting()` 助手 + `g_lastFocus` / `g_focusOffSent` 全局 |
| `src/DX12SwapChain.cpp` | D2 | 每帧焦点采样（**在守卫之前**）+ 失焦边沿发一次 `SetDLSSGOptions(..., false)` |
| `src/DX12SwapChain.cpp` | D3 | 看门狗 tick 1000 ms → **200 ms** |
| `src/DX12SwapChain.cpp` | D4 | 看门狗行新增 `focus=` 字段 |
| `src/DX12SwapChain.cpp` | D5 | 守卫吃焦点：`menuBlock || focusBlock` 同级直通，并清 `dlssgFailCount` |
| `src/DX12SwapChain.cpp` | D6/D7 | 两处 `Present` 失焦时带 `DXGI_PRESENT_DO_NOT_WAIT` |
| `src/Streamline.h` | H1 | `SetDLSSGOptions(..., bool a_enable = true)` |
| `src/Streamline.cpp` | C1 | `a_enable == false` 的早返回停机路径 |

要点：

* **失焦时给运行时停机是 DLSS-G 的硬性要求** —— 不停机的话它还在往交换链里交帧。
* **停机顺手清 `dlssgFailCount`**：否则一次长 alt-tab 会被自动禁用计数器误判成"插帧失败 N 次"而关掉。
* **`DXGI_ERROR_WAS_STILL_DRAWING` 当"这帧没显示"，不是失败** —— 不能进 `ThrowIfFailed`。
* **`focus=` 采样必须在守卫之前**，否则守卫改变了执行路径，采到的是被守卫影响过的状态。

### 2.1 版本号后缀的三次修正（都是编译期抓到的）

* **071b**：`GetForegroundWindow() == hwnd` 在包装窗口下**永远为假** ⇒ 必须比 **根窗口** `GetAncestor(h, GA_ROOT)`；`GetForegroundWindow() == nullptr`（锁屏/模式切换）按"前台"处理，避免瞬时状态静默关掉插帧。
* **071c**：`DXGI_SWAP_CHAIN_DESC1` **没有** `OutputWindow`（那是旧版 `DXGI_SWAP_CHAIN_DESC` 的成员），改用 `swapChain->GetHwnd()`。
* **071d**：`IDXGISwapChain1::GetHwnd()` 是**出参 + HRESULT**，不是属性 getter（`C2660`）。

---

## 3. 构建 / 部署校验

| 项 | 值 |
|---|---|
| 构建 | `BUILD SUCCESS`，**零告警** |
| DLL | `1292288 B`，md5 `6f377cd8241b2ec170f847a004be6c82` |
| 部署 | `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/` md5 **一致**（POST_BUILD 已同步） |
| 源码 md5 | `DX12SwapChain.cpp 8b1008004acda6978a6153459be0da17` / `Streamline.cpp 97d311154abfd7a79482b8acb421a9dd` / `Streamline.h 4c4a8c1fc93da847c873c2e2ec0f3719` |
| 备份 | `src/*.bak-20260917-234942`（v0.71 前）、`.bak-20260917-235057`（071b 前）、`.bak-20260917-235544`（071c 前） |

---

## 4. 下跑验收（**验收，不是试错**）

```bat
REM 1. 进世界
REM 2. 走动 + 转视角 20 秒
REM 3. Alt+Tab 切出去，停 5 秒
REM 4. 切回来，再走 10 秒
REM 5. 退出游戏
read_log.bat
```

只看四件事：

| # | 期望 | 说明 |
|---|---|---|
| 1 | **Alt+Tab 切回来后还能继续玩** | 主验收项。之前是切出去就永久冻结 |
| 2 | 日志出现 `[XRAY] FOCUS lost` / `[XRAY] FOCUS regained` | 焦点采样通了 |
| 3 | 出现 `[XRAY] DLSSG mode -> OFF` | 失焦时确实给运行时打了停机 |
| 4 | 切回后心跳 `mult(acc/pres)` 恢复 `4/4` | 插帧自动回来 |

看门狗文件应出现 `focus=0` 的行，且**没有** `RENDER THREAD STALLED`。

顺带（v0.69/v0.70 的验收项一直没做，可一并看）：加载画面是否还闪、`DLSSNR suppressed` 是否出现、`MENU EDGE` 是否成对。

---

## 5. 诚实边界（未定案，别当成已解决）

1. **本次没有 STALLED 行**：看门狗在线程上是独立的，若渲染线程真的永久卡在 `Present`，它应该在 1.5 秒后打出 `RENDER THREAD STALLED`。它没有 —— 因为看门狗自己也在同一秒停了。两种情况都符合现有数据：
   (a) 挂死后 1.5 秒内进程就结束了；
   (b) 整个进程停了（含被手动结束）。
   **这正是 `focus=` 字段要解决的**：下一跑若"看门狗还在 tick 且 `focus=0` 且打出了 STALLED"，就是 (a) 的铁证。
2. 也不能 100% 排除"用户在失焦后从任务管理器结束了进程"，而 spdlog 尾部缓冲把最后的日志吞掉（本工程历史上发生过一次）。但五日志同秒停摆 + 看门狗（自带 `fflush`）也停 + 无 WER/TDR，共同指向失焦即停。
3. `dvd(ok/used)=0/0 err=16` 三字段互相矛盾，是残值，未清。
4. 插件侧 `countedFrameIndex` 与每帧 5 次 `slSetConstants` 的同步性未查（本跑单线程，风险下降但未排除）。
5. 菜单直通路径仍在 `menuBlock` 判定**之前**发 PCL 模拟区间 marker。
6. `engineMvec=false`（引擎运动矢量纹理取不到）依旧存在，插帧只能靠相机重投影。

---

## 6. 附带的读取器修复（v0.71 / v0.71e）

* `tools/patch_reader_v071.py`：`WD_RE` 增加**可选** `focus=` 组（旧 build 的行必须仍能解析，否则按帧号回退切分运行段会丢历史 —— 解析器不匹配是**静默**的）；新增 `part_focus()` 与 **"4c. 焦点 / Present 死锁（v0.71）"** 段，含跨插件日志 mtime 交叉验证。
* `tools/fix_reader_uicheck_v071e.py`：**修掉一个假判据**。旧写法
  ```python
  if "ui=0" in raw or "ui=0x0" in raw:      # ← 子串判定
  ```
  `"ui=0"` 是 `"ui=0x7ff745c3ceb0"` 的**前缀**，于是每次正常运行都被报成
  「RE::UI 单例为空 → 菜单检测整体失效，这是 CommonLib 地址/版本问题」，
  还会进总结。改成按数值判（`int(value, 0) == 0`），并补一行 `RE::UI 单例有效`。
  **通则：金丝雀要写真实损伤特征，别写会撞上健康输出的子串。**

---

## 7. 本轮顺手结清的旧悬案

* **`menuOpen=0` 是真的没菜单**，不是探针坏：`MENU PROBE` 里 `mainMenu` / `loadingMenu` / `journalMenu` 三个指针**两两与字面名指针相等** ⇒ InterfaceStrings 布局正确。
* **v0.69 / v0.70 确认生效**：`[FrameGen] DLSSNR suppressed: frame generation is active` 出现且全程无 `[DLSSNR] frames=` 增长；`menu=1200 edges=2 resetTrue=1`；`MENU EDGE open=1 / open=0` 各一次；`RUN TIME 2026-09-17 23:39:12` 与 `RUN START` 的构建时间戳 `Sep 17 2026 23:32:07` 分离成功。
* **"双线程并发 Present"不成立**：世界阶段全部单线程。
* `frozen` 计数涨（71→101）是"引擎 `prevViewProj` 冻结"计数（`engPrevEqCur` 常态），**不是卡死信号**。
* `det(inv(cur)×prev)==1` 是 `cur==prev` 时的恒等式，不是缺陷信号；本跑 `det(min/max)=0.011/3.187` 只在世界阶段出现，且 `clipDevMax` 同时从 0.0488 涨到 0.3859 ⇒ 与"两组相机"无关。
