# @version V1.0 / 2026-10-02 / pi / 行尾卫生门禁（双 CR / 混合行尾）单测
"""`check_encoding` 的第五道检查：行尾卫生（2026-10-02）。

背景（实测，2026-10-02）：中枢有 **23 个已提交文件** 的行尾是 `\\r\\r\\n`
（双重 CR），含全部 L1 规则卡（`global-rules` / `chinese-text-encoding-discipline`
/ `agent-code-discipline-iron-rule` / `dual-platform-coherence-discipline` /
`memory-hub-distill-last` / `cross-platform-sync-rule`）与 14 张 blueprint。

为什么必须门禁：
- git 视 `\\r` 为**内容**，所以 diff/提交都不报错，缺陷可长期潜伏；
- 但任何按「通用换行」读取的工具（Python `open()` 默认、多数 markdown 解析器）
  会把 `\\r\\r\\n` 解读成 **两个换行** ⇒ 每行后多出一个空行；
- 实测后果：某卡被写回时 74 行变 148 行（空行占比 0.62），并连带把
  `render_index --check` 打红、阻断整个中枢仓的提交。
- 编码门禁（UTF-8/BOM/乱码串）**查不到**这类缺陷，故单列一道。
"""

from pathlib import Path

from scripts.check_encoding import check_file, fix_eol, results


def _write(p: Path, data: bytes) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _run(p: Path) -> list[tuple[str, str, str]]:
    results.clear()
    check_file(p)
    return list(results)


def test_double_cr_is_fail(tmp_path):
    """核心回归：`\\r\\r\\n` 必须 FAIL（当前实现查不到 → 本用例先红）"""
    p = _write(tmp_path / "a.md", b"---\r\r\ntype: rule\r\r\n---\r\r\n\nbody\r\r\n")
    rows = _run(p)
    fails = [r for r in rows if r[0] == "FAIL" and "行尾" in r[2]]
    assert fails, f"双 CR 行尾应 FAIL，实际：{rows}"


def test_mixed_eol_is_fail(tmp_path):
    """同一文件里 CRLF 与裸 LF 混用 → FAIL（工具行为不可预测）"""
    p = _write(tmp_path / "b.md", b"line1\r\nline2\nline3\r\n")
    rows = _run(p)
    assert [r for r in rows if r[0] == "FAIL" and "行尾" in r[2]], f"混合行尾应 FAIL，实际：{rows}"


def test_pure_lf_is_pass(tmp_path):
    """纯 LF 合规（git 存储口径 + autocrlf 负责工作树转换）"""
    p = _write(tmp_path / "c.md", b"line1\nline2\n")
    rows = _run(p)
    assert not [r for r in rows if "行尾" in r[2] and r[0] == "FAIL"], rows


def test_pure_crlf_is_pass(tmp_path):
    """纯 CRLF 合规（既有 590 个文件即此形态，不能一改就红一片）"""
    p = _write(tmp_path / "d.md", b"line1\r\nline2\r\n")
    rows = _run(p)
    assert not [r for r in rows if "行尾" in r[2] and r[0] == "FAIL"], rows


def test_fix_eol_normalizes_double_cr_and_keeps_content(tmp_path):
    """修复：`\\r\\r\\n` → `\\n`，且**非空行内容逐字节不变**（不可毁内容）"""
    p = _write(tmp_path / "e.md", "---\r\r\ntype: rule\r\r\n\r\r\n中文正文\r\r\n".encode())
    before = [ln for ln in p.read_bytes().replace(b"\r", b"").split(b"\n") if ln.strip()]
    assert fix_eol(p) is True
    after = [ln for ln in p.read_bytes().split(b"\n") if ln.strip()]
    assert p.read_bytes() == "---\ntype: rule\n\n中文正文\n".encode()
    assert before == after, "非空行内容必须逐行保持不变"


def test_fix_eol_noop_on_clean_file(tmp_path):
    p = _write(tmp_path / "f.md", b"clean\r\nlines\r\n")
    assert fix_eol(p) is False
    assert p.read_bytes() == b"clean\r\nlines\r\n"
