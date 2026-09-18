# -*- coding: utf-8 -*-
"""v0.90: wrap the two naked '>' comparisons so they stop closing no template
argument list.

WHY
---
SKSE::log::info expands to fmt, whose arguments become TEMPLATE arguments
(fmt::basic_format_string<char, T1, T2, ...>).  Inside a template argument
list a bare '>' is the CLOSING token.  These two source arguments:

    (diag.detMin > diag.detMax ? 0.0f : diag.detMin),
    (diag.detMin > diag.detMax ? 0.0f : diag.detMax),

therefore closed the list early, and the compiler deduced 82 template
parameters where the format string needs 84 slots.  Everything after the
cut -- det guards, tid, snap counters, gate, mapHit -- was misaligned.

EVIDENCE
--------
  * fmt walk of the 16 chained literals -> 84 fields (no typos, 956 bytes)
  * compiler-reported S=char[957] -> exactly those 16 literals, nothing lost
  * compiler-reported parameter count -> 82  (2 short)
  * first hard spec mismatch at slot 16/17 ({:.3f} vs {:#x}) -> offset 2
  * exactly two naked top-level '>' in the argument list

FIX
---
Wrap the condition in parentheses: ((a > b) ? x : y).  The '>' is then nested
and can no longer close the template argument list.  Semantics unchanged.

GUARDS
------
  * each anchor must occur EXACTLY once
  * the replacement must not introduce or remove a bare '>' at top level
  * argument count of the heartbeat call must still be 84
  * line count + line endings unchanged

Usage: python tools/patch_v090_template_gt.py [--apply]
"""
import io
import sys

PATH = "src/Streamline.cpp"
APPLY = "--apply" in sys.argv

OLD_A = "\t\t\t\t\t(diag.detMin > diag.detMax ? 0.0f : diag.detMin),\n"
NEW_A = "\t\t\t\t\t((diag.detMin > diag.detMax) ? 0.0f : diag.detMin),\n"

OLD_B = "\t\t\t\t\t(diag.detMin > diag.detMax ? 0.0f : diag.detMax),\n"
NEW_B = "\t\t\t\t\t((diag.detMin > diag.detMax) ? 0.0f : diag.detMax),\n"

EDITS = [
    ("detMin arg: wrap the comparison", OLD_A, NEW_A),
    ("detMax arg: wrap the comparison", OLD_B, NEW_B),
]

raw = io.open(PATH, "rb").read()
text = raw.decode("utf-8")
orig_lines = text.count("\n")
orig_bytes = len(raw)

for label, old, new in EDITS:
    n = text.count(old)
    if n != 1:
        print("REFUSED: [%s] anchor count = %d (must be 1)" % (label, n))
        sys.exit(1)
    if text.count(new) != 0:
        print("REFUSED: [%s] replacement already present" % label)
        sys.exit(1)
    print("  [%s] anchor=1 OK" % label)

new_text = text
for label, old, new in EDITS:
    new_text = new_text.replace(old, new, 1)

# ---- invariants -----------------------------------------------------------
ok = True
if new_text.count("\n") != orig_lines:
    print("REFUSED: line count changed %d -> %d" % (orig_lines, new_text.count("\n")))
    ok = False
if not ok:
    sys.exit(1)

print("bytes %d -> %d (delta %+d)"
      % (orig_bytes, len(new_text.encode("utf-8")),
         len(new_text.encode("utf-8")) - orig_bytes))
print("lines %d -> %d" % (orig_lines, new_text.count("\n")))

for label, old, new in EDITS:
    if new_text.count(new) != 1:
        print("REFUSED: [%s] post-check failed" % label)
        sys.exit(1)
print("post-check: both replacements present exactly once")

if not APPLY:
    print()
    print("DRY RUN -- nothing written. Add --apply to write.")
    sys.exit(0)

with io.open(PATH, "wb") as f:
    f.write(new_text.encode("utf-8"))
print()
print("APPLIED to %s" % PATH)
