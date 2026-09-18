#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append the 00:05 freeze -> v0.72 entry to the daily memory (date rolled over)."""

import os
import shutil
import sys
import time

TARGET = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-18.md"
MARKER = "## 00:05 卡死定案 → v0.72（撤销 v0.71 的焦点处理，改为「失焦期间不排工作」）"

BODY = r"""# 2026-09-18

（接 2026-09-17 的 DynamicShaderFrameGen 调试会话）

## 00:05 卡死定案 → v0.72（撤销 v0.71 的焦点处理，改为「失焦期间不排工作」）

**用户原话**：「不行就是会卡死」。上一轮我把根因判成"失焦 → Present 死锁"，**判错了**。

### 破案靠的是**看门狗**，不是冻结那次的日志

主日志 `DynamicShaderFrameGen.log` **每次运行被覆盖** ⇒ 00:03 那次冻结的日志已经没了。
但 `…watchdog.log` 是**跨运行追加**的。按运行段切开后一眼就看到了：

| # | ticks | 时长 | 末帧 | 末 silent | 最大 silent | focus | STALLED |
|---|---|---|---|---|---|---|---|
| 6 | 54 | 53.2s | 1493 | 22 | 25017 | ? | 0（23:40 那次） |
| **7** | **175** | **34.9s** | **275** | **4318** | **25814** | **0** | **3** ← 冻结 |
| 8 | 261 | 52.2s | 1701 | 11 | 19198 | 1 | 0（00:05 那次） |

**段 #7 = 冻结**：帧号停在 275、silent 涨到 4318 ms、看门狗 200 ms 一写**还在写 STALLED**
⇒ **进程活着，只是帧循环停了**；focus=0；`focus 1→0` 发生在停摆前 **2.6 秒**。
段 #0 的 19 个 STALLED 是**装载期假警报**（帧号=1，游戏还没进帧循环；v0.63 的 `frames>=60` 闸门就是为它加的）。

### 排掉的

- 崩溃（CrashLogger 只有启动 5 行）、WER AppHang/AppCrash（本时段无；同时段 WER 正常记录了 explorer 的 AppHang，所以不是 WER 不工作）
- **TDR：System 日志 `Display` 提供商历史 25 条只有 4125（自动 HDR），无 4101/4102**
- **焦点死锁：本次 focus=1 全程、根本没有 Alt+Tab ⇒ 上一轮结论被自己的仪表否掉**
- 设备丢失

### 顺带挖出的环境事实：`TdrDelay = 30`（默认 2）

`HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers`：`TdrDelay=30`、`TdrDdiDelay=30`。
⇒ **GPU 卡死在头 30 秒里完全不留痕迹**（无 TDR 事件、无复位、无日志），用户只看到永久冻结然后手动结束进程。
（多半是为 ENB/CS 长着色器编译设的，**别盲目改回 2**。）

### 定案：我 v0.71 加的两个东西就是根因

`stage="d3d11 Wait"` 是**帧跑完时**设的最后一个 stage（设完即 return），而
`ID3D11DeviceContext4::Wait` 官方文档写明**等价于 `ID3D12CommandQueue::Wait`** ——
**GPU 侧排队等待，不阻塞 CPU**。所以那一帧是跑完的，线程是 **Present 返回之后**才停的。

1. **给正常路径加了 `DXGI_PRESENT_DO_NOT_WAIT`**：这套设计**依赖 Present 阻塞** ——
   `FLIP_DISCARD`+`BufferCount=3` 下翻页队列满是"CPU 不许跑到 GPU 前面"的唯一刹车，
   而紧接着就要 Reset 命令分配器。**这不是优化，是把同步机制拿掉了。**
2. **在 Present 中途切 DLSS-G 模式**（`slDLSSGSetOptions(eOff)`）+ `focusBlock` 在 `mode` 仍 `eOn` 时跳过 `slEvaluateDLSSG`。
   pacer 期望每帧一次评估。

**真正的死锁面**：每帧排一条跨队列链
`d3d11 Signal → d3d12 Wait → [D3D12 干活+Present] → d3d12 Signal → d3d11 Wait`，
它假设 D3D12 队列永远能做完一帧 —— 而"没人能显示的窗口"恰好打破这个假设。
D3D12 卡住 → D3D11 被堵死 → 引擎下一次 D3D11 操作永远等下去 ⇒ 冻结/有声/不崩溃/不 TDR。

### v0.72 改动（`tools/add_v072_unfocused_bypass.py`，6 处）

- **失焦时提前返回**：只做一次 `Present(0, DO_NOT_WAIT)`，**不做 interop 拷贝、不评估 DLSS-G、不排任何跨队列 fence**，更新 `frameIndex` 后 return
- 删掉中途 `SetDLSSGOptions(..., false)` 调用 + `g_focusOffSent` 全局
- 两处 `Present` 恢复成**普通阻塞**（`Present(0, Flags)` / `Present(1, Flags)`）
- 菜单守卫去掉 `focusBlock`
- 看门狗行新增 **`fence=完成值/完成值`**（GPU 侧围栏）—— 区分"队列停了"与"CPU 侧被挡"的唯一一个数
- 保留 v0.71 的纯仪表：每帧焦点采样、`FOCUS lost/regained`、`focus=` 字段、200 ms tick

原则：**不去跑赢死锁，而是从构造上让它不可能发生**（失焦期间队列上没有任何工作）。

DLL `cfc8b08d013c37e78a9e72c2bf1e8a41`（1292288 B），构建产物与 mod 目录 **md5 一致**，
`BUILD SUCCESS` 零告警。源码 `DX12SwapChain.cpp fb54ee6b0f2f7fb7de8a54c4af983614`。
备份 `src/DX12SwapChain.cpp.bak-20260918-001232`。

### 读取器新增（本轮真正破案的工具，已固化）

`read_xray_log.py` 新增 **"0b. 全部运行段"**：切分**跨运行追加**的看门狗文件，
逐段列 `ticks/时长/末帧/末silent/最大silent/focus/末stage/STALLED`，
并对卡死段判 `GPU 围栏不动 ⇒ 队列死` vs `围栏在动 ⇒ CPU 侧被挡`，
装载期（帧号<60）的 STALLED 标注为**假警报**。
另修掉 4c 段的**越权结论**（"多插件同秒停摆"只能证明写日志的东西同时停了，不能证明停在哪）。

### 诚实边界

- 段 #7 是上机复现的硬证据，但**具体哪次调用堵住 D3D12 队列没有直接证据** —— 那正是 v0.72 新增 `fence=` 要给的
- 段 #6（23:40）无 STALLED 记录：主日志与看门狗在失焦那一瞬同时停，进程在卡死成形前就被结束了；症状一致但**未证实**
- 段 #8（00:05）看门狗全程健康、focus=1、无 STALLED，进程 200 ms 内消失 ⇒ **与本轮定案不是同一件事**，本轮无法解释
- 新增观察（单独跟进）：`[CAM] RELOCK after 12 consecutive jumps` 100 ms 内连发 6 次、`JUMP rejected … dist=994.6` —— 相机探针读到明显不是玩家的坐标，影响重投影质量，与卡死无关
- v0.72 **未上机验证**

### 本轮踩到的坑（都已修）

- 补丁脚本 `SURVIVE` 断言里放了**别的文件**的锚点（`const bool useDerived` 在 Streamline.cpp，不在 DX12SwapChain.cpp）⇒ 干跑 `anchor x0`
- 补丁脚本 `POST` 里写 `("focusBlock", 0)` —— **我自己新写的注释里就有 "focusBlock"** ⇒ 计数撞上自己的说明文字。**同类错误第二次**：断言要写**代码形态**（`const bool focusBlock = !winFocused;`），不要写裸词
- 读取器补丁 `R3_NEW` 生成的目标代码里出现**嵌套双引号**（`说明"所有写日志的东西同时停了"`）⇒ 会写出语法错误。改用「」
- `part_watchdog()` 是**无参**调用，我按 `part_watchdog(lines)` 写的锚点 ⇒ `anchor x0`
"""


def main():
    apply_it = "--apply" in sys.argv
    if not os.path.exists(TARGET):
        print("target does not exist yet: %s" % TARGET)
    else:
        with open(TARGET, "rb") as f:
            text = f.read().decode("utf-8")
        if MARKER in text:
            print("REFUSED -- already appended")
            return 2

    if not apply_it:
        print("bytes to append: %d" % len(BODY.encode("utf-8")))
        print("\nDRY RUN -- nothing written. Re-run with --apply")
        return 0

    if os.path.exists(TARGET):
        shutil.copy2(TARGET, TARGET + ".bak-" + time.strftime("%Y%m%d_%H%M%S"))
        with open(TARGET, "a", encoding="utf-8") as f:
            f.write("\n" + BODY)
    else:
        with open(TARGET, "w", encoding="utf-8") as f:
            f.write(BODY)

    back = open(TARGET, "rb").read().decode("utf-8")
    if MARKER not in back:
        print("READBACK FAIL")
        return 3
    print("readback OK | %d bytes" % len(back.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
