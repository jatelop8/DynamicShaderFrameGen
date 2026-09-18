#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append section 12 (2026-09-18) to the workspace daily log.

Append-only. The daily log is never rewritten, only extended, so this script
appends and guards against a double run with a marker string.
"""
import io
import sys

PATH = ("C:/Users/Administrator/WorkBuddy/2026-09-17-11-48-48/"
        ".workbuddy/memory/2026-09-18.md")
MARKER = "## 12. \u300c\u5230\u5e95\u80fd\u4e0d\u80fd\u89e3\u51b3\u300d\u2014\u2014 22:02 \u65e5\u5fd7\u91cd\u8bfb"

SECTION = """

---

## 12. \u300c\u5230\u5e95\u80fd\u4e0d\u80fd\u89e3\u51b3\u300d\u2014\u2014 22:02 \u65e5\u5fd7\u91cd\u8bfb\uff0c\u5426\u6389\u4e86\u7b2c 14 \u7ae0\u7684\u4e00\u534a

### 12.1 \u8d77\u56e0
\u7528\u6237\u95ee\uff1a\u300c\u6211\u60f3\u77e5\u9053\u8fd9\u6b21\u4f60\u5230\u5e95\u80fd\u4e0d\u80fd\u89e3\u51b3\u5361\u6b7b\u5f97\u95ee\u9898\u4e86\uff0c\u662f\u5426\u80fd\u5b8c\u6210\u76ee\u6807\u4efb\u52a1\uff0c\u5982\u679c\u4e0d\u80fd\u4f60\u4ea4\u4ed8\u6ca1\u6709\u610f\u4e49\u300d

\u4e3a\u4e86\u4e0d\u7ed9\u51fa\u4e0d\u8d1f\u8d23\u4efb\u7684\u627f\u8bfa\uff0c\u6211\u6ca1\u6709\u76f4\u63a5\u56de\u7b54\uff0c\u800c\u662f**\u628a 22:02 \u90a3\u4efd v1.06 \u65e5\u5fd7\u6309\u300c\u51bb\u7ed3\u7684\u673a\u68b0\u6210\u56e0\u300d
\u91cd\u65b0\u8d70\u4e86\u4e00\u904d**\uff08\u800c\u4e0d\u662f\u6309\u6211\u4e0a\u4e00\u8f6e\u7684\u5047\u8bbe\u8d70\uff09\u3002\u7ed3\u679c\u5426\u6389\u4e86\u7b2c 14 \u7ae0\u7684\u4e00\u534a\u7ed3\u8bba\u3002

### 12.2 \u65b0\u4e8b\u5b9e\u4e00\uff1a\u65cf\u9501**\u6ca1\u6709**\u5835\u4f4f\u53d1\u5e03\u901a\u9053
\u9501\u786e\u5b9e\u5728\u81f4\u75c5\u8def\u5f84\u4e0a \u2014\u2014 `FrameGen.cpp:991` \u7684 `frameBufferCopy = a_src` \u662f\u552f\u4e00\u5411 DLSS-G
\u53d1\u5e03\u76f8\u673a\u7684\u5199\u5165\u70b9\uff0c\u9501\u5757\u5185\u7684 `return false`\uff08\u73b0\u5728\u5728 `FrameGen.cpp:947`\uff09\u4f1a\u7ed5\u8fc7\u5b83\u3002
\u4f46 22:02 \u7684\u8ba1\u6570\u662f\uff1a

```
snap(acc/jmp/re/zero/arr/frozen/shape/rejPct)=11821/309/0/0/12130/0/9196 75.8%
```

12130 \u6b21\u5230\u8fbe\uff0c**11821 \u6b21\u88ab\u53d1\u5e03\uff0897%\uff09**\uff0c\u53ea\u6709 309 \u6b21\u88ab\u62d2\u3002\u800c\u90a3 309 \u6b21**\u6b63\u662f\u505a\u5bf9\u4e86\u4e8b**\uff1a

```
[CAM] #8048 family rejected: proj00=0.8391 locked=0.149184 ratio=5.6246 \\
      pos=(-243.0,-415.3,118.6) dist=1258.1 - another render pass, never re-acquires
```

\u9501\u5728\u4e16\u754c\u65cf 0.149184\uff0c\u62d2\u6389\u83dc\u5355\u65cf 0.8391 \u2014\u2014 \u8fd9\u6b63\u662f v1.00 \u60f3\u8981\u7684\u884c\u4e3a\u3002
**\u21d2\u300c\u65cf\u9501 = 22:02 \u51bb\u7ed3\u7684\u6210\u56e0\u300d\u8fd9\u4e2a\u65ad\u8a00\u4e0d\u6210\u7acb\u3002
**\u21d2\u672c\u6587\u4ef6 \u00a711.3\u300c\u7b2c\u4e09\u6210\u56e0\uff1a\u65cf\u9501\u53ea\u6709\u8d4b\u503c\u3001\u6ca1\u6709\u6e05\u96f6\u300d\u88ab\u672c\u8282\u5426\u6389\uff1a\u90a3\u4e2a\u201c\u6ca1\u6709\u6e05\u96f6\u201d\u662f\u771f\u7684\uff0c
\u4f46\u5b83**\u4e0d\u662f\u51bb\u7ed3\u7684\u6210\u56e0** \u2014\u2014 \u9501\u5728 22:02 \u53cd\u800c\u6b63\u5728\u6b63\u786e\u5730\u62d2\u7edd\u83dc\u5355\u65cf\u3002**

### 12.3 \u65b0\u4e8b\u5b9e\u4e8c\uff1a\u88ab\u53d1\u5e03\u7684\u76f8\u673a**\u539f\u5730\u4e0d\u52a8**
```
[CAM] acc #10255 pos=(-243.05,-415.31,118.56) move=0.0000 path=72.92
[CAM] acc #10783 pos=(-243.05,-415.31,118.56) move=0.0000 path=72.92
[CAM] acc #11541 pos=(-285.88,-410.36,96.87)  move=0.0000 path=121.33
[CAM] acc #11801 pos=(-285.88,-410.36,96.87)  move=0.0000 path=121.33
```
- `move` \u8fde\u7eed 0.0000\uff1b`pos` \u5728 1e-2 \u7cbe\u5ea6\u4e0b\u51e0\u5341\u79d2\u4e0d\u53d8\uff1b
- `path` \u53ea\u4ece 72.92 \u722c\u5230 136.60\uff0c\u5168\u90e8\u589e\u91cf\u6765\u81ea**\u4e24\u6b21\u69fd\u4f4d\u5207\u6362**\uff08#10255\u2192#10976\u3001#11366\u2192#11996\uff09\uff0c\u4e0d\u662f\u8fde\u7eed\u8fd0\u52a8\uff1b
- `cur == prev` \u21d2 `clipToPrev = I`\uff08\u5fc3\u8df3 `clipDev=0.000015`\u3001`clipDevMax=0.0000`\uff09
  \u21d2 \u751f\u6210\u7684\u5e27\u662f\u5f53\u524d\u5e27\u526f\u672c \u21d2 **\u753b\u9762\u4e0d\u53ef\u80fd\u524d\u8fdb = \u51bb\u7ed3\u7684\u673a\u68b0\u5b9a\u4e49**\u3002

### 12.4 \u65b0\u4e8b\u5b9e\u4e09\uff1a\u90a3\u4efd\u76f8\u673a\u77e9\u9635**\u5f62\u72b6\u662f\u574f\u7684**
`[CAM] raw #10801` \u539f\u6587\uff1a
```
ProjUnj      | 0.8391 -0 0 0 | -0 0.471993 0 0 | 0 0 0 1 | 0 0 -0.0666638 0.0666667
ViewProjUnj  | 1.19174 0.00466757 -5.41947e-13 0
             | 1.24468e-05 -0.00317798 2.11867 0
             | -0.00391672 1.00003 0.00150006 -15.0006
             | -0.00391655 0.999991 0.0015 0
ViewInv      | 0.999992 5.87483e-06 -0.00391655 -0
             | 0.00391656 -0.00149999 0.999991 -0
             | -4.54747e-13 0.999999 0.0015 -0
             | -0 -0 -0 1
```
\u81ea\u6d3d\u6027\u68c0\u67e5\uff08\u6570\u5b57\u662f\u6211\u7b97\u7684\uff09\uff1a
- `ProjUnj[0][0]/ProjUnj[1][1] = 0.8391/0.471993 = 1.7775 = 16/9` \u21d2 `ProjUnj` \u662f\u5e72\u51c0\u7684\u771f\u6295\u5f71\uff1b
- \u4f46 `[3][3] = 0.0666667 = 1/15.0006`\uff08\u771f\u900f\u89c6\u5e94\u4e3a 0\uff09\u3001`[2][2] = 0`\uff08\u5e94\u4e3a `f/(f-n)`\uff09\uff1b
- `ViewProjUnj` \u7684 w \u884c\u662f `(-0.00391655,0.999991,0.0015,0)`\uff0c**\u4e0d\u662f `[0,0,0,1]`**\uff1b`detProj=0`\uff1b
- \u9010\u5143\u7d20\u5bf9\u7167\uff1a`ViewProjUnj` \u7b2c 3 \u884c = `View`\uff08`ViewInv` \u7684\u9006\uff09\u7684\u7b2c 2 \u884c\uff1b
  \u5b83\u65e2\u4e0d\u662f `Proj@View`\u3001\u4e5f\u4e0d\u662f `View@Proj`\u3001\u4e5f\u4e0d\u662f\u4e24\u8005\u8f6c\u7f6e\uff08\u4e09\u79cd\u6211\u90fd\u7b97\u8fc7\uff09\u3002
- **`FrameGen.h:326-332` \u7684 v0.86 \u6ce8\u91ca\u65e9\u5c31\u5199\u4e0b\u4e86\u540c\u4e00\u6bb5\u6570\u5b57**\uff1a\u201cnot a camera at all, but a
  mis-offset read of the perFrame constant buffer\u201d\u3002\u6211\u628a\u5b83\u8bb0\u8fdb\u4e86 header\uff0c\u7136\u540e**\u5728\u5b83\u4e0a\u9762\u53e0\u4e86
  \u4e09\u4ee3\u542f\u53d1\u5f0f**\uff08\u65cf\u6307\u7eb9\u3001\u91cf\u7ea7\u9003\u9038\u3001\u91ca\u653e\u8def\u5f84\uff09\uff0c\u4ece\u6765\u6ca1\u53bb\u67e5\u90a3\u4e2a\u8bfb\u3002

### 12.5 \u4f46\u8fd9\u4e09\u6761\u90fd**\u4e0d\u80fd\u5b9a\u6848**
`move=0.0000` **\u53ea\u6709\u5728\u73a9\u5bb6\u5728\u8d70\u7684\u65f6\u5019\u624d\u662f\u9519\u8bef**\u3002\u8fd9\u4efd\u65e5\u5fd7\u91cc\u73a9\u5bb6\u51e0\u4e4e\u6ca1\u52a8\u3002
\u800c `FrameGen.cpp:1001-1003`\uff08v0.68 \u57cb\u7684\u63a2\u9488\uff09\u6ce8\u91ca\u539f\u6587\u5c31\u662f\u4e3a\u8fd9\u4e00\u523b\u5199\u7684\uff1a
> \u201c\u82e5\u73a9\u5bb6\u5728\u8d70\u800c\u8fd9\u91cc move/path \u6052\u4e3a 0.000\uff0c\u5219\u6839\u56e0\u5728\u6355\u83b7\u5c42\uff0c\u4efb\u4f55\u91cd\u6295\u5f71\u4fa7\u7684\u4fee\u6cd5\u90fd\u6551\u4e0d\u4e86\u3002\u201d

**\u21d2 \u8fd9\u4efd\u65e5\u5fd7\u6070\u597d\u6ca1\u6709\u56de\u7b54\u5b83\u3002\u7f3a\u7684\u662f\u4e00\u4e2a\u6570\u636e\u70b9\uff0c\u4e0d\u662f\u53c8\u4e00\u4e2a\u731c\u60f3\u3002**

### 12.6 \u7ed9\u7528\u6237\u7684\u4e0b\u4e00\u6b65\uff08\u5236\u6210 `docs/acceptance-v1.07b.html`\uff09
\u8fdb\u6e38\u620f \u2192 4x \u8dd1\u8d77\u6765 \u2192 **\u6309\u4f4f W \u8d70\u7ea6 10 \u79d2\u5e76\u8f6c\u89c6\u89d2** \u2192 \u9000\u51fa \u2192 \u8dd1 `tools/analyze_session.py`\u3002\u4e09\u6761\u5224\u636e\uff1a

| \u5224\u636e | \u8bfb\u6570 | \u6839\u56e0 | \u4e0b\u4e00\u6b65 |
|---|---|---|---|
| A | `move` \u975e 0 \u4e14 `clipDev` > 0 | \u76f8\u673a\u94fe\u597d | \u51bb\u7ed3\u5728\u5448\u73b0/\u914d\u901f\u4fa7\uff08pacer / Present\uff09 |
| B | \u5728\u8d70\u4f46 `move`\u22480\u3001`path`\u22480 | **\u6355\u83b7\u5c42**\u4e0d\u8ddf\u73a9\u5bb6 | perFrame \u955c\u50cf\u7684\u504f\u79fb/\u5e03\u5c40\uff08`[3][3]=0.0667`\u3001w \u884c\u2260`[0,0,0,1]`\uff09 |
| C | `move` \u5927\u4f46 `clipToPrev`\u2248I | \u91cd\u5efa/\u5386\u53f2\u4e22\u8fd0\u52a8 | `rebuildViewProj`\uff08`Streamline.cpp:629\uff09\u4e0e `s_prevVP`\uff08`1022-1050`\uff09 |

### 12.7 \u672c\u8f6e\u4ea7\u51fa
- `MFG_MASTER_NOTES.md` 62,970 \u2192 **70,096 B / 1,296 \u884c**\uff08\u65b0\u589e\u7b2c 15 \u7ae0\uff0c\u542b\u5bf9\u7b2c 14 \u7ae0\u7684\u6b63\u5f0f\u66f4\u6b63 15.6\uff09
- `tools/notes_ch15.py`\uff08\u65b0\uff09\u2014\u2014 \u951a\u70b9 `count==1`\u3001\u5e42\u7b49\u6807\u8bb0\u3001**8 \u9879 post-condition \u5305\u542b\u4e00\u6761\u201c\u53cd\u5411\u201d\u68c0\u67e5**
- `docs/acceptance-v1.07b.html` \u2014\u2014 **\u6574\u7bc7\u91cd\u5199**\uff1a\u4e0a\u4e00\u7248\u662f\u201c\u770b\u65cf\u9501\u662f\u5426\u91ca\u653e\u201d\uff0c\u65b9\u5411\u5df2\u9519\uff1b\u73b0\u5728\u662f\u201c10 \u79d2\u5b9e\u9a8c + A/B/C \u5224\u636e\u8868\u201d
- \u672c\u8282

### 12.8 \u7ecf\u9a8c\uff08\u56db\u6761\uff0c\u53ef\u590d\u7528\uff09
1. **\u300c\u4fee\u4e86\u4e00\u4e2a\u771f\u9519\u8bef\u300d \u2260 \u300c\u4fee\u7684\u662f\u6b63\u5728\u8ffd\u7684\u95ee\u9898\u300d** \u2014\u2014 v1.04 \u5df2\u5efa\uff0c\u672c\u8f6e\u518d\u6b21\u5e94\u9a8c\u3002
2. **\u72b6\u6001\u673a\u7684\u8f93\u51fa\u8ba1\u6570\u662f\u5b83\u6700\u4fbf\u5b9c\u7684\u53cd\u8bc1\u3002** \u53d1\u5e03\u8ba1\u6570\uff0811821/12130\uff09\u901a\u7740\uff0c\u5c31\u4e0d\u80fd\u8bf4\u5b83\u5835\u4f4f\u4e86\u4e0b\u6e38\u3002
3. **\u4e00\u4e2a\u63a2\u9488\u53ea\u80fd\u5728\u5b83\u7684\u524d\u63d0\u6210\u7acb\u65f6\u8bfb\u3002** `move=0` \u7684\u8bca\u65ad\u4ef7\u503c\u53d6\u51b3\u4e8e\u201c\u73a9\u5bb6\u5728\u4e0d\u5728\u8d70\u201d\uff0c\u800c\u8fd9\u4e2a\u524d\u63d0**\u5fc5\u987b\u4ece\u65e5\u5fd7\u91cc\u8bfb\u51fa\u6765**\u3002
4. **\u8bfb\u5230\u4e00\u4e2a\u88ab\u53cd\u590d\u8bb0\u5f55\u7684\u5f02\u5e38\u6570\u5b57\uff0c\u5148\u67e5\u5b83\u7684\u6765\u6e90\uff0c\u4e0d\u8981\u5728\u5b83\u4e0a\u9762\u53e0\u542f\u53d1\u5f0f\u3002** `[3][3]=0.0667` / w \u884c\u2260`[0,0,0,1]` \u5df2\u7ecf\u88ab v0.86 \u8bb0\u4e86\u4e00\u6b21\u3002

### 12.9 \u4ecd\u672a\u9a8c\u8bc1
- **v1.07b \u662f\u5426\u6b62\u4f4f\u51bb\u7ed3**\uff1a\u4e0d\u77e5\u9053\uff08\u6211\u65e0\u6cd5\u8fd0\u884c\u6e38\u620f\uff09\u3002
- \u4e16\u754c\u65cf 0.149184 / \u83dc\u5355\u65cf 0.8391 \u5230\u5e95\u5bf9\u5e94\u54ea\u4e24\u4e2a\u771f\u5b9e\u955c\u5934 \u2014\u2014 \u53ea\u77e5\u9053\u5b83\u4eec\u662f\u4e0d\u540c\u7684\uff1b
  `pos=(-243.05,-415.31,118.56)` \u4e00\u76f4\u88ab\u6211\u5f53\u4f5c\u201c\u83dc\u5355\u76f8\u673a\u201d\uff0c\u4f46 22:02 \u91cc\u5b83\u51fa\u73b0\u5728 **\u5df2\u8fdb\u4e16\u754c\u4e4b\u540e**\uff0c\u8fd9\u4e2a\u6807\u6ce8\u5f88\u53ef\u80fd\u4e5f\u9519\u4e86\u3002
- Modex \u9700\u5728 MO2 GUI \u624b\u52a8\u53d6\u6d88\u52fe\u9009\u3002RTX 20/30 \u7cfb\uff1bDLSS5 \u4e0a\u673a\u9a8c\u8bc1 \u2014\u2014 \u5747\u672a\u52a8\u3002
"""


def main():
    apply = "--apply" in sys.argv
    src = io.open(PATH, "rb").read().decode("utf-8")
    eol = "\r\n" if "\r\n" in src else "\n"
    body = SECTION.replace("\n", eol) if eol == "\r\n" else SECTION

    print("target        : %s" % PATH)
    print("eol           : %s" % ("CRLF" if eol == "\r\n" else "LF"))
    print("bytes before  : %d" % len(src.encode("utf-8")))
    print("marker present: %s   (must be False)" % (MARKER in src))
    if MARKER in src:
        print("REFUSED, nothing written: section 12 already present")
        return 1

    out = src
    if not out.endswith(eol):
        out += eol
    out += body

    checks = [
        ("section 12 heading present", out.count("## 12. ") == 1),
        # section 11's headings are ## 11.1 .. ## 11.16; there is no bare "## 11. "
        ("section 11 kept", "## 11.16 " in out),
        ("evidence 11821/12130 present", "11821/12130" in out),
        ("evidence stationary camera present", "move=0.0000 path=72.92" in out),
        ("self-correction of chapter 14 present", "\u7b2c 14 \u7ae0\u7684\u4e00\u534a" in out),
        ("A/B/C table present", "| A |" in out),
        ("grew", len(out.encode()) > len(src.encode())),
    ]
    bad = [n for n, ok in checks if not ok]
    print("--- post-conditions ---")
    for n, ok in checks:
        print("  %-46s %s" % (n, "OK" if ok else "FAIL"))
    if bad:
        print("REFUSED, nothing written: %s" % ", ".join(bad))
        return 1

    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply.")
        return 0
    io.open(PATH, "wb").write(out.encode("utf-8"))
    print("WROTE %d -> %d bytes" % (len(src.encode()), len(out.encode())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
