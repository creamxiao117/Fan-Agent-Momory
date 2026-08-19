from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.mcp_handlers import (
    REUSE_STATE,
    hub_bootstrap,
    hub_get,
    hub_index,
    hub_ingest_candidate,
    hub_search,
    record_reuse,
)


def _seed(root: Path) -> None:
    (root / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [autocad, dll-lock]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nDLL 修改后必须递增版本号避免被锁。\n",
        encoding="utf-8",
    )
    (root / "experience" / "blunder.md").write_text(
        "---\ntype: exp\ntags: [autocad]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\n上次没重命名导致 AutoCAD 占用文件无法覆盖。\n",
        encoding="utf-8",
    )
    (root / "methodology" / "occam.md").write_text(
        "---\ntype: methodology\ntags: [thinking]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\n奥卡姆剃刀：最少文件/字段/步骤。\n",
        encoding="utf-8",
    )
    # project 卡用于 bootstrap 分组的 projects 类别（dll 任务映射 rules+projects）
    (root / "projects" / "omniroute.md").write_text(
        "---\ntype: project\ntags: [autocad, dll-project]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nDLL 插件项目：改 DLL 后锁管理。\n",
        encoding="utf-8",
    )


def test_search_deterministic_hit(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_search(root, "dll-lock", platform="trae")
    assert res["ok"] and res["channel"] == "deterministic"
    assert res["hits"][0]["slug"] == "dll-lock"
    assert res["hits"][0]["rel_path"] == "rules/dll-lock.md"


def test_search_empty_query(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_search(root, "   ", platform="trae")
    assert res["ok"] and res["hits"] == [] and res["channel"] == "empty"


def test_search_types_filter(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_search(root, "占用", types=["rule"], top_k=5, platform="trae")
    assert all(h["type"] == "rule" for h in res["hits"])


def test_search_writes_audit(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    hub_search(root, "dll-lock", platform="trae")
    log = root / ".sync" / "state" / "query.log.jsonl"
    assert log.exists()
    assert "search" in log.read_text(encoding="utf-8")


def test_get_by_slug(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_get(root, id_="dll-lock", platform="trae")
    assert res["ok"]
    assert res["card"]["body"] == "DLL 修改后必须递增版本号避免被锁。"
    assert res["card"]["rel_path"] == "rules/dll-lock.md"


def test_get_not_found(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_get(root, id_="nope", platform="trae")
    assert res["ok"] is False and res["error"] == "not_found"


def test_get_path_escape(tmp_path):
    root = bootstrap(tmp_path)
    res = hub_get(root, rel_path="../secret.md", platform="trae")
    assert res["ok"] is False and res["error"] == "path_escape"


def test_index_categories(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_index(root, types=["rules", "experience"], platform="trae")
    assert res["ok"]
    assert {x["slug"] for x in res["categories"]["rules"]} == {"dll-lock"}
    assert {x["slug"] for x in res["categories"]["experience"]} == {"blunder"}


def test_bootstrap_groups_by_kind(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_bootstrap(
        root, "dll", context="改了 DLL 被 AutoCAD 锁住", platform="trae"
    )
    assert res["ok"] and res["task_kind"] == "dll"
    kinds = {b["kind"] for b in res["blocks"]}
    assert kinds == {"rules", "projects"}
    assert "## 中枢命中" in res["markdown"]
    assert "rules/dll-lock.md" in res["markdown"]


def test_bootstrap_unknown_kind_falls_back(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    res = hub_bootstrap(root, "whatever", context="奥卡姆剃刀", platform="trae")
    assert res["task_kind"] == "generic"
    assert "methodology" in {b["kind"] for b in res["blocks"]}


def test_ingest_candidate_writes_draft(tmp_path):
    root = bootstrap(tmp_path)
    (root / "hub.config.yaml").write_text(
        "platforms:\n  trae: {memory_dir: x, target_file: y}\n", encoding="utf-8"
    )
    res = hub_ingest_candidate(
        root, platform="trae", title="测试经验", body="某条经验。"
    )
    assert res["ok"] and res["deduped"] is False
    p = root / ".sync" / "drafts" / "trae_draft" / "测试经验.md"
    assert p.exists() or (root / ".sync" / "drafts" / "trae_draft").exists()
    text = (root / ".sync" / "drafts" / "trae_draft" / f"{res['slug']}.md").read_text(
        encoding="utf-8"
    )
    assert "type: exp" in text
    assert "status: candidate" in text


def test_ingest_candidate_dedup(tmp_path):
    root = bootstrap(tmp_path)
    (root / "hub.config.yaml").write_text(
        "platforms:\n  trae: {memory_dir: x, target_file: y}\n", encoding="utf-8"
    )
    hub_ingest_candidate(root, platform="trae", title="T", body="相同正文")
    res = hub_ingest_candidate(root, platform="trae", title="T", body="相同正文")
    assert res["deduped"] is True


def test_ingest_candidate_rule_forbidden(tmp_path):
    root = bootstrap(tmp_path)
    (root / "hub.config.yaml").write_text(
        "platforms:\n  trae: {memory_dir: x, target_file: y}\n", encoding="utf-8"
    )
    res = hub_ingest_candidate(root, platform="trae", title="R", body="b", type_="rule")
    assert res["ok"] is False and res["error"] == "type_forbidden"


def test_ingest_candidate_unknown_platform_forbidden(tmp_path):
    root = bootstrap(tmp_path)
    res = hub_ingest_candidate(root, platform="unknown", title="X", body="b")
    assert res["ok"] is False and res["error"] == "platform_forbidden"


def _dll(root):
    return (root / "rules" / "dll-lock.md").read_text(encoding="utf-8")


def test_search_tracks_reuse(tmp_path):
    """hub_search 命中 → 命中卡 reuse_count 元数据 +1（A2）"""
    root = bootstrap(tmp_path)
    _seed(root)
    hub_search(root, "dll-lock", platform="trae")
    assert "reuse_count: 1" in _dll(root)


def test_record_reuse_daily_throttle(tmp_path):
    """同卡同本地日多次计数只 +1（节流防抖）"""
    root = bootstrap(tmp_path)
    _seed(root)
    rp = "rules/dll-lock.md"
    assert record_reuse(root, [rp])["counted"] == 1
    r2 = record_reuse(root, [rp])
    assert r2["counted"] == 0 and r2["dup_skipped"] == 1
    assert "reuse_count: 1" in _dll(root)


def test_record_reuse_next_day_counts(tmp_path):
    """跨日（状态记昨天）→ 再次计数 +1"""
    import json

    root = bootstrap(tmp_path)
    _seed(root)
    rp = "rules/dll-lock.md"
    record_reuse(root, [rp])
    assert "reuse_count: 1" in _dll(root)
    # 模拟次日：把节流状态日期改成更早
    st = json.loads((root / REUSE_STATE).read_text(encoding="utf-8"))
    st[rp] = "2026-01-01"
    (root / REUSE_STATE).write_text(json.dumps(st), encoding="utf-8")
    r = record_reuse(root, [rp])
    assert r["counted"] == 1
    assert "reuse_count: 2" in _dll(root)


def test_record_reuse_skips_archived_and_missing_field(tmp_path):
    """归档卡与无 reuse_count 字段卡不计数"""
    root = bootstrap(tmp_path)
    (root / "rules" / "old.md").write_text(
        "---\ntype: rule\ntags: []\nupdated: 2026-08-01\nstatus: archived\nreuse_count: 0\n---\n旧。",
        encoding="utf-8",
    )
    (root / "rules" / "noreuse.md").write_text(
        "---\ntype: rule\ntags: []\nupdated: 2026-08-01\nstatus: active\n---\n无计数字段。",
        encoding="utf-8",
    )
    r = record_reuse(root, ["rules/old.md", "rules/noreuse.md"])
    assert r["counted"] == 0 and r["archived_skipped"] == 1
    assert "reuse_count" not in (root / "rules" / "noreuse.md").read_text(
        encoding="utf-8"
    )


def test_reuse_bump_minimal_diff(tmp_path):
    """只改 reuse_count 行，其余字节保持不变（最小 diff）"""
    root = bootstrap(tmp_path)
    (root / "rules" / "only.md").write_text(
        "---\ntype: exp\ntags: [k, v]\nupdated: 2026-08-01\nstatus: active\nreuse_count: 3\n---\n正文 A。",
        encoding="utf-8",
    )
    p = root / "rules" / "only.md"
    before = p.read_text(encoding="utf-8")
    assert record_reuse(root, ["rules/only.md"])["counted"] == 1
    after = p.read_text(encoding="utf-8")
    assert "reuse_count: 4" in after
    # 除 reuse_count 行外完全一致
    assert before.replace("reuse_count: 3", "reuse_count: 4") == after
