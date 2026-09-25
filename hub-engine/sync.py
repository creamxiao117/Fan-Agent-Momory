"""同步器：单一写入者 + 暂存区提升 + 去重/冲突 + 人工确认 + Git 提交"""

import json
import os
import shutil
import subprocess
import time as _t
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

# 权威区 type→目录映射（仅 5 个权威区）
# exp/note/retro 类型卡不再自动提升进权威区
TYPE_DIR = {
    "rule": "rules",
    "blueprint": "blueprints",
    "methodology": "methodology",
    "longterm": "longterm",
    "project": "projects",
}
# （2026-09-02 清理）原 _NON_AUTH_TYPES = {exp,note,retro} 为死常量：定义后无消费，
# 跳过逻辑实际由 TYPE_DIR.get(card.type) is None 分支承担（sync.py ingest 内），已删除。
# HIGH_RISK 已统一到 common/constants.py（含 rule + methodology）

# 与 bootstrap_hub 一致：注入本地身份，保证未配置全局 user.name/email 也能提交（不污染全局配置）
GIT_ID = ["-c", "user.name=AgentMemoryHub", "-c", "user.email=hub@local"]


def _git(repo: Path, *args: str) -> str:
    """运行 git 子命令；返回 stdout，失败时透传真实 stderr（与 bootstrap 的 _run_git 一致）"""
    cmd = ["git", "-C", str(repo), *args]
    try:
        r = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
        return r.stdout or ""
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise RuntimeError(f"git 命令失败: {' '.join(cmd)}\n{stderr or e}") from e


def _snapshot_dirty(root: Path) -> set[str]:
    """操作开始前的「他人现场」快照：当前已 dirty 的路径（含未跟踪），供 _commit 豁免。

    V1.3 (2026-09-19): 修 §4 工作区守护缺陷 —— 原 _commit 无条件 `git add -A`，会把
    操作期间**其它进程/平台**未提交的改动一并卷进本次 commit。实证：ingest 提交
    f93742e 卷入 nightly.log / retro/log.md / cross-platform-sync-rule.md /
    candidate-1.md 删除 共 4 项。现改为「只提交本次操作新产生的改动」。

    残留边界（已知，远优于 add -A）：快照之后才被别人改脏的路径仍会被纳入。引擎侧写入
    都在 _WriteLock 内（其它引擎操作无法并发），故窗口仅剩不持锁的外部编辑器。
    """
    # -uall: 未跟踪文件逐条列出（默认会把整个未跟踪目录折叠成 "dir/"，
    #        那样"本次新产出"落在全新目录里时会算不出差异 → 静默漏提交）
    out = _git(root, "-c", "core.quotepath=false", "status", "--porcelain", "-uall")
    dirty: set[str] = set()
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:  # rename 记录形如 "old -> new"
            old, new = path.split(" -> ", 1)
            dirty.update({old.strip(), new.strip()})
        else:
            dirty.add(path)
    return dirty


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
    # 仅扫 6 个权威区目录
    # V1.2 (2026-09-10): 新增 experience/ —— trae-work-ruff-format-batch-bug.md 实证
    # 经验卡也可被 sync --push 推到各平台（避免 "not-found" 阻断）
    for sub in (
        "rules",
        "blueprints",
        "methodology",
        "longterm",
        "projects",
        "experience",
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


def _commit(root: Path, message: str, protect: set[str] | None = None) -> None:
    """提交变更：只提交本次操作新产生的改动；无变更时跳过；Git 失败透传 stderr

    V1.3 (2026-09-19): 新增 protect（_snapshot_dirty 产物）。
      protect 有值 → 只 `git add` 本次新变化，绝不卷入他人未提交改动
      protect=None → 兼容旧调用，退回 add -A 并打印告警

    V1.1 (2026-09-08): T10 Phase 2 —— commit_ledger 双平台协调。
    每次 commit 前在 .sync/state/commit_ledger.jsonl 写一行：
      {ts, who, intent, parent_sha, new_sha, branch}
    - who = env HERMES_PLATFORM（hermes/trae/code/workbuddy/dsh）
    - parent_sha = commit 前 HEAD
    - new_sha = commit 后 HEAD（commit 后再回填）
    这样 reset --hard 必须先写 ledger 一行说明理由。
    """
    if not _git(root, "status", "--porcelain").strip():
        return
    if protect is None:
        print("[sync] 警告: _commit 未给 protect 快照, 退回 git add -A（可能卷入他人改动）")
        add_args = ["add", "-A"]
    else:
        mine = sorted(_snapshot_dirty(root) - protect)
        if not mine:
            return
        add_args = ["add", "--", *mine]
    parent_sha = _git(root, "rev-parse", "HEAD").strip()
    _git(root, *add_args)
    _git(root, *GIT_ID, "commit", "-m", message)
    new_sha = _git(root, "rev-parse", "HEAD").strip()
    _record_commit(root, parent_sha, new_sha, message)


def _record_commit(root: Path, parent_sha: str, new_sha: str, intent: str) -> None:
    """记一行到 .sync/state/commit_ledger.jsonl。失败仅 warning 不阻断。

    V1.0 (2026-09-08): T10 Phase 2 —— 双平台协调 commit ledger。
    """
    import json
    import os
    import time

    ledger = root / ".sync" / "state" / "commit_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    who = os.environ.get("HERMES_PLATFORM", "unknown")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() or "unknown"
    rec = {
        "ts": int(time.time()),
        "who": who,
        "intent": intent[:200],  # 截断超长 commit message
        "parent_sha": parent_sha,
        "new_sha": new_sha,
        "branch": branch,
        "action": "commit",
    }
    try:
        with ledger.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        import warnings

        warnings.warn(f"commit_ledger 写入失败：{e}", stacklevel=2)


class _WriteLock:
    """写前锁：单写者 + 僵尸检测 + 指数退避（双平台协调方法论 Phase 1.1）

    锁文件 = .sync/locks/writer.lock，内容 = <pid>
    - 检测僵尸：PID 不存活 + mtime > LOCK_TIMEOUT（5 分钟）→ 自动清
    - 撞锁：退避 1s/2s/4s 重试，最多 3 次
    - 仍失败：raise RuntimeError 提示走 schedule.toml 错峰

    V1.0 (2026-09-08): user 选 C 实施完整 3 阶段。
    """

    LOCK_TIMEOUT = 300
    LOCK_MAX_RETRY = 3
    LOCK_BACKOFF_BASE = 1.0

    def __init__(self, root: Path):
        self.lock = root / ".sync" / "locks" / "writer.lock"
        import uuid

        self._signature = f"{os.getpid()}|{uuid.uuid4().hex[:12]}|{self._hostname()}|{int(_t.time())}"

    @staticmethod
    def _hostname() -> str:
        import socket

        try:
            return socket.gethostname()
        except OSError:
            return "unknown"

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            if os.name == "nt":
                import subprocess

                r = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=2,
                )
                return bool(r.stdout) and str(pid) in r.stdout
            os.kill(pid, 0)
            return True
        except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
            return False

    def _read_lock(self):
        try:
            text = self.lock.read_text(encoding="utf-8").strip()
            lines = text.splitlines()
            first = lines[0] if lines else ""
            parts = first.split("|") if "|" in first else (first, "", "", "")
            pid = int(parts[0]) if parts[0].isdigit() else None
            mtime = self.lock.stat().st_mtime
            return pid, mtime
        except (FileNotFoundError, ValueError, IndexError):
            return None, None

    def _is_zombie(self) -> bool:
        pid, mtime = self._read_lock()
        if pid is None or mtime is None:
            return False
        if self._pid_alive(pid):
            return False
        import time as _t

        return _t.time() - mtime > self.LOCK_TIMEOUT

    def __enter__(self):
        for attempt in range(self.LOCK_MAX_RETRY):
            if not self.lock.exists():
                self.lock.parent.mkdir(parents=True, exist_ok=True)
                self.lock.write_text(self._signature + chr(10), encoding="utf-8")
                return self
            if self._is_zombie():
                self.lock.unlink(missing_ok=True)
                continue
            if attempt < self.LOCK_MAX_RETRY - 1:
                _t.sleep(self.LOCK_BACKOFF_BASE * (2**attempt))
                continue
            break
        raise RuntimeError(
            f"写锁被持续占用（重试 {self.LOCK_MAX_RETRY} 次失败）。"
            "请检查 .sync/locks/writer.lock 持锁进程，或走 schedule.toml 错峰。"
        )

    def __exit__(self, *exc):
        try:
            text = self.lock.read_text(encoding="utf-8").strip()
            sig_uuid = self._signature.split("|")[1] if "|" in self._signature else ""
            file_uuid = text.split("|")[1] if "|" in text else ""
            if file_uuid and file_uuid == sig_uuid:
                self.lock.unlink(missing_ok=True)
        except (FileNotFoundError, OSError):
            pass


def _write_dedup_prediction(cdir: Path, platform: str, draft: Path, card, decision: dict) -> None:
    """把 LLM 去重建议写到冲突区伴生 .pred.json，供人工终审（不自动执行 merge/delete）"""
    try:
        payload = {
            "op": "dedup_prediction",
            "platform": platform,
            "draft": draft.name,
            "decision": decision,
        }
        pred = cdir / f"{platform}_{draft.stem}.pred.json"
        pred.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # 决策留痕失败不阻断同步主流程


def _ingest_stat_template() -> dict:
    """ingest 的统计骨架（键名是 post_ingest_hook 的接口，勿随意改）。"""
    return {
        "promoted": 0,
        "pending": 0,
        "duplicate": 0,
        "invalid": 0,
        "status": "ok",
        "moved_names": [],  # T1 (2026-09-07): 给 post_ingest_hook 精确清单
        "promoted_names": [],
        "lint_errors": [],
    }


def _read_valid_draft(p: Path, stat: dict):
    """读草稿并过合法性门；不合规则计入 invalid 并返回 None。

    两类不合规：① frontmatter 读不出来（`try_read_card` → None）；
    ② 能读但字段非法（`validate_card` 有错）。
    """
    card = try_read_card(p)
    if card is None:
        stat["invalid"] += 1
        return None
    if validate_card(card):
        stat["invalid"] += 1
        return None
    return card


def _move_non_authority_draft(root: Path, p: Path, card, stat: dict) -> None:
    """非权威区类型（exp/note/retro）→ 不参与去重/向量/检索，**改挪 experience/ 保留**。

    用户指令（2026-09-02）：改挪而非删除。同名时加日期后缀，绝不覆盖既有卡。
    """
    exp_dir = root / "experience"
    exp_dir.mkdir(parents=True, exist_ok=True)
    dst = exp_dir / p.name
    if dst.exists():
        dst = exp_dir / f"{p.stem}-{today_iso()}{p.suffix}"
    shutil.move(str(p), str(dst))
    stat["moved"] = stat.get("moved", 0) + 1
    stat["moved_names"].append(p.name)
    _append_log(root, "ingest", f"非权威区 type={card.type}，改挪 experience/ 保留：{dst.name}")
    record_diff(
        root,
        {
            "op": "move",
            "name": p.name,
            "type": card.type,
            "before": str(p.relative_to(root)).replace(os.sep, "/"),
            "after": str(dst.relative_to(root)).replace(os.sep, "/"),
        },
    )


def _put_into_conflicts(
    root: Path,
    platform: str,
    p: Path,
    card,
    *,
    diff_message: str,
    log_message: str | None = None,
    decision: dict | None = None,
    unlink: bool,
) -> None:
    """把草稿复制进 `.sync/conflicts/<platform>_<name>`，并按需留痕/记账/删草稿。

    动作顺序与原实现逐字一致：**复制 → （可选）`.pred.json` 建议 → （可选）日志 → diff → （可选）删草稿**。
    `unlink` 由调用方指定：重复分流路径自己删；低风险同名冲突路径交给循环尾部的统一 `p.unlink()`。
    """
    cdir = root / ".sync" / "conflicts"
    cdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, cdir / f"{platform}_{p.name}")
    if decision:
        _write_dedup_prediction(cdir, platform, p, card, decision)
    if log_message:
        _append_log(root, "ingest", log_message)
    record_diff(
        root,
        {
            "op": "delete",
            "name": p.name,
            "type": card.type,
            "deleted_content": diff_message,
        },
    )
    if unlink:
        p.unlink()  # 内容已保留在冲突区，草稿无保留价值


def _handle_duplicate_draft(root: Path, platform: str, p: Path, card, cands: list, stat: dict, chat_fn) -> None:
    """命中去重候选后的三条出路（按 LLM 决策分流；`cands` 原样传给 dedup_decide）。

    1. **高置信 skip(≥0.8)** → 判为真重复，丢弃草稿（不入冲突区）
    2. **高置信 create(≥0.8) 且非高风险** → 视作无有效候选：权威区无同名则直接入区，
       有同名则进冲突区（不覆盖）
    3. **其余（merge/delete/review/低置信/无决策）** → 进冲突区交人工
    """
    stat["duplicate"] += 1
    decision = dedup_decide(root, card, cands, chat_fn=chat_fn) if chat_fn else None
    # 高置信重复（LLM 明确 skip 且 ≥0.8）→ 丢弃草稿，不落冲突区
    if decision and decision["action"] == "skip" and decision["confidence"] >= 0.8:
        _append_log(root, "ingest", f"LLM 判定重复，丢弃草稿：{p.name}")
        record_diff(
            root,
            {
                "op": "delete",
                "name": p.name,
                "type": card.type,
                "deleted_content": (
                    f"LLM 判定重复(skip conf={decision['confidence']:.2f})，丢弃：{decision['reason']}"
                ),
            },
        )
        p.unlink()
        return
    # 反哺经验(2026-08-21)：LLM 高置信判 create（新卡、与候选主题不同无重复，target=null）
    # → 视作无有效候选，低风险卡型直接自动入区；rule 仍须人工；权威区同名冲突仍交冲突区兜底
    if (
        decision
        and decision["action"] == "create"
        and decision.get("confidence", 0) >= 0.8
        and card.type not in HIGH_RISK
    ):
        dst_c = root / TYPE_DIR.get(card.type) / p.name
        if dst_c.exists():
            _put_into_conflicts(
                root,
                platform,
                p,
                card,
                # 外层 cands 命中已 duplicate+=1，此处不重复计数
                log_message=f"LLM 判 create 高置信但权威区同名，进冲突区：{p.name}",
                diff_message=f"同名冲突，回收进冲突区（hash={hash(card.body) & 0xFFFF:x}）",
                unlink=False,
            )
        else:
            if card.type != "blueprint":
                card.status = "active"
            dst_c.parent.mkdir(parents=True, exist_ok=True)
            dst_c.write_text(write_card(card), encoding="utf-8")
            stat["promoted"] += 1
            stat["promoted_names"].append(p.name)
            _append_log(root, "ingest", f"LLM 判 create 高置信，自动入区：{p.name}")
            record_diff(
                root,
                {
                    "op": "add",
                    "name": p.name,
                    "type": card.type,
                    "before": None,
                    "after": str(dst_c.relative_to(root)).replace(os.sep, "/"),
                },
            )
        p.unlink()
        return
    _put_into_conflicts(
        root,
        platform,
        p,
        card,
        log_message=(
            f"重复内容进冲突区：{p.name}" + (f"（LLM 建议 {decision['action']}，待人工终审）" if decision else "")
        ),
        diff_message=f"重复，回收进冲突区（hash={hash(card.body) & 0xFFFF:x}）",
        decision=decision,  # 决策留痕：冲突区附 .pred.json 建议，供人工终审
        unlink=True,
    )


def _stage_pending_draft(root: Path, p: Path, card, stat: dict) -> None:
    """高风险类型（rule + methodology）→ 落 `.sync/pending/` 且状态置 `candidate`，等人工确认。"""
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


def _promote_or_conflict_draft(root: Path, platform: str, p: Path, card, stat: dict) -> None:
    """低风险内容 → 自动入区；权威区已存在同名（语义去重已在上游处理过）→ 不覆盖，转冲突区。

    状态处理：蓝图保留草稿声明（reference→T1 前 / active→试用后），其余低风险卡置 `active`。
    草稿的删除统一由调用方（循环尾部）负责。
    """
    dst_dir = TYPE_DIR.get(card.type)
    dst = root / dst_dir / p.name
    if dst.exists():
        # 同名不同内容（语义去重已在上方处理过）→ 不覆盖权威区，转冲突区
        _put_into_conflicts(
            root,
            platform,
            p,
            card,
            log_message=f"同名不同内容进冲突区：{p.name}",
            diff_message=f"同名冲突，回收进冲突区（hash={hash(card.body) & 0xFFFF:x}）",
            unlink=False,
        )
        stat["duplicate"] += 1
        return
    # 蓝图卡保留草稿声明的 status（reference→T1 前 / active→试用后），其余低风险卡默认为 active
    if card.type != "blueprint":
        card.status = "active"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(write_card(card), encoding="utf-8")
    stat["promoted"] += 1
    stat["promoted_names"].append(p.name)
    _append_log(root, "ingest", f"自动入区：{p.name}")
    record_diff(
        root,
        {
            "op": "add",
            "name": p.name,
            "type": card.type,
            "before": None,
            "after": str(dst.relative_to(root)).replace(os.sep, "/"),
        },
    )


def ingest(root: Path, platform: str, chat_fn=None, strict_lint: bool = False) -> dict:
    """把 .sync/drafts/<platform>_draft/ 下的内容提升到中枢；返回统计。

    chat_fn（可选）：去重 LLM 注入入口（OpenViking 路径 B）。缺省为 None →
    走 legacy 纯向量去重（离线/离线环境 = 冲突区人工，不误删）。传入时对相似
    候选产 LLM 路由建议：高置信 skip 丢弃草稿，其余（merge/delete/review）仍进
    冲突区交人工，绝不自动覆盖权威区。

    strict_lint（T2, 2026-09-07）：True = 草稿 frontmatter 不合规直接 return 阻断；
    False（默认）= 软门禁，只把 errors 写进 stat["lint_errors"], 继续 ingest。

    2026-09-25（审计 SPLIT / P2-b）：本函数由 229 行拆成「门禁 + 遍历派发 + 提交」编排，
    各分支的落盘/日志/diff 行为抽到 `_move_non_authority_draft` / `_handle_duplicate_draft` /
    `_stage_pending_draft` / `_promote_or_conflict_draft` / `_put_into_conflicts`，
    行为逐字保持不变（拆分前先补了 14 例分支级 fixture 测试作网，拆分后同一套测试全绿）。
    """
    from tools.lint import lint_drafts  # lazy import 避免循环依赖

    root = Path(root)
    stat = _ingest_stat_template()
    drafts = root / ".sync" / "drafts" / f"{platform}_draft"
    if not drafts.is_dir():
        return stat
    # T2 (2026-09-07): L1 门禁——只扫本平台草稿，不扫全库
    _lint = lint_drafts(root, platform)
    stat["lint_errors"] = _lint["errors"]
    if strict_lint and _lint["errors"]:
        stat["status"] = "lint_blocked"
        return stat
    # §4 工作区守护（2026-09-19）：先快照"他人现场"，_commit 只 add 本次新变化
    protect = _snapshot_dirty(root)
    try:
        with _WriteLock(root):
            for p in sorted(drafts.glob("*.md")):
                card = _read_valid_draft(p, stat)
                if card is None:
                    continue
                # (2026-09-02) 非权威区类型（exp/note/retro）→ 直接改挪 experience/ 保留
                if card.type not in TYPE_DIR:
                    _move_non_authority_draft(root, p, card, stat)
                    continue
                cands = dedup_candidates(root, card)
                if cands:
                    _handle_duplicate_draft(root, platform, p, card, cands, stat, chat_fn)
                    continue
                if card.type in HIGH_RISK:
                    _stage_pending_draft(root, p, card, stat)
                else:
                    _promote_or_conflict_draft(root, platform, p, card, stat)
                p.unlink()
            _commit(root, f"sync: ingest {platform} draft → hub", protect=protect)
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
    protect = _snapshot_dirty(root)  # §4 工作区守护：只提交本次确认产生的改动
    with _WriteLock(root):
        card = read_card(src)
        card.status = "active"
        card.reuse_count = 0
        # 目标目录跟随卡片类型（复用 ingest 的 TYPE_DIR 映射；此前硬编码 rules/，
        # methodology/exp 等待确认卡无法经 CLI 提升）
        dst = root / TYPE_DIR.get(card.type) / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(write_card(card), encoding="utf-8")
        src.unlink()
        _append_log(root, "confirm", f"确认卡片：{name} → {dst.parent.name}/")
        _commit(root, f"sync: confirm {card.type} {name}", protect=protect)
    return dst
