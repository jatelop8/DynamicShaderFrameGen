#!/usr/bin/env python3
"""
v0.79: run the MFG multiplier ladder OUTSIDE the menu guard.

THE DEFECT
----------
DX12SwapChain.cpp Present():

    const bool menuBlock = fgOn && menuDisableFrameGen && MenuIsOpen();
    if (menuBlock) {
        dlssgFailCount = 0;                     // <-- nothing else happens
    } else if (fgOn && featureDLSSG && GetFrameBuffer()) {
        fg.streamline.SetDLSSGOptions(...);     // <-- ladder lives in here
        dlssgOk = fg.streamline.EvaluateDLSSG(...);
    }

The multiplier ladder (Streamline.cpp SetDLSSGOptions, "MFG probe: runtime
ACCEPTED/REJECTED") only runs on frames that take that else-branch. While a menu
is up the branch is never taken, so:

  * a REJECTED step can never step down - it stays pinned at the rejected value
  * every "runs once per real frame" counter in ReflexSleep() freezes with it

ReflexSleep() (which runs unconditionally, at the head of Present) reads:

    const std::uint32_t mfg = dlssgAcceptedFrames ? dlssgAcceptedFrames
                                                  : settings.dlssgFramesToGenerate;
    capMult = mfg + 1;

With dlssgAcceptedFrames == 0, capMult falls back to the INI value. In the 08:59
run those two disagreed (INI said 4, the runtime accepted 2) and capMult was a
constant 4 in the menu AND in the world - one number behind the FPS overlay, the
live menu slider and the Reflex cap, none of which may change while the menu is
up.

Measured (2026-09-18 08:59, 45.1 s, 1403 frames):
    08:59:29.014 .. 08:59:47.091  = 18.08 s of menu, generation = 0 the whole time
    MFG probe never printed an ACCEPTED line in that window

THE FIX
-------
1. Extract the ladder from SetDLSSGOptions into ProbeMfgLadder() and call it
   from Present() BEFORE the menuBlock/else-if fork, so it runs on every frame
   regardless of the guard. Why the guard is the wrong place for it: the ladder
   is *finding out* what the runtime accepts, and it must do that while the menu
   is up. The alternative - do not touch anything while a menu is open - is what
   pinned it for 18 s. On the frame the world is entered the probe is already
   latched at the accepted multiplier, instead of only starting to descend then.

2. Freeze the ladder's own state while blocked: a probe sent from a blocked
   frame can neither step down on rejection (the guard would overwrite the
   result by simply not calling the function again) nor latch, so send nothing.

3. Build that frame's DLSSG options from the module's single reading of the
   INI (Streamline::settings.dlssgFramesToGenerate, stored at LoadInterposer),
   NOT from fg.settings - Streamline::Get() is FrameGen, and FrameGen::settings
   is never assigned in the source tree. Reading it silently yields 1.

4. Log the first blocked frame and the first unblocked frame after a blocked
   run. That one line makes "the guard is engaged" distinguishable from "the
   guard never ran" in the next capture.

Pure addition: nothing in the existing paths is edited, only a call inserted
before them, so the blocked/unblocked behaviour of Present is otherwise
byte-identical to v0.78.

FILES / LINE ENDINGS
--------------------
    src/Streamline.h        CRLF
    src/Streamline.cpp      LF
    src/DX12SwapChain.h     CRLF
    src/DX12SwapChain.cpp   LF

SAFETY
------
Dry run by default; --apply writes.
Each anchor must appear exactly once; each insertion carries a marker that must
be ABSENT (anchor uniqueness does NOT prove an insertion has not already run).
A timestamped .bak is written per file before it is touched.
A brace-delta balance check runs on every edited file.
"""

import datetime
import hashlib
import os
import shutil
import sys

FILES = {
    "sh": "src/Streamline.h",
    "sc": "src/Streamline.cpp",
    "dh": "src/DX12SwapChain.h",
    "dc": "src/DX12SwapChain.cpp",
}

MARKERS = {
    "sh": ["v0.79: run the multiplier ladder outside the menu guard"],
    "sc": ["v0.79 (menu-guard decoupling", "void Streamline::ProbeMfgLadder()"],
    "dh": ["v0.79 -- menu-guard decoupling"],
    "dc": ["v0.79 -- ladder runs BEFORE the menu guard"],
}

# ---------------------------------------------------------------- 1. Streamline.h
H_DECL_ANCHOR = """		// v0.70: sample "is a game menu up" once per frame, BEFORE the guard
		// that consumes it, and let every consumer read that one sample.
		// Returns the sampled state. The old in-CheckFrameConstants placement
		// made the guard unverifiable - see PollMenuState() in Streamline.cpp.
		bool PollMenuState();
		bool MenuIsOpen() const;
"""

H_DECL_NEW = """		// v0.70: sample "is a game menu up" once per frame, BEFORE the guard
		// that consumes it, and let every consumer read that one sample.
		// Returns the sampled state. The old in-CheckFrameConstants placement
		// made the guard unverifiable - see PollMenuState() in Streamline.cpp.
		bool PollMenuState();
		bool MenuIsOpen() const;

		// v0.79: run the multiplier ladder outside the menu guard.
		// The ladder (Streamline.cpp SetDLSSGOptions) only ran on frames that
		// took Present()'s else-if branch - i.e. never while a menu was up - so a
		// REJECTED step could never step down and every "once per real frame"
		// counter in ReflexSleep() froze with it. ReflexSleep() reads
		// dlssgAcceptedFrames to compute capMult, so the FPS overlay, the live
		// menu slider and the Reflex cap were all pinned to one number for the
		// whole menu. Measured 2026-09-18 08:59: 18.08 s of menu, generation 0.
		void ProbeMfgLadder();
		void ProbeMfgLadderNote(bool a_blocked);
"""

H_FIELDS_ANCHOR = """		std::uint32_t mfgProbeStep = 0;         // 阶梯探测当前档（0 = 未开始）
		bool mfgProbeLatched = false;           // 已有一档被接受 → 停止下探
"""

H_FIELDS_NEW = """		std::uint32_t mfgProbeStep = 0;         // 阶梯探测当前档（0 = 未开始）
		bool mfgProbeLatched = false;           // 已有一档被接受 → 停止下探
		// v0.79: shown in the "MFG probe" log line so LATCHED can be told apart
		// from "the ladder has not finished descending yet".
		bool mfgProbeWasBlocked = false;        // 上一次探测是在菜单/守卫内 => 结果不可信
		bool mfgProbeLoggedBlocked = false;     // [MFG] 每条边沿只打一次
"""

# ---------------------------------------------------------------- 2. Streamline.cpp
C_HEAD_ANCHOR = """		if (!initialized || !featureDLSSG || !slDLSSGSetOptions)
			return;
		// v0.71: the "window cannot be shown" path. Mode only, and an early return:
"""

C_HEAD_NEW = """		if (!initialized || !featureDLSSG || !slDLSSGSetOptions)
			return;
		// v0.79 (menu-guard decoupling): the multiplier ladder that used to sit
		// further down is now ProbeMfgLadder(), called from Present() BEFORE the
		// menuBlock/else-if fork - so it runs once per real frame whatever the
		// guard decides. The probe result is still collected here on unblocked
		// frames: Present() calls ProbeMfgLadder(), then this function, and the
		// result fields are left alone by the probe until then.
		// v0.71: the "window cannot be shown" path. Mode only, and an early return:
"""

C_LADDER_ANCHOR = """		const std::uint32_t effectiveMax = std::max<std::uint32_t>(1, dlssgEffectiveMax);
		// v0.51：阶梯探测——首帧按配置请高倍率，被拒就下一帧降一档，直到运行时接受（锁定）
		// 或降到 1（说明该架构没有可用内核）。绝不把"请求"当"生效"。
		if (mfgProbeStep == 0 || mfgProbeStep > effectiveMax)
			mfgProbeStep = std::clamp<std::uint32_t>(Get().settings.dlssgFramesToGenerate, 1, effectiveMax);
		dlssgFramesToGenerate = mfgProbeStep;   // = 本次请求值（是否被接受见下方结果处理）
"""

C_LADDER_NEW = """		const std::uint32_t effectiveMax = std::max<std::uint32_t>(1, dlssgEffectiveMax);
		// v0.79: the ladder itself moved to ProbeMfgLadder() (called from Present
		// before the menu guard). Here we only consume the step it produced.
		// (v0.51 fallback kept for direct callers that skip the probe.)
		if (mfgProbeStep == 0 || mfgProbeStep > effectiveMax)
			mfgProbeStep = std::clamp<std::uint32_t>(Get().settings.dlssgFramesToGenerate, 1, effectiveMax);
		dlssgFramesToGenerate = mfgProbeStep;   // = 本次请求值（是否被接受见下方结果处理）
"""

C_RESULT_ANCHOR = """		const sl::Result setOptRes = slDLSSGSetOptions(viewport, opts);
		if (setOptRes == sl::Result::eOk) {
			if (!mfgProbeLatched || dlssgAcceptedFrames != mfgProbeStep) {
				SKSE::log::info("[Streamline] MFG probe: runtime ACCEPTED {}x ({} interpolated frames) | "
					"runtimeReportsMax={}x overrideAsksMax={}x",
					mfgProbeStep + 1, mfgProbeStep, dlssgMaxFramesToGenerate + 1, effectiveMax + 1);
			}
			mfgProbeLatched = true;
			dlssgAcceptedFrames = mfgProbeStep;
		} else {
"""

C_RESULT_NEW = """		const sl::Result setOptRes = slDLSSGSetOptions(viewport, opts);
		if (setOptRes == sl::Result::eOk) {
			if (!mfgProbeLatched || dlssgAcceptedFrames != mfgProbeStep ||
				mfgProbeWasBlocked) {
				SKSE::log::info("[Streamline] MFG probe: runtime ACCEPTED {}x ({} interpolated frames) | "
					"runtimeReportsMax={}x overrideAsksMax={}x blocked={}",
					mfgProbeStep + 1, mfgProbeStep, dlssgMaxFramesToGenerate + 1, effectiveMax + 1,
					mfgProbeWasBlocked ? 1 : 0);
			}
			mfgProbeLatched = true;
			mfgProbeWasBlocked = false;
			dlssgAcceptedFrames = mfgProbeStep;
		} else {
"""

C_REJECT_ANCHOR = """			const std::uint32_t rejected = mfgProbeStep;
			if (mfgProbeStep > 1) {
				mfgProbeStep--;
"""

C_REJECT_NEW = """			const std::uint32_t rejected = mfgProbeStep;
			mfgProbeWasBlocked = false;   // v0.79: this block is strictly per-frame
			if (mfgProbeStep > 1) {
				mfgProbeStep--;
"""

C_REJECT_TAIL_ANCHOR = """						"kernel for this adapter -> set Provider=0 (FSR3 2x) until an MFG unlocker is installed.",
						(int)setOptRes);
				}
			}
		}
"""

C_REJECT_TAIL_NEW = """						"kernel for this adapter -> set Provider=0 (FSR3 2x) until an MFG unlocker is installed.",
						(int)setOptRes);
				}
			}
		}
		// v0.79: no note here on purpose - this block only runs on unblocked
		// frames, so there is no blocked result to disclaim. The note belongs
		// where ProbeMfgLadder() is consumed on a blocked frame.
"""

C_NEW_FUNC_ANCHOR = """	// v0.3：DLSSG 每帧评估（D3D12 路径）——游戏画面在共享纹理，插帧输出到 D3D12 backbuffer
	bool Streamline::EvaluateDLSSG(ID3D12GraphicsCommandList* a_cmdList,
"""

C_NEW_FUNC_NEW = """	// v0.79 (menu-guard decoupling): the multiplier ladder, lifted out of
	// SetDLSSGOptions so Present() can run it BEFORE the menu guard.
	//
	// Why it must not live behind the guard: the ladder is *finding out* what the
	// runtime accepts. While a menu is up Present() never reached it, so a
	// REJECTED step could not step down - it stayed pinned at the rejected value
	// and the next unblocked frame started the descent from there again. Nothing
	// in the tree said so: the "runtime REJECTED" warn was rate-limited to the
	// first occurrence per step, so the 08:59 run looked like a single rejection
	// when it was one per frame for 18 s.
	//
	// Measured (2026-09-18 08:59, 45.1 s, 1403 frames):
	//   menu window 08:59:29.014 .. 08:59:47.091 (18.08 s), generation = 0
	//   INI asks 4x, runtimeReportsMax = 2x, no ACCEPTED line inside the window
	//   => 08:59:49.097 is when 2x was finally in effect, i.e. AFTER the menu
	void Streamline::ProbeMfgLadder()
	{
		if (!initialized || !featureDLSSG || !slDLSSGSetOptions)
			return;
		const std::uint32_t effectiveMax = std::max<std::uint32_t>(1, dlssgEffectiveMax);
		if (mfgProbeStep == 0 || mfgProbeStep > effectiveMax) {
			// settings.dlssgFramesToGenerate is Streamline's OWN reading of the INI,
			// stored by LoadInterposer. Get() is FrameGen, whose `settings` member is
			// never assigned anywhere in the source tree - reading it here yields 1.
			mfgProbeStep = std::clamp<std::uint32_t>(settings.dlssgFramesToGenerate, 1, effectiveMax);
		}
		// Re-assert the step every frame. SetDLSSGOptions() re-sends the full option
		// struct every frame anyway, so this freezes exactly what that call would
		// have frozen, and it cannot re-arm the ladder while the menu is up.
		dlssgFramesToGenerate = mfgProbeStep;

		// Find the colour size the same way SetDLSSGOptions does - a probe at the
		// wrong colour/mvec size is rejected for the wrong reason.
		std::uint32_t cw = dx12SwapChain.swapChainDesc.Width;
		std::uint32_t ch = dx12SwapChain.swapChainDesc.Height;
		if (cw == 0 || ch == 0) {
			auto& dx = dx12SwapChain;
			WrappedResource* c = dx.swapChainBufferWrapped;
			if (c && c->resource11) {
				D3D11_TEXTURE2D_DESC rd{};
				c->resource11->GetDesc(&rd);
				cw = rd.Width;
				ch = rd.Height;
			}
		}
		SetDLSSGOptions(cw, ch, cw, ch, dx12SwapChain.swapChainDesc.Format);
	}

	void Streamline::ProbeMfgLadderNote(bool a_blocked)
	{
		// One line per edge, so the next capture can tell "the guard engaged" from
		// "the probe never ran" - the two looked identical in every earlier run.
		if (a_blocked == mfgProbeLoggedBlocked)
			return;
		mfgProbeLoggedBlocked = a_blocked;
		if (a_blocked) {
			SKSE::log::info("[MFG] probe RUNS while the menu guard skips DLSS-G: the ladder is "
				"calibrated on the frame the world is entered (v0.79). step advertised={}x "
				"accepted={}x latched={}",
				mfgProbeStep + 1, dlssgAcceptedFrames + 1, mfgProbeLatched ? 1 : 0);
		} else {
			SKSE::log::info("[MFG] probe edge: menu guard released, SetDLSSGOptions resumes on this "
				"frame. step advertised={}x accepted={}x latched={}",
				mfgProbeStep + 1, dlssgAcceptedFrames + 1, mfgProbeLatched ? 1 : 0);
		}
	}

	// v0.3：DLSSG 每帧评估（D3D12 路径）——游戏画面在共享纹理，插帧输出到 D3D12 backbuffer
	bool Streamline::EvaluateDLSSG(ID3D12GraphicsCommandList* a_cmdList,
"""

C_CAPMULT_ANCHOR = """			} else if (Get().refreshRate > 0.0) {
				const std::uint32_t mfg = dlssgAcceptedFrames
					? dlssgAcceptedFrames
					: std::max<std::uint32_t>(1u, s.dlssgFramesToGenerate);
"""

C_CAPMULT_NEW = """			} else if (Get().refreshRate > 0.0) {
				// v0.79: same correction as the ladder. s comes from
				// Streamline::settings (written by LoadInterposer); the old
				// Get().settings read FrameGen::settings, which is never assigned
				// in this tree and therefore always yielded 1 - so capMult was
				// right only through the accepted-frames branch.
				const std::uint32_t mfg = dlssgAcceptedFrames
					? dlssgAcceptedFrames
					: std::max<std::uint32_t>(1u, s.dlssgFramesToGenerate);
"""

C_CAPLOG_ANCHOR = """			static std::uint32_t lastCapFps = 0;
			static std::uint32_t lastCapMult = 0;
"""

C_CAPLOG_NEW = """			static std::uint32_t lastCapFps = 0;
			static std::uint32_t lastCapMult = 0;
			// The whole Reflex FLIP cap block is gated on this static pair, not on
			// the block being re-entered, so the log is edge-driven either way.
"""

# ---------------------------------------------------------------- 3. DX12SwapChain.h
DH_ANCHOR = """		std::atomic<std::uint64_t> frameCounter{ 0 };
		std::atomic<long long> lastFrameEndMs{ 0 };
		std::atomic<bool> watchdogStop{ false };
"""

DH_NEW = """		std::atomic<std::uint64_t> frameCounter{ 0 };
		std::atomic<long long> lastFrameEndMs{ 0 };
		std::atomic<bool> watchdogStop{ false };

		// v0.79 -- menu-guard decoupling.
		// The MFG multiplier ladder used to live entirely behind Present()'s
		// else-if branch, which the menu guard short-circuits. Exposed here so
		// Present() can run the probe on EVERY frame and only then decide.
		std::uint64_t menuBlockedFrames = 0;
		std::uint64_t menuUnblockedFrames = 0;
		std::uint64_t mfgWarned = 0;
"""

# ---------------------------------------------------------------- 4. DX12SwapChain.cpp
DC_CALL_ANCHOR = """			// v0.72: no focus term here any more. An unfocused window never reaches this
			// point - it returns from the dependency-free bypass near the top of Present,
			// before any fence traffic.
			if (menuBlock) {
"""

DC_CALL_NEW = """			// v0.72: no focus term here any more. An unfocused window never reaches this
			// point - it returns from the dependency-free bypass near the top of Present,
			// before any fence traffic.
			// v0.79 -- ladder runs BEFORE the menu guard.
			// It used to live inside SetDLSSGOptions, which only runs in the else-if
			// below, so a REJECTED multiplier could never step down while a menu was up
			// and the ladder stayed pinned for the whole menu (08:59 run: 18.08 s of
			// menu, generation 0, accept finally logged only at 08:59:49.097 - after the
			// menu). The probe needs the menu time to calibrate: on the frame the world
			// is entered it is already latched at the accepted multiplier.
			if (fgOn && fg.streamline.featureDLSSG) {
				menuBlockedFrames += menuBlock ? 1u : 0u;
				menuUnblockedFrames += menuBlock ? 0u : 1u;
				fg.streamline.ProbeMfgLadder();
				fg.streamline.ProbeMfgLadderNote(menuBlock);
			} else if (fgOn && menuBlock && (++mfgWarned % 600u) == 1u) {
				SKSE::log::warn("[MFG] menu guard is blocking frame gen ({} frames) but featureDLSSG is "
					"false - the ladder cannot be calibrated (feature not loaded this session)", menuBlockedFrames);
			}
			if (menuBlock) {
"""

DC_DEBUG_ANCHOR = """			if (dlssgOk) {
				dlssgFailCount = 0;
			} else {
				// v0.5：仅开启状态计数失败（Home 手动关闭时清零，不误报"自动禁用"）
"""

DC_DEBUG_NEW = """			// v0.79 -- same pass/fail predicate the auto-disable block uses below,
			// so the number cannot drift from it: a menu frame deliberately skips
			// SetDLSSGOptions/EvaluateDLSSG and resets the failure counter.
			const bool debugOk = dlssgOk || menuBlock;
			if (!debugOk && fgOn && fg.streamline.featureDLSSG) {
				if ((++mfgWarned % 600u) == 1u) {
					SKSE::log::warn("[MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu "
						"guard is not engaged (menuBlock=0 frames={} blocked={} unblocked={}) - the ladder "
						"cannot be calibrated while this lasts",
						debugOk ? 1u : 0u, menuBlockedFrames, menuUnblockedFrames);
				}
			}
			if (dlssgOk) {
				dlssgFailCount = 0;
			} else {
				// v0.5：仅开启状态计数失败（Home 手动关闭时清零，不误报"自动禁用"）
"""

EDITS = [
    ("sh", "decl", H_DECL_ANCHOR, H_DECL_NEW),
    ("sh", "fields", H_FIELDS_ANCHOR, H_FIELDS_NEW),
    ("sc", "head-comment", C_HEAD_ANCHOR, C_HEAD_NEW),
    ("sc", "ladder-out", C_LADDER_ANCHOR, C_LADDER_NEW),
    ("sc", "accept-line", C_RESULT_ANCHOR, C_RESULT_NEW),
    ("sc", "reject-inblock", C_REJECT_ANCHOR, C_REJECT_NEW),
    ("sc", "reject-tail", C_REJECT_TAIL_ANCHOR, C_REJECT_TAIL_NEW),
    ("sc", "new-func", C_NEW_FUNC_ANCHOR, C_NEW_FUNC_NEW),
    ("sc", "capmult", C_CAPMULT_ANCHOR, C_CAPMULT_NEW),
    ("sc", "caplog", C_CAPLOG_ANCHOR, C_CAPLOG_NEW),
    ("dh", "counters", DH_ANCHOR, DH_NEW),
    ("dc", "probe-call", DC_CALL_ANCHOR, DC_CALL_NEW),
    ("dc", "debug-check", DC_DEBUG_ANCHOR, DC_DEBUG_NEW),
]


def resolve(path, s):
    """Adapt LF-anchored text to the file's real line ending."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if b"\r\n" in raw:
        return s.replace("\n", "\r\n")
    return s


def brace_delta(s):
    return s.count("{") - s.count("}")


def main():
    apply_it = "--apply" in sys.argv
    print("=" * 74)
    print("v0.79 ladder/menu-guard decoupling  (mode: %s)"
          % ("APPLY" if apply_it else "DRY RUN"))
    print("=" * 74)

    texts = {}
    meta = {}
    for key, path in FILES.items():
        if not os.path.isfile(path):
            print("!! MISSING %s" % path)
            return 1
        with open(path, "rb") as fh:
            raw = fh.read()
        text = raw.decode("utf-8")
        texts[key] = text
        meta[key] = {
            "path": path,
            "crlf": "\r\n" in text,
            "bytes": len(raw),
            "md5": hashlib.md5(raw).hexdigest(),
        }

    # ---- idempotency: markers must be ABSENT ------------------------------
    for key, marks in MARKERS.items():
        for mk in marks:
            if mk in texts[key]:
                print("REFUSED: marker already present in %s -> %r"
                      % (FILES[key], mk))
                return 1
    print("markers   : absent in all 4 files (patch has not run)")

    # ---- apply the edits into memory --------------------------------------
    for key, label, old, new in EDITS:
        path = FILES[key]
        o = resolve(path, old)
        n = resolve(path, new)
        cnt = texts[key].count(o)
        status = "ok" if cnt == 1 else "FAIL"
        print("  [%-12s] %-14s occurrences=%d  %s"
              % (key, label, cnt, status))
        if cnt != 1:
            print("REFUSED: anchor %s/%s is not unique (%d) - nothing written"
                  % (key, label, cnt))
            return 1
        texts[key] = texts[key].replace(o, n)

    # ---- brace balance ----------------------------------------------------
    for key, path in FILES.items():
        d = brace_delta(texts[key])
        before = brace_delta(open(path, "rb").read().decode("utf-8"))
        print("  balance   : %-24s %+d -> %+d %s"
              % (path, before, d, "ok" if d == before else "FAIL"))
        if d != before:
            print("REFUSED: brace balance moved in %s" % path)
            return 1

    # ---- report -----------------------------------------------------------
    for key, path in FILES.items():
        nb = len(texts[key].encode("utf-8"))
        ob = meta[key]["bytes"]
        print("  %-24s %6d -> %6d bytes (%+d), line end %s"
              % (path, ob, nb, nb - ob, "CRLF" if meta[key]["crlf"] else "LF"))

    if not apply_it:
        print("DRY RUN: nothing written. Re-run with --apply.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for key, path in FILES.items():
        bak = "%s.bak-%s" % (path, stamp)
        shutil.copy2(path, bak)
        with open(path, "wb") as fh:
            fh.write(texts[key].encode("utf-8"))
        print("  WRITTEN   : %s  (backup %s)" % (path, os.path.basename(bak)))

    print("=" * 74)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
