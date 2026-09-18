#!/usr/bin/env python3
"""
v1.06 patch -- two independent defects, both confirmed from disk evidence.

DEFECT 1 (the freeze): the Reflex render cap lost its divisor.

  v0.54 (79a0ea4) derived this line from the over-submit it was fixing and
  proved it in game:

      const double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;
                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  v0.54's own comment: "160Hz / 4x -> 39fps render -> 156 present fps, just
  under the panel". That is the invariant: render_fps * multiplier <= refresh.

  Every committed revision up to 2a2b592 (09-17 17:18) carries the divisor.
  The v1.00 source backup (09-18 17:56) does not:

      const double want = Get().refreshRate - 1.0;

  Measured consequence, 21:27 session on this 160Hz panel:

      capFps = 159  =>  render 159fps  x4  =  636 present fps vs a 160Hz panel

  The present queue backs up, the SL pacer loses its cadence, and the picture
  stops advancing while the frame counter keeps climbing. That is exactly
  "freezing the moment 4x starts, with the fps readout still alive".

DEFECT 2 (dead history): the v1.02c camera history had a reader and no writer.

  Streamline.cpp declares, immediately above the reader:

      static Matrix s_prevCamView{};
      static Matrix s_prevCamProj{};
      static float  s_prevCamEye[3] = {0,0,0};
      static bool   s_hasPrevCam = false;

  and then only ever READS them:

      if (camCurOk && s_hasPrevCam) {
          camPrevOk = rebuildViewProj(s_prevCamView, s_prevCamEye, s_prevCamProj, camPrevVP) ...
      }

  Nothing writes s_prevCamView / s_prevCamProj / s_prevCamEye and nothing sets
  s_hasPrevCam = true. camPrevOk is therefore false on every frame of every
  run, and the 21:27 heartbeat confirms it: camPrev(ok/used)=0/0, on a run
  where cam(ok/inv)=121/0 was healthy. The rebuild was never reachable.

Both edits are pure text substitutions with count==1 assertions. Dry run by
default; pass --apply to write.
"""

import sys

SRC = r"D:\Modding\DynamicShaderFrameGen\src\Streamline.cpp"

EDITS = []

# --------------------------------------------------------------------------
# EDIT 1 -- restore the divisor
# --------------------------------------------------------------------------
EDITS.append((
    "capfps-restore-divisor",

    b"\t\t\t\tconst double want = Get().refreshRate - 1.0;\r\n"
    b"\t\t\t\tcapFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);\r\n",

    b"\t\t\t\t// v1.06: the divisor is the whole point of this line, and it was\r\n"
    b"\t\t\t\t// lost. v0.54 (79a0ea4) derived the formula from the over-submit\r\n"
    b"\t\t\t\t// it was fixing and stated the invariant in its own comment:\r\n"
    b"\t\t\t\t//\r\n"
    b"\t\t\t\t//     \"160Hz / 4x -> 39fps render -> 156 present fps,\r\n"
    b"\t\t\t\t//      just under the panel\"\r\n"
    b"\t\t\t\t//\r\n"
    b"\t\t\t\t// Every commit up to 2a2b592 carries /capMult. The v1.00 source\r\n"
    b"\t\t\t\t// backup (09-18 17:56) does not, and neither did any run since.\r\n"
    b"\t\t\t\t// With capFps = refreshRate - 1 = 159 on this 160Hz panel, 4x\r\n"
    b"\t\t\t\t// presents 636 fps, the present queue backs up, the SL pacer\r\n"
    b"\t\t\t\t// loses cadence, and the picture stops advancing while the frame\r\n"
    b"\t\t\t\t// counter keeps climbing - the 21:27 freeze.\r\n"
    b"\t\t\t\tconst double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;\r\n"
    b"\t\t\t\tcapFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);\r\n"
    b"\t\t\t\t// v1.06: state the invariant as an assertion, so a future edit to\r\n"
    b"\t\t\t\t// either term cannot silently re-introduce the over-submit.\r\n"
    b"\t\t\t\tif (capFps * capMult > Get().refreshRate)\r\n"
    b"\t\t\t\t\tSKSE::log::warn(\"[Streamline] Reflex cap OVER-SUBMIT: {}fps render x{} = \"\r\n"
    b"\t\t\t\t\t\t\"{} present fps vs a {}Hz panel - the cap formula is wrong (v1.06)\",\r\n"
    b"\t\t\t\t\t\tcapFps, capMult, capFps * capMult, Get().refreshRate);\r\n",
))

# --------------------------------------------------------------------------
# EDIT 2 -- give the camera history its writer
# --------------------------------------------------------------------------
EDITS.append((
    "camhistory-writer",

    b"\t\t\tcamPrevOk = rebuildViewProj(s_prevCamView, s_prevCamEye,\r\n"
    b"\t\t\t                            s_prevCamProj, camPrevVP) &&\r\n"
    b"\t\t\t            finiteMagOf(camPrevVP) > 1.0e-6f;\r\n"
    b"\t\t}\r\n",

    b"\t\t\tcamPrevOk = rebuildViewProj(s_prevCamView, s_prevCamEye,\r\n"
    b"\t\t\t                            s_prevCamProj, camPrevVP) &&\r\n"
    b"\t\t\t            finiteMagOf(camPrevVP) > 1.0e-6f;\r\n"
    b"\t\t}\r\n"
    b"\r\n"
    b"\t\t// v1.06: THE WRITER THIS HISTORY NEVER HAD.\r\n"
    b"\t\t//\r\n"
    b"\t\t// v1.02c wrote the reader above and stopped there. The four statics\r\n"
    b"\t\t// declared a few lines up are read once each and written nowhere:\r\n"
    b"\t\t// s_prevCamView, s_prevCamProj and s_prevCamEye are never assigned,\r\n"
    b"\t\t// and s_hasPrevCam is initialised to false and never set true. So\r\n"
    b"\t\t// camPrevOk was false on every frame of every run, and the heartbeat\r\n"
    b"\t\t// proves it rather than inferring it:\r\n"
    b"\t\t//\r\n"
    b"\t\t//     21:27:27.912  cam(ok/inv)=121/0  camPrev(ok/used)=0/0\r\n"
    b"\t\t//\r\n"
    b"\t\t// cam() is healthy and camPrev() is flat zero - the rebuild existed\r\n"
    b"\t\t// and could never be reached. A rebuild is only as good as its\r\n"
    b"\t\t// history; this is that history. Stored as RAW engine matrices, so\r\n"
    b"\t\t// the previous frame goes through exactly the same rebuildViewProj\r\n"
    b"\t\t// as the current one and the two cannot diverge by convention.\r\n"
    b"\t\tif (camCurOk) {\r\n"
    b"\t\t\ts_prevCamView = a_fb.CameraView;\r\n"
    b"\t\t\ts_prevCamProj = a_fb.CameraProj;\r\n"
    b"\t\t\ts_prevCamEye[0] = a_fb.CameraPosAdjust[0];\r\n"
    b"\t\t\ts_prevCamEye[1] = a_fb.CameraPosAdjust[1];\r\n"
    b"\t\t\ts_prevCamEye[2] = a_fb.CameraPosAdjust[2];\r\n"
    b"\t\t\ts_hasPrevCam = true;\r\n"
    b"\t\t}\r\n",

))


def main() -> int:
    apply = "--apply" in sys.argv
    raw = open(SRC, "rb").read()

    problems = []
    for label, old, new in EDITS:
        n = raw.count(old)
        print(f"[{label}] count(old) = {n}")
        if n != 1:
            problems.append(f"{label}: expected exactly 1 anchor, found {n}")
        # idempotency guard: the inserted marker must not already be present
        marker = new.split(b"\r\n")[0][:0]  # placeholder, replaced below
    # explicit idempotency markers
    guards = [
        ("capfps-restore-divisor", b"v1.06: the divisor is the whole point of this line"),
        ("camhistory-writer", b"v1.06: THE WRITER THIS HISTORY NEVER HAD"),
    ]
    for label, marker in guards:
        if marker in raw:
            problems.append(f"{label}: MARKER ALREADY PRESENT - patch has already run")

    if problems:
        print()
        for p in problems:
            print("REFUSED:", p)
        print("REFUSED, nothing written")
        return 1

    if not apply:
        print()
        print("DRY RUN OK - all anchors unique, no markers present")
        print("re-run with --apply to write")
        return 0

    out = raw
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)

    # post-conditions, checked on the RESULT text
    checks = [
        (b"refreshRate / static_cast<double>(capMult) - 1.0", "divisor present"),
        (b"capFps * capMult > Get().refreshRate", "over-submit assertion present"),
        (b"v1.06: THE WRITER THIS HISTORY NEVER HAD", "history writer present"),
        (b"s_hasPrevCam = true;", "s_hasPrevCam set true"),
        (b"s_prevCamView = a_fb.CameraView;", "s_prevCamView assigned"),
        (b"s_prevCamEye[2] = a_fb.CameraPosAdjust[2];", "s_prevCamEye assigned"),
    ]
    bad = [(pat, why) for pat, why in checks if pat not in out]
    if bad:
        print()
        for pat, why in bad:
            print("POST-CONDITION FAILED:", why, pat)
        print("REFUSED, nothing written")
        return 1

    open(SRC, "wb").write(out)

    crlf = out.count(b"\r\n")
    bare = out.count(b"\n") - crlf
    print()
    print(f"WROTE {SRC}")
    print(f"  bytes {len(raw)} -> {len(out)}  (delta {len(out) - len(raw)})")
    print(f"  CRLF={crlf}  bare_LF={bare}")
    if bare != 0:
        print("  WARNING: bare LF appeared - the file was CRLF-only before")
    return 0


if __name__ == "__main__":
    sys.exit(main())
