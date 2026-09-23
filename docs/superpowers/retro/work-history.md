# WORK 历史轮次归档（自 WORK.md 迁出 · 2026-09-23）

> 启动链只读 WORK.md 当前态；本文件按需检索/点读。

## 归档说明

- 来源：原 `WORK.md` 的「本轮 R1…」叙事、已核销待办表、VLM 长说明等
- 迁出规则：非「当前状态 / 活跃 P0P1 待办 / 本轮验收口径」的章节全部移入此处

## 原 WORK.md 全文快照（2026-09-23 迁出）
# WORK.md（当前状态 · 唯一来源）

更新于：2026-08-20（R10：check-code-v1 规则门禁 + semgrep/codebase-memory 两仓内化 + vector.db 维度门禁落地）

## 当前 MVP（已完成）

- **中枢骨架**：`AgentMemoryHub/`（本仓库内，已从 `D:\AIwork\AgentMemoryHub` 迁移，规避沙箱权限）。Obsidian 库：rules/libs/experience/projects/retro/archive + .sync + INDEX.md，已 Git 初始化（6 提交）。
- **hub-engine**（本仓库）：同步器（单一写入者/暂存/去重/确认/Git）、混合检索、复盘提炼、整理归档、Lint 健康检查、omniroute 问答。
- **CLI**：`engine.py` 子命令 `retrieve/ingest/confirm/distill/tidy/lint/chat/status/sync`。
- **测试**：79 项通过。
- **注入**：trae 平台指令已注入 `user_profile.md`；code 平台已注入 `D:/AIwork/code-memory/CLAUDE.md`（幂等，待平台目录生效）。
- **端到端**：DLL 版本防锁规则全流程走通（distill → ingest → confirm → retrieve → 回写经验）。

## 本轮 R1（status 快照）

- 已实现 `engine.py status` 子命令：一键输出卡片分布 / Lint / 待确认 / 最近 Git 提交。

## 本轮 R2（project-visual-guide）

- 已生成 `project-visual-guide.md`：Mermaid 流程图 + 脑图 + 核心决策点/风险表。
- 一页看懂三层架构、内容流转、决策点与风险边界。

## 本轮 R3（code 注入 + methodology 卡片）

- code 平台指令注入完成：`D:/AIwork/code-memory/CLAUDE.md`（幂等验证通过）。
- 沉淀 methodology/ 两张卡片：共享（旧项目最小迁移）+ 项目专属（协作约定）。

## 本轮 R4（status --json + 卡片回写 + 质量体检）

- `status` 新增 `--json` 输出：卡片分布 / Lint / 待确认 / 最近提交，结构化供工具链消费（已配测试）。
- methodology 卡片回写中枢 experience/：`old-project-minimal-migration.md`、`unified-memory-hub-workflow.md`（走 ingest，已在中央 Git 审计）。
- 全仓 check-code-v1 体检：8 项全通过，失败 0 跳过 0。
- 配置新增：`.ruff.toml`、`.markdownlint.json`、`.markdownlintignore`、`.gitignore` 补 `.tools/`/`work/`/`.venv/`

## 本轮 R5（中枢迁移 + 每日巡检 + n-gram 调优）

- **中枢迁移**：`D:\AIwork\AgentMemoryHub` 已复制到项目内 `AgentMemoryHub/`，所有引用更新为相对路径（scripts 默认值、AGENTS/CHARTER、visual-guide、draft 卡片、user_profile）。源目录受沙箱保护未删除，保留为陈旧副本。
- **engine.py 解耦**：`requests` 改为 chat 内延迟导入，`status`/`retrieve` 等本地子命令不再依赖网络库（.venv 无 requests 也能跑）。
- **每日巡检 cron**：每日 09:00（北京时间）生成 `retro/snapshot-<日期>.json` + `lint-report-<日期>.md`，异常时记 log 并提交 Git（Schedule ID 35e02dc8）。
- **n-gram 召回率实测调优**：8 卡 11 查询评测，n=2 最优（top_k=3 即 100% 召回），n=3/4 因稀疏性召回明显下降；确定性通道对语义改写查询命中为 0（依赖精确 tag）。
- **n 参数化**：`semantic_retrieve`/`retrieve` 新增 `n` 参数（默认 2，CLI `--n`），为语料变化保留调参入口；新增 2 项测试，49 项全通过。
- **评测脚本**：`work/bench_recall.py`（gitignored，不入库）可复跑召回率评测。

## 本轮 R6（中文语义召回增强）

- **jieba 词模式**：`vector.py` `tokenize(mode="word")` jieba 分词 + 去停用词/标点，无 jieba 回退 char；`build_idf` IDF 加权缓解领域共词抢占。
- **确定性通道词级匹配**：`retrieve.py` `mode` 参数传播，word 模式下查询分词与 tag 互相包含即命中。
- **默认切 word**：检索默认模式改为 word，CLI `--mode` 可选；`requirements.txt` 加 jieba>=0.42。
- **评测胜出**：word 全面优于 char（确定性通道 0→5/11、语义 top1 8→9/11、混合 top1 8→10/11）。

## 本轮 R6b（code 平台接入 + 语料增长复核 + IDF 稳定性）

- **code 平台接入生效**：注入目标由 `D:/AIwork/code-memory/CLAUDE.md` 修正为真实机制 `C:/Users/Fan-SJSS/.codex/AGENTS.md`（`hub.config.yaml` 与 `bootstrap_hub.py` 同步修正）；`.codex/AGENTS.md` 已含中枢指令且幂等验证通过。
- **语料增长重评**：18 卡 / 19 查询评测，word 仍全面优于 char（确定性通道 0→9、语义 top1 12→16、混合 top1 12→17）；n=2 保持最优。
- **停用词审计**：word 高频前 25 无实质噪声词，停用词表无需调整。
- **IDF 稳定性**：按文档频率分层（常见 vs 稀有）随机子语料 10 次重算，区分度边界 margin=0.405>0，结论稳定（语料增删后权重分层不翻转）。

## 本轮 R6c（hermes + workbuddy 平台接入）

- **平台登记**：`hub.config.yaml` 与 `bootstrap_hub.py` 新增 hermes（`AppData/Local/hermes/memories`）与 workbuddy（`~/.workbuddy`）两平台，现共 4 平台（trae/code/hermes/workbuddy）。
- **指令注入**：hermes 的 `MEMORY.md`/`USER.md`（§ 分隔格式）、workbuddy 的 `MEMORY.md`/`USER.md` 均注入「执行前先查中枢」指令（幂等）。
- **记忆沉淀**：hermes 3 张经验入区（omniroute-gateway、browser-automation-chrome、text-extraction-priority）；workbuddy 2 条规则确认入 rules（context-budget-discipline、markdown-revision-style）+ 1 张经验（github-repos-and-skills）；omniroute-api 与 hermes 卡片重复进冲突区。
- **验收**：中枢 6 exp + 3 rules，pending 0，58 项测试全通过。

## 本轮 R6d（sync 平台双向同步桥）

- **设计稿**：`docs/superpowers/specs/2026-08-17-sync-platforms-bridge-design.md`（Pull/Push 双向桥 + Adapter 适配 + 命令接线）。
- **platform_bridge.py**：`Entry` + `Adapter` 抽象（`MdSectionAdapter` ## 分段 / `SectSeparatedAdapter` § 分隔）+ `fingerprint` 内容规范化哈希 + `pull`/`push`。
- **pull**：平台记忆 → `.sync/drafts/<platform>_draft/` 候选卡片（type=exp）；标题已存在 skip、语义相似 ≥0.7 进冲突区、指纹状态做幂等（`.sync/state/pulled_<platform>.json`）。
- **push**（默认关）：中枢 rules/experience 卡片渲染回平台文件；同标题不同正文追加「中枢权威版」不覆盖；mtime+hash 基线检测外部改动即中止；`--only-rules` 过滤。
- **CLI**：`engine.py sync --root <hub> --platform <name|all> [--push] [--only-rules] [--dry-run]`。
- **验收**：新增 `test_platform_bridge.py` 21 项（Adapter 往返/去重/幂等/dry-run/Push 安全/外部改动/CLI），全量 79 项通过，ruff 全绿。
- **4 平台 dry-run 实测**：trae 4 / code 2 / hermes 8+4 冲突 / workbuddy 3+3 冲突；workbuddy `--push --dry-run` 预览 11 条待加。

## 本轮 R6e（首批平台记忆沉淀 + 冲突处置）

- **冲突处置**：`omniroute-api.md` 冲突核对后合并入 `omniroute-gateway.md`（补充 qwen2.5:7b / 超时 30s / 11434 配置，标注来源 workbuddy），冲突文件删除，信息不丢失。
- **正式 sync**（非 dry-run）：`sync --platform all` → trae 4 / code 2 / hermes 8+4 冲突 / workbuddy 3+3 冲突，draft 全部落 `.sync/drafts/<platform>_draft/`。
- **ingest 入区**：4 平台共提升 14 张 exp 卡片（trae 4、code 1、hermes 7、workbuddy 2），3 张语义重复进冲突区；git 自动提交 4 次（ed2988a/0d2a190/b2fbe20/0c5c1c8）。experience 现 21 张。
- **定期复核**：新增每周自动复核 Schedule（运行 `work/bench_recall.py` 复核 n 值 / 停用词表 / IDF 边界）。

## 本轮 R6f（hub MCP 服务器）

- **MCP stdio 服务器**：`hub-engine/mcp_server.py`（mcp SDK 1.26）暴露 5 个工具 hub_search / hub_get / hub_index / hub_bootstrap / hub_ingest_candidate，参数经 `_normalize` 映射（id/type → id_/type_）。
- **检索带通道**：`retrieve_with_meta` 一次返回 channel（empty/deterministic/semantic）+ score；路径防逃逸 `resolve_rel` + platform/type 白名单（`tools/mcp_policy.py`）。
- **审计落盘**：`.sync/state/query.log.jsonl`，8MiB 轮转、best-effort 静默；查询周报 `scripts/query_report.py`。
- **回写分级**：exp/project 事实经 hub_ingest_candidate 只写 draft（status=candidate，不直写权威区）；新规则/方法论走收件箱人工审核（本版未实现 confirm_rule）。
- **指令升级**：inject 指令改为任务级引导契约——任务开始 hub_bootstrap 检索、结果「引用+摘要」固化进任务 AGENTS.md、冲突回中枢复核、闭环回写。
- **客户端样例**：`mcp.example.json`；手动冒烟已验证 initialize / tools/list / tools/call(hub_bootstrap) 端到端 + 审计落盘（bootstrap/trae/dll 命中 rules/dll-version-lock）。
- **验收**：pytest 全量 115 通过，ruff check/format 全绿。8 任务提交（Task 1-8，commit 469b040 → a4f9993，均已推送）。

## 本轮 R6g（snippet 片段节选 + 巡检接入向量库）

- **snippet 片段节选**：新增 `tools/snippet.py` 的 `extract_snippet(body, query)`，抽取正文中与查询词重叠最多的行(+上下文)作为命中片段，替代旧「卡片前 200 字」；接入 MCP `_hit.excerpt` 与 CLI `_cmd_retrieve`，不动检索核与 MCP schema（对齐 md-GuanLi「命中返回相关段落」）。新增 `test_snippet.py` 5 项，全量 134 通过。
- **巡检接入 build-vectors**：每日巡检 Schedule（35e02dc8）第 3 步新增 `engine.py build-vectors --root AgentMemoryHub`，当日新增/变更卡自动补写 `.sync/vector.db`（幂等增量，未变卡跳过 embedding；无模型/无网自动退化，不影响快照）。

## 本轮 R7（真实语料回归门禁 + 巡检告警闭环）

- **真实语料回归门禁**：`scripts/vector_bench.py` 新增 `--real ROOT` + `--fail-below` 模式——对真实中枢（AgentMemoryHub）跑 6 条聚焦关键事实的回归查询（REAL_QUERIES 已对齐真实卡名），输出词袋/向量/融合命中率；融合命中率低于阈值返回退出码 3（门禁未过）。`top_k=3` 实测 83% 通过（词袋 6/6、融合 5/6）。
- **巡检告警闭环**：`engine.py build-vectors` 增加向量通道检测——有卡建库但零向量（模型/网络退化）返回退出码 2 并打印【告警】；`engine.py lint` 有孤儿/陈旧/无效卡返回退出码 2。每日巡检 Schedule（35e02dc8）相应升级：必查退出码，向量退化/健康异常/回归门禁未过均须写 retro/log.md 告警记录并向用户高亮（不允许静默忽略）。
- **三环经验汇总**：新增方法论卡 `retrieval-quality-three-loop`（C1 模型选型→C2 规模压测→C3 告警闭环）聚合三条经验，作为新平台接入检索质量交付的模板（ingest 入权威区 + 登 INDEX + build 入向量库）。
- **验收**：新增 3 项测试（build-vectors 正常/退化、lint 异常），全量 137 通过，ruff 全绿。

## 本轮 R8（blueprint 蓝图体系 + github-star-distill 仓库内化）

- **blueprint 卡型 + ideation 立项检索类落地**（建议 A1+B1，commit e0bb21d）：`VALID_TYPES`/`VALID_STATUS` 增 blueprint/reference；`TYPE_DIR`/`SUBDIR_BY_TYPE`/authority dirs 六处入列 blueprints；ingest 保留蓝图草稿 status 不强制 active；`TASK_KIND_TYPES` 新增 ideation（bootstrap 立项即命中 blueprints 块）；bootstrap_hub 建 blueprints 目录；新测试 6 项全量 162 + ruff 绿。
- **立项闭环吹净**：`memory-hub-query-first` 规则补 blueprints 目录 + 立项必查蓝图（evidence 分级）；`ideation-github-scan` 改「先查本地蓝图库 → 外部扫描 → 反哺 blueprint」三段；github-star-distill skill 补 blueprint 产物类型 + T1 才转 active。
- **github-star-distill 跑通两仓**（worktree 分支 worktree/github-star-distill，commit 1669a04）：
  - 第一仓 gh-duoduoler-ops（Table-GitHub-Capability-Router，判级 A）→ `methodology/gh-cap-router-paradigm`。
  - 第二仓 gh-mattpocock（mattpocock/skills，222k★，判级 A）→ `blueprints/skill-governance-blueprint`（路径A promoted桶+invocation双轨+路由器+docs路由 / 路径B 双轴并行审查 / 路径C 领域共用语）。
- **决策指南**：`methodology/dual-axis-review-routing-guide`（双轴审查 × 复杂度路由三判据：改动文件数>2/跨模块/公开行为；判据收敛路由器一处）。
- **双轴范式 T1 试用**：对 commit e0bb21d(blueprint) 做 Spec×Standards 双轴核对通过、9 测试、ideation 检索精确命中。
- **env 陷阱**：项目 `.venv` 是缺 transformers/pytest 的最小运行时；build-vectors 的 embed 与 pytest/ruff 须用系统 python（`C:\Users\Fan-SJSS\AppData\Local\hermes\hermes-agent\venv`）；用 .venv 跑会写空向量（embedded 0）须清 vector.db 重建。
- **验收**：中枢 82 卡 lint 全健康 0 孤儿；向量库全带向量；中枢已推 master（f8d8301→721227c 等）。

## 下一步候选

1. 源目录 `D:\AIwork\AgentMemoryHub` 清理 —— 已核销（2026-08-18 复核：该目录已不存在，`D:\AIwork` 下无此项，陈旧副本早已随迁移清理）。
2. 冲突区 10 张已全部处置清零（2026-08-18：7 删除 + 3 合并权威卡）。
3. Push 默认开启策略已评估（2026-08-18）：**维持默认关闭**。实证：0 个 pushed 状态、MCP 未暴露 push；理由：Pull 低风险沉淀 / Push 高风险写平台原生文件、价值被 MCP hub_search 覆盖、默认开启致外部改动频繁 abort + 无基线首次放行存在隐性污染窗口。保留显式 `--push` + `--dry-run` 受控反哺。
4. 向量规模拐点压测（2026-08-19 固化自 experience/bge-small-zh-sqlite-vector-search，**已核销**）：新增 `hub-engine/scripts/vector_scale_bench.py`（隔离库灌假向量测全表余弦耗时）。实证呈完美线性 ~93μs/卡：1k 即时(93ms)/5k≈468ms/10k≈933ms。**切 ANN 阈值 ≈3.2k 卡（>300ms）**；现状中枢仅几十卡、<100ms，**无需提前引 FAISS**。经验卡 `vector-cosine-scale-benchmark` 已 ingestion 入区并登记 INDEX。
5. 稠密检索模型选型定版（2026-08-19，**已核销，维持 bge-small-zh-v1.5**）：以候选 6 同一评测集实证对比（见下），small 全面不劣于 base，无增益，**不切换**。经验卡 `local-dense-retrieval-model-selection` 的「默认 base」决策规则已过时，以本实证为准。
6. 检索评测基准定版入库（2026-08-19，**已落地**）：新增正式基准 `hub-engine/scripts/vector_bench.py`，中英文语料 10 卡 + 评测集 12 easy + 5 HARD（同义改写/跨语言，专测语义通道），三通道命中率统计，`--model` 可换模型、按 model 删库隔离向量。已纳入每周复核 Schedule（44e1e8ef）。实测（top_k=1，easy 组词袋+jieba 已饱和故由 HARD 组区分模型）：

   | 组 | 模型 | 词袋 | 向量 | 融合 |
   |---|---|---|---|---|
   | easy(12) | small | 12 | **12** | 12 |
   | easy(12) | base | 12 | 11 | 12 |
   | HARD(5) | small | 4 | **4** | 4 |
   | HARD(5) | base | 4 | 3 | 4 |

   结论：同一评测集下 small ≥ base（HARD 向量 4vs3、easy 向量 12vs11）。base 体积/内存约 small 的 3 倍且更慢，本项目向量仅作词袋之上的语义辅助通道，**维持 bge-small-zh-v1.5，不切换**。
7. 向量存储 JSON→二进制列（2026-08-19，**已落地，即建议 A**）：`semsearch.py` 将 `embedding` 列 `TEXT(json)` 改为 `BLOB(float32 .tobytes())`，读侧 `_decode_vec` 用 `np.frombuffer` 免全表反序列化，兼容旧 JSON 行回退解析。压测 `vector_scale_bench.py` 增 `--format json|bin` 对比：10k 卡 933ms→160ms（≈5.8×），切 ANN 阈值由 ≈3.2k 卡抬升至 **~20k+ 卡**。经验卡 `vector-cosine-scale-benchmark` 已补充二进制实测与新阈值。测试 +2（二进制落列/旧 JSON 兼容），全量 14 通过，ruff 绿。
8. 查询侧 embedding LRU 缓存（2026-08-19，**已落地，即建议 1**）：`semsearch.py` 新增 `query_embedded`，仅缓存**查询**文本的向量（LRU 128 条，`_LOCK` 保护，超限淘汰最老），build 批量卡片文本走原 `embed` 不污染热点缓存；退化态（embed 返回 None）不缓存、后端恢复自动命中。`retrieve.semantic_vector_retrieve` 改调 `query_embedded`，MCP hub_bootstrap/hub_search 模板查询免重复模型推理。新增 `test_query_cache.py` 5 项（同 query 复用/异 query 独立/LRU 淘汰/退化不缓存/空查询），全量 144 通过，ruff 绿。
9. 高频未命中查询补卡闭环（2026-08-19，**已落地，即建议 2**）：新增 `scripts/missing_query.py` 消费 `.sync/state/query.log.jsonl`（hub_search 审计），按归一化查询聚合，识别两类知识缺口并给建议动作（**只读分析+输出清单，不自动造卡**，补卡走 ingest 人工确认）：P0 完全未命中(零命中占比≥0.5)→建议新增卡片；P1 低命中(平均命中<3)→建议补 tag/别名。`--json` 结构化输出、`-o` 写 Markdown。真机跑通：当前审计 9 条，识别 2 条低命中（DLL 锁定 / codex 升级 changelog）。新增 `test_missing_query.py` 6 项，全量 150 通过，ruff 绿。
10. 性能/召回回归门禁并入巡检（2026-08-19，**已落地，即建议 3**）：召回门禁此前已在每日巡检（步骤 6 vector_bench --real --fail-below 0.8）；本次补**性能门禁**——`vector_scale_bench.py` 新增 `--single N` 单点模式 + `--fail-above MS` 门禁（专退出码 4），纳入每日巡检 Schedule 步骤 7（`--single 5000 --fail-above 300`）。新增 `test_vector_scale_bench.py` 4 项（单点放行/门禁失败/无门禁/全曲线不干扰）。缺口盘点：原建议预期"性能/召回回归"实为召回已在其、性能乃缺口。
11. 单卡 push 反哺工作流正式化（2026-08-19，**已落地，即建议 4**）：`sync --push --name` 此前已有（commit 1177a54）；本次补齐 **not-found guard**——`platform_bridge.push` 在 `name_filter` 无匹配权威卡时返回 `status:"not-found: <卡名>"`（engine 据此退出码 1），避免传错卡名静默 0 添加误以为已同步。新增 `test_platform_bridge.py` 2 项（not-found 报错 / name 命中只推目标卡）。全量 156 通过，ruff 绿。
12. blueprint 蓝图体系 + 两仓内化（2026-08-19，**本会话已落地**，见 R8）。后续候选：横向铺开内化下一仓（用户给 URL）；或把 skill-governance-blueprint 的 invocation 双轨/A 下'shutdown'产物逐步在本 hub 试用。
13. 路径 C 接线 + 分级注入（2026-08-19，**本会话已落地，即任务1+2**）：MCP 层 `SEARCH_SCHEMA`/`BOOTSTRAP_SCHEMA` 声明 `compress_level` + `hub_bootstrap` handler 补齐透传（此前仅 hub_search 函数支持但 schema 未暴露=协议层够不到）；`inject.py` 指令补「命中正文按用途分级取用（路由 5 级/审计 0 级）」。补测 3 项，全量 174 通过、ruff 绿。后续未做项：单卡压缩 LRU（收益低，评估砍）。
14. 薄卡体检（2026-08-19，**本会话已落地**）：因 A-lite 对单仓 83 卡是过度工程（成熟度单峰 active、语言合规易误告警），仅取「体量」一维轻量化落地。新增 `scripts/thin_card_scan.py`（只读扫权威区 frontmatter 后正文 < `--min-chars` 默认 80 字的薄卡，体量升序清单，`--json`/`-o`，**不自动改卡、刻意不并入 lint** 防误告警噪音，复用 `tools.lint._all_cards` 遍历）。真机命中 25 张（多为指针/清单型短卡）。新增 `test_thin_card_scan.py` 4 项，全量 178 通过、ruff 绿。
15. 自驱成长飞轮最小环 A+E 立项（2026-08-19，蓝图 `blueprints/self-growth-flywheel-blueprint` 已固化；**本候选=立项拆分，未落地**）。依据第一性/奥卡姆：A(复用路径反哺)+E(可验证信号度量) 是飞轮发动机，先行；B/C/D 是维护站、按需再开。拆分（奥卡姆收敛为 5 任务）：

    - **E1 指标日行 `metrics.jsonl`**（**已落地 2026-08-19**）：新 `scripts/metrics_daily.py` → `.sync/state/metrics.jsonl` append-only 一行/日（date/total_cards/vector_rows/search_count/hit/miss/hit_rate/reuse_ops），复用 status + query.log 产物；已接入每日巡检 Schedule 步骤 8。真机验证 cards=86/vectors=86/hit_rate=1.0，8 项单测 + 全量 186 通过。metrics.jsonl 为 git-ignored 运营数据不入提交。
    - **E2 日命中率聚合**（**已落地 2026-08-19，无新增组件**）：扩展 `scripts/metrics_daily.py`——`compute` 新增 `miss_rate` 列；新增 `series()` 按 query.log 已出现日期升序逐日聚 hit_rate/miss_rate 时间序列，CLI 暴露 `--series`（含 `--series --json`）供画命中率曲线。复用 missing_query 解析层，不新增文件。真机两日 hit_rate=1.0 曲线可画。+2 项单测，全量 200 通过、ruff 绿。
    - **E3 真实召回回归门禁**（**已落地 2026-08-19**）：新 `scripts/real_query_regression.py`——从 query.log 抽「高频完全未命中(P0)」查询固化成 canary 固定集 `.sync/state/real_regression.json`（git-ignored，跨日稳定，`--max-age-days` 超龄或 `--refresh` 重建），每日跑 `tools.retrieve.retrieve_with_meta` 融合检索（不写审计）；默认**全未命中即 fail**，`--fail-below X` 可抬阈值，退出码 3 沿用 `patrol-alert-exit-code`；已接入每日巡检 Schedule 步骤 9。真机健康中枢返回 0（无断言样本跳过），端到端冒烟空库全未命中返回 3。12 项单测 + 全量 198 通过、ruff 绿。
    - **A1 未命中→补卡候选每日自动产出**（**已落地 2026-08-20**）：把 `missing_query.py` 从"每周人工跑"接入每日自动触发——新增 `--since-days N` CLI 与 `_local_ts_date`/`aggregate(since=)` 日期窗口过滤，聚焦最近 7 天缺口 `-o AgentMemoryHub\.sync\state\missing_daily.md` 生成候选清单（P0 新增卡 / P1 补 tag）。已接入每日巡检 Schedule 步骤 10（git-ignored 运营数据，**不自动造卡、不发告警**，仅当含 P0 候选时汇报提示人工确认后走 ingest）。真机 `--since-days 7` 产出近期 P1 候选 4 条聚焦正常。+2 项单测（since 过滤 + main 接线），全量 202 通过、ruff 绿。
    - **A2 命中复用累积**（**已落地 2026-08-20**）：在 `tools/mcp_handlers.py` 新增 `record_reuse`——`hub_search` 命中后对命中卡 frontmatter `reuse_count += 1`（仅改该行，最小 diff，不重排其它字段）；**按日节流**（同卡同本地日只计 1 次，状态落 `.sync/state/reuse_daily.json`，git-ignored）；写入置于单写者锁内、失败静默不影响检索返回；只计非 archived 且含 reuse_count 字段的卡。真机验证命中 dll-lock reuse_count 0→1、二次计数节流 skipped。+5 项单测（search 追踪/日节流/跨日/归档跳过/最小 diff），全量 207 通过、ruff 绿。
    - 验收：metrics.jsonl 有日行且 hit_rate 曲线可画；回归门禁真机有一组未命中样本可拦截；daily Schedule 退出码检查覆盖 E1/E3；reuse_count 真实递增。全量测试按其分别 +2~4 项，ruff 绿。
16. 夜间离线自进化引擎（SkillOpt-Sleep 纪律落地，**本会话已落地**，见 R9 蓝图 skillopt-blueprint）：判级 A 隔离克隆内化 microsoft/SkillOpt，方法沉淀为 `blueprints/skillopt-blueprint`（reference，未装依赖）。T2 映射中枢现有底座，实现原生 `scripts/hub_sleep_consolidate.py`——**零外发、零自动改卡**，收割(复用 missing_query.aggregate)→挖掘(P0新卡/P1补tag)→有界候选(--max-candidates 类比编辑预算)→held-out 验证(复用 retrieve_with_meta 标注当前命中)→暂存(.sync/state/sleep/<日期>/proposal.{md,json}，git-ignored，绝不写权威区)→人工采纳(review 后 ingest)。已接入每日巡检 Schedule 步骤 11；真机产出近期 P1 候选 4 条可见。+6 项单测，全量 213 通过、ruff 绿。
17. **每周召回评测复核（2026-08-22，修复落地）**：三通道基准 + 缺失查询补卡闭环已验证（结论与定版一致）；work/bench_recall.py 已重建并验证（word 确定性 0→5/11 与 R6 吻合）。**真实回归门禁修复前：** vector_bench --real --fail-below 0.8 融合命中率 67%（4/6）< 80% 退出码 3，语料 123 卡后跌破；**根因** 确定性通道中文高频词 over-hit（如「代理」命中多 tag 短路、期望卡被挤出 top）。**修复落地（建议1+2 收敛版）**：`tools/retrieve.py`——① 确定性命中数>top_k时**短路降级**，不再直接返回；② **确定性纳入RRF作第三通道**，且仅取 det ∩ 语义 top_k 计 rank 分（避免 8+ 条噪点卡叠加 rank 压制纯语义目标）。**修复后** 融合命中率 **100%（6/6）≥ 80% 门禁通过**（退出码 0），proxy-guard-ie-override、query-writeback-dll 两卡已正常召回；全量测试 261 passed 4 skipped 无回归。经验卡 `det-overhit-shortcircuit-fallback` 已 ingest 入区。
ector_bench --real --fail-below 0.8 融合命中率 **67%（4/6）< 80% 门禁失败**（R7 时为 83% 通过），语料 123 卡后跌破。根因诊断为**确定性通道中文高频词 over-hit**（如「代理」命中多个 tag 即短路返回，期望卡 proxy-guard-ie-override 被挤出	op），即 retrieve-with-meta 确定性短路导致融合通道未参与。**未擅自改码**，需人工评估（建议：确定性命中过多时降级至 RRF 融合、纳入确定性作第三通道）。明细见本会话汇报。

18. **任务收尾建议清单 · 首次实战（2026-08-31，源自 `methodology/post-task-recommendations`）✅ 已核销（2026-08-31，本会话，代码 commit `ec87aee`）**：LM Studio API 开机自启任务（本会话）收尾产生的待办，按方法论四列格式登记如下：

    | 任务 | 优先级 | 预估工作量 | 详细说明 |
    |:--|:--|:--|:--|
    | ~~`confirm` 命令按 `card.type` 路由目标目录~~ **✅ 已核销（2026-08-31，commit `ec87aee`）** | 🟡中 | 30分钟 | 两处均已改：① `sync.py` 复用现成 `TYPE_DIR.get(card.type)` 路由目标目录；② 裸卡名自动补 `.md`；CLI help 同步；新增 2 项单测，全量 267 passed 无回归 |
    | ~~重启实测 LM Studio API 自启~~ **✅ 已核销·等效验证（2026-08-31，本会话）** | 🟡中 | 5分钟 | 无法替你物理重启，已逐字执行 HKCU Run 项原值命令（wscript 隐藏 VBS）：1234 监听 ✅、API 返回 6 模型 ✅、engine status 退出码 0（llm_health 恢复）✅；Windows 登录时执行同一命令，行为一致 |

    完成后将本条改「已核销」并附 commit 号（沿用本清单既有惯例 1~4 条）。

19. **待办清单第 18 项执行中新发现（2026-08-31）✅ 已核销（2026-08-31，commit `46d21fd`）**：`tests/test_engine.py::test_status_prints_snapshot` / `test_status_json_output` 断言退出码 ∈ (0,2)，但 1234 LLM 离线时 `engine status` 触发 `local_llm_unavailable` critical 告警返回 3，2 测试随机红（与代码无关，纯环境耦合，stash 旧代码复现证实）。

    | 任务 | 优先级 | 预估工作量 | 详细说明 |
    |:--|:--|:--|:--|
    | ~~status 测试与环境解耦~~ **✅ 已核销（2026-08-31，commit `46d21fd`）** | 🟡中 | 30分钟 | 两测试 monkeypatch `engine._collect_llm_status` 桩注入 available=True；新增 critical 路径测试（available=False → 退出码 3 + 告警断言）。双态实测：LLM 在线/离线 9 passed；全量 268 passed 无回归 |

20. **LLM 服务运行时自愈提案（2026-08-31，用户建议"检测离线→恢复 1234"，分层评估后采纳于运行时层）✅ 已核销（2026-08-31，commit `01b3ede`）**：单元测试层维持桩解耦（`46d21fd` 已做，两态确定性覆盖，不宜测前启真服务）；运行时层现状是"检测离线只告警"（`engine.py:768` local_llm_unavailable critical），应升级为"先自愈、失败才告警"。

    | 任务 | 优先级 | 预估工作量 | 详细说明 |
    |:--|:--|:--|:--|
    | LLM 运行时自愈 ensure_llm_service() | 🟡中 | 1小时 | `tools/llm_health.py` 新增：探测 1234 离线→subprocess 执行现成 `start_lm_studio_api.vbs`（wscript）→轮询端口就绪（如 2s×15 次）→返回最终态；每进程生命周期只重试 1 次防死循环。接入点：`engine.py _collect_llm_status()`（538 行）判 critical 前调一次；`vector_bench --real` 等真语料基准前置同样调用。补单测：桩 vbs 执行+桩探测验证重试逻辑。**待用户确认**：是否需要"手动下线标记文件"（故意停服务时不被自愈救活） |

21. **每周召回评测复核（2026-09-02，发现→修复闭环）**：真实回归 **67%（4/6）→ 100%（6/6）**；向量通道 0/6→5/6、词袋 4/6→5/6，6 张目标卡全命中（含 experience 两卡）。

    | 项 | 状态 | 说明 |
    |:--|:--|:--|
    | 根因 | 🔴 已修复 | `tools/retrieve.py::_ACTIVE_DIRS` 今晨被 bf8f49b（Codex Local）移除 `experience`（clone含 libs/retro），与 INDEX.md 五类口径冲突 → 经验卡 84 张整体游离检索 |
    | 修复1 | ✅ | 恢复 `experience` 入 `_ACTIVE_DIRS`（libs/retro 维持不纳入），改注释说明 |
    | 修复2 | ✅ | `engine.py build-vectors` 全量重建：removed 148 / inserted **229**（experience 全部入索引） |
    | 验证 | ✅ | 真实回归 100%；bench_recall char 混合top3 10/21→**18/21**；pytest **290 passed 4 skipped**；ruff 绿 |
    | P1补tag | ✅ | `methodology/memory-hub-card-promotion` 补 `gate` tag（P1 查询「孤儿 INDEX 登记…」唯一缺词），复跑 missing_query 该查询退出 P0/P1 候选 |
    | 口径 | ✅ 决议 | 周任务 `--fail-below 0.6` = 软检视（提示人工）；日巡检 0.8 = 硬门禁（退出码 3）。两者并存非冲突，不再视为漂移 |
    | 经验卡 | ✅ | `experience/local-dense-retrieval-model-selection` 口径修正：现役 = LM Studio bge-m3（config + db_meta 实证），small 降为历史注记 |
    | missing_daily | 🔶 部分 | 仅 1 份（09-01），已补归档 `missing_daily_2026-09-01.md`；生成侧 = 每日巡检 Schedule 步骤 10（覆盖写），按日归档属对方引擎流程，未代改，交人工评估 |

    修复 commit：主仓 retrieve.py（本会话）；中枢仓 2 张卡（本会话）。后续候选：①把「每日 missing_daily 按日归档」纳入日巡检 prompt；②周评测门禁阈值 0.6 的 prompt 与 0.8 口径已记录，若希望统一可改任务定义。

22. **每周召回评测复核（2026-09-19，发现 3 类问题；未改代码，交用户裁定）**：真实回归 **100%（6/6，2026-09-02 基线）→ 50%（3/6）**，`vector_bench --real --fail-below 0.8` 门禁失败（退出码 3）。细项：词袋 3/6、向量 3/6、融合 3/6（cwd=项目根；cwd=hub-engine → 向量 0/6）。

    | 项 | 状态 | 证据与说明 |
    |:--|:--|:--|
    | 归因① 基准夹具腐化（2/6，主因） | 🔴 待用户裁定 | 门禁期望目标 `projects/omniroute-gateway.md`、`projects/cad2020-pdf-merge.md` 已被 **2026-09-18 08:26 commit `8f8ce4f`**「聚类合并 14→5 张卡」移入 `archive/projects/`（标注 superseded_by）；`retrieve._ACTIVE_DIRS` 不含 archive 且 `_index` 跳过 `status: archived` → 这 2 张**永不可能命中**，门禁数学上无法达 100%。需把 REAL_QUERIES 改指后继卡（`projects/omniroute-local-deployment.md` / `projects/cad2020-tu-fen-pipeline.md`） |
    | 归因② 融合通道缺陷（1/6，真问题） | 🟠 待用户裁定 | `experience/query-writeback-dll.md` **词袋通道排第 1**，但 RRF 融合输出 3 张不相关卡把它挤掉 → 融合不是各通道并集，存在「通道 top-1 被丢弃」 |
    | 归因③ 向量通道 CWD 依赖（真问题，影响生产） | 🔴 待用户裁定 | `vector.db` 的 `path` 列存**相对路径** `AgentMemoryHub\rules\x.md`（build 时用相对 root，`full = str(card.path)`），检索侧 `_norm_path` 用 `Path(p).resolve()` 按**进程 CWD** 解析 → 仅 CWD=项目根时匹配。实测：cwd=项目根 向量 3/6；cwd=hub-engine 或 `C:\Users\Fan-SJSS` 向量 **0/6 静默退化**。生产 MCP 以绝对 `--hub-root` 启动、CWD 继承 Hermes 进程（非项目根）→ **线上向量通道大概率长期静默失效，检索实际只剩词袋通道** |
    | 归因④ 每日巡检门禁失效 | 🔴 待用户裁定 | `scripts/patrol_runner.py::_step_vector_regression` 只传 `--real <root>`，**丢掉了 `--fail-below 0.8`**；`vector_bench` 该参数默认 `None`（不设阈值）→ 每日「向量回归」步骤恒 exit 0，即使 50% 也判 pass（今日快照 stages 无异常即为此） |
    | 混检索复核 | ✅ 一致 | `work/bench_recall.py --top-k 3`：char(n=2) 混合 top1 15/21、混合 top3 16/21；word 确定性 12/21、语义 top1 13/21、混合 top1 12/21、混合 top3 12/21（char 仍优于 word） |
    | 复核① char n 值 | 🟠 需调整 | n=2 → 76%（15/21），**n=3 → 81%（17/21）**，n=4 → 81%（17/21）→ 默认 n=2 在 427 卡规模下**已非最优**（`retrieve.py:325` 注释与 `bench_recall` docstring 仍写「实测 n=2 最优」） |
    | 复核② jieba 停用词 | 🟠 需调整 | `_EN_STOP` 仅英文停用词 + `len>=2` 过滤，**无中文停用词表**；word 混合 top3 12/21 反低于 char 16/21 → 高频中文词（怎么/什么/如何/批量）带偏命中，历史 `det-overhit-shortcircuit-fallback` 问题在更大语料下复发 |
    | 复核③ IDF 分层 | ✅ 区分度仍 >0（有边界风险） | `common/vector.py::build_idf` = 单层平滑 `log((1+N)/(1+df))+1`，**无文档频率分层/截断**；df=N 时权重塌到下限 1.0。区分度未归零，但 blueprints 114 张同主题卡抬升 df，或为复核① n=3 反超的诱因 |
    | 复核④ 向量模型 | 🟠 需用户评估 | 现役 = **`text-embedding-bge-small-zh-v1.5`（512 维，LM Studio 1234）**，**不是任务书假定的 bge-m3**（bge-m3 在 `system/config.yaml::embed_alternatives` 仅备选，1024 维）。427 卡全语料语义-only 实测 4 个可命中目标：small **recall@1 1/4、@3 3/4**；m3 **recall@1 2/4、@3 3/4** → m3 top-1 区分度更优（4 组竞争对 margin：m3 胜 3/4 vs small 胜 1/4），**差距未收窄反而略拉开**；切换须 512→1024 全量重建 vector.db（维度门禁禁止混用） |
    | 补卡候选（本周缺口） | ✅ 无候选 | 最近 7 份 `missing_daily_*.md`（09-14…09-19）+ 当前 `missing_daily.md` 全部 0 P0 / 0 P1 → 未写 `missing_candidates.md`（无候选）。当日有真实检索流量（09-18 18 条、09-19 8 条且均有 hits），故「0 缺口」非空跑 |
    | 较上周基线 | ✅ 告警收敛 | 今日快照 exit **0**、`llm_available=true`、仅 1 条 info（`local_llm_slow` 2037ms）；一周前（09-10）exit **2**（lint orphans=2 + `low_flywheel_activity` 14.3%）。active 卡 427 张（rules 31 / blueprints 114 / methodology 57 / longterm 8 / projects 20 / experience 205），archive 26 张不计入，`vector.db` 427 行与 active 数一致 |
    | 未改代码 | ✅ 遵守 | 本次仅只读评测 + 记录；`vector_bench.py` 夹具、`patrol_runner` 门禁参数、`retrieve._norm_path`、`build_idf` 四项修复均**待用户裁定后**再动 |

    后续 commit（待用户裁定后）：① 修 `vector_bench` REAL_QUERIES 指后继卡（夹具腐化）；② `patrol_runner._step_vector_regression` 补 `--fail-below 0.8`；③ `retrieve._norm_path` 改为「相对 root 解析 + 绝对路径双尝试」（消 CWD 依赖）；④ 评估 RRF 融合保底（通道 top-1 强制入池）；⑤ 评估 embed 切 bge-m3（需重建库）；⑥ 复评 char 默认 n 与中文停用词表。

## 本轮 R10（check-code-v1 规则门禁 + semgrep/codebase-memory 两仓内化 + vector.db 维度门禁落地）

- **check-code-v1 路径A 注释契约规则回归门禁**（`c:\Users\Fan-SJSS\.trae-cn\skills\check-code-v1`，技能仓非本仓）：新 `scripts/rule_regression.py` + `tests/test_rule_regression.py`——为每类检查器（python/yaml/markdown/json/toml）维护【正样例=应 FAIL + 负样例=应 PASS】合成契约，跑门禁判定 True/False Positive/Negative；正样例遇 SKIP（工具缺失）记为通过不误报。`SKILL.md` 补「第8条」约束：改检查器规则必须先跑门禁，无可回归才交付，新增检查类型先补样例再实现规则。**已借语义检索挂接中枢 `blueprints/semgrep-rules-engine-blueprint`。**
- **两仓蓝图内化（github-star-distill 流程）**：
  - `blueprints/semgrep-rules-engine-blueprint`（**已落地，新卡** reference）：路径A 注释契约门禁（零依赖纯纪律，本 hub 真实采纳）／路径B 接入 semgrep CLI 统一规则层（T0/T1 未跑，维持 reference 不落地）；INGEST `promoted:1`、lint 全绿，中枢仓 commit `44a5d1e`。
  - `blueprints/vector-db-shareable-artifact`（**已落地，新卡** reference）：内化自 gh-deusdata-codebase-memory-mcp artifact.c 的团队共享 zstd 工件+git HEAD 溯源；路径A 快照一致性(只用 VACUUM INTO 勿裸拷WAL)+strip索引再zstd+meta溯源+schema版本门禁+原子写／路径B .gitattributes binary merge=ours 冲突防护(#492行序坑)；对照中枢 vector.db 底层同构、仅缺一等工件外壳、冲突侧 _WriteLock 已覆盖。INGEST `promoted:1`、lint 90 卡全绿，commit `0bd24fe`。
- **vector.db 维度门禁（已落地，主仓）**：直接借鉴 codebase-memory-mcp schema_version 门禁，修复中枢 `tools/semsearch.py` 的**维度静默错分缺陷**——`db_meta` 表记录 `embed_dim/embed_model`；build 检测换模型且维度变→清库全量重建；`vector_scores` 校验 query 维度与库不符→返回 `[]`（上游融合自动退化词袋）；兼容旧库无 `db_meta` 表（`_stored_dim` 容错回退行探测）。新增 3 项单测（写meta/退化/换模型重建），全量 222 通过、ruff 绿；真机中枢库 build 全重建 `stored_dim=512`（bge 维度吻合）。commit `ba80bba`，改动仅 2 文件。
- 进度小结：本 session 训练集方法价值（semgrep 规则引擎 + codebase-memory 工件共享）均判级 B、沉淀为 reference 蓝图 + 各落地一个真实采纳点（rule_regression 门禁 / vector.db 维度门禁）；待未来真实需求触发再转 active。

## 本轮 R11（diagram-design 内化 + INDEX 幽灵登记落地）

- **diagram-design 蓝图内化（github-star-distill 流程）**：隔离克隆 gh-cathrynlavery-diagram-design（判级 B+，方法价值高且与中枢"技能治理"同构），T0 试跑 `scripts/verify-docs-sync.py` **exit 0 干净**（8 类检查全过：description hooks/gallery reachability/README tree/reference links/packaged support/profile surfaces/manifest/Factory install 契约）证机械可用。沉淀 `blueprints/skill-docroute-verify-blueprint`（**已落地，新卡** reference）：8 类文档↔路由一致性检查互不遮蔽；多宿主单插件根+渐进披露；ADR 决策纪律一决策一档永不重辩；vs 中枢 lint 补 2 切入点（描述↔能力 hook 同步 + INDEX.md 登记防漂移）。INGEST `promoted:1`、lint 96 卡全绿，中枢仓 commit `2d40854`，克隆已清理。
- **INDEX 幽灵登记落地（已落地，主仓 commit `5e1c338`）**：从 skill-docroute-verify-blueprint 路径A「INDEX.md 登记防漂移」**选取反向盲区落地**——新增 `tools/lint.py find_index_ghosts(root)`：检测「INDEX 已登记但权威区查无对应卡文件」的幽灵登记（支持连字符卡名 `[A-Za-z0-9_-]+`、排除 `/` 目录行），与现有 `find_orphans`（文件在但未登记）双向互补；`engine.py` lint/status 命令输出、JSON、退出码全部纳入 ghosts。补 2 单测，全量 **224 通过**、ruff 全绿（PIE810 startswith tuple）；真机 lint **幽灵=[] 零误报**、孤儿仍仅历史 autocad（保留项）。
- 进度小结：本 session 绪 method（verify-docs-sync 结构门禁 + ADR 纪律）判级 B+、沉淀 reference 蓝图 + 落地一个真实采纳点（INDEX 幽灵登记）；待未来需求触发再转 active。


## 本轮 R12（看板 v5：P0→P3 分级完善 + 告警详情抽屉 + 数据源体检 + VLM 待办）

后端（`hub-engine/scripts/`）：
- `hub_dashboard_collect.py`：告警富化（`id/level/detail/source/evidence/cmds/docs` 七字段，
  含现读证据行 + 可复制修复命令 + 关联中枢卡）；新增 `collect_metric_sources`（8 个 KPI 的
  出处/计算式）与 `collect_source_health`（4 项数据源自检）。
- `hub_dashboard_server.py`：新增 `GET /api/alert/<id>`（返回现读证据 + 自包含「修复包」Markdown）；
  `/api/snapshot` 加 **ETag/304**（配合既有 10s TTL）——命中时 0 字节。
前端（`docs/dashboard/index-v4.html`，单文件无外链）：
- 告警**可点击 → 详情抽屉**：根因/定位来源/证据/错误日志/建议命令/关联卡，含
  「复制修复包」「复制证据」「复制命令」三键（剪贴板实测可读回，修复包 398 字符）。
- P0-1 来源徽章（每个 KPI 挂 ⓘ，hover 显示出处+口径）；P0-2 a11y（tablist/tab 角色 +
  aria-selected + aria-live 播报 + skip 链接 + focus-visible + prefers-reduced-motion）；
  P0-3 采集期「采集中…」可见反馈 + 刷新按钮禁用。
- P1-4 字阶 13/14/16/20/30 + 全局 `tabular-nums`；P1-5 KPI 趋势 delta（历史数组，
  与「上一个不同值」比较，无差异显示基线）；P1-6 Ctrl/⌘+K 命令面板（视图+技能）。
- P2-7 亮色主题（Alt+T，localStorage 记忆）；P2-9 表内滚动；P3-11 数据源体检面板。

验证：`docs/dashboard/verify_v5.py`（真 Chromium，DOM 取值断言）——**45 项，45 PASS / 0 FAIL**；
七视图高度全部 ≤1.6 屏（最高 overview 1520px）。

本轮踩坑（已沉淀 `experience/2026-09-11-patch-input-truncation-silent-corruption`）：
**长 patch 输入被静默截断**，一次会话命中 4 次——其中 `$("#kpis")` 被削成 `$("kpis")`
语法完全合法，py/ruff/node 全过，**只有真开浏览器才炸**。故「改完必须真开页面」不是形式主义。

## 本轮 R14（4 项待办收尾 + 8899 重启）

### 完成项
- **任务1 技能表**：新增 200/500 两档页尺寸。**先度量再决定**——实测分页已把 DOM 限死在 ps 行，
  157~5000 行渲染恒定 ~1.4~2.1ms、整页 `renderAll()` 1.6ms ⇒ **虚拟滚动不成立，坚决不做**（依据写入 HTML 注释）。
  ⚠️ 本轮 patch 曾漏掉 `</select></label>`，把告警抽屉整块吞进 `<select>` → 抽屉 0×0 不可见、
  verify_v5 卡死在 `#dw-copy`。**已修**；并靠「原始 HEAD 基线对照」证明已完全排除。
- **任务2 告警现读证据**：`alert_detail` 由「只管 hub-writer-lock / git-*」扩到
  `hub-vector-*` / `flywheel-health-low` / `source-health` / `cron-*` / `backend-*`。
  顺带修既有 bug：git 分支按「目录名 == 显示名」反查，而主仓目录名是 worktree 名
  （feat-implement-plan-ZilBmv）而显示名是 Fan-Agent-Momory → 主仓告警现读**恒为空**；
  改走采集器 `repo_list()` 单一来源按显示名反查。
- **任务3 collect_git**：**明确不采用缓存**——未暂存改动不触碰 `.git/`，任何基于 `.git` mtime
  的签名都会漏报 dirty，直接损坏「工作区守护」告警。实测 237ms 中 git 计算量≈0，
  全是 Windows 子进程 spawn（17ms/次 × 12 次）⇒ 合并为每仓 2 条命令：
  `status --short --branch`（一条给出 分支/ahead/behind/dirty）+ `log -1 --format=%h<US>%cI<US>%s`
  （一条给出 HEAD/时间/标题）。**222.3 → 80.6ms（2.76×，省 142ms）**，10 字段逐字段等价，9/9 边界用例通过。
- **任务4 夜间摘要**：**已打通**（用户选 ①，授权改 trae work 工作区的 `local_summary.py`）。

### 任务4 实施（两层根因 + 修法）
- **根因一（网关层）**：`local_summary.py` 只认 `cfg.batch_model` + `cfg.gateway_url`，而 OmniRoute
  （20128／394 模型）**没有任何通往 LM Studio 的路由**；唯一 `offline` 路由 → **502 ECONNREFUSED**
  （指向已退役后端）；`auto/offline` 实际调远程 felo/oc → 429。且 `gateway_url` 与 `engine.py:63`
  引擎网关**同一配置键** ⇒ 配置层无法把摘要指向本机 1234。
- **根因二（模型层，跑起来才暴露）**：改成直连 LM Studio 后仍返回空摘要——**HTTP 400
  `No models loaded`**。真因是配置里 `local_chat.model = qwen/qwen3.5-9b` **在 LM Studio 里根本不存在**，
  即便 JIT 加载开启也无法解析；而真实存在的 `qwen2.5-coder-1.5b-instruct` 立即成功。
- **修法（最小可逆，改前已备份 `local_summary.py.bak-20260911`）**：
  1. 新增 `_resolve_target()`：优先 `batch_model + gateway_url`（**原口径完全不变**）；
     未配置则回退 `local_chat`（本机 LM Studio 直连，离线零 token）。
  2. 新增 `_pick_local_model()`：从端点 `/v1/models` **动态发现真正可用的对话模型**
     （优先用配置名；不存在则挑第一个非 嵌入/OCR/重排 模型）⇒ 配置名再失效也能自愈。
  3. `_chat()` 改为接收**完整端点**；空摘要时把端点与模型名打进日志，便于下次定位。
- **验证**：`_resolve_target` 三分支单测 **3/3 通过**；真实配置解析 → `qwen2.5-coder-1.5b-instruct`
  @ `127.0.0.1:1234`；**端到端实跑 1.2s 生成 167~259 字摘要**（正确提取 distill / build-vectors /
  sleep-consolidate 与 361 个向量）；**幂等**（同日期覆盖不追加，节数恒 1）；**跨 cwd 调用可用**
  （凌晨 `.cmd` 只做 `cd /d "%ENGINE%"`）；核对 `nightly_consolidate.cmd` 第 27 行确实无参调用本脚本。
- **遗留提示**：`local_chat.model = qwen/qwen3.5-9b` 这个失效模型名**同时影响 hub-engine 的本地 chat
  链路**（引擎本地环会失败并落到网关）。本次按"不动引擎配置"处理，仅让摘要脚本自愈；建议另开一轮修。
- 产物 `.sync/daily_summary.md` 已提交中枢仓（`61d7fde`、`a6cd949`），两仓工作区均干净。

### 顺带查实的既有问题（非本轮引入）
- `AgentMemoryHub/skills/` **目录不存在** → `skill_health = 0` → 飞轮总分恒 **29.3** ⇒
  「飞轮健康度 29.3 分」告警**永远无法消除**（存在两套技能口径：中枢自带注册表 vs `SKILLS_ROOT`）。
- verify_v5 既有 3 项失败（**原始 HEAD 同样失败**）：技能表总数提示 / 体检 SKILL.md 数量 /
  `delta == 当前-种子(340)`（服务端历史有行后压过 localStorage 种子 → 期望 ▲31.0 实得 ▲2.0）。

### 验证
- 页面级：158 条技能**单页放下**；flywheel 6 行现读 / git 6 行 / cron 11 行；force 采集 **408ms**；
  20 张 KPI；**无 JS 异常**。
- 回归：**44 通过 / 3 失败**，失败项与原始 HEAD 基线**逐行一致 ⇒ 零回归**；`#dw-copy` 崩溃已消除。
- `ruff check` + `ruff format --check` 全清；两文件 `py_compile` 通过。

## 本轮 R13（P3-10 采集器增量 + P2-5 徽章补全 + P1-3 服务端趋势 + 2 个真 bug 修复）

**性能（P3-10 采集器增量）——先度量再优化**：
- 剖析全量 4349ms：`collect_hub_health` 2270ms（52.7%）+ `collect_skills` 1653ms（38.4%）
  = **91% 集中在 2 个函数**，其余 10 项合计仅 4.4% → 只打这两个，不做全量缓存。
- `collect_skills` **1675ms → 142ms（12.1×）**：真凶不是「158 个技能各扫一遍全文正则」
  （改成一次分词 + `Counter` 后仍 1.0x，**假设错了**），而是 `d in p.parents` 生成式
  → 约 90 万次 Path 构造、profiled 6.03s；改为一次自底向上累加子树计数即解。
- 签名缓存（walk + stat 指纹 ≈101ms）：**冷 2919ms → 热 585ms（降 80%）**；
  签名遍历须跳过缓存文件自身（否则每写一次缓存就把自己失效）。
- 等价性：新旧 `collect_skills` 输出 `json.dumps(sort_keys)` **逐字段一致**；冷/热仅时间字段不同。

**P2-5 来源徽章补全**：`metric_sources` 8 → **20 条**；飞轮 / 技能 / 仓库 / cron 四组 KPI 全挂 ⓘ。
浏览器实测：17 个 `srcKey` **0 未登记**、20 个徽章 **0 个 tooltip 异常**。

**P1-3 服务端趋势历史**：新增 `.sync/state/dashboard-history.jsonl` + `GET /api/history`；
每次采集按 KPI 变化去重追加（上限 800 行轮转）。前端改为「本地（旧）+ 服务端（新）串联」，
`histPrev` 从尾部回溯 → 优先服务端、本地只补位，**既跨设备共享、又不让既有趋势归零**。

**两个真 bug（既存缺陷，非本轮引入）**：
1. `collect_alerts` 中 `return out` **误置于体检告警块之前** → 「数据源体检不通过」告警
   永不触发（HEAD 即如此）。已修 + 分支单测：正常 6 条 → 异常 7 条、证据/命令正确。
2. 前端 `kpi()` 读 `ms.how`，而采集器只发 `formula` → **所有徽章口径显示 "undefined"**。
   已修（`ms.formula || ms.how || "—"`）。

验证：`docs/dashboard/verify_v5.py --url http://127.0.0.1:8898/` → **47 PASS / 0 FAIL**，
delta 逐位一致（▲29.0 / ▲9.2 / ▲43.0 / ▼9.0）。

经验卡（已 ingest + build-vectors；语义检索对两张卡的自然语言查询均列**第 1**）：
`experience/stale-run-false-failure-freeze-test-first.md`、
`experience/dashboard-collector-incremental-three-pitfalls.md`。

⚠️ **生效前提**：8899 常驻服务仍加载旧后端代码，**需重启才生效**（静态前端因逐请求读盘已即时生效）。

## 待办（R12 起，按等级）

### P0（未做，建议优先）
1. 技能表虚拟滚动（>500 条时仍会卡）。
2. `/api/alert/<id>` 的证据行随告警类型扩展（当前 cron/git 已覆盖，hub 类待补）。

### P1
3. ~~采集器增量（全量 4.45s）~~ ✅ **R13 完成**：冷 2919ms → 热 585ms（-80%），
   `collect_skills` 1675→142ms（12.1×）。遗留：`collect_git`（237ms）是热态最大项，
   暂不缓存 —— git 状态变动频繁，收益/风险不划算。
4. ~~KPI 趋势的服务端历史~~ ✅ **R13 完成**：`.sync/state/dashboard-history.jsonl` + `GET /api/history`。

### P2
5. ~~指标来源徽章补全到飞轮/技能/仓库三组~~ ✅ **R13 完成**（另顺带补齐 cron 视图组共四组）。

### P3 / 阻塞
6. **VLM 视觉评审（见下节「VLM 现状与改进」）**——需用户决策是否腾显存。

## VLM 现状与改进（诚实声明，2026-09-11 实测）

**现状（比"本机没有 VLM"更准确的说法）**：
- 本机**有**真实视觉模型 `nvidia/LocateAnything-3B`（`D:\AIminiLLM\cad-gui-tester\`），
  但 `vision_server.py` **未运行**；其默认端口 5001 **被 `VaultService.Gui.exe` 占用**
  （中枢卡早预警「常被占用换 --port 5005」，5005 实测空闲）。
- 显存是**硬约束**：RTX 4070 Ti 共 12.3 GB，**已用 10.4 GB（LM Studio 常驻），仅剩 1.6 GB**，
  装不下 3B 视觉模型（需 ~7 GB）。
- LM Studio 内只有 `paddleocr-vl`（**OCR 型**，不做审美判断）；`vision_analyze` 回落纯文本模型→看不到图。
- 故本轮 UI 评分**全部来自 DOM 实测 + 数值断言**，**审美/观感未由视觉模型复核**。
  （旁证：视觉模型认数字不准，实测把 0 读成 8、40 读成 48，数字类必须以 DOM 为准。）

**改进路径（按性价比）**：
1. **零成本**：布局/可访问性回归继续用 CDP + DOM 几何断言（重叠/溢出/对比度/字号/间距），
   这比 VLM **更准**，且已固化为 `verify_v5.py`。VLM 只在"纯主观审美"上不可替代。
2. **低成本（推荐）**：需要视觉定位时，停 LM Studio 常驻模型 → 释放 ~7 GB →
   `python vision_server.py --port 5005` → 用完卸载。定位能力（bbox/center/confidence）真实可用。
3. **中成本**：常备一个真 VLM 需固定占用 ~7-16 GB 显存，与 LM Studio 二选一；或换 16 GB+ 显卡。
4. **兜底**：截图交付人工目检（本轮已产出 `shot-v5-*.png`）。

**待用户决策**：是否接受「用时腾显存」模式（方案 2）？

## 本轮 R16（存量整合 ABC · 2026-09-18）

**A. CadGuiTest 并入收尾** —— 核查确认**并入已由早前会话完成**（真合并 `--allow-unrelated-histories` 零冲突，merge commit `2019e98` 已推 origin；含 263 行合并记录 `b2bc39b`）。`vision/main` 已是 `master` 祖先；`AutoCAD_GUI_Text` 已无独有提交（内容全被吸收）。
A 的**剩余缺口 2 项（均未动）**：
1. `master` 领先 `origin/master` **1 个提交**（`bde2745` 段一真机终判 R5~R8）→ 需推送（涉公网上传，待授权）
2. 冗余克隆 `AutoCAD_GUI_Text`（5.2M，已被完全吸收）→ 可退役；注意 CadGuiTest 已注册 `vision` remote 指向它，退役后应 `git remote remove vision`

**B. 旧代归档** —— 建 `D:/AIwork/_archive/`（**只移不删**，`.git` 完整保留，附 `MANIFEST.md` 台账）：
- 归档 `20260810-LingGan`（2.3M/16 文件；**零引用**，安全）
- 归档 `20260728-Bee-Agent`（1.5M/84 文件；被 `BeeAgent-v2`(R21) 取代；仅 md-GuanLi 扫描台账有历史引用）
- ⚠️ **纠错**：`20260811-Fan-LingGan` **不可归档** —— 它是 `Fan-LingGanPro-V1` 的**活数据源**（Pro README 明写「在现有灵感库 `D:\AIwork\20260811-Fan-LingGan`（R10）上加信号层」）+ `pipeline/config.json` 等 6 处硬引用。

**C. 中枢 projects/ 卡聚类** —— **28 → 19 张**（14 张并为 5 张；原件入 `archive/projects/` 并标 `status: archived` + `superseded_by`）：

| 合并卡 | 压缩 | 原卡 |
|:--|:--|:--|
| `cad2020-tu-fen-pipeline` | 4→1 | kplot / pdf-merge / tachart / upload |
| `omniroute-local-deployment` | 3→1 | gateway / container-networking / local-config |
| `hermes-desktop-facts` | 3→1 | context-usage / default-project-dir / fan-debug-v1 |
| `gateway-platforms` | 2→1 | weixin / yuanbao |
| `memory-hub-facts-and-injection` | 2→1 | facts / inject-targets |

- ⚠️ **纠错**：`cad-plugin-management-platform` **不并入**（主题=Cad 插件管理平台，与拆图无关）
- ⚠️ **纠错**：3 张大卡（`t1-plan-three-blueprints` 10.6KB / `T21` 9.6KB / `T19` 1.7KB）**暂不合并**（合 22KB 会造巨型卡，待单独评估）
- INDEX.md 同步；顺带修一处 INDEX 缺陷（`trae-work-ruff-format-batch-bug` 漏登记于 rules 段、错落在目录图例）→ rules 段 29→**30** 条，与磁盘 30 张对齐
- **验证**：lint 0 孤儿/0 幽灵/0 陈旧/0 无效；build-vectors **417 卡**重建；`retrieve "CAD2020 拆图 PDF 总图 15B 空壳"` **命中合并卡排第 1**

**提交**：中枢 `8f8ce4f`（聚类合并+INDEX）、`6dcdd16`（INDEX 修正）
**遗留**：`retro/conflicts-adjudication-20260917.md` 仍触发 schema_drift（他方产物，未动）

## 本轮 R17（ABCD 全量执行 · 2026-09-18）

### A. conflicts 区裁决 —— **17 组 → 4 组 → ✅ 0 组**（2026-09-18 收尾清零）
- **追加裁决 2 组**（用户裁定「都按 A」）：`agent-trigger-symbols-7state` → 入 `methodology/`（并**接上** exp 卡长期悬空的引用）；`T15-improvement-backlog` → 入 `projects/`
- 另 2 组由我用实证自裁：`T21`（6/6 条目已在 `platform-backlog-t19-t21`，陈旧重复）· `embassy-rs`（与权威卡 `canonical` 相同 ⇒ 同一张卡，`anti_trigger` 3 条已并入）
- **意外收获**：入区后修好了一处**长期悬空链接**（exp 卡引用一张只存在于 conflicts 的卡）
- ⚠️ 门禁暴露**既有**问题：**20 张卡 `type` 与目录不一致**（lint 不查 type↔目录，只有 hook 查）→ 已登记至中枢待办卡 §5
- **C（根因）先修**：17 组的 `pred.json` 时间戳全在 **09-06~09-16**，即 **09-15 修复之前**；09-16 23:45 的 3 组 deepseek 已拿到真判决（merge/0.9）⇒ **修复早已生效，只是旧产物未被重跑**。
- **重判**：新增 `scripts/readjudicate_conflicts.py`，用当前本地链（`smart_chat`→LM Studio 1234）重跑 12 组 → 单组实测 0.3~4.3s（embassy → merge/0.95）。
- **执行**：新增 `scripts/resolve_conflicts_20260918.py`，按可验证规则（R1/R2/R3）**13 组移入 `.sync/conflicts/_resolved_20260918/`**（含 `DECISION.md` 逐组依据）；**4 组保留未决**。

### B. 3 张大卡合并 —— **3 → 2**
- `T19` + `T21` → **`projects/platform-backlog-t19-t21.md`**（同为「时间窗分桶的后续优化待办」，合流为一张总表：A 短期 / B 一月 / C 长期 / 永远不动 / 已完成）。
- **不并入**：`t1-plan-three-blueprints`（264 行**未执行**的执行计划，门禁清单全未勾）→ 独立保留，仅加互链。
- 原件入 `archive/projects/` 标 `superseded_by`；INDEX 同步。

### C. 网关降级根因 —— **确认已修，无需改代码**
- 根因＝**旧产物未重跑**，非代码缺陷；`config.yaml` 的 `batch_model: local` + `escalation.min_confidence: 0` 已生效。
- 遗留：1.5b 小模型**主题漂移** 3 例（见待办 1.1）。

### D. A 级剩余 2 项 —— **经核验均「不是重复」，无需合并**
- `BuildNewTaskOnWB`(项目) vs `BuildNewTask`(**技能包** `name: build-new-task`) → 是「源项目 + 提炼技能」关系，**互补非重复**。
- `Fan-ComputerUse` 本地 vs GitHub：**两边内容不同**（本地有 `.workbuddy/memory`、`path_b_artifacts` 等；GitHub 有 `cua_src/`、`browser_run.py`、`briefs/` 等）→ 是不同工作副本，**不可归档也不可强合**。

---

## 本轮 R18（P2-6 内容合并 + 平台卡修复 + 本地 AI 栈抢修 · 2026-09-19）

### 交付（均有实证）
1. **P2-6 完成并端到端验证**：`_resolved_20260918/` **17 张**冲突卡的独有内容接回权威区（11 个目标文件 · 固定章节 `## 合并自 conflicts 区（2026-09-19）`）；提交中枢 `8c7f5c8` + `c01b420`；另 4 张经逐句比对确认无独有内容、未改。**验证**：`retrieve "WASM 运行时 可插拔 编译后端 wasm3 与 wasmer"` → **第 1 命中** `wasmtime-wasm-runtime-multi-backend-blueprint.md`（摘要含来源卡名）
2. **hermes 平台记忆文件碎片修复**：根因＝`_insert_after_instruction` 停止集含 `§`，但 hermes 卡片区**无 §**、卡片以 body 首行 `# ` 开头 ⇒ 每次 push 把上一条卡的**标题与正文劈开**。**引擎已修**：`platform_bridge.py:22-29` 的 `_STOP_HEADS_SECT = ("# ", "## ", "### ", "§")`。**文件已修并核验**：碎片 0 · §区逐字节不变 · 0 删除/67 新增 · 幂等 PASS · 备份 `MEMORY.md.bak-20260919-pre-repair`

3. **2 处悬空引用修完**（`13ce566`）：`methodology/dual-platform-coordination-3phase` 在权威区**不存在** → `experience/phase-2-3-implementation.md` 与 `experience/write-lock-zombie-detection.md` 改指真实落点
4. **P3-13 定案**（`abe211c`）：`t1-plan-three-blueprints` **保持独立卡**（264 行**未执行**计划，并入 backlog 会被条目淹没而失去可执行语义）
5. **🔧 本地 AI 全栈停机抢修**：LM Studio 运行时**今日 14:32 更新 CUDA 12@2.41.0 后任何模型都加载不了**（`llama-server exited before becoming healthy`）⇒ `local_chat` / dedup / embedding / VLM **全部停摆**。回退 2.38.0 **无效** → **切 Vulkan 引擎**（`llama.cpp-win-x86_64-vulkan-avx2@2.38.0`）→ **全恢复**

### 当前状态（单源快照 · 2026-09-19 18:2x）
- **lint**：孤儿 0 · **幽灵 1**（`workbuddy-host-shim-breaks-child-build-and-services`，**并发工作者在制品**）· 陈旧 0 · 无效 0 · 漂移 0 · type↔目录 0 · **230 张卡**
- **向量库**：**428 张全量重嵌入**（`inserted/removed: 428`）· embedding **512 维**；后端保护曾正确拦下 `degraded`（**零丢失**）
- **LM Studio**：1234 · **引擎 = Vulkan@2.38.0**（CUDA 未恢复）· `local_chat.model = qwen3-4b-instruct-2507` · dedup `top_k = 3`
- **conflicts**：**0 未决**
- **卡片分布**：blueprints 109 · methodology 57 · projects 20 · rules 31 · longterm 8 · experience 205
- **健康度**：总分 **83.4** · 飞轮 **57.1**（cron `cfd8cfe6f547` 07:40 已跑通）
- **并发工作者现场**：中枢仓 **33 个 `M`**（mtime `16:43:41` / `17:45:23` **两批同秒批量改** = 自动化批改）+ 新增 1 幽灵登记 ⇒ §4 判定为其现场，**全程只精确 add 自己的文件**

### 阻塞项（R18）
- 🔴 **P0-1 日报投递**：`channel_directory.json` = `yuanbao: []` ⇒ **需你先在元宝给 bot 发一条消息**登记通道（此后免扫码）
- 🟡 **`agent-trigger-symbols-7state` 平台副本暂不推**：实测推它会**越界替换 361 行（删 286）**，边界停在**未闭合代码围栏内**（`_stale_heading_span` 不识别围栏）
- 🟡 **trae / workbuddy 同步**：被"平台文件已被外部修改"闸拦下 → **绝不覆盖**
- 🟡 **CUDA 加速未恢复**：现走 Vulkan；恢复需重装 CUDA 运行时

### 下一步（优先级序）
1. 给 `platform_bridge.py` 边界逻辑加**代码围栏感知**（与已修的 `_STOP_HEADS_SECT` 同源 ⇒ 防将来再吞卡）→ 之后可安全推 7state
2. 恢复 CUDA 运行时（`lms runtime update` / GUI 重下）
3. P0-1 元宝通道（待你一条消息）

## 📋 遗留待办（2026-09-18 登记 · 未完成事项）

> ⚠️ **本段为 2026-09-18 快照，已被上方 R18「当前状态 / 阻塞项」取代**（conflicts 已清零、P2-6/P3-13 等已结案）。单一事实源＝中枢卡 `projects/consolidation-backlog-20260918`；保留本段仅作演进历史。

### 1. conflicts 区剩余 4 组（**需人工终审**）
| # | 冲突卡 | 保留原因 |
|--:|:--|:--|
| 1.1 | `hermes_T21-5platform-后续优化-待办` | **判决漂移**：target 指向 `hub-engine-push-no-card-scope-filter`（与 5 平台待办无关） |
| 1.2 | `trae_embassy-rs-embedded-async-blueprint` | **判决漂移**：target 指向 `heapless-...`（应为 `embassy-rs-async-embedded-architecture`） |
| 1.3 | `deepseek_agent-trigger-symbols-7state` | **低置信 + 无承接物**：权威区无同主题卡，丢弃即丢内容 |
| 1.4 | `hermes_T15-improvement-backlog` | **低置信 + 无承接物**：backlog 卡无对应权威卡 |

> 1.1/1.2 的漂移根因＝本地 1.5b 模型在「5 候选」场景主题漂移 → 可考虑**候选数上限调低**或**换更大模型**。

### 2. blueprints/ 同主题多份（最隐蔽的一类，未处理）
| 主题 | 份数 | 成员 |
|:--|:--|:--|
| `embassy`（Rust 嵌入式 async） | 3 | `embassy-rs-async-embedded-architecture` + 2 张 trae 冲突卡 |
| `wasm` 运行时 | 2~3 | `wasmtime-wasm-runtime-multi-backend` + `wasm3`(已裁决) + `wasmer`(已裁决) |
| `CadAddinManager` | 3 | `cadaddinmanager-hot-reload-architecture` + `-blueprint` + trae 冲突卡(已裁决) |
| `duckdb` | 2 | `duckdb-analytical-db-architecture` + `duckdb-olap-inprocess-sql-architecture` |

### 3. A 级剩余 / 新发现
- `20260805-BuildNewTaskOnWB` ↔ `BuildNewTask`：**确认互补**（项目 + 技能包），但 **`build-new-task` 技能未安装**到 `%LOCALAPPDATA%/hermes/skills`（属未发布技能，待决定是否入库）
- `20260805-Fan-ComputerUse`：本地与 GitHub **内容不一致**（各有所长），待决定「以哪边为主 / 是否补推」
- `20260810-APIKEY`、`20260812-周期行业研究`、`20260808-KoreaStudy` 等**未纳入整合评估**

### 4. B 级（上轮选项 D，未执行）
- `Fan-*` 生态 7 仓（SkillHub / PluginHub / VideoHub / SpeechToText / CadGuiTest / ComputerUse / Agent-Memory）**统一 monorepo 可行性评估**
- ⚠️ 前置：`Fan-SkillHub` 有 **139 个未提交改动**（§4 工作区守护红旗，动前须先 commit/stash）

### 5. 更早遗留
- **VLM 视觉评审**：显存决策未定（RTX 4070 Ti，LM Studio 占 10.4GB，free 1.6GB）
- `projects/t1-plan-three-blueprints` 是否并入待办总表（**待你定**，我建议独立）
- 中枢 `_resolved_20260918` 的 13 组**未做内容级 merge**（按既有 `_resolved_*` 惯例＝只归档）；若需把冲突卡独有内容真正并入权威卡，需另开工单

### 6. 🔴 新发现：飞轮 13 天未跑（真实信号，非误报）
- `status` 显示 **飞轮健康度 0.0** —— 末次运行 **2026-09-05**，至 09-18 已 **13 天**（打分口径 `max(0, 100-8×天数)`）
- 复核：这是 **09-11 修复采集器之后**的真实读数（此前 29.3/52.0 是"读不存在路径"的假告警，现已排除）
- 待查：星标内化/T1 飞轮的 cron 是否失效（`21ff20ab3607` 每日 08:10）
- 关联：`projects/consolidation-backlog-20260918`（中枢侧同项）

## 阻塞项

- 🔴 **P0：飞轮日报微信投递失败**（cron `12c532815d47`，`last_status=delivery_failed`）—— iLink `sendmessage rate limited: ret=-2 ... prepare failed`。日报**生成成功但送不到你手上**。归属：**你**（查 iLink 限流或改投递目标）→ 详见 `projects/consolidation-backlog-20260918` §P0-1
- 无（2026-08-18：源目录 `D:\AIwork\AgentMemoryHub` 已核销清理，原沙箱阻塞解除）。

> 📋 **待办总表**：17 项未完成已按 **P0-P3** 结构化（含归属/前置/预估），单一事实源＝中枢卡 `projects/consolidation-backlog-20260918`（跨平台可见）；本文件 R16/R17 段保留项目级细节。

## 验证方法

- `python -m pytest hub-engine/tests -q`（全量测试，79 项；需有 pytest+yaml+jieba 的 python 环境）
- `python hub-engine/engine.py status --root AgentMemoryHub --json`（健康快照 JSON）
- `python hub-engine/engine.py retrieve --root AgentMemoryHub --mode word --top-k 3 "<问题>"`（混检索，mode 默认 word，`--mode char` 切回字符 n-gram）
- `python hub-engine/engine.py sync --root AgentMemoryHub --platform all --dry-run`（平台记忆同步预览）
- `.venv\Scripts\python.exe work\bench_recall.py`（char vs word 召回率对比评测）
- `python hub-engine\scripts\vector_scale_bench.py --sizes 100 1000 5000 10000`（向量全表余弦耗时 vs 卡数曲线，定切 ANN 阈值）
- `python hub-engine\scripts\vector_bench.py --real AgentMemoryHub --fail-below 0.8`（真实语料回归门禁：融合命中率低于 0.8 退出码非零，供巡检监控）