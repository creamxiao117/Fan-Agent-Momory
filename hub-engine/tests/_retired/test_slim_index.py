# @status: retired
# @retired_at: 2026-10-01
# @original_path: hub-engine/tests/test_slim_index.py
# @superseded_by: hub-engine/tests/test_render_index.py
# @reason: 随 slim_index 退役（被测对象已归档）
# @retired_from_commit: a7e941b
# @restore: git checkout a7e941b -- hub-engine/tests/test_slim_index.py && git mv hub-engine/tests/test_slim_index.py hub-engine/tests/test_slim_index.py

# hub-engine/tests/test_slim_index.py
from scripts.slim_index import slim_line, slim_text


def test_slim_truncates_description():
    line = "- foo-bar    " + "描述" * 50
    out = slim_line(line, max_desc=40)
    assert out.startswith("- foo-bar")
    assert "foo-bar" in out
    desc = out.split("foo-bar", 1)[1].strip()
    assert len(desc) <= 42  # 含截断省略号


def test_slim_keeps_headers_and_comments():
    text = "# 中枢索引\n\n<!-- [全局] 注释 -->\n\n## 规则（rules/）\n"
    assert slim_text(text) == text


def test_slim_short_desc_untouched():
    line = "- short-name    短描述"
    assert slim_line(line) == line


def test_slim_ignores_non_card_bullets():
    line = "- rules/        权威规则（命令式/约束式，违反有代价）"
    assert slim_line(line) == line


def test_main_writes_and_budget(tmp_path):
    src = tmp_path / "INDEX.md"
    src.write_text("- " + "a" * 20 + "    " + "长" * 200 + "\n", encoding="utf-8")
    from scripts.slim_index import main

    assert main(["--path", str(src), "--dry-run"]) == 0
    assert "长" * 100 in src.read_text(encoding="utf-8")
    assert main(["--path", str(src)]) == 0
    assert len(src.read_text(encoding="utf-8")) < 400
