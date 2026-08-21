"""统一知识卡片 frontmatter 的解析 / 写入 / 校验"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

VALID_TYPES = {
    "rule",
    "exp",
    "note",
    "project",
    "retro",
    "methodology",
    "longterm",
    "blueprint",
}
VALID_STATUS = {"active", "archived", "candidate", "reference"}
KNOWN = {"type", "tags", "updated", "status", "reuse_count"}


def today_date() -> date:
    """本地日期（时区感知，满足 lint 的 tz 要求）"""
    return datetime.now(tz=timezone.utc).astimezone().date()


def today_iso() -> str:
    """本地日期 YYYY-MM-DD"""
    return today_date().isoformat()


@dataclass
class Card:
    """一张知识卡片（对应一个 .md 文件）"""

    type: str = "note"
    tags: list = field(default_factory=list)
    updated: str = ""
    status: str = "active"
    reuse_count: int = 0
    extra: dict = field(default_factory=dict)  # 其他自定义字段原样保留
    body: str = ""
    path: Path | None = None  # 从磁盘读取时记录来源路径


def parse_card(text: str, path: Path | None = None) -> Card:
    """解析 '---\n...\n---\n正文' 的统一卡片"""
    if not text.startswith("---"):
        raise ValueError("缺少 frontmatter 起始分隔符 '---'")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("frontmatter 缺少结束分隔符 '---'")
    fm = yaml.safe_load(parts[1]) or {}
    card = Card(path=path)
    if isinstance(fm.get("tags"), list):
        card.tags = [str(t) for t in fm["tags"]]
    card.type = str(fm.get("type", "note"))
    card.updated = str(fm.get("updated", ""))
    card.status = str(fm.get("status", "active"))
    card.reuse_count = int(fm.get("reuse_count", 0) or 0)
    card.extra = {k: v for k, v in fm.items() if k not in KNOWN}
    card.body = parts[2].strip()
    return card


def write_card(card: Card) -> str:
    """把卡片渲染回统一格式文本"""
    fm = {
        "type": card.type,
        "tags": card.tags,
        "updated": card.updated or today_iso(),
        "status": card.status,
        "reuse_count": card.reuse_count,
    }
    fm.update(card.extra)
    return (
        "---\n"
        + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip()
        + "\n---\n\n"
        + card.body.strip()
        + "\n"
    )


def validate_card(card: Card) -> list[str]:
    """返回错误列表；空列表表示合法"""
    errs = []
    if card.type not in VALID_TYPES:
        errs.append(f"type 必须为 {sorted(VALID_TYPES)} 之一，当前: {card.type}")
    if card.status not in VALID_STATUS:
        errs.append(f"status 必须为 {sorted(VALID_STATUS)} 之一，当前: {card.status}")
    if not card.updated:
        errs.append("updated 必填（YYYY-MM-DD）")
    return errs


def read_card(path: Path) -> Card:
    """读取卡片。utf-8-sig 同时容忍 BOM 与无 BOM——带 EF BB BF 头三字节的卡也能正常解析，
    避免误判为 invalid（实测 2026-08-21：草稿写入默认 UTF8 会带 BOM，导致 startswith(--) 判空）。"""
    return parse_card(path.read_text(encoding="utf-8-sig"), path=path)


def try_read_card(path: Path) -> Card | None:
    """读取卡片；非卡片/格式错误时返回 None（供各扫描器跳过坏文件）"""
    try:
        return read_card(path)
    except (ValueError, OSError, yaml.YAMLError, TypeError, AttributeError):
        return None


def save_card(card: Card, path: Path) -> None:
    path.write_text(write_card(card), encoding="utf-8")
