# @version V1.0 / 2026-09-10 / Hermes / 中枢看板 v4 运行说明

## 启动（一条命令）

```bash
cd <repo>
python hub-engine/scripts/hub_dashboard_server.py
# 打开 http://127.0.0.1:8899
```

默认自动探测 AgentMemoryHub；也可显式指定：
```bash
python hub-engine/scripts/hub_dashboard_server.py --hub-root <AgentMemoryHub 路径> --port 8899
```

## 为什么必须走 HTTP 而不是双击 HTML

旧看板（index-v3.html）用 `file://` 打开，浏览器把 origin 视为 `null`，
**会拦截页面到 127.0.0.1 的所有请求**（CORS）。这导致：
- Hermes Chat 三条链路全挂
- 所有按钮只能做假动作

v4 由本地后端托管页面，同源请求，CORS 问题不存在。

## 文件职责（一图流）

| 文件 | 职责 |
|:--|:--|
| `hub-engine/scripts/hub_dashboard_collect.py` | 真实数据采集（唯一数据来源，禁止硬编码） |
| `hub-engine/scripts/hub_dashboard_server.py` | 本地后端（静态托管 + API + 真交互） |
| `docs/dashboard/index-v4.html` | 看板 UI（自包含，零 CDN，纯 SVG/div 图表） |
| `docs/dashboard/verify_v4.py` | 端到端验证（16 项，改完必跑） |
| `hub-engine/scripts/vlook.py` | 截图视觉检查（本机 VL 模型驱动） |

## 数据源对照（每个字段都能指到真实文件）

| 指标 | 来源 |
|:--|:--|
| 卡片数 / 类型 / 状态 | 扫描 `AgentMemoryHub/{rules,methodology,experience,...}/*.md` 的 YAML frontmatter |
| 向量库覆盖 | `AgentMemoryHub/.sync/vector.db` |
| 写锁 | `AgentMemoryHub/.sync/locks/writer.lock` |
| 定时任务 / 执行次数 / 故障 | `%LOCALAPPDATA%/hermes/cron/jobs.json` + `executions.db` |
| 技能被引用次数 | 词边界匹配技能名于中枢 359 张卡正文 |
| 后端服务在线 | TCP 探测 1234 / 20128 / 8765 |
| 检索日志 | `AgentMemoryHub/.sync/state/query.log.jsonl` |
| Git 同步 | 对主仓与中枢仓跑 `git status/rev-list` |

## 改完必须验证（规则 agent-modify-must-view-page）

```bash
python docs/dashboard/verify_v4.py --url http://127.0.0.1:8899/ --shots <截图目录>
python hub-engine/scripts/vlook.py <截图> --backend lmstudio   # 真视觉看一眼
```

注意：`paddleocr-vl` 认数字不准（实测把 0 读成 8、40 读成 48）。
**数字以 DOM/API 为准，视觉只用于判断布局与内容是否存在。**

## 已知未做（下一轮）

- 卡片状态里有 `unknown 5`（无 frontmatter 的卡）——应回写 frontmatter
- `检测到 10 个定时任务故障未处理` 是中枢侧待办，不是看板问题
- 趋势图（历史曲线）尚未做，目前只有当前值 + 分布
