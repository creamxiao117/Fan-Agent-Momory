"""pytest 全局配置（2026-10-01 新增）。

为什么需要：`_retired/`（退役归档区）里的测试**故意不可运行**——它们 import 的是
已归档的模块（`scripts/slim_index` 等），保真留档优先于“改到能跑”。若被收集，
每次全量测试都会在 collection 阶段报 ImportError。

`testpaths`/`norecursedirs` 都挡不住子目录递归收集，唯一切实有效的是这里显式忽略。
"""

from pathlib import Path

collect_ignore = [str(Path(__file__).parent / "_retired")]
