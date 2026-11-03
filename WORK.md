# WORK.md（当前状态 · 唯一来源）

更新于：2026-11-02 · 架构重构（2026-10-02 两计划）主体已落地：判据 **C1–C7 通过，C8 已重新定义**

> 过程明细 `docs/superpowers/retro/work-history.md`｜审计 `docs/compose/reports/2026-09-25-project-audit.md`｜**重构计划 `docs/compose/plans/2026-10-02-hub-architecture-refactor.md`**｜**pi 计划 `...-pi-hub-bridge.md`**｜逐轮日志 `RUNLOG.md`（最新在前）

## 当前状态（2026-11-02 实测）

- 卡片 **616**（blueprints 212 / experience 286 / methodology 64 / projects 23 / rules 23 / longterm 8）；lint **全 0**（orphan/ghost/hook/stale/invalid/schema_drift）
- 巡检 **8 步 exit 0**（lint / render_check / audit / recall / reconcile / secret_sentry / encoding / tests）；产物恰两件 `retro/snapshot-*.json` + `retro/daily-*.md`；健康 **91.9/100**（card 100 / skill 100 / gate 100 / flywheel 85.7 / **llm 60** ← LM Studio 2060 ms，唯一 info 告警）
- 测试 **841 用例已收集**；**门禁 9→3 且 scope-gated**（`common/gate_scope.py`：`code`/`text`/`l0`，按 staged 触发）⇒「他人未提交改动阻断提交」缺陷已消除，`--no-verify` 合法用途归零
- **grade 覆盖 616/616 = 100%**（iron 7 / proven 135 / domain 190 / pitfall 42 / task 242）；**L1 由 `grade=iron` 派生**、`tiers` 归型；bootstrap 按 grade 三段分层；**正交轴 `evidence`**（t1 92 · measured 57，其余缺失即 none）
- 平台元数据**单源**（`hub.config.yaml`；旧双源文件已删）；能力账本 `system/capabilities.json|md` + `scripts/INVENTORY.json`（**114 条**：keep 81 · manual-cli 33 · unused 0）；`capability_reconcile` 已挂巡检第 4 步（含**降级路线图**）
- **pi 接入**：MCP 已通（本会话 7 工具）· `agent/mcp.json` → `.venv` · `agent/AGENTS.md` **顶部托管块**已注入 · 扩展 `memory-hub.ts`（`/hub` `/hub-write` `/hub-cap` `/hub-on` `/hub-off`；注入走 `sections["hub-context"]`）· 回写落 `.sync/drafts/pi_draft/`（**人工确认制**）· 降级账本 `<agent-dir>/hub-bridge.log` · MCP ui 资源**按客户端声明**（agent 侧零弹窗）+ WorkBuddy 侧为**人类真卡片**
- 定时链：07:30 巡检 / 00:35 夜间合并 / 06:00 密钥哨兵 / 09:00 临时目录清理 + Hermes 5 任务（晨报→提升→star-distill+T1→周六评测）；**微信通道已停用**
## 活跃待办（按优先级）

| # | 任务 | 判据 / 做法 |
| -- | --- | -- |
| **A1–A3** | ✅ **已达成**：grade 616/616 + `tier`/`l1_tier` 退役 · `rules/` 23→13（迁区零损伤）· **C8 重新定义**（`unused`=0 · `duplicate`=0 · 在役证据覆盖 93.9% · 模块数棘轮 114，`inventory.py::c8_violations` 自动判定） | 明细见 RUNLOG R23–R27 |
| **A4** | ✅ **重跑 + 口径修正后成立**：判据①**正面**（后窗口 **37 天** 全 0）、②**正面**（产出率 **66%**、重复率 **34%**）；此前「3.2%」是**指标 bug**（漏计 227 条真实入区）⇒「未触及根因」是**误判**。W40–41 低谷 = **模型漏写 `confidence` ⇒ 静默降级 review**（10-10/10-12 已修）⇒ 本轮补「退化可见」：`degraded` 标记 + 判决台账 + `dedup_stats` 进巡检第 4 步 | 维持 |
| **A5–A7** | ✅ **已达成**：`/hub-write`（预览+确认制 → CLI `draft-write`）+ 检索/失败可见 · 预算帽（棘轮 + 60% 降级目标 + 降级路线图）· 盘点卡去数字化 | 见 RUNLOG R26 || **A8** | ✅ **方案 A 全落地**：① 字段 `evidence`（none/measured/t1，ingest 只给新卡填）② **检索侧**：摘录长度按 evidence 加成（task+measured=240≈proven）+ 命中项透出 evidence + 注入块标 `[measured]` ③ **存量回填 149 张**（v5 判据 + 18 张抽样全成立；t1 92 · measured 57；其余不写=缺失即 none） | 报告 `docs/compose/reports/2026-11-02-evidence-axis.md` |
| **A9** | ✅ **已判定**：用户确认 **workbuddy 最近没使用** ⇒ 原「近 30 天用过 + 近 7 天零检索」告警属**噪音** ⇒ 收紧为「**近 14 天**用过 + 近 7 天零检索」；实测不再被报 | 维持 |### T1 判据（重跑 + 口径修正）

1. 门禁：后窗口 **≥10 天**且 `invalid/orphans/ghosts` 全 0 → 正面（**达成**：37/37 天全 0）
2. 产出：周产出率 **≥40%** 且重复率 **≤60%** → 流入恢复（**达成**：**66%** / **34%**）
3. 反面：任一维度复现非零 / 产出率仍 **≤11%** → 未触及根因（**不命中**）

> 两处口径修正（已留档 `docs/compose/metrics/2026-11-02-t1-rerun.md`）：①「后窗口」原**硬编码 2 天** ⇒ 判据①结构上不可能满足；②入区统计原只认「自动入区」一种字样 ⇒ **漏计 227 条真实入区**（产出率被算成 3%）⇒ 上一轮「未触及根因」是**指标 bug 造成的误判**。

## 架构重构判据现状（C1–C8）

| 判据 | 现状 |
| -- | -- |
| C1 分型单源 | ✅ `task_tier.py` 单表 |
| C2 平台登记单源 | ✅ `hub.config.yaml` |
| C3 尺子双把 | ✅ `INVENTORY.json` + `capabilities.json`（`--check` 可跑） |
| C4 门禁瘦身 | ✅ 3 道 scope-gated |
| C5 流水线瘦身 | ✅ 8 步 + 两件产物 |
| C6 等级轴 | ✅ grade **100%**（616/616）；每型 iron ≤3（code 3 / hub 3 / sync 2）；L1 由 `grade=iron` 派生（`tiers` 归型）；抽样复核 37 张（改判 3 张） |
| C7 账本对账 | ✅ 巡检 pass（差异 0）；帽已定：逐平台棘轮 + 60% 降级目标 + 降级路线图 |
| C8 瘦身结果 | ✅ **已重新定义**（原「≤75」按证据不可达）：`unused`=0 · `duplicate`=0 · 在役证据覆盖 **93.9%**（≥90%）· 模块数**棘轮 114**（新增须等量退役）——全部由 `inventory.py::c8_violations` 自动判定 |

## 门禁

- **提交时**（外层 + 中枢两钩子，逻辑同一份 `hub-engine/scripts/gate_runner.py`）：`code` → ruff×2 · `text` → 编码+markdownlint · `l0` → startup_budget + render_index --check（**按 staged 触发**）；退出码 0/1/2/3
- **每日** 07:30 巡检 8 步 · 00:35 夜间合并 · 06:00 密钥哨兵 · 09:00 临时目录清理
- **手动** `python -m scripts.recall_regression`（58 条金标准，退出码 2 = 未达 90%）；`python -m scripts.inventory --check`；`python -m scripts.capability_reconcile --root ../AgentMemoryHub`
- 验收：`.venv\Scripts\python.exe -m pytest` → **841 用例**；`ruff check` 全绿

## 禁止 / 注意

- **勿执行** `scripts/merge-methodology.py` / `deduplicate-experience.py`（有拒绝护栏）
- **解释器必须 `.venv\Scripts\python.exe`**（系统 python 缺 jieba → 检索测试静默跳过＝假绿）
- 中枢卡提交须 `git -C AgentMemoryHub`；跨仓改动**两仓提交相邻、message 互引**
- **迁卡 / 改 slug 后必须 `engine.py build-vectors` 重建**：向量库按**路径**索引，路径一变旧行即失效（召回静默掉 7 个点）
- **改 `hub.config.yaml` 后必须 `capability_scan --write`**：否则巡检 reconcile 步报「账本与实测态不一致」
- `INDEX*.md` 是渲染产物，禁手改；改卡后 `python -m scripts.render_index --write`
- **提交门禁自改期间不得 `--no-verify`**；门禁故障当场修
- **状态源纪律**：WORK.md = 唯一状态；每轮改动在 RUNLOG.md 追加（最新在前）；**别新建笔记文件**
- 外层超时必须 > 内层（pytest 外 420s / 内 180s）；归档卡须同步检查引用它的夹具（期望卡名会漂移）
- GitHub push 走 **HTTP/1.1**（`git -c http.version=HTTP/1.1 push`）：本机 HTTP/2 协商被中间设备打断
