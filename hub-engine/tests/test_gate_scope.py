# @version V1.0 / 2026-10-02 / pi / 提交门禁作用域判定单测（M0.5/Task 6）
"""`gate_scope` / `gate_runner` 单测——**先证红再改**的落点。

回归背景（本任务要根治的缺陷）：
    旧门禁的渲染检查**无条件跑** ⇒ 工作树里**任何人**未提交的卡改动会阻断**任何**提交。
    代价不是"慢"，而是所有人学会 `git commit --no-verify` ⇒ 全部门禁一起失效。
故这里的核心用例是：**只提交 .py 时，l0 门禁不得触发**。
"""

from pathlib import Path

from common.gate_scope import GATES, classify, gates_to_run
from scripts.gate_runner import main as runner_main

# ── classify：作用域判定 ───────────────────────────────────────


def test_py_only_triggers_code_gate_only():
    """核心属性：改纯代码不该跑 L0 面（预算/渲染）。"""
    flags = classify(["hub-engine/tools/retrieve.py"])
    assert flags == {"code": True, "text": True, "l0": False}
    assert gates_to_run(["hub-engine/tools/retrieve.py"]) == ["code", "text"]


def test_md_only_triggers_text_gate():
    flags = classify(["docs/compose/plans/x.md"])
    assert flags["text"] and not flags["code"] and not flags["l0"]


def test_l0_files_trigger_l0_gate():
    for p in (
        "AGENTS.md",
        "CHARTER.md",
        "WORK.md",
        "AgentMemoryHub/INDEX.md",
        "hub-engine/scripts/render_index.py",
        "hub-engine/tools/task_tier.py",
        "hub-engine/common/index_limits.py",
    ):
        assert classify([p])["l0"], f"{p} 应触发 l0 门禁"


def test_authority_cards_trigger_l0_gate_both_repo_shapes():
    """外层仓写 `AgentMemoryHub/rules/x.md`，中枢仓写 `rules/x.md`——两种形态都要认。"""
    assert classify(["AgentMemoryHub/rules/global-rules.md"])["l0"]
    assert classify(["rules/global-rules.md"])["l0"]
    assert classify(["experience/foo.md"])["l0"]
    # 非权威区（retro/notes）不是 L0 面
    assert not classify(["retro/lint-report-2026-01-01.md"])["l0"]


def test_pre_commit_hook_itself_is_text():
    assert classify(["hub-engine/scripts/pre-commit"])["text"]


def test_empty_staged_runs_no_gate():
    assert gates_to_run([]) == []
    assert classify([]) == {"code": False, "text": False, "l0": False}


def test_gate_order_is_stable():
    """日志顺序必须稳定（否则同一提交的两次输出不可比）。"""
    flags = gates_to_run(["AGENTS.md", "a.py", "b.md"])
    assert flags == [g for g in GATES if g in flags] == ["code", "text", "l0"]


def test_l0_face_is_precisely_the_gate_inputs():
    """L0 面定义要**精确**：多一个只是白跑，少一个就是门禁失效。

    本门禁的两项检查 = `startup_budget`（输入：L0 文档 + INDEX + L1 卡）与
    `render_index --check`（输入：权威区卡 + 渲染器及其派生模块）。
    """
    # 必须收：两项检查的输入
    for p in (
        "hub-engine/scripts/startup_budget.py",
        "hub-engine/scripts/render_index.py",
        "hub-engine/tools/hub_registry.py",
        "hub-engine/tools/task_tier.py",
    ):
        assert classify([p])["l0"], f"{p} 是 l0 门禁的输入，必须覆盖"
    # 刻意不收：改它会影响各平台注入文本，但**不在**这两项检查的输入面内
    assert not classify(["hub-engine/tools/inject.py"])["l0"]


# ── gate_runner：执行器 ────────────────────────────────────────


def test_dry_run_reports_gates_without_running(tmp_path):
    """`--dry-run` 只报触发范围，不真跑（供测试与排障）。"""
    rc = runner_main(["--repo", "outer", "--staged", "hub-engine/tools/retrieve.py", "--dry-run"])
    assert rc == 0


def test_dry_run_with_empty_staged(tmp_path):
    assert runner_main(["--repo", "outer", "--staged", "--dry-run"]) == 0


def test_gate_functions_skip_when_nothing_relevant(tmp_path):
    """无相关文件时各门禁应"通过且说明原因"，而不是报错。"""
    from scripts.gate_runner import gate_code, gate_text

    ok, detail = gate_code(["README.md"], tmp_path, "outer")
    assert ok and ".py" in detail
    ok2, detail2 = gate_text([], tmp_path, "outer")
    assert ok2


def test_runner_uses_venv_python_when_present():
    """解释器必须优先 `.venv`（系统 python 缺 jieba ⇒ 检索类检查会静默跳过＝假绿）。"""
    from scripts.gate_runner import _python

    py = _python()
    assert ".venv" in py or Path(py).name.startswith("python"), py
    if (Path(__file__).resolve().parents[2] / ".venv" / "Scripts" / "python.exe").is_file():
        assert ".venv" in py
