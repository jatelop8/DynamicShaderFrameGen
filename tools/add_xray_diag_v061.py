#!/usr/bin/env python3
"""v0.61 - [XRAY] self-diagnosis instrumentation for DynamicShaderFrameGen.

Why this exists
---------------
The flicker hunt of 2026-09-17 was slowed down by *log correlation*, not by
missing hypotheses. Four probes (MOTION / CAM / RESET / constants) each fired on
their own cadence, and the answers to "which file did the game read", "is the
process DPI-virtualized" and "what was true at the moment it flickered" were
either absent or spread across the log. This patch makes one run conclusive:

  [XRAY] RUN START ... dll=<path> mtime=...   which DLL is actually loaded
  [XRAY] INI: cwd=... file=... size=...B      which ini actually won
  [XRAY] env: virtual=.. physical=.. swapchain=..   DPI / mode alignment
  [XRAY] MENU EDGE open=.. presentedBefore=..       menu transitions
  [XRAY] serial=.. menu=.. world=.. consts ok/fail  ONE heartbeat, all numbers
  [XRAY] VERDICT: ...                              the log states the conclusion

Instrumentation only. The single behaviour-affecting line is unchanged from
v0.59/v0.60 (edge-triggered reset, fullscreen-menu flag).

Safety
------
* Every anchor must match EXACTLY once (count == 1).  0 = stale anchor,
  >1 = ambiguous anchor.  Any failure => REFUSED, nothing written.
* Idempotence marker checked FIRST (v0.59 lesson: "anchor unique" does not
  prove "patch has not already run").
* Per-file EOL is preserved (Streamline.h/main.cpp are CRLF, Streamline.cpp /
  FrameGen.cpp are LF) so the diff stays reviewable.
* Backups + read-back verification after writing.
* Dry run by default; pass --apply to write.
"""

import os
import re
import shutil
import sys
import datetime

ROOT = r"D:\Modding\DynamicShaderFrameGen"
SRC = os.path.join(ROOT, "src")
BAK_ROOT = r"D:\workbuddy2\backup"

MARKER = "[XRAY] diag active v0.61"
MARKER_PATH = os.path.join(SRC, "Streamline.cpp")

H = os.path.join(SRC, "Streamline.h")
C = os.path.join(SRC, "Streamline.cpp")
M = os.path.join(SRC, "main.cpp")
G = os.path.join(SRC, "FrameGen.cpp")

EDITS = []
EDITS_NEW = {}


def pair(path, label, old, new):
    EDITS.append((label, path, "pair", old, new))


def span(path, label, head, tail_marker, tail_suffix, new):
    # The replacement body is keyed by label rather than stored in the tuple so
    # that every record keeps the same 5-field shape as `pair` records.
    EDITS_NEW[label] = new
    EDITS.append((label, path, "span", head, (tail_marker, tail_suffix)))


# ---------------------------------------------------------------- Streamline.h
pair(H, "H1 Diag struct + member", """\t\tstd::uint32_t frameSerial = 0;
\t\tHMODULE interposer = nullptr;
""", """\t\t// v0.61: one-run self-diagnosis. Every counter needed to decide WHERE a
\t\t// remaining flicker comes from is accumulated here and printed as a single
\t\t// [XRAY] heartbeat line, so one launch produces a conclusive log instead of
\t\t// a stack of probes running on four different cadences that cannot be
\t\t// correlated with each other.
\t\tstruct Diag
\t\t{
\t\t\tstd::uint64_t menuFrames = 0;    // real frames with a game menu open
\t\t\tstd::uint64_t worldFrames = 0;
\t\t\tstd::uint64_t menuEdges = 0;     // menu open/close transitions
\t\t\tstd::uint64_t resetTrue = 0;     // frames where reset was eTrue
\t\t\tstd::uint64_t constsOk = 0;
\t\t\tstd::uint64_t constsFail = 0;
\t\t\tstd::int32_t constsLastR = 0;
\t\t\t// presented-per-real-frame histogram (what slDLSSGGetState reported),
\t\t\t// split by menu/world; index = value, clamped to 7. This is the direct
\t\t\t// evidence for "did eEnableFullscreenMenuDetection do anything": if the
\t\t\t// runtime honours it, presentedMenu collapses to 1 while presentedWorld
\t\t\t// holds at the accepted multiplier.
\t\t\tstd::uint64_t presentedAll[8] = {};
\t\t\tstd::uint64_t presentedMenu[8] = {};
\t\t\tstd::uint64_t presentedWorld[8] = {};
\t\t\tstd::uint32_t presentedPrev = 0;
\t\t\tstd::uint32_t lastFlags = 0;
\t\t\tstd::uint32_t lastCountedSerial = 0xFFFFFFFFu;
\t\t\tbool menuOpenNow = false;
\t\t};
\t\tDiag diag;

\t\tstd::uint32_t frameSerial = 0;
\t\tHMODULE interposer = nullptr;
""")

# ---------------------------------------------------------------- Streamline.cpp
pair(C, "C0 shared menu helper", """\tvoid Streamline::CheckFrameConstants(const FrameBuffer& a_fb, float a_aspect, float a_near, float a_far)
\t{
\t\tif (!initialized)
""", """\tnamespace
\t{
\t\t// v0.61: single definition of "a game menu is up". CheckFrameConstants uses
\t\t// it for the reset edge AND for the menu/world counters, so the two can
\t\t// never disagree. Same menu set v0.34 established: the menus the engine
\t\t// draws without valid motion vectors.
\t\tbool GameMenuOpenNow()
\t\t{
\t\t\tauto* ui = RE::UI::GetSingleton();
\t\t\tif (!ui)
\t\t\t\treturn false;
\t\t\tconst auto* istrings = RE::InterfaceStrings::GetSingleton();
\t\t\tif (!istrings)
\t\t\t\treturn false;
\t\t\treturn ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||
\t\t\t\tui->IsMenuOpen(istrings->journalMenu) || ui->IsMenuOpen("PauseMenu");
\t\t}
\t}

\tvoid Streamline::CheckFrameConstants(const FrameBuffer& a_fb, float a_aspect, float a_near, float a_far)
\t{
\t\tif (!initialized)
""")

# MOTION / CAM probes folded into the XRAY heartbeat
span(C, "C1 fold MOTION/CAM probes", """\t\t{
\t\t\tstatic std::uint32_t motionProbe = 0;
""", "\t\t\t\t\ta_fb.CameraPreviousPosAdjust[2]);", """\n\t\t\t}\n\t\t}\n""",
     """\t\t// v0.61: the MOTION / CAM probes that used to live here were folded into the
\t\t// single [XRAY] heartbeat further down (after the menu/reset decision), so
\t\t// every number that decides "where does the flicker come from" lands on ONE
\t\t// line together with the menu state and the constants accounting.
""")

pair(C, "C2 reset edge + menu counters", """\t\tbool isMenuOpen = false;
\t\tif (auto* ui = RE::UI::GetSingleton()) {
\t\t\tconst auto* istrings = RE::InterfaceStrings::GetSingleton();
\t\t\tisMenuOpen = ui->IsMenuOpen(istrings->mainMenu) || ui->IsMenuOpen(istrings->loadingMenu) ||
\t\t\t\tui->IsMenuOpen(istrings->journalMenu) || ui->IsMenuOpen("PauseMenu");
\t\t}
\t\tstatic bool s_wasMenuOpen = false;
\t\tc.reset = (isMenuOpen && !s_wasMenuOpen) ? sl::Boolean::eTrue : sl::Boolean::eFalse;
\t\ts_wasMenuOpen = isMenuOpen;
\t\t{
\t\t\tstatic std::uint32_t resetProbe = 0;
\t\t\tif (++resetProbe % 240 == 1)
\t\t\t\tSKSE::log::info("[Streamline] RESET probe: menuOpen={} reset={} (edge-triggered, v0.59)",
\t\t\t\t\tisMenuOpen, static_cast<int>(c.reset));
\t\t}
""", """\t\tconst bool isMenuOpen = GameMenuOpenNow();
\t\tstatic bool s_wasMenuOpen = false;
\t\tconst bool menuEdgeUp = isMenuOpen && !s_wasMenuOpen;
\t\tconst bool menuEdgeDown = !isMenuOpen && s_wasMenuOpen;
\t\tc.reset = menuEdgeUp ? sl::Boolean::eTrue : sl::Boolean::eFalse;
\t\ts_wasMenuOpen = isMenuOpen;
\t\tdiag.menuOpenNow = isMenuOpen;
\t\tif (c.reset == sl::Boolean::eTrue)
\t\t\t++diag.resetTrue;
\t\t// Count each real frame exactly once for the menu/world split. Guarded by
\t\t// frameSerial so a second call inside the same frame cannot double-count.
\t\tif (frameSerial != diag.lastCountedSerial) {
\t\t\tdiag.lastCountedSerial = frameSerial;
\t\t\tif (isMenuOpen)
\t\t\t\t++diag.menuFrames;
\t\t\telse
\t\t\t\t++diag.worldFrames;
\t\t}
\t\tif (menuEdgeUp || menuEdgeDown) {
\t\t\t++diag.menuEdges;
\t\t\t// Logged at the moment of the transition, with the multiplier that was in
\t\t\t// effect just before it - that pair is what tells whether the menu
\t\t\t// handling actually engages.
\t\t\tSKSE::log::info("[XRAY] MENU EDGE open={} serial={} presentedBefore={} reset={} consts(ok={} fail={})",
\t\t\t\tisMenuOpen ? 1 : 0, frameSerial, diag.presentedPrev,
\t\t\t\tstatic_cast<int>(c.reset), diag.constsOk, diag.constsFail);
\t\t}

\t\t// ===== [XRAY] heartbeat (v0.61) =====
\t\t// One line every 240 real frames carrying every number that decides where a
\t\t// remaining flicker comes from, all sampled in the SAME frame and next to the
\t\t// menu state and the constants accounting. It replaces the four separate
\t\t// probes (MOTION / CAM / RESET / constants) that fired on four different
\t\t// cadences, which made "which combination was true when it flickered"
\t\t// unanswerable from the log.
\t\t{
\t\t\tstatic std::uint32_t xrayTick = 0;
\t\t\tif (++xrayTick % 240 == 1) {
\t\t\t\tauto devOf = [](const Matrix& m) {
\t\t\t\t\tfloat d = 0.0f;
\t\t\t\t\tfor (int r = 0; r < 4; ++r)
\t\t\t\t\t\tfor (int cc = 0; cc < 4; ++cc) {
\t\t\t\t\t\t\tconst float id = (r == cc) ? 1.0f : 0.0f;
\t\t\t\t\t\t\tfloat v = m.data[r][cc] - id;
\t\t\t\t\t\t\tif (v < 0.0f) v = -v;
\t\t\t\t\t\t\tif (v > d) d = v;
\t\t\t\t\t\t}
\t\t\t\t\treturn d;
\t\t\t\t};
\t\t\t\t// max |clipToPrevClip - I|: DLSS-G reprojects every generated frame with
\t\t\t\t// this matrix, so ~0 while the player is moving means the camera term of
\t\t\t\t// the reprojection is silently dropped.
\t\t\t\tfloat clipDev = 0.0f;
\t\t\t\tfor (int row = 0; row < 4; ++row) {
\t\t\t\t\tconst sl::float4 r4 = c.clipToPrevClip[row];
\t\t\t\t\tconst float v4[4] = { r4.x, r4.y, r4.z, r4.w };
\t\t\t\t\tfor (int col = 0; col < 4; ++col) {
\t\t\t\t\t\tconst float id = (row == col) ? 1.0f : 0.0f;
\t\t\t\t\t\tfloat d = v4[col] - id;
\t\t\t\t\t\tif (d < 0.0f) d = -d;
\t\t\t\t\t\tif (d > clipDev) clipDev = d;
\t\t\t\t\t}
\t\t\t\t}
\t\t\t\tauto hist = [](const std::uint64_t (&h)[8]) {
\t\t\t\t\tstd::string s;
\t\t\t\t\tfor (int i = 0; i < 8; ++i) {
\t\t\t\t\t\tif (i) s += '/';
\t\t\t\t\t\ts += std::to_string(h[i]);
\t\t\t\t\t}
\t\t\t\t\treturn s;
\t\t\t\t};
\t\t\t\tauto modeOf = [](const std::uint64_t (&h)[8]) {
\t\t\t\t\tstd::uint32_t best = 0;
\t\t\t\t\tfor (std::uint32_t i = 0; i < 8; ++i)
\t\t\t\t\t\tif (h[i] > h[best]) best = i;
\t\t\t\t\treturn best;
\t\t\t\t};
\t\t\t\tSKSE::log::info("[XRAY] serial={} menu={} world={} edges={} resetTrue={} menuOpen={} reset={} | "
\t\t\t\t\t"consts ok={} fail={} lastR={} | presented all={} world={} menu={} | "
\t\t\t\t\t"mvec=({:.3f},{:.3f}) flags={:#x} | jitter=({:.4f},{:.4f}) clipDev={:.6f} "
\t\t\t\t\t"curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) prevPos=({:.1f},{:.1f},{:.1f})",
\t\t\t\t\tframeSerial, diag.menuFrames, diag.worldFrames, diag.menuEdges, diag.resetTrue,
\t\t\t\t\tisMenuOpen ? 1 : 0, static_cast<int>(c.reset),
\t\t\t\t\tdiag.constsOk, diag.constsFail, diag.constsLastR,
\t\t\t\t\thist(diag.presentedAll), hist(diag.presentedWorld), hist(diag.presentedMenu),
\t\t\t\t\tc.mvecScale.x, c.mvecScale.y, diag.lastFlags,
\t\t\t\t\tGet().jitterX, Get().jitterY, clipDev, devOf(curVP), devOf(prevVP),
\t\t\t\t\ta_fb.CameraPosAdjust[0], a_fb.CameraPosAdjust[1], a_fb.CameraPosAdjust[2],
\t\t\t\t\ta_fb.CameraPreviousPosAdjust[0], a_fb.CameraPreviousPosAdjust[1],
\t\t\t\t\ta_fb.CameraPreviousPosAdjust[2]);

\t\t\t\t// Self-derived verdict: the log states the conclusion instead of leaving
\t\t\t\t// the reader to combine four numbers by hand.
\t\t\t\tconst std::uint32_t want = std::max<std::uint32_t>(1u, dlssgAcceptedFrames);
\t\t\t\tconst std::uint32_t wm = modeOf(diag.presentedWorld);
\t\t\t\tconst std::uint32_t mm = modeOf(diag.presentedMenu);
\t\t\t\tstd::string vd;
\t\t\t\tif (diag.constsFail != 0)
\t\t\t\t\tvd = "PROBLEM constants rejected (fail=" + std::to_string(diag.constsFail) +
\t\t\t\t\t     ", lastR=" + std::to_string(diag.constsLastR) +
\t\t\t\t\t     ") -> frame slot not advancing, per-frame data stays stale";
\t\t\t\telse if (want <= 1u)
\t\t\t\t\tvd = "PROBLEM runtime accepted no interpolation (accepted=0) -> no DLSS-G kernel in effect";
\t\t\t\telse if (diag.menuFrames > 60 && mm >= want)
\t\t\t\t\tvd = "PROBLEM menu still generates " + std::to_string(mm) +
\t\t\t\t\t     " frames/real frame -> eEnableFullscreenMenuDetection NOT honoured";
\t\t\t\telse if (diag.worldFrames > 60 && wm != want)
\t\t\t\t\tvd = "PROBLEM world ran at " + std::to_string(wm) + " frames/real frame but " +
\t\t\t\t\t     std::to_string(want) + " was accepted";
\t\t\t\telse if (diag.menuFrames <= 60)
\t\t\t\t\tvd = "inconclusive: menu never sampled for long enough (need >60 menu frames)";
\t\t\t\telse
\t\t\t\t\tvd = "clean: constants ok, menu throttled, world at the accepted rate";
\t\t\t\tSKSE::log::info("[XRAY] VERDICT: {}", vd);
\t\t\t}
\t\t}
""")

pair(C, "C3 constants counters into diag", """\t\tstatic std::uint32_t constsOk = 0, constsFail = 0;
\t\tstatic int constsLastR = 0;
\t\tif (SL_FAILED(r, slSetConstants(c, *frameToken, viewport))) {
\t\t\t++constsFail;
\t\t\tconstsLastR = (int)r;
\t\t} else {
\t\t\t++constsOk;
\t\t}
\t\tif (((constsOk + constsFail) % 120) == 0)
\t\t\tSKSE::log::info("[Streamline] constants: ok={} fail={} lastR={} serial={} token={:p}",
\t\t\t\tconstsOk, constsFail, constsLastR, frameSerial,
\t\t\t\tstatic_cast<const void*>(frameToken));
""", """\t\tif (SL_FAILED(r, slSetConstants(c, *frameToken, viewport))) {
\t\t\t++diag.constsFail;
\t\t\tdiag.constsLastR = static_cast<std::int32_t>(r);
\t\t\t// v0.61: only the first rejection gets its own line. A rejected call used
\t\t\t// to print on every frame and drown the log; the running totals - and in
\t\t\t// particular whether they keep climbing - live in the [XRAY] heartbeat.
\t\t\tif (diag.constsFail == 1)
\t\t\t\tSKSE::log::warn("[Streamline] slSetConstants FAILED first time: r={} "
\t\t\t\t\t"(27 = eErrorDuplicatedConstants => frame slot not advancing); totals in [XRAY]",
\t\t\t\t\tstatic_cast<std::int32_t>(r));
\t\t} else {
\t\t\t++diag.constsOk;
\t\t}
""")

pair(C, "C4 flags + env banner", """\t\topts.flags |= sl::DLSSGFlags::eEnableFullscreenMenuDetection;
\t\t{
\t\t\tstatic bool menuFlagLogged = false;
\t\t\tif (!menuFlagLogged) {
\t\t\t\tmenuFlagLogged = true;
\t\t\t\tSKSE::log::info("[Streamline] DLSSG flags: fullscreenMenuDetection=on (v0.60)");
\t\t\t}
\t\t}
""", """\t\topts.flags |= sl::DLSSGFlags::eEnableFullscreenMenuDetection;
\t\tdiag.lastFlags = static_cast<std::uint32_t>(opts.flags);
\t\t{
\t\t\tstatic bool menuFlagLogged = false;
\t\t\tif (!menuFlagLogged) {
\t\t\t\tmenuFlagLogged = true;
\t\t\t\tSKSE::log::info("[Streamline] DLSSG flags: fullscreenMenuDetection=on (v0.60) raw={:#x}",
\t\t\t\t\tdiag.lastFlags);
\t\t\t\t// v0.61 environment banner - the single line that would have saved a
\t\t\t\t// whole debug round on 2026-09-17. `virtual` is what THIS process sees
\t\t\t\t// through Windows DPI virtualization, `physical` is the real display
\t\t\t\t// mode, `swapchain` is what DXGI actually got. A swapchain that does not
\t\t\t\t// match the display mode breaks Independent Flip and the pacer; and
\t\t\t\t// virtual != physical means every window rect and system metric the
\t\t\t\t// plugin reads is scaled - which is what made "window 2560x1440" look
\t\t\t\t// like a 1440p window on a 4K screen when it was in fact fullscreen.
\t\t\t\tconst int vw = ::GetSystemMetrics(SM_CXSCREEN);
\t\t\t\tconst int vh = ::GetSystemMetrics(SM_CYSCREEN);
\t\t\t\tDEVMODEA dm{};
\t\t\t\tdm.dmSize = sizeof(dm);
\t\t\t\tint pw = 0, ph = 0, hz = 0;
\t\t\t\tif (::EnumDisplaySettingsA(nullptr, ENUM_CURRENT_SETTINGS, &dm)) {
\t\t\t\t\tpw = static_cast<int>(dm.dmPelsWidth);
\t\t\t\t\tph = static_cast<int>(dm.dmPelsHeight);
\t\t\t\t\thz = static_cast<int>(dm.dmDisplayFrequency);
\t\t\t\t}
\t\t\t\tconst auto& sc = Get().dx12SwapChain;
\t\t\t\tSKSE::log::info("[XRAY] env: virtual={}x{} physical={}x{}@{}Hz swapchain={}x{} "
\t\t\t\t\t"render={:.4f} dpiAware={} | virtual!=physical => DPI-virtualized process",
\t\t\t\t\tvw, vh, pw, ph, hz, a_width, a_height, sc.renderScaleX,
\t\t\t\t\t::IsProcessDPIAware() ? 1 : 0);
\t\t\t\tSKSE::log::info("[XRAY] diag active v0.61 (compiled " __DATE__ " " __TIME__ ")");
\t\t\t}
\t\t}
""")

pair(C, "C5 presented histogram", """\t\t\t\tdlssgFramesPresentedLast = state.numFramesActuallyPresented;
\t\t\t\tstatic std::uint32_t presentedLog = 0;
""", """\t\t\t\tdlssgFramesPresentedLast = state.numFramesActuallyPresented;
\t\t\t\t// v0.61: classify every presented sample by menu/world and keep a
\t\t\t\t// histogram. The run then answers "was generation throttled in the menu?"
\t\t\t\t// without grepping interleaved probes: if the runtime honours
\t\t\t\t// eEnableFullscreenMenuDetection, presentedMenu collapses to 1 while
\t\t\t\t// presentedWorld holds at the accepted multiplier. `menuOpenNow` is
\t\t\t\t// written once per frame by CheckFrameConstants, which runs after this
\t\t\t\t// call, so the split can lag by at most one frame.
\t\t\t\t{
\t\t\t\t\tconst std::uint32_t p = dlssgFramesPresentedLast;
\t\t\t\t\tconst std::uint32_t idx = p > 7u ? 7u : p;
\t\t\t\t\t++diag.presentedAll[idx];
\t\t\t\t\tif (diag.menuOpenNow)
\t\t\t\t\t\t++diag.presentedMenu[idx];
\t\t\t\t\telse
\t\t\t\t\t\t++diag.presentedWorld[idx];
\t\t\t\t\tdiag.presentedPrev = p;
\t\t\t\t}
\t\t\t\tstatic std::uint32_t presentedLog = 0;
""")

# ---------------------------------------------------------------- main.cpp
pair(M, "M1 RUN START banner", """\tSKSE::log::info("[FrameGen] DynamicShaderFrameGen loaded (build {} {})", __DATE__, __TIME__);

\tauto& fg = FrameGen::Get();
""", """\tSKSE::log::info("[FrameGen] DynamicShaderFrameGen loaded (build {} {})", __DATE__, __TIME__);

\t// v0.61: identify the exact DLL the game loaded. "Which copy is actually
\t// running" (build tree vs MO2 mods dir vs overwrite) could not be answered
\t// from the log more than once. Module path + write time settles it in one line.
\t{
\t\tHMODULE self = nullptr;
\t\tif (::GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
\t\t                         GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
\t\t        reinterpret_cast<LPCSTR>(&MessageHandler), &self) &&
\t\t\tself) {
\t\t\tchar dllPath[MAX_PATH] = {};
\t\t\t::GetModuleFileNameA(self, dllPath, MAX_PATH);
\t\t\tWIN32_FILE_ATTRIBUTE_DATA fad{};
\t\t\tSYSTEMTIME st{};
\t\t\tif (::GetFileAttributesExA(dllPath, GetFileExInfoStandard, &fad) &&
\t\t\t\t::FileTimeToSystemTime(&fad.ftLastWriteTime, &st)) {
\t\t\t\tSKSE::log::info("[XRAY] RUN START {} - dll={} mtime={:04d}-{:02d}-{:02d} {:02d}:{:02d} size={}B",
\t\t\t\t\t__DATE__ " " __TIME__, dllPath, st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute,
\t\t\t\t\tstatic_cast<unsigned long long>(
\t\t\t\t\t\t(static_cast<unsigned long long>(fad.nFileSizeHigh) << 32) |
\t\t\t\t\t\tstatic_cast<unsigned long long>(fad.nFileSizeLow)));
\t\t\t} else {
\t\t\t\tSKSE::log::info("[XRAY] RUN START {} - dll={}", __DATE__ " " __TIME__, dllPath);
\t\t\t}
\t\t}
\t}

\tauto& fg = FrameGen::Get();
""")

# ---------------------------------------------------------------- FrameGen.cpp
pair(G, "G1 which ini won", """\t\tstd::ifstream f("Data/SKSE/Plugins/DynamicShaderFrameGen.ini");
\t\tif (!f.is_open()) {
\t\t\tSKSE::log::warn("[FrameGen] No INI found, using defaults (Enable={})", settings.enableFrameGen);
\t\t\treturn;
\t\t}
\t\tstd::string line;
""", """\t\tstd::ifstream f("Data/SKSE/Plugins/DynamicShaderFrameGen.ini");
\t\tif (!f.is_open()) {
\t\t\tchar cwdMissing[MAX_PATH] = {};
\t\t\t::GetCurrentDirectoryA(MAX_PATH, cwdMissing);
\t\t\tSKSE::log::warn("[FrameGen] No INI found, using defaults (Enable={})", settings.enableFrameGen);
\t\t\tSKSE::log::warn("[XRAY] INI MISSING: cwd={} expected={}\\\\Data\\\\SKSE\\\\Plugins\\\\DynamicShaderFrameGen.ini",
\t\t\t\tcwdMissing, cwdMissing);
\t\t\treturn;
\t\t}
\t\t// v0.61: name the file that actually won. The path is relative to the process
\t\t// CWD (the game directory) and a whole debug round was lost to "which copy of
\t\t// the ini is the game reading" - resolved path + size is the only proof.
\t\t{
\t\t\tchar cwd[MAX_PATH] = {};
\t\t\t::GetCurrentDirectoryA(MAX_PATH, cwd);
\t\t\tf.seekg(0, std::ios::end);
\t\t\tconst auto iniSize = static_cast<long long>(f.tellg());
\t\t\tf.clear();
\t\t\tf.seekg(0, std::ios::beg);
\t\t\tSKSE::log::info("[XRAY] INI: cwd={} file={}\\\\Data\\\\SKSE\\\\Plugins\\\\DynamicShaderFrameGen.ini size={}B",
\t\t\t\tcwd, cwd, iniSize);
\t\t}
\t\tstd::string line;
""")


# ---------------------------------------------------------------- machinery
def read_text(path):
    raw = open(path, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    enc = "utf-8-sig" if bom else "utf-8"
    try:
        text = raw.decode(enc)
    except UnicodeDecodeError:
        enc = "gbk"
        text = raw.decode(enc)
    return text, enc, bom


def eol_of(text):
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def apply_edits(text):
    eol = eol_of(text)
    problems = []
    for label, path, kind, a, b in EDITS:
        if path != CURRENT:
            continue
        if kind == "pair":
            old = a.replace("\n", eol)
            new = b.replace("\n", eol)
            n = text.count(old)
            if n != 1:
                problems.append("%-34s count(old)=%d (need 1)" % (label, n))
                continue
            text = text.replace(old, new, 1)
            print("  [apply] %s  (+%d chars)" % (label, len(new) - len(old)))
        else:
            head = a.replace("\n", eol)
            tail_marker, tail_suffix = b
            tm = tail_marker.replace("\n", eol)
            ts = tail_suffix.replace("\n", eol)
            new = b if isinstance(b, str) else None
            new_txt = EDITS_NEW[label].replace("\n", eol)
            if text.count(head) != 1:
                problems.append("%-34s count(head)=%d (need 1)" % (label, text.count(head)))
                continue
            i = text.index(head)
            if text.count(tm) != 1:
                problems.append("%-34s count(tail_marker)=%d (need 1)" % (label, text.count(tm)))
                continue
            j = text.index(tm)
            if j < i:
                problems.append("%-34s tail marker precedes head" % label)
                continue
            end = j + len(tm)
            if text[end:end + len(ts)] != ts:
                problems.append("%-34s tail_suffix mismatch: %r" % (label, text[end:end + len(ts)]))
                continue
            end += len(ts)
            text = text[:i] + new_txt + text[end:]
            print("  [apply] %s  (%d chars removed)" % (label, end - i))
    return text, problems


def main():
    global CURRENT
    apply_now = "--apply" in sys.argv

    print("== idempotence guard ==")
    holder = open(MARKER_PATH, encoding="utf-8", newline="").read()
    if MARKER in holder:
        print("REFUSED: '%s' already present in Streamline.cpp - patch has run." % MARKER)
        return 1
    print("  marker absent -> safe to proceed")

    # span replacement bodies were registered at definition time (see `span`).

    files = {}
    for path in (H, C, M, G):
        text, enc, bom = read_text(path)
        files[path] = [text, enc, bom]

    print()
    print("== per-file EOL / anchors ==")
    ok = True
    for path in (H, C, M, G):
        text = files[path][0]
        eol = "CRLF" if eol_of(text) == "\r\n" else "LF"
        n = sum(1 for e in EDITS if e[1] == path)
        print("%-28s eol=%-4s edits=%d" % (os.path.basename(path), eol, n))

    print()
    print("== anchor check (dry run) ==")
    for path in (H, C, M, G):
        CURRENT = path
        text, problems = apply_edits(files[path][0])
        if problems:
            ok = False
            print("  !! %s" % os.path.basename(path))
            for p in problems:
                print("     " + p)
    if not ok:
        print()
        print("RESULT: REFUSED, nothing written")
        return 2

    if not apply_now:
        print()
        print("RESULT: DRY RUN OK - all anchors matched exactly once. Re-run with --apply.")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(BAK_ROOT, "xray_diag_" + stamp)
    os.makedirs(bak, exist_ok=True)

    print()
    print("== writing ==")
    for path in (H, C, M, G):
        CURRENT = path
        text, enc, bom = files[path]
        before = text
        new_text, problems = apply_edits(before)
        assert not problems, problems
        shutil.copy2(path, os.path.join(bak, os.path.basename(path) + ".bak"))
        data = new_text.encode(enc)
        if bom and not data.startswith(b"\xef\xbb\xbf"):
            data = b"\xef\xbb\xbf" + data
        open(path, "wb").write(data)
        raw = open(path, "rb").read()
        crlf, lf = raw.count(b"\r\n"), raw.count(b"\n")
        print("  WROTE %-22s bytes=%d (was %d)  CRLF=%d bareLF=%d"
              % (os.path.basename(path), len(raw), len(before.encode(enc)), crlf, lf - crlf))

    print()
    print("== read-back verification ==")
    after_c = open(C, encoding="utf-8", newline="").read()
    checks = [
        ("[XRAY] heartbeat", "[XRAY] serial={} menu={} world={}" in after_c),
        ("[XRAY] verdict",    "[XRAY] VERDICT: {}" in after_c),
        ("[XRAY] menu edge",  "[XRAY] MENU EDGE open={}" in after_c),
        ("diag active marker", MARKER in after_c),
        ("orphan counters gone", "static std::uint32_t constsOk = 0" not in after_c),
        ("old motionProbe gone", "motionProbe" not in after_c),
        ("old resetProbe gone", "resetProbe" not in after_c),
        ("GameMenuOpenNow defined", "bool GameMenuOpenNow()" in after_c),
    ]
    after_h = open(H, encoding="utf-8", newline="").read()
    checks.append(("Diag struct in header", "struct Diag" in after_h and "Diag diag;" in after_h))
    after_m = open(M, encoding="utf-8", newline="").read()
    checks.append(("[XRAY] RUN START in main", "[XRAY] RUN START" in after_m))
    after_g = open(G, encoding="utf-8", newline="").read()
    checks.append(("[XRAY] INI in FrameGen", "[XRAY] INI:" in after_g))

    all_ok = True
    for name, got in checks:
        print("  [%s] %s" % ("ok" if got else "!!", name))
        all_ok = all_ok and got

    print()
    print("backup dir: %s" % bak)
    print("RESULT: %s" % ("OK - patched and verified" if all_ok else "FAILED - inspect manually"))
    return 0 if all_ok else 3


if __name__ == "__main__":
    sys.exit(main())
