#!/usr/bin/env python3
"""v1.24 -- (A) the fader must hold the guard through the LOAD FADE, and
(B) the pixel probe must be able to settle the question in a 3-second run.

WHY (A). The 01:30 run is the evidence, and every field below is from the SAME
[CAM] PC v1.19 line, so the three readings are one game state, not three guesses:

  01:30:53.130  [XRAY] MENU EDGE open=0 serial=1158 consts(ok=0 fail=0)
  01:30:53.365  paused=0 ld=0 fade=1 hrsD=0.000326  PC_STILL   INPUT_NONE
  01:30:54.373  paused=0 ld=0 fade=1 hrsD=0.006651  PC_MOVING  INPUT_NONE
  01:30:55.379  paused=0 ld=0 fade=1 hrsD=0.005666  PC_STILL   INPUT_NONE
  01:30:53.494  [Streamline] DLSSG presented per real frame = 4

The guard released at 01:30:53.130 because GameIsPaused() had gone to 0. The
fader was STILL UP on every sample afterwards -- the screen had not been handed
the world yet -- and 0.36 s later the 4x request was granted on that same screen.
The player then reported a frozen, flickering picture and left 2.5 s after that.

v1.22 dropped the fader term on purpose, and its reasoning was right for the case
it was looking at (the 00:30 run): the clock is already advancing at fade=1, so
the fader is not evidence of a menu, and a stale guard had parked 4x for 40+ s in
the 23:38 run. What that change also did, silently, was let the guard go DURING
the fade -- which is the one window where there is no world on screen to
interpolate. Both cases are kept: the fader holds for at most 8 s after it is
first seen, so a fader that never drops still cannot park the guard forever.

Why 8 s and not 90 s: faderUpSec counts from process start, so on the 01:30 run
the old "90" cap could not have fired before 01:31:24 -- the run ended at
01:30:55. The cap was never the thing releasing the guard; GameIsPaused() was.

WHY (B). The probe was fixed in v1.23 and produced its first samples ever, but it
samples at 1 Hz and only shouts VERDICT after 10 identical samples -- 10 s. Three
consecutive runs ended 2.5/6.1/2.6 s after the guard released, so the verdict
threshold can never be reached in the only window that matters. The probe now
samples at 2 Hz and calls it at 6 samples (3 s), and requires the camera to have
been moving on >= 4 of them, which is the same L44 bar as before (a still camera
makes interpolated frames legitimately identical). Nothing about the copy changes:
it is still DO_NOT_WAIT, still dropped-not-retried, so a shorter interval can cost
samples but can never stall the render thread.

What this deliberately does NOT do: it does not claim the fade is the whole cause.
The 01:30 run has no INPUT_SEEN sample at all -- all 26 [CAM] PC lines read
INPUT_NONE -- so this run cannot say whether the world responds to input. It can
only say that 4x was switched on while the screen was still under the fader.
"""

import argparse
import ast
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SL = "src/Streamline.cpp"
DX = "src/DX12SwapChain.cpp"

EDITS = [
    (
        SL,
        "S1 declare the fader-open timestamp",
        "static const auto s_faderT0 = std::chrono::steady_clock::now();\n"
        "\t\t\tconst auto faderUpSec = std::chrono::duration_cast<std::chrono::seconds>(\n"
        "\t\t\t\tstd::chrono::steady_clock::now() - s_faderT0).count();",

        "static const auto s_faderT0 = std::chrono::steady_clock::now();\n"
        "\t\t\tconst auto faderUpSec = std::chrono::duration_cast<std::chrono::seconds>(\n"
        "\t\t\t\tstd::chrono::steady_clock::now() - s_faderT0).count();\n"
        "\t\t\t// v1.24: when the fader was FIRST seen, so the hold below can be bounded.\n"
        "\t\t\t// atomic, not a plain static: this function is reached from the present path\n"
        "\t\t\t// and the constants path, which are not the same thread (01:30 run: tid 2088\n"
        "\t\t\t// and 14480 both wrote MENU EDGE lines).\n"
        "\t\t\tstatic std::atomic<long long> s_faderOpenSinceMs{ 0 };",
    ),
    (
        SL,
        "S2 hold the guard through the load fade, for at most 8 s",
        "\t\t\treturn ui->GameIsPaused() && faderUpSec < 90;",

        "\t\t\t// v1.24 -- the fader also covers the LOAD FADE, where the clock is already\n"
        "\t\t\t// running (hrsD > 0, paused=0) but the screen still has no world on it.\n"
        "\t\t\t// 01:30 run: guard released at 01:30:53.130 with fade=1 on every sample\n"
        "\t\t\t// after it, and 'presented per real frame = 4' at 01:30:53.494 -- 4x was\n"
        "\t\t\t// granted while the fade was still up. Bounded at 8 s so a fader that never\n"
        "\t\t\t// drops (23:38 run: 40+ s) cannot park the guard the way it did before v1.22.\n"
        "\t\t\tif (ui->IsMenuOpen(\"Fader Menu\")) {\n"
        "\t\t\t\tconst auto nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(\n"
        "\t\t\t\t\tstd::chrono::steady_clock::now().time_since_epoch()).count();\n"
        "\t\t\t\tlong long t0 = s_faderOpenSinceMs.load();\n"
        "\t\t\t\tif (t0 == 0) {\n"
        "\t\t\t\t\ts_faderOpenSinceMs.store(nowMs);\n"
        "\t\t\t\t\tt0 = nowMs;\n"
        "\t\t\t\t}\n"
        "\t\t\t\tif (nowMs - t0 < 8000)\n"
        "\t\t\t\t\treturn true;\n"
        "\t\t\t} else {\n"
        "\t\t\t\ts_faderOpenSinceMs.store(0);\n"
        "\t\t\t}\n"
        "\t\t\treturn ui->GameIsPaused() && faderUpSec < 90;",
    ),
    (
        DX,
        "D1 probe interval 1 Hz -> 2 Hz",
        "\t\tif (pixelProbeLastMs != 0 && nowMs - pixelProbeLastMs < 1000)\n"
        "\t\t\treturn;\n"
        "\t\tpixelProbeLastMs = nowMs;",

        "\t\t// v1.24: 1 Hz could not reach the verdict threshold in the windows we actually\n"
        "\t\t// get (three runs ended 2.5/6.1/2.6 s after the guard released). 2 Hz keeps the\n"
        "\t\t// copy DO_NOT_WAIT and dropped-not-retried, so a tighter interval can only\n"
        "\t\t// cost samples, never stall the render thread.\n"
        "\t\tif (pixelProbeLastMs != 0 && nowMs - pixelProbeLastMs < 500)\n"
        "\t\t\treturn;\n"
        "\t\tpixelProbeLastMs = nowMs;",
    ),
    (
        DX,
        "D2 verdict at 6 samples (3 s) with >= 4 moving",
        "\t\t\t\tif (pixelProbeStreak == 10) {\n"
        "\t\t\t\t\tif (pixelProbeMovedDuringStreak >= 5) {",

        "\t\t\t\tif (pixelProbeStreak == 6) {\n"
        "\t\t\t\t\tif (pixelProbeMovedDuringStreak >= 4) {",
    ),
    (
        DX,
        "D3 verdict text says 3 seconds",
        "\t\t\t\t\t\tSKSE::log::error(\"[PIXEL] VERDICT: the frame content is byte-identical for 10 \"\n"
        "\t\t\t\t\t\t\t\"consecutive seconds WHILE the camera was moving (clipDev > 0 on {} of them). \"",

        "\t\t\t\t\t\tSKSE::log::error(\"[PIXEL] VERDICT: the frame content is byte-identical for 3 \"\n"
        "\t\t\t\t\t\t\t\"consecutive seconds WHILE the camera was moving (clipDev > 0 on {} of them). \"",
    ),
    (
        DX,
        "D4 the counter-example text says 3 seconds",
        "\t\t\t\t\t\tSKSE::log::warn(\"[PIXEL] 10 identical seconds, but the camera was still on {} of \"",

        "\t\t\t\t\t\tSKSE::log::warn(\"[PIXEL] 3 identical seconds, but the camera was still on {} of \"",
    ),
]

EOL = {SL: "\r\n", DX: "\n"}


def read(path: Path):
    raw = path.read_bytes()
    return raw, raw.decode("utf-8-sig")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    # self-check: the script must at least parse before it touches anything.
    ast.parse(Path(__file__).read_text(encoding="utf-8"))

    changed = {}
    for rel, label, old, new in EDITS:
        p = ROOT / rel
        raw, text = read(p)
        eol = "\r\n" if "\r\n" in text else "\n"
        old_c = old.replace("\n", eol)
        new_c = new.replace("\n", eol)
        n = text.count(old_c)
        if n != 1:
            print(f"REFUSED, nothing written :: [{label}] anchor count == {n} (must be 1)")
            return 2
        if text.count(new_c) >= 1:
            print(f"REFUSED, nothing written :: [{label}] the NEW text already exists (already applied?)")
            return 2
        changed.setdefault(rel, []).append((label, old_c, new_c))

    print("dry run OK - every anchor is unique:")
    for rel, items in changed.items():
        for label, old, new in items:
            print(f"  {rel:26s} {label:52s} +{len(new) - len(old)} chars")

    if not args.apply:
        print("\n(dry run only; re-run with --apply)")
        return 0

    for rel, items in changed.items():
        p = ROOT / rel
        raw, text = read(p)
        eol = "\r\n" if "\r\n" in text else "\n"
        for label, old_c, new_c in items:
            text = text.replace(old_c, new_c, 1)
        body = text.replace("\r\n", "\n").replace("\n", eol)
        out = body.encode("utf-8")
        if raw.startswith(b"\xef\xbb\xbf"):
            out = b"\xef\xbb\xbf" + out
        p.write_bytes(out)
        print(f"wrote {rel}  md5={hashlib.md5(out).hexdigest()}  bytes={len(out)}")

    # post-condition: the old anchors are gone, the new ones are readable back.
    for rel, items in changed.items():
        _, text = read(ROOT / rel)
        eol = "\r\n" if "\r\n" in text else "\n"
        for label, old_c, new_c in items:
            # A "grow" edit (new text CONTAINS old text) legitimately leaves the old
            # string in the file. The correctly counted post-condition is therefore
            # "the old anchor appears exactly as often as the NEW block contains it":
            # 0 expected occurrences means the replacement never happened, and more
            # than that means a second copy exists somewhere it should not.
            want = new_c.count(old_c)
            got = text.count(old_c)
            if got != want:
                print(f"POST-CHECK FAILED: {rel} [{label}] old anchor count {got} != {want}")
                return 3
            if new_c not in text:
                print(f"POST-CHECK FAILED: new text not readable back in {rel} [{label}]")
                return 3
    print("post-check OK: every old anchor is gone and every new block reads back")
    return 0


if __name__ == "__main__":
    sys.exit(main())
