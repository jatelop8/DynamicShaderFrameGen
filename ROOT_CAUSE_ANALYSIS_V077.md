# DFG 帧生成失效 —— 最终根因（v0.77 定案）

**日期**：2026-09-18
**被分析运行**：v0.76（build Sep 18 2026 07:34:13，md5 `8428c0f9e793571e481e2ffe0de70813`），08:27:22 – 08:29:09
**数据源**：`DynamicShaderFrameGen.watchdog.log`（470 tick / 95.4s）+ `DynamicShaderFrameGen.log`（821 行）+ 插件源码

---

## 0. 两次认错

### 0.1 上一轮（`msg=0` 判据）
我写"卡的是消息线程 ⇒ 渲染侧修不到"。**错。**
只看首个/末个采样点，没做分布分析。补齐后（`tools/analyze_msg0.py`），115 次 `msg=0` 是**两段**：

```
#0  08:27:35.140 -> 08:27:53.999  95 探测 18.86s  帧 1->6      maxSil=19591ms
#1  08:28:54.744 -> 08:28:59.356  20 探测  4.61s  帧 3530->3792 maxSil=17ms
```

段 #0 里 `frames` 从 1 到 6（≈0.27 fps）、`silent` 爬到 **19591ms** ⇒ **渲染线程也停着**。
我引用的 `silent=13ms` 是**末次采样**，属于另一段。且 `alive=0` 那 4 次全在 **08:27:34.3–34.9**（首个 `Present` 之前，hwnd 未发布），
**不是窗口消失、更不是被杀** —— 我上一轮那两条结论都错了。

### 0.2 本轮中途（一度以为要改插件源码）
我先写了"结论：没有死锁，DDL 是加载时长"——方向对了一半，但**漏掉了真正的病**，因为旧报告根本没有"帧生成实际有没有输出"这一段。补了 `part_dlssg_health()` 才看到。
**教训：诊断工具缺一个"结果"维度的段，就会让"条件全绿"看起来像"功能正常"。**

---

## 1. 真正的根因（★ 一句话）

> **倍率阶梯探测（ladder probe）被菜单屏蔽逻辑挡住了。**
> 菜单开着时 `menuBlock=true` ⇒ 跳过 `SetDLSSGOptions` ⇒ **阶梯一次都不推进**。
> 用户在**主菜单停留了 67.1 秒**，这 67 秒里插件一直在请求 `numFramesToGenerate=3`（4x），
> 运行时只接受 2x ⇒ `slDLSSGSetOptions` 每帧被拒 ⇒ **插值帧数 = 0**。
> 菜单一关（`08:29:01.030`），阶梯立刻跑了 **35 毫秒**就收敛到 2x —— 证明阶梯本身是好的，**只是没机会跑**。

### 1.1 证据链（四步闭合）

**① 调用点：阶梯只在这里推进**（`DX12SwapChain.cpp:1229-1242`）
```cpp
const bool menuBlock = fgOn && fg.settings.menuDisableFrameGen && fg.streamline.MenuIsOpen();
if (menuBlock) {
    dlssgFailCount = 0;                       // 主动直通，不是失败
}                                              // <-- SetDLSSGOptions 被完全跳过
else if (fgOn && fg.streamline.featureDLSSG && fg.GetFrameBuffer()) {
    m_stage = "dlssg SetDLSSGOptions";
    fg.streamline.SetDLSSGOptions(...);        // <-- 只有这里会推进阶梯
```

**② 阶梯状态机**（`Streamline.cpp:1114-1116`）
```cpp
if (mfgProbeStep == 0 || mfgProbeStep > effectiveMax)
    mfgProbeStep = clamp(settings.dlssgFramesToGenerate, 1, effectiveMax);
```
`MFGMaxFramesOverride=3` ⇒ `effectiveMax=3`；INI `DLSSGFramesToGenerate=3` ⇒ **首帧就请求 4x**。

**③ 菜单开合窗口 = 死亡窗口**（主日志，**精确到毫秒吻合**）
```
08:27:53.909  MENU EDGE open=1 serial=2
08:29:01.030  MENU EDGE open=0 serial=3890
```
跨度 = **67.121 秒**。

**④ 帧生成死亡窗口 = 同一个区间**（`9x` 段实测）
```
帧生成在 08:27:53.903 .. 08:29:00.013 之间全程为 0（34 个连续探针）
FPS 探针 38 次，accepted=0 : 34 次，accepted>=1 : 4 次
首次真正生效：08:29:02.027
```
`08:27:53.903` vs `MENU EDGE open=1 @ 08:27:53.909` —— **差 6 毫秒**。
`08:29:00.013` vs `MENU EDGE open=0 @ 08:29:01.030` —— 差 1 秒（菜单关闭后的最后一帧）。

### 1.2 阶梯本身完全正常（35 毫秒收敛）

菜单一关，三行日志连着出现：
```
08:29:01.030  MFG probe: runtime REJECTED 4x (result 38 = eErrorInvalidState) -> retrying at 3x
08:29:01.048  MFG probe: runtime REJECTED 3x (result 38 = eErrorInvalidState) -> retrying at 2x
08:29:01.065  MFG probe: runtime ACCEPTED 2x (1 interpolated frames) | runtimeReportsMax=2x overrideAsksMax=4x
```
⇒ **35 ms 就收敛**。而它被挡了 **67 秒**。

---

## 2. 修复方案

### 2.1 主修：让阶梯在菜单期间也能推进（推荐）

**机理**：阶梯是**一次性校准**（探测运行时的真实能力），不是每帧的状态。
把它绑在"渲染路径会跑到"的条件下，就必然被菜单屏蔽逻辑挡住。
**修法**：把阶梯校准从 `SetDLSSGOptions` 里提出来，改为**每帧独立调用一次**，
且**不受 `menuBlock` 影响**（因为它只是校准，不下发插帧决策）。

```cpp
// 新增：Streamline::ProbeMfgLadder()
// 与 SetDLSSGOptions 解耦；每真实帧调一次；menuBlock 不影响它。
// 只做「请高倍率 -> 被拒则降档 -> 接受则锁定」，不碰 present 路径。
void Streamline::ProbeMfgLadder(std::uint32_t a_width, std::uint32_t a_height,
                                std::uint32_t a_colorFormat)
{
    if (mfgProbeLatched) return;                  // 已收敛，零开销
    const std::uint32_t effectiveMax = std::max<std::uint32_t>(1, dlssgEffectiveMax);
    if (mfgProbeStep == 0 || mfgProbeStep > effectiveMax)
        mfgProbeStep = std::clamp<std::uint32_t>(Get().settings.dlssgFramesToGenerate, 1, effectiveMax);
    // ... 与现有 1160-1190 行同一套 opts 构造 + 结果处理 ...
}
```
调用点放在 `DX12SwapChain.cpp` 的 `menuBlock` 分支**之前**：
```cpp
if (fgOn && fg.streamline.featureDLSSG && !fg.streamline.MfgProbeLatched())
    fg.streamline.ProbeMfgLadder(swapChainDesc.Width, swapChainDesc.Height, swapChainDesc.Format);
const bool menuBlock = ...;   // 保持原有逻辑不变
```

**收益**：首帧 + 最多 3 帧内收敛（4x→3x→2x），**不管菜单开不开**。
**风险**：校准期会在菜单里下发 1–3 帧的插值请求。这本来就是 `eEnableFullscreenMenuDetection` 要处理的情况，
且比"67 秒零输出"轻得多。

### 2.2 次修：`MFGMaxFramesOverride=3` → `0`（无 unlocker 时）

用户已明确 **Transfusion 不部署在游戏本体**（"本体不需要部署，删掉"）。
那么 `runtimeReportsMax=2x` 就是**硬上限**，INI 请求 4x 等于**必然被拒**。

| INI | 当前 | 建议（选项 A：接受 2x） |
|---|---|---|
| `MFGMaxFramesOverride` | `3`（4x） | **`0`**（跟随硬件上报） |
| `DLSSGFramesToGenerate` | `3`（4x） | **`1`**（2x） |

⇒ 首帧直接请求 2x，**零阶梯、零拒绝、零空窗**。INI 第 22 行自己就写了
"Changing this needs a game restart"，第 79 行写了"Without such an unlocker a high multiplier has no kernel to run"。

### 2.3 若要 4x（选项 B）

把 Transfusion 放回**游戏根目录**（备份在 `_removed_transfusion_20260918-074044/`）。
但**必须知道代价**：两插件同时钩同一份 `sl.interposer.dll`（md5 一致 `4bef61f9eb918aa7dc05169e8fb73e01`），
每帧互写 `slSetConstants` / `slSetTagForFrame` / `slDLSSGSetOptions`（**已证实冲突**）。

**⇒ A 与 B 互斥。当前环境处于"A 但请求值仍是 4x"的矛盾状态，这就是 67 秒零输出的直接来源。**

```bash
# 选项 B 才执行
cp "D:/Modding/DynamicShaderFrameGen/_removed_transfusion_20260918-074044/dinput8.dll" \
   "D:/ENB-EJ/Skyrim Special Edition/"
cp "D:/Modding/DynamicShaderFrameGen/_removed_transfusion_20260918-074044/DLSSG-Transfusion.json" \
   "D:/ENB-EJ/Skyrim Special Edition/"
```

### 2.4 附带：`menuBlock` 期间也应保持"已知可用倍率"

现在 `menuBlock` 分支把 `dlssgFailCount` 清零（正确），但它**不下发任何 options**，
于是运行时状态停留在"上一次被拒的 4x"。更稳的做法是在 menuBlock 分支里
**用已锁定的 `dlssgAcceptedFrames` 下发一次 eOn**，让菜单里的状态与锁定值一致。

---

## 3. 关于"卡死"

**修正后的结论：不存在 DFG 导致的卡死。**

| 段 | 时间 | `msg` | `frames` | `LONG FRAME` | 判读 |
|---|---|---|---|---|---|
| A | 08:27:34.3 → 08:27:53.9 | 0 ×95 | 1→6 | **19707.4ms** | 游戏自身加载 19.7s |
| B | 08:27:54 → 08:28:54 | 1 ×347 | 1→3530 | — | 主菜单 3D 背景，58fps，健康 |
| C | 08:28:54.7 → 08:28:59.4 | 0 ×20 | 3530→3792 | 357.2ms | 菜单→世界 切换载入 |
| D | 08:28:59.4 → 08:29:09.7 | 1 | 3792→4314 | — | 世界内，健康 |

* `LONG FRAME` 只有 2 条，与 burst #0 / #1 **一一对应** ⇒ 同源。
* `focus=1` 全程、`alive=1`（除启动前 4 次）⇒ 窗口与进程都在。
* 会话以 `08:29:09.828 [DMK] WM_ACTIVATEAPP: Game lost focus` 结束 ⇒ **用户切走**，非崩溃。
* 看门狗 `<DLL_PROCESS_DETACH>` 缺失 + 末帧健康 ⇒ 不是 loader 正常退出，也不是硬崩。

⇒ **"卡死" = Skyrim 自身的同步加载（19.7s + 0.36s），窗口在加载期间不应答是正常表现。**

---

## 4. 本次代码改动

**插件源码：未改**（根因已定位到具体行，但改动需要构建+进游戏验证，等用户选 A/B 后再动）。
**诊断工具：5 个补丁已应用。**

| 文件 | 改动 |
|---|---|
| `tools/analyze_msg0.py` | **新建** —— `msg=0` 按 burst 分组 + 交叉 `silent`/`stage`/`focus`/`frames` |
| `tools/patch_reader_v077_msg0_classify.py` | `part_responsiveness` 改为 burst 分类，`LOAD_STALL_MS=1500` |
| `tools/patch_reader_v077b_alive_semantics.py` | `alive=0` 区分"hwnd 未发布"/"窗口真消失"；删除错误的 TerminateProcess 结论 |
| `tools/patch_reader_v077c_dlssg_health.py` | **新增 `part_dlssg_health()`（9x 段）** —— 五轮来第一次报告帧生成实际产出 |
| `tools/patch_reader_v077d_lines_tuple.py` | 修 `lines` 元素是 `(ts,tid,text)` 元组而非裸串的迭代 bug |

`read_xray_log.py`：68927 B → **76409 B**（5 个 `.bak` 备份）

### 4.1 新判据

```python
LOAD_STALL_MS = 1500
load_like = (max_sil >= LOAD_STALL_MS) and (frames_right - frames_left) <= max(8, len(b) // 4)
```
* `msg=0 + silent>=1500ms + 帧不动` ⇒ **载入停顿**（游戏自身）
* `msg=0 + silent<1500ms + 帧在走` ⇒ **消息泵卡死**（才需查主线程）

### 4.2 新段实测输出

```
9x. DLSS-G 实际产出（v0.77：accepted= / dlssgOk= / MFG 梯子）
  [信息]FPS 探针 38 次
         其中 accepted=0（帧生成**没有输出任何插值帧**）：34 次
         accepted>=1（真的在插帧）：4 次
         首次真正生效：08:29:02.027（accepted=2）
  [问题]帧生成在 08:27:53.903 .. 08:29:00.013 之间全程为 0（34 个连续探针）
  [信息]日志自己把倍率标为 COMPUTED not measured 的行：38 条
  [信息]MFG 梯子：拒绝 2 次 / 接受 1 次
         运行时自报上限 = 2x，我们请求 = 4
  [问题]运行时自报上限只有 2x —— 4x/3x 被 eErrorInvalidState(38) 拒绝。
  [问题]帧生成有 89% 的时间是关闭的（accepted=0）。
```
总结段新增：`运行时只支持 2x（4x 需要外部 unlocker）` + `帧生成 89% 时间未输出`。

---

## 5. 验证方法

```bash
"C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe" \
  D:/Modding/DynamicShaderFrameGen/tools/read_xray_log.py
```

**判据（按优先级）**
1. `9x` 段 `accepted>=1` 占比 → **应接近 100%**（现 10.5%）
2. `9x` 段不得再出现 `runtimeReportsMax=2x overrideAsksMax=4x` 并存
3. `9x` 段 `accepted=0` 连续段长度 → **应 ≤ 3 个探针**（现 34 个）
4. `0e` 段 `② 消息泵卡死` 段数 → 应为 0
5. **在菜单里等 30 秒**再看 `9x` —— 修复后菜单期间也应已锁定 2x（现会全程 0）
6. 进世界走动 30 秒，`clipDevMax > 0`（证明自维护历史在动）

**回归测试（必须）**：改完源码后至少跑一次"主菜单停 30 秒"的用例 —— 这正是本次暴露缺陷的场景。

---

## 6. 仍未定案

1. **加载 19.7 秒** —— mod 规模问题（775+ mod / DynDOLOD），DFG 改不到。
2. **捕获层缺陷**：被接受的相机整场累计位移 **0.00 单位**（`[CAM] acc` 全是 `pos=(-50,600,80)`）⇒ 快照相机不跟随玩家。**独立严重缺陷，未处理。**
3. **重投影 `clipToPrev=identity`** —— 两插件独立观测到；DFG 侧 `hist hit=420/miss=1`（99.8%）走自维护，但 `useDerived = false && ...`（`Streamline.cpp:649`）是死代码 ⇒ **未在世界验证**。本次 `clipDevMax=0` 因相机确实静止，不是缺陷。
4. **`dvd(ok/used)=0/0 err=16`** 三字段矛盾，未解。
5. **加载画面闪烁**（v0.63–v0.70 老问题）**完全未触及**。
6. **世界样本仅 424/4312 帧（9.8%）** —— 验证世界内表现必须专门进去走一段。

---

## 7. 双插件冲突证据（存档）

Transfusion v1.4.0-pure-warp，PDB 路径 `D:\Coding\DLSSGUnlock\DLSSG-Transfusion\build\Release\DLSSG-Transfusion.pdb`（md5 `c048b46e4005…`）。
自述：`Direct Detours on sl.interposer.dll installed successfully (slGetFeatureFunction, slInit, slSetD3DDevice, slSetVulkanInfo, slSetData, slSetConstants, slSetTag, slSetTagForFrame)`、
`Intercepted slDLSSGSetOptions for live multiplier control`、`Applied fixed multiplier: 4x, result=0 (eOk)`。
独立佐证重投影缺陷：`[MOTION] route=slSetConstants call=0..3 clipToPrev=identity prevToClip=identity projection=non-identity`（每帧 4 次）。

`DLSSG-Transfusion.crash.log` **有内容但并非崩溃**：`rva=0x7B9D` 落在它自己的 `DINPUT8.dll` 内，仅 3 条
（撞上自设"每站点 3 次"上限），access address 各不相同 + `Rax=0x5A4D`("MZ") ⇒ 模块枚举试读，全部 `END_EXCEPTION`。

---

## 8. 构建记录

本次**未改 `.cpp`/`.h`** ⇒ dll 仍是 v0.76（`8428c0f9e793571e481e2ffe0de70813`），无需构建。
改动全在 `tools/read_xray_log.py` + 5 个新脚本。

回滚：
```bash
cp D:/Modding/DynamicShaderFrameGen/tools/read_xray_log.py.bak-20260918-083401 \
   D:/Modding/DynamicShaderFrameGen/tools/read_xray_log.py
```
