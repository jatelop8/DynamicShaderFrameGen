"""v0.60: enable DLSSGFlags::eEnableFullscreenMenuDetection.

Why this and not another hand-rolled menu hack:
  Streamline's own SDK exposes exactly this switch (sl_dlss_g.h):
      eEnableFullscreenMenuDetection = 1 << 4
  and DFG never sets it -- `opts.flags{}` stays 0, so the SDK keeps generating
  frames while the main menu is up and every menu element gets interpolated as
  if it were 3D content.  Letting the SDK do the menu detection is strictly more
  authoritative than any per-frame heuristic of ours.

Relationship to the v0.59 reset fix (already on disk, kept as-is):
  * this flag  -> the SDK pauses generation while a fullscreen menu is open
  * reset edge -> we stop telling the SDK "new sequence" on every single frame
  They are independent, and each leaves its own log line, so shipping both does
  not cost diagnostic power:
      "DLSSG flags: fullscreenMenuDetection=on"      <- this patch
      "RESET probe: menuOpen=true reset=0"           <- v0.59

Guards: marker idempotency, pure-LF precheck, anchor uniqueness, backup,
post-write read-back including a line-ending re-check.
Dry run by default; pass --apply to write.
"""
import sys
import os
import shutil
import datetime

SRC = r"D:\Modding\DynamicShaderFrameGen\src\Streamline.cpp"
MARK = "eEnableFullscreenMenuDetection"

OLD = (
    "\t\tsl::DLSSGOptions opts{};\n"
    "\t\topts.mode = sl::DLSSGMode::eOn;\n"
)

NEW = (
    "\t\tsl::DLSSGOptions opts{};\n"
    "\t\topts.mode = sl::DLSSGMode::eOn;\n"
    "\t\t// v0.60: hand fullscreen-menu handling to the SDK instead of guessing.\n"
    "\t\t// sl_dlss_g.h ships DLSSGFlags::eEnableFullscreenMenuDetection (1 << 4)\n"
    "\t\t// and we were leaving it unset (`flags{}` == 0), so DLSS-G kept generating\n"
    "\t\t// frames with a fullscreen menu up -- buttons, text and the fading backdrop\n"
    "\t\t// all got interpolated as 3D content.  Observed evidence: Transfusion's\n"
    "\t\t// [MOTION] dump printed reset=1 on every consecutive frame while the main\n"
    "\t\t// menu was open, i.e. the SDK was told \"new sequence\" once per frame.\n"
    "\t\t// Keep in sync with the v0.59 edge-triggered reset: that one limits how\n"
    "\t\t// often we reset, this one stops the generation altogether.\n"
    "\t\topts.flags |= sl::DLSSGFlags::eEnableFullscreenMenuDetection;\n"
    "\t\t{\n"
    "\t\t\tstatic bool menuFlagLogged = false;\n"
    "\t\t\tif (!menuFlagLogged) {\n"
    "\t\t\t\tmenuFlagLogged = true;\n"
    "\t\t\t\tSKSE::log::info(\"[Streamline] DLSSG flags: fullscreenMenuDetection=on (v0.60)\");\n"
    "\t\t\t}\n"
    "\t\t}\n"
)


def main():
    raw = open(SRC, "rb").read()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    print("line endings before : CRLF=%d bare_LF=%d" % (crlf, bare))
    if crlf != 0:
        print("REFUSED: file is not pure LF; refusing to touch line endings")
        return 2

    text = raw.decode("utf-8")

    # guard 1 -- idempotency.  The anchor survives the patch (we keep both anchor
    # lines), so requiring count(OLD)==1 would happily run twice; this marker is
    # what actually makes the patch single-shot.
    if MARK in text:
        print("REFUSED: %s already present, nothing written" % MARK)
        return 1

    # guard 2 -- anchor uniqueness
    n = text.count(OLD)
    print("anchor count        : %d" % n)
    if n != 1:
        print("REFUSED: anchor is not unique (expected exactly 1), nothing written")
        return 2

    # guard 3 -- the field we are about to touch must look untouched
    if "opts.flags" in text:
        print("REFUSED: opts.flags is already referenced elsewhere (%d hits); "
              "inspect before patching" % text.count("opts.flags"))
        return 2

    if "--apply" not in sys.argv:
        print("[dry run] anchor OK, would insert %d chars -- re-run with --apply"
              % (len(NEW) - len(OLD)))
        return 0

    bak = os.path.join(
        r"D:\workbuddy2\backup",
        "menuflag_v060_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    os.makedirs(bak, exist_ok=True)
    shutil.copy2(SRC, os.path.join(bak, "Streamline.cpp.bak"))
    print("backup              : %s" % bak)

    new_text = text.replace(OLD, NEW)
    open(SRC, "wb").write(new_text.encode("utf-8"))

    # read-back
    after_raw = open(SRC, "rb").read()
    after = after_raw.decode("utf-8")
    acrlf = after_raw.count(b"\r\n")
    abare = after_raw.count(b"\n") - acrlf
    print()
    print("[verify] delta chars        : %d" % (len(after) - len(text)))
    print("[verify] marker present     : %s" % (MARK in after))
    print("[verify] opts.flags line    : %s" % ("opts.flags |= sl::DLSSGFlags::eEnableFullscreenMenuDetection;" in after))
    print("[verify] log line present   : %s" % ("fullscreenMenuDetection=on (v0.60)" in after))
    print("[verify] line endings after : CRLF=%d bare_LF=%d" % (acrlf, abare))
    print("[verify] anchor still there : %s  (expected True; marker is the real guard)"
          % (OLD in after))
    print("[verify] source line count  : %d -> %d"
          % (text.count("\n"), after.count("\n")))

    ok = (MARK in after and acrlf == 0 and abare > 0
          and "opts.flags |= sl::DLSSGFlags::eEnableFullscreenMenuDetection;" in after)
    print()
    print("RESULT: %s" % ("OK - patched and verified" if ok else "FAILED - inspect manually"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
