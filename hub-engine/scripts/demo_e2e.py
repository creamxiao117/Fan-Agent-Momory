"""端到端演示：一条真实 AutoCAD DLL 规则走通 沉淀→提炼→确认→复用"""
from datetime import date
from pathlib import Path

from common.frontmatter import write_card, parse_card
from scripts.bootstrap_hub import bootstrap
from sync import append_log, confirm_rule, ingest
from tools.retrieve import retrieve


def run_demo(root: str | Path) -> dict:
    root = Path(root)
    bootstrap(root)

    # 1) 平台复盘沉淀到暂存区
    draft = root / ".sync" / "drafts" / "trae_draft"
    draft.mkdir(parents=True, exist_ok=True)
    retro = draft / "retro"
    retro.mkdir(parents=True, exist_ok=True)
    (retro / "retro-2026-08-17.md").write_text(
        f"""# 复盘 {date.today().isoformat()}
今天改完插件 DLL 直接覆盖源文件，结果被 AutoCAD 占用锁住，最后只能递增版本号解决。
教训：修改 DLL 后必须递增版本号，绝不能原地覆盖同名文件。
""", encoding="utf-8")

    # 2) 提炼 → 候选
    from tools.distill import distill
    distill(root, "trae")
    cand_dir = root / ".sync" / "drafts" / "trae_draft" / "candidates"
    cands = sorted(cand_dir.glob("*.md"))

    # 3) 把候选改为规则暂存，走 ingest（规则 → 待确认）
    rule_draft = draft / "dll-version-lock.md"
    card = parse_card(cands[0].read_text(encoding="utf-8"))
    card.type = "rule"
    card.tags = ["autocad", "dll-lock"]
    card.status = "candidate"
    rule_draft.write_text(write_card(card), encoding="utf-8")

    stat = ingest(root, "trae")
    assert stat["pending"] == 1, stat

    # 4) 人工确认 → 提升到 rules/
    dst = confirm_rule(root, "dll-version-lock.md")

    # 5) 复用：查询能命中该规则
    hits = retrieve(root, "DLL 被 AutoCAD 锁住了怎么办")
    append_log(root, "reuse", f"查询命中 {len(hits)} 条")

    # 6) 查询产物回写：好答案→新经验卡片（写入暂存区后自动入区）
    insight = parse_card(f"""---
type: exp
tags:
  - autocad
  - dll-lock
  - writeback
updated: 2026-08-17
status: candidate
reuse_count: 0
---
查询"DLL 被锁"命中规则后确认：预防优于补救——开发期即采用递增版本命名，避免发布后被 AutoCAD 锁文件。
""")
    insight.type = "exp"
    qwb = root / ".sync" / "drafts" / "trae_draft" / "query-writeback.md"
    qwb.write_text(write_card(insight), encoding="utf-8")
    ingest(root, "trae")  # exp 属低风险 → 自动入区仅记日志

    return {"confirmed": dst.name, "hits": [h.path.name for h in hits]}


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else r"D:\AIwork\AgentMemoryHub"
    print(run_demo(target))
