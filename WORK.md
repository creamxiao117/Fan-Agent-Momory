# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-23 · 迭代 T14–T16 已完成并**已合并到 master**（分支已删）

> 历史轮次/过程明细：`docs/superpowers/retro/work-history.md`
> T1 完整基线：`docs/compose/metrics/2026-09-23-t1-baseline.md`（本文件只留当前态 + 活跃待办）

## 当前状态

- 启动链曾 136K → **现测 22,805/30,000 PASS**（`cd hub-engine && .venv\Scripts\python.exe -m scripts.startup_budget`）
- 分层：L0（AGENTS / CHARTER / **本文件** / 根 INDEX 目录版）→ L1 四型（`tools/task_tier.py`）→ L2 检索
- 安全底座常驻：单写者+§4 守护+ledger；query-first + 交回用户 + 回写
- 方案 `docs/compose/specs/2026-09-23-slim-rules-gates-design.md`；计划 `docs/compose/plans/2026-09-23-slim-rules-gates.md`
- 分项帽：AGENTS≤2500 / CHARTER≤1500 / WORK≤5000 / INDEX≤20000（和 29,000 ≤ 总帽 30,000；不变量有测试看守）

## 活跃待办

| # | 任务 | 触发 / 做法 |
| -- | --- | --- |
| **T1** | **量「规则遵循/返工」改造前后**——唯一需要真实时间的一条 | **重跑 ≥2026-10-07**：`python -m scripts.rule_following_timeseries`。判据 3 条见下 |
| T2 | 复核 INDEX 可定位性 | `python -m scripts.index_locatability_bench --rev 68088fa^`（当前 18/20、覆盖 42.5%）。**关键词代理，不衡量语义理解** |
| T3 | 上一轮遗留「待用户裁定」四项 | vector_bench 夹具 / patrol fail-below / `_norm_path` CWD / RRF 保底——非本迭代引入 |
| T4 | ~~两工具是否再合并~~ | **已裁定：保持分开**（理由+推翻条件见 `scripts/index_consistency.py` 头部） |

### T1 首轮结果（2026-09-23，**结论：未成立**）

- **门禁**：改造前 17 个有数据的天中 **5 天** `invalid>0`（最大 21）；后窗口 **2 天全 0**。
- **产出**（ingest 流水账，定义未变）：W35→W38 提交量稳定 ~35/周，但**新知识产出率 41%→11%**、重复率 59%→89%。
- **根因已定性**：W38 冲突中 **61% 是真重复**（LLM `merge`）、**误杀为 0** ⇒ 属**真漂移，非判重误杀**；11 个卡名被反复提交（两卡各 4 次）。
- ⚠️ 可比性缺口：lint 报告两种格式（09-08 起新增 `long_desc` 等维度）⇒ **跨格式不可直接比大小**。

**重跑判据（可证伪）**：
1. 门禁：后窗口 **≥10 天**且 `invalid/orphans/ghosts` 全 0 → 正面
2. 产出：周产出率 **≥40%** 且重复率 **≤60%** → 流入恢复
3. 反面：任一维度复现非零 / 产出率仍 **≤11%** → **未触及根因，须重新诊断**

> 完整表格、数据源性质、可比性细节：`docs/compose/metrics/2026-09-23-t1-baseline.md`

## 门禁（都必须在跑，不只是"代码里有"）

- **提交时**（`.git/hooks/pre-commit` V1.2，源 `hub-engine/scripts/pre-commit`）：编码 → **预算** → ruff；退出码 1/2/4/5
- **每日 07:30** 定时任务 `AgentHub-DailyPatrol` → `scripts/run_patrol.cmd` → `patrol_runner`（lint / pytest / ruff / startup_budget / autofix）
- 验收：`.venv\Scripts\python.exe -m pytest` → **444 通过 / 4 跳过 / 0 失败**；`startup_budget` 退出码 0

## 禁止 / 注意

- **勿执行** `scripts/merge-methodology.py`、`scripts/deduplicate-experience.py`——已加拒绝护栏（实测会截断内容 / 误杀互补卡）
- **解释器必须用 `.venv\Scripts\python.exe`**：系统 python 缺 jieba，会让 9 个检索/分词测试**静默跳过**（假绿）
- 中枢卡提交须 `git -C AgentMemoryHub`（嵌套 git，外层已 gitignore）；巡检脏文件单独分笔提交
- embed 配置以 `AgentMemoryHub/system/config.yaml` 为准（生效单源；`hub-engine/config/engine.config.yaml` 仅兜底）
- **外层超时必须 > 内层超时**（`patrol_runner` 的 pytest 步骤外层 420s / 内层 180s；曾因外层 120s < 内层导致内层永不生效）
- 勿提交 `nul`（已清除的幽灵条目）
