# 主菜单就闪 / 进不去游戏 —— 呈现链尺寸不匹配（2026-09-17 19:50）

## 一、结论（一句话）

**swapchain 尺寸 (2560×1440) ≠ 显示模式尺寸 (3840×2160) ⇒ DXGI 无法走 Independent Flip
⇒ Streamline pacer 失去节拍 ⇒ 画面持续闪烁。** 与 ENB 无关，与 mvecScale 无关，与场景无关
（所以主菜单也闪）。这是**呈现层**缺陷，不是渲染层。

## 二、证据链（全部本机实测，非推断）

### 2.1 尺寸不匹配（决定性）

```
Win32_VideoController:
  NVIDIA GeForce RTX 4080 SUPER | Cur=3840x2160@160Hz | Max=160 Min=29

SkyrimPrefs.ini  (My Games):
  iSize W=2560
  iSize H=1440
  bFull Screen=0
  bBorderless=1

DFG log: [Streamline] DLSSG options dims: color=2560x1440 mvecDepth=2560x1440
DFG log: [Streamline] Reflex render cap = 39 fps (25641us) - 160Hz / 4x => ~156 present fps
```

输出侧是 1440p，面板是 4K ⇒ **DWM 必须做缩放合成**。

### 2.2 系统层三个前提全部正常（所以只剩尺寸这一条）

| 项 | 实测值 | 判定 |
|---|---|---|
| `DirectXUserGlobalSettings` | `AutoHDREnable=1;SwapEffectUpgradeEnable=1;` | 窗口化游戏优化**已开** ✓ |
| `DISABLEDXMAXIMIZEDWINDOWEDMODE` | 不存在（SkyrimSE.exe 只有 `HIGHDPIAWARE`） | 全屏优化**未**被禁用 ✓ |
| `HwSchMode` | 2 | 硬件加速 GPU 调度已开 ✓ |
| `GameDVR_FSEBehaviorMode` | 0 | 默认，未干预 FSE ✓ |

DXGI 使用 Independent Flip 的硬性条件：**swapchain 的尺寸与格式必须与当前显示模式完全一致**。
前三条都满足，唯一不满足的就是尺寸。

### 2.3 症状是插件作者自己写下的原话（v0.54 INI 注释）

> *"If that product is above the monitor refresh rate the frames are OVER-SUBMITTED: the present
> queue backs up, **the SL pacer loses its rhythm and the picture flickers continuously**."*
> *"render fps x multiplier <= refresh rate"* / *"Too low = stutter, **too high = flicker**."*

**"flickers continuously"** —— 与用户描述逐字吻合。DFG 只按**刷新率**算节拍（39 = 160/4 - 1），
**没有考虑 swapchain 与面板分辨率的匹配**。刷新率对了，尺寸不对，Independent Flip 仍然不成立。

### 2.4 与已排除项的交叉验证

| 已试过的改动 | 结果 | 说明 |
|---|---|---|
| `MvecScaleOverride` 0.00 → 1.00 | 已生效（日志 `{1.0000,1.0000} override=1.00`），**闪未改善** | 证明不是运动估计问题 |
| `forceUiRecomposition` true → false | 已回滚 | 与闪无关 |
| 重复代理（version.dll） | 已修，`Patch worker started` 只 1 次 | 那是之前的卡死，不是这个闪 |

**共同点：这三个都作用在渲染/输入层，而闪在呈现层 —— 所以都无效。这本身就是指向呈现层的一个证据。**

## 三、本次改动（两处，均带断言与备份）

### 3.1 `SkyrimPrefs.ini` —— swapchain 变成面板原生尺寸

```
iSize W : 2560 -> 3840
iSize H : 1440 -> 2160
```
（`C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SkyrimPrefs.ini`
行 162 / 158；CRLF 保持；197 行不变；`bFull Screen=0`、`bBorderless=1` 未动 —— DLSS-G 要求 windowed swapchain）

### 3.2 `DynamicShaderFrameGen.ini` —— 保住内部渲染分辨率（性能不变）

```
RenderResolutionScale : 0 -> 0.44
```

| | 之前 | 之后 |
|---|---|---|
| 输出 / swapchain | 2560×1440 | **3840×2160（原生）** |
| 内部渲染 | 2560×0.6667 = **1707×960** | 3840×0.44 = **1690×950** |
| 到面板的路径 | DLSS→1440p，再被 DWM 双线性拉到 4K | DLSS 一次性到原生 4K |

**渲染像素数基本不变（1.64M → 1.61M），但省掉了 DWM 那次缩放 —— 画质净提升。**

**倍率仍是 4x，`blackwellTransfusion` / `patchFlipMetering` / `mvecScale` 全部未动 —— 不是回退。**

源仓库与部署副本**两份都改了**（md5 `f7115e5e…`），因为 CMake POST_BUILD 会用仓库那份
`copy_if_different` 覆盖部署副本。

- 备份：`D:\workbuddy2\backup\swapchain_native_20260917_195041\`
- 脚本：`D:\Modding\DynamicShaderFrameGen\tools\fix_swapchain_native.py`（断言 + 幂等 + 备份 + 回读，默认干跑）

**回滚**：
```
copy /Y "D:\workbuddy2\backup\swapchain_native_20260917_195041\SkyrimPrefs.ini.bak" "C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SkyrimPrefs.ini"
copy /Y "D:\workbuddy2\backup\swapchain_native_20260917_195041\DynamicShaderFrameGen.ini.bak" "E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini"
copy /Y "D:\workbuddy2\backup\swapchain_native_20260917_195041\DynamicShaderFrameGen.ini.bak" "D:\Modding\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini"
```

## 四、关于"是不是和 ENB 冲突" —— 不是，逐项有据

| 候选冲突点 | 实测 | 判定 |
|---|---|---|
| ENB 联网 / 与外部通信 | `d3d11.dll` 导入 `WinHttp`/`WinInet`/`InternetOpen`/`ws2_32` **全为 0** | 排除 |
| ENB 帧率限制与 DLSS-G 抢节拍 | `enblocal.ini [LIMITER] EnableFPSLimit=false` | 排除 |
| ENB VSync 与 flip 冲突 | `enblocal.ini [ENGINE] ForceVSync=false` | 排除 |
| ENB 代理库链 | `[PROXY] EnableProxyLibrary=false` | 排除 |
| 两者 hook 同一呈现路径 | ENB 在 **D3D11 渲染层**（prepass/postpass 后处理）；闪在 **DWM 合成/flip 呈现层** | 两条管线不重叠 |

**结论：不是 ENB 冲突。** 机制上 ENB 改的是"画面内容"，而闪来自"画面什么时候被推到屏幕"。
（若要 100% 封口，游戏内关掉 ENB 效果跑一次即可，但那只是排除法，不是修因。）

## 五、下次启动要看的验证点

**必须重启游戏**（swapchain 在创建时确定，热改无效）。

DFG 日志应当打印：
```
[Streamline] DLSSG options dims: color=3840x2160 ...
[Streamline] Reflex render cap = 39 fps (25641us) - 160Hz / 4x => ~156 present fps
FPS probe: real=NN | ...
```

`color=3840x2160` = swapchain 已是原生 ⇒ 前提成立。

**如果仍闪**，按顺序单变量（都只动呈现节拍）：
1. 退出 **ToDesk**（本机检测到 `ToDesk.exe` 在跑，带 `Todesk Virtual Display Adapter`
   —— 远程桌面会强制 DWM 合成路径，直接破坏 Independent Flip）**和向日葵（`OrayIddDriver Device`）**
2. 关闭 **GameDVR / Xbox Game Bar**（`HKCU\System\GameConfigStore\GameDVR_Enabled = 1`，
   屏幕捕获同样会强制合成）
3. 关闭 **Auto HDR**（系统全局 `AutoHDREnable=1`；Auto HDR 走 DWM 合成）
4. `ReflexFpsLimit` 0 → 35（给节拍留更多余量，日志会打印新的 cap）
5. `multiplier` 4 → 2（诊断：若 2x 也闪，则与倍率无关）

**如果游戏又"自己消失"**（不是闪，是进程没了），跑退出手表拿退出码 ——
这是区分"未处理异常 / `__fastfail`（绕过 SEH，本来就不会有崩溃日志）/ 主动 ExitProcess"
的唯一手段：

```
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Modding\DLSSG-Transfusion\tools\watch_exit_code.ps1"
```

## 六、本机既有的、与本次无关的观察（供参考）

- `enblocal.ini [FIX] IgnoreLoadingScreen=true`、`[PERFORMANCE] SpeedHack=true`
- `TdrDelay=30`（默认 2 秒，被调大过；说明历史上遇到过 TDR）
- 两个虚拟显示适配器：`OrayIddDriver Device`、`Todesk Virtual Display Adapter`
- `E:\EJ\mod\profiles\DIPEI\` **没有** profile-specific ini ⇒ 走全局 My Games 那份（改对了地方）；
  `ck` profile 有一份自己的，未受影响
