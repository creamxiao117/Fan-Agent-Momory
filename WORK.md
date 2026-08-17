# WORK.md（当前状态 · 唯一来源）

更新于：2026-08-17（R5：中枢迁移 + 每日巡检 + n-gram 调优）

## 当前 MVP（已完成）

- **中枢骨架**：`AgentMemoryHub/`（本仓库内，已从 `D:\AIwork\AgentMemoryHub` 迁移，规避沙箱权限）。Obsidian 库：rules/libs/experience/projects/retro/archive + .sync + INDEX.md，已 Git 初始化（6 提交）。
- **hub-engine**（本仓库）：同步器（单一写入者/暂存/去重/确认/Git）、混合检索、复盘提炼、整理归档、Lint 健康检查、omniroute 问答。
- **CLI**：`engine.py` 子命令 `retrieve/ingest/confirm/distill/tidy/lint/chat/status`。
- **测试**：49 项通过。
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

## 下一步候选

1. code 平台本体接入生效（目录已存在，指令已注入，待平台连接）。
2. 定期重跑 `work/bench_recall.py` 复核召回率（语料增长后 n 值可能需再调）。

## 阻塞项

- code 平台目录 `D:/AIwork/code-memory` 为注入自动创建，平台本体尚未接入，指令暂未生效。
- 源目录 `D:\AIwork\AgentMemoryHub` 受沙箱保护无法删除（如需清理，在 TRAE 权限设置放行或手动删除）。

## 验证方法

- `python -m pytest hub-engine/tests -q`（全量测试，49 项；需有 pytest+yaml 的 python 环境）
- `python hub-engine/engine.py status --root AgentMemoryHub --json`（健康快照 JSON）
- `.venv\Scripts\python.exe hub-engine/engine.py retrieve --root AgentMemoryHub --n 2 --top-k 3 "<问题>"`（混检索，n 可调）
