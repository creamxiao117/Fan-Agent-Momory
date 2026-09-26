"""auto_fix_lint 单测（2026-09-25 SPLIT2 补网：此前 run_fix 无直接测试）。

覆盖：早退（无 invalid）/ 机械修复 + 留痕 / 高风险目录转人工 / dry-run 不落盘 /
**deprecated 不被误改**（原实现有一份手写 status 四元组且漏了 deprecated）。
"""

from pathlib import Path

from scripts.auto_fix_lint import run_fix

INDEX = "# 中枢索引\n\n## 经验\n"


def _hub(tmp: Path) -> Path:
    (tmp / "INDEX.md").write_text(INDEX, encoding="utf-8")
    (tmp / "experience").mkdir(parents=True, exist_ok=True)
    (tmp / "rules").mkdir(parents=True, exist_ok=True)
    return tmp


def _card(tmp: Path, rel: str, fm: str) -> Path:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm}\n---\n\n正文\n", encoding="utf-8")
    return p


def test_no_invalid_card_returns_message(tmp_path):
    """没有 invalid 卡 → 早退（fixed=0 + message），且不产生 patch 文件"""
    hub = _hub(tmp_path)
    _card(hub, "experience/ok.md", "type: exp\ntags: [x]\nupdated: '2026-09-25'\nstatus: active")
    res = run_fix(hub)
    assert res["fixed"] == 0
    assert "无需修复" in res["message"]
    assert not (hub / ".sync" / "patches").exists()


def test_fixes_invalid_type_and_writes_patch(tmp_path):
    """type 非法（experience 走 type: experience）→ 按目录映射修好 + 写留痕"""
    hub = _hub(tmp_path)
    p = _card(hub, "experience/bad.md", "type: experience\ntags: [x]\nupdated: '2026-09-25'\nstatus: active")
    res = run_fix(hub)
    assert res["fixed"] == 1
    text = p.read_text(encoding="utf-8")
    assert "type: exp" in text
    patches = list((hub / ".sync" / "patches").glob("lint-fix-*.md"))
    assert len(patches) == 1
    assert "experience/bad.md" in patches[0].read_text(encoding="utf-8")


def test_deprecated_status_is_not_flipped(tmp_path):
    """回归：status: deprecated + 另一处缺陷 ⇒ 只修该缺陷，deprecated 必须保留。

    原实现用本地四元组 ("active","archived","candidate","reference") 判定 status，
    漏了 deprecated ⇒ 会把已作废的卡改回 active（内容已并入别卡，改回等于复活）。
    """
    hub = _hub(tmp_path)
    p = _card(hub, "experience/dep.md", "type: exp\ntags: [x]\nstatus: deprecated")
    res = run_fix(hub)
    assert res["fixed"] == 1
    text = p.read_text(encoding="utf-8")
    assert "status: deprecated" in text
    assert "updated:" in text  # 缺失的 updated 被补上


def test_high_risk_dir_goes_to_human(tmp_path):
    """rules/（高风险）即便有缺陷也不自动改，计入需人工"""
    hub = _hub(tmp_path)
    p = _card(hub, "rules/r.md", "type: experience\ntags: [x]\nupdated: '2026-09-25'\nstatus: active")
    before = p.read_text(encoding="utf-8")
    res = run_fix(hub)
    assert res["fixed"] == 0
    assert res["failed"] >= 1
    assert p.read_text(encoding="utf-8") == before


def test_dry_run_does_not_write(tmp_path):
    """dry-run：统计照给，但卡与 patch 都不落盘"""
    hub = _hub(tmp_path)
    p = _card(hub, "experience/bad.md", "type: experience\ntags: [x]\nupdated: '2026-09-25'\nstatus: active")
    before = p.read_text(encoding="utf-8")
    res = run_fix(hub, dry_run=True)
    assert res["fixed"] == 1
    assert res["dry_run"] is True
    assert p.read_text(encoding="utf-8") == before
    assert not (hub / ".sync" / "patches").exists()
