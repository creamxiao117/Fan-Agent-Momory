import json

from scripts.bootstrap_hub import bootstrap
from scripts.query_report import load_records, report


def _write(root, records):
    d = root / ".sync" / "state"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "query.log.jsonl", "a", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def test_load_records(tmp_path):
    root = bootstrap(tmp_path)
    _write(
        root,
        [
            {"action": "search", "platform": "trae"},
            {"action": "get", "platform": "code"},
        ],
    )
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
