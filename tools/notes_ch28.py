#!/usr/bin/env python3
"""Append ledger chapter 28 and daily 6.20 for the 22:02 run + v1.16.

Marker-guarded and style-preserving: the ledger is LF-only, the daily log is
LF-only; neither may gain a CRLF, and neither style may flip.
"""

import pathlib

LEDGER = pathlib.Path("D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md")
DAILY = pathlib.Path("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md")

LEDGER_MARK = "### 28.1 22:02 那局"
DAILY_MARK = "## 6.20 22:02 那局"

LEDGER_BODY = """## 28. 22:02 那局 + v1.16：不再推断，直接问引擎

### 28.1 22:02 那局：内容门是对的，4x 也是真的

构建 `Sep 19 2026 21:21:37`（v1.15b）。跑 53 秒：启动 22:01:48，菜单 22:02:22–22:02:37（15 s），
世界 22:02:37–22:02:41.8（**只有 4.5 s**），随后玩家退出。watchdog 尾：`frames=765 alive=1
presentAge=17ms silent=6ms`——**没有挂起、没有崩溃**，渲染循环一直是健康的。

| 项 | 实测 | 含义 |
|---|---|---|
| `DLSSG presented per real frame = 4 (status=0)` @22:02:37.524 | **4** | **4x 真的在产出**（菜单期是 1 = 不插帧，符合菜单门） |
| `real=38.25` fps | 38 | 帧率没问题 |
| `Reflex FLIP cap = 159 fps (6289us)` | 6289 | v1.12 的收益仍在 |
| `cap=2560/0` | 左涨右 0 | v1.13 内容门照常在丢弃正交写，逃生门未触发 |
| 菜单期发布流 | `pub #4495 pos=(-50.00,618.10,105.33) move=0.0562 path=54.89 frozenRep=0 stalePub=0 \\| ok` | **相机链在菜单里是活的**（path 从 0 涨到 54.89） |
| `FAM[0] proj00=0.149184 moved=169 stepSum=54.99` | 菜单期逐秒增长 | 唯一会动的族是 0.149184（加载/主菜单的慢漂） |

### 28.2 但世界段：锁在一个恒定写者上，且接管门再次死锁

世界段四条 `[CAM] acc` **逐字节相同**：

    [CAM] acc #4572/#4598/#4625/#4652 pos=(0.00,0.00,1.00) move=0.0000 path=54.99
                                        devVP=2.0001 detVP=-2.25023 magVP=2 consecJmp=0

心跳：`frozen` 与世界帧数 1:1（29/30、59/64、89/94）、`clipDev=0.000000`、`clipW=1.000000`
⇒ `clipToPrevClip = I` ⇒ 插帧退化成复制。

过程的两次释放：

    #7343 lock RELEASED on the reset edge (was proj00=0.149184 famRej=1111)
    #7390 lock RELEASED on the reset edge (was proj00=0.8391  famRej=1114)

⇒ v1.07b 的"释放后由第一个到达者重采"在世界里**采到的是停车写者**（先 0.8391，再 0.888889）。
而被拒的族 `0.8391` 位置**恒定** `(-243.0493,-415.3115,118.5582)`，`still=4..1000/90`，
`famRej 1114 → 2671`（+390/s）⇒ **v1.11 的"移动的异族才能接管"永远不成立**（停车族的位移恒 0）。
死锁第二次被确证。

### 28.3 ★ 我自己的探针是坏的（两处），上一轮那张判据表不可信

1. **族键容差 2%**：两个投影略有差异的写者被并进同一个桶，它们的到达交错 ⇒ 位置读成巨大位移。
   铁证：`FAM[1] proj00=1 moved=765 stepSum=318990`，而世界段**没有任何东西在动**（平均 417 单位/步）。
2. **MOTION 明细行只有 60 行预算**，被菜单期 0.149184 的慢漂全部吃掉 ⇒ 世界段**一条明细都没有**。

⇒ 上一轮"所有族 moved=0 ⇒ 换源"是从**坏仪器**上读出来的判据，不能作数。
**L31：自造的量表凡是带容差，就可能把两个不同样本并成一个；读数一旦不代表任何单一对象，
就不能用来做判据。**

### 28.4 参考实现（CS）逐行对照：差异**不在**钩子，在 helper

- CS `src/Globals.cpp:217-265` 的 Map/Unmap 钩子与我们**逐字相同**：同一 REL ID `524768/411384`、
  同一对槽 14/15、同样是"记下最近一次匹配的 Map 指针，在 Unmap 时拷走再置空"。
  ⇒ **"取最后一个写者"不是我们独有的缺陷，CS 也这么做。**
- CS `src/Features/Upscaling/Streamline.cpp:235-264`：`cameraRight/Up/Fwd` ← `CameraViewInverse.Transpose()`，
  `cameraPos` ← `CameraPosAdjust`，`cameraViewToClip` ← `CameraProjUnjittered.Transpose()`
  —— **这三项和我们完全一样**。
- **真正的差异**：CS 在 flat（非 VR）分支调用 **Streamline 官方 helper `recalculateCameraMatrices(slConstants)`**
  （`extern/Streamline/include/sl_matrix_helpers.h:178`），由它重算 `clipToCameraView` / `clipToPrevClip` /
  `prevClipToClip`，并**自己维护上一帧的相机位姿**（`static cameraViewToWorldPrev` / `cameraViewToClipPrev`）。
  只有 VR 分支才自己算（因为 helper 的 prev 只有单槽）。
- 该 helper 通过 `calcCameraToPrevCamera`（同文件 154 行）**先把当前相机平移到世界原点再求逆乘**，
  注释明说这样是为了避开"大平移相加导致 fp32 精度崩塌"；而我们一直用 `inv(curVP) × prevVP`
  —— **正是它警告的那件事**（18:20 世界段的 `clipToPrevClip[3].w=170.324310`、22:02 的 `-195.222366`
  大概就是这个代价）。
⇒ **下一轮候选改动：flat 路径也交给官方 helper。**

### 28.5 为什么下一步是"问引擎"而不是"再猜一族"

我们每一道门都在**从写者身上推断**哪个是相机：族指纹、步长、冻结、接管……22:02 证明这条路会走进死锁。
而引擎可以**直接问**：`RE::PlayerCamera::GetSingleton()->cameraRoot->world.translate` 是活的相机眼位
（CS `src/Hooks.cpp:711-722` 就是这么取水面反射的相机位置用的），`CameraPosAdjust` 装的是同一个量。
⇒ 落在它 `kPcMatchTol = 20` 单位内的到达者，**就是**相机写。这是可判定的（L30），不是推断。

### 28.6 v1.16 改动（+ v1.16b 安全补丁）

`tools/patch_v116_pctakeover.py`（5 处，行为 1 + 诊断 4）+ `tools/patch_v116b_pcrefuse.py`（4 处）。

1. **行为**：`AcceptCameraSnapshot` 在锁块**之前**新增 ground-truth 块。读 PlayerCamera；每个到达者算
   `pcDist`；当 `pcDist <= 20` **且锁在另一个族上** ⇒ `snapLockHave = false; snapHaveLast = false`，
   让紧接着的正常 acquire 路径接纳它并发布，锁的族随之刷新成相机族。
   - "另一个族"这一条是防抖：否则相机锁上以后每来一个到达者都会掉锁，
     而 v0.93 已实测过掉锁的代价（`#7818/#7824/#7837 RELOCK`，`path=845264`，CTD）。
2. **v1.16b**：同一参考也用来**拒绝**——`snapPcEverMatched`（参考已自证：真有到达者落在 20 单位内）
   为真、`pcDist > 20`、且族与锁不同 ⇒ `return false`。没有这一条，当相机写在前、停车写在后时，
   每帧会发布一次停车矩阵 = v0.93 的交错源流。全部以 `snapPcEverMatched` 为门：
   **参考若永不匹配，这一版与上一版行为完全一致。**
3. **诊断**：每秒一行 `[CAM] PC v1.16: read= match= adopt=sec/total best= at proj00= eye=(x,y,z)`；
   族普查键收紧到 0.01%，每条加 `arr=`、`span=(x,y,z)`、`last=`。
   `span` 一个数就能分开三种群体：`0.0000` = 停车写者；小且 `moved≈arr` = 活相机；几百 = 合并过的桶。

### 28.7 下一局判据（一次读数定案）

| 看到什么 | 结论 | 下一步 |
|---|---|---|
| `[CAM] PC` 的 `best` 掉到几单位内、`adopt` 开始增长 | 相机写**确实在这个 CB 里**，v1.16 抓住了 | 看 `path`/`clipDev` 是否活了 |
| `best` 全程几百~上千、`match=0`、`adopt=0` | **相机写根本不在这个 CB 里** | 用 PlayerCamera 的位姿**合成**相机（pos=eye，right/up/fwd 取 `cameraRoot->world.rotate`，投影取已到达的族），并接官方 helper |
| `PC TAKEOVER` 出现但 `path` 仍不涨 | 源对了、装配有问题 | 换官方 helper（28.4） |
| `best` 在几百但 `read=0` | PlayerCamera 读不到（时序/线程） | 移到 Present 侧取参考 |

**前置条件：进世界后停留 15 秒以上并真的走动。** 22:02 世界段只有 4.5 s，与 19:39 的 11.5 s、21:15 的 3.4 s 一样，
**"玩家没动"和"锁在固定相机上"在日志里同形**，这是唯一无法从数据消歧的点。

### 28.8 交付物

DLL **1,352,192 B**、md5 `b21bd0f3be23b396c1f5ec0534447188`（build == 部署）、commit `437fadc`、
tag `v1.16`、回退件 `src/backup-v1.16-20260919-221351/`（内置 DLL md5 `1178525c…` = 跑过 22:02 那局的 v1.15b）。
本局日志 `docs/runlogs/2026-09-19-2202-v1.15probe-world-no-live-family.log`。

### 28.9 L0 两遍自检

**第一遍·手脚**：8/8 锚点 `count==1`；两个补丁脚本重跑都 `REFUSED`(exit 1)；
`FrameGen.cpp` 1887 CRLF / 裸 LF 0，`FrameGen.h` 473 / 0；`BUILD SUCCESS` 无 `error C*`/`LNK`；
DLL 双份 md5 一致；新串各 1 次；两条旧串（`[CAM] MOTION fam={:.6g}`、`cen={}/{}`）**0** 次；
关键旧串（v1.13 闸门、v1.12 限速器、DLSSNR CHAINED）各 1 次。

**第二遍·脑子**：本轮我自己踩了三个坑，全被断言/后置条件挡住，**没有一个落盘**——
1. `Path.read_text()` 会做通用换行转换 ⇒ CRLF 文本变 LF，锚点全部失配；
   更危险的是 `write_text` 会把整份文件写成 LF。干跑的后置条件抓到（未落盘）。
2. 预检用 LF 锚点去数 CRLF 文件 ⇒ 计数 0。**"行尾要按文件取"这条铁律又救一次。**
3. 我断言 `frameBufferCopy = a_src;` 出现 ≥2 次，实际**只有 1 次**——是断言写错，不是代码错。
   已改成 `==1`（发布点是唯一的）。

另外更正两处上一轮的叙述：①"最后写者"并非我们独有的缺陷（CS 同款钩子，见 28.4）；
②上一轮的判据表读自坏探针（28.3）。
"""

DAILY_BODY = """## 6.20 22:02 那局：4x 是真的，相机是假的；v1.16 改成"直接问引擎"

- **这局 4x 真的在跑**：`DLSSG presented per real frame = 4 (status=0)`；`real=38.25` fps；
  `Reflex FLIP cap=6289us`；`cap=2560/0`（v1.13 门照常丢正交写，逃生门未触发）。
  watchdog `alive=1 presentAge=17ms silent=6ms`——**无挂起无崩溃**（玩家自己退出的）。
- **菜单期相机链是活的**：`pub #4495 pos=(-50.00,618.10,105.33) move=0.0562 path=54.89 frozenRep=0
  stalePub=0 | ok`；唯一会动的族 `0.149184`（`moved` 涨到 169）。
- **世界段锁死在恒定写者上**：4 条 `[CAM] acc` 逐字节相同（`pos=(0,0,1) devVP=2.0001 detVP=-2.25023
  magVP=2`），`frozen` == 世界帧数、`clipDev=0.000000`、`clipW=1.000000`、`path` 冻 54.99。
  世界入口两次释放（`was 0.149184` → `0.8391` → `0.888889`），v1.07b 采到的都是停车写者；
  被拒族 `0.8391` 位置恒定、`famRej +390/s` ⇒ **v1.11 接管门死锁第二次确证**。
- **★ 我的探针坏了（两处）**：v1.15 族键 2% 容差把两个写者并桶 ⇒ `FAM[1] moved=765 stepSum=318990`
  读数毫无意义；MOTION 的 60 行预算被菜单吃光 ⇒ 世界段零明细。**上一轮判据表作废。L31 记录在案。**
- **CS 对照（关键）**：Map/Unmap 钩子与我们逐字相同（同 REL ID、同槽位），
  `cameraRight/Up/Fwd/Pos/ViewToClip` 的来源也相同；**差异是 flat 分支调用官方
  `recalculateCameraMatrices()`**，并且该 helper 用"先把相机移到原点"的方式避开 fp32 精度崩塌
  ——而我们用的 `inv(curVP)×prevVP` 正是它警告的做法。⇒ 下一轮候选改动。
- **v1.16（+v1.16b）**：`RE::PlayerCamera::cameraRoot->world.translate` 作**地面真值**，
  落在 `kPcMatchTol=20` 单位内的到达者就是相机写：掉锁让它重采（v1.16）；参考自证后，
  远离且异族的到达者**不得**夺锁（v1.16b，防 v0.93 交错源 CTD）。全部以 `snapPcEverMatched` 为门，
  **参考不匹配则行为与上一版完全一致**。诊断：每秒 `[CAM] PC … best= adopt=`；族普查加 `span=`。
- **产物**：DLL 1,352,192 B md5 `b21bd0f3…`（build == 部署），commit `437fadc`，tag `v1.16`；
  回退件 `src/backup-v1.16-20260919-221351/`（DLL = v1.15b）；日志存 `docs/runlogs/2026-09-19-2202-*`。
- **下一局**：进世界后**停留 15 秒并走动**。`PC best` 若掉到几单位 ⇒ 抓对了；
  若恒几百且 `match=0` ⇒ 相机不在 CB 里，改用 PlayerCamera 位姿合成相机 + 官方 helper。
"""


def append(path: pathlib.Path, mark: str, body: str) -> bool:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    style = "CRLF" if crlf > bare else "LF"
    if mark in text:
        print(f"REFUSED {path.name}: marker present")
        return False
    if style == "LF" and crlf:
        print(f"WARNING {path.name}: has {crlf} CRLF lines, refusing to mix")
        return False
    out = text + "\n" + body
    data = out.encode("utf-8")
    crlf2 = data.count(b"\r\n")
    bare2 = data.count(b"\n") - crlf2
    if style == "LF" and crlf2:
        print(f"REFUSED {path.name}: would add CRLF to an LF file")
        return False
    path.write_bytes(data)
    print(f"appended {path.name}: {len(raw)} -> {len(data)} bytes, style {style}, bareLF {bare2}")
    return True


ok = append(LEDGER, LEDGER_MARK, LEDGER_BODY)
ok &= append(DAILY, DAILY_MARK, DAILY_BODY)
raise SystemExit(0 if ok else 1)
