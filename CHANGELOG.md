# DynamicShaderFrameGen 更新日志

帧生成插件（FrameGen）：FSR3 帧生成 + DLSS 超分，ENB 完全兼容，A/N 显卡通用。

---

## v0.40 — 2026-08-31

**命名统一（玩家友好）**
- 面向玩家的叫法统一为 **FrameGen（帧生成）**，菜单/INI 不再使用容易误解的 FSR/DLSS 标签
- 明确标注"通用帧插值，NVIDIA 与 AMD 显卡均可使用"
- DLL 版本号规范为 0.40.0.0

## v0.39 — 2026-08-31

**移除 DLSSG 模式，专注稳定**
- 移除 DLSSG（DLSS 帧生成）模式——在复杂整合环境下（高刷窗口化 + 多插件）实测不稳定（频闪/黑屏/进不去游戏），十二轮调试后决定移除
- 帧生成统一使用 **FSR3 技术**（AMD FidelityFX SDK，A/N 卡全支持），稳定可靠
- 游戏内菜单移除 Provider 切换选项，杜绝误开
- **N 卡用户**：FSR3 帧生成 + DLSS 超分组合效果与 DLSSG 相当，且稳定

## v0.26 — 2026-08-31

**ForceBorderless 强制无边框窗口化（新功能）**
- 新增 `ForceBorderless=1`（默认开启）：强制游戏以无边框窗口化运行
- 解决"帧生成不生效"的经典问题——无论玩家在游戏里设置全屏还是窗口化，帧生成一定激活，视觉等同全屏
- 每帧开销 <1μs，无性能影响

## v0.25.4 — 2026-08-31

**修复三个关键 Bug**
- 修复 **AMD 显卡打不开帧生成**的问题（误用 DLSS 可用性判断 FSR3）
- 修复 **FSR 切换到 DLSS 后打不开**的问题（加载已删除的组件）
- 修复 **游戏菜单关闭后小鼠标光标残留**的问题

## v0.25 — 2026-08-30

**架构重构（首个正式版基础）**
- DLSS-NR（神经渲染）移出插件，改由外部 ReShade 方案提供，插件保持纯净
- 帧生成：FSR3（默认）+ DLSSG（实验性）
- DLSS 超分：DLAA / Quality / Balanced / Performance / Ultra Performance
- 游戏内菜单（长按 Home）：开关帧生成、超分档位、锐度
- ENB 兼容（swapchain 代理）

---

## 使用要求

| 项 | 要求 |
|---|---|
| 游戏 | Skyrim SE（AE 1.6.1170） |
| 前置 | SKSE64 |
| 显卡 | 任意 DX12 显卡（FSR3 帧生成 A/N 通用；DLSS 超分仅 N 卡） |
| 显示模式 | 无要求（ForceBorderless 自动处理） |

## 说明

- 帧生成后 FPS 翻倍（60 → 120）
- 与 ENB 完全共存
- 与 DynamicWetness / Community Shaders 等 swapchain 插件兼容
