"""中枢每日集中审核清单（抗会话归档）单测。

覆盖：今日新增/更新采集、pending 采集、今日 sleep 候选采集、渲染三区块。
"""

from scripts.hub_review_today import (
    _today_local,
    collect_new_updated,
    collect_pending,
    collect_today_sleep,
    render,
)


def _mk_writer(root, sub, name, body, updated=None):
    p = root / sub / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fm_updated = updated or _today_local().isoformat()
    p.write_text(
        f"---\ntype: exp\ntags:\n- t\nupdated: '{fm_updated}'\nstatus: active\n---\n\n{body}",
        encoding="utf-8",
    )
    return p


def _sleep_proposal(root, ts, date_s):
    pd = root / ".sync" / "state" / "sleep" / ts
    pd.mkdir(parents=True, exist_ok=True)
    (pd / "proposal.json").write_text("{}", encoding="utf-8")
    (pd / "proposal.md").write_text("# p", encoding="utf-8")
    return pd


def _pending_rule(root, name):
    pd = root / ".sync" / "pending"
    pd.mkdir(parents=True, exist_ok=True)
    (pd / name).write_text("---\ntype: rule\nstatus: pending\n---", encoding="utf-8")
    return pd


def _as_posix(path: str) -> str:
    return path.replace("\\", "/")


def test_collect_new_updated_today(tmp_path):
    """updated == 今日 的卡才列入；其它日期不入"""
    _mk_writer(tmp_path, "experience", "today.md", "今日卡")
    _mk_writer(tmp_path, "rules", "old.md", "旧卡", updated="2000-01-01")
    got = collect_new_updated(tmp_path)
    files = [_as_posix(c["file"]) for c in got]
    assert "experience/today.md" in files
    assert "rules/old.md" not in files
    assert got[0]["tags"] == ["t"]


def test_collect_pending(tmp_path):
    """pending 目录下的 *.md 相对路径列出；无目录为空"""
    _pending_rule(tmp_path, "rule-a.md")
    got = [_as_posix(p) for p in collect_pending(tmp_path)]
    assert got == ["rule-a.md"]


def test_collect_pending_empty_dir(tmp_path):
    """无 pending 目录 → 空列表"""
    assert collect_pending(tmp_path) == []


def test_collect_today_sleep(tmp_path):
    """只取日期前缀含今日的 sleep 提案"""
    today = _today_local().isoformat().replace("-", "")
    _sleep_proposal(tmp_path, "20200101-000000", "2020-01-01")
    _sleep_proposal(tmp_path, f"{today}-000000", today)
    paths = collect_today_sleep(tmp_path)
    assert len(paths) == 1
    assert today in paths[0]


def test_render_sections(tmp_path):
    """渲染含三区块、空态显示（无新增/无 pending/无 sleep）"""
    md = render({"date": "2026-08-20"}, [], [], [])
    assert "新增/更新卡" in md and "（本日无新增/更新卡）" in md
    assert "待确认 rule" in md and "（无待确认）" in md
    assert "sleep 候选" in md and "（今日无夜间提案候选）" in md


def test_render_with_items(tmp_path):
    """填充态：新增表、pending 项、sleep 项均展示"""
    new = [
        {"file": "experience/a.md", "type": "exp", "status": "active", "tags": ["t"]}
    ]
    md = render({"date": "2026-08-20"}, new, ["rule-a.md"], ["sleep/p/proposal.md"])
    assert "experience/a.md" in md
    assert "rule-a.md" in md
    assert "sleep/p/proposal.md" in md
