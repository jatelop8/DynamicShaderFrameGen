# v0.60 — 菜单闪的第三刀：用 SDK 官方的全屏菜单检测

**时间**：2026-09-17 21:29
**产物**：`e8be2ade876c7901e1553f465561db08`（1227776 B）— 构建产物与 MO2 mods 副本 md5 已核对一致
**备份**：`D:\workbuddy2\backup\menuflag_v060_20260917_212842\Streamline.cpp.bak`
**补丁**：`tools/fix_menuflag_v060.py`（干跑默认，`--apply` 落盘）

---

## 1. 为什么加这一刀

在 `sl_dlss_g.h` 里翻 DLSSG 的选项时发现一条**一直没被设过的官方开关**：

```cpp
enum class DLSSGFlags : uint32_t
{
    eShowOnlyInterpolatedFrame       = 1 << 0,
    eDynamicResolutionEnabled        = 1 << 1,
    eRequestVRAMEstimate             = 1 << 2,
    eRetainResourcesWhenOff          = 1 << 3,
    eEnableFullscreenMenuDetection   = 1 << 4,   // ← 就是这个
    eAll = ...
};
```

而 DFG 的 `SetDLSSGOptions()`（`Streamline.cpp:512`）里：

```cpp
sl::DLSSGOptions opts{};
opts.mode = sl::DLSSGMode::eOn;   // 硬编码，从不回 eOff
                                  // opts.flags 从未被碰过 ⇒ == 0
```

⇒ **全屏菜单检测从头到尾是关的。** 菜单打开时 SDK 照样生成帧，按钮、文字、
渐隐背景全被当成 3D 内容做运动插值 —— 这正是「停在主菜单画面 + 一直闪」的形态。

**判据优先级**：SDK 自己提供开关时，永远优先用 SDK 的，而不是自己写启发式。
这一刀比上一轮我提的「自己检测菜单 → `mode = eOff`」更正统：不用自己维护菜单列表，
也不用在运行时切 mode。

改动只有一行（外加一条一次性日志）：

```cpp
opts.flags |= sl::DLSSGFlags::eEnableFullscreenMenuDetection;
SKSE::log::info("[Streamline] DLSSG flags: fullscreenMenuDetection=on (v0.60)");
```

---

## 2. 现在盘面上是三道改动（互不冲突，判据彼此独立）

| 版本 | 改动 | 针对什么 | 独立判据（日志） |
|---|---|---|---|
| v0.58 | `frameSerial` 每帧推进（替换恒 0 的 `engineFrameCount`） | 帧令牌不推进 ⇒ `slSetConstants` 被拒(27) ⇒ 常量永不刷新 | `constants: ok=` 每帧增长、`fail=0`、`serial` 递增 **← 已实测通过** |
| v0.59 | `reset` 改边沿触发（`s_wasMenuOpen`） | 菜单里**每帧**告诉 DLSS-G「新序列，丢历史」 | `RESET probe: menuOpen=true reset=0` |
| v0.60 | 启用 `eEnableFullscreenMenuDetection` | 菜单里根本不该生成帧 | `DLSSG flags: fullscreenMenuDetection=on` + 菜单里 `presented per real frame` 应降到 **1** |

**为什么可以齐发而不损失归因**：三者各自的日志行互不重叠，
`presented per real frame` 一条就把 v0.60 是否生效说清楚（**菜单里变成 1 = SDK 接管了**）。

---

## 3. 本轮的判定：哪些是确证的，哪些不是

### 确证（有直接证据）

- **`jitterX` / `jitterY` 是孤儿变量**：全仓只有 `FrameGen.h:177-178` 声明与
  `Streamline.cpp:422` 读取两处，**零运行时写入** ⇒ `c.jitterOffset` 恒 {0,0}。
  与 `engineFrameCount` 同族（生产者同为 v0.50 拔掉的 `OnMainUpdateJitter`）。
  同仓库 `FidelityFX.cpp:175-176` 的 FSR3 路径接了引擎真实 jitter —— **自证矛盾**。
- **`reset` 每帧置位**：Transfusion `[MOTION]` 连续帧 `reset=1`（call=0/1/2/3）。
- **`eEnableFullscreenMenuDetection` 从未启用**：源码可读，`opts.flags` 零引用。

### ★ 上一轮的一个误判，已纠正

我曾说「第三个孤儿是相机矩阵」（`CameraViewProjUnjittered` / `CameraPreviousViewProjUnjittered`
都只有声明 + 读取）。**错了。** `FrameGen.h:69-90` 的注释写明 `FrameBuffer` 是
**引擎 per-frame 常量缓冲的内存镜像**（`Matrix CameraViewProjUnjittered; // c24`），
字段行尾的 `c24` / `c32` / `c80` 是**引擎寄存器偏移**，这些字段**本来就不该由 DFG 写**。

⇒ 必须区分两类「零写入」：

| 类型 | 特征 | 零写入的含义 |
|---|---|---|
| A 类：本插件变量 | 无 `c<偏移>` 注释；以 `Get().X` 右值出现 | **真 bug**（`engineFrameCount`、`jitterX/Y`） |
| B 类：引擎缓冲镜像 | 字段行尾带 `// c24` 这类寄存器注释 | **正常** —— 值来自 `SetMappedFrameBuffer()` 灌入的引擎内存 |

所以 `clipToPrevClip = identity` 的正确问法是「**那块引擎内存在 c24/c32 偏移上的值为什么是单位矩阵**」，
而不是「谁忘了写」。

### 尚未解决（不影响本轮判断，但不能假装不存在）

- `jitterOffset` 恒 {0,0}：**在主菜单里无害**（引擎不渲染 3D 世界时 jitter 本就该是 0），
  所以它不是菜单闪的因。**在游戏内有影响**，但那需要一个符号验证 ——
  SDK 定义是 `//! Specifies pixel space jitter offset`（**像素空间**），
  换算式与 FSR3 一致（`projectionPosScaleX * swapchainW / 2`），
  但仓库里遗留的负号（`-Get().jitterX`）来自一个「值恒为 0」的时代，**从未被验证过**。不许猜。
- `clipToPrevClip = identity`：成因未定（引擎缓冲偏移 or 该帧确实没写这组寄存器）。

---

## 4. 测试步骤与判据

重启游戏即可，无需改配置。

**① 主菜单停 10 秒** → 看日志：

| 日志 | 含义 |
|---|---|
| `DLSSG flags: fullscreenMenuDetection=on (v0.60)` | 这一刀已装载（只出现一次） |
| `DLSSG presented per real frame = 1 (status=0)` | **SDK 接管了菜单** —— 这一刀生效 |
| `DLSSG presented per real frame = 4` | SDK 没接管 —— 只剩 `reset` 边沿这一道防线 |
| `RESET probe: menuOpen=true reset=0` | v0.59 生效 |
| `constants: ok=` 递增 / `fail=0` | v0.58 仍然正常 |

**② 按回车进游戏走一段** → `presented per real frame` 应回到 **4**（世界里插帧必须跑）。

日志路径：
`C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`

**主观三选一**（请明确告诉我是哪种）：
1. 好了 — 菜单不闪，进游戏也正常
2. 还闪 — 菜单依旧
3. **变成重影/拖影** — 方向对但力度不足（`reset` 不丢历史了，菜单动画被插值）

---

## 5. 如果还闪，下一顺位（按证据强度）

1. **`jitterOffset` 接引擎真实来源**（`projectionPosScaleX/Y`，符号先用探针打出来确认量级）
2. **`clipToPrevClip` 追引擎缓冲来源** —— `FrameGen.cpp` 里 `SetMappedFrameBuffer` 的指针怎么来的、
   偏移是否与当前游戏版本一致（ENB 是否插过手）
3. **UI 层**：`Streamline.cpp` 把含 UI 的 backbuffer 标成 `kBufferTypeHUDLessColor`（`uir=0`、`suppliedTexture=0x0`）
   —— 唯一完全没测过的一层

---

## 6. 回滚

```bat
copy /Y "D:\workbuddy2\backup\menuflag_v060_20260917_212842\Streamline.cpp.bak" ^
        "D:\Modding\DynamicShaderFrameGen\src\Streamline.cpp"
```
然后 `D:\Modding\DynamicShaderFrameGen\build_vs.bat` 重新编译。

只回退 v0.60 一行（保留 v0.58/v0.59）时，删掉
`opts.flags |= sl::DLSSGFlags::eEnableFullscreenMenuDetection;` 这一行即可。
