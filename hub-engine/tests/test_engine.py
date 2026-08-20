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
    # freshness 软汇报块（OpenViking 路径 A）：未 build 时如实暴露待重建
    assert "fresh" in data
    assert "stale_total" in data["fresh"]


def test_build_vectors_returns_zero_when_model_ok(tmp_path, capsys):
    from scripts.bootstrap_hub import bootstrap
    from tools.semsearch import set_embed_backend

    root = bootstrap(tmp_path)
    # 注入确定性假后端产出非零向量，验证正常路径返回 0（不真实加载模型/联网）
    set_embed_backend(lambda text: [1.0, 0.0])
    try:
        code = main(["build-vectors", "--root", str(root)])
        assert code == 0
        assert "【告警】" not in capsys.readouterr().out
    finally:
        set_embed_backend(None)


def test_build_vectors_warns_and_nonzero_when_no_vectors(tmp_path, capsys, monkeypatch):
    """向量通道退化（embed 后端不可用 → 零向量）时应返回非零触发巡检告警。"""
    from scripts.bootstrap_hub import bootstrap
    from tools.semsearch import set_embed_backend

    root = bootstrap(tmp_path)
    # 建一张有效卡，确保 build 有卡片可处理（否则 touched=0 不触发告警）
    exp = root / "experience"
    exp.mkdir(parents=True, exist_ok=True)
    (exp / "sample.md").write_text(
        "---\n"
        "type: exp\n"
        "tags:\n- demo\n"
        "updated: '2026-08-19'\n"
        "status: active\n"
        "reuse_count: 0\n"
        "---\n\n"
        "示例经验卡。\n",
        encoding="utf-8",
    )
    # 注入不可用后端：任何文本都返回 None，build 会全部空向量
    set_embed_backend(lambda text: None)
    try:
        code = main(["build-vectors", "--root", str(root)])
        out = capsys.readouterr().out
        assert code == 2  # 专用退出码：向量未产出
        assert "【告警】向量通道退化" in out
    finally:
        set_embed_backend(None)  # 复位默认后端


def test_lint_nonzero_when_unhealthy(tmp_path, capsys, monkeypatch):
    """lint 发现孤儿/陈旧/无效卡之一时返回非零，供巡检告警闭环捕获。"""
    from scripts.bootstrap_hub import bootstrap

    root = bootstrap(tmp_path)
    # 注入一枚无效卡（缺 frontmatter）触发 invalid 告警
    bad = root / "experience" / "broken.md"
    bad.write_text("# 无 frontmatter 的坏卡\n", encoding="utf-8")
    code = main(["lint", "--root", str(root)])
    out = capsys.readouterr().out
    assert code == 2
    assert "【告警】" in out
