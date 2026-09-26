# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-25 · **审计 P1 六项 / P2 六小项 / 重构 A–D / SPLIT / COV / D1 / D2 / R1 均收口；重评 7.7 → 8.5 → 8.7/10（§11）**；只剩 T1（时间门）

> 过程明细 `docs/superpowers/retro/work-history.md`｜T1 基线 `docs/compose/metrics/2026-09-23-t1-baseline.md`｜清理留档 `docs/compose/cleanup/`｜**审计（§11 即最新评分）：`docs/compose/reports/2026-09-25-project-audit.md`**

## 当前状态

- 启动链曾 136K → **现测 25.2K/30,000 PASS**（`python -m scripts.startup_budget`）
- 分层：L0（AGENTS / CHARTER / **本文件** / 根 INDEX 目录版）→ L1 四型（`hub-engine/tools/task_tier.py`）→ L2 检索
- 安全底座常驻：单写者+§4 守护+ledger；query-first + 交回用户 + 回写
- 分项帽：AGENTS≤2500 / CHARTER≤1500 / WORK≤5000 / INDEX≤20000（和 29,000 ≤ 总帽 30,000；不变量有测试看守）
- **测试 681 passed / 4 skipped / 0 failed**；**ruff 新规则集（B/SIM/UP/C901）全绿**；lint 干净；**巡检 24 步 exit 0**（248 s，健康 92/100）
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
- **每日 06:00** `AgentHub-NightlyConsolidate` → `scripts/nightly_consolidate.cmd`（distill→build-vectors→sleep→local-summary）
- **每日 06:00** `AgentHub-SecretSentry` → `scripts/secret_sentry.cmd`（误报 **26 → 0**）
- **手动**：`python -m scripts.recall_regression`（**58 条金标准**，退出码 2 = 未达 90% 或夹具失效）；`python -m scripts.index_locatability_bench --rev <rev>`；`python -m scripts.audit_dead_modules`（零引用审计，**有假阳性须复查**）；**覆盖率** `pytest --cov=.`（基线 40.0%，实测 54.0%）
- 验收：`.venv\Scripts\python.exe -m pytest` → **681 通过 / 4 跳过 / 0 失败**；`startup_budget` 退出码 0

## 已闭环（本迭代；明细见各留档与 `work-history.md`）

- **审计 P1-a**（I-1）规则集：`select E4/E7/E9/F/W/I/UP/B/SIM/C901` + 行宽 120 + E501 按文件登记基线（C901 已于 SPLIT2 清零）
- **审计 P1-b**（I-3）覆盖率：装 pytest-cov、立基线 **40.0%**、写进 `[tool.coverage.*]`
- **审计 P1-c**（I-2）硬编码清零：**57 处** → 自解析／`Path.home()`／单点 `external_path()`；新增护栏测试（首次即多揪出 10 处）
- **审计 P1-d**（I-4）/ **P1-e**（I-6）/ **P1-f**（I-5）：`work/` 审计器入仓 · 两仓推 origin · `local_summary` 自愈 LM Studio `.internal\temp`（含 4 例测试）
- **P0-A** 检索召回 5%→80%（`2a22648`）；**P0-B** 蓝图配额证伪，改冠军保底+通道加权 → **100%/86%**（`9c7f79f`）
- **P1-1** 脚本迁入（`ee4af05`）+ 三定时任务统一指本检出 + 24 步巡检契约测试（`703ce45`，+73 例）
- **P2 / T2 / T3** 死代码与仪表盘处置 + INDEX 可定位性复核（17/20→18/20）+ 四项待裁定
- **审计 P2 六小项**：`lint_report` argparse · 拆超长函数 · 卡片去重裁定 · 路径写全 · 延迟剖析（**340→138 ms**）· markdownlint 挂门禁（详审计 §4）
- **重构 A–D**：巡检器拆分（9 个 `_stage_*`）· 仪表盘 v4 归归档 · 删 `node_modules/`+`.tools/`（≈12.8 MB）· `work/` 定为只读归档区
- **历史遗留清理**：逐项取证（tracked 记 blob SHA、untracked 先归档）；留档 `docs/compose/cleanup/`
- **SPLIT 收口**：`sync.py::ingest` **229 → 54 行**（先补 **14 例分支级夹具测试**再抽函数，前后同一套测试全绿）
- **COV 收口**：`scripts/` 覆盖率 **26.9% → 41.8%**（TOTAL 54.0%），+73 例测试；顺带修 3 个真 bug（详审计 §11.2）
- **D1/D1b 收口**（审计 §11.5）：6 张卡补 `status` + 4 张补空 `tags`；门禁与修复器升 V1.1（必填字段缺失即阻断、可一键修）；顺手修掉修复器漏 `deprecated` 的潜在错改
- **SPLIT2 收口**：C901 **16 → 0**（第二批拆 8 个；保真靠 stdout 逐行 diff + 新补 14 例网）；**顺带修 `auto_fix_lint` 漏 `deprecated` 的错改**（详审计 §11.7）
- **patrol 拆包**（审计 §11.8）：`patrol_runner.py` **1,597 → 477 行**（core/steps/report + 编排层，依赖单向）；纯搬运经 AST 源码比对（53/53）；新增 `test_patrol_cli.py` 守护**入口/重导出**（防“定时任务假绿”）
- **D2 收口**（审计 §11.6）：金标准 **22 → 58 条**（+39 含 8 条真实日志；剔除 3 条 candidate 目标）；@1 恢复分辨力（word **100%/79%**、char 100%/72%）；顺带揪出冠军保底“补首位”抢位缺陷 → 改补末位；**R1**（唯一真未命中）由“保底前 2 条 + 卡补 tag”关闭
- **重评两轮**：同一口径重测 → **加权 7.7 → 8.5（§10）→ 8.7/10（§11）**；代码卫生 6.0→**8.3**、可维护性 6.0→**8.4**、测试与门禁 8.5→**9.3**
- **secret_sentry** 26 误报 → 0；**首评总分 5.9 → 7.7（整改前） → 8.5 → 8.7（重评两轮）**

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
