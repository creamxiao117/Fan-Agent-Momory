# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-23（启动链与规则门禁分层瘦身 · 分支 `optimize/slim-rules-gates`）

## 当前状态快照

- 启动链实测曾达 136K 字符；本迭代目标四件套 **≤30K**（门禁 `hub-engine/scripts/startup_budget.py`）。
- 方案：`docs/compose/specs/2026-09-23-slim-rules-gates-design.md`（S1–S5）。
- 计划：`docs/compose/plans/2026-09-23-slim-rules-gates.md`。
- 分层：L0 常驻（AGENTS/CHARTER/WORK 当前态/INDEX 目录版）→ L1 按四型（light/code/hub/sync）→ L2 检索。
- 安全底座常驻：单写者+§4 守护+ledger；query-first+交回用户+回写。
- 历史轮次：`docs/superpowers/retro/work-history.md`。
- 本迭代进度：A1 budget 门禁已立（真机仍超标属预期）；A2 AGENTS/CHARTER 已压至 ≤3K；A3 本任务。

## 活跃待办（本迭代）

| # | 任务 | 状态 |
| -- | --- | --- |
| A1 | startup_budget 门禁+单测 | 完成（真机待 A4 后 PASS） |
| A2 | AGENTS 路由+CHARTER 压缩 | 完成 |
| A3 | WORK 当前态+历史归档 | 本任务 |
| A4 | INDEX 目录化 | 按计划 |
| A5 | rules tier+长卡拆分+inject 瘦身 | 按计划 |
| B1 | backup+方法论合并+经验去重 | 按计划 |
| 收口 | 预算 PASS + 全量 pytest + ruff + 挂巡检 | 按计划 |

## 验收口径

- `python -m scripts.startup_budget` 退出码 0
- 四文件字符：AGENTS≤3000 CHARTER≤3000 WORK≤9000 INDEX≤14000 总≤30000
- `cd hub-engine && python -m pytest` 无**新增**失败（基线既有 4 败见归档/环境）；ruff 绿
- L0 可见六条铁律；INDEX 无长描述正文；改码型 L1 含编码核心卡名

## 上一轮遗留（须人工裁定，非本迭代引入）

见归档「待用户裁定」四修（vector_bench 夹具 / patrol fail-below / _norm_path CWD / RRF 保底）——本迭代不擅自改。

## 环境备忘

- 系统 python 跑 pytest/ruff（.venv 缺依赖会假绿）；LM Studio 1234 / embed 对齐 bge 配置以 config 为准。
