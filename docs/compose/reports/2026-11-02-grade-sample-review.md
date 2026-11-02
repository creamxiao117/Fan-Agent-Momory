# grade 抽样复核报告（2026-11-02 · Task 13 Step 2）

> 计划要求：**抽样复核 ≥30 张**人工确认（尤其 `pitfall` 与 `iron` 两类）。
> 本轮抽检 **37 张**（`iron` **全 7 张** + `pitfall` 12 张 + 六目录分层补齐），
> 逐条读卡判读 ⇒ **差异逐条裁定**（计划 Step 4：**不静默改**）。

## 判读口径（复核时用的 rubric）

| grade | 判据 |
| -- | -- |
| `iron` | 铁律：必须遵守 + **有可执行门禁/强制约束**（`gate:` 字段） |
| `proven` | 已验证方案：有实测 / T1 / 回归证据 |
| `domain` | 领域事实 / 长期知识 / 选型结论 / 客观现状 |
| `pitfall` | 坑 / 反面教材 / 易错点 / 静默失败 |
| `task` | 随手记 / 任务性 / 待办 / 仍是草稿 |

## 抽检结果总览

| 目录 | 抽检 | 判读一致 | 差异（已改） |
| -- | -- | -- | -- |
| `rules/` | 10 | 10 | 0 |
| `methodology/` | 5 | 3 | **2** |
| `experience/` | 12 | 11 | **1** |
| `blueprints/` | 3 | 3 | 0 |
| `longterm/` | 3 | 3 | 0 |
| `projects/` | 3 | 3 | 0 |
| **合计** | **37**（含 iron 7 / pitfall 12） | **34** | **3** |

### 逐条判定（摘录关键判定依据）

| 目录 | slug | grade | 判定 | 依据 |
| -- | -- | -- | -- | -- |
| rules | agent-code-discipline-iron-rule | iron | ✅ | 有 pre-commit `code` 门禁（ruff×2） |
| rules | chinese-text-encoding-discipline | iron | ✅ | 有 `text` 门禁（check_encoding 五道） |
| rules | cross-platform-sync-rule | iron | ✅ | reconcile 步门禁；含**在役平台**清单（trae 已退役） |
| rules | dual-platform-coherence-discipline | iron | ✅ | pre-commit code + reconcile 双门禁 |
| rules | global-rules | iron | ✅ | GR-1~4，度量口径（rule_following_timeseries） |
| rules | memory-hub-distill-last | iron | ✅ | 夜间链 distill 执行度量 |
| rules | multi-language-style-config | iron | ✅ | text 门禁；核心卡 + 附录分离 |
| rules | chinese-text-encoding-discipline-appendix | proven | ✅ | 核心卡的完整附录（非铁律本体） |
| rules | markdown-revision-style | proven | ✅ | 修订样式约定，2026-10-21 已核验有实例 |
| rules | reusable-code-header-comment-rule | proven | ✅ | 强约定但**无门禁** ⇒ 按 D7 不算 iron |
| methodology | checker-must-be-provably-red | pitfall | ✅ | 「假绿制造机」反面教材 |
| methodology | **2026-09-26-gate-fix-prove-red-then-green** | pitfall→**proven** | ⚠️ 改 | 主体是**已验证的修复方法**（`index_note` 载明 T1 09-27 ✅ 红 exit1 / 绿 exit0 + 4 处源副本 ACMR）⇒ proven 才符合「有验证证据」 |
| methodology | **next-roi-suggestion** | proven→**domain** | ⚠️ 改 | 正文仅一句「下一步推荐 2-3 个高 ROI 方向…」⇒ 是**流程约定**，既非已验证方案也非坑 ⇒ domain |
| methodology | 2026-08-17-dsh-worktable-cordis-plugin | proven | ✅ | 有关键验证步骤 + 沙盒 |
| methodology | env-injection-yaml | proven | ✅ | 已实测的可靠做法（`hermes mcp add --env` 不可靠） |
| experience | pi-card-merge-hurts-recall | pitfall | ✅ | 反例卡（合并伤召回），本轮 A2 的依据 |
| experience | gate-orchestrator-false-green-path-and-emptyrun | pitfall | ✅ | 空转假绿三形态 |
| experience | idempotent-installer-must-not-rewrite-source | pitfall | ✅ | 幂等安装自伤 |
| experience | chinese-windows-lisp-gb2312-vs-ps1-utf8-bom | pitfall | ✅ | 静默失败 |
| experience | dead-code-detection-grep-truncation-trap | pitfall | ✅ | 输出截断导致误判 |
| experience | powershell51-three-recurring-pits | pitfall | ✅ | 三坑复发 |
| experience | patrol-alert-exit-code | pitfall | ✅ | 静默退化坑 |
| experience | autocad-automation-command-not-delivered-vs-invisible-dialog | pitfall | ✅ | 隐形失败 |
| experience | fanhub-bilibili-up-connector-pre-existing-bugs | pitfall | ✅ | 预存 bug 假阴性 |
| experience | minicpm5-1b-memoryhub-integration | pitfall | ✅ | 三路径实测 + 坑 |
| experience | **lmstudio-local-llm-migration** | pitfall→**proven** | ⚠️ 改 | 主体是**迁移方案与配置规范表**（模型映射表），坑只是其中一节 ⇒ proven |
| experience | 2026-09-10-12gb-vram-model-selection-...-fix | task | ✅ | 仍是草稿（`状态：draft，待 ingest`） |
| experience | dsh-plugin-add-overwrites-cordis-patch | task | ✅ | `experience/` 合法集 = {task, pitfall, proven}（**无 domain**）⇒ task 是唯一合法档 |
| blueprints | act-local-ci-runner-... / gh-hugohe3-ppt-master-... / nats-messaging-layered | domain | ✅ | 蓝图 = 领域事实/方案 |
| longterm | ai-model-stack / github-account / memory-hub-location | domain | ✅ | 长期事实（账号/位置/技术栈） |
| projects | alphafold-... / github-autopush / platform-backlog-t19-t21 | domain | ✅ | 项目/选型事实（`projects/` 合法集 = {domain, proven}） |

## 系统性发现（比单张差异更重要）

**分布明显偏保守**：

| 目录 | grade 分布 |
| -- | -- |
| `rules/` | iron 7 · proven 6 |
| `methodology/` | proven 68 · pitfall 6 |
| `experience/` | **task 242** · pitfall 36 · proven 8 |
| `blueprints/` | domain 160 · proven 52 |
| `projects/` | domain 22 · proven 1 |
| `longterm/` | domain 8 |

量化检查（脚本口径：正文含 `T1 验证 / 已验证 / 实测通过 / 回归测试通过 / 复现` 等证据标记）：

- **弱档（task/pitfall）却带验证证据：52 张**（`experience/task` 42 + `experience/pitfall` 8 + `methodology/pitfall` 2）
  ⇒ 这些卡**实际是已验证的**，却因 ingest 默认落 `task` 而被埋在最弱档 ⇒ **「已验证的教训」与「随手记」无法区分** —— 这恰是 grade 轴要解决的问题，却被默认值淹没。
- **强档（proven/iron）却零证据标记：99 张**（含 6 张 iron）—— 但 **iron 的证据是「门禁」不是 T1 标记**，关键词法不适用；`proven` 也可能证据在别处 ⇒ **不足以作为降级依据**（本轮未动）。

⇒ **处置（不静默批量改）**：
1. 本轮只改**复核中确证**的 3 张（见上），其余**逐条留待下一轮**（计划 Step 4：差异逐条裁定，不静默改）。
2. 建议下一轮做**口径而非逐卡**的修正：**ingest 时按证据推断 grade**（正文含 T1/实测证据 ⇒ 至少 `proven`；命中坑类关键词 ⇒ `pitfall`），
   而不是无条件落默认档（`common/frontmatter.py` 已有「按目录补保守默认值」的先例，可同源扩展）。
3. 已把 `grade_source`（`rule` / `manual`）字段写进新卡，为将来「按来源分别复核」留出抓手。

## 验证

- 改 grade 只动 frontmatter（正文零 diff）；`iron` 未被触动 ⇒ **L1 派生集合不变**（`l1_cards()` 仍 code 3 / hub 3 / sync 2，`check_l1_shape` 空）。
- 改后 `render_index --write` 已重渲；`build-vectors` 已重建（向量按路径+内容索引，grade 变了要重建）。
- `pytest` / `ruff` / `startup_budget` / `recall_regression` 全绿。
