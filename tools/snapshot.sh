#!/usr/bin/env bash
# 每次改动前跑这个。用法：
#   bash tools/snapshot.sh v1.06                 # 只备份源码
#   bash tools/snapshot.sh v1.06 --with-build    # 额外备份 build 产物与部署 INI
#
# 规则（写死，别绕过）：
#   1. 备份目录名必须带版本号 + 时间戳，永不覆盖
#   2. 至少含 Streamline.cpp/.h + DX12SwapChain.cpp/.h
#   3. --with-build 时额外存 built_DLL + deployed.ini（便于整体回退）
#   4. 备份完成后打印 md5，便于与"改后"对比
set -euo pipefail

VER="${1:-}"
shift || true
WITH_BUILD=0
for a in "$@"; do
  [ "$a" = "--with-build" ] && WITH_BUILD=1
done

if [ -z "$VER" ]; then
  echo "用法: bash tools/snapshot.sh <版本号> [--with-build]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TS="$(date +%Y%m%d-%H%M%S)"
DEST="src/backup-${VER}-${TS}"
mkdir -p "$DEST"

SRC_FILES="src/Streamline.cpp src/Streamline.h src/DX12SwapChain.cpp src/DX12SwapChain.h"
for f in $SRC_FILES; do
  if [ ! -f "$f" ]; then echo "缺少文件: $f" >&2; exit 3; fi
done
cp $SRC_FILES "$DEST/"

if [ "$WITH_BUILD" = "1" ]; then
  [ -f build/NINJA/DynamicShaderFrameGen.dll ] && cp build/NINJA/DynamicShaderFrameGen.dll "$DEST/built_DLL.bin" || true
  DEPLOY="E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins"
  [ -f "$DEPLOY/DynamicShaderFrameGen.ini" ] && cp "$DEPLOY/DynamicShaderFrameGen.ini" "$DEST/deployed.ini" || true
  [ -f "$DEPLOY/DynamicShaderFrameGen.dll" ] && cp "$DEPLOY/DynamicShaderFrameGen.dll" "$DEST/deployed_DLL.bin" || true
fi

echo "=== 备份完成: $DEST ==="
ls -la "$DEST"
echo
echo "--- md5（改后请与此对比）---"
md5sum $SRC_FILES
[ -f "$DEST/built_DLL.bin" ] && md5sum "$DEST/built_DLL.bin"
[ -f "$DEST/deployed_DLL.bin" ] && md5sum "$DEST/deployed_DLL.bin"
[ -f "$DEST/deployed.ini" ] && md5sum "$DEST/deployed.ini"

echo
echo "=== 行尾实测（改前基线，改后必须一致）==="
python - <<'PY'
import glob
for p in sorted(glob.glob('src/*.cpp'))+sorted(glob.glob('src/*.h')):
    b=open(p,'rb').read()
    crlf=b.count(b'\r\n'); lf=b.count(b'\n')-crlf
    kind = 'CRLF' if crlf and not lf else ('LF' if lf and not crlf else 'MIXED')
    print(f'  {p:28s} {len(b):8d}  CRLF={crlf:5d} LF={lf:5d}  {kind}')
PY
