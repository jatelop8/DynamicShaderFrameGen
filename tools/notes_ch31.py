#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append ledger chapter 31 and daily note 6.26.  LF-only, marker-guarded."""
import sys
import pathlib

LEDG = pathlib.Path("D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md")
DAY = pathlib.Path("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/2026-09-19.md")

LM = "## 31. 第 31 章"
DM = "## 6.26 22:54 那局"


def load(p):
    b = p.read_bytes()
    if b"\r\n" in b:
        print("REFUSED: %s is not LF-only" % p.name)
        sys.exit(1)
    return b.decode("utf-8"), b


def save(p, s):
    p.write_bytes(s.encode("utf-8"))


LEDGER = """
## 31. 第 31 章　22:54 那局 + v1.19：**用户一句「怎么动啊」把两天的问题换掉了**

### 31.1 决定性的一句

问用户「你说的『卡』，画面到底是哪一种」，四个选项里他选了 **「画面完全定死」**；
问「那 7 秒内你有没有按过键盘」——**「画面卡死了，怎么动啊？」**

**⇒ 这一句把 v1.18 的整个前提推翻了。** 22:02 / 22:22 / 22:38 / 22:54 四局，
世界段分别只有 4.5 / 2.2 / 2 / 6.8 秒、`keys=0x0`、`dc=0`、`plrD≈0` ——
**那不是「玩家站着不动」，是「画面从进世界那一刻就定死，用户看了一眼就强退」。**
`keys=0x0` 是**结果**，不是证据：一张不变的脸不会让人想去按键。

**⇒ v1.18 加的那四个「上游见证」回答的是一个没人问的问题。**
L33 描写的那层含糊（「玩家没动」与「世界冻结」同形）消失了，
换上来一层更利的：**渲染循环活着，画面不活。**

### 31.2 新判据表：这一层含糊住在「游戏边界」的两侧

| 事实 | 来源 | 说明 |
|---|---|---|
| `watchdog: alive=1 focus=1 presentAge=13/0/1/36ms frames 528→643 dsync=0` | 独立线程 | **渲染循环全程活着**，30 帧/秒 |
| 日志在 `22:55:06.773` **句中截断**，无 shutdown、无崩溃转储 | 两个日志文件 | **进程是被强杀/卡死后杀掉的** |
| `eye=(-243.05,-415.31,118.56)` 逐字不变 | 相机链 | 相机不动（但那是结果） |
| `clipDev=0.000061 clipW=1.000000` ⇒ `clipToPrevClip=I` | 相机链 | 画面＝重复上一帧 |
| `DLSSG presented per real frame = 4 (status=0)`、`mult(acc/pres)=4/4` | 插帧 | **4x 一直在产出** |
| `DLSSNR frames=539 status=initialized version=310.8.0.0` | DLSS5 | **NR 一直在跑** |

**⇒ 渲染线程活着 + 画面定死 + 每一个真实帧都被 4x 复制** = 只有一种形状：
**喂给 DLSS-G 的那张彩色缓冲是陈旧的。**

### 31.3 ★★★ INI 自己写明了机制（这是本轮最重的一条）

`DynamicShaderFrameGen.ini` 第 214–222 行，v1.01 自己的注释：

```
; 1 = NR runs first on the real frame and DLSS-G then interpolates the
;     neural-rendered result. The order is already correct in Present()
;     (NR writes swapChainBufferWrapped, which is what EvaluateDLSSG reads,
;      with the D3D11->D3D12 fence between them).
; Start at 0 if the picture flickers; raise NRRenderScale cost awareness
; first - full-resolution NR on every frame is the expensive part.
NRAllowWithFrameGen=1
```

**「NR 写 `swapChainBufferWrapped`，而 `EvaluateDLSSG` 读的就是它」** ——
**NR 的写入如果不落地（fence/互操作失败），DLSS-G 每个真实帧读到的都是同一张陈旧缓冲
⇒ 画面完全定死，而 `Present` 一直成功、`presentAge` 一直正常。**

**⇒ 这正是观测到的形状。而且 `NRAllowWithFrameGen` 是 v1.01 才有的，
它之前的任何版本都没有这条串联——与「冻结从 MFG 这条支线开始出现」完全吻合。**

### 31.4 v1.19 做了什么（零行为改动，只读）

| 见证 | 取法 | 能回答 |
|---|---|---|
| `hrsD` | `RE::Calendar::GetSingleton()->GetHoursPassed()` 的每秒增量 | **游戏逻辑在不在跑** |
| `rawD` | `Calendar->rawDaysPassed * 24` 的每秒增量 | 同上，**另一条路**取同一个量 |
| `paused` | `RE::UI::GetSingleton()->GameIsPaused()` | 游戏自己说暂停没有 |
| `ld` / `fade` | `IsMenuOpen("Loading Menu")` / `("Fader Menu")` | 卡在加载/黑屏淡入淡出没有 |

**两个时钟是有意取两条路**：`GetHoursPassed()` 走 `gameDaysPassed` 这个 TESGlobal，
`rawDaysPassed` 是引擎自己累加的裸 float。**任一个在动就是证明；两个同时不动才是结论。**

**⇒ 判据：**
- `hrsD > 0` 而画面仍定死 ⇒ **游戏在模拟，陈旧的帧是我们的**（⇒ 查 NR→DLSSG 的交接）。
- `hrsD == 0` 而 watchdog 仍在出帧 ⇒ **游戏被暂停** ⇒ 那么「两天在追的
  `clipToPrevClip=I`」只是**症状**，不是病。

### 31.5 两处我自己的错（都在落盘/编译阶段被拦住，没进游戏）

**① `GetKeyboard()` 拖垮链接（14 个 LNK2001）。** 引擎侧按键见证
（`RE::BSInputDeviceManager::GetSingleton()->GetKeyboard()->IsPressed(...)`）
会让链接器从 `CommonLibSSE.lib` 里拖出 `BSWin32KeyboardDevice.cpp.obj` 与
`BSKeyboardDevice.cpp.obj`，这两个 TU 引用了 14 个 `RE::BSInputDevice` 的虚函数，
而预编译库里没有它们的定义。**⇒ 整个见证删掉**（OS 侧 `GetAsyncKeyState` 已经回答了
「有没有按键」，它是四个里最不重要的一个）。

**② 我把 `L(...)` 的闭合括号写成了字符串。** 手写 `Edit` 时把

```python
    "\\t\\t\\t\\t\\tstatic bool  s_liveRawHave = false;",
)
```

写成了 `")"` ——**闭合括号变成了一个字符串**，于是 `L(` 永不闭合，
`ast.parse` 报 `'(' was never closed line 52`，而**词法器扫描显示「未闭合的括号在第 52 行」**，
肉眼看那一行完全正常。

**⇒ 新增强制步骤：任何补丁脚本，在运行它之前先 `ast.parse` 它自己。**
```bash
python -c "import ast;ast.parse(open('tools/patch_xxx.py',encoding='utf-8').read());print('syntax OK')"
```
**⇒ 根因是同一类：我手写补丁文本。凡是手写的，必须先过机器（词法器/编译器）再看结果。**

### 31.6 ★ L35：v1.18b「修」了一个不存在的 bug

v1.18b 把 `s_plrStep = sqrt(...)` 改成 `+=`，理由写在 commit 里：
「`AcceptCameraSnapshot` 每秒跑约 400 次，所以赋值让 `plrD` 变成两次到达之间（~2.5ms）的位移」。

**⇒ 这个前提是错的。** `AcceptCameraSnapshot` **函数**确实每秒被调用约 400 次，
但那段见证代码在**每秒执行一次的块**里（与 `snapPcRead = 0;`、pub 行、FAM 普查同块）。
实测佐证：日志里 `[CAM] PC` 每秒恰好一行，`read=425` 是「这一秒内读了几次」。

**⇒ `=` 与 `+=` 在这个位置等价**（一秒只加一次）。v1.18b 无害，但它是**多余的**。

**⇒ L35 = L34 的第三种形态：L34 是「读错了字段的语义」，
L35 是「读错了代码的位置」——**同一个我在同一天里第三次拿「函数」当「代码块」**。
**⇒ 强制检查项：给别人报一个数值的量纲之前，先确认那段代码在**哪个块**里，而不是它在哪个函数里。**

### 31.7 本轮的 Experiment（INI，一行，可秒退）

```ini
NRAllowWithFrameGen=1   →   NRAllowWithFrameGen=0
```
- 备份：`src/backup-ini-20260919-2310/DynamicShaderFrameGen.ini.bak`（md5 `a19307d47caeb513b9ef6a16c4a83a42`）
- 改后：md5 `ed9655ad2bd0d2576d7f7e9d200a3f4c`（CRLF 259 / 裸 LF 0，14,525 B）
- 一行还原：`cp src/backup-ini-20260919-2310/DynamicShaderFrameGen.ini.bak "<MO2>/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini"`

**为什么这一行值得先试**：v1.19 是**零行为改动**，所以这一次的运行里
「若画面活过来 ⇒ 一定是 NR↔DLSSG 串联这条」是**无歧义**的；
「若还是定死 ⇒ 不是它」，同时我们拿到了 v1.19 的存活数据。
**两种结果都有信息，没有白跑的可能。**

### 31.8 版本

| 项 | 值 |
|---|---|
| DLL | 1,357,824 B md5 `df726bcd8ce70d800b9d01fc6f45c06f`（build == MO2 部署）|
| `FrameGen.cpp` | 99,971 → **102,934 B**（CRLF 2,098 / 裸 LF 0）|
| commit / tag | `dd1b004` / **`v1.19`** |
| 补丁 | `tools/patch_v119_liveness.py`（4 锚点，干跑默认，重跑 REFUSED）|
| 归档 | `docs/runlogs/2026-09-19-2254-v1.18b-hard-freeze-from-world-entry.*` |
| 回 v1.18b | `git checkout v1.18b -- src/FrameGen.cpp` |
"""

DAILY = """
## 6.26 22:54 那局 + v1.19：用户一句「怎么动啊」把问题换掉了

- **用户答案**：画面**完全定死**；问「那 7 秒内按过键盘吗」→「**画面卡死了，怎么动啊**」。
  ⇒ 四局世界段只有 2–7 秒、`keys=0x0` **不是**「玩家没动」，是**画面从进世界就定死、看一眼就强退**。
  v1.18 的四个见证在回答一个没人问的问题。
- **新形状**：渲染循环活着（watchdog `alive=1 focus=1 presentAge` 个位数 ms、30 帧/秒、无崩溃转储、
  日志句中截断无退出记录）+ 画面定死 + 4x 照常在产出 + DLSS5 `frames=539 initialized`
  ⇒ **喂给 DLSS-G 的彩色缓冲是陈旧的**。
- **INI 自己写明了机制**（第 218 行）：「NR writes swapChainBufferWrapped, which is what
  EvaluateDLSSG reads」⇒ NR 写入不落地 = 每个真实帧读同一张陈旧缓冲 = 画面定死而 Present 照常成功。
  `NRAllowWithFrameGen` 是 **v1.01** 才有的串联，之前没有任何版本有它。
- **已改 INI（一行，可秒退）**：`NRAllowWithFrameGen=1 → 0`；
  备份 `src/backup-ini-20260919-2310/`（原 md5 `a19307d47caeb513b9ef6a16c4a83a42`），改后 md5 `ed9655ad…`。
- **v1.19（零行为改动、只读）**：`hrsD`/`rawD`（游戏时钟两条路取值）+ `paused` + `ld`/`fade`。
  `hrsD>0` 而画面定死 ⇒ 陈旧的帧是我们的；`hrsD==0` ⇒ 游戏被暂停，`clipToPrevClip=I` 只是**症状**。
  DLL 1,357,824 B md5 `df726bcd8ce70d800b9d01fc6f45c06f`；commit `dd1b004`、tag `v1.19`。
- **我自己的三处错**：① 引擎侧按键见证让链接拖出 `BSWin32KeyboardDevice.cpp.obj` ⇒ 14 个 LNK2001 ⇒ 删；
  ② 手写 `Edit` 把 `L(...)` 的闭合括号写成字符串 `")"` ⇒ `ast.parse` 报「第 52 行括号未闭合」⇒
  **新增强制步骤：跑补丁脚本前先 `ast.parse` 它自己**；③ **L35**：v1.18b 那次 `=`→`+=` 修的是**不存在的 bug**
  ——那段见证在**每秒一次**的块里（`[CAM] PC` 每秒恰好一行、`read=425` 是每秒读数），
  我读的是**函数**被调用的频率而不是**代码块**执行的频率。
- 细节一律在账本 `MFG_MASTER_NOTES.md`（§31）。
"""


def main():
    l, lb = load(LEDG)
    if LM in l:
        print("SKIP: ledger already has chapter 31")
    else:
        out = l.rstrip("\n") + "\n" + LEDGER
        save(LEDG, out)
        print("ledger +%d bytes" % (len(out.encode()) - len(lb)))

    d, db = load(DAY)
    if DM in d:
        print("SKIP: daily already has 6.26")
    else:
        out = d.rstrip("\n") + "\n" + DAILY
        save(DAY, out)
        print("daily +%d bytes" % (len(out.encode()) - len(db)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
