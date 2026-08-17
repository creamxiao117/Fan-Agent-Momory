# 项目卡：统一记忆中枢 · 协作约定

> 范围：**项目专属**（本项目 local）｜来源：统一记忆中枢项目 R1/R2/R3（2026-08-17）

## 骨架文件职责（本项目既定）

| 文件 | 职责 |
| --- | --- |
| AGENTS.md | 唯一启动入口：启动顺序 + 事实来源映射 + 执行前必读 |
| CHARTER.md | 总目标 / 三层架构 / 第一版边界 / 关键约束 |
| WORK.md | 当前状态唯一来源（MVP / 本轮 / 下一步 / 阻塞 / 验证） |
| RUNLOG.md | 只追加迭代日志，最新在前 |
| briefs/ | 每轮一份简报：加什么 / 为什么 / 不加什么 / 怎么验证 |
| project-visual-guide.md | 一页流程图 + 脑图 + 决策点/风险表 |

## 引擎约定

- CLI 统一入口 `hub-engine/engine.py`，子命令：retrieve/ingest/confirm/distill/tidy/lint/chat/status。
- 新子命令必须配测试（pytest，pythonpath=`.`），全量须通过。
- 注入目标（幂等）：trae → `C:/Users/Fan-SJSS/.trae-cn/memory/user_profile.md`；
  code → `D:/AIwork/code-memory/CLAUDE.md`（已预备，待平台目录生效）。
- 中枢唯一事实源 `D:\AIwork\AgentMemoryHub`；单写者锁 `.sync/locks/writer.lock`。

## 不可违背（用户既定规则）

- 先查统一记忆中枢（INDEX.md + rules/experience），命中再执行。
- 不确定交回用户，不得臆测/捏造历史经验。
- 修改 DLL 后必须递增版本号（防 AutoCAD 锁文件）。
- 代码注释尽量中文；lint 规范。

## 迭代门

每轮结束用 4 字段（收益/时间/Token/阻塞）判断：继续 / 收尾 / 需人工。
