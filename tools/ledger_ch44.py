# -*- coding: utf-8 -*-
"""Append chapter 44 to MFG_MASTER_NOTES.md.  Pure LF, append only."""
import pathlib

LEDGER = pathlib.Path(__file__).resolve().parent.parent / "MFG_MASTER_NOTES.md"

CH = """

# 第 44 章 13:26 局（v1.30 首跑）：4x 真的上台了，然后游戏丢失了焦点

## 44.1 这一局推翻了本章之前所有关于「进程被终止」的推论方向

本局 13:25:16 启动，13:25:48 进主菜单，13:26:37.5 按回车（读档/新游戏），
13:26:45.052 `MENU EDGE open=0`（进世界），13:26:46.6 全部日志停止 —— 世界段 1.5 秒。
再一次「刚进去两秒」。

但本局第一次同时拿到了三条此前从未同框的证据：

1. **4x 确实在跑，而且是在呈现的。**
   `[MFG] probe edge: menu guard released, SetDLSSGOptions resumes on this frame.
   step advertised=4x accepted=4x latched=1`
   `[Streamline] MFG probe: runtime ACCEPTED 4x (3 interpolated frames) | runtimeReportsMax=6x`
   `[Streamline] DLSSG presented per real frame = 4 (status=0)`
   `[CAM] PC` 世界段 `mult(acc/pres)=4/4`
   `[XRAY] serial=2427 ... presented all=0/12/0/0/54/0/0/0 world=0/12/0/0/54/0/0/0`
   ⇒ 世界段 66 帧里有 **54 帧是在 4x 槽上呈现的**。
   `[XRAY] 4x SNAPSHOT t=0 frames=2406 lastPr=2418 (live4x: +19 flips for +6 Present entries)`
   `[XRAY] 4x probe +446ms frames=2422 lastPr=2482 panel=139 flips/s live4x=1`
   ⇒ **v1.30 修掉的那个「按构造不可能触发」的累积比判据，首跑就触发了。**
   Transfusion 独立佐证：`DLSS-G actual presentation count: 4x (maximum generated frames=5)`、
   `[PERF] 4x | Kernel: Ada | FPS: 34.4`。

2. **`[SCREEN]` 活了，74 个采样。** 但它的判据是错的（见 44.3）。

3. **死亡前 0.95 秒有一次 LeftAlt，死亡那一刻游戏「丢失焦点」。**
   `[13:26:45.648] [INPUT] vk 0x00 -> 0xA4 (2 held, fg=1)`
   `[13:26:46.590] [DMK] WM_ACTIVATEAPP: Game lost focus. Clearing inputs.`（DirectionalMovement）

## 44.2 「不是崩溃」现在有三条互相独立的证据（此前两条）

| 来源 | 9/18 | 9/19 | 9/20 |
|---|---|---|---|
| WER `AppCrash_SkyrimSE.exe` | 3 份 | 0 | 0 |
| Crash Logger `SKSE/crash-*.log` | 最后 5 份全是 | 0 | 0 |
| **`%LOCALAPPDATA%\\CrashDumps\\SkyrimSE.exe.*.dmp`**（本章新增） | 3 份 18:23/19:04/19:16 | 0 | 0 |
| **System 日志 `nvlddmkm` 错误（TDR）**（本章新增） | — | — | **最近一次是 9/15** |
| Application 日志 1000/1002 | — | — | 13:10–13:35 **零条** |

⇒ 两天里所有「卡死」，游戏**一次都没崩、一次都没 TDR**。
新查询方式（`wevtutil`，PowerShell 在本机对这些查询静默返回空，已弃用）：
`wevtutil qe System /q:"*[System[Provider[@Name='nvlddmkm']]]" /c:10 /rd:true /f:text`

## 44.3 我的 `[SCREEN]` 判据是错的 —— 用 `distinct` 数「屏幕有没有变」在原理上不成立

本局 74 个采样，**每一个**都是 `distinct=8/8`：加载淡出时 8/8、菜单里 8/8、世界里 8/8。
原因：`distinct` 数的是**8 个环样本里有几个不同的哈希**，而一个横跨任何转变的环，
按构造就是 8 个不同哈希。它实际上在回答「最近八秒里发生过任何事吗」，
而不是「屏幕有没有变」。真正重要的两个采样是：

```
[44082295] [SCREEN] #73 hash=899CCF386BE74EC8 lum=100.93 distinct=8/8 ours=A4110C0648902D2C ourDistinct=5
[44083350] [SCREEN] #74 hash=C0A1CFCA8D01D28C lum=100.93 distinct=8/8 ours=EDCD53D17F0537A5 ourDistinct=6
```

**lum 一模一样（100.93），哈希不同。** 这既可能是「画面在动」，也可能是
「世界冻了、只有左上角 FPS 覆盖层在跳」—— 一个哈希分不出来。**这正是判据必须换成
连续样本同一性 + 亮度差幅度的原因。**（L60：一行日志把自己的值一起打出来时，
它带着同样的值重复就自我否证了。）

另一半：`[SCREEN] STALE` 要求 `sDistinct<=1`，而 `sDistinct` 永远到不了 1 ⇒
**这条判据在世界上一次都不可能触发。** 第四个「按构造不可能触发」的仪器。

## 44.4 `[INPUT]` 的「(2 held)」是我自己的扫描在重复计数同一次按键

`GetAsyncKeyState` 对**同一个物理 Alt** 会同时报告 `VK_MENU (0x12)` 和
`VK_LMENU (0xA4)`。Shift（0x10/0xA0/0xA1）、Ctrl（0x11/0xA2/0xA3）同理。
⇒ 打印 `2 held` 时，实际可能只有 **一个** 键。
而「第二个键在不在」恰恰决定这一局是 **ALT+F4 退出** 还是 **ALT 单独按下**。
这又是一个 L61：判据的推论范围超出了它测量的范围。

## 44.5 另一条被忽略的读数：`hrsD` 在走，`eyeD=0.00`，`paused=0`

`[13:26:45.648] [CAM] PC v1.19: read=592 match=555 adopt=2/3 ... paused=0 ld=0 fade=0
hrs=12.32800 hrsD=0.005469 ... PC_STILL INPUT_SEEN - input reached the game, so a still
eyeD here is a frozen world`

**`INPUT_SEEN` 是错的**：这一局唯一的键是 LeftAlt，它不能移动角色。
画面「冻住」和「玩家没动」在这里又混成了一句 —— 而 `fade=0` 说明淡入刚好在这一刻结束。

## 44.6 v1.31 改了什么（`patch_v131_the_picture_and_the_hand.py`，16 锚点 count==1）

**不碰帧生成路径。**

1. **★ 屏幕存成图片。** 每次采样写一个 640×360 24-bit BMP 到
   `<我的文档>\\My Games\\Skyrim Special Edition\\SKSE\\DFG_screens\\screen_NNN.bmp`，
   环形 96 个文件（自覆盖，不无限增长），日志行带上文件名。
   理由：哈希回答「变了没有」，回答不了「变出来的是不是游戏」—— 而后者已经花掉四天。
   **一张没人找得到的图等于没有图（L58），所以文件名必须进日志。**
2. **判据换成连续样本同一性。** 行上新增 `same=`（与上一张**逐字节相同**的连续次数）、
   `oursSame=`（我们自己 colorOut 的同项）、`dLum=`（亮度差幅度）。
   `same>=7 && oursSame<=1` ⇒ `[SCREEN] STALE`；`same>=3 && oursSame<=1` ⇒
   **`[SCREEN] FROZEN`（本项目第一条能看见用户从 15 号起就在描述的那个故障的判据）**。
   为什么 `oursSame` 是必须的：菜单里我们的 colorOut 哈希会连续重复十几次
   （`1C6B76BA62059E4D` 在 13:25:48–13:26:44 之间出现 11 次），没有它就会在菜单里误报。
3. **采样节奏 1 Hz → 有 4x 时 2.5 Hz**（`(frames>60 && lastPr>frames+8)` 时 `tick%2==0`）。
   最近八局世界段 2.0/2.1/2.5/3.0/3.2/4.1/5.7/6.1 秒 ⇒ 1 Hz 只有 2~6 张。`same>=3` 需要至少 3 张。
4. **flush 提到捕获之前。** 原来一 tick 的行全部先写、`fflush` 在循环末尾，
   而 GDI blit 是这个循环里唯一会阻塞的调用 —— **一次阻塞的 blit 会静默吃掉整个 tick 的读数。**
   本局本文件最后一行在游戏丢焦点前 110 ms，下一个 tick 从未到达，正是这个形状。
5. **`PollHomeKey` 里加逐帧（~35 Hz）按键组合检测**：展开别名、打印真实键集、
   点名 `ALT+F4 (quit)` / `ALT+TAB (unfocus)` / `ALT+ENTER` / `ALT+ESC` / `CTRL+ESC` / `F4`。
   理由：**「进程被杀」和「玩家自己退出」是两个不同的结论，只有一个是我们的 bug。**
6. **`INPUT_SEEN` 判据收窄成 `INPUT_MOVE_SEEN`**（必须有能移动角色的键，或鼠标动过），
   否则 `INPUT_NONMOVE` —— 不再拿 Alt 当「世界没响应」的证据。

**验证**：16 锚点 count==1｜构建 0 error（第一次编译失败：补丁脚本里 `\\n` 写成 `\\n` 前少了一层转义，
字符串常量里进了真换行，已修）｜DLL **1,394,176 B · `e02600bb0c5d94226df78d84acf6dec6`**，
**build == MO2 部署**｜11 个新串在、2 个旧串消失｜INI 未动（`efce8911…`，358 行 CRLF，双份一致）｜
行尾 DX 纯 LF / FG 纯 CRLF。

## 44.7 下一局要读的四件事

| 看到 | 结论 |
|---|---|
| `[INPUT] *** ALT+F4 (quit) ***` 且键集含 `73` | **这一局是用户自己退的** —— 「进程被终止」从此有主语 |
| `[INPUT] *** ALT+TAB (unfocus) ***` | 游戏被切到后台，Skyrim 会停渲染 ⇒ **「卡死」可能是切出去造成的** |
| 键集只有 `[12 A4]`（Alt 单独） | 焦点丢失不是 Alt 干的 ⇒ 继续查外部 |
| `[SCREEN] FROZEN for N captures` | **★ 四天来第一次真正量到用户说的冻结**，且有图可看 |
| `DFG_screens\\screen_*.bmp` | 直接看图：黑 / 冻 / 撕裂 / 重影，一眼可见 |

## 44.8 仍未证（不许假装）

- **「4x 导致卡死」仍未证**，而且本局是**反证**：4x 上台后 panel 139 flips/s、real 34.4 fps、
  `hrsD` 在走、`paused=0`，日志里没有任何一行像卡死。
- **2x 对照局（`MFGMaxFramesOverride=0`）仍然一次都没跑过** —— 四天里最大的方法论缺口。
- **那 1.5~2 秒之后到底发生了什么仍未证**：本局只有「丢焦点」+「Alt 按下」两个读数，
  谁先谁后、是否有第二个键，都要等 v1.31 的逐帧键集。
- **Transfusion 隔离实验**（`DINPUT8.dll` -> `DINPUT8.dll.transfusion-off`，**不能用 `.disabled`**）
  仍然一次都没跑过。
- `WriteScreenBmp` 与 `s_scrSame`/`FROZEN` **一局都没跑过** ⇒ 首跑按「校准」读（L53）。
"""


def main() -> int:
    raw = LEDGER.read_bytes()
    assert b"\r" not in raw, "ledger must stay pure LF"
    txt = raw.decode("utf-8")
    assert "# 第 44 章" not in txt, "chapter 44 already present"
    txt = txt.rstrip("\n") + "\n" + CH
    if not txt.endswith("\n"):
        txt += "\n"
    LEDGER.write_bytes(txt.encode("utf-8"))
    raw2 = LEDGER.read_bytes()
    print("ledger %d -> %d bytes, CR count = %d, ch44 = %s"
          % (len(raw), len(raw2), raw2.count(b"\r"), b"# \xe7\xac\xac 44 \xe7\xab\xa0" in raw2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
