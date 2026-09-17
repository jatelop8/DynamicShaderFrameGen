#!/usr/bin/env python3
"""
fix_v057_deploy_docs.py - correct the deployment/rollback story and document the
new INI key where the build will actually deploy it.

What was wrong:

  CMakeLists.txt:105-121 adds a POST_BUILD step that copies, into
  PLUGIN_DEPLOY_DIR (= E:\\EJ\\mod\\mods\\DynamicShaderFrameGen):

      copy_if_different  <dll>  SKSE/Plugins/DynamicShaderFrameGen.dll
      copy_if_different  <ini>  SKSE/Plugins/DynamicShaderFrameGen.ini
      copy_directory     Shaders

  So the build deploys itself.  Two things followed from that and both were
  reported wrongly by the v0.57 docs:

  1. The manual `cp` of the DLL was redundant, and the ".pre_v056" copy taken
     before it captured the ALREADY deployed v0.57 build.  It is not a rollback
     point for v0.56.  (Verified: it hashes 73fa4a5c, the v0.57 build.)

  2. Editing the deployed INI and then rebuilding reverts the edit, because the
     same POST_BUILD step pushes the repo INI back over it.  The mvecScale A/B
     is exactly such an edit, so the checklist has to say so.

Also: the new key is added to the repo INI (which is what gets deployed) rather
than only mentioned, so it is discoverable and survives a rebuild if set there.
FrameGen.cpp:121 skips comment lines whose first character is ';', so the
documentation block - which contains '=' characters - cannot be misparsed.

Line endings: the INI and CHANGELOG.md are CRLF, VERIFY_v057.md is LF. Preserved
per file and re-verified after writing.
"""
import os
import sys

ROOT = r"D:\Modding\DynamicShaderFrameGen"
APPLY = "--apply" in sys.argv

INI = os.path.join(ROOT, "SKSE", "Plugins", "DynamicShaderFrameGen.ini")
VERIFY = os.path.join(ROOT, "VERIFY_v057.md")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
STALE_BAK = r"E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.dll.pre_v056"


def read_norm(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8").replace("\r\n", "\n"), nl


# ------------------------------------------------------------------ the INI
INI_ANCHOR = "; ===== DLSS 5 Neural Rendering (NGX Feature 18, built in since v0.48) ====="
INI_ADD = """; ---------------------------------------------------------------------------
; v0.57 - mvecScale override: the motion-vector scale handed to DLSS-G every frame.
;
; sl::Constants::mvecScale tells DLSS-G how to normalise the motion vectors so the
; values land in [-1,1]. NVIDIA's guide: "values in {-1,1} range -> scale factor
; should be {1,1}". The standard full-frame path should therefore be identity;
; open-shaders agrees ("must keep mvecScale at identity or DLSS massively
; over-estimates motion").
;
; This engine's motion vectors are reported as displacement / screen width, which
; already reaches 1.0 for a full-screen pan, i.e. already inside [-1,1]. The legacy
; value used below is 1/renderScale (= 1.5 at QualityMode=1, a 50% motion
; over-estimate), tuned in-game at v0.49k against a different defect.
;
;   0.00 = legacy 1/renderScale (default, behaviour unchanged)
;   1.00 = identity, the reference-implementation value
;
; The effective value is logged once per run:
;   [Streamline] mvecScale = { 1.5000, 1.5000 } (renderScale=0.6667 override=0.00)
;
; NOTE: the build's POST_BUILD step copies THIS file over the one in the mod folder
; (copy_if_different). Set the value here if it must survive a rebuild; edit the
; deployed copy only for a one-off A/B, and do not rebuild in between.
; ---------------------------------------------------------------------------
MvecScaleOverride=0.00

"""

# --------------------------------------------------------------- VERIFY_v057
V_ANCHOR = ("Then restart and read line (a) again - it must print `{ 1.0000, 1.0000 }`.\n"
            "If it still prints 1.5000, the INI being edited is not the one being loaded.")
V_ADD = ("**Do not rebuild between editing the INI and testing.** The build's POST_BUILD step runs\n"
         "`copy_if_different` on the INI into the mod folder, so a rebuild silently reverts your\n"
         "edit to whatever the repo copy holds. Either set the value in the repo copy\n"
         "(`SKSE/Plugins/DynamicShaderFrameGen.ini`, which is the one that gets deployed), or edit\n"
         "the deployed copy and restart the game without building.\n\n"
         + V_ANCHOR)

V_ROLL_ANCHOR = """## Rollback

    E:\\EJ\\mod\\mods\\DynamicShaderFrameGen\\SKSE\\Plugins\\DynamicShaderFrameGen.dll.pre_v056

is the v0.56 binary. Source backups are `.pre_v057` next to each patched file
(`src/FrameGen.h`, `src/FrameGen.cpp`, `src/ImguiMenu.cpp`, `src/Streamline.cpp`,
`src/version.rc`). `git checkout .` also returns to commit `135c4e4` (v0.56);
v0.57 is committed on top of it."""

V_ROLL_NEW = """## Rollback

**There is no usable DLL-level backup of v0.56 - do not restore `.pre_v056`.** The
build deploys itself (see the INI note above), so by the time a manual backup was
taken the deployed DLL was already the v0.57 build; that copy hashes `73fa4a5c`,
i.e. v0.57.

Rollback is source-level and exact:

    git checkout 135c4e4 -- src
    # rebuild - the POST_BUILD step redeploys on its own

  * `135c4e4` = v0.56, `4770fae` = v0.57, `9d4ed78` = v0.57 tooling.
  * per-file source backups `.pre_v057` sit next to each patched file
    (`src/FrameGen.h`, `src/FrameGen.cpp`, `src/ImguiMenu.cpp`, `src/Streamline.cpp`,
    `src/version.rc`). Those are valid: nothing overwrites source files during a build."""

# ------------------------------------------------------------------ CHANGELOG
C_ANCHOR = """Built clean: 7/7 objects, exit 0, `1223168 bytes md5=73fa4a5c2c762635703ca952205a1192`,
deployed byte-identical to
`E:\\EJ\\mod\\mods\\DynamicShaderFrameGen\\SKSE\\Plugins\\`."""

C_NEW = """Built clean: 7/7 objects, exit 0, `1223168 bytes md5=73fa4a5c2c762635703ca952205a1192`.

The build deploys itself - `CMakeLists.txt:105-121` adds a POST_BUILD step that runs
`copy_if_different` for the DLL **and the INI**, plus `copy_directory` for `Shaders`,
into `PLUGIN_DEPLOY_DIR` (`E:\\EJ\\mod\\mods\\DynamicShaderFrameGen\\SKSE\\Plugins\\`).
The deployed DLL was verified byte-identical to the build output.

Two consequences:

  * a manual DLL copy is redundant, and a "backup" taken before it captures the
    already-deployed new build - so there is no DLL-level rollback point. Roll back
    with `git checkout <commit> -- src` and rebuild.
  * because the INI is deployed the same way, editing the deployed INI and then
    rebuilding **reverts the edit**. The new key is therefore documented in the repo
    INI (`SKSE/Plugins/DynamicShaderFrameGen.ini`) as `MvecScaleOverride=0.00`, which
    is what reaches the mod folder."""

problems, planned = [], []

ini, ini_nl = read_norm(INI)
if "MvecScaleOverride=" in ini:
    problems.append("INI: MvecScaleOverride already present -> refusing")
else:
    n = ini.count(INI_ANCHOR)
    if n != 1:
        problems.append("INI anchor count = %d (want 1)" % n)
    else:
        ini = ini.replace(INI_ANCHOR, INI_ADD + INI_ANCHOR, 1)
        planned.append("INI: add documented MvecScaleOverride=0.00")

v, v_nl = read_norm(VERIFY)
if "Do not rebuild between editing the INI" in v:
    problems.append("VERIFY: rebuild warning already present -> refusing")
else:
    if v.count(V_ANCHOR) != 1:
        problems.append("VERIFY section-2 anchor count = %d (want 1)" % v.count(V_ANCHOR))
    if v.count(V_ROLL_ANCHOR) != 1:
        problems.append("VERIFY rollback anchor count = %d (want 1)" % v.count(V_ROLL_ANCHOR))
    if not problems:
        v = v.replace(V_ANCHOR, V_ADD, 1).replace(V_ROLL_ANCHOR, V_ROLL_NEW, 1)
        planned.append("VERIFY: rebuild warning + corrected rollback")

c, c_nl = read_norm(CHANGELOG)
if "The build deploys itself" in c:
    problems.append("CHANGELOG: deploy note already present -> refusing")
else:
    if c.count(C_ANCHOR) != 1:
        problems.append("CHANGELOG build anchor count = %d (want 1)" % c.count(C_ANCHOR))
    else:
        c = c.replace(C_ANCHOR, C_NEW, 1)
        planned.append("CHANGELOG: correct the deployment/backup description")

if os.path.exists(STALE_BAK):
    planned.append("remove invalid DLL-level backup %s (it is v0.57, not v0.56)" % STALE_BAK)

if problems:
    print("REFUSED, nothing written")
    for p in problems:
        print("  !", p)
    sys.exit(1)

print("planned:")
for p in planned:
    print("  *", p)

# post-conditions
assert "MvecScaleOverride=0.00" in ini and ini.count("MvecScaleOverride") == 1
assert "Do not rebuild between editing the INI" in v
assert "do not restore `.pre_v056`" in v
assert "The build deploys itself" in c

if not APPLY:
    print("\nDRY RUN - nothing written. Re-run with --apply")
    sys.exit(0)

for path, text, nl, name in ((INI, ini, ini_nl, "INI"), (VERIFY, v, v_nl, "VERIFY"),
                             (CHANGELOG, c, c_nl, "CHANGELOG")):
    data = text.replace("\n", nl).encode("utf-8")
    open(path, "wb").write(data)
    crlf, lf = data.count(b"\r\n"), data.count(b"\n")
    stray = data.count(b"\r") - crlf
    ok = (crlf == lf and stray == 0) if nl == "\r\n" else (crlf == 0 and stray == 0)
    print("  %-10s %7d bytes  CRLF=%-5d LF=%-5d stray=%-3d %s"
          % (name, len(data), crlf, lf, stray, "OK" if ok else "*** LINE-ENDING BROKEN ***"))
    assert ok, name

if os.path.exists(STALE_BAK):
    os.remove(STALE_BAK)
    print("  removed invalid backup:", STALE_BAK)
    assert not os.path.exists(STALE_BAK)

print("\ndone. Rebuild once so the INI change is deployed, then test.")
