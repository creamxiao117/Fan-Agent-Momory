# @version V2.0 / 2026-10-02 / pi / 支持顶部托管块（--top）+ BEGIN/END 标记 + 旧块自愈
"""平台固定指令注入：向各平台规则文件写入"执行前先查中枢"指令（幂等 + 位置自愈）。

V2.0（2026-10-02）：
- 新增 `position="top"`（CLI `--top`）：托管块置于文件**最顶部**。
  依据 `methodology/memory-injection-pattern.md` §2「放最顶部」——项目记忆每次会话注入，
  最顶部最不可能被截断，从而成为"环境级强约束"而非"提醒"。
- 托管块改用 `<!-- BEGIN/END memory-hub-bridge -->` 标记：位置可审计、可整块替换。
- 兼容旧块：旧版以 `## 统一记忆中枢` 开头的无标记块会被识别并整块移除（自愈），
  避免"新旧两块并存"。

为什么需要"顶部"（pi 接入 P0 的裁定）：
  pi 的用户级长期记忆 `AGENTS.md` 已有中枢路径等事实，但**没有**「执行前必须先查」的
  硬约束，且位于文件中部（易被截断）。顶部托管块把"必须查 → 命中进上下文 → 搜不到问用户
  → 收尾回写草案"四步固化为环境级约束。
"""

from __future__ import annotations

from pathlib import Path

MARKER_BEGIN = "<!-- BEGIN memory-hub-bridge"
MARKER_END = "<!-- END memory-hub-bridge -->"
# 旧版（V1.x）无标记块的起始行特征；命中则整块移除（自愈）
LEGACY_MARKER = "## 统一记忆中枢"

INSTRUCTION = """<!-- BEGIN memory-hub-bridge（由 hub-engine/tools/inject.py 维护，勿手改） -->
## 【强制·最高优先级】执行前先查统一记忆中枢

L0 铁律：①单写者锁 + 工作区守护 + ledger 审计 ②执行前先查中枢 ③不确定交回用户、不得臆测、不得捏造经验 ④结果回写。

- 涉及规则/规范/约定/经验/历史踩坑的任务，动手前**必须**先检索中枢：
  MCP `hub_bootstrap` / `hub_search`，或 `python hub-engine/engine.py retrieve --root <hub> "<问题>"`；
  无 MCP 时读 `INDEX.md`（L0 能力图）与五权威区目录。
- 任务分型后按 `AGENTS.md` 路由补读 L1 规则卡（light/code/hub/sync/project，口径 `tools.task_tier`）。
- 命中以「引用+摘要」进任务上下文；规则类命中须读卡全文；正文按用途分级取用（`compress_level`）。
- **搜不到必须交回用户询问**，不得自作主张写新卡；冲突以中枢为准。
- 收尾：可复用结论用 `hub_ingest_candidate` 写草案区（`.sync/drafts/<平台>_draft/`），ingest 归维护者。

中枢位置：{hub}
<!-- END memory-hub-bridge -->"""


def hub_location() -> str:
    """中枢当前绝对路径（由本文件位置动态推导，避免硬编码过期路径）。"""
    return str(Path(__file__).resolve().parents[2] / "AgentMemoryHub")


def _strip_managed(text: str) -> str:
    """移除全部托管块（新标记块 + 旧无标记块），返回剩余内容。

    新块：`<!-- BEGIN ... -->` 到 `<!-- END ... -->` 整段删除。
    旧块：从 `## 统一记忆中枢` 起始行到下一个 `## ` 标题（或文末）删除。
    """
    # 新标记块（可能有零到多个）
    while MARKER_BEGIN in text:
        start = text.index(MARKER_BEGIN)
        end_at = text.find(MARKER_END, start)
        end = len(text) if end_at < 0 else end_at + len(MARKER_END)
        text = text[:start] + text[end:]
    # 旧无标记块（幂等：删除后不再命中）
    lines = text.splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.startswith(LEGACY_MARKER):
            end = i + 1
            while end < len(lines) and not lines[end].lstrip().startswith("## "):
                end += 1
            text = "".join(lines[:i]) + "".join(lines[end:])
            break
    return text


def inject_instruction(target: str | Path, *, position: str = "bottom") -> Path:
    """把托管块写入目标规则文件；已存在且内容一致则跳过，位置/内容过期则整块刷新。

    Args:
        target: 目标规则文件（如 pi 的 `<agent-dir>/AGENTS.md`）。
        position: `"top"` 置顶（pi 用），`"bottom"` 追加到末尾（其他平台既有口径）。
    """
    if position not in ("top", "bottom"):
        raise ValueError(f"position 必须是 top/bottom，收到 {position!r}")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    block = INSTRUCTION.format(hub=hub_location())
    existing = target.read_text(encoding="utf-8") if target.exists() else ""

    body = _strip_managed(existing).strip("\n")
    text = f"{block}\n\n{body}" if position == "top" and body else (f"{body}\n\n{block}" if body else block)
    text = text.rstrip("\n") + "\n"

    if text == existing:  # 幂等：字节级不变才跳过，避免无谓的 mtime 抖动
        return target
    target.write_text(text, encoding="utf-8")
    return target


if __name__ == "__main__":
    import sys

    argv = [a for a in sys.argv[1:] if a != "--top"]
    if not argv:
        sys.exit("用法: python -m tools.inject [--top] <目标规则文件路径>")
    print(f"已注入: {inject_instruction(argv[0], position='top' if '--top' in sys.argv[1:] else 'bottom')}")
