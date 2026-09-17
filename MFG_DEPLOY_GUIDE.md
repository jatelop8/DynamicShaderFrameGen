# DynamicShaderFrameGen — 多倍帧生成（MFG）状态说明

**版本**：v0.52 · 构建 `Sep 17 2026 14:08` · DLL MD5 `f93031f7df63b1ec84976439e2621ae0`（1213952 字节）
**工程**：`D:\Modding\DynamicShaderFrameGen`（提交基线 `44591b7` → v0.52）
**Git 回退点**：`44591b7`（v0.51）；源码备份 `D:\workbuddy2\backup\DynamicShaderFrameGen_mfg_20260917_121051\`

---

## 一、这次修的是什么（"切换 DLSS 没有任何变化"）

### 日志给出的硬事实

本次会话（13:59:55 启动）唯一被记录的菜单交互是：

```
14:00:54.445  [FrameGen] DLSSNR disabled (GUI)
14:00:55.019  [FrameGen] DLSSNR enabled  (GUI)
```

除此之外**什么都没有**。而配置自始至终是 `Provider=0`：

```
13:59:55.164  Config loaded: ... Provider=0 ... QualityMode=1 ...
每一行 FPS probe: real=55.8 | FSR3 | ...
每一行 MenuDraw entry: dlssg=false ...
```

### 三条各自独立的原因

**① Provider 下拉框在运行中切换，按设计就是"零效果"**

`Provider` 只在 `DX12SwapChain::CreateSwapChain()` 里被消费**一次**：它决定 `dlssgMode`、`BufferCount`（DLSSG 三缓冲 / FSR3 双缓冲）、以及整条 D3D12 proxy 路径。这些在 swapchain 创建时定型，运行中改内存变量不会重建任何东西。

> 这是结构性的，**没有热切方案**。原来那条 `ImGui::Combo` 连一行日志都没写，所以"切了没反应"连个痕迹都查不到。

**② 改动根本没落盘**

下拉框只改内存里的 `s.provider`；只有点 "Save to INI" 才写文件。而全盘检查证明那次保存从未成功：

| 检查 | 结果 |
|---|---|
| 全盘 9 份同名 INI，指纹比对日志 | 生效的是 `E:\EJ\mod\mods\DynamicShaderFrameGen\...ini`（13:30 我写的那份，`Provider=0`）|
| `E:\EJ\mod\overwrite\SKSE\Plugins\` 有 FrameGen INI 吗 | **没有**（只有 CrashLogger / po3 / ImmersiveHUD 等）→ 说明 Save 从未成功过 |
| MO2 档案 `DIPEI` 里哪些 FrameGen mod 启用 | 只有 `+DynamicShaderFrameGen`（DLL MD5 `7d9ee3be`，13:30 构建）；另两个 v047b / NR 都是 `-` 禁用 |

**③ 旧版 "Save to INI" 还会静默删键**

它把文件**截断重写**成 17 个键，于是 `QualityMode` / `RenderResolutionScale` / `Sharpness` / `FpsOverlay` / `EnableUpscale` / `PresetDLSS` 整行消失 —— 自定义渲染比例会被无声重置。

另外，菜单标题还写着 "DLSS Upscaling (live adjust)"，但**超分在 v0.48 就移除了**（`EnableUpscale`、`PresetDLSS` 只被解析、没有任何实现引用）→ 用户会一直去找那个不存在的开关。

---

## 二、v0.52 改了什么

| # | 改动 | 影响 |
|---|---|---|
| 1 | `SaveSettingsToIni()` 统一写入口，**Save 按钮与所有开关共用** | 开关改动**立即落盘**，不再需要记得按 Save |
| 2 | 写路径与 `LoadConfig` 读取路径**逐字一致**，并写全 **24 个键** | 不再静默失败、不再删掉别的键 |
| 3 | 写成功/失败**都记日志**（`INI saved:` / `INI save FAILED:`） | 静默失败这类 bug 下次能被日志抓住 |
| 4 | 记录 `providerAtCreate`，GUI 显示 **PENDING RESTART** 横幅 | 切了 Provider 会明确告诉你"要重启" |
| 5 | FPS probe 增加 `cfgProvider=`，不一致时追加 `(CHANGED - RESTART REQUIRED)` | 一条日志同时给出"在跑的"和"INI 写的" |
| 6 | MFG 倍率/上限控件**不再藏在 provider==1 后面** | FSR3 下也能先把 DLSSG 参数设好 |
| 7 | DLSSNR 诊断改打 **Apply 真正吃的输入 + NGX 成功帧数**，输入没就绪时警告一次 | 以前那条日志读的是引擎原生 depth/mvec，**无论 NR 有没有跑都显示 true**，无法证伪 |
| 8 | INI 标注 `EnableUpscale`/`PresetDLSS` 为 parsed-but-not-wired；Provider 注明仅下次启动生效 | 不再让人追死开关 |
| 9 | 版本 0.50 → 0.52 | — |

---

## 三、当前配置与"两半"的对应关系

拿 4-6 倍帧生成需要**两半同时到位**，现在都装了：

| 半边 | 位置 | 状态 |
|---|---|---|
| **代码：把请求发出去** | `MFGMaxFramesOverride=3` | ✅ 已配（`=0` 时阶梯探测只会请求硬件上限 1→2x）|
| **内核：让请求能执行** | `D:\ENB-EJ\Skyrim Special Edition\version.dll` | ✅ DLSSG-Transfusion v1.4.1，SHA256 `a7f517ca…` 与官方发布包一致 |

**生效配置**（`E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini`）：

```
Provider=1                 ; DLSSG 路径
DLSSGFramesToGenerate=3    ; 4x
MFGMaxFramesOverride=3     ; 抬到 4x（=0 会被压回 2x）
NeuralRenderingEnabled=1
```

> 活动 MO2 实例：档案 **DIPEI**，`base_directory=E:\EJ\mod`，`gamePath=D:\ENB-EJ\Skyrim Special Edition`。
> 游戏根目录里 `version.dll` 原本不存在（ENB 占的是 `d3d11.dll`），所以代理名无冲突。

### 回退（10 秒）

1. **只退回 FSR3**：菜单里把 Provider 切回 `FSR3` —— v0.52 起它会**立刻写入 INI**，重启即生效；或直接改 INI 的 `Provider=0`。
2. **连解锁器一起撤**：删掉 `D:\ENB-EJ\Skyrim Special Edition\version.dll` 与 `DLSSG-Transfusion.json`。

---

## 四、进游戏后怎么验证（每次启动覆盖日志）

日志：`Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`

| 看这一行 | 期望 | 含义 |
|---|---|---|
| `Provider in effect this session: 1 (DLSSG)` | 出现 | swapchain 走了 DLSSG 路径 |
| `FPS probe: ... cfgProvider=1` | 无 `(CHANGED ...)` 后缀 | 在跑的和 INI 写的一致 |
| `MFG probe: runtime ACCEPTED 4x` | **出现** | **唯一可信的"4 倍生效"证据** |
| `MFG probe: runtime REJECTED` | 不应大量出现 | 被拒 → 阶梯探测会逐帧降档并锁定 |
| `cap~=real*4` | — | 只是**推算**的理论上限，**不是测量值** |
| `DLSSNR: ... inputs=true frames=N` | `frames` **持续增长** | NR 真的在跑（`frames=0` = 从未执行）|

**判读**：

- `ACCEPTED 4x` + 画面正常 → 成功，4 倍到手
- `REJECTED` 且锁定在 `accepted=1x(2x)` → 解锁器没生效，看游戏目录的 `DLSSG-Transfusion.log`（JSON 里 `logPerformance: true`、`showOverlay: true`）
- 画面闪 → 先看有没有 `REJECTED`；v0.51 的阶梯探测就是为这个加的，理论上不该再闪

---

## 五、诚实的边界

- **倍率上限由运行时决定**，不是写了就一定拿到。`dlssgFramesToGenerate` 只是请求；真正决定的是 Streamline 运行时接不接受。
- **Provider 切换永远需要重启**（swapchain 路径一次性定型）。v0.52 做的是让它"落盘 + 记日志 + 界面提示"，不是让它热切。
- `EnableUpscale` / `PresetDLSS` 是**死开关**（v0.48 移除超分后遗留），已在 INI 里标注。
- 6x 需要把 `MFGMaxFramesOverride` 与 Transfusion 的 `multiplier` 一起提到 6；4x 是当前两边一致的配置。
