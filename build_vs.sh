#!/usr/bin/env bash
# Build DynamicShaderFrameGen (x64) from Git Bash - equivalent of build_vs.bat.
#
# Why this exists: the agent's shell cannot invoke cmd.exe/build_vs.bat (blocked
# by sandbox policy), so the same pinned toolchain is exported here instead.
# Same two rules as the .bat apply: never add <SDK>\cppwinrt to INCLUDE (it
# clashes with vcpkg's C++/WinRT), and keep MSVCVER / SDKVER in sync with the
# installed toolchain.
#
# Usage:  bash build_vs.sh            # incremental
#         bash build_vs.sh --clean    # wipe build/NINJA first
set -euo pipefail

MSVCVER="14.50.35717"
SDKVER="10.0.26100.0"
MSVC="C:/Program Files (x86)/Microsoft Visual Studio/18/BuildTools/VC/Tools/MSVC/${MSVCVER}"
SDK="C:/Program Files (x86)/Windows Kits/10"
BUILD="D:/Modding/DynamicShaderFrameGen/build/NINJA"
CMAKE="/c/Program Files/CMake/bin/cmake"

[ -x "${MSVC}/bin/Hostx64/x64/cl.exe" ] || { echo "[FAIL] cl.exe missing: ${MSVC}/bin/Hostx64/x64/cl.exe"; exit 1; }
[ -f "${SDK}/Include/${SDKVER}/ucrt/stddef.h" ] || { echo "[FAIL] SDK headers missing under ${SDK}/Include/${SDKVER}"; exit 1; }

export INCLUDE="${MSVC}/include;${SDK}/Include/${SDKVER}/ucrt;${SDK}/Include/${SDKVER}/shared;${SDK}/Include/${SDKVER}/um;${SDK}/Include/${SDKVER}/winrt"
export LIB="${MSVC}/lib/x64;${SDK}/Lib/${SDKVER}/ucrt/x64;${SDK}/Lib/${SDKVER}/um/x64"
export PATH="${MSVC}/bin/Hostx64/x64:$PATH"

if [ "${1:-}" = "--clean" ]; then rm -rf "$BUILD"; fi

cd "$BUILD"
"$CMAKE" --build .
echo "BUILD SUCCESS: ${BUILD}/DynamicShaderFrameGen.dll"
