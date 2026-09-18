# -*- coding: utf-8 -*-
"""
Append chapter 19 to MFG_MASTER_NOTES.md: the first flight of the v1.08 probe.

Dry run by default; pass --apply to write. Every anchor must occur exactly once.
The ledger is pure LF, so the anchors are written with the real control
character (the project has been bitten twice by literal backslash-n ending up in
the file).
"""
import io
import sys

PATH = "MFG_MASTER_NOTES.md"
MARKER = "## 第 19 章"

ANCHOR = (
    "\n\n---\n\n---\n---\n\n**本文件维护规则**"
)

BLOCK = """
## 第 19 章 2026-09-19 07:37 —— v1.08 探针构建的第一次上机：**运行有效，但这一趟测不到冻结**

本章每一条都出自 `DynamicShaderFrameGen.log` 的**这一段**运行
（`RUN START 07:36:58.442` → 最后一条 `07:38:10.028`），全部经
`tools/analyze_session.py` 判读。**二进制未改动**，DLL 仍
`0a10b4b637eb…b613`（1,329,664 B，构建 == MO2 部署）。

### 19.1 加载与帧生成：全绿，没有疑问

| 项 | 实测 |
|---|---|
| 横幅 | `[XRAY] diag active v1.08 (probe build, compiled Sep 19 2026 00:06:10)` |
| 启动 | `RUN START 07:36:58` `dll=…\\data\\SKSE\\Plugins\\DynamicShaderFrameGen.dll size=1329664B` |
| 帧生成 | `mult(acc/pres)=4/4`、`mfg(hwMax/reqMax/rungsSkipped)=5/5/0` |
| Reflex | `capFps=39`、`panel=160Hz`、4x ⇒ `~156 presented fps` |
| GPU | `fence 2/2 -> 2080/2080`，`submitted == completed` |
| 渲染循环 | `presentAge max=594ms`，无 stall |

**⇒ v1.08 的探针代码确实被加载并执行了。** 这是本次上机首先确认的事。

### 19.2 ★★★★★ 这一趟**测不到冻结**：心跳与相机运动在时间上完全错开

这是本章最重要的一条，也是 `analyze_session.py` 之前会**误判**的地方。

相机真的动过。`[CAM] acc` 行里的 `path=`（`snapPathLen`，累计路径长）从
`0.00` 涨到 **`153.78`**：

```
07:37:33  move=0.0000  path=0.00    devVP=15.011   ← 静止
07:37:46  move=0.5179  path=5.20    devVP=15.011   ← 开始走
07:37:48  move=0.4637  path=44.63   devVP=15.011
07:37:50  move=0.4465  path=81.26   devVP=15.011
07:37:52  move=0.4107  path=115.05  devVP=15.011
07:37:54  move=0.3751  path=146.05  devVP=15.011   ← 停止
07:37:58  move=0.0000  path=153.78  devVP=2.0001   ← 停住之后
```

**运动窗口 = `07:37:46` – `07:37:54`（约 8 秒）。**

而 8 条完整心跳的时间是：

```
07:37:57  07:37:59  07:38:01  07:38:02  07:38:04  07:38:05  07:38:07  07:38:08
```

**⇒ 一条都不在运动窗口内。全部落在玩家已经停下之后。**

`clipDev` 这 8 条全是 `0.000000` —— 而**相机静止时，identity 就是正确答案**。
所以这 8 个 0 **既不能证明修好了，也不能证明没修好；它们不含关于冻结的信息。**

★ 判读代码原本会把它报成
`PROBLEM: clipToPrevClip was the identity for the WHOLE session`
—— 把一次**成功的静止**读成了**最严重的那种冻结**。已修，见 19.6。

**⇒ 下一次运行的要求：走起来，并且让心跳落在走动的**那几秒**里。**
心跳只在 `world` 帧打，而 `world` 计数从 `07:37:57` 才开始
（`serial=907 menu=903 world=4`）⇒ **玩家进世界后还要再走 10 秒以上，心跳才会覆盖运动。**

### 19.3 ★★★★ 新发现：相机矩阵在 `07:37:54 → 07:37:58` 之间**塌缩**

上表最后两列：`devVP` 从 **15.011** 掉到 **2.0001**，`detVP` 从 **-79.9373**
掉到 **-2.25023**，`magVP` 从 **15.011** 掉到 **2**。

`devVP = camDev(CameraViewProjUnjittered) = max|M - I|`。三个指标同时变小 7 倍。

**⇒ 引擎的 `CameraViewProjUnjittered`（c24）在那一刻换成了另一个矩阵，而且之后
11 秒（124 帧）一直是 `devVP=2.0001`，再没回来。**

**同一秒还发生了两件事（同时，未证明因果）：**

1. `[XRAY] serial=907` 里 `resetTrue=1`、`reset=1`（本次运行唯一的 reset）
2. 两次 `lock RELEASED on the reset edge`：
   ```
   #9907  (was proj00=0.149184 famRej=3681)
   #9954  (was proj00=0.888889 famRej=3724)
   ```
   —— **相邻 116 ms 内族指纹从 `0.149184` 换成了 `0.888889`。**

**★ 这一条仍是「待查」，不是「结论」。**需要下一次运行看：`devVP=2.0001` 是不是
每次进世界都会出现、以及它与 `world` 帧计数、`reset` 的先后关系。**不要拿它当根因。**

### 19.4 ★★★★ 记忆订正：`move=` **不是**死仪表

记忆里把 `move=0.0000` 与 `jitter=(0,0)`、`snapAcceptDist=0` 并列，归为
「无写者的死字段」。**实测这次它有非零值**：`0.5179 / 0.4637 / 0.4465 / 0.4107 / 0.3751`。

代码证据（`src/FrameGen.cpp:999` 附近）：

```cpp
snapAcceptDist = snapHaveLast ? std::sqrt(d2) : 0.0f;
snapPathLen += snapAcceptDist;
...
SKSE::log::info("[CAM] acc #{} pos=({:.2f},{:.2f},{:.2f}) move={:.4f} path={:.2f} ...",
                snapAccept, px, py, pz, snapAcceptDist, snapPathLen, ...);
```

**⇒ `move` = `snapAcceptDist` = 与**上一次被接受的**相机样本的距离（**瞬时**步长）。
`path` = `snapPathLen` = 累计路径长。**

而 `src/FrameGen.cpp:1000` 的自带注释正是为这件事写的：

> v0.68：捕获层的**运动轨迹**。这是判定「被捕获的相机到底有没有跟着玩家动」的
> 那一行 —— 若玩家在走而这里 move/path 恒为 0.000，则根因在捕获层，任何重投影
> 侧的修法都救不了。

**⇒ 本次实测：捕获层跟着玩家动了（`path` 0 → 153.78）。**
**⇒ 所以「捕获层不跟踪真实相机」这个假设被**排除**了，问题在重投影侧。**

★ **订正后的死仪表名单**：`jitter=(0,0)`（写者 v0.50 删除）、`mvecScale=1`
（被 `MvecScaleOverride=1.00` 钉死）、INI `EnableUpscale`/`PresetDLSS`
（PARSED but NOT WIRED）。**`move` 不在其中** —— 它之前显示 0 是因为**当时相机确实没动**。

### 19.5 ★★★★ 探针读错了抽象层：`CameraProj`(c8) 不是族锁的 `ProjUnj`(c40)

v1.08 的探针读 `a_fb.CameraProj.data[0][0]`（c8），给出 **`p00(c/p)=1.1250/1.1250`**。

而族锁报的是 `proj00=0.888889`，并且 `[CAM] raw #1 ProjUnj` 打印
`ProjUnj[0][0] = 0.149184`（世界族）。

**两者关系：`1 / 1.1250 = 0.888889`（精确到 6 位有效数字）。**

**⇒ `CameraProj`(c8) 与 `CameraProjUnjittered`(c40) 在同一帧上是**互为倒数**的，
不是同一个矩阵的两个版本。** 探针读出来的数因此**不能**与 0.149184 / 0.8391 那张
族指纹表比对。

**★ 这是 §43.3「一个读数只对应一个候选，而且要选对抽象层」的第四次违反 —— 而且是在立下这条规矩的同一轮里。**

**⇒ 待办（要重编译，故未在本轮做）**：探针改读 `CameraProjUnjittered`(c40)，
并在心跳里补打 `P23`（透视/正交判别），让 `p00` 与族锁同源。

**★ 顺带澄清**：本轮 `p00` 的 8/8 两侧一致仍然有意义 —— 它说明**两侧取自同一矩阵**
（对候选 (a)「两侧投影不同」不利）。但因为 `clipW` 全程 = 1，本来也不需要判 (a)/(b)。

### 19.6 判读层修掉两个缺陷（都在 `tools/analyze_session.py`）

**(1) 横幅正则被 v1.08 自己打破。** 正则要求 `\\(compiled`，而 v1.08 的横幅是
`(probe build, compiled …)` ⇒ **匹配失败**，输出
`build (no [XRAY] banner found)` + `PROBLEM: no banner at all`。
**⇒ 一次成功的加载被报成失败。** 已改为 `\\((?:[^)]*?)compiled ([^)]+)\\)`。
`EXPECTED_BUILD` 同时从 `v1.07c` 更新为 `v1.08`。

**(2) `clipDev == 0` 缺少前提。** 见 19.2。新增：从 `[CAM] acc` 行取 `move=` 建
**运动窗口**，与心跳时间戳求交。

★ **这里又踩了一个坑，值得单独记：第一版用 `path=`（累计值）建窗口。累计量单调
递增、永不回落 ⇒ `path > 0` 恒真 ⇒ 窗口一直盖到日志末尾 ⇒ 报「8 of 8 心跳在运动窗口内」，
**恰好把结论反过来了**。改用 `move=`（瞬时）后正确报「0 of 8」。**
**⇒ 通用规则：用累计量做时间窗口的边界，必然恒真。窗口要用**瞬时**量建。**

现在的三种结局互斥：

| 条件 | 判读 |
|---|---|
| 相机从未移动 | `NO DATA: … that is the correct answer, not a finding` |
| 移动过，但心跳全在窗口外 | `NO DATA: … cannot tell a freeze from a standstill` |
| 移动过，且窗口内有心跳 | `PROBLEM: pinned at identity for the whole run` ← **真缺陷** |

回归 `tools/regress_v108_p00.py` 新增 **CASE F / CASE G** —— 两份日志**只差心跳时间**，
判据必须给出相反结论。5 个旧 CASE + 2 个新 CASE 全部 PASS。

### 19.7 本次运行里还没有解释的计数（原样记录，不解释）

| 字段 | 值 | 说明 |
|---|---|---|
| `engPrevZero` | **121** | 引擎的 `CameraPreviousViewProjUnjittered` 全程是**零矩阵** ⇒ 与 16.x 的「引擎 prev 是僵死常量」一致，**但这次是"零"不是"等于 cur"** |
| `famRej` | 6330 | 族拒绝数；`lock(pub/hold/re/still)=6452/6331/4/2` |
| `shapeRej` | 9480（**74.2%**） | `snap(shapeRej)` 比例 |
| `resets` / `frozenRep` | **8036 / 4746** | `gate(resets/frozenRep)` —— 插件**自己**判定的「冻结重复」有 4746 次 |
| `hist(hit/miss)` | 120/1 | 相机历史命中 120、未命中 1 ⇒ **历史是活的** |
| `camPrev(ok/used)` | 1/120 | `camPrevOk` 是**每帧布尔**（`Streamline.cpp:704` `bool camPrevOk = false;`），1 = 本帧有；120 = 累计使用 ⇒ **正常**，不是缺陷 |
| `clipDevMax` | 0.0000 | 全程 0 |

★ **`resets=8036` 与 `frozenRep=4746` 与「相机静止 11 秒」是矛盾的量级**（总帧仅 1027）
—— 这两个计数器数的是**相机块**不是帧。**下次带上 `[CAM] acc` 的 `#N` 与心跳 `serial`
一起对齐，才能确定它们的单位。**

### 19.8 下一次运行：照旧四步，但把走动放到**心跳开始之后**

1. MO2 取消勾选 `Modex.dll`
2. 进游戏，**等到确认已进入世界**（横幅已有 v1.08，看画面上 4x 已在跑）
3. **先站着不动约 10 秒**（让心跳先跑起来）→ **然后持续走动 + 转视角 10 秒以上**
   → 再站住 5 秒
4. 退出，`python tools/analyze_session.py`

**判据（这一版）：**
- ① 横幅 `v1.08`
- ② `clipW == 1.000000`
- ③ **第 4 节必须打出 `heartbeats inside the moving window: N of M` 且 `N > 0`**
  —— 这是这一趟能不能得出结论的**先决条件**，不是结论本身
- ④ 若 ③ 满足且 `clipDev` 仍全 0 ⇒ **真缺陷实锤**
- ⑤ 若出现 `[MOTION]` 行 ⇒ 读其 `p00 cur/prev` + `mag invSrc` 判 (a)/(b)
  （**但注意 19.5：那个 p00 来自 c8，本轮不能与族表比对**）

★ **仍未动二进制**：以上全部是工具与文档改动。DLL 保持 `0a10b4b6…b613`。
"""


def main():
    raw = io.open(PATH, "rb").read()
    src = raw.decode("utf-8")

    if "\r\n" in src:
        print("REFUSED: ledger is not pure LF (CRLF=%d)" % src.count("\r\n"))
        return 1
    if MARKER in src:
        print("REFUSED: %r already present - this patch has run before" % MARKER)
        return 1

    n = src.count(ANCHOR)
    print("anchor occurrences: %d (must be 1)" % n)
    if n != 1:
        print("REFUSED, nothing written")
        return 1

    out = src.replace(ANCHOR, "\n\n---\n" + BLOCK.rstrip("\n") + ANCHOR)

    checks = [
        ("chapter 19 heading", "## 第 19 章" in out),
        ("19.2 window", "运动窗口 = `07:37:46` – `07:37:54`" in out),
        ("19.3 collapse", "devVP` 从 **15.011** 掉到 **2.0001**" in out),
        ("19.4 move correction", "`move` = `snapAcceptDist`" in out),
        ("19.5 layer", "互为倒数" in out),
        ("19.6 cumulative trap", "累计量做时间窗口的边界，必然恒真" in out),
        ("19.7 unit doubt", "数的是**相机块**不是帧" in out),
        ("19.8 prerequisite", "先决条件" in out),
        ("maintenance rule last", out.rstrip().endswith("只在第 9 章与末尾追加。")),
        ("maintenance count", out.count("**本文件维护规则**") == 1),
    ]
    ok = True
    for label, cond in checks:
        print("  %-28s %s" % (label, "OK" if cond else "FAIL"))
        ok = ok and cond
    if not ok:
        print("REFUSED, nothing written")
        return 1

    print("bytes %d -> %d (+%d)" % (len(src.encode()), len(out.encode()),
                                    len(out.encode()) - len(src.encode())))
    if "--apply" in sys.argv:
        io.open(PATH, "wb").write(out.encode("utf-8"))
        print("APPLIED")
    else:
        print("DRY RUN - pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
