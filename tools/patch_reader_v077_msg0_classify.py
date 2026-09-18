#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch part_responsiveness() in tools/read_xray_log.py.

WHY
---
The 08:27 run produced 115 msg=0 ticks. The existing verdict reads only
`last["silent"]` - the FINAL sample of the whole hung list - and on that single
number declares "the render path is alive, the message thread is the culprit".
That was wrong for this run: the 115 msg=0 ticks form exactly TWO bursts, and
inside the first burst `silent` climbs 932ms -> 19591ms, i.e. the render thread
was stopped too, because the game's main thread was inside a 19.7 s synchronous
load (`LONG FRAME 19707.4ms`).

So the field is right and the reading was wrong. `msg=0` alone cannot
distinguish these two very different states:

  A) main thread blocked in a load  -> frames barely move, silent is huge,
                                       msg=0 is a SYMPTOM of the same stall.
  B) message pump wedged while the render thread keeps presenting
                                   -> frames advance, silent is small,
                                       msg=0 is the ONLY anomaly.

The patch makes the section:
  1. group the msg=0 ticks into bursts (probe cadence gap > 5 ticks = new burst)
  2. classify every burst as LOAD-STALL (silent >= 1500ms) or PUMP-WEDGE
     (silent < 1500ms) and report them separately
  3. cross-check `alive` at the same time so "window gone" is not mixed in
  4. only then print a verdict, per burst class instead of per last sample

Structure of this script: EDITS + CANARIES + MARKERS, all assert-counted.
Dry run by default; pass --apply to write.
"""
import os
import sys
import shutil
import datetime
import ast

READER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "read_xray_log.py")

# ---------------------------------------------------------------- anchor text

OLD_TAIL = '''    dead = [r for r in have if r.get("alive") == 0]
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
'''

NEW_TAIL = '''    dead = [r for r in have if r.get("alive") == 0]
    hung = [r for r in have if r.get("alive") == 1 and r.get("msg") == 0]
    ok = [r for r in have if r.get("alive") == 1 and r.get("msg") == 1]
    print("  [信息]本次运行段 {} 个 tick，其中 {} 个带窗口探测".format(len(cur), len(have)))
    print("         alive=1 且 msg=1（窗口在应答）：{}".format(len(ok)))
    print("         alive=1 且 msg=0（窗口不应答，需进一步分类）：{}".format(len(hung)))
    print("         alive=0（窗口已消失）：{}".format(len(dead)))

    # ---- v0.77: msg=0 must never be judged on its own -------------------
    # msg=0 has two completely different causes and the watchdog line alone
    # cannot tell them apart. Group the ticks into bursts first: the watchdog
    # probes every 5 ticks, so a probe gap > 5 means the pump came back and
    # then went deaf again = a separate event.
    LOAD_STALL_MS = 1500

    def _bursts(seq):
        out = []
        run = []
        for r in seq:
            if run and (r["stim"] - run[-1]["stim"]) > 5:
                out.append(run)
                run = []
            run.append(r)
        if run:
            out.append(run)
        return out

    classes = []
    if hung:
        for b in _bursts(hung):
            frames_left = b[0]["frames"]
            frames_right = b[-1]["frames"]
            max_sil = max(x["silent"] for x in b)
            # A burst whose frame counter barely moved while silent is huge is
            # the game sitting in a synchronous load; msg=0 there is a symptom,
            # not the disease.
            load_like = (max_sil >= LOAD_STALL_MS) and (frames_right - frames_left) <= max(8, len(b) // 4)
            classes.append({
                "burst": b,
                "load": load_like,
                "max_sil": max_sil,
                "frames": (frames_left, frames_right),
            })

        n_load = sum(1 for c in classes if c["load"])
        n_wedge = len(classes) - n_load
        print("  [信息]msg=0 共 {} 次，聚成 {} 段（探针间隔>5 tick 视为新的一段）".format(
            len(hung), len(classes)))
        print("         {:<44} {:>3} 段".format("① 载入停顿（silent>=1500ms 且几乎不出帧）", n_load))
        print("         {:<44} {:>3} 段".format("② 消息泵卡死（silent<1500ms，渲染仍在出帧）", n_wedge))
        print()
        for i, c in enumerate(classes):
            b = c["burst"]
            st = {}
            for x in b:
                st[x["stage"]] = st.get(x["stage"], 0) + 1
            modal = sorted(st.items(), key=lambda kv: -kv[1])[0][0]
            tag = "①载入停顿" if c["load"] else "②消息泵卡死"
            print("         #{:<3} {}  {} -> {}  {:>2} 探测 {:>5.2f}s  帧 {:>5}->{:<5} "
                  "maxSil={:<6}ms  stage={}".format(
                      i, tag, b[0]["wall"][:12], b[-1]["wall"][:12], len(b),
                      b[-1]["ms"] / 1000.0 - b[0]["ms"] / 1000.0,
                      c["frames"][0], c["frames"][1], c["max_sil"], modal))

        # ---------------- verdict, per class ----------------
        print()
        for i, c in enumerate(classes):
            b = c["burst"]
            if c["load"]:
                # Find the LONG FRAME line that owns this burst, if the caller
                # has already parsed the main log; otherwise just quote silent.
                print("  [信息]段 #{} 是**载入停顿**：{} -> {}，期间只走了 {} 帧，"
                      "silent 峰值 {}ms。".format(
                          i, b[0]["wall"], b[-1]["wall"],
                          c["frames"][1] - c["frames"][0], c["max_sil"]))
                print("         窗口在载入期间不应答是**游戏自身同步加载**的正常表现，")
                print("         与 DFG 无关（渲染线程也停着，因为主线程没在喂它）。")
                print("         判据：silent>=1500ms 且帧数几乎不动 => 载入，不是卡死。")
            else:
                print("  [问题]段 #{} 是**消息泵卡死**：{} -> {}，帧 {:}->{} 仍在推进、"
                      "silent 只有 {}ms。".format(
                          i, b[0]["wall"], b[-1]["wall"],
                          c["frames"][0], c["frames"][1], c["max_sil"]))
                print("         ⇒ 渲染路径活着而窗口失聪 => 卡的是消息线程。")
                print("            这一条是渲染侧任何改法都修不到的，必须查谁在占用主线程。")

        if n_wedge == 0:
            print("  [OK] 没有任何一段属于「消息泵卡死」类 ⇒ msg=0 全部可由载入解释，")
            print("       DFG 侧无需改动（要缩短它只能减少 mod / 加快 IO）。")
        else:
            print("  [问题]存在 {} 段「消息泵卡死」⇒ 这一类才是真正需要查的。".format(n_wedge))
    else:
        print("  [OK] 全程窗口都在应答消息 ⇒ 用户看到的不是「无响应」型卡死。")
'''

CANARIES = [
    ("    dead = [r for r in have if r.get(\"alive\") == 0]", 1),
    ("    def _bursts(seq):", 1),
    ("    LOAD_STALL_MS = 1500", 1),
    ("    classes = []", 1),
    ("if c[\"load\"]:", 1),
]

MARKERS = [
    "v0.77: msg=0 must never be judged on its own",
    "① 载入停顿（silent>=1500ms 且几乎不出帧）",
    "② 消息泵卡死（silent<1500ms，渲染仍在出帧）",
]

EDITS = [
    ("part_responsiveness verdict: per-burst classification", OLD_TAIL, NEW_TAIL),
]


def structural_check(text, label):
    try:
        ast.parse(text)
    except SyntaxError as e:
        return "REFUSED: %s not parseable after patch: %s" % (label, e)
    for lu in (text.count("\\n"),):
        pass
    return None


def main():
    apply = "--apply" in sys.argv
    for m in MARKERS:
        if m in open(READER, "r", encoding="utf-8").read():
            print("REFUSED: marker already present -> patch has run before: %r" % m)
            return 2

    src = open(READER, "r", encoding="utf-8", newline="").read()
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

    err = structural_check(text, "read_xray_log.py")
    if err:
        print(err)
        return 2

    if text.count("\\n") and src.count("\\n") and (("\r\n" in src) != ("\r\n" in text)):
        print("REFUSED: line-ending style changed (src CRLF=%s -> new CRLF=%s)"
              % ("\r\n" in src, "\r\n" in text))
        return 2

    if not apply:
        print("[dry-run] all anchors unique, canaries OK, ast.parse OK")
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
