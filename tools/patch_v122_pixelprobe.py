#!/usr/bin/env python3
"""v1.22 -- two changes, one build.

A. The fader guards ENTRY, not play.
   00:30 run, in-world window (all four fields from the same [CAM] PC v1.19 line):

     time          paused  ld  fade   hrsD       presents/real frame
     00:31:02.935    0     0    1     0.003807   ~1     <- world is LIVE
     00:31:03.935    0     0    1     0.005663    1.00
     00:31:04.943    0     0    0     0.005501    4.00   <- fader closes

   The world became live at 00:31:02.935 -- paused=0, ld=0, and the calendar
   advancing at timescale 20 -- yet "presented per real frame" stayed at 1 for
   another two seconds because `IsMenuOpen("Fader Menu")` was still true, and
   [XRAY] MENU EDGE open=0 fired at 00:31:04.683, between the fade=1 sample and
   the fade=0 sample. The guard was not released by the 90 s safety cap (this run
   was 57 s long); it was released by the fader finally closing. The 23:38 run
   shows the same term holding far longer: fade=1 in the world for 40+ s.
   GameIsPaused() splits the two cases exactly -- 1 through start-up, the main
   menu and the load fade (every pre-world sample in the 00:30 log reads 1, so
   the v0.96 protection is untouched), 0 the moment the player camera takes over
   (the v1.16 TAKEOVER line lands on the same 00:31:02.935 sample).

B. The pixel probe.
   Every witness this project already owns -- Present's return, presentAge,
   dsync, the presented-per-real-frame ratio -- reports that a flip HAPPENED.
   Not one of them can see the same picture being flipped again, which is why
   the 00:30 run looks healthy (ratio 4.00, dsync 0, presentAge 5-8 ms) while
   the player reports a frozen screen. A flip is not a picture. This samples a
   64x64 block from the centre of the frame the plugin hands to the swap chain,
   once per second, and logs whether it changed. Read-only, self-disabling, and
   the Map uses DO_NOT_WAIT so a sample that is not ready is dropped instead of
   stalling the render thread.

Default is a DRY RUN; pass --apply to write.
Every anchor must match exactly once or nothing is written at all.
"""
import ast
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPL = ROOT / "tools" / "v122_pixelprobe_impl.txt"

# --- (file, label, mode, needle, payload) -----------------------------------
# mode: "before"    -> insert payload lines before the needle's line
#       "after"     -> append payload lines after the needle's line
#       "replace"   -> the needle's WHOLE LINE becomes the payload's lines
#       "elseif"    -> insert an `else if` block after the needle's line
#       "impl"      -> payload is a whole function placed before the needle's line
#       "afterline" -> needle is a WHOLE LINE (no indentation assumed) and the
#                      payload goes after it. Needed for .ini, where a key name
#                      may also appear inside prose comments: a substring anchor
#                      is ambiguous there, and a "\n"-prefixed one is destroyed
#                      by the EOL conversion, because line_indent() would read the
#                      PREVIOUS line as the indentation.
E1_NEEDLE = 'return ui->IsMenuOpen("Fader Menu") && faderUpSec < 90;'
E1_ADD = [
    "// v1.22 -- the fader guards ENTRY, not play. Measured on the 00:30 run,",
    "// in-world (every field from the same [CAM] PC v1.19 line):",
    "//   00:31:02.935  paused=0 ld=0 fade=1 hrsD=0.003807  ~1 present/frame",
    "//   00:31:03.935  paused=0 ld=0 fade=1 hrsD=0.005663   1 present/frame",
    "//   00:31:04.943  paused=0 ld=0 fade=0 hrsD=0.005501   4 present/frame",
    "// The world was already live at 00:31:02.935 -- paused=0, ld=0, the calendar",
    "// advancing at timescale 20 -- but the fader held this line true for another",
    "// two seconds, and [XRAY] MENU EDGE open=0 fired at 00:31:04.683, between the",
    "// fade=1 sample and the fade=0 sample. The 90 s cap did not release it (the",
    "// run was 57 s long); the fader closing did. The 23:38 run is the same defect",
    "// with a longer fade: fade=1 in the world for 40+ s.",
    "//",
    "// GameIsPaused() separates the two cases: 1 through start-up, the main menu",
    "// and the load fade -- every pre-world sample in the 00:30 log reads 1, so the",
    "// v0.96 protection is untouched -- and 0 the moment the player camera takes",
    "// over (the v1.16 TAKEOVER line lands on that same 00:31:02.935 sample).",
    "return ui->GameIsPaused() && faderUpSec < 90;",
]

E2_NEEDLE = "bool mvecCopyFailed = false;"
E2_ADD = [
    "// ---- v1.22 PIXEL PROBE ----",
    "// See PixelProbeTick() in the .cpp for the full argument. In one line: every",
    "// witness this file already has (Present's return, presentAge, dsync, the",
    "// presented-per-real-frame ratio) reports that a flip HAPPENED, and not one",
    "// of them can see that the same picture was flipped again. The 00:30 run",
    "// measured ratio = 4.00 with dsync = 0 and presentAge 5-8 ms while the player",
    "// reported a frozen screen, which is the gap this closes.",
    "void PixelProbeTick();",
    "winrt::com_ptr<ID3D11Texture2D> pixelProbeStaging;",
    "D3D11_BOX pixelProbeBox{};",
    "std::uint32_t pixelProbeWidth = 0;",
    "std::uint32_t pixelProbeHeight = 0;",
    "std::uint64_t pixelProbeLastMs = 0;",
    "std::uint64_t pixelProbeLastHash = 0;",
    "std::uint32_t pixelProbeSamples = 0;",
    "std::uint32_t pixelProbeChanged = 0;",
    "std::uint32_t pixelProbeUnchanged = 0;",
    "std::uint32_t pixelProbeStreak = 0;",
    "std::uint32_t pixelProbeMaxStreak = 0;",
    "bool pixelProbeReady = false;",
    "bool pixelProbeDisabled = false;",
]

E3_NEEDLE = "// v0.81 -- who actually presents? Observation only; this never refuses."
E3_ADD = [
    "// v1.22: sample the content the plugin is about to hand to the swap chain.",
    "// One call site, on the path all three return branches share, so no branch",
    "// has to be touched to cover them.",
    "PixelProbeTick();",
]

E4_NEEDLE = "HRESULT DX12SwapChain::GetDevice(REFIID uuid, void** ppDevice)"

E5_NEEDLE = "bool menuGuardFader = true;     // INI MenuGuardFader"
E5_ADD = [
    "// v1.22 -- PIXEL PROBE (default 1). Samples a 64x64 block from the centre of",
    "// the frame the plugin hands to the swap chain, once per second, and reports",
    "// whether that content changed. It exists because up to v1.21 a frozen screen",
    "// and a healthy one produced the same log: presents, presentAge, dsync and the",
    "// presented-per-real-frame ratio are all witnesses that a flip happened, and",
    "// none of them can see the same picture being flipped again (ledger L38).",
    "// Read-only and self-disabling; 0 switches it off without a rebuild.",
    "bool pixelProbe = true;         // INI PixelProbe",
]

E6_NEEDLE = "settings.menuGuardFader = readBool(line, true);"
E6_ADD = [
    'else if (key == "PixelProbe")',
    "settings.pixelProbe = readBool(line, true);",
]

E7_NEEDLE = r'<< "MenuGuardFader=" << (s.menuGuardFader ? 1 : 0) << "\n"'
E7_ADD = [r'<< "PixelProbe=" << (s.pixelProbe ? 1 : 0) << "\n"']

# A WHOLE-LINE anchor. The bare substring "MenuGuardFader=1" matches twice in
# this file -- line 22 is a comment that names the key while explaining it.
E8_NEEDLE = "MenuGuardFader=1"
E8_ADD = [
    "; v1.22 PIXEL PROBE. 1 = sample a 64x64 block from the centre of the frame the",
    "; plugin hands to the swap chain, once per second, and log whether it changed",
    "; (grep the log for [PIXEL]). 0 = off.",
    ";",
    "; Why: up to v1.21 every witness the plugin owns (Present's return, presentAge,",
    "; dsync, the presented-per-real-frame ratio) reports that a flip HAPPENED, and",
    "; none of them can see that the same buffer was flipped again. The 00:30 run",
    "; measured ratio = 4.00, dsync = 0 and presentAge 5-8 ms while the player",
    "; reported a frozen screen. Reading pixels is the only thing that separates",
    "; \"the world is running\" from \"the screen is stale\".",
    ";",
    "; Cost: one small copy plus one Map per second. The Map uses DO_NOT_WAIT, so a",
    "; sample that is not ready is dropped rather than stalling the render thread,",
    "; and any failure disables the probe permanently with a single log line.",
    "PixelProbe=1",
]

SL = "src/Streamline.cpp"
H = "src/DX12SwapChain.h"
CPP = "src/DX12SwapChain.cpp"
FH = "src/FrameGen.h"
FC = "src/FrameGen.cpp"
IM = "src/ImguiMenu.cpp"
INI = "SKSE/Plugins/DynamicShaderFrameGen.ini"

EDITS = [
    (SL, "A1 fader requires paused", "replace", E1_NEEDLE, E1_ADD),
    (H, "B1 probe members", "after", E2_NEEDLE, E2_ADD),
    (CPP, "B2 probe call site", "before", E3_NEEDLE, E3_ADD),
    (CPP, "B3 probe implementation", "impl", E4_NEEDLE, None),
    (FH, "B4 settings field", "after", E5_NEEDLE, E5_ADD),
    (FC, "B5 settings reader", "elseif", E6_NEEDLE, E6_ADD),
    (IM, "B6 settings writer", "after", E7_NEEDLE, E7_ADD),
    (INI, "B7 ini key", "afterline", E8_NEEDLE, E8_ADD),
]

# What the RESULT text must contain.
POST = {
    SL: ["ui->GameIsPaused() && faderUpSec < 90"],
    H: ["void PixelProbeTick();", "bool pixelProbeDisabled = false;"],
    CPP: ["PixelProbeTick();", "void DX12SwapChain::PixelProbeTick()",
          "D3D11_MAP_FLAG_DO_NOT_WAIT", "VERDICT"],
    FH: ["bool pixelProbe = true;"],
    FC: ['key == "PixelProbe"'],
    IM: ['<< "PixelProbe="'],
    INI: ["\nPixelProbe=1\n"],
}

# What the RESULT text must NOT contain. An assertion that a no-op can satisfy is
# worse than no assertion: it reports success for a change that never happened.
POST_GONE = {
    SL: ['IsMenuOpen("Fader Menu") && faderUpSec < 90'],
}

MARKER = "pixelProbe"
GUARD = FH


def eol_of(text: str) -> str:
    crlf = text.count("\r\n")
    bare = text.count("\n") - crlf
    return "\r\n" if crlf > bare else "\n"


def line_indent(text: str, needle: str) -> str:
    i = text.index(needle)
    j = text.rfind("\n", 0, i) + 1
    return text[j:i]


def whole_line_span(text: str, needle: str):
    """Span of the ONE line whose whole content equals `needle`.

    Returns (start, content_end, eol) or None when the line is absent or the
    match is ambiguous. This is the anchor the .ini needs: its key names appear
    inside the documentation comments as well as as assignments.
    """
    eol = eol_of(text)
    parts = text.split(eol)
    hits = [i for i, p in enumerate(parts) if p == needle]
    if len(hits) != 1:
        return None
    idx = hits[0]
    start = sum(len(p) + len(eol) for p in parts[:idx])
    return start, start + len(needle), eol


def sha(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def build(text: str, mode: str, needle: str, payload, impl: str) -> tuple[str, str]:
    """Return (old, new) with \\n as the newline placeholder."""
    ind = line_indent(text, needle)
    old = ind + needle + "\n"

    if mode == "impl":
        return old, impl.rstrip("\n") + "\n" + ind + needle + "\n"

    if mode == "replace":
        new = "".join(ind + c + "\n" for c in payload)
        return old, new

    if mode == "before":
        new = "".join(ind + c + "\n" for c in payload) + ind + needle + "\n"
        return old, new

    if mode == "after":
        new = ind + needle + "\n" + "".join(ind + c + "\n" for c in payload)
        return old, new

    if mode == "elseif":
        inner = ind[:-1] if ind.endswith("\t") else ind
        new = (ind + needle + "\n"
               + inner + payload[0] + "\n"
               + ind + payload[1] + "\n")
        return old, new

    raise ValueError(f"unknown mode {mode}")


def main() -> int:
    apply = "--apply" in sys.argv

    if not IMPL.is_file():
        print(f"REFUSED: implementation text missing: {IMPL}")
        return 2

    guard_path = ROOT / GUARD
    if guard_path.is_file():
        if MARKER in guard_path.read_bytes().decode("utf-8", "surrogateescape"):
            print(f"REFUSED: already applied ({MARKER} present in {GUARD}), nothing written")
            return 1

    impl = IMPL.read_text(encoding="utf-8")

    per_file: dict[str, list] = {}
    for f, label, mode, needle, payload in EDITS:
        per_file.setdefault(f, []).append((label, mode, needle, payload))

    results: dict[str, str] = {}

    for f, edits in per_file.items():
        path = ROOT / f
        if not path.is_file():
            print(f"REFUSED: missing file {f}")
            return 2
        text = path.read_bytes().decode("utf-8", "surrogateescape")
        eol = eol_of(text)
        tag = "CRLF" if eol == "\r\n" else "LF"

        for label, mode, needle, payload in edits:
            if mode == "afterline":
                span = whole_line_span(text, needle)
                if span is None:
                    n = text.split(eol).count(needle)
                    print(f"REFUSED: {f} :: {label}: whole-line matches={n} (must be 1), nothing written")
                    return 1
                start, end, le = span
                old_f = text[start:end + len(le)]
                new_f = old_f + le.join(payload) + le
                if text.count(old_f) != 1:
                    print(f"REFUSED: {f} :: {label}: assembled anchor count={text.count(old_f)} (must be 1), nothing written")
                    return 1
                text = text.replace(old_f, new_f, 1)
                print(f"  ok  {f:<44} {label}  [{tag}] whole-line anchor")
                continue

            if text.count(needle) != 1:
                print(f"REFUSED: {f} :: {label}: needle count={text.count(needle)} (must be 1), nothing written")
                return 1
            old, new = build(text, mode, needle, payload, impl)
            old_f, new_f = old.replace("\n", eol), new.replace("\n", eol)
            if text.count(old_f) != 1:
                print(f"REFUSED: {f} :: {label}: assembled anchor count={text.count(old_f)} (must be 1), nothing written")
                return 1
            text = text.replace(old_f, new_f, 1)
            print(f"  ok  {f:<44} {label}  [{tag}]")

        results[f] = text

    ok = True
    for f, needles in POST.items():
        text = results.get(f)
        if text is None:
            continue
        # Normalise EOL before matching, so a post-condition can be written once
        # with \n and still be exact on a CRLF file.
        probe = text.replace("\r\n", "\n")
        for needle in needles:
            c = probe.count(needle)
            good = c >= 1
            print(f"  post {'OK  ' if good else 'FAIL'} {f:<44} {needle!r} count={c}")
            if not good:
                ok = False

    for f, needles in POST_GONE.items():
        text = results.get(f)
        if text is None:
            continue
        probe = text.replace("\r\n", "\n")
        for needle in needles:
            c = probe.count(needle)
            good = c == 0
            print(f"  gone {'OK  ' if good else 'FAIL'} {f:<44} {needle!r} count={c}")
            if not good:
                ok = False

    if not ok:
        print("REFUSED: post-condition failed, nothing written")
        return 1

    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply to write.")
        for f in sorted(results):
            print(f"  md5 {sha(ROOT / f)}")
        return 0

    for f, text in results.items():
        path = ROOT / f
        before = sha(path)
        path.write_bytes(text.encode("utf-8", "surrogateescape"))
        print(f"WROTE {f:<44} {before} -> {sha(path)}")

    print("done. Rebuild, then verify with tools/eol_census.py.")
    return 0


if __name__ == "__main__":
    ast.parse(Path(__file__).read_text(encoding="utf-8"))
    raise SystemExit(main())
