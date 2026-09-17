#!/usr/bin/env python3
"""
patch_v056.py - DynamicShaderFrameGen v0.55 -> v0.56

Fixes the one defect that static analysis can *prove* is wrong, and adds the
probes that make the remaining unknowns decidable in a single game launch.

THE DEFECT (proven, three independent sources disagree for the same two buffers):

  DLSS-G is handed depth + motion-vector textures that are physically 2560x1440:

    * src/DX12SwapChain.cpp Present(), lazy interop creation
      "depth interop texture created lazily (R32_FLOAT 2560x1440)"
      "mvec interop texture created lazily (2560x1440)"          <- runtime log
    * CopyDepthToShared / CopyMvecToShared draw a fullscreen triangle with
      viewport = swapChainDesc.Width x Height, so the WHOLE 2560x1440 texture
      is valid content, not just a corner.
    * sl_dlss_g.h: mvecDepthWidth = "Expected width of the input render targets
      (depth, motion-vector buffers etc)" -> the plugin passes 2560x1440. Correct.

  ...but the resource tag said 1706x960:

    sl.h, ResourceTag::extent --
      "The area of the tagged resource to use (if using the entire resource
       leave as null)"

  So DLSS-G was told: colour = 2560x1440, depth/motion = the top-left 1706x960
  area only. The colour/MV spatial correspondence is off by 1/0.667 = 1.5x, which
  is exactly the input DLSS-G uses to build every generated frame -> every
  generated frame carries wrong motion, so the display alternates correct frame /
  wrong frame at the generated rate. That reads as continuous flicker.

  Confirmed from the outside as well - DLSSG-Transfusion logged the tags it
  received in the 16:34 run:

    [MOTION-TAG] type=hudless         rect=(0,0 2560x1440)
    [MOTION-TAG] type=scaling-output  rect=(0,0 2560x1440)
    [MOTION-TAG] type=depth           rect=(0,0 1706x960)   <- wrong
    [MOTION-TAG] type=motion          rect=(0,0 1706x960)   <- wrong

  The stale value comes from v0.34, when the interop textures really were render
  resolution. v0.7.8 resized them to the output resolution and never updated the
  tag.

FIX: stop hardcoding any of the three numbers. Take the extent straight from the
D3D12 resource, and the options' mvec/depth size from the D3D11 interop texture.
One source of truth, so they cannot drift apart again.

ALSO: CreateInterop's eager path creates depth/mvec from the engine kMAIN desc
(render resolution) while the lazy path forces the output resolution - the same
buffers, two different sizes depending on which path happens to run. Both now use
the output resolution, which is what FSR3 frame generation requires anyway.

INSTRUMENTATION (so one launch settles what static analysis cannot):

  * "DLSSG tag dims:" - the declared extents, printed once. Must read 2560x1440
    for depth and mvec on the next run.
  * "MOTION probe:" - clipToPrevClip deviation from identity, every 600 frames.
    Transfusion's log shows clipToPrev=identity for the first 4 frames of a run,
    which is expected on a loading screen but fatal during gameplay: DLSS-G would
    lose camera reprojection entirely. This tells us which it is.
  * "Present called with ... Flags=" - only printed when the flag word changes.
    DXGI_PRESENT_ALLOW_TEARING in that argument permits real tearing.

Assertion rules:
  * every anchor must match EXACTLY once (0 = stale, >1 = ambiguous -> REFUSE)
  * insertions are guarded by a marker, because a unique anchor does not prove
    the patch has not already run
  * dry run by default; nothing is written without --apply
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APPLY = "--apply" in sys.argv


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


problems = []
planned = []

# =============================================================== Streamline.cpp
P_SL = os.path.join(ROOT, "src", "Streamline.cpp")
sl = read(P_SL)
sl_before = sl

if "DLSSG tag dims:" in sl or "MOTION probe:" in sl or "DLSSG options dims:" in sl:
    problems.append("Streamline.cpp: v0.56 markers already present -> refusing")

# --- E1: options mvec/depth size must come from the real interop texture -------
E1_OLD = """\t\topts.mvecDepthWidth = a_mvecDepthW;
\t\topts.mvecDepthHeight = a_mvecDepthH;
"""
E1_NEW = """\t\t// v0.56 (fix: declared != actual). sl_dlss_g.h defines mvecDepthWidth/Height as
\t\t// "Expected width/height of the input render targets (depth, motion-vector
\t\t// buffers etc)" - the size of THOSE buffers, not the swap chain. The caller
\t\t// passed swapChainDesc, which agrees with the lazy-created interop textures
\t\t// (2560x1440) but would NOT agree if CreateInterop's eager path had won (it
\t\t// reads the engine kMAIN desc = render resolution). Derive both from the
\t\t// resource that is actually handed to DLSS-G so they cannot drift apart.
\t\tstd::uint32_t mvecDepthW = a_mvecDepthW;
\t\tstd::uint32_t mvecDepthH = a_mvecDepthH;
\t\t{
\t\t\tauto& dx = Get().dx12SwapChain;
\t\t\tWrappedResource* mvSrc = (dx.depthWrapped && dx.depthWrapped->resource11)
\t\t\t\t? dx.depthWrapped
\t\t\t\t: dx.mvecWrapped;
\t\t\tif (mvSrc && mvSrc->resource11) {
\t\t\t\tD3D11_TEXTURE2D_DESC rd{};
\t\t\t\tmvSrc->resource11->GetDesc(&rd);
\t\t\t\tmvecDepthW = rd.Width;
\t\t\t\tmvecDepthH = rd.Height;
\t\t\t}
\t\t}
\t\topts.mvecDepthWidth = mvecDepthW;
\t\topts.mvecDepthHeight = mvecDepthH;
\t\t{
\t\t\tstatic bool optDimsLogged = false;
\t\t\tif (!optDimsLogged) {
\t\t\t\toptDimsLogged = true;
\t\t\t\tSKSE::log::info("[Streamline] DLSSG options dims: color={}x{} mvecDepth={}x{} "
\t\t\t\t\t"(mvecDepth must equal the real depth/MV interop buffers)",
\t\t\t\t\ta_width, a_height, mvecDepthW, mvecDepthH);
\t\t\t}
\t\t}
"""

# --- E2: tag extents must come from the resource, not from a stale render size -
E2_OLD = """\t\tconst std::uint32_t w = fg.dx12SwapChain.swapChainDesc.Width;
\t\tconst std::uint32_t h = fg.dx12SwapChain.swapChainDesc.Height;
\t\t// v0.34（对齐 CS TagDX12Resources:1005-1021）：depth/mvec 只在渲染分辨率
\t\t// 子矩形有有效数据（DRS 0.667 时全屏 extent 会让 DLSSG 读错运动矢量）——
\t\t// depth/mvec 用 renderExtent，color 用全屏 extent
\t\tconst std::uint32_t rw = std::max(1u, fg.dx12SwapChain.renderWidth);
\t\tconst std::uint32_t rh = std::max(1u, fg.dx12SwapChain.renderHeight);
\t\tsl::Extent extent{ 0, 0, w, h };
\t\tsl::Extent renderExtent{ 0, 0, rw, rh };
\t\tsl::ResourceTag tags[] = {
\t\t\t{ &colorInRes, sl::kBufferTypeHUDLessColor, sl::ResourceLifecycle::eOnlyValidNow, &extent },
\t\t\t{ &colorOutRes, sl::kBufferTypeScalingOutputColor, sl::ResourceLifecycle::eOnlyValidNow, &extent },
\t\t\t{ &depthRes, sl::kBufferTypeDepth, sl::ResourceLifecycle::eValidUntilPresent, &renderExtent },
\t\t\t{ &mvecRes, sl::kBufferTypeMotionVectors, sl::ResourceLifecycle::eValidUntilPresent, &renderExtent },
\t\t};
"""
E2_NEW = """\t\tconst std::uint32_t w = fg.dx12SwapChain.swapChainDesc.Width;
\t\tconst std::uint32_t h = fg.dx12SwapChain.swapChainDesc.Height;
\t\t// v0.56 (flicker root cause, proven). sl.h defines ResourceTag::extent as
\t\t// "The area of the tagged resource to use (if using the entire resource leave
\t\t// as null)". Declaring 1706x960 therefore told DLSS-G to use only the top-left
\t\t// 1706x960 of a 2560x1440 buffer - a 1.5x spatial mismatch against a colour
\t\t// buffer of 2560x1440, which corrupts the motion input of EVERY generated
\t\t// frame. The old renderExtent dates from v0.34, when the interop textures were
\t\t// still render resolution; v0.7.8 resized them to the output resolution and
\t\t// the tag was never updated (Transfusion's MOTION-TAG log in the 16:34 run
\t\t// shows exactly this: hudless/scaling-output 2560x1440, depth/motion 1706x960).
\t\t// Take the extent from the resource itself - correct by construction.
\t\tconst D3D12_RESOURCE_DESC depthDesc = a_depth->GetDesc();
\t\tconst D3D12_RESOURCE_DESC mvecDesc = a_motionVectors->GetDesc();
\t\tsl::Extent extent{ 0, 0, w, h };
\t\tsl::Extent depthExtent{ 0, 0,
\t\t\tstatic_cast<std::uint32_t>(depthDesc.Width), static_cast<std::uint32_t>(depthDesc.Height) };
\t\tsl::Extent mvecExtent{ 0, 0,
\t\t\tstatic_cast<std::uint32_t>(mvecDesc.Width), static_cast<std::uint32_t>(mvecDesc.Height) };
\t\tsl::ResourceTag tags[] = {
\t\t\t{ &colorInRes, sl::kBufferTypeHUDLessColor, sl::ResourceLifecycle::eOnlyValidNow, &extent },
\t\t\t{ &colorOutRes, sl::kBufferTypeScalingOutputColor, sl::ResourceLifecycle::eOnlyValidNow, &extent },
\t\t\t{ &depthRes, sl::kBufferTypeDepth, sl::ResourceLifecycle::eValidUntilPresent, &depthExtent },
\t\t\t{ &mvecRes, sl::kBufferTypeMotionVectors, sl::ResourceLifecycle::eValidUntilPresent, &mvecExtent },
\t\t};
\t\t{
\t\t\tstatic bool tagDimsLogged = false;
\t\t\tif (!tagDimsLogged) {
\t\t\t\ttagDimsLogged = true;
\t\t\t\tSKSE::log::info("[Streamline] DLSSG tag dims: hudless/scaling-output={}x{} depth={}x{} mvec={}x{} "
\t\t\t\t\t"- depth/mvec must read 2560x1440 (the real interop buffers)",
\t\t\t\t\textent.width, extent.height, depthExtent.width, depthExtent.height,
\t\t\t\t\tmvecExtent.width, mvecExtent.height);
\t\t\t}
\t\t}
"""

# --- E3: is the camera matrix live? (insert after the clipToPrev invert) ------
E3_OLD = "\t\tsl::matrixFullInvert(c.prevClipToClip, c.clipToPrevClip);\n"
E3_NEW = """\t\tsl::matrixFullInvert(c.prevClipToClip, c.clipToPrevClip);

\t\t// v0.56 probe: DLSS-G reprojects each generated frame with clipToPrevClip.
\t\t// Transfusion's log shows clipToPrev=identity for the first frames of the run,
\t\t// which is correct on a loading screen but catastrophic during gameplay - an
\t\t// identity matrix tells DLSS-G the camera never moved, so the camera part of
\t\t// the reprojection is silently dropped. This settles which it is: run, walk
\t\t// around, and read maxDevFromIdentity. Near 0 while moving = the matrix is not
\t\t// live and the previous view-projection is not being updated.
\t\t{
\t\t\tstatic std::uint32_t motionProbe = 0;
\t\t\tif (++motionProbe % 600 == 1) {
\t\t\t\tfloat dev = 0.0f;
\t\t\t\tfor (int row = 0; row < 4; ++row) {
\t\t\t\t\tconst sl::float4 r = c.clipToPrevClip[row];
\t\t\t\t\tconst float v[4] = { r.x, r.y, r.z, r.w };
\t\t\t\t\tfor (int col = 0; col < 4; ++col) {
\t\t\t\t\t\tconst float id = (row == col) ? 1.0f : 0.0f;
\t\t\t\t\t\tconst float d = v[col] - id;
\t\t\t\t\t\tconst float a = d < 0.0f ? -d : d;
\t\t\t\t\t\tif (a > dev)
\t\t\t\t\t\t\tdev = a;
\t\t\t\t\t}
\t\t\t\t}
\t\t\t\tconst sl::float4 r3 = c.clipToPrevClip[3];
\t\t\t\tSKSE::log::info("[Streamline] MOTION probe: clipToPrevClip maxDevFromIdentity={:.6f} "
\t\t\t\t\t"r3=({:.5f} {:.5f} {:.5f}) - ~0 while the player is moving means the camera "
\t\t\t\t\t"matrix is NOT live (DLSS-G loses camera reprojection)",
\t\t\t\t\tdev, r3.x, r3.y, r3.z);
\t\t\t}
\t\t}
"""

if sl.count(E1_OLD) != 1:
    problems.append("Streamline.cpp E1 anchor count = %d (want 1)" % sl.count(E1_OLD))
else:
    sl = sl.replace(E1_OLD, E1_NEW, 1)
    planned.append("Streamline.cpp E1 options mvecDepth from the real interop texture")

if sl.count(E2_OLD) != 1:
    problems.append("Streamline.cpp E2 anchor count = %d (want 1)" % sl.count(E2_OLD))
else:
    sl = sl.replace(E2_OLD, E2_NEW, 1)
    planned.append("Streamline.cpp E2 tag extent from the real resource")

if sl.count(E3_OLD) != 1:
    problems.append("Streamline.cpp E3 anchor count = %d (want 1)" % sl.count(E3_OLD))
else:
    sl = sl.replace(E3_OLD, E3_NEW, 1)
    planned.append("Streamline.cpp E3 clipToPrevClip liveness probe")

# ============================================================ DX12SwapChain.cpp
P_DX = os.path.join(ROOT, "src", "DX12SwapChain.cpp")
dx = read(P_DX)

if "eager interop texture fixed to the output resolution" in dx:
    problems.append("DX12SwapChain.cpp: v0.56 markers already present -> refusing")

E4_OLD = """\t\t\t\tif (main.texture) {
\t\t\t\t\tD3D11_TEXTURE2D_DESC dDesc{};
\t\t\t\t\tstatic_cast<ID3D11Texture2D*>(main.texture)->GetDesc(&dDesc);
\t\t\t\t\tdDesc.Format = DXGI_FORMAT_R32_FLOAT;
\t\t\t\t\tdDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;
\t\t\t\t\tdepthWrapped = new WrappedResource(dDesc, d3d11Device.get(), d3d12Device.get());
"""
E4_NEW = """\t\t\t\tif (main.texture) {
\t\t\t\t\tD3D11_TEXTURE2D_DESC dDesc{};
\t\t\t\t\tstatic_cast<ID3D11Texture2D*>(main.texture)->GetDesc(&dDesc);
\t\t\t\t\t// v0.56: eager interop texture fixed to the output resolution. It used to
\t\t\t\t\t// inherit the engine kMAIN desc (render resolution), while the lazy path
\t\t\t\t\t// below forces the output resolution - the same buffer came out at two
\t\t\t\t\t// different sizes depending on which path happened to run. FSR3 frame
\t\t\t\t\t// generation requires depth to match the colour input size anyway.
\t\t\t\t\tdDesc.Width = swapChainDesc.Width;
\t\t\t\t\tdDesc.Height = swapChainDesc.Height;
\t\t\t\t\tdDesc.Format = DXGI_FORMAT_R32_FLOAT;
\t\t\t\t\tdDesc.BindFlags = D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET;
\t\t\t\t\tdepthWrapped = new WrappedResource(dDesc, d3d11Device.get(), d3d12Device.get());
"""
E4_TAIL_OLD = """\t\t\t\t\tdepthWrapped = new WrappedResource(dDesc, d3d11Device.get(), d3d12Device.get());
\t\t\t\t\tSKSE::log::info("[FrameGen] DLSSG: depth interop texture created (R32_FLOAT {0}x{1})", dDesc.Width, dDesc.Height);
"""
E4_TAIL_NEW = """\t\t\t\t\tdepthWrapped = new WrappedResource(dDesc, d3d11Device.get(), d3d12Device.get());
\t\t\t\t\tSKSE::log::info("[FrameGen] DLSSG: depth interop texture created (R32_FLOAT {0}x{1}) [output res]", dDesc.Width, dDesc.Height);
"""

E5_OLD = """\t\t\t\tif (mvecTex.texture) {
\t\t\t\t\tD3D11_TEXTURE2D_DESC mDesc{};
\t\t\t\t\tstatic_cast<ID3D11Texture2D*>(mvecTex.texture)->GetDesc(&mDesc);
\t\t\t\t\tmvecWrapped = new WrappedResource(mDesc, d3d11Device.get(), d3d12Device.get());
"""
E5_NEW = """\t\t\t\tif (mvecTex.texture) {
\t\t\t\t\tD3D11_TEXTURE2D_DESC mDesc{};
\t\t\t\t\tstatic_cast<ID3D11Texture2D*>(mvecTex.texture)->GetDesc(&mDesc);
\t\t\t\t\t// v0.56: same as depth above - both creation paths now agree.
\t\t\t\t\tmDesc.Width = swapChainDesc.Width;
\t\t\t\t\tmDesc.Height = swapChainDesc.Height;
\t\t\t\t\tmvecWrapped = new WrappedResource(mDesc, d3d11Device.get(), d3d12Device.get());
"""

if dx.count(E4_OLD) != 1:
    problems.append("DX12SwapChain.cpp E4 anchor count = %d (want 1)" % dx.count(E4_OLD))
elif dx.count(E4_TAIL_OLD) != 1:
    problems.append("DX12SwapChain.cpp E4 tail anchor count = %d (want 1)" % dx.count(E4_TAIL_OLD))
else:
    dx = dx.replace(E4_OLD, E4_NEW, 1)
    dx = dx.replace(E4_TAIL_OLD, E4_TAIL_NEW, 1)
    planned.append("DX12SwapChain.cpp E4 eager depth texture -> output resolution")

if dx.count(E5_OLD) != 1:
    problems.append("DX12SwapChain.cpp E5 anchor count = %d (want 1)" % dx.count(E5_OLD))
else:
    dx = dx.replace(E5_OLD, E5_NEW, 1)
    planned.append("DX12SwapChain.cpp E5 eager mvec texture -> output resolution")

E6_OLD = """\t\t// v0.5.5: stage marker - pinpoint which D3D11/D3D12 call throws (E_INVALIDARG black screen debug)
\t\tm_stage = "enter";
"""
E6_NEW = """\t\t// v0.5.5: stage marker - pinpoint which D3D11/D3D12 call throws (E_INVALIDARG black screen debug)
\t\tm_stage = "enter";

\t\t// v0.56 probe: does the engine hand DXGI_PRESENT_ALLOW_TEARING to Present?
\t\t// Present(0, ALLOW_TEARING) permits genuine tearing; the swap chain keeps the
\t\t// flag only because Present(0) without it was rejected once (v0.38). Printed
\t\t// only when the flag word changes, so it costs nothing per frame.
\t\t{
\t\t\tstatic UINT lastPresentFlags = 0xFFFFFFFFu;
\t\t\tif (Flags != lastPresentFlags) {
\t\t\t\tlastPresentFlags = Flags;
\t\t\t\tSKSE::log::info("[FrameGen] Present called with SyncInterval={} Flags={:#x}{}", SyncInterval, Flags,
\t\t\t\t\t(Flags & DXGI_PRESENT_ALLOW_TEARING) ? "  [ALLOW_TEARING - tearing permitted]" : "");
\t\t\t}
\t\t}
"""

if dx.count(E6_OLD) != 1:
    problems.append("DX12SwapChain.cpp E6 anchor count = %d (want 1)" % dx.count(E6_OLD))
else:
    dx = dx.replace(E6_OLD, E6_NEW, 1)
    planned.append("DX12SwapChain.cpp E6 Present Flags probe")

# ================================================================== version.rc
P_RC = os.path.join(ROOT, "src", "version.rc")
rc = read(P_RC)
if rc.count("0,55,0,0") != 2 or rc.count("0.55.0.0") != 2:
    problems.append("version.rc: expected 2x FILEVERSION form and 2x string form, got %d/%d"
                    % (rc.count("0,55,0,0"), rc.count("0.55.0.0")))
else:
    rc = rc.replace("0,55,0,0", "0,56,0,0").replace("0.55.0.0", "0.56.0.0")
    planned.append("version.rc 0.55 -> 0.56")

# ======================================================================= report
if problems:
    print("REFUSED, nothing written")
    for p in problems:
        print("  !", p)
    sys.exit(1)

print("planned edits:")
for p in planned:
    print("  *", p)

# post-conditions on the in-memory result
assert "sl::Extent renderExtent" not in sl, "the stale renderExtent declaration must be gone"
assert "&renderExtent" not in sl, "no tag may still reference renderExtent"
assert "DLSSG tag dims:" in sl and "MOTION probe:" in sl and "DLSSG options dims:" in sl
assert "ALLOW_TEARING - tearing permitted" in dx

if not APPLY:
    print("\nDRY RUN - nothing written. Re-run with --apply")
    sys.exit(0)

# backups
for path, old in ((P_SL, sl_before), (P_DX, read(P_DX)), (P_RC, read(P_RC))):
    bak = path + ".pre_v056"
    if not os.path.exists(bak):
        write(bak, old)

write(P_SL, sl)
write(P_DX, dx)
write(P_RC, rc)

print("\nAPPLIED")
for path in (P_SL, P_DX, P_RC):
    with open(path, encoding="utf-8", newline="") as fh:
        t = fh.read()
    print("  {}  {} bytes  lines={}".format(os.path.basename(path), len(t.encode("utf-8")), t.count("\n")))
