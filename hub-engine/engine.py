"""omniroute 增强引擎统一入口：chat（检索/归纳/整理均复用此通道）"""

from pathlib import Path

from common.config import HubConfig, load_engine_config, load_provider_keys
from tools.lint import _all_cards, lint
from tools.retrieve import retrieve


def _gateway_kwargs(hub_root: Path) -> tuple[str, str, str, int]:
    cfg = load_engine_config()
    keys = load_provider_keys(hub_root)
    url = (
        cfg.get("gateway_url", "http://127.0.0.1:11434").rstrip("/")
        + "/v1/chat/completions"
    )
    model = cfg.get("default_model", "qwen2.5:7b")
    api_key = keys.get("default", "")
    timeout = int(cfg.get("timeout", 30))
    return url, model, api_key, timeout


def chat(prompt: str, hub_root: str | Path, fallback: bool = True) -> str:
    """调用 omniroute 网关；网关不可用则回退到文件关键词/full-text 检索"""
    import requests  # 延迟导入：仅 chat 依赖网络库，本地子命令不引入

    hub_root = Path(hub_root)
    try:
        url, model, api_key, timeout = _gateway_kwargs(hub_root)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = requests.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
            },
            headers=headers,
            timeout=timeout,
        )
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
    return (
        "网关不可用，已回退本地检索：\n"
        + "\n".join(parts)
        + "\n---\n"
        + "\n\n".join(bodies)
    )


def _cmd_retrieve(args) -> int:
    for c in retrieve(
        Path(args.root), args.query, top_k=args.top_k, n=args.n, mode=args.mode
    ):
        from tools.snippet import extract_snippet  # 展示层片段节选，延迟导入

        print(f"[{c.type}/{c.status}] {c.path.name}")
        print(extract_snippet(c.body, args.query))
    return 0


def _cmd_build_vectors(args) -> int:
    """增量补写中枢 .sync/vector.db（含 embedding 惰性加载模型，首次联网下载权重）"""
    from tools.semsearch import build

    stats = build(Path(args.root))
    print(stats)
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


def _cmd_status(args) -> int:
    """一键健康快照：卡片分布 / Lint / 待确认 / 最近提交（--json 输出结构化结果）"""
    import subprocess
    from collections import Counter

    root = Path(args.root)
    counts = dict(sorted(Counter(sub for sub, _p, _c in _all_cards(root)).items()))
    report = lint(root)
    pending_dir = root / ".sync" / "pending"
    pending = sorted(pending_dir.glob("*.md")) if pending_dir.is_dir() else []
    try:
        last = (
            subprocess.run(
                ["git", "log", "-1", "--format=%h %ad %s", "--date=short"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            ).stdout.strip()
            or "（无提交）"
        )
    except (subprocess.SubprocessError, OSError):
        last = "（无法读取 git 日志）"

    data = {
        "root": str(root),
        "cards": counts,
        "lint": {
            "orphans": len(report["orphans"]),
            "stale": len(report["stale"]),
            "invalid": report["invalid"],
        },
        "pending": len(pending),
        "pending_first": pending[0].name if pending else None,
        "last_commit": last,
    }
    if getattr(args, "json", False):
        import json

        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        dist = " · ".join(f"{k}={v}" for k, v in counts.items()) or "（空）"
        print(f"中枢: {root}")
        print(f"卡片分布: {dist}")
        print(
            f"Lint: 孤儿 {data['lint']['orphans']} · 陈旧 {data['lint']['stale']} · 无效 {data['lint']['invalid']}"
        )
        print(
            f"待人工确认: {data['pending']}"
            + (f" → {data['pending_first']}" if data["pending_first"] else "")
        )
        print(f"最近提交: {last}")
    return 0 if report["invalid"] == 0 and not report["orphans"] else 1


def _cmd_sync(args) -> int:
    """sync 子命令：平台记忆 ↔ 中枢（默认 Pull；--push 显式切 Push；--dry-run 预览）"""
    from tools.platform_bridge import pull, push

    root = Path(args.root)
    cfg = HubConfig.load(root)
    platforms = list(cfg.platforms) if args.platform == "all" else [args.platform]
    ok = True
    for name in platforms:
        try:
            stat = (
                push(root, name, only_rules=args.only_rules, dry_run=args.dry_run)
                if args.push
                else pull(root, name, dry_run=args.dry_run)
            )
        except KeyError as e:
            print(e)
            ok = False
            continue
        print(f"{name}: {stat}")
        ok = ok and stat["status"] == "ok"
    return 0 if ok else 1


def _cmd_chat(args) -> int:
    print(chat(args.prompt, Path(args.root)))
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="hub", description="跨 Agent 平台统一记忆中枢"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("retrieve", help="混合检索")
    p.add_argument("--root", required=True)
    p.add_argument("query")
    p.add_argument("--top-k", type=int, default=5, help="语义通道召回条数（默认 5）")
    p.add_argument(
        "--n", type=int, default=2, help="字符 n-gram 长度（实测 n=2 最优，默认 2）"
    )
    p.add_argument(
        "--mode",
        choices=("char", "word"),
        default="word",
        help="检索模式：char=字符 n-gram，word=jieba 分词+IDF（默认 word，无 jieba 回退 char）",
    )
    p.set_defaults(func=_cmd_retrieve)

    p = sub.add_parser(
        "build-vectors", help="增量补写第二层语义向量库 .sync/vector.db"
    )
    p.add_argument("--root", required=True)
    p.set_defaults(func=_cmd_build_vectors)

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

    p = sub.add_parser("status", help="一键健康快照")
    p.add_argument("--root", required=True)
    p.add_argument("--json", action="store_true", help="输出结构化 JSON")
    p.set_defaults(func=_cmd_status)

    p = sub.add_parser("sync", help="同步平台记忆（默认 Pull；--push 切 Push）")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", required=True, help="平台名或 all")
    p.add_argument(
        "--push", action="store_true", help="Push 模式：中枢卡片 → 平台文件（默认关闭）"
    )
    p.add_argument(
        "--only-rules", action="store_true", help="Push 时仅同步 rules/ 卡片"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="预览：只打印统计，不落盘、不写锁"
    )
    p.set_defaults(func=_cmd_sync)

    p = sub.add_parser("chat", help="omniroute 问答")
    p.add_argument("--root", required=True)
    p.add_argument("prompt")
    p.set_defaults(func=_cmd_chat)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
