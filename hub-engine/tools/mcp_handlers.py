"""MCP 工具处理函数：search/get/index/bootstrap/ingest_candidate（纯函数，便于单测）"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from common.frontmatter import Card, today_iso, try_read_card, write_card

from tools.compress import compress_card_text
from tools.mcp_audit import append_query_log, audit_id
from tools.mcp_policy import (
    AUTHORITY_DIRS,
    PolicyError,
    allowed_platforms,
    assert_candidate_type,
    resolve_slug,
)
from tools.retrieve import retrieve_with_meta
from tools.snippet import extract_snippet

DEFAULT_EXCERPT = 200
SUBDIR_BY_TYPE = {
    "rule": "rules",
    "methodology": "methodology",
    "longterm": "longterm",
    "project": "projects",
    "exp": "experience",
    "note": "experience",
    "retro": "retro",
    "blueprint": "blueprints",
}
TASK_KIND_TYPES = {
    "dll": ("rules", "projects"),
    "code": ("rules", "methodology", "projects"),
    "project": ("longterm", "methodology", "blueprints"),
    "debug": ("projects", "experience"),
    "ideation": ("blueprints", "methodology", "experience"),
    "generic": ("rules", "methodology", "longterm", "projects"),
}


def _hit(
    card: Card,
    channel: str,
    score: float | None,
    root: Path,
    include_body: bool,
    query: str = "",
    compress_level: int = 0,
) -> dict:
    rel = card.path.relative_to(root).as_posix()
    h = {
        "slug": card.path.stem,
        "rel_path": rel,
        "type": card.type,
        "status": card.status,
        "tags": card.tags,
        "updated": card.updated,
        "channel": channel,
        "excerpt": extract_snippet(card.body, query, DEFAULT_EXCERPT),
    }
    if score is not None:
        h["score"] = round(score, 4)
    if include_body:
        # 可选渐进压缩：>0 时返回压缩后的正文（前端/注入按用途取级），0=原文
        h["body"] = (
            compress_card_text(card.body, int(compress_level))
            if compress_level > 0
            else card.body
        )
    return h


def hub_search(
    root: Path,
    query: str,
    top_k: int = 5,
    mode: str = "word",
    n: int = 2,
    types: list[str] | None = None,
    include_body: bool = False,
    compress_level: int = 0,
    platform: str = "unknown",
) -> dict:
    top_k = max(1, min(20, int(top_k)))
    channel, scored = retrieve_with_meta(root, query, top_k=top_k, n=n, mode=mode)
    allow = set(types) if types else None
    hits = []
    for card, score in scored:
        if allow is not None and card.type not in allow:
            continue
        hits.append(
            _hit(card, channel, score, root, include_body, query, compress_level)
        )
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "search",
            "platform": platform,
            "ok": True,
            "query": query,
            "channel": channel,
            "top_k": top_k,
            "mode": mode,
            "hit_paths": [h["rel_path"] for h in hits],
            "hit_count": len(hits),
        },
    )
    # A2 命中复用累积：命中卡 reuse_count += 1（按日节流；失败静默，不影响检索返回）
    if hits:
        record_reuse(root, [h["rel_path"] for h in hits])
    return {
        "ok": True,
        "query": query,
        "channel": channel,
        "hits": hits,
        "audit_id": aid,
    }


REUSE_STATE = Path(".sync") / "state" / "reuse_daily.json"


def _load_reuse_state(root: Path) -> dict:
    """读取按日节流状态 {rel_path: YYYY-MM-DD}；缺失/损坏返回空表。"""
    p = root / REUSE_STATE
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _save_reuse_state(root: Path, state: dict) -> None:
    p = root / REUSE_STATE
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError:
        pass


def _bump_reuse(path: Path) -> bool:
    """只改 frontmatter 的 reuse_count 行 +1，尽量保持其余字节不变（最小 diff）。

    无 frontmatter / 无 reuse_count 行 / 读取失败返回 False（不计次）。
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.match(r"(?s)^(---\n.*?)(\n---\n)", text)
    if not m:
        return False
    fm_block = m.group(1)

    def _inc(mo: re.Match) -> str:
        return f"reuse_count: {int(mo.group(1)) + 1}"

    new_fm, n = re.subn(
        r"^reuse_count:\s*(\d+)", _inc, fm_block, count=1, flags=re.MULTILINE
    )
    if n == 0:
        return False  # 无 reuse_count 字段则不计数
    if new_fm == fm_block:
        return True
    try:
        path.write_text(text.replace(fm_block, new_fm, 1), encoding="utf-8")
    except OSError:
        return False
    return True


def record_reuse(root: Path, rel_paths: list[str]) -> dict:
    """A2 命中复用累积：命中卡 reuse_count 元数据 += 1，把"被用到"变为可观测权重。

    - 只对仍存在、非 archived、且 frontmatter 含 reuse_count 字段的卡计数；
    - 按日节流：同卡同本地日只计 1 次（状态落 .sync/state/reuse_daily.json，git-ignored）；
    - 写入置于单写者锁内；锁被占用或缺锁时静默跳过，写回失败不影响检索返回。
    返回 {counted, dup_skipped, archived_skipped}。
    """
    today = today_iso()
    state = _load_reuse_state(root)
    counted = dup = arc = 0
    try:
        from sync import _WriteLock
    except ImportError:  # pragma: no cover - 极端环境退化为无锁
        from contextlib import nullcontext as _WriteLock
    try:
        with _WriteLock(root):
            for rp in rel_paths:
                p = (root / rp).resolve()
                try:
                    if "status: archived" in p.read_text(encoding="utf-8"):
                        arc += 1
                        continue
                except OSError:
                    continue
                if state.get(rp) == today:  # 节流：同日已计
                    dup += 1
                    continue
                if _bump_reuse(p):
                    state[rp] = today
                    counted += 1
            _save_reuse_state(root, state)
    except RuntimeError:
        pass  # 写锁已被占用，静默跳过本次写回
    return {"counted": counted, "dup_skipped": dup, "archived_skipped": arc}


def hub_get(
    root: Path, id_: str = "", rel_path: str = "", platform: str = "unknown"
) -> dict:
    target = rel_path or id_
    if not target:
        return {
            "ok": False,
            "error": "bad_request",
            "message": "id 或 rel_path 至少一个",
        }
    try:
        p = resolve_slug(root, target)
    except PolicyError as e:
        return {"ok": False, "error": e.code, "message": str(e)}
    except FileNotFoundError as e:
        return {"ok": False, "error": "not_found", "message": str(e)}
    card = try_read_card(p)
    if card is None:
        return {"ok": False, "error": "not_found", "message": f"非卡片文件: {target}"}
    hit = _hit(card, "get", None, root, include_body=True)
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "get",
            "platform": platform,
            "ok": True,
            "id": target,
            "hit_paths": [hit["rel_path"]],
            "hit_count": 1,
        },
    )
    return {"ok": True, "card": hit, "audit_id": aid}


def hub_index(
    root: Path,
    types: list[str] | None = None,
    include_markdown: bool = False,
    platform: str = "unknown",
) -> dict:
    allow = set(types) if types else None
    categories = {}
    for sub in AUTHORITY_DIRS:
        if allow is not None and sub not in allow:
            continue
        d = root / sub
        if not d.exists():
            continue
        items = []
        for p in sorted(d.glob("*.md")):
            c = try_read_card(p)
            if c is not None and c.status != "archived":
                items.append(
                    {
                        "slug": p.stem,
                        "rel_path": p.relative_to(root).as_posix(),
                        "type": c.type,
                        "tags": c.tags,
                    }
                )
        categories[sub] = items
    res = {"ok": True, "categories": categories}
    if include_markdown:
        idx = root / "INDEX.md"
        if idx.exists():
            res["index_markdown"] = idx.read_text(encoding="utf-8")[:32768]
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "index",
            "platform": platform,
            "ok": True,
            "types": sorted(allow) if allow else sorted(AUTHORITY_DIRS),
            "category_counts": {k: len(v) for k, v in categories.items()},
        },
    )
    res["audit_id"] = aid
    return res


def hub_bootstrap(
    root: Path,
    task_kind: str,
    context: str = "",
    platform: str = "unknown",
    top_k: int = 3,
    include_body: bool = False,
    compress_level: int = 0,
) -> dict:
    kinds = TASK_KIND_TYPES.get(task_kind)
    if kinds is None:
        task_kind = "generic"
        kinds = TASK_KIND_TYPES["generic"]
    top_k = max(1, min(10, int(top_k)))
    _, scored = retrieve_with_meta(root, context, top_k=20, mode="word")
    blocks = []
    for sub in kinds:
        picked = [h for h in scored if SUBDIR_BY_TYPE.get(h[0].type) == sub]
        blocks.append(
            {
                "kind": sub,
                "hits": [
                    _hit(
                        card,
                        "semantic",
                        score,
                        root,
                        include_body,
                        context,
                        compress_level,
                    )
                    for card, score in picked[:top_k]
                ],
            }
        )
    blocks = [b for b in blocks if b["hits"]]  # 空类别不出现在引导块
    snapshot = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"## 中枢命中（本任务快照 @{snapshot}）"]
    for b in blocks:
        header = f"### {b['kind']}"
        if b["kind"] == "rules":
            header += "（必读全文）"
        lines.append(header)
        for h in b["hits"]:
            lines.append(f"- {h['rel_path']} — {h['excerpt']}")
    markdown = "\n".join(lines)
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "bootstrap",
            "platform": platform,
            "ok": True,
            "task_kind": task_kind,
            "types": list(kinds),
            "category_hits": {b["kind"]: len(b["hits"]) for b in blocks},
        },
    )
    return {
        "ok": True,
        "task_kind": task_kind,
        "snapshot_at": snapshot,
        "blocks": blocks,
        "markdown": markdown,
        "audit_id": aid,
    }


def _slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:40] or "candidate"


def hub_ingest_candidate(
    root: Path,
    platform: str,
    title: str,
    body: str,
    type_: str = "exp",
    tags: list[str] | None = None,
    slug: str = "",
) -> dict:
    if not platform or platform == "unknown":
        return {
            "ok": False,
            "error": "platform_forbidden",
            "message": "platform 必填且不能为 unknown",
        }
    if not title.strip() or not body.strip():
        return {"ok": False, "error": "bad_request", "message": "title 与 body 必填"}
    try:
        assert_candidate_type(type_)
    except PolicyError as e:
        return {"ok": False, "error": e.code, "message": str(e)}
    if platform not in allowed_platforms(root):
        return {
            "ok": False,
            "error": "platform_forbidden",
            "message": f"platform 未授权: {platform}",
        }
    base = slug or _slugify(title)
    draft_dir = root / ".sync" / "drafts" / f"{platform}_draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    final = base
    n = 0
    path = draft_dir / f"{final}.md"
    while path.exists():
        existing = try_read_card(path)
        if existing is not None and existing.body.strip() == body.strip():
            aid = audit_id()
            append_query_log(
                root,
                {
                    "audit_id": aid,
                    "action": "ingest_candidate",
                    "platform": platform,
                    "ok": True,
                    "slug": final,
                    "rel_path": path.relative_to(root).as_posix(),
                    "deduped": True,
                },
            )
            return {
                "ok": True,
                "rel_path": path.relative_to(root).as_posix(),
                "slug": final,
                "deduped": True,
                "audit_id": aid,
            }
        n += 1
        final = f"{base}-{n:02d}"
        path = draft_dir / f"{final}.md"
    card = Card(
        type=type_,
        tags=list(dict.fromkeys([platform] + (tags or []))),
        updated=today_iso(),
        status="candidate",
        body=body.strip(),
        extra={"source": f"mcp/{platform}"},
    )
    path.write_text(write_card(card), encoding="utf-8")
    aid = audit_id()
    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "ingest_candidate",
            "platform": platform,
            "ok": True,
            "slug": final,
            "rel_path": path.relative_to(root).as_posix(),
            "deduped": False,
        },
    )
    return {
        "ok": True,
        "rel_path": path.relative_to(root).as_posix(),
        "slug": final,
        "deduped": False,
        "audit_id": aid,
    }
