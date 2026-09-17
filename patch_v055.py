#!/usr/bin/env python3
"""
patch_v055.py - DynamicShaderFrameGen v0.54 -> v0.55

Pure instrumentation change. No behaviour change: the Reflex cap, the provider
choice and the MFG probe are all untouched, so the only *behavioural* variable
still under test stays exactly where it was (DLSSG-Transfusion's
patchFlipMetering=true).

Why: the v0.53 presented-counter line was emitted with `++presentedLog % 240 == 1`,
i.e. one reading every 240 real frames. At the 39 fps render rate the v0.54 Reflex
cap now enforces that is ~6.2 s of play before the FIRST reading, and the debug
sessions we are looking at lasted ~6 s - so the value that decides whether multi
frame generation actually runs was never measured once. Sample it early and on
every change instead, so a 1 -> 4 transition (or a 1/4 oscillation, which is what
two pacers fighting over the same swap chain would look like) shows up in a frame.

Assertion rules (per the workflow's hard rules):
  * every anchor must match EXACTLY once  (0 = stale, >1 = ambiguous -> REFUSE)
  * insertion/replacement must be guarded by a marker so a re-run cannot double
    apply it (anchor uniqueness alone does not prove the patch has not run)
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


def line_end(lines):
    """Detect the dominant line ending so new lines match the file."""
    crlf = sum(1 for ln in lines if ln.endswith("\r\n"))
    return "\r\n" if crlf * 2 > len(lines) else "\n"


problems = []
planned = []

# ---------------------------------------------------------------- Streamline.cpp
P = os.path.join(ROOT, "src", "Streamline.cpp")
src = read(P)
lines = src.splitlines(keepends=True)

# --- guard: has this patch already run?
if "presentedChanges" in src or "presentedChanged" in src:
    problems.append("Streamline.cpp: marker 'presentedChanged(s)' already present "
                    "-> patch already applied, refusing")

# --- locate the block by content, not by line number
idx = next((i for i, ln in enumerate(lines)
            if "static std::uint32_t presentedLog = 0;" in ln), None)
if idx is None:
    problems.append("Streamline.cpp: anchor line 'static std::uint32_t presentedLog = 0;' not found")
else:
    n_static = src.count("static std::uint32_t presentedLog = 0;")
    n_if = src.count("if (++presentedLog % 240 == 1)")
    n_log = src.count('DLSSG presented per real frame = {}')
    if n_static != 1:
        problems.append("Streamline.cpp: 'static std::uint32_t presentedLog = 0;' x%d (want 1)" % n_static)
    if n_if != 1:
        problems.append("Streamline.cpp: 'if (++presentedLog % 240 == 1)' x%d (want 1)" % n_if)
    if n_log != 1:
        problems.append("Streamline.cpp: 'DLSSG presented per real frame = {}' x%d (want 1)" % n_log)

    if not problems:
        # the four lines we replace must be exactly the block we expect
        blk = lines[idx:idx + 4]
        expect = [
            "static std::uint32_t presentedLog = 0;",
            "if (++presentedLog % 240 == 1)",
            'DLSSG presented per real frame = {}',
            "dlssgFramesPresentedLast, static_cast<int>(state.status));",
        ]
        for k, (got, want) in enumerate(zip(blk, expect)):
            if want not in got:
                problems.append("Streamline.cpp: block line %d mismatch: %r" % (k, got))

        if not problems:
            indent = blk[0][:len(blk[0]) - len(blk[0].lstrip())]
            eol = line_end(lines)
            tail = blk[3][len(blk[3].rstrip("\r\n")):]
            new_block = [
                indent + "static std::uint32_t presentedLog = 0;" + eol,
                indent + "static std::uint32_t lastPresentedLogged = 0xFFFFFFFFu;" + eol,
                indent + "static std::uint32_t presentedChanges = 0;" + eol,
                indent + "++presentedLog;" + eol,
                indent + "// v0.55: sample early AND on every change. The old '% 240 == 1' interval needed" + eol,
                indent + "// ~6s of play before the first reading - longer than the debug sessions we have," + eol,
                indent + "// so the value was never actually measured. A 1 -> 4 transition, or a 1/4" + eol,
                indent + "// oscillation (what two pacers fighting over one swap chain looks like), now" + eol,
                indent + "// shows up within a single frame. Instrumentation only - no behaviour change." + eol,
                indent + "const bool presentedChanged = (dlssgFramesPresentedLast != lastPresentedLogged);" + eol,
                indent + "if (presentedLog <= 8 || (presentedChanged && presentedChanges < 200) || presentedLog % 300 == 0) {" + eol,
                indent + "\tif (presentedChanged) { lastPresentedLogged = dlssgFramesPresentedLast; ++presentedChanges; }" + eol,
                indent + "\tSKSE::log::info(\"[Streamline] DLSSG presented per real frame = {} (status={}) - 1 means NO interpolation\"," + eol,
                indent + "\t\tdlssgFramesPresentedLast, static_cast<int>(state.status));" + eol,
                indent + "}" + eol,
            ]
            lines[idx:idx + 4] = new_block
            planned.append(("Streamline.cpp",
                            "presented sampling: 240-frame interval -> first 8 frames + on-change (cap 200) + every 300",
                            len(new_block)))

# ---------------------------------------------------------------- version.rc
V = os.path.join(ROOT, "src", "version.rc")
vrc = read(V)
# (anchor, replacement, expected count). The two string resources (FileVersion and
# ProductVersion) share one anchor, so that entry legitimately expects 2 hits.
VERSION_EDITS = [
    ("FILEVERSION 0,54,0,0", "FILEVERSION 0,55,0,0", 1),
    ("PRODUCTVERSION 0,54,0,0", "PRODUCTVERSION 0,55,0,0", 1),
    ('"0.54.0.0\\0"', '"0.55.0.0\\0"', 2),
]
if "0.55.0.0" in vrc:
    problems.append("version.rc: already at 0.55 -> refusing")
else:
    for old, new, want in VERSION_EDITS:
        n = vrc.count(old)
        if n != want:
            problems.append("version.rc: anchor %r x%d (want %d)" % (old, n, want))
    if not problems:
        for old, new, _want in VERSION_EDITS:
            vrc = vrc.replace(old, new)
        planned.append(("version.rc", "file/product version 0.54 -> 0.55", len(vrc.splitlines())))

# ---------------------------------------------------------------- CHANGELOG.md
C = os.path.join(ROOT, "CHANGELOG.md")
chg = read(C)
if "# v0.55" in chg:
    problems.append("CHANGELOG.md: '# v0.55' already present -> refusing")
else:
    head_anchor = "# v0.54"
    if chg.count(head_anchor) != 1:
        problems.append("CHANGELOG.md: anchor %r x%d (want 1)" % (head_anchor, chg.count(head_anchor)))
    else:
        eol = "\r\n" if "\r\n" in chg[:200] else "\n"
        entry = eol.join([
            "# v0.55 - instrumentation: sample the presented-frames counter early and on change",
            "",
            "Instrumentation only. No behaviour change - the Reflex render cap, the provider",
            "choice and the MFG probe are untouched, so the single behavioural variable under",
            "test remains DLSSG-Transfusion's `patchFlipMetering`.",
            "",
            "**Why.** v0.53 added the one measurement that can prove multi frame generation is",
            "really running (`sl::DLSSGState::numFramesActuallyPresented`), but emitted it with",
            "`++presentedLog % 240 == 1`. With the v0.54 cap pinning the render rate to",
            "`refreshRate / multiplier` = 39 fps at 4x on a 160 Hz panel, the first reading needs",
            "~6.2 s of play. Every debug session so far ended inside that window, so the decisive",
            "number was never printed once - which is why three rounds of fixes each ended in",
            "\"still flickering\" with no data either way.",
            "",
            "**Change.** The line is now emitted for the first 8 real frames, then on every change",
            "of the reported value (capped at 200 change lines), then every 300 frames. A 1 -> 4",
            "transition - or a 1/4 oscillation, which is what two pacers fighting over one swap",
            "chain would look like - is therefore visible within a single frame.",
            "",
            "Read it as: `= 4` proves 4 frames really reach the display per real frame. `= 1`",
            "proves none do, no matter what `MFG probe: runtime ACCEPTED 4x` said.",
            "",
            "---",
            "",
        ])
        chg = chg.replace(head_anchor, entry + head_anchor, 1)
        planned.append(("CHANGELOG.md", "add 0.55 entry", None))

# ---------------------------------------------------------------- report
print("=== PLAN ===")
for name, what, extra in planned:
    print("  %-18s %s%s" % (name, what, ("  (%d lines)" % extra) if extra else ""))

if problems:
    print()
    print("=== PROBLEMS ===")
    for p in problems:
        print("  !", p)
    print()
    print("REFUSED, nothing written")
    sys.exit(1)

print()
print("All anchors unique, no prior application detected.")
if not APPLY:
    print("DRY RUN - nothing written. Re-run with --apply to write.")
    sys.exit(0)

write(P, "".join(lines))
write(V, vrc)
write(C, chg)
print("WRITTEN OK")
