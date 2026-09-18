# 19:34 修复记录 —— "一直闪"

## 一、先纠正两件事

**1) 拿 open-shaders 当倍率对标是错的。** 它是 2x 级别的上采样+插帧实现，
和这里要的 4x/6x 多帧生成不是一回事。它的架构不能作为依据，这条我撤回。

**2) 我上一轮把 `forceUiRecomposition` 改成 `true` 是错的，已改回 `false`。**

依据是 Transfusion **自己的 README**（不是任何第三方项目）：

```
* Preset A (Single-surface / non-UIR pipeline):
    "Used when games render HUD and 3D world into a single flattened buffer."
* Preset B (UI Recomposition / UIR ON):
    "Used when games tag separate UI and HUDless buffers."
    "Always use Preset B (UIR ON) whenever SUPPORTED BY THE GAME"
```

DFG 的状态是 Preset A —— 运行日志里 `uiFmt=0`（DXGI_FORMAT_UNKNOWN）
就是"根本没有 UI 纹理"的硬证据。强行打开 UIR 等于把一个不成立的前提当成立。

数据也反向印证了：UIR 打开后 **Jitter 从 1.47ms 恶化到 9.07ms**，1% Low 从 39.0 掉到 35.1。

改完后部署 JSON 与 `ready/` 出厂模板 **MD5 完全一致**：`8b6571be7c507d19f6a2c710d8c35a5f`

---

## 二、本次真正改动（核心）

**`DynamicShaderFrameGen.ini`：`MvecScaleOverride` 0.00 → 1.00**

改了两份（源仓库 + 部署副本），MD5 一致：`7099056c633853dd5eaaeb0d171d9021`

改两份是因为 `CMakeLists.txt` 的 POST_BUILD 会把源仓库的 INI
`copy_if_different` 覆盖到 mod 目录 —— 只改部署副本会被下次构建静默回滚。

### 为什么这是"一直闪"的嫌疑

运行日志里这行是病灶：

```
[Streamline] mvecScale = { 1.5000, 1.5000 } (renderScale=0.6667 override=0.00)
```

`mvecScale` 是**归一化因子**，不是放大因子：

- NVIDIA 指南：mvec 已在 [-1,1] ⇒ `{1,1}`；mvec 是像素单位 ⇒ `{1/W,1/H}`
- Skyrim 的 mvec 是"位移 / 屏幕宽度"，全屏平移时已达 1.0 ⇒ **已在 [-1,1]**
- 原值 = `1/renderScale`，QualityMode=1 时 renderScale=0.6667 ⇒ **1.5 = 运动高估 50%**

50% 高估为什么表现为"闪"而不是"糊"：

| | 正确 | 50% 高估 |
|---|---|---|
| 真实帧 | 0 | 0 |
| 生成帧 1 | 5 | 7.5 |
| 生成帧 2 | 10 | 15 |
| 生成帧 3 | 15 | 22.5 |
| 下一张真实帧 | 20 | **20 ← 比上一个生成帧还靠前** |

最后一个生成帧**越过了下一张真实帧** ⇒ 物体冲过头再弹回 ⇒ 每 4 帧一次回弹
⇒ 连续抖动/闪烁。

**倍率仍是 4x，`blackwellTransfusion`、`patchFlipMetering` 等都没动 —— 不是回退。**

---

## 三、本次排除的（省得再查）

| 怀疑 | 结论 |
|---|---|
| Transfusion 反复 patch NGX 文件导致内核损坏 | 排除。`C:\ProgramData\NVIDIA\NGX\models\...` mtime **08-28**（今天 09-17），只在内存 patch，不落盘 |
| 4x 显存不足 | 排除。RTX 4080 SUPER **16GB**；README 警告的对象是 8GB |
| 部署的是旧版本 DLL | 排除。DLL MD5 `c048b46e…` = 官方 `DLSSG-Transfusion-v1.4.1.zip`；日志里的 `v1.4.0-pure-warp` 只是开发者没更新的版本字符串 |
| Transfusion 记录了崩溃 | 它自己写着 "First-chance records are observations, **not proof of a fatal crash**" |

---

## 四、下次启动怎么验证

**不用重新编译**，直接重启游戏。然后看这一行：

```
grep "mvecScale = " "C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE/DynamicShaderFrameGen.log"
```

- 改对了：`mvecScale = { 1.0000, 1.0000 } (renderScale=0.6667 override=1.00)`
- 没生效：还是 `{ 1.5000, 1.5000 } (override=0.00)` ⇒ 告诉我，说明 INI 被别处覆盖了

**注意：此期间不要重新编译 DFG。**（源仓库那份我也改了，所以即使编译也是 1.00，
但编译会让 INI 被 POST_BUILD 重写一次，多看一个变量。）

---

## 五、如果还闪，先分清是哪种

这次改的是**整个画面抖**。如果下次的现象不一样，方向就完全不同：

- **整个画面在抖/闪**（连纯 3D 场景、天空都在抖）⇒ 还是 mvecScale 这条线
- **只有 UI / HUD / 菜单在闪，3D 场景是稳的** ⇒ 那才轮到 UI 纹理 / UIR 那条线，
  而那条线的正解是让 DFG 提供独立的 UI 纹理，不是改 Transfusion 的开关

这两种在游戏里一眼就能分清，告诉我哪一种，我直接走对应那条。

---

## 六、本次备份位置

```
D:\workbuddy2\backup\transfusion_uir_off_20260917_193147\DLSSG-Transfusion.json.bak
D:\workbuddy2\backup\dfg_mvecscale_20260917_193400\DynamicShaderFrameGen.ini.src.bak
D:\workbuddy2\backup\dfg_mvecscale_20260917_193400\DynamicShaderFrameGen.ini.deploy.bak
```

回滚 INI：

```
copy /Y "D:\workbuddy2\backup\dfg_mvecscale_20260917_193400\DynamicShaderFrameGen.ini.deploy.bak" "E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini"
```
