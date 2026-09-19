#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_v110_archive_order.py -- make v1.09's log archive actually run.

THE DEFECT (found by trying to verify v1.09, not by inspection)
  The 11:30 run was the FIRST run with v1.09's ArchivePreviousLog() in the DLL,
  and it produced no DynamicShaderFrameGen.20*.log:

      ls SKSE/ | grep -c 'DynamicShaderFrameGen\\.20'   ->   0

  Cause, in main.cpp:

      :167    ArchivePreviousLog();              <- reads WatchdogLogPath()
      :173    FrameGen::InitWatchdogLogPath();   <- FILLS it

  WatchdogLogPath() returns the static char buffer g_watchdogLogPath, which is
  empty until InitWatchdogLogPath() runs. So ArchivePreviousLog() hit its first
  guard ("wd == nullptr || wd[0] == '\\0'") and returned. The feature that exists
  to stop the next run from destroying the bug was itself inert, and only a run
  could reveal it.

  Fix: call InitWatchdogLogPath() first. It is SHGetFolderPathA + snprintf --
  no SKSE dependency, safe before SKSE::Init, idempotent, and it is the reason
  the DllMain exit probe can stay a pure Win32 append.

Conventions: dry run unless --apply, anchor count == 1, EOL from the FILE,
marker guard, splice guard, post-conditions on the RESULT text.
"""

import os
import sys

F = "src/main.cpp"
MARK = "the watchdog path must exist BEFORE the copy below"

OLD = (
    '\tArchivePreviousLog();\n'
    '\n'
    '\tSKSE::Init(a_skse);\n'
    '\n'
    '\t// v0.73: cache the watchdog log path before anything can go wrong, so the\n'
    '\t// exit probe in DllMain is a pure Win32 append with no path resolution.\n'
    '\tFrameGen::InitWatchdogLogPath();\n'
)

NEW = (
    '\t// v1.10: the watchdog path must exist BEFORE the copy below, because\n'
    '\t// ArchivePreviousLog() resolves the directory from it and returns at its\n'
    '\t// first guard when the buffer is still empty. v1.09 had the two calls in\n'
    '\t// the other order, and the 11:30 run is the proof: it produced no\n'
    '\t// DynamicShaderFrameGen.20*.log at all, so the archive never ran.\n'
    '\t// InitWatchdogLogPath() is SHGetFolderPathA plus a snprintf - safe before\n'
    '\t// SKSE::Init, idempotent, and it stays cached for the DllMain exit probe.\n'
    '\tFrameGen::InitWatchdogLogPath();\n'
    '\tArchivePreviousLog();\n'
    '\n'
    '\tSKSE::Init(a_skse);\n'
)


def file_eol(path):
    with open(path, "rb") as f:
        b = f.read()
    crlf = b.count(b"\r\n")
    return "\r\n" if crlf > (b.count(b"\n") - crlf) else "\n"


def main():
    do_apply = "--apply" in sys.argv
    do_revert = "--revert" in sys.argv

    with open(F, "rb") as f:
        raw = f.read()
    eol = file_eol(F)
    text = raw.decode("utf-8")
    o = OLD.replace("\n", eol)
    n = NEW.replace("\n", eol)

    if not do_revert and MARK in text:
        print("REFUSED: marker already present -- patch already applied")
        return 1

    if do_revert:
        src, dst = n, o
    else:
        src, dst = o, n

    c = text.count(src)
    print(f"{F}  eol={eol!r}  size={len(raw)} B  anchor count={c}")
    if c != 1:
        print("REFUSED, nothing written (want exactly 1)")
        return 2
    idx = text.index(src)
    if idx != 0 and text[idx - 1] not in ("\n", "\t"):
        print("REFUSED, nothing written (splice guard)")
        return 3

    out_text = text.replace(src, dst, 1)

    bad = []
    if do_revert:
        if MARK in out_text:
            bad.append("marker survived revert")
    else:
        # post-conditions on the RESULT text
        if MARK not in out_text:
            bad.append("marker missing")
        if out_text.count("FrameGen::InitWatchdogLogPath();") != 1:
            bad.append("InitWatchdogLogPath count != 1")
        if out_text.count("ArchivePreviousLog();") != 1:
            bad.append("ArchivePreviousLog count != 1")
        if out_text.find("FrameGen::InitWatchdogLogPath();") > out_text.find("ArchivePreviousLog();"):
            bad.append("ORDER STILL WRONG: archive is called before the path exists")
        if out_text.count("SKSE::Init(a_skse);") != 1:
            bad.append("SKSE::Init count != 1")
    print("post-conditions:", "PASS" if not bad else f"FAIL {bad}")
    if bad:
        print("REFUSED, nothing written")
        return 4

    if not do_apply:
        print("DRY RUN ok -- re-run with --apply to write")
        return 0

    out = out_text.encode("utf-8")
    with open(F, "wb") as f:
        f.write(out)
    print(f"written {F}: {len(raw)} B -> {len(out)} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
