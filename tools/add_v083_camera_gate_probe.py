#!/usr/bin/env python3
"""
v0.83 -- instrument the camera-snapshot gate so the next log NAMES the killer.

WHY: the 13:22 run has
        det(min/max)=1.000/1.000   clipDevMax=0.0000   frozen=300
        snap(acc/jmp/re/zero/arr)=1737/5402/0/0/17412   dist(last/acc)=849.4/0.0
     i.e. the accepted camera NEVER MOVES (acc-dist 0.0, move=0.0000) while the
     jump gate rejects 5402 arrivals.  `snapFrozenReject` exists in the struct but
     is NOT printed anywhere, so we cannot tell whether the v0.78 frozen gate is
     the one killing the stream.

WHAT THIS ADDS (observation only -- no gate logic is changed):

  1. Map/Unmap hook hit counters
        mapPerFrameHits   : Map() on the perFrame resource
        unmapPerFrameHits : Unmap() with a live tlsMappedFB
     If these keep rising after entering the world, the buffer IS being written
     and the loss is in the gate.  If they stop, the engine switched buffers.

  2. Instantaneous gate state, sampled every heartbeat
        frozenRej         : cumulative snapFrozenReject  (was invisible)
        frozenRep         : cumulative snapFrozenRepeats
        sawDiff           : snapSawDifferentSinceRepeat  (0/1)
        consecRej         : snapConsecReject at sample time
        lastDist          : snapLastDist (this arrival vs last accepted)

  3. The accept-ratio is already derivable: acc / arrivals.

The heartbeat line gains one compact group, so it stays readable:

    | snap(acc/jmp/re/zero/arr/frozen)=... gate(sawDiff/consecRej/frozenRep)=...
      map(perFrame/unmap)=N/N
"""

import io
import sys

CPP = "src/FrameGen.cpp"     # LF
HDR = "src/FrameGen.h"       # CRLF
SLN = "src/Streamline.cpp"   # LF

NL_HDR = "\r\n"
NL_CPP = "\n"

# ------------------------------------------------------------------ header ---
H_ANCHOR = (NL_HDR.join([
    "\t\tbool  snapHaveLastMat = false;",
    "\t\tfloat snapLastMat[4][4] = {};",
    "\t\tstd::uint64_t snapFrozenRepeats = 0;   // identical-after-different count",
    "\t\tstd::uint64_t snapFrozenReject = 0;    // rejected because of the above",
    "\t\tbool  snapSawDifferentSinceRepeat = false;",
]) + NL_HDR)

H_NEW = (H_ANCHOR + NL_HDR.join([
    "\t\t// ---- v0.83: instrument the gate so a log can name which branch fires ----",
    "\t\t// snapFrozenReject / snapFrozenRepeats already existed but were never",
    "\t\t// printed, so the 13:22 run could not tell whether the v0.78 frozen gate",
    "\t\t// was the thing rejecting every arrival. These are observation only.",
    "\t\tstd::uint64_t mapPerFrameHits = 0;      // Map() matched the perFrame buffer",
    "\t\tstd::uint64_t unmapPerFrameHits = 0;    // Unmap() had a live tlsMappedFB",
    "\t\tstd::uint64_t snapIdenticalArrivals = 0;  // matrix == snapLastMat",
    "\t\tstd::uint64_t snapDifferentArrivals = 0;  // matrix != snapLastMat",
]) + NL_HDR)

# -------------------------------------------------------------------- cpp ----
# 1. Map hook: count every time the perFrame buffer is actually mapped.
M_ANCHOR = NL_CPP.join([
    "\t\t\t\tif (SUCCEEDED(hr) && pMappedResource) {",
    "\t\t\t\t\tauto* perFrame = FrameGen::GetPerFrameBuffer();",
    "\t\t\t\t\tif (perFrame && *perFrame == pResource && pMappedResource->pData)",
    "\t\t\t\t\t\ttlsMappedFB = static_cast<FrameBuffer*>(pMappedResource->pData);",
    "\t\t\t\t}",
]) + NL_CPP

M_NEW = NL_CPP.join([
    "\t\t\t\tif (SUCCEEDED(hr) && pMappedResource) {",
    "\t\t\t\t\tauto* perFrame = FrameGen::GetPerFrameBuffer();",
    "\t\t\t\t\tif (perFrame && *perFrame == pResource && pMappedResource->pData) {",
    "\t\t\t\t\t\ttlsMappedFB = static_cast<FrameBuffer*>(pMappedResource->pData);",
    "\t\t\t\t\t\t// v0.83: does the engine still write this buffer after entering",
    "\t\t\t\t\t\t// the world? If this stops rising, the loss is upstream of the gate.",
    "\t\t\t\t\t\t++Get().mapPerFrameHits;",
    "\t\t\t\t\t}",
    "\t\t\t\t}",
]) + NL_CPP

# 2. Unmap hook: count the arrivals that actually reach the gate.
U_ANCHOR = NL_CPP.join([
    "\t\t\t\tif (tlsMappedFB) {",
    "\t\t\t\t\tauto& fg = Get();",
]) + NL_CPP

U_NEW = NL_CPP.join([
    "\t\t\t\tif (tlsMappedFB) {",
    "\t\t\t\t\tauto& fg = Get();",
    "\t\t\t\t\t++fg.unmapPerFrameHits;   // v0.83: arrivals that DO reach the gate",
]) + NL_CPP

# 3. Frozen gate: count identical / different separately (no behaviour change).
G_ANCHOR = NL_CPP.join([
    "\t\t\tif (identical && snapSawDifferentSinceRepeat) {",
]) + NL_CPP

G_NEW = NL_CPP.join([
    "\t\t\t// v0.83: split the two populations so the log shows how much of the",
    "\t\t\t// stream is byte-identical (a stale slot) vs genuinely changing.",
    "\t\t\tif (identical)",
    "\t\t\t\t++snapIdenticalArrivals;",
    "\t\t\telse",
    "\t\t\t\t++snapDifferentArrivals;",
    "",
    "\t\t\tif (identical && snapSawDifferentSinceRepeat) {",
]) + NL_CPP

# ------------------------------------------------------------------ heartbeat -
HB_FMT_ANCHOR = ('"snap(acc/jmp/re/zero/arr)={}/{}/{}/{}/{} dist(last/acc)={:.1f}/{:.1f}",')

HB_FMT_NEW = ('"snap(acc/jmp/re/zero/arr/frozen)={}/{}/{}/{}/{}/{} "\n'
              '\t\t\t\t\t"gate(sawDiff/consecRej/frozenRep/id/diff)={}:{}/{}/{}/{} "\n'
              '\t\t\t\t\t"mapHit(perFrame/unmap)={}/{} dist(last/acc)={:.1f}/{:.1f}",')

HB_ARG_ANCHOR = "\t\t\t\t\tGet().snapAccept, Get().snapRejectJump, Get().snapRelock,\n" \
                "\t\t\t\t\tGet().snapRejectZero, Get().snapArrivals,\n" \
                "\t\t\t\t\tGet().snapLastDist, Get().snapAcceptDist);\n"

HB_ARG_NEW = ("\t\t\t\t\tGet().snapAccept, Get().snapRejectJump, Get().snapRelock,\n"
              "\t\t\t\t\tGet().snapRejectZero, Get().snapArrivals, Get().snapFrozenReject,\n"
              "\t\t\t\t\tGet().snapSawDifferentSinceRepeat ? 1 : 0, Get().snapConsecReject,\n"
              "\t\t\t\t\tGet().snapFrozenRepeats,\n"
              "\t\t\t\t\tGet().snapIdenticalArrivals, Get().snapDifferentArrivals,\n"
              "\t\t\t\t\tGet().mapPerFrameHits, Get().unmapPerFrameHits,\n"
              "\t\t\t\t\tGet().snapLastDist, Get().snapAcceptDist);\n")

EDITS = [
    (HDR, "H: v0.83 counters", H_ANCHOR, H_NEW, NL_HDR),
    (CPP, "M: Map hit counter", M_ANCHOR, M_NEW, NL_CPP),
    (CPP, "U: Unmap hit counter", U_ANCHOR, U_NEW, NL_CPP),
    (CPP, "G: identical/different split", G_ANCHOR, G_NEW, NL_CPP),
    (SLN, "HB-fmt: heartbeat format", HB_FMT_ANCHOR, HB_FMT_NEW, NL_CPP),
    (SLN, "HB-arg: heartbeat args", HB_ARG_ANCHOR, HB_ARG_NEW, NL_CPP),
]

MARKERS = ["v0.83", "snapIdenticalArrivals", "mapPerFrameHits"]


def main():
    apply = "--apply" in sys.argv
    print("=" * 74)
    print("v0.83 camera-gate instrumentation  (mode: %s)" % ("APPLY" if apply else "DRY RUN"))
    print("=" * 74)

    files = {}
    for path in (HDR, CPP, SLN):
        with io.open(path, "rb") as f:
            files[path] = f.read().decode("utf-8")

    # guard 1: markers absent
    for path, s in files.items():
        hit = [m for m in MARKERS if m in s]
        if hit:
            print("markers   : ALREADY PRESENT in %s -> REFUSED" % path)
            for m in hit:
                print("   found: %s" % m)
            return 2
    print("markers   : absent (patch has not run)")

    # guard 2: every anchor occurs exactly once
    ok = True
    for path, label, old, new, _nl in EDITS:
        n = files[path].count(old)
        if n != 1:
            ok = False
        print("  [%s][%-28s] occurrences=%d  %s"
              % (path.split("/")[-1], label, n, "ok" if n == 1 else "FAIL"))
    if not ok:
        print("REFUSED: anchor not unique. nothing written.")
        return 2

    # guard 3: brace balance must not move inside the edited regions
    for path, label, old, new, _nl in EDITS:
        d = (new.count("{") - new.count("}")) - (old.count("{") - old.count("}"))
        if d != 0:
            ok = False
        print("balance   : [%-28s] %+d  %s" % (label, d, "ok" if d == 0 else "FAIL"))
    if not ok:
        print("REFUSED: brace balance moved. nothing written.")
        return 2

    # guard 4: heartbeat placeholders must equal arguments (1:1)
    f_n = HB_FMT_NEW.count("{}")
    a_n = HB_ARG_NEW.count("Get().")
    f_o = HB_FMT_ANCHOR.count("{}")
    a_o = HB_ARG_ANCHOR.count("Get().")
    d_f, d_a = f_n - f_o, a_n - a_o
    print("  [%-28s] format +%d  args +%d  %s"
          % ("heartbeat placeholders", d_f, d_a, "ok" if d_f == d_a else "FAIL"))
    if d_f != d_a:
        print("REFUSED: placeholder/argument mismatch. nothing written.")
        return 2

    out = {p: s for p, s in files.items()}
    for path, _label, old, new, _nl in EDITS:
        out[path] = out[path].replace(old, new, 1)

    print("")
    for path in (HDR, CPP, SLN):
        a = len(files[path].encode("utf-8"))
        b = len(out[path].encode("utf-8"))
        print("  %-28s %7d -> %7d bytes (%+d)" % (path, a, b, b - a))

    if not apply:
        print("DRY RUN: nothing written. Re-run with --apply.")
        return 0

    for path in (HDR, CPP, SLN):
        with io.open(path, "wb") as f:
            f.write(out[path].encode("utf-8"))
        print("WRITTEN   : %s" % path)
    print("RESULT: APPLIED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
