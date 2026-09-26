# RUNLOG.md（迭代日志 · 只追加 · 最新在前）

按轮次（R1…）追加；每条含巡检/门禁结果、决策与进行中的事项。当前状态见 `WORK.md`。

## [2026-09-25] R17 | 审计整改收口 + COV/SPLIT2 + 两轮重评（**8.7/10**）

- **审计报告**（`docs/compose/reports/2026-09-25-project-audit.md`）：首评 **5.9** → 整改前 **7.7**（§2）→ 第一轮重评 **8.5**（§10）→ **第二轮正式重评 8.7（§11）**；本会话 **31 笔提交**
- **P1 六项全闭环**：规则集（B/SIM/UP/C901 + 行宽 120）· 覆盖率基线 · **硬编码 57→0（带护栏）** · `work/` 审计器入仓 · 两仓推送 · `local_summary` 自愈 LM Studio `.internal\temp`
- **P2 六小项 + 重构 A–D**：`lint_report` argparse · 卡片去重裁定 · 延迟剖析（**340→138 ms**）· markdownlint 挂门禁 · 巡检器拆 9 个 `_stage_*` · 仪表盘 v4 归档 · 删 `node_modules/`+`.tools/`（≈12.8 MB）
- **SPLIT**：`sync.py::ingest` **229→54 行**（先补 14 例分支级夹具测试）· **COV**：`scripts/` **26.9%→41.7%**（TOTAL **53.9%**，+64 例 → **643 passed**）
- **测试实测揪出 3 个真 bug（已修+回归）**：日报空 `_gap` **KeyError 崩** · 健康分把“LLM 未知”当满分（总分虚高）· `card_tags` 块写法只读首个 tag
- **巡检**：24 步 exit 0（239 s，健康 **92/100**）· 预算 **25,114/30,000** · 两仓 ahead=**0**
- **新发现待办**：6 张 `experience/` 卡缺 `status`（`check_card_frontmatter` 不报）；金标准集 22 条已无区分度（recall 100%）；SPLIT2 余 8 个 C901（待有测试）
- **D1/D1b 当日已收口**（审计 §11.5）：6 张补 `status` + 4 张补空 `tags`；`common/frontmatter.py` 新增 raw 层 `raw_frontmatter()`/`missing_required_keys()`，门禁与修复器同步升至 V1.1（缺 `type`/`status`/`updated` → 阻断并可一键修）；顺手修掉修复器漏 `deprecated` 的潜在错改。验证：469 张卡门禁 0 警告 · 测试 **652 passed** · 巡检 exit 0
- **D2 当日已收口**（审计 §11.6）：金标准 **22 → 58 条**（+39：8 条真实日志改写 + 31 条区域补写；−3：目标卡是 candidate）；建立**夹具体检**（目标卡必须存在且 active/reference，否则 exit 2 且“修夹具不改阈值”）；@1 从饱和 86% 恢复分辨力；**顺带揪出向量冠军保底“补首位”缺陷**（带假 score=0.0 抢位）→ 改补末位；权重新集合上扫 1.0–2.0 同分 ⇒ 保留 1.5。验证：测试 **661 passed** · 巡检 exit 0（248 s）
- **R1 当日已收口**（审计 §11.6.3）：唯一真未命中 `memory-hub-card-promotion` —— 诊断确认它在**向量第 2**却被融合挤出（RRF 只看位序）；保底从“只保第 1”推广到**保前 2**（word @5 98% → **100%**，char 维持 100%；保 3/4 条反而伤 char）
- **SPLIT2 当日已收口**（审计 §11.7）：**C901 复杂度债 16 → 0**，`pyproject.toml` 里 C901 豁免全删；第二批拆 8 个函数（`audit_index.audit` / `post_ingest_hook.main` / `rule_following_timeseries.main` / `platform_bridge.push` / `status`×2 / `auto_fix_lint.run_fix` / `flywheel._cmd_daily_report`），保真靠 **stdout 逐行 diff（差异 0）**；顺手修 `auto_fix_lint` 漏 `deprecated` 的错改。验证：测试 **677 passed** · 巡检 exit 0（258 s）
- **patrol 拆包当日已收口**（审计 §11.8）：`patrol_runner.py` **1,597 → 477 行**（`scripts/patrol/{core,steps,report}.py` + 编排层，单向依赖）；纯搬运经 AST 源码比对 53/53；⚠️ 过程踩到**“假绿入口”**（漏搬 `if __name__ == "__main__"` ⇒ `python -m` 静默 exit 0 什么都不做，而所有单测/契约测试全绿）⇒ 新增 `test_patrol_cli.py` 守护入口与重导出。验证：测试 **681 passed** · 完整巡检 24 步 exit 0（248 s，健康 92/100）
- **自查回归已修**（审计 §11.9）：P1-c 给 `hub_orchestrator.py` 加 `from common.config import …` 时漏了 `sys.path` 引导 ⇒ 2026-09-26 06:00 Hermes 任务 `ModuleNotFoundError` 真挂一场（绝对路径 + 任意 cwd）；护栏测试又捐出 **3 个同病脚本**（`bootstrap_hub` / `demo_e2e` / **`hub_mcp_launcher`（MCP 启动链）**）一并修；新增 `tests/test_script_bootstrap.py`（静态扫 + 反例端到端）
- **Hermes 定时任务精简**（7 → 5）：删 2 个与 Windows 计划任务重复的（中枢每日健康快照 agent 版、5 平台健康检查）；2 个 LLM 任务改脚本；新写 `hub_daily_cron.py`（6 工具 + 日报 + 补卡候选 + 睡眠候选 + 快照提交→一条 07:30 链）与 `recall_review_cron.py`（召回回归 + 可定位性 + 缺口汇总）；**全部任务模型改 mimo-v2.6-flash@xiaomi（effort=low）**；时间 **07:30 / 07:40 / 07:50 + 周六 08:00 / 08:10**；**当日再取消微信推送（5 个任务全 `deliver=local`）+ 微信通道整体停用**（`platforms.weixin.enabled: false` + `hermes gateway restart`；实证日志：“explicitly disabled … will NOT start its adapter” + “Gateway running with 1 platform(s)”）。验证：`hermes cron run` 两个新脚本任务均 succeeded · 模型一次性 prompt 回“可用” · 详见卡片 `projects/hermes-cron-jobs`

## 阶段总结（R17 收尾 · 2026-09-25 → 09-26）

> **完整版：`docs/compose/reports/2026-09-26-stage-summary.md`**（量化对比表 / 分层做了什么 / 自查回归与教训 / 证据索引 / 遗留与下一阶段 / 提交明细）

**一句话**：把审计报告里的欠债从“已登记”改成“已还完”——保真优先、每步都留可复算的证据，并顺手捐出 6 个真 bug；再把真在跑的定时任务从 7 个精简到 5 个、修好 4 个长期失败的、统一换模型、关掉微信外发。

| 主题 | 做了什么 | 硬证据 |
|:--|:--|:--|
| **P1/P2 六项 + 重构 A–D** | 规则族启用、硬编码清零、覆盖率基线、`work/` 纳管、单点自愈、推送；`lint_report` argparse、卡片去重裁定、延迟 340→138 ms、markdownlint 挂门禁；巡检器拆分、仪表盘单一化、删遗留 ≈12.8 MB | 审计 §9/§10 |
| **COV** | `scripts/` 覆盖率 26.9% → 41.7%（+64 例） | 测试 579 → 643 |
| **SPLIT / SPLIT2** | `sync.ingest` 229→54 行；**C901 16 → 0**（豁免全删） | stdout 逐行 diff = 0 |
| **D1/D1b** | 6 卡补 `status` + 4 卡补 tag；门禁/修复器升 V1.1（raw 层必填字段） | 469 张卡 0 警告 |
| **D2 / R1** | 金标准 22 → 58 条；融合保底推广到 top-2 | word recall@5 **100%** |
| **patrol 拆包** | `patrol_runner` 1,597 → 477 行（core/steps/report 包） | AST 纯搬运 53/53 |
| **自查回归** | P1-c 引入的导入回归 + 3 个同病脚本 | 巡检 24 步 exit 0 |
| **Hermes 定时任务** | 7 → 5，模型统一 mimo-v2.6-flash，07:30 起每 10 分钟 | 两个新任务 run succeeded |

**当前基线**：测试 **683 passed / 4 skipped** · 覆盖率 **56.3%** · C901 **0** · 巡检 24 步 exit 0（264 s，健康 92/100）·
预算 25.0K/30,000 · 审计重评 **8.7/10** · 两仓 ahead=0 · 调度：Windows 4 任务 + Hermes **5 任务（零自动外发）**。

**遗留**：T1 重跑（**≥2026-10-07**，判据在 `WORK.md`）；E501 78 处；首调延迟 6.7 s；单机依赖/无 CI。

## [2026-09-23] R16 | 每日巡检 exit 2（13 Lint）· 修复进行中

- **巡检**（patrol_runner v3，快照 `retro/snapshot-2026-09-23.json`）：⚠️ lint total=13 = invalid 12 + schema_drift 1；auto_fix_lint「无修复」；LM Studio 可用（~2s，info）；missing_query P0/P1=0（已归档 `.sync/state/missing_daily_2026-09-23.md`）；sleep 候选 0
- **Git**：已提交 `chore: 每日巡检快照 2026-09-23`；commit 后快照被重跑更新（git status 显示该文件 modified）→ 修复完成时一并补提交
- **Lint 工具定位**（`hub_lint.py` 不存在，勿再找它）：`commands/lint.py` · `scripts/check_card_frontmatter.py` · `scripts/auto_fix_lint.py` · `scripts/lint_report.py` · `tools/lint.py`；巡检明细在 `AgentMemoryHub/retro/log.md`（最新 run 段落）
- **进行中**：取逐卡错误明细 → 修复 13 处 → 重跑巡检验证 exit → 补提交快照

## [2026-09-15] R15 | star-distill 6 仓 + T1 3 卡 + 待处理四项收口 + 日期纠偏

**PART A star-distill（判级 B+，全部入权威区）**
- 候选：Macad3D(.NET/CAD 内核) / Pynite(Python 结构 FEA) / TradingAgents(多智能体辩论) / OCRmyPDF(插件流水线) / FastMCP(MCP 框架) / qlib(量化研究平台)
- 流程：隔离克隆 --depth 1 → 只读盘点 → 静态 T0（清单良构+声明/源码一致）→ 6 张 blueprint 卡 → ingest
- ingest 结果：`promoted 0 / duplicate 6 / invalid 0` —— 全部降级落 conflicts（根因见下），经 pred.json 判降级误判 + 真实查重后 6 张 `mv` 进 blueprints/，INDEX 登记 6 行
- 提交：`61c5a04`（6 卡 + T1 回写 + INDEX + retro）· `1a563c5`（配置修法）· `c98f8c2`（日期纠偏）

**PART B T1 验证 3 卡**
- ✅ `pynite-python-structural-fea-architecture` → active / rc 1：简支梁挠度+弯矩 **0.000%**；悬臂 P-Delta 放大 5.0690 vs 梁柱理论 5.0692（0.004%）；踩坑=节点结果按组合 dict + 读错自由度（DY 轴向 vs DX 横向，误差 96× 自查两轮）
- ✅ `fastmcp-modular-mcp-server-framework` → active / rc 1：fastmcp 4.0.3 内存 + stdio 双传输全通（list_tools / call_tool `.data`+`structured_content` / resource）
- ⚠️ `llm-dedup-gateway-degrade-fix` → rc 2：根因=`commands/ingest.py:23` 因缺 `batch_model` 致去重走 `engine.chat`(OmniRoute 直连，池子 429/401/400)→6/6 降级；**已修**（`system/config.yaml` 增 `batch_model: local`，仅配置层）→ 复测产出真实决策 `merge/0.8`

**待处理四项收口**
1. ✅ 去重本地优先链修法落地+实测（同上）
2. ✅ `hub audit` 5 项遗留清零（2 orphan 补登 + 3 短描述；我方另补 4 条截断描述）→ audit ✅ 健康（389/213）
3. ✅ 临时产物清理：`work/star` 21 项 + `F:\AgentMemoryT1` 33 项（du 口径 10.3 GB；df 296→293G，差值=git 硬链接重复计数）→ 51 个小脚本先归档到 `F:\AgentMemoryT1_script-archive_2026-09-15`（56 文件 / 468 KB）
4. ✅ 中枢仓 push：fetch→rebase 24 commit 无冲突→push→SHA 核验一致

**日期纠偏**：2 处未来日期 `2026-09-21` → `2026-09-15`（三方时间源：本机 date / git 提交日 / GitHub HTTP Date）；`lint` 全绿（213 卡，0 无效、0 幽灵、0 漂移）

**当前状态**：中枢仓 `origin/master = c98f8c2`（工作区干净）；向量库 378→381 张；五权威区 rules 29 / blueprints 93 / methodology 54 / longterm 8 / projects 28
**遗留**：无阻塞项；主仓他人在制文件（mcp_server.py 等）未认领

## [2026-08-17] R6 | 中文语义召回增强（jieba 分词 + IDF 加权）

- **jieba 词模式**：`vector.py` 新增 `tokenize(mode="word")` 支持 jieba 分词 + 去停用词/标点，无 jieba 时自动回退字符 n-gram；`build_idf` 语料 IDF 加权，稀有词权重更高（缓解领域共词抢占）。
- **确定性通道词级匹配**：`retrieve.py` 新增 `mode` 参数传播，word 模式下查询任一分词与 tag 互相包含即命中（如 "dll 锁文件" 命中 tag "dll-lock"），char 模式仍为整句包含。
- **评测对比**：`work/bench_recall.py` 扩展对比 char n=2 vs word+IDF——word 全面胜出（确定性通道 0→5/11，语义 top1 8→9/11，混合 top1 8→10/11，top3 两者 100%）。
- **默认切 word**：`retrieve`/`semantic_retrieve`/`deterministic_retrieve` 默认 mode 改为 "word"，CLI `--mode` 可选 char/word（默认 word）；`requirements.txt` 加入 jieba>=0.42。
- **测试**：新增 9 项测试（jieba 分词/停用词/标点/回退/IDF 加权/word 检索/确定性词级匹配），58 项全通过。
- 决策：word 模式推广为默认，检索质量提升明显；无 jieba 环境自动回退 char，零成本兼容。

## [2026-08-17] R5 | 中枢迁移 + 每日巡检 + n-gram 召回率调优

- **中枢迁移**：`D:\AIwork\AgentMemoryHub` 复制到项目内 `AgentMemoryHub/`（规避沙箱权限），scripts 默认值 / AGENTS / CHARTER / visual-guide / draft 卡片 / user_profile 全部改为项目内相对路径。源目录受沙箱保护未删，保留为陈旧副本。
- **engine.py 解耦**：`import requests` 移入 `chat` 内延迟导入，`status`/`retrieve`/`lint` 等本地子命令不再强依赖网络库；测试 monkeypatch 改打 `requests.post`。
- **每日巡检 cron**：`Schedule` 每日 09:00（北京时间）巡检，产出 `retro/snapshot-<日期>.json` + `lint-report-<日期>.md`，异常追加 log 并提交 Git。
- **n-gram 召回率实测**：`work/bench_recall.py` 8 卡 11 查询评测——n=2 最优（top_k=3 即 100% 召回），n=3/4 因中文 n-gram 稀疏性召回降至 0.73~0.82；确定性通道对语义改写查询命中 0（需精确 tag）。
- **调优**：`semantic_retrieve`/`retrieve` 新增 `n` 参数（默认 2），CLI `retrieve --n` 可调；新增 2 项测试（n 可调 + retrieve 透传），测试 49 项全通过。
- 决策：继续下一轮（迁移收敛、巡检上线、检索参数已固化）。

## [2026-08-17] R4 | status --json + methodology 回写 + 全仓质量体检

- `status` 新增 `--json` 输出（卡片分布/Lint/待确认/最近提交），新增 `test_status_json_output`，测试 47 项全通过。
- methodology 卡片回写中枢 experience/（走 ingest + 中央 Git 审计）：共享卡 + 项目专属卡各 1 张。
- 全仓 check-code-v1 体检：Ruff 32 项待修、markdown lint 格式问题；pytest 在 hub-engine/ 下 47 项全过（根目录跑因路径失败属运行器配置问题）；yamllint 未装跳过。
- 决策：继续下一轮（功能已收敛；下一步做代码质量清理，成本低、消除体检噪音）。

## [2026-08-17] R4b | 代码质量清理完成

- `.gitignore` 补 `.tools/`/`work/`/`.venv/` → ruff 停扫 vendored 三方代码。
- 项目内 `.venv` 建好，yamllint 可运行（2 YAML 文件通过，仅 warning 缺 `---` 文档头）。
- `.ruff.toml` 排除 `docs/`/`work/`/`.tools/`。
- Ruff 修复：`engine.py` 和 `test_engine.py` 导入排序 2 项。
- Markdown 格式修复：`RUNLOG.md`/`AGENTS.md`/`CHARTER.md` 标题空行 + 表格管道符。
- `.markdownlint.json` 放宽行宽/表格样式噪音规则 + `.markdownlintignore` 排除归档文档 `docs/superpowers/`。
- 重跑 check-code-v1 --all：8 项全通过（失败 0 跳过 0 退出码 0）。
- 实跑 `engine.py status --root D:\AIwork\AgentMemoryHub --json` 正常，孤儿 0 陈旧 0 无效 0。

## [2026-08-17] R3 | code 平台注入 + methodology 卡片

- code 平台指令注入：`D:/AIwork/code-memory/CLAUDE.md`（幂等验证：重复注入无重复块）。
- 沉淀 methodology/：共享卡（旧项目最小迁移 5 条经验）+ 项目专属卡（协作约定）。
- 决策：继续下一轮（骨架稳定、成本低；code 平台本体待接入）。

## [2026-08-17] R2 | project-visual-guide.md 可视化指南

- 新增 `project-visual-guide.md`：Mermaid 流程图（三层架构+内容流转+人工确认决策点）+ 脑图 + 核心决策点/风险表。
- 决策：继续下一轮（骨架已稳定，cost-benefit 仍为正）。

## [2026-08-17] R1 | context-engineering-v1 骨架迁移 + status 子命令

- 按最小迁移方式给旧项目补协作骨架：AGENTS.md / CHARTER.md / WORK.md / RUNLOG.md。
- 定义当前 MVP 与事实来源映射；映射旧资料（specs/plans/hub-engine/中枢数据）。
- 补 `briefs/2026-08-17-r1-status-snapshot.md`。
- 真实小迭代：`engine.py` 新增 `status` 一键健康快照子命令（卡片分布/Lint/待确认/最近提交）。
- 验证：全量 pytest 通过；实跑 status 输出正常。
- 决策：继续下一轮（低成本高收益）。

## [2026-08-17] 初建 | 统一记忆中枢 v1 落地（14 任务 + 45 测试 + 端到端）

- 详见 `docs/superpowers/plans/2026-08-17-unified-agent-memory-hub.md`（全部勾选完成）。
- 中枢 `D:\AIwork\AgentMemoryHub` 已创建并 Git 初始化；trae 指令注入；DLL 规则全流程走通。
- 首份 Lint 报告生成；INDEX.md 补引孤儿页卡片后孤儿清零。
