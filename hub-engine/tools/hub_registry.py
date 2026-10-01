# 中枢卡片派生层：卡文件是唯一真相，本模块是**纯扫描**（不写盘、不缓存）。
#
# 背景（2026-10-01 裁定，见 docs/compose/plans/2026-10-01-single-source-l0-shape.md）：
# L0 的 INDEX 枚举行与卡数成正比（blueprints 区 4.25 卡/天）→ 字符帽永远需要人批。
# 根治 = 把枚举移出 L0（改为渲染产物，见 scripts/render_index.py），机器消费方
# 一律直接扫卡文件。本模块即那个「唯一扫描入口」。
#
# **loud-fail 是硬要求**：权威区卡解析/校验失败必须显式报错、并列出全部文件名。
# 原因：ghost/orphan/misrouted 三个漂移维度退役后，若扫描静默丢弃坏卡，
# 「卡在派生视图里消失」将无任何门禁可见（历史上靠 tools/lint.py 的 invalid 计数兜住）。
#
# 不引入缓存/派生文件（裁定）：实测 501 张卡全扫约 452ms，无需缓存，而缓存会引入
# 「陈旧 / 新写入者 / 跨进程可见性」三个失败模式（先例：vector.db 被并发 MCP 锁住）。

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from common.frontmatter import Card, try_read_card, validate_card

# 参与派生的目录（与 tools/retrieve.py 的 _ACTIVE_DIRS 同口径：五权威区 + experience）
CARD_DIRS: tuple[str, ...] = (
    "rules",
    "methodology",
    "longterm",
    "projects",
    "blueprints",
    "experience",
)

# 非卡片文件名（时间线/报告/索引渲染产物），不参与派生
NON_CARD_NAMES: frozenset[str] = frozenset({"log.md"})
NON_CARD_PREFIXES: tuple[str, ...] = ("lint-report-", "INDEX")

DEFAULT_SUMMARY_MAX = 40


class RegistryError(Exception):
    """派生层构建失败：解析不了/校验不过的卡必须显式报错（loud-fail）。"""


@dataclass(frozen=True)
class CardMeta:
    """卡片派生元数据（字段全部来自卡自身，不臆造）。

    `summary` = 索引描述：优先取卡 frontmatter 的 `index_desc`（卡自己声明的描述，
    用于保留 ★/语言/判级 等选型元信息），否则用正文摘要（extract_summary）。
    `note` = `index_note`（T1/status 等**追加注解**）：回写只动这一个字段，
    不重写描述——避免「回写一次就制造一次漂移」（09-27 的历史形态）。
    """

    slug: str
    rel_path: str
    dir: str
    type: str
    status: str
    updated: str
    tags: tuple[str, ...] = ()
    reuse_count: int = 0
    title: str = ""
    summary: str = ""
    note: str = ""


def hub_root() -> Path:
    """默认中枢根（仓库根 / AgentMemoryHub），由本文件位置推导，避免硬编码。"""
    return Path(__file__).resolve().parents[2] / "AgentMemoryHub"


def _is_card_file(p: Path) -> bool:
    if p.name in NON_CARD_NAMES:
        return False
    return not any(p.name.startswith(pre) for pre in NON_CARD_PREFIXES)


def _title_of(card: Card) -> str:
    """卡正文首个 `# ` 标题（无则空串）——INDEX 行的人类可读名。"""
    for line in card.body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return ""


_EXTRACT_SUMMARY = None  # 惰性缓存的 extract_summary 引用（见 _summary_of）


def _summary_of(path: Path, max_len: int) -> str:
    """卡自身摘要。实现单一来源 = post_ingest_hook.extract_summary（不另写一份）。

    惰性缓存函数对象：501 张卡只付一次 import 成本，且 tools/ 不因 scripts/
    的导入期副作用而牵连失败（降级：摘要视为空串由调用方容忍）。
    """
    global _EXTRACT_SUMMARY
    if _EXTRACT_SUMMARY is None:
        from scripts.post_ingest_hook import extract_summary

        _EXTRACT_SUMMARY = extract_summary
    return _EXTRACT_SUMMARY(path, max_len=max_len)


def _index_desc(card: Card, path: Path, max_len: int) -> str:
    """索引描述：`index_desc`（卡声明）优先，否则卡正文摘要。"""
    declared = card.extra.get("index_desc")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    return _summary_of(path, max_len)


def _index_note(card: Card) -> str:
    """追加注解（T1/status 等），**逐字**拼在描述后（不 strip：前导空格也是迁移前的原样）。"""
    note = card.extra.get("index_note")
    if not isinstance(note, str) or not note.strip():
        return ""
    return note


def scan(hub: Path | None = None, *, summary_max: int = DEFAULT_SUMMARY_MAX) -> list[CardMeta]:
    """扫描卡片目录 → CardMeta 列表（按 CARD_DIRS 顺序 + slug 升序，稳定可复现）。

    任一卡解析失败或 `validate_card` 报错 → 汇总后一次性抛 `RegistryError`，
    消息含**全部**坏卡相对路径（便于一次修完）。
    """
    root = Path(hub) if hub is not None else hub_root()
    cards: list[CardMeta] = []
    bad: list[str] = []
    for sub in CARD_DIRS:
        d = root / sub
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            if not _is_card_file(p):
                continue
            card = try_read_card(p)
            if card is None:
                bad.append(f"{sub}/{p.name}（frontmatter 无法解析）")
                continue
            errs = validate_card(card)
            if errs:
                bad.append(f"{sub}/{p.name}（{'; '.join(errs)}）")
                continue
            cards.append(
                CardMeta(
                    slug=p.stem,
                    rel_path=p.relative_to(root).as_posix(),
                    dir=sub,
                    type=card.type,
                    status=card.status,
                    updated=card.updated,
                    tags=tuple(str(t) for t in card.tags),
                    reuse_count=int(card.reuse_count or 0),
                    title=_title_of(card),
                    summary=_index_desc(card, p, summary_max),
                    note=_index_note(card),
                )
            )
    if bad:
        raise RegistryError(f"{len(bad)} 张卡不合法（派生层拒绝静默跳过）：\n  " + "\n  ".join(sorted(bad)))
    return cards


def by_dir(cards: list[CardMeta]) -> dict[str, list[CardMeta]]:
    """按目录分组（保持 CARD_DIRS 顺序，空目录不出现）。"""
    out: dict[str, list[CardMeta]] = {}
    for sub in CARD_DIRS:
        rows = [c for c in cards if c.dir == sub]
        if rows:
            out[sub] = rows
    return out


def example_slugs(cards: list[CardMeta], dir_name: str, n: int = 3) -> list[str]:
    """某目录的示例 slug（reuse_count 降序 → updated 降序 → slug 升序，取前 n）。

    用于 L0 能力图的内联示例：上限 n 与「内联不换行」共同保证 L0 行数恒定。
    多趟稳定排序（Python sort 稳定），避免手写复合键的降序陷阱。
    """
    rows = [c for c in cards if c.dir == dir_name]
    rows.sort(key=lambda c: c.slug)
    rows.sort(key=lambda c: c.updated, reverse=True)
    rows.sort(key=lambda c: -c.reuse_count)
    return [c.slug for c in rows[:n]]


__all__ = [
    "CARD_DIRS",
    "DEFAULT_SUMMARY_MAX",
    "CardMeta",
    "RegistryError",
    "by_dir",
    "example_slugs",
    "hub_root",
    "scan",
]
