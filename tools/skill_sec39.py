#!/usr/bin/env python3
"""Append section 39 to the framegen-diagnosis skill."""
import io
import sys

P = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"

SEC39 = """
---

## 39. 相机族锁**没有释放路径**（v1.07b）—— 结掉 §38 末尾那条悬案

§38 末尾写着：「`still=0` ⇒ 从未触发"流断了"。**是否锁死错误族，需要一次"玩家确实在
移动"的运行才能判定。未改动**（v1.00 写它是为修 v0.93 的 CTD）。」

**2026-09-18 22:02 那次运行就是那次判定，答案是：锁死了，而且这是画面不动的第三成因。**
本条把判定方法、修法、以及**我写出来又撤回的一条错误修复**全部固化。

### 39.1 一眼判定的那一行

心跳里的 `proj00=` 打印的是 `snapLockProjValid ? Get().snapLockProj00 : 0.0f` ——
**当前占锁那一族**的投影指纹，**不是**当前到达那一族的。

```
lock(pub/hold/re/still)=11821/2725/2416/0  proj00=0.8391  famRej=309
menu=857 world=94
```

判据：`world` 在涨（已经在世界里渲染）**而 `proj00` 是 0.8391** ⇒
DLSS-G 拿到的是"给一个已经不存在的世界"的相机 ⇒ **画面冻、帧数活**。

### 39.2 三个族的指纹（本整合包实测）

| 族 | `ProjUnj[0][0]` | 位置特征 | 是不是相机 |
|---|---|---|---|
| **A 世界（玩家）** | `0.149184` | 随玩家 glide（`(-50,600,80)` 起） | **是** |
| B 单位/正交 | `1.0` | `(-160,160,128)` 恒定 | 否 |
| **C 3D 菜单** | `0.8391` | `(-243.05,-415.31,118.56)` 恒定 | **否** |

A 与 C 相差 **5.62x**，所以 `±2%` 相对比率测试**足以判别**。C 的证据在 `FrameGen.h`
（row3 `(-0.00391655,0.999991,0.0015,0)`，「not a camera at all, but a mis-offset read of the
perFrame constant buffer」）。

### 39.3 ★ 不要用 `w != 1`（non-affine）当判据 —— v0.89 的注释拦住了我

我一度想用 `CameraViewProjUnjittered[3][3] != 1` 把 C 筛掉。**它筛不出 A 和 C 的区别**：
`FrameGen.cpp` 里 v0.89 的注释已实测 —— 被 `[3][3] != 1` 丢掉的那一族**定位在 glide**
（`pos=(-50.0,880.7,94.3)`，**正是世界相机**），而通过的是**冻结在 `(-160,160,128)`** 的单位族。
⇒ **世界相机与菜单族都是非仿射。** 该 guard 在 v0.89 已被移除（只因它会丢弃 80.6% 的到达，
其中包含真相机）。

### 39.4 ★★ 新铁律：**释放路径必须证明它选对了族**

任何"清掉锁、让下一个到达者接管"的修法**本质是重新掷骰子**。必须回答：**它落到哪个族？**

第一版 v1.07 我加了三条释放路径，其中一条是"异族连续失败 `kCamStillTol(90)` 次就释放并采纳
当前到达"。离线回归量出它的真面目：

```
被弃草稿（隔离，无边缘）   locked proj00=1   pub=700  released=1  world-refusals=744
```

`proj00=1` = **采纳了单位正交族**。原因：那条分支采纳的是"恰好第 90 次非连续的那个到达"，
两个异族交替时第 90 次是谁**取决于到达顺序** ⇒ **用错族换错族**，
而单位正交族的 `clipToPrev` 是 identity —— **恰恰就是冻结本身**。

它并且**重开了 v1.00 故意关上的门**（源码原文）：

> v0.94 re-acquired unconditionally after kCamStillTol non-continuing arrivals, so a foreign
> camera that arrived monotonically for 90 frames was adopted and then "continued" itself
> forever. **That is the freeze.** Only an arrival from the SAME family may take over.

⇒ **已撤回**。有边缘时两个数字量化了害处：`pub=700`（草稿）vs `372`（v1.07b），
差 **328 帧** = 单位族在边沿之前一直占着 `frameBufferCopy`。

### 39.5 ★★ 新铁律：**一个"通过"的回归，若无法让被测改动体现差别，它证明的是别的东西**

第二版回归跑出 `RESULT: OK`，但表里 **`no release` 与 `release` 每一行数字完全相同** ——
释放路径**一次都没改变结果**。也就是说：C1 的"修复"其实**全部由删逃逸贡献**，
释放**零贡献**。若不重写回归，我会带着一条假证据交差。

⇒ **判据**：让回归里**每一条被测改动都至少有一个用例，去掉它结果就变**。
重写后：删逃逸（承重，C1）、边沿释放（补救，C2）、still 重采（有害，C2b），三件事各自被证明。

### 39.6 离线仿真自己的三个口径错误（同类，会重复犯）

1. **`run()` 给 OLD 构件也发了 `request_release()`** —— 而 v1.03..v1.06 **连这个字段都没有**。
   仿真凭空造了一次释放，于是断言"old code released the lock"失败。
   ⇒ **模型必须按构件特性门控，不能共用一条驱动路径。**
2. **参数名与实现不符**（`menu_stops_at_edge` 实际实现成"C 全程不到达"）。
3. **靠到达顺序去构造某个状态不可靠**：v1.03 的逃逸**既是病因也是解药**
   （它允许任何量级不同的族重新夺锁），逃逸期构建会**自己跌回 A**。
   ⇒ **改成直接 `prime()` 预置锁状态**，模型才诚实。

### 39.7 分诊工具 `tools/analyze_session.py` 的三处改动（本工程内）

1. **版本横幅改成硬比对**（`EXPECTED_BUILD`）。**旧正则 `v[\\d.]+` 连 `v1.07b` 都匹配不到**
   （只吃数字和小数点）—— 这是真 bug，不是疏漏。
2. **第 4 项 CAMERA MOTION 剔除 `frames=1` 首个样本**：原本把开机加载的
   `presentAge=19199ms` 报成 "a real hang"；修后 `presentAge max=432ms ... never stalled`。
3. **第 6 项 CAMERA FAMILY LOCK 判据改写**：旧判据要求 `still==0`，而 `still` 只在
   v1.06（一个从不加它的版本）里恒 0。新判据：
   - `famRej` 大 + **世界族持锁** ⇒ **健康**（v1.00 不变式在工作）；
   - `famRej` 大 + **0 次释放** + 确有 `menu>0 && world>60` ⇒ 问题。

### 39.8 ★ 行尾的长期误判根因：`core.autocrlf=true`

本工程 **`core.autocrlf=true`** 且**没有 `.gitattributes`** ⇒ `git checkout --`
会把仓库里的 LF 规范形式**在落盘时转成 CRLF**。实证：`FrameGen.cpp` 从
**LF（1364 bare_LF）** 变成 **CRLF（1364 CRLF）**，md5 变，而 `git status` 说工作树**干净**。
⇒ **"12 个文件行尾各不相同"这类结论可能是 git 规范化造成的假象。**
**行尾永远逐文件实测，补丁脚本必须自动探测。**

### 39.9 ★ 命令链坑：管道会让 `&&` 误判成功

`git commit -F /tmp/msg.txt 2>&1 | tail -8 && git tag -f v1.07b` ——
`git commit` **失败了**（`/tmp` 是 MSYS 路径，Windows 版 git 读不到，报
`could not read log file`），但**管道的退出码是 `tail` 的 0**，于是 `&&` 继续执行，
**把 tag 打到了错误的提交上**（已 `git tag -d` 撤掉重做）。
⇒ **`&&` 后不要挂依赖前一条成功与否的命令；或改为 `;` + 单独校验。**

### 39.10 产物核验（v1.07b，全部通过）

| 项 | 值 |
|---|---|
| 提交 / tag | `01ce63c` / `v1.07b` |
| DLL | 1,325,568 B，md5 `ae44a128c07f02d7d6d70f2a1c76452d` |
| 构建 == 部署 | `cmp` IDENTICAL |
| 编译 | `BUILD SUCCESS` |

DLL 内字符串（**必须验证"删掉的串为 0"，不只验证"加的串存在"**）：

| 串 | 计数 | 含义 |
|---|---|---|
| `diag active v1.07b` | 1 | 横幅已升 |
| `diag active v1.07 ` | **0** | 旧横幅不在 |
| `lock RELEASED on the reset edge` | 1 | 边沿释放进产物 |
| `lock RELEASED after` | **0** | still 重采**不在产物** |
| `magnitude classes differ` | **0** | 量级逃逸**不在产物** |

### 39.11 本章仍未验证 / 已知残留（不假装）

- **v1.07b 是否真止住冻结**：**未知**（我无法运行游戏）。验收＝
  `analyze_session.py` 第 6 项 `proj00=0.149184` 且 `release events ≥ 1`，
  且横幅是 `v1.07b`。
- **残留（故意未修）**：释放是"让下一个到达者建立新族"，**若菜单族在释放后先到**，
  锁又回 `0.8391`，且**任何"异族持锁太久就释放"的设计都救不了**
  （异族位置恒定 ⇒ `continues` 恒真 ⇒ `still` 每帧清零）。
  要真关掉它需要**属性判据**（"某指纹一旦被判为菜单族，在没有菜单打开的帧里不许发布"），
  不是顺序。日志 `proj00=` **一行即可判定**是否落进这个残留。
- **Modex 闪退**（第三方 `Modex::UIManager::MainWndProc`）：须在 MO2 GUI 手动取消勾选；
  **验证冻结前必须隔离它**，否则结论不可信。
- **RTX 20/30 系**：一行未写。**DLSS5**：代码在，**未上机验证**。
"""


def main():
    raw = io.open(P, "rb").read()
    text = raw.decode("utf-8")
    if "## 39. 相机族锁" in text:
        print("REFUSED: section 39 already present")
        return 2
    res = text
    if not res.endswith("\n"):
        res += "\n"
    res += SEC39
    if res.count("## 39. 相机族锁") != 1:
        print("REFUSED: marker count wrong")
        return 3
    io.open(P, "wb").write(res.encode("utf-8"))
    back = io.open(P, "rb").read().decode("utf-8")
    assert "## 39. 相机族锁" in back
    assert "## 38." in back or "真凶二：v1.02c 的相机历史" in back
    print(f"APPLIED. {len(raw)} -> {len(res.encode('utf-8'))} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
