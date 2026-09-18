#!/usr/bin/env python3
"""
Machine-checked proof that the v1.08 probe is INSTRUMENT-ONLY.

Two independent checks, both on the real files, no inference:

  A. REVERSIBILITY. Re-apply the inverse of every edit in
     tools/patch_v108_probe.py to the patched sources and compare against the
     pre-patch backup byte for byte. If the patched tree minus the probe is
     identical to v1.07c, then the probe added text and changed nothing.

  B. NEW-LINE AUDIT. Extract every line the patch introduced and classify it.
     No introduced line may assign to anything except `diag.probe*` / the two
     `s_probe*` holders, and no introduced line may touch `c.*`.

Exit code 0 = both hold. This is the same class of proof as
tools/verify_v107c_is_inert.py, applied to the opposite conclusion: there the
functional edit was shown to be a no-op, here the edit is shown to be purely
additive.
"""
import difflib
import io
import sys

sys.path.insert(0, "tools")
from patch_v108_probe import EDITS, to_crlf, CPP, HDR  # noqa: E402

BACKUP = "src/backup-v1.08-20260919-000410"

fails = 0


def report(ok, label, detail=""):
    global fails
    print("  %s %s%s" % ("OK  " if ok else "FAIL", label, ("  " + detail) if detail else ""))
    if not ok:
        fails += 1


print("=" * 78)
print("A. REVERSIBILITY  (patched - probe  ==  v1.07c, byte for byte)")
print("=" * 78)

for path in (CPP, HDR):
    name = path.split("/")[-1]
    patched = io.open(path, "rb").read()
    backup = io.open("%s/%s" % (BACKUP, name), "rb").read()

    reverted = patched
    for p, label, old, new in EDITS:
        if p != path:
            continue
        nb, ob = to_crlf(new), to_crlf(old)
        c = reverted.count(nb)
        if c != 1:
            report(False, "%s: reverse anchor %s count=%d" % (name, label, c))
            break
        reverted = reverted.replace(nb, ob)
    else:
        same = reverted == backup
        report(same, "%s reverted == backup" % name,
               "(%d B vs %d B)" % (len(reverted), len(backup)))
        if not same:
            a = backup.decode("utf-8").split("\r\n")
            b = reverted.decode("utf-8").split("\r\n")
            d = [l for l in difflib.unified_diff(a, b, "backup", "reverted", n=0, lineterm="")]
            print("\n".join("      " + l for l in d[:30]))
            print("      (%d diff lines total)" % len(d))

print()
print("=" * 78)
print("B. NEW-LINE AUDIT  (every introduced line is a read, a declaration or a log)")
print("=" * 78)

import re  # noqa: E402

ALLOW = [
    (re.compile(r"^\s*//"), "comment"),
    (re.compile(r"^\s*$"), "blank"),
    (re.compile(r"^\s*diag\.probe[A-Za-z0-9_]*\s*="), "write to diag.probe*"),
    (re.compile(r"^\s*static\s+Matrix\s+s_probe[A-Za-z0-9_]*\{\};"), "probe decl"),
    (re.compile(r"^\s*static\s+bool\s+s_probe[A-Za-z0-9_]*\s*=\s*false;"), "probe decl"),
    (re.compile(r"^\s*s_probePrevProj\s*=\s*s_prevCamProj;"), "probe snapshot copy"),
    (re.compile(r"^\s*s_probeHasPrevProj\s*=\s*true;"), "probe flag"),
    (re.compile(r"^\s*if\s*\(s_hasPrevCam\)\s*\{"), "probe guard open"),
    (re.compile(r"^\s*if\s*\(s_probeHasPrevProj\)\s*\{"), "probe guard open"),
    (re.compile(r"^\s*\}\s*$"), "brace close"),
    (re.compile(r'^\s*"[^"]*",?\s*$'), "log string continuation"),
    (re.compile(r"^\s*SKSE::log::"), "log call"),
    (re.compile(r"^\s*diag\.clipW, diag\.probe"), "log args"),
    (re.compile(r"^\s*static_cast<double>\(diag\.probe"), "log args"),
    # heartbeat argument continuation lines (the patch reflowed one into two)
    (re.compile(r"^\s*Get\(\)\.jitterX, Get\(\)\.jitterY, clipDev, diag\.clipW,$"), "log args"),
    (re.compile(r"^\s*diag\.probeCurP00, diag\.probePrevP00, devOf\(curVP\), devOf\(prevVP\),$"),
     "log args"),
    (re.compile(r"^\s*float\s+probe[A-Za-z0-9_]*\s*=\s*0\.0f;"), "diag field"),
]

DANGEROUS = re.compile(r"^\s*(c\.|camCurVP\s*=|prevForReproj\s*=|invCurrViewProj\s*=|s_prevVP\s*=)")

def lines_of(p):
    # MUST read binary: text mode applies universal newlines, which rewrites
    # \r\n to \n, so split("\r\n") would return ONE element -- the whole file.
    # That silently turned this audit into a no-op on the first attempt.
    return io.open(p, "rb").read().decode("utf-8").split("\r\n")


counts = {}
unknown = []
dangerous = []

# Guard against the failure mode just fixed: if the split ever collapses to a
# single element the audit compares nothing and still reports OK. Fail loudly.
for path in (CPP, HDR):
    n = len(lines_of(path))
    report(n > 100, "%s split into %d lines (split is live)" % (path.split("/")[-1], n))

for path in (CPP, HDR):
    name = path.split("/")[-1]
    patched = lines_of(path)
    backup = lines_of("%s/%s" % (BACKUP, name))
    sm = difflib.SequenceMatcher(None, backup, patched, autojunk=False)
    added = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            added.extend(patched[j1:j2])
    print("  %s: %d introduced line(s)" % (name, len(added)))
    for line in added:
        if DANGEROUS.match(line):
            dangerous.append((name, line))
        hit = None
        for rx, kind in ALLOW:
            if rx.match(line):
                hit = kind
                break
        if hit is None:
            unknown.append((name, line))
        else:
            counts[hit] = counts.get(hit, 0) + 1

print("\n  classification:")
for k in sorted(counts):
    print("    %-22s %d" % (k, counts[k]))

report(not dangerous, "no introduced line writes to c.* / cam* / prev*",
       "(%d hits)" % len(dangerous))
for n, line in dangerous[:10]:
    print("      DANGER %s: %r" % (n, line))

report(not unknown, "every introduced line matched the read-only whitelist",
       "(%d unmatched)" % len(unknown))
for n, line in unknown[:10]:
    print("      UNKNOWN %s: %r" % (n, line))

print()
print("=" * 78)
if fails == 0:
    print("RESULT: OK - the v1.08 probe is purely additive instrumentation.")
    print("  A: removing it reproduces v1.07c byte for byte.")
    print("  B: nothing it adds assigns to anything but diag.probe* / s_probe*.")
else:
    print("RESULT: %d CHECK(S) FAILED - do NOT ship this build." % fails)
print("=" * 78)
sys.exit(0 if fails == 0 else 1)
