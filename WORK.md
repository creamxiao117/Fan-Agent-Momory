# WORK.md（当前状态 · 唯一来源）

更新于：2026-08-17（context-engineering-v1 迁移 R4b）

## 当前 MVP（已完成）

- **中枢骨架**：`D:\AIwork\AgentMemoryHub`（Obsidian 库：rules/libs/experience/projects/retro/archive + .sync + INDEX.md），已 Git 初始化（5 提交，终态 4264e3f）。
- **hub-engine**（本仓库）：同步器（单一写入者/暂存/去重/确认/Git）、混合检索、复盘提炼、整理归档、Lint 健康检查、omniroute 问答。
- **CLI**：`engine.py` 子命令 `retrieve/ingest/confirm/distill/tidy/lint/chat/status`。
- **测试**：47 项通过（`cd hub-engine && python -m pytest -q`）。
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
  - Ruff 0 错误（含 format），`hub-engine/` 29 文件已格式化
  - yamllint 已安装（项目 `.venv`），2 个 YAML 文件通过（仅 warning 缺 `---` 文档头）
  - Markdown lint 通过（`.markdownlint.json` 放松行宽/表格样式等噪音规则，`.markdownlintignore` 排除归档文档）
  - pytest 47 项通过
  - JSON/TOML 语法检查通过
- 配置新增：`.ruff.toml`（排除 docs/ 归档）、`.markdownlint.json`、`.markdownlintignore`、`.gitignore` 补 `.tools/`/`work/`/`.venv/`

## 下一步候选

1. code 平台本体接入生效（目录已存在，指令已注入，待平台连接）。
2. 对真实中枢执行 `engine.py status --json` 快照并纳入自动化巡检。**（已完成，一次实跑正常）**

## 阻塞项

- code 平台目录 `D:/AIwork/code-memory` 为注入自动创建，平台本体尚未接入，指令暂未生效。

## 验证方法

- `cd hub-engine && python -m pytest -q`（全量测试，47 项）
- `python hub-engine/engine.py status --root D:\AIwork\AgentMemoryHub --json`（健康快照 JSON）
- `python hub-engine/engine.py status --root D:\AIwork\AgentMemoryHub`（健康快照）
