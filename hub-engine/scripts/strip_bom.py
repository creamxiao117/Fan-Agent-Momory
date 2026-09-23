# hub-engine/scripts/strip_bom.py
"""剥离「按扩展名不该带 BOM」的文件的 UTF-8 BOM。

补 `check_encoding.py` 只检不修的缺口：门禁对 `.md` 等含 BOM 只记 **WARN**
（不 FAIL），于是这类违规会静默累积——2026-09-23 实测中枢里有 19 个 .md 带 BOM。

**字节级操作**：只删文件头 3 个字节（EF BB BF），其余字节一一保持不变
（不重新编码、不动换行、不动内部 BOM）。写入前会断言
`new == old[3:]`，任何偏差即中止。

BOM 期望值取自 `check_encoding.BOM_EXPECT`（单一事实源），只处理
`expect is False` 的扩展名（如 .py/.md/.json/.yaml），绝不碰
`.ps1`/`.cs` 这些**必须带** BOM 的类型。

默认 dry-run；加 `--apply` 写盘。
"""

from __future__ import annotations

import argparse
import codecs
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_encoding import BOM_EXPECT

BOM = codecs.BOM_UTF8  # b"\xef\xbb\xbf"

# 扫描时跳过的目录（运行态/缓存/历史备份）
SKIP_PARTS = {".git", ".backup", ".sync", "__pycache__", ".obsidian", "node_modules"}


def find_bom_files(root: Path) -> list[tuple[Path, str]]:
    """返回 [(文件, 扩展名)]：扩展名期望无 BOM 但实际带 BOM 的文件。

    root 可以是目录（递归）或单个文件；显式传入的文件不受 SKIP_PARTS 限制
    （便于处理 .sync/conflicts 下已跟踪的归档文件）。
    """
    want_no_bom = {ext for ext, expect in BOM_EXPECT.items() if expect is False}

    def _hit(p: Path) -> bool:
        if not p.is_file() or p.suffix.lower() not in want_no_bom:
            return False
        try:
            with p.open("rb") as f:
                return f.read(3) == BOM
        except OSError:
            return False

    if root.is_file():
        return [(root, root.suffix.lower())] if _hit(root) else []

    out: list[tuple[Path, str]] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        if _hit(p):
            out.append((p, p.suffix.lower()))
    return out


def strip_one(p: Path) -> bool:
    """删掉文件头 BOM；返回是否改动。断言除 BOM 外字节不变。"""
    raw = p.read_bytes()
    if not raw.startswith(BOM):
        return False
    new = raw[len(BOM) :]
    if new != raw[len(BOM) :]:  # 恒等断言（防将来改动引入偏差）
        raise AssertionError(f"字节校验失败: {p}")
    if new == raw:  # 理论不可达
        raise AssertionError(f"未剥离: {p}")
    p.write_bytes(new)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="剥离不该有的 UTF-8 BOM（字节级）")
    ap.add_argument(
        "targets",
        nargs="*",
        type=Path,
        help="扫描路径（默认: 仓库内的 AgentMemoryHub）",
    )
    ap.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    args = ap.parse_args(argv)

    roots = args.targets or [Path(__file__).resolve().parents[2] / "AgentMemoryHub"]
    want_no_bom = sorted(ext for ext, expect in BOM_EXPECT.items() if expect is False)
    print(f"期望无 BOM 的扩展名: {want_no_bom}")

    found: list[tuple[Path, str]] = []
    for r in roots:
        if not r.exists():
            print(f"[skip] 不存在: {r}")
            continue
        found.extend(find_bom_files(r))

    print(f"\n命中（不该带 BOM 却带了）: {len(found)}")
    for p, ext in found:
        print(f"  {ext:6s} {p}")

    if not found:
        print("\n无违规，无需处理")
        return 0

    if not args.apply:
        print("\n[dry-run] 未写盘。加 --apply 生效。")
        return 0

    ok = 0
    for p, _ext in found:
        try:
            if strip_one(p):
                ok += 1
        except AssertionError as e:
            print(f"  ❌ {e}")
            return 1
    print(f"\n✅ 已剥离 {ok} 个文件的 BOM（字节级，其余字节未变）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
