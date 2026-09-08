# @version V1.0 / 2026-09-09 / Hermes / DSH 平台桥接脚本
"""dsh_hub_bridge - DSH 平台与中枢文件 Junction 桥接.

V1.0 (2026-09-09): 用范式接入 DSH。
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# DSH 平台配置（从 system/platforms.yaml 读取；硬编码 fallback 便于 DSH 机器上直接跑）
DEFAULT_HUB_ROOT_STR = "C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub"
DSH_PLATFORM = "dsh"
DSH_DRAFT_SUBDIR = "deepseek_draft"


def cmd_status(hub_root: Path) -> int:
    print("=== DSH 中枢状态 ===")
    print(f"中枢根: {hub_root}")
    draft_dir = hub_root / ".sync" / "drafts" / DSH_DRAFT_SUBDIR
    if draft_dir.exists():
        files = list(draft_dir.glob("*.md"))
        print(f"DSH 草稿: {len(files)} 张")
        for f in files:
            print(f"  - {f.name}")
    else:
        print(f"DSH 草稿目录不存在: {draft_dir}")
    key = hub_root / "system" / "keys" / "dsh.key"
    print(f"DSH 签名 key: {'已就绪' if key.exists() else '未初始化'}")
    return 0


def cmd_write(hub_root: Path, title: str, body: str, tags: str = "dsh,bridge") -> int:
    """写 DSH 草稿到 .sync/drafts/deepseek_draft/ 根目录。"""
    draft_dir = hub_root / ".sync" / "drafts" / DSH_DRAFT_SUBDIR
    draft_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    slug = title.replace(" ", "-").lower()[:40]
    out = draft_dir / f"{now}-{slug}.md"
    front_matter = (
        "---\n"
        f"type: note\n"
        f"tags: [{tags}]\n"
        f"updated: {datetime.now(timezone.utc).date().isoformat()}\n"
        f"status: active\n"
        f"source: dsh-platform-bridge V1.0\n"
        f"---\n\n"
    )
    out.write_text(front_matter + body, encoding="utf-8")
    print(f"已写 DSH 草稿: {out.relative_to(hub_root)}")
    return 0


def cmd_sign(hub_root: Path, intent: str, sha: str) -> int:
    """用 platform_sign 签 DSH 的 commit_ledger 条目。"""
    ledger = hub_root / ".sync" / "state" / "commit_ledger.jsonl"
    if not ledger.exists():
        print("ledger 不存在，跳过")
        return 0
    message = f"dsh:{intent}:{sha}".encode()
    key_path = hub_root / "system" / "keys" / "dsh.key"
    if not key_path.exists():
        print("dsh.key 未初始化，先跑 init")
        return 1
    sign_script = (
        hub_root.parent / "hub-engine" / "scripts" / "platform_sign.py"
    )
    sig_proc = subprocess.run(
        [
            sys.executable,
            str(sign_script),
            "sign",
            "--platform",
            DSH_PLATFORM,
            "--payload",
            message.decode("utf-8"),
        ],
        capture_output=True,
        text=True,
    )
    if sig_proc.returncode != 0:
        print(f"签名失败: {sig_proc.stderr}")
        return 1
    signature = sig_proc.stdout.strip()
    entry = {
        "ts": int(datetime.now(timezone.utc).timestamp()),
        "who": DSH_PLATFORM,
        "intent": intent,
        "sha": sha,
        "platform_signature": signature,
    }
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + chr(10))
    print(f"已登记带签名的 ledger: intent={intent}, sha={sha[:8]}")
    return 0


def cmd_check(hub_root: Path) -> int:
    """DSH 接入验证清单（范式步骤 3）。"""
    print("=== DSH 接入验证 ===")
    draft_dir = hub_root / ".sync" / "drafts" / DSH_DRAFT_SUBDIR
    print(f"[{'PASS' if draft_dir.exists() else 'FAIL'}] 草稿目录: {draft_dir.name}")
    files = list(draft_dir.glob("*.md")) if draft_dir.exists() else []
    print(f"[{'PASS' if files else 'WARN'}] 草稿数: {len(files)} 张")
    key = hub_root / "system" / "keys" / "dsh.key"
    print(f"[{'PASS' if key.exists() else 'FAIL'}] 平台签名 key")
    ledger = hub_root / ".sync" / "state" / "commit_ledger.jsonl"
    print(f"[{'PASS' if ledger.exists() else 'FAIL'}] commit_ledger 可访问")
    platforms = hub_root / "system" / "platforms.yaml"
    print(f"[{'PASS' if platforms.exists() else 'FAIL'}] platforms.yaml 注册")
    print("[INFO] DSH 走文件 Junction 接入，不走 MCP（无 hub_search 直接调用）")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="DSH 平台桥接")
    p.add_argument("--hub-root", default=DEFAULT_HUB_ROOT_STR, help="中枢根")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="查 DSH 在中枢的状态")
    sub.add_parser("check", help="范式验证清单")
    w = sub.add_parser("write", help="写 DSH 草稿")
    w.add_argument("--title", required=True)
    w.add_argument("--body", required=True)
    w.add_argument("--tags", default="dsh,bridge")
    s = sub.add_parser("sign", help="为 ledger 条目签名")
    s.add_argument("--intent", required=True)
    s.add_argument("--sha", required=True)
    args = p.parse_args()
    hub = Path(args.hub_root)
    if not hub.exists():
        print(f"中枢根不存在: {hub}")
        return 1
    if args.cmd == "status":
        return cmd_status(hub)
    if args.cmd == "write":
        return cmd_write(hub, args.title, args.body, args.tags)
    if args.cmd == "sign":
        return cmd_sign(hub, args.intent, args.sha)
    if args.cmd == "check":
        return cmd_check(hub)
    return 1


if __name__ == "__main__":
    sys.exit(main())
