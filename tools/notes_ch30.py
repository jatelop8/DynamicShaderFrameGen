#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append ledger chapter 30 and daily note 6.24 for the 22:38 run + v1.18.

Idempotency: both targets are checked for their marker first, and the two
targets are independent, so a re-run after a partial failure still works.
LF-only is asserted for both: the ledger and the daily note are LF files, and
writing CRLF into them would break the next append's anchors.
"""

import sys
import pathlib

LEDGER = pathlib.Path("D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md")
DAILY = pathlib.Path("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md")

CH_MARK = "## 30. 第 30 章　22:38 那局 + v1.18"
DAY_MARK = "## 6.24 22:38 那局（v1.17）"

CH30 = """
## 30. 第 30 章　22:38 那局 + v1.18：**选源结了，但两天来第一次「没有可修的 bug」**

跑的是 **v1.17**（DLL `91493b4d2c5d7eaf89761e1b01eb3d`，1,353,728 B）。
开局 22:38:15，加载吃掉 21 秒（`LONG FRAME 20997.2ms`），菜单 22:38:47–22:39:01，
**世界段 22:39:01–22:39:03（约 2 秒 / 64 帧）**，用户在 22:39:03 退出。
日志 220,166 B / 1,804 行。归档 `docs/runlogs/2026-09-19-2238-v1.17-source-fixed-world-2s-no-input.log`。

### 30.1 ★★★ 选源问题终结：锁第一次站在活相机上

```
[22:38:59.586] [CAM] PC v1.17: read=389 match=289 adopt=1/1 rej=28 ref=2
               best=0.00 at proj00=0.8391 eye=(-243.05,-415.31,118.56) eyeD=0.07 PC_MOVING
[22:39:00.588] [CAM] PC v1.17: read=482 match=444 adopt=0/1 rej=66 ref=2
               best=0.00 at proj00=0.8391 eye=(-243.05,-415.31,118.56) eyeD=0.00 PC_STILL
[22:39:03.630] [CAM] PC v1.17: read=423 match=397 adopt=0/3 rej=152 ref=2
               best=0.00 at proj00=0.8391 eye=(-243.05,-415.31,118.56) eyeD=0.00 PC_STILL
```

`match/read ≈ 94%`、`best=0.00` 从 22:38:59 起每一秒都成立、`rej` 每秒 +30。
心跳 `lock(pub/hold/re/still)=5938/1/5/0 proj00=0.8391 famRej=0`。

**⇒ v1.00 的族指纹、v1.07b 的第一个到达者、v1.11 的接管门、v1.13 的内容判据、
v1.16 的夺锁 —— 全部是在错误的一侧修。v1.17 把 `RE::PlayerCamera` 从「选源依据」
升格为「唯一权威」之后，锁在 60 帧里**没有一帧**落在非相机族上。**
**⇒ 这是两天来第一个确定性成果，而且它是可测的（`match`/`best`/`rej` 三个数）。**

三次夺锁原文（`proj00` 都是 `0.8391`）：

```
[22:38:58.846] [CAM] #4988 PC TAKEOVER (v1.16): this arrival is 0.00 units from the live
               player camera pos=(-243.049,-415.315,118.624) pc=(-243.049,-415.315,118.624)
               proj00=0.8391 - dropping the lock so it re-acquires on this arrival
[22:39:01.188] [CAM] #6633 PC TAKEOVER ... pos=(-243.049,-415.312,118.558) pc=(同左)
[22:39:01.305] [CAM] #6681 PC TAKEOVER ... 同上
```

### 30.2 ★★ 族普查终于可信（v1.16 的 `kSnapFamKeyTol=1e-4` 生效）

```
FAM[0] proj00=0.149184 arr=376 moved=191 stepSum=376.23   span=(0.21,17.71,1.54)  last=(-49.50,824.49,89.46)
FAM[1] proj00=1        arr=216 moved=532 stepSum=332103   span=(980.84,530.17,11.28) last=(-952.21,886.25,103.16)
FAM[2] proj00=0.8391   arr=397 moved=0   stepSum=0.08     span=(0.0000,0.0000,0.0000) last=(-243.0493,-415.3115,118.5582)
FAM[3] proj00=0.888889 arr=26  moved=0   stepSum=0.00     span=(0,0,0)              last=(0.0000,0.0000,1.0000)
```

- **`FAM[1] proj00=1` 是两天来见过最凶的假写者**：`span x=980.84`（桶内至少两个写者，
  相距约 980 单位）、`stepSum` 每秒 +67,500、`last` 恒定 `(-952.2053,886.2523,103.1622)`、
  **`moved=532 > arr=216`**。它能满足 v1.11 的 `kCamForeignMoveTol(200)`，
  v1.00g 的同族 step-break 也会因为它的跳变把锚交给它 —— **v1.17 的门现在挡着它（`rej` +30/s）。**
- **`FAM[2]`（活相机）`moved=0`、`stepSum=0.08`、`span=(0,0,0)`** ⇒ 5 秒里累计只走 8 厘米。
  与 `eye` 逐字不变、`eyeD=0.00` 三处互相印证。
- `FAM[0]`（`0.149184`，主菜单相机）在世界段 `arr=0` —— **它已经不写了**，
  与 30.1 的结论一致。

**注意 `arr=` 是每秒值、`moved=`/`stepSum=` 是累计值**（`snapFamArrSec`/`snapFamSpanN`
每秒清零，`snapFamMoved`/`snapFamStep` **不清零**）。`moved > arr` 不是 bug，是两种量纲。

### 30.3 ★★★ 三个「差点误判」——L0 第二遍当场救回来三次

这一局我三次把**瞬时值**当成**累计值**，三次都推出完全相反的结论，三次都被回读代码推翻：

| 字段 | 我以为 | 实际 | 若没查会得出 |
|---|---|---|---|
| `inSetOptions={}` | 累计调用数 ⇒ 世界段从没调 `SetDLSSGOptions` | `g_inSetOptions.store(1/0)`（`Streamline.cpp:1981/1983`）⇒ **「此刻是否在函数内」** | 「DLSSG 没被喂」→ 去修一个不存在的问题 |
| `menuUnblockedFrames` | 总共只 unblocked 1 次 | `unblocked=1` 是**第一次 unblocked**（`DX12SwapChain.cpp:1386`，进入世界那一帧） | 「进世界后 `featureDLSSG` 掉了」→ 去修另一个不存在的问题 |
| `camPrev(ok/used)=1/60` | 重建 prev 只成功 1 次、失败 59 次 | `diag.camPrevOk` 是**赋值**（瞬时，`Streamline.cpp:1002`），`camPrevUsed` 是 `++`（累计，`:1063`） | 「prev 重建坏了」→ 第三趟白修 |

**⇒ 三者实际全部健康**：`camPrev` 60/60 全用、`featureDLSSG` 全程 true、
`SetDLSSGOptions` 无异常证据。**这一局日志里没有任何故障证据，每个指标都自洽。**

**⇒ 方法论（并入 L33）：一个「累计 / 瞬时」看错的字段，会凭空造出一个不存在的 bug。**
**声称某个计数器证明了什么之前，先去源头看它是 `= x` 还是 `++x`。**

### 30.4 ★★★★★ L33：判据只建在故障的下游，就无法命名故障

三次局面都一样、三次都读不出结论，根因不是代码，是**仪器的位置**：

```
[22:38:59.586] eye=(-243.05,-415.31,118.56) eyeD=0.07  PC_MOVING    ← 进世界那一秒
[22:39:00.588] eye=(-243.05,-415.31,118.56) eyeD=0.00  PC_STILL
[22:39:01.590] eye=(-243.05,-415.31,118.56) eyeD=0.00  PC_STILL
[22:39:02.619] eye=(-243.05,-415.31,118.56) eyeD=0.00  PC_STILL
[22:39:03.630] eye=(-243.05,-415.31,118.56) eyeD=0.00  PC_STILL
```

心跳三连：`frozen=60`（世界帧 64）、`clipDev=0.000061`、`clipW=1.000000`、
`curVP=15.0006 prevVP=15.0006`、`engPrevEqCur=61/61` ⇒ **`clipToPrevClip = I`**。
`det3=1.000000`，`[XRAY] clipGate v0.92: ... (rotation-only, expected ~1)`。
watchdog 全程 `alive=1 focus=1 presentAge` 个位数 ms、`dsync=0`、无崩溃转储
⇒ **游戏在正常出帧，没有死锁、没有崩溃。**

于是：

```
玩家站着不动      ⇒ 相机不动 ⇒ clipToPrevClip = I    ⇒ 画面不变【正确】
世界被引擎冻住    ⇒ 相机不动 ⇒ clipToPrevClip = I    ⇒ 画面不变【就是故障】
```

**两种世界，日志逐字节相同。** `eye` 是相机的**原点**，纯转视角不改它；
`matChanges` 60 帧只涨 2；`FAM[2]` 累计只走 8 厘米 —— 这些**都是下游量**，
它们只能证明「相机的输出没变」，**永远不能证明「是谁让它没变」**。

**⇒ 这就是两天读不出结论的唯一原因，而且不是代码问题。**
**⇒ 修法不是再调一个门，是换一个上游的见证。**

### 30.5 v1.18：四个上游见证（零行为改动）

`src/FrameGen.cpp` 的 `[CAM] PC` 行加 `in(keys= dc=/ fg=) plr=(…) plrD=`，
全部**在游戏之外**或在**玩家身上**，与相机链无因果关系：

| 见证 | 来源 | 能回答什么 |
|---|---|---|
| `keys` | `GetAsyncKeyState`（W/A/S/D/SPACE/SHIFT/LMB/RMB），每次到达采样、**按秒 OR** | 这一秒有没有输入进窗口 |
| `dc` / `{}` | `GetCursorPos` 的每秒累计距离 / 变动次数（`ClipCursor` 下系统光标仍在裁剪矩形内移动） | 有没有转视角（**`eye` 是原点，转视角不动它**） |
| `fg` | `GetForegroundWindow()` 的 PID 与本进程比对 | **Skyrim 失焦会暂停世界** ⇒ `fg=0` 直接就是答案 |
| `plrD` | `RE::PlayerCharacter::GetSingleton()->GetPosition()` 每秒位移 | 玩家本体有没有动（既非相机也非输入） |

判据词从 1 个变 2 个，日志自己给出结论：

```
PC_STILL INPUT_NONE  ⇒ 玩家没动，本局不判定任何东西，重跑（必须走动）
PC_STILL INPUT_SEEN  ⇒ 输入到了窗口而世界没动 ⇒ 真故障
PC_MOVING …          ⇒ 正常
```

**⇒ 这一局如果是 `PC_STILL INPUT_NONE`，那就是「本局作废」，而不是「还没修好」——
这是两天来第一次能把这两件事分开。**

### 30.6 下一局判定表

| 看到 | 结论 | 下一步 |
|---|---|---|
| `fg=0` | 窗口失焦 ⇒ 世界暂停（朴素解释，插件无责） | 查 ForceBorderless/焦点抢占 |
| `PC_STILL INPUT_SEEN` | 输入到达但世界冻结 | 查引擎暂停态（菜单/控制台/加载） |
| `PC_MOVING` + `path`/`matChanges` 同步涨 | **源与装配都对，冻结已修** | 转 DLSS5 上屏 + 20/30 系 |
| `PC_MOVING`（或 `plrD>0`）但 `eyeD=0` 且 `clipDev=0` | **源对了、装配错了** | 换官方 `recalculateCameraMatrices()`（原点平移消 fp32 精度塌陷，见 §29.6） |
| `PC_STILL INPUT_NONE` | **本局作废，不是 bug** | 重跑，**停留 ≥15 秒并真的走路** |

### 30.7 仍未解释（不动它，先做探针）

`CameraProj[0][0]` 与 `CameraProjUnjittered[0][0]` **互为倒数**：`1.1918`↔`0.8391`、
`6.70312`↔`0.149184`。抖动只改千分之几，**不可能产生倒数关系**。
族键不受影响（同族内两个值自洽），但这是个潜在雷。**先做成探针再改。**

### 30.8 产物与回退

| 项 | 值 |
|---|---|
| DLL | 1,356,800 B，md5 `03b8e540cc9e0e91f9a280afd5db57fa`（build == MO2 部署） |
| 源码 | `src/FrameGen.cpp` 95,713 → **99,492 B**，CRLF 2,027 / 裸 LF **0** |
| 补丁 | `tools/patch_v118_inputwitness.py`（4 锚点，干跑 → `--apply`，重跑 REFUSED） |
| git | commit `c940ef9`，tag **`v1.18`** |
| 回退 DLL | `src/backup-v1.18-20260919-224153/built_DLL.bin`（= v1.17，1,353,728 B） |
| 回退源码 | `git checkout v1.17 -- src/FrameGen.cpp` |
| 判据表作废 | **无**（v1.18 只加读取，不改任何门） |
"""

DAY624 = """
## 6.24 22:38 那局（v1.17）+ v1.18 输入见证

- 22:38 那局跑 **v1.17**，世界段仅 **2 秒 / 64 帧**（22:39:01–22:39:03），加载吃掉 21 秒。
- **★ 选源终结**：`[CAM] PC v1.17 … match=397/read=423 best=0.00 at proj00=0.8391`，
  心跳 `lock=5938/1/5/0 proj00=0.8391` ⇒ **锁第一次站在活相机上，60 帧无一帧跑偏**。
  三次 `PC TAKEOVER` 的 `proj00` 全是 `0.8391`。**两天来第一个确定性成果。**
- **族普查可信了**（1e-4 容差）：`FAM[2] 0.8391` 累计只走 8cm（活相机，真的没动）；
  `FAM[1] proj00=1` 是凶物 —— `span x=980.84`、`stepSum` 累计 332,103、`moved=532 > arr=216`。
  **`arr=` 是每秒值，`moved=`/`stepSum=` 是累计值**（后者不清零）。
- **三个差点误判（L0 第二遍救回来三次）**：`inSetOptions`（`store(1/0)` 瞬时）、
  `menuUnblockedFrames=1`（是「第一次」不是「总共 1 次」）、`diag.camPrevOk`（`=` 瞬时，
  `camPrevUsed` 才是 `++`）。**三者实际全健康 ⇒ 这一局日志里没有任何故障证据。**
  ⇒ 铁律：**声称某个计数器证明了什么之前，先去源头看它是 `= x` 还是 `++x`。**
- **★ L33：判据只建在故障下游，就无法命名故障。** `eye` 不动 + `clipToPrevClip=I`
  在「玩家站着不动」和「世界被冻住」两种世界下**逐字节相同**。两天读不出结论的唯一原因，
  不是代码，是仪器的位置。
- **v1.18**：加四个上游见证 —— `keys`（Win32 键态，按秒 OR）、`dc`（光标每秒距离/次数，
  `ClipCursor` 下仍可测转视角）、`fg`（前台窗口 PID ⇒ **Skyrim 失焦会暂停世界**）、
  `plrD`（`RE::PlayerCharacter` 位移）。判据词变两个：`PC_STILL INPUT_NONE`（本局作废）/
  `PC_STILL INPUT_SEEN`（真故障）/ `PC_MOVING`。**零行为改动，只读。**
- DLL 1,356,800 B、md5 `03b8e540…`（build == 部署）；`FrameGen.cpp` 99,492 B、CRLF 2027 / 裸 LF 0；
  commit `c940ef9`、tag `v1.18`；回退 `src/backup-v1.18-20260919-224153/`。
- **下一局前置条件：进世界后停留 ≥15 秒，并且真的走路。** 细节在账本 §30。
"""


def append(path, mark, text):
    b = path.read_bytes()
    if b"\r\n" in b:
        print("REFUSED: %s is not LF-only" % path.name)
        return 1
    if mark.encode("utf-8") in b:
        print("SKIP (already present): %s" % path.name)
        return 0
    path.write_bytes(b + text.encode("utf-8"))
    print("appended %d bytes to %s (now %d)" % (len(text.encode()), path.name, len(b) + len(text.encode())))
    return 0


def main():
    rc = append(LEDGER, CH_MARK, CH30)
    rc |= append(DAILY, DAY_MARK, DAY624)
    return rc


if __name__ == "__main__":
    sys.exit(main())
