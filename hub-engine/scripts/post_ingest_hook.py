# @version V1.0 / 2026-09-07 / Hermes / ingest 后置 hook：自动同步 INDEX.md
"""post_ingest_hook：ingest 完成后扫描 memory_diff.jsonl 找本轮新增/移动的卡，
按 type → INDEX.md 对应小节末尾追加一行。

设计要点（实测背景）：
- ingest 已写 `.sync/state/memory_diff.jsonl`，每条记录形如：
    {"op": "add", "name": "x.md", "type": "exp", "before": null,
     "after": "experience/x.md", "ts": 1234567890}
- hook 从 jsonl 倒序读，跳过 ts < since_ts 的 entry，只处理本轮
- 首跑：since_ts 不传 → 处理整个 diff 文件（兼容幂等）
- 失败不阻塞 ingest：独立进程 + 独立 try/except
- INDEX.md 用 section 标题锚定（与 INDEX.md 现行结构完全一致）
"""

from __future__ import annotations

# bootstrap：让此脚本可独立从任何 cwd 调用（不依赖外部 sys.path 设置）
import sys
from pathlib import Path as _P

_THIS = _P(__file__).resolve().parent
sys.path.insert(0, str(_THIS.parent))  # hub-engine/

import argparse
import json
import logging
import os
import re
import subprocess
from pathlib import Path

_LOG = logging.getLogger(__name__)

# 分区表收敛到 scripts/index_consistency.py（单一事实源，2026-09-23）
# 本地曾自持一份 SECTION_TITLES（与 fix_orphans / fix_index_registry 各存一份→共 3~4 份），
# 拆分 INDEX 后 experience 目标文件变了却只改一处 → 出现“卡被追加回根 INDEX”的 bug。
# 故此处改为导入契约模块：表与目标文件选择同源。
from scripts.index_consistency import SECTION_TITLES as _TITLES
from scripts.index_consistency import index_file_for_dir

# type → 分区标题（在契约表的目录键基础上补两个 type 别名）
SECTION_TITLES = {
    **_TITLES,
    "exp": _TITLES["experience"],  # 非权威区 type 也登记 INDEX
    "note": _TITLES["experience"],  # 注释类合并入经验区
    "retro": "## 沉淀通道",  # retro 是 append-only 留痕，不入主索引
}


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    cmd = ["git", "-C", str(repo), *args]
    r = subprocess.run(
        cmd, check=True, capture_output=True, text=True, encoding="utf-8", env=env
    )
    return r.stdout or ""


def read_diff_since(
    root: Path, since_ts: float | None, max_records: int = 200
) -> list[dict]:
    """读 memory_diff.jsonl，过滤本轮新增（before is None）的 add/move 记录。

    安全保护：不传 since_ts 时只取最近 max_records 条，防止历史污染 INDEX。
    """
    diff = root / ".sync" / "state" / "memory_diff.jsonl"
    if not diff.exists():
        return []
    lines = diff.read_text(encoding="utf-8", errors="ignore").splitlines()
    if since_ts is None and len(lines) > max_records:
        # 仅扫描尾部，避免历史 diff 大量污染
        lines = lines[-max_records:]
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if since_ts is not None and rec.get("ts", 0) < since_ts:
            continue
        if rec.get("op") not in ("add", "move"):
            continue  # delete / 等其他操作不登记 INDEX
        out.append(rec)
    return out


# 样板标题：这些 H1 是写作规范要求的固定小标题，不是内容摘要，
# 直接返回会得到 4 字符垃圾描述（如「结论先行」）→ 必须继续找下一段实质内容。
_BOILERPLATE_HEADINGS = {"结论先行", "一句话结论", "摘要", "概述", "结论", "背景"}

# 摘要默认上限（INDEX 传更小的帽；见 scripts/regen_index_desc.py）
_SUMMARY_MAX = 80

# 子句边界字符：只收录**真正的子句终止/分隔号**。
# 不收 `：`——引导符，切在其后会得到 `仅 4 字段：` 悬空摘要；
# 不收 `）】」』`——它们只闭合标签/括注，不是子句结束，切在其后会得到
# `【迭代闸门】` 这类只剩标签的碎片（均实测踩到）。
_BOUNDARY_CHARS = "。！？；，、…"

# 括号对：窗口内有**不闭合**的开括号时，宁可切在开括号之前，
# 也不要截出 `任务收尾经验蒸馏纪律（rules: memory-hub-distill-la…` 这种半截括注。
_OPEN_BRACKETS = "（([【「『"
_CLOSE_BRACKETS = "）)]】」』"

# 正文中不作为摘要候选的行首（表格/代码围栏/HTML 注释）
_SKIP_PREFIXES = ("|", "```", "<!--", ">")


def cut_at_boundary(text: str, max_len: int) -> str:
    """把 text 压到 max_len 以内，优先在**子句边界**断开；确实截断才补省略号。

    2026-09-23 新增：此前上游用 `desc[:N]` 硬切，INDEX 里出现 `GitHub 仓库选…`
    这类读不懂的半截词（实测 239/251 条）。摘要必须可读。

    不变量：返回值长度 **≤ max_len**（省略号计入帽内）。
    """
    text = text.strip()
    if max_len <= 0 or len(text) <= max_len:
        return text

    def _with_ellipsis(body: str) -> str:
        """补省略号，并保证含省略号也不超帽"""
        body = body.rstrip()
        if len(body) >= max_len:
            body = body[: max_len - 1].rstrip()
        return body + "…"

    window = text[:max_len]
    # 优先：窗口内存在不闭合的开括号 → 切在开括号之前（整段括注宁可不写）
    for i in range(len(window) - 1, -1, -1):
        if window[i] in _OPEN_BRACKETS and not any(
            c in _CLOSE_BRACKETS for c in window[i:]
        ):
            cut = window[:i].rstrip()
            if cut:
                return cut
    # 其次：从右往左找最近的边界字符，切在其后（自然断句，无需省略号）
    for i in range(len(window) - 1, -1, -1):
        if window[i] in _BOUNDARY_CHARS:
            cut = window[: i + 1].rstrip()
            if cut:
                return cut
    # 最后：退到最近的空格（中英混排），否则硬切
    sp = window.rstrip().rfind(" ")
    if sp > max_len * 0.5:
        return _with_ellipsis(window[:sp])
    return _with_ellipsis(window)


def _clean(text: str) -> str:
    """去掉 markdown 修饰符，得到纯文本摘要。

    注意：**不去下划线**——`speech_input` 这类标识符里的 `_` 不是 markdown 强调符，
    删掉会损坏内容（2026-09-23 实测：旧实现删 `_` 使索引标题变成 speechinput）。
    """
    return re.sub(r"[*`#\[\]]", "", text).strip()


def extract_summary(card_path: Path, max_len: int = _SUMMARY_MAX) -> str:
    """从卡正文提取一句话描述。

    策略：跳过样板标题后返回**第一个实质标题或段落**——本仓卡片的写作规范就是
    把「一句话结论」放在样板标题之下，故该段落即卡自身的摘要（比机械截断旧描述可靠）。

    2026-09-23 修正：读取改 `utf-8-sig`。此前用 `utf-8`，文件带 BOM 时首行是
    `\ufeff---`，`s == "---"` 判定失败 ⇒ 整个函数返回空 ⇒ 该卡在 INDEX 无描述
    （实测 19/655 个 .md 带 BOM，全部命中此坑）。
    """
    if not card_path.exists():
        return ""
    text = card_path.read_text(encoding="utf-8-sig", errors="ignore")
    fm_end_count = 0
    for line in text.splitlines():
        s = line.strip()
        if fm_end_count < 2:
            if s == "---":
                fm_end_count += 1
            continue
        if not s or s.startswith(_SKIP_PREFIXES):
            continue
        if s.startswith("#"):
            title = s.lstrip("#").strip()
            if title in _BOILERPLATE_HEADINGS:
                continue  # 样板标题 → 继续找实质内容
            if s.startswith("# "):
                return cut_at_boundary(_clean(title), max_len)
            continue  # ## 级小标题跳过
        return cut_at_boundary(_clean(s), max_len)
    return ""


def append_to_index(
    index_path: Path, section_title: str, slug: str, summary: str
) -> bool:
    """在指定 section 末尾（下一个 ## 之前）追加一行；幂等：已存在则跳过。"""
    text = index_path.read_text(encoding="utf-8")
    if f"- {slug}    " in text or f"- {slug}  " in text:
        return False
    lines = text.splitlines(keepends=True)
    in_section = False
    section_end_idx = len(lines)
    for i, line in enumerate(lines):
        if line.startswith(section_title):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            section_end_idx = i
            break
    if not in_section:
        return False  # section 不存在，不擅自创建
    summary_clean = summary.replace("\n", " ").strip()
    new_line = f"- {slug}    {summary_clean}\n"
    lines.insert(section_end_idx, new_line)
    index_path.write_text("".join(lines), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(prog="post_ingest_hook")
    ap.add_argument("--root", required=True)
    ap.add_argument(
        "--since-ts",
        type=float,
        default=None,
        help="只处理 ts >= since_ts 的 diff；默认 = None（处理整个文件）",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印候选，不实际改 INDEX.md / commit",
    )
    ap.add_argument(
        "--names",
        default="",
        help="本轮 ingest 涉及的卡名清单（逗号分隔）；优先于 diff 扫描，避免历史污染",
    )
    args = ap.parse_args()
    root = Path(args.root)
    index_path = root / "INDEX.md"
    if not index_path.exists():
        print(f"INDEX.md 不存在: {index_path}", file=sys.stderr)
        return 2
    # 注：根 INDEX 只用于前置存在性检查；实际写入目标由
    #     index_consistency.index_file_for_dir() 按卡所在目录决定
    #     （experience → INDEX-experience.md）。
    # 优先使用 ingest 传入的精确清单（防历史污染 INDEX）
    target_names = [n.strip() for n in args.names.split(",") if n.strip()]
    if target_names:
        # 直接从权威区目录读这 N 张卡（不走 diff 扫描）
        diffs = []
        for name in target_names:
            # 找文件位置：先查权威区，再查 experience，再查 .sync
            found = None
            for sub in [
                "rules",
                "methodology",
                "blueprints",
                "longterm",
                "projects",
                "experience",
                "notes",
            ]:
                p2 = root / sub / name
                if p2.exists():
                    found = p2
                    break
            if found is None:
                continue
            # 解析 type：从 frontmatter 读取
            try:
                from common.frontmatter import read_card

                card = read_card(found)
                diffs.append(
                    {
                        "name": name,
                        "type": card.type,
                        "after": str(found.relative_to(root)).replace(os.sep, "/"),
                    }
                )
            except Exception as e:
                _LOG.warning("post_ingest_hook: 跳过卡片 %s 解析失败: %s", name, e)
                continue
    else:
        diffs = read_diff_since(root, args.since_ts)
    if not diffs:
        print("post_ingest_hook: 本轮无新增卡", file=sys.stderr)
        return 0
    planned: list[tuple[str, str, str]] = []
    for rec in diffs:
        card_type = rec.get("type", "")
        after = rec.get("after", "")
        if not after or not card_type:
            continue
        if after.startswith(".sync/"):  # 跳过 pending/conflicts
            continue
        section_title = SECTION_TITLES.get(card_type)
        if not section_title:
            continue
        slug = Path(rec["name"]).stem
        card_path = root / after
        summary = extract_summary(card_path)
        # 按卡所在目录选**目标 INDEX 文件**（2026-09-23 修）：experience 已拆到
        # INDEX-experience.md（L2），不能再追加回根 INDEX（会白涨 L0）。
        rel_dir = after.split("/")[0]
        target_name = index_file_for_dir(rel_dir) or "INDEX.md"
        planned.append((target_name, section_title, slug, summary))
    if args.dry_run:
        print(f"post_ingest_hook dry-run: 计划登记 {len(planned)} 张")
        for tn, st, slug, sm in planned:
            print(f"  → {tn} | {st} | {slug} | {sm[:60]}")
        return 0
    added = []
    written_files: set[str] = set()
    for target_name, section_title, slug, summary in planned:
        if append_to_index(root / target_name, section_title, slug, summary):
            added.append(slug)
            written_files.add(target_name)
    if not added:
        print(
            "post_ingest_hook: 无 INDEX 变更（可能已存在或无匹配 section）",
            file=sys.stderr,
        )
        return 0
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "AgentMemoryHub"
    env["GIT_AUTHOR_EMAIL"] = "hub@local"
    env["GIT_COMMITTER_NAME"] = "AgentMemoryHub"
    env["GIT_COMMITTER_EMAIL"] = "hub@local"
    try:
        # 暂存**实际写入过的**索引文件：此前硬编码只 add INDEX.md，
        # 在 experience 拆到分册后 → 分册的改动从未被暂存 ⇒ commit 无内容 ⇒ 报错退出。
        # （同一 bug 类的第二处：写入路由改了，暂存路径没改）
        git(root, "add", *sorted(written_files), env=env)
        msg = f"docs(INDEX): post_ingest_hook 自动登记 {len(added)} 张新卡"
        git(root, "commit", "-m", msg, env=env)
    except RuntimeError as e:
        print(f"commit 失败: {e}", file=sys.stderr)
        return 3
    print(
        f"post_ingest_hook: 已登记 {len(added)} 张 → {added}（已提交 {sorted(written_files)}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
