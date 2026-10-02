# @version V1.0 / 2026-10-02 / pi / 模块台账与职责重复检测单测（M0/Task 5）
"""`inventory` 单测：**尺子本身必须可信**（本模块存在的理由就是上一把尺子量不出冗余）。

V1 曾用「产物文件名字面量重叠」聚类 ⇒ 把 40+ 个活模块误判 duplicate。故这里的用例
主要锁"不会误报"与"不发明结论"：
- 引用度必须认 `from a.b.X import y`（V1 的正则漏它 ⇒ 误判 `snippet` 等 unused）
- 重复判据必须来自**声明**，`review` 只是建议
- 声明必须**被验证**（保留者/被取代者都得还在），否则台账会撒谎
"""

import json
from pathlib import Path

from scripts.inventory import (
    DECLARED_DUPLICATES,
    HUB,
    INVENTORY_PATH,
    build,
    check,
    declared_map,
    imported_names,
    jaccard,
    module_key,
    review_pairs,
    verify_declarations,
)


def test_module_key_is_unique_and_kind_prefixed():
    """V1 用裸 stem ⇒ `tools/lint.py` 与 `commands/lint.py` 撞名互相"重复"。"""
    a = module_key(Path("hub-engine/tools/lint.py"))
    b = module_key(Path("hub-engine/commands/lint.py"))
    assert a == "tools/lint" and b == "commands/lint" and a != b


def test_imported_names_handles_from_import():
    """本仓跨模块导入**全部**是 `from a.b.X import y` 形态；漏它就会误判 unused。"""
    src = "from tools.snippet import extract_snippet\nimport json\nfrom scripts.card_fields import set_fields\n"
    names = imported_names(src)
    assert {"snippet", "json", "card_fields"} <= names


def test_imported_names_survives_syntax_error():
    assert imported_names("def broken(:") == set()


def test_jaccard_bounds():
    assert jaccard(set(), {"a"}) == 0.0
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_declared_map_shape():
    """声明表必须有 keep/retire/why 三字段（why 是给人复核的判据，不可省）。"""
    m = declared_map()
    assert m, "应至少有一条声明"
    for grp in DECLARED_DUPLICATES:
        assert grp["keep"] and grp["retire"] and grp["why"], grp
        for r in grp["retire"]:
            assert m[r] == grp["keep"]


def test_verify_declarations_detects_expired_entry():
    """声明过期（被取代者已不在磁盘）必须报出来——否则台账会持续撒谎。"""
    keys = {"scripts/render_index": Path("x"), "scripts/audit_index": Path("y")}
    errs = verify_declarations(keys)
    assert any("index_consistency" in e for e in errs), errs


def test_review_requires_same_gate_same_kind_and_high_similarity():
    """`review` 只是**建议**：三条判据不同时满足就不该出现（防 V1 那种误报洪水）。"""
    rows = [
        {
            "module": "scripts/a",
            "kind": "scripts",
            "gate_role": "pre-commit",
            "resp_words": ["index", "lint"],
        },
        {
            "module": "scripts/b",
            "kind": "scripts",
            "gate_role": "pre-commit",
            "resp_words": ["index", "lint"],
        },
        {  # 不同 kind
            "module": "tools/c",
            "kind": "tools",
            "gate_role": "pre-commit",
            "resp_words": ["index", "lint"],
        },
        {  # 无 gate_role
            "module": "scripts/d",
            "kind": "scripts",
            "gate_role": None,
            "resp_words": ["index", "lint"],
        },
    ]
    pairs = review_pairs(rows)
    assert ["scripts/a", "scripts/b"] in pairs
    assert not any("tools/c" in p for p in pairs)


def test_build_is_reproducible_and_declarations_hold():
    """真实仓库：两次构建除时间戳外必须一致；声明必须全部成立。"""
    a = build()
    b = build()
    assert a["declaration_errors"] == [], a["declaration_errors"]
    a.pop("generated_at")
    b.pop("generated_at")
    for d in (a, b):
        for m in d["modules"]:
            m.pop("refs_code"), m.pop("refs_test"), m.pop("refs_doc")
    assert a == b, "同磁盘的两次构建必须一致（否则台账不可复现）"
    assert a["totals"]["modules"] > 50
    assert a["totals"].get("duplicate", 0) < 20, "duplicate 数量异常大 = 尺子又在误报"


def test_check_detects_stale_ledger(tmp_path, monkeypatch):
    """产物与磁盘不一致必须红（负样本）：注入一个过期台账，check 必须报错。"""
    import scripts.inventory as inv

    fake = tmp_path / "INVENTORY.json"
    fake.write_text(json.dumps({"modules": [], "totals": {}}), encoding="utf-8")
    monkeypatch.setattr(inv, "INVENTORY_PATH", fake)
    errs = inv.check()
    assert errs and "INVENTORY.json" in errs[0]


def test_real_ledger_is_current():
    """真实台账必须是最新的（否则巡检/门禁的结论建立在过期数据上）。"""
    assert check() == [], check()


def test_inventory_path_points_into_hub():
    """台账落在中枢 system 侧（与 capabilities 同区），而非引擎目录里。"""
    assert INVENTORY_PATH.parent.name == "scripts"
    assert INVENTORY_PATH.parent.parent == HUB
