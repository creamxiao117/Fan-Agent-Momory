from pathlib import Path

import pytest
from scripts.bootstrap_hub import bootstrap
from tools.retrieve import deterministic_retrieve, retrieve, semantic_retrieve

try:
    import jieba  # noqa: F401

    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False

skip_no_jieba = pytest.mark.skipif(not HAS_JIEBA, reason="jieba 未安装")


def _seed(root: Path) -> None:
    (root / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [autocad, dll-lock]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\nDLL 修改后必须递增版本号避免被锁。\n",
        encoding="utf-8",
    )
    (root / "experience" / "blunder.md").write_text(
        "---\ntype: exp\ntags: [autocad]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n上次没重命名导致 AutoCAD 占用文件无法覆盖。\n",
        encoding="utf-8",
    )


def test_deterministic_by_tag(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    hits = deterministic_retrieve(root, "dll-lock")
    assert [h.path.name for h in hits] == ["dll-lock.md"]


def test_semantic_recalls_similar(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    hits = semantic_retrieve(root, "改了插件 DLL 结果被 AutoCAD 锁住打不开")
    names = [h.path.name for h in hits]
    assert "dll-lock.md" in names or "blunder.md" in names


def test_mixed_retrieve_returns_results(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    hits = retrieve(root, "DLL 被锁怎么办")
    assert len(hits) >= 1


def test_empty_query_returns_no_results(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    assert retrieve(root, "") == []
    assert retrieve(root, "   ") == []


def test_semantic_n_is_tunable(tmp_path):
    """n-gram 长度可调（char 模式）：n 值不同应产出不同召回（实测 n=2 最优）"""
    root = bootstrap(tmp_path)
    _seed(root)
    q = "改了插件 DLL 结果被 AutoCAD 锁住打不开"
    hits2 = semantic_retrieve(root, q, top_k=2, n=2, mode="char")
    hits3 = semantic_retrieve(root, q, top_k=2, n=3, mode="char")
    # n 参数生效：两者至少一端有命中，且召回集合不同（n 影响相似度排序）
    assert len(hits2) >= 1 or len(hits3) >= 1
    assert [h.path.name for h in hits2] != [h.path.name for h in hits3]


def test_retrieve_passes_n_to_semantic(tmp_path):
    """retrieve 透传 n 参数到语义通道，默认不破坏确定性行为"""
    root = bootstrap(tmp_path)
    _seed(root)
    # 确定性命中不受 n 影响
    assert retrieve(root, "dll-lock", n=3)[0].path.name == "dll-lock.md"
    # 语义兜底在 n 可调下仍可返回结果
    assert len(retrieve(root, "文件被占用打不开", top_k=3, n=2)) >= 1


@skip_no_jieba
def test_deterministic_word_mode_tag_word_match(tmp_path):
    """word 模式：查询词 'dll' 可命中 tag 'dll-lock'（char 模式整句包含命中不了）"""
    root = bootstrap(tmp_path)
    _seed(root)
    assert deterministic_retrieve(root, "dll 锁文件", mode="char") == []
    hits = deterministic_retrieve(root, "dll 锁文件", mode="word")
    assert [h.path.name for h in hits] == ["dll-lock.md"]


@skip_no_jieba
def test_retrieve_word_mode_returns_dll_lock(tmp_path):
    """retrieve 透传 word 模式：确定性词级匹配优先命中 dll-lock"""
    root = bootstrap(tmp_path)
    _seed(root)
    hits = retrieve(root, "dll 锁文件", mode="word")
    assert hits[0].path.name == "dll-lock.md"


@skip_no_jieba
def test_semantic_word_mode_recalls_similar(tmp_path):
    """word 模式语义通道也能召回相似卡片"""
    root = bootstrap(tmp_path)
    _seed(root)
    hits = semantic_retrieve(root, "改了插件 DLL 结果被锁住打不开", mode="word")
    names = [h.path.name for h in hits]
    assert "dll-lock.md" in names or "blunder.md" in names
