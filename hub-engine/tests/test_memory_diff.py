"""memory_diff 结构化变更审计（OpenViking 路径 C）单测。"""

from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools import memory_diff
from tools.memory_diff import LOG_NAME, read_records, record


def test_record_writes_add_and_read(tmp_path):
    root = bootstrap(tmp_path)
    p = record(root, {"op": "add", "name": "a.md", "after": "experience/a.md"})
    assert p is not None and p.name == LOG_NAME
    recs = read_records(root)
    assert recs[0]["op"] == "add"
    assert recs[0]["after"] == "experience/a.md"


def test_record_preserves_before_and_deleted_content(tmp_path):
    root = bootstrap(tmp_path)
    record(
        root,
        {
            "op": "update",
            "name": "b.md",
            "before": "旧正文",
            "after": "新正文",
            "deleted_content": None,
        },
    )
    record(
        root,
        {"op": "delete", "name": "c.md", "deleted_content": "被删的正文片段"},
    )
    recs = read_records(root)
    assert recs[0]["op"] == "update" and recs[0]["before"] == "旧正文"
    assert recs[1]["op"] == "delete" and recs[1]["deleted_content"] == "被删的正文片段"


def test_read_records_tolerates_bad_lines(tmp_path):
    """残行（非法 JSON）容忍跳过，不影响有效记录读取"""
    root = bootstrap(tmp_path)
    record(root, {"op": "add", "name": "ok.md"})
    log = root / ".sync" / "state" / LOG_NAME
    with open(log, "a", encoding="utf-8") as f:
        f.write("{oops, not json}\n")
    record(root, {"op": "add", "name": "ok2.md"})
    recs = read_records(root)
    assert [r.get("name") for r in recs] == ["ok.md", "ok2.md"]


def test_record_failure_returns_none(tmp_path, monkeypatch):
    """审计写失败 → 返回 None 且不抛错（不阻断写回主流程）"""
    root = bootstrap(tmp_path)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(memory_diff, "_log_path", boom)
    assert record(root, {"op": "add", "name": "a.md"}) is None


def test_noop_record_writes_null_op(tmp_path):
    """空操作也给零计数结构（对齐 OpenViking memory_diff 空操作语义）"""
    root = bootstrap(tmp_path)
    record(root, {"op": "noop"})
    recs = read_records(root)
    assert recs[0]["op"] == "noop"


def test_memory_diff_under_sync_state(tmp_path):
    """日志路径固定落 .sync/state/memory_diff.jsonl（与 query.log 同源可核）"""
    root = bootstrap(tmp_path)
    p = record(root, {"op": "noop"})
    assert str(p).replace("\\", "/").endswith(".sync/state/memory_diff.jsonl")
    assert Path(p).parent == root / ".sync" / "state"