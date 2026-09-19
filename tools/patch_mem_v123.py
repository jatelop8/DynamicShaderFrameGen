#!/usr/bin/env python3
"""MEMORY.md index: v1.22 -> v1.23.

Every needle is a unique SUBSTRING of the target line; the payload always
contains the COMPLETE replacement line, so nothing has to be transcribed.
Default is a dry run; --apply writes.
"""
import hashlib
import sys
from pathlib import Path

MEM = Path("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/MEMORY.md")

EDITS = [
    # --- header: chapter count -------------------------------------------
    ("E1 账本章数", "replace", "MFG_MASTER_NOTES.md`（34 章）",
     ["**权威账本 `D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md`（35 章）——动手前先读，改动后追写（只追加，写证据原文）。"]),

    # --- the status block -------------------------------------------------
    ("E2a 现状标题", "replace", "v1.22 现状（代码 commit",
     ["## ★★★★★ v1.23 现状（代码 commit `2acd52f` = tag `v1.23`，工作区干净）"]),
    ("E2b DLL md5", "replace", "DLL 1,362,944 B md5",
     ["DLL 1,368,576 B md5 `83e84a781bf645ec3363b58c5fb671ec`（build == 部署）；"]),
    ("E2c INI 说明", "replace", "20,658 B、纯 CRLF 358 行",
     ["INI md5 `efce89119d840670e519d219749a6476`（**v1.23 未改 INI：零新键**；纯 CRLF 358 行、裸 LF 0，源树 == 部署）。"]),
    ("E2d PixelProbe 行", "replace", "唯一能说「画面没动」的仪器",
     ["| **`PixelProbe`** | **1** | v1.23 修：两相采样（收割上一秒的拷贝）+ 自证告警 + 采 **colorOut**（真正上屏那张）+ `clipDev` 区分「静止」与「冻结」 |"]),
    ("E2e 补丁行", "after", "patch_v122_pixelprobe.py",
     ["补丁 `tools/patch_v123_probe_fix.py`（9 条编辑 / 4 文件；`funcspan` 模式按签名+花括号定位整个函数；重跑 `REFUSED`）。"]),
    ("E2f 本局结论", "after", "冻结有第二个成因，且不在请求路径上",
     ["**★★★ v1.23 补记（00:58 局）**：世界**真的进去了**（`paused=0 ld=0 best=0.00 proj00=0.8391 hrsD>0`），",
      "00:58:49–53 看门狗逐秒 `ratio=4.00`、`dsync=0`、`presentAge 0–18 ms` —— **呈现侧每一项都健康**。",
      "所以「屏幕是死的」与「世界在跑」同时成立 ⇒ **唯一能定案的是像素读回**，而 v1.22 的探针 39 秒零样本。"]),

    # --- the denied list --------------------------------------------------
    ("E3 已否定第 4 条", "after", "把开关翻过去拿到同样故障，才叫**否定**。",
     ["4. **「v1.22 让加载变差 / 这次更糟」不成立**：加载 13.1 s vs v1.21 局 12.3 s；两局指纹逐项相同",
      "   （`stall governor` 2/2、`MOTION` 1/1、`non-affine` 20/21、`presented=1` 10/9）。唯一的差异是",
      "   **探针 0 样本**和**一条被我自己的阈值误报的 verdict**。"]),

    # --- next-run verdicts ------------------------------------------------
    ("E4a 判据标题", "replace", "下一局判据（v1.22 已装像素探针",
     ["## ★ 下一局判据（v1.23 探针已修：**先确认它在采样，再读它**）"]),
    ("E4b PIXEL 行 1", "replace", "进世界就 `presented per real frame = 4` 且 `[PIXEL] chg=1`",
     ["| 每秒一行 `[PIXEL] #N … chg= clipDev= movedThisStreak=` | 仪器活着 ⇒ 它的读数才算证据 |"]),
    ("E4c PIXEL 行 2", "replace", "`[PIXEL]` 行完全没出现",
     ["| `[PIXEL] ERROR: … produced ZERO samples` | **仪器坏了，不是画面正常**（L42）|"]),
    ("E4d PIXEL 行 3", "replace", "`chg=1` 但用户仍说冻",
     ["| `10 identical seconds, but the camera was still` | 站桩 ⇒ **预期行为，不是冻结**（L44）|"]),
    ("E4e 协议", "replace", "按住 W 走 5 秒以上",
     ["运行协议：① 进世界**站着不动 15 秒**；② **按住 W 走 10 秒以上**（VERDICT 需要连续 10 秒且其中 ≥5 秒在动）；③ 再退。"]),

    # --- methodology ------------------------------------------------------
    ("E5 L42/L43/L44", "after", "字符串计数对方法名恒为 0，是结构性假阴性。",
     ["- **L42：仪器必须自证运行过（L39 用在自己代码上）。** 只在成功路径上打日志的探针，",
      "  **失败时和「一切正常」在日志里长得一模一样**（v1.22 探针 armed 后 39 秒零样本，日志看着无异常）。",
      "  必须有一条**独立的**「我没跑起来」告警；v1.23 落地为 armed 15 秒仍 0 样本 ⇒ `log::error`。",
      "- **L43：跨 tick 的生产/消费不能塞进同一个调用。** `CopySubresourceRegion` 与 `Map` 同调用 ⇒",
      "  消费者必然等不到生产者（恒 `DXGI_ERROR_WAS_STILL_DRAWING`），而「失败就重置计时器」还会把节流废掉、",
      "  变成每帧重试。先问：**消费者需要等待生产者吗？** 要，就必须跨帧。",
      "  `DO_NOT_WAIT` 只是让**失败**变便宜，它不会让**成功**出现。",
      "- **L44：一个量只有在「反例下会变」时才是见证。** 哈希连续相同，只在**相机在动**时才等于「画面陈旧」；",
      "  相机静止时插帧输出本来就该与真实帧一致 ⇒ v1.23 把 `clipDev` 与哈希并排记录，",
      "  只有 10 秒里 ≥5 秒相机在动才报 VERDICT，否则明说「这是静止造成的，不是冻结」。"]),
]

# What the RESULT must contain / must not contain.
POST = [
    "（35 章）", "v1.23 现状（代码 commit `2acd52f`", "83e84a781bf645ec3363b58c5fb671ec",
    "零新键", "两相采样", "patch_v123_probe_fix.py", "先确认它在采样",
    "produced ZERO samples", "走 10 秒以上", "L42", "L43", "L44",
    "「v1.22 让加载变差 / 这次更糟」不成立",
]
GONE = [
    "（34 章）", "v1.22 现状（代码 commit", "5f1793d921493f1e94fc23aad4a8b390",
    "走 5 秒以上", "`[PIXEL]` 行完全没出现",
]


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def main() -> int:
    apply = "--apply" in sys.argv
    text = MEM.read_bytes().decode("utf-8", "surrogateescape")
    crlf = text.count("\r\n")
    bare = text.count("\n") - crlf
    eol = "\r\n" if crlf > bare else "\n"
    print(f"file: {MEM}\nbytes={len(text.encode('utf-8', 'surrogateescape'))} crlf={crlf} bare_lf={bare} eol={'CRLF' if eol == chr(13)+chr(10) else 'LF'}\n")

    if "L42" in text:
        print("REFUSED: already applied (L42 present), nothing written")
        return 1

    parts = text.split(eol)
    for label, mode, needle, payload in EDITS:
        hits = [i for i, p in enumerate(parts) if needle in p]
        if len(hits) != 1:
            print(f"REFUSED: {label}: line matches={len(hits)} (must be 1), nothing written")
            return 1
        i = hits[0]
        if mode == "replace":
            parts[i:i + 1] = payload
        elif mode == "after":
            parts[i + 1:i + 1] = payload
        else:
            raise ValueError(mode)
        print(f"  ok  {label:<22} [{'replace' if mode == 'replace' else 'after'}]  {needle[:34]!r}")

    out = eol.join(parts)

    print("\n-- post-conditions --")
    ok = True
    for n in POST:
        c = out.count(n)
        print(f"  post {'OK  ' if c >= 1 else 'FAIL'} {n[:46]!r} count={c}")
        ok &= c >= 1
    for n in GONE:
        c = out.count(n)
        print(f"  gone {'OK  ' if c == 0 else 'FAIL'} {n[:46]!r} count={c}")
        ok &= c == 0

    if not ok:
        print("\nREFUSED: a post-condition failed, nothing written")
        return 1

    if not apply:
        print("\nDRY RUN ok. Re-run with --apply to write.")
        return 0

    before = md5(MEM)
    MEM.write_bytes(out.encode("utf-8", "surrogateescape"))
    print(f"\nwrote {MEM}\n  {before} -> {md5(MEM)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
