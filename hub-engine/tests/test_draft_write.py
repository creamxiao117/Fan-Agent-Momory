# @version V1.0 / 2026-11-02 / pi / draft-write CLI 与平台活跃度检查的单测
"""`draft-write`（回写闭环入口）与 `platform_activity`（通道死掉的早期信号）单测。

为什么测这两个：
- `draft-write` 是**唯一**能让 pi 扩展落盘的入口 ⇒ 它坏了 = 回写闭环断（且**静默**）。
- `platform_activity` 是「通道死掉」的**唯一**探测器 ⇒ 它误报 = 报警即噪音 ⇒ 报警被忽略。
"""

import json
from pathlib import Path

from commands.draft_write import _auto_slug, cmd_draft_write
from scripts.capability_reconcile import platform_activity


class _Args:
    def __init__(self, **kw):
        self.root = kw.get("root")
        self.platform = kw.get("platform", "pi")
        self.title = kw.get("title", "t")
        self.body = kw.get("body", "b")
        self.body_file = kw.get("body_file", "")
        self.type = kw.get("type", "exp")
        self.tags = kw.get("tags", "")
        self.slug = kw.get("slug", "")


def _hub(tmp_path: Path) -> Path:
    """最小中枢：.sync/drafts 目录 + hub.config.yaml（平台授权要读它）。"""
    hub = tmp_path / "AgentMemoryHub"
    (hub / ".sync" / "drafts").mkdir(parents=True)
    (hub / "hub.config.yaml").write_text(
        "authority_dirs: [rules, methodology, experience]\nplatforms:\n  pi:\n    role: contributor\n",
        encoding="utf-8",
    )
    return hub


def test_draft_write_creates_card_in_draft_root(tmp_path, capsys):
    """回写必须落在 `.sync/drafts/<platform>_draft/` **根目录**（子目录不会被 ingest 提升）。"""
    hub = _hub(tmp_path)
    rc = cmd_draft_write(_Args(root=str(hub), title="draft write round trip", body="正文内容", tags="a,b"))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is True
    p = hub / ".sync" / "drafts" / "pi_draft" / f"{payload['slug']}.md"
    assert p.is_file(), p
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "type: exp" in text and "status: candidate" in text


def test_draft_write_refuses_rule_type(tmp_path, capsys):
    """贡献者**禁直写 rule/methodology**（高风险档必须走人工授权）。"""
    hub = _hub(tmp_path)
    rc = cmd_draft_write(_Args(root=str(hub), title="x", body="y", type="rule"))
    assert rc == 1
    out = capsys.readouterr().out
    assert '"ok": false' in out
    assert not list((hub / ".sync" / "drafts" / "pi_draft").glob("*.md"))


def test_auto_slug_falls_back_for_chinese_title():
    """纯中文标题 ⇒ ASCII 化后为空 ⇒ 必须给**唯一可溯源**的兜底 slug。"""
    s = _auto_slug("冒烟：pi 回写入口", "pi", "exp")
    assert s.startswith("pi-exp-")
    assert len(s.split("-")[-1]) == 6
    # 同一标题 ⇒ 同一 slug（幂等）；不同标题 ⇒ 不同 slug
    assert s == _auto_slug("冒烟：pi 回写入口", "pi", "exp")
    assert s != _auto_slug("另一个标题", "pi", "exp")


def test_auto_slug_keeps_ascii_kebab():
    assert _auto_slug("Draft Write Round Trip", "pi", "exp") == "draft-write-round-trip"


def test_draft_write_accepts_full_card_without_double_frontmatter(tmp_path, capsys):
    """传入**完整卡**（含 frontmatter）时不得产生双 frontmatter（实测踩过：第二层会变成正文噪声）。"""
    hub = _hub(tmp_path)
    full = "---\ntype: exp\ntags: [x, y]\nupdated: '2026-01-01'\nstatus: candidate\n---\n\n# 标题\n\n正文\n"
    rc = cmd_draft_write(_Args(root=str(hub), title="full card", body=full, type=""))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    text = (hub / ".sync" / "drafts" / "pi_draft" / f"{payload['slug']}.md").read_text(encoding="utf-8")
    assert text.count("\n---\n") == 1, f"只允许一个 frontmatter 闭合块，实际：\n{text[:200]}"
    assert "- x" in text and "- y" in text, "卡自带的 tags 应被采纳"
    assert "# 标题" in text


def _log(root: Path, rows: list[dict]) -> None:
    d = root / ".sync" / "state"
    d.mkdir(parents=True, exist_ok=True)
    (d / "query.log-2026-11-02.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
    )


def _registered_hub(tmp_path: Path) -> Path:
    """带平台登记的中枢（活跃度只对**注册平台**判警）。"""
    hub = tmp_path / "AgentMemoryHub"
    (hub / ".sync" / "state").mkdir(parents=True, exist_ok=True)
    (hub / "hub.config.yaml").write_text(
        "platforms:\n  pi:\n    role: contributor\n  workbuddy:\n    role: contributor\n",
        encoding="utf-8",
    )
    return hub


def test_platform_activity_flags_recently_used_but_now_silent(tmp_path):
    """近 30 天用过、近 7 天零检索 ⇒ 列为「通道可能已死」（silent）。"""
    hub = _registered_hub(tmp_path)
    _log(
        hub,
        [
            {"ts": "2026-11-02T01:00:00+08:00", "platform": "pi", "action": "bootstrap"},
            {"ts": "2026-10-20T01:00:00+08:00", "platform": "workbuddy", "action": "search"},
        ],
    )
    act = platform_activity(hub, days=7)
    assert act["active"].get("pi") == 1
    assert [s["platform"] for s in act["silent"]] == ["workbuddy"]


def test_platform_activity_ignores_long_unused_platform(tmp_path):
    """很久没用的平台**不算 silent**（不是「通道死了」，只是「没在用」）。"""
    hub = _registered_hub(tmp_path)
    _log(
        hub,
        [
            {"ts": "2026-11-02T01:00:00+08:00", "platform": "pi", "action": "bootstrap"},
            {"ts": "2026-01-02T01:00:00+08:00", "platform": "workbuddy", "action": "search"},
        ],
    )
    act = platform_activity(hub, days=7)
    assert act["silent"] == []


def test_platform_activity_ignores_never_seen_platforms(tmp_path):
    """从未出现过的平台**不算 silent**（否则天天误报 ⇒ 报警被忽略）。"""
    hub = _registered_hub(tmp_path)
    _log(hub, [{"ts": "2026-11-02T01:00:00+08:00", "platform": "pi", "action": "bootstrap"}])
    act = platform_activity(hub, days=7)
    assert act["silent"] == []
    assert act["seen"] == {"pi": 1}


def test_platform_activity_ignores_unregistered_platform_names(tmp_path):
    """账本里的**非平台噪声**（unknown/e2e-test/…）不得进静默名单。"""
    hub = _registered_hub(tmp_path)
    _log(
        hub,
        [
            {"ts": "2026-10-20T01:00:00+08:00", "platform": "unknown", "action": "search"},
            {"ts": "2026-11-02T01:00:00+08:00", "platform": "pi", "action": "bootstrap"},
        ],
    )
    act = platform_activity(hub, days=7)
    assert act["silent"] == []
    assert "unknown" not in act["active"]
