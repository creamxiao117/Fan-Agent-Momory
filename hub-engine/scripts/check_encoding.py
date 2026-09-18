# @version V1.0 / 2026-09-19 / Hermes / 中文文本与路径编码全链路自检脚本
"""编码自检脚本（rules/chinese-text-encoding-discipline 配套）。

功能（四道检查，全部纯标准库、无第三方依赖）：
  1. 文件编码检查：目标文件必须能以 UTF-8 解码（否则报实际编码，如 GBK）
  2. BOM 检查：按扩展名判定 BOM 是否合规（.ps1 必须带 BOM；.py/.md/.json/.yaml 不应带）
  3. 乱码串检查：命中「UTF-8 被 GBK 解码」的概率乱码串（如 闃块噷 / 涓枃 / 锟斤拷）
  4. 中文路径 round-trip：在临时目录下建中文目录 + 中文文件名，写入→读回→逐字符比对

退出码：0 = 全部 PASS；1 = 有 FAIL（可直接进 CI / pre-commit）

用法：
  python hub-engine/scripts/check_encoding.py <文件或目录> [<文件或目录> ...]
  python hub-engine/scripts/check_encoding.py --roundtrip            # 只跑中文路径 round-trip
  python hub-engine/scripts/check_encoding.py --root <中枢> <目录>   # 显式指定扫描目录
"""

from __future__ import annotations

import argparse
import codecs
import sys
import tempfile
from pathlib import Path

# 需要跳过的目录（运行态数据 / 依赖 / 版本控制）
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
}

# 按扩展名的 BOM 期望：True=必须带 BOM，False=不应带 BOM，None=不检查
BOM_EXPECT: dict[str, bool | None] = {
    ".ps1": True,  # PS 5.1 无 BOM 会按 ANSI 解析，中文必爆
    ".py": False,  # BOM 会被部分工具当内容
    ".md": False,
    ".json": False,
    ".yaml": False,
    ".yml": False,
    ".toml": False,
    ".cs": True,  # MSVC 建议 UTF-8 with BOM
    ".vbs": False,  # 但必须纯 ASCII（由乱码/非 ASCII 检查兜底）
}

# 「UTF-8 字节被按 GBK 解码」产生的典型高频字对（出现即可疑）
MOJIBAKE_MARKERS = (
    "闃块",
    "鐧剧",
    "涓枃",
    "鏂囦",
    "锟斤拷",
    "鐨勶",
    "涓€",
    "鏄剧",
    "鍜岃",
    "澶辫触",
    "璺緞",
    "缂栫",
    "鎵ц",
    "涓嶅",
    "鍙パ",
    "銆?",
    "杩囩",
    "鐢熸",
)

# 乱码串豁免：这些文件**按定义**要引用乱码样例（规范文档 / 本脚本），不当 FAIL
MARKER_EXEMPT_NAMES = {"chinese-text-encoding-discipline.md", "check_encoding.py"}

TEXT_EXTS = {
    ".py",
    ".ps1",
    ".bat",
    ".cmd",
    ".vbs",
    ".js",
    ".ts",
    ".cs",
    ".c",
    ".cpp",
    ".h",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".xml",
    ".csv",
}

results: list[tuple[str, str, str]] = []  # (级别, 对象, 说明)


def _record(level: str, target: str, detail: str) -> None:
    results.append((level, target, detail))


def check_file(path: Path) -> None:
    """检查单个文件的编码 / BOM / 乱码串。"""
    ext = path.suffix.lower()
    raw = path.read_bytes()

    # 1) 编码可解性
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        try:
            guess = "GBK/CP936"
            raw.decode("gbk")
        except UnicodeDecodeError:
            guess = "未知（非 UTF-8 也非 GBK）"
        _record("FAIL", str(path), f"非 UTF-8 编码（疑似 {guess}）：{exc}")
        return

    # 2) BOM 期望
    has_bom = raw.startswith(codecs.BOM_UTF8)
    expect = BOM_EXPECT.get(ext)
    if expect is True and not has_bom:
        _record(
            "FAIL",
            str(path),
            f"{ext} 缺少 UTF-8 BOM（PS5.1/MSVC 会按 ANSI 解析，中文必爆）",
        )
    elif expect is False and has_bom:
        _record("WARN", str(path), f"{ext} 含 UTF-8 BOM（建议去除）")

    # 3) 乱码串（规范文档与本脚本自身引用乱码样例，豁免）
    if path.name not in MARKER_EXEMPT_NAMES:
        hits = sorted({m for m in MOJIBAKE_MARKERS if m in text})
        if hits:
            _record("FAIL", str(path), f"疑似 UTF-8→GBK 误解码残留：{', '.join(hits)}")

    # 4) .vbs 非 ASCII（WScript 按 ANSI 解析）
    if ext == ".vbs" and any(ord(ch) > 127 for ch in text):
        _record(
            "FAIL",
            str(path),
            ".vbs 含非 ASCII 字符（WScript 按 ANSI 解析，必须纯 ASCII）",
        )

    _record("PASS", str(path), f"UTF-8 可解，BOM={'有' if has_bom else '无'}")


def iter_files(targets: list[Path]) -> list[Path]:
    """展开目标（文件 / 目录递归），只取文本类扩展名。"""
    out: list[Path] = []
    for t in targets:
        if t.is_file():
            out.append(t)
        elif t.is_dir():
            for p in t.rglob("*"):
                if p.is_file() and p.suffix.lower() in TEXT_EXTS:
                    if any(part in SKIP_DIRS for part in p.parts):
                        continue
                    out.append(p)
        else:
            _record("FAIL", str(t), "路径不存在")
    return sorted(set(out))


def roundtrip_path_test() -> bool:
    """中文目录 + 中文文件名：写入 → 读回 → 逐字符比对。"""
    probe = "结构工程师-C30混凝土-测试.txt"
    payload = "中文内容 round-trip：钢筋 HRB400，f_y=360 MPa。\n"
    try:
        with tempfile.TemporaryDirectory(prefix="enc-check-") as tmp:
            d = Path(tmp) / "中文目录-测试"
            d.mkdir()
            f = d / probe
            f.write_text(payload, encoding="utf-8")
            back = f.read_text(encoding="utf-8")
            names = [p.name for p in d.iterdir()]
            ok = back == payload and names == [probe]
            _record(
                "PASS" if ok else "FAIL",
                "中文路径 round-trip",
                f"目录/文件名回读={'一致' if names == [probe] else names}，内容回读={'逐字符相等' if back == payload else '不一致'}",
            )
            return ok
    except Exception as exc:  # 任何异常都记为 FAIL 并保留原因
        _record("FAIL", "中文路径 round-trip", f"异常：{exc!r}")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="中文文本与路径编码全链路自检")
    parser.add_argument("targets", nargs="*", help="要扫描的文件或目录（可多个）")
    parser.add_argument(
        "--roundtrip", action="store_true", help="只跑中文路径 round-trip 测试"
    )
    args = parser.parse_args(argv)

    if args.roundtrip:
        ok = roundtrip_path_test()
    else:
        files = iter_files([Path(t) for t in args.targets]) if args.targets else []
        for f in files:
            check_file(f)
        ok = roundtrip_path_test()
        if files:
            _record("PASS", "扫描汇总", f"共检查 {len(files)} 个文本文件")

    for level, target, detail in results:
        print(f"[{level}] {target} :: {detail}")

    fails = [r for r in results if r[0] == "FAIL"]
    print(
        f"\n=== 结果：{'PASS' if not fails and ok else 'FAIL'}（FAIL {len(fails)} 项）==="
    )
    return 0 if not fails and ok else 1


if __name__ == "__main__":
    sys.exit(main())
