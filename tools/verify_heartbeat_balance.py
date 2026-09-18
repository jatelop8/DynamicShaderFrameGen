"""Count the heartbeat format fields and arguments precisely.

Line-oriented, quote-aware, bracket-aware. Two earlier attempts failed because
shell quoting mangled the embedded double quotes; this file avoids the problem
entirely by living on disk.
"""
import re
import sys
from pathlib import Path

SRC = Path(r"D:/Modding/DynamicShaderFrameGen/src/Streamline.cpp")

DQ = '"'


def count_fields(fmt):
    n, i, cnt = len(fmt), 0, 0
    while i < n:
        if fmt[i] == "{":
            if i + 1 < n and fmt[i + 1] == "{":
                i += 2
                continue
            cnt += 1
            depth = 1
            j = i + 1
            while j < n and depth:
                if fmt[j] == "{":
                    depth += 1
                elif fmt[j] == "}":
                    depth -= 1
                j += 1
            i = j
            continue
        i += 1
    return cnt


def split_top(s):
    """Split an argument list on top-level commas.

    Only parentheses and brackets are tracked for nesting. Angle brackets are
    NOT tracked: in this argument list they appear exclusively as comparison
    operators inside ternaries (`(a > b) ? x : y`), and counting them drives the
    depth negative, which then swallows every following comma and merges the
    remaining arguments into one -- the exact failure that made this script
    report 54 arguments for an 88-field format string.

    Verified safe here: `grep '<'` over the argument region finds no template at
    all -- every cast uses `static_cast<double>(...)`, which is parenthesised.
    """
    out, depth, cur, i = [], 0, "", 0
    while i < len(s):
        ch = s[i]
        if ch == DQ:
            j = i + 1
            while j < len(s):
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == DQ:
                    break
                j += 1
            cur += s[i:j + 1]
            i = j + 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return out


def main():
    src = SRC.read_text(encoding="utf-8")
    lines = src.split("\n")
    start = next(i for i, l in enumerate(lines) if "[XRAY] serial=" in l)
    end = start
    while ");" not in lines[end]:
        end += 1
    block = lines[start:end + 1]
    print(f"call spans source lines {start+1}..{end+1} ({len(block)} lines)")

    # Every line of the argument list begins with an identifier or a call, never
    # with a double quote.  Every line of the format string begins (after
    # whitespace) with a double quote -- EXCEPT the first, which carries the
    # "SKSE::log::info(" prefix.  Normalise that first line before testing.
    first = block[0]
    first_norm = first[first.find('"'):] if '"' in first else first
    fmt_last = -1
    for k, ln in enumerate(block):
        probe = first_norm if k == 0 else ln
        if probe.strip().startswith(DQ):
            fmt_last = k
        else:
            break
    if fmt_last < 0:
        print("could not locate the format-string region")
        print("first line:", repr(first[:80]))
        return 1

    fmt_region = "\n".join(block[:fmt_last + 1])
    fmt = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', fmt_region))
    fields = count_fields(fmt)

    arg_region = "\n".join(block[fmt_last + 1:]).rstrip()
    if arg_region.endswith(");"):
        arg_region = arg_region[:-2]
    args = split_top(arg_region)

    print(f"format string : {len(fmt)} chars across {fmt_last+1} literals")
    print(f"FIELDS        = {fields}")
    print(f"ARG COUNT     = {len(args)}")
    ok = fields == len(args)
    print("RESULT:", "MATCH" if ok else "MISMATCH")
    print(f"\nformat tail: ...{fmt[-95:]}")
    print(f"\nlast 5 args:")
    for a in args[-5:]:
        print("   ", a.replace("\n", " ").replace("\t", "")[:70])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
