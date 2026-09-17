#!/usr/bin/env python3
"""
doc_v057.py - write the v0.57 CHANGELOG entry and the v0.57 verification checklist.

CHANGELOG.md is CRLF (344 lines) and VERIFY_v057.md is new (LF). Line endings are
handled explicitly per file rather than through an editor, because the edit tool
has been observed silently converting CRLF to LF.

Markers guard re-runs; anchors must match exactly once.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPLY = "--apply" in sys.argv

CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
VERIFY = os.path.join(ROOT, "VERIFY_v057.md")

CHANGELOG_BODY = """# v0.57 - mvecScale: the last self-contradictory constant, made switchable

Reported: still flickering after v0.56.

This round deliberately changes no behaviour. It closes a question v0.56 opened,
and makes the answer testable with one INI line instead of another rebuild cycle.

## What v0.56 opened

v0.56 corrected the depth/mvec `ResourceTag::extent`. That fix is now confirmed
against this project's own reference implementation - open-shaders is on this
machine at D:\\Modding\\open-shaders - and the confirmation runs from the opposite
direction:

    open-shaders/src/Features/Upscaling/Streamline.cpp, TagDX12Resources()

      sl::Extent extent{ 0, 0, width, height };            // display/output size
      // Depth/mvec carry valid data only in the render-resolution subrect of
      // their display-sized targets; declare that extent, matching the FSR FG
      // dispatch.
      auto renderSizeF = globals::state->screenSize * upscaling.resolutionScale;
      sl::Extent renderExtent{ 0, 0, renderSizeF.x, renderSizeF.y };
      ...
      { &depthRes, sl::kBufferTypeDepth,         ..., &renderExtent },
      { &mvecRes,  sl::kBufferTypeMotionVectors, ..., &renderExtent },

The reference declares the RENDER subrect and is right to: it never upscales.
Its mvec path is a bare `CopyResource(dst, motionVector.texture)`
(Upscaling.cpp:2206), which only works when the dimensions are identical, and its
interop targets are built from the engine's own desc (DX12SwapChain.cpp:695-708).
The data genuinely occupies a corner of a larger target.

DFG is the opposite, and its own comment says why (DX12SwapChain.cpp:662):

    // 引擎 depth/mvec 是渲染尺寸（低）→ 都走 shader 采样放大（CopyResource 尺寸不匹配）

That blit runs in the DLSS-G path as well - `if ((dlssgMode || ...))`, line 663 -
and draws a fullscreen triangle with viewport = swapChainDesc.Width x Height
through a shader that returns the sampled value unchanged. DFG's interop
depth/mvec are therefore valid over the WHOLE 2560x1440.

Same constant, opposite correctness. `renderExtent` was copied from the reference
when it was still right; v0.7.8 changed how the buffers are filled and it was
never revisited. v0.56 stands.

## What was still self-contradictory: mvecScale

    Streamline.cpp:412
      // v0.49k（修重影）：... 引擎 mvec=位移/2560，DLSS 期望 位移/1706 →
      // 差 1/renderScale 倍，需放大补偿，否则 temporal 重投影错 → 重影。
      c.mvecScale = { 1.0f / renderScaleX, 1.0f / renderScaleY };   // = {1.5, 1.5}

Three sources, none of which agrees with 1.5:

| source | says |
|---|---|
| `sl_consts.h:203`, the field's own definition | "scale factors used to normalize motion vectors (so the values are in [-1,1] range)" |
| `ProgrammingGuideDLSS_G.md:653` | "values in {-1,1} range -> scale factor should be {1,1}"; otherwise "adjusted so that values end up in [-1,1]" |
| open-shaders `Streamline.cpp:490` | "The standard full-frame DLSS path ... must keep mvecScale at identity or DLSS massively over-estimates motion" |

The v0.49k comment carries its own refutation: "引擎 mvec = 位移/2560". A UV
displacement that reaches 1.0 for a full-screen pan is already inside [-1,1] -
exactly the condition the guide gives for scale = {1,1}. At 1.5, DLSS-G would
over-estimate motion by 50% in every generated frame, and wrong motion in every
generated frame alternating with correct real frames is the reported symptom.

But 1.5 was tuned in-game against a *different* defect - the depth/mvec extent that
v0.56 removed - so which value is right is decidable only in-game. Nothing is
changed silently.

## Change

  * `Streamline.cpp` reads `MvecScaleOverride` from the INI. 0 (default) = the
    legacy `1/renderScale`, so default behaviour is identical to v0.56. 1.00 =
    identity, the reference-implementation value.
  * the effective value is logged exactly once, so it is observed at runtime
    instead of inferred from source:

        [Streamline] mvecScale = { 1.5000, 1.5000 } (renderScale=0.6667 override=0.00)
        - 1.0 means already in [-1,1]

  * `FrameGen.h` / `FrameGen.cpp` / `ImguiMenu.cpp`: one new setting, one reader,
    one writer, so the INI contract stays symmetric. Verified in the built binary:
    the key string `MvecScaleOverride` occurs exactly twice, and the old direct
    assignment is gone.

## Build

Built clean: 7/7 objects, exit 0, `1223168 bytes md5=73fa4a5c2c762635703ca952205a1192`,
deployed byte-identical to
`E:\\EJ\\mod\\mods\\DynamicShaderFrameGen\\SKSE\\Plugins\\`.

The sandbox blocked `reg.exe`, which breaks `VsDevCmd.bat` and leaves the Windows
SDK paths unset - every translation unit then fails on `crtdbg.h`, including ones
this round never touched. Working manual environment, including the cppwinrt trap:

    INCLUDE = <MSVC>\\include ; <SDK>\\ucrt ; <SDK>\\shared ; <SDK>\\um ; <SDK>\\winrt
    LIB     = <MSVC>\\lib\\x64 ; <SDK>\\Lib\\ucrt\\x64 ; <SDK>\\Lib\\um\\x64

`<SDK>\\cppwinrt` must NOT be added: vcpkg ships the matching C++/WinRT set
(`E:\\vcpkg-full\\installed\\x64-windows-static-md\\include\\winrt`, 2.0.250303.1)
and the SDK's own copy is 2.0.250303.5, so mixing them makes `base.h` fire
`static_assert(... "Mismatched C++/WinRT headers.")`. `wrl/client.h` comes from
`<SDK>\\winrt`, which is the only part of that directory that is needed.

"""

VERIFY_BODY = """# VERIFY v0.57 - restart checklist

Supersedes VERIFY_v056.md. Same code path as v0.56 by default; the difference is
that one more value is now observable and switchable without a rebuild.

Read the runtime log: `C:\\Users\\Administrator\\Documents\\My Games\\Skyrim Special Edition\\SKSE\\DynamicShaderFrameGen.log`

-------------------------------------------------------------------------------

## 0. Confirm which build is actually live

    loaded (build Sep 17 2026 ...)

then the version resource. If the build date is older than this round, the launch
did not pick up the new DLL - check which MO2 instance is running (`Skyrim Special
Edition (3)`, profile `DIPEI`, base_directory `E:/EJ/mod`).

-------------------------------------------------------------------------------

## 1. The four lines this round is about

**(a) mvecScale - the value under test**

    [Streamline] mvecScale = { x, y } (renderScale=..., override=...)

Expected on an untouched INI: `x = y = 1.5000`, `renderScale = 0.6667`,
`override = 0.00`. If you see anything else, the INI has a value in it.

**(b) tag dims - the v0.56 fix, do not regress**

    [Streamline] DLSSG tag dims: ...

**depth and mvec must both read 2560x1440.** Anything else means v0.56 was undone.

**(c) options dims**

    [Streamline] DLSSG options dims: color=2560x1440 mvecDepth=2560x1440 ...

**(d) frames actually generated**

    DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)

`status=0` is eOk, and the `4x` is what makes this MFG rather than 2x. This line
proves interpolation is running - it does not prove the frames are correct.

-------------------------------------------------------------------------------

## 2. THE ONE VARIABLE TO TEST - mvecScale, one line, no rebuild

Open the INI used by MO2 (same folder the log's `INI loaded` line names) and add:

    MvecScaleOverride=1.00

Then restart and read line (a) again - it must print `{ 1.0000, 1.0000 }`.
If it still prints 1.5000, the INI being edited is not the one being loaded.

  * flicker gone at 1.00  -> 1.5 was 50% over-estimated motion, and v0.56 plus
    this is the whole fix. Keep `MvecScaleOverride=1.00`.
  * flicker unchanged     -> motion scale is not the cause; revert to 0 and move
    to section 3.

This is deliberately the first test: it is the only remaining value in the file
that both the field's own header and the reference implementation contradict.

-------------------------------------------------------------------------------

## 3. If flicker survives both - one change at a time

Keep `MvecScaleOverride` at whichever value section 2 selected, then change exactly
one of these per launch:

  1. `disableMenuDetection=false`
     Menu detection sets `c.reset` whenever a menu is open. If it fires during play,
     DLSS-G discards its history every frame.
  2. Transfusion `mode: dynamic` + `dynamicTargetFrameRate: 160`
     (`D:\\ENB-EJ\\Skyrim Special Edition\\DLSSG-Transfusion.json`)
  3. `Ctrl+Alt+3` - drop 4x to 3x and check whether the flicker rate follows the
     multiplier. If it does, the pacer is over-presenting; the Reflex cap is
     `refreshRate / multiplier - 1` = 39 fps render -> 156 present on a 160 Hz
     panel, which is correct for VRR and deliberately unchanged.
  4. `NeuralRenderingEnabled=0` - A/B against DLSS ray reconstruction, to separate
     frame generation from the upscaler.

-------------------------------------------------------------------------------

## 4. Walking-time probe

    [Streamline] MOTION probe: clipToPrevClip maxDevFromIdentity=...

Printed every 600 frames. **Walk around and read it.** The DLSS-G runtime logged
`clipToPrev=identity` for the first frames of a run, which is normal on a loading
screen. If it stays ~0 while you are moving, the camera reprojection matrices are
not live and every generated frame is built from a stale camera.

-------------------------------------------------------------------------------

## 5. Tearing check

    [FrameGen] Present called with SyncInterval=... Flags=...  [ALLOW_TEARING - ...]

Printed only when the flag word changes. `DXGI_PRESENT_ALLOW_TEARING` in that
argument permits genuine tearing.

-------------------------------------------------------------------------------

## Rollback

    E:\\EJ\\mod\\mods\\DynamicShaderFrameGen\\SKSE\\Plugins\\DynamicShaderFrameGen.dll.pre_v056

is the v0.56 binary. Source backups are `.pre_v057` next to each patched file
(`src/FrameGen.h`, `src/FrameGen.cpp`, `src/ImguiMenu.cpp`, `src/Streamline.cpp`,
`src/version.rc`). `git checkout .` also returns to commit `135c4e4` (v0.56);
v0.57 is committed on top of it.

## Known but deliberately untouched

  * In DLSSG mode the ImGui overlay and menu are drawn into `colorOutWrapped`, which
    the DLSSG branch never reads, and the colourOut -> backbuffer copy is skipped by
    that branch's early `return S_OK`. They are therefore invisible under DLSSG.
    Pointing them at `swapChainBufferWrapped` instead would put UI into DLSS-G's
    HUD-less input and get it interpolated; the correct fix is a separate UI texture
    plus `enableUserInterfaceRecomposition` / `uiBufferFormat`.
  * The Reflex render cap (`refreshRate / multiplier - 1`) is correct for VRR and is
    not a bug.
"""

problems = []
planned = []

# ---------------------------------------------------------------- CHANGELOG.md
raw = open(CHANGELOG, "rb").read()
ch_nl = b"\r\n" if b"\r\n" in raw else b"\n"
ch = raw.decode("utf-8").replace("\r\n", "\n")

if "v0.57 - mvecScale" in ch:
    problems.append("CHANGELOG.md: v0.57 section already present -> refusing")
else:
    anchor = "# v0.56 - declared != actual"
    if ch.count(anchor) != 1:
        problems.append("CHANGELOG.md anchor count = %d (want 1)" % ch.count(anchor))
    else:
        ch_new = CHANGELOG_BODY + ch
        planned.append("CHANGELOG.md prepend v0.57 entry (%d bytes)" % len(CHANGELOG_BODY))

# ------------------------------------------------------------------- VERIFY
if os.path.exists(VERIFY):
    problems.append("VERIFY_v057.md already exists -> refusing")
else:
    planned.append("VERIFY_v057.md create (%d bytes)" % len(VERIFY_BODY))

if problems:
    print("REFUSED, nothing written")
    for p in problems:
        print("  !", p)
    sys.exit(1)

print("planned:")
for p in planned:
    print("  *", p)

if "v0.57 - mvecScale" not in ch_new:
    sys.exit("internal error: changelog not staged")

if not APPLY:
    print("\nDRY RUN - nothing written. Re-run with --apply")
    sys.exit(0)

# CHANGELOG keeps CRLF, VERIFY is fresh LF
data = ch_new.replace("\n", "\r\n").encode("utf-8")
open(CHANGELOG, "wb").write(data)
crlf, lf = data.count(b"\r\n"), data.count(b"\n")
print("  CHANGELOG.md     %7d bytes  CRLF=%-5d LF=%-5d stray=%d %s"
      % (len(data), crlf, lf, data.count(b"\r") - crlf, "OK" if crlf == lf else "*** MISMATCH ***"))
assert crlf == lf, "CHANGELOG.md line endings broke"

vdata = VERIFY_BODY.encode("utf-8")
open(VERIFY, "wb").write(vdata)
print("  VERIFY_v057.md   %7d bytes  CRLF=0     LF=%-5d" % (len(vdata), vdata.count(b"\n")))

print("\ndone.")
