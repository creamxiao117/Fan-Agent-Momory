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

## 裁定：两个工具**保持分开**（2026-09-23 用户拍板）
两者是**同一一致性问题的两个方向**，不是同一件事的两份实现：

| 方向 | 现象 | 工具 |
|:--|:--|:--|
| 文件有 / INDEX 无 | 新卡未登记 | `fix_orphans.py`（**追加**登记行） |
| INDEX 有 / 文件无 | 幽灵 slug（登记名 ≠ 文件名） | `fix_index_registry.py`（**改名/纠偏**） |

**不合并的理由**：合并后单文件要同时承担「追加索引行」与「守护/改名源文件」——
后者的危险等级明显更高（会改卡文件名），把两者塞进一个 CLI 会让
`--apply` 的语义变模糊（“我这次到底会不会动源文件？”）。
**共享的部分已收敛到本模块**（分区表 / 登记行解析 / slug 集合），
所以拆分不再带来契约漂移——这是两者可以安全分开的前提。

若要调整此裁定：请同步改 WORK.md 的 T4 行，并在 commit 里说明理由。
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))  # hub-engine/

import re

# ── INDEX 登记行正则（**权威定义**，2026-09-23 从 audit_index 上移至此）──
# 为何上移：`audit_index` 需要本模块的 `expected_index_file()` 做错位检查，
# 而本模块又需它的正则 → 循环导入。契约模块应当是**叶子**（不依赖任何 script），
# 故把两者共用的正则/目录清单归到此处，`audit_index` 反过来导入本模块。
#
# slug 字符集含 CJK（2026-09-11 用户裁定）：中文 slug 卡此前无法被解析 → 恒被误判
# 为「INDEX 未登记」。slug 类仍不含空格，故加 CJK 不会引入贪婪越界。
# 注意：字符集**不含 `/`** —— 这是排除目录图例行（`- rules/  说明`）的机制。
_CJK = "\u4e00-\u9fff"
INDEX_ENTRY_RE = re.compile(
    rf"^- ([a-zA-Z0-9{_CJK}][a-zA-Z0-9_\-." rf"{_CJK}]{{0,80}})(?:\s{{2,}}|\s+)(.+)$"
)
NESTED_ENTRY_RE = re.compile(
    rf"^\|- ([a-zA-Z0-9{_CJK}][a-zA-Z0-9_\-." rf"{_CJK}]{{0,80}})(?:\s{{2,}}|\s+)(.+)$"
)

# slug 格式校验（原在 audit_index，2026-09-23 一并上移：同样依赖 _CJK）
SLUG_RE = re.compile(rf"^[a-zA-Z0-9{_CJK}][a-zA-Z0-9_\-." rf"{_CJK}]{{1,79}}$")

# 权威区（与 hub.config.yaml 的 authority_dirs 对齐）
# 注意：experience/notes/retro 是非权威区，仅参与 INDEX 登记，不参与权威文件扫描
AUTHORITY_DIRS = (
    "rules",
    "methodology",
    "longterm",
    "projects",
    "blueprints",
)

# 目录名 → INDEX 分区标题（**唯一定义**；必须与目标 INDEX 文件内实际标题一致）
SECTION_TITLES: dict[str, str] = {
    "rules": "## 规则（rules/）",
    "methodology": "## 方法论（methodology/）",
    "longterm": "## 长期记忆（longterm/）",
    "projects": "## 项目记忆（projects/）",
    "blueprints": "## 技术路径蓝图（blueprints/）",
    "experience": "## 经验（experience/）",
}

# 分区 → **写入哪个 INDEX 文件**（2026-09-23 裁定）
#
# 背景：A4 已把 experience 整区从根 INDEX 拆到 INDEX-experience.md（保 L0 ≤ 14K→20K 帽），
# 根 INDEX 里只留一句**指针**（“详见 INDEX-experience.md”）。
# 但两个写入方（`post_ingest_hook` / `fix_orphans`）当时把 index_path 硬编码为
# `root/INDEX.md` → **experience 卡又被追加回根 INDEX**，既白涨 L0、又把条目放错文件。
# 实测：2026-09-23 某经验卡被登记到根 INDEX 的 L180（该区本应只有指针）。
# 本映射即是修复：写入前先按目录选文件。
INDEX_FILE_FOR_DIR: dict[str, str] = {
    d: ("INDEX-experience.md" if d == "experience" else "INDEX.md")
    for d in SECTION_TITLES
}


def index_file_for_dir(dir_name: str) -> str | None:
    """该目录的 INDEX 条目应写入哪个文件（相对 hub 根）"""
    return INDEX_FILE_FOR_DIR.get(dir_name)


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


def dir_for_section(heading: str) -> str | None:
    """分区标题 → 目录名（反向查找；与 `SECTION_TITLES` 同源，不另维表）。

    用于审计“某条目登记到了哪个文件”——标题在两个 INDEX 文件里是同一套。
    """
    for d, title in SECTION_TITLES.items():
        if title == heading:
            return d
    return None


def expected_index_file(heading: str) -> str | None:
    """该分区标题下的条目**应该**住在哪个 INDEX 文件。

    返回 None 表示该标题不是卡片清单分区（如说明性分区）。
    """
    d = dir_for_section(heading)
    return INDEX_FILE_FOR_DIR.get(d) if d else None


__all__ = [
    "AUTHORITY_DIRS",
    "CARD_SECTION_TOKENS",
    "INDEX_FILE_FOR_DIR",
    "SECTION_TITLES",
    "card_slug",
    "dir_for_section",
    "expected_index_file",
    "index_file_for_dir",
    "is_card_section",
    "registered_slugs",
    "section_for_dir",
]
