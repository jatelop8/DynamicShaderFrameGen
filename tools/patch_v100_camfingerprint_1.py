# -*- coding: utf-8 -*-
"""
v1.00 - world-camera fingerprint lock for the source-lock.

ROOT CAUSE (evidence, 2026-09-18 16:42 run + DLSSG-Transfusion.log 07:29 run):

  The camera stream contains TWO families that both look "valid" to the
  current lock, and the lock has no way to tell them apart by distance:

    family WORLD  (the player camera)
        ViewProjUnjittered | -6.70312 0 0 0 | 0 -1.57495 11.8121 0 | ...
        ProjUnj            | 0.149184 ... | 0 0.0839162 ...      <- [0][0]=0.149184
        ViewInv            | -1 -0 -0 -0 | ...                    <- translation ZERO
        pos=(-50.0,600.0,80.0) / (-54.3,793.2,80.0) ... moves with the player

    family MENU   (a 3D menu / UI scene camera)
        ViewProjUnjittered | 1.19174 0.00466757 ... | ...
        ProjUnj            | 0.8391 ... | 0 0.471993 ...        <- [0][0]=0.8391
        ViewInv            | 0.999992 5.87483e-06 ... | ...        <- translation ZERO too
        pos=(-243.0493,-415.3115,118.5582)  CONSTANT for 9 s

  ProjUnj[0][0] differs by 5.62x between the two families (0.8391 / 0.149184).
  That ratio is the fingerprint: it does not depend on FOV, resolution or
  aspect (a resolution change moves BOTH families' [0][0] by the same factor
  only when the aspect changes; the projection KIND is what differs here).

  WHY THE CURRENT LOCK FAILS
  v0.94 rejects an arrival that does not "continue" the locked stream and
  counts it. After kCamStillTol (=90) consecutive non-continuing arrivals it
  assumes the locked stream died and RE-ACQUIRES -- snapHaveLast = false, so
  the NEXT arrival is adopted unconditionally.

  The MENU family arrives every frame, monotonically, for 9 seconds
  (36 logged acc lines, all byte-identical). So:
      frame 1   : MENU arrives, !continues (dist 1259 >> kCamStepTol 50)
      ... 90 frames ...
      frame 91  : kCamStillTol reached -> RE-ACQUIRE, snapHaveLast=false
      frame 92  : MENU adopted as the new stream, snapHaveLast=true
      frame 93+ : MENU continues MENU -> continues==true forever
  => the MENU camera owns frameBufferCopy permanently, and clipToPrevClip is
     built from inv(MENU_cur) x MENU_prev = I  => DLSS-G is told the camera is
     parked => generated frames are reprojected to one stale view => FREEZE.
     Only engine-native particles (fire) keep animating, which is exactly what
     the user sees.

  FIX
  1) Fingerprint the locked family by ProjUnj[0][0] (relative test, not an
     absolute threshold: accept only when the ratio to the LOCKED value is
     within +-2%, so no magic number is bound to this resolution/FOV).
  2) An arrival from a different projection family may NEVER re-acquire the
     lock, no matter how many times it arrives. Only an arrival from the SAME
     family may take over when the current stream is dead.
  3) Re-acquisition keeps its old ceiling for the same-family case (scene
     change / loading screen), so nothing that used to work stops working.

Post-patch invariants asserted by this script before writing:
  - every anchor matched exactly once
  - the removed 'snapHaveLast = false' re-acquire path is gone
  - the new family test is present
Run with --apply to write; without it, dry-run only.
"""
import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPP = os.path.join(ROOT, "src", "FrameGen.cpp")
HDR = os.path.join(ROOT, "src", "FrameGen.h")

APPLY = "--apply" in sys.argv

# ---------------------------------------------------------------- new code ----

NEW_MEMBERS = """	// ---- v1.00: world-camera fingerprint lock ----
	// The arrival stream carries two projection families that the distance
	// test cannot separate (see tools/patch_v100_camfingerprint_1.py header):
	//
	//   WORLD  ProjUnj[0][0] = 0.149184   (player camera, view translation 0)
	//   MENU   ProjUnj[0][0] = 0.8391     (3D menu / UI scene camera)
	//
	// 5.62x apart. The lock keeps the fingerprint of the family it accepted and
	// refuses to re-acquire onto a different family, which is what let the MENU
	// camera take over frameBufferCopy and freeze the picture.
	float snapLockProj00 = 0.0f;      // ProjUnj[0][0] of the locked family
	bool  snapLockProjValid = false;  // the fingerprint above is meaningful
	std::uint64_t snapLockFamilyRej = 0;  // arrivals refused for being another family
	std::uint64_t snapLockAdopted = 0;    // times a position snapshot was adopted
"""

# The replacement for the whole source-lock decision block. Anchors: the
# `const bool continues = ...` line and the closing `++snapLockPublish; }`.
OLD_DECIDE_HEAD = """			const bool continues = snapLockHave && snapHaveLast && (d2 <= kCamStepTol2);
			if (!snapLockHave) {"""

NEW_DECIDE_HEAD = """			// ---- v1.00: projection-family fingerprint ----
			// ProjUnj[0][0] identifies the projection kind. Compare it against the
			// family currently locked, with a RELATIVE tolerance so the test does
			// not depend on the resolution / FOV this run happens to use.
			const float proj00 = a_src.CameraProjUnjittered.data[0][0];
			const bool projOk = (proj00 == proj00) && (proj00 > 1.0e-6f);
			bool sameFamily = true;
			if (projOk && snapLockProjValid) {
				const float ratio = proj00 / snapLockProj00;
				// +-2%: the two real families sit 5.62x apart, so 2% separates them
				// with a ~280x margin while still tolerating float drift and a
				// resolution/FOV nudge.
				sameFamily = (ratio > 0.98f) && (ratio < 1.02f);
			}

			const bool continues = snapLockHave && snapHaveLast && (d2 <= kCamStepTol2);
			if (!snapLockHave) {"""

# Inside the !continues branch: the re-acquire must be gated on sameFamily.
OLD_RELOCK = """				++snapLockHold;
				if (++snapLockStill >= kCamStillTol) {
					// The locked stream has not continued for ~1.5 s at 60 Hz, so
					// it is dead (loading screen / scene change). Re-acquire on
					// this arrival and drop the stale anchor so the next test is
					// made against the new source rather than the old one.
					snapLockHave = true;
					snapLockStill = 0;
					++snapLockRelock;
					snapHaveLast = false;"""

NEW_RELOCK = """				++snapLockHold;
				// ---- v1.00: a different projection family may NEVER re-acquire ----
				// v0.94 re-acquired unconditionally after kCamStillTol non-continuing
				// arrivals, so a foreign camera that arrived monotonically for 90
				// frames was adopted and then "continued" itself forever. That is the
				// freeze. Only an arrival from the SAME family may take over.
				if (!sameFamily) {
					++snapLockFamilyRej;
					if (snapLockFamilyRej <= 3u || (snapLockFamilyRej % 500u) == 0u) {
						SKSE::log::info("[CAM] #{} family rejected: proj00={:.6g} locked={:.6g} "
							"ratio={:.4f} pos=({:.1f},{:.1f},{:.1f}) dist={:.1f} - another render "
							"pass, never re-acquires",
							snapArrivals, proj00, snapLockProj00,
							snapLockProjValid ? (proj00 / snapLockProj00) : 0.0f,
							px, py, pz, std::sqrt(d2));
					}
					if (d2 > kCamJumpTol2) ++snapRejectJump;
					return false;
				}
				if (++snapLockStill >= kCamStillTol) {
					// The locked stream has not continued for ~1.5 s at 60 Hz, so
					// it is dead (loading screen / scene change) AND the arrival
					// belongs to the same projection family. Re-acquire on this
					// arrival and drop the stale anchor so the next test is made
					// against the new source rather than the old one.
					snapLockHave = true;
					snapLockStill = 0;
					++snapLockRelock;
					snapHaveLast = false;"""

# On accept, refresh the fingerprint (the family in force) and count adopts.
OLD_ACCEPT = """		frameBufferCopy = a_src;
		++snapAccept;
		snapAcceptDist = snapHaveLast ? std::sqrt(d2) : 0.0f;"""

NEW_ACCEPT = """		frameBufferCopy = a_src;
		++snapAccept;
		// ---- v1.00: remember which family owns the stream ----
		if (projOk) {
			snapLockProj00 = proj00;
			snapLockProjValid = true;
		}
		snapAcceptDist = snapHaveLast ? std::sqrt(d2) : 0.0f;"""


def load(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def eol_of(text, anchor):
    """Line ending of the line that contains `anchor` (anchor must be LF-only)."""
    i = text.index(anchor)
    j = text.find("\n", i)
    if j < 0:
        return "\n"
    return "\r\n" if text[j - 1] == "\r" else "\n"


def apply_edit(text, label, old, new, newline):
    """Replace exactly one occurrence; assert the anchor is unique.

    `old` / `new` are written with plain LF in this file. They are converted to
    the file's own line ending FIRST, then matched. Conversion is skipped for a
    string that already contains CRLF (an anchor that carries its own EOL), so
    it is never turned into CRCRLF.
    """
    def conv(s):
        if "\r\n" in s:
            return s
        return s.replace("\n", "\r\n") if newline == "\r\n" else s

    old_c, new_c = conv(old), conv(new)
    n = text.count(old_c)
    if n != 1:
        print("REFUSED: anchor '%s' occurs %d times (must be exactly 1)" % (label, n))
        return None
    return text.replace(old_c, new_c)


def main():
    src = load(CPP)
    hdr = load(HDR)
    print("FrameGen.cpp %d bytes, FrameGen.h %d bytes" % (len(src), len(hdr)))

    # marker guard: has this patch already run?
    for marker in ("v1.00: projection-family fingerprint",
                   "snapLockFamilyRej",
                   "v1.00: world-camera fingerprint lock"):
        for name, text in (("FrameGen.cpp", src), ("FrameGen.h", hdr)):
            if marker in text:
                print("REFUSED: marker already present in %s (%r) - patch has run" % (name, marker))
                return 1

    eol_cpp = eol_of(src, OLD_DECIDE_HEAD)
    eol_hdr = eol_of(hdr, "\tbool  snapLockHave = false;")
    print("line endings: cpp=%r hdr=%r" % (eol_cpp, eol_hdr))

    orig_cpp, orig_hdr = src, hdr

    for label, old, new in (
        ("cpp/decide-head", OLD_DECIDE_HEAD, NEW_DECIDE_HEAD),
        ("cpp/relock-gate", OLD_RELOCK, NEW_RELOCK),
        ("cpp/accept-fingerprint", OLD_ACCEPT, NEW_ACCEPT),
    ):
        out = apply_edit(src, label, old, new, eol_cpp)
        if out is None:
            return 1
        src = out
        print("  ok: %s" % label)

    # header: members after snapLockHave. Anchor carries its own EOL so the
    # inserted block lands on the following line with the file's own line ending.
    anchor_hdr = "\tbool  snapLockHave = false;           // a stream is locked" + eol_hdr
    out = apply_edit(hdr, "hdr/members", anchor_hdr, anchor_hdr + NEW_MEMBERS, eol_hdr)
    if out is None:
        return 1
    hdr = out
    print("  ok: hdr/members")

    # ---- post-conditions ----
    # NOTE: `snapHaveLast = false;` legitimately survives inside the same-family
    # re-acquire branch. What must be gone is the *unguarded* form, i.e. the
    # `snapHaveLast = false;` line that directly follows `++snapLockRelock;`
    # with no family test in between. Check the shape of the new block instead.
    n_cpp = src.replace("\r\n", "\n")
    checks = [
        ("cpp: family test present", "v1.00: projection-family fingerprint" in n_cpp),
        ("cpp: family counters present", "snapLockFamilyRej" in n_cpp),
        ("cpp: family gate precedes relock",
         n_cpp.find("if (!sameFamily) {") > 0
         and n_cpp.find("if (!sameFamily) {") < n_cpp.find("if (++snapLockStill >= kCamStillTol)")),
        ("cpp: family gate lives inside !continues branch",
         n_cpp.find("} else if (!continues) {") < n_cpp.find("if (!sameFamily) {")),
        ("cpp: exactly one family-reject log", n_cpp.count("family rejected: proj00=") == 1),
        ("cpp: accept refreshes fingerprint", "snapLockProj00 = proj00;" in n_cpp),
        ("hdr: members present", "snapLockProj00" in hdr),
        ("hdr: family rej counter", "snapLockFamilyRej" in hdr),
        ("cpp: brace balance unchanged",
         src.count("{") - src.count("}") == orig_cpp.count("{") - orig_cpp.count("}")),
        ("cpp: line count grew", src.count("\n") > orig_cpp.count("\n")),
    ]
    ok = True
    for label, cond in checks:
        print("  %-42s %s" % (label, "PASS" if cond else "FAIL"))
        if not cond:
            ok = False

    if not ok:
        print("REFUSED: post-conditions failed, nothing written")
        return 1

    if not APPLY:
        print("\nDRY RUN - nothing written. Re-run with --apply")
        print("  FrameGen.cpp would grow %+d bytes" % (len(src) - len(orig_cpp)))
        print("  FrameGen.h   would grow %+d bytes" % (len(hdr) - len(orig_hdr)))
        return 0

    with io.open(CPP, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    with io.open(HDR, "w", encoding="utf-8", newline="") as f:
        f.write(hdr)
    print("\nAPPLIED: FrameGen.cpp %d -> %d bytes, FrameGen.h %d -> %d bytes"
          % (len(orig_cpp), len(src), len(orig_hdr), len(hdr)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
