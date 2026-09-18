import hashlib
import os
import sys

PAIRS = [
    ("build", r"D:/Modding/DynamicShaderFrameGen/build/NINJA/DynamicShaderFrameGen.dll"),
    ("deployed", r"E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins/DynamicShaderFrameGen.dll"),
]

MARKERS = [b"DLL_PROCESS_DETACH", b"[exit] ", b"stim=%llu", b"fence=%s",
           b"BYPASS present hr=", b"samples the GPU timeline from its own thread",
           b"frames=%llu silent=%lldms"]


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


info = {}
for label, p in PAIRS:
    if not os.path.isfile(p):
        print(f"{label:9s} MISSING  {p}")
        continue
    st = os.stat(p)
    info[label] = (md5(p), st.st_size, p)
    print(f"{label:9s} md5={md5(p)}  size={st.st_size}  {p}")

if "build" in info and "deployed" in info:
    same = info["build"][0] == info["deployed"][0]
    print(f"\nMATCH = {same}")
    if not same:
        print("  !! build 与部署目录不一致")

src = info.get("build", (None, None, PAIRS[0][1]))[2]
if os.path.isfile(src):
    blob = open(src, "rb").read()
    print("\n-- v0.73 markers inside the built DLL --")
    for m in MARKERS:
        print(f"  {'OK ' if m in blob else 'MISSING'}  {m.decode('ascii', 'replace')}")
    # 看门狗行格式里的墙钟字段（printf 模板被拆开存储，用两个片段间接确认）
    print(f"  {'OK ' if b'%02d:%02d:%02d.%03d' in blob else 'MISSING'}  %02d:%02d:%02d.%03d")
