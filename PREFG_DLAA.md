# PreFgDLAA — design notes

`PreFgDLAA` is an optional setting (written against v1.52):

```ini
PreFgDLAA=1
```

Default is `0`, which leaves the plugin's behaviour unchanged.

## What it does

With `Provider=1` (DLSS-G) the plugin runs a D3D12 Streamline session that never evaluates DLSS
super resolution. Tools that attach to the game's DLSS evaluate therefore find nothing to attach to.
The typical case is the RenoDX DLSS 5 ReShade add-on in its **After Upscaling** hook point: it loads,
reports `NOT_ENGAGED`, and never processes a frame.

`PreFgDLAA=1` makes the plugin evaluate DLSS in **DLAA mode** (render size = output size) on the
finished frame, on the D3D12 present path, right before the frame is tagged for DLSS-G:

1. `slDLSSSetOptions` with `DLSSMode::eDLAA` at the swap chain size.
2. The shared colour copy is tagged as scaling input, a new UAV texture as scaling output, together
   with the depth and motion vector textures the plugin already shares for DLSS-G.
3. `slEvaluateFeature(kFeatureDLSS)` on the present command list.
4. The DLAA output becomes the HUD-less colour for DLSS-G and the source of the back buffer copy.

The pass is skipped while the menu guard blocks frame generation, and on any failure the plugin falls
back to its normal path for that frame.

## Why

Frame order with the setting on:

```
game (D3D11) + ENB  ->  shared copy  ->  DLAA (D3D12)  ->  [add-on hooks here]  ->  DLSS-G  ->  display
```

An add-on that hooks the DLSS evaluate now runs once per real frame, before interpolation, on a real
DLSS call with engine depth and motion vectors — the same situation as in a game with native DLSS.

## Tested configuration

One machine only. Treat this as experimental.

- Skyrim SE 1.5.97, SKSE64 2.0.20, ENB 0.505, a large modlist
- RTX 4090, driver 621.01, 2560x1440, borderless
- DLSS-G at 4x through an external MFG unlocker (`MFGMaxFramesOverride=3`)
- ReShade 6.8 as `dxgi.dll` with the RenoDX DLSS 5 add-on v10.8.0, hook point After Upscaling
- Plugin's built-in neural rendering off (`NeuralRenderingEnabled=0`) so the frame is not processed twice

Observed over a 20 minute session: 28,800 DLAA evaluates without a failure, the add-on engaged on
99.99 % of frames, frame generation accepted at 4x.

## Known limits

- The input is the **final** frame, HUD included, so the HUD goes through DLAA and through whatever
  hooks the evaluate.
- The frame is already anti-aliased by the game's TAA and carries no sub-pixel jitter; DLAA acts as an
  additional temporal pass here, not as a replacement for TAA.
- The pass costs GPU time on every real frame.
- Not tested with `Provider=0` (FSR 3), on AE builds, or on other GPU generations.

## Files touched

`src/Streamline.cpp`, `src/Streamline.h` (new `Streamline::EvaluateDLAA`), `src/DX12SwapChain.cpp`,
`src/DX12SwapChain.h` (output texture, call site, copy source), `src/FrameGen.cpp`, `src/FrameGen.h`,
`src/ImguiMenu.cpp` (setting read and write-back).
