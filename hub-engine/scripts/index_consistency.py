# @version V1.0 / 2026-09-23 / pi / INDEX 一致性契约（分区表 / 登记行解析 / section 判定）

"""INDEX 一致性契约 —— **单一事实源**。

## 为什么需要这个模块
INDEX 一致性此前散落三套实现，同一契约各写各的：

| 位置 | 自带的实现 |
|:--|:--|
| `audit_index.py` | `INDEX_ENTRY_RE` / `NESTED_ENTRY_RE`（**权威正则**）+ `AUTHORITY_DIRS` |
| `fix_orphans.py` | `SECTION_TITLES`（目录→分区标题） |
| `fix_index_registry.py` | `_CARD_SECTION_TOKENS` + `_is_card_section`（另一套分区判定）|

后果：`- rules/  说明` 这类目录图例行，在一处被当登记、在另一处不是；
`fix_orphans` 甚至曾用 `f"- {slug}" in text` **子串**匹配 → slug `foo` 被
`- foobar` 误判已登记 → 静默漏登。

## 本模块的定位
- **登记行正则**：直接复用 `audit_index.INDEX_ENTRY_RE`（不复制正则）
- **分区表**：唯一定义 `SECTION_TITLES`；`is_card_section()` 的 token **由该表派生**，
  不再手写第二份 token 列表——两处手工维护必然漂移
- **slug 解析**：按行精确匹配（禁止子串语义）

下游：`fix_orphans.py`（补登未登记卡）、`fix_index_registry.py`（幽灵 slug 纠偏）。
两个工具方向不同（文件有/INDEX 无 ↔ INDEX 有/文件无），**保持分开**；
但共享契约收敛到本模块。
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))  # hub-engine/

from scripts.audit_index import AUTHORITY_DIRS, INDEX_ENTRY_RE  # single source

# 目录名 → INDEX 分区标题（**唯一定义**；必须与 AgentMemoryHub/INDEX.md 内实际标题一致）
SECTION_TITLES: dict[str, str] = {
    "rules": "## 规则（rules/）",
    "methodology": "## 方法论（methodology/）",
    "longterm": "## 长期记忆（longterm/）",
    "projects": "## 项目记忆（projects/）",
    "blueprints": "## 技术路径蓝图（blueprints/）",
    "experience": "## 经验（experience/）",
}

# 卡片清单分区判定用的 token：**从 SECTION_TITLES 派生**，避免手写第二份而漂移。
# 依据：分区标题里都含 `<目录名>/`（如「## 规则（rules/）」），故 token = "<dir>/"。
CARD_SECTION_TOKENS: tuple[str, ...] = tuple(f"{d}/" for d in SECTION_TITLES)


def is_card_section(heading: str) -> bool:
    """该 `## ` 分区是否是卡片清单分区（排除使用约定/沉淀通道等说明性分区）"""
    return any(tok in heading for tok in CARD_SECTION_TOKENS)


def card_slug(line: str) -> str | None:
    """从 INDEX 行解析登记 slug；非登记行返回 None。

    用 `audit_index.INDEX_ENTRY_RE`（唯一权威正则）。该字符集**不含 `/`**，
    因此目录图例行（`- rules/   权威规则说明`）天然不匹配——这正是 audit 的机制。
    """
    m = INDEX_ENTRY_RE.match(line)
    return m.group(1) if m else None


def registered_slugs(index_path: Path) -> set[str]:
    """INDEX 中已登记的 slug 集合（按行精确解析）。

    历史坑：某实现用 `f"- {slug}" in text` 子串匹配，slug `foo` 会被
    `- foobar` 误判为已登记 → 真正未登记的卡被静默跳过。此处按行取 slug 后精确比对。
    """
    text = index_path.read_text(encoding="utf-8-sig", errors="ignore")
    out: set[str] = set()
    for line in text.splitlines():
        slug = card_slug(line)
        if slug:
            out.add(slug)
    return out


def section_for_dir(dir_name: str) -> str | None:
    return SECTION_TITLES.get(dir_name)


__all__ = [
    "AUTHORITY_DIRS",
    "CARD_SECTION_TOKENS",
    "SECTION_TITLES",
    "card_slug",
    "is_card_section",
    "registered_slugs",
    "section_for_dir",
]
