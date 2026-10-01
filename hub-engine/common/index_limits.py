# 索引**描述长度上限**的单一事实源（2026-10-01 抽取）。
#
# 为何要抽：同一策略此前散落在两处——`scripts/audit_index.py`（校验侧）与
# 派生侧（`tools/hub_registry.py` / 渲染器）。分头写就会漂移，而漂移的形态很难看：
# 派生侧按 40 字硬切 → INDEX 里全是 `gh-…` / 半截句（实测 142 条不合格），
# 校验侧却允许 250/800 → **门禁不会红**，于是破损描述长期存活。
#
# 数值依据（2026-09-11 用户裁定）：蓝图描述承载「技术路径 A/B/C + 判级 + 状态」，
# 250 字符必然截断决策信息 → 蓝图单列 800；其余分区维持 250（防摘要退化为正文）。
#
# 注意：spec S3 曾写「≤40 字」，那是为 **L0 预算**设的；2026-10-01 枚举已移出 L0
# （见 docs/compose/plans/2026-10-01-single-source-l0-shape.md），40 字约束随之失去理由。

from __future__ import annotations

DESC_LIMIT_DEFAULT = 250
DESC_LIMIT_BLUEPRINTS = 800


def desc_limit_for_dir(dir_name: str) -> int:
    """目录名 → 描述上限（目录口径，供派生/渲染侧使用）。"""
    return DESC_LIMIT_BLUEPRINTS if dir_name == "blueprints" else DESC_LIMIT_DEFAULT


def desc_limit_for_section(section: str) -> int:
    """分区标题 → 描述上限（标题口径，供校验侧使用；按标题内目录名判定，抗中文标题改写）。"""
    return DESC_LIMIT_BLUEPRINTS if "blueprints" in section else DESC_LIMIT_DEFAULT


__all__ = [
    "DESC_LIMIT_BLUEPRINTS",
    "DESC_LIMIT_DEFAULT",
    "desc_limit_for_dir",
    "desc_limit_for_section",
]
