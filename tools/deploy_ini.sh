#!/usr/bin/env bash
# deploy_ini.sh -- publish the repo INI to the MO2 mod directory, and verify.
#
# WHY THIS EXISTS (2026-09-19, cost: two wasted rounds)
# -----------------------------------------------------
# CMakeLists.txt deploys the INI with
#     add_custom_command(TARGET ${PROJECT_NAME} POST_BUILD
#         COMMAND ... copy_if_different "${CMAKE_SOURCE_DIR}/SKSE/Plugins/DynamicShaderFrameGen.ini" ...)
#
# Two consequences that were not understood, and both bit us:
#
#   1. The REPO copy is the deploy source. Hand-editing the deployed INI is
#      futile: the next build overwrites it with whatever the repo says. The
#      NRAllowWithFrameGen=1 fix was written into the deployed file at 11:25 and
#      silently reverted by the 11:45 build, because the repo copy still said 0.
#      (Same mechanism as the 11:17:57 "mystery" revert earlier in the day.)
#
#   2. POST_BUILD only runs when the target RELINKS. If ninja sees the DLL
#      up to date there is no POST_BUILD, so "I rebuilt" does not mean
#      "the INI was redeployed". Fixing the repo INI and running build_vs.sh
#      left the deployed file at the OLD md5.
#
# So: edit the repo INI, then run this. It copies unconditionally and fails loudly
# if the two md5s still disagree. Always use this instead of a bare build when the
# INI is what changed.
set -u

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_DIR/SKSE/Plugins/DynamicShaderFrameGen.ini"
DST_DIR="${1:-E:/EJ/mod/mods/DynamicShaderFrameGen/SKSE/Plugins}"
DST="$DST_DIR/DynamicShaderFrameGen.ini"

if [ ! -f "$SRC" ]; then echo "FAIL: no repo INI at $SRC"; exit 2; fi
if [ ! -d "$DST_DIR" ]; then echo "FAIL: no deploy dir $DST_DIR"; exit 3; fi

cp -p "$SRC" "$DST" || { echo "FAIL: copy failed"; exit 4; }

a=$(md5sum "$SRC" | cut -d' ' -f1)
b=$(md5sum "$DST" | cut -d' ' -f1)
echo "repo     $a  $SRC"
echo "deployed $b  $DST"
if [ "$a" != "$b" ]; then echo "FAIL: md5 mismatch after copy"; exit 5; fi

echo "--- the keys that decide 4x + DLSS5 ---"
grep -nE '^(Enable|Provider|FrameGeneration|NeuralRenderingEnabled|DLSSGFramesToGenerate|MFGMaxFramesOverride|NRAllowWithFrameGen|NRRenderScale|RenderResolutionScale|MenuDisableFrameGen)=' "$DST" \
  || echo "(none matched - wrong file?)"

echo
echo "EXPECTED for '4x + DLSS5 together':"
echo "  Provider=1  FrameGeneration=1  NeuralRenderingEnabled=1"
echo "  MFGMaxFramesOverride=3  NRAllowWithFrameGen=1   <- 0 silently disables DLSS5"
