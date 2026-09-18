#!/usr/bin/env python3
"""Append section 11 to the 2026-09-18 work log (append-only)."""
import io
import sys

P = r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-18.md"

SEC11 = """
---

# 11. 22:00–22:25 —— v1.07b：第三成因「相机族锁**没有释放路径**」+ 撤回我自己写的一条错误修复

## 11.1 用户这一轮的输入（原话）

> **"看日志把，我感觉四倍帧生成这次也没有出现，但是画面依旧卡住"**

用户对"4 倍没出现"的**直觉是错的**，但"画面依旧卡住"是准的 —— 而这正是最有价值的信息：
它把范围从"没跑起来"缩到了"跑起来了但画面对不上"。

## 11.2 ★★★★★ 第一件事：22:02 的日志证明 v1.06 的修复**都生效了**

追新根因前必须先排除"v1.06 没修好"，否则会又一次把已修的东西再修一遍。

```
[22:02:00.649] [XRAY] diag active v1.06 (compiled Sep 18 2026 21:38:18)
[22:02:00.676] [Streamline] Reflex FLIP cap = 39 fps (25641us) - panel 160Hz, 4 flips per real frame => ~156 presented fps
camPrev(ok/used)=1/90
Transfusion: DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)
Transfusion: [PERF] 4x | Kernel: Ada | FPS: 21.7 (46.14ms) | Jitter: 37.18ms
```

- `39 fps / ~156 presented`（v1.05 是 `159 fps / 636`）⇒ **反射率除数回来了**，对 160Hz 面板留 4fps 余量。
- `camPrev(ok/used)=1/90`（v1.05 是 `0/0`）⇒ **v1.06 补的相机历史写端在工作**。
- `presentation count: 4x` ⇒ **4 倍帧生成确实在跑**。

⇒ **"没有出现 4 倍" 是错觉；4x 在跑，是画面没动。** 所以必有第三条成因 —— 这个判定直接决定了我
不该再去动 DLSS-G 的请求侧（那已经证明是对的），而该去看**交给它的相机数据**。

## 11.3 ★★★★★ 第三成因：族锁只有赋值、没有清零

```
grep -rn 'snapLockHave|snapLockProjValid|snapLockProj00' src/FrameGen.cpp
-> snapLockHave      只在两处置 true，无 false
-> snapLockProjValid 只置 true，无 false
-> snapLockProj00    只赋值，无重置
```

v1.00 的注释自己写着"**异族永不 re-acquire**"（现 `FrameGen.cpp:903-908`），
⇒ 这个状态机**没有出锁转换**。一旦锁落到错的族，**整局都出不来**。
日志尾部正是这个状态：`lock(pub/hold/re/still)=11821/2725/2416/0  proj00=0.8391  famRej=309`，
而且 `menu=857 world=94` —— **已经在世界里渲染，锁还在菜单族手上**。

`proj00=0.8391` 这一族是什么？`FrameGen.h:326-332` 早就标记过：

> row3=(-0.00391655,0.999991,0.0015,0) ... **not a camera at all, but a mis-offset read of the
> perFrame constant buffer**

22:02 日志里正是它在占锁：`[CAM] #8058 non-affine w=0 ACCEPTED row3=(-0.00391655,0.999991,0.0015,0) det3=-2.52504 pos=(-243.0,-415.3,118.6)`。

另外注意 `still=0` 这个数：异族分支在 `return false` 之前**完全不计数** ⇒
"锁死了多久"这个量**在日志里读不出来**。这是仪表缺陷（顺手修了），不是主因。

## 11.4 走锁的棘轮 = v1.03 的「量级逃逸」

v1.03 在比率测试前加了一条：

```cpp
const bool unitProj = 0.995f < proj00         && proj00         < 1.005f;
const bool lockUnit = 0.995f < snapLockProj00 && snapLockProj00 < 1.005f;
if (unitProj != lockUnit) sameFamily = true;      // 一整类到达被无条件放行
```

叠上 accept 处的刷新 `snapLockProj00 = proj00;` ⇒ **锁会走**。22:02 日志逐字：

```
#1  acquire  proj00=0.149184                -> lock 0.149184   （世界相机抢到了第一把！）
#2  esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
#4  esc 0.149184 vs locked 1.0      -> adopt -> lock 0.149184
#11 esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
#13 esc 0.149184 vs locked 1.0      -> adopt -> lock 0.149184
#20 esc 1.0      vs locked 0.149184 -> adopt -> lock 1.0
...                                          -> lock 0.8391    （3D 菜单族）
```

锁读到 1.0 时**任何非单位到达都算"合法第二相机"**，包括 0.8391；锁一旦是 0.8391，
比率 `0.149184/0.8391 = 0.178` ⇒ 世界相机**永久被拒**（`famRej=309`）。

## 11.5 v1.07b 的改动（2 处交付 + 1 处**写过又丢掉**）

| # | 位置 | 改动 | 定性 |
|---|---|---|---|
| 1 | `FrameGen.cpp:862-888` | **删除 v1.03 量级逃逸** | **承重** |
| 2 | `Streamline.cpp:507` / `:1217` 抬高；`FrameGen.cpp:838-851` 消费 | 新增 **reset-edge 释放** | 补救 |
| 3 | — | still 阈值重采，**写过、量过、撤回** | 见 11.6 |
| 4 | `FrameGen.cpp:915` | 异族分支补 `++snapLockStill` | 仪表 |
| 5 | `Streamline.cpp:1577` | 横幅 `v1.06` → **`v1.07b`** | 仪表 |
| 6 | `FrameGen.h:336-337` | 新增 `snapLockReleasePending` / `snapLockReleased` | 支撑 2 |

**edit 1 为什么承重**：`#1 acquire proj00=0.149184` 证明**锁本来就在世界族手里**，是逃逸走掉的。
删掉逃逸，锁**根本到不了 0.8391**。回归 C1 证明：只删逃逸、**不带任何释放**，
结果就已经 `proj00=0.149184` / `world-refusals=0` —— **释放对这份日志零贡献**。

**edit 2 为什么留**：治的是**另一条入口**（开局第一把锁就被菜单族拿到），那条路上
v1.03..v1.06 永远出不来。回归 C2 里只删逃逸是 `pub=0 world-refusals=744`（**一个快照都发不出去**），
加释放后恢复。

## 11.6 ★★ 我撤回自己写的 edit 3（still 阈值重采）—— 附量化

第一版 v1.07 我加了第三条释放：异族连续失败 `kCamStillTol(90)` 次就释放并采纳当前到达。
**回归量出它不是修复**：

```
[C2b] 被弃草稿（隔离，无边缘）  locked proj00=1   pub=700  released=1  world-refusals=744
```

`proj00=1` = **它采纳了单位正交族**。因为那条分支采纳的是"**恰好第 90 次**非连续的那个到达"，
A/B 交替时第 90 次是 A 还是 B **取决于到达顺序** ⇒ **用错族换错族**，
而单位正交族的 `clipToPrev` 是 identity，**恰恰就是冻结本身**。

更要命：它**重开了 v1.00 故意关上的门**（`FrameGen.cpp:903-908` 原文）：

> v0.94 re-acquired unconditionally after kCamStillTol non-continuing arrivals, so a foreign
> camera that arrived monotonically for 90 frames was adopted and then "continued" itself
> forever. **That is the freeze.** Only an arrival from the SAME family may take over.

⇒ 按用户"**哪些已经出错了 就不要再犯**"，**已撤回**（`tools/patch_v107b_dropstill.py`），
只在回归里留作**反证**。有边缘时的两个数字正好量化害处：`pub=700`（草稿）vs `372`（v1.07b），
差 **328 帧** = 单位族在边沿之前一直占着 `frameBufferCopy`。

## 11.7 残留：释放后的竞态（**已知，故意不修**）

释放 = "清锁 → 让**下一个到达者**建立新族"。若菜单族在释放后**先到**，锁又回 0.8391：

```
[C3] NEW 菜单族先到且持续到达  locked proj00=0.8391  famrej=1488  released=1  world-refusals=744
```

而且**任何**"异族持锁太久就释放"的设计都救不了 —— 异族自己位置恒定 ⇒ `continues` 恒真
⇒ `still` 每帧清零，阈值永远到不了。**要关掉它需要的是"属性判据"而不是"顺序"**
（例如"某指纹一旦被判为菜单族，在没有菜单打开的帧里不许发布"）。**本轮故意不做**：
v1.07b 修掉的是 **22:02 实际发生的那一个**，再叠一个未验证的判据就是又一次赌博。
日志 `proj00=` **一行就能判定**是否落进这个残留。

**不要拿 `w != 1`（non-affine）当判据**：`FrameGen.cpp:654-683`（v0.89）已经实测过 ——
被 `[3][3] != 1` 丢掉的那一族定位**在 glide**（`pos=(-50.0,880.7,94.3)`，正是世界相机），
通过的却是**冻结在 `(-160,160,128)`** 的单位族。世界相机与菜单族**都是非仿射**，`w` 区分不了。
⇒ **差一点又选错判据，是 v0.89 留下的注释拦住了我。**

## 11.8 回归第一次 FAIL：三个仿真口径错误（全是我自己的）

第一版 `regress_v107_lockrelease.py` 报 `RESULT: FAIL / C1: old code released the lock`：

1. **`run()` 给 OLD 也发了 `request_release()`** —— 而 v1.03..v1.06 **根本没有释放机制**，
   这个字段都不存在。是仿真凭空造了一次释放。修：pending 消费按构件特性门控 + OLD 不发释放。
2. **`menu_stops_at_edge` 名不符实**：我实现成了"C 全程不到达"，而参数名说的是"边沿后不到达"。
3. **靠到达顺序推"菜单族持锁"这个状态不可靠** —— 因为**逃逸本身既是病因也是解药**
   （它允许任何量级不同的族重新夺锁），逃逸期的构建会**自己跌回 A**。
   修：改成**直接 `prime()` 预置锁状态**，模型才诚实。

## 11.9 ★ 这一轮最值得记的一条：「no release 和 release 每一行数字相同」

第二版回归跑出 `RESULT: OK`，但 C2 表里 **`no release` 与 `release` 每一行数字完全相同** ——
也就是说**释放路径一次都没改变结果**。这正是我笔记里那条**方法论第一检查项**要抓的东西：

> **修一个真实错误 ≠ 修的是正在追的问题。**

一个"通过"的回归，如果它**无法让被测改动体现差别**，那它证明的是**别的东西**在起作用。
我因此重写了回归，让三件事分开被证明：删逃逸（承重，C1）、边沿释放（补救，C2）、
still 重采（有害，C2b）。**没有这一次重写，我就会带着一条假证据交差。**

## 11.10 三诊工具 `tools/analyze_session.py` 的三处改动

1. **版本横幅改成硬比对**（`EXPECTED_BUILD`）。旧正则 `v[\\d.]+` **连 `v1.07b` 都匹配不到**
   （只吃数字和小数点）。现在 `v[\\d.a-z]+`，不一致直接报 PROBLEM。
2. **第 4 项 CAMERA MOTION 剔除 `frames=1` 首个样本**：原本把开机加载的
   `presentAge=19199ms` 报成 "a real hang"。修后是
   `presentAge max=432ms ... the render loop never stalled`。
3. **第 6 项 CAMERA FAMILY LOCK 判据改写**：旧判据要求 `still==0`，而 `still` 只在
   v1.06（一个从不加它的版本）里恒 0；v1.07b 里它会涨。新判据：`famRej` 大 + **世界族持锁**
   = **健康**（不变式在工作）；`famRej` 大 + **0 次释放** + 确有菜单→世界转换 = 问题。
   新增 `menuFrames` 输出与释放事件回显。

拿 22:02 日志回测，**四条结论全部自动报出**（版本不符 / 世界帧里锁在菜单族 / 转换期 0 次释放 /
晚期 clipToPrev 退回 identity），同时确认反射率 `OK 4fps 余量`、`presentAge OK`、`accepted=4x presented=4x`。

## 11.11 交付验证表

| 项 | 值 |
|---|---|
| 提交 | `01ce63c` |
| tag | `v1.07b` |
| DLL | 1,325,568 B，md5 `ae44a128c07f02d7d6d70f2a1c76452d` |
| 构建 == 部署 | `cmp` IDENTICAL |
| 备份 | `src/backup-v1.07b-20260918-222454/`（`built_DLL.bin` 与 `deployed_DLL.bin` 同 md5）|
| 编译 | `BUILD SUCCESS` |

DLL 内字符串（**"删掉的串必须为 0"**）：

| 串 | 计数 |
|---|---|
| `diag active v1.07b` | 1 |
| `diag active v1.07 ` | **0** |
| `lock RELEASED on the reset edge` | 1 |
| `lock RELEASED after` | **0**（still 重采不在产物里）|
| `magnitude classes differ` | **0**（量级逃逸不在产物里）|
| `non-affine w=` | 1（v0.89 观测仍在）|

回归 `tools/regress_v107_lockrelease.py`：**RESULT OK**，数字表见账本第 14.7 节。

## 11.12 本轮踩的坑（补丁/命令/工具）

- **★ `git commit -F /tmp/xxx` 会失败**：`/tmp` 是 MSYS 路径，Windows 版 git 读不到
  （报 `could not read log file`）。而 `cmd 2>&1 | tail -N && next` 里**管道退出码是 `tail` 的 0**，
  于是 `&&` 链**继续执行了 `git tag -f v1.07b`**，**把 tag 打到了错误的提交 `a40f946` 上**。
  ⇒ 已 `git tag -d` 撤掉重做；**教训：`&&` 后面接的必须是不依赖前一条成功的命令，或改 `;` 后单独校验。**
- **`core.autocrlf=true` + 无 `.gitattributes`**（见 11.13）—— 提交时一串
  `LF will be replaced by CRLF` 警告就是在提示这件事。
- 补丁脚本自身 4 个 bug（打印 `b'\\\\r\\\\n'` 在 f-string 里恒不等 / `str.count(bytes)` 类型错 /
  post-condition 靠运算符优先级碰巧成立 / 行数统计口径），逐个修掉并回读验证。

## 11.13 ★ 一个长期误判的根因：`core.autocrlf=true`

我在账本第 6 章写过"12 个源文件行尾各不相同"。**这个结论部分是我自己造成的**：

- 仓库 **`core.autocrlf=true`**，**没有 `.gitattributes`**；
- ⇒ `git checkout --` 会把仓库里的 LF 规范形式**在落盘时转成 CRLF**；
- 实证：`git checkout -- src/FrameGen.cpp` 后，该文件从 **LF（1364 bare_LF）**
  变成 **CRLF（1364 CRLF）**，md5 从 `0363c183…` 变 `d5c4cf34…`，而 `git status` 说工作树**干净**。
- 2026-09-18 22:24 实测（当前真值）：`FrameGen.cpp` **CRLF 1414 / bare_LF 0**、
  `FrameGen.h` 366、`Streamline.cpp` 2254、`Streamline.h` 384、
  **`DX12SwapChain.cpp` 纯 LF 1806**、`main.cpp` MIXED(162/7)。

⇒ **行尾永远逐文件实测，补丁脚本必须自动探测，不要凭记忆也不要写死。**

## 11.14 仍未验证（不假装）

- **v1.07b 是否真止住冻结**：**未知**。我无法运行游戏。
- **§14.6 的竞态**：故意未修。
- **Modex 闪退**（第三方 `Modex::UIManager::MainWndProc`）：须在 MO2 GUI 手动取消勾选；
  **验证冻结前必须隔离它**，否则结论不可信。
- **RTX 20/30 系**：一行未写。**DLSS5**：代码在，**未上机验证**。

## 11.15 下次开游戏**只看这三条**（`python tools/analyze_session.py`）

1. `build  v1.07b` —— 若报 `PROBLEM: this log was written by ...` ⇒ **DLL 没换上去**，后面都不作数。
2. 第 6 项 `proj00=` 是 **`0.149184`**（世界族持锁）——**不是 `0.8391`**。
3. 第 6 项 `release events: N` 中 **N ≥ 1**（菜单→世界转换触发了释放）。

## 11.16 记忆与技能更新

- 账本 `MFG_MASTER_NOTES.md`：**49,986 → 62,970 B**，追写第 14 章（14.1–14.11）。
- 工作区 `MEMORY.md`：重写至 **2,429 字符**（原 3,709 B 超限被截断），
  版本更新为 v1.07b，新增第 3 条头号教训（"释放路径必须证明它选对了族"），
  修正"FrameGen.cpp 纯 LF"这条**已不成立**的记录。
- 技能 `framegen-diagnosis`：新增第 39 节。
"""


def main():
    raw = io.open(P, "rb").read()
    text = raw.decode("utf-8")
    if "# 11. 22:00–22:25" in text:
        print("REFUSED: section 11 already present")
        return 2
    if not text.rstrip().endswith("`src/Streamline.cpp`。"):
        print("REFUSED: tail does not look like the end of section 10")
        return 3
    res = text + SEC11
    if res.count("# 11. 22:00–22:25") != 1:
        print("REFUSED: marker count wrong after append")
        return 4
    io.open(P, "wb").write(res.encode("utf-8"))
    back = io.open(P, "rb").read().decode("utf-8")
    assert "# 11. 22:00–22:25" in back
    assert "# 10. 21:30–21:50" in back
    print(f"APPLIED. {len(raw)} -> {len(res.encode('utf-8'))} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
