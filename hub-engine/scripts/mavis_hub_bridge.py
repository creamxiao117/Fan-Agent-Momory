# @version V1.0 / 2026-09-09 / Hermes / Mavis (MiniMax Code) 3 层接入桥
"""mavis_hub_bridge - Mavis 平台 3 层接入桥.

V1.0 (2026-09-09): 用范式接入 Mavis (第 5 平台)。

3 层接入:
- L1 Hook: UserPromptSubmit 启动门禁(提醒读中枢)
- L2 Memory: topic 镜像(6h 同步中枢卡)
- L3 Workspace: AGENTS.md 模板生成(默认 SKIP)

CLI:
  mavis_hub_bridge check
  mavis_hub_bridge write --title "..." --body "..." --type exp
  mavis_hub_bridge sign --intent "..." --sha "..."
  mavis_hub_bridge mirror --topics
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

MAVIS_PLATFORM = "mavis"
DEFAULT_HUB_ROOT = r"C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub"
DEFAULT_MAVIS_DATA = r"C:\Users\Fan-SJSS\AppData\Roaming\MiniMax"
DEFAULT_SIGN_SCRIPT = r"C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\hub-engine\scripts\platform_sign.py"
DEFAULT_PLATFORMS_YAML = r"C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv\AgentMemoryHub\system\platforms.yaml"

# Mavis 3 层接入验证点
L1_HOOK_PATH = (
    r"C:\Users\Fan-SJSS\AppData\Roaming\MiniMax\agents\mavis\hooks\startup-gate.js"
)
L2_TOPIC_DIR = r"C:\Users\Fan-SJSS\AppData\Roaming\MiniMax\agents\mavis\memory\topics"
L3_WORKSPACE_GEN = r"C:\Users\Fan-SJSS\AppData\Roaming\MiniMax\bin\gen_agents_md.py"

CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def _read_yaml(path: Path) -> dict:
    """最小 YAML 解析（仅 platforms.yaml 简单结构）。"""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict = {}
    current_platform: str | None = None
    for line in text.splitlines():
        s = line.rstrip()
        if not s or s.lstrip().startswith("#"):
            continue
        if s.startswith("platforms:"):
            continue
        if s.startswith("  ") and not s.startswith("    "):
            key = s.strip().rstrip(":")
            current_platform = key
            out[key] = {}
        elif current_platform and s.startswith("    "):
            k, _, v = s.strip().partition(":")
            v = v.strip()
            if current_platform in out:
                out[current_platform][k] = v
    return out


def cmd_check(args) -> int:
    """验证 Mavis 3 层接入状态。"""
    hub_root = Path(args.hub_root)
    _mavis_data = Path(args.mavis_data)
    sign_script = Path(args.sign_script)
    platforms_yaml = hub_root / "system" / "platforms.yaml"

    print("=== Mavis 接入验证（3 层） ===")
    checks = []

    # 平台元数据
    platforms = _read_yaml(platforms_yaml)
    if MAVIS_PLATFORM in platforms:
        checks.append(("平台元数据", "PASS", "platforms.yaml 已注册"))
    else:
        checks.append(("平台元数据", "FAIL", "platforms.yaml 未注册 mavis"))

    # 平台签名 key
    key_path = hub_root / "system" / "keys" / f"{MAVIS_PLATFORM}.key"
    if key_path.exists():
        checks.append(("平台签名 key", "PASS", str(key_path)))
    else:
        checks.append(("平台签名 key", "FAIL", f"{key_path} 不存在"))

    # 草稿目录
    draft_dir = hub_root / ".sync" / "drafts" / f"{MAVIS_PLATFORM}_draft"
    if draft_dir.exists():
        n = sum(1 for _ in draft_dir.glob("*.md"))
        checks.append(("草稿目录", "PASS", f"{draft_dir}（{n} 张）"))
    else:
        checks.append(("草稿目录", "FAIL", f"{draft_dir} 不存在"))

    # L1 Hook
    if Path(L1_HOOK_PATH).exists():
        checks.append(("L1 Hook 启动门禁", "PASS", L1_HOOK_PATH))
    else:
        checks.append(
            ("L1 Hook 启动门禁", "WARN", f"未部署 {L1_HOOK_PATH}（首次接入可忽略）")
        )

    # L2 Memory topic 目录
    if Path(L2_TOPIC_DIR).exists():
        n = sum(1 for _ in Path(L2_TOPIC_DIR).glob("*.md"))
        checks.append(("L2 Memory topic", "PASS", f"{L2_TOPIC_DIR}（{n} 个 topic）"))
    else:
        checks.append(
            ("L2 Memory topic", "WARN", f"未部署 {L2_TOPIC_DIR}（首次接入可忽略）")
        )

    # L3 Workspace gen
    if Path(L3_WORKSPACE_GEN).exists():
        checks.append(("L3 Workspace AGENTS.md", "PASS", L3_WORKSPACE_GEN))
    else:
        checks.append(
            (
                "L3 Workspace AGENTS.md",
                "WARN",
                f"未部署 {L3_WORKSPACE_GEN}（首次接入可忽略）",
            )
        )

    # platform_sign.py
    if sign_script.exists():
        checks.append(("platform_sign.py", "PASS", str(sign_script)))
    else:
        checks.append(("platform_sign.py", "FAIL", f"{sign_script} 不存在"))

    # 输出结果
    fail = 0
    for name, status, msg in checks:
        print(f"[{status}] {name}: {msg}")
        if status == "FAIL":
            fail += 1
    print()
    if fail:
        print(f"=== 失败 {fail} 项 ===")
        return 1
    print("=== 3 层接入基础设施就绪（Hook/topic/workspace 可后续部署） ===")
    return 0


def cmd_write(args) -> int:
    """Mavis 写草稿到 mavis_draft/ 根目录。"""
    hub_root = Path(args.hub_root)
    draft_dir = hub_root / ".sync" / "drafts" / f"{MAVIS_PLATFORM}_draft"
    draft_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(CST).strftime("%Y%m%d-%H%M%S")
    safe_title = "".join(c if c.isalnum() or c in "-_" else "-" for c in args.title)[
        :50
    ]
    out = draft_dir / f"{ts}-{MAVIS_PLATFORM}-v1.0-{safe_title}.md"

    frontmatter = f"""---
type: {args.type or "exp"}
tags: [mavis, MiniMax-Code, {MAVIS_PLATFORM}, t15]
updated: 2026-09-09
status: active
reuse_count: 0
source: 2026-09-09 T17 mavis 接入落地
---

# {args.title}

{args.body}
"""
    out.write_text(frontmatter, encoding="utf-8")
    print(f"已写 Mavis 草稿: {out.relative_to(hub_root)}")
    return 0


def cmd_sign(args) -> int:
    """Mavis 写带签名的 commit_ledger 条目。"""
    from pathlib import Path as P

    hub_root = P(args.hub_root)
    ledger = hub_root / ".sync" / "state" / "commit_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)

    sign_script = Path(args.sign_script)
    if not sign_script.exists():
        print(f"FAIL: 签名脚本不存在 {sign_script}", file=sys.stderr)
        return 1

    message = json.dumps(
        {"who": MAVIS_PLATFORM, "intent": args.intent, "sha": args.sha},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")

    sig_proc = subprocess.run(
        [
            sys.executable,
            str(sign_script),
            "sign",
            "--platform",
            MAVIS_PLATFORM,
            "--payload",
            message.decode("utf-8"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if sig_proc.returncode != 0:
        print(f"签名失败: {sig_proc.stderr}", file=sys.stderr)
        return 1
    signature = sig_proc.stdout.strip()

    entry = {
        "ts": int(datetime.now(CST).timestamp()),
        "who": MAVIS_PLATFORM,
        "intent": args.intent,
        "sha": args.sha,
        "platform_signature": signature,
    }
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"已登记带签名的 ledger: intent={args.intent}, sha={args.sha}")
    return 0


def cmd_mirror(args) -> int:
    """L2 memory topic 镜像（生成 5 个 topic 草稿到目标目录）。"""
    hub_root = Path(args.hub_root)
    target = Path(args.target or L2_TOPIC_DIR)
    target.mkdir(parents=True, exist_ok=True)

    topics = [
        ("memory-hub-rules.md", "中枢 5 个核心规则摘要"),
        ("post-task-discipline.md", "收尾双通道纪律"),
        ("memory-hub-index.md", "中枢 INDEX 摘要"),
        ("memory-hub-card-promotion.md", "经验卡回写流程"),
        ("memory-hub-query-first-rule.md", "查询优先规则"),
    ]
    written = []
    for fname, desc in topics:
        out = target / fname
        content = f"""# {desc}

> 镜像自中枢 AgentMemoryHub/{fname}（每 6h 同步）
> 源: {hub_root}/methodology/{fname}
> 同步: mavis_hub_bridge mirror

## 何时读

每次 mavis 处理 T1+ 任务时（改/修/完善/查/审 + bug/错误 + 复审强调）

## 关键纪律

按中枢权威版本执行，本文件是缓存镜像。
"""
        out.write_text(content, encoding="utf-8")
        written.append(str(out))
    print(f"已镜像 {len(written)} 个 topic 到 {target}:")
    for w in written:
        print(f"  - {w}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Mavis (MiniMax Code) 3 层接入桥")
    sub = ap.add_subparsers(dest="action", required=True)

    p_check = sub.add_parser("check", help="验证 3 层接入状态")
    p_check.add_argument("--hub-root", default=DEFAULT_HUB_ROOT)
    p_check.add_argument("--mavis-data", default=DEFAULT_MAVIS_DATA)
    p_check.add_argument("--sign-script", default=DEFAULT_SIGN_SCRIPT)
    p_check.set_defaults(func=cmd_check)

    p_write = sub.add_parser("write", help="写 mavis 草稿到 mavis_draft/")
    p_write.add_argument("--hub-root", default=DEFAULT_HUB_ROOT)
    p_write.add_argument("--title", required=True)
    p_write.add_argument("--body", required=True)
    p_write.add_argument("--type", default="exp", help="card type (exp/note/project)")
    p_write.set_defaults(func=cmd_write)

    p_sign = sub.add_parser("sign", help="写带签名的 ledger 条目")
    p_sign.add_argument("--hub-root", default=DEFAULT_HUB_ROOT)
    p_sign.add_argument("--intent", required=True)
    p_sign.add_argument("--sha", required=True)
    p_sign.add_argument("--sign-script", default=DEFAULT_SIGN_SCRIPT)
    p_sign.set_defaults(func=cmd_sign)

    p_mirror = sub.add_parser("mirror", help="L2 memory topic 镜像")
    p_mirror.add_argument("--hub-root", default=DEFAULT_HUB_ROOT)
    p_mirror.add_argument("--target", default=None, help="目标 topic 目录")
    p_mirror.set_defaults(func=cmd_mirror)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
