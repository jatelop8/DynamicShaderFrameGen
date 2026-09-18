# FIX_NRFG_V070_2332 —— 加载画面闪烁：NR×帧生成串联 + 菜单守卫不可观测

构建：2026-09-17 23:32　DLL md5 `21ce1ab2444c17fa55cfd2ebf7da6a14`（1290240 B，已同步到 mod 目录）
基线日志：2026-09-17 23:07–23:08 运行（**v0.68** DLL，22:59 构建），3222 行
本文回答用户原话：**"我看到帧数好像变多了，27变成107了，但是进不去游戏，卡在加载画面闪烁"**

---

## 0. 一句话结论

- **27 → 107 是真的**，而且是正确的技术结果：`real=36.6ms`（27 fps）× `mult(acc/pres)=4/4` ≈ 107 fps。
  v0.63 的 pacing 修复成立，4x MFG 确实在输出。**不要回退它。**
- **"加载画面闪"的第一顺位成因是 DLSSNR 与帧生成串联**：两个 temporal 处理器为同一帧写历史。
  v0.42 在 `ImguiMenu.cpp:373` 亲手写下退路"若叠加闪烁再回退互斥" —— 本次就是那个情形，已验证并回退互斥。
- **本该拦住它的 `MenuDisableFrameGen=1` 从未生效，而原因是结构性的**：菜单状态在它自己的下游被采样
  （只在 `EvaluateDLSSG` 里算，而守卫恰恰跳过 `EvaluateDLSSG`）。所以 `menu=0` 这个数**不能**读作
  "没检测到菜单" —— 它同样可以是"计数器根本没跑"。v0.70 把采样提到守卫之前。

---

## 1. 证据（全部来自这份日志，可直接复核）

| # | 观测 | 数值 | 含义 |
|---|---|---|---|
| 1 | `[FrameGen] DLSSNR: … frames=` | 179 → 359 → 539 → 719（≈11 秒） | NR 以 **~65 次/秒**在 3840×2160 全分辨率上评估 |
| 2 | `[DLSSNR] D3D12 command contexts saturated` | x1 | NR 与 FG 争抢 D3D12 上下文，NR 侧被迫 CPU 背压 |
| 3 | INI `NeuralRenderingEnabled=1` **且** `FrameGeneration=1` | 同时为 1 | v0.42 的串联覆盖了设计意图；`FrameGen.h:105` 的注释仍写"与帧生成互斥" |
| 4 | `DLSSG presented per real frame` 序列 | 8 帧 `1` 建立 pacer → 之后**恒** `4` | **倍率稳定**，闪不是 pacing 造成的（排除一条） |
| 5 | `real=36.6ms`、`mult(acc/pres)=4/4`、`presented all=0/8/0/0/25/…` | — | 帧生成确实在跑；用户看到的 107 由此而来 |
| 6 | 心跳 1（serial=670）`consts ok=0 fail=0`、`presented all=0/3/…`、`real=0.00ms` | — | 前 ~667 帧 DLSS-G 一个常量都没收到，`EvaluateDLSSG` 还没开始跑 |
| 7 | `menu=0 world=1 → 151`、`menuEdges=0`、`menuOpen=0` | 全程 | **计数器结构性失效**（见根因 2），不可作为"没开菜单"的证据 |
| 8 | `[CAM] acc` 位置：世界相机 `(-243.048859,-415.314819,118.623505)` | 6 个窗口几乎不动 | 这 5.6 秒是**相机冻住的加载/淡入阶段**，不是可玩状态 |
| 9 | `frozen`（引擎 viewProj 连续不变帧数） | 29 → 59 → 66 → 66 → 82 | 与 #8 一致：相机确实静止 |
| 10 | `[MOTION] clipToPrev rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1]` | 单位矩阵 | 交给 DLSS-G 的重投影矩阵是单位矩阵 —— 在相机静止时这是**正确值** |
| 11 | `dvd(ok/used)=0/0 err=16` | — | DERIVED 源已（在 v0.69）关掉；`err=16` 是残值 |

### 1.1 三条被本轮推翻的旧读法（诚实纠正）

| 旧结论 | 为什么错 |
|---|---|
| "`det(inv(cur)×prev)` 恒 1 ⇒ 两组相机" | `det==1` 在 `cur==prev` 时是**恒等式**，单位矩阵与真实两帧投影都满足 ⇒ det **不是**有效区分器。实测 `detGuard=0`（守卫从未触发）。已修读取器措辞。 |
| "`clipDevMax=0` ⇒ 相机项被丢" | 必须先证明"相机在动"。本跑相机在仪表启动期间**从未连续运动** ⇒ 单位矩阵是正确结果。已修读取器 + 新建 `diag_camwindows.py`。 |
| "`[CAM] JUMP` 拒绝 2862 次 ⇒ perFrame 缓冲携带两组相机" | 被拒的是**常量桩**（菜单背景相机 `(-50,600,80)` / UI 正交相机 `(-160,160,128)` / 无平移遗留矩阵 `(0,0,1)`），它们与真实相机**交错**出现；被**接受**的快照是连续的。闸门正在正常工作。 |

### 1.2 一条被排除的误判

| 现象 | 正确读法 |
|---|---|
| Transfusion `[MOTION] … mv3D=0 dilatedGame=0` | **设计如此，不是缺陷。** 插件把 mvec 当**纹理参数**传给 `slEvaluateDLSSG`（`DX12SwapChain.cpp:912` 传 `mvecWrapped`），没有走 `sl::Constants::motionVectors3D`（源码里从未设置该字段）⇒ 那行必然读到 0。判定运动矢量要认 `engineMvec` / `mvecWrapped`；实测 NR 自己报 `engineMvec=true`。 |

---

## 2. 根因与改动

### 根因 1（v0.69 已修）：NR × 帧生成串联

**机理**：NR 是 temporal 处理器（有自己的历史与累积），DLSS-G 也是。两者串联时同一帧被写两份历史，
且 NR 以 ~65 Hz 更新而真实帧只有 27 Hz ⇒ NR 的历史节奏与 FG 期望的节奏不一致 ⇒ 生成帧与真实帧
在"锐/噪/位移"上交替 ⇒ **闪烁**。静止场景掩盖它（两份历史一致，所以主菜单看着没事），一有变化就暴露。

**改动**（`DX12SwapChain.cpp`）：
```cpp
const bool fgGeneratingNow =
    dlssgMode && fg.settings.frameGeneration && fg.fgActive.load();
if (fg.settings.neuralRenderingEnabled && fgGeneratingNow) {   // 新增抑制块 + 一次性 warn
    ...
}
if (fg.settings.neuralRenderingEnabled && !fgGeneratingNow) {  // 原条件加 !fgGeneratingNow
    ... NR Apply ...
}
```
依据是 v0.42 自己留下的退路。Toggle 键（`0xC7`）关掉 FG 即 NR 立刻回来，不需要第二个开关。

### 根因 2（v0.70 已修）：菜单守卫不可观测 —— 采样落在自己的下游

**机理链**：`isMenuOpen` 原本在 `CheckFrameConstants()` 内计算 → `CheckFrameConstants()` 只被
`EvaluateDLSSG()` 调用（`Streamline.cpp:1229`）→ 而 `menuBlock`（`DX12SwapChain.cpp:896`）**恰恰
不调用** `EvaluateDLSSG`。于是在守卫生效的每一帧：`menuOpenNow`、`menuFrames`、`menuEdges`、
以及"进菜单时丢一次历史"的 reset 边沿**全部不更新**。
⇒ 守卫无法自证，且 reset 边沿在它最该生效的那一帧永远不会触发。

**改动**：
- `Streamline.cpp/.h`：新增 `PollMenuState()`（每帧采样一次，更新计数与边沿，置 `menuResetPending`）
  与 `MenuIsOpen()`（读缓存的 `diag.menuOpenNow`）。`CheckFrameConstants` 改成读缓存，不再自行计算，
  并通过 `menuResetPending` 消费 reset 边沿。
- `DX12SwapChain.cpp`：在算 `menuBlock` **之前**调用 `fg.streamline.PollMenuState()`；
  `menuBlock` 改用 `MenuIsOpen()`。守卫与诊断自此共享同一个采样值。
- 顺带修 `ProbeMenuNamesOnce()` 的静默失败：`if (!ui || !is) return;` 原本在 `done = true` **之前**，
  单例为空时探针**一个字都不打印** ⇒ 无法与"探针没跑到"区分。现在先置 `done` 并明确报出哪个为空。

### 同批（v0.69，仪表/降噪）

| 文件 | 改动 | 理由 |
|---|---|---|
| `Streamline.cpp` | `useDerived = false && (…)` | DERIVED 源 `inv(CameraViewInverse) × CameraProjUnjittered` **按构造就错**：实测 `inv(VI)` 的平移行 = `(0,0,0,1)`、平移列 = `(0,0,0)`（`CameraViewInverse` 不含平移），九种乘法约定最优残差 14.93 而 `VP` 最大元素仅 15.0028（误差 99%）。它唯一的触发条件是"引擎 cur 冻结 ≥30 帧"，而冻结正是加载画面的正常状态 ⇒ 会把"没有运动"伪造成运动。 |
| `FrameGen.cpp` | `[CAM] JUMP` 日志节流（前 3 条 + 每 250 条） | 本次日志 3222 行里 3111 行是自己的埋点在刷屏，压掉了真正要看的行。总量仍在心跳里。 |
| `main.cpp` | 新增真实 `[XRAY] RUN TIME` | `RUN START` 打的是 `__DATE__/__TIME__` 即**构建时间戳**，已两次误导时间线还原（23:07 那次看着像 22:59 开始）。 |
| `tools/read_xray_log.py` | ①"多线程并发"判据改为**两方各自 >10**（原来只看 b 的次数，把 `a=1 / b=150` 这种"一次性交接 + 持续线程"误报成并发）；②"两组相机"措辞改为"常量桩与真实相机交错"；③det 判据改为**恒等式**说明；④新增 **4b 段**：NR 互斥是否生效 / `engineMvec` 正确读法 / MENU PROBE 指针比对 / MENU EDGE / RUN TIME。 |
| `tools/diag_camwindows.py`（新建） | 逐心跳窗口交叉引用 `clipDevMax` 与相机位移，并**先验证前提**：① 位移是否"连续"（单步分解，把加载瞬移判为"跳变"）；② `hist(hit)` 是否 >0（0 表示仪表没启动，`clipDevMax=0` 说明不了任何事） | 不加这两条前提，第一个窗口（横跨 serial 1..670 的启动期）**永远**会被报成"相机在动而矩阵是单位矩阵 = BUG"。这正是前两轮误判的机制。 |

---

## 3. 下跑验收（这次是**验收**，不是试错）

玩法：主菜单停 5 秒 → 回车进世界 → **持续走动 + 转视角 20 秒**（关键：必须连续动，站着不动这一项永远采不到样本）→ 退出 → 跑 `read_log.bat`。

| # | 看哪里 | 期望 | 若不符说明什么 |
|---|---|---|---|
| 1 | `[FrameGen] DLSSNR suppressed` 是否出现 | **出现** | 根因 1 未生效（DLL 没换 / `fgActive` 没置位） |
| 2 | `[DLSSNR] frames=` 是否还在涨 | **不再出现或不再增长** | 同上 |
| 3 | 心跳 `real=` | 回到 ~35–55ms 区间且**画面不闪** | 若仍闪则闪另有来源 |
| 4 | `[XRAY] MENU PROBE` 一行的 `ptr mainMenu=` 与 `lit=` | **指针相等** ⇒ 布局正确 | 不相等 ⇒ `InterfaceStrings` 布局不匹配（字面名那一半仍有效） |
| 5 | `[XRAY] MENU EDGE` 行数 | **>0**（进出菜单各一次） | 为 0 且 #4 指针相等 ⇒ **真的没有菜单打开**，那是游戏状态事实 |
| 6 | 心跳 `menu=` / `world=` | 主菜单/加载期 `menu` 增长 | 仍是 `menu=0 world=N` ⇒ 守卫还是没看到菜单 |
| 7 | 心跳 `presented menu=…` vs `presented world=…` | 菜单期 menu 塌到 `1`，世界期 world 保持 `4` | 这是守卫**直接生效**的证据（守卫期间不插帧） |
| 8 | `[MOTION] clipToPrev rows` | 走动时应**不再**是单位矩阵 | 若走动中仍是单位矩阵 ⇒ 相机项真的坏了，转去查重投影取源 |
| 9 | `[XRAY] RUN TIME` | 出现，且与 `RUN START` 的构建时间戳**不同** | 未出现 ⇒ DLL 还是 v0.68 |
| 10 | `diag_camwindows.py` 的结论行 | 出现"每个「相机连续在动」的窗口 clipDevMax 都 > 0" | 出现"严重"⇒ 相机项缺陷定案 |

---

## 4. 未定案（不许当成已修）

| 项 | 现状 | 缺什么才能定案 |
|---|---|---|
| **相机项到底对不对** | **未采样**。本跑相机在仪表启动期间从未连续运动（`diag_camwindows.py`：跳过 1 窗，其余 5 窗"静止"或"跳变"） | 下跑**持续走动** 20 秒，看窗口成为"连续" |
| `dvd(ok/used)=0/0 err=16` 三字段自相矛盾 | `checked=0` 却说 `err=16`（残值） | DERIVED 已关，暂不影响；若要干净应把 `derivedMatchErr` 一并清位 |
| 插件侧 `countedFrameIndex` 与 DLSS-G 每帧 5 次 `slSetConstants` 不同步 | 未查 | 需要一个"把插件索引与 `slGetNewFrameToken` 回传值对照打印"的仪表 |
| 两个线程共享 frame token × `frameSerial` 单线程递增 | 实测 `tid(a/b/c)=0x37e0/0x4968/0x0 calls=1/150/0` ⇒ 是**一次性交接 + 持续线程**，不是并发 | 交接发生在初始化期，风险窗口 = 启动首帧；如需排除要打 token 指针 |
| 菜单直通路径仍发 PCL 模拟区间 marker（`DX12SwapChain.cpp:883-884` 在 `menuBlock` 判定之前） | 未查 | 若菜单期出现 RSYNC 抖动，先查这里 |
| `[DLSSNR] D3D12 command contexts saturated` | 随根因 1 应消失 | 下跑确认 |

---

## 5. 回滚

```bash
cd D:/Modding/DynamicShaderFrameGen/src
# v0.70 之前的备份
cp Streamline.h.bak-20260917-233143 Streamline.h
cp Streamline.cpp.bak-20260917-233143 Streamline.cpp
cp DX12SwapChain.cpp.bak-20260917-233143 DX12SwapChain.cpp
# v0.69 之前的备份（如需退回 v0.68 行为）
# Streamline.cpp.bak-20260917-231935 / DX12SwapChain.cpp.bak-20260917-231935
# FrameGen.cpp.bak-20260917-231935 / main.cpp.bak-20260917-231935
bash build_vs.sh
```
补丁脚本：`tools/add_xray_v070.py`（默认干跑，`--apply` 落盘，幂等 marker + 锚点唯一 + brace 平衡 + 行尾自适应）。

> 注意：构建的 POST_BUILD 会把 `SKSE/Plugins/DynamicShaderFrameGen.ini` 覆盖到 mod 目录（`copy_if_different`）。
> 要长期生效就改**源 INI**；只做一次 A/B 才改部署副本，且中间不要重新编译。
> 运行期间不要编译。
