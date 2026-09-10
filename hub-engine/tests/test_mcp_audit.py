import json

from scripts.bootstrap_hub import bootstrap
from tools.mcp_audit import append_query_log, audit_id, query_log_files


def test_audit_id_shape():
    aid = audit_id()
    assert aid.count("-") == 1
    assert "T" in aid.split("-")[0]


def test_append_query_log_writes_line(tmp_path):
    root = bootstrap(tmp_path)
    append_query_log(
        root, {"audit_id": "a1", "action": "search", "platform": "trae", "ok": True}
    )
    files = query_log_files(root)
    assert files, "应至少有一个 query.log 文件"
    # 取最新（按日切分的今日文件）
    latest = files[0]
    assert latest.exists()
    rec = json.loads(latest.read_text(encoding="utf-8").strip().splitlines()[0])
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


def test_query_log_files_returns_daily(tmp_path):
    """query_log_files 应包含按日切分文件"""
    root = bootstrap(tmp_path)
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone(timedelta(hours=+8))).strftime("%Y-%m-%d")
    state = root / ".sync" / "state"
    state.mkdir(parents=True, exist_ok=True)

    # 模拟三日历史文件
    for date_str in ("2026-09-05", "2026-09-06", today):
        (state / f"query.log-{date_str}.jsonl").write_text(
            json.dumps({"ts": "2026-09-07T00:00:00+08:00", "action": "search"}) + "\n",
            encoding="utf-8",
        )
    files = query_log_files(root)
    names = [f.name for f in files]
    # 应有 3 个按日切分文件，按日期降序
    assert len(files) == 3
    assert names[0] == f"query.log-{today}.jsonl"
    assert names[2] == "query.log-2026-09-05.jsonl"


def test_query_log_files_includes_legacy(tmp_path):
    """旧版 query.log.jsonl 应被兼容识别"""
    root = bootstrap(tmp_path)
    state = root / ".sync" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "query.log.jsonl").write_text(
        json.dumps({"ts": "2026-09-07T00:00:00+08:00", "action": "search"}) + "\n",
        encoding="utf-8",
    )
    files = query_log_files(root)
    names = [f.name for f in files]
    assert "query.log.jsonl" in names


def test_query_log_files_empty_when_no_state(tmp_path):
    """state 目录不存在时返回空列表"""
    root = bootstrap(tmp_path)
    # 确保 state 目录不存在
    state = root / ".sync" / "state"
    if state.exists():
        import shutil

        shutil.rmtree(state)
    assert query_log_files(root) == []
