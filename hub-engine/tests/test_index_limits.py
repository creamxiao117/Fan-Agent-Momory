"""描述长度上限的单一来源契约（2026-10-01）。

背景：这条策略曾散在两处——校验侧（audit_index 的 250/800）与派生侧（render_index/
hub_registry 的 40 字硬切）。分头写的结果是：派生侧把 142 条描述砍成半截句/仓库 id，
而校验侧允许 250/800 ⇒ **门禁不会红**，破损描述长期存活（2026-10-01 实测）。
本测试把「两侧必须同源」钉死。
"""

from common.index_limits import (
    DESC_LIMIT_BLUEPRINTS,
    DESC_LIMIT_DEFAULT,
    desc_limit_for_dir,
    desc_limit_for_section,
)
from scripts.audit_index import DESC_LIMIT_BLUEPRINTS as AUDIT_BP
from scripts.audit_index import DESC_LIMIT_DEFAULT as AUDIT_DEFAULT
from tools.hub_registry import SUMMARY_MAX_BY_DIR


def test_audit_and_common_agree():
    """校验侧（audit_index）与单一来源（common）必须取同一数值"""
    assert (AUDIT_DEFAULT, AUDIT_BP) == (DESC_LIMIT_DEFAULT, DESC_LIMIT_BLUEPRINTS)


def test_derivation_side_uses_same_limits():
    """派生侧（hub_registry 的分目录上限）不得再自定一套（历史坑：40 字硬切）"""
    for d, limit in SUMMARY_MAX_BY_DIR.items():
        assert limit == desc_limit_for_dir(d), f"{d} 派生上限与单一来源不一致"


def test_blueprints_allow_decision_info():
    """蓝图描述承载「技术路径 + 判级 + 状态」→ 必须显著宽于默认（2026-09-11 裁定）"""
    assert desc_limit_for_dir("blueprints") >= 3 * desc_limit_for_dir("rules")
    assert desc_limit_for_section("## 技术路径蓝图（blueprints/）") == DESC_LIMIT_BLUEPRINTS
    assert desc_limit_for_section("## 规则（rules/）") == DESC_LIMIT_DEFAULT
