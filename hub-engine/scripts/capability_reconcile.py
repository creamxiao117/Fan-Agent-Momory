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
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))

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

# ⚠️ 2026-11-13 修订（用户裁定：「软目标不该规定死一个数，对每个平台应该都不一样」）：
#   原口径 `per_session_target: 1500` 是**全平台统一常量** ⇒
#     ① 对不同平台、不同任务量级的会话**不合理**（workbuddy 3150 与 mavis 21 拿同一把尺子）；
#     ② 1500 是**拍出来的理想值**而非实测基线 ⇒ 从设立当天起就有 2 个平台常年超标，
#        报告天天报「超目标」却从来没人动 ⇒ **噪音掩盖真问题**。
#   新口径：
#     · `per_platform_target`：逐平台**各自**的目标线（可缺省 ⇒ 回落到实测基线）。
#     · 目标线的语义**不变**：仍是「该往哪降的方向」，仍**只报不拦**。
#     · 目标线**由月度体检维护**（只降不升 + 膨胀检测），不由人肉拍脑袋定。
#   保留 `per_session_target` 作**回退默认值**（老配置仍能工作，不破坏兼容性）。


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


def budgets(root: Path) -> dict:
    """预算配置：`{"per_session_target": 1500, "mcp_servers_max": 5, "reduction_target_ratio": 0.6}`。

    `reduction_target_ratio` = **季度降级目标**（非门禁）：常驻成本降到现状的该比例。
    为何是「目标」而不是「帽」：硬帽 = 逐平台棘轮（只许降不许升，见 `ratchet()`）；
    目标 = 方向（现状 60%），拿它当门禁会在第一天就红 ⇒ 训练出 --no-verify。
    """
    cfg = HubConfig.load(root).data
    cap = (cfg.get("platforms_global") or {}).get("capability_budget") or {}

    def _int(key: str, default: int) -> int:
        try:
            return int(cap.get(key) or default)
        except (TypeError, ValueError):
            return default

    def _float(key: str, default: float) -> float:
        try:
            return float(cap.get(key) or default)
        except (TypeError, ValueError):
            return default

    return {
        "per_session_target": _int("per_session_target", DEFAULT_TARGET_TOKENS),
        "per_platform_target": {
            str(k): int(v) for k, v in (cap.get("per_platform_target") or {}).items() if str(v).strip().isdigit()
        },
        "mcp_servers_max": _int("mcp_servers_max", DEFAULT_MCP_MAX),
        "reduction_target_ratio": _float("reduction_target_ratio", 0.6),
    }


def target_for(plat: str, budgets_map: dict) -> int:
    """取某平台的软目标线。

    优先级（2026-11-13 新口径）：
      1. `per_platform_target[plat]` —— 逐平台**各自**的目标线（首选）
      2. `per_session_target` —— 回退默认值（老配置兼容）

    ⚠️ 缺省时**回落到该平台自己的实测值**（而不是全局 1500）：
       没登记目标线的平台，等于「以现状为基线」⇒ 不报超目标。
       这才是「逐平台不同」的真实含义——不是给每个平台编一个新数字，
       而是**不再用一把尺子量所有平台**。
    """
    per_plat = budgets_map.get("per_platform_target") or {}
    if plat in per_plat:
        return int(per_plat[plat])
    return int(budgets_map.get("per_session_target") or 0)


def reduction_plan(root: Path, r: dict) -> list[dict]:
    """**降级路线图**：每个平台距「现状 × 比例」目标还差多少 token，降哪几项。

    与「软目标只报不拦」的区分：软目标报「超了多少」；本函数报「**降哪几项能达标**」——
    可执行清单（每项 = 降为 `conditional`/`explicit-only` 后能省的常驻 token）。

    口径：**逐平台**（每个客户端各自付各自那份），**不做全平台求和**
    （2026-10-02 教训：求和不约束任何一次真实会话）。
    """
    ratio = (r.get("budgets") or {}).get("reduction_target_ratio", 0.6)
    caps = (r.get("budgets") or {}).get("per_platform_ratchet", {})
    out: list[dict] = []
    for plat, c in sorted(r.get("cost_by_platform", {}).items()):
        cur = int(c.get("per_session_tokens") or 0)
        target = int(cur * ratio)
        need = max(0, cur - target)
        cap = caps.get(plat)
        picks: list[dict] = []
        saved = 0
        for item in c.get("top_skills") or []:
            if saved >= need:
                break
            name, tok = item[0], int(item[1] or 0)
            picks.append({"name": name, "tokens": tok, "kind": "skill"})
            saved += tok
        mcp_need = max(0, need - saved)
        out.append(
            {
                "platform": plat,
                "current_tokens": cur,
                "target_tokens": target,
                "ratio": ratio,
                "need_tokens": need,
                "ratchet": cap,
                "over_ratchet": bool(cap is not None and cur > int(cap)),
                "picks": picks,
                "mcp_servers_to_drop": (mcp_need + 199) // 200 if mcp_need > 0 else 0,
            }
        )
    return out


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
    hub_impl = {q.parent.name for q in (sh / "skills").rglob("skill.yaml")}
    hub_impl |= {q.parent.name for q in (sh / "skills").rglob("SKILL.md")}
    impl = set(hub_impl)
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

    # 2026-10-21 体检修复（口径过宽 ⇒ 指标永不收敛）：
    #   原判据 `installed - recorded` 把**客户端自带/marketplace 技能**也算成
    #   「装了却没登记」—— 实测 48 个里绝大多数是 workbuddy 官方 marketplace 装的
    #   （darwin-skill / bailian-* / 腾讯文档 / ima-skills …）与平台本地技能，
    #   它们**本就不该进 SkillHub 共享登记**（登记了反而污染共享路由，
    #   且中枢自己的口径是「误命中比没有更糟」）。
    #   ⇒ 拆成两类：
    #     · hub_owned_unregistered：**SkillHub 仓有实现**、装到了客户端、却没进登记
    #       —— 这才是真缺口（换机必丢、需要人写 trigger/forgot 才能登记）。
    #     · platform_provided：客户端自带/marketplace 技能，**不要求登记**（仅可见）。
    hub_owned_unregistered = sorted((installed & hub_impl) - recorded)
    platform_provided = sorted(installed - hub_impl)
    unregistered = sorted(installed - recorded)
    unimplemented = sorted(recorded - impl - mcp_records)
    return {
        "available": True,
        "recorded": len(recorded),
        "implemented": len(impl),
        "measured_installed": len(installed),
        "unregistered_installed": unregistered,
        # 2026-10-21 新增：真缺口 vs 平台自带（口径拆分，见上）
        "hub_owned_unregistered": hub_owned_unregistered,
        "platform_provided": platform_provided,
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
    # ⚠️ 2026-11-13：改为**逐平台各自**的目标线（不再用全局 1500 一把尺子）。
    over_target: list[dict] = []
    for plat, c in sorted(costs.items(), key=lambda kv: -kv[1]["per_session_tokens"]):
        target = target_for(plat, soft)
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
        "targets": {p: target_for(p, soft) for p in costs},
        "over_ratchet": over_ratchet,
        "over_target": over_target,
        "worst": _worst(costs),
    }


def _scan_query_log(
    state_dir: Path, cutoff: datetime, recent_cutoff: datetime
) -> tuple[Counter, Counter, Counter, dict[str, str]]:
    """扫查询账本 → (近窗活跃, 近月用过, 累计见过, 最后一次时间)。"""
    active: Counter = Counter()
    recently_used: Counter = Counter()
    seen: Counter = Counter()
    last: dict[str, str] = {}
    if not state_dir.is_dir():
        return active, recently_used, seen, last
    for f in sorted(state_dir.glob("query.log*.jsonl")):
        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            plat = str(d.get("platform") or "").strip()
            if not plat:
                continue
            seen[plat] += 1
            ts = str(d.get("ts") or "")
            if ts > last.get(plat, ""):
                last[plat] = ts
            try:
                when = datetime.fromisoformat(ts)
            except ValueError:
                continue
            if when.tzinfo is None:
                # naive 时间戳按本地时区解释（账本里两种形态都有：带时区/不带）
                when = when.replace(tzinfo=CST)
            if when >= cutoff:
                active[plat] += 1
            if when >= recent_cutoff:
                recently_used[plat] += 1
    return active, recently_used, seen, last


def platform_activity(root: Path, days: int = 7, active_window_days: int = 14) -> dict:
    """平台**检索活跃度**（近 N 天）——「通道死掉的早期信号」。

    数据源 = `.sync/state/query.log-*.jsonl`（MCP 的 hub_search/hub_bootstrap 与
    `tier-bootstrap` 都写；后者是 2026-11-02 才补上的，见 `commands/tier_bootstrap.py`）。

    口径纪律（三条，缺一个就变成噪音）：
    1. **只对注册平台告警**（平台清单 = `hub.config.yaml` 的唯一源）——
       账本里混着 `unknown` / `e2e-test` / `tracet` 等**非平台**噪声，不是平台就不该报。
    2. **只对「近 14 天确实在用」的平台告警**——很久没用的平台（走自己的通道）不算「死了」。
       ⚠️ 2026-11-02 用户确认「**workbuddy 最近没使用**」⇒ 窗口由 30 天收紧为 **14 天**
       （30 天时它会卡在边界上被误报；收紧后不再报——**「没在用」≠「通道死了」**）。
    3. 「近 7 天零检索」且它近 14 天用过 ⇒ 通道可能已死（真信号）。

    返回：{window_days, active{平台: 次数}, silent[{平台, 最后一次时间}], seen{平台: 累计}}
    """
    now = datetime.now(CST)
    cutoff = now - timedelta(days=days)
    recent_cutoff = now - timedelta(days=active_window_days)
    active, recently_used, seen, last = _scan_query_log(Path(root) / ".sync" / "state", cutoff, recent_cutoff)
    registered = set(platform_meta(root)["platforms"])
    active = Counter({k: v for k, v in active.items() if k in registered})
    silent = []
    for p in sorted(seen):
        if p not in registered:
            continue  # 非注册平台（unknown/e2e-test/…）⇒ 不是平台，不报
        if recently_used.get(p, 0) == 0:
            continue  # 近 30 天根本没用过 ⇒ 不是「死了」，是「没在用」
        if active.get(p, 0) == 0:
            silent.append({"platform": p, "last_seen": last.get(p, "")})
    return {
        "window_days": days,
        "active_window_days": active_window_days,
        "active": dict(sorted(active.items())),
        "seen": dict(sorted(seen.items())),
        "silent": silent,
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
    result = {
        "matched": sorted(matched),
        "declared_only": declared_only,
        "actual_only": actual_only,
        "cost_by_platform": rep["costs"],
        "fleet_tokens": rep["fleet"],  # 仅库存参考；**不设帽**
        "worst_platform": rep["worst"],
        "budgets": {**rep["soft"], "per_platform_ratchet": rep["caps"]},
        # ⚠️ 2026-11-13：逐平台目标线（渲染层读它，不用再算一遍）
        "targets": rep.get("targets") or {},
        "over_ratchet": rep["over_ratchet"],
        "over_target": rep["over_target"],
        "registry": registry_coverage(root),
        "activity": platform_activity(root),
    }
    # 降级路线图要读**已组装好的**结果（成本/棘轮/预算），故放最后算
    result["reduction_plan"] = reduction_plan(root, result)
    return result


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
    lines.append("| 平台 | 单会话 token | 该平台棘轮 | 该平台目标线 | 状态 |")
    lines.append("| --- | --- | --- | --- | --- |")
    caps = r["budgets"]["per_platform_ratchet"]
    targets = r.get("targets") or {}
    for plat, c in sorted(r["cost_by_platform"].items(), key=lambda kv: -kv[1]["per_session_tokens"]):
        n = c["per_session_tokens"]
        cap = caps.get(plat)
        target = targets.get(plat) or 0
        if cap is None:
            st = "（未登记棘轮）"
        elif n > cap:
            st = f"❌ **超棘轮 {n - cap}**"
        elif target and n > target:
            st = f"⚠️ 超目标 {n - target}（待降级，需批准）"
        else:
            st = "✅"
        lines.append(f"| {plat} | {n} | {cap if cap is not None else '—'} | {target or '—'} | {st} |")
    lines.append("")
    lines.append(
        f"- 最贵单平台：**{r['worst_platform']['platform']} {r['worst_platform']['tokens']} token/会话**"
        "（目标线**逐平台各设**，不再用统一常量）"
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
    _render_registry(reg, lines)
    if r["over_target"]:
        lines.append("")
        lines.append("### 降级候选（软目标，需用户批准后执行；**不拦提交**）")
        for d in r["over_target"]:
            top = "、".join(f"`{n}`({t})" for n, t in d["top_skills"])
            lines.append(
                f"- {d['platform']}：超目标 {d['over']} token；最贵的技能 {top or '（无）'}；"
                f"MCP server {d['mcp_servers']} 个"
            )
    act = r.get("activity") or {}
    lines.append("")
    lines.append(f"## 平台检索活跃度（近 {act.get('window_days', 7)} 天 · 通道死掉的早期信号）")
    lines.append("")
    if act.get("active"):
        lines.append("- 有检索记录：" + "、".join(f"{k}={v}" for k, v in act["active"].items()))
    else:
        lines.append("- 有检索记录：**无**")
    if act.get("silent"):
        lines.append(f"- ⚠️ **近 30 天用过、近 {act.get('window_days')} 天零检索**（通道可能已死；**只报不拦**）：")
        for s in act["silent"]:
            lines.append(f"  - {s['platform']}：最后一次 {s['last_seen'] or '未知'}")
    else:
        lines.append("- ✅ 近 30 天用过的平台近窗均有检索记录")

    _render_reduction_plan(r, lines)
    return "\n".join(lines)


def _render_registry(reg: dict, lines: list[str]) -> None:
    """SkillHub 登记覆盖率段（软指标：缺口要可见，不自动补登记）。"""
    if not reg.get("available"):
        return
    lines.append("")
    lines.append("### SkillHub 登记覆盖率（软指标：缺口要可见，不自动补登记）")
    lines.append("")
    lines.append(
        f"- 登记记录 **{reg['recorded']}** / 有 SKILL.md 的实现 **{reg['implemented']}**"
        f" / 实测装过的技能名 **{reg['measured_installed']}**"
    )
    lines.append(
        f"- ⚠️ **真缺口：SkillHub 有实现、装到了客户端、却从未登记**："
        f"{len(reg.get('hub_owned_unregistered') or [])} 个"
        "（换机必丢；补登记需人写 trigger/forgot，机器从名字编路由会误命中）"
    )
    if reg.get("hub_owned_unregistered"):
        lines.append(f"  - {', '.join(reg['hub_owned_unregistered'][:30])}")
    lines.append(
        f"- ℹ️ **客户端自带 / marketplace 技能（不要求登记）**："
        f"{len(reg.get('platform_provided') or [])} 个"
        "（2026-10-21 口径拆分：原口径把它们也算成「装了没登记」，指标永不收敛）"
    )
    lines.append(
        f"- ⚠️ **登记了却查无实现**（无 SKILL.md 且非 mcp）："
        f"{len(reg['recorded_but_unimplemented'])} 个 —— 要么补实现，要么删记录"
    )
    if reg["recorded_but_unimplemented"]:
        lines.append(f"  - {', '.join(reg['recorded_but_unimplemented'])}")


def _render_reduction_plan(r: dict, lines: list[str]) -> None:
    """降级路线图（目标 = 现状 × 比例；**目标非门禁**，硬帽 = 逐平台棘轮）。"""
    plan = r.get("reduction_plan") or []
    if not plan:
        return
    ratio = plan[0].get("ratio", 0.6)
    lines.append("")
    lines.append(f"## 降级路线图（目标 = 现状 ×{ratio}，**目标非门禁；硬帽 = 逐平台棘轮**）")
    lines.append("")
    lines.append("| 平台 | 现状 | 目标 | 还差 | 棘轮 | 降级候选（降为 conditional 可省） |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for p in plan:
        picks = "、".join(f"`{x['name']}`({x['tokens']})" for x in p["picks"]) or "—"
        if p.get("mcp_servers_to_drop"):
            picks += f"；另需减 MCP server ×{p['mcp_servers_to_drop']}"
        ratchet = p.get("ratchet")
        lines.append(
            f"| {p['platform']} | {p['current_tokens']} | {p['target_tokens']} | {p['need_tokens']} | "
            f"{ratchet if ratchet is not None else '—'} | {picks} |"
        )


def _monthly_state_dir(root: Path) -> Path:
    d = root / ".sync" / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _monthly_used_skills(root: Path) -> set[str]:
    """**已登记 / 有实现**的技能名（质量闸信号源：这些不许自动建议降级）。

    ⚠️ 2026-11-13 修正（**信号源三次都选错，此处是最终版**）：
       ① 首版从 `.sync/state/query.log*.jsonl` 抓技能名 ⇒ 恒为空。
          根因：检索留痕记的是**卡片路径**（`hit_paths`），不是技能名 ——
          中枢卡片与客户端技能是两套命名空间，本就不该混。
       ② 二版扫 `SkillHub/skills/*/SKILL.md` ⇒ 没命中（SkillHub 是**分层结构**
          `skills/<层>/<域>/<名>/SKILL.md`）。
       ③ 三版调 `registry_coverage()` ⇒ 拿到的是**计数（int）**不是集合 ⇒ 仍空。

    最终版：直接读 `router/router.yaml` 的登记名 + `skills/**/{skill.yaml,SKILL.md}`
    的实现名（与 `registry_coverage()` **同一套口径**，但不依赖它的返回值形态）。
    「登记过」= 用户认可并在用 ⇒ 降级它要先问人。
    """
    used: set[str] = set()
    try:
        from common.config import external_path

        sh = Path(str(external_path("skillhub", root) or ""))
        if sh.is_dir():
            router = sh / "router" / "router.yaml"
            if router.is_file():
                import yaml

                rows = (yaml.safe_load(router.read_text(encoding="utf-8")) or {}).get("skills") or []
                used |= {str(r["name"]) for r in rows if isinstance(r, dict) and r.get("name")}
            skills_dir = sh / "skills"
            if skills_dir.is_dir():
                used |= {q.parent.name for q in skills_dir.rglob("skill.yaml")}
                used |= {q.parent.name for q in skills_dir.rglob("SKILL.md")}
    except Exception:  # noqa: BLE001 - 量不到就当"全可降级"，不猜
        return set()
    return used


def monthly_review(root: Path) -> dict:
    """**月度体检**：逐平台核对常驻成本 → 比上月基线 → 检膨胀 → 给降级建议。

    口径（用户裁定 2026-11-13）：
    > 「每个月适当进行一次检查，在不改变它原本语义的情况下，尽量减少这个数值的大小，
    > 把它优化在一个合理的范围内，不让它过度膨胀……初衷就是想尽量减少每次对话中固定的 token 消耗。」

    硬约束：
    - **只降不升**：建议目标线 ≤ 上月基线（膨胀了标红，但目标线不因膨胀而抬高）。
    - **质量闸**：在用能力（已登记/有实现）标 🚫，不自动建议降级。
    - **只建议**：不改 `hub.config.yaml`、不降级能力（均需人工确认）。
    """
    now = datetime.now(CST)
    month = now.strftime("%Y-%m")
    prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    rep = cost_report(root)
    costs = rep["costs"]
    caps = ratchet(root)
    soft = budgets(root)

    prev_file = _monthly_state_dir(root) / f"capability_budget_review-{prev_month}.json"
    prev: dict = {}
    if prev_file.is_file():
        try:
            prev = json.loads(prev_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}
    prev_costs = (prev.get("platforms") or prev.get("costs") or {}) if prev else {}
    used = _monthly_used_skills(root)

    platforms: dict[str, dict] = {}
    for plat, c in sorted(costs.items()):
        cur = int(c.get("per_session_tokens") or 0)
        pv = prev_costs.get(plat) or {}
        prev_val = int(pv.get("current_tokens") or 0) or int(pv.get("per_session_tokens") or 0)
        delta = cur - prev_val if prev_val else 0
        pct = (delta / prev_val * 100) if prev_val else 0.0

        cap = caps.get(plat)
        target = target_for(plat, soft)

        candidates = []
        for name, tok in c.get("top_skills") or []:
            candidates.append(
                {
                    "skill": name,
                    "tokens": int(tok),
                    "in_use": name in used,
                    "actionable": name not in used,
                }
            )

        # 建议目标线：**以实测为基线**，只允许 ≤ 上月基线（只降不升）
        suggested = prev_val if (prev_val and delta > 0) else cur

        platforms[plat] = {
            "current_tokens": cur,
            "prev_tokens": prev_val,
            "delta": delta,
            "delta_pct": round(pct, 1),
            "ratchet": cap,
            "target": target,
            "suggested_target": min(suggested, cur),
            "over_ratchet": bool(cap is not None and cur > cap),
            "over_target": bool(target and cur > target),
            "bloat": bool(prev_val and delta > 0),
            "mcp_servers": int(c.get("mcp_servers") or 0),
            "candidates": candidates,
            "actionable_savings": sum(x["tokens"] for x in candidates if x["actionable"]),
        }

    return {
        "generated_at": now.isoformat(),
        "month": month,
        "prev_month": prev_month,
        "has_prev": bool(prev),
        "platforms": platforms,
        "summary": {
            "total_current": sum(p["current_tokens"] for p in platforms.values()),
            "total_prev": sum(p["prev_tokens"] for p in platforms.values()),
            "bloat_platforms": [k for k, v in platforms.items() if v["bloat"]],
            "over_ratchet_platforms": [k for k, v in platforms.items() if v["over_ratchet"]],
            "actionable_savings": sum(p["actionable_savings"] for p in platforms.values()),
            "in_use_protected": sum(
                x["tokens"] for p in platforms.values() for x in p["candidates"] if not x["actionable"]
            ),
        },
        "note": "只建议不擅自动手：写入 hub.config.yaml 需人工确认；降级能力需用户批准。",
    }


def render_monthly(rep: dict) -> str:
    """月度体检的人读报告。"""
    L: list[str] = []
    L.append(f"# 能力常驻成本月度体检 · {rep['month']}")
    L.append("")
    if not rep["has_prev"]:
        L.append(f"> ⚠️ 无上月基线（{rep['prev_month']}）⇒ 本次为**首期**，「膨胀」判定不可用，但目标线建议仍有效。")
        L.append("")
    L.append("| 平台 | 本月实测 | 上月实测 | 变化 | 棘轮 | 当前目标线 | 建议目标线 | 状态 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for plat, p in rep["platforms"].items():
        d = p["delta"]
        dtxt = f"{d:+d}" if p["prev_tokens"] else "—"
        if p["bloat"]:
            dtxt += f" ({p['delta_pct']:+.1f}%) 🔺"
        st = []
        if p["over_ratchet"]:
            st.append("❌超棘轮")
        if p["bloat"]:
            st.append("🔺膨胀")
        if not st:
            st.append("✅")
        L.append(
            f"| {plat} | {p['current_tokens']} | {p['prev_tokens'] or '—'} | {dtxt} | "
            f"{p['ratchet'] if p['ratchet'] is not None else '—'} | {p['target'] or '—'} | "
            f"**{p['suggested_target']}** | {' '.join(st)} |"
        )
    L.append("")
    s = rep["summary"]
    L.append("## 摘要")
    L.append("")
    L.append(f"- 全平台实测合计：{s['total_current']} token（上月 {s['total_prev'] or '—'}）")
    L.append(f"- 🔺 膨胀平台：{', '.join(s['bloat_platforms']) or '无'}")
    L.append(f"- ❌ 超棘轮平台：{', '.join(s['over_ratchet_platforms']) or '无'}")
    L.append(f"- **可降级空间**（闲置能力）：**{s['actionable_savings']} token**")
    L.append(f"- **在用能力（受保护，不建议降级）**：{s['in_use_protected']} token")
    L.append("")
    L.append("## 逐平台降级候选（🚫=在用，质量闸保护）")
    L.append("")
    for plat, p in rep["platforms"].items():
        if not p["candidates"]:
            continue
        items = "、".join(
            f"`{x['skill']}`({x['tokens']}){'🚫' if not x['actionable'] else ''}" for x in p["candidates"][:6]
        )
        L.append(f"- **{plat}**（{p['current_tokens']} token，建议目标 {p['suggested_target']}）：{items}")
    L.append("")
    L.append(f"> {rep['note']}")
    return "\n".join(L)


def _monthly_main(root: Path, *, write: bool, as_json: bool) -> int:
    """月度体检的 CLI 入口（并入本模块 ⇒ 不新增模块数，守住 C8④ 棘轮）。"""
    rep = monthly_review(root)
    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(render_monthly(rep))
    if write:
        p = _monthly_state_dir(root) / f"capability_budget_review-{rep['month']}.json"
        p.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n留痕已写：{p}")
    return 0  # 只建议 ⇒ 永远 exit 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="能力对账（声明态 vs 实测态）")
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--monthly",
        action="store_true",
        help="月度体检模式：比上月基线检膨胀 + 给降级建议（只建议不擅自动手）",
    )
    ap.add_argument("--write", action="store_true", help="月度体检：写留痕到 .sync/state/")
    args = ap.parse_args(argv)
    root = args.root or (_HUB_ENGINE.parent / "AgentMemoryHub")

    if args.monthly:
        return _monthly_main(root, write=args.write, as_json=args.json)

    r = reconcile(root)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(render(r))
    if r["declared_only"]:
        return 1
    if r["actual_only"] or r["over_ratchet"]:
        return 2
    # `activity.silent`（近 30 天用过、近 7 天零检索）**只报不拦**：
    # 中枢的查询账本只覆盖「走 MCP / tier-bootstrap」的通道 ⇒ 某个平台静默可能是
    # 「换了通道」而非「通道死了」。把它计入退出码 = 巡检天天带 warn ⇒ 训练出 --no-verify。
    return 0  # over_target 是**软目标**（积压项），只报不拦 —— 否则会训练出 --no-verify


if __name__ == "__main__":
    sys.exit(main())
