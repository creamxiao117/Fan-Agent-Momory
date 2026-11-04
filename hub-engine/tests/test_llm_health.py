"""LLMHealthChecker：多端点链相关行为（端点判定 + 单例分键 + 探针地址纪律）"""

from tools.llm_health import LLMHealthChecker, ensure_llm_service


def test_probe_uses_ipv4_literal_not_localhost():
    """探针**必须**用 `127.0.0.1`，不得用 `localhost`（2026-11-04 实测）。

    LM Studio 只监听 IPv4；`localhost` 先解析 `::1` ⇒ urllib 先连 `::1` ⇒
    白等 ~2 s SYN 超时 ⇒ **把探针开销记成「服务慢」**（实测 2.07 s vs 0.015 s）⇒
    一条假延迟告警长期占着告警位。
    """
    LLMHealthChecker.reset_instance()
    assert LLMHealthChecker().base_url == "http://127.0.0.1:1234"
    assert LLMHealthChecker.get_instance().base_url == "http://127.0.0.1:1234"
    assert "localhost" not in LLMHealthChecker().base_url


def test_ensure_llm_service_default_is_ipv4_literal():
    """自愈入口的默认端点同样不得是 `localhost`（否则自愈探测也要白等 2 s）。"""
    import inspect

    default = inspect.signature(ensure_llm_service).parameters["base_url"].default
    assert default == "http://127.0.0.1:1234"
    assert "localhost" not in default


def test_get_instance_keyed_by_base_url():
    """不同 base_url 必须拿到不同检查器（否则多端点链健康判定串味）"""
    LLMHealthChecker.reset_instance()
    lm = LLMHealthChecker.get_instance("http://127.0.0.1:1234")
    sgl = LLMHealthChecker.get_instance("http://127.0.0.1:30000")
    assert lm is not sgl
    assert lm.base_url == "http://127.0.0.1:1234"
    assert sgl.base_url == "http://127.0.0.1:30000"
    # 同 base_url 仍复用同一实例
    assert LLMHealthChecker.get_instance("http://127.0.0.1:1234/") is lm


def test_probe_paths_openai_vs_ollama():
    """OpenAI 兼容端点探 /v1/models（+ /health）；仅 Ollama 端口走 /api/tags"""
    LLMHealthChecker.reset_instance()
    sgl = LLMHealthChecker.get_instance("http://127.0.0.1:30000")
    assert sgl._probe_paths() == ["/v1/models", "/health"]
    assert sgl._is_openai_style() is True

    ollama = LLMHealthChecker.get_instance("http://127.0.0.1:11434")
    assert ollama._probe_paths() == ["/api/tags"]
    assert ollama._is_openai_style() is False
