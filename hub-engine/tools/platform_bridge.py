"""平台记忆 ↔ 中枢双向同步桥

- Entry / Adapter：把平台记忆文件解析为统一条目，或把条目渲染回平台格式
- pull：平台记忆 → .sync/drafts/<platform>_draft/ 候选卡片（复用既有 ingest 管线）
- push：中枢权威卡片 → 平台记忆文件（默认关闭；外部改动检测到即中止，不覆盖本地旧版）
"""

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from common.config import HubConfig
from common.frontmatter import Card, parse_card, today_iso, write_card
from sync import _authority_cards, _find_duplicate, _WriteLock, append_log

# hermes 记忆为 § 分隔纯文本条目；其余平台为 ## Markdown 分段
_SECT_PLATFORMS = {"hermes"}

# 注入指令块标题标记（与 tools/inject.py 保持一致）；找不到时 Push 退化为文末追加
_INSTRUCTION_KEY = "统一记忆中枢"

# Windows 文件名非法字符
_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]+')


@dataclass
class Entry:
    """平台记忆中的一条条目：标题(title) + 正文(body) + 来源(platform/file)"""

    title: str
    body: str
    platform: str = ""
    source_file: str = ""


def fingerprint(text: str) -> str:
    """内容规范化哈希：小写 + 去空白/统一换行 → md5（幂等去重指纹）"""
    norm = " ".join(text.strip().lower().split())
    return hashlib.md5(norm.encode("utf-8")).hexdigest()


class Adapter(ABC):
    """平台记忆文件 ↔ Entry 的双向转换"""

    @abstractmethod
    def parse(self, text: str) -> list[Entry]: ...

    @abstractmethod
    def render(self, entries: list[Entry]) -> str: ...


class MdSectionAdapter(Adapter):
    """## 标题分段（trae/code/workbuddy）：标题行 + 其后正文；无标题前导文本归入空标题条目"""

    def parse(self, text: str) -> list[Entry]:
        entries: list[Entry] = []
        title = ""
        buf: list[str] = []
        for ln in text.splitlines():
            if ln.startswith("## "):
                if buf or title:
                    entries.append(Entry(title=title, body="\n".join(buf).strip()))
                title = ln[3:].strip()
                buf = []
            else:
                buf.append(ln)
        if buf or title:
            entries.append(Entry(title=title, body="\n".join(buf).strip()))
        return [e for e in entries if e.title or e.body]

    def render(self, entries: list[Entry]) -> str:
        parts = []
        for e in entries:
            body = e.body.strip()
            if e.title and e.title != "(无标题)":
                parts.append(
                    f"## {e.title}\n\n{body}".strip() if body else f"## {e.title}"
                )
            elif body:
                parts.append(body)
        return "\n\n".join(parts)


class SectSeparatedAdapter(Adapter):
    """§ 分隔纯文本条目（hermes）：无标题，body 为条目全文"""

    def parse(self, text: str) -> list[Entry]:
        entries: list[Entry] = []
        buf: list[str] = []
        for ln in text.splitlines():
            if ln.strip() == "§":
                body = "\n".join(buf).strip()
                if body:
                    entries.append(Entry(title="", body=body))
                buf = []
            else:
                buf.append(ln)
        body = "\n".join(buf).strip()
        if body:
            entries.append(Entry(title="", body=body))
        return entries

    def render(self, entries: list[Entry]) -> str:
        bodies = [e.body.strip() for e in entries if e.body.strip()]
        return "\n§\n".join(bodies)


def adapter_for(platform: str, cfg: HubConfig | None) -> Adapter:
    """按平台选适配器：hermes → § 分隔，其余 → ## 分段；未登记平台抛错"""
    if cfg is not None and platform not in cfg.platforms:
        raise KeyError(f"未知平台: {platform}（hub.config.yaml 未登记）")
    if platform in _SECT_PLATFORMS:
        return SectSeparatedAdapter()
    return MdSectionAdapter()


def _target_path(root: Path, platform: str) -> Path:
    """解析平台记忆文件路径（唯一来源：hub.config.yaml 的 platforms 段）"""
    p = HubConfig.load(root).platforms.get(platform)
    if not p:
        raise KeyError(f"未知平台: {platform}（hub.config.yaml 未登记）")
    return Path(p["memory_dir"]) / p["target_file"]


def _slug(text: str, limit: int = 24) -> str:
    """文本 → 文件名安全的 slug（非法字符替换为 -，空白/连字符折叠，超长截断）"""
    s = _ILLEGAL.sub("-", text.strip().lower())
    s = re.sub(r"[\s\-]+", "-", s).strip("-")
    return s[:limit].strip("-") or "untitled"


def _unique_name(base: str, used: set[str]) -> str:
    """在 used（存 "name.md"）里取不冲突的文件名基名"""
    name = base
    i = 2
    while f"{name}.md" in used:
        name = f"{base}-{i}"
        i += 1
    used.add(f"{name}.md")
    return name


def _make_card(platform: str, slug: str, body: str) -> Card:
    """Pull 产物卡片：type=exp + 平台名/slug 标签（默认 exp，规则语义可人工改判）"""
    return parse_card(
        f"""---
type: exp
tags:
  - {platform}
  - {slug}
updated: {today_iso()}
status: candidate
reuse_count: 0
---

{body}
"""
    )


def _state_path(root: Path, platform: str) -> Path:
    return root / ".sync" / "state" / f"pulled_{platform}.json"


def _read_state(root: Path, platform: str) -> dict:
    try:
        return json.loads(_state_path(root, platform).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pulled": [], "pushed": [], "push": None}


def _write_state(root: Path, platform: str, state: dict) -> None:
    p = _state_path(root, platform)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def pull(root: Path, platform: str, dry_run: bool = False) -> dict:
    """平台记忆 → .sync/drafts/<platform>_draft/ 候选卡片；重复跳过、语义相近进冲突区"""
    root = Path(root)
    stat = {"pulled": 0, "skipped": 0, "conflicted": 0, "status": "ok"}
    target = _target_path(root, platform)
    if not target.is_file():
        stat["status"] = f"平台记忆文件不存在: {target}"
        return stat
    cfg = HubConfig.load(root)
    entries = adapter_for(platform, cfg).parse(target.read_text(encoding="utf-8"))
    if not entries:
        return stat

    state = _read_state(root, platform)
    done_fps = set(state.get("pulled", []))
    stems = {c.path.stem.lower() for c in _authority_cards(root) if c.path}
    draft_dir = root / ".sync" / "drafts" / f"{platform}_draft"
    conflict_dir = root / ".sync" / "conflicts"
    used: set[str] = set()
    for d in (draft_dir, conflict_dir):
        if d.is_dir():
            used |= {p.name for p in d.glob("*.md")}

    plans: list[tuple[str, str, Card]] = []  # (draft|conflict, 文件名, 卡片)
    for e in entries:
        body = e.body.strip()
        if not body:
            continue
        title = e.title or _slug(body, 12)  # hermes 无标题 → 首 12 字 slug
        slug = _slug(title, 24)
        fp = fingerprint(f"{title}\n{body}")
        if fp in done_fps:
            stat["skipped"] += 1  # 幂等：已沉淀过，不重复建卡
            continue
        if slug in stems:
            stat["skipped"] += 1  # 标题已存在于中枢 → 记 reused
            done_fps.add(fp)
            continue
        card = _make_card(platform, slug, body)
        if _find_duplicate(root, card):
            stat["conflicted"] += 1  # 语义相似 → 进冲突区，不写 draft
            done_fps.add(fp)
            plans.append(
                ("conflict", f"{platform}_{_unique_name(slug, used)}.md", card)
            )
        else:
            stat["pulled"] += 1
            done_fps.add(fp)
            plans.append(("draft", f"{_unique_name(slug, used)}.md", card))

    if dry_run or not plans:
        return stat
    try:
        with _WriteLock(root):
            for kind, name, card in plans:
                dst = (conflict_dir if kind == "conflict" else draft_dir) / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(write_card(card), encoding="utf-8")
            state["pulled"] = sorted(done_fps)
            _write_state(root, platform, state)
            append_log(root, "pull", f"{platform} → {len(plans)} 条候选")
    except RuntimeError as e:
        stat["status"] = str(e)
    return stat


def _render_section(
    adapter: Adapter, title: str, body: str, authority: bool = False
) -> str:
    """把一张中枢卡片渲染为平台格式小节；authority=True 标注"中枢权威版"（不覆盖本地旧版）"""
    if authority:
        body = "> 中枢权威版（AgentMemoryHub，未覆盖本地旧版）\n\n" + body
    return adapter.render([Entry(title=title, body=body)])


def _insert_after_instruction(text: str, extra: str) -> str:
    """在注入指令块之后插入 extra；找不到指令块则追加到文末（不触碰平台原有段落）"""
    lines = text.splitlines(keepends=True)
    start = next(
        (
            i
            for i, ln in enumerate(lines)
            if _INSTRUCTION_KEY in ln and ln.lstrip().startswith(("## ", "### ", "【"))
        ),
        None,
    )
    if start is None:
        base = text.rstrip()
        return (base + "\n\n" + extra + "\n") if base else (extra + "\n")
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith(("## ", "### ", "§")):
        end += 1
    head = "".join(lines[:end]).rstrip()
    tail = "".join(lines[end:]).rstrip()
    out = head + "\n\n" + extra
    if tail:
        out += "\n\n" + tail
    return out + "\n"


def push(
    root: Path, platform: str, only_rules: bool = False, dry_run: bool = False
) -> dict:
    """中枢权威卡片 → 平台记忆文件（默认关闭）；外部改动检测到即中止，绝不覆盖本地旧版"""
    root = Path(root)
    stat = {"added": 0, "updated": 0, "skipped": 0, "status": "ok"}
    target = _target_path(root, platform)
    if not target.is_file():
        stat["status"] = f"平台记忆文件不存在: {target}"
        return stat
    state = _read_state(root, platform)
    text = target.read_text(encoding="utf-8")

    # 外部改动检测：mtime + 内容哈希 与上次 Push 基线比对（首次无基线则放行）
    baseline = state.get("push")
    if baseline and (
        baseline.get("hash") != fingerprint(text)
        or baseline.get("mtime") != target.stat().st_mtime_ns
    ):
        stat["status"] = (
            "平台文件已被外部修改（与上次 Push 基线不符），已中止以免覆盖本地编辑"
        )
        return stat

    cfg = HubConfig.load(root)
    adapter = adapter_for(platform, cfg)
    entries = adapter.parse(text)
    existing_bodies = {e.body.strip() for e in entries if e.body.strip()}
    existing_titles = {e.title for e in entries if e.title}

    cards = _authority_cards(root)
    if only_rules:
        cards = [c for c in cards if c.path and c.path.parent.name == "rules"]

    pushed_fps = set(state.get("pushed", []))
    blocks: list[str] = []
    for card in cards:
        if not card.path:
            continue
        title = card.path.stem
        body = card.body.strip()
        if not body:
            continue
        block = _render_section(adapter, title, body)
        fp = fingerprint(block)
        if fp in pushed_fps or body in existing_bodies:
            stat["skipped"] += 1  # 幂等：已推过或平台已有同内容
            continue
        if title in existing_titles:
            stat["updated"] += 1  # 同标题不同正文 → 追加"中枢权威版"，不覆盖
            blocks.append(_render_section(adapter, title, body, authority=True))
        else:
            stat["added"] += 1
            blocks.append(block)
        pushed_fps.add(fp)

    if dry_run or not blocks:
        return stat
    try:
        with _WriteLock(root):
            new_text = _insert_after_instruction(text, "\n\n".join(blocks))
            target.write_text(new_text, encoding="utf-8")
            state["pushed"] = sorted(pushed_fps)
            state["push"] = {
                "hash": fingerprint(new_text),
                "mtime": target.stat().st_mtime_ns,
            }
            _write_state(root, platform, state)
            append_log(
                root,
                "push",
                f"{platform} ← 中枢（added={stat['added']} updated={stat['updated']}）",
            )
    except RuntimeError as e:
        stat["status"] = str(e)
    return stat
