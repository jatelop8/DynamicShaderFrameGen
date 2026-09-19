#!/usr/bin/env python3
"""Rewrite the workspace MEMORY.md index after the 23:22 run.

Five asserted replacements. Every anchor must occur exactly once, else REFUSED.
Dry-run by default; --apply writes.
"""

import hashlib
import sys
from pathlib import Path

P = Path(r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/MEMORY.md")

EDITS = []


EDITS.append((
    "chapter count 31 -> 32, add L36",
    "**权威账本 `D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md`（31 章 + L0–L35）——动手前先读，改动后追写（只追加，写证据原文）。本文件只是索引，细节一律查账本。**",
    "**权威账本 `D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md`（32 章 + L0–L36）——动手前先读，改动后追写（只追加，写证据原文）。本文件只是索引，细节一律查账本。**",
))

EDITS.append((
    "replace the two stale sections (shape + prime suspect) with the falsified list",
    """## ★★★★★ 最重要的一条：问题的形状变了（22:54 用户定案）
问「卡是哪种」→ **「画面完全定死」**；问「那 7 秒内按过键吗」→ **「画面卡死了，怎么动啊？」**
⇒ **四局世界段只有 2–7 秒、`keys=0x0`，不是「玩家没动」，是「画面从进世界就定死、看一眼就强退」。**
⇒ v1.18 的四个见证在回答一个没人问的问题；**L33 的含糊消失，换成：渲染循环活着，画面不活。**

| 事实 | 来源 | 含义 |
|---|---|---|
| `watchdog alive=1 focus=1 presentAge` 个位数 ms、30 帧/秒、`dsync=0`、无崩溃转储 | 独立线程 | **渲染循环全程活着** |
| 日志**句中截断**、无 shutdown、进程消失 | 两个日志文件 | 进程被强杀/卡死后杀掉 |
| `presented per real frame = 4`、`mult(acc/pres)=4/4` | 插帧 | 4x 一直在产出 |
| `DLSSNR frames=539 status=initialized 310.8.0.0` | DLSS5 | NR 一直在跑 |
| `clipDev=0.000061 clipW=1.000000` ⇒ `clipToPrevClip=I` | 相机链 | 画面＝重复同一帧 |

**⇒ 唯一形状：喂给 DLSS-G 的那张彩色缓冲是陈旧的。**

## ★★★★★ 头号嫌疑（INI 自己写明，v1.01 引入）
`DynamicShaderFrameGen.ini` 第 218 行原文：
> `1 = NR runs first on the real frame and DLSS-G then interpolates the neural-rendered result.`
> `(NR writes swapChainBufferWrapped, which is what EvaluateDLSSG reads, with the D3D11->D3D12 fence between them)`
> `Start at 0 if the picture flickers`

**「NR 写 `swapChainBufferWrapped`，而 `EvaluateDLSSG` 读的就是它」** ⇒ NR 写入不落地
⇒ DLSS-G 每个真实帧读同一张陈旧缓冲 ⇒ **画面定死而 `Present` 一直成功**。**`NRAllowWithFrameGen` 是 v1.01 才有。**""",
    """## ★★★★★ 两条主线已被**否定**（别再沿它们往上修）
1. **NR↔DLSS-G 串联不是冻结原因**（23:22 结案）。INI `NRAllowWithFrameGen` 翻成 `0` 后日志原文
   `DLSSNR suppressed: frame generation is active` ⇒ NR 整个被压掉，故障照旧。第 31 章的「头号嫌疑」作废。
2. **「引擎半死 / 游戏暂停」也不成立**。`hrsD=0.005342…0.005609`/秒 = **timescale 20**（0.0055×3600=19.8），
   且 `paused=0 ld=0 fade=0 menuOpen=0` ⇒ **游戏在正常模拟。**
★ 方法论：INI 自己写明的机制再合理也只是**假设**；只有真把开关翻过去、拿到同样故障，才变成**否定**。

## ★★★★★ 当前真正的未知，一句话
**相机（和玩家）自进世界起一帧都没动**：`frozen=90/90`、`plrD=0.00`、`eyeD=0.00`、`clipDev=0.000061`；
**Transfusion 独立算出同一结论**（`[MOTION] route=slSetConstants clipToPrev=identity`）。
**★ 但这三个见证全部由「相机」派生 ⇒ 结构性盲区：分不出「相机静止（画面本该静止）」和「画面陈旧」。**
**⇒ 全部由一个上游量派生的见证 = 没有独立性 = 无法证伪。**（与「用僵死常量做门 = 空操作」同构。）

**已确证的健康面（两个独立插件互证）**：`real=25.51ms`、`dt 23.73/25.54/30.10`、`longFrames=0`、无崩溃转储；
**4x 真在产出** —— DFG `presented per real frame = 4` + `mult(acc/pres)=4/4`，
Transfusion `DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)`。
**⇒ 用户「四倍感觉没成功」被硬证据否定。**""",
))

EDITS.append((
    "replace the v1.19 reading table with the new control-group protocol",
    """## ★ 下一局看什么（判据全在 `[CAM] PC v1.19` 一行）
`in(os=0x… dc=…/… fg=…) plr=(…) plrD=… LIVE paused=… ld=… fade=… hrs=… hrsD=… rawD=… PC_STILL/PC_MOVING INPUT_SEEN/INPUT_NONE`

| 看到 | 结论 | 下一步 |
|---|---|---|
| **画面活过来了**（INI `NRAllowWithFrameGen=0` 后） | **就是 NR↔DLSSG 串联** | 修 v1.01 那条交接（fence/顺序/输出目标） |
| `LIVE hrsD>0` 或 `rawD>0`，画面仍定死 | 游戏在模拟 ⇒ **陈旧的帧是我们自己的** | 查 NR→DLSSG 交接；`EvaluateDLSSG` 的输入是否刷新 |
| `LIVE paused=1` / `ld=1` / `fade=1` | 游戏被暂停/卡加载 ⇒ `clipToPrevClip=I` 只是**症状** | 查谁把它按住了（引擎/他模组） |
| `hrsD==0` 且 `paused=0` 且 watchdog 仍在出帧 | 引擎半死（逻辑停、渲染走） | 查主线程卡在哪 |
| `PC_MOVING` + `path`/`matChanges` 涨 | 源与装配都对 | 转 DLSS5 上屏 + 20/30 系 |

**⚠ `paused/ld/fade` 是那一秒最后一次采样的瞬时值（不是每秒 OR）；`hrsD/rawD` 是每秒增量。量纲不同，别混。**""",
    """## ★ 下一局看什么 —— 一刀两半的对照组
**已改（只改 INI 三行，见下）**：本轮 Experiment = **复现用户自己说过的「FSR3 2x + DLSS5」**。

| 看到 | 结论 | 下一步 |
|---|---|---|
| 画面活了、能走 | 冻结是 **DLSS-G / 多倍** 支线独有（吻合「v0.39–v0.50 正常，MFG 引入故障」） | 回 `Provider=1`，只在 MFG 分支内二分 |
| 还是定死 | 冻结**不在**帧生成这条路上 ⇒ 插件之外（ENB / 他模组 / 存档 / 驱动） | 停手改插件，转查外部 |
| `os=0x…` 有值 且 `plrD>0` | 输入通路通，之前「卡」是 4 秒的印象 | 继续玩看极限 |
| `os=0x…` 有值 但 `plrD=0.00` | 键到了 OS，游戏不收 ⇒ 输入被拦 | 查拦截者（ImGui 菜单 / 他插件） |
| 按住 W 仍 `os=0x0` | **探针本身坏了** | 换探针，别再拿它当证据 |

**★★ 运行协议（必须照做，否则白跑）**：① 进世界**站着不动 15 秒**；② **按住 W 走 5 秒以上**；③ 再退。
23:22 那局世界段只有 **4.5 秒** + `os=0x0 dc=0/0` 零输入 ⇒ **我分不清「没按」和「按了没进去」。**
`[CAM] PC v1.19` 每秒一行：`in(os= dc= fg=) plr= plrD= LIVE paused= ld= fade= hrs= hrsD= rawD=`。
**⚠ `paused/ld/fade` 是那一秒最后一次采样的瞬时值；`hrsD/rawD` 是每秒增量。量纲不同，别混。**""",
))

EDITS.append((
    "environment / current state: code v1.19, INI now the known-good control",
    """**当前 `v1.19`**（存活见证：游戏时钟 + 暂停态 + 加载/淡出菜单，**零行为改动，只读**）：
DLL 1,357,824 B、md5 `df726bcd8ce70d800b9d01fc6f45c06f`、commit `dd1b004`、tag `v1.19`；
补丁 `tools/patch_v119_liveness.py`（4 锚点，干跑默认，重跑 REFUSED）。
**★ INI 已改（对手），本轮 Experiment**：`NRAllowWithFrameGen` `1→0`（md5 `ed9655ad…`，CRLF 259，14,525 B）；
备份 + 一行还原：`src/backup-ini-20260919-2310/DynamicShaderFrameGen.ini.bak`（原 md5 `a19307d47caeb513b9ef6a16c4a83a42`）。
- **回退**：节流 → INI `ReflexFpsLimit=40`；**纯 2x 可玩 → `Provider=0` + `MFGMaxFramesOverride=0`**；
  **回 v1.18b** → `git checkout v1.18b -- src/FrameGen.cpp`（DLL 用 `src/backup-v1.19-*/built_DLL.bin`）；
  回 v1.17 → `git checkout v1.17 -- src/FrameGen.cpp`。备份目录不入 git，只在磁盘上。""",
    """**代码仍是 `v1.19`**（存活见证：游戏时钟 + 暂停态 + 加载/淡出菜单，**零行为改动，只读**）：
DLL 1,357,824 B、md5 `df726bcd8ce70d800b9d01fc6f45c06f`、commit `dd1b004`、tag `v1.19`；
补丁 `tools/patch_v119_liveness.py`（4 锚点，干跑默认，重跑 REFUSED）。
**★★ INI 现在 = 「已知良好对照组」（23:27 改，只改 INI 三行）**：
`Provider` `1→0`、`MFGMaxFramesOverride` `3→0`、`NRAllowWithFrameGen` `0→1`
⇒ md5 `478bb555acd84b1e5c101a098c0607f0`、14,559 B、CRLF 261 / 裸 LF 0；
补丁 `tools/patch_v120_ini_known_good.py`（干跑默认 / `--apply` / `--revert` / 标记幂等）；
备份 `src/backup-ini-20260919-2327/DynamicShaderFrameGen.ini.bak`（原 md5 `ed9655ad2bd0d2576d7f7e9d200a3f4c`）。
⚠ `Provider=0` 后 FSR3 `numGeneratedFrames` 硬编码 1 ⇒ **这一组是 2x，不是 4x**；是诊断对照，不是目标。
- **回退**：节流 → INI `ReflexFpsLimit=40`；**纯 2x 可玩 → 就是现在这组**；
  **回 v1.18b** → `git checkout v1.18b -- src/FrameGen.cpp`（DLL 用 `src/backup-v1.19-*/built_DLL.bin`）。""",
))

EDITS.append((
    "known-not-done section",
    """**DLSS5 输出上屏**：只证了在跑（`status=initialized`），**上屏未证**。**冻结**：仍未证修好（本轮 Experiment 要回答）。""",
    """**DLSS5 输出上屏**：只证了在跑（`status=initialized`），**上屏未证**。**冻结**：仍未证修好（对照组要回答）。
**族标签作废**：`proj00=0.149184` 本局出现在 `eye=(0.00,0.00,128.00)`（加载期空相机）、`best=603.99`
⇒ 旧账本写它「= WORLD 族（随玩家动）」**站不住**。`FAM[1] proj00=1` 一秒涨 `stepSum +94,803`（~592/步）= **噪声族**。
**未被解释**：Transfusion `Jitter` 世界加载前后 1.4–6.4ms → **51.14/51.26ms** 并停住；本轮 crash.log 零异常记录。""",
))


def md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    apply = "--apply" in sys.argv
    src = P.read_bytes()
    text = src.decode("utf-8")
    print("file  : %s" % P)
    print("size  : %d B, md5 %s" % (len(src), md5(src)))
    print()

    for label, old, new in EDITS:
        n = text.count(old)
        print("[%s] count=%d  %s" % ("OK " if n == 1 else "BAD", n, label))
        if n != 1:
            print("REFUSED, nothing written")
            return 1

    for i, (label, old, new) in enumerate(EDITS):
        text = text.replace(old, new, 1)

    # post-conditions
    print()
    checks = [
        ("32 章", text.count("（32 章") == 1),
        ("no NR prime suspect", "头号嫌疑（INI 自己写明" not in text),
        ("NR falsified present", "NR↔DLSS-G 串联不是冻结原因" in text),
        ("timescale 20 present", "timescale 20" in text),
        ("no-Independence lesson", "没有独立性 = 无法证伪" in text),
        ("new ini md5 present", "478bb555acd84b1e5c101a098c0607f0" in text),
        ("old ini md5 kept as backup", "ed9655ad2bd0d2576d7f7e9d200a3f4c" in text),
        ("run protocol present", "按住 W 走 5 秒以上" in text),
        ("control group table", "一刀两半的对照组" in text),
        ("stale table gone", "切 4x 三键" in text),
    ]
    bad = False
    for name, ok in checks:
        print("[%s] %s" % ("OK " if ok else "BAD", name))
        if not ok:
            bad = True
    if bad:
        print("REFUSED, nothing written")
        return 1

    out = text.encode("utf-8")
    print()
    print("size  : %d B (was %d, %+d)" % (len(out), len(src), len(out) - len(src)))
    print("lines : %d" % out.count(b"\n"))
    print("md5   : %s" % md5(out))
    if not apply:
        print()
        print("DRY RUN - nothing written. Pass --apply to write.")
        return 0

    P.write_bytes(out)
    back = P.read_bytes()
    if back == out:
        print()
        print("VERIFIED: read back identical, %d B, md5 %s" % (len(back), md5(back)))
        return 0
    print("ERROR: read back differs")
    return 1


if __name__ == "__main__":
    sys.exit(main())
