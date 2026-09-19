#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v111_stalepub.py -- v1.11: the takeover gate now watches the PUBLISHED
stream instead of a counter that the frozen family itself keeps resetting.

ROOT CAUSE, from the 14:20 run of 2026-09-19 (every number below is read out of
DynamicShaderFrameGen.log; nothing is inferred)

  The run is the first one with v1.10's moving-family takeover live.

  1. Before 14:28:14 the game was in the MAIN MENU (XRAY `MENU EDGE open=1
     serial=2` at 14:21:03 -> `open=0 serial=16308` at 14:28:14.271), at a
     steady real=39.0 with hwMax=6 ask=4 accepted=4.

  2. The moment the world started, the anchor was lost:
        14:28:14.278  lock RELEASED on the reset edge (was proj00=1  famRej=34258)
        14:28:14.412  lock RELEASED on the reset edge (was proj00=0.8391 famRej=34276)
        14:28:14.346  [MOTION] clipToPrevClip[3].w=-195.222366 (must be 1)
                      v1.08 PROBE: p00 cur=1.1918 prev=0.0000 | mag invSrc=203.9
     Then, for the rest of the log, a single frozen state:
        pos=(-243.05,-415.31,118.56)  matChanges=542   move=0.0000  path=151.05
        lock(pub/hold/re/still)=149766/34951/274/0   proj00=0.8391  famRej=34681
        clipDev=0.000061  prevPos == pos  prevVP == curVP
     i.e. frameBufferCopy is byte-frozen while a family that IS walking
     (proj00=1, pos=(-865.8,657.2,285.8) / (-125.9,-190.7,187.0) / ...) is
     refused ~100 times a second.  clipToPrevClip == I -> DLSS-G is told the
     camera never moved -> the 3 interpolated frames of every present are
     duplicates -> the picture is frozen while frames keep presenting.

  3. WHY v1.10's escape hatch could not save it.  The takeover was gated on
        snapLockStill >= kCamForeignMinRej (30)
     and snapLockStill is set to 0 by EVERY accepted arrival:

        FrameGen.cpp:1073   } else { snapLockStill = 0; }      // `continues`
        FrameGen.cpp:1069   snapLockStill = 0;                 // step break
        FrameGen.cpp:933    snapLockStill = 0;                 // acquire

     The frozen family arrives at d2 == 0 against its own previous arrival, so
     `continues` is true, so it is accepted, so `still` goes back to 0.  The log
     shows exactly that: `still=3/90`, `still=8/90` ... never 30, while famRej
     climbs 34258 -> 34681.  81.6% of 184 000 arrivals were published, and the
     frozen family dominated them.
     The one takeover that DID fire (14:28:11.972, "travelled 255.4 units") fired
     only because a release had just set snapHaveLast=false; and it PROVED the
     mechanism works -- matChanges went 2 -> 542 in three seconds.

  => The gate must watch the published stream, not an arrival counter that the
     frozen source resets.  That is the whole change.

WHAT THIS PATCH DOES

  * FrameGen.h   : adds `snapPubStale` (consecutive publishes with a byte-identical
                   matrix) next to the existing snapMatChanges probe.
  * FrameGen.cpp : resets / increments it at the publish site (one site, so there
                   is no second writer to get wrong);
                   replaces kCamForeignMinRej with kCamPubStaleTol and gates the
                   v1.10 takeover on it;
                   prints `stalePub=` on the [CAM] pub heartbeat and extends the
                   verdict string so a frozen published stream is named as such.

WHAT THIS PATCH DELIBERATELY DOES NOT DO

  * It does not touch the lock state machine, the family fingerprint, the release
    path or the step-break logic.  The only behavioural difference is WHICH number
    opens the takeover, and that number is now a direct measurement of the failure
    instead of a proxy that the failure resets.
  * It does not add a second reset writer.  `snapPubStale = 0` happens on exactly
    one branch (the matrix changed), so the counter cannot be zeroed by the very
    source whose stagnation it is supposed to detect.

CONVENTIONS (project iron law -- each one has been violated at least once)
  * dry run by default; --apply writes; --revert undoes
  * anchor count(old) must be exactly 1 else REFUSED, nothing written
  * EOL is decided by the FILE, never by the anchor
  * idempotency: an explicit marker string refuses a second run
  * SPLICE GUARD: the byte before a match must be a newline, a tab, or BOF
  * post-conditions are evaluated on the RESULT text
"""

import sys

F_H = "src/FrameGen.h"
F_CPP = "src/FrameGen.cpp"

MARK = "v1.11: snapLockStill is not a liveness measure"
MARK_H = "v1.11: the takeover gate watches the published stream"


# --------------------------------------------------------------------------- #
# edit 1 -- FrameGen.h: the new state
# --------------------------------------------------------------------------- #
H_OLD = (
    '\tstd::uint64_t snapMatChanges = 0;   // publishes whose matrix differed from the previous one\n'
    '\tbool  snapPubHaveMat = false;\n'
)

H_NEW = (
    '\tstd::uint64_t snapMatChanges = 0;   // publishes whose matrix differed from the previous one\n'
    '\t// ---- v1.11: the takeover gate watches the published stream -------------\n'
    '\t// snapMatChanges proves the stream is ALIVE over a whole run; it cannot\n'
    '\t// prove it is alive NOW. This one can: consecutive publishes that carried\n'
    '\t// a byte-identical matrix. Reset on exactly one branch (the matrix\n'
    '\t// changed) so nothing that suffers stagnation can zero it -- which is\n'
    '\t// precisely what was wrong with the counter v1.10 gated on.\n'
    '\t//\n'
    '\t// The 14:20 run measured the failure this detects: after the world started,\n'
    '\t// pos=(-243.05,-415.31,118.56), matChanges frozen at 542, move=0.0000,\n'
    '\t// clipDev=0.000061 -- while a walking family (proj00=1) was refused\n'
    '\t// ~100 times a second. 200 stale publishes is ~0.6 s of that.\n'
    '\tstd::uint64_t snapPubStale = 0;\n'
    '\tbool  snapPubHaveMat = false;\n'
)

H_MARKER_BYTE = 'snapPubStale'


# --------------------------------------------------------------------------- #
# edit 2 -- FrameGen.cpp: kCamForeignMinRej -> kCamPubStaleTol
# --------------------------------------------------------------------------- #
C_OLD = (
    '\t\t// Floor on the refusal count so two jittery arrivals cannot take the\n'
    '\t\t// anchor by accident. 30 arrivals is ~0.06 s at the measured 500/s and\n'
    '\t\t// ~0.33 s at the 90/s the world phase actually ran at.\n'
    '\t\tconstexpr std::uint32_t kCamForeignMinRej = 30;\n'
)

C_NEW = (
    '\t\t// ---- v1.11: snapLockStill is not a liveness measure -------------------\n'
    '\t\t// v1.10 gated the takeover below on\n'
    '\t\t//     snapLockStill >= kCamForeignMinRej (= 30)\n'
    '\t\t// and that gate is dead by construction: snapLockStill is reset to 0 by\n'
    '\t\t// EVERY accepted arrival, and a frozen family arrives at d2 == 0 against\n'
    '\t\t// its own previous arrival, so `continues` is true, so it is accepted,\n'
    '\t\t// so the counter goes back to zero. The 14:20 run is the measurement:\n'
    '\t\t// 81.6% of 184 000 arrivals were published, the frozen family dominated\n'
    '\t\t// them, and `still` never left the 3..8 band while famRej climbed past\n'
    '\t\t// 34 000. The one takeover that DID fire (14:28:11.972) fired because a\n'
    '\t\t// release had just cleared snapHaveLast for an unrelated reason -- and\n'
    '\t\t// it worked: matChanges went 2 -> 542 in three seconds.\n'
    '\t\t//\n'
    '\t\t// So gate on what we actually care about, measured at the publish site\n'
    '\t\t// instead of the arrival site: how many consecutive publishes carried a\n'
    '\t\t// byte-identical matrix. 200 publishes is ~0.6 s of a provably dead\n'
    '\t\t// published stream at the measured ~330/s.\n'
    '\t\t//\n'
    '\t\t// The SECOND condition is unchanged and is still what makes this safe: a\n'
    '\t\t// parked or stale family contributes no travel, so a legitimately still\n'
    '\t\t// player -- where an identity clipToPrev is CORRECT -- can never hand the\n'
    '\t\t// anchor away. Only a family that has walked >= kCamForeignMoveTol on its\n'
    '\t\t// own can take it.\n'
    '\t\tconstexpr std::uint64_t kCamPubStaleTol = 200;\n'
)


# --------------------------------------------------------------------------- #
# edit 3 -- FrameGen.cpp: the gate itself
# --------------------------------------------------------------------------- #
G_OLD = (
    '\t\t\t\t\t\tif (snapLockStill >= kCamForeignMinRej &&\n'
    '\t\t\t\t\t\t    snapForeignMove >= kCamForeignMoveTol) {\n'
)

G_NEW = (
    '\t\t\t\t\t\t// v1.11: was snapLockStill >= kCamForeignMinRej, which the\n'
    '\t\t\t\t\t\t// frozen family reset to 0 on every one of its own accepts.\n'
    '\t\t\t\t\t\t// See the kCamPubStaleTol comment for the 14:20 numbers.\n'
    '\t\t\t\t\t\tif (snapPubStale >= kCamPubStaleTol &&\n'
    '\t\t\t\t\t\t    snapForeignMove >= kCamForeignMoveTol) {\n'
)


# --------------------------------------------------------------------------- #
# edit 4 -- FrameGen.cpp: the takeover log line
# --------------------------------------------------------------------------- #
L_OLD = (
    '\t\t\t\t\t\t\t\tSKSE::log::info("[CAM] #{} FOREIGN TAKEOVER (v1.10): locked "\n'
    '\t\t\t\t\t\t\t\t\t"proj00={:.6g} has not moved for {} arrivals while the "\n'
    '\t\t\t\t\t\t\t\t\t"refused family proj00={:.6g} travelled {:.1f} units - "\n'
    '\t\t\t\t\t\t\t\t\t"adopting pos=({:.1f},{:.1f},{:.1f})",\n'
    '\t\t\t\t\t\t\t\t\tsnapArrivals,\n'
    '\t\t\t\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f,\n'
    '\t\t\t\t\t\t\t\t\tsnapLockStill, proj00, snapForeignMove, px, py, pz);\n'
)

L_NEW = (
    '\t\t\t\t\t\t\t\tSKSE::log::info("[CAM] #{} FOREIGN TAKEOVER (v1.11): locked "\n'
    '\t\t\t\t\t\t\t\t\t"proj00={:.6g} has gone {} publishes with an unchanged "\n'
    '\t\t\t\t\t\t\t\t\t"matrix while the refused family proj00={:.6g} travelled "\n'
    '\t\t\t\t\t\t\t\t\t"{:.1f} units - adopting pos=({:.1f},{:.1f},{:.1f})",\n'
    '\t\t\t\t\t\t\t\t\tsnapArrivals,\n'
    '\t\t\t\t\t\t\t\t\tsnapLockProjValid ? snapLockProj00 : 0.0f,\n'
    '\t\t\t\t\t\t\t\t\tsnapPubStale, proj00, snapForeignMove, px, py, pz);\n'
)


# --------------------------------------------------------------------------- #
# edit 5 -- FrameGen.cpp: the publish-site counter
# --------------------------------------------------------------------------- #
P_OLD = (
    '\t\t\tif (!same) ++snapMatChanges;\n'
)

P_NEW = (
    '\t\t\tif (!same) {\n'
    '\t\t\t\t++snapMatChanges;\n'
    '\t\t\t\t// v1.11: the published stream moved, so the lock is demonstrably\n'
    '\t\t\t\t// alive. THIS IS THE ONLY WRITE THAT CLEARS THE COUNTER -- a\n'
    '\t\t\t\t// second writer (an accept, a release, a timer) would let the\n'
    '\t\t\t\t// stagnation erase the evidence of itself, which is exactly the\n'
    '\t\t\t\t// defect this release removes.\n'
    '\t\t\t\tsnapPubStale = 0;\n'
    '\t\t\t} else {\n'
    '\t\t\t\t// v1.11: the SAME matrix went out again. The direct measurement of\n'
    '\t\t\t\t// "the published stream is dead" -- snapMatChanges can only report\n'
    '\t\t\t\t// that it is dead on average over a whole run.\n'
    '\t\t\t\t++snapPubStale;\n'
    '\t\t\t}\n'
)


# --------------------------------------------------------------------------- #
# edit 6 -- FrameGen.cpp: stalePub= on the heartbeat
# --------------------------------------------------------------------------- #
Q_OLD = (
    '\t\t\t\t\t\t"fMove={:.1f} takeover={} | {}",\n'
)

Q_NEW = (
    '\t\t\t\t\t\t"fMove={:.1f} takeover={} stalePub={} | {}",\n'
)

QA_OLD = (
    '\t\t\t\t\t\tsnapForeignMove, snapForeignTakeover,\n'
)

QA_NEW = (
    '\t\t\t\t\t\tsnapForeignMove, snapForeignTakeover,\n'
    '\t\t\t\t\t\tsnapPubStale,\n'
)


# --------------------------------------------------------------------------- #
# edit 7 -- FrameGen.cpp: name the frozen published stream in the verdict
# --------------------------------------------------------------------------- #
V_OLD = (
    '\t\t\t\t\t\tsnapMatChanges == 0u\n'
    '\t\t\t\t\t\t\t? "PROBLEM nothing has ever been published with a changed matrix"\n'
    '\t\t\t\t\t\t\t: "ok");\n'
)

V_NEW = (
    '\t\t\t\t\t\tsnapMatChanges == 0u\n'
    '\t\t\t\t\t\t\t? "PROBLEM nothing has ever been published with a changed matrix"\n'
    '\t\t\t\t\t\t\t: (snapPubStale >= kCamPubStaleTol\n'
    '\t\t\t\t\t\t\t\t   ? "PROBLEM the published camera has been byte-identical for a long run"\n'
    '\t\t\t\t\t\t\t\t   : "ok"));\n'
)


PLAN = [
    # (file, label, old, new, must-see-in-result)
    (F_H,   "h_state",     H_OLD,  H_NEW,  MARK_H),
    (F_CPP, "cpp_consts",  C_OLD,  C_NEW,  "kCamPubStaleTol = 200;"),
    (F_CPP, "cpp_gate",    G_OLD,  G_NEW,  "if (snapPubStale >= kCamPubStaleTol &&"),
    (F_CPP, "cpp_takelog", L_OLD,  L_NEW,  "FOREIGN TAKEOVER (v1.11)"),
    (F_CPP, "cpp_pubcnt",  P_OLD,  P_NEW,  MARK),
    (F_CPP, "cpp_fmt",     Q_OLD,  Q_NEW,  'stalePub={}'),
    (F_CPP, "cpp_args",    QA_OLD, QA_NEW, None),
    (F_CPP, "cpp_verdict", V_OLD,  V_NEW,  "byte-identical for a long run"),
]


def file_eol(path):
    """EOL comes from the FILE. A single-line anchor contains no newline, so the
    anchor itself can never tell us the convention (v1.09: this mistake wrote 78
    bare LF into a pure-CRLF file and every post-condition still passed)."""
    with open(path, "rb") as f:
        b = f.read()
    crlf = b.count(b"\r\n")
    return "\r\n" if crlf > (b.count(b"\n") - crlf) else "\n"


def splice_ok(text, idx):
    """A match that starts in the middle of a token is not an insertion point.
    v1.09: the anchor `bool SKSEAPI SKSEPlugin_Load(...)` matched inside
    `extern "C" DLLEXPORT bool SKSEAPI ...` and moved `dllexport` onto a static
    function (error C2201)."""
    if idx == 0:
        return True
    return text[idx - 1] in ("\n", "\t")


def main():
    do_apply = "--apply" in sys.argv
    do_revert = "--revert" in sys.argv

    by_file = {}
    for path, label, old, new, want in PLAN:
        by_file.setdefault(path, []).append((label, old, new, want))

    results = []
    for path, edits in by_file.items():
        with open(path, "rb") as f:
            raw = f.read()
        eol = file_eol(path)
        text = raw.decode("utf-8")
        crlf = raw.count(b"\r\n")
        print(f"--- {path}  ({len(raw)} B, eol={eol!r}, CRLF={crlf}, "
              f"bareLF={raw.count(chr(10).encode()) - crlf})")

        if not do_revert:
            if MARK in text or MARK_H in text:
                print("    REFUSED: marker already present -- patch already applied")
                return 1
            if H_MARKER_BYTE in text:
                print(f"    REFUSED: {H_MARKER_BYTE!r} already present")
                return 1

        for label, old, new, want in edits:
            o = old.replace("\n", eol)
            n = new.replace("\n", eol)
            c = text.count(o)
            print(f"    {label:15s} count={c}")
            if c != 1:
                print(f"    REFUSED, nothing written ({label}: want 1)")
                return 2
            if not splice_ok(text, text.index(o)):
                print(f"    REFUSED, nothing written ({label}: splice guard)")
                return 3
            if do_revert:
                if text.count(n) != 1:
                    print(f"    REFUSED, nothing written (revert {label})")
                    return 4
                text = text.replace(n, o, 1)
            else:
                text = text.replace(o, n, 1)
        results.append((path, raw, text, eol, edits))

    # ---- post-conditions on the RESULT text ----
    bad = []
    for path, raw, text, eol, edits in results:
        if do_revert:
            if MARK in text or MARK_H in text:
                bad.append(f"{path}: marker still present after revert")
            continue
        for label, old, new, want in edits:
            if want and want not in text:
                bad.append(f"{path}:{label} missing {want!r}")
        # The DECLARATION must be gone. The NAME may still appear inside the new
        # comments -- naming the retired constant is the archaeology, so the
        # assertion is on the declaration, not on the identifier.
        if path == F_CPP and "constexpr std::uint32_t kCamForeignMinRej" in text:
            bad.append(f"{path}: kCamForeignMinRej is still declared")
        # it must also no longer be USED, i.e. not on a non-comment line
        if path == F_CPP:
            for ln in text.split("\n"):
                s = ln.strip()
                if s.startswith("//") or s.startswith("*"):
                    continue
                if "kCamForeignMinRej" in s:
                    bad.append(f"{path}: kCamForeignMinRej still used: {s[:70]}")
        # and the counter must have exactly one clearing write
        if path == F_CPP and text.count("snapPubStale = 0;") != 1:
            bad.append(f"{path}: snapPubStale = 0 appears "
                       f"{text.count('snapPubStale = 0;')} times, want 1")
    print("post-conditions:", "PASS" if not bad else f"FAIL {bad}")
    if bad:
        print("REFUSED, nothing written")
        return 5

    if not do_apply:
        print("DRY RUN ok -- re-run with --apply to write")
        return 0

    for path, raw, text, eol, edits in results:
        out = text.encode("utf-8")
        with open(path, "wb") as f:
            f.write(out)
        crlf = out.count(b"\r\n")
        print(f"written {path}: {len(raw)} B -> {len(out)} B  "
              f"(CRLF={crlf}, bareLF={out.count(chr(10).encode()) - crlf})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
