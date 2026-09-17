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
