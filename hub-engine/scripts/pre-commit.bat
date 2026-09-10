@echo off
REM @version V1.0 / 2026-09-10 / Hermes / hub-engine pre-commit ruff 门禁钩子（Windows 版）
REM
REM 作用：pre-commit 时跑 ruff check + ruff format --check，不通过则阻断 commit
REM 安装：复制此文件到 .git/hooks/pre-commit
REM
REM 退出码：
REM   0 = 通过
REM   1 = 阻断（ruff check 报错）
REM   2 = 阻断（ruff format 不一致）

setlocal enabledelayedexpansion

echo [pre-commit] hub-engine ruff 门禁启动（Windows）...

REM 检测 .py 文件
set STAGED_PY=
for /f "delims=" %%i in ('git diff --cached --name-only --diff-filter=ACM ^| findstr /r "\.py$"') do (
    set STAGED_PY=!STAGED_PY! %%i
)

if "!STAGED_PY!"=="" (
    echo [pre-commit] 无 .py 文件 staged，跳过
    exit /b 0
)

echo [pre-commit] 检测到 .py staged 文件:!STAGED_PY!

REM 1. ruff check
echo [pre-commit] 跑 ruff check...
ruff check --fix !STAGED_PY!
if errorlevel 1 (
    echo [pre-commit] X ruff check 未通过，commit 阻断
    exit /b 1
)

REM 2. ruff format --check
echo [pre-commit] 跑 ruff format --check...
ruff format --check !STAGED_PY!
if errorlevel 1 (
    echo [pre-commit] X ruff format --check 不一致，commit 阻断
    exit /b 2
)

echo [pre-commit] + ruff 门禁通过
exit /b 0