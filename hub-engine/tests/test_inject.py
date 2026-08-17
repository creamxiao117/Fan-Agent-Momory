from pathlib import Path

from tools.inject import inject_instruction


def test_inject_writes_block(tmp_path):
    target = tmp_path / "user_profile.md"
    target.write_text("# 用户档案\n", encoding="utf-8")
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert "INDEX.md" in text
    assert "不得臆测" in text


def test_inject_idempotent(tmp_path):
    target = tmp_path / "user_profile.md"
    target.write_text("", encoding="utf-8")
    inject_instruction(target)
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert text.count("## 统一记忆中枢") == 1
