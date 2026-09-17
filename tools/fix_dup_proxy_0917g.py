# -*- coding: utf-8 -*-
"""
DLSSG-Transfusion 双代理实例（double-proxy double-load）修复记录。

2026-09-17 实锤：游戏根目录同时存在 version.dll 与 dinput8.dll（逐字节相同，
md5 c048b46e4005aa11a152bad5c6483182，540672 字节），导致 Transfusion 在同一进程里
被加载两次（两个基址），两个 patch worker 互撞 ->
  17:21 崩溃：mov byte ptr [rax], 0xE9 写 sl.interposer.dll+0xB750（slGetFeatureFunction，
               .text 节 X|R 不可写）
  18:05 卡死：slSetD3DDevice 进入后永不返回，看门狗刷 pending=1 到 101859ms

本脚本只写文档/记忆/技能，不改任何源码。
契约：
  * 每个锚点必须恰好匹配 1 次
  * 每个 marker 必须**是载荷的子串**（insertion 型改动不消耗锚点，必须显式守卫）
  * 逐文件保持行尾（SKILL.md 是 CRLF，其余是 LF）
  * 默认干跑，--apply 才落盘
"""
import os
import sys

APPLY = "--apply" in sys.argv

HOME = r"C:\Users\Administrator"
DEPLOY_NOTE = r"D:\Modding\DLSSG-Transfusion\DEPLOY_NOTE.md"
USER_MEM = os.path.join(HOME, ".workbuddy", "MEMORY.md")
SKILL = os.path.join(HOME, ".workbuddy", "skills", "framegen-diagnosis", "SKILL.md")
DAILY = r"C:\Users\Administrator\WorkBuddy\2026-09-17-11-48-48\.workbuddy\memory\2026-09-17.md"

# ----------------------------------------------------------------------------
# 1) DEPLOY_NOTE.md
#    替换型：纠正我自己写错的部署步骤（块内含错误说法，替换即消耗）
#    追加型：文件末尾追加事故记录
# ----------------------------------------------------------------------------
DN_OLD = """```bash
GAME="/d/ENB-EJ/Skyrim Special Edition"        # MO2 实例 "Skyrim Special Edition (3)" 的 gamePath
cp "$GAME/version.dll" "$GAME/dinput8.dll"      # 就地改名（version.dll 不被导入 = 无害死文件，可留可删）
```

- `DLSSG-Transfusion.json` 必须与 DLL 同目录（游戏根目录）✅
- 代理 DLL **必须落在 gamePath 根**：MO2 的 usvfs 只虚拟化 `Data\\`，不虚拟化根目录
- 保留 `version.dll` 不影响运行，同时是个免风险回滚点"""

DN_NEW = """```bash
GAME="/d/ENB-EJ/Skyrim Special Edition"        # MO2 实例 "Skyrim Special Edition (3)" 的 gamePath
cp "$BK/DLSSG-Transfusion.dll" "$GAME/dinput8.dll"   # 部署唯一一份，代理名 = dinput8.dll
```

- `DLSSG-Transfusion.json` 必须与 DLL 同目录（游戏根目录）✅
- 代理 DLL **必须落在 gamePath 根**：MO2 的 usvfs 只虚拟化 `Data\\`，不虚拟化根目录
- **⚠️ 只放一份。绝不要同时留 `version.dll` 当"回滚点"** —— 2026-09-17 踩过，
  见文末《双代理双实例事故》。回滚点放备份目录，不要放游戏目录。"""

DN_ADD = """
---

## ⚠️ 双代理双实例事故（2026-09-17，已修复）

**一句话**：我按"version.dll 不被导入 = 无害死文件"的假设，把同一个包 `cp` 成了
`version.dll` + `dinput8.dll` 两份放在游戏根目录。**那个假设是错的** —— 有别的代码
`LoadLibrary("version.dll")`，于是 Transfusion **每个会话被加载两次**，两个 patch worker 互撞。

### 证据（两套独立日志系统给出同一结论）

| 来源 | 内容 |
|---|---|
| CrashLogger 模块表（17:21） | `DINPUT8.dll 0x7FFD5A7D0000` + `VERSION.dll 0x7FFD9CC30000`（游戏目录副本，大写）**与** `dinput8.dll 0x7FFDFD370000` + `version.dll 0x7FFE17690000`（System32，小写）——**四条** |
| Transfusion 自己的 `.crash.log` MODULE 表（18:05） | `DINPUT8.dll 0x7FFD34E40000` + `VERSION.dll 0x7FFD9CC30000`，同为 `size=0xA1000` |
| 文件指纹 | 两份 md5 完全相同 `c048b46e4005aa11a152bad5c6483182`，540672 字节，同一时刻 14:09 部署 |

**最硬的一条判据**：Transfusion 报 `NGX device support: already patched at RVA 0x61484`，
而磁盘上那个 `nvngx_dlssg.dll` 的 md5 与原始包**逐字节一致**（已核对）。
补丁不可能来自上次会话 ⇒ **只能来自同一进程里的另一个实例**。

辅助指纹：
- 每次 `LoadLibrary` 在日志里出现**两次**，两条 path 写法不同（一个虚拟路径、一个真实路径）
- 日志横幅身份每次会话都不同：17:21 是 `Loaded as: version.dll`，18:05 是 `Loaded as: dinput8.dll`
  —— 两个实例抢写同一个日志文件

### 后果（同一份配置，非确定性的两种死法）

```
17:21  EXCEPTION_ACCESS_VIOLATION
       VERSION.dll+0028A20   mov byte ptr [rax], 0xE9
       Tried to write at 0x7FFCF139B750 = sl.interposer.dll+0xB750
       -> 该 RVA 正是导出 slGetFeatureFunction 的函数体，落在 .text（X|R，不可写）
       -> 整条调用栈都在 VERSION.dll 那一个实例里

18:05  [DBG] slSetD3DDevice ENTER: device=00000000234C30A0 original=00007FFCA05F01E0
       （主线程 12904 从此再无输出）
       [STARTUP] worker alive; slSetD3DDevice pending=1 thread=12904 elapsed=101859ms
       -> 主线程卡在 slSetD3DDevice 里 102 秒，Transfusion 自己的 worker 在等它
```

16:34 那次能跑（4x MFG 真的在生成）也是双实例状态下跑起来的 —— 说明这是**竞态**，
不是必然失败。竞态最忌讳的就是"两个执行者"。

### 修法

```bash
GAME="/d/ENB-EJ/Skyrim Special Edition"
mv "$GAME/version.dll" "$GAME/version.dll.off"    # 只留 dinput8.dll 一份
```

回滚：

```bash
cp /d/workbuddy2/backup/transfusion_proxy_dup_20260917_182050/version.dll \\
   "/d/ENB-EJ/Skyrim Special Edition/version.dll"
```

### 代理名怎么选

**选游戏 exe 静态导入表里真实存在的那个。** `SkyrimSE.exe` 导入 `DINPUT8`，**不导入 `version.dll`**
（见本文开头的 31 项导入表）—— 但游戏目录里的 `version.dll` 仍会被别的东西加载起来。
所以"不在导入表里"**不能**推出"不会被加载"。判据只能是 `pe_import_dump.py` 核对导入表
**加上**数副本数，**不要用字符串扫描代替**。

### 顺带记录的次级风险（未修，非本次死因）

本机 Streamline 运行时是 **2.13**（interposer 内嵌宽字符 `"2.13"`，全盘 6 份副本内容相同），
而 DFG 是拿 **SDK 2.12 头文件**编译的（`sl_version.h` 里 `SL_VERSION_MINOR 12`）。
Transfusion v1.4.1 的 README 头号特性写的是 *"Full Streamline 2.14+ Compatibility with
direct slGetPluginFunction and interposer hooks"*，而实测这个 2.13 interposer：

```
slGetPluginFunction   -> 未导出
slSetData             -> 未导出
slDLSSGSetOptions     -> 未导出
```

Transfusion 日志却报 `Direct Detours ... installed successfully (slGetFeatureFunction, slInit,
slSetD3DDevice, slSetVulkanInfo, slSetData, slSetConstants, slSetTag, slSetTagForFrame)`
—— 它声称 hook 了 `slSetData`，而这个 DLL 不导出它。三个版本号（头 2.12 / 运行时 2.13 /
Transfusion 要求的 2.14+）互不相同，是结构性隐患，本期不动（一次只改一个变量）。
"""
DN_ADD_MARKER = "双代理双实例事故（2026-09-17，已修复）"
DN_STALE = ["无害死文件，可留可删", "保留 `version.dll` 不影响运行"]

# ----------------------------------------------------------------------------
# 2) 用户级 MEMORY.md —— 跨项目铁律（行尾锚点追加）
# ----------------------------------------------------------------------------
UM_ADD = """

## 注入器代理 DLL：同一个包绝不要放两份代理名（跨项目，2026-09-17 实锤）

**代理 DLL（`version.dll` / `dinput8.dll` / `winmm.dll` / `dxgi.dll` 这类）只要放在游戏目录，
进程里任何代码 `LoadLibrary` 了这个名字，它就会被加载 —— 不是你"以为只有在 exe
静态导入表里的那个才会被加载"。**

实测（Skyrim SE + DLSSG-Transfusion v1.4.1）：

- 同一个包 `cp` 出 `version.dll` + `dinput8.dll`，md5 完全相同（540672 字节）
  ⇒ **每个会话进程里加载两次**（两个不同基址），两个补丁 worker 互撞
- 症状（同一份配置，非确定性）：一次崩（`mov byte ptr [rax], 0xE9` 写只读代码页）、
  一次卡死（`slSetD3DDevice` 进了不返回，看门狗刷 `pending=1 elapsed=…` 到 102 秒）
- **最硬的判据**：注入器报 `already patched at RVA 0x…`，而磁盘文件 md5 与原始包
  **逐字节一致** ⇒ 补丁只可能来自**同一进程的另一个实例**
- 辅助：每次 `LoadLibrary` 在日志里出现两次、两条 path 写法不同；
  日志横幅身份每次会话不同（两个实例抢写同一个日志文件）

**取证方法**：崩溃观测文件的 MODULE 表里，同一个文件会以**两个基址**各出现一次。
注意大小写 —— `VERSION.dll`/`DINPUT8.dll`（游戏目录副本）与 `version.dll`/`dinput8.dll`
（System32 正版）是**四条**记录，别以为"名字一样就是同一个模块"。

**铁律**：不要用"留着当回滚点"当理由把第二份代理名留在游戏目录。**回滚点放备份目录。**
禁用就改名成 `.off`（不必删）。
"""
UM_ANCHOR = "**别把探测期的噪声当成结论。**"
UM_MARKER = "注入器代理 DLL：同一个包绝不要放两份代理名"

# ----------------------------------------------------------------------------
# 3) 技能 framegen-diagnosis —— 新增 ㉖（CRLF 文件）
# ----------------------------------------------------------------------------
SK_ADD = """
---

## ㉖ 同一个注入器以两个代理名部署 → 同进程双实例互撞（2026-09-17 实锤）

**症状族**：**同一份配置**，一次崩（写只读代码页 EXCEPTION_ACCESS_VIOLATION）、
一次卡死（某次 Streamline 调用进了永不返回）。**非确定性本身就是"有两个执行者"的指纹** ——
单线程 bug 不会这样。

**取证三步（缺一不可）**：

1. **数副本**：游戏根目录里同尺寸同 md5 的二进制有几份。代理 DLL 都是从同一个包 `cp` 出来的，
   尺寸完全一致，一抓一个准。
2. **看崩溃观测文件的 MODULE 表**：同一个文件会以**两个基址**各出现一次。
   ⚠️ 注意大小写 —— `VERSION.dll`/`DINPUT8.dll`（游戏目录副本）与
   `version.dll`/`dinput8.dll`（System32 正版）是**四条**记录。
   不要以为"名字一样就是同一个模块"。
3. **找"已经打过补丁"类日志**：注入器报 `already patched at RVA 0x…`，而
   **磁盘上那个文件的 md5 与原始包逐字节一致** ⇒ 补丁只可能来自**同一进程里的另一个实例**。
   这是最硬的一条，因为它排除了"上次会话留下的持久补丁"。

**辅助指纹**：
- 每次 `LoadLibrary` 在日志里出现**两次**，两条 path 写法不同（一个虚拟路径、一个真实路径）
  —— 两个 hook 各记一次。别把它当成 usvfs 的正常重复。
- 日志横幅身份每次会话都不一样（这次 `Loaded as: version.dll`，下次 `Loaded as: dinput8.dll`）
  —— 两个实例抢写同一个日志文件。

**判据：代理名必须选游戏 exe 静态导入表里真实存在的那个。**
并且 —— **"不在导入表里"不能推出"不会被加载"**。实测 `SkyrimSE.exe` 不导入 `version.dll`，
但放在游戏目录里的 `version.dll` 照样被别的东西 `LoadLibrary` 起来，于是双实例。
⇒ 判据只能是「核对导入表 **加上** 数副本数」，**不要用字符串扫描代替**。

**修法**：只留一个，另一个改名成 `.off`（改名即可，不必删；回滚点放备份目录，不要放游戏目录）。

**排查顺位**：出现"同一配置两种死法"时，**先数代理副本数**，再谈别的。
这一步只要 30 秒，却能把整类竞态一次性排除掉。
"""
SK_ANCHOR = "但**不要因此停下来只问问题**：先把日志和 A/B 跑完，把能排除的都排除掉，再带着具体选项问。"
SK_MARKER = "㉖ 同一个注入器以两个代理名部署"

# ----------------------------------------------------------------------------
# 4) 工作区日志 —— 追加到文件末尾
# ----------------------------------------------------------------------------
DAILY_ADD = """
### 18:20 找到崩/卡的真因：我自己把 Transfusion 装了两份

**根因**：游戏根目录同时有 `version.dll` + `dinput8.dll`，md5 完全相同（`c048b46e…`，540672 字节）。
Transfusion 每个会话**被加载两次**，两个 patch worker 互撞。

**证据（两套独立日志系统）**：
- CrashLogger 模块表（17:21）：`DINPUT8.dll 0x7FFD5A7D0000` + `VERSION.dll 0x7FFD9CC30000`
  加上 `dinput8.dll 0x7FFDFD370000` 加 `version.dll 0x7FFE17690000`（System32）—— 四条
- Transfusion 自己 `.crash.log` MODULE 表（18:05）：两个 `size=0xA1000` 的游戏目录副本
- **最硬**：`NGX device support: already patched at RVA 0x61484`，而磁盘上该 `nvngx_dlssg.dll`
  的 md5 与原始包逐字节一致 ⇒ 补丁只能来自同进程的另一个实例
- 辅助：每次 LoadLibrary 记两遍（两条 path 写法不同）；日志横幅 17:21 是 `version.dll`、
  18:05 是 `dinput8.dll`

**两种死法（同一配置，竞态）**：
- 17:21 `mov byte ptr [rax], 0xE9` 写 `sl.interposer.dll+0xB750`
  —— 该 RVA 正是导出 `slGetFeatureFunction` 的函数体，落在 `.text`（X|R 不可写）
- 18:05 `slSetD3DDevice ENTER` 后主线程再无输出；看门狗刷 `pending=1 elapsed=101859ms`
  （卡死 102 秒），Transfusion 自己的 worker 在等这条调用

**已修复**：`version.dll` 改成 `version.dll.off`（只留 `dinput8.dll`）。
备份 `/d/workbuddy2/backup/transfusion_proxy_dup_20260917_182050/`。
**源码一行未动；v0.56/v0.57 保留原位。**

**排除掉的**：Streamline/NGX 的 DLL 线上与仓库逐字节一致、NGX 模型 `.bin` 未被改
⇒ 不是磁盘污染。`already patched` 是内存内的另一实例，不是上次会话的残留。

**次级风险（未修）**：本机 Streamline 运行时 2.13，DFG 用 SDK 2.12 头编译，
Transfusion v1.4.1 要求 2.14+（`slGetPluginFunction` / `slSetData` 在该 2.13 里**未导出**，
但 Transfusion 日志声称 hook 成功）。三版本号互不相同，一次只改一个变量，本期不动。

**下一步（用户执行）**：原样启动一次，读 `DLSSG-Transfusion.log` 横幅身份（应只剩 dinput8）
与 `DynamicShaderFrameGen.log` 是否出现 `D3D11/D3D12 device set`。
若仍卡 ⇒ 下一个单变量是 `patchFlipMetering` 改成 `false`（v1.4.1 的官方默认）。
"""
DAILY_MARKER = "18:20 找到崩/卡的真因：我自己把 Transfusion 装了两份"

# ----------------------------------------------------------------------------
# 自检：marker 必须**是**载荷的子串，否则守卫恒空、重跑会再插一遍
# ----------------------------------------------------------------------------
for _name, _mk, _payload in [
    ("DN_ADD", DN_ADD_MARKER, DN_ADD),
    ("UM_ADD", UM_MARKER, UM_ADD),
    ("SK_ADD", SK_MARKER, SK_ADD),
    ("DAILY_ADD", DAILY_MARKER, DAILY_ADD),
]:
    assert _mk in _payload, "SELF-CHECK FAILED: %s marker not in payload" % _name


def load(path):
    d = open(path, "rb").read()
    crlf = d.count(b"\r\n") > 0
    return d.decode("utf-8").replace("\r\n", "\n"), crlf


def save(path, txt, crlf):
    out = txt.replace("\n", "\r\n") if crlf else txt
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    d = open(path, "rb").read()
    return d.count(b"\r\n"), d.count(b"\n"), d.count(b"\r") - d.count(b"\r\n")


def do_edit(label, path, anchor, payload, marker):
    print("--- %s ---" % label)
    print("  %s" % path)
    txt, crlf = load(path)
    if marker in txt:
        print("  REFUSED: marker already present (idempotency guard)")
        return "REFUSED"
    if anchor is None:
        print("  anchor: <EOF append>")
        new = txt + payload
    else:
        n = txt.count(anchor)
        print("  anchor x%d %s" % (n, "OK" if n == 1 else "*** NOT UNIQUE ***"))
        if n != 1:
            return False
        new = txt.replace(anchor, anchor + payload, 1)
    print("  marker <- %s" % marker[:34])
    print("  payload +%d bytes (%s)" % (len(payload.encode("utf-8")), "CRLF" if crlf else "LF"))
    if not APPLY:
        return True
    a, b, c = save(path, new, crlf)
    print("  written: CRLF=%d LF=%d stray=%d" % (a, b, c))
    txt2, _ = load(path)
    cnt = txt2.count(marker)
    print("  post-check marker x%d %s" % (cnt, "OK" if cnt == 1 else "*** FAIL ***"))
    return "OK" if cnt == 1 else "FAIL"


results = {}

# ---- DEPLOY_NOTE：先替换错误说法，再在文件末尾追加事故记录 ----
print("--- DEPLOY_NOTE.md ---")
print("  %s" % DEPLOY_NOTE)
dn_txt, dn_crlf = load(DEPLOY_NOTE)
if DN_ADD_MARKER in dn_txt:
    print("  REFUSED: already applied")
    results["deploy_note"] = "REFUSED"
else:
    n1 = dn_txt.count(DN_OLD)
    print("  wrong-claim block x%d %s" % (n1, "OK" if n1 == 1 else "*** NOT UNIQUE ***"))
    if n1 != 1:
        results["deploy_note"] = "FAIL"
    else:
        dn_new = dn_txt.replace(DN_OLD, DN_NEW, 1) + DN_ADD
        bad = [s for s in DN_STALE if s in dn_new]
        print("  旧说法残留: %s" % (bad if bad else "无 OK"))
        print("  marker x%d" % dn_new.count(DN_ADD_MARKER))
        assert not bad, "stale claim survived: %s" % bad
        assert dn_new.count(DN_ADD_MARKER) == 1
        if APPLY:
            a, b, c = save(DEPLOY_NOTE, dn_new, dn_crlf)
            print("  written: CRLF=%d LF=%d stray=%d" % (a, b, c))
            t2, _ = load(DEPLOY_NOTE)
            print("  post-check marker x%d | 旧说法残留 %d"
                  % (t2.count(DN_ADD_MARKER), t2.count("无害死文件")))
            results["deploy_note"] = "OK" if (t2.count(DN_ADD_MARKER) == 1 and t2.count("无害死文件，可留可删") == 0) else "FAIL"
        else:
            print("  payload +%d bytes (%s)" % (len(DN_ADD.encode("utf-8")), "CRLF" if dn_crlf else "LF"))
            results["deploy_note"] = "OK"

results["user_mem"] = do_edit("USER MEMORY.md", USER_MEM, UM_ANCHOR, UM_ADD, UM_MARKER)
results["skill"] = do_edit("SKILL framegen-diagnosis", SKILL, SK_ANCHOR, SK_ADD, SK_MARKER)
results["daily"] = do_edit("DAILY 2026-09-17.md", DAILY, None, DAILY_ADD, DAILY_MARKER)

print()
print("=" * 60)
for k, v in results.items():
    print("  %-14s %s" % (k, v))
bad = [k for k, v in results.items() if v not in ("OK", "REFUSED")]
if not APPLY:
    print("DRY RUN - nothing written. Re-run with --apply")
else:
    print("RESULT:", "OK (applied; REFUSED = already applied, which is correct)" if not bad
          else "FAILED: %s" % bad)
