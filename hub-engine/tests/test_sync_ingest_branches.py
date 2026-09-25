# @version V1.0 / 2026-09-25 / SPLIT 前置：sync.ingest 分支的 fixture 级测试
"""`sync.ingest` 的分支级测试（拆分前先立网，拆分后用于验证行为等价）。

## 为什么先补这批

`sync.py::ingest` 是 229 行的中枢**写入路径**（单写者 + 判重 + 冲突区），
审计 P2-b 点名要拆，但拆分必须能证明"行为不变"。原有 `tests/test_sync.py`
覆盖了 6 条主干（低风险入区 / rule 待确认 / 重复进冲突 / 同名不覆盖 / exp 改挪），
**未覆盖**的分支正是拆分时最容易碰坏的部分：

- 草稿目录缺失 / `strict_lint` 阻断 / 坏 frontmatter / `validate_card` 失败
- 蓝图保留 `reference` 状态（vs 其它低风险卡置 `active`）
- LLM 决策四条路径：skip 高置信丢弃 / create 高置信入区 / create 但同名 → 冲突区 / merge → 冲突区 + `.pred.json`
- `_commit` 抛错时写入 `stat["status"]`

LLM 相关分支用 monkeypatch 顶替 `dedup_candidates` / `dedup_decide`，**不打网络**。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sync as sync_mod
from common.frontmatter import parse_card, write_card
from scripts.bootstrap_hub import bootstrap
from sync import ingest


def _drafts_dir(root: Path, platform: str) -> Path:
    d = root / ".sync" / "drafts" / f"{platform}_draft"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_draft(
    root: Path,
    platform: str = "trae",
    name: str = "draft.md",
    *,
    ctype: str = "longterm",
    status: str = "candidate",
    body: str = "这是一条足够长的正文内容，用于避免薄卡判定。",
    raw: str | None = None,
) -> Path:
    p = _drafts_dir(root, platform) / name
    if raw is not None:
        p.write_text(raw, encoding="utf-8")
        return p
    card = parse_card(
        f"---\ntype: {ctype}\ntags:\n  - test\nupdated: 2026-08-17\nstatus: {status}\nreuse_count: 0\n---\n{body}\n"
    )
    p.write_text(write_card(card), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 前置门禁与非法输入
# ---------------------------------------------------------------------------


def test_missing_drafts_dir_is_noop(tmp_path):
    """草稿目录不存在 → 空统计 + status ok（不建目录、不报错）。"""
    stat = ingest(tmp_path, "trae")
    assert stat["status"] == "ok"
    assert stat["promoted"] == stat["pending"] == stat["duplicate"] == stat["invalid"] == 0
    assert not (tmp_path / ".sync" / "drafts" / "trae_draft").exists()


def test_strict_lint_blocks_before_any_write(tmp_path):
    """strict_lint=True 且草稿 frontmatter 不合规 → status=lint_blocked，草稿原样保留。"""
    root = bootstrap(tmp_path)
    p = _make_draft(root, name="bad.md", raw="没有 frontmatter 的正文\n")
    stat = ingest(root, "trae", strict_lint=True)
    assert stat["status"] == "lint_blocked"
    assert stat["lint_errors"]
    assert p.exists(), "被门禁拦下的草稿不得移动/删除"
    assert stat["promoted"] == 0


def test_soft_lint_records_errors_but_continues(tmp_path):
    """默认软门禁：记录 errors，但仍继续处理（坏卡计 invalid）。"""
    root = bootstrap(tmp_path)
    _make_draft(root, name="bad.md", raw="没有 frontmatter 的正文\n")
    stat = ingest(root, "trae")
    assert stat["lint_errors"]
    assert stat["status"] == "ok"


def test_unreadable_frontmatter_counts_invalid(tmp_path):
    root = bootstrap(tmp_path)
    _make_draft(root, name="broken.md", raw="---\nnot: [valid\n---\n正文\n")
    stat = ingest(root, "trae")
    assert stat["invalid"] == 1
    assert stat["promoted"] == 0


def test_validate_card_failure_counts_invalid(tmp_path):
    """frontmatter 能解析但字段非法（status/type 不在枚举内）→ 计 invalid，不入区。"""
    root = bootstrap(tmp_path)
    _make_draft(
        root,
        name="badstatus.md",
        raw="---\ntype: longterm\ntags:\n  - t\nupdated: 2026-08-17\nstatus: 不存在的状态\n---\n正文\n",
    )
    stat = ingest(root, "trae")
    assert stat["invalid"] == 1
    assert not (root / "longterm" / "badstatus.md").exists()


# ---------------------------------------------------------------------------
# 状态与类型路由
# ---------------------------------------------------------------------------


def test_rule_draft_pending_gets_candidate_status(tmp_path):
    """高风险（rule）→ 落 .sync/pending/ 且**状态改为 candidate**（等人工确认）。"""
    root = bootstrap(tmp_path)
    _make_draft(root, name="r1.md", ctype="rule", status="active", body="规则正文内容足够长。")
    stat = ingest(root, "trae")
    pending = root / ".sync" / "pending" / "r1.md"
    assert stat["pending"] == 1
    assert pending.exists()
    assert "status: candidate" in pending.read_text(encoding="utf-8")
    assert not (root / "rules" / "r1.md").exists()


def test_blueprint_keeps_declared_reference_status(tmp_path):
    """蓝图保留草稿声明的 status（reference），其它低风险卡才会被改成 active。"""
    root = bootstrap(tmp_path)
    _make_draft(root, name="bp.md", ctype="blueprint", status="reference", body="蓝图正文内容足够长。")
    stat = ingest(root, "trae")
    promoted = root / "blueprints" / "bp.md"
    assert stat["promoted"] == 1
    assert "status: reference" in promoted.read_text(encoding="utf-8")


def test_low_risk_promote_sets_active(tmp_path):
    root = bootstrap(tmp_path)
    _make_draft(root, name="lt.md", ctype="longterm", status="candidate")
    ingest(root, "trae")
    assert "status: active" in (root / "longterm" / "lt.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# LLM 去重决策的四条路径（monkeypatch，不打网络）
# ---------------------------------------------------------------------------


@pytest.fixture()
def with_candidates(monkeypatch):
    """让 ingest 认为「有重复候选」，并把 dedup_decide 换成可注入的桩。"""

    def _apply(decision: dict | None):
        monkeypatch.setattr(sync_mod, "dedup_candidates", lambda root, card: [("some-card", 0.9)])
        monkeypatch.setattr(sync_mod, "dedup_decide", lambda *a, **k: decision)

    return _apply


def test_llm_skip_high_confidence_discards_draft(tmp_path, with_candidates):
    """LLM 高置信 skip(≥0.8) → 草稿直接丢弃，既不进冲突区也不入区。"""
    root = bootstrap(tmp_path)
    p = _make_draft(root, name="dup.md")
    with_candidates({"action": "skip", "confidence": 0.92, "reason": "真重复"})

    stat = ingest(root, "trae", chat_fn=lambda *a, **k: "unused")

    assert stat["duplicate"] == 1
    assert not p.exists()
    assert not (root / ".sync" / "conflicts" / "trae_dup.md").exists()


def test_llm_create_high_confidence_promotes(tmp_path, with_candidates):
    """LLM 高置信 create(≥0.8) 且非高风险 → 视作无有效候选，直接入区。"""
    root = bootstrap(tmp_path)
    _make_draft(root, name="draft.md")
    with_candidates({"action": "create", "confidence": 0.9, "reason": "主题不同"})

    stat = ingest(root, "trae", chat_fn=lambda *a, **k: "unused")

    assert stat["promoted"] == 1
    assert (root / "longterm" / "draft.md").exists()


def test_llm_create_but_same_name_conflicts(tmp_path, with_candidates):
    """LLM 判 create 但权威区已存在同名 → 不覆盖，回收进冲突区。"""
    root = bootstrap(tmp_path)
    _drafts_dir(root, "trae")
    (root / "longterm").mkdir(parents=True, exist_ok=True)
    (root / "longterm" / "draft.md").write_text("旧内容", encoding="utf-8")
    _make_draft(root, name="draft.md")
    with_candidates({"action": "create", "confidence": 0.9, "reason": "同主题不同内容"})

    stat = ingest(root, "trae", chat_fn=lambda *a, **k: "unused")

    assert stat["promoted"] == 0
    assert (root / ".sync" / "conflicts" / "trae_draft.md").exists()
    assert (root / "longterm" / "draft.md").read_text(encoding="utf-8") == "旧内容"


def test_llm_merge_decision_conflicts_with_prediction_sidecar(tmp_path, with_candidates):
    """merge/review 类决策 → 进冲突区 + 伴生 .pred.json 留痕（供人工终审）。"""
    root = bootstrap(tmp_path)
    _make_draft(root, name="maybe.md")
    with_candidates({"action": "merge", "confidence": 0.5, "reason": "疑似互补"})

    stat = ingest(root, "trae", chat_fn=lambda *a, **k: "unused")

    cdir = root / ".sync" / "conflicts"
    assert stat["duplicate"] == 1
    assert (cdir / "trae_maybe.md").exists()
    assert (cdir / "trae_maybe.pred.json").exists()


def test_llm_decision_low_confidence_never_auto_promotes(tmp_path, with_candidates):
    """create 但置信度 0.5（<0.8）→ 不自动入区，交冲突区（保守优先）。"""
    root = bootstrap(tmp_path)
    _make_draft(root, name="draft.md")
    with_candidates({"action": "create", "confidence": 0.5, "reason": "不确定"})

    stat = ingest(root, "trae", chat_fn=lambda *a, **k: "unused")

    assert stat["promoted"] == 0
    assert (root / ".sync" / "conflicts" / "trae_draft.md").exists()


# ---------------------------------------------------------------------------
# 提交阶段
# ---------------------------------------------------------------------------


def test_commit_runtime_error_lands_in_status(tmp_path, monkeypatch):
    """_commit 抛 RuntimeError（如写锁不可用）→ 记进 stat['status']，不抛穿到调用方。"""
    root = bootstrap(tmp_path)
    _make_draft(root, name="x.md")
    monkeypatch.setattr(sync_mod, "_commit", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("writer busy")))

    stat = ingest(root, "trae")

    assert stat["status"] == "writer busy"
