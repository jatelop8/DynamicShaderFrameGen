#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append the machine-wide TDR fact to the user-level MEMORY.md (cross-project)."""

import shutil
import sys
import time

TARGET = r"C:/Users/Administrator/.workbuddy/MEMORY.md"
MARKER = "## 本机 GPU 卡死是「静默」的：TdrDelay=30（跨项目，2026-09-18 实测）"

BODY = r"""

## 本机 GPU 卡死是「静默」的：TdrDelay=30（跨项目，2026-09-18 实测）

```
HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers
    TdrDelay    = 30      ← 默认 2
    TdrDdiDelay = 30      ← 默认 2
```

Windows 判定"显示驱动卡死并恢复"靠超时。默认 2 秒 ⇒ 卡死会留痕：
System 日志里 `Display` 提供商的 **4101**（已停止响应并已恢复）/ **4102**。

本机是 30 秒。**后果：GPU 侧卡死在头 30 秒里完全静默** —— 无事件、无复位、无日志。
用户看到的是"画面冻结"，然后手动结束进程，**证据随进程消失**。

⇒ **诊断规则（适用于本机所有图形项目：Skyrim/ENB/CS、SnowDeformationPlugin、
DLSS5 跨游戏部署、DynamicWetness 等）**：
1. 先查 `TdrDelay`。**不是默认值时，"事件日志里没有 4101/4102"不能用来排除 GPU 卡死。**
2. 注意 `Display` 提供商**历史里全是 4125**（自动 HDR 提示，fullscreen 应用启动时打的）——
   它只能证明"从没触发过 TDR"，不能证明"从没卡死过"。
3. 排查期可临时下调（例如 10）让卡死可观测，**排查完必须恢复** ——
   这个值多半是为 ENB/CS 长着色器编译设的，盲目改回 2 会把编译变成驱动复位。

**另一条同源规则**：卡死型故障要有**跨运行追加**的证据文件。
某个文件每次运行被覆盖 ⇒ 冻结那次的日志在下一次启动后就没了。
本机 DynamicShaderFrameGen 的 `watchdog.log`（200 ms、只读原子量 + fflush）就是这种文件，
按"帧号回退"切成运行段后，冻结那次的形状（帧停 + silent 涨 + 还在写 STALLED）一眼可见。
"""


def main():
    apply_it = "--apply" in sys.argv
    with open(TARGET, "rb") as f:
        text = f.read().decode("utf-8")
    if MARKER in text:
        print("REFUSED -- already appended")
        return 2

    anchor = text[-60:]
    n = text.count(anchor)
    print("tail anchor x%d" % n)
    if n != 1:
        print("REFUSED -- tail anchor not unique")
        return 2

    out = text + BODY
    if out.count(MARKER) != 1:
        print("REFUSED -- post-condition failed")
        return 2
    print("post-conditions OK | +%d bytes" % (len(out.encode("utf-8")) - len(text.encode("utf-8"))))

    if not apply_it:
        print("\nDRY RUN -- nothing written. Re-run with --apply")
        return 0

    shutil.copy2(TARGET, TARGET + ".bak-" + time.strftime("%Y%m%d_%H%M%S"))
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))
    back = open(TARGET, "rb").read().decode("utf-8")
    if back.count(MARKER) != 1:
        print("READBACK FAIL")
        return 3
    print("readback OK | %d bytes" % len(back.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
