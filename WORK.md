# WORK.md（当前状态 · 唯一来源）

更新于：2026-08-19（R8：blueprint 蓝图体系 + github-star-distill 两个仓库内化）

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

## 阻塞项

- 无（2026-08-18：源目录 `D:\AIwork\AgentMemoryHub` 已核销清理，原沙箱阻塞解除）。

## 验证方法

- `python -m pytest hub-engine/tests -q`（全量测试，79 项；需有 pytest+yaml+jieba 的 python 环境）
- `python hub-engine/engine.py status --root AgentMemoryHub --json`（健康快照 JSON）
- `python hub-engine/engine.py retrieve --root AgentMemoryHub --mode word --top-k 3 "<问题>"`（混检索，mode 默认 word，`--mode char` 切回字符 n-gram）
- `python hub-engine/engine.py sync --root AgentMemoryHub --platform all --dry-run`（平台记忆同步预览）
- `.venv\Scripts\python.exe work\bench_recall.py`（char vs word 召回率对比评测）
- `python hub-engine\scripts\vector_scale_bench.py --sizes 100 1000 5000 10000`（向量全表余弦耗时 vs 卡数曲线，定切 ANN 阈值）
- `python hub-engine\scripts\vector_bench.py --real AgentMemoryHub --fail-below 0.8`（真实语料回归门禁：融合命中率低于 0.8 退出码非零，供巡检监控）
