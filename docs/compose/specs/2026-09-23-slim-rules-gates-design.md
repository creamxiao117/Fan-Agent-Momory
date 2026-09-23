# 启动链与规则门禁分层瘦身设计

日期：2026-09-23  
分支：`optimize/slim-rules-gates`  
方案骨架：A+B（三层渐进披露 + 卡级合并）

## [S1] Problem & goals

### 问题

在线模型时代为约束弱模型而堆叠的规则/门禁，在 128K 本地模型上加载臃肿。实测启动链四件套约 **136,109 字符**：

| 文件 | 字符 | 行数 |
| --- | ---: | ---: |
| AGENTS.md | 1,400 | 38 |
| CHARTER.md | 1,867 | 74 |
| WORK.md | 41,952 | 519 |
| AgentMemoryHub/INDEX.md | 90,890 | 570 |

另有 rules 32 张共约 70,787 字符、methodology 61 张约 139,028 字符；INDEX 对每卡保留长描述，等效第二正文。

### 目标（第一版）

1. 启动链（AGENTS+CHARTER+WORK 当前态+INDEX 目录版）**≤30,000 字符**。
2. **按任务分级加载**：简单任务不背重规则；L1 按任务型补读，L2 检索才全文。
3. 覆盖路由、规则、方法论的分层治理（启动链 + 卡内容 + 注入面）。

### 安全底座（L0 永不裁剪）

- 单写者锁 + 工作区守护（§4）+ ledger 审计
- 检索优先（query-first）+ 不确定交回用户 + 结果回写经验卡

### 明确排除

- 机器侧门禁（pre-commit / patrol / vector 回归等）不占模型上下文，保持不动
- 不做自动删卡、不改向量/MCP 架构、不做 4 型以外精细矩阵
- push 默认关等既有裁定不翻案

## [S2] Architecture & task tiers

### 三层加载模型

| 层 | 何时加载 | 内容 | 预算 |
| --- | --- | --- | ---: |
| **L0 常驻** | 每次会话 | AGENTS 薄路由 + CHARTER 压缩 + WORK 仅当前态 + INDEX 目录版 + 铁律底座摘要 | **≤30K 字符** |
| **L1 按任务型** | 路由命中后 | 任务型对应规则核心节 / 方法论指针 / 路由表切片 | ≤15K |
| **L2 按需检索** | retrieve / hub_bootstrap / 点名读文件 | 规则全文、方法论全文、历史归档 | 不限（单次命中） |

### 任务分型（第一版 4 型）

1. **轻问答/查状态** → 仅 L0（+query-first 一行）
2. **改代码/提交** → L0 + 编码/ruff/pytest 门禁核心（L1）
3. **动中枢内容** → L0 + 单写者/工作区守护/query-first 回写全量（L1）
4. **同步/注入/跨平台** → L0 + cross-platform sync / push dry-run（L1）

判定：显式指令优先；关键词兜底（commit/PR/patch/ruff → 改码；sync/push/注入 → 同步；中枢/rules/ingest → 动中枢）；判不出默认轻问答，动作变重再升型（升型廉价，不做降型）。

### A+B 分工

- **A**：改加载路径与分级（AGENTS/WORK/INDEX/注入/预算门禁），服务 30K 主路径。
- **B**：卡级合并去重（方法论 4 组、经验去重、长卡拆分），降 L2 单次命中成本；先 backup 再动。

## [S3] Components

1. **AGENTS.md**：重写为任务分型路由表（4 型 × L1 卡名清单，一行一个）；启动顺序指向 WORK 当前态与 INDEX 目录版；保留中枢查询/不确定交回/缺工具自找；铁律以摘要进 L0。预算 ≤3K（见 [S3] 分项帽）。
2. **WORK.md**：仅保留更新日期、当前状态快照、活跃待办、验收口径；R1 起历史轮次迁 `docs/superpowers/retro/work-history.md`。预算 ≤9K。
3. **INDEX.md**：每卡一行 `卡名 + ≤40 字摘要`；分区保留；安全底座规则顶部 `★` 标注；**长描述不进 INDEX**，详情以卡自身 frontmatter/正文为唯一源（不再维护第二正文）。预算 ≤14K。
4. **rules/**：frontmatter 增 `tier: iron | task | ref`（手工标 32 张）；长卡（chinese-text-encoding、multi-language-style-config、rules-routing-table）拆核心（≤1.5K）+ 附录；启动门禁模板进附录。
5. **methodology/**：INDEX 仅名称+一行；B 步执行 `merge-methodology.py` 4 组合并、`deduplicate-experience.py` 去重（前序 `backup-rules.py` 全量备份）。
6. **inject.py / 各平台注入**：只注入 L0 底座 6 条（单写者/工作区守护/ledger + query-first/交回用户/回写）+ 按任务型读路由 + 检索一句；不贴规则全文与长模板。
7. **预算脚本** `scripts/startup_budget.py`：四文件字符和 >30K 或任一单文件超分项帽 → 非 0 退出；挂巡检，不挂 pre-commit。

单文件上限（硬门禁以总和 ≤30K 为准，单文件为防单点回潮的分项帽）：AGENTS ≤3K、CHARTER ≤3K、WORK ≤9K、INDEX ≤14K（四者上限合计 29K，预留约 1K 给铁律摘要等边角）。

## [S4] Runtime behavior & degradation

1. 启动：AGENTS → 识别任务型 → CHARTER + WORK 当前态 + INDEX 目录版（计入 30K）→ 读 L1 命中卡核心节。
2. 执行中细节 → `engine.py retrieve` / MCP `hub_bootstrap` 取 L2。
3. 收尾 → 既有 ingest 回写流程（回写纪律不变）。
4. **检索降级**：L0 铁律仍在；AGENTS 写明检索失败按路由表卡名直读文件（确定性兜底，不静默）。
5. **INDEX 完整性**：沿用既有 lint 孤儿+幽灵检测，不新增第二套。
6. **B 步安全**：backup manifest → dry-run 清单人工确认 → 写入；DEPRECATED 头可回滚。

## [S5] Verification & delivery

### 验证

1. 预算门禁真机：四件套总和 ≤30K 且各单文件不超分项帽；故意超长样例证退出码非 0。
2. pytest：预算脚本 + 任务型路由判定补测；全量既有测试无回归。
3. 冷读 L0 路径：安全底座铁律（单写者/工作区守护/ledger + query-first/交回用户/回写，共 6 条）可见、INDEX 无长描述。
4. L1/L2 抽查：改码型命中编码核心；`retrieve` 召回完整卡（合并后抽 4 组）。
5. ruff + encoding 过 pre-commit。
6. B 步：backup manifest → dry-run → 执行 → lint 干净。

### 交付顺序（同分支分步 commit）

1. A1 预算脚本 + 单测  
2. A2 AGENTS 路由化 + CHARTER 压缩  
3. A3 WORK 当前态抽取 + 历史归档  
4. A4 INDEX 目录化  
5. A5 规则 tier 标注 + 长卡拆分 + inject 瘦身  
6. B1 backup + 方法论合并 + 经验去重  
7. 收口：预算/全量测试/ruff 证据 + WORK 当前态更新  

### 回滚

各步独立 commit；卡合并靠 backup + DEPRECATED；INDEX/WORK 旧版在 git 历史。
