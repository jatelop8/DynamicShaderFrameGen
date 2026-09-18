#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extend read_xray_log.py for the v0.76 watchdog fields.

Two new fields and one corrected one:

  msg=1|0     did the window answer WM_NULL within 200 ms. This is the same
              question USER32 asks before it paints "Not Responding", so msg=0
              is the user-visible freeze, measured rather than inferred.
  alive=1|0   does the window still exist.
  dsync       DIRECTION CHANGED IN v0.76. Before: 1 meant "GetCurrentBackBuffer
              Index() after Present differed from frameIndex before it", which
              is what a SUCCESSFUL flip does - so every healthy run read as a
              desync (the 07:23 run: 291/291). From v0.76 it means the opposite:
              1 = the index did NOT move, i.e. Present returned success without
              flipping the screen. Reading an old file with the new meaning
              would invert the verdict, so the reader must not silently mix
              them - it reports the field's own value and lets the section
              header name which build wrote it.

Four edits, each asserting its anchor appears exactly once.
Dry-run by default; --apply to write.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, "read_xray_log.py")

R1_OLD = '''    r"(?:\\s+dsync=(?P<dsync>\\d+))?"
    r"\\s*(?P<stalled><==.*)?$")'''
R1_NEW = '''    r"(?:\\s+dsync=(?P<dsync>\\d+))?"
    r"(?:\\s+msg=(?P<msg>\\d+))?"
    r"(?:\\s+alive=(?P<alive>\\d+))?"
    r"\\s*(?P<stalled><==.*)?$")'''

R2_OLD = '''        "dsync": int(g["dsync"]) if g.get("dsync") is not None else None,
        "stalled": bool(g["stalled"]),'''
R2_NEW = '''        "dsync": int(g["dsync"]) if g.get("dsync") is not None else None,
        # v0.76: window responsiveness. None when the build predates the probe.
        "msg": int(g["msg"]) if g.get("msg") is not None else None,
        "alive": int(g["alive"]) if g.get("alive") is not None else None,
        "stalled": bool(g["stalled"]),'''

R3_OLD = '''#   dsync   1 when frameIndex no longer matches GetCurrentBackBufferIndex()'''
R3_NEW = '''#   dsync   v0.76 CHANGED MEANING. Up to v0.75: 1 = the index after Present
#           differed from frameIndex before it - which is what a SUCCESSFUL flip
#           does, so healthy runs read as desynced. From v0.76: 1 = the index did
#           NOT move, i.e. Present returned success without flipping the screen.
# v0.76 also adds msg/alive: the watchdog asking the game window whether it is
# still answering messages (SendMessageTimeout WM_NULL). msg=0 is the same
# condition USER32 paints as "Not Responding" - the user-visible freeze.'''

# ---- the new verdict section (appended before main's final return) ----
R4_ANCHOR_OLD = '''def part_gpu_timeline():'''
R4_ANCHOR_NEW = '''def part_responsiveness():
    """v0.76: did the window itself stop answering? Separates the two readings
    that the 07:28 run could not tell apart - 'the user killed a live process'
    from 'the message thread hung while the render thread kept presenting'."""
    print()
    print("=" * 78)
    print("0e. Window responsiveness (v0.76: msg= / alive=)")
    print("=" * 78)

    recs = parse_wd_file(WATCHDOG) if os.path.exists(WATCHDOG) else []
    runs = _split_wd_runs(recs) if recs else []
    if not runs:
        print("  [信息]看门狗文件里没有记录。")
        return
    cur = runs[-1]
    have = [r for r in cur if r.get("msg") is not None]
    if not have:
        print("  [信息]本次运行段 {} 个 tick 全都没有 msg=/alive= 字段".format(len(cur)))
        print("         => 这次跑的不是 v0.76+。（该字段由 v0.76 引入，")
        print("            判据：需 v0.76+ 再跑一次才能给出结论。）")
        return

    dead = [r for r in have if r.get("alive") == 0]
    hung = [r for r in have if r.get("alive") == 1 and r.get("msg") == 0]
    ok = [r for r in have if r.get("alive") == 1 and r.get("msg") == 1]
    print("  [信息]本次运行段 {} 个 tick，其中 {} 个带窗口探测".format(len(cur), len(have)))
    print("         alive=1 且 msg=1（窗口在应答）：{}".format(len(ok)))
    print("         alive=1 且 msg=0（**窗口不应答 = 真正的无响应**）：{}".format(len(hung)))
    print("         alive=0（窗口已消失）：{}".format(len(dead)))

    if hung:
        first = hung[0]
        last = hung[-1]
        print("  [问题]窗口消息泵停止应答 {} 次 —— 这就是玩家说的「卡死」，".format(len(hung)))
        print("         也是 Windows 画「程序未响应」的同一个判据（USER32 自己用的就是它）。")
        print("         首次 {}（frames={} silent={}ms stage={}）".format(
            first["wall"], first["frames"], first["silent"], first["stage"]))
        print("         末次 {}（frames={} silent={}ms stage={}）".format(
            last["wall"], last["frames"], last["silent"], last["stage"]))
        # The render thread state at the moment the window went deaf is the
        # whole point of the field: a silent render thread points at the render
        # path, a loud one points at whatever else owns the message thread.
        if last["silent"] > 1500:
            print("         ⇒ 窗口失聪时**渲染线程同时是哑的**（silent {} ms）".format(last["silent"]))
            print("            → 卡死在渲染路径上，stage={} 是最后写入的标记。".format(last["stage"]))
        else:
            print("         ⇒ 窗口失聪时**渲染线程仍在出帧**（silent {} ms，frames={}）".format(
                last["silent"], last["frames"]))
            print("            → 渲染路径是活的，卡的是**消息线程**（别的插件 / 引擎主线程）。")
            print("               这一条是渲染侧任何改法都修不到的，必须查谁在占用主线程。")
    else:
        print("  [OK] 全程窗口都在应答消息 ⇒ 用户看到的不是「无响应」型卡死。")

    if dead and dead[-1]["frames"] >= 60:
        print("  [信息]窗口消失发生在 frames={}（>60 = 帧循环已经跑顺过）".format(dead[-1]["frames"]))
    if not dead:
        print("  [信息]窗口全程存在 ⇒ 进程是被外部 TerminateProcess 结束的，")
        print("         而不是自己退出（自己退出会走到窗口销毁并留下 alive=0）。")


def part_gpu_timeline():'''

EDITS = [
    ("R1 regex", READER, R1_OLD, R1_NEW),
    ("R2 dict fields", READER, R2_OLD, R2_NEW),
    ("R3 field doc", READER, R3_OLD, R3_NEW),
    ("R4 new section", READER, R4_ANCHOR_OLD, R4_ANCHOR_NEW),
]
# R4's anchor is INSERTED BEFORE, which does not consume it -> needs its own
# guard. The section header is unique to this patch.
MARKERS = ["0e. Window responsiveness (v0.76"]

CANARIES = [
    (READER, 'r"(?:\\s+msg=(?P<msg>\\d+))?"', 1),
    (READER, '"alive": int(g["alive"]) if g.get("alive") is not None else None', 1),
    (READER, "def part_responsiveness():", 1),
    (READER, "0e. Window responsiveness (v0.76: msg= / alive=)", 1),
    # the definition line is "def part_responsiveness():" which does NOT contain
    # the bare call form, so the call must be counted separately
    (READER, "    part_responsiveness()", 1),
]


def main():
    apply = "--apply" in sys.argv
    text = open(READER, encoding="utf-8").read()

    for m in MARKERS:
        if m in text:
            print("REFUSED: marker already present: %r" % m)
            return 2

    # ---- also need main() to call the new section
    step5 = "    part_responsiveness()"
    call_anchor = "    part_gpu_timeline()"
    if call_anchor not in text:
        print("REFUSED: cannot find the part_gpu_timeline() call in main()")
        return 1

    for label, path, old, new in EDITS:
        n = text.count(old)
        if n != 1:
            print("REFUSED: %s -- anchor found %d times (need 1)" % (label, n))
            return 1

    for label, path, old, new in EDITS:
        text = text.replace(old, new, 1)
        print("applied: %s" % label)

    # wire the new section into main(), right after the GPU timeline one
    text = text.replace(call_anchor, call_anchor + "\n" + step5, 1)
    print("applied: R5 main() wiring")

    # ---- structural check ----
    # Counting brackets is NOT a valid assertion for Python source: the baseline
    # file itself has [ 496 / ] 497 because a regex or string literal may contain
    # one without the other (verified: ast.parse(baseline) is clean). The only
    # trustworthy check for a .py patch is the parser itself.
    try:
        ast.parse(text)
    except SyntaxError as e:
        print("REFUSED: patched reader is not valid Python: line %s: %s" % (e.lineno, e.msg))
        return 1
    print("syntax check: ast.parse OK")

    for path, needle, want in CANARIES:
        got = text.count(needle)
        if got != want:
            print("REFUSED: canary %r found %d times (want %d)" % (needle[:55], got, want))
            return 1

    if not apply:
        print("\nDRY RUN - pass --apply to write.")
        return 0

    data = text.encode("utf-8")
    with open(READER, "wb") as fh:
        fh.write(data)
    print("wrote read_xray_log.py")

    print("\n--- verification (independent re-read) ---")
    disk = open(READER, encoding="utf-8").read()
    bad = 0
    for path, needle, want in CANARIES:
        got = disk.count(needle)
        if got != want:
            bad += 1
        print("  [%s] %-52s %d (want %d)" % ("OK " if got == want else "BAD", needle[:52], got, want))
    print("RESULT: %s" % ("OK" if bad == 0 else "%d failures" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
