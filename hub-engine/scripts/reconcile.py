# @version V1.0 / 2026-09-08 / Hermes / 双平台 commit 重建脚本（Phase 2.2）
"""
reconcile.py —— 检测并重建丢失的 commit。

V1.0 (2026-09-08): T10 Phase 2.2 —— 双平台协调 reconcile。

功能：
1. 读 .sync/state/commit_ledger.jsonl
2. 对每条 ledger 记录，检查 parent_sha 是不是当前 HEAD 的 ancestor
3. 如果不是（即父 SHA 不在 history 里），说明被人 reset --hard 丢掉了
4. 用 git replace --graft 把孤儿 commit 重新挂回主链
5. 生成报告

用法：
    python -m scripts.reconcile --root AgentMemoryHub [--dry-run] [--report path]

退出码：
    0 = 一切正常（无孤儿 / 全部已修复）
    1 = 发现孤儿 commit（已尝试 repair）
    2 = 运行错误
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    return r.stdout.strip()


def _is_ancestor(root: Path, ancestor: str, descendant: str = "HEAD") -> bool:
    """ancestor 是不是 descendant 的祖先？"""
    if ancestor.startswith("TESTSHA") or len(ancestor) != 40:
        return False
    r = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def _is_valid_sha(root: Path, sha: str) -> bool:
    if len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha):
        return False
    r = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-t", sha],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def reconcile(root: Path, dry_run: bool = False) -> dict:
    """主函数：返回 report dict。"""
    ledger = root / ".sync" / "state" / "commit_ledger.jsonl"
    if not ledger.exists():
        return {"status": "no_ledger", "orphans": [], "repaired": []}

    records = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    orphans = []
    repaired = []

    for rec in records:
        parent_sha = rec.get("parent_sha", "")
        new_sha = rec.get("new_sha", "")

        if not _is_valid_sha(root, new_sha):
            # 新 commit SHA 已被 GC 丢掉
            if parent_sha and _is_valid_sha(root, parent_sha):
                orphans.append({
                    "ts": rec["ts"],
                    "who": rec["who"],
                    "intent": rec["intent"],
                    "lost_sha": new_sha,
                    "parent_sha": parent_sha,
                })
            continue

        if not _is_ancestor(root, parent_sha, new_sha):
            # parent 不是 new 的祖先 → 说明中间有人 reset
            orphans.append({
                "ts": rec["ts"],
                "who": rec["who"],
                "intent": rec["intent"],
                "new_sha": new_sha,
                "parent_sha": parent_sha,
                "note": "parent not ancestor of new",
            })

    # 尝试 repair：把孤儿 SHA 用 git replace --graft 挂回主链
    if not dry_run and orphans:
        for orph in orphans:
            sha = orph.get("lost_sha") or orph.get("new_sha")
            if not sha or not _is_valid_sha(root, sha):
                continue
            # 用 replace --graft 重建：把 sha 的 parent 指向当前 HEAD
            r = subprocess.run(
                ["git", "-C", str(root), "replace", "--graft", sha, "HEAD"],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                repaired.append(sha)

    return {
        "status": "ok" if not orphans else "orphans_found",
        "ledger_entries": len(records),
        "orphans": orphans,
        "repaired": repaired,
        "dry_run": dry_run,
    }


def main():
    ap = argparse.ArgumentParser(description="reconcile commit_ledger orphans")
    ap.add_argument("--root", required=True, help="AgentMemoryHub root")
    ap.add_argument("--dry-run", action="store_true", help="仅报告不修复")
    ap.add_argument("--report", help="报告输出路径")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print(f"ERROR: {root} 不是 git repo", file=sys.stderr)
        return 2

    report = reconcile(root, dry_run=args.dry_run)

    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    print(f"status: {report['status']}")
    print(f"ledger entries: {report['ledger_entries']}")
    print(f"orphans: {len(report['orphans'])}")
    print(f"repaired: {len(report['repaired'])}")

    return 0 if not report["orphans"] else 1


if __name__ == "__main__":
    sys.exit(main())