#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.91 fix: the heartbeat's `snap(...)` group is missing ONE argument.

Format chain requires:
    "snap(acc/jmp/re/zero/arr/frozen/shape/rejPct)={}/{}/{}/{}/{}/{}/{} {:.1f}% "
      -> 7 integer fields (acc/jmp/re/zero/arr/frozen/shape) + 1 float (rejPct)
    "shapeRej(own)={:.1f}% "
      -> 1 float (own share)

Args supplied were only:
    Get().snapAccept, Get().snapRejectJump, Get().snapRelock,
    Get().snapRejectZero, Get().snapArrivals, Get().snapFrozenReject,
    Get().snapRejectShape,                       <- fills {:.1f} rejPct (WRONG: it is a count)
    Get().snapArrivals ? 100.0*... : 0.0,        <- fills shapeRej(own)
  => 1 field short => fmt consteval check fails => C7595.

Fix: insert the real rejPct percentage expression BEFORE shapeRej(own), and
     keep the own-share expression as-is. Result: 84 args for 84 fields.

Assertions: exactly one occurrence of each anchor; idempotency marker checked
FIRST; dry-run by default, --apply to write.
"""
import io, sys, hashlib

PATH = "src/Streamline.cpp"
MARKER = "100.0 * static_cast<double>(Get().snapRejectShape)\n\t\t\t\t\t\t\t/ static_cast<double>(Get().snapArrivals)"

OLD = """					Get().snapRejectShape,
					Get().snapArrivals
						? 100.0 * static_cast<double>(Get().snapRejectShape)
							/ static_cast<double>(Get().snapArrivals)
						: 0.0,"""

NEW = """					Get().snapRejectShape,
					Get().snapArrivals
						? 100.0 * static_cast<double>(Get().snapRejectShape)
							/ static_cast<double>(Get().snapArrivals)
						: 0.0,
					Get().snapArrivals
						? 100.0 * static_cast<double>(Get().snapRejectShape)
							/ static_cast<double>(Get().snapArrivals)
						: 0.0,"""

data = io.open(PATH, "r", encoding="utf-8", newline="").read()

# ---- guard 1: idempotency marker (must be checked BEFORE anchors) ----
# after a correct apply there will be TWO copies of the ternary; before, ONE.
occ = data.count(MARKER)
print("guard0  marker occurrences =", occ, "(1 = not yet applied, 2 = already applied)")
if occ >= 2:
    print("REFUSED: already applied (or duplicate). nothing written.")
    sys.exit(0)

# ---- guard 2: anchor uniqueness ----
n = data.count(OLD)
print("guard1  OLD anchor count =", n)
EDITS = [("heartbeat snap missing-arg", OLD, NEW)]
for label, old, new in EDITS:
    c = data.count(old)
    if c != 1:
        print("REFUSED: anchor '%s' count=%d (need exactly 1). nothing written." % (label, c))
        sys.exit(1)

new_data = data.replace(OLD, NEW)
assert new_data != data

# ---- structural post-checks ----
crlf_before = data.count("\r\n"); lf_before = data.count("\n")
crlf_after = new_data.count("\r\n"); lf_after = new_data.count("\n")
print("line endings: before CRLF=%d LF=%d | after CRLF=%d LF=%d" % (
    crlf_before, lf_before, crlf_after, lf_after))
if "\r\n" in data and crlf_after == 0:
    print("REFUSED: would destroy CRLF. nothing written."); sys.exit(1)
print("bytes: %d -> %d (delta %+d)" % (len(data), len(new_data), len(new_data) - len(data)))

if "--apply" not in sys.argv:
    print("\nDRY RUN - nothing written. re-run with --apply to write.")
    sys.exit(0)

io.open(PATH, "w", encoding="utf-8", newline="").write(new_data)
back = io.open(PATH, "r", encoding="utf-8", newline="").read()
print("\napplied. readback bytes =", len(back), "md5 =", hashlib.md5(back.encode("utf-8")).hexdigest())
print("readback marker occurrences =", back.count(MARKER))
print("readback OLD-anchor count  =", back.count(OLD), "(expect 0)")
