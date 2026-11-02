# hub-engine 模块职责重复裁定表（2026-11-02）

> 计划来源：架构重构 **M0/Task 4–5**（`docs/compose/plans/2026-10-02-hub-architecture-refactor.md`）
> 工具口径：`python -m scripts.inventory --candidates` / `--write`（台账 `AgentMemoryHub/scripts/INVENTORY.json`）
> 原则：**保留需举证**（D6）·「计数是结果，不是目标」（`experience/pi-card-merge-hurts-recall.md`）

## 结论摘要

| 项 | 值 |
| -- | -- |
| 台账模块总数 | **113**（keep 80 · manual-cli 33 · duplicate 0 · unused 0） |
| 本轮物理删除 | **0** |
| 撤销的退役声明 | **1 条**（含 2 个模块，见下） |
| 尺子增强 | `last_run`（在役时间证据）实装 + `refs_scheduled`（编排引用）新增 |

## 簇 1：INDEX 一致性（唯一声明簇）

| 项 | 内容 |
| -- | -- |
| 保留者 | `scripts/render_index` |
| 归档者 | **无**（原声明的 `index_consistency` / `audit_index` 退役**已撤销**） |
| 原判据 | 「INDEX 一致性的唯一实现 = 渲染器 `--check`；另两个自称同一职责（均带『一致性』）」 |
| 撤销判据 | 原判据是**字面相似**（名字都含「一致性」），非职责分析；实测三条反证 |
| 取证 | ① `audit_index` 是 **`hub audit` CLI 的实现体**：`commands/audit.py` 以子进程调用 `scripts/audit_index.py` ⇒ 在役<br>② `index_consistency` 是 **INDEX 登记行正则 / 分区表 / 目录→文件映射的单一源**：`render_index.py`、`post_ingest_hook.py`、`startup_budget.py` + 4 个测试模块 import 它<br>③ 检查维度不同：`audit_index` 独有 **misrouted（错位登记）** 维度（`tests/test_audit_index.py` 锁定），`render_index --check` 只管「可复现」 |
| 处置 | **保留两者**并在本表留证；若将来确要退役，前置条件是先把共享常量抽到 `common/index_registry.py`（独立重构批次） |

## 全量裁定（113 个模块）

| 判定 | 数量 | 含义 | 本轮处置 |
| -- | -- | -- | -- |
| `keep` | 80 | 有门禁角色 / 活代码引用 / **在役编排引用 / 产物时间戳证据** | 保留 |
| `manual-cli` | 33 | 人工 CLI 入口（`__main__` 可执行） | **保留**：逐个取证见下 |
| `duplicate` | 0 | 命中**声明**的职责重复 | 原 2 条已撤销（簇 1） |
| `unused` | **0** | 三无（无门禁 / 无引用 / 无在役证据） | **无死模块可删** |

### `manual-cli` 33 个为何全保留（取证口径）

- 它们是**用户/定时任务可调用的 CLI 入口**：`recall_regression`、`secret_sentry`、`platform_healthcheck`、
  `hub_mcp_launcher`、`hub_daily_report`、`task_capability`、`star_trend_snapshot`、`vlook`、`safe_patch`、
  `reconcile`、`rule_following_timeseries`、`query_report`、`real_query_regression` 等。
- 证据来源三类：① 巡检/定时脚本（`scripts/*.cmd`）编排引用 ② 中枢产物文件（`retro/` · `.sync/` · `system/run/`）的最近时间戳 ③ 测试与文档引用。
- 本轮**新增**两类在役证据（原尺子只有 ①③）：
  - `refs_scheduled`：**编排入口**（`.cmd`/`.bat`/`.ps1`）里以 `x.py` 或 `scripts.x` 形态提到本模块；
  - `last_run`：本模块**产物**的最新时间戳（`artifact` = 真实运行时间）/ 编排脚本 mtime（`scheduled` = 弱证据）。

## C8「模块数 ≤75」目标裁定

**裁定：按当前证据口径，该目标不可达 ⇒ 需重新定义（不再是本轮待办）。**

依据：
1. 台账内 `unused`（三无）= **0** ⇒ **没有死模块可删**；删除任何在役模块都会破坏定时任务或用户工作流。
2. 唯一被声明为重复的 2 个模块经取证**在役**（簇 1）⇒ 强删会同时打断 `hub audit` CLI 与 INDEX 正则单一源。
3. 计划里的「105 → ≤75」是**重构前的估算**；此后新增的模块多数是门禁/巡检能力（recall 回归、secret sentry、能力对账、向量回归…），
   删它们等于删门禁。⇒ 与 A2 同一条原则：**计数是结果，不是目标**。

## 尺子本轮增强（为将来的「死模块」判定补齐证据）

| 字段 | 含义 | 口径 |
| -- | -- | -- |
| `refs_scheduled` | 编排入口引用（`.cmd`/`.bat`/`.ps1`） | 只认 `x.py` / `scripts.x` 两种调用形态，避免散文误判 |
| `last_run` | 最近一次**产物**时间戳 | `artifact` = 真实运行时间；`scheduled` = 编排脚本 mtime（弱证据）；**无证据就是 null，不猜** |
| `last_run_kind` | 上述证据的类别标签 | `artifact` / `scheduled` / `none` |

配套单测（`hub-engine/tests/test_inventory.py`）：
`test_scheduled_refs_detects_cmd_orchestration` · `test_last_run_evidence_prefers_real_artifact` ·
`test_verify_declarations_detects_expired_entry`（改为 monkeypatch 注入过期声明，不再依赖仓库状态） ·
`test_declared_map_shape`（允许空 `retire`，但必须留 `why` 说明撤销理由）。
