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

### D2（2026-09-25）扩容：22 → 58 条

扩容前 @1 = 86%（19/22）已饱和、失去区分度。本轮：**+39 条新题，−3 条失效题**。

| 来源 | 条数 | 说明 |
| -- | --: | -- |
| **真实日志** | 8 | 取自 `.sync/state/query.log*.jsonl` 的历史查询（人工改写为自然提问，不照抄） |
| **区域补写** | 31 | 每张目标卡写一句"不知道题面时人会怎么问"；覆盖此前几乎空白的区域（longterm / projects / methodology） |
| **剔除** | −3 | 原 22 条里有 3 条目标卡是 `candidate`（临时态）—— 见 `GOLD` 上方的备查注释 |

**同时确立两条目标卡卫生规则**（已固化为 `_validate_gold()` + 单测）：

1. 目标卡必须**存在**（卡改名/归档后夹具不得静默失效）；
2. 目标卡 status 必须是 `active`/`reference` —— 实测踩过：初稿里 2 条目标卡已是
   `deprecated`（内容已并入 `global-rules` / `memory-injection-pattern`），检索按设计排除它们 ⇒
   那不是检索缺口、是**夹具造错了**。

**已知未命中 1 条**（有意保留为红样例，避免"永远全绿的度量"）：
`新写好的卡怎么晋升到权威区` → `memory-hub-card-promotion`（见审计 §11.6）。

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

import yaml

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


# ── 金标准集（58 条：初版 22 条 − 失效 3 条 + D2 扩容 39 条）────────────────────
# 目标卡卫生规则（`validate_gold` 强制）：必须存在、且 status ∈ {active, reference}。
GOLD: tuple[GoldCase, ...] = (
    GoldCase("写锁残留 僵尸锁", "write-lock-zombie-detection"),
    GoldCase("本地模型嵌入维度不一致", "lmstudio-embed-model-switch-triple-drift"),
    GoldCase("去重网关降级失败怎么修", "llm-dedup-gateway-degrade-fix"),
    GoldCase("微信推送失败 限流", "flywheel-weixin-rate-limit-diagnosis"),
    GoldCase(
        "换向量模型前该先跑什么基准",
        "embedding-model-chinese-retrieval-bench-bge-m3-vs-nomic",
    ),
    GoldCase("两套引擎共用向量库的字段契约", "dual-engine-single-vector-db-meta-contract"),
    GoldCase("npm 清理失败 文件被占用", "npm-eperm-node-file-lock-self-update-residue"),
    GoldCase("pi 自更新找不到包目录", "pi-self-update-path-layout-requirements"),
    GoldCase("ruff 错误凭空变多", "ruff-rule-set-drift-lock-select-precommit-gate"),
    GoldCase("跑 Qt 测试在桌面弹出窗口", "pytest-qt-offscreen-no-real-windows"),
    GoldCase("强制查中枢反而违背分级规则", "gating-overforce-violates-hub-tiering"),
    # ⚠ D2（2026-09-25）剔除 3 条原金标准：它们的**目标卡是 `candidate`**（临时态，随时可能
    # 被归档/并入）—— 按新卫生规则不再作金标准目标；下方保留原因备查：
    #   dsh 配置与真实导入行为不一致 → dsh-dump-config-vs-actual-import（candidate）
    #   pnpm 阻断构建脚本怎么办       → pnpm-blocked-build-script-bypass（candidate）
    #   去重跨类型误判                 → llm-cross-type-merge-misjudge（candidate）
    # 这三个主题都暂无 `active/reference` 等价卡；若有卡晋升为 active，可原样恢复。
    GoldCase("浏览器驱动端口被残留实例占用", "browser-chrome-single-instance"),
    GoldCase("VBS 脚本编码怎么处理", "vbs-ascii-constraint"),
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
    # ── D2 扩容（2026-09-25）：真实日志改写 8 条 ──────────────────────────────
    GoldCase("启动时怎么决定读哪几条规则", "rules-routing-table", note="D2/真实日志：启动门禁 规则 路由"),
    GoldCase(
        "订阅规则怎么固化进 Merge.yaml",
        "clash-rule-fix-consumption-standard",
        note="D2/真实日志：Clash 规则 配置 沉淀",
    ),
    GoldCase("改完 DLL 要不要改版本号", "dll-version-lock", note="D2/真实日志：如何修复 DLL 锁问题"),
    GoldCase(
        "脚本开头那段注释该写什么",
        "reusable-code-header-comment-rule",
        note="D2/真实日志：可复用 代码 头注释 @version",
    ),
    GoldCase(
        "虚拟机抢占内存导致容器被拖死怎么办",
        "vmmem-wsl2-docker-memory-three-layer",
        note="D2/真实日志：WSL2 内存限制 .wslconfig",
    ),
    GoldCase(
        "CAD 插件测试怎么和 GUI 解耦",
        "autocad-cad-plugin-testing-skill-decoupled-architecture",
        note="D2/真实日志：CAD GUI 测试 工程接手",
    ),
    GoldCase(
        "DeepSeek 高峰时段自动换模型",
        "deepseek-peak-offpeak-scheduler",
        note="D2/真实日志：Hermes DeepSeek 模型配置",
    ),
    GoldCase(
        "直连模型接口总是超时是不是代理问题",
        "hermes-env-only-proxy-vs-clash-fakeip",
        note="D2/真实日志：DeepSeek 超时 timeout",
    ),
    # ── D2 扩容：区域补写（rules / methodology / projects / longterm）─────────
    GoldCase("现在本地模型跑在哪个运行时上", "ollama-retired-lmstudio-takeover", note="D2/补写 rules"),
    GoldCase("Agent 改完页面要不要自己看一眼", "agent-modify-must-view-page", note="D2/补写 rules"),
    GoldCase("对话过程中要不要随时显示待办", "agent-show-todo-rule", note="D2/补写 rules"),
    GoldCase("卸载软件前该检查什么", "pre-uninstall-data-safety-check", note="D2/补写 rules"),
    GoldCase("4 个平台之间怎么同步规则", "cross-platform-sync-rule", note="D2/补写 rules"),
    GoldCase("中文乱码问题该怎么根治", "chinese-text-encoding-discipline", note="D2/补写 rules"),
    GoldCase("哪些目录的数据不进 lint", "lint-runtime-data-exclude", note="D2/补写 rules"),
    GoldCase("全局规则 GR 系列讲了哪几条", "global-rules", note="D2/补写 rules"),
    GoldCase(
        "插件平台的开机自动化脚本怎么注册",
        "pluginhub-startup-automation-script-registration-standard",
        note="D2/补写 rules",
    ),
    GoldCase(
        "GitHub 上挑仓库要先过滤什么",
        "gh-star-repo-filter-rule",
        note="D2/补写 rules",
    ),
    GoldCase("怎么证明一个检查器不是摆设", "checker-must-be-provably-red", note="D2/补写 methodology"),
    GoldCase(
        "判断该不该重构看什么指标",
        "2026-09-10-refactor-judgment-fanout-not-loc",
        note="D2/补写 methodology",
    ),
    GoldCase("任务收尾时该给用户什么建议", "post-task-recommendations", note="D2/补写 methodology"),
    GoldCase(
        "怎么让 CLAUDE.md 里的指令更被遵守",
        "improve-claude-md-important-if",
        note="D2/补写 methodology",
    ),
    GoldCase("把开源项目内化成自己的技能", "github-star-distill", note="D2/补写 methodology"),
    GoldCase(
        "MCP 挂载以后怎么保证一定查得到",
        "mcp-hub-mount-guaranteed-retrieval",
        note="D2/补写 methodology",
    ),
    GoldCase(
        "踩坑之后怎么反哺工具和卡片",
        "pitfall-feedback-loop-closed",
        note="D2/补写 methodology",
    ),
    GoldCase(
        "想找记忆中间层工具有哪些可选项",
        "memory-tool-landscape",
        note="D2/补写 methodology",
    ),
    GoldCase(
        "写自动化脚本的骨架要注意什么",
        "python-automation-skeleton-blueprint",
        note="D2/补写 methodology",
    ),
    GoldCase(
        "Python 测试框架怎么组织",
        "pytest-python-test-framework-methodology",
        note="D2/补写 methodology",
    ),
    GoldCase(
        "断网或模型不可用时检索会怎样",
        "retrieval-quality-three-loop",
        note="D2/补写 methodology",
    ),
    GoldCase(
        "新写好的卡怎么晋升到权威区",
        "memory-hub-card-promotion",
        note="D2/**已知未命中**（检索缺口，见审计 §11.6）",
    ),
    GoldCase("CAD 命令自动化模板长什么样", "cad-automation-command-template", note="D2/补写 methodology"),
    GoldCase("OmniRoute 在本机是怎么部署的", "omniroute-local-deployment", note="D2/补写 projects"),
    GoldCase(
        "语音输入插件怎么注册到平台",
        "pluginhub-speech-input-registration",
        note="D2/补写 projects",
    ),
    GoldCase("CAD 拆图流水线有哪几步", "cad2020-tu-fen-pipeline", note="D2/补写 projects"),
    GoldCase(
        "threeRowRein 现在的交付基线是哪个版本",
        "project-threeRowRein-baseline-v51-snapshot",
        note="D2/补写 projects",
    ),
    GoldCase(
        "Hypertrace 这个项目是做什么的",
        "hypertrace-distributed-tracing-observability-project",
        note="D2/补写 projects",
    ),
    GoldCase("那家云厂商的记忆存储方案", "tencentdb-agent-memory", note="D2/补写 projects"),
    GoldCase("我的 OneDrive 账号信息", "onedrive-account", note="D2/补写 longterm"),
)

# 允许作为金标准目标的 status（deprecated/archived/candidate 一律不合格：检索按设计排除它们）
GOLD_VALID_STATUS = ("active", "reference")

# 防“抄题面”检查（tests/test_recall_regression.py）用的实体名白名单。
#
# 规则本意是“查询不得是卡片标题/摘要的字面改写”，但 slug 里也会出现**实体名/技术名**：
# 问“Hypertrace 是干什么的”“浏览器怎么处理 WSL2 内存”是完全自然的提问，不是抄答案。
# 故这些词不计入“泄漏”；**描述性词汇仍零容忍**，且任何查询不得命中三维及以上
# slug 词（即使全部在白名单里）—— 那已经是整句 slug 改写。
GOLD_SLUG_WORD_ALLOWLIST = frozenset(
    {
        "agent",
        "claude",
        "deepseek",
        "docker",
        "hypertrace",
        "memory",
        "omniroute",
        "onedrive",
        "python",
        "tencentdb",
    }
)
GOLD_MAX_SLUG_WORDS_IN_QUERY = 2


def _card_status(path: Path) -> str:
    """读一张卡的 status；读不到/解析不了返回空串（夹具体检，不抛异常）"""
    try:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return ""
        fm = yaml.safe_load(text.split("---", 2)[1]) or {}
    except (OSError, IndexError, yaml.YAMLError):
        return ""
    return str(fm.get("status", "")) if isinstance(fm, dict) else ""


def validate_gold(root: Path) -> list[str]:
    """检查金标准集自身是否健康 → 问题列表（空 = 合格）。

    为什么需要（2026-09-25 实测教训）：写作金标准时很容易把目标卡写成
    **已废弃卡**（内容已 `superseded_by` 并入别的卡），此时“未命中”不是检索缺口，
    而是夹具造错了 —— 检索排除废弃卡是设计行为。同类风险：卡改名/归档后夹具静默失效。
    """
    problems: list[str] = []
    seen: set[str] = set()
    for case in GOLD:
        if case.query in seen:
            problems.append(f"重复查询：{case.query}")
        seen.add(case.query)
        matches = list(root.rglob(f"{case.slug}.md"))
        if not matches:
            problems.append(f"目标卡不存在：{case.slug}（「{case.query}」）")
            continue
        if not any(_card_status(p) in GOLD_VALID_STATUS for p in matches):
            status = next((_card_status(p) for p in matches), "")
            problems.append(f"目标卡 status={status or '缺'} 不可作金标准：{case.slug}（「{case.query}」）")
    return problems


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
        pools = ["blueprint" if getattr(c, "type", "") == "blueprint" else "core" for c in hits]
        rows.append(
            {
                "query": case.query,
                "slug": case.slug,
                "rank": rank,
                "target_pool": "blueprint" if case.slug.endswith("-blueprint") else "core",
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
    print(f"{'模式':<8} {'recall@' + str(top_k):<12} {'recall@1':<10} {'蓝图占位':<9} 说明")
    print("-" * 66)
    for r in results:
        tag = "← CLI 默认（生产路径）" if r["mode"] == PRODUCTION_MODE else ""
        print(
            f"{r['mode']:<8} {r['recall_at_k'] * 100:>6.0f}%"
            f"      {r['recall_at_1'] * 100:>5.0f}%     {r['blueprint_share'] * 100:>5.1f}%   {tag}"
        )
    print("-" * 66)
    print("蓝图占位 = 目标非蓝图的查询里，blueprints/ 卡占的槽位比（P0-B 度量；判据见 WORK.md）")

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

    # 先体检夹具自身：目标卡必须存在且 status ∈ {active, reference}（见 validate_gold docstring）
    problems = validate_gold(root)
    if problems:
        print(f"[error] 金标准集自身不合格（{len(problems)} 处）——修夹具，不要改阈值：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
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
