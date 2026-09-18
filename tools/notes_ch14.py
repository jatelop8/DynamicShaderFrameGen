#!/usr/bin/env python3
"""Append chapter 14 to MFG_MASTER_NOTES.md, before the maintenance-rule tail."""
import io
import sys

P = "MFG_MASTER_NOTES.md"
ANCHOR = (
    "---\n\n"
    "**本文件维护规则**：每次改动后追写「本轮改动 / 验证结果 / 新证据 / 新错误」，\n"
    "**不覆盖历史章节**，只在第 9 章与末尾追加。\n"
)

CH14 = """## 第 14 章：v1.07b —— 第三成因：相机族锁**没有释放路径**（2026-09-18 22:24）

### 14.1 先确认 v1.06 的两处修复**真的生效了**（22:02 日志实锤）

在追第三成因之前必须先排除"v1.06 没修好"。22:02 那份日志逐字证明**两处都生效**：

```
[22:02:00.649] [XRAY] diag active v1.06 (compiled Sep 18 2026 21:38:18)
[22:02:00.676] [Streamline] Reflex FLIP cap = 39 fps (25641us) - panel 160Hz, 4 flips per real frame => ~156 presented fps
camPrev(ok/used)=1/90
Transfusion: DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
```

- `39 fps / 156 presented` ⇒ 反射率除数回来了，相对 160Hz 面板还有 4fps 余量（v1.05 曾是 `159 fps / 636`）。
- `camPrev(ok/used)=1/90` ⇒ v1.06 补的相机历史**写端**在工作（v1.05 是 `0/0`）。
- `presentation count: 4x` ⇒ 4 倍帧生成**确实在跑**。

⇒ **"没有出现 4 倍" 是错觉；4 倍在跑，是画面没动。** 所以一定存在第三条成因。

### 14.2 第三成因：族锁只有赋值，没有任何一处清零

`snapLockHave` / `snapLockProjValid` / `snapLockProj00` 三个状态**全项目只被赋 true，没有一处赋 false**：

```
grep -rn 'snapLockHave\\|snapLockProjValid\\|snapLockProj00' src/FrameGen.cpp
-> snapLockHave      置 true（v1.07b 后 :894 / :981）          无 false
-> snapLockProjValid 置 true（:996）                          无 false
-> snapLockProj00    赋值（:995）                              无重置
```

而 v1.00 的注释自己写着「**异族永不 re-acquire**」（`FrameGen.cpp:903-908`）——
于是这个状态机**没有出锁转换**。一旦锁落到错的族，整局都出不来。

### 14.3 走锁的棘轮：v1.03 的"量级逃逸"

`FrameGen.cpp` v1.03 在比率测试**之前**加了一条：

```cpp
const bool unitProj  = 0.995f < proj00         && proj00         < 1.005f;
const bool lockUnit  = 0.995f < snapLockProj00 && snapLockProj00 < 1.005f;
if (unitProj != lockUnit) sameFamily = true;      // <-- 一整类的到达被无条件放行
```

再叠上 accept 处的刷新（`:995-996  snapLockProj00 = proj00;`）⇒ **锁会"走"**。
22:02 日志逐字记录了这次行走：

```
#1  acquire  proj00=0.149184                -> lock 0.149184   （世界相机抢到了第一把）
#2  esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
#4  esc 0.149184 vs locked 1.0      -> adopt -> lock 0.149184
#11 esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
#13 esc 0.149184 vs locked 1.0      -> adopt -> lock 0.149184
#20 esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
...                                          -> lock 0.8391    （3D 菜单族）
```

锁读到 1.0（单位投影）时，**任何非单位到达都算"合法第二相机"**，包括 0.8391。
锁一旦变成 0.8391，比率就是 `0.149184/0.8391 = 0.178` ⇒ 世界相机**永久被拒**。
日志尾部的证据：`lock(pub/hold/re/still)=11821/2725/2416/0  proj00=0.8391  famRej=309`，
且 `menu=857 world=94` —— **已经在世界里渲染了，锁还在菜单族手上。**

**注意 `still=0` 这个数字**：异族分支在 `return false` 之前**完全不计数**
（`snapLockStill` 只在同族步进断裂那条路加），所以"锁死了多久"这个量在日志里读不出来。
这是本轮顺手修掉的**仪表**缺陷，不是主因。

### 14.4 v1.07b 的改动（两处交付 + 一处**写出来又丢掉**）

| # | 位置 | 改动 | 定性 |
|---|---|---|---|
| 1 | `FrameGen.cpp:862-888` | **删除 v1.03 量级逃逸**，`±2%` 比率测试独立成立 | **承重** |
| 2 | `Streamline.cpp:507` / `:1217` 抬高，`FrameGen.cpp:838-851` 消费 | 新增 **reset-edge 释放**：菜单开/关边沿把族锁清掉 | 补救 |
| 3 | — | still 阈值重采 —— **写过、量过、丢掉** | 见 14.5 |
| 4 | `FrameGen.cpp:915` | 异族分支补 `++snapLockStill`，让 `still=N/M` 报真话 | 仪表 |
| 5 | `Streamline.cpp:1577` | 横幅 `v1.06` → **`v1.07b`** | 仪表 |
| 6 | `FrameGen.h:336-337` | 新增 `snapLockReleasePending` / `snapLockReleased` | 支撑 2 |

**edit 1 为什么是承重的**：22:02 的 `#1 acquire proj00=0.149184` 说明**锁本来就在世界族手里**，
是逃逸把它走掉的。删掉逃逸，锁**根本到不了 0.8391**。
回归 C1 直接证明：只删逃逸、**不带任何释放路径**，结果就已经是 `proj00=0.149184`、
`world-refusals=0` —— 释放对这份日志**零贡献**。

**edit 2 为什么还是要留**：它治的是**另一条入口**——"开局第一把锁就被菜单族拿到"。
那条路上 v1.03..v1.06 永远出不来（v1.00 明令异族不得 re-acquire）。回归 C2 里
只删逃逸的表现是 `pub=0 world-refusals=744`（**一个快照都发布不出去**），加上释放后恢复。

### 14.5 ★★ 被丢掉的 edit 3：still 阈值重采（附回归量化）

我第一版 v1.07 还加了第三条释放路径：异族连续失败 `kCamStillTol(90)` 次就释放并采纳当前到达。
**回归量出它不是修复**：

```
[C2b] 被弃草稿（隔离，无边缘）    locked proj00=1         pub=700  released=1  world-refusals=744
```

`proj00=1` —— 它**采纳了单位正交族**。原因很直白：那条分支采纳的是
"**恰好第 90 次**非连续的那个到达"，而 A/B 两个异族交替到达时，第 90 次是 A 还是 B
**取决于到达顺序**。⇒ 它只是**用错族换错族**，而单位正交族的 `clipToPrev` 是 identity，
**恰恰就是冻结本身**。

更要命的是它**重开了 v1.00 故意关上的门**（`FrameGen.cpp:903-908` 原文）：

> v0.94 re-acquired unconditionally after kCamStillTol non-continuing arrivals, so a
> foreign camera that arrived monotonically for 90 frames was adopted and then
> "continued" itself forever. **That is the freeze.** Only an arrival from the SAME
> family may take over.

⇒ 按用户"**哪些已经出错了 就不要再犯**"的要求，edit 3 **已撤回**（`patch_v107b_dropstill.py`），
只在回归里留作**反证**，防止下次有人再把它加回来。
**有边缘时**的两个数字恰好量化了它的害处：`pub=700`（草稿）vs `372`（v1.07b），
差值 **328 帧**就是"单位族在边沿之前一直占着 `frameBufferCopy`"。

### 14.6 残留：释放后的竞态（**已知，故意不修**）

释放是"清锁 → 让**下一个到达者**建立新族"。若菜单族在释放后**先到**，锁又回到 0.8391：

```
[C3] NEW 菜单族先到且持续到达   locked proj00=0.8391  famrej=1488  released=1  world-refusals=744
```

而且**任何**"异族持锁太久就释放"的设计都救不了它——异族自己位置恒定 ⇒ `continues` 恒真
⇒ `still` 每帧被清零，阈值永远到不了。

**要真关掉这个竞态，需要的是"属性判据"而不是"顺序"**：例如"某个指纹一旦被判为菜单族，
在没有菜单打开的帧里就不许发布"。**本轮故意不做**——v1.07b 已经修掉的是
**22:02 实际发生的那一个**（日志 `#1` 是世界族夺锁），再叠一个未验证的判据就是又一次赌博。
日志里 `proj00=` 这一行**一行就能判定**是否落进这个残留。

**不要拿 `w != 1`（non-affine）做判据**：v0.89 的注释（`FrameGen.cpp:654-683`）已经实测过——
被 `[3][3] != 1` 丢掉的那一族定位**在 glide**（`pos=(-50.0,880.7,94.3)`，正是世界相机），
而通过的是**冻结在 `(-160,160,128)`** 的单位族。世界相机与菜单族**都是非仿射**，`w` 区分不了。

### 14.7 v1.07b 的提交与验证表

| 项 | 值 |
|---|---|
| 提交 | `01ce63c` |
| tag | `v1.07b` |
| DLL | 1,325,568 B，md5 `ae44a128c07f02d7d6d70f2a1c76452d` |
| 构建 == 部署 | `cmp` IDENTICAL（`build/NINJA/` 与 `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/`）|
| 备份 | `src/backup-v1.07b-20260918-222454/` |
| 编译 | `BUILD SUCCESS`，无 `error C/LNK` |

DLL 内字符串（**"删掉的串必须为 0"，不只验证"加的串存在"**）：

| 串 | 计数 | 含义 |
|---|---|---|
| `diag active v1.07b` | 1 | 横幅已升 |
| `diag active v1.07 ` | **0** | 旧横幅已不存在 |
| `lock RELEASED on the reset edge` | 1 | 边沿释放已进产物 |
| `lock RELEASED after` | **0** | still 重采**已不在产物里** |
| `magnitude classes differ` | **0** | 量级逃逸**已不在产物里** |
| `non-affine w=` | 1 | v0.89 的非破坏性观测仍在 |

离线回归 `tools/regress_v107_lockrelease.py`：**RESULT OK**

| 用例 | locked `proj00` | world-refusals | released | pub |
|---|---|---|---|---|
| C1 OLD v1.03..v1.06 | **0.8391** | 743 | 0 | 1489 |
| C1 只删逃逸 | **0.149184** | **0** | 0 | 744 |
| C1 NEW v1.07b | 0.149184 | 0 | 1 | 744 |
| C2 只删逃逸（菜单族预置持锁） | 0.8391 | 744 | 0 | **0** |
| C2 NEW v1.07b | 0.149184 | 372 | 1 | 372 |
| C2b 被弃草稿（隔离） | **1** | 744 | 1 | 700 |
| C3 NEW 菜单族持续到达 | 0.8391 | 744 | 1 | 744 |
| C4 连续世界流 200 帧 | 0.149184 | 0 | 0 | 200 |
| C5a 仅 A/B，只删逃逸 | 0.149184 | 0 | 0 | 6 |
| C5b 仅 A/B，OLD | **1** | 0 | 0 | 12 |

C5 是**逃逸就是行走器**的最干净证明：完全不引入菜单族，只让 A/B 交替到达，
逃逸就把锁翻到单位族（`A/B only, OLD -> proj00=1`）。

### 14.8 本轮新增/修改的工具

- **新增** `tools/patch_v107_lockrelease.py` —— v1.07（含已弃用的 edit 3）的补丁脚本，
  逐条锚点 `count==1`、幂等标记、行尾归一化、9 项 post-condition、落盘后回读。
- **新增** `tools/patch_v107b_dropstill.py` —— 撤回 edit 3 的补丁脚本（8 项 post-condition）。
- **新增** `tools/regress_v107_lockrelease.py` —— 建模 A(world 0.149184, glide) /
  B(unit 1.0, 恒定) / C(menu 0.8391, 恒定) 三个族，C1–C5 五组用例，
  `OLD` / `ESCAPE_GONE` / `NEW` / `DRAFT_STILL` 四种构建组合。
- **修改** `tools/analyze_session.py`：
  1. **版本横幅改成硬比对**（`EXPECTED_BUILD`）。旧正则 `v[\\d.]+` **连 `v1.07b` 都匹配不到**——
     它只吃数字和小数点。现在 `v[\\d.a-z]+`，且与期望版本不一致直接报 PROBLEM。
  2. **第 4 项 CAMERA MOTION 剔除 `frames=1` 首个样本**：日志原本把开机加载
     `presentAge=19199ms` 报成 "a real hang"，修后报
     `presentAge max=432ms ... the render loop never stalled`。
  3. **第 6 项 CAMERA FAMILY LOCK 判据改写**：旧判据要求 `still==0`，
     而 `still` 只在 v1.06（一个从不加它的版本）里恒 0；v1.07b 里它会涨。
     新判据：`famRej` 大 + **世界族持锁** = **健康**（不变式在工作）；
     `famRej` 大 + **0 次释放** + 确有菜单→世界转换 = 问题。
     另新增 `menuFrames` 输出与释放事件回显。

### 14.9 一行命令自检（下次开游戏**只看这个**）

```
python tools/analyze_session.py
```

判据（三条，缺一不可）：

1. `build  v1.07b`，**不是** `PROBLEM: this log was written by ...`
2. 第 6 项 `proj00=` 是 **`0.149184`**（世界族持锁）——**不是 `0.8391`**
3. 第 6 项 `release events: N` 中 **N ≥ 1**（菜单→世界转换触发了释放）

若第 2 条是 `0.8391` ⇒ 落进了 14.6 的残留（或 DLL 没换上去）。
若第 1 条报版本不符 ⇒ **DLL 根本没换上去**，后面所有结论都不作数。

### 14.10 仍未验证（不假装）

- **v1.07b 是否真止住冻结**：**未知**。我无法运行游戏。
- **§14.6 的竞态**：故意未修。
- **Modex 闪退**（第三方 `Modex::UIManager::MainWndProc`）：须在 MO2 GUI 手动取消勾选；
  **验证冻结前必须隔离它**，否则结论不可信。
- **RTX 20/30 系**：一行未写（`grep -i xess` = 0，需 sm86/sm75 内核）。
- **DLSS5**：代码在 `src/NeuralRendering/`（NGX Feature 18，自有实现），**未上机验证**。

### 14.11 ★ 一个长期误判的根因：`core.autocrlf=true`

我在本文件第 6 章写过"12 个源文件行尾各不相同"。**这个结论部分是我自己造成的**：

- 仓库 **`core.autocrlf=true`**，且**没有 `.gitattributes`**；
- ⇒ `git checkout --` 会把仓库里的 LF 规范形式**在落盘时转成 CRLF**；
- 于是"实测行尾"其实是「git 规范化」+「补丁脚本按探测结果插入」共同作用的**动态**结果。
- 实证：`git checkout -- src/FrameGen.cpp` 后，该文件从 **LF（1364 bare_LF）**
  变成 **CRLF（1364 CRLF）**，md5 从 `0363c183…` 变成 `d5c4cf34…`，
  而 `git status` 认为工作树**干净**。
- 2026-09-18 22:24 实测（当前真实值）：
  `FrameGen.cpp` **CRLF 1414 / bare_LF 0**、`FrameGen.h` CRLF 366、`Streamline.cpp` CRLF 2254、
  `Streamline.h` CRLF 384、**`DX12SwapChain.cpp` 纯 LF 1806**、`main.cpp` MIXED(162/7)。

**结论：行尾永远逐文件实测，补丁脚本必须自动探测，不要凭记忆也不要写死。**

---
"""


def main():
    raw = io.open(P, "rb").read()
    text = raw.decode("utf-8")
    n = text.count(ANCHOR)
    print(f"anchor count = {n} (must be 1)")
    if n != 1:
        print("REFUSED, nothing written")
        return 2
    if "第 14 章" in text:
        print("REFUSED, nothing written (chapter 14 already present)")
        return 2
    res = text.replace(ANCHOR, CH14 + ANCHOR, 1)
    for label, ok in [
        ("chapter 14 heading present", "## 第 14 章" in res),
        ("maintenance rule still last", res.rstrip().endswith(
            "**不覆盖历史章节**，只在第 9 章与末尾追加。")),
        ("chapter 13 kept", "### 13.6 v1.06 终版备份位置" in res),
        ("chapter 12 kept", "### 12.9 v1.06 的提交与验证" in res),
    ]:
        print(f"  [{'ok ' if ok else 'BAD'}] {label}")
        if not ok:
            print("REFUSED, nothing written")
            return 3
    io.open(P, "wb").write(res.encode("utf-8"))
    back = io.open(P, "rb").read().decode("utf-8")
    assert "## 第 14 章" in back
    print(f"APPLIED. {len(raw)} -> {len(res.encode('utf-8'))} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
