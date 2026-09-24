@echo off
rem == AgentHub secret sentry: daily credential-leak scan of the hub ==
rem -- ENCODING CONTRACT (rules/chinese-text-encoding-discipline) -----------
rem  Keep this file ANSI (pure ASCII) + CRLF. Pin BOTH ends:
rem    chcp 65001 here  +  PYTHONUTF8=1 / PYTHONIOENCODING=utf-8 for the child.
rem
rem  2026-09-24 - MIGRATED INTO THE REPO (was D:\AIwork\traework\<hash>\scripts).
rem  Reason: the old copy lived OUTSIDE version control, and its patterns had
rem  three by-construction false positives (sk-key without \b, authorization
rem  matching only the field name, api-key-field accepting provider labels).
rem  Result: 26 "high" findings per night, 6/6 sampled were false, task stuck
rem  at exit 2 forever -> alert fatigue. Now precise: real findings only.
rem
rem  2026-09-24 - Interpreter MUST be the .venv python (same reason as patrol:
rem  the system python lacks jieba and silently changes test coverage).
rem -------------------------------------------------------------------------
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem Resolve project root from this script location (no hardcoded absolute path).
for %%I in ("%~dp0..") do set "PROJ=%%~fI"
set "ROOT=%PROJ%\AgentMemoryHub"
set "ENGINE=%PROJ%\hub-engine"
set "PY=%PROJ%\.venv\Scripts\python.exe"
set "LOG=%ROOT%\.sync\secret_sentry.log"

if not exist "%ROOT%\.sync" mkdir "%ROOT%\.sync"

if not exist "%PY%" (
  echo [%date% %time%] ERROR: venv python not found: %PY% >> "%LOG%"
  endlocal & exit /b 127
)

echo [%date% %time%] ==== secret-sentry start ==== >> "%LOG%"
cd /d "%ENGINE%"
"%PY%" -m scripts.secret_sentry --root "%ROOT%" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo [%date% %time%] ==== secret-sentry done (exit %RC%) ==== >> "%LOG%"
endlocal & exit /b %RC%
