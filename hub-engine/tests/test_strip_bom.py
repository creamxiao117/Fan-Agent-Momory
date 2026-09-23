# @version V1.0 / 2026-09-23 / pi / strip_bom 测试：按扩展名剥离 BOM，字节级安全

"""`strip_bom` 单测（2026-09-23）。

背景：`check_encoding.py` 对 `.md` 等含 BOM 只记 **WARN**（不 FAIL），于是违规
静默累积——实测中枢有 19 个 .md 带 BOM。strip_bom 补上"修"的缺口。
关键安全要求：只删文件头 3 字节，其余字节一一不变；且**绝不碰** `.ps1` 这类
必须带 BOM 的类型。
"""

from pathlib import Path

from scripts.check_encoding import BOM_EXPECT
from scripts.strip_bom import BOM, find_bom_files, strip_one


def _write(p: Path, data: bytes) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def test_strip_one_removes_only_bom_bytes(tmp_path):
    """字节级安全：除 BOM 外其余字节逐一致"""
    body = "---\ntype: exp\n---\n\n中文正文\n".encode()
    p = _write(tmp_path / "a.md", BOM + body)
    assert strip_one(p) is True
    assert p.read_bytes() == body, "除 BOM 外不得改动任何字节"


def test_strip_one_noop_without_bom(tmp_path):
    p = _write(tmp_path / "b.md", "---\n无 BOM\n".encode())
    assert strip_one(p) is False
    assert p.read_bytes() == "---\n无 BOM\n".encode()


def test_find_bom_files_skips_extensions_that_require_bom(tmp_path):
    """.ps1 必须带 BOM（PS5.1 按 ANSI 解析会爆中文）→ 绝不能被列入待剥离"""
    assert BOM_EXPECT.get(".ps1") is True, "前置假设：.ps1 期望带 BOM"
    _write(tmp_path / "keep.ps1", BOM + b"$x = 'a'\n")
    _write(tmp_path / "strip.md", BOM + b"---\nx\n")
    _write(tmp_path / "clean.md", b"---\nx\n")

    hits = {p.name for p, _ in find_bom_files(tmp_path)}
    assert "strip.md" in hits, "期望无 BOM 却带 BOM 的 .md 应被列出"
    assert "keep.ps1" not in hits, ".ps1 必须带 BOM，不得被剥离"
    assert "clean.md" not in hits, "无 BOM 的文件不应被列出"


def test_find_bom_files_skips_runtime_dirs(tmp_path):
    """运行态/缓存目录默认跳过（避免对 .git/.backup/.sync 造成无意义改动）"""
    _write(tmp_path / ".git" / "x.md", BOM + b"x")
    _write(tmp_path / ".backup" / "x.md", BOM + b"x")
    _write(tmp_path / "real.md", BOM + b"x")
    hits = {p.name for p, _ in find_bom_files(tmp_path)}
    assert hits == {"real.md"}, f"应只命中 real.md，实际: {hits}"


def test_find_bom_files_accepts_explicit_file_target(tmp_path):
    """显式传入文件时不受跳过规则限制（用于 .sync/conflicts 下已跟踪的归档）"""
    f = _write(tmp_path / ".sync" / "conflicts" / "archived.md", BOM + b"x")
    assert find_bom_files(tmp_path) == [], "默认扫描应跳过 .sync"
    got = find_bom_files(f)
    assert got and got[0][0] == f, "显式文件目标应被检查"


def test_strip_is_byte_safe_on_multibyte_content(tmp_path):
    """含中文/emoji 的内容剥离后必须逐字节一致（防误用文本模式重写）"""
    body = "中文 emoji 🎯 CRLF\r\n第二行\n".encode()
    p = _write(tmp_path / "c.md", BOM + body)
    strip_one(p)
    assert p.read_bytes() == body
