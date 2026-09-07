# @version V1.0 / 2026-09-07 / Hermes / ingest 后置 hook：自动同步 INDEX.md
"""post_ingest_hook：ingest 完成后扫描 memory_diff.jsonl 找本轮新增/移动的卡，
按 type → INDEX.md 对应小节末尾追加一行。

设计要点（实测背景）：
- ingest 已写 `.sync/state/memory_diff.jsonl`，每条记录形如：
    {"op": "add", "name": "x.md", "type": "exp", "before": null,
     "after": "experience/x.md", "ts": 1234567890}
- hook 从 jsonl 倒序读，跳过 ts < since_ts 的 entry，只处理本轮
- 首跑：since_ts 不传 → 处理整个 diff 文件（兼容幂等）
- 失败不阻塞 ingest：独立进程 + 独立 try/except
- INDEX.md 用 section 标题锚定（与 INDEX.md 现行结构完全一致）
"""
from __future__ import annotations

# bootstrap：让此脚本可独立从任何 cwd 调用（不依赖外部 sys.path 设置）
import sys
from pathlib import Path as _P
_THIS = _P(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))  # hub-engine/

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

# 镜像 sync.py / INDEX.md 的 section 标题表
SECTION_TITLES = {
    "rules":       "## 规则（rules/）",
    "methodology": "## 方法论（methodology/）",
    "blueprints":  "## 技术路径蓝图（blueprints/）",
    "longterm":    "## 长期记忆（longterm/）",
    "projects":    "## 项目记忆（projects/）",
    "exp":         "## 经验（experience/）",    # T1 (2026-09-07): 非权威区 type 也登记 INDEX
    "note":        "## 经验（experience/）",    # 注释类合并入经验区
    "retro":       "## 沉淀通道",                # retro 是 append-only 留痕，不入主索引
}


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    cmd = ["git", "-C", str(repo), *args]
    r = subprocess.run(
        cmd, check=True, capture_output=True, text=True, encoding="utf-8", env=env
    )
    return r.stdout or ""


def read_diff_since(root: Path, since_ts: float | None, max_records: int = 200) -> list[dict]:
    """读 memory_diff.jsonl，过滤本轮新增（before is None）的 add/move 记录。

    安全保护：不传 since_ts 时只取最近 max_records 条，防止历史污染 INDEX。
    """
    diff = root / ".sync" / "state" / "memory_diff.jsonl"
    if not diff.exists():
        return []
    lines = diff.read_text(encoding="utf-8", errors="ignore").splitlines()
    if since_ts is None and len(lines) > max_records:
        # 仅扫描尾部，避免历史 diff 大量污染
        lines = lines[-max_records:]
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since_ts is not None and rec.get("ts", 0) < since_ts:
            continue
        if rec.get("op") not in ("add", "move"):
            continue  # delete / 等其他操作不登记 INDEX
        out.append(rec)
    return out


def extract_summary(card_path: Path) -> str:
    """从卡正文提取一句话描述（frontmatter 后首段非标题文本，去掉 markdown 标记）。"""
    if not card_path.exists():
        return ""
    text = card_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    seen_fm_end = False
    fm_end_count = 0
    for line in lines:
        s = line.strip()
        if fm_end_count < 2:
            if s == "---":
                fm_end_count += 1
            continue
        if not s:
            continue
        if s.startswith("# "):
            return s[2:].strip()[:80]
        if s.startswith("## "):
            continue
        return re.sub(r"[*_`#\[\]]", "", s)[:80]
    return ""


def append_to_index(index_path: Path, section_title: str, slug: str, summary: str) -> bool:
    """在指定 section 末尾（下一个 ## 之前）追加一行；幂等：已存在则跳过。"""
    text = index_path.read_text(encoding="utf-8")
    if f"- {slug}    " in text or f"- {slug}  " in text:
        return False
    lines = text.splitlines(keepends=True)
    in_section = False
    section_end_idx = len(lines)
    for i, line in enumerate(lines):
        if line.startswith(section_title):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            section_end_idx = i
            break
    if not in_section:
        return False  # section 不存在，不擅自创建
    summary_clean = summary.replace("\n", " ").strip()
    new_line = f"- {slug}    {summary_clean}\n"
    lines.insert(section_end_idx, new_line)
    index_path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(prog="post_ingest_hook")
    ap.add_argument("--root", required=True)
    ap.add_argument(
        "--since-ts",
        type=float,
        default=None,
        help="只处理 ts >= since_ts 的 diff；默认 = None（处理整个文件）",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印候选，不实际改 INDEX.md / commit",
    )
    ap.add_argument(
        "--names",
        default="",
        help="本轮 ingest 涉及的卡名清单（逗号分隔）；优先于 diff 扫描，避免历史污染",
    )
    args = ap.parse_args()
    root = Path(args.root)
    index_path = root / "INDEX.md"
    if not index_path.exists():
        print(f"INDEX.md 不存在: {index_path}", file=sys.stderr)
        return 2
    # 优先使用 ingest 传入的精确清单（防历史污染 INDEX）
    target_names = [n.strip() for n in args.names.split(",") if n.strip()]
    if target_names:
        # 直接从权威区目录读这 N 张卡（不走 diff 扫描）
        diffs = []
        for name in target_names:
            # 找文件位置：先查权威区，再查 experience，再查 .sync
            found = None
            for sub in ["rules", "methodology", "blueprints", "longterm", "projects",
                         "experience", "notes"]:
                p2 = root / sub / name
                if p2.exists():
                    found = p2
                    break
            if found is None:
                continue
            # 解析 type：从 frontmatter 读取
            try:
                from common.frontmatter import read_card
                card = read_card(found)
                diffs.append({
                    "name": name,
                    "type": card.type,
                    "after": str(found.relative_to(root)).replace(os.sep, "/"),
                })
            except Exception:
                continue
    else:
        diffs = read_diff_since(root, args.since_ts)
    if not diffs:
        print("post_ingest_hook: 本轮无新增卡", file=sys.stderr)
        return 0
    planned: list[tuple[str, str, str]] = []
    for rec in diffs:
        card_type = rec.get("type", "")
        after = rec.get("after", "")
        if not after or not card_type:
            continue
        if after.startswith(".sync/"):  # 跳过 pending/conflicts
            continue
        section_title = SECTION_TITLES.get(card_type)
        if not section_title:
            continue
        slug = Path(rec["name"]).stem
        card_path = root / after
        summary = extract_summary(card_path)
        planned.append((section_title, slug, summary))
    if args.dry_run:
        print(f"post_ingest_hook dry-run: 计划登记 {len(planned)} 张")
        for st, slug, sm in planned:
            print(f"  → {st} | {slug} | {sm[:60]}")
        return 0
    added = []
    for section_title, slug, summary in planned:
        if append_to_index(index_path, section_title, slug, summary):
            added.append(slug)
    if not added:
        print("post_ingest_hook: 无 INDEX 变更（可能已存在或无匹配 section）", file=sys.stderr)
        return 0
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "AgentMemoryHub"
    env["GIT_AUTHOR_EMAIL"] = "hub@local"
    env["GIT_COMMITTER_NAME"] = "AgentMemoryHub"
    env["GIT_COMMITTER_EMAIL"] = "hub@local"
    try:
        git(root, "add", "INDEX.md", env=env)
        msg = f"docs(INDEX): post_ingest_hook 自动登记 {len(added)} 张新卡"
        git(root, "commit", "-m", msg, env=env)
    except RuntimeError as e:
        print(f"commit 失败: {e}", file=sys.stderr)
        return 3
    print(f"post_ingest_hook: 已登记 {len(added)} 张 → {added}")
    return 0


if __name__ == "__main__":
    sys.exit(main())