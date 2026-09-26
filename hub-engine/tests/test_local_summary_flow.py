# @version V1.0 / 2026-09-25 / COV：本地摘要端到端 + 巡检报告打印
"""两个「高密度但未被跑过」的入口：

1. `local_summary.main()` —— 夜间摘要的完整流程（日志截段 → 候选端点 → 写盘），
   用桩替掉真实端点调用，断言**落盘内容**与退出码语义。
2. `patrol_runner.print_report()` —— 巡检报告渲染（每个状态图标、告警、健康分条、
   自动修复层、建议），这是巡检唯一的"人看"出口，之前 0 覆盖。
"""

from __future__ import annotations

from pathlib import Path

from scripts import local_summary as ls
from scripts import patrol_runner as patrol

# ---------------------------------------------------------------------------
# local_summary：纯函数
# ---------------------------------------------------------------------------


def test_latest_log_segment_prefers_last_marker(tmp_path):
    log = tmp_path / "nightly.log"
    log.write_text(
        "==== night-consolidate start ====\n旧的一轮\n==== night-consolidate start ====\n新的一轮\n",
        encoding="utf-8",
    )
    seg = ls._latest_log_segment(log)
    assert "新的一轮" in seg and "旧的一轮" not in seg


def test_latest_log_segment_missing_file(tmp_path):
    assert ls._latest_log_segment(tmp_path / "nope.log") == ""


def test_pick_local_model_falls_back_when_endpoint_down(monkeypatch):
    """端点不可达 → 用配置里的模型名，不炸。"""
    import requests

    def _boom(*a, **k):
        raise requests.RequestException("down")

    monkeypatch.setattr(requests, "get", _boom)
    assert ls._pick_local_model("http://127.0.0.1:1234/v1/chat/completions", "qwen-x") == "qwen-x"


def test_pick_local_model_skips_embedding_models(monkeypatch):
    import requests

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"id": "text-embedding-bge-m3"},
                    {"id": "qwen3.8-27b-fast"},
                    {"id": "rerank-x"},
                ]
            }

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
    picked = ls._pick_local_model("http://127.0.0.1:1234/v1/chat/completions", "不存在的模型")
    assert picked == "qwen3.8-27b-fast", "必须排除 embed/rerank 类模型"


def test_upsert_daily_is_idempotent_per_date(tmp_path):
    out = tmp_path / "daily_summary.md"
    ls._upsert_daily(out, "2026-09-25", "第一次")
    ls._upsert_daily(out, "2026-09-25", "第二次（覆盖）")
    text = out.read_text(encoding="utf-8")
    assert text.count("## 2026-09-25 夜间汇总") == 1, "同日小节不得重复"
    assert "第二次" in text and "第一次" not in text


# ---------------------------------------------------------------------------
# local_summary：main() 端到端
# ---------------------------------------------------------------------------


def _hub_with_nightly_log(tmp_path: Path) -> Path:
    hub = tmp_path / "AgentMemoryHub"
    sync = hub / ".sync"
    sync.mkdir(parents=True)
    (sync / "nightly.log").write_text(
        "==== night-consolidate start ====\n"
        "[周四] -- 2/4 build-vectors --\n{'inserted': 3}\n"
        "[周四] -- 3/4 sleep-consolidate --\n[sleep] P0 0 / P1 0 候选\n",
        encoding="utf-8",
    )
    (hub / "system").mkdir(parents=True, exist_ok=True)
    (hub / "system" / "config.yaml").write_text(
        "batch_model: ''\nlocal_chat:\n  model: qwen3.8-27b-fast\n  url: http://127.0.0.1:1234/v1/chat/completions\n",
        encoding="utf-8",
    )
    (hub / "provider_keys.yaml").write_text("default: k\n", encoding="utf-8")
    return hub


def test_main_writes_summary_when_endpoint_answers(tmp_path, monkeypatch):
    hub = _hub_with_nightly_log(tmp_path)
    monkeypatch.setattr(ls, "_chat", lambda *a, **k: "- 要点一\n- 要点二")

    rc = ls.main(["--root", str(hub)])

    assert rc == 0
    out = hub / ".sync" / "daily_summary.md"
    assert out.is_file() and "要点一" in out.read_text(encoding="utf-8")


def test_main_returns_2_when_all_endpoints_fail(tmp_path, monkeypatch):
    """候选端点全失败 → 不写盘、退出码 2（夜间任务据此记录 best-effort 失败）。"""
    hub = _hub_with_nightly_log(tmp_path)
    monkeypatch.setattr(ls, "_chat", lambda *a, **k: "")

    assert ls.main(["--root", str(hub)]) == 2
    assert not (hub / ".sync" / "daily_summary.md").exists()


def test_main_skips_when_log_too_short(tmp_path, monkeypatch):
    hub = _hub_with_nightly_log(tmp_path)
    (hub / ".sync" / "nightly.log").write_text("太短", encoding="utf-8")
    monkeypatch.setattr(ls, "_chat", lambda *a, **k: "不该被调用")
    assert ls.main(["--root", str(hub)]) == 0


# ---------------------------------------------------------------------------
# patrol_runner.print_report
# ---------------------------------------------------------------------------


def _report() -> patrol.PatrolReport:
    rep = patrol.PatrolReport(hub_root="C:/hub", generated_at="2026-09-25T08:00:00+08:00")
    stage_ok = patrol.StageResult(name="基础设施检查")
    stage_ok.steps.append(patrol.StepResult(name="llm_check", stage="基础设施", status="pass", output="ok"))
    stage_warn = patrol.StageResult(name="质量门禁")
    stage_warn.steps.append(patrol.StepResult(name="ruff", stage="质量门禁", status="warn", exit_code=1, output="告警"))
    stage_fail = patrol.StageResult(name="数据质量")
    stage_fail.steps.append(
        patrol.StepResult(name="vector_regression", stage="数据质量", status="fail", exit_code=2, output="挂了")
    )
    stage_skip = patrol.StageResult(name="飞轮活跃度", skipped=True)
    stage_skip.steps.append(patrol.StepResult(name="flywheel", stage="飞轮活跃度", status="skip", output="跳过"))
    rep.stages = [stage_ok, stage_warn, stage_fail, stage_skip]
    rep.alerts = [
        {"level": "critical", "rule": "local_llm_unavailable", "message": "本地 LLM 不可用"},
        {"level": "info", "rule": "low_hit_rate", "message": "命中率低"},
    ]
    rep.auto_fix_results = {"auto_fix_lint": {"status": "pass", "output": "无需修复"}}
    rep.snapshot = {
        "health_scores": {
            "overall": 92.0,
            "card_health": 100.0,
            "skill_health": 95.0,
            "flywheel_activity": 100.0,
            "llm_health": 60.0,
        }
    }
    rep.suggestions = ["🟢 建议一", "🟢 建议二"]
    rep.overall_exit_code = 3
    return rep


def test_print_report_renders_every_status_and_section(capsys):
    patrol.print_report(_report())
    out = capsys.readouterr().out
    for token in ("中枢每日健康巡检报告", "基础设施检查", "质量门禁", "数据质量", "飞轮活跃度"):
        assert token in out
    assert "✅" in out and "⚠️" in out and "❌" in out and "⏭️" in out
    assert "告警汇总" in out
    assert "健康度评分" in out
    assert "自动修复层结果" in out
    assert "建议一" in out


def test_print_report_survives_minimal_report(capsys):
    """空报告（首日/幂等跳过）不得崩。"""
    patrol.print_report(patrol.PatrolReport(hub_root="C:/hub", generated_at="x"))
    assert "中枢每日健康巡检报告" in capsys.readouterr().out
