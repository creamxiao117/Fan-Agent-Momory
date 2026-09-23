# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-23 · 分支 `optimize/slim-rules-gates` · 迭代 T14–T16 已完成，**待用户验收**

> 历史轮次与过程明细：`docs/superpowers/retro/work-history.md`（本文件只留当前态 + 活跃待办）

## 当前状态

- 启动链曾 136K → **现测 25,020/30,000 PASS**（`cd hub-engine && .venv\Scripts\python.exe -m scripts.startup_budget`）
- 分层：L0（AGENTS / CHARTER / **本文件** / 根 INDEX 目录版）→ L1 四型（`tools/task_tier.py`）→ L2 检索
- 安全底座常驻：单写者+§4 守护+ledger；query-first + 交回用户 + 回写
- 方案 `docs/compose/specs/2026-09-23-slim-rules-gates-design.md`；计划 `docs/compose/plans/2026-09-23-slim-rules-gates.md`
- 分项帽：AGENTS≤2500 / CHARTER≤1500 / WORK≤5000 / INDEX≤20000（和 29,000 ≤ 总帽 30,000；不变量有测试看守）

## 活跃待办

| # | 任务 | 触发 / 做法 |
| -- | --- | --- |
| **T1** | **量「规则遵循/返工」改造前后**——唯一需要真实时间的一条 | **≥2026-10-07** 跑 `python -m scripts.rule_following_timeseries --csv`，对比改造前基线：`lint_invalid` 均值 2.38 / 最大 21、`orphans` 非零 7 天；改造后窗口现为 **0**（改造日=今天，数据未积累）。取 ≥2–4 周再下结论 |
| T2 | 复核 INDEX 可定位性 | `python -m scripts.index_locatability_bench --rev 68088fa^` —— 当前 18/20 可定位、覆盖 42.5%（改造前 17/20、36.5%）。**该指标是关键词代理，不衡量语义理解** |
| T3 | 上一轮遗留「待用户裁定」四项 | vector_bench 夹具 / patrol fail-below / `_norm_path` CWD / RRF 保底——非本迭代引入，须人工裁定 |
| T4 | 幽灵 vs 未登记两工具是否再合并 | 共享契约已收敛到 `scripts/index_consistency.py`；两者方向不同（INDEX 有/文件无 ↔ 文件有/INDEX 无），**暂分** |

## 门禁（都必须在跑，不只是"代码里有"）

- **提交时**（`.git/hooks/pre-commit` V1.2，源 `hub-engine/scripts/pre-commit`）：编码 → **预算** → ruff；退出码 1/2/4/5
- **每日 07:30** 定时任务 `AgentHub-DailyPatrol` → `scripts/run_patrol.cmd` → `patrol_runner`（lint / pytest / ruff / startup_budget / autofix）
- 验收：`.venv\Scripts\python.exe -m pytest` → **416 通过 / 4 跳过 / 0 失败**；`startup_budget` 退出码 0

## 禁止 / 注意

- **勿执行** `scripts/merge-methodology.py`、`scripts/deduplicate-experience.py`——已加拒绝护栏（实测会截断内容 / 误杀互补卡）
- **解释器必须用 `.venv\Scripts\python.exe`**：系统 python 缺 jieba，会让 9 个检索/分词测试**静默跳过**（假绿）
- 中枢卡提交须 `git -C AgentMemoryHub`（嵌套 git，外层已 gitignore）；巡检脏文件（`RUNLOG.md`、`retro/snapshot-*.json`）单独分笔提交
- embed 配置以 `AgentMemoryHub/system/config.yaml` 为准（生效单源；`hub-engine/config/engine.config.yaml` 仅兜底，改它看不到效果）
- 勿提交 `nul`（已清除的幽灵条目）
