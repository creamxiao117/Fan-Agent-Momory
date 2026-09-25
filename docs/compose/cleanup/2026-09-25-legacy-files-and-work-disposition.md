# 清理记录：历史遗留文件 + `work/` 定位（2026-09-25）

> 上游：用户指令「删除历史遗留的无用文件」+ 审计（`docs/compose/reports/2026-09-25-project-audit.md`）
> 纪律：**逐项取证再动**；可恢复的（tracked）记 blob SHA；不可恢复的（untracked）先归档或确认可重建。

## 1. 删除项（每项都有"零引用/可重建"取证）

| 目标 | 体积 / 跟踪 | 取证 | 处置与恢复 |
|:--|:--|:--|:--|
| `node_modules/` | 11.33 MB / **untracked**（跟踪 0 文件） | 根目录 npm 残留（`.gitignore` 已含 `node_modules/`）；全仓无引用 | **删**。恢复：在需要处 `npm install`（本项目 py 侧无依赖它） |
| `.tools/` | 1.5 MB / **untracked**（跟踪 0 文件） | 内含且仅含 `yamllint/`；`.gitignore`/`.markdownlintignore` 仅作排除项列出，**无任何活跃引用**（`RUNLOG.md` 的 yamllint 提及是历史记录，非当前门禁） | **删**。恢复：`pip install yamllint` |
| `methodology/**`（仓根层） | 1 文件 / 24 行 / **tracked** | 早期项目卡《统一记忆中枢·协作约定》（2026-08-17）：内容（骨架职责/引擎约定/不可违背/迭代门）已被现行 AGENTS.md + CHARTER.md + WORK.md 全面覆盖；全仓**零引用**；与中枢 `AgentMemoryHub/methodology/` 无同名卡 | **`git rm`**（blob `4b5b7095f29112b6c218d2b2a29f4f17d609b5a6`）。恢复：`git cat-file -p 4b5b7095 > <路径>` |
| `work/` 下 97 个草稿件 | 本地草稿区（gitignore） | 见 §3 | **归档**（不删）到 `work/_archive/scratch-20260925/` |

## 2. 补完 P1-d：又迁入 2 个「被 tracked 文件引用」的只读工具

先前只迁了 `audit_dead_modules.py`；本次扫到还有两个只读分析器被**仓库内文件**引用（正是 I-4 那个病）：

| 原位置 | 现位置 | 谁引用它 |
|:--|:--|:--|
| `work/analyze_experience_dupes.py` | `hub-engine/scripts/analyze_experience_dupes.py` | `scripts/deduplicate-experience.py` docstring |
| `work/verify_merge_fidelity.py` | `hub-engine/scripts/verify_merge_fidelity.py` | `scripts/merge-methodology.py` docstring |

两处路径已改为 `Path(__file__).resolve().parents[2]`；同时修掉 4 处悬空引用（`python work/xxx.py` → `python -m scripts.xxx`），
其中 `hub-engine/scripts/rule_following_timeseries.py` 的 usage 行此前指向 `work/`（早已迁走）—— 已改对。

## 3. `work/` 定位（审计重构候选 D）

**定位：只读草稿归档区**。规则：

1. **不许再把仍在用的能力留在 `work/`**（它是 gitignore 区，换机即失）——要用就迁进仓库；
2. 临时产物写这里没问题，但**文档里不得引用 `work/` 下的脚本路径**（I-4 / M-3 同一个病）；
3. 收尾时把当轮草稿移入 `work/_archive/<批次>-<日期>/`。

本次执行：97 个文件（含 `check-code-v1/`、`trae-handoff-archive/`、各 `*.py` 一次性脚本）→
`work/_archive/scratch-20260925/`；历史批次另存 `work/_archive/oneoffs-20260925/`、`work/_archive/dashboard-20260925.zip`。
`work/` 根目录现已只剩 `_archive/`。

恢复：直接从 `work/_archive/<批次>/` 拷回即可（untracked 内容只存在于此）。

## 4. 验收

- 删除后：`ruff check .` 全绿；`pytest` 通过（见提交信息）；巡检 24 步 exit 0
- `git status`：跟踪区仅剩本次 `git rm` 与新增两脚本 + 文档
- 磁盘：本次释放 ≈ **12.8 MB**（11.33 MB node_modules + 1.5 MB .tools）
