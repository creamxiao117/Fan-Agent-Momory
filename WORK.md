# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-25 · 下一条主任务 = **审计负债整改**（AUD，见活跃待办）；已闭环项已移入文末「已闭环」段

> 过程明细：`docs/superpowers/retro/work-history.md`｜T1 基线：`docs/compose/metrics/2026-09-23-t1-baseline.md`｜清理留档：`docs/compose/cleanup/`｜**全面分析：`docs/compose/reports/2026-09-25-project-audit.md`**

## 当前状态

- 启动链曾 136K → **现测 24.9K/30,000 PASS**（`cd hub-engine && .venv\Scripts\python.exe -m scripts.startup_budget`）
- 分层：L0（AGENTS / CHARTER / **本文件** / 根 INDEX 目录版）→ L1 四型（`hub-engine/tools/task_tier.py`）→ L2 检索
- 安全底座常驻：单写者+§4 守护+ledger；query-first + 交回用户 + 回写
- 方案 `docs/compose/specs/2026-09-23-slim-rules-gates-design.md`；计划 `docs/compose/plans/2026-09-23-slim-rules-gates.md`
- 分项帽：AGENTS≤2500 / CHARTER≤1500 / WORK≤5000 / INDEX≤20000（和 29,000 ≤ 总帽 30,000；不变量有测试看守）
- **测试 558 passed / 4 skipped / 0 failed**；ruff 全绿；lint 干净；**巡检 24 步 exit 0**（健康 92/100）
- **检索 recall@5 100% / recall@1 86%**（22 条金标准）；向量回归 100%

## 活跃待办

| # | 任务 | 触发 / 做法 |
| -- | --- | --- |
| **T1** | 量「规则遵循/返工」改造前后 | **重跑 ≥2026-10-07**：`python -m scripts.rule_following_timeseries`；判据见下 |
| **P1-c** | 硬编码清零（审计 I-2） | 22 文件 47 处个人绝对路径 → `__file__` 自解析／env 覆盖（优先 `bootstrap_hub.py` / `hub_mcp_launcher.py` / `mcp_healthcheck.py`）；加护栏测试禁新增 |
| **P1-a** | ruff 规则集（I-1） | `select = E,F,W,I,UP,B,SIM,C901`（`max-complexity=15`）；按文件建基线后分批清 |
| **P1-b** | 覆盖率基线（I-3） | 装 pytest-cov；`retrieve.py`/`sync.py`/`patrol_runner.py` 单列阈值 |
| **P1-d** | `work/` 迁入（I-4） | 审计器 / T1 派生 / `bench_recall` → `hub-engine/scripts/`；**T1 重跑前必须先做** |
| **P1-e** | 推送备份（I-6） | 外层 + 中枢推 origin；把推送纳入夜间链路（失败非零） |
| **P1-f** | 单点降级（I-5） | 夜间任务兜底建 `%LMSTUDIO_HOME%\.internal\temp`；LM Studio 停机时的降级可诊断性实测 |
| P2 | 六小项 | `lint_report.py` 加 argparse；拆超长函数（`run_patrol` 319 行等）；3 对高相似卡裁定；L0 路径写全；检索延迟剖析；markdownlint 挂门禁 |
| **重构** | 候选 A–D | **需你拍板**：**A 巡检器拆分**（有 24 步契约测试兜底，建议先做）／B 仪表盘单一化／C `.tools/` 去留／D `work/` 定位 |

### T1 重跑判据（可证伪）

1. 门禁：后窗口 **≥10 天**且 `invalid/orphans/ghosts` 全 0 → 正面
2. 产出：周产出率 **≥40%** 且重复率 **≤60%** → 流入恢复
3. 反面：任一维度复现非零 / 产出率仍 **≤11%** → **未触及根因，须重新诊断**

> 首轮结论「未成立」、完整表格与可比性缺口（lint 报告两种格式）见 T1 基线文档。

## 门禁（都必须在跑，不只是"代码里有"）

- **提交时**（`.git/hooks/pre-commit` V1.2，源 `hub-engine/scripts/pre-commit`）：编码 → **预算** → ruff；退出码 1/2/4/5
- **每日 07:30** `AgentHub-DailyPatrol` → `scripts/run_patrol.cmd` → `hub-engine/scripts/patrol_runner.py`（**24 步**：lint / pytest / ruff / startup_budget / 向量回归【含 `--fail-below 0.8`】/ 平台三项 / autofix）
- **每日 06:00** `AgentHub-NightlyConsolidate` → `scripts/nightly_consolidate.cmd`（distill→build-vectors→sleep→local-summary；**仅 build-vectors 失败才非零**——索引坏会静默劣化检索）
- **每日 06:00** `AgentHub-SecretSentry` → `scripts/secret_sentry.cmd` → `hub-engine/scripts/secret_sentry.py`（**26 条永久误报 → 0**）
- **手动门禁**：`python -m scripts.recall_regression`（**22 条**金标准含 2 条蓝图池守卫，退出码 2 = 未达 90%）；`python -m scripts.index_locatability_bench --rev <rev>`
- 验收：`.venv\Scripts\python.exe -m pytest` → **558 通过 / 4 跳过 / 0 失败**；`startup_budget` 退出码 0

## 已闭环（本迭代；明细见各留档与 `work-history.md`）

- **瘦身迭代 T14–T16**：已并入 master（分支已删）；启动链 136K → 24.9K
- **T2** INDEX 可定位性复核：17/20 → 18/20、覆盖率 36.5% → 42.5%（不劣化且改善；tags 变体破帽不采用）
- **T3** 四项待裁定：夹具腐化→修；RRF 保底→不复现；CWD 依赖→加固；巡检 `--fail-below 0.8`→补回
- **P0-A** 检索召回：根因「确定性通道部分命中即短路」→ `recall@1` **5% → 80%**（`2a22648`）
- **P0-B** 蓝图分池：配额对 recall **零影响 → 判不成立**；真因「向量强证据被 RRF 淹没」→ 冠军保底 + 通道加权，word **95%/77% → 100%/86%**（`9c7f79f`）
- **P1-1** 外部脚本迁入（`ee4af05`）+ 三定时任务统一指本检出 + 24 步巡检契约测试（`703ce45`，+73 例）
- **P2** 死代码/仪表盘处置：删 3 个零引用脚本（留 blob SHA）、仪表盘草稿归档（留档 `cleanup/2026-09-25-…`）
- **secret_sentry** 26 误报 → 0；**审计总分 5.9 → 7.7/10**（`docs/compose/reports/2026-09-25-project-audit.md`）

## 禁止 / 注意

- **勿执行** `scripts/merge-methodology.py`、`scripts/deduplicate-experience.py`——已加拒绝护栏（实测会截断内容 / 误杀互补卡）
- **解释器必须用 `.venv\Scripts\python.exe`**：系统 python 缺 jieba，会让 9 个检索/分词测试**静默跳过**（假绿）
- 中枢卡提交须 `git -C AgentMemoryHub`（嵌套 git，外层已 gitignore）；巡检脏文件单独分笔提交
- embed 配置以 `AgentMemoryHub/system/config.yaml` 为准（生效单源；`hub-engine/config/engine.config.yaml` 仅兜底）
- **外层超时必须 > 内层超时**（pytest 步骤外 420s / 内 180s；曾因外 120s < 内导致内层永不生效）
- **夹具里的期望卡名会随卡片生命周期漂移**：归档卡片时必须同步检查引用它的夹具（否则门禁数学上无法达标）
- **LM Studio 缺 `%LMSTUDIO_HOME%\.internal\temp` 会让所有模型 JIT 加载 400**（`mkdtemp ENOENT`）⇒ 夜间摘要恒空；修复=建回该目录，`hub-engine/scripts/local_summary.py` 已打印响应体可直接定位
- **文档里写的命令必须来自被跟踪的文件**：`work/` 是 gitignore 草稿区，把它的脚本写进文档就制造悬空引用（审计 I-4 / M-3 是同一个病）
- 勿提交 `nul`（已清除的幽灵条目）
