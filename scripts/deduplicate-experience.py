#!/usr/bin/env python3
# Deduplicate experience files
import hashlib
from difflib import SequenceMatcher
from pathlib import Path

EXP_PATH = Path(
    r"C:/Users/Fan-SJSS/.trae-cn/worktrees/20260817-Fan-Agent-Momory/feat-implement-plan-ZilBmv/AgentMemoryHub/experience"
)


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def fingerprint(content):
    return hashlib.md5(content[:500].encode("utf-8")).hexdigest()


def deduplicate():
    print("=" * 60)
    print("Deduplicate Experience Files")
    print("=" * 60)

    files = list(EXP_PATH.glob("*.md"))
    print(f"Found {len(files)} experience files")

    duplicates = []
    keep = []
    remove = []
    fingerprints = {}

    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            content = fp.read()

        title = f.stem
        fp_hash = fingerprint(content)

        # Check duplicates
        is_dup = False
        for existing_fp, existing_file in fingerprints.items():
            if fp_hash == existing_fp:
                # Same content, keep the one with longer filename
                if len(f.name) > len(existing_file.name):
                    keep.append(f)
                    remove.append(existing_file)
                else:
                    keep.append(existing_file)
                    remove.append(f)
                duplicates.append((existing_file, f))
                is_dup = True
                break
            elif similarity(title, Path(existing_file).stem) > 0.85:
                # Similar title, check content manually
                with open(existing_file, "r", encoding="utf-8") as ef:
                    existing_content = ef.read()
                if similarity(content, existing_content) > 0.7:
                    keep.append(f)
                    remove.append(existing_file)
                    duplicates.append((existing_file, f))
                    is_dup = True
                    break

        if not is_dup:
            fingerprints[fp_hash] = f

    # Write deprecation markers
    for f in remove:
        with open(f, "r", encoding="utf-8") as fp:
            old = fp.read()
        with open(f, "w", encoding="utf-8") as fp:
            keep_file = next((k for k in keep if k.stem in old), None)
            marker = f"<!-- DEPRECATED: merged into {keep_file.name if keep_file else 'unknown'} -->\n\n"
            fp.write(marker + old)
        print(f"[OK] Deprecated: {f.name}")

    print("=" * 60)
    print(f"Total duplicates found: {len(duplicates)}")
    print(f"Files deprecated: {len(remove)}")
    print(f"Files kept: {len(keep)}")
    return True


if __name__ == "__main__":
    deduplicate()
