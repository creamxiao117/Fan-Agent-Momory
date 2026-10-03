# @version V1.0 / 2026-10-02 / pi / 能力路由：按任务上下文建议能力（M3/Task 20）
"""capability_router —— 把「本任务该用什么能力」变成可计算的建议（架构重构 M3/Task 20）。

## 为什么不能靠模型临场想

`hub_bootstrap` 原本只返回**记忆命中**，"该用什么能力"全靠模型临场反应——
想到了就用，想不到就退化成裸跑。而能力的**触发词与禁用边界（负路由）早就写在
SkillHub 的 `router.yaml` 里**（`trigger` / `forgot` / `invoke` / `slot`），
只是从没人把它接到任务开头。

## 算法（刻意保持可解释）

1. 读 `router.yaml`（**唯一源**，`hub.config.yaml::external_paths.skillhub` 定位）；
   读不到就返回空（不猜、不硬编码技能清单）。
2. 对每条技能按 **trigger 子串命中数 − forgot 命中数 × 2** 打分（负路由权重更高：
   "误命中比没有更糟"）。
3. 按 `invoke` 分类：
   - `model`（可自动触发）→ 进 `suggested`
   - `user`（只由人触发）→ 进 `suggested` 但标注需人工
4. 与**实测态**（`capabilities.json` 里该平台的 skills）比对 → `missing`
   （= 账本里该装、磁盘上没有）。

## 硬约束

- **只建议，不自动安装**（改客户端配置前需用户批准，见 `global-rules`）。
- 建议必须带 `why`（命中了哪些触发词），否则用户无从复核。
"""

from __future__ import annotations

import sys
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

MAX_SUGGESTIONS = 5
FORGOT_PENALTY = 2  # 负路由权重 > 命中权重（误命中比没有更糟）


def skillhub_router(root: Path) -> dict:
    """读 SkillHub 的 `router.yaml`（唯一源）；不可达返回空 dict（不猜）。"""
    from common.config import HubConfig, external_path

    hub = external_path("skillhub", root) or (HubConfig.load(root).data.get("external_paths") or {}).get("skillhub")
    if not hub:
        return {}
    router = Path(str(hub)) / "router" / "router.yaml"
    if not router.is_file():
        return {}
    try:
        import yaml

        return yaml.safe_load(router.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 - 外部仓格式问题不该让预取崩掉
        return {}


def score_skill(skill: dict, context: str) -> tuple[int, list[str], list[str]]:
    """返回 (得分, 命中的触发词, 命中的禁用词)。纯函数，便于单测。"""
    text = (context or "").lower()
    hit = [t for t in (skill.get("trigger") or []) if str(t).lower() in text]
    bad = [t for t in (skill.get("forgot") or []) if str(t).lower() in text]
    return len(hit) - FORGOT_PENALTY * len(bad), hit, bad


def suggest(root: Path, context: str, platform: str = "pi", limit: int = MAX_SUGGESTIONS) -> dict:
    """按任务上下文给出能力建议 + 与实测态的差集。"""
    router = skillhub_router(root)
    skills = router.get("skills") or []

    scored = []
    for s in skills:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        sc, hit, bad = score_skill(s, context)
        if sc <= 0:
            continue
        # M2/Task 16：把 `deploy_scope` 带进建议 —— 否则调用方不知道
        # 「这条是常驻（已在客户端）还是可以任务级临时装」
        scope = str(s.get("deploy_scope") or "always").strip() or "always"
        scored.append(
            {
                "name": s.get("name"),
                "slot": s.get("slot"),
                "invoke": s.get("invoke"),
                "kind": s.get("kind") or "skill",
                "deploy_scope": scope,
                "task_installable": scope in {"task", "on-demand"},
                "score": sc,
                "hit": hit,
                "forgot": bad,
                "why": f"命中触发词 {hit}" + (f"；但同时命中禁用词 {bad}（已降权）" if bad else ""),
            }
        )
    scored.sort(key=lambda d: (-d["score"], str(d["name"])))
    suggested = scored[:limit]

    # 与实测态比对：账本建议的、磁盘上没有的 → missing
    installed: list[str] = []
    try:
        import json

        cap = root / "system" / "capabilities.json"
        if cap.is_file():
            data = json.loads(cap.read_text(encoding="utf-8"))
            info = (data.get("skills") or {}).get(platform) or {}
            installed = list(info.get("skills") or [])
    except (OSError, ValueError):
        installed = []

    # (a) 使用登记：把"曾按任务建议过它"记下来 —— 这是"有没有被用过"的**唯一可查口径**。
    # 旁路调用，失败不影响建议本身（capability_events.record 内部兜住异常）。
    try:
        from common.capability_events import record_many

        record_many(root, "suggested", [s["name"] for s in suggested], platform=platform, source="capability_router")
    except Exception:  # noqa: BLE001
        pass

    missing = [s for s in suggested if s["name"] not in installed]
    return {
        "platform": platform,
        "installed": sorted(installed),
        "suggested": suggested,
        "missing": missing,
        "note": "只建议不自动安装（改客户端配置前需用户批准）；why 字段给出命中依据供复核",
    }
