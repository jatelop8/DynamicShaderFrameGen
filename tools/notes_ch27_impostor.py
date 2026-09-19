#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append ledger chapter 27 + daily section 6.16 for v1.13 (the impostor write).

Dry run by default; --apply writes.  Marker-guarded so a re-run refuses.
"""
import sys

LEDGER = "MFG_MASTER_NOTES.md"
DAILY = "C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md"

MARK_L = "## 27. 第 27 章"
MARK_D = "### 6.16"

LEDGER_BODY = """## 27. 第 27 章 v1.13 —— 那个「相机」根本不是相机：同一个 CB 每帧被写 20 多次

（2026-09-19 18:20 那局，v1.12 上机。证据全部是日志原文 + 源码行号。）

### 27.1 先说结论

**hook 抓的不是「引擎的相机」，而是「这个 ID3D11Buffer 最后一次被写的那个 pass」。**
那个 buffer 每渲染帧被 Map 二十多次，其中只有一次写的是相机。取「最后一个写者」
就等于取「最后一个 pass」，而世界里最后写它的那个 pass 是**一个正交全屏投影**。

### 27.2 先说 v1.12 生效了（这条是净收益，别丢）

```
[18:20:52.273] [Streamline] Reflex cap check (v1.12): 159 flip fps on a 160Hz panel = 79.5 rendered fps at 2x
[18:20:52.273] [Streamline] Reflex FLIP cap = 159 fps (6289us) - panel 160Hz, 2 flips per real frame => ~159 presented fps, ~79.5 rendered fps (v1.12: the cap is the FLIP rate)
[18:21:14.242] [XRAY] LONG FRAME 21969.0ms (capUs=6289 mult=1 menu=0)
[18:21:32.503] [XRAY] LONG FRAME 809.0ms (capUs=6289 mult=4 menu=1)
FPS probe: real=48.3 | DLSSG | cap~=193.4 (=real*4, COMPUTED not measured) | hwMax=6 ask=4 accepted=4 | cfgProvider=1
```
`capUs` 从 25641 变 6289，**真实帧率从 9.74 变成 48.3（菜单）/ 24.3（世界）**。
v1.12 的那一行除法确实修对了。

### 27.3 菜单期：捕获层是活的，而且是**真相机**

```
[CAM] pub #6724  pos=(-60.00,849.98,80.00)  move=0.0000 path=0.00  matChanges=2   ... proj00=0.149184
[CAM] pub #7116  pos=(-58.35,833.53,80.00)  move=0.3401 path=16.53 matChanges=51  ... proj00=0.149184
[CAM] pub #9852  pos=(-48.30,732.97,80.00)  move=0.2444 path=117.60 matChanges=393 ... proj00=0.149184
[FLD] #1 c8  Proj    row3=(0,0,1,0) [3][3]=0 dev=15.011 det=79.9373 mag=15.011 BAD
[FLD] #1 c16 ViewProj row3=(0,-0.991228,-0.132164,0) [3][3]=0 dev=15.011 det=-79.9373 mag=15.011 BAD
[CAM] raw #9001  pos=(-57.9856,829.8564,80.0000,0.0000) prevPos=(-58.0176,830.1761,80.0000,0.0000) devVP=15.011
[CAM] raw #11701 pos=(-49.8816,748.8160,80.0000,0.0000) prevPos=(-49.9048,749.0475,80.0000,0.0000) devVP=15.011
```
`prevPos` **紧贴 pos**（差 0.1~0.3），`path` 单调增长，`move` 0.24~0.34/帧 —— 这是真相机的签名。

把菜单的两个矩阵按「读出来的行列」重建，**`ViewProj = Proj · View` 精确成立**（手算过），
而且 `c8 Proj` 分解为 **D3D 无穷远投影**：`m22≈1`、`m23=-zn`、`m32=1`、`m33=0`，反解出 **zn=15.011**。
⇒ **字段偏移是对的**，结构体布局没问题。

### 27.4 世界期：同一个结构体里，**十个字段全是平凡矩阵**

```
[FLD] #31501 c0  View       row3=(0,0,0,1)   dev=1      det=-1      mag=1
[FLD] #31501 c8  Proj       row3=(0,0,0,1)   dev=0.111111 det=1.11111  mag=1.11111
[FLD] #31501 c16 ViewProj   row3=(0,0,0,1)   dev=1.11111  det=-1.11111 mag=1.11111
[FLD] #31501 c24 ViewProjU  row3=(0,0,0,1)   dev=1.11111  det=-1.11111 mag=1.11111
[FLD] #31501 c32 PrevVPU    全零                                                                  BAD
[FLD] #31501 c40 ProjU      det=0.9
[FLD] #31501 c48 ProjUInv   det=1.11111
[FLD] #31501 c56 ViewInv    row3=(-0,-0,-0,1) dev=1      det=-1      mag=1
[FLD] #31501 c64 ViewProjInv det=-0.9
[FLD] #31501 c72 ProjInv     det=0.9
[RAW] +0x0000 | 0 0 1 0 | 0 1 0 0
[RAW] +0x0020 | 1 0 0 0 | 0 0 0 1
[RAW] +0x0040 | 1 0 0 -0 | 0 1 0 -0
[RAW] +0x0060 | 0 0 1.111111 -0.1111111 | 0 0 0 1
[RAW] +0x0080 | 0 0 1 0 | 0 1 0 0
[RAW] +0x00a0 | 1.111111 0 0 -0.1111111 | 0 0 0 1
[RAW] +0x00c0 | 0 0 1 0 | 0 1 0 0
[RAW] +0x00e0 | 1.111111 0 0 -0.1111111 | 0 0 0 1
[RAW] +0x0100 | 0 0 0 0 | 0 0 0 0
[RAW] +0x0280 | -464.5398 349.1476 101.2857 0 | 0 0 0 0
```

把它读成矩阵：

- `c0 View = [[0,0,1,0],[0,1,0,0],[1,0,0,0],[0,0,0,1]]` —— **精确的轴交换置换阵**（det=-1）
- `c8 Proj = [[1,0,0,0],[0,1,0,0],[0,0,1.111111,-0.1111111],[0,0,0,1]]`
  反解：`m22 = zf/(zf-zn)`、`m23 = -zn·zf/(zf-zn)`，且 **`m32=0`、`m33=1` ⇒ 没有透视除法**。
  令 zf=1、zn=0.1：`z' = (z-0.1)/0.9 = 1.1111z - 0.1111` ✓ **逐位吻合**。
  ⇒ **这是一个 [0.1,1] 深度范围的正交投影（全屏 pass 的投影）。**
- `c40 ProjU = [[1,0,0,0],[0,1,0,0],[0,0,0.9,0.1],[0,0,0,1]]` = 上式的**逆**（`z'=0.9z+0.1`）

**旁证（独立、且不依赖矩阵）**：`CameraPreviousPosAdjust` 在世界里**恒为 (0,0,0,0) 整整 30 秒**，
而菜单里它紧贴 pos。写相机的那段引擎代码不可能把 prev 留成 0。

### 27.5 后果：发布流冻住

```
[CAM] pub #10085 pos=(-243.05,-415.31,118.56) move=0.0000 path=124.92 matChanges=422  lock(...)=10085/4158/3/0  proj00=0.8391 famRej=4157
[CAM] pub #16042 pos=(-381.34,208.40,187.07)  move=0.0000 path=124.92 matChanges=6171 lock(...)=16042/18667/2879/0 proj00=1    famRej=15792 ... stalePub=0 | ok
```
30 秒里 `path` 卡在 **124.92**，`pos` 只在小数点后抖动 ±0.6，
而 `matChanges` 每秒 +40 —— 因为发布序列在「真相机（~24/s，逐帧一变）」与
「恒定假相机（~500/s）」之间交替：真相机那一份被紧接着的假相机覆盖掉。

进世界那一刻的连环动作（全部同一秒）：
```
[18:21:43.686] MENU EDGE open=0 serial=1329 presentedBefore=1
[18:21:43.692] [CAM] #14242 lock RELEASED on the reset edge (was proj00=0.149184 famRej=4157)
[18:21:43.764] [MOTION] clipToPrevClip[3].w=-195.222366 (must be 1)  ... p00 cur=1.1918 prev=0.0000
[18:21:43.832] [CAM] #14289 lock RELEASED on the reset edge (was proj00=0.8391 famRej=4177)
[18:21:44.338] [CAM] #14583 FOREIGN TAKEOVER (v1.11): locked proj00=0.8391 has gone 208 publishes with an unchanged matrix while the refused family proj00=1 travelled 289.8 units - adopting pos=(-464.8,349.9,100.5)
[18:21:44.338] [CAM] #14585 same-family step break: pos=(-126.2,210.8,189.1) locked=(-464.8,349.9,100.5) dist=376.6 proj00=1 still=1/90
[18:21:44.357] [XRAY] clipGate v0.92: det3=267.144165 ... clipDev=70992.125000 finite=1
[18:21:44.369] [CAM] #14603 same-family step break: pos=(-381.4,208.6,187.6) locked=(-126.2,210.8,189.1) dist=255.2 proj00=1 still=17/90
[18:21:44.369] [CAM] #14605 same-family step break: pos=(-693.5,527.5,111.4) locked=(-381.4,208.6,187.6) dist=452.7 proj00=1 still=1/90
```
31 毫秒内 anchor 连跳 4 次、每次 255~453 单位 —— 这在游戏里不是相机，是**多个 pass 的假相机在抢同一个槽**。

### 27.6 量化：每帧 20 多次写，只有一次是相机

`arrivalsPerSec=591`，世界内 `FPS probe: real≈24` ⇒ **每渲染帧 ~22 次 Map/Unmap**。
`matChanges` 每秒 +40 ≈ `2 × 24`，正是「真相机 24/s 与恒定假相机交替」应有的计数（每次交替两变）。

### 27.7 v1.13 的改动（唯一一处行为改动）

判据（两群样本精确分离，取自同一局日志）：

| | `|CameraProj[3][2]|` | `|CameraProj[3][3]|` |
|---|---|---|
| 相机写 | **1** | **0** |
| 假相机写 | **0** | **1** |

```cpp
constexpr float kCamProjDivideMin = 0.05f;   // 有透视除法的才是相机
constexpr float kCamProjWMax = 0.05f;
constexpr std::uint64_t kCamCaptureFallbackSkips = 6000;   // ~10 s

const bool camShaped =
    (std::fabs(a_src.CameraProj.data[3][2]) >= kCamProjDivideMin) &&
    (std::fabs(a_src.CameraProj.data[3][3]) <= kCamProjWMax);
if (!camShaped) {
    ++snapNonCamera; ++snapSkipsSinceCam;
    if (snapNonCamera <= 5u) { ...一行日志，打印 row3/prevPos/pos/magVP... }
    if (snapSkipsSinceCam < kCamCaptureFallbackSkips) return false;
} else { snapSkipsSinceCam = 0; }
```

- **逃生门**：连续 6000 次都不像相机 ⇒ 判据在这台机器上不成立 ⇒ 退回「接受最后写者」（= 今天的行为）。
  **最坏情况 = 当前版本，不会更坏。**
- `[CAM] pub` 增 `cap={}/{}`（drop 数 / 连续 drop 数）。
- **锁、族指纹、release、step-break 一行未改** —— 先把输入弄干净，再看锁。

### 27.8 L30（本轮的方法论）

> **同一个槽位被多个来源共享时，「谁最后写」不是选源依据；选源必须用内容里可判定的特征。**

配套：新判据必须带**逃生门**（退化成旧行为），否则判据错了就是把「不好」换成「更糟」；
以及**先测出两群样本的分离量再写判据**（这里 1 vs 0，不是估值）。

### 27.8b 交付物

`BUILD SUCCESS` · DLL 1,340,928 B · md5 `4b34118e…`（build == 部署）· commit `9e6ac64` · tag `v1.13`。
改前存档 `src/backup-v1.13-20260919-182918/`；本局日志 `docs/runlogs/2026-09-19-1820-v1.12-world-impostor.log`
（+ `.watchdog.log`）。INI 两份 md5 `a19307d4…` 一致，六键全对：
`Provider=1 / FrameGeneration=1 / NeuralRenderingEnabled=1 / DLSSGFramesToGenerate=3 /
MFGMaxFramesOverride=3 / NRAllowWithFrameGen=1`。

### 27.9 下一局的判据

| 看到什么 | 说明什么 |
|---|---|
| `cap=` 左边 ≈ 帧率（~24/s），右边 0~30 | **修对了**：捕获层只收相机 |
| `path` 开始增长、走动时 `clipDev` 明显 >0 | 发布流是活的，重投影有内容 |
| `[CAM] NON-CAMERA write dropped (v1.13)` 有输出且 row3 是 `(0,0,0,1)` | 假相机确实存在（判据选对了） |
| `cap=` 左边 **一直是 0**、右边涨到 6000 | 世界里**没有**相机写 ⇒ 必须换源（`RE::PlayerCamera`），逃生门已自动退回旧行为 |
| 又冻结但 `cap=` 左边在涨 | **第一次能定性的复现**，这一跑就够下结论 |

"""

DAILY_BODY = """### 6.16 18:20 那局（v1.12 上机）：抓到「假相机」——同一个常量缓冲每帧被写 20 多次

**结论**：hook 取的是「最后写者」，而世界里最后写 perFrame 缓冲的不是相机，是一个
**正交全屏投影**（`m22=1.1111, m23=-0.1111` 反解出 zn=0.1/zf=1，且 `m32=0,m33=1` 无透视除法）。
菜单里同一结构体十个字段全是真相机；世界里十个字段全是平凡矩阵，`CameraPreviousPosAdjust` 恒 0。

**净收益先记下**：v1.12 生效 —— `capUs` 25641→6289，真实帧率 9.74→48.3（菜单）/24.3（世界）。

**量化**：`arrivalsPerSec=591` ÷ `real≈24` ⇒ **每渲染帧 ~22 次 Map/Unmap**；
`matChanges` +40/s = 2×24，正是「真相机 24/s 与恒定假相机交替」的计数。

**证据**（原文）：
- 菜单 `path` 0→117.60 单调涨、`prevPos` 紧贴 `pos`、`[FLD] #1 c8 Proj row3=(0,0,1,0) det=79.9373 mag=15.011`
- 世界 `[FLD] #31501` 全部平凡 + `[RAW] +0x0060 | 0 0 1.111111 -0.1111111 | 0 0 0 1`
- 世界 `path` 卡 124.92 三十秒，`pos` 只抖 ±0.6，`matChanges` 6171
- 31 ms 内四次 `same-family step break`，dist 376.6 / 255.2 / 452.7

**v1.13**：只加一道内容门 `|Proj[3][2]|>=0.05 && |Proj[3][3]|<=0.05`，
带逃生门（连续 6000 次不匹配就退回旧行为），`[CAM] pub` 增 `cap={}/{}`。
锁一行未改。DLL 1,340,928 B，md5 `4b34118e…`（build == 部署），commit `9e6ac64`，tag `v1.13`。
本局日志存档：`docs/runlogs/2026-09-19-1820-v1.12-world-impostor.log`。

**L30**：同一个槽位被多个来源共享时，「谁最后写」不是选源依据；选源必须用内容里可判定的特征，
且判据必须带逃生门（退化成旧行为）。

"""


def append(path, marker, body, extra, eol):
    raw = open(path, "rb").read()
    text = raw.decode("utf-8")
    if marker in text:
        print(f"    REFUSED, nothing written ({marker!r} already present in {path})")
        return 1
    if not text.endswith(eol) and not text.endswith("\n"):
        text += eol
    out = text + body.replace("\r\n", eol)
    for probe in extra:
        if out.count(probe) < 1:
            print(f"    REFUSED, nothing written (post-condition: {probe!r} absent)")
            return 2
    nb = out.encode("utf-8")
    # EOL guard: the file must keep its own line-ending style.  (An equality test
    # on the bare-LF COUNT is wrong for an LF-only file -- appending lines is
    # supposed to raise it. What matters is that the style does not change.)
    oc, ol = raw.count(b"\r\n"), raw.count(b"\n") - raw.count(b"\r\n")
    nc, nl = nb.count(b"\r\n"), nb.count(b"\n") - nb.count(b"\r\n")
    if (oc == 0) != (nc == 0):
        print("    REFUSED, nothing written (line-ending style flipped)")
        return 3
    if oc > 0 and (nl != ol or nc <= oc):
        print("    REFUSED, nothing written (CRLF file gained bare LF)")
        return 3
    if ol > 0 and nc != 0:
        print("    REFUSED, nothing written (LF file gained CRLF)")
        return 3
    print(f"    ok: {len(raw)} B -> {len(nb)} B   (CRLF {oc}->{nc}, bareLF {ol}->{nl})")
    return ("WRITE", path, out)


def main():
    apply = "--apply" in sys.argv
    print(f"mode: {'APPLY' if apply else 'dry run'}")
    rc = 0
    for path, marker, body, extra in [
        (LEDGER, MARK_L, LEDGER_BODY, ["27.1", "L30", "4b34118e", "cap={}/{}"]),
        (DAILY, MARK_D, DAILY_BODY, ["6.16", "L30", "4b34118e"]),
    ]:
        eol = "\r\n" if path.endswith(".md") and open(path, "rb").read().count(b"\r\n") else "\n"
        print(f"  {path}")
        r = append(path, marker, body, extra, eol)
        if isinstance(r, tuple):
            if apply:
                open(r[1], "w", encoding="utf-8", newline="").write(r[2])
                print("    written")
            else:
                print("    (dry run: not written)")
        else:
            rc |= r
    return rc


if __name__ == "__main__":
    sys.exit(main())
