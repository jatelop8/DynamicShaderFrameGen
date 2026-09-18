#!/usr/bin/env python3
"""
patch_v102b_diag_1.py -- v1.02 diagnostics: camPrevOk / camPrevUsed.

Adds the two counters the v1.02 camera-history fix needs to be verifiable from
a log, and prints them on the [XRAY] heartbeat next to the existing cam(ok/inv)
column so the two halves of the reprojection pair are visible in the same frame.

Also bumps the banner to v1.02 so a run can be attributed to this build.

Guards: --apply to write, exact-once anchors, post-conditions, eol preserved.
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SL_H = os.path.join(ROOT, "src", "Streamline.h")
SL_CPP = os.path.join(ROOT, "src", "Streamline.cpp")


# ---------------------------------------------------------------------------
# Streamline.h -- declare the two counters.
# ---------------------------------------------------------------------------
H_OLD = (
    "\t\t\t// v0.82: no self-maintained history -> seed from the engine's prev.\n"
)

H_NEW = (
    "\t\t\t// ---- v1.02: rebuilt previous-camera accounting ----\n"
    "\t\t\t// camPrevOk: the frame carried a usable rebuild of the PREVIOUS\n"
    "\t\t\t// camera (Proj @ [R_prev | -R_prev @ eye_prev]). camPrevUsed: that\n"
    "\t\t\t// matrix was the one actually handed to DLSS-G. A value that stays 0\n"
    "\t\t\t// while camValid rises means the rebuild never took, and the old\n"
    "\t\t\t// engine-prev path is still feeding clipToPrevClip.\n"
    "\t\t\tstd::uint64_t camPrevOk = 0;\n"
    "\t\t\tstd::uint64_t camPrevUsed = 0;\n"
    "\t\t\t// v0.82: no self-maintained history -> seed from the engine's prev.\n"
)


# ---------------------------------------------------------------------------
# Streamline.cpp -- banner.
# ---------------------------------------------------------------------------
B_OLD = '\t\t\t\tSKSE::log::info("[XRAY] diag active v1.00 (compiled " __DATE__ " " __TIME__ ")");\n'
B_NEW = '\t\t\t\tSKSE::log::info("[XRAY] diag active v1.02 (compiled " __DATE__ " " __TIME__ ")");\n'


# ---------------------------------------------------------------------------
# Streamline.cpp -- heartbeat format string: one extra column after cam(ok/inv).
# ---------------------------------------------------------------------------
F_OLD = (
    '"capUs={} mult(acc/pres)={}/{} longFrames={} cam(ok/inv)={}/{} | "\n'
)

F_NEW = (
    '"capUs={} mult(acc/pres)={}/{} longFrames={} cam(ok/inv)={}/{} camPrev(ok/used)={}/{} | "\n'
)


# ---------------------------------------------------------------------------
# Streamline.cpp -- heartbeat argument list.
# ---------------------------------------------------------------------------
A_OLD = (
    "\t\t\t\t\tdiag.camValid, diag.camInvalid,\n"
    "\t\t\t\t\t(diag.reprojSource == 2 ? \"fixed\"\n"
)

A_NEW = (
    "\t\t\t\t\tdiag.camValid, diag.camInvalid,\n"
    "\t\t\t\t\tdiag.camPrevOk, diag.camPrevUsed,\n"
    "\t\t\t\t\t(diag.reprojSource == 2 ? \"fixed\"\n"
)


EDITS = [
    ("h: declare camPrevOk / camPrevUsed", H_OLD, H_NEW),
    ("banner -> v1.02", B_OLD, B_NEW),
    ("heartbeat format string", F_OLD, F_NEW),
    ("heartbeat argument list", A_OLD, A_NEW),
]


def read_text(path):
    with open(path, "rb") as f:
        raw = f.read()
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    eol = "\r\n" if crlf > lf else "\n"
    return raw.decode("utf-8"), eol


def _fix_eol(block, eol):
    """The anchors are written with \n; convert to the file's own ending."""
    if eol == "\r\n":
        return block.replace("\r\n", "\n").replace("\n", "\r\n")
    return block.replace("\r\n", "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    h_txt, h_eol = read_text(SL_H)
    c_txt, c_eol = read_text(SL_CPP)
    print("Streamline.h   : {} chars eol={}".format(len(h_txt), repr(h_eol)))
    print("Streamline.cpp : {} chars eol={}".format(len(c_txt), repr(c_eol)))

    targets = [
        (SL_H, h_txt, [EDITS[0]]),
        (SL_CPP, c_txt, [EDITS[1], EDITS[2], EDITS[3]]),
    ]

    bad = False
    for path, txt, edits in targets:
        eol = h_eol if path == SL_H else c_eol
        for label, old, new in edits:
            n = txt.count(_fix_eol(old, eol))
            print("  [{}] {:<40} count={}".format("OK " if n == 1 else "BAD", label, n))
            if n != 1:
                bad = True
    if bad:
        print("REFUSED: anchor missing or not unique; nothing written.")
        return 2

    # Build the results first, then post-check the RESULT (not the input).
    results = []
    for path, txt, edits in targets:
        eol = h_eol if path == SL_H else c_eol
        out = txt
        for label, old, new in edits:
            out = out.replace(_fix_eol(old, eol), _fix_eol(new, eol), 1)
        results.append((path, txt, out))

    # Post-check: placeholder/argument balance on the heartbeat.
    c_out = [o for p, _, o in results if p == SL_CPP][0]
    fmt_n = c_out.count("camPrev(ok/used)={}/{}")
    args_n = c_out.count("diag.camPrevOk, diag.camPrevUsed,")
    print("  [{}] heartbeat placeholder <-> argument   count={}/{}".format(
        "OK " if (fmt_n == 1 and args_n == 1) else "BAD", fmt_n, args_n))
    if fmt_n != 1 or args_n != 1:
        print("REFUSED: heartbeat wiring incomplete; nothing written.")
        return 3

    if not args.apply:
        for path, txt, out in results:
            print("  DRY  {:<16} {} -> {} chars".format(os.path.basename(path), len(txt), len(out)))
        print("DRY RUN: pass --apply to write.")
        return 0

    for path, txt, out in results:
        bak = path + ".bak-v102b"
        if not os.path.exists(bak):
            with open(bak, "wb") as f:
                f.write(txt.encode("utf-8"))
        with open(path, "wb") as f:
            f.write(out.encode("utf-8"))
        print("APPLIED {}: {} -> {} chars".format(os.path.basename(path), len(txt), len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
