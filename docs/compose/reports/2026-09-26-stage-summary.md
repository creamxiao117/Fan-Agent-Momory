# 阶段总结 · 记忆中枢审计整改 + 调度治理（2026-09-25 → 09-26）

- **阶段范围**：`20260817-Fan-Agent-Momory`（外层）+ 嵌套中枢仓 `AgentMemoryHub`
- **阶段起点**：审计首评 **5.9/10**（2026-09-24）→ 本阶段结束 **8.7/10**
- **提交量**：外层 **43 笔** + 中枢 **28 笔**（含 SkillHub/star-distill 自动同步提交）
- **配套文档**：逐时点评分与实测见 `docs/compose/reports/2026-09-25-project-audit.md`（§2 首评 / §9 执行记录 / §10–§11.9 逐轮重评与追加修复）

---

## 0. 结论先行

**做完了什么**：把"审计报告里已登记的欠债"逐条改成"已还清 + 有护栏 + 可复算"，并把**真实跑在机器上的定时任务**从 7 个精简到 5 个、修好 4 个长期失败的、统一换成 Token Plan 模型、关掉微信外发。

**两个数字最能说明**：**测试 558 → 683**（且新测试实测揪出 **6 个真 bug**）；**代码复杂度债 16 → 0**（不再有超阈函数，基线豁免条目清零）。

**遗留 1 项**：T1（规则遵循/返工）重跑受时间门约束，**≥2026-10-07** 才能做对照。

---

## 1. 量化成绩（同口径，全部实测）

| 指标 | 阶段初 | 阶段末 | 说明 |
|:--|--:|--:|:--|
| 审计加权总分 | **5.9** | **8.7** | 5.9 → 7.7（整改前）→ 8.5（§10）→ 8.7（§11） |
| 测试 | 558 passed | **683 passed / 4 skipped** | +125；含 24 步巡检契约、融合层、金标准夹具体检 |
| 覆盖率（生产代码） | 无度量 → 40.0%（基线） | **56.3%** | tools 85.8 / common 91.1 / patrol 86.2 / commands 63.5 / scripts 42.6 |
| C901 超阈函数 | 16 | **0** | `pyproject.toml` 里的 C901 豁免条目 16 → 0 |
| 函数 >100 行 | 24 | **14** | 最长 `build_timeline_html` 225 行 |
| 硬编码个人/本机路径 | 57 处 / 22 文件 | **0**（+ 护栏测试） | 白名单仅 2 处且校验"确有该串" |
| TODO/FIXME | 6 | **1** | 仅模板骨架 |
| E501 长行 | 81 | **78** | 仍在按文件基线，**未还清**（内容型长行） |
| 检索 recall@5（word 生产路径） | 5%（诊断篇）→ 100%（22 条） | **100%（58 条）** | @1 79%（22 条时 86% 已饱和） |
| 金标准集 | 22 | **58** | 含 8 条真实日志改写；新增夹具体检（失效即 exit 2） |
| 检索稳态延迟 | ~340 ms | **~138 ms** | 首调 6.7 s 属进程级一次性 |
| 巡检 | 24 步 exit 0（199 s） | **24 步 exit 0（264 s，健康 92/100）** | 步骤数未变，用例变多 |
| 启动链预算（L0） | 24.9K/30K | **25.0K/30K**（WORK 4,771/5,000） | 分项帽有测试看守 |
| 磁盘/仓库体量 | — | 释放 ≈12.8 MB；仪表盘 v4（32 文件/1,691 行）归档；`work/` 定为只读归档区 | 逐项取证（tracked 记 blob SHA、untracked 先归档） |

---

## 2. 做了什么（按层）

### 2.1 审计整改：P1 六项 + P2 六小项 + 重构 A–D

- **P1**：规则族启用（`B/SIM/UP/C901` + 行宽 120 + 按文件基线）· 覆盖率基线 · **硬编码清零**（+护栏）· `work/` 在用脚本入仓 · 两仓推送备份 · 单点降级自愈（LM Studio `.internal\temp`）
- **P2**：`lint_report` 补 argparse · 卡片去重裁定（pluginhub v1.1 教训并入 v1.2）· **检索延迟剖析提速 2.5×** · markdownlint 挂提交门禁 · 路径写全/空目录定去留 · 死代码与仪表盘处置
- **重构 A–D**：巡检器拆 9 个 `_stage_*` · 仪表盘单一化（v4 死路线归档）· 删 `node_modules/`+`.tools/` · `work/` 定位为只读归档区

### 2.2 度量与重构：COV → SPLIT → SPLIT2

- **COV**：`scripts/` 覆盖率 26.9% → 41.8%（+64 例），**并因此找出 3 个真 bug**（日报空 `_gap` KeyError 崩 / 健康分把"LLM 未知"当满分 / `card_tags` 块写法只读首个 tag）
- **SPLIT**：`sync.ingest` 229 → 54 行（先补 **14 例分支级夹具测试**再动手）
- **SPLIT2**：**C901 16 → 0**，共拆 14 个函数；保真靠 **stdout 逐行 diff（差异 0）** 与新增 14 例测试网；**顺带修** `auto_fix_lint` 漏 `deprecated` 的错改（会把作废卡改回 active）

### 2.3 数据卫生：D1/D1b → D2 → R1

- **D1（根因）**：`parse_card` 对缺字段有默认值 ⇒ `validate_card` **永远看不到"没写"**；补 **raw 层**判定（`type/status/updated` 缺即阻断、`tags` 空即警告），门禁与修复器同步升 V1.1；6 张卡补 `status`、4 张补空 `tags`；**469 张卡 0 警告**
- **D2**：金标准 22 → 58 条，@1 从饱和恢复分辨力；**顺手揪出向量保底"补首位"抢位缺陷**（带假 `score=0.0` 却压在真命中卡之前）
- **R1**：唯一真未命中（`memory-hub-card-promotion`，向量第 2 却被融合挤出）→ 保底从"只保第 1"推广到 **保前 2** ⇒ word recall@5 **98% → 100%**

### 2.4 调度治理：Hermes 定时任务 7 → 5 + 模型统一 + 停止外发

| 时间 | 任务 | 类型 |
|:--|:--|:--|
| 07:30 | 中枢晨间日报（6 面板 + 补卡候选） | 脚本 `hub_daily_cron.py` |
| 07:40 | 飞轮·草稿自动提升 | 脚本 `flywheel_cron.py` |
| 07:50 | 每日 GitHub star-distill + T1 迭代 | **agent**（唯一） |
| 周六 08:00 | 每周召回评测复核 | 脚本 `recall_review_cron.py` |
| 周六 08:10 | SkillHub 周晋级巡检 | 脚本 `skillhub_promote.py` |

- **删 2 个重复的**：`中枢每日健康快照`（agent 版，与 Windows `AgentHub-DailyPatrol` 完全重复，且 prompt 还写着"本机 .venv 不存在"）、`5平台每日健康检查`（已是巡检的三个步骤）
- **合并/重构**：新写晨间链（6 工具 → 日报 → 补卡候选归档 → 睡眠候选 → 中枢提交）；周召回评测从 agent 提示词改脚本（原 prompt 引用的 `work/bench_recall.py` 已归档、`vector_bench.py` 已退役 ⇒ 本来就跑不通）
- **模型**：`qwen3.5-35b-a3b@localmoe`（端点不可用，3 个 agent 任务连续 5 天 Connection error）→ 统一 **`mimo-v2.6-flash@xiaomi`（reasoning-effort=low）**，连通性用一次性 prompt 实证
- **外发**：5 个任务全部 `deliver=local`（零自动外发）；**微信通道整体停用**（`platforms.weixin.enabled: false` + `hermes gateway restart`，日志实证"will NOT start its adapter" + "Gateway running with 1 platform(s)"）
- 详见中枢卡 `projects/hermes-cron-jobs`（含回滚与恢复路径）

### 2.5 自查回归修复（本阶段自己踩的坑，自己修）

| 回归 | 现象 | 护栏 |
|:--|:--|:--|
| **P1-c 漏 `sys.path` 引导** | `hub_orchestrator.py` 改成 `from common.config import …` 后，被外部调度器以绝对路径+任意 cwd 调用 ⇒ `ModuleNotFoundError`，2026-09-26 06:00 真挂一场；静态扫描又捐出 **3 个同病脚本**（含 **MCP 启动链** `hub_mcp_launcher`） | `tests/test_script_bootstrap.py`：静态扫"import 项目包前必须引导" + 反例端到端（任意 cwd + 绝对路径真跑一次） |
| **拆包漏 CLI 入口** | 漏搬 `if __name__ == "__main__":` ⇒ `python -m scripts.patrol_runner` **静默 exit 0 什么都不做**（定时任务视角就是"全绿"），而单测/契约测试全绿 | `tests/test_patrol_cli.py`：`--help` 必须真打 usage · `__all__` 全部可访问 · re-export 是同一对象 · `main` 可调用 |

**共同教训（已入中枢经验卡）**：**"单测全绿 ≠ 调度器能跑"** —— 单测都是 `import scripts.x`（`sys.path` 已就绪、入口是函数），而真实调用方是「绝对路径 + 任意 cwd + CLI 入口」。

---

## 3. 证据索引（都可复算）

| 想要什么 | 命令 / 位置 |
|:--|:--|
| 全部数字的来源 | `docs/compose/reports/2026-09-25-project-audit.md` §6 复现命令 |
| 逐时点评分 | 同报告 §2 / §10 / §11（最新有效 = §11 的 8.7） |
| 追加修复记录 | 同报告 §11.5（D1/D1b）· §11.6（D2/R1）· §11.7（SPLIT2）· §11.8（patrol 拆包）· §11.9（回归） |
| 测试 / 覆盖率 | `.venv\Scripts\python.exe -m pytest -q`（683）· `pytest --cov=.`（56.3%） |
| 巡检（24 步） | `scripts\run_patrol.cmd` → `AgentMemoryHub\.sync\patrol.log`（exit 0 / 264 s / 92 分） |
| 召回与金标准 | `python -m scripts.recall_regression`（58 条，word 100%/79%）· `index_locatability_bench` |
| 规则债现状 | `python -m ruff check .`（0）· 隔离口径 C901（0） |
| 调度现状 | `hermes cron list` / `hermes cron doctor`；中枢卡 `projects/hermes-cron-jobs` |
| 清理留档 | `docs/compose/cleanup/`（三份，含逐项 blob SHA 取证） |

---

## 4. 遗留与下一阶段候选

| 项 | 状态 | 说明 |
|:--|:--|:--|
| **T1 重跑（时间门）** | **待做（≥2026-10-07）** | 判据三条已固化在 `WORK.md`（门禁 / 产出率与重复率 / 反面） |
| E501 78 处长行 | 已登记未还 | 内容型长行，重排会损可读性；可按文件逐个评估 |
| 首调延迟 6.7 s | 未优化 | jieba 词典 + 索引构建，进程级一次性；预热/持久化索引是可选项 |
| 单机依赖 + 无 CI | 设计选择 | LM Studio / 网关 / 计划任务全在一台机器 |
| 金标准集再扩容 | 可选 | 当前 58 条 @1 79%；扩到 80+ 才有更高分辨力 |
| `candidate` 目标卡 | 观察项 | 检索可召回 candidate 卡（只排除 archived/deprecated）——是否合适值得专门讨论 |

---

## 5. 提交明细（写清内容）

**外层仓（43 笔，按主题分组）**

- **审计报告与 WORK 回写（8 笔）**：`38ca6e0` 初版分析（7.7/10）· `de32403`/`cac81bd`/`57b5968`/`5b692ae`/`599dd74`/`6c98f46`/`f635dd8` 各轮收口与实测回写
- **P1 六项（7 笔）**：`ddbd873` 规则族 · `5e8ad56` 覆盖率基线 · `2841941` 硬编码清零 · `276e8da` 审计器入仓 · `2b8303d` 夜间摘要自愈 · （推送与清理见下）
- **P2 六小项 + 重构 A–D（7 笔）**：`b8e8fa4` argparse+markdownlint 门禁 · `049d283` 延迟提速 · `63c42d1` 巡检器拆分 · `ab9071b` auto_flywheel 拆分 · `235e2eb` 仪表盘单一化 · `9bc5322` 删遗留+work 归档 · `618a57c` markdownlint 归零
- **度量与重构（6 笔）**：`18727df` COV · `92117be`+`06a2c74` SPLIT · `f6518f1`+`88db4b4` SPLIT2 · `9d6684e` patrol 拆包
- **数据卫生（4 笔）**：`9e98040` D1 门禁/修复器 V1.1 · `499d2ed` D2 金标准扩容 · `077e41f` 文档修正 · `7e1d133` R1 保底 top-2
- **自查回归 + 调度治理（4 笔）**：`5cd5b43` sys.path 回归修复+护栏+Hermes 精简 · `6f17a11` 取消微信推送 · `4148bb7` 微信通道停用 · （护栏测试随首笔）
- **其它（7 笔）**：提前铺垫的 P0 召回修复、巡检契约测试、T1/T2/T3 收口、work 瘦身等

**中枢仓（28 笔，含自动同步）**

- **人工/本阶段**：`projects/hermes-cron-jobs` 新卡 + 2 次同步（投递策略、微信停用）· D1 的 10 张卡补元数据 · R1 的 tag 补充 · 规则卡 pre-commit 描述对齐 · 编码附录卡 · 巡检运行产物提交（多笔）
- **自动同步（其它主体）**：SkillHub auto-evolution · star-distill 6 张蓝图 + T1 验证回写 · ingest/INDEX 登记

---

*本文档由阶段收尾生成；后续轮次请按同样格式追加"下一阶段总结"，不要改写本文件的历史结论。*
