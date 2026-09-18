#!/usr/bin/env python3
"""
v0.65 patch - the reprojection SOURCE was the bug.

Evidence (22:18 run, 2026-09-17):
  * XRAY heartbeat: prevVP == curVP on EVERY sample (15.0110/15.0110,
    15.0006/15.0006). Transfusion [MOTION] 4/4 calls logged clipToPrev=identity.
    => clipToPrevClip = inv(cur) * prev = I, i.e. DLSS-G is told "the camera
       never moved" on every single frame. Loading menu (camera static) looks
       fine; the moment you enter the world (camera moves) everything smears.
  * v0.64 clamped the ZERO matrix to IDENTITY - both mean "no motion", so it
    could not have fixed the flicker. The clamp was treating a symptom.
  * 45% of frames read a zero prev: that is the Unmap hook reading pData AFTER
    the original Unmap already ran (driver is free to recycle that memory).

Fix:
  1. Stop trusting FrameBuffer::CameraPreviousViewProjUnjittered. Maintain our
     own "viewProj we handed to DLSS-G last frame" history.
  2. Copy the perFrame buffer BEFORE the original Unmap, in a thread_local slot.
  3. Fallback source: viewProj = inv(CameraViewInverse) * CameraProjUnjittered,
     enabled only when the engine's own viewProj is frozen for >=30 frames AND
     a first-frame cross-check proves our construction matches the engine's to
     within 1%. If the construction were wrong the check fails and the fallback
     is simply never used - it cannot introduce a new failure mode.

Dry-run by default. Pass --apply to write.
"""

import re
import sys
import shutil
import datetime

ROOT = "D:/Modding/DynamicShaderFrameGen/src"
STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def detect_eol(b: bytes) -> str:
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    return "\r\n" if crlf > lf else "\n"


class File:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as f:
            raw = f.read()
        self.eol = detect_eol(raw)
        self.text = raw.decode("utf-8").replace("\r\n", "\n")
        self.orig = self.text

    def render(self):
        return self.text.replace("\n", self.eol).encode("utf-8")


# ---------------------------------------------------------------------------
# 1. Streamline.h : new diag fields
# ---------------------------------------------------------------------------
H_ANCHOR = "\t\t\tstd::uint64_t camInvalid = 0;\n"

H_NEW = """\t\t\t// ---- v0.65: reprojection source accounting ----
\t\t\t// engPrevEqCur is the direct evidence for "the engine's previous viewProj
\t\t\t// is useless": when it equals cur, clipToPrevClip degenerates to identity
\t\t\t// and DLSS-G is told the camera never moved. engCurFrozenRun / derived*
\t\t\t// cover the case where the engine's CUR matrix is itself frozen.
\t\t\tstd::uint64_t engPrevEqCur = 0;
\t\t\tstd::uint64_t engPrevDiffers = 0;
\t\t\tstd::uint64_t engPrevZero = 0;
\t\t\tstd::uint64_t engCurFrozenRun = 0;
\t\t\tstd::uint64_t derivedChecked = 0;
\t\t\tstd::uint64_t derivedMatch = 0;
\t\t\tstd::uint64_t derivedUsed = 0;
\t\t\tstd::uint64_t prevHistoryHits = 0;
\t\t\tstd::uint64_t prevHistoryMiss = 0;
\t\t\tstd::uint64_t reprojSource = 0;
\t\t\tstd::uint32_t tidMarker = 0;
\t\t\tfloat curMagLast = 0.0f;
\t\t\tfloat engPrevMagLast = 0.0f;
\t\t\tfloat derivedMatchErr = 0.0f;
\t\t\tfloat clipDevMax = 0.0f;
"""

# ---------------------------------------------------------------------------
# 2. Streamline.cpp : replace the whole reprojection block (lines 382-441)
# ---------------------------------------------------------------------------
CPP_OLD_BLOCK = "\t\t// prev 帧矩阵（引擎提供的 prev viewproj）——值拷贝避免引用推导歧义\n"

CPP_NEW_BLOCK = r"""		// ===== v0.65: reprojection source ====================================
		// 2026-09-17 22:18 运行实测：引擎的 CameraPreviousViewProjUnjittered 与
		// CameraViewProjUnjittered **逐元素恒等**（心跳里每一条 prevVP 都等于同一行的
		// curVP），Transfusion 侧 4/4 次 slSetConstants 也全部记录 clipToPrev=identity。
		// 于是 clipToPrevClip = inv(cur) x prev = I —— DLSS-G 收到的相机运动量**恒为 0**：
		//   加载菜单（相机本来静止）看着正常；一进世界（相机开始动）就成片闪。
		// v0.64 的钳制只是把"零矩阵"换成"单位矩阵"，两者都等价于"没动"，所以治不了闪。
		// 要修的是**数据源**：
		//   1. 不再采信引擎的 prev 字段，自己维护"上一帧交给 DLSS-G 的 viewProj"
		//   2. 自带派生源（view x proj），在引擎 cur 冻结时接管（附首帧交叉校验）
		const Matrix curVP = a_fb.CameraViewProjUnjittered;
		sl::float4x4 currViewProjSL;
		currViewProjSL[0] = sl::float4(curVP.data[0][0], curVP.data[1][0], curVP.data[2][0], curVP.data[3][0]);
		currViewProjSL[1] = sl::float4(curVP.data[0][1], curVP.data[1][1], curVP.data[2][1], curVP.data[3][1]);
		currViewProjSL[2] = sl::float4(curVP.data[0][2], curVP.data[1][2], curVP.data[2][2], curVP.data[3][2]);
		currViewProjSL[3] = sl::float4(curVP.data[0][3], curVP.data[1][3], curVP.data[2][3], curVP.data[3][3]);

		// 引擎的 prev 只保留做对照（engPrev*），不再参与重投影。
		const Matrix prevVP = a_fb.CameraPreviousViewProjUnjittered;
		sl::float4x4 engPrevViewProjSL;
		engPrevViewProjSL[0] = sl::float4(prevVP.data[0][0], prevVP.data[1][0], prevVP.data[2][0], prevVP.data[3][0]);
		engPrevViewProjSL[1] = sl::float4(prevVP.data[0][1], prevVP.data[1][1], prevVP.data[2][1], prevVP.data[3][1]);
		engPrevViewProjSL[2] = sl::float4(prevVP.data[0][2], prevVP.data[1][2], prevVP.data[2][2], prevVP.data[3][2]);
		engPrevViewProjSL[3] = sl::float4(prevVP.data[0][3], prevVP.data[1][3], prevVP.data[2][3], prevVP.data[3][3]);

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
		// 逐元素相同判定。引擎把 prev 写成 cur 时是**位级相同**（日志里两个 devOf
		// 精确一致到 4 位小数），1e-9 绝对容差足够。
		auto sameMat = [](const sl::float4x4& a, const sl::float4x4& b) -> bool {
			for (int r = 0; r < 4; ++r) {
				const float d[4] = { a[r].x - b[r].x, a[r].y - b[r].y,
				                     a[r].z - b[r].z, a[r].w - b[r].w };
				for (int k = 0; k < 4; ++k) {
					if (!(d[k] == d[k]))
						return false;                              // NaN
					const float a2 = d[k] < 0.0f ? -d[k] : d[k];
					if (a2 > 1.0e-9f)
						return false;
				}
			}
			return true;
		};

		// 谁在调本函数？钩子/调用点若被两个线程命中，自维护历史会被交错污染 ——
		// 让日志回答，不要假设。0xFFFFFFFF = 观察到多个线程。
		{
			const std::uint32_t tid = static_cast<std::uint32_t>(::GetCurrentThreadId());
			if (diag.tidMarker == 0)
				diag.tidMarker = tid;
			else if (diag.tidMarker != tid)
				diag.tidMarker = 0xFFFFFFFFu;
		}

		// ---- 派生源：viewProj = inv(CameraViewInverse) x CameraProjUnjittered ----
		// 两个**独立字段**。CameraViewInverse 同时是 DLSS-G 相机朝向
		// （cameraRight/Up/Fwd）的来源，所以它与那份数据天然一致。
		sl::float4x4 derivedViewProj;
		{
			sl::float4x4 viewInvSL, projUnjSL;
			const auto& vi = a_fb.CameraViewInverse.data;
			viewInvSL[0] = sl::float4(vi[0][0], vi[1][0], vi[2][0], vi[3][0]);
			viewInvSL[1] = sl::float4(vi[0][1], vi[1][1], vi[2][1], vi[3][1]);
			viewInvSL[2] = sl::float4(vi[0][2], vi[1][2], vi[2][2], vi[3][2]);
			viewInvSL[3] = sl::float4(vi[0][3], vi[1][3], vi[2][3], vi[3][3]);
			const auto& pu = a_fb.CameraProjUnjittered.data;
			projUnjSL[0] = sl::float4(pu[0][0], pu[1][0], pu[2][0], pu[3][0]);
			projUnjSL[1] = sl::float4(pu[0][1], pu[1][1], pu[2][1], pu[3][1]);
			projUnjSL[2] = sl::float4(pu[0][2], pu[1][2], pu[2][2], pu[3][2]);
			projUnjSL[3] = sl::float4(pu[0][3], pu[1][3], pu[2][3], pu[3][3]);
			sl::float4x4 viewSL;
			sl::matrixFullInvert(viewSL, viewInvSL);
			sl::matrixMul(derivedViewProj, viewSL, projUnjSL);
		}
		// 首帧交叉校验：派生源必须与引擎源一致（相对误差 <= 1%）才允许启用。
		// 构造方式若不对，匹配失败，派生源直接作废 —— 不会引入新病。
		if (!diag.derivedChecked && finiteMag(currViewProjSL) > 1.0e-6f &&
			finiteMag(derivedViewProj) > 1.0e-6f) {
			diag.derivedChecked = 1;
			float worst = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float d[4] = { derivedViewProj[r].x - currViewProjSL[r].x,
				                     derivedViewProj[r].y - currViewProjSL[r].y,
				                     derivedViewProj[r].z - currViewProjSL[r].z,
				                     derivedViewProj[r].w - currViewProjSL[r].w };
				for (int k = 0; k < 4; ++k) {
					const float a2 = d[k] < 0.0f ? -d[k] : d[k];
					if (!(a2 <= 1.0e7f)) { worst = 1.0e30f; break; }   // NaN/Inf
					if (a2 > worst) worst = a2;
				}
			}
			diag.derivedMatchErr = worst;
			diag.derivedMatch = (worst <= finiteMag(currViewProjSL) * 0.01f) ? 1 : 0;
		}

		// ---- 引擎 cur 是否冻结 ----
		static sl::float4x4 s_lastEngCur{};
		static bool s_hasLastEngCur = false;
		static std::uint32_t s_engCurFrozen = 0;
		const bool engCurOk = finiteMag(currViewProjSL) > 1.0e-6f;
		if (engCurOk) {
			if (s_hasLastEngCur && sameMat(s_lastEngCur, currViewProjSL))
				++s_engCurFrozen;
			else
				s_engCurFrozen = 0;
			s_lastEngCur = currViewProjSL;
			s_hasLastEngCur = true;
			if (s_engCurFrozen > diag.engCurFrozenRun)
				diag.engCurFrozenRun = s_engCurFrozen;
		}

		// ---- 选源：引擎 cur 连续冻结 >= 30 帧且派生源通过校验 -> 换派生源 ----
		const bool useDerived = (diag.derivedMatch == 1) && (s_engCurFrozen >= 30) &&
		                        finiteMag(derivedViewProj) > 1.0e-6f;
		sl::float4x4 curForReproj = useDerived ? derivedViewProj : currViewProjSL;
		const bool curOk = finiteMag(curForReproj) > 1.0e-6f;
		diag.reprojSource = useDerived ? 1 : 0;
		if (useDerived)
			++diag.derivedUsed;
		diag.curMagLast = curOk ? finiteMag(curForReproj) : 0.0f;
		diag.engPrevMagLast = finiteMag(engPrevViewProjSL);

		// ---- 引擎 prev 是否 == cur（"相机运动恒为 0"的直接证据）----
		if (finiteMag(engPrevViewProjSL) > 1.0e-6f) {
			if (sameMat(engPrevViewProjSL, currViewProjSL))
				++diag.engPrevEqCur;
			else
				++diag.engPrevDiffers;
		} else {
			++diag.engPrevZero;
		}

		// ---- 自维护 prev 历史 ----
		// s_prevVP 只在 cur 有效时推进 —— 无效帧（零矩阵）绝不能进历史，否则下一帧
		// 的 prev 就是零，又回到"矩阵无效"。
		static sl::float4x4 s_prevVP{};
		static bool s_hasPrevVP = false;
		sl::float4x4 prevForReproj{};
		bool havePrev = false;
		if (curOk) {
			if (s_hasPrevVP) {
				prevForReproj = s_prevVP;
				havePrev = true;
			}
			s_prevVP = curForReproj;
			s_hasPrevVP = true;
		}

		sl::float4x4 invCurrViewProj;
		if (curOk && havePrev) {
			++diag.prevHistoryHits;
			sl::matrixFullInvert(invCurrViewProj, curForReproj);
			sl::matrixMul(c.clipToPrevClip, invCurrViewProj, prevForReproj);
		} else {
			// 首帧 / cur 无效：单位矩阵。这是安全退化，但会被 prevHistoryMiss 计数
			// 暴露出来 —— 若它长期增长，说明数据源还是有问题。
			++diag.prevHistoryMiss;
			c.clipToPrevClip[0] = { 1.f, 0.f, 0.f, 0.f };
			c.clipToPrevClip[1] = { 0.f, 1.f, 0.f, 0.f };
			c.clipToPrevClip[2] = { 0.f, 0.f, 1.f, 0.f };
			c.clipToPrevClip[3] = { 0.f, 0.f, 0.f, 1.f };
		}
		sl::matrixFullInvert(c.prevClipToPrev, c.clipToPrevClip);
		// 重投影矩阵是否真带运动：|clipToPrev - I| 的窗口最大值。运动中它必须明显
		// 大于 0；恒 0 就说明相机项又被丢掉了（这是判定修复是否生效的那个数）。
		{
			float d = 0.0f;
			for (int r = 0; r < 4; ++r) {
				const float v[4] = { c.clipToPrevClip[r].x, c.clipToPrevClip[r].y,
				                     c.clipToPrevClip[r].z, c.clipToPrevClip[r].w };
				for (int k = 0; k < 4; ++k) {
					const float id = (r == k) ? 1.0f : 0.0f;
					const float a2 = v[k] - id;
					const float m = a2 < 0.0f ? -a2 : a2;
					if (m > d) d = m;
				}
			}
			if (d > diag.clipDevMax) diag.clipDevMax = d;
		}
		if (curOk) ++diag.camValid; else ++diag.camInvalid;
		const bool camValid = curOk;   // 下游的 reset 边沿语义保持不变
		// =====================================================================
"""

# ---------------------------------------------------------------------------
# 3. Streamline.cpp : heartbeat format + args + window reset
# ---------------------------------------------------------------------------
HB_FMT_OLD = '\t\t\t\t\t"capUs={} mult(acc/pres)={}/{} longFrames={} cam(ok/inv)={}/{}",\n'
HB_FMT_NEW = ('\t\t\t\t\t"capUs={} mult(acc/pres)={}/{} longFrames={} cam(ok/inv)={}/{} | "\n'
              '\t\t\t\t\t"reproj src={} engPrevEqCur={}/{} engPrevZero={} frozen={} "\n'
              '\t\t\t\t\t"dvd(ok/used)={}/{} err={:.3g} curMag={:.3g} engPrevMag={:.3g} "\n'
              '\t\t\t\t\t"clipDevMax={:.4f} hist(hit/miss)={}/{} tid={:#x}",\n')

HB_ARG_OLD = "\t\t\t\t\tdiag.camValid, diag.camInvalid);\n"
HB_ARG_NEW = ("\t\t\t\t\tdiag.camValid, diag.camInvalid,\n"
              "\t\t\t\t\tdiag.reprojSource ? \"derived\" : \"engine\",\n"
              "\t\t\t\t\tdiag.engPrevEqCur, diag.engPrevEqCur + diag.engPrevDiffers,\n"
              "\t\t\t\t\tdiag.engPrevZero, diag.engCurFrozenRun,\n"
              "\t\t\t\t\tdiag.derivedMatch, diag.derivedUsed, diag.derivedMatchErr,\n"
              "\t\t\t\t\tdiag.curMagLast, diag.engPrevMagLast,\n"
              "\t\t\t\t\tdiag.clipDevMax,\n"
              "\t\t\t\t\tdiag.prevHistoryHits, diag.prevHistoryMiss,\n"
              "\t\t\t\t\tdiag.tidMarker);\n")

WIN_OLD = ("\t\t\t\tdiag.winMinMs = 0.0;\n"
           "\t\t\t\tdiag.winMaxMs = 0.0;\n"
           "\t\t\t\tdiag.winSumMs = 0.0;\n"
           "\t\t\t\tdiag.winN = 0;\n"
           "\t\t\t\tdiag.longFrames = 0;\n")
WIN_NEW = ("\t\t\t\tdiag.winMinMs = 0.0;\n"
           "\t\t\t\tdiag.winMaxMs = 0.0;\n"
           "\t\t\t\tdiag.winSumMs = 0.0;\n"
           "\t\t\t\tdiag.winN = 0;\n"
           "\t\t\t\tdiag.longFrames = 0;\n"
           "\t\t\t\tdiag.clipDevMax = 0.0f;\n")

VD_OLD = ('\t\t\t\tif (diag.camInvalid > 0 &&\n'
          '\t\t\t\t\tdiag.camInvalid * 4 > (diag.camValid + diag.camInvalid))\n'
          '\t\t\t\t\tvd = "camera data INVALID on " + std::to_string(diag.camInvalid) + " of " +\n'
          '\t\t\t\t\t     std::to_string(diag.camValid + diag.camInvalid) +\n'
          '\t\t\t\t\t     " frames -> ClipToPrevClip was zero and got clamped to identity "\n'
          '\t\t\t\t\t     "(that IS the flicker source: DLSS-G reprojects with it)";\n')
VD_NEW = ('\t\t\t\tif (diag.tidMarker == 0xFFFFFFFFu)\n'
          '\t\t\t\t\tvd = "PROBLEM two threads are calling slSetConstants -> the self-maintained "\n'
          '\t\t\t\t\t     "viewProj history is being interleaved";\n'
          '\t\t\t\telse if (diag.derivedChecked && diag.derivedMatch == 0)\n'
          '\t\t\t\t\tvd = "derived viewProj does not match the engine source (maxErr=" +\n'
          '\t\t\t\t\t     std::to_string(diag.derivedMatchErr) + ") -> fallback disabled; if the "\n'
          '\t\t\t\t\t     "engine viewProj is frozen the reprojection stays identity";\n'
          '\t\t\t\telse if (diag.engPrevDiffers == 0 &&\n'
          '\t\t\t\t\t(diag.engPrevEqCur + diag.engPrevZero) > 0)\n'
          '\t\t\t\t\tvd = std::string("flicker cause: the engine previousViewProj is USELESS on every ") +\n'
          '\t\t\t\t\t     "frame (== cur " + std::to_string(diag.engPrevEqCur) + ", zero " +\n'
          '\t\t\t\t\t     std::to_string(diag.engPrevZero) + ") -> v0.65 now uses self-maintained "\n'
          '\t\t\t\t\t     "history; moving frames must show clipDevMax > 0 (was 1.000000 = identity)";\n'
          '\t\t\t\telse if (diag.engCurFrozenRun > 120 && diag.derivedUsed == 0)\n'
          '\t\t\t\t\tvd = "PROBLEM engine viewProj frozen for " + std::to_string(diag.engCurFrozenRun) +\n'
          '\t\t\t\t\t     " frames and the derived source is unavailable -> clipToPrevClip collapses "\n'
          '\t\t\t\t\t     "to identity (THIS is the flicker)";\n'
          '\t\t\t\telse if (diag.prevHistoryMiss * 4 > (diag.prevHistoryHits + diag.prevHistoryMiss))\n'
          '\t\t\t\t\tvd = "PROBLEM reprojection history missing on " +\n'
          '\t\t\t\t\t     std::to_string(diag.prevHistoryMiss) + " frames";\n')

# ---------------------------------------------------------------------------
# 4. FrameGen.cpp : copy BEFORE Unmap, thread_local slot
# ---------------------------------------------------------------------------
FG_NS_OLD = "\tnamespace\n\t{\n\t\tstruct ID3D11DeviceContext_Map\n"
FG_NS_NEW = ("\tnamespace\n\t{\n"
             "\t\t// v0.65: 每个线程各自的\"当前已映射的 perFrame 指针\"。这个钩子实测被\n"
             "\t\t// 不止一个线程命中（Transfusion [MOTION] 的 tid 在 40760 / 3508 之间\n"
             "\t\t// 交替），共享成员会被交叉覆盖，Unmap 时就会拷到别的线程的内存。\n"
             "\t\tthread_local FrameBuffer* tlsMappedFB = nullptr;\n\n"
             "\t\tstruct ID3D11DeviceContext_Map\n")

FG_MAP_OLD = ("\t\t\t\tif (SUCCEEDED(hr) && pMappedResource) {\n"
              "\t\t\t\t\tauto* perFrame = FrameGen::GetPerFrameBuffer();\n"
              "\t\t\t\t\tif (perFrame && *perFrame == pResource && pMappedResource->pData)\n"
              "\t\t\t\t\t\tGet().SetMappedFrameBuffer(static_cast<FrameBuffer*>(pMappedResource->pData));\n"
              "\t\t\t\t}\n")
FG_MAP_NEW = ("\t\t\t\ttlsMappedFB = nullptr;\n"
              "\t\t\t\tif (SUCCEEDED(hr) && pMappedResource) {\n"
              "\t\t\t\t\tauto* perFrame = FrameGen::GetPerFrameBuffer();\n"
              "\t\t\t\t\tif (perFrame && *perFrame == pResource && pMappedResource->pData)\n"
              "\t\t\t\t\t\ttlsMappedFB = static_cast<FrameBuffer*>(pMappedResource->pData);\n"
              "\t\t\t\t}\n")

FG_UNMAP_OLD = ("\t\t\t\tfunc(This, pResource, Subresource);\n"
                "\t\t\t\t// v0.5：Unmap 时内容完整 → 值拷贝到自有缓冲（Present 线程读稳定副本，\n"
                "\t\t\t\t// 消除跨线程读半写 UB；同时让 Unmap 钩子有意义）\n"
                "\t\t\t\tauto* perFrame = FrameGen::GetPerFrameBuffer();\n"
                "\t\t\t\tif (perFrame && *perFrame == pResource) {\n"
                "\t\t\t\t\tauto& fg = Get();\n"
                "\t\t\t\t\tif (fg.GetFrameBuffer()) {\n"
                "\t\t\t\t\t\tfg.frameBufferCopy = *fg.GetFrameBuffer();\n"
                "\t\t\t\t\t\tfg.SetMappedFrameBuffer(&fg.frameBufferCopy);\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n")
FG_UNMAP_NEW = ("\t\t\t\t// v0.65：拷贝必须发生在**原始 Unmap 之前**。旧版在 func() 之后才读\n"
                "\t\t\t\t// pData —— 那时已经解映射，驱动可以立刻回收/复用这块内存，实测约\n"
                "\t\t\t\t// 45% 的帧因此读到全零（心跳 prevVP 恰好 = 1.0000 = 零矩阵指纹）。\n"
                "\t\t\t\tif (tlsMappedFB) {\n"
                "\t\t\t\t\tauto& fg = Get();\n"
                "\t\t\t\t\tfg.frameBufferCopy = *tlsMappedFB;\n"
                "\t\t\t\t\tfg.SetMappedFrameBuffer(&fg.frameBufferCopy);\n"
                "\t\t\t\t\ttlsMappedFB = nullptr;\n"
                "\t\t\t\t}\n"
                "\t\t\t\tfunc(This, pResource, Subresource);\n")

MARKER = "v0.65: reprojection source"

# ---------------------------------------------------------------------------
EDITS = [
    ("Streamline.h : diag fields", "Streamline.h", H_ANCHOR, H_ANCHOR + H_NEW),
    ("Streamline.cpp : reproj block", "Streamline.cpp", CPP_OLD_BLOCK, CPP_NEW_BLOCK),
    ("Streamline.cpp : heartbeat fmt", "Streamline.cpp", HB_FMT_OLD, HB_FMT_NEW),
    ("Streamline.cpp : heartbeat args", "Streamline.cpp", HB_ARG_OLD, HB_ARG_NEW),
    ("Streamline.cpp : window reset", "Streamline.cpp", WIN_OLD, WIN_NEW),
    ("Streamline.cpp : VERDICT", "Streamline.cpp", VD_OLD, VD_NEW),
    ("FrameGen.cpp : tls slot", "FrameGen.cpp", FG_NS_OLD, FG_NS_NEW),
    ("FrameGen.cpp : Map thunk", "FrameGen.cpp", FG_MAP_OLD, FG_MAP_NEW),
    ("FrameGen.cpp : Unmap thunk", "FrameGen.cpp", FG_UNMAP_OLD, FG_UNMAP_NEW),
]


def block_span(text, start_anchor, end_anchor):
    """Return (start_idx, end_idx) of the region from start_anchor to the line
    containing end_anchor (inclusive, including trailing newline)."""
    si = text.find(start_anchor)
    if si < 0:
        return -1, -1
    ei = text.find(end_anchor, si)
    if ei < 0:
        return -1, -1
    ei = text.find("\n", ei)
    return si, (ei + 1 if ei >= 0 else len(text))


def main():
    apply = "--apply" in sys.argv

    files = {}
    for _, fname, _, _ in EDITS:
        if fname not in files:
            files[fname] = File(ROOT + "/" + fname)

    # guard: whole-block replacement of the reprojection region
    rp_start = "// prev 帧矩阵（引擎提供的 prev viewproj）——值拷贝避免引用推导歧义"
    rp_end = "// ====================================================================="
    t = files["Streamline.cpp"].text
    s_idx, e_idx = block_span(t, rp_start, rp_end)
    if s_idx < 0:
        print("REFUSED: cannot locate the reprojection block (start=%d end=%d)"
              % (s_idx, e_idx))
        return 1
    old_block = t[s_idx:e_idx]
    print("[block] reprojection region: %d bytes, %d lines"
          % (len(old_block), old_block.count("\n")))

    # idempotency marker check FIRST (see the skill's rule: anchor uniqueness is
    # not the same thing as "this patch has not run yet")
    for fname, f in files.items():
        if MARKER in f.text:
            print("REFUSED: marker %r already present in %s -- patch already applied"
                  % (MARKER, fname))
            return 1

    # verify every anchor is unique BEFORE touching anything
    ok = True
    simple = [(lbl, fn, o, n) for (lbl, fn, o, n) in EDITS
              if lbl != "Streamline.cpp : reproj block"]
    for lbl, fname, old, new in simple:
        c = files[fname].text.count(old)
        status = "OK" if c == 1 else "FAIL"
        if c != 1:
            ok = False
        print("[%-30s] anchor count=%d %s" % (lbl, c, status))
    if not ok:
        print("REFUSED: at least one anchor is not unique (or is stale).")
        return 1

    # substitute the whole block first (it is the only non-anchor edit)
    files["Streamline.cpp"].text = (
        t[:s_idx] + CPP_NEW_BLOCK + t[e_idx:])

    for lbl, fname, old, new in simple:
        f = files[fname]
        c = f.text.count(old)
        if c != 1:
            print("REFUSED mid-flight: %s anchor count=%d" % (lbl, c))
            return 1
        f.text = f.text.replace(old, new)
        print("[%-30s] applied" % lbl)

    # readback verification
    print("\n--- readback ---")
    cpp = files["Streamline.cpp"].text
    checks = [
        ("v0.65 marker", MARKER in cpp),
        ("self-maintained history", "s_prevVP = curForReproj;" in cpp),
        ("derived source", "sl::matrixMul(derivedViewProj, viewSL, projUnjSL);" in cpp),
        ("derived cross-check", "diag.derivedMatch = (worst <= finiteMag(currViewProjSL) * 0.01f) ? 1 : 0;" in cpp),
        ("old zero-clamp gone", "c.clipToPrevClip was zero and got clamped to identity" not in cpp),
        ("clipDevMax probe", "if (d > diag.clipDevMax) diag.clipDevMax = d;" in cpp),
    ]
    hh = files["Streamline.h"].text
    checks += [
        ("diag engPrevEqCur", "std::uint64_t engPrevEqCur = 0;" in hh),
        ("diag derivedMatch", "std::uint64_t derivedMatch = 0;" in hh),
        ("diag clipDevMax", "float clipDevMax = 0.0f;" in hh),
    ]
    fg = files["FrameGen.cpp"].text
    checks += [
        ("tls slot", "thread_local FrameBuffer* tlsMappedFB = nullptr;" in fg),
        ("unmap copy-before", "fg.frameBufferCopy = *tlsMappedFB;" in fg),
        ("no post-unmap read", "fg.frameBufferCopy = *fg.GetFrameBuffer();" not in fg),
    ]
    allok = True
    for name, res in checks:
        print("  %-26s %s" % (name, "OK" if res else "FAIL"))
        if not res:
            allok = False
    if not allok:
        print("REFUSED: readback failed, nothing written.")
        return 1

    if not apply:
        print("\nDRY RUN OK - %d edits in %d files. Re-run with --apply to write."
              % (len(EDITS), len(files)))
        return 0

    # backup + write, preserving each file's original EOL
    print("\n--- writing ---")
    for fname, f in files.items():
        bak = f.path + ".bak-" + STAMP
        shutil.copy2(f.path, bak)
        data = f.render()
        with open(f.path, "wb") as fh:
            fh.write(data)
        # verify EOL preserved
        eol2 = detect_eol(data)
        print("  %-18s %6d -> %6d bytes | eol %s -> %s %s | backup %s"
              % (fname, len(f.orig.encode("utf-8")), len(data),
                 repr(f.eol), repr(eol2),
                 "OK" if eol2 == f.eol else "CHANGED!",
                 bak.split("/")[-1]))
    print("\nAPPLIED. Rebuild with: bash build_vs.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
