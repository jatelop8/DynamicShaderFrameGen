@echo off
REM Build DynamicShaderFrameGen (x64) with NO registry lookups.
REM
REM Why this does not call vcvars64.bat / VsDevCmd.bat:
REM   they shell out to reg.exe to locate the Windows SDK. That program is on the
REM   sandbox program blacklist, so INCLUDE/LIB stay empty and every TU dies with
REM   yvals.h(NN): fatal error C1083: cannot open "crtdbg.h".
REM   Toolchain paths are pinned below instead - deterministic, no registry.
REM
REM Two rules learned the hard way:
REM   * never add <SDK>\cppwinrt to INCLUDE - the project uses vcpkg's C++/WinRT and
REM     mixing the two versions trips static_assert("Mismatched C++/WinRT headers")
REM   * paths echoed inside any paren block must be quoted, or "(x86)" breaks cmd
REM
REM If MSVC / the Windows SDK is updated, bump MSVCVER / SDKVER.
REM Usage:  build_vs.bat  |  build_vs.bat --clean
setlocal
set "MSVCVER=14.50.35717"
set "SDKVER=10.0.26100.0"
set "MSVC=C:/Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Tools\MSVC\%MSVCVER%"
set "SDK=C:/Program Files (x86)\Windows Kits\10"
if not exist "%MSVC%\bin\Hostx64\x64\cl.exe" echo [FAIL] cl.exe missing: "%MSVC%\bin\Hostx64\x64\cl.exe"
if not exist "%MSVC%\bin\Hostx64\x64\cl.exe" exit /b 1
if not exist "%SDK%\Include\%SDKVER%\ucrt\stddef.h" echo [FAIL] SDK headers missing: "%SDK%\Include\%SDKVER%\ucrt\stddef.h"
if not exist "%SDK%\Include\%SDKVER%\ucrt\stddef.h" exit /b 1
set "INCLUDE=%MSVC%\include;%SDK%\Include\%SDKVER%\ucrt;%SDK%\Include\%SDKVER%\shared;%SDK%\Include\%SDKVER%\um;%SDK%\Include\%SDKVER%\winrt"
set "LIB=%MSVC%\lib\x64;%SDK%\Lib\%SDKVER%\ucrt\x64;%SDK%\Lib\%SDKVER%\um\x64"
set "PATH=%MSVC%\bin\Hostx64\x64;%PATH%"
set "BUILD=D:/Modding/DynamicShaderFrameGen/build/NINJA"
if /I "%~1"=="--clean" rmdir /s /q "%BUILD%"
cd /d "%BUILD%"
if errorlevel 1 exit /b 1
cmake --build .
if errorlevel 1 echo [FAIL] build failed
if errorlevel 1 exit /b 1
echo BUILD SUCCESS: %BUILD%\DynamicShaderFrameGen.dll
exit /b 0
