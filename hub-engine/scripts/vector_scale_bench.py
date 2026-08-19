"""向量规模拐点压测：全表余弦(JSON)检索耗时 vs 卡数曲线（对应 WORK 候选 4）。

目的：量化 semsearch.vector_scores 的「全表 fetchall + json.loads + 点积 + sort」耗时
随向量条数 N 的增长，据此定「何时切 FAISS/ANN」阈值。

方法：在隔离 work/bench_scale 库中直接灌 N 条假向量（维度与 bge-small-zh 一致，384），
不触发真实 embedding（快、无网也可跑），测 vector_scores 查询耗时。

- 不污染真实中枢：库建在 work/bench_scale/.sync/vector.db（gitignored）。
- 复用 semsearch._ensure_schema / vector_scores 真实检索路径，保证测的是线上代码。
- 假向量维度=384 与默认模型一致，仅影响 json 体积/点积计算量，与真实一致。

用法：
  python hub-engine/scripts/vector_scale_bench.py
  python hub-engine/scripts/vector_scale_bench.py --sizes 100 500 1000 5000 10000
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
from tools.semsearch import _ensure_schema, db_path, vector_scores

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "work" / "bench_scale"
DIM = 384  # bge-small-zh / bge-base-zh 共用 512token，维数仅影响点积量；small=384
SIZES_DEFAULT = [100, 500, 1_000, 2_000, 5_000, 10_000, 20_000, 50_000]


def _rng() -> list[float]:
    return [random.uniform(-1.0, 1.0) for _ in range(DIM)]


def _fill(db: sqlite3.Connection, n: int) -> None:
    """清空并灌 n 条假向量（模拟 n 张卡的 embedding 行）。"""
    db.execute("DELETE FROM docs")
    rows = [
        (
            f"/mock/card-{i}.md",
            0.0,
            0,
            f"card-{i}.md",
            "",
            "exp",
            f"mock body {i}",
            json.dumps(_rng()),
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
    args = ap.parse_args()

    db = db_path(BENCH)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        _ensure_schema(conn)
        qv = _rng()

        print(f"维度={DIM}  top_k={args.top_k}  repeat={args.repeat}（取中位 ms）")
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
    print("\n判断指南:")
    print("  - <100ms：用户感知即时，全表 JSON 余弦可持续用")
    print("  - 100~300ms：可接受但开始有感知，卡到数千级先考虑优化(索引/向量列二进制)")
    print("  - >300ms：检索过慢，应切 FAISS/ChromaDB ANN 或改向量存储格式")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
