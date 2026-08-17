"""复盘 → 候选规则：扫描暂存区复盘草稿，归纳去重，产出 candidate 卡片"""
from datetime import date
from pathlib import Path

from common.frontmatter import parse_card, write_card
from common.vector import cosine, vector
from sync import append_log

REQUIRE_MARKERS = ("必须", "禁止", "不要", "一定", "教训", "注意", "规则")


def _split_lessons(text: str) -> list[str]:
    """从复盘草稿里切出带有约束意味的句子/段落"""
    lessons = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if any(m in line for m in REQUIRE_MARKERS):
            lessons.append(line)
    return lessons


def collect_candidates(root: Path, platform: str) -> list[dict]:
    """收集该平台暂存区复盘草稿中的候选内容（含来源）"""
    root = Path(root)
    draft_dir = root / ".sync" / "drafts" / f"{platform}_draft" / "retro"
    if not draft_dir.is_dir():
        return []
    out = []
    for p in sorted(draft_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue  # 坏文件跳过，避免中断整个 distill
        for lesson in _split_lessons(text):
            out.append({"source": p.name, "body": lesson})
    return out


def distill(root: Path, platform: str, output: str = "experience") -> list[Path]:
    """把复盘草稿转成去重后的候选卡片，写入 .sync/drafts/<platform>_draft/candidates/"""
    root = Path(root)
    candidates = collect_candidates(root, platform)
    out_dir = root / ".sync" / "drafts" / f"{platform}_draft" / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)

    unique: list[str] = []
    for c in candidates:
        body = c["body"].lstrip("- ").strip()
        if any(cosine(vector(body), vector(u)) >= 0.7 for u in unique):
            continue  # 与已有候选高度相似，跳过
        unique.append(body)

    written = []
    for i, body in enumerate(unique, 1):
        card = parse_card(f"""---
type: exp
tags:
  - distill
updated: {date.today().isoformat()}
status: candidate
reuse_count: 0
---
{body}
""")
        p = out_dir / f"candidate-{i}.md"
        p.write_text(write_card(card), encoding="utf-8")
        written.append(p)

    if written:
        append_log(root, "distill", f"从 {platform} 复盘产出 {len(written)} 条候选")
    return written
