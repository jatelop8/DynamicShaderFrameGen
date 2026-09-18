#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notes_ch15.py -- append chapter 15 to MFG_MASTER_NOTES.md.

WHY THIS CHAPTER EXISTS
-----------------------
Chapter 14 declared "the camera family lock has no release path" to be the third
cause of the freeze, and v1.07b was released on that claim. Re-reading the 22:02
log against the MECHANICAL definition of a frozen picture falsifies half of it:
the lock's own counters show the publish path was open (11821 publishes out of
12130 arrivals), and the family-rejection branch was doing exactly what v1.00
intended. The chapter therefore has to correct 14.x rather than rest on it.

Convention (see the maintenance rules at the end of the notes):
  * default dry run, --apply to write
  * every anchor must have count(old) == 1, else REFUSED, nothing written
  * insert-type edit, so a marker guard is mandatory:
    "anchor unique" and "ran only once" are two different things
  * post-conditions are checked on the RESULT text, not the input
"""
import io
import sys

TARGET = "MFG_MASTER_NOTES.md"
MARKER = "## 第 15 章"

ANCHOR = "\n---\n---\n\n**\u672c\u6587\u4ef6\u7ef4\u62a4\u89c4\u5219**"

CHAPTER = """
---

## 第 15 章：22:02 \u65e5\u5fd7\u91cd\u8bfb \u2014\u2014 \u7b2c 14 \u7ae0\u7684\u7ed3\u8bba\u88ab\u5b83\u81ea\u5df1\u7684\u65e5\u5fd7\u5426\u6389\u4e86\u4e00\u534a

\u8fd9\u4e00\u7ae0\u4e0d\u662f\u65b0\u53d1\u73b0\uff0c\u662f**\u81ea\u68c0**\u3002\u7528\u6237\u95ee\u201c\u5230\u5e95\u80fd\u4e0d\u80fd\u89e3\u51b3\u201d\uff0c\u4e8e\u662f\u6211\u628a 22:02 \u90a3\u4efd\u65e5\u5fd7\u6309
**\u51bb\u7ed3\u7684\u673a\u68b0\u6210\u56e0**\uff08\u800c\u4e0d\u662f\u6309\u6211\u4e0a\u4e00\u8f6e\u7684\u5047\u8bbe\uff09\u91cd\u65b0\u8d70\u4e86\u4e00\u904d\u3002\u7ed3\u679c\uff1a\u7b2c 14 \u7ae0\u628a\u65cf\u9501\u5f53\u6210\u7b2c\u4e09\u6210\u56e0\uff0c
**\u8fd9\u4e2a\u65ad\u8a00\u88ab\u65e5\u5fd7\u81ea\u5df1\u7684\u8ba1\u6570\u5426\u6389\u4e86**\u3002

### 15.1 \u7b2c\u4e00\u4ef6\uff1a\u65cf\u9501\u5728 22:02 **\u6ca1\u6709** \u5835\u4f4f\u53d1\u5e03\u901a\u9053

\u9501\u786e\u5b9e\u5728\u81f4\u75c5\u8def\u5f84\u4e0a \u2014\u2014 `FrameGen.cpp:991` \u7684 `frameBufferCopy = a_src` \u662f**\u552f\u4e00**
\u5411 DLSS-G \u53d1\u5e03\u76f8\u673a\u7684\u5199\u5165\u70b9\uff0c\u800c\u9501\u5757\u5185\u7684 `return false`\uff08\u5f53\u524d\u5728 `FrameGen.cpp:947`\uff09
\u4f1a\u7ed5\u8fc7\u5b83\u3002\u6240\u4ee5\u9501\u8c03\u5ea6\u7684\u662f\u201c\u54ea\u4e00\u5e27\u7684\u76f8\u673a\u88ab\u53d1\u5e03\u201d\uff0c\u800c\u4e0d\u662f\u53cd\u6295\u5f71\u8def\u5f84\u672c\u8eab
\uff08`Streamline.cpp:666` \u7684\u6ce8\u91ca\u5c31\u662f\u8fd9\u4e2a\u610f\u601d\uff1a\u53cd\u6295\u5f71\u4e0d\u518d\u67e5\u8be2\u5b83\uff09\u3002

**\u4f46 22:02 \u7684\u8ba1\u6570\u8bf4\u660e\u53d1\u5e03\u901a\u9053\u662f\u5f00\u7684**\uff1a

```
snap(acc/jmp/re/zero/arr/frozen/shape/rejPct)=11821/309/0/0/12130/0/9196 75.8%
```

12130 \u6b21\u5230\u8fbe\uff0c**11821 \u6b21\u88ab\u53d1\u5e03\uff0897%\uff09**\uff0c\u53ea\u6709 309 \u6b21\u88ab\u62d2\u3002\u800c\u90a3 309 \u6b21\u6b63\u662f**\u505a\u5bf9\u4e86\u4e8b**\uff1a

```
[22:02:21] [CAM] #8048 family rejected: proj00=0.8391 locked=0.149184 ratio=5.6246 \\
             pos=(-243.0,-415.3,118.6) dist=1258.1 - another render pass, never re-acquires
```

\u9501\u5728**\u4e16\u754c\u65cf 0.149184**\uff0c\u62d2\u6389\u83dc\u5355\u65cf 0.8391 \u2014\u2014 \u8fd9\u6b63\u662f v1.00 \u60f3\u8981\u7684\u884c\u4e3a\u3002

> **\u65b9\u6cd5\u8bba\u94c1\u5f8b\uff08\u65b0\uff09\uff1a\u4e00\u4e2a\u72b6\u6001\u673a\u7684\u8f93\u51fa\u88ab\u8ba1\u6570\u8bc1\u660e\u662f\u901a\u7684\uff0c\u548c\u201c\u8fd9\u4e2a\u72b6\u6001\u673a\u662f\u6545\u969c\u70b9\u201d
> \u4e0d\u80fd\u540c\u65f6\u6210\u7acb\u3002\u53d1\u5e03\u8ba1\u6570\u662f\u6700\u4fbf\u5b9c\u7684\u53cd\u8bc1\u3002**

### 15.2 \u7b2c\u4e8c\u4ef6\uff1a\u88ab\u53d1\u5e03\u7684\u76f8\u673a**\u539f\u5730\u4e0d\u52a8**

```
[CAM] acc #10255 pos=(-243.05,-415.31,118.56) move=0.0000 path=72.92
[CAM] acc #10783 pos=(-243.05,-415.31,118.56) move=0.0000 path=72.92
[CAM] acc #11541 pos=(-285.88,-410.36,96.87)  move=0.0000 path=121.33
[CAM] acc #11801 pos=(-285.88,-410.36,96.87)  move=0.0000 path=121.33
```

- `move`\uff08\u9010\u5e27\u4f4d\u79fb\uff09\u8fde\u7eed\u4e3a **0.0000**\uff1b`pos` \u5728 1e-2 \u7cbe\u5ea6\u4e0b**\u51e0\u5341\u79d2\u4e0d\u53d8**\uff1b
- `path` \u53ea\u4ece 72.92 \u722c\u5230 136.60\uff08\u8de8\u51e0\u5341\u79d2\uff09\uff0c**\u5168\u90e8\u589e\u91cf\u6765\u81ea\u4e24\u6b21\u69fd\u4f4d\u5207\u6362**
  \uff08`#10255\u2192#10976` \u4e0e `#11366\u2192#11996`\uff09\uff0c\u4e0d\u662f\u8fde\u7eed\u8fd0\u52a8\uff1b
- `cur == prev` \u21d2 `clipToPrev = I`\uff08\u5fc3\u8df3 `clipDev=0.000015`\u3001`clipDevMax=0.0000`\uff09
  \u21d2 **DLSS-G \u751f\u6210\u7684\u5e27\u662f\u5f53\u524d\u5e27\u7684\u526f\u672c \u21d2 \u753b\u9762\u4e0d\u53ef\u80fd\u524d\u8fdb\u3002\u8fd9\u5c31\u662f\u201c\u51bb\u7ed3\u201d\u7684\u673a\u68b0\u5b9a\u4e49\u3002**
- \u5fc3\u8df3 `pos == prevPos` \u9010\u5b57\u76f8\u540c\uff0c\u4e0e\u4e4b\u4e00\u81f4\u3002

### 15.3 \u7b2c\u4e09\u4ef6\uff1a\u90a3\u4efd\u76f8\u673a\u77e9\u9635**\u5f62\u72b6\u662f\u574f\u7684**

`[CAM] raw #10801` \u539f\u6587\uff08\u672a\u5220\u8282\uff09\uff1a

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

\u81ea\u6d3d\u6027\u68c0\u67e5\uff08\u8fd9\u6bb5\u6570\u5b57\u662f\u6211\u7b97\u7684\uff0c\u4e0d\u662f\u6211\u8bb0\u7684\u7ed3\u8bba\uff09\uff1a

- `ProjUnj[0][0] / ProjUnj[1][1] = 0.8391 / 0.471993 = 1.7775 = 16/9`
  \u21d2 **`ProjUnj` \u662f\u4e00\u4e2a\u5e72\u51c0\u7684\u771f\u6295\u5f71**\uff08\u5bbd\u9ad8\u6bd4\u5bf9\u5f97\u4e0a 3840x2160\uff09\u3002
- \u4f46 `ProjUnj[3][3] = 0.0666667 = 1/15.0006`\uff0c\u800c\u771f\u900f\u89c6\u6295\u5f71\u7684 `[3][3]` \u5e94\u4e3a **0**\uff1b
  `[2][2]` \u5e94\u4e3a `f/(f-n)` \u5374\u662f **0**\u3002\u21d2 \u77e9\u9635\u5373\u4f7f\u662f\u771f\u7684\uff0c**\u5b58\u50a8\u5e03\u5c40\u4e5f\u548c\u8bfb\u53d6\u65b9\u5047\u8bbe\u5bf9\u4e0d\u4e0a**\u3002
- `ViewProjUnj` \u7684 w \u884c\u662f `(-0.00391655, 0.999991, 0.0015, 0)`\uff0c**\u4e0d\u662f `[0,0,0,1]`**\uff1b`detProj = 0`\u3002
- \u9010\u5143\u7d20\u5bf9\u7167\uff1a`ViewProjUnj` \u7b2c 3 \u884c **\u7b49\u4e8e `View`\uff08\u5373 `ViewInv` \u7684\u9006\uff09\u7684\u7b2c 2 \u884c**\uff1b
  `ViewProjUnj[2][3] = -15.0006` \u800c `View` \u8be5\u4f4d\u4e3a 0\u3002
  \u5b83\u65e2\u4e0d\u662f `Proj @ View`\uff0c\u4e5f\u4e0d\u662f `View @ Proj`\uff0c\u4e5f\u4e0d\u662f\u4e24\u8005\u7684\u8f6c\u7f6e\uff08\u4e09\u79cd\u6211\u90fd\u7b97\u8fc7\uff09\u3002
- **`FrameGen.h:326-332` \u7684 v0.86 \u6ce8\u91ca\u65e9\u5c31\u5199\u4e0b\u4e86\u540c\u4e00\u6bb5\u6570\u5b57**\uff1a
  > `row3=(-0.00391655,0.999991,0.0015,0) ... not a camera at all, but a
  >  mis-offset read of the perFrame constant buffer`
  **\u6211\u628a\u5b83\u8bb0\u8fdb\u4e86 header\uff0c\u7136\u540e\u5728\u5b83\u4e0a\u9762\u7ee7\u7eed\u53e0\u542f\u53d1\u5f0f\uff08\u65cf\u6307\u7eb9\u3001\u91cf\u7ea7\u9003\u9038\u3001\u91ca\u653e\u8def\u5f84\uff09\uff0c
  \u4ece\u6765\u6ca1\u53bb\u67e5\u90a3\u4e2a\u8bfb\u3002**

### 15.4 \u4f46 15.2 / 15.3 **\u4e0d\u80fd\u5b9a\u6848** \u2014\u2014 \u7f3a\u7684\u662f\u4e00\u4e2a\u6570\u636e\u70b9\uff0c\u4e0d\u662f\u53c8\u4e00\u4e2a\u731c\u60f3

`move=0.0000` **\u53ea\u6709\u5728\u73a9\u5bb6\u5728\u8d70\u7684\u65f6\u5019\u624d\u662f\u9519\u8bef**\u3002\u8fd9\u4efd\u65e5\u5fd7\u91cc\u73a9\u5bb6\u51e0\u4e4e\u6ca1\u52a8
\uff08`path` \u8de8\u51e0\u5341\u79d2\u53ea\u6da8\u4e86 63.7\uff0c\u4e14\u5168\u90e8\u7531\u69fd\u4f4d\u5207\u6362\u8d21\u732e\uff09\u3002

`FrameGen.cpp:1001-1003`\uff08v0.68 \u57cb\u7684\u63a2\u9488\uff09\u6ce8\u91ca\u539f\u6587\u5c31\u662f\u4e3a\u8fd9\u4e00\u523b\u5199\u7684\uff1a

> \u201c\u82e5\u73a9\u5bb6\u5728\u8d70\u800c\u8fd9\u91cc move/path \u6052\u4e3a 0.000\uff0c\u5219\u6839\u56e0\u5728\u6355\u83b7\u5c42
> \uff08\u8bfb\u5230\u7684\u76f8\u673a\u6570\u636e\u4e0d\u8ddf\u8e2a\u771f\u5b9e\u76f8\u673a\uff09\uff0c\u4efb\u4f55\u91cd\u6295\u5f71\u4fa7\u7684\u4fee\u6cd5\u90fd\u6551\u4e0d\u4e86\u3002\u201d

**\u21d2 \u8fd9\u4efd\u65e5\u5fd7\u6070\u597d\u6ca1\u6709\u56de\u7b54\u5b83\u3002\u7f3a\u7684\u4e0d\u662f\u53c8\u4e00\u4e2a\u731c\u60f3\uff0c\u662f\u4e00\u4e2a\u6570\u636e\u70b9\u3002**

### 15.5 \u552f\u4e00\u7f3a\u7684\u5b9e\u9a8c\uff0810 \u79d2\uff0c\u4e00\u6b21\uff09\u4e0e\u4e09\u6761\u5224\u636e

\u8fdb\u6e38\u620f \u2192 4x \u8dd1\u8d77\u6765 \u2192 **\u6309\u4f4f W \u8d70\u7ea6 10 \u79d2\u5e76\u8f6c\u89c6\u89d2** \u2192 \u9000\u51fa\u3002\u53ea\u770b\u4e09\u884c\uff1a

| \u5224\u636e | \u8bfb\u6570 | \u6839\u56e0 | \u4e0b\u4e00\u6b65 |
|---|---|---|---|
| **A** | `move` \u660e\u663e\u975e 0 \u4e14 `clipDev` \u660e\u663e > 0 | \u76f8\u673a\u94fe\u662f\u597d\u7684 | \u51bb\u7ed3\u5728\u5448\u73b0/\u914d\u901f\u4fa7\uff08pacer / Present\uff09\uff0c\u53bb\u67e5\u90a3\u6761 |
| **B** | \u5728\u8d70\u4f46 `move`\u22480\u3001`path`\u22480 | **\u6355\u83b7\u5c42**\u8bfb\u5230\u7684\u76f8\u673a\u4e0d\u8ddf\u73a9\u5bb6 | \u67e5 perFrame \u955c\u50cf\u7684\u504f\u79fb/\u5e03\u5c40\uff0815.3 \u7684 `[3][3]=0.0667`\u3001w \u884c\u4e0d\u662f `[0,0,0,1]` \u5c31\u662f\u7ebf\u7d22\uff09 |
| **C** | `move` \u5927\u4f46 `clipToPrev`\u2248I | \u91cd\u5efa/\u5386\u53f2\u628a\u8fd0\u52a8\u4e22\u4e86 | \u67e5 `rebuildViewProj`\uff08`Streamline.cpp:629`\uff09\u4e0e `s_prevVP` \u63a8\u8fdb\uff08`1022-1050`\uff09 |

\u4e09\u79cd\u7ed3\u679c\u5bf9\u5e94\u4e09\u4e2a**\u4e0d\u540c\u7684**\u6839\u56e0\uff0c\u6bcf\u4e00\u79cd\u90fd\u76f4\u63a5\u6307\u5411\u4e00\u4e2a\u5177\u4f53\u4f8b\u7a0b\uff0c\u4e0d\u9700\u518d\u731c\u3002

### 15.6 \u5bf9\u7b2c 14 \u7ae0\u7684\u6b63\u5f0f\u66f4\u6b63

\u7b2c 14 \u7ae0\u628a\u201c\u65cf\u9501\u65e0\u91ca\u653e\u8def\u5f84\u201d\u5217\u4e3a\u7b2c\u4e09\u6761\u6210\u56e0\uff0c\u5e76\u636e\u6b64\u53d1\u5e03 v1.07b\u3002**\u66f4\u6b63\u5982\u4e0b**\uff1a

| 14 \u7ae0\u7684\u8bf4\u6cd5 | \u66f4\u6b63\u540e |
|---|---|
| \u5220\u9664 v1.03 \u91cf\u7ea7\u9003\u9038 | **\u4ecd\u7136\u6b63\u786e\u4e14\u5fc5\u8981**\u3002\u5b83\u786e\u5b9e\u662f\u90a3\u628a\u9501\u88ab\u201c\u8d70\u201d\u5230 0.8391 \u7684\u68d8\u8f6e\uff0c\u903c\u8fd1\u8fc7\u7a0b\u6709\u9010\u5e27\u65e5\u5fd7\u4e3a\u8bc1\uff08`#2 esc 1.0 \u2192 adopt`\u3001`#4 esc 0.149184 \u2192 adopt`\uff09 |
| \u65b0\u589e reset-edge \u91ca\u653e | **\u65e0\u5bb3\u4f46\u672a\u8bc1\u660e\u627f\u91cd**\uff08C1 \u56de\u5f52\u91cc\u53ea\u5220\u9003\u9038\u5c31\u5df2\u7ecf\u7ec8\u4e8e 0.149184\uff09 |
| \u201c\u65cf\u9501 = 22:02 \u51bb\u7ed3\u7684\u6210\u56e0\u201d | **\u88ab\u65e5\u5fd7\u81ea\u5df1\u5426\u6389**\uff1a11821/12130 \u53d1\u5e03\u6210\u529f\uff0c309 \u6b21\u62d2\u7edd\u5168\u90e8\u662f\u5bf9\u83dc\u5355\u65cf\u7684\u6b63\u786e\u62d2\u7edd |

**\u21d2 v1.07b \u4fdd\u7559\uff08\u5b83\u4fee\u7684\u662f\u771f bug\uff09\uff0c\u4f46\u4e0d\u80fd\u518d\u58f0\u79f0\u5b83\u4fee\u7684\u662f\u51bb\u7ed3\u3002**

### 15.7 \u56db\u6761\u53ef\u590d\u7528\u7684\u65b9\u6cd5\u8bba

1. **\u201c\u4fee\u4e86\u4e00\u4e2a\u771f\u9519\u8bef\u201d \u2260 \u201c\u4fee\u7684\u662f\u6b63\u5728\u8ffd\u7684\u95ee\u9898\u201d\u3002**\uff08v1.04 \u5df2\u5efa\uff0c\u672c\u7ae0\u518d\u6b21\u9a8c\u8bc1\uff09
2. **\u72b6\u6001\u673a\u7684\u8f93\u51fa\u8ba1\u6570\u662f\u5b83\u6700\u4fbf\u5b9c\u7684\u53cd\u8bc1\u3002**\u53d1\u5e03\u8ba1\u6570\u901a\u7740\uff0c\u5c31\u4e0d\u80fd\u8bf4\u5b83\u5835\u4f4f\u4e86\u4e0b\u6e38\u3002
3. **\u4e00\u4e2a\u63a2\u9488\u53ea\u80fd\u5728\u5b83\u7684\u524d\u63d0\u6210\u7acb\u65f6\u8bfb\u3002**`move=0` \u7684\u8bca\u65ad\u4ef7\u503c\u5b8c\u5168\u53d6\u51b3\u4e8e\u201c\u73a9\u5bb6\u5728\u4e0d\u5728\u8d70\u201d\u2014\u2014
   \u800c\u8fd9\u4e2a\u524d\u63d0\u672c\u8eab**\u5fc5\u987b\u4ece\u65e5\u5fd7\u91cc\u8bfb\u51fa\u6765**\uff0c\u4e0d\u80fd\u5047\u8bbe\u3002
4. **\u8bfb\u5230\u4e00\u4e2a\u88ab\u53cd\u590d\u8bb0\u5f55\u7684\u5f02\u5e38\u6570\u5b57\uff0c\u5148\u67e5\u5b83\u7684\u6765\u6e90\uff0c\u4e0d\u8981\u5728\u5b83\u4e0a\u9762\u53e0\u542f\u53d1\u5f0f\u3002**
   `[3][3]=0.0667` / w \u884c \u2260 `[0,0,0,1]` \u5df2\u7ecf\u88ab v0.86 \u8bb0\u4e86\u4e00\u6b21\uff0c\u6211\u5728\u5b83\u4e0a\u9762\u53e0\u4e86\u4e09\u4ee3\u542f\u53d1\u5f0f\u3002
"""


def main():
    apply = "--apply" in sys.argv
    src = io.open(TARGET, "rb").read().decode("utf-8")

    eol = "\r\n" if "\r\n" in src else "\n"
    chapter = CHAPTER.replace("\n", eol) if eol == "\r\n" else CHAPTER

    n = src.count(ANCHOR)
    print("target        : %s" % TARGET)
    print("eol           : %s" % ("CRLF" if eol == "\r\n" else "LF"))
    print("anchor count  : %d   (must be exactly 1)" % n)
    print("marker present: %s   (must be False)" % (MARKER in src))

    if n != 1:
        print("REFUSED, nothing written: anchor count is %d, not 1" % n)
        return 1
    if MARKER in src:
        print("REFUSED, nothing written: chapter 15 marker already present")
        return 1

    out = src.replace(ANCHOR, chapter + eol + ANCHOR, 1)

    # post-conditions on the RESULT, not the input
    checks = [
        ("chapter heading inserted", out.count("## \u7b2c 15 \u7ae0") == 1),
        ("chapter 14 survived", "\u7b2c 14 \u7ae0" in out),
        ("maintenance rules still last", out.rstrip().endswith(
            "**\u4e0d\u8986\u76d6\u5386\u53f2\u7ae0\u8282**\uff0c\u53ea\u5728\u7b2c 9 \u7ae0\u4e0e\u672b\u5c3e\u8ffd\u52a0\u3002")),
        ("green: 11821 evidence present", "11821/309/0/0/12130" in out),
        ("green: stationary camera evidence present",
         "move=0.0000 path=72.92" in out),
        ("green: the -15.0006 column present", "-15.0006" in out),
        ("green: the A/B/C decision table present", "| **A** |" in out),
        ("red: no stale claim that the lock caused it",
         "\u65cf\u9501 = 22:02 \u51bb\u7ed3\u7684\u6210\u56e0" in out),
    ]
    bad = [name for name, ok in checks if not ok]
    print("--- post-conditions ---")
    for name, ok in checks:
        print("  %-46s %s" % (name, "OK" if ok else "FAIL"))
    if bad:
        print("REFUSED, nothing written: failing post-conditions: %s" % ", ".join(bad))
        return 1

    lines_in = src.count(eol)
    lines_out = out.count(eol)
    print("line count    : %d -> %d (+%d)" % (lines_in, lines_out, lines_out - lines_in))
    assert lines_out > lines_in, "the chapter did not grow the file"

    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply to write.")
        return 0

    io.open(TARGET, "wb").write(out.encode("utf-8"))
    print("WROTE %s (%d -> %d bytes)" % (TARGET, len(src.encode()), len(out.encode())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
