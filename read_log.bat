@echo off
REM Print the verdict for the most recent DynamicShaderFrameGen run.
REM
REM Reads the [XRAY] instrumentation (v0.61) out of the plugin log and states
REM what the run proved - which dll loaded, which ini won, whether the display
REM mode and swapchain agree, whether constants were rejected, whether the menu
REM was throttled, and what the real per-frame multiplier was.
REM
REM Usage:  read_log.bat
REM         read_log.bat <other log path>
setlocal
set "PY=C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" echo [FAIL] python not found: %PY% & exit /b 1
"%PY%" "D:\Modding\DynamicShaderFrameGen\tools\read_xray_log.py" %*
endlocal
