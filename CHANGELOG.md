# v1.52 - two engine hooks CommunityShaders also owns, made switchable

Reported: DFG installed into a second modpack crashes 0.25 s after the plugin
loads, with the faulting address outside every loaded module.

The crash is a detour collision. Both DFG and CommunityShaders write a jump over
the same two engine function heads:

    BSInputDeviceManager::PollInputDevices      REL 67315 / 68617
    MenuManager::DrawInterfaceStart             REL 79947 / 82084

Each side believes it is the head of the chain, the second write lands on a jump
target the first one owns, and the process takes an `EXCEPTION_BREAKPOINT`
before the main menu finishes drawing.

Neither hook is load-bearing for this plugin:

- `MenuManager::DrawInterfaceStart` lands on `OnMenuDrawStart()`, which has been
  an empty function since v0.50 — the DLSS upscaler it fed was removed and its
  `kFRAMEBUFFER` path is unreachable. Suppressing this detour costs only the
  "just before UI draw" timing point.
- ImGui input does not go through `PollInputDevices`. The mouse is read with
  `GetCursorPos` + `GetAsyncKeyState`, and the keyboard arrives through
  `ToggleInputHandler`'s `AddEventSink`, registered before the detour is
  written. Suppressing this one costs only "the mouse turns the camera while the
  menu is open".

Both are now settings rather than constants:

    MenuDrawHook=1     1 = detour MenuManager::DrawInterfaceStart (default)
    PollInputHook=1    1 = thunk BSInputDeviceManager::PollInputDevices (default)

Default 1 keeps the behaviour of v1.51 bit-for-bit; a pack that ships
CommunityShaders must set both to 0. Both values are logged at INI load, and a
`LEGACY-HOOK SUPPRESSION ACTIVE` warning is printed at `kDataLoaded` when either
is 0, so "was it even read" can never be confused with "it was read and did
nothing".

Also in this round: MSVC now gets `/utf-8`. The sources are UTF-8 without a BOM,
and without the flag MSVC decodes them using the system ANSI code page (936
here), which mangles every Chinese literal. `/wd4819` was already suppressing the
one warning that would have reported it, which is how that class of breakage
stays invisible.

---

# v1.51 - the v1.50 probes removed, behaviour unchanged

v1.50/v1.51 were instrumented builds: they logged the camera field family and the
projection inverse and changed nothing about how a frame is produced. With their
questions answered the probes are deleted and the build returns to the v1.49
code path. The two `viewSL[0] = sl::float4(vm[0][0]...` sites that carry the
v1.49 fix are both still present, and the bilingual strings are intact in the
binary.

---

# v1.50 - camera field family, and one self-falsification

Instrumentation only. Three findings, one of which retracts an earlier claim:

- `curProj` and `prevProj` are identical element-for-element in every sampled
  frame, so the earlier "CameraProj is the only untested input, therefore it must
  be the cause" reasoning was unsound — being untested is not evidence.
- `inv(CameraProj)` equals `CameraProjUnjittered` exactly, so those two fields
  are not a naming trap; they have different consumers.
- The `[CAMVP] tr` reading is `projSL[3] @ V`, not a translation.

---

# v1.49 - the double transpose, at both sites

`rebuildViewProj` transposed the matrix twice on the way into `clipToPrevClip`:
the values were right in memory and wrong at the consumer. Both sites — the
yaw/pitch read and the field-family build — now read `vm[0][0], vm[1][0],
vm[2][0]` in the intended order. Verified by anchor count: the fixed form appears
exactly twice, the old `vm[0][0], vm[1][0], vm[2][0]` ordering zero times.

---

# v1.48 - two probes that were themselves wrong, and the data that caught them

Both probes in this round produced a wrong comparison before a useful one, and in
both cases the run's own numbers caught it rather than a second reading of the
code:

- Probe 1 compared `rows[0..2].xyz` against a reference row that was itself
  transposed, so it reported a difference where there was none.
- Probe 2 "fixed" that by moving the read to a different row, which compared two
  different quantities and reported a match that was not a match.

The useful output is the negative result: the camera blocks are internally
consistent, and the corruption is introduced by the consumer, not the producer.

---

# v1.47 - 4K: the guide was declared full-resolution while holding a subrect

At 4K the neural-rendering guides were declared at output size while the
depth/mvec content occupied only the render-resolution subrect of those targets,
so inference read pixels that had never been written. The declared extent is now
the render size, which is where the data actually is.

---

# v1.46 - bilingual menu, CJK font, and MFG persistence

Three changes that trace back to one complaint: the menu told the user things the
user could not act on.

**Bilingual labels.** Every label, checkbox and readout is Chinese first, English
after, and the font is loaded with CJK coverage so the Chinese renders instead of
showing as boxes.

**The multiplier readout is three-state.** It used to show only the requested
value, which made "I changed it in the menu" indistinguishable from "it was
saved" and from "this is what is actually on screen". Requested, stored and
in-effect are now shown separately.

**MFG persistence, and why it needs a switch.** This plugin's own
`DLSSGFramesToGenerate` is read only by this plugin. The multiplier that reaches
the screen is decided by `DLSSG-Transfusion`, a third-party injector that reads
`<game dir>\DLSSG-Transfusion.json` once at startup and then re-applies it on the
render thread, overwriting any `SetOptions` request this plugin makes. Writing our
own INI from the menu was therefore "change it and nothing changes" — after a
restart the json value wins again.

The only way to make "menu -> restart -> in effect" true is to write that json,
which belongs to another author:

    WriteTransfusionConfig=0    0 = write only our own INI (default, safe)
                                1 = also write the Transfusion json, with an
                                    automatic backup taken before each write

Default off. The plugin does not touch another author's file unless the user ticks
the box in the menu.

---

# v1.45 - multi-layer neural rendering (`NRLayers`)

Neural rendering runs the frame through N passes in series: layer k takes layer
k-1's output as its colour input, while the depth/mvec guides are shared across
all layers because it is the same frame and the same camera.

Each layer is an independent NGX Feature 18 instance with its own temporal
history and internal resources, so the layer count is simultaneously the upper
bound on per-frame cost and on VRAM. It is not free restacking. The pool went
from 2 hard-coded slots to `kMaxNRLayers` (8), and the output no longer carries an
exclusive-read description because the next layer reads it as an input.

    NRLayers=1     off (v1.44 behaviour, default)
    NRLayers=N     N passes in series, 2..8

---

# v1.44 - FenceWaitBusy: where the wait sits on the fence

The one knob that separates this build from the Sep 11 build at the end of
`Present()`, and the two behaviours differ by a whole frame of CPU/GPU overlap.

Every frame signals the shared fence on the D3D12 queue and then waits for it.
`d3d11Fence` and `d3d12Fence` wrap the *same* fence object, so the wait can sit on
either timeline:

    1 = the CPU polls d3d12Fence->GetCompletedValue() until it passes. The poll
        runs on the render thread, so the CPU submits a frame and then blocks
        until the GPU has finished it; no frame is prepared while the previous
        one executes. Keeps the v1.03b anti-freeze guard.
    0 = d3d11Context->Wait(d3d11Fence, v). The wait is queued on the D3D11
        timeline and the CPU returns at once — what the Sep 11 build did, and why
        it reached 56.12 base fps at 2K. Cannot hang the CPU, but a fence that is
        never signalled stalls the D3D11 queue instead.

Measured on the same box, same 2K output, same FSR3 2x chain:

    Sep 11 build (queue-side wait)     base 56.12 fps (17.8 ms)
    CPU-poll build                     base 36.08 fps

The watchdog number alone is not proof — it reports exactly where the code was
told to block. Hence a switch, not a conclusion. If the game freezes on mode 0,
this line is the one to flip back.

---

# v1.43 - neural rendering: guide resolution separated from output resolution

The neural-rendering guides (depth, motion vectors) are sampled at their own
resolution rather than at output resolution, and the copy is sized to match.
`NRRenderScale` was introduced in the same pass.

---

# v1.42 - the perf/quality preset reaches `Evaluate`

The upscaler's perf/quality preset was set on the feature options but never
reached the `sl::DLSSOptimalSettings` call that consumes it, so the plugin asked
for the mode it wanted and got the default.

---

# v1.41 / v1.40 - neural rendering input size, taken from the texture

Two rounds on the same class of mismatch: a view built from one size and a
dispatch from another. Both now derive from the descriptor they are used with.

---

# v1.39 - `NRRenderScale` written back, and the FG interplay documented

`NRRenderScale` is persisted like the other knobs. Documented that neural
rendering and frame generation size their work independently, so scaling one does
not scale the other.

---

# v1.38 - scale-aware depth guide (`NRRenderScale`)

`CopyDepthGuideCS.hlsl` now maps by UV instead of copying texel-for-texel:

    srcUV   = (dispatchThreadID.xy + 0.5) / destinationSize
    srcTexel = int2(srcUV * sourceSize), clamped to source bounds

When `width == sourceWidth` this is an identity mapping, so the DRS 1:1 subrect
path is byte-for-byte unchanged; a smaller destination gives a nearest-neighbour
downscale that stays aligned with the colour/mvec downscale.

`NRRenderScale` itself was added alongside it so neural rendering can be scaled
independently of the engine render scale — `RenderResolutionScale` lowers the
engine resolution but does not lower the neural-rendering resolution, because they
are different sizes.

Measured at 4K, world-walking steady state:

    NRRenderScale=1.00     25.9 fps
    NRRenderScale=0.75     40.0 fps   (+54%)

`0.75` was then found to be a non-integer downscale, which samples on an uneven
lattice and shows as shimmer while turning.

---

# v1.37 - the MFG request is tracked apart from the ladder position

The ladder latches `mfgProbeStep` on its first accepted rung and only re-reads
settings when that step is 0 or above the ceiling, so a multiplier changed in the
ImGui menu never reached the runtime. `mfgProbeRequestedStep` now tracks the
requested value separately, which is what makes such a change visible.

---

# v1.36 - INI write-back, and the MFG log carries the ladder state

`SaveSettingsToIni()` writes the settings the menu exposes, so a menu change
survives a restart for the knobs this plugin owns. The MFG log line prints the
ladder state next to the request, so a held value is visible rather than implied.

---

# v1.35 - the menu draw target

The ImGui overlay was drawing into the wrong target once frame generation had
replaced the swap chain. It now draws into the wrapped back buffer, matching the
D3D12 swap chain's actual layout.

---

# v1.34 - ForceBackBufferCopy, and the back-buffer probe's self-witness

A second DLSS-G writer (`DLSSG-Transfusion`, loaded as `dinput8.dll`) was renamed
away before launch. Its log was untouched for the whole session and the freeze was
bit-for-bit identical, so the second writer is not the cause and the break is
downstream of the copy.

Added `ForceBackBufferCopy` (default off). With it on, the passthrough
`CopyResource` runs even when `dlssgOk` is true, overwriting whatever DLSS-G did
or did not put in the back buffer with our own `colorOut`:

    picture comes back   -> DLSS-G never filled the back buffer
    picture still frozen -> the back buffer does hold new content; the break is in
                            the flip, past us

Diagnostic switch, no effect on a normal run, value printed at INI load.

---

# v1.33 - the back-buffer probe

A 19:11 run forced this. Two instruments disagreed for 28 s: `[PIXEL]` (colourOut,
the D3D11 copy of what we hand *to* DLSS-G) took 74 distinct values while the
`[SCREEN]` capture kept showing 3. That puts the break between them, and exactly
one object sits between them that no instrument had ever read: the D3D12
swap-chain back buffer DXGI actually flips. The probe hashes it.

Three channels then read side by side, each compared only against its own
history:

    [PIXEL]    colourOut      engine image, handed TO DLSS-G
    [BACKBUF]  back buffer    the frame we ask DXGI to present
    [SCREEN]   desktop capture what the panel displays

Same two-phase design as `PixelProbeTick`, and for the same reason (v1.22 copied
and mapped in one call and never produced a single sample): the copy is recorded
on the frame's own command list just before it closes, and harvested on a later
tick once the fence reports that frame done. Nothing waits; a sample that cannot
be read is dropped and counted, never retried inside the same tick. Armed time
plus a one-shot alarm, because an instrument that produces nothing looks exactly
like a healthy one.

---

# v1.32 - the BMP header that was never written, and a screen hash the overlay
#         could not fool

Frame captures were written with a header length taken from the wrong field, so
the files were unreadable in standard viewers.

The screen hash used to decide "did the picture change" was computed over the
region the plugin's own overlay occupies, so the plugin's own frame counter made
every frame look different. The hash now excludes the overlay.

---

# v1.31 - save the picture, and find out whose hand ended the run

Added frame dumps and a run-terminator record, which together answer "the run
stopped — was that us, the game, or the OS".

---

# v1.30 - read the screen, and fix the 4x test that could never fire

Added a screen-region hash so "did the image change" could be answered without a
human looking. Also fixed a 4x-path test whose guard condition was never true, so
it had been reporting success without ever executing.

---

# v1.29 - two torn edge detectors, and two instruments that could not see

Two edge detectors read their state non-atomically across threads, so a
transition could be reported twice or missed; both now read once per frame into a
local. Two instruments added earlier could not observe the events they were added
to observe.

---

# v1.28 - the flicker gate requires a return, and the watchdog gets an OS reading

The flicker gate latched on the first transition and never reset, so it reported
one event forever; it now requires a return to the prior state before firing
again. The watchdog gained `GetThreadTimes` so a hitch caused by the OS scheduling
the thread away is distinguishable from one caused by the code blocking.

---

# v1.27 - session boundaries in the log

Each run writes a `RUN START` line carrying the DLL path, its modification time,
its size and the build timestamp. This is what makes "which build produced these
numbers" a fact in the log instead of something inferred from a file listing
afterwards.

---

# v1.24 - v1.23's own claim checked

Verification-only round. The v1.23 change was re-tested from the artifacts, and
the result is recorded whether or not it matched the expectation.

---

# v1.23 - camera: what a published matrix is allowed to be

The camera publisher now rejects matrices that are structurally invalid (row 3
not `(0,0,0,1)`, or a determinant outside the range a projection can have)
instead of adopting them and reporting them as the camera.

---

# v1.22 - the published camera is not always the camera

The engine's published camera block is stale or uninitialised in some states
(loading screens, the main menu), so the plugin now requires the published matrix
to be plausible before using it rather than reading whatever is there.

---

# v1.21 - the fader menu is not a menu

`IsMenuOpen("Fader Menu")` is true the whole time the player is in the world, so
counting it as a menu engaged the v0.63 menu guard on essentially every frame and
suppressed DLSS-G for entire sessions.

---

# v1.20 - the camera source is written down

Documentation round: the `[CAMSOURCE]` investigation recorded which engine camera
block each value actually comes from, so the next investigation starts from a fact
instead of a guess.

---

# v1.19 - read the source, publish what the consumer expects

The camera reader and the camera publisher now derive from the same source,
instead of one reading a raw field and the other a processed one.

---

# v1.18 - the camera field family

Introduced the `[FLD]` table so each candidate matrix can be identified by its
shape in the log rather than by its reported name.

---

# v1.17 - `non-affine` is a diagnostic, not a verdict

A matrix with `w != 1` in the last row is legitimate for a projection. The
detector now reports it and lets the consumer decide, instead of rejecting the
frame.

---

# v1.16 - the reprojection source is stated

The log now says which matrix the reprojection actually used (`reproj src=`),
rather than leaving it to be inferred from the code path taken.

---

# v1.15 - clamped camera: report the clamp, not the clamped value

When the published camera was clamped, only the post-clamp value was recorded,
which read as a smooth camera. Both values are now recorded.

---

# v1.14 - the reset flag

The camera reset flag is tracked and reported. A missing reset is the difference
between "the camera jumped" and "the camera teleported", and the two reproject
differently.

---

# v1.13 - first frame of a session

The first frame after a load has no previous camera; the plugin now recognises
that state instead of reprojecting against uninitialised memory.

---

# v1.12 - Reflex cap: the check is printed where it can be read

The Reflex frame-rate cap calculation is printed at the point it decides, with the
numbers it decided from.

---

# v1.11 - motion vector scale

`mvecScale` is reported and overridable. The engine's scale and the scale the
runtime expects are not always the same number.

---

# v1.10 - the depth guide

The depth guide is copied and handed to the runtime in the layout it expects,
instead of being declared at output size and read at render size.

---

# v1.09 - the flicker gate

Added the frame-to-frame screen hash gate that decides whether the presented image
actually changed, so "it is flickering" became a measurement.

---

# v1.08 - interop fence ordering

Restore the fence ordering between the D3D12 writes and the D3D11 reads. Without
it the two devices touch the shared textures with no ordering at all — a race that
shows up as intermittent corruption rather than as a crash.

    InteropFenceWait=1    1 = fence before the D3D11 read (default)
                          0 = the v0.75 behaviour

---

# v1.07 - DLSS-G options: send what the runtime reads

The options struct was filled with field names from the header rather than with
the fields the runtime reads, so several settings went out as defaults.

---

# v1.06 - the upscaling ratio reaches the runtime

`RenderResolutionScale` was stored and reported but never reached the runtime's
evaluation, so the upscaler ran at 1:1 regardless.

---

# v1.03b - the anti-freeze guard on the fence wait

The CPU-side fence poll gained a timeout that drops a frame rather than hanging
the render thread. This is the guard referenced by `FenceWaitBusy` above.

---

# v0.94 - DLSS upscaling: hand the runtime the render size, not the output size

The upscaler was given the output size as its input size, so it read a subrect of
the render target and produced a soft image.

---

# v0.86 / v0.84 / v0.83 - the menu guard

Three rounds on the menu guard: what counts as a menu (v0.83); why a guard that
never releases suppresses frame generation for a whole session (v0.84); and
`MenuDisableFrameGen`, which keeps the 2D UI out of the interpolation path and is
what stops the main menu flickering (v0.86).

---

# v0.75 - DLSS-G writes through D3D11 with no ordering

The build referenced above as the "no fence ordering" baseline. `InteropFenceWait`
(v1.08) restores the ordering this version omitted.

---

# v0.63 - the original menu guard

While a menu is open, frame generation is suppressed. See v1.21 for the case where
this guard was engaged permanently.
