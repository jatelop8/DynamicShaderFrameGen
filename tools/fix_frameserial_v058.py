#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复：v0.50 移除 OnMainUpdateJitter 后 engineFrameCount 再无写入点（恒 0），
导致 EnsureFrameToken 的"新帧"判据永远为真 -> slGetNewFrameToken 只调一次 ->
frame index 恒 0、frameToken 永不推进 -> slSetConstants 每帧被拒(27) ->
每帧常量(jitter/相机矩阵/pacer 数据)永不更新 -> 频闪。

方案：引入 frameSerial，由 DX12SwapChain::Present 每帧唯一推进。

安全：marker 幂等守卫（先于锚点检查）+ 锚点唯一性断言 + 备份 + 落盘回读。
默认干跑，--apply 才落盘。
"""
import sys
import os
import shutil
import datetime

ROOT = r"D:\Modding\DynamicShaderFrameGen"
H = os.path.join(ROOT, "src", "Streamline.h")
CPP = os.path.join(ROOT, "src", "Streamline.cpp")
SWAP = os.path.join(ROOT, "src", "DX12SwapChain.cpp")

# ---------------------------------------------------------------- 编码/行尾探测
# 本机实测：Streamline.h 是 CRLF，Streamline.cpp / DX12SwapChain.cpp 是 LF。
# 全部归一成 LF 内部处理，写回时按原行尾还原，落盘后校验 bare-LF/stray 为 0。
def read_text(path):
    raw = open(path, "rb").read()
    bom = raw[:3] == b"\xef\xbb\xbf"
    body = raw[3:] if bom else raw
    eol = "crlf" if b"\r\n" in body else "lf"
    if eol == "crlf":
        body = body.replace(b"\r\n", b"\n")
    if bom:
        text = body.decode("utf-8")
        enc = "utf-8-sig"
    else:
        try:
            text = body.decode("utf-8")
            enc = "utf-8"
        except UnicodeDecodeError:
            text = body.decode("gbk")
            enc = "gbk"
    return text, enc, bom, eol

def write_text(path, text, enc, had_bom, eol):
    body = text.replace("\n", "\r\n") if eol == "crlf" else text
    data = body.encode(enc)
    if had_bom and not data.startswith(b"\xef\xbb\xbf"):
        data = b"\xef\xbb\xbf" + data
    open(path, "wb").write(data)

def eol_report(path, expected_eol, baseline_lines):
    """落盘后校验：行尾一致、无 stray 反相行尾、行数增量符合预期。"""
    raw = open(path, "rb").read()
    crlf = raw.count(b"\r\n")
    lf_all = raw.count(b"\n")
    bare = lf_all - crlf
    lines = lf_all
    if expected_eol == "crlf":
        good = bare == 0
        detail = "CRLF=%d bare_LF=%d" % (crlf, bare)
    else:
        good = crlf == 0
        detail = "LF=%d stray_CRLF=%d" % (lf_all, crlf)
    return good, "%s lines=%d(was %d, +%d)" % (detail, lines, baseline_lines, lines - baseline_lines)

# ---------------------------------------------------------------- 补丁定义
# (label, path, marker, old, new)
EDITS = [
    # ---------- A. Streamline.h：新增 frameSerial 成员 ----------
    (
        "A. Streamline.h 新增 frameSerial",
        H,
        "frameSerial = 0;",
        "\t\tsl::ViewportHandle viewport{ 0 };\n"
        "\t\tsl::FrameToken* frameToken = nullptr;\n"
        "\t\tHMODULE interposer = nullptr;\n",
        "\t\tsl::ViewportHandle viewport{ 0 };\n"
        "\t\tsl::FrameToken* frameToken = nullptr;\n"
        "\t\t// v0.58: per-frame serial, advanced once per Present (see DX12SwapChain.cpp).\n"
        "\t\t// v0.50 removed OnMainUpdateJitter, which was the ONLY writer of\n"
        "\t\t// engineFrameCount -> it stays 0 forever, while EnsureFrameToken still\n"
        "\t\t// used it as the new-frame test. Result: slGetNewFrameToken was called\n"
        "\t\t// exactly once, frame index stayed 0, frameToken never advanced, and\n"
        "\t\t// slSetConstants got rejected every frame (eErrorDuplicatedConstants=27)\n"
        "\t\t// -> per-frame constants (jitter / camera matrices / clipToPrevClip /\n"
        "\t\t// frame time / Reflex pacer data) were never refreshed -> bad\n"
        "\t\t// reprojection of every generated frame -> constant flicker.\n"
        "\t\t// v0.31 already hit this exact class of bug (\"must pass a frame count\n"
        "\t\t// or the frame number stalls\"); v0.50 reintroduced it.\n"
        "\t\tstd::uint32_t frameSerial = 0;\n"
        "\t\tHMODULE interposer = nullptr;\n",
    ),
    # ---------- B. Streamline.cpp：判据换源 ----------
    (
        "B. EnsureFrameToken 判据改用 frameSerial",
        CPP,
        "const std::uint32_t frame = frameSerial;",
        "\t\tstatic std::uint32_t s_lastFrame = UINT32_MAX;\n"
        "\t\tconst std::uint32_t frame = Get().engineFrameCount;\n"
        "\t\tif (frame == s_lastFrame)  // \u540c\u5e27 \u2192 \u590d\u7528\u5df2\u6709 token\n",
        "\t\tstatic std::uint32_t s_lastFrame = UINT32_MAX;\n"
        "\t\t// v0.58: judge on frameSerial (advanced once per Present). engineFrameCount\n"
        "\t\t// has had no writer since v0.50 -> always equal -> never took a new token.\n"
        "\t\tconst std::uint32_t frame = frameSerial;\n"
        "\t\tif (frame == s_lastFrame)  // \u540c\u5e27 \u2192 \u590d\u7528\u5df2\u6709 token\n",
    ),
    # ---------- C. Streamline.cpp：常量写入成功/失败计数 ----------
    (
        "C. slSetConstants 成功/失败计数",
        CPP,
        "constants: ok={} fail={}",
        "\t\tif (SL_FAILED(r, slSetConstants(c, *frameToken, viewport)))\n"
        "\t\t\tSKSE::log::error(\"[Streamline] slSetConstants failed: {}\", (int)r);\n",
        "\t\t// v0.58: success/failure accounting (throttled). This is the direct\n"
        "\t\t// evidence for \"are per-frame constants actually reaching DLSS-G\":\n"
        "\t\t// climbing fail=27 (eErrorDuplicatedConstants) means the frame slot is\n"
        "\t\t// not advancing, constants stay stale, and every generated frame is\n"
        "\t\t// reprojected with old motion/jitter -> flicker.\n"
        "\t\tstatic std::uint32_t constsOk = 0, constsFail = 0;\n"
        "\t\tstatic int constsLastR = 0;\n"
        "\t\tif (SL_FAILED(r, slSetConstants(c, *frameToken, viewport))) {\n"
        "\t\t\t++constsFail;\n"
        "\t\t\tconstsLastR = (int)r;\n"
        "\t\t} else {\n"
        "\t\t\t++constsOk;\n"
        "\t\t}\n"
        "\t\tif (((constsOk + constsFail) % 120) == 0)\n"
        "\t\t\tSKSE::log::info(\"[Streamline] constants: ok={} fail={} lastR={} serial={} token={:p}\",\n"
        "\t\t\t\tconstsOk, constsFail, constsLastR, frameSerial,\n"
        "\t\t\t\tstatic_cast<const void*>(frameToken));\n",
    ),
    # ---------- D. DX12SwapChain.cpp：每帧推进 ----------
    (
        "D. Present 每帧推进 frameSerial",
        SWAP,
        "++fg.streamline.frameSerial;",
        "\t\t\tfg.streamline.EnsureFrameToken();\n"
        "\t\t\t// v0.32\uff08\u5bf9\u9f50 open-shaders Streamline.cpp:890-924\uff09\uff1aReflex sleep \u5148\u4e8e\n",
        "\t\t\t// v0.58: the single per-frame advance point. Drives both the\n"
        "\t\t\t// new-frame test in EnsureFrameToken and the frame index handed to\n"
        "\t\t\t// slGetNewFrameToken. Must run before any SL call of this frame.\n"
        "\t\t\t++fg.streamline.frameSerial;\n"
        "\t\t\tfg.streamline.EnsureFrameToken();\n"
        "\t\t\t// v0.32\uff08\u5bf9\u9f50 open-shaders Streamline.cpp:890-924\uff09\uff1aReflex sleep \u5148\u4e8e\n",
    ),
]


def main():
    apply = "--apply" in sys.argv

    # ---- 1) marker 幂等守卫（必须最先，插入型改动不消耗锚点）----
    cache = {}
    for label, path, marker, old, new in EDITS:
        if path not in cache:
            cache[path] = read_text(path)
        text = cache[path][0]
        if marker in text:
            print("REFUSED: [%s] marker already present -> already applied, nothing written" % label)
            print("         marker: %r" % marker)
            return 1

    # ---- 2) 锚点唯一性断言（0 = 过期，>1 = 不唯一）----
    for label, path, marker, old, new in EDITS:
        text = cache[path][0]
        n = text.count(old)
        print("[anchor] %-38s count=%d" % (label, n))
        if n != 1:
            print("REFUSED: [%s] anchor count=%d (must be exactly 1) -> nothing written" % (label, n))
            return 1

    # ---- 3) 干跑预览 ----
    print()
    print("all anchors OK, %d edit(s) across %d file(s)" % (len(EDITS), len(cache)))
    for label, path, marker, old, new in EDITS:
        print("   %-38s delta=%+d bytes" % (label, len(new) - len(old)))
    if not apply:
        print()
        print("DRY-RUN only. re-run with --apply to write.")
        return 0

    # ---- 4) 备份 + 落盘 ----
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(r"D:\workbuddy2\backup", "frameserial_" + stamp)
    os.makedirs(bak, exist_ok=True)
    newtexts = {}
    for label, path, marker, old, new in EDITS:
        text = newtexts.get(path, cache[path][0])
        assert text.count(old) == 1, "re-check failed for " + label
        newtexts[path] = text.replace(old, new, 1)

    for path, text in newtexts.items():
        base = os.path.basename(path)
        shutil.copy2(path, os.path.join(bak, base + ".bak"))
        _, enc, had_bom, eol = cache[path]
        write_text(path, text, enc, had_bom, eol)
        print("WROTE %s  (enc=%s bom=%s eol=%s)" % (base, enc, had_bom, eol))

    # ---- 5) 回读验证（逐 marker grep + 行尾完整性）----
    print()
    ok = True
    for label, path, marker, old, new in EDITS:
        after = read_text(path)[0]
        hit = marker in after
        grew = len(after) > len(cache[path][0])
        print("[verify] %-38s marker=%s grew=%s" % (label, hit, grew))
        if not (hit and grew):
            ok = False
    # 关键：确认旧引用真的消失
    cpp_after = read_text(CPP)[0]
    stale = "Get().engineFrameCount" in cpp_after
    print("[verify] stale 'Get().engineFrameCount' gone: %s" % (not stale))
    if stale:
        ok = False
    # 行尾完整性
    for path in newtexts:
        baseline = len(cache[path][0].split("\n")) - 1
        good, detail = eol_report(path, cache[path][3], baseline)
        print("[EOL]    %-24s %s  %s" % (os.path.basename(path), "OK" if good else "BAD", detail))
        if not good:
            ok = False
    print()
    print("RESULT: %s" % ("OK - patched and verified" if ok else "FAILED - inspect manually"))
    print("backup dir: %s" % bak)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
