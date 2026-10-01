#!/usr/bin/env python3
import shutil
import time
from pathlib import Path

# 本仓路径：由脚本位置推导（原为写死 worktree 绝对路径）
_REPO = Path(__file__).resolve().parents[1]
SOURCE_PATH = _REPO / "AgentMemoryHub" / "rules"
DATE = time.strftime("%Y%m%d")
BACKUP_PATH = _REPO / "AgentMemoryHub" / ".backup" / DATE


def backup_rules():
    BACKUP_PATH.mkdir(parents=True, exist_ok=True)
    files = list(SOURCE_PATH.glob("*.md"))
    print(f"Found {len(files)} rule files")

    total_chars = 0
    for f in files:
        backup_file = BACKUP_PATH / f.name
        shutil.copy2(f, backup_file)
        size = f.stat().st_size
        print(f"  [OK] {f.name}: {size} chars")
        total_chars += size

    manifest = BACKUP_PATH / "manifest.txt"
    # 2026-10-01 修：内层循环变量曾复用 `f`，遮蔽了文件句柄 → AttributeError（脚本直接崩）
    with open(manifest, "w", encoding="utf-8") as mf:
        mf.write(f"Rule files backup ({DATE})\n")
        mf.write("=" * 50 + "\n\n")
        mf.writelines(f"{p.name}: {p.stat().st_size} chars\n" for p in files)
        mf.write(f"\nTotal: {len(files)} files, {total_chars:,} chars\n")

    print(f"\nBackup completed! Location: {BACKUP_PATH}")
    return BACKUP_PATH


if __name__ == "__main__":
    backup_rules()
