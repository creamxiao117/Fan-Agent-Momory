# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-25 · **审计 P1 六项 + P2 六小项 + 重构 A–D 均已收口**；只剩 T1（时间门）与 `sync.ingest` 拆分（待专项）

> 过程明细：`docs/superpowers/retro/work-history.md`｜T1 基线：`docs/compose/metrics/2026-09-23-t1-baseline.md`｜清理留档：`docs/compose/cleanup/`｜**全面分析：`docs/compose/reports/2026-09-25-project-audit.md`**

## 当前状态

- 启动链曾 136K → **现测 24.6K/30,000 PASS**（`cd hub-engine && .venv\Scripts\python.exe -m scripts.startup_budget`）
- 分层：L0（AGENTS / CHARTER / **本文件** / 根 INDEX 目录版）→ L1 四型（`hub-engine/tools/task_tier.py`）→ L2 检索
- 安全底座常驻：单写者+§4 守护+ledger；query-first + 交回用户 + 回写
- 分项帽：AGENTS≤2500 / CHARTER≤1500 / WORK≤5000 / INDEX≤20000（和 29,000 ≤ 总帽 30,000；不变量有测试看守）
- **测试 565 passed / 4 skipped / 0 failed**；**ruff 新规则集（B/SIM/UP/C901）全绿**；lint 干净；**巡检 24 步 exit 0**（健康 92/100）
- **检索 recall@5 100% / recall@1 86%**（22 条金标准）；向量回归 100%；**检索稳态延迟 340 → 138 ms**（P2-e）
- **覆盖率基线 40.0%**（生产代码；tools/ 84.3% · scripts/ 23.6%）；**两仓均已推送 origin**；`work/` 只剩 `_archive/`

## 活跃待办

| # | 任务 | 触发 / 做法 |
| -- | --- | --- |
| **T1** | 量「规则遵循/返工」改造前后 | **重跑 ≥2026-10-07**：`python -m scripts.rule_following_timeseries`；判据见下 |
| **SPLIT** | `sync.py::ingest`（229 行）拆分 | **需先补 fixture 级测试再动**：它是写入路径（单写者 + 判重 + 冲突区），高风险低收益；`C901` 基线为它留着记录 |

### T1 重跑判据（可证伪）

1. 门禁：后窗口 **≥10 天**且 `invalid/orphans/ghosts` 全 0 → 正面
2. 产出：周产出率 **≥40%** 且重复率 **≤60%** → 流入恢复
3. 反面：任一维度复现非零 / 产出率仍 **≤11%** → **未触及根因，须重新诊断**

> 首轮结论「未成立」、完整表格与可比性缺口（lint 报告两种格式）见 T1 基线文档。

## 门禁（都必须在跑，不只是"代码里有"）

- **提交时**（`.git/hooks/pre-commit` V1.2，源 `hub-engine/scripts/pre-commit`）：编码 → **预算** → ruff check → ruff format
- **每日 07:30** `AgentHub-DailyPatrol` → `scripts/run_patrol.cmd` → `hub-engine/scripts/patrol_runner.py`（**24 步**：lint / pytest / ruff / startup_budget / 向量回归【含 `--fail-below 0.8`】/ 平台三项 / autofix）
- **每日 06:00** `AgentHub-NightlyConsolidate` → `scripts/nightly_consolidate.cmd`（distill→build-vectors→sleep→local-summary；**仅 build-vectors 失败才非零**）
- **每日 06:00** `AgentHub-SecretSentry` → `scripts/secret_sentry.cmd` → `hub-engine/scripts/secret_sentry.py`（**26 条永久误报 → 0**）
- **手动**：`python -m scripts.recall_regression`（22 金标准，退出码 2 = 未达 90%）；`python -m scripts.index_locatability_bench --rev <rev>`；`python -m scripts.audit_dead_modules`（零引用审计，**有假阳性须复查**）；**覆盖率** `pytest --cov=. --cov-report=term:skip-covered`（基线 40.0%，暂不设 fail_under）
- 验收：`.venv\Scripts\python.exe -m pytest` → **565 通过 / 4 跳过 / 0 失败**；`startup_budget` 退出码 0

## 已闭环（本迭代；明细见各留档与 `work-history.md`）

- **审计 P1-a**（I-1）规则集：`select E4/E7/E9/F/W/I/UP/B/SIM/C901` + 行宽 120 钉死 + E501/C901 按文件登记基线（81/16）
- **审计 P1-b**（I-3）覆盖率：装 pytest-cov、立基线 **40.0%**、写进 `[tool.coverage.*]`（暂不设阈值）
- **审计 P1-c**（I-2）硬编码清零：**57 处**个人/本机绝对路径 → 自解析／`Path.home()`／单点 `external_path()`；新增护栏测试（首次运行即多揪出 10 处）
- **审计 P1-d**（I-4）`work/` 迁入：审计器入仓，5 个一次性脚本归档（`work/_archive/oneoffs-20260925/`）
- **审计 P1-e**（I-6）推送：外层 + 中枢推 origin（中枢 rebase 了 skillhub-bot 的 1 笔自动同步）
- **审计 P1-f**（I-5）单点降级：`local_summary` **自愈** LM Studio `.internal\temp` 缺失（含 4 例测试）
- **P0-A** 检索召回 5%→80%（`2a22648`）；**P0-B** 蓝图配额证伪，改冠军保底+通道加权 → **100%/86%**（`9c7f79f`）
- **P1-1** 脚本迁入（`ee4af05`）+ 三定时任务统一指本检出 + 24 步巡检契约测试（`703ce45`，+73 例）
- **P2** 死代码/仪表盘处置 + **T2** INDEX 可定位性复核（17/20→18/20、36.5%→42.5%）+ **T3** 四项待裁定
- **审计 P2 六小项**：P2-a `lint_report` argparse、P2-b 拆超长函数（`run_patrol` 319→57、`auto_flywheel.run` 220→109）、P2-c 卡片去重裁定（pluginhub v1.1 的 3 条教训并入 v1.2）、P2-d 路径写全与空目录定去留、P2-e 延迟剖析（**340→138 ms**）、P2-f markdownlint 挂门禁
- **重构 A–D**：A 巡检器拆分（9 个 `_stage_*`）· B 仪表盘单一化（v4 归归档，保留巡检产物 + 手动 HTML）· C 删 `node_modules/` + `.tools/`（≈12.8 MB）· D `work/` 定为只读归档区（97 件归档）
- **历史遗留文件清理**：逐项取证（untracked 归档/删除、tracked 记 blob SHA）；留档 `docs/compose/cleanup/2026-09-25-legacy-files-and-work-disposition.md`
- **secret_sentry** 26 误报 → 0；**审计总分 5.9 → 7.7/10**

## 禁止 / 注意

- **勿执行** `scripts/merge-methodology.py`、`scripts/deduplicate-experience.py`——已加拒绝护栏（实测会截断内容 / 误杀互补卡）
- **解释器必须用 `.venv\Scripts\python.exe`**：系统 python 缺 jieba，会让 9 个检索/分词测试**静默跳过**（假绿）
- 中枢卡提交须 `git -C AgentMemoryHub`（嵌套 git，外层已 gitignore）；巡检脏文件单独分笔提交
- embed 配置以 `AgentMemoryHub/system/config.yaml` 为准（生效单源；`hub-engine/config/engine.config.yaml` 仅兜底）
- **外层超时必须 > 内层超时**（pytest 步骤外 420s / 内 180s；曾因外 120s < 内导致内层永不生效）
- **夹具里的期望卡名会随卡片生命周期漂移**：归档卡片时必须同步检查引用它的夹具（否则门禁数学上无法达标）
- **LM Studio 缺 `%LMSTUDIO_HOME%\.internal\temp` 会让所有模型 JIT 加载 400**（`mkdtemp ENOENT`）；`hub-engine/scripts/local_summary.py` 现已**自愈**（解析报错建回目录并重试一次），其余调用方仍需人工建目录
- **文档里写的命令必须来自被跟踪的文件**：`work/` 是 gitignore 草稿区，把它的脚本写进文档就制造悬空引用（审计 I-4 / M-3 是同一个病）
- **零引用 ≠ 死代码**：`audit_dead_modules` 存在假阳性，删除前逐个人工看入口/注册表
- 勿提交 `nul`（已清除的幽灵条目）
