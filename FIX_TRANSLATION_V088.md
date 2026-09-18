# v0.88 — 相机平移缺失：根因与修法

日期：2026-09-18
上一版：v0.87 探针版（md5 `bb6a2544a724318b1b91239734e6e205`）
本版：**v0.88**（md5 `6822e2ba6400b9bb2e85024140ae0bfe`，1320960 B）

---

## 一、根因（三层，全部有逐字节证据）

### 第 1 层：引擎的 view 矩阵不含平移

`c0 CameraView` 与 `c56 CameraViewInverse` **逐字节相同**：

```
c0  = [ 0  0  1  0 ]
      [-0 -1 -0  0 ]
      [ 1  0  0  0 ]
      [ 0  0  0  1 ]
```

左上 3×3 是纯旋转（`R == R⁻¹`，即 `R² = I`，纯轴交换 + Y 翻转），
**第 4 列平移全为零**。合法 view 矩阵必须是 `[R | t]`、`t = -R·eye`；
这里 `t = 0`，等价于 `eye = 0`。

位置只存在于 **`c80 CameraPosAdjust`**。

### 第 2 层：引擎的 ViewProj 是 `Proj @ View`（投影在左）

用真实字节穷举（`tools/derive_vp_formula.py`）：

| 候选 | `max|cand − c24|` |
|---|---|
| **`c8 @ c0`（Proj @ View）** | **0.000000** ← 精确 |
| `c0 @ c8`（View @ Proj） | 0.111111 |

**我前六轮手推全部用 `View @ Proj`，方向是反的** —— 差的就是 `0.111`。

### 第 3 层：⇒ `clipToPrevClip ≡ I`

合并第 1、2 层：

```
Proj @ [R | 0]  ==  c24        误差 0.000000
```

⇒ **引擎给的 ViewProj 根本不含位置** ⇒ 它**在任何相机位置上都是同一个矩阵**。
⇒ `clipToPrevClip = inv(cur) × prev` **恒为单位阵**。
⇒ DLSS-G 收到「**相机没动**」。

运行时实测（`tools/v088_regression_fixed.py`）：

| 场景 | engine | 修复后 |
|---|---|---|
| 相机静止 | 0.000000 | 0.000000 |
| **相机移动 0.4/帧** | **0.000000（盲）** | **0.400000** |
| 相机传送 574 | — | 574.000000 |
| 原地转头 0.02 rad | 0.000000（盲） | 17.843444 |

**`engine=0.000000` 与真实日志的 `det=1.000/1.000`、`clipDevMax=0.0324` 完全吻合。**

---

## 二、为什么之前十轮没找到

上一轮我已锁定「矩阵缺平移」，但**手推补平移公式失败六次**，然后**转向猜**。
真正的原因是 **乘法顺序**（`Proj @ View`），不是公式形式。

另外，`Streamline.cpp:635-648` 那段 **v0.69 注释把因果搞反了**：

> 「derivedViewProj = inv(CameraViewInverse) × CameraProjUnjittered，但 perFrame
>  CameraViewInverse 不带平移 …… 所以 derived 无法复现 ViewProjUnjittered
>  …… 它是 dead code by construction」

它**观察对了**（derived 确实不带平移），**结论错了**：
- 错的说法：「derived 构造有问题 → 所以禁用它」
- 真相：**引擎的 ViewProj 本身缺平移**；derived 失败恰恰是因为它忠实地继承了
  同一个缺陷。**禁用 derived 等于删掉了唯一能承载修复的路径。**

这段注释用 `false &&` 把 `useDerived` 焊死，缺陷因此存活了十轮。

---

## 三、修法（v0.88）

在 `CheckFrameConstants` 中用**已有的**操作数重建：

```
R3  = c0  CameraView  左上 3×3        （纯旋转）
eye = c80 CameraPosAdjust[0..2]       （唯一携带位置）
View_fixed = [R3 | -R3 @ eye]
VP_fixed   = c8 CameraProj（转置） @ View_fixed      ← 顺序是关键
```

然后用 `VP_fixed` 同时充当 **cur 与 prev**，`clipToPrevClip` 才带运动。

### 安全性（离线已证）

| 场景 | `|I − clip|` | 含义 |
|---|---|---|
| `eye = 0` | 与 `c24` 完全相同（误差 0） | **原点退化守卫** |
| 相机静止 | 0.000000 | **绝不凭空发明运动** |
| 相机移动 0.4 | 0.400000 | 运动恢复 |

**v0.69 的反对意见（"缺平移的矩阵只会在没运动的地方编造运动"）就此作废** ——
它针对的正是「缺平移」这个缺陷本身，而本修法提供的就是那个缺失项。

### 顺带修正的两处日志谎言

- `diag.reprojSource` 增加第三态：`0=engine / 2=fixed`
- 「derived source is unavailable」告警改为 `NO corrected source was used (fixedVpDev=...)`

---

## 四、改动清单

| 文件 | 行尾 | 改动 |
|---|---|---|
| `src/Streamline.cpp` | **LF** | E1 重建 ViewProj；E2 源标签三态；E3 告警文本；版本 tag → v0.88 |
| `src/Streamline.h` | **CRLF** | 新增 `float fixedVpDev = -1.0f;` |

备份：`src/Streamline.cpp.bak-20260918-145137`、`src/Streamline.h.bak-*`

补丁脚本（均带断言、默认干跑）：
`tools/patch_v088_translation.py`、`tools/patch_v088_header.py`、
`tools/patch_v088b_float4_access.py`、`tools/patch_v088c_version_tag.py`

---

## 五、验收判据（跑一次即可判死）

看 `DynamicShaderFrameGen.log`，**按顺序**核对：

### 1. 版本与生效标志（**第一判据，不满足则整轮作废**）

```
[XRAY] diag active v0.88 (compiled ...)
[XRAY] fixed-viewproj v0.88 ACTIVE: reprojSource=2 fixedVpDev=<大数>
```

- `reprojSource` 必须为 **2**
- `fixedVpDev` 必须 **> 0**（相机不在原点时通常 **数百**）
  - `fixedVpDev = 0` ⇒ 重建退化成了引擎副本，**修复未生效**，整轮作废
  - `fixedVpDev = -1` ⇒ 重建不可用

### 2. 运动是否恢复（**核心判据**）

```
det(min/max)=...    clipDevMax=...
```

| | v0.86/v0.87（坏） | v0.88（预期） |
|---|---|---|
| `det(min/max)` | `1.000/1.000` 恒定 | **不再恒为 1** |
| `clipDevMax` | `0.0324` | **显著大于 0**（相机移动时约 0.4 量级） |

**`det` 恒为 1 等价于 `prev == cur`** —— 那就是"相机没动"的指纹。

### 3. 主观判据

- 火焰与人**不再来回拉扯**
- 生成帧不再把画面拉回上一帧位置
- 移动时画面连贯

### 4. 回归判据（必须同时成立）

- **相机静止时**（主菜单/暂停/读档界面）画面**不得**出现抖动
  —— 这是 `eye=0` 守卫的运行时对应项

---

## 六、已知未修（**本版不碰**，修一处验一处）

1. **场景切换的假位移**：`s_prevVP` 跨帧持久，世界加载/读档会留下一帧巨大的假位移
2. **加载画面闪烁**（v0.63–v0.70 老问题）完全未触及
3. `EnsureFrameToken()` 的 `static s_lastFrame` 多线程隐患
4. `s_prevVP` / `s_lastGoodClip` 跨线程共享
5. `[MFG] Present skips SetDLSSGOptions` 守卫
6. `presented world` mode=710（1 张/帧）与 `mult(acc/pres)=2/2` 不一致

---

## 七、回滚

```bash
cd D:/Modding/DynamicShaderFrameGen
cp src/Streamline.cpp.bak-20260918-145137 src/Streamline.cpp
cp "E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.dll.v087-*" \
   "E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.dll"
```

---

## 八、本轮新增铁律

1. **`sl::float4` 没有 `operator[]`** —— 只有 `.x/.y/.z/.w`；
   `float4x4::operator[]` 返回 `float4&`。写 SL 矩阵前先看既有代码怎么写。
2. **守卫的检查范围必须是「被改写的那一段」**，不是整个文件 ——
   否则既有合法代码会让守卫假阳性。
3. **版本 tag 必须随每次改动更新** ——
   v0.87 打了 v0.86 的 tag，直接导致上一轮日志判读错误。
4. **构建脚本不负责部署，是 CMakeLists 的 POST_BUILD 在部署** ——
   核验部署要看 md5，不要看构建脚本。
