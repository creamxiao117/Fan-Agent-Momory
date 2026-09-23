# CHARTER.md

## 总目标

跨 Agent 平台统一记忆中枢：Hermes / trae / code / workbuddy 共享权威知识、行为一致。定位：中枢给 Agent 用、人监管。

## 架构（三层）

- `AgentMemoryHub/` —— 唯一事实源（Obsidian 纯内容）
- `hub-engine/` —— 同步/检索/提炼/整理/Lint/CLI/MCP
- 各平台 —— 经同步器对接：只读权威区、可写暂存、重要规则人工确认

## 能力（Phase 1–3 已完成，细节看历史归档）

写锁与错峰、commit ledger 审计、hub_announce、每日巡检+微信推送、ingest/confirm/distill/tidy/lint/retrieve/chat/sync。

## 维护者职责

1. 每日 patrol（lint/pytest/向量增量）
2. 任务收尾写经验卡 → ingest → sync
3. 改前查中枢；改后 ruff + pytest
4. commit 前 ledger + push（即 post_ingest_hook）

## 边界

做：中枢+核心能力、双平台并发安全、规则卡工作流、每日巡检。  
不做：平台全量复制、无人工提炼、复杂向量库、Web UI、跨 repo 原子事务。

## 关键约束

- 单一写入者锁；DLL 改后递增版本；Hub 内 git 审计
- 依赖尽量标准库（PyYAML/requests/mcp）
- `safe_patch` 为高风险改动唯一安全渠道
- type=rule 须 ingest 入区，不得直写

历史轮次与已完成细节：`docs/superpowers/retro/work-history.md`（按需读）。
