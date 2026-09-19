
---

# 36. 进程里有两个 DLSS-G 驱动 —— 12 局日志把冻结切给了 DLSS-G 支线

日志：`docs/runlogs/*.log`（12 局，09-19 14:55 → 09-20 00:58），外加第三方驱动自己的四份文件
`DLSSG-Transfusion.{log,crash.log}` / `_perf.csv` / `DLSSG-Transfusion.json`。
触发：用户重启电脑后要求继续推进「多倍帧生成」（v1.23 已构建部署但**尚未运行过任何一局**）。

## 36.1 12 局对照：切分点不在倍数，在「DLSS-G 有没有参与」

| 局 | Provider | ask/accepted | Transfusion 施加 4x | 画面 |
|---|---|---|---|---|
| 09-19 14:55 → 22:38（7 局，v1.11–v1.17）| DLSSG | 4/4 | 是 | 冻结 |
| 09-19 22:54 v1.18b | DLSSG | 4/4 | 是 | **硬冻结** |
| 09-19 23:22 v1.19 | DLSSG | 4/4 | 是 | **硬冻结** |
| **09-19 23:38 v1.19** | **FSR3** | **2/0** | **从未** | **活了** |
| 09-20 00:31 v1.21 | DLSSG | 4/4 | 是 | 冻结 |
| 09-20 00:58 v1.22 | DLSSG | 4/4 | 是 | 冻结 |

**11/11 局 DLSSG 都是 `ask=4 accepted=4`。** ⇒ 第 34 章那句「4x 请求从来没被发出去」
**只对 22:54 那一局的 571/572 帧成立**；对请求路径而言，它早已通了。

**★ 22:54 那一局还否掉了「倍数太高」这条线**：那局全程 `presented per real frame = 1`（**一帧都没插**），
画面照样定死。⇒ 冻结与「有没有生成帧」无关。

**⇒ 剩下的唯一切分：DLSS-G 这条支线参与 ⟺ 冻结。**

## 36.2 第二个驱动：DLSSG-Transfusion（游戏根目录的 `dinput8.dll`）

它自己写的身份（`DLSSG-Transfusion.log:1-16`，00:58:00.077）：

```
DLSSG-Transfusion (Universal Blackwell Transfusion & Multi-Game Edition)
Build: v1.4.0-pure-warp (Sep 14 2026 18:42:03)
Loaded as: dinput8.dll
Proxied system DLL: C:\WINDOWS\system32\dinput8.dll
Module Path: D:\ENB-EJ\Skyrim Special Edition\DINPUT8.dll      （540,672 B，Sep 18 19:44）
Initial control: mode=fixed multiplier=4x ... blackwellTransfusion=1 disableMenuDetection=1
```

**它 Direct Detours 的是同一批入口**（00:58:11.622）：

```
(slGetFeatureFunction, slInit, slSetD3DDevice, slSetVulkanInfo,
 slSetData, slSetConstants, slSetTag, slSetTagForFrame)
```

其中 `slSetConstants`（我们发布 `clipToPrevClip` 的地方）、`slSetTag`、`slSetTagForFrame`、`slSetData`
**六个和我们插件钩的是同一个函数**。

**它还在改 DLSS-G 运行时的二进制**（每次启动都做）：

```
00:58:12.802  HUDless UIR patch applied in E:\EJ\mod\mods\DynamicShaderFrameGen\Shaders\Upscaling\Streamline\nvngx_dlssg.dll
00:58:12.840  ... in C:\ProgramData\NVIDIA\NGX\models\dlssg\versions\0\files/160_876232C.bin
00:58:12.881  ... in C:\ProgramData\NVIDIA\NGX\models\dlssg\versions\0\files/160_E658703.bin
00:58:13.772  ... 同上一份，再来一次
```

改动覆盖 **①我们 mod 目录里的 `nvngx_dlssg.dll`** 与 **②全局 NVIDIA 模型缓存**（会影响其它游戏）。
`blackwellTransfusion=1` 开在一张 **Ada（RTX 40）** 卡上，而它自己打印的内核就是 `Kernel: Ada`。

**它这一侧的 4x 没坏**：

```
00:58:35.782  Applied fixed multiplier: 4x, result=0 (eOk)
00:58:48.641  DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
00:58:51.551  [PERF] 4x | Kernel: Ada | FPS: 40.2 (24.85ms)
```

而 INI 里被记为「4x 真的能用」的 09-18 07:29 局是 `4x | Kernel: Ada | FPS: 39.6 (25.28ms)` ——
**两次数字几乎完全一致**。⇒ **Transfusion 的生成侧与"验证成功"时逐项相同。**

**但它不是全程都在生成**（`_perf.csv`，650 帧）：

```
Multiplier = 0 : 548 帧
Multiplier = 4 : 102 帧        ← frame 549 处从 0 跳到 4
```

## 36.3 时间戳级同现：闸门与它落在同一毫秒

| 时刻 | 来源 | 事件 |
|---|---|---|
| 00:58:35.782 | 我们 | `[XRAY] MENU EDGE open=1 serial=2` —— 闸门在第 **2** 帧就按住 |
| 00:58:35.782 | Transfusion | `[OPTIONS] Game DLSS-G options: mode=eOn frames=3 … flags=0x00000010` |
| 00:58:35.782 | Transfusion | `Applied fixed multiplier: 4x` + `stripped eEnableFullscreenMenuDetection (0x10 -> 0x00)` |
| 00:58:35.783 | 我们 | `[MFG] probe RUNS while the menu guard skips DLSS-G … advertised=4x accepted=4x` |
| 00:58:48.150 | 我们 | `MENU EDGE open=0 serial=566`、`blocked=564 unblocked=1` —— **13 秒后才放开** |

**这 13 秒里**：我们插件（`MenuDisableFrameGen=1`）对 `SetDLSSGOptions`/`EvaluateDLSSG` 一次都不调；
Transfusion 把 `eEnableFullscreenMenuDetection` 从选项里**剥掉**，让运行时不知道菜单开着。
**两边都不告诉运行时"现在是菜单/加载画面"。**

这不是新问题 —— v1.05 的 INI 笔记就记过同源事故：
「Transfusion set 4x, this plugin set 2x, the pacer never converged, and the frame ended inside Present()」，
那次读数是 **一帧 19480.5 ms**。区别只在于当时两边写的值不同，现在两边"同时不说话"。

## 36.4 判据与下一局

**决定性实验（单变量、可秒回退）：** 把游戏根目录的 `dinput8.dll` 改名。

```
D:\ENB-EJ\Skyrim Special Edition\DINPUT8.dll
   →  DINPUT8.dll.transfusion-off
```

★ **名字必须用 `.transfusion-off`，不能用 `.disabled`** —— 该目录里**已经**有
`dinput8.dll.disabled`（5,945,344 B，另一个 DLL）与 `dinput8.dll.rtxmfg-off`（同尺寸，Sep 18 18:01），
用 `.disabled` 会**撞名覆盖一个不相干的 5.9 MB 文件**。参照用户自己的 `.rtxmfg-off` 命名法。

**这一局会发生什么（先说清，免得白跑）：** 没有内核解锁器 ⇒ 我们插件读到
`kernelUnlocker=false`（`Streamline.cpp:265-269` 读 `GetModuleHandleA("dinput8.dll")`）⇒ 请求被夹到硬件上报的 **2x**。
**这一局不是去拿 4x，是去拿一个干净的基线** —— 而「我们的插件 + DLSS-G 2x + 无第二个驱动」**至今没跑过一局**。

| 看到 | 结论 |
|---|---|
| `[PIXEL]` 每秒一行、`chg=1`，画面能走 | 第二个驱动被证实是并因 ⇒ 回头修协同，不再改围栏 |
| 仍冻结但 `presented per real frame` 正常 | 第二个驱动被洗清 ⇒ 冻结在我们自己的 DLSS-G 呈现路径，围栏是下一个目标 |
| `[PIXEL] ERROR: … produced ZERO samples` | 仪器又坏了 ⇒ 先修仪器 |
| `hrsD == 0` | 游戏时钟停了 ⇒ 冻结在游戏里 |

**备选（想留住 4x 再测）**：只改 `DLSSG-Transfusion.json` 一个键 `"disableMenuDetection": 1 -> 0`。
但**它不能用来隔离变量**：4x 仍在，若画面依旧冻结，分不清是 4x 本身还是协同。

## 36.5 方法论

- **L45：相关性要能落成"实验可以推翻它的形式"，否则它只是故事。**
  本轮拿到 12/12 的切分（DLSS-G 参与 ⟺ 冻结）和一次**时间戳级**同现，全部是**相关性**。
  它足以把下一个实验设计成单变量隔离，**不足以**写成因果。
  判据：**如果我的结论是错的，哪个读数会不一样？** 本轮答案是「去掉第二个驱动后画面会不会活」。
- **L46：改文件名前先 `ls` 目标目录。** 我第一版卡里写 `dinput8.dll.disabled`，
  而那个名字**已被另一个 5.9 MB 的文件占用** —— 按这个操作会覆盖一个不相干的 DLL。
  **"用户会不会因此白跑或受损"这一问必须在给出指令之前问，不是之后。**
- **L39 复现**：`grep -c` 返 0 匹配 ⇒ 退出码 1 ⇒ `&&` 链断 ⇒ 后面的检查根本没跑，
  而输出看起来"只是没打印"。**这次因为我已经知道要看退出码，没有误判。**

## 36.6 收尾状态

| 项 | 值 |
|---|---|
| DLL | 1,368,576 B，md5 `83e84a781bf645ec3363b58c5fb671ec`（build == MO2 部署）|
| INI | md5 `efce89119d840670e519d219749a6476`（源树 == 部署），8 键：`Provider=1`/`DLSSGFramesToGenerate=3`/`MFGMaxFramesOverride=3`/`MenuDisableFrameGen=1`/`MenuGuardFader=1`/`InteropFenceWait=1`/`NRAllowWithFrameGen=0`/`PixelProbe=1` |
| 本轮有无新局 | **没有。** 最后一份日志仍是 00:58（v1.22），**v1.23 尚未运行** |
| 交付卡 | `docs/diagnosis-20260920-0115-two-dlssg-drivers-in-one-process.html`（15.7 KB）|
| 工具 | `tools/check_card.py` 修了 DOCTYPE 假阳性（`<!DOCTYPE html>` 被当成杂散尖括号）|

**未证 / 不说满**：Transfusion 与冻结之间是 **12/12 相关 + 一次时间戳同现，不是已证的因果**；
它 patch NGX 运行时与全局模型缓存**是否**参与冻结，未证；`blackwellTransfusion=1` 用在 Ada 上**是否不当**，未证；
`[PIXEL]` 至今**从未产出过一个样本**，「画面到底是不是陈旧」目前仍只有间接证据；
DLSS5 屏幕输出未证；RTX 20/30 一行未动。
