# -*- coding: utf-8 -*-
"""v1.29 -- four repairs. None of them touches the frame generation path.

The 12:26 run (v1.28) was the second run in a row in which the world came
alive: read=553 match=518 paused=0 ld=0 hrsD=0.0056, 4x confirmed by DXGI's own
counter (lastPr 4806 -> 5021 -> 5297 against frames 4807 -> 4878 -> 4947), and
PIXEL reporting every one of its samples distinct.  It ended 4.0 s after the
world was entered, every log stopping inside the same 90 ms, with no shutdown
line in any of them.

Two of these four changes exist because that run exposed a defect that had been
sitting in the code for many versions:

  (1) 'Reflex cap check' printed 4823 lines ON ONE LOAD SCREEN while the values
      it prints (159 flip fps, 2x) never moved, and 'Reflex options applied'
      printed 4896 lines while its three values never moved either.  A log line
      that carries its values is self-refuting when it repeats with identical
      values: the edge detector is torn, not the value.  Two threads reach this
      code (this plugin's Present path runs on both, and Transfusion's own
      trace shows two tids calling slSetConstants), and a multi-word compare
      against a concurrently-written static cannot detect an edge.
      => pack each signature into one atomic word and compare with exchange.

The other two exist because two instruments have been reporting a verdict they
cannot support:

  (3) The input witness scanned eight keys (W A S D Space Shift LMB RMB).
      Sixteen consecutive runs printed os=0x0, and every one of them was read as
      "the user never pressed anything".  But the mask can only ever prove the
      negative "not those eight", and a player whose picture looks frozen
      reaches for ESC or Alt+F4 first -- neither of which is in the mask.
      => scan the whole VK space once a second.

  (4) Nothing in any log answers "is the panel advancing?".  frames= counts our
      Present entries and lastPr= counts our swapchain's flips, and on the 12:26
      run both climbed (98 entries and 392 flips in 2.86 s = 137 flips/s =
      exactly 4x) while the user was looking at a picture he called frozen.
      => print a snapshot the moment the multiplier lands on 4x and for the
         first 3 s after it, and shout when the flip counter stops.

Run:  python tools/patch_v129_torn_edges_and_blind_witnesses.py            (dry)
      python tools/patch_v129_torn_edges_and_blind_witnesses.py --apply
"""

import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPLY = "--apply" in sys.argv

# ---------------------------------------------------------------- change 1
SL_OLD1 = """\t\t\topts.frameLimitUs = capFps ? (1000000u / capFps) : 0u;
\t\t\tstatic std::uint32_t lastCapFps = 0;
\t\t\tstatic std::uint32_t lastCapMult = 0;
\t\t\t// The whole Reflex FLIP cap block is gated on this static pair, not on
\t\t\t// the block being re-entered, so the log is edge-driven either way.
\t\t\tif (capFps != lastCapFps || capMult != lastCapMult) {
\t\t\t\tconst bool capConfirmed = (dlssgAcceptedFrames != 0);
\t\t\t\tSKSE::log::info("[Streamline] Reflex FLIP cap = {} fps ({}us) - panel {}Hz, {} flips per real frame => ~{} presented fps, ~{:.1f} rendered fps (v1.12: the cap is the FLIP rate){}{}",
\t\t\t\t\tcapFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps,
\t\t\t\t\tcapFps / static_cast<double>(capMult),
\t\t\t\t\tcapFps ? "" : "  [UNLIMITED - over-submit possible]",
\t\t\t\t\tcapConfirmed ? "" : "  [UNCONFIRMED - using the 2x floor, v1.04]");
\t\t\t\tlastCapFps = capFps;
\t\t\t\tlastCapMult = capMult;
\t\t\t}
"""

SL_NEW1 = """\t\t\topts.frameLimitUs = capFps ? (1000000u / capFps) : 0u;
\t\t\t// v1.29 -- this gate was a pair of plain statics:
\t\t\t//     static std::uint32_t lastCapFps = 0, lastCapMult = 0;
\t\t\t//     if (capFps != lastCapFps || capMult != lastCapMult) { ... log ... }
\t\t\t// Two threads reach ReflexSleep (this plugin's Present path runs on both
\t\t\t// and Streamline's own trace shows two tids reaching the sibling call),
\t\t\t// and a two-word store is not atomic: one thread writes lastCapFps while
\t\t\t// the other reads lastCapMult, both see a change, and the edge-driven
\t\t\t// line fires on EVERY frame.  The 12:26 run is the proof -- 4823
\t\t\t// "Reflex cap check" lines on a single load screen, every one of them
\t\t\t// printing the same 159 flip fps and the same 2x.  A line that carries
\t\t\t// its values refutes itself when it repeats with identical values: the
\t\t\t// detector is torn, the value never moved.  One packed atomic word and
\t\t\t// an exchange, so exactly one thread sees the old value per real edge.
\t\t\tconst std::uint32_t capSig = (capFps << 4) | (capMult & 0x0Fu);
\t\t\tstatic std::atomic<std::uint32_t> lastCapSig{ 0xFFFFFFFFu };
\t\t\tif (lastCapSig.exchange(capSig) != capSig) {
\t\t\t\tconst bool capConfirmed = (dlssgAcceptedFrames != 0);
\t\t\t\tSKSE::log::info("[Streamline] Reflex FLIP cap = {} fps ({}us) - panel {}Hz, {} flips per real frame => ~{} presented fps, ~{:.1f} rendered fps (v1.12: the cap is the FLIP rate){}{}",
\t\t\t\t\tcapFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps,
\t\t\t\t\tcapFps / static_cast<double>(capMult),
\t\t\t\t\tcapFps ? "" : "  [UNLIMITED - over-submit possible]",
\t\t\t\t\tcapConfirmed ? "" : "  [UNCONFIRMED - using the 2x floor, v1.04]");
\t\t\t}
"""

# ---------------------------------------------------------------- change 2
SL_OLD2 = """\t\t// \u7f13\u5b58\u6bd4\u8f83\uff1a\u9009\u9879\u53d8\u5316\u624d\u4e0b\u53d1\uff08CS applyReflexOptionsIfChanged \u540c\u6b3e\uff09
\t\tstatic sl::ReflexOptions lastOpts{};
\t\tstatic bool lastValid = false;
\t\tif (!lastValid || std::memcmp(&lastOpts, &opts, sizeof(opts)) != 0) {
\t\t\tif (SL_FAILED(r, slReflexSetOptions(opts)))
\t\t\t\tSKSE::log::warn("[Streamline] slReflexSetOptions failed: {}", (int)r);
\t\t\telse
\t\t\t\tSKSE::log::info("[Streamline] Reflex options applied (mode={} frameLimitUs={} markers={})",
\t\t\t\t\tstatic_cast<int>(opts.mode), opts.frameLimitUs, opts.useMarkersToOptimize);
\t\t\tlastOpts = opts;
\t\t\tlastValid = true;
\t\t}
"""

SL_NEW2 = """\t\t// v1.29 -- the same torn edge as the flip-cap block above, except this gate
\t\t// decides whether slReflexSetOptions is CALLED, not merely whether a line
\t\t// is printed.  The 12:26 run carried 4896 "Reflex options applied" lines --
\t\t// one per frame, through a load screen and into the world -- while the
\t\t// three fields it prints (mode=1 frameLimitUs=6289 markers=true) never
\t\t// changed once.  memcmp over a multi-word struct that a second thread is
\t\t// concurrently writing can never be a change detector, and the struct may
\t\t// carry padding no writer initialises, which would break it even
\t\t// single-threaded.  Compare the three fields this function actually sets,
\t\t// packed into one atomic word, and let exchange pick the one caller that
\t\t// sees a real change.  Same predicate, no race, and the runtime stops
\t\t// being reconfigured on every frame.
\t\tconst std::uint64_t optsSig =
\t\t\t(static_cast<std::uint64_t>(static_cast<std::uint32_t>(opts.mode) & 0xFFFFu) << 40)
\t\t\t| (static_cast<std::uint64_t>(opts.frameLimitUs) << 1)
\t\t\t| (opts.useMarkersToOptimize ? 1ull : 0ull);
\t\tstatic std::atomic<std::uint64_t> lastOptsSig{ ~0ull };
\t\tif (lastOptsSig.exchange(optsSig) != optsSig) {
\t\t\tif (SL_FAILED(r, slReflexSetOptions(opts)))
\t\t\t\tSKSE::log::warn("[Streamline] slReflexSetOptions failed: {}", (int)r);
\t\t\telse
\t\t\t\tSKSE::log::info("[Streamline] Reflex options applied (mode={} frameLimitUs={} markers={})",
\t\t\t\t\tstatic_cast<int>(opts.mode), opts.frameLimitUs, opts.useMarkersToOptimize);
\t\t}
"""

# ---------------------------------------------------------------- change 3a
FG_OLD_DECL = """\t\t\t\t\tstatic bool s_inCurHave = false;
\t\t\t\t\tstatic int s_inFg = -1;
"""

FG_NEW_DECL = """\t\t\t\t\tstatic bool s_inCurHave = false;
\t\t\t\t\tstatic int s_inFg = -1;
\t\t\t\t\t// v1.29: the full-VK scan's two readings. kbHeld is what is down at the
\t\t\t\t\t// instant of this sample; the [INPUT] line below records transitions,
\t\t\t\t\t// which is the only part of this that survives a 1 Hz sample.
\t\t\t\t\tstatic int s_inKbHeld = 0;
"""

# ---------------------------------------------------------------- change 3b
FG_OLD_SCAN = """\t\t\t\t\t{
\t\t\t\t\t\tstd::uint32_t keys = 0u;
\t\t\t\t\t\tif (::GetAsyncKeyState('W') & 0x8000) keys |= 1u;
\t\t\t\t\t\tif (::GetAsyncKeyState('A') & 0x8000) keys |= 2u;
\t\t\t\t\t\tif (::GetAsyncKeyState('S') & 0x8000) keys |= 4u;
\t\t\t\t\t\tif (::GetAsyncKeyState('D') & 0x8000) keys |= 8u;
\t\t\t\t\t\tif (::GetAsyncKeyState(VK_SPACE) & 0x8000) keys |= 16u;
\t\t\t\t\t\tif (::GetAsyncKeyState(VK_SHIFT) & 0x8000) keys |= 32u;
\t\t\t\t\t\tif (::GetAsyncKeyState(VK_LBUTTON) & 0x8000) keys |= 64u;
\t\t\t\t\t\tif (::GetAsyncKeyState(VK_RBUTTON) & 0x8000) keys |= 128u;
\t\t\t\t\t\ts_inKeys |= keys;
"""

FG_NEW_SCAN = """\t\t\t\t\t{
\t\t\t\t\t\tstd::uint32_t keys = 0u;
\t\t\t\t\t\tif (::GetAsyncKeyState('W') & 0x8000) keys |= 1u;
\t\t\t\t\t\tif (::GetAsyncKeyState('A') & 0x8000) keys |= 2u;
\t\t\t\t\t\tif (::GetAsyncKeyState('S') & 0x8000) keys |= 4u;
\t\t\t\t\t\tif (::GetAsyncKeyState('D') & 0x8000) keys |= 8u;
\t\t\t\t\t\tif (::GetAsyncKeyState(VK_SPACE) & 0x8000) keys |= 16u;
\t\t\t\t\t\tif (::GetAsyncKeyState(VK_SHIFT) & 0x8000) keys |= 32u;
\t\t\t\t\t\tif (::GetAsyncKeyState(VK_LBUTTON) & 0x8000) keys |= 64u;
\t\t\t\t\t\tif (::GetAsyncKeyState(VK_RBUTTON) & 0x8000) keys |= 128u;
\t\t\t\t\t\ts_inKeys |= keys;
\t\t\t\t\t\t// v1.29 -- the mask above can only prove a NEGATIVE.  Sixteen runs
\t\t\t\t\t\t// in a row printed os=0x0 and every one of them was read as "the
\t\t\t\t\t\t// user never touched the keyboard", but the mask holds eight keys
\t\t\t\t\t\t// (W A S D Space Shift LMB RMB), and a player whose picture looks
\t\t\t\t\t\t// frozen reaches for ESC or Alt+F4 first -- neither is in it.
\t\t\t\t\t\t// "Not those eight" was being promoted to "no input at all", and
\t\t\t\t\t\t// the whole input-witness verdict rests on that inference.
\t\t\t\t\t\t// Scan the full VK space once a second instead: 255 batched
\t\t\t\t\t\t// GetAsyncKeyState calls cost nothing next to a 4K frame, and they
\t\t\t\t\t\t// turn the verdict from an accusation into a measurement.
\t\t\t\t\t\t// Known limit, stated rather than hidden: this is a 1 Hz sample,
\t\t\t\t\t\t// so a key tapped and released entirely between two samples is
\t\t\t\t\t\t// missed.  Holding W for the protocol's ten seconds cannot be.
\t\t\t\t\t\t{
\t\t\t\t\t\t\tstatic int s_kbLast = 0;
\t\t\t\t\t\t\tint held = 0;
\t\t\t\t\t\t\tint lastVk = 0;
\t\t\t\t\t\t\tfor (int vk = 1; vk < 256; ++vk) {
\t\t\t\t\t\t\t\tif (::GetAsyncKeyState(vk) & 0x8000) {
\t\t\t\t\t\t\t\t\t++held;
\t\t\t\t\t\t\t\t\tlastVk = vk;
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t}
\t\t\t\t\t\t\ts_inKbHeld = held;
\t\t\t\t\t\t\tif (lastVk != s_kbLast) {
\t\t\t\t\t\t\t\tSKSE::log::info("[INPUT] vk 0x{:02X} -> 0x{:02X} ({} held, fg={}) - any line here means the keyboard "
\t\t\t\t\t\t\t\t\t"reaches this process, so an os=0x0 further down is a measurement and not a blind spot",
\t\t\t\t\t\t\t\t\tstatic_cast<unsigned>(s_kbLast), static_cast<unsigned>(lastVk),
\t\t\t\t\t\t\t\t\theld, s_inFg);
\t\t\t\t\t\t\t\ts_kbLast = lastVk;
\t\t\t\t\t\t\t}
\t\t\t\t\t\t}
"""

# ---------------------------------------------------------------- change 3c
FG_OLD_FMT = """\t\t\t\t\t\t"in(os=0x{:x} dc={:.0f}/{} fg={}) "
"""

FG_NEW_FMT = """\t\t\t\t\t\t"in(os=0x{:x} dc={:.0f}/{} fg={} kb={}) "
"""

FG_OLD_ARGS = """\t\t\t\t\t\ts_inKeys, s_inDist, s_inMoves, s_inFg,
"""

FG_NEW_ARGS = """\t\t\t\t\t\ts_inKeys, s_inDist, s_inMoves, s_inFg, s_inKbHeld,
"""

# ---------------------------------------------------------------- change 3d
FG_OLD_VERDICT = """\t\t\t\t\t\t(s_inKeys != 0u || s_inMoves != 0u)
"""

FG_NEW_VERDICT = """\t\t\t\t\t\t(s_inKeys != 0u || s_inMoves != 0u || s_inKbHeld > 0)
"""

# ---------------------------------------------------------------- change 3e
FG_OLD_CLR = """\t\t\t\t\ts_inKeys = 0u;
\t\t\t\t\ts_inDist = 0.0f;
"""

FG_NEW_CLR = """\t\t\t\t\ts_inKeys = 0u;
\t\t\t\t\ts_inKbHeld = 0;
\t\t\t\t\ts_inDist = 0.0f;
"""

# ---------------------------------------------------------------- change 4
DX_OLD_TAIL = """\t\t\t\t\t\t(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
\t\t\t\t\tstd::fflush(f);
\t\t\t\t\tstd::fclose(f);
"""

DX_NEW_TAIL = """\t\t\t\t\t\t(stalled && (tick % 5) == 0) ? "   <== RENDER THREAD STALLED" : "");
\t\t\t\t\t// v1.29 -- the one question no field in this file has ever answered:
\t\t\t\t\t// is the PANEL advancing?  frames= counts our own Present entries and
\t\t\t\t\t// lastPr= counts our own swapchain's flips, and on the 12:26 run both
\t\t\t\t\t// climbed (98 entries and 392 flips in 2.86 s = 137 flips/s = exactly
\t\t\t\t\t// 4x) while the user was looking at a picture he called frozen.  Both
\t\t\t\t\t// are our side of the fence.  A flip counter that stalls is
\t\t\t\t\t// unambiguous evidence from the other side, so say it out loud; and
\t\t\t\t\t// snapshot the moment the multiplier lands on 4x plus the first 3 s
\t\t\t\t\t// after it, because that is the entire window the user has been
\t\t\t\t\t// reporting on (each of the last six runs ended inside 6 s of world
\t\t\t\t\t// time, so a rate that only ever gets printed once a minute is a rate
\t\t\t\t\t// that has never been seen).
\t\t\t\t\t{
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
\t\t\t\t\t}
\t\t\t\t\tstd::fflush(f);
\t\t\t\t\tstd::fclose(f);
"""

# helper injected just above the watchdog loop's lambda body is not needed: the
# predicate is inlined as a small file-local lambda right before it.
DX_OLD_HELPER = """\t\tstd::thread([this, path]() {
\t\t\tauto& self = *this;
"""

DX_NEW_HELPER = """\t\t// v1.29: "the multiplier is really 4x" needs a test that cannot fire during
\t\t// the load screen, where frames and lastPr are both tiny and their ratio is
\t\t// meaningless.  Both must be warm AND the flip counter must be running well
\t\t// ahead of our Present count -- 3x of frames is the conservative form of
\t\t// "around 4 flips per real frame".
\t\tconst auto is4xEligible = [](std::uint64_t f, unsigned long long lp) -> bool {
\t\t\treturn f > 200ull && lp > f * 3ull;
\t\t};
\t\tstd::thread([this, path]() {
\t\t\tauto& self = *this;
"""

EDITS = [
    ("Streamline.cpp :: flip-cap edge detector -> packed atomic", "src/Streamline.cpp", SL_OLD1, SL_NEW1),
    ("Streamline.cpp :: setOptions edge detector -> packed atomic", "src/Streamline.cpp", SL_OLD2, SL_NEW2),
    ("FrameGen.cpp   :: declare the full-VK reading", "src/FrameGen.cpp", FG_OLD_DECL, FG_NEW_DECL),
    ("FrameGen.cpp   :: scan all 255 VKs", "src/FrameGen.cpp", FG_OLD_SCAN, FG_NEW_SCAN),
    ("FrameGen.cpp   :: print kb= in the CAM line", "src/FrameGen.cpp", FG_OLD_FMT, FG_NEW_FMT),
    ("FrameGen.cpp   :: pass kb= argument", "src/FrameGen.cpp", FG_OLD_ARGS, FG_NEW_ARGS),
    ("FrameGen.cpp   :: verdict counts kb too", "src/FrameGen.cpp", FG_OLD_VERDICT, FG_NEW_VERDICT),
    ("FrameGen.cpp   :: clear the new reading", "src/FrameGen.cpp", FG_OLD_CLR, FG_NEW_CLR),
    ("DX12SwapChain  :: flip freeze + 4x snapshot", "src/DX12SwapChain.cpp", DX_OLD_TAIL, DX_NEW_TAIL),
]


def load(path):
    raw = pathlib.Path(path).read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    if bom:
        raw = raw[3:]
    crlf = raw.count(b"\r\n")
    mixed = crlf > 0 and raw.count(b"\n") > crlf
    text = raw.replace(b"\r\n", b"\n").decode("utf-8")
    return text, bom, crlf, mixed


def save(path, text, bom, crlf):
    data = text.encode("utf-8")
    if crlf:
        data = data.replace(b"\n", b"\r\n")
    if bom:
        data = b"\xef\xbb\xbf" + data
    pathlib.Path(path).write_bytes(data)


def main():
    print("=" * 78)
    print("v1.29  dry run" if not APPLY else "v1.29  APPLYING")
    print("=" * 78)
    files = {}
    for label, rel, old, new in EDITS:
        if rel not in files:
            files[rel] = load(rel)
    ok = True
    for label, rel, old, new in EDITS:
        text, bom, crlf, mixed = files[rel]
        n = text.count(old)
        flag = "OK " if n == 1 else "!! "
        if n != 1:
            ok = False
        print("%s%-58s %s  count=%d" % (flag, label, "CRLF" if crlf else "LF  ", n))
        if n == 1 and old == new:
            print("      !! old == new, this edit is a no-op")
            ok = False
    print()
    for rel, (text, bom, crlf, mixed) in files.items():
        print("%-28s crlf=%d mixed=%s bom=%s" % (rel, crlf, mixed, bom))
    if not ok:
        print("\nREFUSED, nothing written.")
        return 1
    if not APPLY:
        print("\ndry run clean - re-run with --apply")
        return 0

    # apply
    for rel in files:
        text, bom, crlf, mixed = files[rel]
        for label, r2, old, new in EDITS:
            if r2 != rel:
                continue
            assert text.count(old) == 1, "anchor lost while applying: " + label
            text = text.replace(old, new)
        files[rel] = (text, bom, crlf, mixed)
        save(rel, text, bom, crlf)
        print("wrote %s" % rel)

    # post-check: every new fragment present, every replaced anchor gone
    print()
    bad = 0
    for label, rel, old, new in EDITS:
        text, _, _, _ = files[rel]
        if old in text:
            print("  !! OLD STILL PRESENT: %s" % label)
            bad += 1
        if new not in text:
            print("  !! NEW MISSING      : %s" % label)
            bad += 1
    print("post-check: %s" % ("OK - all %d edits landed" % len(EDITS) if bad == 0 else "%d PROBLEMS" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
