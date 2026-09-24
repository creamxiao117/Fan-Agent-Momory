#!/usr/bin/env python3
"""夜间汇总产物 → 本地模型生成人类可读摘要（离线、零 token）。

## 2026-09-24 迁入仓库（P1-1）

原文件在**非版本控制目录**（`D:\\AIwork\\traework\\<hash>\\scripts\\local_summary.py`），
由定时任务 `AgentHub-NightlyConsolidate` 的 .cmd 直接调用 —— 无版本、无评审、无历史。
迁入 `hub-engine/scripts/`，并把**硬编码的 worktree 绝对路径**改为 `--root` 自解析
（原实现把 HUB_ROOT 写死到一个 worktree，worktree 一移就静默扫空/写错位置）。

## 做什么

- 抓 `nightly.log` 最新一段（distill/build-vectors/sleep 原始输出），截断后送本地模型
- 提炼为 3-4 条中文要点，追加写入 `<hub>/.sync/daily_summary.md`（按日期分节）
- 端点按优先级解析（见 `_resolve_target`）：
    1. `cfg.batch_model` + `cfg.gateway_url` —— 原有口径（经 OmniRoute 网关）
    2. `cfg.local_chat.model` + `cfg.local_chat.url` —— 直连本机 LM Studio（离线、零 token）
  回退原因：本机 OmniRoute 无通往 LM Studio 的路由（唯一 offline 路由返回 502），
  而 gateway_url 与引擎共用、不宜为摘要单独改，故 batch_model 未配置时回退本地通道。

用法：
    python -m scripts.local_summary [--root AgentMemoryHub]

幂等：同一日期重复运行会覆盖当天小节。可加入夜间流程末尾。
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 中枢根：由脚本位置推导（hub-engine/scripts/ → parents[2]），不硬编码 worktree 路径
_DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "AgentMemoryHub"
_ENGINE = Path(__file__).resolve().parents[1]

START_MARK = "==== night-consolidate start ===="
MAX_LOG_CHARS = 6000

# 推理模型（如 qwen3.8-27b-fast）先出 reasoning_content 再出 content，
# 阀值必须覆盖两者；取值依据见 `_chat` docstring 的实测对照表。
_MAX_TOKENS = 4096


def _latest_log_segment(log: Path) -> str:
    """截取最新一段夜间 consolidation 日志（含 start 标记到文末）。"""
    if not log.exists():
        return ""
    text = log.read_text(encoding="utf-8", errors="replace")
    last = text.rfind(START_MARK)
    seg = text[last:] if last >= 0 else text[-MAX_LOG_CHARS:]
    return seg.strip()[:MAX_LOG_CHARS]


def _pick_local_model(url: str, preferred: str) -> str:
    """在本地端点 /v1/models 里挑一个真正可用的对话模型（排除嵌入/OCR/重排）。

    必要性：配置里的模型名可能已被卸载或改名（本机 `local_chat.model` 写的是
    `qwen/qwen3.5-9b`，而 LM Studio 里并不存在该模型），此时即便开了 JIT 加载也会
    返回 400 "No models loaded" ⇒ 夜间摘要恒为空。故动态挑一个真实存在的模型；
    「配置名确实存在」时优先用它，保持原有口径。
    """
    import requests

    try:
        base = url.rsplit("/v1/", 1)[0]
        resp = requests.get(base + "/v1/models", timeout=15)
        resp.raise_for_status()
        ids = [str(m.get("id", "")) for m in (resp.json().get("data") or [])]
    except Exception:
        return preferred
    if preferred and preferred in ids:
        return preferred
    non_chat = ("embed", "bge", "ocr", "paddle", "rerank", "whisper")
    chat = [i for i in ids if i and not any(t in i.lower() for t in non_chat)]
    return chat[0] if chat else (ids[0] if ids else preferred)


def _resolve_target(cfg: dict, keys: dict) -> tuple[str, str, str]:
    """解析（模型, 完整 chat/completions 端点, 凭证）—— 返回**候选列表**见下。

    优先 batch_model + gateway_url（原口径）；未配置则回退 local_chat（本机 LM Studio，
    并对模型名做动态发现）。两者都没有时返回空串，由调用方跳过摘要。

    ⚠️ 本函数只给「首选」。**備号候选请用 `_candidates()`** —— 2026-09-24 实测：
    `batch_model: local` 已配置而网关（`127.0.0.1:20128`）未运行，首选恒失败，
    而回退分支因 batch_model 非空而**永远走不到** ⇒ 夜间摘要每晚静默 exit 2（空摘要）。
    """
    api_key = keys.get("default", "")
    model = str(cfg.get("batch_model", "") or "").strip()
    if model:
        gateway = str(cfg.get("gateway_url", "http://127.0.0.1:20128")).strip()
        return model, gateway.rstrip("/") + "/v1/chat/completions", api_key
    lc = cfg.get("local_chat")
    if isinstance(lc, dict) and lc.get("model") and lc.get("url"):
        url = str(lc["url"]).strip()
        return (
            _pick_local_model(url, str(lc["model"]).strip()),
            url,
            str(lc.get("api_key") or "lm-studio"),
        )
    return "", "", api_key


def _candidates(cfg: dict, keys: dict) -> list[tuple[str, str, str]]:
    """返回按优先级排序的端点候选（去重）——首选失败则依次后备。

    修复点：旧逻辑只在 `batch_model` **为空**时才用 local_chat；而本机 `batch_model` 已设
    却指向未运行的网关 ⇒ 摘要每晚为空且无任何提示。改为「首选失败就试下一个」。
    """
    api_key = keys.get("default", "")
    out: list[tuple[str, str, str]] = []

    def _add(m: str, u: str, k: str) -> None:
        if m and u and (m, u, k) not in out:
            out.append((m, u, k))

    gateway = str(cfg.get("gateway_url", "http://127.0.0.1:20128")).strip()
    model = str(cfg.get("batch_model", "") or "").strip()
    if model:
        _add(model, gateway.rstrip("/") + "/v1/chat/completions", api_key)
    lc = cfg.get("local_chat")
    if isinstance(lc, dict) and lc.get("model") and lc.get("url"):
        url = str(lc["url"]).strip()
        _add(
            _pick_local_model(url, str(lc["model"]).strip()),
            url,
            str(lc.get("api_key") or "lm-studio"),
        )
    return out


def _chat(model: str, prompt: str, url: str, api_key: str) -> str:
    """调本机 OpenAI 兼容端点（非流式）返回文本；失败返回空串（不抛错）。

    url 必须是完整的 chat/completions 地址（由候选列表拼好）。

    ⚠️ **`max_tokens` 必须覆盖「推理 + 正文」**（2026-09-24 实测踩坑）：
    本机 `qwen3.8-27b-fast` 是**推理模型**，先出 `reasoning_content`（思考）再出 `content`。
    旧值 400 连思考都不够 ⇒ `content` 恒为空、`finish_reason=length`，而夜间摘要
    **每晚静默失败**（只报“摘要为空”，看不出原因）。实测对比：

    | max_tokens | reasoning 消耗 | content | finish_reason |
    | --: | --: | -- | -- |
    | 400 | ≥400 | **空** | length |
    | 500 | 457 | 3 字 | stop |

    ⇒ 一个“说三个字”就要 457 个推理 token，提炼 6000 字日志所需思考只会更大。
    故上调阀值，并在 content 为空时**打印诊断**（否则此类失败无从排查）。
    """
    import requests

    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                # 见 docstring：推理模型的 reasoning 会先吃掉预算
                "max_tokens": _MAX_TOKENS,
            },
            timeout=600,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        # 带上响应体：LM Studio 的 400 只能靠 body 定位（模型未加载／prompt 过长等）
        detail = ""
        body = getattr(getattr(exc, "response", None), "text", "") or ""
        if body:
            detail = " | body=" + body.strip().replace("\n", " ")[:300]
        print(f"[warn] 端点调用失败 {url}: {type(exc).__name__}: {exc}{detail}")
        return ""
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = str(msg.get("content") or "").strip()
    if not text:
        # 不静默：把“为何空”打出来（推理预算耗尽 / 模型返回异常）
        rt = ((data.get("usage") or {}).get("completion_tokens_details") or {}).get(
            "reasoning_tokens"
        )
        print(
            f"[warn] content 为空：{url} model={model} "
            f"finish_reason={choice.get('finish_reason')} reasoning_tokens={rt} "
            f"reasoning_len={len(str(msg.get('reasoning_content') or ''))} "
            f"max_tokens={_MAX_TOKENS}"
        )
    return text


def _upsert_daily(out: Path, date: str, body: str) -> None:
    """追加/替换当天小节到 daily_summary.md（幂等）。"""
    existing = out.read_text(encoding="utf-8") if out.exists() else ""
    head = f"## {date} 夜间汇总\n"
    if head in existing:
        idx = existing.index(head)
        tail_start = existing.find("\n## ", idx + len(head))
        block = existing[: idx + len(head)] + "\n" + body.strip() + "\n"
        if tail_start >= 0:
            block += existing[tail_start:]
        existing = block
    else:
        existing = existing.rstrip() + "\n\n" + head + "\n" + body.strip() + "\n"
    out.write_text(existing, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="夜间汇总 → 本地模型摘要")
    parser.add_argument("--root", type=Path, default=_DEFAULT_ROOT)
    args = parser.parse_args(argv)
    hub_root = args.root.resolve()

    log = hub_root / ".sync" / "nightly.log"
    out = hub_root / ".sync" / "daily_summary.md"

    seg = _latest_log_segment(log)
    if len(seg) < 80:
        print("无足量夜间日志段，跳过摘要。")
        return 0

    try:
        sys.path.insert(0, str(_ENGINE))
        from common.config import load_engine_config, load_provider_keys

        # 显式传配置绝对路径：消除 CWD 依赖（原实现靠 CWD=hub-engine 才读对）
        cfg = load_engine_config(hub_root / "system" / "config.yaml")
        keys = load_provider_keys(hub_root)
        candidates = _candidates(cfg, keys)
    except Exception:
        print("配置读取失败，跳过摘要。")
        return 1

    if not candidates:
        print("未配置 batch_model 且无可用 local_chat，跳过本地摘要。")
        return 1

    prompt = (
        "你是一个记忆中枢运维助手。下面是昨夜后台维护(distill建卡/build-vectors嵌入/"
        "sleep-consolidate收割)的原始日志。请用中文提炼 3-4 条要点：做了什么、多少量、"
        "有无异常(如嵌入失败/源不可用)。只给要点,不要复述整段日志。\n日志如下:\n" + seg
    )
    today = datetime.date.today().isoformat()  # noqa: DTZ011
    # 依次尝试候选端点：首选（网关）失败就试后备（local_chat）
    body, tried = "", []
    for model, url, api_key in candidates:
        tried.append(f"{url} model={model}")
        body = _chat(model, prompt, url, api_key)
        if body:
            break
    if not body:
        print(
            f"[{today}] 本地摘要为空（候选端点均不可用：{' | '.join(tried)}），跳过写盘。"
        )
        return 2
    _upsert_daily(out, today, body)
    print(f"[{today}] 已更新 {out.name}（{len(body)} 字）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
