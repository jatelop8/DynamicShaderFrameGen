# -*- coding: utf-8 -*-
"""
v1.30 -- THE SCREEN, and the 4x test that could not fire.

Run 13:12 (v1.29, first run of it) ends at 13:12:46.855 with NO shutdown line,
and the watchdog thread writes its own last line at 13:12:46.759 still reading
silent=5ms.  Transfusion has 4x applied at 13:12:44.551, DLSS-G reporting 4x at
13:12:44.747, [PERF] 4x 33.3 FPS at 13:12:45.454 -- and the process is gone
2.2 s later.  That is the user's "as soon as 4x starts it freezes, two seconds
after entering the game", to the millisecond.

There is no crash: WER holds three AppCrash_SkyrimSE.exe reports from Sep 18
and none from Sep 20, and the Application log has no 1000/1002 event for this
window.  So the process was terminated, not crashed.

Four changes:

  A. THE SCREEN PROBE (new).  Every field this plugin owns is on our side of
     the fence: frames= our Present entries, lastPr= our swap chain's flips,
     [PIXEL] colorOut -- the D3D11 texture we hand TO DLSS-G, i.e. the input --
     cpuD our process, silent/presentAge our calls.  None of them reads the
     screen, and a rising lastPr is not even evidence the panel moved, because
     a flip queue lets Present return before anything has scanned out.
     So capture the screen: StretchBlt the desktop into a 64x64 DIB once a
     second in the watchdog thread, hash it, and compare that hash against the
     hash of our own colorOut.  When the screen holds one image while our own
     image takes three or more values in the same window, the picture the
     player sees is not the picture we are producing -- and that is printed
     with the word STALE.

  B. THE 4x TEST COULD NEVER FIRE.  v1.29 asked for lastPr > frames*3, a
     CUMULATIVE ratio.  On this run the end state was lastPr=906 against
     frames=705, so the test needed 2115 flips and was false for the whole
     session -- including the two seconds it was built for.  4x SNAPSHOT,
     4x probe and FLIP COUNTER FROZEN all reported zero occurrences, and every
     one of those zeros was the instrument, not the phenomenon.  The definition
     of "the multiplier is 4x" is a RATE over the last 200 ms slice, which is
     what it now is.  FLIP COUNTER FROZEN additionally loses its dependence on
     live4x: it is now simply "our Present ran at least 3 times in the last
     200 ms and the flip counter did not move at all".

  C. THE FLICKER GATE, THIRD FALSE POSITIVE.  rev >= 1 fired four times on the
     load screen at 13:12:33.9-35.5 with the window
       [0 0 1 1 1 1 2 1]   (luminance 0.0, 0.0, 104.0 x4, 104.9, 104.0)
     That is a one-way black-to-bright ramp plus ONE sample that is 0.9/255
     brighter than its neighbours.  A 0.9/255 wobble is not "the image came
     back".  rev now has to reach 2, which a single blip cannot.

  D. THE INPUT WITNESS GETS A SECOND SOURCE.  This run printed kb=0 in all
     sixteen [CAM] PC lines while dc= (the mouse) read 2006/1, 2155/1, 2132/1,
     so the mouse reached the process and the keyboard did not.  Scanning more
     keys cannot settle that -- GetLastInputInfo asks the OS the only question
     that matters, "was there ANY input to this session in the last second",
     and is immune to which key it was.  It returns a timestamp, so 1 Hz is
     enough.  Printed as ai=<ms since last input>.

Not claimed: v1.30 has not been run.  The screen probe can fail in a way that
would make its absence look like health -- if the game ever goes exclusive
fullscreen the capture sees nothing -- so it prints [SCREEN] BLIND when ten
consecutive captures are uniformly black, and it prints a [SCREEN] ERROR if the
capture could not be created at all.
"""

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load(rel):
    raw = pathlib.Path(ROOT / rel).read_bytes()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n")
    cr = raw.count(b"\r")
    assert cr == crlf, "%s has a stray CR" % rel
    nl = b"\r\n" if crlf == lf else b"\n"
    text = raw.decode("utf-8")
    if nl == b"\r\n":
        text = text.replace("\r\n", "\n")
    return text, nl


def save(rel, text, nl):
    out = text.encode("utf-8")
    if nl == b"\r\n":
        out = out.replace(b"\n", b"\r\n")
    pathlib.Path(ROOT / rel).write_bytes(out)


# ---------------------------------------------------------------- anchors ----

DX = "src/DX12SwapChain.cpp"
FG = "src/FrameGen.cpp"

G_OLD = "\tstatic std::atomic<std::uintptr_t> g_probeHwnd{ 0 };"

G_NEW = """\tstatic std::atomic<std::uintptr_t> g_probeHwnd{ 0 };
\t// v1.30: the hash of the image we hand to DLSS-G, published by PixelProbeTick
\t// so the watchdog can put it beside the hash of the screen.  The screen probe
\t// is the only witness in this file that is not ours, and it means nothing
\t// without a second reading to compare against: "the screen did not change" is
\t// a bug only if OUR image did.
\tstatic std::atomic<std::uint64_t> g_colorOutHash{ 0 };"""

PIX_OLD = """\t\t\t\tpixelProbeLastHash = h;

\t\t\t\t// v1.26 -- oscillation window. `changed` is incremented whenever this"""

PIX_NEW = """\t\t\t\tpixelProbeLastHash = h;
\t\t\t\t// v1.30: hand this sample to the watchdog, which samples the SCREEN
\t\t\t\t// once a second and compares the two.  This buffer is colorOut -- what
\t\t\t\t// we hand TO DLSS-G.  It is the input to frame generation, so it can
\t\t\t\t// never show whether the generated picture arrived; that is what the
\t\t\t\t// screen probe is for.
\t\t\t\tg_colorOutHash.store(h);

\t\t\t\t// v1.26 -- oscillation window. `changed` is incremented whenever this"""

FLICKER_OLD = """\t\t\t\tif (pixelProbeRingFill >= 8u && distinct <= 3u && revisits >= 1u &&
\t\t\t\t\tpixelProbeFlickerFired < 4u) {"""

FLICKER_NEW = """\t\t\t\t// v1.30 -- rev >= 1 was not enough, and the 13:12 run is the third
\t\t\t\t// false positive in a row.  It fired four times on the load screen
\t\t\t\t// with shape=[0 0 1 1 1 1 2 1], i.e. black, black, bright x4, ONE
\t\t\t\t// sample at 104.9 among neighbours at 104.0, bright.  That is a
\t\t\t\t// one-way black-to-bright ramp plus a 0.9/255 wobble, and a 0.9/255
\t\t\t\t// wobble is not "the image came back".  rev counts every non-adjacent
\t\t\t\t// pair of equal states, so a genuine alternation A,B,A,B,A,B,A,B
\t\t\t\t// scores 12 while a single blip scores 1: requiring 2 separates them
\t\t\t\t// without touching the sensitivity that matters.
\t\t\t\tif (pixelProbeRingFill >= 8u && distinct <= 3u && revisits >= 2u &&
\t\t\t\t\tpixelProbeFlickerFired < 4u) {"""

W4X_OLD = """\t\t\t\t\t{
\t\t\t\t\t\tstatic unsigned long long s_prevFlipPr = 0;
\t\t\t\t\t\tstatic unsigned long long s_prevFlipMs = 0;
\t\t\t\t\t\tstatic int s_frozenTicks = 0;
\t\t\t\t\t\tstatic bool s_saw4x = false;
\t\t\t\t\t\tstatic long long s_4xAtMs = 0;
\t\t\t\t\t\t// "the multiplier really is 4x" needs a test that cannot fire on a load
\t\t\t\t\t\t// screen, where frames and lastPr are both tiny and their ratio means
\t\t\t\t\t\t// nothing.  Both must be warm AND the flip counter must run well ahead
\t\t\t\t\t\t// of our own Present count; 3x of frames is the conservative form of
\t\t\t\t\t\t// "about 4 flips per real frame".
\t\t\t\t\t\tconst bool warm4x = frames > 200ull && lastPr > frames * 3ull;
\t\t\t\t\t\tif (warm4x && !s_saw4x) {
\t\t\t\t\t\t\ts_saw4x = true;
\t\t\t\t\t\t\ts_4xAtMs = nowMs;
\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [XRAY] 4x SNAPSHOT t=0 frames=%llu lastPr=%llu cpuD=%llums "
\t\t\t\t\t\t\t\t"silent=%lldms presentAge=%lldms fence=%s queued=%llu dsync=%llu msg=%d\\n",
\t\t\t\t\t\t\t\tnowMs, static_cast<unsigned long long>(frames), lastPr, cpuDelta,
\t\t\t\t\t\t\t\tsilent,
\t\t\t\t\t\t\t\t(g_presentEnteredMs.load() > 0) ? (nowMs - g_presentEnteredMs.load()) : 0LL,
\t\t\t\t\t\t\t\tfenceTxt, queued, dsync, msgOk);
\t\t\t\t\t\t} else if (warm4x && s_saw4x && (nowMs - s_4xAtMs) < 3000LL && (tick % 5) == 0) {
\t\t\t\t\t\t\tconst unsigned long long dFlip = (lastPr >= s_prevFlipPr) ? (lastPr - s_prevFlipPr) : 0ull;
\t\t\t\t\t\t\tconst unsigned long long dMs = (nowMs > (long long)s_prevFlipMs) ? (unsigned long long)(nowMs - (long long)s_prevFlipMs) : 0ull;
\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [XRAY] 4x probe +%lldms frames=%llu lastPr=%llu "
\t\t\t\t\t\t\t\t"panel=%llu flips/s cpuD=%llums silent=%lldms stage=%s\\n",
\t\t\t\t\t\t\t\tnowMs, nowMs - s_4xAtMs,
\t\t\t\t\t\t\t\tstatic_cast<unsigned long long>(frames), lastPr,
\t\t\t\t\t\t\t\tdMs ? (dFlip * 1000ull / dMs) : 0ull, cpuDelta, silent, self.lastStage());
\t\t\t\t\t\t}
\t\t\t\t\t\tif (s_prevFlipPr != 0 && lastPr <= s_prevFlipPr && warm4x) {
\t\t\t\t\t\t\tif (++s_frozenTicks >= 5) {
\t\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [XRAY] FLIP COUNTER FROZEN for %d ticks - our Present is still being "
\t\t\t\t\t\t\t\t\t"entered (frames=%llu) but nothing has reached the panel (lastPr stuck at %llu). "
\t\t\t\t\t\t\t\t\t"The picture on screen is not advancing.\\n",
\t\t\t\t\t\t\t\t\tnowMs, s_frozenTicks, static_cast<unsigned long long>(frames), lastPr);
\t\t\t\t\t\t\t\ts_frozenTicks = 0;
\t\t\t\t\t\t\t}
\t\t\t\t\t\t} else {
\t\t\t\t\t\t\ts_frozenTicks = 0;
\t\t\t\t\t\t}
\t\t\t\t\t\ts_prevFlipPr = lastPr;
\t\t\t\t\t\ts_prevFlipMs = (unsigned long long)nowMs;
\t\t\t\t\t}"""

W4X_NEW = """\t\t\t\t\t{
\t\t\t\t\t\tstatic unsigned long long s_prevFlipPr = 0;
\t\t\t\t\t\tstatic unsigned long long s_prevFlipMs = 0;
\t\t\t\t\t\tstatic unsigned long long s_prevFrames = 0;
\t\t\t\t\t\tstatic int s_frozenTicks = 0;
\t\t\t\t\t\tstatic bool s_saw4x = false;
\t\t\t\t\t\tstatic long long s_4xAtMs = 0;
\t\t\t\t\t\t// v1.30 -- "the multiplier really is 4x" has to be a RATE.
\t\t\t\t\t\t//
\t\t\t\t\t\t// v1.29 asked for lastPr > frames*3, a CUMULATIVE ratio, and the
\t\t\t\t\t\t// 13:12 run shows why that can never fire: the flip counter only
\t\t\t\t\t\t// gets ahead of our Present count while 4x is actually live, so
\t\t\t\t\t\t// the cumulative test needs 4x to have been live for most of the
\t\t\t\t\t\t// session.  That run ended at lastPr=906 against frames=705, so
\t\t\t\t\t\t// the test wanted 2115 flips and was false for the whole session
\t\t\t\t\t\t// -- including the 2.2 s it was written for.  4x SNAPSHOT,
\t\t\t\t\t\t// 4x probe and FLIP COUNTER FROZEN all reported zero lines, and
\t\t\t\t\t\t// every one of those zeros was the instrument.
\t\t\t\t\t\t//
\t\t\t\t\t\t// The definition is not cumulative: it is 4 flips per real frame
\t\t\t\t\t\t// over the slice just gone.  At ~34 present-entries/s a 200 ms
\t\t\t\t\t\t// slice holds ~7 frames, so >=3 is conservative and cannot fire
\t\t\t\t\t\t// on a load screen (where the ratio is 1.00).
\t\t\t\t\t\tconst unsigned long long dFlip =
\t\t\t\t\t\t\t(s_prevFlipPr != 0ull && lastPr >= s_prevFlipPr) ? (lastPr - s_prevFlipPr) : 0ull;
\t\t\t\t\t\tconst unsigned long long dFrames =
\t\t\t\t\t\t\t(s_prevFrames != 0ull && frames >= s_prevFrames) ? (frames - s_prevFrames) : 0ull;
\t\t\t\t\t\tconst bool live4x = (dFrames >= 3ull) && (dFlip >= dFrames * 3ull);
\t\t\t\t\t\tif (live4x && !s_saw4x) {
\t\t\t\t\t\t\ts_saw4x = true;
\t\t\t\t\t\t\ts_4xAtMs = nowMs;
\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [XRAY] 4x SNAPSHOT t=0 frames=%llu lastPr=%llu cpuD=%llums "
\t\t\t\t\t\t\t\t"silent=%lldms presentAge=%lldms fence=%s queued=%llu dsync=%llu msg=%d "
\t\t\t\t\t\t\t\t"(live4x: +%llu flips for +%llu Present entries over the last 200 ms slice)\\n",
\t\t\t\t\t\t\t\tnowMs, static_cast<unsigned long long>(frames), lastPr, cpuDelta,
\t\t\t\t\t\t\t\tsilent,
\t\t\t\t\t\t\t\t(g_presentEnteredMs.load() > 0) ? (nowMs - g_presentEnteredMs.load()) : 0LL,
\t\t\t\t\t\t\t\tfenceTxt, queued, dsync, msgOk, dFlip, dFrames);
\t\t\t\t\t\t} else if (s_saw4x && (nowMs - s_4xAtMs) < 3000LL && (tick % 5) == 0) {
\t\t\t\t\t\t\tconst unsigned long long dMs = (nowMs > (long long)s_prevFlipMs) ? (unsigned long long)(nowMs - (long long)s_prevFlipMs) : 0ull;
\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [XRAY] 4x probe +%lldms frames=%llu lastPr=%llu "
\t\t\t\t\t\t\t\t"panel=%llu flips/s cpuD=%llums silent=%lldms stage=%s live4x=%d\\n",
\t\t\t\t\t\t\t\tnowMs, nowMs - s_4xAtMs,
\t\t\t\t\t\t\t\tstatic_cast<unsigned long long>(frames), lastPr,
\t\t\t\t\t\t\t\tdMs ? (dFlip * 1000ull / dMs) : 0ull, cpuDelta, silent, self.lastStage(),
\t\t\t\t\t\t\t\tlive4x ? 1 : 0);
\t\t\t\t\t\t}
\t\t\t\t\t\t// v1.30 -- no dependence on live4x any more.  The question is
\t\t\t\t\t\t// exactly "our Present ran and the flip counter did not move",
\t\t\t\t\t\t// and a precondition that requires 4x to be live would hide the
\t\t\t\t\t\t// case where 4x was requested and never arrived.
\t\t\t\t\t\tif (dFrames >= 3ull && dFlip == 0ull) {
\t\t\t\t\t\t\tif (++s_frozenTicks >= 5) {
\t\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [XRAY] FLIP COUNTER FROZEN for %d ticks - our Present is still being "
\t\t\t\t\t\t\t\t\t"entered (%llu times in the last 200 ms) but nothing has reached the swap chain "
\t\t\t\t\t\t\t\t\t"(lastPr stuck at %llu). The picture cannot be advancing.\\n",
\t\t\t\t\t\t\t\t\tnowMs, s_frozenTicks, dFrames, lastPr);
\t\t\t\t\t\t\t\ts_frozenTicks = 0;
\t\t\t\t\t\t\t}
\t\t\t\t\t\t} else {
\t\t\t\t\t\t\ts_frozenTicks = 0;
\t\t\t\t\t\t}
\t\t\t\t\t\ts_prevFlipPr = lastPr;
\t\t\t\t\t\ts_prevFlipMs = (unsigned long long)nowMs;
\t\t\t\t\t\ts_prevFrames = frames;
\t\t\t\t\t}

\t\t\t\t\t// ========================== v1.30: THE SCREEN ==========================
\t\t\t\t\t//
\t\t\t\t\t// Every field in this file is on our side of the fence.  frames= counts
\t\t\t\t\t// our own Present entries.  lastPr= counts our own swap chain's flips,
\t\t\t\t\t// and a rising flip counter is not even evidence that the panel moved:
\t\t\t\t\t// with a flip queue, Present returns while nothing has scanned out.
\t\t\t\t\t// [PIXEL] hashes colorOut -- the D3D11 texture we hand TO DLSS-G, which
\t\t\t\t\t// is the input to frame generation, not the output.  cpuD measures our
\t\t\t\t\t// own process; silent and presentAge measure our own calls.  Not one of
\t\t\t\t\t// them has ever read the screen, and that gap is the whole of the
\t\t\t\t\t// disagreement: the user reports a frozen picture, the log reports 137
\t\t\t\t\t// flips a second, and both can be true at once.
\t\t\t\t\t//
\t\t\t\t\t// So read the screen.  StretchBlt the desktop into a 64x64 DIB once a
\t\t\t\t\t// second, hash it, and hold it beside the hash of our own colorOut.  If
\t\t\t\t\t// the screen shows ONE image across the whole window while our own
\t\t\t\t\t// image takes three or more values in that same window, then what the
\t\t\t\t\t// player sees is not what we are producing, and no amount of reading
\t\t\t\t\t// our side could ever have said so.
\t\t\t\t\t//
\t\t\t\t\t// It runs here, in the watchdog, for three reasons: it is 1 Hz, it is
\t\t\t\t\t// read-only GDI, and it sends no message to the game window -- all of
\t\t\t\t\t// which are the same requirements the rest of this thread already has.
\t\t\t\t\t// HALFTONE is on purpose: a nearest-neighbour 4K-to-64 downscale would
\t\t\t\t\t// sample 1 pixel in 60 and could miss a real change entirely.
\t\t\t\t\t//
\t\t\t\t\t// Known failure mode, stated rather than hidden: if the game ever runs
\t\t\t\t\t// exclusive fullscreen the desktop capture sees nothing, and silence
\t\t\t\t\t// would then read as health.  So a uniformly black capture is counted
\t\t\t\t\t// and [SCREEN] BLIND is printed, and a capture that cannot be created
\t\t\t\t\t// prints [SCREEN] ERROR.  ForceBorderless forces Windowed=TRUE, so the
\t\t\t\t\t// capture does include this game -- but that is a claim about the INI,
\t\t\t\t\t// not a measurement, and the two lines above are how it gets checked.
\t\t\t\t\tif ((tick % 5) == 3) {
\t\t\t\t\t\tstatic const int kScrDim = 64;
\t\t\t\t\t\tstatic std::uint64_t s_scrHash[8] = {};
\t\t\t\t\t\tstatic std::uint64_t s_scrPix[8] = {};
\t\t\t\t\t\tstatic float         s_scrLum[8] = {};
\t\t\t\t\t\tstatic std::uint32_t s_scrAt = 0u;
\t\t\t\t\t\tstatic std::uint32_t s_scrFill = 0u;
\t\t\t\t\t\tstatic std::uint32_t s_scrSeq = 0u;
\t\t\t\t\t\tstatic HDC           s_scrDc = nullptr;
\t\t\t\t\t\tstatic HBITMAP       s_scrBmp = nullptr;
\t\t\t\t\t\tstatic void*         s_scrBits = nullptr;
\t\t\t\t\t\tstatic bool          s_scrDead = false;
\t\t\t\t\t\tstatic int           s_scrBlind = 0;
\t\t\t\t\t\tstatic bool          s_scrBlindSaid = false;
\t\t\t\t\t\tif (!s_scrDead && !s_scrDc) {
\t\t\t\t\t\t\tHDC sd = ::GetDC(nullptr);
\t\t\t\t\t\t\tif (!sd) {
\t\t\t\t\t\t\t\ts_scrDead = true;
\t\t\t\t\t\t\t} else {
\t\t\t\t\t\t\t\tBITMAPINFO bi{};
\t\t\t\t\t\t\t\tbi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
\t\t\t\t\t\t\t\tbi.bmiHeader.biWidth = kScrDim;
\t\t\t\t\t\t\t\tbi.bmiHeader.biHeight = -kScrDim;   // negative: rows top-down
\t\t\t\t\t\t\t\tbi.bmiHeader.biPlanes = 1;
\t\t\t\t\t\t\t\tbi.bmiHeader.biBitCount = 32;
\t\t\t\t\t\t\t\tbi.bmiHeader.biCompression = BI_RGB;
\t\t\t\t\t\t\t\tvoid* bits = nullptr;
\t\t\t\t\t\t\t\ts_scrDc = ::CreateCompatibleDC(sd);
\t\t\t\t\t\t\t\ts_scrBmp = s_scrDc
\t\t\t\t\t\t\t\t\t? ::CreateDIBSection(sd, &bi, DIB_RGB_COLORS, &bits, nullptr, 0)
\t\t\t\t\t\t\t\t\t: nullptr;
\t\t\t\t\t\t\t\tif (s_scrDc && s_scrBmp && bits && ::SelectObject(s_scrDc, s_scrBmp)) {
\t\t\t\t\t\t\t\t\ts_scrBits = bits;
\t\t\t\t\t\t\t\t\t::SetStretchBltMode(s_scrDc, HALFTONE);
\t\t\t\t\t\t\t\t\t::SetBrushOrgEx(s_scrDc, 0, 0, nullptr);
\t\t\t\t\t\t\t\t} else {
\t\t\t\t\t\t\t\t\ts_scrDead = true;
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t\t::ReleaseDC(nullptr, sd);
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\tif (s_scrDead) {
\t\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [SCREEN] ERROR: the capture could not be created (dc=%d bmp=%d). "
\t\t\t\t\t\t\t\t\t"Every other field in this file stays on our side of the fence, so with this dead "
\t\t\t\t\t\t\t\t\t"this run contains no measurement of what the player sees - not one, either way.\\n",
\t\t\t\t\t\t\t\t\tnowMs, s_scrDc ? 1 : 0, s_scrBmp ? 1 : 0);
\t\t\t\t\t\t\t}
\t\t\t\t\t\t}
\t\t\t\t\t\tif (s_scrDc && s_scrBits) {
\t\t\t\t\t\t\tHDC sd = ::GetDC(nullptr);
\t\t\t\t\t\t\tif (sd) {
\t\t\t\t\t\t\t\tconst int vx = ::GetSystemMetrics(SM_XVIRTUALSCREEN);
\t\t\t\t\t\t\t\tconst int vy = ::GetSystemMetrics(SM_YVIRTUALSCREEN);
\t\t\t\t\t\t\t\tconst int vw = ::GetSystemMetrics(SM_CXVIRTUALSCREEN);
\t\t\t\t\t\t\t\tconst int vh = ::GetSystemMetrics(SM_CYVIRTUALSCREEN);
\t\t\t\t\t\t\t\tconst BOOL ok = (vw > 0 && vh > 0)
\t\t\t\t\t\t\t\t\t? ::StretchBlt(s_scrDc, 0, 0, kScrDim, kScrDim, sd, vx, vy, vw, vh, SRCCOPY)
\t\t\t\t\t\t\t\t\t: FALSE;
\t\t\t\t\t\t\t\t::ReleaseDC(nullptr, sd);
\t\t\t\t\t\t\t\tif (ok) {
\t\t\t\t\t\t\t\t\tconst auto* px = static_cast<const std::uint8_t*>(s_scrBits);
\t\t\t\t\t\t\t\t\tconst std::size_t nPx = static_cast<std::size_t>(kScrDim) * kScrDim;
\t\t\t\t\t\t\t\t\tstd::uint64_t h2 = 1469598103934665603ull;   // FNV-1a
\t\t\t\t\t\t\t\t\tstd::uint64_t lsum = 0;
\t\t\t\t\t\t\t\t\tfor (std::size_t i = 0; i < nPx * 4u; ++i) {
\t\t\t\t\t\t\t\t\t\th2 ^= px[i];
\t\t\t\t\t\t\t\t\t\th2 *= 1099511628211ull;
\t\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t\t\t// DIB section is BGRA; sum B+G+R, skip A.
\t\t\t\t\t\t\t\t\tfor (std::size_t i = 0; i + 3u < nPx * 4u; i += 4u)
\t\t\t\t\t\t\t\t\t\tlsum += static_cast<std::uint64_t>(px[i]) + px[i + 1u] + px[i + 2u];
\t\t\t\t\t\t\t\t\tconst float slum = static_cast<float>(lsum) / (static_cast<float>(nPx) * 3.0f);
\t\t\t\t\t\t\t\t\t++s_scrSeq;
\t\t\t\t\t\t\t\t\ts_scrHash[s_scrAt] = h2;
\t\t\t\t\t\t\t\t\ts_scrPix[s_scrAt] = g_colorOutHash.load();
\t\t\t\t\t\t\t\t\ts_scrLum[s_scrAt] = slum;
\t\t\t\t\t\t\t\t\ts_scrAt = (s_scrAt + 1u) % 8u;
\t\t\t\t\t\t\t\t\tif (s_scrFill < 8u)
\t\t\t\t\t\t\t\t\t\t++s_scrFill;
\t\t\t\t\t\t\t\t\t// Read the window in WRITE order.  v1.28 had to fix exactly
\t\t\t\t\t\t\t\t\t// this mistake in the pixel probe, where slot order is write
\t\t\t\t\t\t\t\t\t// order rotated by the write cursor.
\t\t\t\t\t\t\t\t\tstd::uint32_t sDistinct = 0u;
\t\t\t\t\t\t\t\t\tstd::uint32_t pDistinct = 0u;
\t\t\t\t\t\t\t\t\tfor (std::uint32_t i = 0; i < s_scrFill; ++i) {
\t\t\t\t\t\t\t\t\t\tconst std::uint64_t sHere = s_scrHash[(s_scrAt + i) % 8u];
\t\t\t\t\t\t\t\t\t\tconst std::uint64_t pHere = s_scrPix[(s_scrAt + i) % 8u];
\t\t\t\t\t\t\t\t\t\tbool sSeen = false, pSeen = false;
\t\t\t\t\t\t\t\t\t\tfor (std::uint32_t k = 0; k < i; ++k) {
\t\t\t\t\t\t\t\t\t\t\tif (s_scrHash[(s_scrAt + k) % 8u] == sHere) sSeen = true;
\t\t\t\t\t\t\t\t\t\t\tif (s_scrPix[(s_scrAt + k) % 8u] == pHere) pSeen = true;
\t\t\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t\t\t\tif (!sSeen) ++sDistinct;
\t\t\t\t\t\t\t\t\t\tif (!pSeen) ++pDistinct;
\t\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t\t\tconst HWND probeW = reinterpret_cast<HWND>(g_probeHwnd.load());
\t\t\t\t\t\t\t\t\tconst int isFg = (probeW && ::GetForegroundWindow() == probeW) ? 1 : 0;
\t\t\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [SCREEN] #%u hash=%016llX lum=%.2f distinct=%u/%u "
\t\t\t\t\t\t\t\t\t\t"ours=%016llX ourDistinct=%u fg=%d frames=%llu\\n",
\t\t\t\t\t\t\t\t\t\tnowMs, s_scrSeq, static_cast<unsigned long long>(h2),
\t\t\t\t\t\t\t\t\t\tstatic_cast<double>(slum), sDistinct, s_scrFill,
\t\t\t\t\t\t\t\t\t\tstatic_cast<unsigned long long>(g_colorOutHash.load()),
\t\t\t\t\t\t\t\t\t\tpDistinct, isFg,
\t\t\t\t\t\t\t\t\t\tstatic_cast<unsigned long long>(frames));
\t\t\t\t\t\t\t\t\tif (slum < 0.05f) {
\t\t\t\t\t\t\t\t\t\tif (++s_scrBlind == 10 && !s_scrBlindSaid) {
\t\t\t\t\t\t\t\t\t\t\ts_scrBlindSaid = true;
\t\t\t\t\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [SCREEN] BLIND: ten consecutive captures are uniformly black. "
\t\t\t\t\t\t\t\t\t\t\t\t"Either the screen really is black or the capture cannot see the game "
\t\t\t\t\t\t\t\t\t\t\t\t"(exclusive fullscreen does this). Until this is resolved, a missing "
\t\t\t\t\t\t\t\t\t\t\t\t"[SCREEN] change is NO MEASUREMENT - never 'the screen was fine'.\\n",
\t\t\t\t\t\t\t\t\t\t\t\tnowMs);
\t\t\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t\t\t} else {
\t\t\t\t\t\t\t\t\t\ts_scrBlind = 0;
\t\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t\t\t// The verdict this instrument exists for, and the first one in
\t\t\t\t\t\t\t\t\t// this project that is about the screen rather than about us.
\t\t\t\t\t\t\t\t\tif (s_scrFill >= 8u && sDistinct <= 1u && pDistinct >= 3u && slum > 3.0f) {
\t\t\t\t\t\t\t\t\t\tstd::fprintf(f, "[%lld] [SCREEN] STALE over %u s: the SCREEN has shown ONE image "
\t\t\t\t\t\t\t\t\t\t\t"(hash=%016llX lum=%.1f) while our own colorOut took %u different values in "
\t\t\t\t\t\t\t\t\t\t\t"the same window, with our Present entered %llu times. What the player "
\t\t\t\t\t\t\t\t\t\t\t"sees is not advancing, and it is not the image we hand to DLSS-G.\\n",
\t\t\t\t\t\t\t\t\t\t\tnowMs, s_scrFill - 1u,
\t\t\t\t\t\t\t\t\t\t\tstatic_cast<unsigned long long>(s_scrHash[(s_scrAt + s_scrFill - 1u) % 8u]),
\t\t\t\t\t\t\t\t\t\t\tstatic_cast<double>(s_scrLum[(s_scrAt + s_scrFill - 1u) % 8u]),
\t\t\t\t\t\t\t\t\t\t\tpDistinct, static_cast<unsigned long long>(frames));
\t\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t}
\t\t\t\t\t\t}
\t\t\t\t\t}"""

CAM_FMT_OLD = '\t\t\t\t\t\t"in(os=0x{:x} dc={:.0f}/{} fg={} kb={}) "'
CAM_FMT_NEW = '\t\t\t\t\t\t"in(os=0x{:x} dc={:.0f}/{} fg={} kb={} ai={}) "'

CAM_ARG_OLD = "\t\t\t\t\t\ts_inKeys, s_inDist, s_inMoves, s_inFg, s_inKbHeld,"
CAM_ARG_NEW = "\t\t\t\t\t\ts_inKeys, s_inDist, s_inMoves, s_inFg, s_inKbHeld, s_lastInputAge,"

CAM_INS_OLD = """\t\t\t\t\t\tsnapPcEyeStep = std::sqrt(pdx * pdx + pdy * pdy + pdz * pdz);
\t\t\t\t\t}
\t\t\t\t\tSKSE::log::info("[CAM] PC v1.19: read={} match={} adopt={}/{} rej={} ref={} \""""

CAM_INS_NEW = """\t\t\t\t\t\tsnapPcEyeStep = std::sqrt(pdx * pdx + pdy * pdy + pdz * pdz);
\t\t\t\t\t}
\t\t\t\t\t// v1.30 -- the input question, asked the other way round.
\t\t\t\t\t//
\t\t\t\t\t// v1.29 widened the mask from eight keys to all 255 and this run
\t\t\t\t\t// still printed kb=0 in all sixteen samples while dc= (the mouse)
\t\t\t\t\t// read 2006/1, 2155/1 and 2132/1.  Widening the mask cannot
\t\t\t\t\t// settle that: "no key out of 255 was down at this instant" and
\t\t\t\t\t// "the user did nothing" are still different sentences, and a
\t\t\t\t\t// 1 Hz sample has a one-second hole in it.
\t\t\t\t\t//
\t\t\t\t\t// GetLastInputInfo asks the OS the only question that matters --
\t\t\t\t\t// was there ANY input to this session -- and it is immune to
\t\t\t\t\t// which key it was, which is the whole point.  It returns a
\t\t\t\t\t// timestamp rather than a state, so 1 Hz is enough, and it covers
\t\t\t\t\t// the keyboard and the mouse together, which makes it a genuinely
\t\t\t\t\t// independent second reading of a quantity kb= has only ever
\t\t\t\t\t// reported as zero.
\t\t\t\t\tstatic DWORD s_lastInputTick = 0;
\t\t\t\t\tstatic DWORD s_lastInputAge = 0u;
\t\t\t\t\t{
\t\t\t\t\t\tLASTINPUTINFO lii{};
\t\t\t\t\t\tlii.cbSize = sizeof(LASTINPUTINFO);
\t\t\t\t\t\tif (::GetLastInputInfo(&lii)) {
\t\t\t\t\t\t\tconst DWORD nowTick = ::GetTickCount();
\t\t\t\t\t\t\ts_lastInputAge = nowTick - lii.dwTime;
\t\t\t\t\t\t\tif (lii.dwTime != s_lastInputTick) {
\t\t\t\t\t\t\t\tconst bool firstEver = (s_lastInputTick == 0u);
\t\t\t\t\t\t\t\ts_lastInputTick = lii.dwTime;
\t\t\t\t\t\t\t\tif (!firstEver) {
\t\t\t\t\t\t\t\t\tSKSE::log::info("[INPUT] system input {} ms ago - something was pressed or "
\t\t\t\t\t\t\t\t\t\t"clicked anywhere in this session within the last second (kb={} held, "
\t\t\t\t\t\t\t\t\t\t"os=0x{:x}, dc={:.0f}/{}). This is the OS's own answer and does not "
\t\t\t\t\t\t\t\t\t\t"depend on which key it was.",
\t\t\t\t\t\t\t\t\t\ts_lastInputAge, s_inKbHeld, s_inKeys,
\t\t\t\t\t\t\t\t\t\tstatic_cast<double>(s_inDist), s_inMoves);
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t}
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t\tSKSE::log::info("[CAM] PC v1.19: read={} match={} adopt={}/{} rej={} ref={} \""""

EDITS = [
    ("DX globals   :: g_colorOutHash", DX, G_OLD, G_NEW),
    ("DX pixel     :: publish the hash", DX, PIX_OLD, PIX_NEW),
    ("DX flicker   :: rev must reach 2", DX, FLICKER_OLD, FLICKER_NEW),
    ("DX watchdog  :: live4x + SCREEN", DX, W4X_OLD, W4X_NEW),
    ("FG cam       :: ai= in the format", FG, CAM_FMT_OLD, CAM_FMT_NEW),
    ("FG cam       :: ai= argument", FG, CAM_ARG_OLD, CAM_ARG_NEW),
    ("FG input     :: GetLastInputInfo", FG, CAM_INS_OLD, CAM_INS_NEW),
]

apply = "--apply" in sys.argv

files = {}
for label, rel, old, new in EDITS:
    if rel not in files:
        files[rel] = load(rel)
    text, nl = files[rel]
    n = text.count(old)
    flag = "ok " if n == 1 else "**FAIL**"
    print("%-32s %-28s count=%d %s" % (label, rel, n, flag))
    if n != 1:
        print("--- anchor was ---")
        print(repr(old[:400]))
        sys.exit("REFUSED, nothing written")

if not apply:
    print()
    print("dry run: all %d anchors are unique. re-run with --apply" % len(EDITS))
    sys.exit(0)

for label, rel, old, new in EDITS:
    text, nl = files[rel]
    n = text.count(old)
    assert n == 1, label
    text = text.replace(old, new)
    files[rel] = (text, nl)

print()
for rel, (text, nl) in files.items():
    save(rel, text, nl)
    print("wrote %-24s newline=%r" % (rel, nl))

print()
print("--- post-check: the new text is in, the old text is not ---")
for label, rel, old, new in EDITS:
    path = ROOT / rel
    raw2 = path.read_bytes()
    crlf = raw2.count(b"\r\n")
    lf = raw2.count(b"\n")
    cr = raw2.count(b"\r")
    print("%-32s crlf=%-6d lf=%-6d cr=%-6d strayCR=%d" % (label, crlf, lf, cr, cr - crlf))

for rel in files:
    raw2 = (ROOT / rel).read_bytes()
    if rel == DX:
        assert raw2.count(b"\r") == 0, "DX12SwapChain.cpp must stay pure LF"
    if rel == FG:
        assert raw2.count(b"\r\n") == raw2.count(b"\n"), "FrameGen.cpp must stay pure CRLF"

print()
print("new markers present (bytes):")
check = {
    b"g_colorOutHash": 4,
    b"[SCREEN] STALE": 1,
    b"[SCREEN] BLIND": 1,
    b"[SCREEN] ERROR": 1,
    b"live4x": 3,
    b"ai={}": 1,
    b"GetLastInputInfo": 1,
}
rawdx = (ROOT / DX).read_bytes()
rawfg = (ROOT / FG).read_bytes()
for s, want in check.items():
    n = rawdx.count(s) + rawfg.count(s)
    print("  %-24s %d (want >= %d) %s" % (s.decode(), n, want, "ok" if n >= want else "**LOW**"))

print()
print("old markers gone:")
for s in [b"revisits >= 1u", b"lastPr > frames * 3ull", b"warm4x"]:
    n = rawdx.count(s)
    print("  %-28s %d %s" % (s.decode(), n, "ok" if n == 0 else "**STILL THERE**"))

for rel in [DX, FG]:
    print("md5 %s %s" % (hashlib.md5((ROOT / rel).read_bytes()).hexdigest(), rel))
