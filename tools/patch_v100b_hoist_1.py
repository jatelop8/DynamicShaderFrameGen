# -*- coding: utf-8 -*-
"""
v1.00b - hoist proj00 / projOk out of the source-lock scope block.

The v1.00 patch computed the projection fingerprint inside the `{ ... }` block
that wraps the source-lock decision, but reads `proj00` again AFTER that block
closes (at `frameBufferCopy = a_src;` to refresh snapLockProj00). That is a
C2065 'undeclared identifier' -- the block scope ends at `++snapLockPublish; }`.

This patch moves the two declarations to just before the block, so both the
decision inside and the refresh outside can see them. The lookup itself
(a_src.CameraProjUnjittered.data[0][0]) is unchanged.

Run with --apply to write; without it, dry-run only.
"""
import io
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPP = os.path.join(ROOT, "src", "FrameGen.cpp")
APPLY = "--apply" in sys.argv

OLD = """		{
			// ---- v1.00: projection-family fingerprint ----
			// ProjUnj[0][0] identifies the projection kind. Compare it against the
			// family currently locked, with a RELATIVE tolerance so the test does
			// not depend on the resolution / FOV this run happens to use.
			const float proj00 = a_src.CameraProjUnjittered.data[0][0];
			const bool projOk = (proj00 == proj00) && (proj00 > 1.0e-6f);
			bool sameFamily = true;"""

NEW = """		// ---- v1.00: projection-family fingerprint ----
		// ProjUnj[0][0] identifies the projection kind. Compare it against the
		// family currently locked, with a RELATIVE tolerance so the test does
		// not depend on the resolution / FOV this run happens to use.
		//
		// v1.00b: these two live OUTSIDE the block below, because the accept path
		// (which refreshes snapLockProj00) sits after the block has closed.
		const float proj00 = a_src.CameraProjUnjittered.data[0][0];
		const bool projOk = (proj00 == proj00) && (proj00 > 1.0e-6f);

		{
			bool sameFamily = true;"""


def main():
    with io.open(CPP, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    if "v1.00b: these two live OUTSIDE the block below" in src:
        print("REFUSED: v1.00b marker already present - patch has run")
        return 1

    n = src.count(OLD)
    if n != 1:
        print("REFUSED: anchor occurs %d times (must be exactly 1)" % n)
        return 1

    out = src.replace(OLD, NEW)

    checks = [
        ("hoisted decl outside block", "\t\tconst float proj00 = a_src.CameraProjUnjittered.data[0][0];" in out),
        ("sameFamily still inside block", "\t\t\tbool sameFamily = true;" in out),
        ("accept refresh still present", "snapLockProj00 = proj00;" in out),
        ("brace balance unchanged", out.count("{") - out.count("}") == src.count("{") - src.count("}")),
    ]
    ok = True
    for label, cond in checks:
        print("  %-38s %s" % (label, "PASS" if cond else "FAIL"))
        ok = ok and cond
    if not ok:
        print("REFUSED: post-conditions failed, nothing written")
        return 1

    if not APPLY:
        print("\nDRY RUN - nothing written. Re-run with --apply")
        return 0

    with io.open(CPP, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    print("\nAPPLIED: FrameGen.cpp %d -> %d chars" % (len(src), len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
