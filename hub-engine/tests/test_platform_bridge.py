"""platform_bridge 单测：Adapter 解析/渲染往返、Pull 去重/幂等/dry-run、Push 安全/外部改动、CLI 接线"""

from pathlib import Path

import yaml

from common.frontmatter import parse_card, write_card
from engine import main
from scripts.bootstrap_hub import bootstrap
from tools.platform_bridge import (
    MdSectionAdapter,
    SectSeparatedAdapter,
    adapter_for,
    fingerprint,
    pull,
    push,
)


def _register_platform(
    root: Path, name: str, mem_dir: Path, target: str = "memory.md"
) -> None:
    """在测试中枢的 hub.config.yaml 登记一个指向临时目录的平台"""
    cfg_path = root / "hub.config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    data.setdefault("platforms", {})[name] = {
        "memory_dir": str(mem_dir),
        "target_file": target,
    }
    cfg_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _root_with_platform(
    tmp_path: Path,
    platform: str = "testplat",
    content: str = "## 新经验\n记录一条新经验\n",
) -> Path:
    """bootstrap 一个测试中枢并登记一个指向临时记忆文件的平台"""
    root = bootstrap(tmp_path / "hub")
    mem = tmp_path / "platforms"
    mem.mkdir(exist_ok=True)
    (mem / "memory.md").write_text(content, encoding="utf-8")
    _register_platform(root, platform, mem)
    return root


def _hub_card(root: Path, name: str, body: str, ctype: str = "exp") -> None:
    """在测试中枢权威区放一张卡片（rules 或 experience）"""
    sub = "rules" if ctype == "rule" else "experience"
    card = parse_card(
        f"""---
type: {ctype}
tags: [push-test]
updated: 2026-08-17
status: active
reuse_count: 0
---
{body}
"""
    )
    p = root / sub / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(write_card(card), encoding="utf-8")


# ---------- Adapter 解析 / 渲染 ----------


def test_md_section_parse_splits_headings():
    entries = MdSectionAdapter().parse("## 小节A\n内容A\n\n## 小节B\n内容B\n")
    assert [e.title for e in entries] == ["小节A", "小节B"]
    assert [e.body for e in entries] == ["内容A", "内容B"]


def test_md_section_parse_leading_text_goes_to_empty_title():
    entries = MdSectionAdapter().parse("开头无标题文本\n\n## 小节\n正文\n")
    assert entries[0].title == ""
    assert "开头无标题文本" in entries[0].body
    assert entries[1].title == "小节"


def test_sect_separated_parse_splits_on_mark_and_drops_empty():
    entries = SectSeparatedAdapter().parse("条目一\n§\n\n条目二\n\n§\n  ")
    assert [e.body for e in entries] == ["条目一", "条目二"]
    assert all(e.title == "" for e in entries)


def test_render_round_trip_is_idempotent():
    for adapter, text in [
        (MdSectionAdapter(), "## A\nx\n\n## B\ny\n"),
        (SectSeparatedAdapter(), "一\n§\n二\n"),
    ]:
        first = adapter.parse(text)
        second = adapter.parse(adapter.render(first))
        assert [(e.title, e.body) for e in first] == [(e.title, e.body) for e in second]


def test_fingerprint_normalizes_whitespace_and_case():
    assert fingerprint("Hello  世界\n") == fingerprint("hello 世界")


def test_adapter_for_hermes_sect_others_md():
    assert isinstance(adapter_for("hermes", None), SectSeparatedAdapter)
    assert isinstance(adapter_for("trae", None), MdSectionAdapter)


# ---------- Pull：去重 / 幂等 / dry-run ----------


def test_pull_writes_draft_for_new_entry(tmp_path):
    root = _root_with_platform(tmp_path)
    stat = pull(root, "testplat")
    assert stat["status"] == "ok"
    assert stat["pulled"] == 1
    drafts = list((root / ".sync" / "drafts" / "testplat_draft").glob("*.md"))
    assert len(drafts) == 1
    card = parse_card(drafts[0].read_text(encoding="utf-8"))
    assert card.type == "exp"
    assert "testplat" in card.tags


def test_pull_is_idempotent_second_run_skipped(tmp_path):
    root = _root_with_platform(tmp_path)
    assert pull(root, "testplat")["pulled"] == 1
    stat2 = pull(root, "testplat")
    assert stat2["pulled"] == 0
    assert stat2["skipped"] == 1


def test_pull_skips_when_title_already_in_hub(tmp_path):
    root = _root_with_platform(tmp_path)
    _hub_card(root, "新经验", "中枢已有同名卡片内容")
    stat = pull(root, "testplat")
    assert stat["skipped"] == 1
    assert stat["pulled"] == 0
    assert not list((root / ".sync" / "drafts" / "testplat_draft").glob("*.md"))


def test_pull_conflict_on_semantic_duplicate(tmp_path):
    root = _root_with_platform(
        tmp_path,
        content="## 内存不足处理\n遇到内存不足时先清理缓存再重启服务，同时检查日志定位根因\n",
    )
    _hub_card(
        root,
        "mem-cache",
        "遇到内存不足时先清理缓存再重启服务，同时检查日志定位根因（补充）",
    )
    stat = pull(root, "testplat")
    assert stat["conflicted"] == 1
    assert stat["pulled"] == 0
    assert list((root / ".sync" / "conflicts").glob("testplat_*.md"))
    assert not list((root / ".sync" / "drafts" / "testplat_draft").glob("*.md"))


def test_pull_dry_run_writes_nothing(tmp_path):
    root = _root_with_platform(tmp_path)
    stat = pull(root, "testplat", dry_run=True)
    assert stat["pulled"] == 1
    assert not (root / ".sync" / "drafts" / "testplat_draft").exists()
    assert not (root / ".sync" / "state" / "pulled_testplat.json").exists()


def test_pull_sect_separated_platform(tmp_path):
    root = _root_with_platform(
        tmp_path, platform="hermes", content="条目一\n§\n条目二\n"
    )
    stat = pull(root, "hermes")
    assert stat["pulled"] == 2


# ---------- Push：安全 / 外部改动 / 幂等 ----------


def test_push_adds_new_section_without_touching_original(tmp_path):
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "中枢规则正文")
    stat = push(root, "testplat")
    assert stat["status"] == "ok"
    assert stat["added"] == 1
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "## 新规则" in text
    assert "中枢规则正文" in text
    assert "原有内容" in text  # 平台原内容未被覆盖


def test_push_same_title_appends_authority_not_overwrite(tmp_path):
    root = _root_with_platform(tmp_path, content="## 既有小节\n本地旧版内容\n")
    _hub_card(root, "既有小节", "中枢新版内容")
    stat = push(root, "testplat")
    assert stat["updated"] == 1
    assert stat["added"] == 0
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "本地旧版内容" in text  # 未覆盖本地旧版
    assert "中枢权威版" in text
    assert "中枢新版内容" in text


def test_push_is_idempotent_second_run_skipped(tmp_path):
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "正文")
    assert push(root, "testplat")["added"] == 1
    stat2 = push(root, "testplat")
    assert stat2["added"] == 0
    assert stat2["skipped"] >= 1
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert text.count("## 新规则") == 1


def test_push_aborts_on_external_edit(tmp_path):
    root = _root_with_platform(tmp_path, content="## 小节\n内容\n")
    _hub_card(root, "新规则", "正文")
    assert push(root, "testplat")["status"] == "ok"
    # 外部修改平台文件 → 下次 Push 中止
    p = tmp_path / "platforms" / "memory.md"
    p.write_text(p.read_text(encoding="utf-8") + "\n外部改动\n", encoding="utf-8")
    stat = push(root, "testplat")
    assert stat["status"] != "ok"
    assert "外部" in stat["status"]


def test_push_dry_run_writes_nothing(tmp_path):
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "正文")
    stat = push(root, "testplat", dry_run=True)
    assert stat["added"] == 1
    assert "新规则" not in (tmp_path / "platforms" / "memory.md").read_text(
        encoding="utf-8"
    )


def test_push_only_rules_skips_experience(tmp_path):
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "rule-a", "规则正文", ctype="rule")
    _hub_card(root, "exp-a", "经验正文")
    stat = push(root, "testplat", only_rules=True)
    assert stat["added"] == 1
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "rule-a" in text
    assert "exp-a" not in text


def test_push_name_filter_not_found_reports_not_found(tmp_path):
    """push --name 卡名不存在时返回 not-found 而非静默 0 添加"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "存在的卡", "正文")
    stat = push(root, "testplat", name_filter="不存在的卡")
    assert stat["status"] != "ok"
    assert "not-found" in stat["status"]
    assert stat["added"] == 0
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "不存在的卡" not in text


def test_push_name_filter_matches_existing(tmp_path):
    """push --name 命中现有权威卡才推，其他卡不动"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "目标卡", "目标卡正文")
    _hub_card(root, "其他卡", "其他卡正文")
    stat = push(root, "testplat", name_filter="目标卡")
    assert stat["status"] == "ok"
    assert stat["added"] == 1
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "## 目标卡" in text
    assert "## 其他卡" not in text
    assert "目标卡正文" in text


# ---------- CLI 接线 ----------


def test_cli_sync_dry_run_reports_stats(tmp_path, capsys):
    root = _root_with_platform(tmp_path)
    rc = main(["sync", "--root", str(root), "--platform", "testplat", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pulled" in out


def test_cli_sync_default_is_pull_not_push(tmp_path, capsys):
    root = _root_with_platform(tmp_path, content="## 小节\n原有内容\n")
    _hub_card(root, "新规则", "正文")
    rc = main(["sync", "--root", str(root), "--platform", "testplat"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "新规则" not in (tmp_path / "platforms" / "memory.md").read_text(
        encoding="utf-8"
    )
    assert "pulled" in out


def test_cli_sync_unknown_platform_fails(tmp_path, capsys):
    root = bootstrap(tmp_path / "hub")
    rc = main(["sync", "--root", str(root), "--platform", "nope", "--dry-run"])
    out = capsys.readouterr().out
    assert rc != 0
    assert "未知平台" in out
