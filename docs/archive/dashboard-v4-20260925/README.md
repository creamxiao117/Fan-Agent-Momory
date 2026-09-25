# 归档：仪表盘 v4 路线（2026-09-25 审计重构候选 B）

> 上游：`docs/compose/reports/2026-09-25-project-audit.md` §5 候选项 **B（仪表盘单一化）**。

## 为什么归档

清理前仓里并存**三条**仪表盘路线，只有一条仍在跑：

| 路线 | 形态 | 现状（2026-09-25 取证） | 结论 |
|:--|:--|:--|:--|
| **(c) 巡检产物** | `AgentMemoryHub/system/run/{platform-dashboard.md,daily-6panel.json}` + `retro/snapshot-*.json` | **每天由巡检/夜间链路刷新**（当日 mtime） | ✅ **保留：唯一"常跑"视图** |
| (a) 根级 HTML | `hub-health.html` / `flywheel-timeline.html` / `memory-hub-flywheel-v2.html` | 生成器（`hub-engine/scripts/hub_health.py`、`flywheel_runlog.py`）仍 tracked；HTML 最后生成 **2026-08-29**（手动可再生） | ✅ 保留（手动视图） |
| (b) v4 路线 | `docs/dashboard/**`（含 T1–T5 原型 slots）+ `hub-engine/scripts/hub_dashboard_{collect,server}.py` | **无任何调度**（`Get-ScheduledTask` 无匹配）、仓外无调用（mcp.json / scheduled_tasks.json 无匹配）、除自述外无引用 | 📦 **本次归档** |

判据：谁都没在跑、没人调它，却要维护 `collect 1214 行 + server 692 行 + 32 个原型文件`
—— 属于"两条死路线拖累一条活路线"。

## 归档内容

- `docs/` ← 原 `docs/dashboard/`（含 `README-v4.md`、`index-v4.html`、`slots/T1..T5` 原型、`dashboard-data.json`、`gen_dashboard_v3.py`）
- `hub_dashboard_collect.py`（50,774 B）← 原 `hub-engine/scripts/`
- `hub_dashboard_server.py`（29,951 B）← 原 `hub-engine/scripts/`

`docs/**` 在 `.ruff.toml` 的 `extend-exclude` 内 ⇒ 归档脚本不再参与 lint（其既有的 E501/C901 债随之离开门禁基线）。

## 如何恢复或"复活"

```powershell
# 恢复（历史齐全，直接挪回即可）
git mv docs/archive/dashboard-v4-20260925/docs docs/dashboard
git mv docs/archive/dashboard-v4-20260925/hub_dashboard_collect.py hub-engine/scripts/
git mv docs/archive/dashboard-v4-20260925/hub_dashboard_server.py hub-engine/scripts/
# 记得同步 hub-engine/pyproject.toml 的 per-file-ignores（E501/C901 基线里原含 collect）
```

若将来真要复活它，请同时补两件当时缺的东西：**① 一个调度（计划任务/巡检步骤）② 一个入口文档**，
否则它会再次变成"没人跑的第三套"。
