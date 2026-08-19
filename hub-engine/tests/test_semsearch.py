"""semsearch（方案 A：bge-small-zh + SQLite 向量）单测。

策略：用 monkeypatch 替换 semsearch.embed 为确定性假实现，不加载真实模型/不联网。
覆盖：build 增量复用 / 新增 / 更新 / 孤儿清理 / vector_scores 余弦排序 / 空库退化。
"""

from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools import semsearch
from tools.retrieve import (
    _index,
    _rrf_fuse,
    retrieve,
    semantic_vector_retrieve,
)
from tools.semsearch import build, db_path, set_embed_backend, vector_scores


def _fake_embed(fn=None):
    """构造确定性假 embed：基于输入文本的字符正余弦对，长度 8 的 L2 归一化向量。"""
    import math

    def fake(text: str):
        h = sum(ord(c) for c in text)
        v = [math.sin((i + 1) * h) % 2 - 1 for i in range(8)]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    set_embed_backend(fake if fn is None else fn)


def _seed(root: Path) -> None:
    (root / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [autocad, dll-lock]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\nDLL 修改后必须递增版本号避免被锁。\n",
        encoding="utf-8",
    )
    (root / "experience" / "blunder.md").write_text(
        "---\ntype: exp\ntags: [autocad]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n上次没重命名导致 AutoCAD 占用文件无法覆盖。\n",
        encoding="utf-8",
    )


def _vector_rows(db: Path):
    """读库中 path→embedding 映射（用于断言增量）"""
    import sqlite3

    conn = sqlite3.connect(db)
    try:
        return dict(conn.execute("SELECT path, embedding FROM docs").fetchall())
    finally:
        conn.close()


def test_build_inserts_and_embeds(tmp_path):
    """首次 build：插入所有卡并全部 embedding"""
    root = bootstrap(tmp_path)
    _seed(root)
    _fake_embed()
    st = build(root)
    assert st["inserted"] >= 2
    assert st["reused"] == 0
    assert st["embedded"] >= 2
    db = db_path(root)
    assert db.exists()
    rows = _vector_rows(db)
    assert any("dll-lock.md" in p for p in rows)
    # 所有行都有向量（假 embed 始终返回 → embedded=行数）
    assert all(v is not None for v in rows.values())


def test_build_incremental_reuses_unchanged(tmp_path):
    """第二次 build：未变更卡全部复用（不重新 embedding）"""
    root = bootstrap(tmp_path)
    _seed(root)
    _fake_embed()
    st1 = build(root)
    st2 = build(root)
    assert st2["inserted"] == 0
    assert st2["reused"] >= st1["inserted"]
    assert st2["embedded"] == 0  # mock 直查：build 里 embedded 因旧行复用而不触发


def test_build_updates_changed_card(tmp_path):
    """卡片内容变更（mtime/size 变化）：该卡更新并重新 embedding"""
    root = bootstrap(tmp_path)
    _seed(root)
    _fake_embed()
    build(root)
    # 修改 dll-lock 内容 → size/mtime 变化
    (root / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [autocad, dll-lock]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\nDLL 修改后必须递增版本号避免被锁，同时备份。\n",
        encoding="utf-8",
    )
    st = build(root)
    assert st["updated"] >= 1
    # 其余卡保持 reused
    assert st["reused"] + st["updated"] >= 2


def test_build_removes_orphan(tmp_path):
    """源卡删除：孤儿行从库中清理"""
    root = bootstrap(tmp_path)
    _seed(root)
    _fake_embed()
    build(root)
    blunder = root / "experience" / "blunder.md"
    blunder.unlink()
    st = build(root)
    assert st["removed"] >= 1
    rows = _vector_rows(db_path(root))
    assert not any("blunder.md" in p for p in rows)


def test_vector_scores_ranks_by_similarity(tmp_path):
    """vector_scores：query 向量与其最相似卡得分最高且排最前"""
    root = bootstrap(tmp_path)
    _seed(root)
    # 假 embed 里 h=sum(ord)，让 query 与含相同首字母的文本更近——
    # 直接用 dll-lock 的 body 文本作 query，期望它自匹配最相似
    _fake_embed()
    build(root)
    q_vec = semsearch.embed("DLL 修改后必须递增版本号避免被锁")
    scored = vector_scores(root, q_vec)
    assert len(scored) >= 1
    assert scored[0][0].endswith("dll-lock.md")
    assert all(isinstance(s, float) for _, s in scored)
    scores = [s for _, s in scored]
    assert scores == sorted(scores, reverse=True)


def test_vector_scores_empty_db_returns_empty(tmp_path, monkeypatch):
    """空库/未 build → 返回 []（上游融合退化兜底）"""
    root = Path(tmp_path)
    assert vector_scores(root, [0.0, 1.0]) == []


def test_embed_backend_unavailable_returns_none(tmp_path, monkeypatch):
    """当 embed 后端抛错/不可用 → embed 返回 None 即退化（build 不写入向量但成功）"""
    root = bootstrap(tmp_path)
    _seed(root)

    def broken(text: str):
        raise RuntimeError("no backend")

    set_embed_backend(broken)
    st = build(root)
    # embedded=0，行数仍在（向量列为空/未写），不抛错
    assert st["embedded"] == 0
    rows = _vector_rows(db_path(root))
    assert all(v is None for v in rows.values())
    set_embed_backend(None)  # 复位默认


def test_db_path_is_under_sync(tmp_path):
    """向量库路径固定在中枢 .sync/vector.db"""
    root = bootstrap(tmp_path)
    assert str(db_path(root)).replace("\\", "/").endswith(".sync/vector.db")


def test_rrf_fuse_surfaces_vector_only_card(tmp_path):
    """RRF 融合：两通道共现卡 rank 分更高；仅向量通道召回的卡也能上榜"""
    root = bootstrap(tmp_path)
    _seed(root)
    c0, c1 = _index(root).cards[:2]
    # 词袋通道：c0 第 1、c1 第 2；向量通道：仅 c1（语义独有召回）
    # score: c1 = 1/61+1/61，c0 = 1/61 → c1 排前
    fused = _rrf_fuse([(c0, 1.0), (c1, 0.8)], [(c1, 0.9)], top_k=2)
    assert [c.path.name for c, _ in fused] == [c1.path.name, c0.path.name]


def test_semantic_vector_retrieve_reads_built_db(tmp_path):
    """建库后向量通道能按 query 余弦召回卡，最相似卡排最前"""
    root = bootstrap(tmp_path)
    _seed(root)
    _fake_embed()
    build(root)
    hits = semantic_vector_retrieve(root, "DLL 修改后必须递增版本号避免被锁")
    assert hits and hits[0][0].path.name == "dll-lock.md"


def test_semantic_vector_retrieve_empty_db_returns_empty(tmp_path):
    """未建库 → 向量通道返回 []（融合兜底词袋）"""
    root = bootstrap(tmp_path)
    _seed(root)
    _fake_embed()
    assert semantic_vector_retrieve(root, "DLL 修改后必须递增版本号避免被锁") == []


def test_retrieve_fuses_vector_channel(tmp_path):
    """始终并行接入 retrieve：建库后检索正常（>=1），无回归"""
    root = bootstrap(tmp_path)
    _seed(root)
    _fake_embed()
    build(root)
    hits = retrieve(root, "文件被占用打不开")
    assert len(hits) >= 1
