# 退役协议（D8：**默认直接 `git rm`**，不建实体归档仪式）

- 日期：2026-10-02
- 取代：`_retired/` 目录 + `RETIRED.json`（三份）+ 逐件标签块 + 守卫测试 + 4 处排除规则的**仪式**
- 关联：架构重构 `M0.6/Task 10`；上游讨论 `docs/compose/specs/2026-10-02-hub-capability-memory-architecture.md` §Q12

## 为什么删掉仪式

旧流程退役**一件**需要维护 **5 处**：①文件头 6 行标签块 ②`RETIRED.json`（三份）
③`_retired/README.md` 段落 ④守卫测试 `test_retired_archive.py` ⑤`.ruff.toml` +
`pyproject.toml` + `test_no_hardcoded_paths.py` 的排除规则。

**16 件退役换来的仪式成本 ≥ 被清理的代码体积** —— 而 **git 历史本身就是归档**
（`git show <commit>:<path>` 取回即可）。判据：**仪式成本 > 被清理物成本时，删仪式**。

## 协议（两句话）

1. **默认 `git rm`**，把为什么退役写进**结构化 commit message**（信息不丢）。
2. **只有两类保留实体归档**：
   - **反面教材**（如 `scripts/merge-methodology.py` / `deduplicate-experience.py`：
     护栏本身是资产，留着防重蹈）
   - **仍被卡/文档引用且改不掉**（此时应先改引用，改不掉才留档，并在本文件登记一行）

## 退役件必须写进 commit message 的三行

```text
@reason:        <为什么它已无用 / 被谁取代>
@superseded_by: <取代者；确无则写（无）>
@evidence:      <零引用的取证方式（如 AST 级引用扫描 + 产mtime 时间戳）>
```

> **取证纪律不变**：`--candidates` 会给出候选，但**不得凭印象删**。
> 每个候选必须能回答：①活代码引用（AST 级）②是否被计划任务/文档消费 ③产物时间戳。
> 反例已发生两次：`sleep` 自进化链**在跑**（每日 00:35/07:30 两次产出）——曾差点被当成死代码；
> `retro/snapshot-*.json` 是 `rule_following_timeseries` 的**输入**——曾被我的产物清理误删。

## 一次性的迁移脚本

同理：一次性脚本（如 `migrate_grade.py`）完成使命后按本协议 `git rm`；
若同类迁移还要再来一次，**优先把它做成幂等的常规工具**（如 `check_encoding --fix`），
而不是留着一个个 `migrate_*.py`。

## 现存实体归档清单（本协议下仅此几类）

| 文件 | 类别 | 为何留 |
|---|---|---|
| `scripts/merge-methodology.py` | 反面教材 | 实测会截断内容；护栏本身是资产（已加 `forbidden-guarded` 标签） |
| `scripts/deduplicate-experience.py` | 反面教材 | 实测会误杀互补卡；同上 |
| `scripts/backup-rules.py` | 人工 CLI | 改 `rules/` 卡前的纪律动作 |
| `scripts/fix_type_dir_mismatch.py` | 人工 CLI | lint 只检测不修复，本脚本是人工修复入口 |
| `hub-engine/scripts/proofread_index_desc.py` | 人工 CLI | 描述质量巡检工具 |
