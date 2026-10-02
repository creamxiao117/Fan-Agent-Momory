# @version V2.0 / 2026-10-02 / pi / 模块台账 INVENTORY.json + 职责重复检测（V2 修假阳性）
"""inventory —— hub-engine 模块台账（**渲染产物 + --check**）与**职责重复检测**。

## 为什么要有它（本仓第三次复发的病）

`audit_dead_modules` 实测输出「**零引用模块: 0**」，但系统明明臃肿（105 个模块、
9 道提交门禁、25 步巡检、≥7 种报告产物）。原因不是工具有 bug，是**尺子只有一把**：

> **冗余 ≠ 没被引用；冗余 = 多处引用同一个职责。**

用"零引用"这把尺子去量一个有 3 个 INDEX 一致性检查器、4 处健康快照采集、5 个检索评测脚本
的系统，结果必然是 0。本模块补上**第二把尺子**。

## V2 的关键修正（V1 的教训：坏尺子比没尺子更糟）

V1 用「产物文件名字面量重叠」做聚类 ⇒ 把 40+ 个模块标成 duplicate，其中 `hub_registry` /
`render_index` / `mcp_handlers` / `startup_budget` / `status` 全是**明显的活模块**
（因为大家都提到 `INDEX.md`、`lint-report-*.md`）。同时 `module` 键用 stem ⇒
`tools/lint.py` 与 `commands/lint.py` 撞名互相"重复"。两条都修：

1. **键唯一化**：`<kind>/<stem>`（如 `tools/lint`、`commands/lint`）。
2. **引用度改用 AST**（而非正则）：`from a.b.X import y` 与 `import a.b.X` 都能识别
   ——V1 漏掉前者，导致 `snippet`/`mcp_policy`/`resilience` 等**被误判 unused**。
3. **重复判据改为「声明 + 验证」**：职责是否重复是**语义判断**，由人裁定一次并
   **声明**在本模块的 `DECLARED_DUPLICATES`（可复核、可门禁）；工具负责
   **验证声明是否仍然成立**（被取代者是否还在、保留者是否还活着），并对
   **未声明但高相似**的对只标 `review`（建议），绝不自动判 `duplicate`。
   ——"工具发明聚类"就是 V1 失败的根因。

## `verdict` 口径（"保留需举证"，架构重构 D6）

| verdict | 含义 |
|---|---|
| `keep` | 有 `gate_role`（今天真在拦东西）或有**活代码**引用 |
| `duplicate` | 命中 `DECLARED_DUPLICATES`（有取代者）→ 归档候选 |
| `review` | 未声明但同门禁+同 kind+职责词高相似 → **待人工复核**，不是结论 |
| `manual-cli` | 带 `__main__` 的人工 CLI：有存在理由，但**移出门禁视野** |
| `unused` | 三无（无活引用 / 无 gate_role / 非 CLI）→ 归档候选 |

**不自动删**：`--candidates` 只产出人工裁定清单。

用法：
    python -m scripts.inventory --write      # 写 INVENTORY.json
    python -m scripts.inventory --check      # 与磁盘比对（0/3）
    python -m scripts.inventory              # 打印人读台账
    python -m scripts.inventory --candidates # 只列归档候选 + 待复核
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

REPO = _HUB_ENGINE.parent
HUB = REPO / "AgentMemoryHub"
OUT_REL = Path("scripts") / "INVENTORY.json"
# 台账落中枢 system 侧（与 capabilities 同区）；作为模块常量以便测试注入
INVENTORY_PATH: Path = HUB / OUT_REL
CST = timezone(timedelta(hours=8))

# 产物文件名字面量（列在台账里供人看，**不参与聚类**——V1 的教训）
ARTIFACT_RE = re.compile(r"[\"']([A-Za-z0-9_\-.]+\.(?:json|jsonl|md|html))[\"']")
ARTIFACT_DROP = {"package.json", "requirements.txt", "pyproject.toml", "mcp.json", "bundle.js"}

# 门禁/编排器文件（它们调用谁 = 谁的 gate_role）
GATE_FILES = (
    _HUB_ENGINE / "scripts" / "pre-commit",
    _HUB_ENGINE / "scripts" / "patrol_runner.py",
    _HUB_ENGINE / "scripts" / "patrol" / "steps.py",
    REPO / ".git" / "hooks" / "pre-commit",
    HUB / ".git" / "hooks" / "pre-commit",
)

# 职责词白名单（只在这些词里比 jaccard，避免虚词造成假重叠）
RESP_WORDS = frozenset(
    {
        "index",
        "l0",
        "l1",
        "lint",
        "card",
        "cards",
        "frontmatter",
        "schema",
        "encoding",
        "bom",
        "eol",
        "health",
        "healthcheck",
        "platform",
        "mcp",
        "launcher",
        "report",
        "metrics",
        "snapshot",
        "regression",
        "recall",
        "bench",
        "vector",
        "sleep",
        "review",
        "query",
        "missing",
        "gap",
        "fix",
        "auto",
        "migrate",
        "promote",
        "distill",
        "ingest",
        "render",
        "audit",
        "dead",
        "modules",
        "capability",
        "skill",
        "budget",
        "startup",
        "context",
        "artifact",
        "ledger",
        "consistency",
        "dashboard",
        "daily",
        "cleanup",
    }
)

# ── **声明的**职责重复（人裁定；工具只验证，不发明）────────────────────
# 每条：保留者 + 被取代者列表 + 一句判据。`--check` 会验证双方都还在。
# 新增条目请同步 `docs/compose/reports/` 的裁定记录（证据：引用/产物时间戳）。
DECLARED_DUPLICATES: list[dict] = [
    {
        "keep": "scripts/render_index",
        "retire": ["scripts/index_consistency", "scripts/audit_index"],
        "why": "INDEX 一致性的唯一实现 = 渲染器 --check；另两个自称同一职责（均带『一致性』）",
    },
    # 2026-10-02 已物理退役（不再登记；verify_declarations 只验证"仍在磁盘"的声明）：
    #   missing_query / knowledge_gap · check_encoding / nightly_log_encoding_check+strip_bom ·
    #   capability_scan / platform_unregistered · audit_dead_modules（被本模块吸收）
    # 注：`scripts/audit_dead_modules` 已于 2026-10-02 git rm（本模块吸收其引用扫描并换 AST 实现）
    # —— 已被物理删除者不再登记（`verify_declarations` 只验证"仍在磁盘"的声明）。
]


def module_key(p: Path) -> str:
    """模块唯一键 = `<kind>/<stem>`（V1 用裸 stem ⇒ tools/lint 与 commands/lint 撞名）。"""
    return f"{p.parent.name}/{p.stem}"


def module_files() -> list[Path]:
    """参与台账的模块（排除 `__init__.py`——它们是包标记/导出定义，不是候选模块）。"""
    out = []
    for p in sorted(_HUB_ENGINE.rglob("*.py")):
        if "__pycache__" in p.parts or "tests" in p.parts or "_retired" in p.parts:
            continue
        if p.name == "__init__.py":
            continue
        out.append(p)
    return out


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def first_line(path: Path) -> str:
    """模块文档首句（职责声明的最近似物）。"""
    try:
        doc = ast.get_docstring(ast.parse(read_text(path))) or ""
    except SyntaxError:
        doc = ""
    for line in doc.strip().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:120]
    return ""


def imported_names(src: str) -> set[str]:
    """AST 提取本模块 import 的所有模块名（取 dotted 末段）——**不用正则**。

    V1 只用 `import\\s+X` 正则 ⇒ 漏掉 `from a.b.X import y`（本仓**全部**跨模块导入
    都是这种形态），于是 `snippet` / `mcp_policy` / `resilience` 等被误判 `unused`。
    """
    names: set[str] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[-1])
    return names


def artifacts_of(path: Path) -> list[str]:
    names = {m.group(1) for m in ARTIFACT_RE.finditer(read_text(path))}
    return sorted(n for n in names if n not in ARTIFACT_DROP)


def gate_roles(keys: dict[str, Path]) -> dict[str, str]:
    """模块 → 调用它的门禁/编排器文件名（只扫门禁面，不看文档）。"""
    roles: dict[str, str] = {}
    for gf in GATE_FILES:
        if not gf.is_file():
            continue
        text = read_text(gf)
        for key, path in keys.items():
            stem = path.stem
            if re.search(rf"(?<![\w.]){re.escape(stem)}\.py\b", text) or re.search(
                rf"(?<![\w.]){re.escape(stem)}\b", text
            ):
                roles.setdefault(key, gf.name)
    return roles


SCAN_EXTS = {".sh", ".cmd", ".bat", ".ps1", ".md", ".yaml", ".yml", ".json", ".toml"}


def _scan_one(p, keys, stem_to_keys, code, test, doc) -> None:
    """把「单个引用来源文件」记入对应桶（抽出以压 refs_of 的圈复杂度）。"""
    if not p.is_file() or "__pycache__" in p.parts or "_retired" in p.parts:
        return
    suffix = p.suffix.lower()
    is_py = suffix == ".py"
    if not is_py and suffix not in SCAN_EXTS and p.name != "pre-commit":
        return
    text = read_text(p)
    if not text:
        return
    if "tests" in p.parts:
        bucket = test
    elif is_py or suffix in {".sh", ".cmd", ".bat", ".ps1"}:
        bucket = code
    else:
        bucket = doc

    rel = p.relative_to(REPO).as_posix()
    if is_py:
        names = imported_names(text)
        names.discard(p.stem)  # 自引用不算
        for name in names:
            for key in stem_to_keys.get(name, []):
                if keys[key] != p:
                    bucket[key].add(rel)
        return
    # 非 py：只看「作为脚本被调用」的形态（`x.py`）
    for stem, ks in stem_to_keys.items():
        if re.search(rf"(?<![\w.]){re.escape(stem)}\.py\b", text):
            for key in ks:
                bucket[key].add(rel)


def refs_of(keys: dict[str, Path]) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    """引用度三分：活代码 / 测试 / 文档（doc 仅作存活参考，**不作保留理由**）。"""
    code: dict[str, set[str]] = defaultdict(set)
    test: dict[str, set[str]] = defaultdict(set)
    doc: dict[str, set[str]] = defaultdict(set)
    stem_to_keys: dict[str, list[str]] = defaultdict(list)
    for key, path in keys.items():
        stem_to_keys[path.stem].append(key)

    for p in sorted(_HUB_ENGINE.rglob("*")):
        _scan_one(p, keys, stem_to_keys, code, test, doc)

    return (
        {k: sorted(v) for k, v in code.items()},
        {k: sorted(v) for k, v in test.items()},
        {k: sorted(v) for k, v in doc.items()},
    )


def _resp_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", text.lower())) & RESP_WORDS


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def declared_map() -> dict[str, str]:
    """声明的 `{被取代键: 保留键}`（含**存在性验证**，见 `verify_declarations`）。"""
    out: dict[str, str] = {}
    for grp in DECLARED_DUPLICATES:
        for r in grp["retire"]:
            out[r] = grp["keep"]
    return out


def verify_declarations(keys: dict[str, Path]) -> list[str]:
    """验证声明仍成立：双方都还在。缺一边即"声明过期"，必须人工更新（否则台账撒谎）。"""
    errs: list[str] = []
    for grp in DECLARED_DUPLICATES:
        if grp["keep"] not in keys:
            errs.append(f"DECLARED_DUPLICATES 的保留者不存在：{grp['keep']}")
        for r in grp["retire"]:
            if r not in keys:
                errs.append(f"DECLARED_DUPLICATES 的被取代者已不在磁盘（声明过期，请更新）：{r}")
    return errs


def review_pairs(rows: list[dict]) -> list[list[str]]:
    """未声明但高相似的对 → **只标 review**（建议人工复核），绝不自动判 duplicate。

    判据收紧为三条同时满足：同一门禁 + 同 kind + 职责词 jaccard ≥ 0.5。
    """
    out = []
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if a["kind"] != b["kind"] or not a["gate_role"] or a["gate_role"] != b["gate_role"]:
                continue
            if a["module"] in declared_map() or b["module"] in declared_map():
                continue
            if jaccard(set(a["resp_words"]), set(b["resp_words"])) >= 0.5:
                out.append(sorted([a["module"], b["module"]]))
    return out


def build() -> dict:
    files = module_files()
    keys = {module_key(p): p for p in files}
    gates = gate_roles(keys)
    code, test, doc = refs_of(keys)
    dup = declared_map()

    rows = []
    for key, p in keys.items():
        src = read_text(p)
        resp = first_line(p)
        rows.append(
            {
                "module": key,
                "path": p.relative_to(REPO).as_posix(),
                "kind": p.parent.name,
                "resp": resp,
                "refs_code": code.get(key, []),
                "refs_test": test.get(key, []),
                "refs_doc": doc.get(key, []),
                "gate_role": gates.get(key),
                "artifacts": artifacts_of(p),
                "resp_words": sorted(_resp_words(resp)),
                "has_main": "__main__" in src,
                # 诚实口径：无证据就是 null，不猜日期
                "last_run": None,
                "duplicate_of": dup.get(key),
                "verdict": "keep",
            }
        )

    for r in rows:
        if r["duplicate_of"]:
            r["verdict"] = "duplicate"
        elif r["gate_role"] or r["refs_code"]:
            r["verdict"] = "keep"
        elif r["has_main"]:
            r["verdict"] = "manual-cli"
        else:
            r["verdict"] = "unused"

    for pair in review_pairs(rows):
        for r in rows:
            if r["module"] in pair and r["verdict"] == "keep" and not r["gate_role"]:
                r["verdict"] = "review"

    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["verdict"]] += 1
    return {
        "generated_at": datetime.now(CST).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "note": (
            "渲染产物（禁手改）。保留需举证：keep=有 gate_role 或活代码引用；"
            "duplicate=命中 DECLARED_DUPLICATES（人裁定）；review=未声明但高相似（待复核）；"
            "manual-cli=人工 CLI；unused=三无。last_run 无证据时一律 null（不猜）。"
        ),
        "declarations": DECLARED_DUPLICATES,
        "declaration_errors": verify_declarations(keys),
        "totals": {"modules": len(rows), **dict(sorted(counts.items()))},
        "modules": sorted(rows, key=lambda r: r["module"]),
    }


def render(data: dict) -> str:
    t = data["totals"]
    lines = [
        "# hub-engine 模块台账（渲染产物，禁手改）",
        "",
        f"> 由 `python -m scripts.inventory --write` 生成。生成时间 {data['generated_at']}",
        f"> 模块 **{t['modules']}** 个：keep {t.get('keep', 0)} · duplicate {t.get('duplicate', 0)} · "
        f"review {t.get('review', 0)} · manual-cli {t.get('manual-cli', 0)} · unused {t.get('unused', 0)}",
        "> 判据：**保留需举证**（旧标准「证明它没用才删」会让系统只增不减）。",
        "> 「职责重复」是**人裁定 + 声明**（`DECLARED_DUPLICATES`），工具只验证不发明——",
        "> V1 曾用产物名聚类，把 40+ 个活模块误判 duplicate，比没有尺子更糟。",
        "",
        "## 归档候选（duplicate / unused）",
        "",
        "| 模块 | verdict | 被谁取代 | 活引用 | 门禁 | 职责 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in data["modules"]:
        if r["verdict"] in {"duplicate", "unused"}:
            lines.append(
                f"| `{r['module']}` | {r['verdict']} | {r['duplicate_of'] or '—'} | "
                f"{len(r['refs_code'])} | {r['gate_role'] or '—'} | {r['resp'][:60]} |"
            )
    lines += ["", "## 待人工复核（review：高相似但未声明）", ""]
    rev = [r["module"] for r in data["modules"] if r["verdict"] == "review"]
    lines += [f"- `{m}`" for m in rev] or ["（无）"]
    lines += [
        "",
        "## 全量",
        "",
        "| 模块 | kind | verdict | gate | 活引用 | 产物 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in data["modules"]:
        lines.append(
            f"| `{r['module']}` | {r['kind']} | {r['verdict']} | {r['gate_role'] or '—'} | "
            f"{len(r['refs_code'])} | {', '.join(r['artifacts'][:3]) or '—'} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_products() -> int:
    data = build()
    out = INVENTORY_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] 已渲染 {out.relative_to(REPO).as_posix()}")
    for e in data["declaration_errors"]:
        print(f"[WARN] {e}")
    return 0


def check() -> list[str]:
    out = INVENTORY_PATH
    if not out.is_file():
        return [f"产物缺失（先跑 --write）：{out.name}"]
    old = json.loads(out.read_text(encoding="utf-8"))
    new = build()
    errs = list(new["declaration_errors"])
    for d in (old, new):
        d.pop("generated_at", None)
        for m in d.get("modules", []):
            for volatile in ("refs_code", "refs_test", "refs_doc"):
                m.pop(volatile, None)
    if old != new:
        errs.append(f"{out.name} 与磁盘不一致（模块增删/职责变化未重渲）→ 跑 --write 修复")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="hub-engine 模块台账 + 职责重复检测")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--candidates", action="store_true", help="只列归档候选 + 待复核")
    args = ap.parse_args(argv)

    if args.write:
        return write_products()
    if args.check:
        errs = check()
        for e in errs:
            print(f"FAIL: {e}")
        if not errs:
            print("PASS: INVENTORY.json 与磁盘一致（含声明验证）")
        return 3 if errs else 0
    data = build()
    if args.candidates:
        for r in data["modules"]:
            if r["verdict"] in {"duplicate", "unused", "review"}:
                print(f"{r['verdict']:9s} {r['module']:34s} duplicate_of={r['duplicate_of'] or '-'}")
        return 0
    print(render(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
