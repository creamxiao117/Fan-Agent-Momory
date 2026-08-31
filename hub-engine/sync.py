"""同步器：单一写入者 + 暂存区提升 + 去重/冲突 + 人工确认 + Git 提交"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from common.constants import HIGH_RISK  # 高风险类型：rule + methodology
from common.frontmatter import (
    Card,
    read_card,
    today_iso,
    try_read_card,
    validate_card,
    write_card,
)
from common.vector import cosine, vector
from tools.dedup import candidates as dedup_candidates
from tools.dedup import decide as dedup_decide
from tools.memory_diff import record as record_diff

TYPE_DIR = {
    "rule": "rules",
    "methodology": "methodology",
    "longterm": "longterm",
    "exp": "experience",
    "note": "experience",
    "project": "projects",
    "retro": "retro",
    "blueprint": "blueprints",
}
# HIGH_RISK 已统一到 common/constants.py（含 rule + methodology）

# 与 bootstrap_hub 一致：注入本地身份，保证未配置全局 user.name/email 也能提交（不污染全局配置）
GIT_ID = ["-c", "user.name=AgentMemoryHub", "-c", "user.email=hub@local"]


def _git(repo: Path, *args: str) -> str:
    """运行 git 子命令；返回 stdout，失败时透传真实 stderr（与 bootstrap 的 _run_git 一致）"""
    cmd = ["git", "-C", str(repo), *args]
    try:
        r = subprocess.run(
            cmd, check=True, capture_output=True, text=True, encoding="utf-8"
        )
        return r.stdout or ""
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(f"git 命令失败: {' '.join(cmd)}\n{stderr or e}") from e


def _append_log(root: Path, op: str, title: str) -> None:
    """retro/log.md append-only 时间线：## [YYYY-MM-DD] <op> | <title>"""
    log = root / "retro" / "log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"## [{today_iso()}] {op} | {title}\n")


def append_log(root: Path, op: str, title: str) -> None:
    _append_log(root, op, title)


def _authority_cards(root: Path) -> list[Card]:
    cards = []
    for sub in (
        "rules",
        "methodology",
        "longterm",
        "projects",
        "experience",
        "libs",
        "blueprints",
        "retro",
    ):
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.glob("*.md")):
            card = try_read_card(p)
            if card is not None:
                cards.append(card)
    return cards


def _find_duplicate(root: Path, card: Card, threshold: float = 0.7) -> Card | None:
    """语义相似度判断是否与权威区已有卡片重复（内容冲突不覆盖）"""
    cv = vector(card.body)
    for c in _authority_cards(root):
        if cosine(cv, vector(c.body)) >= threshold:
            return c
    return None


def _commit(root: Path, message: str) -> None:
    """提交变更：无变更可提交时直接跳过；真实 Git 失败透传 stderr"""
    if not _git(root, "status", "--porcelain").strip():
        return
    _git(root, "add", "-A")
    _git(root, *GIT_ID, "commit", "-m", message)


class _WriteLock:
    """写前锁：同一时刻只允许一个写入者（.sync/locks/writer.lock）"""

    def __init__(self, root: Path):
        self.lock = root / ".sync" / "locks" / "writer.lock"

    def __enter__(self):
        if self.lock.exists():
            raise RuntimeError("写锁已存在，同步器正在运行中")
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text("", encoding="utf-8")
        return self

    def __exit__(self, *exc):
        self.lock.unlink(missing_ok=True)


def _write_dedup_prediction(
    cdir: Path, platform: str, draft: Path, card, decision: dict
) -> None:
    """把 LLM 去重建议写到冲突区伴生 .pred.json，供人工终审（不自动执行 merge/delete）"""
    try:
        payload = {
            "op": "dedup_prediction",
            "platform": platform,
            "draft": draft.name,
            "decision": decision,
        }
        pred = cdir / f"{platform}_{draft.stem}.pred.json"
        pred.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass  # 决策留痕失败不阻断同步主流程


def ingest(root: Path, platform: str, chat_fn=None) -> dict:
    """把 .sync/drafts/<platform>_draft/ 下的内容提升到中枢；返回统计。

    chat_fn（可选）：去重 LLM 注入入口（OpenViking 路径 B）。缺省为 None →
    走 legacy 纯向量去重（离线/离线环境 = 冲突区人工，不误删）。传入时对相似
    候选产 LLM 路由建议：高置信 skip 丢弃草稿，其余（merge/delete/review）仍进
    冲突区交人工，绝不自动覆盖权威区。
    """
    root = Path(root)
    stat = {"promoted": 0, "pending": 0, "duplicate": 0, "invalid": 0, "status": "ok"}
    drafts = root / ".sync" / "drafts" / f"{platform}_draft"
    if not drafts.is_dir():
        return stat
    try:
        with _WriteLock(root):
            for p in sorted(drafts.glob("*.md")):
                card = try_read_card(p)
                if card is None:
                    stat["invalid"] += 1
                    continue
                if validate_card(card):
                    stat["invalid"] += 1
                    continue
                cands = dedup_candidates(root, card)
                if cands:
                    stat["duplicate"] += 1
                    decision = (
                        dedup_decide(root, card, cands, chat_fn=chat_fn)
                        if chat_fn
                        else None
                    )
                    # 高置信重复（LLM 明确 skip 且 ≥0.8）→ 丢弃草稿，不落冲突区
                    if (
                        decision
                        and decision["action"] == "skip"
                        and decision["confidence"] >= 0.8
                    ):
                        _append_log(root, "ingest", f"LLM 判定重复，丢弃草稿：{p.name}")
                        record_diff(
                            root,
                            {
                                "op": "delete",
                                "name": p.name,
                                "type": card.type,
                                "deleted_content": (
                                    f"LLM 判定重复(skip conf={decision['confidence']:.2f})，"
                                    f"丢弃：{decision['reason']}"
                                ),
                            },
                        )
                        p.unlink()
                        continue
                    # 反哺经验(2026-08-21)：LLM 高置信判 create（新卡、与候选主题不同无重复，
                    # target=null）→ 视作无有效候选，低风险卡型直接自动入区不落冲突区；
                    # rule 仍须人工；权威区同名冲突仍交冲突区兜底。
                    if (
                        decision
                        and decision["action"] == "create"
                        and decision.get("confidence", 0) >= 0.8
                        and card.type not in HIGH_RISK
                    ):
                        dst_c = root / TYPE_DIR.get(card.type, "experience") / p.name
                        if dst_c.exists():
                            cdir = root / ".sync" / "conflicts"
                            cdir.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(p, cdir / f"{platform}_{p.name}")
                            # 外层 cands 命中已 duplicate+=1，此处不重复计数
                            _append_log(
                                root,
                                "ingest",
                                f"LLM 判 create 高置信但权威区同名，进冲突区：{p.name}",
                            )
                            record_diff(
                                root,
                                {
                                    "op": "delete",
                                    "name": p.name,
                                    "type": card.type,
                                    "deleted_content": (
                                        f"同名冲突，回收进冲突区（hash={hash(card.body) & 0xFFFF:x}）"
                                    ),
                                },
                            )
                        else:
                            if card.type != "blueprint":
                                card.status = "active"
                            dst_c.parent.mkdir(parents=True, exist_ok=True)
                            dst_c.write_text(write_card(card), encoding="utf-8")
                            stat["promoted"] += 1
                            _append_log(
                                root,
                                "ingest",
                                f"LLM 判 create 高置信，自动入区：{p.name}",
                            )
                            record_diff(
                                root,
                                {
                                    "op": "add",
                                    "name": p.name,
                                    "type": card.type,
                                    "before": None,
                                    "after": str(dst_c.relative_to(root)).replace(
                                        os.sep, "/"
                                    ),
                                },
                            )
                        p.unlink()
                        continue
                    cdir = root / ".sync" / "conflicts"
                    cdir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, cdir / f"{platform}_{p.name}")
                    # 决策留痕：冲突区附 .pred.json 建议，供人工终审
                    if decision:
                        (_write_dedup_prediction(cdir, platform, p, card, decision))
                    _append_log(
                        root,
                        "ingest",
                        f"重复内容进冲突区：{p.name}"
                        + (
                            f"（LLM 建议 {decision['action']}，待人工终审）"
                            if decision
                            else ""
                        ),
                    )
                    record_diff(
                        root,
                        {
                            "op": "delete",
                            "name": p.name,
                            "type": card.type,
                            "deleted_content": f"重复，回收进冲突区（hash={hash(card.body) & 0xFFFF:x}）",
                        },
                    )
                    p.unlink()  # 内容已保留在冲突区，草稿无保留价值
                    continue
                if card.type in HIGH_RISK:
                    # 新增重要规则 → 待人工确认
                    pending = root / ".sync" / "pending"
                    pending.mkdir(parents=True, exist_ok=True)
                    card.status = "candidate"
                    (pending / p.name).write_text(write_card(card), encoding="utf-8")
                    stat["pending"] += 1
                    _append_log(root, "ingest", f"新规则待确认：{p.name}")
                    record_diff(
                        root,
                        {
                            "op": "add",
                            "name": p.name,
                            "type": card.type,
                            "before": None,
                            "after": f".sync/pending/{p.name}",
                        },
                    )
                else:
                    # 低风险内容 → 自动入区，仅记日志
                    dst = root / TYPE_DIR.get(card.type, "experience") / p.name
                    if dst.exists():
                        # 同名不同内容（语义去重已在上方处理过）→ 不覆盖权威区，转冲突区
                        cdir = root / ".sync" / "conflicts"
                        cdir.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(p, cdir / f"{platform}_{p.name}")
                        stat["duplicate"] += 1
                        _append_log(root, "ingest", f"同名不同内容进冲突区：{p.name}")
                        record_diff(
                            root,
                            {
                                "op": "delete",
                                "name": p.name,
                                "type": card.type,
                                "deleted_content": f"同名冲突，回收进冲突区（hash={hash(card.body) & 0xFFFF:x}）",
                            },
                        )
                    else:
                        # 蓝图卡保留草稿声明的 status（reference→T1 前 / active→试用后），其余低风险卡默认为 active
                        if card.type != "blueprint":
                            card.status = "active"
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_text(write_card(card), encoding="utf-8")
                        stat["promoted"] += 1
                        _append_log(root, "ingest", f"自动入区：{p.name}")
                        record_diff(
                            root,
                            {
                                "op": "add",
                                "name": p.name,
                                "type": card.type,
                                "before": None,
                                "after": str(dst.relative_to(root)).replace(
                                    os.sep, "/"
                                ),
                            },
                        )
                p.unlink()
            _commit(root, f"sync: ingest {platform} draft → hub")
    except RuntimeError as e:
        stat["status"] = str(e)
    return stat


def confirm_rule(root: Path, name: str) -> Path:
    """人工确认后，把待确认卡片提升为 active 并按 card.type 路由入对应权威区"""
    root = Path(root)
    # 兼容裸卡名：CLI 传 "post-task-recommendations" 时自动补 .md（此前必报 FileNotFoundError）
    if not name.endswith(".md"):
        name = f"{name}.md"
    src = root / ".sync" / "pending" / name
    if not src.exists():
        raise FileNotFoundError(f"待确认文件不存在: {src}")
    with _WriteLock(root):
        card = read_card(src)
        card.status = "active"
        card.reuse_count = 0
        # 目标目录跟随卡片类型（复用 ingest 的 TYPE_DIR 映射；此前硬编码 rules/，
        # methodology/exp 等待确认卡无法经 CLI 提升）
        dst = root / TYPE_DIR.get(card.type, "experience") / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(write_card(card), encoding="utf-8")
        src.unlink()
        _append_log(root, "confirm", f"确认卡片：{name} → {dst.parent.name}/")
        _commit(root, f"sync: confirm {card.type} {name}")
    return dst
