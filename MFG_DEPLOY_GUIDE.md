# DynamicShaderFrameGen — 多倍帧生成（MFG）状态说明

**版本**：v0.53 · 构建 `Sep 17 2026 15:18` · DLL MD5 `e176f8bb0f3605f51d070be342b993f2`（1214976 字节）
**工程**：`D:\Modding\DynamicShaderFrameGen`（提交基线 `c9b531c` = v0.52 → 本版 v0.53）
**Git 回退点**：`c9b531c`（v0.52，工作区干净，一条 `git checkout -- .` 即可整体回退）
**硬件**：RTX 4080 SUPER（Ada / sm_89），驱动 616.64 —— 原生 DLSSG 上限锁 1（=2x），
>2x 必须靠外部内核解锁器。这就是 `version.dll` 存在的原因。

---

## 〇、当前状态：装了什么、哪一半缺

| 半边 | 位置 | 状态 |
|---|---|---|
| **代码：把请求发出去** | `MFGMaxFramesOverride=3` | ✅ 已配（`=0` 时阶梯探测只会请求硬件上限 1→2x）|
| **内核：让请求能执行** | `D:\ENB-EJ\Skyrim Special Edition\version.dll` | ✅ DLSSG-Transfusion v1.4.1，SHA256 `a7f517ca…` 与官方发布包一致 |
| **配置生效层** | `E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini` | ✅ `Provider=1` / `DLSSGFramesToGenerate=3` / `MFGMaxFramesOverride=3` |

```
Provider=1                 ; DLSSG 路径
DLSSGFramesToGenerate=3    ; 4x
MFGMaxFramesOverride=3     ; 抬到 4x（=0 会被压回 2x）
NeuralRenderingEnabled=1
```

> 活动 MO2 实例：档案 **DIPEI**，`base_directory=E:\EJ\mod`，
> `gamePath=D:\ENB-EJ\Skyrim Special Edition`，构建部署目标 `PLUGIN_DEPLOY_DIR=E:/EJ/mod/mods/DynamicShaderFrameGen`。

### v0.53 全链路审计（逐项对着磁盘核，不靠推断）

| 检查项 | 结果 |
|---|---|
| 部署 DLL 与构建产物 | ✅ 字节一致，MD5 `e176f8bb0f3605f51d070be342b993f2` |
| 生效 INI | ✅ 就是上面那份，`Provider=1` |
| `overwrite\SKSE\Plugins\` 有没有 FrameGen INI | ✅ **没有** → 不会盖住 mod 里的模板 |
| 同实例里另外两份同名 INI（`…Dlss5-v047b-20260911`、`…NR`） | ✅ 在 DIPEI 里都是 `-` **禁用**，不参与文件冲突 |
| 竞争的解锁器 RTXMFG-Universal | ✅ 已失效：它的 `dinput8.dll` 在 2026-09-11 被改名成 `dinput8.dll.disabled` |
| Streamline 版本 | ✅ 游戏根目录与 mod 目录**都是 2.13.0.0**，无版本打架 |
| `nvngx_dlssg.dll` | ✅ 3.10.8，在 Transfusion 支持区间内 |

**结论：部署侧没有发现任何会阻止 MFG 的问题。** 剩下的未知数只有一个 ——
运行时到底接不接受 >2x（见第四节怎么看）。

---

## 一、v0.52 修的是什么（"切换 DLSS 没有任何变化"）

### 日志给出的硬事实

会话（13:59:55 启动）唯一被记录的菜单交互是：

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

`Provider` 只在 `DX12SwapChain::CreateSwapChain()` 里被消费**一次**：它决定 `dlssgMode`、
`BufferCount`（DLSSG 三缓冲 / FSR3 双缓冲）、以及整条 D3D12 proxy 路径。这些在 swapchain
创建时定型，运行中改内存变量不会重建任何东西。

> 这是结构性的，**没有热切方案**。原来那条 `ImGui::Combo` 连一行日志都没写，所以"切了没反应"
> 连个痕迹都查不到。

**② 改动根本没落盘**

下拉框只改内存里的 `s.provider`；只有点 "Save to INI" 才写文件。而全盘检查证明那次保存从未成功：

| 检查 | 结果 |
|---|---|
| 全盘 9 份同名 INI，指纹比对日志 | 生效的是 `E:\EJ\mod\mods\DynamicShaderFrameGen\...ini`（`Provider=0`）|
| `overwrite\SKSE\Plugins\` 有 FrameGen INI 吗 | **没有** → 说明 Save 从未成功过 |
| MO2 档案 `DIPEI` 里哪些 FrameGen mod 启用 | 只有 `+DynamicShaderFrameGen`；另两个 v047b / NR 都是 `-` 禁用 |

**③ 旧版 "Save to INI" 还会静默删键**

它把文件**截断重写**成 17 个键，于是 `QualityMode` / `RenderResolutionScale` / `Sharpness` /
`FpsOverlay` / `EnableUpscale` / `PresetDLSS` 整行消失 —— 自定义渲染比例会被无声重置。

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
| 7 | DLSSNR 诊断改打 **Apply 真正吃的输入 + NGX 成功帧数** | 以前那条日志无论 NR 有没有跑都显示 true，无法证伪 |
| 8 | INI 标注 `EnableUpscale`/`PresetDLSS` 为 parsed-but-not-wired | 不再让人追死开关 |

---

## 三、v0.53 改了什么（"那个 FPS 数字一直在骗人"）

### 找到的缺陷：屏幕上的帧率是**写死 ×2** 的

```cpp
// 旧代码
const float mult = a_fg.fgActive.load() ? 2.0f : 1.0f;
std::snprintf(buf, sizeof(buf), "%.0f FPS", s_fps * mult);
```

两个后果，第二个恰好就是"切换了没有任何变化"的直接来源：

1. 它**不知道 MFG 存在** —— 3x / 4x 永远不可能显示出来；
2. 只要 `fgActive` 为真就乘 2 —— 就算运行时**拒绝了**请求、一帧都没插，屏幕照样打出翻倍的数字。

⇒ 从 FSR3 切到 DLSSG 时，屏幕上的数字**按构造就不可能变**。

**修法**：倍数改为来自运行时自己的报告；没在生成时**不做任何放大**，直接标出来。

```
DLSSG 路径 + 实测在生成   →  例如 220 FPS
DLSSG 路径 + 没在生成     →  55 FPS (MFG off)     ← 不再假装翻倍
FSR3 路径 + FG 开着       →  110 FPS              ← 2x，有 dispatch 探针佐证
```

### 新增的证据通道：一个**测量值**，不是算出来的值

Streamline 头文件对 `sl::DLSSGState::numFramesActuallyPresented` 的注释是关键：

```cpp
//! Number of frames presented since the last 'slDLSSGGetState' call
uint32_t numFramesActuallyPresented{};
```

它是**区间计数**（距上次查询之间呈现了几帧），不是累计值。而 `SetDLSSGOptions` 每真实帧跑一次
⇒ **这个值就是那一帧真正生效的倍数**：`1` = 完全没插帧（无论我们请求了几倍），`4` = 4x。

v0.53 起每帧记录、并按周期打日志：

```
[Streamline] DLSSG presented per real frame = 4 (status=0) - 1 means NO interpolation
```

**这是本项目里第一个"测出来的"数字**（此前 `cap~=real*4` 那行从 v0.51 起就明确标注为
`COMPUTED not measured`）。

### 顺带修掉的

- `version.rc` 的字符串版本写的是 `0.50.0.0`、`FILEVERSION` 写的是 `0,52,0,0` —— 两边现在统一为 **0.53**。
- INI 里补上了 **DLSSG-Transfusion 自己的热键**说明（见下节）——因为真正的倍率控制权在它手上。

### Transfusion 的真实用法（务必知道）

它不是靠游戏的画面菜单控制的，而是**自带热键、实时生效、不用重启**：

| 热键 | 作用 |
|---|---|
| `Ctrl+Alt+2` / `Ctrl+Alt+3` / `Ctrl+Alt+4` | 切到 2x / 3x / 4x |
| `Page Up` / `Page Down` | 逐档调倍率 |
| `Ctrl+Alt+D` | 切换 fixed / dynamic 模式 |

它的自绘覆盖层由 `DLSSG-Transfusion.json` 里的 `"showOverlay": true` 打开（当前就是开的），
日志由 `"logPerformance": true` 打开。**别去游戏图形菜单里找这个开关。**

---

## 四、进游戏后怎么验证（每次启动覆盖日志）

日志：`Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`

**证据分三层，别混：**

| 层级 | 看这一行 | 含义 |
|---|---|---|
| **① 路径走对了**（必要） | `Provider in effect this session: 1 (DLSSG)` | swapchain 走了 DLSSG 路径 |
| | `FPS probe: ... cfgProvider=1` 无 `(CHANGED …)` | 在跑的和 INI 写的一致 |
| **② 选项被接受**（必要，**不充分**） | `MFG probe: runtime ACCEPTED 4x` | `slDLSSGSetOptions` 没报错。**但它只说明"选项被收下了"** |
| **③ 帧真的生成了**（**充分**） | `DLSSG presented per real frame = 4` | **唯一能证明 4x 真的在跑的行。** `=1` 就是没插帧 |

> v0.52 的文档把第②层写成了"唯一可信的证据" —— 那是错的：`ACCEPTED` 只代表选项通过，
> 不代表有帧被生成。第③层才是实测值，v0.53 才补上。

辅助观察：

- 屏幕右上角：`220 FPS` 这种**没有后缀**的数字 = 实测在生成；出现 `(MFG off)` = 没生成。
- `REJECTED` 大量出现 → 阶梯探测会逐帧降档并锁定，画面不该再闪。
- Transfusion 自己的覆盖层（`Ctrl+Alt+…` 切换时会显示当前倍率）。

**判读**：

- ③层 `= 4` + 画面正常 → 成功，4 倍到手。
- ②层 `ACCEPTED` 但③层 `= 1` → **选项被收下但没出帧**：解锁器没真正供上内核。
  按 `Ctrl+Alt+3` / `Ctrl+Alt+4` 手动切一档再看；仍为 1 就去看 Transfusion 的日志/覆盖层。
- ②层一路 `REJECTED` 到 2x → 解锁器没生效。

---

## 五、诚实的边界

- **倍率上限由运行时决定**，不是写了就一定拿到。`dlssgFramesToGenerate` 只是请求。
- **Provider 切换永远需要重启**（swapchain 路径一次性定型）。v0.52 做的是让它"落盘 + 记日志 +
  界面提示"，不是让它热切。
- **`Provider=1` 的 >2x 尚未在本机验证过。** 但 DLSSG 2x 本身是**跑通过的**（代码里留有
  v0.27–v0.33 的实证记录："DLSS-G IS available 实锤"、"插帧正常 → 频闪消除"）。
  所以未知数只有"运行时接不接受 >2x"这一条，不是整条链路。
- `EnableUpscale` / `PresetDLSS` 是**死开关**（v0.48 移除超分后遗留），已在 INI 里标注。
- 6x 需要把 `MFGMaxFramesOverride` 与 Transfusion 的 `multiplier` 一起提到 6；4x 是当前两边一致的配置。
- **⚠️ 别在 GUI 里点 "Save to INI"（以及尽量别动那些"改动即存"的开关）**：
  写侧路径是 `Data/SKSE/Plugins/…`，在 MO2 下会落到 **`overwrite\`**，而 `overwrite\` 的优先级
  **高于 mod 目录**。一旦写进去一份，之后我再更新 mod 里的 INI 模板就**会被它盖住**，
  又变成"改了没生效"。当前 `overwrite\` 是干净的，保持这样。
  （而且那次重写只写键值、**不写注释**，本文件里这些说明会一起消失。）

---

## 六、回退（10 秒）

1. **只退回 FSR3**：菜单里把 Provider 切回 `FSR3`（v0.52 起立刻写 INI），或直接改 INI 的
   `Provider=0`，重启即生效。
2. **连解锁器一起撤**：删掉 `D:\ENB-EJ\Skyrim Special Edition\version.dll` 与
   `DLSSG-Transfusion.json`。
3. **回退代码**：`cd D:\Modding\DynamicShaderFrameGen && git checkout -- .`（回到 `c9b531c`，v0.52），
   再跑 `tools/build_incremental.py` 重新构建部署。
