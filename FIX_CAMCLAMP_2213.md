# v0.64 相机数据有效性钳制 —— 零矩阵是闪烁的主犯

**日期**：2026-09-17 22:13
**本次运行**：22:05:14 启动 → 22:06:18 结束（约 64 秒，其中装载 ~35 s）
**触发**：用户"这次主菜单可以，卡在加载界面闪烁，进不去游戏"

---

## 一、先纠正一个误判：主菜单好了，不是菜单拦截的功劳

上一轮我加了 `MenuDisableFrameGen`（菜单期间不向 DLSS-G 提交）。本次运行**它从未被激活**：

```
[XRAY] serial=711 menu=0 world=1 edges=0 ... menuOpen=0
[XRAY] serial=1251 menu=0 world=541 edges=0 ... menuOpen=0
```

`edges=0` —— **MENU EDGE 一次都没触发**。

原因不是"菜单检测失灵"，而是**探针根本没跑到那儿**：

```
[22:05:47]–[22:05:59]  主菜单 12 秒：ask=2 accepted=0    ← DLSS-G 还没被接受
[22:06:00.238]         MFG probe: runtime ACCEPTED 4x    ← 从这一刻才真正插帧
[22:06:00.238]         [XRAY] diag active v0.61           ← 这行只打印一次
[22:06:00.280]         serial=711 menu=0 world=1          ← 计数从 1 起算
```

`worldFrames` 是**累计**计数器。它在 serial=711 时值为 1，说明
**`CheckFrameConstants` 从 serial 711 才开始被调用**（它挂在
`EvaluateDLSSG` 里，而后者在此之前一直不满足前置条件）。

**⇒ 主菜单那 12 秒从未被采样。** 而它不闪的真正原因是
**DLSS-G 那时还没接受插帧**（`ask=2 accepted=0` 持续到 22:05:59.967），
画面就是干净的原始帧。

**这修正了上一轮的结论**：`MenuDisableFrameGen` 至今**尚未被验证过一次**。
它可能对、可能错，本次运行没有证据。

---

## 二、根因：`ClipToPrevClip` 被写成**零矩阵**

Transfusion 侧记录到的真值（22:06:00.279–22:06:00.507，call=0..3）：

```
call=0  tid=7052   clipToPrev=identity  cameraPos=(-49.3662415, 814.982849, 88.6318436)
call=1  tid=36108  clipToPrev=zero      cameraPos=(-243.048859,-415.314819,118.623505)
        clipToPrev rows=[0 0 0 0][0 0 0 0][-0 -0 -0 -0][0 0 0 0]
call=2  tid=36108  clipToPrev=identity  cameraPos=(-243.048828,-415.315033,118.628662)
call=3  tid=36108  clipToPrev=identity  cameraPos=(-243.04892, -415.314362,118.615227)
```

**零矩阵不是"相机没动"，是"矩阵无效"。**
DLSS-G 用 `clipToPrevClip` 重投影**每一个生成帧**，拿到零矩阵 →
输出画面整体崩坏。这就是"加载界面/世界持续闪"的直接来源。

### 代码路径

```cpp
const Matrix prevVP = a_fb.CameraPreviousViewProjUnjittered;   // Streamline.cpp:384
sl::matrixFullInvert(invCurrViewProj, currViewProjSL);
sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevViewProjSL);
//                             ↑ inv(curVP) × 0 = 0
```

### 成因

`FrameGen.h:232`：

```cpp
FrameBuffer frameBufferCopy{};   // 值初始化 → 全零
```

`Unmap` 钩子每帧把游戏 perFrame 缓冲拷进它。但**游戏并非每帧都写
`CameraPreviousViewProjUnjittered`**（D3D11 `WRITE_DISCARD` 之后内容未定义），
于是 `prevVP` 读成零 → `camValid` 判据失败。

### 与心跳的咬合（三条独立读数指向同一件事）

| 心跳里的值 | 含义 | 出处 |
|---|---|---|
| `clipDev=1.000000` | `max\|clipToPrev−I\|` = 1.0，**零矩阵的指纹**（`\|0−I\|` 恰为 1） | `devOf` lambda，Streamline.cpp:486 |
| `prevVP=1.0000` | `max\|prevVP−I\|` = 1.0，**`prevVP` 是零矩阵** | 同上 |
| `pos=(0.0,0.0,1.0)` | `CameraPosAdjust` 是未写入的残留值 | Streamline.cpp:562 |
| `curVP=2.0001`（vs 有效帧的 `15.0006`） | 两组**不同的**缓冲数据在交替 | 同上 |

按 19 条心跳统计：`clipDev=1.0`（无效）约 8 条，**占 ~42%**。

---

## 三、v0.64 修了什么

**核心（`Streamline.cpp`，`CheckFrameConstants` 内）**：校验三个矩阵的幅度，
任一无量级（零 / NaN / Inf）→ 把 `clipToPrevClip` 钳成**单位矩阵**。

```cpp
auto finiteMag = [](const sl::float4x4& m) -> float {
    float mx = 0.0f;
    for (int r = 0; r < 4; ++r) {
        const float v[4] = { m[r].x, m[r].y, m[r].z, m[r].w };
        for (int k = 0; k < 4; ++k) {
            const float a = v[k] < 0.0f ? -v[k] : v[k];
            if (!(a <= 1.0e6f)) return 1.0e30f;   // NaN/Inf 也走这里
            if (a > mx) mx = a;
        }
    }
    return mx;
};
const bool camValid = finiteMag(currViewProjSL) > 1.0e-6f &&
                      finiteMag(prevViewProjSL) > 1.0e-6f &&
                      finiteMag(c.clipToPrevClip) > 1.0e-6f;
if (camValid) { ++diag.camValid; }
else {
    ++diag.camInvalid;
    c.clipToPrevClip[0] = { 1.f, 0.f, 0.f, 0.f };   // ...→ 单位矩阵
    c.prevClipToClip = c.clipToPrevClip;
}
```

**为什么单位矩阵是对的**：无效帧出现的场合（装载 / 过场 / 菜单）**相机本来就没动**，
单位矩阵正好是正确答案；世界帧偶发无效只会丢一帧的相机运动，
远好于画面整体崩坏。

**配套三件**：

1. **`reset` 边沿并入相机断裂**：
   `c.reset = (menuEdgeUp || camEdgeDown) ? eTrue : eFalse;`
   相机断裂与菜单边沿同类 —— 旧矩阵建立的重投影历史已失效，丢**一次**即可
   （边沿触发，不是每帧，v0.59 的教训）。
2. **心跳新增 `cam(ok/inv)=N/M`**：一眼看出无效比例。
3. **VERDICT 新增分支**：无效占比 > 25% 时直接打印
   `camera data INVALID on N of M frames -> ClipToPrevClip was zero and got clamped to identity (that IS the flicker source)`。

**6 处改动 / 2 文件**，`tools/add_xray_v064.py`（断言式、幂等 marker
`v0.64: camera-data validity`），备份 `src/*.bak-20260917-221155`。

---

## 四、关于"进不去游戏"

**日志显示游戏引擎实际已经在世界里跑**：

| 证据 | 值 |
|---|---|
| 世界帧计数 | `world=541` 持续累加 |
| 常数提交 | `consts ok=540 fail=0`（零失败） |
| 相机位置 | 出现过真实世界坐标 `(-243.0,-415.3,118.6)`、`(-209.4,-406.7,151.4)` |
| 帧率 | 稳定 30 fps，全程 **无** `LONG FRAME` 记录 |
| 看门狗 | frames 涨到 1252，`silent` 最大 28 ms，**无 STALLED** |
| 崩溃记录 | 只有装载期 4 次 first-chance AV（NGX 加载，非致命） |

**⇒ 这不是卡死。** 用户看到的"卡在加载界面"很可能是
**DLSS-G 输出的错误画面**：零矩阵重投影后每 4 帧里有 3 帧是垃圾，
残影与加载画面混杂，看起来就像"加载没完成"。

**⇒ 这一条我没有 100% 证明**，但它与"闪烁"是同一个根因，
修掉零矩阵后画面应当恢复。**如果修完仍然进不去世界**，
日志会给出新信息（见下一节）。

---

## 五、下次运行看什么

跑法：主菜单停 5 秒 → 回车进世界 → **走一走、转一转** → 退出。

| 看什么 | 修好后 | 若不对，说明 |
|---|---|---|
| `cam(ok/inv)` | 无效占比低 | 占比仍 >20% ⇒ 引擎侧 prev-VP 更新不稳，需在 `Unmap` 钩子加"源侧防护"（拒绝写入零缓冲，保留上份有效快照） |
| `clipDev` | 大部分为 0 或合理的非零 | —— |
| 画面 | 加载界面不闪、能进世界 | —— |
| `dt min/avg/max` | avg ≈ 25.2 ms（159 flip cap 下的 39.75 真实 fps） | 若 avg 明显高且**在飘**（min/max 差几毫秒）⇒ GPU 真受限，按 `FIX_PACING_2202.md` 第五节降负载 |
| `Reflex FLIP cap` | `159 fps (6289us) - panel 160Hz` | —— |

**注意**：`MenuDisableFrameGen` 至今未被验证。若本次运行主菜单期间
出现 `MENU EDGE open=1` 且 `presentedMenu` 直方图塌到 1，才算它生效。

---

## 六、文件清单

| 文件 | 说明 |
|---|---|
| `src/Streamline.h` / `src/Streamline.cpp` | v0.64 改动（6 处） |
| `src/*.bak-20260917-221155` | 改动前备份 |
| `tools/add_xray_v064.py` | 断言式补丁（干跑 / `--apply`） |
| `tools/read_xray_log.py` | 新增相机数据有效性判定 |
| `build/NINJA/DynamicShaderFrameGen.dll` | `b4410b9aa4ad2c6d5a44f793a3b9e77b`（1252352 B） |

部署位置 `E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\`，
与构建产物 **md5 一致**（POST_BUILD 自动同步）。
