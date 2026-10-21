"""中枢增强引擎统一入口：chat（检索/归纳/整理均复用此通道；2026-09-15 起本地优先、无 OmniRoute 兜底）

V1.1 (2026-09-07): P1 拆分 — 10 个 _cmd_* 子命令搬到 commands/ 子包，
本文件仅保留 chat + main() 路由表。子命令处理函数从 commands 包导入。
"""

import json  # noqa: F401  (chat helpers 复用)
import sys
from contextlib import suppress
from datetime import datetime, timedelta, timezone  # noqa: F401  (chat helpers 复用)
from pathlib import Path

# 让 engine.py 能 import commands/ 子包（同级目录）
sys.path.insert(0, str(Path(__file__).resolve().parent))

# === P1 拆分：从 commands 子包导入各子命令处理函数 ===
from commands import (  # noqa: I001  (must precede common.config — needs sys.path insert)
    cmd_audit,
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
    cmd_tier_bootstrap,
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


def _gateway_kwargs(hub_root: Path, model: str | None = None) -> tuple[str, str, str, int, str, int | None]:
    """返回 (url, model, api_key, timeout, compress, max_tokens)；**无远程配置则返回 None**。

    2026-09-15 用户裁定：**OmniRoute 从兜底中移除**（长期 401，且会静默吞掉本地结果）。
    故这里**不再硬编码 127.0.0.1:20128** —— 只有配置里显式给出 `gateway_url` 才返回远程通道，
    否则返回 None，调用方一律走本地降级，绝不隐式打到一个可能已死的网关上。
    """
    cfg = load_engine_config()
    gateway_url = str(cfg.get("gateway_url", "") or "").strip()
    if not gateway_url:
        return None
    keys = load_provider_keys(hub_root)
    url = gateway_url.rstrip("/") + "/v1/chat/completions"
    model = model or cfg.get("default_model", "auto/offline")
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
            on_retry=lambda evt: print(f"[resilience] retry #{evt.attempt}: {evt.detail}"),
        )
    )


def chat(
    prompt: str,
    hub_root: str | Path,
    fallback: bool = True,
    *,
    model: str | None = None,
) -> str:
    """调用远程网关（**仅当配置了 gateway_url**）；不可用则回退本地检索+本地模型兜底。

    2026-09-15：OmniRoute 已从兜底移除 —— 未配置远程时**不做任何 HTTP**，
    直接走 `_do_fallback`（本地检索 + 本地模型骨架），避免空转到死网关。
    """
    import requests

    hub_root = Path(hub_root)
    gw = _gateway_kwargs(hub_root, model)
    if gw is None:
        print("[llm_chain] 未配置远程网关（OmniRoute 已移除）→ 直接走本地兜底")
        return _do_fallback(prompt, hub_root)
    url, model, api_key, timeout, compress, max_tokens = gw
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
            on_fallback=lambda evt: print(f"[resilience/chat] fallback: {evt.detail}"),
        )
        .add_timeout(timeout=timeout)
        .add_retry(
            max_attempts=3,
            base_delay=0.5,
            max_delay=30.0,
            jitter=0.3,
            on_retry=lambda evt: print(f"[resilience/chat] retry #{evt.attempt}: {evt.detail}"),
        )
        .build()
    )
    return pipeline.execute(_do_http)


def _do_fallback(prompt: str, hub_root: Path) -> str:
    """降级逻辑：网关不可用时回退到文件检索 + 本地兜底。"""
    cards = retrieve(hub_root, prompt)
    if not cards:
        return "（本地兜底且中枢无命中，建议交回用户确认）"
    parts = [f"[{c.type}/{c.status}] {c.path.name}" for c in cards[:3]]
    bodies = [c.body.strip() for c in cards[:3]]
    try:
        local = _local_fallback_chat(hub_root, prompt, parts, bodies)
    except Exception:
        local = ""
    if local:
        return "（外部 AI 源不可用，已用本地模型兜底应答，仅供参考，建议人工复核）\n\n" + local
    return "本地检索兜底（无远程网关）：\n" + "\n".join(parts) + "\n---\n" + "\n\n".join(bodies)


def _local_fallback_chat(hub_root: Path, prompt: str, parts: list[str], bodies: list[str]) -> str:
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

    ref = "\n".join(f"- {p}:\n{b[:400]}" for p, b in zip(parts, bodies, strict=False))
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
        max_attempts=2,
        base_delay=1.0,
        jitter=0.2,
        on_retry=lambda evt: print(f"[resilience/local_fallback] retry #{evt.attempt}: {evt.detail}"),
    )
    try:
        return pipeline.build().execute(_do_fallback_http)
    except Exception as e:
        print(f"[resilience/local_fallback] 本地 LLM 兜底失败: {e}")
        return ""


def _endpoint_base(url: str) -> str:
    """从 chat/completions URL 取健康检查基址（http://h:p/v1/chat/completions → http://h:p）"""
    return url.rsplit("/v1/", 1)[0] if "/v1/" in url else url.rsplit("/", 1)[0]


def _local_endpoint_chain(cfg: dict) -> list[tuple[str, str, int]]:
    """本地 LLM 端点链：① LM Studio（local_chat）② local_chat_fallbacks（可选，当前为空）。

    返回 [(url, model, max_tokens)]；model 为空串 = 调用前动态解析 served model。
    """
    primary = cfg.get("local_chat") or {}
    chain = [
        (
            str(primary.get("url", "http://127.0.0.1:1234/v1/chat/completions")),
            str(primary.get("model", cfg.get("default_model", ""))),
            int(primary.get("max_tokens", 2048)),
        )
    ]
    for extra in cfg.get("local_chat_fallbacks") or []:
        if not isinstance(extra, dict) or not extra.get("url"):
            continue
        chain.append(
            (
                str(extra["url"]),
                str(extra.get("model") or ""),
                int(extra.get("max_tokens", 2048)),
            )
        )
    return chain


def _resolve_served_model(url: str, timeout: int) -> str:
    """OpenAI 兼容端点的模型名：GET {base}/v1/models 取首个 **非 embedding** 的 id。

    端点内已加载的模型会随看板切换而变（LM Studio 可随时换载），
    qwen/qwen3.5-9b 亦已退役，故一律不硬编码，调用前动态解析。

    ⚠️ 2026-10-10 体检修正：原为“取首个 id”——而 LM Studio 的模型列表是**混排**的
    （本机实测：gemma-4-26b-a4b-it-qat / text-embedding-bge-m3 / qwen3.8-27b-fast /
    text-embedding-nomic-…），一旦看板把 embedding 排到首位，chat 端点就会拿到
    embedding 模型名 ⇒ 400 ⇒ 整链静默降级（与 system/config.yaml 注释里的历史事故同型）。
    现优先在非 embedding 的 id 里取首个；全为 embedding 时才退回原行为。
    """
    import re

    import requests

    try:
        resp = requests.get(f"{_endpoint_base(url)}/v1/models", timeout=min(timeout, 10))
        resp.raise_for_status()
        data = resp.json().get("data") or []
        ids = [str(d["id"]) for d in data if isinstance(d, dict) and d.get("id")]
        if not ids:
            return ""
        chat_like = [i for i in ids if not re.search(r"embed", i, re.I)]
        return (chat_like or ids)[0]
    except Exception as e:
        print(f"[llm_chain] 解析模型名失败: {e}")
    return ""


def _post_chat(url: str, model: str, prompt: str, max_tokens: int, timeout: int) -> str:
    """单次 OpenAI 兼容 chat 调用（失败向上抛，由调用方决定降级/自愈）。"""
    import requests

    resp = requests.post(
        url,
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "stream": False,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _local_chain_fallback(prompt: str, hub_root: Path) -> str:
    """本地模型降级链：LM Studio(1234) → local_chat_fallbacks（当前为空）；**无远程兜底**（OmniRoute 已移除）。

    逐环尝试「健康 + 调用成功」；全链失败才落到 chat()（无远程配置时即本地检索兜底）。

    ⚠️ 2026-10-10 体检新增「**模型名钉子腐化自愈**」：`local_chat.model` 是**硬钉**，
    而 LM Studio 换载后该名字会 400（本机实测：`qwen3-4b-instruct-2507` 已不在服务列表
    ⇒ 去重链整段降级、每次 ingest 只能靠人工 `git mv` 兜底）。现在首次调用失败后，
    用动态解析到的 chat 模型**再试一次**，把「静默降级」变成「自愈一次」；仍失败才继续降级。
    """
    cfg = load_engine_config()
    timeout = int(cfg.get("timeout", 30))
    for url, model_name, max_tokens in _local_endpoint_chain(cfg):
        base = _endpoint_base(url)
        if not LLMHealthChecker.get_instance(base).is_available():
            print(f"[llm_chain] 跳过未就绪本地端点: {base}")
            continue
        use_model = model_name or _resolve_served_model(url, timeout)
        if not use_model:
            print(f"[llm_chain] 端点模型名解析失败，跳过: {url}")
            continue
        try:
            text = _post_chat(url, use_model, prompt, max_tokens, timeout)
            print(f"[llm_chain] 命中本地端点: {base} (model={use_model})")
            return text
        except Exception as e:  # noqa: BLE001 - 单环失败继续降级
            resolved = _resolve_served_model(url, timeout)
            if resolved and resolved != use_model:
                print(f"[llm_chain] 模型 {use_model} 调用失败（{e}）→ 自愈重试动态模型 {resolved}")
                try:
                    text = _post_chat(url, resolved, prompt, max_tokens, timeout)
                    print(f"[llm_chain] 自愈命中本地端点: {base} (model={resolved})")
                    return text
                except Exception as e2:  # noqa: BLE001
                    print(f"[llm_chain] 自愈仍失败: {type(e2).__name__}: {e2}")
            print(f"[llm_chain] 本地端点失败，继续降级: {base}: {e}")
    print("[llm_chain] 本地链全部不可用 → 无远程兜底（OmniRoute 已移除）")
    return chat(prompt, hub_root, fallback=True)


def _local_chat(prompt: str, hub_root: Path, model: str | None = None) -> str:
    """直连本地 LLM 的统一入口 (LM Studio)，供本地默认逻辑任务使用。
    接入 LLM 健康检测 + 弹性管道：本地 LLM 不可用时自动降级到网关。"""
    import requests

    cfg = load_engine_config()
    local_cfg = cfg.get("local_chat") or {}
    # 本地默认逻辑入口：模型绑定
    url = str(local_cfg.get("url", "http://127.0.0.1:1234/v1/chat/completions"))
    model_name = model or str(local_cfg.get("model", cfg.get("default_model", "qwen2.5-coder-1.5b-instruct")))
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
        print("[llm_health] 本地端点不可用，走降级链（仅次选端点，无远程兜底）")
        return _local_chain_fallback(prompt, hub_root)

    def _do_local_http() -> str:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    # 使用弹性管道：Timeout(外) + Retry(内)
    pipeline = ResiliencePipelineBuilder()
    pipeline.add_timeout(timeout=timeout)
    pipeline.add_retry(
        max_attempts=2,
        base_delay=0.5,
        jitter=0.2,
        on_retry=lambda evt: print(f"[resilience/local_chat] retry #{evt.attempt}: {evt.detail}"),
    )
    # 添加降级：本地 LLM 调用失败时降级到网关
    pipeline.add_fallback(
        fallback_fn=lambda: _local_chain_fallback(prompt, hub_root),
        on_fallback=lambda evt: print(f"[resilience/local_chat] 本地失败 → 降级链: {evt.detail}"),
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
    升级路径只在本地区间内（2026-09-15 OmniRoute 已从兜底移除）；无可用升级环时，
    直接采用本地结果，绝不外送。
    """
    root = Path(hub_root)
    cfg = load_engine_config()
    local_cfg = cfg.get("local_chat") or {}
    # 2026-10-10：默认值由两个早已下线的模型名（qwen2.5-coder:1.5b / qwen3-4b-instruct-2507）
    # 改为**空串 = 调用前动态解析**（`_resolve_served_model` 已过滤 embedding）——
    # 硬编码名必然随 LM Studio 换载而腐化（本机已两次）。
    local_model = str(local_cfg.get("model", ""))
    escalation = cfg.get("escalation") or {}
    is_dedup = "记忆库去重决策器" in prompt
    min_score = float(escalation.get("min_score", 0.80))
    min_conf = float(escalation.get("min_confidence", 0.80))

    # LM Studio / LLM 健康检测（现役本地端点；变量原名 ollama_* 属退役残名，2026-09-02 清理）
    llm_url = str(local_cfg.get("url", "http://127.0.0.1:1234/v1/chat/completions"))
    llm_base = llm_url.rsplit("/v1/", 1)[0] if "/v1/" in llm_url else llm_url.rsplit("/", 1)[0]
    health_checker = LLMHealthChecker.get_instance(llm_base)

    # 本地可用性 = 主端点或降级链上任一本地端点健康（2026-09-11：LM Studio → 次选端点，当前为空）
    llm_available = health_checker.is_available() or any(
        LLMHealthChecker.get_instance(_endpoint_base(u)).is_available() for u, _m, _t in _local_endpoint_chain(cfg)[1:]
    )
    if not llm_available:
        print("[llm_health] 本地 LLM 不可用 → 无远程兜底（OmniRoute 已移除）")
        return _do_fallback(prompt, root)

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
            if not str(upgrade_model).strip():
                continue  # 方案B（2026-09-15）：空名=该环未配置，跳过空转
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

    # 最终兜底（2026-09-15 OmniRoute 已移除）：优先采用已有本地结果，否则本地检索兜底
    if last_text.strip():
        print("[llm_chain] 无远程兜底 → 采用本地模型结果（未过质量门禁，谨慎）")
        return last_text
    return _do_fallback(prompt, root)


def _cmd_chat(args) -> int:
    print(smart_chat(args.prompt, Path(args.root)))
    return 0


def _force_utf8_stdio() -> None:
    """把 stdout/stderr 钉死 UTF-8（**中枢侧根修**，不依赖客户端环境）。

    2026-10-21 实测根因：Windows 中文环境（ACP=936）下，**子进程被拉起时若不带
    `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`**，Python 的 `sys.stdout.encoding`
    会退回 `gbk`（实测 `child stdout encoding = gbk`）⇒ 写出的 JSON 是 **GBK 字节**；
    而消费端（pi 扩展 `memory-hub.ts` → `pi.exec` → `data.toString()`）按 **UTF-8** 解码
    ⇒ 每次会话的 `hub-context` 注入块**整段乱码**（实测 U+FFFD≈27/70 字符，混装
    U+0636 等替换字符），模型读到的是不可读字节。

    与 `rules/chinese-text-encoding-discipline`（iron）「全链路钉死 UTF-8，两端都显式声明
    编码，禁依赖默认值」同口径：**不能只靠客户端设环境变量**，中枢自己的 CLI 出口
    必须自带保证——否则任何不带 UTF-8 环境的调用方都会踩同一个坑。

    `errors="replace"` 而非默认 "strict"：万一真遇到不可编码字符，宁可降级成 U+FFFD
    也不能让整个 CLI 因 UnicodeEncodeError 崩掉（stdout 崩 ⇒ 通道静默失效）。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    import argparse

    _force_utf8_stdio()

    parser = argparse.ArgumentParser(prog="hub", description="跨 Agent 平台统一记忆中枢")
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
    p.add_argument(
        "--no-index",
        action="store_true",
        help="跳过 INDEX.md 自动同步（默认 ingest 成功后会自动追加 INDEX 条目）",
    )
    p.add_argument(
        "--strict-lint",
        action="store_true",
        help="L1 门禁：草稿 frontmatter 不合规直接 return 阻断（默认软门禁，只标红）",
    )
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("confirm", help="确认待人工审核的卡片（按 card.type 路由入权威区）")
    p.add_argument("--root", required=True)
    p.add_argument("name")
    # 2026-10-21 体检新增：冲突区（.sync/conflicts/）的卡此前**无提升路径**
    # （去重分流把不重复的新卡送进去后，只能靠人手搬文件）⇒ 本开关补上人工终审动作。
    p.add_argument(
        "--from-conflicts",
        action="store_true",
        help="源改为 .sync/conflicts/<platform>_<name>（去重分流后待人工终审的卡）",
    )
    p.set_defaults(func=cmd_confirm)

    p = sub.add_parser(
        "tier-bootstrap",
        help="会话级预取：任务分型 → 按型检索 → 输出可直接注入的引导块（与 MCP hub_bootstrap 同 handler）",
    )
    p.add_argument("--root", required=True)
    p.add_argument("--context", default="", help="用户首条消息/当前意图（分型依据与检索 query）")
    p.add_argument("--platform", default="pi", help="审计与 reuse 计数用的平台名")
    p.add_argument("--tier", default="", help="强制指定规范型（light/code/hub/sync/project）；缺省自动判定")
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--compress-level", type=int, default=1, help="正文压缩级别（0=原文，1-5 渐进压缩）")
    p.add_argument("--json", action="store_true", help="输出 JSON（供 agent 扩展消费）")
    p.set_defaults(func=cmd_tier_bootstrap)

    p = sub.add_parser("distill", help="复盘→候选规则")
    p.add_argument("--root", required=True)
    # 2026-10-05 修：原默认 `trae`（trae 退役后即“以已退役平台名义写草稿”）⇒ 改为维护者 hermes。
    # 注意：`auto_flywheel` 会扫所有 `*_draft` 目录，改默认即改草稿落位。
    p.add_argument("--platform", default="hermes")
    p.set_defaults(func=cmd_distill)

    p = sub.add_parser("tidy", help="归档")
    p.add_argument("--root", required=True)
    p.add_argument("rel")
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_tidy)

    p = sub.add_parser("lint", help="库健康检查")
    p.add_argument("--root", required=True)
    p.set_defaults(func=cmd_lint)

    # T7 (2026-09-07): L2 INDEX 审核
    p = sub.add_parser("audit", help="INDEX 自动审核（orphan/ghost/格式/重复）")
    p.add_argument("--root", required=True)
    p.add_argument("--report", action="store_true", help="写 retro/lint-report-YYYYMMDD.md")
    p.add_argument("--no-fail", action="store_true", help="发现问题也返回 0（cron 模式）")
    p.set_defaults(func=cmd_audit)

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

    p = sub.add_parser("chat", help="本地优先问答（无远程兜底）")
    p.add_argument("--root", required=True)
    p.add_argument("prompt")
    p.set_defaults(func=_cmd_chat)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
