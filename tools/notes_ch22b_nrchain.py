#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notes_ch22b_nrchain.py -- record the L0-second-pass catch (missing INI key) in
the two append-only ledgers.

Targets
  A) D:/Modding/DynamicShaderFrameGen/MFG_MASTER_NOTES.md          -> new chapter 23
  B) <workspace>/.workbuddy/memory/2026-09-19.md                   -> new section 6.11

Rules honoured
  * append only, never rewrite
  * marker string guard -> a second run is REFUSED (append does not consume its anchor)
  * EOL taken from each FILE, post-conditions checked on the RESULT text
  * dry run unless --apply
"""

import os
import sys

CWD = "D:/Modding/DynamicShaderFrameGen"
LEDGER = os.path.join(CWD, "MFG_MASTER_NOTES.md")
DAILY = ("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/"
         "2026-09-19.md")

MARK_A = "## 23. 第 23 章"
MARK_B = "### 6.11"

CHAPTER = """
---

## 23. 第 23 章　v1.09 交付前的 L0 第二遍：线上 INI 少了一个键（2026-09-19 11:25）

### 23.1 我在第 22 章里写了假话
- 第 22 章正文（本文件 **2450 行**、**2559 行**）**两次**写「INI 仍是
  `Provider=1 / MFGMaxFramesOverride=3 / NRAllowWithFrameGen=1`」。
- **实测（2026-09-19 11:25，只读）**：线上
  `E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.ini`
  **第 222 行是 `NRAllowWithFrameGen=0`**。
- 判定不是"我看错"：`tools/patch_ini_4x_run.py:47-52` 自己声明了后置条件，跑在线上文件上得 **False**：

```
count(Provider=1)              = 1
count(MFGMaxFramesOverride=3)  = 1
count(NRAllowWithFrameGen=1)   = 0     <-- 它自己的脚本要求恰好 1
PATCH-POSTCONDITION SATISFIED: False
```

- 且改动前的线上 INI md5 `ed9655ad2bd0d2576d7f7e9d200a3f4c`，
  **与 `ini.bak_20260919_090521` 逐字节相同**（14525 B，CRLF 259 / 裸 LF 0）
  ⇒ 11:17:57 那次写入是**把 10:56 的成果回退成了 09:05 的旧状态**，
  **不是"我从来没改对"**。至于是谁写的（我 / 用户）——**未证，不猜**。

### 23.2 后果：如果就这样起游戏，DLSS5 一定不跑
`DX12SwapChain.cpp` 同一条链上三行，全部已回读确认：

| 行 | 代码 | 代入现值 |
|---|---|---|
| `:1161` | `fgGeneratingNow = dlssgMode && fg.settings.frameGeneration && fg.fgActive` | `Provider=1`+`FrameGeneration=1` ⇒ **true** |
| `:1179` | `nrSuppressed = fgGeneratingNow && !fg.settings.nrAllowWithFrameGen` | ⇒ **true** |
| `:1203` | `if (fg.settings.neuralRenderingEnabled && !nrSuppressed) { …NR 真正执行… }` | ⇒ **整段跳过** |

⇒ **4x 会跑，DLSS5 静默不跑** —— 正好是用户目标的相反面，又是一趟白跑。
`:1180` 那个分支只会打一行 `DLSSNR suppressed` 警告，不会自愈。

### 23.3 处置（已落盘）
`NRAllowWithFrameGen 0 → 1`。断言脚本：锚点 `\\r\\nNRAllowWithFrameGen=0\\r\\n` 的 `count==1`，
先备份 `.bak_before_nrchain_20260919_112507`，等长替换（14525 B 不变），
纯 CRLF **259** / 裸 LF **0** 保住，后置条件查结果文本，新 md5
**`a19307d47caeb513b9ef6a16c4a83a42`**。

> 注：这个 md5 与第 22 章记的那一个**一致** ⇒ 反过来证明 10:56 那次内容确实是对的，
> 是后来被回退的，而不是我没改成。

### 23.4 ★ 新铁律 L26（对 L0 第二遍的加强）
**「INI 写对了」≠「代码执行了」。**
`NRAllowWithFrameGen=1` 只是**允许**链式执行；真正证明 DLSS5 与 FG 同时在跑的**唯一**证据，
是日志里这一行：

```
[FrameGen] DLSSNR CHAINED with frame generation (v1.01, NRAllowWithFrameGen=1)
```

**它不出现 ⇒ 别读后面的日志，先回来查这一行。**

**推论（这条是本章真正的收获）：**
L0 第二遍里「用户会不会白跑一趟」这一问，**必须落到配置文件的实际字节上核**，
不能凭"我这轮改过它"的记忆。
**记忆不是证据；后置条件跑在文件上才是。**
"""

DAILY_BODY = """
### 6.11 11:25　L0 第二遍拦下一次白跑：线上 INI 少了 `NRAllowWithFrameGen`（本轮第二次救场）

**怎么发现的：** 交付前我按 L0 第二遍问"用户会不会白跑一趟"，于是把
`tools/patch_ini_4x_run.py` **自己声明的后置条件**跑在**线上文件**上，而不是回忆我改过什么。

```
count(Provider=1)              = 1   ok
count(MFGMaxFramesOverride=3)  = 1   ok
count(NRAllowWithFrameGen=1)   = 0   FAIL   <-- 脚本要求恰好 1
PATCH-POSTCONDITION SATISFIED: False
```

**后果链（`DX12SwapChain.cpp`，三行已逐一回读）：**
`:1161 fgGeneratingNow=true` → `:1179 nrSuppressed=true` →
`:1203 if (neuralRenderingEnabled && !nrSuppressed)` **整段跳过**。
⇒ 那样起游戏 = **4x 跑起来、DLSS5 静默不跑** = 用户目标的相反面。

**旁证：** 改前线上 INI md5 `ed9655ad…` 与 `ini.bak_20260919_090521` 逐字节相同
⇒ 11:17:57 那次写入是**把 10:56 的成果回退成 09:05 的旧状态**。
是谁写的（我 / 用户）**未证，不猜**。

**已修：** `NRAllowWithFrameGen 0→1`，断言脚本 + 先备份 `.bak_before_nrchain_20260919_112507`
+ 等长替换 14525 B + 纯 CRLF 259/裸 LF 0 保住，新 md5 `a19307d4…`
（与第 22 章记录一致 ⇒ 反过来证明 10:56 那次内容本来就对）。

**新增判据（唯一）：** 日志出现
`[FrameGen] DLSSNR CHAINED with frame generation (v1.01, NRAllowWithFrameGen=1)`
才算 DLSS5 与 FG 同时在跑。**INI 的值不是代码执行过的证据。**
"""


def file_eol(path):
    with open(path, "rb") as f:
        b = f.read()
    crlf = b.count(b"\r\n")
    return "\r\n" if crlf > (b.count(b"\n") - crlf) else "\n"


def append(path, marker, body, must_contain):
    if not os.path.exists(path):
        print(f"REFUSED: missing {path}")
        return 1
    eol = file_eol(path)
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")

    if marker in text:
        print(f"REFUSED: marker already present in {os.path.basename(path)}")
        return 1

    add = body.replace("\n", eol)
    if not text.endswith(eol):
        add = eol + add
    out_text = text + add

    missing = [s for s in must_contain if s not in out_text]
    print(f"  {os.path.basename(path):22s} {len(raw)} -> {len(out_text.encode('utf-8'))} B"
          f"   eol={eol!r}   postcondition={'PASS' if not missing else 'FAIL ' + str(missing)}")
    if missing:
        print("REFUSED, nothing written")
        return 3

    if not apply:
        return 0
    with open(path, "wb") as f:
        f.write(out_text.encode("utf-8"))
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    rc = 0
    rc |= append(LEDGER, MARK_A, CHAPTER, [
        "## 23. 第 23 章",
        "NRAllowWithFrameGen=0",
        "PATCH-POSTCONDITION SATISFIED: False",
        "a19307d47caeb513b9ef6a16c4a83a42",
        "L26",
        "DLSSNR CHAINED with frame generation",
    ])
    rc |= append(DAILY, MARK_B, DAILY_BODY, [
        "### 6.11",
        "PATCH-POSTCONDITION SATISFIED: False",
        "a19307d4",
        "DLSSNR CHAINED with frame generation",
    ])
    if rc:
        print("one or more targets REFUSED")
        sys.exit(rc)
    print("DRY RUN ok -- re-run with --apply" if not apply else "written")
