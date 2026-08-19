"""真机验证：对比纯词袋(n-gram) / 纯向量(bge-small-zh) / 融合 三通道的中英文召回。

用法：python scripts/verify_vector.py <中枢根>
前置：先跑 build-vectors 生成 .sync/vector.db。
"""

import sys
from pathlib import Path

from scripts.bootstrap_hub import bootstrap
from tools.retrieve import (
    _semantic_scored,
    retrieve,
    semantic_vector_retrieve,
)

# (标签, 查询) —— 前几组为向量优势场景（同义/英文/跨语言），末几组为中文基准
QUERIES = [
    ("中·同义/意译", "DLL 改完别直接覆盖，先递增版本号避免被 AutoCAD 占坑"),
    ("英·命中原规则", "how to avoid autocad locking a dll after replacing it"),
    ("英·CAD 出图", "batch plot script for autocad drawing to pdf"),
    ("中英混合", "chrome automation profile 单实例 不要走 preview"),
    ("英·账号", "what github account do i use"),
    ("中文基准", "lint 时运行态数据要不要被排除"),
    ("中文基准", "网关配置不能把凭证写进文件"),
]


def top_names(root: Path, query: str, top_k: int = 5) -> list[str]:
    bag = [c.path.name for c, _ in _semantic_scored(root, query, top_k=top_k)]
    vec = [c.path.name for c, _ in semantic_vector_retrieve(root, query, top_k=top_k)]
    fused = [c.path.name for c in retrieve(root, query, top_k=top_k)]
    return bag, vec, fused


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "AgentMemoryHub")
    bootstrap(root)
    print(f"中枢: {root}\n")
    for tag, q in QUERIES:
        bag, vec, fused = top_names(root, q)
        print(f"── [{tag}] {q}")
        print(f"  词袋 : {bag}")
        print(f"  向量 : {vec}")
        print(f"  融合 : {fused}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
