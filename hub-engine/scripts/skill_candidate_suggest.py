"""skill_candidate_suggest.py —— 改进2 落地，经验 → 技能建议卡生成器。

V1.0 (2026-09-09): 扫描中枢 exp 卡 reuse_count >= 3 的条目，
在 SkillHub cards/ 目录生成"技能建议卡"，供 Fan 周审。

设计原则：
- 不自动升级，仅生成建议（用户决策）
- 幂等（同名卡存在则覆盖更新）
- 不破坏已有 cards 目录结构
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import yaml

THRESHOLD = 3
OUTPUT_DIR = "skill-candidates"


def find_hot_cards(hub_root: Path, threshold: int = 3) -> list[dict]:
    """扫描中枢 experience/ 目录，提取 reuse_count >= 阈值的卡片。"""
    exp_dir = hub_root / "experience"
    if not exp_dir.exists():
        return []
    hot = []
    for f in sorted(exp_dir.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.startswith("---\n"):
            continue
        try:
            end = text.index("\n---\n", 4)
            fm = yaml.safe_load(text[4:end])
        except (ValueError, yaml.YAMLError):
            continue
        if not isinstance(fm, dict):
            continue
        rc = fm.get("reuse_count", 0) or 0
        if rc >= threshold:
            hot.append({
                "path": str(f.relative_to(hub_root)),
                "name": f.stem,
                "type": fm.get("type", "exp"),
                "title": fm.get("title", f.stem),
                "reuse_count": rc,
                "tags": fm.get("tags", []),
            })
    return hot


def write_suggestion_card(card: dict, skillhub_root: Path, threshold: int = 3) -> Path:
    """在 SkillHub cards/skill-candidates/ 生成一张建议卡。"""
    out_dir = skillhub_root / "cards" / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    out = out_dir / f"{card['name']}.md"
    body = f"""---
type: skill-candidate
status: pending-review
source: {card['path']}
reuse_count: {card['reuse_count']}
detected_at: '{today}'
---

# 技能建议：{card['title']}

## 建议依据

- 源卡：`{card['path']}`
- 复用次数：{card['reuse_count']}（阈值 {threshold}）
- 类型：{card['type']}
- 标签：{', '.join(card.get('tags', []))}

## 下一步

- [ ] 评估是否升级为 SkillHub 技能
- [ ] 若升级：创建 `skills/shared/<name>/SKILL.md` + `skill.yaml`
- [ ] 在 `router/router.yaml` 注册 trigger/forgot
- [ ] 跑 T1 验证
"""
    out.write_text(body, encoding="utf-8")
    return out


def main() -> int:
    """CLI 入口：扫描中枢 + 生成建议卡。"""
    import argparse

    ap = argparse.ArgumentParser(description="exp → skill candidate 流水线")
    ap.add_argument("--hub-root", required=True, help="中枢根目录")
    ap.add_argument("--skillhub-root", required=True, help="SkillHub 根目录")
    ap.add_argument("--threshold", type=int, default=THRESHOLD)
    args = ap.parse_args()

    hot = find_hot_cards(Path(args.hub_root), threshold=args.threshold)
    if not hot:
        print(f"无 reuse_count >= {args.threshold} 的经验卡")
        return 0

    written = []
    for card in hot:
        p = write_suggestion_card(card, Path(args.skillhub_root), threshold=args.threshold)
        written.append(str(p.relative_to(args.skillhub_root)))
    print(f"生成 {len(written)} 张建议卡：")
    for w in written:
        print(f"  - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
