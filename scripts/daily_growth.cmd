@echo off
REM AgentHub 每日成长：star-distill ingest + T1 迭代验证
REM 权威区 5 目录: rules/ blueprints/ methodology/ longterm/ projects/
REM T1 每日 3 张卡：reference 至少 1 + active 至少 1
cd /d D:\AIwork\20260817-Fan-Agent-Momory
C:\Users\Fan-SJSS\AppData\Local\Programs\Python\Python312\python.exe "D:\AIwork\20260817-Fan-Agent-Momory\scripts\daily_growth.py" >> "D:\AIwork\20260817-Fan-Agent-Momory\logs\daily_growth_%date:~0,4%-%date:~5,2%-%date:~8,2%.log" 2>&1