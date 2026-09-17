# -*- coding: utf-8 -*-
"""
Append the 17:19 verification-round note to the workspace daily log.

Contract:
  * LOG must be LF. Refuse otherwise (the Edit tool has been seen rewriting line endings).
  * MARKER must NOT already be present - re-running refuses.
  * Prints a diff summary; --apply writes.
"""
import sys
import os

LOG = r"C:\Users\Administrator\WorkBuddy\2026-09-17-11-48-48\.workbuddy\memory\2026-09-17.md"

MARKER = "### 17:19 收尾核验 —— 从日志里读出的事实（未改代码）"

SECTION = """
### 17:19 收尾核验 —— 从日志里读出的事实（未改代码）

**时间线（决定性）**：两个日志（SKSE 插件日志 + DLSSG-Transfusion 日志）的 mtime 都是 `16:34:59`，
而 v0.57 是 `17:13:49` 部署的。⇒ **v0.56 与 v0.57 从未进过游戏**，用户此前三次"还是闪烁"
全部发生在 v0.55 上（该次会话日志里没有 v0.56 的任何新标记行，为证）。

**"多倍帧生成在跑"是运行时自己说的（外部证据，非插件自报）**：
- `[OPTIONS] Game DLSS-G options: structVersion=5 mode=eOn frames=3 uir=0 color=2560x1440 flags=0x00000000`
- `Applied fixed multiplier: 4x, result=0 (eOk)`
- `DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)`
- `[PERF] 4x | Kernel: Ada | FPS: 34.6 (28.89ms) | Jitter: 16.31ms | 1% Low: 30.8 FPS`

**同时，运行时亲手写下错配铁证（即 v0.56 修的那条）**：
```
[MOTION-TAG] type=hudless         rect=(0,0 2560x1440)
[MOTION-TAG] type=scaling-output  rect=(0,0 2560x1440)
[MOTION-TAG] type=depth           rect=(0,0 1706x960)   <-- 1.5x 错配
[MOTION-TAG] type=motion          rect=(0,0 1706x960)   <-- 1.5x 错配
```

**修正上一轮的一处措辞**：插件自身日志第 44 行 `DLSSG presented per real frame = 1 (status=0)
- 1 means NO interpolation` 是 **16:34:53.871 的启动瞬态读数**，174ms 后运行时（16:34:54.045）
即报 `presentation count: 4x`。两者不矛盾：前者读在 options 生效之前。不要把它当成"没插帧"。

**新发现（待进游戏确认，已写进 v0.56 的 MOTION probe 量它）**：
`[MOTION]` 全部 4 次调用（call=0..3）均为 `clipToPrev=identity prevToClip=identity`，
`clipToPrev rows=[1.00000012 0 0 0][0 1 9.3e-10 9.3e-10][0 0 1.00000012 0][0 -1.19e-07 -1.19e-07 1]`，
且四次均 `reset=1`。这些都是**启动期 ~200ms 内**的采样，不能据此判定游戏中仍为 identity。

**另一处观察（非结论）**：Transfusion 的 `D157 midpoint fix` 对 NGX 模型 `.bin`
成功（`redirected 8 dlfg_kernel descriptor(s)`，`midpointPatched=1`），但对
mod 目录内的 `nvngx_dlssg.dll` 报 `no supported temporal descriptor found`，
而驱动目录（DriverStore）内那份 `nvngx_dlssg.dll` 是 `ngxCandidate=0 ngxPatched=0 midpointPatched=0`。
两份 DLL 是否都参与、以哪份为准，尚未验证。

**结论**：静态可达之处已穷尽。剩余三问全部需要进游戏：① extent 修复是否止闪；
② `mvecScale` 是否应回 identity（改 INI 一行，勿重建）；③ `clipToPrevClip` 在游玩中是否仍为 identity。
"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.exists(LOG):
        print("REFUSED - log not found:", LOG)
        return 1
    raw = open(LOG, "rb").read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    stray = raw.count(b"\r") - crlf
    if crlf or stray:
        print("REFUSED - log is not pure LF (CRLF=%d LF=%d stray=%d)" % (crlf, lf, stray))
        return 1
    txt = raw.decode("utf-8")
    if MARKER in txt:
        print("REFUSED - marker already present, refusing to insert twice")
        return 1
    if txt and not txt.endswith("\n"):
        print("REFUSED - log does not end with a newline")
        return 1
    out = txt + SECTION
    print("log      : LF=x%d CRLF=0 stray=0  %d bytes" % (lf, len(raw)))
    print("append   : +%d bytes" % (len(SECTION.encode("utf-8"))))
    print("marker   : NOT present -> safe")
    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply")
        return 0
    open(LOG, "wb").write(out.encode("utf-8"))
    chk = open(LOG, "rb").read()
    print("written  : %d bytes  CRLF=%d LF=%d stray=%d"
          % (len(chk), chk.count(b"\r\n"), chk.count(b"\n"),
             chk.count(b"\r") - chk.count(b"\r\n")))
    assert MARKER in chk.decode("utf-8"), "post-condition failed"
    print("post-condition OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
