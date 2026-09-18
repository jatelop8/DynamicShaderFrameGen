#!/usr/bin/env python3
"""
v0.78 INI patch: drop the MFG ceiling because the unlocker is gone.

WHY
---
DynamicShaderFrameGen.ini itself says (lines 72-80):
    "raising the ceiling only changes what is REQUESTED. The frame generation
     kernels for Ada/Ampere/Turing are not in nvngx_dlssg.dll, so you also need
     an external kernel unlocker ... Without such an unlocker a high multiplier
     has no kernel to run and the result is a black screen or a hang."

The runtime log confirmed it:
    runtimeReportsMax = 2x   (Ada)
    INI request       = 4x
    => eErrorInvalidState (38)

DLSSG-Transfusion was moved out this session (_removed_transfusion_...).
So the ceiling must go back to the hardware truth.

   MFGMaxFramesOverride   3 -> 0   (0 = follow the hardware report exactly)
   DLSSGFramesToGenerate  3 -> 1   (1 = 2x, the only kernel Ada actually has)

FILES
-----
Both copies are patched, and they are kept byte-identical:
  SKSE/Plugins/DynamicShaderFrameGen.ini                    (authoritative: the
      POST_BUILD step copies this over the mod folder - see the note in the INI
      itself at "the build's POST_BUILD step copies THIS file over the one in
      the mod folder")
  E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini
      (deployed; rebuilt from the source on every build)

Line endings are preserved (the file is LF).

SAFETY
------
Dry run by default. Pass --apply to write.
Every anchor must appear EXACTLY once, and the file must not already carry the
marker, or the script refuses and writes nothing.
A timestamped .bak-YYYYMMDD-HHMMSS is made before any write.
"""

import datetime
import hashlib
import os
import shutil
import sys

SRC = "SKSE/Plugins/DynamicShaderFrameGen.ini"
DST = "E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini"

# The two edits. Anchors are the FULL line (value included) so a half-applied
# file cannot match.
EDITS = [
    ("mfg ceiling",
     "MFGMaxFramesOverride=3\n",
     "MFGMaxFramesOverride=0\n"),
    ("frames to generate",
     "DLSSGFramesToGenerate=3\n",
     "DLSSGFramesToGenerate=1\n"),
]

# Idempotency guard: if this text is present the patch already ran.
MARKERS = [
    "; ---- v0.78 ----",
]

# Canaries: strings that must still be present after patching (proves we did not
# clobber the file).
CANARIES = [
    "Enable=1\n",
    "Provider=1\n",
    "MenuDisableFrameGen=1\n",
    "MvecScaleOverride=1.00\n",
    "ReflexFpsLimit=0\n",
    "MFGMaxFramesOverride=0\n",
    "DLSSGFramesToGenerate=1\n",
]

NOTE = """\
; ---- v0.78 ----
; MFG ceiling returned to the hardware truth (owned by Defaults/ENB setup, not
; edited here by hand):
;   MFGMaxFramesOverride   3 -> 0  (0 = follow the hardware report exactly)
;   DLSSGFramesToGenerate  3 -> 1  (1 = 2x; Ada's kernel set stops there)
; Reason: the runtime reports numFramesToGenerateMax=1 (2x) on this GPU, the INI
; was asking for 4x, and the mismatch came back as eErrorInvalidState(38). The
; external kernel unlocker that used to bridge the gap (DLSSG-Transfusion) is no
; longer installed. Without a kernel there is nothing to run at 3x/4x, so the
; request is simply not made any more. Raise these again only AFTER an unlocker
; is back and the log shows "runtimeReportsMax = 4x".
"""


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def resolve(path, s):
    """Adapt LF-anchored text to the file's real line ending."""
    with open(path, "rb") as fh:
        raw = fh.read()
    crlf = b"\r\n" in raw
    if crlf:
        return s.replace("\n", "\r\n")
    return s


def patch(path, apply_it):
    if not os.path.isfile(path):
        print("  !! MISSING: %s" % path)
        return False

    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    before_len = len(raw)
    before_md5 = hashlib.md5(raw).hexdigest()
    crlf = "\r\n" in text

    print("  file      : %s" % path)
    print("  size      : %d bytes   md5 %s" % (before_len, before_md5))
    print("  line end  : %s" % ("CRLF" if crlf else "LF"))

    # ---- idempotency marker check FIRST (anchor uniqueness does not prove the
    # patch has not already run; insertions do not consume their anchor) -------
    for mk in MARKERS:
        if mk in text:
            print("  REFUSED: marker already present (%r) - patch has run" % mk)
            return False

    # ---- anchor uniqueness -------------------------------------------------
    work = text
    for label, old, new in EDITS:
        o = resolve(path, old)
        n = resolve(path, new)
        cnt = work.count(o)
        print("  anchor [%s] found %d time(s)" % (label, cnt))
        if cnt != 1:
            print("  REFUSED: anchor %r is not unique (%d) - nothing written"
                  % (label, cnt))
            return False
        work = work.replace(o, n)

    # ---- canaries ----------------------------------------------------------
    bad = [c for c in CANARIES if resolve(path, c) not in work]
    if bad:
        print("  REFUSED: canary missing after edit: %r" % bad)
        return False
    print("  canaries  : OK (%d)" % len(CANARIES))

    # ---- append the provenance note ----------------------------------------
    if not work.endswith("\n"):
        work += "\r\n" if crlf else "\n"
    work += resolve(path, NOTE)

    after_len = len(work.encode("utf-8"))
    print("  size      : %d -> %d bytes (%+d)" % (before_len, after_len,
                                                  after_len - before_len))

    if not apply_it:
        print("  DRY RUN   : not written")
        return True

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-%s" % (path, stamp)
    shutil.copy2(path, bak)
    print("  backup    : %s" % bak)

    with open(path, "wb") as fh:
        fh.write(work.encode("utf-8"))
    print("  WRITTEN   : md5 %s" % sha(path))
    return True


def main():
    apply_it = "--apply" in sys.argv
    print("=" * 72)
    print("v0.78 INI patch - MFG ceiling  (mode: %s)"
          % ("APPLY" if apply_it else "DRY RUN"))
    print("=" * 72)

    ok = True
    for p in (SRC, DST):
        print("-" * 72)
        ok = patch(p, apply_it) and ok

    print("=" * 72)
    if apply_it and ok:
        # verify the two copies stayed identical
        if os.path.isfile(SRC) and os.path.isfile(DST):
            a, b = sha(SRC), sha(DST)
            print("source md5   : %s" % a)
            print("deployed md5 : %s" % b)
            print("IDENTICAL    : %s" % ("yes" if a == b else "NO"))
            if a != b:
                ok = False
    print("RESULT: %s" % ("OK" if ok else "REFUSED / FAILED"))
    print("=" * 72)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
