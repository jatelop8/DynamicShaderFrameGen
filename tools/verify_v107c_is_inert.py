#!/usr/bin/env python3
"""Is v1.07c inert?  Pure Python, no dependencies.  Read-only.

v1.07c's only functional change was the SOURCE of the inverse:

    - sl::matrixFullInvert(invCurrViewProj, curForReproj);
    + const sl::float4x4& reprojInvSrc = camCurOk ? camCurVP : curForReproj;
    + sl::matrixFullInvert(invCurrViewProj, reprojInvSrc);

That only does something if `camCurVP != curForReproj`.  In the run the
diagnosis came from (23:10, v1.07b) the heartbeat logged `reproj src=fixed`,
i.e. useFixed == true, i.e. curForReproj == fixedViewProj.

PART A  are the two matrix builders the same construction?
          camCurVP      <- rebuildViewProj(a_fb.CameraView, a_fb.CameraPosAdjust, a_fb.CameraProj)
          fixedViewProj <- inline block, same three inputs
        If yes, camCurVP == fixedViewProj bit for bit -> v1.07c changes nothing.

PART B  does the inverse source matter at all?
        B1  with the SAME P on both sides: inv(P@A) @ (P@B) == inv(A) @ B
        B2  what v1.07c moved (should be exactly 0 if A == B)
        B3  what it takes to get a NON-AFFINE result (the -195.22 in the dump)
"""
import hashlib
import io
import re
import sys

SRC = "src/Streamline.cpp"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def strip_comments(text):
    return re.sub(r"//[^\n]*", "", text)


def normalize(block):
    """Reduce a builder to its semantic skeleton: no comments, no whitespace,
    no NaN guard, no return, and with the call-site ARGUMENTS folded into the
    lambda's parameters (the caller passes a_fb.CameraPosAdjust for a_eye and
    a_fb.CameraProj for a_proj -- without folding those in, the two blocks look
    different when they are not)."""
    b = strip_comments(block)
    lines = []
    for line in b.splitlines():
        s = line.strip()
        if not s:
            continue
        if s in ("return false;", "return true;", "};"):
            continue
        if s.startswith("if (!(m0 ") or s.startswith("if (!(m1 ") or s.startswith("if (!(m2 "):
            continue                        # the NaN guard only exists in the lambda
        if re.match(r"const float m[012] = ", s):
            continue                        # lambda-only aliases, folded in below
        lines.append(s)
    b = "\n".join(lines)

    # fold the call-site bindings and unify every name
    for a, z in (("a_fb.CameraPosAdjust", "SRCEYE"), ("a_fb.CameraProj", "SRCPROJ"),
                 ("a_fb.CameraView", "SRCVIEW"),
                 ("a_eye", "SRCEYE"), ("a_proj", "SRCPROJ"), ("a_view", "SRCVIEW"),
                 ("vw", "SRCVIEW"), ("a_out", "DST"), ("fixedViewProj", "DST")):
        b = re.sub(r"\b%s\b" % re.escape(a), z, b)

    # fold the lambda's m0/m1/m2 aliases back into their expressions
    b = re.sub(r"\bm0\b", "SRCVIEW.data[r][0]", b)
    b = re.sub(r"\bm1\b", "SRCVIEW.data[r][1]", b)
    b = re.sub(r"\bm2\b", "SRCVIEW.data[r][2]", b)

    b = re.sub(r"sl::float4x4\s+\w+\{\}", "DECL", b)
    b = re.sub(r"sl::float4x4\s+\w+", "DECL", b)
    b = re.sub(r"\bfiniteMag\([^)]*\)\s*>\s*1\.0e-6f", "FINITE", b)
    b = b.replace(".data", "")              # engine Matrix -> its raw array
    b = re.sub(r"\s+", " ", b)
    return b.strip()


def main():
    text = io.open(SRC, "r", encoding="utf-8").read()
    ok = True

    lam_raw = text[text.index("auto rebuildViewProj = [&]"):]
    lam_raw = lam_raw[:lam_raw.index("return true;")]
    lam_raw = lam_raw[lam_raw.index("const float ex"):]

    fix_raw = text[text.index("sl::float4x4 fixedViewProj{};"):]
    fix_raw = fix_raw[:fix_raw.index("fixedViewProjOk = finiteMag")]
    fix_raw = fix_raw[fix_raw.index("const float ex"):]

    nl, nf = normalize(lam_raw), normalize(fix_raw)

    print("=== A. same construction? ===")
    print(f"  rebuildViewProj  {len(nl):4d} chars  sha1 {hashlib.sha1(nl.encode()).hexdigest()[:12]}")
    print(f"  fixedViewProj    {len(nf):4d} chars  sha1 {hashlib.sha1(nf.encode()).hexdigest()[:12]}")
    same = (nl == nf)
    print(f"  identical: {'YES' if same else 'NO'}")
    if not same:
        import difflib
        for d in difflib.unified_diff(nl.split(), nf.split(), "rebuildViewProj", "fixedViewProj",
                                      lineterm="", n=2):
            print("   ", d)
        ok = False

    call = re.search(r"rebuildViewProj\((.*?),\s*camCurVP\)", text, re.S)
    args = re.sub(r"\s+", "", call.group(1)) if call else "?"
    print(f"  rebuildViewProj inputs: {args}")
    print(f"  inline block inputs:    a_fb.CameraView, a_fb.CameraPosAdjust, a_fb.CameraProj"
          f"   {'(same)' if args == 'a_fb.CameraView,a_fb.CameraPosAdjust,a_fb.CameraProj' else '(DIFFERENT!)'}")
    if args != "a_fb.CameraView,a_fb.CameraPosAdjust,a_fb.CameraProj":
        ok = False

    # ----------------------------------------------------------------------
    print()
    rnd = 12345

    def nextf():
        nonlocal rnd
        rnd = (1103515245 * rnd + 12345) & 0x7FFFFFFF
        return (rnd / 0x7FFFFFFF) * 2.0 - 1.0

    def mul(A, B):
        return [[sum(A[i][k] * B[k][j] for k in range(4)) for j in range(4)] for i in range(4)]

    def invert(M):
        n = 4
        a = [r[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, r in enumerate(M)]
        for c in range(n):
            p = max(range(c, n), key=lambda r: abs(a[r][c]))
            if abs(a[p][c]) < 1e-14:
                return None
            a[c], a[p] = a[p], a[c]
            pv = a[c][c]
            a[c] = [x / pv for x in a[c]]
            for r in range(n):
                if r != c and a[r][c] != 0.0:
                    f = a[r][c]
                    a[r] = [a[r][k] - f * a[c][k] for k in range(2 * n)]
        return [r[n:] for r in a]

    def rot():
        m = [[0.0] * 4 for _ in range(4)]
        m[3][3] = 1.0
        R = [[nextf() for _ in range(3)] for _ in range(3)]
        for i in range(3):
            for j in range(i):
                d = sum(R[i][k] * R[j][k] for k in range(3))
                for k in range(3):
                    R[i][k] -= d * R[j][k]
            nm = sum(R[i][k] ** 2 for k in range(3)) ** 0.5
            for k in range(3):
                R[i][k] /= nm
        for r in range(3):
            for c in range(3):
                m[r][c] = R[r][c]
        return m

    def view(R, eye):
        V = [r[:] for r in R]
        for r in range(3):
            V[r][3] = -sum(R[r][k] * eye[k] for k in range(3))
        V[3] = [0.0, 0.0, 0.0, 1.0]
        return V

    def persp(scale=1.0):
        P = [[0.0] * 4 for _ in range(4)]
        P[0][0], P[1][1] = 1.6 * scale, 0.9 * scale
        P[2][2] = scale / (1.0 - 100000.0)
        P[2][3] = -100000.0 * scale / (1.0 - 100000.0)
        P[3][2], P[3][3] = -1.0 * scale, 0.0
        return P

    def diff(A, B):
        return max(abs(A[i][j] - B[i][j]) for i in range(4) for j in range(4))

    eye = [-243.05, -415.31, 118.56]
    P = persp()
    worst = 0.0
    for _ in range(200):
        R1, R2 = rot(), rot()
        A, B = mul(P, view(R1, eye)), mul(P, view(R2, eye))
        got = mul(invert(A), B)
        want = mul(invert(view(R1, eye)), view(R2, eye))
        worst = max(worst, diff(got, want))

    print("=== B1. same P on both sides ===")
    print(f"  max |inv(P@A)@(P@B)  -  inv(A)@B| = {worst:.3e}   over 200 random rotation pairs")
    print("  => the shared projection cancels exactly; which P-carrying matrix you invert")
    print("     is irrelevant, as long as prev carries the SAME projection.")
    if worst > 1e-8:
        ok = False

    print()
    print("=== B2. what v1.07c actually moved ===")
    R1, R2 = rot(), rot()
    old_invsrc = mul(P, view(R1, eye))      # curForReproj  (= fixedViewProj, useFixed)
    new_invsrc = mul(P, view(R1, eye))      # camCurVP      (same construction, part A)
    prev = mul(P, view(R2, eye))
    d = diff(mul(invert(old_invsrc), prev), mul(invert(new_invsrc), prev))
    print(f"  |old_result - new_result| = {d:.3e}")
    print("  (0 by construction: part A proves the two inputs are the same matrix,")
    print("   so re-pointing the inverse at the other one cannot change any output.)")

    print()
    print("=== B3. what it takes to get a NON-AFFINE result ===")
    print("  The engine's projection is NOT affine: [3][3] = 0.0666667 (FLD c40),")
    print("  so the product carries a projection-scale factor in [3][3].")
    for k in (1.0, 0.5, 2.0, -195.22):
        A = mul(persp(), view(rot(), eye))
        B = mul(persp(k), view(rot(), eye))
        prod = mul(invert(A), B)
        print(f"    prev's projection scaled by k = {k:>+8.2f}  ->  row3[3] = {prod[3][3]:+12.6f}")
    print()
    print("  => row3[3] of the result is a RATIO between the two projections.")
    print("     Same P on both sides -> exactly 1. Different P -> anything.")
    print("     The 5.62x world/menu family ratio seen in the logs would give")
    print("     row3[3] ~ 5.62 or 0.178 -- NOT the -195.22 in Transfusion's dump.")
    print("     So the observed value is still UNEXPLAINED by this mechanism.")
    print()
    print("=== C. path enumeration: where can the change do anything at all? ===")
    print("  old inv-src: curForReproj        = useFixed ? fixedViewProj : currViewProjSL")
    print("  new inv-src: camCurOk ? camCurVP : curForReproj")
    print("  part A says camCurVP == fixedViewProj, so:")
    print()
    rows = [
        ("useFixed=true,  camCurOk=true ", "fixedViewProj", "camCurVP",
         "same matrix -> NO EFFECT"),
        ("useFixed=true,  camCurOk=false", "fixedViewProj", "curForReproj=fixedViewProj",
         "same matrix -> NO EFFECT"),
        ("useFixed=false, camCurOk=true ", "currViewProjSL", "camCurVP",
         ">>> THE ONLY PATH THAT CHANGES <<<"),
        ("useFixed=false, camCurOk=false", "currViewProjSL", "curForReproj=currViewProjSL",
         "same matrix -> NO EFFECT"),
    ]
    print(f"  {'case':32s} {'old':18s} {'new':26s} verdict")
    for a, b, c, d in rows:
        print(f"  {a:32s} {b:18s} {c:26s} {d}")
    print()
    print("  useFixed == fixedViewProjOk == finiteMag(fixedViewProj) > 1e-6.")
    print("  The 23:10 run logged `reproj src=fixed` -> reprojSource==2 -> useFixed==true.")
    print("  => the change was inert in the very run it was derived from, and stays inert")
    print("     on every non-degenerate frame. It is armed only when the rebuild fails.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
