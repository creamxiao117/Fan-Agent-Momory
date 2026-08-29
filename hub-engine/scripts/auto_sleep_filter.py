r"""auto_sleep_filter.py — 过滤 sleep 候选中的假信号（lint 自检串 / 通用关键词 slug）。

消费 hub_sleep_consolidate.py 产出的 proposal.json，将候选按确定性信号分类：
- NOISE（直接自动 ignore，写 IGNORED.md）：
    ① 查询含 lint / hub-engine 内部关键词串（孤儿 / ghost / stale / INDEX 登记 / conflicts /
       sleep 消化 / gate / pytest / ruff 等）
    ② 同查询 deterministic 通道已命中 ≥ 30 张卡（说明是通用关键词串，不是真实知识缺口）
    ③ 查询是 slug 格式（纯英文连字符串，无中文，≥ 3 个词）
- REAL（保留给 auto_process_sleep 或人工）：
    有明确语义、候选数在合理范围（< 30 命中）

用法：
  python scripts/auto_sleep_filter.py --root ..\AgentMemoryHub
  python scripts/auto_sleep_filter.py --root ..\AgentMemoryHub --since-days 3
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

_LOCAL_TZ = timezone(timedelta(hours=+8))

# 内部工具关键词：命中任何一个即判为 lint/自检假信号
_INTERNAL_NOISE_KEYWORDS = {
    "孤儿", "orphan", "ghost", "stale", "INDEX 登记", "index 登记",
    "conflicts", "sleep 消化", "sleep消化", "gate", "pytest", "ruff",
    "lint", "orphans", "ghosts", "stales",
}


def _is_slug_query(query: str) -> bool:
    """判断是否是英文连字符 slug 查询（≥3 个连字符词，无中文）。"""
    q = query.strip()
    if re.search(r"[\u4e00-\u9fff]", q):
        return False  # 含中文
    parts = [p for p in re.split(r"[\s\-_]+", q) if p]
    return len(parts) >= 3 and all(p.isascii() and p.isalpha() for p in parts)


def _has_internal_noise(query: str) -> bool:
    """检查是否命中内部工具关键词。"""
    q_lower = query.lower()
    return any(kw.lower() in q_lower for kw in _INTERNAL_NOISE_KEYWORDS)


def _classify_candidate(c: dict) -> str:
    """返回 'NOISE' 或 'REAL'。"""
    q = c.get("query", "")
    current_hits = c.get("current_hits", 0)
    channels = c.get("channels", [])

    # 规则 1：内部工具关键词
    if _has_internal_noise(q):
        return "NOISE: internal-noise-keywords"

    # 规则 2：slug 格式
    if _is_slug_query(q):
        return "NOISE: slug-query"

    # 规则 3：deterministic 通道命中 ≥ 30 张（通用关键词）
    if "deterministic" in channels and current_hits >= 30:
        return "NOISE: too-many-deterministic-hits"

    return "REAL"


def find_recent_proposals(root: Path, since_days: int = 3) -> list[Path]:
    """找到最近 N 天内的所有 proposal.json。"""
    sleep_dir = root / ".sync" / "state" / "sleep"
    if not sleep_dir.is_dir():
        return []
    cutoff = datetime.now(_LOCAL_TZ) - timedelta(days=since_days)
    results = []
    for sub in sleep_dir.iterdir():
        if not sub.is_dir():
            continue
        ts_match = re.match(r"(\d{8})-(\d{6})", sub.name)
        if not ts_match:
            continue
        try:
            ts = datetime.strptime(sub.name, "%Y%m%d-%H%M%S").replace(tzinfo=_LOCAL_TZ)
        except ValueError:
            continue
        if ts < cutoff:
            continue
        proposal = sub / "proposal.json"
        if proposal.is_file():
            results.append(proposal)
    return sorted(results, reverse=True)


def filter_proposal(proposal_path: Path) -> dict:
    """过滤单个 proposal.json。返回 {noise, real, total} 统计。"""
    data = json.loads(proposal_path.read_text(encoding="utf-8"))
    cands = data.get("candidates", [])
    noise = []
    real = []
    for c in cands:
        verdict = _classify_candidate(c)
        if verdict.startswith("NOISE"):
            noise.append({**c, "_verdict": verdict})
        else:
            real.append(c)

    # 回写过滤后的候选到同一个 proposal.json
    data["candidates"] = real
    data["meta"]["filter_applied"] = {
        "date": datetime.now(_LOCAL_TZ).isoformat(),
        "noise_filtered": len(noise),
        "noise_reasons": [c["_verdict"] for c in noise],
    }
    proposal_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 写 IGNORED.md 记录被过滤的
    if noise:
        parent = proposal_path.parent
        ignored = parent / "IGNORED.md"
        lines = [
            "# auto_sleep_filter 自动忽略清单",
            f"ignored_at: {datetime.now(_LOCAL_TZ).isoformat()}",
            f"reason: auto_filtered {len(noise)} noise candidates",
            "",
        ]
        for c in noise:
            lines.append(f"- {c['query']} → {c['_verdict']}")
        ignored.write_text("\n".join(lines), encoding="utf-8")

    return {"noise": len(noise), "real": len(real), "total": len(cands)}


def main() -> int:
    ap = argparse.ArgumentParser(prog="auto-sleep-filter", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument("--since-days", type=int, default=3, help="最近 N 天")
    ap.add_argument("--date", default=None, help="只处理某一天的 sleep 目录")
    args = ap.parse_args()

    root = Path(args.root).resolve()

    if args.date:
        # 只处理指定日期（精准模式）
        sleep_dir = root / ".sync" / "state" / "sleep"
        targets = list(sleep_dir.glob(f"{args.date}-*/proposal.json"))
    else:
        targets = find_recent_proposals(root, args.since_days)

    if not targets:
        print("[auto_sleep_filter] 无待处理的 proposal")
        return 0

    total_noise = 0
    total_real = 0
    for p in targets:
        result = filter_proposal(p)
        total_noise += result["noise"]
        total_real += result["real"]
        print(f"[auto_sleep_filter] {p.parent.name}: 过滤 {result['noise']} noise, 保留 {result['real']} real")

    print(f"\n[auto_sleep_filter] 总计: {total_noise} noise 已自动忽略, {total_real} real 保留")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
