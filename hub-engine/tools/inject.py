"""平台固定指令注入：向各平台规则文件写入"执行前先查中枢"指令（幂等）"""
from pathlib import Path

INSTRUCTION = """## 统一记忆中枢（AGENT MEMORY HUB）
执行前先查统一记忆中枢：读取 INDEX.md 与 rules / experience，命中再执行；
不确定的内容交回用户，不得臆测、不得凭空捏造历史经验。
中枢位置：D:\\AIwork\\AgentMemoryHub
"""


def inject_instruction(target: str | Path) -> Path:
    """把固定指令追加到目标规则文件；已存在则跳过。返回目标文件。"""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and "统一记忆中枢" in target.read_text(encoding="utf-8"):
        return target
    block = ("\n" if target.exists() else "") + INSTRUCTION
    with open(target, "a", encoding="utf-8") as f:
        f.write(block)
    return target


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        sys.exit("用法: python -m tools.inject <目标规则文件路径>")
    print(f"已注入: {inject_instruction(sys.argv[1])}")
