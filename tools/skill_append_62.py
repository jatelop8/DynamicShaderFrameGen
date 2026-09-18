#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append sections 62..69 to the framegen-diagnosis skill.

Insert-style change at END OF FILE: the "anchor" is the tail of the file, and it
survives the write -- so the marker check is the only thing preventing a double
append.  Marker is checked FIRST, as the user-level rule requires.
"""

import os
import shutil
import sys
import time

TARGET = r"C:/Users/Administrator/.workbuddy/skills/framegen-diagnosis/SKILL.md"
MARKER = "## 62 画面冻结 + 有声音 + 多插件日志同秒停摆 + 无 TDR/WER = Present 死锁"

BODY = r"""

## 62 画面冻结 + 有声音 + 多插件日志同秒停摆 + 无 TDR/WER = Present 死锁 ★2026-09-17 23:40 实锤

**症状**：进世界成功，玩着玩着**画面冻住、声音还在正常播**。
这是"渲染线程停了但进程还活着"的典型形态 —— 音频线程与渲染线程是分开的。

**判别法（不需要调试器，只要文件时间戳）**：
SKSE 日志目录里挑 **3 个以上互不相干的插件日志**（不是本插件的），
看它们的 `mtime`。若它们**在同一秒内一起停摆**，那就不是"某个插件出问题"，
而是**整个帧循环停了** —— 因为那些日志器分属不同插件、不同线程、不同文件。

```python
import os, time
d = r"C:/Users/Administrator/Documents/My Games/Skyrim Special Edition/SKSE"
rows = sorted((os.path.getmtime(os.path.join(d, n)), n)
              for n in os.listdir(d) if n.lower().endswith((".log", ".txt")))
for m, n in rows[-12:]:
    print(time.strftime("%H:%M:%S", time.localtime(m)), n)
```

**本机实测（2026-09-17 23:40:22）**：

| 时刻 | 文件 | 最后一行 |
|---|---|---|
| 23:40:22.221 | `DirectionalMovement.log` | `WM_ACTIVATEAPP: Game lost focus. Clearing inputs.` ← 全语料最后一行 |
| 23:40:22.166 | `ShadowLimitFix.log` | 逐帧日志停止（早 55 ms） |
| 23:40:22.09x | `DynamicShaderFrameGen.log` | 心跳停止 |
| 23:40:21 | `DynamicShaderFrameGen.watchdog.log` | 最后一个 tick |
| 23:40:21.918 | `DynamicSnow.log` | 停止 |

**必须先排除的三件事**（排除掉才敢下"卡住"的结论）：

| 可能 | 查法 | 本机结果 |
|---|---|---|
| 崩溃 | `CrashLogger.log` | 只有启动 5 行 |
| 挂起进程 | WER `ReportArchive` / `ReportQueue` | 本时段无 |
| GPU 复位 | 事件日志 `Display` 提供商 id=4101/4102 | **无 TDR** |

**为什么是 `Present` 而不是别处**：`FLIP_DISCARD` 交换链在被遮挡/后台的窗口上
DXGI 会**停止释放缓冲** ⇒ `Present` 永不返回。见 63。

**⚠️ 一条数据缺口（别忽略）**：看门狗是**独立线程**，若渲染线程真的永久卡住，
它应当在 1.5 s 后打出 `RENDER THREAD STALLED`。本次**没有** —— 因为看门狗自己也停了。
两种解释都符合数据：(a) 挂死后 1.5 s 内进程就结束了；(b) 整个进程停了（含被手动结束）。
**要区分它，就在看门狗行里加一个 `focus=` 字段**（64 节）：
下一跑若"看门狗还在 tick 且 `focus=0` 且打了 STALLED"，就是 (a) 的铁证。

---

## 63 `FLIP_DISCARD` + `BufferCount=3`：窗口一失焦，`Present` 就**永久**阻塞 ★2026-09-17 23:40 实锤

```cpp
// 本工程实测的交换链参数
desc1.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
desc1.BufferCount = 3;
...
swapChain->Present(0, Flags);          // ← 没有 DXGI_PRESENT_DO_NOT_WAIT
```

* 翻页模型下 `Present` 是**阻塞**的：要等一个已排队缓冲被释放才能交出下一帧。
* DXGI 对**被遮挡 / 后台**的窗口**停止释放缓冲** ⇒ `Present` 永不返回 ⇒ 渲染线程卡死。
* **MFG 把"可能卡"变成"一失焦就死"**：4x 每真实帧交 **4 帧**给 **3 深**队列，
  本来就贴着"队列满"的边缘，失焦后**下一个 `Present` 立刻楔死**（不是晚一点，是永久）。

**本插件当时的致命缺口**：`GetForegroundWindow` / `IsIconic` / `WM_ACTIVATEAPP` /
`DXGI_PRESENT_DO_NOT_WAIT` 在 `src/` **全工程 0 处** —— 一处焦点处理都没有。
**排查动作**：拿到"卡住"报告先 grep 这四个符号：

```bash
grep -rn "GetForegroundWindow\|IsIconic\|WM_ACTIVATEAPP\|DXGI_PRESENT_DO_NOT_WAIT" src/
```

---

## 64 `DO_NOT_WAIT` 的正确用法：`DXGI_ERROR_WAS_STILL_DRAWING` 是"这帧没显示"，不是失败 ★2026-09-17

```cpp
const HRESULT hrPresent = swapChain->Present(0,
    Flags | (winFocused ? 0u : static_cast<UINT>(DXGI_PRESENT_DO_NOT_WAIT)));
// 关键：STILL_DRAWING 不能进 ThrowIfFailed，否则失焦会变成"崩溃"而不是"跳过"
if (hrPresent != DXGI_ERROR_WAS_STILL_DRAWING)
    DX::ThrowIfFailed(hrPresent);
```

配套的三件事（少一件就会引入新问题）：

1. **失焦时要通知运行时停机**：DLSS-G 只要还开着就继续往交换链里交帧。
   一次性发 `DLSSGOptions{ .mode = DLSSGMode::eOff }`，**只在焦点边沿发，不要每帧发**
   （否则倍率阶梯会被每帧探针步骤吃掉，并刷出假的拒绝日志）。
2. **停机顺手清自动禁用计数器**（`dlssgFailCount = 0`），否则长 alt-tab 会被
   "插帧失败 N 次就自动关"的逻辑误判成真失败。
3. **恢复时不要立刻重开**：`focus` 采到 1 之后再走正常的启用路径即可。

---

## 65 `GetForegroundWindow() == hwnd` 在**包装窗口**下永远为假 ⇒ 必须比根窗口 ★2026-09-17 踩到

第一版写的是直接比句柄。若交换链的窗口是某个包装窗口的**子窗口**，
`GetForegroundWindow()` 返回的是**根窗口**，那么 `fg == hwnd` **整场都是假**
⇒ `focusBlock` 恒真 ⇒ 插帧**彻底不跑**（而且日志上看起来"很合理"，不报错）。

```cpp
static bool FocusAllowsPresenting(HWND a_hwnd)
{
    if (!a_hwnd)
        return true;                     // 未知窗口：什么都不要改
    if (::IsIconic(a_hwnd))
        return false;
    const HWND fg = ::GetForegroundWindow();
    if (!fg)
        return true;                     // 锁屏 / 模式切换：瞬时状态，不是挂死
    const HWND ourRoot = ::GetAncestor(a_hwnd, GA_ROOT);
    const HWND fgRoot  = ::GetAncestor(fg, GA_ROOT);
    if (ourRoot && fgRoot)
        return ourRoot == fgRoot;        // ★ 比根，不比句柄
    return fg == a_hwnd;
}
```

**`fg == nullptr` 必须按"前台"处理**：锁屏、分辨率/显示模式切换的瞬间会拿到空，
若判成"失焦"就会静默把插帧关掉，而且没有任何日志会解释为什么。

**Win32 注意**：`IDXGISwapChain1::GetHwnd()` 是**出参 + HRESULT**，不是属性 getter；
`DXGI_SWAP_CHAIN_DESC1` **没有** `OutputWindow`（那是旧版 `DXGI_SWAP_CHAIN_DESC` 的成员）。
两个都是编译期才暴露，别凭记忆写。

---

## 66 看门狗行加了字段 ⇒ 读取器的正则必须同步（**解析器不匹配是静默的**）★2026-09-17

看门狗行从

```
[92319551] frames=1493 silent=22ms stage=cmdlist Reset
```

变成

```
[92319551] frames=1493 silent=22ms stage=cmdlist Reset focus=1
```

若读取器还写 `stage=(.*?)\s*(<==.*)?$`，`.*?` 会把 ` focus=1` **一起吃进 stage**，
或者更糟 —— 正则整体不匹配 ⇒ 读取器打印"文件存在但没有可解析的行"，
看起来像"这次没数据"，其实**每次都在丢数据**。

**正确做法**：新增组一律写成**可选**，旧 build 的行必须仍能解析：

```python
WD_RE = re.compile(r"^\[(\d+)\]\s+frames=(\d+)\s+silent=(-?\d+)ms\s+stage=(.*?)"
                   r"(?:\s+focus=(-?\d+))?\s*(<==.*)?$")
...
focus = int(m.group(5)) if m.group(5) is not None else -1   # -1 = 旧 build，认不出来
```

理由不只是兼容：读取器会**按帧号回退切分运行段**（跨运行追加的日志要分段，
见 54 节），丢历史会让分段算错。

---

## 67 子串判空把**非空指针**判成空 —— 「金丝雀要用真实损伤特征」的镜像陷阱 ★2026-09-17 23:40 实锤（读取器自伤）

读取器里这行：

```python
if "ui=0" in raw or "ui=0x0" in raw:
    note(SEV_BAD, "RE::UI 单例为空：菜单守卫不可能生效")
```

而探针实际打印的是

```
MENU PROBE ui=0x7ff745c3ceb0 istrings=0x7ff745c71150 | ptr mainMenu=...
```

**`"ui=0"` 是 `"ui=0x7ff745c3ceb0"` 的前缀** ⇒ 每一次正常运行都被判成
"RE::UI 单例为空 → 菜单检测整体失效，这是 CommonLib 地址/版本问题"，
还会进总结。更糟的是它**和它自己上一行输出的**「InterfaceStrings 布局正确（指针相等）」
**直接矛盾** —— 下一轮排查会去追一个不存在的 CommonLib 问题。

**修法：判值，不判子串。**

```python
mu = re.search(r"\bui=(0x[0-9a-fA-F]+|\d+)", raw)
if mu is not None and int(mu.group(1), 0) == 0:
    ...          # 真空
elif mu is not None:
    print(SEV_OK + "  RE::UI 单例有效（ui=%s）" % mu.group(1))
```

这是 60 节那条规则的**镜像面**：那边说"金丝雀不要写会撞上健康输出的子串"，
这边说"**判空/判坏也不要写会撞上健康输出的子串**"。
**凡是 `X == 0` 意图的检查，一律解析出数值再比，不要用字符串包含。**

---

## 68 补丁脚本自己用错编码 ⇒ 含中文的锚点永远 `anchor x0` ★2026-09-17 23:40 踩到

`tools/fix_reader_uicheck_v071e.py` 第一版：

```python
text = raw_bytes.decode("latin-1")      # ← 错
...
if old in text:                          # old 是 Python 源码里的 UTF-8 字符串
```

`latin-1` 把目标文件的中文**逐字节**映射成乱码字符（每个字节一个字符），
而 `old` 里的中文是正常 Unicode ⇒ 两者**永远不相等**，干跑报 `anchor x0`。

**规则要按文件分**：

| 文件 | 读法 |
|---|---|
| 本工程 `.py` / `.md`（UTF-8 无 BOM） | **UTF-8** |
| ENB 的 `.ini`（常含日韩文注释） | **latin-1**（字节保持不动的往返编码） |

「用 latin-1 不动字节」这条经验只在**文件本身不是 UTF-8** 时才成立，
照搬到 UTF-8 源码上就是"锚点永远匹配不到"。

---

**本节产物（2026-09-17 23:40 冻结 → v0.71）**：
`tools/add_xray_v071.py`（9 处 / 3 文件）、`add_xray_v071b.py`（比根窗口）、
`add_xray_v071c.py`（改用 `GetHwnd`）、`tools/patch_reader_v071.py`（读取器适配 `focus=` + 新增 4c 段）、
`tools/fix_reader_uicheck_v071e.py`（修 `ui=0` 假判据）；
交接文档 `FIX_FOCUS_PRESENT_V071.md`；
DLL `6f377cd8241b2ec170f847a004be6c82`（1292288 B，构建产物与 mod 目录 md5 一致）。
"""


def main():
    apply_it = "--apply" in sys.argv

    with open(TARGET, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")

    # MARKER FIRST -- an append does not consume its anchor, so uniqueness of
    # the tail proves nothing about whether this already ran.
    if MARKER in text:
        print("REFUSED -- already applied (marker present)")
        return 2

    anchor = text[-80:]
    n = text.count(anchor)
    print("target: %s" % TARGET)
    print("bytes before: %d" % len(raw))
    print("tail anchor occurrences: %d" % n)
    if n != 1:
        print("REFUSED -- tail anchor not unique (%d)" % n)
        return 2

    out = text + BODY
    if out.count(MARKER) != 1:
        print("REFUSED -- marker not exactly once after append")
        return 2
    for s in ("## 62 ", "## 63 ", "## 64 ", "## 65 ", "## 66 ", "## 67 ", "## 68 "):
        if out.count(s) != 1:
            print("POST FAIL: %r count=%d" % (s, out.count(s)))
            return 2

    delta = len(out.encode("utf-8")) - len(raw)
    print("post-conditions OK | +%d bytes" % delta)

    if not apply_it:
        print()
        print("DRY RUN -- nothing written. Re-run with --apply")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = TARGET + ".bak_" + stamp
    shutil.copy2(TARGET, backup)
    with open(TARGET, "wb") as f:
        f.write(out.encode("utf-8"))

    back = open(TARGET, "rb").read().decode("utf-8")
    if back.count(MARKER) != 1 or not back.endswith(BODY[-40:]):
        print("READBACK FAIL")
        return 3
    crlf = back.count("\r\n")
    print("readback OK | CRLF=%d loneLF=%d loneCR=%d | %d bytes"
          % (crlf, back.count("\n") - crlf, back.count("\r") - crlf,
             len(back.encode("utf-8"))))
    print("wrote %s (backup %s)" % (TARGET, os.path.basename(backup)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
