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


def test_inject_new_instruction_mentions_compress_level(tmp_path):
    """任务2：模板注入时应含 compress_level 分级取用说明，且幂等重跑不重复"""
    target = tmp_path / "AGENTS.md"
    target.write_text("", encoding="utf-8")
    inject_instruction(target)
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert "compress_level" in text
    assert "分级取用" in text
    assert text.count("compress_level") == 1  # 幂等：不重复


def test_inject_slim_l0_and_task_tier(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("", encoding="utf-8")
    inject_instruction(target)
    text = target.read_text(encoding="utf-8")
    assert "L0 铁律" in text
    assert "task_tier" in text
    assert "单写者" in text

    # spec 验收口径：L0 必须常驻六条绊律概念（单写者/工作区守护/ledger
    # + query-first/交回用户/回写），一个都不能丢
    for concept in ("单写者", "工作区守护", "ledger", "查中枢", "交回用户", "回写"):
        assert concept in text, f"L0 绊律缺少概念：{concept}"

    # 不再贴旧长模板：断言旧模板的**真实片段**不存在
    # （旧断言写的是一个从未存在过的字符串，永远为真，测不出回归——2026-09-23 修正）
    for legacy in (
        "路由/决策看 5 级",
        "审计/精读看 0 级",
        "上下文紧张时用 higher 省 token",
    ):
        assert legacy not in text, f"旧长模板片段应已移除：{legacy}"

    # 注入面必须保持精简（防回潮）：整段指令给个宽松长度帽
    assert len(text) < 800, f"注入指令过长（{len(text)} 字符），可能又贴回了长模板"
