# 「一直闪」的真正病灶：改错了 INI —— 游戏读的根本不是那一份

时间：2026-09-17 20:40
症状：MFG 4x 已生效，但有 OSD 显示 `39/10 fps 4x`，画面**持续闪烁**，主菜单就闪。

---

## 一、先纠正我上一轮的错误

19:50 我把 `C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SkyrimPrefs.ini`
的 `iSize` 从 2560x1440 改成 3840x2160，回读也确认了。

**但这次启动后游戏仍然报：**

```
[OPTIONS] Game DLSS-G options: structVersion=5 mode=eOn frames=3 uir=0 color=2560x1440 flags=0x00000000
```

`color=2560x1440` —— swapchain 尺寸**一点没变**。

**原因：MO2 的 profile 专属 INI 是开启的，游戏读的是另一份文件。**

```
E:\EJ\mod\profiles\DIPEI\settings.ini
    [General]
    LocalSettings=true          <-- 「Profile-specific game INI files」= 开
```

`LocalSettings=true` 时，MO2 的 usvfs 会把游戏的每一次 INI 读取重定向到 profile 目录，
游戏读的是：

```
E:\EJ\mod\profiles\DIPEI\skyrimprefs.ini      <-- 真正的文件，写的是 iSize W=2560 / iSize H=1440
```

而 My Games 那份是**诱饵**，改了完全没用。我上一轮查 profile 目录时漏掉了小写的
`skyrimprefs.ini`，得出了"没有 profile 专属 ini"的错误结论 —— 这一点我认。

旁证：profile 目录里躺着 `skyrimprefs.ini.bak_20260830_4K`，内容正是 `iSize W=3840 H=2160`，
说明 8/30 之前你用的就是 4K，9/7 才改回 1440p。

---

## 二、为什么尺寸不匹配会导致「一直闪」

DXGI 的 **Independent Flip** 有两个硬条件：swapchain 的**尺寸**和**格式**都必须等于当前显示模式。

| 项 | 实测 |
|---|---|
| 显示模式 | **3840×2160 @ 160Hz**（RTX 4080 SUPER） |
| swapchain | **2560×1440** ← 不匹配 |
| 窗口化游戏优化 `SwapEffectUpgradeEnable` | 1（已开，不是它的问题） |
| 禁用全屏优化 | 不存在（没被禁用） |

尺寸不匹配 ⇒ 只能走 **DWM composed flip** ⇒ Streamline pacer 无法把呈现时刻锁到刷新周期。

这解释了本次会话里的两个异常：

**(1) 倍率长时间起不来。** `DLSSG-Transfusion_perf.csv` 统计：

| 时间窗 | 4x 帧 | 未生成帧 |
|---|---|---|
| 20–30s | 0 | 367 |
| 30–40s | 0 | 392 |
| 40–50s | 154 | 238 |
| 50–60s | 56 | 0 |

1207 帧里只有 **210 帧**（17%）真正生成，前 46 秒一帧都没生成。

**(2) 插件作者自己写过这个症状。** DFG 源码 v0.55 注释：

> "A 1 -> 4 transition, or a **1/4 oscillation (what two pacers fighting over one swap chain looks like)**"

DFG v0.54 的 INI 注释：

> "the present queue backs up, the SL pacer loses its rhythm and **the picture flickers continuously**"

**注意**：作者的节拍公式 `render fps × multiplier ≤ refresh rate` **只算刷新率、不算分辨率**。
刷新率算对了（160/4−1 = 39fps cap），尺寸不对，独立 flip 照样不成立。

---

## 三、本次改动（唯一一处，两行）

文件：`E:\EJ\mod\profiles\DIPEI\skyrimprefs.ini`

```
第146行  iSize W=2560  ->  iSize W=3840
第155行  iSize H=1440  ->  iSize H=2160
```

等长替换，字节数（4162）、行数（197）、行尾（197 个 CRLF）全部不变。
`diff` 对备份的结果就是这两行，没有别的。

- 脚本：`D:\Modding\DynamicShaderFrameGen\tools\fix_profile_ini_4k.py`（断言 + 幂等守卫 + 备份 + 回读，默认干跑）
- 备份：`D:\workbuddy2\backup\profile_ini_4k_20260917_204315\skyrimprefs.ini.bak`
- My Games 那份上轮已改成 4K，与 profile 保持一致（万一哪天关掉 LocalSettings 也不会翻车）

**`bBorderless=1` / `bFull Screen=0` 没动，倍率仍是 4x，没有回退。**

---

## 四、连带纠正：`RenderResolutionScale=0.44` 之前是错的

DFG 的定义（`src/DX12SwapChain.cpp:171`）：

```cpp
renderWidth  = swapChainDesc.Width  * renderScaleX;
renderHeight = swapChainDesc.Height * renderScaleY;
```

我 19:50 把 `RenderResolutionScale` 改成 0.44，**是按「swapchain 会变成 4K」推的**：

```
3840 × 0.44 = 1690     ≈ 你原本的 1707×960（2560×2/3）✓
```

但 swapchain 当时**没变**，于是真实渲染分辨率变成了：

```
2560 × 0.44 = 1126  ×  1440 × 0.44 = 634     <-- 比原来砍掉 56%
```

**这是我上一轮"只改了一半"造成的额外变量。** 现在 swapchain 真的到 4K 了，0.44 才回到设计意图：

| | swapchain | 内部渲染 | 输出 | 上采样比 |
|---|---|---|---|---|
| 你的原始配置 | 2560×1440 | 1706×960 | 2560×1440 | 1.50x |
| 本次修复后 | **3840×2160** | **1690×950** | **3840×2160** | 2.27x |

渲染像素数基本不变（1690×950 vs 1706×960，少 1%），**所以这不是性能回退**；
换来的是输出分辨率匹配面板、独立 flip 成为可能、DWM 那次多余的缩放消失。

---

## 五、下次启动怎么验证

**不用重编译，直接重启游戏**（swapchain 只在创建时确定一次，热改无效）。

```bash
grep "DLSSG options dims" "C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.log"
```

期望：

```
DLSSG options dims: color=3840x2160 mvecDepth=3840x2160
```

出现 `color=3840x2160` ⇒ 前提成立。同时观察 OSD：`39/10` 里第二个数应当上升，
呈现应当连续。也可以直接看生成率：

```bash
awk -F, 'NR>1 && $4>1 {g++} END {print "generated frames:", g+0}' "D:/ENB-EJ/Skyrim Special Edition/DLSSG-Transfusion_perf.csv"
```

---

## 六、如果还闪，按这个顺序单变量（每次只动一个）

1. **`disableMenuDetection`: `true` → `false`**
   现状是**关掉了** Streamline 的菜单节流（README 原文 "Disable Streamline menu throttling"），
   所以主菜单也会插帧。而 DFG 把**含 UI 的后缓冲**标成了 `kBufferTypeHUDLessColor`（"不含 UI"）——
   主菜单画面几乎全是 UI，这个标记在菜单场景下是错的。把节流恢复，主菜单就不会插帧。
   **如果你能确认「主菜单闪、进了游戏之后反而稳定」，那基本就是这一条。**

2. **`multiplier`: `4` → `2`**（纯诊断，看是否与倍率相关）

3. **`qualityValidWarp`: `true` → `false`**（作者自己标注过启动崩溃风险）

另外两个已知的 DFG 源码级缺陷，**目前不影响呈现、暂不动**，但记在这里：
- `clipToPrevClip` 恒为 identity（每次运行都打印 `maxDevFromIdentity=0.000000`）⇒ DLSS-G 失去相机重投影
- 每帧调两次 `slSetConstants`，第二次返回 27 = `eErrorDuplicatedConstants`

---

## 七、本次排除项（有新证据的）

- **不是 ENB 冲突**：ENB 的 `d3d11.dll` 导入表 `WinHttp`/`WinInet`/`ws2_32` 全 0；`enblocal.ini` 里
  `EnableFPSLimit=false`、`ForceVSync=false`、`EnableProxyLibrary=false`
- **不是代理重复**：`Patch worker started` 只出现 1 次；`slSetD3DDevice pending=0`（18:05 那次 101 秒挂起未复现）
- **不是崩溃**：本次无 `crash-*.log`、无 WER、无 TDR；`crash.log` 只有 1 条良性 first-chance + 215 条 MODULE
- **不是 NGX 被改坏**：`C:\ProgramData\NVIDIA\NGX\models\...` mtime 仍是 08-28，Transfusion 只在内存 patch
- **不是显存**：16GB，README 警告的是 8GB 场景
- **不是 mvecScale**：已是 `{1.0000, 1.0000} (override=1.00)`，改动已生效

---

## 八、关于 OSD 上的 `39/10 fps 4x`

这是 **Transfusion 的 overlay**（`showOverlay: true`），格式串取自 DLL：

```
%u/%u fps %ux
```

与之对应的 JSON 字段是 `"realFpsMilli":%u,"dlssFpsMilli":%u` ⇒ 两个数是 **real fps / dlss fps**。
`39/10` 意味着渲染 39fps、而实际生成的帧只有约 10fps（远低于 4x 应有的 117fps）——
这与 perf.csv 里「只有 17% 的帧真正生成」是同一个事实的两种度量。
overlay 开关热键：**Ctrl+Alt+O**。
