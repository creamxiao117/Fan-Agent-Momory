# 中枢总控台 Dashboard (V3)

## 概述

自包含 HTML dashboard，展示 AgentMemoryHub 中枢 13 大区实时状态。

## 快速打开

```
file:///C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/docs/dashboard/index-v3.html
```

或起 HTTP server：
```
cd docs/dashboard
python -m http.server 8765
# 然后打开 http://127.0.0.1:8765/index-v3.html
```

## 文件清单

| 文件 | 说明 |
|:--|:--|
| `index-v3.html` | **主 dashboard**（自包含 data）|
| `dashboard-data.json` | 13 大区数据快照 |
| `gen_dashboard_v3.py` | 生成器（从 dashboard-data.json 生成）|
| `slots/` | 5 任务产物（T1 mockup / T2 schema / T3 collect / T4 integration / T5 cron）|

## 13 大区

1. 总体健康 · 2. 5 平台连接 · 3. 6 面板自检 · 4. 知识缺口 · 5. 待人工处理
6. 关键告警 · 7. Cron 任务 · 8. 中枢卡片 · 9. 三仓同步 · 10. commit_ledger
11. 最近 ingest · 12. Hermes Chat（占位）· 13. 立即跑按钮组

## 互动功能

- **5 nav tabs**：总控台 / 飞轮详情 / SkillHub / 平台健康 / Hermes Chat
- **7 cron 立即跑按钮**：每个 cron 一行，点触发（占位，后端 trigger 待接）
- **Hermes Chat 输入框**：Enter 发送（占位 UI）

## 已知问题（T24 经验）

- iframe 在 file:// 协议下不可用 → 已用占位卡替代
- HTTP server 端口冲突 → 用 lockfile 跟踪 PID
- Hermes chat 后端 trigger 待接入

## 关联

- `experience/T22-3agent-parallel-dispatch-real-test.md`
- `experience/T23-遇到问题先查中枢再下结论.md`
- `experience/T24-http-server-iframe-enter-bind-pitfalls.md`