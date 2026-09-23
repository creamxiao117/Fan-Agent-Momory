# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-23（启动链与规则门禁分层瘦身 · 分支 `optimize/slim-rules-gates` · **交接给下一 Agent**）

## 当前状态快照

- 启动链曾 136K → **现测 17,173/30,000 PASS**（`cd hub-engine && python -m scripts.startup_budget` 退出码 0）。
- 方案：`docs/compose/specs/2026-09-23-slim-rules-gates-design.md`（S1–S5）；计划：`docs/compose/plans/2026-09-23-slim-rules-gates.md`。
- 分层：L0（AGENTS/CHARTER/WORK 当前态/根 INDEX 目录版）→ L1 四型（`hub-engine/tools/task_tier.py`）→ L2 检索。
- 安全底座常驻：单写者+§4 守护+ledger；query-first+交回用户+回写。
- 历史：`docs/superpowers/retro/work-history.md`；experience 索引：`AgentMemoryHub/INDEX-experience.md`（L2）。
- 实测分项：AGENTS 1426 / CHARTER 784 / WORK ~1451 / INDEX 13512。

## 每日巡检状态（cron，独立于本迭代）

- 2026-09-23：exit 2 —— 13 Lint（invalid 12 + schema_drift 1）**修复进行中**；快照已 commit 又被重跑更新，待补提交。明细见 RUNLOG R16。
- 工作区 `RUNLOG.md`/`WORK.md` 可能有巡检脏改动——**瘦身收口提交时勿误丢巡检段**，分笔提交。

## 活跃待办（本迭代）

| # | 任务 | 状态 |
| -- | --- | --- |
| A1 | startup_budget 门禁+单测 | 完成（1b709a0） |
| A2 | AGENTS 路由+CHARTER 压缩 | 完成（d3b8b3e+ca31e31） |
| A3 | WORK 当前态+历史归档 | 完成（db3d52e+33659c1） |
| A4 | INDEX 目录化+experience 拆分 | 完成（外层 da9f3c0 / 中枢 8556c53）；根 INDEX≤14K |
| A5 | rules tier+长卡拆分+inject 瘦身 | **代码/卡已提交未过双审**（外层 6884b9b / 中枢 f5eca53）；任务 T14 待 spec+quality review |
| B1 | backup+方法论合并+经验去重 | **未开始**（T15）；backup 已于 `.backup/20260923/` |
| 收口 | 预算 PASS + 全量 pytest + ruff + 挂巡检 | **未开始**（T16）；预算已 PASS，缺挂巡检与全量收口回写 |

## 已完成提交索引（外层 optimize/slim-rules-gates）

- 计划/spec：d3d633e, bc620e2, 40874f0, e7c05c6, 1315f55, 23e3b60
- T1–T6：1b709a0, ac132cc, fcfcffe, d3b8b3e, ca31e31, db3d52e, 33659c1, da9f3c0, 6884b9b
- 中枢仓 AgentMemoryHub：8556c53（INDEX 拆分）, f5eca53（rules tier+拆卡）

## 下一 Agent 必做（按序）

1. 读本文件 + spec + plan；确认分支 `optimize/slim-rules-gates`。
2. **补完 T14 双审**（compose:subagent 规格 Phase1 + 质量）：范围 = 外层 6884b9b + 中枢 f5eca53；已知实现事实见下「T14 交接」。
3. **T15 B1**：`python scripts/merge-methodology.py` + `deduplicate-experience.py`（同日已 backup）；INDEX 合并对齐再 slim；中枢单独 commit。
4. **T16 收口**：`startup_budget` 须仍 PASS；`patrol_runner` 挂 `startup_budget` 步（spec S3 挂巡检，plan Task8 Step0.5）；全量 pytest 无新增败（基线 4 败：test_engine status×3 + test_missing_query×1）；ruff 绿；回写本表状态。
5. 勿提交 `nul`；巡检脏文件单独处理。

## T14 交接（A5 实现事实）

- 备份：`AgentMemoryHub/.backup/20260923/manifest.txt`
- tier：iron 3 / task 29 / ref 3（appendix）
- 长卡核心 ≤2000：encoding 1303 / multi-lang 1058 / routing 1140；`*-appendix.md` 已建
- inject 新模板 L0+task_tier+检索；`test_inject` 6/6；ruff 绿
- `check_encoding.py` 加 appendix 卡名豁免（拆卡配套）
- 子代理 general-27 被 cancel；**未完成规格/质量评审**——接手后先审再标 T14 done

## 验收口径

- `python -m scripts.startup_budget` 退出码 0（**当前已满足**）
- 四文件字符：AGENTS≤3000 CHARTER≤3000 WORK≤9000 INDEX≤14000 总≤30000（**当前已满足**）
- `cd hub-engine && python -m pytest` 无**新增**失败；ruff 绿
- L0 六条铁律；INDEX 无长描述；改码型 L1 含编码核心卡名
- 挂巡检后 `rg startup_budget hub-engine/scripts/patrol_runner.py` 有匹配

## 上一轮遗留（须人工裁定，非本迭代引入）

见归档「待用户裁定」四修（vector_bench 夹具 / patrol fail-below / _norm_path CWD / RRF 保底）——本迭代不擅自改。

## 环境备忘

- 系统 python 跑 pytest/ruff（.venv 缺依赖会假绿）；LM Studio 1234 / embed 对齐 bge 配置以 config 为准。
- 基线全量 4 败非本迭代引入；`AgentMemoryHub` 为嵌套 git 且被外层 gitignore——中枢卡必须 `git -C AgentMemoryHub` 提交。
