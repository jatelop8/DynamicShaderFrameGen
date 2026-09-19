#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notes_ch24_takeover.py -- record the 11:30 run (the first run with instrumentation)
and the v1.10 change, in the two append-only ledgers.

Targets
  A) D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md   -> chapter 24
  B) <workspace>/.workbuddy/memory/2026-09-19.md            -> section 6.12

Append-only. Marker guard so a second run is REFUSED. EOL from each file.
Post-conditions checked on the RESULT text.
"""

import os
import sys

CWD = "D:/Modding/DynamicShaderFrameGen"
LEDGER = os.path.join(CWD, "MFG_MASTER_NOTES.md")
DAILY = ("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/"
         "2026-09-19.md")

MARK_A = "## 24. 第 24 章"
MARK_B = "### 6.12"

CHAPTER = """
---

## 24. 第 24 章　2026-09-19 11:30 那局：**第一次拿到 4x 的实测值**，也是第一次把冻结链指到具体族

### 24.1 这一局的身份
- 11:30:56 启动，DLL = v1.09 构建（`mtime=2026-09-19 03:17` UTC = 本地 11:17，size=1335296B）。
- 11:31:27 第一个相机快照；11:33:15.6 进世界；11:33:25 结束。
- **`DynamicShaderFrameGen.20*.log` = 0 个** —— v1.09 的归档**一次都没跑**（见 24.9）。

### 24.2 ★★★ 4x 是**实测**成功的，而且 hwMax=6（推翻旧记忆）
```
[Streamline] DLSS-G supports up to 6x frame generation (5 interpolated frames per real frame)
[Streamline] MFG override 3 <= hardware max 5 - no change needed
11:33:16.432  FPS probe: real=25.4 | DLSSG | cap~=101.6 | hwMax=6 ask=4 accepted=4
11:33:18.483  FPS probe: real=9.7  | DLSSG | cap~=39.0  | hwMax=6 ask=4 accepted=4
11:33:24.637  FPS probe: real=9.8  | DLSSG | cap~=39.0  | hwMax=6 ask=4 accepted=4
```
- `accepted=4` 是 `dlssgAcceptedFrames+1`，**测量值**（`DX12SwapChain.cpp:968-973`）。
- `hwMax=6` = `dlssgMaxFramesToGenerate+1` ⇒ **运行时自报支持 6x（5 个插帧）**。
- 呈现直方图：`presented all=… world=0/12/0/0/174/…` ⇒ 世界里 **174 次 present 各出 4 个 flip**；`menu=0/371/…` ⇒ 菜单里 FG 关（`MenuDisableFrameGen=1`）。

**⇒ 结论一：4x 从来没有被上限卡住。旧记忆里「Ada 只能 2x / `dlssgMaxFramesToGenerate`=1」是错的。**
**⇒ 结论二：用户的「4x 没成功」不是"没插帧"，是"插了但没有画面推进"（见 24.3）。**

### 24.3 但画面不推进：`clipToPrevClip` = 单位阵
```
11:33:15.546 [MOTION] clipToPrevClip[3].w=-195.222366 (must be 1) - the inverse and the
             previous matrix came from different cameras
serial=399   clipDev=243.962387 clipW=-195.222366 p00(c/p)=1.1918/0.0000
稳态          clipDev=0.000061 clipW=1.000000 p00(c/p)=1.1918/1.1918
             curVP=15.0006 prevVP=15.0006 | pos=(-243.0,-415.3,118.6) prevPos=(-243.0,-415.3,118.6)
```
`prevVP == curVP` 且 `prevPos == pos` ⇒ `inv(cur)×prev = I` ⇒ DLSS-G 被告知"相机没动"
⇒ **每 4 个呈现帧里有 3 个是复制品**。

### 24.4 v1.09 的探针把"发布流冻结"变成了数字
`[CAM] pub` 第一次有输出（115 行）。首尾：
```
#52989 (11:33:15.482) pos=(-243.05,-415.31,118.56) move=0.0000 path=65.41 matChanges=168 proj00=0.8391 famRej=13575
#54489 (11:33:24.725) pos=(-243.05,-415.31,118.56) move=0.0000 path=65.41 matChanges=168 proj00=0.8391 famRej=14475
```
**`matChanges` 在 9.2 秒 / ≈2100 次发布里冻结在 168**，`path` 冻结在 65.41，`famRej` +900。
（菜单阶段则相反：`matChanges=1` 冻结、`famRej` 增长，因为相机真的静止。）
**⇒ 我们发布出去的快照是"逐字节冻结"的。这是 v1.09 探针要回答的问题，它回答了。**

### 24.5 ★★★ 锁拿着的是"场景固定的相机"，不是玩家相机
判据不是估值、不是直觉，是**跨运行的数字恒等**：
- 被锁住的位置 `(-243.05,-415.31,118.56)`，与 `Streamline.cpp` v1.07c 注释里引用的 **23:10 那局**（两天前）
  `cameraPos=(-243.049301,-415.311523,118.558205)`、`clipToPrev[3].w=-195.222366` **逐位相同**。
- 活着的相机不可能精确复现另一局的坐标 ⇒ 这组值是**场景几何**（3D 菜单 / 载入画面相机）。

而真正的活相机以 `proj00=1` 到达，**位置在走**：
```
[CAM] #67695 family rejected: proj00=1 locked=0.8391 ratio=1.1918 pos=(-125.7,210.8,188.4) dist=640.8
[CAM] #69020 family rejected: proj00=1 locked=0.8391 ratio=1.1918 pos=(255.0,804.7,-94.4)  dist=1334.8
```
反证：菜单阶段同一个 `proj00=1` 在 `pos=(-160.0,160.0,128.0)` 上**逐字节恒定**（238 条拒绝全同）
⇒ 它的行为与"活相机"完全一致：**菜单里静止、世界里走动**。

### 24.6 触发点：reset edge 把锁交给了"下一个到达"，而那一个是假的
```
11:33:15.482 [CAM] #66564 lock RELEASED on the reset edge (was proj00=0.149184 famRej=13575)
11:33:15.482 [CAM] pub #52989 ... proj00=0.8391
11:33:15.482 [CAM] #66564 -> 立即 re-acquire 成 0.8391
```
v1.07b 的注释自己写着：release 之后 "hands the lock to the first arrival after it,
**which is the world camera whenever the menu has closed**"。
**这条假设是错的** —— 重置边之后第一个到达的是场景固定的 `0.8391`。

### 24.7 而且没有任何东西能把它放掉（D2 由日志证实，不只是 grep）
```
[CAM] #66488 family rejected: proj00=0.8391 locked=0.149184 ratio=5.6246 pos=(-243.0,-415.3,118.6) still=1570/90
```
**连续 1570 次拒绝、阈值 90、什么都没发生。** `lock RELEASED` 全程 3 条，全部是 `on the reset edge`。
⇒ 与第 22 章 D2 完全一致：锁没有自己的释放路径。

### 24.8 ★ 我自己读错的两处（写下来避免再犯）
**(a) `[MFG] debug CHECK: ... blocked=396 unblocked=1` 不是缺陷。**
我第一遍读成"我们跳过了 396 次 SetDLSSGOptions"。读 `DX12SwapChain.cpp:1372-1439`：
`blocked/unblocked` 数的是 **`menuBlock`**，即菜单守卫帧数。396 = 菜单开着 396 帧；
警告之所以打，是因为**唯一那一个非菜单帧**的 `EvaluateDLSSG` 返回了 false。不是 bug。
**(b) `camPrev(ok/used)=1/90` 不是"90 次里只成功 1 次"。**
`Streamline.cpp:1002` 是 `diag.camPrevOk = camPrevOk ? 1 : 0;` —— **赋值，瞬时标志**；只有
`camPrevUsed` 是累加。它读作"此刻重建成功，且已被使用 90 次"。

### 24.9 v1.10 改了什么（已构建 = 已部署）
- `FrameGen.h`：新增 `snapForeignMove` / `snapForeignHave` / `snapForeignPos[3]` /
  `snapForeignProj00` / `snapForeignTakeover`。
- `FrameGen.cpp`：新增 `kCamForeignMoveTol=200.0f`、`kCamForeignMinRej=30`；
  **`!sameFamily` 分支尾部不再无条件 `return false`**，而是累计"被拒族自己的位移"，
  当 `still >= 30 && travel >= 200` 时**接管 anchor**（落到已有的 adopt 路径）；
  `foreignTakeover` 抑制那条会误述的 `same-family step break` 日志；
  acquire / reset-edge 两个入口都清零累计器；`[CAM] pub` 增加 `fMove=` 与 `takeover=`。
- `main.cpp`：`InitWatchdogLogPath()` **移到 `ArchivePreviousLog()` 之前**。
  v1.09 把两者写反了：归档函数从 `WatchdogLogPath()` 取目录，而那个缓冲区当时还是空的，
  于是它在第一个 guard 就返回 —— **11:30 那局一个归档文件都没有**。
- **为什么这不是 v1.07b 删掉的那个 v0.94 re-acquire**：v0.94 是"谁排在第 90 个谁赢"（只看顺序），
  所以一个静止的错族也能靠顺序夺锁（v1.07b 注释说它有一半概率落到 `proj00=1`）。
  这里被拒族**必须自己走出 ≥200 单位**才可能接管 —— 静止或陈旧的相机不可能满足。计数下限只防抖动。
- **没改**：`kCamStillTol` 依然是死常量。现在 v1.10 这条接管路径是锁唯一的自驱动释放通道。
  记为已知缺口。

### 24.10 仍未定 / 下一步
1. **真实帧率从 58（菜单）塌到 9.8（世界）**。首要嫌疑：`NRRenderScale=1.00` ⇒ 每个真实帧做一遍
   **3840×2160** 的神经渲染，而渲染分辨率只有 1689×950（INI 自己的注释就写着 "the expensive part"）。
   **未测**，一次纯 INI 改动就能界定。
2. `proj00=1` 到底是玩家相机还是"随玩家移动的非游戏相机"：**由 v1.10 的接管自己回答** ——
   改后若 `matChanges` 开始增长、`clipDev` 变成非零，它就是相机。
3. 判据（下一局）：
   - 出现 `FOREIGN TAKEOVER (v1.10)` 且随后 `matChanges` 持续增长 ⇒ 链修对了；
   - `clipDev` 在走动时明显 > 0（不再恒 0.000061）⇒ `clipToPrevClip` 有运动了；
   - `SKSE/DynamicShaderFrameGen.20*.log` 出现 ⇒ 归档修对了。
"""

DAILY_BODY = """
### 6.12 11:47　11:30 那局的结论：**4x 其实成功了，插帧内容全是复制品**；根因指到"锁拿着场景固定相机"

**用户的直觉是对的，但机制和他以为的不同。** `FPS probe: real=9.8 | hwMax=6 ask=4 accepted=4`
—— `accepted` 是 `dlssgAcceptedFrames+1`，**实测 4x 被接受**；呈现直方图 `world=0/12/0/0/174/…`
= 174 次 present 各出 4 个 flip。**4x 从来没被上限卡住，`hwMax=6`（旧记忆"Ada 只能 2x"是错的）。**

**但 `clipDev=0.000061`、`prevVP=curVP`、`prevPos=pos` ⇒ `clipToPrevClip` = 单位阵 ⇒ 每 4 帧里 3 帧是复制品。**

**v1.09 的探针把它变成数字**：`matChanges` 在 9.2 秒 / ≈2100 次发布里**冻结在 168**，`path` 冻结 65.41。

**根因（跨运行数字恒等，不是估值）**：锁住的位置 `(-243.05,-415.31,118.56)` 与 `Streamline.cpp`
v1.07c 注释里引用的 **23:10 那局**（两天前）`cameraPos=(-243.049301,-415.311523,118.558205)`、
`clipToPrev[3].w=-195.222366` **逐位相同** ⇒ 那是场景几何（菜单/载入相机），不是玩家相机。
活相机以 `proj00=1` 到达且**位置在走**（-125.7,210.8,188.4 → 255.0,804.7,-94.4），却被 `ratio=1.1918` 全部拒掉。

**触发**：`11:33:15.482 lock RELEASED on the reset edge ... - the next arrival re-acquires`，
而"下一个到达"是场景固定的 `0.8391`。v1.07b 注释假设"重置边之后第一个到达就是世界相机" —— **错的**。
**且放不掉**：`still=1570/90` 而无任何动作（D2 由日志证实）。

**我自己读错的两处（记下来）**：`blocked=396 unblocked=1` 是 **menuBlock 帧数**（`DX12SwapChain.cpp:1372`），
不是"跳过了 396 次 SetDLSSGOptions"；`camPrev(ok/used)=1/90` 里 `ok` 是**瞬时标志**（`Streamline.cpp:1002` 赋值），
不是"90 次里成功 1 次"。

**v1.10（已构建已部署，md5 `198877d1…`，tag v1.10）**：
- 被拒族**必须自己走出 ≥200 单位**才可接管 anchor（`kCamForeignMoveTol`/`kCamForeignMinRej`）——
  与 v0.94 那个"谁排第 90 谁赢"的无条件 re-acquire 有本质区别；
- `main.cpp` 把 `InitWatchdogLogPath()` 挪到 `ArchivePreviousLog()` 之前（v1.09 写反了 ⇒ **归档一次都没跑**）。

**下一局只看三样**：`FOREIGN TAKEOVER` 后 `matChanges` 是否增长；走动时 `clipDev` 是否 > 0；
`SKSE/DynamicShaderFrameGen.20*.log` 是否出现。
"""


def file_eol(path):
    with open(path, "rb") as f:
        b = f.read()
    crlf = b.count(b"\r\n")
    return "\r\n" if crlf > (b.count(b"\n") - crlf) else "\n"


def append(path, marker, body, must_contain, apply):
    if not os.path.exists(path):
        print(f"REFUSED: missing {path}")
        return 1
    eol = file_eol(path)
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    if marker in text:
        print(f"REFUSED: marker already present in {os.path.basename(path)}")
        return 1
    add = body.replace("\n", eol)
    if not text.endswith(eol):
        add = eol + add
    out = text + add
    missing = [s for s in must_contain if s not in out]
    print(f"  {os.path.basename(path):22s} {len(raw)} -> {len(out.encode('utf-8'))} B"
          f"  eol={eol!r}  post={'PASS' if not missing else 'FAIL ' + str(missing)}")
    if missing:
        print("REFUSED, nothing written")
        return 3
    if apply:
        with open(path, "wb") as f:
            f.write(out.encode("utf-8"))
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    rc = 0
    rc |= append(LEDGER, MARK_A, CHAPTER, [
        "## 24. 第 24 章",
        "hwMax=6",
        "accepted=4",
        "FOREIGN TAKEOVER (v1.10)",
        "-195.222366",
        "matChanges",
        "kCamForeignMoveTol",
    ], apply)
    rc |= append(DAILY, MARK_B, DAILY_BODY, [
        "### 6.12",
        "hwMax=6 ask=4 accepted=4",
        "FOREIGN TAKEOVER",
        "198877d1",
    ], apply)
    if rc:
        print("one or more targets REFUSED")
        sys.exit(rc)
    print("DRY RUN ok -- re-run with --apply" if not apply else "written")
