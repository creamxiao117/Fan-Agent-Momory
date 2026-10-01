# @status: retired
# @retired_at: 2026-10-01
# @original_path: hub-engine/tests/test_migrate_index_fields.py
# @superseded_by: hub-engine/tests/test_set_index_meta.py
# @reason: 随一次性迁移脚本退役；卡字段安全写入由 card_fields + test_set_index_meta 覆盖
# @retired_from_commit: a7e941b
# @restore: git checkout a7e941b -- hub-engine/tests/test_migrate_index_fields.py && git mv hub-engine/tests/test_migrate_index_fields.py hub-engine/tests/test_migrate_index_fields.py

"""一次性迁移脚本的单测（纯函数部分）。

为何要测：`_insert_fields` / `_yaml_line` 处理的是**卡 frontmatter 的写入**——
写坏一列就污染权威区（BOM/换行/引号/中文冒号都是踩过的坑），而迁移脚本只跑一次，
没有测试就等于把风险押在一次性人工核对上。
"""

from pathlib import Path

from scripts.migrate_index_fields import (
    _has_bom,
    _insert_fields,
    _yaml_line,
    plan_fields,
    proofread_candidates,
)
from tools.hub_registry import CardMeta, scan

CARD = """---
type: rule
tags: [demo]
updated: '2026-10-01'
status: active
---

{body}"""


def _card(hub: Path, slug: str, body: str, *, sub: str = "rules") -> Path:
    d = hub / sub
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{slug}.md"
    p.write_text(CARD.format(body=body), encoding="utf-8")
    return p


def test_plan_splits_annotation_into_note(tmp_path: Path):
    """老行 = 卡摘要 + 人工后缀 → 后缀进 `index_note`（描述保持派生）"""
    hub = tmp_path / "AgentMemoryHub"
    _card(hub, "demo-rule", "摘要一句话。\n")
    cards = scan(hub)
    old = {"demo-rule": "摘要一句话。 status=active（T1 09-30 ✅）"}

    plan = plan_fields(hub, cards, old)

    assert plan == {"demo-rule": {"index_note": " status=active（T1 09-30 ✅）"}}


def test_plan_keeps_handwritten_desc(tmp_path: Path):
    """老行与卡摘要不同（携带 ★/判级 等元信息）→ 整段进 `index_desc`（不降级）"""
    hub = tmp_path / "AgentMemoryHub"
    _card(hub, "demo-bp", "carries 摘要。\n", sub="blueprints")
    cards = scan(hub)
    old = {"demo-bp": "COLMAP（12.8k★, C++/CUDA）SfM+MVS；判级 B+。"}

    plan = plan_fields(hub, cards, old)

    assert plan == {"demo-bp": {"index_desc": "COLMAP（12.8k★, C++/CUDA）SfM+MVS；判级 B+。"}}


def test_plan_skips_identical_rows(tmp_path: Path):
    hub = tmp_path / "AgentMemoryHub"
    _card(hub, "demo-rule", "一样的一句话。\n")

    assert plan_fields(hub, scan(hub), {"demo-rule": "一样的一句话。"}) == {}


def test_plan_skips_ghost_entries(tmp_path: Path):
    """INDEX 有、卡无（幽灵）不由本迁移处理（由渲染/审计口径另管）"""
    hub = tmp_path / "AgentMemoryHub"
    _card(hub, "demo-rule", "摘要。\n")

    assert plan_fields(hub, scan(hub), {"no-such-card": "幽灵行"}) == {}


def test_insert_fields_before_closing_fence():
    text = "---\ntype: rule\n---\n\n正文\n"

    out = _insert_fields(text, {"index_desc": "描述"})

    assert out == "---\ntype: rule\nindex_desc: 描述\n---\n\n正文\n"


def test_insert_fields_preserves_bom_and_crlf(tmp_path: Path):
    """BOM 与 CRLF 必须原样保留（编码纪律：UTF-8 无 BOM，但历史卡有 BOM 的不动它）"""
    p = tmp_path / "c.md"
    p.write_bytes("\ufeff---\r\ntype: rule\r\n---\r\n\r\n正文\r\n".encode())
    assert _has_bom(p)

    out = _insert_fields(p.read_bytes().decode("utf-8-sig"), {"index_note": "（T1 ✅）"})

    assert out.startswith("---\r\n")
    assert "index_note: （T1 ✅）\r\n" in out
    assert out.endswith("正文\r\n")


def test_yaml_line_escapes_colon_and_quotes():
    """值里含 `：` `"` `'` 时不能手拼（必须走 YAML 序列化）"""
    line = _yaml_line("index_note", "说「假绿制造机」：不是 'fake'")

    assert line.startswith("index_note: ")
    assert "\n" not in line
    # 回读必须与原值逐字相等
    import yaml

    assert yaml.safe_load(line)["index_note"] == "说「假绿制造机」：不是 'fake'"


def test_proofread_candidates_flags_bad_desc():
    def meta(slug: str, summary: str) -> CardMeta:
        return CardMeta(
            slug=slug,
            rel_path=f"rules/{slug}.md",
            dir="rules",
            type="rule",
            status="active",
            updated="2026-10-01",
            summary=summary,
        )

    rows = proofread_candidates(
        [
            meta("hard-cut", "运行态数据目录（AgentMemoryHub）不进 markdownlint…"),
            meta("repo-id", "gh-FreeCAD-FreeCAD"),
            meta("too-long", "一" * 46),
            meta("fine", "正常描述"),
        ]
    )

    assert [s for s, _ in rows] == ["hard-cut", "repo-id", "too-long"]
