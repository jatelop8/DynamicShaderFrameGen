# VERIFY v0.57 - restart checklist

Supersedes VERIFY_v056.md. Same code path as v0.56 by default; the difference is
that one more value is now observable and switchable without a rebuild.

Read the runtime log: `C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`

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
     (`D:\ENB-EJ\Skyrim Special Edition\DLSSG-Transfusion.json`)
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

    E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.dll.pre_v056

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
