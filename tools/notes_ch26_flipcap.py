#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.12 records: ledger chapter 26 + daily section 6.15.

Both target files are LF-only. The earlier version of this driver asserted
"the bare-LF count is unchanged", which is the wrong invariant for an LF-only
file -- appending lines must INCREASE the bare-LF count. The correct assertion
is per-file: the file's own EOL grows by the number of lines added, and the
OTHER EOL kind does not grow at all.
"""
import sys
import os
import time

LEDGER = "MFG_MASTER_NOTES.md"
DAILY = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md"

MARK_L = "## 26. 第 26 章"
MARK_D = "### 6.15"

LEDGER_BODY = """## 26. 第 26 章 v1.12 —— 限速器的量子是 flip，不是渲染帧

### 26.1 这一局（2026-09-19 14:55:21，v1.11，build 14:34:24）

先说结论：**v1.11 的接管触发了，但画面依旧像冻住 —— 因为游戏在世界里只跑 9.74 fps。**

| 时刻 | 事实（全部读自日志） |
|---|---|
| 14:55:21.817 | v1.11 载入，`Provider=1`，`Refresh rate: 160 Hz` |
| 14:55:51.670 | `DLSSNR CHAINED with frame generation (NRAllowWithFrameGen=1)` —— DLSS5 与 FG 同时在线 |
| 14:55:51.626 | `[CAM] pub #1 pos=(-50.00,600.00,80.00) proj00=0.149184` 首次发布 |
| 14:55:52.039 | `MENU EDGE open=1 serial=2` 进主菜单；`real=39.0` 稳定 |
| 14:56:04.143 | `MENU EDGE open=0 serial=435` 进世界 |
| 14:56:04.745 | **`#5507 FOREIGN TAKEOVER (v1.11)`** —— v1.11 的门开了，`stalePub=211` |
| 14:56:04.765 | `[MOTION] clipToPrevClip[3].w=167.815231`（最后一次非仿射告警） |
| 14:56:05.159 | `#3069 matChanges=213 ... stalePub=0 | ok` —— **之后 `clipW=1.000000`，非仿射告警不再出现** |
| 14:56:18.281 | watchdog 最后一 tick `frames=583` |

**v1.11 起作用的直接证据**：接管后 `clipDev` 开始摆动（0.011 ~ 0.547），不再是恒定
`0.000061`；`clipW=1.000000`；`[MOTION]` 告警停在 14:56:04.765 不再增长。
⇒ `clipToPrevClip` 不再是单位阵，重投影**有**运动了。

**但** `dt min/avg/max = 100.95/102.63/104.26ms`，watchdog 独立复核
`frames 535 -> 583 / 4.926 s = 9.74 fps`。**画面动不了不是因为相机冻住，是因为真的只有 10 帧。**

### 26.2 根因：限速器的量子作用在 flip 上（不是渲染帧率）

`Streamline::ReflexSleep`（`src/Streamline.cpp`，v0.63 注释块之后）：

```cpp
const double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;
capFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);
...
opts.frameLimitUs = capFps ? (1000000u / capFps) : 0u;
```

`refreshRate=160`、`capMult=4` ⇒ `want = 39` ⇒ `frameLimitUs = 25641 us`。
而 `frameLimitUs` 是**每个上屏 flip 的量子**：39 flip/s，每真实帧要 4 个 flip
⇒ 渲染侧被压成 `39/4 = 9.75 fps`。

### 26.3 四项独立印证（全部来自同一份日志，全部复现 1e6/(160/capMult-1)）

| 观测 | 日志值 | 反推 |
|---|---|---|
| `capUs`（capMult 还是 2 时） | `12658` | `1e6/(160/2-1) = 1e6/79` = 12658 ✓ |
| `capUs`（capMult 变 4 之后） | `25641` | `1e6/(160/4-1) = 1e6/39` = 25641 ✓ |
| 真实帧间隔 `dt` | `102.56 ms` | `4 x 25641 us = 102564 us` ✓（五位有效数字）|
| 真实帧率（watchdog 复核） | `9.74 fps` | `39/4 = 9.75` ✓ |
| 菜单真实帧率 | `real=39.0` | 菜单 1 flip/帧 ⇒ `39/1 = 39` ✓（GPU 受限不会恰好压在 39.0）|

`LONG FRAME 365.2ms (capUs=25641 mult=4 menu=1)` 也印着同一个 25641。
`dt` 的离散度只有 0.02 ms —— **限速器的量子是平的，GPU 受限的帧会飘。**

### 26.4 为什么之前两轮没找到

`src/Streamline.cpp` 里有一段 v0.63 注释，**把这个问题诊断得完全正确**：

> v0.54 按"渲染帧率"反推（刷新率 / 总倍数 - 1），等于把 flip 节流到 39/s；
> 而 DLSS-G 每真实帧要发 4 个 flip ⇒ 渲染侧被压成 39/4 = 9.75fps。
> 实测（2026-09-17 21:54）... 102.56 / 25.641 = 4.0000（5 位有效数字）
> 现在：cap = 刷新率 - 1 ... 倍率只用于日志里算"每真实帧几个 flip"，不再参与上限计算。

**而紧下面还有一段 v1.06 注释，把同一行改了回去**，理由是"dropping the divisor
causes 636 present fps -> the 21:27 freeze"。这个推理把 flip 上限当成了渲染上限：
若 `frameLimitUs` 是渲染上限，`capFps - 1` 才会超发；但本局的实测（`dt` = 4 倍量子、
`real` = capFps/4）**证明它是 flip 上限**，所以 v1.06 的因果是反的。
两段注释互相矛盾，代码执行的是 v1.06 那一版。

**教训：同一个文件里两段互相矛盾的注释，本身就是"这里被改坏过"的信号；
不要只看最新那段，要看哪一段能被测量证实。**

### 26.5 v1.12 改了什么（`tools/patch_v112_flipcap.py`）

1. **行为**：`want = Get().refreshRate - 1.0;`（去掉 `/capMult`）⇒ `capFps=159`、
   `frameLimitUs=6289 us`（与工程内既有注释 `capUs=6289` 一致）。flip 节流 159/s < 160Hz，
   渲染侧 `159/4 ≈ 39.75 fps`。
2. **断言**：`capFps * capMult > refreshRate` 是 v1.06 的误读，改为
   `capFps > refreshRate`（flip 上限不能超面板），并新增一行
   `Reflex cap check (v1.12): {} flip fps on a {}Hz panel = {:.1f} rendered fps at {}x`。
3. **日志**：`Reflex FLIP cap` 行不再打印 `capFps * capMult`（那会印出 636 假超发），
   改为 `~{} presented fps, ~{:.1f} rendered fps (v1.12: the cap is the FLIP rate)`。

`capMult=1`（无 FG）时改动前后都是 159，**行为不变** —— 这一步只影响多倍帧生成。
INI `ReflexFpsLimit>0` 的旁路未动：**改一行 `ReflexFpsLimit=40` 就能退回今天的行为**，
这是本改动的逃生门。

### 26.6 L0 两遍

**第一遍·手脚**：干跑 3/3 锚点 `count==1` → `--apply`；重跑被幂等 marker
（`v1.12 -- THE DIVISOR WAS THE BUG`）`REFUSED`(exit=1)；`capFps * capMult` 归零、
旧算式归零；`Streamline.cpp` 123094 → 124710 B，CRLF 2340 → 2366、裸 LF **0**；
`BUILD SUCCESS`；DLL 1,338,880 B、md5 `b51ef90b...`（build == 部署一致）；
DLL 内新串各 1 次、旧串 `presented fps (real = cap/flips)` 0 次；
仓库 INI == 部署 INI（md5 `a19307d4`），五键 `Provider=1 / FrameGeneration=1 /
NeuralRenderingEnabled=1 / MFGMaxFramesOverride=3 / NRAllowWithFrameGen=1`。

**第二遍·脑子**：
- 「`frameLimitUs` 是 flip 上限」不是假设，是**本局量出来的**（`dt`=4 倍量子、`real`=capFps/4）。
- **残余风险**：若世界里 GPU 本来就跑不到 39 fps，真实帧率会低于 39 —— 但那时
  `dt` 会**飘**而不是钉在 102.56ms。**「钉死 vs 飘动」就是区分节流与 GPU 受限的判据。**
- 本轮**没有**动锁/族指纹/接管：真实帧率变 4 倍后，接受的节拍整体改变，
  **必须先在新节拍下重测**，再决定要不要碰锁。这是纪律，不是回避。
- `docs/runlogs/`：本局日志与 watchdog 已手动存档（自动归档仍未产出文件，
  见 26.8），下一局实验不会再销毁这一局的证据。

### 26.7 下一局只看三样

| 看到什么 | 结论 |
|---|---|
| `[XRAY] serial=... capUs=6289`（不再是 25641） | 限速器修对了 |
| `dt min/avg/max` 落在 ~25ms 且**开始飘** | 渲染侧回到 ~39 fps；飘 = 真的 GPU 受限 |
| `FPS probe: real=` 从 9.8 跳到 ~39 | 合成确认，四倍帧生成第一次有可用的呈现节奏 |
| `dt` 仍钉在 102.56ms、`capUs` 仍 25641 | 说明还有第二处在写同一个上限 |

### 26.8 仍未解 / 未做

- **自动归档没产出文件**（`ArchivePreviousLog()` 调用顺序已对：`InitWatchdogLogPath()`
  → `ArchivePreviousLog()` → `SKSE::Init()`，`DynamicShaderFrameGen.%04d%02d%02d`
  串在 DLL 里存在）。静态检查找不到原因，**本轮不猜、不改**，先用 `docs/runlogs/`
  手工存档顶住。
- **发布出去的相机族仍可能被锁在陈旧的一族上**：本局 `[CAM] pub` 的 `pos` 冻在
  `(-952.21,886.25,103.16)` 达 12 秒，而 `[CAM] raw #8101` 读到的是活的
  `(-126.8871,-190.8163,186.3070)`。但 `matChanges` 每秒 +80、`clipDev` 非零
  ⇒ **发布的矩阵在变、`CameraPosAdjust` 这个字段不动** —— 这两件事的含义不同，
  不能在 10 fps 的节拍下下结论。**留到 v1.12 的 39 fps 环境再测。**
- **世界内 10 fps 之外的性能**：`RenderResolutionScale=0.44`（渲染 1689x950）配
  `NRRenderScale=1.00`（每个真实帧做一遍 3840x2160 的 DLSS5）仍是嫌疑，未测。
"""

DAILY_BODY = """### 6.15 15:0x v1.12 —— 世界内只有 9.74 fps：限速器量子作用在 flip 上

- **症状**：用户「还是老样子」。日志取到 14:55:21 那局（v1.11，build 14:34:24）。
- **v1.11 生效了**：`FOREIGN TAKEOVER (v1.11)` 在 14:56:04.745 触发（`stalePub=211`）；
  之后 `clipDev` 从恒定 `0.000061` 变成 0.011~0.547 摆动，`clipW=1.000000`，
  `[MOTION]` 非仿射告警停在 14:56:04.765 不再增长 ⇒ `clipToPrevClip` 不再是单位阵。
- **真问题**：`dt min/avg/max = 100.95/102.63/104.26ms`；watchdog 独立复核
  `frames 535->583 / 4.926s = 9.74 fps`。**画面动不了不是相机冻住，是真的只有 10 帧。**
- **根因**：`Streamline.cpp` 的 `want = refreshRate / capMult - 1.0` ⇒ `capFps=39`、
  `frameLimitUs=25641us`。该量子是**每个 flip** 的：39 flip/s；每真实帧要 4 个 flip
  ⇒ 渲染侧 `39/4 = 9.75 fps`。
- **四项印证**（同一份日志）：`capUs=12658`（capMult=2 时，`1e6/79`）、
  `capUs=25641`（capMult=4 时，`1e6/39`）、`dt=102.56ms = 4x25641us`、
  `real=9.74 = 39/4`；菜单 `real=39.0` 恰等于 capFps（1 flip/帧）。
- **为什么之前没找到**：文件里 v0.63 注释**诊断完全正确**，v1.06 注释把同一行改了
  回去并给出反的因果。**两段互相矛盾的注释 = 这里被改坏过；以能被测量证实的那段为准。**
- **v1.12 改动**（`tools/patch_v112_flipcap.py`，3 处）：① 去掉 `/capMult`
  ⇒ `capFps=159`、`frameLimitUs=6289`；② 断言由 `capFps*capMult > refreshRate` 改为
  `capFps > refreshRate` + 新增 `Reflex cap check (v1.12)`；③ 日志行不再印假超发 636。
  `capMult=1` 时前后都是 159 ⇒ 不影响非多倍路径。逃生门：INI `ReflexFpsLimit=40`
  可退回今天的行为。
- **L0**：3/3 锚点 count==1；幂等 marker `REFUSED`(exit=1)；`Streamline.cpp`
  123094→124710 B、CRLF 2340→2366、裸LF 0；`BUILD SUCCESS`；DLL 1,338,880 B、
  md5 `b51ef90b`（build==部署）；INI 两份 md5 `a19307d4` 一致、五键正确；
  tag `v1.12`（`640a938`）。
- **证据存档**：`docs/runlogs/2026-09-19-1455-v1.11-freeze.log` + `.watchdog.log`
  （自动归档仍不产出文件，本轮不猜、不改）。
- **下一局判据**：`capUs=6289` 且 `dt` 落在 ~25ms 开始飘、`real` 跳到 ~39。
  若 `dt` 仍钉在 102.56ms ⇒ 还有第二处在写同一个上限。
- **未动**：锁/族指纹/接管一行未改 —— 帧率变 4 倍后节拍全变，必须先在新节拍下重测。
"""


def eol_of(path):
    b = open(path, "rb").read()
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    return ("\r\n", crlf, lf) if crlf and not lf else ("\n", crlf, lf)


def plan_append(path, marker, body):
    if not os.path.exists(path):
        print(f"    MISSING {path}")
        return None
    eol, crlf0, lf0 = eol_of(path)
    text = open(path, "rb").read().decode("utf-8")
    if marker in text:
        print(f"    REFUSED, nothing written ({path}: marker {marker!r} already present)")
        return None
    add = eol + body.replace("\n", eol).rstrip(eol) + eol
    out = text + add
    ob = out.encode("utf-8")
    crlf1, lf1 = ob.count(b"\r\n"), ob.count(b"\n") - ob.count(b"\r\n")
    nlines = add.count(eol)
    ok = (crlf1 - crlf0 == (nlines if eol == "\r\n" else 0)
          and lf1 - lf0 == (nlines if eol == "\n" else 0))
    if not ok:
        print(f"    REFUSED, nothing written ({path}: EOL accounting failed "
              f"crlf {crlf0}->{crlf1} lf {lf0}->{lf1} for {nlines} lines)")
        return None
    print(f"    ok: {path}  {len(text.encode('utf-8'))} B -> {len(ob)} B  "
          f"({nlines} lines, {'CRLF' if eol == chr(13) + chr(10) else 'LF'})  "
          f"crlf {crlf0}->{crlf1} lf {lf0}->{lf1}")
    return out


def main():
    apply = "--apply" in sys.argv
    rc = 0
    for path, marker, body in ((LEDGER, MARK_L, LEDGER_BODY), (DAILY, MARK_D, DAILY_BODY)):
        out = plan_append(path, marker, body)
        if out is None:
            rc = 1
            continue
        if apply:
            open(path, "wb").write(out.encode("utf-8"))
            print(f"    WRITTEN {path}")
    if not apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
