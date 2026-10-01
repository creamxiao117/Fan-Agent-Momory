# 退役归档区（仓根 scripts/ 侧）

**归档 ≠ 删除**：本目录保存已完成使命的一次性脚本，保留完整内容以便日后取证/恢复。
机器可读清单见同目录 `RETIRED.json`（守卫测试 `hub-engine/tests/test_retired_archive.py` 校验一致性）。

## 约定

与 `hub-engine/scripts/_retired/README.md` 同一套（标签块四条 + 同步清单 + 不再当门禁对象）。
`.ruff.toml` 已用 `**/_retired/**` 排除本目录。

## 本批（2026-10-01）

- `conflicts_adjudication_20260917.py` / `readjudicate_conflicts.py` / `resolve_conflicts_20260918.py`
  —— 2026-09-17/18 冲突裁定的一次性脚本，裁定结果已落盘中枢与 `docs/`。
- `daily_growth.py` + `daily_growth.cmd` —— 旧日常链，已被 Hermes 晨间链
  （`hub-engine/scripts/hub_daily_cron.py` / `flywheel_cron.py`）取代；且 `.cmd` 内写死
  `D:\AIwork\...` 绝对路径与系统 python，在本 worktree 下必然失败（危险的历史残留）。

## 注意：这里**没有** merge/dedup 类脚本

`merge-methodology.py` / `deduplicate-experience.py` **刻意留在仓根**（带拒绝护栏）：
实测它们会截断内容 / 误杀互补卡，保留是为了让「执行即报错」这件事继续生效，
并作为反面教材被 WORK.md 与卡引用。它们打的是 `@status: forbidden-guarded`，不是 `retired`。
