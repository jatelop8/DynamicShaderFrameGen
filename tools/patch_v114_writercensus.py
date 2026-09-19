#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.14 probe: a census of the WRITERS that share the perFrame constant buffer.

Why: the 19:39 run proved the v1.13 gate works -- the orthographic writer is
dropped 13,804 times (cap=13804/0, so the escape hatch never fired) and the
published projection is a perspective one again.  But the published camera was
still BYTE-IDENTICAL for the entire 11.4 s world session (pos == prevPos ==
(-243.05,-415.31,118.56), move 0.0000, path stuck at 63.91, clipDev pinned at
its floor of 0.000061 for 274 frames), so clipToPrevClip stayed the identity.

Two completely different repairs follow from:
  (A) no writer moves its CameraPosAdjust -> the hook cannot see the camera at
      all -> the SOURCE must change (RE::PlayerCamera / cameraRoot->world).
  (B) a moving writer exists but is rejected -> the ACCEPTANCE rule must change.

Only a census of the actual writers can tell them apart, so this patch adds a
bounded table of distinct (pos) signatures and logs each new one.  Purely
additive: no behaviour changes, no gate/lock/reprojection touch.

Files: src/FrameGen.cpp and src/FrameGen.h, both PURE CRLF.
Dry run by default; --apply to write; --revert to undo.
"""
import sys
import pathlib

ROOT = pathlib.Path(r"D:/Modding/DynamicShaderFrameGen")
CPP = ROOT / "src/FrameGen.cpp"
HDR = ROOT / "src/FrameGen.h"

MARKER = "v1.14 probe: a census of the WRITERS"

H_MEMBERS = """	std::uint64_t snapNonCamera = 0;
	std::uint64_t snapSkipsSinceCam = 0;

	// ---- v1.14 probe: a census of the WRITERS sharing the perFrame buffer.
	// After v1.13 the orthographic writer is dropped, yet the published camera is
	// still byte-identical for a whole world session (19:39 run: pos == prevPos ==
	// (-243.05,-415.31,118.56), move 0.0000, path stuck at 63.91, clipDev pinned
	// at its floor of 0.000061 across 274 frames).  The decisive question is
	// whether ANY writer here moves its CameraPosAdjust: if none does, no
	// acceptance rule can ever produce motion and the SOURCE has to change.
	// The table is bounded to kSnapCensusMax signatures; snapCensusNew counts
	// arrivals whose position is not within 1.0 unit of any already-known one.
	static constexpr std::uint32_t kSnapCensusMax = 8;
	float snapCensus[kSnapCensusMax][3] = {};
	std::uint32_t snapCensusCount = 0;
	std::uint64_t snapCensusNew = 0;
	std::uint64_t snapCensusLogged = 0;"""

H_OLD = """	std::uint64_t snapNonCamera = 0;
	std::uint64_t snapSkipsSinceCam = 0;"""

CPP_CENSUS = """		const float pz = a_src.CameraPosAdjust[2];

		// ---- v1.14 probe: a census of the WRITERS -- who writes this buffer, and
		// does any of them MOVE?  Purely additive and placed BEFORE the gate, so it
		// sees the whole cast.
		// The 19:39 run proved the v1.13 gate works (the orthographic writer is
		// dropped 13,804 times, cap=13804/0) but the published camera stayed
		// byte-identical for the whole 11.4 s world session.  "The player was
		// standing still" and "we are locked on a parked camera" call for two very
		// different repairs, and only a census of the actual writers separates
		// them: if snapCensusNew stays at 2-3 for a whole session, NO writer moves
		// and the source itself has to change.
		{
			bool known = false;
			for (std::uint32_t i = 0; i < snapCensusCount && !known; ++i) {
				known = (std::fabs(snapCensus[i][0] - px) +
				         std::fabs(snapCensus[i][1] - py) +
				         std::fabs(snapCensus[i][2] - pz)) < 1.0f;
			}
			if (!known) {
				if (snapCensusCount < kSnapCensusMax) {
					snapCensus[snapCensusCount][0] = px;
					snapCensus[snapCensusCount][1] = py;
					snapCensus[snapCensusCount][2] = pz;
					++snapCensusCount;
				}
				++snapCensusNew;
				if (snapCensusLogged < 80u) {
					++snapCensusLogged;
					SKSE::log::info("[CAM] WRITER #{} NEW pos=({:.3f},{:.3f},{:.3f}) proj00={:.6g} "
						"row3_2={:.6g} row3_3={:.6g} prevPos=({:.3f},{:.3f},{:.3f}) arr#{}",
						snapCensusNew, px, py, pz,
						a_src.CameraProj.data[0][0],
						a_src.CameraProj.data[3][2], a_src.CameraProj.data[3][3],
						a_src.CameraPreviousPosAdjust[0], a_src.CameraPreviousPosAdjust[1],
						a_src.CameraPreviousPosAdjust[2], snapArrivals);
				}
			}
		}

		const bool usable"""

CPP_OLD = """		const float pz = a_src.CameraPosAdjust[2];
		const bool usable"""

FMT_OLD = '"fMove={:.1f} takeover={} stalePub={} cap={}/{} | {}",'
FMT_NEW = '"fMove={:.1f} takeover={} stalePub={} cap={}/{} cen={}/{} | {}",'

ARGS_OLD = "snapNonCamera, snapSkipsSinceCam,"
ARGS_NEW = "snapNonCamera, snapSkipsSinceCam, snapCensusNew, snapCensusCount,"

EDITS = [
    ("FrameGen.h members", HDR, H_OLD, H_MEMBERS),
    ("FrameGen.cpp census block", CPP, CPP_OLD, CPP_CENSUS),
    ("FrameGen.cpp pub format", CPP, FMT_OLD, FMT_NEW),
    ("FrameGen.cpp pub args", CPP, ARGS_OLD, ARGS_NEW),
]


def eol_of(path: pathlib.Path) -> bytes:
    """Decide the EOL from the FILE, never from the anchor."""
    raw = path.read_bytes()
    crlf = raw.count(b"\r\n")
    bare = raw.count(b"\n") - crlf
    return b"\r\n" if crlf >= bare else b"\n"


def main() -> int:
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if apply and revert:
        print("REFUSED: --apply and --revert are mutually exclusive")
        return 1

    src = {}
    eol = {}
    for p in (CPP, HDR):
        src[p] = p.read_bytes().decode("utf-8")
        eol[p] = eol_of(p)
        raw = p.read_bytes()
        crlf = raw.count(b"\r\n")
        bare = raw.count(b"\n") - crlf
        print(f"  {p.name}: CRLF {crlf} bareLF {bare} -> eol {eol[p]!r}")

    if revert:
        # revert must be PER PATH -- edit 0 lives in FrameGen.h, edits 1..3 in
        # FrameGen.cpp.  Applying them all to one buffer refuses on the first edit.
        work = {CPP: src[CPP], HDR: src[HDR]}
        # undo in reverse order, per file
        for name, path, old, new in reversed(EDITS):
            e = eol[path].decode()
            new_n = new.replace("\n", e)
            old_n = old.replace("\n", e)
            t = work[path]
            if t.count(new_n) != 1:
                print(f"REFUSED (revert): anchor for {name} appears {t.count(new_n)}x, want 1")
                return 1
            work[path] = t.replace(new_n, old_n)
        CPP.write_bytes(work[CPP].encode("utf-8"))
        HDR.write_bytes(work[HDR].encode("utf-8"))
        print("REVERTED src/FrameGen.cpp + src/FrameGen.h")
        return 0

    # --- idempotency guard: "anchor appears once" != "the patch never ran" ---
    for p in (CPP, HDR):
        if MARKER in src[p]:
            print(f"REFUSED, nothing written: marker already present in {p.name}")
            return 1

    counts = []
    for name, path, old, new in EDITS:
        # ★ the eol comes from the FILE, never from the anchor: the payload is
        #   written with "\n" for readability but these files are pure CRLF, so a
        #   raw count would report 0 for every multi-line anchor.
        old_n = old.replace("\n", eol[path].decode())
        n = src[path].count(old_n)
        counts.append((name, path, n))
        print(f"  count={n}  {name}  ({path.name})")
    bad = [name for name, _p, n in counts if n != 1]
    if bad:
        print(f"REFUSED, nothing written: non-unique anchors: {bad}")
        return 1

    if not apply:
        print("DRY RUN OK (nothing written) -- 4/4 anchors unique")
        print("  re-run with --apply to write")
        return 0

    for name, path, old, new in EDITS:
        t = src[path]
        # splice guard: normalise the payload to the FILE's eol before matching
        old_n = old.replace("\n", eol[path].decode())
        new_n = new.replace("\n", eol[path].decode())
        if t.count(old_n) != 1:
            print(f"FAIL: after eol normalisation {name} appears {t.count(old_n)}x, want 1")
            return 2
        src[path] = t.replace(old_n, new_n)

    # --- post-conditions on the RESULT text ---
    cpp, hdr = src[CPP], src[HDR]
    probes = [
        ("cpp: census marker once", cpp.count(MARKER), 1),
        ("hdr: census marker once", hdr.count(MARKER), 1),
        ("cpp: WRITER log line once", cpp.count("WRITER #{} NEW pos="), 1),
        ("cpp: snapCensusNew++ once", cpp.count("++snapCensusNew;"), 1),
        ("cpp: bound respected", cpp.count("snapCensusCount < kSnapCensusMax"), 1),
        ("hdr: table declared once", hdr.count("float snapCensus[kSnapCensusMax][3] = {};"), 1),
        ("cpp: fmt has cen once", cpp.count("cap={}/{} cen={}/{}"), 1),
        ("cpp: args have census once", cpp.count("snapNonCamera, snapSkipsSinceCam, snapCensusNew, snapCensusCount,"), 1),
        # ★ assert on DECLARATIONS, not identifiers: the new comments legitimately
        #   mention the v1.13 identifier names, so a raw identifier count is wrong.
        ("cpp: gate declaration untouched", cpp.count("const bool camShaped ="), 1),
        ("cpp: escape hatch untouched", cpp.count("if (snapSkipsSinceCam < kCamCaptureFallbackSkips)"), 1),
    ]
    fails = [f"{n}: got {g}, want {w}" for n, g, w in probes if g != w]
    if fails:
        print("FAIL post-conditions:\n  " + "\n  ".join(fails))
        return 2

    for p in (CPP, HDR):
        out = src[p].encode("utf-8")
        crlf, bare = out.count(b"\r\n"), out.count(b"\n") - out.count(b"\r\n")
        want_bare = 0 if eol[p] == b"\r\n" else bare
        if eol[p] == b"\r\n" and bare != 0:
            print(f"FAIL: {p.name} gained {bare} bare LF (must stay pure CRLF)")
            return 2
        print(f"  wrote {p.name}: CRLF {crlf} bareLF {bare}")

    for p in (CPP, HDR):
        p.write_bytes(src[p].encode("utf-8"))
    print("APPLIED (4/4 edits)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
