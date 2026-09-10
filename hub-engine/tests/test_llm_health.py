"""LLMHealthChecker：多端点链相关行为（端点判定 + 单例分键）"""

from tools.llm_health import LLMHealthChecker


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
