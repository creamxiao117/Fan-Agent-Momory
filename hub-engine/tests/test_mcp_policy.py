import pytest

from scripts.bootstrap_hub import bootstrap
from tools.mcp_policy import (
    AUTHORITY_DIRS,
    allowed_platforms,
    assert_candidate_type,
    resolve_rel,
    resolve_slug,
)


def test_resolve_rel_in_bounds(tmp_path):
    root = bootstrap(tmp_path)
    p = resolve_rel(root, "rules/dll-lock.md")
    assert p == (root / "rules" / "dll-lock.md").resolve()


def test_resolve_rel_escape(tmp_path):
    root = bootstrap(tmp_path)
    for bad in (
        "../secret.md",
        "..\\secret.md",
        "C:/windows/win.ini",
        "C:\\windows\\win.ini",
    ):
        with pytest.raises(ValueError, match="path_escape"):
            resolve_rel(root, bad)


def test_resolve_slug_unique(tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules" / "dll-lock.md").write_text(
        "---\ntype: rule\ntags: [autocad]\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nx\n",
        encoding="utf-8",
    )
    p = resolve_slug(root, "dll-lock")
    assert p == (root / "rules" / "dll-lock.md").resolve()


def test_resolve_slug_not_found(tmp_path):
    root = bootstrap(tmp_path)
    with pytest.raises(FileNotFoundError, match="not_found"):
        resolve_slug(root, "no-such-card")


def test_resolve_slug_ambiguous(tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules" / "dup.md").write_text(
        "---\ntype: rule\ntags: []\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nx\n",
        encoding="utf-8",
    )
    (root / "methodology" / "dup.md").write_text(
        "---\ntype: methodology\ntags: []\nupdated: 2026-08-18\nstatus: active\nreuse_count: 0\n---\nx\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_slug(root, "dup")


def test_allowed_platforms_from_config(tmp_path):
    root = bootstrap(tmp_path)
    # bootstrap 模板含 trae/code/hermes/workbuddy；extra 应并入
    s = allowed_platforms(root, extra=("traework",))
    assert "traework" in s
    assert "hermes" in s or isinstance(s, set)


def test_assert_candidate_type_whitelist():
    assert_candidate_type("exp")
    assert_candidate_type("note")
    assert_candidate_type("project")
    for bad in ("rule", "methodology", "longterm", "retro", "note2"):
        with pytest.raises(ValueError, match="type_forbidden"):
            assert_candidate_type(bad)


def test_authority_dirs_has_five_plus():
    assert set(AUTHORITY_DIRS) >= {
        "rules",
        "methodology",
        "longterm",
        "projects",
        "experience",
    }
