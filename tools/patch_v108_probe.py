#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
v1.08 PROBE -- instrument only, no behaviour change.

Goal: one run must be able to decide between the two surviving explanations of

    clipToPrevClip[3].w = -195.222366      (23:10 run, Transfusion [MOTION] dump)

  (a) the inverse side and the `prev` side carry DIFFERENT projections
      (a curve/menu camera against the world camera) -> inv(Pc@Vc)@(Pp@Vp) is
      not affine at all and [3].w is free to be any finite number. The known
      family ratio is 0.149 (world) / 0.839 (menu) = 5.62x, which does NOT
      produce -195, so this explanation needs a stronger mismatch than the
      known pair.

  (b) both sides share the projection, but matrixFullInvert() was handed a
      near-singular matrix and the elements blew up. Then the projections
      MATCH and only the inverse's magnitude is huge.

The probe therefore records, right where clipToPrevClip is finished:

    probeCurP00 / probePrevP00    the two projections' [0][0] -- the same
                                  family fingerprint the source-lock uses.
                                  Read from the PROJECTION, not from ViewProj,
                                  because (P@V)[0][0] = P[0][0]*V[0][0] would
                                  mix in the rotation and jitter every frame.
    probeCurP23 / probePrevP23    the perspective/orthographic discriminator:
                                  0 for an orthographic projection, non-zero
                                  for a perspective one. Independent of
                                  orientation, so it survives a camera spin.
    probeInvSrcMag                finiteMagOf(invCurrViewProj) -- a
                                  near-singular inverse shows up here as an
                                  absurd magnitude, which is (b)'s signature.
    probePrevSrcMag               finiteMagOf(prevForReproj), the scale the
                                  inverse is being multiplied against.

TRAP THIS PATCH AVOIDS: s_prevCamProj is OVERWRITTEN with this frame's value
at line 750, long before the reprojection site at line 1202. Reading it there
would return the CURRENT frame's projection and the comparison would be
vacuous -- the same "both sides identical, so the gate can never fire" mistake
as v1.02c. Hence the explicit snapshot (s_probePrevProj) taken BEFORE the
overwrite.

Dry run by default; pass --apply to write. Every anchor must occur exactly
once or the script refuses and writes nothing.
"""
import io
import sys
import hashlib

CPP = "src/Streamline.cpp"
HDR = "src/Streamline.h"

# Both files are pure CRLF as measured by tools/snapshot.sh on 2026-09-19 00:04
# (Streamline.cpp: CRLF=2298 LF=0). The LF note in MEMORY.md is stale.
def to_crlf(s: str) -> bytes:
    return s.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


# ---------------------------------------------------------------- Streamline.h
H1_OLD = """			float clipW = 1.0f;
"""

H1_NEW = """			float clipW = 1.0f;
			// ---- v1.08 PROBE (instrument only) ----------------------------
			// The two projections' [0][0], i.e. the family fingerprint the
			// source-lock already uses (0.149 world / 0.839 menu), read from
			// the PROJECTION and not from ViewProj: (P@V)[0][0] is P[0][0]
			// times V[0][0] and would mix in the rotation.
			//
			// [2][3] is the perspective/orthographic discriminator -- exactly
			// 0 for an orthographic projection, non-zero for a perspective
			// one -- so a 3D-menu (curve/ortho) camera facing a world camera
			// shows up in BOTH numbers at once, independently of orientation.
			//
			// probeInvSrcMag is finiteMagOf(invCurrViewProj): a near-singular
			// inverse blows up here, which is the competing explanation for
			// clipToPrevClip[3].w = -195.22.
			float probeCurP00 = 0.0f;
			float probePrevP00 = 0.0f;
			float probeCurP23 = 0.0f;
			float probePrevP23 = 0.0f;
			float probeInvSrcMag = 0.0f;
			float probePrevSrcMag = 0.0f;
"""

# ---------------------------------------------------------------- Streamline.cpp
# C1: declare the snapshot holders next to the history they shadow.
C1_OLD = """		static bool s_hasPrevCam = false;
"""

C1_NEW = """		static bool s_hasPrevCam = false;
		// v1.08 PROBE: the previous frame's projection, captured BEFORE the
		// block below overwrites s_prevCamProj with this frame's value.
		static Matrix s_probePrevProj{};
		static bool s_probeHasPrevProj = false;
"""

# C2: take the snapshot first, then let the history advance as before.
C2_OLD = """		if (camCurOk) {
			s_prevCamView = a_fb.CameraView;
"""

C2_NEW = """		if (camCurOk) {
			// v1.08 PROBE: snapshot the OLD projection before the line below
			// replaces it. Reading s_prevCamProj at the reprojection site
			// returns this frame's value, which would make the probe vacuous.
			if (s_hasPrevCam) {
				s_probePrevProj = s_prevCamProj;
				s_probeHasPrevProj = true;
			}
			s_prevCamView = a_fb.CameraView;
"""

# C3: record the readings where clipToPrevClip is complete.
C3_OLD = """		diag.clipW = c.clipToPrevClip[3].w;
"""

C3_NEW = """		diag.clipW = c.clipToPrevClip[3].w;
		// ---- v1.08 PROBE --------------------------------------------------
		//
		// Everything below is READ-ONLY. It exists so that one run can decide
		// between the two surviving explanations of clipToPrevClip[3].w != 1:
		//
		//   (a) the inverse side and the prev side carry different
		//       projections. Then inv(Pc@Vc)@(Pp@Vp) is not affine and [3].w
		//       is free. Signature: probeCurP00 != probePrevP00 (or the [2][3]
		//       pair disagreeing), i.e. the two sides are different families.
		//   (b) both sides share the projection and matrixFullInvert() was
		//       handed a near-singular matrix. Signature: probeCurP00 ==
		//       probePrevP00 while probeInvSrcMag is absurd.
		//
		// Reading the projection (not ViewProj) is deliberate: (P@V)[0][0]
		// equals P[0][0]*V[0][0], so a ViewProj-level fingerprint would mix in
		// the rotation and change every frame the player turns.
		diag.probeCurP00 = a_fb.CameraProj.data[0][0];
		diag.probeCurP23 = a_fb.CameraProj.data[2][3];
		if (s_probeHasPrevProj) {
			diag.probePrevP00 = s_probePrevProj.data[0][0];
			diag.probePrevP23 = s_probePrevProj.data[2][3];
		}
		diag.probeInvSrcMag = finiteMagOf(invCurrViewProj);
		diag.probePrevSrcMag = finiteMagOf(prevForReproj);
"""

# C4: the non-affine warning now carries the probe, so a single grep of
#     [MOTION] answers the question without correlating across lines.
C4_OLD = """				SKSE::log::warn("[MOTION] clipToPrevClip[3].w={:.6f} (must be 1) - "
					"the inverse and the previous matrix came from different "
					"cameras; DLSS-G is reprojecting with a non-affine matrix",
					diag.clipW);
"""

C4_NEW = """				SKSE::log::warn("[MOTION] clipToPrevClip[3].w={:.6f} (must be 1) - "
					"the inverse and the previous matrix came from different "
					"cameras; DLSS-G is reprojecting with a non-affine matrix. "
					"v1.08 PROBE: p00 cur={:.4f} prev={:.4f} | p23 cur={:.6f} "
					"prev={:.6f} | mag invSrc={:.4g} prevSrc={:.4g}",
					diag.clipW, diag.probeCurP00, diag.probePrevP00,
					static_cast<double>(diag.probeCurP23),
					static_cast<double>(diag.probePrevP23),
					static_cast<double>(diag.probeInvSrcMag),
					static_cast<double>(diag.probePrevSrcMag));
"""

# C5: heartbeat format string -- two short fields, right after clipW.
C5_OLD = """					"clipDev={:.6f} clipW={:.6f} curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) "
"""

C5_NEW = """					"clipDev={:.6f} clipW={:.6f} p00(c/p)={:.4f}/{:.4f} curVP={:.4f} prevVP={:.4f} | pos=({:.1f},{:.1f},{:.1f}) "
"""

# C6: matching heartbeat arguments.
C6_OLD = """					Get().jitterX, Get().jitterY, clipDev, diag.clipW, devOf(curVP), devOf(prevVP),
"""

C6_NEW = """					Get().jitterX, Get().jitterY, clipDev, diag.clipW,
					diag.probeCurP00, diag.probePrevP00, devOf(curVP), devOf(prevVP),
"""

# C7: banner.
C7_OLD = """				SKSE::log::info("[XRAY] diag active v1.07c (compiled " __DATE__ " " __TIME__ ")");
"""

C7_NEW = """				SKSE::log::info("[XRAY] diag active v1.08 (probe build, compiled " __DATE__ " " __TIME__ ")");
"""


EDITS = [
    (HDR, "H1 diag fields", H1_OLD, H1_NEW),
    (CPP, "C1 snapshot decl", C1_OLD, C1_NEW),
    (CPP, "C2 snapshot take", C2_OLD, C2_NEW),
    (CPP, "C3 probe readings", C3_OLD, C3_NEW),
    (CPP, "C4 warn carries probe", C4_OLD, C4_NEW),
    (CPP, "C5 heartbeat fmt", C5_OLD, C5_NEW),
    (CPP, "C6 heartbeat args", C6_OLD, C6_NEW),
    (CPP, "C7 banner", C7_OLD, C7_NEW),
]

# Idempotence guards: phrases that only exist AFTER the patch has run.
GUARDS = [
    (HDR, "v1.08 PROBE (instrument only)"),
    (CPP, "s_probeHasPrevProj"),
    (CPP, "diag.probeCurP00"),
    (CPP, "diag active v1.08"),
]


def sha1b(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def main() -> int:
    apply = "--apply" in sys.argv
    texts = {}
    for path in (CPP, HDR):
        texts[path] = io.open(path, "rb").read()

    print("== guards (must all be ABSENT) ==")
    for path, marker in GUARDS:
        n = texts[path].count(marker.encode("utf-8"))
        print("  %-22s %-34s count=%d" % (path, marker, n))
        if n != 0:
            print("REFUSED: already patched (%s)" % marker)
            return 2

    print("== anchors (must all be EXACTLY 1) ==")
    ok = True
    for path, label, old, new in EDITS:
        c = texts[path].count(to_crlf(old))
        flag = "OK " if c == 1 else "!! "
        print("  %s%-24s %-34s count=%d" % (flag, path, label, c))
        if c != 1:
            ok = False
    if not ok:
        print("REFUSED, nothing written")
        return 3

    print("== dry run: all anchors unique, all guards absent ==")
    if not apply:
        print("(no --apply: nothing written)")
        return 0

    before = {p: sha1b(texts[p]) for p in texts}
    for path, label, old, new in EDITS:
        b = texts[path]
        ob, nb = to_crlf(old), to_crlf(new)
        assert b.count(ob) == 1, label
        texts[path] = b.replace(ob, nb)

    for path, _ in ((CPP, 0), (HDR, 0)):
        out = texts[path]
        io.open(path, "wb").write(out)
        print("  wrote %-22s %d -> %d B  sha1 %s -> %s"
              % (path, len(io.open(path, "rb").read()), len(out), before[path][:12], sha1b(out)[:12]))

    # ---- post-conditions, checked on the RESULT text (see MEMORY.md) --------
    print("== post-conditions ==")
    cpp = texts[CPP].decode("utf-8")
    hdr = texts[HDR].decode("utf-8")
    checks = [
        ("C++: probe fields declared", "float probeCurP00 = 0.0f;" in hdr),
        ("C++: snapshot taken before overwrite",
         cpp.index("s_probePrevProj = s_prevCamProj;") < cpp.index("s_prevCamProj = a_fb.CameraProj;")),
        ("C++: readings present", "diag.probeInvSrcMag = finiteMagOf(invCurrViewProj);" in cpp),
        ("C++: heartbeat has p00", "p00(c/p)={:.4f}/{:.4f}" in cpp),
        ("C++: heartbeat args match", "diag.probeCurP00, diag.probePrevP00, devOf(curVP)" in cpp),
        ("C++: banner v1.08", 'diag active v1.08' in cpp),
        ("C++: warn carries 7 args",
         cpp.count("static_cast<double>(diag.probePrevSrcMag));") == 1),
        ("C++: no LF-only line left", b"\n" not in texts[CPP].replace(b"\r\n", b"")),
        ("HDR: no LF-only line left", b"\n" not in texts[HDR].replace(b"\r\n", b"")),
    ]
    bad = 0
    for name, cond in checks:
        print("  %s %s" % ("OK " if cond else "FAIL", name))
        if not cond:
            bad += 1
    print("RESULT: %s" % ("OK" if bad == 0 else "%d FAILED" % bad))
    return 0 if bad == 0 else 4


if __name__ == "__main__":
    sys.exit(main())
