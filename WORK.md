# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-25 · **审计 P1 六项 / P2 六小项 / 重构 A–D / SPLIT / COV / D1 / D2 / R1 均收口；重评 7.7 → 8.5 → 8.7/10（§11）**；只剩 T1（时间门）

> 过程明细 `docs/superpowers/retro/work-history.md`｜T1 基线 `docs/compose/metrics/2026-09-23-t1-baseline.md`｜清理留档 `docs/compose/cleanup/`｜**审计（§11 即最新评分）：`docs/compose/reports/2026-09-25-project-audit.md`**

## 当前状态

- 启动链曾 136K → **现测 25.2K/30,000 PASS**（`python -m scripts.startup_budget`）
- 分层：L0（AGENTS / CHARTER / **本文件** / 根 INDEX 目录版）→ L1 四型（`hub-engine/tools/task_tier.py`）→ L2 检索
- 安全底座常驻：单写者+§4 守护+ledger；query-first + 交回用户 + 回写
- 分项帽：AGENTS≤2500 / CHARTER≤1500 / WORK≤5000 / INDEX≤20000（和 29,000 ≤ 总帽 30,000；不变量有测试看守）
- **测试 683 passed / 4 skipped / 0 failed**；**ruff 新规则集（B/SIM/UP/C901）全绿**；lint 干净；**巡检 24 步 exit 0**（248 s，健康 92/100）
- **检索（D2 扩容后 58 条金标准）word recall@5 98% / @1 79%**、char 100% / 70%；向量回归 100%；首调 6.7 s（进程级一次性）· 稳态 4–145 ms
- **覆盖率 56.3%**（生产代码；tools/ 85.8% · common/ 91.1% · 顶层 67.6% · commands/ 63.5% · **patrol/ 86.2%** · scripts/ 42.6%）；**两仓均已推送 origin**；`work/` 只剩 `_archive/`；**审计重评 8.7/10（§11）**

## 活跃待办

| # | 任务 | 触发 / 做法 |
| -- | --- | --- |
| **T1** | 量「规则遵循/返工」改造前后 | **重跑 ≥2026-10-07**：`python -m scripts.rule_following_timeseries`；判据见下 |

### T1 重跑判据（可证伪）

1. 门禁：后窗口 **≥10 天**且 `invalid/orphans/ghosts` 全 0 → 正面
2. 产出：周产出率 **≥40%** 且重复率 **≤60%** → 流入恢复
3. 反面：任一维度复现非零 / 产出率仍 **≤11%** → **未触及根因，须重新诊断**

> 首轮结论「未成立」、完整表格与可比性缺口（lint 报告两种格式）见 T1 基线文档。

## 门禁（都必须在跑，不只是"代码里有"）

- **提交时**（`.git/hooks/pre-commit` V1.3，源 `hub-engine/scripts/pre-commit`）：编码 → **预算** → markdownlint → ruff check → ruff format
- **每日 07:30** `AgentHub-DailyPatrol` → `scripts/run_patrol.cmd`（**24 步**：lint / pytest / ruff / startup_budget / 向量回归【含 `--fail-below 0.8`】/ 平台三项 / autofix）
- **每日 00:35** `AgentHub-NightlyConsolidate` → `scripts/nightly_consolidate.cmd`（distill→build-vectors→sleep→local-summary）
- **每日 06:00** `AgentHub-SecretSentry` → `scripts/secret_sentry.cmd`（误报 **26 → 0**）
- **每日 09:00** `PluginHub-PytestTempClean`（临时目录清理）
- **Hermes 链（5 个，07:30 起每 10 min；模型统一 `mimo-v2.6-flash@xiaomi`，全部 `deliver=local` = 零自动外发）**：07:30 晨间日报 → 07:40 草稿提升 → 07:50 star-distill+T1（唯一 agent）→ 周六 08:00 召回评测 → 周六 08:10 SkillHub（详卡 `projects/hermes-cron-jobs`）
- **手动**：`python -m scripts.recall_regression`（**58 条金标准**，退出码 2 = 未达 90% 或夹具失效）；`python -m scripts.index_locatability_bench --rev <rev>`；`python -m scripts.audit_dead_modules`（零引用审计，**有假阳性须复查**）；**覆盖率** `pytest --cov=.`（基线 40.0%，实测 54.0%）
- 验收：`.venv\Scripts\python.exe -m pytest` → **683 通过 / 4 跳过 / 0 失败**；`startup_budget` 退出码 0

## 已闭环（本迭代；明细见各留档、审计报告与 `RUNLOG.md` 本轮小结）

- **审计 P1 六项**：a 规则集（B/SIM/UP/C901 + 行宽 120）· b 覆盖率基线 · c 硬编码 **57 → 0**（带护栏）· d `work/` 审计器入仓 · e 两仓推送 · f `local_summary` 自愈 LM Studio `.internal\temp`
- **P0-A/B** 召回 5%→80% + 蓝图配额证伪（改冠军保底+通道加权）；**P1-1** 脚本迁入 + 24 步巡检契约测试（+73 例）
- **审计 P2 六小项**：`lint_report` argparse · 卡片去重裁定 · 延迟 **340→138 ms** · markdownlint 挂门禁（详审计 §4）；**T2** 可定位性 17/20→18/20；**T3** 四项待裁定
- **重构 A–D**：巡检器拆 9 个 `_stage_*` · 仪表盘 v4 归档 · 删 `node_modules/`+`.tools/`（≈12.8 MB）· `work/` 定为只读归档区；历史遗留逐项取证留档
- **SPLIT**：`sync.ingest` 229→54 行（先补 14 例夹具测试）；**COV**：`scripts/` 26.9%→41.8%（+73 例，顺带修 3 个真 bug，详审计 §11.2）
- **D1/D1b**（§11.5）：6 卡补 `status` + 4 卡补 tag；门禁/修复器升 V1.1（必填字段缺失即阻断、可一键修）
- **D2 + R1**（§11.6）：金标准 **22 → 58 条**；融合保底推广到 top-2 → word recall@5 **100%** / @1 79%
- **SPLIT2**（§11.7）：C901 **16 → 0**（豁免全删）；保真靠 stdout 逐行 diff；顺带修 `auto_fix_lint` 漏 `deprecated` 的错改
- **patrol 拆包**（§11.8）：`patrol_runner.py` **1,597 → 477 行**；AST 纯搬运 53/53；`test_patrol_cli.py` 守护入口（防假绿）
- **导入回归修复**（§11.9）：P1-c 漏 `sys.path` 引导 ⇒ Hermes 任务真挂；护栏又捐出 3 个同病脚本；`test_script_bootstrap.py`
- **Hermes 定时任务精简**：**7 → 5** + 模型统一 `mimo-v2.6-flash@xiaomi` + 07:30 起每 10 min + **取消微信推送（全部 `deliver=local`）**（卡 `projects/hermes-cron-jobs`）
- **重评两轮**：同一口径重测 → **7.7 → 8.5（§10）→ 8.7/10（§11）**；**首评 5.9 → 现 8.7**

## 禁止 / 注意

- **勿执行** `scripts/merge-methodology.py`、`scripts/deduplicate-experience.py`——已加拒绝护栏（实测会截断内容 / 误杀互补卡）
- **解释器必须用 `.venv\Scripts\python.exe`**：系统 python 缺 jieba，会让 9 个检索/分词测试**静默跳过**（假绿）
- 中枢卡提交须 `git -C AgentMemoryHub`（嵌套 git，外层已 gitignore）；巡检脏文件单独分笔提交
- embed 配置以 `AgentMemoryHub/system/config.yaml` 为准（生效单源；`hub-engine/config/engine.config.yaml` 仅兜底）
- **外层超时必须 > 内层超时**（pytest 外 420s / 内 180s；曾因外 120s < 内导致内层永不生效）
- **夹具里的期望卡名会随卡片生命周期漂移**：归档卡片时必须同步检查引用它的夹具（否则门禁数学上无法达标）
- **LM Studio 缺 `%LMSTUDIO_HOME%\.internal\temp` 会让所有模型 JIT 加载 400**（`mkdtemp ENOENT`）；`local_summary.py` 现已**自愈**（建回目录并重试一次）
- **文档里写的命令必须来自被跟踪文件**：`work/` 是 gitignore 草稿区，写进去就制造悬空引用（审计 I-4 / M-3 同一病）
- **零引用 ≠ 死代码**：`audit_dead_modules` 存在假阳性，删除前逐个人工看入口/注册表
- 勿提交 `nul`（已清除的幽灵条目）
