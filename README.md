# DynamicShaderFrameGen

An open-source SKSE plugin that adds **FSR 3.1 Frame Generation**,
**NVIDIA DLSS Upscaling / DLAA** and **DLSS 5 Neural Rendering** to Skyrim
Special Edition (Anniversary Edition 1.6.1170), designed to work side-by-side
with ENB.

Frame generation uses motion-vector based interpolation to double the effective
frame rate and significantly stabilizes frame pacing. Because the plugin proxies
the swap chain (D3D11 shared textures + a D3D12 swap chain), ENB composites its
post-processing onto the shared backbuffer — **ENB effects survive frame
generation**.

Fully open-source, no paid or closed-source runtime is bundled; the Streamline
and FidelityFX runtimes are loaded at runtime from the official NVIDIA / AMD
SDKs.

---

## Features

- **FSR 3.1 Frame Generation** (AMD FidelityFX SDK runtime) — up to 2× effective
  frame rate; works on **any DX12-capable GPU** (NVIDIA / AMD / Intel).
- **NVIDIA DLSS Upscaling and DLAA** (NVIDIA Streamline SDK runtime) — temporal
  upscaling with reconstruction and sharpening; at equal input/output
  resolution it runs as DLAA.
- **DLSS 5 Neural Rendering** (NGX Feature 18, built in since v0.48) — neural
  re-lighting and detail synthesis on top of the upscaled frame, running in
  series with frame generation. See the dedicated section below.
- **ENB compatibility** — verified side-by-side; also works with ReShade (they
  proxy different API layers).
- **In-game ImGui menu** (hold `Home`) — toggle frame generation, DLSS upscale
  mode, sharpness, DLSS 5 neural rendering and its tuning sliders, FPS overlay,
  save to INI.
- **FPS overlay** — a white frame counter in the top-right corner (toggle in
  menu or INI); it doubles automatically while frame generation is active.
- **Render scale via engine dynamic resolution** — the engine render target is
  scaled through the dynamic-resolution hooks (perf gain; the backbuffer stays
  at output resolution). Since **v0.41** the ratio is configurable:
  `RenderResolutionScale=0.70` in the INI (default) or the in-game menu slider
  (30%–100%, live). `0` = Auto (follows the DLSS Quality Mode table).

---

## Requirements

- Skyrim Special Edition — **Anniversary Edition 1.6.1170 only** (1.5.97 is NOT
  supported)
- SKSE64 (2.2.x for AE)
- Address Library for SKSE Plugins (1.6.1170)
- ENB Series — optional but recommended (fully supported; frame generation keeps
  ENB's post-processing intact)
- Any DX12-capable GPU for FSR 3.1 FG; NVIDIA RTX GPU for DLSS / DLAA
- **DLSS 5 Neural Rendering** (optional) — an RTX GPU plus the
  `nvngx_dlssnr.dll` **310.8.x** runtime shipped in this mod's archive

---

## Installation

Install with a mod manager (MO2 / Vortex), or manually: copy the contents of the
mod folder into your Data folder.

```
SKSE/Plugins/DynamicShaderFrameGen.dll
SKSE/Plugins/DynamicShaderFrameGen.ini
Shaders/Upscaling/                  (copy shaders + upscale shaders)
Shaders/Upscaling/FidelityFX/       (AMD FSR3 frame-generation runtime)
Shaders/Upscaling/Streamline/       (NVIDIA Streamline runtime + nvngx_dlssnr.dll)
Shaders/Upscaling/NeuralRendering/  (DLSS5 depth-guide / downscale compute shaders)
```

---

## Usage

Hold `Home` to open the in-game menu.

| Menu / INI | Action |
|---|---|
| Frame Generation | Toggle frame interpolation (FSR 3.1 on all GPUs, or DLSSG on NVIDIA) |
| Frame Gen Provider | `FSR3 (2x, all GPUs)` or `DLSSG (NVIDIA, 3x/4x MFG)` — needs a restart |
| MFG Multiplier | 2x / 3x / 4x (3x–4x requires RTX 50; 40-series clamps to 2x) |
| DLSS Upscale | Toggle DLSS upscaling / DLAA rebuild |
| Quality Mode / Sharpness | Adjust DLSS settings (live) |
| DLSS5 Neural Rendering | Enable the built-in neural render pass + its tuning sliders (Intensity, Local Tone, Local Structure, Skin Structure, Style, Automatic Mask, UI Correction, DLSSNR Render Scale) |
| Render Resolution Scale | Engine render = output × scale (30–100%, live; Auto = Quality Mode table) |
| FPS Overlay | Toggle the top-right frame counter |
| Save to INI | Persist all settings |

`EnableUpscale=0` in the INI disables DLSS and returns to pure frame generation
(highest frame rate at native resolution).

`RenderResolutionScale` — Skyrim's engine always renders at 100% resolution, so
DLSS has nothing to upscale and the full-res render cost is paid anyway. Setting
`RenderResolutionScale=0.70` renders at 70% (e.g. 1792×1008 at 1440p output) and
DLSS upscales back to output resolution — real upscaling, a large FPS gain, and
a proper low-res input for DLSS5 / neural rendering. `0` = Auto (follows the
Quality Mode table: DLAA 100% / Quality 66.7% / Balanced 58.5% / Performance
50% / Ultra Performance 33.3%).

---

## Architecture

1. Engine renders to its render targets (kMAIN); the plugin's swap-chain proxy
   exposes a D3D11 shared texture as the backbuffer.
2. `Main_UpdateJitter` hook (render-time) sets the engine dynamic-resolution
   ratio and DLSS Halton jitter.
3. `Main_PostProcessing` hook — since **v0.48** DLSS upscales `kMAIN` into the
   output-resolution wrapper texture and copies it back into `kMAIN`, so the
   engine's post-processing (including ENB) reads the *upscaled* frame. This is
   what makes DLSS sharpening / preset LMK actually visible: previously the
   upscale ran in `Present`, after ENB, so ENB's own post-processing painted
   over the sharpening.
4. `Present` — the backbuffer is copied into `colorOut`. When **DLSS 5 Neural
   Rendering** is enabled, the neural pass runs on that frame (engine depth +
   motion vectors as guides, private D3D12 session) and its result feeds frame
   generation.
5. FSR3 / DLSSG frame generation is dispatched on the D3D12 swap chain and
   presented; it consumes depth / motion vectors copied to shared textures and
   upscaled by the bundled HLSL shaders under `Shaders/Upscaling/`.

---

## DLSS 5 Neural Rendering — now built in (v0.48)

As of **v0.48** the plugin drives DLSS 5 neural rendering (NGX **Feature 18**,
`nvngx_dlssnr.dll`) **natively from inside the plugin** — no ReShade add-on, no
`dlss5-dx11-bridge`, no proxy DLLs in the game root. The runtime is loaded
directly on the plugin's own private D3D12 session.

- **What it does** — after DLSS upscaling resolves the frame, the neural
  renderer re-lights and re-details the image before UI composition: sharper
  skin, hair, foliage and stone surface detail, with automatic per-pixel
  masking so the effect stays off flat/uniform areas.
- **Runs in series with frame generation** — NR is applied first, frame
  generation interpolates the NR result. (Older builds made the two mutually
  exclusive; that restriction is gone.)
- **GPU support** — RTX 20 / 30 / 40 / 50. RTX 40/50 give the best
  quality-per-cost; RTX 20/30 work with a higher performance cost, since the
  network runs on FP8 tensor cores with an FP16 fallback.
- **Runtime requirement** — `nvngx_dlssnr.dll` **310.8.x** must be present at
  either of these paths (the mod archive ships it; if you removed it, restore
  it from the archive):

  ```
  Data/Shaders/Upscaling/Streamline/nvngx_dlssnr.dll
  Data/Shaders/Upscaling/StreamlineDX12/nvngx_dlssnr.dll
  ```

  Any other version is rejected at load and logged — the plugin stays off
  rather than misbehaving.
- **In-game tuning** (hold `Home` → *DLSS5 Neural Rendering* section):
  Intensity, Local Tone, Local Structure, Skin Structure, Style (0–3),
  Automatic Mask, UI Correction, and **DLSSNR Render Scale** (0.25–1.0, lower =
  faster but less detail; 1.0 = full-resolution analysis). All values persist
  to the INI via *Save to INI*, and the menu shows a live status line plus a
  successful-frames counter.

> **External ReShade route (alternative).** If you already run the DLSS5
> ReShade pack (`dlss5-dx11-bridge` + `renodx-dlss5` + `nvngx_dlssnr.dll` in the
> game root), that still works and coexists with this plugin — ReShade proxies
> `dxgi.dll` while this plugin owns its own swap-chain proxy. Use **either** the
> built-in NR **or** the ReShade add-on, not both at once, or the image gets two
> passes of neural processing.

---

## Building from source

Requirements: Visual Studio 2022+ Build Tools (MSVC x64), CMake ≥ 3.24, Ninja,
vcpkg (spdlog, directxtk, detours preinstalled), a local CommonLibSSE-NG clone.

```bat
build_ninja.bat   :: loads VsDevCmd → cmake --preset NINJA → build → deploy
```

Output: `build\NINJA\DynamicShaderFrameGen.dll` (auto-deployed to
`SKSE\Plugins\` under the mod folder configured in the script). The Streamline
and FidelityFX runtimes are loaded at runtime from your own SDK installs.

---

## Troubleshooting

- **Nothing happens in-game** — verify SKSE64 + Address Library (1.6.1170) are
  installed and the mod is enabled in MO2; check
  `My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log`.
- **DLSS menu greyed out** — non-NVIDIA GPU or Streamline runtime missing.
- **FPS counter shows 2×** — frame generation is active (the overlay displays
  the interpolated frame rate). Most external overlays (NVIDIA overlay, etc.)
  report only the internal frame rate because of the proxy chain — use the
  in-game overlay for the true frame-generated rate.
- **ENB + ReShade** — both are supported; install order does not matter (each
  proxies a different API layer).
- **Not compatible with other frame-generation / upscaler plugins**
  (SkyrimUpscaler, other FSR3-only plugins, etc.) — use one at a time.
- **DLSS5 Neural Rendering does nothing** — check the log for the `[DLSSNR]`
  lines. The runtime must be `nvngx_dlssnr.dll` **310.8.x** under
  `Shaders/Upscaling/Streamline/`; any other version is rejected at load
  (logged as `expected DLSSNR 310.8.x, found …`). An RTX GPU is required.
- **Picture looks double-sharpened** — the built-in neural rendering and the
  external ReShade DLSS5 add-on are both active. Disable one of them.

---

## Code Sources & Attributions

This project is fully open-source and builds on the following projects. Each
component is used under its own license; full attribution is provided to avoid
any ambiguity:

| Component | Source | License | Used for |
|---|---|---|---|
| D3D12 swap-chain proxy, dynamic-resolution hooks, Halton jitter, DRS ratio, DLSS upscaling integration | **Community Shaders** (doodlum / Pentalimb) — https://github.com/doodlum/skyrim-community-shaders | GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception | `src/DX12SwapChain.*`, `src/FrameGen.cpp`, `src/Streamline.*` (code) |
| DLSS 5 Neural Rendering integration — NGX Feature 18 runtime wrapper, D3D11 front-end, D3D12 interop, tuning parameter set | **Community Shaders** fork `YtzyFvra/skyrim-community-shaders`, branch `feature/dlssnr-vr` (upstream: https://github.com/doodlum/skyrim-community-shaders) | GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception | `src/NeuralRendering/Runtime.*`, `src/NeuralRendering/Renderer.*`, `src/NeuralRendering/D3D12Interop.*`, `Shaders/Upscaling/NeuralRendering/*.hlsl` |
| FSR 3.1 Frame Generation integration (runtime table loading, swap-chain creation, per-frame configure/dispatch) | **ENBFrameGeneration** (doodlum / Pentalimb) — https://github.com/doodlum/ENBFrameGeneration | GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception | `src/FidelityFX.cpp` |
| In-game menu + FPS overlay | **Dear ImGui** (Omar Cornut) — https://github.com/ocornut/imgui | MIT | `src/ImguiMenu.*`, `extern/imgui` (vendored) |
| DLSS upscaling runtime | **NVIDIA Streamline SDK** — https://github.com/NVIDIA/streamline | Streamline SDK License | runtime DLLs (loaded at runtime, not bundled) |
| FSR 3.1 FG runtime | **AMD FidelityFX SDK** — https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK | AMD License (MIT-style) | FSR3 runtime loading |
| RE / REL framework | **CommonLibSSE-NG** (Ryan-rsm-McKenzie, alandtse) — https://github.com/alandtse/CommonLibSSE-NG | MIT | Whole plugin framework |
| Function detours | **Microsoft Detours** — https://github.com/microsoft/Detours | MIT | detours |
| DLSS session establishment pattern | **Skyrim-Upscaler** (PureDark) — https://github.com/PureDark/Skyrim-Upscaler | MIT | DLSS session setup research |
| DLSS5 external ReShade add-on route (documented alternative) | **dlss5-dx11-bridge** (NIGos) — https://github.com/NIGos/dlss5-dx11-bridge | MIT | Design reference for the optional ReShade-based DLSS5 route (not bundled) |
| Logging library | **spdlog** (Gabi Melman) — https://github.com/gabime/spdlog | MIT | build dependency |
| Math / texture utilities | **DirectXTK** (Microsoft) — https://github.com/microsoft/DirectXTK | MIT | build dependency (via CommonLibSSE-NG) |

No code was taken from closed-source or paid projects. This repository contains
no NVIDIA Streamline or AMD FidelityFX binaries — those runtimes are loaded from
the official SDK installs at runtime.

---

## License

**GPL-3.0-or-later WITH Modding Exception AND GPL-3.0 Linking Exception** — see
[LICENSE](LICENSE) and [EXCEPTIONS.md](EXCEPTIONS.md).

This project derives from **Community Shaders** and **ENBFrameGeneration** (both
GPL-3.0), so this project is released under the same license, with full
attribution in the table above.

Note: the *runtime DLLs* loaded by this plugin (NVIDIA Streamline, AMD
FidelityFX) are subject to their respective SDK licenses; they are not part of
this repository.

---

## Credits

- doodlum (Pentalimb) — Community Shaders, ENBFrameGeneration
- Omar Cornut — Dear ImGui
- alandtse, Ryan-rsm-McKenzie — CommonLibSSE-NG
- NVIDIA Streamline, AMD FidelityFX, Microsoft Detours teams
- Skyrim Script Extender (SKSE) team
- NIGos — dlss5-dx11-bridge (DLSS5 external route)
- The RenoDX community — DLSS5 neural rendering addons

## Special Thanks

- **doodlum / Pentalimb** — for the open-source Community Shaders ecosystem and
  ENBFrameGeneration, which made the FSR3 + ENB coexistence possible
- **The Skyrim modding community** — for Address Library, Crash Logger, and the
  countless open-source tools this project relies on
- **NVIDIA & AMD** — for releasing Streamline and FidelityFX SDKs under
  permissive licenses, enabling open-source frame generation & upscaling
- **Microsoft** — for open-sourcing Detours
- Everyone who tested and debugged with us along the way

---

*If you enjoy the mod, please endorse it! Bug reports and feature requests are
welcome on the Posts / Bugs tabs.*
