# AGENTS.md

跨 Agent 平台统一记忆中枢 · 薄路由入口。细节不常驻，按任务型取 L1/L2。

## 启动顺序（L0，计入 30K 预算）

1. 本文件（路由 + 铁律）
2. `CHARTER.md` —— 目标与边界
3. `WORK.md` —— **仅当前状态/待办**（历史见 `docs/superpowers/retro/work-history.md`）
4. `AgentMemoryHub/INDEX.md` —— **目录版**（卡名+一行摘要；全文走检索）
5. 简报 `briefs/*.md` 若有

不依赖历史聊天；事实来源=WORK 当前态 + 中枢。

## L0 铁律（安全底座，永不裁剪）

- 单一写入者（`AgentMemoryHub/.sync/locks/writer.lock`）+ 工作区守护（≥3 modified 须分析）+ ledger 审计
- 执行前先查中枢（INDEX/`engine.py retrieve`/MCP hub_bootstrap），命中再执行
- 不确定交回用户，不臆测、不捏造历史经验
- 查询结果回写经验卡（ingest/回写纪律）

## 任务分型 → L1 卡（代码口径 `hub-engine/tools/task_tier.py` 的 `L1_CARDS`）

| 型 | 判定（关键词兜底，判不出=light） | L1 规则卡（只读核心节/全文按需） |
| --- | --- | --- |
| light | 默认、问答、查状态 | （无，仅 L0） |
| code | commit/ruff/pytest/patch/PR/改代码 | chinese-text-encoding-discipline · agent-code-discipline-iron-rule · multi-language-style-config |
| hub | 中枢/ingest/rules/experience/回写 | dual-platform-coherence-discipline · global-rules · memory-hub-distill-last |
| sync | sync/push/注入/跨平台 | cross-platform-sync-rule · dual-platform-coherence-discipline |

升型廉价：动作变重再补读 L1；只升不降。完整关键词见 `hub-engine/tools/task_tier.py`。

## 降级

检索不可用 → 按上表卡名直读 `AgentMemoryHub/rules/<卡名>.md`；仍失败则问用户。

## 事实来源映射

| 内容 | 位置 |
| --- | --- |
| 设计/计划 | `docs/superpowers/specs/ 与 plans/`；瘦身设计 `docs/compose/specs/2026-09-23-slim-rules-gates-design.md` |
| 引擎 | `hub-engine/`（`engine.py`） |
| 中枢唯一事实源 | `AgentMemoryHub/` |
| 缺工具/写码 | 主动找装；中文注释；ruff 规范 |
