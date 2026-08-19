"""blueprint 卡型：validate / ingest 落位 / boostrap 组块 / search 过滤 / slug 解析"""

from pathlib import Path

from common.frontmatter import parse_card, validate_card
from scripts.bootstrap_hub import bootstrap
from sync import ingest
from tools.mcp_handlers import (
    SUBDIR_BY_TYPE,
    TASK_KIND_TYPES,
    hub_bootstrap,
    hub_search,
)
from tools.mcp_policy import AUTHORITY_DIRS, resolve_slug

BLUEPRINT_TEXT = """---
type: blueprint
tags:
- agent-architecture
- routing
updated: '2026-08-19'
status: reference
reuse_count: 0
---

## 领域
测试蓝图
## 目标
决策问题
## 可选技术路径
### 路径 A：事务写回
- 证据等级：t1
"""


def write_draft(root: Path, name: str, text: str) -> None:
    d = root / ".sync" / "drafts" / "trae_draft"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


def test_blueprint_is_valid_type():
    card = parse_card(BLUEPRINT_TEXT)
    assert validate_card(card) == []
    assert card.type == "blueprint"


def test_blueprint_type_belongs_to_blueprints_dir():
    assert SUBDIR_BY_TYPE["blueprint"] == "blueprints"
    assert "blueprints" in AUTHORITY_DIRS
    assert "blueprints" in TASK_KIND_TYPES["ideation"]


def test_ingest_promotes_blueprint_into_blueprints(tmp_path):
    root = bootstrap(tmp_path)
    write_draft(root, "demo-blueprint.md", BLUEPRINT_TEXT)
    res = ingest(root, "trae")
    assert res["promoted"] == 1
    dst = root / "blueprints" / "demo-blueprint.md"
    assert dst.exists()
    assert parse_card(dst.read_text(encoding="utf-8")).type == "blueprint"


def test_bootstrap_ideation_includes_blueprints_block(tmp_path):
    root = bootstrap(tmp_path)
    write_draft(root, "demo-blueprint.md", BLUEPRINT_TEXT)
    ingest(root, "trae")
    res = hub_bootstrap(
        root, "ideation", context="要给新项目定技术路径", platform="trae"
    )
    kinds = {b["kind"] for b in res["blocks"]}
    assert "blueprints" in kinds


def test_hub_search_by_blueprint_type(tmp_path):
    root = bootstrap(tmp_path)
    write_draft(root, "demo-blueprint.md", BLUEPRINT_TEXT)
    ingest(root, "trae")
    res = hub_search(root, "Agent 架构 路径", types=["blueprint"], platform="trae")
    assert res["hits"], "blueprint 类型卡应能被按类型检索命中"


def test_resolve_slug_finds_blueprint(tmp_path):
    root = bootstrap(tmp_path)
    write_draft(root, "demo-blueprint.md", BLUEPRINT_TEXT)
    ingest(root, "trae")
    p = resolve_slug(root, "demo-blueprint")
    assert p == root / "blueprints" / "demo-blueprint.md"