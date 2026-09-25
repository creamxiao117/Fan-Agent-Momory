# @version V1.0 / 2026-09-19 / Hermes / nightly.log 编码巡检与混合编码回填
"""`.sync/nightly.log` 编码巡检 / 回填工具（rules/chinese-text-encoding-discipline 配套）。

背景（2026-09-19 实证）：
  `nightly_consolidate.cmd` 用 `echo %date% %time%`（中文 locale 输出"周六"）并直接重定向
  python 子进程 stdout —— 两端都按控制台 CP936(GBK) 写出，GBK 字节混进 UTF-8 日志，
  导致 460 行非 ASCII 行**任何单一解码器都读不出**（`utf-8` 解码直接失败）。
  根因已在 .cmd 侧修（chcp 65001 + PYTHONUTF8/PYTHONIOENCODING），本工具负责：
  ① 巡检：当前日志是否还有非 UTF-8 行（复发即报警，可挂每日巡检）
  ② 回填：把历史 GBK 行**逐行**解码后以 UTF-8 重写（可逆操作，先备份）

用法：
  python hub-engine/scripts/nightly_log_encoding_check.py --log <path>            # 只巡检
  python hub-engine/scripts/nightly_log_encoding_check.py --log <path> --repair   # 巡检+回填
退出码：0 = 全 UTF-8（或回填后全 UTF-8）；1 = 仍有不可解行；2 = 文件不存在
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 中文本地化 Windows 的 cmd/PowerShell 时间戳特征（GBK 编码后仍含这些字节序列）
GBK_HINT = (b"\xc9\xcf\xce\xe7", b"\xcf\xc2\xce\xe7", b"\xd6\xdc", b"\xd0\xc7\xc6\xda")


def scan(path: Path) -> tuple[int, int, list[tuple[int, bytes]]]:
    """返回 (总行数, 非 UTF-8 行数, 坏行样本[(行号, 原文字节)])。"""
    data = path.read_bytes()
    lines = data.split(b"\n")
    bad: list[tuple[int, bytes]] = []
    for i, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append((i, raw))
    return len(lines), len(bad), bad


def repair(path: Path) -> tuple[int, int]:
    """逐行：能 UTF-8 解则原样保留；否则按 GBK 解码再以 UTF-8 重写。

    返回 (处理行数, 修复行数)。整份不可解的行按 GBK 解；仍失败的以 errors=replace 兜底。
    写回保持原换行风格，避免二次损伤。
    """
    data = path.read_bytes()
    crlf = data.count(b"\r\n")
    eol = b"\r\n" if crlf > (data.count(b"\n") - crlf) else b"\n"
    out: list[bytes] = []
    fixed = 0
    for raw in data.split(b"\n"):
        body = raw[:-1] if raw.endswith(b"\r") else raw
        if not body.strip():
            out.append(body)
            continue
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = body.decode("gbk")
                fixed += 1
            except UnicodeDecodeError:
                text = body.decode("utf-8", errors="replace")
                fixed += 1
        out.append(text.encode("utf-8"))
    path.write_bytes(eol.join(out))
    return len(out), fixed


def main() -> int:
    ap = argparse.ArgumentParser(description="nightly.log 编码巡检 / 回填")
    ap.add_argument("--log", required=True, help="日志路径，如 AgentMemoryHub/.sync/nightly.log")
    ap.add_argument("--repair", action="store_true", help="把非 UTF-8 行按 GBK 解码后回填为 UTF-8")
    ap.add_argument("--backup-suffix", default=".bak-encoding", help="回填前备份后缀")
    args = ap.parse_args()

    path = Path(args.log)
    if not path.is_file():
        print(f"[FAIL] 日志不存在: {path}")
        return 2

    total, bad, samples = scan(path)
    print(f"扫描 {path}")
    print(f"  总行数 {total} | 非 UTF-8 行 {bad}")
    for ln, raw in samples[:5]:
        hint = " (含中文时间戳特征)" if any(h in raw for h in GBK_HINT) else ""
        try:
            decoded = raw.decode("gbk")
        except UnicodeDecodeError:
            decoded = raw.decode("utf-8", errors="replace")
        print(f"    行{ln}{hint}: 按 GBK 解 -> {decoded[:90]!r}")

    if bad and args.repair:
        bak = path.with_suffix(path.suffix + args.backup_suffix)
        shutil.copy2(path, bak)
        processed, fixed = repair(path)
        _total2, bad2, _ = scan(path)
        print(f"[repair] 备份 {bak.name} | 处理 {processed} 行、修复 {fixed} 行 | 残余非 UTF-8 {bad2}")
        bad = bad2

    if bad:
        print("\n=== 结果：FAIL（仍有非 UTF-8 行；若刚修过 .cmd，请确认 chcp/PYTHONUTF8 已生效）===")
        return 1
    print("\n=== 结果：PASS（全 UTF-8 可解）===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
