@echo off
REM @version V1.0 / 2026-09-10 / Hermes / hub-engine working tree 守护扫描脚本（Windows 版）

setlocal enabledelayedexpansion

set THRESHOLD=3
set AUTO_STASH=false

REM 解析参数
:parse_args
if "%~1"=="" goto scan
if "%~1"=="--threshold" (
    set THRESHOLD=%~2
    shift
    shift
    goto parse_args
)
if "%~1"=="--auto-stash" (
    set AUTO_STASH=true
    shift
    goto parse_args
)

:scan
REM 扫描 modified
git status --short > %TEMP%\wt_scan.txt 2>nul
set MODIFIED=0
for /f %%i in ('type %TEMP%\wt_scan.txt ^| find /c /v ""') do set MODIFIED=%%i

set MTIME_DISTINCT=0

if !MODIFIED! GEQ !THRESHOLD! (
    set STATUS=ALARM
    set RECOMMENDATION=必须分析来源，commit/stash/reset 三选一
    set EXIT_CODE=1
) else (
    set STATUS=OK
    set RECOMMENDATION=working tree 干净
    set EXIT_CODE=0
)

echo { "status": "!STATUS!", "modified_count": !MODIFIED!, "threshold": !THRESHOLD!, "auto_stash_enabled": !AUTO_STASH!, "recommendation": "!RECOMMENDATION!" }

del %TEMP%\wt_scan.txt 2>nul
exit /b !EXIT_CODE!