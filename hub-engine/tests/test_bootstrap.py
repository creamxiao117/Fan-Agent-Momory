from pathlib import Path

from scripts.bootstrap_hub import bootstrap


def test_bootstrap_creates_skeleton(tmp_path):
    root = bootstrap(tmp_path)
    for sub in ("rules", "libs", "experience", "projects", "retro", "archive",
                ".sync/drafts/trae_draft", ".sync/drafts/code_draft",
                ".sync/conflicts", ".sync/locks", ".sync/state", ".sync/pending"):
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


def test_bootstrap_git_init(tmp_path):
    root = bootstrap(tmp_path)
    assert (root / ".git" / "config").exists()
