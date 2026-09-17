#!/usr/bin/env python3
"""Incremental build for DynamicShaderFrameGen with the MSVC environment injected
by hand.

Why not VsDevCmd.bat: it shells out to reg.exe to locate the SDK, and both shells
in this environment refuse to launch cmd.exe / reg.exe. The compiler paths are
already recorded in build/NINJA/CMakeCache.txt, so we read them and set
INCLUDE / LIB / PATH ourselves, then call cmake directly.

Success is judged by artifact size + md5, NOT by stdout - ninja can rebuild and
relink with completely empty output.
"""
import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build", "NINJA")
TARGET = "DynamicShaderFrameGen.dll"
DEPLOY = r"E:\EJ\mod\mods\DynamicShaderFrameGen\SKSE\Plugins\DynamicShaderFrameGen.dll"

MSVC = r"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\14.50.35717"
SDK = r"C:\Program Files (x86)\Windows Kits\10"
SDKV = "10.0.26100.0"
CMAKE = r"C:\Program Files\CMake\bin\cmake.exe"
NINJA_DIR = r"E:\vcpkg-full\downloads\tools\ninja-1.13.2-windows"


def fingerprint(path):
    if not os.path.exists(path):
        return "(missing)"
    with open(path, "rb") as fh:
        data = fh.read()
    return "{} bytes  md5={}".format(len(data), hashlib.md5(data).hexdigest())


def main():
    env = dict(os.environ)
    sdk_inc = SDK + "\\Include\\" + SDKV
    sdk_lib = SDK + "\\Lib\\" + SDKV
    sdk_bin = SDK + "\\bin\\" + SDKV

    env["INCLUDE"] = ";".join([
        MSVC + r"\include",
        sdk_inc + r"\ucrt",
        sdk_inc + r"\um",
        sdk_inc + r"\shared",
        sdk_inc + r"\winrt",
    ])
    env["LIB"] = ";".join([
        MSVC + r"\lib\x64",
        sdk_lib + r"\ucrt\x64",
        sdk_lib + r"\um\x64",
    ])
    env["PATH"] = ";".join([
        MSVC + r"\bin\Hostx64\x64",
        sdk_bin + r"\x64",
        os.path.dirname(CMAKE),
        NINJA_DIR,
        env.get("PATH", ""),
    ])
    for probe in (sdk_inc + r"\ucrt\crtdbg.h", MSVC + r"\include\algorithm"):
        print("probe {}: {}".format(probe, "OK" if os.path.exists(probe) else "MISSING"))

    built = os.path.join(BUILD, TARGET)
    before_build = fingerprint(built)
    before_deploy = fingerprint(DEPLOY)
    print("BEFORE build :", before_build)
    print("BEFORE deploy:", before_deploy)

    proc = subprocess.run([CMAKE, "--build", BUILD, "-j", "4"],
                          env=env, capture_output=True)
    # MSVC emits messages in the system ANSI codepage (GBK here), so decoding as
    # UTF-8 raises part-way through and we lose the whole log. Read bytes and
    # decode defensively.
    raw = (proc.stdout or b"") + (proc.stderr or b"")
    try:
        out = raw.decode("utf-8")
    except UnicodeDecodeError:
        out = raw.decode("gbk", errors="replace")
    lines = out.strip().splitlines()
    print("---- build output (tail 40) ----")
    print("\n".join(lines[-40:]) if lines else "(empty stdout - normal for ninja)")
    print("exit code:", proc.returncode)

    after_build = fingerprint(built)
    after_deploy = fingerprint(DEPLOY)
    print("AFTER build :", after_build)
    print("AFTER deploy:", after_deploy)

    if not lines:
        print("NOTE: stdout was empty; judge success by the md5/size above and "
              "by build/NINJA/.ninja_log")
    relinked = before_build != after_build
    print("RESULT:", "RELINKED" if relinked else "NOT RELINKED (no artifact change)")
    if relinked and after_build != after_deploy:
        print("NOTE: POST_BUILD deploy did not match - check PLUGIN_DEPLOY_DIR")
    return 0


if __name__ == "__main__":
    sys.exit(main())
