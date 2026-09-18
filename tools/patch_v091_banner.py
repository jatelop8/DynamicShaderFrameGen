#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v0.91 banner: bump the boot banner from v0.89 -> v0.91 so logs are unambiguous.
Guarded, dry-run by default.
"""
import io, sys, hashlib

PATH = "src/Streamline.cpp"
OLD = '[XRAY] diag active v0.89 (compiled '
NEW = '[XRAY] diag active v0.91 (compiled '

data = io.open(PATH, "r", encoding="utf-8", newline="").read()

# guard 0 (idempotency) FIRST
if NEW in data:
    print("REFUSED: already bumped to v0.91. nothing written."); sys.exit(0)

n = data.count(OLD)
print("anchor count =", n)
if n != 1:
    print("REFUSED: anchor count=%d (need 1). nothing written." % n); sys.exit(1)

new = data.replace(OLD, NEW)
crlf_b = data.count("\r\n"); crlf_a = new.count("\r\n")
print("line endings CRLF %d -> %d" % (crlf_b, crlf_a))
print("bytes %d -> %d" % (len(data), len(new)))

if "--apply" not in sys.argv:
    print("\nDRY RUN - nothing written.")
    sys.exit(0)
io.open(PATH, "w", encoding="utf-8", newline="").write(new)
back = io.open(PATH, "r", encoding="utf-8", newline="").read()
print("applied. readback has v0.91:", NEW in back, "| v0.89 left:", OLD in back)
print("readback chars =", len(back), "md5 =", hashlib.md5(back.encode("utf-8")).hexdigest())
