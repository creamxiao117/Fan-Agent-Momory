# 记忆中枢顶层架构重构：分级记忆 + 能力治理（讨论稿 v0.1）

- 日期：2026-10-02
- 性质：**架构讨论稿**（未裁定，不定任务工时；裁定后再转 `plans/`）
- 关联：`blueprints/agent-memory-capability-router-blueprint.md`、`methodology/gh-cap-router-paradigm.md`、`blueprints/skill-governance-blueprint.md`、`methodology/agent-tool-inventory.md`、`docs/compose/plans/2026-10-02-pi-hub-bridge.md`（pi 接入，本稿的落地载体之一）、`docs/compose/specs/2026-09-23-slim-rules-gates-design.md`
- 触发：用户要求「多 agent 共享长期记忆（可分级）」+「MCP/CLI/Skill 统一管理（常驻 / 任务级临时装 / 中途补装）」作为中枢的**主要功能**，并声明既有方案均为过渡方案
- 结论摘要：**不需要新建系统，需要把已有的两套半成品收敛成「两库一协议」**；根因是**缺轴 + 手写枚举**，不是缺功能
- **v0.2 增补（2026-10-02 同日）**：用户追加诉求——「门禁和规则如果不合理也可以重构，陈旧腐烂的一律删除，必须化繁为简」。新增第十/十一节与 M0.5 / M0.6 里程碑。

---

## 一、事实盘点：现在到底有什么（4 套并行资产）

| # | 资产 | 位置 | 形态 | 谁是消费者 | 门禁 | 新鲜度（实测） |
|---|---|---|---|---|---|---|
| A1 | **知识卡** | `AgentMemoryHub/<6 权威区>/*.md`（506 张） | 文件 = 唯一源 | 检索（word/char/vector）、INDEX 渲染 | 有（frontmatter/编码/渲染一致性） | 活 |
| A2 | **规则路由表** | `rules/rules-routing-table.md` + `appendix` | 手写 markdown | 人读；AGENTS.md 引 | 无 | **已腐烂** |
| A3 | **技能直达映射** | `rules/routing-table.json`（v4.0 / 2026-09-21） | 手写 JSON，**只有 2 个 task_type** | 仓内 `scripts/update-routing-table.py` 自产自销 | 无 | **事实死亡** |
| A4 | **平台工具清单** | `methodology/agent-tool-inventory.md` | 手写快照卡（2026-08-18 实采） | 人读 | 无 | **一次性快照，必然腐烂** |
| A5 | **技能路由表** | `SkillHub/router/router.yaml`（v1.1.2）+ `schema.yaml` | 手写 YAML（实现物在 `skills/`） | `bridge/`、`skillhub/cli.py` | 有 schema 校验，**但无「与实际安装态对账」** | 半活 |
| A6 | **平台登记 + 适配器** | `hub.config.yaml.platforms` + `platform_bridge.ADAPTER_REGISTRY` | 手写 YAML/Python | `router_sync.py`、ingest | **有（warn 级覆盖度对账）** | 活 — **这是全项目唯一健康的「声明 vs 实测」范例** |
| A7 | **能力建议器** | `scripts/skill_candidate_suggest.py` | 代码 | 人（周审） | 无 | 活但极窄（只扫 `experience/` 且 `reuse_count≥3`） |
| A8 | **各平台 MCP 配置** | pi `agent/mcp.json`、trae `~/.trae-cn/mcp.json`、workbuddy、mavis、dsh、hermes `config.yaml` | **实测态**（真正的部署事实） | 各平台自身 | `mcp_healthcheck.py` 只查「中枢 MCP 路径可达」 | 活但无登记 |

**覆盖度实测（这就是问题所在）：**

| 轴 | 字段 | 覆盖率 | 备注 |
|---|---|---|---|
| 形态/类型 | `type` | 506/506（100%） | 健康 |
| 生命周期 | `status` | 506/506（100%） | active 316 / reference 116 / candidate 50 / deprecated 15 / archived 8 |
| **等级** | `tier` | **35/506（7%）** | 取值 `iron`/`task`；设计文档写的是 `iron\|task\|ref` → **`ref` 从未落地** |
| 强制读入 | `l1_tier` | 7 张 | 手标，与「派生」原则冲突 |
| 复用信号 | `reuse_count` | 431/506 | 「命中即 +1」，无升级用途 |
| 负路由 | `forgot` | **0 张** | 只在 SkillHub `router.yaml` 有（A5） |

**A2 腐烂举证**（可复现）：`rules/rules-routing-table.md` 正文仍写「`hub-engine/tools/task_tier.py` 的 `L1_CARDS`」，而该符号已于 2026-10-01 由 `l1_tier` frontmatter 派生取代 → **规则路由表描述的实现已不存在**。

---

## 二、根因诊断（为什么"都是过渡方案"）

| # | 根因 | 证据 | 会怎么复发 |
|---|---|---|---|
| D1 | **缺「等级轴」**：用目录（形态）兼职承担了「可信度/强制性」，导致"铁律"与"随手记的坑"在检索里同权 | `tier` 覆盖 7%、`ref` 未落地 | 检索命中噪音；新人/新 agent 无法分辨「必须遵守」与「仅供参考」 |
| D2 | **缺「部署范围轴」**：没有任何地方记录"MCP/CLI/Skill 装在哪一级（本项目/本用户/全局）" | A8 是隐式决定，无登记 | 装了不卸、隐式常驻；换机/换 worktree 就断（pi 的 hub 路径就在 worktree 里） |
| D3 | **双库分裂、无统一 ID**：知识在中枢、能力在 SkillHub，连接仅靠 `reuse_count≥3` 单向建议（A7） | 一个"方法"要同时是卡和 skill 时，两边各写一次 | 同一件事两处维护 → 必然漂移 |
| D4 | **手写枚举必然腐烂**：4 套路由资产全是手写（A2/A3/A4/A5） | 2 套已死/腐烂 | 本项目已复发 3 次（L0 INDEX 枚举行、L1_CARDS 清单、`tier` 覆盖） |
| D5 | **无成本计量**：`discovery cost`（每会话都付）vs `invocation cost`（触发才付）只写在卡里当理念 | `agent-tool-inventory` §3：TRAE 常驻注入 lark×25 + trends-hub 21 工具，多数场景用不到 | 能力只增不减 → 上下文被常驻描述吃掉，无人拦 |
| D6 | **无任务级能力装配**：`hub_bootstrap` 只返回「记忆命中」，不返回「本任务该用什么能力（含缺什么）」 | pi 计划 P1 的返回体只有 `markdown` | 每轮靠模型临场想 → 想到才用，想不到就退化 |
| D7 | **无回收机制**：既然没有"临时装"，自然没有"任务后结算/卸载" | 无任何卸载路径 | 「临时装」退化成「永久装」 |

---

## 三、目标架构：两库一协议（不建议合并仓库）

```
              ┌────────────── 唯一事实源（各自的）──────────────┐
   知识事实源：AgentMemoryHub/<领域目录>/*.md          能力事实源：SkillHub/router/ + capabilities/
              └──────────────────┬──────────────────────────────┘
                                 │  派生层（只读渲染 + 门禁，禁手写）
                    ┌────────────▼────────────┐
                    │   capability · ledger   │  ← 「声明态」纯函数扫描/渲染
                    │  （技能 / MCP / CLI）   │
                    └────────────┬────────────┘
                                 │  对账（desired vs actual）
                    ┌────────────▼────────────┐
                    │  各平台实测态（scanner）│  ← pi mcp.json / trae / workbuddy / mavis / dsh
                    └─────────────────────────┘
   消费方：MCP server（hub_search/bootstrap）· CLI（engine.py）· pi 扩展 · SkillHub CLI · 各平台注入
```

**四条原则（全部沿用本项目已验证的先例，不自创新范式）**

| 原则 | 依据先例 |
|---|---|
| P-1 单源 + 派生只读：清单/路由一律渲染产物，`--check` 门禁 | L0 INDEX + `render_index`、`rules-routing-table-appendix` |
| P-2 形状断言优先、数字帽兜底 | `startup_budget.check_l0_shape`、`check_l1_shape`（单型 ≤3） |
| P-3 声明态 vs 实测态对账，差异即报红（「路由撒谎比没有更糟」） | `router_sync`（A6）+ `schema.yaml` 自述 |
| P-4 无人工批准不装、无实测不升、无卸载路径不上架 | CHARTER「不做无人工提炼」+ gh-cap-router「记录≠实操」 |

**建议的三轴（知识）+ 两轴（能力）——注意：不要复用 `L0/L1/L2` 这三个名字，它们已被 `startup_budget` 占为预算分层**

---

## 四、建议 A：记忆分级（功能 #1）

### 4.1 五级 `grade`（与目录**正交**，不合并）

| grade | 含义 | 判据（可证伪） | 现有对应 | 建议上限 |
|---|---|---|---|---|
| `iron` 铁律 | 违反必返工；每型必读；附可执行门禁 | 有真实返工证据 **且** 有自动门禁/固定格式约束 | 3 张真标 + `global-rules` | ≤ 每型 3（沿用 L1 帽） |
| `proven` 成熟方案 | 已在本项目 T1 亲跑通过的方案/蓝图 | `source` 可追到本项目实测记录；`evidence=t1` | blueprints 里标「t1」者、部分 methodology | 无（按类配额） |
| `domain` 领域知识 | 工具/平台/术语/环境事实（会过期） | 描述的是"世界是什么"，非"该怎么做" | `longterm/`、部分 `projects/` | 无 |
| `task` 任务经验 | 单次任务得到的可复用结论 | 有具体现场（时间/项目/报错） | `experience/` 主体 | 无 |
| `pitfall` 踩坑与错误 | 会**静默失败/假绿**的坑（最危险类，应强制上升） | 失败不可见或假绿，需主动探测 | 散在 `experience/`（如 GB2312、BOM、观测者自污染） | 无 |

要点：
1. **`pitfall` 单列**是因为本机最贵的三次教训全是"静默失败"（`.lsp` 存 UTF-8 零报错、`requirements.txt` 与 `pyproject` 不一致、系统 python 缺 jieba 让 9 个测试静默跳过）。它与 `task` 混在一起时会被当普通经验忽略。
2. **grade 与 `status` 是两条独立轴**（gh-cap-router 已验证）：`iron` 也可能被 `deprecated`（如 `memory-hub-query-first` 已并入 `global-rules`）；`candidate` 也可能是 `pitfall`。
3. **L1 卡集合改为从 grade 派生**（`grade=iron` ∧ 目录=`rules` → 自动进 L1 集），取代手标 `l1_tier`（现仅 7 张）。这顺手修掉一处手写枚举。
4. **升级路径必须可证伪**（否则 grade 会通胀）：
   - `task → proven`：`reuse_count ≥ 3`（复用信号**真正派上用场**）**或** 有记录在案的「避免了一次返工」
   - `proven → iron`：必须同时有 ①返工证据 ②可执行门禁（否则只是"我觉得很重要"）
   - 降级：`status → deprecated/archived`；`pitfall` 一旦被工具固化（如写进 pre-commit）→ 转 `iron` 或退役
5. **落位**：新增 frontmatter `grade:` 字段（不覆用 `tier`，避免与既有 35 张语义打架；`tier` 可标 deprecated 或映射迁移）。

### 4.2 与"检索"的关系（让分级真正有用，而不只是标签）

- `hub_search` / `hub_bootstrap` 返回体带 `grade` → pi 侧注入时**按 grade 排序与截断**：`iron` 全文、`proven` 摘要、`task/pitfall` 一行摘要
- 注入模板分块：`## 铁律（必读全文）` / `## 已验证方案` / `## 相关经验` —— 这直接回答"新 agent 怎么知道哪条必须遵守"
- 负路由 `forgot`（SkillHub 已有，知识侧为 0）：把「不适用/禁止命中」下沉到 frontmatter，检索侧过滤 → 治 `retrieve-english-stopword-overhit` 那类误命中

---

## 五、建议 B：能力治理（功能 #2）

### 5.1 一个账本，三类能力（`kind`）

| kind | 例子 | 唯一源 | 实测态来源 |
|---|---|---|---|
| `skill` | superpowers、memory-hub-card-promotion | `SkillHub/router/router.yaml` | 各平台 skills 目录 |
| `mcp` | `agent-memory-hub`、github、textin-xparse | **新增** `SkillHub/capabilities/mcp.yaml`（或中枢新目录，见待拍板 Q4） | 各平台 `mcp.json`（A8） |
| `cli` | `engine.py`、`scripts/*.py`、pwsh 脚本 | 新增 `capabilities/cli.yaml` | 可执行性探针（`--help`） |

### 5.2 新增字段（在现有 SkillHub schema 上扩展，不推翻）

| 字段 | 取值 | 现状 | 作用 |
|---|---|---|---|
| `deploy_scope` | `not-installed` / `task`（本任务临时）/ `project` / `user` / `global` | ❌ 全新 | **本功能的核心**：常驻 vs 临时 |
| `invoke` | `auto` / `conditional` / `explicit-only` / `disabled` | 现有 2 值（user/model） | 与 scope 解耦：常驻也可 explicit-only |
| `discovery_cost` | token 估算（描述常驻成本） | ❌ | 预算帽的计量单位（可用探针实测） |
| `install` / `uninstall` / `verify` | 命令或步骤 | ❌ | 让「临时安装」可执行、可验证、**可回收** |
| `requires` | 运行时依赖（python 包/venv/服务） | 部分（如 hub 要 `.venv`） | 防 D5 与 R6 类假绿 |
| `grade` / `source_card` | 关联知识卡 | ❌ | 打通两库（**单向引用**：能力 → 卡，不反向维护） |

### 5.3 任务级能力装配（Task Capability Manifest）

```
任务计划（plan）
  → 提取能力需求（按 grade=iron 的 skill 路由 + 计划关键词）
  → 与实测态对比 → 差集 = missing
  → 用户批准 → 临时安装到 task scope（不改 user/global）
  → 任务进行中：发现缺口 → 再申请（中途补装，同样需批准）
  → 任务结束：结算（保留升级 / 卸载回 not-installed）
```

- **接入点**：pi 计划 P1 的 `engine.py tier-bootstrap` **扩展返回体**：
  `{tier, markdown, capabilities: {installed:[], suggested:[], missing:[{id, install, cost}]}}`
- **硬约束**：`suggested/missing` **只提示不自动装**（对齐 `global-rules`：改客户端配置前需用户批准）；卸载必须有 `verify` 证明"确实卸了"（对齐 P-4）
- **与 pi 的天然衔接**：pi 有 project 级 `.pi/` 配置（可承载 task scope）；trae/mavis/dsh 是否支持任务级配置**需先调研**（Q5）

### 5.4 预算帽（让"常驻"有牙齿）

- 口径建议：每 agent 的**常驻 `discovery_cost` 总和 ≤ N token**（N 待定，见 Q7），超帽即门禁报红
- 实测锚点（来自 A4）：TRAE 常驻注入约 65 skill + 27 MCP 工具；`trends-hub` 单 server 21 工具。这些都是"付费但不用"的常驻成本
- 配套动作：超帽时**必须**把某项降为 `conditional` 或 `not-installed`，而不是抬帽（沿用 L0 帽先例的裁定口径）

---

## 六、现有资产处置建议

| 资产 | 处置 | 理由 |
|---|---|---|
| A1 知识卡 | **保留为知识唯一源**；新增 `grade`/`forgot` 字段 | 最大资产，不动结构 |
| A2 规则路由表 | **改为派生**（从卡 frontmatter 渲染）+ `--check`；正文里过期的 `L1_CARDS` 段落删 | 已腐烂；手写必复发（D4） |
| A3 `routing-table.json` | **废弃归档**（或合并进 A5 的账本） | 事实死亡 + 只有 2 条 + 无消费者 |
| A4 工具清单卡 | **改为 M0 scanner 的渲染产物** | 快照卡必然腐烂 |
| A5 SkillHub router | **保留，扩字段**（5.2）+ 补「声明 vs 实测」对账门禁 | 已有 schema 校验，是最接近正解的一环 |
| A6 平台登记/适配器 | **保留并升级为对账范例**（推广到能力账本） | 唯一健康的声明/实测对账 |
| A7 能力建议器 | 扩展：`reuse_count≥3` → 生成 `grade` 升级建议 + `missing` 能力建议 | 已有闸口，复用 |
| A8 平台 MCP 配置 | **保留为唯一实测态**，禁止手工登记重复（登记在账本，实测在配置） | 防双源 |

---

## 七、实施路线（4 个里程碑，每个独立可交付、可验证、可停下）

| 里程碑 | 交付 | 依赖 | 风险 | 判据 |
|---|---|---|---|---|
| **M0 事实固定** | capability scanner：扫各平台 skills/MCP/CLI → 渲染 `capabilities.md`（派生，禁手写）+ `scripts/INVENTORY.json`（§10.7）；`--check` 门禁 | 无 | **零**（只读） | 能复现 A4 的盘点结论且**数据比它新**；`--check` 可红 |
| **M0.5 门禁收敛** | 门禁/规则层重构（§10）：9→3 scope-gated 提交门禁、25→8 步流水线、产物 1 快照、`rules/` 35→~12 | M0 的 INVENTORY | 中（门禁改动风险高 → 先证红再改 + 新旧并行跑一周） | 提交门禁 <2 s；巡检产物 1 个；`rules/` 每张绑门禁或明确检查 |
| **M0.6 清理** | §10.6 A/B/D 类归档 + `_retired` 仪式简化（Q12） | M0.5 | 低（git 兜底） | 模块数 105 → 目标 ≤75；门禁全绿 |
| **M1 等级轴** | `grade` 定义 + 506 张卡批量标注（按规则映射，不改正文）+ 形状门禁 + L1 改由 grade 派生 | M0 不依赖 | 中（标注可能误判 → 需分批 + 抽样复核） | L1 集合与现状差异表（必须为**空或已裁定**）；每型 iron ≤3 |
| **M2 账本协议** | SkillHub 扩 5 字段 + MCP/CLI 纳入 + 声明/实测对账门禁 | M0 | 中 | 对账差异 = 0 或有裁定记录；`discovery_cost` 有实测值 |
| **M3 任务级装配** | `tier-bootstrap` 返回能力建议 + 临时装/结算流程（pi 先落地） | M2、pi P1 | **高**（各平台任务级配置能力未知 → 先调研 Q5） | pi 上跑通「装→用→卸」全环；卸载有 verify 证据 |

**并行关系**：M0 与 pi 接入（P0/P1）**可并行且互相受益**（pi 的 P1 需要账本；M0 顺带产出 pi 的实测数据）。**M1 不建议与 P0 并行**（都改中枢 frontmatter 与门禁，会撞车）。

---

## 八、需要拍板的问题（7 条）

| # | 问题 | 我的建议 |
|---|---|---|
| Q1 | 分级命名与字段名 | 英文 5 档 `grade: iron\|proven\|domain\|task\|pitfall`；**新增** `grade` 字段，不覆用 `tier`（现有 35 张先映射迁移） |
| Q2 | grade 与目录的关系 | **正交**（目录=领域，grade=可信度/强制性）。目录即等级会立刻撞墙（同一目录里既有铁律也有随手记） |
| Q3 | 两库关系 | **保两仓 + 统一协议**（不合并）。合并收益低、迁移成本高，且 SkillHub 有独立 git/CI/部署链 |
| Q4 | MCP/CLI 登记落哪 | **SkillHub `capabilities/`**（与 skill 同库同 schema）；中枢只保留"方法论/事实"卡，不存能力清单（防双源） |
| Q5 | 任务级临时安装的落点 | **先调研**：pi `.pi/` 可用；trae/mavis/dsh/workbuddy 是否有任务级配置**未知**。若都没有 → 退化为「session 级 += 结束后门禁提醒卸载」 |
| Q6 | L1 改为 grade 派生是否会改集合 | 需先算差异（M1 Step 0）。若差异非空，**按差异逐条裁定**，不静默改路由 |
| Q7 | 预算帽口径与数值 | 口径=`discovery_cost` token 估算之和；数值建议先测 pi/trae 实测值再定帽（不拍脑袋），帽 ≠ 可抬 |

## 九、本稿的自我约束（防过度工程）

- 本稿**不新增事实源**（只用 A1/A5 两个既有源），不引入缓存派生文件（沿用 `hub_registry` 裁定）
- 不引入新数据库/向量库；`grade` 与 `forgot` 都是 frontmatter 字段，零基础设施成本
- M0 是**只读**里程碑，先拿数据再谈改造（避免"先架构后现实"）
- 拒绝的选项（本稿明确不做）：合并成单仓、自动安装未经批准的能力、用 LLM 自动判定 grade（可作建议，不可作裁定）、为 MCP 单独建一套 schema

---

## v0.2 增补：门禁 / 规则 / 清理

## 十、门禁与规则层重构

### 10.1 实测：门禁家族的规模与重叠

| 对象 | 实测规模 | 问题 |
|---|---|---|
| **提交时门禁** | 外层 **6 道**（编码 / 预算+形状 / 渲染可复现 / markdownlint / ruff check / ruff format）+ 中枢 **3 道**（渲染一致性 / 编码 / frontmatter）= **9 道** | 编码检查**两处实现**；渲染检查**两处实现** |
| **每日巡检** | WORK.md 记 **25 步**（`patrol/steps.py` 20 个 `_step_*`，`patrol_runner.py` 另有 8 个 `_stage_*`） | 与提交门禁**大面积重复**（ruff / 预算 / 渲染 / markdownlint / 编码） |
| **INDEX 一致性检查器** | **3 个**：`render_index --check`、`index_consistency.py`（自称"单一事实源"）、`audit_index.py` | 三个都自称管 INDEX 一致性 |
| **检索评测脚本** | **5 个**：`recall_regression`、`real_query_regression`、`vector_bench`、`vector_scale_bench`、`index_locatability_bench` | 只有 1 个是门禁，其余是手动基准 |
| **健康/快照采集** | **4 个**：`commands/status.py`(22K)、`hub_health.py`(22K)、patrol `_step_status_snapshot`、`metrics_daily.py` | 四处各自采集"健康" |
| **报告产物** | **≥7 种**：`retro/lint-report-*.md`、`retro/snapshot-*.json`、`.sync/state/review_today.md`、`system/run/daily-6panel.json`、`hub-health.html`、`memory-hub-flywheel-v2.html`、`flywheel-timeline-data.json` | 无人定期看（T1 观测产出率 ≤11%） |
| **hub-engine 模块总数** | **105**（scripts 62 + tools 20 + commands 12 + common 7 + patrol 4） | 无冗余度量 |
| **rules 卡** | **35 张**，其中**只有 13 张**与可执行门禁有关，**22 张是纯文本** | 纯文本规则靠自觉 ⇒ 必然腐烂 |

### 10.2 根因：**现在的尺子量不出冗余**（本节是最重要的一条）

- `audit_dead_modules` 实测输出：**「零引用模块: 0」** —— 但系统明明臃肿。
  原因：**冗余不是「没被引用」，而是「多处引用同一个职责」**。当前只有「零引用」一把尺子，
  缺「**职责重复**」这把尺子。用它量一个职责重复四遍的系统，结果必然是 0。
- 现役退役标准是「**证明它没用，才删**」（正向举证：`_retired/README.md` 要求逐个取证）。
  逻辑后果：**只要还有一处引用就永远留** ⇒ 系统只能只增不减。
  2026-10-01 那批退役 16 件**全部合格**，但它是这个标准的产物——保守到无法矫正结构。
- 建议把默认**反过来**：**保留需要举证**。每个模块必须能回答两问：
  ①它今天拦住了什么（gate role）？②最近 30 天有产出吗（last_run / evidence）？
  答不出 → 降级为 `manual-cli`（留档但移出门禁视野）或归档。
- **证据支持这一转向**：`rule_following_timeseries` 记录巡检**曾连续 18 天未跑**；
  T1 观测周产出率 **≤11%**、重复率 **≥60%**。
  ⇒ **门禁数量与遵循率成反比**：门禁太重就会被绕过，而 `--no-verify` 口径本身就是被训练出来的。

### 10.3 提交门禁：9 道 → 3 道（全部 **scope-gated**）

| # | 门禁 | 触发范围（由 staged 内容决定） | 目标耗时 |
|---|---|---|---|
| 1 | **code**：`ruff check` + `ruff format --check` | staged 含 `.py` | < 1 s |
| 2 | **text**：`check_encoding` + markdownlint | staged 含文本 / `.md` | < 0.5 s |
| 3 | **l0**：`startup_budget` + `render_index --check` | staged 触及 `AGENTS.md`/`CHARTER.md`/`WORK.md`/`INDEX*.md`/权威区卡/渲染器 | ~0.3 s（绝大多数提交不跑） |

**为什么必须 scope-gated（这是实质，不是"少跑几个检查"）：**

- 中枢 pre-commit 现在**无条件**跑渲染一致性 ⇒ 工作树里**任何人**未提交的卡改动会阻断**任何**提交。
  这条缺陷已在案（处置办法是 `--no-verify`）。**一条会让正常操作受阻的门禁，实际效果是
  训练所有人用 `--no-verify`，从而让全部门禁一起失效**。改成 scope-gated 后只对 **staged 内容**
  做可复现性比对 ⇒ 既不丢保护，也不添阻力。
- 预算门禁仅 ~84 ms（实测），但**只在改 L0 文件时才有意义**；scope-gated 后 99% 提交不跑它。
- 编码检查两处实现 → **一处**（唯一入口 `check_encoding.py`，支持 `--fix` 吸收 `strip_bom`）。
- 巡检仍保留这些步骤作为**兜底**（双保险不变），但不再是唯一的发现通道。

### 10.4 每日流水线：25 步 → 8 步，产物 **1 个**

| # | 步骤 | 唯一实现（其余重叠者处置见 §10.6） |
|---|---|---|
| 1 | 索引一致性 | `render_index --check`（唯一） |
| 2 | 卡片健康 | `tools/lint.py`（唯一） |
| 3 | 检索召回回归 | `recall_regression`（唯一门禁；其余 4 个转手动基准） |
| 4 | 平台 / 能力对账 | `router_sync` + M0 scanner（合并 `platform_healthcheck`/`mcp_healthcheck`/`platform_unregistered`） |
| 5 | 密钥哨兵 | `secret_sentry` |
| 6 | 编码巡检 | `check_encoding --all` |
| 7 | 测试 | `pytest` |
| 8 | **产出单一快照** | `retro/snapshot-YYYY-MM-DD.json` + **一份**人读 md（其余报告改为从快照派生或删除） |

### 10.5 规则层：**没有门禁的规则不许叫「铁律」**

- `iron` 资格收紧为：**有可执行门禁或固定格式约束**（否则最高只能是 `proven`/`domain`）
- 22 张纯文本 rules 卡三条出路：
  ①**升门禁**（值得的，如 `dll-version-lock`：加一条版本自检）
  ②**合并进 `global-rules`**（同类纪律；已有先例：原 4 张卡已并入）
  ③**降级为 `pitfall`/经验卡**（本就不是规则，是教训）
- 目标：`rules/` 从 **35 张 → ~12 张**，每张都绑一条门禁或一条明确检查
- `rules-routing-table.md` + `-appendix` + `routing-table.json` **三件 → 一张派生表**（渲染产物 + `--check`）

### 10.6 删除 / 归档候选（按类；**默认归档，复核只为确认判据**）

> 沿用 `_retired/` 既有标签约定（Q12 会建议简化仪式，但标签块本身保留）。

**A 类 · 职责重复（留一个，其余归档）**

| 职责 | 保留 | 归档候选 |
|---|---|---|
| INDEX 一致性 | `render_index --check` | `index_consistency.py`、`audit_index.py`（检测部分并入 `lint`） |
| 未命中查询统计 | `missing_query.py` | `knowledge_gap.py`（1.8K，被前者覆盖） |
| 卡片 schema 修复 | 合并后的单一 `fix-cards` | `auto_fix_lint.py`、`fix_card_schema_drift.py` |
| 编码检查/修复 | `check_encoding --fix` | `nightly_log_encoding_check.py`、`strip_bom.py` |
| 平台/MCP 健康 | 单一 `platform_healthcheck` | `mcp_healthcheck.py`、`platform_sign.py`（若无消费者） |
| 健康快照 | `commands/status.py` | `hub_health.py`、patrol `_step_status_snapshot`、`metrics_daily.py` |
| 报告 | 单一快照 + 一份 md | `hub_daily_report.py`、`lint_report.py`、`hub_review_today.py`、`auto_review_today.py`、`query_report.py` |
| 平台桥 | `platform_bridge`（config 驱动） | `mavis_hub_bridge.py`、`dsh_hub_bridge.py`（若可并入） |

**B 类 · 已完成使命的一次性脚本 → 归档**

`reclassify.py`（21K，2026-08-18 一次性拆卡；活代码引用仅剩测试）、`verify_merge_fidelity.py`、
`index_locatability_bench.py`（改造前后对比已完成）、`vector_scale_bench.py`、`bootstrap_hub.py`、
`demo_e2e.py`、`thin_card_scan.py`（自称一次性）

**C 类 · 原拟归档，但取证后判定保留（记录在此，作为「取证优先于印象」的样例）**

sleep 自进化链：`hub_sleep_consolidate.py` + `auto_sleep_filter.py` + `auto_process_sleep.py`

- 取证结果：`.sync/state/sleep/` 实测**每日两次产出**（`20261002-073015` / `20261002-003506`，往前逐日连续），
  即由 `AgentHub-NightlyConsolidate`(00:35) 与 `AgentHub-DailyPatrol`(07:30) 真实驱动 ⇒ **在跑，不得归档**。
- 唯一遗留问题：产出是否**被消费**（只产不消 = 隐性陈旧）→ 列入 M0 台账的 `consumed` 列考察，
  不作为本轮的删除候选。

> 教训：本节 A/B/D 类均需沿用这个粒度取证（如查 `schtasks` + 产物目录时间戳），不得凭"看起来没人用"裁定。

**D 类 · 文档/卡层腐烂**

| 对象 | 处置 |
|---|---|
| `rules-routing-table.md` 里的 `L1_CARDS` 段落 | **删**（该符号已不存在，描述的实现已换） |
| `rules/routing-table.json` | **废弃**（2 条 + 无消费者） |
| `methodology/agent-tool-inventory.md` | 改为 M0 scanner 的**渲染产物**（禁手写） |
| `INDEX-experience.md` | 评估是否与 `INDEX-full.md` 合并（当前 3 个索引分册） |

### 10.7 防复发：模块台账 + 季度负向举证

一次性清理必然复发（本项目已复发 3 次：L0 枚举行 / `L1_CARDS` / `tier` 覆盖）。机制：

- M0 scanner 顺带产出 `hub-engine/scripts/INVENTORY.json`（**派生，禁手写**），每模块一行：
  `refs_code`（仅活代码引用）/ `last_run` / `gate_role`（承担哪道门禁）/ `verdict`
- 季度门禁：`verdict=unused`（无活引用且无 gate role 且 30 天无产出）→ 生成**归档候选清单**，
  人工裁定一次（不自动删）
- 与 §七 M0 同一把尺子：**声明态 vs 实测态对账**

---

## 十一、v0.2 新增拍板问题

| # | 问题 | 我的建议 |
|---|---|---|
| Q8 | 提交门禁 9 → 3 且全部 scope-gated？ | **是**。这同时修掉「他人未提交改动阻断我的提交 → 训练 `--no-verify`」这条已在案的缺陷 |
| Q9 | 巡检 25 步 → 8 步、产物 1 个？ | **是**。报告产物从 ≥7 种降到 1 快照 + 1 人读 |
| Q10 | 退役默认反转为「保留需举证」？ | **是**。这是唯一能阻止只增不减的机制（§10.2） |
| Q11 | `rules/` 35 → ~12（每张须绑门禁）？ | **是**，但分批：先合并同类，再逐张裁定 iron 资格 |
| Q12 | **「一律删除」与现有「归档优于删除」冲突，怎么裁？** | 见下 |

### Q12 详述：`_retired/` 仪式本身就是过度设计

现状：退役一件需维护 **5 处**：①文件头 6 行标签块 ②`RETIRED.json`（三份）③`_retired/README.md` 段落
④守卫测试 `test_retired_archive.py` ⑤`.ruff.toml` + `test_no_hardcoded_paths.py` + `audit_dead_modules.py`
的排除规则。**16 件退役换来的仪式成本 ≥ 被清理的代码体积。**

而 **git 历史本身就是归档**（`git show <commit>:<path>` 可取回）。

建议：
- **默认直接 `git rm`**，把 `@superseded_by` / `@reason` 写进**结构化 commit message**（信息不丢）
- 只有两类保留实体归档：①**反面教材**（如 `merge-methodology.py` / `deduplicate-experience.py`，护栏本身是资产）
  ②**被卡/文档仍引用**者（此时应先改引用，改不掉才留档）
- 相应**简化**：`RETIRED.json` 三份收敛为一份（或直接用 git log）；
  取消 `test_retired_archive.py` 与逐件登记义务
- 判据：**仪式成本 > 被清理物成本时，删仪式**
