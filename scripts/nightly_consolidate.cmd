@echo off
rem == AgentHub nightly consolidation (distill -> build-vectors -> sleep -> local-summary) ==
rem -- ENCODING CONTRACT (rules/chinese-text-encoding-discipline) --------------
rem  Keep this file ANSI (pure ASCII) + CRLF. Pin BOTH ends:
rem    chcp 65001 here  +  PYTHONUTF8=1 / PYTHONIOENCODING=utf-8 for the child.
rem  Reason (fixed 2026-09-19): this .cmd echoes %date%/%time% (Chinese locale ->
rem  GBK weekday text) and forwards child stdout; both were emitted in the console
rem  code page (CP936) and appended into a UTF-8 log, so .sync\nightly.log could not
rem  be decoded by any single codec (460 bad lines verified).
rem
rem  2026-09-24 - MIGRATED INTO THE REPO (was D:\AIwork\traework\<hash>\scripts).
rem  Changes vs the old copy:
rem   1) paths are resolved from this script's location (the old copy hardcoded
rem      absolute worktree paths, so moving the worktree silently broke it)
rem   2) local_summary.py now lives in hub-engine/scripts (was outside version control)
rem   3) per-step exit codes are recorded in the log (the old copy swallowed them)
rem
rem  Exit code: propagates build-vectors failure ONLY. Rationale: a stale vector index
rem  silently degrades retrieval (that is exactly the P0 fixed on 2026-09-24), so it must
rem  fail loudly. distill (5 platforms) and local-summary are best-effort: their codes are
rem  logged but do not fail the task, matching prior behaviour.
rem ---------------------------------------------------------------------------
setlocal enabledelayedexpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem Resolve project root from this script location (no hardcoded absolute path).
for %%I in ("%~dp0..") do set "PROJ=%%~fI"
set "ROOT=%PROJ%\AgentMemoryHub"
set "ENGINE=%PROJ%\hub-engine"
set "PY=%PROJ%\.venv\Scripts\python.exe"
set "LOG=%ROOT%\.sync\nightly.log"

if not exist "%ROOT%\.sync" mkdir "%ROOT%\.sync"

if not exist "%PY%" (
  echo [%date% %time%] ERROR: venv python not found: %PY% >> "%LOG%"
  endlocal & exit /b 127
)

echo [%date% %time%] ==== night-consolidate start ==== >> "%LOG%"
cd /d "%ENGINE%"

echo [%date% %time%] -- 1/4 distill (5 platforms) -- >> "%LOG%"
for %%P in (code hermes ref trae workbuddy) do (
  echo [%date% %time%]    distill platform=%%P >> "%LOG%"
  "%PY%" engine.py distill --root "%ROOT%" --platform %%P >> "%LOG%" 2>&1
  echo [%date% %time%]    distill platform=%%P exit=!ERRORLEVEL! >> "%LOG%"
)

echo [%date% %time%] -- 2/4 build-vectors -- >> "%LOG%"
"%PY%" engine.py build-vectors --root "%ROOT%" >> "%LOG%" 2>&1
set "RC_VEC=%ERRORLEVEL%"
echo [%date% %time%]    build-vectors exit=%RC_VEC% >> "%LOG%"

echo [%date% %time%] -- 3/4 sleep-consolidate -- >> "%LOG%"
"%PY%" scripts\hub_sleep_consolidate.py --root "%ROOT%" --since-days 7 --max-candidates 5 >> "%LOG%" 2>&1
echo [%date% %time%]    sleep-consolidate exit=%ERRORLEVEL% >> "%LOG%"

echo [%date% %time%] -- 4/4 local-summary (in-repo since 2026-09-24) -- >> "%LOG%"
"%PY%" -m scripts.local_summary --root "%ROOT%" >> "%LOG%" 2>&1
echo [%date% %time%]    local-summary exit=%ERRORLEVEL% >> "%LOG%"

rem secret-sentry moved to the standalone daily task AgentHub-SecretSentry
rem (scripts\secret_sentry.cmd) so that distill/build-vectors stalls cannot block the scan.

echo [%date% %time%] ==== night-consolidate done (rc=%RC_VEC%) ==== >> "%LOG%"
endlocal & exit /b %RC_VEC%
