# -*- coding: utf-8 -*-
"""Append chapter 42 to MFG_MASTER_NOTES.md (pure LF, append-only)."""
import pathlib

LEDGER = pathlib.Path(r"D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md")

CH = r"""
# 第 42 章：12:26 局是第二次「世界活了」；「21 秒零 Present」原来早有答案；而我两个「边沿」检测器其实是撕裂的（v1.29）

**局：2026-09-20 12:26:56 - 12:29:35（跑 v1.28，DLL md5 `4184e1c898c1a188a3899358857d7194`）**
归档 `docs/runlogs/2026-09-20-1226-v128-tbd.*`（5 件）。

## 一、先把时间线钉死（每一条都有时间戳）

| 时刻 | 事件 | 证据 |
|---|---|---|
| 12:26:56.508 | SKSE 加载 DLL | log 头 |
| 12:27:08.5 | swapchain / interop ready | `D3D12 FG swapchain created` |
| 12:27:08.6 | 最后一次进入我方 Present（本段共 1 次） | `frames=1` |
| 12:27:08.6 -> 12:27:30.0 | **21.4 秒无 Present** | `dt max=21426.80ms`（见第二节） |
| 12:27:30.003 | `MENU EDGE open=1 serial=2`；PIXEL 开始采样；frames 从 1 跳到 135 | watchdog 12:27:32.775 |
| 12:27:30 -> 12:29:30 | **加载屏 2 分钟**，2x，4822 帧，全程无停顿 | `at 2x` x 4822 |
| 12:29:30.928 | `MENU EDGE open=0 serial=4822` 闸门释放 | 同毫秒 `Applied fixed multiplier: 4x (eOk)` |
| 12:29:31.133 | **`DLSSG presented per real frame = 4`** | Transfusion + 我方双份 |
| 12:29:31.163 | `[OVERLAY] world clock started` | v1.28 新加的覆盖层计时 |
| 12:29:32.598 | `FLIPS per real frame = 3.03` | DXGI 自己的计数 |
| 12:29:34.609 | **`FLIPS per real frame = 4.00`** | DXGI `lastPresentCount 5021->5297` vs 我方 Present `4878->4947` |
| **12:29:34.991** | **全部日志在此瞬间停止** | 5 份日志最后一行都落在 12:29:34.9~35.0 |

**世界段 = 12:29:30.928 -> 12:29:34.991 约 4.06 秒；其中 4x 真正生效 = 12:29:31.133 -> 12:29:34.991 约 3.86 秒。**

**结论：这一段的仪器读数全部正常** —— `hrsD=0.0056`（游戏时钟在走）、`paused=0 ld=0 fade=0`、
`read=553 match=518`、watchdog `silent` 全程 1~30 ms、DXGI 137 翻转/秒。
**没有任何一处显示卡死。** 日志**瞬间**停止且没有任何 shutdown/dtor 行 ⇒ **进程是被强制结束的**。

## 二、「21 秒零 Present」不是谜 —— 答案在第 719 行，我自己写的

watchdog 的 warm 判据注释（`src/DX12SwapChain.cpp:719-722`，v0.63 写的原文）：

> 21:54 那次运行在约 20s 装载里 frames 恒为 1、stage 恒为 "d3d11 Wait"，看门狗连打 19 行
> RENDER THREAD STALLED —— 全是假警报。判据收紧：渲染线程必须「曾经跑顺过」（frames>=60）
> 才允许报卡死，未达标只记 silent（装载期的正常表现）。

⇒ **装载期 `frames=1` + `stage="d3d11 Wait"` 是已知的正常现象**，并且当时就已经处理了
（`warm = frames >= 60`）。

本轮新拿到的那条硬证据，第一次把这个现象**量化**：

```
[XRAY] ... dt min/avg/max=17.74/29.53/21426.80ms n=4823
```

**一帧耗时 21426.80 ms。** 不是「20 秒没进 Present」，是「有一帧真的跑了 21.4 秒」。

⇒ 第 40 章把这段写成「未解之谜 / 唯一硬读数是 DXGI 零翻转」是**过头了**。
零翻转只说明「我们的 FG swapchain 还没被用上」（装载期游戏走原生 D3D11 swapchain），
不是「引擎卡住」。而且 **`frames` 从 1 跳到 135 发生在 `MENU EDGE open=1` 的同一秒**，
说明链路是**跟着菜单打开的**，不是自己恢复的。

**下次不要再花一局去查这件事。**

## 三、12:26 局与 03:17 局（第一次活的世界）逐字段相同

| 量 | 03:17（v1.27） | 12:26（v1.28） |
|---|---|---|
| `[CAM] PC` read/match/adopt | 512 / 480 / 1:1 | 553 / 518 / 0:3 |
| `eye` | (-243.05,-415.31,118.56) | **同一个坐标** |
| `proj00` | 0.8391 | 0.8391 |
| `paused= / ld= / fade=` | 0/0/1 | 0/0/0 |
| `hrsD` | 0.0056 | 0.0056 |
| `FLIPS per real frame` | **4.00** | **4.00** |
| 世界段 PIXEL shape | `sw=7 maxRun=1`（每样本都不同） | `sw=7 maxRun=1` |
| 世界段长度 | 5.7 s | **4.1 s** |
| `os=` | `0x0` | `0x0` |

⇒ **两局在仪器上无法区分。「世界活了 / 4x 生效」已经复现两次，不是侥幸。**

## 四、v1.29 修的：两个「边沿」检测器其实是撕裂的

### 4.1 `Reflex cap check` 在一个加载屏上打了 4823 行，而它的值一次都没变

```
[Streamline] Reflex cap check (v1.12): 159 flip fps on a 160Hz panel = 79.5 rendered fps at 2x
```

**这一行打了 4822 次，每一次的数值都字面相同**（加载屏全程 2x / 159）。

判据在 `src/Streamline.cpp:2410`：

```cpp
static std::uint32_t lastCapFps = 0;
static std::uint32_t lastCapMult = 0;
if (capFps != lastCapFps || capMult != lastCapMult) { ... log ...; lastCapFps = capFps; lastCapMult = capMult; }
```

**两个 plain static + 两个线程**（本插件 Present 路径两个 tid 都走；Transfusion 自己的 trace
也显示两个 tid 到达姊妹调用）。**两个字宽的写不是原子的**：一个线程写 `lastCapFps` 的
同时另一个读 `lastCapMult`，两边都「看到变化」⇒ **边沿检测器退化成每帧触发**。

**修法**：`(capFps << 4) | (capMult & 0xF)` 打包成一个 `std::atomic<uint32_t>`，
用 `exchange` 比较 —— **一次真边沿只有一个线程能拿到旧值**。

### 4.2 `Reflex options applied` 打了 4896 行，而这次它决定的是「要不要调用」

```cpp
static sl::ReflexOptions lastOpts{};
static bool lastValid = false;
if (!lastValid || std::memcmp(&lastOpts, &opts, sizeof(opts)) != 0) { slReflexSetOptions(opts); ... }
```

**同一个撕裂缺陷，但严重一档：这个判据决定 `slReflexSetOptions` 是否被调用**，
所以它让运行时**每帧被重新配置一次**，全程（加载屏 + 世界）都是。

打印出来的三个字段 `mode=1 frameLimitUs=6289 markers=true` 同样**从未变过**。

**修法**：只比较这个函数真正设置的三个字段（已 grep 确认 `opts` 只有这三处赋值：
`mode` / `frameLimitUs` / `useMarkersToOptimize`），打包成 `std::atomic<uint64_t>`，`exchange` 比较。

**这不是改变设计，是恢复设计** —— 原注释（v0.35）写的就是「选项变化才 slReflexSetOptions
（缓存比较，CS 同款）」。**缓存比较从未生效过。**

## 五、v1.29 修的仪器：输入见证只能证明「不是那八个键」

`src/FrameGen.cpp:1583-1590` 的输入见证扫八个键：`W A S D Space Shift LMB RMB`。

**16 局连续打出 `os=0x0`，而每一局都被读成「用户没碰过键盘」。**

**但那个掩码只能证明否定命题「不是那八个键」。** 一个觉得画面卡死的玩家，
**最先按的是 ESC 或 Alt+F4 —— 两个都不在掩码里。** 于是「不是这八个」被静默升级成
「完全没有输入」，而整个输入见证的结论就架在这个越界推论上。

**修法**：每秒扫全 `vk 1..255`（255 次 `GetAsyncKeyState` 相对 4K 帧是免费的），
`kb=` 打印当前按住的键数，并在**任何键变化**时打一条 `[INPUT] vk 0x.. -> 0x.. (N held, fg=1)`。

**已写明的局限**：这是 1 Hz 采样，**两次采样之间按一下就松开的键会被漏掉**。
协议要求的「按住 W 十秒」漏不掉。

## 六、v1.29 加的仪器：屏幕上到底有没有新帧

`frames=` 数的是**我们的** Present 进入次数，`lastPr=` 数的是**我们的** swapchain 翻转次数 ——
**两个都在我们这一侧。** 12:26 局两者都在涨（2.86 秒里 98 次进入、392 次翻转 = 137 翻转/秒 = 正好 4x），
而用户说画面是卡死的。

⇒ 加两条：

1. `[XRAY] 4x SNAPSHOT t=0` —— 倍数落到 4x 的那一 tick（判据 `frames>200 && lastPr>frames*3`，
   登录界面 `lastPr≈2*frames` 达不到，不会误触），随后 3 秒内每 5 tick 一条 `4x probe`，
   带**实测面板翻转率**。**这段时间正是用户唯一在报告的窗口** —— 最近 6 局每一局都在
   世界时间 6 秒内结束，所以「一分钟才打一次」的速率等于从未被看到过。
2. `[XRAY] FLIP COUNTER FROZEN for N ticks` —— `lastPr` 连续 5 tick 不涨而 `frames` 仍在涨。

## 七、方法论

**L60（本轮最有用）**：**一行日志如果把自己的值一起打出来，那么当它带着同样的值重复时，
它就自我否证了 —— 坏的是判据，不是值。** 这次两个「边沿」检测器都是这样被抓出来的：
4823 行 `at 2x`、4896 行 `mode=1 frameLimitUs=6289`。
**下次看到一个「变化才打」的日志在刷屏，第一件事是把它打印的值读出来，而不是去查它测的东西。**

**L61（本轮最贵）**：**判据的推论范围不能超出它测量的范围。**
`os` 测的是八个键，结论却是「没有任何输入」。**16 局都架在这个越界推论上。**
修法不是「多测几个键」，而是**把能测的全测**（255 个 VK），因为**你不知道用户会按哪个键**。

**L62**：**「已知的正常现象」会被自己重新发现成「未解之谜」。**
第 40 章把装载期 21 秒写成「未证」，而这个现象的说明就写在同一工程第 719 行的注释里，
连处理方式（`warm = frames >= 60`）都已经实现了。**查未证清单之前，先搜一遍源码里
有没有人已经回答过。**

## 八、仍未证（不许假装已修）

- **v1.29 一局都没跑过。** 上面四条改动**全部只有静态验证**（构建 + 二进制串 + 行尾），
  没有任何运行读数。`kb=` / `[INPUT]` / `4x SNAPSHOT` / `FLIP COUNTER FROZEN`
  **四个新读数一个都没出现过。**
- **「4x 导致卡死」仍未证，而且这一局是反证**：4x 生效后的 3.86 秒里，
  DXGI 实测 137 翻转/秒、silent <= 30 ms、画面每 500 ms 完全不同。
  只有在 2x 对照局（`MFGMaxFramesOverride=0`）也复现同样现象之后，才能说 4x 无关；
  **这个对照局一次都没跑过。**
- **用户看到的画面内容 —— 仍然没有任何仪器覆盖。** PIXEL 读的是我们的
  `colorOut(presented)`，不是屏幕。两台仪器都在栅栏的这一侧。
- **Transfusion 隔离实验**（`DINPUT8.dll` -> `DINPUT8.dll.transfusion-off`）**一次都没跑**。
"""


def main():
    raw = LEDGER.read_bytes()
    assert b"\r" not in raw, "ledger is not pure LF"
    txt = raw.decode("utf-8")
    assert "# 第 42 章" not in txt, "chapter 42 already present"
    assert txt.endswith("\n")
    txt += CH.strip("\n") + "\n"
    LEDGER.write_bytes(txt.encode("utf-8"))
    raw2 = LEDGER.read_bytes()
    print("ledger bytes %d -> %d, CR count = %d, ch42 = %s"
          % (len(raw), len(raw2), raw2.count(b"\r"), "# 第 42 章".encode("utf-8") in raw2))


main()
