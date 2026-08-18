# hub-mcp-server · 执行期中枢查询总线 + 任务级引导设计

> **状态：** 设计稿（未实现，待评审）  
> **日期：** 2026-08-18  
> **关联：** `hub-engine/tools/retrieve.py` · `hub-engine/engine.py` · `hub-engine/sync.py` · `hub-engine/common/frontmatter.py` · `AgentMemoryHub/hub.config.yaml` · `docs/superpowers/specs/2026-08-17-sync-platforms-bridge-design.md`

## 1. 背景与目标

### 1.1 现状缺口

| 能力 | 现状 | 问题 |
| --- | --- | --- |
| 提醒先查中枢 | `tools/inject.py` 写入各平台记忆文件 | **软约束**，无法证明 agent 是否真读 |
| 混合检索 | `tools/retrieve.py` + `engine.py retrieve` CLI | 各平台需自行拼命令/路径，调用率不可观测 |
| 查询审计 | 无 | `reuse_count` 不自增；retrieve 无日志 |
| 候选回写 | 人工放 draft → `ingest` | 「查询产物回写」靠自觉 |
| 记忆同步 | `platform_bridge` Pull/Push | **与本设计正交**；MCP 不替代文件桥 |
| 任务启动检索 | 无；agent 自行翻 INDEX/目录 | 每次任务重复低效检索；命中结果不入任务上下文 |

### 1.2 目标

提供本地 **MCP Server（stdio）**，把中枢变成各 Agent 平台会话内的标准工具：

1. **统一检索入口**：封装现有 `retrieve`，不重写召回算法。  
2. **可审计读取**：每次查询落日志，解决「有没有先读中枢」。  
3. **最小权限写**：可选候选卡只进 `.sync/drafts/`，永不直写权威区。  
4. **与文件桥并存**：MCP = 执行期查询总线；`platform_bridge` = 离线/定时同步总线；`inject` = 行为契约。
5. **任务级引导**：任务开始一次 `hub_bootstrap` 分类检索，把命中固化进本次任务 AGENTS.md（引用+摘要），执行中按需补全文，避免反复调用。

### 1.3 非目标（本版不做）

- 不实现平台 MEMORY 全量 Pull/Push（已有 bridge 设计）。  
- 不直写 `rules/` / `methodology/` / `longterm/` / `projects/` / `experience/` 权威卡。  
- 不删除、归档、改 frontmatter 权威字段。  
- 不做远程 HTTP MCP、不做多租户鉴权（单机本用户）。  
- 不强制所有平台接入（不支持 MCP 的平台继续 inject + 读文件降级）。

---

## 2. 关键决策

| # | 决策 | 理由 |
| --- | --- | --- |
| D1 | **薄封装，算法零分叉** | 召回只调 `tools.retrieve.retrieve`；列表/读卡复用 `_walk_active_cards` 同级目录约定 |
| D2 | **stdio 本地进程** | 与 TRAE/Codex 等常见 MCP 配置一致；中枢路径本机绝对路径，无网络暴露面 |
| D3 | **默认只读；写需显式工具且仅 draft** | 防 agent 误改权威区；写路径复用 ingest 管线 |
| D4 | **每次 search/get 都审计** | 验证「是否先查」的唯一硬证据；日志失败不得阻断查询（best-effort） |
| D5 | **返回摘要优先，全文按需** | 控制上下文预算；`hub_search` 默认截断 body，`hub_get` 取全文 |
| D6 | **platform 标识必填（写）/ 强烈建议（读）** | 审计与 draft 分目录依赖 platform；未知 platform 拒绝写入 |
| D7 | **不在 MCP 内跑 ingest/confirm** | 提升权威卡仍走 CLI + 人工确认（HIGH_RISK 规则） |
| D8 | **任务级引导一次固化，不反复检索** | 开始 `hub_bootstrap` 分类检索 → 写任务 AGENTS.md（引用+摘要）；后续按需 `hub_get` |
| D9 | **任务 AGENTS.md 用「引用+摘要」，不整卡拷贝** | 防上下文膨胀 + 防固化即过时；规则类标「必读全文」 |
| D10 | **回写分级** | exp/project 走 draft→ingest 快路径；rule/methodology 进 `.sync/pending/` 经 confirm_rule 人工审核 |

---

## 3. 架构

```
┌──────────────────────────────┐
│ Agent 平台（trae/code/…）     │
│  MCP Client                  │
└─────────────┬────────────────┘
              │ stdio JSON-RPC (MCP)
              ▼
┌──────────────────────────────┐
│ hub-mcp-server               │
│  tools: search/get/index/    │
│         ingest_candidate     │
│  audit.append(query.log)     │
│  policy: read vs draft-only  │
└─────────────┬────────────────┘
              │ in-process import
              ▼
┌──────────────────────────────┐
│ hub-engine                   │
│  retrieve.retrieve(...)      │
│  frontmatter.try_read_card   │
│  write_card → drafts/        │
└─────────────┬────────────────┘
              ▼
         AgentMemoryHub/
           rules|methodology|longterm|projects|experience|…
           .sync/drafts/<platform>_draft/
           .sync/state/query.log.jsonl
           retro/log.md（可选摘要行，非每查必写）
```

### 3.1 进程与配置

| 项 | 约定 |
| --- | --- |
| 入口 | `python -m hub_mcp` 或 `hub-engine/mcp_server.py`（实现阶段二选一，推荐包内模块） |
| 传输 | MCP stdio |
| 中枢根目录 | 启动参数 `--root` **或** 环境变量 `AGENT_MEMORY_HUB`；二者都缺则报错退出 |
| 工作目录 | 不依赖 cwd；所有路径相对 `root` 解析 |
| Python path | 保证可 `import tools.retrieve` / `common.frontmatter`（与现有 scripts 同样 `sys.path` 注入 hub-engine） |
| 并发 | 单进程；写 draft 时复用或轻量文件锁（与 `_WriteLock` 同目录约定，避免与 ingest 交叉写坏） |

### 3.2 客户端配置示意（非实现，仅约定）

```json
{
  "mcpServers": {
    "agent-memory-hub": {
      "command": "python",
      "args": [
        "C:/…/feat-implement-plan-ZilBmv/hub-engine/mcp_server.py",
        "--root",
        "C:/…/feat-implement-plan-ZilBmv/AgentMemoryHub"
      ]
    }
  }
}
```

各平台把 `platform` 通过工具参数传入（见 §4）；不在 server 启动时绑死单一 platform，以便同一 server 服务多客户端（若并行，靠参数区分审计字段）。

### 3.3 与 inject 文案协同

注入块升级为（实现 inject 时另改，本设计只定契约）：

```text
任务开始：先调用 MCP 工具 hub_bootstrap（或 hub_search）检索中枢；无 MCP 时读 INDEX.md 与五类目录。
命中结果以「引用+摘要」写入本次任务 AGENTS.md（规则类标注必读全文），执行中需要细节再 hub_get。
执行中若发现与任务 AGENTS.md 冲突，回中枢复核（以中枢为准）。
任务闭环：exp/project 事实用 hub_ingest_candidate 回写（仅候选）；新规则/方法论进收件箱等待人工审核。
```

---

## 4. 工具 Schema

命名前缀统一 `hub_`。所有工具响应为 **JSON 可序列化对象**（MCP text content 内嵌 JSON 字符串亦可，实现选一种并固定）。

### 4.1 公共类型

```ts
// 逻辑类型（文档用）；实现可用 TypedDict / pydantic

type CardType =
  | "rule" | "methodology" | "longterm" | "project" | "exp"
  | "note" | "retro";

type CardHit = {
  slug: string;           // 文件名去 .md，如 dll-version-lock
  rel_path: string;       // 相对中枢根，如 rules/dll-version-lock.md
  type: CardType;
  status: string;         // active | candidate | archived（检索默认不含 archived）
  tags: string[];
  updated: string;        // YYYY-MM-DD
  score?: number;         // 语义通道余弦；确定性命中可省略或 1.0
  channel?: "deterministic" | "semantic";
  excerpt: string;        // body 截断，默认前 200 字（与 CLI 打印一致）
  body?: string;          // 仅 hub_get 或 search include_body=true
};

type TaskKind =
  | "code" | "dll" | "project" | "debug" | "generic";

type BootstrapHit = {
  kind: CardType;        // 所属类别：rule/methodology/longterm/project/exp
  hits: CardHit[];
};

type BootstrapResult = {
  ok: true;
  task_kind: TaskKind;
  snapshot_at: string;   // 命中快照时间戳，用于 staleness 判断
  blocks: BootstrapHit[];// 按类别分组，供生成任务 AGENTS.md
  markdown: string;      // 现成的「任务级引导块」Markdown（见 §5）
  audit_id: string;
};

type ErrorBody = {
  ok: false;
  error: string;          // 稳定错误码，见 §7
  message: string;        // 人可读
};
```

### 4.2 `hub_search`（只读 · 核心）

**映射：** → `tools.retrieve.retrieve(root, query, top_k=…, n=…, mode=…)`  
**说明：** 混合检索：先确定性（type/tag），命中即返回该列表；否则语义 top_k。与 CLI `engine.py retrieve` 语义一致。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `query` | string | 是 | — | 非空；空串返回 `ok:true, hits:[]`（与 retrieve 护栏一致） |
| `top_k` | int | 否 | 5 | 语义通道条数；范围 1–20，越界 clamp |
| `mode` | `"word"` \| `"char"` | 否 | `"word"` | 与 retrieve 一致 |
| `n` | int | 否 | 2 | char n-gram；word 模式保留参数透传 |
| `types` | string[] | 否 | 全部活跃类 | **过滤在 retrieve 之后**做（避免改算法）；非法 type 忽略 |
| `include_body` | bool | 否 | false | true 时每条带全文（慎用） |
| `excerpt_chars` | int | 否 | 200 | excerpt 长度 |
| `platform` | string | 否 | `"unknown"` | 写入审计 |

**成功响应：**

```json
{
  "ok": true,
  "query": "DLL 被锁",
  "channel": "deterministic",
  "hits": [
    {
      "slug": "dll-version-lock",
      "rel_path": "rules/dll-version-lock.md",
      "type": "rule",
      "status": "active",
      "tags": ["autocad", "dll-lock"],
      "updated": "2026-08-18",
      "channel": "deterministic",
      "excerpt": "DLL 版本防锁规则…"
    }
  ],
  "audit_id": "20260818T153012Z-a1b2"
}
```

**channel 字段规则：**

- 若 `deterministic_retrieve` 非空 → 整次 `channel=deterministic`，hits 不再跑语义。  
- 否则语义 → `channel=semantic`，每条可带 `score`（若 retrieve 未返回分数，实现阶段为 `semantic_retrieve` 增加可选 scored API，**或** MCP 层对 semantic 路径调用 scored 变体；**禁止**为拿分数再跑第二遍全库。推荐：在 `retrieve.py` 增补 `retrieve_with_meta(...) -> list[tuple[Card, meta]]`，CLI 仍用旧 `retrieve`）。

**审计：** 每次调用追加 query 日志（§6），含 hits 的 `rel_path` 列表。

### 4.3 `hub_get`（只读）

**映射：** 解析 `slug` 或 `rel_path` → `try_read_card`；**不**走向量检索。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `id` | string | 是* | — | `rules/dll-version-lock` 或 `dll-version-lock` 或带 `.md` |
| `rel_path` | string | 是* | — | 与 id 二选一；同时给以 `rel_path` 为准 |
| `platform` | string | 否 | `"unknown"` | 审计 |

\* 至少一个。

**解析顺序：**

1. 若 `rel_path` 含 `/`：`root / rel_path`（规范化，禁止 `..` 逃逸，见 §7）。  
2. 若仅 slug：在权威目录 `rules, methodology, longterm, projects, experience, libs, retro` 下查找 `{slug}.md`；多命中返回 `error=ambiguous` 并列出候选路径。  
3. 文件不存在或非卡 → `error=not_found`。  
4. `status=archived`：默认仍可读（显式 get），响应标 `status`；search 默认不返回 archived（与 `_walk_active_cards` 一致）。

**成功响应：** 单条 `CardHit` 且必含 `body` + `audit_id`。

**审计：** 记 `action=get`，`id/rel_path`，是否命中。

### 4.4 `hub_index`（只读）

**映射：** 读 `INDEX.md` 全文 **或** 扫五类目录生成精简目录（实现优先：**扫目录生成结构化列表**，避免 INDEX 与磁盘漂移；INDEX 原文可作为可选 `include_markdown=true`）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `types` | string[] | 否 | 五类+libs | 子集过滤 |
| `include_markdown` | bool | 否 | false | true 时附带 INDEX.md 原文（截断上限 32KiB） |
| `platform` | string | 否 | `"unknown"` | 审计 |

**成功响应：**

```json
{
  "ok": true,
  "categories": {
    "rules": [{"slug": "dll-version-lock", "rel_path": "rules/dll-version-lock.md", "tags": ["…"]}],
    "methodology": [],
    "longterm": [],
    "projects": [],
    "experience": []
  },
  "audit_id": "…"
}
```

**审计：** `action=index`（可采样：同一 platform 1 分钟内重复 index 可只记一条，降噪；search/get 不采样）。

### 4.5 `hub_ingest_candidate`（受控写 · 第二优先级，可与只读同版交付或紧随）

**映射：** 构造 `Card` → `write_card` 写入  
`{root}/.sync/drafts/{platform}_draft/{slug}.md`  
**不**调用 `ingest()`；提升仍走 `engine.py ingest --platform …`。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `platform` | string | 是 | — | 必须在 `hub.config.yaml` 的 `platforms` **或** 显式允许列表（见 §7）；禁止 `unknown` |
| `title` | string | 是 | — | 用于 slug；非空 |
| `body` | string | 是 | — | 候选正文 |
| `type` | string | 否 | `"exp"` | 允许 `exp` \| `note` \| `project`；**禁止** `rule`（rule 须人工 confirm 路径） |
| `tags` | string[] | 否 | `[platform]` | 自动确保含 platform 标签 |
| `slug` | string | 否 | 自 title 生成 | 仅 `[a-z0-9-]`；冲突则后缀短哈希 |

**frontmatter 固定：**

```yaml
type: exp          # 或 note/project
tags: […, <platform>, mcp-candidate]
updated: '<today>'
status: candidate
reuse_count: 0
source: mcp/<platform>
```

**成功响应：** `{ ok, rel_path, slug, audit_id }`  
**审计：** `action=ingest_candidate`。  
**幂等：** 同 platform+slug+body 指纹已存在则 `ok:true, deduped:true`，不重复写。

### 4.6 明确不暴露的工具

| 禁止 | 原因 |
| --- | --- |
| `hub_delete` / `hub_archive` | 破坏性，走人工 + tidy CLI |
| `hub_confirm_rule` | HIGH_RISK，须人工 |
| `hub_push_platform` / `hub_pull_platform` | 属 platform_bridge，非会话工具 |
| `hub_exec` / 任意 shell | 权限面过大 |
| 直接写权威目录的任意 write | D3 |

### 4.7 `hub_bootstrap`（只读组合 · 任务级引导）

**映射：** 按 `task_kind` 映射类别清单（§5.2），对每类调 `retrieve_with_meta`，聚合成按类分组的结果 + 现成 Markdown 引导块。**不引入新召回算法**，只是编排多次检索。

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `task_kind` | string | 是 | — | 取值见 §5.2；未知值回退 `generic` |
| `context` | string | 否 | `""` | 一句话任务描述，作为各类检索的 query |
| `platform` | string | 否 | `"unknown"` | 审计 |
| `top_k` | int | 否 | 3 | 每类语义通道条数；范围 1–10 clamp |
| `include_body` | bool | 否 | false | 引导块默认不含全文（§5.3 模板） |

**响应：** `BootstrapResult`（§4.1）：`blocks` 按类别分组 + `markdown` 引导块 + `snapshot_at`。

**设计要点：**

- 每类最多 `top_k` 条；规则类恒 `include_body=false` 且响应中标 `must_read=true`（引导 agent 用 `hub_get` 读全文）。
- `markdown` 由 server 生成（模板 §5.3），agent 直接追加到任务 AGENTS.md。
- 幂等：同一 `task_kind`+`context` 允许重复调用（每次重新检索，保证最新）；审计可对同 platform 1 分钟内重复 bootstrap 采样只记一条。

**审计：** `action=bootstrap`，含 `task_kind` 与 `category_hits`。

---

## 5. 任务级引导模式（Task Bootstrap）

目标：任务开始一次检索、固化进任务 AGENTS.md、避免反复调用、结束后回写闭环。这是 `hub_bootstrap` 的使用模式，也是各平台统一的任务行为契约。

### 5.1 任务级闭环流程

```
任务开始
  ├─ 判定 task_kind（code/dll/project/debug/generic）
  ├─ hub_bootstrap(task_kind, context)     # 一次调用，分类检索
  │     └─ 返回 blocks + markdown 引导块
  ├─ 把 markdown 追加到本次任务 AGENTS.md（引用+摘要 + 快照时间戳）
任务执行
  ├─ 需要细节 → hub_get 单卡全文（按需，不反复检索）
  ├─ 长任务 > 4h → 中途对关键规则重新 bootstrap 一次（防 staleness）
任务闭环
  ├─ exp / project 事实 → hub_ingest_candidate（快路径）
  ├─ 新规则 / 方法论 → 收件箱（.sync/pending/ + confirm_rule 人工审核）
  ├─ 审计已自动记录 bootstrap/get/ingest_candidate
  └─ 清理本次任务 AGENTS.md（可沉淀的已回写，不长期堆积）
```

### 5.2 task-kind → 类别映射

| task_kind | 必查类别 | 说明 |
| --- | --- | --- |
| `dll` | rules, projects | 改 DLL/文件：先查防锁规则 + 相关项目 |
| `code` | rules, methodology, projects | 写代码/重构：规则 + 方法论 + 相似项目 |
| `project` | longterm, methodology | 新项目/立项：用户档案 + 方法论 |
| `debug` | projects, experience | 排障/复盘：相似项目 + 历史经验 |
| `generic` | rules, methodology, longterm, projects | 兜底全查（每类 top_k 最小化） |

### 5.3 任务级 AGENTS.md 模板（引用 + 摘要）

```markdown
## 中枢命中（本任务快照 @2026-08-18T15:30Z）
### 规则（必读全文）
- rules/dll-version-lock — 改 DLL 必须递增版本号（涉及文件操作前 hub_get 读全文）
### 方法论
- methodology/occam-razor — 最少文件/字段/步骤
### 项目记忆
- projects/omniroute-gateway — 容器绑 127.0.0.1:20128
### 长期记忆
- longterm/memory-hub-location — 中枢路径
```

### 5.4 staleness 对策（固化结果过时）

1. **快照时间戳**（模板内 `@…Z`）：发生冲突时据此判断该信谁。
2. **冲突回中枢**：执行中与引导块矛盾 → 以中枢为准，回 `hub_get` 复核。
3. **长任务刷新**：任务执行 > 4h → 中途对关键规则重新 `hub_bootstrap` 一次。

### 5.5 回写分级

| 内容 | 路径 | 审核 |
| --- | --- | --- |
| exp / project 事实 | `hub_ingest_candidate` → draft → `ingest` | 低风险自动 |
| 新规则 / 方法论 | 收件箱 `.sync/pending/` → `confirm_rule` | 人工必审 |

### 5.6 任务 AGENTS.md 生命周期

任务闭环后，可沉淀内容已回写，任务级 AGENTS.md 随即清理（删除或并入项目记忆），不长期堆积碎片文件。

---

## 6. 审计

### 6.1 日志路径与格式

| 项 | 约定 |
| --- | --- |
| 主日志 | `{root}/.sync/state/query.log.jsonl`（JSON Lines，UTF-8） |
| 目录 | 若不存在则创建 `.sync/state/` |
| 单行字段 | 见下表 |
| 轮转 | 单文件超过 8MiB 时 rename 为 `query.log.jsonl.YYYYMMDD-HHMMSS` 再新建（实现可简） |
| 失败策略 | 写日志异常只打 stderr，**仍返回业务成功**（D4） |

**行 schema：**

```json
{
  "ts": "2026-08-18T15:30:12Z",
  "audit_id": "20260818T153012Z-a1b2",
  "action": "search",
  "platform": "trae",
  "ok": true,
  "query": "DLL 被锁",
  "channel": "deterministic",
  "top_k": 5,
  "mode": "word",
  "hit_paths": ["rules/dll-version-lock.md"],
  "hit_count": 1,
  "latency_ms": 12,
  "error": null
}
```

| action | 额外字段 |
| --- | --- |
| `search` | query, channel, mode, top_k, hit_paths, hit_count |
| `get` | id 或 rel_path, hit_paths（0/1）, hit_count |
| `index` | types, category_counts |
| `ingest_candidate` | platform, slug, rel_path, deduped |
| `bootstrap` | task_kind, types, category_hits |

### 6.2 与 reuse_count / retro

| 机制 | 本版行为 |
| --- | --- |
| `reuse_count` | **不在 MCP 热路径递增**（避免多客户端写冲突与卡片抖动）。可选后续：定时任务按 query.log 聚合回写 |
| `retro/log.md` | **不每查追加**（噪声）。仅 `ingest_candidate` 成功时可追加一行摘要；或每日巡检汇总「昨日 MCP 查询次数」 |
| 验证「是否先读」 | 查 `query.log.jsonl` 是否在任务时间窗内出现对应 `platform` + `action=search|get` |

### 6.3 验证用例（验收）

1. 平台 A 调 `hub_search` → 日志出现 `platform=A` 与 `hit_paths`。  
2. 不调工具直接做事 → 时间窗内无日志 → 判定未读中枢。  
3. 蜜罐卡：`hub_get` 蜜罐 slug → 日志 + 回复含口令。

---

## 7. 权限与安全

### 7.1 权限矩阵

| 区域 | search/get/index | ingest_candidate |
| --- | --- | --- |
| `rules/` 等权威 `*.md` | 读 | 否 |
| `INDEX.md` | 读 | 否 |
| `archive/` | 默认不 search；get 若路径显式且允许则可读（默认 **拒绝** archive，防噪音） | 否 |
| `.sync/drafts/<platform>_draft/` | 否 | 仅写本 platform 目录 |
| `.sync/conflicts|locks|pending` | 否 | 否 |
| `hub.config.yaml` / `provider_keys.yaml` | 否 | 否 |
| 中枢外任意路径 | 否 | 否 |

### 7.2 路径安全

- 所有用户输入路径：`Path.resolve()` 后必须 `relative_to(root)` 成功，否则 `error=path_escape`。  
- 禁止绝对路径、盘符穿越、符号链接跳出 root（resolve 后检查）。  
- `hub_get` 仅允许后缀 `.md`。

### 7.3 platform 策略

```text
allowed_platforms =
  keys(hub.config.yaml platforms)  ∪  optional mcp.extra_platforms
```

- `hub_ingest_candidate`：`platform ∉ allowed` → `error=platform_forbidden`。  
- 读工具：`platform` 自由字符串仅用于审计（便于 traework 等未登记平台先观察调用率）；实现可在配置打开 `mcp.require_known_platform_on_read: true` 后拒绝未知方。

### 7.4 写类型白名单

- 允许：`exp`, `note`, `project`  
- 拒绝：`rule`, `methodology`, `longterm`, `retro` → `error=type_forbidden`  
  （方法论/长期记忆/规则需人工或专用流程，防会话噪声污染）

### 7.5 密钥与隐私

- Server **不读** `provider_keys.yaml`，不调外部 LLM。  
- 审计日志可能含用户 query：仅存本机中枢目录；不进 git 时依赖中枢 `.gitignore` 已忽略 `.sync/`（若未忽略，实现前确认不把 query.log 提交主仓）。  
- 响应不回显环境变量与 server 本地绝对路径以外的系统信息（`root` 可在初始化 resource 中暴露一次便于调试）。

### 7.6 错误码稳定表

| code | 含义 |
| --- | --- |
| `bad_request` | 缺参/类型错误 |
| `not_found` | 卡不存在 |
| `ambiguous` | slug 多命中 |
| `path_escape` | 路径越权 |
| `platform_forbidden` | 平台未授权写 |
| `type_forbidden` | 候选 type 不允许 |
| `write_failed` | 磁盘/锁失败 |
| `hub_unavailable` | root 无效或不可读 |

---

## 8. 与 retrieve / CLI 映射总表

| MCP 工具 | 引擎调用 | CLI 等价 | 差异 |
| --- | --- | --- | --- |
| `hub_search` | `retrieve(root, query, top_k, n, mode)` + 可选 post-filter `types` + 截断 | `engine.py retrieve --root … "q" --top-k --n --mode` | 多 JSON/审计/types/excerpt；建议增 `retrieve_with_meta` 一次拿 channel/score |
| `hub_get` | `try_read_card(path)` | 无（手读文件） | 新增能力 |
| `hub_index` | 扫 AUTHORITY 目录 / 读 INDEX.md | 无 | 新增；目录列表对齐 lint 的 AUTHORITY_DIRS |
| `hub_ingest_candidate` | `write_card` → drafts | 手写 draft 文件 | 不自动 `ingest` |
| `hub_bootstrap` | 按 task_kind 映射类别 → 各调 `retrieve_with_meta` | 无 | 新增组合工具；agent 直接追加到任务 AGENTS.md |
| （无） | `ingest` / `confirm_rule` / `sync` | 对应 CLI | 保持人工/批处理 |

**推荐的 retrieve 小扩展（实现计划内可选 Task 0）：**

```python
def retrieve_with_meta(root, query, top_k=5, n=2, mode="word") -> tuple[str, list[tuple[Card, float | None]]]:
    """返回 (channel, [(card, score|None), …])；channel in deterministic|semantic|empty"""
```

- `retrieve()` 改为调用 meta 版并只返回 cards，**保证 CLI 行为不变**。  
- MCP 只依赖 meta 版，避免双次检索。

**目录集合（与现网一致）：**

```text
AUTHORITY_DIRS = rules, methodology, longterm, projects, experience, libs, retro
```

---

## 9. 模块与文件布局（实现时）

```text
hub-engine/
  mcp_server.py          # 入口：argparse --root，注册工具，stdio serve
  tools/
    mcp_audit.py         # append_jsonl、audit_id、轮转
    mcp_policy.py        # path_escape、platform/type 白名单
    mcp_handlers.py      # search/get/index/ingest_candidate/bootstrap 纯函数便于单测
  tests/
    test_mcp_handlers.py
    test_mcp_audit.py
    test_mcp_policy.py
```

依赖：优先使用已有 MCP Python SDK（若环境无，再评估最小 JSON-RPC 手写——实现计划阶段锁定一种，设计不绑死包名）。

---

## 10. 测试计划（TDD）

1. **policy**  
   - `../secret.md`、绝对路径、`.sync/../rules` 逃逸 → `path_escape`。  
   - `type=rule` 候选 → `type_forbidden`。  
   - 未登记 platform 写入 → `platform_forbidden`。  
2. **search 映射**  
   - 与直接调用 `retrieve` 同 query 得到相同 slug 集合。  
   - 空 query → hits `[]`。  
   - `types=["rule"]` 过滤后无非 rule。  
3. **get**  
   - slug 唯一/歧义/不存在。  
   - archived 不出现在 search，但显式 rel_path 策略按 §4.3。  
4. **audit**  
   - search 成功后 jsonl 多一行且 `hit_paths` 正确。  
   - 故意让日志目录只读 → 业务仍 ok。  
5. **ingest_candidate**  
   - 文件出现在正确 draft 目录，`status=candidate`。  
   - 指纹重复 → `deduped=true`。  
6. **bootstrap**  
   - 同一 task_kind 结果与手动多次 search 相同 query 的并集一致。  
   - 生成的 `markdown` 为「引用+摘要」，不含整卡全文。  
   - 空命中返回 `blocks` 空数组，不报错。  
7. **不变量**  
   - 全测试结束后权威区 git diff 无新增（仅 draft/state 可写）。

---

## 11. 落地顺序与成功标准

| 阶段 | 内容 | 成功标准 |
| --- | --- | --- |
| P0 | `retrieve_with_meta` + `hub_search` + `hub_get` + 审计 jsonl | 单测绿；TRAE 配 server 后一次真实 search 有日志 |
| P1 | `hub_index` + inject 文案升级 | agent 可浏览五类；抽检引用 rel_path |
| P2 | `hub_ingest_candidate` | 候选进 draft；人工 ingest 仍成功 |
| P3 | 多平台配置样例 + 查询率周报脚本（读 jsonl） | 可回答「本周谁查了中枢」 |

**成功标准（产品）：**  
任意已接 MCP 的平台，在任务时间窗内可用 `query.log.jsonl` **证实或证伪**「是否先查中枢」；检索结果与 CLI `retrieve` 一致。

---

## 12. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 模型仍不调用工具 | inject 契约 + 蜜罐抽检 + 周报调用率 |
| 平台不支持 MCP | 保留文件读 INDEX 降级；bridge 照旧 |
| 审计日志膨胀 | 8MiB 轮转；index 采样 |
| draft 与 ingest 并发 | 写 draft 用平台子目录 + 短文件锁；ingest 已有 `_WriteLock` |
| 上下文被 hits 撑爆 | 默认 excerpt 200；top_k≤20；index 默认无 markdown 全文 |

---

## 13. 与三层总图的关系（备忘）

```text
inject（契约） → 要求先 hub_bootstrap / hub_search，任务级引导流程
MCP（本设计） → 执行期读/写/引导 + 审计
platform_bridge → 平台 MEMORY ↔ 中枢 批处理同步
```

三者互补；本设计 **规范 MCP 这一层及任务级引导模式**。
