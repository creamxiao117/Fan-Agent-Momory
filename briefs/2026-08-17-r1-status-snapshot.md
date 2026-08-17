# 简报 R1：`status` 一键健康快照子命令

- 日期：2026-08-17
- 状态：已完成

## 加什么

给 `hub-engine/engine.py` 新增 `status` 子命令：输入 `--root`，一键输出
卡片分布（各权威目录计数）、Lint 结果（孤儿/陈旧/无效）、待人工确认数、最近 Git 提交。

## 为什么现在

项目第一版已落地（45 测试 + 端到端走通）。跨会话接续时，下一轮 Agent 需要
10 秒内判断中枢健康状况，而不是手动拼多条命令。这正对 context-engineering-v1
"跨会话持续推进"的核心诉求，且成本极低（复用现有 `lint()`，仅加一层汇总）。

## 不加什么

- 不改造检索/同步/提炼等既有能力。
- 不做重型监控、定时任务、Web 界面。
- 不新增第三个"当前状态文件"（WORK.md 已是唯一状态源）。

## 怎么验证

1. `cd hub-engine && python -m pytest -q` 全量通过（新增 status 测试）。
2. `python hub-engine/engine.py status --root D:\AIwork\AgentMemoryHub` 输出可读快照。
