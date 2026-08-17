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


def _cmd_retrieve(args) -> int:
    from tools.retrieve import retrieve
    for c in retrieve(Path(args.root), args.query):
        print(f"[{c.type}/{c.status}] {c.path.name}")
        print(c.body[:200])
    return 0


def _cmd_ingest(args) -> int:
    from sync import ingest
    stat = ingest(Path(args.root), args.platform)
    print(stat)
    return 0 if stat["status"] == "ok" else 1


def _cmd_confirm(args) -> int:
    from sync import confirm_rule
    dst = confirm_rule(Path(args.root), args.name)
    print(f"已确认并提升: {dst}")
    return 0


def _cmd_distill(args) -> int:
    from tools.distill import distill
    written = distill(Path(args.root), args.platform)
    print(f"产出候选 {len(written)} 张: {[p.name for p in written]}")
    return 0


def _cmd_tidy(args) -> int:
    from tools.tidy import archive
    dst = archive(Path(args.root), args.rel, reason=args.reason)
    print(f"已归档: {dst}")
    return 0


def _cmd_lint(args) -> int:
    from tools.lint import lint
    report = lint(Path(args.root))
    print("孤儿页:", report["orphans"])
    print("陈旧页:", report["stale"])
    print("无效卡片:", report["invalid"])
    print("备注:", report["notes"])
    return 0


def _cmd_chat(args) -> int:
    print(chat(args.prompt, Path(args.root)))
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="hub", description="跨 Agent 平台统一记忆中枢")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("retrieve", help="混合检索")
    p.add_argument("--root", required=True)
    p.add_argument("query")
    p.set_defaults(func=_cmd_retrieve)

    p = sub.add_parser("ingest", help="导入暂存区")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", required=True)
    p.set_defaults(func=_cmd_ingest)

    p = sub.add_parser("confirm", help="确认待人工审核的规则")
    p.add_argument("--root", required=True)
    p.add_argument("name")
    p.set_defaults(func=_cmd_confirm)

    p = sub.add_parser("distill", help="复盘→候选规则")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", default="trae")
    p.set_defaults(func=_cmd_distill)

    p = sub.add_parser("tidy", help="归档")
    p.add_argument("--root", required=True)
    p.add_argument("rel")
    p.add_argument("--reason", default="")
    p.set_defaults(func=_cmd_tidy)

    p = sub.add_parser("lint", help="库健康检查")
    p.add_argument("--root", required=True)
    p.set_defaults(func=_cmd_lint)

    p = sub.add_parser("chat", help="omniroute 问答")
    p.add_argument("--root", required=True)
    p.add_argument("prompt")
    p.set_defaults(func=_cmd_chat)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
