# @version V1.0 / 2026-10-02 / pi / 任务级能力装配：装 → 验 → 卸 + 残留检测（M3/Task 21）
"""task_capability —— 任务级（project scope）能力装配的**唯一机制**（架构重构 M3/Task 21）。

## 为什么需要它（用户的原始诉求）

> 常用的能力直接装在 agent 里；不常用的/特定的，在任务建立初期**按任务计划临时安装**，
> 任务结束**卸载**；也可任务中途发现缺口再补装。

没有这个机制，"临时装"必然退化成"永久装"——因为**没有卸载路径**。
所以本模块的重点不是"复制文件"，而是三件套：**install → verify → remove(verify)** + **残留检测**。

## 落点（见 `docs/compose/reports/2026-10-02-task-scope-capability-survey.md`）

| 平台 | task scope 落点 | 状态 |
|---|---|---|
| **pi** | `<project>/.pi/skills/<name>/`（官方文档「Project `.pi` directory」） | ✅ 本模块支持 |
| 其他 | 未发现任务级配置 ⇒ 退化为"建议 + 提示 + 残留检测" | 不做 |

## 安全约束（SkillHub `hub.config.yaml` 的既有纪律）

- **外部仓内容不可信**：只**复制**文件，绝不执行 / 安装依赖 / 外发（`guard_import_untrusted`）
- 技能名**白名单化**（防路径穿越）：只允许 SkillHub 里**实际存在**的技能名
- 目标已存在则**拒绝**（除非 `--force`），避免覆盖用户已有内容
- 每次动作都写**账本**（`.sync/state/task_caps.jsonl`，追加式），供残留检测与审计

## 用法

    python -m scripts.task_capability list   --root <hub> [--project <dir>]
    python -m scripts.task_capability install --root <hub> --skill <name> --project <dir>
    python -m scripts.task_capability verify  --root <hub> --skill <name> --project <dir>
    python -m scripts.task_capability remove  --root <hub> --skill <name> --project <dir>
    python -m scripts.task_capability residue --root <hub> [--days 7]

退出码：0 成功｜1 失败（含"验不过"）｜2 残留告警
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

CST = timezone(timedelta(hours=8))
LEDGER_REL = Path(".sync") / "state" / "task_caps.jsonl"
DEFAULT_RESIDUE_DAYS = 7
SKILL_ENTRY = "SKILL.md"


# ── 技能来源（SkillHub 是唯一源；不硬编码清单）─────────────────────


def skillhub_skills(root: Path) -> dict[str, Path]:
    """SkillHub 里可安装的技能 `{name: 目录}`（递归找含 SKILL.md 的目录）。"""
    from common.config import HubConfig, external_path  # 与外层「SkillHub 唯一源」定位一致

    hub_path = external_path("skillhub", root) or (HubConfig.load(root).data.get("external_paths") or {}).get(
        "skillhub"
    )
    if not hub_path:
        return {}
    base = Path(str(hub_path)) / "skills"
    if not base.is_dir():
        return {}
    out: dict[str, Path] = {}
    for entry in base.rglob(SKILL_ENTRY):
        if entry.parent.name.startswith("."):
            continue
        out.setdefault(entry.parent.name, entry.parent)
    return out


# ── 账本（追加式；残留检测的输入）─────────────────────────────────


def ledger_path(root: Path) -> Path:
    return root / LEDGER_REL


def append_ledger(root: Path, action: str, skill: str, project: str, *, ok: bool, detail: str = "") -> None:
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "action": action,
        "skill": skill,
        "project": str(project),
        "deploy_scope": "task",
        "ok": ok,
        "detail": detail[:200],
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def ledger_rows(root: Path) -> list[dict]:
    p = ledger_path(root)
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


# ── 三件套 ────────────────────────────────────────────────────


def target_dir(project: Path, skill: str) -> Path:
    return project / ".pi" / "skills" / skill


def install(root: Path, skill: str, project: Path, *, force: bool = False) -> tuple[bool, str]:
    """把 SkillHub 里的技能复制到**项目级** `.pi/skills/`（task scope）。"""
    src = skillhub_skills(root).get(skill)
    if src is None:
        return False, f"SkillHub 里没有技能 {skill!r}（不猜路径；先确认已登记）"
    dst = target_dir(project, skill)
    if dst.exists() and not force:
        return False, f"目标已存在：{dst}（加 --force 覆盖；拒绝静默覆盖用户内容）"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        shutil.rmtree(dst)
    # 只复制文件，**不执行**任何内容（外部仓内容不可信）
    shutil.copytree(src, dst)
    ok, detail = verify(project, skill)
    append_ledger(root, "install", skill, project, ok=ok, detail=detail)
    return ok, f"已装到 {dst}；{detail}"


def verify(project: Path, skill: str) -> tuple[bool, str]:
    """**验证装上/卸掉**都要证据（无证据不上架；见架构重构 P-4）。"""
    dst = target_dir(project, skill)
    if not dst.is_dir():
        return False, f"目标不存在：{dst}"
    entry = dst / SKILL_ENTRY
    if not entry.is_file():
        return False, f"缺少 {SKILL_ENTRY}：{entry}"
    files = sum(1 for _ in dst.rglob("*") if _.is_file())
    head = entry.read_text(encoding="utf-8", errors="ignore")[:200].replace("\n", " ")
    return True, f"存在 {files} 个文件；SKILL.md 首行：{head[:80]}"


def remove(root: Path, skill: str, project: Path) -> tuple[bool, str]:
    dst = target_dir(project, skill)
    if not dst.exists():
        append_ledger(root, "remove", skill, project, ok=True, detail="本就不存在（幂等）")
        return True, f"目标本就不存在：{dst}（幂等，视为已卸）"
    shutil.rmtree(dst)
    ok, detail = verify(project, skill)  # 期望 False
    gone = not ok
    append_ledger(root, "remove", skill, project, ok=gone, detail="已卸载并验证不存在" if gone else detail)
    return gone, ("已卸载并验证不存在" if gone else f"卸载后仍可见：{detail}")


def residue(root: Path, days: int = DEFAULT_RESIDUE_DAYS) -> list[dict]:
    """残留检测：**装了但从未卸载**且已超期的 task-scope 能力。

    这是"临时装 → 永久装"退化的唯一防线：没有它，task scope 就是个说辞。
    """
    cutoff = datetime.now(CST) - timedelta(days=days)
    installed: dict[tuple[str, str], str] = {}
    for row in ledger_rows(root):
        key = (row.get("skill", ""), row.get("project", ""))
        if row.get("action") == "install" and row.get("ok"):
            installed[key] = row.get("ts", "")
        elif row.get("action") == "remove" and row.get("ok"):
            installed.pop(key, None)
    out = []
    for (skill, project), ts in installed.items():
        if not ts:
            continue
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if when < cutoff and target_dir(Path(project), skill).is_dir():
            out.append(
                {"skill": skill, "project": project, "installed_at": ts, "age_days": (datetime.now(CST) - when).days}
            )
    out.sort(key=lambda r: -r["age_days"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="任务级能力装配（装/验/卸 + 残留检测）")
    ap.add_argument("action", choices=("list", "install", "verify", "remove", "residue"))
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--skill", default=None)
    ap.add_argument("--project", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--days", type=int, default=DEFAULT_RESIDUE_DAYS)
    args = ap.parse_args(argv)

    root = args.root or (_HUB_ENGINE.parent / "AgentMemoryHub")
    if args.action == "list":
        skills = skillhub_skills(root)
        print(f"SkillHub 可安装技能 {len(skills)} 个：" + ", ".join(sorted(skills)[:20]))
        return 0
    if args.action == "residue":
        res = residue(root, args.days)
        if not res:
            print(f"✅ 无残留（{args.days} 天内未结算的 task-scope 能力）")
            return 0
        print(f"⚠️ 残留 {len(res)} 项（task scope 装了但未卸载）：")
        for r in res:
            print(f"  - {r['skill']} @ {r['project']}（已 {r['age_days']} 天）")
        return 2
    if not args.skill:
        print("--skill 必填", file=sys.stderr)
        return 1
    if args.action in ("install", "remove"):
        if not args.project:
            print(f"--project 必填（{args.action} 的落点是**项目级** .pi/skills/）", file=sys.stderr)
            return 1
        fn = install if args.action == "install" else remove
        ok, detail = fn(root, args.skill, args.project, **({"force": args.force} if args.action == "install" else {}))
        print(("✅ " if ok else "❌ ") + f"{args.action} {args.skill}：{detail}")
        return 0 if ok else 1
    ok, detail = verify(args.project or Path("."), args.skill)
    print(("✅ " if ok else "❌ ") + f"verify {args.skill}：{detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
