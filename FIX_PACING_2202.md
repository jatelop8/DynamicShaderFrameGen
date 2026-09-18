# v0.63 — 限速器作用面搞错（"越来越闪" + 9.75fps 的同一个根因）

**结论**：`ReflexOptions::frameLimitUs` 限的是**上屏 flip 的节拍**，不是渲染帧率。
v0.54 按"渲染帧率"反推（`刷新率 / 倍数 - 1`），等于把 flip 节流到 39/s；而 DLSS-G 每
真实帧要发 4 个 flip ⇒ 渲染侧被压成 **39/4 = 9.75fps**。每 4 个上屏帧只有 1 个是真的，
另 3 个要跨越最长 102ms 的世界运动去重投影 ⇒ 静止时轻微微闪，**一动就崩**。

**修法**：`frameLimitUs = 刷新率 - 1`（160Hz → 159fps flip 上限 ⇒ ~39.75 真实 fps）。
因为上限仍然低于刷新率，v0.54 想解决的"超发"依然不可能发生。

---

## 一、证据链（2026-09-17 21:53:46–21:54:31 那次运行）

| # | 观测 | 出处 |
|---|---|---|
| 1 | `capUs=25641` **每一条心跳都相同**（=25.641ms=39.0fps） | `DynamicShaderFrameGen.log` 17 条 `[XRAY]` |
| 2 | `dt min/avg/max = 102.10/102.57/103.12ms` | 同上 |
| 3 | `102.56 / 25.641 = 4.0000`（5 位有效数字） | 计算 |
| 4 | `presented per real frame = 4` | `DLSSG state` / Streamline 日志 |
| 5 | perf.csv 连续 65 帧 `102.55 / 102.56 / 102.57` ⇒ **离散度 0.02ms** | `DLSSG-Transfusion_perf.csv` |
| 6 | `160Hz / 4x => ~156 present fps` | `Reflex render cap = 39 fps (25641us)` |
| 7 | 真实帧率 `real=9.7~10.1` 全程不变（菜单与世界都一样） | `[FrameGen] FPS probe` |

**为什么能确定是限速器而不是 GPU 不够**：4K + ENB + 神经渲染的真实负载不可能恰好落在
25.641ms 量子的整 4 倍上（#3），而且 GPU 受限的帧会飘几毫秒，不会 65 帧只差 0.02ms（#5）。
25.641ms 这个量子**就是这份 build 自己交给 Reflex 的 frameLimitUs**（#1），每真实帧 4 个
flip（#4）⇒ 4 × 25.641 = 102.56（#2/#3）。四者互相咬合，没有别的解释能同时满足。

**为什么"越来越闪"**：`dt=102.56ms` 意味着 1 真实帧 / 世界运动 102ms。DLSS-G 要在其中
伪造 3 帧，全部靠运动矢量 / 光流外推。运动量越大，外推误差越大。
站在主菜单（静止）只是轻微微闪，进世界一转身就成片崩坏。

---

## 二、本次改动（15 处 / 7 文件，`tools/add_xray_v063.py`）

| 类别 | 文件 | 内容 |
|---|---|---|
| **P0 根因** | `Streamline.cpp` | `want = refreshRate / capMult - 1.0` → `want = refreshRate - 1.0`；`capMult` 只留作日志 |
| **P0 根因** | `Streamline.cpp` | 日志格式串改为 `Reflex FLIP cap = ... flips per real frame => ... presented fps (real = cap/flips)` |
| **P0 根因** | `Streamline.cpp` | v0.54 那段注释整体改写为 v0.63（原文写的是错误模型，留着会再次误导） |
| **P0 根因** | `DynamicShaderFrameGen.ini` | v0.54 注释块 → v0.63；新增 `MenuDisableFrameGen=1` |
| **P1 菜单闪** | `Streamline.h/.cpp` | `GameMenuOpenNow` 从匿名 namespace 引出为 `Streamline::MenuOpenNow()`（**不复制判断逻辑**，保持单一实现） |
| **P1 菜单闪** | `DX12SwapChain.cpp` | `menuBlock` 分支：菜单开着就不向 DLSS-G 提交，走已有的直通拷回路径；**并把 `dlssgFailCount` 清零**（否则菜单里待满 ~2s 会撞上 `>120` 把插帧整个自动关掉，Home 也救不回） |
| **P1 菜单闪** | `FrameGen.h/.cpp` + `ImguiMenu.cpp` | 新 INI 键 `MenuDisableFrameGen`（默认 1，0 = 旧行为，**不用重编译就能回退**） |
| **探针完整性** | `DX12SwapChain.cpp` | 看门狗：`frames >= 60` 才允许打 `RENDER THREAD STALLED` |
| **探针完整性** | `Streamline.cpp` | VERDICT：菜单分支加 `diag.menuOpenNow` 门控 |

### 两个探针缺陷（都是"探针自己说谎"，已修）

1. **看门狗在装载期误报**：21:54 那次在约 20s 装载里 `frames` 恒为 1、`stage` 恒为
   `d3d11 Wait`，看门狗连打 **19 行** `RENDER THREAD STALLED`，全是假警报。
   现在要求渲染线程"曾经跑顺过"（`frames >= 60`）才允许报卡死；未达标只记 `silent`。
2. **VERDICT 在菜单关闭后仍永久复读**：它读的 `diag.menuFrames` 是**累计值、从不复位**，
   所以 `menuOpen=0` 且 `world` 已在增长时仍一直打印
   `PROBLEM menu still generates 4 frames/real frame`。现在加了 `diag.menuOpenNow` 门控。

---

## 三、下次运行的判定标准（一次就能定案）

跑法：进主菜单停 10 秒 → 按回车进世界 → **走一走、转一转**（这一步才是"越来越闪"的检验）
→ 退出。然后双击 `read_log.bat`。

| 看什么 | 修好应该是 | 没修好的话 |
|---|---|---|
| `[Streamline] Reflex FLIP cap` | `159 fps (6289us) - panel 160Hz` | 仍是 `39 fps (25641us)` |
| `dt min/avg/max` | **≈ 25.2ms 附近**（若 GPU 不够则飘到 30~50ms，但仍远小于 102） | 仍是 `102.56` |
| `[FrameGen] FPS probe: real=` | **≈ 39**（或 GPU 受限的 20~39） | 仍是 9.7~10 |
| 心跳 `capUs` | `6289` | 仍是 `25641` |
| VERDICT | `clean: ...` 或世界那条 | 仍是菜单那条 |
| 主菜单 | 不闪（FG 在菜单里被关掉了） | 仍闪 |
| 看门狗 | 装载期不再出现 `STALLED` | 又打了 19 行 |

**残余量怎么读**：如果 `dt avg` 落在 25.2ms 附近 ⇒ 限速器一解除就到位了。
如果 `dt avg` 明显大于 25.2ms 且**飘**（`min/max` 差几毫秒）⇒ 此时才是真 GPU 受限，
按下面的杠杆降负载。

---

## 四、还没修的那一件事（和上面无关，别混在一起）

`DLSS-G flags=0x10` **从未到达运行时**：

```
21:54:06.810  Option C active: stripped eEnableFullscreenMenuDetection from DLSS-G options
              (game flags=0x00000010 -> 0x00000010)
```

剥前剥后**完全相同**，说明是 Transfusion 中间层干掉的，插件侧怎么设都没用。
本次改动用"菜单期间不提交"绕过了它（行为等价于该 flag 的语义），
但**没有**去动 Transfusion（`DLSSG-Transfusion.json` 里 `disableMenuDetection: false` 的
真实语义我没有 Transfusion 源码可以确证，**不猜**）。

另外记录两条未验证的怀疑，仅作线索：
- `DLSSG-Transfusion.json`: `"mode": "fixed"` ⇒ 倍率不自动降档，任何超发都不会自愈。
- `"blackwellTransfusion": true` 而 Transfusion 自己报 `Kernel: Ada` —— Ada 卡走 Blackwell
  路径是否有代价，未验证。

---

## 五、降负载杠杆（仅当第三节显示"真 GPU 受限"时才动，一次只动一个）

1. `NRRenderScale` **1.00 → 0.75**（INI 默认本来就是 0.75，是后来被调到 1.00 的）
   —— DLSS5-NR 的分析分辨率，4K 下 1.00 是全程 4K 分析，FP8 开销最大。
2. `DLSSGFramesToGenerate` / Transfusion `multiplier` **4 → 2**（伪造帧比例减半）。
3. `RenderResolutionScale` 0.44 已是激进值，**不要再降**（越降质量越差且收益下降）。

## 六、回退

```bash
cp D:/Modding/DynamicShaderFrameGen/src/*.bak-20260917-220142 D:/Modding/DynamicShaderFrameGen/src/
cp D:/Modding/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini.bak-20260917-220142 \
   D:/Modding/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini
```
只回退行为不动代码：把部署的 INI 里 `MenuDisableFrameGen=1` 改成 `0`，或把
`ReflexFpsLimit=0` 改成 `39`（旧值），**都不用重编译**。

## 七、文件

| 文件 | 内容 |
|---|---|
| `tools/add_xray_v063.py` | 15 处断言的补丁脚本（幂等 marker `v0.63`，重跑会被拒） |
| `src/*.bak-20260917-220142` | 改动前备份 |
| `build/NINJA/DynamicShaderFrameGen.dll` | md5 `6c8e3387b10e6e346247a4ad55f20364`，1250304 B |
| 部署 | `E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\`（DLL + INI 均已 md5 校验一致） |
