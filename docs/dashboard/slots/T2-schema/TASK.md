# T2 任务: 中枢总控台 JSON Schema（修正版 V2）

## 你的角色
你是 M2.7 子 Agent，由 M3 主 Agent 派发。
任务：写 6 大区的 JSON Schema 草案。

## 关键路径
- 本文件: `C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/work/dashboard/slots/T2-schema/TASK.md`
- 数据源（用绝对路径读）:
  - 平台元数据: `C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub/system/platforms.yaml`
  - 6 面板 JSON: `C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub/system/run/daily-6panel.json`
  - 平台 dashboard: `C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub/system/run/platform-dashboard.md`

## 6 大区
1. health: 综合评分（overall / card_health / skill_health / flywheel_activity / llm_health）
2. platforms: 6 平台状态（hermes/trae/code/workbuddy/dsh/mavis）
3. flywheel: 5 阶段统计（ingest/build-vectors/dedup/consolidate/lint）
4. knowledge_gap: 24h miss 统计（total/miss/miss_rate/top_misses）
5. todos: 待人工处理（T19/T21/pending rules/候选卡）
6. alerts: critical/error 告警列表

## 完成步骤
1. `read_file` 上面 3 个数据源文件（**3 个文件，约 5-10s**）
2. `write_file` schema.json 到 T2-schema 目录
3. `write_file` done.txt = "OK"
4. `write_file` result.txt 一句话总结

## Schema 格式
JSON Schema 2020-12 草案，6 个顶层 key 对应 6 大区，每个字段含 type/format/description。

## 关键禁止
- ❌ 不要 `find` 全盘
- ❌ 不要写超过 200 行 schema（这是草案，不是产品）

## 时间预算
30s 内完成。

完成直接报告。