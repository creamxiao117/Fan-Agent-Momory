# @version V2.0 / 2026-09-25 / pi / 死代码审计：hub-engine 下哪些模块没有任何引用

"""对引擎（hub-engine/）做引用度审计，找出疑似死代码。

判据（任一命中即视为"有引用"）：
  1. 被其它 .py 以 `import <mod>` / `from <mod>` / 字符串路径引用
  2. 被 patrol_runner 等编排器以文件名调用（含 engine_dir / "scripts" / "x.py"）
  3. 被文档/配置/钩子/批处理提及（.md/.yaml/.json/.toml/.cmd/.bat/.ps1/pre-commit）
  4. 被 Windows 计划任务引用

只输出**零引用**的候选人，供人工裁定——不自动删。

⚠️ 结论必须人工复查，本工具**会漏判**：2026-09-25 实测 `tools/safe_patch_handler.py`
被判零引用，实际它被 `mcp_server.py` / `tools/mcp_handlers.py` / `tests/test_mcp_server.py`
使用（CHARTER:33 还声明它是高风险改动的唯一渠道）。原因见该文件被引用的形态不在上述
正则覆盖内（跨模块注册表式调用）。故"零引用 ≠ 死代码"，删除前逐个人工看入口/注册表。

用法（从仓库根或 hub-engine 下均可）：
    python -m scripts.audit_dead_modules            # 在 hub-engine/ 下
    python hub-engine/scripts/audit_dead_modules.py # 在仓库根
"""

from __future__ import annotations

import re
from pathlib import Path

# 2026-09-25 迁入仓库：本文件原在 gitignore 的 work/ 草稿区，却被
# docs/compose/cleanup/*.md 与审计报告引用 ⇒ 换机即断链。改由脚本位置推导。
PROJ = Path(__file__).resolve().parents[2]
ENGINE = PROJ / "hub-engine"

# 扫描引用来源时跳过的目录（运行态/第三方/历史日志）
SKIP_DIRS = {
    ".git",
    ".venv",
    "_t1_venv",
    "_t1_deps",
    "node_modules",
    "__pycache__",
    ".backup",
    "sessions",
    "traces",
    "web-search-cache",
    ".pytest_cache",
    ".ruff_cache",
    "work",
}

REF_EXTS = {
    ".py",
    ".md",
    ".yaml",
    ".yml",
    ".json",
    ".toml",
    ".cmd",
    ".bat",
    ".ps1",
    ".cfg",
    ".ini",
}
# 无扩展名但含引用的文件
REF_NAMES = {"pre-commit"}


def iter_ref_files() -> list[Path]:
    out = []
    for root in (PROJ, PROJ / "AgentMemoryHub"):
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            if p.suffix.lower() in REF_EXTS or p.name in REF_NAMES:
                out.append(p)
    return out


def main() -> int:
    # 只审**非测试**模块：tests/ 由 pytest 自动发现，无需被 import；
    # 且它们本身就是回归保护，不能当"死代码"。
    modules = sorted(p for p in ENGINE.rglob("*.py") if "__pycache__" not in p.parts and "tests" not in p.parts)
    print(f"hub-engine 下 .py（不含 tests）: {len(modules)}")

    ref_files = iter_ref_files()
    print(f"引用来源文件: {len(ref_files)}")
    # 预读文本（只读一次，避免 O(n*m) I/O）
    blobs: dict[Path, str] = {}
    for p in ref_files:
        try:
            blobs[p] = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

    dead: list[Path] = []
    for m in modules:
        stem = m.stem
        # 匹配形态：import x / from x import / x.py / "x" / x'  ...
        pats = [
            re.compile(rf"\bimport\s+{re.escape(stem)}\b"),
            re.compile(rf"\bfrom\s+{re.escape(stem)}\b"),
            re.compile(rf"{re.escape(stem)}\.py"),
            re.compile(rf"[\"'/]{re.escape(stem)}[\"']"),
            # CLI 调用形态：python -m scripts.<stem> / -m <stem>
            re.compile(rf"-m\s+scripts\.{re.escape(stem)}\b"),
            re.compile(rf"-m\s+{re.escape(stem)}\b"),
        ]
        hits = 0
        for p, blob in blobs.items():
            if p == m:
                continue  # 自身不算
            if any(pt.search(blob) for pt in pats):
                hits += 1
        if hits == 0:
            dead.append(m)

    print(f"\n零引用模块: {len(dead)}")
    for d in dead:
        print(f"  {d.relative_to(ENGINE)}  ({d.stat().st_size} bytes)")

    # 补充口径：带 __main__ 入口的模块本就是给人手执行的，"零引用"属正常。
    cli_entries = []
    for d in dead:
        try:
            if "__main__" in d.read_text(encoding="utf-8", errors="ignore"):
                cli_entries.append(d)
        except OSError:
            continue
    print(f"\n其中带 __main__ 入口（本就是给人手跑的 CLI）: {len(cli_entries)}")
    for d in cli_entries:
        print(f"  {d.relative_to(ENGINE)}")

    print(
        "\n注意：零引用 ≠ 死代码。带 __main__ 的 CLI 脚本、以及人工按文档执行的\n"
        "      一次性脚本都会落在本名单里。真正可考虑的仅是『既无引用、又已被\n"
        "      其它脚本取代』者——须逐个人工裁定（本工具存在假阳性，见模块 docstring）。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
