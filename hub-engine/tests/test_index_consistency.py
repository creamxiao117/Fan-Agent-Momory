# @version V1.0 / 2026-09-23 / pi / INDEX 一致性契约单测（单一事实源）

"""`index_consistency` 单测：分区表 / 登记行解析 / 图例行排除。

背景：INDEX 一致性此前散落三套实现（`audit_index` 的正则、`fix_orphans` 的
`SECTION_TITLES`、`fix_index_registry` 的 `_CARD_SECTION_TOKENS`），
同一契约多份实现必然漂移。本模块收敛为单一事实源，本文件锁住这些不变量。
"""

from scripts.audit_index import AUTHORITY_DIRS as AUDIT_AUTHORITY_DIRS
from scripts.index_consistency import (
    AUTHORITY_DIRS,
    CARD_SECTION_TOKENS,
    INDEX_FILE_FOR_DIR,
    SECTION_TITLES,
    card_slug,
    index_file_for_dir,
    is_card_section,
    registered_slugs,
    section_for_dir,
)


def test_authority_dirs_is_audit_source_not_copy():
    """权威目录清单必须来自 audit_index，而不是本模块另抄一份"""
    assert AUTHORITY_DIRS is AUDIT_AUTHORITY_DIRS or tuple(AUTHORITY_DIRS) == tuple(AUDIT_AUTHORITY_DIRS)


def test_card_section_tokens_are_derived_from_section_titles():
    """token 必须由 SECTION_TITLES **派生**——手写第二份 token 列表就会漂移。

    这是本模块存在的核心理由：`fix_index_registry` 曾手写 token 列表，
    与 `fix_orphans` 的目录映射各维护一份。
    """
    assert tuple(f"{d}/" for d in SECTION_TITLES) == CARD_SECTION_TOKENS
    # 每个分区标题都应能被 is_card_section 认出来（自洽性）
    for heading in SECTION_TITLES.values():
        assert is_card_section(heading), f"分区标题未被识别: {heading}"


def test_is_card_section_rejects_prose_sections():
    """说明性分区（使用约定/沉淀通道）不是卡片清单分区"""
    assert not is_card_section("## 使用约定（各平台执行前必读）")
    assert not is_card_section("## 检索方式")
    assert not is_card_section("## 沉淀通道")


def test_card_slug_parses_normal_and_cjk_entries():
    assert card_slug("- alpha    描述一") == "alpha"
    assert card_slug("- 中文卡名    描述") == "中文卡名"
    assert card_slug("- with.dot-and_underscore    d") == "with.dot-and_underscore"


def test_card_slug_rejects_legend_and_note_lines():
    """目录图例行（`- rules/  说明`）与加粗注释行都不是卡片登记"""
    assert card_slug("- rules/        权威规则（命令式/约束式，违反有代价）") is None
    assert card_slug("- **各平台内容先写入** .sync/drafts/…") is None
    assert card_slug("普通文本行") is None
    assert card_slug("") is None


def test_registered_slugs_exact_not_substring(tmp_path):
    """回归：`- alphabeta` 不得让 `alpha` 被当成已登记（曾是静默漏登 bug）"""
    idx = tmp_path / "INDEX.md"
    idx.write_text("## 规则（rules/）\n- alphabeta    更长的另一个 slug\n", encoding="utf-8")
    got = registered_slugs(idx)
    assert got == {"alphabeta"}
    assert "alpha" not in got


def test_registered_slugs_tolerates_bom(tmp_path):
    """带 BOM 的 INDEX 仍须正确解析"""
    idx = tmp_path / "INDEX.md"
    idx.write_text("\ufeff## 规则（rules/）\n- alpha    描述\n", encoding="utf-8")
    assert registered_slugs(idx) == {"alpha"}


def test_section_for_dir_covers_all_card_dirs():
    for d in SECTION_TITLES:
        assert section_for_dir(d) == SECTION_TITLES[d]
    assert section_for_dir("不存在目录") is None


# ────────────────── 分区 → 目标 INDEX 文件（拆分后路由）──────────────────


def test_experience_routes_to_split_file():
    """experience 必须写入 INDEX-experience.md，而非根 INDEX。

    回归背景：A4 把 experience 整区拆出后，两个写入方仍硬编码 `root/INDEX.md`
    → 经验卡被追加回根 INDEX（白涨 L0 + 条目放错文件）。
    实测 2026-09-23：某经验卡被登记到根 INDEX L180，而该区本应只有指针。
    """
    assert index_file_for_dir("experience") == "INDEX-experience.md"
    for d in ("rules", "methodology", "longterm", "projects", "blueprints"):
        assert index_file_for_dir(d) == "INDEX.md", f"{d} 应写入根 INDEX"


def test_index_file_mapping_covers_every_section_dir():
    """映射必须覆盖全部卡目录——漏一个就会回退到根 INDEX（静默回涨）"""
    assert set(INDEX_FILE_FOR_DIR) == set(SECTION_TITLES)
    assert index_file_for_dir("不存在目录") is None
