# v0.55 验证清单 — 重启游戏后照这个看

状态：**已部署，未验证**。`patchFlipMetering=true` 是本次唯一的行为改动，
v0.55 只是把"是否真在插帧"的采样间隔从 240 帧（≈6.2 秒）改成"头 8 帧 + 变化即打"，
否则你退出得比第一次采样还早，永远看不到结论。

---

## 一、必须先做的一步

**完全退出游戏再重开。** 两个改动都是载入期读取的：

- `DLSSG-Transfusion.json` 的 `patchFlipMetering` → provider 载入期消费
- `DynamicShaderFrameGen.dll` v0.55 → 进程载入期加载

不重启 = 还是在跑旧状态。

---

## 二、进游戏后看三行日志

### 1. 判决行（最重要）

`Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`

```
[Streamline] DLSSG presented per real frame = N
```

这条现在是**头 8 帧就会打**，而且值一变就打。

| 读到 | 含义 | 下一步 |
|---|---|---|
| `= 4` | **4x 真在出帧** — 成功 | 看画面还闪不闪 |
| `= 1` | 选项被接受但**一帧没插** | 见第四节"如果还是 1" |
| `1` 和 `4` 交替刷 | 两个 pacer 在抢呈现通道 | 见第四节 |
| 这行没出现 | 游戏没走到帧生成阶段 | 先看 `Provider in effect` 那行 |

⚠️ **别再用 `MFG probe: runtime ACCEPTED 4x` 当成功证据** —— 那只证明选项被收下，
不证明有帧被生成。这是前三轮翻车的根源。

### 2. 限帧行（确认 v0.54 仍生效）

```
[Streamline] Reflex render cap = 39 fps (25641us) - 160Hz / 4x => ~156 present fps
```

应出现 `39 fps`。上一次确认过，不该变。

### 3. 闪烁开关（本次新改的那一行）

`D:\ENB-EJ\Skyrim Special Edition\DLSSG-Transfusion.log`

```
NVAPI: Hooked nvapi_QueryInterface (OptiScaler FlipMetering bypass: ENABLED)
```

- `ENABLED` ← **目标**，说明 Ada 缺硬件 flip metering 这一层被绕过了
- 仍是 `DISABLED` → 说明这个键没被消费，告诉我，我从别处下手

---

## 三、顺带看这个（节奏的量化指标）

`DLSSG-Transfusion_perf.csv` 与日志里的 `[PERF]` 行：

```
[PERF] 4x | Kernel: Ada | FPS: 34.6 (28.89ms) | Jitter: 16.31ms | 1% Low: 30.8 FPS
```

上一次 **Jitter = 16.31ms ≈ 半个帧长**，是节奏不稳的指纹。
改对了的话这个数应该明显掉下来。

---

## 四、如果还是闪 / 还是 `= 1`，按这个顺序动，**一次只动一个**

1. **`"disableMenuDetection": false`**（JSON）
   你现在是 `true`。Streamline 的 DLSS-G 规范要求菜单/加载/暂停时把
   `DLSSGOptions::mode` 设为 `eOff`，`true` 等于关掉了这层保护。
   改动需重启。

2. **`Ctrl+Alt+3` 降到 3x**（免重启，Transfusion 自带热键）
   3x 要求渲染 53fps，比 4x 的 39fps 富余得多。
   **40 系上 4x 本来就是绕过硬件限制的灰色地带，2x/3x 才是稳的。**

3. **`ReflexFpsLimit` 手动填数字**（INI，免编译）
   当前 `0` = 自动（160/4 → 39）。可试 `40`（正好 160 present，消掉 4fps 缺口）
   或 `30`（更宽松）。

4. **回退到 `Ctrl+Alt+2`（2x）+ `patchFlipMetering=false`**
   回到"确定能跑"的基线，用来判断闪烁到底是插帧倍率问题还是别的。

---

## 五、回滚点

| 对象 | 回滚方式 |
|---|---|
| 插件代码 | `git checkout 79a0ea4`（或整体 `git checkout -- .`） |
| 插件二进制 | 已备份在 `/d/workbuddy2/backup/DynamicShaderFrameGen_flicker_20260917_163103/deployed_v053.dll` |
| JSON | `/d/workbuddy2/backup/transfusion_json_20260917_163940/DLSSG-Transfusion.json` |
| 代理 DLL | **不要动**（见下） |

---

## 六、已知但未解释 / 不要动的东西

- **`version.dll` 与 `dinput8.dll` 两个副本都在进程里**（`crash.log` 模块表实锤）。
  但活跃的只有一个（`Loaded as:` 与 `Patch worker started` 各 1 条），另一个被识别为
  同族副本且**故意不补**（`wrapperCandidate=0 wrapperPatched=0` = 防双补丁守卫）。
  **`SkyrimSE.exe` 既不导入 `version.dll`、延迟导入表也是空的，它却被加载了 ——
  加载者未定位。** 但当前组合已被证明能工作，**在闪烁定性之前不要改名/删除**。
- **别在插件菜单里点 "Save to INI"**：MO2 下会写进 `overwrite\`，优先级高于 mod 目录，
  会长期盖住模板（而且只写键值、丢注释）。
