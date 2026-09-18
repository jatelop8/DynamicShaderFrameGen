#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.04b -- make the watchdog name Present() honestly.

WHY. The 2026-09-18 19:04 watchdog wrote "stage=d3d11 Wait" for 19.7 seconds while
frames stayed at 1. That was read as "the fence wait is hanging", but
WaitFenceBounded returns immediately when the fence is already complete (the same
lines reported fence=2/2). The stage name was simply the LAST string m_stage held:
line 1533 writes "d3d11 Wait" just before the wait, and nothing writes m_stage
again until the next frame enters Present at line 928 -- which never came. So the
honest reading is "the thread never came back to Present", and the only call
between those two writes that can block for seconds is swapChain->Present(0).

The fix is to stop relying on a name that outlives its own call: stamp a
monotonic millisecond counter the instant the blocking Present is entered, and
expose it to the watchdog. The watchdog prints presentAge=; a large presentAge on
a silent frame now names Present() in one glance, with no inference.
"""

import sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
CPP = os.path.join(HERE, "..", "src", "DX12SwapChain.cpp")
HDR = os.path.join(HERE, "..", "src", "DX12SwapChain.h")


def mk(*lines):
    return ("\r\n".join(lines) + "\r\n")

# ------------------------------------------------------------------ header --
H_OLD = "\t\tstatic constexpr std::uint32_t kFenceWaitTimeoutMs = 250;\r\n"
H_NEW = mk(
    "",
    "\t\t// v1.04b: steady_clock millisecond stamp taken the instant the blocking",
    "\t\t// Present is entered. The watchdog prints its age so a silent frame names",
    "\t\t// Present() instead of the stale m_stage string that outlived its call.",
    "\t\tstatic std::atomic<long long> g_presentEnteredMs;",
    "",
    "\t\tstatic constexpr std::uint32_t kFenceWaitTimeoutMs = 250;",
)

# --------------------------------------------------------------------- cpp --
C_DEF_OLD = ""
C_DEF_NEW = mk(
    "",
    "\t// v1.04b: see the header. Stamped immediately before every blocking Present.",
    "\tstd::atomic<long long> g_presentEnteredMs{ 0 };",
)

C_P0_OLD = mk(
    "",
)
C_P0_NEW = mk(
    "\t\t\t// v1.04b: stamp the entry so a watchdog tick that lands inside this call",
    "\t\t\t// can say so. This is the only call between \"d3d11 Wait\" being written",
    "\t\t\t// and the next frame's \"present entry\", so before this change it was",
    "\t\t\t// invisible: the 19:04 run blamed the fence wait for 19.7 s of stall",
    "\t\t\t// that belonged here.",
    "\t\t\tg_presentEnteredMs.store(static_cast<long long>(std::chrono::duration_cast<std::chrono::milliseconds>(",
    "\t\t\t\tstd::chrono::steady_clock::now().time_since_epoch()).count()));",
    "",
)

C_P1_OLD = mk(
    "",
)
C_P1_NEW = mk(
    "\t\tg_presentEnteredMs.store(static_cast<long long>(std::chrono::duration_cast<std::chrono::milliseconds>(",
    "\t\t\tstd::chrono::steady_clock::now().time_since_epoch()).count()));",
    "",
)

C_FMT_OLD = ""
C_FMT_NEW = ""

C_WHOLE_OLD = mk(
    "",
)
C_WHOLE_NEW = mk(
    "",
    "\t\t\t\t\t\t(g_presentEnteredMs.load() > 0)",
    "\t\t\t\t\t\t\t? (nowMs - g_presentEnteredMs.load())",
    "\t\t\t\t\t\t\t: 0LL,",
)

EDITS = [
    ("header-atomic-decl",  HDR, H_OLD,      H_NEW),
    ("cpp-atomic-def",      CPP, C_DEF_OLD,  C_DEF_NEW),
    ("stamp-dlssg-present", CPP, C_P0_OLD,   C_P0_NEW),
    ("stamp-fsr-present",   CPP, C_P1_OLD,   C_P1_NEW),
    ("watchdog-format",     CPP, C_FMT_OLD,  C_FMT_NEW),
    ("watchdog-arg",        CPP, C_WHOLE_OLD,C_WHOLE_NEW),
]


def main():
    apply = "--apply" in sys.argv
    files = {p: open(p, "r", encoding="utf-8", newline="").read() for p in (CPP, HDR)}
    print(f"mode: {'APPLY' if apply else 'DRY RUN'}\n")
    ok = True
    for label, path, old, new in EDITS:
        t = files[path]
        n = t.count(old)
        if n != 1:
            ok = False
        print(f"[{'OK' if n == 1 else 'FAIL'}] {label:22s} ({os.path.basename(path)}): count={n}")
        if n == 1:
            files[path] = t.replace(old, new, 1)
    print()
    if not ok:
        print("REFUSED, nothing written")
        return 1
    for label, path, _, new in EDITS:
        c = files[path].count(new)
        if c != 1:
            print(f"GUARD FAILED: {label} new-fragment count={c}; REFUSED")
            return 1
    if apply:
        for p, t in files.items():
            open(p, "w", encoding="utf-8", newline="").write(t)
            crlf = t.count("\r\n"); bare = t.count("\n") - crlf
            print(f"WROTE {len(t):>7} bytes  CRLF={crlf} bare_LF={bare}  {os.path.basename(p)}")
    else:
        for p, t in files.items():
            print(f"would write {len(t):>7} bytes  {os.path.basename(p)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
