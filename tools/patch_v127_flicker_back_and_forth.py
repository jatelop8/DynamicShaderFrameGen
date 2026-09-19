#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.27 -- two edits, both aimed at the same wall.

A. The flicker verdict of v1.26 fired twice on the 02:39 run and BOTH were false.
   The window it saw was [black 0.0] [black 0.0] [bright 104.0] x6 -- a single
   monotonic transition (the loading screen going from black to lit), not an
   oscillation. The predicate was `distinct <= 3 && swing > 40`, and a one-way
   change satisfies both: it lands on a small number of states and it swings far.
   An oscillation has to come BACK. So the predicate becomes "the state changed
   at least 3 times inside the window" (A->B->A->B), and the swing term is
   dropped: a flicker between two nearly equally bright images is still a flicker,
   and requiring a 40/255 brightness step would miss it.
   The PIXEL line and the FLICKER line both now print the switch count and the
   longest run, so the raw shape of the window is in the log even when no verdict
   fires.

B. The overlay gets a world-phase clock.
   Five consecutive runs ended 2.1 / 3.0 / 3.2 / 2.5 / 6.1 s after the guard
   released, so the one question every instrument here exists to answer ("does the
   world respond, and does the picture advance?") has never had a world phase long
   enough to answer it. The player cannot read this log; they can read the overlay.
   mult>1 is measured (the runtime reports it via slDLSSGGetState), so its rising
   edge means "4x is running now" -- a real event, not another name for "the guard
   is up".

Anchors: every one must appear exactly once, or nothing is written.
Line endings: DX12SwapChain.cpp is pure LF, ImguiMenu.cpp is pure CRLF. Taken from
the files, not from memory.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
APPLY = "--apply" in sys.argv

LF = "\n"
CRLF = "\r\n"

# ----------------------------------------------------------------------------
# A. DX12SwapChain.cpp -- make the flicker verdict require a return trip
# ----------------------------------------------------------------------------
A1_OLD = (
    "\t\t\t\tconst float lumSwing = (pixelProbeRingFill >= 8u) ? (lumHi - lumLo) : 0.0f;" + LF
)
A1_NEW = (
    "\t\t\t\tconst float lumSwing = (pixelProbeRingFill >= 8u) ? (lumHi - lumLo) : 0.0f;" + LF +
    "" + LF +
    "\t\t\t\t// v1.27 -- how many times the window changed state, and the longest run of" + LF +
    "\t\t\t\t// one state. `distinct <= 3` plus a wide brightness swing is NOT enough on" + LF +
    "\t\t\t\t// its own, and the 02:39 run proved it: the first two FLICKER reports of" + LF +
    "\t\t\t\t// v1.26 both saw [0.0] [0.0] [104.0] x6 -- black, black, then lit for the" + LF +
    "\t\t\t\t// rest of the window. That is a single transition (the loading screen" + LF +
    "\t\t\t\t// lighting up), it lands on 2 distinct images, it swings 104/255, and it" + LF +
    "\t\t\t\t// is not an oscillation. An oscillation has to come BACK, so require the" + LF +
    "\t\t\t\t// state to change at least three times inside the window (A->B->A->B)." + LF +
    "\t\t\t\t// The swing is printed but no longer gates: a flicker between two nearly" + LF +
    "\t\t\t\t// equally bright images is still a flicker." + LF +
    "\t\t\t\tstd::uint32_t switches = 0;" + LF +
    "\t\t\t\tstd::uint32_t maxRun = 0;" + LF +
    "\t\t\t\tstd::uint32_t runLen = 0;" + LF +
    "\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {" + LF +
    "\t\t\t\t\tif (i > 0u && pixelProbeRingHash[i] != pixelProbeRingHash[i - 1u]) {" + LF +
    "\t\t\t\t\t\t++switches;" + LF +
    "\t\t\t\t\t\trunLen = 0;" + LF +
    "\t\t\t\t\t}" + LF +
    "\t\t\t\t\t++runLen;" + LF +
    "\t\t\t\t\tif (runLen > maxRun)" + LF +
    "\t\t\t\t\t\tmaxRun = runLen;" + LF +
    "\t\t\t\t}" + LF
)

A2_OLD = (
    "\t\t\t\tif (pixelProbeRingFill >= 8u && distinct <= 3u && lumSwing > 40.0f &&" + LF +
    "\t\t\t\t\tpixelProbeFlickerFired < 4u) {" + LF
)
A2_NEW = (
    "\t\t\t\tif (pixelProbeRingFill >= 8u && distinct <= 3u && switches >= 3u &&" + LF +
    "\t\t\t\t\tpixelProbeFlickerFired < 4u) {" + LF
)

A3_OLD = (
    "\t\t\t\t\t\"lum={:.2f} seen={}/{} swing={:.1f}\"," + LF
)
A3_NEW = (
    "\t\t\t\t\t\"lum={:.2f} seen={}/{} swing={:.1f} sw={} maxRun={}\"," + LF
)

A4_OLD = (
    "\t\t\t\t\tstatic_cast<double>(lum), distinct, pixelProbeRingFill," + LF +
    "\t\t\t\t\tstatic_cast<double>(lumSwing));" + LF
)
A4_NEW = (
    "\t\t\t\t\tstatic_cast<double>(lum), distinct, pixelProbeRingFill," + LF +
    "\t\t\t\t\tstatic_cast<double>(lumSwing), switches, maxRun);" + LF
)

A5_OLD = (
    "\t\t\t\t\tSKSE::log::error(\"[PIXEL] FLICKER: the last 8 samples ({:.1f} s) contain only \"" + LF +
    "\t\t\t\t\t\t\"{} distinct images while the block's brightness swings {:.0f}/255 \"" + LF +
    "\t\t\t\t\t\t\"(min {:.0f} max {:.0f}). A picture that CHANGES is not the same as one \"" + LF +
    "\t\t\t\t\t\t\"that ADVANCES, and the changed counter cannot tell them apart: every \"" + LF +
    "\t\t\t\t\t\t\"sample differs from the previous one and the image is still cycling \"" + LF +
    "\t\t\t\t\t\t\"through a handful of states. This is the flicker, measured.\"," + LF +
    "\t\t\t\t\t\tstatic_cast<double>(pixelProbeRingFill) * 0.5, distinct," + LF +
    "\t\t\t\t\t\tstatic_cast<double>(lumSwing), static_cast<double>(lumLo)," + LF +
    "\t\t\t\t\t\tstatic_cast<double>(lumHi));" + LF
)
A5_NEW = (
    "\t\t\t\t\tSKSE::log::error(\"[PIXEL] FLICKER: the last 8 samples ({:.1f} s) hold only \"" + LF +
    "\t\t\t\t\t\t\"{} distinct images AND changed state {} times (longest run {}), so the \"" + LF +
    "\t\t\t\t\t\t\"image is coming BACK to what it already showed rather than advancing. \"" + LF +
    "\t\t\t\t\t\t\"Brightness swings {:.0f}/255 (min {:.0f} max {:.0f}); the swing is \"" + LF +
    "\t\t\t\t\t\t\"reported, not required -- a flicker between two equally bright images \"" + LF +
    "\t\t\t\t\t\t\"is still a flicker. A picture that CHANGES is not the same as one that \"" + LF +
    "\t\t\t\t\t\t\"ADVANCES, and the change counter cannot tell them apart: every sample \"" + LF +
    "\t\t\t\t\t\t\"differs from the previous one while the image cycles a handful of \"" + LF +
    "\t\t\t\t\t\t\"states. This is the flicker, measured (v1.27: a one-way transition \"" + LF +
    "\t\t\t\t\t\t\"such as the loading screen lighting up does NOT qualify -- it has to \"" + LF +
    "\t\t\t\t\t\t\"come back).\"," + LF +
    "\t\t\t\t\t\tstatic_cast<double>(pixelProbeRingFill) * 0.5, distinct, switches," + LF +
    "\t\t\t\t\t\tmaxRun, static_cast<double>(lumSwing), static_cast<double>(lumLo)," + LF +
    "\t\t\t\t\t\tstatic_cast<double>(lumHi));" + LF
)

FLICKER_MARKER = "v1.27 -- how many times the window changed state"

# ----------------------------------------------------------------------------
# B. ImguiMenu.cpp -- a world-phase clock on the overlay
# ----------------------------------------------------------------------------
B1_OLD = (
    "\t\tchar buf[64];" + CRLF +
    "\t\tif (mult > 1.0f)" + CRLF +
    "\t\t\tstd::snprintf(buf, sizeof(buf), \"%.0f FPS  [%.0f real x%.0f reported]\"," + CRLF +
    "\t\t\t\ts_fps * mult, s_fps, mult);" + CRLF +
    "\t\telse" + CRLF +
    "\t\t\tstd::snprintf(buf, sizeof(buf), \"%.0f FPS%s\", s_fps * mult, tag);" + CRLF
)
B1_NEW = (
    "\t\tchar buf[64];" + CRLF +
    "\t\tif (mult > 1.0f)" + CRLF +
    "\t\t\tstd::snprintf(buf, sizeof(buf), \"%.0f FPS  [%.0f real x%.0f reported]\"," + CRLF +
    "\t\t\t\ts_fps * mult, s_fps, mult);" + CRLF +
    "\t\telse" + CRLF +
    "\t\t\tstd::snprintf(buf, sizeof(buf), \"%.0f FPS%s\", s_fps * mult, tag);" + CRLF +
    "" + CRLF +
    "\t\t// v1.27 -- how long 4x has actually been running this visit." + CRLF +
    "\t\t//" + CRLF +
    "\t\t// Five consecutive runs ended 2.1 / 3.0 / 3.2 / 2.5 / 6.1 s after the guard" + CRLF +
    "\t\t// released, so the one question every instrument in this project exists to" + CRLF +
    "\t\t// answer -- does the world respond, and does the picture advance -- has never" + CRLF +
    "\t\t// had a world phase long enough to answer it. The player does not read the log" + CRLF +
    "\t\t// and cannot be blamed for exiting early; they can read the overlay." + CRLF +
    "\t\t//" + CRLF +
    "\t\t// mult > 1 is MEASURED: it is what the runtime reported for the last real" + CRLF +
    "\t\t// frame, so its rising edge means \"4x is running now\" and not another name" + CRLF +
    "\t\t// for \"the menu guard is up\". It is also the only edge in this overlay that" + CRLF +
    "\t\t// comes from the runtime rather than from us." + CRLF +
    "\t\tstatic bool s_worldSeen = false;" + CRLF +
    "\t\tstatic steady_clock::time_point s_worldSince{};" + CRLF +
    "\t\tif (mult > 1.0f) {" + CRLF +
    "\t\t\tif (!s_worldSeen) { s_worldSeen = true; s_worldSince = now; }" + CRLF +
    "\t\t} else {" + CRLF +
    "\t\t\ts_worldSeen = false;" + CRLF +
    "\t\t}" + CRLF +
    "\t\tchar buf2[80];" + CRLF +
    "\t\tbuf2[0] = '\\0';" + CRLF +
    "\t\tif (s_worldSeen) {" + CRLF +
    "\t\t\tconst double secs =" + CRLF +
    "\t\t\t\tduration_cast<duration<double>>(now - s_worldSince).count();" + CRLF +
    "\t\t\tstd::snprintf(buf2, sizeof(buf2), \"%.1f s with 4x - %s\", secs," + CRLF +
    "\t\t\t\t(secs < 20.0) ? \"KEEP PLAYING, hold W for 10 s\"" + CRLF +
    "\t\t\t\t              : \"enough - you can exit now\");" + CRLF +
    "\t\t}" + CRLF
)

B2_OLD = (
    "\t\tImDrawList* dl = ImGui::GetBackgroundDrawList();" + CRLF +
    "\t\t// black outline around the white text (bold look + readable on any background)" + CRLF +
    "\t\tfor (int dx = -2; dx <= 2; ++dx)" + CRLF +
    "\t\t\tfor (int dy = -2; dy <= 2; ++dy)" + CRLF +
    "\t\t\t\tif (dx * dx + dy * dy <= 8)" + CRLF +
    "\t\t\t\t\tdl->AddText(font, size, ImVec2(pos.x + dx, pos.y + dy)," + CRLF +
    "\t\t\t\t\t\tIM_COL32(0, 0, 0, 235), buf);" + CRLF +
    "\t\tdl->AddText(font, size, pos, IM_COL32(255, 255, 255, 255), buf);" + CRLF
)
B2_NEW = (
    "\t\tImDrawList* dl = ImGui::GetBackgroundDrawList();" + CRLF +
    "\t\t// black outline around the white text (bold look + readable on any background)" + CRLF +
    "\t\tfor (int dx = -2; dx <= 2; ++dx)" + CRLF +
    "\t\t\tfor (int dy = -2; dy <= 2; ++dy)" + CRLF +
    "\t\t\t\tif (dx * dx + dy * dy <= 8)" + CRLF +
    "\t\t\t\t\tdl->AddText(font, size, ImVec2(pos.x + dx, pos.y + dy)," + CRLF +
    "\t\t\t\t\t\tIM_COL32(0, 0, 0, 235), buf);" + CRLF +
    "\t\tdl->AddText(font, size, pos, IM_COL32(255, 255, 255, 255), buf);" + CRLF +
    "" + CRLF +
    "\t\t// v1.27: the world-phase clock, same outline treatment, smaller and amber so" + CRLF +
    "\t\t// it cannot be mistaken for the frame-rate line above it." + CRLF +
    "\t\tif (buf2[0] != '\\0') {" + CRLF +
    "\t\t\tconst float size2 = size * 0.55f;" + CRLF +
    "\t\t\tconst ImVec2 ts2 = font->CalcTextSizeA(size2, FLT_MAX, 0.0f, buf2);" + CRLF +
    "\t\t\tconst ImVec2 pos2(disp.x - ts2.x - 26.0f, pos.y + ts.y + 8.0f);" + CRLF +
    "\t\t\tfor (int dx = -2; dx <= 2; ++dx)" + CRLF +
    "\t\t\t\tfor (int dy = -2; dy <= 2; ++dy)" + CRLF +
    "\t\t\t\t\tif (dx * dx + dy * dy <= 8)" + CRLF +
    "\t\t\t\t\t\tdl->AddText(font, size2, ImVec2(pos2.x + dx, pos2.y + dy)," + CRLF +
    "\t\t\t\t\t\t\tIM_COL32(0, 0, 0, 235), buf2);" + CRLF +
    "\t\t\tdl->AddText(font, size2, pos2, IM_COL32(255, 220, 110, 255), buf2);" + CRLF +
    "\t\t}" + CRLF
)

WORLD_MARKER = "v1.27 -- how long 4x has actually been running this visit"

FILES = [
    ("src/DX12SwapChain.cpp", LF, [
        ("A1 switch counters", A1_OLD, A1_NEW, FLICKER_MARKER),
        ("A2 predicate", A2_OLD, A2_NEW, None),
        ("A3 pixel line format", A3_OLD, A3_NEW, None),
        ("A4 pixel line args", A4_OLD, A4_NEW, None),
        ("A5 flicker text", A5_OLD, A5_NEW, None),
    ]),
    ("src/ImguiMenu.cpp", CRLF, [
        ("B1 world clock", B1_OLD, B1_NEW, WORLD_MARKER),
        ("B2 world clock draw", B2_OLD, B2_NEW, None),
    ]),
]


def main():
    plan = []          # (rel, label, new_text, path, decoded_before)
    failed = False
    for rel, eol, edits in FILES:
        p = ROOT / rel
        raw = p.read_bytes()
        text = raw.decode("utf-8")
        # idempotence: an insert-type anchor still matches after it has been applied,
        # so the marker has to be tested first (L51).
        for label, old, new, marker in edits:
            if marker is not None and marker in text:
                print(f"REFUSED [{rel}] {label}: already applied (marker present)")
                failed = True
        cur = text
        for label, old, new, marker in edits:
            n = cur.count(old)
            if n != 1:
                print(f"REFUSED [{rel}] {label}: anchor count == {n} (must be 1)")
                failed = True
                continue
            cur = cur.replace(old, new, 1)
        plan.append((rel, cur, p))
    if failed:
        print("\nREFUSED, nothing written")
        return 2

    for rel, new_text, p in plan:
        print(f"  would write {rel}: {len(new_text.encode('utf-8'))} bytes (was {len(p.read_bytes())})")

    if not APPLY:
        print("\nDRY RUN - pass --apply to write")
        return 0

    for rel, new_text, p in plan:
        p.write_bytes(new_text.encode("utf-8"))
        print(f"wrote {rel}: {len(new_text.encode('utf-8'))} bytes")

    # post-conditions: each file must now contain its new text exactly once, and
    # the ones that are replacements must no longer contain the old anchor.
    for (rel, new_text, p), (rel2, eol, edits) in zip(plan, FILES):
        raw = p.read_bytes().decode("utf-8")
        for label, old, new, marker in edits:
            if raw.count(new) != 1:
                print(f"POST-CHECK FAILED: new block not present exactly once in {rel} [{label}]")
                return 3
            if marker is None and old in raw and old not in new:
                # `old not in new` excludes the append-type edits (B1/B2), where the
                # new text is the old text plus more. Testing "old is gone" on those
                # reports a failure for every correct application (L51 again).
                print(f"POST-CHECK FAILED: old anchor still present in {rel} [{label}]")
                return 3
    print("post-check OK: every new block present exactly once; every replaced anchor gone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
