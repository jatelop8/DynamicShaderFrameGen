#!/usr/bin/env python3
"""Append ledger 27.12 and daily 6.19 for the 21:15 run (v1.14probe on machine)."""

import pathlib

LEDGER = pathlib.Path(r"D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md")
DAILY = pathlib.Path(r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md")

L_MARK = "### 27.12 21:15 那局（v1.14probe 上机）"
D_MARK = "## 6.19 21:15 那局"

LEDGER_BODY = """### 27.12 21:15 那局（v1.14probe 上机）：探针先把自己测出了缺陷

日志 `docs/runlogs/2026-09-19-2115-v1.14probe-static-refused-family.log`（build `Sep 19 2026 19:45:58`
= v1.14probe）。整局 48 秒，**世界段只有 3.4 秒**（`MENU EDGE open=0` 在 `21:15:09.552`，
日志止于 `21:15:12.917`）。watchdog 全程 `alive=1`、`presentAge=46ms` ⇒ **不是崩溃，是正常退出**。

#### 27.12.1 一条正面结论：v1.13 的闸门在世界段一次都没开火

`cap=2296/0` —— **右边恒 0**（一次没丢），逃生门（6000）没触发。世界段的每一个到达在 v1.13 的
内容判据眼里**都是相机长相**。**问题不在内容门。**

#### 27.12.2 ★ 头号发现：v1.14 的 `cen` 探针有设计缺陷，这局的读数作废

`cen` 数的不是「不同的位置」，而是「与**最初见到的那 8 个**位置相差 > 1 单位」的到达次数 ——
因为 `kSnapCensusMax = 8` 的表**满了就不再写入、也不淘汰**，而 `++snapCensusNew` 照样执行。

铁证在日志里：

```
[CAM] WRITER #9  NEW pos=(-49.995,892.661,95.364) prevPos=(-49.996,893.077,95.400) arr#3645
[CAM] WRITER #10 NEW pos=(-49.995,892.661,95.364) prevPos=(-49.996,893.077,95.400) arr#3648
```

`#9` 与 `#10` 的 `pos` 与 `prevPos` **逐位相同**却都被判为 NEW —— 表里装的是更早的 8 个，
`#9` 自己没进表（满了），所以 `#10` 只能与那 8 个旧值比较。

⇒ **一个停着的写者也能让 `cen` 无限增长。`cen=5077/8` 不能读成「有 5077 个在动的位置」。**
**这局回答不了 v1.14 想问的问题，而错不在日志，在探针。**

**L31：任何「我见过几个不同的 X」计数器，必须先定义「X 的表满了怎么办」。**
不限制容量的「新值计数」把**从未见过**和**在变化**混为一谈 —— 与 L28（用会被故障重置的计数器做门）
是同一族错误的两端：一个是门被重置，一个是表被撑爆。

#### 27.12.3 世界段的实测（全部是本节的新读数）

| 量 | 世界段实测 | 读法 |
|---|---|---|
| 发布的位置 | `pos=(0.00,0.00,1.00)` | 不是相机位置 |
| `path` / `move` | `82.39` 冻住 / `0.0000` | 发布流静止 |
| `stalePub` | `0 → 80`，每秒 +26 | 连续 80 次发布的矩阵逐字节相同 |
| 锁定族 | `proj00=0.888889` | 进世界后换上的 |
| 被拒族 | `proj00=0.8391`，`pos=(-243.0,-415.3,118.6)` | 菜单相机，**位置恒定** |
| `famRej` / `hold` | 各每秒 +390 | 几乎每个到达都被族门拒 |
| `arrivalsPerSec` | `620` | 与 19:39 局一致 |

#### 27.12.4 ★ 死锁确证：接管门的**两个**条件同时不满足

v1.11 接管门的条件（`FrameGen.cpp:1143`）：

```cpp
if (snapPubStale >= kCamPubStaleTol && snapForeignMove >= kCamForeignMoveTol)
```

| 条件 | 阈值 | 世界段实测 | 结论 |
|---|---|---|---|
| `snapPubStale` | `kCamPubStaleTol = 200` | `80`，每秒 +26 | 需 **7.7 秒**，世界段只 3.4 秒 |
| `snapForeignMove` | `kCamForeignMoveTol = 200` | **恒 0** | 被拒族位置恒定 ⇒ `fStep = 0` ⇒ 永不累计 |

⇒ **第二个条件是结构性的**：`snapForeignMove` 的累计（`FrameGen.cpp:1127-1139`）只在
「被拒族自己**在走**」时才增长。世界里被拒的是**停着的菜单相机**，所以它永远不会满足。
而且这个死锁是**安全的**（不会让菜单相机夺流）—— 这就是它一直没被发现的原因。

#### 27.12.5 锁在 124 ms 内被释放两次

```
[21:15:09.557] lock RELEASED on the reset edge (was proj00=0.149184 famRej=1095)
[21:15:09.681] lock RELEASED on the reset edge (was proj00=0.888889 famRej=1122)
```

进世界后 124 ms 内两次「重置边缘释放」，每次都由**释放后的第一个到达者**接管 ⇒ 两次都撞上
`0.888889` 族。**「释放后第一个到达」是一个没有准入检查的选择规则** —— 记在这里，本局不改。

#### 27.12.6 一条排除项：`non-affine w=0 ACCEPTED (v0.89)` 不是根因

```
[21:15:09.425] [CAM] #7148 non-affine w=0 ACCEPTED (v0.89)
  row3=(-0.00391655,0.999991,0.0015,0) det3=-2.52504 pos=(-243.0,-415.3,118.6)
```

回代码（`FrameGen.cpp:842-857`）：它打印的是 `CameraViewProjUnjittered`（**不是** `CameraProj`），
块尾是 `// NO return false` —— **只是计数器与日志，不改变任何控制流**；而 v1.13 的闸门查
`CameraProj.data[3][2]/[3][3]`（不同字段、不同条件）。**排除。**

#### 27.12.7 v1.15 的改动（纯诊断，零行为改动）

`tools/patch_v115_fammotionprobe.py` + `tools/patch_v115b_famtable.py`：

1. **删掉 v1.14 的 census**，换成**按族测位移**：16 个族槽，每槽记 `(proj00, lastPos, moved, stepSum)`，
   比较**相邻两次到达**的步长，`> kCamMoveEps(0.05)` 才计一次「在动」。
2. 每秒一条 `[CAM] FAM[n] proj00=… moved=… stepSum=…`。
3. `family rejected` 行：`pos` 精度 `{:.1f}` → `{:.4f}`，并加 `prevPos` 与 `row3` ——
   **1 位小数下「停着」和「在滑」看不出区别**，这正是 27.12.3 那条读不准的原因。
4. `[CAM] MOTION fam=… step=…` 打印前 60 次真实位移。
5. 族表满时**打印一次告警**（v1.15b），不再静默丢弃 —— 被丢的那个族很可能就是活相机。

#### 27.12.8 下一局的判据（一次读数定案）

| `[CAM] FAM` 读数 | 结论 | 修法 |
|---|---|---|
| 有族的 `moved` **持续增长** | 活相机**正在到达**这个 hook | 修**接受规则**（族锁 / 接管门），不改源 |
| 所有族 `moved=0` | 到达这个 hook 的**没有活相机** | 改**源**：`RE::PlayerCamera` |
| `[CAM] MOTION` 一行都没有 | 同上，更硬 | 同上 |
| `[CAM] FAM table full` 出现 | 有族没被统计 | 提高 `kSnapFamMax` |

**前置条件（不满足就是又白跑一局）：进世界后停留 15 秒以上，并且真的走动。**
19:39 与 21:15 两局的世界段分别只有 11.5 秒与 3.4 秒；`stalePub` 需要 7.7 秒才够阈值。

#### 27.12.9 交付物

DLL **1,349,120 B**、md5 `1178525c…`（build == 部署）；commit `8e28f05`、tag `v1.15probe`；
回退件 `src/backup-v1.15-20260919-211959/`（内含 **v1.14probe** 的 `built_DLL.bin`，md5 `39a41225…`）；
本局日志存 `docs/runlogs/2026-09-19-2115-*`。
"""

DAILY_BODY = """## 6.19 21:15 那局（v1.14probe）：探针自己先被测出缺陷

- **局面**：48 秒一局，**世界段只 3.4 秒**（`open=0` 在 `21:15:09.552`，日志止于 `21:15:12.917`）；
  watchdog `alive=1 / presentAge=46ms` ⇒ **正常退出，不是崩溃**。
- **v1.13 闸门在世界段一次没开火**：`cap=2296/0`（右边恒 0），逃生门未触发 ⇒ 问题不在内容门。
- **★ 头号发现：v1.14 的 `cen` 探针有缺陷，这局读数作废。** `kSnapCensusMax=8` 的表满了不淘汰，
  `++snapCensusNew` 照样加 ⇒ 它数的是「与最初 8 个位置不同」而非「在动」。
  铁证：`WRITER #9` 与 `#10` 的 `pos`/`prevPos` **逐位相同**却都记为 NEW。
  **⇒ 停着的写者也能让它无限增长。**
- **L31**：任何「我见过几个不同的 X」计数器，必须先定义「X 的表满了怎么办」。
  与 L28 同族：一个是门被故障重置，一个是表被撑爆。
- **世界段实测**：发布 `pos=(0.00,0.00,1.00)`、`path=82.39` 冻住、`move=0.0000`、`stalePub=80`（每秒 +26）、
  锁定族 `proj00=0.888889`、被拒族 `proj00=0.8391` 且 `pos=(-243.0,-415.3,118.6)` **恒定**、
  `famRej`/`hold` 各每秒 +390、`arrivalsPerSec=620`。
- **★ 接管门死锁确证**（`FrameGen.cpp:1143`）：`snapPubStale>=200` 需 7.7 秒（世界段只到 80）；
  `snapForeignMove>=200` **恒 0**，因为被拒族位置恒定 ⇒ `fStep=0`。**两个条件同时不满足，且第二个是结构性的。**
  这个死锁是**安全的**（不会让菜单相机夺流），所以一直没暴露。
- **锁在 124 ms 内被释放两次**（09.557 释放 0.149184、09.681 释放 0.888889），每次由「释放后第一个到达者」接管
  ⇒ 那个选择规则没有准入检查。本局不改，先记下。
- **排除**：`non-affine w=0 ACCEPTED (v0.89)` 回代码确认只是计数器 + 日志（`// NO return false`），
  且查的是 `CameraViewProjUnjittered` 而非 `CameraProj` ⇒ **不是根因**。
- **v1.15（纯诊断，零行为改动）**：删掉旧 census，改成**按族测相邻步长**（16 族槽、`kCamMoveEps=0.05`），
  每秒一条 `[CAM] FAM[n] …moved=…`；`family rejected` 的 `pos` 由 1 位小数改 4 位并加 `prevPos`/`row3`；
  族表满时打印告警而不是静默丢弃。
- **下一步判据**：有族 `moved` 持续增长 ⇒ 活相机在到达 ⇒ 修**接受规则**；所有族 `moved=0` ⇒ 改**源**
  （`RE::PlayerCamera`）。
- **前置条件**：进世界后**停留 15 秒以上并真的走动**（19:39 与 21:15 的世界段只有 11.5 秒 / 3.4 秒）。
- **产物**：DLL 1,349,120 B、md5 `1178525c…`（build == 部署）、commit `8e28f05`、tag `v1.15probe`；
  回退件 `src/backup-v1.15-20260919-211959/`（内含 v1.14probe 的 DLL，md5 `39a41225…`）。
"""


def append(path, marker, body):
    raw = path.read_bytes()
    if marker in raw.decode("utf-8"):
        print(f"REFUSED {path.name}: marker present")
        return False
    out = raw + body.encode("utf-8") + b"\n"
    path.write_bytes(out)
    crlf = out.count(b"\r\n")
    bare = out.count(b"\n") - crlf
    print(f"appended {path.name}: {len(raw)} -> {len(out)} bytes, CRLF {crlf} bareLF {bare}")
    return True


append(LEDGER, L_MARK, LEDGER_BODY)
append(DAILY, D_MARK, DAILY_BODY)
