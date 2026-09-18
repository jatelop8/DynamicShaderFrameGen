"""v0.96c: bump the startup banner so the log cannot be misread.

The v0.96 build still printed "[XRAY] diag active v0.95" because the banner
string was never updated.  That is exactly the ambiguity that broke the v0.93
investigation: the log said one version while the disk held another.  Bump it
so the next run names the build that is actually loaded.

Safety: dry run unless --apply; anchor must occur exactly once; read-back check.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPPS = ROOT / "src" / "Streamline.cpp"

OLD = b'"[XRAY] diag active v0.95 (compiled "'
NEW = b'"[XRAY] diag active v0.96 (compiled "'

EDITS = [("banner: v0.95 -> v0.96", CPPS, OLD, NEW)]


def main() -> int:
    apply = "--apply" in sys.argv

    for label, path, old, new in EDITS:
        data = path.read_bytes()
        hits = data.count(old)
        if hits != 1:
            print(f"[FAIL] {label}: anchor count = {hits}, expected exactly 1")
            print("REFUSED, nothing written")
            return 2

    acc: dict[Path, bytes] = {}
    for label, path, old, new in EDITS:
        cur = acc.get(path, path.read_bytes())
        assert cur.count(old) == 1, label
        acc[path] = cur.replace(old, new, 1)
        print(f"[OK]   {label}")

    if not apply:
        print("\nDRY RUN -- pass --apply to write.")
        return 0

    for path, data in acc.items():
        path.write_bytes(data)
        print(f"WROTE {path.name}: LF={data.count(chr(10).encode())} "
              f"CRLF={data.count(b'\\r\\n')} bytes={len(data)}")

    print("\n--- read-back ---")
    cpp = CPPS.read_bytes()
    checks = [
        ("old banner absent", cpp.count(OLD) == 0),
        ("new banner present", cpp.count(NEW) == 1),
    ]
    ok = True
    for name, cond in checks:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond
    print("RESULT:", "OK" if ok else "NEEDS FIX")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
