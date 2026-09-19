#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notes_ch25_stalepub.py -- append ledger chapter 25 + daily section 6.13 for v1.11.

Same conventions as every other notes_* script in this project:
  * dry run by default, --apply writes
  * marker guard: a second run is REFUSED, so an insertion cannot happen twice
  * EOL is taken from the FILE, not from the payload
  * post-conditions are evaluated on the RESULT text
"""
import sys

LEDGER = "D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md"
DAILY = ("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/"
         ".workbuddy/memory/2026-09-19.md")

MARK_L = "## 25. 第 25 章"
MARK_D = "### 6.14"

LEDGER_BODY = """
## 25. 第 25 章　v1.11 —— 接管门的计数器被它要检测的故障清零（2026-09-19 14:20 那局）

### 25.1 这一章只讲一件事
v1.10 的「会动的族可以接管静止的锁」机制**本身是对的**，但它的**门**是 `snapLockStill >= 30`，
而 `snapLockStill` 被**每一次 accept** 清零。冻结族恰好在 `d2 == 0` 上到达自己的上一个到达点，
所以它 `continues`、所以它被接受、所以计数器回零。**门永远打不开。**

### 25.2 14:20 那局的证据（全部读自 DynamicShaderFrameGen.log，无一推测）
这局是 v1.10 第一次上机，也是第一次有 `[CAM] pub` 探针。

    14:20:33.718  build Sep 19 2026 11:46:58  dll size=1337856B  Provider=1
    14:21:03.345  DLSSNR CHAINED with frame generation (v1.01, NRAllowWithFrameGen=1)
    14:21:03.697  [XRAY] MENU EDGE open=1 serial=2 presentedBefore=0
    14:21:03.697  [XRAY] LONG FRAME 20206.7ms (capUs=12658 mult=1 menu=0)     <- 载入存档
    14:21:03.300  [CAM] raw #1  ... ProjUnj[0][0]=0.149184   pos=(-50.0000,600.0000,80.0000)
    14:24:26.030  [CAM] raw #86401 ... 与 #1 逐字节相同（这 3.5 分钟在主菜单，相机确实静止）
    14:27:38-14:28:08  real=39.0 稳定  hwMax=6 ask=4 accepted=4
    14:28:01.109  FOCUS lost    14:28:11.999  FOCUS regained   (用户切出去 10.9 秒)
    14:28:11.972  [CAM] #181702 FOREIGN TAKEOVER (v1.10): locked proj00=0.149184 has not
                  moved for 30 arrivals while the refused family proj00=1 travelled 255.4
                  units - adopting pos=(-125.8,211.4,189.1)
    14:28:11.973  [CAM] pub #148521 pos=(-125.79,211.45,189.11) matChanges=2  takeover=1
    14:28:12.001  [XRAY] LONG FRAME 10916.8ms           <- 切回来那一下，与 bug 无关
    14:28:12.816  [CAM] MenuDraw entry: ... kMAIN=true kFRAMEBUFFER=false
    14:28:14.271  [XRAY] MENU EDGE open=0 serial=16308   <- 7 分 11 秒后终于进世界
    14:28:14.278  [CAM] #183318 lock RELEASED on the reset edge (was proj00=1    famRej=34258)
    14:28:14.346  [MOTION] clipToPrevClip[3].w=-195.222366 (must be 1)
                  v1.08 PROBE: p00 cur=1.1918 prev=0.0000 | mag invSrc=203.9 prevSrc=15
    14:28:14.412  [CAM] #183366 lock RELEASED on the reset edge (was proj00=0.8391 famRej=34276)
    14:28:15.015  [CAM] pub #149316 pos=(-243.05,-415.31,118.56) move=0.0000 path=151.05
                  matChanges=542 | lock(pub/hold/re/still)=149316/34681/274/0
                  proj00=0.8391 famRej=34411 | fMove=0.0 takeover=1 | ok
    14:28:15.926  [CAM] #183951 family rejected: proj00=1 locked=0.8391 ratio=1.1918
                  pos=(-865.8,657.2,285.8) dist=1251.4 still=8/90
    14:28:18.479  日志停止；watchdog 同时停止，但最后一行 alive=1 presentAge=102ms

### 25.3 从这些数字里能**推出**什么（以及不能）
**能推出**
- 两次 release 相隔 134 ms，中间的 acquire 抓到了 `proj00=0.8391`，此后**再没变过**。
- `matChanges` 从 2 涨到 542 用了 3 秒 —— 这 3 秒里**接管确实让发布流活了**。**机制有效。**
- 之后 `matChanges` 冻结在 542 直到日志结束；`clipDev=0.000061`；`prevPos == pos`。
- `famRej` 从 34276 涨到 34681（<1 s，~100/s），而 `still` 只在 3–8。
- `still` 上不去的原因看代码就明白：`:1073`（`continues` 分支）、`:1069`（step break）、`:933`（acquire）
  三处都写 `snapLockStill = 0`，而 `:1014` 的门要 `>= 30`。
**不能推出**
- 世界内是不是真的"动不了" —— world 只有 34 帧、日志在进世界 4 秒后就停了，用户随后退出。
  watchdog 证明进程活着、帧数在涨、`presentAge=102ms`（≈10 fps）。**"卡死"没有证据，"极慢且画面静止"有。**

### 25.4 修法（v1.11，唯一一处行为改动）
门改盯**发布流的直接测量**，而不是到达侧的代理计数：

    FrameGen.h   新增  std::uint64_t snapPubStale = 0;
    FrameGen.cpp 发布点： if (!same) { ++snapMatChanges; snapPubStale = 0; }
                        else     { ++snapPubStale; }
                 常数：  constexpr std::uint64_t kCamPubStaleTol = 200;   // 替换 kCamForeignMinRej
                 门：    if (snapPubStale >= kCamPubStaleTol &&
                             snapForeignMove >= kCamForeignMoveTol) { ...接管... }
                 心跳：  [CAM] pub ... fMove={} takeover={} stalePub={} | {}
                 verdict：stalePub 超阈时输出 "PROBLEM the published camera has been
                          byte-identical for a long run"

**为什么 200**：冻结族 ~150 次发布/s（14:28:15→18 是 450 次/3 s）⇒ 200 ≈ 1.3 秒的
**可证死**发布流。**第二条件一个字没动**，它仍然是安全性的来源：停住的族贡献不了位移，
所以"玩家本来就站着不动"（此时 identity 的 clipToPrev **是对的**）永远夺不走 anchor。

**为什么只留一个清零点**：补丁里加了断言 `snapPubStale = 0;` 全文**必须恰好出现 1 次**。
第二个写者（accept / release / 定时器）会让停滞自己擦掉自己的证据 —— 那正是这一版要消灭的缺陷。

### 25.5 这一版**没有**做什么
锁状态机、族指纹、release 路径、step-break 逻辑**一行未改**。
唯一的行为差别是"哪个数字开门"，而这个数字从"被故障重置的代理量"变成了"故障本身的直接测量"。
**"为什么接管前会锁到场景固定相机"仍未证** —— v1.11 只保证锁能自愈（~1.3 秒内），不解释它怎么锁错的。

### 25.6 L28（本轮新增）
**「被检测的故障本身会把这个检测器的计数清零」—— 用任何计数器做门之前，先证明这个故障不会重置它。**
判据不是"这个门看起来合理"，而是"走一遍故障路径，看这个计数器还在不在"。
"""

DAILY_BODY = """
### 6.14 14:20 那局：v1.11 —— 接管门的计数器被它要检测的故障清零

**用户报告**：「依旧进入游戏卡住了 动不了」。**实测更精确**：没卡死，是"世界内 10 fps 且画面静止"。

**这局拿到了什么**（全部读自日志）
- `DLSSNR CHAINED with frame generation` 出现 ⇒ 4x 与 DLSS5 **同时在跑**（这一步成了）。
- `hwMax=6 ask=4 accepted=4`、`presented world` 各出 4 flips ⇒ **4x 真的在插**。
- 但 `clipDev=0.000061`、`prevPos=pos`、`matChanges` 冻在 **542** ⇒ 插的是复制品。
- 主菜单里待了 **7 分 11 秒**（`MENU EDGE open=1 serial=2` → `open=0 serial=16308`），
  进世界只有 34 帧，日志 4 秒后停；watchdog `alive=1` ⇒ **用户退出，不是崩溃**。

**根因（代码层，可复现地推出）**
v1.10 的接管门是 `snapLockStill >= 30`，而 `snapLockStill` 被**每一次 accept** 清零
（`FrameGen.cpp:1073/1069/933`）；冻结族以 `d2==0` 到达自己的上一个到达点 ⇒ `continues` 真 ⇒
被接受 ⇒ 计数归零。实测 `still` 全程只在 **3–8**，而 `famRej` 涨到 **34681**。**门永远打不开。**
唯一一次接管发生在 release 刚清过 `snapHaveLast` 之后 —— 而它**证明机制有效**：`matChanges` 2→542/3s。

**v1.11 改了什么（只有一处行为改动）**
门改盯发布流的直接测量 `snapPubStale`（连续多少次发布矩阵逐字节相同），阈值 200（≈1.3 s 的**可证死**流）；
`fMove>=200` 第二条件不变。清零点**只有一处**，并加断言 `snapPubStale = 0;` 全文恰好 1 次。
`[CAM] pub` 增 `stalePub=`；verdict 增 "byte-identical for a long run"。**锁状态机一行未改。**
DLL 1,337,856 B，md5 `75e38aa7…`（build == 部署），commit `dbf278f`，tag `v1.11`。

**L0 两遍自检**
- 第一遍·手脚：双份 md5 一致；行尾 `FrameGen.cpp` 1599 CRLF/裸LF 0、`FrameGen.h` 409/0（基线 1560/0、397/0，
  增量=新增行数）；INI 五键齐（`a19307d4…` 两份一致）；备份存在；锚点 7/7 count==1；幂等守卫重跑 REFUSED(exit=1)。
- 第二遍·脑子：★补丁脚本**自己的后置条件误报过一次** —— 断言"旧常量名不得出现"，而新注释里正当地点了
  旧常量名，`FAIL`。**要断言的是"声明消失"，不是"标识符消失"**（已改断言，并记进 MEMORY.md 补丁铁律第 6 条）。
  ★反向假设：`snapPubStale` 会不会在菜单里就爆表并把 anchor 交给菜单相机？理论可能，但需"被拒族自己走出 200 单位"
  这个第二条件同时成立；菜单里玩家相机本身在动（`matChanges` 在涨），所以不容易触发。**未证，记为残余风险。**
  ★这条路径真会走到吗：`!sameFamily` 分支要求 `snapLockHave` 为真 —— 现实中一直为真。
  ★用户会不会白跑一趟：已核 INI 五键 + DLL 双份 md5；但这趟**仍可能因为残余风险没修好**，所以判据要写清楚。

**下一局的判据**
| 看到什么 | 结论 |
|---|---|
| `FOREIGN TAKEOVER (v1.11)` 后 `matChanges` 持续涨 | 自愈路径生效，发布相机跟着玩家动 |
| 走动时 `clipDev` 明显 > 0（不再恒 `0.000061`） | `clipToPrevClip` 有运动 ⇒ 插帧开始有内容 |
| `stalePub=` 一直很小 | 发布流活着 |
| `stalePub=` 涨到 200 却不接管 | `snapForeignMove` 没到 200 ⇒ 被拒族没有平滑路径，需要第三种判据 |
| `SKSE/DynamicShaderFrameGen.20*.log` 出现 | 归档修对了 |

**未证**：世界内 10 fps 的成因。嫌疑 `RenderResolutionScale=0.44`（渲染 1689×950）而 `NRRenderScale=1.00`
⇒ 每个真实帧做一遍 3840×2160 的 DLSS5 神经渲染。**没测过**，改一个 INI 值即可界定。
"""


def file_eol(path):
    with open(path, "rb") as f:
        b = f.read()
    crlf = b.count(b"\r\n")
    return "\r\n" if crlf > (b.count(b"\n") - crlf) else "\n"


def append(path, marker, body, must_see):
    with open(path, "rb") as f:
        raw = f.read()
    eol = file_eol(path)
    text = raw.decode("utf-8")
    print(f"--- {path}  ({len(raw)} B, eol={eol!r})")
    if marker in text:
        print(f"    REFUSED: {marker!r} already present")
        return 1
    payload = body.replace("\n", eol)
    if not text.endswith(eol):
        payload = eol + payload
    out = text + payload
    bad = [w for w in must_see if w not in out]
    if bad:
        print(f"    REFUSED, nothing written (post-condition {bad})")
        return 2
    out_b = out.encode("utf-8")
    # Preserve the EOL CONVENTION, not the absolute count: an LF-only file must
    # stay LF-only (its bare-LF count legitimately grows), a CRLF-only file must
    # stay CRLF-only. v1.09's lesson was the opposite mistake -- comparing an
    # anchor's EOL instead of the file's.
    if eol == "\r\n":
        ok = (out_b.count(b"\n") - out_b.count(b"\r\n")
              == raw.count(b"\n") - raw.count(b"\r\n"))
    else:
        ok = out_b.count(b"\r\n") == raw.count(b"\r\n")
    if not ok:
        print("    REFUSED, nothing written (EOL convention changed)")
        return 3
    print(f"    ok: {len(raw)} B -> {len(out_b)} B")
    return ("WRITE", path, out)


def main():
    do_apply = "--apply" in sys.argv
    rc = 0
    pending = []
    for path, marker, body, must in [
        (LEDGER, MARK_L, LEDGER_BODY, ["25.6 L28", "snapPubStale", "kCamPubStaleTol"]),
        (DAILY, MARK_D, DAILY_BODY, ["6.14", "snapPubStale", "75e38aa7", "L0 两遍自检"]),
    ]:
        r = append(path, marker, body, must)
        if isinstance(r, tuple):
            pending.append(r[1:])
        else:
            rc |= r
    if rc:
        print("ABORTED")
        return rc
    if not do_apply:
        print("DRY RUN ok -- re-run with --apply to write")
        return 0
    for path, out in pending:
        with open(path, "wb") as f:
            f.write(out.encode("utf-8"))
        print(f"written {path}: {len(out.encode('utf-8'))} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
