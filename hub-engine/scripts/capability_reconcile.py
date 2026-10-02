# @version V1.0 / 2026-10-02 / pi / 能力对账：声明态 vs 实测态 + 常驻成本帽（M2/Task 17+18）
"""capability_reconcile —— 能力账本对账（架构重构 M2/Task 17 + 18）。

## 两个"态"

| 态 | 位置 | 回答 |
|---|---|---|
| **声明态**（期望） | `AgentMemoryHub/hub.config.yaml` 的 `platforms:` | 我们**期望**哪个平台装什么、装在哪 |
| **实测态**（事实） | `AgentMemoryHub/system/capabilities.json`（由 `capability_scan` 渲染） | 磁盘上**实际**是什么 |

## 对账口径（沿用 `router_sync` 的"声明 vs 覆盖度"范式）

| 差异 | 含义 | 级别 |
|---|---|---|
| `declared_only` | 声明了 `mcp_config_path`/`skills_dir`，但**磁盘上不存在** | **fail**（登记了却没装 ⇒ 台账在撒谎） |
| `actual_only` | 磁盘上有 MCP 配置，但**未登记** | **warn**（装了没登记 ⇒ 下次换机必丢） |
| `matched` | 两边都有 | ok |

## 成本帽（Task 18）

`platforms_global.capability_budget.max_discovery_tokens` —— 全平台**常驻发现成本**上限。
本帽是**棘轮**：初始值取上线时的实测值，此后**只许降不许抬**；
超帽必须把某项能力降级为 `conditional`/`not-installed`，而不是改数字
（沿用 L0 预算帽的既定裁定口径：抬帽 = 把结构病记成资源配置问题）。

用法：
    python -m scripts.capability_reconcile            # 人读报告
    python -m scripts.capability_reconcile --json     # 机器可读
退出码：0 全绿｜1 有 fail｜2 有 warn
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

from common.config import HubConfig, platform_meta  # noqa: E402
from scripts.capability_scan import (  # noqa: E402
    _paths,
    _skills_dir,
    discovery_cost,
)

DEFAULT_BUDGET_TOKENS = 0  # 0 = 未设帽（不检查）


def actual(root: Path) -> dict:
    """读实测态产物（**事实源仍是平台配置本身**，这里只为不重复扫描）。"""
    json_path, _md = _paths(root)
    if not json_path.is_file():
        return {}
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def budget(root: Path) -> int:
    cfg = HubConfig.load(root).data
    glob = cfg.get("platforms_global") or {}
    cap = glob.get("capability_budget") or {}
    try:
        return int(cap.get("max_discovery_tokens") or DEFAULT_BUDGET_TOKENS)
    except (TypeError, ValueError):
        return DEFAULT_BUDGET_TOKENS


def reconcile(root: Path) -> dict:
    meta = platform_meta(root)["platforms"]
    act = actual(root)
    mcp_actual = act.get("mcp") or {}
    skills_actual = act.get("skills") or {}

    declared_only: list[dict] = []
    actual_only: list[dict] = []
    matched: list[str] = []

    for name, info in meta.items():
        info = info or {}
        problems: list[str] = []
        raw_mcp = info.get("mcp_config_path")
        if raw_mcp:
            p = Path(str(raw_mcp).replace("\\", "/"))
            p = p if p.is_absolute() else Path.home() / p
            if not p.is_file():
                problems.append(f"mcp_config_path 不存在：{p}")
            elif name not in mcp_actual:
                problems.append("实测态里没有该平台的 MCP 记录（跑 `capability_scan --write`）")
        if info.get("skills_dir"):
            d = _skills_dir(info)
            if not d or not d.is_dir():
                problems.append(f"skills_dir 不存在：{info.get('skills_dir')}")
        if problems:
            declared_only.append({"platform": name, "problems": problems})
        else:
            matched.append(name)

    # 实测有、声明无（含别名平台）
    declared_names = set(meta)
    for name in mcp_actual:
        if name not in declared_names:
            actual_only.append({"platform": name, "what": "有 MCP 配置但未在 hub.config.yaml 登记"})
    for name, v in skills_actual.items():
        if name not in declared_names and v.get("count"):
            actual_only.append({"platform": name, "what": f"有 {v['count']} 个技能目录但未登记"})

    costs = discovery_cost(root)
    total = sum(c["total_tokens"] for c in costs.values())
    cap = budget(root)
    over = cap > 0 and total > cap

    return {
        "matched": sorted(matched),
        "declared_only": declared_only,
        "actual_only": actual_only,
        "discovery_cost_total": total,
        "budget_tokens": cap,
        "budget_over": over,
        "cost_by_platform": costs,
    }


def render(r: dict) -> str:
    lines = ["# 能力对账（声明态 vs 实测态）", ""]
    lines.append(f"- 一致平台：{', '.join(r['matched']) or '（无）'}")
    lines.append(f"- **声明了却没装**（fail）：{len(r['declared_only'])} 项")
    for d in r["declared_only"]:
        lines.append(f"  - {d['platform']}：{'；'.join(d['problems'])}")
    lines.append(f"- **装了却没登记**（warn）：{len(r['actual_only'])} 项")
    for d in r["actual_only"]:
        lines.append(f"  - {d['platform']}：{d['what']}")
    lines.append("")
    cap = r["budget_tokens"]
    lines.append(
        f"- 常驻发现成本：**{r['discovery_cost_total']} token/会话**" + (f"（帽 {cap}）" if cap else "（未设帽）")
    )
    if r["budget_over"]:
        lines.append(
            f"  - ⚠️ **超帽 {r['discovery_cost_total'] - cap} token**：必须把某项能力降级为"
            " `conditional`/`not-installed`，**不得抬帽**（抬帽 = 把结构病记成资源配置问题）"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="能力对账（声明态 vs 实测态）")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = args.root or (_HUB_ENGINE.parent / "AgentMemoryHub")
    r = reconcile(root)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(render(r))
    if r["declared_only"]:
        return 1
    return 2 if (r["actual_only"] or r["budget_over"]) else 0


if __name__ == "__main__":
    sys.exit(main())
