# @version V1.0 / 2026-09-23 / pi / rule_following_timeseries 的 lint 报告解析测试

"""`load_lint_reports` 单测：两种历史格式都要能解析。

为什么值得测：lint 报告存在**两种格式**（旧 `# Lint 报告` 报 孤儿/无效/幽灵；
新 `# L2 巡检报告` 报“发现问题数”），解析器靠正则分支兼容。
若解析静默失效（如返回空表），T1 的对比会退化成“只有快照一个序列”，
而使用者不会察觉——故用测试锁住两种格式。
"""

from pathlib import Path

import scripts.rule_following_timeseries as ts


def _retro(monkeypatch, tmp_path: Path) -> Path:
    retro = tmp_path / "retro"
    retro.mkdir(parents=True)
    monkeypatch.setattr(ts, "RETRO", retro)
    return retro


def test_parses_old_format_inline_list(monkeypatch, tmp_path):
    """旧格式：`孤儿页: [...]` 内联 + `无效卡片: N`"""
    retro = _retro(monkeypatch, tmp_path)
    (retro / "lint-report-2026-08-25.md").write_text(
        "# Lint 报告 2026-08-25\n\n"
        "- 孤儿页: ['a.md']\n"
        "- 陈旧页: []\n"
        "- 无效卡片: 21\n"
        "- 备注: 共检查 148 张卡片\n",
        encoding="utf-8",
    )
    rows = ts.load_lint_reports()
    assert len(rows) == 1
    r = rows[0]
    assert r["date"] == "2026-08-25"
    assert r["fmt"] == "A"
    assert r["invalid"] == 21
    assert r["orphans"] == 1
    assert r["checked"] == 148


def test_parses_old_format_multiline_list(monkeypatch, tmp_path):
    """旧格式：`孤儿页:` 后跟多行 `- x` 列表"""
    retro = _retro(monkeypatch, tmp_path)
    (retro / "lint-report-2026-08-27.md").write_text(
        "# Lint 报告 2026-08-27\n\n"
        "- 孤儿页:\n"
        "  - experience/a.md\n"
        "  - experience/b.md\n"
        "  - experience/c.md\n"
        "- 幽灵登记: []\n"
        "- 无效卡片: 0\n",
        encoding="utf-8",
    )
    r = ts.load_lint_reports()[0]
    assert r["orphans"] == 3, f"多行列表应计 3 项，实际 {r['orphans']}"
    assert r["ghosts"] == 0
    assert r["invalid"] == 0


def test_parses_new_format_problem_count(monkeypatch, tmp_path):
    """新格式：`# L2 巡检报告` + `发现问题数: N`"""
    retro = _retro(monkeypatch, tmp_path)
    (retro / "lint-report-2026-09-08.md").write_text(
        "# L2 巡检报告 - 2026-09-08\n\n"
        "- INDEX 条目总数: 306\n"
        "- 权威区文件总数: 307\n"
        "- 发现问题数: 40\n",
        encoding="utf-8",
    )
    r = ts.load_lint_reports()[0]
    assert r["fmt"] == "B"
    assert r["problems"] == 40
    assert r["invalid"] == "", "新格式不报 invalid，应为空而非 0（避免当成真值比较）"


def test_empty_report_dir_returns_empty_list(monkeypatch, tmp_path):
    """无报告时返回空表（调用方据此降级，不应崩）"""
    _retro(monkeypatch, tmp_path)
    assert ts.load_lint_reports() == []
