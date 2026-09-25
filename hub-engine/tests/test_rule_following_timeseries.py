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
        "# Lint 报告 2026-08-25\n\n- 孤儿页: ['a.md']\n- 陈旧页: []\n- 无效卡片: 21\n- 备注: 共检查 148 张卡片\n",
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
        "# L2 巡检报告 - 2026-09-08\n\n- INDEX 条目总数: 306\n- 权威区文件总数: 307\n- 发现问题数: 40\n",
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


# ──────────────────────── ingest 结果序列（第三数据源）────────────────────────


def _retro_log(monkeypatch, tmp_path: Path, body: str) -> None:
    retro = tmp_path / "retro"
    retro.mkdir(parents=True, exist_ok=True)
    (retro / "log.md").write_text(body, encoding="utf-8")
    monkeypatch.setattr(ts, "RETRO", retro)


def test_ingest_outcomes_counts_both_kinds_per_day(monkeypatch, tmp_path):
    """逐日统计「自动入区」与「重复内容进冲突区」"""
    _retro_log(
        monkeypatch,
        tmp_path,
        "## [2026-08-20] ingest | 自动入区：a.md\n"
        "## [2026-08-20] ingest | 自动入区：b.md\n"
        "## [2026-08-20] ingest | 重复内容进冲突区：c.md\n"
        "## [2026-08-21] ingest | 重复内容进冲突区：d.md\n",
    )
    rows = ts.load_ingest_outcomes()
    assert [r["date"] for r in rows] == ["2026-08-20", "2026-08-21"]
    d1, d2 = rows
    assert (d1["promoted"], d1["conflict"], d1["total"]) == (2, 1, 3)
    assert abs(d1["conflict_rate"] - 1 / 3) < 1e-9
    assert (d2["promoted"], d2["conflict"]) == (0, 1)
    assert d2["conflict_rate"] == 1.0


def test_ingest_outcomes_ignores_non_header_lines(monkeypatch, tmp_path):
    """只认 `## [date] ingest | ...` 叙事标题——审计行 `ingest:promote` 不得被算入
    （实测两者卡名零重叠，混计会虚构出一个不存在的通道）"""
    _retro_log(
        monkeypatch,
        tmp_path,
        "## [2026-08-20] ingest | 自动入区：a.md\n"
        "- 2026-08-20 12:00 ingest:promote b from trae\n"
        "- ingest：`{'promoted': 1, 'duplicate': 4}`\n",
    )
    rows = ts.load_ingest_outcomes()
    assert len(rows) == 1
    assert rows[0]["promoted"] == 1, "审计行不得被计入 promoted"
    assert rows[0]["conflict"] == 0


def test_ingest_outcomes_missing_log_returns_empty(monkeypatch, tmp_path):
    """log.md 不存在时返回空表（不抛）"""
    retro = tmp_path / "retro"
    retro.mkdir(parents=True)
    monkeypatch.setattr(ts, "RETRO", retro)
    assert ts.load_ingest_outcomes() == []


# ────────────────────── 冲突判决分解（真重复 vs 误杀）──────────────────────


def test_verdicts_classify_all_four_kinds(monkeypatch, tmp_path):
    """四种注记必须分别归类——混淆就会把「误杀」当成「真重复」"""
    _retro_log(
        monkeypatch,
        tmp_path,
        "## [2026-08-20] ingest | 重复内容进冲突区：a.md（LLM 建议 merge，待人工终审）\n"
        "## [2026-08-20] ingest | 重复内容进冲突区：b.md（LLM 建议 create，待人工终审）\n"
        "## [2026-08-20] ingest | 重复内容进冲突区：c.md（LLM 建议 review，待人工终审）\n"
        "## [2026-08-20] ingest | 重复内容进冲突区：d.md\n",
    )
    got = {r["card"]: r["kind"] for r in ts.load_ingest_verdicts()}
    assert got == {
        "a.md": "真重复",  # merge
        "b.md": "误杀",  # create
        "c.md": "不确定",  # review
        "d.md": "无注记",  # 早期无判决
    }


def test_verdicts_survive_halfwidth_parens_and_missing_close(monkeypatch, tmp_path):
    """实测存在 半宽括号 / 缺右括号 的条目，必须仍能解析出卡名与判决"""
    _retro_log(
        monkeypatch,
        tmp_path,
        "## [2026-08-20] ingest | 重复内容进冲突区：x.md (LLM 建议 merge, 待人工终审)\n"
        "## [2026-08-21] ingest | 重复内容进冲突区：y.md（LLM 建议 create，待人工终审\n",
    )
    rows = ts.load_ingest_verdicts()
    assert [r["card"] for r in rows] == ["x.md", "y.md"]
    assert [r["kind"] for r in rows] == ["真重复", "误杀"]


def test_verdicts_ignore_non_conflict_headers(monkeypatch, tmp_path):
    """自动入区 与 ingest 统计块不得混入判决序列"""
    _retro_log(
        monkeypatch,
        tmp_path,
        "## [2026-08-20] ingest | 自动入区：a.md\n- ingest：`{'promoted': 1, 'duplicate': 4}`\n",
    )
    assert ts.load_ingest_verdicts() == []
