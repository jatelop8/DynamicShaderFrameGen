"""v0.95 stage 2 -- point the heartbeat at the new counters.

Stage 1 deleted snapLockPublish/Hold/Relock/Still from FrameGen.h but the
heartbeat at Streamline.cpp:1062 still referenced all four, so the build failed
with C2039 x4 plus a C7595 (fmt could not make the format string a constant
expression once a referenced member was missing).

The fix keeps the arity identical -- four arguments out, four in -- so the
format string stays in balance and no other counter has to move:

    lock(pub/hold/re/still)={}/{}/{}/{}   ->   world(acc/skip/boot)/magVP={}/{}/{}/{:.6g}

The new fields are the ones that make a v0.95 run self-diagnosing:
  worldAcc    arrivals published because they ARE the world camera
  worldSkip   arrivals ignored because they are the UI/menu camera
  worldBoot   arrivals adopted before the first world camera was ever seen
  magVP       magnitude of the camera actually published on this heartbeat

If the filter is right, worldSkip should sit near worldAcc on a busy frame
(both cameras arrive each frame) and worldBoot should stop growing within the
first few dozen frames.
"""
import sys
from pathlib import Path

CPP = Path(r"D:/Modding/DynamicShaderFrameGen/src/Streamline.cpp")
FGCPP = Path(r"D:/Modding/DynamicShaderFrameGen/src/FrameGen.cpp")
FGHDR = Path(r"D:/Modding/DynamicShaderFrameGen/src/FrameGen.h")


def endings(data: bytes):
    return data.count(b"\r\n"), data.count(b"\n")


# ---------------------------------------------------------------------------
# Part A: export the magnitude of the last published camera so the heartbeat can
# report it. camMag() is an inline function in an anonymous namespace inside
# FrameGen.cpp, so it is NOT visible from Streamline.cpp -- referencing it there
# fails to compile. A plain data member crosses the TU boundary without any
# visibility problem.
# ---------------------------------------------------------------------------
PART_A = [
    (
        "hdr.snapLastMagVP",
        FGHDR,
        b"\t\tstd::uint64_t snapBootstrap = 0;       // published before 1st world cam\n",
        b"\t\tstd::uint64_t snapBootstrap = 0;       // published before 1st world cam\n"
        b"\t\tfloat snapLastMagVP = 0.0f;            // magVP of the last published camera\n",
    ),
    (
        "cpp.store_magvp",
        FGCPP,
        b"\t\tsnapPathLen += snapAcceptDist;\n",
        b"\t\tsnapPathLen += snapAcceptDist;\n"
        b"\t\tsnapLastMagVP = srcMag;\n",
    ),
]


EDITS = [
    (
        "fmt.tail",
        b'\t\t\t\t\t"lock(pub/hold/re/still)={}/{}/{}/{}",',
        b'\t\t\t\t\t"world(acc/skip/boot)/lastMagVP={}/{}/{}/{:.6g}",',
    ),
    (
        "args.tail",
        b"\t\t\t\t\tGet().snapLockPublish, Get().snapLockHold,\n"
        b"\t\t\t\t\tGet().snapLockRelock, Get().snapLockStill);",
        b"\t\t\t\t\tGet().snapWorldAccepted, Get().snapUiSkipped,\n"
        b"\t\t\t\t\tGet().snapBootstrap, Get().snapLastMagVP);",
    ),
    (
        "banner",
        b"diag active v0.94 (compiled",
        b"diag active v0.95 (compiled",
    ),
]


def main():
    apply = "--apply" in sys.argv
    print(f"mode: {'APPLY' if apply else 'DRY-RUN'}")
    for p in (CPP, FGCPP, FGHDR):
        crlf, lf = endings(p.read_bytes())
        print(f"  {p.name:16s} CRLF={crlf:5d} LF={lf:5d}")

    edits = []

    # ---- Part A: multi-line anchors, ending-agnostic -----------------------
    for label, path, old, new in PART_A:
        data = path.read_bytes()
        variants = [old, old.replace(b"\n", b"\r\n")]
        hit = None
        for v in variants:
            if data.count(v) == 1:
                hit = v
                break
        if hit is None:
            print(f"REFUSED, nothing written: {label} "
                  f"counts={[data.count(v) for v in variants]}")
            return 1
        edits.append((label, path, hit,
                      new.replace(b"\n", b"\r\n") if b"\r\n" in hit else new))

    # ---- Part B: Streamline.cpp --------------------------------------------
    data = CPP.read_bytes()
    for label, old, new in EDITS:
        variants = [old]
        if b"\n" in old and b"\r\n" not in old:
            variants.append(old.replace(b"\n", b"\r\n"))
        hit = None
        for v in variants:
            if data.count(v) == 1:
                hit = v
                break
        if hit is None:
            print(f"REFUSED, nothing written: {label} "
                  f"counts={[data.count(v) for v in variants]}")
            return 1
        edits.append((label, CPP, hit,
                      new.replace(b"\n", b"\r\n") if b"\r\n" in hit else new))

    # ---- apply, accumulating per file --------------------------------------
    acc = {}
    for label, path, old, new in edits:
        cur = acc.get(path, path.read_bytes())
        if cur.count(old) != 1:
            print(f"REFUSED at apply time: {label} count={cur.count(old)}")
            return 1
        acc[path] = cur.replace(old, new, 1)
        print(f"  {'WROTE' if apply else 'WOULD WRITE'} {label}  (+{len(new)-len(old)} bytes)")

    if apply:
        for path, out in acc.items():
            bc, bl = endings(path.read_bytes())
            ac, al = endings(out)
            print(f"  {path.name}: CRLF {bc}->{ac}, LF {bl}->{al}")
            path.write_bytes(out)

    if not apply:
        print("\n(dry run -- pass --apply to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
