from pathlib import Path

from common.config import load_engine_config, load_provider_keys


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_load_engine_config_returns_gateway(tmp_path):
    _write(
        tmp_path,
        "engine.config.yaml",
        "gateway_url: http://127.0.0.1:11434\ndefault_model: qwen2.5:7b\ntimeout: 30\n",
    )
    cfg = load_engine_config(tmp_path / "engine.config.yaml")
    assert cfg["gateway_url"] == "http://127.0.0.1:11434"
    assert cfg["default_model"] == "qwen2.5:7b"
    assert cfg["timeout"] == 30


def test_load_provider_keys_reads_hub_root(tmp_path):
    _write(tmp_path, "provider_keys.yaml", "default: sk-fake-123\n")
    keys = load_provider_keys(tmp_path)
    assert keys["default"] == "sk-fake-123"


def test_load_engine_config_default_path_exists():
    # 默认路径指向仓库内 config/engine.config.yaml，必须存在
    p = Path(__file__).resolve().parents[1] / "config" / "engine.config.yaml"
    assert p.exists()
