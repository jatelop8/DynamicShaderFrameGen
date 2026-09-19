#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notes_l27_ini_source.py -- record the INI revert mechanism (iron law L27).

Append-only, marker-guarded, EOL from each file, post-conditions on the result.
"""

import os
import sys

CWD = "D:/Modding/DynamicShaderFrameGen"
LEDGER = os.path.join(CWD, "MFG_MASTER_NOTES.md")
DAILY = ("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/.workbuddy/memory/"
         "2026-09-19.md")

MARK_A = "### 24.11"
MARK_B = "### 6.13"

A = """
### 24.11 ★★★ L27：改部署目录的 INI 是白改 —— **部署源在仓库里**

**怎么发现的**：交付前的 L0 第二遍，我按惯例复核"用户起游戏时读到的 INI"，第 222 行又是
`NRAllowWithFrameGen=0`。而我 11:25 明明把它改成了 1，md5 也验过是 `a19307d4`。

**根因（`CMakeLists.txt` POST_BUILD，逐行读出来的）：**
```cmake
add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_SOURCE_DIR}/SKSE/Plugins/DynamicShaderFrameGen.ini"
        "${PLUGIN_DEPLOY_DIR}/SKSE/Plugins/DynamicShaderFrameGen.ini" )
```
**仓库里的那一份才是部署源。** 手工改部署目录 = 下一次构建被覆盖回去。

**md5 实证（2026-09-19 11:48）：**
```
repo     SKSE/Plugins/DynamicShaderFrameGen.ini        ed9655ad2bd0d2576d7f7e9d200a3f4c   NRAllowWithFrameGen=0
deployed E:/EJ/mod/mods/.../DynamicShaderFrameGen.ini  ed9655ad2bd0d2576d7f7e9d200a3f4c   NRAllowWithFrameGen=0
```
两份**逐字节相同**，且都还是 0 ⇒ 11:25 那次修复（`a19307d4`）被 11:45 的构建盖掉了。
**这也解释了当天 11:17:57 的那次"神秘回退"**：`ini.bak_20260919_090521` 的 md5 `ed9655ad`
之所以与当时的部署文件相同，不是因为"我从来没改对"，而是因为**构建把仓库那份复制了过来**，
而仓库那份一直没动。

**第二个坑（同一次踩到）：`copy_if_different` 只在 DLL 重新链接时才执行。**
我改完仓库 INI 后跑 `build_vs.sh`，DLL 是最新的 ⇒ ninja 不重新链接 ⇒ **POST_BUILD 不跑** ⇒
部署目录仍是旧 md5 `ed9655ad`。**"我构建了" ≠ "INI 重新部署了"。**

**处置：**
1. 仓库 INI `NRAllowWithFrameGen 0→1`（锚点 count==1、等长替换 14525 B、纯 CRLF 259/0、
   备份 `.bak_before_nrchain_20260919_114858`），md5 → **`a19307d47caeb513b9ef6a16c4a83a42`**。
2. 新增 `tools/deploy_ini.sh`：无条件复制 + **核 md5 一致** + 逐条打印决定 4x/DLSS5 的键。
   **改 INI 后必须跑它，不许只跑构建。**
3. 复核结果：repo 与 deployed 均为 `a19307d4`，`Provider=1 / FrameGeneration=1 /
   NeuralRenderingEnabled=1 / DLSSGFramesToExecute=3 / MFGMaxFramesOverride=3 /
   NRAllowWithFrameGen=1`。

**⇒ 新铁律 L27：部署源在仓库，不在部署目录。判据永远是 `md5(repo) == md5(deployed)`，
不是"我改过"。**
"""

B = """
### 6.13 11:48　L0 第二遍又拦下一次白跑：INI 被自己的构建脚本盖回去了（L27）

交付前复核"用户起游戏时读到的 INI"，第 222 行**又是** `NRAllowWithFrameGen=0`，
而我 11:25 改成 1 并验过 md5 `a19307d4`。

**根因**：`CMakeLists.txt` 的 POST_BUILD 用 **`CMAKE_SOURCE_DIR/SKSE/Plugins/DynamicShaderFrameGen.ini`**
（仓库那份）`copy_if_different` 到部署目录。**仓库那份才是部署源**，一直是 `=0`。
实测两份 md5 **逐字节相同**（都是 `ed9655ad`）⇒ 11:45 的构建把 11:25 的修复盖掉了。
**当天 11:17:57 那次"神秘回退"也是同一个机制**，不是"我从来没改对"。

**第二个坑**：`copy_if_different` 只在 **DLL 重新链接**时才跑；我改完仓库 INI 再 `build_vs.sh`，
DLL 是最新的 ⇒ 不链接 ⇒ POST_BUILD 不跑 ⇒ 部署目录仍是旧 md5。**"我构建了" ≠ "INI 部署了"。**

**处置**：仓库 INI `0→1`（md5 → `a19307d4…`）；新增 `tools/deploy_ini.sh`
（无条件复制 + 核 md5 + 打印决定 4x/DLSS5 的键）；两份复核一致，五键全对
（`Provider=1 / FrameGeneration=1 / NeuralRenderingEnabled=1 / DLSSGFramesToGenerate=3 /
MFGMaxFramesOverride=3 / NRAllowWithFrameGen=1`）。

**L27：部署源在仓库，不在部署目录。判据是 `md5(repo)==md5(deployed)`，不是"我改过"。**
"""


def file_eol(path):
    with open(path, "rb") as f:
        b = f.read()
    crlf = b.count(b"\r\n")
    return "\r\n" if crlf > (b.count(b"\n") - crlf) else "\n"


def append(path, marker, body, must, apply):
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
    out = text + add
    missing = [s for s in must if s not in out]
    print(f"  {os.path.basename(path):22s} {len(raw)} -> {len(out.encode('utf-8'))} B"
          f"  eol={eol!r}  post={'PASS' if not missing else 'FAIL ' + str(missing)}")
    if missing:
        print("REFUSED, nothing written")
        return 3
    if apply:
        with open(path, "wb") as f:
            f.write(out.encode("utf-8"))
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    rc = 0
    rc |= append(LEDGER, MARK_A, A, [
        "### 24.11", "L27", "ed9655ad2bd0d2576d7f7e9d200a3f4c",
        "copy_if_different", "deploy_ini.sh", "a19307d47caeb513b9ef6a16c4a83a42",
    ], apply)
    rc |= append(DAILY, MARK_B, B, ["### 6.13", "L27", "deploy_ini.sh", "a19307d4"], apply)
    if rc:
        sys.exit(rc)
    print("DRY RUN ok -- re-run with --apply" if not apply else "written")
