# 中枢索引文件的**集合口径**（单一事实源）。
#
# 为何需要（2026-10-01，计划 2026-10-01-single-source-l0-shape 的 Task 4）：
# 09-23 把 experience 整区拆到 INDEX-experience.md 时，读方/写方散落硬编码
# `("INDEX.md", "INDEX-experience.md")` → 漏改一处就静默失能（当时 post_ingest_hook
# 与 fix_orphans 继续把经验卡写回根 INDEX，白涨 L0）。本次改造又会新增
# INDEX-full.md（L2 全量渲染产物），同样不能靠「每个读方各自记得加」。
#
# 故：**凡新增分册，本文件一处即可**，读方一律走 index_files()/all_index_text()。
#
# 放在 common/ 而非 scripts/：tools/（lint 等）与 scripts/ 都要用，而 common 无内部依赖。

from __future__ import annotations

from pathlib import Path

# 已知分册（顺序 = 读取优先级；未列出的 INDEX*.md 仍会被自动发现并排在末尾）
KNOWN_INDEX_FILES: tuple[str, ...] = (
    "INDEX.md",  # L0 能力图（定形，无 per-card 行）
    "INDEX-full.md",  # L2 全量清单（渲染产物）
    "INDEX-experience.md",  # L2 经验分册
)


def index_files(hub: Path) -> list[Path]:
    """现存的中枢索引文件（含未列出的新分册，自动发现）。

    自动发现的意义：新增 INDEX-<dir>.md 时**不需要改任何读方**，
    从机制上消灭「拆分后读方漏改」这一类漂移。
    """
    hub = Path(hub)
    found = {p.name for p in hub.glob("INDEX*.md")}
    ordered = [hub / n for n in KNOWN_INDEX_FILES if n in found]
    rest = sorted(hub / n for n in found - set(KNOWN_INDEX_FILES))
    return ordered + rest


def all_index_text(hub: Path, encoding: str = "utf-8-sig") -> str:
    """合并全部索引文件的文本（缺文件即跳过；不抛错——索引未建不是错误）。"""
    parts = []
    for p in index_files(hub):
        parts.append(p.read_text(encoding=encoding, errors="ignore"))
    return "\n".join(parts)


__all__ = ["KNOWN_INDEX_FILES", "all_index_text", "index_files"]
