"""post_ingest_hook.extract_summary 单测：样板标题不得被当摘要返回。

背景：卡片按写作规范以 `# 结论先行` / `# 一句话结论` 作为 H1，旧实现直接返回该
标题 → INDEX 描述退化成 4 字符「结论先行」，触发 audit「描述过短」告警。
"""

from pathlib import Path

from scripts.post_ingest_hook import extract_summary, main


def _card(p: Path, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntype: exp\ntags:\n- a\n---\n\n{body}", encoding="utf-8")
    return p


def test_boilerplate_heading_falls_through_to_paragraph(tmp_path):
    p = _card(tmp_path / "a.md", "# 结论先行\n\n把域名强制 DIRECT 会导致登录失败。\n")
    got = extract_summary(p)
    assert got == "把域名强制 DIRECT 会导致登录失败。"
    assert len(got) > 4


def test_one_line_conclusion_boilerplate_skipped(tmp_path):
    p = _card(tmp_path / "b.md", "# 一句话结论\n\nX 与 Y 的因果关系。\n")
    assert extract_summary(p) == "X 与 Y 的因果关系。"


def test_real_h1_title_is_returned(tmp_path):
    p = _card(tmp_path / "c.md", "# PluginHub 注册卡：speech_input\n\n正文段落\n")
    assert extract_summary(p) == "PluginHub 注册卡：speech_input"


def test_h2_skipped_then_paragraph(tmp_path):
    p = _card(tmp_path / "d.md", "## 小标题\n\n段落文本。\n")
    assert extract_summary(p) == "段落文本。"


def test_missing_file_returns_empty(tmp_path):
    assert extract_summary(tmp_path / "nope.md") == ""


# ── main() 编排层（2026-09-25 SPLIT2 补网：拆分前 main 无测试）────────────────


def test_main_missing_index_returns_2(tmp_path):
    """根 INDEX 不存在 → 退出码 2（不静默成功）"""
    assert main(["--root", str(tmp_path)]) == 2


def test_main_no_new_cards_returns_0(tmp_path):
    """没有新增卡 → 退出码 0 且不打 commit"""
    (tmp_path / "INDEX.md").write_text("# idx\n", encoding="utf-8")
    assert main(["--root", str(tmp_path)]) == 0


def test_main_dry_run_plans_named_card(tmp_path, capsys):
    """--names 分支 + --dry-run：只规划不写盘（经验卡应路由到分册）"""
    (tmp_path / "INDEX.md").write_text("# idx\n", encoding="utf-8")
    _card(tmp_path / "experience" / "x.md", "# 标题\n\n摘要段落。\n")
    assert main(["--root", str(tmp_path), "--names", "x.md", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "x" in out
    # 未写盘（dry-run 不碰文件；且不调 git）
    assert not (tmp_path / "INDEX-experience.md").exists()


# ---------- 2026-09-26 单数 type 别名修复（漏登记 INDEX）----------


def _typed_card(p: Path, ctype: str, body: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntype: {ctype}\ntags:\n- a\n---\n\n{body}", encoding="utf-8")
    return p


def test_section_titles_covers_all_type_dir():
    """防漏登记：sync.TYPE_DIR 的全部 card.type（含单数 rule/blueprint/project）
    必须都能映射到 INDEX 分区标题，否则 hook 对该 type 静默 `continue`（2026-09-26 缺陷）。"""
    from scripts.post_ingest_hook import SECTION_TITLES
    from sync import TYPE_DIR

    missing = sorted(t for t in TYPE_DIR if t not in SECTION_TITLES)
    assert not missing, f"card.type {missing} 无对应分区标题 → 新卡静默不登记 INDEX"


def test_main_dry_run_plans_blueprint_card(tmp_path, capsys):
    """type=blueprint（单数）新卡须被规划进 blueprints 分区（修复前因缺别名而漏规划）。"""
    (tmp_path / "INDEX.md").write_text("# idx\n", encoding="utf-8")
    _typed_card(tmp_path / "blueprints" / "bp.md", "blueprint", "# 标题\n\n蓝图摘要段落。\n")
    assert main(["--root", str(tmp_path), "--names", "bp.md", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out and "bp" in out, f"blueprint 卡未被规划: {out}"


# ── 2026-10-09 体检回归：源与派生必须同批提交（写入流水线自锁）─────────────────
# 背景：`sync.ingest` 先提交卡、后由 post_ingest_hook 渲染 INDEX，而 pre-commit 的 l0
# 渲染一致性门禁会阻断“卡已暂存、INDEX 未更新”的提交 ⇒ ingest 报 `git 命令失败`、
# hook 又因 status != ok 被跳过 ⇒ 卡与 INDEX 双双滞留未提交。另有两处叠加：
#   ① `_apply_plan` 的 written_files 漏 EXPERIENCE_NAME（第三个渲染产物永不被暂存）；
#   ② main() 的 `if not added: return 0` 让渲染型变更永不提交（added 只统计追加式分册）；
#   ③ render_index.write 自取写锁，而 _WriteLock 不可重入 ⇒ 锁内渲染报“写锁被持续占用”。


def _hub(tmp_path: Path) -> Path:
    from scripts.bootstrap_hub import bootstrap

    return bootstrap(tmp_path / "AgentMemoryHub")


def _exp_card(root: Path, name: str, body: str = "这是一张用于回归测试的经验卡正文。") -> Path:
    p = root / "experience" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\ntype: exp\ngrade: task\ntags:\n- a\nupdated: 2026-10-09\nstatus: candidate\nreuse_count: 0\n---\n\n# 标题\n\n{body}\n",
        encoding="utf-8",
    )
    return p


def _head_names(root: Path) -> str:
    import subprocess

    return subprocess.run(
        ["git", "-C", str(root), "show", "--name-only", "--pretty=format:", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def test_sync_indices_works_under_already_held_lock(tmp_path):
    """回归③：调用方**已持写锁**时必须能渲染（`lock=False`），否则“写锁被持续占用”。

    同时钉住“三个渲染产物一个都不能漏”（回归①：旧代码只暂存 L0 + FULL）。"""
    from scripts.post_ingest_hook import sync_indices
    from sync import _WriteLock

    root = _hub(tmp_path)
    _exp_card(root, "lock-demo.md")
    with _WriteLock(root):
        written = sync_indices(root, ["lock-demo.md"], lock=False)
    assert written == {"INDEX.md", "INDEX-full.md", "INDEX-experience.md"}, written
    # INDEX 行是 **slug（去 .md）**，不要把扩展名写进断言
    assert "lock-demo" in (root / "INDEX-experience.md").read_text(encoding="utf-8")


def test_main_commits_render_only_changes(tmp_path):
    """回归②：渲染型变更（当日不再走追加式分册）也必须被提交。"""
    root = _hub(tmp_path)
    _exp_card(root, "hook-demo.md")
    assert main(["--root", str(root), "--names", "hook-demo.md"]) == 0
    assert "hook-demo" in (root / "INDEX-experience.md").read_text(encoding="utf-8")
    names = _head_names(root)
    assert "INDEX-experience.md" in names, names


def test_ingest_commits_card_and_rendered_index_together(tmp_path):
    """回归（主用例）：`ingest` 一笔提交里必须**同时**含卡与 INDEX 渲染产物。

    修复前：提交只含卡 ⇒ 被 l0 渲染门禁阻断 ⇒ `stat["status"] != "ok"` 且卡滞留暂存区。"""
    root = _hub(tmp_path)
    d = root / ".sync" / "drafts" / "pi_draft"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ing-demo.md").write_text(
        "---\ntype: exp\ngrade: task\ntags:\n- a\nupdated: 2026-10-09\n"
        "status: candidate\nreuse_count: 0\n---\n\n# 标题\n\n入库回归测试卡正文。\n",
        encoding="utf-8",
    )
    from sync import ingest

    stat = ingest(root, "pi")
    assert stat["status"] == "ok", stat
    assert (root / "experience" / "ing-demo.md").exists()
    names = _head_names(root)
    assert "experience/ing-demo.md" in names, names
    assert "INDEX-experience.md" in names, names
