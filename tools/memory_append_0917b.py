#!/usr/bin/env python3
"""Append/insert the 2026-09-17 findings into the memory files.

Anchors must match exactly once; insertions carry markers so a re-run refuses.
Both target files are LF - verified before writing, and line endings are
re-verified after (the Edit tool has been observed silently converting CRLF to
LF, so nothing here relies on it).
"""
import os
import sys

APPLY = "--apply" in sys.argv

MEM = r"C:\Users\Administrator\.workbuddy\MEMORY.md"
LOG = r"C:\Users\Administrator\WorkBuddy\2026-09-17-11-48-48\.workbuddy\memory\2026-09-17.md"

TAIL_ANCHOR = "  + `midpointPatched=1`）。**别把探测期的噪声当成结论。**\n"
MO2_ANCHOR = "把 `QualityMode`/`RenderResolutionScale`/`Sharpness` 整行删了）。\n"

NEW_SECTIONS = TAIL_ANCHOR + """
## 帧生成：「声明 ≠ 实际」—— 所有"生效性"证据全绿但画面还是错的（跨项目，2026-09-17 实锤并修复）

**症状**：`DLSSG presented per real frame = 4`（真在插 4x）、渲染帧率稳如尺子、Reflex 限帧生效、
无崩溃无报错 —— **但画面一直闪**。
⇒ **「渲染有没有跑」和「渲染内容对不对」是两个独立轴。前者全绿不代表后者对。**
凡是"改动确实生效了 + 画面还是不对"，就要往「送进运行时的**数据**对不对」上查，别再盯 fps。

**根因**：同一对缓冲被三种方式描述成不同尺寸，其中写死的那个是错的。

| 来源 | 颜色 | depth / motion |
|---|---|---|
| 互操作纹理实际尺寸（创建代码 + 运行日志） | 2560x1440 | 2560x1440 |
| `DLSSGOptions::mvecDepthWidth/Height` | 2560x1440 | 2560x1440 |
| `ResourceTag::extent`（**写死的**） | 2560x1440 | **1706x960 ← 错** |

颜色/运动矢量的空间对应差了 `1/0.667 = 1.5 倍`，而**这一对正是每一张插帧的输入**
⇒ 每张插帧的运动都是错的 ⇒ 屏幕在「正确的真实帧 / 错误的插帧」之间按生成频率交替
⇒ **持续闪烁**。（陈旧值来自更早版本，那时纹理确实是渲染分辨率；后来为 FSR3 改成输出分辨率，
tag 没跟改。同病第二出口：`CreateInterop` 有**两条创建路径**，主动路径按引擎 kMAIN desc 建
（渲染分辨率）、惰性路径强制输出分辨率 ⇒ 同一块缓冲因"先跑哪条路径"而尺寸不同。）

**两条权威依据（NVIDIA 头文件原文，别再靠推理）**：
- `sl_dlss_g.h`：`mvecDepthWidth` = *"Expected width of the input render targets
  (depth, motion-vector buffers etc)"* —— 是**这两个缓冲自己的**尺寸，不是 swapchain。
- `sl.h`：`ResourceTag::extent` = *"The area of the tagged resource to use (if using the
  entire resource leave as null)"* —— 声明小了等于告诉 DLSS-G「只用这块资源的这个角」。

**修法（根治，不是改数字）**：一个数字都不写死 —— extent 取自 `ID3D12Resource::GetDesc()`，
options 的 mvec/depth 取自 D3D11 互操作纹理的 `GetDesc()`。**单一来源 ⇒ 以后任一侧改动都不会再脱节。**
**通用规则：凡"两条创建路径 + 一处写死的尺寸"的代码，都按这条查。**

**关于 `refreshRate / mult - 1`（2026-09-17 复审：不是 bug，别乱改）**：
160Hz/4x → 39fps 渲染 → 156 present。看着该整除成 40，但 156 就是"比面板上限低 4Hz"，
正是 VRR 的通行建议（贴着上限会触发 VRR ceiling → 掉回 VSync 反而抖）。跑 VRR 时面板会跟着
156fps 那条流走，不存在节拍对不齐。要动只能用 INI `ReflexFpsLimit` 实测。

**DLSSG-Transfusion 的日志是「外部证据通道」—— 独立第二视角，别再只用插件自己的日志。**
插件日志只能证明"我调了什么"；Transfusion 能证明"运行时**收到了什么**、**实际做了什么**"。
上面那个根因就是靠它从外部钉死的。`<gamePath>\\DLSSG-Transfusion.log` 五行按价值排序：

```
DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)   # 真在出几倍帧
[MOTION-TAG] type=hudless rect=(0,0 2560x1440)                                # 颜色 tag
[MOTION-TAG] type=depth   rect=(0,0 1706x960)                                 # 与颜色不一致 = bug
[OPTIONS] Game DLSS-G options: structVersion=5 mode=eOn frames=3 uir=0 color=2560x1440
[MOTION] route=slSetConstants call=0 clipToPrev=identity prevToClip=identity projection=non-identity
[PERF] 4x | Kernel: Ada | FPS: 34.6 (28.89ms) | Jitter: 16.31ms | 1% Low: 30.8 FPS  # Jitter≈半帧 = 节奏崩
```

注意：模板大量是 **UTF-16LE**；且 `[MOTION]`/`[MOTION-TAG]` **只打头几次调用（call=0..3）**，
**加载期的 `identity` 不能当 bug 证据**（相机确实没动）—— 要判游戏内是否也为 identity，
只能在插件侧自己加探针（`clipToPrevClip` 与单位矩阵的最大偏差，每 N 帧打一次）。
JSON 里两个键直接决定闪不闪：`disableMenuDetection`（true = 菜单/加载不停插帧，违反 DLSS-G 规范）、
`mode`（`fixed` 锁死倍率，渲染跑不满「刷新率/倍率」时必然呈现欠发 + 节奏抖；`dynamic` 才自适应）。

---

## Edit 工具会**改写行尾** —— 改完必须核 CRLF/LF（跨项目，2026-09-17 实测）

除了"静默丢失改动"，Edit 工具还有第二个静默副作用：**它会把文件的换行符统一成 LF**。
实测 `framegen-diagnosis/SKILL.md` 原本**全 CRLF**（421 行），一次 Edit 之后变成
`CRLF=0 / LF=566`；同一轮里对 `CHANGELOG.md`（CRLF）的 Edit 却**保住了 CRLF** ⇒ **行为不一致，不可假设**。

⇒ **对策**：改完任何文件都跑一次行尾统计（`CRLF` / `LF_total` / `stray_CR` 三个数），
需要保住 CRLF 的文件直接用 Python 按字节写回：`t.replace("\\r\\n","\\n").replace("\\n","\\r\\n")`。
批量改动仍优先用带断言的补丁脚本（并在脚本里一并做行尾归一），不要用多次 Edit 叠。

**同时新增：一个 DLL 的"版本"只能按二进制指纹判**，不能按文件名/路径/mtime。
指纹 = 该版本独有的日志串（例：v0.54+ 才有 `Reflex render cap`；v0.50+ 才有 `MFGMaxFramesOverride`）。
用法：`for k in [b"Reflex render cap", ...]: print(k, k in open(dll,'rb').read())`，
再与构建产物比 md5，最后用日志里的 `__DATE__/__TIME__` 编译戳（`loaded (build Sep 17 2026 16:32:15)`）
反查"跑的到底是哪次构建"。
"""

MO2_ADD = MO2_ANCHOR + """
**★ 多实例指向同一 `gamePath`（2026-09-17 实测，务必先排除）**：本机 `%LOCALAPPDATA%\\ModOrganizer\\`
下有 20+ 实例，其中 **两个实例的 `gamePath` 完全相同**（都指向同一个游戏），但 `base_directory`
不同（`E:/ENB-EJ/mod` vs `E:/EJ/mod`）⇒ **同一个游戏、两套 mods 目录、同名插件两份不同内容**。
再叠加桌面/`fg_rebuild2`/`D:\\EJ-1.0\\MOD\\mods` 等打包暂存目录，同名 DLL 实测有 **5+ 份**，
其中一份还是 6 天前的旧版。**只核对"某一个路径下的 DLL"就会得出完全错误的结论。**
⇒ 三步定"哪一份是活的"：① 读实例 ini 的 `gamePath` **与** `base_directory`（两个都要看）；
② 按**二进制指纹**判各副本版本（见下节）；③ 与构建产物比 md5 + 用日志编译戳反查。
⇒ 顺带：**`find` 的 `maxdepth` 给小了会整片漏掉** —— `AppData\\Local\\ModOrganizer` 在第 4~5 层、
mods 里的插件在第 7 层以上，本次 `maxdepth 6` 直接漏了，白查一轮。找插件时不要设 `maxdepth`。
"""


def load(p):
    d = open(p, "rb").read()
    t = d.decode("utf-8")
    assert "\r\n" not in t, f"{p}: expected LF, refusing"
    return t, d


def main():
    mem, mem_raw = load(MEM)
    log, log_raw = load(LOG)
    problems = []

    if "声明 ≠ 实际" in mem:
        problems.append("MEMORY.md: marker '声明 ≠ 实际' already present -> refusing")
    if "Edit 工具会**改写行尾**" in mem:
        problems.append("MEMORY.md: line-ending marker already present -> refusing")
    if "多实例指向同一 `gamePath`" in mem:
        problems.append("MEMORY.md: multi-instance marker already present -> refusing")
    if mem.count(TAIL_ANCHOR) != 1:
        problems.append(f"MEMORY.md TAIL anchor count={mem.count(TAIL_ANCHOR)} (want 1)")
    if mem.count(MO2_ANCHOR) != 1:
        problems.append(f"MEMORY.md MO2 anchor count={mem.count(MO2_ANCHOR)} (want 1)")
    if problems:
        print("REFUSED, nothing written")
        for p in problems:
            print("  !", p)
        return 1

    mem2 = mem.replace(TAIL_ANCHOR, NEW_SECTIONS, 1).replace(MO2_ANCHOR, MO2_ADD, 1)
    assert mem2 != mem
    assert mem2.count("## 帧生成：「声明 ≠ 实际」") == 1
    assert mem2.count("## Edit 工具会**改写行尾**") == 1

    log_add = """
## 17:0x · MFG「声明 ≠ 实际」根因 + v0.56（闪烁第五轮收口）

前四轮都在证明"改动生效了"，这轮换了轴：**送进运行时的数据对不对**。

**根因（已修，提交 `135c4e4`，v0.56，md5 5a51dfb5…，已自动部署到 `E:\\EJ\\mod\\mods\\DynamicShaderFrameGen`）**：
DLSSG 的 depth/mvec 互操作纹理实际是 **2560x1440**（创建代码 + 运行日志 +
`CopyDepthToShared` 的 viewport 都指向这点，`sl_dlss_g.h` 的 `mvecDepthWidth`
也确认该填这两个缓冲自己的尺寸），但 `EvaluateDLSSG` 的 `ResourceTag::extent`
**写死成 renderExtent = 1706x960**。`sl.h` 说 extent 是"要用这块资源的哪一块"
⇒ DLSS-G 被要求只看 2560 缓冲的左上角 1706x960，颜色/运动矢量对应差 **1.5 倍**
⇒ 每张插帧的运动都错 ⇒ 画面在真实帧/错帧间交替 ⇒ **持续闪烁**。
陈旧值来自 v0.34（那时纹理确实是渲染分辨率），v0.7.8 为 FSR3 改成输出分辨率后没跟改。
**外部旁证**：Transfusion 日志 `[MOTION-TAG] type=depth rect=(0,0 1706x960)` vs
`type=hudless rect=(0,0 2560x1440)` —— 运行时自己把它收到的 tag 打出来了。
**修法**：extent 取 `ID3D12Resource::GetDesc()`、options 的 mvec/depth 取 D3D11 纹理 `GetDesc()`，
一个数字都不写死；顺带把 `CreateInterop` 两条创建路径统一为输出分辨率。

**本轮排除/推翻的（同样重要）**：
- `refreshRate/mult - 1` = 39fps → 156 present vs 160Hz：**查证后不是 bug**（156 就是"比面板低 4Hz"，
  正是 VRR 通行建议）。**没改** —— 保持本次唯一行为变量是 extent 修复。
- 部署面**是对的**（生效路径 `E:\\EJ\\mod\\mods\\DynamicShaderFrameGen`，DLL 与构建产物字节一致）。
  但另有 5+ 份过期同名副本，且**两个 MO2 实例指向同一 gamePath、mods 目录不同**
  （`EJ-ENB` 那个里面是 9月11日旧版 + `Provider=0`）。启动实例搞错等于整套 MFG 没生效。
- INI 存/读键**完全对称**（各 25 个）——v0.52 那个截断重写 bug 已彻底修好。
- `EnsureBorderless` 有提前返回，**不是**每帧动窗口，排除。
- 无 `Refresh rate` 强制逻辑：日志里的 `force=true` 其实是 `ForceEnable`（日志标签写错了）。

**新发现（未改，记着）**：DLSSG 模式下 ImGui 覆盖层与菜单画进了 `colorOutWrapped`，
而 DLSSG 分支（761–862）从不读 colorOut，非 DLSSG 的 colorOut→backbuffer 拷贝还被
`return S_OK` 跳过 ⇒ **覆盖层/菜单在 DLSSG 模式下不可见**（画到死纹理）。
不急着改：改回 `swapChainBufferWrapped` 会让 UI 进 DLSS-G 的 HUD-less 输入被一起插帧，
**正解是给 UI 独立纹理 + `enableUserInterfaceReconfiguration`**，不是换绘制目标。

**用户下一步**：完全重启游戏，按 `VERIFY_v056.md` 看 4 行日志
（`DLSSG tag dims:` 必须 2560x1440 / `presented per real frame = 4` /
走路时 `MOTION probe` 明显 >0 / Present Flags 是否含 ALLOW_TEARING）。
若仍闪，按清单顺序一次只动一个：`disableMenuDetection=false` →
Transfusion `mode: dynamic` + target 160 → `Ctrl+Alt+3` 降 3x → `NR=0` 做 A/B。

**技能已更新**：`framegen-diagnosis` 新增 ⑰（声明≠实际）/⑱（Transfusion 日志作外部证据通道）/
⑲（Invisible UI：画到死纹理）/⑳（MO2 多实例染指纹），全文 CRLF 已修复。
"""

    log2 = log + log_add
    assert log2 != log

    if not APPLY:
        print("DRY RUN - nothing written. Re-run with --apply")
        print("  MEMORY.md: +%d bytes" % (len(mem2.encode("utf-8")) - len(mem_raw)))
        print("  daily log: +%d bytes" % (len(log2.encode("utf-8")) - len(log_raw)))
        return 0

    for p, t in ((MEM, mem2), (LOG, log2)):
        open(p, "wb").write(t.encode("utf-8"))
        d = open(p, "rb").read()
        print(f"{os.path.basename(p):16} {len(d):>7} bytes  CRLF={d.count(chr(13).encode()+chr(10).encode())} "
              f"LF={d.count(chr(10).encode())} strayCR={d.count(chr(13).encode())-d.count((chr(13)+chr(10)).encode())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
