"""omniroute 增强引擎统一入口：chat（检索/归纳/整理均复用此通道）

V1.1 (2026-09-07): P1 拆分 — 10 个 _cmd_* 子命令搬到 commands/ 子包，
本文件仅保留 chat + main() 路由表。子命令处理函数从 commands 包导入。
"""

import json  # noqa: F401  (chat helpers 复用)
import sys
from datetime import datetime, timedelta, timezone  # noqa: F401  (chat helpers 复用)
from pathlib import Path

# 让 engine.py 能 import commands/ 子包（同级目录）
sys.path.insert(0, str(Path(__file__).resolve().parent))

# === P1 拆分：从 commands 子包导入各子命令处理函数 ===
from commands import (  # noqa: I001  (must precede common.config — needs sys.path insert)
    cmd_build_vectors,
    cmd_confirm,
    cmd_distill,
    cmd_gate,
    cmd_ingest,
    cmd_lint,
    cmd_retrieve,
    cmd_status,
    cmd_sync,
    cmd_tidy,
)

# === P1 兼容 shim：保留旧 helper 名供测试 monkeypatch.setattr("engine._<name>", ...) ===

from commands.status import (
    collect_llm_status as _collect_llm_status,  # noqa: F401,
    collect_snapshot_alerts as _collect_snapshot_alerts,  # noqa: F401,
    collect_today_metrics as _collect_today_metrics,  # noqa: F401,
    compare_snapshots as _compare_snapshots,  # noqa: F401,
    compute_snapshot_health_scores as _compute_snapshot_health_scores,  # noqa: F401,
    estimate_hub_tool_capacity as _estimate_hub_tool_capacity,  # noqa: F401,
    load_previous_snapshot as _load_previous_snapshot,  # noqa: F401,
    print_snapshot_report as _print_snapshot_report,  # noqa: F401,
)








from common.config import (  # noqa: F401  (HubConfig 供 future shim 用)
    HubConfig,
    load_engine_config,
    load_provider_keys,
)
from tools.lint import _all_cards, lint  # noqa: F401  (供 monkeypatch 兼容)
from tools.llm_health import LLMHealthChecker
from tools.resilience import ResiliencePipelineBuilder
from tools.retrieve import retrieve


def _gateway_kwargs(
    hub_root: Path, model: str | None = None
) -> tuple[str, str, str, int, str, int | None]:
    """返回 (url, model, api_key, timeout, compress)。
    model 传入则覆盖 default_model（如批次任务抽样本地 MiniCPM 兜底处理模型）。"""
    cfg = load_engine_config()
    keys = load_provider_keys(hub_root)
    url = (
        cfg.get("gateway_url", "http://127.0.0.1:20128").rstrip("/")
        + "/v1/chat/completions"
    )
    model = model or cfg.get(
        "default_model", "auto/offline"
    )
    api_key = keys.get("default", "")
    timeout = int(cfg.get("timeout", 30))
    compress = str(cfg.get("compress", "") or "").strip()
    max_tokens = cfg.get("max_tokens")
    return url, model, api_key, timeout, compress, max_tokens


def _build_http_pipeline(
    timeout: float,
    max_attempts: int = 3,
    base_delay: float = 0.5,
) -> ResiliencePipelineBuilder:
    """构建 HTTP 调用弹性管道：Timeout(外) + Retry(内)。"""
    # 正确顺序：Timeout 在外层，Retry 在内层
    return (
        ResiliencePipelineBuilder()
        .add_timeout(timeout=timeout)
        .add_retry(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=min(base_delay * (2 ** (max_attempts - 1)), 30.0),
            jitter=0.3,
            on_retry=lambda evt: print(
                f"[resilience] retry #{evt.attempt}: {evt.detail}"
            ),
        )
    )


def chat(
    prompt: str,
    hub_root: str | Path,
    fallback: bool = True,
    *,
    model: str | None = None,
) -> str:
    """调用 omniroute 网关；网关不可用则回退到文件关键词/full-text 检索。
    接入弹性管道：Retry(3次) + Timeout + Fallback(降级到本地检索)。"""
    import requests

    hub_root = Path(hub_root)
    url, model, api_key, timeout, compress, max_tokens = _gateway_kwargs(
        hub_root, model
    )
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    if compress:
        headers["X-OmniRoute-Compression"] = f"{compress};source=request"
    # 原条件 model.startswith("ollama/") 已随 Ollama 退役恒 False（2026-09-02 残名清理）；
    # 等价简化：仅当顶层配置显式给出 max_tokens 才透传（当前未配置 → 行为不变）。
    extra = {"max_tokens": int(max_tokens)} if max_tokens else {}

    def _do_http() -> str:
        resp = requests.post(
            url,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                **extra,
            },
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    if not fallback:
        return _build_http_pipeline(timeout=timeout).build().execute(_do_http)

    # 弹性管道：Fallback(外) + Timeout + Retry(内)
    # 正确顺序：Fallback 在外层作为最后降级，Retry 在内层重试实际调用
    pipeline = (
        ResiliencePipelineBuilder()
        .add_fallback(
            fallback_fn=lambda: _do_fallback(prompt, hub_root),
            on_fallback=lambda evt: print(
                f"[resilience/chat] fallback: {evt.detail}"
            ),
        )
        .add_timeout(timeout=timeout)
        .add_retry(
            max_attempts=3,
            base_delay=0.5,
            max_delay=30.0,
            jitter=0.3,
            on_retry=lambda evt: print(
                f"[resilience/chat] retry #{evt.attempt}: {evt.detail}"
            ),
        )
        .build()
    )
    return pipeline.execute(_do_http)


def _do_fallback(prompt: str, hub_root: Path) -> str:
    """降级逻辑：网关不可用时回退到文件检索 + 本地兜底。"""
    cards = retrieve(hub_root, prompt)
    if not cards:
        return "（网关不可用且中枢无命中，建议交回用户确认）"
    parts = [f"[{c.type}/{c.status}] {c.path.name}" for c in cards[:3]]
    bodies = [c.body.strip() for c in cards[:3]]
    try:
        local = _local_fallback_chat(hub_root, prompt, parts, bodies)
    except Exception:
        local = ""
    if local:
        return "（外部 AI 源不可用，已用本地模型兜底应答，仅供参考，建议人工复核）\n\n" + local
    return (
        "网关不可用，已回退本地检索：\n"
        + "\n".join(parts)
        + "\n---\n"
        + "\n\n".join(bodies)
    )


def _local_fallback_chat(
    hub_root: Path, prompt: str, parts: list[str], bodies: list[str]
) -> str:
    """直连本地 LLM (LM Studio) 生成骨架回答（不经 OmniRoute，外部源全挂仍可用）。
    接入 LLM 健康检测 + 弹性管道：本地 LLM 不可用时返回空字符串，由上层处理。"""
    from common.config import load_engine_config

    cfg = (load_engine_config() or {}).get("fallback_chat") or {}
    url = str(cfg.get("url", "") or "").strip()
    model = str(cfg.get("model", "") or "").strip()
    api_key = str(cfg.get("api_key", "") or "").strip()
    if not url or not model:
        return ""
    import requests

    # LLM 健康检测（本地端点，现役 LM Studio）
    llm_base = url.rsplit("/v1/", 1)[0] if "/v1/" in url else url.rsplit("/", 1)[0]
    health_checker = LLMHealthChecker.get_instance(llm_base)

    if not health_checker.is_available():
        print("[llm_health] fallback_chat 本地 LLM 不可用，跳过本地兜底")
        return ""

    ref = "\n".join(f"- {p}:\n{b[:400]}" for p, b in zip(parts, bodies))
    body = (
        "你是记忆中枢离线兜底助手。外部 AI 源暂时不可用，下面是从中枢检索到的参考卡片。"
        "请基于这些卡片，用中文尽量给出一份可用的骨架回答；若参考不足以回答，明确说明缺什么。\n"
        f"问题：{prompt}\n参考卡片：\n{ref}"
    )
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": body}],
        "stream": False,
    }
    mt = cfg.get("max_tokens")
    if mt:
        payload["max_tokens"] = int(mt)

    def _do_fallback_http() -> str:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    # 使用弹性管道：Timeout(外) + Retry(内)
    pipeline = ResiliencePipelineBuilder()
    pipeline.add_timeout(timeout=60)
    pipeline.add_retry(
        max_attempts=2, base_delay=1.0, jitter=0.2,
        on_retry=lambda evt: print(f"[resilience/local_fallback] retry #{evt.attempt}: {evt.detail}"),
    )
    try:
        return pipeline.build().execute(_do_fallback_http)
    except Exception as e:
        print(f"[resilience/local_fallback] 本地 LLM 兜底失败: {e}")
        return ""


def _local_chat(prompt: str, hub_root: Path, model: str | None = None) -> str:
    """直连本地 LLM 的统一入口 (LM Studio)，供本地默认逻辑任务使用。
    接入 LLM 健康检测 + 弹性管道：本地 LLM 不可用时自动降级到网关。"""
    import requests

    cfg = load_engine_config()
    local_cfg = cfg.get("local_chat") or {}
    # 本地默认逻辑入口：模型绑定
    url = str(local_cfg.get("url", "http://127.0.0.1:1234/v1/chat/completions"))
    model_name = model or str(
        local_cfg.get("model", cfg.get("default_model", "qwen/qwen3.5-9b"))
    )
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": False,
        "max_tokens": int(local_cfg.get("max_tokens", 2048)),
    }
    timeout = int(cfg.get("timeout", 30))

    # LLM 健康检测（本地端点，现役 LM Studio）
    llm_base = url.rsplit("/v1/", 1)[0] if "/v1/" in url else url.rsplit("/", 1)[0]
    health_checker = LLMHealthChecker.get_instance(llm_base)

    if not health_checker.is_available():
        print("[llm_health] 本地 LLM 不可用，降级到 OmniRoute 网关")
        # 降级到网关
        return chat(prompt, hub_root, fallback=True)

    def _do_local_http() -> str:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    # 使用弹性管道：Timeout(外) + Retry(内)
    pipeline = ResiliencePipelineBuilder()
    pipeline.add_timeout(timeout=timeout)
    pipeline.add_retry(
        max_attempts=2, base_delay=0.5, jitter=0.2,
        on_retry=lambda evt: print(f"[resilience/local_chat] retry #{evt.attempt}: {evt.detail}"),
    )
    # 添加降级：本地 LLM 调用失败时降级到网关
    pipeline.add_fallback(
        fallback_fn=lambda: chat(prompt, hub_root, fallback=True),
        on_fallback=lambda evt: print(f"[resilience/local_chat] fallback to gateway: {evt.detail}"),
    )
    return pipeline.build().execute(_do_local_http)


def _decision_quality(text: str) -> tuple[float, dict]:
    """量化去重决策质量。不信任模型自报 confidence，依据结构化 + 长度 + 合规度打分。"""
    from tools.dedup import parse_decision

    parsed = parse_decision(text)
    score = 0.0
    if parsed.get("action") in {"skip", "create", "merge", "delete"}:
        score += 0.35
    if parsed.get("reason") and len(parsed["reason"]) >= 8:
        score += 0.15
    conf = parsed.get("confidence", None)
    if isinstance(conf, (int, float)) and 0.0 <= float(conf) <= 1.0:
        score += 0.15
    if parsed.get("action") in {"skip", "create"} or parsed.get("target"):
        score += 0.20
    if text and len(text) <= 2000:
        score += 0.15
    return round(score, 3), parsed


def smart_chat(prompt: str, hub_root: str | Path) -> str:
    """本地优先 + 量化升级的统一逻辑任务入口。

    接入 LLM 健康检测：本地 LLM 不可用时直接跳过本地通道，使用网关。
    去重任务（包含记忆库去重决策器）按决策质量分 + 模型自报 confidence 双重门禁。
    达不到阈值时升级路径：本地模型 -> OmniRoute auto/offline。
    """
    root = Path(hub_root)
    cfg = load_engine_config()
    local_cfg = cfg.get("local_chat") or {}
    local_model = str(local_cfg.get("model", "qwen2.5-coder:1.5b"))
    escalation = cfg.get("escalation") or {}
    is_dedup = "记忆库去重决策器" in prompt
    min_score = float(escalation.get("min_score", 0.80))
    min_conf = float(escalation.get("min_confidence", 0.80))

    # LM Studio / LLM 健康检测（现役本地端点；变量原名 ollama_* 属退役残名，2026-09-02 清理）
    llm_url = str(local_cfg.get("url", "http://127.0.0.1:1234/v1/chat/completions"))
    llm_base = llm_url.rsplit("/v1/", 1)[0] if "/v1/" in llm_url else llm_url.rsplit("/", 1)[0]
    health_checker = LLMHealthChecker.get_instance(llm_base)

    llm_available = health_checker.is_available()
    if not llm_available:
        print("[llm_health] 本地 LLM 不可用，直接使用 OmniRoute 网关")
        return chat(
            prompt, root, fallback=False,
            model=str(escalation.get("remote_model", "auto/offline")),
        )

    # 本地 LLM 可用，走本地通道
    last_text = ""
    try:
        last_text = _local_chat(prompt, root, local_model)
        if not is_dedup:
            return last_text
        score, parsed = _decision_quality(last_text)
        if score >= min_score and float(parsed.get("confidence", 0.0)) >= min_conf:
            return last_text
    except OSError as e:
        print(f"[smart_chat] local_chat failed: {e}")

    # 升级路径：尝试更大本地模型
    if bool(escalation.get("enabled", True)):
        local_upgrade_models = [
            str(escalation.get("intermediate_model", "qwen2.5-coder:3b")),
            str(escalation.get("local_model", "qwen3.5:4b")),
        ]
        for upgrade_model in local_upgrade_models:
            try:
                # 再次检查 LLM 健康状态
                if not health_checker.is_available():
                    print("[llm_health] 本地 LLM 在升级期间不可用，切换到网关")
                    break
                upgraded = _local_chat(prompt, root, upgrade_model)
            except OSError as e:
                print(f"[smart_chat] upgrade {upgrade_model} failed: {e}")
                continue
            last_text = upgraded
            if not is_dedup:
                return upgraded
            score, parsed = _decision_quality(upgraded)
            if score >= min_score and float(parsed.get("confidence", 0.0)) >= min_conf:
                return upgraded

    # 最终降级：使用 OmniRoute 网关
    return chat(
        prompt,
        root,
        fallback=False,
        model=str(escalation.get("remote_model", "auto/offline")),
    )





















def _cmd_chat(args) -> int:
    print(smart_chat(args.prompt, Path(args.root)))
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
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--n", type=int, default=2)
    p.add_argument("--mode", choices=("char", "word"), default="word")
    p.set_defaults(func=cmd_retrieve)

    p = sub.add_parser("build-vectors", help="增量补写第二层语义向量库")
    p.add_argument("--root", required=True)
    p.set_defaults(func=cmd_build_vectors)

    p = sub.add_parser("ingest", help="导入暂存区（默认自动跑 post_ingest_hook 同步 INDEX）")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--no-index", action="store_true",
                   help="跳过 INDEX.md 自动同步（默认 ingest 成功后会自动追加 INDEX 条目）")
    p.add_argument("--strict-lint", action="store_true",
                   help="L1 门禁：草稿 frontmatter 不合规直接 return 阻断（默认软门禁，只标红）")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("confirm", help="确认待人工审核的卡片（按 card.type 路由入权威区）")
    p.add_argument("--root", required=True)
    p.add_argument("name")
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser("distill", help="复盘→候选规则")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", default="trae")
    p.set_defaults(func=cmd_distill)

    p = sub.add_parser("tidy", help="归档")
    p.add_argument("--root", required=True)
    p.add_argument("rel")
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_tidy)

    p = sub.add_parser("lint", help="库健康检查")
    p.add_argument("--root", required=True)
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("status", help="一键健康快照")
    p.add_argument("--root", required=True)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("gate", help="质量门禁编排")
    p.add_argument("--root", required=True)
    p.add_argument("--fail-below", type=float, default=None)
    p.add_argument("--skip-pytest", action="store_true")
    p.add_argument("--skip-ruff", action="store_true")
    p.add_argument("--skip-vector", action="store_true")
    p.add_argument("--keep-going", action="store_true")
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("sync", help="同步平台记忆")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--push", action="store_true")
    p.add_argument("--only-rules", action="store_true")
    p.add_argument("--name", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("chat", help="omniroute 问答")
    p.add_argument("--root", required=True)
    p.add_argument("prompt")
    p.set_defaults(func=_cmd_chat)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())