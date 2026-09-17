#!/usr/bin/env python3
"""v0.53 patch - honest FPS overlay + runtime-reported MFG evidence.

Rules enforced by this script (learned the hard way):
  * every anchor must occur EXACTLY ONCE. count==0 -> anchor stale, count>1 ->
    ambiguous. Either way the script refuses and writes NOTHING.
  * a unique anchor does NOT prove the patch has not already run (inserting AFTER
    an anchor leaves the anchor intact, so a second run would insert again), so
    every file also carries a marker: if the marker is present, refuse.
  * bytes are read/written as latin-1 so non-ASCII comment bytes survive untouched.
  * the file's own line ending is detected and reused.
Dry run by default; pass --apply to write.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
APPLY = "--apply" in sys.argv

OPS = []


def line_after(file, anchor, block, marker, extra=0):
    OPS.append(dict(kind="line_after", file=file, anchor=anchor, block=block,
                    marker=marker, extra=extra))


def line_before(file, anchor, block, marker, extra=0):
    OPS.append(dict(kind="line_before", file=file, anchor=anchor, block=block,
                    marker=marker, extra=extra))


def replace_block(file, old, new, marker):
    OPS.append(dict(kind="replace_block", file=file, old=old, new=new, marker=marker))


def replace_sub(file, anchor, sub_old, sub_new, marker):
    OPS.append(dict(kind="replace_sub", file=file, anchor=anchor,
                    sub_old=sub_old, sub_new=sub_new, marker=marker))


T = "\t"

# ---------------------------------------------------------------- E1 Streamline.h
line_after(
    "src/Streamline.h",
    "bool mfgProbeLatched = false;",
    "// v0.53: the runtime's own measurement. Streamline documents\n"
    "// numFramesActuallyPresented as \"number of frames presented since the last\n"
    "// slDLSSGGetState call\" - a PER-INTERVAL count, not a cumulative one.\n"
    "// SetDLSSGOptions runs once per real frame, so this value IS the multiplier that\n"
    "// actually happened: 1 = no interpolation at all (rejected, or DLSSG idle),\n"
    "// 2 = 2x, 4 = 4x. It is the only number that proves MFG really generates frames,\n"
    "// and the FPS overlay reads it instead of inventing a factor.\n"
    "std::uint32_t dlssgFramesPresentedLast = 0;  // 0 = never queried yet\n",
    "dlssgFramesPresentedLast = 0;",
)

# -------------------------------------------------------------- E2 Streamline.cpp
line_before(
    "src/Streamline.cpp",
    "if (state.status != sl::DLSSGStatus::eOk && state.status != lastStatus) {",
    "// v0.53: publish the runtime's own measurement. numFramesActuallyPresented counts\n"
    "// frames presented since the PREVIOUS slDLSSGGetState call, and this function runs\n"
    "// once per real frame - so the value is the effective multiplier of that frame.\n"
    "// 1 means no interpolation happened at all, whatever we asked for. The overlay uses\n"
    "// it, and the periodic line below is the evidence that MFG really runs (or not).\n"
    "dlssgFramesPresentedLast = state.numFramesActuallyPresented;\n"
    "static std::uint32_t presentedLog = 0;\n"
    "if (++presentedLog % 240 == 1)\n"
    "\tSKSE::log::info(\"[Streamline] DLSSG presented per real frame = {} (status={}) - 1 means NO interpolation\",\n"
    "\t\tdlssgFramesPresentedLast, static_cast<int>(state.status));\n",
    "dlssgFramesPresentedLast = state.numFramesActuallyPresented;",
    extra=0,
)

# -------------------------------------------------------------- E3 ImguiMenu.cpp
replace_sub(
    "src/ImguiMenu.cpp",
    "show on-screen (displayed) fps",
    "// Frame generation active -> show on-screen (displayed) fps (FSR3/DLSSG are 2x)",
    "// v0.53: honesty fix. This line hardcoded x2 whenever frame generation was on.\n"
    "\t\t// Two consequences: it could never show 3x/4x, so switching from FSR3 2x to\n"
    "\t\t// DLSSG MFG looked like \"nothing changed any more\"; and it printed a doubled\n"
    "\t\t// number even when the runtime had rejected the request. The factor now comes\n"
    "\t\t// from what the runtime actually reported doing, and nothing is inflated when\n"
    "\t\t// nothing is generated.",
    "v0.53: honesty fix. This line hardcoded x2",
)

replace_sub(
    "src/ImguiMenu.cpp",
    "const float mult = a_fg.fgActive.load() ? 2.0f : 1.0f;",
    "const float mult = a_fg.fgActive.load() ? 2.0f : 1.0f;",
    "float mult = 1.0f;\n"
    "\t\tconst char* tag = \"\";\n"
    "\t\tif (a_fg.dx12SwapChain.dlssgMode) {\n"
    "\t\t\t// dlssgFramesPresentedLast = frames the runtime really presented for the last\n"
    "\t\t\t// real frame. >1 is measured evidence of multi-frame generation; <=1 means\n"
    "\t\t\t// DLSSG is not generating, so the number must NOT be doubled.\n"
    "\t\t\tconst std::uint32_t presented = a_fg.streamline.dlssgFramesPresentedLast;\n"
    "\t\t\tif (presented > 1u)\n"
    "\t\t\t\tmult = static_cast<float>(presented);\n"
    "\t\t\telse\n"
    "\t\t\t\ttag = \" (MFG off)\";\n"
    "\t\t} else if (a_fg.fgActive.load()) {\n"
    "\t\t\tmult = 2.0f;  // FSR3 generates exactly one frame (verified by the dispatch probe)\n"
    "\t\t}",
    "const std::uint32_t presented = a_fg.streamline.dlssgFramesPresentedLast;",
)

replace_sub(
    "src/ImguiMenu.cpp",
    'std::snprintf(buf, sizeof(buf), "%.0f FPS", s_fps * mult);',
    'std::snprintf(buf, sizeof(buf), "%.0f FPS", s_fps * mult);',
    'std::snprintf(buf, sizeof(buf), "%.0f FPS%s", s_fps * mult, tag);',
    'std::snprintf(buf, sizeof(buf), "%.0f FPS%s", s_fps * mult, tag);',
)

# ---------------------------------------------------------------- E4 version.rc
replace_sub("src/version.rc", "FILEVERSION 0,52,0,0",
            "FILEVERSION 0,52,0,0", "FILEVERSION 0,53,0,0", "FILEVERSION 0,53,0,0")
replace_sub("src/version.rc", "PRODUCTVERSION 0,50,0,0",
            "PRODUCTVERSION 0,50,0,0", "PRODUCTVERSION 0,53,0,0", "PRODUCTVERSION 0,53,0,0")
replace_sub("src/version.rc", 'VALUE "FileVersion"',
            '"0.50.0.0\\0"', '"0.53.0.0\\0"', "0.53.0.0")
replace_sub("src/version.rc", 'VALUE "ProductVersion"',
            '"0.52.0.0\\0"', '"0.53.0.0\\0"', "0.53.0.0")

# --------------------------------------------------------------------- E5 INI
replace_block(
    "SKSE/Plugins/DynamicShaderFrameGen.ini",
    "; 1 = DLSSG (NVIDIA only) - multi-frame generation; 3x/4x needs RTX 50,\n"
    ";     40-series is clamped to 2x by the Streamline runtime. Changing this\n"
    ";     needs a game restart (the swapchain path is rebuilt).",
    "; 1 = DLSSG (NVIDIA only) - multi-frame generation. The Streamline runtime\n"
    ";     reports numFramesToGenerateMax=1 on Ada (RTX 40) and older, so on a 40\n"
    ";     series card 3x/4x only works with an external MFG kernel unlocker\n"
    ";     installed - see MFGMaxFramesOverride below. Changing this needs a game\n"
    ";     restart (the swapchain path is rebuilt).",
    "external MFG kernel unlocker",
)

line_after(
    "SKSE/Plugins/DynamicShaderFrameGen.ini",
    "MFGMaxFramesOverride=3",
    "; DLSSG-Transfusion (RTX 40) drives the multiplier with ITS OWN hotkeys, live and\n"
    "; without a game restart: Ctrl+Alt+2 / Ctrl+Alt+3 / Ctrl+Alt+4 = 2x / 3x / 4x,\n"
    "; Page Up / Page Down steps the multiplier, Ctrl+Alt+D toggles fixed/dynamic mode.\n"
    "; Its overlay is switched on by \"showOverlay\" in DLSSG-Transfusion.json. Do not try\n"
    "; to drive it from the game's video menu. If Transfusion is active, the value above\n"
    "; is only the plugin's request; the log line\n"
    ";   \"DLSSG presented per real frame = N\"\n"
    "; is the runtime's own measurement and the only reliable proof of what is actually\n"
    "; being generated (1 = no interpolation, 4 = 4x).",
    "DLSSG-Transfusion (RTX 40) drives the multiplier",
)

# --------------------------------------------------------------- E6 CHANGELOG.md
line_before(
    "CHANGELOG.md",
    "# v0.52 - switch states that actually stick",
    "# v0.53 - the FPS number stops lying, and MFG gets a measurement\n"
    "\n"
    "Reported: \"check it yourself before I go in again, I do not want another launch\n"
    "that is completely wrong.\"\n"
    "\n"
    "Audit of the whole chain (all verified against on-disk state, not assumed):\n"
    "  * Deployment is correct. The DLL in the active MO2 instance is byte-identical to\n"
    "    the build output; the active INI is Provider=1 / DLSSGFramesToGenerate=3 /\n"
    "    MFGMaxFramesOverride=3; overwrite/ carries no copy of it; the two other mods\n"
    "    that also ship an INI of this name are DISABLED in the DIPEI profile, so there\n"
    "    is no file conflict. PLUGIN_DEPLOY_DIR points at the instance that is played.\n"
    "  * RTXMFG-Universal (the competing unlocker that also detours slInit /\n"
    "    setOptions / ngxCreate) has been inert since 2026-09-11 - its proxy is sitting\n"
    "    in the game dir renamed to dinput8.dll.disabled.\n"
    "  * Streamline is 2.13.0.0 everywhere (game root and mod folder agree), and\n"
    "    nvngx_dlssg.dll is 3.10.8, inside DLSSG-Transfusion's supported range.\n"
    "\n"
    "Defect found and fixed - the overlay could not have shown the difference:\n"
    "  * ImguiMenu::DrawFps hardcoded `mult = fgActive ? 2.0f : 1.0f`. It never knew\n"
    "    about MFG, so 3x/4x could not appear on screen, and it multiplied the number\n"
    "    even when the runtime had rejected the request. Switching FSR3 -> DLSSG was\n"
    "    therefore guaranteed to look like \"nothing changed\". The factor now comes from\n"
    "    dlssgFramesPresentedLast, and when DLSSG is not generating nothing is inflated\n"
    "    (the overlay says so instead).\n"
    "\n"
    "New evidence channel:\n"
    "  * sl::DLSSGState::numFramesActuallyPresented is documented as \"frames presented\n"
    "    since the last slDLSSGGetState call\" - a per-interval count. Since\n"
    "    SetDLSSGOptions runs once per real frame, that value IS the multiplier that\n"
    "    actually happened. It is now recorded every frame and logged periodically as\n"
    "    \"DLSSG presented per real frame = N\" (1 = no interpolation). This is the first\n"
    "    number in this project that is measured rather than computed.\n"
    "\n"
    "Also: version.rc string version said 0.50.0.0 while FILEVERSION said 0.52 - both\n"
    "now 0.53. The INI documents DLSSG-Transfusion's own Ctrl+Alt+2/3/4 hotkeys, which\n"
    "are how the multiplier is really driven, not the game's video menu.\n"
    "\n"
    "Still unproven: Provider=1 has never completed a session on this machine. Every\n"
    "log so far is the FSR3 path. The next launch is the first real test; if the runtime\n"
    "rejects 4x the ladder probe steps back to whatever it accepts and says so.\n"
    "\n",
    "# v0.53 - the FPS number stops lying",
)


def detect_eol(raw):
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def main():
    cache = {}
    for op in OPS:
        cache.setdefault(op["file"], None)

    # ---- pass 1: guards (marker) and anchor uniqueness ----
    files = {}
    errors = []
    for name in cache:
        path = os.path.join(ROOT, name.replace("/", os.sep))
        if not os.path.isfile(path):
            errors.append("MISSING FILE: " + name)
            continue
        with open(path, "rb") as f:
            raw = f.read()
        eol = detect_eol(raw)
        files[name] = dict(path=path, raw=raw, eol=eol, text=raw.decode("latin-1"))

    if errors:
        print("\n".join(errors))
        print("REFUSED, nothing written")
        return 1

    # marker guard first
    for op in OPS:
        if op["marker"] in files[op["file"]]["text"]:
            print("REFUSED: marker already present in {} -> {}".format(op["file"], op["marker"]))
            print("REFUSED, nothing written")
            return 1

    # anchor checks
    for op in OPS:
        f = files[op["file"]]
        text = f["text"]
        if op["kind"] in ("line_after", "line_before"):
            hits = [ln for ln in text.split(f["eol"]) if op["anchor"] in ln]
            label = "anchor"
        elif op["kind"] == "replace_sub":
            hits = [ln for ln in text.split(f["eol"]) if op["anchor"] in ln]
            label = "anchor"
            n = text.count(op["sub_old"])
            if n != 1:
                print("REFUSED: sub_old occurs {} times (want 1) in {} -> {}".format(
                    n, op["file"], op["sub_old"]))
                print("REFUSED, nothing written")
                return 1
        else:  # replace_block
            old = op["old"].replace("\n", f["eol"])
            hits = [old] if text.count(old) == 1 else []
            if not hits:
                print("REFUSED: block occurs {} times (want 1) in {}".format(
                    text.count(old), op["file"]))
                print("REFUSED, nothing written")
                return 1
            label = "block"
        if len(hits) != 1:
            print("REFUSED: {} occurs {} times (want 1) in {} -> {!r}".format(
                label, len(hits), op["file"], op["anchor"]))
            print("REFUSED, nothing written")
            return 1

    print("all anchors unique ({} edits), no markers present".format(len(OPS)))

    # ---- pass 2: apply in memory ----
    for op in OPS:
        f = files[op["file"]]
        eol = f["eol"]
        lines = f["text"].split(eol)

        if op["kind"] == "line_after" or op["kind"] == "line_before":
            idx = next(i for i, ln in enumerate(lines) if op["anchor"] in ln)
            base = lines[idx][:len(lines[idx]) - len(lines[idx].lstrip())]
            blk = op["block"].rstrip("\n").split("\n")
            ins = [base + b if b else b for b in blk]
            at = idx + 1 if op["kind"] == "line_after" else idx
            lines[at:at] = ins
        elif op["kind"] == "replace_sub":
            idx = next(i for i, ln in enumerate(lines) if op["anchor"] in ln)
            # sub_new may be multi-line: its \n must become the file's own EOL or the
            # file ends up with mixed line endings.
            sub_new = op["sub_new"].replace("\n", eol)
            lines[idx] = lines[idx].replace(op["sub_old"], sub_new)
        else:
            old = op["old"].replace("\n", eol)
            new = op["new"].replace("\n", eol)
            joined = eol.join(lines)
            assert joined.count(old) == 1
            joined = joined.replace(old, new)
            lines = joined.split(eol)

        f["text"] = eol.join(lines)

    # ---- pass 3: report / write ----
    for name, f in files.items():
        new_raw = f["text"].encode("latin-1")
        changed = new_raw != f["raw"]
        print("{}: {} -> {} bytes ({})".format(name, len(f["raw"]), len(new_raw),
                                               "CHANGED" if changed else "unchanged"))
        if changed and APPLY:
            with open(f["path"], "wb") as fh:
                fh.write(new_raw)

    # ---- pass 4: verify markers landed ----
    ok = True
    for op in OPS:
        f = files[op["file"]]
        if op["marker"] not in f["text"]:
            print("VERIFY FAILED: marker missing after patch: {} -> {}".format(
                op["file"], op["marker"]))
            ok = False
    print("marker verify: " + ("OK" if ok else "FAILED"))
    if not APPLY:
        print("DRY RUN - pass --apply to write")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
