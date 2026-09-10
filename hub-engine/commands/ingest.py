# @version V1.0 / 2026-09-07 / Hermes / hub CLI 子命令 ingest（engine.py P1 拆分）
"""CLI 子命令：`hub ingest` 对应的业务实现（从 engine.py V1.0 拆出）。

V1.0 (2026-09-07): engine.py P1 拆分原样搬入，行为零变化。
"""

import sys
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_ingest(args) -> int:
    import subprocess

    from common.config import load_engine_config
    from engine import chat, smart_chat  # lazy: 避免循环导入
    from sync import ingest

    cfg = load_engine_config()
    batch_model = str(cfg.get("batch_model", "") or "").strip()
    chat_fn = (lambda prompt, root: smart_chat(prompt, root)) if batch_model else chat
    stat = ingest(
        Path(args.root),
        args.platform,
        chat_fn=chat_fn,
        strict_lint=getattr(args, "strict_lint", False),
    )
    # T2 (2026-09-07): 把 L1 lint 软门禁的 errors 直接打印（标红）
    lint_errs = stat.get("lint_errors") or []
    if lint_errs:
        print(
            f"  [L1 门禁] {len(lint_errs)} 张草稿不合规（软告警，{'-strict' if stat.get('status') == 'lint_blocked' else '继续 ingest'}）:"
        )
        for e in lint_errs[:5]:
            print(f"    - {e['name']}: {e['errors'][:2]}")
        if len(lint_errs) > 5:
            print(f"    ... 还有 {len(lint_errs) - 5} 张（省略）")
    print(stat)

    # T1 (2026-09-07): ingest 成功后自动跑 post_ingest_hook 同步 INDEX.md
    # 解耦设计：hook 失败不阻塞 ingest（独立 commit/独立回退），可通过 --no-index 跳过
    if stat.get("status") == "ok" and not getattr(args, "no_index", False):
        moved = stat.get("moved", 0)
        promoted = stat.get("promoted", 0)
        if (moved + promoted) > 0:
            moved_names = stat.get("moved_names", []) + stat.get("promoted_names", [])
            if moved_names:
                hook_py = (
                    Path(__file__).resolve().parent.parent
                    / "scripts"
                    / "post_ingest_hook.py"
                )
                python_exe = sys.executable
                try:
                    r = subprocess.run(
                        [
                            python_exe,
                            str(hook_py),
                            "--root",
                            str(args.root),
                            "--names",
                            ",".join(moved_names),
                        ],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=60,
                    )
                    if r.returncode == 0:
                        for line in r.stdout.splitlines():
                            print(f"  [hook] {line}")
                    else:
                        print(
                            f"  [hook WARN] exit={r.returncode}: {r.stderr.strip()[:200]}",
                            file=sys.stderr,
                        )
                except Exception as e:
                    print(f"  [hook WARN] {type(e).__name__}: {e}", file=sys.stderr)

    return 0 if stat["status"] == "ok" else 1
