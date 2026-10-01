rem @status: retired
rem @retired_at: 2026-10-01
rem @original_path: scripts/daily_growth.cmd
rem @superseded_by: scripts/nightly_consolidate.cmd + Hermes 晨间链
rem @reason: 同 daily_growth.py：硬编码 D:\AIwork\... 路径与系统 python（本 worktree 下必然失败）
rem @retired_from_commit: a7e941b
rem @restore: git checkout a7e941b -- scripts/daily_growth.cmd && git mv scripts/daily_growth.cmd scripts/daily_growth.cmd

@echo off
REM AgentHub 每日成长：star-distill ingest + T1 迭代验证
REM 权威区 5 目录: rules/ blueprints/ methodology/ longterm/ projects/
REM T1 每日 3 张卡：reference 至少 1 + active 至少 1
cd /d D:\AIwork\20260817-Fan-Agent-Momory
C:\Users\Fan-SJSS\AppData\Local\Programs\Python\Python312\python.exe "D:\AIwork\20260817-Fan-Agent-Momory\scripts\daily_growth.py" >> "D:\AIwork\20260817-Fan-Agent-Momory\logs\daily_growth_%date:~0,4%-%date:~5,2%-%date:~8,2%.log" 2>&1