# v0.61 — [XRAY] 自诊断仪器（"下一次开游戏就能看出问题在哪"）

日期：2026-09-17 21:35
产物 md5：`d9dd81dc96f7506f4b9d0d73a3a8e59a`（1244160 B）
备份：`D:\workbuddy2\backup\xray_diag_20260917_213333\`

---

## 1. 这一轮要解决的不是"闪"，是"看不见"

前几轮反复卡在同一件事上：**改了三处、跑一次、还是闪，但日志里没有一条能把结论说死**。
具体缺三样东西：

| 缺的东西 | 代价 |
|---|---|
| 不知道这次跑的是哪份 DLL | 曾整整一轮在怀疑"部署没生效" |
| 不知道游戏读的是哪份 INI | 曾改错层（My Games vs MO2 profile），白干一轮 |
| 四条探针各自成行、节奏不同（MOTION/CAM 每 240 帧、constants 每 120 帧、presented 变化即打） | 无法回答"闪的那一刻，这几个值分别是什么" |

v0.61 把这三样一次补齐，并让**插件自己在日志里给出结论**。

---

## 2. 新增的日志行（全部以 `[XRAY]` 开头，一次运行即可 grep）

| 行 | 时机 | 证明什么 |
|---|---|---|
| `[XRAY] RUN START <build> - dll=<路径> mtime=… size=…B` | 启动 | **游戏实际加载了哪份 DLL**（构建树 / mods 目录 / overwrite 一望而知） |
| `[XRAY] INI: cwd=… file=… size=…B` | 启动 | **哪份 INI 赢了**（路径是相对进程 CWD 的，这正是以前踩的坑）<br>读不到时另有 `[XRAY] INI MISSING` |
| `[XRAY] env: virtual=WxH physical=WxH@Hz swapchain=WxH render=… dpiAware=…` | 首个 DLSSG 帧 | **呈现链三件套是否对齐**；`virtual != physical` 直接指出进程被 DPI 虚拟化（2560 那种数字从此有解释） |
| `[XRAY] MENU EDGE open=? serial=? presentedBefore=? reset=? consts(ok/fail)` | 菜单开/关的那一帧 | 菜单切换的**时间点 + 切换前的倍率**，用来判断菜单处理有没有真的介入 |
| `[XRAY] serial=… menu=… world=… edges=… resetTrue=… \| consts ok/fail/lastR \| presented all=… world=… menu=… \| real=…ms \| mvec=… flags=… \| jitter=… clipDev=… curVP=… prevVP=… \| pos=… prevPos=…` | 每 240 真实帧 | **所有决定性数字在同一帧上**（原来分散在四条不同节奏的探针里） |
| `[XRAY] VERDICT: …` | 每 240 真实帧 | **插件自己下结论**，不用人再算 |

被**删除**的旧探针（避免重复与交错）：`MOTION probe`、`CAM probe`、`RESET probe`、
`constants: ok={} fail={} lastR={} serial=`。
`slSetConstants` 失败改为**只打第一条**（原来每帧刷屏淹没日志），总量走心跳。

新增列 `real=…ms` 的作用：它是**区分两种"闪"的唯一一列** ——
`real` 稳定 + `clipDev` 非零 ⇒ 重投影本身错；`real` 抖动 ⇒ pacer 失节拍。
其它所有列在两种情况下都可能干净。

---

## 3. 一键读日志（把日志翻译成结论）

```
D:\Modding\DynamicShaderFrameGen\read_log.bat
```

等价于：

```
python D:\Modding\DynamicShaderFrameGen\tools\read_xray_log.py [日志路径]
```

它做 7 段输出 + 一个总结，逐条给 `[OK]/[注意]/[问题]`：

1. **run identity** —— 还带一个版本自检：日志里若出现 `MOTION probe` / `RESET probe` /
   旧 `constants: ok=` 串，说明**跑的不是 v0.61**（旧 DLL 生效）
2. **显示/DPI 对齐** —— swapchain ≠ 显示模式则直接判定"呈现链问题"
3. **菜单切换时间线**
4. **心跳解析**（含 presented 直方图表格）+ 三条派生判定：
   constants 是否被拒 / reset 是否边沿触发 / 菜单与世界各自的众数倍率
5. **插件自判 VERDICT 汇总**
6. **已知错误签名扫描**（auto-disabled、跳过、降档、`[E]` 等）
7. **Transfusion 侧交叉验证**（自动读 `DLSSG-Transfusion.log`：`reset` 序列、`clipToPrev`、Jitter）

退出码：`0` 无问题，`1` 有 `[问题]`，`2` 日志读不到。

---

## 4. 测试流程（一次就够）

1. 重启游戏（配置没有改，无需重编译）
2. **主菜单停 10 秒**（计时：心跳每 240 真实帧一条，约 6~7 秒；菜单样本要 > 60 帧）
3. 按回车进世界，走一段、转视角，约 30 秒
4. 退出游戏，双击 `read_log.bat`

然后**只回答一个问题**：这次还闪不闪、闪的是菜单还是世界。

### 日志里怎么判定（不用读全文，只看这几列）

| 判据 | 正常 | 异常含义 |
|---|---|---|
| `consts fail=` | `0` | >0 且 `lastR=27` ⇒ 帧槽不推进（v0.58 那类缺陷复发） |
| `resetTrue` vs `edges` | 接近（边沿触发） | `resetTrue` ≈ 总帧数 ⇒ 每帧重置（v0.59 未生效） |
| `presented … menu=` 众数 | `1`（被节流） | 仍等于世界倍率 ⇒ 运行时没理会 `eEnableFullscreenMenuDetection` |
| `presented … world=` 众数 | `= accepted`（FPS probe 里的 `accepted`） | 不等于 ⇒ MFG 没按接受值输出 |
| `real=` | 稳定（≈1000/真实fps） | 抖动 ⇒ pacer 失节拍 |
| `clipDev` | 移动时 ≠ 0 | 移动中仍 ≈ 0 ⇒ 相机矩阵没喂进去 |

---

## 5. 改动清单

| 文件 | 改动 |
|---|---|
| `src/main.cpp` | `[XRAY] RUN START` 横幅：`GetModuleHandleExA` + `GetModuleFileNameA` + `GetFileAttributesExA` 取加载模块路径与写入时间 |
| `src/FrameGen.cpp` | INI 解析前记录 CWD + 路径 + 大小；补 `[XRAY] INI MISSING` 分支 |
| `src/Streamline.h` | 新增嵌套 `struct Diag`（计数器 + presented 直方图 + 标志/帧号快照）与成员 `Diag diag;` |
| `src/Streamline.cpp` | 新增匿名命名空间函数 `GameMenuOpenNow()`（唯一菜单判定，reset 与计数器共用）；reset 边沿 + 菜单/世界计数 + `MENU EDGE`；折叠 MOTION/CAM 探针为单条心跳 + 自判 VERDICT；constants 计数进 `diag` 且只打首条失败；`DLSSG flags` 行加 `raw=` 与 `[XRAY] env` / `diag active`；presented 采样按菜单/世界分类入直方图；新增 `#include <chrono>` 与 `real=` 列 |
| `tools/add_xray_diag_v061.py` | 断言式补丁脚本（9 处锚点，各 `count==1`；幂等 marker 先查；逐文件保留行尾；备份 + 回读） |
| `tools/read_xray_log.py` | 日志→结论 的读取器 |
| `read_log.bat` | 一键跑读取器 |

行尾：`Streamline.h` / `main.cpp` 保持 CRLF，`Streamline.cpp` / `FrameGen.cpp` 保持 LF（脚本按文件自动识别，未污染）。

## 6. 环境顺带核实

MO2 `profiles\DIPEI\modlist.txt` 里有三份 DFG，实际只启用了一份：

```
  8:-DynamicShaderFrameGenDlss5-v047b-20260911     (禁用)
 20:+DynamicShaderFrameGen                        (启用 ← 本次部署目标)
134:-DynamicShaderFrameGenNR                      (禁用)
```

其余两份 DLL 仍在 mods 目录里（`c99d8968…` / `61542d0c…`）。**若哪天启用它们且排在本体之后，
MO2 的 VFS 会让旧 DLL 覆盖新的。** 以后不用再靠猜——`[XRAY] RUN START` 第一行就是答案。

## 7. 诚实边界

- **这一轮没有改任何行为**。v0.59（reset 边沿）与 v0.60（fullscreen menu flag）仍然在位，仍然
  **未被验证**。v0.61 只负责让下一次运行把它们的有效性说清楚。
- `[XRAY]` 行本身不产生画面影响（每 240 帧一行 + 启动 3 行）。
- 若下一次运行 `VERDICT` 报 `clean` 而画面仍闪，说明缺陷在现有仪器**之外**——
  届时 `real=` 与 `clipDev` 会给出方向（pacer 还是重投影），再决定下一刀。

## 8. 回滚

```
copy /Y "D:\workbuddy2\backup\xray_diag_20260917_213333\Streamline.cpp.bak" "D:\Modding\DynamicShaderFrameGen\src\Streamline.cpp"
copy /Y "D:\workbuddy2\backup\xray_diag_20260917_213333\Streamline.h.bak"   "D:\Modding\DynamicShaderFrameGen\src\Streamline.h"
copy /Y "D:\workbuddy2\backup\xray_diag_20260917_213333\main.cpp.bak"       "D:\Modding\DynamicShaderFrameGen\src\main.cpp"
copy /Y "D:\workbuddy2\backup\xray_diag_20260917_213333\FrameGen.cpp.bak"   "D:\Modding\DynamicShaderFrameGen\src\FrameGen.cpp"
```
然后 `build_vs.bat` 重编译。
