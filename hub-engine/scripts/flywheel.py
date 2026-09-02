"""飞轮统一启动命令：auto-flywheel → skill-create → smoke-test → tag → runlog → iteration → session-preload → daily-report
用法：
  python flywheel.py run --hub-root <中枢> --skillhub-root <SkillHub> [--auto] [--promote] [--tag] [--dry-run]
  python flywheel.py status --skillhub-root <SkillHub>          # 状态
  python flywheel.py timeline --skillhub-root <SkillHub>        # 时间线回放
  python flywheel.py version-tag --skill <技能名> --skillhub-root <SkillHub>
  python flywheel.py iteration --hub-root <中枢> --skillhub-root <SkillHub> [--dry-run]
  python flywheel.py record-usage --skill <技能名> --skillhub-root <SkillHub> [--grade strong|weak]
  python flywheel.py alert --hub-root <中枢> --skillhub-root <SkillHub>
  python flywheel.py runlog list|record|timeline ...            # runlog 三段子命令
  python flywheel.py session-preload --hub-root <中枢> --query <用户问题>  # 会话预加载
  python flywheel.py daily-report --hub-root <中枢> --skillhub-root <SkillHub> [--hermes-target <微信>]  # 日报推送
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 脚本目录（与本脚本同目录）
_SCRIPT_DIR = Path(__file__).resolve().parent

# 确保可 import 同级脚本与 flywheel_runlog
import sys as _sys_mod

_sys_mod.path.insert(0, str(_SCRIPT_DIR))

from flywheel_runlog import append_record, make_record
from flywheel_runlog import main as runlog_main


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """运行子命令，统一捕获输出。不抛异常，调用方自行判断 returncode。"""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        **kwargs,
    )


def step_flywheel(hub_root: str | Path, dry_run: bool) -> dict:
    """步骤 1：自动飞轮（扫描草稿 → ingest → build-vectors）"""
    script = _SCRIPT_DIR / "auto_flywheel.py"
    cmd = [sys.executable, str(script), "--root", str(hub_root)]
    if dry_run:
        cmd.append("--dry-run")
    r = _run(cmd)
    return {
        "step": "auto-flywheel",
        "exit": r.returncode,
        "output": r.stdout.strip(),
        "error": r.stderr.strip() if r.stderr else "",
    }


def step_register(hub_root: str | Path, skillhub_root: str | Path, dry_run: bool) -> dict:
    """步骤 2：自动注册（从中枢新卡片创建 SkillHub 技能）
    扫描中枢 .sync/drafts/ 中已 ingest 但 SkillHub 中尚无对应技能的卡片，
    或者用 --card 指定的卡片名
    """
    # 先调用 auto_flywheel 看 ingest 后产生了哪些新卡
    # 简化版：直接遍历中枢的新卡片，检查 SkillHub 是否已注册
    import re
    from pathlib import Path as _P

    hub = _P(hub_root)
    skillhub = _P(skillhub_root)

    # 收集 SkillHub 中已注册的技能名
    registered = set()
    for skill_yaml in skillhub.rglob("skill.yaml"):
        try:
            content = skill_yaml.read_text(encoding="utf-8")
            m = re.search(r"^name:\s*(\S+)", content, re.MULTILINE)
            if m:
                registered.add(m.group(1))
        except (OSError, ValueError):
            pass

    # 收集中枢新卡片（experience/methodology/rules/blueprints/projects）
    card_dirs = ["experience", "methodology", "rules", "blueprints", "projects"]
    new_cards = []
    for d in card_dirs:
        dir_path = hub / d
        if not dir_path.is_dir():
            continue
        for md_file in dir_path.glob("*.md"):
            card_name = md_file.stem
            if card_name not in registered and not card_name.startswith("_"):
                # 读取 frontmatter 获取类型和 tags
                try:
                    content = md_file.read_text(encoding="utf-8")
                    type_m = re.search(r"^type:\s*(\S+)", content, re.MULTILINE)
                    card_type = type_m.group(1) if type_m else "exp"
                    # 映射 card type → slot + scope
                    slot, scope_map = _card_type_to_slot_scope(card_type)
                    new_cards.append(
                        {
                            "name": card_name,
                            "type": card_type,
                            "dir": d,
                            "slot": slot,
                            "scope": scope_map,
                        }
                    )
                except (OSError, ValueError):
                    pass

    results = []
    for card in new_cards:
        register_cmd = [
            sys.executable,
            str(_SCRIPT_DIR / "skill_create_from_card.py"),
            "--card",
            card["name"],
            "--hub-root",
            str(hub_root),
            "--skillhub-root",
            str(skillhub_root),
            "--slot",
            card["slot"],
            "--scope",
            card["scope"],
        ]
        if dry_run:
            register_cmd.append("--dry-run")
        r = _run(register_cmd)
        results.append(
            {
                "card": card["name"],
                "exit": r.returncode,
                "output": r.stdout.strip(),
            }
        )

    return {
        "step": "skill-register",
        "found_new": len(new_cards),
        "results": results,
    }


def step_smoke(
    skillhub_root: str | Path,
    hub_root: str | Path,
    auto_promote: bool,
    dry_run: bool,
    do_tag: bool = False,
    tag_flywheel: bool = False,
) -> dict:
    """步骤 3：对 SkillHub 中所有 reference 状态的技能做 smoke test

    当 promote + do_tag 同时开启时，对每个 promote 成功的技能自动打 git tag
    （tag_flywheel=True 时追加 -flywheel 后缀，标识为飞轮产出）。
    """
    import re
    from pathlib import Path as _P

    skillhub = _P(skillhub_root)
    results = []

    # 找所有 status=reference 的技能
    for skill_yaml in skillhub.rglob("skill.yaml"):
        try:
            content = skill_yaml.read_text(encoding="utf-8")
            status_m = re.search(r"^status:\s*(\S+)", content, re.MULTILINE)
            name_m = re.search(r"^name:\s*(\S+)", content, re.MULTILINE)
            if not status_m or not name_m:
                continue
            status = status_m.group(1)
            skill_name = name_m.group(1)
            if status != "reference":
                continue
        except (OSError, ValueError):
            continue

        smoke_cmd = [
            sys.executable,
            str(_SCRIPT_DIR / "skill_smoke_test.py"),
            "--skill",
            skill_name,
            "--skillhub-root",
            str(skillhub_root),
            "--hub-root",
            str(hub_root),
        ]
        if auto_promote:
            smoke_cmd.append("--auto-promote")
        if do_tag:
            smoke_cmd.append("--tag")
            if tag_flywheel:
                smoke_cmd.append("--tag-flywheel-origin")
        if dry_run:
            smoke_cmd.append("--dry-run")
        r = _run(smoke_cmd)
        results.append(
            {
                "skill": skill_name,
                "exit": r.returncode,
                "output": r.stdout.strip(),
                "tagged": (do_tag and auto_promote and r.returncode == 0),
            }
        )

    return {
        "step": "smoke-test",
        "tested": len(results),
        "results": results,
        "tagged": sum(1 for r in results if r.get("tagged")),
    }


def _card_type_to_slot_scope(card_type: str) -> tuple[str, str]:
    """中枢卡类型 → SkillHub slot + scope"""
    mapping = {
        "rule": ("shared", "govern"),
        "methodology": ("shared", "engineering"),
        "blueprint": ("shared", "engineering"),
        "exp": ("shared", "productivity"),
        "project": ("shared", "engineering"),
        "longterm": ("shared", "govern"),
        "note": ("shared", "productivity"),
        "retro": ("shared", "govern"),
    }
    return mapping.get(card_type, ("shared", "productivity"))


def cmd_status(skillhub_root: str | Path) -> int:
    """查看飞轮状态（已注册技能的 status 分布）"""
    import re
    from collections import Counter

    skillhub = Path(skillhub_root)
    statuses = Counter()
    skills = []

    for skill_yaml in skillhub.rglob("skill.yaml"):
        try:
            content = skill_yaml.read_text(encoding="utf-8")
            status_m = re.search(r"^status:\s*(\S+)", content, re.MULTILINE)
            name_m = re.search(r"^name:\s*(\S+)", content, re.MULTILINE)
            reuse_m = re.search(r"^reuse_count:\s*(\d+)", content, re.MULTILINE)
            if status_m and name_m:
                status = status_m.group(1)
                name = name_m.group(1)
                reuse = int(reuse_m.group(1)) if reuse_m else 0
                statuses[status] += 1
                skills.append(
                    {
                        "name": name,
                        "status": status,
                        "reuse": reuse,
                        "path": str(skill_yaml.parent.relative_to(skillhub)),
                    }
                )
        except (OSError, ValueError):
            pass

    # 输出
    print("=== SkillHub 飞轮状态 ===")
    print(f"技能总数: {len(skills)}")
    for status, count in sorted(statuses.items()):
        print(f"  {status}: {count}")
    print()
    for s in sorted(skills, key=lambda x: (x["status"] != "active", x["name"])):
        print(f"  [{s['status']:10s}] {s['name']} (reuse={s['reuse']}) → {s['path']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="flywheel",
        description="飞轮统一启动：auto-flywheel → skill-register → smoke-test",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # flywheel run：执行完整飞轮
    p_run = sub.add_parser("run", help="执行完整飞轮（飞轮→注册→验证→打tag→记日志）")
    p_run.add_argument("--hub-root", required=True, help="中枢根目录")
    p_run.add_argument("--skillhub-root", required=True, help="SkillHub 根目录")
    p_run.add_argument("--auto", action="store_true", help="自动注册新卡为 SkillHub 技能")
    p_run.add_argument("--promote", action="store_true", help="验证通过时自动提升为 active")
    p_run.add_argument(
        "--tag",
        action="store_true",
        help="promote 成功时自动打 git tag（默认 flywheel 来源）",
    )
    p_run.add_argument(
        "--no-flywheel-tag",
        action="store_true",
        help="tag 不追加 -flywheel 后缀（标为手动）",
    )
    p_run.add_argument("--no-log", action="store_true", help="本次不写入 runlog（默认写）")
    p_run.add_argument("--dry-run", action="store_true", help="预览模式，不落盘")
    p_run.set_defaults(func=_cmd_run)

    # flywheel flywheel：单独跑 auto-flywheel
    p_fw = sub.add_parser("flywheel", help="仅执行 auto-flywheel（草稿→ingest→build）")
    p_fw.add_argument("--hub-root", required=True)
    p_fw.add_argument("--dry-run", action="store_true")
    p_fw.set_defaults(func=_cmd_flywheel)

    # flywheel register：单独跑 skill-register
    p_reg = sub.add_parser("register", help="仅执行 skill-register（新卡→技能）")
    p_reg.add_argument("--hub-root", required=True)
    p_reg.add_argument("--skillhub-root", required=True)
    p_reg.add_argument("--dry-run", action="store_true")
    p_reg.set_defaults(func=_cmd_register)

    # flywheel smoke：单独跑 smoke-test
    p_smoke = sub.add_parser("smoke", help="仅执行 smoke-test（reference→active）")
    p_smoke.add_argument("--hub-root", required=True)
    p_smoke.add_argument("--skillhub-root", required=True)
    p_smoke.add_argument("--promote", action="store_true")
    p_smoke.add_argument("--dry-run", action="store_true")
    p_smoke.set_defaults(func=_cmd_smoke)

    # flywheel status：查看状态
    p_status = sub.add_parser("status", help="查看飞轮状态")
    p_status.add_argument("--skillhub-root", required=True)
    p_status.set_defaults(func=_cmd_status)

    # flywheel timeline：生成可视化回放 HTML
    p_timeline = sub.add_parser("timeline", help="生成飞轮可视化回放 HTML")
    p_timeline.add_argument("--skillhub-root", required=True, help="SkillHub 根目录")
    p_timeline.add_argument(
        "--output",
        default="",
        help="HTML 输出路径（默认 SkillHub/work/flywheel/timeline.html）",
    )
    p_timeline.set_defaults(func=cmd_timeline_proxy)

    # flywheel version-tag：给单个技能打 git tag（代理 skill_version_tag.py）
    p_tag = sub.add_parser("version-tag", help="技能打 git tag（skill-<名>-v<版本>[-flywheel]）")
    p_tag.add_argument("--skill", required=True, help="技能名")
    p_tag.add_argument("--skillhub-root", required=True, help="SkillHub 根目录")
    p_tag.add_argument("--hub-root", default="", help="中枢路径（用于检测源卡）")
    p_tag.add_argument(
        "--flywheel-origin",
        action="store_true",
        help="标识为飞轮产出（追加 -flywheel 后缀）",
    )
    p_tag.add_argument("--force", action="store_true", help="tag 已存在则覆盖")
    p_tag.add_argument("--dry-run", action="store_true", help="预览模式，不真的 commit/tag")
    p_tag.set_defaults(func=_cmd_version_tag_proxy)

    # flywheel runlog：三段子命令 list/record/timeline（直接代理 flywheel_runlog）
    p_runlog = sub.add_parser("runlog", help="飞轮运行日志：list / record / timeline")
    p_runlog.add_argument(
        "runlog_sub",
        nargs=argparse.REMAINDER,
        help="子命令参数（list / record ... / timeline ...）",
    )
    p_runlog.set_defaults(func=_cmd_runlog_proxy)

    # flywheel iteration：技能迭代引擎（detect → apply → deprecation-check → auto-tag）
    p_iter = sub.add_parser("iteration", help="技能迭代：源卡变更检测 → 版本升级/降级 → 能力画像")
    p_iter.add_argument("--hub-root", required=True)
    p_iter.add_argument("--skillhub-root", required=True)
    p_iter.add_argument("--dry-run", action="store_true", help="预览模式，不落盘")
    p_iter.set_defaults(func=_cmd_iteration)

    # flywheel record-usage：记录技能使用（reuse_count++）
    p_rec = sub.add_parser("record-usage", help="记录技能使用（strong→reuse_count++）")
    p_rec.add_argument("--skill", required=True)
    p_rec.add_argument("--skillhub-root", required=True)
    p_rec.add_argument("--grade", default="strong", choices=["strong", "weak", "discard"])
    p_rec.set_defaults(func=_cmd_record_usage)

    # flywheel alert：自监控告警检查
    p_alert = sub.add_parser("alert", help="飞轮自监控告警检查（无产物/低命中率/零复用）")
    p_alert.add_argument("--hub-root", required=True)
    p_alert.add_argument("--skillhub-root", required=True)
    p_alert.add_argument("--alert-days", type=int, default=2)
    p_alert.set_defaults(func=_cmd_alert)

    # flywheel router-sync：跨平台路由表同步检查
    p_rs = sub.add_parser("router-sync", help="中枢↔SkillHub 路由表双向 diff + 同步")
    p_rs.add_argument("--hub-root", required=True)
    p_rs.add_argument("--skillhub-root", required=True)
    p_rs.add_argument("--fix", action="store_true", help="正向修复（中枢→SkillHub）")
    p_rs.add_argument("--reverse-fix", action="store_true", help="反向修复（SkillHub→中枢）")
    p_rs.add_argument(
        "--merge-strategy",
        default="manual",
        choices=["manual", "prefer_hub", "prefer_skillhub"],
        help="字段冲突合并策略",
    )
    p_rs.add_argument("--classification", action="store_true", help="显示差异分类统计")
    p_rs.add_argument("--report", default="", help="JSON 报告输出路径")
    p_rs.set_defaults(func=_cmd_router_sync)

    # flywheel session-preload：会话预加载（基于用户意图加载 Top-K 卡片摘要）
    p_sp = sub.add_parser("session-preload", help="会话预加载：基于用户意图加载 Top-K 卡片摘要")
    p_sp.add_argument("--hub-root", required=True, help="中枢根目录")
    p_sp.add_argument("--query", required=True, help="用户初始查询/问题")
    p_sp.add_argument("--top-k", type=int, default=3, help="加载的卡片数量")
    p_sp.add_argument("--max-tokens", type=int, default=800, help="最大 token 数")
    p_sp.add_argument("--json", action="store_true", help="输出 JSON 格式")
    p_sp.add_argument("--brief-only", action="store_true", help="仅输出简报文本")
    p_sp.set_defaults(func=_cmd_session_preload)

    # flywheel daily-report：飞轮日报生成与推送
    p_dr = sub.add_parser("daily-report", help="生成飞轮日报并推送到微信/企业微信/飞书")
    p_dr.add_argument("--hub-root", required=True, help="中枢根目录")
    p_dr.add_argument("--skillhub-root", required=True, help="SkillHub 根目录")
    p_dr.add_argument("--date", default="", help="指定日期 (YYYY-MM-DD)，默认今天")
    p_dr.add_argument("--output", default="", help="输出 Markdown 文件路径")
    p_dr.add_argument("--hermes-target", default="", help="Hermes 推送到微信 (如 weixin:chat_id)")
    p_dr.add_argument("--serverchan-key", default="", help="Server酱 SCKEY（推送到个人微信）")
    p_dr.add_argument("--pushplus-token", default="", help="PushPlus Token（推送到个人微信）")
    p_dr.add_argument("--wecom-webhook", default="", help="企业微信群机器人 Webhook")
    p_dr.add_argument("--feishu-webhook", default="", help="飞书群机器人 Webhook")
    p_dr.add_argument("--push-config", default="", help="推送配置文件（批量多渠道）")
    p_dr.set_defaults(func=_cmd_daily_report)

    args = parser.parse_args(argv)
    return args.func(args)


def _cmd_run(args) -> int:
    """执行完整飞轮（自动写 runlog，默认 tag 带 flywheel 来源）"""
    print("=" * 60)
    print("  飞轮统一启动（flywheel run）")
    print("=" * 60)

    # Runlog: 记录本圈启动（--no-log 跳过）
    skillhub_root = Path(args.skillhub_root).resolve()
    do_log = not getattr(args, "no_log", False)
    start_ts = datetime.now().astimezone().isoformat(timespec="seconds")
    run_input = (
        f"dry-run={args.dry_run}, auto={args.auto}, promote={args.promote}, "
        f"tag={args.tag}, flywheel-tag={not getattr(args, 'no_flywheel_tag', False)}"
    )
    run_ok = True
    results = []  # 收集每个子步骤的结果，用于 run 记录

    tag_flywheel = not getattr(args, "no_flywheel_tag", False)

    # 步骤 1：auto-flywheel
    print("\n[1/3] auto-flywheel：扫描草稿 → ingest → build-vectors")
    r1 = step_flywheel(args.hub_root, args.dry_run)
    print(f"  exit={r1['exit']}")
    print(f"  {r1['output']}")
    if r1.get("error"):
        print(f"  error: {r1['error']}")
    # Runlog: flywheel 子步骤
    if do_log:
        append_record(
            skillhub_root,
            make_record(
                "flywheel",
                f"hub={args.hub_root} dry-run={args.dry_run}",
                (r1.get("output") or "")[:1000],
                r1.get("exit", 0) == 0,
                {"exit_code": r1.get("exit"), "step": r1.get("step")},
            ),
        )
    results.append(r1)
    if r1.get("exit", 0) != 0:
        run_ok = False

    # 步骤 2：skill-register（仅当 --auto）
    if args.auto:
        print("\n[2/3] skill-register：新卡 → SkillHub 技能")
        r2 = step_register(args.hub_root, args.skillhub_root, args.dry_run)
        print(f"  发现新卡: {r2['found_new']}")
        reg_output_parts = []
        for res in r2["results"]:
            status = "✓" if res["exit"] == 0 else "✗"
            line = f"  {status} {res['card']}: {res['output'][:100]}"
            print(line)
            reg_output_parts.append(line)
        # Runlog: register 子步骤
        reg_ok = all(res.get("exit", 0) == 0 for res in r2["results"]) if r2["results"] else True
        if do_log:
            append_record(
                skillhub_root,
                make_record(
                    "register",
                    f"hub={args.hub_root} skillhub={args.skillhub_root} found_new={r2.get('found_new', 0)}",
                    ("\n".join(reg_output_parts) or r2.get("output", ""))[:1000],
                    reg_ok,
                    {
                        "exit_code": 0 if reg_ok else 1,
                        "step": r2.get("step"),
                        "found_new": r2.get("found_new"),
                    },
                ),
            )
        results.append(r2)
        if not reg_ok:
            run_ok = False
    else:
        print("\n[2/3] skill-register：跳过（--auto 未指定）")

    # 步骤 3：smoke-test（带 --tag 透传）
    print("\n[3/3] smoke-test：reference → active 验证")
    r3 = step_smoke(
        args.skillhub_root,
        args.hub_root,
        args.promote,
        args.dry_run,
        do_tag=args.tag,
        tag_flywheel=tag_flywheel,
    )
    print(f"  测试技能数: {r3['tested']}  已打 tag: {r3.get('tagged', 0)}")
    smoke_output_parts = []
    for res in r3["results"]:
        status = "✓" if res["exit"] == 0 else "✗"
        tag_mark = " 🏷️" if res.get("tagged") else ""
        line = f"  {status} {res['skill']}: {res['output'][:120]}{tag_mark}"
        print(line)
        smoke_output_parts.append(line)
    # Runlog: smoke 子步骤
    smoke_ok = all(res.get("exit", 0) == 0 for res in r3["results"]) if r3["results"] else True
    if do_log:
        append_record(
            skillhub_root,
            make_record(
                "smoke",
                f"skillhub={args.skillhub_root} hub={args.hub_root} promote={args.promote} "
                f"tag={args.tag} tested={r3.get('tested', 0)} tagged={r3.get('tagged', 0)}",
                ("\n".join(smoke_output_parts) or r3.get("output", ""))[:1000],
                smoke_ok,
                {
                    "exit_code": 0 if smoke_ok else 1,
                    "step": r3.get("step"),
                    "tested": r3.get("tested"),
                    "tagged": r3.get("tagged"),
                },
            ),
        )
    results.append(r3)
    if not smoke_ok:
        run_ok = False

    print("\n" + "=" * 60)
    print("  飞轮执行完成")
    print("=" * 60)
    if args.tag:
        tag_count = r3.get("tagged", 0)
        if tag_count:
            suff = "-flywheel" if tag_flywheel else ""
            print(f"  🏷️  {tag_count} 个 promote 成功的技能已打 git tag（{suff or '手动'} 来源）")
        else:
            print("  🏷️  无可打 tag 的技能（没有 reference 技能 promote 成功）")

    # Runlog: 完整 run 结果
    if do_log:
        append_record(
            skillhub_root,
            make_record(
                "run",
                run_input,
                f"子步骤数={len(results)}  成功子步骤={sum(1 for r in results if _step_ok(r))}  "
                f"tagged={r3.get('tagged', 0)}",
                run_ok,
                {
                    "stages": len(results),
                    "start_ts": start_ts,
                    "tagged": r3.get("tagged"),
                },
            ),
        )
    return 0


def _step_ok(result: dict) -> bool:
    """判断一个步骤结果是否成功（兼容不同结构的 result）。"""
    if "exit" in result:
        return result.get("exit", 0) == 0
    if "results" in result:
        return all(r.get("exit", 0) == 0 for r in result["results"])
    return True


def _cmd_flywheel(args) -> int:
    print("[auto-flywheel]")
    r = step_flywheel(args.hub_root, args.dry_run)
    print(r["output"])
    return r["exit"]


def _cmd_register(args) -> int:
    print("[skill-register]")
    r = step_register(args.hub_root, args.skillhub_root, args.dry_run)
    print(f"发现新卡: {r['found_new']}")
    for res in r["results"]:
        status = "✓" if res["exit"] == 0 else "✗"
        print(f"  {status} {res['card']}")
    return 0


def _cmd_smoke(args) -> int:
    print("[smoke-test]")
    r = step_smoke(args.skillhub_root, args.hub_root, args.promote, args.dry_run)
    print(f"测试技能数: {r['tested']}")
    for res in r["results"]:
        status = "✓" if res["exit"] == 0 else "✗"
        print(f"  {status} {res['skill']}")
    return 0


def _cmd_status(args) -> int:
    return cmd_status(args.skillhub_root)


def cmd_timeline_proxy(args) -> int:
    """代理调用 flywheel_runlog timeline 子命令，生成回放页。"""
    from flywheel_runlog import main as timeline_main

    skillhub = getattr(args, "skillhub_root", None)
    tl_args = ["timeline"]
    if skillhub:
        tl_args += ["--skillhub-root", str(skillhub)]
    if getattr(args, "output", None):
        tl_args += ["--output", str(args.output)]
    return timeline_main(tl_args)


def _cmd_version_tag_proxy(args) -> int:
    """代理调用 skill_version_tag 的 CLI 入口。"""
    from skill_version_tag import main as tag_main

    sub = ["--skill", args.skill, "--skillhub-root", str(args.skillhub_root)]
    if getattr(args, "hub_root", None):
        sub += ["--hub-root", str(args.hub_root)]
    if getattr(args, "flywheel_origin", False):
        sub.append("--flywheel-origin")
    if getattr(args, "force", False):
        sub.append("--force")
    if getattr(args, "dry_run", False):
        sub.append("--dry-run")
    return tag_main(sub)


def _cmd_runlog_proxy(args) -> int:
    """代理调用 flywheel_runlog 三段子命令。"""
    extra = getattr(args, "runlog_sub", []) or []
    return runlog_main(list(extra))


def _cmd_iteration(args) -> int:
    """技能迭代引擎：detect → apply → deprecation-check → auto-tag。"""
    import skill_iteration

    hub = Path(args.hub_root).resolve()
    skillhub = Path(args.skillhub_root).resolve()

    print("=" * 50)
    print("  技能迭代引擎 (flywheel iteration)")
    print("=" * 50)

    # Step 1: detect
    print("\n[1/4] detect_source_changes...")
    changes = skill_iteration.detect_source_changes(hub, skillhub)
    print(f"  检测到 {len(changes)} 条变更")
    for c in changes:
        print(f"  [{c['action']}] {c['skill']}: {c['detail']}")

    # Step 2: apply rules
    print("\n[2/4] apply_iteration_rules...")
    results = skill_iteration.apply_iteration_rules(changes, hub, skillhub, dry_run=args.dry_run)
    for r in results:
        emoji = "🆕" if "version" in r.get("action", "") else "⚠️" if "deprecate" in r.get("action", "") else "✅"
        print(f"  {emoji} [{r['action']}] {r['skill']}: {r['detail']}")

    # Step 3: deprecation check
    print("\n[3/4] apply_deprecation_rules...")
    dep_results = skill_iteration.apply_deprecation_rules(skillhub, dry_run=args.dry_run)
    for r in dep_results:
        print(f"  ⚠️ [{r['action']}] {r['skill']}: {r['detail']}")
    if not dep_results:
        print("  无需降级的技能")

    # Step 4: auto capability tagging
    print("\n[4/4] auto_capability_tagging...")
    cap_results = skill_iteration.auto_capability_tagging(skillhub, dry_run=args.dry_run)
    changed = [r for r in cap_results if r["action"] == "capabilities_updated"]
    print(f"  能力画像更新: {len(changed)} 个技能")
    for r in changed:
        print(f"  🆕 [{r['skill']}] {r['old_caps']} → {r['new_caps']}")

    total = len(results) + len(dep_results)
    print(f"\n迭代完成: {total} 条变更（{'dry-run' if args.dry_run else '已落盘'}）")
    return 0


def _cmd_record_usage(args) -> int:
    """记录技能使用（归因 strong → reuse_count++）。"""
    import skill_iteration

    skillhub = Path(args.skillhub_root).resolve()
    result = skill_iteration.record_skill_usage(args.skill, skillhub, args.grade)
    action_icons = {
        "reuse_count_incremented": "📈",
        "weak_recorded": "📝",
        "discard_ignored": "🚫",
        "not_found": "❌",
    }
    icon = action_icons.get(result.get("action", ""), "❓")
    print(f"{icon} {result['skill']}: {result.get('action', 'unknown')}")
    if "new_reuse" in result:
        print(f"   reuse_count: {result['old_reuse']} → {result['new_reuse']}")
    return 0


def _cmd_alert(args) -> int:
    """飞轮自监控告警检查。"""
    import hub_health
    import skill_iteration

    hub = Path(args.hub_root).resolve()
    skillhub = Path(args.skillhub_root).resolve()
    log_dir = hub / ".sync" / "logs"

    card_stats = hub_health.collect_card_stats(hub)
    skill_stats = hub_health.collect_skill_stats(skillhub)
    flywheel_stats = hub_health.count_scripts_run(log_dir)

    print("=" * 50)
    print("  ⚠️ 飞轮自监控告警检查")
    print("=" * 50)

    alerts = hub_health.check_alerts(
        hub, skillhub, card_stats, skill_stats, flywheel_stats,
        alert_days=args.alert_days,
    )

    if alerts:
        print(f"\n共 {len(alerts)} 条告警:\n")
        for alert in alerts:
            level_icon = {"warning": "⚠️", "info": "ℹ️", "critical": "🚨"}.get(alert["level"], "⚠️")
            print(f"  {level_icon} [{alert['rule']}] {alert['message']}")
            if alert.get("suggestion"):
                print(f"     💡 建议: {alert['suggestion']}")
            if alert.get("skills"):
                print(f"     📋 受影响: {alert['skills']}")
    else:
        print("\n✅ 飞轮健康度良好，无告警")

    # 同时输出技能迭代健康度
    print("\n--- 技能迭代健康度 ---")
    summary = skill_iteration.health_summary(skillhub)
    print(f"技能总数: {summary['total']}")
    print(f"状态分布: {summary['status_distribution']}")
    print(f"总复用次数: {summary['total_reuse']}  平均: {summary['avg_reuse']}")

    return 0


def _cmd_router_sync(args) -> int:
    """跨平台路由表双向同步检查（代理 router_sync.py）。"""
    import router_sync

    hub = Path(args.hub_root).resolve()
    skillhub = Path(args.skillhub_root).resolve()

    print("=" * 60)
    print("  🔄 路由表同步检查（router-sync）")
    print("=" * 60)

    hub_md = router_sync.find_hub_router(hub)
    if hub_md:
        print(f"[info] 中枢路由文件: {hub_md}")
    else:
        print("[warn] 未找到中枢路由文件")

    skillhub_yaml = skillhub / "router" / "router.yaml"
    if not skillhub_yaml.is_file():
        print(f"[warn] SkillHub 路由文件不存在: {skillhub_yaml}")

    hub_entries = router_sync.parse_hub_router(hub_md) if hub_md else []
    skillhub_entries = router_sync.parse_skillhub_router(skillhub_yaml)

    report = router_sync.diff_routers(hub_entries, skillhub_entries)
    router_sync.print_report(report)

    if getattr(args, "classification", False):
        router_sync.print_classification_summary(report)

    exit_code = 0

    if getattr(args, "fix", False):
        fixes, msgs = router_sync.apply_fixes(
            skillhub, report, merge_strategy=args.merge_strategy
        )
        print("\n--- 正向修复（中枢 → SkillHub）---")
        for m in msgs:
            print(f"  {m}")
        print(f"共修复 {fixes} 个条目")
        if fixes > 0:
            exit_code = 2

    if getattr(args, "reverse_fix", False):
        rfixes, rmsgs = router_sync.apply_reverse_fix(
            hub, report, merge_strategy=args.merge_strategy
        )
        print("\n--- 反向修复（SkillHub → 中枢）---")
        for m in rmsgs:
            print(f"  {m}")
        print(f"共修复 {rfixes} 个条目")
        if rfixes > 0 and exit_code == 0:
            exit_code = 2

    # 重新读取修复后的状态
    if getattr(args, "fix", False) or getattr(args, "reverse_fix", False):
        hub_entries2 = router_sync.parse_hub_router(hub_md) if hub_md else []
        skillhub_entries2 = router_sync.parse_skillhub_router(skillhub_yaml)
        report2 = router_sync.diff_routers(hub_entries2, skillhub_entries2)
        print("\n--- 修复后状态 ---")
        router_sync.print_report(report2)
        if report2["mismatch"] and exit_code == 0:
            exit_code = 1

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            __import__("json").dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n报告已写入: {args.report}")

    return exit_code


def _cmd_session_preload(args) -> int:
    """会话预加载（代理 session_preload.py）。"""
    import session_preload

    hub = Path(args.hub_root).resolve()
    if not hub.is_dir():
        print(f"错误: 中枢目录不存在: {hub}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  📋 会话预加载（session-preload）")
    print("=" * 60)

    result = session_preload.preload_session(
        hub_root=hub,
        query=args.query,
        top_k=args.top_k,
        max_tokens=args.max_tokens,
    )

    if not result["success"]:
        print(f"❌ 预加载失败: {result.get('error', '未知错误')}", file=sys.stderr)
        return 1

    if args.json:
        output = {
            "query": result["query"],
            "keywords": result["keywords"],
            "total_tokens": result["total_tokens"],
            "cards_count": len(result["cards"]),
            "cards": [
                {
                    "title": c["title"],
                    "type": c["type"],
                    "type_label": c["type_label"],
                    "path": c["path"],
                    "score": c["score"],
                    "value_score": c["value_score"],
                    "summary": c["summary"][:100] if c.get("summary") else "",
                }
                for c in result["cards"]
            ],
        }
        import json as _json
        print(_json.dumps(output, ensure_ascii=False, indent=2))
    elif args.brief_only:
        print(result["brief"])
    else:
        print(result["brief"])
        print()
        print("---")
        print("📊 预加载统计:")
        print(f"   命中卡片: {len(result['cards'])} 张")
        print(f"   预估 tokens: ~{result['total_tokens']}")
        print(f"   关键词: {', '.join(result['keywords'][:3])}")

    return 0


def _cmd_daily_report(args) -> int:
    """生成飞轮日报并推送。

    2026-09-02 Hermes 代办收尾断链修复：原代理 flywheel_daily_report.py
    源码灭失（仅 .pyc，且早于现存 hub_daily_report.py），改 subprocess
    走本目录 hub_daily_report.py（与 8:00 cron 日报同源）；
    hermes 通道改走 `hermes send` CLI（push_channel 模块亦无源码）。
    """
    hub = Path(args.hub_root).resolve()
    skillhub = Path(args.skillhub_root).resolve()

    if not hub.is_dir():
        print(f"错误: 中枢目录不存在: {hub}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  📊 飞轮日报生成与推送")
    print("=" * 60)

    # 生成日报（hub_daily_report 基于 hub-health.json 最新快照，不支持历史回放）
    if args.date:
        from datetime import date as _date
        try:
            _date.fromisoformat(args.date)
        except ValueError:
            print(f"错误: 日期格式错误: {args.date}", file=sys.stderr)
            return 1
        print(
            f"⚠️ --date={args.date} 已忽略：当前日报基于最新快照生成，无历史回放",
            file=sys.stderr,
        )

    gen = subprocess.run(
        [
            sys.executable, "-u", str(_SCRIPT_DIR / "hub_daily_report.py"),
            "--hub-root", str(hub), "--skillhub-root", str(skillhub),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    if gen.returncode != 0:
        print(
            f"❌ 日报生成失败: {(gen.stderr or gen.stdout).strip()[:300]}",
            file=sys.stderr,
        )
        return 1
    report = gen.stdout.strip()

    # 输出
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"📄 日报已保存: {output_path}")

    # 构建推送参数
    push_kwargs = {}
    if args.hermes_target:
        push_kwargs["hermes_target"] = args.hermes_target
    if args.serverchan_key:
        push_kwargs["serverchan_key"] = args.serverchan_key
    if args.pushplus_token:
        push_kwargs["pushplus_token"] = args.pushplus_token
    if args.wecom_webhook:
        push_kwargs["wecom_webhook"] = args.wecom_webhook
    if args.feishu_webhook:
        push_kwargs["feishu_webhook"] = args.feishu_webhook
    if args.push_config:
        push_kwargs["push_config"] = args.push_config

    # 推送（2026-09-02 Hermes 代办断链修复：原依赖的 push_channel 模块无
    # 源码可考，hermes 通道改走 `hermes send` CLI，webhook 通道用 urllib 直发）
    if push_kwargs:
        report_title = f"📊 飞轮日报 ({datetime.now().astimezone().strftime('%Y-%m-%d')})"
        push_results = []

        def _post(url: str, payload: dict) -> dict:
            """POST JSON（wecom/feishu/pushplus 通道通用）。"""
            import json as _json
            import urllib.request

            body = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp.read()
                return {"success": True}
            except Exception as exc:  # 网络/HTTP 错误统一转失败结果
                return {"success": False, "error": str(exc)[:200]}

        if push_kwargs.get("push_config"):
            print(
                "❌ --push-config 暂不可用：原 push_channel 配置文件格式无源码可考，"
                "请改用显式通道参数（--hermes-target/--serverchan-key/...）",
                file=sys.stderr,
            )
            push_kwargs.pop("push_config")

        if push_kwargs.get("hermes_target"):
            target = push_kwargs.pop("hermes_target")
            print(f"📤 正在通过 Hermes 推送到微信 ({target})...")
            try:
                send = subprocess.run(
                    ["hermes", "send", "-t", target, "-"],
                    input=f"{report_title}\n\n{report}",
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=120,
                )
                ok = send.returncode == 0
                if ok:
                    print("  ✅ 推送成功")
                else:
                    err = (send.stderr or send.stdout).strip()[:200]
                    print(f"  ❌ 失败: {err}")
                    if "session timeout" in err:
                        print("  💡 微信会话已过期，请重新认证 Hermes 微信连接")
                push_results.append({"success": ok, "channel": "hermes"})
            except FileNotFoundError:
                print("  ❌ hermes CLI 不在 PATH，跳过", file=sys.stderr)
                push_results.append(
                    {"success": False, "channel": "hermes", "error": "hermes 不可用"}
                )

        if push_kwargs.get("serverchan_key"):
            key = push_kwargs.pop("serverchan_key")
            print("📤 正在推送到 Server酱 (微信)...")
            import urllib.parse
            import urllib.request

            data = urllib.parse.urlencode(
                {"text": report_title, "desp": report}
            ).encode("utf-8")
            try:
                req = urllib.request.Request(
                    f"https://sctapi.ftqq.com/{key}.send", data=data
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    resp.read()
                print("  ✅ 成功")
                push_results.append({"success": True, "channel": "serverchan"})
            except Exception as exc:
                print(f"  ❌ 失败: {str(exc)[:200]}")
                push_results.append(
                    {"success": False, "channel": "serverchan", "error": str(exc)[:200]}
                )

        if push_kwargs.get("pushplus_token"):
            token = push_kwargs.pop("pushplus_token")
            print("📤 正在推送到 PushPlus (微信)...")
            result = _post(
                "http://www.pushplus.plus/send",
                {"token": token, "title": report_title, "content": report},
            )
            result["channel"] = "pushplus"
            print(f"  {'✅ 成功' if result.get('success') else '❌ 失败: ' + result.get('error', '未知')}")
            push_results.append(result)

        if push_kwargs.get("wecom_webhook"):
            webhook = push_kwargs.pop("wecom_webhook")
            print("📤 正在推送到企业微信...")
            result = _post(webhook, {"msgtype": "text", "text": {"content": f"{report_title}\n{report}"}})
            result["channel"] = "wecom"
            print(f"  {'✅ 成功' if result.get('success') else '❌ 失败: ' + result.get('error', '未知')}")
            push_results.append(result)

        if push_kwargs.get("feishu_webhook"):
            webhook = push_kwargs.pop("feishu_webhook")
            print("📤 正在推送到飞书...")
            result = _post(webhook, {"msg_type": "text", "content": {"text": f"{report_title}\n{report}"}})
            result["channel"] = "feishu"
            print(f"  {'✅ 成功' if result.get('success') else '❌ 失败: ' + result.get('error', '未知')}")
            push_results.append(result)

        if push_results:
            success_count = sum(1 for r in push_results if r.get("success"))
            print(f"\n📊 推送汇总: {success_count}/{len(push_results)} 成功")

    if not args.output and not push_kwargs:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
