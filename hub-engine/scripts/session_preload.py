"""session_preload: 会话预加载轻量版。

在新会话启动时，基于用户初始意图，自动加载 Top-3 相关卡片摘要，
生成会话简报（约 500-800 tokens），供 AI 助手开箱即用。

用法：
    python session_preload.py --hub-root <AgentMemoryHub> --query "用户初始查询" \
        [--top-k 3] [--max-tokens 800] [--json] [--brief-only]

⚠️ 代完成注记（2026-09-02，Hermes 代办 trae work 现场收尾）：
本文件源码灭失（全仓+git 历史无、仅存 8/26 的 cpython-311 .pyc），
由 .pyc 反汇编等价重构：停用词表、value_score 公式、简报模板、
hub_search 调用参数均按 dis 指令流逐项还原，非逐字节复刻。
消费方：flywheel.py session-preload 子命令。
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# hub-engine 目录入 path，复用 MCP 检索入口
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from tools.mcp_handlers import hub_search

    HUB_SEARCH_AVAILABLE = True
except ImportError:
    HUB_SEARCH_AVAILABLE = False

LOCAL_TZ = timezone(timedelta(hours=8))  # Asia/Shanghai

TYPE_LABELS = {
    "rule": "📐 规则",
    "methodology": "🔧 方法论",
    "blueprint": "📐 蓝图",
    "experience": "💡 经验",
    "longterm": "📚 长期记忆",
    "projects": "🗂️ 项目",
    "libs": "📦 库",
    "retro": "🔍 复盘",
}

_STOPWORDS = frozenset(
    {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一",
        "上", "也", "很", "到", "说", "要", "去", "会", "着", "没有", "看", "好",
        "自己", "这", "那", "你", "他", "什么", "怎么", "如何", "为什么", "吗",
    }
)


def _extract_keywords(query: str) -> list[str]:
    """从用户查询中提取关键词。"""
    tokens = re.split(r"[\s,。，、；：！？.!?；:]+", query.lower())
    tokens = [
        t
        for t in tokens
        if t.strip() and t.strip() not in _STOPWORDS and len(t.strip()) > 1
    ]
    if len(tokens) < 3:
        return [query]
    return tokens[:5]


def _get_card_summary(hit: dict, max_length: int = 100) -> str:
    """获取卡片摘要。"""
    excerpt = hit.get("excerpt", "")
    body = hit.get("body", "")
    title = hit.get("slug", "")
    text = excerpt or body[:max_length]
    text = text.replace("\n", " ").strip()
    if len(text) > max_length:
        text = text[:max_length] + "..."
    if not text:
        text = title or ""
    return text


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数（粗略估计：1 token ≈ 4 字符）。"""
    return len(text) // 4


def preload_session(
    hub_root: Path, query: str, top_k: int = 3, max_tokens: int = 800
) -> dict:
    """预加载会话上下文。

    Args:
        hub_root: 中枢根目录
        query: 用户初始查询
        top_k: 加载的卡片数量
        max_tokens: 最大 token 数

    Returns:
        预加载结果，包含会话简报、卡片列表等
    """
    if not HUB_SEARCH_AVAILABLE:
        return {
            "success": False,
            "error": "hub_search 模块不可用，请确认 hub-engine 目录结构",
        }

    keywords = _extract_keywords(query)
    search_result = hub_search(
        root=hub_root,
        query=query,
        top_k=top_k * 2,
        mode="hybrid",
        include_body=False,
        platform="session_preload",
    )
    hits = search_result.get("hits", [])

    scored_hits = []
    for hit in hits:
        score = hit.get("score", 0)
        status = hit.get("status", "")
        card_type = hit.get("type", "")
        reuse_count = hit.get("reuse_count", 0)
        value_score = score * 0.4
        if status == "active":
            value_score += 0.2
        value_score += min(reuse_count * 0.02, 0.2)
        if card_type in ("rule", "methodology"):
            value_score += 0.2
        scored_hits.append((hit, round(value_score, 2)))

    scored_hits.sort(key=lambda x: x[1], reverse=True)
    top_hits = scored_hits[:3]

    cards = []
    for hit, value_score in top_hits:
        cards.append(
            {
                "title": hit.get("slug", "未知"),
                "slug": hit.get("slug", ""),
                "type": hit.get("type", "unknown"),
                "type_label": TYPE_LABELS.get(hit.get("type", ""), "-"),
                "path": hit.get("rel_path", ""),
                "score": hit.get("score", 0),
                "value_score": value_score,
                "summary": _get_card_summary(hit, 100),
                "status": hit.get("status", ""),
                "reuse_count": hit.get("reuse_count", 0),
            }
        )

    brief = _generate_brief(query, keywords, cards, max_tokens)
    return {
        "success": True,
        "query": query,
        "keywords": keywords,
        "brief": brief,
        "cards": cards,
        "total_tokens": _estimate_tokens(brief),
        "hub_root": str(hub_root),
        "generated_at": datetime.now(LOCAL_TZ).isoformat(),
    }


def _generate_brief(
    query: str, keywords: list[str], cards: list[dict], max_tokens: int = 800
) -> str:
    """生成会话简报。"""
    now = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    lines = [
        "<session_brief>",
        "## 🎯 会话简报",
        "",
        f"**检测意图**: {query}",
        f"**关键词**: {', '.join(keywords[:3])}",
        f"**生成时间**: {now}",
        "",
        "---",
        f"### 📋 命中卡片 ({len(cards)} 张)",
        "",
    ]
    for i, c in enumerate(cards, 1):
        lines.append(
            f"**{i}. {c['type_label']} {c['title']}**"
        )
        lines.append(f"- 路径: `{c['path']}`")
        lines.append(
            f"- 相关度: {c['score']:.2f} | 价值分: {c['value_score']:.2f}"
        )
        if c.get("reuse_count", 0) > 0:
            lines.append(f"- 复用次数: {c['reuse_count']}")
        lines.append(f"- 摘要: {c['summary']}")
        lines.append("")

    rule_cards = [c for c in cards if c["type"] == "rule"]
    if rule_cards:
        lines.append("### ⚠️ 相关规则")
        for c in rule_cards:
            lines.append(f"- {c['title']}: {c['summary'][:60]}")
        lines.append("")

    lines.extend(
        [
            "### 💡 建议",
            "- 以上卡片可直接引用，无需重复检索",
            "- 如需详细内容，可使用 `hub_read` 读取完整文件",
            "</session_brief>",
        ]
    )
    brief = "\n".join(lines)
    # 超预算时按行数比例粗截
    if _estimate_tokens(brief) > max_tokens:
        keep = max(1, int(len(lines) * max_tokens / _estimate_tokens(brief)))
        brief = "\n".join(lines[:keep]) + "\n…（已截断）\n</session_brief>"
    return brief


def main() -> int:
    parser = argparse.ArgumentParser(description="会话预加载：生成开箱简报")
    parser.add_argument("--hub-root", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=800)
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    parser.add_argument("--brief-only", action="store_true", help="只输出简报")
    args = parser.parse_args()

    result = preload_session(
        Path(args.hub_root).resolve(), args.query, args.top_k, args.max_tokens
    )
    if not result["success"]:
        print(f"❌ {result.get('error', '未知错误')}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["brief"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
