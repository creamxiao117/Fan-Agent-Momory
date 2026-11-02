# WORK.md（当前状态 · 唯一来源）

更新于：2026-11-02 · **本轮刷新：原 10-01 版已脱节 3 周（实际提交已到 11-02），按现场取证重写**；架构重构（2026-10-02 两计划）**Wave 1–4 主体已落地**，判据 **C1–C5、C7 通过，C6/C8 未达标**

> 过程明细 `docs/superpowers/retro/work-history.md`｜审计 `docs/compose/reports/2026-09-25-project-audit.md`｜**重构计划 `docs/compose/plans/2026-10-02-hub-architecture-refactor.md`**｜**pi 计划 `docs/compose/plans/2026-10-02-pi-hub-bridge.md`**｜逐轮日志 `RUNLOG.md`（最新在前）

## 当前状态（2026-11-02 实测）

- 卡片 **616**（blueprints 212 / experience 286 / methodology 64 / projects 23 / rules 23 / longterm 8）；lint **全 0**（orphan/ghost/hook/stale/invalid/schema_drift）
- 巡检 **8 步 exit 0**（lint / render_check / audit / recall / reconcile / secret_sentry / encoding / tests）；产物恰两件 `retro/snapshot-*.json` + `retro/daily-*.md`；健康 **91.9/100**（card 100 / skill 100 / gate 100 / flywheel 85.7 / **llm 60** ← LM Studio 2060 ms，唯一 info 告警）
- 测试 **827 用例已收集**；**门禁 9→3 且 scope-gated**（`common/gate_scope.py`：`code`/`text`/`l0`，按 staged 触发）⇒「他人未提交改动阻断提交」缺陷已消除，`--no-verify` 合法用途归零
- **grade 覆盖 616/616 = 100%**（task 242 / domain 190 / proven 135 / pitfall 42 / iron 7）；枚举校验已生效（`VALID_GRADES`）；**L1 集合已改由 `grade=iron` 派生**，归属由 `tiers` 声明（`l1_tier`/`tier` 已退役）；bootstrap 已按 grade 三段分层（铁律 / 已验证方案 / 相关经验）
- 平台元数据**单源**（`hub.config.yaml`，`system/platforms.yaml` 已删）；能力账本 `system/capabilities.json|md` + `scripts/INVENTORY.json`（**113 条**：keep 73 / manual-cli 38 / duplicate 2）；`capability_reconcile` 已挂巡检第 4 步
- **pi 接入**：MCP 已通（本会话 7 工具）· `agent/mcp.json` → `.venv` · `agent/AGENTS.md` **顶部托管块**已注入 · 扩展 `agent/extensions/memory-hub.ts`（`/hub` `/hub-cap list|install|verify|remove|residue` `/hub-on` `/hub-off`；注入走 `sections["hub-context"]` ← `engine.py tier-bootstrap`）· pi 已登记 · 回写通道 `.sync/drafts/pi_draft/` 定期 ingest
- 定时链：07:30 巡检 / 00:35 夜间合并 / 06:00 密钥哨兵 / 09:00 临时目录清理 + Hermes 5 任务（07:30 晨报 → 07:40 提升 → 07:50 star-distill+T1 → 周六评测/SkillHub）；**微信通道已停用**

## 活跃待办（按优先级）

| # | 任务 | 判据 / 做法 |
| -- | --- | -- |
| **A1** | ✅ **已达成**（实测 616/616 = 100%；此前“63.1%”是前 15 行文本窗口的测量假象）；本轮补：旧 `tier` 字段退役 + `l1_tier` → `tiers`（零漂移） | 维持 |
| **A2** | **`rules/` 23 → ≤13** | 重构 Task 8/14：同族卡合并；每张须绑门禁，否则降级 |
| **A3** | **模块瘦身 113 → ≤75** | Task 9 + 38 个 `manual-cli` 裁定（保留者 / 归档者 / 取证） |
| **A4** | **T1 重跑（逾期）** | `python -m scripts.rule_following_timeseries`；判据见下。`docs/compose/metrics/` 仍只有 09-23 基线 |
| **A5** | **pi 计划 P2/P3 收口** | Task 9 `/hub-write`（人工确认制）+ Task 10 审计可见 + Task 11/12 回归沉淀 |
| **A6** | **能力账本预算帽** | Task 18：`discovery_cost` 已实测回填，**预算帽未定**；账本 vs 实测差异须清零 |
| **A7** | **腐烂文档处置** | Task 11：`methodology/agent-tool-inventory.md` 仍是手写快照 → 改为指向 `capabilities.md` |

### T1 重跑判据（可证伪）

1. 门禁：后窗口 **≥10 天**且 `invalid/orphans/ghosts` 全 0 → 正面
2. 产出：周产出率 **≥40%** 且重复率 **≤60%** → 流入恢复
3. 反面：任一维度复现非零 / 产出率仍 **≤11%** → **未触及根因，须重新诊断**

## 架构重构判据现状（C1–C8）

| 判据 | 现状 |
| -- | -- |
| C1 分型单源 | ✅ `task_tier.py` 单表 |
| C2 平台登记单源 | ✅ `hub.config.yaml` |
| C3 尺子双把 | ✅ `INVENTORY.json` + `capabilities.json`（`--check` 可跑） |
| C4 门禁瘦身 | ✅ 3 道 scope-gated |
| C5 流水线瘦身 | ✅ 8 步 + 两件产物 |
| C6 等级轴 | 🔶 grade 63.1%（目标 100%）；`rules/` 23（目标 ≤13） |
| C7 账本对账 | ✅ 巡检 pass（差异 0）；🔶 `discovery_cost` 预算帽未定 |
| C8 瘦身结果 | 🔶 模块 113（目标 ≤75）；`_retired` 已清空 |

## 门禁（都在跑，不只是"代码里有"）

- **提交时**（外层 + 中枢两钩子，逻辑同一份 `hub-engine/scripts/gate_runner.py`）：`code` → ruff×2 · `text` → 编码+markdownlint · `l0` → startup_budget + render_index --check（**按 staged 触发**）；退出码 0/1/2/3
- **每日** 07:30 巡检 8 步 · 00:35 夜间合并 · 06:00 密钥哨兵 · 09:00 临时目录清理
- **手动** `python -m scripts.recall_regression`（58 条金标准，退出码 2 = 未达 90%）；`python -m scripts.inventory --check`；`python -m scripts.capability_reconcile --root ../AgentMemoryHub`
- 验收：`.venv\Scripts\python.exe -m pytest` → **827 用例**

## 禁止 / 注意

- **勿执行** `scripts/merge-methodology.py`、`scripts/deduplicate-experience.py`（已加拒绝护栏）
- **解释器必须 `.venv\Scripts\python.exe`**（系统 python 缺 jieba → 9 个检索测试静默跳过＝假绿）
- 中枢卡提交须 `git -C AgentMemoryHub`（嵌套 git）；跨仓改动**两仓提交相邻、message 互引**
- **本文件 ≤5000 字符**（`startup_budget` 看守）；超了先砍内容再加，别超帽硬塞
- `INDEX*.md` 是渲染产物，禁手改；改卡后 `python -m scripts.render_index --write`
- **提交门禁自改期间不得 `--no-verify`**；门禁故障当场修
- **状态源纪律**：WORK.md = 唯一当前状态；每轮改动在 RUNLOG.md 追加（最新在前）；**不要新建笔记文件**
- 外层超时必须 > 内层（pytest 外 420s / 内 180s）
- 归档卡片须同步检查引用它的夹具（期望卡名会随生命周期漂移）
- GitHub push 走 **HTTP/1.1**（`git -c http.version=HTTP/1.1 push`）：本机 HTTP/2 协商被中间设备打断
