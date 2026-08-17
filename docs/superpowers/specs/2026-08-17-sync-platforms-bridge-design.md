# sync 消费 platforms 配置 · 双向同步桥设计

> **状态：** 设计稿（未实现，待评审）
> **日期：** 2026-08-17
> **关联：** `hub-engine/sync.py` · `hub-engine/common/config.py` · `hub-engine/engine.py` · `AgentMemoryHub/hub.config.yaml`

## 1. 背景与现状

当前 4 个平台（trae / code / hermes / workbuddy）已通过 `tools/inject.py` 完成**指令注入**（各平台记忆文件里写入了"执行前先查中枢"指令），并在 `hub.config.yaml` 的 `platforms` 段完成**路径登记**：

```yaml
platforms:
  trae:      { memory_dir: "C:/Users/Fan-SJSS/.trae-cn/memory",     target_file: "user_profile.md" }
  code:      { memory_dir: "C:/Users/Fan-SJSS/.codex",              target_file: "AGENTS.md" }
  hermes:    { memory_dir: "C:/Users/Fan-SJSS/AppData/Local/hermes/memories", target_file: "MEMORY.md" }
  workbuddy: { memory_dir: "C:/Users/Fan-SJSS/.workbuddy",          target_file: "MEMORY.md" }
```

**差距（本方案要补的缺口）：**

1. `common/config.py` 的 `HubConfig.platforms` 属性**没有任何代码消费**——配置只是登记，未用于实际同步。
2. `sync.ingest` 只从 `.sync/drafts/<platform>_draft/` 读取人工/脚本放好的卡片，**不会**自动读取平台记忆文件。
3. 目前"平台记忆 → 中枢卡片"是**半自动**的（R6c 手工建 draft → ingest）；"中枢变更 → 平台文件"完全没做。
4. 检索行为是软约束：平台 agent 是否会真去查中枢，取决于是否遵循注入指令。

**目标：** 让 `sync` 真正消费 `platforms` 配置，提供**双向同步桥**：

- **Pull**（平台记忆 → 中枢 draft → ingest 流程）：把平台记忆文件解析成候选卡片，进入既有去重/冲突/确认管线。
- **Push**（中枢权威卡片 → 平台记忆文件）：把中枢 rules/experience 渲染回平台文件，让平台本地也能看到中枢沉淀（可选，默认关闭防误写）。

---

## 2. 关键约束与决策

| # | 决策 | 理由 |
| --- | --- | --- |
| D1 | **不破坏平台原生文件格式** | 平台文件各有独特结构（见 §3），双向桥只做"解析/追加/渲染"，不得重排或删除平台原有内容 |
| D2 | **Pull 是默认且唯一必需方向** | 平台记忆 → 中枢是单向可信的沉淀通道；Push 有覆盖平台本地编辑的风险，默认禁用，需 `--push` 显式开启 |
| D3 | **复用既有 ingest 管线** | Pull 的产物一律落到 `.sync/drafts/<platform>_draft/`，由现有 `ingest` 去重/冲突/人工确认，不另造一套 |
| D4 | **卡片类型默认 exp** | 平台记忆多为经验条目；含"强制/必须/不得"语义时可由人工改判 rule（沿用 HIGH_RISK 人工确认机制） |
| D5 | **幂等** | 重复执行不重复建卡：以"解析出的内容哈希 + 标题"做去重指纹 |
| D6 | **只读中枢权威区，不自动改写** | Pull 永远只新增/提示冲突，不覆盖既有卡片；改动全部经 `retro/log.md` 记录 + Git 提交 |

---

## 3. 平台记忆文件格式差异（适配层要处理的事实）

| 平台 | 文件 | 结构 | 条目分隔 | 标题来源 |
| --- | --- | --- | --- | --- |
| trae | `user_profile.md` | Markdown 段落（小节标题） | `##` 标题行 | 小节标题（如 `User Preferences`） |
| code | `AGENTS.md` | Markdown 段落 | `##` 标题行 | 小节标题 |
| hermes | `MEMORY.md` / `USER.md` | 纯文本条目 | 行内 `§` 分隔符 | 无标题 → 取条目首 12 字做 slug |
| workbuddy | `MEMORY.md` / `USER.md` | Markdown 段落（小节标题） | `##` 标题行 | 小节标题 |

**格式适配结论：**

- 全量 Markdown 段落式（trae/code/workbuddy）可共用一个 `md_section_adapter`；
- hermes 需单独的 `sect_separated_adapter`；
- 每个平台 `memory_dir` 下除 `target_file` 外，可能还有其它记忆文件（hermes 的 `USER.md`）——适配层按配置的 `target_file` 为**主入口**，其余文件按同名解析逻辑追加，避免硬编码。

---

## 4. 双向同步桥设计

### 4.1 新增模块：`hub-engine/tools/platform_bridge.py`

```
platform_bridge.py
├── Entry            # dataclass: 标题(title) + 正文(body) + 来源(platform/file)
├── Adapter          # 抽象基类: parse(text)->list[Entry]; render(entries)->str
│   ├── MdSectionAdapter   # ## 标题分段（trae/code/workbuddy）
│   └── SectSeparatedAdapter # § 分隔（hermes）
├── adapter_for(platform, cfg) -> Adapter
├── pull(root, platform, dry_run=False) -> dict   # 平台记忆 → draft 卡片
├── push(root, platform, only_rules=False, dry_run=False) -> dict  # 中枢卡片 → 平台文件
└── fingerprint(text) -> str   # 内容规范化哈希（去空白/统一换行）
```

**入口文件路径解析**（复用 `HubConfig`）：

```python
def _target_path(root, platform):
    cfg = HubConfig.load(root)
    p = cfg.platforms.get(platform)
    if not p:
        raise KeyError(f"未知平台: {platform}（hub.config.yaml 未登记）")
    return Path(p["memory_dir"]) / p["target_file"]
```

### 4.2 Pull 流程（平台记忆 → 中枢）

```
engine.py sync --platform hermes [--dry-run]
        │
        ▼
platform_bridge.pull(root, "hermes")
  1. 读目标文件 → Adapter.parse → list[Entry]
  2. 每个 Entry:
     a. title = 已有标题 或 首 12 字 slug
     b. body  = 条目正文
     c. fingerprint = hash(title + body)
  3. 去重（对中枢既有 cards 的标题/正文做 字符串+语义 双检）:
     - 标题已存在 → skip（记 reused）
     - 语义相似 ≥0.7 → 进 .sync/conflicts/<platform>_<slug>.md（复用 _find_duplicate）
     - 其余 → 写 .sync/drafts/<platform>_draft/<slug>.md（type=exp）
  4. 返回统计 {pulled, skipped, conflicted}
        │
        ▼
engine.py ingest --platform hermes   # 走既有去重/冲突/确认管线（可 --dry-run 预览）
```

**写卡片样例**（draft 目录，供 ingest 消费）：

```markdown
---
type: exp
tags:
- hermes
- <slug>
updated: '2026-08-17'
status: candidate
reuse_count: 0
---

<条目正文>
```

### 4.3 Push 流程（中枢卡片 → 平台文件，默认关闭）

```
engine.py sync --platform workbuddy --push [--only-rules] [--dry-run]
  1. 读中枢权威区: rules/ + experience/ 卡片列表
  2. (可选) --only-rules: 只同步 rules/（避免经验刷屏平台文件）
  3. 对每张卡片:
     a. 标题已存在于平台文件 → 对比正文：不一致则 追加"中枢权威版"块 + 记录 log（不覆盖平台本地旧版）
     b. 标题不存在 → 追加新小节（MdSectionAdapter.render）
  4. 幂等：指纹相同则跳过
  5. 全程在 [注入指令块] 之后追加，绝不触碰平台原有段落
  6. 返回统计 {added, updated, skipped}
```

**安全边界（Push 必读）：**

- Push 默认关闭；`--push` 必须显式指定，防止误把中枢大语料写进平台文件。
- 平台文件若被**外部编辑**（平台运行中写入）→ 以文件 mtime + 内容哈希比对，检测到外部改动则 abort 并提示冲突。
- Push 产物不含 frontmatter（平台文件非中枢卡片），只在注入指令块之后追加纯文本小节。

### 4.4 命令接入 `engine.py`

新增子命令 `sync`（与现有 `ingest/confirm/distill/tidy/lint/status` 并列）：

```
engine.py sync --root <hub> --platform <name> [--push] [--only-rules] [--dry-run]
```

- `--dry-run`：只打印将执行的动作，不落盘、不写 draft、不提交（安全预览，符合"先看再做"）。
- 默认方向 = Pull；`--push` 显式切到 Push。
- `--platform all`：遍历 `HubConfig.platforms` 全部平台（便于一键同步）。

### 4.5 与既有能力的复用点

| 既有能力 | 复用方式 |
| --- | --- |
| `_find_duplicate`（语义去重 ≥0.7） | Pull 冲突判定 |
| `ingest`（draft → 去重/冲突/确认 + `_WriteLock` + `_commit`） | Pull 的落盘端 |
| `confirm_rule`（人工确认规则） | 用户把 exp 改判 rule 后走确认 |
| `HubConfig.platforms` | 路径/平台枚举唯一来源 |
| `retro/log.md` + Git | 全量审计 |

---

## 5. 边界与风险

1. **不覆盖平台本地编辑**：Pull 只读平台文件、只新增 draft；Push 追加不替换，外部改动检测到即中止。
2. **hermes 无标题条目**：slug 化可能生成不可读标题（如 `On this Windows h…`）；Pull 时允许 `--title-prefix` 或交人工在 draft 阶段改名（draft 是中间产物，可安全编辑）。
3. **指纹碰撞**：仅用标题去重可能漏判"同标题不同内容"；Pull 用 `hash(title+body)` 指纹 + 语义双检兜底。
4. **平台文件编码**：统一 UTF-8 读写；hermes 文件无 BOM（已实测）。
5. **性能**：卡片量小（当前 <20），直接全量比对即可，无需索引。

---

## 6. 测试计划（TDD）

新增 `hub-engine/tests/test_platform_bridge.py`：

1. **Adapter 解析**
   - `MdSectionAdapter.parse`：`## 小节` 正确切分标题/正文；无标题文本归入 `(无标题)` 条目。
   - `SectSeparatedAdapter.parse`：`§` 分隔条目正确拆分；空条目剔除。
   - `render`：entries → 原文往返一致（幂等）。
2. **Pull 去重**
   - 平台已有标题与中枢重复 → `skipped`，不写 draft。
   - 语义相似 → 进 conflicts，不写 draft。
   - 新条目 → 写 draft，`fingerprint` 可复现。
   - `--dry-run` 不落盘、不写锁。
3. **Push 安全**
   - 默认（无 `--push`）只做 Pull，绝不写平台文件。
   - `--push`：新标题追加小节；同标题不同正文 → 追加"中枢权威版"块 + log，不覆盖。
   - 外部改动检测：篡改 mtime → abort。
4. **命令接线**
   - `engine.py sync --platform trae --dry-run` 退出码 0，输出统计。
   - 未知平台 → 非 0 退出 + 明确报错。
5. **幂等**：同一仓库重复 Pull 两次，第二次全 `skipped`。

---

## 7. 分阶段实施

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| P1 | `platform_bridge.py`：Adapter 抽象 + 两个实现 + `fingerprint` | 单测通过 |
| P2 | `pull()`：解析 → 去重 → 写 draft；`ingest` 无缝衔接 | 单测 + 对 4 平台实跑 `--dry-run` |
| P3 | `engine.py sync` 子命令接线 + `--all`/`--dry-run` | CLI 单测 + 实跑 |
| P4 | `push()`（默认关）+ 外部改动检测 | 单测 + workbuddy `--push --dry-run` 预览 |
| P5 | 全仓 check-code-v1 + 提交 + WORK.md 记录 | Lint 全绿，58+ 测试通过 |

---

## 8. 未决问题（评审时确认）

1. Push 是否需要"全量镜像中枢 rules 到平台文件"，还是只推「被注入指令引用到的关键规则」？
2. Pull 产出的 draft 卡片 tags 自动带平台名（如 `hermes`），是否可接受？
3. `--platform all` 是否需要串行写锁（避免多平台同时 ingest 竞争 `_WriteLock`）？—— 建议默认串行。
