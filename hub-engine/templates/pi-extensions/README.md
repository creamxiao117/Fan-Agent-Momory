# pi 扩展模板（仓内即唯一源）

## 为什么有这一层

pi 的扩展必须放在 `<agent-dir>/extensions/` 才能生效，但那个目录**不在版本控制内**
（属 pi 的用户配置）。若只在那边维护，扩展一旦被删/换机就永久丢失。

按本机既有的「开发副本 / 部署副本」纪律（见 `agent/AGENTS.md §2.2` 的 LISP 例子）：

| 角色 | 位置 | 说明 |
|---|---|---|
| **唯一源（开发副本）** | `hub-engine/templates/pi-extensions/*.ts`（本目录，入 git） | 改扩展**只改这里** |
| 部署副本 | `<PI_CODING_AGENT_DIR>/extensions/*.ts` | 由下面的命令安装，勿手改 |

## 安装 / 更新

```powershell
# 1) 部署（覆盖式；扩展是纯文本，无需转换编码）
Copy-Item `
  "hub-engine/templates/pi-extensions/memory-hub.ts" `
  "$env:PI_CODING_AGENT_DIR\extensions\memory-hub.ts" -Force

# 2) 生效
#    在 pi 里执行 /reload（扩展运行时会重建）
```

## 验证（无需模型调用）

```powershell
# 用 pi 自带的 jiti 加载，检查语法 + 纯函数行为
node hub-engine/templates/pi-extensions/smoke.cjs
```

## 扩展清单

| 文件 | 作用 |
|---|---|
| `memory-hub.ts` | 记忆中枢自动检索：首轮 / resume / 话题漂移三点预取，注入 `systemPromptOptions.sections["hub-context"]` |

## 硬约束（改扩展时不得违反）

1. **不硬编码中枢知识**：分型、检索子区、卡名一律由中枢侧 `engine.py tier-bootstrap`
   计算（与 MCP `hub_bootstrap` 共用同一 handler）。扩展里出现区名/卡名 = 第三套口径。
2. **唯一注入点** = `systemPromptOptions.sections`（Pi 会 diff 后追加增量 ⇒ prompt cache 友好）。
   不替换 `systemPrompt`、不注册 `context_with_system`。
3. **失败静默降级**：超时/非 0 退出/JSON 坏 → 不注入、不抛给模型、状态栏提示。
4. **不要把预取放在用户等待的关键路径**：中枢检索**进程级冷启动实测 ~5s**
   （向量后端加载；证据见中枢 `experience/pi-prefetch-process-cold-start.md`），
   故在 `session_start` 后台发起。
