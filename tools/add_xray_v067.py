#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.67: camera snapshot continuity gate + raw matrix dump + det-hold.

ROOT CAUSE (2026-09-17 22:42 run, v0.66):

    det( inv(cur) x prev )  ==  1   <==>   cur and prev are the SAME camera's data
    (two frames with the same projection cancel their projection terms exactly)

    The heartbeat only ever reports det in {-0.025248, 1.000000}:
        detGuard=77 / world=91  ->  77 frames computed an ILLEGAL determinant,
        and the observed value is a CONSTANT -0.025248 (not a random spread).

    A constant non-1 determinant can only come from mixing two DIFFERENT
    sources: the perFrame constant buffer is written with two camera sets per
    frame (menu 3D background camera vs world camera -- heartbeat pos alternates
    between (-50.0, 618.2, 105.5) and (-243.0, -415.3, 118.6), 1300+ units
    apart, which no real camera can cover in one frame). frameBufferCopy is
    overwritten by whichever was written last, so cur/prev always span sources
    -> det illegal -> clamped to identity -> DLSS-G is told "the camera did not
    move" on EVERY frame (Transfusion independently logs clipToPrev=identity 4/4).

    => DLSS-G has been generating every interpolated frame with zero camera
       motion. That is the flicker.

PATCH:
  1. FrameGen::AcceptCameraSnapshot -- temporal continuity gate on
     CameraPosAdjust. One frame cannot teleport > 400 units; a real teleport or
     scene change re-locks after 12 consecutive rejects. Rejected snapshots do
     not touch frameBufferCopy, so cur/prev stay on ONE source.
  2. Forensic dump: full raw matrices every 300 arrivals (offline ground truth)
     plus one log line per accept/reject.
  3. Streamline: when the det guard trips, HOLD the last legal clipToPrevClip
     instead of writing identity -- "identity" means "camera did not move",
     which is a lie that corrupts DLSS-G's occlusion reasoning.
  4. heartbeat + VERDICT report the new counters.

Dry run by default. --apply writes. Idempotency markers checked FIRST.
"""

import io
import os
import sys
import shutil
import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")

FILES = {
    "fgh": os.path.join(SRC, "FrameGen.h"),
    "fgc": os.path.join(SRC, "FrameGen.cpp"),
    "slh": os.path.join(SRC, "Streamline.h"),
    "slc": os.path.join(SRC, "Streamline.cpp"),
}

MARKERS = [
    "v0.67: camera snapshot continuity gate",
    "AcceptCameraSnapshot",
    "detHold",
    "snap(acc/jmp/re/zero/arr)",
    "[CAM] raw",
]

# ---------------------------------------------------------------- helpers ---
FG_HELPERS = '''		thread_local FrameBuffer* tlsMappedFB = nullptr;

		// v0.67: camera snapshot continuity gate
		// 取证用的小工具。矩阵是引擎的行主序 float[4][4]（FrameGen.h:73）。
		inline float camDev(const Matrix& m)
		{
			float mx = 0.0f;
			for (int r = 0; r < 4; ++r)
				for (int c = 0; c < 4; ++c) {
					float d = m.data[r][c] - (r == c ? 1.0f : 0.0f);
					if (!(d == d)) return 1.0e30f;   // NaN
					if (d < 0.0f) d = -d;
					if (d > mx) mx = d;
				}
			return mx;
		}
		inline float camMag(const Matrix& m)
		{
			float mx = 0.0f;
			for (int r = 0; r < 4; ++r)
				for (int c = 0; c < 4; ++c) {
					float v = m.data[r][c];
					if (!(v == v)) return 1.0e30f;
					if (v < 0.0f) v = -v;
					if (v > mx) mx = v;
				}
			return mx;
		}
		inline float camDet3(const Matrix& m)
		{
			const float a = m.data[0][0], b = m.data[0][1], c = m.data[0][2];
			const float d = m.data[1][0], e = m.data[1][1], f = m.data[1][2];
			const float g = m.data[2][0], h = m.data[2][1], i = m.data[2][2];
			return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
		}
		// 每 300 个到达快照打一组**原始矩阵**（约 10s 一次）。这是离线核对量级、
		// 行列式、以及"两组数据差在哪"的唯一地面真值 —— 不要只靠推导。
		inline void DumpCameraSnapshot(const FrameBuffer& b, std::uint64_t a_n)
		{
			if ((a_n % 300u) != 1u)
				return;
			const Matrix* ms[3] = { &b.CameraViewProjUnjittered, &b.CameraProjUnjittered, &b.CameraViewInverse };
			const char* nm[3] = { "ViewProjUnj", "ProjUnj", "ViewInv" };
			for (int k = 0; k < 3; ++k) {
				const auto& d = ms[k]->data;
				SKSE::log::info("[CAM] raw #{} {} | {:.6g} {:.6g} {:.6g} {:.6g} | {:.6g} {:.6g} {:.6g} {:.6g} "
					"| {:.6g} {:.6g} {:.6g} {:.6g} | {:.6g} {:.6g} {:.6g} {:.6g}",
					a_n, nm[k],
					d[0][0], d[0][1], d[0][2], d[0][3],
					d[1][0], d[1][1], d[1][2], d[1][3],
					d[2][0], d[2][1], d[2][2], d[2][3],
					d[3][0], d[3][1], d[3][2], d[3][3]);
			}
			SKSE::log::info("[CAM] raw #{} pos=({:.4f},{:.4f},{:.4f},{:.4f}) prevPos=({:.4f},{:.4f},{:.4f},{:.4f}) "
				"devVP={:.6g} detVP={:.6g} detProj={:.6g} magVP={:.6g}",
				a_n, b.CameraPosAdjust[0], b.CameraPosAdjust[1], b.CameraPosAdjust[2], b.CameraPosAdjust[3],
				b.CameraPreviousPosAdjust[0], b.CameraPreviousPosAdjust[1], b.CameraPreviousPosAdjust[2],
				b.CameraPreviousPosAdjust[3],
				camDev(b.CameraViewProjUnjittered), camDet3(b.CameraViewProjUnjittered),
				camDet3(b.CameraProjUnjittered), camMag(b.CameraViewProjUnjittered));
		}

		struct ID3D11DeviceContext_Map'''

FG_VALIDATOR = '''	// v0.67: camera snapshot continuity gate
	// 判定量 = CameraPosAdjust（相机世界位置，心跳 pos= 与 Transfusion
	// [MOTION] cameraPos= 打的是同一个值）。Skyrim 人物高约 100 单位，真实相机
	// 一帧移动顶多几十单位；实测两组数据相差 1300+ 单位 —— 那不可能是同一个相机。
	// 被拒绝的快照**不写入** frameBufferCopy，于是 cur/prev 恒定来自同一来源，
	// det(inv(cur) x prev) 才会是 1。
	namespace
	{
		constexpr float kCamJumpTol = 400.0f;
		constexpr float kCamJumpTol2 = kCamJumpTol * kCamJumpTol;
		constexpr std::uint32_t kCamRelockAfter = 12;
	}

	bool FrameGen::AcceptCameraSnapshot(const FrameBuffer& a_src)
	{
		++snapArrivals;
		DumpCameraSnapshot(a_src, snapArrivals);

		const float px = a_src.CameraPosAdjust[0];
		const float py = a_src.CameraPosAdjust[1];
		const float pz = a_src.CameraPosAdjust[2];
		const bool usable = (px == px) && (py == py) && (pz == pz) &&
		                    camMag(a_src.CameraViewProjUnjittered) > 1.0e-6f &&
		                    camMag(a_src.CameraView) > 1.0e-6f;
		if (!usable) {
			++snapRejectZero;
			SKSE::log::warn("[CAM] #{} rejected: empty/garbage snapshot (magVP={:.6g} devVP={:.6g})",
				snapArrivals, camMag(a_src.CameraViewProjUnjittered), camDev(a_src.CameraViewProjUnjittered));
			return false;
		}

		float d2 = 0.0f;
		if (snapHaveLast) {
			const float dx = px - snapLastPos[0];
			const float dy = py - snapLastPos[1];
			const float dz = pz - snapLastPos[2];
			d2 = dx * dx + dy * dy + dz * dz;
		}
		snapLastDist = snapHaveLast ? std::sqrt(d2) : 0.0f;

		if (snapHaveLast && d2 > kCamJumpTol2) {
			if (snapConsecReject < kCamRelockAfter) {
				++snapConsecReject;
				++snapRejectJump;
				SKSE::log::info("[CAM] #{} JUMP rejected: pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} "
					"last=({:.1f},{:.1f},{:.1f}) consec={}",
					snapArrivals, px, py, pz, std::sqrt(d2),
					snapLastPos[0], snapLastPos[1], snapLastPos[2], snapConsecReject);
				return false;
			}
			++snapRelock;
			SKSE::log::warn("[CAM] #{} RELOCK after {} consecutive jumps (teleport / scene change) "
				"-> accepting pos=({:.1f},{:.1f},{:.1f})",
				snapArrivals, snapConsecReject, px, py, pz);
			snapConsecReject = 0;
		} else {
			snapConsecReject = 0;
		}

		frameBufferCopy = a_src;
		++snapAccept;
		snapAcceptDist = snapHaveLast ? std::sqrt(d2) : 0.0f;
		snapLastPos[0] = px;
		snapLastPos[1] = py;
		snapLastPos[2] = pz;
		snapHaveLast = true;
		return true;
	}

	void FrameGen::InstallContextHooks(ID3D11DeviceContext* a_context)'''

EDITS = []

# ------------------------------------------------------------ FrameGen.h ---
EDITS.append(("FrameGen.h: gate API + counters",
              '''		// Map hook 写入缓存（ID3D11DeviceContext_Map::thunk 调用）
		void SetMappedFrameBuffer(FrameBuffer* a_fb) { mappedFrameBuffer = a_fb; }
''',
              '''		// Map hook 写入缓存（ID3D11DeviceContext_Map::thunk 调用）
		void SetMappedFrameBuffer(FrameBuffer* a_fb) { mappedFrameBuffer = a_fb; }

		// v0.67: camera snapshot continuity gate
		// 实测 22:42 运行：det(inv(cur) x prev) 只取 -0.025248（77 帧）与 1.000000
		// 两个值。行列式恒等式要求「同一套相机数据」时恰好为 1，出现**固定**的非 1
		// 值只有一个解释：同一个 perFrame 缓冲每帧被写入**两组不同的相机数据**
		// （菜单 3D 背景相机 vs 世界相机），frameBufferCopy 每帧被后写的那组覆盖。
		// 于是 cur/prev 永远跨来源 -> det 非法 -> 钳成单位矩阵 -> DLSS-G 收到的
		// 相机运动**恒为 0**（Transfusion 侧 4/4 次 clipToPrev=identity 佐证）。
		// 闸门：相机世界位置必须与上一次接受的快照连续（一帧内跳跃 > 400 单位
		// 不可能是真实运动）。连续拒绝 12 次判定为真实传送/场景切换，重新锁定。
		bool AcceptCameraSnapshot(const FrameBuffer& a_src);
		std::uint64_t snapAccept = 0;
		std::uint64_t snapRejectJump = 0;
		std::uint64_t snapRejectZero = 0;
		std::uint64_t snapRelock = 0;
		std::uint64_t snapArrivals = 0;   // 到达的快照总数（含被丢弃的）
		float snapLastDist = 0.0f;        // 本次到达与上次接受的距离（sqrt 后）
		float snapAcceptDist = 0.0f;      // 上一次被接受的到达距离
		bool  snapHaveLast = false;
		float snapLastPos[3] = { 0.0f, 0.0f, 0.0f };
		std::uint32_t snapConsecReject = 0;
'''))

# ---------------------------------------------------------- FrameGen.cpp ---
EDITS.append(("FrameGen.cpp: helpers + raw dump",
              '''		thread_local FrameBuffer* tlsMappedFB = nullptr;

		struct ID3D11DeviceContext_Map''',
              FG_HELPERS))

EDITS.append(("FrameGen.cpp: Unmap hook uses the gate",
              '''				if (tlsMappedFB) {
					auto& fg = Get();
					fg.frameBufferCopy = *tlsMappedFB;
					fg.SetMappedFrameBuffer(&fg.frameBufferCopy);
					tlsMappedFB = nullptr;
				}''',
              '''				if (tlsMappedFB) {
					auto& fg = Get();
					// v0.67：只接受「与上一次接受的快照时间连续」的相机数据。
					// 同一个 perFrame 缓冲每帧写入两组不同相机（菜单 3D 背景 + 世界）
					// 时，后写的那组会把先写的冲掉 —— 闸门挡住它，frameBufferCopy 与
					// 自维护 prev 历史才可能是同一来源（det(inv(cur) x prev)=1）。
					if (fg.AcceptCameraSnapshot(*tlsMappedFB))
						fg.SetMappedFrameBuffer(&fg.frameBufferCopy);
					tlsMappedFB = nullptr;
				}'''))

EDITS.append(("FrameGen.cpp: AcceptCameraSnapshot definition",
              '''	void FrameGen::InstallContextHooks(ID3D11DeviceContext* a_context)''',
              FG_VALIDATOR))

# --------------------------------------------------------- Streamline.h ---
EDITS.append(("Streamline.h: detHold counter",
              '''			std::uint64_t detGuard = 0;''',
              '''			std::uint64_t detGuard = 0;
			// v0.67：守卫触发时改用「保留上一帧合法矩阵」而不是单位矩阵的次数。
			// detHold == detGuard 说明一直在吃上一帧的值（数据源仍未修好）。
			std::uint64_t detHold = 0;'''))

# ------------------------------------------------------- Streamline.cpp ---
EDITS.append(("Streamline.cpp: hold last legal clipToPrevClip",
              '''		sl::float4x4 invCurrViewProj;
		if (curOk && havePrev) {
			++diag.prevHistoryHits;
			sl::matrixFullInvert(invCurrViewProj, curForReproj);
			sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);
			// v0.66 (v0.66: det guard)：行列式守卫。坏帧的矩阵在数学上不可能是
			// 合法重投影 —— 宁可告诉 DLSS-G「相机没动」，也不给它一个错误的位移。
			const float det = det3(c.clipToPrevClip);
			if (det < diag.detMin) diag.detMin = det;
			if (det > diag.detMax) diag.detMax = det;
			if (!(det > 0.5f && det < 2.0f)) {
				++diag.detGuard;
				setIdentity(c.clipToPrevClip);
			}
		} else {''',
              '''		sl::float4x4 invCurrViewProj;
		// v0.67：守卫触发时保留上一帧**合法**的 clipToPrevClip，不再写单位矩阵。
		// 「单位矩阵」在 DLSS-G 眼里是「相机没动」—— 那是一句谎话，会让它的遮挡/
		// 去遮挡判断整体错位；上一帧的真实位移是远好得多的估计。detHold 把它暴露出来。
		thread_local sl::float4x4 s_lastGoodClip{};
		thread_local bool s_hasLastGoodClip = false;
		if (curOk && havePrev) {
			++diag.prevHistoryHits;
			sl::matrixFullInvert(invCurrViewProj, curForReproj);
			sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);
			// v0.66 (det guard)：det(inv(cur) x prev) **恒等于 1 当且仅当** cur/prev
			// 是同一套相机数据（两帧投影相同则投影项互相抵消）。实测只出现
			// -0.025248 与 1.000000 两个取值 —— 前者是同一缓冲每帧被写入两组不同
			// 相机（菜单 3D 背景 <-> 世界）时跨来源相减的指纹。
			const float det = det3(c.clipToPrevClip);
			if (det < diag.detMin) diag.detMin = det;
			if (det > diag.detMax) diag.detMax = det;
			if (det > 0.5f && det < 2.0f) {
				s_lastGoodClip = c.clipToPrevClip;
				s_hasLastGoodClip = true;
			} else {
				++diag.detGuard;
				if (s_hasLastGoodClip) {
					c.clipToPrevClip = s_lastGoodClip;
					++diag.detHold;
				} else {
					setIdentity(c.clipToPrevClip);
				}
			}
		} else {'''))

EDITS.append(("Streamline.cpp: heartbeat format string",
              '''					"detGuard={} tid(a/b/c)={:#x}/{:#x}/{:#x} calls={}/{}/{}",''',
              '''					"detGuard={} detHold={} tid(a/b/c)={:#x}/{:#x}/{:#x} calls={}/{}/{} | "
					"snap(acc/jmp/re/zero/arr)={}/{}/{}/{}/{} dist(last/acc)={:.1f}/{:.1f}",'''))

EDITS.append(("Streamline.cpp: heartbeat args",
              '''					diag.detGuard,
					diag.tidA, diag.tidB, diag.tidC,
					diag.tidCallsA, diag.tidCallsB, diag.tidCallsC);''',
              '''					diag.detGuard, diag.detHold,
					diag.tidA, diag.tidB, diag.tidC,
					diag.tidCallsA, diag.tidCallsB, diag.tidCallsC,
					Get().snapAccept, Get().snapRejectJump, Get().snapRelock,
					Get().snapRejectZero, Get().snapArrivals,
					Get().snapLastDist, Get().snapAcceptDist);'''))

EDITS.append(("Streamline.cpp: VERDICT reports the gate",
              '''				if (diag.detGuard > 0)
					vd = "PROBLEM " + std::to_string(diag.detGuard) + " frame(s) had a "
					     "MATHEMATICALLY ILLEGAL clipToPrevClip (det outside [0.5,2.0], "
					     "range seen = " + std::to_string(diag.detMin) + " .. " +
					     std::to_string(diag.detMax) + ") -> v0.66 clamped them to identity; "
					     "this is the flicker source (DLSS-G was given a bogus per-frame "
					     "displacement)";''',
              '''				if (Get().snapRejectJump > 0 && Get().snapRejectJump >= Get().snapAccept)
					vd = "PROBLEM the perFrame buffer carries TWO cameras: accepted " +
					     std::to_string(Get().snapAccept) + " / jump-rejected " +
					     std::to_string(Get().snapRejectJump) + " (relock " +
					     std::to_string(Get().snapRelock) + ") -> cur/prev keep spanning two "
					     "sources, so det(inv(cur) x prev) is never 1 and DLSS-G is told the "
					     "camera did not move";
				else if (diag.detGuard > 0)
					vd = "PROBLEM " + std::to_string(diag.detGuard) + " frame(s) had a "
					     "MATHEMATICALLY ILLEGAL clipToPrevClip (det outside [0.5,2.0], "
					     "range seen = " + std::to_string(diag.detMin) + " .. " +
					     std::to_string(diag.detMax) + ") -> " + std::to_string(diag.detHold) +
					     " of them held the last legal matrix (identity would tell DLSS-G the "
					     "camera never moved, which is a lie)";'''))


# ------------------------------------------------------------------ main ---
def detect_eol(text):
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def norm(text):
    return text.replace("\r\n", "\n")


def denorm(text, eol):
    return text.replace("\n", eol) if eol != "\n" else text


def main():
    apply = "--apply" in sys.argv
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    # ---- idempotency guard FIRST (insertions do not consume their anchor) ----
    for key, path in FILES.items():
        raw = io.open(path, "rb").read().decode("utf-8", "replace")
        for mk in MARKERS:
            if mk in raw:
                print("REFUSED, nothing written: marker %r already present in %s" % (mk, path))
                return 2

    originals = {}
    results = {}
    for key, path in FILES.items():
        raw = io.open(path, "rb").read().decode("utf-8", "replace")
        eol = detect_eol(raw)
        originals[key] = (norm(raw), eol)
        results[key] = norm(raw)

    where = {
        "fgh": "fgh",
        "fgc": "fgc",
        "slh": "slh",
        "slc": "slc",
    }
    # map each edit label -> file key
    labels = [
        ("fgh", 0), ("fgc", 1), ("fgc", 2), ("fgc", 3),
        ("slh", 4), ("slc", 5), ("slc", 6), ("slc", 7), ("slc", 8),
    ]

    failed = 0
    for idx, (label, old, new) in enumerate(EDITS):
        fkey = labels[idx][0]
        text = results[fkey]
        n = text.count(old)
        status = "OK " if n == 1 else "FAIL"
        if n != 1:
            failed += 1
            print("%s %-46s anchor occurs %d times" % (status, label, n))
            head = old.strip().splitlines()[0][:60] if old.strip() else ""
            print("      anchor head: %r" % head)
            for ln in originals[fkey][0].split("\n"):
                if head and head[:25] in ln:
                    print("      candidate  : %r" % ln)
        else:
            print("%s %-46s anchor occurs 1 time" % (status, label))
            results[fkey] = text.replace(old, new)

    if failed:
        print("\nREFUSED, nothing written: %d anchor(s) not unique" % failed)
        return 2

    # ---- write + readback ----
    for key, path in FILES.items():
        txt, eol = originals[key]
        new = results[key]
        if apply:
            shutil.copy2(path, path + ".bak-" + stamp)
            io.open(path, "wb").write(denorm(new, eol).encode("utf-8"))
            back = io.open(path, "rb").read().decode("utf-8", "replace")
            same = norm(back) == new
            print("write %-46s %s  bytes %d -> %d (%+d)"
                  % (os.path.basename(path),
                     "IDENTICAL" if same else "*** MISMATCH ***",
                     len(txt), len(norm(back)), len(norm(back)) - len(txt)))
            if not same:
                print("REFUSED: readback mismatch on %s" % path)
                return 3
        else:
            print("dry-run %-44s would gain %+d bytes" % (os.path.basename(path), len(new) - len(txt)))

    print()
    print("DRY RUN - nothing written (pass --apply to write)" if not apply else "APPLIED (backup suffix .bak-%s)" % stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
