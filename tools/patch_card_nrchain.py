#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_card_nrchain.py -- add the L0-second-pass catch to the user-facing card.

WHY THIS FILE EXISTS
--------------------
While re-verifying "did the user get what he asked for" before telling him to
launch, the deployed INI failed its OWN patch script's post-condition:

    tools/patch_ini_4x_run.py  declares NRAllowWithFrameGen=1 as REQUIRED
    deployed INI (before this patch):  Provider=1, MFGMaxFramesOverride=3,
                                       NRAllowWithFrameGen=0   <-- missing

Consequence with line numbers (DX12SwapChain.cpp):
    :1161 fgGeneratingNow = dlssgMode && frameGeneration && fgActive   -> true
    :1179 nrSuppressed    = fgGeneratingNow && !nrAllowWithFrameGen    -> true
    :1203 if (neuralRenderingEnabled && !nrSuppressed) { ...NR runs... }  -> SKIPPED

So the run would have produced 4x WITH DLSS5 SILENTLY OFF -- the exact opposite
of the stated goal, and another wasted launch.  The INI has been fixed
(NRAllowWithFrameGen 0 -> 1, md5 a19307d4...).  This script records that on the
card, plus the only valid proof that the switch took effect (the CHAINED log
line -- an INI value is not evidence that code executed).

CONVENTIONS (project iron law)
------------------------------
* dry run by default; --apply writes, --revert undoes.
* anchor count(old) must be exactly 1 else REFUSED, nothing written.
* EOL taken from the FILE, never from the anchor.
* idempotency: an explicit marker string REJECTS a second run.
* post-conditions are evaluated on the RESULT text.
"""

import sys

CARD = "docs/diagnosis-20260919-v109.html"

MARKER = "L0 第二遍·脑子拦下的一次白跑"

OLD_SUB = ('v1.09-diag &nbsp;·&nbsp; 2026-09-19 11:1x &nbsp;·&nbsp; '
           'DLL 1,335,296 B')
NEW_SUB = ('v1.09-diag &nbsp;·&nbsp; 2026-09-19 11:25（含 INI 三键复核）&nbsp;·&nbsp; '
           'DLL 1,335,296 B')

OLD_MTIME = ('日志 mtime <span class="mono">10:04:39</span> &lt; INI 落盘 '
             '<span class="mono">10:56:31</span>。')
NEW_MTIME = ('日志 mtime <span class="mono">10:04:39</span> &lt; INI 落盘 '
             '<span class="mono">11:25:07</span>。')

ANCHOR = '<h2>一、冻结机制（确证，非推断）</h2>'

INSERT = """<h2 style="border-left-color:var(--amb)">零、★ L0 第二遍·脑子拦下的一次白跑：DLSS5 的开关被关着</h2>
<div class="card" style="border-left:4px solid var(--amb)">
<b>切 4x 要三个键，线上 INI 只落了两个。</b>我用 <code>tools/patch_ini_4x_run.py</code>
<b>自己声明的后置条件</b>复核线上文件，结果是 False：
<pre>count(Provider=1)              = 1   ok
count(MFGMaxFramesOverride=3)  = 1   ok
count(NRAllowWithFrameGen=1)   = 0   FAIL  &lt;-- 它自己的脚本要求恰好 1
PATCH-POSTCONDITION SATISFIED: False
md5 = ed9655ad...  (14525 B)  ==  ini.bak_20260919_090521 逐字节相同
                              ==&gt; 11:17:57 被回退过，不是"一直没改对"</pre>
后果链（全部带行号，<span class="mono">DX12SwapChain.cpp</span>）：
<code>Provider=1</code> + <code>FrameGeneration=1</code>
=&gt; <code>fgGeneratingNow=true</code>(<code>:1161</code>)
=&gt; <code>nrSuppressed=true</code>(<code>:1179</code>)
=&gt; <code>if (neuralRenderingEnabled &amp;&amp; !nrSuppressed)</code>(<code>:1203</code>) <b>整段跳过</b>。
<br>⇒ 那样起游戏：<b class="r">4x 会跑，DLSS5 一定不跑</b> —— 正好是目标的反面，又是一趟白跑。
<br><b class="g">已修：</b><code>NRAllowWithFrameGen 0 → 1</code>。断言脚本、锚点 count==1、先备份
<code>.bak_before_nrchain_20260919_112507</code>、等长替换（14525 B 不变）、
纯 CRLF 259 / 裸 LF 0 保住、新 md5 <span class="mono">a19307d4…</span>。
</div>
<div class="card" style="border-left:4px solid var(--red)">
<b>但「INI 写对了」≠「DLSS5 真跑了」。</b>唯一判据是日志里这一行：
<pre>[FrameGen] DLSSNR CHAINED with frame generation (v1.01, NRAllowWithFrameGen=1)</pre>
它不出现 ⇒ 开关没生效，后面都不用读了。<b>INI 的值不是代码执行过的证据，这是两件事。</b>
</div>

"""

# (label, old, new, expected_result_count_of_new)
PLAN = [
    ("sub_date",  OLD_SUB,   NEW_SUB,   1),
    ("log_mtime", OLD_MTIME, NEW_MTIME, 1),
    ("section0",  ANCHOR,    INSERT + ANCHOR, 1),
]


def file_eol(path):
    """EOL is decided by the FILE, never by the anchor (single-line anchors
    contain no newline, so the anchor cannot tell us)."""
    with open(path, "rb") as f:
        b = f.read()
    crlf = b.count(b"\r\n")
    bare = b.count(b"\n") - crlf
    return "\r\n" if crlf > bare else "\n"


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    with open(CARD, "rb") as f:
        raw = f.read()
    eol = file_eol(CARD)
    text = raw.decode("utf-8")

    if not revert and MARKER in text:
        print(f"REFUSED: marker already present ({MARKER!r}) -- patch already applied")
        return 1

    edits = []
    for label, old, new, _ in PLAN:
        old_l = old.replace("\n", eol)
        new_l = new.replace("\n", eol)
        n = text.count(old_l)
        print(f"  {label:10s} anchor count = {n}")
        if n != 1:
            print(f"REFUSED, nothing written  (label={label}, count={n}, want 1)")
            return 2
        edits.append((label, old_l, new_l))

    if revert:
        for label, old_l, new_l in edits:
            if text.count(new_l) != 1:
                print(f"REFUSED, nothing written  (revert: {label} not found once)")
                return 4
            text = text.replace(new_l, old_l, 1)
    else:
        for label, old_l, new_l in edits:
            text = text.replace(old_l, new_l, 1)

    # ---- post-conditions on the RESULT text ----
    checks = [
        (not revert, "marker present",       (MARKER in text)),
        (not revert, "three keys quoted",    ("NRAllowWithFrameGen=1" in text)),
        (not revert, "line numbers cited",   ("1179" in text and "1203" in text and "1161" in text)),
        (not revert, "md5 shown",            ("a19307d4" in text)),
        (not revert, "CHAINED judgement",    ("DLSSNR CHAINED with frame generation" in text)),
        (not revert, "no stale 10:56:31",    ("10:56:31" not in text)),
        (revert,     "marker gone",          (MARKER not in text)),
    ]
    failed = [name for want, name, got in checks if want and not got]
    print("post-conditions:", "PASS" if not failed else f"FAIL {failed}")
    if failed:
        print("REFUSED, nothing written")
        return 3

    if not apply:
        print("DRY RUN ok -- re-run with --apply to write")
        return 0

    out = text.encode("utf-8")
    with open(CARD, "wb") as f:
        f.write(out)
    print(f"written: {len(raw)} B -> {len(out)} B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
