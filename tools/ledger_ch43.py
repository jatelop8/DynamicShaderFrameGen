# -*- coding: utf-8 -*-
"""Append chapter 43 to MFG_MASTER_NOTES.md.  Append-only; pure LF."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "MFG_MASTER_NOTES.md"

CH = """
# 第 43 章：不是崩溃，是被终止 —— 而「屏幕上是什么」终于有了仪器（v1.30）

局：2026-09-20 13:12:00 -> 13:12:46.86，跑 v1.29（首跑）。归档
`docs/runlogs/2026-09-20-1312-v129-terminated-not-crashed-4x-lived-2-seconds.*`。
本局 46 秒，世界段 2.0 秒 —— 但这一次，「2 秒」不再是一个含糊的说法。

## 43.1 先把用户的话对齐到毫秒

用户原话：「还是卡在游戏刚进去两秒，只要开始四倍帧生成，就卡死。」

Transfusion 侧（`DLSSG-Transfusion.log`）：

- `13:12:44.551 [OPTIONS] Game DLSS-G options: ... frames=3`
- `13:12:44.551 Option C active: stripped eEnableFullscreenMenuDetection ...`
- `13:12:44.551 Applied fixed multiplier: 4x, result=0 (eOk)`
- `13:12:44.747 DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)`
- `13:12:45.454 [PERF] 4x | Kernel: Ada | FPS: 33.3 (30.08ms) | Jitter: 7.87ms | 1% Low: 32.2`

我方 `[XRAY] MENU EDGE open=0 serial=631`（世界入口）= `13:12:44.551`，
即 **4x 生效与世界入口是同一毫秒**。我方日志最后一行 `13:12:46.855`，
watchdog 最后一行 `13:12:46.759`。

把 watchdog 末尾两个计数拿出来除：

| 时刻 | frames（我方 Present 入口） | lastPr（DXGI 自己的计数） |
|---|---|---|
| 13:12:44.931 | 643 | 658 |
| 13:12:46.759 | 705 | 906 |
| 差值 | **+62** | **+248** |

248 / 62 = **4.00**。**4x 第三次被实测到，而且是精确的 4.00。**

分钟级别的主日志最后一条 `FLIPS per real frame = 3.57` —— 那个窗口
（13:12:44.508 -> 46.526）**跨在 4x 生效的前后**，所以被 1x 的部分稀释了。
这是把「速率」用「窗口」去量时的必然误差，不是异常。

进程消失的时刻 = 4x 生效 **2.21 秒**之后。用户说的「刚进去两秒」，
与日志逐字段吻合。

## 43.2 这一局不是崩溃 —— 两条独立证据

**证据一（WER / 事件日志）**：`Get-WinEvent` 查 13:10-13:20 的 Application 日志，
没有任何 Application Error / AppHang 事件。WER 的 `ReportArchive` 里
`AppCrash_SkyrimSE.exe` 有三份，**全部是 9 月 18 日的**，9 月 20 日零份。
这个目录对 SkyrimSE.exe 是有效的（否则不会有那三份）。

**证据二（Crash Logger SSE）**：`Documents\\My Games\\Skyrim Special Edition\\SKSE\\crash-*.log`
共 20 个（`Max Crash Logs = 20`，旧的已被轮转掉），最后五个是
`09-18 16:04 / 18:23 / 19:04 / 19:16 / 19:34`。
**9 月 19 日和 9 月 20 日一个都没有。**

⇒ 两天里所有「卡死」，游戏**一次都没崩**。进程是被**终止**的
（`TerminateProcess` 不留 WER 报告、不留 crash log、不调用任何析构）。

## 43.3 那不是卡死 —— 但也不是「正常」

watchdog 最后一行：

```
[43243629] 13:12:46.759 frames=705 silent=5ms stage=d3d11 Wait focus=1 fence=1401/1401
           stim=179 queued=1 lastPr=906 dsync=0 msg=1 alive=1 presentAge=-12ms cpuD=156ms
```

`silent=5ms` —— 渲染线程在进程消失前 5 毫秒还在正常跑。全程 `silent`
2~27 ms、`presentAge` ±27 ms、`fence` 两侧相等、`msg=1 alive=1`。
**没有任何一行读数像「卡住」。**

`presentAge` 的负值（-4 / -16 / -12 ms）是**看门狗自己的测量伪影**：
`nowMs` 在循环顶部取一次，而 `SendMessageTimeoutA(..., 200ms)` 在写这一行
之前跑，最长 200 ms ⇒ `nowMs` 相对 `g_presentEnteredMs` 是过期的。
**名字叫 age，参考点却是旧的。** 记下来，别再当异常读。

`stage=d3d11 Wait` 仍然是「最后写下的名字」，不是「当前调用」。

## 43.4 v1.29 的四台仪器：两台按构造就不可能触发

**这是本轮最该记住的技术教训。**

v1.29 加的 `4x SNAPSHOT` / `4x probe` / `FLIP COUNTER FROZEN`，前提条件是：

```cpp
const bool warm4x = frames > 200ull && lastPr > frames * 3ull;
```

这是**累积比**。而 `lastPr` 只有在 4x 活着的时候才会跑到 `frames` 前面，
所以「累积比 > 3」等价于要求「4x 已经活了整个会话的大部分时间」。
本局末态 `lastPr=906` / `frames=705`，测试要 `lastPr > 2115` ——
**它要的那 2115 次翻转，在这个 2 秒的窗口里根本不存在。**

四个读数一个都没出现，**四个零全是仪器，不是现象**。

修法：把定义改回它本来该有的样子 —— **速率**。
`dFlips / dFrames >= 3` 在最近 200 ms 的切片上（34 次入口/秒 ⇒ 切片内约 7 帧，
取 >=3 是保守的，且装载期比值是 1.00，不可能误触发）。
`FLIP COUNTER FROZEN` 顺便**去掉对 live4x 的依赖**：
它要问的是「我方 Present 在跑而翻转计数没动」，一个要求「4x 必须活着」的
前置条件，恰好会藏住「4x 被请求了但没到」这一种情况。

**L66（本轮）：一个仪器如果要求「我要测的那个现象已经成立」才启动，
那它就永远测不到那个现象。**

## 43.5 第三条误报：0.9/255 的抖动不算「回来了」

v1.28 的回访判据（`revisits >= 1`）本局触发 **4 次**，窗口逐字：

```
shape=[0 0 1 1 1 1 2 1]   亮度 0.0 / 0.0 / 104.0 x4 / 104.9 / 104.0
```

这是**加载屏由黑转亮的一次单向渐变**，加上**一个比邻居亮 0.9/255 的样本**。
`revisits` 数的是折叠序列里所有非相邻的相等对：一次真实的
A,B,A,B,A,B,A,B 得 12，而单个毛刺得 1。所以门槛抬到 **2** 即可分开，
且不动真正需要的灵敏度。

**★ 这是同一个探针的第三次误报**（v1.26 一次、v1.27 一次、v1.28 一次），
而**它一次真阳性都没有过**。它读的是 `colorOut` —— 交给 DLSS-G 的**输入**，
所以它从原理上看不见插帧之后的画面。它的正当用途只剩「我方这一侧有没有动」。

## 43.6 盲点有了准确的名字，而且比之前说的更大

本工程（v1.30 之前）拥有的每一个读数，都在栅栏的**我们这一侧**：

| 读数 | 它到底测什么 |
|---|---|
| `frames=` | 我们自己的 Present 被进入了多少次 |
| `lastPr=` | 我们自己的 swapchain 翻转了多少次 |
| `[PIXEL]` | 我们交给 DLSS-G 的 D3D11 纹理（**输入**）的哈希 |
| `cpuD=` | 我们整个进程的 CPU 时间 |
| `silent=` / `presentAge=` | 我们自己函数调用之间的间隔 |

**没有任何一个读屏幕。** 而且 `lastPr` 上涨**连「面板动了」都证明不了**：
FLIP 模型下有翻转队列，Present 可以在任何东西扫出之前就返回。

⇒ 「DXGI 报 137 翻转/秒」从来不是「画面在动」的证据。
这条我上一轮说得比实际强，纠正。

**所以 v1.30 加了屏幕探针**：在 watchdog 线程里每秒一次
`GetDC(NULL)` + `StretchBlt` 到 64x64 DIB（`HALFTONE`，最近邻会在 4K->64
的降采样里只采到 1/60 的像素，可能整片漏掉真实变化），算哈希与平均亮度，
并与**我们自己 `colorOut` 的哈希**并排保存；窗口按**写序**读（v1.28 在
环形缓冲上犯过这个错）。

判据只有一条，而且是这个工程里第一条关于**屏幕**而不是关于**我们**的判据：

```
窗口内 sDistinct <= 1 && pDistinct >= 3   ->  [SCREEN] STALE
```

屏幕 8 秒只有一张图，而我们自己的 `colorOut` 取过 3 个以上的值。

两条自证：捕获创建失败打 `[SCREEN] ERROR`；连续十次全黑打 `[SCREEN] BLIND`
（独占全屏会让桌面捕获什么都看不到，而**沉默会被读成健康**）。

**★ 顺带排除一条假设（不需要跑一局）**：`DX12SwapChain.cpp:206/241` 里
`CreateSwapChainForHwnd(commandQueue.get(), a_swapChainDesc.OutputWindow, ...)`
用的是**游戏自己的窗口**，所以「FG swapchain 建在一个隐形窗口上」不成立。

## 43.7 输入见证：换一个问法

本局 16 行 `[CAM] PC` 全是 `kb=0`（255 个 VK 全扫），
而同一行的 `dc=`（鼠标位移/事件数）读到 `2006/1`、`2155/1`、`2132/1`。
⇒ 鼠标到了，键盘没有。

但「255 个键此刻都没按下」和「用户什么都没做」仍然是两句不同的话，
而且 1 Hz 采样本身有 1 秒的洞。

v1.30 加 `GetLastInputInfo`（`ai=<距上次输入 ms>`）：
它问的是「这个会话里有没有任何输入」，**与是哪个键无关** ——
这正是 L61 要的答案。它返回时间戳而不是状态，所以 1 Hz 够用。

## 43.8 v1.30 改动清单（不碰帧生成路径）

`tools/patch_v130_the_screen_and_the_dead_4x_test.py`，7 个锚点各 `count==1`：

1. `[SCREEN]` 探针（上述）——新增。
2. `live4x` 改速率定义；`FLIP COUNTER FROZEN` 去掉 live4x 前提。
3. 闪烁门槛 `revisits >= 1u` -> `>= 2u`。
4. `ai=`（`GetLastInputInfo`）+ `[INPUT] system input ... ms ago`。

另有两处读数窗口收紧（`Edit` 工具，逐符号回读 + 行尾复查）：

5. `DLSSG diag` 每 120 次 -> **每 20 次**。旧节奏在 34 入口/秒下是 3.5 秒，
   而 13:12 局 4x 只活了 2.2 秒 —— **下一个读数排在进程已经死掉之后**。
6. `[MFG] debug CHECK` 每 600 帧 -> **每 120 帧**（同上理由）。

**这两条本身就是 L47 的一个新例子：为装载屏选的节奏，在用户真正报告的那个
窗口里等于零。**

## 43.9 第一遍（手脚）

- 7 个锚点干跑全 `count==1`；`--apply` 后 post-check：新串在、旧串（
  `revisits >= 1u` / `lastPr > frames * 3ull` / `warm4x`）计数为 **0**。
- 行尾：`src/DX12SwapChain.cpp` **CRLF=0 CR=0**（纯 LF）；
  `src/FrameGen.cpp` **CRLF==LF==CR**（纯 CRLF）。`Edit` 工具两次改动后复查，未被转成 CRLF。
- 构建 `BUILD SUCCESS`，0 error 0 warning。
- DLL **1,389,056 B** md5 `40704c8cc78466a77884ccee3f9f4414`，**build == MO2 部署目录**。
- 二进制内新串 4/4 在（`ai={}` / `[SCREEN] STALE over` / `live4x: +%llu flips` /
  `system input {} ms ago`）。
- INI **未动**：`efce89119d840670e519d219749a6476`，20658 B，358 行 CRLF，源树 == 部署。

## 43.10 第二遍（脑子）

- **反向假设**：如果那两条「边沿」日志的值真的变了，日志文本会不同 ——
  本局 `Reflex cap check` 709 行里 **631 行是 `at 2x`、78 行是 `at 4x`**，
  也就是说这一行的值是**跟着倍数在切的**（它本来就是每帧行，不是边沿行）；
  而 `Reflex options applied` 从 4896 行掉到 **1 行**、`Reflex FLIP cap` 只打 **2 行**
  （正好在 2x->4x 那一个边沿）。
  ⇒ **v1.29 对 `slReflexSetOptions` 那个门做的原子修复生效了**，
  这是本轮唯一一处「上一版的修复被本局证实」。
- **A ≠ B**：`revisits >= 1` 与 `>= 2` 在同一段日志上判据相反（1 vs 1）——
  实测对照，不是推理。
- **这条路径真会走到吗**：`[SCREEN]` 挂在 watchdog 的 `(tick % 5) == 3` 上，
  与 `SendMessageTimeoutA` 的 `(tick % 5) == 0` **错开**，避免两件慢事叠在同一次。
- **空集不能当健康**：`[SCREEN] ERROR` / `[SCREEN] BLIND` 就是为这一条写的。
- **用户会不会白跑**：**会** —— 而这是本轮唯一没能解决的问题。
  屏幕探针要求世界段足够长（8 秒窗口才出 STALE），而最近 8 局的
  世界段是 2.1 / 3.0 / 3.2 / 2.5 / 6.1 / 5.7 / 4.1 / **2.0** 秒。

## 43.11 未证 / 下一步

- **屏幕上到底是什么 —— 仍然未证**，但从 v1.30 起有仪器了。
  首跑按「校准」读（L53）：先确认 `[SCREEN]` 每秒在打、`distinct` 不是恒为 1、
  不是连续十次全黑。
- **「4x 导致卡死」仍未证**。而且现在多了一条更强的说明：
  **4x 之后进程是被终止的，不是崩的，日志里没有任何一行像卡死。**
  2x 对照局（`MFGMaxFramesOverride=0`）**仍然一次都没跑过**。
- **Transfusion 隔离实验**（`DINPUT8.dll` -> `DINPUT8.dll.transfusion-off`，
  **绝不能用 `.disabled`**）**仍然一次都没跑过**。
- **`[MFG] debug CHECK` 在本局报了 `dlssgOk=0`**，落在解除守卫后的**第一帧**；
  下一帧起是否恢复，旧节奏（600 帧）让它排在进程死亡之后 ⇒ 本局**读不到**。
  v1.30 收紧到 120 帧。
"""


def main():
    raw = LEDGER.read_bytes()
    assert b"\r" not in raw, "ledger must stay pure LF"
    txt = raw.decode("utf-8")
    assert "# 第 43 章" not in txt, "chapter 43 already present"
    assert txt.endswith("\n")
    txt += CH.lstrip("\n")
    LEDGER.write_bytes(txt.encode("utf-8"))
    raw2 = LEDGER.read_bytes()
    print("ledger %d -> %d bytes, CR count = %d, ch43 = %s"
          % (len(raw), len(raw2), raw2.count(b"\r"),
             ("# 第 43 章".encode("utf-8") in raw2)))


main()
