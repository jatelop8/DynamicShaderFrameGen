#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append ledger ch29 + daily 6.22 for the 22:22 run and v1.17.

Both files are LF-only; the script refuses to write if that is not true, and
refuses to append twice (marker guard).
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "MFG_MASTER_NOTES.md"
DAILY = pathlib.Path(
    "C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md"
)

CH29_MARK = "## 29. 第 29 章"
CH29 = """
## 29. 第 29 章　22:22 那局 + v1.17：**方向是反的——整整两天锁的是菜单相机**

### 29.1 那局的骨架（构建 Sep 19 2026 22:15:25 = v1.16）

| 时刻 | 事件 |
|---|---|
| 22:22:25 | 进程起 |
| 22:22:33 | Map/Unmap 钩子装好 |
| **22:22:56.967** | `LONG FRAME 20582.9ms` —— 载入的单帧卡了 20.6 秒 |
| 22:22:56.967 | `MENU EDGE open=1 serial=2` —— 主菜单出现 |
| 22:22:57→22:23:12 | 菜单期，668 帧，约 15 秒 |
| **22:23:12.473** | `MENU EDGE open=0 serial=670` —— 进世界 |
| 22:23:14.665 | 最后一行日志，**世界段只有 2.2 秒 / 34 帧** |

无崩溃转储，无 error/exception；最后 80 ms 还有 5 行正常帧日志
（`Reflex cap check` / `clipGate v0.92` 每秒两轮）⇒ **游戏到最后一刻都在正常渲染，
是用户主动退出的，不是崩溃。**

`mapHit(perFrame/unmap)=8303/8303` —— 钩子配对，没有丢 Unmap。

### 29.2 ★★★★★ 真值判据给出了**两个方向相反的判决**

v1.16 插的探针每秒打一行：

```
[CAM] PC v1.16: read=… match=… adopt=… best=… at proj00=… eye=(…)
```

| 时刻 | read | match | best | proj00 | eye |
|---|---|---|---|---|---|
| 22:23:02–08 | 74→392 | **0** | **603.99 → 835.51** | 0.149184 | (0.00,0.00,128.00) |
| 22:23:09 | 384 | 0 | 797.67 | 0.149184 | **(-243.05,-415.31,118.62)** |
| **22:23:10** | 366 | **154** | **0.00** | **0.8391** | (-243.05,-415.31,118.56) |
| 22:23:11–14 | 408–493 | 380–456 | **0.00** | **0.8391** | 同上 |

`best=0.00` 的含义：**`RE::PlayerCamera::cameraRoot->world.translate`
与那个到达者的 `CameraPosAdjust` 相距 0.00 单位**，而且是一秒 397 次。

三条 `PC TAKEOVER` 原文（第一次）：

```
[CAM] #5842 PC TAKEOVER (v1.16): this arrival is 0.00 units from the live player
camera pos=(-243.049,-415.315,118.624) pc=(-243.049,-415.315,118.624) proj00=0.8391
- dropping the lock so it re-acquires on this arrival
```

**⇒ `proj00=0.8391` 就是玩家相机。**
**⇒ `proj00=0.149184`（被真值判为 604～836 单位远）不是玩家相机。**

### 29.3 ★★★★★ 这是整个案件的根因，而且方向与 v1.00–v1.15 的结论**完全相反**

两天来我一直把 `0.149184` 当作「世界相机」、把 `0.8391` 当作「停着的 3D 菜单相机」。
真值说反了。逐条对照：

| 读数 | 我此前的解释 | 真值判决 |
|---|---|---|
| `0.8391` @ `(-243.0493,-415.3115,118.5582)` | 「场景固定的菜单机位」 | **玩家相机**（距真值 0.00，397 次/秒）|
| `0.149184` @ `(-50, 600→848, 65→69)` | 「世界相机 / 跟着玩家」 | 主菜单相机（离玩家 604～836 单位）|
| `0.8391` 的「不动」 | 「停着的写者」 | **玩家站着不动** |

`FrameGen.h` 里 v1.10 那条注释白纸黑字写着
**"The real camera (proj00=1) then walked (-125.7,210.8,188.4) -> (255.0,804.7,-94.4)"**
—— 那也是**推断**出来的，不是测出来的。已在该处插入 `CORRECTION (v1.17, 22:22 run)` 标注。

**★ 教训（写进 L32）：`proj00=1` 那个桶根本不是相机。**
22:22 局 `FAM[1] proj00=1 arr=500 moved=500 stepSum=542149.75 span=(974.79,901.49,86.68)
last=(-126.89,210.43,189.29)` —— 四秒内 `last` 只挪了 1.9 单位，`stepSum` 却累积 54 万。
⇒ 一个桶里至少装了**两个相距约 1000 单位的写者**，互相跳。
`kSnapFamKeyTol=1e-4` 对 `proj00 == 1.0` 是**精确相等** ⇒ 所有单位投影都并桶。
这个桶**能满足 v1.11 的 `kCamForeignMoveTol(200)`**，而它连相机都不是。
v1.00g 的同族 step-break 会**因为它的跳变**把锚交给它 —— v1.17 就是来堵这个洞的。

### 29.4 4x 与 DLSS5 的现场读数（都还在）

```
[FrameGen] FPS probe: real=25.9 | DLSSG | cap~=103.4 (=real*4, COMPUTED not measured)
           | hwMax=6 ask=4 accepted=4 | cfgProvider=1
[Streamline] Reflex cap check (v1.12): 159 flip fps on a 160Hz panel = 39.8 rendered fps at 4x
[XRAY] presented all=0/630/0/0/54/0/0/0   world=0/12/0/0/54/0/0/0   ⇒ 桶 4 有 54 帧
[FrameGen] DLSSNR: color=true engineDepthSRV=true engineMvec=true inputs=true
           frames=719 status=initialized
```
`real=25.9ms`（25.9 fps 渲染）× 4 ≈ 103 fps 呈现。**v1.12 的限速收益与 DLSS5 注册都还在。**

### 29.5 ★ 这一局**不能**判定冻结是否修好，原因是可测量的

世界段 4 条 `[CAM] acc` **逐字节相同**：

```
[CAM] acc #6093 pos=(-243.05,-415.31,118.56) move=0.0000 path=71.82
       devVP=15.0006 detVP=-2.52504 magVP=15.0006 consecJmp=0
```

心跳：`frozen=30/34`、`clipDev=0.000061`、`clipW=1.000000`、`det3=1.000000` ⇒ `clipToPrevClip = I`。

**但这一次 `I` 是正确的** —— 相机真值 `eye=(-243.05,-415.31,118.56)` 在
22:23:10→14.5 的五次采样里字节不变。相机没动，`clipToPrevClip` 就该是单位阵。

唯一的「动」是 `FAM[2] span=(0.0005,0.0036,0.0712)` —— z 方向 7 厘米，即**待机呼吸**。
⇒ **玩家站着没动，或者动不了。这两件事在日志里是同一个形状。**

### 29.6 ★ L32：我引入的 v1.16b 分支是死代码，是日志抓出来的

v1.16b 的拒收是这么挂的：

```cpp
if (pc && pc->cameraRoot) {
    ... 匹配 / 接管 ...
} else if (snapPcEverMatched && snapLockHave && <异族>) {   // ← 挂在 else 上
    ++snapPcReject; return false;
}
```

`else if` 挂在 **"没有 PlayerCamera"** 那条臂上 ⇒ **只有参考不可用时才会执行**，
而参考一直是可用的。证据：整局 `PC REFUSE` 计数 = **0**（`grep -ac "PC REFUSE"` = 0，
`rej` 在 v1.16 的 dump 里没打印，但 `snapPcReject` 从未增长）。

它还与下面 `!sameFamily` 那条**无条件 `return false`** 重复 ⇒ 就算挂对了也是多余。
**v1.17 把它删了**，改到唯一还有洞的地方（见 29.7）。

★ **教训：写 `else if` 之前先问「这个 else 属于哪个 if」。**
一个分支挂错父节点，行为 = 不存在，而它**看起来**像在保护什么。

### 29.7 v1.17 的改动（唯一行为改动：一处守卫）

真实漏洞有两条路，都通到「把锚交给非相机写者」：

1. **空槽获取** `if (!snapLockHave)` —— 22:02 局就是在 reset edge 之后由它拿到 `0.149184`；
2. **v1.00g 同族 step-break** —— 任何同族、步长超 `kCamStepTol` 的到达者都能重新拿锚，
   而 `proj00=1` 那个装着两个写者的桶正好满足（29.3）。

v1.17 在 acquire 之前放**一道守卫**，同时盖住三条路（空槽获取 / 异族下坠 / 同族 step-break）：

```cpp
bool pcIsThis = false;                      // 这一个到达者就是活相机
const bool pcKnown = snapPcRefSeen > 0u;    // 参考在最近 kPcRefHoldSec 秒内匹配过

// ... 真值块内，命中时：
snapPcRefSeen = kPcRefHoldSec;              // = 2
pcIsThis = true;

// ... accept 路径最前：
if (pcKnown && !pcIsThis) { ++snapPcReject; return false; }
```

**`snapPcRefSeen` 是秒级闩锁**：每次命中置 2，`[CAM] PC` 每秒减 1。
⇒ 参考一旦不再匹配，闩锁 2 秒内失效，**退回 v1.17 之前的行为** ⇒ **这道门不可能把锁锁死。**
（`return false` 不碰 `snapLastPos`/`snapHaveLast`，所以下一帧相机到达时流是连续的。）

**另加运动见证 `eyeD`**：`[CAM] PC` 末尾打印活相机在过去一秒走了多少单位，并给出判决词：

```
eyeD=… PC_STILL - the live camera did not move: an unchanged picture is CORRECT here
eyeD=… PC_MOVING - the live camera is walking
```

**这是为了让下一局无法再含糊** —— 「玩家没动」与「锁在停着的写者上」从此可分。

### 29.8 产物与回退

| 项 | 值 |
|---|---|
| DLL | 1,353,728 B，md5 `91493b4d2c5d7eaf89761e1b1f01eb3d`（build == 部署）|
| 源码 | `FrameGen.cpp` 95,713 B / 1939 CRLF / 裸 LF 0；`FrameGen.h` 27,564 B / 498 / 0 |
| commit / tag | `c36c693` / `v1.17` |
| 补丁脚本 | `tools/patch_v117_pcauthority.py`（9 条锚点全 count==1，干跑默认，重跑 REFUSED exit 1）|
| 回退 v1.16 | `src/backup-v1.17-20260919-222922/`（`built_DLL.bin` = `b21bd0f3…`）|
| 本局日志 | `docs/runlogs/2026-09-19-2222-v1.16-pc-takeover-works-world-2s-static.log` |

### 29.9 ★ 下一局的判据表（全部换成可判定的）

**前置条件（不满足就是白跑）：进世界后停留 ≥15 秒，并且真的走路。**

| 看到 | 结论 | 下一步 |
|---|---|---|
| `PC_MOVING` + `eyeD` 明显 > 0，且 `path`/`matChanges` 同步增长 | **源与装配都对，冻结已修** | 进下一步：DLSS5 上屏验证、20/30 系 |
| `PC_MOVING` 但 `path` 仍冻（`move=0.0000`） | 源对了、**装配**错了 | 换官方 `recalculateCameraMatrices()` / `calcCameraToPrevCamera()`（原点平移消 fp32 精度）|
| `PC_STILL`（`eyeD≈0`） | **这一局作废**，不是 bug | 重跑，必须走动 |
| `rej` 暴涨且 `ref` 长期为 0 | 参考不可用 ⇒ 闩锁失效、退回旧行为 | 看 `best=` 是否恒几百 ⇒ 相机不在 CB 里，改用 PlayerCamera 位姿自建 |

### 29.10 仍未证 / 未做的事（别假装做了）

- **冻结是否修好**：**未证**。22:22 局相机没动，无法判定。
- **DLSS5 输出上屏**：`status=initialized frames=719` 只证**在跑**，**未证上屏**。
- **RTX 20/30**：`grep -i xess` = 0，一行未写。
- **`CameraProj[0][0]` 与 `CameraProjUnjittered[0][0]` 互为倒数**（`1.1918`↔`0.8391`、
  `6.70312`↔`0.149184`、`1`↔`1`）：**仍未解释**。抖动只改 `[0][0]/[1][1]` 千分之几，
  不可能产生倒数关系 ⇒ 同一结构体里两条链取了两台不同相机的矩阵，或字段偏移是错的。
  它**不影响**族键（同族内两个值都自洽），但是个潜在雷。**先做成探针再改。**
"""

D622_MARK = "## 6.22"
D622 = """
## 6.22 22:22 那局（v1.16 上机）+ v1.17：**方向是反的，两天锁的是菜单相机**

- **真值判决（决定性）**：`[CAM] PC v1.16` 打出
  `match=154/397/456 best=0.00 at proj00=0.8391 eye=(-243.05,-415.31,118.56)`，
  而菜单期是 `match=0 best=603.99→835.51 at proj00=0.149184`。
  三条 `PC TAKEOVER ... 0.00 units from the live player camera ... proj00=0.8391`。
  ⇒ **`0.8391` 是玩家相机，`0.149184` 不是。** v1.00–v1.15 两天把两者搞反了。
- **我此前的判据表整体作废**：`0.8391` 的「不动」是**玩家站着不动**，不是「停着的写者」。
  `FrameGen.h` v1.10 注释「真正的相机是 `proj00=1`」也是推断，已插 `CORRECTION (v1.17, 22:22 run)`。
- **`proj00=1` 那个桶不是相机**：`span=(974.79,901.49,86.68) stepSum=542149.75` 而 `last` 4 秒只挪 1.9
  ⇒ 至少两个相距 ~1000 单位的写者并桶（`proj00==1.0` 精确相等，容差形同虚设）
  ⇒ 它能满足 v1.11 的 `kCamForeignMoveTol(200)`。记为 L32。
- **★ 我引入的 v1.16b 分支是死代码**：`else if` 挂在「没有 PlayerCamera」那条臂上 ⇒ 只在参考不可用时执行，
  `snapPcReject` 整局为 0；且与 `!sameFamily` 的无条件拒收重复。**v1.17 删掉它。**
- **v1.17 唯一行为改动**：acquire 前加一道守卫 `if (pcKnown && !pcIsThis) return false;`，
  同时盖住空槽获取 / 异族下坠 / v1.00g 同族 step-break 三条路。
  `snapPcRefSeen` 是**秒级闩锁**（命中置 2，每秒减 1）⇒ 参考不再匹配就退回旧行为，**门锁不死**。
- **新增运动见证 `eyeD`** + 判决词 `PC_STILL` / `PC_MOVING` ⇒ 「玩家没动」与「锁在停着的写者上」从此可分。
- **4x 与 DLSS5 都还在**：`real=25.9` fps、`hwMax=6 ask=4 accepted=4`、
  `presented world` 桶 4 有 54 帧、`DLSSNR status=initialized frames=719 inputs=true`。
- **这一局不能判定冻结**：世界段只有 **2.2 秒 / 34 帧**，`[CAM] acc` 四条逐字节相同，
  `eye` 五次采样字节不变，唯一运动是 `FAM[2] span z=0.0712`（待机呼吸）。
  ⇒ `clipToPrevClip = I` **这一次是正确的**（相机真值确实没动）。
- **产物**：DLL 1,353,728 B md5 `91493b4d2c5d7eaf89761e1b1f01eb3d`（build == 部署），
  commit `c36c693`，tag `v1.17`；回退件 `src/backup-v1.17-20260919-222922/`（= v1.16）；
  日志 `docs/runlogs/2026-09-19-2222-v1.16-pc-takeover-works-world-2s-static.log`。
- **下一局判据（先看 `PC_STILL`/`PC_MOVING`）**：
  `PC_MOVING` + `path` 增长 ⇒ 源与装配都对，冻结已修；
  `PC_MOVING` + `path` 仍冻 ⇒ 源对、装配错 ⇒ 换官方 `recalculateCameraMatrices()`；
  `PC_STILL` ⇒ 这一局作废，必须走动重跑。
- **前置条件：进世界后停留 ≥15 秒，并且真的走路。** 22:22 只有 2.2 秒且没动。
"""


def append(path, mark, text):
    b = path.read_bytes()
    if b"\r\n" in b:
        print("REFUSED: %s is not LF-only" % path.name)
        return 1
    if mark.encode("utf-8") in b:
        print("SKIP (already appended): %s" % mark)
        return 0
    out = b + text.encode("utf-8")
    path.write_bytes(out)
    print("appended %d bytes to %s (now %d)" % (len(out) - len(b), path.name, len(out)))
    return 0


rc = append(LEDGER, CH29_MARK, CH29)
rc |= append(DAILY, D622_MARK, D622)
sys.exit(rc)
