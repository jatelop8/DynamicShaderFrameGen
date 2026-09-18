#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_v087_rawdump.py -- v0.87: dump the RAW perFrame bytes to settle the layout
question once and for all.

WHY THIS PATCH EXISTS
---------------------
Ten rounds of fixes have all operated on the *gates* (which arrival to accept),
while assuming that `b.CameraViewProjUnjittered` actually lands on the engine's
viewProjUnjittered. That assumption has NEVER been tested.

The evidence that it may be FALSE:
  * FIX_RESET_2123.md (2026-09-17 21:23) already raised it as hypothesis (a):
      "dev(curVP)~0 and dev(viewProj)!=0  =>  c24/c32 not written by the engine
       (wrong offset / field does not exist)"
    It was never actually checked. Ten rounds went by.
  * The dumped matrices are self-inconsistent. From the 14:20 log:

      [CAM] raw #1 ViewProjUnj | -6.70312 0 0 0 | 0 -1.57495 11.8121 0 |
                                 0 -0.991954 -0.132261 -15.011 | 0 -0.991228 -0.132164 0
      [CAM] raw #1 ViewInv     | -1 -0 -0 -0 | -0 -0.132164 -0.991228 0 |
                                 -0 0.991228 -0.132164 -0 | 0 -0 0 1

    The numbers -0.132164 / -0.991228 appear in BOTH, in different positions.
    Reading the same underlying values at two different field offsets is the
    signature of a stride mismatch, not of two independent matrices.

  * The struct comments imply 8 c-registers (128 B) per Matrix (c0,c8,c16,...,
    c72) but sizeof(Matrix) == 64 B == 4 c-registers. So either (i) the engine
    really uses a 128-byte stride and our struct is packed wrongly, or (ii) the
    comments are simply wrong. Both cannot be checked on paper; each has a
    counter-example in the log. The only way out is to look at the bytes.

WHAT THIS PATCH DOES (diagnostics ONLY -- no gate, no verdict)
-------------------------------------------------------------
Inside DumpCameraSnapshot, additionally emit the raw float stream starting at
the FrameBuffer base, so the layout can be reconstructed offline:

  [RAW] base+0    f00 f01 f02 f03 | f10 f11 f12 f13 | ...
  [RAW] stride4   i.e. interpretation A: matrices packed at 64 B
  [RAW] stride8   interpretation B: matrices packed at 128 B

Concretely we print 96 floats (0x180 bytes) from the base pointer, 8 per line,
each line prefixed with its byte offset. From that dump we can:

  1. locate every 4x4 block whose row3 == (0,0,0,1)   -> a real matrix
  2. measure the distance between consecutive such blocks -> the true stride
  3. identify which field offset the engine actually writes

It prints once per DumpCameraSnapshot call (already throttled to <=80 per run).

USAGE
-----
  python tools/add_v087_rawdump.py                 # dry run, prints plan
  python tools/add_v087_rawdump.py --apply         # write source

Mirrors add_v086_homog_guard.py: unique-anchor assertion, brace balance,
line-ending check, dry-run by default.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPP = os.path.join(ROOT, "src", "FrameGen.cpp")

# --- anchors -----------------------------------------------------------------

ANCHOR_DUMP_TAIL = (
    "\t\t\t\tcamDev(b.CameraViewProjUnjittered), camDet3(b.CameraViewProjUnjittered),\n"
    "\t\t\t\tcamDet3(b.CameraProjUnjittered), camMag(b.CameraViewProjUnjittered));\n"
    "\t\t}\n"
)

NEW_DUMP_TAIL = (
    "\t\t\t\tcamDev(b.CameraViewProjUnjittered), camDet3(b.CameraViewProjUnjittered),\n"
    "\t\t\t\tcamDet3(b.CameraProjUnjittered), camMag(b.CameraViewProjUnjittered));\n"
    "\n"
    "\t\t\t// ---- v0.87: raw byte dump (diagnostic only) -------------------\n"
    "\t\t\t// Emit the raw float stream from the FrameBuffer base so the true\n"
    "\t\t\t// layout can be measured offline. Rationale in\n"
    "\t\t\t// tools/add_v087_rawdump.py: the dumped matrices contradict each\n"
    "\t\t\t// other. In the 14:20 log, block #1 has a ProjUnj whose fourth row\n"
    "\t\t\t// is (0, 0, -0.0666178, 0.0666667) -- a textbook perspective\n"
    "\t\t\t// projection -- and a ViewInv that is a clean rotation, yet its\n"
    "\t\t\t// ViewProjUnj fourth row is (0, -0.991228, -0.132164, 0), which is\n"
    "\t\t\t// ViewInv data. View x Proj cannot have that fourth row. Either the\n"
    "\t\t\t// field offsets are wrong or the struct stride is wrong; both make\n"
    "\t\t\t// every offset wrong at once, so no gate can fix it.\n"
    "\t\t\t//\n"
    "\t\t\t// Bounds: sizeof(FrameBuffer) is 672 B. Dump exactly that much so the\n"
    "\t\t\t// read can never leave the mapped region (a_src points at the live\n"
    "\t\t\t// D3D11 mapping; a longer read could touch an unmapped page).\n"
    "\t\t\t{\n"
    "\t\t\t\tconstexpr int kFloatCount =\n"
    "\t\t\t\t\tstatic_cast<int>(sizeof(FrameBuffer) / sizeof(float));   // 168\n"
    "\t\t\t\tconst float* raw = reinterpret_cast<const float*>(&b);\n"
    "\t\t\t\tfor (int off = 0; off < kFloatCount; off += 8) {\n"
    "\t\t\t\t\tSKSE::log::info(\"[RAW] +{:#06x} | {:.7g} {:.7g} {:.7g} {:.7g} | {:.7g} {:.7g} {:.7g} {:.7g}\",\n"
    "\t\t\t\t\t\toff * 4,\n"
    "\t\t\t\t\t\traw[off + 0], raw[off + 1], raw[off + 2], raw[off + 3],\n"
    "\t\t\t\t\t\traw[off + 4], raw[off + 5], raw[off + 6], raw[off + 7]);\n"
    "\t\t\t\t}\n"
    "\t\t\t}\n"
    "\t\t}\n"
)

EDITS = [
    (
        "raw-dump inside DumpCameraSnapshot",
        ANCHOR_DUMP_TAIL,
        NEW_DUMP_TAIL,
    ),
]

MARKERS = ["[RAW] +{:#06x} |"]


def read_bytes(p):
    with open(p, "rb") as fh:
        return fh.read()


def count_eol(data):
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n")
    return crlf, lf - crlf


def check_braces(text, label):
    depth = 0
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return "neg at %d" % i
    return "ok (final depth %d)" % depth


def main():
    apply = "--apply" in sys.argv
    data = read_bytes(CPP)
    text = data.decode("utf-8")
    crlf, lf = count_eol(data)

    print("=" * 78)
    print("v0.87 raw-dump probe -- %s" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 78)
    print("file   : %s" % CPP)
    print("bytes  : %d" % len(data))
    print("eol    : crlf=%d lf=%d" % (crlf, lf))
    print("expect : crlf=0 lf>0 (FrameGen.cpp is LF)")
    if crlf != 0:
        print("!! unexpected CRLF -- abort")
        return 2
    print()

    # marker guard: refuse if the probe is already in
    for m in MARKERS:
        if m in text:
            print("REFUSED: marker already present: %r" % m)
            print("(the probe has already been applied -- nothing written)")
            return 1

    new_text = text
    for label, old, new in EDITS:
        n = new_text.count(old)
        print("-" * 78)
        print("edit   : %s" % label)
        print("anchor : occurrences=%d %s" % (n, "OK" if n == 1 else "FAIL"))
        if n != 1:
            print("REFUSED, nothing written")
            return 2
        new_text = new_text.replace(old, new, 1)

    print("-" * 78)
    print("brace check (new text): %s" % check_braces(new_text, "cpp"))
    print("delta bytes           : %+d" % (len(new_text) - len(text)))
    print()

    if not apply:
        print("DRY RUN complete. Re-run with --apply to write.")
        return 0

    # write back, preserving LF
    with open(CPP, "wb") as fh:
        fh.write(new_text.encode("utf-8"))
    print("WROTE %s" % CPP)

    # independent read-back
    back = read_bytes(CPP)
    bcrlf, blf = count_eol(back)
    print("read-back: bytes=%d crlf=%d lf=%d" % (len(back), bcrlf, blf))
    for m in MARKERS:
        print("read-back marker %r : %s" % (m, "PRESENT" if m in back.decode("utf-8") else "MISSING"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
