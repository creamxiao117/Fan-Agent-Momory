import pytest
from engine import chat, main


def test_chat_calls_gateway_and_returns_content(monkeypatch, tmp_path):
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "已命中 DLL 规则"}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["model"] = json["model"]
        return FakeResp()

    monkeypatch.setattr("requests.post", fake_post)
    out = chat("DLL 被锁怎么办", tmp_path)
    assert "DLL" in out
    assert captured["url"].endswith("/v1/chat/completions")


def test_chat_falls_back_on_gateway_error(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("requests.post", boom)
    out = chat("随便问一句", tmp_path)
    assert isinstance(out, str) and out  # 不抛异常，返回兜底文本


def test_chat_raises_when_fallback_disabled(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("gateway down")

    monkeypatch.setattr("requests.post", boom)
    with pytest.raises(RuntimeError):
        chat("x", tmp_path, fallback=False)


def test_status_prints_snapshot(tmp_path, capsys):
    from scripts.bootstrap_hub import bootstrap

    root = bootstrap(tmp_path)
    code = main(["status", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "卡片分布" in out
    assert "Lint:" in out
    assert "待人工确认" in out


def test_status_json_output(tmp_path, capsys):
    import json

    from scripts.bootstrap_hub import bootstrap

    root = bootstrap(tmp_path)
    code = main(["status", "--root", str(root), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert set(data) >= {"root", "cards", "lint", "pending", "last_commit"}
    assert data["lint"]["invalid"] == 0
