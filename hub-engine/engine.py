"""omniroute 增强引擎统一入口：chat（检索/归纳/整理均复用此通道）"""
from pathlib import Path

import requests

from common.config import load_engine_config, load_provider_keys
from tools.retrieve import retrieve


def _gateway_kwargs(hub_root: Path) -> tuple[str, str, str, int]:
    cfg = load_engine_config()
    keys = load_provider_keys(hub_root)
    url = cfg.get("gateway_url", "http://127.0.0.1:11434").rstrip("/") + "/v1/chat/completions"
    model = cfg.get("default_model", "qwen2.5:7b")
    api_key = keys.get("default", "")
    timeout = int(cfg.get("timeout", 30))
    return url, model, api_key, timeout


def chat(prompt: str, hub_root: str | Path, fallback: bool = True) -> str:
    """调用 omniroute 网关；网关不可用则回退到文件关键词/full-text 检索"""
    hub_root = Path(hub_root)
    try:
        url, model, api_key, timeout = _gateway_kwargs(hub_root)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = requests.post(url, json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        if not fallback:
            raise
        # 网关不可用，走本地兜底（retrieve 独立于 try 之外，避免异常掩盖）
    cards = retrieve(hub_root, prompt)
    if not cards:
        return "（网关不可用且中枢无命中，建议交回用户确认）"
    parts = [f"[{c.type}/{c.status}] {c.path.name}" for c in cards[:3]]
    bodies = [c.body.strip() for c in cards[:3]]
    return "网关不可用，已回退本地检索：\n" + "\n".join(parts) + "\n---\n" + "\n\n".join(bodies)
