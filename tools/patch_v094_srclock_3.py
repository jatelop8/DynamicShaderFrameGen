#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.94 stage 3: add the source-lock counters to the heartbeat.

Appends ` lock(pub/hold/re/still)={}/{}/{}/{}` to the LAST format literal and
the 4 matching arguments at the END of the argument list. Field count and arg
count must BOTH grow by exactly 4 -- the script asserts that before writing
(this is the exact class of edit that produced C7595 in v0.91).

Assertions: marker first, exactly-one anchors, field/arg balance re-checked,
dry-run default.
"""
import io, re, sys, hashlib

PATH = "src/Streamline.cpp"
MARKER = "lock(pub/hold/re/still)"

OLD_FMT = '''					"mapHit(perFrame/unmap)={}/{} dist(last/acc)={:.1f}/{:.1f}",'''
NEW_FMT = '''					"mapHit(perFrame/unmap)={}/{} dist(last/acc)={:.1f}/{:.1f} | "
					"lock(pub/hold/re/still)={}/{}/{}/{}",'''

OLD_ARG = """					Get().snapLastDist, Get().snapAcceptDist);"""
NEW_ARG = """					Get().snapLastDist, Get().snapAcceptDist,
					Get().snapLockPublish, Get().snapLockHold,
					Get().snapLockRelock, Get().snapLockStill);"""

def count_fields(fmt):
    n = 0; i = 0
    while i < len(fmt):
        if fmt[i] == "{" and i + 1 < len(fmt) and fmt[i + 1] == "{":
            i += 2; continue
        if fmt[i] == "{":
            n += 1
            j = i + 1; d = 1
            while j < len(fmt) and d:
                if fmt[j] == "{": d += 1
                elif fmt[j] == "}":
                    d -= 1
                    if d == 0: break
                j += 1
            i = j + 1; continue
        i += 1
    return n

def heartbeat_counts(text):
    lines = text.split("\n")
    a = next(i for i, l in enumerate(lines) if "SKSE::log::info(" in l and '"[XRAY] serial={}' in l)
    off = sum(len(l) + 1 for l in lines[:a])
    oi = text.index("(", off)
    i = oi + 1; d = 1; instr = None; n = len(text)
    while i < n:
        c = text[i]
        if instr:
            if c == "\\": i += 2; continue
            if c == instr: instr = None
            i += 1; continue
        if c in "\"'": instr = c; i += 1; continue
        if c == "(": d += 1
        elif c == ")":
            d -= 1
            if d == 0: break
        i += 1
    inner = text[oi + 1:i]
    chain = []; k = 0
    while True:
        m = re.match(r'\s*"((?:[^"\\]|\\.)*)"', inner[k:])
        if not m: break
        chain.append(m.group(1)); k += m.end()
    fmt = "".join(chain)
    rest = inner[k:].lstrip()
    if rest.startswith(","): rest = rest[1:]
    parts = []; buf = ""; d = 0; instr = None; j = 0
    while j < len(rest):
        c = rest[j]
        if instr:
            buf += c
            if c == "\\": buf += rest[j + 1]; j += 2; continue
            if c == instr: instr = None
            j += 1; continue
        if c in "\"'": instr = c; buf += c; j += 1; continue
        if c in "([{": d += 1
        elif c in ")]}": d -= 1
        if c == "," and d == 0:
            parts.append(buf); buf = ""; j += 1; continue
        buf += c; j += 1
    if buf.strip(): parts.append(buf)
    return count_fields(fmt), len(parts)

data = io.open(PATH, "r", encoding="utf-8", newline="").read()

if MARKER in data:
    print("REFUSED: stage 3 already applied."); sys.exit(0)

f0, a0 = heartbeat_counts(data)
print("BEFORE: fields=%d args=%d  %s" % (f0, a0, "balanced" if f0 == a0 else "MISMATCH"))

EDITS = [("fmt tail", OLD_FMT, NEW_FMT), ("arg tail", OLD_ARG, NEW_ARG)]
for label, old, _ in EDITS:
    c = data.count(old)
    print("anchor '%-9s' count = %d" % (label, c))
    if c != 1:
        print("REFUSED: anchor '%s' count=%d (need exactly 1)." % (label, c)); sys.exit(1)

new = data
for label, old, newv in EDITS:
    new = new.replace(old, newv)

f1, a1 = heartbeat_counts(new)
print("AFTER : fields=%d args=%d  %s" % (f1, a1, "balanced" if f1 == a1 else "MISMATCH"))
print("delta : fields %+d args %+d" % (f1 - f0, a1 - a0))
if f1 != a1:
    print("REFUSED: not balanced after edit. nothing written."); sys.exit(1)
if (f1 - f0) != 4 or (a1 - a0) != 4:
    print("REFUSED: expected +4/+4. nothing written."); sys.exit(1)

print("line endings CRLF %d -> %d" % (data.count("\r\n"), new.count("\r\n")))
if "--apply" not in sys.argv:
    print("\nDRY RUN - nothing written."); sys.exit(0)

io.open(PATH, "w", encoding="utf-8", newline="").write(new)
back = io.open(PATH, "r", encoding="utf-8", newline="").read()
bf, ba = heartbeat_counts(back)
print("\napplied. readback fields=%d args=%d | md5=%s" % (bf, ba, hashlib.md5(back.encode()).hexdigest()))
