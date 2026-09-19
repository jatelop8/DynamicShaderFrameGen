
---

# 35. v1.23 —— 像素探针从来没采到一个样本；零矩阵被当成合法 clipToPrevClip

日志：`docs/runlogs/2026-09-20-0058-v1.22-loadscreen-freeze.log`（00:58:00.284 → 00:58:54.206，54 s，
v1.22 build `Sep 20 2026 00:52:35`）。用户原话：
**「这次游戏都没进去，直接在加载界面就卡死闪烁了」**。

## 35.1 这一局到底发生了什么（时间线全部取自日志原文）

| 时刻 | 证据 | 含义 |
|---|---|---|
| 00:58:14.743–14.810 | `D3D12 FG swapchain created (3840x2160)`、`interop ready`、`[PIXEL] probe armed` | 装置就位 |
| 00:58:35.782 | `MENU EDGE open=1 serial=2`、`paused=1 ld=1 fade=1`、`hrs=0.0`、`eye=(0,0,0)` | 闸门按在**第 2 帧** |
| 00:58:35.783 | `[MFG] probe RUNS while the menu guard skips DLSS-G: step advertised=4x accepted=4x` | 阶梯在跑，但 `SetDLSSGOptions` 被跳 |
| 00:58:37.772 | `FPS probe: real=45.7 … ask=4 accepted=4` | 4x 已被运行时接受 |
| 00:58:41.753–46.789 | `proj00=0.149184 eye=(0,0,128)`、`hrs=32.0`、`plr=(2048,2048,0)` | **加载期空相机**（既有的加载指纹） |
| 00:58:44.761 | `plr=(-250.3,-360.4,0.1) plrD=3329.08`、`hrs=12.31110` | 玩家被传送到世界坐标 |
| 00:58:48.150 | `MENU EDGE open=0 serial=566` ⇒ `blocked=564 unblocked=1` | 闸门放开（世界入口） |
| 00:58:48.807 | `paused=0 ld=0 best=0.00 proj00=0.8391 eyeD=0.07 hrsD=0.003136` | **世界真的进去了** |
| 00:58:48.641 / 49.694 / 53.959 | `DLSSG presented per real frame = 4` | 4x 上屏 |
| 00:58:49–53 | 看门狗逐秒 `ratio = 4.00`、`dsync=0`、`presentAge 0–18 ms` | 呈现链路**每一项都健康** |
| 00:58:54.206 | 最后一行；**无关闭序列**；看门狗 `alive=1` | 被强杀/硬挂 |

**加载耗时 13.1 秒，与上一局（v1.21，00:31）的 12.3 秒同量级** ⇒ v1.22 没有让加载变慢。

**A≠B：两局逐项对照**（指纹计数）

| 指纹 | v1.21（00:31） | v1.22（00:58） |
|---|---|---|
| `stall governor` | 2 | 2（最大 346 ms → **822 ms**）|
| `flicker cause` / `USELESS` | 3 | 1 |
| `MOTION` | 1 | 1 |
| `non-affine` | 20 | 21 |
| `presented per real frame = 4` | 1 | 3 |
| `presented per real frame = 1` | 10 | 9 |
| `debug CHECK` / `probe RUNS while` | 1 / 1 | 1 / 1 |
| **`second thread PERSISTENTLY`** | **0** | **6** |
| **`[PIXEL]`** | n/a | **1（只有 armed，0 个样本）** |

⇒ **v1.22 在可观测行为上几乎没有改变任何东西。** 用户感到"这次更糟"，但日志是同一种局：
加载 → 进世界 → 4x 生效 → 5 秒后被杀。**唯一新增的两条：探针没出数据，以及那条被我自己的阈值误报的 verdict。**

★ 用户说"没进去"，日志说"进去了"（`paused=0 ld=0`、真玩家相机 `best=0.00 proj00=0.8391`、
`hrsD≈0.0057`＝timescale 20）。两者可以同时为真：**世界在跑，屏幕没显示它。** 这正是 L38。

## 35.2 探针是死的 —— 这是我 v1.22 的 bug，不是环境的

```
[PIXEL] probe armed: src=3840x2160 fmt=28 block=64x64 at (1888,1048)   00:58:14.810
[PIXEL] <没有下一行>                                        00:58:14.811 … 00:58:54.206
```

**39 秒、0 个样本。** 根因在 v1.22 的代码里：`CopySubresourceRegion` 与 `Map` 在**同一次调用**里，
所以 `Map` 永远在问一张 GPU 还没写完的 staging 纹理 ⇒ 恒返回
`DXGI_ERROR_WAS_STILL_DRAWING`；而那条分支还写了 `pixelProbeLastMs = 0`，
**把 1 Hz 节流给废掉了** ⇒ 重试发生在**每一帧**。两个后果：

1. 唯一能回答"画面到底动没动"的仪器**一个数据点都没产出** —— 而这一局恰恰需要它；
2. **它把一次跨 API 拷贝塞进了每一帧**（从 D3D12 拥有的共享后备缓冲拷到 D3D11 staging）。
   这是 v1.22 里**唯一**改动渲染热路径的东西。最大帧时间从 346 ms 涨到 **822 ms**。

**★ 诚实边界**：822 ms 这个数字**不能**证明是探针造成的（`stall governor` 在 v1.21 也触发过 2 次）。
它被移除的理由是**它是缺陷**，不是因为已证它是成因。下一局如果加载顺了，那条因果仍只是**嫌疑**，
要另设对照才能定案。

修法：**两相采样** —— 这一秒收割"上一秒发出的拷贝"（有整整一秒落地），再发下一次拷贝；
取不到样本就**丢弃并计数**，绝不在同一秒里重试。

## 35.3 零矩阵被当成合法的 clipToPrevClip（真缺陷，已证）

同一条日志，加载→世界的**交界处**：

```
[W] [MOTION] clipToPrevClip[3].w=-68.073540 (must be 1) - the inverse and the previous
    matrix came from different cameras … v1.08 PROBE: p00 cur=6.7031 prev=0.0000 |
    p23 cur=-15.010994 prev=0.000000 | mag invSrc=68.54 prevSrc=15.01
[FLD] #1 c32 PrevVPU row3=(0,0,0,0) [3][3]=0 dev=1 det=0 mag=0 BAD
```

`prevForReproj` 是**零矩阵** ⇒ `inv(cur) × 0 = 0`。而代码里唯一的合法性判据是：

```cpp
const bool clipFinite = clipMagAll < 1.0e30f;   // rejects NaN / Inf
if (clipFinite) { s_lastGoodClip = c.clipToPrevClip; s_hasLastGoodClip = true; }
```

**零矩阵的 mag = 0，"小于 1e30"完全成立** ⇒ 它被当成合法矩阵，**并且被写进
`s_lastGoodClip`** —— 也就是后续帧在守卫触发时回退用的那份"上一帧合法位移"。
**污染是不可逆的：一个 0 会作为"好值"被反复重放。**

`clipDev` 那一侧同样会骗人：零矩阵的 `max|I − 0| = 1.0`，**看起来像"动了很远"**，
实际是一个退化矩阵。

修法：判据加下界 —— `clipMagAll < 1.0e30f && clipMagAll > 1.0e-6f`。
单位阵（真正静止的相机）mag = 4.0，任何真实运动都维持在 4 附近，**只有退化矩阵会掉下 1e-6**。
失败的那一帧现在保持上一份合法矩阵（没有就退回单位阵），不再把"相机没动"这句假话发给 DLSS-G。

## 35.4 两条自伤诊断（都在这一轮浪费了我的时间）

1. **verdict 阈值与它宣称区分的东西不匹配。** 判定链把
   `else if (diag.tidCallsB > 10)`（"第二个线程在持续调用 slSetConstants"）排在所有检查**之前**，
   而日志显示 `a=1`：**第一个调用者只调了一次就再没回来**（这正是世界入口处一次性调用的样子），
   `b=30→180` 只是渲染线程在正常每帧调用。⇒ **它一条危害都证明不了。**
   改为 `tidCallsB > 10 && tidCallsA > 10`（两个线程都真的在活跃）。
   ★ 这是 **L37 的近亲**：条件写了，但它选中的是**另一类样本**。
2. **陈旧断言。** `- depth/mvec must read 2560x1440 (the real interop buffers)`
   打印时三个 extent 全是 `3840x2160`，而这些 extent 就在**上面几行**从 interop 资源本身读出来的
   （v0.56 就是为修那个 1.5× 错配才改成从资源取）。**这条消息是这一局日志里唯一能把我引向
   "分辨率不匹配"这个不存在的方向的东西** —— 它确实短暂地骗了我。
   改成比较 depth 与 mvec（唯一会失败的检查）。

## 35.5 方法论

- **L42：仪器必须自证运行过（L39 用在自己代码上）。** 只在成功路径上打日志的探针，
  **失败时和"一切正常"在日志里长得一模一样**。必须有一条**独立的**"我没跑起来"的告警。
  本轮落地：armed 后 15 秒仍 0 样本 ⇒ `log::error`，并在文本里写死
  **「没有 [PIXEL] 采样行 = 没测量，绝不等于画面正常」**。
- **L43：跨 tick 的生产/消费不能塞进同一个调用。** `Copy` 与 `Map` 同调用 ⇒ 消费者必然
  等不到生产者。任何"生产-消费"设计都要先问：**消费者需要等待生产者吗？**
  要，就必须跨帧；不要，才允许同调用。这也是"DO_NOT_WAIT 便宜"这个想法的反面 ——
  DO_NOT_WAIT 只是让**失败**变便宜，它不会让**成功**出现。
- **L44：一个量只有在"反例下会变"时才是见证。** 哈希连续相同，只有在**相机在动**时才等于
  "画面陈旧"；相机静止时插帧输出**本来就该**和真实帧一致。本轮把 `clipDev` 与哈希并排记录，
  并规定只有 10 秒里 ≥5 秒相机在动才报 VERDICT —— **否则探针会对着站桩的玩家喊"冻结"**，
  再浪费一局。

## 35.6 收尾状态与下一局判据

| 项 | 值 |
|---|---|
| DLL | 1,368,576 B，md5 `83e84a781bf645ec3363b58c5fb671ec`（build == MO2 部署）|
| INI | md5 `efce89119d840670e519d219749a6476`（源树 == 部署）—— 本轮**无新键**，无需改 |
| INI 关键键 | `Provider=1`、`DLSSGFramesToGenerate=3`、`MFGMaxFramesOverride=3`、`MenuDisableFrameGen=1`、`MenuGuardFader=1`、`InteropFenceWait=1`、`NRAllowWithFrameGen=0`、`PixelProbe=1` |
| git | HEAD `2acd52f`，tag `v1.23`，`git status --short` 空 |
| 行尾 | `DX12SwapChain.cpp` 纯 LF（bare_lf 1819→2035）；`Streamline.cpp` CRLF+BOM（2392→2423）；两个头文件纯 CRLF；全库 `lone_cr=0` |
| 补丁 | `tools/patch_v123_probe_fix.py`（9 条编辑 / 4 文件；干跑默认；funcspan 模式按签名+花括号定位函数；重跑 `REFUSED`）+ `tools/v123_pixelprobe_impl.txt` |

**下一局这么跑**：① 进世界**站着不动 15 秒** → ② **按住 W 走 10 秒以上** → ③ 再退。
（第二步从 5 秒改成 **10 秒**：VERDICT 需要连续 10 秒的样本，而且要求其中 ≥5 秒相机在动。）

| 日志里看什么 | 命令 | 判据 |
|---|---|---|
| 探针有没有在采样 | `grep -a "\[PIXEL\]" <log>` | 每秒一行 `#N … chg= clipDev= movedThisStreak=` |
| 探针**没**在采样 | 同上 | 出现 `[PIXEL] ERROR: armed N s ago and produced ZERO samples` ⇒ 仪器坏了，**不要**读成画面正常 |
| 画面是不是真的陈旧 | 同上 | `[PIXEL] VERDICT`（连续 10 秒同哈希且相机在动）|
| 站桩时的同哈希 | 同上 | `10 identical seconds, but the camera was still` ⇒ **预期行为，不是冻结** |
| 4x 有没有生效 | `grep -a "presented per real frame" <log>` | 出现 `= 4` |
| 加载为什么慢 | `grep -a "stall governor" <log>` | 帧时间是否仍 > 800 ms |
| 零矩阵还在不在 | `grep -a "\[MOTION\]" <log>` | 修订后应**消失**（或伴随 `detGuard` 计数）|

**回退**：探针 `PixelProbe=0`（只改 INI）；围栏 `InteropFenceWait=0`（只改 INI）；
零矩阵那条与 fader 那条在**代码**里 ⇒ `git checkout v1.22 -- src/` 再 `./build_vs.sh`。

**未证 / 未做（别假装做了）**：v1.22 的每帧跨 API 拷贝**与加载卡死之间的关系未证**；
机制②互操作围栏仍是**症状吻合 + 头号嫌疑**；冻结的**存在性**至今**仍无独立见证**
（`[PIXEL]` 从未成功采样过任何一局）；DLSS5 屏幕输出未证；RTX 20/30 未动。
