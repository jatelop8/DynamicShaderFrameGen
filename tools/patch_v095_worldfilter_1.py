"""v0.95 -- structural world-camera filter (replaces the distance/continuity gate).

Byte-level patcher with line-ending adaptivity.

LINE ENDINGS (measured, not assumed -- an earlier note claimed FrameGen.h was
pure CRLF; it is not):
    FrameGen.cpp   CRLF=0    LF=1282   (pure LF)
    Streamline.cpp CRLF=0    LF=1822   (pure LF)
    FrameGen.h     CRLF=304  LF=323    (MIXED -- historical patches)

So this patcher works on bytes, never rewrites a line it did not touch, and
gives every inserted line the ending of the anchor line it sits next to.

THE DIAGNOSIS (from the 16:04 crash log, 848 Unmap calls / 14.8 s)
------------------------------------------------------------------
The engine writes the perFrame constant buffer TWICE per frame; both writes
reach the Unmap hook.

    per-call member pattern:  'MW' 768, 'M' 39, 'W' 39, 'WM' 1, 'MMMW' 1
    M = UI/menu camera : magVP = devVP = 1.11111, pos constant (-160,160,128)
    W = world camera   : magVP = devVP = 15.011,  pos moves smoothly

Separated, the world stream is continuous (WORLD->WORLD step median 0.000; only
2 of 808 steps exceed 5 units). Interleaved, the sequence alternates on almost
every arrival (run length 1 for 98% of samples), which is why every
continuity/distance gate from v0.67 to v0.94 failed -- it was judging two
interleaved streams as one.

The last call before the crash had FOUR members and v0.93 published all four:

    t=57844.874 n=4: (-694,528,111) | (-952,886,103) | (-126,211,189) | (-243,-415,119)
                     ^-------- all mag=1.1111 (UI) ---------^          ^ mag=15.001 (world)

Consecutive generated frames reprojected from cameras hundreds of units apart.
That is the CTD.

THE FIX: filter on magnitude, which is a property of what the matrix MEANS
----------------------------------------------------------------------------
A world view-projection encodes the player's world position, hundreds of units
from the origin, so its coefficients are large. A UI camera rendering a flat
overlay stays near the origin, so its matrix stays near identity. Threshold 3.0
replayed over the whole log:

    809 calls with exactly 1 world member
      0 calls with more than 1
     39 calls with none  -- each isolated (run length 1), all inside the first
                            39 frames of the load

Valley check: [1.5, 13.0) contains ONE sample in the entire log (magVP=2.0001,
the degenerate (0,0,1) matrix), so the threshold has orders of magnitude of
headroom and cannot flip on a scene change -- unlike the distance gate, which
did not survive teleports.

BOOTSTRAP. The 39 starved calls are during the load, where there is no world
camera. Rejecting a UI camera there is correct (publishing it would be the
crash), but mappedFrameBuffer must not stay null: SetMappedFrameBuffer() runs
only on accept, so a permanent rejection would leave GetFrameBuffer() null and
Present would skip SetDLSSGOptions entirely. So until the first world camera is
EVER seen, the first arrival of each call is adopted. The window closes after a
few dozen frames.
"""
import sys
from pathlib import Path

CPP = Path(r"D:/Modding/DynamicShaderFrameGen/src/FrameGen.cpp")
HDR = Path(r"D:/Modding/DynamicShaderFrameGen/src/FrameGen.h")


def endings(data: bytes):
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n")
    return crlf, lf


def tail_before(data: bytes, idx: int) -> bytes:
    """The line ending that terminates the line containing byte idx-1."""
    j = idx - 1
    while j >= 0 and data[j:j+1] not in (b"\r", b"\n"):
        j -= 1
    if j >= 0 and data[j:j+1] == b"\n" and j - 1 >= 0 and data[j-1:j] == b"\r":
        return b"\r\n"
    if j >= 0 and data[j:j+1] in (b"\r", b"\n"):
        return data[j:j+1]
    return b"\n"


def build():
    edits = []   # (label, path, old_bytes, new_lines(list of str), eol_source_index)

    # ---------------------------------------------------------------- FrameGen.h
    h = HDR.read_bytes()
    # The five state lines have MIXED endings (four LF, the last CRLF), so build
    # the byte anchor by joining the bare lines with whatever ending each one
    # actually carries in the file.
    h_lines_bare = [
        b"\t\tstd::uint64_t snapLockPublish = 0;    // arrivals published onto the stream",
        b"\t\tstd::uint64_t snapLockHold = 0;       // arrivals withheld (other source)",
        b"\t\tstd::uint64_t snapLockRelock = 0;     // times the stream was re-acquired",
        b"\t\tstd::uint32_t snapLockStill = 0;      // consecutive non-continuing arrivals",
        b"\t\tbool  snapLockHave = false;           // a stream is locked",
    ]
    j = h.find(h_lines_bare[0])
    if j < 0:
        return None, "header: first state line not found"
    k = j
    h_old_parts = []
    for ln in h_lines_bare:
        if h[k:k+len(ln)] != ln:
            return None, f"header: state line mismatch at {k}: {h[k:k+40]!r}"
        k += len(ln)
        if h[k:k+2] == b"\r\n":
            h_old_parts.append(ln + b"\r\n")
            k += 2
        elif h[k:k+1] == b"\n":
            h_old_parts.append(ln + b"\n")
            k += 1
        else:
            return None, f"header: no line ending after {ln[:30]!r}"
    h_old = b"".join(h_old_parts)
    if h.count(h_old) != 1:
        return None, f"header anchor count = {h.count(h_old)}"

    h_new_lines = [
        "		// v0.95: structural source filter.",
        "		//",
        "		// The engine writes the perFrame buffer twice per frame: a UI/menu",
        "		// camera (magVP ~ 1.11111) and the world camera (magVP ~ 15.011).",
        "		// Only the world camera may be published to DLSS-G; publishing both,",
        "		// or publishing a UI camera in place of the world one, reprojects",
        "		// generated frames from the wrong viewpoint and CTDs (v0.93).",
        "		//",
        "		// The two are told apart by matrix MAGNITUDE, which is a property of",
        "		// what the matrix means (a world view-projection encodes a position",
        "		// hundreds of units from the origin), not of where it currently",
        "		// points -- so it survives teleports, scene changes and loads.",
        "		std::uint64_t snapWorldAccepted = 0;   // published (world camera)",
        "		std::uint64_t snapUiSkipped = 0;       // ignored (UI/menu camera)",
        "		std::uint64_t snapBootstrap = 0;       // published before 1st world cam",
        "		bool  snapSawWorldCamera = false;      // a world camera has been seen",
    ]

    # Inserted lines go BEFORE the block, so match the ending of the first line
    # of the block itself (LF here), not of whatever precedes it.
    eol = b"\r\n" if h_old_parts[0].endswith(b"\r\n") else b"\n"
    new_h = eol.join(l.encode("utf-8") for l in h_new_lines) + eol
    edits.append(("hdr.world_filter_state", HDR, h_old, new_h))

    # -------------------------------------------------------------- FrameGen.cpp
    c = CPP.read_bytes()

    c1_old = b"\tconstexpr std::uint32_t kCamStillTol = 90;\n"
    if c.count(c1_old) != 1:
        return None, f"cpp const anchor count = {c.count(c1_old)}"
    c1_lines = [
        "",
        "	// v0.95: minimum view-projection magnitude that can be a world camera.",
        "	// Replay over the 16:04 log: the UI cluster sits at magVP = 1.11111",
        "	// (810 samples), the world cluster at 15.011 (809 samples), and the",
        "	// valley [1.5, 13.0) holds exactly ONE sample in the whole log",
        "	// (magVP = 2.0001, the degenerate (0,0,1) matrix). A world",
        "	// view-projection must encode a player position hundreds of units from",
        "	// the origin, so its coefficients are large; a UI overlay camera stays",
        "	// near the origin. 3.0 sits orders of magnitude clear of the valley.",
        "	constexpr float kWorldMagMin = 3.0f;",
    ]
    new_c1 = c1_old + eol.join(l.encode("utf-8") for l in c1_lines) + eol
    edits.append(("cpp.world_mag_const", CPP, c1_old, new_c1))

    # replace the v0.94 lock block (delimited by unique markers)
    start_marker = b"\t\t// ---- v0.94: source lock (replaces the distance gate) ------------------\n"
    end_marker = b"\t\t\t++snapLockPublish;\n\t\t}\n"
    i0 = c.find(start_marker)
    if i0 < 0:
        return None, "cpp: v0.94 lock start marker not found"
    i1 = c.find(end_marker, i0)
    if i1 < 0:
        return None, "cpp: v0.94 lock end marker not found"
    i1 += len(end_marker)
    block_old = c[i0:i1]

    block_lines = [
        "		// ---- v0.95: structural world-camera filter ----------------------------",
        "		//",
        "		// v0.67..v0.94 all tried to separate the two cameras by WHERE they are",
        "		// (distance) or HOW they move (continuity). Both fail here, because the",
        "		// two streams are interleaved arrival-by-arrival: on the 16:04 log the",
        "		// combined sequence has run length 1 for 98% of arrivals, and the two",
        "		// UI constants are 456 units apart, so no step-size test can prefer one",
        "		// of them -- which is exactly why v0.94 published only the constants",
        "		// and never the moving camera.",
        "		//",
        "		// The cameras ARE separable by WHAT THEIR MATRIX IS:",
        "		//",
        "		//     UI/menu  : magVP = devVP = 1.11111, pos = (-160,160,128), constant",
        "		//     world    : magVP = devVP = 15.011,  pos glides with the player",
        "		//",
        "		// A world view-projection encodes the player's world position, hundreds",
        "		// of units from the origin, so its coefficients are large. A UI camera",
        "		// drawing a flat overlay stays near the origin and near identity.",
        "		// Replay at threshold 3.0: 809 calls with exactly one world member,",
        "		// ZERO with more than one, and 39 with none -- each isolated (run",
        "		// length 1) and inside the first 39 frames of the load.",
        "		//",
        "		// v0.93 published every member of every call. The last call before the",
        "		// crash had four members, three of them UI and one world:",
        "		//",
        "		//     (-694,528,111) (-952,886,103) (-126,211,189) | (-243,-415,119)",
        "		//     ^--------------- all magVP=1.1111 (UI) ------^   ^ world ^",
        "		//",
        "		// so consecutive generated frames reprojected from cameras hundreds of",
        "		// units apart. That is the CTD this filter prevents.",
        "		const float srcMag = camMag(a_src.CameraViewProjUnjittered);",
        "		const bool isWorldCamera = (srcMag >= kWorldMagMin);",
        "",
        "		if (isWorldCamera) {",
        "			snapSawWorldCamera = true;",
        "			++snapWorldAccepted;",
        "		} else {",
        "			++snapUiSkipped;",
        "			// Not a world camera. Do NOT publish it, or DLSS-G reprojects the",
        "			// generated frames from a viewpoint that is not the player's.",
        "			// Returning false leaves mappedFrameBuffer untouched (it is not",
        "			// cleared), so the last good world camera stays in effect across",
        "			// the UI/menu passes that share the frame.",
        "			//",
        "			// Bootstrap: during the load no world camera exists yet, and a",
        "			// strict filter would leave mappedFrameBuffer null -- then",
        "			// GetFrameBuffer() is null and Present skips SetDLSSGOptions.",
        "			// Adopt the first arrival of each call until the first world",
        "			// camera is ever seen. Measured starvation is confined to the",
        "			// first 39 frames, so this window closes almost immediately.",
        "			if (!snapSawWorldCamera && snapAccept == 0u) {",
        "				++snapBootstrap;",
        "			} else {",
        "				if (snapUiSkipped <= 3u || (snapUiSkipped % 500u) == 0u) {",
        "					SKSE::log::info(\"[CAM] #{} skipped (not a world camera): \"",
        "						\"magVP={:.6g} magView={:.6g} pos=({:.1f},{:.1f},{:.1f}) \"",
        "						\"world accepted so far={}\",",
        "						snapArrivals, srcMag, camMag(a_src.CameraView),",
        "						px, py, pz, snapWorldAccepted);",
        "				}",
        "				return false;",
        "			}",
        "		}",
    ]
    new_block = eol.join(l.encode("utf-8") for l in block_lines) + eol
    edits.append(("cpp.world_filter_block", CPP, block_old, new_block))

    return edits, None


def main():
    apply = "--apply" in sys.argv
    print(f"mode: {'APPLY' if apply else 'DRY-RUN'}")

    for p in (CPP, HDR):
        crlf, lf = endings(p.read_bytes())
        print(f"  {p.name:16s} CRLF={crlf:5d} LF={lf:5d}")

    edits, err = build()
    if err:
        print("REFUSED, nothing written:")
        print("  -", err)
        return 1

    for label, path, old, new in edits:
        data = path.read_bytes()
        n = data.count(old)
        if n != 1:
            print(f"REFUSED, nothing written: {label} byte-anchor count = {n}")
            return 1

    # Apply ALL edits per file into ONE accumulated buffer. Using a dict keyed by
    # path silently dropped every edit but the last for the same file (two edits
    # to FrameGen.cpp, one overwrote the other) -- and the run still reported
    # success for both. Accumulate instead, and assert each new state grew.
    acc = {}
    for label, path, old, new in edits:
        data = acc.get(path, path.read_bytes())
        assert data.count(old) == 1, label
        acc[path] = data.replace(old, new, 1)
        print(f"  {'WROTE' if apply else 'WOULD WRITE'} {label}  (+{len(new)-len(old)} bytes)")

    if apply:
        for path, out in acc.items():
            before = path.read_bytes()
            bc, bl = endings(before)
            ac, al = endings(out)
            print(f"  {path.name}: CRLF {bc}->{ac} (d={ac-bc}), LF {bl}->{al} (d={al-bl})")
            path.write_bytes(out)

    if not apply:
        print("\n(dry run -- pass --apply to write)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
