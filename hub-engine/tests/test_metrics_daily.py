"""E1 指标日行脚本（metrics_daily）单测。

覆盖：当日 search/hit/miss/hit_rate 聚合 / reuse 计数 / 跨日过滤 / 无查询 hit_rate=null /
卡片数与向量行数探测 / append 落盘 / 无日志目录容忍。
"""

import json
import sqlite3
from datetime import date

from scripts.metrics_daily import LOG, _total_cards, _vector_rows, append, compute


def _write_log(root, records):
    p = root / LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def _search(ts, hit_count):
    return {
        "ts": ts,
        "action": "search",
        "platform": "t",
        "query": "q",
        "hit_count": hit_count,
    }


def _reuse(ts, n=1):
    return {
        "ts": ts,
        "action": "reuse",
        "platform": "t",
        "name": f"x{n}",
        "hit_count": 0,
    }


def _mkcard(root, sub, name, body="DLL 修改后必须递增版本号避免被锁。"):
    d = root / sub
    d.mkdir(parents=True, exist_ok=True)
    fm = "---\ntype: rule\ntags: [x]\nupdated: 2026-08-19\nstatus: active\nreuse_count: 0\n---\n"
    (d / f"{name}.md").write_text(fm + body, encoding="utf-8")


def _mkvector_db(root, n):
    db = root / ".sync" / "vector.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    try:
        con.execute(
            "CREATE TABLE docs (path TEXT, mtime TEXT, size INT, title TEXT, tags TEXT, type TEXT, body TEXT, embedding BLOB)"
        )
        for i in range(n):
            con.execute("INSERT INTO docs(path) VALUES(?)", (f"rules/c{i}.md",))
        con.commit()
    finally:
        con.close()


def test_hit_miss_hit_rate_aggregation(tmp_path):
    _write_log(
        tmp_path,
        [
            _search("2026-08-19T01:00:00Z", 3),
            _search("2026-08-19T02:00:00Z", 0),
            _search("2026-08-19T03:30:00Z", 1),
        ],
    )
    row = compute(tmp_path, date(2026, 8, 19))
    assert row["search_count"] == 3
    assert row["hit"] == 2
    assert row["miss"] == 1
    assert row["hit_rate"] == round(2 / 3, 4)


def test_cross_date_filter_and_reuse(tmp_path):
    _write_log(
        tmp_path,
        [
            _search("2026-08-19T01:00:00Z", 1),
            _search("2026-08-18T01:00:00Z", 5),  # 另一天，排除
            _reuse("2026-08-19T02:00:00Z"),
            _reuse("2026-08-19T02:05:00Z"),
            _reuse("2026-08-18T02:00:00Z"),  # 另一天，排除
        ],
    )
    row = compute(tmp_path, date(2026, 8, 19))
    assert row["search_count"] == 1
    assert row["hit"] == 1
    assert row["miss"] == 0
    assert row["reuse_ops"] == 2  # 当日 2 条 reuse
    assert row["date"] == "2026-08-19"


def test_no_query_hit_rate_null(tmp_path):
    _mkcard(tmp_path, "rules", "a")
    row = compute(tmp_path, date(2026, 8, 19))
    assert row["search_count"] == 0
    assert row["hit"] == 0
    assert row["miss"] == 0
    assert row["hit_rate"] is None
    assert row["total_cards"] >= 1


def test_total_cards_and_vector_rows(tmp_path):
    _mkcard(tmp_path, "rules", "a")
    _mkcard(tmp_path, "blueprints", "b")
    _mkvector_db(tmp_path, 5)
    row = compute(tmp_path, date(2026, 8, 19))
    assert row["total_cards"] == 2  # rules + blueprints
    assert row["vector_rows"] == 5


def test_append_writes_metrics_jsonl(tmp_path):
    _write_log(tmp_path, [_search("2026-08-19T01:00:00Z", 2)])
    row = compute(tmp_path, date(2026, 8, 19))
    append(tmp_path, row)
    p = tmp_path / ".sync" / "state" / "metrics.jsonl"
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["date"] == "2026-08-19"
    assert json.loads(lines[0])["search_count"] == 1


def test_append_creates_missing_state_dir(tmp_path):
    row = compute(tmp_path, date(2026, 8, 19))
    append(tmp_path, row)
    p = tmp_path / ".sync" / "state" / "metrics.jsonl"
    assert p.exists()


def test_missing_log_returns_empty(tmp_path):
    row = compute(tmp_path, date(2026, 8, 19))
    assert row["search_count"] == 0
    assert row["reuse_ops"] == 0


def test_vector_rows_zero_without_db(tmp_path):
    assert _vector_rows(tmp_path) == 0
    assert _total_cards(tmp_path) == 0  # 无权威目录
