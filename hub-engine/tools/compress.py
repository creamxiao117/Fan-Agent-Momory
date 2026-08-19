"""渐进内容压缩（内化自 paulpas/agent-skill-router 路径C，0-10 级缩为 0-5 级）。

给「检索返回/注入」端按用途取不同压缩级省 token，直连 context-budget 纪律。
原则：
- 保护块永远保留：YAML frontmatter（含路由元数据/反触发）与围栏代码块（可执行代码不可损）。
- 用占位符先把保护块抽走，prose 上跑阶梯，再原位还原 → 保护块即使落在被丢弃 section 内也不丢。
- 失败降级：任何异常回退原稿，绝不丢数据（调用方语义安全）。
- 注入语义分级沿用：选路看高级(如 4/5)、审计看 0 级（原文放 sidecar 已含）。

level 阶梯（cumulative）：
  0  原文
  1  折叠连续空行（>=2 空行压成 1）
  2  丢弃「负路由/反模式」section（不适用/禁止命中/避免/别做）
  3  + 丢弃「引用/来源」section（引用/参考/来源/refs/reference）
  4  + 丢弃「示例/用法/流程」section（示例/样例/example/用法/流程/步骤/how to）→ 只留核心知识+头
  5  摘要模式：只留 `#` 标题 + 其后首个非空段落（首个 `##`+ heading 前）
"""

from __future__ import annotations

import re

_MAX_LEVEL = 5

# 按 level 递增的忽略词表（命中并丢弃该 heading 标题下的整段 section）
_LV2 = ("不适用", "禁止命中", "避免", "别做")
_LV3 = _LV2 + ("引用", "参考", "来源", "refs", "reference", "credit")
_LV4 = _LV3 + ("示例", "样例", "example", "用法", "流程", "步骤", "how to")
_NEEDLES = ("", "", _LV2, _LV3, _LV4, ())  # index = level

_PROT_HEAD = "\ue000PROT_"  # 占位符前缀（private-use char，既非 # 开头也非空行，剥离时不当作 heading/空行）

_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_FRONT_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def _is_protected(line: str) -> bool:
    return line.strip().startswith(_PROT_HEAD)


def _head_depth(line: str) -> int:
    n = 0
    for ch in line:
        if ch == "#":
            n += 1
        else:
            break
    return n


def _is_heading(line: str) -> bool:
    return line.lstrip().startswith("#") and _head_depth(line) > 0


def _fold_blank(lines: list[str]) -> list[str]:
    out: list[str] = []
    blank = 0
    for ln in lines:
        if _is_protected(ln) or ln.strip() != "":
            blank = 0
            out.append(ln)
        else:
            blank += 1
            if blank <= 1:
                out.append(ln)
    return out


def _drop_sections(lines: list[str], needles) -> list[str]:
    """丢弃以命中关键词 heading 为首的整段 section；保护占位行不受影响地保留。"""
    if not needles:
        return lines
    out: list[str] = []
    dropping = False
    drop_depth = 0
    low = tuple(s.lower() for s in needles)
    for ln in lines:
        if _is_protected(ln):
            out.append(ln)  # 保留落在被丢弃 section 内的保护块
            continue
        if _is_heading(ln):
            depth = _head_depth(ln)
            text = ln.lstrip("#").strip().lower()
            if any(k in text for k in low):
                dropping, drop_depth = True, depth
                continue
            if dropping and depth <= drop_depth:
                dropping = False
                drop_depth = 0
            out.append(ln)
            continue
        if dropping:
            continue
        out.append(ln)
    return out


def _summary(lines: list[str]) -> list[str]:
    """摘要：保留 `#` 标题 + 首个非空段落，遇到首个 `##`+ heading 截断（保护块仍保留）。"""
    out: list[str] = []
    seen_title = False
    hit_next_head = False
    pending_intro: list[str] = []
    for ln in lines:
        if _is_protected(ln):
            out.append(ln)  # 保护块始终保留
            continue
        if hit_next_head:
            continue  # 首个 ##+ 之后的 prose 丢弃（保护块已在上行保留）
        if _is_heading(ln):
            if _head_depth(ln) == 1 and not seen_title:
                seen_title = True
                out.append(ln)
            elif seen_title:
                # 首个二级+标题：保留它（作摘要结束标志），之后再丢弃 prose
                hit_next_head = True
                out.append(ln)
            else:
                out.append(ln)
            continue
        if seen_title:
            if ln.strip() == "" or pending_intro:
                out.append(ln)
            else:
                pending_intro.append(ln)
                out.append(ln)
        else:
            out.append(ln)
    return out


def _protect(text: str) -> tuple[str, dict[str, str]]:
    """抽走 frontmatter 与围栏代码块，换成占位符；返回 (占位文本, {token: 原内容})。"""
    tokens: dict[str, str] = {}
    n = 0

    def _gen(kind: str, original: str) -> str:
        nonlocal n
        tok = f"{_PROT_HEAD}{kind}{n}"
        n += 1
        tokens[tok] = original
        return tok

    # 先抽 frontmatter（在最前），再抽代码块
    m = _FRONT_RE.match(text)
    if m:
        text = _FRONT_RE.sub(_gen("FM", m.group(0)), text, count=1)
    text = _CODE_RE.sub(lambda mm: _gen("CB", mm.group(0)), text)
    return text, tokens


def _restore(text: str, tokens: dict[str, str]) -> str:
    for tok, orig in tokens.items():
        text = text.replace(tok, orig)
    return text


def compress_card_text(text: str, level: int = 0, max_level: int = _MAX_LEVEL) -> str:
    """把卡片正文按 level 渐进压缩；任何异常一律回退原稿（调用方语义安全）。"""
    try:
        lv = min(max(0, int(level if level is not None else 0)), max_level)
        if lv <= 0 or not text:
            return text
        prose, tokens = _protect(text)
        lines = prose.split("\n")
        if lv >= 1:
            lines = _fold_blank(lines)
        for lv_i in range(2, min(lv, 4) + 1):
            lines = _drop_sections(lines, _NEEDLES[lv_i])
        if lv >= 5:
            lines = _summary(lines)
        return _restore("\n".join(lines), tokens)
    except Exception:  # noqa: BLE001 - 压缩是可选加速，任何异常都放回原稿
        return text
