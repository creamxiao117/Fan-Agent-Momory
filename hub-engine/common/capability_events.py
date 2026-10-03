"""能力使用登记（append-only 台账）—— **(a) 技能使用登记** 的唯一写入/读取入口。

## 为什么需要它（2026-10-03 的实测结论）

「精简客户端技能、删掉没用过的」这个诉求**当时无法执行**，因为**客户端技能没有任何使用遥测**：

| 曾被误当证据的数据源 | 实际记的是什么 |
|---|---|
| `route_trace.ndjson` | **中枢卡片 slug**，不是客户端技能 |
| `reuse_daily.json` | 中枢卡片的复用日期 |
| `mcp_connect_ledger.jsonl` | MCP server 的**路径** |
| SkillHub `.skillhub/usage.jsonl` | 设计对了（`{outcome,name,ts}`），但**最后写入 2026-09-09**，只 9 条（测试产生） |

⇒ 结论：**必须先有登记，才谈得上"没使用过"**。本模块就是那个登记。

## 记什么（只记**可观测**的，不编造）

| event | 何时 | 能证明什么 |
|---|---|---|
| `injected` | 某平台会话开始、把该能力的说明注入上下文 | **常驻成本真实发生了**（每次会话都付） |
| `suggested` | 路由按任务上下文建议了它 | 有机会被用 |
| `installed` / `removed` | 部署/卸载（`task_capability` 已另有账本，此处只做统一视图） | 部署生命期 |
| `hit` | 检索/引用命中了它 | 被用到（最强证据） |

## 纪律

- **只追加**，不重写（与 `task_caps.jsonl`、`commit_ledger.jsonl` 同口径）。
- **绝不抛异常**：登记是旁路，不能因为它挂掉而让主流程失败（`_safe` 兜住一切）。
- **不记内容**，只记名字/平台/来源 —— 避免把用户数据写进台账。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEDGER_REL = ".sync/state/capability_events.jsonl"
CST = timezone(timedelta(hours=8))

VALID_EVENTS = ("injected", "suggested", "installed", "removed", "hit")


def ledger_path(root: Path) -> Path:
    return Path(root) / LEDGER_REL


def record(
    root: Path,
    event: str,
    name: str,
    *,
    platform: str = "",
    source: str = "",
    detail: str = "",
) -> bool:
    """追加一条事件。**永不抛异常**（旁路失败不得影响主流程）。

    Returns: 是否真写进去了（调用方可据此打日志，但不必处理）。
    """
    try:
        if event not in VALID_EVENTS or not name:
            return False
        p = ledger_path(root)
        p.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(CST).isoformat(timespec="seconds"),
            "event": event,
            "name": str(name),
            "platform": str(platform),
            "source": str(source),
        }
        if detail:
            row["detail"] = str(detail)[:200]
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:  # noqa: BLE001 - 登记是旁路，永不因它失败
        return False


def record_many(root: Path, event: str, names, *, platform: str = "", source: str = "") -> int:
    """批量登记（一次会话可能注入几十个能力，逐条 open 太慢）。返回写入条数。"""
    n = 0
    for name in names or []:
        n += 1 if record(root, event, str(name), platform=platform, source=source) else 0
    return n


def rows(root: Path) -> list[dict]:
    """读全部事件（坏行跳过，不抛）。"""
    p = ledger_path(root)
    if not p.is_file():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            if isinstance(d, dict) and d.get("name"):
                out.append(d)
        except ValueError:
            continue
    return out


def summarize(root: Path, *, days: int = 30) -> dict:
    """按能力汇总：{name: {counts, last_ts, platforms}}。`days=0` 表示不设时间窗。"""
    cutoff = None
    if days > 0:
        cutoff = (datetime.now(CST) - timedelta(days=days)).isoformat(timespec="seconds")
    agg: dict[str, dict] = {}
    for r in rows(root):
        if cutoff and str(r.get("ts") or "") < cutoff:
            continue
        name = str(r["name"])
        e = agg.setdefault(name, {"counts": {}, "last_ts": "", "platforms": [], "sources": []})
        ev = str(r.get("event") or "?")
        e["counts"][ev] = e["counts"].get(ev, 0) + 1
        e["last_ts"] = max(e["last_ts"], str(r.get("ts") or ""))
        plat = str(r.get("platform") or "")
        if plat and plat not in e["platforms"]:
            e["platforms"].append(plat)
        src = str(r.get("source") or "")
        if src and src not in e["sources"]:
            e["sources"].append(src)
    return agg


def never_recorded(root: Path, candidates, *, days: int = 30) -> list[str]:
    """候选里**一条登记都没有**的名字 —— "没使用过"的**唯一可证明形式**。

    注意限定语：这只能证明"本台账里没有它的痕迹"，**不等于"用户没用过"**。
    它的正当用途是"**在有登记的窗口期内**，连一次注入/建议/命中都没有" ⇒ 才是删除候选。
    """
    seen = set(summarize(root, days=days))
    return sorted(str(c) for c in candidates if str(c) not in seen)


def stats(root: Path) -> dict:
    rs = rows(root)
    return {
        "total": len(rs),
        "events": {e: sum(1 for r in rs if r.get("event") == e) for e in VALID_EVENTS},
        "first": rs[0]["ts"] if rs else None,
        "last": rs[-1]["ts"] if rs else None,
        "ledger": str(ledger_path(root)),
        "size": os.path.getsize(ledger_path(root)) if ledger_path(root).is_file() else 0,
    }
