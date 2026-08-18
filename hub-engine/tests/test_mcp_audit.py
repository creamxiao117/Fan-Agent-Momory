import json

from scripts.bootstrap_hub import bootstrap
from tools.mcp_audit import append_query_log, audit_id


def test_audit_id_shape():
    aid = audit_id()
    assert aid.count("-") == 1
    assert "T" in aid.split("-")[0]


def test_append_query_log_writes_line(tmp_path):
    root = bootstrap(tmp_path)
    append_query_log(
        root, {"audit_id": "a1", "action": "search", "platform": "trae", "ok": True}
    )
    log = root / ".sync" / "state" / "query.log.jsonl"
    assert log.exists()
    rec = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[0])
    assert rec["action"] == "search"
    assert rec["platform"] == "trae"
    assert rec["ts"]


def test_append_query_log_best_effort(tmp_path):
    """日志写入失败不抛异常（D4 best-effort）"""
    root = bootstrap(tmp_path)
    state = root / ".sync" / "state"
    # 让 state 目录变成普通文件，导致 mkdir 失败（Windows 上目录不能直接覆盖为文件）
    state.rmdir()
    state.write_text("not a dir", encoding="utf-8")
    append_query_log(root, {"audit_id": "a2", "action": "get"})  # 不应抛异常


def test_audit_id_unique():
    assert len({audit_id() for _ in range(100)}) == 100
