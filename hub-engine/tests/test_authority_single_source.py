"""权威区目录「单一事实源」看守（2026-10-05 立）。

背景：`authority_dirs` 曾有 **6 份副本、4 种内容**，而 `hub.config.yaml` 的那份**无人消费**
（`common/config.py::HubConfig` 只暴露 platforms/draft_dir）⇒ 声明的单一事实源是装饰性的。
实测漂移后果：`tools/lint.py` 缺 experience（236 张卡不进孤儿判定、engine.py status/audit 计数漏区）、
`tools/mcp_policy.py` 多 libs/retro（slug 可解析到非卡片文件）、`scripts/metrics_daily.py` 多 libs/retro
（卡片总数虚高）、`scripts/secret_sentry.py` 多 notes（误报高危）。

本测试防两件事：
1. **回潮**：任何副本重新自持一份字面量（以 `is` 断言，只有 import 同一对象才成立）；
2. **声明漂移**：`hub.config.yaml` 与 `common/authority.py` 不一致（改一处漏另一处）。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from common import authority as A

_HUB = Path(__file__).resolve().parents[2] / "AgentMemoryHub"


def test_hub_config_matches_single_source():
    """hub.config.yaml 的 authority_dirs / non_authority_dirs 必须与常量逐项一致。"""
    cfg = yaml.safe_load((_HUB / "hub.config.yaml").read_text(encoding="utf-8"))
    assert tuple(cfg["authority_dirs"]) == A.AUTHORITY_DIRS, (
        "hub.config.yaml 的 authority_dirs 与 common/authority.py 漂移（改一处漏另一处）"
    )
    assert tuple(cfg["non_authority_dirs"]) == A.NON_AUTHORITY_DIRS, (
        "hub.config.yaml 的 non_authority_dirs 与 common/authority.py 漂移"
    )


def test_experience_is_authority_not_non_authority():
    """experience 于 2026-09-10 升级进权威区——两处互斥性由本断言钉死。"""
    assert "experience" in A.AUTHORITY_DIRS
    assert "experience" not in A.NON_AUTHORITY_DIRS
    assert "notes" in A.NON_AUTHORITY_DIRS and "notes" not in A.AUTHORITY_DIRS
    assert "retro" in A.NON_AUTHORITY_DIRS and "retro" not in A.AUTHORITY_DIRS


def test_no_module_keeps_a_private_copy():
    """所有消费方都必须 import 同一个对象（`is` / frozenset 相等），不得自持字面量。"""
    from scripts import index_consistency as ic
    from scripts import metrics_daily as md
    from scripts import secret_sentry as ss
    from tools import hub_registry as hr
    from tools import lint as lint_mod
    from tools import mcp_policy as mp
    from tools import retrieve

    assert lint_mod.AUTHORITY_DIRS is A.AUTHORITY_DIRS
    assert lint_mod.NON_AUTHORITY_DIRS is A.NON_AUTHORITY_DIRS
    assert mp.AUTHORITY_DIRS is A.CARD_DIRS
    assert retrieve._ACTIVE_DIRS is A.CARD_DIRS
    assert hr.CARD_DIRS is A.CARD_DIRS
    assert ic.AUTHORITY_DIRS is A.AUTHORITY_DIRS
    assert md._AUTHORITY_DIRS is A.CARD_DIRS
    assert frozenset(A.CARD_DIRS) == ss.AUTHORITY_DIRS  # frozenset 是新建对象，比内容
    assert "notes" not in ss.AUTHORITY_DIRS, "notes 不参与检索/注入，不得当高危区扫描"


def test_audit_scan_dirs_do_not_duplicate_experience():
    """audit_index 的 _ALL_SCAN_DIRS 不得重复 experience（修复前的补偿写法会与新的
    AUTHORITY_DIRS 重叠，导致同一目录被扫两遍）。"""
    from scripts import audit_index

    assert len(audit_index._ALL_SCAN_DIRS) == len(set(audit_index._ALL_SCAN_DIRS))
    assert set(audit_index._ALL_SCAN_DIRS) >= set(A.AUTHORITY_DIRS)


def test_gate_scope_l0_prefixes_derived_from_authority():
    """L0 门禁面（权威区目录）由 common/authority.py 派生，不得再手措清单。"""
    from common import gate_scope

    assert tuple(f"{d}/" for d in A.AUTHORITY_DIRS) == gate_scope.L0_PREFIXES


def test_tier_scope_values_reference_real_card_dirs():
    """task_tier 的检索子区是**有意收窄的语义子集**（不是权威区副本），不应派生；
    但它的每个取值必须指向真实存在的卡目录——否则是拼写错/已退役目录（如 libs）。"""
    from tools import task_tier

    valid = set(A.AUTHORITY_DIRS) | set(A.NON_AUTHORITY_DIRS)
    for table_name in ("TIER_SCOPE", "LEGACY_KIND_SCOPE"):
        table = getattr(task_tier, table_name)
        for tier, dirs in table.items():
            if not dirs:
                assert tier == "light", f"{table_name}[{tier}] 为空——只有 light 允许空范围（不检索）"
                continue
            assert set(dirs) <= valid, f"{table_name}[{tier}] 含非卡目录 {sorted(set(dirs) - valid)}（退役/拼写错？）"
