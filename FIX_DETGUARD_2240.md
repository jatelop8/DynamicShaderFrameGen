# v0.66 —— 交给 DLSS-G 的重投影矩阵在**数学上非法**（det 守卫）

运行：2026-09-17 22:30:39 – 22:31:53（v0.65 DLL `aed2c152…`）
结论日期：2026-09-17 22:40
用户原话：「就是进不去游戏啊」

---

## 一、先纠正我上一轮的错误判读

上一轮我用 `world=541` 断言「引擎实际已经在世界里跑」。

**这个推断是错的。** 代码里 `worldFrames` 的判定是：

```cpp
if (frameSerial != diag.lastCountedSerial) {
    diag.lastCountedSerial = frameSerial;
    if (isMenuOpen) ++diag.menuFrames;
    else            ++diag.worldFrames;   // 只表示「菜单没开」
}
```

`worldFrames` **只表示"这一帧菜单没打开"**，不代表"在可玩的世界里"。
加载界面 / 进场过程同样会被算进 `world`。

⇒ 我上一轮「日志显示引擎在世界里跑」的结论**不成立**，用户的「进不去」应当接受。

---

## 二、22:31 那次运行的完整时间线（每条都有出处）

| 时刻 | 事件 | 日志出处 |
|---|---|---|
| 22:30:39.866 | Reflex FLIP cap 设置成功 | `Reflex FLIP cap = 159 fps (6289us) - panel 160Hz, 4 flips per real frame` |
| 22:30:40 → 22:31:01 | 启动 + 装载主菜单，**单帧 21.5 秒** | `LONG FRAME 21469.6ms (capUs=6289 mult=1 menu=0)` |
| 22:31:01.407 | DLSS-NR 命令上下文饱和 | `[W] [DLSSNR] D3D12 command contexts saturated; applying CPU backpressure` |
| **22:31:04 → 22:31:49（45 秒）** | `ask=2 accepted=0`、`real=45~55 fps`、`kMAIN=true` | 每 2.5 秒一条 `DLSSG diag` / `FPS probe` |
| 22:31:50.126 | **`SetDLSSGOptions` 首次调用 = 进入世界流程** | `MFG probe: runtime ACCEPTED 4x (3 interpolated frames)` |
| 22:31:50.466 | 插帧启动 | `DLSSG presented per real frame = 4` |
| 22:31:50.951 | DLSS-G 就绪 | `DLSSG diag: fgOn=true dlssgOk=true ... fail=0` |
| 22:31:51.141 | 插帧确认在跑 | `FPS probe: real=42.1 ... ask=4 accepted=4` |
| 22:31:53.3 | **进程终止**（DFG 日志与看门狗同时停止，看门狗无 STALLED） | 两份日志最后一行 |

**⇒ 整个世界阶段只有 3 秒。**

**⇒ 那 45 秒里 `accepted=0`（DLSS-G 未插帧）—— 这正是主菜单「不闪」的原因，不是菜单拦截的功劳。**

---

## 三、新根因：重投影矩阵**数学上非法**

### 3.1 中间层记录的真值（Transfusion 自己写的，不是我推的）

```
22:31:50.166  call=0 tid=42736  clipToPrev=identity      cameraPos=(-49.5040817,824.555054,89.4614334)
22:31:50.278  call=1 tid=37436  clipToPrev=non-identity  cameraPos=(-243.048859,-415.314819,118.623505)
22:31:50.314  call=2 tid=37436  clipToPrev=identity      cameraPos=(-243.048828,-415.315033,118.628716)
22:31:50.366  call=3 tid=37436  clipToPrev=non-identity  cameraPos=(0,0,1.00001001)
```

**注意 `call=0` 与 `call=1` 的相机位置相距 1300+ 单位** —— 一秒内同一个相机不可能出现在两个位置。

### 3.2 数学判据（这是本轮的核心）

`clipToPrevClip = inv(cur) × prev`。当两帧的投影矩阵相同时，投影项互相抵消：

```
det(clipToPrevClip 的左上 3x3) = det(inv(proj)) × det(view_prev × view_cur⁻¹) × det(proj) = 1
```

⇒ **合法重投影矩阵的左上 3×3 行列式必须 ≈ 1**（纯旋转）。

用 Transfusion 记录的真实矩阵手算：

| 矩阵 | 数据 | det(左上3×3) | 判定 |
|---|---|---|---|
| `call=1` | `m[2]=[0,0,1.00069,0]`, `m[0][0]=-5.6245`, `m[1][1]=5.5764` | **−31.39** | 非法 |
| `call=3` | `m[2]=[0,0,14.99914,0]`, `m[1][2]=0.50002` | **−0.0252** | 非法 |
| `call=2` | 单位矩阵 | **1.0000001** | 合法 |

**⇒ 那两个矩阵不是任何合法变换。DLSS-G 拿它们重投影每一个生成帧 ⇒ 位移完全错 ⇒ 成片闪。**

### 3.3 内部证据咬合（同一行心跳里）

| 字段 | 观测值 | 含义 |
|---|---|---|
| `clipDev` | `15.002136` | = `clipToPrev[3][2]`，与 Transfusion 的 `−15.0021362` **是同一个数** |
| `curVP` | `15.0110` / `15.0006` / `2.0001` | 三组交替 |
| `pos` | `(-49.5,824.6,89.5)` / `(-243.0,-415.3,118.6)` / `(0.0,0.0,1.0)` | 同上 |

---

## 四、v0.66 改动（12 处 / 3 文件）

| # | 改动 | 目的 |
|---|---|---|
| 1 | **行列式守卫** `det3()`：det 不在 `[0.5, 2.0]` ⇒ `clipToPrevClip` 钳成单位矩阵 + 计数 | **核心修复**。数学可判定，不是猜阈值 |
| 2 | `det(min/max)` / `detGuard` 进心跳 | 让判据**自我验证** —— 下次日志可见真实 det 分布 |
| 3 | 7 个函数内 `static` → `thread_local`（`s_prevVP` / `s_hasPrevVP` / `s_lastEngCur` / `s_hasLastEngCur` / `s_engCurFrozen` / `s_wasMenuOpen` / `s_wasCamValid`） | 跨线程共享历史会被交错污染 |
| 4 | per-tid 调用计数取代哨兵（`tid(a/b/c)=…` + `calls=a/b/c`） | 哨兵分不清「一次性线程交接」与「真的并发」 |
| 5 | `dlssgFailCount` / `dlssgDiag` → `std::atomic<int>` | 消除多线程 `++` 的数据竞争 |

**踩坑**：`fmt` 无法直接格式化 `std::atomic<int>` —— 编译直接报错，已改为 `.load()`。
（这是必须编译的理由：Streamline.cpp 的改动全部一次通过，只有这一处被编译器抓到。）

### 为什么用「单位矩阵」而不是「跳过这一帧」

单位矩阵 = 告诉 DLSS-G「相机没动」。这是**安全的退化**：宁可少一次相机运动，也不要一个错误的位移。
若改成「跳过插帧」，上屏帧率会在 `real` 与 `real×4` 之间振荡 ⇒ **引入新的闪**。

---

## 五、这次为什么不是「再来一轮试错」

v0.66 的判据是**数学的**，不依赖阈值调参；而且判据本身被打进日志，下次运行会**自己给出结论**：

| 下次日志出现 | 结论 |
|---|---|
| `detGuard>0`，且 `det(min/max)` 里有一批远离 1 的值 | **确认**：非法矩阵就是闪源，且已被拦住 |
| `det(min/max)` 全部 ≈1 且 `detGuard=0` | 判据没命中 ⇒ 坏帧没出现，或我的 det 推导需修正（看数据即可定） |
| `calls=a=N, b=1` | 第二线程只是**一次性交接**（不是并发）—— 我上一轮的哨兵误报了它 |
| `calls=a=N, b=M`（都很大） | **真的并发** ⇒ `thread_local` 是必需的 |

---

## 六、诚实边界

- 我无法启动游戏，**v0.66 没有经过运行验证**。
- 但这次的判据不依赖"试出来"：`det(inv(cur)×prev) = 1` 是矩阵恒等式。
- 若下次 `detGuard` 拦住大量帧而画面仍闪 ⇒ 闪另有他源，需要看新数据再定（我会明确说"还不确定"，不会硬凑结论）。
- 「进不去游戏」：日志显示进程在 22:31:53 终止、看门狗 `frames=2463 silent=30ms` **无 STALLED**
  ⇒ 是**主动退出**而非卡死。那 3 秒里插帧确实在跑，画面看到的应当是 DLSS-G 输出的错位结果。

---

## 七、下次运行（一次即可）

1. 主菜单停 **5 秒** → 回车 → **走一走、转一转 20 秒** → 退出
2. 双击 `read_log.bat`
3. 最关心的四个数：

| 字段 | 期望 |
|---|---|
| `detGuard` | 若 >0 即坐实根因（已被拦） |
| `det(min/max)` | 健康时应贴近 `1.000` |
| `calls=` | 看出到底几个线程在调 |
| `clipDevMax` | 修好后应远小于 15 |

⚠️ **运行期间不要编译** —— `build_vs.bat` / `build_vs.sh` 的 POST_BUILD 会把工程 INI 覆盖回 mod 目录，手改的值会被冲掉。

---

## 八、文件清单

- `tools/add_xray_v066.py` —— 断言式补丁（12 处锚点必须恰好命中 1 次，支持干跑）
- `src/*.bak-20260917-223806` —— 改动前备份
- `tools/read_xray_log.py` —— 新增 det / per-tid 判定（含旧日志向后兼容）
- DLL `6ee7a0f8deb8dc29bec82e9645d670ae`（1265152 B），POST_BUILD 自动同步到
  `E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\`，**md5 与构建产物一致**
