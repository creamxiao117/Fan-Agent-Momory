# 卡 frontmatter 字段的**安全写入口**（单一实现）。
#
# 为何独立成模块：2026-10-01 起 `index_desc` / `index_note` / `l1_tier` 等字段会由
# **脚本与 Agent 自动写入**（T1 回写、描述校对、L1 迁移）。手拼 YAML 会踩三类坑：
#   1. 中文冒号/引号/`#` → YAML 解析炸掉或值被截断（实测过：手拼 `index_note: （T1 ✅）` 里
#      的引号会把整行吃掉）；
#   2. BOM：19/655 个历史卡带 BOM，读写用错编码会把 BOM 写丢或写重；
#   3. 换行：Windows 下 `write_text` 默认把 `\n` 翻成 `\r\n`，会造成全文件 EOL 漂移。
# 本模块把这三件事一次做对，所有写方共用。

from __future__ import annotations

from pathlib import Path

import yaml


def yaml_line(key: str, value: str) -> str:
    """生成一行安全的 `key: value`（含中文/引号/冒号也正确引用）。"""
    return yaml.safe_dump(
        {key: value}, allow_unicode=True, default_flow_style=False, width=10**6, sort_keys=False
    ).strip()


def _frontmatter_end(lines: list[str]) -> int:
    seen = 0
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            seen += 1
            if seen == 2:
                return i
    raise ValueError("frontmatter 未闭合（找不到第二个 ---）")


def _value_end(lines: list[str], start: int, end: int) -> int:
    """``start`` 处标量键的**值块**结束行号（不含）。

    YAML 的多行折叠值是「首行 + 缩进续行」**同一个**标量 ⇒ 改写/删除一个键必须整块处理；
    只处理首行会把旧续行留在文件里（值 = 新首行 + 旧续行）。

    续行 = 紧随其后、以空白开头的行；遇到空行或新的顶层键即止。
    """
    i = start + 1
    while i < end:
        ln = lines[i]
        if ln[:1] in (" ", "\t"):
            i += 1
            continue
        break
    return i


def set_fields(path: Path, fields: dict[str, str]) -> None:
    """写入/替换卡 frontmatter 字段（保留 BOM 与换行风格，原地替换已存在键）。"""
    raw = path.read_bytes()
    bom = raw[:3] == b"\xef\xbb\xbf"
    encoding = "utf-8-sig" if bom else "utf-8"
    text = raw.decode(encoding)

    lines = text.splitlines(keepends=True)
    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    end = _frontmatter_end(lines)
    slots: dict[str, int] = {}
    for i, ln in enumerate(lines[:end]):
        for key in fields:
            if ln.startswith(f"{key}:"):
                slots[key] = i

    for key, value in fields.items():
        rendered = yaml_line(key, value) + newline
        if key in slots:
            # ⚑ 旧值可能是**多行折叠**（YAML 折行续行）⇒ 只换首行会把旧续行留在文件里，
            #   值变成「新首行 + 旧续行」⇒ 实测把 index_desc 越写越长（1051 → 1664 字符）
            #   ⇒ 整块替换：首行连同它的续行一起换成新值。
            i = slots[key]
            stop = _value_end(lines, i, end)
            lines[i:stop] = [rendered]
            end -= stop - i - 1
        else:
            lines.insert(end, rendered)
            end += 1
    path.write_text("".join(lines), encoding=encoding, newline="")


def remove_field(path: Path, key: str) -> bool:
    """删除 frontmatter 字段（不存在返回 False）。"""
    raw = path.read_bytes()
    encoding = "utf-8-sig" if raw[:3] == b"\xef\xbb\xbf" else "utf-8"
    lines = raw.decode(encoding).splitlines(keepends=True)
    end = _frontmatter_end(lines)
    for i, ln in enumerate(lines[:end]):
        if ln.startswith(f"{key}:"):
            # 同 set_fields：多行折叠值要**整块**删，否则续行会留在文件里变成野值。
            del lines[i : _value_end(lines, i, end)]
            path.write_text("".join(lines), encoding=encoding, newline="")
            return True
    return False


__all__ = ["remove_field", "set_fields", "yaml_line"]
