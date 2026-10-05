"""提交门禁的**作用域判定**（唯一事实源；架构重构 M0.5/Task 6）。

## 为什么要有"作用域"

改造前提交门禁是 **9 道**（外层 6 + 中枢 3），且其中**渲染一致性是无条件跑**的：

> 工作树里只要存在**任何人**未提交的卡改动，就会阻断**任何**提交。

这条缺陷的代价不是"慢"，而是**训练所有人使用 `--no-verify`**——而一旦 `--no-verify`
成为习惯，**全部门禁一起失效**（巡检曾连续 18 天未跑就是同一机制）。

修法不是"少跑几个检查"，而是**让检查只在它有意义时跑**：门禁的触发范围由
**staged 内容**决定。于是 9 道收敛为 3 道：

| 门禁 | 触发条件 | 内容 |
|---|---|---|
| `code` | staged 含未归档 `.py` | `ruff check` + `ruff format --check` |
| `text` | staged 含文本/`.md`/钩子 | `check_encoding` + markdownlint |
| `l0` | staged 触及 L0 面（见 `L0_PREFIXES`） | `startup_budget` + `render_index --check` |

绝大多数提交只跑 `code` 或 `text`，`l0` 面（L0 文档 / 权威区卡 / 渲染器 / 分型源）
只有真的改到才跑。
"""

from __future__ import annotations

from pathlib import PurePosixPath

GATES: tuple[str, ...] = ("code", "text", "l0")

TEXT_EXTS: frozenset[str] = frozenset(
    {
        ".py",
        ".ps1",
        ".bat",
        ".cmd",
        ".vbs",
        ".js",
        ".ts",
        ".tsx",
        ".cs",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".go",
        ".rs",
        ".java",
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".xml",
        ".csv",
    }
)

# L0 面 = **l0 门禁那两项检查的输入面**（定义要精确：多一个只是白跑，少一个就是门禁失效）
#   - `startup_budget` 的输入：AGENTS/CHARTER/WORK + INDEX*.md + L1 卡（= 权威区卡）
#   - `render_index` 的输入：权威区卡 + 渲染器及其派生模块（hub_registry / index_limits / index_files）
#   - `task_tier`：L1 分型源，直接决定 L1 预算的分子
# 注：`tools/inject.py` 会改各平台注入的 L0 文本，但**不在这两项检查的输入面内**，
#     放进来只会白跑门禁 → 刻意不收。
from common.authority import AUTHORITY_DIRS as _AUTHORITY_DIRS  # noqa: E402

L0_FILES: frozenset[str] = frozenset(
    {
        "AGENTS.md",
        "CHARTER.md",
        "WORK.md",
        "hub-engine/scripts/startup_budget.py",
        "hub-engine/scripts/render_index.py",
        "hub-engine/tools/hub_registry.py",
        "hub-engine/tools/task_tier.py",
        "hub-engine/common/index_files.py",
        "hub-engine/common/index_limits.py",
    }
)
L0_PREFIXES: tuple[str, ...] = tuple(f"{d}/" for d in _AUTHORITY_DIRS)
# 2026-10-05（体检 A1 残留）：「权威区卡变更 ⇒ 跑 L0 门禁」这个耦合关系直接由
# common/authority.py 派生，避免再手措一份清单。**语义提醒**：此处的
# “权威区” = l0 门禁的输入面，与“参与检索的卡目录”（同为 AUTHORITY_DIRS）恰好同集，
# 但**不是同一概念**——将来若某个卡目录不需要跑 L0 门禁，就在这里显式排除，
# 不要去改 common/authority.py。


def _norm(path: str) -> str:
    """归一为仓库相对 posix 路径：兼容外层仓（`AgentMemoryHub/rules/x.md`）与中枢仓（`rules/x.md`）。"""
    p = str(path).replace("\\", "/").lstrip("./")
    if p.startswith("AgentMemoryHub/"):
        p = p[len("AgentMemoryHub/") :]
    return p


def classify(staged: list[str]) -> dict[str, bool]:
    """staged 路径列表 → `{门禁名: 是否触发}`。

    这是**唯一事实源**：两个（外层/中枢）pre-commit 钩子都调它，故不存在"钩子自述与实现不一致"。
    """
    paths = [_norm(p) for p in staged if p]
    live = paths  # 归档区已按 D8 协议取消（退役 = git rm，见 docs/compose/cleanup/retire-protocol.md）

    code = any(p.endswith(".py") for p in live)
    text = any(PurePosixPath(p).suffix.lower() in TEXT_EXTS or PurePosixPath(p).name == "pre-commit" for p in live)
    l0 = any(
        p in L0_FILES
        or PurePosixPath(p).name.startswith("INDEX")
        or (("/" not in p) and p.startswith("INDEX"))
        or any(p.startswith(pref) for pref in L0_PREFIXES)
        for p in live
    )
    return {"code": code, "text": text, "l0": l0}


def gates_to_run(staged: list[str]) -> list[str]:
    """要跑的门禁名（保持 GATES 顺序，便于日志稳定）。"""
    flags = classify(staged)
    return [g for g in GATES if flags[g]]
