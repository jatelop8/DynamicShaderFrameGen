# FIX_FRAMESERIAL_2115 — 频闪根因：帧令牌（frame token）自 v0.50 起从未推进

**日期**：2026-09-17 21:15
**构建**：v0.58（源码 `D:\Modding\DynamicShaderFrameGen`）
**产物**：`DynamicShaderFrameGen.dll` 1224192 字节 · md5 `31ba818d6c92f050c8e891864ce335ce`
**部署**：`E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.dll`（md5 已核对一致）

---

## 一、结论（一句话）

**`slSetConstants` 从 v0.50 起就没成功过 —— 每帧都在被 Streamline 拒绝（错误码 27 =
`eErrorDuplicatedConstants`）。DLSS-G 拿到的每帧常量（`clipToPrevClip` 相机重投影矩阵、
`jitterOffset`、`reset`、frame 时间、Reflex pacer 数据）**永远是第一帧的旧值**，
于是每个生成帧都被用**过期的相机变换**做重投影 → 画面闪；pacer 拿不到新数据 →
节拍乱 → 主菜单画面停滞 + 闪。**

## 二、证据链（三层，全部可复核）

### 1. 源码层：`engineFrameCount` 是个"孤儿变量"

`src/FrameGen.h:207-209` 自己写着：

```
// v0.50：DLSS 超分/DRS/Halton jitter 已全部拔掉（引擎回到 2560 原生渲染）。
// InstallDRSHook / OnMainUpdateJitter / InstallMainPostProcessingHook /
// OnMainPostProcessing 已移除。仅保留 DLSS5(DLSSNR) + FSR3 FG 串联。
```

**`OnMainUpdateJitter` 被移除了 —— 它是 `engineFrameCount` 唯一的写入者。**
全仓取证（`grep -rn "engineFrameCount" D:\Modding\DynamicShaderFrameGen`）：

```
src/FrameGen.h:182:      std::uint32_t engineFrameCount = 0;   <- 声明
src/Streamline.cpp:289:  const std::uint32_t frame = Get().engineFrameCount;   <- 读取
```

**只有声明和读取，零写入。⇒ 恒等于 0。**

### 2. 逻辑层：恒 0 直接毁掉帧令牌

```cpp
bool Streamline::EnsureFrameToken() {
    static std::uint32_t s_lastFrame = UINT32_MAX;
    const std::uint32_t frame = Get().engineFrameCount;   // 恒 0
    if (frame == s_lastFrame)          // 第 2 次起永远为真
        return frameToken != nullptr;  // -> 永不取新 token
    s_lastFrame = frame;               // = 0，此后再不更新
    frameToken = nullptr;
    slGetNewFrameToken(frameToken, &frame);   // 只调用一次，frameIndex 恒 0
}
```

同一类坑 **v0.31 的注释里已经记过一次**（"必须传帧计数，nullptr → 帧号停滞"），
v0.50 移除 jitter hook 时**复发**。

### 3. 官方头文件层（本机 `D:\Modding\extern\Streamline\include\`）

`sl_result.h` 枚举第 27 项 = **`eErrorDuplicatedConstants`**：

```
25 eErrorInvalidParameter
26 eErrorMissingConstants
27 eErrorDuplicatedConstants   <-- 日志里的 27
```

`sl_core_api.h` 对 `slGetNewFrameToken` 的定义：

```
//! @param frameIndex Frame index (optional, if not provided SL internal frame counting is used)
//! NOTE: Normally SL would not expect more that 3 frames in flight due to added latency.
SL_API sl::Result slGetNewFrameToken(sl::FrameToken*& token, const uint32_t* frameIndex = nullptr);
```

`sl_consts.h` 对关键字段的定义：

```
//! Specifies matrix transformation from the current clip to the previous clip space.
float4x4 clipToPrevClip;      // <- DLSS-G 用它重投影每个生成帧
//! Specifies pixel space jitter offset
float2 jitterOffset;
```

⇒ 帧索引必须逐帧推进（SL 按 ≤3 帧在飞设计环缓冲）；传恒定值 → 帧槽不换 →
常量写入命中"该帧已设置" → 27。

### 4. 运行时日志（`Documents\My Games\...\SKSE\DynamicShaderFrameGen.log`，21:04:26 启动）

```
21:04:55.987  mvecScale = { 1.0000, 1.0000 } (override=1.00)     <- 上轮修复生效
21:05:50.608  [E] slSetConstants failed: 27      <- 进入游戏起，每 26ms（每帧）一次
21:05:50.634  [E] slSetConstants failed: 27
21:05:50.813  [E] slSetConstants failed: 27
...（持续到 21:06:09 退出，共约 700 次）
```

主菜单阶段只零星出现（每 5 秒 2 次），**一进游戏就变成每帧一次** ——
即"常量完全断供"的窗口正好与用户描述的"一直停在主菜单画面 + 一直闪"重合。

## 三、本次改动（4 处，源文件已落盘并回读验证）

| # | 文件 | 改动 |
|---|---|---|
| A | `src/Streamline.h` | 新增 `std::uint32_t frameSerial = 0;`（每帧序号，唯一写入点在 Present） |
| B | `src/Streamline.cpp` | `EnsureFrameToken` 判据 `Get().engineFrameCount` → `frameSerial` |
| C | `src/Streamline.cpp` | `slSetConstants` 增加成功/失败计数 + 每 120 帧上报一次（**本轮的可验证判据**） |
| D | `src/DX12SwapChain.cpp` | `Present` 里在任何 SL 调用之前 `++fg.streamline.frameSerial;` |

- 补丁脚本：`tools/fix_frameserial_v058.py`（marker 幂等守卫 + 锚点唯一性断言 + 备份 + 行尾校验）
- 备份：`D:\workbuddy2\backup\frameserial_20260917_211113\`
- 行尾完整性：`Streamline.h` CRLF 199 行（bare LF = 0）、`Streamline.cpp` LF 852 行（stray CRLF = 0）、
  `DX12SwapChain.cpp` LF 1105 行（stray CRLF = 0）
- 旧引用已确认消失：`Get().engineFrameCount` 在源码中不再出现

### 设计要点

`++frameSerial` 放在 `DX12SwapChain::Present` 的 `if (dlssgMode)` 块内、`EnsureFrameToken()`
之前 —— **Present 是每帧唯一入口**，因此：

- 本帧第 1 次调用（Present 内）→ frameSerial 是新值 → 取新 token ✓
- 本帧第 2 次调用（`EvaluateDLSSG` → `CheckFrameConstants`）→ frameSerial 未变 → 复用同一 token ✓
  （v0.37b 的意图得以保留：同帧所有 SL 调用共用一个 token）

## 四、构建（本轮踩到的两个环境坑）

**必须用能拿到 MSVC + Windows SDK 的环境编译**，否则：

1. `cmake --build` 在裸 shell 里跑 → `PCH.h(3): fatal error C1083: 无法打开 "algorithm"`
   （`INCLUDE` 为空）
2. 调 `vcvars64.bat` 也不够 —— **它内部会调 `reg.exe` 去探测 Windows SDK，
   本机沙箱拦截 `reg.exe`** → SDK 路径没设上 → `yvals.h(21): fatal error C1083: 无法打开 "crtdbg.h"`

**解决**：`build_vs.bat` 改为**不调 vcvars、直接钉死工具链路径**（无注册表依赖）：

```
MSVCVER=14.50.35717
SDKVER=10.0.26100.0
INCLUDE = <MSVC>\include; <SDK>\Include\<SDKVER>\{ucrt,shared,um,winrt,cppwinrt}
LIB     = <MSVC>\lib\x64; <SDK>\Lib\<SDKVER>\{ucrt,um}\x64
```

用法：`build_vs.bat`（增量）/ `build_vs.bat --clean`（清空重建）。
**MSVC 或 SDK 升级后需要同步 bump `MSVCVER` / `SDKVER`。**

构建结果：`[7/7] Linking CXX shared library DynamicShaderFrameGen.dll` —— 成功。
POST_BUILD 自动部署到 mods 目录，**两份 md5 已核对一致**。
⚠️ POST_BUILD 也会 `copy_if_different` 源仓库的 `DynamicShaderFrameGen.ini` 覆盖部署副本 ——
**本次已核对两份 INI md5 相同（`f7115e5e`，`MvecScaleOverride=1.00` / `RenderResolutionScale=0.44`），不会回退。**

## 五、测试判据（跑一轮就能定死）

配置未动（`disableMenuDetection=0` 已生效），**直接重启游戏即可**。

**读 `Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`：**

| 判据 | 修复前 | 期望 |
|---|---|---|
| `[Streamline] constants: ok=N fail=M serial=K` | 不存在（旧版无此行） | **`ok` 每帧增长、`fail` 停在 0 附近、`serial` 持续增长** |
| `[E] slSetConstants failed: 27` | 每帧刷屏 | **该行不再逐条输出** —— v0.58 用计数行取代（避免刷屏），失败信息改由上一行的 `fail=` / `lastR=` 承载 |
| `[Streamline] MOTION probe ... maxDevFromIdentity` | 主菜单恒 0.000000 | 主菜单仍 ~0（正常）；**移动时应明显 ≠ 0** |
| `DLSSG presented per real frame` | 4 | 4（不变） |

**主观**：主菜单是否还闪；菜单里画面是否还会"停住"。

**若 `fail` 仍在增长**（说明 token 机制另有约束），下一手备选：
把 `slGetNewFrameToken(frameToken, &frame)` 的第二个参数改传 **`nullptr`**
（官方文档：不提供则用 SL 内部计数）—— 这是与当前方案正交的第二个变量。

**其余已排除项（均有实测证据，不要回头再查）**：mvecScale 高估、swapchain ≠ 显示模式、
窗口物理尺寸（DPI 虚拟化）、倍率抖动、配置偏离出厂、`slSetConstants` 之外的 SL 报错、
ENB 冲突、`disableMenuDetection`、`qualityValidWarp`、`patchFlipMetering`。

## 六、回滚

```bat
copy /Y "D:\workbuddy2\backup\frameserial_20260917_211113\Streamline.h.bak"     "D:\Modding\DynamicShaderFrameGen\src\Streamline.h"
copy /Y "D:\workbuddy2\backup\frameserial_20260917_211113\Streamline.cpp.bak"   "D:\Modding\DynamicShaderFrameGen\src\Streamline.cpp"
copy /Y "D:\workbuddy2\backup\frameserial_20260917_211113\DX12SwapChain.cpp.bak" "D:\Modding\DynamicShaderFrameGen\src\DX12SwapChain.cpp"
D:\Modding\DynamicShaderFrameGen\build_vs.bat
```
