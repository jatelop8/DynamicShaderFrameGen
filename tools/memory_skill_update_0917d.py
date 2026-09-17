#!/usr/bin/env python3
"""
memory_skill_update_0917d.py - record the POST_BUILD auto-deploy trap.

Discovered while validating the v0.57 deployment: CMakeLists.txt:105-121 copies
the DLL, the INI and the Shaders directory into PLUGIN_DEPLOY_DIR after every
link. Two traps follow, and both cost a debugging round if unknown:

  * a manual DLL backup taken before deploying captures the already-deployed build
    (a "backup" that is actually the new binary - this happened here)
  * editing the deployed INI and rebuilding reverts the edit, because the repo INI
    is pushed back over it - which would silently undo the mvecScale A/B

Anchors must match exactly once; markers guard re-runs; line endings preserved.
"""
import sys

APPLY = "--apply" in sys.argv

SKILL = r"C:\Users\Administrator\.workbuddy\skills\framegen-diagnosis\SKILL.md"
MEM = r"C:\Users\Administrator\.workbuddy\MEMORY.md"
LOG = r"C:\Users\Administrator\WorkBuddy\2026-09-17-11-48-48\.workbuddy\memory\2026-09-17.md"

SKILL_ANCHOR = '另外 `cmd /c *.bat` 在 Bash 工具里会被安全策略拒（"Invoking cmd.exe from Bash"），改用 PowerShell。'

SKILL_ADD = """### ㉔ 工程自带 POST_BUILD 自动部署 ⇒ "手动备份 DLL" 备份到的是新文件，改 INI 后重建会被冲掉 ★2026-09-17 实锤

```cmake
# DX12SwapChain/CMakeLists.txt 尾部
if(DEFINED PLUGIN_DEPLOY_DIR)
    add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different  $<TARGET_FILE:${PROJECT_NAME}>  "${PLUGIN_DEPLOY_DIR}/SKSE/Plugins/<name>.dll"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different  "${CMAKE_SOURCE_DIR}/SKSE/Plugins/<name>.ini"  "${PLUGIN_DEPLOY_DIR}/SKSE/Plugins/<name>.ini"
        COMMAND ${CMAKE_COMMAND} -E copy_directory     "${CMAKE_SOURCE_DIR}/Shaders"  "${PLUGIN_DEPLOY_DIR}/Shaders")
endif()
```

**两个坑，都费一整轮调试：**

1. **备份无效**：构建一结束线上 DLL 就已经是新版本了，所以"先 `cp` 线上 DLL 到 `.pre_vNNN` 再部署"
   备份到的是**新文件**。实测 `.pre_v056` 的 md5 与刚构建的 v0.57 完全一致 ⇒ 这个"回滚点"是假的。
   真正的回滚是源码级：`git checkout <commit> -- src` + 重建（POST_BUILD 会自动部署回去）。
   自检：`ls -la` 线上 DLL 时若 mtime/size 已经是本次构建的，就说明构建先于你的备份动了它。

2. **改 INI 后重建 = 改动被冲掉**：同一个 POST_BUILD 用 `copy_if_different` 把**仓库里的 INI**
   推回模组目录。所以进游戏做 INI 开关 A/B 之前**不要重建**；要么改仓库那份（它才是被部署的），
   要么只改线上那份、改完直接重启游戏。
   注意：**POST_BUILD 只在目标重新链接时才执行** —— 只改 INI 不触发重链接 ⇒ 不会自动部署，
   这时要手动按 `copy_if_different` 语义同步一次。

"""

MEM_ANCHOR = '**另**：Bash 工具里 `cmd /c *.bat` 会被安全策略拒（Invoking cmd.exe from Bash），改走 PowerShell。'

MEM_ADD = """
**★ 连带坑：工程 CMake 尾部常有 `POST_BUILD` 自动部署**（`copy_if_different` 拷 DLL + **INI** +
`copy_directory` 拷 Shaders 到 `PLUGIN_DEPLOY_DIR`）。两个后果：
① **"先备份线上 DLL 再部署"备份到的是新文件**（构建一结束线上就已被覆盖）⇒ 该"回滚点"是假的，
实测 HASH 与刚构建的产物一致；真回滚是 `git checkout <commit> -- src` + 重建。
② **改线上 INI 后重建 → 被仓库 INI 覆盖回去**（同一个 `copy_if_different`）。做 INI 开关 A/B 前
**不要重建**；要持久就改仓库那份。另注：POST_BUILD 只在**重新链接**时跑，只改 INI 不会触发部署。
"""

LOG_ANCHOR = "**到这里，静态可判定项已穷尽**：剩下的全是只有进游戏才能读到的量。"

LOG_ADD = LOG_ANCHOR + """

### 收尾时查出的第 5 个问题：部署是"构建自动做的"，我第一版文档写错了回滚

核对线上 DLL 时发现 `.pre_v056` 备份的 md5 **等于**刚构建的 v0.57（`73fa4a5c`），不是 v0.56。
追下去读到 `CMakeLists.txt:105-121`：**POST_BUILD 用 `copy_if_different` 自动部署 DLL + INI，
再用 `copy_directory` 部署整个 Shaders**到 `PLUGIN_DEPLOY_DIR`。

⇒ 构建一结束线上就已经是新版本，所以我"先备份再部署"备份到的是**新文件**，那个回滚点是假的。
同时暴露更危险的一点：**同一个 POST_BUILD 会把仓库 INI 推回线上** —— 用户若把
`MvecScaleOverride=1.00` 写进线上 INI 再习惯性重建，改动会被冲掉，A/B 直接白做。

**处置**：
* 仓库 INI 里**正式加上带注释的 `MvecScaleOverride=0.00`**（构建会部署它 ⇒ 用户能看见这个键；
  值 0.00 = 行为不变，零风险），并已按 `copy_if_different` 语义同步到线上（md5 `163e748e` 一致）。
  （只改 INI 不会触发重新链接，POST_BUILD 不跑，所以手动同步。）
* `VERIFY_v057.md` 补**"改完 INI 不要重建"**的禁令 + 把回滚段改成**源码级**：
  `git checkout 135c4e4 -- src` + 重建。
* 删掉那个无效的 `.pre_v056` DLL 备份（标错的"回滚点"比没有更危险）。
* 已固化进技能 ㉔ 与用户记忆。

**最终状态**：HEAD `9d4ed78`；线上 DLL md5 `73fa4a5c`（与构建产物一致，1223168 字节）；
线上 INI 已含 `MvecScaleOverride=0.00`。"""

targets = []

raw = open(SKILL, "rb").read()
s_nl = "\r\n" if b"\r\n" in raw else "\n"
sk = raw.decode("utf-8").replace("\r\n", "\n")
if "㉔ 工程自带 POST_BUILD 自动部署" in sk:
    print("SKILL.md: ㉔ present -> skip")
else:
    if sk.count(SKILL_ANCHOR) != 1:
        sys.exit("REFUSED: SKILL anchor count = %d" % sk.count(SKILL_ANCHOR))
    sk = sk.replace(SKILL_ANCHOR, SKILL_ANCHOR + "\n\n" + SKILL_ADD.rstrip("\n"), 1)
    assert sk.count("㉔ 工程自带 POST_BUILD 自动部署") == 1
    targets.append((SKILL, sk, s_nl, "SKILL.md"))

raw = open(MEM, "rb").read()
m_nl = "\r\n" if b"\r\n" in raw else "\n"
mem = raw.decode("utf-8").replace("\r\n", "\n")
if "POST_BUILD" in mem:
    print("MEMORY.md: POST_BUILD note present -> skip")
else:
    if mem.count(MEM_ANCHOR) != 1:
        sys.exit("REFUSED: MEMORY anchor count = %d" % mem.count(MEM_ANCHOR))
    mem = mem.replace(MEM_ANCHOR, MEM_ANCHOR + "\n" + MEM_ADD, 1)
    targets.append((MEM, mem, m_nl, "MEMORY.md"))

raw = open(LOG, "rb").read()
l_nl = "\r\n" if b"\r\n" in raw else "\n"
lg = raw.decode("utf-8").replace("\r\n", "\n")
if "POST_BUILD 用 `copy_if_different` 自动部署" in lg:
    print("daily log: section present -> skip")
else:
    if lg.count(LOG_ANCHOR) != 1:
        sys.exit("REFUSED: LOG anchor count = %d" % lg.count(LOG_ANCHOR))
    lg = lg.replace(LOG_ANCHOR, LOG_ADD, 1)
    targets.append((LOG, lg, l_nl, "daily log"))

if not targets:
    sys.exit("nothing to do")

print("planned writes:")
for _, _, _, n in targets:
    print("  *", n)

if not APPLY:
    print("\nDRY RUN - nothing written. Re-run with --apply")
    sys.exit(0)

for path, text, nl, name in targets:
    data = text.replace("\n", nl).encode("utf-8")
    open(path, "wb").write(data)
    crlf, lf = data.count(b"\r\n"), data.count(b"\n")
    stray = data.count(b"\r") - crlf
    ok = (crlf == lf and stray == 0) if nl == "\r\n" else (crlf == 0 and stray == 0)
    print("  %-12s %7d bytes  CRLF=%-5d LF=%-5d stray=%-3d %s"
          % (name, len(data), crlf, lf, stray, "OK" if ok else "*** BROKEN ***"))
    assert ok, name

print("\ndone.")
