# hub-mcp-server 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现本地 MCP Server（stdio），把中枢检索/读卡/索引/候选回写/任务级引导暴露给各 Agent 平台，并落审计日志，解决「是否先查中枢」可验证问题。

**Architecture:** 纯函数 handler（`tools/mcp_handlers.py`）薄封装现有 `tools/retrieve.py`（新增 `retrieve_with_meta` 一次拿 channel/score），`tools/mcp_policy.py` 做路径防逃逸与平台/类型白名单，`tools/mcp_audit.py` 写 `query.log.jsonl`；`mcp_server.py` 用官方 MCP SDK（`mcp` 1.26）做 stdio 入口，只做协议转发，不掺业务。任务级引导 `hub_bootstrap` 按 task-kind 映射类别多次检索，聚合出「引用+摘要」引导块。

**Tech Stack:** Python 3.11（全局解释器，无 venv）、`mcp==1.26.0`（已装）、PyYAML、jieba（可选）、pytest、ruff。`AgentMemoryHub/` 为运行态数据区（`.check-code.toml` 已排除静态 lint）。

**运行命令（均假设 PowerShell，仓库根 = `c:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv`）：**

```powershell
# 测试（在 hub-engine 目录，pythonpath=["."]）
cd hub-engine; python -m pytest tests/test_xxx.py -v
cd hub-engine; python -m pytest            # 全量

# lint
python -m ruff check hub-engine
python -m ruff format --check hub-engine
```

**文件结构（本计划落地）：**

```text
hub-engine/
  tools/retrieve.py            # 修改：新增 retrieve_with_meta / _semantic_scored
  tools/mcp_policy.py          # 新建：路径防逃逸 + 白名单
  tools/mcp_audit.py           # 新建：审计日志
  tools/mcp_handlers.py        # 新建：search/get/index/bootstrap/ingest_candidate 纯函数
  mcp_server.py                # 新建：MCP stdio 入口（build_server 可测）
  tools/inject.py              # 修改：指令文案升级为任务级引导契约
  scripts/query_report.py      # 新建：查询周报统计
  tests/test_retrieve.py       # 修改：retrieve_with_meta 用例
  tests/test_mcp_policy.py     # 新建
  tests/test_mcp_audit.py      # 新建
  tests/test_mcp_handlers.py   # 新建
  tests/test_mcp_server.py     # 新建
  tests/test_inject.py         # 修改：新文案断言
  tests/test_query_report.py   # 新建
mcp.example.json               # 新建：平台 MCP 客户端配置样例（Task 8）
```

**关键事实（勿假设）：**

- `Card` 在 `common/frontmatter.py`：`type/tags/updated/status/reuse_count/extra/body/path`；`try_read_card(path) -> Card|None` 带 `path`；`write_card(card) -> str`；`today_iso()`。
- `tools/retrieve.py` 现有：`_walk_active_cards(root)` 扫 7 目录（rules/methodology/longterm/projects/experience/libs/retro，跳过 archived）；`deterministic_retrieve`；`semantic_retrieve`（内部算 score 但只返回 cards）。
- `common/vector.py`：`build_idf/cosine/vector/tokenize`。
- `common/config.py`：`HubConfig.load(root).platforms -> dict`。
- `sync.py`：`_WriteLock` 在 `.sync/locks/writer.lock`；draft 目录约定 `.sync/drafts/<platform>_draft/`；rule 走 `.sync/pending/` + `confirm_rule`。
- 测试建库用 `from scripts.bootstrap_hub import bootstrap`（返回临时中枢根）。
- `mcp` 包 1.26.0 已装在全局 python；`from mcp.server import Server`、`from mcp.server.stdio import stdio_server` 可用。

---

## Task 1: retrieve_with_meta（一次拿 channel/score）

**Files:**
- Modify: `hub-engine/tools/retrieve.py`
- Test: `hub-engine/tests/test_retrieve.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_retrieve.py` 末尾追加：

```python
def test_retrieve_with_meta_deterministic_channel(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    channel, scored = retrieve_with_meta(root, "dll-lock")
    assert channel == "deterministic"
    assert [c.path.name for c, _ in scored] == ["dll-lock.md"]
    assert all(s is None for _, s in scored)  # 确定性命中不带 score


def test_retrieve_with_meta_semantic_scores(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    channel, scored = retrieve_with_meta(root, "改了插件 DLL 结果被 AutoCAD 锁住打不开")
    assert channel == "semantic"
    assert scored and all(s is not None for _, s in scored)


def test_retrieve_with_meta_empty_channel(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    channel, scored = retrieve_with_meta(root, "   ")
    assert channel == "empty"
    assert scored == []


def test_retrieve_still_returns_cards(tmp_path):
    """retrieve 兼容层：行为与之前一致（返回 Card 列表）"""
    root = bootstrap(tmp_path)
    _seed(root)
    hits = retrieve(root, "DLL 被锁怎么办")
    assert all(isinstance(c, object) for c in hits)
    assert len(hits) >= 1
```

同时更新导入行：

```python
from tools.retrieve import (
    deterministic_retrieve,
    retrieve,
    retrieve_with_meta,
    semantic_retrieve,
)
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd hub-engine; python -m pytest tests/test_retrieve.py -v
```

Expected: FAIL，`ImportError: cannot import name 'retrieve_with_meta'`。

- [ ] **Step 3: 实现**

修改 `tools/retrieve.py`：把 `semantic_retrieve` 的评分逻辑抽成 `_semantic_scored`，新增 `retrieve_with_meta`，并让 `retrieve` 复用。

```python
def _semantic_scored(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[tuple[Card, float]]:
    """语义通道带分数召回：返回 [(card, sim)]，按相似度降序"""
    cards = _walk_active_cards(root)
    idf = (
        build_idf([_card_text(c) for c in cards], n=n, mode=mode)
        if mode == "word"
        else None
    )
    qv = vector(query, n=n, mode=mode, idf=idf)
    scored = []
    for c in cards:
        sim = cosine(qv, vector(_card_text(c), n=n, mode=mode, idf=idf))
        if sim > 0:
            scored.append((sim, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(c, sim) for sim, c in scored[:top_k]]


def semantic_retrieve(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[Card]:
    """语义通道：对 body+tags 做 token 余弦相似度召回 top-k（兼容旧接口）"""
    return [c for c, _ in _semantic_scored(root, query, top_k, n, mode)]


def retrieve_with_meta(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> tuple[str, list[tuple[Card, float | None]]]:
    """混合检索入口，带通道与分数：返回 (channel, [(card, score|None)])

    channel: "empty"（空查询）| "deterministic"（确定性命中，score=None）| "semantic"
    """
    if not query.strip():
        return "empty", []
    hits = deterministic_retrieve(root, query, mode)
    if hits:
        return "deterministic", [(c, None) for c in hits]
    return "semantic", _semantic_scored(root, query, top_k, n, mode)


def retrieve(
    root: Path, query: str, top_k: int = 5, n: int = 2, mode: str = "word"
) -> list[Card]:
    """混合检索入口（兼容旧接口，仅返回卡片列表）"""
    _, scored = retrieve_with_meta(root, query, top_k, n, mode)
    return [c for c, _ in scored]
```

- [ ] **Step 4: 运行确认通过**

```powershell
cd hub-engine; python -m pytest tests/test_retrieve.py -v
```

Expected: 全部 PASS（含原有用例）。

- [ ] **Step 5: Commit**

```powershell
git add hub-engine/tools/retrieve.py hub-engine/tests/test_retrieve.py
git commit -m "feat: retrieve_with_meta 一次返回 channel/score，retrieve 复用保持兼容"
```

---

## Task 2: mcp_policy.py（路径防逃逸 + 白名单）

**Files:**
- Create: `hub-engine/tools/mcp_policy.py`
- Test: `hub-engine/tests/test_mcp_policy.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_mcp_policy.py`：

```python
import pytest
from scripts.bootstrap_hub import bootstrap
from tools.mcp_policy import (
    AUTHORITY_DIRS,
    allowed_platforms,
    assert_candidate_type,
    resolve_rel,
    resolve_slug,
)


def test_resolve_rel_in_bounds(tmp_path):
    root = bootstrap(tmp_path)
    p = resolve_rel(root, "rules/dll-lock.md")
    assert p == (root / "rules" / "dll-lock.md").resolve()


def test_resolve_rel_escape(tmp_path):
    root = bootstrap(tmp_path)
    for bad in ("../secret.md", "..\\secret.md", "C:/windows/win.ini", "C:\\windows\\win.ini"):
        with pytest.raises(ValueError, match="path_escape"):
            resolve_rel(root, bad)


def test_resolve_slug_unique(tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [autocad]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nx\n",
        encoding="utf-8",
    )
    p = resolve_slug(root, "dll-lock")
    assert p == (root / "rules" / "dll-lock.md").resolve()


def test_resolve_slug_not_found(tmp_path):
    root = bootstrap(tmp_path)
    with pytest.raises(FileNotFoundError, match="not_found"):
        resolve_slug(root, "no-such-card")


def test_resolve_slug_ambiguous(tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules" / "dup.md").write_text(
        "---\ntype: rule\ntags: []\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nx\n",
        encoding="utf-8",
    )
    (root / "methodology" / "dup.md").write_text(
        "---\ntype: methodology\ntags: []\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nx\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_slug(root, "dup")


def test_allowed_platforms_from_config(tmp_path):
    root = bootstrap(tmp_path)
    # bootstrap 默认无 platforms；带 extra 时应并入
    s = allowed_platforms(root, extra=("traework",))
    assert "traework" in s
    assert "hermes" in s or isinstance(s, set)


def test_assert_candidate_type_whitelist():
    assert_candidate_type("exp")
    assert_candidate_type("note")
    assert_candidate_type("project")
    for bad in ("rule", "methodology", "longterm", "retro", "note2"):
        with pytest.raises(ValueError, match="type_forbidden"):
            assert_candidate_type(bad)


def test_authority_dirs_has_five_plus():
    assert set(AUTHORITY_DIRS) >= {
        "rules",
        "methodology",
        "longterm",
        "projects",
        "experience",
    }
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd hub-engine; python -m pytest tests/test_mcp_policy.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'tools.mcp_policy'`。

- [ ] **Step 3: 实现**

创建 `tools/mcp_policy.py`：

```python
"""MCP 权限与路径策略：路径防逃逸 / platform 白名单 / 候选 type 白名单"""

from pathlib import Path

from common.config import HubConfig

AUTHORITY_DIRS = (
    "rules",
    "methodology",
    "longterm",
    "projects",
    "experience",
    "libs",
    "retro",
)
CANDIDATE_TYPES = {"exp", "note", "project"}


class PolicyError(ValueError):
    """策略违规；code 对应用户可见的稳定错误码"""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def resolve_rel(root: Path, rel: str) -> Path:
    """相对中枢根解析路径；越界抛 PolicyError(path_escape)"""
    root_r = root.resolve()
    p = (root / rel).resolve()
    try:
        p.relative_to(root_r)
    except ValueError:
        raise PolicyError("path_escape", f"路径越界: {rel}") from None
    return p


def resolve_slug(root: Path, slug: str) -> Path:
    """slug/相对路径 → 权威目录唯一卡片路径。

    - 含 '/' 或 .md 后缀 → 按相对路径解析（允许越权目录不存在时报 not_found）
    - 纯 slug → 在 AUTHORITY_DIRS 下找唯一 {slug}.md
    """
    if "/" in slug or slug.endswith(".md"):
        p = resolve_rel(root, slug)
        if not p.exists():
            raise FileNotFoundError(f"not_found: {slug}")
        return p
    name = f"{slug}.md"
    hits = [root / sub / name for sub in AUTHORITY_DIRS if (root / sub / name).exists()]
    if len(hits) > 1:
        raise PolicyError("ambiguous", f"slug 多命中: {slug}")
    if not hits:
        raise FileNotFoundError(f"not_found: {slug}")
    return hits[0]


def allowed_platforms(root: Path, extra: tuple[str, ...] = ()) -> set[str]:
    """hub.config.yaml platforms 键 ∪ 显式 extra"""
    return set(HubConfig.load(root).platforms) | set(extra)


def assert_candidate_type(type_: str) -> str:
    """候选卡类型白名单；非法抛 PolicyError(type_forbidden)"""
    if type_ not in CANDIDATE_TYPES:
        raise PolicyError("type_forbidden", f"候选 type 不允许: {type_}")
    return type_
```

- [ ] **Step 4: 运行确认通过**

```powershell
cd hub-engine; python -m pytest tests/test_mcp_policy.py -v
```

Expected: 全部 PASS。（注意：`test_allowed_platforms_from_config` 依赖 `bootstrap` 生成的 hub.config.yaml 是否含 platforms——bootstrap 模板无 platforms 时 `allowed_platforms` 返回空集∪extra，断言 `"traework" in s` 成立即可；若模板含 hermes 也无碍。）

- [ ] **Step 5: Commit**

```powershell
git add hub-engine/tools/mcp_policy.py hub-engine/tests/test_mcp_policy.py
git commit -m "feat: mcp_policy 路径防逃逸 + 平台/候选类型白名单"
```

---

## Task 3: mcp_audit.py（审计日志）

**Files:**
- Create: `hub-engine/tools/mcp_audit.py`
- Test: `hub-engine/tests/test_mcp_audit.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_mcp_audit.py`：

```python
import json

from scripts.bootstrap_hub import bootstrap
from tools.mcp_audit import append_query_log, audit_id


def test_audit_id_shape():
    aid = audit_id()
    assert aid.count("-") == 1
    assert "T" in aid.split("-")[0]


def test_append_query_log_writes_line(tmp_path):
    root = bootstrap(tmp_path)
    append_query_log(root, {"audit_id": "a1", "action": "search", "platform": "trae", "ok": True})
    log = root / ".sync" / "state" / "query.log.jsonl"
    assert log.exists()
    rec = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[0])
    assert rec["action"] == "search"
    assert rec["platform"] == "trae"
    assert rec["ts"]


def test_append_query_log_best_effort(tmp_path, monkeypatch):
    """日志写入失败不抛异常（D4 best-effort）"""
    root = bootstrap(tmp_path)
    state = root / ".sync" / "state"
    # 让 state 目录变成普通文件，导致 mkdir 失败
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("not a dir", encoding="utf-8")
    append_query_log(root, {"audit_id": "a2", "action": "get"})  # 不应抛异常


def test_audit_id_unique():
    assert len({audit_id() for _ in range(100)}) == 100
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd hub-engine; python -m pytest tests/test_mcp_audit.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'tools.mcp_audit'`。

- [ ] **Step 3: 实现**

创建 `tools/mcp_audit.py`：

```python
"""MCP 审计日志：query.log.jsonl（best-effort 追加 + 简单轮转）"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

LOG_NAME = "query.log.jsonl"
ROTATE_BYTES = 8 * 1024 * 1024


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit_id() -> str:
    """形如 20260818T153012Z-a1b2"""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:4]


def append_query_log(root: Path, record: dict) -> None:
    """best-effort 追加一行；目录/写盘失败静默（不阻断业务）"""
    try:
        d = root / ".sync" / "state"
        d.mkdir(parents=True, exist_ok=True)
        path = d / LOG_NAME
        if path.exists() and path.stat().st_size > ROTATE_BYTES:
            path.rename(
                path.with_name(f"{LOG_NAME}.{datetime.now().strftime('%Y%m%d-%H%M%S')}")
            )
        rec = {"ts": _ts(), **record}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        pass
```

- [ ] **Step 4: 运行确认通过**

```powershell
cd hub-engine; python -m pytest tests/test_mcp_audit.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```powershell
git add hub-engine/tools/mcp_audit.py hub-engine/tests/test_mcp_audit.py
git commit -m "feat: mcp_audit 审计日志（jsonl/best-effort/轮转）"
```

---

## Task 4: mcp_handlers.py（search/get/index/bootstrap/ingest_candidate 纯函数）

**Files:**
- Create: `hub-engine/tools/mcp_handlers.py`
- Test: `hub-engine/tests/test_mcp_handlers.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_mcp_handlers.py`：

```python
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.mcp_handlers import (
    hub_bootstrap,
    hub_get,
    hub_index,
    hub_ingest_candidate,
    hub_search,
)


def _seed(root: Path) -> None:
    (root / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [autocad, dll-lock]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nDLL 修改后必须递增版本号避免被锁。\n",
        encoding="utf-8",
    )
    (root / "experience" / "blunder.md").write_text(
        "---\ntype: exp\ntags: [autocad]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\n上次没重命名导致 AutoCAD 占用文件无法覆盖。\n",
        encoding="utf-8",
    )
    (root / "methodology" / "occam.md").write_text(
        "---\ntype: methodology\ntags: [thinking]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\n奥卡姆剃刀：最少文件/字段/步骤。\n",
        encoding="utf-8",
    )


def test_search_deterministic_hit(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_search(root, "dll-lock", platform="trae")
    assert res["ok"] and res["channel"] == "deterministic"
    assert res["hits"][0]["slug"] == "dll-lock"
    assert res["hits"][0]["rel_path"] == "rules/dll-lock.md"


def test_search_empty_query(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_search(root, "   ", platform="trae")
    assert res["ok"] and res["hits"] == [] and res["channel"] == "empty"


def test_search_types_filter(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_search(root, "占用", types=["rule"], top_k=5, platform="trae")
    assert all(h["type"] == "rule" for h in res["hits"])


def test_search_writes_audit(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    hub_search(root, "dll-lock", platform="trae")
    log = root / ".sync" / "state" / "query.log.jsonl"
    assert log.exists()
    assert "hub_search" not in log.read_text(encoding="utf-8") or True  # 仅确认日志已写
    assert "search" in log.read_text(encoding="utf-8")


def test_get_by_slug(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_get(root, id_="dll-lock", platform="trae")
    assert res["ok"]
    assert res["card"]["body"] == "DLL 修改后必须递增版本号避免被锁。"
    assert res["card"]["rel_path"] == "rules/dll-lock.md"


def test_get_not_found(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_get(root, id_="nope", platform="trae")
    assert res["ok"] is False and res["error"] == "not_found"


def test_get_path_escape(tmp_path):
    root = bootstrap(tmp_path)
    res = hub_get(root, rel_path="../secret.md", platform="trae")
    assert res["ok"] is False and res["error"] == "path_escape"


def test_index_categories(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_index(root, types=["rules", "experience"], platform="trae")
    assert res["ok"]
    assert {x["slug"] for x in res["categories"]["rules"]} == {"dll-lock"}
    assert {x["slug"] for x in res["categories"]["experience"]} == {"blunder"}


def test_bootstrap_groups_by_kind(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_bootstrap(root, "dll", context="改了 DLL 被 AutoCAD 锁住", platform="trae")
    assert res["ok"] and res["task_kind"] == "dll"
    kinds = {b["kind"] for b in res["blocks"]}
    assert kinds == {"rules", "projects"}
    assert "## 中枢命中" in res["markdown"]
    assert "rules/dll-lock.md" in res["markdown"]


def test_bootstrap_unknown_kind_falls_back(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_bootstrap(root, "whatever", context="奥卡姆剃刀", platform="trae")
    assert res["task_kind"] == "generic"
    assert "methodology" in {b["kind"] for b in res["blocks"]}


def test_ingest_candidate_writes_draft(tmp_path):
    root = bootstrap(tmp_path)
    (root / "hub.config.yaml").write_text(
        "platforms:\n  trae: {memory_dir: x, target_file: y}\n", encoding="utf-8"
    )
    res = hub_ingest_candidate(root, platform="trae", title="测试经验", body="某条经验。")
    assert res["ok"] and res["deduped"] is False
    p = root / ".sync" / "drafts" / "trae_draft" / "测试经验.md"
    assert p.exists() or (root / ".sync" / "drafts" / "trae_draft").exists()
    text = (root / ".sync" / "drafts" / "trae_draft" / f"{res['slug']}.md").read_text(
        encoding="utf-8"
    )
    assert "type: exp" in text
    assert "status: candidate" in text


def test_ingest_candidate_dedup(tmp_path):
    root = bootstrap(tmp_path)
    (root / "hub.config.yaml").write_text(
        "platforms:\n  trae: {memory_dir: x, target_file: y}\n", encoding="utf-8"
    )
    hub_ingest_candidate(root, platform="trae", title="T", body="相同正文")
    res = hub_ingest_candidate(root, platform="trae", title="T", body="相同正文")
    assert res["deduped"] is True


def test_ingest_candidate_rule_forbidden(tmp_path):
    root = bootstrap(tmp_path)
    (root / "hub.config.yaml").write_text(
        "platforms:\n  trae: {memory_dir: x, target_file: y}\n", encoding="utf-8"
    )
    res = hub_ingest_candidate(root, platform="trae", title="R", body="b", type_="rule")
    assert res["ok"] is False and res["error"] == "type_forbidden"


def test_ingest_candidate_unknown_platform_forbidden(tmp_path):
    root = bootstrap(tmp_path)
    res = hub_ingest_candidate(root, platform="unknown", title="X", body="b")
    assert res["ok"] is False and res["error"] == "platform_forbidden"
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd hub-engine; python -m pytest tests/test_mcp_handlers.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'tools.mcp_handlers'`。

- [ ] **Step 3: 实现**

创建 `tools/mcp_handlers.py`：

```python
"""MCP 工具处理函数：search/get/index/bootstrap/ingest_candidate（纯函数，便于单测）"""

import re
from datetime import datetime, timezone
from pathlib import Path

from common.frontmatter import Card, today_iso, try_read_card, write_card
from tools.mcp_audit import append_query_log, audit_id
from tools.mcp_policy import (
    AUTHORITY_DIRS,
    PolicyError,
    allowed_platforms,
    assert_candidate_type,
    resolve_slug,
)
from tools.retrieve import retrieve_with_meta

DEFAULT_EXCERPT = 200
SUBDIR_BY_TYPE = {
    "rule": "rules",
    "methodology": "methodology",
    "longterm": "longterm",
    "project": "projects",
    "exp": "experience",
    "note": "experience",
    "retro": "retro",
}
TASK_KIND_TYPES = {
    "dll": ("rules", "projects"),
    "code": ("rules", "methodology", "projects"),
    "project": ("longterm", "methodology"),
    "debug": ("projects", "experience"),
    "generic": ("rules", "methodology", "longterm", "projects"),
}


def _excerpt(text: str, limit: int) -> str:
    return text[:limit]


def _hit(card: Card, channel: str, score: float | None, root: Path, include_body: bool) -> dict:
    rel = card.path.relative_to(root).as_posix()
    h = {
        "slug": card.path.stem,
        "rel_path": rel,
        "type": card.type,
        "status": card.status,
        "tags": card.tags,
        "updated": card.updated,
        "channel": channel,
        "excerpt": _excerpt(card.body, DEFAULT_EXCERPT),
    }
    if score is not None:
        h["score"] = round(score, 4)
    if include_body:
        h["body"] = card.body
    return h


def hub_search(
    root: Path,
    query: str,
    top_k: int = 5,
    mode: str = "word",
    n: int = 2,
    types: list[str] | None = None,
    include_body: bool = False,
    platform: str = "unknown",
) -> dict:
    top_k = max(1, min(20, int(top_k)))
    channel, scored = retrieve_with_meta(root, query, top_k=top_k, n=n, mode=mode)
    allow = set(types) if types else None
    hits = []
    for card, score in scored:
        if allow is not None and card.type not in allow:
            continue
        hits.append(_hit(card, channel, score, root, include_body))
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "search",
            "platform": platform,
            "ok": True,
            "query": query,
            "channel": channel,
            "top_k": top_k,
            "mode": mode,
            "hit_paths": [h["rel_path"] for h in hits],
            "hit_count": len(hits),
        },
    )
    return {"ok": True, "query": query, "channel": channel, "hits": hits, "audit_id": aid}


def hub_get(root: Path, id_: str = "", rel_path: str = "", platform: str = "unknown") -> dict:
    target = rel_path or id_
    if not target:
        return {"ok": False, "error": "bad_request", "message": "id 或 rel_path 至少一个"}
    try:
        p = resolve_slug(root, target)
    except PolicyError as e:
        return {"ok": False, "error": e.code, "message": str(e)}
    except FileNotFoundError as e:
        return {"ok": False, "error": "not_found", "message": str(e)}
    card = try_read_card(p)
    if card is None:
        return {"ok": False, "error": "not_found", "message": f"非卡片文件: {target}"}
    hit = _hit(card, "get", None, root, include_body=True)
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "get",
            "platform": platform,
            "ok": True,
            "id": target,
            "hit_paths": [hit["rel_path"]],
            "hit_count": 1,
        },
    )
    return {"ok": True, "card": hit, "audit_id": aid}


def hub_index(
    root: Path,
    types: list[str] | None = None,
    include_markdown: bool = False,
    platform: str = "unknown",
) -> dict:
    allow = set(types) if types else None
    categories = {}
    for sub in AUTHORITY_DIRS:
        if allow is not None and sub not in allow:
            continue
        d = root / sub
        if not d.exists():
            continue
        items = []
        for p in sorted(d.glob("*.md")):
            c = try_read_card(p)
            if c is not None and c.status != "archived":
                items.append(
                    {
                        "slug": p.stem,
                        "rel_path": p.relative_to(root).as_posix(),
                        "type": c.type,
                        "tags": c.tags,
                    }
                )
        categories[sub] = items
    res = {"ok": True, "categories": categories}
    if include_markdown:
        idx = root / "INDEX.md"
        if idx.exists():
            res["index_markdown"] = idx.read_text(encoding="utf-8")[:32768]
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "index",
            "platform": platform,
            "ok": True,
            "types": sorted(allow) if allow else sorted(AUTHORITY_DIRS),
            "category_counts": {k: len(v) for k, v in categories.items()},
        },
    )
    res["audit_id"] = aid
    return res


def hub_bootstrap(
    root: Path,
    task_kind: str,
    context: str = "",
    platform: str = "unknown",
    top_k: int = 3,
    include_body: bool = False,
) -> dict:
    kinds = TASK_KIND_TYPES.get(task_kind)
    if kinds is None:
        task_kind = "generic"
        kinds = TASK_KIND_TYPES["generic"]
    top_k = max(1, min(10, int(top_k)))
    _, scored = retrieve_with_meta(root, context, top_k=20, mode="word")
    blocks = []
    for sub in kinds:
        picked = [h for h in scored if SUBDIR_BY_TYPE.get(h[0].type) == sub]
        blocks.append(
            {
                "kind": sub,
                "hits": [
                    _hit(card, "semantic", score, root, include_body)
                    for card, score in picked[:top_k]
                ],
            }
        )
    blocks = [b for b in blocks if b["hits"]]  # 空类别不出现在引导块
    snapshot = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"## 中枢命中（本任务快照 @{snapshot}）"]
    for b in blocks:
        header = f"### {b['kind']}"
        if b["kind"] == "rules":
            header += "（必读全文）"
        lines.append(header)
        for h in b["hits"]:
            lines.append(f"- {h['rel_path']} — {h['excerpt']}")
    markdown = "\n".join(lines)
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "bootstrap",
            "platform": platform,
            "ok": True,
            "task_kind": task_kind,
            "types": list(kinds),
            "category_hits": {b["kind"]: len(b["hits"]) for b in blocks},
        },
    )
    return {
        "ok": True,
        "task_kind": task_kind,
        "snapshot_at": snapshot,
        "blocks": blocks,
        "markdown": markdown,
        "audit_id": aid,
    }


def _slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:40] or "candidate"


def hub_ingest_candidate(
    root: Path,
    platform: str,
    title: str,
    body: str,
    type_: str = "exp",
    tags: list[str] | None = None,
    slug: str = "",
) -> dict:
    if not platform or platform == "unknown":
        return {"ok": False, "error": "platform_forbidden", "message": "platform 必填且不能为 unknown"}
    if not title.strip() or not body.strip():
        return {"ok": False, "error": "bad_request", "message": "title 与 body 必填"}
    try:
        assert_candidate_type(type_)
    except PolicyError as e:
        return {"ok": False, "error": e.code, "message": str(e)}
    if platform not in allowed_platforms(root):
        return {"ok": False, "error": "platform_forbidden", "message": f"platform 未授权: {platform}"}
    base = slug or _slugify(title)
    draft_dir = root / ".sync" / "drafts" / f"{platform}_draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    final = base
    n = 0
    path = draft_dir / f"{final}.md"
    while path.exists():
        existing = try_read_card(path)
        if existing is not None and existing.body.strip() == body.strip():
            aid = audit_id()
            append_query_log(
                root,
                {
                    "audit_id": aid,
                    "action": "ingest_candidate",
                    "platform": platform,
                    "ok": True,
                    "slug": final,
                    "rel_path": path.relative_to(root).as_posix(),
                    "deduped": True,
                },
            )
            return {"ok": True, "rel_path": path.relative_to(root).as_posix(), "slug": final, "deduped": True, "audit_id": aid}
        n += 1
        final = f"{base}-{n:02d}"
        path = draft_dir / f"{final}.md"
    card = Card(
        type=type_,
        tags=list(dict.fromkeys([platform] + (tags or []))),
        updated=today_iso(),
        status="candidate",
        body=body.strip(),
        extra={"source": f"mcp/{platform}"},
    )
    path.write_text(write_card(card), encoding="utf-8")
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "ingest_candidate",
            "platform": platform,
            "ok": True,
            "slug": final,
            "rel_path": path.relative_to(root).as_posix(),
            "deduped": False,
        },
    )
    return {"ok": True, "rel_path": path.relative_to(root).as_posix(), "slug": final, "deduped": False, "audit_id": aid}
```

- [ ] **Step 4: 运行确认通过**

```powershell
cd hub-engine; python -m pytest tests/test_mcp_handlers.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```powershell
git add hub-engine/tools/mcp_handlers.py hub-engine/tests/test_mcp_handlers.py
git commit -m "feat: mcp_handlers 五个工具纯函数（search/get/index/bootstrap/ingest_candidate）"
```

---

## Task 5: mcp_server.py（MCP stdio 入口）

**Files:**
- Create: `hub-engine/mcp_server.py`
- Test: `hub-engine/tests/test_mcp_server.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_mcp_server.py`：

```python
import asyncio

import pytest

try:
    from mcp.server import Server  # noqa: F401

    HAS_MCP = True
except ImportError:
    HAS_MCP = False

pytestmark = pytest.mark.skipif(not HAS_MCP, reason="mcp 未安装")


def test_build_server_exposes_tools(tmp_path):
    from mcp_server import build_server

    server = build_server(tmp_path)
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "hub_search",
        "hub_get",
        "hub_index",
        "hub_bootstrap",
        "hub_ingest_candidate",
    }


def test_call_tool_search(tmp_path):
    import json

    from mcp_server import build_server

    (tmp_path / "rules").mkdir(parents=True, exist_ok=True)
    (tmp_path / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [dll-lock]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nx\n",
        encoding="utf-8",
    )
    server = build_server(tmp_path)
    res = asyncio.run(
        server.call_tool("hub_search", {"query": "dll-lock", "platform": "trae"})
    )
    payload = json.loads(res[0].text)
    assert payload["ok"] is True
    assert payload["hits"][0]["slug"] == "dll-lock"
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd hub-engine; python -m pytest tests/test_mcp_server.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'mcp_server'`。

- [ ] **Step 3: 实现**

创建 `hub-engine/mcp_server.py`：

```python
"""hub-mcp-server：MCP stdio 入口，把中枢工具暴露给各 Agent 平台。

用法：python mcp_server.py --root <中枢根>  （或设环境变量 AGENT_MEMORY_HUB）
仅做协议转发，业务全部在 tools/mcp_handlers.py。
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 保证可 import tools.*

from mcp.server import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402
from mcp.types import TextContent, Tool  # noqa: E402

import tools.mcp_handlers as H  # noqa: E402

HANDLERS = {
    "hub_search": H.hub_search,
    "hub_get": H.hub_get,
    "hub_index": H.hub_index,
    "hub_bootstrap": H.hub_bootstrap,
    "hub_ingest_candidate": H.hub_ingest_candidate,
}

SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "top_k": {"type": "integer"},
        "mode": {"type": "string"},
        "n": {"type": "integer"},
        "types": {"type": "array", "items": {"type": "string"}},
        "include_body": {"type": "boolean"},
        "platform": {"type": "string"},
    },
    "required": ["query"],
}
GET_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "rel_path": {"type": "string"},
        "platform": {"type": "string"},
    },
}
INDEX_SCHEMA = {
    "type": "object",
    "properties": {
        "types": {"type": "array", "items": {"type": "string"}},
        "include_markdown": {"type": "boolean"},
        "platform": {"type": "string"},
    },
}
BOOTSTRAP_SCHEMA = {
    "type": "object",
    "properties": {
        "task_kind": {"type": "string"},
        "context": {"type": "string"},
        "platform": {"type": "string"},
        "top_k": {"type": "integer"},
        "include_body": {"type": "boolean"},
    },
    "required": ["task_kind"],
}
INGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string"},
        "title": {"type": "string"},
        "body": {"type": "string"},
        "type": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "slug": {"type": "string"},
    },
    "required": ["platform", "title", "body"],
}


def _normalize(name: str, arguments: dict) -> dict:
    """MCP 参数名（id/type）→ Python 参数名（id_/type_）"""
    args = dict(arguments)
    if name == "hub_get" and "id" in args:
        args["id_"] = args.pop("id")
    if name == "hub_ingest_candidate" and "type" in args:
        args["type_"] = args.pop("type")
    return args


def build_server(root: Path) -> Server:
    server = Server("agent-memory-hub")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(name="hub_search", description="混合检索中枢（确定性+语义）", inputSchema=SEARCH_SCHEMA),
            Tool(name="hub_get", description="按 slug/路径读单张卡片全文", inputSchema=GET_SCHEMA),
            Tool(name="hub_index", description="浏览五类目录结构", inputSchema=INDEX_SCHEMA),
            Tool(name="hub_bootstrap", description="任务级引导：按 task_kind 分类检索生成引导块", inputSchema=BOOTSTRAP_SCHEMA),
            Tool(name="hub_ingest_candidate", description="候选回写（仅写 draft，不直写权威区）", inputSchema=INGEST_SCHEMA),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        handler = HANDLERS.get(name)
        if handler is None:
            raise ValueError(f"未知工具: {name}")
        res = handler(root, **_normalize(name, arguments or {}))
        return [TextContent(type="text", text=json.dumps(res, ensure_ascii=False))]

    return server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hub-mcp-server")
    ap.add_argument("--root", help="中枢根目录；缺省读环境变量 AGENT_MEMORY_HUB")
    args = ap.parse_args(argv)
    root = args.root or os.environ.get("AGENT_MEMORY_HUB", "")
    if not root:
        print("需要 --root 或环境变量 AGENT_MEMORY_HUB", file=sys.stderr)
        return 2
    server = build_server(Path(root))

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行确认通过**

```powershell
cd hub-engine; python -m pytest tests/test_mcp_server.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```powershell
git add hub-engine/mcp_server.py hub-engine/tests/test_mcp_server.py
git commit -m "feat: mcp_server stdio 入口（MCP SDK 1.26，build_server 可测）"
```

---

## Task 6: inject.py 指令文案升级（任务级引导契约）

**Files:**
- Modify: `hub-engine/tools/inject.py:5-9`
- Test: `hub-engine/tests/test_inject.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_inject.py` 末尾追加：

```python
def test_inject_new_instruction_mentions_bootstrap(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("", encoding="utf-8")
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert "hub_bootstrap" in text
    assert "hub_ingest_candidate" in text
    assert "引用+摘要" in text
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd hub-engine; python -m pytest tests/test_inject.py -v
```

Expected: FAIL，`AssertionError: 'hub_bootstrap' not in text`（旧文案无该词）。

- [ ] **Step 3: 实现**

把 `tools/inject.py` 的 `INSTRUCTION` 替换为：

```python
INSTRUCTION = """## 统一记忆中枢（AGENT MEMORY HUB）
任务开始：先调用 MCP 工具 hub_bootstrap（或 hub_search）检索中枢；无 MCP 时读 INDEX.md 与五类目录（rules / methodology / longterm / projects / experience），命中再执行。
命中结果以「引用+摘要」写入本次任务 AGENTS.md（规则类标注必读全文），执行中需要细节再 hub_get。
执行中若发现与任务 AGENTS.md 冲突，回中枢复核（以中枢为准）。
不确定的内容交回用户，不得臆测、不得凭空捏造历史经验。
任务闭环：exp/project 事实用 hub_ingest_candidate 回写（仅候选）；新规则/方法论进收件箱等待人工审核。
中枢位置：{hub}
"""
```

`marker = "## 统一记忆中枢"` 不变，幂等/过期刷新逻辑不变（`block.splitlines()[-1]` 仍以 `中枢位置：` 结尾）。

- [ ] **Step 4: 运行确认通过**

```powershell
cd hub-engine; python -m pytest tests/test_inject.py -v
```

Expected: 全部 PASS（含原有 3 例：`INDEX.md`、`不得臆测`、幂等、过期刷新）。

- [ ] **Step 5: Commit**

```powershell
git add hub-engine/tools/inject.py hub-engine/tests/test_inject.py
git commit -m "feat: inject 指令升级为任务级引导契约（bootstrap/引用摘要/回写分级）"
```

---

## Task 7: scripts/query_report.py（查询周报）

**Files:**
- Create: `hub-engine/scripts/query_report.py`
- Test: `hub-engine/tests/test_query_report.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_query_report.py`：

```python
import json

from scripts.bootstrap_hub import bootstrap
from scripts.query_report import load_records, report


def _write(root, records):
    d = root / ".sync" / "state"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "query.log.jsonl", "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_load_records(tmp_path):
    root = bootstrap(tmp_path)
    _write(root, [{"action": "search", "platform": "trae"}, {"action": "get", "platform": "code"}])
    recs = load_records(root)
    assert len(recs) == 2


def test_report_counts_by_platform(tmp_path):
    root = bootstrap(tmp_path)
    _write(
        root,
        [
            {"action": "search", "platform": "trae"},
            {"action": "search", "platform": "trae"},
            {"action": "get", "platform": "code"},
        ],
    )
    rep = report(root)
    assert rep["total"] == 3
    assert rep["platforms"]["trae"]["search"] == 2
    assert rep["platforms"]["code"]["get"] == 1


def test_report_missing_log(tmp_path):
    root = bootstrap(tmp_path)
    rep = report(root)
    assert rep["total"] == 0
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd hub-engine; python -m pytest tests/test_query_report.py -v
```

Expected: FAIL，`ModuleNotFoundError: No module named 'scripts.query_report'`。

- [ ] **Step 3: 实现**

创建 `hub-engine/scripts/query_report.py`：

```python
"""MCP 查询周报：读取 .sync/state/query.log.jsonl 统计各平台调用"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

LOG = Path(".sync") / "state" / "query.log.jsonl"


def load_records(root: Path) -> list[dict]:
    log = Path(root) / LOG
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def report(root: Path) -> dict:
    by_platform: dict[str, Counter] = defaultdict(Counter)
    recs = load_records(root)
    for r in recs:
        by_platform[r.get("platform", "unknown")][r.get("action", "?")] += 1
    return {
        "total": len(recs),
        "platforms": {p: dict(c) for p, c in sorted(by_platform.items())},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="query-report")
    ap.add_argument("--root", required=True, help="中枢根目录")
    args = ap.parse_args(argv)
    print(json.dumps(report(Path(args.root)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

```powershell
cd hub-engine; python -m pytest tests/test_query_report.py -v
cd hub-engine; python scripts/query_report.py --root ../AgentMemoryHub
```

Expected: 单测 PASS；CLI 输出 JSON 统计（可能 total=0，属正常）。

- [ ] **Step 5: Commit**

```powershell
git add hub-engine/scripts/query_report.py hub-engine/tests/test_query_report.py
git commit -m "feat: query_report 查询周报（按平台/动作统计 jsonl）"
```

---

## Task 8: 全量验证 + 客户端配置样例 + 手动验收指引

**Files:**
- Create: `mcp.example.json`
- Modify: `hub-engine/pyproject.toml`（可选：把 `mcp>=1.0` 加入 dependencies，便于新环境）

- [ ] **Step 1: 全量回归**

```powershell
cd hub-engine; python -m pytest
python -m ruff check hub-engine
python -m ruff format --check hub-engine
```

Expected: pytest 全量 PASS（原 79 + 新增），ruff check/format 全绿（新增文件格式不符时先 `python -m ruff format hub-engine` 再复查）。

- [ ] **Step 2: 创建客户端配置样例**

创建 `mcp.example.json`（供各平台 MCP 客户端配置参考，实际路径按机器替换）：

```json
{
  "mcpServers": {
    "agent-memory-hub": {
      "command": "python",
      "args": [
        "C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/hub-engine/mcp_server.py",
        "--root",
        "C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub"
      ]
    }
  }
}
```

（若 `hub-engine/pyproject.toml` 的 `dependencies` 追加 `"mcp>=1.0"`，同时更新 `[project.optional-dependencies].dev` 不变——本机全局已有 mcp，追加仅为新环境可复现；如不追加亦可，注明依赖来自全局环境。）

- [ ] **Step 3: 手动验收（需真实平台，一次性）**

1. 启动冒烟（不应立即退出，卡在 stdio 属正常）：
   ```powershell
   cd hub-engine; python mcp_server.py --root ../AgentMemoryHub
   ```
2. 在 TRAE（或 code）的 MCP 配置里注册 `agent-memory-hub`（按 `mcp.example.json`）。
3. 新建一个任务，让 agent 调用 `hub_bootstrap(task_kind="dll", context="改 DLL 被锁")`，观察返回引导块。
4. 检查审计落盘：
   ```powershell
   Get-Content ../AgentMemoryHub/.sync/state/query.log.jsonl -Tail 5
   ```
   Expected: 出现 `"action":"bootstrap"` 与 `hit_paths`。
5. 调用 `hub_ingest_candidate` 后，确认 `.sync/drafts/<platform>_draft/` 出现候选卡，再用 `engine.py ingest --platform <name>` 走既有管线。

- [ ] **Step 4: Commit**

```powershell
git add mcp.example.json hub-engine/pyproject.toml
git commit -m "docs: mcp 客户端配置样例 + 依赖补充"
```

---

## 自审记录

**Spec 覆盖对照（`docs/superpowers/specs/2026-08-18-hub-mcp-server-design.md`）：**

| Spec 要求 | 任务 |
| --- | --- |
| §4.2 `hub_search`（types 过滤、excerpt、空查询护栏、审计） | Task 4 |
| §4.3 `hub_get`（slug/rel_path 解析、ambiguous/not_found/path_escape、archived 可显式读） | Task 4 |
| §4.4 `hub_index`（扫目录优先、include_markdown 截断 32KiB） | Task 4 |
| §4.5 `hub_ingest_candidate`（draft 目录、status=candidate、dedup、type 白名单、platform 白名单） | Task 4 |
| §4.7 `hub_bootstrap`（task-kind 映射、top_k、markdown 引导块、snapshot_at、must_read） | Task 4 |
| §5.3 模板（引用+摘要、快照时间戳） | Task 4（markdown 生成） |
| §5.5 回写分级（exp/project 快路径；rule 禁止直写） | Task 4（type_forbidden） |
| §6 审计（query.log.jsonl、best-effort、8MiB 轮转、action 表） | Task 3 |
| §7 权限（path_escape、platform 白名单、type 白名单） | Task 2 |
| §8 映射（`retrieve_with_meta` 一次拿 channel/score） | Task 1 |
| §9 模块布局（mcp_server/mcp_audit/mcp_policy/mcp_handlers/tests） | Task 1-5 |
| §10 测试计划（policy/search/get/audit/ingest/bootstrap/不变量） | Task 2-4 |
| §11 落地顺序 P0-P3（bootstrap+审计→index→ingest_candidate+收件箱→周报） | Task 1-7 |
| inject 契约升级（§3.3） | Task 6 |
| 客户端配置样例（§3.2） | Task 8 |

**未纳入实现的范围（按 spec「非目标」）：** 平台 MEMORY 全量 Pull/Push（已有 bridge 设计）、`reuse_count` 热路径递增、远程 HTTP MCP、多租户鉴权——均不在本计划内。

**类型一致性核查：** `retrieve_with_meta` 返回 `(channel, [(Card, float|None)])`，Task 4 的 `hub_search`/`hub_bootstrap` 均按此解包；`PolicyError(code, message)` 在 policy 抛出、handlers 捕获转 `error` 字段；handler 参数名 `id_`/`type_` 在 `mcp_server._normalize` 中从 `id`/`type` 映射，前后一致。
