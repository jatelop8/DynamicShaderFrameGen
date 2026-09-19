#!/usr/bin/env python3
"""Patch MEMORY.md: refresh the HEAD pointer and add L39 (broken instrument
vs negative result look identical on stdout).

Default is a DRY RUN; pass --apply to write. Every anchor must match exactly
once or nothing is written at all.
"""
import ast
import hashlib
import sys
from pathlib import Path

TARGET = Path(
    r"C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/MEMORY.md"
)

EDITS = [
    (
        "E1 refresh HEAD pointer",
        "## \u2605\u2605\u2605\u2605\u2605 v1.21 \u73b0\u72b6\uff08commit `741fbe8`\uff0ctag `v1.21`\uff09",
        "## \u2605\u2605\u2605\u2605\u2605 v1.21 \u73b0\u72b6\uff08\u4ee3\u7801 commit `741fbe8` = tag `v1.21`\uff1b"
        "\u8d26\u672c+\u4ea4\u4ed8\u5361\u5df2\u5230 `ebc2233`\uff0c\u5de5\u4f5c\u533a\u5e72\u51c0\uff09",
    ),
    (
        "E2 add L39",
        "  `clipDev/det3/detVP` \u5168\u7531\u76f8\u673a\u6d3e\u751f \u21d2 \u8bc1\u660e\u4e0d\u4e86\u5c4f\u5e55\u5185\u5bb9\u3002",
        "  `clipDev/det3/detVP` \u5168\u7531\u76f8\u673a\u6d3e\u751f \u21d2 \u8bc1\u660e\u4e0d\u4e86\u5c4f\u5e55\u5185\u5bb9\u3002\n"
        "- **L39\uff1a\u4efb\u4f55\u300c\u8ba1\u6570\u4e3a 0\u300d\u7684\u65ad\u8a00\uff0c\u5148\u8bc1\u660e\u4ea7\u751f\u8fd9\u4e2a\u8ba1\u6570\u7684\u5de5\u5177\u8dd1\u8d77\u6765\u4e86\u3002**\n"
        "  \u672c\u8f6e `strings -a <dll> | grep -c <key>` \u4e09\u884c\u5168\u62a5 `0` \u2014\u2014 \u771f\u56e0\u662f\u8fd9\u4e2a Git Bash"
        "**\u6ca1\u88c5 binutils\u3001\u6ca1\u6709 `strings`**\uff0c\u5de5\u5177\u5931\u8d25\u2192\u7ba1\u9053\u65e0\u8f93\u51fa\u2192`grep -c`"
        "\u6570\u5230 0\u2192\u9000\u51fa\u7801\u88ab `for` \u541e\u6389\u3002\n"
        "  **\u300c\u5de5\u5177\u6ca1\u8dd1\u300d\u88ab\u4f2a\u88c5\u6210\u300c\u7ed3\u679c\u4e3a\u7a7a\u300d\u3002**\u6539 "
        "`grep -a -c <key> <dll>` \u540e\uff1a`InteropFenceWait`=2 `MenuGuardFader`=2 `NRAllowWithFrameGen`=3\u3002\n"
        "  \u5224\u636e\u4e09\u8fde\uff1a\u2460 `which <tool>` \u5148\u786e\u8ba4\u5b58\u5728\uff1b\u2461 "
        "**\u5fc5\u987b\u6709\u4e00\u4e2a\u5fc5\u7136\u5b58\u5728\u7684\u4e32\u505a\u9633\u6027\u5bf9\u7167**\uff1b\u2462 \u770b\u9000\u51fa\u7801\u3002",
    ),
]


def sha(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    apply = "--apply" in sys.argv

    for label, _old, _new in EDITS:
        pass  # AST sanity of this module is checked by the caller

    if not TARGET.is_file():
        print(f"REFUSED: target not found: {TARGET}")
        return 2

    raw = TARGET.read_bytes()
    text = raw.decode("utf-8", errors="surrogateescape")
    before = sha(TARGET)

    # ---- anchors: every one must match exactly once ----
    for label, old, _new in EDITS:
        n = text.count(old)
        if n != 1:
            print(f"REFUSED: {label}: anchor count={n} (must be 1), nothing written")
            return 1

    # ---- idempotency guard: L39 must not already be present ----
    marker = "L39\uff1a\u4efb\u4f55\u300c\u8ba1\u6570\u4e3a 0\u300d\u7684\u65ad\u8a00"
    if marker in text:
        print("REFUSED: already applied (L39 marker present), nothing written")
        return 1

    out = text
    for label, old, new in EDITS:
        out = out.replace(old, new, 1)
        print(f"  ok  {label}")

    # ---- post-conditions on the RESULT text ----
    post_ok = True
    for needle in ("ebc2233", "L39", "grep -a -c <key> <dll>", "InteropFenceWait`=2"):
        c = out.count(needle)
        flag = "OK " if c >= 1 else "FAIL"
        if c < 1:
            post_ok = False
        print(f"  post {flag} {needle!r} count={c}")

    if not post_ok:
        print("REFUSED: post-condition failed, nothing written")
        return 1

    after = hashlib.md5(out.encode("utf-8", errors="surrogateescape")).hexdigest()
    print(f"  md5 {before} -> {after}")

    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply to write.")
        return 0

    TARGET.write_bytes(out.encode("utf-8", errors="surrogateescape"))
    print(f"WROTE {TARGET}  ({len(raw)} -> {len(out.encode('utf-8', errors='surrogateescape'))} bytes)")
    print(f"  md5 on disk = {sha(TARGET)}")
    return 0


if __name__ == "__main__":
    ast.parse(Path(__file__).read_text(encoding="utf-8"))
    raise SystemExit(main())
