# pi 自动接入记忆中枢（分层自动检索 + 回写）Implementation Plan

- 日期：2026-10-02
- 来源：用户提出「pi 应按任务类型与复杂度自动接入中枢检索，与其他 agent 共享同一份长期记忆」；经一轮方案讨论后裁定：A→C→B 分期、决策点 1–7 全部按建议、**两套分型口径必须统一**、映射表放**中枢**、触发策略=首轮/resume/话题漂移、注入块落 **pi AGENTS.md 顶部**
- 关联：`docs/superpowers/specs/2026-08-18-hub-mcp-server-design.md`（hub_bootstrap 契约）、`AgentMemoryHub/methodology/memory-injection-pattern.md`（双保险范式 + §mavis 三层机制=新平台接入模板）、`docs/compose/plans/2026-10-01-single-source-l0-shape.md`（单源派生 + 迁移零漂移证明先例）、**`docs/compose/plans/2026-10-02-hub-architecture-refactor.md`（架构重构计划，合流顺序见其 §0）**
- 验收判据：C1–C5，见「验收判据」节（**判据不通过即视为未完成**）
- 范围外（另案）：pi 之外的其他平台改造；中枢侧 ingest/distill 自动化变更；向量库/embedding 改造；Web UI；`work/` 归档区任何改动

---

## 一、现状与问题（2026-10-02 实测）

| # | 事实 | 证据 |
|---|---|---|
| F1 | pi 的可执行接入面齐备：扩展（`pi.on` 事件、`registerTool`、`exec`）、Skills、`AGENTS.md`/`APPEND_SYSTEM.md`、MCP（`pi-mcp-adapter` 已装 2.37.0） | `agent/extensions/tps.ts` 唯一扩展；`agent/settings.json` packages |
| F2 | **pi 未接中枢**：MCP 状态 `0/0 servers, 0 tools` | `mcp({action:status})` |
| F3 | pi 的全局 MCP 配置位置 = `<agent-dir>/mcp.json`（`$PI_CODING_AGENT_DIR/mcp.json`），当前**不存在** | `pi-mcp-adapter/dist/config.js:88` |
| F4 | **`.venv` 缺 `mcp` 包**（`jieba`/`yaml`/`numpy` 有）；`hub-engine/pyproject.toml` 声明 `mcp>=1.0`，但 `requirements.txt` **没有** `mcp` → 两处单源不一致，现状靠 hermes venv 兜（其 mcp/jieba 均有） | 实测 `find_spec` |
| F5 | 中枢 MCP 暴露 7 工具；`hub_bootstrap(task_kind, context, platform, top_k, include_body, compress_level)` 只做编排，检索走 `mode="word"`（稳态 4–145 ms，无向量首调开销） | `mcp_server.py`、`mcp_handlers.py:291` |
| F6 | **两套分型并存**：`task_tier.Tier = light\|code\|hub\|sync`（AGENTS 路由 → 读哪些 L1 卡）；`mcp_handlers.TASK_KIND_TYPES = dll\|code\|project\|debug\|ideation\|generic`（bootstrap → 查哪些子区）。键集不相交、知识重复 | 两文件 |
| F7 | 出向/入向通道：出向 `tools/inject.py`（幂等 + 路径自愈，**只追加到尾部**）；入向 `.sync/drafts/<platform>_draft/` **根目录** `*.md` 才会被 `auto_flywheel` 扫到并 ingest | `inject.py`、`auto_flywheel.py:33` |
| F8 | **pi 未登记**：`hub.config.yaml.platforms` 与 `platform_bridge.ADAPTER_REGISTRY` 均无 pi → MCP 回写被 `mcp_policy.allowed_platforms` 拒绝；`router_sync.py` 会以 warn 暴露适配器覆盖缺口 | 两文件 |
| F9 | pi 侧已有用户级长期记忆 `agent/AGENTS.md`（已含中枢路径等事实），但**无「执行前先查」硬约束与检索动作**；`inject.py` 的 `INSTRUCTION` 是尾追加语义 | `hub-engine/tools/inject.py`、实测文件 |
| F10 | pi 扩展**无法直接调用 MCP 工具**（MCP 工具经 `pi-mcp-adapter` 以模型面向的代理工具暴露）→ 确定性预取必须走中枢自己的 CLI/函数 | `pi-mcp-adapter` 架构 |
| F11 | pi 事件面满足需求：`session_start.reason ∈ startup\|reload\|new\|resume\|fork`；`before_agent_start.prompt` + 可改的 `systemPromptOptions.sections`（Pi 会 **diff 后追加增量**，cache 友好）；`ctx.sessionManager.getBranch()`；`agent_settled` | `dist/core/extensions/types.d.ts`、`core/system-prompt.d.ts:65` |
| F12 | `.sync/drafts/` **未被 gitignore**（仅 state/locks/vector.db 等被忽略）→ 草案入仓，须守中枢提交纪律 | `AgentMemoryHub/.gitignore` |

**结论：** pi 缺的不是能力，而是 ①一条接通的通道 ②一条「必须查」的硬约束 ③一次「自动查」的确定性动作 ④一条回写通道；且中枢侧的分型有**双源**必须先修，否则 pi 会变成第三套分型。

## 二、不做什么（防止过度工程）

- **不做每轮检索**：首轮 + resume + 话题漂移三点足够；每轮检索 = 噪声 + 延迟 + 破坏上下文前缀稳定
- **不在 pi 侧复刻任何中枢知识**：分型、卡清单、平台路径、检索范围一律派生自中枢（铁律：单源派生，见 L0 形状门禁先例）
- **不引入新 taxonomy 名**：pi 只使用规范型（`tier`）；legacy `task_kind` 仅作入参兼容层并逐值锁定
- **不做无人工提炼的自动回写**：CHARTER 边界明确「不做无人工提炼」；pi 只写**草案**，且默认需人工触发/确认
- **不改中枢 L0 预算口径**：pi 的 `AGENTS.md` 是 pi 的用户级记忆文件，**不受** `startup_budget` 管辖（那是中枢仓的 `AGENTS.md`）；但托管块自身仍压到 ≈10 行
- **不手改 `INDEX*.md`**、不改 `work/`

## 三、架构裁定（实施时不得偏离）

| 项 | 裁定 | 理由 |
| --- | --- | --- |
| 分型唯一源 | `hub-engine/tools/task_tier.py` **一张表**：规范型 `Tier`（5 型）+ `TIER_SCOPE`（取数范围）+ `LEGACY_KIND_*`（兼容别名，逐值等同今天）+ 唯一解析入口 `scope_for()` / `resolve_kind()` | F6；与 `LEGACY_L1_CARDS` 同款「迁移零漂移」证明手法 |
| 规范型 | `light \| code \| hub \| sync \| project`（新增 `project` = 立项/蓝图，承接 legacy `project`/`ideation` 语义） | 立项必查蓝图是 `global-rules` 铁律，不能因归一而丢 |
| legacy 兼容 | `TASK_KIND_TYPES` 保留为**由表渲染的只读常量**，取值与今天**逐一相等**（测试锁死）；`hub_bootstrap` 新增规范参数 `task_tier`，`task_kind` 标 deprecated | 零行为回归；trae/mavis/deepseek 既有调用不动 |
| pi 检索入口 | **MCP（模型自主深挖）+ `engine.py tier-bootstrap`（确定性预取）**，两者共用 `mcp_handlers.hub_bootstrap`/`hub_search` 实现 | F10；避免「pi 一套、MCP 一套」的第三处口径 |
| pi 注入点 | `event.systemPromptOptions.sections["hub-context"]`（首轮/resume/漂移时写一次，内容稳定→Pi 只追加一次 delta） | F11；**不**替换 `systemPrompt`（会整段失效 cache） |
| 常驻硬约束 | 注入到 pi `agent/AGENTS.md` **顶部**，托管块带 BEGIN/END 标记，由 `inject.py` 维护（幂等 + 路径自愈 + 位置自愈） | 用户裁定；范式见 `memory-injection-pattern.md` §2「放最顶部」 |
| 中枢路径单源 | pi 侧唯一手写处 = `agent/mcp.json`；扩展**不硬编码路径**，按 `AGENT_MEMORY_HUB` → `mcp.json` 的 `--root` 解析，解析不到则**禁用并提示** | F3；worktree 路径易漂移，必须有单一处 + 可检查 |
| pi 回写 | 只写 `AgentMemoryHub/.sync/drafts/pi_draft/` **根目录**；ingest 仍归 Hermes（07:40 cron） | F7/F12；单写者纪律 |
| 平台角色 | pi = `contributor`（与 trae/code/workbuddy/mavis/deepseek 同级） | 现状分工 |

## 四、验收判据（C1–C5）

- **C1 分型单源**：`rg -n "TASK_KIND_TYPES|TASK_KIND" hub-engine` 的命中只有 ①`task_tier.py` 的表定义 ②`mcp_handlers.py`/测试的**引用**，无第二处枚举；`rg -n "dll.*ideation|ideation.*generic"` 无手写键集
- **C2 迁移零漂移**：`test_task_tier.py::test_legacy_kind_types_unchanged` 断言 `TASK_KIND_TYPES` 与 2026-10-02 快照**逐值相等**；`pytest` 733+ 全绿、ruff 全绿
- **C3 通道可用**：`mcp` 状态 ≥1 server / 7 tools；手动 `hub_search(platform="pi")` 返回命中，且 `AgentMemoryHub/.sync/query.log.jsonl` 出现 `platform:"pi"` 记录
- **C4 自动预取（端到端）**：pi 新会话提交一个 code 型任务 → ①`query.log.jsonl` 有 `platform:"pi"` 的 `bootstrap` 记录 ②该轮 system prompt 含 `hub-context` 段且含「中枢命中」 ③**同一会话内 light 型提问不产生任何检索记录** ④注入 ≤1000 token（估算）
- **C5 回写闭环**：`.sync/drafts/pi_draft/` 根目录出现一张合法卡；`python -m scripts.auto_flywheel --root ../AgentMemoryHub --dry-run` 能扫到它；`router_sync.py` 退出码 0（pi 无覆盖缺口告警）

## 五、Global Constraints

- 解释器一律 `..\.venv\Scripts\python.exe`（系统 python 缺 jieba → 9 个检索测试静默跳过＝假绿）
- 测试在 `hub-engine/` 下跑：`cd hub-engine && ..\.venv\Scripts\python.exe -m pytest ...`
- 编码：`.py`/`.md`/`.ts`/`.json` 一律 **UTF-8 无 BOM**（过 `scripts/check_encoding.py`）
- 中枢是嵌套仓：改动走 `git -C AgentMemoryHub`；**跨仓改动两仓提交相邻**（message 互引），保证 `git bisect` 不停中间态
- `INDEX.md` / `INDEX-full.md` / `INDEX-experience.md` 是渲染产物：改卡后跑 `python -m scripts.render_index --write`，**禁手改**；`render_index --check` 必须 0
- pre-commit 渲染一致性是**无条件跑**的：若失配源于**他人未提交**的卡改动 → `git add -- <仅自己的文件>` + `git commit --no-verify`，并在 message 写明原因；**不得**擅自 `render_index --write` 把他人在途改动烘进索引
  - ⚠️ **本条在架构重构计划 Task 6（门禁 9→3 scope-gated）落地后作废**：届时渲染检查只比对 staged 内容，不再被他人未提交改动阻断，`--no-verify` 的合法用途归零。两计划并行期间以「当时生效的门禁行为」为准，并在 Task 6 并行期结束后同步删掉本条 |
- 每任务收尾：相关 `pytest` + `ruff check` + `ruff format --check` 全绿；新增 `.md` **markdownlint 0 违规**（不进 `.markdownlintignore` 基线）
- **先证红再改**：每条行为/门禁变更先写失败用例（负样本）再改实现
- pi 侧：扩展**不引入 npm 依赖**（无自定义工具注册 → 不需要额外 schema 库）；不改 `agent/settings.json` 的既有键
- 中枢写盘一律走单写者锁（`from sync import _WriteLock`）——**pi 侧不触发 ingest/distill/build-vectors**

## 六、风险与反模式对照（上一轮清单 → 本计划的硬性护栏）

| # | 反模式 | 本计划的护栏 | 判据 |
|---|---|---|---|
| R1 | **双事实源**（分型/卡清单在 pi 侧复刻） | Task 3 单表 + `scope_for()` 唯一入口；Task 6 扩展**只调中枢 CLI**，不做任何本地分类/检索；扩展内不出现卡名或子区名字面量 | `rg "rules\|methodology\|blueprints" memory-hub*.ts` 命中 0；C1 |
| R2 | **prompt cache 失效** | 只写 `systemPromptOptions.sections["hub-context"]`（Pi diff 后追加增量），且同会话内容稳定；**禁**改 `systemPrompt` / `context_with_system` | Task 6 Step「cache 守卫」断言 |
| R3 | **注入噪声**（light 任务也被注） | `light` 型**不调用**中枢、不写 section；`tier-bootstrap` 对 light 返回 `skipped:true` 且不写审计 | C4③ |
| R4 | **回写越权 / 自噬** | 只写 `drafts/pi_draft/` 根目录；**禁**递归扫描；扩展不解镜像目录 | C5；`auto_flywheel.scan_drafts` docstring |
| R5 | **L0 膨胀** | 托管块 ≈10 行 + 只放「必须查/搜不到问用户/回写」三条铁律，细节靠 MCP/CLI | Task 2 Step4（行数断言） |
| R6 | **解释器漂移（假绿）** | Task 1 把 `mcp>=1.0` 补进 `requirements.txt`，pi 的 `mcp.json` 指向 `.venv` python；测试统一 `.venv` | C3；`router_sync`/`platform_healthcheck` |
| R7 | **平台未登记静默失败** | Task 4 三处同改（`hub.config.yaml` + `ADAPTER_REGISTRY` + draft 目录）+ `router_sync` 绿 | C5 |
| R8 | **路径漂移**（worktree 变动） | 扩展不硬编码；`mcp.json` 唯一手写处；`platform_healthcheck` 增 pi 可达性检查（warn 级） | Task 4 Step4 |
| R9 | **超时阻塞首轮** | 1.5 s 超时 + 失败静默降级 + 状态栏提示；`mode="word"`（无向量首调 6.7 s 问题）；不重试 | Task 7 |
| R10 | **漂移检测抖动**（每轮重取） | Jaccard 阈值 + 本轮最少词数 + 同会话重取上限 5 + 每轮 ≤1 次 | Task 6 Step「参数表」 |
| R11 | **废弃卡引用** | 不引 `rules/memory-hub-query-first.md`（已 deprecated，并入 `global-rules`）；引用 `global-rules` / `memory-injection-pattern` | Task 2/12 文档审查 |
| R12 | **污染他人改动** | 提交纪律见 Global Constraints（`--no-verify` 口径） | 每任务收尾 |

## 七、Gate 0（动手前必须验证的 4 项，任一失败先修）

| # | 验证 | 命令/方法 | 失败处置 |
|---|---|---|---|
| G1 | `.venv` 能跑 mcp server | `..\.venv\Scripts\python.exe -c "import mcp"`（当前 **False**） | Task 1 先做 |
| G2 | 中枢 MCP 端到端可用 | 临时 `mcp.json` + `mcp` 状态 + `hub_search` 手调 | Task 1 |
| G3 | `drafts/pi_draft/` 可写且未被 ignore | `git -C AgentMemoryHub check-ignore -v .sync/drafts/pi_draft/x.md` | Task 4 |
| G4 | `render_index --check` 当前是绿的（记录基线，防「越改越红」） | `cd hub-engine && ..\.venv\Scripts\python.exe -m scripts.render_index --check` | 记录基线，先归因再动 |

---

## P0 — 接通 + 被要求查 + 分型统一 + 登记（只读接入，零 pi 代码）

> 交付物：pi 能查（MCP）、被要求查（AGENTS.md 顶部硬约束）、分型单源、pi 平台登记在册。**此阶段结束即可用，不依赖任何 pi 扩展。**

### Task 1: 解释器单源归位（消 R6）+ pi 全局 MCP 接通

**Files:**
- Modify: `hub-engine/requirements.txt`（补 `mcp>=1.0`，与 `pyproject.toml` 对齐）
- Create: `../PiAgent/agent/mcp.json`（仓外；`D:\Program Files (x86)\PiAgent\agent\mcp.json`）
- Modify（可选）: `mcp.example.json`（补 pi 段落注释，作为他机复刻样例）

**Interfaces:**
- Produces: `<agent-dir>/mcp.json` → `mcpServers["agent-memory-hub"] = {command: "<repo>\\.venv\\Scripts\\python.exe", args: ["<repo>\\hub-engine\\mcp_server.py", "--root", "<repo>\\AgentMemoryHub"]}`
- Consumes: 既有 `hub-engine/mcp_server.py --root <hub>`

**Covers:** C3、R6

- [ ] **Step 1: 证红** — 记录基线：`..\.venv\Scripts\python.exe -c "import mcp"` → 当前 `ModuleNotFoundError`（F4）
- [ ] **Step 2: 补依赖（单源）** — `requirements.txt` 增 `mcp>=1.0`；`..\.venv\Scripts\python.exe -m pip install -r hub-engine/requirements.txt`
- [ ] **Step 3: 写 `mcp.json`** — 路径用**绝对路径**、正斜杠（与 `mcp.example.json` 同风格）；`--root` 指 `AgentMemoryHub`
- [ ] **Step 4: 端到端验证（G2）** — `mcp` 状态应显示 1 server / 7 tools；`hub_search(query="dll 版本锁", platform="pi")` 返回命中
- [ ] **Step 5: 审计落盘验证** — 确认 `AgentMemoryHub/.sync/query.log.jsonl` 末条 `platform:"pi"`（C3）
- [ ] **Step 6: 记录** — 在 `docs/compose/reports/` 追加一行「pi MCP 接通实测（server/tools/首调耗时）」

**验收：** `.venv` 内 `import mcp` 成功；`mcp` 状态 1/7；手调返回命中且审计含 `platform:"pi"`

---

### Task 2: 常驻硬约束注入 pi AGENTS.md 顶部（`inject.py` 增 top 模式）

**Files:**
- Modify: `hub-engine/tools/inject.py`（新增 `position` 语义 + BEGIN/END 托管标记 + 位置自愈）
- Modify: `hub-engine/tests/test_inject.py`（新增顶部注入/幂等/位置自愈/字节稳定用例）
- Modify（仓外产物）: `D:\Program Files (x86)\PiAgent\agent\AGENTS.md`

**Interfaces:**
- Produces: `inject_instruction(target: str|Path, *, position: Literal["top","bottom"]="bottom") -> Path`
- Produces: 托管块常量 `INSTRUCTION`（新增顶部版文案，含「必须查 / 唯一权威路径 / 搜不到问用户 / 收尾回写」）
- Consumes: `hub_location()`（既有，动态推导中枢绝对路径）

**Covers:** C4② 前提、R5、R11

- [ ] **Step 1: 证红** — 新用例：对含既有内容的文件 `inject_instruction(pos=top)` → 断言托管块在**首行之前**（当前实现必然失败）
- [ ] **Step 2: 实现 top 模式** — 复用既有「marker 命中 → 位置过期则整块刷新」逻辑，改为「首部块」；保持幂等（第二次调用字节不变）
- [ ] **Step 3: 写文案（≈10 行硬上限）**

  ```markdown
  <!-- BEGIN memory-hub-bridge（由 hub-engine/tools/inject.py 维护，勿手改） -->
  ## 【强制·最高优先级】执行前先查统一记忆中枢

  - 涉及规则/规范/约定/经验/历史踩坑的任务，动手前必须先检索中枢：
    MCP `hub_bootstrap` / `hub_search`，或 `python <hub>/hub-engine/engine.py retrieve --root <hub> "<问题>"`。
  - 中枢唯一权威路径：`<hub>/AgentMemoryHub`。禁止臆测、禁止用旧路径、禁止绕过检索直接翻目录。
  - 命中以「引用+摘要」进任务上下文；**规则类命中必须读卡全文**再动手（`hub_get`）。
  - **搜不到必须交回用户询问**，不得自作主张写新卡。
  - 收尾：可复用结论用 `hub_ingest_candidate(platform="pi")` 写草案区（`.sync/drafts/pi_draft/`），ingest 归 Hermes。
  <!-- END memory-hub-bridge -->
  ```
- [ ] **Step 4: 行数/预算断言** — 测试断言托管块 ≤ 12 行且 ≤ 700 字符（防 L0 膨胀，R5）
- [ ] **Step 5: 写入 pi AGENTS.md（需向用户展示 diff 后再写）** — 同时**归并**第 1 节里与新块重复/冲突的条目（保留 pi 特有的路径事实，删除重复的检索纪律）；编码 UTF-8 无 BOM
- [ ] **Step 6: 验证** — `..\.venv\Scripts\python.exe -m tools.inject "<pi>/AGENTS.md"` 二次执行应「无变化」；`pi` 新会话 system prompt 顶部可见该块

**验收：** 托管块在文件最顶部；二次注入字节不变；pi 会话可见；`test_inject.py` 全绿

---

### Task 3: 分型统一（中枢单表 + 唯一解析入口 + 规范 `task_tier` 参数）

**Files:**
- Modify: `hub-engine/tools/task_tier.py`（**核心**）
- Modify: `hub-engine/tools/mcp_handlers.py`（`TASK_KIND_TYPES` 改为派生）
- Modify: `hub-engine/mcp_server.py`（`BOOTSTRAP_SCHEMA` 增 `task_tier`，`task_kind` 标 deprecated）
- Modify: `hub-engine/tools/inject.py`（指令文案里的型名清单）
- Modify: `AGENTS.md`（路由表加 `project` 行）
- Modify: `hub-engine/tests/test_task_tier.py`、`hub-engine/tests/test_blueprint.py`
- Create: `hub-engine/tests/fixtures/task_kind_snapshot_2026-10-02.json`（迁移基准快照）

**Interfaces:**
- Produces: `Tier = Literal["light","code","hub","sync","project"]`
- Produces: `TIER_SCOPE: dict[Tier, tuple[str, ...]]`（型 → 检索子区；`light` = `()`）
- Produces: `LEGACY_KIND_ALIAS: dict[str, Tier]`（`dll/code/debug→code`，`project/ideation→project`，`generic→hub`，`light/hub/sync→本身`）
- Produces: `LEGACY_KIND_SCOPE: dict[str, tuple[str, ...]]`（**取值 = 2026-10-02 快照**，逐值不变）
- Produces: `resolve_kind(name: str) -> Tier`（未知 → `hub`）、`scope_for(name: str) -> tuple[str,...]`（未知 → `generic` 范围）——**唯一解析入口**
- Produces: `TASK_KIND_TYPES: dict[str, tuple[str,...]]`（兼容导出，由表渲染，逐值等同今天）
- Produces: `classify(prompt) -> Tier` 增 `project` 关键词（立项/蓝图/选型/新项目/技术路径/方案对比）
- Produces: `l1_cards()` 的 out-dict 增 `"project"` 键（L1 卡由 `l1_tier` frontmatter 派生，本任务不新增卡）
- Consumes: `mcp_handlers.hub_bootstrap`

**Covers:** C1、C2、F6

- [ ] **Step 1: 快照证红** — 先生成今天的 `TASK_KIND_TYPES` 快照（逐值），写用例 `test_legacy_kind_types_unchanged`（当前应**通过**）；再写 `test_tier_scope_is_single_source`（断言 `TASK_KIND_TYPES` 的定义处只有 `task_tier.py`，当前**失败**）
- [ ] **Step 2: 单表落地** — 按 Interfaces 实现；`TASK_KIND_TYPES` 改为 `{k: scope_for(k) for k in LEGACY_KIND_ALIAS}`（或由 `LEGACY_KIND_SCOPE` 渲染）
- [ ] **Step 3: 行为差异表写入 docstring** — 明确：legacy 键**零行为变化**（R 值逐值锁定）；新增型 `project`；`classify` 新增 project 关键词；未知 kind 仍回退 `generic` 范围
- [ ] **Step 4: `hub_bootstrap` 支持规范参数** — 解析顺序 `task_tier`（规范）→ `task_kind`（deprecated，warning 级日志）→ 缺省 `generic`；`light` 返回 `{ok:true, task_tier:"light", skipped:true, blocks:[], markdown:""}` 且**不写审计**
- [ ] **Step 5: schema 与文案同步** — `mcp_server.BOOTSTRAP_SCHEMA` 增 `task_tier`；`inject.py` 指令的型名清单改 5 型
- [ ] **Step 6: AGENTS.md 路由表加 `project` 行**（关键词兜底：立项/蓝图/选型/新项目）；跑 `startup_budget`（`check_l1_shape` 须 0 违规）
- [ ] **Step 7: 全绿** — `pytest`（含 `test_blueprint`/`test_mcp_server`）+ ruff + `startup_budget` + markdownlint

**验收：** C1、C2 通过；`hub_bootstrap(task_tier="project", context="立项选型")` 的 `blueprints` 块有命中；`hub_bootstrap(task_tier="light")` 返回 `skipped:true` 且无审计

---

### Task 4: pi 平台登记（回写通道 + 漂移可见）

**Files:**
- Modify: `AgentMemoryHub/hub.config.yaml`（`platforms.pi`）
- Modify: `hub-engine/tools/platform_bridge.py`（`ADAPTER_REGISTRY["pi"] = MdSectionAdapter`）
- Create: `AgentMemoryHub/.sync/drafts/pi_draft/.gitkeep`
- Modify: `hub-engine/scripts/platform_healthcheck.py`（pi 记忆文件 + `mcp.json` 可达性检查，**warn 级**）
- Modify: `hub-engine/tests/`（router_sync / platform_bridge 相关，按实际夹具）

**Interfaces:**
- Produces: `platforms.pi = {memory_dir: "D:/Program Files (x86)/PiAgent/agent", target_file: "AGENTS.md", role: contributor}`
- Consumes: `mcp_policy.allowed_platforms()`（自动放行 pi）、`auto_flywheel.scan_drafts`（自动扫 `pi_draft/`）

**Covers:** C5、R7、R8、R4

- [ ] **Step 1: 证红** — `python -m scripts.router_sync --root ../AgentMemoryHub`：确认 pi 未登记时的 warn 输出（基线）
- [ ] **Step 2: 登记三件套** — `hub.config.yaml` + `ADAPTER_REGISTRY` + draft 目录（**根目录**语义，`.gitkeep` 只为占位）
- [ ] **Step 3: 回写冒烟** — `hub_ingest_candidate(platform="pi", title=..., body=..., type="exp")` → 落 `pi_draft/` 根目录；`auto_flywheel --dry-run` 扫到；随后**删除冒烟卡**（避免污染）
- [ ] **Step 4: 漂移可见（R8）** — `platform_healthcheck` 增检查：`<agent-dir>/mcp.json` 存在、`--root` 路径可达、`command` 解释器存在；失败为 warn 不 fail（同现有口径）
- [ ] **Step 5: 全绿** — `router_sync` 退出码 0；相关 pytest + ruff

**验收：** C5 通过；`router_sync` 无 pi 告警；`platform_healthcheck` 输出 pi 三项全 ok

---

## P1 — 确定性预取扩展（pi 侧首次写码）

> 交付物：`memory-hub.ts` —— 首轮 / resume / 话题漂移三点自动预取，cache 友好注入，超时降级，手动命令与开关。

### Task 5: 中枢 CLI 预取入口 `engine.py tier-bootstrap`（先做中枢侧，扩展只做壳）

**Files:**
- Modify: `hub-engine/engine.py`（新增子命令）
- Modify: `hub-engine/tests/test_cli.py`（新增用例）
- (Reuse) `tools/task_tier.scope_for`、`tools/mcp_handlers.hub_bootstrap`

**Interfaces:**
- Produces: `engine.py tier-bootstrap --root <hub> --context "<文本>" [--platform pi] [--top-k 3] [--compress-level 1] [--json]`
  输出 JSON：`{ok, tier, scope:[...], skipped:bool, markdown:str, hit_count:int, audit_id:str, elapsed_ms:int}`
- Consumes: `task_tier.classify`（自动分型）+ `task_tier.scope_for` → `mcp_handlers.hub_bootstrap`
- 预留：`--tier` 参数可强制指定型（供 `/hub` 手动命令与调试），缺省自动判定
- 关键：**与 MCP 走同一 handler**（同审计、同 reuse 计数、同 policy），不新增检索实现（R1）

**Covers:** C4、R1、R9

- [ ] **Step 1: 证红** — 用例：`tier-bootstrap --context "帮我 commit 并跑 ruff"` → `tier=="code"`、`hit_count>0`、审计落一条（当前无该子命令 → 失败）
- [ ] **Step 2: 实现** — 薄封装（≤60 行）：分类 → `hub_bootstrap(task_tier=..., context=..., platform="pi", top_k, compress_level, include_body=False)` → 组装 JSON（`markdown` 直接取 handler 已生成的引导块）
- [ ] **Step 3: light 短路** — `tier=="light"` → `skipped:true`、`markdown:""`、**不落审计**
- [ ] **Step 4: 性能基线** — 断言 ≤1.5 s（`mode="word"`，无向量）；实测值写入报告
- [ ] **Step 5: 全绿** — pytest + ruff

**验收：** 命令产出稳定 JSON；code/hub/sync/project 四型均能返回引导块；light 短路无审计；≤1.5 s

---

### Task 6: `memory-hub.ts` 扩展 — 触发、分型、注入

**Files:**
- Create: `D:\Program Files (x86)\PiAgent\agent\extensions\memory-hub.ts`
- (Dev) `D:\Program Files (x86)\PiAgent\agent\extensions\memory-hub.core.ts`（纯函数：漂移判定、摘录、降级——便于单测）

**Interfaces:**
- Consumes: `engine.py tier-bootstrap --json`（经 `pi.exec`）
- Consumes: `process.env.AGENT_MEMORY_HUB` → else `<agent-dir>/mcp.json` 的 `agent-memory-hub` `args[--root 之后]` → else 禁用（R8）
- Produces: `event.systemPromptOptions.sections["hub-context"] = markdown`（**唯一注入点**，R2）
- Produces: session 状态（`pi.appendEntry("hub-context-state", {...})`：已注入 query 的词集哈希、重取次数）

**触发与参数表（写进代码注释，作为可复查口径）：**

| 触发 | 条件 | 动作 |
|---|---|---|
| 首轮 | `session_start.reason ∈ {startup,new,fork}` 后首次 `before_agent_start` | 用当前 `prompt` 预取 |
| resume | `reason=="resume"` 后首次 `before_agent_start` | `prompt` 长度 < 8 时，取 `getBranch()` 中最近一条 user 消息（截断 200 字）拼接作为 context |
| 漂移 | 每轮：`jaccard(本轮词集, 已注入 query 词集) < 0.2` 且 本轮词数 ≥ 3 | 重取一次并更新 section |
| 上限 | 同会话重取 ≤ 5 次；每轮 ≤ 1 次；距上次重取 ≥ 30 s | 防抖（R10） |
| light | `tier == "light"` | 不注入、不写 section、状态栏显示 `中枢 light`（R3） |

**Covers:** C4、R1、R2、R3、R8、R9、R10

- [ ] **Step 1: 骨架 + 解析器** — hub root 三段式解析（env → mcp.json → 禁用）；禁用时 `ctx.ui.setStatus("hub","中枢:未配置")`
- [ ] **Step 2: 首轮预取** — `before_agent_start` 首次：`exec(venvPython, [engine.py, "tier-bootstrap", "--root", hub, "--context", q, "--platform", "pi", "--top-k", "3", "--compress-level", "1", "--json"])` → 解析 JSON
- [ ] **Step 3: 注入（cache 守卫）** — 写 `sections["hub-context"]`；**断言**不触碰 `systemPrompt`、不注册 `context_with_system`；section 内容含 `<!-- hub-query: <hash> -->` 以便 resume 时复用
- [ ] **Step 4: resume 语义** — 若 branch 中已有同一 `hub-query` 哈希 → 不重复预取，仅沿用
- [ ] **Step 5: 漂移检测** — `core.ts` 纯函数 `shouldRefetch(prevWords, curWords)`；单测覆盖阈值边界
- [ ] **Step 6: 降级与超时** — 1.5 s 超时 / 非 0 退出 / JSON 解析失败 → 静默跳过 + `ctx.ui.setStatus("hub","中枢:离线")`；**不重试、不抛给模型**（R9）
- [ ] **Step 7: 命令** — `/hub`（手动检索并回显命中，走 `hub_search` CLI 同源）、`/hub-on` / `/hub-off`（会话级开关，写入 `appendEntry`）
- [ ] **Step 8: reload 验证** — `/reload` 后无残留进程/定时器（遵守扩展生命周期契约：长资源只在需要时起，`session_shutdown` 幂等清理）

**验收：** C4 四项全过；`rg "rules|methodology|blueprints|experience" memory-hub*.ts` 命中 0（R1）；light 提问零检索

---

### Task 7: 扩展单测与冒烟

**Files:**
- Create: `D:\Program Files (x86)\PiAgent\agent\extensions\memory-hub.core.test.mjs`（Node 22 `--experimental-strip-types` 直跑纯函数）
- Modify: `hub-engine/tests/test_cli.py`（`tier-bootstrap` 契约用例，Task 5 已含）

**Covers:** R2、R3、R10

- [ ] **Step 1: 纯函数单测** — 漂移阈值（0.2 边界）、`prompt<8` 的 resume 摘录、markdown 截断（≤1000 token 估算）、`hub-query` 哈希稳定性
- [ ] **Step 2: 冒烟脚本** — PowerShell 一步跑：单测 → 手调 `tier-bootstrap` → 打印注入内容预览（便于人工核对）
- [ ] **Step 3: 负样本** — hub root 不存在 / python 不存在 / JSON 损坏 → 断言降级路径（不抛异常）

**验收：** 单测全绿；负样本三条均静默降级

---

### Task 8: P1 收口 — 预算与可观测

**Files:**
- Modify: `docs/compose/reports/2026-10-03-pi-bridge-measurement.md`（Create）
- Modify: `hub-engine/scripts/query_report.py`（若已有 platform 过滤则仅补文档）

**Covers:** C4④、R5

- [ ] **Step 1: 注入预算实测** — 记录 section 字符数与 token 估算（目标 ≤1000）；超限则调 `--top-k`/`--compress-level`
- [ ] **Step 2: 命中率抽测** — 用 5 类真实任务（code/hub/sync/project/light）各 1 条，记录 tier、命中卡、是否人工判定有用
- [ ] **Step 3: 审计统计** — `python -m scripts.query_report --platform pi`（或等价）输出 pi 的检索次数/耗时分布

**验收：** 报告落盘；token ≤1000；light 桶检索次数为 0

---

## P2 — 回写闭环 + 审计

### Task 9: 收尾回写（人工确认制，不做无提炼自动写）

**Files:**
- Modify: `memory-hub.ts`（`agent_settled` → 提醒 + `/hub-write` 命令）
- Modify: `hub-engine/tools/mcp_handlers.py`（如需，补充返回体字段；一般无需改）

**Interfaces:**
- Produces: `/hub-write <title>` → 从本会话导出「结论草稿」→ `hub_ingest_candidate(platform="pi", type="exp", tags=[...], slug=...)`
- 约束：`type ∈ [exp, note, project]`（`rule/methodology` 禁直写）；frontmatter 必填 `type/tags/updated` + `status: candidate`；kebab-case slug

**Covers:** C5、R4

- [ ] **Step 1: 收尾提醒** — `agent_settled`：若本会话出现过写操作且含「结论型」输出 → 状态栏/通知提示「可 `/hub-write` 沉淀」（**不自动写**）
- [ ] **Step 2: `/hub-write` 实现** — 生成卡（标题/标签/正文从会话摘要提炼，**必须给出预览供用户确认后再落盘**）
- [ ] **Step 3: 落盘路径** — `hub_ingest_candidate` → `.sync/drafts/pi_draft/` 根目录（R4）
- [ ] **Step 4: 冒烟** — 落一张真卡（例如本计划的实施经验），验证 `auto_flywheel --dry-run` 扫到

**验收：** C5；草案卡 frontmatter 合法（过 `check_card_frontmatter`）；未自动写任何卡

---

### Task 10: 审计与失败可见

**Files:**
- Modify: `hub-engine/scripts/hub_daily_report.py` 或 patrol 步骤（把 pi 检索纳入日报/巡检统计）
- Modify: `hub-engine/scripts/patrol/`（如需新增一步）

**Covers:** C3、C4

- [ ] **Step 1: 平台维度统计** — 日报/巡检输出各平台（含 pi）检索次数、bootstrap 占比、命中卡 Top
- [ ] **Step 2: 失败可见** — 扩展的降级事件（超时/解析失败）写入 `<agent-dir>/` 日志或 pi 通知；巡检检查「pi 近 7 天零检索」→ warn（通道死掉的早期信号）

**验收：** 巡检输出含 pi 行；人为制造 hub 离线 → 出现 warn

---

## P3 — 度量、回归与沉淀

### Task 11: 回归与门禁总检

**Covers:** C1–C5、R1–R12

- [ ] **Step 1: 全量门禁** — `cd hub-engine && ..\.venv\Scripts\python.exe -m pytest`（≥733 通过）+ `ruff check` + `ruff format --check` + `startup_budget`
- [ ] **Step 2: 中枢渲染一致性** — `python -m scripts.render_index --check`（0）
- [ ] **Step 3: 平台与巡检** — `router_sync`（0）、`platform_healthcheck`、`python -m scripts.recall_regression`（≥90%，防检索侧被改坏）
- [ ] **Step 4: markdownlint** — 新增/修改的 `.md` 0 违规
- [ ] **Step 5: 端到端重跑** — C3/C4/C5 三条判据逐条复现并留档（命令 + 输出片段）

**验收：** 全绿；C1–C5 有可复现证据

---

### Task 12: 沉淀与文档

**Files:**
- Create: `AgentMemoryHub/.sync/drafts/pi_draft/pi-auto-hub-retrieval-bridge.md`（经验卡草案，交 Hermes ingest）
- Modify: `AgentMemoryHub/methodology/memory-injection-pattern.md`（补 pi 为第 6 平台接入路径，if user 同意 → 走草案 + 维护者晋升，**贡献者不直写权威区**）
- Modify: `WORK.md`（当前状态 + 待办）、`RUNLOG.md`（本轮小结）
- Modify: `hub-engine/tools/inject.py` 指令文案（若 Task 3 未覆盖全）

**Covers:** R11

- [ ] **Step 1: 经验卡草案** — 内容：分层架构（L0 硬约束 / L1 预取 / L2 深挖 / 回写）、分型统一裁定与零漂移证明手法、扩展不调 MCP 而走 CLI 同源的理由、cache 友好注入点、踩坑（`.venv` 缺 mcp / `inject.py` 只支持尾部）
- [ ] **Step 2: 平台接入模板更新** — 以**草案**形式提交「pi = 第 6 平台，三层机制（硬约束注入 + 确定性预取 + 回写草案）」，不直写 `methodology/`
- [ ] **Step 3: 索引与仓** — `render_index --write`；`git -C AgentMemoryHub` 与主仓**相邻两次提交**；`INDEX*` 不手改
- [ ] **Step 4: WORK.md 收口** — 状态行、门禁行、待办表更新（含 T1 重跑 ≥2026-10-07 不受影响）

**验收：** 草案卡在 `pi_draft/` 根目录；`render_index --check` 0；两仓提交相邻且 message 互引；WORK.md 反映现状

---

## 八、执行顺序与停止点

```
Gate 0 ──► P0(T1→T2→T3) ──► ★架构计划 Task 3（平台元数据单源化）──► P0(T4)
                                                                    │
                                ┌───────────────────────────────────┘
                                ▼
     P1(T5→T6→T7→T8) ──► P2(T9→T10) ──► P3(T11→T12)
              ▲ 可停机：此时已"能查+被要求查+可回写"        ▲ 可停机：自动预取已可用
```

**与架构重构计划的合流**（权威顺序 = 架构计划 §0）：

| 本计划任务 | 与架构计划的交叉 |
|---|---|
| P0/T3 分型统一 | **先于**架构计划 Task 14（L1 改 grade 派生）——同一口径，禁并行 |
| P0/T4 pi 登记 | **后于**架构计划 Task 3（平台元数据单源化），使 pi 只登记**一处** |
| P1/T6 扩展注入 | Task 15（按 grade 分层）落地后，注入模板改为分块标题（`## 铁律（必读全文）`）；本计划先用平铺版本，留好切点 |
| P1/T8 可观测 | 与架构计划 Task 4（scan/inventory）共用同一台账 |
| P2/T9 回写 | 与架构计划 Task 16/17（账本/对账）无耦合，可先后任意 |
| P3/T11 总检 | 与架构计划 Task 6/7（门禁与流水线）同期时，以新门禁为准 |

**禁并行对**：P0/T3 ∥ 架构 Task 14；P0 ∥ 架构 Task 6/7（门禁与巡检自改期）。

- **P0 结束是可独立交付点**：pi 已能自主检索（模型自觉）+ 被硬约束要求检索 + 回写通道在册
- **P1 结束是「自动自主」达成点**：不依赖模型自觉
- 每个 Task 独立可提交、独立可回滚；跨仓改动两仓相邻提交
- 任一 Task 出现门禁红 → 停在该 Task 内修复，不得带入下一 Task（尤其 T3 分型，是后续全部任务的口径前提）

## 九、裁定记录（已全部锁定，无待确认项）

| # | 事项 | 裁定 |
|---|---|---|
| 1 | 修改 pi 的 `agent/AGENTS.md`（顶部托管块 + 归并重复条目） | **同意改**（2026-10-02 用户明示）；Task 2 Step 5 仍先出 diff 供你过一眼再写 |
| 2 | 触发策略 | 首轮 / resume（开 pi 继续上次任务）/ 话题漂移 |
| 3 | 注入位置 | pi `AGENTS.md` **顶部**托管块 + `systemPromptOptions.sections` |
| 4 | 分型统一 | 两套口径必须统一；映射表放**中枢**（`tools/task_tier.py`） |
| 5 | 其余决策点 1–7 | 全部按计划建议（已在§三与各 Task 体现） |
