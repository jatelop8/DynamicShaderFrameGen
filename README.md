# DynamicShaderFrameGen

SKSE plugin for The Elder Scrolls V: Skyrim Special Edition — **FrameGen (frame
interpolation, FSR3 tech, works on ALL GPUs including NVIDIA) + DLSS Upscaling**,
fully compatible with ENB. Fully open-source:
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
- **DLSS-NR (Neural Rendering)** — not bundled since v0.25; neural rendering is
  provided by the external ReShade addon route (dlss5-dx11-bridge + renodx-dlss5),
  keeping this plugin clean of any NVIDIA-binary patching code.
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

**DLSS-NR**: since v0.25 the plugin no longer integrates DLSS-NR internally —
use the external ReShade addon route (dlss5-dx11-bridge + renodx-dlss5).

## Usage

| Key | Action |
|---|---|
| Hold `Home` | Open / close the in-game menu |
| Menu → Frame Generation (FG) | Toggle FSR 3.1 frame generation |
| Menu → DLSS Upscale | Toggle DLSS upscaling / DLAA rebuild |
| Menu → Quality Mode / Sharpness | Adjust DLSS settings (live) |
| Menu → Save to INI | Persist settings |

`EnableUpscale=0` in the INI disables DLSS and returns to pure frame
generation (highest frame rate, native engine image).

## Architecture

1. Engine renders to its render targets (kMAIN); the plugin's swap-chain proxy
   exposes a D3D11 shared texture as the backbuffer.
2. `Main_UpdateJitter` hook (render-time) sets the engine dynamic-resolution
   ratio and DLSS Halton jitter.
3. `Present`: DLSS upscales the frame (backbuffer → `colorOut`, 4K) → FSR 3.1
   Frame Generation is dispatched on the D3D12 swap chain → presented.
4. FSR3 FG consumes depth / motion vectors (copied to shared textures and
   upscaled by the bundled HLSL shaders under `Shaders/Upscaling/`).

## Building from source

Requirements: Visual Studio 2022+ Build Tools (MSVC x64), CMake ≥ 3.24, Ninja,
vcpkg (spdlog, directxtk, detours preinstalled), a local CommonLibSSE-NG clone.

```bat
build_ninja.bat   :: loads VsDevCmd → cmake --preset NINJA → build → deploy
```

Output: `build\NINJA\DynamicShaderFrameGen.dll` (auto-deployed to
`SKSE\Plugins\` under the mod folder configured in the script). The Streamline
and FidelityFX runtimes are loaded at runtime from your own SDK installs.

## Troubleshooting

- **Nothing happens in-game** — verify SKSE64 + Address Library (1.6.1170) are
  installed and the mod is enabled in MO2; check
  `My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`.
- **FG works but DLSS menu disabled** — non-NVIDIA GPU or Streamline missing.
- **FPS counter shows 2×** — frame generation is active (displaying
  interpolated frame rate); the NVIDIA overlay often cannot read it (proxy
  chain), use the in-game overlay instead.
- **ENB + ReShade** — both are supported; install order does not matter (each
  proxies a different API layer).

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
| DLSS session establishment pattern (D3D11/D3D12 Init sequence, driver core loading) | **Skyrim-Upscaler** (PureDark) — https://github.com/PureDark/Skyrim-Upscaler | MIT | DLSS session setup in `src/FrameGen.cpp` (NGX integration studied during early development) |
| NGX direct-integration initialization (core library loading, parameter allocation, feature create/evaluate sequence) | **PDPerfPlugin** (bundled in Skyrim-Upscaler) — https://github.com/PureDark/Skyrim-Upscaler (extern/PDPerfPlugin) | MIT | NGX initialization research (removed with DLSS-NR in v0.25) |
| DLSS5 / DLSS-NR independent D3D12 session architecture ("second NGX session on its own device") | **dlss5-dx11-bridge** (NIGos) — https://github.com/NIGos/dlss5-dx11-bridge | MIT | DLSS-NR session design research (removed with DLSS-NR in v0.25) |
| Logging library | **spdlog** (Gabi Melman) — https://github.com/gabime/spdlog | MIT | build dependency (logging) |
| Math / texture utilities | **DirectXTK** (Microsoft) — https://github.com/microsoft/DirectXTK | MIT | build dependency (via CommonLibSSE-NG) |

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
