"""Incremental build for DynamicShaderFrameGen without reg.exe / vcvars.

Why this exists:
  build_vs.bat pins the MSVC + Windows SDK paths by hand because reg.exe is
  blocked in this sandbox, so calling vcvars64.bat leaves INCLUDE/LIB empty
  and every translation unit dies with
      fatal error C1083: cannot open include file: 'algorithm'
  Running cmake --build directly (bypassing the .bat) reproduces that failure
  exactly. This script sets the same environment the .bat sets, then invokes
  ninja itself, so the two agree without shelling out to cmd.exe.

Usage:
  python tools/build_via_python.py           # incremental
  python tools/build_via_python.py --clean   # wipe build/NINJA first
  python tools/build_via_python.py --verify  # report artifact md5 + size
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "NINJA"

MSVC = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools"
            r"\VC\Tools\MSVC\14.50.35717")
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10")
SDKVER = "10.0.26100.0"

# Deployment artefacts worth printing after a build.
DEPLOY_DLL = Path(r"E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins"
                  r"\DynamicShaderFrameGen.dll")


def build_env() -> dict:
    env = dict(os.environ)
    inc = [
        str(MSVC / "include"),
        str(SDK / "Include" / SDKVER / "ucrt"),
        str(SDK / "Include" / SDKVER / "shared"),
        str(SDK / "Include" / SDKVER / "um"),
        str(SDK / "Include" / SDKVER / "winrt"),
    ]
    lib = [
        str(MSVC / "lib" / "x64"),
        str(SDK / "Lib" / SDKVER / "ucrt" / "x64"),
        str(SDK / "Lib" / SDKVER / "um" / "x64"),
    ]
    # NOTE: deliberately no <SDK>\cppwinrt -- the project uses vcpkg's
    # C++/WinRT and mixing the two trips static_assert("Mismatched headers").
    env["INCLUDE"] = ";".join(inc)
    env["LIB"] = ";".join(lib)
    env["PATH"] = str(MSVC / "bin" / "Hostx64" / "x64") + ";" + env.get("PATH", "")
    return env


def which_ninja(env: dict) -> str:
    n = shutil.which("ninja", path=env.get("PATH"))
    if n:
        return n
    # CMake ships one with VS; also check the usual CMake install
    for cand in (
        Path(r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools"
             r"\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"),
        Path(r"D:\Modding\DynamicShaderFrameGen\build\ninja\ninja.exe"),
    ):
        if cand.is_file():
            return str(cand)
    return "ninja"


def md5_of(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--target", default="DynamicShaderFrameGen")
    args = ap.parse_args()

    # sanity: toolchain present?
    cl = MSVC / "bin" / "Hostx64" / "x64" / "cl.exe"
    if not cl.is_file():
        print(f"[FATAL] cl.exe missing: {cl}")
        return 1
    sdk_hdr = SDK / "Include" / SDKVER / "ucrt" / "stddef.h"
    if not sdk_hdr.is_file():
        print(f"[FATAL] SDK headers missing: {sdk_hdr}")
        return 1

    if args.clean and BUILD.is_dir():
        print(f"[CLEAN] removing {BUILD}")
        shutil.rmtree(BUILD, ignore_errors=True)

    if not (BUILD / "build.ninja").is_file():
        print(f"[FATAL] {BUILD}\\build.ninja not found - configure first")
        return 1

    env = build_env()
    ninja = which_ninja(env)
    print(f"[BUILD] {BUILD}")
    print(f"[TOOL]  {ninja}")
    proc = subprocess.run([ninja, args.target], cwd=str(BUILD), env=env,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-8000:] if len(out) > 8000 else out)
    if proc.returncode != 0:
        print(f"[FAIL] ninja exit={proc.returncode}")
        return proc.returncode
    print("[OK] build succeeded")

    if args.verify:
        dll = BUILD / f"{args.target}.dll"
        if dll.is_file():
            print(f"[ART ] build   {dll}  {dll.stat().st_size} B  "
                  f"md5={md5_of(dll)}")
        if DEPLOY_DLL.is_file():
            print(f"[ART ] deploy  {DEPLOY_DLL}  {DEPLOY_DLL.stat().st_size} B  "
                  f"md5={md5_of(DEPLOY_DLL)}")
            if dll.is_file():
                same = md5_of(dll) == md5_of(DEPLOY_DLL)
                print(f"[ART ] identical={same}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
