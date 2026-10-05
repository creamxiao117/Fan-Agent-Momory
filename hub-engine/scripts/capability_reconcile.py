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

# 软目标：单平台**单会话**常驻发现成本的 aspiration。仅报告，**从不拦提交**。
DEFAULT_TARGET_TOKENS = 1500
DEFAULT_MCP_MAX = 5


def actual(root: Path) -> dict:
    """读实测态产物（**事实源仍是平台配置本身**，这里只为不重复扫描）。"""
    json_path, _md = _paths(root)
    if not json_path.is_file():
        return {}
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def ratchet(root: Path) -> dict[str, int]:
    """每平台单会话常驻成本的**硬棘轮**：只许降不许升（基线登记在 hub.config.yaml）。

    为什么是「逐平台棘轮」而不是「一个总数帽」：常驻成本是**每个客户端各自付**的。
    跨平台求和（2026-10-02 曾为 8836）**不约束任何一次真实会话**——最贵的单平台也才 3264。
    那把求和当帽，等于用错误的量做治理（数字吓人、行为毫无约束）。

    棘轮挡的是真实退化：「加了新能力却没换掉旧的」。它天然不会阻断例行工作，
    因为基线就是当前实测值（门禁别自我放大的反面）。
    """
    cfg = HubConfig.load(root).data
    cap = (cfg.get("platforms_global") or {}).get("capability_budget") or {}
    raw = cap.get("per_platform_ratchet") or {}
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def budgets(root: Path) -> dict[str, int]:
    """软目标配置：`{"per_session_target": 1500, "mcp_servers_max": 5}`。"""
    cfg = HubConfig.load(root).data
    cap = (cfg.get("platforms_global") or {}).get("capability_budget") or {}

    def _int(key: str, default: int) -> int:
        try:
            return int(cap.get(key) or default)
        except (TypeError, ValueError):
            return default

    return {
        "per_session_target": _int("per_session_target", DEFAULT_TARGET_TOKENS),
        "mcp_servers_max": _int("mcp_servers_max", DEFAULT_MCP_MAX),
    }


def registry_coverage(root: Path) -> dict:
    """SkillHub **登记覆盖率**：声明态（router.yaml）vs 实测态（各客户端技能目录）。

    为什么需要它：2026-10-02 实测发现三个集合**并不重合** ——
    75 条路由记录 / 47 个有 SKILL.md 的实现 / **103 个实测装过的技能名**。
    也就是说：「能力通胀」的大头（85 个技能）**根本没进过登记表**，
    而这恰恰是不可见的部分：没登记 ⇒ 没人知道它存在 ⇒ 没人裁它该不该常驻。

    本函数只**计量**（软指标、只报不拦），把缺口从"看不见"变成"每次都看得见"。
    不自动补登记：`trigger`/`forgot` 要靠人写，机器从名字编出来的路由会误命中
    （误命中比没有更糟 —— 见 router/schema.yaml 开头）。
    """
    from common.config import HubConfig, external_path

    hub_path = external_path("skillhub", root) or (HubConfig.load(root).data.get("external_paths") or {}).get(
        "skillhub"
    )
    out: dict = {"available": False}
    if not hub_path:
        return out
    sh = Path(str(hub_path))
    f = sh / "router" / "router.yaml"
    if not f.is_file():
        return out
    try:
        import yaml

        rows = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("skills") or []
    except Exception:  # noqa: BLE001 - 读不到当"无法计量"，不猜
        return out

    recorded = {str(r["name"]) for r in rows if isinstance(r, dict) and r.get("name")}
    mcp_records = {str(r["name"]) for r in rows if isinstance(r, dict) and str(r.get("kind") or "skill") == "mcp"}
    # schema（router/schema.yaml 顶层）要求登记记录**逐一对应 skills/<name>/skill.yaml**
    # ⇒ 实现的判据是 skill.yaml（SKILL.md 只是 instructions）——2026-10-05 修：
    # 原判据只认 SKILL.md，导致"有 skill.yaml 但无 SKILL.md"的技能被误判无实现。
    impl = {q.parent.name for q in (sh / "skills").rglob("skill.yaml")}
    impl |= {q.parent.name for q in (sh / "skills").rglob("SKILL.md")}
    # 2026-10-05 修（**假阳性根因**）：实现可能装在**客户端技能目录**而非 SkillHub 仓内
    # ——实测 22 条 "recorded_but_unimplemented" 里 15 条其实有客户端实现
    # （1password / obsidian / sherlock / skill-creator …）。原实现只看 SkillHub 侧，
    # 于是这个指标长期误报，逼维护者反复手工取证（本会话就干过一次）。
    # 现把各平台 skills_dir 的来源并入 impl。
    try:
        from common.config import load_yaml

        _cfg = load_yaml(root / "hub.config.yaml") or {}
        for _meta in (_cfg.get("platforms") or {}).values():
            _dir = (_meta or {}).get("skills_dir")
            if _dir and Path(_dir).is_dir():
                impl |= {q.parent.name for q in Path(_dir).rglob("SKILL.md")}
    except Exception:  # 配置缺失/权限问题不该让对账整体失败（软指标）
        pass
    installed = set()
    for info in (actual(root).get("skills") or {}).values():
        installed.update(info.get("skills") or [])

    unregistered = sorted(installed - recorded)
    unimplemented = sorted(recorded - impl - mcp_records)
    return {
        "available": True,
        "recorded": len(recorded),
        "implemented": len(impl),
        "measured_installed": len(installed),
        "unregistered_installed": unregistered,
        "recorded_but_unimplemented": unimplemented,
    }


def _worst(costs: dict[str, dict]) -> dict:
    """最贵单平台（要在渲染里当一句话讲，所以在这里算清）。"""
    if not costs:
        return {"platform": None, "tokens": 0}
    plat = max(costs.items(), key=lambda kv: kv[1]["per_session_tokens"])[0]
    return {"platform": plat, "tokens": costs[plat]["per_session_tokens"]}


def cost_report(root: Path) -> dict:
    """成本判定：**逐平台**硬棘轮 + 软目标 + 降级候选（从 `reconcile` 抽出以降低复杂度）。"""
    costs = discovery_cost(root)
    fleet = sum(c["per_session_tokens"] for c in costs.values())
    caps = ratchet(root)
    soft = budgets(root)

    # 硬：超棘轮（加了能力却没换掉旧的）
    over_ratchet: list[dict] = []
    for plat, c in sorted(costs.items(), key=lambda kv: -kv[1]["per_session_tokens"]):
        cap = caps.get(plat)
        if cap is not None and c["per_session_tokens"] > cap:
            over_ratchet.append(
                {
                    "platform": plat,
                    "tokens": c["per_session_tokens"],
                    "cap": cap,
                    "over": c["per_session_tokens"] - cap,
                }
            )

    # 软：超目标（带具体降级候选，交用户批准；**只报不拦**）
    target = soft["per_session_target"]
    over_target: list[dict] = []
    for plat, c in sorted(costs.items(), key=lambda kv: -kv[1]["per_session_tokens"]):
        if target > 0 and c["per_session_tokens"] > target:
            over_target.append(
                {
                    "platform": plat,
                    "tokens": c["per_session_tokens"],
                    "target": target,
                    "over": c["per_session_tokens"] - target,
                    "top_skills": c.get("top_skills") or [],
                    "mcp_servers": c.get("mcp_servers", 0),
                }
            )
    return {
        "costs": costs,
        "fleet": fleet,
        "caps": caps,
        "soft": soft,
        "over_ratchet": over_ratchet,
        "over_target": over_target,
        "worst": _worst(costs),
    }


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

    rep = cost_report(root)
    return {
        "matched": sorted(matched),
        "declared_only": declared_only,
        "actual_only": actual_only,
        "cost_by_platform": rep["costs"],
        "fleet_tokens": rep["fleet"],  # 仅库存参考；**不设帽**
        "worst_platform": rep["worst"],
        "budgets": {**rep["soft"], "per_platform_ratchet": rep["caps"]},
        "over_ratchet": rep["over_ratchet"],
        "over_target": rep["over_target"],
        "registry": registry_coverage(root),
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
    lines.append("## 单会话常驻发现成本（每个客户端各付各的）")
    lines.append("")
    lines.append("| 平台 | 单会话 token | 该平台棘轮 | 状态 |")
    lines.append("| --- | --- | --- | --- |")
    caps = r["budgets"]["per_platform_ratchet"]
    target = r["budgets"]["per_session_target"]
    for plat, c in sorted(r["cost_by_platform"].items(), key=lambda kv: -kv[1]["per_session_tokens"]):
        n = c["per_session_tokens"]
        cap = caps.get(plat)
        if cap is None:
            st = "（未登记棘轮）"
        elif n > cap:
            st = f"❌ **超棘轮 {n - cap}**"
        elif target and n > target:
            st = f"⚠️ 超目标 {n - target}（待降级，需批准）"
        else:
            st = "✅"
        lines.append(f"| {plat} | {n} | {cap if cap is not None else '—'} | {st} |")
    lines.append("")
    lines.append(
        f"- 最贵单平台：**{r['worst_platform']['platform']} {r['worst_platform']['tokens']} token/会话**；软目标 {target}"
    )
    lines.append(
        f"- 全平台求和 **{r['fleet_tokens']}** —— 库存参考，**不是任何会话的成本、不设帽**"
        "（2026-10-02 教训：曾把此求和当帽，它对真实会话毫无约束）"
    )
    for d in r["over_ratchet"]:
        lines.append(
            f"  - ❌ {d['platform']} 超棘轮 {d['over']} token（{d['tokens']} > {d['cap']}）："
            "要么换掉旧能力，要么把新能力降级为 `conditional`/`not-installed`；**不得改基线**"
        )
    reg = r.get("registry") or {}
    if reg.get("available"):
        lines.append("")
        lines.append("### SkillHub 登记覆盖率（软指标：缺口要可见，不自动补登记）")
        lines.append("")
        lines.append(
            f"- 登记记录 **{reg['recorded']}** / 有 SKILL.md 的实现 **{reg['implemented']}**"
            f" / 实测装过的技能名 **{reg['measured_installed']}**"
        )
        lines.append(
            f"- ⚠️ **实测装了但从未登记**：{len(reg['unregistered_installed'])} 个"
            "（这些才是常驻成本的大头，且没人审过它们该不该常驻；补登记需人写 trigger/forgot，"
            "机器从名字编路由会误命中）"
        )
        lines.append(
            f"- ⚠️ **登记了却查无实现**（无 SKILL.md 且非 mcp）："
            f"{len(reg['recorded_but_unimplemented'])} 个 —— 要么补实现，要么删记录"
        )
        if reg["recorded_but_unimplemented"]:
            lines.append(f"  - {', '.join(reg['recorded_but_unimplemented'])}")
    if r["over_target"]:
        lines.append("")
        lines.append("### 降级候选（软目标，需用户批准后执行；**不拦提交**）")
        for d in r["over_target"]:
            top = "、".join(f"`{n}`({t})" for n, t in d["top_skills"])
            lines.append(
                f"- {d['platform']}：超目标 {d['over']} token；最贵的技能 {top or '（无）'}；"
                f"MCP server {d['mcp_servers']} 个"
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
    if r["actual_only"] or r["over_ratchet"]:
        return 2
    return 0  # over_target 是**软目标**（积压项），只报不拦 —— 否则会训练出 --no-verify


if __name__ == "__main__":
    sys.exit(main())
