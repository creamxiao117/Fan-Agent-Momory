# @version V1.0 / 2026-09-09 / Hermes / 双仓 stale 检测
"""stale_detect.py —— 改进3 落地，标记长期未复用的卡片/技能。

V1.0 (2026-09-09): 扫描中枢卡 + SkillHub 技能，
根据 reuse_count + updated_at 判断是否 stale。
不删除任何文件，仅生成 stale 报告供人审核。
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import yaml

DEFAULT_DAYS_STALE = 90  # 90 天未更新 + 0 复用 = stale


def _parse_updated(value) -> dt.date | None:
    if not value:
        return None
    if isinstance(value, dt.date):
        return value
    s = str(value)[:10]
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def detect_stale_cards(hub_root: Path, *, days: int = DEFAULT_DAYS_STALE) -> list[dict]:
    """扫描中枢权威区，标记 stale 卡。"""
    out: list[dict] = []
    cutoff = dt.date.today() - dt.timedelta(days=days)
    for sub in ("rules", "methodology", "blueprints", "experience", "longterm", "projects"):
        d = hub_root / sub
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            try:
                text = f.read_text(encoding="utf-8")
            except OSError:
                continue
            if not text.startswith("---\n"):
                continue
            try:
                end = text.index("\n---\n", 4)
                fm = yaml.safe_load(text[4:end]) or {}
            except (ValueError, yaml.YAMLError):
                continue
            rc = fm.get("reuse_count", 0) or 0
            upd = _parse_updated(fm.get("updated"))
            if rc == 0 and upd and upd < cutoff:
                out.append({
                    "kind": "card",
                    "path": str(f.relative_to(hub_root)),
                    "name": f.stem,
                    "type": fm.get("type", sub),
                    "updated": str(upd),
                    "age_days": (dt.date.today() - upd).days,
                    "reuse_count": rc,
                })
    return out


def detect_stale_skills(skillhub_root: Path, *, days: int = DEFAULT_DAYS_STALE) -> list[dict]:
    """扫描 SkillHub，标记 stale 技能。"""
    out: list[dict] = []
    cutoff = dt.date.today() - dt.timedelta(days=days)
    for slot in ("shared", "dedicated"):
        d = skillhub_root / "skills" / slot
        if not d.exists():
            continue
        for f in d.rglob("skill.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (yaml.YAMLError, OSError):
                continue
            rc = data.get("reuse_count", 0) or 0
            upd = _parse_updated(data.get("updated"))
            if rc == 0 and upd and upd < cutoff:
                out.append({
                    "kind": "skill",
                    "path": str(f.relative_to(skillhub_root)),
                    "name": data.get("name", f.parent.name),
                    "updated": str(upd),
                    "age_days": (dt.date.today() - upd).days,
                    "reuse_count": rc,
                })
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="双仓 stale 检测")
    ap.add_argument("--hub-root", required=True)
    ap.add_argument("--skillhub-root", required=True)
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS_STALE)
    args = ap.parse_args()

    cards = detect_stale_cards(Path(args.hub_root), days=args.days)
    skills = detect_stale_skills(Path(args.skillhub_root), days=args.days)

    print(f"Stale 卡片：{len(cards)} 张")
    for c in cards[:5]:
        print(f"  - {c['path']} (updated={c['updated']}, age={c['age_days']}d)")
    if len(cards) > 5:
        print(f"  ... 共 {len(cards)} 张")
    print(f"Stale 技能：{len(skills)} 个")
    for s in skills[:5]:
        print(f"  - {s['path']} (updated={s['updated']}, age={s['age_days']}d)")
    if len(skills) > 5:
        print(f"  ... 共 {len(skills)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
