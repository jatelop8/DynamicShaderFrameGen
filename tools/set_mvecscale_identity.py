#!/usr/bin/env python3
"""
set_mvecscale_identity.py - MvecScaleOverride: 0.00 -> 1.00

WHY.  Native motion vectors in this engine are already normalised: they are
reported as displacement / screen width, so a full-screen pan already reaches
1.0, i.e. the values are already inside [-1,1].

  sl_consts.h / NVIDIA guide  : "values in [-1,1] -> scale factor should be {1,1}"
  open-shaders (Skyrim, works) : "The standard full-frame DLSS path ... must keep
                                mvecScale at identity or DLSS MASSIVELY
                                over-estimates motion."

The legacy value in use is 1/renderScale.  With QualityMode=1 the render scale
is 0.6667, so mvecScale = {1.5, 1.5} and every motion vector handed to DLSS-G is
50% too large.  Generated frames are therefore placed with 1.5x the true
displacement; alternating them with real frames produces continuous judder /
flicker.  The runtime log confirms the effective value:

    [Streamline] mvecScale = { 1.5000, 1.5000 } (renderScale=0.6667 override=0.00)

This is not a rollback: multiplier stays 4x, blackwellTransfusion and every
other setting are untouched.  Only the normalisation factor handed to DLSS-G
changes, from a 50% over-estimate to the documented identity.

BOTH copies are patched because CMakeLists.txt POST_BUILD does
copy_if_different(${CMAKE_SOURCE_DIR}/SKSE/Plugins/...ini -> PLUGIN_DEPLOY_DIR).
Patching only the deployed copy would be silently undone by the next rebuild.

Guards, per project rules:
  - dry-run by default, --apply writes
  - per file: anchor uniqueness (count == 1)
  - idempotency checked BEFORE the anchor check
  - binary read/write so line endings and any non-ASCII comments survive
  - timestamped backup of every file written
"""
import os
import shutil
import sys
import datetime

SRC_INI = r"D:\Modding\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini"
DEPLOY_INI = r"E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini"
TARGETS = [SRC_INI, DEPLOY_INI]

BACKUP_ROOT = r"D:\workbuddy2\backup"

OLD = b"MvecScaleOverride=0.00"
NEW = b"MvecScaleOverride=1.00"


def fail(msg):
    print("REFUSED: %s" % msg)
    raise SystemExit(1)


def main():
    apply = "--apply" in sys.argv
    plans = []

    for path in TARGETS:
        if not os.path.isfile(path):
            fail("target not found: %s" % path)
        with open(path, "rb") as fh:
            src = fh.read()

        # ---- guard 1: idempotency (BEFORE anchor check) ---------------------
        if NEW in src and OLD not in src:
            print("skip (already 1.00): %s" % path)
            continue

        # ---- guard 2: anchor uniqueness -------------------------------------
        n = src.count(OLD)
        if n != 1:
            fail("%s: anchor %r found %d times (expected exactly 1)"
                 % (path, OLD.decode(), n))

        out = src.replace(OLD, NEW)

        # ---- post-conditions ------------------------------------------------
        if out.count(OLD) != 0:
            fail("%s: post: old value still present" % path)
        if out.count(NEW) != 1:
            fail("%s: post: new value not exactly once" % path)
        if len(out) != len(src):
            fail("%s: post: size drift %d -> %d" % (path, len(src), len(out)))

        plans.append((path, src, out))
        print("plan: %s" % path)
        print("      %s  ->  %s   (len %d, unchanged)" % (OLD.decode(), NEW.decode(), len(src)))

    if not plans:
        fail("nothing to patch on any target")

    print("")
    print("effect            : DLSS-G mvec normalisation 1.5x over-estimate -> identity")
    print("multiplier        : unchanged (4x) - NOT a rollback")
    print("other settings    : unchanged")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply to write.")
        return

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = os.path.join(BACKUP_ROOT, "dfg_mvecscale_%s" % ts)
    os.makedirs(bdir, exist_ok=True)
    print("\nbackup dir        : %s" % bdir)

    for path, src, out in plans:
        tag = "src" if path == SRC_INI else "deploy"
        bak = os.path.join(bdir, "DynamicShaderFrameGen.ini.%s.bak" % tag)
        shutil.copy2(path, bak)
        with open(path, "wb") as fh:
            fh.write(out)
        with open(path, "rb") as fh:
            chk = fh.read()
        if chk != out:
            fail("%s: read-back mismatch" % path)
        print("wrote + verified  : %s" % path)
        print("   backup         : %s" % bak)

    print("APPLIED")


if __name__ == "__main__":
    main()
