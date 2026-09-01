"""auto_flywheel.py 扫描口径单元测试。

锁定 2026-09-01 健康度检查修复的缺陷：
旧版 scan_drafts 用 rglob 递归统计草稿，与 sync.ingest 只扫
<platform>_draft/*.md（根目录、不递归）的口径不一致，
导致「扫描到 N 张但提升 0 张」的假象（candidates/、retro/ 子目录被误计）。

覆盖：
1. 根目录 *.md → 计入对应平台
2. candidates/ 与 retro/ 子目录 → 不计入
3. 扁平结构（.sync/drafts/*.md）→ 归入 default
4. 与 sync.ingest 口径一致：扫描数 == 可提升数
"""

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from auto_flywheel import scan_drafts


def _make_draft(root: Path, rel: str, *, with_fm: bool = True) -> Path:
    """在 root/.sync/drafts/ 下创建一张最小合法草稿。"""
    p = root / ".sync" / "drafts" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if with_fm:
        p.write_text(
            "---\r\ntype: exp\r\ntags: [test]\r\nupdated: '2026-09-01'\r\nstatus: active\r\n---\r\n\r\n测试内容\r\n",
            encoding="utf-8",
        )
    else:
        p.write_text("无 frontmatter 的裸文本\r\n", encoding="utf-8")
    return p


def test_root_level_draft_counted(tmp_path: Path):
    """平台目录下根级 *.md 应计入该平台。"""
    _make_draft(tmp_path, "trae_draft/card-a.md")
    _make_draft(tmp_path, "trae_draft/card-b.md")
    result = scan_drafts(tmp_path)
    assert result == {"trae": [
        tmp_path / ".sync" / "drafts" / "trae_draft" / "card-a.md",
        tmp_path / ".sync" / "drafts" / "trae_draft" / "card-b.md",
    ]}


def test_subdirs_not_counted(tmp_path: Path):
    """candidates/ 与 retro/ 子目录不属于提升输入，不计入（回归锁定）。"""
    _make_draft(tmp_path, "trae_draft/card-a.md")
    _make_draft(tmp_path, "trae_draft/candidates/candidate-1.md")
    _make_draft(tmp_path, "trae_draft/retro/retro-2026-08-17.md")
    result = scan_drafts(tmp_path)
    assert len(result.get("trae", [])) == 1
    assert result["trae"][0].name == "card-a.md"


def test_flat_drafts_default_platform(tmp_path: Path):
    """扁平结构（drafts 根级 *.md）归入 default 平台。"""
    _make_draft(tmp_path, "loose.md")
    result = scan_drafts(tmp_path)
    assert "default" in result
    assert result["default"][0].name == "loose.md"


def test_non_draft_dir_ignored(tmp_path: Path):
    """不匹配 *_draft 命名约定的子目录一律忽略。"""
    _make_draft(tmp_path, "misc/stray.md")
    result = scan_drafts(tmp_path)
    assert result == {}


def test_empty_and_missing_dirs(tmp_path: Path):
    """无 drafts 目录 / 空目录 → 空结果（dry-run 输出「无待处理草稿」）。"""
    assert scan_drafts(tmp_path) == {}
    (tmp_path / ".sync" / "drafts").mkdir(parents=True)
    assert scan_drafts(tmp_path) == {}


def test_consistent_with_ingest_scan(tmp_path: Path):
    """与 sync.ingest 扫描口径一致：本函数统计数 == ingest 可见提升源数。"""
    _make_draft(tmp_path, "hermes_draft/ok.md")
    _make_draft(tmp_path, "hermes_draft/candidates/c.md")
    _make_draft(tmp_path, "hermes_draft/retro/r.md")
    scanned = scan_drafts(tmp_path)
    n_scanned = len(scanned.get("hermes", []))
    # 复现 ingest 的扫描（sync.py: drafts.glob("*.md")）
    drafts_dir = tmp_path / ".sync" / "drafts" / "hermes_draft"
    n_ingest = len(list(drafts_dir.glob("*.md")))
    assert n_scanned == n_ingest == 1
