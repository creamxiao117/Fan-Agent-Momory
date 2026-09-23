# @version V1.0 / 2026-09-23 / pi / fix_orphans V2.0 测试（合并 register_missing_index 后）

"""`fix_orphans` V2.0 单测。

合并背景：本仓曾有 `fix_orphans.py`（清单驱动）与 `register_missing_index.py`
（自动检测）两份做同一件事的脚本。V2.0 合并为一个，并：
- 复用 `post_ingest_hook.extract_summary` / `append_to_index`（公共实现，单一来源）
- 修 `_exists_in_index` 的**子串误判**：`f"- {slug}" in text` 会让 slug `foo`
  被 `- foobar` 误判为已登记 → 静默漏登
- 改为默认 dry-run
"""

from pathlib import Path

from scripts.fix_orphans import detect_missing, main, registered_slugs


def _index(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "INDEX.md"
    p.write_text(body, encoding="utf-8")
    return p


def _card(root: Path, rel: str, title: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "---\ntype: rule\ntags:\n- a\nupdated: 2026-09-23\nstatus: active\n---\n\n"
        f"# {title}\n",
        encoding="utf-8",
    )
    return p


def test_registered_slugs_parses_lines(tmp_path):
    idx = _index(tmp_path, "## 规则（rules/）\n- alpha    描述一\n- beta    描述二\n")
    assert registered_slugs(idx) == {"alpha", "beta"}


def test_registered_slugs_ignores_bold_note_lines(tmp_path):
    """加粗行不是卡登记，而是注释行——真实 INDEX 里唯一加粗行就是这种：
    `- **各平台内容先写入** .sync/drafts/<platform>_draft/，…`

    权威正则 `audit_index.INDEX_ENTRY_RE` 的 slug 字符集不含 `*`，故加粗天然不匹配。
    （曾有一段时间 experience 分区有 4 条**加粗式卡登记**，已由 regen_index_desc
    规范化为普通形式；契约以 audit 为准。）
    """
    idx = _index(
        tmp_path,
        "## 规则（rules/）\n- **各平台内容先写入** 说明文字\n- alpha    描述\n",
    )
    assert registered_slugs(idx) == {"alpha"}


def test_registered_slugs_does_not_prefix_match(tmp_path):
    """回归：`- alphabeta` 不得被当成 `alpha` 已登记（原实现用子串匹配，会静默漏登）"""
    idx = _index(tmp_path, "## 规则（rules/）\n- alphabeta    长度更长的另一个 slug\n")
    got = registered_slugs(idx)
    assert "alphabeta" in got
    assert "alpha" not in got, "短 slug 不应被子串匹配误判为已登记"


def test_registered_slugs_ignores_legend_lines(tmp_path):
    """目录图例行（`- rules/  说明`）不是卡登记"""
    idx = _index(
        tmp_path, "## 规则（rules/）\n- rules/        权威规则说明\n- alpha    描述\n"
    )
    assert registered_slugs(idx) == {"alpha"}


def test_detect_missing_finds_unregistered_authority_cards(tmp_path):
    root = tmp_path / "hub"
    _card(root, "rules/alpha.md", "Alpha 规则")
    _card(root, "rules/beta.md", "Beta 规则")
    _card(root, "experience/gamma.md", "Gamma 经验")  # 非权威区，不参与
    idx = _index(root, "## 规则（rules/）\n- alpha    Alpha 规则\n")
    missing = {p.stem for p in detect_missing(root, idx)}
    assert missing == {"beta"}, f"应只报 beta，实际: {missing}"


def test_detect_missing_consults_both_index_files(tmp_path):
    """回归：已登记于是**任一** INDEX 文件的 slug 都算已登记。

    否则已搬到分册的条目（或错位登记的）会被误报为未登记 → 重复补登。
    """
    root = tmp_path / "hub"
    _card(root, "rules/alpha.md", "Alpha 规则")
    _index(root, "## 规则（rules/）\n")
    # alpha 登记在**分册**里（错位登记）——仍应被认为“已登记”，不再重复加入
    (root / "INDEX-experience.md").write_text(
        "## 经验（experience/）\n- alpha    Alpha 规则\n", encoding="utf-8"
    )
    assert {p.stem for p in detect_missing(root)} == set()


def test_experience_is_out_of_scope(tmp_path):
    """**设计边界**：本工具只扫权威区（rules/methodology/longterm/projects/blueprints），
    **不扫 experience**（非权威区）——experience 的登记由 post_ingest_hook 负责。

    故：此处即使 experience 卡未登记，也不应被本工具报出。
    """
    root = tmp_path / "hub"
    _card(root, "experience/gamma.md", "Gamma 经验")
    _index(root, "## 规则（rules/）\n")
    assert detect_missing(root) == [], "experience 不在权威区扫描范围"


def test_main_dry_run_does_not_write(tmp_path, capsys):
    root = tmp_path / "hub"
    _card(root, "rules/alpha.md", "Alpha 规则")
    idx = _index(root, "## 规则（rules/）\n")
    before = idx.read_text(encoding="utf-8")
    rc = main(["--root", str(root)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dry-run" in out
    assert idx.read_text(encoding="utf-8") == before, "dry-run 不得写盘"


def test_main_apply_registers_and_is_idempotent(tmp_path, capsys):
    root = tmp_path / "hub"
    _card(root, "rules/alpha.md", "Alpha 规则")
    _card(root, "methodology/beta.md", "Beta 方法论")
    idx = _index(root, "## 规则（rules/）\n\n## 方法论（methodology/）\n")

    assert main(["--root", str(root), "--apply"]) == 0
    text = idx.read_text(encoding="utf-8")
    assert "- alpha" in text
    assert "- beta" in text
    capsys.readouterr()

    # 二次运行：应报 0 待补登（幂等）
    assert main(["--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "待补登: 0" in out, f"应幂等，实际输出: {out}"
