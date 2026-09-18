# v0.65 交接 — 重投影的**数据源**才是闪烁根因

**时间**：2026-09-17 22:28
**输入**：22:18 那次运行的 `DynamicShaderFrameGen.log`(169 行) / `DynamicShaderFrameGen.watchdog.log`(9058 B) / `DLSSG-Transfusion.log`(82065 B) / `DLSSG-Transfusion_perf.csv`(791 B)
**DLL**：`aed2c1529a5c3b5c64096c2f9322997a`（1261568 B），已由 POST_BUILD 同步到 `E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\`
**备份**：`src/Streamline.h.bak-20260917-222448`、`src/Streamline.cpp.bak-20260917-222448`、`src/FrameGen.cpp.bak-20260917-222448`

---

## 一、判决

### 1.1 上一版（v0.63）修好的部分 —— 确认生效

| 观测 | 值 | 说明 |
|---|---|---|
| `Reflex FLIP cap` | `159 fps (6289us) - panel 160Hz` | v0.63 的 pacing 修复生效（旧值 25641us） |
| `dt min/avg/max` | `17.46 / 32.06 / 47.09 ms` | **在飘**，不再是 102.56 的量子 ⇒ 真负载支配 |
| `real=` | `30.9` fps（`cap~=123.8 (=real*4)`） | 真实帧率从 9.75 → 31（上屏 ~124） |
| 看门狗 | frames 2270，`silent` 最大 33 ms，**无 STALLED** | 装载期 20 s 静默属正常 |
| `consts ok=150 fail=0` | 零失败 | 帧令牌健康 |

`LONG FRAME 21561.9ms` 只有一条，是装载主菜单那 21.5 秒 —— 正常。

### 1.2 真正根因：引擎的 `CameraPreviousViewProjUnjittered` **恒等于 cur**

心跳里每一条采样，`prevVP` 都等于同一行的 `curVP`：

```
serial=2120: curVP=15.0110  prevVP=15.0110
serial=2210: curVP=15.0006  prevVP=15.0006
serial=2240: curVP=15.0006  prevVP=15.0006
serial=2270: curVP=15.0006  prevVP=15.0006
```

Transfusion 侧是独立佐证 —— 4 次 `slSetConstants` 全部记录 `clipToPrev=identity`：

```
22:18:57.463 [MOTION] call=1 clipToPrev=identity rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1]
22:18:57.500 [MOTION] call=2 clipToPrev=identity rows=[1 9.5e-14 -1.36e-10 2.3e-10]...
22:18:57.558 [MOTION] call=3 clipToPrev=identity rows=[1 0 0 0][0 1 0 0][0 0 1 0][0 0 0 1]
```

**⇒ `clipToPrevClip = inv(cur) × prev = 单位矩阵`，DLSS-G 收到的相机运动量恒为 0。**
**⇒ 它被反复告知「相机没动」，生成帧永远按「静止」重投影。**

这解释了用户观察到的**每一个字**：

| 现象 | 机制 |
|---|---|
| **加载菜单本身不闪** | 菜单里相机本来就静止，单位矩阵**恰好是正确答案** |
| **快进游戏的时候闪** | 一进世界相机开始动，但 DLSS-G 仍被告知「没动」⇒ 生成帧停在旧位置 ⇒ 成片错位 |
| **进不去游戏（像卡住）** | 画面在加载图与世界之间来回错位，看起来像没进去 |

**为什么 v0.64 没修好**：v0.64 把**零矩阵**钳成**单位矩阵**。零矩阵 = 「矩阵无效」，单位矩阵 = 「相机没动」—— **两者都让 DLSS-G 认为相机静止**，所以症状照旧。v0.64 治的是症状，不是数据源。

**成因**：Skyrim 只在 **temporal upscaler（TAA/DLSS-SR）启用时**才维护 prev viewProj。v0.50 把超分整段拔掉（`FrameGen.h:207`、`main.cpp:31`），那个字段就再也没人写，引擎把它与 cur 同步成同一个值。

### 1.3 顺带确认：45% 的帧读到零矩阵，是 `Unmap` 钩子读晚了

`cam(ok/inv)` 稳定在 **42~46% 无效**（13/31、27/61、41/91、55/121、70/151）。无效帧的指纹是 `prevVP=1.0000`（`max|0−I|` 恰好是 1）。

旧 `Unmap` 钩子的顺序是：

```cpp
func(This, pResource, Subresource);              // ← 先把资源解映射了
fg.frameBufferCopy = *fg.GetMappedFrameBuffer(); // ← 才去读 pData
```

Unmap 之后驱动可以立刻回收/复用那块内存 ⇒ 读到零或陈旧数据。**拷贝必须发生在原始 Unmap 之前。**

### 1.4 排除掉的：不是"两个线程在打架"

Transfusion 的 tid 在 40760 / 3508 之间交替，一度像是并发。但 `CheckFrameConstants` 全仓**只有一个调用点**（`Streamline.cpp:934`，在 `EvaluateDLSSG` 内），没有第二个线程路径。v0.65 把 tid 打进心跳（`tid={:#x}`），若真出现并发会直接报 `0xFFFFFFFF`。

---

## 二、v0.65 改了什么（9 处 / 3 文件）

| # | 文件 | 改动 | 目的 |
|---|---|---|---|
| 1 | `Streamline.h` | `Diag` 新增 16 个字段 | 让日志能自己回答"数据源是谁" |
| 2 | `Streamline.cpp` | **不再使用引擎的 prev**，改为自维护 `s_prevVP` 历史 | 核心修复 |
| 3 | `Streamline.cpp` | **派生源**：`viewProj = inv(CameraViewInverse) × CameraProjUnjittered` | 引擎 cur 冻结时的保险 |
| 4 | `Streamline.cpp` | 派生源**首帧交叉校验**（相对误差 ≤1% 才启用） | 构造错就作废，不引入新病 |
| 5 | `Streamline.cpp` | `clipDevMax` 探针（窗口内 `max|clipToPrev−I|`） | 一眼判定"有没有相机运动" |
| 6 | `Streamline.cpp` | 心跳扩展 + VERDICT 重写 | 自判定 |
| 7 | `FrameGen.cpp` | `thread_local FrameBuffer* tlsMappedFB` | 消除跨线程交叉覆盖 |
| 8 | `FrameGen.cpp` | Map 钩子写 tls 槽 | 同上 |
| 9 | `FrameGen.cpp` | **Unmap 钩子改为"先拷贝、后调原始 Unmap"** | 修掉 45% 零矩阵 |

### 核心逻辑（`Streamline.cpp` `CheckFrameConstants`）

```cpp
if (curOk) {
    if (s_hasPrevVP) { prevForReproj = s_prevVP; havePrev = true; }
    s_prevVP = curForReproj;      // 只在 cur 有效时推进历史
    s_hasPrevVP = true;
}
if (curOk && havePrev) {
    sl::matrixFullInvert(invCurrViewProj, curForReproj);
    sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);
} else {
    /* 首帧 / cur 无效 → 单位矩阵，并由 prevHistoryMiss 计数暴露 */
}
```

**关键约束**：无效帧（零矩阵）**绝不能进历史**，否则下一帧的 prev 就是零，又回到"矩阵无效"。

### 派生源的安全阀

```cpp
// 只在"引擎 cur 连续冻结 >= 30 帧" 且 "首帧交叉校验通过" 时启用
const bool useDerived = (diag.derivedMatch == 1) && (s_engCurFrozen >= 30) &&
                        finiteMag(derivedViewProj) > 1.0e-6f;
```

`derivedMatch` 来自首帧比对：`derivedViewProj` 与引擎 `currViewProjSL` 的最大逐元素差 ≤ 引擎幅度的 1%。
**若我的矩阵构造方式有错，校验失败 ⇒ 派生源永不启用 ⇒ 不会制造新故障**（只会在日志里留下一行说明）。

---

## 三、下次运行怎么读（一眼判定）

跑：主菜单停 **5 秒** → 回车进世界 → **走一走、转一转 20 秒**（这一步才是检验） → 退出 → 双击 `read_log.bat`。

| 看什么 | 修好后应该是 | 若不对说明 |
|---|---|---|
| `reproj src=` | `engine`（正常）或 `derived`（引擎冻结时切了备源） | — |
| `engPrevEqCur=N/N` | **N == N**（全等） | 引擎确实不维护 prev ⇒ 这正是自维护历史的理由 |
| `clipDevMax` | **> 0.01**（移动中） | `≈0` ⇒ 重投影矩阵还是单位矩阵，闪还在 |
| `hist(hit/miss)` | miss 只在首帧出现（几帧） | miss 持续增长 ⇒ cur 没能每帧提供有效矩阵 |
| `tid=` | 一个具体值 | `0xFFFFFFFF` ⇒ 多线程并发污染 |
| `dvd(ok/used)` | `1/0`（校验通过但不需要） | `0/0` ⇒ 我的派生构造方式不对（无害，但我会修） |
| `dt min/avg/max` | ≈ 25~35ms 且**在飘** | 恒定整数倍 ⇒ pacing 又有问题 |
| `real=` | ≈ 30~40 | 明显低于 25 ⇒ GPU 真受限 |

**最关键的单个数字是 `clipDevMax`**：它衡量"交给 DLSS-G 的重投影矩阵到底带不带相机运动"。
- v0.64 时代它恒为 **0.000000**（单位矩阵）
- 修好后，**移动中它应该明显大于 0**

---

## 四、若 `clipDevMax` 仍为 0（预案）

说明连"自维护历史"都没能产生运动 ⇒ 引擎的 `CameraViewProjUnjittered` 本身是冻结的。此时：

1. 看 `frozen=` —— 若 > 120，就是这条路
2. 看 `dvd(ok/used)` —— 若 `1/N`（已启用派生源），说明连派生源也冻结 ⇒ 引擎两块矩阵都不更新
3. 再往下的杠杆（按顺序，一次一个）：
   - Transfusion `DLSSG-Transfusion.json`：`"multiplier": 4 → 2`（先排除插帧成本）
   - `DynamicShaderFrameGen.ini`：`NRRenderScale` 1.00 → 0.75
   - 关掉 NR 做对照（`-DynamicShaderFrameGenNR` 在 MO2 里启用）
4. **A/B 期间不要编译** —— `build_vs.bat` / `build_vs.sh` 的 POST_BUILD 会把工程 INI 覆盖回 mod 目录，手改的值会被冲掉。

---

## 五、本轮排查中排除的死胡同（别再追）

| 线索 | 结论 |
|---|---|
| `jitter=(0.0000,0.0000)` 全程为 0 | **设计如此**：v0.50 已把 DLSS 超分/DRS/Halton jitter 全拔掉。`FrameGen.h:175` 那句注释是过期谎言 |
| 两个 tid 调 `slSetConstants` | `CheckFrameConstants` 全仓单调用点，不是并发。v0.65 已把 tid 打进心跳验证 |
| 主菜单不闪 = 菜单拦截生效 | **不成立**。`edges=0` 全程 ⇒ 探针那时还没上岗（`world=1` 出现在 `serial=2120`）。而主菜单不闪的真因是 **相机静止 + 单位矩阵恰好正确** |
| `stripped eEnableFullscreenMenuDetection` | 中间层剥离（`0x10 → 0x10`，剥前剥后相同）。v0.65 的 `MenuDisableFrameGen` 是本插件侧实现该语义，与本次根因无关 |

---

## 六、编译环境备忘

- 编译命令：`bash build_vs.sh`（沙箱拦截 `cmd.exe`，`build_vs.bat` 不可用）
- 本轮遇到一次**真实代码错误**：`c.prevClipToPrev` 不是 `sl::Constants` 成员（我自己打错，应为 `c.prevClipToClip`）—— 编译器直接指出，这正是每次改完必须编译的理由
- 另有一次瞬时文件锁（`Permission denied` 写 `.obj`），**重跑即过**
