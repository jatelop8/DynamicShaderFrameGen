#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full-file audit: for EVERY SKSE::log::info / warn / error / debug / trace call
in the given files, count format fields vs argument count and report mismatches.

Must replicate the compiler's view: string-literal-aware, comment-aware,
depth-aware arg splitting, and fmt field counting ({{ }} escapes).
"""
import io, re, sys

FILES = ["src/Streamline.cpp", "src/FrameGen.cpp", "src/main.cpp", "src/DX12SwapChain.cpp"]
LOGGERS = re.compile(r"\b(?:SKSE::)?log::(trace|debug|info|warn|error)\s*\(")
# NOTE (known limitation): the literal chain is read as *adjacent* string
# literals only. Calls that splice macros into the chain, e.g.
#   log::info("[x] built " __DATE__ " " __TIME__)
# are reported as a false mismatch (fields=0 args=1). Those entries are listed
# and must be eyeballed; they are never the real defect. Verified: Streamline.cpp:1251.


def strip_comments_keep_positions(s):
    """Replace comment bodies with spaces so index arithmetic stays valid."""
    out = list(s)
    i = 0
    n = len(s)
    instr = None
    while i < n:
        c = s[i]
        if instr:
            if c == "\\":
                i += 2; continue
            if c == instr:
                instr = None
            i += 1; continue
        if c in "\"'":
            instr = c; i += 1; continue
        if c == "/" and i + 1 < n and s[i + 1] == "/":
            j = s.find("\n", i)
            if j < 0: j = n
            for k in range(i, j):
                out[k] = " "
            i = j; continue
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            j = s.find("*/", i + 2)
            if j < 0: j = n
            else: j += 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j; continue
        i += 1
    return "".join(out)


def find_call(text, open_idx):
    d = 1; i = open_idx + 1; n = len(text); instr = None
    while i < n:
        c = text[i]
        if instr:
            if c == "\\":
                i += 2; continue
            if c == instr: instr = None
            i += 1; continue
        if c in "\"'":
            instr = c; i += 1; continue
        if c == "(": d += 1
        elif c == ")":
            d -= 1
            if d == 0: return i
        i += 1
    return -1


def split_args(s):
    parts = []; buf = []; d = 0; instr = None; i = 0; n = len(s)
    while i < n:
        c = s[i]
        if instr:
            buf.append(c)
            if c == "\\":
                if i + 1 < n: buf.append(s[i + 1]); i += 2; continue
            elif c == instr: instr = None
            i += 1; continue
        if c in "\"'":
            instr = c; buf.append(c); i += 1; continue
        if c in "([{": d += 1
        elif c in ")]}": d -= 1
        if c == "," and d == 0:
            parts.append("".join(buf)); buf = []; i += 1; continue
        buf.append(c); i += 1
    if "".join(buf).strip(): parts.append("".join(buf))
    return parts


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


def literal_chain(inner):
    chain = []; k = 0
    while True:
        m = re.match(r'\s*"((?:[^"\\]|\\.)*)"', inner[k:])
        if not m: break
        chain.append(m.group(1)); k += m.end()
    return "".join(chain), k


total = 0; bad = 0
for path in FILES:
    try:
        raw = io.open(path, "r", encoding="utf-8", newline="").read()
    except FileNotFoundError:
        print("skip (missing):", path); continue
    clean = strip_comments_keep_positions(raw)
    for m in LOGGERS.finditer(clean):
        total += 1
        oi = m.end() - 1
        ci = find_call(clean, oi)
        if ci < 0:
            print("  %s: unclosed call near char %d" % (path, oi)); bad += 1; continue
        inner = clean[oi + 1:ci]
        fmt, consumed = literal_chain(inner)
        rest = inner[consumed:]
        # skip the comma after the literal chain
        rest = rest.lstrip()
        if rest.startswith(","):
            rest = rest[1:]
        args = split_args(rest) if rest.strip() else []
        nf = count_fields(fmt)
        na = len(args)
        line = clean.count("\n", 0, m.start()) + 1
        if nf != na:
            bad += 1
            print("  MISMATCH %s:%d  %s  fields=%d args=%d" % (
                path, line, m.group(1), nf, na))
            print("      fmt: %s" % fmt[:150].replace("\n", " "))
    print("%s scanned" % path)

print("\nTOTAL logger calls =", total, "| MISMATCHED =", bad)
print("RESULT:", "OK - all logger calls balanced" if bad == 0 else "NEEDS FIX")
