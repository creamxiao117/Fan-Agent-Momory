"""统一知识卡片 frontmatter 的解析 / 写入 / 校验"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

VALID_TYPES = {
    "rule",
    "exp",
    "note",
    "project",
    "retro",
    "methodology",
    "longterm",
    "blueprint",
}
# 合法 status。2026-09-23 新增 "deprecated"：作废卡改用显式字段表达（内容已并入
# frontmatter.superseded_by），不再靠「DEPRECATED 注释在第 1 行导致 frontmatter 解析
# 失败」这种位置敏感的隐式手法。
# 排出口径统一在 tools/retrieve.py 的 EXCLUDED_STATUSES（本字段与它必须一致）。
VALID_STATUS = {"active", "archived", "candidate", "reference", "deprecated"}
KNOWN = {"type", "tags", "updated", "status", "reuse_count", "superseded_by"}

# 必填字段（**原始 frontmatter 层**判定，非 Card 层）。
# 为何需要 raw 层：`parse_card` 对缺字段有默认值（status→active / type→note），
# 于是「卡里压根没写 status」在 `validate_card` 眼里是合法的 —— 2026-09-25 实测
# experience/ 下 6 张卡缺 status 静默存活（审计 §11.4 D1），status 统计因此失真。
# 使用方：`scripts/check_card_frontmatter.py`（提交门禁）与
# `scripts/fix_card_schema_drift.py`（修复器）——两者必须同一口径。
REQUIRED_KEYS = ("type", "status", "updated")

# ── grade：记忆**可信度/强制性**轴（2026-10-02 架构重构 M1）──────────────────
#
# 为何要另开一轴（而不是复用目录或 status）：
#   目录表达**领域/形态**（rules/methodology/experience…），status 表达**生命周期**
#   （candidate/active/deprecated…），两者都无法回答“这条我必须遵守吗？”——
#   而这是 agent 消费记忆时最关键的一问（铁律 vs 随手记的坑，不能用同一权重检索）。
#
# 为何不叫 L0/L1/L2：那三个名字已被 `scripts.startup_budget.py` 占为**预算分层**。
#
# 为何**不复用** `tier` 字段：卡 frontmatter 已有 `tier: task|iron`（旧的重要度字段，
# 覆盖率仅 7%），语义与本轴重叠但取值不同；M1 用 `grade` 建新轴，`tier` 于 Task 13
# 迁移后退役，避免“同一概念两个字段名”的漂移。
VALID_GRADES: frozenset[str] = frozenset({"iron", "proven", "domain", "task", "pitfall"})

# 分目录的合法 grade 集（防止“蓝图被标成铁律”这类语义错位）
GRADES_BY_DIR: dict[str, frozenset[str]] = {
    "rules": frozenset({"iron", "proven", "domain", "task", "pitfall"}),
    "blueprints": frozenset({"proven", "domain"}),
    "methodology": frozenset({"iron", "proven", "domain", "pitfall"}),
    "longterm": frozenset({"domain", "task"}),
    "projects": frozenset({"domain", "proven"}),
    "experience": frozenset({"task", "pitfall", "proven"}),
}

# 各目录的**默认 grade**（2026-10-29 补）：草稿经 ingest 落权威区时若未声明 grade，
# 按目标目录补一个保守默认值，避免每天新增卡都触发 audit 的 P0「缺 grade」。
# 取值口径：必须在该目录合法集内，取**最弱**的一档（宁可低估可信度，
# 也不把随手记标成铁律）。逐目录合法集见 GRADES_BY_DIR。
DEFAULT_GRADE_BY_DIR: dict[str, str] = {
    "rules": "task",  # 合法集含 task；新规则未经确认前不当铁律
    "blueprints": "domain",  # 合法集 {proven, domain} → 取最弱的 domain
    "methodology": "pitfall",  # 合法集不含 task → 取最弱的 pitfall
    "longterm": "domain",  # 合法集 {domain, task} → 取最弱的 domain
    "projects": "domain",  # 合法集 {domain, proven} → 取最弱的 domain
    "experience": "task",  # 合法集 {task, pitfall, proven} → 取最弱的 task
}

# ── evidence 轴（2026-11-02 新增，A8 方案 A）────────────────────────────────
#
# 为何**另开一轴**而不改 `grade`：实测证明 `grade` 是**混合轴**
# （强制性 iron × 证据强度 proven/task × 体裁 pitfall/domain），
# 用关键词拟合它与人工标注的**一致率只有 22%**（5/23）⇒ 机械改判不可行。
#
# 而「这张卡**自己**有没有验证记录」是**客观问题** ⇒ 适合机械填写，
# 且与 `grade` **正交**（实测交叉表无相关）。
#
# 取值：
#   `t1`       —— 本卡做过 T1 亲跑验证（沙盒 / `evidence: t1` / 「T1 验证」小节）
#   `measured` —— 本卡有**自证型**验证记录（实测次数 / 测试通过 / 负样本打红 / 验证结果）
#   `none`     —— 没有可识别的自证记录（**默认**）
#
# 关键约束：**必须自证**——「引用别人的结论」「规则陈述（必须/应当 X）」**不算**验证记录。
EVIDENCE_VALUES: tuple[str, ...] = ("none", "measured", "t1")

# T1 亲跑痕迹：**只看结构标记**（frontmatter 声明 / T1 小节标题 / 沙盒路径）——
# 散文里的「T1 验证」三个字可能是**引用别人**（如路由表引用 T1 结论），不能当自证。
_EV_T1_FM = re.compile(r"^evidence:\s*t1\s*$", re.M)
_EV_T1_SECTION = re.compile(r"^#{2,4}[^\n]*\bT1\b", re.M)
_EV_T1_SANDBOX = re.compile(r"AgentMemoryT1")
# 验证类小节标题（结构位）
_EV_VERIFY_SECTION = re.compile(r"^#{2,4}[^\n]*(验证|实测|复现|回归)", re.M)
# 自证型验证**结果形态**（这些形态在散文里几乎不出现 ⇒ 精度高）：
#   测试通过数 / exit 码 / 负样本打红 / 实测次数 / 跑通时间 / 复现成功
_EV_RESULT = re.compile(
    r"负样本.{0,16}(打红|自证|变红)"
    r"|\d+\s*/\s*\d+\s*(tests?\s*)?(pass|passed|通过)"
    r"|tests?\s+pass(ed)?\b"
    r"|exit\s*[01]\b"
    r"|实测\s*\d+\s*次"
    r"|跑通时间"
    r"|复现成功",
    re.I,
)
# 「要求语气」= 规则陈述而非验证记录（如「写完**必须**跑通再交付」）
_EV_REQUIREMENT = re.compile(r"必须|应当|应该|需先|禁止|务必|要跑|得跑")


def _sections(body: str) -> list[tuple[str, str]]:
    """正文 → [(小节标题, 小节内容)]（按 `##`/`###` 切分；首段归入空标题）。"""
    out: list[tuple[str, str]] = []
    head, buf = "", []
    for ln in (body or "").splitlines():
        if ln.startswith("#"):
            if head or buf:
                out.append((head, "\n".join(buf)))
            head, buf = ln, []
        else:
            buf.append(ln)
    if head or buf:
        out.append((head, "\n".join(buf)))
    return out


def _has_t1_proof(body: str) -> bool:
    """是否**真的**有 T1 验证记录（小节标题含 T1 **且**节内有结果形态/沙盒痕迹）。

    为何要这一步（实测）：光看「标题含 T1」会把
    「## 关键教训（适用所有 T1+ 任务）」这种**提及**误判成验证记录。
    """
    for head, content in _sections(body):
        if "T1" not in head:
            continue
        if _EV_RESULT.search(content) or _EV_T1_SANDBOX.search(content) or "沙盒" in content:
            return True
    return False


def infer_evidence(extra: dict, body: str) -> str:
    """→ evidence 档（none/measured/t1）。

    仅用于**入库时补全新卡**（不覆盖卡已声明的值，也**不改存量卡**）。

    判定只看**结构标记**，不看散文措辞（v1 用散文关键词实测精度不足：
    「引用别人的结论」「规则陈述（必须 X）」会被误判 ⇒ 已收窄）：
      - T1：frontmatter 显式 `evidence: t1` / 有「T1」小节**且节内有实质证据** / 出现沙盒路径
      - measured：有**验证类小节标题**且节内有**结果形态**，或全文出现**强结果形态**
      - 其余：none
    """
    text = body or ""
    # frontmatter 显式声明（extra 里是**已解析的值**，不是原文）
    if str(extra.get("evidence") or "").strip() == "t1":
        return "t1"
    if _EV_T1_SANDBOX.search(text):
        return "t1"
    if _has_t1_proof(text):
        return "t1"
    has_section = bool(_EV_VERIFY_SECTION.search(text))
    for line in text.splitlines():
        if not _EV_RESULT.search(line):
            continue
        if _EV_REQUIREMENT.search(line):
            continue  # 「必须跑通」= 要求，不是记录
        if has_section or _EV_RESULT.search(line):
            return "measured"
    return "none"


def raw_frontmatter(path: Path) -> dict:
    """读**原始** frontmatter（不经 Card 默认值兜底）；不可解析时返回 {}。

    容忍 BOM 与前导空行（与 try_read_card 同口径）；只负责取字典，不做校验。
    """
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return {}
    if not text.lstrip().startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}


def missing_required_keys(raw: dict) -> list[str]:
    """返回原始 frontmatter 中**缺失或空值**的必填字段名（顺序同 REQUIRED_KEYS）"""
    return [k for k in REQUIRED_KEYS if not str(raw.get(k) or "").strip()]


def today_date() -> date:
    """本地日期（时区感知，满足 lint 的 tz 要求）"""
    return datetime.now(tz=timezone.utc).astimezone().date()


def today_iso() -> str:
    """本地日期 YYYY-MM-DD"""
    return today_date().isoformat()


@dataclass
class Card:
    """一张知识卡片（对应一个 .md 文件）"""

    type: str = "note"
    tags: list = field(default_factory=list)
    updated: str = ""
    status: str = "active"
    reuse_count: int = 0
    extra: dict = field(default_factory=dict)  # 其他自定义字段原样保留
    body: str = ""
    path: Path | None = None  # 从磁盘读取时记录来源路径


def parse_card(text: str, path: Path | None = None) -> Card:
    """解析 '---\n...\n---\n正文' 的统一卡片"""
    if not text.startswith("---"):
        raise ValueError("缺少 frontmatter 起始分隔符 '---'")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("frontmatter 缺少结束分隔符 '---'")
    fm = yaml.safe_load(parts[1]) or {}
    card = Card(path=path)
    if isinstance(fm.get("tags"), list):
        card.tags = [str(t) for t in fm["tags"]]
    card.type = str(fm.get("type", "note"))
    card.updated = str(fm.get("updated", ""))
    card.status = str(fm.get("status", "active"))
    card.reuse_count = int(fm.get("reuse_count", 0) or 0)
    card.extra = {k: v for k, v in fm.items() if k not in KNOWN}
    card.body = parts[2].strip()
    return card


def write_card(card: Card) -> str:
    """把卡片渲染回统一格式文本"""
    fm = {
        "type": card.type,
        "tags": card.tags,
        "updated": card.updated or today_iso(),
        "status": card.status,
        "reuse_count": card.reuse_count,
    }
    fm.update(card.extra)
    return (
        "---\n"
        + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip()
        + "\n---\n\n"
        + card.body.strip()
        + "\n"
    )


def validate_card(card: Card) -> list[str]:
    """返回错误列表；空列表表示合法。

    `grade`（2026-10-02 M1/Task 12 新增，**灰度口径**）：
      - 只校验**取值合法性**（枚举 + 分目录约束），**不要求存在**；
      - 缺失由 `scripts.migrate_grade` 批量回填（已完成 499/499）；
      - **覆盖率由提交门禁 `scripts/check_card_frontmatter` 看守**，不放这里 ——
        本函数只管"单卡合法性"，放进来的话所有测试夹具（最简卡）都会被迫带 grade；
      - 这样新卡从前就是“可选字段”，不会因新增字段而让存量 506 张卡集体变 invalid。
    """
    errs = []
    if card.type not in VALID_TYPES:
        errs.append(f"type 必须为 {sorted(VALID_TYPES)} 之一，当前: {card.type}")
    if card.status not in VALID_STATUS:
        errs.append(f"status 必须为 {sorted(VALID_STATUS)} 之一，当前: {card.status}")
    if not card.updated:
        errs.append("updated 必填（YYYY-MM-DD）")
    grade = str(card.extra.get("grade") or "").strip()
    if grade and grade not in VALID_GRADES:
        errs.append(f"grade 必须为 {sorted(VALID_GRADES)} 之一，当前: {grade}")
    evidence = str(card.extra.get("evidence") or "").strip()
    if evidence and evidence not in EVIDENCE_VALUES:
        errs.append(f"evidence 必须为 {sorted(EVIDENCE_VALUES)} 之一，当前: {evidence}")
    if grade and card.path is not None:
        allowed = GRADES_BY_DIR.get(card.path.parent.name)
        if allowed and grade not in allowed:
            errs.append(f"grade={grade} 不适用于 {card.path.parent.name}/（允许 {sorted(allowed)}）")
    return errs


def read_card(path: Path) -> Card:
    """读取卡片。utf-8-sig 同时容忍 BOM 与无 BOM——带 EF BB BF 头三字节的卡也能正常解析，
    避免误判为 invalid（实测 2026-08-21：草稿写入默认 UTF8 会带 BOM，导致 startswith(--) 判空）。"""
    return parse_card(path.read_text(encoding="utf-8-sig"), path=path)


def try_read_card(path: Path) -> Card | None:
    """读取卡片；非卡片/格式错误时返回 None（供各扫描器跳过坏文件）"""
    try:
        return read_card(path)
    except (ValueError, OSError, yaml.YAMLError, TypeError, AttributeError):
        return None


def card_title(path: Path) -> str | None:
    """卡的**标题**：frontmatter `title:` → 首个 H1 → None。

    与 `extract_summary` 用途不同，两者不可互换：
    - 本函数取**身份**（用于幽灵 slug ↔ 卡的匹配、按标题查找）
    - `extract_summary` 取**摘要内容**（用于 INDEX 描述；会跳过样板标题、读正文段落）
    2026-09-23：原 `fix_index_registry._card_title` 是这份逻辑的私有副本，已上提此处
    成为单一来源（合并时曾误以为它与 extract_summary 重复而删掉，被测试拦住）。
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for raw in parts[1].splitlines():
                if raw.strip().startswith("title:"):
                    val = raw.split(":", 1)[1].strip().strip("\"'")
                    if val:
                        return val
    for raw in text.splitlines():
        if raw.startswith("# "):
            return raw[2:].strip()
    return None


def save_card(card: Card, path: Path) -> None:
    path.write_text(write_card(card), encoding="utf-8")
