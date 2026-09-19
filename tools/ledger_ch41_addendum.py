import pathlib

ADDENDUM = """

## 八、附：`core.autocrlf=true` 是一把对着行尾铁律的枪（本轮新发现）

本工程有一条行尾铁律（`src/DX12SwapChain.cpp` 纯 LF；`src/ImguiMenu.cpp` / `src/Streamline.cpp`
纯 CRLF+BOM；账本 / 记忆 / 日记纯 LF）。本轮提交时 git 打出了这条警告：

```
warning: in the working copy of 'src/DX12SwapChain.cpp', LF will be replaced by CRLF
         the next time Git touches it
```

查证：`git config core.autocrlf` = **true**，仓库里**没有 `.gitattributes`**。

```
$ git ls-files --eol src/*.cpp
i/lf   w/lf     src/DX12SwapChain.cpp    <- 工作区 LF（对），index 里也是 LF
i/lf   w/crlf   src/ImguiMenu.cpp        <- 工作区 CRLF（对），index 里却是 LF
i/lf   w/crlf   src/Streamline.cpp
$ git show HEAD:src/DX12SwapChain.cpp | byte counts -> CRLF=0 LF=2254
$ git show HEAD:src/ImguiMenu.cpp     | byte counts -> CRLF=0 LF=533
```

**读法**：`autocrlf=true` 在 **add 时把工作区的 CRLF 规范化成 LF 存进 index**，
在 **checkout 时再把 LF 还原成 CRLF**。于是同一份配置对两个文件的效果正好相反：

- `src/ImguiMenu.cpp`（工作区 CRLF、index LF）：checkout 后**仍是 CRLF** ⇒ **侥幸**符合铁律。
- `src/DX12SwapChain.cpp`（工作区 LF、index LF）：checkout 后变成 **CRLF** ⇒ **违反铁律**。

⇒ **一条 `git restore src/DX12SwapChain.cpp` 就能把 LF 文件变成 CRLF，而且事后用 grep 看语法
没有任何异常**。它至今没被触发，只是因为本工程**一直只 commit、从不 checkout**。

**处置（本轮只记录，不改任何配置）**：

| 方案 | 后果 | 结论 |
|---|---|---|
| `git config core.autocrlf false` | `ImguiMenu.cpp` / `Streamline.cpp` 下次 checkout 会变 **LF**（**反向破坏**） | 否决 |
| 新增 `.gitattributes`（`text eol=...`） | index 里全部文件按新规则规范化 ⇒ **一次性巨大 diff**，污染全部历史对比 | 否决 |
| `*.cpp -text` | index 从 LF 改成 CRLF ⇒ 同样是一次性全文件 diff | 否决 |
| **只记录 + 加硬性规则** | 零风险 | **采用** |

⇒ 新增硬性规则（与行尾铁律同级）：

> **永远不要对本工程做 `git checkout` / `git restore` / `git stash pop` 之类会写回工作区的操作。**
> 若万不得已做了，**事后立刻**跑 `python tools/eol_census.py <四个文件>` 复查，因为 git 会静默改行尾。

（**L59**：**"只 commit 不 checkout"是一个没写在规则里的前提。** 一个工程能长期遵守行尾铁律，
可能不是因为铁律被守住了，而是因为**那条会破坏它的命令从来没被用过**。
凡是"一直以来都对"的东西，都要问一句：**它靠什么维持**。）
"""

p = pathlib.Path("MFG_MASTER_NOTES.md")
raw = p.read_bytes()
assert b"\r" not in raw, "ledger must be pure LF before append"
assert "## 八、附：`core.autocrlf=true`".encode("utf-8") not in raw, "addendum already present"
before = len(raw)
out = raw + ADDENDUM.encode("utf-8")
assert b"\r" not in out, "addendum introduced CR"
p.write_bytes(out)
print("appended", len(out) - before, "bytes; total", len(out))
