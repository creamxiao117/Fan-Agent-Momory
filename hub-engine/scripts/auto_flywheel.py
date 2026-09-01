"""自动飞轮触发：扫描中枢草稿 → ingest → build-vectors 一条龙。

用法：
  python auto_flywheel.py --root <中枢根> [--dry-run] [--platform trae]

逻辑：
  1. 扫描 <root>/.sync/drafts/ 下所有 .md 草稿（递归，含平台子目录）
  2. 无草稿 → 输出「无待处理草稿」退出
  3. 有草稿 → 按平台分组，逐平台调 ingest，再调 build-vectors
  4. 结果追加写入 .sync/state/flywheel-log.json
"""

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 确保可 import hub-engine 同级模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.frontmatter import today_iso


def write_text_utf8(path: Path, text: str) -> None:
    """UTF-8 无 BOM 写入；mkdir parents 保证目标目录存在。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def scan_drafts(root: Path) -> dict[str, list[Path]]:
    """扫描 .sync/drafts/<platform>_draft/ 根目录下的 .md 草稿，按平台分组。

    与 sync.ingest 的扫描口径**严格一致**（只扫根目录 `*.md`，不递归）：
    - candidates/ 子目录 = 候选草稿区（status: candidate），由人工审核后移入根
      目录再提升，**不属于自动飞轮的输入**。
    - retro/ 子目录 = 复盘归档区，ingest 提升时自动追加，**不作为提升源**。
    - 旧版用 rglob 递归统计，导致「扫描到 N 张但提升 0 张」的口径错位假象
      （2026-09-01 健康度检查发现并修复）。

    平台判定规则：
    - 若草稿在 .sync/drafts/<platform>_draft/ 下 → 该平台
    - 若草稿直接在 .sync/drafts/ 下（扁平结构） → 归入 "default"
    """
    drafts_dir = root / ".sync" / "drafts"
    if not drafts_dir.is_dir():
        return {}

    platform_drafts: dict[str, list[Path]] = {}
    # 与 ingest 对齐：只扫根目录 *.md，不递归子目录
    for p in sorted(drafts_dir.glob("*")):
        if p.is_dir():
            platform = p.name.replace("_draft", "") if p.name.endswith("_draft") else None
            if platform is None:
                continue
            mds = sorted(p.glob("*.md"))
        elif p.suffix == ".md":
            platform = "default"
            mds = [p]
        else:
            continue
        if mds:
            platform_drafts.setdefault(platform, []).extend(mds)

    return platform_drafts


def run_ingest(root: Path, platform: str) -> dict:
    """调用 hub-engine 的 ingest 流程。返回 stat dict。"""
    from sync import ingest

    try:
        stat = ingest(root, platform)
        return stat
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[error] ingest 失败（平台={platform}）：{exc}", file=sys.stderr)
        traceback.print_exc()
        return {
            "promoted": 0,
            "pending": 0,
            "duplicate": 0,
            "invalid": 0,
            "status": f"error: {exc}",
        }


def run_build_vectors(root: Path) -> dict:
    """调用 hub-engine 的 build-vectors 流程。返回 stats dict。"""
    from tools.semsearch import build

    try:
        stats = build(root)
        return stats
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[error] build-vectors 失败：{exc}", file=sys.stderr)
        traceback.print_exc()
        return {"error": str(exc)}


def append_log(root: Path, record: dict) -> None:
    """追加写入 flywheel-log.json（JSON 行格式，便于审计）。"""
    log_path = root / ".sync" / "state" / "flywheel-log.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # 读取已有记录（若存在），追加后整体重写
    existing = []
    if log_path.exists():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, ValueError):
            existing = []
    existing.append(record)
    write_text_utf8(log_path, json.dumps(existing, ensure_ascii=False, indent=2))


def has_pending_drafts(root: Path) -> bool:
    """检查是否有待处理的草稿（供事件触发使用）。"""
    platform_drafts = scan_drafts(root)
    return sum(len(v) for v in platform_drafts.values()) > 0


def run(args: argparse.Namespace) -> int:
    """执行自动飞轮主流程。"""
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[error] 中枢根目录不存在：{root}", file=sys.stderr)
        return 2

    # 1. 扫描草稿
    platform_drafts = scan_drafts(root)
    total_drafts = sum(len(v) for v in platform_drafts.values())

    if total_drafts == 0:
        print("无待处理草稿")
        # 事件触发模式下，输出信号供调用方判断
        if getattr(args, "event_mode", False):
            print("EVENT:NO_DRAFTS")
        return 0

    # 过滤平台（--platform 指定时只处理该平台）
    if args.platform:
        platform_drafts = {k: v for k, v in platform_drafts.items() if k == args.platform}
        if not platform_drafts:
            print(f"指定平台 [{args.platform}] 无草稿")
            return 0

    print(f"扫描到 {total_drafts} 张草稿，分布于 {len(platform_drafts)} 个平台：")
    for pf, files in platform_drafts.items():
        print(f"  - {pf}: {len(files)} 张")

    # 路由表同步检查（可选，dry-run 时也执行）
    if getattr(args, "router_sync", False) and getattr(args, "skillhub_root", ""):
        skillhub_root = Path(args.skillhub_root).resolve()
        if skillhub_root.is_dir():
            print("\n===== 路由表同步检查 =====")
            try:
                import router_sync as rs

                hub_md = rs.find_hub_router(root)
                sh_yaml = skillhub_root / "router" / "router.yaml"
                hub_entries = rs.parse_hub_router(hub_md) if hub_md else []
                sh_entries = rs.parse_skillhub_router(sh_yaml)
                rs_report = rs.diff_routers(hub_entries, sh_entries)

                rs.print_report(rs_report)

                sem = len(rs_report.get("semantic_mismatch", []))
                struc = len(rs_report.get("structural_mismatch", []))
                miss_sh = len(rs_report.get("missing_in_skillhub", []))
                miss_hub = len(rs_report.get("missing_in_hub", []))

                if sem or struc or miss_sh or miss_hub:
                    print(f"\n[router-sync] 语义差异={sem}, 结构差异={struc}, 中枢缺失={miss_sh}, SkillHub缺失={miss_hub}")

                    # 智能自动修复策略
                    if getattr(args, "auto_fix", False):
                        has_field_diff = sem > 0 or struc > 0
                        if has_field_diff:
                            print("[router-sync] ⚠️ 存在字段差异，需人工确认，仅报告不自动修复")
                        elif miss_sh or miss_hub:
                            print("[router-sync] ✅ 仅缺失条目，无字段差异，执行自动修复")
                            _fixes, msgs = rs.apply_fixes(
                                skillhub_root, rs_report,
                                merge_strategy=getattr(args, "router_sync_strategy", "manual"),
                            )
                            for m in msgs:
                                print(f"  {m}")
                            print(f"[router-sync] 自动修复完成，共处理 {miss_sh + miss_hub} 条缺失项")
                    elif getattr(args, "router_sync_fix", False):
                        _fixes, msgs = rs.apply_fixes(
                            skillhub_root, rs_report,
                            merge_strategy=getattr(args, "router_sync_strategy", "manual"),
                        )
                        for m in msgs:
                            print(f"  {m}")
                    print("[router-sync] 建议: 定期运行 router-sync diff 检查，避免路由表漂移")
                else:
                    print("[router-sync] ✅ 路由表完全同步")

            except (ImportError, OSError, ValueError) as e:
                print(f"[router-sync] 检查失败: {e}")

    if args.dry_run:
        print("[dry-run] 仅扫描，不执行 ingest / build-vectors")
        return 0

    # 2. 逐平台执行 ingest
    ingest_results: dict[str, dict] = {}
    total_promoted = 0
    total_pending = 0
    total_duplicate = 0
    total_invalid = 0

    for platform in sorted(platform_drafts.keys()):
        count = len(platform_drafts[platform])
        print(f"\n[ingest] 处理平台 {platform}（{count} 张草稿）...")
        stat = run_ingest(root, platform)
        ingest_results[platform] = stat
        total_promoted += stat.get("promoted", 0)
        total_pending += stat.get("pending", 0)
        total_duplicate += stat.get("duplicate", 0)
        total_invalid += stat.get("invalid", 0)
        status = stat.get("status", "ok")
        print(
            f"  → promoted={stat.get('promoted', 0)}  pending={stat.get('pending', 0)}"
            f"  duplicate={stat.get('duplicate', 0)}  invalid={stat.get('invalid', 0)}"
            f"  status={status}"
        )

    # 3. 执行 build-vectors（不阻断于 ingest 失败）
    print("\n[build-vectors] 构建向量库...")
    vec_stats = run_build_vectors(root)
    print(f"  → {json.dumps(vec_stats, ensure_ascii=False)}")

    # 4. 汇总结果
    print("\n===== 处理汇总 =====")
    print(f"草稿总数：{total_drafts}")
    print(f"成功提升：{total_promoted}")
    print(f"待确认：{total_pending}")
    print(f"重复进冲突区：{total_duplicate}")
    print(f"无效卡片：{total_invalid}")

    # 5. 写入日志
    record = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": today_iso(),
        "total_drafts": total_drafts,
        "platforms": {pf: len(files) for pf, files in platform_drafts.items()},
        "ingest_results": ingest_results,
        "vector_stats": vec_stats,
        "summary": {
            "promoted": total_promoted,
            "pending": total_pending,
            "duplicate": total_duplicate,
            "invalid": total_invalid,
        },
    }
    append_log(root, record)
    print(f"\n日志已写入：{root / '.sync' / 'state' / 'flywheel-log.json'}")

    # 6. 路由表同步检查（可选）
    if getattr(args, "router_sync", False) and getattr(args, "skillhub_root", ""):
        skillhub_root = Path(args.skillhub_root).resolve()
        if skillhub_root.is_dir():
            print("\n===== 路由表同步检查 =====")
            try:
                import router_sync as rs

                hub_md = rs.find_hub_router(root)
                sh_yaml = skillhub_root / "router" / "router.yaml"
                hub_entries = rs.parse_hub_router(hub_md) if hub_md else []
                sh_entries = rs.parse_skillhub_router(sh_yaml)
                rs_report = rs.diff_routers(hub_entries, sh_entries)

                rs.print_report(rs_report)

                # 输出分类摘要
                sem = len(rs_report.get("semantic_mismatch", []))
                struc = len(rs_report.get("structural_mismatch", []))
                miss_sh = len(rs_report.get("missing_in_skillhub", []))
                miss_hub = len(rs_report.get("missing_in_hub", []))

                if sem or struc or miss_sh or miss_hub:
                    print(f"\n[router-sync] 语义差异={sem}, 结构差异={struc}, 中枢缺失={miss_sh}, SkillHub缺失={miss_hub}")

                    # 智能自动修复策略
                    if getattr(args, "auto_fix", False):
                        has_field_diff = sem > 0 or struc > 0
                        if has_field_diff:
                            print("[router-sync] ⚠️ 存在字段差异，需人工确认，仅报告不自动修复")
                        elif miss_sh or miss_hub:
                            print("[router-sync] ✅ 仅缺失条目，无字段差异，执行自动修复")
                            _fixes, msgs = rs.apply_fixes(
                                skillhub_root, rs_report,
                                merge_strategy=getattr(args, "router_sync_strategy", "manual"),
                            )
                            for m in msgs:
                                print(f"  {m}")
                            print(f"[router-sync] 自动修复完成，共处理 {miss_sh + miss_hub} 条缺失项")
                    elif getattr(args, "router_sync_fix", False):
                        _fixes, msgs = rs.apply_fixes(
                            skillhub_root, rs_report,
                            merge_strategy=getattr(args, "router_sync_strategy", "manual"),
                        )
                        for m in msgs:
                            print(f"  {m}")
                    print("[router-sync] 建议: 定期运行 router-sync diff 检查，避免路由表漂移")
                else:
                    print("[router-sync] ✅ 路由表完全同步")

            except (ImportError, OSError, ValueError) as e:
                print(f"[router-sync] 检查失败: {e}")
        else:
            print(f"[router-sync] SkillHub 目录不存在: {skillhub_root}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="auto-flywheel",
        description="自动飞轮：扫描草稿 → ingest → build-vectors",
    )
    parser.add_argument(
        "--root",
        required=True,
        help="中枢根目录路径",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="仅扫描不落盘，不执行 ingest / build",
    )
    parser.add_argument(
        "--platform",
        default="",
        help="仅处理指定平台（留空则处理所有有草稿的平台）",
    )
    parser.add_argument(
        "--event-mode",
        action="store_true",
        default=False,
        help="事件触发模式：无草稿时输出 EVENT:NO_DRAFTS 信号，供上层判断",
    )
    parser.add_argument(
        "--skillhub-root",
        default="",
        help="SkillHub 根目录路径（用于路由表同步检查）",
    )
    parser.add_argument(
        "--router-sync",
        action="store_true",
        default=False,
        help="飞轮完成后执行路由表同步检查",
    )
    parser.add_argument(
        "--router-sync-fix",
        action="store_true",
        default=False,
        help="路由表同步时自动修复缺失项",
    )
    parser.add_argument(
        "--router-sync-strategy",
        default="manual",
        choices=["manual", "prefer_hub", "prefer_skillhub"],
        help="路由表同步合并策略",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        default=False,
        help="智能自动修复：无字段差异时自动修复缺失项，有字段差异时仅报告",
    )
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
