# DynamicShaderFrameGen v0.50 — 多倍帧生成（RTX 40/30/20）部署与验证

生成时间：2026-09-17
工程路径：`D:\Modding\DynamicShaderFrameGen`
备份：`D:\workbuddy2\backup\DynamicShaderFrameGen_mfg_20260917_121051\source_full.tar.gz`
Git 提交：`6729bcd` v0.50: MFG max-frames override

---

## 一、已完成的部分（代码层）

### 改动的文件

| 文件 | 改动 |
|---|---|
| `src/Streamline.h` | 声明 `ApplyMfgOverride()` |
| `src/Streamline.cpp` | 新增 `ApplyMfgOverride()`；`PostDevice()` 里改为 `hwMax` + 调用覆盖；`SetDLSSGOptions()` 里 `effectiveMax = max(hardware max, override)` |
| `src/FrameGen.h` | 新增 `Settings::mfgMaxFramesOverride` |
| `src/FrameGen.cpp` | 读取 INI `MFGMaxFramesOverride`（0-5）；`DLSSGFramesToGenerate` 上限 4→5 |
| `src/ImguiMenu.cpp` | MFG 倍率选项 3 档→5 档（2x-6x）；新增 `MFG Max Override` 滑块 |
| `src/version.rc` | 0.48.0.0 → 0.50.0.0 |
| `CHANGELOG.md` | 新增 v0.50 条目 |
| `SKSE/Plugins/DynamicShaderFrameGen.ini` | 新增 `MFGMaxFramesOverride`；Provider→1 |

### 构建产物

- `D:\Modding\DynamicShaderFrameGen\build\NINJA\DynamicShaderFrameGen.dll`（1201152 字节）
- 自动部署到 `E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\`
- MD5 一致：`27ccc313af5732c7e2075fd475efef05`
- 编译 EXITCODE=0，无错误

### 当前生效配置

```ini
Provider=1                 ; DLSSG 路径（多倍帧生成只在这条路径上）
DLSSGFramesToGenerate=3    ; 4x
MFGMaxFramesOverride=3     ; 抬高上报上限到 3（=4x）
```

### 核心逻辑说明

问题根源：Streamline 运行时在 Ada 及更早架构上报 `numFramesToGenerateMax = 1`，
而旧代码 `clamp(INI值, 1, 硬件上限)` 把一切请求压到 2x。日志证据：`dlssgMax=1 req=3`。

v0.50 的行为：

```
ApplyMfgOverride(hwMax):
    if override == 0  -> 不动（严格跟随硬件，50 系仍可 4x，零倒退）
    if override > hwMax -> 抬到 override（解锁路径）
    if override <= hwMax -> 不动

SetDLSSGOptions:
    effectiveMax = max(1, max(hardwareMax, override))
    numFramesToGenerate = clamp(INI, 1, effectiveMax)
```

---

## 二、还差的部分（内核层）

**这一半无法用源码解决。** `nvngx_dlssg.dll` 里没有 Ada/Ampere/Turing 的内核，
抬高上限只是让请求发得出去，内核不在 → 高倍率无内核可执行。

需要外部内核解锁器。已选定 **DLSSG-Transfusion v1.4.1**。

### 为什么是 Transfusion

1. **只 patch 进程映射内存，不改磁盘 DLL** — 不与插件的 swapchain 接管冲突
2. 你的 `nvngx_dlssg.dll` 是 **310.8.0.0**，在其支持列表内（3.10.1 - 3.10.9）
3. 热键 `Ctrl+Alt+2..6`，与插件 `Home` 键不冲突
4. 默认 `multiplier: 4` + `blackwellTransfusion: true`，正好对上 4x

### 已下载并校验

- 源：`https://github.com/TonyJoaca/DLSSG-Transfusion/releases/download/1.4.1/DLSSG-Transfusion-v1.4.1.zip`
- SHA256 校验**通过**（与官方发布值一致）
- 解压位置：`D:\Modding\DLSSG-Transfusion\extracted\`
- 已改名为 `version.dll` 的安装包：`D:\Modding\DLSSG-Transfusion\ready\`

---

## 三、待确认：游戏目录

Transfusion 必须放在**游戏主程序 exe 同级目录**。需要确认你的 MO2 实例
（mods 指向 `E:\EJ\mod\mods\`）实际关联的游戏目录。

候选（本机存在多个副本）：
- `D:\EJ-1.0\SkyrimSE\`
- `E:\ej-all in one\SkyrimAe\`
- `E:\ENB-EJ\Skyrim Special Edition\`
- `D:\ENB-EJ\Skyrim Special Edition\`

**部署前必须确认哪一个是当前 MO2 实际启动的**，否则放错位置不生效。

### 部署步骤（确认目录后执行）

1. 把 `D:\Modding\DLSSG-Transfusion\ready\version.dll` 复制到 **游戏 exe 同级目录**
2. 把 `DLSSG-Transfusion.json` 复制到同一目录
3. 检查该目录**是否已存在 `version.dll`** — 若存在说明被别的模组占用：
   - CET / OptiScaler / 某些 SKSE 插件会用 `version.dll`
   - 存在冲突时改用 `dinput8.dll` 或 `winmm.dll`（把 DLL 重命名即可）
4. 启动游戏

---

## 四、验证清单

### 步骤 1：先验证插件本身（不装 Transfusion 就跑一次）

启动游戏进主菜单，等 10 秒，然后立刻看：

```
C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log
```

（注意：每次启动覆盖，必须在游戏还开着时读）

**必看的行：**

| 日志行 | 期望值 | 含义 |
|---|---|---|
| `Config loaded: ... Provider=1` | `Provider=1` | 已切到 DLSSG 路径 |
| `DLSS-G supports up to Nx frame generation` | N=2 | 硬件原生上报（40 系） |
| `MFG override ACTIVE: raising reported max 1 -> 3` | 出现这行 | **覆盖生效**（核心验证点） |
| `FPS probe: real=... \| DLSSG ... \| dlssgMax=3 req=3` | `dlssgMax=3` | 上限已抬高（之前是 1） |
| `DLSSNR: ... status=initialized` | `initialized` | NGX Core 没被抢 |

**判读：**
- `dlssgMax=3 req=3` + 画面正常 → 请求链打通，可以进行步骤 2
- `dlssgMax=3 req=3` + **黑屏/卡死** → 正是预期的"内核缺失"表现，装 Transfusion 解决
- `dlssgMax=1` 仍然出现 → 覆盖没生效，回传日志给我
- `status=not-probed` 或 `0xBAD00007` → NGX Core 被抢（检查是否有 ENB Anti-Aliasing）

### 步骤 2：装 Transfusion 后再跑一次

同样的日志 + 额外看：

```
<游戏目录>\DLSSG-Transfusion.log
```

| 检查项 | 期望 |
|---|---|
| Transfusion 日志出现 | DLL 被加载 |
| 提到 kernel transfusion / sm_120 → sm_89 | 内核转换成功 |
| 出现 "fails closed to native 2x" | **失败回退**，说明 patch 没成功 |
| `FPS probe` 里 `present~` | 应约为 `real × 4`（不是 ×2） |

### 步骤 3：游戏内确认

- `Ctrl + Alt + O` 开 Transfusion 叠加层 → 应显示当前倍率与 FG 状态
- `Ctrl + Alt + 4` 锁 4x，`Ctrl + Alt + 3` 锁 3x
- `Ctrl + Alt + 6` 冲 6x（注意：6x 下真实渲染帧会大幅下降）

---

## 五、风险与注意事项

| 风险 | 说明 |
|---|---|
| **显存** | 4x 起需要额外显存；8GB 卡建议 2x/3x。出现 "Out of Video Memory" 就降倍率或关后台硬件加速程序 |
| **伪影** | 倍率越高伪影越明显。Transfusion 的 `qualityValidWarp` 已开，能减电线/栅栏撕裂与 HUD 重影 |
| **UIR** | Skyrim 是单表面管线（无独立 UI 缓冲），`forceUiRecomposition` 保持 `false` 正确 |
| **反作弊** | 仅单机使用。Skyrim 无影响，但别把这个思路用到网游 |
| **易碎** | NVIDIA 驱动 / Streamline / DLSS 运行时的 OTA 更新都可能使其失效 |
| **回滚** | 删掉游戏目录的 `version.dll` + `DynamicShaderFrameGen.json` 即完全卸载；插件用 `git checkout b20dae4` 回退 |

---

## 六、回滚命令

```bash
# 回退插件源码
cd /d/Modding/DynamicShaderFrameGen && git checkout b20dae4 -- src/ SKSE/

# 或从备份完整还原
tar -xzf /d/workbuddy2/backup/DynamicShaderFrameGen_mfg_20260917_121051/source_full.tar.gz -C /d/Modding/DynamicShaderFrameGen
```
