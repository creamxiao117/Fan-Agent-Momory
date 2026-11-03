"""MCP 工具处理函数：search/get/index/bootstrap/ingest_candidate（纯函数，便于单测）"""

import html
import json
import re
import time
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
from tools.safe_patch_handler import (
    hub_safe_patch,  # noqa: F401  转发供 H.hub_safe_patch
)
from tools.snippet import extract_snippet
from tools.task_tier import FALLBACK_KIND, resolve_kind, scope_for

DEFAULT_EXCERPT = 200

# ── grade → 注入分层（2026-10-02 M1/Task 15）────────────────────────
# 解决的问题：铁律与"随手记的坑"此前在注入块里**同权**——agent 无法一眼看出
# "哪条必须遵守、哪条只是参考"。分层后：铁律读全文，经验只给一行摘要。
GRADE_ORDER = ("iron", "proven", "domain", "pitfall", "task")
GRADE_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("## 铁律（必读全文）", ("iron",)),
    ("## 已验证方案与领域事实", ("proven", "domain")),
    ("## 相关经验与坑（先看坑）", ("pitfall", "task")),
)
# 分级摘要长度：iron 给足上下文（要照做），其余只给"值不值得点开"的判断依据
EXCERPT_BY_GRADE = {"iron": 400, "proven": 220, "domain": 180, "pitfall": 200, "task": 140}
# ── evidence → 摘要长度加成（2026-11-02，A8 方案 A 落到检索侧）──────────────
# 为何要加成：`grade` 是混合轴，**「随手记的教训」与「已验证的教训」都落 task 档**
# ⇒ 两者拿到的摘录长度相同（140）⇒ 已验证的内容被压成一行，等于白验证。
# ⇒ 现在让**证据强度**参与摘要长度：带实测/T1 证据的卡，摘录更长（能看见验证段）。
#   净效果：grade=task(140) + measured(100) = 240 ⇒ 接近 proven(220)；
#            grade=iron(400) + t1(150) = 550（注入预算 ≤1000 token 估算，仍安全）。
EXCERPT_BY_EVIDENCE = {"t1": 150, "measured": 100}
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
# TASK_KIND_TYPES 于 2026-10-02 迁往 tools/task_tier.py（口径单一事实源）。
# 此处**不再**定义分型知识；既有 import（tests / 文档）请改从 task_tier 取。
# 兼容背书：迁移前取值被 LEGACY_KIND_SCOPE 逐值锁定，
# 见 tests/test_task_tier.py::test_legacy_kind_types_unchanged。


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
    grade = str(card.extra.get("grade") or "").strip()
    evidence = str(card.extra.get("evidence") or "").strip()
    # 摘要长度 = grade 基准 + evidence 加成（证据强的卡值得看更多）
    excerpt_limit = EXCERPT_BY_GRADE.get(grade, DEFAULT_EXCERPT) + EXCERPT_BY_EVIDENCE.get(evidence, 0)
    h = {
        "slug": card.path.stem,
        "rel_path": rel,
        "type": card.type,
        "status": card.status,
        "tags": card.tags,
        "updated": card.updated,
        "channel": channel,
        # grade 透出给消费方（pi 扩展按可信度决定读全文还是一行）
        "grade": grade,
        # evidence 透出：**证据强度**（与 grade 正交的一维，消费方可据此判断可信度）
        "evidence": evidence,
        "excerpt": extract_snippet(card.body, query, excerpt_limit),
    }
    if score is not None:
        h["score"] = round(score, 4)
    if include_body:
        # 可选渐进压缩：>0 时返回压缩后的正文（前端/注入按用途取级），0=原文
        h["body"] = compress_card_text(card.body, int(compress_level)) if compress_level > 0 else card.body
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
        hits.append(_hit(card, channel, score, root, include_body, query, compress_level))
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

    new_fm, n = re.subn(r"^reuse_count:\s*(\d+)", _inc, fm_block, count=1, flags=re.MULTILINE)
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


def hub_get(root: Path, id_: str = "", rel_path: str = "", platform: str = "unknown") -> dict:
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
    task_tier: str = "",
    task_kind: str = "",
    context: str = "",
    platform: str = "unknown",
    top_k: int = 3,
    include_body: bool = False,
    compress_level: int = 0,
) -> dict:
    # 口径唯一来源 = tools/task_tier：task_tier（规范）> task_kind（deprecated 别名）
    # 两者都空 → 等价旧 generic 宽范围（保持迁移前行为）
    requested = (task_tier or task_kind or FALLBACK_KIND).strip().lower()
    # 未知名字回显为 generic（**保持迁移前行为**：旧实现对未知 kind 归一为 "generic"）
    resolved_kind = (
        requested if scope_for(requested) != scope_for(FALLBACK_KIND) or requested == FALLBACK_KIND else FALLBACK_KIND
    )
    tier = resolve_kind(requested)
    kinds = scope_for(requested)
    top_k = max(1, min(10, int(top_k)))
    if tier == "light" or not kinds:
        # light 型 = 不检索：明确返回 skipped，且**不写审计**（避免污染检索统计）
        return {
            "ok": True,
            "task_tier": "light",
            "task_kind": resolved_kind,
            "skipped": True,
            "reason": "light 型不检索（无取数范围）",
            "blocks": [],
            "markdown": "",
            "hit_count": 0,
        }
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
    # 按 **grade** 分层渲染（而不是按子区分组）：agent 需要的顺序是
    # "先别违反铁律 → 再参考已验证方案 → 最后看别人踩过的坑"，不是"先看 rules/ 再看 experience/"。
    flat = [h for b in blocks for h in b["hits"]]
    for title, grades in GRADE_SECTIONS:
        picked = [h for h in flat if (h.get("grade") or "") in grades]
        if not picked:
            continue
        lines.append(title)
        for h in picked:
            tag = f"[{h['grade']}] " if h.get("grade") else ""
            # evidence 标记：**与 grade 正交的一维**，让「已验证的教训」在注入里一眼可辨
            # （否则 grade=task 的卡与随手记无异，白验证了）
            etag = f"[{h['evidence']}] " if h.get("evidence") else ""
            lines.append(f"- {tag}{etag}{h['rel_path']} — {h['excerpt']}")
    if len(lines) == 1:  # 全部 hit 都没有 grade（存量卡未标注）→ 退回平铺，不静默丢内容
        for b in blocks:
            lines.append(f"### {b['kind']}")
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
            "task_tier": tier,
            "task_kind": resolved_kind,
            "types": list(kinds),
            "category_hits": {b["kind"]: len(b["hits"]) for b in blocks},
        },
    )
    return {
        "ok": True,
        "task_tier": tier,
        "task_kind": resolved_kind,
        "hit_count": sum(len(b["hits"]) for b in blocks),
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


def hub_announce(
    root: Path,
    platform: str,
    action: str,
    payload: dict | None = None,
) -> dict:
    """跨平台公告：把事件写到 .sync/announcements.jsonl，供对端启动时读取。

    V1.0 (2026-09-08): T11 Phase 3 —— 双平台协调跨平台通知。
    用法：
        hub_announce(root, "hermes", "ingest_done", {"moved": ["a.md"], "commit": "abc123"})
        hub_announce(root, "trae", "reset_warning", {"reason": "conflict", "sha": "abc"})

    返回：{"ok": bool, "rel_path": ..., "ts": int, "audit_id": str}
    """
    import time

    allow = allowed_platforms(root)
    if platform not in allow:
        raise PolicyError(f"platform {platform!r} not allowed; allowed: {sorted(allow)}")

    aid = audit_id()
    rec = {
        "ts": int(time.time()),
        "platform": platform,
        "action": action[:80],
        "payload": payload or {},
        "audit_id": aid,
    }
    rel = ".sync/announcements.jsonl"
    p_path = root / rel
    p_path.parent.mkdir(parents=True, exist_ok=True)
    with p_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + chr(10))

    append_query_log(
        root,
        {
            "audit_id": aid,
            "action": "announce",
            "platform": platform,
            "ok": True,
            "announce_action": action,
        },
    )
    return {"ok": True, "rel_path": rel, "ts": rec["ts"], "audit_id": aid}


# ── MCP Apps「工具卡片」渲染（2026-11-03，A+ 方案）────────────────────────────
# 为什么不是占位页：原实现只有一句「此工具以文本响应为主…仅供目录展示」——连我们自己都承认它没用，
# 而它是**给人看的**（agent 不需要；agent 侧也已按客户端屏蔽）。
# 现在这张卡回答人真正会问的四件事：做什么 / 怎么调 / 返回什么 / 中枢里现在有什么。
# 性能：宿主**每次工具调用**都会读 resources/read ⇒ 走 TTL 缓存（60 s）+ 只读 INDEX.md。
from pathlib import Path

# 中枢现状缓存：{root: (ts, data)}
_SNAPSHOT_CACHE: dict[str, tuple[float, dict]] = {}
SNAPSHOT_TTL_S = 60.0

TOOL_HINTS: dict[str, dict[str, str]] = {
    "hub_search": {
        "what": "按关键词检索中枢里的卡片（字面 + 语义融合），返回命中卡与摘要。",
        "boundary": "只读。不会写入任何卡。检索结果会记进中枢的调用账本（可追溯）。",
        "returns": "hits[]：slug / grade / evidence / title / excerpt；含 query、命中数、耗时。",
    },
    "hub_get": {
        "what": "按 slug 或路径读**单张卡的全文**（检索结果只给摘要，要全文用这个）。",
        "boundary": "只读。路径必须在中枢内（越界会被拒绝）。",
        "returns": "单张卡的 frontmatter + 正文全文。",
    },
    "hub_index": {
        "what": "浏览中枢的目录结构（各权威区有哪些卡、怎么组织的）。",
        "boundary": "只读。",
        "returns": "目录清单（按区/类型分组）。",
    },
    "hub_bootstrap": {
        "what": "**任务级引导块**：按任务类型（light/code/hub/sync/project）自动检索并组织成一段可直接读入上下文的引导。",
        "boundary": "只读。会按任务型判断取数范围（light 型不检索）。",
        "returns": "markdown 引导块（按「铁律 / 已验证方案 / 相关经验与坑」分层）+ 能力建议。",
    },
    "hub_ingest_candidate": {
        "what": "**候选回写**：把一条结论写进中枢的**草案区**（不直接改权威区）。",
        "boundary": "只写草案区（` .sync/drafts/<平台>_draft/`）；type 只能是 exp/note/project；最终提升由维护者链处理。",
        "returns": "ok / rel_path / slug / audit_id（可回溯）。",
    },
}


def _esc(text: object, limit: int = 400) -> str:
    s = str(text or "")
    if len(s) > limit:
        s = s[:limit] + "…"
    return html.escape(s)


def _hub_snapshot(root: Path) -> dict:
    """中枢现状（卡数 / 目录分布 / 最近入区 / 示例卡），带 TTL 缓存。"""
    key = str(root)
    now = time.time()
    hit = _SNAPSHOT_CACHE.get(key)
    if hit and now - hit[0] < SNAPSHOT_TTL_S:
        return hit[1]

    dirs = ("rules", "methodology", "experience", "blueprints", "projects", "longterm")
    counts: dict[str, int] = {}
    latest = ("", 0.0)
    for d in dirs:
        dd = root / d
        if not dd.is_dir():
            counts[d] = 0
            continue
        files = list(dd.glob("*.md"))
        counts[d] = len(files)
        for f in files:
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if mt > latest[1]:
                latest = (f"{d}/{f.stem}", mt)

    # 示例卡：从 **INDEX-full.md**（逐卡清单，渲染产物）取几行，避免重扫全库
    samples: list[tuple[str, str]] = []
    for idx_name in ("INDEX-full.md", "INDEX.md"):
        idx = root / idx_name
        if not idx.is_file():
            continue
        for line in idx.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"^-\s+`?([a-zA-Z0-9_\-.]+)`?\s{2,}(.+)$", line.rstrip())
            if m:
                samples.append((m.group(1), m.group(2).strip()[:90]))
            if len(samples) >= 4:
                break
        if samples:
            break

    data = {
        "total": sum(counts.values()),
        "counts": counts,
        "latest": latest[0],
        "latest_ts": latest[1],
        "samples": samples,
    }
    _SNAPSHOT_CACHE[key] = (now, data)
    return data


# 参数说明（MCP schema 里没有 description ⇒ 这里给人话版；按 工具名.参数名 查）
PARAM_DOCS: dict[str, str] = {
    "query": "检索词（字面 + 语义）",
    "top_k": "返回条数（1–20）",
    "mode": "检索模式：word（字面，默认）/ char（字形 n-gram）",
    "n": "字形 n-gram 长度（char 模式用）",
    "types": "限定卡类型（rule/methodology/exp/…）",
    "include_body": "是否返回正文全文（默认只给摘要）",
    "compress_level": "正文压缩级 0–5（0=原文）",
    "platform": "调用方平台（记入账本，用于回溯）",
    "id": "卡 slug 或相对路径",
    "rel_path": "卡相对路径（与 id 二选一）",
    "title": "卡标题",
    "body": "卡正文",
    "type": "卡类型：exp / note / project（不能是 rule / methodology）",
    "tags": "标签列表（逗号分隔）",
}


def _schema_rows(schema: dict, tool_name: str = "") -> list[tuple[str, str, str, str]]:
    """inputSchema → [(参数, 类型, 必填, 说明)]（自动生成 ⇒ 不会与实现漂移）。"""
    props = (schema or {}).get("properties") or {}
    required = set((schema or {}).get("required") or [])
    rows = []
    for name, spec in props.items():
        typ = spec.get("type", "?")
        if isinstance(spec.get("enum"), list):
            typ = "|".join(str(x) for x in spec["enum"])
        desc = str(spec.get("description") or "") or PARAM_DOCS.get(name, "")
        rows.append((name, str(typ), "必填" if name in required else "可选", desc[:70]))
    return rows


def render_tool_card(root: Path, tool_name: str, description: str, schema: dict) -> str:
    """渲染一张**人类可读**的工具卡片（HTML）。"""
    safe = "".join(c for c in tool_name if c.isalnum() or c in "_-")
    hint = TOOL_HINTS.get(tool_name, {})
    snap = _hub_snapshot(root)

    params = _schema_rows(schema, tool_name)
    param_html = (
        "".join(
            f"<tr><td><code>{_esc(n)}</code></td><td>{_esc(t)}</td><td>{_esc(req)}</td>"
            f"<td class='dim'>{_esc(d)}</td></tr>"
            for n, t, req, d in params
        )
        or "<tr><td colspan='4' class='dim'>（无参数）</td></tr>"
    )

    counts_html = " · ".join(f"{k} {v}" for k, v in snap["counts"].items())
    samples_html = (
        "".join(
            f"<li><code>{_esc(slug)}</code> — <span class='dim'>{_esc(desc)}</span></li>"
            for slug, desc in snap["samples"]
        )
        or "<li class='dim'>（暂无）</li>"
    )
    latest = snap["latest"] or "（无）"

    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>{_esc(safe)}</title>
<style>
 body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;padding:18px 20px;line-height:1.55;color:#1a1a1a;background:#fff}}
 h1{{font-size:18px;margin:0 0 4px}} h2{{font-size:13px;margin:18px 0 6px;color:#555;font-weight:600;letter-spacing:.02em}}
 .lead{{margin:0 0 10px;color:#333}} .dim{{color:#777;font-size:12px}}
 table{{border-collapse:collapse;width:100%;font-size:13px}}
 td,th{{border-bottom:1px solid #eee;padding:5px 8px;text-align:left;vertical-align:top}}
 code{{background:#f4f4f5;padding:1px 5px;border-radius:4px;font-size:12px}}
 ul{{margin:6px 0 0;padding-left:18px;font-size:13px}}
 .note{{background:#f7f7f8;border-left:3px solid #d0d0d4;padding:8px 12px;margin:12px 0;font-size:13px;color:#444}}
 .kpi{{display:flex;gap:18px;flex-wrap:wrap;margin-top:6px}}
 .kpi b{{display:block;font-size:19px;font-weight:650}}
</style></head>
<body>
<h1>Agent Memory Hub · <code>{_esc(safe)}</code></h1>
<p class="lead">{_esc(description or hint.get("what", ""))}</p>

<div class="note">
  <div><b>它做什么</b>：{_esc(hint.get("what", "—"))}</div>
  <div style="margin-top:6px"><b>边界</b>：{_esc(hint.get("boundary", "—"))}</div>
  <div style="margin-top:6px"><b>返回</b>：{_esc(hint.get("returns", "—"))}</div>
</div>

<h2>参数</h2>
<table><tr><th>参数</th><th>类型</th><th>必填</th><th>说明</th></tr>{param_html}</table>

<h2>中枢现状</h2>
<div class="kpi">
  <div><b>{snap["total"]}</b><span class="dim">张卡</span></div>
  <div><b>{len(snap["samples"])}</b><span class="dim">目录样例</span></div>
  <div><b>{_esc(latest.split("/")[0] if "/" in latest else "—")}</b><span class="dim">最近入区</span></div>
</div>
<p class="dim" style="margin-top:6px">{_esc(counts_html)}</p>

<h2>目录里有什么（样例）</h2>
<ul>{samples_html}</ul>

<p class="dim" style="margin-top:16px">本卡片为<b>人类</b>阅读用（Agent 走文本响应，不需要界面）。
数据取自中枢实测态，页面由 <code>hub-engine/mcp_server.py</code> 渲染。</p>
</body></html>"""


def render_error_card(tool_name: str, message: str) -> str:
    """渲染失败时的兜底卡片（不抛 ⇒ 不影响宿主调用）。"""
    return f"""<!doctype html><html lang="zh"><meta charset="utf-8">
<title>{_esc(tool_name)}</title><body style="font-family:system-ui;padding:16px">
<h2>Agent Memory Hub · {_esc(tool_name)}</h2>
<p class="dim">卡片渲染降级：{_esc(message, 200)}</p>
<p class="dim">工具本身仍可用（文本响应）。</p></body></html>"""


__all__ = ["render_tool_card", "render_error_card", "TOOL_HINTS", "json"]
