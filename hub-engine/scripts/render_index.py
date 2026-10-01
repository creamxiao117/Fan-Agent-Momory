# INDEX 渲染器：**卡文件是唯一真相**，本脚本是 INDEX 的**唯一写入者**。
#
# 背景（2026-10-01 裁定，计划 docs/compose/plans/2026-10-01-single-source-l0-shape.md）：
# L0 的 INDEX 枚举行与卡数成正比 → 字符帽永远需要人批（先例 09-23、09-27 两次抬帽）。
# 根治 = 枚举移出 L0、改为**渲染产物**；机器消费方直接扫卡文件（tools/hub_registry）。
#
# 因此：
#   - `INDEX-full.md`  全量分区清单（L2，不参与 L0 预算）
#   - `INDEX.md`       L0 定形能力图（Task 5 起由本脚本渲染，per-card 行 = 0）
#   - 一致性靠门禁：`--check` 与磁盘不一致即非 0（模型同 `ruff format --check`）
#   - 写入唯一入口：`--write`（单写者锁内）
#
# 不做的事：**不替换 INDEX-experience.md**（experience 分册自 09-23 起独立；
# 分册边界见 scripts/index_consistency.INDEX_FILE_FOR_DIR，单一事实源）。
#
# 用法与退出码：
#   python -m scripts.render_index --check    # 0 一致 / 1 派生失败（坏卡）/ 3 不一致
#   python -m scripts.render_index --write    # 0 落盘（锁内）/ 1 派生失败
#   python -m scripts.render_index --report   # 0；迁移期差异分类（不改盘）

from __future__ import annotations

# bootstrap：让此脚本可独立从任何 cwd 调用（外部调度器用绝对路径跑时不能 ModuleNotFoundError）
# 回归背景：2026-09-26 曾因缺引导让 Hermes 任务真挂（见 tests/test_script_bootstrap.py 守护）
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parents[1]))  # hub-engine/

import argparse
from pathlib import Path

from scripts.index_consistency import INDEX_ENTRY_RE, SECTION_TITLES
from tools.hub_registry import CARD_DIRS, CardMeta, RegistryError, hub_root, scan

L0_NAME = "INDEX.md"
FULL_NAME = "INDEX-full.md"
REQUIRED_FILES: tuple[str, ...] = (L0_NAME, FULL_NAME)

# 全量清单覆盖的目录 = **现根 INDEX 枚举的五个权威区**（experience 自 09-23 起
# 独立成 INDEX-experience.md，本渲染器不接管，避免一次改动跨两个分册）。
FULL_DIRS: tuple[str, ...] = tuple(d for d in CARD_DIRS if d != "experience")

_HEADER = """# 中枢索引 · 全量清单（INDEX-full，L2 按需）

> **渲染产物，禁止手工编辑**：由 `python -m scripts.render_index --write` 生成，
> 手改会被 `--check` 打红（模型同 `ruff format --check`）。
> 事实源 = 卡文件自身；语义检索走 `engine.py retrieve` / MCP `hub_search`。
> 经验分册见 `INDEX-experience.md`（同样为 L2）。
"""


def _line(meta: CardMeta) -> str:
    """单条登记行：`- slug    <≤40 字摘要>`（描述取自卡自身，缺摘要时退标题）。"""
    desc = meta.summary or meta.title or "（无摘要）"
    return f"- {meta.slug}    {desc}"


def render_full(cards: list[CardMeta]) -> str:
    """渲染全量清单（五个权威区，按 CARD_DIRS 顺序 + slug 升序，稳定可复现）。"""
    parts = [_HEADER]
    for sub in FULL_DIRS:
        rows = sorted((c for c in cards if c.dir == sub), key=lambda c: c.slug)
        if not rows:
            continue
        parts.append(f"\n{SECTION_TITLES[sub]}\n\n")
        parts.append("\n".join(_line(c) for c in rows))
        parts.append("\n")
    parts.append("\n## 沉淀通道\n\n")
    # 行首**不用 `- `**：非卡片的说明行不得被登记正则解析成条目
    # （历史上根 INDEX 的 `- **各平台内容先写入** …` 就被 audit 当成了幽灵登记）
    parts.append("> 各平台内容先写入 `.sync/drafts/<platform>_draft/`，经同步器校验后提升。\n")
    return "".join(parts)


def render_l0(cards: list[CardMeta]) -> str:
    """渲染 L0 能力图（Task 5 启用）。

    契约：**每个目录 1 行**，示例 slug 内联且 ≤3 个 → 行数与卡数解耦，
    因此 `startup_budget.check_l0_shape()`（禁 per-card 登记行）永不失效。
    """
    raise NotImplementedError("Task 5 启用：L0 定形渲染")


def parse_entries(text: str) -> dict[str, str]:
    """解析 INDEX 文本 → {slug: 描述}（正则复用 index_consistency，不另写一份）。"""
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = INDEX_ENTRY_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def read_indexes(hub: Path) -> dict[str, str]:
    """读现有分册 → {slug: 描述}（合并根 INDEX 与经验分册）。"""
    out: dict[str, str] = {}
    for name in (L0_NAME, "INDEX-experience.md"):
        p = hub / name
        if p.exists():
            out.update(parse_entries(p.read_text(encoding="utf-8-sig", errors="ignore")))
    return out


def check(hub: Path | None = None) -> list[str]:
    """`--check`：渲染产物与磁盘不一致 → 违规消息（空=通过）。"""
    root = Path(hub) if hub is not None else hub_root()
    errs: list[str] = []
    try:
        text = render_full(scan(root))
    except RegistryError as e:
        return [f"派生失败：{e}"]
    target = root / FULL_NAME
    if not target.exists():
        errs.append(f"{FULL_NAME} 不存在（先跑 `--write`）")
    elif target.read_text(encoding="utf-8-sig") != text:
        errs.append(f"{FULL_NAME} 与卡文件不一致（被手改或未重渲染）→ 跑 `--write` 修复")
    return errs


def write(hub: Path | None = None) -> list[str]:
    """`--write`：渲染落盘（单写者锁内）。返回错误列表（空=成功）。"""
    root = Path(hub) if hub is not None else hub_root()
    try:
        text = render_full(scan(root))
    except RegistryError as e:
        return [f"派生失败：{e}"]
    try:
        from sync import _WriteLock
    except ImportError:  # pragma: no cover - 无 sync 环境降级为无锁
        from contextlib import nullcontext as _WriteLock  # type: ignore[assignment]

    with _WriteLock(root):
        (root / FULL_NAME).write_text(text, encoding="utf-8")
    return []


def _classify(old: dict[str, str], new: dict[str, str]) -> dict[str, list[str]]:
    """差异分类（迁移期用）：幽灵 / 未登记 / 摘要漂移（注释型 vs 陈旧型）。

    注释型 = 旧描述以新摘要为前缀（人工追加了 T1/status 后缀）；
    陈旧型 = 卡正文已改、INDEX 行没跟着重建（渲染更正确）。
    """
    both = set(old) & set(new)
    return {
        "ghost": sorted(set(old) - set(new)),
        "unregistered": sorted(set(new) - set(old)),
        "annotated": sorted(s for s in both if old[s] != new[s] and old[s].startswith(new[s])),
        "stale": sorted(s for s in both if old[s] != new[s] and not old[s].startswith(new[s])),
    }


def report(hub: Path | None = None, out=None) -> int:
    """迁移期差异报告：渲染结果 vs 现有手写 INDEX 行（只读，不改盘）。"""
    out = out if out is not None else sys.stdout  # 晚绑定：勿在 import 期固定 stdout（capsys 会失效）
    root = Path(hub) if hub is not None else hub_root()
    try:
        cards = scan(root)
    except RegistryError as e:
        print(f"[FAIL] 派生失败：{e}", file=out)
        return 1
    old = read_indexes(root)
    new = {c.slug: (c.summary or c.title or "（无摘要）") for c in cards}
    diff = _classify(old, new)
    print(f"卡数={len(cards)}  现有登记={len(old)}  渲染行={len(new)}", file=out)
    for key, label in (
        ("ghost", "幽灵登记（旧有/渲染无）"),
        ("unregistered", "未登记（渲染有/旧无）"),
        ("annotated", "摘要漂移·注释型（人工追加后缀）"),
        ("stale", "摘要漂移·陈旧型（卡已改未重建）"),
    ):
        rows = diff[key]
        print(f"\n[{label}] {len(rows)}", file=out)
        for s in rows[:5]:
            if s in old and s in new:
                print(f"   {s}\n     old: {old[s][:60]}\n     new: {new[s][:60]}", file=out)
            else:
                print(f"   {s}", file=out)
        if len(rows) > 5:
            print(f"   …（共 {len(rows)}）", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="INDEX 渲染器（卡文件 → 索引产物）")
    ap.add_argument("--root", type=Path, default=None, help="中枢根（默认仓库内 AgentMemoryHub）")
    ap.add_argument("--check", action="store_true", help="与磁盘不一致 → 退出码 3")
    ap.add_argument("--write", action="store_true", help="渲染落盘（单写者锁内）")
    ap.add_argument("--report", action="store_true", help="迁移期差异分类（只读）")
    args = ap.parse_args(argv)
    if args.report:
        return report(args.root)
    if args.write:
        errs = write(args.root)
        if errs:
            for e in errs:
                print(f"FAIL: {e}")
            return 1
        print(f"[OK] 已渲染 {FULL_NAME}")
        return 0
    # 默认（含 --check）走检查口径
    errs = check(args.root)
    if errs:
        for e in errs:
            print(f"FAIL: {e}")
        return 3
    print(f"PASS: {FULL_NAME} 与卡文件一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
