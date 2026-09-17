# v0.56 验证清单 — 重启游戏后照这个看

状态：**已部署，未验证**。构建产物 md5 `5a51dfb54b50ac22408a6578447604bb`（1221632 B），
与生效部署副本**字节一致**（`E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\`）。

这一轮不是猜的：**同一两块缓冲被三种方式描述了三个不同的尺寸**，而其中一个是错的。
证据链、四个独立来源全在第 4 节。修的就是它。

---

## 一、必须先做的一步

**完全退出游戏再重开。** DLL 是进程载入期加载的，热更新无效。

另外确认一下你是从哪个 MO2 实例启动的：

| 实例 | mods 目录 | 里面的插件 |
|---|---|---|
| **`Skyrim Special Edition (3)`**（profile `DIPEI`） | `E:\EJ\mod\mods` | **v0.56 ✅ 生效** |
| `EJ-ENB`（profile `ej-v3`） | `E:\ENB-EJ\mod\mods` | 9月11日旧版，`Provider=0`，**没有 MFG** |

如果你平时是从 `EJ-ENB` 启动的，那这一整套 MFG 从来没生效过 —— 告诉我，我改那一边。
另外 `D:\EJ-1.0\MOD\mods\`、`C:\Users\Administrator\Desktop\DynamicShaderFrameGen\`、
`C:\Users\Administrator\fg_rebuild2\` 三处也有同名插件，**都是过期副本**，别拿它们判断版本。

---

## 二、进游戏后看四行日志（都在 `Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`）

### 1. 本次修复的回读证据（最重要）

```
[Streamline] DLSSG tag dims: hudless/scaling-output=2560x1440 depth=2560x1440 mvec=2560x1440 - ...
[Streamline] DLSSG options dims: color=2560x1440 mvecDepth=2560x1440 ...
```

**判决标准：`depth=` 与 `mvec=` 必须都是 2560x1440。**

| 读到 | 含义 |
|---|---|
| 三个都是 `2560x1440` | **修复生效** —— 声明与实际一致了 |
| `depth=1706x960` | 修复没进游戏（版本没换 / 启动的不是这个实例），回第 1 节 |
| 这行完全不出现 | 游戏没走到 DLSS-G 打 tag 的阶段，先看 `Provider in effect this session` |

### 2. 是否真在插帧（v0.55 就加的）

```
[Streamline] DLSSG presented per real frame = N
```

| 读到 | 含义 |
|---|---|
| `= 4` | 4x 真在出帧 |
| `= 1` | 选项被接受但一帧没插 |
| `1`/`4` 交替刷 | 两个 pacer 在抢呈现通道 |

**交叉验证在同目录的 `D:\ENB-EJ\Skyrim Special Edition\DLSSG-Transfusion.log`：**

```
DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
```

上一次这行**已经读到 4x** —— 也就是说「能多倍帧生成吗」这个问题，答案早就是**能**。
「闪」和「没出帧」从来不是同一个问题，别混在一起判断。

### 3. 相机矩阵是否是活的（本次新增，唯一无法静态定案的一条）

```
[Streamline] MOTION probe: clipToPrevClip maxDevFromIdentity=0.000xxx r3=(...)
```

**请一边走/一边转视角再看这行。** 它每 600 帧打一次。

| 读到 | 含义 |
|---|---|
| 走路时明显 > 0（比如 0.01 以上） | 正常，矩阵是活的 |
| **走路时仍然 ≈ 0** | **大问题**：上一帧 viewProj 没被更新，DLSS-G 的相机重投影被静默丢掉，只有运动矢量在撑着 |
| 主菜单/加载时 ≈ 0 | 正常（相机确实没动），不用管 |

Transfusion 的日志在 16:34 那次只打了头 4 次，全是 `clipToPrev=identity` ——
那会儿正在加载，所以**不能**据此说是 bug；但也**没能排除**。这条探针就是为它加的。

### 4. Present 是不是被允许撕裂（本次新增）

```
[FrameGen] Present called with SyncInterval=0 Flags=0x200  [ALLOW_TEARING - tearing permitted]
```

只在 flag 变化时打。出现 `[ALLOW_TEARING]` 说明引擎确实在要求无同步呈现 ——
那画面撕裂就有了合法通道。**这行没出现**（只有普通 Flags=0x0）就是干净的。

---

## 三、判定：修好了没有

**修好了 = 三件事同时成立**

1. `depth=` 与 `mvec=` 都是 `2560x1440`
2. `DLSSG presented per real frame = 4`（稳定为 4，不是 1/4 跳）
3. 走起来画面**不再一直闪**，`Jitter` 明显下降

**只看 1 不够** —— 1 只证明声明对齐了；闪不闪要你亲眼看。

---

## 四、这轮为什么这么改（证据链）

DLSS-G 拿到的两块缓冲，被三种方式描述了三个尺寸，而我写死的那个 1706x960 是错的：

| 来源 | 颜色 | depth / motion |
|---|---|---|
| 互操作纹理实际尺寸 | 2560x1440 | **2560x1440** |
| `DLSSGOptions::mvecDepthWidth/Height` | 2560x1440 | **2560x1440** |
| `ResourceTag::extent`（旧代码写死） | 2560x1440 | **1706x960 ← 错** |

四个独立来源：

1. **运行日志**：`depth interop texture created lazily (R32_FLOAT 2560x1440)` / `mvec ... (2560x1440)`
2. **拷贝代码**：`CopyDepthToShared` / `CopyMvecToShared` 的 viewport 设成
   `swapChainDesc.Width x Height` 并画家全屏三角形 —— 整张纹理都是有效内容，不是个角
3. **NVIDIA 头文件 `sl_dlss_g.h`**：`mvecDepthWidth` = *"Expected width of the input
   render targets (depth, motion-vector buffers etc)"* —— 就是这两个缓冲自己的尺寸
4. **NVIDIA 头文件 `sl.h`**：`ResourceTag::extent` = *"The area of the tagged resource
   to use (if using the entire resource leave as null)"* —— 声明 1706x960 等于告诉
   DLSS-G「只用这张 2560 缓冲的左上角」

⇒ 颜色/运动矢量的空间对应差了 **1/0.667 = 1.5 倍**，而这一对正是生成每一张插帧的输入。
**每一张插帧的运动都是错的** → 屏幕在「正确的真实帧」和「错误的插帧」之间按生成频率交替
→ 就是「一直闪烁」。

外部旁证：Transfusion 自己把它收到的 tag 打了出来（16:34 那次）：

```
[MOTION-TAG] type=hudless         rect=(0,0 2560x1440)
[MOTION-TAG] type=scaling-output  rect=(0,0 2560x1440)
[MOTION-TAG] type=depth           rect=(0,0 1706x960)   ← 错
[MOTION-TAG] type=motion          rect=(0,0 1706x960)   ← 错
```

那个 1706x960 是 v0.34 留下的：当时互操作纹理**确实是**渲染分辨率，所以是对的；
v0.7.8 为了 FSR3 把它们改成输出分辨率，**tag 没跟着改**。

**改法**：一个数字都不再写死。extent 取自 D3D12 资源本身（`GetDesc()`），
options 的 mvec/depth 尺寸取自 D3D11 互操作纹理。单一来源，改也不会再脱节。
同一类问题还有一处：`CreateInterop` 的主动路径按引擎 kMAIN desc 建纹理（渲染分辨率），
而惰性路径强制输出分辨率 —— 同一块缓冲会因先跑哪条路径而尺寸不同。两条统一为输出分辨率。

---

## 五、这次**故意没改**的东西

**Reflex 限帧仍是 `刷新率 / 倍率 - 1` = 39fps（160Hz 屏上呈现 156）。**

我本来把它当 bug（160/4 = 40 正好整除），查完发现**不能动**：156 就是比面板上限低 4Hz，
而这正是通行建议（"cap a few Hz below max refresh"，避免顶到 VRR 上限掉回 VSync）。
**如果你的显示器跑着 VRR/G-SYNC，面板会跟着 156fps 那条流走，不存在节拍对不齐。**
留它不动，本次唯一的行为变量才是 extent 修复，不然又变成一个说不出因果的混改。
显示器没开 VRR 的话，把 INI 里 `ReflexFpsLimit` 填 `40` 试（免编译）。

---

## 六、如果还是闪，按这个顺序动，**一次只动一个**

1. **`"disableMenuDetection": false`**（`DLSSG-Transfusion.json`，需重启）
   你现在是 `true`。DLSS-G 规范要求菜单/加载/暂停时 `DLSSGOptions::mode = eOff`，
   `true` 等于把这层保护关了。**如果闪烁只在菜单/加载界面，就是这条。**

2. **`"mode": "dynamic"` + `"dynamicTargetFrameRate": 160`**（JSON，需重启）
   你现在是 `"mode": "fixed"` + `"multiplier": 4`。上一次 `[PERF]` 是
   `FPS: 34.6 | Jitter: 16.31ms | 1% Low: 30.8` —— 34.6 × 4 = 138，够不到 160。
   固定 4x 在跑不满 40fps 的场景里必然呈现欠发 + 节奏抖。dynamic 会自己降档补上。

3. **`Ctrl+Alt+3` 降到 3x**（免重启，Transfusion 自带热键）
   3x 只要渲染 53fps，比 4x 的 39fps 富余得多。**40 系上 4x 本就是绕硬件限制的**
   **灰色地带，3x 才可能是稳的上限。**

4. **`NeuralRenderingEnabled=0`**（INI，需重启）
   DLSS5 的神经细节合成跑在**插帧的输入**上（日志 `DLSSNR ... frames=179` 说明它在跑）。
   合成出来的高频细节是光流追不稳的，会让插帧的细节闪。关掉做一次 A/B 很便宜。

---

## 七、回滚点

| 对象 | 回滚方式 |
|---|---|
| 插件代码 | `git checkout HEAD~1 -- src/`（v0.55 = 提交 `d781672`） |
| v0.56 源码/二进制副本 | `/d/workbuddy2/backup/framegen_v056_src_20260917/`（含 `*.pre_v056` 原始文件） |
| v0.55 二进制 | 无独立备份，但可由 `git checkout d781672` 重新编译（部署期无人工干预） |
| JSON | `/d/workbuddy2/backup/transfusion_json_20260917_163940/DLSSG-Transfusion.json` |

---

## 八、已知但不要动 / 说明

- **`version.dll` 与 `dinput8.dll` 两个副本都在进程里**，活跃的是 `version.dll`，
  单实例。加载者未定位，但组合已被证明能工作 → **闪烁定性前不要改名/删除。**
- **别在插件菜单里点 "Save to INI"**：MO2 下会写进 `overwrite\`，优先级高于 mod 目录，
  会长期盖住模板。
- `DXGISwapChainProxy::ResizeBuffers` 是**直接转发**给真 swapchain 的，插件自己的
  `swapChainBuffers[3]` 不会重建。窗口尺寸一变（alt-tab 触发分辨率变化等）就会变成
  悬空引用。目前无边框固定尺寸下不会触发，**先记着，不在本轮改动范围内**。
- `GetFrameLatencyWaitableObject()` 在 DLSSG 分支建的 swapchain 上（已去掉
  `FRAME_LATENCY_WAITABLE_OBJECT`）会返回 `INVALID_HANDLE_VALUE`。本插件不调用它，
  只有引擎可能调；若引擎在等它，那也只是退化成不等（pacer 本来就在管节奏），无害。
