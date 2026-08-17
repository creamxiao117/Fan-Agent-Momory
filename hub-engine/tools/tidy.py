"""整理/归档：把过时/废弃卡片标 archived 并移入 archive/"""

from pathlib import Path

from common.frontmatter import read_card, write_card
from sync import append_log


def archive(root: Path, rel_path: str, reason: str = "") -> Path:
    """把卡片改为 archived 并移动到 archive/；返回新位置"""
    root = Path(root)
    src = root / rel_path
    if not src.exists():
        raise FileNotFoundError(f"待归档文件不存在: {src}")
    card = read_card(src)
    card.status = "archived"
    card.extra.setdefault("archived_reason", reason or "未说明")
    # 保留来源子目录结构，避免不同目录同名文件互相覆盖
    rel_dir = src.parent.relative_to(root)
    dst = root / "archive" / rel_dir / src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(write_card(card), encoding="utf-8")
    src.unlink()
    append_log(root, "tidy", f"归档 {rel_path}（{reason or '未说明'}）")
    return dst
