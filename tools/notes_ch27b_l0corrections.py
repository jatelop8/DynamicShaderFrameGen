#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Append §27.10 to MFG_MASTER_NOTES.md -- the corrections found during the L0
second pass (brain): the matChanges rate, and the fact that the world DOES
contain real camera writes (proven by the v1.08 MOTION probe, an independent
witness).

Idempotency guard: refuses when the section header is already present.
Ledger is PURE LF.  Splice guard: file must end with exactly one newline.

Usage:
    python tools/notes_ch27b_l0corrections.py            # dry run
    python tools/notes_ch27b_l0corrections.py --apply    # write
"""
import sys
import pathlib

LEDGER = pathlib.Path(r"D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md")
MARKER = "### 27.10 ★ L0 第二遍"

BODY = """### 27.10 ★ L0 第二遍（过脑子）翻出来的两条更正 + 一条独立证据链

写卡片的最后一步我按 L0 回去做「反向假设」，把日志又翻了一遍。
**翻出两个我自己写错的数字，和一个此前被我判为「未证」其实已经证了的事实。**
记在这里，因为这正是 L0 第二遍存在的理由 —— 第一遍（手脚）全部通过，错的是脑子。

#### 27.10.1 更正①：`matChanges` 的增速是 +195/s，不是 +40/s

我之前写「`matChanges` +40/s = 2×24 ⇒ 真相机 24/s 与恒定假相机交替」。**错的。**

实测采样（同一份 18:20 日志，`[CAM] pub` 行）：

| 时刻 | `matChanges` |
|---|---|
| `18:22:11.115` | `5571` |
| `18:22:12.142` | `5771` |
| `18:22:13.164` | `5971` |
| `18:22:14.191` | `6171` |

⇒ `600 / 3.076 s =` **+195/s**，即 `arrivalsPerSec(591)` 的 **33%**。
按真实帧率 24 折算 ⇒ **每渲染帧约 8 个互不相同的矩阵**被写进这个缓冲。

**教训**：`2×24` 那套算术是我**先有结论再去凑数字**（"交替 ⇒ 应该是 2 倍"），
而不是从采样点直接算。**报任何一个速率之前，先把两个采样点的时间戳和数值并排写下来。**

#### 27.10.2 更正②：「世界内有没有相机写」——已证：有

上一版我写「世界内到底有没有相机写仍未证」。**已经证了，而且证据早就在日志里。**

`v1.08` 时代留下的 `[MOTION]` 告警里带着 `p00 / p23` 探针 —— 它当时是为查「矩阵非仿射」插的，
**与本次推理没有任何关系，所以它是一条干净的独立证人**：

```
[18:21:43.764]  p00 cur=1.1918  prev=0.0000 | p23 cur=-15.000636 prev=0.000000
[18:21:44.357]  p00 cur=1.0000  prev=1.1918 | p23 cur=-0.111111  prev=-15.000636
```

- `p00=1.1918, p23=-15.000636` ⇒ **真实相机**（`p23 = -zn`，`zn = 15.000636`，
  与菜单期手算的 `15.011` 同源）。
- `p00=1.0000, p23=-0.111111` ⇒ **正交冒牌货**（`-0.111111` 与 §27.4 反解出的
  `z' = 1.1111z - 0.1111` 是同一个数）。

**★ 两条独立证据链给出同一个 `-0.111111`**（FLD 转储 vs MOTION 探针），
并且第二条是**为别的问题写的**，不可能被我这一轮的推理污染。

⇒ 世界内确实有真相机写进这个 CB，且我们的 hook 在 `18:21:43.764`
（`MENU EDGE open=0` 之后 21 毫秒）**确实抓到了它**。
⇒ 「世界里根本没有相机写」这个最坏分支**排除**。v1.13 的闸门撞上它的概率很高。

#### 27.10.3 顺带查出：v1.11 的接管判据当时挑错了族

```
[CAM] #14583 FOREIGN TAKEOVER (v1.11): locked proj00=0.8391 has gone 208 publishes with an
unchanged matrix while the refused family proj00=1 travelled 289.8 units
- adopting pos=(-464.8,349.9,100.5)
```

它把「锁着的族不动」读成"这是菜单相机"、把「被拒的族在动」读成"这才是玩家"。
在那一刻这个推理是合理的 —— **但被拒的族 `proj00=1` 恰恰就是正交冒牌货**
（采纳的 `pos=(-464.8,349.9,100.5)` 与 `[CAM] raw #31501` 读到的
`(-464.5398,349.1476,101.2857)` 是同一个点）。
接管之后 `proj00=1` 占住锁、`famRej` 从 `4157` 涨到 `15792`，**真相机被当异族拒掉**。

**本轮按纪律不改接管判据**（一次只动一处可证伪的东西）。
内容门比改判据更稳的地方正在这里：正交写进不到发布 ⇒ 接管**没有机会**再采纳它。

#### 27.10.4 ★ L30 补充：两条独立证据链，才敢把「未证」改成「已证」

> **一条证据链只能产生一个结论，不能产生一个置信度。**
> 把「未证」改写成「已证」之前，必须找到**第二条来源不同**的证据，
> 且最好是**为别的问题而插的**探针 —— 那种探针不可能被当前的推理污染。

配套的自我检查：**翻完一条链就下结论，是"先有结论再找证据"的伪装。**
本条更正就是活例子：第一条链（FLD）我读了两遍都只得出"那不是相机"，
直到我去翻 MOTION 探针才同时拿到「世界里有真相机写」这个正面事实。
"""


def main() -> int:
    apply = "--apply" in sys.argv
    if not LEDGER.exists():
        print(f"REFUSED: ledger not found: {LEDGER}")
        return 1

    raw = LEDGER.read_bytes()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    if crlf != 0:
        print(f"REFUSED: expected a PURE LF ledger, found {crlf} CRLF (bare LF {bare})")
        return 1

    text = raw.decode("utf-8")

    if MARKER in text:
        print(f"REFUSED, nothing written: {MARKER!r} already present")
        return 1

    if not text.endswith("\n"):
        print("REFUSED: ledger does not end with a newline; inspect before appending")
        return 1
    if text.endswith("\n\n\n"):
        print("REFUSED: ledger already ends with two blank lines; inspect before appending")
        return 1

    out = text + "\n" + BODY + "\n"

    # --- post-conditions ---
    # ★ Assert on BODY only, never on `out`: the ledger already contains earlier
    #   text (including the wrong +40/s claim this section corrects), so counting
    #   on `out` measures pre-existing content as well.  (Same class of bug as
    #   "assert on declarations, not identifiers".)
    probes = [
        ("section header", BODY.count("### 27.10 ★ L0 第二遍"), 1),
        ("correction 1 label", BODY.count("更正①：`matChanges` 的增速是 +195/s，不是 +40/s"), 1),
        ("correction 2 label", BODY.count("更正②：「世界内有没有相机写」——已证：有"), 1),
        ("MOTION evidence", BODY.count("p23 cur=-15.000636 prev=0.000000"), 1),
        ("measured rate arithmetic", BODY.count("600 / 3.076 s"), 1),
        ("L30 addendum header", BODY.count("#### 27.10.4"), 1),
    ]
    bad = [f"{name}: got {got}, want {want}" for name, got, want in probes if got != want]
    if bad:
        print("FAIL post-conditions:\n  " + "\n  ".join(bad))
        return 2

    # --- the result must actually contain the body ---
    if BODY not in out:
        print("FAIL: BODY is not present verbatim in the result")
        return 2

    new_crlf = out.encode("utf-8").count(b"\r\n")
    if new_crlf != 0:
        print(f"FAIL: result would contain {new_crlf} CRLF (ledger must stay pure LF)")
        return 2

    if not apply:
        print("DRY RUN OK (nothing written)")
        print(f"  would grow: {len(raw)} -> {len(out.encode('utf-8'))} bytes")
        print(f"  lines: {text.count(chr(10))} -> {out.count(chr(10))}")
        print("  re-run with --apply to write")
        return 0

    LEDGER.write_bytes(out.encode("utf-8"))
    print("APPLIED")
    print(f"  bytes: {len(raw)} -> {len(out.encode('utf-8'))}")
    print(f"  lines: {text.count(chr(10))} -> {out.count(chr(10))}")
    print("  CRLF: 0 (pure LF preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
