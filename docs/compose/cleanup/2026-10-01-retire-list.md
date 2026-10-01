# 退役清单与归档（2026-10-01）

> 上游：单源/定形改造收尾（`docs/compose/plans/2026-10-01-single-source-l0-shape.md`）
> 的「附带裁定项」——`slim_index` / `regen_index_desc` / `fix_index_registry` 等已被渲染器取代。
> 纪律：**逐个取证，非批量**；归档优于删除；每件带可恢复标签。

## 0. 方法与工具修正（先修尺子，再量东西）

1. **修好审计工具**：`audit_dead_modules` 的引用正则只认 `import X` / `from X import`，
   不认 `from scripts.X import`——而本仓跨模块导入**全部**是带前缀写法 ⇒ 系统性误报「零引用」
   （实测漏报 `scripts/card_fields.py`，它被 3 处引用）。已改为**可选包前缀**并加单测
   `tests/test_audit_dead_modules.py`（含反例：`foobar` 不得因 `foo` 的模式命中）。
   修好后零引用名单从 2 项降到 1 项（剩下的 `proofread_index_desc.py` 是**活的手工 CLI**，保留）。
2. **引用面普查**：对每个候选把引用分类为「活代码 / 测试 / cmd·钩子 / 文档 / 卡」，
   并查 Windows 计划任务（`schtasks`）——**无候选脚本出现在计划任务里**。
3. **人工裁定**：只有「既无活引用、职责又被取代」者才归档；手工 CLI、反面教材、被测对象一律保留并打标签。
4. 归档区一律从**门禁视野**移除：`.ruff.toml`（`**/_retired/**`）、
   `tests/test_no_hardcoded_paths.py`、`scripts/audit_dead_modules.py` 均已排除。

## 1. 已归档（16 件 → `_retired/`，带标签 + 机器可读清单）

| # | 归档件 | 位置 | 判据（为何已无用） | 被谁取代 |
|:--|:--|:--|:--|:--|
| 1 | `slim_index.py` | `hub-engine/scripts/_retired/` | 机械字符截断（09-23 已证伪：239/251 条变半截词）；枚举迁出 L0 后无可截之物 | `render_index.py` |
| 2 | `test_slim_index.py` | `hub-engine/tests/_retired/` | 随被测对象退役 | `test_render_index.py` |
| 3 | `regen_index_desc.py` | `hub-engine/scripts/_retired/` | 描述列重建并入渲染器；上限改由 `common/index_limits` 单一来源 | `render_index.py` |
| 4 | `fix_index_registry.py` | `hub-engine/scripts/_retired/` | 幽灵 slug 纠偏：渲染保证「索引 == 卡文件」，前提不复存在 | `render_index.py` |
| 5 | `test_fix_index_registry.py` | `hub-engine/tests/_retired/` | 随被测对象退役 | `test_render_index.py` |
| 6 | `fix_orphans.py` | `hub-engine/scripts/_retired/` | 补登记职责被渲染取代（**检测**仍由 `tools/lint.py` 负责） | `render_index.py` |
| 7 | `test_fix_orphans.py` | `hub-engine/tests/_retired/` | 随被测对象退役 | `test_lint.py` |
| 8 | `migrate_index_fields.py` | `hub-engine/scripts/_retired/` | 一次性迁移已完成（69 卡写入 `index_desc`/`index_note`） | `set_index_meta.py` |
| 9 | `test_migrate_index_fields.py` | `hub-engine/tests/_retired/` | 随一次性脚本退役 | `test_set_index_meta.py` |
| 10 | `migrate_l1_tier.py` | `hub-engine/scripts/_retired/` | 一次性迁移已完成（7 卡写入 `l1_tier`） | `card_fields.py` + `l1_cards()` |
| 11 | `analyze_experience_dupes.py` | `hub-engine/scripts/_retired/` | 去重分析结论已沉淀为卡；merge/dedup 系脚本已被裁定禁止执行 | 无（结论已落卡） |
| 12 | `conflicts_adjudication_20260917.py` | `scripts/_retired/` | 09-17 冲突裁定一次性任务，结果已落盘 | 无 |
| 13 | `readjudicate_conflicts.py` | `scripts/_retired/` | 配套重裁一次性脚本 | 无 |
| 14 | `resolve_conflicts_20260918.py` | `scripts/_retired/` | 09-18 冲突解决一次性脚本 | 无 |
| 15 | `daily_growth.py` | `scripts/_retired/` | 旧日常链已被 Hermes 晨间链取代；配套 `.cmd` 写死 `D:\AIwork\...` 绝对路径（本 worktree 下必然失败） | `hub_daily_cron.py` / `flywheel_cron.py` |
| 16 | `daily_growth.cmd` | `scripts/_retired/` | 同上（硬编码系统 python + 另一 worktree 路径） | 同上 |

**每件的标签块**（`.py` 用 `#`、`.cmd` 用 `rem`）：

```text
@status: retired
@retired_at: 2026-10-01
@original_path: <退役前路径>
@superseded_by: <取代者>
@reason: <一句话>
@retired_from_commit: <归档前 HEAD>
@restore: git checkout <同一个 commit> -- <原路径>
```

**机器可读清单**：`hub-engine/scripts/_retired/RETIRED.json`（7 项）、
`hub-engine/tests/_retired/RETIRED.json`（4 项）、`scripts/_retired/RETIRED.json`（5 项）。

## 2. 保留但已打状态标签（5 件，**不要**当退役件处理）

| 文件 | 标签 | 为什么留 |
|:--|:--|:--|
| `scripts/merge-methodology.py` | `forbidden-guarded` | 实测会截断内容；护栏本身是资产（WORK.md 禁止执行） |
| `scripts/deduplicate-experience.py` | `forbidden-guarded` | 实测会误杀互补卡；同上 |
| `scripts/backup-rules.py` | `manual-cli` | 改 `rules/` 卡前的纪律动作（本轮刚修好它的崩溃 bug） |
| `scripts/fix_type_dir_mismatch.py` | `manual-cli` | lint 只**检测** type/目录不一致，本脚本是人工修复入口 |
| `hub-engine/scripts/proofread_index_desc.py` | `manual-cli` | 描述质量巡检工具（② 增长感知评测待接入） |

其他审计候选但**明确保留**：`demo_e2e.py`（被 `tests/test_e2e.py` 导入）、
`index_locatability_bench.py`（T2 正式度量命令）、`audit_dead_modules.py`（本清单工具）。

## 3. 本地未跟踪残留（不可由 git 恢复，另行处置）

| 位置 | 性质 | 建议 |
|:--|:--|:--|
| `hub-engine/scripts/work/report_full.json` | 已被 `.gitignore:23`（`work/`）忽略的运行产物 | 可安全删除（非 tracked，删除不可由 git 恢复，但不含信息） |
| `AgentMemoryHub/.backup/**` | `backup-rules.py` 的本地保险副本（已 ignore） | 保留（只占本地磁盘） |
| `AgentMemoryHub/retro/snapshot-2026-10-01.json` | 巡检快照产物，**未被 ignore 也未跟踪** | **待裁**：要么纳入 git（历史快照可比对），要么加进 `.gitignore`（推荐后者，与 `patrol.log` 同口径） |

## 4. 校验机制（防止归档腐化）

`hub-engine/tests/test_retired_archive.py` 钉死三条不变量：

1. **标签**：归档区每个文件都必须带 `@status: retired` + 原路径 + 取代者 + 理据；
2. **清单双向一致**：`RETIRED.json` ↔ 磁盘（归档未登记 / 登记未归档 都红）；
3. **不得复活**：活代码/钩子/cmd 不得再**可执行地**引用退役模块
   （引号内的路径调用、`from/import`、`-m scripts.X`；反引号里的历史叙述不算）；
4. 附加：保留体必须自报 `@status:`（`manual-cli` / `forbidden-guarded`），否则下次清理会误删。

## 5. 恢复方式

```bash
# 按标签里的 @restore（最省事）
git checkout <retired_from_commit> -- <original_path>
# 或直接取历史内容
git show <retired_from_commit>:<original_path> > <target_path>
```

> 归档 ≠ 删除：这些文件仍在仓库里、仍可读；`git log --follow` 也能追到它们的完整历史。
