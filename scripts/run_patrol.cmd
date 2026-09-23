@echo off
rem == AgentHub daily patrol: lint / pytest / ruff / startup_budget / autofix ==
rem -- ENCODING CONTRACT (rules/chinese-text-encoding-discipline) -----------
rem  Keep this file ANSI (pure ASCII) + CRLF. Pin BOTH ends:
rem    chcp 65001 here  +  PYTHONUTF8=1 / PYTHONIOENCODING=utf-8 for the child.
rem
rem  2026-09-23 - Interpreter MUST be the .venv python.
rem  Reason: the system python lacks jieba, which silently SKIPS 9 retrieval
rem  and tokenizer tests. Verified: system python 393 passed / 13 skipped vs
rem  .venv python 402 passed / 4 skipped. Using the wrong one yields a
rem  falsely-green patrol ("jia-lv") and hides real coverage.
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
set "LOG=%ROOT%\.sync\patrol.log"

if not exist "%ROOT%\.sync" mkdir "%ROOT%\.sync"

if not exist "%PY%" (
  echo [%date% %time%] ERROR: venv python not found: %PY% >> "%LOG%"
  endlocal & exit /b 127
)

echo [%date% %time%] ==== patrol start ==== >> "%LOG%"
cd /d "%ENGINE%"
"%PY%" -m scripts.patrol_runner --root "%ROOT%" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo [%date% %time%] ==== patrol done (exit %RC%) ==== >> "%LOG%"
endlocal & exit /b %RC%
