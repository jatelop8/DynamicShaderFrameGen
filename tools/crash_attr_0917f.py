# -*- coding: utf-8 -*-
"""
Record the 17:2x crash-attribution round:
  * insert section 25 into the framegen-diagnosis skill (CRLF file)
  * append a dated section to the workspace daily log (LF file)

Contract:
  * marker MUST be a substring of the payload (asserted - third time this class bit us)
  * anchor must match exactly once
  * line endings verified before and after
"""
import sys
import os

SKILL = r"C:\Users\Administrator\.workbuddy\skills\framegen-diagnosis\SKILL.md"
LOG = r"C:\Users\Administrator\WorkBuddy\2026-09-17-11-48-48\.workbuddy\memory\2026-09-17.md"

SKILL_ANCHOR = "## 第四步：隔离测试（上面都排完还没头绪时）\n"
SKILL_MARKER = "### \u3255 \u5d29\u6e83\u5f52\u56e0"

SKILL_ADD = r"""### ㉕ 崩溃归因：CrashLogger 报的 faulting 模块名**可能是假的** —— 用模块表 + 目标工具自己的日志还原 ★2026-09-17 实锤

**症状**：闪退。CrashLogger 报 `VERSION.dll+0028A20  mov byte ptr [rax], 0xE9`。
而系统 `VERSION.dll` 真实大小仅 ~45KB —— **偏移 0x28A20 = 165KB 根本不可能**。
只信这一行会得出完全错误的结论（"系统 DLL 在写代码" / "是被测插件在打补丁"）。

**为什么会假**：进程里有**代理 DLL**。本例游戏根目录放了 `VERSION.dll` 与 `DINPUT8.dll`
（各 540672 字节），那是 DLSSG-Transfusion 以 version.dll / dinput8.dll 代理形式注入自己。
于是同一进程里 `VERSION.dll`（游戏目录，映射 660992）与 `version.dll`（system32，45056）**并存**，
CrashLogger 按名字匹配，你看到的那一行指向的是**代理那一份**。

**四步还原真名（只用崩溃现场自带的证据，不猜）**：
1. 崩溃日志自己的 `MODULES:` 段查故障地址所属基址：`grep 0x7FFD9CC3` → `VERSION.dll 0x7FFD9CC30000`。
   注意该段**只有名字没有路径**，到此还不能定性。
2. **用目标工具自己的日志取名与大小** —— 最硬的一条。Transfusion 的崩溃观测文件 `.crash.log`
   里 `MODULE` 记录**带完整路径和 size**：
   `base=0x00007FFD9CC30000 size=0x00000000000A1000 path=D:\ENB-EJ\Skyrim Special Edition\VERSION.dll`
   ⇒ 660992 字节 ⇒ 确认是"被代理的那个工具本身"，不是系统 DLL。
3. **用工具的启动日志确认身份**：`Loaded as: version.dll` / `Module Path: ...\VERSION.dll`
   —— 一句就把"假 VERSION.dll"解释干净。
4. **把 `Exception Thread ID` 对上工具日志里的线程名**（本例 31068 = 日志里
   `Patch worker started for PID ...` 那条），再看调用栈里**有没有游戏主线程 / 被测插件的帧**。
   本例栈 = 目标工具 + `usvfs_x64` + `sl.interposer`，**没有 SkyrimSE.exe、没有被测插件**
   ⇒ 故障发生在目标工具自己的线程上。

**判定"是不是我改坏的"：先做文件级差异表，不要推理。**
列出「最后一次正常会话」与「崩溃会话」之间的文件差异（mtime + md5）。本例只剩三项：
① 被测插件 DLL（v0.55→v0.57）② 它的 INI ③ Streamline 运行时 DLL 的 **mtime 变成构建时刻但 md5 未变**
（③ 是 POST_BUILD `copy_directory` 的副作用，内容没变 ⇒ 排除）。
`VERSION.dll`/`DINPUT8.dll` 都是更早时刻（上一次正常会话已在用）、其余自有 DLL 也未变 ⇒ 非本次差异。

**再查"被测插件有没有可能执行那条故障指令"（源码级）**：
`grep -rn "VirtualProtect|0xE9|Detour|trampoline|InstallHook" src/`
本例证明它只改 **虚表槽**（`IDXGISwapChain` 槽 10 / D3D11 上下文 / NeuralRendering 的 `slot_`）
与 **游戏函数**，对 interposer 只有 `LoadLibraryW` + `GetProcAddress`（**纯读**）
⇒ **机制上不可能写出那个 E9**。于是可以明确说"不是它执行的"，
但仍要诚实标注：**"二进制变了 ⇒ 时序可能被带偏"这一层无法用静态手段排除，必须 A/B。**

**这类崩溃的根因画像**：`mov byte ptr [rax], 0xE9`（写 5 字节 JMP）落在**已经存在 jmp 的同一地址**上，
且写失败（目标页已恢复只读）⇒ **重复补丁 + 忘了重新 VirtualProtect**。
多钩子并存（工具 A 挂钩子、工具 B 同时改同一个 stub，或模块自身在 init 期间重写自己的导出 stub）
时的经典竞态，往往**间歇复现** —— 所以第一处置建议永远是「原样再启动一次」。

**处置顺序**：① 原样重启一次（竞态未必复现）② 复现则回滚被测插件到上一个已正常启动的提交并重建
③ 若与插件无关，根因在第三方注入工具侧，查其更新版 / 向作者反馈。

"""

LOG_MARKER = "### 17:26 闪退取证"

LOG_ADD = r"""
### 17:26 闪退取证 —— 崩溃是 DLSSG-Transfusion 的补丁线程，不是 v0.57（静态可达处已穷尽）

用户报"现在直接闪退了"。现场：`crash-2026-09-17-17-21-23.log`（CrashLoggerSSE v1.24）、
Transfusion 自己的 `.crash.log` 与 `.log`。插件日志只跑到 `[Streamline] Plugin dir:`
（1228 字节）⇒ 死在 `slInit()` 里、`Initialized OK` 之前。日志 build 戳 `Sep 17 2026 17:13:38` = v0.57。
**v0.56/v0.57 改的 extent / mvecScale 全在 slInit 之后才执行，这次一行都没跑。**

**故障指令**：`mov byte ptr [rax], 0xE9` at `VERSION.dll+0028A20`，写 `0x7FFCF139B750`
= `sl.interposer.dll+0xB750` —— 写 5 字节 JMP 装钩子，目标页不可写 ⇒ 访问违例。

**CrashLogger 的模块名是假的**（系统 VERSION.dll 仅 45KB，偏移 165KB 不可能）。真名三条互证：
① CrashLogger `MODULES:` 段 `VERSION.dll 0x7FFD9CC30000`（无路径）；
② Transfusion `.crash.log` 的 `MODULE` 记录（带路径+size）`base=0x00007FFD9CC30000 size=0xA1000
path=D:\ENB-EJ\Skyrim Special Edition\VERSION.dll` ⇒ 660992 字节；
③ Transfusion 启动日志 `Loaded as: version.dll` / `Module Path: ...\VERSION.dll`。
⇒ 那个"VERSION.dll"就是 **DLSSG-Transfusion v1.4.0-pure-warp 自己**（代理注入；游戏根目录
另有同尺寸 `DINPUT8.dll`，以及 09-11 被停用的 5945344 字节 `dinput8.dll.disabled`）。

**线程**：`Exception Thread ID: 31068` = Transfusion 日志 `Patch worker started for PID 31128` 的 tid。
调用栈 = Transfusion(VERSION.dll) + usvfs_x64 + sl.interposer，**无 SkyrimSE.exe、无 DFG 帧**。

**重复补丁证据**：该地址**已经是** `jmp 0x00007FFCB1380178`（Transfusion 跳板），
而 RDX = `0x7FFCB1370178` —— 它要把同一 stub 改指到**另一个**跳板；
Transfusion 日志 `HookSlInit: calling original=00007FFCB1370180` 印证 `0x7FFCB137xxxx` 是它的跳板区。

**差异表（16:34 正常会话 vs 17:21 崩溃会话）** 只剩三项：`DynamicShaderFrameGen.dll`（v0.55→v0.57）、
`DynamicShaderFrameGen.ini`（+注释 + `MvecScaleOverride=0.00`）、`sl.*.dll` 全部 **mtime 变 17:13 但 md5 未变**
（POST_BUILD `copy_directory` 副作用，内容一致 ⇒ 排除）。VERSION.dll/DINPUT8.dll 均 14:09（16:34 已在用）、
DynamicShaderCore/DynamicShader.dll 08-27、DVGProbe 16:14 ⇒ 均非本次差异。

**DFG 已被机制排除**：`grep -rn "VirtualProtect|0xE9|Detour|trampoline" src/` 显示它只改**虚表槽**
（IDXGISwapChain 槽 10 / D3D11 设备上下文 / `NeuralRendering/Runtime.cpp` 的 `slot_`）与**游戏函数**；
对 interposer 只有 `LoadLibraryW` + `GetProcAddress`（纯读，`Streamline.cpp:105-117`）⇒ 写不出那个 E9。

**未排除（静态到此为止）**：DFG 二进制变了 ⇒ `slInit` 耗时可能被带偏（16:34 耗时 1.38s，
本次约 0.2s 即崩），竞态结果可能因此翻转 ⇒ **必须 A/B**。

**处置**：① 原样重启一次（竞态未必复现）② 复现则回滚 DFG 到 `135c4e4` 重建 ③ 根因在
Transfusion（v1.4.0-pure-warp，Sep 14 构建）侧，查更新版。
"""


def check_lf(path):
    raw = open(path, "rb").read()
    crlf = raw.count(b"\r\n")
    stray = raw.count(b"\r") - crlf
    return raw, crlf, stray


def main():
    apply = "--apply" in sys.argv

    # self-check: every marker must literally exist in its payload
    assert SKILL_MARKER in SKILL_ADD, "SKILL_MARKER not in payload"
    assert LOG_MARKER in LOG_ADD, "LOG_MARKER not in payload"

    ok = True
    for path, anchor, add, marker, crlf_target in (
        (SKILL, SKILL_ANCHOR, SKILL_ADD, SKILL_MARKER, True),
        (LOG, None, LOG_ADD, LOG_MARKER, False),
    ):
        raw, crlf, stray = check_lf(path)
        print("=== %s ===" % os.path.basename(path))
        print("  line endings: CRLF=%d LF=%d stray=%d" % (crlf, raw.count(b"\n"), stray))
        if crlf_target and (stray or crlf == 0):
            print("  REFUSED - expected CRLF file"); ok = False; continue
        if not crlf_target and (stray or crlf != 0):
            print("  REFUSED - expected LF file"); ok = False; continue
        txt = raw.decode("utf-8")
        if marker in txt:
            print("  REFUSED - marker already present"); ok = False; continue
        a = anchor
        if a is not None:
            if crlf_target:
                a = a.replace("\n", "\r\n")
            n = txt.count(a)
            print("  anchor x%d %s" % (n, "OK" if n == 1 else "*** NOT UNIQUE ***"))
            if n != 1:
                ok = False; continue
        payload = add.replace("\n", "\r\n") if crlf_target else add
        print("  payload +%d bytes  marker=%s" % (len(payload.encode("utf-8")), marker[:24]))
        if not apply:
            continue
        out = (txt.replace(a, payload + a, 1) if a is not None else txt + payload)
        open(path, "wb").write(out.encode("utf-8"))
        raw2, crlf2, stray2 = check_lf(path)
        print("  written: %d bytes  CRLF=%d LF=%d stray=%d"
              % (len(raw2), crlf2, raw2.count(b"\n"), stray2))
        if marker not in raw2.decode("utf-8"):
            print("  *** post-condition FAILED"); ok = False

    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply")
        return 0
    print("post-conditions OK" if ok else "*** SOME REFUSED ***")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
