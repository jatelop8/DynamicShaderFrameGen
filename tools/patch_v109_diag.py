# -*- coding: utf-8 -*-
"""
v1.09-diag -- DIAGNOSTICS ONLY. No behaviour change.

Why this patch exists
---------------------
Two days of runs could not answer "why does the published camera stop moving".
Two structural reasons were found by reading the code against the logs:

  1. The only per-frame instrumentation (mapHit / lock(...) / clipDev / frozen)
     lives inside CheckFrameConstants, which lives inside EvaluateDLSSG, which
     is only called when featureDLSSG is true (DX12SwapChain.cpp:1419). With
     Provider=0 (FSR3) that call never happens, so the 09:55 log contained
     ZERO heartbeats. Every conclusion drawn from it was drawn from air.

  2. The gate DOES run on both providers (it lives in the Map/Unmap hook), but
     its output was throttled to 0.25 s and capped at 200 lines -- 50 seconds,
     which expired before the player had control. On top of that, `snapAccept`
     counts PUBLISHES, not changes, so 19 288 consecutive publishes of a
     byte-identical matrix looked like a healthy, busy capture layer.

  3. The SKSE log sink truncates its file on open, so every launch destroys the
     previous run's evidence. The only run that reproduced the freeze
     (2026-09-19 07:36) was overwritten six minutes later and is gone.

What this patch changes (all three items are additive)
------------------------------------------------------
  A. main.cpp: archive the previous session's log before SKSE::Init truncates
     it, date-stamped, pruned by age (7 days). Evidence now survives a rerun.
  B. FrameGen.cpp/.h: track and print how often the PUBLISHED matrix changes,
     and make the published-camera trace run for the whole session at 1 Hz.
  C. Comment-only corrections for two defects proven against the log:
       * kCamStillTol has no comparison anywhere -- the release it documents is
         dead code (verified by a whole-project grep).
       * every "consecutive arrivals" threshold is calibrated for 60 arrivals/s
         while the hook actually sees 493-502/s, so each fires ~8x early.

Nothing here touches the lock state machine. That changes only after the
published-stream trace has said which of the two candidate causes is real.
"""

import io
import os
import sys

ROOT = r"D:/Modding/DynamicShaderFrameGen"
FRAMEGEN_CPP = os.path.join(ROOT, "src", "FrameGen.cpp")
FRAMEGEN_H = os.path.join(ROOT, "src", "FrameGen.h")
MAIN_CPP = os.path.join(ROOT, "src", "main.cpp")

# ---------------------------------------------------------------- new text ---

# --- FrameGen.h: published-stream change counter -----------------------------
H_FIELDS = """
\t// ---- v1.09: is the PUBLISHED stream actually moving? ----
\t// `snapAccept` counts publishes, not changes. The 09:55 run published a
\t// byte-identical matrix 19 288 times in a row, so a dead capture layer and a
\t// healthy one looked identical in the log. This counter separates them, and
\t// it is live on both providers because the gate runs in the Map/Unmap hook.
\tstd::uint64_t snapMatChanges = 0;   // publishes whose matrix differed from the previous one
\tbool  snapPubHaveMat = false;
\tfloat snapPubLastMat[4][4] = {};
"""

# --- FrameGen.cpp: count matrix changes at the single publish site -----------
CPP_MATCHANGES = """
\t\t// v1.09: how often the matrix we PUBLISH actually changes. `snapAccept`
\t\t// alone cannot answer that -- 19 288 consecutive accepts at a byte-identical
\t\t// matrix is exactly what the freeze looks like from this side.
\t\t{
\t\t\tbool same = snapPubHaveMat;
\t\t\tif (same) {
\t\t\t\tfor (int r = 0; r < 4 && same; ++r) {
\t\t\t\t\tfor (int k = 0; k < 4; ++k) {
\t\t\t\t\t\tif (snapPubLastMat[r][k] != a_src.CameraViewProjUnjittered.data[r][k]) {
\t\t\t\t\t\t\tsame = false;
\t\t\t\t\t\t\tbreak;
\t\t\t\t\t\t}
\t\t\t\t\t}
\t\t\t\t}
\t\t\t}
\t\t\tif (!same) ++snapMatChanges;
\t\t\tfor (int r = 0; r < 4; ++r)
\t\t\t\tfor (int k = 0; k < 4; ++k)
\t\t\t\t\tsnapPubLastMat[r][k] = a_src.CameraViewProjUnjittered.data[r][k];
\t\t\tsnapPubHaveMat = true;
\t\t}
"""

# --- FrameGen.cpp: the published-stream trace, right after [CAM] acc ---------
CPP_PUB_LINE = """
\t\t\t\t// v1.09: the published-stream trace.
\t\t\t\t//
\t\t\t\t// `matChanges` counts publishes whose matrix differed from the one
\t\t\t\t// published before it. A stream that stops changing while the player
\t\t\t\t// walks IS the freeze -- clipToPrev collapses to identity and DLSS-G
\t\t\t\t// repeats the previous frame -- and no other line shows it directly.
\t\t\t\t//
\t\t\t\t// `arrivals/s` settles the calibration defect: every "consecutive
\t\t\t\t// arrivals" threshold in this file was written for 60 arrivals/s
\t\t\t\t// (kCamStillTol = "~1.5 s at 60 Hz"), while the hook is measured at
\t\t\t\t// 493-502/s because the engine maps the perFrame buffer ~12 times per
\t\t\t\t// rendered frame. Each of those thresholds therefore fires about
\t\t\t\t// eight times earlier than its comment intends.
\t\t\t\t{
\t\t\t\t\tstatic std::uint64_t rateLastArrivals = 0;
\t\t\t\t\tstatic std::uint64_t rateLastTick = 0;
\t\t\t\t\tconst std::uint64_t tickNow = ::GetTickCount64();
\t\t\t\t\tfloat arrPerSec = 0.0f;
\t\t\t\t\tif (rateLastTick != 0u && tickNow > rateLastTick) {
\t\t\t\t\t\tarrPerSec = static_cast<float>(snapArrivals - rateLastArrivals) * 1000.0f /
\t\t\t\t\t\t\tstatic_cast<float>(tickNow - rateLastTick);
\t\t\t\t\t}
\t\t\t\t\trateLastArrivals = snapArrivals;
\t\t\t\t\trateLastTick = tickNow;
\t\t\t\t\tSKSE::log::info("[CAM] pub #{} pos=({:.2f},{:.2f},{:.2f}) move={:.4f} path={:.2f} "
\t\t\t\t\t\t"matChanges={} arrivalsPerSec={:.0f} | lock(pub/hold/re/still)={}/{}/{}/{} "
\t\t\t\t\t\t"proj00={:.6g} famRej={} frozenRep={} ident/diff={}/{} | {}",
\t\t\t\t\t\tsnapAccept, px, py, pz, snapAcceptDist, snapPathLen, snapMatChanges,
\t\t\t\t\t\tarrPerSec, snapLockPublish, snapLockHold, snapLockRelock, snapLockStill,
\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f, snapLockFamilyRej,
\t\t\t\t\t\tsnapFrozenRepeats, snapIdenticalArrivals, snapDifferentArrivals,
\t\t\t\t\t\tsnapMatChanges == 0u
\t\t\t\t\t\t\t? "PROBLEM nothing has ever been published with a changed matrix"
\t\t\t\t\t\t\t: "ok");
\t\t\t\t}
"""

# --- FrameGen.cpp: comment fixes for the two proven defects ------------------
CPP_STILL_DOC = """\t\t// short enough that a genuine scene change re-locks promptly.
\t\t//
\t\t// v1.09 -- THIS THRESHOLD IS NOT CONSUMED ANYWHERE.
\t\t// A whole-project grep finds kCamStillTol in exactly four places: this
\t\t// definition, three comments, and two log-format argument lists. There is
\t\t// no comparison against it, so the release that the comment above promises
\t\t// does not exist. The v1.07b note at the same site says the reset edge is
\t\t// "the ONLY release path", and snapLockStill is reset to 0 by every accept
\t\t// (so `still=2/90` never grows). Observed consequence: the lock has no
\t\t// release of its own, so whichever family wins the first acquire keeps the
\t\t// stream until the process exits.
\t\t//
\t\t// v1.09 -- AND THE NUMBER IS WRONG BY 8x.
\t\t// 90 arrivals is not "~1.5 s at 60 Hz", it is 0.18 s: the Map/Unmap hook
\t\t// fires 493-502 times per second (measured: 612 arrivals per 1.22 s, at
\t\t// 41.4 rendered fps, i.e. ~12 maps per frame). Every arrival-count
\t\t// threshold in this file carries the same 8.2x error."""

CPP_FROZEN_DOC = """\tconstexpr std::uint32_t kCamFrozenTol = 600;
\t// v1.09: 600 arrivals is 1.2 s at the measured 493-502 arrivals/s, not the
\t// 10 s this comment describes. The gate itself was downgraded to a counter
\t// in v0.93 ("gates observe, they do not discard"), so this detector fires
\t// and changes nothing -- see the [CAM] pub `frozenRep=` field for its value."""

# --- main.cpp: keep the previous session's log -------------------------------
MAIN_ARCHIVE_FN = """// v1.09: keep the previous session's log.
//
// CommonLibSSE-NG's spdlog sink is a rotating logger whose base file is
// truncated when it is opened, so every launch destroys the previous run's
// evidence. That is exactly how the one run that reproduced the freeze
// (2026-09-19 07:36) was lost: it was overwritten six minutes later by the next
// launch, and the freeze could no longer be re-examined from the log that saw
// it. One copy before SKSE::Init keeps it.
//
// The archive name is `DynamicShaderFrameGen.<YYYYMMDD>-<HHMMSS>.log`, which
// sorts chronologically. Archives older than 7 days are deleted. The delete is
// restricted to files matching `DynamicShaderFrameGen.20*.log`, so it can never
// touch the watchdog log or any other plugin's log -- the `20` prefix is the
// year, and the watchdog log is named `.watchdog.log`.
static void ArchivePreviousLog()
{
\tconst char* wd = FrameGen::WatchdogLogPath();
\tif (wd == nullptr || wd[0] == '\\0')
\t\treturn;

\tchar dir[MAX_PATH] = {};
\tstd::snprintf(dir, sizeof(dir), "%s", wd);
\tint cut = -1;
\tfor (int i = 0; dir[i] != '\\0'; ++i)
\t\tif (dir[i] == '\\\\')
\t\t\tcut = i;
\tif (cut <= 0)
\t\treturn;
\tdir[cut] = '\\0';

\tchar src[MAX_PATH] = {};
\tstd::snprintf(src, sizeof(src), "%s\\\\DynamicShaderFrameGen.log", dir);
\tif (::GetFileAttributesA(src) == INVALID_FILE_ATTRIBUTES)
\t\treturn;   // no previous run to preserve

\tSYSTEMTIME st{};
\t::GetLocalTime(&st);
\tfor (int attempt = 0; attempt < 120; ++attempt) {
\t\tchar dst[MAX_PATH] = {};
\t\t::GetLocalTime(&st);   // refresh so a long copy cannot skew the stamp
\t\tstd::snprintf(dst, sizeof(dst),
\t\t\t"%s\\\\DynamicShaderFrameGen.%04d%02d%02d-%02d%02d%02d.log",
\t\t\tdir, st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
\t\tif (::CopyFileA(src, dst, TRUE))       // TRUE = never overwrite
\t\t\tbreak;
\t\tif (::GetLastError() != ERROR_FILE_EXISTS)
\t\t\tbreak;
\t\t::Sleep(1000);                          // collision: wait for the next second
\t}

\t// Prune. Cutoff string is YYYYMMDD; the stamp starts at offset 21, which is
\t// the length of "DynamicShaderFrameGen.".
\tFILETIME nowFt{};
\t::GetSystemTimeAsFileTime(&nowFt);
\tULARGE_INTEGER t{};
\tt.LowPart = nowFt.dwLowDateTime;
\tt.HighPart = nowFt.dwHighDateTime;
\tt.QuadPart -= 7ull * 24ull * 60ull * 60ull * 10000000ull;
\tFILETIME cutFt{};
\tcutFt.dwLowDateTime = t.LowPart;
\tcutFt.dwHighDateTime = t.HighPart;
\tSYSTEMTIME cutSt{};
\tchar cutoff[16] = {};
\tif (::FileTimeToSystemTime(&cutFt, &cutSt))
\t\tstd::snprintf(cutoff, sizeof(cutoff), "%04d%02d%02d", cutSt.wYear, cutSt.wMonth, cutSt.wDay);
\tif (cutoff[0] == '\\0')
\t\treturn;

\tchar pattern[MAX_PATH] = {};
\tstd::snprintf(pattern, sizeof(pattern), "%s\\\\DynamicShaderFrameGen.20*.log", dir);
\tWIN32_FIND_DATAA fd{};
\tHANDLE hf = ::FindFirstFileA(pattern, &fd);
\tif (hf == INVALID_HANDLE_VALUE)
\t\treturn;
\tdo {
\t\tif ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0u)
\t\t\tcontinue;
\t\tconst char* stamp = fd.cFileName + 21;
\t\tbool older = true;
\t\tfor (int i = 0; i < 8; ++i) {
\t\t\tif (stamp[i] == '\\0') { older = false; break; }
\t\t\tif (stamp[i] < cutoff[i]) break;
\t\t\tif (stamp[i] > cutoff[i]) { older = false; break; }
\t\t}
\t\tif (!older)
\t\t\tcontinue;
\t\tchar victim[MAX_PATH] = {};
\t\tstd::snprintf(victim, sizeof(victim), "%s\\\\%s", dir, fd.cFileName);
\t\t::DeleteFileA(victim);
\t} while (::FindNextFileA(hf, &fd) != 0);
\t::FindClose(hf);
}

"""

MAIN_CALL = """\t// v1.09: SKSE::Init opens the spdlog sink, which truncates the log file. Copy
\t// the previous session's log out of the way first, or the run that reproduced
\t// the bug is destroyed by the run that follows it.
\tArchivePreviousLog();

\tSKSE::Init(a_skse);"""

# ------------------------------------------------------------------ edits ----

# (file, label, old, new, idempotency_marker)
#
# The marker matters for the four edits whose ANCHOR SURVIVES the edit (pure
# insertions). `count(old) == 1` proves the anchor is unique, not that this
# patch has not already run -- the project has been bitten by exactly that
# twice (DESIGN section 16.3, and skill rule 5). Where the anchor is consumed
# by the edit (pure replacements) no marker is needed: a rerun finds 0 anchors
# and the script refuses on its own.
EDITS = [
    (FRAMEGEN_H, "h_pub_fields",
     "// times a position snapshot was adopted",
     "// times a position snapshot was adopted\n" + H_FIELDS,
     "std::uint64_t snapMatChanges = 0;"),

    (FRAMEGEN_CPP, "cpp_mat_changes",
     "++snapAccept;",
     "++snapAccept;" + CPP_MATCHANGES,
     "snapPubHaveMat = true;"),

    (FRAMEGEN_CPP, "cpp_acc_no_cap_type",
     "static std::uint32_t accLogs = 0;",
     "static std::uint64_t accLogs = 0;",
     None),

    (FRAMEGEN_CPP, "cpp_acc_no_cap_if",
     "if (accLogs < 200u &&\n\t\t\t\t(snapAccept == 1u || "
     "std::chrono::duration<double>(now - lastAccLog).count() >= 0.25)) {",
     "if (snapAccept == 1u || "
     "std::chrono::duration<double>(now - lastAccLog).count() >= 1.0) {",
     None),

    (FRAMEGEN_CPP, "cpp_pub_line",
     "camMag(a_src.CameraViewProjUnjittered), snapConsecReject);",
     "camMag(a_src.CameraViewProjUnjittered), snapConsecReject);" + CPP_PUB_LINE,
     "[CAM] pub #{} pos="),

    (FRAMEGEN_CPP, "cpp_still_doc",
     "\t\t// short enough that a genuine scene change re-locks promptly.",
     CPP_STILL_DOC,
     "THIS THRESHOLD IS NOT CONSUMED ANYWHERE"),

    (FRAMEGEN_CPP, "cpp_frozen_doc",
     "\tconstexpr std::uint32_t kCamFrozenTol = 600;",
     CPP_FROZEN_DOC,
     "600 arrivals is 1.2 s at the measured"),

    (MAIN_CPP, "main_archive_fn",
     'extern "C" DLLEXPORT bool SKSEAPI SKSEPlugin_Load(const SKSE::LoadInterface* a_skse)',
     MAIN_ARCHIVE_FN +
     'extern "C" DLLEXPORT bool SKSEAPI SKSEPlugin_Load(const SKSE::LoadInterface* a_skse)',
     "static void ArchivePreviousLog()"),

    (MAIN_CPP, "main_archive_call",
     "\tSKSE::Init(a_skse);",
     MAIN_CALL,
     "\tArchivePreviousLog();"),
]

POST = [
    (FRAMEGEN_H, "snapMatChanges = 0;", 1),
    (FRAMEGEN_H, "snapPubLastMat[4][4] = {};", 1),
    (FRAMEGEN_CPP, "[CAM] pub #{} pos=", 1),
    (FRAMEGEN_CPP, "arrivalsPerSec=", 1),
    (FRAMEGEN_CPP, "accLogs < 200u", 0),
    (FRAMEGEN_CPP, ">= 0.25", 0),
    (FRAMEGEN_CPP, "if (snapAccept == 1u ||", 1),
    (FRAMEGEN_CPP, "static std::uint64_t accLogs = 0;", 1),
    (MAIN_CPP, "static void ArchivePreviousLog()", 1),
    (MAIN_CPP, "\tArchivePreviousLog();", 1),
    # the pre-existing anchors must survive untouched
    (FRAMEGEN_CPP, "constexpr std::uint32_t kCamStillTol = 90;", 1),
    (FRAMEGEN_CPP, "frameBufferCopy = a_src;", 1),
    (MAIN_CPP, "SKSE::Init(a_skse);", 1),
]


def read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def file_eol(path):
    """The target file's own line ending, decided from the FILE and never from
    the anchor.

    A single-line anchor contains no newline, so it cannot tell you what the file
    uses. Getting this wrong is exactly how the first v1.09 dry run passed 12/12
    post-conditions and still landed 78 bare LF characters inside a pure-CRLF
    file: every anchor matched, and every inserted block was written with LF.
    """
    with io.open(path, "rb") as f:
        d = f.read()
    crlf = d.count(b"\r\n")
    bare = d.count(b"\n") - crlf
    return "\r\n" if crlf >= bare else "\n"


def variants(text, eol):
    """Both encodings of the same block, file-EOL first.

    The forward pass only ever needs one, but the REVERT pass must cope with a
    block that a previous run landed in the wrong encoding -- which is precisely
    the state this script is recovering from.
    """
    primary = text.replace("\n", eol)
    return (primary, text) if primary != text else (primary,)


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    selected = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = sorted({e[0] for e in EDITS} | {p[0] for p in POST})
    if selected:
        wanted = {os.path.basename(s) for s in selected}
        files = [f for f in files if os.path.basename(f) in wanted]
        if not files:
            print("nothing selected (--only %s)" % " ".join(selected))
            return 5
        print("RESTRICTED to: %s" % ", ".join(os.path.basename(f) for f in files))
    cur = {p: read(p) for p in files}
    acts = [e for e in EDITS if e[0] in files]

    if revert:
        ok = True
        for path, label, old, new, marker in acts:
            eol = file_eol(path)
            hit = None
            for cand in variants(new, eol):
                if cur[path].count(cand) == 1:
                    hit = cand
                    break
            if hit is None:
                print("REVERT SKIP [%s] %s: inserted block not found exactly once"
                      % (os.path.basename(path), label))
                ok = False
                continue
            back = old.replace("\n", eol)
            cur[path] = cur[path].replace(hit, back, 1)
            print("  reverted [%s] %s" % (os.path.basename(path), label))
        if not ok:
            print("REVERT INCOMPLETE, nothing written")
            return 4
        if not apply:
            print("DRY REVERT OK -- no file written. Re-run with --revert --apply.")
            return 0
        for p in files:
            write(p, cur[p])
            print("WROTE %s (%d bytes)" % (p, os.path.getsize(p)))
        print("REVERTED")
        return 0

    plan = []
    ok = True
    for path, label, old, new, marker in acts:
        eol = file_eol(path)
        k_old = old.replace("\n", eol)
        n_old = cur[path].count(k_old)
        if n_old != 1:
            print("REFUSED [%s] %s: anchor count = %d (must be exactly 1)"
                  % (os.path.basename(path), label, n_old))
            ok = False
            continue
        # SPLICE GUARD.
        #
        # A short anchor can match in the MIDDLE of a token and tear it in half.
        # That is not hypothetical: the first v1.09 build anchored on
        # `bool SKSEAPI SKSEPlugin_Load(...)` while the line actually reads
        # `extern "C" DLLEXPORT bool SKSEAPI SKSEPlugin_Load(...)`, so the
        # insertion landed BETWEEN `extern "C" DLLEXPORT` and the declaration
        # and the compiler answered with
        #     main.cpp(82): error C2201: 'ArchivePreviousLog' must have external
        #     linkage to be exported/imported
        # The guard is that whatever precedes the match must be a line start or a
        # tab -- a space means we are inside a token sequence and must stop.
        at = cur[path].find(k_old)
        prev = cur[path][at - 1] if at > 0 else "\n"
        if prev not in ("\n", "\t"):
            print("REFUSED [%s] %s: anchor is preceded by %r, i.e. it starts inside a "
                  "token -- widening the anchor to the whole line is required"
                  % (os.path.basename(path), label, prev))
            ok = False
            continue
        # IDEMPOTENCY GUARD -- only for edits whose anchor survives (insertions).
        if marker is not None and marker in cur[path]:
            print("REFUSED [%s] %s: marker %r already present (already applied?)"
                  % (os.path.basename(path), label, marker[:60]))
            ok = False
            continue
        fixed_new = new.replace("\n", eol)     # EOL from the FILE, not the anchor
        plan.append((path, label, k_old, fixed_new, n_old))

    if not ok:
        print("REFUSED, nothing written")
        return 2

    result = dict(cur)
    for path, label, old, new, _n in plan:
        result[path] = result[path].replace(old, new, 1)
        print("  would apply [%s] %s" % (os.path.basename(path), label))

    # post-conditions are checked on the RESULT text, never on the input
    bad = False
    for path, needle, want in POST:
        if path not in files:
            continue
        got = result[path].count(needle)
        flag = "OK " if got == want else "FAIL"
        if got != want:
            bad = True
        print("  %s post %-42r want=%d got=%d" % (flag, needle[:42], want, got))

    if bad:
        print("REFUSED, nothing written (post-conditions failed)")
        return 3

    if not apply:
        print("DRY RUN OK -- no file written. Re-run with --apply to land it.")
        return 0

    for p in files:
        write(p, result[p])
        print("WROTE %s (%d bytes)" % (p, os.path.getsize(p)))
    print("APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
