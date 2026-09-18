#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append the 23:40 -> v0.71 section to today's workspace memory."""

import os
import shutil
import sys
import time

TARGET = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-17.md"
MARKER = "## 23:40 画面冻结（进世界成功了）→ v0.71 失焦 Present 死锁"

BODY = r"""

---

## 23:40 画面冻结（进世界成功了）→ v0.71 失焦 Present 死锁

**用户原话**：「现在进游戏了，但是却卡死了，有声音，但是画面冻结」。
进世界成功 = v0.69/v0.70 修复到位；这次的冻结**与"闪"无关**，是另一个根因。

### 定案：失焦（Alt+Tab）→ `FLIP_DISCARD` 交换链的 `Present` 永久阻塞

- 全日志语料的**最后一行**在 `DirectionalMovement.log`：
  `[23:40:22.221] [31204] [I] [DMK] WM_ACTIVATEAPP: Game lost focus. Clearing inputs.`
- `ShadowLimitFix.log` 逐帧日志停在 `23:40:22.166`（早 55 ms）；同秒 `LeftAlt` 1→0。
- **五个互不相干的日志器同秒停摆**（DynamicSnow / ShadowLimitFix / DirectionalMovement /
  本插件主日志 / 本插件看门狗线程）⇒ **进程级停摆，帧循环自己停了**。
- 排除：无崩溃日志、**无 WER 报告**（ReportArchive/Queue 只有 20:19 系统更新项）、
  **无 TDR**（`Display` 提供商无 4101/4102）、无 `DEVICE_REMOVED`。
- 机理：`FLIP_DISCARD` + `BufferCount=3` + `Present(0, Flags)`（**无** `DO_NOT_WAIT`）；
  被遮挡/后台窗口 DXGI **停止释放缓冲** ⇒ `Present` 永不返回。**MFG 4x 每真实帧交 4 帧给 3 深队列**，
  本就贴满 ⇒ 一失焦**下一个 `Present` 就楔死**（不是晚一点，是永久）。
- 本插件此前 **`GetForegroundWindow`/`IsIconic`/`WM_ACTIVATEAPP`/`DO_NOT_WAIT` 全工程 0 处**。

### 跨插件日志 mtime = 手边最便宜的"进程级探针"

判别"单个插件故障" vs "整个帧循环停了"：挑 3 个以上**别人写的**插件日志看 mtime，
同秒一起停摆 ⇒ 帧循环停了。已固化进读取器 `part_focus()` 的判据里。

### 交付（全部落盘 + `BUILD SUCCESS` 零告警 + 独立回读）

- **v0.71**（`tools/add_xray_v071.py`，9 处 / 3 文件）：焦点采样（**在守卫之前**）、
  失焦边沿一次性 `SetDLSSGOptions(..., false)` 停机、`focusBlock` 与 `menuBlock` 同级直通
  且清 `dlssgFailCount`、两处 `Present` 失焦带 `DXGI_PRESENT_DO_NOT_WAIT`
  （`STILL_DRAWING` 当"这帧没显示"不进 `ThrowIfFailed`）、看门狗 1000→200 ms 且加 `focus=` 字段。
- **071b**：`GetForegroundWindow() == hwnd` 在包装窗口下**永远为假** ⇒ 改比根窗口
  `GetAncestor(h, GA_ROOT)`；`fg == nullptr`（锁屏/模式切换）按"前台"处理。
- **071c / 071d**：`DXGI_SWAP_CHAIN_DESC1` **没有** `OutputWindow`（那是旧版 `DXGI_SWAP_CHAIN_DESC` 的）
  ⇒ 改用 `swapChain->GetHwnd()`；而它是**出参 + HRESULT**，不是属性 getter（`C2660`）。
- DLL `6f377cd8241b2ec170f847a004be6c82`（1292288 B），构建产物与 `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/` **md5 一致**。
- 源码 md5：`DX12SwapChain.cpp 8b1008004acda6978a6153459be0da17` / `Streamline.cpp 97d311154abfd7a79482b8acb421a9dd` / `Streamline.h 4c4a8c1fc93da847c873c2e2ec0f3719`。
- 备份 `src/*.bak-20260917-234942` / `-235057` / `-235544`。
- 读取器：`tools/patch_reader_v071.py`（`WD_RE` 加可选 `focus=` 组 + 新增 **"4c. 焦点 / Present 死锁"** 段 +
  跨插件日志 mtime 交叉验证）；`tools/fix_reader_uicheck_v071e.py`（修 `ui=0` 假判据）。
- 交接文档 `D:/Modding/DynamicShaderFrameGen/FIX_FOCUS_PRESENT_V071.md`。

### 顺手结清的旧悬案

- **`menuOpen=0` 是真的没菜单**，不是探针坏：`MENU PROBE` 里 `mainMenu`/`loadingMenu`/`journalMenu`
  三个指针**两两与字面名指针相等** ⇒ InterfaceStrings 布局正确。
- **v0.69/v0.70 确认生效**：`[FrameGen] DLSSNR suppressed` 出现且全程无 `[DLSSNR] frames=` 增长；
  `menu=1200 edges=2 resetTrue=1`；`MENU EDGE open=1/0` 各一次；`RUN TIME` 与 `RUN START` 构建戳分离成功。
- **"双线程并发 Present"不成立**：世界阶段全部单线程 `31204`，`serial` 增速 == 真实帧率。
- `frozen` 涨（71→101）是"引擎 `prevViewProj` 冻结"计数（`engPrevEqCur` 常态），**不是卡死信号**。

### 本轮踩到的坑（都已修）

- **读取器子串判空自伤**：`if "ui=0" in raw` —— `"ui=0"` 是 `"ui=0x7ff745c3ceb0"` 的**前缀**，
  于是每次正常运行都报「RE::UI 单例为空 → CommonLib 地址/版本问题」，**且与自己上一行的
  「InterfaceStrings 布局正确」直接矛盾**，还进总结。改成 `re.search(r"\bui=(0x[0-9a-fA-F]+|\d+)", raw)`
  + `int(v, 0) == 0` 判值。**镜像通则：判空/判坏同样不能写会撞上健康输出的子串。**
- **补丁脚本自身编码用错**：`fix_reader_uicheck_v071e.py` 第一版用 `latin-1` 读目标文件，
  而锚点含中文 ⇒ **永远 `anchor x0`**。「latin-1 保字节往返」只适用于**非 UTF-8** 的文件（ENB ini）；
  UTF-8 源码必须按 UTF-8 读。按文件分编码。
- `add_xray_v071c.py` 断言自伤：FFX 路径的 `a_swapChainDesc.OutputWindow` **包含**
  `swapChainDesc.OutputWindow` 子串 ⇒ 改判"精确调用"形式。

### 诚实边界（未定案）

- **本次没有 `RENDER THREAD STALLED`**：看门狗是独立线程，若渲染线程真永久卡在 `Present`，
  它应在 1.5 s 后打 STALLED。它没有 —— 因为**看门狗自己也停了**。两种解释都符合数据：
  (a) 挂死后 1.5 s 内进程结束；(b) 整个进程停了（含被手动结束）。
  **`focus=` 字段就是为下一跑区分这两者加的。**
- 不能 100% 排除"失焦后用户从任务管理器结束进程"而 spdlog 尾部缓冲吞掉最后日志（本工程历史上发生过一次）。
- `dvd(ok/used)=0/0 err=16` 三字段矛盾（残值）未清。
- `countedFrameIndex` 与每帧 5 次 `slSetConstants` 的同步性未查（本跑单线程，风险下降但未排除）。
- 菜单直通路径仍在 `menuBlock` 判定**之前**发 PCL 模拟区间 marker。
- `engineMvec=false` 依旧存在，插帧仍只能靠相机重投影。
- **v0.71 系列未上机验证**（由用户下跑验收）。
"""


def main():
    apply_it = "--apply" in sys.argv
    with open(TARGET, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")

    if MARKER in text:
        print("REFUSED -- already appended")
        return 2

    anchor = text[-60:]
    n = text.count(anchor)
    print("target: %s" % TARGET)
    print("bytes before: %d | tail anchor x%d" % (len(raw), n))
    if n != 1:
        print("REFUSED -- tail anchor not unique")
        return 2

    out = text + BODY
    if out.count(MARKER) != 1:
        print("REFUSED -- marker count != 1 after append")
        return 2
    for s in ("FIX_FOCUS_PRESENT_V071.md", "6f377cd8241b2ec170f847a004be6c82"):
        if out.count(s) != 1:
            print("POST FAIL: %r x%d" % (s, out.count(s)))
            return 2
    print("post-conditions OK | +%d bytes" % (len(out.encode("utf-8")) - len(raw)))

    if not apply_it:
        print()
        print("DRY RUN -- nothing written. Re-run with --apply")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(TARGET, TARGET + ".bak-" + stamp)
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))
    back = open(TARGET, "rb").read().decode("utf-8")
    if back.count(MARKER) != 1:
        print("READBACK FAIL")
        return 3
    print("readback OK | %d bytes | appended %s" % (len(back.encode("utf-8")), MARKER[:40]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
