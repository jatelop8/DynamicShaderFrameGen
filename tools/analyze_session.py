#!/usr/bin/env python3
"""
One-command triage for a DynamicShaderFrameGen session.

Reads the two files the plugin writes and answers the only question that
matters after a run: did the present path over-submit, did something block,
and was the camera actually moving?

    python tools/analyze_session.py

Both files are written fresh each launch, so this always describes the LAST
run. Everything it prints is a number taken from the log, with the line it
came from. It does not guess.

Checks, in the order a freeze is actually built:

  1. REFLEX CAP     capFps * multiplier must be <= panel refresh.
                    The 21:27 run had 159 x 4 = 636 against a 160Hz panel -
                    a 4x over-submit, which is what a freeze looks like from
                    the inside. v1.06 restored the divisor that makes this 39.

  2. PRESENT BLOCK  the watchdog's presentAge is the age of the timestamp
                    taken when Present was entered. Milliseconds = healthy.
                    The 19:16 run sat at 19400ms.

  3. GPU PROGRESS   fence completed/submitted. Equal and climbing = moving.
                    fence=1/1 for 50 seconds is the v0.73 signature of a
                    device that never advanced.

  4. CAMERA MOTION  clipDev is max|I - clipToPrevClip|. It is > 0 exactly
                    when the camera moved between the two frames. A walking
                    player with clipDev pinned at 0.000061 means DLSS-G was
                    told the camera was still, and every generated frame is a
                    copy of the last real one.
                    camPrev(ok/used) must also be non-zero once v1.06's
                    history writer has run.
                    READ THIS WITH clipW, NOT ALONE. clipDev grows with camera
                    speed AND with frame interval, so on a slow run a large
                    clipDev is expected and a small one is not proof of health.
                    The 23:10 run alternated between 0.000023 and 28.77 on
                    consecutive heartbeats; that alternation is the signature
                    of the v1.07c defect, not of a fast camera.

  4b. clipW         clipToPrevClip[3].w. A clip-to-clip reprojection matrix is
                    affine, so its last row is (tx,ty,tz,1) and this must read
                    1.000000. Unlike clipDev it does NOT grow with frame time,
                    which makes it the only absolute camera-side criterion
                    here. A w away from 1 means the inverse of `cur` and the
                    `prev` matrix were NOT built from a consistent camera pair.
                    NOTE: the v1.07c edit that was supposed to fix this is a
                    NO-OP on the live path (chapter 17, machine-checked), so a
                    non-1 w here is still UNEXPLAINED. Section 4c is what
                    decides it.

  4c. p00(c/p)      The two sides' PROJECTION [0][0], the same family
                    fingerprint the source-lock uses (0.149 world / 0.839 menu,
                    5.62x apart). Read from the projection, not ViewProj,
                    because (P@V)[0][0] = P[0][0]*V[0][0] would mix in the
                    rotation. [2][3] is the perspective/orthographic
                    discriminator. This is the reading that separates the two
                    surviving explanations of a w away from 1:
                      (a) different families on the two sides -> p00 differs,
                          and the ratio is a projection ratio, not a translation;
                      (b) same projection, near-singular inverse -> p00 agrees
                          while mag(invSrc) is absurd.
                    Also watch p00 over time: if it FLIPS between two values
                    while the player is in the world, the menu camera is still
                    taking turns owning the stream.

  5. MULTIPLIER     mult(acc/pres) is (dlssgAcceptedFrames+1)/presented. The
                    two must agree; the pacer is told to expect `pres` flips
                    and the runtime must be delivering them.
"""

import re
import sys
from pathlib import Path

DFG = Path(r"C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log")
WD = Path(r"C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.watchdog.log")

# Optional overrides, so the offline regressions can push a SYNTHETIC log
# through the very same reading logic instead of a re-implementation of it
# (tools/regress_v108_p00.py does exactly that):
#     python tools/analyze_session.py --log D:\tmp\synthetic.log
#     python tools/analyze_session.py --log A --watchdog B
_args = sys.argv[1:]
for _i, _a in enumerate(_args):
    if _i + 1 >= len(_args):
        continue
    if _a == "--log":
        DFG = Path(_args[_i + 1])
    elif _a == "--watchdog":
        WD = Path(_args[_i + 1])

VERDICT_OK = "OK"
VERDICT_BAD = "PROBLEM"
VERDICT_UNKNOWN = "NO DATA"


def read(p: Path) -> str:
    if not p.exists():
        return ""
    return p.read_bytes().replace(b"\x00", b"").decode("utf-8", "replace")


def tail_lines(text: str, n: int) -> list:
    lines = [l for l in text.splitlines() if l.strip()]
    return lines[-n:]


def last_match(text: str, pattern: str):
    ms = re.findall(pattern, text)
    return ms[-1] if ms else None


def main() -> int:
    dfg = read(DFG)
    wd = read(WD)

    if not dfg and not wd:
        print("Neither log exists. Has the game been run with the plugin loaded?")
        print(f"  {DFG}")
        print(f"  {WD}")
        return 2

    problems = []

    # The watchdog is append-only and spans EVERY launch, so each check below
    # must work on the last run only. A run starts at frames=1; the final such
    # line begins the current one. Judging the whole file would keep reporting
    # the 19:16 hang on every future run - the mistake this block prevents.
    wlines = [l for l in wd.splitlines() if "presentAge=" in l]
    start = 0
    for i, l in enumerate(wlines):
        if re.search(r"frames=1\b", l):
            start = i
    recent_wd = wlines[start:]

    print("=" * 74)
    print("DynamicShaderFrameGen session triage")
    print("=" * 74)

    # ---- which build wrote this ------------------------------------------
    # Every check below assumes the shipped build. Saying WHICH build wrote the
    # log used to be informational only; the 22:02 run was analysed against the
    # wrong assumption more than once, so it is now a hard comparison.
    # The regex has to accept a letter suffix: v1.02c and v1.07b both exist.
    # v1.08 added a build tag to the banner: "(probe build, compiled ...)". The
    # literal "\(compiled" stopped matching, and the failure was the worst kind:
    # the tool printed "no [XRAY] banner at all" and appended it to `problems`,
    # i.e. a successful load was reported as a failure. Accept an optional
    # prefix, and keep one capture group so m[1] stays "compiled <when>".
    EXPECTED_BUILD = "v1.08"
    m = last_match(dfg, r"\[XRAY\] diag active (v[\d.a-z]+) \((?:[^)]*?)compiled ([^)]+)\)")
    if m:
        print(f"\nbuild            {m[0]}  compiled {m[1]}")
        if m[0] != EXPECTED_BUILD:
            print(f"   {VERDICT_BAD}: this log was written by {m[0]}, not "
                  f"{EXPECTED_BUILD}. Check the DLL actually in "
                  f"E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/ - the "
                  f"checks below describe {EXPECTED_BUILD}, not {m[0]}.")
            problems.append(f"log written by {m[0]}, expected {EXPECTED_BUILD}")
    else:
        print("\nbuild            (no [XRAY] banner found)")
        print(f"   {VERDICT_BAD}: no banner at all - either the plugin never "
              f"reached its first log line, or this predates the banner")
        problems.append("no [XRAY] banner in the log")

    # ---- 1. reflex cap ---------------------------------------------------
    print("\n1. REFLEX CAP")
    cap = re.findall(
        r"Reflex FLIP cap = (\d+) fps \((\d+)us\) - panel ([\d.]+)Hz, (\d+) flips per real frame => ~(\d+) presented fps",
        dfg)
    if cap:
        fps, us, panel, mult, presented = cap[-1]
        fps, us, mult, presented = int(fps), int(us), int(mult), int(presented)
        panel = float(panel)
        print(f"   capFps={fps}  frameLimitUs={us}  panel={panel}Hz  mult={mult}x"
              f"  => {presented} present fps")
        if presented > panel:
            pct = 100.0 * (presented - panel) / panel
            print(f"   {VERDICT_BAD}: over-submit {pct:.0f}% - the present queue"
                  f" backs up and the picture stops advancing")
            problems.append(f"reflex cap over-submits by {pct:.0f}%")
        else:
            print(f"   {VERDICT_OK}: {panel - presented:.0f} fps of headroom under the panel")
        over = re.findall(r"Reflex cap OVER-SUBMIT[^\n]*", dfg)
        if over:
            print(f"   self-check lines: {len(over)}  (v1.06 assertion fired)")
    else:
        print(f"   {VERDICT_UNKNOWN}: no 'Reflex FLIP cap' line."
              f" Either the run never reached frame generation or ReflexFpsLimit was set by hand.")
        problems.append("no reflex cap line")

    # ---- 2. present blocking --------------------------------------------
    print("\n2. PRESENT")
    if recent_wd:
        # The FIRST sample of a run is not a Present measurement. presentAge is
        # `now - g_presentEnteredMs`, and before the first frame Present has
        # never been entered, so the field measures "time since the plugin
        # initialised" - i.e. the loading screen. The 22:02 run's first sample
        # reads frames=1 silent=19196ms presentAge=19199ms, which is 19.2s of
        # loading, and the very next sample is frames=4 presentAge=14ms.
        # Judging it reports "Present blocked for 19199ms - a real hang" on a
        # run whose render loop never stalled once. Same class of error as the
        # three fixed in v1.06: a statistic that cannot mean what it is read as.
        boot = [l for l in recent_wd
                if not re.search(r"frames=1\b", l)]
        recent_wd = boot if boot else recent_wd
        recent_txt = "\n".join(recent_wd)
        ages = [int(m) for m in re.findall(r"presentAge=(-?\d+)ms", recent_txt)]
        frames = [int(m) for m in re.findall(r"frames=(\d+)", recent_txt)]
        all_ages = [int(m) for m in re.findall(r"presentAge=(-?\d+)ms", wd)]
        # `silent` counts ms since the previous frame. While the game is not
        # focused it does not render, so the pre-focus stretch reports tens of
        # seconds and means nothing. Requiring the PREVIOUS sample to be focused
        # as well is what excludes the single focus=1 line that announces the
        # transition: the 21:27 file has exactly one such line, stage=enter
        # frames=2 silent=21031ms, and it carried the whole pre-focus wait.
        focused = []
        prev_focused = False
        for l in recent_wd:
            is_focused = "focus=1" in l
            if is_focused and prev_focused:
                focused.append(l)
            prev_focused = is_focused
        silents = [int(m) for m in re.findall(r"silent=(\d+)ms", "\n".join(focused))]
        unfocused_drop = len(recent_wd) - len(focused)
        print(f"   last run: samples={len(recent_wd)} (focused={len(focused)},"
              f" before-focus dropped={unfocused_drop})  frames {frames[0]} -> {frames[-1]}")
        print(f"   presentAge max={max(ages)}ms   silent max while focused="
              f"{max(silents) if silents else 0}ms")
        if len(all_ages) > len(ages) and max(all_ages) > max(ages):
            print(f"   (earlier runs in this file reached presentAge={max(all_ages)}ms"
                  f" - not counted)")
        if max(ages) > 1000:
            print(f"   {VERDICT_BAD}: Present was entered and did not return for"
                  f" {max(ages)}ms - a real hang, not a stale picture")
            problems.append(f"Present blocked for {max(ages)}ms")
        elif max(silents) > 1000:
            print(f"   {VERDICT_BAD}: {max(silents)}ms with no frame progress")
            problems.append(f"render loop stalled {max(silents)}ms")
        else:
            print(f"   {VERDICT_OK}: the render loop never stalled")
    else:
        print(f"   {VERDICT_UNKNOWN}: watchdog has no presentAge field"
              f" (build older than v1.04b?)")

    # ---- 3. gpu progress -------------------------------------------------
    print("\n3. GPU PROGRESS")
    fences = re.findall(r"fence=(\d+)/(\d+)", "\n".join(recent_wd))
    if fences:
        first = tuple(map(int, fences[0]))
        last = tuple(map(int, fences[-1]))
        print(f"   fence {first[0]}/{first[1]} -> {last[0]}/{last[1]}")
        if last[0] == last[1] and last[0] - first[0] < 10:
            print(f"   {VERDICT_BAD}: the fence barely advanced - the device is stuck")
            problems.append("GPU fence not advancing")
        else:
            print(f"   {VERDICT_OK}: submitted==completed and both climbed"
                  f" (+{last[0] - first[0]})")
    else:
        print(f"   {VERDICT_UNKNOWN}: no fence field")

    # ---- 4. camera motion -----------------------------------------------
    print("\n4. CAMERA MOTION")
    hb = re.findall(r"\[XRAY\].*?clipDev=([-\d.]+).*?cam\(ok/inv\)=(\d+)/(\d+)"
                    r".*?camPrev\(ok/used\)=(\d+)/(\d+)", dfg)
    if hb:
        n = min(3, len(hb))
        print(f"   last {n} heartbeats (clipDev, cam ok/inv, camPrev ok/used):")
        for row in hb[-n:]:
            print(f"     clipDev={row[0]}  cam={row[1]}/{row[2]}  camPrev={row[3]}/{row[4]}")
        cd = [float(r[0]) for r in hb]
        camprev_ok = int(hb[-1][3])
        print(f"   clipDev: min={min(cd):.6f} max={max(cd):.6f} last={cd[-1]:.6f}")
        # ---- was the camera actually MOVING while those heartbeats were taken? --
        # A clipDev of exactly 0 is the CORRECT answer when the camera is still:
        # the identity is what "player did not move" is supposed to look like.
        # Without this check the 07:37 run was reported as "identity for the WHOLE
        # session", which reads exactly like the worst freeze, when in truth all
        # eight heartbeats were taken AFTER the player stopped walking.
        # The camera's real travel lives in the [CAM] acc lines, which the
        # heartbeat does not carry - so the two have to be joined on time.
        # Use move= (snapAcceptDist: the step from the previously accepted
        # sample, i.e. INSTANTANEOUS) and NOT path= (snapPathLen: a running sum).
        # A cumulative counter is monotonically increasing, so "path > 0" stays
        # true forever and the window swallows the whole rest of the log - the
        # first version of this check did exactly that and reported 8/8.
        acc = re.findall(r"\[(\d\d:\d\d:\d\d)(?:\.\d+)?\].*?\[CAM\] acc #\d+ "
                         r"pos=\([^)]*\) move=([\d.]+) path=([\d.]+)", dfg)
        hbt = re.findall(r"\[(\d\d:\d\d:\d\d)(?:\.\d+)?\].*?\[XRAY\] serial=\d+"
                         r".*?clipDev=([-\d.]+)", dfg)
        t_mov_lo = t_mov_hi = None
        in_win = []
        if acc:
            moving = [(t, float(m)) for t, m, _ in acc if float(m) > 0.001]
            t_mov_lo = moving[0][0] if moving else None
            t_mov_hi = moving[-1][0] if moving else None
            print(f"   camera travel ([CAM] acc): {float(acc[-1][2]):.2f} units total"
                  + (f", moving between {t_mov_lo} and {t_mov_hi}" if moving
                     else " - the captured camera never moved"))
            if moving:
                in_win = [float(v) for t, v in hbt if t_mov_lo <= t <= t_mov_hi]
                print(f"   heartbeats inside the moving window: {len(in_win)}"
                      f" of {len(hbt)}")
        # The metric to judge is the LAST heartbeat, not the maximum. A run can
        # show real translation early and then pin at identity for good - the
        # 21:27 log does exactly that (max=243.96, final three 0.000061), and a
        # max() test calls it healthy. That is the mistake this comment marks.
        if max(cd) <= 1.0e-4:
            if t_mov_lo is None:
                print(f"   {VERDICT_UNKNOWN}: clipDev is 0 on every heartbeat AND the"
                      f" camera never moved - that is the correct answer, not a"
                      f" finding. This run says nothing about the freeze.")
                problems.append("camera never moved - run does not test anything")
            elif not in_win:
                print(f"   {VERDICT_UNKNOWN}: clipDev is 0 on every heartbeat, but not"
                      f" one heartbeat falls inside the moving window"
                      f" ({t_mov_lo}..{t_mov_hi}). A still camera is SUPPOSED to give"
                      f" identity, so this run cannot tell a freeze from a standstill."
                      f" Walk first, then keep walking while the heartbeats fire.")
                problems.append("no heartbeat during camera movement - run does not test the freeze")
            else:
                print(f"   {VERDICT_BAD}: clipToPrevClip was the identity for the WHOLE"
                      f" session - DLSS-G was told the camera never moved, so every"
                      f" generated frame is a copy of the last real one")
                problems.append("clipToPrevClip pinned at identity for the whole run")
        elif cd[-1] <= 1.0e-4:
            print(f"   {VERDICT_BAD}: translation was reaching clipToPrevClip early"
                  f" (max={max(cd):.3f}) but the LAST heartbeat is back at identity"
                  f" ({cd[-1]:.6f}). The camera stopped being updated while the run"
                  f" continued - late-session freeze. Compare the frame numbers of"
                  f" the first identity heartbeat against when 4x started in the"
                  f" Transfusion log.")
            problems.append("clipToPrevClip fell back to identity late in the run")
        else:
            print(f"   {VERDICT_OK}: translation reaches clipToPrevClip at the end"
                  f" of the run too")
        if camprev_ok == 0:
            print(f"   {VERDICT_BAD}: camPrev(ok)=0 - the v1.02c history has no writer"
                  f" (fixed in v1.06; a 0 here means the fix is not loaded)")
            problems.append("camPrev history never populated")
        else:
            print(f"   {VERDICT_OK}: camPrev history is live (ok={camprev_ok})")

        # ---- 4b. clipW ---------------------------------------------------
        # The one camera-side criterion that does not grow with frame time.
        cw = re.findall(r"clipW=([-\d.]+)", dfg)
        if cw:
            w = float(cw[-1])
            print(f"   clipW (clipToPrevClip[3].w, must be 1.000000): "
                  f"last={w:.6f}  n={len(cw)}")
            if abs(w - 1.0) > 0.01:
                print(f"   {VERDICT_BAD}: w={w:.6f} - the two sides do not form a"
                      f" consistent camera pair, so DLSS-G is reprojecting with a"
                      f" non-affine matrix. NOTE: the v1.07c invert-site edit is a"
                      f" NO-OP on the live src=fixed path (chapter 17;"
                      f" tools/verify_v107c_is_inert.py), so this is NOT"
                      f" explained yet - section 4c decides between the two"
                      f" remaining candidates.")
                problems.append("clipToPrevClip[3].w is not 1 - non-affine reprojection")
            else:
                print(f"   {VERDICT_OK}: affine, [3].w == 1")

        # ---- 4c. p00(c/p): the projections on the two sides (v1.08 probe) ---
        # Decides (a) two different families vs (b) one projection, singular
        # inverse. Without this field the question is not answerable from a log.
        pp = re.findall(r"p00\(c/p\)=([-\d.]+)/([-\d.]+)", dfg)
        mo = re.findall(
            r"PROBE: p00 cur=([-\d.eE+]+) prev=([-\d.eE+]+) \| p23 cur=([-\d.eE+]+) "
            r"prev=([-\d.eE+]+) \| mag invSrc=([-\d.eE+]+) prevSrc=([-\d.eE+]+)", dfg)
        if pp:
            cur = [float(a) for a, _ in pp]
            prv = [float(b) for _, b in pp]
            # CAREFUL: this probe reads CameraProj (c8). The family lock reads
            # ProjUnj (c40), and those are NOT the same matrix - on the 07:37
            # run c8 read 1.1250 while the lock reported 0.888889, i.e. the two
            # are exact reciprocals. So a p00 here can only be compared with
            # another p00 from this same probe; it must never be read against
            # the 0.149184 / 0.8391 family table.
            print(f"   p00 (CameraProj c8 [0][0] - NOT the family-lock ProjUnj c40): "
                  f"cur min/max={min(cur):.4f}/{max(cur):.4f}  "
                  f"prev min/max={min(prv):.4f}/{max(prv):.4f}  n={len(pp)}")
            distinct = sorted({round(v, 3) for v in cur})
            if len(distinct) >= 2:
                lo2, hi2 = distinct[0], distinct[-1]
                ratio = (hi2 / lo2) if lo2 > 0 else 0.0
                print(f"   p00 takes {len(distinct)} distinct values "
                      f"({lo2:.4f} .. {hi2:.4f}, ratio {ratio:.2f}x)")
                if ratio > 1.15:
                    print(f"   {VERDICT_BAD}: the projection family SWITCHES during"
                          f" the run - two cameras are still taking turns on the"
                          f" stream even though the player is in the world")
                    problems.append("projection family switches mid-run (p00)")
                else:
                    print(f"   {VERDICT_OK}: single family (the spread is <15%)")
            else:
                print(f"   {VERDICT_OK}: p00 is one family ({distinct[0]:.4f})")
            mism = sum(1 for a, b in zip(cur, prv) if b != 0.0 and abs(a / b - 1.0) > 0.02)
            print(f"   cur/prev projection agreement: {len(pp) - mism}/{len(pp)}"
                  f" within 2%")
            if mism:
                print(f"   {VERDICT_BAD}: {mism} heartbeat(s) have the two sides on"
                      f" DIFFERENT projections -> explanation (a) for a bad clipW")
        else:
            print(f"   {VERDICT_UNKNOWN}: no p00(c/p) field - this build predates"
                  f" the v1.08 probe, so (a) vs (b) cannot be decided")
        if mo:
            c0f, p0f = float(mo[-1][0]), float(mo[-1][1])
            c23, p23, m1, m2 = mo[-1][2], mo[-1][3], mo[-1][4], mo[-1][5]
            print(f"   [MOTION] non-affine frame: p00 cur={c0f:.4f} prev={p0f:.4f} |"
                  f" p23 cur={c23} prev={p23} | mag invSrc={m1} prevSrc={m2}")
            if p0f != 0.0 and abs(c0f / p0f - 1.0) > 0.02:
                print(f"   -> explanation (a): the two sides carry DIFFERENT"
                      f" projections (ratio {c0f / p0f:.4f}); the 5.62x world/menu"
                      f" family ratio is the candidate")
            else:
                print(f"   -> explanation (b): the projections AGREE, so the culprit"
                      f" is the inverse itself (mag(invSrc)={m1}) - a near-singular"
                      f" invCurrViewProj")
        else:
            print(f"   {VERDICT_OK}: no [MOTION] non-affine warning in this run")

        # The v1.07c fingerprint: clipDev alternating between ~0 and absurd.
        if len(cd) >= 4:
            # 0.0 <= v is not decoration: clipDev is max|I - clip|, so it cannot
            # be negative, but the parse now accepts a leading '-' (it has to --
            # a negative reading is itself a finding). Without the lower bound a
            # bogus -195 would be counted as an "identity" sample and would
            # manufacture an alternation out of nothing.
            lo = [v for v in cd if 0.0 <= v <= 1.0e-4]
            hi = [v for v in cd if v > 10.0]
            neg = [v for v in cd if v < 0.0]
            if neg:
                print(f"   {VERDICT_BAD}: clipDev is NEGATIVE on {len(neg)}"
                      f" heartbeat(s) (min={min(neg):.6f}). clipDev is"
                      f" max|I - clipToPrevClip|, which cannot be negative, so the"
                      f" reading itself is broken on those frames - every threshold"
                      f" below is meaningless there.")
                problems.append("clipDev reads negative - the metric itself is broken")
            if lo and hi:
                print(f"   {VERDICT_BAD}: clipDev alternates between identity"
                      f" ({len(lo)} samples <=1e-4) and absurd ({len(hi)} samples"
                      f" >10) in the SAME run. DLSS-G is being told 'still' then"
                      f" 'moved hundreds of units', frame by frame - the picture"
                      f" cycles back and forth. The 23:10 run had this with"
                      f" max=243.96 and it is STILL UNEXPLAINED: the invert-site"
                      f" edit in v1.07c changes nothing on the live path"
                      f" (chapter 17). Section 4c is the reading that decides it.")
                problems.append("clipDev alternates identity <-> absurd")
    else:
        print(f"   {VERDICT_UNKNOWN}: no [XRAY] heartbeat lines")

    # ---- 5. multiplier ---------------------------------------------------
    print("\n5. MULTIPLIER")
    mm = re.findall(r"mult\(acc/pres\)=(\d+)/(\d+)", dfg)
    if mm:
        acc, pres = map(int, mm[-1])
        # Both fields are printed as dlssgAcceptedFrames+1 and presentedPrev,
        # i.e. already TOTAL multipliers: 4 means 4x = 1 real + 3 generated.
        print(f"   accepted={acc}x  presented={pres}x  (total multipliers:"
              f" 4 = 1 real + 3 generated)")
        if acc != pres:
            print(f"   {VERDICT_BAD}: the pacer is told to expect {pres} flips but the"
                  f" runtime accepted {acc} - the two disagree")
            problems.append(f"multiplier mismatch acc={acc} pres={pres}")
        else:
            print(f"   {VERDICT_OK}: request and confirmation agree")
    else:
        print(f"   {VERDICT_UNKNOWN}: no mult() field")

    mv = last_match(dfg, r"mfg\(hwMax/reqMax/rungsSkipped\)=(\d+)/(\d+)/(\d+)")
    if mv:
        print(f"   mfg(hwMax/reqMax/rungsSkipped)={mv[0]}/{mv[1]}/{mv[2]}")

    # ---- 6. camera family lock (v1.07) -----------------------------------
    # `proj00` in the heartbeat is snapLockProj00 (Streamline.cpp:1371) - the
    # projection fingerprint of the family that currently OWNS the stream, not
    # the fingerprint of the arrival being examined. The two known families are
    # 0.149184 (world) and 0.8391 (3D menu), 5.62x apart. If the world is being
    # rendered (worldFrames climbing) and the lock still reads 0.8391, DLSS-G is
    # being handed a camera for a world that is gone - which is a frozen picture
    # with a live frame counter.
    print("\n6. CAMERA FAMILY LOCK")
    lk = re.findall(
        r"lock\(pub/hold/re/still\)=(\d+)/(\d+)/(\d+)/(\d+) proj00=([\d.eE+-]+) famRej=(\d+)",
        dfg)
    if lk:
        pub, hold, re_, still, proj00, famrej = lk[-1]
        wm = re.findall(r"menu=(\d+) world=(\d+)", dfg)
        menu_frames = int(wm[-1][0]) if wm else 0
        world_frames = int(wm[-1][1]) if wm else 0
        print(f"   lock(pub/hold/re/still)={pub}/{hold}/{re_}/{still}"
              f"  proj00={proj00}  famRej={famrej}")
        print(f"   worldFrames at the end of the run: {world_frames}"
              f"  (menuFrames={menu_frames})")
        rel = re.findall(r"\[CAM\] #\d+ lock RELEASED[^\n]*", dfg)
        print(f"   release events: {len(rel)}")
        for r in rel[:4]:
            print(f"     {r}")
        p = float(proj00)
        if world_frames > 60 and abs(p - 0.8391) < 0.01:
            print(f"   {VERDICT_BAD}: the lock is on the MENU family (proj00={proj00})"
                  f" while the world is being rendered ({world_frames} world frames)."
                  f" The world camera is arriving and being refused - famRej={famrej}."
                  f" clipToPrev cannot move, so the picture is frozen.")
            problems.append("camera lock is on the menu family during world frames")
        elif world_frames > 60 and abs(p - 0.149184) < 0.01:
            print(f"   {VERDICT_OK}: the world family owns the lock (proj00={proj00})")
        else:
            print(f"   {VERDICT_UNKNOWN}: proj00={proj00} is neither known family,"
                  f" or the run never reached the world"
                  f" (worldFrames={world_frames})")
        # v1.07b: heavy family refusals are HEALTHY while the world family owns
        # the lock - that is the v1.00 invariant doing its job, and the count is
        # only how many times the menu/unit passes were turned away. It is a
        # problem only when the lock sits on a foreign family AND no release ever
        # fired, because a release fires at every menu open/close edge. The old
        # form of this check required still==0, which was true only in v1.06
        # where that counter was never incremented; in v1.07b it counts.
        if int(famrej) > 50 and abs(p - 0.149184) < 0.01:
            print(f"   {VERDICT_OK}: {famrej} refusals with the world family holding"
                  f" the lock - foreign families turned away, as intended")
        if (int(famrej) > 50 and len(rel) == 0
                and menu_frames > 0 and world_frames > 60):
            print(f"   {VERDICT_BAD}: {famrej} refusals and a menu->world transition"
                  f" (menu={menu_frames} world={world_frames}) but 0 releases."
                  f" v1.07b+ raises the release at that edge - is {EXPECTED_BUILD}"
                  f" the build actually loaded?")
            problems.append("reset-edge release never fired across a menu->world transition")
    else:
        print(f"   {VERDICT_UNKNOWN}: no lock(...) field"
              f" (build older than v1.00?)")

    # ---- summary ---------------------------------------------------------
    print("\n" + "=" * 74)
    if problems:
        print("RESULT: PROBLEMS FOUND")
        for p in problems:
            print(f"  - {p}")
    else:
        print("RESULT: no over-submit, no stall, no frozen camera in this session")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
