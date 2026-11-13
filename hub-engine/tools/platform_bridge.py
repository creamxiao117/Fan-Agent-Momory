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
    "code": MdSectionAdapter,
    "workbuddy": MdSectionAdapter,
    "mavis": MdSectionAdapter,  # MiniMax Code（2026-09-19 显式登记）
    "deepseek": MdSectionAdapter,  # DeepSeek Harness / DSH（2026-09-19 显式登记）
    "pi": MdSectionAdapter,  # pi coding agent（2026-10-02 接入；用户级 agent dir/AGENTS.md）
}
# 历史：`trae` 曾在此显式登记（## 分段）。2026-10-05 用户裁定 trae 退役、降为普通工作区，
# 已从 hub.config.yaml 的 platforms 与本注册表同时移除——**两处必须同改**，否则
# router_sync 会报「未登记适配器」假告警（2026-09-19 mavis/deepseek 同类前例）。

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


def _push_guard(target: Path, state: dict, text: str) -> str | None:
    """外部改动检测：mtime + 内容哈希 与上次 Push 基线比对（首次无基线则放行）。

    返回非 None 即应中止（避免覆盖用户在平台记忆文件里的本地编辑）。
    """
    baseline = state.get("push")
    if not baseline:
        return None
    if baseline.get("hash") != fingerprint(text) or baseline.get("mtime") != target.stat().st_mtime_ns:
        return "平台文件已被外部修改（与上次 Push 基线不符），已中止以免覆盖本地编辑"
    return None


def _select_cards(root: Path, only_rules: bool, name_filter: str | None) -> tuple[list, str | None]:
    """挑出待推的权威卡片；`name_filter` 命中不到时报错（不静默 0 添加）"""
    cards = _authority_cards(root)
    if only_rules:
        cards = [c for c in cards if c.path and c.path.parent.name == "rules"]
    if name_filter:
        cards = [c for c in cards if c.path and c.path.stem == name_filter]
        if not cards:
            # guard：卡名不存在时报错而非静默 0 添加，避免误以为已同步
            return [], f"not-found: 未找到权威卡片 {name_filter}"
    return cards, None


# ---------- 指针模式（2026-11-13）------------------------------------------------
# 平台记忆文件是**每轮对话都加载**的输入（hermes: agent/system_prompt.py:529
# ⇒ MEMORY.md 全文进系统提示）⇒ 卡正文全是「每轮固定成本」。
# 指针模式：平台只收「卡名 + 一句话 + 中枢检索路径」，正文留中枢按需检索
# ⇒ 既覆盖全部规则，又把每轮固定成本压到 ~10%。
# ⚠ 与 GR-1 的关系：平台记忆里已有「必须检索中枢」机制 ⇒ 指针是被读的**入口**，不是死文档。

_POINTER_MAX_DESC = 120  # 一句话摘要截断长度（超长会把指针变成第二份正文）


def _pointer_body(card, hub_root: Path) -> str:
    """把一张权威卡压成**指针块**（正文留中枢，平台只留检索线索）。

    块结构：
        > **<标题>** —— <一句话摘要>
        > 中枢路径：`AgentMemoryHub/rules/<slug>.md`（用 hub_search / hub_get 按需取全文）

    ⚠ 摘要取 frontmatter 的 `description`（卡片自述）⇒ 不是从正文截断
    ⇒ 不会把「正文前 120 字」这种半截句子当成摘要。
    """
    path = card.path
    desc = ""
    if path and path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if text:
            # ① frontmatter 的 description（若有）—— 最准
            m = re.search(r"^description:\s*(.+)$", text[:2000], re.M)
            if m:
                desc = m.group(1).strip().strip("'\"")
            if not desc:
                # ② 正文首个 `>` 引用行（中枢卡的惯例 = 一句话导语）
                for line in text.split("\n"):
                    st = line.strip()
                    if st.startswith(">") and not st.startswith(">-"):
                        desc = st.lstrip(">").strip()
                        break
            if not desc:
                # ③ 首个 H1 标题（去掉 `#`）⇒ 至少有点定位信息
                m = re.search(r"^#\s+(.+)$", text, re.M)
                if m:
                    desc = m.group(1).strip()
    if len(desc) > _POINTER_MAX_DESC:
        desc = desc[: _POINTER_MAX_DESC - 1].rstrip() + "…"

    slug = path.stem if path else "?"
    rel = path.relative_to(hub_root.parent).as_posix() if path else "?"
    title = desc or slug
    return f"> **{slug}** —— {title}\n> 中枢路径：`{rel}`（用 `hub_search` / `hub_get` 按需取全文）"


# ⚑ 清单区（2026-11-13，迭代2）：指针模式下，平台记忆里的**全部**规则条目
#   收进**一个**可整体替换的区块 ⇒ 推送时按清单重算并**覆盖**旧清单
#   （而不是逐卡追加 ⇒ 逐卡追加会让清单与实际推送集合漂移、且重推时新旧两份并存）。
#
#   区块头（哨兵）：固定文本 ⇒ 两端都能精确定位 ⇒ 幂等覆盖。
_POINTER_INDEX_HEAD = "【中枢规则指针清单】"
# ⚑⚑ **托管区哨兵**（2026-11-13，迭代4）：指针模式下，中枢管辖的全部内容
#   （清单区 + 内联白名单卡 + 旧全文块清理）收进**一个**哨兵包围的区块。
#
#   为什么必须这样（迭代 2/3 的实测教训）：
#     · 逐块定位（`## <slug>` / 中文标题）在**交错**结构里必然不稳
#       （实测 workbuddy：`## global-rules` 与 `# 全局规则` 交错 ⇒ 替换互吞 ⇒ 不幂等）。
#     · 边界靠「猜」（下一个标题 / 空行）⇒ 越界吞掉别的内容（实测吞 2,364 字符）。
#   ⇒ 唯一可靠口径：**哨兵包围** ⇒ 边界由中枢自己的标记决定 ⇒ 天然幂等。
_MANAGED_BEGIN = "<!-- hub-managed:begin -->"
_MANAGED_END = "<!-- hub-managed:end -->"
# ⚑ 永远**内联全文**的规则卡（不进指针清单、也不删旧全文块）。
#   理由：这些是**每轮都该生效**的铁律（GR-1~GR-4）⇒ 指针化会削弱合规性。
_KEEP_INLINE_RULES = {"global-rules"}
_POINTER_INDEX_HEAD_MD = "## 中枢规则指针清单"


def _pointer_index_body(cards, hub_root: Path) -> str:
    """生成**指针清单区**正文（含哨兵头 + 全部卡的指针行）。

    ⚠ 只列**本次推送集合**的卡 ⇒ 清单与实际落地始终一致（不会多、不会少）。
    """
    lines = [
        _POINTER_INDEX_HEAD,
        "（下列规则的**全文在中枢**⇒ 执行前用 `hub_search` / `hub_get` 按需检索，不要凭印象执行；",
        " `global-rules`（GR-1~GR-4）已内联 ⇒ 直接可读）",
        "",
    ]
    for card in cards:
        if not card.path:
            continue
        # ⚠ `global-rules` 永远内联 ⇒ 不重复出现在清单里（避免两份口径）
        if card.path.stem in _KEEP_INLINE_RULES:
            continue
        body = _pointer_body(card, hub_root)
        if body:
            lines.append(body)
    return "\n".join(lines)


def _title_block_line_ranges(text: str, titles: set[str]) -> list[tuple[int, int]]:
    """按**标题文本**定位旧块（行区间），兼容两种形态：
      · slug 式：`## global-rules`
      · 中文标题式：`# 全局规则（GR-1 ~ GR-4）`（hermes 平台推 `global-rules` 后的形态）

    ⚠ 同名标题可能**多处**（实测 workbuddy 同时有 `## global-rules` 与
      `# 全局规则（GR-1 ~ GR-4）` 两份）⇒ 返回**全部**命中区间，
      由调用方逐个替换（否则旧份残留 ⇒ 越推越臃肿）。
    """
    lines = text.splitlines(keepends=True)
    hits: list[tuple[int, int]] = []
    pat = re.compile(r"^#{1,3}\s+(.+?)\s*$")
    for i, ln in enumerate(lines):
        m = pat.match(ln.strip())
        if not m:
            continue
        head = m.group(1).strip()
        if head not in titles:
            continue
        j = i + 1
        while j < len(lines):
            st = lines[j].strip()
            # ⚠⚠ 清单区哨兵 ⇒ **本块到此结束**
            #   （实测 workbuddy 的清单区**落在 global-rules 全文块内部**
            #    ⇒ 白名单替换整块时会把清单区一起清掉 ⇒ 推送后清单消失 ⇒ 规则指针全丢）
            if st.startswith(_POINTER_INDEX_HEAD) or st.startswith(_POINTER_INDEX_HEAD_MD):
                break
            nxt = pat.match(st)
            if nxt and nxt.group(1).strip() in titles:
                break
            # ⚠ 下一个**卡名式**标题（`## global-rules`）也算边界
            #   ⇒ 否则中文标题块（`# 全局规则（GR-1 ~ GR-4）`）的范围会跨过它
            #   ⇒ 旧块没被清掉 ⇒ **两份 global-rules 并存**（实测 code/workbuddy 各 2 份）。
            if re.match(r"^#{1,3}\s+[a-z0-9][a-z0-9\-]*\s*$", st):
                break
            j += 1
        hits.append((i, j))
    return hits


def _slug_block_line_ranges(text: str, slugs: set[str]) -> list[tuple[int, int]]:
    """找出平台文件里 `## <slug>` 形态的**规则卡全文块**的行区间。

    ⚠ 只认**顶层** `## <slug>`（slug 是 `a-z0-9-` 形态的**卡名**）⇒
      卡片**内部**的子标题（`## 一句话结论` / `## 关联` …）**不**误伤
      （实测 code 平台一张卡内部就有 20+ 个 `## ` 子标题 ⇒ 按标题一刀切会碎成一地）。
    """
    lines = text.splitlines(keepends=True)
    hits: list[tuple[int, int]] = []
    pat = re.compile(r"^## ([a-z0-9][a-z0-9\-]*)\s*$")
    # ⚠ 块结束边界 = **下一个卡名式标题**（`## <slug>`）——
    #   · 不能用「任何 `## `」：卡**内部**的中文子标题（`## 关键语义`）会截断块
    #     ⇒ 块尾正文变成孤儿（实测：块删了但体量反而涨 1,022 字符）。
    #   · 不能用「卡内子标题也算块内」而不管下一个卡名：那样会把**下一张卡**
    #     一起吞掉（实测 `## 关键语义` 被误删）。
    #   ⇒ 正确口径：**卡名式标题之间**才算同一张卡（中枢推的卡就是 `## <slug>` 形态，
    #     卡内子标题是 `## 中文标题`，两者可区分）。
    pat_any = re.compile(r"^## ([a-z0-9][a-z0-9\-]*)\s*$")
    for i, ln in enumerate(lines):
        m = pat.match(ln.strip())
        if not m or m.group(1) not in slugs:
            continue
        j = i + 1
        while j < len(lines):
            st = lines[j].strip()
            # ⚠ 清单区哨兵 ⇒ 本块结束（否则旧全文块清理会把清单区一起删掉）
            if st.startswith(_POINTER_INDEX_HEAD) or st.startswith(_POINTER_INDEX_HEAD_MD):
                break
            if pat_any.match(st):  # 下一个卡名式标题 ⇒ 本块结束
                break
            j += 1
        hits.append((i, j))
    return hits


def _pointer_index_line_range(text: str) -> tuple[int, int] | None:
    """定位清单区在 `text` 中的**行区间** `[start, end)`（含）。

    ⚠ 为什么用**行区间**而不是字符串 span：
      清单区常被 `_insert_after_instruction` 插在某个 § 条目**内部**
      （实测：插在 §[11] 中枢规则块内，后面紧跟 global-rules 全文）
      ⇒ 任何「按分隔符/空行猜边界」的做法都会**越界吞掉别的内容**
      （实测两次：吞掉 global-rules 全文 2,364 字符 / 吞掉 global-rules 标题行）。
      ⇒ 唯一可靠口径：**清单区 = 哨兵行 + 连续的 `> ` 指针行**（消费到即止），
        边界由**内容**决定，不由分隔符决定。
    """
    lines = text.splitlines(keepends=True)
    start = None
    for i, ln in enumerate(lines):
        st = ln.strip()
        # ⚠ 兼容两种渲染形态：`§` 平台是裸文本行、`## ` 平台是 `## 【中枢规则指针清单】`
        #   ⇒ 定位必须容忍标题前缀（否则起点算错 ⇒ 替换时把上一行也换掉 ⇒ 重复）。
        if st in (_POINTER_INDEX_HEAD, _POINTER_INDEX_HEAD_MD):
            start = i
            break
        if st.endswith(_POINTER_INDEX_HEAD) and st.startswith("#"):
            start = i
            break
    if start is None:
        return None
    end = start + 1
    seen_pointer = False
    while end < len(lines):
        st = lines[end].strip()
        if st.startswith(">"):
            seen_pointer = True
            end += 1
            continue
        if not seen_pointer:
            end += 1  # 说明行 / 空行 ⇒ 清单头部
            continue
        break  # 指针区结束
    return start, end


def _managed_zone_span(text: str) -> tuple[int, int] | None:
    """定位托管区（哨兵包围）的**行区间** `[start, end)`。

    找不到 ⇒ None（⇒ 首次推送时新建）。
    """
    lines = text.splitlines(keepends=True)
    b = e = None
    for i, ln in enumerate(lines):
        st = ln.strip()
        if st == _MANAGED_BEGIN and b is None:
            b = i
        elif st == _MANAGED_END and b is not None:
            e = i + 1
            break
    if b is None or e is None:
        return None
    return b, e


def _managed_zone_content(
    adapter,
    index_cards: list,
    hub_root: Path,
    keep_inline_cards: list,
    old_full_slugs: set[str],
    text: str,
    titleless: bool,
) -> str:
    """生成**托管区**内容（哨兵 + 清单区 + 内联白名单卡）。

    ⚠ 托管区**完全重建**（不增量）⇒ 内容只取决于中枢当前状态 ⇒ **天然幂等**。
    ⚠ 旧全文块（`## <slug>` 形态）**不**放进托管区，而是在托管区**之外**清理
      （旧块可能在文件任意位置；放进托管区会让文件结构错乱）。
    """
    parts: list[str] = [_MANAGED_BEGIN + "\n"]

    # ① 内联白名单卡（global-rules 等）—— 铁律必须常驻
    for card in keep_inline_cards:
        if not card.path:
            continue
        body = card.body.strip()
        if not body:
            continue
        blk = _render_section(adapter, card.path.stem, body)
        if not blk.endswith("\n"):
            blk += "\n"
        parts.append(blk)

    # ② 指针清单区
    index_body = _pointer_index_body(index_cards, hub_root)
    if index_body:
        blk = _render_section(adapter, _POINTER_INDEX_HEAD, index_body)
        if not blk.endswith("\n"):
            blk += "\n"
        parts.append(blk)

    parts.append(_MANAGED_END + "\n")
    return "".join(parts)


def _push_mode(cfg, platform: str) -> str:
    """平台记忆推送模式：`pointer`（只推指针）/ `full`（推全文，默认）。

    ⚠ 默认 `full` ⇒ **行为逐字不变**（向后兼容；老平台不受影响）。
    """
    meta = (getattr(cfg, "platforms", None) or {}).get(platform) or {}
    mode = str(meta.get("memory_push_mode") or "full").strip().lower()
    if mode not in ("full", "pointer"):
        raise ValueError(f"平台 {platform} 的 memory_push_mode 非法：{mode!r}（须为 full 或 pointer）")
    return mode


def _plan_push_pointer(
    adapter,
    cards: list,
    text: str,
    stat: dict,
    hub_root: Path,
    index_cards: list | None,
    titleless: bool,
) -> tuple[list[str], list[tuple], set[str]]:
    """指针模式的推送规划（**托管区**方案，迭代4）。

    托管区 = 中枢管辖内容的**哨兵包围区块**（内联白名单卡 + 指针清单区）⇒
    边界由哨兵决定 ⇒ **完全重建** ⇒ 天然幂等（推 N 次内容逐字符相同）。
    """
    blocks: list[str] = []
    replacements: list[tuple] = []
    pushed_fps: set[str] = set()
    if hub_root is None:
        return blocks, replacements, pushed_fps

    # ⚠⚠ 清单区必须基于**全量规则卡**生成，**不能**用本次推送集合：
    #   `--name xxx` 只推一张时，若清单按推送集合重算 ⇒ 清单只剩那张卡
    #   ⇒ **规则清单丢失**（实测 7,457 → 5,186，少 2,271 字符）。
    if index_cards is None:
        index_cards = cards

    keep_inline = [c for c in index_cards if c.path and c.path.stem in _KEEP_INLINE_RULES]

    # ① 清理**托管区之外**的旧全文块
    #    （指针模式切换前推的全文块；否则「清单区 + 旧全文」并存 ⇒ 臃肿 + 两套口径打架）
    zone_rng = _managed_zone_span(text)
    slugs = {c.path.stem for c in index_cards if c.path}
    hits = list(_slug_block_line_ranges(text, slugs))
    # ⚠ 白名单卡的中文标题形态旧块也要清（hermes/workbuddy 实测有独立的
    #   `# 全局规则（GR-1 ~ GR-4）` 块）⇒ **总是**按标题形态定位；
    #   与 slug 块**重叠**的问题由后面的「区间合并」解决。
    for c in index_cards:
        if not c.path or c.path.stem not in _KEEP_INLINE_RULES:
            continue
        m = re.search(r"^#\s+(.+)$", c.body, re.M)
        if m:
            hits.extend(_title_block_line_ranges(text, {m.group(1).strip()}))
    for rng in hits:
        # 跳过托管区内部（托管区整体会被替换 ⇒ 内部无需逐块清）
        if zone_rng and rng[0] >= zone_rng[0] and rng[1] <= zone_rng[1]:
            continue
        replacements.append((rng, ""))
        stat["replaced"] = stat.get("replaced", 0) + 1

    # ⚠⚠ **合并重叠区间**后再替换：slug 块与其内部的中文标题块会**重叠**
    #   ⇒ 直接同时替换会让行号相互错位 ⇒ 删不干净
    #   （实测 workbuddy：区外仍残留 1 份 `# 全局规则（GR-1 ~ GR-4）`）。
    replacements[:] = _merge_overlapping(replacements)

    # ② 重建托管区（内联白名单卡 + 指针清单区）
    zone = _managed_zone_content(adapter, index_cards, hub_root, keep_inline, slugs, text, titleless)
    rng = _managed_zone_span(text)
    if rng is not None:
        lines = text.splitlines(keepends=True)
        old_zone = "".join(lines[rng[0] : rng[1]])
        if old_zone == zone:
            stat["skipped"] += 1
        else:
            replacements.append((rng, zone))
            stat["replaced"] = stat.get("replaced", 0) + 1
    else:
        stat["added"] += 1
        blocks.append(zone)
    pushed_fps.add(fingerprint(zone))
    return blocks, replacements, pushed_fps


def _merge_overlapping(replacements: list[tuple]) -> list[tuple]:
    """把**重叠**的行区间合并（按起点排序，前区间吸收后区间）。

    ⚠ 不合并 ⇒ 区间替换时行号相互错位 ⇒ 删不干净
    （实测 workbuddy：区外残留 1 份 `# 全局规则（GR-1 ~ GR-4）`）。
    """
    if len(replacements) <= 1:
        return replacements
    merged: list[tuple] = []
    for r in sorted(replacements, key=lambda x: x[0][0] if isinstance(x[0], tuple) else 0):
        if isinstance(r[0], tuple) and merged:
            prev = merged[-1][0]
            if r[0][0] < prev[1]:
                merged[-1] = ((prev[0], max(prev[1], r[0][1])), r[1])
                continue
        merged.append(r)
    return merged


def _plan_push(
    adapter,
    cards: list,
    text: str,
    state: dict,
    titleless: bool,
    existing_bodies: set[str],
    existing_titles: set[str],
    stat: dict,
    mode: str = "full",
    hub_root: Path | None = None,
    index_cards: list | None = None,
) -> tuple[list[str], list[tuple[str, str]], set[str]]:
    """规划本轮推送：返回 (追加块, 原地替换对, 本轮全部指纹)，并就地累加 stat 计数。

    幂等：已推过（指纹命中）或平台已有同内容 → skipped，不重复写。
    """
    pushed_prev = set(state.get("pushed") or [])
    pushed_fps = set(state.get("pushed", []))
    blocks: list[str] = []
    replacements: list[tuple[str, str]] = []
    if mode == "pointer":
        # ⚑⚑ 指针模式（迭代4）：**托管区**方案。
        #   中枢管辖的全部内容（内联白名单卡 + 指针清单区）收进**一个**哨兵包围的区块
        #   ⇒ 边界由中枢自己的标记决定 ⇒ **完全重建** ⇒ 天然幂等。
        #
        #   迭代 2/3 的实测教训（为什么不能逐块定位）：
        #     · 交错结构下逐块定位必然互吞（workbuddy：`## global-rules` 与
        #       `# 全局规则` 交错 ⇒ 替换互吞 ⇒ 推 3 次体量 11,556 → 12,887 → 9,157）。
        #     · 靠「猜边界」（下一个标题 / 空行）会越界吞掉别的内容（实测吞 2,364 字符）。
        return _plan_push_pointer(adapter, cards, text, stat, hub_root, index_cards, titleless)

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
    return blocks, replacements, pushed_fps


def _compose_text(
    text: str,
    blocks: list[str],
    replacements: list[tuple[str, str]],
    titleless: bool,
) -> str:
    """把本轮推送**投影**成新的平台文件文本（**不落盘**）。

    `_apply_push` 与体量闸共用同一段合成逻辑 ⇒ 闸算出来的体量 = 真会写下去的体量
    （两处各写一份 ⇒ 闸算 A、写的却是 B ⇒ 闸形同虚设）。
    """
    new_text = text
    # ⚑ 统一成**行区间**替换，并按起始行**倒序**应用
    #   （倒序 ⇒ 后面的替换不影响前面的行号 ⇒ 多处替换互不干扰）。
    #   字符串形态的旧替换先转成行区间（一次性转换，避免混用两套语义）。
    _lines = new_text.splitlines(keepends=True)
    _edits: list[tuple[int, int, str]] = []
    for old_block, new_block in replacements:
        if isinstance(old_block, tuple):
            _edits.append((old_block[0], old_block[1], new_block))
            continue
        # 字符串形态 ⇒ 定位首次出现 ⇒ 换成行区间
        _pos = new_text.find(old_block)
        if _pos < 0:
            continue
        _s = new_text.count("\n", 0, _pos)
        _e = _s + old_block.count("\n") + (0 if old_block.endswith("\n") else 1)
        _edits.append((_s, _e, new_block))
    for _s, _e, _new in sorted(_edits, key=lambda x: x[0], reverse=True):
        _lines = new_text.splitlines(keepends=True)
        new_text = "".join(_lines[:_s]) + _new + "".join(_lines[_e:])
    if blocks:
        heads = _STOP_HEADS_SECT if titleless else _STOP_HEADS_MD
        new_text = _insert_after_instruction(new_text, "\n\n".join(blocks), heads)
    return new_text


def _parse_char_budget(raw, field: str, platform: str) -> int:
    """把 hub.config.yaml 的体量字段（字符数）解析成正整数；非法 ⇒ 抛错（fail-closed）。

    两个字段共用同一套解析规则 ⇒ 「声明了但非法」的行为完全一致（不因字段名而分叉）：
      - `memory_char_limit`     = 消费端加载上限（超限 ⇒ **拒绝写入**）
      - `memory_char_warn_limit` = hub 侧告警线（超限 ⇒ **只报不拦**）
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise ValueError(f"平台 {platform} 的 {field} 非法：{raw!r}（须为正整数）")
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError(f"平台 {platform} 的 {field} 非法：{raw!r}（须为正整数）") from None
    if value <= 0:
        raise ValueError(f"平台 {platform} 的 {field} 非法：{raw!r}（须为正整数）")
    return value


def _platform_budget(cfg, platform: str) -> int | None:
    """平台声明的**记忆文件体量上限**（字符数）；未声明 ⇒ None（不设闸）。

    ⚑ 这个数字必须等于**消费端自己的加载上限**（hermes = `memory_char_limit`）⇒
    中枢侧与消费侧说的是同一个数，不会各说各话。

    ⚑ **声明了但非法 ⇒ 抛错（fail-closed）**，不得静默当成「未声明」：
    误写成 `"16k"` / `-5` / `0` 若被当成「不设闸」，就是**本闸要根治的同一类
    「生产端零信号」**（悄悄失效的闸比没有闸更坏）⇒ 调用方必须据此**拒绝写入**。

    ⚑ 与 `memory_char_warn_limit`（告警线）的差别：**本字段超限 ⇒ 阻断写入**，
    因为它代表**消费端契约**（消费端超限后会拒绝一切新增/替换写入 ⇒ 推了也白推）。
    消费端上限**无法核验**的平台（mavis / code / workbuddy / deepseek / pi）
    **不得声明本字段**，只能声明告警线。
    """
    meta = (getattr(cfg, "platforms", None) or {}).get(platform) or {}
    raw = meta.get("memory_char_limit")
    if raw is None or raw == "":
        return None
    return _parse_char_budget(raw, "memory_char_limit", platform)


def _platform_warn_budget(cfg, platform: str) -> int | None:
    """平台声明的**告警预算**（hub 侧自设的告警线，字符数）；未声明 ⇒ None（不告警）。

    ⚑ **与 `memory_char_limit` 的语义差别（务必分清）**：
      - `memory_char_limit`     = **消费端自己的加载上限** ⇒ 超限 ⇒ **拒绝写入**（阻断）。
        只有能**核验消费端上限**的平台才能声明它（hermes = 其 config.yaml 的 `memory_char_limit`）。
      - `memory_char_warn_limit` = **hub 侧自设的预算**（告警线）⇒ 超限 ⇒ **照常写入**，
        但必须留下**可见的告警信号**（`push()` 返回的 `stat["warnings"]` + 中枢日志
        `retro/log.md` 留一行）。它是「提前知道在长胖」的**探针**，**不是**消费端限制。

    ⇒ 适用对象：**消费端上限无法核验**的平台（mavis / code / workbuddy / deepseek / pi）。
    实测 2026-11-13：mavis 平台记忆文件 `~/.mavis/memories/MEMORY.md`（84,510 B）在
    MiniMax Code 运行时（app.asar）里**没有任何读取路径**（`memories` 字面量只出现在
    Beta managed-agent 的 `./memory/memories` 工具与 Anthropic SDK 的 memoryStores 里；
    运行时自己的记忆是 `~/.mavis/memory/user.md` 与 `~/.mavis/agents/<name>/memory/MEMORY.md`）
    ⇒ 该文件本质是**中枢的镜像**（只有中枢自己 push/pull 读写）⇒ 没有消费端上限可核验
    ⇒ **不能声明** `memory_char_limit`，只能声明告警线。

    ⚑ **声明了但非法 ⇒ 抛错（fail-closed）**，不得静默当成「未声明」：
    非法值 = 探针**悄悄失效** = 生产端零信号 = 与 `memory_char_limit` 同一类事故
    ⇒ 调用方据此拒绝写入并要求修配置。
    （注意：**非法**与**超限**是两件事——超限只是提醒、照常写；非法是配置错误、停下修。）
    """
    meta = (getattr(cfg, "platforms", None) or {}).get(platform) or {}
    raw = meta.get("memory_char_warn_limit")
    if raw is None or raw == "":
        return None
    return _parse_char_budget(raw, "memory_char_warn_limit", platform)


def _log_warnings(root: Path, warnings: list[dict]) -> None:
    """把告警写进中枢日志（retro/log.md）——stdout 会被吞，**必须留痕**。"""
    for w in warnings:
        append_log(root, "push", str(w.get("message", w)))


def _apply_push(
    root: Path,
    platform: str,
    target: Path,
    state: dict,
    text: str,
    blocks: list[str],
    replacements: list[tuple[str, str]],
    titleless: bool,
    pushed_fps: set[str],
    stat: dict,
) -> str | None:
    """写盘 + 更新状态 + 记日志（单写者锁内）；返回错误信息或 None"""
    try:
        with _WriteLock(root):
            new_text = _compose_text(text, blocks, replacements, titleless)
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
        return str(e)
    return None


def _check_budget_and_warn(
    cfg,
    platform: str,
    root: Path,
    target: Path,
    text: str,
    blocks: list,
    replacements: list,
    titleless: bool,
    stat: dict,
    dry_run: bool,
) -> str | None:
    """体量闸（阻断）+ 告警预算（只报不拦）；返回**拒绝原因**或 None（通过）。

    ⚑ 体量闸（2026-11-12）：平台记忆文件是**消费端**的输入，消费端有自己的加载上限
    （hermes `memory_char_limit`）⇒ 超限后消费端会**拒绝一切新增/替换写入**，
    而 push 本身照样报「成功」⇒ 生产端不给任何信号，故必须在**写之前**按消费端上限核对。
    口径：按**推后文件长度**核对（文件长度 ≥ 消费端的条目计数 ⇒ 保守方向：宁严勿松）。
    """
    try:
        budget = _platform_budget(cfg, platform)
    except ValueError as exc:
        stat["status"] = (
            f"拒绝写入：{exc} ⇒ 配置错误不得静默当成「不设闸」（闸悄悄失效 = 生产端零信号 = 本闸要根治的那类事故）"
        )
        stat["added"] = 0
        stat["updated"] = 0
        stat["replaced"] = 0
        return stat["status"]
    if budget is not None and (blocks or replacements):
        projected = _compose_text(text, blocks, replacements, titleless)
        if len(projected) > budget:
            stat["status"] = (
                f"拒绝写入：推后体量 {len(projected)} 字符 > 平台记忆上限 {budget}"
                f"（= 消费端加载上限；超限后消费端会拒绝一切新增/替换写入）"
                f" ⇒ 请改推更小的卡片，或先瘦身 {target.name}（中枢暂无「只推指针」模式）"
            )
            stat["added"] = 0
            stat["updated"] = 0
            stat["replaced"] = 0
            return stat["status"]

    # ⚑ 告警预算（2026-11-13）：**消费端上限无法核验**的平台（mavis / code / workbuddy /
    # deepseek / pi）没有可声明的 `memory_char_limit` ⇒ 平台记忆文件会**无信号地长胖**
    # （实测 mavis MEMORY.md 已 84,510 B，且此前**零告警** ⇒ 涨到多大都不会有人知道）。
    # ⇒ 用 hub 侧自设的**告警线**补上信号：**只报不拦**（超线照常写入），
    #    但 `stat["warnings"]` 出结构化告警 + 中枢日志 retro/log.md 留一行（stdout 会被吞）。
    # 优先级：**limit 阻断优先**（上面已 return）⇒ warn 只在「不阻断」的路径上产生。
    try:
        warn_budget = _platform_warn_budget(cfg, platform)
    except ValueError as exc:
        stat["status"] = (
            f"拒绝写入：{exc} ⇒ 告警线配置错误不得静默当成「未设告警」"
            f"（探针悄悄失效 = 生产端零信号 = 本机制要根治的那类事故）"
        )
        stat["added"] = 0
        stat["updated"] = 0
        stat["replaced"] = 0
        if not dry_run:
            append_log(root, "push", f"拒绝写入：{exc}")
        return stat["status"]
    # 触发条件与体量闸一致：**本轮确实要写**（有新增/替换）才量体量 ⇒
    # 空推（幂等重推）不刷告警日志（避免噪音掩盖真问题）。
    if warn_budget is not None and (blocks or replacements):
        projected = _compose_text(text, blocks, replacements, titleless)
        if len(projected) > warn_budget:
            stat["warnings"].append(
                {
                    "type": "memory_char_warn_limit",
                    "platform": platform,
                    "projected_chars": len(projected),
                    "warn_limit": warn_budget,
                    "message": (
                        f"⚠ 告警：{platform} 推后体量 {len(projected)} 字符 > 告警线 {warn_budget}"
                        f"（hub 侧自设预算，**只报不拦**；写入照常执行）"
                        f" ⇒ 请考虑瘦身 {target.name} 或改推更小的卡片"
                    ),
                }
            )
    return None


def push(
    root: Path,
    platform: str,
    only_rules: bool = False,
    name_filter: str | None = None,
    dry_run: bool = False,
) -> dict:
    """中枢权威卡片 → 平台记忆文件（默认关闭）；外部改动检测到即中止，绝不覆盖本地旧版。

    2026-09-25（SPLIT2）：原为单函数 98 行（C901=18），拆成
    `_push_guard` / `_select_cards` / `_plan_push` / `_apply_push` + 此处纯编排。
    行为逐字不变（tests/test_platform_bridge.py 34 例看守）。
    """
    root = Path(root)
    # `warnings`：结构化告警列表（**只报不拦**的告警线命中时才有内容）。
    # 恒存在（无告警即空列表）⇒ 消费方不必判键是否存在。
    stat = {
        "added": 0,
        "updated": 0,
        "replaced": 0,
        "skipped": 0,
        "status": "ok",
        "warnings": [],
    }
    target = _target_path(root, platform)
    if not target.is_file():
        stat["status"] = f"平台记忆文件不存在: {target}"
        return stat
    state = _read_state(root, platform)
    text = target.read_text(encoding="utf-8")

    abort = _push_guard(target, state, text)
    if abort:
        stat["status"] = abort
        return stat

    cfg = HubConfig.load(root)
    adapter = adapter_for(platform, cfg)
    titleless = isinstance(adapter, SectSeparatedAdapter)  # § 分隔无标题平台：无同名键，走段首行指纹闸
    entries = adapter.parse(text)
    existing_bodies = {e.body.strip() for e in entries if e.body.strip()}
    existing_titles = {e.title for e in entries if e.title}

    cards, not_found = _select_cards(root, only_rules, name_filter)
    if not_found:
        stat["status"] = not_found
        return stat

    # ⚑ 推送模式（2026-11-13）：`pointer` = 平台只收指针（省每轮固定 token）；
    #   默认 `full` ⇒ 行为逐字不变。
    try:
        mode = _push_mode(cfg, platform)
    except ValueError as exc:
        stat["status"] = f"拒绝写入：{exc}"
        return stat

    # ⚑ 指针模式的**清单区**必须反映「平台已落地的全部规则卡」，而非本次推送集合
    #   （`--name xxx` 只推一张时，若清单按推送集合重算 ⇒ 清单只剩那张卡 ⇒ 规则清单丢失；
    #    实测 7,457 → 5,186 字符，少 2,271）。
    #   ⇒ 取**全量 rules/** 作为清单来源（与 `--name` / `--only-rules` 过滤无关）。
    index_cards = None
    if mode == "pointer":
        all_rules, _nf = _select_cards(root, True, None)
        index_cards = all_rules

    pushed_fps = set(state.get("pushed") or [])
    blocks, replacements, pushed_fps = _plan_push(
        adapter,
        cards,
        text,
        state,
        titleless,
        existing_bodies,
        existing_titles,
        stat,
        mode=mode,
        hub_root=root,
        index_cards=index_cards,
    )

    # ⚑ 体量闸 + 告警预算（抽成独立函数 ⇒ push() 复杂度可控，ruff C901）
    _reject = _check_budget_and_warn(cfg, platform, root, target, text, blocks, replacements, titleless, stat, dry_run)
    if _reject:
        return stat

    if dry_run or (not blocks and not replacements):
        if not dry_run:
            _log_warnings(root, stat["warnings"])
        return stat
    err = _apply_push(root, platform, target, state, text, blocks, replacements, titleless, pushed_fps, stat)
    if err:
        stat["status"] = err
    _log_warnings(root, stat["warnings"])
    return stat
