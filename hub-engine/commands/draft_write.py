# @version V1.0 / 2026-11-02 / pi / CLI 子命令 draft-write（回写闭环的确定性入口）
"""CLI 子命令：`hub draft-write` —— 把会话结论写成**中枢草案卡**。

为什么要有 CLI（而不是让扩展直接调 MCP）
------------------------------------------
pi 扩展**无法直接调用 MCP 工具**（MCP 工具经 `pi-mcp-adapter` 以「模型面向的代理工具」
暴露，扩展拿不到确定性句柄）⇒ 扩展要落盘只能走**中枢 CLI**。
但 CLI 与 MCP **必须共用同一实现**，否则就是两套口径（pi 接入计划 R1「双事实源」要防的正是这个）。

⇒ 本命令是**薄封装**：策略校验（`type ∈ [exp, note, project]`）、平台授权、slug 化、
去重、审计日志**全部**委托 `tools.mcp_handlers.hub_ingest_candidate`。

落点与纪律
----------
- 落点 `<hub>/.sync/drafts/<platform>_draft/<slug>.md`（**根目录**语义 ⇒ `auto_flywheel` 才扫得到；
  子目录 `candidates/` 只统计不提升，见 `auto_flywheel.scan_drafts` docstring）。
- **不写权威区**：贡献者只能写 `exp/note/project`；`rule/methodology` 由 `assert_candidate_type` 拒绝。
- **不做无提炼自动写**：调用方（pi 扩展）必须先给用户**预览并确认**，本命令只负责「按指令落盘」。

用法
----
```bash
python engine.py draft-write --root ../AgentMemoryHub --platform pi \
  --title "标题" --body "正文" --type exp --tags "a,b"
```
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml


def _split_card(text: str) -> tuple[dict, str]:
    """若传入的是**完整卡**（带 frontmatter），拆成 (frontmatter, 正文)。

    为何需要：agent / 人写卡时习惯直接写完整卡（含 `---` 块）；
    若不拆，就会出现**双 frontmatter**（外层 CLI 的 + 内层卡的）⇒ 解析器只认第一层，
    第二层会变成正文里的噪声（实测踩过）。
    """
    t = text.lstrip("\ufeff")
    if not t.startswith("---"):
        return {}, t
    parts = t.split("---", 2)
    if len(parts) < 3:
        return {}, t
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return {}, t
    return (fm if isinstance(fm, dict) else {}), parts[2].strip()


def _auto_slug(title: str, platform: str, type_: str) -> str:
    """标题 → kebab-case slug（ASCII 优先；中文标题给**可读兜底**）。

    为何要自己算（不直接用 `_slugify`）：中枢的 `_slugify` 只保留 ASCII，
    中文标题会被压成 `candidate`（或空）⇒ 所有中文候选撞同一个文件名（靠后缀数字区分）。
    这里补一条：**ASCII 化后不足 4 字符**（典型：纯中文标题）⇒ 用
    `平台-类型-日期-标题短哈希` 兜底，既唯一又可溯源。
    """
    s = re.sub(r"[^a-z0-9-]+", "-", title.lower()).strip("-")[:40]
    if len(s) < 4:
        digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:6]
        s = f"{platform}-{type_}-{date.today().strftime('%Y%m%d')}-{digest}"
    return s


def cmd_draft_write(args) -> int:
    from tools.mcp_handlers import hub_ingest_candidate

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"中枢根不存在：{root}", file=sys.stderr)
        return 1

    body = args.body or ""
    if not body and args.body_file:
        p = Path(args.body_file)
        if not p.is_file():
            print(f"正文文件不存在：{p}", file=sys.stderr)
            return 1
        body = p.read_text(encoding="utf-8")

    # 传入的是**完整卡**时：拆出它的 frontmatter（type/tags 优先用卡里的）
    fm, body = _split_card(body)
    card_type = args.type or str(fm.get("type") or "") or "exp"
    tag_list = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    if not tag_list:
        raw_tags = fm.get("tags")
        if isinstance(raw_tags, list):
            tag_list = [str(t).strip() for t in raw_tags if str(t).strip()]

    tags = tag_list
    slug = args.slug or _auto_slug(args.title, args.platform, card_type)
    res = hub_ingest_candidate(
        root=root,
        platform=args.platform,
        title=args.title,
        body=body,
        type_=card_type,
        tags=tags or None,
        slug=slug,
    )
    print(json.dumps(res, ensure_ascii=False))
    return 0 if res.get("ok") else 1


__all__ = ["cmd_draft_write"]
