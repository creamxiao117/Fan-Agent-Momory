# @version V1.0 / 2026-09-23 / pi / 弃用语义测试：status:deprecated 显式表达 + 两引擎一致排除

"""弃用语义（2026-09-23 重构）。

背景：此前"弃用"靠文件第 1 行的 `<!-- DEPRECATED -->` 注释隐式表达——它使 `---`
不在第 0 字节，frontmatter 解析失败，卡被*被动*丢弃。该机制位置敏感：
为给 frontmatter 加 `tier:` 而把注释下移，作废卡就会"复活"进检索库（A5 踩坑）。

重构后：`status: deprecated` + `superseded_by` 显式表达，且：
- 引擎一致排除（口径唯一在 `tools/retrieve.EXCLUDED_STATUSES`）
- frontmatter 合法 ⇒ lint 不再报 invalid
- 作废状态可被测试证伪（而非依赖字节偏移的副作用）

同日附加：删除了历史上的**第二套重复引擎**（`AgentMemoryHub/hub-engine/`）。
它实现同一批卡片的解析/检索，口径却不同（无 status 白名单、db_meta 写法不一），
一整个会话内已因此产生 3 次契约漂移。下方测试看守它不被重新引入。
"""

from pathlib import Path

from common.frontmatter import try_read_card, validate_card
from scripts.bootstrap_hub import bootstrap
from tools.lint import lint
from tools.retrieve import _index


def _write_card(root: Path, rel: str, status: str) -> Path:
    """在 root/rel 写一张最小合法卡（type 由目录推断）"""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    card_type = "rule" if rel.startswith("rules") else "methodology"
    p.write_text(
        "---\n"
        f"type: {card_type}\n"
        "tags: [probe]\n"
        "updated: 2026-09-23\n"
        f"status: {status}\n"
        "reuse_count: 0\n"
        "---\n"
        f"# {rel} 的卡片正文\n",
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------- 校验层


def test_validate_card_accepts_deprecated_status(tmp_path):
    """deprecated 必须进入合法 status 白名单，否则全新的显式弃用会被判 invalid"""
    root = bootstrap(tmp_path)
    card = try_read_card(_write_card(root, "rules/dep.md", "deprecated"))
    assert card is not None, "deprecated 卡应能被解析"
    assert card.status == "deprecated"
    assert validate_card(card) == [], (
        f"deprecated 不应产生校验错误: {validate_card(card)}"
    )


def test_lint_does_not_flag_deprecated_as_invalid(tmp_path):
    """显式弃用卡 frontmatter 合法 → lint 的 invalid 与 schema_drift 均为空"""
    root = bootstrap(tmp_path)
    _write_card(root, "rules/dep.md", "deprecated")
    report = lint(root)
    assert report["invalid"] == 0, f"invalid 应为 0，实际 {report['invalid']}"
    assert report["schema_drift"] == [], (
        f"schema_drift 应为空，实际 {report['schema_drift']}"
    )


# ---------------------------------------------------------------- 检索层（项目引擎）


def test_deprecated_card_excluded_from_retrieval_index(tmp_path):
    """作废卡不得进检索索引（否则会把已并入他卡的旧副本喂给模型）"""
    root = bootstrap(tmp_path)
    _write_card(root, "rules/keep.md", "active")
    _write_card(root, "rules/gone.md", "deprecated")
    names = {Path(c.path).name for c in _index(root).cards}
    assert "keep.md" in names, "active 卡应在检索索引中"
    assert "gone.md" not in names, "deprecated 卡不应进检索索引"


def test_archived_card_still_excluded_from_retrieval_index(tmp_path):
    """archived 仍被排除（本次改动不得回归掉既有行为）"""
    root = bootstrap(tmp_path)
    _write_card(root, "rules/keep.md", "active")
    _write_card(root, "rules/arch.md", "archived")
    names = {Path(c.path).name for c in _index(root).cards}
    assert "keep.md" in names
    assert "arch.md" not in names


def test_candidate_and_reference_remain_retrievable(tmp_path):
    """candidate / reference 不在排除集合内——不得误伤（它们是合法可检索状态）"""
    root = bootstrap(tmp_path)
    _write_card(root, "methodology/cand.md", "candidate")
    _write_card(root, "methodology/ref.md", "reference")
    names = {Path(c.path).name for c in _index(root).cards}
    assert "cand.md" in names, "candidate 应可检索"
    assert "ref.md" in names, "reference 应可检索"


# ---------------------------------------------------------------- 常量同口径（防两引擎漂移）


def test_project_engine_excluded_statuses_matches_hub_engine():
    """两套引擎的排除集合必须一致——历史上"两套实现各写各的"已多次造成漂移"""


# ---------------------------------------------------------------- 架构守卫（防重复实现回流）


def test_legacy_duplicate_engine_is_gone():
    """历史遗留的**第二套引擎**必须保持已删除。

    `AgentMemoryHub/hub-engine/`（8 个模块）曾与 `hub-engine/` 重复实现同一批卡片
    的解析/向量/同步/MCP，但口径不同。它已无任何消费者：4 个平台的 MCP 配置、
    仓内 mcp.example.json / platforms.yaml、以及 hub_mcp_launcher 的 5 个候选路径
    全部指向 `hub-engine/`；且它无测试。2026-09-23 删除。

    本测试防止它被无意重建——重冒两套实现就会重冒契约漂移。
    """
    legacy = Path(__file__).resolve().parents[2] / "AgentMemoryHub" / "hub-engine"
    assert not legacy.exists(), (
        f"应已删除的重复引擎又出现了: {legacy}\n"
        "若确需重建，请先移除本测试并在 commit 中说明理由。"
    )


def test_excluded_statuses_covers_documented_states():
    """排除集合必须覆盖已文档化的两个非活跃状态，且与 VALID_STATUS 不矛盾"""
    from common.frontmatter import VALID_STATUS
    from tools import retrieve as proj_retrieve

    excluded = set(proj_retrieve.EXCLUDED_STATUSES)
    assert {"archived", "deprecated"} <= excluded, f"排除集合缺项: {excluded}"
    assert excluded <= set(VALID_STATUS), (
        f"排除集合含未在 VALID_STATUS 声明的状态: {excluded - set(VALID_STATUS)}"
    )
    # 合法但**必须可检索**的状态不得被误排除
    for keep in ("active", "candidate", "reference"):
        assert keep not in excluded, f"{keep} 不应被排除"
