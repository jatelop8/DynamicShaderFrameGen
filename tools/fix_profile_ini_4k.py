#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Make the game's OUTPUT resolution match the DISPLAY MODE -- in the file the game
actually reads.

WHY THE PREVIOUS FIX DID NOTHING (2026-09-17, 19:50 attempt)
----------------------------------------------------------
The previous patch edited
    C:\\Users\\Administrator\\Documents\\My Games\\Skyrim Special Edition\\SkyrimPrefs.ini
and set iSize to 3840x2160.  The running game still reported
    [OPTIONS] Game DLSS-G options: ... color=2560x1440
because that file is NOT the one the game loads.

MO2 profile "DIPEI" has  profiles/DIPEI/settings.ini  containing:
    [General]
    LocalSettings=true          <-- "profile-specific game INI files" is ON

With LocalSettings=true, MO2's usvfs redirects every game INI read to the profile
directory.  The game therefore reads
    E:\\EJ\\mod\\profiles\\DIPEI\\skyrimprefs.ini
which still said  iSize W=2560  iSize H=1440.  The My Games copy was a decoy.

WHY SIZE == DISPLAY MODE MATTERS
--------------------------------
DXGI can only use Independent Flip (the low-latency, tear-free presentation path)
when the swap chain size AND format equal the current display mode.  Output
2560x1440 on a 3840x2160 panel forces DWM composed flip, where the Streamline
pacer cannot lock present timing to the refresh period.  The measured symptom is
exactly what the DFG source itself documents:

    "a 1/4 oscillation (what two pacers fighting over one swap chain looks like)"

and the plugin owner's own INI note:

    "the SL pacer loses its rhythm and the picture flickers continuously"

Observed in this session's log: presented-per-real-frame flipped 1 -> 4 -> 1 -> 4
across the run, i.e. the multiplier oscillates instead of holding 4x.

THE PAIRED CHANGE
-----------------
RenderResolutionScale intentionally stays at 0.44 (already set in the DFG INI).
It is defined as   renderSize = swapChainSize * scale,   so:
    before: 2560x1440 swap chain, Auto(0) quality ratio 2/3  -> 1707x960 render
    after : 3840x2160 swap chain, scale 0.44                 -> 1690x950 render
=> the engine's real render load is unchanged (~1% less), so this is NOT a
   performance regression.  It buys: output matches the panel, Independent Flip
   becomes possible, and DWM's extra rescale disappears.

This script changes ONLY the two iSize lines in the profile INI.
Equal-length substitution: byte count, line count and line endings are preserved
exactly, so a diff against the backup shows precisely two changed lines.
"""

import os
import shutil
import sys
import time

# ---------------------------------------------------------------------------
TARGET = r"E:\EJ\mod\profiles\DIPEI\skyrimprefs.ini"

# (label, old_bytes, new_bytes)  -- every substitution must be EQUAL LENGTH
EDITS = [
    ("iSize W", b"iSize W=2560", b"iSize W=3840"),
    ("iSize H", b"iSize H=1440", b"iSize H=2160"),
]

# Idempotency markers: strings that prove the patch has ALREADY been applied.
# Checked BEFORE the anchor check, per the standing rule that "anchor is unique"
# and "patch runs once" are two different properties.
MARKERS = [b"iSize W=3840", b"iSize H=2160"]

BACKUP_ROOT = r"D:\workbuddy2\backup"
# ---------------------------------------------------------------------------


def fail(msg):
    print("REFUSED, nothing written: " + msg)
    sys.exit(1)


def main():
    apply = "--apply" in sys.argv

    if not os.path.isfile(TARGET):
        fail("target not found: %s" % TARGET)

    with open(TARGET, "rb") as fh:
        src = fh.read()

    print("target              : %s" % TARGET)
    print("size                : %d bytes" % len(src))
    print("lines (LF total)    : %d" % src.count(b"\n"))
    print("lines (CRLF)        : %d" % src.count(b"\r\n"))
    print("")

    # --- guard 1: idempotency (MUST run before the anchor check) -----------
    for m in MARKERS:
        if m in src:
            fail("marker %r already present -- patch has already been applied" % m)
    print("guard 1 (idempotency): no marker present  OK")

    # --- guard 2: anchor uniqueness ----------------------------------------
    for label, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            fail("anchor for %s: %r found %d times (expected exactly 1)" % (label, old, n))
        if len(old) != len(new):
            fail("substitution for %s is not equal length (%d -> %d)" % (label, len(old), len(new)))
    print("guard 2 (anchors)    : each anchor unique, all substitutions equal length  OK")

    out = src
    for label, old, new in EDITS:
        out = out.replace(old, new)

    # --- post-conditions ----------------------------------------------------
    if len(out) != len(src):
        fail("post: byte count changed %d -> %d" % (len(src), len(out)))
    if out.count(b"\n") != src.count(b"\n"):
        fail("post: line count changed")
    if out.count(b"\r\n") != src.count(b"\r\n"):
        fail("post: CRLF count changed")
    for label, old, new in EDITS:
        if out.count(old) != 0:
            fail("post: old value still present for %s" % label)
        if out.count(new) != 1:
            fail("post: new value not exactly once for %s" % label)
    print("post-conditions      : size/lines/endings identical, values swapped  OK")
    print("")

    if not apply:
        print("DRY RUN.  Pass --apply to write.")
        return

    stamp = time.strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(BACKUP_ROOT, "profile_ini_4k_" + stamp)
    os.makedirs(bdir, exist_ok=True)
    bpath = os.path.join(bdir, "skyrimprefs.ini.bak")
    shutil.copy2(TARGET, bpath)
    print("backup              : %s" % bpath)

    with open(TARGET, "wb") as fh:
        fh.write(out)

    with open(TARGET, "rb") as fh:
        check = fh.read()
    if check != out:
        fail("read-back mismatch after write")

    print("written             : %s" % TARGET)
    print("read-back           : identical  OK")
    for label, old, new in EDITS:
        print("  %-9s -> %s" % (label, new.decode()))


if __name__ == "__main__":
    main()
