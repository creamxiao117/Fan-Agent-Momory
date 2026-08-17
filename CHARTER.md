# CHARTER.md

## 总目标

建成"跨 Agent 平台统一记忆中枢"：让 trae / code 等平台的 Agent 共享同一份权威知识、集中沉淀、行为一致、正向迭代。

## 架构

三层分工：

- `C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub` —— 唯一事实源（Obsidian 库，纯内容）。
- 本仓库 `hub-engine/` —— 全部能力：单一写入者同步器、确定性+语义混合检索、复盘提炼、整理归档、Lint 健康检查、omniroute 问答、CLI 统一入口。
- 各平台 —— 经同步器对接中枢：只读权威区、可写暂存区、重要规则人工确认。

## 边界（第一版范围）

做：中枢骨架 + 7 项核心能力（ingest/confirm/distill/tidy/lint/retrieve/chat + sync 同步器）+ trae 指令注入 + 一条真实 DLL 规则端到端走通。

不做：平台全量接入、无人工提炼、复杂向量库、定时 Lint、Web 界面。

## 关键约束

- 单一写入者（`.sync/locks/writer.lock`），防并发冲突。
- 修改 DLL 后必须递增版本号（防 AutoCAD 锁文件）。
- Git 在 Hub 内做审计/回滚。
- 依赖尽量标准库，仅 PyYAML + requests。
