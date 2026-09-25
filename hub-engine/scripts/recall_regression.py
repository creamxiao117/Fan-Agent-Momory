#!/usr/bin/env python3
"""检索召回回归集 + 双通道诊断。

## 为什么需要它（2026-09-24）

全局审计实测：自然语言查询的召回率仅 ~25%。**没有度量就无法修**——本脚本先立仪表。

首轮实测即定位到根因（**模式差异，不是模型能力**）：

| 模式 | 召回率 | 谁在用 |
| -- | --: | -- |
| `char`（字符 n-gram） | **6/9** | `tools.retrieve.retrieve()` 的函数默认 |
| `word`（jieba + IDF） | **3/9** | **`engine.py retrieve` 的 CLI 默认** ← 生产路径 |

⇒ CLI 默认模式比库函数默认模式**差一倍**，这正是"命令行召不回、库函数召得回"的原因。

## 金标准集的口径（重要，避免自欺）

- 查询由**人工编写为自然提问**（如"写锁残留 僵尸锁"），
  **不抄卡片摘要原文** —— 抄原文会让检索容易得毫无意义。
- 每张目标卡都**已核实位于权威区**（否则对检索不公平）。
- 命中判据：目标卡出现在 top-k 内。

## 用法

    python -m scripts.recall_regression                # 全量，双模式对比
    python -m scripts.recall_regression --verbose      # 列出未命中项与其实际返回
    python -m scripts.recall_regression --mode char    # 只测某模式
    python -m scripts.recall_regression --json         # 机器可读

退出码：0 = 达到阈值；2 = 未达标（可作为门禁）。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "AgentMemoryHub"

# 生产路径用的模式（engine.py retrieve 的 CLI 默认值）。改动 CLI 默认时须同步这里。
PRODUCTION_MODE = "word"
MODES = ("char", "word")

# 目标召回率（recall@k）。低于此值退出码 2 —— 它是**待达成的目标**，不是现状描述。
DEFAULT_THRESHOLD = 0.90


@dataclass(frozen=True)
class GoldCase:
    """一条金标准：自然语言查询 → 应被召回的目标卡（slug）。"""

    query: str
    slug: str
    note: str = ""


# ── 金标准集（20 条，人工编写，覆盖 rules / methodology / experience 三区）──────
GOLD: tuple[GoldCase, ...] = (
    GoldCase("写锁残留 僵尸锁", "write-lock-zombie-detection"),
    GoldCase("本地模型嵌入维度不一致", "lmstudio-embed-model-switch-triple-drift"),
    GoldCase("去重网关降级失败怎么修", "llm-dedup-gateway-degrade-fix"),
    GoldCase("微信推送失败 限流", "flywheel-weixin-rate-limit-diagnosis"),
    GoldCase(
        "换向量模型前该先跑什么基准",
        "embedding-model-chinese-retrieval-bench-bge-m3-vs-nomic",
    ),
    GoldCase(
        "两套引擎共用向量库的字段契约", "dual-engine-single-vector-db-meta-contract"
    ),
    GoldCase("npm 清理失败 文件被占用", "npm-eperm-node-file-lock-self-update-residue"),
    GoldCase("pi 自更新找不到包目录", "pi-self-update-path-layout-requirements"),
    GoldCase("ruff 错误凭空变多", "ruff-rule-set-drift-lock-select-precommit-gate"),
    GoldCase("跑 Qt 测试在桌面弹出窗口", "pytest-qt-offscreen-no-real-windows"),
    GoldCase("强制查中枢反而违背分级规则", "gating-overforce-violates-hub-tiering"),
    GoldCase("dsh 配置与真实导入行为不一致", "dsh-dump-config-vs-actual-import"),
    GoldCase("pnpm 阻断构建脚本怎么办", "pnpm-blocked-build-script-bypass"),
    GoldCase("浏览器驱动端口被残留实例占用", "browser-chrome-single-instance"),
    GoldCase("VBS 脚本编码怎么处理", "vbs-ascii-constraint"),
    GoldCase("去重跨类型误判", "llm-cross-type-merge-misjudge"),
    GoldCase("读 DWG 数据用无头方式", "2026-09-15-accoreconsole-headless-read"),
    GoldCase("CAD 字典能不能存图形实体", "2026-09-15-cad-dict-no-entity"),
    GoldCase("本地模型从 Ollama 迁到 LM Studio", "lmstudio-local-llm-migration"),
    GoldCase("中枢卡片目录分区怎么排序", "index-rule-priority-sorting"),
    # ── 蓝图池守卫（2026-09-24，P0-B 裁定配套）──────────────────────────────
    # 这两条的目标卡在 blueprints/（type=blueprint）。存在的意义：
    # ① 证明「外部蓝图在需要时仍召得回」（若未来做分池/降权，这里会先红）；
    # ② 与蓝图占位率指标配对 —— 前者测「召得回」，后者测「不抢位」。
    GoldCase(
        "随机造数据自动找反例的测试思路",
        "hypothesis-property-based-testing-blueprint",
        note="蓝图池守卫",
    ),
    GoldCase(
        "Lua 编辑器插件进程间通信",
        "neovim-lua-plugin-rpc-architecture-blueprint",
        note="蓝图池守卫",
    ),
)


def _load_retrieve():
    """延迟导入：让 --help 在依赖缺失时也能用。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.retrieve import retrieve

    return retrieve


def _rank_of(hits, slug: str) -> int | None:
    """目标卡在结果里的位次（1 起）；未出现返回 None。"""
    for i, card in enumerate(hits, 1):
        if slug in str(card.path):
            return i
    return None


def run(root: Path, mode: str, top_k: int, n: int = 2) -> dict:
    """跑一轮金标准，返回统计与逐条结果。"""
    retrieve = _load_retrieve()
    rows = []
    for case in GOLD:
        hits = retrieve(root, case.query, top_k=top_k, n=n, mode=mode)
        rank = _rank_of(hits, case.slug)
        pools = [
            "blueprint" if getattr(c, "type", "") == "blueprint" else "core"
            for c in hits
        ]
        rows.append(
            {
                "query": case.query,
                "slug": case.slug,
                "rank": rank,
                "target_pool": "blueprint"
                if case.slug.endswith("-blueprint")
                else "core",
                "pools": pools,
                "returned": [c.path.name for c in hits],
            }
        )
    total = len(rows)
    hit5 = sum(1 for r in rows if r["rank"] is not None)
    hit1 = sum(1 for r in rows if r["rank"] == 1)

    # 蓝图占位率（P0-B 度量）：121 张外部蓝图占全库 ~26%，**只在没人问它们时**
    # 占坑才是浪费。故度量口径 = “目标卡不是蓝图”的那些查询里，蓝图占了多少槽位。
    bp_slots = bp_total = 0
    for r in rows:
        if r["target_pool"] == "blueprint" or not r["pools"]:
            continue
        bp_slots += r["pools"].count("blueprint")
        bp_total += len(r["pools"])
    return {
        "mode": mode,
        "total": total,
        "recall_at_k": hit5 / total if total else 0.0,
        "recall_at_1": hit1 / total if total else 0.0,
        "top_k": top_k,
        "blueprint_share": bp_slots / bp_total if bp_total else 0.0,
        "rows": rows,
    }


def _print_report(results: list[dict], verbose: bool, top_k: int) -> None:
    print(f"检索召回回归集：{len(GOLD)} 条金标准查询（recall@{top_k}）\n")
    print(
        f"{'模式':<8} {'recall@' + str(top_k):<12} {'recall@1':<10} {'蓝图占位':<9} 说明"
    )
    print("-" * 66)
    for r in results:
        tag = "← CLI 默认（生产路径）" if r["mode"] == PRODUCTION_MODE else ""
        print(
            f"{r['mode']:<8} {r['recall_at_k'] * 100:>6.0f}%"
            f"      {r['recall_at_1'] * 100:>5.0f}%     {r['blueprint_share'] * 100:>5.1f}%   {tag}"
        )
    print("-" * 66)
    print(
        "蓝图占位 = 目标非蓝图的查询里，blueprints/ 卡占的槽位比（P0-B 度量；判据见 WORK.md）"
    )

    if len(results) == 2:
        char_r = next(r for r in results if r["mode"] == "char")
        word_r = next(r for r in results if r["mode"] == "word")
        gap = (char_r["recall_at_k"] - word_r["recall_at_k"]) * 100
        if abs(gap) >= 10:
            better = "char" if gap > 0 else "word"
            print(f"⚠️  模式间差距 {abs(gap):.0f} 个百分点（{better} 更好）")

    if verbose:
        for r in results:
            misses = [row for row in r["rows"] if row["rank"] is None]
            if not misses:
                continue
            print(f"\n── {r['mode']} 未命中 {len(misses)} 条 ──")
            for m in misses:
                print(f"  ✗ 「{m['query']}」→ 应中 {m['slug']}")
                for name in m["returned"][:3]:
                    print(f"      实际返回: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检索召回回归集 + 双通道诊断")
    parser.add_argument("--root", type=Path, default=_DEFAULT_ROOT)
    parser.add_argument("--mode", choices=(*MODES, "both"), default="both")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--n", type=int, default=2, help="字符 n-gram 长度")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"生产模式的目标 recall@{'{'}top_k{'}'}（默认 {DEFAULT_THRESHOLD}）",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"[error] 中枢根不存在：{root}", file=sys.stderr)
        return 2

    modes = MODES if args.mode == "both" else (args.mode,)
    results = [run(root, m, args.top_k, args.n) for m in modes]

    if args.json:
        print(
            json.dumps(
                {"results": results, "threshold": args.threshold},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        _print_report(results, args.verbose, args.top_k)
        prod = next((r for r in results if r["mode"] == PRODUCTION_MODE), None)
        if prod is not None:
            ok = prod["recall_at_k"] >= args.threshold
            print(
                f"\n生产模式（{PRODUCTION_MODE}）recall@{args.top_k} = "
                f"{prod['recall_at_k'] * 100:.0f}%"
                f"（目标 {args.threshold * 100:.0f}%）"
                f" → {'达标 ✅' if ok else '未达标 ❌'}"
            )

    prod = next((r for r in results if r["mode"] == PRODUCTION_MODE), None)
    if prod is not None and prod["recall_at_k"] < args.threshold:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
