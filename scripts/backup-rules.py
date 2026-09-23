#!/usr/bin/env python3
import shutil
import time
from pathlib import Path

SOURCE_PATH = Path(
    r"C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub/rules"
)
DATE = time.strftime("%Y%m%d")
BACKUP_PATH = (
    Path(
        r"C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub/.backup"
    )
    / DATE
)


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
    with open(manifest, "w", encoding="utf-8") as f:
        f.write(f"Rule files backup ({DATE})\n")
        f.write("=" * 50 + "\n\n")
        for f in files:
            f.write(f"{f.name}: {f.stat().st_size} chars\n")
        f.write(f"\nTotal: {len(files)} files, {total_chars:,} chars\n")

    print(f"\nBackup completed! Location: {BACKUP_PATH}")
    return BACKUP_PATH


if __name__ == "__main__":
    backup_rules()
