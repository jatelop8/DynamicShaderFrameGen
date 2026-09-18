#!/usr/bin/env python3
"""
v0.82 -- fix the frozen-camera bug caused by thread_local prev history.

ROOT CAUSE (established from the 09:39 log, 2026-09-18):

  `CheckFrameConstants()` runs once per Presented frame, but Present() is driven
  by TWO engine threads that alternate (proven by the FPS probe thread column:
  22548,22548,22548,3236,3236,22548,22548,3236,3236,3236,3236).

  v0.66 made the self-maintained prev history `thread_local`:

      thread_local sl::float4x4 s_prevVP{};
      thread_local bool s_hasPrevVP = false;

  So when the presenter switches threads, the new thread starts with
  s_hasPrevVP == false -> havePrev == false -> the code falls into the `else`
  branch and writes `setIdentity(c.clipToPrevClip)`.

  clipToPrevClip == I means "the camera did not move" to DLSS-G.  It therefore
  generates NO interpolated frames -> the picture freezes.  Meanwhile the engine
  still renders real frames, so animated engine particles (the campfire) keep
  moving.  That is exactly the user's report:
      "基本上是冻结得，只有火还会一跳跳"

  Log evidence:
      det(min/max) = 1.000/1.000   (8 samples)  <- det == 1 IFF prev == cur
      detGuard/detHold = 0/0                     <- the det guard never fired
      clipDevMax = 0.0000  (all samples)         <- reprojection carries no motion

WHAT THIS PATCH CHANGES (three edits, all inside CheckFrameConstants):

  A. Drop `thread_local` from the prev history, and document why.  The history
     must describe "the previous frame shown", not "the previous frame shown by
     this thread".  Two threads alternate, so per-thread history is always cold.

  B. When there is no self-maintained history yet, SEED it from the engine's own
     CameraPreviousViewProjUnjittered instead of lying "no motion".  The engine
     field is zero in this build (engPrevZero=241), so the seed additionally has
     to be sanity-checked: only a finite, non-degenerate matrix is accepted.

  C. Replace the bare `setIdentity()` in the no-history branch with
     `s_lastGoodClip` reuse when one exists -- same idea as the v0.67 det guard
     already used a few lines above: "再上一帧的真实位移是远好得多的估计".

  Note that the `useDerived` path (v0.69) and the det guard (v0.66/v0.67) are
  untouched.  The guard fires 0 times in the log, so it is not implicated.

Run without arguments for a dry run; pass --apply to write.
"""

import io
import re
import sys

CPP = "src/Streamline.cpp"

# ---------------------------------------------------------------- anchors ----

# A. thread_local prev history -> shared, with a corrected comment.
A_OLD = """		// ---- 自维护 prev 历史 ----
		// s_prevVP 只在 cur 有效时推进 —— 无效帧（零矩阵）绝不能进历史，否则下一帧
		// 的 prev 就是零，又回到"矩阵无效"。
		// v0.66：thread_local。跨线程共享这份历史，会让计算用上「别的线程的上一帧」
		// —— 那正是观测到 clipDev=15.002136（跨组相减）的成因。
		thread_local sl::float4x4 s_prevVP{};
		thread_local bool s_hasPrevVP = false;
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
"""

A_NEW = """		// ---- 自维护 prev 历史 ----
		// s_prevVP 只在 cur 有效时推进 —— 无效帧（零矩阵）绝不能进历史，否则下一帧
		// 的 prev 就是零，又回到"矩阵无效"。
		//
		// v0.82：**改回共享，撤销 v0.66 的 thread_local**。
		// v0.66 的理由是"跨线程共享会让计算用上别的线程的上一帧"，但那个理由只在
		// 「一个线程独占 Present」时成立。实测（09:39 日志的 FPS probe 线程列）
		// Present() 被 **两个引擎线程交替**驱动：
		//     22548,22548,22548,3236,3236,22548,22548,3236,3236,3236,3236
		// 于是每次切换，新线程的 s_hasPrevVP 都是 false ⇒ havePrev=false ⇒
		// clipToPrevClip 被写成单位矩阵 = 告诉 DLSS-G「相机没动」⇒ **不产出插帧**。
		// 这就是"进世界后整体冻结、只有引擎粒子（火堆）还在动"的直接成因：
		// 真实帧照常渲染，插帧全没了。
		// 日志指纹：det(min/max)=1.000/1.000（det==1 当且仅当 prev==cur）、
		//           clipDevMax=0.0000、detGuard/detHold=0/0（守卫根本没触发）。
		//
		// 这里改成"按帧"维护：历史属于「上一帧呈现的相机」，不属于「上一个线程」。
		// 同一时刻只有一条 Present 线程流在推进，故不加锁也是安全的写者；读到的
		// 顶多是被另一个线程刚更新的、时间上更近的一帧 —— 那正是我们要的语义。
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
		// v0.82: 没有自维护历史时，先试引擎自己的 prev（CameraPreviousViewProjUnjittered）。
		// 本构建里该字段恒为零矩阵（engPrevZero=241），所以必须做有效性校验：
		// 只有有限、非退化的矩阵才接受；否则宁可退回 s_lastGoodClip。
		if (!havePrev && curOk && finiteMag(engPrevViewProjSL) > 1.0e-6f) {
			prevForReproj = engPrevViewProjSL;
			havePrev = true;
			++diag.prevSeededFromEngine;
		}
"""

# B. s_lastGoodClip must be declared BEFORE the seed uses it, and must stop
#    being thread_local too (it is the same "previous frame shown" history).
B_OLD = """		// v0.67：守卫触发时保留上一帧**合法**的 clipToPrevClip，不再写单位矩阵。
		// 「单位矩阵」在 DLSS-G 眼里是「相机没动」—— 那是一句谎话，会让它的遮挡/
		// 去遮挡判断整体错位；上一帧的真实位移是远好得多的估计。detHold 把它暴露出来。
		thread_local sl::float4x4 s_lastGoodClip{};
		thread_local bool s_hasLastGoodClip = false;
"""

B_NEW = """		// v0.67：守卫触发时保留上一帧**合法**的 clipToPrevClip，不再写单位矩阵。
		// 「单位矩阵」在 DLSS-G 眼里是「相机没动」—— 那是一句谎话，会让它的遮挡/
		// 去遮挡判断整体错位；上一帧的真实位移是远好得多的估计。detHold 把它暴露出来。
		// v0.82：同样撤销 thread_local（理由见上）。这份历史是"上一帧的合法位移"，
		// 线程切换后它依然有效，丢掉它只会让新线程重新用单位矩阵。
		static sl::float4x4 s_lastGoodClip{};
		static bool s_hasLastGoodClip = false;
"""

# C. The no-history branch: never lie "no motion" when a good clip is available.
C_OLD = """		} else {
			// 首帧 / cur 无效：单位矩阵。这是安全退化，但会被 prevHistoryMiss 计数
			// 暴露出来 —— 若它长期增长，说明数据源还是有问题。
			++diag.prevHistoryMiss;
			setIdentity(c.clipToPrevClip);
		}
"""

C_NEW = """		} else {
			// 首帧 / cur 无效：这是安全退化，但会被 prevHistoryMiss 计数暴露出来 ——
			// 若它长期增长，说明数据源还是有问题。
			//
			// v0.82：**绝不无条件写单位矩阵**。单位矩阵在 DLSS-G 眼里等于
			// 「相机没动」——那是一句谎话，会让它停止产出插帧（本工程的冻结就是它）。
			// 优先复用一个合法的历史位移；只有连历史都没有（真正的第一帧）才退回单位。
			++diag.prevHistoryMiss;
			if (s_hasLastGoodClip) {
				c.clipToPrevClip = s_lastGoodClip;
				++diag.prevMissUsedLastGood;
			} else {
				setIdentity(c.clipToPrevClip);
			}
		}
"""

EDITS = [
    ("A: prev history shared", A_OLD, A_NEW),
    ("B: lastGoodClip shared", B_OLD, B_NEW),
    ("C: no-history never lies", C_OLD, C_NEW),
]

# Idempotence guards: each marker must be ABSENT before applying.
MARKERS = [
    "v0.82：**改回共享，撤销 v0.66 的 thread_local**",
    "v0.82：同样撤销 thread_local",
    "v0.82：**绝不无条件写单位矩阵**",
]

COUNTERS = ["prevSeededFromEngine", "prevMissUsedLastGood"]


def read(p):
    with io.open(p, "rb") as f:
        return f.read().decode("utf-8")


def write(p, s):
    with io.open(p, "wb") as f:
        f.write(s.encode("utf-8"))


def brace_delta(s):
    """Net brace balance contribution (crude but enough to catch truncation)."""
    return s.count("{") - s.count("}")


def main():
    apply = "--apply" in sys.argv
    src = read(CPP)
    print("=" * 74)
    print("v0.82 prev-history shared  (mode: %s)" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    # ---- guard 1: markers must be absent (patch has not run) -----------------
    present = [m for m in MARKERS if m in src]
    if present:
        print("markers   : ALREADY PRESENT -> REFUSED, nothing written")
        for m in present:
            print("   found: %s" % m)
        return 2
    print("markers   : absent (patch has not run)")

    # ---- guard 2: every anchor must occur exactly once ----------------------
    ok = True
    for label, old, new in EDITS:
        n = src.count(old)
        status = "ok" if n == 1 else "FAIL"
        if n != 1:
            ok = False
        print("  [%-26s] occurrences=%d  %s" % (label, n, status))
    if not ok:
        print("REFUSED: anchor is not unique. nothing written.")
        return 2

    # ---- guard 3: brace delta of each edit must be zero ---------------------
    for label, old, new in EDITS:
        d = brace_delta(new) - brace_delta(old)
        status = "ok" if d == 0 else "FAIL"
        if d != 0:
            ok = False
        print("balance   : %-26s %+d  %s" % (label, d, status))
    if not ok:
        print("REFUSED: edit changes brace balance. nothing written.")
        return 2

    # ---- apply --------------------------------------------------------------
    out = src
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)

    # ---- guard 4: new counters must be declared in Streamline.h -------------
    hdr = read("src/Streamline.h")
    missing = [c for c in COUNTERS if c not in hdr]
    if missing:
        print("")
        print("NOTE: these counters are referenced by the new code but NOT declared")
        print("      in src/Streamline.h yet: %s" % ", ".join(missing))
        print("      -> run tools/add_v082_diag_counters.py first (or together).")

    print("")
    print("  %-28s %7d -> %7d bytes (%+d)" % (CPP, len(src.encode("utf-8")),
                                              len(out.encode("utf-8")),
                                              len(out.encode("utf-8")) - len(src.encode("utf-8"))))
    if not apply:
        print("DRY RUN: nothing written. Re-run with --apply.")
        return 0

    write(CPP, out)
    print("WRITTEN   : %s" % CPP)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
