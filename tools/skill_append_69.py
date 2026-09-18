#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append sections 69..75 to the framegen-diagnosis skill.

The lesson set here is uncomfortable but important: the previous round's "fix" was
itself the root cause. Sections 72/74 exist so the next round does not repeat it.
"""

import os
import shutil
import sys
import time

TARGET = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
MARKER = "## 69 冻结/崩溃/驱动复位三分：**必须有跨运行追加的文件**"

BODY = r"""

---

## 69 冻结/崩溃/驱动复位三分：**必须有跨运行追加的文件** ★2026-09-18 00:05 实锤

**症状**：「进世界了，但是卡死 —— 有声音，但画面冻结」。

三种结局长得几乎一样（帧率掉到 0），但处理方式完全不同：

| | 进程还在？ | 日志会再写？ | 崩溃记录 | TDR 事件 |
|---|---|---|---|---|
| **崩溃** | 否 | 否 | CrashLogger / WER AppCrash | 无 |
| **帧循环卡死** | **是** | **看门狗还能写** | 无 | 无 |
| **GPU 卡死/复位** | 是 | 可能还能写 | 无 | 4101/4102 |

**判定它的唯一可靠办法：让某个东西在渲染线程死掉之后仍然写得动。**

本插件有一个 200 ms 的看门狗线程（只读原子量 + `fprintf`+`fflush`+`fclose`，
不碰 D3D）。**这就是那根救命稻草。**

### 但**主日志每次运行被覆盖** ⇒ post-mortem 时必须靠追加型文件

实测：`DynamicShaderFrameGen.log` 每次启动**重写**（第一次冻结那次的日志，第二次启动后就没了）。
`…watchdog.log` 是**追加**的 ⇒ 它保留了**每一次运行**的形状。
冻结那次的主日志已经不存在，**证据全在 watchdog 里**。

**做法**：把追加型文件按运行段切开。分段判据 = **帧号回退**（新运行从 1 重新计数）。

```python
runs = []; cur = [recs[0]]
for r in recs[1:]:
    if r["frames"] < cur[-1]["frames"] - 10:   # 回退 => 新运行
        runs.append(cur); cur = [r]
    else: cur.append(r)
runs.append(cur)
```

逐段列表：`ticks / 时长 / 末帧 / 末 silent / 最大 silent / focus / 末 stage / STALLED 数`。
一眼就看出来了：

```
#   ticks  dur_s  lastFrame  lastSil  maxSil  focus  STALLED
6   54     53.2   1493       22       25017   ?      0       <- 23:40 那次
7   175    34.9   275        4318     25814   0      3       <- ★冻结：帧停 + 还在写 STALLED
8   261    52.2   1701       11       19198   1      0       <- 00:05 那次
```

段 #7：帧号停在 275、`silent` 一路涨到 4318 ms、看门狗**每 200 ms 还在写 STALLED**
⇒ **进程活着，帧循环停了**。「有声音、画面冻结」完全对上。

**⚠️ 装载期会假警报**：游戏在初始装载期间**根本不调用 Present**，`silent` 会涨到 ~20 s
而帧号恒为 1。判据必须有 `frames >= 60` 的"曾经跑顺过"闸门（v0.63 加的），
否则旧 build 会打印 19 行假的 `RENDER THREAD STALLED`。
**读取器遇到帧号 < 60 的段，必须明确标注"装载期假警报"。**

---

## 70 `stage=X` 是「**最后被设的那个**」，不是「**卡在这里**」 ★2026-09-18 实锤

我上一轮由 `stage="d3d11 Wait"` 推出"卡在 D3D11 围栏等待"，**错了**。

原因有两层：

**(1) stage 是**粘**的。** 它只在我们的代码里被赋值。`m_stage = "d3d11 Wait"` 是
`Present()` 里**帧末尾**设的（设完就 `return`），之后**再没有任何赋值**。
所以"帧跑完了，然后游戏在别处卡住"读出来也是 `d3d11 Wait`。
**只有同一个 stage 连续存在好几秒（silent 一直涨）才说明卡在那个 stage 附近**，
而且要结合"这个 stage 之后代码还会不会设新 stage"一起读。

**(2) API 语义要查，不要猜。** `ID3D11DeviceContext4::Wait` 的官方文档原话：

> Waits until the specified fence reaches or exceeds the specified value before future
> work can begin. **This member function is equivalent to the Direct3D 12
> `ID3D12CommandQueue::Wait` member function**, and applies between Direct3D 11 and
> Direct3D 12 in interop scenarios.

⇒ **GPU 侧排队等待，不阻塞 CPU。** 所以它**不可能**是"CPU 线程停在这里"的原因。
一声"我猜它是阻塞的"就会把整个归因带偏。

**通则**：`stage`/`lastStage` 这类"最后状态"字段，**语义 = 最后写入值**。
把它当"当前执行位置"用之前，先确认"这个位置之后还有没有写入点"。

---

## 71 `TdrDelay=30`：**没有 TDR 事件 ≠ 没有 GPU 卡死** ★2026-09-18 实锤

```
HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers
    TdrDelay    = 30      （默认 2）
    TdrDdiDelay = 30      （默认 2）
```

Windows 判定"GPU 卡死"靠超时。默认 2 秒 ⇒ 卡死会**留下痕迹**：System 日志里
`Display` 提供商的 **4101**（"显示驱动程序已停止响应并已恢复"）/ **4102**（已恢复）。

本机被改成 **30 秒**（多半是为 ENB/Community Shaders 的长着色器编译改的，**别盲目改回 2**）。
后果：**GPU 卡死在头 30 秒里完全静默** —— 无事件、无复位、无日志。
用户看到的就是"永久冻结"，然后手动结束进程，**证据随进程一起消失**。

**排查时的两条规则**：
1. 先查 `TdrDelay`。若不是默认值，那么"System 日志里没有 4101/4102"**不能**用来排除 GPU 卡死。
2. 在**排查期临时**下调到例如 10，让卡死变得可观测；排查完恢复原值。
3. 反过来说：`Display` 提供商**历史里全是 4125**（自动 HDR 提示，fullscreen 应用启动时打的）
   而没有一条 4101/4102，只能证明"从来没有触发过 TDR"，不能证明"从来没有 GPU 卡死"。

---

## 72 `DXGI_PRESENT_DO_NOT_WAIT` 会**拆掉** `FLIP_DISCARD` 的 CPU 背压 ★2026-09-18 实锤（自己踩的）

上一轮为了让"失焦的窗口不能阻塞 Present"，给两处 `Present` 都加了 `DO_NOT_WAIT`。
**这是错的**，而且错得很隐蔽。

```cpp
// 这套设计**依赖** Present 阻塞：
frame N:  Reset(commandAllocators[frameIndex]);      // 复用上一轮的分配器
          ...录命令...
          Present(0, Flags);                          // ← 这里阻塞 = 唯一刹车
frame N+1: Reset(commandAllocators[frameIndex]);
```

`FLIP_DISCARD` + `BufferCount=3` 下，**翻页队列满就是"CPU 不许再跑到 GPU 前面去"的唯一机制**。
`DO_NOT_WAIT` 把它变成"立即返回 `DXGI_ERROR_WAS_STILL_DRAWING`" ⇒ CPU 可以无限制地跑到
GPU 前面去，而去掉刹车之后紧接着就是 **Reset 一个可能仍在执行的命令分配器**。

**规则**：**`Present` 阻塞在这类架构里是同步机制的一部分，不是性能问题。**
要消除"失焦不能显示"的危害，**不是**让 `Present` 不阻塞，而是**在那段时间里根本不要排队任何工作**
（见 73）。`DO_NOT_WAIT` 只在一种场合是对的：**那条路径下游什么都不依赖**（例如直接 return 的旁路）。

---

## 73 跨队列 fence ping-pong 的隐藏假设：**"对面那个队列永远能把一帧做完"** ★2026-09-18 实锤

本插件的每帧同步是一条**跨队列链**：

```
d3d11 Signal(fence, v)   →   d3d12 Wait(fence, v)   →   [D3D12 干活 + Present]
                         →   d3d12 Signal(fence, v+1)   →   d3d11 Wait(fence, v+1)
```

它假设 **D3D12 队列总能把一帧做完**。而"没人能显示的窗口"恰好打破这个假设：
翻页拿不到 slot ⇒ D3D12 队列停 ⇒ **D3D11 队列被它堵死** ⇒
引擎下一次任何 D3D11 操作（或一次需要 GPU 完成的 `Map`）**永远等下去**。

结局就是那个最难查的形态：**画面冻结、声音照放、不崩溃、不 TDR、CPU 侧看什么都没死。**

**修法不是"跑赢它"，而是从构造上让它不可能发生：**

```cpp
if (!winFocused) {
    m_stage = "unfocused bypass";
    if (swapChain) {
        const HRESULT hr = swapChain->Present(0, Flags | DXGI_PRESENT_DO_NOT_WAIT);
        if (hr != DXGI_ERROR_WAS_STILL_DRAWING) DX::ThrowIfFailed(hr);
        frameIndex = swapChain->GetCurrentBackBufferIndex();   // 翻页可能真的发生过，索引要保持诚实
    }
    return S_OK;               // 不做 interop 拷贝、不评估 FG、不排任何 fence
}
```

失焦期间队列上**没有任何工作**，对面也就没有可等的东西。恢复时走正常路径即可。

**⚠️ 顺带一条**：在 `Present` 中途调 `slDLSSGSetOptions(mode = eOff)`、
或在 `mode` 仍为 `eOn` 时跳过 `slEvaluateDLSSG` 很久，都是**没有支持的**中途操作 ——
DLSS-G 的 pacer 期望**每帧一次评估**。要么整段旁路（上面这样），要么完全不动它。

---

## 74 **修复本身可以是根因** —— 加同步/改 Present 语义的改动，要按"同步问题"重审一遍 ★2026-09-18 实锤

上一轮的"修复"（焦点处理 + `DO_NOT_WAIT`）**就是这一轮卡死的根因**。复盘它的成因：

1. 从一个**弱证据**出发（"日志在失焦那一瞬停了"）就推定了机理（Present 死锁），
   而当时**那个 DLL 没有任何焦点仪表**，所以推定**不可检验**；
2. 于是加了既改**行为**又加**仪表**的一坨东西 —— 行为部分**改动了两处同步语义**
   （Present 阻塞性、DLSS-G 模式生命周期），却按"加个保护"来审；
3. 结果：真正的死锁面（跨队列链）**没被碰**，反而多了一个新的失效模式。

**规则（三条，都要照做）：**
1. **行为改动与仪表改动分开交付。** 仪表先上、先跑一次、拿到基线，再动行为。
   混在一起的话，出问题时你分不清是"新改动的行为"还是"新仪表看到了老问题"。
2. **凡改动 `Present` / 围栏 / 模式切换 / 分配器复用的**，按"我在动同步机制"审，
   逐条写清"这个改动让哪条**队列**的**顺序保证**变了"。
3. **别在弱证据上动手。** "日志在 X 时刻停"只能证明**写日志的东西停了**。
   要证明机理，必须有**专门为那个机理加的仪表**（本轮就是看门狗里的 `fence=` 字段）。

---

## 75 判决表：让"卡死在哪一层"变成一个**读数**，而不是一次推理 ★2026-09-18

看门狗行现在是：

```
[mono_ms] frames=N silent=Nms stage=X focus=F fence=GPU完成值/GPU完成值  [<== RENDER THREAD STALLED]
```

| `frames` | `silent` | `focus` | `fence=` | 判决 |
|---|---|---|---|---|
| 不再增长 | 一路涨 | 0 | **不动** | 队列停了：跨队列/驱动级卡死（先查 `TdrDelay`） |
| 不再增长 | 一路涨 | 0 | **在动** | GPU 没停，渲染线程在 **CPU 侧**被挡住 |
| 不再增长 | 一路涨 | 1 | 任意 | 与焦点无关：查引擎/其它插件的 CPU 侧等待 |
| 还在增长 | 正常 | 任意 | 在动 | **没卡死** —— 去查显示/合成路径或用户的结束动作 |

`fence=` 是两个 `GetCompletedValue()`（D3D11 侧与 D3D12 侧视图同一根围栏）——
**只读、非阻塞、可从看门狗线程安全调用**。它是"GPU 到底有没有在推进"的唯一廉价探针，
也是这一轮真正缺的那件东西。**`~0`（UINT64_MAX）= 设备已丢失。**

**产品化**：上面这套表已经是 `tools/read_xray_log.py` 的 **"0b. 全部运行段"** 段，
它同时给出每段的 `ticks/时长/末帧/末silent/最大silent/focus/末stage/STALLED`
并自动下判决 —— 冻结那次的主日志被覆盖了也没关系，看门狗是追加的。
"""


def main():
    apply_it = "--apply" in sys.argv
    with open(TARGET, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")

    if MARKER in text:
        print("REFUSED -- already applied (marker present)")
        return 2

    anchor = text[-80:]
    n = text.count(anchor)
    print("target: %s" % TARGET)
    print("bytes before: %d | tail anchor x%d" % (len(raw), n))
    if n != 1:
        print("REFUSED -- tail anchor not unique")
        return 2

    out = text + BODY
    if out.count(MARKER) != 1:
        print("REFUSED -- marker not exactly once after append")
        return 2
    for s in ("## 69 ", "## 70 ", "## 71 ", "## 72 ", "## 73 ", "## 74 ", "## 75 "):
        if out.count(s) != 1:
            print("POST FAIL: %r x%d" % (s, out.count(s)))
            return 2

    print("post-conditions OK | +%d bytes" % (len(out.encode("utf-8")) - len(raw)))

    if not apply_it:
        print("\nDRY RUN -- nothing written. Re-run with --apply")
        return 0

    shutil.copy2(TARGET, TARGET + ".bak_" + time.strftime("%Y%m%d_%H%M%S"))
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))
    back = open(TARGET, "rb").read().decode("utf-8")
    if back.count(MARKER) != 1 or not back.endswith(BODY[-40:]):
        print("READBACK FAIL")
        return 3
    print("readback OK | %d bytes" % len(back.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
