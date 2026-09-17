# 下一次启动：读什么、判什么（双代理实例修复后）

状态：**只改了部署文件，源码一行未动。** v0.56（extent 修复）与 v0.57（mvecScale 可切换）**保留原位，未回滚。**

---

## 本轮改了什么

```
D:\ENB-EJ\Skyrim Special Edition\version.dll  ->  version.dll.off
```

只留 `dinput8.dll` 一份。**没有改任何源码，没有重新编译，没有动 INI，没有动 JSON。**

原因见 `D:\Modding\DLSSG-Transfusion\DEPLOY_NOTE.md` 的《双代理双实例事故》一节。一句话：
同一个包被 `cp` 成两个代理名放在游戏根目录，于是 **Transfusion 每个会话被加载两次**，
两个补丁 worker 互相踩 —— 这是"同一份配置，一次崩、一次卡死"的唯一解释。

**备份**：`D:\workbuddy2\backup\transfusion_proxy_dup_20260917_182050\`（含两个代理 + 当时的 JSON）

---

## 启动后读四项

### ① `DLSSG-Transfusion.log` 的横幅身份（最先看这个）

```
D:\ENB-EJ\Skyrim Special Edition\DLSSG-Transfusion.log
```

前几行应该还是 `Loaded as: dinput8.dll`，但**整个日志不应该再出现两条横幅**。
更可靠的做法是搜 `Patch worker started`：

```bash
grep -c "Patch worker started" "D:/ENB-EJ/Skyrim Special Edition/DLSSG-Transfusion.log"
```

- **`1`** = 双实例已消除，本轮修复生效
- **`2`** = 还有第二个代理（查游戏根目录里 540672 字节的同尺寸文件）

再看 `LoadLibrary` 是否还是**每条记两遍**（两条 path 写法一虚拟一真实）：
只剩一遍 = 单实例。

### ② `DynamicShaderFrameGen.log` 有没有过 `slSetD3DDevice`

```
C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log
```

18:05 那次卡死，日志停在 `Initialized OK`，**没有** `D3D11/D3D12 device set`。

- 出现 `D3D11/D3D12 device set` ⇒ 卡死点已通过
- 仍停在 `Initialized OK` ⇒ 还在 `slSetD3DDevice` 里（走下面第 4 节）

同时看 v0.56/v0.57 的三个新标记（**它们从来没在游戏里出现过**，这是第一次）：

```
[Streamline] DLSSG tag dims:      <- 必须读 2560x1440（v0.56 修的就是这个）
[Streamline] DLSSG options dims:
[Streamline] MOTION probe:
```

`DLSSG tag dims:` 若是 `2560x1440` ⇒ v0.56 的 extent 修复在真实运行中生效。

### ③ Transfusion 有没有再报 `already patched`

```bash
grep -n "already patched" "D:/ENB-EJ/Skyrim Special Edition/DLSSG-Transfusion.log"
```

**修好后这条不该再出现。** 它是双实例最硬的判据（磁盘文件 md5 与原始包一致，
补丁只能来自同进程的另一个实例）。

### ④ 帧生成是否真在跑（运行时自己说的，不是估算）

```bash
grep -n "actual presentation count\|Applied fixed multiplier\|\[PERF\]" \
  "D:/ENB-EJ/Skyrim Special Edition/DLSSG-Transfusion.log"
```

目标：`DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)`

---

## 如果还不行：一次只动一个变量

**不要重建 DFG。** `CMakeLists.txt:105-121` 有 POST_BUILD，每次链接都会用仓库里的
INI 覆盖线上 INI —— 会把 A/B 用的改动冲掉。

按顺序，每次只改一项，改完直接重启游戏：

| 顺序 | 改什么 | 怎么改 | 为什么是它 |
|---|---|---|---|
| 1 | `patchFlipMetering` | 线上 `DLSSG-Transfusion.json` 里 `true` → `false` | v1.4.1 的**官方默认就是 false**（README: *"patchFlipMetering is now disabled by default"*）。它会在 NGX 初始化路径上装一个递归的 NVAPI 解析器钩子，而 18:05 卡死的正是 NGX 初始化所在的 `slSetD3DDevice` |
| 2 | `multiplier` | `4` → `2` | 排除 4x 的显存/带宽因素（4080 SUPER 上 4x 在 2560x1440 是重负载） |
| 3 | `blackwellTransfusion` | `true` → `false` | Ada 上关掉内核移植；副作用是 >2x 会失效，但能确认崩溃与它是否相关 |

### 已知的次级风险（记录在案，暂不动）

本机 Streamline 运行时是 **2.13**，而 DFG 是拿 **SDK 2.12 头文件**编译的，
Transfusion v1.4.1 声明的兼容目标是 **2.14+**。实测这个 2.13 interposer：

```
slGetPluginFunction   -> 未导出     <- Transfusion README 的头号特性依赖它
slSetData             -> 未导出     <- 但它日志声称 hook 成功
slDLSSGSetOptions     -> 未导出
```

三个版本号互不相同。这是结构性隐患，但**属于下一轮**（一次只改一个变量）。

---

## 回滚

**代理（撤销本轮的改动）**

```bash
cp /d/workbuddy2/backup/transfusion_proxy_dup_20260917_182050/version.dll \
   "/d/ENB-EJ/Skyrim Special Edition/version.dll"
```

**DFG 源码**（本轮未改动，仅备查）

```bash
cd /d/Modding/DynamicShaderFrameGen
git checkout ec80060 -- src/     # 最后一次「确认能启动」的版本（v0.55）
git checkout 135c4e4 -- src/     # 只含 v0.56 extent 修复
```
改完必须重建；重建后 POST_BUILD 会自动覆盖线上 DLL 与 INI。

---

## 本轮排除掉的方向（不必再查）

- **磁盘污染**：线上 `Shaders\Upscaling\Streamline\` 的 10 个 DLL 与仓库**逐字节一致**；
  NGX 模型 `.bin` 的 mtime 仍是 08-28，未被改
- **DFG 往 interposer 写代码**：源码扫描只改虚表槽与游戏函数；
  对 interposer 只有 `LoadLibraryW` + `GetProcAddress`（纯读）
- **POST_BUILD 换掉运行时 DLL**：仓库 `Shaders` 里那些 DLL 是 08-29 的原始文件，内容从未变
- **`c.mvecScale` 的耦合**：v0.56 改了 extent 后，v0.57 已把它做成 INI 一行可切换（默认零变化）
