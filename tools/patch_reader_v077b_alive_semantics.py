#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v0.77 part 2: fix the two remaining mis-readings in read_xray_log.py.

1. Section header still says "(v0.76: msg= / alive=)" and the burst classifier
   prints two lines that no longer match the implementation's own vocabulary.
   More importantly: `alive=0` is reported as "窗口已消失" and then the summary
   claims "进程是被外部 TerminateProcess 结束的". Both are wrong for the 08:27
   run - the four alive=0 ticks sit at 08:27:34, i.e. BEFORE the first Present
   ever published a hwnd, so alive=0 there simply means "no window handle to
   probe yet". The session actually ends at 08:29:09.8 with
   `[DMK] WM_ACTIVATEAPP: Game lost focus` -> the user left / alt-tabbed.

2. The exit summary in `main()` should not conclude "killed externally" when
   the four alive=0 samples are all in the startup window.

Dry run by default; --apply to write.
"""
import os
import sys
import shutil
import datetime
import ast

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, "read_xray_log.py")

# ---- 1. header wording ----
OLD_HDR = '''    print("0e. Window responsiveness (v0.76: msg= / alive=)")'''
NEW_HDR = '''    print("0e. Window responsiveness (v0.77: msg= / alive=, classified)")'''

# ---- 2. alive=0 semantics: it is not "window disappeared" until a hwnd exists ----
OLD_ALIVE = '''    dead = [r for r in have if r.get("alive") == 0]
    hung = [r for r in have if r.get("alive") == 1 and r.get("msg") == 0]
    ok = [r for r in have if r.get("alive") == 1 and r.get("msg") == 1]
    print("  [信息]本次运行段 {} 个 tick，其中 {} 个带窗口探测".format(len(cur), len(have)))
    print("         alive=1 且 msg=1（窗口在应答）：{}".format(len(ok)))
    print("         alive=1 且 msg=0（窗口不应答，需进一步分类）：{}".format(len(hung)))
    print("         alive=0（窗口已消失）：{}".format(len(dead)))
'''
NEW_ALIVE = '''    dead = [r for r in have if r.get("alive") == 0]
    hung = [r for r in have if r.get("alive") == 1 and r.get("msg") == 0]
    ok = [r for r in have if r.get("alive") == 1 and r.get("msg") == 1]
    print("  [信息]本次运行段 {} 个 tick，其中 {} 个带窗口探测".format(len(cur), len(have)))
    print("         alive=1 且 msg=1（窗口在应答）：{}".format(len(ok)))
    print("         alive=1 且 msg=0（窗口不应答，需进一步分类）：{}".format(len(hung)))
    print("         alive=0（还没拿到 hwnd，无法探测）：{}".format(len(dead)))

    # v0.77: alive=0 has TWO meanings and the summary used to conflate them.
    # The hwnd is published by the first Present, so every probe before that
    # frame reports alive=0. Only alive=0 AFTER the window has been seen at
    # least once means the window really went away.
    saw_alive = False
    dead_late = []
    dead_early = 0
    for r in have:
        if r.get("alive") == 1:
            saw_alive = True
        elif saw_alive:
            dead_late.append(r)
        else:
            dead_early += 1
    if dead_early:
        print("         其中 {} 次发生在**首个 Present 之前**（hwnd 还没发布，不是窗口消失）".format(dead_early))
    if dead_late:
        print("         {} 次发生在窗口已出现过之后 ⇒ 这一次才是真的窗口消失".format(len(dead_late)))
'''

# ---- 3. the "killed externally" conclusion ----
OLD_KILLED = '''    if dead and dead[-1]["frames"] >= 60:
        print("  [信息]窗口消失发生在 frames={}（>60 = 帧循环已经跑顺过）".format(dead[-1]["frames"]))
    if not dead:
        print("  [信息]窗口全程存在 ⇒ 进程是被外部 TerminateProcess 结束的，")
        print("         而不是自己退出（自己退出会走到窗口销毁并留下 alive=0）。")
'''
NEW_KILLED = '''    if dead_late:
        print("  [信息]窗口在 frames={} 之后消失".format(dead_late[0]["frames"]))
    else:
        print("  [信息]窗口全程存在（{} 次 alive=0 全在首个 Present 之前）".format(dead_early))
        print("         ⇒ 看门狗文件只是**在窗口仍活着时停止了追加**。")
        print("            这通常意味着进程在记录点之后才被结束/退出 —— 结合主日志的时刻判读，")
        print("            不要仅凭 alive 推断是被 TerminateProcess 杀掉的。")
'''

EDITS = [
    ("section header label", OLD_HDR, NEW_HDR),
    ("alive=0 semantics (early vs late)", OLD_ALIVE, NEW_ALIVE),
    ("exit conclusion", OLD_KILLED, NEW_KILLED),
]

CANARIES = [
    ("    dead_late = []", 1),
    ("    if dead_late:", 2),
    ("         alive=0（还没拿到 hwnd，无法探测）：{}", 1),
    ("0e. Window responsiveness (v0.77: msg= / alive=, classified)", 1),
]

MARKERS = [
    "v0.77: alive=0 has TWO meanings and the summary used to conflate them",
    "hwnd 还没发布，不是窗口消失",
]


def main():
    apply = "--apply" in sys.argv
    src = open(READER, "r", encoding="utf-8", newline="").read()
    for m in MARKERS:
        if m in src:
            print("REFUSED: marker already present -> patch already applied: %r" % m)
            return 2

    text = src
    for label, old, new in EDITS:
        n = text.count(old)
        if n != 1:
            print("REFUSED: anchor for %r found %d times (want exactly 1)" % (label, n))
            return 2
        text = text.replace(old, new)

    for c, want in CANARIES:
        n = text.count(c)
        if n != want:
            print("REFUSED: canary %r found %d times (want %d)" % (c, n, want))
            return 2

    for m in MARKERS:
        if m not in text:
            print("REFUSED: marker missing after patch: %r" % m)
            return 2

    try:
        ast.parse(text)
    except SyntaxError as e:
        print("REFUSED: not parseable after patch: %s" % e)
        return 2

    if ("\r\n" in src) != ("\r\n" in text):
        print("REFUSED: line-ending style changed")
        return 2

    if not apply:
        print("[dry-run] all 3 anchors unique, canaries OK, ast.parse OK")
        print("[dry-run] bytes %d -> %d (%+d)" % (len(src), len(text), len(text) - len(src)))
        print("[dry-run] re-run with --apply to write")
        return 0

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = "%s.bak-%s" % (READER, stamp)
    shutil.copy2(READER, bak)
    with open(READER, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print("applied to %s" % READER)
    print("backup: %s" % bak)
    print("bytes %d -> %d (%+d)" % (len(src), len(text), len(text) - len(src)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
