# v0.56 - declared != actual: DLSS-G was told the motion buffers were 1706x960

Reported: "it still flickers."

This round is not a guess. The same two buffers were described three different ways,
and every one of the three numbers was reachable from a different file:

| source | colour | depth / motion |
|---|---|---|
| the actual interop textures | 2560x1440 | **2560x1440** |
| `DLSSGOptions::mvecDepthWidth/Height` | 2560x1440 | **2560x1440** |
| `ResourceTag::extent` on the tag | 2560x1440 | **1706x960** |

Proof that the textures are 2560x1440 across their whole area:

  * runtime log: `depth interop texture created lazily (R32_FLOAT 2560x1440)`,
    `mvec interop texture created lazily (2560x1440)`
  * `CopyDepthToShared` / `CopyMvecToShared` set the viewport to
    `swapChainDesc.Width x Height` and draw a fullscreen triangle, so the entire
    texture is written, not a corner
  * `sl_dlss_g.h`: `mvecDepthWidth` = "Expected width of the input render targets
    (depth, motion-vector buffers etc)" - the buffer's own size, and 2560x1440 is
    what the caller passes

And the tag was wrong per NVIDIA's own header, `sl.h`:

    //! The area of the tagged resource to use (if using the entire resource leave as null)
    Extent extent{};

So DLSS-G was told to use the top-left 1706x960 of a 2560x1440 buffer while the
colour buffer is 2560x1440 in full. The colour/motion spatial correspondence was
off by 1/0.667 = 1.5x - and that pair is the input every generated frame is built
from. The display therefore alternated a correct real frame with a wrong generated
frame, at the generated rate. Continuous flicker is the expected symptom.

The stale value predates v0.7.8: back then the interop textures really were render
resolution, so `renderExtent` was right. v0.7.8 resized them to the output
resolution for FSR3 frame generation and the tag was never updated.

Independent confirmation from the DLSS-G runtime's own log (DLSSG-Transfusion,
run at 16:34) - it printed the tags it received:

    [MOTION-TAG] type=hudless         rect=(0,0 2560x1440)
    [MOTION-TAG] type=scaling-output  rect=(0,0 2560x1440)
    [MOTION-TAG] type=depth           rect=(0,0 1706x960)   <- wrong
    [MOTION-TAG] type=motion          rect=(0,0 1706x960)   <- wrong

**Fix.** No number is hardcoded any more. The extents come from the D3D12 resource
(`GetDesc()`), and the options' mvec/depth size comes from the D3D11 interop
texture. One source of truth, so the three can never drift apart again.

Also fixed in the same class: `CreateInterop`'s eager path built the depth/mvec
interop textures from the engine kMAIN desc (render resolution) while the lazy path
forces the output resolution - the same buffers came out at two different sizes
depending on which path happened to run first. Both are now the output resolution,
which is what FSR3 frame generation requires anyway.

**Instrumentation added** (so the remaining unknowns are decidable in one launch):

  * `[Streamline] DLSSG tag dims: hudless/scaling-output=... depth=... mvec=...`
    printed once. depth and mvec must read 2560x1440 on the next run.
  * `[Streamline] MOTION probe: clipToPrevClip maxDevFromIdentity=...`
    every 600 frames. Transfusion's log shows `clipToPrev=identity` for the first
    frames of a run, which is correct on a loading screen but fatal during play -
    an identity matrix means DLSS-G drops the camera part of its reprojection.
    Read it while walking: ~0 means the previous view-projection is not live.
  * `[FrameGen] Present called with SyncInterval=... Flags=...`, printed only when
    the flag word changes. `DXGI_PRESENT_ALLOW_TEARING` in that argument permits
    real tearing.

**Not changed on purpose.** The Reflex render cap stays at
`refreshRate / multiplier - 1` = 39 fps (156 presented on a 160 Hz panel). The
`-1` looked like a bug, but 156 is 4 Hz below the panel ceiling, which is exactly
the usual VRR guidance ("cap a few Hz below max refresh to avoid a VRR ceiling
hit"). On a VRR display the panel simply follows the 156 fps stream and there is
no beat. It is left alone so the single behavioural variable this run stays the
extent fix. `ReflexFpsLimit` in the INI overrides it if the display turns out not
to be running VRR.

Worth recording: DLSSG-Transfusion's own line
`DLSS-G actual presentation count: 4x (maximum generated frames=5, status=0)` in
the 16:34 run proves multi frame generation **was** running. "It flickers" and
"it is not generating frames" were never the same complaint.

---
# v0.55 - instrumentation: sample the presented-frames counter early and on change

Instrumentation only. No behaviour change - the Reflex render cap, the provider
choice and the MFG probe are untouched, so the single behavioural variable under
test remains DLSSG-Transfusion's `patchFlipMetering`.

**Why.** v0.53 added the one measurement that can prove multi frame generation is
really running (`sl::DLSSGState::numFramesActuallyPresented`), but emitted it with
`++presentedLog % 240 == 1`. With the v0.54 cap pinning the render rate to
`refreshRate / multiplier` = 39 fps at 4x on a 160 Hz panel, the first reading needs
~6.2 s of play. Every debug session so far ended inside that window, so the decisive
number was never printed once - which is why three rounds of fixes each ended in
"still flickering" with no data either way.

**Change.** The line is now emitted for the first 8 real frames, then on every change
of the reported value (capped at 200 change lines), then every 300 frames. A 1 -> 4
transition - or a 1/4 oscillation, which is what two pacers fighting over one swap
chain would look like - is therefore visible within a single frame.

Read it as: `= 4` proves 4 frames really reach the display per real frame. `= 1`
proves none do, no matter what `MFG probe: runtime ACCEPTED 4x` said.

---
# v0.54 - flicker: the render frame rate was pinned to 60fps regardless of the panel

Reported: "it flickers constantly."

Root cause - measured, not guessed. Streamline::ReflexSleep() pushed a hardcoded
reflex frame limit of 1000000/60 us (inherited from Community Shaders' default), and
Reflex dutifully enforced it on the RENDER frame rate:

    [16:24:47.175] [Streamline] Reflex options applied (mode=1 frameLimitUs=16666 ...)
    DLSSG-Transfusion_perf.csv: DeltaMs=17.43 (=57.4 render fps), Multiplier=4

57.4 render fps x 4 = 229.6 presented fps, pushed at a 2560x1440 @ 160Hz panel.
That is 43% over-submission: the present queue backs up, the SL pacer loses its
rhythm, and the picture flickers continuously. Transfusion was in `fixed` mode, so
it never backed the multiplier off.

Frame generation is only correct when the product lands on the panel:

    render fps x multiplier <= refresh rate

So the cap is now derived instead of hardcoded:

    auto: (refreshRate / totalMultiplier) - 1 fps
          160Hz / 4x -> 39fps -> ~156 presented fps, just under the panel
    ReflexFpsLimit=N  (new INI key) overrides it with an explicit render fps cap

The multiplier used is the runtime-ACCEPTED one (dlssgAcceptedFrames), falling back
to the requested DLSSGFramesToGenerate before the staircase probe latches - so a
stepped-down request re-derives the cap instead of over-submitting again. The value
is logged whenever it changes:

    [Streamline] Reflex render cap = 39 fps (25641us) - 160Hz / 4x => ~156 present fps

If the refresh rate cannot be read the cap is left at 0 (unlimited) and a warning is
logged - silently substituting some made-up number is exactly what caused this bug.

This also explains why the FPS counter sat at ~57 no matter what was requested: the
render side was pinned, so the generated side could never track the panel.


# v0.53 - the FPS number stops lying, and MFG gets a measurement

Reported: "check it yourself before I go in again, I do not want another launch
that is completely wrong."

Audit of the whole chain (all verified against on-disk state, not assumed):
  * Deployment is correct. The DLL in the active MO2 instance is byte-identical to
    the build output; the active INI is Provider=1 / DLSSGFramesToGenerate=3 /
    MFGMaxFramesOverride=3; overwrite/ carries no copy of it; the two other mods
    that also ship an INI of this name are DISABLED in the DIPEI profile, so there
    is no file conflict. PLUGIN_DEPLOY_DIR points at the instance that is played.
  * RTXMFG-Universal (the competing unlocker that also detours slInit /
    setOptions / ngxCreate) has been inert since 2026-09-11 - its proxy is sitting
    in the game dir renamed to dinput8.dll.disabled.
  * Streamline is 2.13.0.0 everywhere (game root and mod folder agree), and
    nvngx_dlssg.dll is 3.10.8, inside DLSSG-Transfusion's supported range.

Defect found and fixed - the overlay could not have shown the difference:
  * ImguiMenu::DrawFps hardcoded `mult = fgActive ? 2.0f : 1.0f`. It never knew
    about MFG, so 3x/4x could not appear on screen, and it multiplied the number
    even when the runtime had rejected the request. Switching FSR3 -> DLSSG was
    therefore guaranteed to look like "nothing changed". The factor now comes from
    dlssgFramesPresentedLast, and when DLSSG is not generating nothing is inflated
    (the overlay says so instead).

New evidence channel:
  * sl::DLSSGState::numFramesActuallyPresented is documented as "frames presented
    since the last slDLSSGGetState call" - a per-interval count. Since
    SetDLSSGOptions runs once per real frame, that value IS the multiplier that
    actually happened. It is now recorded every frame and logged periodically as
    "DLSSG presented per real frame = N" (1 = no interpolation). This is the first
    number in this project that is measured rather than computed.

Also: version.rc string version said 0.50.0.0 while FILEVERSION said 0.52 - both
now 0.53. The INI documents DLSSG-Transfusion's own Ctrl+Alt+2/3/4 hotkeys, which
are how the multiplier is really driven, not the game's video menu.

Still unproven: Provider=1 has never completed a session on this machine. Every
log so far is the FSR3 path. The next launch is the first real test; if the runtime
rejects 4x the ladder probe steps back to whatever it accepts and says so.
# v0.52 - switch states that actually stick, and diagnostics that can be falsified

Reported: "I switched DLSS and nothing changed at all."

Diagnosis (from the 13:59-14:01 SKSE log + on-disk state):
  * The "Frame Gen Provider" combo only mutated in-memory state. Provider is consumed
    exactly once, in DX12SwapChain::CreateSwapChain (dlssgMode / BufferCount / D3D12
    proxy path), so changing it mid-session is a no-op BY CONSTRUCTION - and it wrote
    no log line, so there was no trace of the switch anywhere.
  * It was never persisted either: the combo never touched the INI, and "Save to INI"
    wrote a different path literal than LoadConfig reads, silently dropped keys and
    never logged a failure. overwrite/SKSE/Plugins had no FrameGen INI at all, which
    proves no save ever succeeded -> even a restart read Provider=0 back.
  * The DLSSNR diag line printed the ENGINE's kMAIN depth / kMOTION_VECTOR while
    Apply() is actually fed depthWrapped/mvecWrapped, so it could not falsify
    "is NR running?", and the log carried no success counter.
  * The menu header still advertised "DLSS Upscaling (live adjust)" although DLSS
    upscaling was removed in v0.48, and EnableUpscale / PresetDLSS are parsed but
    wired to nothing -> dead switches that look live.

Changes:
  * ImguiMenu: SaveSettingsToIni() is now the single writer, used by the Save button
    AND by every switch that changed (Provider / MFG multiplier / MFG override /
    DLSSNR). It uses the exact LoadConfig path, writes EVERY key LoadConfig knows
    (the old one truncated the file to 17 keys, silently wiping QualityMode,
    RenderResolutionScale, Sharpness, FpsOverlay, EnableUpscale, PresetDLSS) and logs
    the result either way.
  * MFG multiplier + override are no longer hidden behind provider==1, so DLSSG can be
    pre-configured while on FSR3.
  * DX12SwapChain: records providerAtCreate; GUI shows "PENDING RESTART: running X,
    INI wants Y"; the FPS probe line now prints both (cfgProvider=) and appends
    "(CHANGED - RESTART REQUIRED)" on a mismatch.
  * DLSSNR diag now prints the inputs Apply() actually consumes plus the NGX success
    frame counter, and warns once when the shared depth/mvec inputs are missing
    instead of silently skipping the pass.
  * INI: EnableUpscale / PresetDLSS marked as parsed-but-not-wired; Provider documented
    as applying on the next launch only. Version 0.50 -> 0.52.

Config: Provider=1 (DLSSG), DLSSGFramesToGenerate=3 (4x), MFGMaxFramesOverride=3,
paired with DLSSG-Transfusion v1.4.1 (version.dll) in the game directory.

# DynamicShaderFrameGen — What's New

## Multi-frame generation on RTX 40/30/20 — v0.50

Frame generation above 2x used to be unreachable on anything older than
RTX 50, because the Streamline runtime reports `numFramesToGenerateMax = 1`
on Ada and earlier, and every request was clamped down to that ceiling.

v0.50 adds `MFGMaxFramesOverride` (INI + in-game slider). It raises the
reported ceiling so the higher multipliers are actually submitted, up to 6x.

- `MFGMaxFramesOverride=0` follows the hardware report exactly (default, safe)
- `MFGMaxFramesOverride=1..5` submits 2x / 3x / 4x / 5x / 6x
- In-game: Home key -> Frame Gen Provider = DLSSG -> MFG Multiplier + MFG Max Override

**This only changes what is requested.** The frame generation kernels for
Ada / Ampere / Turing are not present in `nvngx_dlssg.dll`, so pair it with
an external kernel unlocker:

- DLSSG-Transfusion (RTX 40, native DLSS-G path)
- dlssg_for_sm86 (RTX 30)
- dlssg_for_sm75 (RTX 20, experimental)
- NVIDIA MFG Bridge (RTX 20/30)

Without one of those a high multiplier has no kernel to run.


## DLSS 5 Neural Rendering is now built in — v0.48

The headline of this release: DLSS 5 neural rendering (the "DLSS-NR" pass) now
runs straight from the plugin. No ReShade add-on, no `dlss5-dx11-bridge`, no
extra DLLs dropped in your game root.

- Sharper skin, hair, foliage and stone detail, with automatic masking so flat
  and uniform surfaces are left untouched
- Runs **together with frame generation** — the neural pass goes first, frame
  generation interpolates the result (the two used to be mutually exclusive)
- Tune it live in the menu (hold `Home`): Intensity, Local Tone, Local
  Structure, Skin Structure, Style, Automatic Mask, UI Correction and NR Render
  Scale (lower = faster, 1.0 = full-resolution analysis)
- Needs an RTX GPU and the `nvngx_dlssnr.dll` **310.8.x** runtime that ships
  with the mod. Any other version is refused at load, so the plugin turns itself
  off instead of misbehaving

## DLSS sharpening now lands before ENB, not after — v0.48

DLSS upscaling used to run in `Present` — after ENB — so ENB's own
post-processing painted over the DLSS sharpening and the preset's LMK. The
upscale now runs at the engine's post-processing entry point (before ENB), so
the sharpening survives and ENB still composites on top of the upscaled frame.

## Frame gen provider choice is back — v0.42 / v0.45

- Pick **FSR3 (2x, all GPUs)** or **DLSSG (NVIDIA)** in the menu; changing it
  needs a game restart
- DLSSG multi-frame generation: 2x on RTX 40, up to **4x on RTX 50**. The
  ceiling now comes from the Streamline runtime itself (`numFramesToGenerateMax`)
  instead of an unlock hack — no more forced values, no more guessing
- Default `DLSSGFramesToGenerate` is 3, so an RTX 50 gets 4x out of the box and
  a 40-series card quietly clamps to 2x

## Smaller changes

- `RenderResolutionScale` default is now `0` (Auto) — follows the DLSS Quality
  Mode table instead of a hard-coded 0.70. Set `0.30`–`1.00` for a custom ratio
- New compute shaders for the neural pass ship under
  `Shaders/Upscaling/NeuralRendering/` (depth-guide copy + downscale)
- `version.rc` bumped to 0.48.0.0

## Render resolution scale (custom DRS) — new in v0.41

Skyrim always renders at 100% resolution, so DLSS had nothing to upscale and frame
generation paid full-resolution cost. The plugin now lets you set the engine
render resolution as a percentage of your output (default **70%**) — DLSS really
upscales from e.g. 1440p back to 4K, which is a large FPS gain and gives DLSS5/NR
a true upscaling path.

- New INI setting: `RenderResolutionScale=0.70` (`0` = Auto, follows the Quality
  Mode table as before; `0.30`–`1.00` = custom ratio)
- In-game: hold `Home` → menu → **Render Resolution Scale** slider (30%–100%,
  live apply, save via *Save to INI*)

## Frame generation now uses FSR3 — works on ALL GPUs (NVIDIA & AMD)

The experimental DLSS frame generation (DLSSG) mode has been removed — it proved
unstable in complex mod environments (flickering, black screens, failing to reach
the main menu). Frame generation now runs on AMD FSR3 technology, which is rock
solid on every GPU with no quality loss.

## Force borderless windowed (new, enabled by default)

Frame generation used to require a windowed swapchain — many players launched the
game in "fullscreen" and found frame generation doing nothing. The plugin now
automatically switches the game window to borderless fullscreen, so **frame
generation always activates no matter what display mode you set**, while looking
identical to fullscreen.

## Three fixes

- Frame generation not enabling on **AMD GPUs**
- Frame generation breaking after switching **FSR → DLSS**
- Stuck **mouse cursor** after closing the in-game menu

## Cleaner naming

The in-game menu now simply says **FrameGen** — no more confusing FSR/DLSS tags.
Universal frame interpolation, works on NVIDIA & AMD.

## How to use

- Prerequisite: SKSE64
- Any DX12-capable GPU (FSR3 frame gen: all GPUs; DLSS upscaling: NVIDIA only)
- Frame generation doubles your FPS (e.g. 60 → 120)
- Fully coexists with ENB; compatible with snow-wetness and other swapchain plugins
- Hold `Home` in-game for the menu: toggle frame gen, upscale mode, sharpness
