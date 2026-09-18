#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.66 patch: mathematical guard on clipToPrevClip + thread hygiene + per-tid counting.

Why (evidence from the 22:31 run):
  * Transfusion [MOTION] recorded TWO tids (42736 / 37436) calling slSetConstants,
    with two completely different camera positions:
        call=0 tid=42736 cameraPos=(-49.504,824.555,89.461)   clipToPrev=identity
        call=1 tid=37436 cameraPos=(-243.049,-415.315,118.624) clipToPrev=non-identity
    Two world positions ~1300 units apart cannot be one camera one second apart.
  * The heartbeat showed the same alternation: curVP=15.0110 / 15.0006 / 2.0001 and
    pos=(-49.5,824.6,89.5) / (-243.0,-415.3,118.6) / (0.0,0.0,1.0).
  * clipDev (= max|clipToPrev - I|) reached 15.002136, and Transfusion's own rows
    show clipToPrev[3][2] = -15.0021362 - a matrix that is NOT a legal reprojection.

The math: clipToPrevClip = inv(cur) x prev. When both frames share the same
projection, the projection terms cancel, so the upper-left 3x3 must have
determinant ~= 1 (a pure rotation). The observed bad frames give det = -31.4 and
det = -0.025. That is decidable, not a guessed threshold - so we can reject them
without any heuristic tuning, and log the observed det range so the claim is
self-verifying on the next run.

Changes (14 edits / 3 files):
  Streamline.h      : diag.tidMarker -> per-tid counters + det accounting
  Streamline.cpp    : det3/setIdentity helpers, per-tid counting, 7 statics ->
                      thread_local, determinant guard, heartbeat fields, VERDICT
  DX12SwapChain.cpp : dlssgFailCount / dlssgDiag -> std::atomic<int>

Idempotency marker: "v0.66: det guard". Dry-run by default; --apply writes.

Usage:
  python tools/add_xray_v066.py            # dry run
  python tools/add_xray_v066.py --apply    # write
"""

import io
import os
import shutil
import sys
import time

FILES = {
    "sl_h": "src/Streamline.h",
    "sl_cpp": "src/Streamline.cpp",
    "dx_cpp": "src/DX12SwapChain.cpp",
}

MARKER = "v0.66: det guard"

# ---------------------------------------------------------------- edits

EDITS = [
    # ---- Streamline.h : diag fields -------------------------------------
    ("sl_h", "diag: tidMarker -> per-tid counters + det accounting",
     "			std::uint32_t tidMarker = 0;",
     "			// v0.66: per-tid call counting. A sentinel (\"multi-thread\" =\n"
     "			// 0xFFFFFFFF) cannot tell a one-off thread handover from real\n"
     "			// concurrency - count each tid separately instead.\n"
     "			std::uint32_t tidA = 0, tidB = 0, tidC = 0;\n"
     "			std::uint64_t tidCallsA = 0, tidCallsB = 0, tidCallsC = 0;\n"
     "			// v0.66: determinant accounting for the clipToPrevClip guard.\n"
     "			// Legal reprojection matrices must have det(upper-left 3x3) ~= 1.\n"
     "			float detMin = 1.0e30f;\n"
     "			float detMax = -1.0e30f;\n"
     "			std::uint64_t detGuard = 0;"),

    # ---- Streamline.cpp : det3 + setIdentity + per-tid counting ---------
    ("sl_cpp", "helpers + per-tid counting",
     "		// 谁在调本函数？钩子/调用点若被两个线程命中，自维护历史会被交错污染 ——\n"
     "		// 让日志回答，不要假设。0xFFFFFFFF = 观察到多个线程。\n"
     "		{\n"
     "			const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());\n"
     "			if (diag.tidMarker == 0)\n"
     "				diag.tidMarker = tid;\n"
     "			else if (diag.tidMarker != tid)\n"
     "				diag.tidMarker = 0xFFFFFFFFu;\n"
     "		}",
     "		// ===== v0.66: det guard =====\n"
     "		// 1) clipToPrevClip = inv(cur) x prev。两帧投影相同时投影项互相抵消\n"
     "		//    ⇒ 左上 3x3 的行列式必须 ≈ 1（纯旋转）。实测坏帧给出 -31.4 / -0.025，\n"
     "		//    那不是任何合法变换；交给 DLSS-G 会让每个生成帧的位移完全错（成片闪）。\n"
     "		//    这是**可判定**的，不是猜出来的阈值 —— 并且会把观测到的 det 范围打进\n"
     "		//    日志，让这个判断在下次运行时自我验证。\n"
     "		auto det3 = [](const sl::float4x4& m) -> float {\n"
     "			const float a = m[0].x, b = m[0].y, c = m[0].z;\n"
     "			const float d = m[1].x, e = m[1].y, f = m[1].z;\n"
     "			const float g = m[2].x, h = m[2].y, i = m[2].z;\n"
     "			return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);\n"
     "		};\n"
     "		auto setIdentity = [](sl::float4x4& m) {\n"
     "			m[0] = { 1.f, 0.f, 0.f, 0.f };\n"
     "			m[1] = { 0.f, 1.f, 0.f, 0.f };\n"
     "			m[2] = { 0.f, 0.f, 1.f, 0.f };\n"
     "			m[3] = { 0.f, 0.f, 0.f, 1.f };\n"
     "		};\n"
     "\n"
     "		// 2) 谁在调本函数？哨兵（多线程 = 0xFFFFFFFF）分不清「一次线程交接」和\n"
     "		//    「真的并发」—— 改成 per-tid 计数，下次日志一眼看出各线程各调多少次。\n"
     "		{\n"
     "			const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());\n"
     "			if (diag.tidA == 0) { diag.tidA = tid; ++diag.tidCallsA; }\n"
     "			else if (diag.tidA == tid) { ++diag.tidCallsA; }\n"
     "			else if (diag.tidB == 0) { diag.tidB = tid; ++diag.tidCallsB; }\n"
     "			else if (diag.tidB == tid) { ++diag.tidCallsB; }\n"
     "			else if (diag.tidC == 0) { diag.tidC = tid; ++diag.tidCallsC; }\n"
     "			else if (diag.tidC == tid) { ++diag.tidCallsC; }\n"
     "		}"),

    # ---- Streamline.cpp : engine-cur frozen detection -> thread_local ---
    ("sl_cpp", "s_lastEngCur group -> thread_local",
     "		static sl::float4x4 s_lastEngCur{};\n"
     "		static bool s_hasLastEngCur = false;\n"
     "		static std::uint32_t s_engCurFrozen = 0;",
     "		// v0.66：函数内 static = 全局共享。若本函数被两个线程调用，线程 B 会覆盖\n"
     "		// 线程 A 的冻结检测状态 ⇒ thread_local。\n"
     "		thread_local sl::float4x4 s_lastEngCur{};\n"
     "		thread_local bool s_hasLastEngCur = false;\n"
     "		thread_local std::uint32_t s_engCurFrozen = 0;"),

    # ---- Streamline.cpp : self-maintained history -> thread_local -------
    ("sl_cpp", "s_prevVP group -> thread_local",
     "		static sl::float4x4 s_prevVP{};\n"
     "		static bool s_hasPrevVP = false;",
     "		// v0.66：thread_local。跨线程共享这份历史，会让计算用上「别的线程的上一帧」\n"
     "		// —— 那正是观测到 clipDev=15.002136（跨组相减）的成因。\n"
     "		thread_local sl::float4x4 s_prevVP{};\n"
     "		thread_local bool s_hasPrevVP = false;"),

    # ---- Streamline.cpp : the determinant guard -------------------------
    ("sl_cpp", "clipToPrevClip determinant guard",
     "		sl::float4x4 invCurrViewProj;\n"
     "		if (curOk && havePrev) {\n"
     "			++diag.prevHistoryHits;\n"
     "			sl::matrixFullInvert(invCurrViewProj, curForReproj);\n"
     "			sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);\n"
     "		} else {\n"
     "			// 首帧 / cur 无效：单位矩阵。这是安全退化，但会被 prevHistoryMiss 计数\n"
     "			// 暴露出来 —— 若它长期增长，说明数据源还是有问题。\n"
     "			++diag.prevHistoryMiss;\n"
     "			c.clipToPrevClip[0] = { 1.f, 0.f, 0.f, 0.f };\n"
     "			c.clipToPrevClip[1] = { 0.f, 1.f, 0.f, 0.f };\n"
     "			c.clipToPrevClip[2] = { 0.f, 0.f, 1.f, 0.f };\n"
     "			c.clipToPrevClip[3] = { 0.f, 0.f, 0.f, 1.f };\n"
     "		}",
     "		sl::float4x4 invCurrViewProj;\n"
     "		if (curOk && havePrev) {\n"
     "			++diag.prevHistoryHits;\n"
     "			sl::matrixFullInvert(invCurrViewProj, curForReproj);\n"
     "			sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);\n"
     "			// v0.66 (v0.66: det guard)：行列式守卫。坏帧的矩阵在数学上不可能是\n"
     "			// 合法重投影 —— 宁可告诉 DLSS-G「相机没动」，也不给它一个错误的位移。\n"
     "			const float det = det3(c.clipToPrevClip);\n"
     "			if (det < diag.detMin) diag.detMin = det;\n"
     "			if (det > diag.detMax) diag.detMax = det;\n"
     "			if (!(det > 0.5f && det < 2.0f)) {\n"
     "				++diag.detGuard;\n"
     "				setIdentity(c.clipToPrevClip);\n"
     "			}\n"
     "		} else {\n"
     "			// 首帧 / cur 无效：单位矩阵。这是安全退化，但会被 prevHistoryMiss 计数\n"
     "			// 暴露出来 —— 若它长期增长，说明数据源还是有问题。\n"
     "			++diag.prevHistoryMiss;\n"
     "			setIdentity(c.clipToPrevClip);\n"
     "		}"),

    # ---- Streamline.cpp : menu edge state -> thread_local ---------------
    ("sl_cpp", "s_wasMenuOpen -> thread_local",
     "		static bool s_wasMenuOpen = false;",
     "		thread_local bool s_wasMenuOpen = false;   // v0.66：共享会让边沿误触发"),

    ("sl_cpp", "s_wasCamValid -> thread_local",
     "		static bool s_wasCamValid = true;",
     "		thread_local bool s_wasCamValid = true;    // v0.66：同上"),

    # ---- Streamline.cpp : heartbeat format ------------------------------
    ("sl_cpp", "heartbeat format string",
     "					\"clipDevMax={:.4f} hist(hit/miss)={}/{} tid={:#x}\",",
     "					\"clipDevMax={:.4f} hist(hit/miss)={}/{} det(min/max)={:.3f}/{:.3f} \"\n"
     "					\"detGuard={} tid(a/b/c)={:#x}/{:#x}/{:#x} calls={}/{}/{}\","),

    # ---- Streamline.cpp : heartbeat arguments ---------------------------
    ("sl_cpp", "heartbeat arguments",
     "					diag.clipDevMax,\n"
     "					diag.prevHistoryHits, diag.prevHistoryMiss,\n"
     "					diag.tidMarker);",
     "					diag.clipDevMax,\n"
     "					diag.prevHistoryHits, diag.prevHistoryMiss,\n"
     "					(diag.detMin > diag.detMax ? 0.0f : diag.detMin),\n"
     "					(diag.detMin > diag.detMax ? 0.0f : diag.detMax),\n"
     "					diag.detGuard,\n"
     "					diag.tidA, diag.tidB, diag.tidC,\n"
     "					diag.tidCallsA, diag.tidCallsB, diag.tidCallsC);"),

    # ---- Streamline.cpp : VERDICT ---------------------------------------
    ("sl_cpp", "VERDICT: det guard branch + per-tid branch",
     "				std::string vd;\n"
     "				if (diag.tidMarker == 0xFFFFFFFFu)\n"
     "					vd = \"PROBLEM two threads are calling slSetConstants -> the self-maintained \"\n"
     "					     \"viewProj history is being interleaved\";",
     "				std::string vd;\n"
     "				if (diag.detGuard > 0)\n"
     "					vd = \"PROBLEM \" + std::to_string(diag.detGuard) + \" frame(s) had a \"\n"
     "					     \"MATHEMATICALLY ILLEGAL clipToPrevClip (det outside [0.5,2.0], \"\n"
     "					     \"range seen = \" + std::to_string(diag.detMin) + \" .. \" +\n"
     "					     std::to_string(diag.detMax) + \") -> v0.66 clamped them to identity; \"\n"
     "					     \"this is the flicker source (DLSS-G was given a bogus per-frame \"\n"
     "					     \"displacement)\";\n"
     "				else if (diag.tidCallsB > 10)\n"
     "					vd = \"PROBLEM a second thread PERSISTENTLY calls slSetConstants (a=\" +\n"
     "					     std::to_string(diag.tidCallsA) + \" calls, b=\" +\n"
     "					     std::to_string(diag.tidCallsB) + \" calls) -> thread_local history is \"\n"
     "					     \"required, not shared statics\";"),

    # ---- DX12SwapChain.cpp : atomics ------------------------------------
    ("dx_cpp", "dlssgFailCount -> atomic",
     "			// 防刷屏：连续失败计数（static，Present 渲染线程单线程）\n"
     "			static int dlssgFailCount = 0;",
     "			// 防刷屏：连续失败计数。v0.66：Transfusion 侧实测两个 tid 都在调\n"
     "			// slSetConstants，「Present 渲染线程单线程」的旧假设不成立\n"
     "			// ⇒ 改原子，消除多线程 ++ 的数据竞争。\n"
     "			static std::atomic<int> dlssgFailCount{ 0 };"),

    ("dx_cpp", "dlssgDiag -> atomic",
     "				static int dlssgDiag = 0;",
     "				static std::atomic<int> dlssgDiag{ 0 };"),
]


# ---------------------------------------------------------------- helpers

def detect_eol(text):
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf >= lf else "\n"


def clean(text, eol):
    return text.replace("\r\n", "\n").replace("\n", eol)


def main():
    apply_mode = "--apply" in sys.argv
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)

    # read every file once, normalised to LF for matching
    originals = {}
    results = {}
    eols = {}
    for key, path in FILES.items():
        if not os.path.isfile(path):
            print("REFUSED: missing file %s" % path)
            return 1
        raw = io.open(path, "rb").read().decode("utf-8")
        eol = detect_eol(raw)
        eols[key] = eol
        originals[key] = raw
        results[key] = clean(raw, "\n")
        print("%-24s EOL=%s  %d bytes" % (path, repr(eol), len(raw)))

    print()

    # idempotency: refuse if the marker is already present
    for key, txt in results.items():
        if MARKER in txt:
            print("REFUSED: %s already contains marker %r - patch already applied"
                  % (FILES[key], MARKER))
            return 1

    # anchors: every old string must occur exactly once
    ok = True
    for i, (key, label, old, new) in enumerate(EDITS):
        txt = results[key]
        n = txt.count(old)
        status = "OK " if n == 1 else "BAD"
        if n != 1:
            ok = False
        print("[%2d] %s %-56s count=%d" % (i + 1, status, label, n))
        if n != 1:
            head = old.strip().split("\n")[0][:70]
            print("      anchor: %s" % head)
    if not ok:
        print("\nREFUSED: at least one anchor is not unique - nothing written")
        return 1

    # apply
    n_edits = 0
    for key, label, old, new in EDITS:
        if results[key].count(old) != 1:
            print("REFUSED (re-check): %s" % label)
            return 1
        results[key] = results[key].replace(old, new, 1)
        n_edits += 1

    # verify each edit landed by checking a distinctive fragment of new
    for key, label, old, new in EDITS:
        tail = new.strip().split("\n")[-1].strip()
        if tail and tail not in results[key]:
            print("REFUSED: post-check failed for %s" % label)
            return 1

    print("\n%d edits across %d files verified in memory." % (n_edits, len(FILES)))

    if not apply_mode:
        print("\nDRY RUN - nothing written. Re-run with --apply")
        for key, label, old, new in EDITS[:2]:
            print("\n--- sample diff (%s) ---" % label)
            for ln in new.split("\n")[:6]:
                print("+ " + ln)
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    for key, path in FILES.items():
        raw = originals[key]
        eol = eols[key]
        out = clean(results[key], eol)
        # backup
        shutil.copy2(path, path + ".bak-" + stamp)
        # write
        with io.open(path, "wb") as f:
            f.write(out.encode("utf-8"))
        # read back and compare
        back = io.open(path, "rb").read().decode("utf-8")
        same = (back == out)
        crlf = back.count("\r\n")
        lf = back.count("\n") - crlf
        stray = back.replace("\r\n", "").count("\r")
        print("%-24s written=%s  CRLF=%d LF=%d stray_CR=%d  backup=%s.bak-%s"
              % (path, "IDENTICAL" if same else "MISMATCH", crlf, lf, stray, path, stamp))
        if not same:
            print("REFUSED: read-back differs for %s" % path)
            return 1

    print("\nAPPLIED %d edits. Backups use suffix .bak-%s" % (n_edits, stamp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
