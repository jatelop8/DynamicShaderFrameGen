#!/usr/bin/env python3
"""v1.28 patch.

Three independent fixes, all justified by the 03:17 run
(docs/runlogs/2026-09-20-0317-v127-tbd.*):

A. [PIXEL] flicker predicate, two bugs in one place.
   A1  The window was scanned as a plain array while the ring buffer writes
       at pixelProbeRingAt.  `distinct` happened to survive (order-free) but
       switches/maxRun did not: the run printed maxRun=5 for a window whose
       tail holds six identical samples (maxRun is 6).
   A2  v1.27's `switches >= 3` still fired twice on ONE-WAY loading-screen
       brightness ramps.  The predicate has to ask "did it come back", so the
       window is collapsed to its run-length sequence and any state that
       appears twice in it counts as a revisit.  shape= prints that collapsed
       sequence as state indices (self-reading: a ramp is [0 1 2 2 2 2 2 2],
       a flicker is [0 1 0 1 0 1 0 1]).

B. Watchdog gets a process CPU-time field.  The 19.9-20.8 s stall has four
   independent readings (frames / fence / lastPr / presentAge all frozen) but
   all four come from our side or from DXGI.  cpuD= is the first reading that
   comes from the OS scheduler: near-zero means the process is blocked, a
   full 200 ms slice means a thread is burning CPU.

C. [MFG] debug CHECK printed `menuBlock=0` hardcoded and labelled the first
   argument `frames=`, so the line named a quantity it was not printing.
   The value in that slot is dlssgOk when the branch is reached; print it
   under that name.

Every anchor must match exactly once.  Dry run by default, --apply to write.
Re-running after a successful apply is refused (new text already present).
"""

import pathlib
import sys

ROOT = pathlib.Path(r"D:/Modding/DynamicShaderFrameGen")
SWAP = ROOT / "src" / "DX12SwapChain.cpp"      # pure LF
GUI = ROOT / "src" / "ImguiMenu.cpp"           # pure CRLF

# ---------------------------------------------------------------- A1 + A2

OLD_A1 = """\t\t\t\tstd::uint32_t distinct = 0;
\t\t\t\t{
\t\t\t\t\tstd::uint64_t seenHash[8] = {};
\t\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
\t\t\t\t\t\tbool dup = false;
\t\t\t\t\t\tfor (std::uint32_t j = 0; j < distinct; ++j)
\t\t\t\t\t\t\tif (seenHash[j] == pixelProbeRingHash[i]) { dup = true; break; }
\t\t\t\t\t\tif (!dup)
\t\t\t\t\t\t\tseenHash[distinct++] = pixelProbeRingHash[i];
\t\t\t\t\t}
\t\t\t\t}"""

NEW_A1 = """\t\t\t\t// v1.28 -- read the window in RING ORDER.  Samples are written at
\t\t\t\t// pixelProbeRingHash[pixelProbeRingAt], so slot order is write order
\t\t\t\t// rotated by ringAt.  `distinct` survived that mistake because it is
\t\t\t\t// order-free; switches/maxRun did not, and the 03:17 run printed
\t\t\t\t// maxRun=5 for a window whose tail is six identical samples.
\t\t\t\tstd::uint64_t ord[8] = {};
\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i)
\t\t\t\t\tord[i] = pixelProbeRingHash[(pixelProbeRingAt + i) % 8u];

\t\t\t\t// shapeIdx[i] is the index of the first sample in this window that
\t\t\t\t// showed the same image, i.e. the state number of sample i.  Printed
\t\t\t\t// as shape=[...] so the window's shape needs no arithmetic to read.
\t\t\t\tstd::uint32_t distinct = 0;
\t\t\t\tstd::uint32_t shapeIdx[8] = {};
\t\t\t\t{
\t\t\t\t\tstd::uint64_t seenHash[8] = {};
\t\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
\t\t\t\t\t\tstd::uint32_t k = 0;
\t\t\t\t\t\tfor (; k < distinct; ++k)
\t\t\t\t\t\t\tif (seenHash[k] == ord[i]) break;
\t\t\t\t\t\tif (k == distinct)
\t\t\t\t\t\t\tseenHash[distinct++] = ord[i];
\t\t\t\t\t\tshapeIdx[i] = k;
\t\t\t\t\t}
\t\t\t\t}"""

OLD_A2 = """\t\t\t\t// v1.27 -- how many times the window changed state, and the longest run of
\t\t\t\t// one state. `distinct <= 3` plus a wide brightness swing is NOT enough on
\t\t\t\t// its own, and the 02:39 run proved it: the first two FLICKER reports of
\t\t\t\t// v1.26 both saw [0.0] [0.0] [104.0] x6 -- black, black, then lit for the
\t\t\t\t// rest of the window. That is a single transition (the loading screen
\t\t\t\t// lighting up), it lands on 2 distinct images, it swings 104/255, and it
\t\t\t\t// is not an oscillation. An oscillation has to come BACK, so require the
\t\t\t\t// state to change at least three times inside the window (A->B->A->B).
\t\t\t\t// The swing is printed but no longer gates: a flicker between two nearly
\t\t\t\t// equally bright images is still a flicker.
\t\t\t\tstd::uint32_t switches = 0;
\t\t\t\tstd::uint32_t maxRun = 0;
\t\t\t\tstd::uint32_t runLen = 0;
\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
\t\t\t\t\tif (i > 0u && pixelProbeRingHash[i] != pixelProbeRingHash[i - 1u]) {
\t\t\t\t\t\t++switches;
\t\t\t\t\t\trunLen = 0;
\t\t\t\t\t}
\t\t\t\t\t++runLen;
\t\t\t\t\tif (runLen > maxRun)
\t\t\t\t\t\tmaxRun = runLen;
\t\t\t\t}"""

NEW_A2 = """\t\t\t\t// v1.28 -- counting state changes is still the wrong question, and the
\t\t\t\t// 03:17 run proved it twice.  v1.27 required >=3 changes and fired on
\t\t\t\t// [96.6][96.6][43.0]x6 and on [43.0]x4[63.8]x3[73.4] -- both ONE-WAY
\t\t\t\t// brightness ramps of the loading screen, both with switches=2 in ring
\t\t\t\t// order.  (They only fired because the scan was reading the ring out of
\t\t\t\t// order, see above.)  The question is not "did it change", it is "did it
\t\t\t\t// come BACK".  Collapse the window to its run-length sequence and count
\t\t\t\t// how many times a state reappears non-adjacently:
\t\t\t\t//   a ramp            [a b c c c c c c] -> [a b c]              -> 0
\t\t\t\t//   a light-up        [a a b b b b b b] -> [a b]                -> 0
\t\t\t\t//   a flicker         [a b a b a b a b] -> [a b a b a b a b]    -> 5
\t\t\t\t// rev >= 1 is the gate.  A one-way move can never satisfy it, which is
\t\t\t\t// the property v1.26 and v1.27 both lacked.
\t\t\t\tstd::uint32_t switches = 0;
\t\t\t\tstd::uint32_t maxRun = 0;
\t\t\t\tstd::uint32_t runLen = 0;
\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
\t\t\t\t\tif (i > 0u && ord[i] != ord[i - 1u]) {
\t\t\t\t\t\t++switches;
\t\t\t\t\t\trunLen = 0;
\t\t\t\t\t}
\t\t\t\t\t++runLen;
\t\t\t\t\tif (runLen > maxRun)
\t\t\t\t\t\tmaxRun = runLen;
\t\t\t\t}
\t\t\t\tstd::uint32_t trLen = 0;
\t\t\t\tstd::uint32_t trIdx[8] = {};
\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
\t\t\t\t\tif (trLen == 0u || trIdx[trLen - 1u] != shapeIdx[i])
\t\t\t\t\t\ttrIdx[trLen++] = shapeIdx[i];
\t\t\t\t}
\t\t\t\tstd::uint32_t revisits = 0;
\t\t\t\tfor (std::uint32_t i = 0; i + 2u < trLen; ++i)
\t\t\t\t\tfor (std::uint32_t j = i + 2u; j < trLen; ++j)
\t\t\t\t\t\tif (trIdx[i] == trIdx[j])
\t\t\t\t\t\t\t++revisits;
\t\t\t\tchar shapeTxt[40] = {};
\t\t\t\t{
\t\t\t\t\tint off = 0;
\t\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {
\t\t\t\t\t\tconst int wrote = std::snprintf(shapeTxt + off,
\t\t\t\t\t\t\tstatic_cast<std::size_t>(40 - off), (i == 0u) ? "%u" : " %u",
\t\t\t\t\t\t\tshapeIdx[i]);
\t\t\t\t\t\tif (wrote <= 0 || 40 - off - wrote < 4)
\t\t\t\t\t\t\tbreak;
\t\t\t\t\t\toff += wrote;
\t\t\t\t\t}
\t\t\t\t}"""

# print line: add shape= and rev=
OLD_A3 = """\t\t\t\t\t\"lum={:.2f} seen={}/{} swing={:.1f} sw={} maxRun={}\","""

NEW_A3 = """\t\t\t\t\t\"lum={:.2f} seen={}/{} swing={:.1f} sw={} maxRun={} shape=[{}] rev={}\","""

OLD_A4 = """\t\t\t\t\tstatic_cast<double>(lum), distinct, pixelProbeRingFill,
\t\t\t\t\tstatic_cast<double>(lumSwing), switches, maxRun);"""

NEW_A4 = """\t\t\t\t\tstatic_cast<double>(lum), distinct, pixelProbeRingFill,
\t\t\t\t\tstatic_cast<double>(lumSwing), switches, maxRun, shapeTxt, revisits);"""

# gate + verdict text
OLD_A5 = """\t\t\t\tif (pixelProbeRingFill >= 8u && distinct <= 3u && switches >= 3u &&
\t\t\t\t\tpixelProbeFlickerFired < 4u) {"""

NEW_A5 = """\t\t\t\tif (pixelProbeRingFill >= 8u && distinct <= 3u && revisits >= 1u &&
\t\t\t\t\tpixelProbeFlickerFired < 4u) {"""

OLD_A6 = """\t\t\t\t\tSKSE::log::error(\"[PIXEL] FLICKER: the last 8 samples ({:.1f} s) hold only \"
\t\t\t\t\t\t\"{} distinct images AND changed state {} times (longest run {}), so the \"
\t\t\t\t\t\t\"image is coming BACK to what it already showed rather than advancing. \"
\t\t\t\t\t\t\"Brightness swings {:.0f}/255 (min {:.0f} max {:.0f}); the swing is \"
\t\t\t\t\t\t\"reported, not required -- a flicker between two equally bright images \"
\t\t\t\t\t\t\"is still a flicker. A picture that CHANGES is not the same as one that \"
\t\t\t\t\t\t\"ADVANCES, and the change counter cannot tell them apart: every sample \"
\t\t\t\t\t\t\"differs from the previous one while the image cycles a handful of \"
\t\t\t\t\t\t\"states. This is the flicker, measured (v1.27: a one-way transition \"
\t\t\t\t\t\t\"such as the loading screen lighting up does NOT qualify -- it has to \"
\t\t\t\t\t\t\"come back).\",
\t\t\t\t\t\tstatic_cast<double>(pixelProbeRingFill) * 0.5, distinct, switches,
\t\t\t\t\t\tmaxRun, static_cast<double>(lumSwing), static_cast<double>(lumLo),
\t\t\t\t\t\tstatic_cast<double>(lumHi));"""

NEW_A6 = """\t\t\t\t\tSKSE::log::error(\"[PIXEL] FLICKER: the last 8 samples ({:.1f} s) hold only \"
\t\t\t\t\t\t\"{} distinct images and the image RETURNED to a state it had already \"
\t\t\t\t\t\t\"shown {} times (shape=[{}], {} state changes, longest run {}). That is the \"
\t\t\t\t\t\t\"one thing a picture that merely advances can never do: it came back. \"
\t\t\t\t\t\t\"Brightness spans {:.0f}/255 (min {:.0f} max {:.0f}); the swing is \"
\t\t\t\t\t\t\"reported, not required -- a flicker between two equally bright images \"
\t\t\t\t\t\t\"is still a flicker. A picture that CHANGES is not the same as one that \"
\t\t\t\t\t\t\"ADVANCES, and the change counter cannot tell them apart: every sample \"
\t\t\t\t\t\t\"differs from the previous one while the image cycles a handful of \"
\t\t\t\t\t\t\"states. This is the flicker, measured (v1.28: the gate is a revisit, \"
\t\t\t\t\t\t\"so a one-way transition such as the loading screen lighting up or a \"
\t\t\t\t\t\t\"brightness ramp is rejected by construction).\",
\t\t\t\t\t\tstatic_cast<double>(pixelProbeRingFill) * 0.5, distinct, revisits,
\t\t\t\t\t\tshapeTxt, switches, maxRun, static_cast<double>(lumSwing),
\t\t\t\t\t\tstatic_cast<double>(lumLo), static_cast<double>(lumHi));"""

# ---------------------------------------------------------------- C

OLD_C = """\t\t\t\t\tSKSE::log::warn(\"[MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu \"
\t\t\t\t\t\t\"guard is not engaged (menuBlock=0 frames={} blocked={} unblocked={}) - the ladder \"
\t\t\t\t\t\t\"cannot be calibrated while this lasts\",
\t\t\t\t\t\tdebugOk ? 1u : 0u, menuBlockedFrames, menuUnblockedFrames);"""

NEW_C = """\t\t\t\t\t// v1.28: the old text printed `menuBlock=0` as a literal and labelled the
\t\t\t\t\t// next argument `frames=`, but that argument is debugOk, not a frame
\t\t\t\t\t// count -- the line named a quantity it was not printing. This branch is
\t\t\t\t\t// only reachable with menuBlock false, so debugOk here IS dlssgOk.
\t\t\t\t\tSKSE::log::warn(\"[MFG] debug CHECK: Present skips SetDLSSGOptions even though the menu \"
\t\t\t\t\t\t\"guard is not engaged (dlssgOk={} blocked={} unblocked={}) - the ladder \"
\t\t\t\t\t\t\"cannot be calibrated while this lasts\",
\t\t\t\t\t\tdebugOk ? 1u : 0u, menuBlockedFrames, menuUnblockedFrames);"""

# ---------------------------------------------------------------- B (watchdog)

OLD_B1 = """\t\t\t\t\tconst unsigned long long queued = g_queuedDepth.load();"""

NEW_B1 = """\t\t\t\t\t// v1.28 -- the first reading of this stall that does not come from us
\t\t\t\t\t// or from DXGI. frames/fence/lastPr/presentAge all freeze together
\t\t\t\t\t// (03:17 run: 03:16:50.575 -> 03:17:10.861, 20789 ms) which proves
\t\t\t\t\t// the render thread was not inside our code, but says nothing about
\t\t\t\t\t// what the process was doing instead. cpuD is that process's own
\t\t\t\t\t// user+kernel time over this 200 ms slice:
\t\t\t\t\t//   cpuD ~ 0    -> the process is BLOCKED (IO, a lock, a driver
\t\t\t\t\t//                  wait). Nothing is spinning and no stack is hot.
\t\t\t\t\t//   cpuD ~ 200  -> one thread is burning a full core right now.
\t\t\t\t\t//   cpuD > 200  -> more than one thread is, or the slice overran.
\t\t\t\t\t// GetProcessTimes only reads; it cannot perturb the process.
\t\t\t\t\tunsigned long long cpuMs = 0;
\t\t\t\t\t{
\t\t\t\t\t\tFILETIME c{}, e{}, k{}, u{};
\t\t\t\t\t\tif (::GetProcessTimes(::GetCurrentProcess(), &c, &e, &k, &u)) {
\t\t\t\t\t\t\tconst auto toMs = [](const FILETIME& ft) {
\t\t\t\t\t\t\t\treturn (static_cast<unsigned long long>(ft.dwHighDateTime) << 32)
\t\t\t\t\t\t\t\t\t| static_cast<unsigned long long>(ft.dwLowDateTime);
\t\t\t\t\t\t\t};
\t\t\t\t\t\t\tcpuMs = (toMs(k) + toMs(u)) / 10000ull;   // 100 ns ticks -> ms
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t\tstatic unsigned long long s_lastCpuMs = 0;
\t\t\t\t\tconst unsigned long long cpuDelta =
\t\t\t\t\t\t(cpuMs >= s_lastCpuMs) ? (cpuMs - s_lastCpuMs) : 0ull;
\t\t\t\t\ts_lastCpuMs = cpuMs;
\t\t\t\t\tconst unsigned long long queued = g_queuedDepth.load();"""

OLD_B2 = """\t\t\t\t\tstd::fprintf(f, \"[%lld] %02d:%02d:%02d.%03d frames=%llu silent=%lldms \"
\t\t\t\t\t\t\"stage=%s focus=%d fence=%s stim=%llu queued=%llu lastPr=%llu dsync=%llu \"
\t\t\t\t\t\t\"msg=%d alive=%d presentAge=%lldms%s\\n\","""

NEW_B2 = """\t\t\t\t\tstd::fprintf(f, \"[%lld] %02d:%02d:%02d.%03d frames=%llu silent=%lldms \"
\t\t\t\t\t\t\"stage=%s focus=%d fence=%s stim=%llu queued=%llu lastPr=%llu dsync=%llu \"
\t\t\t\t\t\t\"msg=%d alive=%d presentAge=%lldms cpuD=%llums%s\\n\","""

OLD_B3 = """\t\t\t\t\t\t(g_presentEnteredMs.load() > 0)
\t\t\t\t\t\t\t? (nowMs - g_presentEnteredMs.load())
\t\t\t\t\t\t\t: 0LL,"""

NEW_B3 = """\t\t\t\t\t\t(g_presentEnteredMs.load() > 0)
\t\t\t\t\t\t\t? (nowMs - g_presentEnteredMs.load())
\t\t\t\t\t\t\t: 0LL,
\t\t\t\t\t\tcpuDelta,"""

EDITS_SWAP = [
    ("A1  ring-order window + state index", OLD_A1, NEW_A1),
    ("A2  run-length collapse + revisits", OLD_A2, NEW_A2),
    ("A3  print shape=/rev=", OLD_A3, NEW_A3),
    ("A4  print shape=/rev= args", OLD_A4, NEW_A4),
    ("A5  gate uses revisits", OLD_A5, NEW_A5),
    ("A6  verdict text", OLD_A6, NEW_A6),
    ("C   debug CHECK names its argument", OLD_C, NEW_C),
    ("B1  watchdog cpuD= compute", OLD_B1, NEW_B1),
    ("B2  watchdog format string", OLD_B2, NEW_B2),
    ("B3  watchdog args", OLD_B3, NEW_B3),
]

# ---------------------------------------------------------------- ImguiMenu (CRLF, line based)

# CRLF file: the separator inside the anchor must be CRLF, not LF.
GUI_ANCHOR_OLD = ("\t\tif (mult > 1.0f) {\r\n"
                  "\t\t\tif (!s_worldSeen) { s_worldSeen = true; s_worldSince = now; }")

GUI_NEW_LINES = [
    "\t\t// v1.28 -- the clock drawn below was never logged, so 'did the overlay",
    "\t\t// actually appear' could not be answered from any artefact. The 03:17 run",
    "\t\t// released the menu guard at 03:17:24.708 and the player still never pressed",
    "\t\t// a movement key (os=0x0 on all 20 [CAM] PC samples), so before the protocol",
    "\t\t// can be blamed the overlay itself has to be visible in the log. Three edges",
    "\t\t// only: this function runs every frame and must not write a line per frame.",
    "\t\tstatic bool s_worldLogged20 = false;",
    "\t\tif (mult > 1.0f) {",
    "\t\t\tif (!s_worldSeen) {",
    "\t\t\t\ts_worldSeen = true;",
    "\t\t\t\ts_worldSince = now;",
    "\t\t\t\ts_worldLogged20 = false;",
    "\t\t\t\tSKSE::log::info(\"[OVERLAY] world clock started - the runtime just reported \"",
    "\t\t\t\t\t\"mult={:.1f} for the last real frame, so 4x is running now. The second \"",
    "\t\t\t\t\t\"overlay line reads 'KEEP PLAYING, hold W for 10 s'.\",",
    "\t\t\t\t\tstatic_cast<double>(mult));",
    "\t\t\t} else {",
    "\t\t\t\tconst double s =",
    "\t\t\t\t\tduration_cast<duration<double>>(now - s_worldSince).count();",
    "\t\t\t\tif (!s_worldLogged20 && s >= 20.0) {",
    "\t\t\t\t\ts_worldLogged20 = true;",
    "\t\t\t\t\tSKSE::log::info(\"[OVERLAY] world clock reached {:.1f} s - the second overlay \"",
    "\t\t\t\t\t\t\"line now reads 'enough - you can exit now'. This is the point the run \"",
    "\t\t\t\t\t\t\"becomes usable.\", s);",
    "\t\t\t\t}",
    "\t\t\t}",
]


def apply_text(path: pathlib.Path, edits, dry):
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    problems = []
    for label, old, new in edits:
        n = text.count(old)
        if n == 0 and text.count(new) >= 1:
            problems.append(f"{label}: REFUSED - new text already present")
        elif n != 1:
            problems.append(f"{label}: REFUSED - anchor count is {n}, expected 1")
    if problems:
        print(f"--- {path.name}")
        for p in problems:
            print("   ", p)
        return None
    for label, old, new in edits:
        text = text.replace(old, new, 1)
        print(f"    ok  {label}  (+{len(new) - len(old)} chars)")
    if dry:
        return text
    path.write_bytes(text.encode("utf-8"))
    return text


def apply_gui(path: pathlib.Path, dry):
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if "s_worldLogged20" in text:
        print("--- ImguiMenu.cpp\n    REFUSED - s_worldLogged20 already present")
        return None
    n = text.count(GUI_ANCHOR_OLD)
    if n != 1:
        print(f"--- ImguiMenu.cpp\n    REFUSED - anchor count is {n}, expected 1")
        return None
    new_block = "\r\n".join(GUI_NEW_LINES)
    text = text.replace(GUI_ANCHOR_OLD, new_block, 1)
    print(f"    ok  D   overlay world clock logging  (+{len(new_block) - len(GUI_ANCHOR_OLD)} chars)")
    if dry:
        return text
    path.write_bytes(text.encode("utf-8"))
    return text


def main():
    dry = "--apply" not in sys.argv
    print("=== v1.28 %s ===" % ("DRY RUN (nothing written)" if dry else "APPLY"))

    for f in (SWAP, GUI):
        b = f.read_bytes()
        print(f"[eol] {f.name}: CRLF={b.count(bytes([13, 10]))} LF={b.count(bytes([10]))} "
              f"CR={b.count(bytes([13]))} BOM={b[:3] == bytes([239, 187, 191])}")

    out = apply_text(SWAP, EDITS_SWAP, dry)
    gui = apply_gui(GUI, dry)

    if dry:
        print("\nDRY RUN complete - no file written. Re-run with --apply.")
        return
    if out is None or gui is None:
        print("\nREFUSED - nothing written.")
        sys.exit(1)

    # ---- post-check: every new string present, every old anchor gone ----
    print("\n=== post-check ===")
    fails = 0
    raw = SWAP.read_bytes()
    txt = raw.decode("utf-8")
    for label, old, new in EDITS_SWAP:
        # an appended-only edit keeps the old text inside the new one; for those
        # the only honest check is "old no longer stands alone"
        if new not in txt:
            print(f"    FAIL {label}: new text missing")
            fails += 1
        elif old in txt and old not in new:
            print(f"    FAIL {label}: old anchor still present")
            fails += 1
        else:
            print(f"    ok   {label}")
    gt = GUI.read_bytes().decode("utf-8")
    if "s_worldLogged20" not in gt:
        print("    FAIL D: new text missing")
        fails += 1
    elif GUI_ANCHOR_OLD in gt:
        print("    FAIL D: old anchor still present")
        fails += 1
    else:
        print("    ok   D   overlay world clock logging")
    for f in (SWAP, GUI):
        b = f.read_bytes()
        print(f"[eol] {f.name}: CRLF={b.count(bytes([13, 10]))} LF={b.count(bytes([10]))} "
              f"CR={b.count(bytes([13]))}")
    print(f"\n=== {'POST-CHECK FAILED' if fails else 'POST-CHECK OK'} ===")
    if fails:
        sys.exit(1)


if __name__ == "__main__":
    main()
