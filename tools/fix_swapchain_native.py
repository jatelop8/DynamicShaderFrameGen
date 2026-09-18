"""
fix_swapchain_native.py  --  make the Skyrim swapchain size equal the display mode size.

WHY
---
DLSS-G multi-frame generation presents through the Streamline pacer, whose rhythm
depends on DXGI *independent flip* (direct scanout).  DXGI can only use independent
flip when the swapchain size AND format match the active display mode exactly.

Measured state on this machine (2026-09-17):
    display mode        : 3840x2160 @ 160 Hz   (Win32_VideoController, RTX 4080 SUPER)
    game swapchain      : 2560x1440            (SkyrimPrefs iSize W/H; DFG log color=2560x1440)
    windowed-game opts  : SwapEffectUpgradeEnable=1   (enabled)
    fullscreen-opts off : DISABLEDXMAXIMIZEDWINDOWEDMODE absent (not disabled)

=> mismatch, so DWM scales 1440p up to 4K, the present path falls back to composed
   flip, the pacer loses its rhythm and the picture flickers continuously -- which is
   exactly the wording used in the plugin's own v0.54 INI note:
       "the present queue backs up, the SL pacer loses its rhythm and the picture
        flickers continuously" / "Too low = stutter, too high = flicker"

WHAT THIS CHANGES
-----------------
1. SkyrimPrefs.ini : iSize W 2560 -> 3840 , iSize H 1440 -> 2160
   => output/swapchain becomes the panel's native mode; independent flip becomes legal.

2. DynamicShaderFrameGen.ini : RenderResolutionScale 0 -> 0.44
   This does NOT affect the swapchain size; it only keeps the *internal* render
   resolution unchanged so the performance is not lost:
       before : 2560x1440 output x QualityMode(0.6667) = 1707x960 internal
       after  : 3840x2160 output x 0.44              = 1690x950 internal
   Same pixel count, but the final 1440p->4K DWM bilinear stretch is replaced by a
   single DLSS upscale to native 4K (strictly better image).

Both files are patched (the repo copy and the deployed copy) because the CMake
POST_BUILD step copies the repo INI over the deployed one.

USAGE
    python fix_swapchain_native.py            # dry run, prints the plan, writes nothing
    python fix_swapchain_native.py --apply    # back up, patch, verify, write

Guards: idempotency marker first, then anchor uniqueness (count == 1), then
post-conditions, then line-ending preservation. Any failure => REFUSED, nothing written.
"""

import hashlib
import os
import shutil
import sys
import time

APPLY = "--apply" in sys.argv

BACKUP_ROOT = r"D:\workbuddy2\backup"

SKYRIM_PREFS = r"C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SkyrimPrefs.ini"
DFG_INI_DEPLOY = r"E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini"
DFG_INI_REPO = r"D:\Modding\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.ini"

# (label, old, new). Anchors are matched with the file's own line ending.
SKYRIM_EDITS = [
    ("iSize W", b"iSize W=2560", b"iSize W=3840"),
    ("iSize H", b"iSize H=1440", b"iSize H=2160"),
]

DFG_EDITS = [
    # The anchor carries a leading AND a trailing line break. Two separate reasons:
    #
    #  1. UNIQUENESS: the bare string "RenderResolutionScale=0" also occurs inside a
    #     NOTE comment ("(or QualityMode, when RenderResolutionScale=0)."), so a
    #     line-start-only anchor is required to make the setting line the sole match.
    #
    #  2. DISJOINTNESS: with a leading break only, the NEW string still CONTAINS the
    #     OLD string as a prefix ("\nRenderResolutionScale=0.44" begins with
    #     "\nRenderResolutionScale=0"), so the post-condition count(old)==n_old-1 can
    #     NEVER hold and the patch is refused. Anchoring the trailing break as well
    #     makes old and new disjoint and the check meaningful.
    #
    # Both patterns are written with plain "\n" only; plan_file() rewrites every "\n"
    # to the file's own EOL, so a CRLF file gets CRLF on both ends.
    ("RenderResolutionScale", b"\nRenderResolutionScale=0\n", b"\nRenderResolutionScale=0.44\n"),
]


def md5(b):
    return hashlib.md5(b).hexdigest()


def detect_eol(raw):
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    return b"\r\n" if crlf >= lf else b"\n"


def plan_file(path, edits, label):
    print("=" * 74)
    print("[%s]" % label)
    print("  file : %s" % path)
    if not os.path.isfile(path):
        return None, "MISSING FILE"
    with open(path, "rb") as fh:
        src = fh.read()
    eol = detect_eol(src)
    print("  size : %d bytes   md5=%s   eol=%s" % (len(src), md5(src), repr(eol)))
    out = src
    ok = True
    for name, old_b, new_b in edits:
        old = old_b.replace(b"\n", eol)
        new = new_b.replace(b"\n", eol)
        n_old = out.count(old)
        n_new = out.count(new)
        if n_old == 0 and n_new >= 1:
            print("  [%s] ALREADY APPLIED (%r present %d time(s))" % (name, new.decode("latin-1").strip(), n_new))
            continue
        if n_old != 1:
            print("  [%s] REFUSED: anchor %r found %d times (expected exactly 1)"
                  % (name, old.decode("latin-1").strip(), n_old))
            ok = False
            continue
        cand = out.replace(old, new, 1)
        if cand.count(new) != n_new + 1 or cand.count(old) != n_old - 1:
            print("  [%s] REFUSED: post-condition failed" % name)
            ok = False
            continue
        print("  [%s] %s -> %s   (delta %+d bytes)"
              % (name, old.decode("latin-1").strip(), new.decode("latin-1").strip(), len(new) - len(old)))
        out = cand
    if not ok:
        return None, "REFUSED (see above)"
    if out == src:
        return None, "nothing to do"
    # structural check: line count and section layout unchanged
    if out.count(eol) != src.count(eol):
        return None, "REFUSED: line count changed %d -> %d" % (src.count(eol), out.count(eol))
    if detect_eol(out) != eol:
        return None, "REFUSED: line ending changed"
    print("  new size: %d bytes   (line count %d unchanged)" % (len(out), out.count(eol)))
    return out, "OK"


def main():
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(BACKUP_ROOT, "swapchain_native_%s" % stamp)
    jobs = [
        (SKYRIM_PREFS, SKYRIM_EDITS, "SkyrimPrefs.ini (output resolution)"),
        (DFG_INI_DEPLOY, DFG_EDITS, "DFG INI (deployed)"),
        (DFG_INI_REPO, DFG_EDITS, "DFG INI (repo source)"),
    ]

    planned = []
    for path, edits, label in jobs:
        out, status = plan_file(path, edits, label)
        planned.append((path, out, status, label))
        print("  status : %s" % status)

    hard_fail = [p for p in planned if p[2] is not None and p[2] not in ("OK", "nothing to do")]
    if hard_fail:
        print()
        print("REFUSED, nothing written. Failing files:")
        for p, _, s, l in hard_fail:
            print("  - %s : %s" % (l, s))
        return 1

    todo = [p for p in planned if p[2] == "OK"]
    if not todo:
        print()
        print("Nothing to do - all targets already patched.")
        return 0

    print()
    if not APPLY:
        print("DRY RUN - nothing written. Re-run with --apply to write.")
        return 0

    os.makedirs(backup_dir, exist_ok=True)
    for path, out, status, label in todo:
        with open(path, "rb") as fh:
            orig = fh.read()
        base = os.path.basename(path)
        bak = os.path.join(backup_dir, base + ".bak")
        shutil.copy2(path, bak)
        assert md5(open(bak, "rb").read()) == md5(orig), "backup verification failed"
        tmp = path + ".tmp_new"
        with open(tmp, "wb") as fh:
            fh.write(out)
        os.replace(tmp, path)
        with open(path, "rb") as fh:
            back = fh.read()
        assert back == out, "read-back mismatch for %s" % path
        assert md5(back) == md5(out), "read-back md5 mismatch for %s" % path
        print("WROTE %s  (md5 %s -> %s)" % (path, md5(orig), md5(back)))

    print()
    print("BACKUP DIR: %s" % backup_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
