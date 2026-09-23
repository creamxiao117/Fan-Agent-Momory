#!/usr/bin/env python3
# ⚠️ 一次性脚本（已消费）—— 2026-09-23 加护栏，禁止重跑
#
# 为什么不删而是加护栏：
#   WORK.md 的 T15 曾写明「执行 deduplicate-experience.py」，若不拦，
#   下一个 Agent 会照做并误杀经验卡。
#
# 本脚本的问题（2026-09-23 实测确认）：
#   1. **会误杀**：靠模糊相似度判定重复（标题>0.85 且正文>0.7）。
#      实证：pluginhub-date-range-picker v1.1 / v1.2 实测为 **0.97 / 0.95**，
#      会被判为重复并作废 v1.1——而 **v1.1 藏有 v1.2 没有的 4 条教训**
#      （F811 重复 __init__ / Optional[T] vs T|None / I001 import 排序 / 装饰品 UI），
#      且这些教训未在别处成卡。→ 跑它 = 直接销毁知识。
#   2. **marker 目标推导有 bug**：`keep_file = next((k for k in keep if k.stem in old), None)`
#      找不到就写 `merged into unknown`。实证：本仓
#      `chrome-proxy-...-2026-09-05.md` 上那行 `unknown` 就是它留下的。
#   3. **非幂等**：重跑会重复前置 DEPRECATED 注释。
#   4. 无 dry-run，直接写盘。
#
# 现状：经验去重已用**只读分析 + 人工裁定**完成（见 work/analyze_experience_dupes.py）：
#   220 张中仅一组真重复（ingest-probe-a ≡ cross-repo-index-commit，正文逐字相同）
#   → 已作废；pluginhub v1.1/v1.2 判定为互补、均保留。
#
# 确需再做去重：用 work/analyze_experience_dupes.py 出只读候选清单，逐对人工裁定，
# 再用 `status: deprecated` + `superseded_by` 显式作废。不要复活本脚本。
import sys

_REFUSAL = """\
[REFUSED] deduplicate-experience.py 是一次性脚本，已消费，拒绝执行。

原因：
  1) 靠模糊相似度（标题>0.85 且正文>0.7）会误杀。实测 pluginhub v1.1/v1.2
     为 0.97/0.95 会被判重复——但 v1.1 藏有 v1.2 没有的 4 条教训（且未在别处成卡）。
  2) marker 目标推导有 bug，找不到目标就写 `merged into unknown`。
  3) 非幂等、无 dry-run，直接写盘。

经验去重已完成（只读分析 + 人工裁定）：220 张中仅 1 组真重复，已作废。
如需再做：python work/analyze_experience_dupes.py（只读候选）→ 人工裁定
       → 用 status: deprecated + superseded_by 显式作废。
"""

print(_REFUSAL, file=sys.stderr)
sys.exit(2)

# --- 以下为原始实现，仅作历史留存，永不执行 ---
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
