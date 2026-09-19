#!/usr/bin/env python3
"""v1.26 -- measure the flicker, and measure the multiplier instead of computing it.

Two changes, both instruments, both driven by the 02:25 run (v1.25's first run).

A. PixelProbeTick: the probe can only see CHANGE, and a flicker is not a change.
   The 02:25 run's world phase reads chg=1 on 7 of 7 samples while the camera is
   provably static (clipDev=0.000061, eyeD=0.00) -- so the existing probe scores a
   cycling image as healthy. The probe now also averages the sampled block's bytes
   (lum) and keeps the last 8 (hash, lum) pairs. A picture that changes is not the
   same as one that advances: if 8 consecutive samples contain only 2-3 distinct
   images AND the block's brightness swings by more than 40/255, the image is
   oscillating through a small set of states -- a flicker, which the changed
   counter structurally cannot see.

B. FPS probe: print DXGI's OWN flip count divided by our own Present count over the
   same 2 s window. On the 02:25 run the watchdog's lastPr/ frames pair read 1.00
   across the whole loading screen and exactly 4.00 from the frame the guard
   released onwards. That is a direct measurement of the multiplier by a component
   neither the plugin nor the second DLSS-G driver controls, and it is the number
   this project has been calling "computed" for twenty versions.

Also: the FSR3 branch now records GetLastPresentCount too, so the same measurement
exists on the only provider we have ever seen a run stay alive on.

Anchors: count must be exactly 1 or the script refuses and writes nothing.
Insert-type anchors carry an idempotence marker (ledger L51).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPLY = "--apply" in sys.argv

CRLF = "\r\n"

FILES = [
    (
        "src/DX12SwapChain.h",
        CRLF,
        [
            (
                "H1 probe flicker state",
                "\t\tstd::uint32_t pixelProbeMovedDuringStreak = 0;" + CRLF
                + "\t\tstd::uint64_t pixelProbeArmedMs = 0;" + CRLF,
                "\t\tstd::uint32_t pixelProbeMovedDuringStreak = 0;" + CRLF
                + "\t\t// v1.26 -- oscillation state. A flicker is neither a change nor a freeze:" + CRLF
                + "\t\t// the presented image cycles through a small set of states, so the hash" + CRLF
                + "\t\t// differs on every sample and the \"changed\" counter calls it healthy." + CRLF
                + "\t\t// What separates it from real content is that the set stays tiny and that" + CRLF
                + "\t\t// its brightness swings. 8 samples at 2 Hz = a 4 s window." + CRLF
                + "\t\tstd::uint64_t pixelProbeRingHash[8] = {};" + CRLF
                + "\t\tfloat pixelProbeRingLum[8] = {};" + CRLF
                + "\t\tstd::uint32_t pixelProbeRingFill = 0;" + CRLF
                + "\t\tstd::uint32_t pixelProbeRingAt = 0;" + CRLF
                + "\t\tfloat pixelProbeLum = 0.0f;" + CRLF
                + "\t\tstd::uint32_t pixelProbeFlickerFired = 0;" + CRLF
                + "\t\tstd::uint64_t pixelProbeArmedMs = 0;" + CRLF,
                None,
            ),
        ],
    ),
    (
        "src/DX12SwapChain.cpp",
        "\n",
        [
            (
                "C1 luminance alongside the hash",
                "\t\t\t\tstd::uint64_t h = 1469598103934665603ull;   // FNV-1a offset basis\n"
                "\t\t\t\tconst auto* rows = static_cast<const std::uint8_t*>(ms.pData);\n"
                "\t\t\t\tfor (UINT y = 0; y < pixelProbeHeight; ++y) {\n"
                "\t\t\t\t\tconst auto* row = rows + static_cast<std::size_t>(y) * ms.RowPitch;\n"
                "\t\t\t\t\tfor (std::size_t x = 0; x < ms.RowPitch; ++x) {\n"
                "\t\t\t\t\t\th ^= row[x];\n"
                "\t\t\t\t\t\th *= 1099511628211ull;\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n",
                "\t\t\t\tstd::uint64_t h = 1469598103934665603ull;   // FNV-1a offset basis\n"
                "\t\t\t\t// v1.26: the block's mean byte alongside the hash. The hash answers" "\n"
                "\t\t\t\t// \"did it change\"; the mean answers \"did it get brighter or darker\"," "\n"
                "\t\t\t\t// and an oscillation needs the second one. RowPitch padding is stable," "\n"
                "\t\t\t\t// so it dilutes the mean by a fixed amount and cannot fake a swing." "\n"
                "\t\t\t\tstd::uint64_t lumSum = 0;\n"
                "\t\t\t\tstd::uint64_t lumN = 0;\n"
                "\t\t\t\tconst auto* rows = static_cast<const std::uint8_t*>(ms.pData);\n"
                "\t\t\t\tfor (UINT y = 0; y < pixelProbeHeight; ++y) {\n"
                "\t\t\t\t\tconst auto* row = rows + static_cast<std::size_t>(y) * ms.RowPitch;\n"
                "\t\t\t\t\tfor (std::size_t x = 0; x < ms.RowPitch; ++x) {\n"
                "\t\t\t\t\t\th ^= row[x];\n"
                "\t\t\t\t\t\th *= 1099511628211ull;\n"
                "\t\t\t\t\t\tlumSum += row[x];\n"
                "\t\t\t\t\t\t++lumN;\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n"
                "\t\t\t\tconst float lum = lumN ? static_cast<float>(lumSum) / static_cast<float>(lumN) : 0.0f;\n",
                "v1.26: the block's mean byte alongside the hash",
            ),
            (
                "C2 ring the last 8 (hash, lum) and count distinct",
                "\t\t\t\tpixelProbeLastHash = h;\n"
                "\n"
                "\t\t\t\t// v1.23: a streak of identical frames only means \"frozen\" if the camera\n",
                "\t\t\t\tpixelProbeLastHash = h;\n"
                "\n"
                "\t\t\t\t// v1.26 -- oscillation window. `changed` is incremented whenever this\n"
                "\t\t\t\t// sample differs from the previous one, so an image that alternates\n"
                "\t\t\t\t// A,B,A,B scores a change on every single sample and reads as the\n"
                "\t\t\t\t// healthiest possible picture. The window is what tells the two apart:\n"
                "\t\t\t\t// real content advances through many states, a flicker cycles a few.\n"
                "\t\t\t\tpixelProbeLum = lum;\n"
                "\t\t\t\tpixelProbeRingHash[pixelProbeRingAt] = h;\n"
                "\t\t\t\tpixelProbeRingLum[pixelProbeRingAt] = lum;\n"
                "\t\t\t\tpixelProbeRingAt = (pixelProbeRingAt + 1u) % 8u;\n"
                "\t\t\t\tif (pixelProbeRingFill < 8u)\n"
                "\t\t\t\t\t++pixelProbeRingFill;\n"
                "\t\t\t\tstd::uint32_t distinct = 0;\n"
                "\t\t\t\t{\n"
                "\t\t\t\t\tstd::uint64_t seenHash[8] = {};\n"
                "\t\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {\n"
                "\t\t\t\t\t\tbool dup = false;\n"
                "\t\t\t\t\t\tfor (std::uint32_t j = 0; j < distinct; ++j)\n"
                "\t\t\t\t\t\t\tif (seenHash[j] == pixelProbeRingHash[i]) { dup = true; break; }\n"
                "\t\t\t\t\t\tif (!dup)\n"
                "\t\t\t\t\t\t\tseenHash[distinct++] = pixelProbeRingHash[i];\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n"
                "\t\t\t\tfloat lumLo = 1.0e9f;\n"
                "\t\t\t\tfloat lumHi = -1.0e9f;\n"
                "\t\t\t\tfor (std::uint32_t i = 0; i < pixelProbeRingFill; ++i) {\n"
                "\t\t\t\t\tif (pixelProbeRingLum[i] < lumLo) lumLo = pixelProbeRingLum[i];\n"
                "\t\t\t\t\tif (pixelProbeRingLum[i] > lumHi) lumHi = pixelProbeRingLum[i];\n"
                "\t\t\t\t}\n"
                "\t\t\t\tconst float lumSwing = (pixelProbeRingFill >= 8u) ? (lumHi - lumLo) : 0.0f;\n"
                "\n"
                "\t\t\t\t// v1.23: a streak of identical frames only means \"frozen\" if the camera\n",
                "v1.26 -- oscillation window",
            ),
            (
                "C3 sample line carries lum/seen/swing",
                "\t\t\t\tSKSE::log::info(\"[PIXEL] #{} hash={:016X} chg={} streak={} clipDev={:.6f} movedThisStreak={} \"\n"
                "\t\t\t\t\t\"changed={} unchanged={} maxStreak={} dropped={}\",\n"
                "\t\t\t\t\tpixelProbeSamples, h, changed ? 1 : 0, pixelProbeStreak, static_cast<double>(cd),\n"
                "\t\t\t\t\tpixelProbeMovedDuringStreak, pixelProbeChanged, pixelProbeUnchanged,\n"
                "\t\t\t\t\tpixelProbeMaxStreak, pixelProbeDropped);\n",
                "\t\t\t\tSKSE::log::info(\"[PIXEL] #{} hash={:016X} chg={} streak={} clipDev={:.6f} movedThisStreak={} \"\n"
                "\t\t\t\t\t\"changed={} unchanged={} maxStreak={} dropped={} \"\n"
                "\t\t\t\t\t\"lum={:.2f} seen={}/{} swing={:.1f}\",\n"
                "\t\t\t\t\tpixelProbeSamples, h, changed ? 1 : 0, pixelProbeStreak, static_cast<double>(cd),\n"
                "\t\t\t\t\tpixelProbeMovedDuringStreak, pixelProbeChanged, pixelProbeUnchanged,\n"
                "\t\t\t\t\tpixelProbeMaxStreak, pixelProbeDropped,\n"
                "\t\t\t\t\tstatic_cast<double>(lum), distinct, pixelProbeRingFill,\n"
                "\t\t\t\t\tstatic_cast<double>(lumSwing));\n",
                None,
            ),
            (
                "C4 the flicker verdict",
                "\t\t\t\t\t\t\tpixelProbeStreak, pixelProbeMovedDuringStreak);\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n",
                "\t\t\t\t\t\t\tpixelProbeStreak, pixelProbeMovedDuringStreak);\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t}\n"
                "\n"
                "\t\t\t\t// v1.26 -- the flicker verdict. This one needs no input and no camera\n"
                "\t\t\t\t// motion, which is the point: the input witness has read INPUT_NONE on\n"
                "\t\t\t\t// every movement key in every run since it was added, so a verdict that\n"
                "\t\t\t\t// depends on the player walking has never once been reachable. What the\n"
                "\t\t\t\t// player actually reports is a picture that flickers, and a picture that\n"
                "\t\t\t\t// flickers is exactly what the change counter scores as healthy.\n"
                "\t\t\t\tif (pixelProbeRingFill >= 8u && distinct <= 3u && lumSwing > 40.0f &&\n"
                "\t\t\t\t\tpixelProbeFlickerFired < 4u) {\n"
                "\t\t\t\t\t++pixelProbeFlickerFired;\n"
                "\t\t\t\t\tSKSE::log::error(\"[PIXEL] FLICKER: the last 8 samples ({:.1f} s) contain only \"\n"
                "\t\t\t\t\t\t\"{} distinct images while the block's brightness swings {:.0f}/255 \"\n"
                "\t\t\t\t\t\t\"(min {:.0f} max {:.0f}). A picture that CHANGES is not the same as one \"\n"
                "\t\t\t\t\t\t\"that ADVANCES, and the changed counter cannot tell them apart: every \"\n"
                "\t\t\t\t\t\t\"sample differs from the previous one and the image is still cycling \"\n"
                "\t\t\t\t\t\t\"through a handful of states. This is the flicker, measured.\",\n"
                "\t\t\t\t\t\tstatic_cast<double>(pixelProbeRingFill) * 0.5, distinct,\n"
                "\t\t\t\t\t\tstatic_cast<double>(lumSwing), static_cast<double>(lumLo),\n"
                "\t\t\t\t\t\tstatic_cast<double>(lumHi));\n"
                "\t\t\t\t\tSKSE::log::info(\"[PIXEL] FLICKER window (oldest first): \"\n"
                "\t\t\t\t\t\t\"[{:016X} {:.1f}] [{:016X} {:.1f}] [{:016X} {:.1f}] [{:016X} {:.1f}] \"\n"
                "\t\t\t\t\t\t\"[{:016X} {:.1f}] [{:016X} {:.1f}] [{:016X} {:.1f}] [{:016X} {:.1f}]\",\n"
                "\t\t\t\t\t\tpixelProbeRingHash[(pixelProbeRingAt + 0u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 0u) % 8u]),\n"
                "\t\t\t\t\t\tpixelProbeRingHash[(pixelProbeRingAt + 1u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 1u) % 8u]),\n"
                "\t\t\t\t\t\tpixelProbeRingHash[(pixelProbeRingAt + 2u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 2u) % 8u]),\n"
                "\t\t\t\t\t\tpixelProbeRingHash[(pixelProbeRingAt + 3u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 3u) % 8u]),\n"
                "\t\t\t\t\t\tpixelProbeRingHash[(pixelProbeRingAt + 4u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 4u) % 8u]),\n"
                "\t\t\t\t\t\tpixelProbeRingHash[(pixelProbeRingAt + 5u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 5u) % 8u]),\n"
                "\t\t\t\t\t\tpixelProbeRingHash[(pixelProbeRingAt + 6u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 6u) % 8u]),\n"
                "\t\t\t\t\t\tpixelProbeRingHash[(pixelProbeRingAt + 7u) % 8u], static_cast<double>(pixelProbeRingLum[(pixelProbeRingAt + 7u) % 8u]));\n"
                "\t\t\t\t}\n",
                "[PIXEL] FLICKER: the last 8 samples",
            ),
            (
                "C5 flip counter on the FSR3 branch too",
                "\t\tconst HRESULT hrPresentFsr = swapChain->Present(1, Flags);\n"
                "\t\tif (hrPresentFsr != DXGI_ERROR_WAS_STILL_DRAWING)\n"
                "\t\t\tDX::ThrowIfFailed(hrPresentFsr);\n"
                "\t\tGet().streamline.PresentMarkerEnd();\n",
                "\t\tconst HRESULT hrPresentFsr = swapChain->Present(1, Flags);\n"
                "\t\tif (hrPresentFsr != DXGI_ERROR_WAS_STILL_DRAWING)\n"
                "\t\t\tDX::ThrowIfFailed(hrPresentFsr);\n"
                "\t\t// v1.26: the DLSS-G branch has recorded GetLastPresentCount since v0.74; this\n"
                "\t\t// branch never did, so on FSR3 -- the only provider any run has stayed alive\n"
                "\t\t// on -- the one measurement that does not depend on the runtime's own report\n"
                "\t\t// was unavailable.\n"
                "\t\t{\n"
                "\t\t\tUINT pc = 0;\n"
                "\t\t\tif (SUCCEEDED(swapChain->GetLastPresentCount(&pc)))\n"
                "\t\t\t\tg_lastPresentCount.store(pc);\n"
                "\t\t}\n"
                "\t\tGet().streamline.PresentMarkerEnd();\n",
                "this\n\t\t// branch never did, so on FSR3",
            ),
            (
                "C6 FLIPS per real frame, measured",
                "\t\t\t\tprobeFrames = 0;\n"
                "\t\t\t\tprobeLast = probeNow;\n",
                "\t\t\t\tprobeFrames = 0;\n"
                "\t\t\t\tprobeLast = probeNow;\n"
                "\n"
                "\t\t\t\t// v1.26 -- measured, not computed. DXGI keeps its own present counter for\n"
                "\t\t\t\t// the swap chain, so the ratio of ITS advance to OURS over the same\n"
                "\t\t\t\t// window is the number of flips the chain really did per real frame --\n"
                "\t\t\t\t// from a component neither the plugin nor the second DLSS-G driver in\n"
                "\t\t\t\t// this process controls. On the 02:25 run the watchdog's lastPr/frames\n"
                "\t\t\t\t// pair read 1.00 across the entire loading screen and exactly 4.00 from\n"
                "\t\t\t\t// the frame the guard released onwards. Every other multiplier number\n"
                "\t\t\t\t// this project prints is either our request or the runtime's report.\n"
                "\t\t\t\t{\n"
                "\t\t\t\t\tstatic unsigned long long s_lastFlips = 0;\n"
                "\t\t\t\t\tstatic unsigned long long s_lastFrames = 0;\n"
                "\t\t\t\t\tstatic bool s_haveFlipBase = false;\n"
                "\t\t\t\t\tconst unsigned long long flips = g_lastPresentCount.load();\n"
                "\t\t\t\t\tconst unsigned long long fr = static_cast<unsigned long long>(frameCounter.load());\n"
                "\t\t\t\t\tif (s_haveFlipBase && fr > s_lastFrames && flips > s_lastFlips) {\n"
                "\t\t\t\t\t\tSKSE::log::info(\"[FrameGen] FLIPS per real frame = {:.2f} \"\n"
                "\t\t\t\t\t\t\t\"(DXGI lastPresentCount {} -> {}, our Present {} -> {}) - DXGI's own \"\n"
                "\t\t\t\t\t\t\t\"counter, not the runtime's report and not real*mult\",\n"
                "\t\t\t\t\t\t\tstatic_cast<double>(flips - s_lastFlips) / static_cast<double>(fr - s_lastFrames),\n"
                "\t\t\t\t\t\t\ts_lastFlips, flips, s_lastFrames, fr);\n"
                "\t\t\t\t\t}\n"
                "\t\t\t\t\ts_lastFlips = flips;\n"
                "\t\t\t\t\ts_lastFrames = fr;\n"
                "\t\t\t\t\ts_haveFlipBase = true;\n"
                "\t\t\t\t}\n",
                "[FrameGen] FLIPS per real frame",
            ),
        ],
    ),
]


def main():
    plan = []
    for rel, eol, edits in FILES:
        p = ROOT / rel
        text = p.read_bytes().decode("utf-8")
        for label, old, new, marker in edits:
            if marker is not None and marker in text:
                print(f"REFUSED [{rel}] {label}: already applied (marker present)")
                return 2
            n = text.count(old)
            if n != 1:
                print(f"REFUSED [{rel}] {label}: anchor count == {n} (must be 1)")
                return 2
            plan.append((rel, label, old, new))

    for rel, label, *_ in plan:
        print(f"  would edit {rel}: {label}")

    if not APPLY:
        print("\nDRY RUN - pass --apply to write")
        return 0

    byFile = {}
    for rel, eol, edits in FILES:
        p = ROOT / rel
        text = p.read_bytes().decode("utf-8")
        for label, old, new, marker in edits:
            text = text.replace(old, new, 1)
        byFile[rel] = (p, eol, text)

    for rel, (p, eol, text) in byFile.items():
        data = text.encode("utf-8")
        if eol == CRLF and b"\n" in data.replace(b"\r\n", b""):
            print(f"REFUSED [{rel}]: a bare LF survived in a CRLF file")
            return 3
        p.write_bytes(data)
        print(f"wrote {rel}: {len(data)} bytes")

    print("\npost-check:")
    for rel, eol, edits in FILES:
        raw = (ROOT / rel).read_bytes().decode("utf-8")
        for label, old, new, marker in edits:
            if marker is not None:
                if marker not in raw:
                    print(f"POST-CHECK FAILED: marker missing in {rel} [{label}]")
                    return 4
            elif new not in raw:
                print(f"POST-CHECK FAILED: new text missing in {rel} [{label}]")
                return 4
            if not new.startswith(old) and not old.startswith(new) and old in raw:
                print(f"POST-CHECK FAILED: replaced anchor still present in {rel} [{label}]")
                return 4
    print("post-check OK: every new block present, every replaced anchor gone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
