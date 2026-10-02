"""巡检第 9 步：`hub_audit` 系统性体检（库一致性）。

为什么值得独立成步：现有 8 步各有分工（lint 查单卡、render_check 查派生产物、
reconcile 查平台），但**没有一步**回答这几个跨文件的问题：

- 卡片正文引用的卡**还在不在**（悬空指针 —— 只有交过叉引用才会踩）
- iron 卡是否都绑了执行/度量口径（D7）
- 引擎台账与磁盘是否一致
- 历史上被删的产物是否仍被 L0 文档提到（文档漂移）
- 数据完整性（T1 度量快照还在不在 / 写者锁是否活动残留 / task 装-卸是否未结算）

单卡 lint 天然看不见这些。
"""

from __future__ import annotations

from pathlib import Path

from .core import StepResult


def _step_hub_audit(root: Path, engine_dir: Path) -> StepResult:
    """进程内跑体检（不拉子进程）：exit 语义对齐 —— 有 P0/P1 即 fail。"""
    from scripts.hub_audit import collect

    rep = collect(root)
    p0 = rep.get("P0") or []
    p1 = rep.get("P1") or []
    p2 = rep.get("P2") or []
    status = "fail" if (p0 or p1) else "pass"
    parts = [f"P0={len(p0)} P1={len(p1)} P2={len(p2)}"]
    parts += [f"[P0] {m}" for m in p0[:3]]
    parts += [f"[P1] {m}" for m in p1[:3]]
    parts += [f"[P2·待裁定] {m}" for m in p2[:2]]
    return StepResult(
        name="audit",
        stage="库一致性",
        status=status,
        exit_code=1 if status == "fail" else 0,
        output=" ｜ ".join(parts)[:600],
        meta={"p0": len(p0), "p1": len(p1), "p2": len(p2)},
    )
