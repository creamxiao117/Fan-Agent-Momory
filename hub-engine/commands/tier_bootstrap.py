# @version V1.0 / 2026-10-02 / pi / CLI 子命令 tier-bootstrap（会话级确定性预取入口）
"""CLI 子命令：`hub tier-bootstrap` —— 会话级预取（分型 → 检索 → 现成引导块）。

用途：给 agent 侧（如 pi 扩展 `memory-hub.ts`）一个**确定性预取入口**：一次进程调用
完成「任务分型 + 按型检索 + 生成可直接注入的 Markdown」。

契约（不得偏离）：
- **与 MCP `hub_bootstrap` 共用同一 handler** ⇒ 同审计、同 reuse 计数、同 policy，
  不新增任何检索实现。这是"避免出现第二套检索口径"的硬要求（pi 侧不复制中枢知识）。
- `light` 型短路：`skipped=true`、`markdown=""`、**不写审计**（不污染检索统计）。
- 分型知识一律来自 `tools/task_tier`（唯一事实源）；本模块**不含**任何子区字面量。

用法：
  python engine.py tier-bootstrap --root <hub> --context "<用户首条消息>" [--platform pi] \
      [--top-k 3] [--compress-level 1] [--tier code] [--json]

输出（--json）：{ok, tier, task_tier, scope[], skipped, blocks[], markdown, hit_count, audit_id, elapsed_ms}
退出码：0 = 成功（含 light 短路）；1 = 参数/中枢错误
"""

import json
import sys
import time
from pathlib import Path

# 让 commands/ 子包能 import tools/ scripts/ common/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.mcp_handlers import hub_bootstrap  # noqa: E402
from tools.task_tier import classify, resolve_kind, scope_for  # noqa: E402


def cmd_tier_bootstrap(args) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"中枢根不存在：{root}", file=sys.stderr)
        return 1

    t0 = time.perf_counter()
    # --tier 可强制指定（供 /hub 手动命令与调试）；否则按 context 关键词判定
    tier = args.tier or str(classify(args.context or ""))
    res = hub_bootstrap(
        root,
        task_tier=tier,
        context=args.context or "",
        platform=getattr(args, "platform", "pi") or "pi",
        top_k=getattr(args, "top_k", 3) or 3,
        compress_level=getattr(args, "compress_level", 1) or 0,
    )
    payload = {
        **res,
        "tier": resolve_kind(tier),
        "scope": list(scope_for(tier)),
        "hit_count": res.get("hit_count", 0),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(
            f"[tier] {payload['tier']}  scope={payload['scope']}  "
            f"hits={payload['hit_count']}  {payload['elapsed_ms']}ms"
            + ("  (skipped: light 不检索)" if payload.get("skipped") else "")
        )
        if payload.get("markdown"):
            print(payload["markdown"])
    return 0
