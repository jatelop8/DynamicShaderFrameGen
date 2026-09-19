#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.12 -- the Reflex cap is a FLIP cap; the divisor by capMult collapsed the
render side to 9.75 fps.

Evidence (all from the 14:55:21 run, log DynamicShaderFrameGen.log):

  capUs = 12658 while capMult was 2   ->  1e6 / (160/2 - 1) = 1e6/79  = 12658
  capUs = 25641 once capMult was 4    ->  1e6 / (160/4 - 1) = 1e6/39  = 25641
  dt    = 102.56 ms                   ->  4 x 25641 us                = 102564
  real  = 9.74 fps                    ->  39/4                      = 9.75

The limiter's quantum is consumed once per FLIP. Dividing by the multiplier
therefore throttled the flips to 39/s and left the render side at 39/4. The
v0.63 comment block in this very function states the correct invariant; the
v1.06 note that re-added the divisor mis-attributed the 21:27 freeze.

Rule for this driver (same as every other patch here):
  * dry run by default, --apply writes
  * every anchor must have text.count(old) == 1, else REFUSED, nothing written
  * insertion/rewrite guards: an idempotency marker, plus a splice guard
  * post-conditions are checked on the RESULT text, never on the input
  * the EOL is taken from the FILE, never from the anchor
"""
import sys
import hashlib
import shutil
import time

F_SL = "src/Streamline.cpp"

# ---------------------------------------------------------------- anchors ---
A_WANT_OLD = (
    "\t\t\t\tconst double want = Get().refreshRate / static_cast<double>(capMult) - 1.0;\r\n"
    "\t\t\t\tcapFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);"
)

A_WANT_NEW = (
    "\t\t\t\t// v1.12 -- THE DIVISOR WAS THE BUG, and this time it is proved by the\r\n"
    "\t\t\t\t// running process, not by argument. The limiter's quantum is a FLIP,\r\n"
    "\t\t\t\t// not a real frame, so dividing by capMult paced the FLIPS at 39/s\r\n"
    "\t\t\t\t// and left the render side at 39/4 = 9.75 fps. Four numbers from the\r\n"
    "\t\t\t\t// 2026-09-19 14:55 run agree, and all four reproduce\r\n"
    "\t\t\t\t// 1e6/(160/capMult - 1) exactly:\r\n"
    "\t\t\t\t//   capUs = 12658 while capMult was 2  -> 1e6/79      = 12658\r\n"
    "\t\t\t\t//   capUs = 25641 once capMult was 4   -> 1e6/39      = 25641\r\n"
    "\t\t\t\t//   dt    = 102.56 ms                  -> 4 x 25641   = 102564 us\r\n"
    "\t\t\t\t//   real  = 9.74 fps                   -> 39/4        = 9.75\r\n"
    "\t\t\t\t// The 21:27 freeze that the v1.06 note blames on dropping the divisor\r\n"
    "\t\t\t\t// cannot have come from dropping it: with the divisor PRESENT the panel\r\n"
    "\t\t\t\t// saw 39 presents/s, not 636, and the render side collapsed -- which is\r\n"
    "\t\t\t\t// what the log for that run actually shows.\r\n"
    "\t\t\t\t// The v0.63 block above states the correct invariant: the cap is the\r\n"
    "\t\t\t\t// FLIP rate, kept one Hz under the panel; the multiplier only divides\r\n"
    "\t\t\t\t// the render side. This line restores exactly that.\r\n"
    "\t\t\t\tconst double want = Get().refreshRate - 1.0;\r\n"
    "\t\t\t\tcapFps = static_cast<std::uint32_t>(want < 15.0 ? 15.0 : want);"
)

A_ASSERT_OLD = (
    "\t\t\t\t// v1.06: state the invariant as an assertion, so a future edit to\r\n"
    "\t\t\t\t// either term cannot silently re-introduce the over-submit.\r\n"
    "\t\t\t\tif (capFps * capMult > Get().refreshRate)\r\n"
    "\t\t\t\t\tSKSE::log::warn(\"[Streamline] Reflex cap OVER-SUBMIT: {}fps render x{} = \"\r\n"
    "\t\t\t\t\t\t\"{} present fps vs a {}Hz panel - the cap formula is wrong (v1.06)\",\r\n"
    "\t\t\t\t\t\tcapFps, capMult, capFps * capMult, Get().refreshRate);"
)

A_ASSERT_NEW = (
    "\t\t\t\t// v1.12: the assertion must test the invariant the cap now states.\r\n"
    "\t\t\t\t// \"render fps x capMult > panel\" was the v1.06 misreading -- it treats a\r\n"
    "\t\t\t\t// flip cap as a render cap. The real invariants are that a FLIP cap can\r\n"
    "\t\t\t\t// never exceed the panel, and that the render side lands where the\r\n"
    "\t\t\t\t// multiplier promises (the previous defect left no trace of either).\r\n"
    "\t\t\t\tif (capFps > Get().refreshRate)\r\n"
    "\t\t\t\t\tSKSE::log::warn(\"[Streamline] Reflex cap OVER-SUBMIT: {} flip fps on a \"\r\n"
    "\t\t\t\t\t\t\"{}Hz panel - the cap formula is wrong (v1.12)\",\r\n"
    "\t\t\t\t\t\tcapFps, Get().refreshRate);\r\n"
    "\t\t\t\telse\r\n"
    "\t\t\t\t\tSKSE::log::info(\"[Streamline] Reflex cap check (v1.12): {} flip fps on a \"\r\n"
    "\t\t\t\t\t\t\"{}Hz panel = {:.1f} rendered fps at {}x\",\r\n"
    "\t\t\t\t\t\tcapFps, Get().refreshRate,\r\n"
    "\t\t\t\t\t\tcapFps / static_cast<double>(capMult), capMult);"
)

A_LOG_OLD = (
    "\t\t\t\tSKSE::log::info(\"[Streamline] Reflex FLIP cap = {} fps ({}us) - panel {}Hz, "
    "{} flips per real frame => ~{} presented fps (real = cap/flips){}{}\",\r\n"
    "\t\t\t\t\tcapFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps * capMult,"
)

A_LOG_NEW = (
    "\t\t\t\tSKSE::log::info(\"[Streamline] Reflex FLIP cap = {} fps ({}us) - panel {}Hz, "
    "{} flips per real frame => ~{} presented fps, ~{:.1f} rendered fps "
    "(v1.12: the cap is the FLIP rate){}{}\",\r\n"
    "\t\t\t\t\tcapFps, opts.frameLimitUs, Get().refreshRate, capMult, capFps,\r\n"
    "\t\t\t\t\tcapFps / static_cast<double>(capMult),"
)

PLAN = [
    ("want",      A_WANT_OLD,   A_WANT_NEW),
    ("assertion", A_ASSERT_OLD, A_ASSERT_NEW),
    ("log line",  A_LOG_OLD,    A_LOG_NEW),
]

MARKER = "v1.12 -- THE DIVISOR WAS THE BUG"


def file_eol(path: str) -> str:
    """Decide the EOL from the FILE, never from the anchor.

    A single-line anchor contains no newline, so inferring the EOL from it is
    impossible; doing it anyway is how an earlier patch flipped a CRLF file to
    bare LF (12/12 post-conditions passed while bareLF went 0 -> 78)."""
    b = open(path, "rb").read()
    crlf = b.count(b"\r\n")
    lf = b.count(b"\n") - crlf
    return "\r\n" if crlf and not lf else "\n"


def splice_guard(text: str, idx: int) -> bool:
    """The char before a match must be a line start, or the anchor is a
    fragment of a longer identifier/statement."""
    if idx == 0:
        return True
    return text[idx - 1] in "\r\n"


def main() -> int:
    apply = "--apply" in sys.argv
    path = F_SL
    raw = open(path, "rb").read()
    eol = file_eol(path)
    text = raw.decode("utf-8")

    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    print(f"file        : {path}")
    print(f"size        : {len(raw)} B   CRLF={crlf}   bareLF={bare}")
    print(f"eol from file: {'CRLF' if eol == chr(13) + chr(10) else 'LF'}")
    print()

    if MARKER in text:
        print(f"REFUSED, nothing written (idempotency marker present: {MARKER!r})")
        return 1

    # ---- validate every anchor BEFORE touching the result ----------------
    for label, old, _new in PLAN:
        n = text.count(old)
        print(f"  anchor[{label:10s}] count = {n}")
        if n != 1:
            print(f"REFUSED, nothing written (anchor {label!r} is not unique: {n})")
            return 2
        idx = text.index(old)
        if not splice_guard(text, idx):
            print(f"REFUSED, nothing written (splice guard failed on {label!r})")
            return 2
    print()

    # ---- normalise the anchor EOL to the file's EOL, then substitute -----
    out = text
    for label, old, new in PLAN:
        o = old.replace("\r\n", eol)
        n = new.replace("\r\n", eol)
        if out.count(o) != 1:
            print(f"REFUSED, nothing written (anchor {label!r} lost after EOL normalisation)")
            return 2
        out = out.replace(o, n, 1)

    # ---- post-conditions, on the RESULT text ----------------------------
    bad = []
    if out.count("const double want = Get().refreshRate - 1.0;") != 1:
        bad.append("the new cap line is not present exactly once")
    if out.count("refreshRate / static_cast<double>(capMult) - 1.0") != 0:
        bad.append("the divisor survived")
    if out.count("capFps * capMult") != 0:
        bad.append("the 'render fps x capMult' reading survived")
    if out.count("capFps > Get().refreshRate") != 1:
        bad.append("the new invariant assertion is not present exactly once")
    if out.count("Reflex cap check (v1.12)") != 1:
        bad.append("the v1.12 cap-check log is not present exactly once")
    if out.count("v1.12: the cap is the FLIP rate") != 1:
        bad.append("the v1.12 log tail is not present exactly once")
    if MARKER not in out:
        bad.append("idempotency marker missing from the result")
    out_b = out.encode("utf-8")
    if out_b.count(b"\n") - out_b.count(b"\r\n") != raw.count(b"\n") - raw.count(b"\r\n"):
        bad.append("bare-LF count changed")
    if bad:
        print("REFUSED, nothing written (post-conditions on the RESULT failed):")
        for b in bad:
            print("   -", b)
        return 3

    print("post-conditions on the RESULT: PASS")
    print(f"size        : {len(raw)} B -> {len(out_b)} B  ({len(out_b) - len(raw):+d})")
    if not apply:
        print("\nDRY RUN -- nothing written. Re-run with --apply.")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_v112_{stamp}"
    shutil.copy2(path, bak)
    open(path, "wb").write(out_b)
    print(f"\nWRITTEN {path}   backup {bak}")
    print(f"md5 old {hashlib.md5(raw).hexdigest()}")
    print(f"md5 new {hashlib.md5(open(path, 'rb').read()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
