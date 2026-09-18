# -*- coding: utf-8 -*-
"""
Offline regression for the v1.00 projection-family lock.

Reads the assertion that matters: given the ACTUAL matrices dumped in the
2026-09-18 16:42 run, does the family test separate the world camera from the
menu camera, and does it keep the world camera lockable?

Inputs (verbatim from the log):
  world  #1     ProjUnj[0][0] = 0.149184   pos=(-50.0,600.0,80.0)
  world  #7530  ProjUnj[0][0] = 0.149184   pos=(-54.6,796.3,80.0)
  world  #6280  ProjUnj[0][0] = 0.149184   pos=(-57.9,829.3,80.0)
  menu   #8234  ProjUnj[0][0] = 0.8391     pos=(-243.0,-415.3,118.6)
  menu   #18901 ProjUnj[0][0] = 0.8391     pos=(-243.0,-415.3,118.6)

The script simulates the lock state machine exactly as FrameGen.cpp does and
reports whether the freeze would have been prevented.
"""
import sys

K_CAM_STEP_TOL = 50.0
K_CAM_STEP_TOL2 = K_CAM_STEP_TOL * K_CAM_STEP_TOL
K_CAM_STILL_TOL = 90
K_CAM_JUMP_TOL = 400.0
K_CAM_JUMP_TOL2 = K_CAM_JUMP_TOL * K_CAM_JUMP_TOL

FAM_TOL_LO, FAM_TOL_HI = 0.98, 1.02


def family_ok(proj00, locked, have_locked):
    if not have_locked or not (proj00 == proj00 and proj00 > 1e-6):
        return True
    r = proj00 / locked
    return FAM_TOL_LO < r < FAM_TOL_HI


def simulate(arrivals, lock_family_test=True, jump_exempt=True):
    """arrivals: list of (name, proj00, x, y, z). Returns (final_owner, stats)."""
    have = False
    still = 0
    have_last = False
    last = (0.0, 0.0, 0.0)
    locked_p00 = 0.0
    owner = None
    fam_rej = 0
    adopt = 0
    for name, p00, x, y, z in arrivals:
        d2 = 0.0
        if have_last:
            d2 = (x - last[0]) ** 2 + (y - last[1]) ** 2 + (z - last[2]) ** 2

        same = family_ok(p00, locked_p00, lock_family_test and have)
        if have and not same and lock_family_test:
            fam_rej += 1
            continue                      # return false
        continues = have and have_last and d2 <= K_CAM_STEP_TOL2
        if not have:
            have = True
            still = 0
        elif not continues:
            # v1.00g: same-family non-continuation re-acquires immediately
            # (the family test already ran above and passed).
            if jump_exempt:
                have = True
                still = 0
                have_last = False
            else:
                still += 1
                if still >= K_CAM_STILL_TOL:
                    have = True
                    still = 0
                    have_last = False
                else:
                    continue                  # return false
        else:
            still = 0

        # accepted
        locked_p00 = p00
        last = (x, y, z)
        have_last = True
        owner = name
        adopt += 1
    return owner, {"family_rejected": fam_rej, "adopted": adopt}


def main():
    W = 0.149184
    M = 0.8391

    # The observed sequence: loading camera held for ~38 samples, a teleport into
    # the world, 14 walking samples, then the MENU camera arriving forever.
    arrivals = []
    for i in range(38):
        arrivals.append(("world_loading", W, -50.0, 600.0, 80.0))
    arrivals.append(("world_teleport", W, -60.0, 849.98, 80.0))
    for i in range(14):
        arrivals.append(("world_walk", W, -59.56 + i * 0.38, 845.62 - i * 3.74, 80.0))
    for i in range(400):
        arrivals.append(("menu", M, -243.05, -415.31, 118.56))

    owner_old, st_old = simulate(arrivals, lock_family_test=False, jump_exempt=False)
    owner_v100, st_v100 = simulate(arrivals, lock_family_test=True, jump_exempt=False)
    owner_new, st_new = simulate(arrivals, lock_family_test=True, jump_exempt=True)

    print("arrivals: %d" % len(arrivals))
    print()
    print("  OLD behaviour (v0.94, no family test)")
    print("    final owner   : %s" % owner_old)
    print("    family rejects: %d" % st_old["family_rejected"])
    print("    adoptions     : %d" % st_old["adopted"])
    print("    => %s" % ("FREEZE (menu camera owns the stream)" if owner_old == "menu"
                          else "world camera keeps the stream"))
    print()
    print("  v1.00 (family test, no jump exemption)")
    print("    final owner   : %s" % owner_v100)
    print("    family rejects: %d" % st_v100["family_rejected"])
    print("    adoptions     : %d" % st_v100["adopted"])
    print("    => %s" % ("STALE (stream parked on the loading camera)"
                          if owner_v100 != "menu_walk" and "walk" not in str(owner_v100)
                          else "world camera keeps the stream"))
    print()
    print("  v1.00f (family test + same-family jump exemption)")
    print("    final owner   : %s" % owner_new)
    print("    family rejects: %d" % st_new["family_rejected"])
    print("    adoptions     : %d" % st_new["adopted"])
    print("    => %s" % ("FREEZE (menu camera owns the stream)" if owner_new == "menu"
                          else "world camera keeps the stream"))

    # The fix must (a) never let the menu family own the stream,
    # (b) keep adopting world samples after the teleport, and (c) leave a pure
    # world stream completely untouched.
    ok = (owner_old == "menu"
          and owner_new != "menu"
          and st_new["family_rejected"] > 0
          and st_new["adopted"] >= st_v100["adopted"]
          and st_v100["adopted"] >= 38)

    # second scenario: the stream starts on the world camera and STAYS there,
    # with the menu camera never appearing. Must be unaffected.
    simple = [("world", W, -50.0 + i * 0.4, 600.0, 80.0) for i in range(200)]
    own_s, st_s = simulate(simple, lock_family_test=True)
    ok2 = own_s == "world" and st_s["family_rejected"] == 0
    print()
    print("  REGRESSION: pure world stream")
    print("    final owner   : %s  (expect world)" % own_s)
    print("    family rejects: %d  (expect 0)" % st_s["family_rejected"])

    print()
    print("RESULT: %s" % ("PASS" if (ok and ok2) else "FAIL"))
    return 0 if (ok and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
