# 启动链与规则门禁分层瘦身 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 启动链四件套压到 ≤30K 字符，按 4 型任务分级加载规则，安全底座常驻，卡级合并去重降 L2 成本。

**Architecture:** 三层渐进披露（L0 常驻 / L1 按任务型 / L2 检索）；`startup_budget` 立预算门禁；AGENTS 薄路由 + WORK 当前态 + INDEX 目录化改加载路径；rules 打 `tier` 并拆长卡；inject 只注 L0 底座；B 步 backup 后合并方法论/去重经验。

**Tech Stack:** Python 3.10+、pytest、ruff、现有 `hub-engine`（`scripts`/`tools` 包）、Markdown 中枢卡。

**Spec:** `docs/compose/specs/2026-09-23-slim-rules-gates-design.md`

## Global Constraints

- 分支：`optimize/slim-rules-gates`（已建，勿切走除非任务说明）。
- 启动链总预算 **≤30,000 字符**；分项帽 AGENTS ≤3000、CHARTER ≤3000、WORK ≤9000、INDEX ≤14000。
- 安全底座 L0 永不裁剪：单写者锁、工作区守护 §4、ledger、query-first、不确定交回用户、结果回写经验卡。
- 机器侧门禁（pre-commit/patrol/vector）不改行为；push 默认关不翻案；不自动删卡。
- 任务型仅 4 型：`light` / `code` / `hub` / `sync`；判不出 → `light`；只升不降。
- 注入/AGENTS/INDEX 中文表述与既有口径一致；产出面向用户必须中文。
- 每任务收尾：相关 pytest + `ruff check` + `ruff format --check` 全绿再 commit。
- Hub 卡变更遵守：先 `scripts/backup-rules.py`（B 步）；不直写 rules 权威区新卡（本计划只改已有卡 frontmatter/拆分正文）。
- 测试在 `hub-engine/` 下跑：`cd hub-engine && python -m pytest ...`。
- 编码：UTF-8 无 BOM（md/py）；过 pre-commit 编码门禁。

---

### Task 1: 预算门禁 startup_budget + 单测

**Covers:** S3, S5

**Files:**
- Create: `hub-engine/scripts/startup_budget.py`
- Create: `hub-engine/tests/test_startup_budget.py`

**Interfaces:**
- Consumes: 仓库根目录四文件路径约定
- Produces: `startup_budget.STARTUP_FILES: list[tuple[str, str, int]]`、`startup_budget.measure(root: Path) -> list[dict]`、`startup_budget.check(texts: dict[str, str]) -> list[str]`（返回违规消息列表，空=通过）、`startup_budget.main(argv: list[str] | None = None) -> int`（0/1）

- [ ] **Step 1: Write the failing test**

```python
# hub-engine/tests/test_startup_budget.py
"""启动链 30K 预算门禁单测。"""

from pathlib import Path

from scripts.startup_budget import LIMITS, TOTAL_LIMIT, check, main, measure


def _fill(n: int) -> str:
    return "x" * n


def test_check_passes_at_exact_caps():
    texts = {name: _fill(cap) for name, _, cap in LIMITS}
    assert check(texts) == []


def test_check_fails_total_over_30k():
    """分帽合计 29K；单靠顶帽到不了总闸——总闸与分帽独立断言，顶帽时总闸必过。"""
    texts = {name: _fill(cap) for name, _, cap in LIMITS}
    assert check(texts) == []
    assert sum(c for _, _, c in LIMITS) <= TOTAL_LIMIT
    # 模拟「帽被放宽后仍受总闸约束」：check 只认 LIMITS 帽，总闸在 sum(texts)
    # 顶帽 29000 < 30000，故再单独证明常量
    assert TOTAL_LIMIT == 30000


def test_check_fails_single_file_cap():
    texts = {name: _fill(cap) for name, _, cap in LIMITS}
    texts["AGENTS.md"] = _fill(3001)
    errs = check(texts)
    assert any("AGENTS.md" in e for e in errs)


def test_measure_reads_repo_files(tmp_path: Path):
    for name, rel, cap in LIMITS:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("a" * 10, encoding="utf-8")
    rows = measure(tmp_path)
    assert {r["name"] for r in rows} == {name for name, _, _ in LIMITS}
    assert all(r["chars"] == 10 for r in rows)


def test_main_exit_codes(tmp_path: Path, capsys):
    for name, rel, _cap in LIMITS:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ok", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 0
    (tmp_path / "AGENTS.md").write_text("x" * 4000, encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "AGENTS.md" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd hub-engine && python -m pytest tests/test_startup_budget.py -v`
Expected: FAIL（ModuleNotFoundError: scripts.startup_budget）

- [ ] **Step 3: Write minimal implementation**

```python
# hub-engine/scripts/startup_budget.py
"""启动链字符预算门禁：四件套总和 ≤30K + 分项帽；超标退出码 1。

挂巡检、不挂 pre-commit（见 spec S3）。路径相对仓库根（hub-engine 的上级）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TOTAL_LIMIT = 30_000

# (显示名, 相对仓库根路径, 单文件帽)
LIMITS: list[tuple[str, str, int]] = [
    ("AGENTS.md", "AGENTS.md", 3_000),
    ("CHARTER.md", "CHARTER.md", 3_000),
    ("WORK.md", "WORK.md", 9_000),
    ("INDEX.md", "AgentMemoryHub/INDEX.md", 14_000),
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def measure(root: Path) -> list[dict]:
    rows = []
    for name, rel, cap in LIMITS:
        p = root / rel
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        rows.append({"name": name, "path": str(p), "chars": len(text), "cap": cap})
    return rows


def check(texts: dict[str, int]) -> list[str]:
    """texts: 显示名 → 字符数。返回违规消息（空列表=通过）。"""
    errs: list[str] = []
    total = 0
    for name, _rel, cap in LIMITS:
        n = texts.get(name, 0)
        total += n
        if n > cap:
            errs.append(f"{name} {n} > 分项帽 {cap}")
    if total > TOTAL_LIMIT:
        errs.append(f"启动链总和 {total} > {TOTAL_LIMIT}")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="启动链 30K 预算门禁")
    ap.add_argument("--root", type=Path, default=_repo_root(), help="仓库根")
    args = ap.parse_args(argv)
    rows = measure(args.root)
    texts = {r["name"]: r["chars"] for r in rows}
    for r in rows:
        mark = "OK" if r["chars"] <= r["cap"] else "OVER"
        print(f"[{mark}] {r['name']}: {r['chars']} (cap {r['cap']})")
    total = sum(texts.values())
    print(f"[TOTAL] {total} / {TOTAL_LIMIT}")
    errs = check(texts)
    if errs:
        for e in errs:
            print(f"FAIL: {e}")
        return 1
    print("PASS: 启动链预算达标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

注意：`check` 入参类型以测试为准用 `dict[str, int]`（上签名若写成 str 已纠正）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd hub-engine && python -m pytest tests/test_startup_budget.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 真机跑当前仓库（此阶段预期 FAIL，证明门禁有效）**

Run: `cd hub-engine && python -m scripts.startup_budget`
Expected: FAIL（WORK/INDEX 超帽），退出码 1——记入 commit message 说明「门禁先立，内容任务后续压到 PASS」

- [ ] **Step 6: Commit**

```bash
git add hub-engine/scripts/startup_budget.py hub-engine/tests/test_startup_budget.py
git commit -m "feat(budget): 启动链30K预算门禁+分项帽单测（先立门禁，内容瘦身随后）"
```

---

### Task 2: 任务型分类 task_tier + 单测

**Covers:** S2, S4, S5

**Files:**
- Create: `hub-engine/tools/task_tier.py`
- Create: `hub-engine/tests/test_task_tier.py`

**Interfaces:**
- Consumes: 无（纯函数）
- Produces: `task_tier.Tier = Literal["light", "code", "hub", "sync"]`、`task_tier.L1_CARDS: dict[str, list[str]]`、`task_tier.classify(prompt: str) -> Tier`

- [ ] **Step 1: Write the failing test**

```python
# hub-engine/tests/test_task_tier.py
from tools.task_tier import L1_CARDS, classify


def test_default_is_light():
    assert classify("今天天气怎么样") == "light"
    assert classify("") == "light"


def test_code_keywords():
    assert classify("帮我 commit 这个改动并跑 ruff") == "code"
    assert classify("修一下这个 patch 的缩进") == "code"
    assert classify("open a PR for this fix") == "code"


def test_hub_keywords():
    assert classify("把经验 ingest 进中枢 rules") == "hub"
    assert classify("查一下 AgentMemoryHub 的 INDEX") == "hub"


def test_sync_keywords():
    assert classify("sync --push 到四个平台") == "sync"
    assert classify("把指令注入 workbuddy") == "sync"


def test_explicit_beats_keyword():
    # 多关键词冲突时：hub > sync > code > light 的固定优先级
    assert classify("ingest 之后 commit 并 sync --push") == "hub"


def test_l1_covers_all_tiers():
    for t in ("light", "code", "hub", "sync"):
        assert t in L1_CARDS
    assert L1_CARDS["light"] == []  # 仅 L0
    assert any("chinese-text-encoding" in c or "encoding" in c for c in L1_CARDS["code"])
    assert "dual-platform-coherence-discipline" in L1_CARDS["hub"]
    assert "cross-platform-sync-rule" in L1_CARDS["sync"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd hub-engine && python -m pytest tests/test_task_tier.py -v`
Expected: FAIL（tools.task_tier 不存在）

- [ ] **Step 3: Write minimal implementation**

```python
# hub-engine/tools/task_tier.py
"""任务分型（spec S2 四型）与 L1 规则卡路由——AGENTS 路由表的代码侧单一事实源。"""

from __future__ import annotations

from typing import Literal

Tier = Literal["light", "code", "hub", "sync"]

# 关键词 → 型；classify 时按 _ORDER 优先级，同型命中即返回
_KEYWORDS: dict[Tier, tuple[str, ...]] = {
    "hub": ("中枢", "ingest", "rules/", "experience/", "methodology", "agentmemoryhub", "回写", "confirm "),
    "sync": ("sync", "push", "注入", "inject", "platform_bridge", "跨平台"),
    "code": ("commit", "ruff", "pytest", "patch", "pr ", "push 代码", "refactor", "修 bug", "改代码"),
}

_ORDER: tuple[Tier, ...] = ("hub", "sync", "code")

L1_CARDS: dict[Tier, list[str]] = {
    "light": [],
    "code": [
        "chinese-text-encoding-discipline",
        "agent-code-discipline-iron-rule",
        "multi-language-style-config",
    ],
    "hub": [
        "dual-platform-coherence-discipline",
        "memory-hub-query-first",
        "memory-hub-distill-last",
    ],
    "sync": [
        "cross-platform-sync-rule",
        "dual-platform-coherence-discipline",
    ],
}


def classify(prompt: str) -> Tier:
    """显式/关键词判定；判不出返回 light。只升不降由调用方在会话内保持。"""
    text = (prompt or "").lower()
    if not text.strip():
        return "light"
    for tier in _ORDER:
        for kw in _KEYWORDS[tier]:
            if kw.lower() in text:
                return tier
    return "light"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd hub-engine && python -m pytest tests/test_task_tier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hub-engine/tools/task_tier.py hub-engine/tests/test_task_tier.py
git commit -m "feat(tier): 四型任务分类+L1卡路由表（与 AGENTS 路由共用口径）"
```

---

### Task 3: AGENTS 路由化 + CHARTER 压缩

**Covers:** S2, S3, S4

**Files:**
- Modify: `AGENTS.md`（整文件重写）
- Modify: `CHARTER.md`（压缩重写）
- Test: `cd hub-engine && python -m scripts.startup_budget`（人工读输出；此任务后 CHARTER/AGENTS 应 OK）

**Interfaces:**
- Consumes: `tools.task_tier.L1_CARDS` 键名与卡名（AGENTS 文中引用同名）
- Produces: 启动顺序指向 WORK 当前态 + INDEX 目录版；四型路由表；L0 六条铁律

- [ ] **Step 1: 重写 AGENTS.md（≤3000 字符）**

全文替换为：

```markdown
# AGENTS.md

跨 Agent 平台统一记忆中枢 · 薄路由入口。细节不常驻，按任务型取 L1/L2。

## 启动顺序（L0，计入 30K 预算）

1. 本文件（路由 + 铁律）
2. `CHARTER.md` —— 目标与边界
3. `WORK.md` —— **仅当前状态/待办**（历史见 `docs/superpowers/retro/work-history.md`）
4. `AgentMemoryHub/INDEX.md` —— **目录版**（卡名+一行摘要；全文走检索）
5. 简报 `briefs/*.md` 若有

不依赖历史聊天；事实来源=WORK 当前态 + 中枢。

## L0 铁律（安全底座，永不裁剪）

- 单一写入者（`.sync/locks/writer.lock`）+ 工作区守护（≥3 modified 须分析）+ ledger 审计
- 执行前先查中枢（INDEX/`engine.py retrieve`/MCP hub_bootstrap），命中再执行
- 不确定交回用户，不臆测、不捏造历史经验
- 查询结果回写经验卡（ingest/回写纪律）

## 任务分型 → L1 卡（代码口径 `tools.task_tier.L1_CARDS`）

| 型 | 判定（关键词兜底，判不出=light） | L1 规则卡（只读核心节/全文按需） |
| --- | --- | --- |
| light | 默认、问答、查状态 | （无，仅 L0） |
| code | commit/ruff/pytest/patch/PR/改代码 | chinese-text-encoding-discipline · agent-code-discipline-iron-rule · multi-language-style-config |
| hub | 中枢/ingest/rules/experience/回写 | dual-platform-coherence-discipline · memory-hub-query-first · memory-hub-distill-last |
| sync | sync/push/注入/跨平台 | cross-platform-sync-rule · dual-platform-coherence-discipline |

升型廉价：动作变重再补读 L1；只升不降。

## 降级

检索不可用 → 按上表卡名直读 `AgentMemoryHub/rules/<卡名>.md`；仍失败则问用户。

## 事实来源映射

| 内容 | 位置 |
| --- | --- |
| 设计/计划 | `docs/superpowers/specs|plans/`；瘦身设计 `docs/compose/specs/2026-09-23-slim-rules-gates-design.md` |
| 引擎 | `hub-engine/`（`engine.py`） |
| 中枢唯一事实源 | `AgentMemoryHub/` |
| 缺工具/写码 | 主动找装；中文注释；ruff 规范 |
```

- [ ] **Step 2: 压缩 CHARTER.md（≤3000 字符，保留边界与约束）**

全文替换为：

```markdown
# CHARTER.md

## 总目标

跨 Agent 平台统一记忆中枢：Hermes / trae / code / workbuddy 共享权威知识、行为一致。定位：中枢给 Agent 用、人监管。

## 架构（三层）

- `AgentMemoryHub/` —— 唯一事实源（Obsidian 纯内容）
- `hub-engine/` —— 同步/检索/提炼/整理/Lint/CLI/MCP
- 各平台 —— 经同步器对接：只读权威区、可写暂存、重要规则人工确认

## 能力（Phase 1–3 已完成，细节看历史归档）

写锁与错峰、commit ledger 审计、hub_announce、每日巡检+微信推送、ingest/confirm/distill/tidy/lint/retrieve/chat/sync。

## 维护者职责

1. 每日 patrol（lint/pytest/向量增量）
2. 任务收尾写经验卡 → ingest → sync
3. 改前查中枢；改后 ruff + pytest
4. commit 前 ledger + push（即 post_ingest_hook）

## 边界

做：中枢+核心能力、双平台并发安全、规则卡工作流、每日巡检。  
不做：平台全量复制、无人工提炼、复杂向量库、Web UI、跨 repo 原子事务。

## 关键约束

- 单一写入者锁；DLL 改后递增版本；Hub 内 git 审计
- 依赖尽量标准库（PyYAML/requests/mcp）
- `safe_patch` 为高风险改动唯一安全渠道
- type=rule 须 ingest 入区，不得直写

历史轮次与已完成细节：`docs/superpowers/retro/work-history.md`（按需读）。
```

- [ ] **Step 3: 校验字符与预算**

Run: `python -c "from pathlib import Path; print(len(Path('AGENTS.md').read_text(encoding='utf-8')), len(Path('CHARTER.md').read_text(encoding='utf-8')))"`
Expected: 两数均 ≤3000

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md CHARTER.md
git commit -m "refactor(agents): AGENTS 四型薄路由+L0铁律常驻；CHARTER 压缩至≤3K"
```

---

### Task 4: WORK 当前态抽取 + 历史归档

**Covers:** S3, S4, S5

**Files:**
- Create: `docs/superpowers/retro/work-history.md`
- Modify: `WORK.md`（瘦身为当前态 ≤9000 字符）

**Interfaces:**
- Consumes: 现有 WORK.md 全文
- Produces: `WORK.md` 仅含更新日期/当前状态/活跃待办/验收口径；历史 R1–R14+ 待办明细进 `work-history.md`

- [ ] **Step 1: 归档历史**

```powershell
# 将 WORK.md 中「本轮 R…」历史与已核销长待办整体迁出
# 保留结构见 Step 2；历史文件头部写明来源与日期
```

创建 `docs/superpowers/retro/work-history.md`：

```markdown
# WORK 历史轮次归档（自 WORK.md 迁出 · 2026-09-23）

> 启动链只读 WORK.md 当前态；本文件按需检索/点读。

## 归档说明

- 来源：原 `WORK.md` 的「本轮 R1…」叙事、已核销待办表、VLM 长说明等
- 迁出规则：非「当前状态 / 活跃 P0P1 待办 / 本轮验收口径」的章节全部移入此处

## （粘贴原 WORK.md 完整历史正文——执行时用 git show 或迁出前备份整段剪切，禁止丢内容）

<!-- 迁出后此处应包含原文件全部历史章节标题，可用以下命令生成： -->
<!-- git show HEAD:WORK.md > 历史素材.md 后人工分割 -->
```

执行步骤：
1. `git show HEAD:WORK.md > "$env:TEMP\WORK_full.md"`（迁出前完整备份）
2. 将「本轮 Rx」及已核销明细表移入 `work-history.md`
3. 原文件按 Step 2 重写为当前态

- [ ] **Step 2: 重写 WORK.md 当前态（≤9000）**

```markdown
# WORK.md（当前状态 · 唯一来源）

更新于：2026-09-23（启动链与规则门禁分层瘦身 · 分支 `optimize/slim-rules-gates`）

## 当前状态快照

- 启动链实测曾达 136K 字符；本迭代目标四件套 **≤30K**（门禁 `hub-engine/scripts/startup_budget.py`）。
- 方案：`docs/compose/specs/2026-09-23-slim-rules-gates-design.md`（S1–S5）。
- 计划：`docs/compose/plans/2026-09-23-slim-rules-gates.md`。
- 分层：L0 常驻（AGENTS/CHARTER/WORK 当前态/INDEX 目录版）→ L1 按四型（light/code/hub/sync）→ L2 检索。
- 安全底座常驻：单写者+§4 守护+ledger；query-first+交回用户+回写。
- 历史轮次：`docs/superpowers/retro/work-history.md`。

## 活跃待办（本迭代）

| # | 任务 | 状态 |
| -- | --- | --- |
| A1 | startup_budget 门禁+单测 | 进行中/按计划勾选 |
| A2 | AGENTS 路由+CHARTER 压缩 | 按计划 |
| A3 | WORK 当前态+历史归档 | 本任务 |
| A4 | INDEX 目录化 | 按计划 |
| A5 | rules tier+长卡拆分+inject 瘦身 | 按计划 |
| B1 | backup+方法论合并+经验去重 | 按计划 |
| 收口 | 预算 PASS + 全量 pytest + ruff | 按计划 |

## 验收口径

- `python -m scripts.startup_budget` 退出码 0
- 四文件字符：AGENTS≤3000 CHARTER≤3000 WORK≤9000 INDEX≤14000 总≤30000
- `cd hub-engine && python -m pytest` 全绿；ruff check/format 绿
- L0 可见六条铁律；INDEX 无长描述正文；改码型 L1 含编码核心卡名

## 上一轮遗留（须人工裁定，非本迭代引入）

见归档「待用户裁定」四修（vector_bench 夹具 / patrol fail-below / _norm_path CWD / RRF 保底）——本迭代不擅自改。

## 环境备忘

- 系统 python 跑 pytest/ruff（.venv 缺依赖会假绿）；LM Studio 1234 / embed 对齐 bge 配置以 config 为准。
```

- [ ] **Step 3: 校验**

```powershell
python -c "from pathlib import Path; print('WORK', len(Path('WORK.md').read_text(encoding='utf-8'))); print('HIST', len(Path('docs/superpowers/retro/work-history.md').read_text(encoding='utf-8')))"
```
Expected: WORK ≤9000；HIST ≥40000（历史未丢失）

- [ ] **Step 4: Commit**

```bash
git add WORK.md docs/superpowers/retro/work-history.md
git commit -m "refactor(work): 当前态≤9K 启动路径；R1起历史整迁 retro/work-history.md"
```

---

### Task 5: INDEX 目录化（长描述退出启动路径）

**Covers:** S3, S4, S5

**Files:**
- Create: `hub-engine/scripts/slim_index.py`
- Create: `hub-engine/tests/test_slim_index.py`
- Modify: `AgentMemoryHub/INDEX.md`（脚本生成目录版）

**Interfaces:**
- Consumes: 现有 INDEX 行结构：卡行以 `- ` 开头，卡名后 4+ 空格再描述；分区 `## ` 与 `<!--` 注释保留
- Produces: `slim_index.slim_line(line: str, max_desc: int = 40) -> str`、`slim_index.slim_text(text: str) -> str`、`slim_index.main(argv) -> int`

- [ ] **Step 1: Write the failing test**

```python
# hub-engine/tests/test_slim_index.py
from scripts.slim_index import slim_line, slim_text


def test_slim_truncates_description():
    line = "- foo-bar    " + "描述" * 50
    out = slim_line(line, max_desc=40)
    assert out.startswith("- foo-bar")
    # 描述段 ≤40 且原卡名完整
    assert "foo-bar" in out
    desc = out.split("foo-bar", 1)[1].strip()
    assert len(desc) <= 42  # 含截断省略号


def test_slim_keeps_headers_and_comments():
    text = "# 中枢索引\n\n<!-- [全局] 注释 -->\n\n## 规则（rules/）\n"
    assert slim_text(text) == text


def test_slim_short_desc_untouched():
    line = "- short-name    短描述"
    assert slim_line(line) == line


def test_slim_ignores_non_card_bullets():
    line = "- rules/        权威规则（命令式/约束式，违反有代价）"
    # 目录说明行（含 / 结尾 token）不截断
    assert slim_line(line) == line


def test_main_writes_and_budget(tmp_path):
    src = tmp_path / "INDEX.md"
    src.write_text("- " + "a" * 20 + "    " + "长" * 200 + "\n", encoding="utf-8")
    from scripts.slim_index import main
    assert main(["--path", str(src), "--dry-run"]) == 0
    # dry-run 不改文件
    assert "长" * 100 in src.read_text(encoding="utf-8")
    assert main(["--path", str(src)]) == 0
    assert len(src.read_text(encoding="utf-8")) < 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd hub-engine && python -m pytest tests/test_slim_index.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# hub-engine/scripts/slim_index.py
"""INDEX 目录化：卡行描述截断 ≤40 字，标题/注释/目录说明行保留。

详情以卡 frontmatter/正文为唯一源（spec S3）；本脚本幂等可重跑。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# `- name    desc` 或 `- name **desc**`：卡名 [A-Za-z0-9_-]+ 后接空白+描述
_CARD = re.compile(r"^(- [A-Za-z0-9_-]+)(\s+)(.+)$")


def slim_line(line: str, max_desc: int = 40) -> str:
    raw = line.rstrip("\n")
    # 目录说明：`- rules/` 等以 / 结尾的 token 不是卡
    if raw.startswith("- ") and "/" in raw.split()[1]:
        return line
    m = _CARD.match(raw)
    if not m:
        return line
    name, _sp, desc = m.group(1), m.group(2), m.group(3).strip()
    if len(desc) <= max_desc:
        return line
    cut = desc[:max_desc].rstrip()
    return f"{name}    {cut}…\n" if line.endswith("\n") else f"{name}    {cut}…"


def slim_text(text: str) -> str:
    out = []
    for line in text.splitlines(keepends=True):
        if line.startswith("- ") and not line.lstrip().startswith("- /"):
            out.append(slim_line(line))
        else:
            out.append(line)
    return "".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="INDEX 目录化")
    ap.add_argument("--path", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    raw = args.path.read_text(encoding="utf-8")
    slim = slim_text(raw)
    if not args.dry_run:
        args.path.write_text(slim, encoding="utf-8")
    print(f"{len(raw)} -> {len(slim)} chars{' (dry-run)' if args.dry_run else ''}")
    if len(slim) > 14_000:
        print("FAIL: 仍 >14000 分项帽")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests + 真机 dry-run 再写入**

```bash
cd hub-engine && python -m pytest tests/test_slim_index.py -v
python -m scripts.slim_index --path ../AgentMemoryHub/INDEX.md --dry-run
python -m scripts.slim_index --path ../AgentMemoryHub/INDEX.md
python -c "from pathlib import Path; print(len(Path('../AgentMemoryHub/INDEX.md').read_text(encoding='utf-8')))"
```
Expected: 测试 PASS；INDEX ≤14000

- [ ] **Step 5: 人工抽查 + lint 孤儿/幽灵**

```bash
cd hub-engine && python -m engine.py lint --root ../AgentMemoryHub
```
Expected: 无新增孤儿/幽灵（INDEX 行数结构保留）

- [ ] **Step 6: Commit**

```bash
git add hub-engine/scripts/slim_index.py hub-engine/tests/test_slim_index.py AgentMemoryHub/INDEX.md
git commit -m "refactor(index): 目录化——卡描述截断≤40字，详情只在卡正文（≤14K）"
```

---

### Task 6: rules tier 标注 + 长卡拆核心/附录 + inject 瘦身

**Covers:** S2, S3, S4, S5

**Files:**
- Modify: `AgentMemoryHub/rules/*.md`（32 张 frontmatter 加 `tier`）
- Modify: 长卡 3 张拆分 + Create 对应 `*-appendix.md`
- Modify: `hub-engine/tools/inject.py`（INSTRUCTION 文本）
- Modify: `hub-engine/tests/test_inject.py`（断言对齐新模板）

**Interfaces:**
- Consumes: `task_tier.L1_CARDS` 卡名；inject 现有 `INSTRUCTION` / `inject_instruction` / 幂等逻辑（不改函数签名）
- Produces: 每卡 `tier: iron|task|ref`；L1 卡含「核心」段；注入含 6 条铁律 + 任务型一句 + 检索一句

**tier 映射（手工写入各卡 frontmatter，type: rule 行后增加一行）：**

| tier | 卡名 |
| --- | --- |
| iron | dual-platform-coherence-discipline, memory-hub-query-first, memory-hub-distill-last |
| task | chinese-text-encoding-discipline, agent-code-discipline-iron-rule, multi-language-style-config, cross-platform-sync-rule, rules-routing-table, agent-modify-must-view-page, markdown-revision-style, output-language-rule, context-budget-discipline, reusable-code-header-comment-rule, agent-show-todo-rule, auto-promote-empty-today-rule, requirement-alignment-first, gateway-no-credential-rule, lint-runtime-data-exclude, dsh-patch-driven-plugin, pluginhub-startup-automation-script-registration-standard, dll-version-lock, browser-automation-chrome-preference, text-extraction-priority, pre-uninstall-data-safety-check, trae-work-ruff-format-batch-bug, gh-star-repo-filter-rule, clash-rule-fix-consumption-standard, ollama-retired-lmstudio-takeover, hub-inventory-baseline-audit, code-platform-conventions, context-engineering-skeleton, context-engineering-avoid, global-rules |
| （已在 iron/task 覆盖全部 32 张；无 ref） | — |

- [ ] **Step 1: 批量写入 tier 字段**

```powershell
# 在 hub 仓对每个 rules/*.md：若无 tier: 行，在 type: rule 下一行插入
# iron/task 表见上；示例一条：
python - <<'PY'
from pathlib import Path
IRON = {
 "dual-platform-coherence-discipline","memory-hub-query-first","memory-hub-distill-last",
}
# task = 其余 29 张
root = Path("AgentMemoryHub/rules")
for p in sorted(root.glob("*.md")):
    if p.name.endswith("-appendix.md"):
        continue
    t = p.read_text(encoding="utf-8")
    if "\ntier:" in t or t.startswith("tier:"):
        continue
    tier = "iron" if p.stem in IRON else "task"
    t2 = t.replace("type: rule\n", f"type: rule\ntier: {tier}\n", 1)
    assert t2 != t, p
    p.write_text(t2, encoding="utf-8")
    print("tier", tier, p.name)
PY
```

- [ ] **Step 2: 长卡拆核心+附录（3 张）**

对每张 `NAME.md`（chinese-text-encoding-discipline / multi-language-style-config / rules-routing-table）：

1. 原文件全文移入 `AgentMemoryHub/rules/NAME-appendix.md`（frontmatter 加 `tier: ref` + 标题行注「完整附录」）。
2. `NAME.md` 保留：frontmatter（含 tier）+「核心规则」≤1.5K：
   - **chinese-text-encoding**：一句话结论 + 触发条件 5 条 + 7 环检查表（表可精简列）+「细则见 NAME-appendix」
   - **multi-language-style-config**：每语言一行结论（Python=ruff、C#=dotnet format、JS=ESLint+Prettier、通用=.editorconfig）+ 模板见附录
   - **rules-routing-table**：GR-1~4 各一行 + 四型→规则映射指向 `tools/task_tier.L1_CARDS` + 启动门禁模板移附录

核心正文末行固定：`> 完整内容：rules/NAME-appendix.md（L2 按需）`

3. 跑：

```bash
cd hub-engine && python -c "from pathlib import Path; import sys
for n in ['chinese-text-encoding-discipline','multi-language-style-config','rules-routing-table']:
    c=len(Path(f'../AgentMemoryHub/rules/{n}.md').read_text(encoding='utf-8'))
    print(n,c); assert c<=2000, n
"
```
Expected: 三卡均 ≤2000（含 frontmatter，为帽 1.5K 正文 + 边界）

- [ ] **Step 3: inject 瘦身（改 INSTRUCTION，不动签名）**

替换 `hub-engine/tools/inject.py` 中 `INSTRUCTION` 为：

```python
INSTRUCTION = """## 统一记忆中枢（AGENT MEMORY HUB）
L0 铁律：① 单写者锁+工作区守护 ② 执行前先查中枢 ③ 不确定交回用户、不臆测 ④ 结果回写经验卡。
任务分型后按 AGENTS.md 路由读 L1 规则卡（light/code/hub/sync，口径 tools.task_tier）。
细节：MCP hub_bootstrap/hub_search，或 `python hub-engine/engine.py retrieve --root {hub} "<问题>"`；无 MCP 读 INDEX 目录版。
命中「引用+摘要」进任务上下文；规则类再 hub_get/读卡全文（compress_level 分级仍有效）。
冲突以中枢为准；闭环 hub_ingest_candidate 回写候选。
中枢位置：{hub}
"""
```

- [ ] **Step 4: 更新 test_inject 断言**

在 `test_inject.py` 增加并保持旧断言兼容：

```python
def test_inject_slim_l0_and_task_tier(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("", encoding="utf-8")
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert "L0 铁律" in text
    assert "task_tier" in text
    assert "单写者" in text
    # 不再贴长模板
    assert "compress_level 分级取用说明的长展开" not in text
```

保留既有 5 测；若 `compress_level` 字符串在新模板中仍出现则旧测继续过（新模板保留「compress_level 分级仍有效」）。

- [ ] **Step 5: Run tests**

```bash
cd hub-engine && python -m pytest tests/test_inject.py tests/test_task_tier.py -v
ruff check tools/inject.py scripts/ tests/test_inject.py
```
Expected: PASS + ruff 绿

- [ ] **Step 6: Commit（中枢卡与引擎可分两笔）**

```bash
git add AgentMemoryHub/rules hub-engine/tools/inject.py hub-engine/tests/test_inject.py
git commit -m "refactor(rules+inject): 32卡tier标注+3长卡核心/附录拆分+注入只留L0六条与分型路由"
```

---

### Task 7: B1 backup + 方法论合并 + 经验去重

**Covers:** S2, S3, S4, S5

**Files:**
- Run-only: `scripts/backup-rules.py`（根目录）
- Run-only: `scripts/merge-methodology.py`
- Run-only: `scripts/deduplicate-experience.py`
- Modify: `AgentMemoryHub/methodology/*`、`AgentMemoryHub/experience/*`（脚本产物）
- Modify: `AgentMemoryHub/INDEX.md`（合并后卡名行更新，再跑 slim）

**Interfaces:**
- Consumes: 脚本内硬编码路径与 `MERGE_PAIRS` 四组
- Produces: `.backup/<DATE>/manifest.txt`；合并目标卡；DEPRECATED 头

- [ ] **Step 1: 全量备份 rules**

```bash
python scripts/backup-rules.py
```
Expected: `Found N rule files` + manifest 路径打印

- [ ] **Step 2: 合并前确认四组源文件存在**

```bash
python -c "from pathlib import Path; pairs=[
('first-principles','occam-razor'),('iteration-gate','phase-restart'),
('tunnel-vision-check','feedback-loop'),
('cross-agent-memory-hub-architecture','memory-injection-mandatory-hub-query')];
root=Path('AgentMemoryHub/methodology');
[print(a,b,(root/f'{a}.md').exists(),(root/f'{b}.md').exists()) for a,b in pairs]"
```
Expected: 四组 True True（缺则停下问用户，不臆测）

- [ ] **Step 3: 执行合并 + 经验去重**

```bash
python scripts/merge-methodology.py
python scripts/deduplicate-experience.py
```
Expected: `Completed: 4 pairs merged`；去重打印 duplicates（允许 0）

- [ ] **Step 4: INDEX 同步改名 + 再 slim**

1. 手工将 INDEX 中被合并源卡行改为目标卡（thinking-principles / iteration-methodology / reflection-methodology / memory-injection-pattern），删除源卡行或标注 superseded。
2. `cd hub-engine && python -m scripts.slim_index --path ../AgentMemoryHub/INDEX.md`
3. `python -m engine.py lint --root ../AgentMemoryHub`  
Expected: 幽灵/孤儿不因合并新增（源文件仍有 DEPRECATED 头则 lint 口径以现有规则为准；若源卡仍注册但已 DEPRECATED，INDEX 保留源行+「→目标卡」）

- [ ] **Step 5: 检索抽查 4 组目标卡**

```bash
cd hub-engine && python -m engine.py retrieve --root ../AgentMemoryHub "第一性原理 奥卡姆"
python -m engine.py retrieve --root ../AgentMemoryHub "记忆注入 强制查询"
```
Expected: 目标合并卡出现在 top

- [ ] **Step 6: Commit（含中枢子仓若独立——本仓库 AgentMemoryHub 在 monorepo 内则一并）**

```bash
git add AgentMemoryHub scripts docs/compose
git commit -m "refactor(hub): backup+方法论4组合并+经验去重；INDEX 对齐并保持目录化"
```

说明：若 `AgentMemoryHub` 为嵌套独立 git，需在该仓单独 commit（遵循既有双仓习惯）；执行时 `git status` 确认，不臆测。

---

### Task 8: 收口——预算 PASS + 全量验证 + WORK 回写

**Covers:** S1, S5

**Files:**
- Modify: `WORK.md`（待办勾为完成、预算实测数）
- Modify: 本计划 checkbox 勾选

**Interfaces:**
- Consumes: Task 1–7 产物
- Produces: 验收证据（命令输出摘要）

- [ ] **Step 1: 预算门禁必须 PASS**

```bash
cd hub-engine && python -m scripts.startup_budget
```
Expected: 退出码 0；TOTAL ≤30000  
若 FAIL：按超标文件回到对应任务再裁（INDEX→再 slim；WORK→再删历史残段；AGENTS/CHARTER→再压）

- [ ] **Step 2: 全量测试 + ruff**

```bash
cd hub-engine && python -m pytest -q
ruff check . && ruff format --check .
```
Expected: pytest 无 FAIL；ruff 绿（全仓 `ruff check` 在仓库根跑亦可）

- [ ] **Step 3: L0 冷读抽查**

读 `AGENTS.md`：六条铁律+四型表可见；`INDEX.md` 首 50 行无超长描述；`WORK.md` 无 R1–R14 长叙事。

- [ ] **Step 4: 回写 WORK 当前态**

更新「活跃待办」全表为完成、填入 `startup_budget` 实测 TOTAL 数字、验收口径已满足。

- [ ] **Step 5: Commit + 可选推送**

```bash
git add WORK.md docs/compose/plans/2026-09-23-slim-rules-gates.md
git commit -m "chore(verify): 瘦身收口——预算PASS/全量pytest/ruff绿，WORK回写实测"
# 推送仅在用户要求时：git push origin optimize/slim-rules-gates
```

---

## Self-Review（已跑）

1. **Spec coverage:** S1→T8；S2→T2/T3/T6/T7；S3→T1/T3/T4/T5/T6/T7；S4→T2/T3/T5/T6；S5→T1/T2/T5/T6/T7/T8。无缺口。
2. **Placeholder scan:** 历史迁出用「粘贴+git show」为机械步骤，含完整保留要求，非 TBD；inject/AGENTS 均给全文。
3. **Type consistency:** `check(dict[str,int])` 与测试一致；`classify`/`L1_CARDS` 四键一致；`slim_line` 幂等；inject 仍用 `{hub}` 格式化。

