#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.64 - camera-data validity clamp (zero-matrix guard).

Evidence (2026-09-17 22:05 run, DLSSG-Transfusion.log):
    [MOTION] call=1 clipToPrev=zero cameraPos=(-243.048859,-415.314819,118.623505)
             clipToPrev rows=[0 0 0 0][0 0 0 0][-0 -0 -0 -0][0 0 0 0]

A ZERO ClipToPrevClip is not "the camera did not move" - it is an INVALID
matrix. DLSS-G reprojects every generated frame with it, so the output picture
collapses. That is the direct source of "the loading screen keeps flickering".

Cause: FrameBuffer::CameraPreviousViewProjUnjittered is not written on every
frame, while frameBufferCopy is value-initialised (all zero). So prevViewProj
reads as zero and  inv(curVP) * 0 = 0.

Fix: validate the magnitude of currViewProjSL / prevViewProjSL / clipToPrevClip;
if any of them carries no magnitude (zero / NaN / Inf), clamp clipToPrevClip to
identity - the safe degenerate case - count it, and fold the transition into the
existing reset edge.

Plus a diagnostic split (cam ok / inv) on the [XRAY] heartbeat and a matching
VERDICT branch, so one run states the answer instead of leaving it to a reader.

Assertion style: every anchor must occur EXACTLY once, otherwise REFUSED and
nothing is written. Dry run by default, --apply to write.
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAMP = "20260917-221155"

FILES = {
    "SL_H": os.path.join(ROOT, "src", "Streamline.h"),
    "SL_CPP": os.path.join(ROOT, "src", "Streamline.cpp"),
}

# marker used as an idempotency guard: if it is already present, refuse to run
MARKER = "v0.64: camera-data validity"

E1_OLD = """			std::uint32_t longFrames = 0;
		};"""

E1_NEW = """			std::uint32_t longFrames = 0;
			// v0.64: camera-data validity accounting. A zero ClipToPrevClip is an
			// INVALID matrix, not "camera did not move", and it collapses DLSS-G's
			// per-generated-frame reprojection. See the clamp in CheckFrameConstants.
			std::uint64_t camValid = 0;
			std::uint64_t camInvalid = 0;
		};"""

E2_OLD = """		sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevViewProjSL);
		sl::matrixFullInvert(c.prevClipToClip, c.clipToPrevClip);"""

E2_NEW = """		sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevViewProjSL);
		sl::matrixFullInvert(c.prevClipToClip, c.clipToPrevClip);

		// ===== v0.64: camera-data validity clamp =============================
		// 2026-09-17 22:05 运行，Transfusion 记录到的真值：
		//   [MOTION] call=1 clipToPrev=zero cameraPos=(-243.048859,-415.314819,118.623505)
		//            clipToPrev rows=[0 0 0 0][0 0 0 0][-0 -0 -0 -0][0 0 0 0]
		// 零矩阵**不是**"相机没动"，是"矩阵无效"。DLSS-G 用 clipToPrevClip 重投影
		// 每一个生成帧，拿到零矩阵 → 输出画面整体崩坏。这就是"加载界面/世界里持续闪"
		// 的直接来源（主菜单不闪只是因为那时 DLSS-G 还没被接受，accepted=0）。
		// 成因：FrameBuffer::CameraPreviousViewProjUnjittered 并非每帧都被写入，
		// 而 frameBufferCopy 是值初始化（全零），于是 prevViewProj 读成零矩阵，
		// inv(curVP) * 0 = 0。
		// 处理：校验幅度，任一无量级（零/NaN/Inf）即钳成单位矩阵 —— "相机没动"是
		// 安全的退化情形（加载界面/菜单本来也没动）；世界帧偶发无效只会丢一帧的
		// 相机运动，远好于画面崩坏。
		auto finiteMag = [](const sl::float4x4& m) -> float {
			float mx = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float v[4] = { m[r].x, m[r].y, m[r].z, m[r].w };
				for (int k = 0; k < 4; ++k) {
					const float a = v[k] < 0.0f ? -v[k] : v[k];
					// NaN/Inf 都会走到这里（!(NaN <= x) 为真）
					if (!(a <= 1.0e6f))
						return 1.0e30f;
					if (a > mx)
						mx = a;
				}
			}
			return mx;
		};
		const bool camValid = finiteMag(currViewProjSL) > 1.0e-6f &&
		                      finiteMag(prevViewProjSL) > 1.0e-6f &&
		                      finiteMag(c.clipToPrevClip) > 1.0e-6f;
		if (camValid) {
			++diag.camValid;
		} else {
			++diag.camInvalid;
			c.clipToPrevClip[0] = { 1.f, 0.f, 0.f, 0.f };
			c.clipToPrevClip[1] = { 0.f, 1.f, 0.f, 0.f };
			c.clipToPrevClip[2] = { 0.f, 0.f, 1.f, 0.f };
			c.clipToPrevClip[3] = { 0.f, 0.f, 0.f, 1.f };
			c.prevClipToClip = c.clipToPrevClip;
		}
		// ====================================================================="""

E3_OLD = """		c.reset = menuEdgeUp ? sl::Boolean::eTrue : sl::Boolean::eFalse;"""

E3_NEW = """		// v0.64：相机数据断裂与菜单边沿同类 —— 基于旧矩阵建立的重投影历史已经无效，
		// 丢一次即可（边沿，不是每帧，v0.59 的教训）。
		static bool s_wasCamValid = true;
		const bool camEdgeDown = !camValid && s_wasCamValid;
		s_wasCamValid = camValid;
		c.reset = (menuEdgeUp || camEdgeDown) ? sl::Boolean::eTrue : sl::Boolean::eFalse;"""

E4_OLD = """					"capUs={} mult(acc/pres)={}/{} longFrames={}","""

E4_NEW = """					"capUs={} mult(acc/pres)={}/{} longFrames={} cam(ok/inv)={}/{}","""

E5_OLD = """					dlssgAcceptedFrames + 1, diag.presentedPrev, diag.longFrames);"""

E5_NEW = """					dlssgAcceptedFrames + 1, diag.presentedPrev, diag.longFrames,
					diag.camValid, diag.camInvalid);"""

E6_OLD = """				if (diag.constsFail != 0)"""

E6_NEW = """				if (diag.camInvalid > 0 &&
					diag.camInvalid * 4 > (diag.camValid + diag.camInvalid))
					vd = "camera data INVALID on " + std::to_string(diag.camInvalid) + " of " +
					     std::to_string(diag.camValid + diag.camInvalid) +
					     " frames -> ClipToPrevClip was zero and got clamped to identity "
					     "(that IS the flicker source: DLSS-G reprojects with it)";
				else if (diag.constsFail != 0)"""

EDITS = [
    ("SL_H", "cam counters in Diag", E1_OLD, E1_NEW),
    ("SL_CPP", "clipToPrevClip validity clamp", E2_OLD, E2_NEW),
    ("SL_CPP", "reset edge on camera break", E3_OLD, E3_NEW),
    ("SL_CPP", "heartbeat format gains cam(ok/inv)", E4_OLD, E4_NEW),
    ("SL_CPP", "heartbeat args gain cam counters", E5_OLD, E5_NEW),
    ("SL_CPP", "VERDICT gains camera-invalid branch", E6_OLD, E6_NEW),
]


def detect_eol(text):
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def read_norm(path):
    """Read and normalise to LF so anchors can be written with plain \\n."""
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", errors="surrogateescape")
    eol = detect_eol(text)
    return text.replace("\r\n", "\n"), eol


def main():
    apply = "--apply" in sys.argv
    originals = {}
    eols = {}

    for key, path in FILES.items():
        if not os.path.isfile(path):
            print("REFUSED: missing file %s" % path)
            return 2
        text, eol = read_norm(path)
        originals[key] = text
        eols[key] = eol

    # ---- idempotency guard FIRST (anchor uniqueness does not prove it) ----
    for key in FILES:
        if MARKER in originals[key]:
            print("REFUSED: '%s' already present in %s - patch already applied"
                  % (MARKER, FILES[key]))
            return 2

    # ---- anchor check: every anchor exactly once ----
    ok = True
    for key, label, old, _new in EDITS:
        n = originals[key].count(old)
        flag = "OK " if n == 1 else "BAD"
        print("  [%s] %-42s %-42s occurrences=%d" % (flag, os.path.basename(FILES[key]), label, n))
        if n != 1:
            ok = False

    if not ok:
        print("\nREFUSED, nothing written.")
        return 1

    results = dict(originals)
    for key, label, old, new in EDITS:
        results[key] = results[key].replace(old, new, 1)

    print("\nAll anchors unique.")
    for key, label, old, new in EDITS:
        after = originals[key].count(old)
        if after != 1:
            print("ABORT: anchor disappeared for %s" % label)
            return 1

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply to write.")
        for key in FILES:
            print("  %s: %d -> %d bytes" % (os.path.basename(FILES[key]),
                                            len(originals[key]), len(results[key])))
        return 0

    for key, path in FILES.items():
        new = results[key]
        eol = eols[key]
        if eol != "\n":
            new = new.replace("\r\n", "\n").replace("\n", eol)
        out = new.encode("utf-8", errors="surrogateescape")
        bak = "%s.bak-%s" % (path, STAMP)
        shutil.copy2(path, bak)
        with open(path, "wb") as f:
            f.write(out)
        # read back and verify byte-for-byte
        with open(path, "rb") as f:
            back = f.read()
        same = back == out
        print("  wrote %-20s %7d -> %7d bytes  backup=%s  verify=%s"
              % (os.path.basename(path), os.path.getsize(bak), len(out),
                 os.path.basename(bak), "IDENTICAL" if same else "MISMATCH"))
        if not same:
            print("ABORT: read-back mismatch for %s" % path)
            return 1

    print("\nAPPLIED OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
