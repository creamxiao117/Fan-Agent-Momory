# @version V1.0 / 2026-09-18 / Hermes / conflicts 区裁决执行（移入 _resolved_）
"""A 项：把已裁决的冲突组移入 .sync/conflicts/_resolved_20260918/。

裁决规则（不盲信 LLM 判决，只执行可验证的）：
  R1  action=merge 且 confidence>=0.8 且 target 与卡主题一致
  R2  action=skip 且权威区存在同主题/同 slug 卡（有承接物）
  R3  实测全文相似度 >=0.9（真重复）
否则 → 留在 conflicts/ 并进待办（低置信 / 主题漂移 / 无承接物）。

只移动，不删除；写 DECISION.md 记录逐组依据。
"""

from __future__ import annotations

import shutil
from pathlib import Path

HUB = Path(__file__).resolve().parents[1] / "AgentMemoryHub"
CONF = HUB / ".sync" / "conflicts"
DEST = CONF / "_resolved_20260918"

# (冲突卡名, 判决, 依据标签, 说明)
RESOLVE = [
    ("hermes_agent-platform-onboarding-paradigm", "merge/0.0→自身", "R3 真重复", "与权威卡全文相似度 0.96，同名同题"),
    ("hermes_dual-platform-coordination-3phase", "merge/0.9", "R1", "→ memory-hub-card-promotion.md"),
    ("hermes_T21-5platform-后续优化-待办", None, None, None),  # 占位，实际 HOLD
    (
        "trae_cad-addin-manager-dotnet-blueprint",
        "skip/0.0",
        "R2",
        "权威区已有 cadaddinmanager-hot-reload-architecture/-blueprint",
    ),
    ("trae_duckdb-vectorized-olap-blueprint", "merge/0.9", "R1", "→ duckdb-analytical-db-architecture-blueprint.md"),
    ("trae_embassy-embedded-rust-async-blueprint", "merge/0.95", "R1", "→ embassy-rs-async-embedded-architecture.md"),
    (
        "trae_litestar-asgi-api-framework-blueprint",
        "skip/0.0",
        "R2",
        "权威区已有 litestar-asgi-api-framework-blueprint.md（中英双版）",
    ),
    (
        "trae_llvm-compiler-infrastructure-blueprint",
        "merge/0.0",
        "R2",
        "→ llvm-mlir-compiler-infrastructure-architecture.md（同主题）",
    ),
    (
        "trae_metagpt-multi-agent-swe-methodology",
        "merge/0.0",
        "R2",
        "→ metagpt-multi-agent-sop-architecture.md（同主题）",
    ),
    (
        "trae_oxc-javascript-toolchain-architecture-blueprint",
        "merge/0.9",
        "R2",
        "target 漂移(verilator)，但权威区有同 slug 卡 oxc-javascript-toolchain-architecture-blueprint",
    ),
    (
        "trae_wasm3-portable-wasm-interpreter-blueprint",
        "merge/0.9",
        "R1",
        "→ wasmtime-wasm-runtime-multi-backend-blueprint.md",
    ),
    (
        "deepseek_dsh-plugin-dev-agents-md-in-project",
        "merge/0.9",
        "R1",
        "→ openai-agents-sdk-control-flow-architecture-blueprint.md",
    ),
    (
        "deepseek_task-trigger-phrases-for-orchestration",
        "merge/0.9",
        "R1",
        "→ agentscope-multi-agent-framework-blueprint.md",
    ),
    (
        "trae_wasmer-wasm-runtime-pluggable-engine-blueprint",
        "merge/0.81",
        "R1",
        "→ wasmtime-wasm-runtime-multi-backend-blueprint.md",
    ),
]

HOLD = [
    (
        "hermes_T21-5platform-后续优化-待办",
        "merge/0.9",
        "主题漂移",
        "target=hub-engine-push-no-card-scope-filter（与 5 平台待办无关）",
    ),
    (
        "trae_embassy-rs-embedded-async-blueprint",
        "merge/0.0",
        "主题漂移",
        "target=heapless-...（应为 embassy-rs-async-embedded-architecture）",
    ),
    ("deepseek_agent-trigger-symbols-7state", "skip/0.0", "低置信+无承接物", "权威区无同名/同主题卡，丢弃即丢内容"),
    ("hermes_T15-improvement-backlog", "skip/0.0", "低置信+无承接物", "backlog 卡无对应权威卡，丢弃有风险"),
]


def main() -> None:
    DEST.mkdir(exist_ok=True)
    moved, missing = [], []
    for name, verdict, rule, why in RESOLVE:
        if verdict is None:
            continue
        md, pj = CONF / f"{name}.md", CONF / f"{name}.pred.json"
        if not md.exists():
            missing.append(name)
            continue
        shutil.move(str(md), str(DEST / md.name))
        if pj.exists():
            shutil.move(str(pj), str(DEST / pj.name))
        moved.append((name, verdict, rule, why))
        print(f"  ✅ {name[:56]:<58} {verdict}  [{rule}]")

    lines = [
        "# conflicts 区裁决记录 — 2026-09-18",
        "",
        "执行：Hermes · 只移动不删除 · 依据 = 重判结果 + 可验证规则（R1/R2/R3）",
        "",
        f"## 已裁决（{len(moved)} 组，文件已移入本目录，内容可随时 `mv` 回）",
        "",
        "| 冲突卡 | 判决 | 规则 | 依据 |",
        "|:--|:--|:--|:--|",
    ]
    lines += [f"| `{n}` | {v} | {r} | {w} |" for n, v, r, w in moved]
    lines += [
        "",
        f"## 保留在 conflicts 未决（{len(HOLD)} 组，需人工）",
        "",
        "| 冲突卡 | 判决 | 保留原因 | 说明 |",
        "|:--|:--|:--|:--|",
    ]
    lines += [f"| `{n}` | {v} | {r} | {w} |" for n, v, r, w in HOLD]
    lines += [
        "",
        "## 规则定义",
        "",
        "- **R1** action=merge 且 confidence≥0.8 且 target 与卡主题一致",
        "- **R2** action=skip 且权威区存在同主题/同 slug 卡（有承接物）",
        "- **R3** 实测全文相似度 ≥0.9（真重复）",
        "- 其余（低置信 / 主题漂移 / 无承接物）→ 留 conflicts 交人工",
        "",
        "## 重判原始数据",
        "",
        "- `.sync/state/readjudicate-20260918.json`（12 组重判 + 5 组跳过）",
        "- 重判工具：`scripts/readjudicate_conflicts.py`",
    ]
    (DEST / "DECISION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n已裁决 {len(moved)} 组 / 保留 {len(HOLD)} 组")
    if missing:
        print(f"⚠️ 未找到: {missing}")
    print(f"conflicts 剩余未决: {len(list(CONF.glob('*.md')))} 组")


if __name__ == "__main__":
    main()
