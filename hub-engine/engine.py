"""omniroute 增强引擎统一入口：chat（检索/归纳/整理均复用此通道）"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common.config import HubConfig, load_engine_config, load_provider_keys
from tools.lint import _all_cards, lint
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
    extra = (
        {"max_tokens": int(max_tokens)}
        if max_tokens and model.startswith("ollama/")
        else {}
    )

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

    # LLM 健康检测
    ollama_base = url.rsplit("/v1/", 1)[0] if "/v1/" in url else url.rsplit("/", 1)[0]
    health_checker = LLMHealthChecker.get_instance(ollama_base)

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

    # LLM 健康检测
    ollama_base = url.rsplit("/v1/", 1)[0] if "/v1/" in url else url.rsplit("/", 1)[0]
    health_checker = LLMHealthChecker.get_instance(ollama_base)

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
    # 添加降级：Ollama 调用失败时降级到网关
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

    接入 LLM 健康检测：Ollama 不可用时直接跳过本地通道，使用网关。
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

    # LM Studio / LLM 健康检测
    ollama_url = str(local_cfg.get("url", "http://127.0.0.1:1234/v1/chat/completions"))
    ollama_base = ollama_url.rsplit("/v1/", 1)[0] if "/v1/" in ollama_url else ollama_url.rsplit("/", 1)[0]
    health_checker = LLMHealthChecker.get_instance(ollama_base)

    ollama_available = health_checker.is_available()
    if not ollama_available:
        print("[llm_health] 本地 LLM 不可用，直接使用 OmniRoute 网关")
        return chat(
            prompt, root, fallback=False,
            model=str(escalation.get("remote_model", "auto/offline")),
        )

    # Ollama 可用，走本地通道
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


def _cmd_retrieve(args) -> int:
    for c in retrieve(
        Path(args.root), args.query, top_k=args.top_k, n=args.n, mode=args.mode
    ):
        from tools.snippet import extract_snippet

        print(f"[{c.type}/{c.status}] {c.path.name}")
        print(extract_snippet(c.body, args.query))
    return 0


def _cmd_build_vectors(args) -> int:
    from tools.semsearch import build

    stats = build(Path(args.root))
    print(stats)
    touched = stats["inserted"] + stats["updated"] + stats["reused"]
    if touched > 0 and stats["embedded"] + stats["reused"] == 0:
        print(
            "【告警】向量通道退化：有卡片处理但零向量（embed 后端/模型/网络不可用），"
            "语义检索已回退词袋，请检查 bge 模型与网络。"
        )
        return 2
    return 0


def _cmd_ingest(args) -> int:
    from common.config import load_engine_config
    from sync import ingest

    cfg = load_engine_config()
    batch_model = str(cfg.get("batch_model", "") or "").strip()
    chat_fn = (
        (lambda prompt, root: smart_chat(prompt, root))
        if batch_model
        else chat
    )
    stat = ingest(Path(args.root), args.platform, chat_fn=chat_fn)
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
    print("幽灵登记:", report["ghosts"])
    print("hook漂移:", [h["name"] for h in report["hooks"]])
    print("陈旧页:", report["stale"])
    print("无效卡片:", report["invalid"])
    print("备注:", report["notes"])
    unhealthy = (
        len(report["orphans"])
        + len(report["ghosts"])
        + len(report["stale"])
        + report["invalid"]
    )
    if unhealthy:
        print(
            f"【告警】发现 {unhealthy} 处健康问题：orphans {len(report['orphans'])} / "
            f"ghosts {len(report['ghosts'])} / stale {len(report['stale'])} / invalid {report['invalid']}"
        )
        return 2
    return 0


def _cmd_status(args) -> int:
    """一键健康快照 v2：卡片分布 / Lint / LLM 健康 / 健康评分 / 告警 / 今日指标 / 最近提交"""
    import json
    import subprocess
    from collections import Counter
    from datetime import datetime, timedelta, timezone

    _LOCAL_TZ = timezone(timedelta(hours=+8))

    root = Path(args.root)

    # === 1. 静态数据收集 ===
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
        "generated_at": datetime.now(_LOCAL_TZ).isoformat(),
        "root": str(root),
        "cards": counts,
        "lint": {
            "orphans": len(report["orphans"]),
            "ghosts": len(report["ghosts"]),
            "hooks": len(report["hooks"]),
            "stale": len(report["stale"]),
            "invalid": report["invalid"],
        },
        "pending": len(pending),
        "pending_first": pending[0].name if pending else None,
        "last_commit": last,
    }

    # 向量 freshness
    try:
        from tools.semsearch import scan_stale
        fresh = scan_stale(root)
        data["fresh"] = {
            "stale_total": fresh["total"],
            "stale_by_dir": fresh["stale_by_dir"],
        }
    except Exception:
        data["fresh"] = {"stale_total": -1, "stale_by_dir": {}}

    # === 2. LLM 健康检测 ===
    llm_status = _collect_llm_status()
    data["llm_health"] = llm_status

    # === 3. 今日指标聚合 ===
    today_metrics = _collect_today_metrics(root)
    data["today_metrics"] = today_metrics

    # === 4. 健康度评分 ===
    health_scores = _compute_snapshot_health_scores(
        counts, report, llm_status, root
    )
    data["health_scores"] = health_scores

    # === 5. 自监控告警 ===
    alerts = _collect_snapshot_alerts(
        report, llm_status, today_metrics, health_scores, pending
    )
    data["alerts"] = alerts

    # === 6. 与昨日快照对比 ===
    prev_snapshot = _load_previous_snapshot(root)
    if prev_snapshot:
        data["comparison"] = _compare_snapshots(prev_snapshot, data)

    # === 输出 ===
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _print_snapshot_report(data, report, pending)

    # 退出码
    has_critical = any(a["level"] == "critical" for a in alerts)
    has_warning = any(a["level"] == "warning" for a in alerts)
    lint_bad = report["invalid"] > 0 or report["orphans"] or report["ghosts"]
    if has_critical:
        return 3
    if lint_bad or has_warning:
        return 2
    return 0


def _collect_llm_status() -> dict:
    """采集 LM Studio 服务状态。"""
    try:
        from tools.llm_health import LLMHealthChecker
        checker = LLMHealthChecker.get_instance("http://localhost:1234")
        status = checker.get_status()
        return {
            "available": status.available,
            "url": status.url,
            "models": status.models,
            "model_count": len(status.models),
            "response_time_ms": round(status.response_time * 1000, 1),
            "last_check": (
                datetime.fromtimestamp(status.last_check, tz=timezone.utc).isoformat()
                if status.last_check else None
            ),
            "last_error": status.last_error,
        }
    except Exception as e:
        return {
            "available": False,
            "error": str(e),
            "url": "http://localhost:11434",
            "models": [],
            "model_count": 0,
            "response_time_ms": 0,
            "last_check": None,
            "last_error": str(e),
        }


def _collect_today_metrics(root: Path) -> dict:
    """聚合今日查询指标。"""
    from tools.lint import _all_cards

    log_path = root / ".sync" / "state" / "query.log.jsonl"
    search_count = hit = miss = reuse_ops = 0

    if log_path.is_file():
        today = datetime.now(timezone(timedelta(hours=+8))).date()
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = r.get("ts", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.astimezone(timezone(timedelta(hours=+8))).date() != today:
                    continue
            except ValueError:
                continue
            action = r.get("action")
            if action == "search":
                search_count += 1
                if int(r.get("hit_count") or 0) > 0:
                    hit += 1
                else:
                    miss += 1
            elif action == "reuse":
                reuse_ops += 1

    hit_rate = round(hit / search_count, 4) if search_count else None
    miss_rate = round(miss / search_count, 4) if search_count else None
    total_cards = sum(1 for _sub, _p, _c in _all_cards(root) if _c is not None)

    return {
        "date": datetime.now(timezone(timedelta(hours=+8))).date().isoformat(),
        "total_cards": total_cards,
        "searches": search_count,
        "hits": hit,
        "misses": miss,
        "hit_rate": hit_rate,
        "miss_rate": miss_rate,
        "reuse_ops": reuse_ops,
    }



def _estimate_hub_tool_capacity(root: Path) -> float:
    """当 SkillHub 目录不存在时，用 hub 自身 tools/ 模块数 + MCP handlers 估算技能健康度。

    计分规则（满分 100）：
    - tools/ 可导入模块数：16 个 expected，每个 4 分（上限 64）
    - MCP handler 完整性：5 个 expected，每个 6 分（上限 30）
    - 平台适配器覆盖数：4 个 expected，每个 1.5 分（上限 6）
    """
    score = 0.0
    engine_dir = root.parent / "hub-engine"

    # tools/ 可导入模块
    engine_dir / "tools"
    expected_tools = {
        "compress", "dedup", "distill", "inject", "lint", "llm_health",
        "mcp_audit", "mcp_handlers", "mcp_policy", "memory_diff",
        "platform_bridge", "resilience", "retrieve", "semsearch", "snippet", "tidy",
    }
    import_ok = 0
    for mod_name in expected_tools:
        try:
            import importlib
            sys.path.insert(0, str(engine_dir))
            importlib.import_module(f"tools.{mod_name}")
            import_ok += 1
        except (ImportError, Exception):
            pass
    score += min(import_ok, 16) * 4  # 上限 64

    # MCP handler 完整性
    mcp_handlers = ["hub_search", "hub_get", "hub_index", "hub_bootstrap", "hub_ingest_candidate"]
    try:
        import importlib
        sys.path.insert(0, str(engine_dir))
        mod = importlib.import_module("tools.mcp_handlers")
        present = sum(1 for fn in mcp_handlers if hasattr(mod, fn) and callable(getattr(mod, fn)))
        score += present * 6  # 上限 30
    except Exception:
        pass

    # 平台适配器覆盖
    try:
        from common.config import HubConfig
        cfg = HubConfig.load(root)
        platforms = (cfg.platforms or {}).keys()
        supported = {"hermes", "trae", "code", "workbuddy"}
        covered = sum(1 for p in platforms if p in supported)
        score += covered * 1.5  # 上限 6
    except Exception:
        pass

    return min(round(score, 1), 100.0)
def _compute_snapshot_health_scores(
    counts: dict,
    report: dict,
    llm_status: dict,
    root: Path,
) -> dict:
    """计算快照健康度评分（4 维 + 总分）。"""
    total_cards = sum(counts.values())
    unhealthy_cards = len(report.get("orphans", [])) + len(report.get("ghosts", []))
    card_health = ((total_cards - unhealthy_cards) / max(total_cards, 1)) * 100

    # skill_health 默认值改为 hub 自身工具能力估算（取代硬编码 50.0）
    skill_health = _estimate_hub_tool_capacity(root)
    skillhub_root = root.parent / "SkillHub"
    if skillhub_root.is_dir():
        try:
            import yaml
            skills_root = skillhub_root / "skills"
            if skills_root.is_dir():
                from collections import Counter as Ctr
                status_counts = Ctr()
                for yaml_file in skills_root.rglob("skill.yaml"):
                    try:
                        with open(yaml_file, encoding="utf-8") as f:
                            data = yaml.safe_load(f) or {}
                        status_counts[data.get("status", "unknown")] += 1
                    except (OSError, ValueError):
                        continue
                total_skills = sum(status_counts.values())
                active_skills = status_counts.get("active", 0)
                skill_health = (active_skills / max(total_skills, 1)) * 100
        except ImportError:
            pass

    flywheel_log = root / ".sync" / "state" / "flywheel-log.json"
    flywheel_activity = 0.0
    if flywheel_log.is_file():
        try:
            logs = json.loads(flywheel_log.read_text(encoding="utf-8"))
            if isinstance(logs, list) and logs:
                from datetime import timedelta as td
                cutoff = datetime.now(timezone.utc) - td(days=7)
                recent = 0
                for entry in logs[-30:]:
                    ts = entry.get("timestamp", "")
                    if ts:
                        try:
                            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if dt >= cutoff:
                                recent += 1
                        except ValueError:
                            pass
                flywheel_activity = min(recent / 7.0, 1.0) * 100
        except (json.JSONDecodeError, ValueError, OSError):
            pass

    llm_health = 100.0
    if not llm_status.get("available", False):
        llm_health = 0.0
    else:
        rt = llm_status.get("response_time_ms", 1000)
        if rt < 100:
            llm_health = 100.0
        elif rt < 500:
            llm_health = 80.0
        else:
            llm_health = 60.0

    overall = (
        card_health * 0.25
        + skill_health * 0.35
        + flywheel_activity * 0.20
        + llm_health * 0.20
    )

    return {
        "card_health": round(card_health, 1),
        "skill_health": round(skill_health, 1),
        "flywheel_activity": round(flywheel_activity, 1),
        "llm_health": round(llm_health, 1),
        "overall": round(overall, 1),
    }


def _collect_snapshot_alerts(
    report: dict,
    llm_status: dict,
    today_metrics: dict,
    health_scores: dict,
    pending: list,
) -> list:
    """采集快照自监控告警（分级：critical / warning / info）。"""
    alerts = []

    if not llm_status.get("available", False):
        alerts.append({
            "level": "critical",
            "rule": "local_llm_unavailable",
            "message": f"本地 LLM 服务不可用 (LM Studio): {llm_status.get('last_error', '未知错误')}",
            "suggestion": "检查 LM Studio 是否在运行，确认 API 端口 1234",
        })

    unhealthy = (
        len(report.get("orphans", []))
        + len(report.get("ghosts", []))
        + len(report.get("stale", []))
        + report.get("invalid", 0)
    )
    if unhealthy > 0:
        alerts.append({
            "level": "warning",
            "rule": "lint_issues",
            "message": f"Lint 发现 {unhealthy} 处问题：orphans={len(report.get('orphans', []))} ghosts={len(report.get('ghosts', []))} stale={len(report.get('stale', []))} invalid={report.get('invalid', 0)}",
            "suggestion": "运行 hub lint 检查详情并修复",
        })

    hit_rate = today_metrics.get("hit_rate")
    if hit_rate is not None and 0 < hit_rate < 0.6:
        alerts.append({
            "level": "warning",
            "rule": "low_hit_rate",
            "message": f"今日命中率 {hit_rate:.1%}，低于 60% 阈值",
            "suggestion": "检查高频未命中查询，补充卡片或优化 tags",
        })

    if health_scores.get("flywheel_activity", 100) < 30:
        alerts.append({
            "level": "warning",
            "rule": "low_flywheel_activity",
            "message": f"飞轮活跃度 {health_scores['flywheel_activity']}%，近 7 天活动不足",
            "suggestion": "运行 auto_flywheel.py 处理草稿，保持飞轮运转",
        })

    if pending:
        alerts.append({
            "level": "info",
            "rule": "pending_confirmation",
            "message": f"{len(pending)} 张卡片待人工确认",
            "suggestion": "运行 hub confirm 逐张确认 pending 目录下的卡",
        })

    if llm_status.get("available") and llm_status.get("response_time_ms", 0) > 500:
        alerts.append({
            "level": "info",
            "rule": "local_llm_slow",
            "message": f"本地 LLM 响应时间 (LM Studio) {llm_status['response_time_ms']}ms，建议优化",
            "suggestion": "检查 LM Studio 资源占用，考虑开启 GPU 加速或冷启动预热",
        })

    return alerts


def _load_previous_snapshot(root: Path) -> dict | None:
    """加载昨日快照用于对比。"""
    retro_dir = root / "retro"
    if not retro_dir.is_dir():
        return None
    yesterday = (datetime.now(timezone(timedelta(hours=+8))) - timedelta(days=1))
    snapshot_path = retro_dir / f"snapshot-{yesterday.date().isoformat()}.json"
    if not snapshot_path.is_file():
        return None
    try:
        return json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _compare_snapshots(prev: dict, curr: dict) -> dict:
    """对比两个快照的关键指标变化。"""
    changes = {}

    prev_cards = prev.get("cards", {})
    curr_cards = curr.get("cards", {})
    card_changes = {}
    for k in set(list(prev_cards.keys()) + list(curr_cards.keys())):
        delta = curr_cards.get(k, 0) - prev_cards.get(k, 0)
        if delta != 0:
            card_changes[k] = {"delta": delta, "prev": prev_cards.get(k, 0), "curr": curr_cards.get(k, 0)}
    if card_changes:
        changes["cards"] = card_changes

    prev_scores = prev.get("health_scores", {})
    curr_scores = curr.get("health_scores", {})
    score_changes = {}
    for k in set(list(prev_scores.keys()) + list(curr_scores.keys())):
        pv = prev_scores.get(k)
        cv = curr_scores.get(k)
        if pv is not None and cv is not None:
            delta = round(cv - pv, 1)
            if abs(delta) >= 1.0:
                score_changes[k] = {"delta": delta, "prev": pv, "curr": cv}
    if score_changes:
        changes["health_scores"] = score_changes

    prev_ollama = prev.get("llm_health") or prev.get("ollama", {})
    curr_ollama = curr.get("llm_health") or curr.get("ollama", {})
    prev_avail = prev_ollama.get("available", True)
    curr_avail = curr_ollama.get("available", True)
    if prev_avail != curr_avail:
        changes["llm_status"] = {
            "prev": "available" if prev_avail else "unavailable",
            "curr": "available" if curr_avail else "unavailable",
        }

    prev_alert_rules = {a["rule"] for a in prev.get("alerts", [])}
    curr_alert_rules = {a["rule"] for a in curr.get("alerts", [])}
    new_alerts = list(curr_alert_rules - prev_alert_rules)
    resolved_alerts = list(prev_alert_rules - curr_alert_rules)
    if new_alerts or resolved_alerts:
        changes["alerts"] = {
            "new": new_alerts,
            "resolved": resolved_alerts,
        }

    return changes


def _print_snapshot_report(data: dict, report: dict, pending: list):
    """打印人类可读的快照报告。"""
    print(f"生成时间: {data['generated_at']}")
    print(f"中枢: {data['root']}")
    print()

    dist = " · ".join(f"{k}={v}" for k, v in data["cards"].items()) or "（空）"
    print(f"📚 卡片分布: {dist}")
    print(
        f"🔍 Lint: 孤儿 {data['lint']['orphans']} · 幽灵 {data['lint']['ghosts']} "
        f"· hook {data['lint']['hooks']} · 陈旧 {data['lint']['stale']} · 无效 {report['invalid']}"
    )
    print(
        f"📋 待人工确认: {data['pending']}"
        + (f" → {data['pending_first']}" if data["pending_first"] else "")
    )

    fresh = data.get("fresh", {})
    fresh_total = fresh.get("stale_total", -1)
    if fresh_total >= 0:
        fresh_txt = (
            " · ".join(f"{k}={v}" for k, v in fresh.get("stale_by_dir", {}).items())
            or "无"
        )
        print(
            f"💾 向量待重建(freshness): {fresh_total} 张"
            + (f" ({fresh_txt})" if fresh_total > 0 else "")
        )
    print(f"📦 最近提交: {data['last_commit']}")

    ollama = data.get("llm_health") or data.get("ollama", {})
    if ollama.get("available"):
        models_str = ", ".join(ollama.get("models", [])[:3])
        print(
            f"🦙 本地 LLM 健康 (LM Studio): ✅ 可用 · {ollama.get('model_count', 0)} 模型"
            f" · 响应 {ollama.get('response_time_ms', 0)}ms"
            + (f" · 模型: {models_str}" if models_str else "")
        )
    else:
        print(f"🦙 本地 LLM 健康 (LM Studio): ❌ 不可用 · 错误: {ollama.get('last_error', '未知')}")

    scores = data.get("health_scores", {})
    if scores:
        print("\n📊 健康度评分:")
        score_labels = {
            "card_health": "卡片",
            "skill_health": "技能",
            "flywheel_activity": "飞轮",
            "llm_health": "本地 LLM",
            "overall": "📈 总分",
        }
        for k, v in scores.items():
            label = score_labels.get(k, k)
            bar = "█" * int(v / 5) + "░" * (20 - int(v / 5))
            print(f"  {label}: {bar} {v:.1f}")

    metrics = data.get("today_metrics", {})
    if metrics:
        print("\n📈 今日指标:")
        hr = metrics.get("hit_rate", "N/A")
        print(f"  查询 {metrics.get('searches', 0)} 次"
              f" · 命中 {metrics.get('hits', 0)}"
              f" · 命中率 {hr}"
              f" · 复用 {metrics.get('reuse_ops', 0)} 次")

    alerts = data.get("alerts", [])
    if alerts:
        print(f"\n⚠️ 告警 ({len(alerts)} 项):")
        level_icons = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
        for a in alerts:
            icon = level_icons.get(a["level"], "⚠️")
            print(f"  {icon} [{a['level']}] {a['message']}")
            if a.get("suggestion"):
                print(f"     💡 {a['suggestion']}")
    else:
        print("\n✅ 无告警")

    comparison = data.get("comparison", {})
    if comparison:
        print("\n🔄 较昨日变化:")
        for area, changes in comparison.items():
            if area == "cards":
                for k, v in changes.items():
                    arrow = "📈" if v["delta"] > 0 else "📉" if v["delta"] < 0 else "➡️"
                    print(f"  {arrow} {k}: {v['prev']} → {v['curr']} ({v['delta']:+d})")
            elif area == "health_scores":
                for k, v in changes.items():
                    arrow = "📈" if v["delta"] > 0 else "📉"
                    print(f"  {arrow} 健康分 {k}: {v['prev']} → {v['curr']} ({v['delta']:+.1f})")
            elif area == "llm_status":
                print(f"  ⚡ 本地 LLM: {changes['prev']} → {changes['curr']}")
            elif area == "alerts":
                for r in changes.get("new", []):
                    print(f"  🆕 新告警: {r}")
                for r in changes.get("resolved", []):
                    print(f"  ✅ 已消除: {r}")




def _cmd_gate(args) -> int:
    """质量门禁编排：lint -> pytest -> ruff -> 向量召回回归。"""
    import subprocess

    root = Path(args.root)
    engine_dir = Path(__file__).resolve().parent
    steps: dict[str, tuple[list[str], int]] = {}
    results: dict[str, int] = {}

    from tools.lint import lint as _lint

    rep = _lint(root)
    lh = len(rep["orphans"]) + len(rep["ghosts"]) + len(rep["stale"]) + rep["invalid"]
    print(
        f"[gate] lint: 孤儿 {len(rep['orphans'])} · 幽灵 {len(rep['ghosts'])} · "
        f"陈旧 {len(rep['stale'])} · 无效 {rep['invalid']}"
    )
    results["lint"] = 2 if lh else 0
    if lh and not args.keep_going:
        return 2

    if not args.skip_pytest:
        steps["pytest"] = ([sys.executable, "-m", "pytest", "-q"], 11)
    if not args.skip_ruff:
        steps["ruff"] = ([sys.executable, "-m", "ruff", "check", "."], 12)
    if not args.skip_vector:
        argv = [
            sys.executable,
            str(engine_dir / "scripts" / "vector_bench.py"),
            "--real",
            str(root),
        ]
        if args.fail_below is not None:
            argv += ["--fail-below", str(args.fail_below)]
        steps["vector_regression"] = (argv, 3)

    fail = 0
    for name, (argv, fail_code) in steps.items():
        try:
            r = subprocess.run(
                argv,
                cwd=engine_dir,
                capture_output=True,
                text=True,
                timeout=args.timeout,
                check=False,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            print(f"[gate] {name}: 无法运行（{exc}），视作环境缺失 127")
            fail = max(fail, 127)
            results[name] = 127
            if not args.keep_going:
                return fail
            continue
        last = (r.stderr or r.stdout or "(无输出)").strip().splitlines() or ["(无输出)"]
        print(f"[gate] {name}: exit={r.returncode}  {last[-1]}")
        results[name] = r.returncode
        if r.returncode != 0:
            mapped = r.returncode if r.returncode in (3, 127) else fail_code
            fail = max(fail, mapped)
            if not args.keep_going:
                return fail

    print(
        (f"[gate] 结果：fail_code={fail}（keep_going={args.keep_going}）")
        if fail
        else "[gate] 结果：全绿 (0)"
    )
    for k, v in results.items():
        print(f"   {k}: exit={v}")
    return fail


def _cmd_sync(args) -> int:
    from tools.platform_bridge import pull, push

    root = Path(args.root)
    cfg = HubConfig.load(root)
    platforms = list(cfg.platforms) if args.platform == "all" else [args.platform]
    ok = True
    for name in platforms:
        try:
            stat = (
                push(
                    root,
                    name,
                    only_rules=args.only_rules,
                    name_filter=args.name,
                    dry_run=args.dry_run,
                )
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
    p.set_defaults(func=_cmd_retrieve)

    p = sub.add_parser("build-vectors", help="增量补写第二层语义向量库")
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
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_status)

    p = sub.add_parser("gate", help="质量门禁编排")
    p.add_argument("--root", required=True)
    p.add_argument("--fail-below", type=float, default=None)
    p.add_argument("--skip-pytest", action="store_true")
    p.add_argument("--skip-ruff", action="store_true")
    p.add_argument("--skip-vector", action="store_true")
    p.add_argument("--keep-going", action="store_true")
    p.add_argument("--timeout", type=int, default=600)
    p.set_defaults(func=_cmd_gate)

    p = sub.add_parser("sync", help="同步平台记忆")
    p.add_argument("--root", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--push", action="store_true")
    p.add_argument("--only-rules", action="store_true")
    p.add_argument("--name", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=_cmd_sync)

    p = sub.add_parser("chat", help="omniroute 问答")
    p.add_argument("--root", required=True)
    p.add_argument("prompt")
    p.set_defaults(func=_cmd_chat)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
