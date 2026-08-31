# DynamicShaderFrameGen Changelog

Frame generation plugin (FrameGen): FSR3 frame interpolation + DLSS upscaling, fully ENB-compatible, works on all GPUs (NVIDIA & AMD).

---

## v0.40 — 2026-08-31

**Player-friendly naming**
- Player-facing label unified to **FrameGen** (frame interpolation) — menu/INI no longer use confusing FSR/DLSS tags
- Explicitly marked "universal frame interpolation, works on NVIDIA & AMD"
- DLL version bumped to 0.40.0.0

## v0.39 — 2026-08-31

**DLSSG removed, stability first**
- DLSSG (DLSS frame generation) mode removed — proven unstable in complex mod environments (high-refresh windowed + multiple plugins: flicker/black screen/fail to enter game) after 12 iterations of debugging
- Frame generation now uses **FSR3** (AMD FidelityFX SDK runtime) exclusively — works on ALL GPUs (NVIDIA & AMD), rock solid
- In-game menu no longer offers a Provider switch (no accidental enable)
- **NVIDIA users**: FSR3 frame gen + DLSS upscaling gives DLSSG-comparable quality, with stability

## v0.26 — 2026-08-31

**ForceBorderless (new feature)**
- New `ForceBorderless=1` (default ON): forces the game to run borderless windowed
- Fixes the classic "frame generation won't enable" problem — regardless of in-game display mode (fullscreen or windowed), FG always activates; looks identical to fullscreen
- Per-frame overhead <1μs when already satisfied

## v0.25.4 — 2026-08-31

**Three critical bug fixes**
- Fixed **frame generation not enabling on AMD GPUs** (was gating FSR3 on DLSS availability)
- Fixed **FSR → DLSS switch breaking FG** (was loading a removed component)
- Fixed **stuck ImGui cursor after closing the in-game menu**

## v0.25 — 2026-08-30

**Architecture rework (first stable base)**
- DLSS-NR (Neural Rendering) moved out of the plugin — now provided by the external ReShade route; plugin stays clean of NVIDIA-binary patching
- Frame generation: FSR3 (default) + DLSSG (experimental)
- DLSS upscaling: DLAA / Quality / Balanced / Performance / Ultra Performance
- In-game menu (hold `Home`): toggle FG, upscale mode, sharpness
- ENB compatibility (swapchain proxy)

---

## Requirements

| Item | Requirement |
|---|---|
| Game | Skyrim SE (AE 1.6.1170) |
| Prereq | SKSE64 |
| GPU | Any DX12-capable GPU (FSR3 FG: all GPUs; DLSS upscaling: NVIDIA only) |
| Display mode | None (ForceBorderless handles it) |

## Notes

- Frame generation doubles effective FPS (e.g. 60 → 120)
- Fully coexists with ENB
- Compatible with swapchain-intercepting plugins (DynamicWetness, Community Shaders, etc.)
