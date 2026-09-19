#!/usr/bin/env python3
"""Update the DFG index (MEMORY.md) from v1.21 to v1.22.

Five replacements, each anchored on text that must occur exactly once.
Dry-run by default; --apply writes. No EOL conversion is performed: the file is
read and written as bytes-through-str with surrogateescape, so whatever mix of
line endings it has is preserved exactly.
"""
import ast
import hashlib
import sys
from pathlib import Path

TARGET = Path("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/MEMORY.md")

R1_OLD = "MFG_MASTER_NOTES.md`（33 章）"
R1_NEW = "MFG_MASTER_NOTES.md`（34 章）"

R2_OLD = """## ★★★★★ v1.21 现状（代码 commit `741fbe8` = tag `v1.21`；账本+交付卡已到 `ebc2233`，工作区干净）
DLL 1,358,336 B md5 `60378778d6171d3e2651ff3758b47fcb`（build == 部署）；
INI md5 `4dabf3bdee6633400ff4cccff70871e4`（19,761 B、CRLF 343 / 裸 LF 0，**源树与部署一致**）。
| 键 | 值 | 作用 |
|---|---|---|
| `Provider` / `DLSSGFramesToGenerate` / `MFGMaxFramesOverride` | 1 / 3 / 3 | DLSSG + 请求并放开 4x（**4x 只在这条路**）|
| `NRAllowWithFrameGen` | 0 | 本轮把 DLSS5 请出 4x 实验 |
| `MenuDisableFrameGen` | 1 | 保留（闸门已修好）|
| **`MenuGuardFader`** | **1（新）** | 淡出菜单只在「还不该在世界里」时算菜单 |
| **`InteropFenceWait`** | **1（新）** | 恢复 v0.75 拆掉的 D3D11→D3D12 定序 |

**两个新键只需改 INI，不必重编译**：`InteropFenceWait=0` 回 v0.75 行为；`MenuGuardFader=0` 让淡出菜单永不算菜单
（v0.96 会因此进不去游戏，慎用）。补丁 `tools/patch_v121_{fence_and_fader,ini}.py` + `patch_v121b_nrguard.py`
（干跑默认 + 标记幂等）。"""

R2_NEW = """## ★★★★★ v1.22 现状（代码 commit `f7fe9b7` = tag `v1.22`，工作区干净）
DLL 1,362,944 B md5 `5f1793d921493f1e94fc23aad4a8b390`（build == 部署）；
INI md5 `efce89119d840670e519d219749a6476`（20,658 B、纯 CRLF 358 行、裸 LF 0，**源树与部署一致**）。
| 键 | 值 | 作用 |
|---|---|---|
| `Provider` / `DLSSGFramesToGenerate` / `MFGMaxFramesOverride` | 1 / 3 / 3 | DLSSG + 请求并放开 4x |
| `NRAllowWithFrameGen` | 0 | DLSS5 暂不叠加（一次只变一件事）|
| `MenuDisableFrameGen` | 1 | 保留 |
| `MenuGuardFader` | 1 | 闸门判据 = `ui->GameIsPaused()`，**不再看 `Fader Menu`** |
| `InteropFenceWait` | 1 | 恢复 v0.75 拆掉的 D3D11→D3D12 定序 |
| **`PixelProbe`** | **1（新）** | 1 Hz 读回背缓冲中心 64×64；唯一能说「画面没动」的仪器 |

**★★★ 4x 已单独跑通（00:30 局）**：`ask=4 accepted=4`、看门狗逐秒 `ratio=4.00`（`00:31:05`、`00:31:06`）。
所以「4x 请求从来没被发出去」**只对 22:54 那局成立**（那次被 v0.63 闸门按住 571/572 帧）。
**但现在 4x 已经在上屏而用户仍报冻结 ⇒ 冻结有第二个成因，且不在请求路径上。**
IN 键可回退的：`PixelProbe=0`、`InteropFenceWait=0`、`MenuGuardFader=0`。
**A（fader 闸门改 `GameIsPaused`）不是 INI 开关**，回退 = `git checkout v1.21 -- src/Streamline.cpp` + 重编译。
补丁 `tools/patch_v122_pixelprobe.py`（干跑默认 + `afterline` 整行锚点 + `POST_GONE`）。"""

R3_OLD = """## ★ 下一局判据
| 看到 | 结论 |
|---|---|
| 进世界就 `presented per real frame = 4` | 机制①成立：以前**请求发不出去**，不是运行时拒绝 |
| 走动时画面活（`plrD>0`、`clipDev` 明显 >0） | 机制②成立：围栏是根因 → 再开 `NRAllowWithFrameGen=1` 冲用户目标 |
| 仍定死 + `hrsD` **仍在走** | 冻结在**呈现路径** → **做像素探针**（读回 back buffer 像素，唯一能把「世界在动」与「屏幕陈旧」分开的仪器）|
| 仍定死 + `hrsD==0` | 游戏时钟停了 ⇒ 冻结在**游戏里**，插件不背这口锅 |
| `stage=` 停在 `d3d12 queue Wait` | 围栏不可用 → `InteropFenceWait=0` |"""

R3_NEW = """## ★ 下一局判据（v1.22 已装像素探针，先看 `[PIXEL]`）
| 看到 | 结论 |
|---|---|
| 进世界就 `presented per real frame = 4` 且 `[PIXEL] chg=1` | **通了**：4x 生效 + 画面在动 |
| `[PIXEL] VERDICT`（连续 10 秒同哈希） | **陈旧缓冲已证** ⇒ 冻结在呈现路径 ⇒ 沿围栏/呈现链继续 |
| `[PIXEL]` 行完全没出现 | 先看有没有 `probe armed` / `probe disabled: …` —— 别把「仪器没跑」读成「画面健康」（L39）|
| `chg=1` 但用户仍说冻 | 冻结在**读回点之后**（composite/present 之后）⇒ 查交换链呈现链 |
| `hrsD==0` | 游戏时钟停了 ⇒ 冻结在**游戏里**，插件不背这口锅 |
| `stage=` 停在 `d3d12 queue Wait` | 围栏不可用 → `InteropFenceWait=0` |"""

R4_OLD = "  判据三连：① `which <tool>` 先确认存在；② **必须有一个必然存在的串做阳性对照**；③ 看退出码。"
R4_NEW = """  判据三连：① `which <tool>` 先确认存在；② **必须有一个必然存在的串做阳性对照**；③ 看退出码。
- **L40：给「无缩进」文件（ini/csv/json）做锚点要用整行匹配。** 别用「前缀换行」去凑唯一性 ——
  针以 `\\n` 开头时 `line_indent()` 的 `rfind("\\n",0,i)` 求出的「缩进」是**上一行的内容**，
  拼出的 old 带 `\\r` 而永远匹配不上。v1.22 给补丁加了 `afterline` 模式：按 EOL 切行、
  要求**恰好一行**等于该针。**另：后置条件里必须有一条是「什么都没改」无法满足的**
  （`POST_GONE`：旧表达式在结果文本里计数必须为 0），否则断言会被"没改"满足 —— 33 章踩过两次。
- **L41：方法名/类名不是字符串。** `grep -a -c GameIsPaused <dll>` = 0 **是对的**（对照
  `GetSingleton`/`Calendar`/`InterfaceStrings` 全 0；`IsMenuOpen` 那个 1 来自日志格式串）。
  **要证明一次「调用」改动进了二进制，看目标文件修饰符号**：
  `grep -a '?GameIsPaused@UI@RE@@QEAA_NXZ' build/NINJA/.../Streamline.cpp.obj` = 1，
  而 `git show HEAD:src/Streamline.cpp | grep -c GameIsPaused` = 0 ⇒ 只可能来自本次改动。
  **字符串计数对方法名恒为 0，是结构性假阴性。**"""

R5_OLD = "- **4x + DLSS5 同时**：用户总目标，尚未成功（本轮先隔离出 4x）。"
R5_NEW = ("- **4x 已单独成功**（`accepted=4` + `ratio=4.00`，00:30 局）；"
          "**4x + DLSS5 同时**仍是用户的总目标，**未成功**（本轮先隔离出 4x）。")

EDITS = [("R1", R1_OLD, R1_NEW),
         ("R2", R2_OLD, R2_NEW),
         ("R3", R3_OLD, R3_NEW),
         ("R4", R4_OLD, R4_NEW),
         ("R5", R5_OLD, R5_NEW)]

POST = ["v1.22 现状（代码 commit `f7fe9b7`",
        "5f1793d921493f1e94fc23aad4a8b390",
        "efce89119d840670e519d219749a6476",
        "`PixelProbe`",
        "L40",
        "L41",
        "?GameIsPaused@UI@RE@@QEAA_NXZ",
        "4x + DLSS5 同时**仍是用户的总目标"]

POST_GONE = ["v1.21 现状", "60378778d6171d3e2651ff3758b47fcb", "4dabf3bdee6633400ff4cccff70871e4",
             "MFG_MASTER_NOTES.md`（33 章）"]


def sha(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def main() -> int:
    apply = "--apply" in sys.argv
    if not TARGET.is_file():
        print(f"REFUSED: {TARGET} not found")
        return 2

    raw = TARGET.read_bytes()
    text = raw.decode("utf-8", "surrogateescape")
    print(f"file {len(raw)} B  md5 {sha(raw)}")

    for label, old, new in EDITS:
        c = text.count(old)
        ok = (c == 1)
        print(f"  anchor {'OK  ' if ok else 'FAIL'} {label}: count={c}")
        if not ok:
            print("REFUSED: anchor is not unique, nothing written")
            return 1
        text = text.replace(old, new, 1)

    ok = True
    for needle in POST:
        c = text.count(needle)
        print(f"  post {'OK  ' if c >= 1 else 'FAIL'} {needle!r} count={c}")
        ok = ok and c >= 1
    for needle in POST_GONE:
        c = text.count(needle)
        print(f"  gone {'OK  ' if c == 0 else 'FAIL'} {needle!r} count={c}")
        ok = ok and c == 0
    if not ok:
        print("REFUSED: post-condition failed, nothing written")
        return 1

    out = text.encode("utf-8", "surrogateescape")
    if not apply:
        print(f"DRY RUN - nothing written. would be {len(out)} B md5 {sha(out)}")
        return 0

    TARGET.write_bytes(out)
    print(f"WROTE {len(raw)} B md5 {sha(raw)} -> {len(out)} B md5 {sha(out)}")
    return 0


if __name__ == "__main__":
    ast.parse(Path(__file__).read_text(encoding="utf-8"))
    raise SystemExit(main())
