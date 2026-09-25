# 清理记录：3 个零引用脚本 + 仪表盘草稿子系统（2026-09-25）

> 上游：WORK.md 活跃待办 **P2**（死代码 + 仪表盘处置）。
> 纪律：**逐个取证，非批量**；不可逆动作先取证再动；删除项留 SHA 以便一键恢复。

## 0. 复审方法

`python -m scripts.audit_dead_modules`（**2026-09-25 已迁入仓库**，在 `hub-engine/` 下跑；
此前位于 gitignore 的 `work/`，被本文件与审计报告引用 ⇒ 换机即断链。判据：被 .py 导入 / 被编排器按文件名调用 /
被 .md·.yaml·.cmd·pre-commit 提及 / 被计划任务引用 —— 任一命中即算"有引用"）。

**首轮结果：零引用模块 5 个**（WORK.md 记录的历史值是 8 个，已收敛）。逐个人工复查后
**保留 2 个**、**删除 3 个**：

| 模块 | 复审结论 |
|:--|:--|
| `scripts/index_locatability_bench.py` | **保留**。它是 T2 的正式度量命令（`python -m scripts.index_locatability_bench --rev`），本次刚用它复核完 INDEX 可定位性 |
| `tools/safe_patch_handler.py` | **保留（审计假阳性）**。被 `mcp_server.py` / `tools/mcp_handlers.py` / `tests/test_mcp_server.py` 引用；且 `CHARTER.md:33` 声明 **`safe_patch` 为高风险改动唯一安全渠道** ⇒ 删除会破坏契约 |

> ⚠️ 结论：**零引用 ≠ 可删**。本次 5 个候选里就有 1 个假阳性（`safe_patch_handler`），
> 且另有 1 个正在被文档化的手动命令使用。任何删除动作都必须逐个人工复查入口/注册表。

## 1. 删除项与取证

| # | 删除文件 | 判断依据 | 恢复用 blob SHA |
|:--|:--|:--|:--|
| 1 | `hub-engine/scripts/measure_embed_speed.py`（1,097 B） | 一次性测速脚本（Hermes 2026-09-14）：硬编码 3 个嵌入模型 + `localhost:1234`，**无 `__main__` 守卫**（导入即发请求）；结论已沉淀进经验卡（`embedding-model-chinese-retrieval-bench-bge-m3-vs-nomic`） | `6d8ece41e8e57b2ff3c261651f0e4611cdcccf4c` |
| 2 | `hub-engine/scripts/mcp_e2e_phase3.py`（1,521 B） | T11 Phase 3（2026-09-08）的一次性 E2E：断言 `hub_announce` 出现在 MCP `list_tools`。**该断言已被常驻测试覆盖**：`tests/test_mcp_server.py:33`（工具清单含 `hub_announce`） | `a0a81c6666961981b3a3b0cd715ab4852530067c` |
| 3 | `hub-engine/scripts/verify_vector.py`（1,871 B） | 7 条**临时**查询的三通道并排打印。**口径已被 `recall_regression.py` 取代**：后者 22 条金标准（含 2 条蓝图池守卫）+ 双模式 recall@k/recall@1 + 蓝图占位率 + 阈值门禁（`--fail-below` 同族的退出码 2）。留着无金标准、无阈值，反而容易与门禁口径混淆 | `3cbbfdebb04a446faa0b4d796a0ce86ce719733d` |

恢复命令（任一）：

```powershell
git checkout <删除前的提交> -- hub-engine/scripts/<文件名>.py
# 或按内容恢复（blob 仍在新提交的历史里）
git cat-file -p <blob SHA> > hub-engine/scripts/<文件名>.py
```

## 2. 仪表盘草稿子系统（31 文件 / 226.4 KB）

- **位置**：`work/dashboard/`（`work/` 已在 `.gitignore:19` 中忽略 ⇒ **本就未进版本控制**，
  删除不可由 git 恢复，故改为**归档**而非直删）
- **内容**：`index*.html`（4 版）、`gen_dashboard_v2/v3.py`、`mini_server.py`、`vlook.py`、
  `dashboard_collect.py`、`dashboard_regen.py`、`verify_dashboard.py`、`dashboard-data.json`、`slots/`
- **为何判为处置对象**：
  1. **无入口**：没有任何 tracked 文件引用该目录（审计零引用）
  2. **路径写死且已失效**：`mini_server.py` 里 `os.chdir(...\feat-implement-plan-ZilBmv\work\dashboard)`
     写死本 worktree 路径，worktree 一移即废
  3. **与"活着的仪表盘"不是同一套**：仓库根部的 `hub-health.html` / `flywheel-timeline.html` /
     `memory-hub-flywheel-v2.html` **仍在用**，由 tracked 脚本
     `hub-engine/scripts/hub_health.py`、`flywheel_runlog.py` 生成 ⇒ **本次不动**（勿连坐）
- **处置**：归档为
  `work/_archive/dashboard-20260925.zip`（74.8 KB，zip 内 32 条目 = 31 文件 + 1 目录项，
  已校验条目数）；随后删除 `work/dashboard/`
- **恢复**：`Expand-Archive work\_archive\dashboard-20260925.zip -DestinationPath work`

## 3. 仍在用的 `work/` 脚本处置（2026-09-25 追加）

`work/` 在 `.gitignore` 里，但其中的脚本会被文档引用（P1-d / 审计 I-4）。本次处置：

| 脚本 | 处置 | 理由 |
|:--|:--|:--|
| `audit_dead_modules.py` | **迁入仓库** → `hub-engine/scripts/audit_dead_modules.py`（V2.0，路径自解析） | 死代码审计是 P2 类工作的常备工具，且被 cleanup 留档与审计报告引用 |
| `bench_recall.py` | 归档 → `work/_archive/oneoffs-20260925/` | 能力已被 `hub-engine/scripts/recall_regression.py` 取代（22 条金标准 + 阀值门禁 + 蓝图占位率）；`RUNLOG.md` 的 2 处引用是**历史记录**，保留不改 |
| `_t1_precheck.py`、`write_t1_{method,results,v2_results}.py` | 归档 → 同上目录 | 一次性卡回写/预检脚本，产物已落卡与 `docs/compose/metrics/`；T1 重跑靠仓内的 `scripts.rule_following_timeseries` |
| 旧 `work/audit_dead_modules.py` | 归档（已被迁入版取代） | 避免两份并存 |

恢复：直接从 `work/_archive/oneoffs-20260925/` 拷回（未进版本控制的那几个仍只存在于此）。

## 4. 验收

- 删除后全量 `pytest`：**558 passed / 4 skipped / 0 failed**（无测试/导入引用被删脚本）
- `ruff check .` 通过
- 外层工作区仅剩本次 2 个删除 + 1 个新增文档
