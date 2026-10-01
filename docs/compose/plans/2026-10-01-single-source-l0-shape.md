# 单源派生 + L0 定形（形状门禁取代批帽）Implementation Plan

- 日期：2026-10-01
- 来源：维护者就「INDEX 帽余量 77 字符 / 建议抬到 24k」发起根因讨论后裁定的「① 单源 + 派生 + L0 定形 + 形状门禁」路线
- 关联：`docs/compose/specs/2026-09-23-slim-rules-gates-design.md`（S3 预算口径）、`docs/compose/plans/2026-09-23-slim-rules-gates.md`（A4 INDEX 拆分先例）
- 验收判据：C1 / C2 / C3，见 Task 8（**判据不通过即视为未完成**）
- 范围外（另案，本计划不含）：② 增长感知评测（金标准随语料扩容 + @1 阈值告警）、③ 生命周期/GC（未验 B+ 不落卡、active 配额、超期降级）

## 问题与不做什么

事实（2026-10-01 实测）：

- `AgentMemoryHub/INDEX.md` = **21923** 字符 / 帽 22000，余量 77；L0 合计 28907/30000
- 09-27→10-01 四天 L0 净增 **1565** 字符，其中 blueprints 区 **+1568（135→152 行）**，其余各节净变化 ≈ 0
- 分项帽之和 = 2500+1500+5000+22000 = **31000 > 30000**（09-27 抬帽 20k→22k 时已破不变量）；`tests/test_startup_budget.py` 2 条用例自 09-27 起持续失败，patrol 自 09-28 起连续 exit=1
- 抬到 24000 → 合计 33000，除非把其余三项帽压到 6000 以下，而三项实际值已达 6984（1416+784+4784）→ **数学上不可行**；按实际值重配平的 INDEX 帽上限 23016，按当前增速只够约 1.5 天

因此本计划**不做**：抬帽、压缩描述（09-23 已证伪的机械截断）、截断卡片正文。做的是一件事——**把「与卡数成正比」的增长项从被门禁盯的文件里整项移除**。

## 架构裁定（本计划前提，实施时不得偏离）

| 项 | 裁定 | 理由 |
| --- | --- | --- |
| 唯一真相 | `AgentMemoryHub/<dir>/*.md` 卡文件 | 已是现状，最大资产，不动 |
| 派生形式 | **纯函数扫描 + 渲染产物**，**不建缓存派生文件**（不引入 `registry.jsonl`） | 消除「陈旧 / 新写入者 / 跨进程可见性」三个失败模式；实测 501 张卡全扫 **452ms**，无需缓存 |
| L0 形态 | `INDEX.md` = 定形能力图，**per-card 登记行 = 0**，行数不随卡数变化 | 形状不变量顶不了帽，永不需人批 |
| L2 形态 | `INDEX-full.md` = 全量分区清单（渲染产物，不参与预算） | 人仍可查全量；机器用检索 |
| 一致性 | `python -m scripts.render_index --check`（模型同 `ruff format --check`：与磁盘不一致即非 0，`--write` 一键修） | 交给门禁，不靠自觉 |
| 门禁分层 | **形状断言（主）+ 数字帽（兜底）** | 形状管「不许有枚举」，数字管「散文回潮」 |
| 数字帽 | AGENTS 2000 / CHARTER 1000 / WORK 4900 / INDEX 12000 = **19900 ≤ 30000** | 每项实测（1416/784/4784/~9350）+ 余量，不变量恢复 |
| 退役维度 | `ghosts` / `orphans` / `misrouted` 三维度**删除**，由构建期 **loud-fail** 取代 | 派生投影不存在漂移；但扫描解析失败必须报错，不得静默跳过 |
| 已有先例 | MCP `hub_index` 早已按目录扫描（不读 INDEX 文本）；`_CorpusIndex` 用目录签名失效 | 机器路径单源化已被验证可行 |

## Global Constraints

- 解释器一律 `.venv\Scripts\python.exe`（系统 python 缺 jieba → 9 个检索测试静默跳过＝假绿）
- 测试在 `hub-engine/` 下跑：`cd hub-engine && ..\.venv\Scripts\python.exe -m pytest ...`
- 每任务收尾：相关 pytest + `ruff check` + `ruff format --check` 全绿；新增 .md 必须 **markdownlint 0 违规**（不得加入 `.markdownlintignore` 基线）
- 编码：UTF-8 无 BOM（md/py），过 `check_encoding.py`
- 中枢仓是嵌套仓：`git -C AgentMemoryHub`；跨仓改动**两仓提交相邻**（message 互引），保证 `git bisect` 不停在中间态
- 写中枢必须走单写者锁 `_WriteLock`（`from sync import _WriteLock`），与 ingest 互斥；渲染器写盘在锁内
- **先证红再改**：每条门禁/行为变更先写失败用例（负样本）再改实现
- 夹具漂移警告：`INDEX*` 相关夹具的期望值会随改造漂移，改前先 grep 引用（`rg "INDEX" hub-engine/tests`）
- 本计划分两阶段交付：Task 1 可立即独立上线（消红）；Task 2–4 零行为变化；Task 5 是唯一可见变更

## 时点与应急

余量 77 字符，下一次 star-distill（约 4–5 卡/天，每卡约 105 字符）即触发中枢仓 pre-commit exit 5。两条路径：

- **推荐**：Task 1 今天上线（消红），Task 2–5 连续上线（预计 1–2 个工作日）。期间若先撞帽，做过渡动作——把 blueprints 分区手工迁至 `INDEX-blueprints.md`，并按 Task 4 的口径同步读方（它是 Task 4/5 的真子集，不会返工）。
- **不推荐**：临时抬帽至 23016 并改不变量测试。这需要维护者显式授权，且等于把结构病记为资源配置问题。

---

### Task 1: 不变量归位（还 09-27 的债）

**Files:**

- Modify: `hub-engine/scripts/startup_budget.py`
- Modify: `hub-engine/tests/test_startup_budget.py`

**Interfaces:**

- Produces: `LIMITS` 帽值口径（AGENTS 2000 / CHARTER 1000 / WORK 4900 / INDEX 22000，合计 29900 ≤ 30000）
- Produces: `startup_budget.check_limits_invariant() -> list[str]`（分项帽之和超总帽即违规）

**Covers:** C2（形状/不变量类判据的第一步：让不变量由脚本自身看守，而不是只靠 pytest）

- [ ] **Step 1: 复现红灯**

```powershell
cd hub-engine; ..\.venv\Scripts\python.exe -m pytest tests/test_startup_budget.py -q
```

Expected: `2 failed, 9 passed`（`test_check_passes_at_exact_caps` / `test_check_fails_total_over_30k`，断言消息 `启动链总和 31000 > 30000`）

- [ ] **Step 2: 收紧另三项帽并写不变量断言**

```python
# hub-engine/scripts/startup_budget.py
# 帽值口径：分项帽之和 ≤ TOTAL_LIMIT（不变量），且每项 ≥ 实测值 + 余量。
LIMITS: list[tuple[str, str, int]] = [
    ("AGENTS.md", "AGENTS.md", 2_000),   # 实测 1416
    ("CHARTER.md", "CHARTER.md", 1_000),  # 实测 784
    ("WORK.md", "WORK.md", 4_900),        # 实测 4784
    ("INDEX.md", "AgentMemoryHub/INDEX.md", 22_000),  # Task 5 收至 12_000
]


def check_limits_invariant() -> list[str]:
    """分项帽之和 ≤ TOTAL_LIMIT。数字帽不变量必须由脚本自身看守。

    回归背景：2026-09-27 抬 INDEX 帽 20k→22k 时合计变成 31_000 > 30_000，
    该断言当时只写在 pytest 里 → pre-commit 照常放行，红灯存活 4 天。
    """
    total = sum(c for _n, _r, c in LIMITS)
    if total > TOTAL_LIMIT:
        return [f"分项帽之和 {total} > 总帽 {TOTAL_LIMIT}（帽值口径违规）"]
    return []
```

并在 `main()` 里把 `errs += check_limits_invariant()` 放在 `check(texts)` 之前。

- [ ] **Step 3: 补负样本测试**

```python
# hub-engine/tests/test_startup_budget.py
def test_limits_invariant_is_enforced_by_script(monkeypatch):
    """抬帽破不变量必须被脚本自己打红（不能只靠 pytest 看守）"""
    from scripts import startup_budget as sb

    bad = [("INDEX.md", "AgentMemoryHub/INDEX.md", sb.TOTAL_LIMIT)]  # 与其余三项相加必超
    monkeypatch.setattr(sb, "LIMITS", bad)
    assert sb.check_limits_invariant()
```

- [ ] **Step 4: 验证**

```powershell
cd hub-engine
..\.venv\Scripts\python.exe -m pytest tests/test_startup_budget.py -q
..\.venv\Scripts\python.exe -m scripts.startup_budget
```

Expected: pytest 全绿；`startup_budget` 输出 `[OK] INDEX.md: 21923 (cap 22000)`、`[TOTAL] 28907 / 30000`、`PASS`，退出码 0

---

### Task 2: `tools/hub_registry.py`（纯扫描 + loud-fail）

**Files:**

- Create: `hub-engine/tools/hub_registry.py`
- Create: `hub-engine/tests/test_hub_registry.py`

**Interfaces:**

- Produces: `CardMeta`（`slug` / `rel_path` / `dir` / `type` / `status` / `tags` / `title` / `summary` / `updated` / `reuse_count`）——**不含 T1 字段**：T1 事实目前只写在卡正文散文里（无 frontmatter 字段），不臆造（字段化见 Task 3b）
- Produces: `RegistryError(Exception)`；`scan(hub: Path) -> list[CardMeta]`（解析/校验失败即抛，消息含文件名清单）
- Produces: `by_dir(cards) -> dict[str, list[CardMeta]]`、`example_slugs(cards, dir, n=3) -> list[str]`（按 `reuse_count` 降序、`updated` 降序取前 n）
- Consumes: `common.frontmatter.try_read_card` / `validate_card`、`scripts.post_ingest_hook.extract_summary`

- [ ] **Step 1: 写失败测试（先证红）**

```python
# hub-engine/tests/test_hub_registry.py
def test_scan_fails_loud_on_broken_card(tmp_path):
    """权威区坏卡必须抛错并列名，不得静默跳过。

    回归背景：切到派生层后 ghost/orphan 维度退役，若扫描静默丢弃坏卡，
    「卡消失」将无任何门禁可见（今天靠 lint 的 invalid 计数兜住）。
    """
    hub = tmp_path / "AgentMemoryHub"
    (hub / "rules").mkdir(parents=True)
    (hub / "rules" / "good.md").write_text(GOOD_CARD, encoding="utf-8")
    (hub / "rules" / "broken.md").write_text("no frontmatter here", encoding="utf-8")

    with pytest.raises(RegistryError) as ei:
        scan(hub)
    assert "broken.md" in str(ei.value)
```

- [ ] **Step 2: 实现**

```python
# hub-engine/tools/hub_registry.py
class RegistryError(Exception):
    """派生层构建失败：解析不了的权威区卡必须显式报错（loud-fail）。"""


def scan(hub: Path) -> list[CardMeta]:
    """扫描权威区 + experience → 卡片元数据（纯函数，不写盘、不缓存）。"""
```

`scan` 规则：目录集合 = `rules` / `methodology` / `longterm` / `projects` / `blueprints` / `experience`；跳过 `log.md`、`lint-report-*.md`、`INDEX*.md`；`try_read_card` 返回 None 或 `validate_card` 非空 → 收集后一次性抛 `RegistryError`（列出全部文件名，不只第一个）。

- [ ] **Step 3: 记录性能与对照**

```powershell
cd hub-engine
..\.venv\Scripts\python.exe -c "import sys,time,pathlib; sys.path.insert(0,'.'); from tools.hub_registry import scan; t=time.perf_counter(); c=scan(pathlib.Path('../AgentMemoryHub')); print(len(c), f'{(time.perf_counter()-t)*1000:.0f}ms')"
```

Expected: 卡数与 `rules/methodology/longterm/projects/blueprints/experience` 下 .md 文件数一致（当前 501），耗时与基线 452ms 同量级

---

### Task 3: `scripts/render_index.py`（`--check` / `--write`）

**Files:**

- Create: `hub-engine/scripts/render_index.py`
- Create: `hub-engine/tests/test_render_index.py`

**Interfaces:**

- Produces: `render_l0(cards, hub) -> str`、`render_full(cards, hub) -> str`
- Produces: CLI `--check`（不一致 → 退出码 3）、`--write`（在 `_WriteLock` 内写盘）、`--root`
- Produces: `REQUIRED_FILES = ("INDEX.md", "INDEX-full.md")`

- [ ] **Step 1: 零信息损失对照（**一次性证明**，Task 5 前必须跑过）**

```powershell
# 断言：新渲染的全量行集合 == 现 INDEX.md 的行集合（除分区头/说明行）
cd hub-engine
..\.venv\Scripts\python.exe -c "
import sys,re,pathlib; sys.path.insert(0,'.')
from tools.hub_registry import scan
from scripts.render_index import render_full
hub=pathlib.Path('../AgentMemoryHub')
old={l.strip() for l in (hub/'INDEX.md').read_text(encoding='utf-8-sig').splitlines() if re.match(r'^- ',l)}
new={l.strip() for l in render_full(scan(hub), hub).splitlines() if re.match(r'^- ',l)}
print('old',len(old),'new',len(new),'missing',sorted(old-new)[:5],'extra',sorted(new-old)[:5])
"
```

Expected: `missing []`、`extra []`（行内容逐字相等；顺序固定按 `dir + slug`）。**若 missing 非空 → 禁止继续 Task 5**，先补全 `scan`/渲染逻辑。

- [ ] **Step 2: `--check` 语义（本步不动 L0）**

```python
# hub-engine/scripts/render_index.py
def main(argv: list[str] | None = None) -> int:
    """--check：产物与磁盘不一致 → 3；--write：渲染落盘（锁内）。"""
```

Task 3 结束时 `--check` 只对 `INDEX-full.md`（新文件）生效；`INDEX.md` 的切换在 Task 5。

- [ ] **Step 3: 测试**

```python
def test_check_detects_hand_edit(tmp_path):
    """手改渲染产物必须被打红（模型同 ruff format --check）"""
```

Expected: 手工改一行 → `--check` 退出码 3，`--write` 后退出码 0 且内容还原

---

### Task 3b: 描述质量对齐（**Task 3 实测新增的硬前置**）

Task 3 执行后对真实中枢跑 `--report`，暴露出一个原计划未预见的缺口：**渲染描述会低于现有手写描述**。实测（2026-10-01）：

| 项 | 数量 | 含义 |
| --- | --- | --- |
| 卡片数 / 现有登记 | 501 / 491 | `scan` 501 卡 438ms，空摘要 0 |
| 幽灵登记 | 0 | 现有索引无悬空条目 |
| 未登记（渲染会补上） | 10 | 真实漂移（含 `bge-small-zh-sqlite-vector-search` 等） |
| 摘要漂移·注释型 | 9 | 人工追加的 `status=…｜T1 09-xx ✅` 后缀，frontmatter 里无对应字段 |
| 摘要漂移·陈旧型 | 42 | INDEX 行未随卡重建；其中 **24 条渲染结果明显更差** |

根因：blueprint 卡正文首行常是 `- 仓库：gh-…` 列表行或结构化信息（★/判级/status），而 `extract_summary` 取「首个实质行」→ 渲染出 `- 仓库：gh-biopython-biopython —…` 这类劣于人工描述的结果。**若直接切 L0，等于把 24 行降级 + 丢 9 条注释**（09-23 机械截断的教训重演）。

**Files:**

- Modify: `hub-engine/scripts/post_ingest_hook.py`（`_SKIP_PREFIXES` 与摘要取样）
- Modify: `hub-engine/tools/hub_registry.py`（注解派生）
- Modify: 9 张带注释的卡 frontmatter + 24 张需校对的卡
- Modify: `hub-engine/scripts/render_index.py`（渲染注解列）

- [ ] **Step 1: 先证红**：以 `-` 开头的列表行不得当摘要

```python
# tests/test_index_desc_quality.py（已有文件，扩充）
def test_summary_skips_list_lines(tmp_path):
    """正文首行是 `- 仓库：gh-xxx` 时不得把它当摘要（实测 biopython 卡）"""
```

- [ ] **Step 2: T1/status 注释字段化**：卡 frontmatter 增 `t1_verified: 'YYYY-MM-DD'`（可选字段，不填则无注解）；渲染时由卡拼出注解列
- [ ] **Step 3: 对照测试**：9 张卡拼出的注解必须与旧后缀**逐字相等**（迁移零漂移）
- [ ] **Step 4: 24 条人工校对**（一次性），校对后由 `--check` 冻结
- [ ] **Step 5: 复跑 `--report`**，**硬判据：注释型 = 0 且「渲染更差」= 0**；未登记 10 条属真实漂移（渲染补上）
- [ ] **Step 6: 改 Hermes T1 回写口径**：由「改 INDEX 行」改为「写卡 frontmatter 字段」，否则下次回写又会把注解写回索引（新漂移源）

> **门禁**：Task 3b 未达标前**不得执行 Task 5**（否则 L0 定形会伴随信息降级）。

**执行结果（2026-10-01）：Step 1–5 已完成，Step 6 待办**

- Step 1：`_SKIP_PREFIXES` 加列表项前缀（先证红：`test_extract_summary_skips_list_lines`，红样本即 biopython 卡）
- Step 2/3：新增两个**卡自有**字段：`index_desc`（覆盖描述列）/ `index_note`（追加注解，**逐字**不 strip）
- 一次性迁移：`scripts/migrate_index_fields.py`（默认 dry-run）→ **9 张 `index_note` + 60 张 `index_desc`**
- 硬判据：渲染 vs 现状 **491/491 条逐字一致**（注释型 0 / 陈旧型 0）；幽灵 0；未登记 10（真实漂移，渲染会补上）
- 迁移前已备份规则卡；顺带修了 `scripts/backup-rules.py` 的崩溃 bug（循环变量遮蔽文件句柄 ⇒ 纪律脚本一直不可用）
- **遗留（非阻塞）**：**142 条描述质量待校对**（硬截断 `…` / 仅仓库 id / 超 40 字；迁移前既有，不是本次引入）。复现命令：`python -m scripts.migrate_index_fields --proofread`

---

### Task 4: 消费方切源（零行为变化）

> **执行结果（2026-10-01 已完成）**：新增 `hub-engine/common/index_files.py`
> （`KNOWN_INDEX_FILES` + 自动发现 `INDEX*.md` + `all_index_text`），四处读方统一走它：
> `tools/lint.py`（orphans/ghosts）、`scripts/audit_index.py`（含 `INDEX-full.md`）、
> `scripts/fix_orphans.py`、`scripts/index_locatability_bench.py`；
> 写方（`post_ingest_hook`）改为**渲染产物不得手写**（`RENDERED_INDEX_FILES` ⇒ 调 `render_index`），
> `regen_index_desc.py` 对渲染产物直接**拒绕**并指向 `render_index`。
> 新増守护测试：新分册无需改代码即被审计。

**Files:**

- Modify: `hub-engine/tools/lint.py`（`find_orphans` / `find_index_ghosts` 退役；新增 `registry_ok` / `invalid` 口径）
- Modify: `hub-engine/scripts/audit_index.py`（`INDEX_FILES_AUDITED` → 读 `INDEX-full.md`；删除 `_check_misrouted`）
- Modify: `hub-engine/scripts/fix_orphans.py`（`INDEX_FILES` → `INDEX-full.md`；写目标改为渲染器）
- Modify: `hub-engine/scripts/post_ingest_hook.py`（不再手改 INDEX 文本，改为写卡后调 `render_index --write`）
- Modify: `hub-engine/scripts/regen_index_desc.py`（能力并入 `render_l0` / `render_full`，保留 CLI 兼容期）
- Modify: `hub-engine/scripts/index_locatability_bench.py`（`load_index` 读 `INDEX-full.md`）
- Modify: `hub-engine/scripts/patrol/steps.py`（lint 报告字段名同步）
- Modify: `hub-engine/tests/test_lint.py`、`test_lint_report.py`、`test_audit_index.py`、`test_fix_orphans.py`、`test_post_ingest_hook.py`、`test_index_consistency.py`、`test_platform_and_bench_scripts.py`

**Interfaces:**

- Consumes: `tools.hub_registry.scan`、`scripts.render_index.render_full`
- Produces: `lint(root)` 报告字段变更：删除 `ghosts` / `orphans`，新增 `invalid_names: list[str]`（坏卡文件名，来自 `RegistryError`）

- [ ] **Step 1: 对照测试（切换前后结果集相同）**

在切换前用当前实现落一份基线：

```powershell
cd hub-engine
..\.venv\Scripts\python.exe -c "import sys,json,pathlib; sys.path.insert(0,'.'); from tools.lint import lint; r=lint(pathlib.Path('../AgentMemoryHub')); print(json.dumps({k:(len(v) if isinstance(v,list) else v) for k,v in r.items()}, ensure_ascii=False))"
```

Expected（当前基线）: `ghosts` / `orphans` 计数记入本任务说明；切换后必须证明「旧口径报出的每一张卡，新口径都能解释」（坏卡进 `invalid_names`，正常卡不报）

- [ ] **Step 2: 写方切源（防 09-23 复发）**

`post_ingest_hook` / `fix_orphans` **不得**再向根 INDEX 追加登记行——否则 L0 定形当天就被写回枚举（09-23 experience 拆分踩过同一坑）。改为「卡落盘 → `render_index --write`」。

- [ ] **Step 3: 验证**

```powershell
cd hub-engine
..\.venv\Scripts\python.exe -m pytest tests/test_lint.py tests/test_lint_report.py tests/test_audit_index.py tests/test_fix_orphans.py tests/test_post_ingest_hook.py tests/test_index_consistency.py tests/test_platform_and_bench_scripts.py -q
..\.venv\Scripts\python.exe -m scripts.render_index --check
```

Expected: 全绿；`--check` 退出码 0

---

### Task 5: L0 定形（唯一可见变更，两仓成对提交）

**Files:**

- Modify: `AgentMemoryHub/INDEX.md`（→ 定形能力图）
- Create: `AgentMemoryHub/INDEX-full.md`（全量分区清单，渲染产物）
- Modify: `hub-engine/scripts/startup_budget.py`（INDEX 帽 22000 → 12000）
- Create: `hub-engine/tests/test_l0_shape.py`
- Modify: `AGENTS.md`（启动顺序第 4 条措辞：INDEX 目录版 → 「INDEX 能力图；全量清单 INDEX-full.md（L2）」）
- Modify: `WORK.md`（预算分项帽口径 + 真实测试状态）

**Interfaces:**

- Produces: `startup_budget.L0_ENTRY_RE` —— **直接复用** `audit_index.INDEX_ENTRY_RE`（唯一权威正则，字符集不含 `/`，因此目录图例行天然不匹配）；**不新建第二份正则**
- Produces: `startup_budget.check_l0_shape(text: str) -> list[str]`

> **执行结果（2026-10-01 已完成）**：
> `render_l0()` 已实现（使用约定 3 条 + 能力图每目录 1 行 + 沉淀通道）；
> `write()` 一次渲染 L0 + 全量两产物，`--check` 两产物都查；
> 映射翻转为 `rules/methodology/longterm/projects/blueprints → INDEX-full.md`。
> 实测：**INDEX.md 21923 → 1176 字符**（帽降 22000 → 12000）；L0 合计 **8524/30000**；
> `check_l0_shape` 在真实中枢为 0 违规、对 per-card 行可打红；
> 测试总数 **733 passed / 4 skipped / 0 failed**（新增 `tests/test_l0_shape.py`：C1 解耦 + C2 形状可证红）。

- [ ] **Step 1: 形状断言先证红**（前置：Task 3b 的判据已达标）

```python
# hub-engine/tests/test_l0_shape.py
def test_shape_gate_blocks_per_card_line():
    """L0 里出现 per-card 登记行必须被打红（这是替代批帽的主门禁）"""
    from scripts.startup_budget import check_l0_shape

    assert check_l0_shape("- rules-routing-table    RULES_ROUTING — 规则路由表\n"), "应报 per-card 行"


def test_adding_cards_does_not_change_l0(tmp_path):
    """C1：卡数增长不得改变 L0 字符数（±5%）"""
```

- [ ] **Step 2: 渲染 L0 能力图（模板固定，行数恒定）**

```markdown
# 中枢索引（L0 能力图）

全量分区清单见 `INDEX-full.md`（L2 按需）；语义检索走 `engine.py retrieve` / MCP hub_search。

## 能力图

- rules/        35 张｜示例：rules-routing-table · memory-hub-query-first · gh-star-repo-filter-rule｜查：retrieve / hub_search
- methodology/  62 张｜…
- blueprints/   152 张｜…
- experience/   225 张 → 详见 INDEX-experience.md（L2）
```

固定约束：每目录 **1 行**；示例 slug ≤3 个且内联（不写成 `- slug  描述` 行，避免与登记行正则冲突）；目录数量与名称由 `scan` 注入，数量数字由 `scan` 注入但行数不随卡数变化。

- [ ] **Step 3: 帽与门禁落地**

```python
# hub-engine/scripts/startup_budget.py
("INDEX.md", "AgentMemoryHub/INDEX.md", 12_000),
```

`main()` 中对 INDEX 文本额外调用 `check_l0_shape()`；`render_index --check` 纳入 pre-commit（Task 7）。

- [ ] **Step 4: 两仓成对提交**

```powershell
git -C AgentMemoryHub add INDEX.md INDEX-full.md
git -C AgentMemoryHub commit -m "refactor(index): L0 定形（能力图，per-card 行=0）+ 全量清单迁 INDEX-full.md（L2）"
git add hub-engine AGENTS.md WORK.md
git commit -m "feat(budget): L0 形状门禁取代批帽——INDEX 帽 22k→12k；对应中枢仓 <sha>"
```

- [ ] **Step 5: 验证**

```powershell
cd hub-engine
..\.venv\Scripts\python.exe -m scripts.startup_budget
..\.venv\Scripts\python.exe -m pytest tests/test_l0_shape.py tests/test_startup_budget.py -q
```

Expected: `[OK] INDEX.md: ~9350 (cap 12000)`、`[TOTAL] ~16300 / 30000`、`PASS`；pytest 全绿

---

### Task 6: L1 派生（消掉同一个病在 L1 的复发）

> **执行结果（2026-10-01 已完成）**：`l1_cards(root)` 由卡 frontmatter `l1_tier` 派生
> （7 张卡：code 3 / hub 3 / sync 2，其中双平台一致性卡同属 hub+sync）；
> `check_l1_shape` 单型 ≤3 张（形状断言已进 `startup_budget.check_tiers`）；
> 迁移脚本 `scripts/migrate_l1_tier.py`（dry-run 默认）+ 对照测试
> 「派生集合 == 手写基准快照」（迁移零漂移证明）；AGENTS.md 路由表改为派生顺序 + 声明来源。
> 字段名用 `l1_tier` 而非 `tier`：后者已被卡用于重要度（task/iron）。

**Files:**

- Modify: `hub-engine/tools/task_tier.py`（`L1_CARDS` 常量 → `l1_cards(root)`）
- Create: `hub-engine/scripts/migrate_l1_tier.py`（一次性迁移）
- Modify: 7 张 rules 卡 frontmatter（`l1_tier`）
- Modify: `hub-engine/tests/test_task_tier.py`、`hub-engine/scripts/startup_budget.py`、`AGENTS.md`

**Interfaces:**

- Produces: `task_tier.l1_cards(root: Path | None) -> dict[Tier, list[str]]`
- Produces: `task_tier.check_l1_shape(tier_cards) -> list[str]`、`L1_MAX_CARDS_PER_TIER = 3`

- [ ] **Step 1: 对照测试（迁移正确性证明）**

```python
def test_derived_l1_equals_legacy_map():
    """派生集合必须与旧手写清单集合相等（迁移零漂移）"""
    assert l1_cards() == LEGACY_SNAPSHOT  # 集合口径
```

- [ ] **Step 2: 迁移卡 frontmatter 并切换实现**；`startup_budget.measure_tiers` 改调 `l1_cards()`
- [ ] **Step 3: 形状断言**：单型 >3 张 → 违规（防「顺手再加一张」复发成 L1 ratchet）
- [ ] **Step 4: 验证**

```powershell
cd hub-engine
..\.venv\Scripts\python.exe -m pytest tests/test_task_tier.py tests/test_startup_budget.py -q
..\.venv\Scripts\python.exe -m scripts.startup_budget
```

Expected: L1 四行仍在 15K 内；pytest 全绿

---

### Task 7: 门禁接线（提交时 / 巡检 / 夜间）

**Files:**

- Modify: `hub-engine/scripts/pre-commit`（V1.3 → V1.4：+ 渲染可复现校验，退出码 6）
- Modify: `hub-engine/scripts/pre-commit-hub-cards`（V1.1 → V1.2：+ 无条件渲染校验）
- Modify: `hub-engine/scripts/patrol/steps.py`（+ `_step_render_check`）
- Modify: `hub-engine/scripts/patrol_runner.py`、`hub-engine/scripts/patrol/__init__.py`（注册 + `__all__`）
- Modify: `hub-engine/tests/test_patrol_steps.py`（`_STEP_CALLS` + 24 → 25 步契约）
- Modify: `scripts/nightly_consolidate.cmd`（+ 2.5/4 render-index）

- [ ] **Step 1: pre-commit 加 `--check`**
- [ ] **Step 2: patrol 加步**，并同步「24 步」契约测试与 WORK.md 描述
- [ ] **Step 3: 夜间渲染**，保证三份产物次日晨报可读
- [ ] **Step 4: 验证**

> **执行结果（2026-10-01 已完成）**：`_step_render_check` 上巡检（**24 → 25 步**，阶段 2 紧跟 startup_budget），
> 契约测试同步（`_STEP_CALLS` + 步数断言）；`pre-commit-hub-cards` 升 **V1.2**：
> 渲染一致性检查**无条件跑**（INDEX\*.md 不在卡片目录里，若挂在「有卡片 staged」分支下，
> 单独提交一个手改的 INDEX-full.md 就会绕过它），已**先证红**：手改 INDEX-full.md → 钩子 exit 6 阻断。
> 端到端验收：`patrol_runner` **总体退出码 0（全绿）**，`lint orphans=0 ghosts=0`、
> `startup_budget L0 8708/30000`、`render_check 403ms ✅`、`pytest 755 passed`；
> 夜间链已补 2.5/4 `render-index`（best-effort，每日巡检 render_check 兜底）。

---

### Task 8: 判据 C1 / C2 / C3 可执行化与存档

**Files:**

- Modify: `hub-engine/tests/test_l0_shape.py`、`hub-engine/tests/test_hub_registry.py`
- Create: `docs/compose/metrics/2026-10-01-l0-shape-baseline.md`（改造前后对照留档）

- [ ] **Step 1: C1（解耦）**：临时 hub + 50 张合成卡 → `render_l0` 字符数不变（±5%）且形状断言绿
- [ ] **Step 2: C2（零批帽）**：`check_l0_shape` 负样本可打红 + `check_limits_invariant` 可打红；记录「帽值人工调整次数 = 0」的起始日期
- [ ] **Step 3: C3（drift 维度退役 + loud-fail）**：`scan` 坏卡抛错且列名；lint 报告不再含 `ghosts` / `orphans`
- [ ] **Step 4: 留档对照表**

| 指标 | 改造前（2026-10-01） | 改造后 | 判据 | 状态 |
| --- | --- | --- | --- | --- |
| INDEX.md 字符 / 帽 | 21923 / 22000 | **1176 / 12000** | 余量 ≥ 20% | ✅ |
| L0 合计 / 总帽 | 28907 / 30000 | **8539 / 30000** | — | ✅ |
| 卡数 +50 时 L0 变化 | +约 5250 字符 | **0**（行数不变） | C1 | ✅ `test_c1_l0_line_count_decoupled_from_card_count` |
| 帽值人工调整 | 09-23、09-27 各一次 | **0**（形状门禁） | C2 | ✅ `check_l0_shape` 可证红 + `check_limits_invariant` 进脚本 |
| drift 维度数 | 3（ghost/orphan/misrouted） | **3 保留但覆盖面补全** | C3 | ⚠️ 见下（刻意偏差） |
| 卡数 / 扫描耗时 | 501 / 452ms | 501 / **438ms**（render_check 431ms） | 性能不退化 | ✅ |

**C3 偏差（刻意保留维度，不删）**：计划原写「删 ghost/orphan/misrouted 三维度，由构建期
loud-fail 取代」。实施改为**两者都要**：

- `loud-fail`（`RegistryError` 列全部坏卡）已落地——它能抓「卡坏了」，但抓不到「条目住错文件」；
- 三个维度改为读**全部分册**（`common/index_files`），新增分册零代码成本——删除它们会让
  「条目写成 HTML 列表 / 住错分册」重新变成无人看守的静默漂移。

结论：**保留并补全**比删除更安全（零损失 + 覆盖更宽），已在提交 `9ef5a35` 的实现中标注。

- [ ] **Step 5: 全量验收**

```powershell
cd hub-engine
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m scripts.startup_budget
..\.venv\Scripts\python.exe -m scripts.render_index --check
..\.venv\Scripts\python.exe -m scripts.recall_regression
```

Expected: pytest **0 failed**（当前基线 687 passed / 2 failed / 4 skipped，Task 1 后应转 689 passed / 0 failed）、预算 PASS、渲染一致、召回不降（word @5 100% / @1 79%）

---

## 回滚

- 每个 Task 是独立提交，单独 revert 即可；卡文件正文零改动（唯一例外：Task 6 给 8 张 rules 卡加 `l1_tier` 字段，revert 后卡片回到无该字段状态，`l1_cards` 需回退为常量）
- Task 5 必须**两仓成对回滚**（中枢仓 `INDEX.md` + 外层仓 `startup_budget.py` 帽值）；`INDEX-full.md` 删除即可，无数据损失
- 回滚后旧口径（ghost/orphan/misrouted + 大 INDEX）需按 Task 4/5 的反向操作恢复；因此 Task 4 的删除动作放在**最后一个提交**更安全（若时间不紧，建议 Task 4 拆成 4a 切源 / 4b 删维度）

## 影响的测试清单

| 测试文件 | 影响 |
| --- | --- |
| `tests/test_startup_budget.py` | **当前 2 红**；Task 1 转绿，Task 5/6 加形状与不变用例 |
| `tests/test_l0_shape.py`（新） | C1/C2 判据 |
| `tests/test_hub_registry.py`（新） | C3 loud-fail |
| `tests/test_render_index.py`（新） | `--check` / `--write` / 手改打红 |
| `tests/test_lint.py`、`test_lint_report.py` | 报告字段 `ghosts`/`orphans` → `invalid_names`；`auto_fix_lint` 口径 |
| `tests/test_audit_index.py` | `INDEX_FILES_AUDITED`、`misrouted` 维度退役 |
| `tests/test_fix_orphans.py`、`test_fix_index_registry.py` | 写入目标 → `INDEX-full.md` / 渲染器 |
| `tests/test_index_consistency.py` | `INDEX_FILE_FOR_DIR` 扩到分册；`blueprints` 断言变更 |
| `tests/test_post_ingest_hook.py` | 不再手改 INDEX 文本（改为触发渲染） |
| `tests/test_platform_and_bench_scripts.py` | bench 读 `INDEX-full.md` |
| `tests/test_patrol_steps.py`、`test_patrol_cli.py` | 巡检 24 → 25 步契约 |
| `tests/test_task_tier.py` | `L1_CARDS` 常量 → `l1_cards()` 函数（已乘） |
| `tests/test_index_limits.py`（新） | 描述上限两侧同源 |
| `tests/test_set_index_meta.py`（新） | 回写入口 + 安全写盘（BOM/换行/YAML） |
| `tests/test_slim_index.py`、`tests/test_index_desc_quality.py` | `slim_index` 使命结束，**待裁**（见下） |

## 改造后追加完成项（超出原计划，2026-10-01）

| 项 | 为何加 | 证据 |
| --- | --- | --- |
| 描述质量 142 → 0 | Task 3b 遗留的「描述读不懂」直接损害蓝图层选型 | `proofread_index_desc`：15 自动（注解拆分/H1 替换）+ 3 人工 |
| 描述上限单一来源 `common/index_limits`（250/800） | 真病因：派生侧按 40 硬切、校验侧允许 250/800 ⇒ **门禁不会红** | `tests/test_index_limits.py` 铉死两侧同源 |
| `INDEX-experience.md` 纳入渲染 | 它是**最后一个手写维护的索引**，实测 7 条陈旧重复登记 | audit 从 8 项 → 1 项 |
| `audit_index` 合并全分册 | 枚举迁出根 INDEX 后，278 条被误报「未登记」 | 假阳性洪流消失 |
| `set_index_meta` + `card_fields` | T1/状态回写需要「一条命令」代替手改索引 | `tests/test_set_index_meta.py`（13 例） |
| L1 派生（Task 6） | 手写清单 + 固定帽 ≈ L0 同病 | `l1_cards()` + 单型 ≤3 形状断言 |
| 门禁 V1.4 / hub V1.2 + 夜间 2.5/4 | 产物与卡必须可验证为一致；夜间 ingest 后重渲 | 两钩子均**先证红**（exit 6） |

**验收基线（2026-10-01 全链路巡检）**：`lint orphans=0 ghosts=0`、`L0 8708/30000`、
`render_check 403ms ✅`、`pytest 755 passed / 4 skipped / 0 failed`、**总体退出码 0（全绿）**。

**已知遗留（1 项，low）**：`20260908-170346-mavis-v1.0-接入范式落地测试` 描述 8 字符
——那卡本身正文就只有「接入范式落地测试 / 测试内容」（**thin card**，不是描述问题）；
补内容或归档需维护者裁定，不得臆造。

## 附带裁定项（本计划记录，不擅自删除）

- `scripts/slim_index.py` + `tests/test_slim_index.py`：机械截断已被 09-23 裁定为有害，L0 定形后无用途 → 建议归档（零引用 ≠ 死代码，删除前逐个确认入口）
- `scripts/regen_index_desc.py`：能力并入渲染器后保留 CLI 兼容期一轮，再裁定退役
- `scripts/fix_index_registry.py`：同理（它的职责将完全由 `render_index --write` 覆盖）
- markdownlint 当前**未安装在 PATH**（`node_modules` 已删）：提交纯文档时门禁会「跳过不阻断」——建议本轮顺手恢复安装，否则新文档的 lint 约束形同建议

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 夹具漂移（WORK.md 已警示） | Task 4/5 前 `rg "INDEX" hub-engine/tests` 全量清点；逐个人工看而不是批量替换 |
| 写方漏改 → 枚举写回 L0（09-23 复发） | Task 4 Step 2 显式列为必改项；Task 5 后由 `render --check` 兜底打红 |
| 坏卡静默消失（新增失败模式） | Task 2 loud-fail + C3 判据；`invalid_names` 进 lint 报告 |
| 扫描耗时拖慢门禁（452ms） | Task 2 记录基线；若 pre-commit 感受明显，再引入 `_CorpusIndex` 同款目录签名缓存（本计划默认不引入） |
| 两仓提交错序导致 bisect 中间态 | Task 5 要求两仓提交相邻并互引 sha |
| 判据只写在文档里 | C1/C2/C3 全部落为 pytest 用例（Task 8），否则视为未完成 |
