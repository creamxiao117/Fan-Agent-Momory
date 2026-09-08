"""hub_safe_patch — MCP 工具：智能文件编辑（patch/write_file 混合，风险自动分级）。

V1.0 (2026-09-09): 改进一 —— safe_patch 集成进 MCP 工具链，
Hermes Agent 可直接调用 hub_safe_patch 而非原生 patch。

调用链路：Agent 调用 hub_safe_patch → 本函数内部调用 safe_patch.py 脚本
→ risk=0 走 patch，risk=1 走 write_file（规避 Hermes patch 缩进 bug）
→ 自动 ruff check + format，出错自动回滚。

用法（MCP 调用）：
    hub_safe_patch(root, path=..., old_string=..., new_string=...,
                   replace_all=False, dry_run=False)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# safe_patch.py 核心逻辑（内联，避免 subprocess 依赖）
MAX_PATCH_LINES = 3
MAX_PATCH_CHARS = 200
RISK_MARKERS = [
    r"^\s*def\s+\w+\s*\(",
    r"^\s*async\s+def\s+\w+\s*\(",
    r"^\s*class\s+\w+",
    r"^\s*@\w+",
    r"^\s*import\s+",
    r"^\s*from\s+\w+\s+import\s+",
    r"^\s*if\s+__name__\s*==",
    r"^\s*try\s*:",
    r"^\s*except\s+",
    r"^\s*with\s+",
    r"^\s*for\s+",
    r"^\s*while\s+",
]


def _detect_indent(line: str) -> int:
    return (len(line) - len(line.lstrip())) // 4


def _assess_risk(old: str, new: str) -> tuple[int, str]:
    old_lines = old.split("\n")
    new_lines = new.split("\n")
    if len(old_lines) > MAX_PATCH_LINES or len(new_lines) > MAX_PATCH_LINES:
        return (
            2,
            f"行数超限（old={len(old_lines)}, new={len(new_lines)}，max={MAX_PATCH_LINES}）",
        )
    for line in old_lines + new_lines:
        for marker in RISK_MARKERS:
            import re as _re

            if _re.match(marker, line):
                return 2, f"含敏感语法：{line.strip()[:50]}"
    for line in old_lines + new_lines:
        if len(line) > MAX_PATCH_CHARS:
            return 2, f"行过长（{len(line)} > {MAX_PATCH_CHARS}）"
    old_indents = [_detect_indent(l) for l in old_lines if l.strip()]
    new_indents = [_detect_indent(l) for l in new_lines if l.strip()]
    if old_indents and new_indents and max(new_indents) > max(old_indents):
        return (
            1,
            f"缩进层数增加（old_max={max(old_indents)}, new_max={max(new_indents)}）",
        )
    if len(old_lines) == 1 and len(new_lines) == 1:
        return 0, "single-line"
    return 1, "multi-line simple"


def _lint(path: Path) -> tuple[int, str]:
    """跑 ruff check --fix && ruff format。返回 (exit_code, output)。"""
    try:
        r1 = subprocess.run(
            ["ruff", "check", "--fix", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        subprocess.run(
            ["ruff", "format", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r1.returncode, r1.stdout + r1.stderr
    except FileNotFoundError:
        return 0, "ruff not installed"


def _do_patch(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def _do_write(path: Path, old: str, new: str, replace_all: bool) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError("old_string not found in file")
    path.write_text(
        text.replace(old, new, -1 if replace_all else 1),
        encoding="utf-8",
    )


def hub_safe_patch(
    root: Path,
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    dry_run: bool = False,
) -> dict:
    """MCP 工具：智能文件编辑，patch/write_file 自动分级。

    Args:
        root: 中枢根路径（本函数内不使用，传参保持 MCP 接口一致）
        path: 目标文件路径（绝对路径或相对路径）
        old_string: 原内容（支持多行）
        new_string: 新内容
        replace_all: 是否全部替换（默认 False，只替换第一个匹配）
        dry_run: 仅评估风险，不实际修改文件

    Returns:
        dict，含 keys: ok, risk, reason, action, path, ruff_rc, ruff_output
    """
    import shutil

    file_path = Path(path).resolve()
    if not file_path.exists():
        return {
            "ok": False,
            "error": f"文件不存在：{file_path}",
            "risk": -1,
            "reason": "file-not-found",
        }

    risk, reason = _assess_risk(old_string, new_string)

    if risk >= 2:
        return {
            "ok": False,
            "risk": risk,
            "reason": reason,
            "action": "refused",
            "suggestion": "请改用 write_file 工具（read_file → 重写 → write_file）",
            "path": str(file_path),
        }

    if dry_run:
        return {
            "ok": True,
            "risk": risk,
            "reason": reason,
            "action": "patch" if risk == 0 else "write_file",
            "path": str(file_path),
            "dry_run": True,
        }

    # 备份
    backup = file_path.with_suffix(file_path.suffix + ".bak-safe_patch")
    shutil.copy2(file_path, backup)

    try:
        if risk == 0:
            ok = _do_patch(file_path, old_string, new_string)
        else:
            _do_write(file_path, old_string, new_string, replace_all)
            ok = True

        if not ok:
            return {
                "ok": False,
                "error": "old_string not found in file",
                "risk": risk,
                "reason": reason,
                "path": str(file_path),
            }

        # 自动 lint
        rc, lint_out = _lint(file_path)
        if rc == 0:
            backup.unlink()
            return {
                "ok": True,
                "risk": risk,
                "reason": reason,
                "action": "patch" if risk == 0 else "write_file",
                "path": str(file_path),
                "ruff_rc": 0,
                "ruff_output": lint_out or "OK",
            }
        else:
            # lint 失败，回滚
            shutil.copy2(backup, file_path)
            backup.unlink()
            return {
                "ok": False,
                "error": f"ruff lint 失败 (exit={rc})",
                "ruff_rc": rc,
                "ruff_output": lint_out,
                "rollback": True,
                "path": str(file_path),
            }

    except Exception as e:
        if backup.exists():
            shutil.copy2(backup, file_path)
            backup.unlink()
        return {
            "ok": False,
            "error": str(e),
            "rollback": True,
            "path": str(file_path),
        }
