#!/usr/bin/env python3
"""
patch_v057.py - DynamicShaderFrameGen v0.56 -> v0.57

Makes the ONE remaining self-contradictory constant observable and switchable
without a rebuild. It does NOT change the default behaviour.

CONTEXT - why this is the last static finding before a game launch is required.

v0.56 fixed the depth/mvec `ResourceTag::extent` (1706x960 -> 2560x1440) and that
fix is now *independently* confirmed against the reference implementation:

  open-shaders, src/Features/Upscaling/Streamline.cpp, TagDX12Resources():

    sl::Extent extent{ 0, 0, width, height };          // display/output size
    // Depth/mvec carry valid data only in the render-resolution subrect of their
    // display-sized targets; declare that extent, matching the FSR FG dispatch.
    auto renderSizeF = globals::state->screenSize * upscaling.resolutionScale;
    sl::Extent renderExtent{ 0, 0, renderSizeF.x, renderSizeF.y };

    tags = {
      { &depthRes,  kBufferTypeDepth,         ..., &renderExtent },
      { &mvecRes,   kBufferTypeMotionVectors, ..., &renderExtent },
      { &hudLessRes,kBufferTypeHUDLessColor,  ..., &extent },
      { &uiRes,     kBufferTypeUIColorAndAlpha,...,&extent },
    };

  open-shaders declares the RENDER subrect because it does NOT upscale: the engine
  writes valid data only into the top-left corner of a display-sized target. DFG
  copied that value but fills the targets differently - DX12SwapChain.cpp:663 runs
  CopyDepthToShared/CopyMvecToShared whenever `dlssgMode` is on, and both draw a
  fullscreen triangle with viewport = swapChainDesc.Width x Height through a shader
  that returns the sampled value UNCHANGED. So DFG's interop depth/mvec are valid
  over the WHOLE 2560x1440 and must be tagged as the whole resource. Identical
  constant, opposite correctness. v0.56 stands.

WHAT IS STILL WRONG - mvecScale.

  Streamline.cpp:412
    // v0.49k（修重影）：... 引擎 mvec=位移/2560，DLSS 期望 位移/1706 →
    // 差 1/renderScale 倍，需放大补偿，否则 temporal 重投影错 → 重影。
    c.mvecScale = { 1.0f / renderScaleX, 1.0f / renderScaleY };   // = {1.5, 1.5}

  Two independent sources disagree with that value:

  * sl_consts.h:204, the field's own definition --
      //! Specifies scale factors used to normalize motion vectors
      //! (so the values are in [-1,1] range)

  * ProgrammingGuideDLSS_G.md:653-661 --
      * If motion vector values in your buffer are in {-1,1} range then motion
        vector scale factor in common constants should be {1,1}
      * If motion vector values in your buffer are NOT in {-1,1} range then ...
        must be adjusted so that values end up in [-1,1] range
      consts.mvecScale = {1,1};                                // already [-1,1]
      consts.mvecScale = {1.0f/renderWidth, 1.0f/renderHeight}; // values in pixels

  * open-shaders, Streamline.cpp:490-497, the project this one keeps aligning to --
      // ... The standard full-frame DLSS path - including menus and frames where
      // foveated is skipped - must keep mvecScale at identity or DLSS massively
      // over-estimates motion.
      float mvecX = 1.0f, mvecY = 1.0f;
      slConstants.mvecScale = { mvecX, mvecY };

  Note the author's own premise: "引擎 mvec=位移/2560". A UV displacement that
  reaches 1.0 for a full-screen pan is ALREADY inside [-1,1], so by the official
  rule the scale should be identity, and 1.5 makes DLSS-G over-estimate motion by
  50% in every generated frame - wrong motion in every generated frame alternating
  with correct real frames is exactly the reported flicker.

  It is NOT changed silently. The v0.49k value was tuned in-game against a
  different defect (the extent bug that v0.56 removed), so which value is right is
  only decidable in-game. This patch therefore only:
    * reads the effective value from the INI (MvecScaleOverride, 0 = legacy), and
    * logs it once, so the A/B is one config line and zero rebuilds.

Default behaviour is byte-for-byte the old behaviour: override 0 -> 1/renderScale.

Assertion rules (same contract as patch_v056.py):
  * every anchor must match EXACTLY once (0 = stale, >1 = ambiguous -> REFUSE)
  * a marker string guards re-runs, because a unique anchor does not prove the
    patch has not already run
  * dry run by default; nothing is written without --apply
  * line endings are preserved per file (FrameGen.h / ImguiMenu.cpp / version.rc
    are CRLF; FrameGen.cpp / Streamline.cpp are LF) - sources are normalised to LF
    for matching and restored before writing
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APPLY = "--apply" in sys.argv


def read_norm(path):
    """Return (text with LF newlines, original newline sequence)."""
    with open(path, "rb") as fh:
        raw = fh.read()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8").replace("\r\n", "\n"), nl


def write_restore(path, text, nl):
    data = text.replace("\n", nl).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(data)
    return data


problems = []
planned = []

# ================================================================== FrameGen.h
P_H = os.path.join(ROOT, "src", "FrameGen.h")
h, h_nl = read_norm(P_H)
if "mvecScaleOverride" in h:
    problems.append("FrameGen.h: mvecScaleOverride already present -> refusing")

E1_OLD = ("\t\tfloat renderResolutionScale = 0.0f;  // INI RenderResolutionScale / GUI slider"
          "（0=Auto 跟随 QualityMode 档位表）")
E1_NEW = E1_OLD + "\n" + "\n".join([
    "\t\t// v0.57：mvecScale 覆盖（0 = 保留旧推导 1/renderScale，默认零行为变化）。",
    "\t\t// 运动矢量逐帧喂给 DLSS-G，值错了每张生成帧的 motion 都错 → 频闪。",
    "\t\t// 参照实现 open-shaders 的标准全屏路径用 identity（注释原话：must keep",
    "\t\t// mvecScale at identity or DLSS massively over-estimates motion），官方",
    "\t\t// 指南也写「值已在 {-1,1} 则 scale={1,1}」；而本工程用的是 v0.49k 为修重影",
    "\t\t// 调出的 1/renderScale（=1.5，即 150%）。两者冲突，只有游戏内 A/B 能定。",
    "\t\t// 设 1.00 即切到 identity。",
    "\t\tfloat mvecScaleOverride = 0.0f;   // INI MvecScaleOverride（0=旧行为 1.0=identity）",
])

if h.count(E1_OLD) != 1:
    problems.append("FrameGen.h E1 anchor count = %d (want 1)" % h.count(E1_OLD))
else:
    h = h.replace(E1_OLD, E1_NEW, 1)
    planned.append("FrameGen.h E1 add settings.mvecScaleOverride")

# ================================================================ FrameGen.cpp
P_C = os.path.join(ROOT, "src", "FrameGen.cpp")
c, c_nl = read_norm(P_C)
if "MvecScaleOverride" in c:
    problems.append("FrameGen.cpp: MvecScaleOverride already present -> refusing")

E2_OLD = ("\t\t\t\t\tsettings.renderResolutionScale = std::clamp(std::stof(v), 0.0f, 1.0f);\n"
          "\t\t\t\t} catch (...) {}\n"
          "\t\t\t}\n")
E2_NEW = E2_OLD + "\n".join([
    "\t\t\telse if (key == \"MvecScaleOverride\") {",
    "\t\t\t\t// v0.57：mvecScale 覆盖（单变量 A/B：0=旧行为 1.0=identity）",
    "\t\t\t\ttry {",
    "\t\t\t\t\tstd::string v = line.substr(eq + 1);",
    "\t\t\t\t\twhile (!v.empty() && (v.back() == ' ' || v.back() == '\\r' || v.back() == '\\n'))",
    "\t\t\t\t\t\tv.pop_back();",
    "\t\t\t\t\tsettings.mvecScaleOverride = std::clamp(std::stof(v), 0.0f, 4.0f);",
    "\t\t\t\t} catch (...) {}",
    "\t\t\t}",
    "",
])

if c.count(E2_OLD) != 1:
    problems.append("FrameGen.cpp E2 anchor count = %d (want 1)" % c.count(E2_OLD))
else:
    c = c.replace(E2_OLD, E2_NEW, 1)
    planned.append("FrameGen.cpp E2 parse MvecScaleOverride (INI)")

# =============================================================== ImguiMenu.cpp
P_M = os.path.join(ROOT, "src", "ImguiMenu.cpp")
m, m_nl = read_norm(P_M)
if "MvecScaleOverride=" in m:
    problems.append("ImguiMenu.cpp: MvecScaleOverride= already present -> refusing")

E3_OLD = ("\t\t\t<< \"RenderResolutionScale=\" << std::fixed << std::setprecision(2)"
          " << s.renderResolutionScale << \"\\n\"\n"
          "\t\t\t<< \"StreamlineLogLevel=\" << s.streamlineLogLevel << \"\\n\"\n")
E3_NEW = ("\t\t\t<< \"RenderResolutionScale=\" << std::fixed << std::setprecision(2)"
          " << s.renderResolutionScale << \"\\n\"\n"
          "\t\t\t<< \"MvecScaleOverride=\" << std::fixed << std::setprecision(2)"
          " << s.mvecScaleOverride << \"\\n\"\n"
          "\t\t\t<< \"StreamlineLogLevel=\" << s.streamlineLogLevel << \"\\n\"\n")

if m.count(E3_OLD) != 1:
    problems.append("ImguiMenu.cpp E3 anchor count = %d (want 1)" % m.count(E3_OLD))
else:
    m = m.replace(E3_OLD, E3_NEW, 1)
    planned.append("ImguiMenu.cpp E3 write MvecScaleOverride (keeps INI load/save symmetric)")

# =============================================================== Streamline.cpp
P_S = os.path.join(ROOT, "src", "Streamline.cpp")
s, s_nl = read_norm(P_S)
if "mvecScaleOverride" in s:
    problems.append("Streamline.cpp: mvecScaleOverride already present -> refusing")

E4_OLD = "\t\tc.mvecScale = { 1.0f / Get().dx12SwapChain.renderScaleX, 1.0f / Get().dx12SwapChain.renderScaleY };\n"
E4_NEW = "\n".join([
    "\t\t// v0.57: the 1/renderScale compensation below is the ONE value in this file",
    "\t\t// that both the field's own definition and the reference implementation",
    "\t\t// disagree with, and it is fed to DLSS-G every frame - a wrong value puts",
    "\t\t// wrong motion into every generated frame.",
    "\t\t//",
    "\t\t//   sl_consts.h: \"scale factors used to normalize motion vectors (so the",
    "\t\t//   values are in [-1,1] range)\"",
    "\t\t//   ProgrammingGuideDLSS_G.md: \"values in {-1,1} range -> scale factor",
    "\t\t//   should be {1,1}\"; not in range -> \"adjusted so that values end up in",
    "\t\t//   [-1,1] range\"",
    "\t\t//   open-shaders Streamline.cpp: \"The standard full-frame DLSS path ...",
    "\t\t//   must keep mvecScale at identity or DLSS massively over-estimates motion\"",
    "\t\t//",
    "\t\t// The v0.49k comment states its own premise - \"engine mvec = displacement/2560\"",
    "\t\t// - and a value reaching 1.0 for a full-screen pan is already inside [-1,1],",
    "\t\t// so that premise argues for identity. But 1.5 was tuned in-game against a",
    "\t\t// different defect (the depth/mvec extent that v0.56 removed), so it is not",
    "\t\t// discarded on inference alone: it becomes one INI line, defaulted to the old",
    "\t\t// behaviour, so the A/B costs no rebuild.",
    "\t\t{",
    "\t\t\tconst auto& sc = Get().dx12SwapChain;",
    "\t\t\tconst float ov = Get().settings.mvecScaleOverride;",
    "\t\t\tconst float mvsX = (ov > 0.0f) ? ov : (1.0f / sc.renderScaleX);",
    "\t\t\tconst float mvsY = (ov > 0.0f) ? ov : (1.0f / sc.renderScaleY);",
    "\t\t\tc.mvecScale = { mvsX, mvsY };",
    "\t\t\tstatic bool mvecScaleLogged = false;",
    "\t\t\tif (!mvecScaleLogged) {",
    "\t\t\t\tmvecScaleLogged = true;",
    "\t\t\t\tSKSE::log::info(\"[Streamline] mvecScale = {{ {:.4f}, {:.4f} }} \"",
    "\t\t\t\t\t\"(renderScale={:.4f} override={:.2f}) - 1.0 means already in [-1,1]\",",
    "\t\t\t\t\tmvsX, mvsY, sc.renderScaleX, ov);",
    "\t\t\t}",
    "\t\t}",
    "",
])

if s.count(E4_OLD) != 1:
    problems.append("Streamline.cpp E4 anchor count = %d (want 1)" % s.count(E4_OLD))
else:
    s = s.replace(E4_OLD, E4_NEW, 1)
    planned.append("Streamline.cpp E4 mvecScale override + once-only effective-value log")

# ================================================================== version.rc
P_RC = os.path.join(ROOT, "src", "version.rc")
rc, rc_nl = read_norm(P_RC)
if rc.count("0,56,0,0") != 2 or rc.count("0.56.0.0") != 2:
    problems.append("version.rc: expected 2x FILEVERSION and 2x string form, got %d/%d"
                    % (rc.count("0,56,0,0"), rc.count("0.56.0.0")))
else:
    rc = rc.replace("0,56,0,0", "0,57,0,0").replace("0.56.0.0", "0.57.0.0")
    planned.append("version.rc 0.56 -> 0.57")

# ====================================================================== report
if problems:
    print("REFUSED, nothing written")
    for p in problems:
        print("  !", p)
    sys.exit(1)

print("planned edits:")
for p in planned:
    print("  *", p)

# post-conditions on the in-memory result
assert h.count("float mvecScaleOverride = 0.0f;") == 1, "FrameGen.h field missing"
assert "// INI MvecScaleOverride" in h
assert c.count('key == "MvecScaleOverride"') == 1, "FrameGen.cpp branch missing"
assert "settings.mvecScaleOverride = std::clamp(std::stof(v), 0.0f, 4.0f);" in c
assert m.count('"MvecScaleOverride="') == 1, "SaveSettingsToIni line missing"
assert s.count("Get().settings.mvecScaleOverride") == 1, "Streamline.cpp override missing"
assert "c.mvecScale = { mvsX, mvsY };" in s
assert "mvecScale = {{" in s, "effective-value log missing"
assert "1.0f / Get().dx12SwapChain.renderScaleX" not in s, "old direct assignment must be gone"
assert "1.0f / sc.renderScaleX" in s, "legacy path must survive as the default"
assert rc.count("0,57,0,0") == 2 and rc.count("0.57.0.0") == 2
assert "0.56.0.0" not in rc and "0,56,0,0" not in rc
# keep the INI contract symmetric: exactly one reader, exactly one writer
assert c.count("MvecScaleOverride") == 1 and m.count("MvecScaleOverride") == 1

if not APPLY:
    print("\nDRY RUN - nothing written. Re-run with --apply")
    sys.exit(0)

# backups
for path in (P_H, P_C, P_M, P_S, P_RC):
    bak = path + ".pre_v057"
    if not os.path.exists(bak):
        with open(bak, "wb") as fh:
            fh.write(open(path, "rb").read())

# write + verify line endings survived
for name, path, text, nl in (("FrameGen.h", P_H, h, h_nl),
                             ("FrameGen.cpp", P_C, c, c_nl),
                             ("ImguiMenu.cpp", P_M, m, m_nl),
                             ("Streamline.cpp", P_S, s, s_nl),
                             ("version.rc", P_RC, rc, rc_nl)):
    data = write_restore(path, text, nl)
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n")
    stray = data.count(b"\r") - crlf
    if nl == "\r\n":
        ok = (crlf == lf and stray == 0)
    else:
        ok = (crlf == 0 and stray == 0)
    print("  %-16s %7d bytes  CRLF=%-5d LF=%-5d strayCR=%-3d %s"
          % (name, len(data), crlf, lf, stray, "OK" if ok else "*** LINE-ENDING MISMATCH ***"))
    assert ok, "%s line endings changed" % name

print("\napplied. Rebuild, then read the [Streamline] mvecScale line in the runtime log.")
