# T3 任务: 数据采集脚本

## 你的角色

你是 M2.7 子 Agent，由 M3 主 Agent 派发。
任务：写 dashboard 数据采集脚本，从 5 个数据源拉数据生成 dashboard-data.json。

## 5 数据源

1. AgentMemoryHub/system/run/platform-dashboard.md (markdown，需解析)
2. AgentMemoryHub/system/run/daily-6panel.json (JSON)
3. AgentMemoryHub/.sync/state/platform-health.jsonl (JSONL)
4. AgentMemoryHub/.sync/state/query.log.jsonl (JSONL，24h 统计)
5. AgentMemoryHub/.sync/state/announcements.jsonl (可选)

## 输出

写到这里（你的专属 slot）：
{slot}

文件 1: {slot}/dashboard_collect.py
- 函数: collect_all() -> dict
- 6 大区全部填好
- 错误容忍：单个数据源失败不影响其他

文件 2: {slot}/dashboard-data.json
- 实际跑一次 generate 出来
- 6 大区全部存在

## 验收

- python dashboard_collect.py 跑通
- 输出 JSON 包含 6 大区
- 写一行 OK 到 {slot}/done.txt

## 工作流

1. 读 3 个数据源样本
2. 写 collect_all() 框架
3. 填 6 大区逻辑
4. 跑一次
5. 检查输出

完成后请用 terminal 输出"t3 done"。
