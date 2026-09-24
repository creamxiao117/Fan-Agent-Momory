# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-24 · 迭代 T14–T16 已完成并**已合并到 master**（分支已删）；审计 + 清理 + T3 已收口

> 历史轮次/过程明细：`docs/superpowers/retro/work-history.md`
> T1 完整基线：`docs/compose/metrics/2026-09-23-t1-baseline.md`；清理留档：`docs/compose/cleanup/`（本文件只留当前态 + 活跃待办）

## 当前状态

- 启动链曾 136K → **现测 22.8K/30,000 PASS**（`cd hub-engine && .venv\Scripts\python.exe -m scripts.startup_budget`）
- 分层：L0（AGENTS / CHARTER / **本文件** / 根 INDEX 目录版）→ L1 四型（`tools/task_tier.py`）→ L2 检索
- 安全底座常驻：单写者+§4 守护+ledger；query-first + 交回用户 + 回写
- 方案 `docs/compose/specs/2026-09-23-slim-rules-gates-design.md`；计划 `docs/compose/plans/2026-09-23-slim-rules-gates.md`
- 分项帽：AGENTS≤2500 / CHARTER≤1500 / WORK≤5000 / INDEX≤20000（和 29,000 ≤ 总帽 30,000；不变量有测试看守）
- **测试 471 passed / 4 skipped / 0 failed**；ruff 全绿；lint 干净；audit ✅ 健康
- 磁盘：已释放 ≈1.61 GB（`work/` 历史基准夹具 + `.mimocode/node_modules`）

## 活跃待办

| # | 任务 | 触发 / 做法 |
| -- | --- | --- |
| **T1** | 量「规则遵循/返工」改造前后 | **重跑 ≥2026-10-07**：`python -m scripts.rule_following_timeseries`。判据 3 条见下 |
| T2 | 复核 INDEX 可定位性 | `python -m scripts.index_locatability_bench --rev 68088fa^`（当前 18/20、覆盖 42.5%）。**关键词代理，不衡量语义理解** |
| T3 | ~~四项待裁定~~ | **已裁定（2026-09-24）**：①夹具腐化→**修**（67%→100%）②RRF 保底→**已不复现** ③CWD 依赖→不再复现，**加固**（建库落库存绝对路径）④巡检 fail-below→**修**（补回 `--fail-below 0.8`） |
| **P0-A** | **修检索召回**（唯一核心功能失效项） | 回归集已建：`python -m scripts.recall_regression`。实测生产模式（word）**recall@5 65% / recall@1 5%** vs char 90%/75% ⇒ 根因是 **CLI 默认 `mode=word` 排序劣化**，非模型能力 |
| P0-B | 蓝图分池（121 张外部蓝图挤占召回，已在 word 模式未命中项中现形） | 依赖 P0-A（同一份检索代码，**应与 P0-A 合并一次做**） |
| P1 | 外部非版本控制脚本迁入（~8 活跃 / ~1000 行，含 `nightly_consolidate`、`local_summary`） | 无依赖 |
| P1 | 统一定时任务路径（3 个任务指向 **2 个检出**） | 依赖上项 |
| P1 | 补 16 个巡检步骤测试（现 **4/20** 有） | 可分批，无依赖 |
| P2 | 8 个零引用脚本（1,660 行）+ 仪表盘子系统的处置（~4,900 行、无入口） | **需你给方向**（谁还在手动用？） |

> 审计报告（2026-09-24）结论：**总分 5.9/10**，加权最差项是检索召回与代码卫生。
> 已修：secret_sentry 假红灯（26 误报 → 0，真泄漏已脱敏）、护栏与报警可信度。

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
- **每日 07:30** `AgentHub-DailyPatrol` → `scripts/run_patrol.cmd` → `patrol_runner`（20 步：lint / pytest / ruff / startup_budget / 向量回归【已补 `--fail-below 0.8`】/ autofix）
- **每日 06:00** `AgentHub-SecretSentry` → `scripts/secret_sentry.cmd` → `scripts/secret_sentry.py`（**2026-09-24 迁入仓库并重写**：26 条永久误报 → 0，真泄漏已脱敏；LastTaskResult 由恒 2 变 0）
- **手动门禁**：`python -m scripts.recall_regression`（召回回归集，20 条金标准，退出码 2 = 未达 90% 目标）
- 验收：`.venv\Scripts\python.exe -m pytest` → **471 通过 / 4 跳过 / 0 失败**；`startup_budget` 退出码 0

## 禁止 / 注意

- **勿执行** `scripts/merge-methodology.py`、`scripts/deduplicate-experience.py`——已加拒绝护栏（实测会截断内容 / 误杀互补卡）
- **解释器必须用 `.venv\Scripts\python.exe`**：系统 python 缺 jieba，会让 9 个检索/分词测试**静默跳过**（假绿）
- 中枢卡提交须 `git -C AgentMemoryHub`（嵌套 git，外层已 gitignore）；巡检脏文件单独分笔提交
- embed 配置以 `AgentMemoryHub/system/config.yaml` 为准（生效单源；`hub-engine/config/engine.config.yaml` 仅兜底）
- **外层超时必须 > 内层超时**（pytest 步骤外 420s / 内 180s；曾因外 120s < 内导致内层永不生效）
- **夹具里的期望卡名会随卡片生命周期漂移**：归档卡片时必须同步检查引用它的夹具（否则门禁数学上无法达标）
- 勿提交 `nul`（已清除的幽灵条目）
