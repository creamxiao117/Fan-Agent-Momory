from pathlib import Path

from common.frontmatter import parse_card, write_card
from scripts.bootstrap_hub import bootstrap
from tools.distill import collect_candidates, distill


def _retro_draft(root: Path, platform: str, text: str) -> Path:
    d = root / ".sync" / "drafts" / f"{platform}_draft" / "retro"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "retro-1.md"
    p.write_text(text, encoding="utf-8")
    return p


RETRO_TEXT = """# 复盘 2026-08-17
今天改完插件 DLL 后直接覆盖，被 AutoCAD 锁定，最后只能改版本号解决。
教训：修改 DLL 后必须递增版本号，不能原地覆盖。
"""


def test_collect_candidates_extracts_lessons(tmp_path):
    root = bootstrap(tmp_path)
    _retro_draft(root, "trae", RETRO_TEXT)
    cards = collect_candidates(root, "trae")
    assert len(cards) >= 1
    assert "递增版本" in cards[0]["body"]


def test_distill_writes_candidate_cards(tmp_path):
    root = bootstrap(tmp_path)
    _retro_draft(root, "trae", RETRO_TEXT)
    written = distill(root, "trae")
    assert written  # 至少产出一张候选卡片
    assert all(p.suffix == ".md" for p in written)
    card = parse_card(written[0].read_text(encoding="utf-8"))
    assert card.status == "candidate"


def test_distill_dedupes_repeated_lessons(tmp_path):
    root = bootstrap(tmp_path)
    _retro_draft(root, "trae", RETRO_TEXT)
    _retro_draft(root, "trae", RETRO_TEXT.replace("2026-08-17", "2026-08-18"))
    written = distill(root, "trae")
    # 两条几乎相同 → 只产出一张候选
    assert len(written) == 1
