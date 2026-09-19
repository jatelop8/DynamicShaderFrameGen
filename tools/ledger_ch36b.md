
## 36.7 A≠B：改 NGX 二进制与冻结**无关**，可以划掉

把三局的 Transfusion 活动量逐项数出来：

| 局 | `HUDless UIR patch` | `[OPTIONS]` 拦截 | `Applied fixed` | `[PERF]` | 画面 |
|---|---|---|---|---|---|
| 09-19 23:38 | **14** | 0 | 0 | 0 | **活了** |
| 09-20 00:31 | 10 | 1 | 1 | 4 | 冻结 |
| 09-20 00:58 | 8 | 1 | 1 | 4 | 冻结 |

**NGX 二进制 patch 在活着的那一局也发生了 14 次** ⇒ **它不是并因。**
真正与冻结同现的是「**Transfusion 真的拦截并驱动了 DLSS-G**」（活局全 0）。

★ **但必须先说清一个分不开的混淆**：归档里「Transfusion 驱动了 DLSS-G」与「DLSS-G 支线被用到」**完全共线**
（活局用的是 FSR3，DLSS-G 本来就没启用）。**仅凭归档无法把两者分开 —— 这就是隔离实验的全部理由**，也是为什么
36.1 的「DLSS-G 参与 ⟺ 冻结」这条切分不能直接写成因果（L45）。

## 36.8 本轮给用户的指令已做前置核查

给出「改 `DINPUT8.dll` 文件名」之前，已实测：

1. 目标目录 `ls`：确认 `dinput8.dll`（540,672 B，Sep 18 19:44）是当前生效的那个，
   且 `.disabled`（5,945,344 B）与 `.rtxmfg-off`（5,945,344 B）**已被占用** ⇒ 目标名改用 `.transfusion-off`（L46）。
2. 该局只到 2x 的说法有代码依据：`Streamline.cpp:278-288`，`kernelUnlocker` 为假时
   `diag.reqStepMax = max(1, a_hwMax)` 并**提前 return**，不越过硬件上报值。
   （INI 亦记：Ada 的 `numFramesToGenerateMax` 原生为 1 = 2x；本盘 12 局的 `hwMax=6` 是 Transfusion 抬上去的。）
3. 之前 12 局的 `ask=4 accepted=4` 全部依赖 Transfusion 抬高上报值 ⇒ **「无 Transfusion 的 2x」这一配置从未跑过**。
