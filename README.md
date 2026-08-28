# DynamicShaderFrameGen

SKSE plugin for The Elder Scrolls V: Skyrim Special Edition — **AMD FSR 3.1 Frame
Generation + NVIDIA DLSS Upscaling**, fully compatible with ENB. Fully open-source:
no paid or closed-source runtime is bundled; the Streamline and FidelityFX runtimes
are loaded at runtime from the official NVIDIA / AMD SDKs.

## Features

- **FSR 3.1 Frame Generation** (AMD FidelityFX SDK runtime) — doubles effective
  frame rate with motion-vector based interpolation.
- **DLSS Upscaling** (NVIDIA Streamline SDK runtime) — temporal upscaling with
  reconstruction and sharpening; at equal input/output resolution it runs as DLAA.
- **ENB compatibility** — the plugin proxies the swap chain (D3D11 shared
  textures + a D3D12 swap chain); ENB composites its post-processing onto the
  shared backbuffer, so ENB effects survive frame generation.
- **In-game ImGui menu** (hold `Home`) — toggle frame generation, toggle DLSS
  upscaling, quality mode, sharpness, save to INI.
- **DLSS-NR (Neural Rendering)** — direct NGX integration of NVIDIA's neural
  radiance feature (RTX 50-series only, sm_120). Graceful degradation: on GPUs
  without the FP8 Blackwell kernel the menu item is disabled — never a crash.
- **Render scale via engine dynamic resolution** — the engine render target is
  scaled through the dynamic-resolution hooks (perf gain; the backbuffer stays
  at output resolution).

## Requirements

- Skyrim Special Edition (AE 1.6.1170)
- SKSE64
- Address Library for SKSE Plugins (1.6.1170)
- ENB Series (optional, supported)
- NVIDIA GPU (DLSS) — FSR 3.1 FG works on any DX12-capable GPU

## Installation

Copy the contents of the mod folder into your Data folder (or a Mod Organizer 2
mod):
- `SKSE/Plugins/DynamicShaderFrameGen.dll`
- `SKSE/Plugins/DynamicShaderFrameGen.ini`
- `Shaders/` (upscale copy shaders)

**DLSS-NR (optional, RTX 50-series)**: drop NVIDIA's `nvngx_dlssnr.dll` into
`Shaders/Upscaling/Streamline/`. It is not redistributed (NVIDIA restriction,
~158 MB). On other GPUs the menu item simply stays disabled.

## Usage

| Key | Action |
|---|---|
| Hold `Home` | Open / close the in-game menu |
| Menu → Frame Generation (FG) | Toggle FSR 3.1 frame generation |
| Menu → DLSS Upscale | Toggle DLSS upscaling / DLAA rebuild |
| Menu → DLSS-NR | Toggle neural rendering (RTX 50-series only) |
| Menu → Quality Mode / Sharpness | Adjust DLSS settings (live) |
| Menu → Save to INI | Persist settings |

`EnableUpscale=0` in the INI disables DLSS and returns to pure frame
generation (highest frame rate, native engine image).

`EnableDLSSNR=1` enables DLSS-NR (with `nvngx_dlssnr.dll` present and an
RTX 50-series GPU); `NRIntensity` / `NRStyle` / `NRLocalTone` /
`NRSkinStructure` adjust the neural filter live in the menu.

## Architecture

1. Engine renders to its render targets (kMAIN); the plugin's swap-chain proxy
   exposes a D3D11 shared texture as the backbuffer.
2. `Main_UpdateJitter` hook (render-time) sets the engine dynamic-resolution
   ratio and DLSS Halton jitter.
3. `Present`: DLSS upscales the frame (backbuffer → `colorOut`, 4K) → FSR 3.1
   Frame Generation is dispatched on the D3D12 swap chain → presented.
4. FSR3 FG consumes depth / motion vectors (copied to shared textures and
   upscaled by the bundled HLSL shaders under `Shaders/Upscaling/`).

## Code Sources & Attributions

This project builds on the following open-source projects. Each component is
used and redistributed under its own license; full attribution is provided to
avoid any ambiguity:

| Component | Source | License | Used for |
|---|---|---|---|
| D3D12 swap-chain proxy, dynamic-resolution hooks (`Main_UpdateJitter` / `SetScissorRect`), Halton jitter, DRS ratio | **Community Shaders** (doodlum / Pentalimb) — https://github.com/doodlum/skyrim-community-shaders | GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception | `src/DX12SwapChain.*` architecture, DRS + jitter logic in `src/FrameGen.cpp` |
| FSR 3.1 Frame Generation integration (runtime table loading, swap-chain creation, per-frame configure/dispatch) | **ENBFrameGeneration** (doodlum / Pentalimb) — https://github.com/doodlum/ENBFrameGeneration | GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception | `src/FidelityFX.cpp` |
| In-game menu | **Dear ImGui** (Omar Cornut) — https://github.com/ocornut/imgui | MIT | `src/ImguiMenu.*`, `extern/imgui` (vendored) |
| DLSS upscaling integration code | **Community Shaders** `Streamline.cpp` — https://github.com/doodlum/skyrim-community-shaders | GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception | `src/Streamline.*` (code) |
| DLSS upscaling runtime | **NVIDIA Streamline SDK** — https://github.com/NVIDIA/streamline | Streamline SDK License | runtime DLLs (loaded at runtime, not bundled) |
| FSR 3.1 FG runtime | **AMD FidelityFX SDK** — https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK | AMD License (MIT-style) | FSR3 runtime loading |
| RE / REL framework | **CommonLibSSE-NG** (Ryan-rsm-McKenzie, alandtse) — https://github.com/alandtse/CommonLibSSE-NG | MIT | Whole plugin framework |
| Function detours | **Microsoft Detours** — https://github.com/microsoft/Detours | MIT | `MenuManagerDrawInterfaceStart` / `SetScissorRect` detours |
| Bundled CommonLibSSE-NG tree | **skyrim-community-shaders-dxr** extern (contains CommonLibSSE-NG) — https://github.com/doodlum/skyrim-community-shaders | MIT | `extern/CommonLibSSE-NG` used for RE/REL framework |

No code was taken from closed-source or paid projects. This repository contains
no NVIDIA Streamline or AMD FidelityFX binaries — those runtimes are loaded from
the official SDK installs at runtime.

## License

**GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception** — see [LICENSE](LICENSE) and [EXCEPTIONS.md](EXCEPTIONS.md).

This project derives from **Community Shaders** and **ENBFrameGeneration** (both GPL-3.0), so this project is released under the same license, with full attribution in the table above.

Note: the *runtime DLLs* loaded by this plugin (NVIDIA Streamline, AMD
FidelityFX) are subject to their respective SDK licenses; they are not part of
this repository.

## Credits

- doodlum (Pentalimb) — Community Shaders, ENBFrameGeneration
- Omar Cornut — Dear ImGui
- alandtse, Ryan-rsm-McKenzie — CommonLibSSE-NG
- NVIDIA Streamline, AMD FidelityFX, Microsoft Detours teams
- Skyrim Script Extender (SKSE) team

## Special Thanks

- **doodlum / Pentalimb** — for the open-source Community Shaders ecosystem and
  ENBFrameGeneration, which made the FSR3 + ENB coexistence possible
- **The Skyrim modding community** — for Address Library, Crash Logger, and the
  countless open-source tools this project relies on
- **NVIDIA & AMD** — for releasing Streamline and FidelityFX SDKs under
  permissive licenses, enabling open-source frame generation & upscaling
- **Microsoft** — for open-sourcing Detours
- Everyone who tested and debugged with us along the way
