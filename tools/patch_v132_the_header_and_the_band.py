#!/usr/bin/env python3
# v1.32: two instrument defects found by decoding the 13:47 run's own output.
#   1. WriteScreenBmp never wrote biSize, so every DIB field sat one slot early
#      and all 71 BMPs were rejected by ordinary readers.
#   2. The screen hash covered the whole frame INCLUDING our own overlay, which
#      redraws every sample -> `same` could never reach its threshold and FROZEN
#      could never fire.  Measured: 71 samples, same=0 on every one, while the
#      world band below the overlay was byte-identical across 1.40 s.
# Anchor policy: line-index based, exact tabs, applied bottom-up, every anchor
# verified by its stripped content before anything is written.
import sys, io, os

SRC = r"D:/Modding/DynamicShaderFrameGen/src/DX12SwapChain.cpp"
APPLY = "--apply" in sys.argv

def T(n):
    """n tabs."""
    return "\t" * n

# (start_line, end_line, [expected .strip() of each line], [new FULL lines, tabs explicit])
EDITS = [
    # ---- F. FROZEN message wording: it is the band, not the whole screen ----
    (1209, 1209,
     ['std::fprintf(f, "[%lld] [SCREEN] FROZEN for %u captures: the screen is byte-identical "'],
     [T(9) + 'std::fprintf(f, "[%lld] [SCREEN] FROZEN for %u captures: the world band (overlay excluded) is byte-identical "']),

    # ---- E. STALE message wording ----
    (1192, 1192,
     ['std::fprintf(f, "[%lld] [SCREEN] STALE over %u s: the SCREEN has shown ONE image "'],
     [T(9) + 'std::fprintf(f, "[%lld] [SCREEN] STALE over %u s: the world band has shown ONE image "']),

    # ---- D. printed field names must name what they now measure ----
    (1164, 1165,
     ['std::fprintf(f, "[%lld] [SCREEN] #%u hash=%016llX lum=%.2f dLum=%+.2f "',
      '"same=%u oursSame=%u ring=%u/%u ours=%016llX fg=%d frames=%llu %s\\n",'],
     [T(9) + 'std::fprintf(f, "[%lld] [SCREEN] #%u band=%016llX lum=%.2f dLum=%+.2f "',
      T(10) + '"bandSame=%u oursSame=%u ring=%u/%u ours=%016llX fg=%d frames=%llu %s\\n",']),

    # ---- C. the hash itself: band only, so our overlay cannot mask a freeze ----
    (1106, 1109,
     ['for (std::size_t i = 0; i < nPx * 4u; ++i) {',
      'h2 ^= px[i];',
      'h2 *= 1099511628211ull;',
      '}'],
     [T(9) + '// v1.32: the band only - see kScrBandY0.  The DIB is BGRA top-down,',
      T(9) + '// so image row `by` starts at by*kScrW*4.',
      T(9) + 'for (int by = kScrBandY0; by < kScrBandY1; ++by) {',
      T(10) + 'const std::uint8_t* brow = px',
      T(10) + '+ static_cast<std::size_t>(by) * static_cast<std::size_t>(kScrW) * 4u;',
      T(10) + 'for (int bx = 0; bx < kScrW * 4; ++bx) {',
      T(11) + 'h2 ^= brow[bx];',
      T(11) + 'h2 *= 1099511628211ull;',
      T(10) + '}',
      T(9) + '}']),

    # ---- B. the band definition ----
    (1044, 1044,
     ['static const int kScrH = 360;'],
     [T(6) + 'static const int kScrH = 360;',
      T(6) + '// v1.32: the band the overlay cannot reach.  Our own ImGui overlay (fps',
      T(6) + '// readout top right, loading notices top left) is drawn INTO this capture',
      T(6) + '// and redraws on every single sample, so a whole-frame hash can never',
      T(6) + '// repeat and `same` can never reach its threshold.  Measured on the 13:47',
      T(6) + '// run: 71 samples, same=0 on every one, while the band below the overlay',
      T(6) + '// was byte-identical across 1.40 s.  Hash this band: top 16%, bottom 12%.',
      T(6) + 'static const int kScrBandY0 = (kScrH * 16) / 100;',
      T(6) + 'static const int kScrBandY1 = (kScrH * 88) / 100;']),

    # ---- A. the BMP header: biSize was never written ----
    (705, 710,
     ['const unsigned short planes = 1u, bpp = 24u;',
      "hdr[0] = 'B'; hdr[1] = 'M';",
      'std::memcpy(hdr + 2, &fsize, 4);',
      'std::memcpy(hdr + 10, &off, 4);',
      'std::memcpy(hdr + 14, &a_w, 4);',
      'std::memcpy(hdr + 18, &a_h, 4);'],
     [T(2) + 'const unsigned short planes = 1u, bpp = 24u;',
      T(2) + '// v1.32: biSize was never written, so every field after it sat one slot',
      T(2) + '// early - width landed at 14 (where biSize belongs) and height at 18,',
      T(2) + '// leaving biHeight 0 - and ordinary readers rejected the files',
      T(2) + '// ("Unsupported BMP header type (640)").  Measured on all 71 files of the',
      T(2) + '// 13:47 run: not one was openable.  biSize = 40 for a BITMAPINFOHEADER.',
      T(2) + 'const unsigned dibSize = 40u;',
      T(2) + "hdr[0] = 'B'; hdr[1] = 'M';",
      T(2) + 'std::memcpy(hdr + 2, &fsize, 4);',
      T(2) + 'std::memcpy(hdr + 10, &off, 4);',
      T(2) + 'std::memcpy(hdr + 14, &dibSize, 4);',
      T(2) + 'std::memcpy(hdr + 18, &a_w, 4);',
      T(2) + 'std::memcpy(hdr + 22, &a_h, 4);']),
]

raw = open(SRC, "rb").read()
assert b"\r" not in raw, "source is not pure LF"
lines = raw.decode("utf-8").split("\n")

# ---- verify every anchor BEFORE writing anything ----
fail = 0
for (s, e, exp, new) in EDITS:
    got = [lines[i - 1].strip() for i in range(s, e + 1)]
    if got != exp:
        fail += 1
        print("REFUSED anchor lines %d-%d" % (s, e))
        for k in range(max(len(exp), len(got))):
            g = got[k] if k < len(got) else "<missing>"
            x = exp[k] if k < len(exp) else "<none>"
            if g != x:
                print("   line %d" % (s + k))
                print("     got: %s" % g)
                print("     exp: %s" % x)
if fail:
    print("REFUSED, nothing written (%d bad anchors)" % fail)
    sys.exit(1)

# ---- uniqueness: each expected first line must appear exactly once in the file ----
for (s, e, exp, new) in EDITS:
    n = sum(1 for L in lines if L.strip() == exp[0])
    if n != 1:
        print("REFUSED: anchor line %d is not unique (count=%d): %s" % (s, n, exp[0][:60]))
        sys.exit(1)
print("all %d anchors verified, each unique" % len(EDITS))

# ---- apply bottom-up ----
for (s, e, exp, new) in sorted(EDITS, key=lambda x: -x[0]):
    lines[s - 1:e] = new

out = "\n".join(lines)
# post-checks
assert "dibSize" in out
assert "kScrBandY0" in out and "kScrBandY1" in out
assert "bandSame=" in out
assert "band=%016llX" in out
assert "memcpy(hdr + 14, &a_w, 4)" not in out          # old, wrong
assert "memcpy(hdr + 22, &a_h, 4)" in out              # new, right
assert "same=%u oursSame=%u ring=" not in out
assert "the SCREEN has shown ONE image" not in out
assert "the screen is byte-identical " not in out
assert "\r" not in out

if not APPLY:
    print("DRY RUN OK - %d bytes -> %d bytes (not written)" % (len(raw), len(out.encode("utf-8"))))
    sys.exit(0)

open(SRC, "wb").write(out.encode("utf-8"))
chk = open(SRC, "rb").read()
print("WROTE %d bytes -> %d bytes, CR=%d" % (len(raw), len(chk), chk.count(b"\r")))
