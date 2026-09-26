# 项目全面分析 · 记忆中枢（AgentMemoryHub + hub-engine）

- **日期**：2026-09-25（本机时钟；注意 09-24→09-25 期间时钟自行跳了约 1 天，见 §4 Minor-7）
- **范围**：仓库 `20260817-Fan-Agent-Momory`（外层）+ 嵌套中枢仓 `AgentMemoryHub`（内层）
- **方法**：全部取自**当日实测**（可复现命令见 §6）；判断项与实测项分开标注
- **对照**：上一轮审计（2026-09-24）总分 **5.9/10**，最差项为「检索召回」与「代码卫生」

---

## 0. 执行摘要

**加权总分 7.7 / 10**（上次 5.9 → **+1.8**）。

> ⚠️ **本报告已迭两轮：首评 5.9 → 整改前 7.7（§2）→ 第一轮重评 8.5（§10）→ 第二轮重评 8.7（§11）**。
> **当前有效总分＝§11 的 8.7/10**；§2 与 §10 保留为各时点快照，不再代表现状。

一句话结论：**“可托付”已经成立，但“可长期维护”还没到位。**

> **2026-09-25 当日后续**：§9 记录了六个 Important（I-1…I-6）的收口——规则集、硬编码、覆盖率、
> `work/` 纳管、单点自愈、推送备份全部完成；本报告的 P1 清单已清空，余项降为 P2 与需拍板的重构。
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
| P2-a | `lint_report.py` 加 argparse（`--root`）+ 全仓 CLI 参数一致性抽查 | ✅ **已完成**（`b8e8fa4`） | 2 h |
| P2-b | 拆 `run_patrol`(319) / `auto_flywheel.run`(250) / `sync.ingest`(248) | ✅ **2/3 完成**：`run_patrol` 319→**57**（`63c42d1`，抽 9 个 `_stage_*`）、`auto_flywheel.run` 220→**109**（`ab9071b`，抽掉两份 55 行重复块）；⚠️ **`sync.ingest` 229 行未动**（写入路径 + 单写者/判重/冲突区，拆分需先补 fixture 级测试 ⇒ 高风险低收益，待专项） | 0.5 天 |
| P2-c | 3 对高相似卡逐对人工裁定 | ✅ **已完成**：前两对**早已裁定**（`chrome-proxy-*` 与 `ingest-probe-a` 均已 `status: deprecated` + `superseded_by`）；pluginhub 对是真缺口 —— v1.1 的 3 条独有教训（F811 / `Optional[T]` vs `T\|None` / I001）已并入 v1.2，v1.1 转 deprecated（hub `769df1c`） | 1 h |
| P2-d | WORK.md 路径写全；`notes/`、`archive/` 空目录定去留 | ✅ 路径已写全（`7cdd03a`）；`notes/` 保留（INDEX 使用约定声明）、`archive/` 保留（本次归档仪表盘 v4 就用了它） | 0.5 h |
| P2-e | 检索延迟剖析 | ✅ **已完成且顺手提速 2.5×**（`049d283`）：剖出「缓存命中的 `_index()` 仍要 60 ms」的根因（每文件 `Path.resolve()`），改 `os.scandir` + `abspath` → 稳态 **340 → 138 ms**；首调 4.9 s 属进程级一次性，未做预热 | 2 h |
| P2-f | markdownlint 挂门禁 | ✅ **已完成**（`b8e8fa4`）：pre-commit 第 0.8 道（exit 3），历史文档基线豁免；冒烟验证「违规被拦 / 修好放行」 | 1 h |

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
4. 分析本身暴露了一条流程事实：**“文档化的命令”必须要么在版本控制内、要么不复存在** —— I-4 与 M-3 是同一个病。

---

## 9. 整改执行记录（2026-09-25 当日完成）

六个 Important 全部收口（P1-a…P1-f）；每项都有测试或实测兜底：

| 项 | 动作 | 结果 |
|:--|:--|:--|
| **I-1**（P1-a） | `select = E4/E7/E9/F/W/I/UP/B/SIM/C901`；行宽 120 **显式钉死**（此前 lint 与 format 口径不一致）；E501/C901 按文件登记基线（81/16 处，可度量可递减） | `ruff check` 新规则集下**零违规**；手修 8 处 + 自动修 24 处 + 109 文件按 120 重排（测试全绿） |
| **I-2**（P1-c） | 57 处个人/本机绝对路径 → `__file__` 自解析 / `Path.home()` / 单点 `external_path()`（env → hub.config.yaml → 内置默认） | 新增护栏测试：首跑多揪出 **10 处**（含嵌套仓里扫不到的 9 处）；白名单仅 2 条且带“确有该串”校验 |
| **I-3**（P1-b） | 装 pytest-cov；`[tool.coverage.*]` 入库；一行命令可复现 | 基线 **生产代码 40.0%**（含 tests 55.1% 属虚高）；0% 重灾区：`flywheel.py` 597 语句等 8 个 |
| **I-4**（P1-d） | `audit_dead_modules.py` **迁入仓库**（V2.0，补“有假阳性”实测警告）；`bench_recall` + 4 个 T1 一次性脚本归档 | 文档不再引用 gitignore 区文件；`RUNLOG.md` 的历史引用保留不改 |
| **I-5**（P1-f） | `local_summary` **自愈** `.internal\temp` 缺失（解析报错 → 建回 → 重试一次；严格只认 `lmstudio-chat-template*` 形态） | +4 例测试；下次该故障从“每晚静默为空”变为自动恢复 |
| **I-6**（P1-e） | 外层与中枢**均推送** origin（中枢 rebase 了 `skillhub-bot` 的 1 笔自动同步） | 两仓 ahead = 0；中枢 rebase 后 lint 245 卡 0 问题 |

**仍然开放**（不是 Important）：

- **`sync.py::ingest` 拆分**（229 行）：它是中枢**写入路径**（单写者 + 判重 + 冲突区），
  拆分需先补 fixture 级测试再动刀 ⇒ 高风险低收益，**本次不碰**；`C901` 基线里为它留着记录。
- **重构候选 A–D**：✅ 已全部落地 —— A 巡检器拆分（`63c42d1`）、B 仪表盘单一化（`235e2eb`）、
  C `.tools/` 删除（+`node_modules/`，合计释放 ≈12.8 MB，留档 `cleanup/2026-09-25-legacy-files-and-work-disposition.md`）、
  D `work/` 定为只读归档区（97 件归档，根目录只剩 `_archive/`）。
- **T1**（量「规则遵循/返工」）：时间门 **≥2026-10-07**，未到点。

---

## 10. 重评（2026-09-25 整改后）

同一口径、同一权重、全部重新实测（命令同 §6，另：覆盖率用 `pytest --cov=. --cov-report=json:...` 归并分区）。

### 10.1 维度得分对比

| # | 维度 | 权重 | 改前 | **改后** | 改后的主要依据 | 仍扣在哪 |
|:--|:--|--:|--:|--:|:--|:--|
| 1 | 架构与分层 | 0.12 | 8.5 | **8.7** | `run_patrol` 319→57（编排 + 9 个 `_stage_*`）· `ingest` 229→54 · 提交门禁 3→**4 道** | 仍有 15 个函数 >100 行（`build_timeline_html` 225 / `_cmd_daily_report` 196 / `flywheel.py` 两个 main） |
| 2 | 检索质量 | 0.15 | 8.0 | **8.5** | recall@5 **100%** / @1 **86%**（22 金标准）· 稳态延迟 **340→138 ms** · 新增蓝图占位率指标 | 金标准集偏小（22 条）· 首调 4.9 s（进程级一次性，未预热） |
| 3 | 测试与门禁 | 0.15 | 8.5 | **9.0** | **579 passed / 4 skipped**（+21）· **覆盖率 40.0%→43.8%** · markdownlint 挂第 0.8 道 · 24 步巡检契约 · `ingest` 分支级夹具 14 例 | `scripts/` 覆盖仍低（**26.9%**）· 无 CI（全部本机任务） |
| 4 | 代码卫生 | 0.12 | 6.0 | **8.0** | 规则族启用（B/SIM/UP/C901）+ 行宽统一 → **新规则集下 0 违规** · 硬编码路径 **57→0**（带护栏）· 死代码审计器入仓 · 规则债 E501/C901 **81/16 → 79/11** | 79 处内容型长行 + 11 个 >15 复杂度函数仍在按文件基线里 |
| 5 | 文档与知识一致性 | 0.11 | 7.5 | **8.3** | L0 路径全部可解析 · 3 对相似卡裁定完毕（pluginhub 先并入教训再 deprecate）· cleanup/audit/archive 三处留档齐 · markdownlint 0 违规 | `docs/` 与中枢仍是两套平行文档体系（历史遗留） |
| 6 | 运维与自动化 | 0.12 | 8.5 | **8.8** | 夜间链路自愈 LM Studio temp 缺失 · 三任务 `LastTaskResult=0` · 快照幂等 · **两仓 ahead=0** | 仍依赖本机单点；`local_llm_slow` 报警持续（响应 ~2 s） |
| 7 | 安全与凭证 | 0.12 | 8.5 | **8.6** | 哨兵 0/0 · `safe_patch` 唯一渠道有契约+测试 · 写锁/凭证路径写入 WORK 注意事项 | 凭证体系本轮未动（提升来自文档化） |
| 8 | 可维护性/可移植性 | 0.11 | 6.0 | **8.2** | 硬编码 0 + 护栏 · `work/` 定为只读归档区（135 项归位）· 删遗留 ≈12.8 MB · 提交署名恢复 `FanFan` | 仓内仍 35.7K 行代码 + 6.6 MB 引擎，体量本身即成本 |

**加权总分 7.7 → 8.5 / 10**（↑0.8）；扣分最重的两个 6.0（代码卫生、可维护性）升到 **8.0 / 8.2**。

### 10.2 实测数据对比

| 指标 | 改前 | 改后 |
|:--|--:|--:|
| 测试 | 558 passed | **579 passed / 4 skipped** |
| 覆盖率（生产代码） | 40.0%（基线初立） | **43.8%**（tools 84.9 · common 90.8 · 顶层 67.6 · commands 62.9 · **scripts 26.9**） |
| ruff 规则集 | 仅默认（E4/E7/E9/F） | **E4/E7/E9/F/W/I/UP/B/SIM/C901** + 行宽 120 |
| ruff 违规 | 规则未启用（不可比） | **0**（E501 79 / C901 11 在按文件基线上） |
| 硬编码个人路径 | **57 处 / 22 文件** | **0**（+ 护栏测试，白名单仅 2 条且防腐化） |
| 检索稳态延迟 | ~340 ms | **~138 ms** |
| 函数 >100 行 | 24 个 | 15 个（§11 后为 14） |
| C901 超阈函数（max 15） | 16 个 | **11 个**（§11 后降到 8；已拆 `run_patrol` / `auto_flywheel.run` / `sync.ingest`） |
| 死代码审计 | 仅 `work/` 下临时脚本（gitignore） | 工具入仓（`python -m scripts.audit_dead_modules`） |
| 巡检 | 24 步 exit 0（199 s） | **24 步 exit 0**（225 s；pytest 变长因用例增多） |
| 健康分 | 92/100 | 92/100（唯一扣分仍是本地 LLM 响应慢） |
| 未推送提交 | 外层 10 / 中枢 4 | **0 / 0** |
| 磁盘 | — | 释放 ≈**12.8 MB**（`node_modules` 11.33 + `.tools` 1.5） |

### 10.3 为何不是更高（诚实说明）

1. **覆盖率 43.8%**：`scripts/` 7,250 语句仅 26.9%（大量 CLI 包装与一次性迁移脚本）——要上 60% 得逐个补端到端用例。
2. **规则债未尽**：79 处长行 + 11 处高复杂度函数仍在基线里：**已知、可度量，但没还完**。
3. **单机依赖未解**：LM Studio / 计划任务 / 无 CI —— 属设计选择，但可用性确实绑在一台机器上。
4. **本地 LLM 响应 ~2 s**：`llm_health` 恒 60 分，是总分里唯一持续扣分项。

### 10.4 重评后的下一刀（已执行）

**COV（已完成）**：`scripts/` **26.9% → 41.4%**（超 40% 目标），TOTAL 43.8% → **53.7%**；
+64 例测试（4 个新文件），过程中**搞出 3 个真 bug**（日报空 `_gap` 崩 · 健康分“未知当满分” ·
`card_tags` 块写法只读首个 tag）——均已修 + 回归测试。

**SPLIT2（部分完成）**：C901 超阈函数 **16 → 8**（已拆 6 个，前件均为“已有测试”）。
剩下的 8 个集中在 CLI `main()` 与报表函数，**属线性选项处理，拆分收益低（待有测试后再动）**，
已按文件名+行号登记在 `hub-engine/pyproject.toml` 的 C901 基线里：
`flywheel._cmd_daily_report`(27) · `auto_fix_lint.run_fix`(20) · `commands/status.print_snapshot_report`(19) ·
`post_ingest_hook.main`(19) · `tools/platform_bridge.push`(18) · `audit_index.audit`(17) ·
`rule_following_timeseries.main`(17) · `commands/status.compute_snapshot_health_scores`(16)。

---

## 11. 正式重评（第二轮 · COV + SPLIT2 收口后）

**同 §10 口径**：同权重、同判据，**全部重新实测**（命令同 §6；覆盖率用
`pytest --cov=. --cov-report=json:…` 按目录归并；召回用 `python -m scripts.recall_regression`；
延迟用同进程 3 次复测；规模/规则债务用 AST 与 ruff 实测）。

### 11.1 维度得分（首评 → §10 → 本轮）

| # | 维度 | 权重 | 首评 | §10 | **本轮** | 本轮主要依据 | 仍扣在哪 |
|:--|:--|--:|--:|--:|--:|:--|:--|
| 1 | 架构与分层 | 0.12 | 8.5 | 8.7 | **8.8** | C901 超阈 **16→8**（本轮再拆 3 个：`print_report`/`check_alerts`/`_format_6panel_section`，前件均为已覆盖）· >100 行函数 15→**14** · `run_patrol` 编排层稳定 | `patrol_runner.py` 仍 **1,597 行**（未拆 `steps/` 包）· 14 个 >100 行函数（`build_timeline_html` 225） |
| 2 | 检索质量 | 0.15 | 8.0 | 8.5 | **8.6** | `card_tags` 块写法解析 bug 修复 ⇒ T2「摘要+tags」变体数据此前被**系统性低估**（度量可信度提升）· word/char 同口径列蓝图占位（9.0% / 12.0%）· 召回持平 **100% / 86%** | 金标准仍 **22 条** · **首调 6.7 s**（比 §10 记录的 4.9 s 更长：语料 469 → 729 md）· char 模式无独立金标准 |
| 3 | 测试与门禁 | 0.15 | 8.5 | 9.0 | **9.3** | **643 passed / 4 skipped**（+64）· 覆盖率 **43.8% → 53.9%**、`scripts/` **26.9% → 41.7%**（跨过 40% 目标）· **新测试实测揪出 3 个真 bug**（测试“有效性”而非仅数量） | 仍无 CI（全是本机任务）· 低点仍是 `scripts/` 41.7% 与 `commands/` 62.9% |
| 4 | 代码卫生 | 0.12 | 6.0 | 8.0 | **8.3** | ruff 0 违规 · C901 基线实欠 **11 → 8** · TODO/FIXME **6 → 1**（仅模板骨架）· 硬编码生产代码 0（白名单 2 处 + 护栏）· bare `except:` 0 · 死代码审计器入仓 | E501 仍 **78** 处内容型长行 + 8 个 C901 留在 per-file 基线（已知、可度量、未还完） |
| 5 | 文档与知识一致性 | 0.11 | 7.5 | 8.3 | **8.4** | markdownlint **0** 违规 · 审计/cleanup/archive 三类留档齐 · INDEX 18,048 字符（帽内）· 本轮审计§11 与 WORK/RUNLOG 同步回写 | **6 张卡缺 `status`**（本轮新发现，见 11.4）· `docs/` 与中枢仍是两套平行体系 |
| 6 | 运维与自动化 | 0.12 | 8.5 | 8.8 | **8.9** | 本轮修掉两个**故障类真缺陷**：日报空 `_gap` **KeyError 直接崩**、健康分把“LLM 未知”当满分（虚高总分）· 巡检 24 步 **exit 0**（239 s）· 健康 **92/100** · 三任务 `LastTaskResult=0` · 两仓 ahead=0 | 单机单点未解（LM Studio / 网关 / 计划任务）· `local_llm_slow` 持续（响应 ~2 s） |
| 7 | 安全与凭证 | 0.12 | 8.5 | 8.6 | **8.6** | 本轮无新增风险：哨兵 **0/0** · `safe_patch` 唯一渠道契约+测试 · `provider_keys.yaml`/`vector.db` 均 gitignore | 凭证体系本轮未动（提升仍来自文档化） |
| 8 | 可维护性/可移植性 | 0.11 | 6.0 | 8.2 | **8.4** | 3 个真 bug 修复 + C901 再降 ⇒ 维护风险实质下降 · 本会话 31 笔提交署名 `FanFan` · 硬编码 0 · `work/` 维持只读归档（本轮临时物已清） | 近 30 天署名仍 **64% 是历史 `Codex Local`**（143/225，不重写历史）· 体量成本（`.git` 287 MB / `work/` 11.2 MB） |

**加权总分 8.5 → 8.7 / 10**（↑0.2；首评 5.9 → 累计 **+2.8**）。
最高分仍是测试与门禁（**9.3**）；最低分仍是代码卫生（**8.3**）与文档一致性（**8.4**）。

### 11.2 实测数据（§6 同口径）

| 指标 | 首评 | §10 | **本轮** |
|:--|--:|--:|--:|
| 测试 | 558 passed | 579 passed / 4 skipped | **643 passed / 4 skipped** |
| 覆盖率（TOTAL） | 40.0%（基线初立） | 43.8% | **53.9%**（5,821/10,802） |
| 覆盖率（分模块） | 仅 TOTAL | tools 84.9 / common 90.8 / scripts 26.9 | tools **85.5** / common **91.3** / 顶层 **67.6** / commands **62.9** / **scripts 41.7** |
| C901 超阈（max 15） | 16 个 | 11 个 | **8 个** |
| 函数 >100 行 / 总函数数 | 24 / 1,359 | 15 | **14 / 701**（不含 tests） |
| E501 长行 | 81 | 79 | **78** |
| TODO/FIXME | 6 | 6 | **1** |
| 硬编码个人路径（生产代码） | 57 处 / 22 文件 | 0（白名单 2 + 护栏） | **0**（保持，rg 命中仅白名单与护栏自身） |
| 召回 word / char（recall@5） | — | 100% / 100% | **100% / 100%**（@1 均 86%；蓝图占位 9.0% / 12.0%） |
| 检索延迟 | 首调 0.38–2.09 s | 稳态 ~138 ms | 首调 **6.7 s**（进程级一次性）· 稳态 **4–145 ms** |
| 巡检 | 24 步 exit 0（199 s） | 24 步 exit 0（225 s） | **24 步 exit 0（239 s，健康 92/100）** |
| 预算（L0） | 24,937 / 30,000 | 25,128 / 30,000 | **25,114 / 30,000**（WORK 4,866/5,000） |
| 未推送提交 | 外层 10 / 中枢 4 | 0 / 0 | **0 / 0** |
| **测试实测发现的真 bug（累计）** | — | 0 | **3**（日报崩 · 健康分虚高 · `card_tags` 只读首 tag） |
| 规模（`hub-engine/` tracked） | 165 文件 / 28,318 行 | — | **170 文件 / 30,490 行**（增量主要是本轮 +64 例测试） |

### 11.3 为何不是更高（诚实说明）

1. **覆盖率是“分布不均”的 53.9%**：`scripts/` 41.7%、`commands/` 62.9% 拖后腿——数字上过了 40% 线，
   但**最接近“会伤人”的写入/巡检路径仍非全部端到端**（只补了高频分支）。
2. **规则债已登记未还清**：E501 **78** 处 + C901 **8** 个仍在 `per-file-ignores` 基线里。
3. **检索维度受两个天花板夹制**：金标准集仅 **22 条**（recall 已 100%，再往上是“度量分辨率”问题）；
   首调 **6.7 s**（jieba 词典 + 索引构建，进程级一次性，未做预热/持久化）。
4. **可用性天花板在本机之外**：LM Studio / 网关 / 计划任务全在一台机器，且**无 CI**——设计选择，但确实限制了分数。
5. **两项不可逆债**：历史提交署名（64% `Codex Local`）与仓体量（`.git` 287 MB）——不重写历史即只能向前修复。

### 11.4 下一步（按收益/风险排序，非承诺）

| 优先 | 事项 | 为什么 |
|:--|:--|:--|
| 1 | **T1 重跑（时间门 ≥ 2026-10-07）** | 唯一硬约束项；改造前后对照的判据已写好 |
| 2 | ~~6 张缺 `status` 的卡补元数据（或归档）~~ ✅ **已完成（见 §11.5）** | 6 张补 `status: active`；同一类缺陷（4 张空 `tags`）一并修；门禁新增「必填字段存在性」检查堵住复发 |
| 3 | ~~金标准集 22 → 40+~~ ✅ **已完成（见 §11.6）** | 实际做到 **58 条**（+39，含 8 条真实日志改写），@1 恢复分辨力，并顺带揪出 1 个排序缺陷 |
| 4 | ~~SPLIT2 余 8 个 C901~~ ✅ **已完成（见 §11.7）** | 当日全部拆完：**C901 债清零**（基线豁免 16 处 → 0 处） |
| 5 | ~~可选：`patrol_runner.py` 拆 `steps/` 包~~ ✅ **已完成（见 §11.8）** | 实际拆成 `scripts/patrol/` 包（core/steps/report）+ 编排层保留在 runner；1,597 → **477 行** |

### 11.5 §11 之后的追加修复（D1 / D1b 已关闭）

§11 评的是**当日 COV+SPLIT2 收口时点**；随后当日即把 §11.4 第 2 项做掉，顺带关掉同一缺陷类的 D1b。

| 项 | 内容 | 证据 |
|:--|:--|:--|
| **D1 数据** | 6 张 `experience/` 卡补 `status: active`（`dashboard-metric-source-mismatch` · `autocad-cad-plugin-testing-skill-decoupled-architecture` · `deepseek-peak-offpeak-scheduler` · `hermes-env-only-proxy-vs-clash-fakeip` · `vmmem-wsl2-docker-memory-three-layer` · `workbuddy-model-list-static-deepseek-alias`） | 用**刚修好的** `fix_card_schema_drift` 自身跑 dry-run → `--apply`：`合规 368 / 修复 6 / 需人工 0`；复扫 **0** 张缺 status |
| **D1 规则（根因）** | `common/frontmatter.py` 新增 **raw 层** `raw_frontmatter()` / `missing_required_keys()`；`check_card_frontmatter` V1.1 据此把 `type`/`status`/`updated` 缺失升为**阻断**、`tags` 为空升为**警告** | 根因：`parse_card` 对缺字段有默认值（status→active / type→note），`validate_card` **永远看不到“没写”** —— 所以 6 张卡静默存活 |
| **D1 修复链** | `fix_card_schema_drift` V1.1：`run_fix` 的 clean 判定不再只看 `validate_card`，并新增「缺 type/status 按目录映射与 active 补齐」 | 修前是“门禁报错却无法一键修”；现两条路径同一口径（`REQUIRED_KEYS` 单源） |
| **D1b** | 4 张 `tags:` 为空的 autocad 卡补主题标签（自标题/正文的显式主题提取，**不臆造**），并清掉 frontmatter 内的前导空行 | 空 tags ⇒ tag 检索与可定位性度量看不到该卡；复扫 **0** 张空 tags |
| **顺手修的潜在 bug** | `fix_card_schema_drift` 原有一份本地 `VALID_STATUS` 副本且**漏了 `deprecated`** ⇒ 修其它缺陷时会顺手把 deprecated 卡改成 `active`（只因 `validate_card` 提前放行而从未爆）；现统一取 `common.frontmatter.VALID_STATUS` 单源 | 新增回归测试 `test_deprecated_status_not_flipped_when_repairing_type` |

**验证**：全中枢 **469 张卡门禁 exit 0（0 警告）** · 缺 status / 空 tags 复扫 **0 / 0** ·
测试 **643 → 652 passed**（+9：门禁 3 / 修复器 2 / raw 层 4）· 覆盖率 **54.0%**（common 81.1→**91.1%**）·
巡检 24 步 **exit 0**（249 s，健康 92/100）· lint `orphans/ghosts/stale/invalid` 全 0。

> ⚠ **§11 的 8.7 不因本节回溯上调**：评分是时点快照，D1 的收益计入下一次重跑（T1 重跑或新一轮审计）。

### 11.6 D2：检索度量扩容（22 → 58 条）+ 由它揪出的排序缺陷

**做什么**：金标准集 22 条时 word 模式 recall@1 已达 86%、“再往上无意义”（22 条的分辨率下限为 1/22 ≈ 4.5pp）。
本轮扩到 **58 条**：+39 条（**8 条取自真实日志** `.sync/state/query.log*.jsonl` 改写、31 条区域补写，
补齐此前几乎空白的 longterm/projects/methodology），**−3 条失效题**。

#### 11.6.1 度量结果（2026-09-25 实测）

| 集合 | 模式 | recall@5 | recall@1 | 蓝图占位 |
|:--|:--|--:|--:|--:|
| 22 条（旧） | word（生产） | 100% | 86% | 9.0% |
| 22 条（旧） | char | 100% | 86% | 12.0% |
| **58 条（新）** | **word（生产）** | **98%**（57/58） | **79%** | 9.3% |
| **58 条（新）** | char | **100%** | **70%** | 12.6% |

仍然**达标**（阈値 90%）。@1 从“饱和的 86%”变成有分辨力的 **79% / 70%**，且 char 与 word 的差距（@1 7pp）
首次被量化 —— 印证生产选 word 是对的。

#### 11.6.2 三个发现（均已在代码/夹具里固化）

**① 夹具卫生：废弃/临时卡不能当金标准目标**

- 扩写初稿里我自己的 2 条目标卡已是 **`deprecated`**（内容并入 `global-rules` / `memory-injection-pattern`）——
  检索按设计排除废弃卡 ⇒ 那不是“检索缺口”，是**夹具造错了**；
- 体检又发现**原有 22 条里有 3 条目标卡是 `candidate`**（临时态，随时可能被归档/并入）→ 已剔除
  （其主题暂无 active/reference 等价卡，如需恢复待卡晋升）。
- ⇒ 新增 `validate_gold()`：目标卡必须**存在**且 status ∈ {active, reference}，否则 **exit 2 并拒绝跑分**
  （口径：**修夹具，不要改阈値**）；同规则已于单测（`tests/test_recall_regression_gold.py`，9 例）。

**② 冠军保底“补首位”是错的（本次新发现）**

向量冠军保底为救回“只有向量命中的强证据”而把冠军插到**首位**，并给它假的 `score=0.0`（未参与 RRF）——
后果：它抢在“两通道真命中”的卡之前，分数与位次语义不一致；实测某些查询的向量榜首是**噪声卡**
（如 `auto-promote-empty-today-rule`）也被顶到第 1。三种排布实测（58 条）：

| 排布 | word @5 / @1 | char @5 / @1 |
|:--|--:|--:|
| 冠军补首位（旧） | 98% / 76% | 100% / 69% |
| **冠军补末位（已改）** | **98% / 78%** | **100% / 69%** |
| 取消保底 | 98% / 78% | **98%**（丢掉蓝图守卫条） / 69% |

⇒ 补末位**严格占优**：保住保底的 @5 收益，不再抢位（`tools/retrieve.py::_with_vector_champion`，含回归测试 V1.1）。

**③ 通道权重在新集合上已不敏感**

旧调参（2026-09-24，22 条）得出 `vec=1.5`；本轮在 58 条上扫 1.0/1.25/1.5/1.75/2.0 → **全部 98% / 76%（同分）**。
结论：**保持 1.5 不变**（旧样本太小，本轮只做反向验证，不为无差别指标动参数）—— 已在代码注释里记下。

#### 11.6.3 剩余缺口（诚实，不掩盖）

**唯一真未命中**：`新写好的卡怎么晋升到权威区` → `memory-hub-card-promotion`（methodology）。
该卡写的是“draft → ingest → 权威区提升标准流程”，但查询里的“晋升/权威区”在**语义通道上无锚点**，
top-1 反而是被冠军保底推上来的噪声卡。已作为**有意保留的红样例**（“永远全绿的度量 = 摆设”）。
处置候选（待定，不着急单条调参）：给该卡补 tag、或在卡内正文加上“晋升/提级”这类自然词面。

#### 11.6.4 预计评分影响（不回溯 §11）

| 维度 | §11 分 | 重测预估 | 依据 |
|:--|--:|--:|:--|
| 检索质量 | 8.6 | **≈ 8.8** | 度量分辨率修复（ 22→58 条、@1 不再饱和）+ 排序缺陷修复（@1 76→78%）+ 权重反向验证 |
| 测试与门禁 | 9.3 | **≈ 9.4** | +9 例（金标准集体检 9 例；夹具失效即 red） |

具体数字待 T1 重跑（≥2026-10-07）或新一轮审计时按同一口径重测确认。

### 11.7 SPLIT2 收口：C901 复杂度债清零（16 → 0）

启动规则族时在 `hub-engine/pyproject.toml` 登记了 **16 个超阈函数**（max-complexity 15）作为“可度量的债”。
本轮（§10 / §11 之间共两批）**全部拆完**，基线豁免条目 **16 → 0**：

| 批次 | 函数 | 原复杂度 | 拆法 |
|:--|:--|--:|:--|
| 第一批（前次） | `patrol_runner.run_patrol` | 319 行 | 编排 + 9 个 `_stage_*` |
| 第一批 | `auto_flywheel.run` | 220 行 | 抽掉两份 55 行重复块 |
| 第一批 | `sync.ingest` | 229 行 | 先补 14 例分支测试，再抽 5 个函数 |
| 第一批 | `patrol_runner.print_report` | 16 | 表头 + 5 个 `_print_*` 段落 |
| 第一批 | `hub_health.check_alerts` | 22 | 4 个 `_alert_*` 规则函数 + 编排 |
| 第一批 | `hub_daily_report._format_6panel_section` | 17 | 6 个 `_panel_lines_*` + 表驱动 |
| **第二批** | `audit_index.audit` | 127 行 | 6 个 `_check_*` 维度函数（顺序=输出顺序） |
| **第二批** | `post_ingest_hook.main` | 124 行 | `_parse_args`/`_diffs_from_names`/`_plan_entries`/`_apply_plan`/`_commit_indices` |
| **第二批** | `rule_following_timeseries.main` | 177 行 | 6 个 `_print_*` 段落（A–E）+ `_iso_week` |
| **第二批** | `platform_bridge.push` | 98 行 | `_push_guard`/`_select_cards`/`_plan_push`/`_apply_push` |
| **第二批** | `status.compute_snapshot_health_scores` | 80 行 | 4 个 `_score_*` + 加权求和 |
| **第二批** | `status.print_snapshot_report` | 90 行 | 6 个 `_print_*` 段落 |
| **第二批** | `auto_fix_lint.run_fix` | 130 行 | `_apply_card_fixes`/`_collect_fixable`/`_write_patch` |
| **第二批** | `flywheel._cmd_daily_report` | 212 行 | `_generate_report`/`_collect_push_kwargs`/`_push_report` + 4 个通道函数 |

#### 保真手段（不只是“看起来一样”）

| 手段 | 用在 | 结果 |
|:--|:--|:--|
| **stdout 逐行 diff** | `rule_following_timeseries` / `status.print_snapshot_report` / `flywheel._cmd_daily_report` | 差异 **0 行**（除临时目录随机名） |
| 既有测试全绿 | `audit_index`(5) / `platform_bridge`(34) / 前次 5 个 | 全绿 |
| 新补网测试 | `post_ingest_hook`(+3) / `auto_fix_lint`(+5) / `flywheel 日报通道`(+6) | 拆前无测试的路径现有看守 |
| 覆盖率副作用 | — | `scripts/` **41.8% → 44.9%**、TOTAL **54.0% → 56.2%**（拆出的子函数被新测试覆盖） |

#### 拆的过程中顺手修的真缺陷

1. **`auto_fix_lint` 漏 `deprecated`**（与 `fix_card_schema_drift` 同一 bug 类）：它用一份手写 status 四元组判定合法性，
   漏了 `deprecated` ⇒ **一张已作废的卡只要还有别的缺陷，就会被改回 `active`**（等于把并入旧卡“复活”）。
   现统一取 `common.frontmatter.VALID_STATUS` 单源，并有回归测试 `test_deprecated_status_is_not_flipped`。
2. **留痕路径跨平台**：`auto_fix_lint` 写 patch 时用 `str(relative_to())`（Windows 会写成 `experience\x.md`），
   现统一 `as_posix()`，与 `post_ingest_hook` 同口径。

#### 验收

`ruff check .` 0 违规且 **per-file-ignores 里已无任何 C901 条目**（豁免不再需要，因为真的没超阈函数）·
测试 **663 → 677 passed**（+14）· 巡检 24 步 **exit 0**（258 s，健康 92/100）·
函数层面：`ruff --isolated --select C901` 全库 **0 命中**。

### 11.8 patrol_runner 拆包（1,597 → 477 行编排层）

§11.4 第 5 项的“可选”项也做了。目标：把 1,597 行的单文件按**职责**分层，
且**注册表唯一事实源不变**（`tests/test_patrol_steps.py` 静态扫描的仍是编排层）。

#### 11.8.1 新布局

| 模块 | 行数 | 职责 |
|:--|--:|:--|
| `scripts/patrol/core.py` | 158 | 路径引导 + `_LOCAL_TZ` + 数据模型（`StepResult`/`StageResult`/`PatrolReport`）+ `_run_step`/`_run_cmd` |
| `scripts/patrol/steps.py` | 946 | 24 个步骤实现（预检 / 质量 / 飞轮 / 数据 / 自修复 / 平台）+ 快照归档 + 建议生成 |
| `scripts/patrol/report.py` | 106 | 报告渲染（`_STEP_ICONS` / `_print_*` / `print_report`） |
| `scripts/patrol/__init__.py` | 90 | 公共 API 聚合（`__all__`） |
| **`scripts/patrol_runner.py`** | **477** | **阶段编排 + `run_patrol` + `main` + 向后兼容 re-export** |

依赖方向单向：`runner → {steps, report} → core`，无循环。

#### 11.8.2 保真证据

- **纯搬运校验**（脚本比对 HEAD 版与拆后各文件的 AST 源码）：53/53 函数与类全部找到、**无新增**；
  仅 2 个函数有差异，且经 diff 确认是 ruff 刪掉了**冗余的局部 import**（`import os` / `import subprocess`
  与模块级重复）——语义等价。
- 24 步契约 + 报告渲染测试全绿（`test_patrol_steps.py` 24 例 + `test_local_summary_flow.py`）
- **端到端**：完整巡检 24 步 **exit 0**（248 s，健康 92/100）

#### 11.8.3 踩到的真坑（已固化为守护测试）

1. **漏装饰器**：按行区间搬运时 `@dataclass` 在被搬函数行的**上一行**，漏搬 ⇒ `StepResult() takes no arguments`
   （契约测试立即报红，已补回）。
2. ⚠️ **“假绿”入口**：漏搬 `if __name__ == "__main__":` ⇒ `python -m scripts.patrol_runner`
   **静默 exit 0 什么都不做**（定时任务看到的就是“全绿”）；而单元测试全绿、契约测试也全绿，
   **只有人眼看输出才能发现**。已新增 `tests/test_patrol_cli.py`（4 例）：
   `--help` 必须真打 usage / `__all__` 全部可访问 / re-export 是**同一对象**（否则 monkeypatch 打不到真位置）/ `main` 可调用。
3. **测试 patch 目标随搬移而变**：`test_patrol_steps.py` 原用 `monkeypatch.setattr(patrol, "_run_cmd", …)`（同模块时代有效），
   拆分后步骤从 `steps` 模块解析该名字 ⇒ 已改为 patch `scripts.patrol.steps._run_cmd`（24 处），
   并在测试里写明了“patch 的是步骤实现所在模块”。

#### 11.8.4 验收

测试 **677 → 681 passed**（+4 CLI/re-export 守护）· 巡检 24 步 exit 0（248 s，健康 92/100）·
预算 25,011/30,000（WORK 4,763）· `ruff check .` 0 违规 · C901 仍为 0。

覆盖率复测：TOTAL **56.3%**；新分组的 `patrol/` 包 **86.2%**（412 语句中 355 覆盖）。
⚠️ 口径提醒：`patrol_runner.py` 从 `scripts/` 移入 `patrol/` 分组 ⇒ `scripts/` 从 44.9% 显示为 42.6%
（**分母缩了，不是同口径下降**）；换组后 TOTAL 仍微升（56.2% → 56.3%）。

### 11.9 自查发现的回归（P1-c 引入）+ 护栏

**现象**：2026-09-26 06:00 Hermes 定时任务「T15-6工具每日编排」失败：
`ModuleNotFoundError: No module named 'common'`（`hub_orchestrator.py:13`）。

**根因（自我归因）**：P1-c（硬编码路径清零）把该脚本里 3 处写死盘符路径换成
`from common.config import external_path`，但**没有给它补 `sys.path` 引导** —— 这个脚本此前靠
“cwd 恰好是 hub-engine”才导得到 `common`，而真实调用方（Hermes cron）是**绝对路径 + 任意 cwd**。

**波及面**：写完护栏后静态扫描又捐出 **3 个同病脚本**：
`bootstrap_hub.py`、`demo_e2e.py`、**`hub_mcp_launcher.py`（MCP 启动链）** —— 前两个与本次回归同类，
第三个是潜在坑（MCP 宿主若不用 hub-engine 作 cwd 就会挂）。四个均已补引导。

**护栏**：新增 `tests/test_script_bootstrap.py`（2 例）
① 静态：`scripts/**/*.py` 中任何**模块级** `import common/tools/commands.*` 之前必须已有
`sys.path.insert(...)`（否则即告警）；
② 端到端：以**任意 cwd + 绝对路径**跑 `hub_orchestrator.py --help`（真复现调度器场景）。

**教训（值得记卡）**：“测试全绿 ≠ 调度器能跑” —— 单测都是 `import scripts.x`（`sys.path` 已就绪），
而真实调用方是绝对路径 + 任意 cwd。同类风险：P1-c 那次改动只被 `test_no_hardcoded_paths`（字符扫描）
覆盖，它管不了导入顺序。
