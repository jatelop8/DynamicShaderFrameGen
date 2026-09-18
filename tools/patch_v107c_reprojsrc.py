#!/usr/bin/env python3
"""
v1.07c -- the reprojection inverse was taken from the WRONG camera.

One-line defect, plus the instrument that makes it self-evident next run.

  Streamline.cpp:1073   sl::matrixFullInvert(invCurrViewProj, curForReproj);

`curForReproj` is the engine's own ViewProj. The comment 50 lines above it
(same file) records that it "carries NO translation": the engine builds
Proj @ [R|0], with the eye term dropped. `prevForReproj`, on the other hand,
is camPrevVP or s_prevVP, both produced by rebuildViewProj(), which folds the
eye in as -R@eye. Inverting one and multiplying by the other cannot cancel:

    inv( Proj @ [R|0] ) @ ( Proj @ [R|-R@eye] )
      = [R^T|0] @ Proj^-1 @ Proj @ [R|-R@eye]
      = [R^T R | -R^T R @ eye]   =   [ I | -eye ]

Rotation-correct -- det3() reads only the 3x3, so it reports exactly 1.000000
and every existing guard passes -- and translation-absurd: the whole eye
position, in clip space.

Evidence, 23:10 run, DLSSG-Transfusion.log, frame 578:

    clipToPrev=non-identity
    clipToPrev rows=[...][...][...][-243.962387 2.7390945 -77.6724777 -195.222366]
    cameraPos=(-243.049301,-415.311523,118.558205)

row3[3] == -195.222366, not 1: the matrix is not even affine. And the same
run's heartbeat alternated between clipDev=0.000023 and clipDev=28.772085,
because camCurOk flips from frame to frame: some frames take the rebuilt path
(a non-identity result) and some fall back (identity). DLSS-G was told, frame
by frame, "perfectly still" then "displaced by 244 units". That alternation is
the back-and-forth the picture shows, and it is why raising the frame rate
only makes the cycle faster and look more like a freeze.

Edits (6, across 2 files):
  1. Streamline.cpp  1073  invert source -> camCurOk ? camCurVP : curForReproj
  2. Streamline.cpp  1169  record diag.clipW; warn once per 20 if it leaves 1
  3. Streamline.h     164  add float clipW = 1.0f
  4. Streamline.cpp  1321  heartbeat format gains clipW={:.6f}
  5. Streamline.cpp  1342  heartbeat argument list gains diag.clipW (the
                           argument order must mirror the specifier order in
                           the format string; fmt checks this at compile time)
  6. Streamline.cpp  1385  banner v1.07b -> v1.07c

Dry run by default; --apply writes. Every anchor must occur exactly once.
"""

import io
import sys

EOL = b"\r\n"
SRC = "src/Streamline.cpp"
HDR = "src/Streamline.h"

# ---------------------------------------------------------------- edit 1
CPP_INVERT_OLD = (
    "\t\t\tsl::matrixFullInvert(invCurrViewProj, curForReproj);"
)
CPP_INVERT_NEW = (
    "\t\t\t// v1.07c: the inverse MUST come from the same camera as `prev`.\n"
    "\t\t\t//\n"
    "\t\t\t// prevForReproj is camPrevVP or s_prevVP; both come out of\n"
    "\t\t\t// rebuildViewProj, which folds the eye in as -R@eye. curForReproj is\n"
    "\t\t\t// the engine's own ViewProj and -- per the note further up -- carries\n"
    "\t\t\t// NO translation. Inverting one and multiplying by the other cannot\n"
    "\t\t\t// cancel:\n"
    "\t\t\t//\n"
    "\t\t\t//   inv(Proj @ [R|0]) @ (Proj @ [R|-R@eye])\n"
    "\t\t\t//     = [R^T|0] @ Proj^-1 @ Proj @ [R|-R@eye]\n"
    "\t\t\t//     = [R^T R | -R^T R @ eye] = [I | -eye]\n"
    "\t\t\t//\n"
    "\t\t\t// Rotation-correct (det3() reads only the 3x3, so it still reports\n"
    "\t\t\t// 1.000000 and every guard below passes) and translation-absurd.\n"
    "\t\t\t//\n"
    "\t\t\t// 23:10 run, Transfusion [MOTION] dump, frame 578:\n"
    "\t\t\t//   clipToPrev rows=[...][...][...]\n"
    "\t\t\t//                   [-243.962387 2.7390945 -77.6724777 -195.222366]\n"
    "\t\t\t//   cameraPos=(-243.049301,-415.311523,118.558205)\n"
    "\t\t\t// row3[3] is -195, not 1: not even affine. The heartbeat alternated\n"
    "\t\t\t// between that and clipDev=0.000023 because camCurOk flips, so DLSS-G\n"
    "\t\t\t// was told \"still\" then \"moved 244 units\", frame by frame. That is\n"
    "\t\t\t// the back-and-forth the picture shows.\n"
    "\t\t\tconst sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;\n"
    "\t\t\tsl::matrixFullInvert(invCurrViewProj, reprojInvSrc);"
)

# ---------------------------------------------------------------- edit 2
CPP_W_OLD = (
    "\t\t\tif (d > diag.clipDevMax) diag.clipDevMax = d;\n"
    "\t\t}\n"
    "\t\tif (curOk) ++diag.camValid; else ++diag.camInvalid;"
)
CPP_W_NEW = (
    "\t\t\tif (d > diag.clipDevMax) diag.clipDevMax = d;\n"
    "\t\t}\n"
    "\t\t// v1.07c: a reprojection matrix that maps clip space to clip space is\n"
    "\t\t// affine, so its last row is (tx,ty,tz,1) and [3].w is exactly 1. This\n"
    "\t\t// is the one criterion here that does NOT grow with frame time, which\n"
    "\t\t// matters: clipDev legitimately rises with both camera speed and frame\n"
    "\t\t// interval, so a large clipDev alone proves nothing. A w away from 1\n"
    "\t\t// means the inverse and the `prev` matrix were built from different\n"
    "\t\t// cameras -- the defect fixed at the invert site above.\n"
    "\t\tdiag.clipW = c.clipToPrevClip[3].w;\n"
    "\t\t{\n"
    "\t\t\tconst float wDev = diag.clipW > 1.0f ? (diag.clipW - 1.0f)\n"
    "\t\t\t                                     : (1.0f - diag.clipW);\n"
    "\t\t\tstatic std::uint32_t wWarned = 0;\n"
    "\t\t\tif (wDev > 0.01f && wWarned < 20u) {\n"
    "\t\t\t\t++wWarned;\n"
    "\t\t\t\tSKSE::log::warn(\"[MOTION] clipToPrevClip[3].w={:.6f} (must be 1) - \"\n"
    "\t\t\t\t\t\"the inverse and the previous matrix came from different \"\n"
    "\t\t\t\t\t\"cameras; DLSS-G is reprojecting with a non-affine matrix\",\n"
    "\t\t\t\t\tdiag.clipW);\n"
    "\t\t\t}\n"
    "\t\t}\n"
    "\t\tif (curOk) ++diag.camValid; else ++diag.camInvalid;"
)

# ---------------------------------------------------------------- edit 3
HDR_OLD = "\t\t\tfloat clipDevMax = 0.0f;"
HDR_NEW = (
    "\t\t\tfloat clipDevMax = 0.0f;\n"
    "\t\t\t// v1.07c: clipToPrevClip[3].w of the last frame. Must be 1.000000 for\n"
    "\t\t\t// an affine reprojection matrix; anything else means the inverse and\n"
    "\t\t\t// the previous matrix did not come from the same camera. Unlike\n"
    "\t\t\t// clipDevMax this one is absolute -- it does not grow with frame time.\n"
    "\t\t\tfloat clipW = 1.0f;"
)

# ---------------------------------------------------------------- edit 4
FMT_OLD = '"clipDev={:.6f} curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) "'
FMT_NEW = '"clipDev={:.6f} clipW={:.6f} curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) "'

# ---------------------------------------------------------------- edit 5
# fmt validates the format string against the argument list AT COMPILE TIME
# (consteval), so the argument has to sit where the specifier sits. The
# heartbeat puts clipDev={:.6f} in the jitter line, so diag.clipW goes right
# after `clipDev` there -- NOT after diag.clipDevMax, which belongs to a
# specifier further down the format string. Getting this wrong produces
# C7595 "call to immediate function is not a constant expression".
ARG_OLD = "\t\t\t\t\tGet().jitterX, Get().jitterY, clipDev, devOf(curVP), devOf(prevVP),"
ARG_NEW = "\t\t\t\t\tGet().jitterX, Get().jitterY, clipDev, diag.clipW, devOf(curVP), devOf(prevVP),"

# ---------------------------------------------------------------- edit 6
BAN_OLD = "diag active v1.07b (compiled "
BAN_NEW = "diag active v1.07c (compiled "

EDITS = [
    ("1  invert source",          SRC, CPP_INVERT_OLD, CPP_INVERT_NEW),
    ("2  clipW + warning",        SRC, CPP_W_OLD,      CPP_W_NEW),
    ("3  diag.clipW field",       HDR, HDR_OLD,        HDR_NEW),
    ("4  heartbeat format",       SRC, FMT_OLD,        FMT_NEW),
    ("5  heartbeat argument",     SRC, ARG_OLD,        ARG_NEW),
    ("6  banner v1.07c",          SRC, BAN_OLD,        BAN_NEW),
]

POST = [
    (SRC, "reprojInvSrc defined",      "const sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;"),
    (SRC, "invert uses the source",    "sl::matrixFullInvert(invCurrViewProj, reprojInvSrc);"),
    (SRC, "old invert gone",           None),
    (SRC, "clipW assigned",            "diag.clipW = c.clipToPrevClip[3].w;"),
    (SRC, "clipW warning present",     "[MOTION] clipToPrevClip[3].w="),
    (SRC, "format has clipW",          "clipDev={:.6f} clipW={:.6f}"),
    # NB: write \n here, never \r\n -- norm() expands \n to the file's EOL and
    # would turn a literal \r\n into \r\r\n, which can never match.
    (SRC, "argument list has clipW",   "clipDev, diag.clipW, devOf(curVP)"),
    (SRC, "banner is v1.07c",          "diag active v1.07c (compiled "),
    (HDR, "clipW field declared",      "float clipW = 1.0f;"),
]


def read(path):
    return io.open(path, "rb").read()


def decode(path, raw):
    return raw.decode("utf-8-sig")


def encode(text):
    return text.encode("utf-8-sig")


def eol_of(raw):
    crlf = raw.count(b"\r\n")
    lf = raw.count(b"\n") - crlf
    return b"\r\n" if crlf >= lf else b"\n"


def norm(chunk, eol):
    return chunk.replace("\n", eol.decode("ascii"))


def main(apply_changes):
    files = {}
    raw = {}
    eols = {}
    for p in (SRC, HDR):
        raw[p] = read(p)
        eols[p] = eol_of(raw[p])
        files[p] = decode(p, raw[p])
        print(f"{p:22s} {len(raw[p]):8d} B  eol={'CRLF' if eols[p] == EOL else 'LF'}")

    print()
    # idempotence guard: the fix consumes its own anchor, so a re-run finds
    # count==0; this extra marker check turns that into a clear refusal.
    if "reprojInvSrc" in files[SRC]:
        print("REFUSED, nothing written: 'reprojInvSrc' already present "
              "- this patch has already run")
        return 2

    err = 0
    for label, path, old, new in EDITS:
        eol = eols[path].decode("ascii")
        o = norm(old, eols[path])
        n = norm(new, eols[path])
        count = files[path].count(o)
        print(f"{label:26s} count(old)={count}   (must be exactly 1)")
        if count != 1:
            print(f"  !! REFUSED: anchor not unique in {path}")
            err = 1
        files[path] = files[path].replace(o, n, 1)
    if err:
        print("\nREFUSED, nothing written")
        return 1

    print()
    print("--- post-conditions (checked on the RESULT text) ---")
    bad = 0
    for path, label, needle in POST:
        if needle is None:
            ok = "sl::matrixFullInvert(invCurrViewProj, curForReproj);" not in files[path]
        else:
            ok = norm(needle, eols[path]) in files[path]
        print(f"  {'OK  ' if ok else 'FAIL'} {path:20s} {label}")
        if not ok:
            bad = 1
    if bad:
        print("\nREFUSED, nothing written (post-condition failed)")
        return 1

    for p in (SRC, HDR):
        before = raw[p].count(b"\n")
        after = files[p].count("\n")
        print(f"  {p:20s} lines {before} -> {after}")

    if not apply_changes:
        print("\nDRY RUN - nothing written. Re-run with --apply to write.")
        return 0

    for p in (SRC, HDR):
        with io.open(p, "wb") as fh:
            fh.write(encode(files[p]))
    print("\nWROTE both files.")
    for p in (SRC, HDR):
        r = read(p)
        crlf = r.count(b"\r\n")
        lf = r.count(b"\n") - crlf
        print(f"  {p:20s} {len(r):8d} B  CRLF={crlf} bare_LF={lf}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
