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
| **T1** | **量「规则遵循/返工」改造前后**——唯一需要真实时间的一条 | **首轮已执行 2026-09-23**（见下）。**重跑触发 ≥2026-10-07**：`python -m scripts.rule_following_timeseries --csv` |
| T2 | 复核 INDEX 可定位性 | `python -m scripts.index_locatability_bench --rev 68088fa^` —— 当前 18/20 可定位、覆盖 42.5%（改造前 17/20、36.5%）。**该指标是关键词代理，不衡量语义理解** |
| T3 | 上一轮遗留「待用户裁定」四项 | vector_bench 夹具 / patrol fail-below / `_norm_path` CWD / RRF 保底——非本迭代引入，须人工裁定 |
| T4 | ~~幽灵 vs 未登记两工具是否再合并~~ | **已裁定（2026-09-23）：保持分开**。两者是同一问题的两个方向，不是两份实现——`fix_orphans`＝「文件有/INDEX 无」**纯追加**；`fix_index_registry`＝「INDEX 有/文件无」**改名源文件**（危险等级更高）。合并会让 `--apply` 语义模糊（会动源文件吗？）。共享契约已收敛到 `scripts/index_consistency.py`，故分开不再漂移。裁定原文与理由写在 `index_consistency.py` 头部；**若推翻请同步改此行并说明理由** |

## T1 首轮结果（2026-09-23 执行，**结论：未成立**）

三条数据源：快照 32 份（08-17~09-24）+ lint 周期报告 11 份（08-17~09-15）+ **ingest 流水账 32 天（08-17~09-23）**。

### ① 门禁维度

| 项 | 值 |
|:--|:--|
| 改造前（快照） | 17 个有数据的天，**5 天** `invalid>0`，最大 **21** |
| 改造前（报告） | 11 份中 **4 份** `invalid>0`；新格式“问题数”最大 **40** |
| 改造后 | **2 天，全维度均 0** |

### ② 知识产出维度（ingest 流水账，**定义始终未变，最值得看**）

| 周 | 提交量 | 入区 | 重复 | 重复率 | **新知识产出率** |
|:--|--:|--:|--:|--:|--:|
| W34 | 90 | 75 | 15 | 17% | 83% |
| W35 | 37 | 15 | 22 | 59% | 41% |
| W36 | 37 | 13 | 24 | 65% | 35% |
| W37 | 33 | 9 | 24 | 73% | 27% |
| W38 | 35 | 4 | 31 | 89% | **11%** |

**读法**：W34 是建库初始爆发（不可比）；**W35→W38 提交量稳定在 ~35/周，但新知识产出率 41%→11% 单调下降，重复率 59%→89%** —— 即“投入照旧、新知识越来越少”，是**返工/漂移的量化证据**。
（注：高去重率本身也是门禁在正常工作；担忧的是**产出率下降**本身。）

### 诚实结论
**门禁状态已确认干净**（后窗口 2/2 天全 0），但**趋势未成立**——n=2 天排除不了偶然。

⚠️ 可比性缺口：lint 报告两种格式——旧（~08-27）报 孤儿/无效/幽灵；新（09-08 起）报
“发现问题数”**且新增 long_desc/short_desc**（09-08 的 40 项里 34 项是 long_desc，旧格式不检）
⇒ **跨格式不可直接比大小**，只有 `无效卡片/invalid` 同义可比。

**重跑时的可证伪判据**（≥2026-10-07）：
1. 门禁：后窗口 **≥10 个有数据的天**且 `invalid/orphans/ghosts` 全 0 → 正面
2. **产出：周新知识产出率回到 ≥40%（即 W35 水平）且重复率 ≤60%** → 说明流入恢复
3. 反面：任一维度复现非零 / 产出率仍 ≤11% → 优化未触及根因，须重新诊断
4. 无效对比：若期间 lint 检查维度或 ingest 统计口径变了，**必须分段比较**

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
