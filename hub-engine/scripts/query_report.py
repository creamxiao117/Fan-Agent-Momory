"""MCP 查询周报：读取 .sync/state/query.log.jsonl 统计各平台调用"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

LOG = Path(".sync") / "state" / "query.log.jsonl"


def load_records(root: Path) -> list[dict]:
    log = Path(root) / LOG
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def report(root: Path) -> dict:
    by_platform: dict[str, Counter] = defaultdict(Counter)
    recs = load_records(root)
    for r in recs:
        by_platform[r.get("platform", "unknown")][r.get("action", "?")] += 1
    return {
        "total": len(recs),
        "platforms": {p: dict(c) for p, c in sorted(by_platform.items())},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="query-report")
    ap.add_argument("--root", required=True, help="中枢根目录")
    args = ap.parse_args(argv)
    print(json.dumps(report(Path(args.root)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
