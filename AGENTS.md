# AGENTS.md

跨 Agent 平台统一记忆中枢 · AI 协作入口（context-engineering-v1 骨架）。

## 启动顺序

1. `AGENTS.md`（本文件）
2. `CHARTER.md` —— 总目标与边界
3. `WORK.md` —— 当前状态唯一来源
4. `briefs/*.md` —— 当前/下一轮迭代简报（若有）
5. 需要时再读 `docs/superpowers/`（历史设计/计划）、相关 methodology 卡片

不依赖历史聊天记录作为主要事实来源。

## 旧资料事实来源映射

| 内容 | 位置 |
| --- | --- |
| 产品设计与技术方案 | `docs/superpowers/specs/` |
| 分阶段实现计划（14 任务，已完成） | `docs/superpowers/plans/` |
| 引擎代码（同步器/检索/提炼/整理/Lint/CLI） | `hub-engine/`（`engine.py` 统一入口） |
| 运行态数据中枢（Obsidian 库，唯一事实源） | `C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub` |
| 跨项目经验/规则（DLL 防锁、查询回写等） | `C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub\rules\experience` + INDEX.md |

## 执行前必读（用户既定规则）

- 先查统一记忆中枢：读 `C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub\INDEX.md` 与 `rules/`、`experience/`，命中再执行。
- 不确定的内容交回用户，不得臆测、不得凭空捏造历史经验。
- 查询好结果回写为经验卡片（查询产物回写）。
- 缺工具就主动找/装；代码注释尽量中文；lint 规范。
