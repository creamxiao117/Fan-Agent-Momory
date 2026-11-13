# WORK.md（当前状态 · 唯一来源）

更新于：**2026-11-13** · 架构重构主体已落地：判据 **C1–C7 通过，C8 已重新定义**

> 明细 `docs/superpowers/retro/work-history.md`｜重构计划 `docs/compose/plans/2026-10-02-hub-architecture-refactor.md`｜任务包 `docs/compose/plans/2026-11-13-hermes-hub-task-pack.md`｜逐轮 `RUNLOG.md`

## 当前状态（卡片/测试/grade/账本=2026-11-13，其余 2026-11-02 实测）

- 卡片 **704**（blueprints 232 / experience 352 / methodology 77 / projects 23 / rules 13 / longterm 8）；lint **全 0**
- 巡检 **9 步**；**pytest 969 passed**（指针模式 +24 条回归）；健康 **98.5/100**（card/skill/flywheel/llm 全 100、gate 93.8）⇒ ✅ **exit 0**（code 平台未提交的 `capability_reconcile.py` 已按 §4-A 收口提交 `a62dbe8`，ruff 告警清零）
- 测试 **969 用例**；**门禁 9→3 且 scope-gated**（`common/gate_scope.py`，按 staged 触发）⇒「他人未提交改动阻断提交」缺陷已消除，`--no-verify` 合法用途归零
- **grade 覆盖 704/704 = 100%**（iron 7 / proven 136 / domain 214 / pitfall 45 / task 302）；**L1 由 `grade=iron` 派生**；bootstrap 按 grade 三段分层；**正交轴 `evidence`**（t1 92 · measured 57）
- 平台元数据**单源**（`hub.config.yaml`）；账本 `capabilities.json|md`+`INVENTORY.json`（**114 条**：keep 107·manual-cli 7·unused 0）；`capability_reconcile` 挂巡检第 4 步（含降级路线图）
- **pi 接入**：MCP 已通（7 工具）· `agent/AGENTS.md` 顶部托管块已注入 · `memory-hub.ts` 扩展 5 命令 · 回写落 `pi_draft/`（人工确认制）· MCP ui 资源按客户端声明
- 定时链：07:30 巡检 / 00:35 夜间合并 / 06:00 密钥哨兵 / 09:00 清理 + Hermes 5 任务（晨报→提升→star-distill+T1→周六评测）；微信通道已停用

## 2026-11-13 晚 · 平台记忆指针化（context 成本治理）

| 平台 | 前 | 后 | 降幅 |
| --- | ---: | ---: | ---: |
| hermes MEMORY.md | 14,188 | 9,651 | 32.0% |
| code AGENTS.md | 69,699 | 18,104 | 74.0% |
| workbuddy MEMORY.md | 57,363 | 11,607 | 79.8% |
| **合计** | **141,250** | **39,362** | **72.1%**（≈ 每轮省 50,900 tokens） |

- **机制**：平台只收「卡名+一句话+检索路径」，正文留中枢按需查（`memory_push_mode: pointer`）；`global-rules`（GR-1~GR-4）**永远内联**（铁律每轮生效）
- **托管区哨兵** ⇒ 边界由中枢标记决定 ⇒ 完全重建 ⇒ 天然幂等
- **迭代 4 次收敛**（教训已进方法论卡 `2026-11-13-platform-memory-pointer-mode.md`）：逐卡追加⇒清单漂移／按分隔符定边界⇒吞 2,364 字符／按标题定边界⇒吞标题行／哨兵托管区⇒✅
- **hermes 动态约束**：死上限⇒「基线+窗口增量」⇒无死上限；USER.md 余量 **31→200** 字符；并修掉「user 基线误用 memory 口径⇒约束全失」bug
- **双周体检**（`0 9 1,15 * *`）：14 天窗口 + fail-closed（无证据平台不降级）⇒ 本期 0 可降级 / 53 待确认

## 活跃待办（按优先级）

| # | 任务 | 判据 / 做法 |
| -- | --- | -- |
| **A1–A3** | ✅ **已达成**：grade 100% + `tier`/`l1_tier` 退役 · `rules/` 23→13 · **C8 重定义**（`unused`=0·`duplicate`=0·在役证据覆盖 93.9%·模块数棘轮 114，`c8_violations` 自动判定） | RUNLOG R23–R27 |
| **A4** | ✅ **成立**：后窗口 37 天全 0 · 产出率 **66%**/重复率 **34%**；「3.2%」是指标 bug（漏计 227 条）⇒ 旧「未触及根因」作废；已补「退化可见」（`degraded`） | 明细见 `docs/compose/metrics/2026-11-02-t1-rerun.md` |
| **A5–A7** | ✅ **已达成**：`/hub-write`（预览+确认制）· 检索/失败可见 · 预算帽（棘轮+60%降级目标）· 盘点卡去数字化 | R26 |
| **A8** | ✅ **方案 A 全落地**：`evidence` 字段（none/measured/t1）· 检索侧按 evidence 加成+透出+标 `[measured]` · 回填 149 张 | 报告 `docs/compose/reports/2026-11-02-evidence-axis.md` |
| **A9** | ✅ **已判定**：用户确认 workbuddy 最近没使用 ⇒ 原「近 30 天用过+近 7 天零检索」告警属噪音 ⇒ 收紧为「**近 14 天**用过+近 7 天零检索」；实测不再被报 | 维持 |
| **A10** | ✅ **全部达成**（2026-11-13 晚）：推中枢仓（`409f5ec`+`adc3055`）· 告警线 58000 · capability_scan · inventory · **hermes 动态约束落刀**（`_char_limit()` 改「基线+窗口增量」⇒ 无死上限；`4285fd8c847` 已推 fork）· **§3.5 反向对应**（hermes 16000→`memory_char_warn_limit` 17000 只报不拦）· **指针模式**（三消费端 ⇒ ↓72.1%） | 任务包 `docs/compose/plans/2026-11-13-hermes-hub-task-pack.md`｜方法论卡 `2026-11-13-platform-memory-pointer-mode.md` |

### T1 判据（重跑 + 口径修正）

> **①** 后窗口 ≥10 天且 `invalid/orphans/ghosts` 全 0（37/37 天）**②** 产出率 ≥40% 且重复率 ≤60%（66%/34%）**③** 任一维度非零或产出率 ≤11% ⇒ 未触及根因。口径见 `docs/compose/metrics/2026-11-02-t1-rerun.md`（原「后窗口」硬编码 2 天 ⇒ 判据①结构上不可能满足；入区统计漏计 227 条 ⇒ 旧「未触及根因」是**指标 bug 误判**）。

## 架构重构判据现状（C1–C8）

| 判据 | 现状 |
| -- | -- |
| C1 分型单源 | ✅ `task_tier.py` |
| C2 平台登记单源 | ✅ `hub.config.yaml` |
| C3 尺子双把 | ✅ `INVENTORY.json`+`capabilities.json`（`--check` 可跑） |
| C4 门禁瘦身 | ✅ 3 道 scope-gated |
| C5 流水线瘦身 | ✅ 9 步 + 两件产物 |
| C6 等级轴 | ✅ grade 100%（704/704）；每型 iron ≤3；L1 由 `grade=iron` 派生 |
| C7 账本对账 | ✅ 巡检 pass（差异 0）；帽＝逐平台棘轮+60%降级目标+降级路线图 |
| C8 瘦身结果 | ✅ **已重定义**：`unused`=0·`duplicate`=0·在役证据覆盖 **93.9%**·模块数**棘轮 114**（新增须等量退役）—— `inventory.py::c8_violations` 自动判定 |

## 门禁

- **提交时**（两仓同钩子 `gate_runner.py`）：`code`→ruff×2 · `text`→编码+markdownlint · `l0`→startup_budget+render_index --check（按 staged 触发）；退出码 0/1/2/3
- **每日** 07:30 巡检 9 步 · 00:35 夜间合并 · 06:00 密钥哨兵 · 09:00 清理
- **手动** `recall_regression`（58 条金标准，退出码 2=未达 90%）· `inventory --check` · `capability_reconcile`
- 验收：`.venv\Scripts\python.exe -m pytest` → **969 用例**；ruff 全绿
- **主仓 CI 首次全绿**（run `43434141079`）：12/12 success

## 禁止 / 注意

- **勿执行** `merge-methodology.py`/`deduplicate-experience.py`（有护栏）
- **解释器必须 `.venv\Scripts\python.exe`**（系统 python 缺 jieba → 检索测试静默跳过＝假绿）；中枢卡提交须 `git -C AgentMemoryHub`；跨仓改动两仓提交相邻、message 互引
- **迁卡/改 slug 后必须 `engine.py build-vectors`**：向量库按**路径**索引，路径一变旧行失效（召回静默掉 7 个点）
- **改 `hub.config.yaml` 后必须 `capability_scan --write`**：否则巡检报「账本与实测态不一致」
- `INDEX*.md` 是渲染产物禁手改（改卡后 `render_index --write`）；**提交门禁自改期间不得 `--no-verify`**，门禁故障当场修
- **状态源纪律**：WORK.md=唯一状态；每轮追加 RUNLOG.md（最新在前）；**别新建笔记文件**
- 外层超时>内层（pytest 外 420s/内 180s）；归档卡须同步查引用它的夹具（期望卡名会漂移）
- GitHub push 走 **HTTP/1.1**（`git -c http.version=HTTP/1.1 push`）：本机 HTTP/2 协商被中间设备打断
