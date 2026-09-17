# -*- coding: utf-8 -*-
"""
MEMORY.md: record the third instance of the marker/verbatim mismatch class, and
turn the prose rule into a machine-checked invariant.

Contract:
  * target must be pure LF.
  * anchor must match exactly once.
  * guard string must NOT already be present.
  * dry run unless --apply.
"""
import sys
import os

TGT = r"C:\Users\Administrator\.workbuddy\MEMORY.md"

ANCHOR = "     写完立刻回读 marker 计数、别只信那行 OK/MISSING 之外的推断。\n"

GUARD = "assert MARKER in PAYLOAD"

ADD = (
    "     \u21d2 **\u7b2c\u4e09\u6b21\u8e29\u5230\uff082026-09-17\uff0c`note_0917e.py`\uff09**\uff1a"
    "marker \u5199\u300cv0.56 / v0.57 \u4ece\u672a\u8fdb\u8fc7\u6e38\u620f\u300d\uff0c"
    "\u6b63\u6587\u662f\u300cv0.56 **\u4e0e** v0.57 \u4ece\u672a\u8fdb\u8fc7\u6e38\u620f\u300d\n"
    "     \u21d2 \u540e\u7f6e\u65ad\u8a00\u5f53\u573a `AssertionError: post-condition failed`\uff0c"
    "\u800c\u4e14**\u5b88\u536b\u6052\u7a7a**\uff08marker \u6c38\u8fdc\u641c\u4e0d\u5230 \u21d2 \u91cd\u8dd1\u4f1a\u518d\u63d2\u4e00\u4efd\uff09\u3002\n"
    "     \u21d2 **\u6839\u6cbb\uff1a\u628a\u6563\u6587\u89c4\u5219\u53d8\u6210\u673a\u5668\u81ea\u68c0 \u2014\u2014 "
    "\u811a\u672c\u5f00\u5934\u52a0 `assert MARKER in PAYLOAD`**"
    "\uff08marker \u5fc5\u987b\u662f\u88ab\u8ffd\u52a0\u6587\u672c\u7684\u5b50\u4e32\uff09\uff0c"
    "\u8fd9\u7c7b\u9519\u5c31\u5728\u5199\u76d8\u524d\u70b8\u3002\u63d2\u5165/\u8ffd\u52a0\u578b\u811a\u672c\u4e00\u5f8b\u52a0\u3002\n"
)


def main():
    apply = "--apply" in sys.argv
    raw = open(TGT, "rb").read()
    crlf = raw.count(b"\r\n")
    stray = raw.count(b"\r") - crlf
    if crlf or stray:
        print("REFUSED - not pure LF (CRLF=%d stray=%d)" % (crlf, stray))
        return 1
    txt = raw.decode("utf-8")
    if GUARD in txt:
        print("REFUSED - guard text already present")
        return 1
    n = txt.count(ANCHOR)
    print("target   : LF=x%d CRLF=0 stray=0  %d bytes" % (raw.count(b"\n"), len(raw)))
    print("anchor   : x%d %s" % (n, "OK" if n == 1 else "*** NOT UNIQUE ***"))
    if n != 1:
        return 1
    print("guard    : NOT present -> safe")
    print("append   : +%d bytes" % len(ADD.encode("utf-8")))
    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply")
        return 0
    out = txt.replace(ANCHOR, ANCHOR + ADD, 1)
    open(TGT, "wb").write(out.encode("utf-8"))
    chk = open(TGT, "rb").read()
    t = chk.decode("utf-8")
    print("written  : %d bytes  CRLF=%d LF=%d stray=%d"
          % (len(chk), chk.count(b"\r\n"), chk.count(b"\n"),
             chk.count(b"\r") - chk.count(b"\r\n")))
    assert GUARD in t, "post-condition failed"
    assert t.count(ANCHOR) == 1, "anchor duplicated"
    print("post-condition OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
