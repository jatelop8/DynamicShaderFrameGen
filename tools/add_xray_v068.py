# -*- coding: utf-8 -*-
"""v0.68 patch -- fix the [CAM] raw sampling rule + add a capture-layer motion trace.

Why this patch exists (the trigger rule in v0.67 was itself defective):
  v0.67 dumped raw camera matrices on `(arrivals % 300) == 1`.  The arrival counter
  is cumulative over the WHOLE run, and the 22:42 run spent 45 s in the main menu
  (~600 arrivals) before only 3 s in the world (~90 arrivals).  So the sample points
  1 / 301 / 601 ALL landed inside the menu and the raw ground truth was never printed
  for the world phase -- exactly the stretch that matters.  That run therefore
  answered none of the questions it was instrumented for.

What v0.68 changes:
  1. DumpCameraSnapshot takes the gate's verdict and fires on: first 2 arrivals,
     any verdict flip (accepted <-> rejected) with a >=0.5 s gap, a 900-arrival
     fallback, capped at 80 dumps.  A "two cameras alternating" event is *defined* by
     verdict flips, so it can no longer be missed, and the log volume stays bounded.
  2. New [CAM] acc line: the accepted camera's world position, per-accept movement,
     and cumulative path length.  This is the single decisive datum for "does the
     captured camera actually track the player".  If the player walks and `path`
     stays at 0.000, the defect is in the capture layer and no reprojection-side fix
     can help.
  3. snapPathLen counter (FrameGen.h).

Safety: assertion-guarded patch.  Every anchor must occur EXACTLY once; any mismatch
=> "REFUSED, nothing written".  Dry run by default; pass --apply to write.

Usage:
    python add_xray_v068.py            # dry run
    python add_xray_v068.py --apply    # write + read back
"""

import sys
import shutil
import datetime
import pathlib

ROOT = pathlib.Path(r"D:/Modding/DynamicShaderFrameGen")
H = ROOT / "src" / "FrameGen.h"
C = ROOT / "src" / "FrameGen.cpp"

# Idempotency guards.  "anchor unique" != "patch not already applied" -- inserted
# text does not consume its anchor, so re-running would insert a second copy.
MARKERS = ["v0.68", "a_verdict", "[CAM] acc #", "snapPathLen"]

T = "\t"
I2 = T + T
I3 = T + T + T
I4 = T + T + T + T


def j(*lines):
    return "\n".join(lines)


# ---------------------------------------------------------------- FrameGen.h ----
# FrameGen.h is pure CRLF, FrameGen.cpp is pure LF (verified with a byte count).
# Each file's inserted text must use its own EOL or the file ends up with mixed
# line endings.  Single-line anchors match either way.
H1_OLD = j(
    I2 + "float snapAcceptDist = 0.0f;      // 上一次被接受的到达距离",
)
H1_NEW = "\r\n".join([
    I2 + "float snapAcceptDist = 0.0f;      // 上一次被接受的到达距离",
    I2 + "// v0.68: accepted-snapshot cumulative travel. Stays ~0 while the player walks",
    I2 + "// => the captured camera is not tracking the view camera (capture-layer defect).",
    I2 + "float snapPathLen = 0.0f;",
])

# -------------------------------------------------------------- FrameGen.cpp ----
C1_OLD = j(
    I2 + '// 每 300 个到达快照打一组**原始矩阵**（约 10s 一次）。这是离线核对量级、',
    I2 + '// 行列式、以及"两组数据差在哪"的唯一地面真值 —— 不要只靠推导。',
    I2 + "inline void DumpCameraSnapshot(const FrameBuffer& b, std::uint64_t a_n)",
    I2 + "{",
    I3 + "if ((a_n % 300u) != 1u)",
    I4 + "return;",
)
C1_NEW = j(
    I2 + "// v0.68：**触发规则本身是缺陷，必须修**（这不是加诊断，是修诊断）。v0.67 写成",
    I2 + "// 「每 300 个到达打一次」，但到达计数是**整场累计**的：22:42 那次 45 秒主菜单",
    I2 + "// （~600 到达）之后才进世界 3 秒（~90 到达）⇒ 取样点 1/301/601 全部落在菜单里，",
    I2 + "// **世界阶段一条原始矩阵都看不到** —— 恰恰是最需要它的那一段。改为：",
    I2 + "//   · 前 2 个到达必打；",
    I2 + "//   · 判定翻转（接受 <-> 拒绝）时打，两次之间至少隔 0.5 s；",
    I2 + "//   · 每 900 个到达兜底一次；",
    I2 + "//   · 全场最多 80 组。",
    I2 + '// "两组相机交替"这个事件的签名就是判定翻转，所以它必然被采到，日志量仍有上界。',
    I2 + "inline void DumpCameraSnapshot(const FrameBuffer& b, std::uint64_t a_n, int a_verdict)",
    I2 + "{",
    I3 + "static int lastVerdict = -1;",
    I3 + "static auto lastDump = std::chrono::steady_clock::now() - std::chrono::seconds(30);",
    I3 + "static std::uint32_t dumps = 0;",
    I3 + "const bool flip = (a_verdict != lastVerdict);",
    I3 + "lastVerdict = a_verdict;",
    I3 + "if (dumps >= 80u)",
    I4 + "return;",
    I3 + "const auto now = std::chrono::steady_clock::now();",
    I3 + "const bool gapOk = std::chrono::duration<double>(now - lastDump).count() >= 0.5;",
    I3 + "if (!((a_n <= 2u) || ((a_n % 900u) == 1u) || (flip && gapOk)))",
    I4 + "return;",
    I3 + "lastDump = now;",
    I3 + "++dumps;",
)

C2_OLD = j(
    I2 + "++snapArrivals;",
    I2 + "DumpCameraSnapshot(a_src, snapArrivals);",
    "",
    I2 + "const float px = a_src.CameraPosAdjust[0];",
)
C2_NEW = j(
    I2 + "++snapArrivals;",
    "",
    I2 + "const float px = a_src.CameraPosAdjust[0];",
)

C3_OLD = j(
    I3 + "++snapRejectZero;",
    I3 + 'SKSE::log::warn("[CAM] #{} rejected: empty/garbage snapshot (magVP={:.6g} devVP={:.6g})",',
)
C3_NEW = j(
    I3 + "++snapRejectZero;",
    I3 + "DumpCameraSnapshot(a_src, snapArrivals, 2);",
    I3 + 'SKSE::log::warn("[CAM] #{} rejected: empty/garbage snapshot (magVP={:.6g} devVP={:.6g})",',
)

C4_OLD = j(
    I4 + "++snapRejectJump;",
    I4 + 'SKSE::log::info("[CAM] #{} JUMP rejected: pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} "',
)
C4_NEW = j(
    I4 + "++snapRejectJump;",
    I4 + "DumpCameraSnapshot(a_src, snapArrivals, 3);",
    I4 + 'SKSE::log::info("[CAM] #{} JUMP rejected: pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} "',
)

C5_OLD = j(
    I2 + "frameBufferCopy = a_src;",
    I2 + "++snapAccept;",
    I2 + "snapAcceptDist = snapHaveLast ? std::sqrt(d2) : 0.0f;",
)
C5_NEW = j(
    I2 + "frameBufferCopy = a_src;",
    I2 + "++snapAccept;",
    I2 + "snapAcceptDist = snapHaveLast ? std::sqrt(d2) : 0.0f;",
    I2 + "snapPathLen += snapAcceptDist;",
    I2 + "DumpCameraSnapshot(a_src, snapArrivals, 1);",
    I2 + "// v0.68：捕获层的**运动轨迹**。这是判定「被捕获的相机到底有没有跟着玩家动」",
    I2 + "// 的那一行 —— 若玩家在走而这里 move/path 恒为 0.000，则根因在捕获层（读到的",
    I2 + "// 相机数据不跟踪真实相机），任何重投影侧的修法都救不了。节流 0.25 s，最多 200 行。",
    I2 + "{",
    I3 + "static auto lastAccLog = std::chrono::steady_clock::now() - std::chrono::seconds(30);",
    I3 + "static std::uint32_t accLogs = 0;",
    I3 + "const auto now = std::chrono::steady_clock::now();",
    I3 + "if (accLogs < 200u &&",
    I4 + "(snapAccept == 1u || std::chrono::duration<double>(now - lastAccLog).count() >= 0.25)) {",
    I4 + "lastAccLog = now;",
    I4 + "++accLogs;",
    I4 + 'SKSE::log::info("[CAM] acc #{} pos=({:.2f},{:.2f},{:.2f}) move={:.4f} path={:.2f} "',
    I4 + '"devVP={:.6g} detVP={:.6g} magVP={:.6g} consecJmp={}",',
    I4 + "snapAccept, px, py, pz, snapAcceptDist, snapPathLen,",
    I4 + "camDev(a_src.CameraViewProjUnjittered), camDet3(a_src.CameraViewProjUnjittered),",
    I4 + "camMag(a_src.CameraViewProjUnjittered), snapConsecReject);",
    I3 + "}",
    I2 + "}",
)

EDITS = [
    ("FrameGen.h: snapPathLen counter", H, H1_OLD, H1_NEW),
    ("FrameGen.cpp: dump trigger rule (core fix)", C, C1_OLD, C1_NEW),
    ("FrameGen.cpp: move dump call off the top", C, C2_OLD, C2_NEW),
    ("FrameGen.cpp: dump on zero-reject", C, C3_OLD, C3_NEW),
    ("FrameGen.cpp: dump on jump-reject", C, C4_OLD, C4_NEW),
    ("FrameGen.cpp: dump + motion trace on accept", C, C5_OLD, C5_NEW),
]


# Both source files are valid UTF-8 with Chinese comments (verified).  Reading them
# as latin-1 would turn those comments into mojibake, so an anchor containing any
# comment text could never match the Unicode literals in this script.  Use UTF-8
# with surrogateescape: byte-lossless for anything, and the anchors match.
# newline="" is equally mandatory -- universal-newline mode would convert the .h's
# CRLF to LF on read and write LF back on Windows, silently rewriting every EOL.
def read_text(p):
    with open(p, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
        return f.read()


def write_text(p, s):
    with open(p, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(s)


def main():
    apply = "--apply" in sys.argv

    # --- guard 1: idempotency. Marker check MUST run before the anchor check,
    # because inserted text leaves its anchor intact -> a re-run would look legal.
    for p in (H, C):
        s = read_text(p)
        for m in MARKERS:
            if m in s:
                print("REFUSED, nothing written -- marker %r already in %s" % (m, p.name))
                return 2

    # --- guard 2: every anchor must occur exactly once
    texts = {H: read_text(H), C: read_text(C)}
    for label, path, old, _new in EDITS:
        n = texts[path].count(old)
        if n != 1:
            print("REFUSED, nothing written -- %s: anchor occurs %d time(s), need exactly 1" % (label, n))
            return 2
        print("OK  %s  (anchor occurs 1 time)" % label)

    if not apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply to write.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in (H, C):
        bak = path.with_name(path.name + ".bak-" + stamp)
        shutil.copy2(path, bak)
        print("backup %s" % bak.name)

    before = {p: len(texts[p].encode("utf-8", errors="surrogateescape")) for p in (H, C)}
    for _label, path, old, new in EDITS:
        texts[path] = texts[path].replace(old, new, 1)
    for path in (H, C):
        write_text(path, texts[path])
        after = len(texts[path].encode("utf-8", errors="surrogateescape"))
        print("wrote %s  %d -> %d bytes (%+d)" % (path.name, before[path], after, after - before[path]))

    # --- independent read-back (never trust the writer's own report)
    print("\nread-back:")
    for path, needle in ((H, "snapPathLen"), (C, "a_verdict"), (C, "[CAM] acc #"), (C, "snapPathLen += ")):
        s = read_text(path)
        print("  %-14s %-18s %s" % (path.name, needle, "FOUND" if needle in s else "MISSING"))

    # --- line endings must be unchanged: .h pure CRLF, .cpp pure LF
    print("\nEOL check:")
    ok = True
    for path, want_crlf in ((H, True), (C, False)):
        d = path.read_bytes()
        crlf = d.count(b"\r\n")
        lf = d.count(b"\n")
        stray = d.count(b"\r") - crlf
        pure = (crlf == lf) if want_crlf else (crlf == 0)
        good = pure and stray == 0
        ok = ok and good
        print("  %-14s CRLF=%-5d LF=%-5d stray_CR=%-3d %s" % (
            path.name, crlf, lf, stray,
            ("OK pure " + ("CRLF" if want_crlf else "LF")) if good else "MIXED!"))
    print("RESULT: %s" % ("OK" if ok else "EOL DAMAGED"))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
