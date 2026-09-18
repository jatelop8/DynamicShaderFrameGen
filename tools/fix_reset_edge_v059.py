#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.59 修复：菜单期间 reset 每帧被置位 -> DLSS-G 每帧被要求"丢弃历史"，
却仍在输出 4 帧 -> 每个生成帧都从零历史重建 -> 主菜单静止画面持续闪。

证据（2026-09-17 21:18 运行，DLSSG-Transfusion.log）：
    [MOTION] route=slSetConstants call=0 ... clipToPrev=identity reset=1 ...
    [MOTION] route=slSetConstants call=1 ... clipToPrev=identity reset=1 ...
    [MOTION] route=slSetConstants call=2 ... clipToPrev=identity reset=1 ...
连续三帧（call=0/1/2，间隔 ~26ms）reset 恒为 1，且 cameraPos=(-50,600,80) 有效
=> 相机数据是活的，唯独 reset 每帧被置位。

方案：reset 改为边沿触发 —— 只在"进入菜单的那一帧"置 eTrue。
保留 v0.34 的意图（进菜单时丢弃菜单前遗留的旧数据），但不再每帧打断
DLSS-G 的 temporal 状态。

同时新增 CAM 诊断探针（只打印，不改行为），用于定位 clipToPrev=identity 的
来源：curVP/prevVP 取自引擎 perFrame 常量缓冲的 c24/c32，若 dev 接近 0
说明这两个字段在引擎侧从未被更新。

安全：每条 edit 独立 marker 幂等守卫 + 锚点唯一性断言(count==1)
      + 备份 + 行尾保持 + 落盘回读。默认干跑，--apply 才落盘。
"""
import sys
import os
import shutil
import datetime

ROOT = r"D:\Modding\DynamicShaderFrameGen"
CPP = os.path.join(ROOT, "src", "Streamline.cpp")


# ---------------------------------------------------------------- 编码/行尾探测
# 本机实测：Streamline.cpp 是纯 LF、无 BOM。仍做通用探测以防上游变化。
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


# ---------------------------------------------------------------- 补丁定义
T = "\t"

OLD_RESET = (
    '		c.reset = sl::Boolean::eFalse;\n'
    '		if (auto* ui = RE::UI::GetSingleton()) {\n'
    '			const auto* istrings = RE::InterfaceStrings::GetSingleton();\n'
    '			if (ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||\n'
    '				ui->IsMenuOpen(istrings->journalMenu) || ui->IsMenuOpen("PauseMenu"))\n'
    '				c.reset = sl::Boolean::eTrue;\n'
    '		}\n'
)

NEW_RESET = (
    '		// v0.59：reset 改为**边沿触发**（只在进入菜单的那一帧置位）。\n'
    '		// 之前菜单打开期间每帧都置 eTrue ⇒ 每帧告诉 DLSS-G"这是全新序列、丢掉历史"，\n'
    '		// 而 DLSS-G 仍在输出 4 帧 ⇒ 每个生成帧都从零历史重建 ⇒ 主菜单静止画面持续闪，\n'
    '		// 帧节拍抖动（Transfusion [PERF] Jitter 4.9~15.3ms）。\n'
    '		// 证据：2026-09-17 21:18 运行，Transfusion [MOTION] 连续 call=0..2 上 reset 恒为 1。\n'
    '		// 边沿触发保留 v0.34 的意图（进菜单时丢弃菜单前遗留的旧数据），但不再每帧打断\n'
    '		// DLSS-G 的 temporal 状态。\n'
    '		bool isMenuOpen = false;\n'
    '		if (auto* ui = RE::UI::GetSingleton()) {\n'
    '			const auto* istrings = RE::InterfaceStrings::GetSingleton();\n'
    '			isMenuOpen = ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||\n'
    '				ui->IsMenuOpen(istrings->journalMenu) || ui->IsMenuOpen("PauseMenu");\n'
    '		}\n'
    '		static bool s_wasMenuOpen = false;\n'
    '		c.reset = (isMenuOpen && !s_wasMenuOpen) ? sl::Boolean::eTrue : sl::Boolean::eFalse;\n'
    '		s_wasMenuOpen = isMenuOpen;\n'
    '		{\n'
    '			static std::uint32_t resetProbe = 0;\n'
    '			if (++resetProbe % 240 == 1)\n'
    '				SKSE::log::info("[Streamline] RESET probe: menuOpen={} reset={} (edge-triggered, v0.59)",\n'
    '					isMenuOpen, static_cast<int>(c.reset));\n'
    '		}\n'
)

OLD_PROBE_INT = '			if (++motionProbe % 600 == 1) {'
NEW_PROBE_INT = '			if (++motionProbe % 240 == 1) {'

OLD_PROBE_TAIL = (
    '					dev, r3.x, r3.y, r3.z);\n'
    '			}\n'
    '		}\n'
)

NEW_PROBE_TAIL = (
    '					dev, r3.x, r3.y, r3.z);\n'
    '\n'
    '				// v0.59 CAM probe：定位 clipToPrevClip 恒为单位矩阵的来源。\n'
    '				// curVP/prevVP 取自引擎 perFrame 常量缓冲的 c24/c32；dev(x) 是 x 相对\n'
    '				// 单位矩阵的最大偏差。若 dev(curVP)≈0 而 dev(viewProj)≠0 ⇒ 这两个字段\n'
    '				// 在引擎侧从未被更新（偏移错/字段不存在），需要由 DFG 自己缓存上一帧 viewProj。\n'
    '				auto devOf = [](const Matrix& m) {\n'
    '					float d = 0.0f;\n'
    '					for (int r = 0; r < 4; ++r)\n'
    '						for (int cc = 0; cc < 4; ++cc) {\n'
    '							const float id = (r == cc) ? 1.0f : 0.0f;\n'
    '							float v = m.data[r][cc] - id;\n'
    '							if (v < 0.0f) v = -v;\n'
    '							if (v > d) d = v;\n'
    '						}\n'
    '					return d;\n'
    '				};\n'
    '				SKSE::log::info("[Streamline] CAM probe: dev(curVP c24)={:.4f} dev(prevVP c32)={:.4f} "\n'
    '					"dev(viewProj c16)={:.4f} dev(view c0)={:.4f} pos=({:.1f} {:.1f} {:.1f}) "\n'
    '					"prevPos=({:.1f} {:.1f} {:.1f})",\n'
    '					devOf(curVP), devOf(prevVP), devOf(a_fb.CameraViewProj), devOf(a_fb.CameraView),\n'
    '					a_fb.CameraPosAdjust[0], a_fb.CameraPosAdjust[1], a_fb.CameraPosAdjust[2],\n'
    '					a_fb.CameraPreviousPosAdjust[0], a_fb.CameraPreviousPosAdjust[1],\n'
    '					a_fb.CameraPreviousPosAdjust[2]);\n'
    '			}\n'
    '		}\n'
)

# (label, path, old, new, marker)  marker 用于判断该条是否已经应用过
EDITS = [
    ("reset edge-triggered", CPP, OLD_RESET, NEW_RESET,
     "c.reset = (isMenuOpen && !s_wasMenuOpen) ? sl::Boolean::eTrue : sl::Boolean::eFalse;"),
    ("motion probe interval 600->240", CPP, OLD_PROBE_INT, NEW_PROBE_INT,
     "if (++motionProbe % 240 == 1) {"),
    ("CAM probe", CPP, OLD_PROBE_TAIL, NEW_PROBE_TAIL,
     '"[Streamline] CAM probe: dev(curVP c24)='),
]


def main():
    apply = "--apply" in sys.argv
    print("=" * 74)
    print("v0.59 reset edge-triggered + CAM probe   [%s]" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    src, enc, bom, eol = read_text(CPP)
    print("target : %s" % CPP)
    print("encoding=%s bom=%s eol=%s bytes=%d lines=%d" % (enc, bom, eol, len(src.encode(enc)), src.count("\n")))

    # ---- 1) 逐条判定：已应用 / 可应用 / 拒绝 ----
    print("\n-- anchor check --")
    texts = {CPP: src}
    todo = []
    for label, path, old, new, marker in EDITS:
        t = texts[path]
        if marker in t:
            print("  [done] %-32s already applied, skip" % label)
            continue
        n = t.count(old)
        print("  [%s] %-32s count(old)=%d" % ("ok" if n == 1 else "!!", label, n))
        if n != 1:
            print()
            print("REFUSED: anchor for '%s' matched %d times (need exactly 1)." % (label, n))
            print("Nothing written. Inspect the file and update the anchor.")
            return 1
        todo.append((label, path, old, new, marker))

    if not todo:
        print("\nNothing to do - all edits already applied.")
        return 0

    if not apply:
        print("\nDRY RUN ok (%d edit(s) ready). Re-run with --apply to write." % len(todo))
        return 0

    # ---- 2) 应用 ----
    print("\n-- apply --")
    for label, path, old, new, marker in todo:
        t = texts[path]
        t = t.replace(old, new, 1)
        assert marker in t, "internal error: marker missing after replace"
        texts[path] = t
        print("  patched: %s  (%+d bytes)" % (label, len(new.encode(enc)) - len(old.encode(enc))))

    # ---- 3) 备份 ----
    bak = os.path.join(r"D:\workbuddy2\backup",
                       "reset_edge_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(bak, exist_ok=True)
    shutil.copy2(CPP, os.path.join(bak, "Streamline.cpp.bak"))
    print("\nbackup dir: %s" % bak)

    # ---- 4) 落盘 ----
    newtext = texts[CPP]
    write_text(CPP, newtext, enc, bom, eol)
    print("WROTE %s" % CPP)

    # ---- 5) 回读验证 ----
    print("\n-- verify (read back from disk) --")
    after, enc2, bom2, eol2 = read_text(CPP)
    ok = True
    for label, path, old, new, marker in EDITS:
        hit = marker in after
        stale = old in after if label != "motion probe interval 600->240" else OLD_PROBE_INT in after
        print("  [%s] %-32s marker=%s stale_old=%s" % ("ok" if (hit and not stale) else "!!",
                                                      label, hit, stale))
        if not (hit and not stale):
            ok = False

    raw = open(CPP, "rb").read()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    print("\n  eol: crlf=%d bare_lf=%d (expected eol=%s)" % (crlf, bare, eol))
    if eol == "lf" and crlf != 0:
        print("  !! eol polluted with CRLF"); ok = False
    if eol == "crlf" and bare != 0:
        print("  !! eol polluted with bare LF"); ok = False

    print("\nRESULT: %s" % ("OK - patched and verified" if ok else "FAILED - inspect manually"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
