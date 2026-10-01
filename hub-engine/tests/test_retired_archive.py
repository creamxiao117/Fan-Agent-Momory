"""退役归档区的守卫测试（2026-10-01）。

三个不变量：
1. **标签**：归档区每个文件都带 `@status: retired` 头（否则日后无人知道它是死的还是活的）；
2. **清单一致**：`RETIRED.json` 与磁盘文件**双向**相等（防「归档了但没登记」与「登记了但文件没了」）；
3. **不得复活**：活的代码/钩子/cmd 不得再引用退役模块（防有人照着老文档把归档件接回去）。

另加一条：保留体（manual-cli / forbidden-guarded）必须带 `@status:` 标签，
否则它们会在下一次清理里被当成「无标记者」误删。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# (归档目录, 清单文件)
ARCHIVES: tuple[tuple[str, str], ...] = (
    ("hub-engine/scripts/_retired", "RETIRED.json"),
    ("hub-engine/tests/_retired", "RETIRED.json"),
    ("scripts/_retired", "RETIRED.json"),
)

# 保留体：文件名 → 期望的标签前缀
KEPT_WITH_STATUS = {
    "scripts/merge-methodology.py": "forbidden-guarded",
    "scripts/deduplicate-experience.py": "forbidden-guarded",
    "scripts/backup-rules.py": "manual-cli",
    "scripts/fix_type_dir_mismatch.py": "manual-cli",
    "hub-engine/scripts/proofread_index_desc.py": "manual-cli",
}

REF_SCAN_EXT = {".py", ".cmd", ".bat", ".ps1", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini"}


def _retired_files(rel_dir: str) -> list[Path]:
    d = REPO / rel_dir
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.name != "RETIRED.json" and p.suffix != ".md")


def _manifest(rel_dir: str, name: str) -> dict:
    p = REPO / rel_dir / name
    assert p.exists(), f"归档清单缺失：{rel_dir}/{name}"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.parametrize("rel_dir,_name", ARCHIVES)
def test_every_archived_file_is_tagged(rel_dir: str, _name: str):
    """归档件必须带 @status: retired 头（含退役日期/原路径/取代者/理由/恢复命令）"""
    files = _retired_files(rel_dir)
    assert files, f"{rel_dir} 为空——要么归档被误删，要么清单已过期"
    for p in files:
        head = p.read_text(encoding="utf-8", errors="ignore")[:800]
        assert "@status: retired" in head, f"{p.name} 缺少 @status: retired 标签"
        assert "@original_path:" in head, f"{p.name} 缺少 @original_path（无法恢复）"
        assert "@superseded_by:" in head, f"{p.name} 缺少 @superseded_by（无法判断是否真死）"
        assert "@reason:" in head, f"{p.name} 缺少 @reason"


def test_manifest_matches_disk_both_ways():
    """清单 ↔ 磁盘 双向一致（归档未登记 / 登记未归档 都要红）"""
    on_disk = {f"{rel}/{p.name}" for rel, _ in ARCHIVES for p in _retired_files(rel)}
    in_manifest: set[str] = set()
    for rel_dir, name in ARCHIVES:
        for key in _manifest(rel_dir, name)["items"]:
            in_manifest.add(key)
    assert on_disk - in_manifest == set(), f"归档了但未登记：{sorted(on_disk - in_manifest)}"
    assert in_manifest - on_disk == set(), f"登记了但文件不在：{sorted(in_manifest - on_disk)}"


def _live_reference_files() -> list[Path]:
    out = []
    for p in REPO.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.relative_to(REPO).parts)
        if parts & {".git", ".venv", "__pycache__", "node_modules", "work", "_retired", ".backup", "docs"}:
            continue
        if p.suffix.lower() in REF_SCAN_EXT or p.name.startswith("pre-commit"):
            out.append(p)
    return out


def test_retired_modules_are_not_referenced_by_live_code():
    """防复活：活代码/钩子/cmd 不得再引用退役模块（docs/ 里的历史叙述不算）"""
    stems = {p.stem for rel, _ in ARCHIVES for p in _retired_files(rel) if p.suffix == ".py"}
    # 归档的测试文件（test_xxx）不作为「被引用」的模块名
    stems = {s for s in stems if not s.startswith("test_")}
    offenders: list[str] = []
    for p in _live_reference_files():
        text = p.read_text(encoding="utf-8", errors="ignore")
        rel = p.relative_to(REPO).as_posix()
        for stem in stems:
            pats = (
                re.compile(rf"\bfrom\s+(?:[\w.]+\.)?{re.escape(stem)}\b"),
                re.compile(rf"\bimport\s+(?:[\w.]+\.)?{re.escape(stem)}\b"),
                re.compile(rf"-m\s+scripts\.{re.escape(stem)}\b"),
                # 可执行路径形态（subprocess/编排器调用）：**必须在引号内**——
                # 反引号里的散文提及（如注释里的“`fix_orphans.py`（已退役）”）不算引用。
                re.compile(rf"[\"'][^\"']*{re.escape(stem)}\.py[\"']"),
            )
            if any(pat.search(text) for pat in pats):
                offenders.append(f"{rel} → {stem}")
    assert offenders == [], "退役模块被活代码引用（要么恢复它，要么改引用）：\n  " + "\n  ".join(offenders)


def test_kept_files_declare_status():
    """保留体必须自报状态（manual-cli / forbidden-guarded），否则下次清理会误删"""
    missing = []
    for rel, expect in KEPT_WITH_STATUS.items():
        p = REPO / rel
        if not p.exists():
            missing.append(f"{rel} 不存在（若已退役请同步本测试与归档清单）")
            continue
        head = p.read_text(encoding="utf-8", errors="ignore")[:800]
        if f"@status: {expect}" not in head:
            missing.append(f"{rel} 缺少 `@status: {expect}` 标签")
    assert missing == [], "\n  ".join(missing)


def test_audit_tool_skips_archives():
    """死代码审计必须跳过归档区（否则名单会被“已知已退役”的文件淹没）"""
    from scripts.audit_dead_modules import SKIP_DIRS

    assert "_retired" in SKIP_DIRS
