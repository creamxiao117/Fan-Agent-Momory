from pathlib import Path

from engine import main
from scripts.bootstrap_hub import bootstrap


def test_cli_retrieve_prints_hit(capsys, tmp_path):
    root = bootstrap(tmp_path)
    (root / "rules" / "dll.md").write_text(
        "---\ntype: rule\ntags: [autocad, dll-lock]\nupdated: 2026-08-17\nstatus: active\nreuse_count: 0\n---\nDLL 修改后必须递增版本号。\n",
        encoding="utf-8")
    rc = main(["retrieve", "--root", str(root), "dll-lock"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "dll.md" in out


def test_cli_ingest_and_confirm_flow(tmp_path):
    root = bootstrap(tmp_path)
    d = root / ".sync" / "drafts" / "trae_draft"
    d.mkdir(parents=True, exist_ok=True)
    (d / "r1.md").write_text(
        "---\ntype: rule\ntags: [x]\nupdated: 2026-08-17\nstatus: candidate\nreuse_count: 0\n---\n重要规则：DLL 必须递增版本。\n",
        encoding="utf-8")
    assert main(["ingest", "--root", str(root), "--platform", "trae"]) == 0
    assert main(["confirm", "--root", str(root), "r1.md"]) == 0
    assert (root / "rules" / "r1.md").exists()
