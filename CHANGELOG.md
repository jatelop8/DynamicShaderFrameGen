# DynamicShaderFrameGen — What's New

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
