# DynamicShaderFrameGen — What's New

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
