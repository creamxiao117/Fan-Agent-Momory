# hub-engine/scripts/index_locatability_bench.py
"""INDEX 可定位性基准：改造前（10 字碎片）vs 改造后（卡自身摘要）实测对比。

## 为什么测这个
INDEX 是 L0 目录版，作用是让模型**从条目定位到该读哪张卡**（详情以卡自身为唯一源）。
所以 INDEX 描述的质量直接决定"能否定位"。而 A4 曾用 `slim_index --max-desc 10`
机械截断，条目退化成 `GitHub 仓库选…` 这类碎片——**开销照付，信息近乎为零**。
2026-09-23 改为用卡自身摘要（`regen_index_desc.py`）。

## 这是什么口径（诚实声明）
这是**确定性关键词覆盖**代理指标，**不是模型实验**：
- 对每个（查询 → 期望卡）用例，取出该卡在 INDEX 里的那一行描述，
  用 jieba 分词算「查询内容词被描述覆盖的比例」。
- 含义：描述里若连一个查询内容词都没有，模型光看 INDEX 无从选中该卡。
- 局限：它无法反映语义改写能力，也不测卡正文质量。仅用于回答
  「改造是否让目录从『不可定位』变为『可定位』」。

## 用法
    python -m scripts.index_locatability_bench                    # 与 HEAD 比
    python -m scripts.index_locatability_bench --rev 68088fa^    # 与历史版本比
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.vector import tokenize

REPO_ROOT = Path(__file__).resolve().parents[2]
HUB_REL = "AgentMemoryHub/INDEX.md"
HUB_EXP_REL = "AgentMemoryHub/INDEX-experience.md"
HUB_DIR = REPO_ROOT / "AgentMemoryHub"

# (自然语言需求, 期望命中的卡 slug)
CASES: list[tuple[str, str]] = [
    ("改完代码提交前要跑哪些检查", "agent-code-discipline-iron-rule"),
    ("中文乱码怎么排查，全链路编码规范", "chinese-text-encoding-discipline"),
    ("多个语言的代码风格怎么统一配置", "multi-language-style-config"),
    ("任务类型怎么分档，门禁怎么走", "rules-routing-table"),
    ("两个平台同时写中枢会冲突", "dual-platform-coherence-discipline"),
    ("任务收尾要沉淀经验卡片", "memory-hub-distill-last"),
    ("怎么挑 GitHub 仓库来借鉴", "gh-star-repo-filter-rule"),
    ("agent 改完页面要自己看一眼", "agent-modify-must-view-page"),
    ("上下文占用太高要怎么办", "context-budget-discipline"),
    ("面向用户的产出要用什么语言", "output-language-rule"),
    ("新任务开工前要先对齐需求", "requirement-alignment-first"),
    ("跨平台同步要怎么推送", "cross-platform-sync-rule"),
    ("AutoCAD 插件 DLL 版本要递增", "dll-version-increment-autocad"),
    ("Python 自动化脚本骨架模板", "python-automation-skeleton-blueprint"),
    ("记忆中枢索引怎么维护", "memory-hub-card-promotion"),
    ("检索质量怎么评估和告警", "retrieval-quality-three-loop"),
    ("本地部署的检索模型怎么选型", "local-dense-retrieval-model-selection"),
    ("向量库被别的进程锁住了", "hub-vector-db-locked-by-concurrent-mcp-servers"),
    ("两个仓两套引擎共用向量库的坑", "dual-engine-single-vector-db-meta-contract"),
    ("我的今天待办是空的怎么补", "auto-promote-empty-today-rule"),
]

# 查询里的疑问词/通用词：不构成"定位信号"，剔除后再比
_NOISE = {
    "怎么",
    "什么",
    "如何",
    "哪些",
    "哪个",
    "要",
    "的",
    "了",
    "吗",
    "呢",
    "和",
    "与",
    "以及",
    "是否",
    "可以",
    "需要",
    "应该",
    "我",
    "你",
    "他",
    "是",
    "在",
    "有",
    "对",
    "跑",
    "做",
    "用",
    "会",
    "被",
    "把",
    "从",
    "到",
    "前",
    "后",
    "里",
    "中",
}


def content_tokens(text: str) -> set[str]:
    """内容词集合：jieba 分词 + 去噪声词 + 去单字（单字区分度太低）"""
    toks = set()
    for t in tokenize(text, mode="word"):
        t = t.strip()
        if len(t) < 2 or t in _NOISE:
            continue
        toks.add(t)
    return toks


def card_tags(slug: str) -> list[str]:
    """读卡的 frontmatter tags（用于测试“摘要+标签”变体）"""
    for d in (
        "rules",
        "methodology",
        "blueprints",
        "longterm",
        "projects",
        "experience",
    ):
        p = HUB_DIR / d / f"{slug}.md"
        if not p.exists():
            continue
        raw = p.read_text(encoding="utf-8-sig", errors="replace")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if not m:
            return []
        tags_line = ""
        fm = m.group(1)
        inline = re.search(r"(?m)^tags:\s*\[(.*?)\]\s*$", fm)
        if inline:
            return [t.strip().strip("'\"") for t in inline.group(1).split(",") if t.strip()]
        blk = re.search(r"(?m)^tags:\s*\n((?:\s*-\s*.+\n)*)", fm)
        if blk:
            return [line.strip().lstrip("-").strip().strip("'\"") for line in blk.group(1).splitlines() if line.strip()]
        return [tags_line] if tags_line else []
    return []


def load_index(rev: str | None) -> dict[str, str]:
    """slug → INDEX 描述行；rev 为 None 时读工作区。

    注意：INDEX.md 在**嵌套的中枢仓**（外层仓 gitignore 它），所以必须
    `git -C AgentMemoryHub` 取历史，且路径相对中枢根。
    """
    if rev is None:
        blob = "\n".join(
            (HUB_DIR / name).read_text(encoding="utf-8-sig")
            for name in ("INDEX.md", "INDEX-experience.md")
            if (HUB_DIR / name).exists()
        )
    else:
        blob = ""
        for name in ("INDEX.md", "INDEX-experience.md"):
            r = subprocess.run(
                ["git", "-C", str(HUB_DIR), "show", f"{rev}:{name}"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if r.returncode == 0:
                blob += r.stdout + "\n"
        if not blob.strip():
            print(
                f"[WARN] 未取到 {rev} 的 INDEX（检查是否中枢仓可解析的版本号）",
                file=sys.stderr,
            )

    lines: dict[str, str] = {}
    for ln in blob.splitlines():
        m = re.match(r"^- (?:\*\*)?([^\s*]+?)(?:\*\*)?\s{2,}(.+)$", ln)
        if m:
            lines[m.group(1)] = m.group(2).strip()
    return lines


def score(descs: dict[str, str]) -> dict:
    """返回 {coverage_avg, locatable_n, missing_n, desc_tokens_avg, rows}"""
    rows = []
    for query, slug in CASES:
        desc = descs.get(slug)
        if desc is None:
            rows.append({"query": query, "slug": slug, "covered": 0, "total": 0, "desc": None})
            continue
        qtok = content_tokens(query)
        dtok = content_tokens(desc)
        cov = len(qtok & dtok)
        rows.append(
            {
                "query": query,
                "slug": slug,
                "covered": cov,
                "total": len(qtok),
                "desc": desc,
                "desc_tokens": len(dtok),
            }
        )
    missing = sum(1 for r in rows if r["desc"] is None)
    coverages = [r["covered"] / r["total"] for r in rows if r["total"]]
    locatable = sum(1 for r in rows if r["covered"] >= 1)
    dtok_avg = sum(r.get("desc_tokens", 0) for r in rows) / max(len(rows) - missing, 1)
    return {
        "coverage_avg": sum(coverages) / len(coverages) if coverages else 0.0,
        "locatable": locatable,
        "missing": missing,
        "desc_tokens_avg": dtok_avg,
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="INDEX 可定位性基准（改造前后对比）")
    ap.add_argument("--rev", default=None, help="对比的 git 版本（如 68088fa^）；不带则与工作区比")
    ap.add_argument("--show", action="store_true", help="打印逐例明细")
    args = ap.parse_args(argv)

    old = score(load_index(args.rev))
    new = score(load_index(None))

    # 变体：摘要 + 卡自身 tags（tags 本就是“检索关键词”）——只测不改
    variant = 0
    for query, slug in CASES:
        desc = load_index(None).get(slug) or ""
        merged = desc + " " + " ".join(card_tags(slug))
        if content_tokens(query) & content_tokens(merged):
            variant += 1
    added_chars = sum(len(" ".join(card_tags(s))) for _q, s in CASES if load_index(None).get(s))

    label_old = f"改造前（{args.rev}）" if args.rev else "对照（--rev 未指定，两侧相同）"
    print("=" * 76)
    print("INDEX 可定位性基准（确定性关键词覆盖代理指标）")
    print("=" * 76)
    print(f"用例数: {len(CASES)}")
    print()
    print(f"{'指标':30s} {label_old:24s} {'改造后':>24s}")
    print("-" * 76)
    print(
        f"{'可定位用例数（≥1 个内容词命中）':30s} "
        f"{old['locatable']:>10d}/{len(CASES):<12d} {new['locatable']:>10d}/{len(CASES):<12d}"
    )
    print(f"{'平均内容词覆盖率':30s} {old['coverage_avg']:>22.1%} {new['coverage_avg']:>24.1%}")
    print(f"{'描述平均内容词数':30s} {old['desc_tokens_avg']:>22.1f} {new['desc_tokens_avg']:>24.1f}")
    print(f"{'描述缺失（未登记）用例数':30s} {old['missing']:>22d} {new['missing']:>24d}")
    print()
    print(f"〔变体〕摘要+卡 tags 的可定位用例数: {variant}/{len(CASES)}（当前 {new['locatable']}/{len(CASES)}）")
    print(f"〔变体〕仅本用例集就要额外 {added_chars} 字符；全量 251 条保守估计 +8~10K，会突破 30K 总帽 → 不可直接采用")

    if args.show:
        print()
        print("逐例（前 12）：")
        for o, n in list(zip(old["rows"], new["rows"], strict=False))[:12]:
            print(f"  查询: {o['query']}")
            print(f"    旧 {o['covered']}/{o['total']}  {str(o['desc'])[:52]}")
            print(f"    新 {n['covered']}/{n['total']}  {str(n['desc'])[:52]}")

    print()
    print("口径说明：这是确定性关键词覆盖**代理指标**，不是模型实验；")
    print("它只能回答『目录条目是否还留有定位线索』，不衡量语义改写能力。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
