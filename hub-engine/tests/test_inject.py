from tools.inject import hub_location, inject_instruction


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


def test_inject_refreshes_stale_hub_location(tmp_path):
    target = tmp_path / "user_profile.md"
    stale = (
        "## 统一记忆中枢（AGENT MEMORY HUB）\n"
        "执行前先查统一记忆中枢：读取 INDEX.md 与 rules / experience，命中再执行；\n"
        "不确定的内容交回用户，不得臆测、不得凭空捏造历史经验。\n"
        "中枢位置：D:\\AIwork\\AgentMemoryHub\n"
    )
    target.write_text(stale, encoding="utf-8")
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert text.count("## 统一记忆中枢") == 1
    assert "D:\\AIwork\\AgentMemoryHub" not in text
    assert "中枢位置：" + hub_location() in text


def test_inject_new_instruction_mentions_bootstrap(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("", encoding="utf-8")
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert "hub_bootstrap" in text
    assert "hub_ingest_candidate" in text
    assert "引用+摘要" in text
