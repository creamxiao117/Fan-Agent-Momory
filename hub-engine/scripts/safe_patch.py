# @version V1.0 / 2026-09-08 / Hermes / 安全的 patch/write_file 混合工具（规避 patch 工具缩进 bug）
"""safe_patch.py —— 智能文件编辑工具。

V1.0 (2026-09-08): T13.4 用户授权下实施 —— 规避 Hermes patch 工具多行缩进错位 bug。

设计原则（按规则 rules/agent-code-discipline-iron-rule.md）：
- 改动 ≤3 行且不含新增函数/类 → 走原始 patch 算法
- 改动 ≥4 行 / 含函数体变动 / 含 import 块变动 / 缩进层数变化 → 走 write_file 全量重写
- 任何改动后立刻 ruff check + ruff format

用法：
    python safe_patch.py --file PATH --old "OLD" --new "NEW" [--dry-run]
    python safe_patch.py --write PATH [--content FILE]

退出码：
    0 = 成功
    1 = 检测到高风险 → 拒绝执行并提示用 write_file
    2 = patch 实际执行失败
    3 = ruff lint 失败
"""
import argparse
import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAX_PATCH_LINES = 3
MAX_PATCH_CHARS = 200  # 单行 max 字符数

# @version V1.0 / 2026-09-08 / Hermes / 安全的 patch/write_file 混合工具
RISK_MARKERS = [
    r"^\s*def\s+\w+\(",                # 函数定义
    r"^\s*async\s+def\s+\w+\(",       # 异步函数定义
    r"^\s*class\s+\w+",                # 类定义
    r"^\s*@[\w.]+",                    # 装饰器
    r"^\s*import\s+",                  # import 块
    r"^\s*from\s+\w+\s+import\s+",     # from import
    r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]",  # main 块
    r"^\s*try\s*:",                    # try 块
    r"^\s*except\s+",                  # except
    r"^\s*with\s+",                    # with 块
    r"^\s*for\s+",                     # for 块
    r"^\s*while\s+",                   # while 块
]


def detect_indent_level(line: str) -> int:
    """计算缩进层数（每 4 空格 = 1 层）"""
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    return indent // 4


def assess_risk(old: str, new: str) -> tuple[int, str]:
    """评估 patch 风险。返回 (risk_level, reason)。

    risk_level:
        0 = low (可用 patch)
        1 = medium (建议 write_file)
        2 = high (拒绝)
    """
    old_lines = old.split("\n")
    new_lines = new.split("\n")

    # 1. 行数过多
    if len(old_lines) > MAX_PATCH_LINES or len(new_lines) > MAX_PATCH_LINES:
        return 2, f"行数过多（old={len(old_lines)}, new={len(new_lines)}, max={MAX_PATCH_LINES}）"

    # 2. 含敏感关键词（函数定义/import/类）
    for line in old_lines + new_lines:
        for marker in RISK_MARKERS:
            if re.match(marker, line):
                return 2, f"含敏感语法：{line.strip()[:60]}"

    # 3. 单行过长（可能含多行字符串）
    for line in old_lines + new_lines:
        if len(line) > MAX_PATCH_CHARS:
            return 2, f"行过长（{len(line)} > {MAX_PATCH_CHARS} 字符）"

    # 4. 缩进层数变化（关键 bug 触发点）
    old_indents = [detect_indent_level(l) for l in old_lines if l.strip()]
    new_indents = [detect_indent_level(l) for l in new_lines if l.strip()]
    if old_indents and new_indents and max(new_indents) > max(old_indents):
        return 1, f"缩进层数变化：old_max={max(old_indents)}, new_max={max(new_indents)}"

    # 5. 仅一行修改且非敏感 → low risk
    if len(old_lines) == 1 and len(new_lines) == 1:
        return 0, "single line"

    return 1, "multi-line but simple"


def do_patch(file_path: Path, old: str, new: str) -> bool:
    """执行原始 patch（仅 risk=0 时调用）"""
    text = file_path.read_text(encoding="utf-8")
    if old not in text:
        return False
    new_text = text.replace(old, new, 1)
    file_path.write_text(new_text, encoding="utf-8")
    return True


def do_write(file_path: Path, old: str, new: str) -> None:
    """通过 write_file 模拟 patch 行为（先 read，再 replace，再 write）"""
    text = file_path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError("old string not found")
    new_text = text.replace(old, new, 1)
    file_path.write_text(new_text, encoding="utf-8")


def lint_file(file_path: Path) -> tuple[int, str]:
    """跑 ruff check --fix + ruff format。返回 (exit_code, output)"""
    try:
        r1 = subprocess.run(
            ["ruff", "check", "--fix", str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
        subprocess.run(
            ["ruff", "format", str(file_path)],
            capture_output=True, text=True, timeout=30,
        )
        return r1.returncode, r1.stdout + r1.stderr
    except FileNotFoundError:
        return 0, "ruff not installed, skip"


def main():
    parser = argparse.ArgumentParser(description="safe_patch: 智能 patch/write_file 工具")
    parser.add_argument("--file", required=True, help="目标文件路径")
    parser.add_argument("--old", required=True, help="原内容（支持多行）")
    parser.add_argument("--new", required=True, help="新内容")
    parser.add_argument("--dry-run", action="store_true", help="仅评估风险不执行")
    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"[ERR] 文件不存在：{file_path}", file=sys.stderr)
        return 2

    risk, reason = assess_risk(args.old, args.new)
    print(f"[ASSESS] risk={risk} reason={reason!r}")

    if risk >= 2:
        print(
            "[REFUSE] 高风险 patch。请改用 write_file（read_file → 重写 → ruff check + format）。",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(f"[DRY-RUN] 将执行 {'patch' if risk == 0 else 'write_file'} 路径")
        return 0

    # 备份
    backup = file_path.with_suffix(file_path.suffix + ".bak-safe_patch")
    shutil.copy2(file_path, backup)

    try:
        if risk == 0:
            print("[EXEC] patch 路径...")
            if not do_patch(file_path, args.old, args.new):
                print("[ERR] patch 失败：old 未匹配", file=sys.stderr)
                return 2
        else:
            print("[EXEC] write_file 路径（规避 patch bug）...")
            do_write(file_path, args.old, args.new)
        print(f"[OK] 文件已更新：{file_path}")

        # 自动 lint
        rc, out = lint_file(file_path)
        if rc == 0:
            print(f"[LINT] OK\n{out}")
        else:
            print(f"[LINT] FAIL (exit={rc})\n{out}", file=sys.stderr)
            # 回滚
            shutil.copy2(backup, file_path)
            backup.unlink()
            return 3

        backup.unlink()
        return 0

    except Exception as e:
        print(f"[ERR] {e}", file=sys.stderr)
        if backup.exists():
            shutil.copy2(backup, file_path)
            backup.unlink()
        return 2


if __name__ == "__main__":
    sys.exit(main())