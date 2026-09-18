"""v0.96b: fix the heartbeat's Streamline accessor call.

The v0.96 patch appended `Get().menuHitCount(), Get().menuHitName()` to the
[XRAY] heartbeat.  `Get()` returns `FrameGen&` (FrameGen.h:151), and the two
new accessors live on `Streamline`, not `FrameGen` -- so cl.exe rejected them:

    Streamline.cpp(1168): error C2039: "menuHitCount": is not a member of
                                "FrameGen::FrameGen"
    FrameGen.h(151): note: see declaration of "FrameGen::FrameGen"

The heartbeat already runs INSIDE a Streamline member function
(Streamline::CheckFrameConstants), where `diag` is reached implicitly.  So the
correct spelling drops the `Get().` prefix entirely.

Safety:
  * dry run unless --apply
  * asserts the anchor occurs exactly once
  * asserts the broken spelling is absent afterwards, and the fixed one present
  * line-ending adaptive (this file is LF today, but do not assume)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPPS = ROOT / "src" / "Streamline.cpp"

BROKEN = b"Get().menuHitCount(), Get().menuHitName());"
FIXED = b"menuHitCount(), menuHitName());"

# Idempotency guard: if the fixed spelling is already in, this ran before.
MARKER = b"menuHitCount(), menuHitName());"

EDITS = [
    ("heartbeat: drop the wrong Get(). qualifier on the Streamline accessors",
     CPPS, BROKEN, FIXED),
]


def main() -> int:
    apply = "--apply" in sys.argv

    for label, path, old, new in EDITS:
        data = path.read_bytes()
        hits = data.count(old)
        if hits != 1:
            print(f"[FAIL] {label}: anchor count = {hits}, expected exactly 1")
            print(f"       anchor: {old!r}")
            print("REFUSED, nothing written")
            return 2
        # guard: if the *fixed* text already exists, the patch already ran
        if data.count(MARKER) >= 1 and new == MARKER:
            # only treat as already-applied when the broken form is gone
            if hits == 0:
                print(f"[SKIP] {label}: already applied")
                continue

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
        lf = data.count(b"\n")
        crlf = data.count(b"\r\n")
        print(f"WROTE {path.name}: LF={lf} CRLF={crlf} bytes={len(data)}")

    # independent read-back
    print("\n--- read-back verification ---")
    cpp = CPPS.read_bytes()
    checks = [
        ("broken Get().menuHitCount absent", cpp.count(BROKEN) == 0),
        ("fixed menuHitCount() present", cpp.count(FIXED) == 1),
    ]
    ok = True
    for name, cond in checks:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}")
        ok = ok and cond
    print("RESULT:", "OK" if ok else "NEEDS FIX")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
