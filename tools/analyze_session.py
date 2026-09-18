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

  5. MULTIPLIER     mult(acc/pres) is (dlssgAcceptedFrames+1)/presented. The
                    two must agree; the pacer is told to expect `pres` flips
                    and the runtime must be delivering them.
"""

import re
import sys
from pathlib import Path

DFG = Path(r"C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.log")
WD = Path(r"C:\Users\Administrator\Documents\My Games\Skyrim Special Edition\SKSE\DynamicShaderFrameGen.watchdog.log")

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
    m = last_match(dfg, r"\[XRAY\] diag active (v[\d.]+) \(compiled ([^)]+)\)")
    if m:
        print(f"\nbuild            {m[0]}  compiled {m[1]}")
    else:
        print("\nbuild            (no [XRAY] banner found)")

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
    hb = re.findall(r"\[XRAY\].*?clipDev=([\d.]+).*?cam\(ok/inv\)=(\d+)/(\d+)"
                    r".*?camPrev\(ok/used\)=(\d+)/(\d+)", dfg)
    if hb:
        n = min(3, len(hb))
        print(f"   last {n} heartbeats (clipDev, cam ok/inv, camPrev ok/used):")
        for row in hb[-n:]:
            print(f"     clipDev={row[0]}  cam={row[1]}/{row[2]}  camPrev={row[3]}/{row[4]}")
        cd = [float(r[0]) for r in hb]
        camprev_ok = int(hb[-1][3])
        print(f"   clipDev: min={min(cd):.6f} max={max(cd):.6f} last={cd[-1]:.6f}")
        # The metric to judge is the LAST heartbeat, not the maximum. A run can
        # show real translation early and then pin at identity for good - the
        # 21:27 log does exactly that (max=243.96, final three 0.000061), and a
        # max() test calls it healthy. That is the mistake this comment marks.
        if max(cd) <= 1.0e-4:
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
