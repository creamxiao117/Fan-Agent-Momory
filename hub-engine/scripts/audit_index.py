# @version V1.0 / 2026-09-07 / Hermes / INDEX 自动审核：orphan/ghost/格式一致性检查
"""L2 巡检：核对 INDEX.md 与权威区文件的一致性 + slug 格式 + 描述长度。

产出：
- 控制台报告（issue 列表）
- retro/lint-report-YYYYMMDD.md（持久化报告）
- exit code：0 = 健康、1 = 有问题、2 = 工具错

设计原则：
- 纯只读，不修改任何源文件（不删除 orphan/ghost 文件、不改 INDEX.md）
- 报告给人和自动告警系统各一份
"""

import sys
from pathlib import Path as _P

_THIS = _P(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))  # hub-engine/

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

# INDEX 登记行格式：- slug  描述
# slug 字符集含 CJK（2026-09-11 用户裁定）：中文 slug 卡（如 projects/T21-5platform-后续优化-待办.md）
# 此前无法被解析 → 恒被误判为「INDEX 未登记」。slug 类仍不含空格，故加 CJK 不会引入贪婪越界。
_CJK = "\u4e00-\u9fff"
INDEX_ENTRY_RE = re.compile(
    rf"^- ([a-zA-Z0-9{_CJK}][a-zA-Z0-9_\-\.{_CJK}]{{0,80}})(?:\s{{2,}}|\s+)(.+)$"
)
NESTED_ENTRY_RE = re.compile(
    rf"^\|- ([a-zA-Z0-9{_CJK}][a-zA-Z0-9_\-\.{_CJK}]{{0,80}})(?:\s{{2,}}|\s+)(.+)$"
)

# 描述长度上限：按分区差异化（2026-09-11 用户裁定）
# 蓝图描述承载「技术路径 A/B/C + 判级 + 状态」，250 字符必然截断决策信息 → 单独放宽到 800；
# 其他分区维持 250（防摘要退化为正文）。
DESC_LIMIT_DEFAULT = 250
DESC_LIMIT_BLUEPRINTS = 800


def _desc_limit(section: str) -> int:
    """分区标题 → 描述长度上限（按标题内目录名判定，避免中文标题改写后失效）。"""
    return DESC_LIMIT_BLUEPRINTS if "blueprints" in section else DESC_LIMIT_DEFAULT


# 权威区（与 engine.config.yaml authority_dirs 对齐，2026-09-02 调整为 5 目录）
# 注意：experience/notes/retro 是非权威区，仅参与 INDEX 登记，不参与权威文件扫描
AUTHORITY_DIRS = (
    "rules",
    "methodology",
    "longterm",
    "projects",
    "blueprints",
)

# _ghost_index 检查时额外纳入非权威区（experience/notes/retro）避免误报
_ALL_SCAN_DIRS = AUTHORITY_DIRS + ("experience", "notes", "retro")

# slug 格式：允许小写/大写字母、数字、连字符、下划线、点号；2~80 字符
SLUG_RE = re.compile(rf"^[a-zA-Z0-9{_CJK}][a-zA-Z0-9_\-\.{_CJK}]{{1,79}}$")


def _parse_index(index_path: Path) -> tuple[dict[str, list[str]], list[dict]]:
    """解析 INDEX.md → (slug → 描述列表, 行级 entries)。

    返回 entries 用于做"重复 slug"检查（同 slug 多次登记 = 重复）。
    """
    text = index_path.read_text(encoding="utf-8", errors="ignore")
    by_slug: dict[str, list[str]] = {}
    entries: list[dict] = []
    section = ""  # 当前 `## ` 分区标题，供描述长度按分区差异化
    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.startswith("## "):
            section = line.strip()
            continue
        m = INDEX_ENTRY_RE.match(line)
        if not m:
            # 也接受 |- 嵌套列表项（INDEX.md 实际有大量嵌套登记）
            m = NESTED_ENTRY_RE.match(line)
        if not m:
            continue
        slug, desc = m.group(1), m.group(2).strip()
        by_slug.setdefault(slug, []).append(desc)
        entries.append(
            {"slug": slug, "desc": desc, "line_no": line_no, "section": section}
        )
    return by_slug, entries


def _authority_files(
    root: Path, dirs: tuple[str, ...] | None = None
) -> dict[str, Path]:
    """权威区文件 → 相对路径。dirs=None 时用 AUTHORITY_DIRS。"""
    out: dict[str, Path] = {}
    scan_dirs = dirs if dirs is not None else AUTHORITY_DIRS
    for d in scan_dirs:
        sub = root / d
        if not sub.exists():
            continue
        for p in sub.glob("*.md"):
            if p.name in ("log.md",) or p.name.startswith("lint-report-"):
                continue
            slug = p.stem
            out[slug] = p.relative_to(root)
    return out


def audit(root: Path) -> dict:
    """主审计：返回 issues 列表 + 统计。"""
    issues: list[dict] = []
    stats: dict[str, int] = {"total_index_entries": 0, "total_files": 0}

    index_path = root / "INDEX.md"
    if not index_path.exists():
        issues.append(
            {"type": "missing_index", "msg": f"INDEX.md 不存在: {index_path}"}
        )
        return {"issues": issues, "stats": stats}

    by_slug, entries = _parse_index(index_path)
    stats["total_index_entries"] = len(entries)

    files_by_slug = _authority_files(root)
    stats["total_files"] = len(files_by_slug)

    # 1) ghost：INDEX 登记了但任何目录（含 experience/notes/retro）都找不到文件
    all_files_by_slug = _authority_files(root, dirs=_ALL_SCAN_DIRS)
    for slug in by_slug:
        if slug not in all_files_by_slug:
            issues.append(
                {
                    "type": "ghost_index",
                    "msg": f"INDEX 登记了 '{slug}' 但所有目录都找不到对应文件",
                    "slug": slug,
                    "severity": "high",
                }
            )

    # 2) orphan：权威区有文件但 INDEX 未登记
    for slug, rel in files_by_slug.items():
        if slug not in by_slug:
            issues.append(
                {
                    "type": "orphan_file",
                    "msg": f"权威区有 '{rel}' 但 INDEX 未登记",
                    "slug": slug,
                    "path": str(rel),
                    "severity": "high",
                }
            )

    # 3) 重复 slug（多次登记）
    for slug, descs in by_slug.items():
        if len(descs) > 1:
            issues.append(
                {
                    "type": "duplicate_slug",
                    "msg": f"INDEX 中 '{slug}' 登记了 {len(descs)} 次",
                    "slug": slug,
                    "count": len(descs),
                    "severity": "medium",
                }
            )

    # 4) slug 格式校验
    for entry in entries:
        if not SLUG_RE.match(entry["slug"]):
            issues.append(
                {
                    "type": "invalid_slug",
                    "msg": f"行 {entry['line_no']}: slug '{entry['slug']}' 不符合 slug 格式（小写字母/数字/连字符）",
                    "slug": entry["slug"],
                    "line_no": entry["line_no"],
                    "severity": "low",
                }
            )

    # 5) 描述长度校验（上限按分区差异化：blueprints 800 / 其他 250）
    for entry in entries:
        desc = entry["desc"]
        limit = _desc_limit(entry.get("section", ""))
        if len(desc) < 10:
            issues.append(
                {
                    "type": "short_desc",
                    "msg": f"行 {entry['line_no']}: slug '{entry['slug']}' 描述过短（{len(desc)} 字符 < 10）",
                    "slug": entry["slug"],
                    "desc_len": len(desc),
                    "line_no": entry["line_no"],
                    "severity": "low",
                }
            )
        elif len(desc) > limit:
            issues.append(
                {
                    "type": "long_desc",
                    "msg": f"行 {entry['line_no']}: slug '{entry['slug']}' 描述过长（{len(desc)} 字符 > {limit}）",
                    "slug": entry["slug"],
                    "desc_len": len(desc),
                    "line_no": entry["line_no"],
                    "severity": "low",
                }
            )

    return {"issues": issues, "stats": stats}


def render_report(audit_result: dict, root: Path) -> str:
    """生成 Markdown 报告。"""
    issues = audit_result["issues"]
    stats = audit_result["stats"]
    lines = [
        f"# L2 巡检报告 - {datetime.now(timezone.utc).date().isoformat()}",
        "",
        f"- INDEX 条目总数: {stats['total_index_entries']}",
        f"- 权威区文件总数: {stats['total_files']}",
        f"- 发现问题数: {len(issues)}",
        "",
    ]
    if not issues:
        lines.append("✅ **健康** - 未发现问题。")
    else:
        # 按类型分组
        by_type: dict[str, list] = {}
        for it in issues:
            by_type.setdefault(it["type"], []).append(it)
        for typ, items in sorted(by_type.items()):
            sev = items[0].get("severity", "?")
            lines.append(f"## {typ} ({len(items)} 项, severity={sev})")
            for it in items[:20]:  # 单类型最多列20
                lines.append(f"- {it['msg']}")
            if len(items) > 20:
                lines.append(f"- ...（还有 {len(items) - 20} 项未列）")
            lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(prog="audit-index")
    ap.add_argument("--root", required=True, help="中枢根目录")
    ap.add_argument(
        "--report",
        action="store_true",
        help="写入 retro/lint-report-YYYYMMDD.md",
    )
    ap.add_argument(
        "--no-fail",
        action="store_true",
        help="发现问题也返回 0（用于 cron 只想写报告不想中断）",
    )
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"中枢根不存在: {root}", file=sys.stderr)
        return 2

    result = audit(root)
    issues = result["issues"]
    stats = result["stats"]

    # 控制台报告
    print(
        f"[L2] INDEX 条目 {stats['total_index_entries']} / 权威区文件 {stats['total_files']}"
    )
    if not issues:
        print("[L2] ✅ 健康")
    else:
        print(f"[L2] ⚠️ {len(issues)} 项问题：")
        # 按 severity 高→低
        sev_order = {"high": 0, "medium": 1, "low": 2, "?": 3}
        issues_sorted = sorted(
            issues, key=lambda x: sev_order.get(x.get("severity", "?"), 9)
        )
        for it in issues_sorted[:30]:  # 控制台最多列 30
            print(f"  [{it.get('severity', '?')}] {it['msg']}")
        if len(issues_sorted) > 30:
            print(f"  ...（还有 {len(issues_sorted) - 30} 项未列）")

    # 写报告
    if args.report:
        report_dir = root / "retro"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = (
            report_dir
            / f"lint-report-{datetime.now(timezone.utc).date().isoformat()}.md"
        )
        report_path.write_text(render_report(result, root), encoding="utf-8")
        print(f"[L2] 报告已写: {report_path}")

    if not issues:
        return 0
    return 0 if args.no_fail else 1


if __name__ == "__main__":
    sys.exit(main())
