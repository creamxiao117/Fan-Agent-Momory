# CHARTER.md

## 总目标

建成"跨 Agent 平台统一记忆中枢"：让 Hermes / trae work / code / workbuddy 等平台的 Agent 共享同一份权威知识、集中沉淀、行为一致、正向迭代。

**定位**：记忆中枢给 Agent 用、人只监管（Fan 2026-08 确认）。

---

## 架构

三层分工：

- `C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub` —— 唯一事实源（Obsidian 库，纯内容）。
- 本仓库 `hub-engine/` —— 全部能力：单一写入者同步器、确定性+语义混合检索、复盘提炼、整理归档、Lint 健康检查、omniroute 问答、CLI 统一入口。
- 各平台 —— 经同步器对接中枢：只读权威区、可写暂存区、重要规则人工确认。

---

## 已完成能力（Phase 1-3）

### Phase 1：并发安全

- `_WriteLock` PID+mtime 僵尸检测 + 指数退避 3 次（commit `da23db7` + `f1661f9`）
- `schedule.toml` 双平台写时段错峰（commit `ace7acd`）

### Phase 2：审计追溯

- `commit_ledger.jsonl` 每次 git commit 前登记 who/intent/sha/parent（commit `9866d0c`）
- `reconcile.py` 孤儿 commit 检测（E2E 验证：orphans: 0）

### Phase 3：跨平台通信

- `hub_announce` MCP 工具 → `announcements.jsonl`（commit `9763c39`）
- `flywheel_daily_report.py` 每日 8:00 推送微信（cron 已配置）

---

## 维护者职责

1. **每日**：patrol_runner.py 健康巡检（lint / pytest / 向量增量）
2. **收尾**：任务完成后必须写经验卡 → ingest → sync 同步 4 平台
3. **改前**：查 `rules/memory-hub-query-first`，改后：ruff check + pytest
4. **commit 前**：ledger 登记 + 同步推送（`git push` 即触发 post_ingest_hook）
5. **双平台并发**：遵守 `schedule.toml` 写时段；_WriteLock 自动兜底僵尸锁

---

## 边界

做：
- 中枢骨架 + 7 项核心能力（ingest/confirm/distill/tidy/lint/retrieve/chat + sync 同步器）
- 双平台并发安全（写锁 + 审计 ledger + 跨平台通知）
- 规则卡驱动的工作流自律（铁律规则 + safe_patch）
- 每日自动巡检 + 微信推送

不做：
- 平台全量接入（各平台仅对接，非全功能复制）
- 无人工提炼（全量经验须经 ingest 审查）
- 复杂向量库（SQLite + BM25 + bge-small-zh 向量，够用即可）
- Web 界面（CLI 优先）
- 跨 repo 原子事务（AgentMemoryHub 与 Fan-Agent-Momory 是独立 git repo）

---

## 关键约束

- 单一写入者（`.sync/locks/writer.lock`），防并发冲突；_WriteLock 含 PID+mtime 僵尸检测。
- 修改 DLL 后必须递增版本号（防 AutoCAD 锁文件）。
- Git 在 Hub 内做审计/回滚；commit_ledger.jsonl 记录所有写操作。
- 依赖尽量标准库，仅 PyYAML + requests + mcp（1.29+）。
- `safe_patch.py` 是高风险改动的唯一安全渠道（Hernes 原生 patch 已废弃）。
- 所有规则卡（type=rule）必须经过 `ingest` 再入权威区，不得直写。
