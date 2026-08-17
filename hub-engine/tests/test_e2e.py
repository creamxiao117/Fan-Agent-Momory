from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from scripts.demo_e2e import run_demo


def test_demo_promotes_rule_and_retrieves(tmp_path):
    root = bootstrap(tmp_path)
    result = run_demo(root)
    # 一条真实规则端到端：沉淀→提炼→确认→复用
    assert (root / "rules" / "dll-version-lock.md").exists()
    assert result["confirmed"] == "dll-version-lock.md"
    assert result["hits"]  # 复用检索能命中该规则
    log = (root / "retro" / "log.md").read_text(encoding="utf-8")
    assert "confirm" in log
    # 查询产物回写：好答案→新经验卡片
    assert (root / "experience" / "query-writeback.md").exists()
