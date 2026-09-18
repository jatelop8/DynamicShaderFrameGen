# FIX_RESET_2123 — 主菜单持续闪：`reset` 每帧被置位

**日期**：2026-09-17 21:23
**版本**：v0.58 → **v0.59**
**产物**：`115876a0e4c441ae6cd00a3f50a5ce30`（1227264 B）
**部署**：`E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.dll`
（构建产物与部署副本 md5 一致，POST_BUILD 自动部署生效）

---

## 1. 症状

主菜单停着不动也**一直闪**；按回车能进游戏，进游戏后左上角 FPS 数字才开始动。

---

## 2. 证据链（全部来自本机实测，无推断）

### 2.1 v0.58 的修复生效了（先排除）

`DLSSG-Transfusion_perf.csv` / `DynamicShaderFrameGen.log`：

```
[21:18:33.814] [Streamline] constants: ok=120 fail=0 lastR=0 serial=123 token=0x...
[21:18:36.911] [Streamline] constants: ok=240 fail=0 lastR=0 serial=243 token=0x...
[21:18:45.010] [Streamline] constants: ok=360 fail=0 lastR=0 serial=363 token=0x...
```

- `ok` 每 120 帧稳定递增、`fail=0`、`serial` 持续增长
- 旧的 `slSetConstants failed: 27`（`eErrorDuplicatedConstants`）**出现 0 次**（对比 21:05 那次每 26ms 刷一次）

⇒ 帧令牌停滞已修复。**闪与 27 号错误无关**，是另一个原因。

### 2.2 Transfusion 抓到 `reset` 每帧为 1

`DLSSG-Transfusion.log`：

```
[MOTION] route=slSetConstants call=0 viewport=0 transforms=game-preserved
  clipToPrev=identity prevToClip=identity projection=non-identity reset=1
  cameraIncluded=1 mv3D=0 dilatedGame=0 dilationOverride=0 jittered=0
  depthInverted=0 scale=(1,1) jitter=(-0,-0)
[MOTION] clipToPrev rows=[1.00000012 0 0 0][0 1 9.31322575e-10 9.31322575e-10][0 0 1.00000012 0][0 -1.1920929e-07 -1.1920929e-07 1]
  cameraPos=(-50,600,80)
```

- `call=0/1/2/3` 间隔 ≈ 26 ms（= 每帧一次），**`reset` 恒为 1**
- `cameraPos=(-50,600,80)` **有效** ⇒ 相机缓存是活的，不是"没抓到数据"
- `projection=non-identity` ⇒ 投影矩阵有效
- `clipToPrev=identity`、`jitter=(-0,-0)` ⇒ 另两个独立缺陷（见 §5）

### 2.3 DFG 自己的 MOTION 探针同样报单位矩阵

```
[21:18:30.702] [Streamline] MOTION probe: clipToPrevClip maxDevFromIdentity=0.000000
  r3=(0.00000 -0.00000 -0.00000)
```

### 2.4 帧节拍同时不稳

```
[PERF] 4x | Kernel: Ada | FPS: 37.1 (26.93ms) | Jitter: 11.94ms
[PERF] 4x | Kernel: Ada | FPS: 38.8 (25.78ms) | Jitter:  4.89ms
[PERF] 4x | Kernel: Ada | FPS: 35.0 (28.57ms) | Jitter: 15.31ms
```

帧时间 27 ms 上抖动 15 ms（>50%）。

---

## 3. 根因

源码 `src/Streamline.cpp:403-410`（v0.59 之前）：

```cpp
c.reset = sl::Boolean::eFalse;
if (auto* ui = RE::UI::GetSingleton()) {
    const auto* istrings = RE::InterfaceStrings::GetSingleton();
    if (ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||
        ui->IsMenuOpen(istrings->journalMenu) || ui->IsMenuOpen("PauseMenu"))
        c.reset = sl::Boolean::eTrue;      // ← 菜单打开期间【每帧】都置位
}
```

`reset` 的语义（`sl_consts.h`）：告诉 SL「这是序列重新开始，不要复用历史」。
菜单打开期间它**每帧**都是 `eTrue`，而 DLSS-G 同时在输出 4 帧：

```
DLSSG presented per real frame = 4
```

⇒ 每个生成帧都在「零历史」状态下重建 ⇒ 静止画面也持续闪；DLSS-G 内部状态每帧重建 ⇒ 帧节拍抖动（§2.4）。

**这是一个 v0.34 引入的副作用**：那一版的意图是「菜单里运动矢量无效，别用旧数据插帧」（注释原文："菜单帧插错 = 视觉错乱"），意图正确，但实现选择了「每帧重置」而不是「停止生成」或「只在进入菜单时重置一次」。

---

## 4. 本次改动（v0.59，1 处行为改动 + 1 个诊断）

### 4.1 `reset` 改为边沿触发（`Streamline.cpp`）

```cpp
bool isMenuOpen = false;
if (auto* ui = RE::UI::GetSingleton()) {
    const auto* istrings = RE::InterfaceStrings::GetSingleton();
    isMenuOpen = ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||
        ui->IsMenuOpen(istrings->journalMenu) || ui->IsMenuOpen("PauseMenu");
}
static bool s_wasMenuOpen = false;
c.reset = (isMenuOpen && !s_wasMenuOpen) ? sl::Boolean::eTrue : sl::Boolean::eFalse;
s_wasMenuOpen = isMenuOpen;
```

- 进入菜单的**那一帧**：`reset=true`（保留 v0.34 意图，丢掉菜单前遗留的旧数据）
- 菜单持续期间：`reset=false`（不再每帧打断 DLSS-G 的 temporal 状态）

附带 `RESET probe`（每 240 帧一行）：

```
[Streamline] RESET probe: menuOpen=true reset=0 (edge-triggered, v0.59)
```

### 4.2 新增 `CAM probe` 诊断（只打印，不改行为）

```
[Streamline] CAM probe: dev(curVP c24)=… dev(prevVP c32)=… dev(viewProj c16)=… dev(view c0)=… pos=(…) prevPos=(…)
```

用于定位 §5.3 的 `clipToPrev=identity`：`dev(x)` 是矩阵 x 相对单位矩阵的最大偏差。
若 `dev(curVP)≈0` 而 `dev(viewProj)≠0` ⇒ c24/c32 这两个字段在引擎侧从未被更新。

`MOTION probe` / `CAM probe` 的间隔同时由 600 帧改为 **240 帧**（一次运行能拿到多个样本）。

### 4.3 工具与备份

- 补丁脚本：`tools/fix_reset_edge_v059.py`（每条 edit 独立 marker 幂等守卫 + 锚点 count==1 断言 + 备份 + 行尾保持 + 回读；默认干跑）
- 备份：`D:\workbuddy2\backup\reset_edge_20260917_212303\Streamline.cpp.bak`
- 构建：`build_vs.bat`（已修好，不调 vcvars、不查注册表）

---

## 5. 下一顺位（如果本次没修好）

按证据强度排序，**一次只动一个**：

### 5.1 菜单里直接停止生成（最彻底）

`sl::DLSSGOptions::mode` 目前恒为 `eOn`（`Streamline::SetDLSSGOptions`）。
NVIDIA 的标准做法是**菜单/加载时暂停帧生成**，而不是靠 `reset` 压制。
改法：按菜单状态每帧设 `mode = eOff / eOn`。
风险：需要确认 `slDLSSGSetOptions` 在每帧调用下的时序约束（须早于 `slSetTag`）。

### 5.2 `jitterOffset` 恒 `{0,0}`（已确认是孤儿变量）

```
Streamline.h:177   float jitterX = 0.0f;    ← 声明
Streamline.h:178   float jitterY = 0.0f;
Streamline.cpp:399 c.jitterOffset = { -Get().jitterX, -Get().jitterY };   ← 读取
                                      ↑ 全仓零写入
```

注释自相矛盾：`FrameGen.h:175` 说「v0.34 对齐 open-shaders：jitter 由 `OnMainUpdateJitter` 计算」，
`FrameGen.h:207` 说「v0.50：Halton jitter 已全部拔掉」。**生产者删了，消费者留着** —— 与
`engineFrameCount`（v0.58 修掉）是同一类 bug。

**同仓库内已有真实来源可搬**（`FidelityFX.cpp:173-176`，FSR3 路径）：

```cpp
static auto gameViewport = RE::BSGraphics::State::GetSingleton();
dispatchParameters.jitterOffset.x = gameViewport->projectionPosScaleX * float(sc.swapChainDesc.Width) / 2.0f;
dispatchParameters.jitterOffset.y = gameViewport->projectionPosScaleY * float(sc.swapChainDesc.Height) / 2.0f;
```

SL 语义（`sl_consts.h`）：`//! Specifies pixel space jitter offset` ⇒ **像素单位**，
与 FSR3 公式同量纲。搬到 DLSS-G 路径时注意符号：SL/NVIDIA 约定取负
（`{ -posScaleX * W/2, -posScaleY * H/2 }`）。

⚠️ 当前 `RenderResolutionScale=0.44`（1689×950 → 3840×2160，放大 2.27×），
亚像素 jitter 误差会被放大到 1 像素以上 —— **这个值越大，jitter 缺失越明显**。
若 5.2 要 A/B，可先把 `RenderResolutionScale` 调回 1.0 观察闪是否减轻（不改代码的对照实验）。

### 5.3 `clipToPrevClip` 恒为单位矩阵（原因待 CAM probe 定论）

```
FrameGen.h:82       Matrix CameraPreviousViewProjUnjittered;    // c32
Streamline.cpp:353  const Matrix prevVP = a_fb.CameraPreviousViewProjUnjittered;
                                              ↑ 零写入（依赖引擎在 c32 提供）
```

`clipToPrevClip = inverse(curVP) × prevVP`。结果为精确单位矩阵 ⇒ `prevVP ≡ curVP`。
两种可能，靠 CAM probe 区分：
- `dev(curVP)≈0` 且 `dev(viewProj)≠0` ⇒ c24/c32 在引擎侧未被更新（偏移错/字段不存在）
  ⇒ 修法：DFG 自己缓存上一帧 viewProj
- `dev(curVP)≠0` ⇒ 两个字段都有效但恒等 ⇒ 引擎不维护 prev ⇒ 同样自己缓存

---

## 6. 判据（跑一次就能分层）

**操作**：主菜单停 10 秒 → 按回车进游戏 → 走一段、转视角。

**日志** `Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`：

| 项 | 期望 | 含义 |
|---|---|---|
| `RESET probe: menuOpen=true reset=0` | 菜单稳定后必须是 **0** | 边沿触发生效 |
| `RESET probe: menuOpen=true reset=1` | 只在**进入菜单的第一帧**见到 | — |
| `constants: ok=` | 每 120 帧增长 | 常量在刷新 |
| `constants: fail=` | 停在 0 | — |
| `CAM probe: dev(curVP c24)` | 记录数值即可 | 供 §5.3 定论 |

**主观**：主菜单静止时是否还闪。

---

## 7. 回滚

```bash
copy /Y "D:\workbuddy2\backup\reset_edge_20260917_212303\Streamline.cpp.bak" "D:\Modding\DynamicShaderFrameGen\src\Streamline.cpp"
# 然后重新编译
& "D:\Modding\DynamicShaderFrameGen\build_vs.bat"
```
