"""检索三通道评测基准（正式入库版）：词袋(n-gram) / 纯向量(bge) / 融合 的中英文召回命中率。

用途：
- 对比不同向量模型（默认 bge-small-zh-v1.5；--model 可换 bge-base-zh-v1.5 等），
  为「是否切换模型」提供可复跑量化基线（对应 WORK 候选 5/6）。
- 每周复核 Schedule（44e1e8ef）复用本脚本做回归。

伺服构造独立语料（work/bench_vectors），不污染真实中枢，保证可复现；
向量库在评测语料内，按 --model 删库强制重建（模型间向量维度/语义不一致，必须隔离）。

用法：
  python scripts/vector_bench.py                       # 基线 bge-small-zh-v1.5
  python scripts/vector_bench.py --model BAAI/bge-base-zh-v1.5   # 对比 base
前置：需联网下载对应 HF 权重；无网/无后端时向量通道自动退化（hit=0，融合=词袋）。
"""

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))  # hub-engine 加入 path

# tools.retrieve 惰性 import semsearch（不触发 EMBED_MODEL 快照），可安全模块级导入；
# semsearch 本监督必须在设 AGENT_MD_EMBED_MODEL 后再 import（见 main）。
from tools.retrieve import _semantic_scored, retrieve, semantic_vector_retrieve

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "work" / "bench_vectors"  # gitignored：评测共震语料 + 向量库

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


def _card(type_: str, tags: list[str], body: str) -> str:
    return (
        "---\n"
        f"type: {type_}\n"
        "tags:\n"
        + "".join(f"- {t}\n" for t in tags)
        + "updated: '2026-08-19'\n"
        "status: active\n"
        "reuse_count: 0\n"
        "---\n\n"
        f"{body}\n"
    )


# 评测语料：(相对路径, type, tags, 正文)。中英文主题混合，覆盖规则/经验/长期/项目。
CARDS = {
    "rules/dll-version-lock.md": _card(
        "rule", ["autocad", "dll-lock"],
        "教训：修改 DLL 后必须递增版本号，绝不能原地覆盖同名文件，避免发布后被 AutoCAD 锁文件。",
    ),
    "experience/query-writeback.md": _card(
        "exp", ["writeback", "dll"],
        "查询结论要回写成经验卡片：从查询到命中的复盘沉淀为可复用经验。防止重踩。",
    ),
    "longterm/github-account.md": _card(
        "lt", ["github", "account"],
        "GitHub 账号 creamxiao117；MCP github 已配 gh CLI token。",
    ),
    "experience/feishu-webhook-setup.md": _card(
        "exp", ["feishu", "webhook"],
        "飞书机器人 webhook 配置加签校验、消息幂等发送，防止重复推送。",
    ),
    "experience/obsidian-daily-template.md": _card(
        "exp", ["obsidian", "template"],
        "Obsidian 日记模板：YAML 属性、每日打卡清单、习惯追踪区块。",
    ),
    "rules/docker-image-tag.md": _card(
        "rule", ["docker", "tag"],
        "Docker 镜像 tag 用语义化版本号而非 latest，按 dev/prod 环境区分。",
    ),
    "rules/python-style.md": _card(
        "rule", ["python", "ruff"],
        "Python 代码规范：Ruff lint、导入按序、注释中文、行宽不过长。",
    ),
    "experience/omniroute-gateway.md": _card(
        "exp", ["omniroute", "gateway", "llm"],
        "omniroute 网关聚合免费模型：OpenAI 兼容 API，默认 qwen2.5:7b、超时 30s、地址 127.0.0.1:11434。",
    ),
    "experience/pytest-venv.md": _card(
        "exp", ["pytest", "venv"],
        "跑测试用系统 Python 而非项目 .venv：venv 缺 pytest/yaml/jieba 时报 No module。",
    ),
    "projects/cad2020-pdf-merge.md": _card(
        "proj", ["cad", "pdf", "batch"],
        "CAD 批量出图转 PDF：先查目标 pdf 是否 15B 空壳（合并失败），总图 A/B 区分，批量脚本输出。",
    ),
}

# 评测集：(查询, 期望命中文件名)。中英文混合，覆盖 n-gram / jieba / 向量语义通道。
QUERIES = [
    ("如何避免 AutoCAD 锁住刚替换的 DLL 文件", "dll-version-lock.md"),
    ("how to avoid autocad locking a dll after replacing it", "dll-version-lock.md"),
    ("把查询结论回写成经验卡片", "query-writeback.md"),
    ("我的 github 账号是什么", "github-account.md"),
    ("which github account do i use", "github-account.md"),
    ("飞书机器人怎么配置签名密钥", "feishu-webhook-setup.md"),
    ("obsidian 日记怎么加打卡区块", "obsidian-daily-template.md"),
    ("docker 镜像标签怎么命名", "docker-image-tag.md"),
    ("python 代码风格检查用什么工具", "python-style.md"),
    ("本地大模型网关地址怎么配置", "omniroute-gateway.md"),
    ("跑测试报错找不到 pytest 模块", "pytest-venv.md"),
    ("batch plot cad drawings to pdf", "cad2020-pdf-merge.md"),
]

# 难样例：同义改写/跨语言，词袋(字面 token)大概率 miss，靠语义向量召回——
# 用于区分 small vs base 的语义能力差异（easy 组词袋已饱和无法区分）。
HARD = [
    ("换了 dll 拖进目录就被会议软件进程把持住了", "dll-version-lock.md"),
    ("the shipped plugin binary is stuck because a drawing app still holds it", "dll-version-lock.md"),
    ("一次性把几十张施工图批量导出成一个总的 pdf 再归档", "cad2020-pdf-merge.md"),
    ("remember which account is tied to my code hosting login", "github-account.md"),
    ("对话里问出来的东西要怎么沉淀下来下次复用", "query-writeback.md"),
]


def _ensure_hub(root: Path) -> None:
    """写评测语料卡到 work/bench_vectors（幂等；已存在则跳过）。"""
    for rel, text in CARDS.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(text, encoding="utf-8")


def _channels(root: Path, query: str, top_k: int) -> tuple[set, set, set]:
    """对单查询返回 (词袋命中名集合, 向量命中名集合, 融合命中名集合)。"""
    bag = {c.path.name for c, _ in _semantic_scored(root, query, top_k=top_k)}
    vec = {c.path.name for c, _ in semantic_vector_retrieve(root, query, top_k=top_k)}
    fus = {c.path.name for c in retrieve(root, query, top_k=top_k)}
    return bag, vec, fus


# 真实中枢回归查询集：(查询, 期望命中文件名)。名称必须匹配 AgentMemoryHub 真实存在的卡，
# 语料随时间增长，用于回归门禁：返回融合命中率作为健康信号（而非精确断言）。
REAL_QUERIES = [
    ("如何避免 AutoCAD 锁住 DLL", "dll-version-lock.md"),
    ("github 账号是什么", "github-account.md"),
    ("omniroute 网关怎么配置", "omniroute-gateway.md"),
    ("CAD 批量出图转 PDF", "cad2020-pdf-merge.md"),
    ("代理守卫会冲掉 IE 代理覆盖", "proxy-guard-ie-override.md"),
    ("查询结论怎么回写成经验卡", "query-writeback-dll.md"),
]


def _run_real(root: Path, top_k: int, fail_below: float | None) -> int:
    """真实中枢回归：对 ROOT 跑各通道命中率；fail_below 设置则低于即返回非零(门禁)。"""
    eh, ed = _score(root, [(q, w) for q, w in REAL_QUERIES], top_k)
    _print_group(f"real top_k={top_k}", len(REAL_QUERIES), eh, ed)
    hit_ratio = eh["fus"] / max(len(REAL_QUERIES), 1)
    print(f"fusion hit ratio: {hit_ratio:.0%}")
    if fail_below is not None and hit_ratio < fail_below:
        print(f"【门禁失败】融合命中率 {hit_ratio:.0%} < 阈值 {fail_below:.0%}")
        return 3  # 专用退出码：回归门禁未通过
    return 0


def _score(root: Path, queries: list[tuple[str, str]], top_k: int) -> tuple[dict, list]:
    """统计一组查询的三通道命中数；返回 (计数, 逐查询明细[(want, bag, vec, fus, mark)])。"""
    detail = []
    hits = {"bag": 0, "vec": 0, "fus": 0}
    for q, want in queries:
        bag, vec, fus = _channels(root, q, top_k)
        marks = []
        if want in bag:
            hits["bag"] += 1
            marks.append("B")
        if want in vec:
            hits["vec"] += 1
            marks.append("V")
        if want in fus:
            hits["fus"] += 1
            marks.append("F")
        detail.append((want, want in bag, want in vec, want in fus, "".join(marks) or "-"))
    return hits, detail


def _print_group(label: str, n: int, hits: dict, detail: list) -> None:
    print(f"\n-- {label}（{n} 条）--  词袋 {hits['bag']}/{n}   向量 {hits['vec']}/{n}   融合 {hits['fus']}/{n}")
    for name, b, v, f, m in detail:
        print(f"  [{m:<3}] {name}")


def main() -> int:
    ap = argparse.ArgumentParser(description="检索三通道命中率基准")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="HF 模型 id，默认 bge-small-zh-v1.5")
    ap.add_argument(
        "--no-rebuild", action="store_true",
        help="复用已有向量库（默认：指定模型首次即删库全量重建，保证模型隔离）",
    )
    ap.add_argument(
        "--real", metavar="ROOT", default=None,
        help="真实中枢回归门禁模式：对 ROOT(如 AgentMemoryHub) 跑 REAL_QUERIES，输出融合命中率",
    )
    ap.add_argument(
        "--fail-below", type=float, default=None,
        help="与 --real 联用：融合命中率低于该值则退出码非零(默认 0.0，即不设门禁)",
    )
    args = ap.parse_args()

    # ---------- 真实中枢回归门禁：不建语料、不重建向量库，直接对现库回归 ----------
    if args.real:
        os.environ["AGENT_MD_EMBED_MODEL"] = args.model  # 向量检索读现库，仍需模型参数一致
        return _run_real(Path(args.real), top_k=3, fail_below=args.fail_below)

    os.environ["AGENT_MD_EMBED_MODEL"] = args.model  # 须在 import semsearch 前设好
    from tools.semsearch import (  # 模块级 EMBED_MODEL 在 .import 时快照，故设 env 之后再导
        build,
        db_path,
    )

    _ensure_hub(BENCH)

    db = db_path(BENCH)
    if not args.no_rebuild and db.exists():
        db.unlink()  # 模型隔离：删库强制全量重建为该模型的向量
    stats = build(BENCH)

    print(f"模型: {args.model}\n语料 {len(CARDS)} 卡 / 查询 {len(QUERIES)}+{len(HARD)} 条")
    print(f"vector build: {stats}")
    if stats["embedded"] + stats["reused"] == 0:
        print("警告：无卡片生成向量（模型不可用/无网/退化），以下向量与融合命中受空库影响。")

    top_k = 1
    eh, _ = _score(BENCH, QUERIES, top_k)
    hh, hd = _score(BENCH, HARD, top_k)
    _print_group(f"easy top_k={top_k}", len(QUERIES), eh, [])
    _print_group(f"HARD top_k={top_k}", len(HARD), hh, hd)
    print("\n标记：B=词袋中 V=向量中 F=融合中（hard 组反映语义向量相对词袋的增量）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())