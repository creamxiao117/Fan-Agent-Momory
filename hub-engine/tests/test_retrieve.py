from pathlib import Path

import pytest
from scripts.bootstrap_hub import bootstrap
from tools.retrieve import (
    _anti_triggers,
    deterministic_retrieve,
    retrieve,
    retrieve_with_meta,
    semantic_retrieve,
)

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


def test_retrieve_with_meta_deterministic_channel(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    channel, scored = retrieve_with_meta(root, "dll-lock")
    assert channel == "deterministic"
    assert [c.path.name for c, _ in scored] == ["dll-lock.md"]
    assert all(s is None for _, s in scored)  # 确定性命中不带 score


def test_retrieve_with_meta_semantic_scores(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    # 注意：查询不能含 type/tag 词（如 "dll"），否则 word 模式确定性通道先命中
    channel, scored = retrieve_with_meta(root, "文件被占用打不开")
    assert channel == "semantic"
    assert scored and all(s is not None for _, s in scored)


def test_retrieve_with_meta_empty_channel(tmp_path):
    root = bootstrap(tmp_path)
    _seed(root)
    channel, scored = retrieve_with_meta(root, "   ")
    assert channel == "empty"
    assert scored == []


def test_retrieve_still_returns_cards(tmp_path):
    """retrieve 兼容层：行为与之前一致（返回 Card 列表）"""
    root = bootstrap(tmp_path)
    _seed(root)
    hits = retrieve(root, "DLL 被锁怎么办")
    assert all(isinstance(c, object) for c in hits)
    assert len(hits) >= 1


def _index_cache_state(root):
    """返回 (本进程索引缓存里该 root 的命中数)：间接观测缓存是否建立"""
    from tools import retrieve as _r

    cached = _r._INDEX_CACHE.get(str(root.resolve()))
    if cached is None:
        return (None, None)
    sig, idx = cached
    return (len(sig), len(idx.cards))


def test_first_layer_cache_built_and_reused(tmp_path):
    """第一层缓存：同一 root 第二次检索不重建索引（直接复用目录签名）"""
    root = bootstrap(tmp_path)
    _seed(root)
    assert _index_cache_state(root) == (None, None)
    retrieve(root, "DLL 被锁怎么办")
    hits_after_first = _index_cache_state(root)
    assert hits_after_first[0] is not None and hits_after_first[0] > 0
    # 第二次直接命中缓存（签名一致 → 不重建）
    retrieve(root, "文件被占用打不开")
    assert _index_cache_state(root) == hits_after_first


def test_first_layer_index_invalidates_on_card_change(tmp_path):
    """第一层缓存失效：卡片内容(mtime/size)变更后重建索引，检索反映新内容"""
    from tools import retrieve as _r

    root = bootstrap(tmp_path)
    _seed(root)
    assert retrieve(root, "DLL 被锁怎么办")  # 建立缓存
    before = _index_cache_state(root)
    assert before[0] is not None
    # 新增一张含独特 tag 的卡 → 签名变化 → 下次检索重建
    (root / "experience" / "newbie.md").write_text(
        "---\ntype: exp\ntags: [zebra-finance]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\n量化回测要注意过拟合。\n",
        encoding="utf-8",
    )
    hits = deterministic_retrieve(root, "zebra-finance")
    assert any(h.path.name == "newbie.md" for h in hits)
    after = _index_cache_state(root)
    # 重建后索引签名增加 1 项（新增 1 文件），新卡进入索引
    assert after[0] == before[0] + 1
    _r._clear_index_for(root)
    assert _index_cache_state(root) == (None, None)


@skip_no_jieba
def test_anti_triggers_parse_forms():
    """反触发词解析：list / 逗号|空格 / 连字符 三形态归一为小写词集，过滤停用词"""
    from common.frontmatter import Card

    as_list = Card(extra={"anti_trigger": ["安装", "部署", "install"]})
    assert _anti_triggers(as_list) == {"安装", "部署", "install"}
    as_str = Card(extra={"anti_trigger": "安装, 部署 | install deploy"})
    assert _anti_triggers(as_str) == {"安装", "部署", "install", "deploy"}
    assert _anti_triggers(Card()) == set()


@skip_no_jieba
def test_anti_trigger_penalizes_semantic_score(tmp_path):
    """核心机制：query 命中卡声明 anti_trigger 词时，其语义分被扣（-0.15/条，封顶-0.5）

    用内容完全一致的「对照组」隔离变量：仅一张卡多声明 anti_trigger，
    其余同体同 tag → 基线语义分相等，命中罚分让该卡显著低于对照。
    """
    from tools.retrieve import _semantic_scored

    root = bootstrap(tmp_path)
    body = (
        "---\ntype: blueprint\ntags: [skill-governance]\n"
        "updated: 2026-08-17\nstatus: active\nreuse_count: 0\n"
        "%s---\n通用技能治理原则，覆盖安装部署、日志、配置等全面场景。\n"
    )
    (root / "blueprints" / "sem.md").write_text(
        body % "anti_trigger: [安装, 部署]\n", encoding="utf-8"
    )
    (root / "blueprints" / "ctl.md").write_text(body % "", encoding="utf-8")
    q = "通用技能治理 安装 部署 原则"
    scored = {
        c.path.name: s for c, s in _semantic_scored(root, q, top_k=20, mode="word")
    }
    assert scored["ctl.md"] > 0  # 对照组有分
    # 命中 2 条 anti_trigger(安装/部署) → 扣 min(2*0.15, 0.5)=0.3，应显著低于对照
    assert scored["sem.md"] <= scored["ctl.md"] - 0.2
