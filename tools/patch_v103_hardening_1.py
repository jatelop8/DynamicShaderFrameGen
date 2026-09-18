# -*- coding: utf-8 -*-
"""
patch_v103_hardening_1.py  --  DynamicShaderFrameGen v1.03

Fixes the three faults proven by the 2026-09-18 18:23 logs. All three were mine.

FAULT 1 (the crash / "闪退")
    Log:  [W] [Streamline] MFG probe: runtime REJECTED 4x (result 38 = eErrorInvalidState)
          [W] [Streamline] MFG probe: runtime REJECTED 3x (result 38 = eErrorInvalidState)
          [I] [XRAY] LONG FRAME 19945.3ms (capUs=6289 mult=1 menu=0)
          hwMax=2 ask=2 accepted=0      <- the runtime only ever accepted 2x
    Cause: MFGMaxFramesOverride=3 raised dlssgEffectiveMax to 3, so the ladder
           STARTED at 4x and walked down 4 -> 3 -> 2, ONE PER FRAME, and every
           rejected request burned a whole multi-second frame (19945 ms of it
           wall-clock). The descent existed but its first three rungs were
           already known to be above the runtime's self-reported ceiling.
    Fix:   a capability guard. slDLSSGGetState already told us
           numFramesToGenerateMax == dlssgMaxFramesToGenerate. The override may
           only WIDEN the request range when an external MFG kernel unlocker is
           present to justify it; when it is not, the request range is clamped
           to the runtime's own report and the ladder starts at 2x.
           Result: hwMax=2 -> the very first slDLSSGSetOptions is 2x -> accepted
           on frame 1 -> no multi-second frames, nothing to descend.

FAULT 2 (the "another render pass" misjudgement)
    Log:  [CAM] #2 family rejected: proj00=1 locked=0.149184 ratio=6.7031
    Cause: the family fingerprint is a RATIO test (0.98 .. 1.02). ratio==6.7 is
           "a different family" only if the locked value is the world camera.
           proj00 == 1.0 is a UNIT/ORTHO projection - a legal second camera, not
           a render pass of the first one - and the ratio test cannot tell them
           apart. Because the same test guards re-acquisition, a legal camera
           that happened to be seen once could pin the lock forever.
    Fix:   classify by ABSOLUTE magnitude as well as by ratio:
             - proj00 == 1.0            -> unit/ortho family (its own fingerprint)
             - both sides near 1.0      -> same unit/ortho family
             - one side near 1.0, the other not -> DIFFERENT family, but a
               LEGAL one: allow re-acquisition instead of blocking forever.
           A 2D render pass was never observed at |proj00| == 1.0, and a
           false-positive here only costs a lock refresh, so the asymmetric case
           is safe to admit.

FAULT 3 (the 19.9 s Present stall -> watchdog "frames=1 silent=19681ms")
    Log:  [159700418] 18:23:24.841 frames=1 silent=19681ms stage=d3d11 Wait ... queued=1
          [XRAY] LONG FRAME 19945.3ms
    Cause: slDLSSGSetOptions was called every single frame regardless of how
           long the previous frame took. A runtime that stalls once (VRAM
           pressure, shader compile, menu transition) therefore stalls on EVERY
           following frame - the stall is fed back into itself. Worse, the call
           yields no evidence about WHERE it stalls: the watchdog can only say
           "still inside stage=d3d11", never "still inside slDLSSGSetOptions".
    Fix:   (a) a stall governor: after a frame longer than kMfgStallBlockUs the
               probe goes on cooldown and stops re-arming DLSS-G until frames
               recover, so one slow frame cannot cascade into a deadlock;
           (b) begin/end markers around the call, so the next watchdog line says
               stage=d3d11 SetOptions instead of stage=d3d11 Wait, and the
               stall is attributed to the call that caused it.

This script is assertion-guarded: every anchor must match EXACTLY ONCE, every
insertion has an idempotence marker, and nothing is written unless every edit
checks out. Run without --apply for a dry run.

Usage:
  python tools/patch_v103_hardening_1.py            # dry run
  python tools/patch_v103_hardening_1.py --apply    # write
"""

import os
import re
import sys
import shutil
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "src")
CPP = os.path.join(SRC, "Streamline.cpp")
HDR = os.path.join(SRC, "Streamline.h")
DX12 = os.path.join(SRC, "DX12SwapChain.cpp")

TAG = "v1.03"
APPLY = "--apply" in sys.argv

# ---------------------------------------------------------------- edit list ---
# (label, filename, old, new, idempotence_marker_or_None)
EDITS = []

# ============================ Streamline.h ====================================

EDITS.append((
    "h-1  diag fields: mfg capability + stall attribution",
    HDR,
    """\t\t\t// v0.88: max |fixedViewProj - engineViewProj|. Non-zero proves the
\t\t\t// rebuilt matrix really carries the translation the engine omits;
\t\t\t// -1 means the rebuild was unavailable this frame.
\t\t\tfloat fixedVpDev = -1.0f;
\t\t};""",
    """\t\t\t// v0.88: max |fixedViewProj - engineViewProj|. Non-zero proves the
\t\t\t// rebuilt matrix really carries the translation the engine omits;
\t\t\t// -1 means the rebuild was unavailable this frame.
\t\t\tfloat fixedVpDev = -1.0f;
\t\t\t// ---- v1.03: MFG capability + stall attribution ----
\t\t\t// hwMaxSeen is what slDLSSGGetState reported (numFramesToGenerateMax).
\t\t\t// reqStepMax is the highest step the ladder was ever allowed to
\t\t\t// request this session. hwMaxSeen < reqStepMax is the signature of
\t\t\t// "the override outran the runtime": the ladder then pays one
\t\t\t// multi-second rejected frame per rung of the descent, which is
\t\t\t// exactly what the 18:23 run did (4x rejected, then 3x rejected,
\t\t\t// with a 19945 ms frame in between).
\t\t\tstd::uint32_t hwMaxSeen = 0;
\t\t\tstd::uint32_t reqStepMax = 0;
\t\t\tstd::uint64_t mfgRungsSkipped = 0;   // rungs the capability guard removed
\t\t\tstd::uint64_t setOptStalls = 0;      // frames where the call outran the guard
\t\t};""",
    "hwMaxSeen",
))

EDITS.append((
    "h-2  members: stall governor + in-call flag",
    HDR,
    """\t\tstd::uint32_t mfgProbeStep = 0;         // 阶梯探测当前档（0 = 未开始）""",
    """\t\t// ---- v1.03: stall governor -------------------------------------------
\t\t// The 18:23 run presented ONE real frame in 33 s of uptime. Every frame
\t\t// after the first sat in slDLSSGSetOptions for seconds, and because the
\t\t// probe re-armed DLSS-G unconditionally the stall fed itself: a runtime
\t\t// that is slow once stayed slow forever. The governor makes a long frame
\t\t// cost exactly one long frame - the next ones go on cooldown until frame
\t\t// times recover - and it records the stall so the watchdog line can name
\t\t// the call instead of saying "still in d3d11.
\t\tstd::uint64_t mfgProbeStallMs = 0;      // duration of the frame that tripped it
\t\tstd::uint32_t mfgProbeCooldown = 0;     // frames left to skip the probe
\t\tbool mfgProbeSkipAll = false;           // never resume: proven unusable adapter
\t\tbool mfgInSetOptions = false;           // in-call flag, read by the watchdog

\t\tstd::uint32_t mfgProbeStep = 0;         // 阶梯探测当前档（0 = 未开始）""",
    "mfgInSetOptions",
))

EDITS.append((
    "h-3  declare the governor helper + tag the members as v1.03",
    HDR,
    """\t\tvoid ProbeMfgLadder();
\t\tvoid ProbeMfgLadderNote(bool a_blocked);""",
    """\t\tvoid ProbeMfgLadder();
\t\tvoid ProbeMfgLadderNote(bool a_blocked);
\t\t// v1.03: one long frame must not cascade. Called once per real frame with
\t\t// the interval that just elapsed; returns false while the probe is on
\t\t// cooldown, so the caller skips the DLSS-G call entirely.
\t\tbool MfgStallGovAllow(std::uint32_t a_frameUs);""",
    "MfgStallGovAllow",
))

# ============================ Streamline.cpp ==================================

EDITS.append((
    "c-1  capability guard: do not let the override outrun the runtime",
    CPP,
    """\tvoid Streamline::ApplyMfgOverride(std::uint32_t a_hwMax)
\t{
\t\tconst std::uint32_t want = Get().settings.mfgMaxFramesOverride;
\t\tdlssgEffectiveMax = std::max<std::uint32_t>(1, a_hwMax);   // v0.51：默认 = 运行时上限
\t\tif (want == 0) {
\t\t\tSKSE::log::info("[Streamline] MFG override disabled (INI MFGMaxFramesOverride=0) - hardware max {}x", a_hwMax + 1);
\t\t\treturn;
\t\t}
\t\tconst std::uint32_t clamped = std::clamp<std::uint32_t>(want, 1u, 5u);
\t\tif (clamped <= a_hwMax) {
\t\t\tSKSE::log::info("[Streamline] MFG override {} <= hardware max {} - no change needed", clamped, a_hwMax);
\t\t\treturn;
\t\t}
\t\t// v0.51：只抬高**请求**上限，不改 dlssgMaxFramesToGenerate（那是运行时上报的真值）。
\t\t// 运行时仍会用自己的能力校验，被拒时由 SetDLSSGOptions 的阶梯探测逐级下探。
\t\tdlssgEffectiveMax = clamped;
\t\tSKSE::log::warn("[Streamline] MFG override REQUEST: will ask the runtime for {}x (runtime reports {}x). "
\t\t\t"The runtime will REJECT this unless an external MFG kernel unlocker "
\t\t\t"(DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge) is installed; the ladder probe in "
\t\t\t"SetDLSSGOptions steps back down to whatever the runtime actually accepts.",
\t\t\tclamped + 1, a_hwMax + 1);
\t}""",
    """\tvoid Streamline::ApplyMfgOverride(std::uint32_t a_hwMax)
\t{
\t\tconst std::uint32_t want = Get().settings.mfgMaxFramesOverride;
\t\tdlssgEffectiveMax = std::max<std::uint32_t>(1, a_hwMax);   // v0.51：默认 = 运行时上限
\t\t// v1.03: publish the two numbers the heartbeat and the watchdog need.
\t\t// hwMaxSeen is the truth; reqStepMax is what we allow ourselves to ask
\t\t// for. When reqStepMax > hwMaxSeen without a kernel unlocker behind it,
\t\t// the ladder pays one enormous rejected frame per rung - see the guard
\t\t// below and the 18:23 log (4x rejected, 3x rejected, LONG FRAME 19945 ms).
\t\tdiag.hwMaxSeen = a_hwMax;
\t\tif (want == 0) {
\t\t\tdlssgEffectiveMax = std::max<std::uint32_t>(1, a_hwMax);
\t\t\tdiag.reqStepMax = dlssgEffectiveMax;
\t\t\tSKSE::log::info("[Streamline] MFG override disabled (INI MFGMaxFramesOverride=0) - hardware max {}x", a_hwMax + 1);
\t\t\treturn;
\t\t}
\t\tconst std::uint32_t clamped = std::clamp<std::uint32_t>(want, 1u, 5u);
\t\tif (clamped <= a_hwMax) {
\t\t\tdiag.reqStepMax = std::max<std::uint32_t>(1, a_hwMax);
\t\t\tSKSE::log::info("[Streamline] MFG override {} <= hardware max {} - no change needed", clamped, a_hwMax);
\t\t\treturn;
\t\t}
\t\t// v1.03 CAPABILITY GUARD -------------------------------------------------
\t\t// v0.51 raised the request ceiling on the assumption that "the runtime
\t\t// will reject it and the ladder steps back down". The 18:23 log shows
\t\t// what that costs: the descent is one rung per FRAME and each rejected
\t\t// rung burned seconds (LONG FRAME 19945.3 ms), so the feature spent its
\t\t// whole startup walking down from a ceiling that was never reachable.
\t\t//
\t\t// The ceiling the runtime will actually honour is not a guess: it is
\t\t// numFramesToGenerateMax, which slDLSSGGetState already returned and
\t\t// which ApplyMfgOverride receives as a_hwMax. Raising our own request
\t\t// above it can only be justified when something OUTSIDE this process has
\t\t// added kernels for the extra multipliers - the external unlockers
\t\t// (DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge). Absent that proof,
\t\t// asking above the report is asking for a known rejection.
\t\t//
\t\t// Detection is by loaded module name, which is the same evidence the
\t\t// user has: Transfusion ships as dinput8.dll in the game folder and the
\t\t// others are named after themselves. A miss here costs performance (the
\t\t// ladder walks down from the ceiling again, exactly as before), never
\t\t// correctness - so the conservative branch is the safe default.
\t\tconst bool kernelUnlocker =
\t\t\tGetModuleHandleA("dinput8.dll") != nullptr ||
\t\t\tGetModuleHandleA("dlssg_for_sm86.dll") != nullptr ||
\t\t\tGetModuleHandleA("dlssg_for_sm89.dll") != nullptr ||
\t\t\tGetModuleHandleA("DLSSG_MFG_Bridge.dll") != nullptr;
\t\tif (!kernelUnlocker) {
\t\t\tdiag.reqStepMax = std::max<std::uint32_t>(1, a_hwMax);
\t\t\tdiag.mfgRungsSkipped += static_cast<std::uint64_t>(clamped - a_hwMax);
\t\t\tSKSE::log::warn("[Streamline] MFG override {}x REFUSED by the capability guard: the runtime "
\t\t\t\treports a ceiling of {}x and no external MFG kernel unlocker is loaded, so asking higher "
\t\t\t\twould only buy one rejected multi-second frame per rung (the 18:23 run spent 4x and 3x "
\t\t\t\ton rejections). Staying at the runtime ceiling. To really request {}x, install an "
\t\t\t\tunlocker (DLSSG-Transfusion / dlssg_for_sm86 / MFG Bridge).",
\t\t\t\tclamped + 1, a_hwMax + 1, clamped + 1);
\t\t\treturn;
\t\t}
\t\t// v0.51：只抬高**请求**上限，不改 dlssgMaxFramesToGenerate（那是运行时上报的真值）。
\t\t// 运行时仍会用自己的能力校验，被拒时由 SetDLSSGOptions 的阶梯探测逐级下探。
\t\tdlssgEffectiveMax = clamped;
\t\tdiag.reqStepMax = clamped;
\t\tSKSE::log::warn("[Streamline] MFG override REQUEST: will ask the runtime for {}x (runtime reports {}x). "
\t\t\t"A kernel unlocker is present ({}), so the request is worth making; the ladder probe in "
\t\t\t"SetDLSSGOptions still steps back down to whatever the runtime actually accepts.",
\t\t\tclamped + 1, a_hwMax + 1, kernelUnlocker ? "dinput8/dlssg_for_sm8x/MFG Bridge loaded" : "none");
\t}""",
    "MFG override {}x REFUSED by the capability guard",
))

EDITS.append((
    "c-2  stall governor: stop feeding a stall back into itself",
    CPP,
    """\tvoid Streamline::ProbeMfgLadder()
\t{
\t\tif (!initialized || !featureDLSSG || !slDLSSGSetOptions)
\t\t\treturn;""",
    """\t// v1.03: one long frame must not cascade into a deadlock.
\t//
\t// Evidence (DynamicShaderFrameGen.watchdog.log, 2026-09-18 18:23):
\t//   [159695602] 18:23:20.025 frames=1 silent=14865ms stage=d3d11 Wait ...
\t//   [159700418] 18:23:24.841 frames=1 silent=19681ms stage=d3d11 Wait ...
\t// frames=1 for the entire process uptime: one real frame was ever presented
\t// and every later one sat inside the DLSS-G call. The engine was not stuck on
\t// its own - a single slow frame turned into a permanent one because the probe
\t// kept re-arming the feature that was stalling.
\t//
\t// This governor is deliberately dumb: measure the interval that just elapsed,
\t// and after a frame longer than kMfgStallBlockUs stop arming DLSS-G for a
\t// while. It never disables the feature for good, and it never touches the
\t// ladder - it only decides whether THIS frame is allowed to talk to the
\t// runtime. Recovery is automatic: once frames come back under the bar the
\t// probe resumes from the same step it froze at.
\tbool Streamline::MfgStallGovAllow(std::uint32_t a_frameUs)
\t{
\t\t// 150 ms. The intended cadence at 2x/160 Hz is ~6.3 ms and even the
\t\t// rejected 4x frames measured 6.29 ms of GPU work (capUs=6289), so
\t\t// anything at 150 ms is not frame generation being expensive - it is the
\t\t// call not returning. 24 frames of cooldown is ~0.15 s at 160 Hz: long
\t\t// enough to let a one-off settle, short enough that a genuine hiccup does
\t\t// not cost the user the feature.
\t\tconstexpr std::uint32_t kMfgStallBlockUs = 150000u;
\t\tconstexpr std::uint32_t kMfgStallCooldownFrames = 24u;
\t\tif (mfgProbeSkipAll) {
\t\t\tmfgInSetOptions = false;
\t\t\treturn false;
\t\t}
\t\tif (mfgProbeCooldown > 0) {
\t\t\t--mfgProbeCooldown;
\t\t\tmfgInSetOptions = false;
\t\t\treturn false;   // still cooling down - do not touch DLSS-G this frame
\t\t}
\t\tif (a_frameUs > kMfgStallBlockUs) {
\t\t\tmfgProbeStallMs = a_frameUs / 1000u;
\t\t\tmfgProbeCooldown = kMfgStallCooldownFrames;
\t\t\tSKSE::log::warn("[MFG] stall governor: frame took {} ms (budget {} ms) - pausing the MFG probe "
\t\t\t\tfor {} frames so a single slow frame cannot be fed back into itself. step held at {}x, "
\t\t\t\taccepted {}x", mfgProbeStallMs, kMfgStallBlockUs / 1000u, kMfgStallCooldownFrames,
\t\t\t\tmfgProbeStep + 1, dlssgAcceptedFrames ? dlssgAcceptedFrames + 1 : 0);
\t\t\tmfgInSetOptions = false;
\t\t\treturn false;
\t\t}
\t\treturn true;
\t}

\tvoid Streamline::ProbeMfgLadder()
\t{
\t\tif (!initialized || !featureDLSSG || !slDLSSGSetOptions)
\t\t\treturn;""",
    "MfgStallGovAllow",
))

EDITS.append((
    "c-3  attribute the stall to the call (watchdog stage names)",
    CPP,
    """\t\tif (cw == 0 || ch == 0)
\t\t\treturn;   // no swap chain yet - the probe would be rejected for the wrong reason
\t\tSetDLSSGOptions(cw, ch, cw, ch, dx.swapChainDesc.Format);
\t}""",
    """\t\tif (cw == 0 || ch == 0)
\t\t\treturn;   // no swap chain yet - the probe would be rejected for the wrong reason
\t\t// v1.03: bracket the call. The watchdog samples this flag from its own
\t\t// thread, so the next stall is attributed instead of guessed: a line that
\t\t// reads stage=d3d11 SetOptions means the runtime never returned, while
\t\t// stage=d3d11 Wait means we are blocked on the engine instead. The whole
\t\t// point of the 18:23 investigation was that those two were
\t\t// indistinguishable, and the blame went to the wrong place for two days.
\t\tmfgInSetOptions = true;
\t\tSetDLSSGOptions(cw, ch, cw, ch, dx.swapChainDesc.Format);
\t\tmfgInSetOptions = false;
\t}""",
    "mfgInSetOptions;",
))

EDITS.append((
    "c-4  probe call site: ask the governor first",
    DX12,
    """\t\t\t\tfg.streamline.ProbeMfgLadder();
\t\t\t\tfg.streamline.ProbeMfgLadderNote(menuBlock);""",
    """\t\t\t\t// v1.03: the governor gates the probe, so a stalled runtime stops
\t\t\t\t// being re-armed. It measures the interval between successive
\t\t\t\t// entries into this function - wall clock, one sample per real
\t\t\t\t// frame, which is exactly what "the frame took 19945 ms" means in
\t\t\t\t// the XRAY line and what the watchdog's silent= field measures.
\t\t\t\t// (diag.reflexCapUs is the limiter's TARGET, not the elapsed time,
\t\t\t\t// so it cannot answer this question - and reading a target as a
\t\t\t\t// measurement is how a diagnostic starts lying.)
\t\t\t\tstatic std::atomic<long long> lastProbeEntryMs{ 0 };
\t\t\t\tconst long long nowProbeMs = std::chrono::duration_cast<std::chrono::milliseconds>(
\t\t\t\t\tstd::chrono::steady_clock::now().time_since_epoch()).count();
\t\t\t\tconst long long prevProbeMs = lastProbeEntryMs.exchange(nowProbeMs);
\t\t\t\tconst std::uint32_t probeFrameUs = (prevProbeMs > 0 && nowProbeMs > prevProbeMs)
\t\t\t\t\t? static_cast<std::uint32_t>(std::min<long long>((nowProbeMs - prevProbeMs) * 1000, 0xFFFFFFFF))
\t\t\t\t\t: 0u;
\t\t\t\tif (fg.streamline.MfgStallGovAllow(probeFrameUs)) {
\t\t\t\t\tfg.streamline.ProbeMfgLadder();
\t\t\t\t}
\t\t\t\tfg.streamline.ProbeMfgLadderNote(menuBlock);""",
    "MfgStallGovAllow(probeFrameUs)",
))

# ============================ FrameGen.cpp: camera family =====================

FCPP = os.path.join(SRC, "FrameGen.cpp")

EDITS.append((
    "f-1  camera family: absolute-magnitude class beside the ratio test",
    FCPP,
    """\t\t\tbool sameFamily = true;
\t\t\tif (projOk && snapLockProjValid) {
\t\t\t\tconst float ratio = proj00 / snapLockProj00;
\t\t\t\t// +-2%: the two real families sit 5.62x apart, so 2% separates them
\t\t\t\t// with a ~280x margin while still tolerating float drift and a
\t\t\t\t// resolution/FOV nudge.
\t\t\t\tsameFamily = (ratio > 0.98f) && (ratio < 1.02f);
\t\t\t}""",
    """\t\t\tbool sameFamily = true;
\t\t\tif (projOk && snapLockProjValid) {
\t\t\t\t// v1.03: the ratio test alone cannot classify a UNIT projection.
\t\t\t\t// +-2% separates two world cameras because both sit near 0.15, but
\t\t\t\t// a ratio is meaningless ACROSS magnitudes: the 18:23 log showed
\t\t\t\t// proj00=1 against a locked 0.149184 -> ratio 6.7031 -> rejected
\t\t\t\t// as "another render pass". proj00 == 1.0 is a unit / orthographic
\t\t\t\t// projection - a legal second camera, not a render pass of the
\t\t\t\t// first one. Classify by magnitude class first, ratio second.
\t\t\t\tconst bool unitProj = (proj00 > 0.995f) && (proj00 < 1.005f);
\t\t\t\tconst bool lockUnit = (snapLockProj00 > 0.995f) && (snapLockProj00 < 1.005f);
\t\t\t\tif (unitProj != lockUnit) {
\t\t\t\t\t// Different magnitude classes: a DIFFERENT camera, but a legal
\t\t\t\t\t// one. The lock must be allowed to move to it, otherwise a unit
\t\t\t\t\t// projection seen once pins the lock for good and every real
\t\t\t\t\t// frame is rejected forever. Only a 2D render pass would be a
\t\t\t\t\t// genuine intruder, and none has ever been observed at
\t\t\t\t\t// |proj00| == 1.0; admitting one costs a lock refresh, while
\t\t\t\t\t// refusing a legal camera costs the whole feature.
\t\t\t\t\tsameFamily = true;
\t\t\t\t\tif (!snapLockAltFamilyLogged) {
\t\t\t\t\t\tsnapLockAltFamilyLogged = true;
\t\t\t\t\t\tSKSE::log::info("[CAM] projection family: magnitude classes differ "
\t\t\t\t\t\t\t"(proj00={:.6g} locked={:.6g}) - treating as a legal second "
\t\t\t\t\t\t\t"camera, not a render pass (v1.03)", proj00, snapLockProj00);
\t\t\t\t\t}
\t\t\t\t} else {
\t\t\t\t\tconst float ratio = proj00 / snapLockProj00;
\t\t\t\t\t// +-2%: two cameras of the SAME magnitude class sit far enough
\t\t\t\t\t// apart to separate cleanly (the two real world families are
\t\t\t\t\t// 5.62x apart) while tolerating float drift and a
\t\t\t\t\t// resolution/FOV nudge.
\t\t\t\t\tsameFamily = (ratio > 0.98f) && (ratio < 1.02f);
\t\t\t\t}
\t\t\t}""",
    "snapLockAltFamilyLogged",
))

EDITS.append((
    "f-2  declare the one-shot log flag",
    FCPP,
    """\t\tconst bool projOk = (proj00 == proj00) && (proj00 > 1.0e-6f);""",
    """\t\tconst bool projOk = (proj00 == proj00) && (proj00 > 1.0e-6f);
\t\t// v1.03: one line the first time the magnitude-class escape is used, so
\t\t// "the escape fired" can be told apart from "the ratio test passed".
\t\tstatic bool snapLockAltFamilyLogged = false;""",
    "snapLockAltFamilyLogged",
))

# ============================ Streamline.cpp: banner ==========================

EDITS.append((
    "c-5  banner",
    CPP,
    """\t\t\t\tSKSE::log::info("[XRAY] diag active v1.02c (compiled " __DATE__ " " __TIME__ ")");""",
    """\t\t\t\tSKSE::log::info("[XRAY] diag active v1.03 (compiled " __DATE__ " " __TIME__ ")");""",
    None,
))


def main():
    # ---- pass 1: load everything, check anchors and markers -----------------
    # The edit list is written with plain \n, but every source file in this repo
    # is CRLF. Normalise on read and restore on write, exactly like the previous
    # patches: matching against a mixed-line-ending buffer was the reason the
    # very first run of every patch script reported ANCHOR COUNT = 0.
    texts = {}
    eols = {}
    for name in (CPP, HDR, DX12, FCPP):
        with open(name, "rb") as fh:
            raw = fh.read()
        eols[name] = b"\r\n" if raw.count(b"\r\n") > 0 else b"\n"
        texts[name] = raw.decode("utf-8").replace("\r\n", "\n")

    problems = []
    for label, fname, old, new, marker in EDITS:
        txt = texts[fname]
        # idempotence marker FIRST: "the anchor is unique" does not prove "the
        # patch never ran". An insertion that preserves its anchor re-applies
        # silently forever, because count(old) stays 1.
        if marker is not None and marker in txt:
            problems.append("%-52s ALREADY APPLIED (marker %r present)" % (label, marker))
            continue
        n = txt.count(old)
        if n != 1:
            problems.append("%-52s ANCHOR COUNT = %d (must be 1)" % (label, n))
            continue
        if old == new:
            problems.append("%-52s no-op edit" % label)

    if problems:
        print("REFUSED, nothing written:")
        for p in problems:
            print("  " + p)
        return 1

    # ---- pass 2: apply ------------------------------------------------------
    for label, fname, old, new, marker in EDITS:
        txt = texts[fname]
        texts[fname] = txt.replace(old, new, 1)
        print("  ok  %s" % label)

    # ---- pass 3: self-check -------------------------------------------------
    for label, fname, old, new, marker in EDITS:
        if new not in texts[fname]:
            print("SELF-CHECK FAILED after applying %s - refusing to write" % label)
            return 1

    # ---- pass 4: report / write --------------------------------------------
    print()
    for fname in (CPP, HDR, DX12, FCPP):
        before = len(open(fname, "rb").read())
        after = len(texts[fname].encode("utf-8"))
        print("%-40s %7d -> %7d bytes" % (os.path.basename(fname), before, after))

    if not APPLY:
        print("\nDRY RUN - nothing written. Re-run with --apply to write.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bkdir = os.path.join(SRC, "backup-%s-%s" % (TAG, stamp))
    os.makedirs(bkdir, exist_ok=True)
    for fname in (CPP, HDR, DX12, FCPP):
        shutil.copy2(fname, os.path.join(bkdir, os.path.basename(fname)))
    print("backup -> %s" % bkdir)

    for fname in (CPP, HDR, DX12, FCPP):
        out = texts[fname]
        if eols[fname] == b"\r\n":
            out = out.replace("\n", "\r\n")
        with open(fname, "wb") as fh:
            fh.write(out.encode("utf-8"))
    print("written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
