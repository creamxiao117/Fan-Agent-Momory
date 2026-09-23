"""平台固定指令注入：向各平台规则文件写入"执行前先查中枢"指令（幂等，随仓库迁移自愈旧路径）"""

from pathlib import Path

INSTRUCTION = """## 统一记忆中枢（AGENT MEMORY HUB）
L0 铁律：① 单写者锁+工作区守护+ledger ② 执行前先查中枢 ③ 不确定交回用户，不得臆测、不捏造历史经验 ④ 结果回写经验卡。
任务分型后按 AGENTS.md 路由读 L1 规则卡（light/code/hub/sync，口径 tools.task_tier）。
细节：MCP hub_bootstrap/hub_search，或 `python hub-engine/engine.py retrieve --root {hub} "<问题>"`；无 MCP 读 INDEX.md 目录版。
命中「引用+摘要」进任务上下文；规则类再 hub_get/读卡全文（compress_level 分级取用仍有效）。
冲突以中枢为准；闭环 hub_ingest_candidate 回写候选。
中枢位置：{hub}
"""


def hub_location() -> str:
    """中枢当前绝对路径（由本文件位置动态推导，避免硬编码过期路径）。"""
    return str(Path(__file__).resolve().parents[2] / "AgentMemoryHub")


def inject_instruction(target: str | Path) -> Path:
    """把固定指令写入目标规则文件；已存在且位置正确则跳过，位置过期则整块刷新。返回目标文件。"""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    block = INSTRUCTION.format(hub=hub_location())
    if not target.exists():
        target.write_text(block, encoding="utf-8")
        return target
    text = target.read_text(encoding="utf-8")
    marker = "## 统一记忆中枢"
    if marker not in text:
        with open(target, "a", encoding="utf-8") as f:
            f.write(("\n" if text.strip() else "") + block)
        return target
    if block.splitlines()[-1] in text:
        return target  # 幂等：已存在且中枢位置一致
    # 中枢位置过期：删除旧指令块（marker 行至下一个标题或文末）后重写最新指令
    lines = text.splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if ln.startswith(marker))
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith("## "):
        end += 1
    head = "".join(lines[:start]).rstrip()
    with open(target, "w", encoding="utf-8") as f:
        f.write((head + "\n\n" + block) if head else block)
    return target


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        sys.exit("用法: python -m tools.inject <目标规则文件路径>")
    print(f"已注入: {inject_instruction(sys.argv[1])}")
