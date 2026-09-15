"""方案B + OmniRoute 移出兜底 的行为契约测试（2026-09-15 用户裁定）。

守住两条决定：
  ① 门禁不再依赖 confidence（缺字段不得被判为不通过而丢弃本地结果）
  ② 兜底链里没有远程网关（未配置 gateway_url ⇒ 一次 HTTP 都不发）
"""

from pathlib import Path

import engine
from common.config import load_engine_config

CFG = """
timeout: 30
local_chat:
  url: http://127.0.0.1:1234/v1/chat/completions
  model: fake-local
  max_tokens: 512
escalation:
  min_score: 0.8
  min_confidence: 0
  intermediate_model: ""
  local_model: ""
  enabled: true
"""

DEDUP_PROMPT = "你是记忆库去重决策器。判断一张新记忆卡是否与下列候选卡重复。"
JSON_NO_CONF = '{"action":"merge","target":"a.md","reason":"同主题互补"}'
JSON_OK = '{"action":"merge","target":"a.md","reason":"两者同主题互补，可并入旧卡","confidence":0.9}'


class _Health:
    def __init__(self, ok: bool) -> None:
        self._ok = ok

    def is_available(self) -> bool:
        return self._ok


def _setup(monkeypatch, tmp_path, replies: list[str], healthy: bool = True):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(CFG, encoding="utf-8")
    monkeypatch.setenv("HUB_CONFIG_PATH", str(cfg))

    calls: list[str | None] = []

    def fake_local_chat(prompt, root, model=None):
        calls.append(model)
        return replies[min(len(calls) - 1, len(replies) - 1)]

    monkeypatch.setattr(engine, "_local_chat", fake_local_chat)
    monkeypatch.setattr(
        engine,
        "LLMHealthChecker",
        type(
            "H",
            (),
            {"get_instance": staticmethod(lambda *a, **k: _Health(healthy))},
        ),
    )

    def no_remote(*a, **k):
        raise AssertionError("不得调用远程 chat()（OmniRoute 已移出兜底）")

    monkeypatch.setattr(engine, "chat", no_remote)
    return calls


def test_shipped_config_has_no_remote_gateway_and_zero_min_confidence(monkeypatch):
    """配置回归防护：仓库真实配置必须『无 gateway_url』且『min_confidence = 0』。"""
    monkeypatch.delenv("HUB_CONFIG_PATH", raising=False)
    cfg = load_engine_config()
    assert not cfg.get("gateway_url"), "OmniRoute 已从兜底移除，不应再配 gateway_url"
    esc = cfg.get("escalation") or {}
    assert float(esc.get("min_confidence", 1)) == 0, "门禁不应再依赖 confidence"
    assert not str(esc.get("intermediate_model", "") or "").strip(), "升级环应留空"
    assert not str(esc.get("local_model", "") or "").strip(), "升级环应留空"


def test_missing_confidence_result_is_not_discarded(monkeypatch, tmp_path):
    """缺 confidence 字段时，本地结果不得被丢弃（原缺陷：0.0 < 0.80 → 空转升级+死网关）。"""
    _setup(monkeypatch, tmp_path, [JSON_NO_CONF])
    out = engine.smart_chat(DEDUP_PROMPT, tmp_path)
    assert out == JSON_NO_CONF  # 采用本地结果，未外送、未丢弃


def test_empty_upgrade_models_are_skipped_no_wasted_retries(monkeypatch, tmp_path):
    """升级环留空 ⇒ 不得再空转重试不存在的模型（原默认值是 Ollama 冒号 tag）。"""
    calls = _setup(monkeypatch, tmp_path, [JSON_NO_CONF])
    engine.smart_chat(DEDUP_PROMPT, tmp_path)
    assert len(calls) == 1, f"应只调用一次本地模型，实际 {len(calls)} 次：{calls}"


def test_low_quality_result_still_not_discarded(monkeypatch, tmp_path):
    """质量分不达标 + 无可用升级环 ⇒ 仍返回本地结果（绝不外送远程）。"""
    calls = _setup(monkeypatch, tmp_path, ["这不是 JSON"])
    out = engine.smart_chat(DEDUP_PROMPT, tmp_path)
    assert out == "这不是 JSON"
    assert len(calls) == 1


def test_local_llm_down_degrades_locally_without_remote(monkeypatch, tmp_path):
    """本地端点不可用 ⇒ 本地巡检兜底，不碰远程。"""
    _setup(monkeypatch, tmp_path, [JSON_OK], healthy=False)
    out = engine.smart_chat(DEDUP_PROMPT, tmp_path)
    assert isinstance(out, str) and out
    assert "本地兜底" in out or "本地检索" in out


def test_gateway_kwargs_returns_none_without_config(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("timeout: 30\n", encoding="utf-8")
    monkeypatch.setenv("HUB_CONFIG_PATH", str(cfg))
    assert engine._gateway_kwargs(Path(tmp_path)) is None


def test_gateway_kwargs_present_when_configured(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "gateway:\n  url: http://127.0.0.1:9999\n  default_model: auto/offline\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HUB_CONFIG_PATH", str(cfg))
    kwargs = engine._gateway_kwargs(Path(tmp_path))
    assert kwargs is not None
    assert kwargs[0] == "http://127.0.0.1:9999/v1/chat/completions"
