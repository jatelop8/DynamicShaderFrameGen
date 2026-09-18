#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append two cross-project patch-script rules to the user-level MEMORY.md."""

import shutil
import sys
import time

TARGET = r"C:/Users/Administrator/.workbuddy/MEMORY.md"
MARKER = "## 补丁脚本读数/判空两条硬规则（2026-09-17 固化，跨项目）"

BODY = r"""

## 补丁脚本读数/判空两条硬规则（2026-09-17 固化，跨项目）

**① 按文件选编码，不要一律 latin-1。**
锚点里带中文时，用 `latin-1` 读目标文件会让锚点**永远匹配不到**（干跑报 `anchor x0`）——
`latin-1` 把中文逐字节映射成乱码字符，而脚本里的锚点是正常 Unicode，两者永不相等。实测：
`fix_reader_uicheck_v071e.py` 第一版正是这么错的。
⇒ **规则**：UTF-8 源码（`.py` / `.md` / `.cpp`）按 **UTF-8** 读写；
「latin-1 保字节往返」只用于**本身不是 UTF-8** 的文件（ENB 的 `.ini` 含日韩文注释）。
两种文件混着改时，`open(..., encoding=...)` 必须按文件走，不能设一次全局。

**② `X == 0` 意图的检查必须**解析数值**，不能用字符串包含。**
读取器里 `if "ui=0" in raw or "ui=0x0" in raw:` —— 而 `"ui=0"` 是 `"ui=0x7ff745c3ceb0"`
的**前缀** ⇒ 每次正常运行都被判成「单例为空」，还和自己上一行输出的「布局正确」直接矛盾，
并进了总结（会让人去追一个不存在的问题）。
⇒ **规则**：所有判空/判坏一律 `re.search(r"\bui=(0x[0-9a-fA-F]+|\d+)", raw)` + `int(v, 0) == 0`。
这是「金丝雀要写真实损伤特征」的镜像面：**判坏同样不能写会撞上健康输出的子串**。
"""


def main():
    apply_it = "--apply" in sys.argv
    with open(TARGET, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")

    if MARKER in text:
        print("REFUSED -- already appended")
        return 2

    anchor = text[-60:]
    n = text.count(anchor)
    print("bytes before: %d | tail anchor x%d" % (len(raw), n))
    if n != 1:
        print("REFUSED -- tail anchor not unique")
        return 2

    out = text + BODY
    if out.count(MARKER) != 1 or "fix_reader_uicheck_v071e.py" not in out:
        print("REFUSED -- post-conditions failed")
        return 2
    print("post-conditions OK | +%d bytes" % (len(out.encode("utf-8")) - len(raw)))

    if not apply_it:
        print("\nDRY RUN -- nothing written. Re-run with --apply")
        return 0

    shutil.copy2(TARGET, TARGET + ".bak-" + time.strftime("%Y%m%d_%H%M%S"))
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))
    back = open(TARGET, "rb").read().decode("utf-8")
    if back.count(MARKER) != 1:
        print("READBACK FAIL")
        return 3
    print("readback OK | %d bytes" % len(back.encode("utf-8")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
