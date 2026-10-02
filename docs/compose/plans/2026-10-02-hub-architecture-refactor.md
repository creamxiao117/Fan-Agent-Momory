# 记忆中枢架构重构（分级记忆 + 能力治理 + 门禁瘦身）Implementation Plan

- 日期：2026-10-02
- 来源：架构讨论稿 v0.2（`docs/compose/specs/2026-10-02-hub-capability-memory-architecture.md`）全部建议获用户裁定「就按你的建议来」，含 Q1–Q12
- 姊妹计划：`docs/compose/plans/2026-10-02-pi-hub-bridge.md`（pi 接入 P0–P3）——**两计划合流执行顺序见 §0**
- 验收判据：C1–C8（见 §2），**判据不通过即视为未完成**
- 范围外：pi 之外各平台的客户端功能改造；向量库/embedding 改造；Web UI；`work/` 归档区

---

## 0. 合并执行顺序（与 pi 接入计划合流）

```
Wave 1  pi-P0/T1 解释器归位 → pi-P0/T2 硬约束注入 → pi-P0/T3 分型统一
        → ★T3 平台元数据单源化（本计划）→ pi-P0/T4 pi 登记（登记进唯一源）
Wave 2  M0 事实固定（只读：capability_scan + INVENTORY + 职责重复检测）   ← 可与 Wave 1 尾部并行
Wave 3  pi-P1（engine.py tier-bootstrap + memory-hub.ts 扩展）            ← 只读 M0 结果
Wave 4  M0.5 门禁收敛（9→3 scope-gated / 25→8 步 / 单一快照 / rules 合并）← 需 Wave 2 台账；禁与 pi-P0 并行
Wave 5  M0.6 清理（A/B/D 类归档 + `_retired` 仪式简化）
Wave 6  M1 grade 轴（定义 → 标注 → L1 改派生 → 检索分层 → iron 资格收紧）
Wave 7  M2 能力账本（SkillHub 扩字段 + MCP/CLI 纳入 + 对账门禁 + cost 探针）
Wave 8  pi-P2/P3（回写闭环 + 回归沉淀）
Wave 9  M3 任务级装配（调研 → tier-bootstrap 扩展 → 装/卸全环 + 预算帽）
```

**禁并行对**（会撞车，必须串行）：
- `pi-P0/T3`（改 `task_tier.py` + `AGENTS.md`）∥ `M1/T12`（L1 改 grade 派生）——**同一口径**，必须先后
- `M0.5/T6`（改 `rules/`）∥ `M1/T14`（改 iron 资格）——同批卡，先合并再评级
- `M0.5`（改 pre-commit / patrol）∥ 任何中枢提交密集期——门禁自改期间最易静默失效

### 0.1 开工现场发现（2026-10-02 实测，直接验证了本计划的前提）

| # | 发现 | 含义 |
|---|---|---|
| F-1 | `render_index --check` 现为 **RED（exit 3）** | 中枢仓**任何提交都被阻断**（或逼人用 `--no-verify`）—— 正是 Task 6 要修的缺陷，且**当下就生效** |
| F-2 | `rules/cross-platform-sync-rule.md` 工作树版本**字节级损伤**：每行后插入空行（74→148 行，空行占比 0.62）；非空行内容与 HEAD **完全一致**（57 行逐行相同），仅 `reuse_count: 8→7` | 存在一个**写卡工具的双行距 bug**；全库扫描仅此 1 例（非系统性）。值得单立一张 `pitfall` 卡（M1/T13 的候选） |
| F-3 | 10 张卡 `reuse_count: N→N+1`（自动 churn，MCP 命中复用累积特性） | 非人手改动；但 INDEX 不跟踪 `reuse_count`，所以 **F-1 的红不能全归因于它** |
| F-4 | `retro/snapshot-2026-10-02.json` 未跟踪（既存“待裁”项） | 与 Task 7 的产物口径合并裁定 |
| F-1' | 由此推出：**Wave 1 的 hub 侧任务（Task 3 / pi-T4）在该工作树干净前无法提交** | 开工顺序需插入一步「现场清理」：先裁 F-1/F-2，再动 hub 侧写操作 |

---

## 1. 已裁定的设计决定（锁定，实施不得偏离）

| # | 决定 | 依据 |
|---|---|---|
| D1 | 记忆新增 **`grade` 轴**（与目录正交）：`iron\|proven\|domain\|task\|pitfall`，**不复用** `L0/L1/L2` 命名 | Q1/Q2 |
| D2 | **两库一协议**：知识唯一源=中枢卡文件；能力唯一源=SkillHub `router/` + `capabilities/`；不合并仓库 | Q3/Q4 |
| D3 | 能力新增轴：`deploy_scope`(not-installed/task/project/user/global) + `invoke`(auto/conditional/explicit-only/disabled) + `discovery_cost` + `install/uninstall/verify` | Q5/Q7 |
| D4 | 提交门禁 **9→3 且全部 scope-gated**；渲染检查只比对 **staged 内容** | Q8 |
| D5 | 每日流水线 **25→8 步**，产物 **1 快照 + 1 人读** | Q9 |
| D6 | 退役默认反转为「**保留需举证**」；`audit_dead_modules` 的「零引用」被判定为**尺子不够**，补「职责重复」 | Q10 |
| D7 | `rules/` **35 → ~12**，每张须绑门禁或明确检查；**没有门禁的不许叫 iron** | Q11 |
| D8 | **删仪式**：默认 `git rm` + 结构化 commit message，git 历史即归档；只保留「反面教材」与「仍被引用」两类实体归档 | Q12 |
| D9 | pi 触发=首轮/resume/话题漂移；注入=pi `AGENTS.md` **顶部**托管块 + `systemPromptOptions.sections` | pi 计划 Q1–Q7 |

---

## 2. 验收判据（C1–C8）

- **C1 分型单源**（pi 计划已列）：`rg "TASK_KIND_TYPES" hub-engine` 仅表定义 + 引用，无第二处枚举
- **C2 平台登记单源**：全仓只有 `hub.config.yaml.platforms` 一份平台元数据；`rg "PLATFORMS\s*="` 与 `system/platforms.yaml` 均不再存在（或后者为渲染产物 + `--check` 0）
- **C3 尺子双把**：`INVENTORY.json` 每模块含 `refs_code` / `last_run` / `gate_role` / `duplicate_of` / `verdict`；`--check` 与磁盘一致
- **C4 门禁瘦身**：提交门禁 ≤3 道且 scope-gated（改纯 `.py` 时**不跑** l0 门禁）；单次提交门禁总耗时 **< 2 s**
- **C5 流水线瘦身**：巡检步数 ≤8；单次运行产物恰为 `retro/snapshot-YYYY-MM-DD.json` + `retro/daily-YYYY-MM-DD.md` 两件
- **C6 等级轴**：`grade` 覆盖率 **100%**（506 张）；每型 `iron` ≤3；L1 卡集合由 `grade=iron` 派生（`l1_tier` 字段退役）
- **C7 账本对账**：SkillHub 账本 vs 各平台实测态差异 = 0 或全部有裁定记录；`discovery_cost` 有实测值
- **C8 瘦身结果**：`hub-engine` 模块数 105 → **≤75**；`rules/` ≤13；门禁/测试/渲染全绿

---

## 3. Global Constraints

- 解释器一律 `..\.venv\Scripts\python.exe`；测试 `cd hub-engine && ..\.venv\Scripts\python.exe -m pytest`
- 编码 UTF-8 无 BOM（`.py/.md/.json/.yaml/.ts`）
- 中枢嵌套仓：`git -C AgentMemoryHub`；跨仓改动**两仓提交相邻**（message 互引）
- `INDEX*.md` 是渲染产物：改卡后 `python -m scripts.render_index --write`；**禁手改**；`--check` 必须 0
- **先证红再改**：门禁/校验类改动先写失败用例（负样本）
- **门禁自改期间**：新旧门禁**并行跑一周**（旧门禁降为 warn 不阻断），观察期结束才删旧
- 每任务收尾：相关 `pytest` + `ruff check` + `ruff format --check` + markdownlint 全绿
- 归档件一律走既有标签约定（本计划 T10 会简化该仪式，但简化**之前**仍按现约定）
- **提交门禁自改期间不得使用 `--no-verify`**：本计划的存在理由之一就是消灭该习惯；自改期的门禁故障**必须当场修**

---

## 4. 风险与反模式规避

| # | 风险 | 护栏 |
|---|---|---|
| R1 | **门禁自改造成静默失效**（最危险） | 新旧并行一周 + 旧降 warn；每条新门禁必须有负样本用例；C4 用 `time` 实测 |
| R2 | **删错活物**（凭印象删） | 每个删除候选必须取证：`schtasks` + 产物目录时间戳 + 活代码引用；C 类已有先例（sleep 链**在跑**，撤回删除） |
| R3 | **grade 标注通胀**（铁律泛滥） | iron 资格=有可执行门禁；每型 ≤3 形状断言；600 张全量标注先 dry-run + 抽样复核（≥30 张人工） |
| R4 | **双事实源再生** | 新增任何清单前先问「能否从既有源派生」；本计划新增的 `INVENTORY.json`/`capabilities.json` **全部是渲染产物 + `--check`** |
| R5 | **能力只增不减** | `discovery_cost` 预算帽（T21）+ 季度负向举证（T2 的 `verdict=unused` 清单） |
| R6 | **仪式成本 > 清理物** | D8：默认 `git rm`；任何新增流程先算「维护点数 × 频率」 |
| R7 | **卡/夹具漂移** | 改 `rules/` 或 L1 集合时先 `rg` 夹具与 `INDEX*` 引用，同步更新（历史教训：期望卡名漂移致门禁数学上无法达标） |
| R8 | **解释器假绿** | 全程 `.venv`；`requirements.txt` 与 `pyproject.toml` 单源（pi-P0/T1 已做） |

---

## Wave 1 追加任务

### Task 3: 平台元数据单源化（原 `system/platforms.yaml` + `mcp_healthcheck.PLATFORMS` → `hub.config.yaml`）

**问题（实测）**：平台元数据有**三处**，字段与平台集合各不相同：

| 处 | 位置 | 内容 | 消费者 |
|---|---|---|---|
| A | `AgentMemoryHub/hub.config.yaml` → `platforms:` | `memory_dir`/`target_file`/`role` | `router_sync`、`platform_bridge`、`mcp_policy` |
| B | `AgentMemoryHub/system/platforms.yaml` | `mcp_config_path`/`config_format`/`server_key`/`write_window`/`key_path`/`healthcheck`/`auto_repair` | `platform_sync`、`platform_healthcheck`、`mavis_hub_bridge`、`dsh_hub_bridge` |
| C | `hub-engine/scripts/mcp_healthcheck.py` → 硬编码 `PLATFORMS` dict（3 平台） | `config` 路径 + 解析格式 | 自身 |

→ 加一个平台要改三处；pi 登记会变成**第四处**。

**Files:**
- Modify: `AgentMemoryHub/hub.config.yaml`（吸收 B 的字段，`platforms.<name>.mcp_config_path` 等）
- Delete（本任务只迁不改删）: `AgentMemoryHub/system/platforms.yaml`
- Modify: `hub-engine/scripts/platform_sync.py`、`platform_healthcheck.py`、`platform_unregistered.py`、`mavis_hub_bridge.py`、`dsh_hub_bridge.py`、`mcp_healthcheck.py`
- Modify: `hub-engine/tests/test_bridge_scripts.py`、`test_deprecation_semantics.py`（按实际夹具）
- Modify: `hub-engine/common/config.py`（暴露 `platforms()` 单一访问器）

**Interfaces:**
- Produces: `common.config.HubConfig.platforms` 为**唯一**平台元数据入口，字段超集 = A ∪ B
- Produces: `common.config.platform_mcp_config(name) -> Path`（替掉 `mcp_healthcheck.PLATFORMS` 与 B 的 `mcp_config_path` 拼接）

**Covers:** C2、R4

- [ ] **Step 1: 证红** — 用例：`rg "PLATFORMS\s*=" hub-engine` 应只命中一处（当前命中 `mcp_healthcheck.py` 硬编码）→ 断言失败
- [ ] **Step 2: 字段合并** — 把 B 的全部字段搬进 `hub.config.yaml.platforms.<name>`；A 的既有键不动；补齐平台集合（B 有 `code`、A 有 `deepseek`，取并集）
- [ ] **Step 3: 消费者改造** — 5 个脚本 + `mcp_healthcheck` 全部改读单一源；`platform_sync` 的写入行为**不变**（仅输入源改变）
- [ ] **Step 4: 全链验证** — `platform_healthcheck` 输出与改造前**逐行 diff**（保真，沿用 SPLIT2 口径）
- [ ] **Step 5: 删除 B** — `git -C AgentMemoryHub rm system/platforms.yaml`；跑 `router_sync`（0）+ 相关 pytest
- [ ] **Step 6: 文件化** — `hub.config.yaml` 顶部注释说明「本文件是平台元数据唯一源；加平台只改这里」

**验收：** C2 通过；`mcp_healthcheck` 不再有硬编码平台表；`platform_healthcheck` 输出与改造前等价

---

## M0 — 事实固定（只读，零风险）

### Task 4: capability scanner + 模块台账 `INVENTORY.json`

**Files:**
- Create: `hub-engine/scripts/capability_scan.py`
- Create: `hub-engine/scripts/inventory.py`（吸收 `audit_dead_modules` 的引用扫描函数）
- Create: `hub-engine/tests/test_capability_scan.py`、`tests/test_inventory.py`
- Modify: `hub-engine/scripts/patrol/steps.py`（新增一步；本任务只加）
- Outputs（渲染产物，禁手写）: `AgentMemoryHub/system/capabilities.json` + `capabilities.md`；`hub-engine/scripts/INVENTORY.json`

**Interfaces:**
- Produces: `capability_scan --check`（与磁盘不一致即非 0）
- Produces: `inventory --check`；`INVENTORY.json` 每模块一行：
  `{path, refs_code[], refs_test[], refs_doc[], gate_role|null, last_run, duplicate_of|null, verdict}`
- Consumes: `common.config.platforms`（Task 3 的单一源）

**Covers:** C3、R4、§10.7

- [ ] **Step 1: 扫描面定义** — MCP（各平台 mcp 配置：`mcpServers` 键集）、Skill（各平台 skills 目录）、CLI（`hub-engine/engine.py` 子命令 + `scripts/*.py` 带 `__main__`）
- [ ] **Step 2: 实现 scanner** — 纯读、零写（除产物）；`--check` 模式只比对
- [ ] **Step 3: 实现 inventory** — 复用 `audit_dead_modules` 的正则（含「可选包前缀」修复），**加 `gate_role`**：从 pre-commit 与 `patrol/steps.py` 的调用图反推
- [ ] **Step 4: `last_run` 取证** — 从 `.sync/state/`、`retro/` 产物时间戳、`schtasks` 三处取最晚证据（**无证据=null，不猜**）
- [ ] **Step 5: 双份 `--check` 上巡检** — 加入 8 步流水线（Wave 4 前先以 warn 级接入）
- [ ] **Step 6: 交接** — 把 `capabilities.md` 与 `INVENTORY.json` 提交；`agent-tool-inventory.md` 加一行「本卡已由 X 取代，待 M0.6 处置」

**验收：** C3 通过；scan 结论与 `methodology/agent-tool-inventory.md`（2026-08-18 快照）**可比且更新**；零写盘（除 3 个产物）

---

### Task 5: 职责重复检测（新尺子）

**Files:**
- Modify: `hub-engine/scripts/inventory.py`（`duplicate_of` 计算）
- Modify: `hub-engine/tests/test_inventory.py`
- Create: `docs/compose/reports/2026-10-XX-duplicate-clusters.md`（人读裁定表）

**Interfaces:**
- Produces: 聚类规则 —— 两模块若 `{输出产物} ∩ {gate_role}` 非空且职责关键词交集非空 ⇒ 标 `duplicate_of=<保留者>`
- Consumes: Task 4 的 `INVENTORY.json`

**Covers:** C8、R2、D6

- [ ] **Step 1: 证红** — 以已知重复对（`index_consistency` vs `render_index --check`）为夹具，断言检出
- [ ] **Step 2: 实现聚类** — 三信号：①产物文件路径 ②被同一门禁调用 ③函数名/文档首句的职责词
- [ ] **Step 3: 产出裁定表** — 每簇一行：保留者 / 归档者 / 判据 / 取证（引用与产物时间戳）
- [ ] **Step 4: 人工裁定一次** — 表格交用户确认（**不自动删**，对齐 D6）

**验收：** C8 的候选清单来自机器而非肉眼；每簇有取证；裁定表落盘

---

## M0.5 — 门禁收敛

### Task 6: 提交门禁 9 → 3（全部 scope-gated）

**Files:**
- Modify: `hub-engine/scripts/pre-commit`（源）
- Modify: `.git/hooks/pre-commit`（外层）、`AgentMemoryHub/.git/hooks/pre-commit`（中枢）
- Create: `hub-engine/tests/test_precommit_scope.py`（scope 判定单测）
- Modify: `hub-engine/common/gate_scope.py`（新建：scope 判定纯函数）

**Interfaces:**
- Produces: `gate_scope.classify(staged_paths) -> {code: bool, text: bool, l0: bool}`
- Produces: 3 道门禁（§10.3）：`code`（ruff×2）/ `text`（编码+markdownlint）/ `l0`（startup_budget + `render_index --check`）
- 关键：`render_index --check` 改为 **staged 内容**比对（用 `git stash` 不可行 → 实现为「把 staged 版本写临时树再渲染比对」）

**Covers:** C4、D4、R1

- [ ] **Step 1: 证红** — 用例：staged 只含 `hub-engine/tools/x.py` → `classify` 返回 `l0=False`（当前实现必然 fail，因为无 scope 概念）
- [ ] **Step 2: 实现 `gate_scope`** — 路径规则表集中一处（`l0` 触发面：`AGENTS.md`/`CHARTER.md`/`WORK.md`/`INDEX*.md`/六权威区 `*.md`/`render_index.py`/`hub_registry.py`）
- [ ] **Step 3: 重写两个 pre-commit** — 按 3 道组织；退出码收敛为 `0/1/2/3`
- [ ] **Step 4: 并行期** — 旧门禁保留为 **warn 不阻断** 一周（新旧同时跑，日志记录差异）；一周后删旧
- [ ] **Step 5: 性能实测** — `time` 三种典型提交（纯 py / 纯 md / 中枢卡），全部 < 2 s 并留档
- [ ] **Step 6: 修复「他人未提交改动阻断提交」** — 用「工作树里预置他人未提交卡改动 + 自己只提交 py」的夹具证明不再阻断（这是本任务的核心收益）

**验收：** C4 通过；Step 6 夹具通过（该缺陷在案已久，必须留下回归用例）

---

### Task 7: 每日流水线 25 → 8 步 + 单一快照产物

**Files:**
- Modify: `hub-engine/scripts/patrol_runner.py`、`hub-engine/scripts/patrol/steps.py`、`patrol/report.py`
- Modify: `hub-engine/commands/status.py`（成为唯一快照生成器）
- Modify: `hub-engine/scripts/run_patrol.cmd`（如存在）与 `AgentHub-DailyPatrol` 计划任务参数
- Modify: `hub-engine/tests/test_patrol_cli.py`、`test_patrol_steps.py`

**Interfaces:**
- Produces: 8 步（§10.4）；产物恰两件：`AgentMemoryHub/retro/snapshot-YYYY-MM-DD.json` + `retro/daily-YYYY-MM-DD.md`
- Produces: `snapshot.json` 为**唯一**健康数据源；人读 md 由它渲染
- 保留：`_stage_verify_after_fix` 的「先修后验」语义

**Covers:** C5、D5、R1

- [ ] **Step 1: 证红** — 断言「产物恰 2 件」（当前会产生 ≥7 种）
- [ ] **Step 2: 步骤合并** — 25→8：三索引检查合一 / 五评测只留回归 / 四健康采集合一到 `status.py` / 报告合一
- [ ] **Step 3: 报告收敛** — `lint-report-*`、`daily-6panel.json`、`review_today.md`、`query_report` 全部改为**从快照派生**或停止产出（逐个在 T8 裁定）
- [ ] **Step 4: 产物滚动清理** — 保留 30 天（防 `retro/` 堆积；与 `patrol.log` 同口径）
- [ ] **Step 5: 计划任务对齐** — `schtasks` 参数与 8 步一致；`nightly_consolidate.cmd` 同步
- [ ] **Step 6: 全链验证** — 巡检 `exit 0`；`snapshot.json` 字段与改造前**可比**（关键指标不丢）

**验收：** C5 通过；`retro/` 只新增两类文件

---

### Task 8: `rules/` 结构合并（35 → ~20）

**Files:**
- Modify: `AgentMemoryHub/rules/*.md`（合并/标 deprecated）
- Modify: `AgentMemoryHub/rules/rules-routing-table.md` + `-appendix`（删过期的 `L1_CARDS` 段落）
- Delete: `AgentMemoryHub/rules/routing-table.json`
- Modify: `hub-engine/scripts/render_index.py`（若路由表改为渲染产物）
- Modify: 相关夹具（先 `rg` 引用）

**Covers:** C8、D7、R7

- [ ] **Step 1: 先删腐烂** — `rules-routing-table.md` 的 `L1_CARDS` 段落（该符号已不存在）+ `routing-table.json`（2 条无消费者）
- [ ] **Step 2: 分组裁定表** — 22 张纯文本卡按主题聚类（编码类 / 上下文预算类 / 平台约定类 / 自动化脚本类 / 流程纪律类…），交用户确认
- [ ] **Step 3: 合并** — 同类并入 `global-rules`（沿用既有先例）或保留一张「族卡」（核心 + 附录，沿用 09-23 拆分口径）
- [ ] **Step 4: 每张保留卡的必填项** — frontmatter 增 `gate:`（指向具体门禁或「明确检查」）；无 `gate` 者本任务不删，留给 Task 14 降级
- [ ] **Step 5: 索引与门禁** — `render_index --write`；`pytest` + ruff + markdownlint 全绿；**检查夹具里的期望卡名**（R7）

**验收：** `rules/` ≤20（Task 14 后 ≤13）；无悬空引用；`render_index --check` 0

---

## M0.6 — 清理

### Task 9: A/B 类归档（按 Task 5 裁定表 + 取证）

**Files:** 按裁定表；同步 `tests/` 与被引用文档

**Covers:** C8、D6、R2

- [ ] **Step 1: 逐个取证**（三个证据缺一不可）：①活代码引用 ②计划任务/产物时间戳 ③是否有卡引用它
- [ ] **Step 2: 归档**（本任务仍用现约定**实体归档**；Task 10 之后的新退役才用 `git rm`）
- [ ] **Step 3: 修引用** — 被卡/文档引用者先改引用，再归档
- [ ] **Step 4: 验证** — `pytest` 全绿（含 `test_retired_archive.py`）；模块数记入 `INVENTORY.json`

**验收：** 模块数 105 → **≤85**；零悬空引用；证据表落盘

---

### Task 10: 删仪式（`_retired/` 简化，Q12/D8）

**Files:**
- Delete: `hub-engine/scripts/_retired/**`、`hub-engine/tests/_retired/**`（**git rm**，历史可恢复）
- Delete: `hub-engine/tests/test_retired_archive.py`
- Delete: `hub-engine/scripts/_retired/README.md`、三份 `RETIRED.json`
- Modify: `.ruff.toml`、`hub-engine/pyproject.toml`（移除 `_retired` 排除规则）
- Modify: `hub-engine/tests/test_no_hardcoded_paths.py`、`scripts/audit_dead_modules.py`（移除排除）
- Keep: `docs/compose/cleanup/2026-10-01-retire-list.md`（作为人类可读索引）+ `docs/compose/cleanup/2026-10-02-retire-protocol.md`（新增：结构化 commit message 模板）

**Interfaces:**
- Produces: 退役协议 = 结构化 commit message（`@superseded_by` / `@reason` / `@evidence`）+ `git rm`
- Produces: 实体归档只允许两类：①反面教材 ②仍被外部引用且无法改引用者（须在 `docs/compose/cleanup/` 登记一行）

**Covers:** C8、D8、R6

- [ ] **Step 1: 迁移留档** — 把现有 16 件的 `@superseded_by`/`@reason` 从标签块**搬进** `docs/compose/cleanup/2026-10-01-retire-list.md`（已有表格，只需补全）
- [ ] **Step 2: `git rm` 归档区** — 两仓分别提交；message 写 `@superseded_by: <表文档>` + 原因
- [ ] **Step 3: 移除排除规则** — `.ruff.toml` 等三处
- [ ] **Step 4: 新协议文档** — 一页，含 commit message 模板与「只有两类可实体归档」
- [ ] **Step 5: 验证** — `pytest` 全绿（`test_retired_archive.py` 已删）；`ruff` 全绿；`rg "_retired" hub-engine` 命中 0

**验收：** `_retired/` 目录不存在；退役协议文档落盘；无引用悬空

---

### Task 11: D 类腐烂文档处置

**Files:**
- Modify: `AgentMemoryHub/methodology/agent-tool-inventory.md`（改为引用 Task 4 产物，正文手写清单删除）
- Delete/归档: `AgentMemoryHub/rules/rules-routing-table-appendix.md`（若合并进主卡）
- 评估: `INDEX-experience.md` 与 `INDEX-full.md` 是否合并（**先算体积与查询需求**，不默认合并）

**Covers:** C8、R4

- [ ] **Step 1: `agent-tool-inventory` 改造** — 保留「口径与方法」，删除所有**具体清单数字**，改为指向 `capabilities.md`
- [ ] **Step 2: 索引分册裁定** — 输出「3 分册 vs 2 分册」的体积/查询对比，交用户裁定
- [ ] **Step 3: 渲染与门禁** — `render_index --write` + `--check` 0

**验收：** 不再有手写的「工具清单快照卡」；索引分册数量已裁定

---

## M1 — grade 轴

### Task 12: `grade` 字段定义与校验

**Files:**
- Modify: `hub-engine/common/frontmatter.py`（`VALID_GRADES`）
- Modify: `hub-engine/scripts/check_card_frontmatter.py`、`hub-engine/tools/lint.py`
- Modify: `hub-engine/tools/hub_registry.py`（`CardMeta` 增 `grade`）
- Create: `hub-engine/tests/test_grade.py`

**Interfaces:**
- Produces: `VALID_GRADES = ("iron","proven","domain","task","pitfall")`
- Produces: `frontmatter.validate_card` 对 `grade` 做枚举校验；缺失 = invalid（**先 warn 一周，再转阻断**）

**Covers:** C6、D1

- [ ] **Step 1: 证红** — 用例：含 `grade: 铁律` 的卡应被拒（当前通过 → fail）
- [ ] **Step 2: 实现校验** — 枚举 + 分目录的 `grade` 合法集（如 `blueprints/` 不得为 `iron`）
- [ ] **Step 3: 灰度** — 一周 warn 级（写入 `retro/` 缺 `grade` 清单），之后转阻断
- [ ] **Step 4: `tier` 字段处置** — 现有 35 张 `tier: iron|task` 作迁移映射（`iron→iron`、`task→` 按目录定），`tier` 标 deprecated 并**从门禁必填中移除**

**验收：** `grade` 枚举校验生效；`tier` 不再要求

---

### Task 13: 批量标注 506 张 + 差异复核

**Files:**
- Create: `hub-engine/scripts/migrate_grade.py`（**一次性**，dry-run 默认；完成后按 T10 协议 `git rm`）
- Create: `docs/compose/reports/2026-10-XX-grade-migration.md`（差异表 + 抽样复核记录）
- Modify: 506 张卡的 frontmatter

**Interfaces:**
- Produces: 映射规则（依据 §4.1）：`rules/` 有门禁或既有 `tier:iron` → `iron`；`experience/` 含「静默失败/假绿」关键词 → `pitfall`（**人工复核**）；`blueprints/` 有 `evidence=t1` → `proven`；`longterm/` → `domain`；其余 `task`
- Produces: 逐卡 `@grade_source: rule|manual` 便于回溯

**Covers:** C6、R3

- [ ] **Step 1: dry-run 差异表** — 输出「规则建议 vs 现状 `tier`/`status`」的冲突清单
- [ ] **Step 2: 抽样复核** — 随机 ≥30 张人工确认（尤其 `pitfall` 与 `iron` 两类）
- [ ] **Step 3: 写入** — 只动 frontmatter，不改正文（保证正文零 diff）
- [ ] **Step 4: 冲突裁定** — 差异逐条裁定并落表（不静默改）
- [ ] **Step 5: 覆盖率验证** — `grade` 覆盖 100%；`iron` 每型 ≤3（超则降级）

**验收：** C6 通过；正文零 diff；复核记录落盘

---

### Task 14: L1 卡集合改由 `grade=iron` 派生 + iron 资格收紧（`rules/` → ~12）

**Files:**
- Modify: `hub-engine/tools/task_tier.py`（`l1_cards()` 改读 `grade=iron`，删除 `L1_TIER_FIELD`）
- Modify: `hub-engine/tests/test_task_tier.py`（`LEGACY_L1_CARDS` 迁移基准 → 差异裁定）
- Modify: 6 张卡（移除 `l1_tier`）
- Modify: `AGENTS.md` 路由表 + `rules-routing-table` 派生表
- Modify: `hub-engine/tools/inject.py`（指令文案）

**Covers:** C6、D7、R7

- [ ] **Step 1: 差异表**（**前置，必须先出**）— 现 `l1_tier` 派生集合 vs `grade=iron` 派生集合逐型对比
- [ ] **Step 2: 逐条裁定** — 非空差异**逐条裁定**，不静默改路由（对齐 Q6）
- [ ] **Step 3: 实现派生** — `l1_cards()` 读 `grade`；`l1_tier` 退役；`check_l1_shape` 保持 ≤3
- [ ] **Step 4: iron 资格收紧** — 逐张裁定 Task 8 留下的 ~20 张：有门禁 → `iron`（并可升门禁）；无 → `proven`/`domain`/`pitfall`；目标 `rules/` ≤13
- [ ] **Step 5: 门禁与索引** — `startup_budget`（L1 形状）+ `render_index --check` + 夹具

**验收：** C6 通过；`l1_tier` 全仓命中 0；`rules/` ≤13

---

### Task 15: 检索与注入按 grade 分层

**Files:**
- Modify: `hub-engine/tools/retrieve.py`（返回 `grade`）
- Modify: `hub-engine/tools/mcp_handlers.py`（`_hit` 带 `grade`；`hub_bootstrap` 分块渲染）
- Modify: `hub-engine/tools/snippet.py`（按 grade 定摘要长度：`iron` 全文 / `proven` 摘要 / `task|pitfall` 一行）
- Modify: `hub-engine/tests/test_mcp_handlers.py` 等
- Modify: pi 计划 T6 的注入模板（分块标题）

**Interfaces:**
- Produces: bootstrap markdown 分块：`## 铁律（必读全文）` / `## 已验证方案` / `## 相关经验与坑`
- Produces: 负路由 `forgot` 命中即过滤（知识侧从 0 起步）

**Covers:** C6、§4.2

- [ ] **Step 1: 证红** — 断言 bootstrap 输出含三段标题，且 `iron` 卡出现「必读全文」
- [ ] **Step 2: 实现分层渲染**
- [ ] **Step 3: 排序** — `grade` 优先级 > 分数（同分时 iron 优先）
- [ ] **Step 4: 回归** — `recall_regression` 58 条 ≥90%（**不得因分层而降召回**）

**验收：** 三段标题；`recall_regression` 不退；pi 注入内容按 grade 分层

---

## M2 — 能力账本

### Task 16: SkillHub schema 扩字段

**Files:**
- Modify: `D:/AIwork/20260821-Fan-SkillHub/router/schema.yaml`、`router/router.yaml`
- Modify: `.../bridge/gate.py`（校验新字段）
- Create: `.../capabilities/mcp.yaml`、`.../capabilities/cli.yaml`
- Modify: `.../docs/USER_MANUAL.md`

**Interfaces:**
- Produces: 新字段（§5.2）：`kind`(skill|mcp|cli)、`deploy_scope`、`invoke`、`discovery_cost`、`install`/`uninstall`/`verify`、`requires`、`grade`、`source_card`
- Produces: `kind=mcp|cli` 与 `kind=skill` 共用 schema（不同 `install` 语义）

**Covers:** C7、D2/D3

- [ ] **Step 1: schema 先行** — 加字段 + 校验（缺失给默认：`deploy_scope: not-installed`）
- [ ] **Step 2: 存量迁移** — 73 个 skill 记录补 `kind: skill`（其余默认）
- [ ] **Step 3: MCP 录入** — 用 Task 4 的实测结果**反向录入**（不许手写猜测），每条含 `install` 与 `verify`
- [ ] **Step 4: CLI 录入** — 只收「对 agent 有意义的 CLI」（`engine.py` 子命令等），不含内部脚本

**验收：** schema 校验通过；MCP/CLI 条目与实测态一致

---

### Task 17: 声明 vs 实测对账门禁

**Files:**
- Create: `hub-engine/scripts/capability_reconcile.py`
- Modify: `hub-engine/tools/mcp_policy.py`（若需）
- Modify: 巡检 8 步的第 4 步

**Interfaces:**
- Produces: `capability_reconcile` 输出三集合：`declared_only` / `actual_only` / `matched`
- Produces: 差异处理口径（沿用 `router_sync`）：`actual_only`（装了没登记）→ **warn**；`declared_only` 且 `deploy_scope != not-installed`（登记了没装）→ **fail**

**Covers:** C7、R4

- [ ] **Step 1: 证红** — 夹具：账本声明 user scope 但配置里没有 → 应 fail
- [ ] **Step 2: 实现对账** + 输出可读差异
- [ ] **Step 3: 接入巡检**（第 4 步）
- [ ] **Step 4: 首发对账** — 跑一次并**清账**（把现有隐式常驻能力补登记）

**验收：** C7 差异 = 0 或全部有裁定记录

---

### Task 18: `discovery_cost` 实测探针 + 预算帽

**Files:**
- Modify: `hub-engine/scripts/capability_scan.py`（token 估算）
- Modify: `.../capabilities/*.yaml`（回填实测值）
- Modify: 巡检门禁（超帽报红）

**Interfaces:**
- Produces: `discovery_cost` = 常驻描述字符数 × 系数（或模型 tokenizer，若有）；**口径写进 schema**
- Produces: 预算帽（数值由实测确定，见下 Step 3）

**Covers:** C7、R5

- [ ] **Step 1: 实测** — 输出每个 agent 的常驻成本排行（预期发现 TRAE `lark×25` + `trends-hub×21` 是大头）
- [ ] **Step 2: 回填** 账本
- [ ] **Step 3: 定帽** — 用实测分布定（如「常驻 ≤ 现状的 60%」），**帽 ≠ 可抬**；超帽必须降级某项为 `conditional`/`not-installed`

**验收：** 每个 agent 有常驻成本数字；超帽路径可复现

---

## M3 — 任务级装配

### Task 19: 各平台任务级配置可行性调研（**前置门**）

**Files:** Create `docs/compose/reports/2026-10-XX-task-scope-capability-survey.md`

- [ ] **Step 1: 逐平台验证** — pi（`.pi/` 项目级配置 ✔ 已知）、trae、workbuddy、mavis、dsh、hermes：能否**按任务/按项目**装 MCP/skill 并隔离
- [ ] **Step 2: 输出结论表** — 支持 / 不支持 / 部分（含证据：配置路径 + 实测）
- [ ] **Step 3: 定降级方案** — 不支持的平台退化为「session 级 + 结束卸载门禁」

**验收：** 每平台有证据级结论；不支持者已有降级方案

---

### Task 20: `tier-bootstrap` 扩展返回能力建议

**Files:**
- Modify: `hub-engine/engine.py`（`tier-bootstrap` 返回体）
- Modify: pi 计划 T6（`memory-hub.ts` 消费 `capabilities`）
- Create/Modify: `hub-engine/tests/test_cli.py`

**Interfaces:**
- Produces: `{tier, markdown, capabilities: {installed:[], suggested:[], missing:[{id, install, verify, discovery_cost}]}}`
- 硬约束：**只提示不自动装**（改客户端配置前需用户批准）

**Covers:** §5.3、D3

- [ ] **Step 1: 证红** — 断言返回体含 `capabilities.missing`（当前无）
- [ ] **Step 2: 实现** — 账本 ∩ `task_tier` 的 scope → 差集
- [ ] **Step 3: pi 侧提示** — 首轮展示一次「建议能力（含缺失）」，用户可忽略

**验收：** 返回体含三集合；pi 侧可见；无自动安装路径

---

### Task 21: 装 → 用 → 卸 全环（pi 先落地）+ 预算帽联动

**Files:**
- Modify: `memory-hub.ts`（`/hub-cap` 命令：list/install/remove/verify）
- Modify: `.../capabilities/*.yaml`（回收验证）
- Modify: 巡检（卸载门禁：`deploy_scope=task` 残留检测）

- [ ] **Step 1: install** — 经用户确认后写入 task scope 配置（pi：`.pi/mcp.json` 或项目级 skill 目录）
- [ ] **Step 2: verify** — 调用账本的 `verify` 命令证明"确实装上了"
- [ ] **Step 3: remove + verify** — 任务结束卸载并证明"确实卸了"（对齐 P-4：无卸载路径不上架）
- [ ] **Step 4: 残留门禁** — 巡检检测 `deploy_scope=task` 超过 N 天未结算 → warn
- [ ] **Step 5: 结算** — 保留升级为 `project|user`（需批准）或回 `not-installed`

**验收：** pi 上跑通全环且每步有 verify 证据；残留可被检测

---

## 附：任务 → 判据映射

| 判据 | 任务 |
|---|---|
| C1 分型单源 | pi-P0/T3 |
| C2 平台登记单源 | Task 3 |
| C3 尺子双把 | Task 4、5 |
| C4 门禁瘦身 | Task 6 |
| C5 流水线瘦身 | Task 7 |
| C6 等级轴 | Task 12–15 |
| C7 账本对账 | Task 16–18 |
| C8 瘦身结果 | Task 5、8、9、10、11、14 |
