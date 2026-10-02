"""记忆中枢系统性体检（只读）。逐项给**可复核**的结论，不猜。

覆盖面：卡片 / 索引与预算 / 门禁 / 引擎台账 / 平台与能力 / 数据完整性 / 文档漂移。
输出按严重度分组，每条附证据（数字或路径），便于人工裁定。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HUB = REPO / "AgentMemoryHub"
sys.path.insert(0, str(REPO / "hub-engine"))

FIND: dict[str, list[str]] = defaultdict(list)

# 目录 → 应有的 type（frontmatter.py 的搬运口径）
EXPECTED_TYPE = {
    "rules": "rule",
    "blueprints": "blueprint",
    "methodology": "methodology",
    "longterm": "longterm",
    "projects": "project",
    "experience": "exp",
}


def bad(sev: str, msg: str) -> None:
    FIND[sev].append(msg)


# ── 1. 卡片层 ────────────────────────────────────────────────
def _check_card_meta(d, p, c, missing_grade, bad_grade, bad_type, old) -> None:  # noqa: ANN001
    """单卡 frontmatter 检查（从 `audit_cards` 拆出以降低圈复杂度）。"""
    from common.frontmatter import GRADES_BY_DIR, VALID_GRADES

    grade = str(c.extra.get("grade") or "").strip()
    if not grade:
        missing_grade.append(f"{d}/{p.name}")
    elif grade not in VALID_GRADES:
        bad_grade.append(f"{d}/{p.name}={grade}")
    elif GRADES_BY_DIR.get(d) and grade not in GRADES_BY_DIR[d]:
        bad_grade.append(f"{d}/{p.name}={grade}（该目录只许 {sorted(GRADES_BY_DIR[d])}）")
    # type 是卡对象的一等属性（`c.type`），**不在** `extra` 里（2026-10-02 实测）
    typ = str(getattr(c, "type", "") or "").strip()
    if not typ:
        bad_type.append(f"{d}/{p.name}")
    elif typ != EXPECTED_TYPE.get(d):
        bad_type.append(f"{d}/{p.name}: type={typ}（该目录应为 {EXPECTED_TYPE.get(d)}）")
    up = str(c.extra.get("updated") or "").strip().strip("'\"")
    if not up:
        return
    try:
        if (date.today() - date.fromisoformat(up)).days > 365:
            old.append(f"{d}/{p.name}@{up}")
    except ValueError:
        bad("P1", f"updated 日期非法：{d}/{p.name}={up}")


def audit_cards() -> None:
    from common.frontmatter import try_read_card

    dirs = ("rules", "blueprints", "methodology", "longterm", "projects", "experience")
    cards: dict[str, list[Path]] = defaultdict(list)
    missing_grade, bad_grade, bad_type, old = [], [], [], []
    n = 0
    for d in dirs:
        for p in sorted((HUB / d).glob("*.md")):
            c = try_read_card(p)
            if c is None:
                bad("P0", f"卡片解析失败：{d}/{p.name}")
                continue
            n += 1
            cards[p.stem].append(p)
            _check_card_meta(d, p, c, missing_grade, bad_grade, bad_type, old)
    print(f"[卡片] 权威区 {n} 张")
    if missing_grade:
        bad("P0", f"缺 grade：{len(missing_grade)} 张（例：{missing_grade[:3]}）")
    if bad_grade:
        bad("P0", f"grade 非法/与目录不匹配：{len(bad_grade)} 张（例：{bad_grade[:3]}）")
    if bad_type:
        bad("P0", f"缺 type：{len(bad_type)} 张")
    if old:
        bad("P2", f"updated 超一年：{len(old)} 张（例：{old[:3]}）")
    dup = {k: v for k, v in cards.items() if len(v) > 1}
    if dup:
        bad("P1", f"同名卡跨目录重复：{len(dup)} 组 → {list(dup.items())[:3]}")

    # iron 必须绑 gate（D7）
    no_gate = []
    for p in sorted((HUB / "rules").glob("*.md")):
        c = try_read_card(p)
        if c and str(c.extra.get("grade")) == "iron" and not str(c.extra.get("gate") or "").strip():
            no_gate.append(p.name)
    if no_gate:
        bad("P0", f"iron 卡未绑 gate：{no_gate}")


def audit_card_refs() -> None:
    r"""悬空指针检查（从 `audit_cards` 拆出以降低复杂度）。

    分两类（**这是本审计最容易误报的一处**）：
    - 悬空指针：`见 \`X\`` / `依据 \`X\`` —— 认为 X 还在 ⇒ 缺陷
    - 删除记录：`已并入` / `已被删` / `superseded` —— **必须提到它**才对 ⇒ 非缺陷

    判据用「**git 历史上真的被删除过的卡名**」求交 —— UUID / 外部仓名 /
    Rust target triple 之类因此自动落空（先前的宽松版报 74 个，几乎全假阳性；
    坏尺子比没尺子更糟）。
    """
    dirs = ("rules", "blueprints", "methodology", "longterm", "projects", "experience")
    known = {p.stem for d in dirs for p in (HUB / d).glob("*.md")}
    dangling: dict[str, set[str]] = defaultdict(set)
    documented: dict[str, set[str]] = defaultdict(set)
    for d in dirs:
        for p in sorted((HUB / d).glob("*.md")):
            text = p.read_bytes().decode("utf-8", "ignore")
            for ref in re.findall(r"`([a-z0-9]+(?:-[a-z0-9]+){2,})`", text):
                if ref in known or ref.endswith((".py", ".md", ".yaml", ".json", ".ts", ".jsonl")):
                    continue
                if not ("-" in ref and len(ref) > 12):
                    continue
                if _is_deletion_note(text, ref):
                    documented[ref].add(p.stem)
                else:
                    dangling[ref].add(p.stem)

    deleted = _ever_deleted_cards()
    stale = {k: v for k, v in dangling.items() if k in deleted}
    noted = {k: v for k, v in documented.items() if k in deleted}
    print(
        f"[卡片] 正文疑似卡名 {len(dangling) + len(documented)} 个 → 确属已删卡："
        f"**悬空指针 {len(stale)}** / 删除记录 {len(noted)}"
    )
    for k, v in sorted(stale.items()):
        bad("P1", f"悬空指针：引用了**已删除的卡** `{k}`（{len(v)} 张卡：{sorted(v)}）")
    for k, v in sorted(noted.items()):
        print(f"  （说明性提及，非缺陷）`{k}` ← {sorted(v)}")


DELETION_MARKERS = (
    "已删除",
    "已删",
    "被删",
    "删除",
    "已并入",
    "并入",
    "merged into",
    "superseded",
    "supersede",
    "已弃用",
    "弃用",
    "deprecated",
    "已退役",
    "退役",
    "归档",
    "原 4 张",
    "合并",
)


def _is_deletion_note(text: str, ref: str) -> bool:
    """引用附近（±120 字符）是否在**说明"它已不在了"**。

    判据是启发式（不追求形式化），但足够把"记录删除"从"悬空指针"里分出来 ——
    坏尺子比没尺子更糟，所以宁可把说明性提及单独分类，也不把它们算成缺陷。
    """
    i = text.find(ref)
    while i != -1:
        window = text[max(0, i - 120) : i + len(ref) + 120]
        if any(m in window for m in DELETION_MARKERS):
            return True
        i = text.find(ref, i + 1)
    return False


def _ever_deleted_cards() -> set[str]:
    """本仓 git 历史上**曾被删除**的卡名（含重命名源）—— 判"悬空引用"的判据。"""
    r = subprocess.run(
        ["git", "-C", str(HUB), "log", "--all", "--diff-filter=AD", "--name-only", "--pretty=format:"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    out: set[str] = set()
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.endswith(".md") and "/" in line:
            out.add(Path(line).stem)
    return out


def _skillhub_names() -> set[str]:
    """SkillHub 全部技能名（含路由记录名）—— 排除它们，避免把外部能力误判成悬空卡。"""
    import yaml

    from common.config import external_path

    hub_path = external_path("skillhub", HUB)
    if not hub_path:
        return set()
    sh = Path(str(hub_path))
    out: set[str] = set()
    f = sh / "router" / "router.yaml"
    if f.is_file():
        try:
            for r in (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("skills") or []:
                if isinstance(r, dict) and r.get("name"):
                    out.add(str(r["name"]))
        except Exception:  # noqa: BLE001
            pass
    out |= {p.parent.name for p in (sh / "skills").rglob("SKILL.md")}
    return out


# ── 2. 索引与启动预算 ────────────────────────────────────────
def audit_index_budget() -> None:
    for f, cap in (("AGENTS.md", 2000), ("WORK.md", 5000)):
        p = REPO / f
        if p.is_file():
            n = len(p.read_text(encoding="utf-8"))
            flag = "✅" if n <= cap else "❌"
            print(f"[预算] {f}: {n}/{cap} {flag}")
            if n > cap:
                bad("P1", f"L0 预算超限：{f} {n}>{cap}")
    p = HUB / "INDEX.md"
    if p.is_file():
        n = len(p.read_text(encoding="utf-8"))
        print(f"[预算] INDEX.md: {n} 字符")
        if n > 6000:
            bad("P2", f"INDEX.md 偏大：{n} 字符（L0 能力图，建议 <6000）")


# ── 3. 门禁与关联纪律 ────────────────────────────────────────
def audit_gates() -> None:
    # 中枢只有**一个** `pre-commit` 文件：三道门禁（编码/卡片 frontmatter/渲染一致性）
    # 都在它里面，由 `scripts/gate_runner.py` 按 scope 分派（2026-10-02 实测）
    hook = HUB / ".git" / "hooks" / "pre-commit"
    if not hook.exists():
        bad("P0", "提交门禁缺失：.git/hooks/pre-commit")
    else:
        text = hook.read_text(encoding="utf-8", errors="ignore")
        if "gate_runner" not in text:
            bad("P0", "pre-commit 未走 gate_runner（旧实现残留）")
        if "hub-cards" not in text:
            bad("P1", "pre-commit 缺卡片 frontmatter 门禁（[hub-cards] 分派）")
        print("[门禁] pre-commit 走 gate_runner + 含卡片门禁 ✅")
    # index 物化检查
    r = subprocess.run(
        [sys.executable, "-m", "scripts.render_index", "--check"],
        cwd=REPO / "hub-engine",
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        bad("P0", f"INDEX 渲染不一致：{r.stdout.strip()[:120]}")
    else:
        print("[门禁] INDEX 渲染一致 ✅")


# ── 4. 引擎与台账 ────────────────────────────────────────────
def audit_engine() -> None:
    inv = HUB / "scripts" / "INVENTORY.json"
    if not inv.is_file():
        bad("P1", "台账 INVENTORY.json 缺失")
        return
    data = json.loads(inv.read_text(encoding="utf-8"))
    # modules 是**记录列表**（每条含 module/path/verdict…），不是名字集合
    # 用 `path` 字段比对（`module` 对 scripts/ 省略了前缀，直接比会假阳性）
    declared = {
        str(m.get("path")).removeprefix("hub-engine/").removesuffix(".py")
        for m in (data.get("modules") or [])
        if m.get("path")
    }
    all_py = {
        str(p.relative_to(REPO / "hub-engine").with_suffix("")).replace("\\", "/")
        for p in (REPO / "hub-engine").rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "__init__.py"
    }
    # 台账只覆盖 hub-engine 的代码面；tests/ 与一次性脚本（`_` 前缀）不在其职责内
    actual = {a for a in all_py if not a.startswith("tests/") and not Path(a).name.startswith("_")}
    stale = sorted(declared - actual)
    new = sorted(actual - declared)
    # verdict 分布（台帐的结论要能看到）
    verdict: dict[str, int] = {}
    for m in data.get("modules") or []:
        verdict[str(m.get("verdict"))] = verdict.get(str(m.get("verdict")), 0) + 1
    print(f"[台账] verdict 分布：{verdict}")
    unreviewed = [m["module"] for m in (data.get("modules") or []) if m.get("verdict") == "review"]
    if unreviewed:
        bad("P2", f"台账未裁定（review）：{len(unreviewed)} 个 → {unreviewed[:6]}")
    print(f"[台账] 登记 {len(declared)} / 实际 {len(actual)}")
    if stale:
        bad("P1", f"台账登记了但磁盘没有：{stale[:6]}")
    if new:
        bad("P1", f"磁盘有但台账未登记：{new[:6]}")

    # 门禁脚本必须能被 import（语法/依赖问题会在这里爆）
    for rel in ("scripts/gate_runner.py", "scripts/capability_scan.py", "scripts/task_capability.py", "engine.py"):
        f = REPO / "hub-engine" / rel
        if f.is_file():
            r = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import ast,pathlib,sys;ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))",
                    str(f),
                ],
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                bad("P0", f"语法错误：{rel}")
    print("[引擎] 关键脚本语法 ✅")


# ── 5. 数据完整性 ────────────────────────────────────────────
def audit_data() -> None:
    retro = HUB / "retro"
    snaps = sorted(retro.glob("snapshot-*.json")) if retro.is_dir() else []
    print(f"[数据] retro snapshot {len(snaps)} 份（T1 度量输入，不可清理）")
    if len(snaps) < 5:
        bad("P1", f"T1 度量快照过少：{len(snaps)} 份（历史被误删？）")
    locks = HUB / ".sync" / "locks"
    if locks.is_dir():
        active = locks / "writer.lock"
        if active.is_file():
            bad("P0", f"写者锁**活动残留**：{active}（有写入者崩溃未释放；确认无进程后清理）")
        debris = sorted(p.name for p in locks.iterdir() if p.is_file() and ".bak-" in p.name)
        print(f"[数据] 锁目录：活动锁 {'有' if active.is_file() else '无'}；历史 debris {len(debris)} 个（未跟踪）")
    led = HUB / ".sync" / "state" / "task_caps.jsonl"
    if led.is_file():
        rows = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines() if x.strip()]
        open_installs = defaultdict(int)
        for r in rows:
            open_installs[(r.get("skill"), r.get("project"))] += 1 if r.get("action") == "install" else -1
        live = {k: v for k, v in open_installs.items() if v > 0}
        print(f"[数据] task 装/卸账本 {len(rows)} 行；未结算 {len(live)} 项")
        if live:
            bad("P2", f"task-scope 未结算：{list(live)[:3]}")


# ── 6. 文档漂移 ──────────────────────────────────────────────
def audit_extra_dirs() -> None:
    """权威区之外的目录（`archive/` `optimize/` `notes/` 等）——确认它们**不参与检索/注入**。"""
    known = {
        "rules",
        "blueprints",
        "methodology",
        "longterm",
        "projects",
        "experience",
        "notes",
        "retro",
        "system",
        "scripts",
        ".sync",
        "optimize",
        "archive",
        "skills",
        "templates",
        "assets",
        "docs",
        # 已裁定：都不是卡片区，**不参与检索/注入**
        "libs",  # 已跟踪的项目资产（如 libs/hermes-desktop-rebuild/ 的补丁与脚本）
        "raw",  # 空的本地落地区（未跟踪；有内容时再裁定）
    }
    # 只关心**非空**的未知目录：空目录不构成风险
    extra = sorted(
        d.name
        for d in HUB.iterdir()
        if d.is_dir() and not d.name.startswith(".") and d.name not in known and any(d.iterdir())
    )
    if extra:
        bad("P2", f"中枢出现了**非空**的未归类目录：{extra}（须裁定是否参与检索）")
    for d in ("archive", "optimize"):
        p = HUB / d
        if p.is_dir():
            n = sum(1 for _ in p.rglob("*.md"))
            print(f"[目录] {d}/：{n} 个 md（历史归档，应不参与检索/注入）")


def audit_drift() -> None:
    docs = [REPO / "AGENTS.md", REPO / "WORK.md", REPO / "CHARTER.md", HUB / "INDEX.md"]
    dead_scripts = [
        "audit_dead_modules.py",
        "migrate_grade.py",
        "mcp_healthcheck.py",
        "platform_unregistered.py",
        "_oneshot_rules_tighten.py",
    ]
    for d in docs:
        if not d.is_file():
            bad("P1", f"L0 文件缺失：{d.name}")
            continue
        text = d.read_text(encoding="utf-8")
        for s in dead_scripts:
            if s in text and not (REPO / "hub-engine" / "scripts" / s).exists():
                bad("P2", f"文档漂移：{d.name} 提到已退役的 {s}")
        if "platforms.yaml" in text and not (HUB / "system" / "platforms.yaml").exists():
            bad("P2", f"文档漂移：{d.name} 提到已退役的 system/platforms.yaml")
    print("[漂移] 已检查 L0 文件与被退役产物")


def collect(root: Path | None = None) -> dict[str, list[str]]:
    """进程内入口：跑全部检查并返回 `{P0/P1/P2: [说明]}`（**吞掉打印**）。

    巡检步骤要的是结构化结论而不是 stdout 文本 —— 靠字符串匹配 stdout 判"有没有问题"
    是脆弱写法（措辞一改就失效）。
    """
    import contextlib
    import io

    global HUB
    if root is not None:
        HUB = Path(root)
    FIND.clear()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit_cards()
        audit_card_refs()
        audit_index_budget()
        audit_gates()
        audit_engine()
        audit_data()
        audit_extra_dirs()
        audit_drift()
    return {sev: list(FIND.get(sev) or []) for sev in ("P0", "P1", "P2")}


def main() -> int:
    audit_cards()
    audit_index_budget()
    audit_gates()
    audit_engine()
    audit_data()
    audit_extra_dirs()
    audit_drift()
    print("\n" + "=" * 68)
    order = ["P0", "P1", "P2"]
    title = {"P0": "必修（正确性/纪律已破）", "P1": "应修（一致性/完整性）", "P2": "可议（卫生/待裁定）"}
    total = 0
    for sev in order:
        items = FIND.get(sev) or []
        total += len(items)
        print(f"\n## {sev}·{title[sev]}：{len(items)} 项")
        for m in items:
            print(f"  - {m}")
    if not total:
        print("\n✅ 未发现问题")
    print(f"\n合计 {total} 项发现（{datetime.now():%Y-%m-%d %H:%M}）")
    return 1 if (FIND.get("P0") or FIND.get("P1")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
