import subprocess

from scripts.bootstrap_hub import bootstrap


def test_bootstrap_creates_skeleton(tmp_path):
    root = bootstrap(tmp_path)
    for sub in (
        "rules",
        "libs",
        "experience",
        "projects",
        "retro",
        "blueprints",
        "archive",
        ".sync/drafts/trae_draft",
        ".sync/drafts/code_draft",
        ".sync/conflicts",
        ".sync/locks",
        ".sync/state",
        ".sync/pending",
    ):
        assert (root / sub).is_dir(), sub
    assert (root / "INDEX.md").exists()
    assert (root / "retro" / "log.md").exists()
    assert (root / "hub.config.yaml").exists()
    assert (root / "provider_keys.yaml").exists()
    assert (root / ".gitignore").exists()


def test_bootstrap_idempotent(tmp_path):
    bootstrap(tmp_path)
    bootstrap(tmp_path)  # 重复执行不报错、不覆盖已有文件
    assert (tmp_path / "INDEX.md").exists()
    # 用户自定义 .gitignore 不应被重复执行覆盖
    custom = "# 用户自定义规则\n*.tmp\n"
    (tmp_path / ".gitignore").write_text(custom, encoding="utf-8")
    bootstrap(tmp_path)
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == custom


def test_bootstrap_git_init(tmp_path):
    root = bootstrap(tmp_path)
    assert (root / ".git" / "config").exists()
    # 首次提交应已通过本地身份完成，HEAD 可解析出非空 hash
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert proc.stdout.strip()
