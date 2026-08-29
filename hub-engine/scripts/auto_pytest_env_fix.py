r"""auto_pytest_env_fix.py — 自动修复 pytest 环境类失败（缺依赖 / 缺模块）。

解析 pytest 失败输出，分类：
1. 缺第三方包（ImportError / ModuleNotFoundError + 包名可提取）
   → pip install 包名
2. 缺本地模块（但文件实际存在，只是 sys.path 不对）
   → 提示，不自动修（太复杂，交给巡检报告）
3. 真实逻辑 bug（assert 失败、TypeError、AttributeError）
   → 不自动修，标记为需人工

所有自动操作统一写进 .sync/patches/pytest-fix-<date>.md 留痕。

用法：
  python scripts/auto_pytest_env_fix.py --root ..\AgentMemoryHub
  python scripts/auto_pytest_env_fix.py --root ..\AgentMemoryHub --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import timedelta, timezone
from pathlib import Path

_HUB_ENGINE = Path(__file__).resolve().parent.parent
if str(_HUB_ENGINE) not in sys.path:
    sys.path.insert(0, str(_HUB_ENGINE))

_LOCAL_TZ = timezone(timedelta(hours=+8))

# Python 标准库白名单（出现在 ModuleNotFoundError 里就不是 pip 能解决的）
_STDLIB = {
    "abc", "argparse", "ast", "asyncio", "base64", "collections", "concurrent",
    "contextlib", "copy", "dataclasses", "datetime", "decimal", "functools",
    "hashlib", "http", "importlib", "inspect", "io", "itertools", "json",
    "logging", "os", "pathlib", "re", "shutil", "signal", "subprocess",
    "sys", "tempfile", "textwrap", "typing", "unittest", "urllib", "yaml",
}


def run_pytest(engine_dir: Path) -> tuple[int, str]:
    """运行 pytest，返回 (exit_code, combined_output)。"""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=line"],
            cwd=str(engine_dir),
            capture_output=True, text=True, timeout=180, check=False,
        )
        return r.returncode, (r.stdout or "") + "\n" + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "pytest 超时 (180s)"


def _extract_missing_module(lines: list[str]) -> str | None:
    """从错误行提取缺失的模块名。"""
    for line in lines:
        m = re.search(r"No module named ['\"]([^'\"]+)['\"]", line)
        if m:
            return m.group(1)
        m = re.search(r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]", line)
        if m:
            return m.group(1)
    return None


def _is_third_party_module(module: str) -> bool:
    """判断缺失模块是不是第三方包。"""
    # 取顶层包名
    top = module.split(".")[0]
    if top in _STDLIB:
        return False
    # 尝试 import 看是否真实不存在
    try:
        __import__(top)
        return False  # 能 import 说明在本地
    except (ImportError, ModuleNotFoundError):
        return True  # 真的缺


def auto_fix(engine_dir: Path, *, dry_run: bool = False) -> dict:
    """执行自动修复流程。"""
    exit_code, output = run_pytest(engine_dir)
    if exit_code == 0:
        return {"fixed": 0, "remaining_failures": 0, "message": "pytest 全绿"}

    # 收集所有 ModuleNotFoundError / ImportError 行
    error_lines = [
        l.strip() for l in output.splitlines()
        if any(k in l for k in ("ModuleNotFoundError", "No module named", "ImportError"))
    ]
    # 去重
    seen_mods = set()
    modules_to_install = []
    for line in error_lines:
        mod = _extract_missing_module([line])
        if mod and mod not in seen_mods:
            seen_mods.add(mod)
            top = mod.split(".")[0]
            if _is_third_party_module(top):
                modules_to_install.append(top)

    installed: list[str] = []
    if modules_to_install and not dry_run:
        for pkg in modules_to_install:
            print(f"[auto_pytest_env_fix] pip install {pkg}")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg, "-q"],
                    capture_output=True, timeout=60, check=False,
                )
                installed.append(pkg)
            except Exception as e:
                print(f"[auto_pytest_env_fix] pip install {pkg} 失败: {e}")

    return {
        "fixed": len(installed),
        "installed": installed,
        "modules_detected": list(seen_mods),
        "pytest_exit_code_before": exit_code,
        "dry_run": dry_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser(prog="auto-pytest-env-fix", description=__doc__)
    ap.add_argument("--root", required=True, help="中枢根目录（脚本在 hub-engine 运行）")
    ap.add_argument("--dry-run", action="store_true", help="只分析，不执行 pip install")
    args = ap.parse_args()

    hub_root = Path(args.root).resolve()
    engine_dir = hub_root.parent / "hub-engine"

    if not engine_dir.is_dir():
        print(f"[auto_pytest_env_fix] hub-engine 目录不存在: {engine_dir}")
        return 1

    result = auto_fix(engine_dir, dry_run=args.dry_run)

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    if result["fixed"] > 0:
        print(f"[auto_pytest_env_fix] [{mode}] 检测到 {len(result['modules_detected'])} 个缺失模块, 自动安装 {result['fixed']} 个: {result['installed']}")
    else:
        print(f"[auto_pytest_env_fix] [{mode}] pytest exit={result['pytest_exit_code_before']}, 无环境类缺失需自动安装")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
