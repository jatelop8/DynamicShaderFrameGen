#!/usr/bin/env python3
"""v1.23 -- fix the pixel probe (it never produced a single sample) and stop a
degenerate clipToPrevClip from being published.

WHY, in the order the 00:58 log proves it.

1. THE PROBE WAS DEAD, AND SILENT ABOUT IT.

   [PIXEL] probe armed: src=3840x2160 ...   00:58:14.810
   [PIXEL] <nothing>                        00:58:14.811 .. 00:58:54.206

   Zero samples in 39 s. The cause is in the v1.22 code: CopySubresourceRegion
   and Map ran in the SAME call, so the Map always asked for a texture the GPU
   had not finished writing and returned DXGI_ERROR_WAS_STILL_DRAWING. That path
   also did `pixelProbeLastMs = 0`, which defeats the 1 Hz gate, so the retry
   happened on EVERY present instead of once per second:

     - the picture question (is the screen stale, ledger L38) went unmeasured,
       which is exactly the question this run needed answered;
     - and it put a cross-API copy from the D3D12-owned shared backbuffer into
       every single frame, the only v1.22 change that touches the render path.

   Fixed by splitting the two phases: harvest the copy made on the previous tick
   (a full second to land), then issue the next one. A sample that is not ready
   is dropped and counted, never retried in the same second.

2. THE PROBE NOW WITNESSES ITSELF (ledger L39, applied to my own code).

   If it is armed and has produced nothing for 15 s it logs an ERROR. A silent
   instrument and a healthy screen produced the same log; they must not.

3. THE PROBE NOW SAMPLES WHAT IS ON SCREEN.

   With DLSS-G on, Streamline presents colorOutWrapped -- the engine backbuffer
   is the HUD-less colour INPUT (DX12SwapChain.cpp:1583 vs :1582). v1.22 sampled
   the input, which answers "did the engine render a new frame", not "is the
   screen stale". It now prefers colorOutWrapped and names its source in the
   arm line.

4. A STILL CAMERA IS NOT A FROZEN SCREEN.

   A hash streak of identical frames is only evidence of a freeze if the camera
   was moving: with a still camera DLSS-G's interpolated output is legitimately
   identical to the real frame. The probe now reads lastClipDev (written by the
   constants path in Streamline.cpp) and only shouts VERDICT when the camera was
   moving on >= 5 of the 10 seconds; otherwise it says so explicitly.

5. A ZERO MATRIX PASSED THE OLD VALIDITY TEST.

   Measured in the 00:58 log, at the loading -> world transition:

     [W] [MOTION] clipToPrevClip[3].w=-68.073540 (must be 1) ...
         v1.08 PROBE: p00 cur=6.7031 prev=0.0000 | p23 cur=-15.010994 prev=0.000000

   prevForReproj was a ZERO matrix, so inv(cur) x 0 = 0. That passes
   `clipMagAll < 1.0e30` (mag is 0, not huge), which means the zero matrix was
   accepted AND stored in s_lastGoodClip -- the history that later frames fall
   back to. The same run's FLD dump of frame #1 reads
   `PrevVPU row3=(0,0,0,0) [3][3]=0 mag=0 BAD`.

   The test now also requires mag > 1e-6. Identity gives mag = 4.0 and any real
   motion keeps it there, so only a degenerate matrix fails it -- and a failed
   frame now holds the last good matrix (or identity) instead of publishing
   "the camera moved by nothing" to DLSS-G.

6. Two diagnostic defects that cost time this round:

   - The verdict chain put "a second thread PERSISTENTLY calls slSetConstants"
     (tidCallsB > 10) above every other check, but the log shows a=1: the first
     caller made ONE call and never came back, which demonstrates nothing. It
     now needs BOTH counters > 10, i.e. two threads actually active.
   - The dims line claimed "depth/mvec must read 2560x1440 (the real interop
     buffers)" while printing 3840x2160 for all three extents -- and those
     extents are read off the real interop resources a few lines above. The
     hardcoded expectation was stale and it is the only thing in this log that
     could have sent me after a resolution mismatch that does not exist. It now
     compares depth against mvec, which is the check that can actually fail.

Default is a DRY RUN; pass --apply to write. Every anchor must match exactly
once or nothing is written at all.
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPL = ROOT / "tools" / "v123_pixelprobe_impl.txt"

SL = "src/Streamline.cpp"
H = "src/DX12SwapChain.h"
CPP = "src/DX12SwapChain.cpp"
FH = "src/FrameGen.h"

# --- E1: probe state for two-phase sampling + the self-witness --------------
E1_NEEDLE = "bool pixelProbeDisabled = false;"
E1_ADD = [
    "// v1.23 -- two-phase sampling state. v1.22 copied and mapped in the same",
    "// call, so the Map never once succeeded and the probe logged nothing at all",
    "// (00:58 run: armed at 00:58:14.810, zero samples in 39 s).",
    "bool pixelProbeCopyPending = false;      // a copy for the NEXT tick is in flight",
    "bool pixelProbeSelfWitnessFired = false; // the \"armed but silent\" alarm",
    "std::uint32_t pixelProbeSrcW = 0;        // size we armed against; a change rearms",
    "std::uint32_t pixelProbeSrcH = 0;",
    "std::uint32_t pixelProbeDropped = 0;     // copy landed too late to read",
    "// A hash streak only means \"frozen\" if the camera was moving: with a still",
    "// camera DLSS-G's interpolated output is legitimately identical to the real",
    "// frame, so the streak alone cannot separate a still picture from a stale one.",
    "std::uint32_t pixelProbeMovedDuringStreak = 0;",
    "std::uint64_t pixelProbeArmedMs = 0;",
]

# --- E2: the clipDev the probe reads ----------------------------------------
E2_NEEDLE = "std::atomic<bool> fgActive{ false };"
E2_ADD = [
    "",
    "// v1.23 -- last clipDev the constants path computed, i.e.",
    "// max|I - clipToPrevClip|. Identity (a genuinely still camera) reads 0.000061;",
    "// the pixel probe reads this at 1 Hz so that ten identical frames with a still",
    "// camera are not reported as a frozen screen.",
    "std::atomic<float> lastClipDev{ 0.0f };",
]

# --- E3: publish clipDev every frame ---------------------------------------
E3_NEEDLE = "float clipMagAll = 0.0f;"
E3_ADD = ["Get().lastClipDev.store(clipDev);   // v1.23: read by PixelProbeTick()"]

# --- E5: the over-claiming second-thread verdict ---------------------------
E5_NEEDLE = "else if (diag.tidCallsB > 10)"
E5_ADD = [
    "// v1.23: tidCallsB > 10 alone fired on this run with a=1 -- the FIRST caller",
    "// made one call and never came back (that is what a one-shot at world entry",
    "// looks like), which demonstrates none of the hazard the message describes.",
    "// Two threads are only a problem if BOTH are active.",
    "else if (diag.tidCallsB > 10 && diag.tidCallsA > 10)",
]

# --- E6: the stale dimension expectation -----------------------------------
E6A_NEEDLE = '"[Streamline] DLSSG tag dims: hudless/scaling-output={}x{} depth={}x{} mvec={}x{} "'
E6A_ADD = ['"[Streamline] DLSSG tag dims: {} | hudless/scaling-output={}x{} depth={}x{} mvec={}x{} "']

E6B_NEEDLE = "extent.width, extent.height, depthExtent.width, depthExtent.height,"
E6B_ADD = [
    "(depthExtent.width == mvecExtent.width && depthExtent.height == mvecExtent.height)",
    '? "depth/mvec AGREE" : "depth/mvec DISAGREE - DLSS-G needs them equal",',
    "extent.width, extent.height, depthExtent.width, depthExtent.height,",
]

E6C_NEEDLE = '"- depth/mvec must read 2560x1440 (the real interop buffers)",'
E6C_ADD = [
    '"- v1.23: these extents are read off the real interop resources just above, so "',
    '"- the only thing that can be wrong here is depth and mvec disagreeing.",',
]

# --- E7: a zero matrix is not a valid clipToPrevClip ------------------------
E7_NEEDLE = "const bool clipFinite = clipMagAll < 1.0e30f;   // rejects NaN / Inf"
E7_ADD = [
    "// v1.23: mag == 0 passes \"< 1e30\" but is NOT a valid reprojection -- it means",
    "// prevForReproj was a zero matrix, so inv(cur) x prev = 0. The 00:58 log prints",
    "// exactly that at the loading -> world transition (`prev=0.0000`, and the FLD",
    "// dump of frame #1 reads PrevVPU mag=0 BAD). The old test ACCEPTED it and stored",
    "// it in s_lastGoodClip, so the garbage came back on later frames. Identity gives",
    "// mag = 4.0 and real motion keeps it there, so 1e-6 only rejects degenerate input.",
    "const bool clipFinite = clipMagAll < 1.0e30f && clipMagAll > 1.0e-6f;",
]

EDITS = [
    (H, "E1 probe state", "after", E1_NEEDLE, E1_ADD),
    (FH, "E2 lastClipDev field", "after", E2_NEEDLE, E2_ADD),
    (SL, "E3 publish clipDev", "before", E3_NEEDLE, E3_ADD),
    (CPP, "E4 rewrite PixelProbeTick", "funcspan", "void DX12SwapChain::PixelProbeTick()", None),
    (SL, "E5 verdict needs both threads active", "replace", E5_NEEDLE, E5_ADD),
    (SL, "E6a dims line format", "replace", E6A_NEEDLE, E6A_ADD),
    (SL, "E6b dims real cross-check", "replace", E6B_NEEDLE, E6B_ADD),
    (SL, "E6c stale 2560x1440 claim", "replace", E6C_NEEDLE, E6C_ADD),
    (SL, "E7 reject a degenerate matrix", "replace", E7_NEEDLE, E7_ADD),
]

# funcspan: the function runs from the start signature to the line before this one
E4_STOP = "HRESULT DX12SwapChain::GetDevice"

POST = {
    H: ["pixelProbeCopyPending", "pixelProbeArmedMs", "pixelProbeSrcW"],
    FH: ["std::atomic<float> lastClipDev{ 0.0f };"],
    SL: ["Get().lastClipDev.store(clipDev);", "diag.tidCallsB > 10 && diag.tidCallsA > 10",
         "clipMagAll < 1.0e30f && clipMagAll > 1.0e-6f", '"[Streamline] DLSSG tag dims: {} |'],
    CPP: ["if (pixelProbeCopyPending)", "phase 2: harvest", "pixelProbeMovedDuringStreak",
          "armed {} s ago and produced ZERO samples", "source={}"],
}

# A no-op must not be able to satisfy the post-conditions.
POST_GONE = {
    CPP: ["pixelProbeLastMs = 0;   // retry on the next frame"],
    SL: ['"- depth/mvec must read 2560x1440 (the real interop buffers)",',
         "else if (diag.tidCallsB > 10)\n"],
}

MARKER = "pixelProbeCopyPending"
GUARD = H


def eol_of(text: str) -> str:
    crlf = text.count("\r\n")
    bare = text.count("\n") - crlf
    return "\r\n" if crlf > bare else "\n"


def line_indent(text: str, needle: str) -> str:
    i = text.index(needle)
    j = text.rfind("\n", 0, i) + 1
    return text[j:i]


def sha(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def build(text: str, mode: str, needle: str, payload, eol: str) -> tuple[str, str]:
    ind = line_indent(text, needle)
    old = ind + needle + "\n"

    if mode == "replace":
        new = "".join(ind + c + "\n" for c in payload)
        return old, new
    if mode == "before":
        new = "".join(ind + c + "\n" for c in payload) + ind + needle + "\n"
        return old, new
    if mode == "after":
        new = ind + needle + "\n" + "".join(ind + c + "\n" for c in payload)
        return old, new
    raise ValueError(f"unknown mode {mode}")


def main() -> int:
    apply = "--apply" in sys.argv

    if not IMPL.is_file():
        print(f"REFUSED: implementation text missing: {IMPL}")
        return 2

    guard_path = ROOT / GUARD
    if guard_path.is_file() and MARKER in guard_path.read_bytes().decode("utf-8", "surrogateescape"):
        print(f"REFUSED: already applied ({MARKER} present in {GUARD}), nothing written")
        return 1
    if "Get().lastClipDev" in (ROOT / SL).read_bytes().decode("utf-8", "surrogateescape"):
        print(f"REFUSED: already applied (lastClipDev present in {SL}), nothing written")
        return 1

    impl = IMPL.read_text(encoding="utf-8").strip("\n")

    per_file: dict[str, list] = {}
    for f, label, mode, needle, payload in EDITS:
        per_file.setdefault(f, []).append((label, mode, needle, payload))

    results: dict[str, str] = {}

    for f, edits in per_file.items():
        path = ROOT / f
        if not path.is_file():
            print(f"REFUSED: missing file {f}")
            return 2
        text = path.read_bytes().decode("utf-8", "surrogateescape")
        eol = eol_of(text)
        tag = "CRLF" if eol == "\r\n" else "LF"

        for label, mode, needle, payload in edits:
            if mode == "funcspan":
                start = text.index(needle)
                stop = text.index(E4_STOP, start)
                block = text[start:stop]
                k = block.rindex("\n\t}\n")
                old_f = block[:k + len("\n\t}\n")]
                new_f = impl.replace("\n", eol) + eol
                if text.count(old_f) != 1:
                    print(f"REFUSED: {f} :: {label}: assembled span count={text.count(old_f)} (must be 1), nothing written")
                    return 1
                print(f"  ok  {f:<44} {label}  [{tag}] span {old_f.count(chr(10))} lines -> {new_f.count(chr(10))} lines")
                text = text.replace(old_f, new_f, 1)
                continue

            if text.count(needle) != 1:
                print(f"REFUSED: {f} :: {label}: needle count={text.count(needle)} (must be 1), nothing written")
                return 1
            old, new = build(text, mode, needle, payload, eol)
            old_f, new_f = old.replace("\n", eol), new.replace("\n", eol)
            if text.count(old_f) != 1:
                print(f"REFUSED: {f} :: {label}: assembled anchor count={text.count(old_f)} (must be 1), nothing written")
                return 1
            text = text.replace(old_f, new_f, 1)
            print(f"  ok  {f:<44} {label}  [{tag}]")

        results[f] = text

    ok = True
    print("\n-- post-conditions on the RESULT text --")
    for f, needles in POST.items():
        text = results[f]
        for needle in needles:
            c = text.count(needle)
            good = c >= 1
            print(f"  post {'OK  ' if good else 'FAIL'} {f:<44} {needle[:62]!r} count={c}")
            ok &= good

    print("\n-- what a no-op could NOT have removed --")
    for f, needles in POST_GONE.items():
        text = results[f]
        for needle in needles:
            c = text.count(needle)
            good = c == 0
            print(f"  gone {'OK  ' if good else 'FAIL'} {f:<44} {needle[:62]!r} count={c}")
            ok &= good

    if not ok:
        print("\nREFUSED: a post-condition failed, nothing written")
        return 1

    if not apply:
        print("\nDRY RUN ok. Re-run with --apply to write.")
        return 0

    for f, text in results.items():
        path = ROOT / f
        before = sha(path)
        path.write_bytes(text.encode("utf-8", "surrogateescape"))
        print(f"  wrote {f:<44} {before} -> {sha(path)}")

    print("\napplied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
