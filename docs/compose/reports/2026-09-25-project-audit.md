# 项目全面分析 · 记忆中枢（AgentMemoryHub + hub-engine）

- **日期**：2026-09-25（本机时钟；注意 09-24→09-25 期间时钟自行跳了约 1 天，见 §4 Minor-7）
- **范围**：仓库 `20260817-Fan-Agent-Momory`（外层）+ 嵌套中枢仓 `AgentMemoryHub`（内层）
- **方法**：全部取自**当日实测**（可复现命令见 §6）；判断项与实测项分开标注
- **对照**：上一轮审计（2026-09-24）总分 **5.9/10**，最差项为「检索召回」与「代码卫生」

---

## 0. 执行摘要

**加权总分 7.7 / 10**（上次 5.9 → **+1.8**）。

一句话结论：**"可托付"已经成立，但"可长期维护"还没到位。**
门禁侧（测试 558 / 24 步巡检全覆盖 / 三条定时任务全绿 / 预算 24937 ≤ 30000）已达到很高的可信度；
检索侧从"基本失效"修到 **recall@5 100% / recall@1 86%**；
剩下的负债集中在**代码卫生规则集过松、硬编码与未纳管脚本、缺覆盖率度量、无 CI 与未推送备份**——都属于"不修不会立刻痛，但会持续放血"的类型。

---

## 1. 实测事实（§6 有命令）

### 1.1 规模

| 区域 | 文件 | 行数 | 是否版本控制 |
|:--|--:|--:|:--|
| `hub-engine/`（引擎） | 165 | 28,318 | ✅ tracked |
| ├ `scripts/` | 62 | 15,668 | ✅ |
| ├ `tests/` | 63 | 6,259 | ✅ |
| ├ `tools/` | 19 | 3,725 | ✅ |
| ├ `commands/` + `common/` + 其余 | 21 | 2,666 | ✅ |
| `scripts/`（仓根入口） | 8 | 830 | ✅ |
| `AgentMemoryHub/`（中枢内容） | 1,166 | — | ✅ 独立仓（嵌套 git） |
| `docs/` | 44 | 1,166(py 内) | ✅ |
| `work/`（草稿区） | 104 / 10.9 MB | 4,249 | ❌ **gitignore** |
| `.tools/` | 186 / 1.5 MB | 12,643 | ❌ **未跟踪** |

### 1.2 知识库（中枢）

| 目录 | 卡数 | 目录 | 卡数 |
|:--|--:|:--|--:|
| `experience/` | 224 | `projects/` | 20 |
| `blueprints/` | 121 | `longterm/` | 8 |
| `methodology/` | 61 | `notes/` | **0（空）** |
| `rules/` | 35 | `archive/` | **0（空）** |
| **合计** | **469** | 向量库条目 | **447** |

向量覆盖缺口 **22 张 = 全部为 `status: deprecated`(14) / `archived`(23) 的子集**（抽查 6 张全部命中该规则）⇒ **不是缺陷**，是设计上不索引失效卡。
状态分布：`active 243 / 无字段 131 / reference 73 / candidate 24 / archived 23 / deprecated 14`（无 `status` 字段的按解析默认 `active`）。

### 1.3 质量门禁（当日全绿）

| 门禁 | 实测 |
|:--|:--|
| 全量测试 | **558 passed / 4 skipped / 0 failed**（79.9s，`.venv` 解释器） |
| 测试:源码 | 6,259 : 22,059 ≈ **28%** |
| 巡检（24 步） | `scripts/run_patrol.cmd` **exit 0**（198s），24 步全绿 |
| lint | `orphans=0 ghosts=0 stale=0 invalid=0` |
| ruff | 全项目通过 |
| 启动链预算 | **24,937 / 30,000**（AGENTS 1416 · CHARTER 784 · WORK 4689 · INDEX 18048；分项帽均未破） |
| 向量回归 | fusion hit ratio **100%** |
| 检索召回（22 金标准） | **word 100% / recall@1 86%**；char 100% / 86% |
| 定时任务 | DailyPatrol / NightlyConsolidate / SecretSentry **`LastTaskResult=0`** |
| 凭证哨兵 | 高危 0 / 低危 0 |
| 健康评分 | 总分 **92/100**（卡片 100 · 技能 100 · 飞轮 100 · **本地 LLM 60**） |

### 1.4 自动化与运维

- **无 CI**（无 `.github`）：全部自动化 = **本机 Windows 计划任务**（三条）+ pre-commit 钩子
- 提交活跃度：近 30 天外层 204 笔（峰值 09-23 共 28 笔/日）；中枢仓近 7 天 104 笔
- **未推送**：外层 **10 笔**（origin 停在 09-24 18:38）、中枢 **4 笔** ⇒ 备份缺口
- 提交署名：近 30 天 `Codex Local` **143/204 = 70%**（代理留下的局部 git 身份，**本次已改回 `FanFan`**，既往历史不重写）

---

## 2. 分维度评分

| # | 维度 | 分 | 权重 | 依据（实测） | 主要扣分 |
|:--|:--|--:|--:|:--|:--|
| 1 | 架构与分层 | **8.5** | 0.12 | L0 常驻 24.9K/30K 有测试看守；L1 四型路由由 `task_tier.py` 单一事实源；L2 检索 | 24 个函数 >100 行；`patrol_runner.py` 1,490 行 |
| 2 | 检索质量 | **8.0** | 0.15 | recall@5 **100%**、@1 **86%**（22 金标准）；融合有冠军保底+通道加权 | 金标准集仅 22 条；首调延迟 0.38–2.09s；char 模式无独立金标准 |
| 3 | 测试与门禁 | **8.5** | 0.15 | 558 测试；24/24 巡检步骤有判定契约；三道提交门禁 + 三条定时任务 lastResult=0 | **无覆盖率工具**（pytest-cov 未装）；无 CI 交叉验证 |
| 4 | 代码卫生 | **6.0** | 0.12 | ruff 全绿、TODO 仅 6 处、无 `except: pass` 泛滥 | **`.ruff.toml` 只设 line-length**（无 B/SIM/UP/C90）；**22 文件 47 处硬编码个人绝对路径**；`lint_report.py` 无 argparse |
| 5 | 文档与知识一致性 | **7.5** | 0.11 | INDEX 248/245 条 ✅ 健康；L0 预算三项帽内；审计器/薄卡扫描/定位性基准齐备 | 5 处 L0 路径用简写（从仓根不可解析）；`notes/`、`archive/` 空目录；3 对高相似卡未裁定 |
| 6 | 运维与自动化 | **8.5** | 0.12 | 夜间链路 4/4 步 exit=0；巡检 198s；哨兵 0/0；快照归档幂等 | **单点依赖**：LM Studio(F: 盘 temp) + 网关 20128 + 本机任务；LLM 响应 2.0s（60 分） |
| 7 | 安全与凭证 | **8.5** | 0.12 | 哨兵 0/0；`provider_keys.yaml`/`vector.db` 均在 .gitignore；`safe_patch` 唯一渠道有 CHARTER 契约 + 测试引用 | 写锁是运行时产物（AGENTS 引用不可解析）；历史空 DACL 事故（已留档） |
| 8 | 可维护性/可移植性 | **6.0** | 0.11 | 关键路径自解析（`run_patrol.cmd` 模式已立） | 硬编码路径 47 处；`work/`(4.2K 行)+`.tools/`(12.6K 行) 未纳管；70% 提交署名失真 |

**加权合计 = 7.7 / 10**

---

## 3. 关键发现（按严重度）

### Critical

**无。** 所有门禁绿、无凭证泄漏、无数据丢失风险。

### Important（建议 1–2 周内处理）

| # | 发现 | 证据 | 风险 |
|:--|:--|:--|:--|
| I-1 | **lint 规则集形同虚设**：`.ruff.toml` 只有 `line-length=120` + `extend-exclude`，未选任何规则族（ruff 默认仅 E4/E7/E9/F） | `.ruff.toml` 全文 4 行 | 拼写错误、未用导入之外的**真实缺陷类**（bugbear B、复杂度过高 C901、过期写法 UP、简化 SIM）无护栏 |
| I-2 | **22 个 tracked `.py` 含 47 处个人绝对路径**（`C:\Users\Fan-SJSS\...`、`D:/AIwork\...`）：`mavis_hub_bridge.py`(7)、`reclassify.py`(7)、`bootstrap_hub.py`(4)、`mcp_healthcheck.py`(4)、`hub_mcp_launcher.py`(3)、`hub_orchestrator.py`(3)… | 正则扫描 tracked `*.py` | 与刚修完的 P1-1 同一缺陷类：换机/移 worktree 即静默失效（且这些是**启动类**脚本） |
| I-3 | **无覆盖率度量**：pytest-cov / coverage 未安装 | `python -c "import pytest_cov"` 失败 | 28% 测试行数只是代理指标；"哪些核心路径无测试"无从知晓 |
| I-4 | ~~仍在用的能力放在未纳管的 `work/`~~ | **已修（2026-09-25）**：`audit_dead_modules.py` 迁入 `hub-engine/scripts/`（V2.0 路径自解析）；`bench_recall.py` 与 T1 一次性脚本归档至 `work/_archive/oneoffs-20260925/`（能力已被 `recall_regression` 取代，T1 重跑靠仓内命令）；留档 `docs/compose/cleanup/2026-09-25-dead-scripts-and-dashboard.md` §3 |
| I-5 | **单点依赖叠加**：本地 LLM（且 `F:\lmstudio-home\.internal\temp` 一旦缺失 → 全模型 400）+ 网关 `127.0.0.1:20128` + 本机计划任务 + 无 CI | 09-24 实盘故障复现；`LastTaskResult` 全绿但常驻任务只在 **1 台机器**上 | 机器/模型不可用时，夜间摘要、蒸馏、向量更新**静默降级**（虽有 exit≠0，但没人看日志就不知道） |
| I-6 | **备份缺口**：外层 **10 笔**、中枢 **4 笔**未推送 origin | `git rev-list --count origin/master..master` = 10；中枢 = 4 | 本地磁盘故障即失（中枢是"唯一事实源"） |

### Minor

| # | 发现 | 说明 |
|:--|:--|:--|
| M-1 | `hub-engine/scripts/lint_report.py` **没有 argparse** | 传 `--root` 会被当成路径，**在 `hub-engine/` 下创建名为 `--root` 的目录树**（本次实测复现，已清理） |
| M-2 | 超长函数：**1,359 个函数中 24 个 >100 行** | `run_patrol` 319、`auto_flywheel.run` 250、`sync.ingest` 248、`build_timeline_html` 231、`_cmd_daily_report` 212 |
| M-3 | L0 文档 5 处路径用简写、从仓根不可解析 | `engine.py`、`tools/task_tier.py`、`scripts/secret_sentry.py`、`local_summary.py`、`AgentMemoryHub/.sync/locks/writer.lock`（运行时产物） |
| M-4 | `notes/`、`archive/` 目录为空但仍在 INDEX 使用约定里列出 | 0 张卡 |
| M-5 | 卡片去重债：**3 对高相似（0.90–0.97）** | `chrome-proxy-clash-urnetwork-killswitch-conflict{,-2026-09-05}`、`pluginhub-date-range-picker-v1.1/-v1.2`、`cross-repo-index-commit` ↔ `ingest-probe-a`（自动去重脚本已被禁，须人工逐对看） |
| M-6 | 检索首调延迟 **0.38–2.09 s**（同进程 3 次均值） | 交互路径体感差；有 IDF/index 缓存，但冷启动与向量通道开销仍在 |
| M-7 | 本机时钟在会话中途 **+1 天**（09-24 19:07 → 09-25 20:39） | 影响一切"按日期取数"的判据（T1 的 ≥10 天窗口、快照幂等、metrics）；本次 T2/P2 的日期以此为准 |
| M-8 | 提交署名失真：近 30 天 70% 是 `Codex Local` | 已改回 FanFan（仅影响后续） |
| M-9 | 仪表盘存在两套：根级 `hub-health.html`/`flywheel-timeline.html`（**活**，由 tracked 脚本生成）+ `work/dashboard/`（草稿，**本次已归档**） | 若草稿路线复活会再分叉 |
| M-10 | **markdownlint 配了但没挂门禁**（`.markdownlint.json` 存在，pre-commit / 巡检都不跑它）；全仓现有 **7 处违规**，集中在 2 份历史文档（`cleanup/2026-09-24-*`、`plans/2026-09-23-slim-rules-gates.md`），新文档 0 违规 | 建议挂为门禁 + 对 2 份历史文档加基线豁免（不修改历史记录） |

---

## 4. 整改建议

### P0（无）

没有任何阻断项；现有门禁可以继续放心依赖。

### P1 —— 建议优先（合计约 **3–5 天**）

| # | 动作 | 估时 | 收益 | 备注 |
|:--|:--|:--|:--|:--|
| P1-a | **ruff 规则集升级**：`select = ["E","F","W","I","UP","B","SIM","C901"]`（`mccabe.max-complexity=15`），先跑一次全量统计把违规**按文件**列入 `per-file-ignores` 基线，再逐批清 | 0.5–1 天 | 补齐真实缺陷类护栏（含 M-2 的复杂度） | 与 I-1 直接对应；建议同时把 `ruff format --check` 纳入巡检（已纳入 pre-commit） |
| P1-b | **装 pytest-cov 并立覆盖率基线**：`--cov=hub-engine --cov-report=term-missing`，把**核心路径**（`tools/retrieve.py`、`sync.py`、`scripts/patrol_runner.py`）单列阈值 | 0.5 天 | 从"测试行数代理"升级为真度量 | 对应 I-3；先立基线不加硬门禁，避免假红 |
| P1-c | **硬编码路径清零 + 加护栏测试**：22 文件 47 处改为 `Path(__file__).resolve().parents[n]` 自解析（或 env 覆盖，参照 `run_patrol.cmd`/`nightly_consolidate.cmd`）；新增测试禁止 tracked `.py` 出现 `C:\Users\`/`D:/AIwork` | 1 天 | 消除换机失效类缺陷 | 对应 I-2；**优先 `bootstrap_hub.py`/`hub_mcp_launcher.py`/`mcp_healthcheck.py` 三个启动链文件** |
| P1-d | ~~把 `work/` 仍在用的脚本迁入仓库~~ | **已完成（2026-09-25）**：审计器迁入 + 5 个一次性脚本归档（见 cleanup 留档 §3） | 0.5 天 | 消除"文档引用未跟踪文件"的悬空风险 | 对应 I-4 |
| P1-e | **推送补上 + 备份策略**：外层 10 笔、中枢 4 笔推 origin；给中枢加"每日推送"或纳入夜间任务（失败即非零） | 0.5 天 | 唯一事实源离开单机 | 对应 I-6；推送需你点头（本分析未擅自执行） |
| P1-f | **单点降级实测**：LM Studio 停掉时跑一遍"检索（向量通道退化）+ 夜间链路"，确认降级路径是**可诊断**而非静默；给夜间任务加"`.internal/temp` 不存在则建"的一行兜底 | 0.5 天 | 把 09-24 那次"全模型 400"变成自愈 | 对应 I-5；经验卡已入库，兜底尚未落代码 |

### P2 —— 可分批（合计约 **1 天**）

| # | 动作 | 估时 |
|:--|:--|:--|
| P2-a | `lint_report.py` 加 argparse（`--root`）+ 全仓 CLI 参数一致性抽查 | 2 h |
| P2-b | 拆 `run_patrol`(319) / `auto_flywheel.run`(250) / `sync.ingest`(248)：步骤注册表化 + 阶段函数化 | 0.5 天 |
| P2-c | 3 对高相似卡逐对人工裁定（收敛/转发/不动的理由 + sha256） | 1 h |
| P2-d | WORK.md 5 处简写路径写全；`notes/`/`archive/` 空目录决定去留 | 0.5 h |
| P2-e | 检索延迟剖析：`retrieve` 首次调用的索引/向量开销，评估"预热 + 进程内缓存" | 2 h（剖析） |
| P2-f | **markdownlint 挂门禁**（pre-commit 或巡检步骤）+ 对 2 份历史文档加基线豁免（新文档已 0 违规） | 1 h |

---

## 5. 可考虑重构的部分（需你拍板，风险与收益都较大）

| 候选项 | 现状 | 建议 | 风险 |
|:--|:--|:--|:--|
| **A. 巡检器拆分** | `patrol_runner.py` 1,490 行 / `run_patrol` 319 行 / 24 步内联在同一个函数里 | 抽 `steps/` 包 + 注册表（本次测试已用"注册名"做覆盖守门，拆完正好复用） | 低-中：行为等价需用现有 24 步契约测试兜底（已具备） |
| **B. 仪表盘单一化** | 根级活仪表盘（`hub_health.py` 549 + `flywheel_runlog.py` ≈900 行）+ `hub_dashboard_collect.py` 1,214 + `hub_dashboard_server.py` 692 行；`work/` 下还有两代草稿（已归档） | 定"一套"：保留根级静态 HTML 路线，`hub_dashboard_*` 若无人访问则归档其入口 | 中：需确认你是否还在手动打开某个仪表盘 |
| **C. `.tools/` 去留** | 12,643 行未跟踪（疑似第三方/自建工具集） | 若在用 → 收敛进 `hub-engine/vendor/` 并注明来源与许可证；若弃 → 归档 | 低：不影响 tracked 代码 |
| **D. `work/` 整体定位** | 4.2K 行草稿 + 10.9 MB | 定为"只读归档区"：仍在用的迁出（P1-d），其余打包 `work/_archive/` | 低 |

---

## 6. 复现命令（本次所有数字的来源）

```bash
# 规模 / 结构
git ls-files 'hub-engine/*.py' | ...                      # 分模块行数
python -m scripts.audit_dead_modules                         # 零引用模块（需人工复查：本工具会假阳性）

# 质量门禁
cd hub-engine && ../.venv/Scripts/python.exe -m pytest -q  # 558 passed / 4 skipped
../.venv/Scripts/python.exe -m ruff check .                # 全绿
../.venv/Scripts/python.exe -m scripts.startup_budget       # 24937 / 30000

# 检索
../.venv/Scripts/python.exe -m scripts.recall_regression    # word 100% / @1 86%
../.venv/Scripts/python.exe -m scripts.index_locatability_bench --rev 68088fa^  # 17/20 → 18/20

# 巡检（24 步，等价定时任务）
cmd /c scripts\run_patrol.cmd                              # exit 0（198s）

# 中枢
../.venv/Scripts/python.exe hub-engine/engine.py status --root AgentMemoryHub --json
../.venv/Scripts/python.exe hub-engine/scripts/thin_card_scan.py --root AgentMemoryHub
../.venv/Scripts/python.exe hub-engine/scripts/audit_index.py --root AgentMemoryHub   # 248/245 ✅

# 缺口扫描
# 硬编码路径：rg -n 'C:[\\/]Users[\\/]Fan-SJSS|D:[\\/]AIwork' $(git ls-files '*.py')
# 未推送：  git rev-list --count origin/master..master  /  git -C AgentMemoryHub rev-list --count '@{u}..HEAD'
```

---

## 7. 与上一轮审计（2026-09-24，5.9/10）对比

| 维度 | 上次 | 现在 | 变化原因 |
|:--|--:|--:|:--|
| 检索召回 | 差（recall@1 5%） | **8.0** | P0 修"部分命中即短路"→@1 80%，本轮再修"冠军保底+通道加权"→@1 86%、@5 100%；新增占位率指标与 2 条蓝图池守卫 |
| 代码卫生 | 差 | **6.0** | 清理死文件/夹具（1.6 GB）、补 73 例契约测试；**但规则集与硬编码未动**（仍是最差项） |
| 门禁可信度 | 中 | **8.5** | 巡检 `--fail-below 0.8` 补回；24/24 步有测试；三条定时任务 lastResult=0 |
| 运维 | 中 | **8.5** | 夜间链路修通（`max_tokens` 预算 + 端点回退 + 口径收敛）；单点依赖未解 |
| **加权总分** | **5.9** | **7.7** | — |

---

## 8. 结论

1. **不要再加"层"**：L0/L1/L2 与四型路由已足够，预算还有 5K 余量但**边际收益低**；接下来的收益全在**卫生与度量**（P1-a/b/c）。
2. **优先顺序**：`P1-c（硬编码清零）` → `P1-a（ruff 规则集）` → `P1-b（覆盖率基线）` → `P1-d（work 迁入）` → `P1-e（推送）` → `P1-f（单点降级）`。
3. **重构只做 A（巡检器拆分）**：它有现成的 24 步契约测试兜底，风险最低、收益最直接；B/C/D 都先等你一句"还在用吗"。
4. 分析本身暴露了一条流程事实：**"文档化的命令"必须要么在版本控制内、要么不复存在** —— I-4 与 M-3 是同一个病。
