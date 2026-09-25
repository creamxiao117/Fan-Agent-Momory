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

# 注入指令块标题标记（与 tools/inject.py 保持一致）；找不到时 Push 退化为文末追加
_INSTRUCTION_KEY = "统一记忆中枢"

# 插入点停止集：按适配器的**条目边界**给（2026-09-19 修 hermes 结构性破坏）
_STOP_HEADS_MD = ("## ", "### ", "§")  # MdSection：条目以 `## ` 开头
_STOP_HEADS_SECT = (
    "# ",
    "## ",
    "### ",
    "§",
)  # § 分隔无标题：卡片块以 body 首行 `# ` 开头

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
                parts.append(f"## {e.title}\n\n{body}".strip() if body else f"## {e.title}")
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


# 平台 → 适配器类 注册表（**适配器覆盖度的唯一事实来源**）。
#
# 谁改这里：新增平台时，同时改 hub.config.yaml 的 platforms 段 + 本表一行。
# 谁读这里：scripts/router_sync.py 的覆盖度检查必须 import SUPPORTED_PLATFORMS，
#           禁止自持硬编码清单（2026-09-19 回归教训：router_sync 自带
#           {"hermes","trae","code","workbuddy"} 死清单，而 mavis/deepseek 早已在
#           hub.config.yaml 登记、记忆文件也早已由中枢同步维护，检查却持续报
#           "未实现适配器" → 纯假告警，白白拉低巡检退出码）。
# 未登记的已配置平台：adapter_for() 走 _DEFAULT_ADAPTER 兜底（不炸历史测试），
#           但 router_sync 会给出 warn 提示，提醒补登记。
ADAPTER_REGISTRY: dict[str, type[Adapter]] = {
    "hermes": SectSeparatedAdapter,  # § 分隔无标题条目
    "trae": MdSectionAdapter,  # ## 分段
    "code": MdSectionAdapter,
    "workbuddy": MdSectionAdapter,
    "mavis": MdSectionAdapter,  # MiniMax Code（2026-09-19 显式登记）
    "deepseek": MdSectionAdapter,  # DeepSeek Harness / DSH（2026-09-19 显式登记）
}

# 已显式登记适配器的平台集合（供 router_sync 等消费方读取）
SUPPORTED_PLATFORMS: frozenset[str] = frozenset(ADAPTER_REGISTRY)

# 兜底适配器：已配置但未显式登记的平台按 ## 分段处理
_DEFAULT_ADAPTER: type[Adapter] = MdSectionAdapter


def adapter_for(platform: str, cfg: HubConfig | None) -> Adapter:
    """按平台选适配器：显式登记优先，未登记则兜底 ## 分段；未在 config 登记则抛错。

    平台已在 hub.config.yaml 登记但未进 ADAPTER_REGISTRY 时**不抛错**——
    platform_bridge 的设计是"登记即可用，默认 ## 分段"，硬抛错会误伤新平台接入。
    覆盖度缺口由 scripts/router_sync.py 以 warn 形式暴露给维护者。
    """
    if cfg is not None and platform not in cfg.platforms:
        raise KeyError(f"未知平台: {platform}（hub.config.yaml 未登记）")
    cls = ADAPTER_REGISTRY.get(platform) or _DEFAULT_ADAPTER
    return cls()


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
            plans.append(("conflict", f"{platform}_{_unique_name(slug, used)}.md", card))
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


def _render_section(adapter: Adapter, title: str, body: str, authority: bool = False) -> str:
    """把一张中枢卡片渲染为平台格式小节；authority=True 标注"中枢权威版"（不覆盖本地旧版）"""
    if authority:
        body = "> 中枢权威版（AgentMemoryHub，未覆盖本地旧版）\n\n" + body
    return adapter.render([Entry(title=title, body=body)])


def _dominant_newline(target: Path) -> str:
    """平台文件的主导换行风格（原样保留，避免 push 把整个文件换行重写）。

    V1.2 (2026-09-19)：原 `target.write_text(new_text)` 用默认 newline=None，
    Windows 下把内存里的 LF 全部翻译成 CRLF ⇒ 单卡 push 让**整文件**换行改写
    （实证 workbuddy：LF 1119 → CRLF 1236，内容纯追加却报全文变化）。
    """
    raw = target.read_bytes()
    crlf = raw.count(b"\r\n")
    return "\r\n" if crlf > (raw.count(b"\n") - crlf) else "\n"


def _is_fence(line: str) -> bool:
    """代码围栏行：``` 或 ~~~ 开头（可带语言标识）。

    V1.3 (2026-09-19)：围栏内的行不参与标题边界判定——卡片示例/脚本里的
    `# ` 注释、`## ` 小标题都不是真标题（实证：跨平台同步纪律卡内的
    bash 示例 `# 1. 入库后先 lint...` 被当成 hermes 卡片边界，推 7state
    越界替换 361 行、删 286 行）。
    """
    return line.lstrip()[:3] in ("```", "~~~")


def _span_by_heading(
    text: str,
    pat_head: re.Pattern[str],
    pat_next: re.Pattern[str],
    pushed_prev: set[str],
) -> str | None:
    """段首 = 匹配 pat_head 的**围栏外**行；段尾 = 下一行匹配 pat_next（或 EOF）；指纹闸校验。

    只有整段指纹 ∈ state['pushed']（= 中枢自己推过的版本）才认，边界猜错即返回 None。
    V1.3 (2026-09-19)：围栏感知——围栏内的行既不充当段首也不充当段尾
    （段体本身完整包含围栏，替换时整段替换不丢围栏内容）。
    """
    lines = text.splitlines(keepends=True)
    fence_now = False  # 外层扫描：当前行是否在围栏内
    for i, ln in enumerate(lines):
        if _is_fence(ln):
            fence_now = not fence_now
            continue
        if fence_now or not pat_head.match(ln.strip()):
            continue
        j = i + 1
        fence_in_span = False  # 段内围栏跟踪：围栏内的 # 注释/标题不充当段尾
        while j < len(lines):
            if _is_fence(lines[j]):
                fence_in_span = not fence_in_span
                j += 1
                continue  # 围栏行本身（含闭合行）始终属于段体
            if not fence_in_span and pat_next.match(lines[j].strip()):
                break
            j += 1
        span = "".join(lines[i:j]).strip()
        if span and fingerprint(span) in pushed_prev:
            return span
    return None


def _stale_heading_span(text: str, body: str, pushed_prev: set[str]) -> str | None:
    """**无标题平台**（hermes § 分隔）的陈旧段定位：段键 = 卡片 body 首行（`# 标题`）。

    V1.2 (2026-09-19)：hermes 条目无 title，`existing_titles` 恒为空集 ⇒ 改卡重推
    永远走"新增"→ 副本累积（实测：同一张卡重推后文件里出现新旧两份正文）。
    段尾取下一个 `# ` 或 `§`——与 `_insert_after_instruction(..., stop_heads)` 的边界一致。
    """
    head = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
    if not head:
        return None
    pat_head = re.compile(r"^" + re.escape(head) + r"$")
    return _span_by_heading(text, pat_head, re.compile(r"^(# |§)"), pushed_prev)


def _stale_span(text: str, title: str, pushed_prev: set[str]) -> str | None:
    """**有标题平台**（MdSection）的陈旧段定位：段键 = `## <卡名>`，段尾 = 下一个卡名式标题。

    为什么不用 adapter.parse 取同名 entry：解析器按 `## ` 切分，卡片内部的子标题
    （## 一句话结论 / ## 关联 …）会被切成独立 entry，按标题只能取到第一小段
    （实测只取到 31 字符）→ 指纹必然对不上。
    """
    pat_title = re.compile(r"^## " + re.escape(title) + r"\s*$")
    pat_next = re.compile(r"^## [a-z0-9][a-z0-9-]*\s*$")
    return _span_by_heading(text, pat_title, pat_next, pushed_prev)


def _insert_after_instruction(text: str, extra: str, stop_heads: tuple[str, ...] = ("## ", "### ", "§")) -> str:
    """在注入指令块之后插入 extra；找不到指令块则追加到文末（不触碰平台原有段落）

    V1.2 (2026-09-19) 修 §-分隔平台的结构性破坏：停止集必须**按适配器的条目边界**给。
    hermes 无标题、卡片块以 body 首行 `# ` 开头，而旧停止集只有 `## `/`§` ⇒ `end`
    会一路越过卡片标题、停在**别的卡片内部的 `## ` 小标题**上，于是每次 push 都把
    上一条卡片「标题留上面、正文漂下面」劈开（实测：连推 5 张卡后出现 14 个"只剩标题"
    碎片，与真实 MEMORY.md 的损坏形态完全一致）。传入含 `# ` 的停止集即可修复。
    """
    lines = text.splitlines(keepends=True)
    start = next(
        (i for i, ln in enumerate(lines) if _INSTRUCTION_KEY in ln and ln.lstrip().startswith(("## ", "### ", "【"))),
        None,
    )
    if start is None:
        base = text.rstrip()
        return (base + "\n\n" + extra + "\n") if base else (extra + "\n")
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith(stop_heads):
        end += 1
    head = "".join(lines[:end]).rstrip()
    tail = "".join(lines[end:]).rstrip()
    out = head + "\n\n" + extra
    if tail:
        out += "\n\n" + tail
    return out + "\n"


def push(
    root: Path,
    platform: str,
    only_rules: bool = False,
    name_filter: str | None = None,
    dry_run: bool = False,
) -> dict:
    """中枢权威卡片 → 平台记忆文件（默认关闭）；外部改动检测到即中止，绝不覆盖本地旧版"""
    root = Path(root)
    stat = {"added": 0, "updated": 0, "replaced": 0, "skipped": 0, "status": "ok"}
    target = _target_path(root, platform)
    if not target.is_file():
        stat["status"] = f"平台记忆文件不存在: {target}"
        return stat
    state = _read_state(root, platform)
    text = target.read_text(encoding="utf-8")

    # 外部改动检测：mtime + 内容哈希 与上次 Push 基线比对（首次无基线则放行）
    baseline = state.get("push")
    if baseline and (baseline.get("hash") != fingerprint(text) or baseline.get("mtime") != target.stat().st_mtime_ns):
        stat["status"] = "平台文件已被外部修改（与上次 Push 基线不符），已中止以免覆盖本地编辑"
        return stat

    cfg = HubConfig.load(root)
    adapter = adapter_for(platform, cfg)
    titleless = isinstance(adapter, SectSeparatedAdapter)  # § 分隔无标题平台：无同名键，走段首行指纹闸
    entries = adapter.parse(text)
    existing_bodies = {e.body.strip() for e in entries if e.body.strip()}
    existing_titles = {e.title for e in entries if e.title}
    pushed_prev = set(state.get("pushed") or [])
    replacements: list[tuple[str, str]] = []

    cards = _authority_cards(root)
    if only_rules:
        cards = [c for c in cards if c.path and c.path.parent.name == "rules"]
    if name_filter:
        cards = [c for c in cards if c.path and c.path.stem == name_filter]
        if not cards:
            # guard：卡名不存在时报错而非静默 0 添加，避免误以为已同步
            stat["status"] = f"not-found: 未找到权威卡片 {name_filter}"
            return stat

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
        stale = None
        if title in existing_titles:
            stale = _stale_span(text, title, pushed_prev)
        elif titleless:
            stale = _stale_heading_span(text, body, pushed_prev)
        if stale:
            replacements.append((stale, block))
            stat["replaced"] = stat.get("replaced", 0) + 1
        elif title in existing_titles:
            stat["updated"] += 1
            blocks.append(_render_section(adapter, title, body, authority=True))
        else:
            stat["added"] += 1
            blocks.append(block)
        pushed_fps.add(fp)

    if dry_run or (not blocks and not replacements):
        return stat
    try:
        with _WriteLock(root):
            new_text = text
            for old_block, new_block in replacements:
                new_text = new_text.replace(old_block, new_block, 1)
            if blocks:
                heads = _STOP_HEADS_SECT if titleless else _STOP_HEADS_MD
                new_text = _insert_after_instruction(new_text, "\n\n".join(blocks), heads)
            with target.open("w", encoding="utf-8", newline=_dominant_newline(target)) as f:
                f.write(new_text)
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
