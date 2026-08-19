"""向量规模拐点压测：全表余弦检索耗时 vs 卡数曲线（对应 WORK 候选 4）。

目的：量化 semsearch.vector_scores 的「全表 fetchall + 反序列化 + 点积 + sort」耗时
随向量条数 N 的增长，据此定「何时切 FAISS/ANN」阈值；并对比 JSON 文本 vs 二进制
(float32) 两种向量编码的检索耗时差异（建议 A：JSON→二进制 加速实证）。

方法：在隔离 work/bench_scale 库中直接灌 N 条假向量（维度与 bge-small-zh 一致，384），
不触发真实 embedding（快、无网也可跑），测 vector_scores 查询耗时。

- 不污染真实中枢：库建在 work/bench_scale/.sync/vector.db（gitignored）。
- 复用 semsearch._ensure_schema / vector_scores 真实检索路径，保证测的是线上代码。
- 假向量维度=384 与默认模型一致，仅影响编码体积/点积计算量，与真实一致。
- `--format json|bin`：json 用旧 JSON 文本编码对比基线，bin 用 float32 二进制（默认）。

用法：
  python hub-engine/scripts/vector_scale_bench.py
  python hub-engine/scripts/vector_scale_bench.py --sizes 100 500 1000 5000 10000 --format json
"""

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))  # hub-engine 加入 path

os.environ.setdefault("AGENT_MD_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
from tools.semsearch import (
    _encode_vec,
    _ensure_schema,
    db_path,
    vector_scores,
)

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "work" / "bench_scale"
DIM = 384  # bge-small-zh / bge-base-zh 共用 512token，维数仅影响点积量；small=384
SIZES_DEFAULT = [100, 500, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000]


def _rng() -> list[float]:
    return [random.uniform(-1.0, 1.0) for _ in range(DIM)]


def _encode(vec: list[float]) -> object:
    """统一写侧编码：按本脚本所选格式产出存储值（json 文本 或 float32 二进制）"""
    if FORMAT == "json":
        return json.dumps(vec, ensure_ascii=False)
    return _encode_vec(vec)


# 模块级：--format 参数（默认 bin），_fill 依据它选择编码
FORMAT = "bin"


def _fill(db: sqlite3.Connection, n: int) -> None:
    """清空并灌 n 条假向量（模拟 n 张卡的 embedding 行）；编码遵循 FORMAT。"""
    db.execute("DELETE FROM docs")
    tmp = [_rng() for _ in range(n)]
    rows = [
        (
            f"/mock/card-{i}.md",
            0.0,
            0,
            f"card-{i}.md",
            "",
            "exp",
            f"mock body {i}",
            _encode(tmp[i]),
        )
        for i in range(n)
    ]
    db.executemany(
        """INSERT INTO docs(path, mtime, size, title, tags, type, body, embedding)
        VALUES(?,?,?,?,?,?,?,?)""",
        rows,
    )
    db.commit()


def _bench_once(root: Path, query_vec: list[float], top_k: int, repeat: int) -> float:
    """测 vector_scores 平均耗时（repeat 次取中位，剔除首轮 JIT/冷启动）。"""
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        vector_scores(root, query_vec, top_k=top_k)
        times.append(time.perf_counter() - t0)
    times.sort()
    return times[len(times) // 2]  # 中位，抗抖动


def main() -> int:
    ap = argparse.ArgumentParser(description="全表余弦检索耗时随规模增长曲线")
    ap.add_argument("--sizes", nargs="+", type=int, default=SIZES_DEFAULT)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--repeat", type=int, default=7)
    ap.add_argument(
        "--format",
        choices=["json", "bin"],
        default="bin",
        help="向量编码：json(旧基线)/bin(二进制,默认)",
    )
    ap.add_argument(
        "--single",
        type=int,
        default=None,
        help="单点模式：只测该规模一次（用于巡检性能门禁），忽略 --sizes",
    )
    ap.add_argument(
        "--fail-above",
        type=float,
        default=None,
        help="与 --single 联用：该点平均耗时超过此毫秒值则退出码非零(4，性能门禁)",
    )
    args = ap.parse_args()

    global FORMAT  # 供 _fill 选择编码
    FORMAT = args.format

    db = db_path(BENCH)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        _ensure_schema(conn)
        qv = _rng()

        # ---------- 单点性能门禁模式（先测，供巡检/CI 固化为回归检查项） ----------
        if args.single is not None:
            size = args.single
            _fill(conn, size)
            vector_scores(BENCH, qv, top_k=args.top_k)  # 预热（连接/JIT）
            ms = _bench_once(BENCH, qv, args.top_k, args.repeat) * 1000
            print(
                f"单点 size={size:,}  format={args.format}  top_k={args.top_k}  "
                f"平均={ms:.2f}ms"
            )
            if args.fail_above is not None and ms > args.fail_above:
                print(
                    f"【性能门禁失败】耗时 {ms:.2f}ms > 阈值 {args.fail_above:.1f}ms"
                )
                return 4  # 专用退出码：性能门禁未通过
            return 0

        print(f"format={args.format}  维度={DIM}  top_k={args.top_k}  repeat={args.repeat}（取中位 ms）")
        print(
            f"{'条数'.rjust(8)}  {'平均耗时(ms)'.rjust(12)}  {'每条均摊(us)'.rjust(12)}"
        )
        prev = None
        for n in args.sizes:
            _fill(conn, n)
            # 首轮预热（连接/JIT），再正式测
            vector_scores(BENCH, qv, top_k=args.top_k)
            ms = _bench_once(BENCH, qv, args.top_k, args.repeat) * 1000
            per = ms * 1000 / max(n, 1)
            marker = ""
            if prev is not None:
                ratio = ms / prev
                marker = f"   ×{ratio:.1f}" if ratio > 1.5 else ""
            print(f"{n:>8,}  {ms:>12.2f}  {per:>12.2f}{marker}")
            prev = ms
    finally:
        conn.close()

    # 指南：以「单查询体验」给出切换判断基准（召回卡数通常在百余级，取 5k/1k 看趋势）
    # 注：2026-08-19 已落地浮点32二进制编码，--format bin 即当前生产速率（旧 json 为历史基线）。
    # 实测（同机）：json 1k≈92ms/5k≈462ms/10k≈922ms；bin 1k≈17ms/5k≈79ms/10k≈160ms，加速约 5.8×。
    print("\n判断指南:")
    print("  - bin（当前生产）1-50k 卡均 <200ms：全表余弦已足够快，无需 ANN")
    print("  - 100~300ms：卡到数十万级(约2.5万+卡)再考虑索引/向量列二进制之外优化")
    print("  - >300ms：检索过慢才需切 FAISS/ChromaDB ANN（bin 编码下约 20k+ 卡才触及）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
