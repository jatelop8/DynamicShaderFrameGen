#!/usr/bin/env python3
"""Offline regression for the v1.07 camera-family lock changes.

WHAT THIS MODELS
----------------
FrameGen.cpp's lock block in AcceptCameraSnapshot(), reduced to the parts that
decide which projection family owns frameBufferCopy:

    kCamStepTol   = 50        -> kCamStepTol2 = 2500
    kCamStillTol  = 90
    family test   : ratio in (0.98, 1.02)          [v1.07: and nothing else]
                    v1.03..v1.06 also admitted the arrival outright whenever
                    exactly one of the two projections was a unit projection

The three families are the ones the 22:02 log actually carried:

    A  proj00 = 0.149184  pos (-50,600,80)        -> glides, the world camera
    B  proj00 = 1.0       pos (-160,160,128)      -> constant, unit/orthographic
    C  proj00 = 0.8391    pos (-243,-415.3,118.6) -> the 3D-menu family; its
                          row3 (-0.00391655,0.999991,0.0015,0) is the matrix
                          FrameGen.h:326-332 calls "not a camera at all, but a
                          mis-offset read of the perFrame constant buffer"

v1.07 SHIPS TWO EDITS. A THIRD WAS WRITTEN, MEASURED, AND DISCARDED.
-------------------------------------------------------------------
This regression exists mainly to keep them from being confused, because only the
first one is what the 22:02 log was complaining about.

  1. DELETED the magnitude-class escape (v1.03).               <- LOAD-BEARING
     The 22:02 log opens with `#1 acquire proj00=0.149184`: the world camera won
     the very first adoption. Every later `esc ... -> adopt` line is the escape
     walking that lock onto B and then onto C. With the escape gone the lock
     never leaves A, so the observed failure cannot happen at all.
     C1 proves it: escape-deleted alone already ends on proj00=0.149184, with
     zero world refusals - the release contributes nothing to this log.

  2. ADDED a release request raised by the reset edge.          <- DEFENSIVE
     This repairs a DIFFERENT entry path: a run in which the menu family already
     owns the lock when the menu closes. Those runs are the ones C2 primes
     directly, because making the arrival order alone produce that state is
     unreliable - the escape is both the cause and, perversely, a cure (it lets
     any different-magnitude family re-acquire), so the escape-era build can
     stumble back to A by itself.

  3. DISCARDED: a still-threshold re-adopt after kCamStillTol non-continuations.
     It looked like a second safety net but the regression measured what it
     actually does: this branch adopts whichever arrival happens to BE the 90th
     non-continuation, so with two foreign families arriving it lands on the
     unit orthographic projection (proj00=1) half the time - a different wrong
     family, whose clipToPrev is an identity, i.e. the freeze. It also re-opened
     the door FrameGen.cpp:903-908 closed deliberately: "v0.94 re-acquired
     unconditionally after kCamStillTol non-continuing arrivals ... That is the
     freeze. Only an arrival from the SAME family may take over."
     C2b keeps it only as a counter-example, so the next person does not
     re-add it. The shipped build has no such path (`lock RELEASED after` does
     not appear in the DLL).

THE RESIDUAL THIS REGRESSION ALSO RECORDS
-----------------------------------------
Any "the wrong family owns the lock" repair is defeated if the wrong family
KEEPS arriving: it simply wins the next race, and it can never trip the
still-threshold because its own position never changes, so `continues` stays
true and `still` is reset every frame. C3 shows it. Closing that needs a learned
rule ("this fingerprint is the menu family, do not publish it while no menu is
open") which is deliberately NOT in v1.07 - see MFG_MASTER_NOTES.md chapter
14.6. The log's `proj00=` field reports which of these cases a run fell into,
in one line.

WHAT THIS MODEL IS NOT
----------------------
It is a snapshot-level state machine, not a frame pipeline. It asserts nothing
about rendering, only about which proj00 value the lock ends a run holding - and
therefore which family owns frameBufferCopy, which is the thing the freeze
correlates with.

Run:  python tools/regress_v107_lockrelease.py
"""

import sys

K_STEP_TOL2 = 50.0 * 50.0
K_STILL_TOL = 90
STILL_FRAMES = int(K_STILL_TOL / 2)      # A and B each trip one per frame

A_WORLD = (0.149184, (-50.0, 600.0, 80.0))
B_UNIT = (1.0, (-160.0, 160.0, 128.0))
C_MENU = (0.8391, (-243.0, -415.3, 118.6))

# Which of the v1.07 edits a modelled build has.
OLD = dict(escape=True, edge=False, still=False)             # v1.03 .. v1.06
ESCAPE_GONE = dict(escape=False, edge=False, still=False)    # edit 1 only
NEW = dict(escape=False, edge=True, still=False)             # v1.07b - SHIPPED
DRAFT_STILL = dict(escape=False, edge=True, still=True)      # v1.07 draft - DISCARDED


class Lock:
    def __init__(self, features):
        self.f = features
        self.have = False
        self.proj_valid = False
        self.proj00 = 0.0
        self.have_last = False
        self.last_pos = (0.0, 0.0, 0.0)
        self.still = 0
        self.pub = 0
        self.relock = 0
        self.famrej = 0
        self.released = 0
        self.pending = False
        # observation
        self.refused_world = 0

    def prime(self, family):
        """Seed the lock as if `family` already owned it (have + proj00 set)."""
        proj00, pos = family
        self.have = True
        self.proj_valid = True
        self.proj00 = proj00
        self.have_last = True
        self.last_pos = pos

    def arrival(self, proj00, pos, is_world_family=False):
        # The release request only exists in builds with the edge edit. Gating on
        # the feature (not a caller flag) matters: driving the OLD model with a
        # request would invent a release the log says never fired, and the C1
        # assertion would then fail against a mechanism those builds never had -
        # a harness artefact, not a code defect.
        if self.f["edge"] and self.pending:
            self.pending = False
            self.released += 1
            self.have = False
            self.proj_valid = False
            self.have_last = False
            self.still = 0

        proj_ok = proj00 > 1.0e-6
        if proj_ok and self.proj_valid:
            ratio = proj00 / self.proj00
            same = 0.98 < ratio < 1.02
            if self.f["escape"]:
                unit = 0.995 < proj00 < 1.005
                lock_unit = 0.995 < self.proj00 < 1.005
                if unit != lock_unit:
                    same = True          # the v1.03 escape
        else:
            same = True

        if self.have_last:
            d2 = sum((a - b) ** 2 for a, b in zip(pos, self.last_pos))
        else:
            d2 = 0.0
        continues = self.have and self.have_last and d2 <= K_STEP_TOL2

        if not self.have:
            self.have = True
            self.still = 0
            self.relock += 1
        elif not continues:
            if not same:
                self.famrej += 1
                if is_world_family:
                    self.refused_world += 1
                if self.f["still"]:
                    self.still += 1
                    if self.still < K_STILL_TOL:
                        return False
                    # edit 3: release, then fall through into the re-adopt below
                    self.released += 1
                    self.have = False
                    self.proj_valid = False
                    self.have_last = False
                    self.still = 0
                else:
                    return False         # v1.00..v1.06: never re-acquires
            self.relock += 1
            self.have = True
            self.still = 0
            self.have_last = False
        else:
            self.still = 0

        self.pub += 1
        if proj_ok:
            self.proj00 = proj00
            self.proj_valid = True
        self.last_pos = pos
        self.have_last = True
        return True

    def request_release(self):
        self.pending = True


def glide(pos, i, rate=0.42):
    return (pos[0] + rate * 0.01 * i, pos[1] + rate * i, pos[2] + rate * 0.05 * i)


def run(features, order, frames=744, release_at_edge=True, prime=None):
    """Feed `order` once per frame, optionally raising the reset edge midway.

    `order` is the set of families that arrive every frame, in arrival order.
    `prime` seeds the lock as already owned, which is how the C2 entry path
    (menu family holds the lock when the menu closes) is set up without relying
    on arrival-order side effects.
    """
    lk = Lock(features)
    if not features["edge"]:
        release_at_edge = False      # nothing to model without the edge
    if prime is not None:
        lk.prime(prime)
    fams = {"A": A_WORLD, "B": B_UNIT, "C": C_MENU}
    half = frames // 2

    def feed(i):
        for key in order:
            p00, pos = fams[key]
            if key == "A":
                pos = glide(pos, i)
            lk.arrival(p00, pos, is_world_family=(key == "A"))

    for i in range(half):
        feed(i)
    if release_at_edge:
        lk.request_release()
    for i in range(half, frames):
        feed(i)
    return lk


def show(tag, lk):
    print(f"  {tag:32s} locked proj00={lk.proj00:<9.6g} pub={lk.pub:<5d}"
          f" famrej={lk.famrej:<5d} released={lk.released:<3d}"
          f" world-refusals={lk.refused_world}")


def main():
    fails = []

    print("=" * 94)
    print("v1.07 camera-family lock - offline regression")
    print("=" * 94)

    # ---------------------------------------------------------------- C1
    print("\n[C1] the 22:02 order (world, unit, menu) - the observed sequence.")
    print("     Only the escape deletion is needed here; the log's #1 adoption")
    print("     was already the world camera, so removing the walk suffices.")
    old = run(OLD, ("A", "B", "C"))
    esc = run(ESCAPE_GONE, ("A", "B", "C"))
    new = run(NEW, ("A", "B", "C"))
    show("OLD  v1.03..v1.06", old)
    show("escape deleted only", esc)
    show("NEW  v1.07b", new)
    if abs(old.proj00 - C_MENU[0]) > 1e-4:
        fails.append("C1: old code did not end on the menu family as the log shows")
    if old.released != 0:
        fails.append("C1: old code released the lock, which the log contradicts")
    if old.refused_world == 0:
        fails.append("C1: old code did not refuse the world camera")
    if abs(esc.proj00 - A_WORLD[0]) > 1e-4:
        fails.append("C1: deleting the escape alone did NOT keep the world family")
    if esc.refused_world != 0:
        fails.append("C1: the escape-deleted build still refused the world camera")
    if abs(new.proj00 - A_WORLD[0]) > 1e-4:
        fails.append("C1: new code did not end on the world family")

    # ---------------------------------------------------------------- C2
    print("\n[C2] the OTHER entry path: the menu family already owns the lock")
    print("     when the menu closes. Primed directly. This is the case the")
    print("     release exists for, and the only one where it is observable.")
    esc2 = run(ESCAPE_GONE, ("A", "B"), prime=C_MENU)
    new2 = run(NEW, ("A", "B"), prime=C_MENU)
    show("escape deleted only", esc2)
    show("NEW  v1.07b", new2)
    if abs(esc2.proj00 - C_MENU[0]) > 1e-4:
        fails.append("C2: escape deletion alone was supposed to stay stuck")
    if esc2.refused_world == 0 or esc2.pub != 0:
        fails.append("C2: escape-deleted build should refuse the world camera here")
    if abs(new2.proj00 - A_WORLD[0]) > 1e-4:
        fails.append("C2: v1.07b did not recover the world family")
    if new2.released < 1:
        fails.append("C2: the edge release never fired")

    # --------------------------------------------------------------- C2b
    print("\n[C2b] the DISCARDED draft's still-threshold path, kept only as a")
    print("      counter-example so it does not get re-added. Isolated from the")
    print("      edge first, so its own choice of family is visible:")
    draft_noedge = run(dict(escape=False, edge=False, still=True), ("A", "B"),
                       prime=C_MENU)
    draft_edge = run(DRAFT_STILL, ("A", "B"), prime=C_MENU)
    show("discarded path, no edge", draft_noedge)
    show("discarded path, edge also on", draft_edge)
    if abs(draft_noedge.proj00 - B_UNIT[0]) > 1e-4:
        fails.append("C2b: the discarded path no longer demonstrates its own flaw")
    else:
        print("     -> it adopts whichever arrival is the 90th non-continuation,")
        print("        here the unit orthographic family: proj00=1.")
    # With the edge also present the release eventually rescues it back to A, so
    # the final family looks right - but the pre-edge window is the damage, and
    # the publish count shows it. NEW publishes exactly the post-edge frames;
    # the discarded path publishes those PLUS every frame the unit family owned
    # frameBufferCopy in between.
    if not (draft_edge.pub > new2.pub + 100):
        fails.append("C2b: expected the discarded path to publish a foreign "
                     "family for a long pre-edge window")
    else:
        print(f"     -> pre-edge damage, measured: the discarded path published "
              f"{draft_edge.pub} frames\n        vs v1.07b's {new2.pub} "
              f"({draft_edge.pub - new2.pub} frames of a foreign family owning "
              f"frameBufferCopy)")

    # ---------------------------------------------------------------- C3
    print("\n[C3] residual - if the wrong family KEEPS arriving it wins every")
    print("     race and can never trip the still-threshold (its own position")
    print("     never changes, so `continues` stays true and `still` resets).")
    print("     Chapter 14.6; the log's proj00= reports it in one line.")
    race = run(NEW, ("C", "A", "B"))
    show("NEW  menu-first, menu persists", race)
    if abs(race.proj00 - C_MENU[0]) < 1e-4:
        print("     -> documented residual: v1.07 does not close this race")
    else:
        fails.append("C3: expected the documented residual, got the world family")

    # ---------------------------------------------------------------- C4
    print("\n[C4] the same-family path is untouched: a continuing world stream")
    lk = Lock(NEW)
    for i in range(200):
        lk.arrival(A_WORLD[0], glide(A_WORLD[1], i), is_world_family=True)
    show("200 gliding world arrivals", lk)
    if lk.pub != 200:
        fails.append(f"C4: a continuing stream published {lk.pub} of 200")
    if lk.released != 0 or lk.famrej != 0:
        fails.append("C4: a single continuing source must not trip the release")

    # ---------------------------------------------------------------- C5
    print("\n[C5] direct proof that the escape alone walked the lock: alternate")
    print("     A and B with no third family present at all.")
    lk_new = Lock(ESCAPE_GONE)
    lk_old = Lock(OLD)
    for i in range(6):
        lk_new.arrival(A_WORLD[0], glide(A_WORLD[1], i))
        lk_new.arrival(B_UNIT[0], B_UNIT[1])
        lk_old.arrival(A_WORLD[0], glide(A_WORLD[1], i))
        lk_old.arrival(B_UNIT[0], B_UNIT[1])
    show("A/B only, escape deleted", lk_new)
    show("A/B only, OLD", lk_old)
    if abs(lk_old.proj00 - B_UNIT[0]) > 1e-4:
        fails.append("C5: old code did not let the unit family take the lock")
    if abs(lk_new.proj00 - A_WORLD[0]) > 1e-4:
        fails.append("C5: escape-deleted code let the unit family take the lock")

    print("\n" + "=" * 94)
    if fails:
        print("RESULT: FAIL")
        for f in fails:
            print(f"  - {f}")
    else:
        print("RESULT: OK")
        print("  escape deletion alone fixes the observed 22:02 walk (C1);")
        print("  the reset-edge release repairs the menu-holds-the-lock entry")
        print("  path (C2); a continuing world stream is untouched (C4); the")
        print("  still-threshold re-adopt is confirmed safe to have dropped")
        print("  (C2b); the post-edge race stays open by design (C3, ch. 14.6).")
    print("=" * 94)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
