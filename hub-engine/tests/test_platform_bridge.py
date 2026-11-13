CRLF = chr(13) + chr(10)


"""platform_bridge 单测：Adapter 解析/渲染往返、Pull 去重/幂等/dry-run、Push 安全/外部改动、CLI 接线"""

from pathlib import Path

import yaml

from common.frontmatter import parse_card, write_card
from engine import main
from scripts.bootstrap_hub import bootstrap
from tools.platform_bridge import (
    ADAPTER_REGISTRY,
    SUPPORTED_PLATFORMS,
    MdSectionAdapter,
    SectSeparatedAdapter,
    adapter_for,
    fingerprint,
    pull,
    push,
)


def _register_platform(root: Path, name: str, mem_dir: Path, target: str = "memory.md") -> None:
    """在测试中枢的 hub.config.yaml 登记一个指向临时目录的平台"""
    cfg_path = root / "hub.config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    data.setdefault("platforms", {})[name] = {
        "memory_dir": str(mem_dir),
        "target_file": target,
    }
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _set_platform_budget(root: Path, name: str, limit: int) -> None:
    """给测试中枢的平台登记**体量闸**（= 消费端自己的加载上限，如 hermes memory_char_limit）"""
    cfg_path = root / "hub.config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    data.setdefault("platforms", {}).setdefault(name, {})["memory_char_limit"] = limit
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


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


# 2026-09-02 权威区收缩适配：默认卡必须落在 5 权威区目录（push/pull 只扫
# _authority_cards），非 rule 用 longterm 承载（exp 已退出权威区）
def _hub_card(root: Path, name: str, body: str, ctype: str = "longterm") -> None:
    """在测试中枢权威区放一张卡片（rules 或 longterm）"""
    sub = "rules" if ctype == "rule" else "longterm"
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


def test_adapter_for_mavis_deepseek_use_md_sections():
    """mavis(MiniMax Code) / deepseek(DSH) 走 ## 分段适配器（2026-09-19 显式登记）"""
    assert isinstance(adapter_for("mavis", None), MdSectionAdapter)
    assert isinstance(adapter_for("deepseek", None), MdSectionAdapter)


def test_mavis_deepseek_adapter_roundtrip():
    """两个新登记平台的解析→渲染往返必须无损（内容不被吞/不被改写）"""
    text = "## 卡片甲\n甲正文\n\n## 卡片乙\n乙正文\n"
    for platform in ("mavis", "deepseek"):
        adapter = adapter_for(platform, None)
        first = adapter.parse(text)
        second = adapter.parse(adapter.render(first))
        assert [(e.title, e.body) for e in first] == [(e.title, e.body) for e in second], f"{platform} 往返丢失条目"
        assert [e.title for e in first] == ["卡片甲", "卡片乙"]


def test_adapter_registry_is_coverage_source_of_truth():
    """注册表与集合视图一致；hermes 必须仍是 § 分隔（防重构误改）"""
    assert set(ADAPTER_REGISTRY) == set(SUPPORTED_PLATFORMS)
    assert ADAPTER_REGISTRY["hermes"] is SectSeparatedAdapter


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
    root = _root_with_platform(tmp_path, platform="hermes", content="条目一\n§\n条目二\n")
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
    assert "新规则" not in (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")


def test_push_only_rules_skips_experience(tmp_path):
    """only_rules 只推 rules 目录卡，权威区内其他类型（longterm）被过滤"""
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
    assert "新规则" not in (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "pulled" in out


def test_cli_sync_unknown_platform_fails(tmp_path, capsys):
    root = bootstrap(tmp_path / "hub")
    rc = main(["sync", "--root", str(root), "--platform", "nope", "--dry-run"])
    out = capsys.readouterr().out
    assert rc != 0
    assert "未知平台" in out


# ---------- 换行风格保持（2026-09-19：push 不再重写整文件换行） ----------


LF = chr(10)
CRLF = chr(13) + chr(10)


def test_push_preserves_lf_newlines(tmp_path):
    """LF 风格的平台文件，push 后必须仍为纯 LF（不得被翻译成 CRLF）。"""
    root = _root_with_platform(tmp_path)
    target = tmp_path / "platforms" / "memory.md"
    target.write_bytes(("## 平台小节" + LF + "原有内容" + LF).encode())  # 强制 LF 落盘
    _hub_card(root, "新规则", "正文")
    assert push(root, "testplat")["added"] == 1
    raw = target.read_bytes()
    assert raw.count(CRLF.encode()) == 0, "push 把 LF 文件改写成了 CRLF"
    assert "新规则" in raw.decode("utf-8")  # 卡片确实写入
    assert "原有内容" in raw.decode("utf-8")  # 平台原内容保留


def test_push_preserves_crlf_newlines(tmp_path):
    """CRLF 风格的平台文件，push 后必须仍为 CRLF，且不产生混编。"""
    root = _root_with_platform(tmp_path)
    target = tmp_path / "platforms" / "memory.md"
    target.write_bytes(("## 平台小节" + CRLF + "原有内容" + CRLF).encode())
    _hub_card(root, "新规则", "正文")
    assert push(root, "testplat")["added"] == 1
    raw = target.read_bytes()
    assert raw.count(CRLF.encode()) >= 3
    assert raw.count(LF.encode()) - raw.count(CRLF.encode()) == 0, "出现裸 LF（换行混编）"


def test_repush_updates_card_in_place_no_duplicate(tmp_path):
    """中枢改卡后重推：同名段若是中枢此前推过的版本 → 原地替换，不再追加副本。"""
    root = _root_with_platform(tmp_path)
    _hub_card(root, "新规则", "第一版正文")
    assert push(root, "testplat")["added"] == 1
    _hub_card(root, "新规则", "第二版正文")  # 中枢侧改卡（同标题、正文变化）
    stat = push(root, "testplat")
    assert stat["replaced"] == 1
    assert stat["updated"] == 0
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "第二版正文" in text
    assert "第一版正文" not in text  # 旧版被替换，不留残副本
    assert text.count("## 新规则") == 1  # 无重复段
    assert "中枢权威版" not in text  # 未走追加路径


def test_repush_preserves_local_edit_when_not_hub_pushed(tmp_path):
    """平台本地自己写的同名段（非中枢推的）→ 仍追加权威版，绝不覆盖本地编辑。"""
    root = _root_with_platform(tmp_path, content="## 新规则" + LF + "平台本地自己的内容" + LF)
    _hub_card(root, "新规则", "中枢正文")
    stat = push(root, "testplat")
    assert stat["added"] == 0
    assert stat["updated"] == 1
    assert stat["replaced"] == 0
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "平台本地自己的内容" in text  # 本地编辑保留
    assert "中枢权威版" in text
    assert "中枢正文" in text


def test_repush_handles_card_with_internal_headings(tmp_path):
    """卡片自带 ## 子标题时也必须整段替换（锁定 parse 按 ## 切分导致的取段过短缺陷）。"""
    root = _root_with_platform(tmp_path)
    body1 = "## 一句话结论" + LF + LF + "第一版正文" + LF + LF + "## 关联" + LF + LF + "- 旧关联"
    body2 = "## 一句话结论" + LF + LF + "第二版正文" + LF + LF + "## 关联" + LF + LF + "- 新关联"
    _hub_card(root, "新规则", body1)
    assert push(root, "testplat")["added"] == 1
    _hub_card(root, "新规则", body2)
    stat = push(root, "testplat")
    assert stat["replaced"] == 1, "含内部子标题的卡片未被整段替换"
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "第二版正文" in text
    assert "第一版正文" not in text
    assert "## 新规则" in text and text.count("## 新规则") == 1


# ---------- hermes（§ 分隔无标题）专测：插入不破坏结构 + 改卡原地替换 ----------


def test_hermes_push_does_not_split_existing_cards(tmp_path):
    """新块插入点必须按 §-平台条目边界（`# `）——不得插进既有卡片内部。"""
    root = _root_with_platform(
        tmp_path,
        platform="hermes",
        content="【统一记忆中枢（AGENT MEMORY HUB）】执行前先查中枢\n\n§\n\n# 既有卡片标题\n\n## 一句话结论\n\n既有正文（必须保持紧跟标题、不被劈开）。\n\n## 关联\n\n- 无\n",
    )
    _hub_card(root, "新规则", "中枢新卡正文")
    assert push(root, "hermes")["added"] == 1
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "既有正文（必须保持紧跟标题、不被劈开）。" in text
    assert ("# 既有卡片标题" + LF + LF + "## 一句话结论") in text, "既有卡片被劈开（标题与正文之间被插入）"
    assert "中枢新卡正文" in text


def test_hermes_repush_replaces_in_place_no_duplicate(tmp_path):
    """hermes 无同名键：靠 body 首行 + 指纹闸原地替换，不得追加旧版副本。"""
    root = _root_with_platform(
        tmp_path,
        platform="hermes",
        content="【统一记忆中枢（AGENT MEMORY HUB）】执行前先查中枢\n\n§\n\n# 既有卡片标题\n\n## 一句话结论\n\n既有正文（必须保持紧跟标题、不被劈开）。\n\n## 关联\n\n- 无\n",
    )
    _hub_card(root, "新规则", "# 新规则" + LF + LF + "## 一句话结论" + LF + LF + "第一版正文")
    assert push(root, "hermes")["added"] == 1
    _hub_card(root, "新规则", "# 新规则" + LF + LF + "## 一句话结论" + LF + LF + "第二版正文")
    stat = push(root, "hermes")
    assert stat["replaced"] == 1, "hermes 改卡重推未原地替换"
    assert stat["added"] == 0
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert text.count("# 新规则") == 1
    assert "第二版正文" in text
    assert "第一版正文" not in text


def test_hermes_repush_fence_aware_no_cross_fence_replace(tmp_path):
    """围栏内的 `# ` 注释不得被当成 hermes 卡片边界（R18 教训：越界替换 361 行/删 286 行）。

    卡片正文含 bash 示例围栏（首行即 `# 1. ...` 注释）：改卡重推时
    替换区间必须完整覆盖围栏 + 围栏之后的正文，且围栏内注释保持原样。
    """
    fence_example = "```" + LF + "# 1. 入库后先 lint + build-vectors" + LF + "# 2. dry-run 逐平台预检" + LF + "```"
    body1 = (
        "# 同步纪律"
        + LF
        + LF
        + "正文第一段。"
        + LF
        + LF
        + fence_example
        + LF
        + LF
        + "正文第二段（围栏后，越界替换会把它吞掉）。"
    )
    body2 = body1 + LF + LF + "## 升级记录" + LF + LF + "- V1.1 新增围栏感知说明"
    root = _root_with_platform(tmp_path, platform="hermes", content="【指令】\n\n§\n\n")
    _hub_card(root, "sync-discipline", body1)
    assert push(root, "hermes")["added"] == 1
    _hub_card(root, "sync-discipline", body2)
    stat = push(root, "hermes")
    assert stat["replaced"] == 1, "围栏感知下仍未原地替换（指纹闸未通过？）"
    text = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert text.count("# 同步纪律") == 1
    assert "# 1. 入库后先 lint + build-vectors" in text  # 围栏内注释完整保留
    assert "正文第二段（围栏后，越界替换会把它吞掉）。" in text  # 围栏后正文未被吞
    assert "- V1.1 新增围栏感知说明" in text  # 第二版已替换进来
    assert text.count("```") == 2  # 围栏成对、未被劈开


# ---------- Push 体量闸（2026-11-12：中枢 push 曾把 hermes 平台记忆灌到超限 12.8 倍）----------


def test_push_refuses_when_projected_size_exceeds_platform_budget(tmp_path):
    """推后体量超平台上限 ⇒ 拒绝写入，文件一字不动。

    实测 2026-11-12：中枢 push 7 张卡把 hermes MEMORY.md 灌到 30,668 字符，
    而消费端 `memory_char_limit: 2400` ⇒ **消费端从此拒绝一切写入**，而 push 本身照样报「成功」。
    """
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "中枢规则正文" * 50)
    _set_platform_budget(root, "testplat", 100)
    before = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    stat = push(root, "testplat")
    assert stat["status"] != "ok"
    assert "拒绝写入" in stat["status"]
    assert stat["added"] == 0
    assert (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8") == before


def test_push_allowed_when_within_platform_budget(tmp_path):
    """在上限之内 ⇒ 正常写入（闸只拦超限，不拦正常同步）"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "正文")
    _set_platform_budget(root, "testplat", 5000)
    stat = push(root, "testplat")
    assert stat["status"] == "ok"
    assert stat["added"] == 1
    assert "新规则" in (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")


def test_push_without_declared_budget_is_unaffected(tmp_path):
    """未声明上限的平台（mavis 等镜像）⇒ 不设闸，行为逐字不变"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "正文" * 200)
    stat = push(root, "testplat")
    assert stat["status"] == "ok"
    assert stat["added"] == 1


def test_push_budget_refusal_also_reported_in_dry_run(tmp_path):
    """dry-run 也要报出超限（维护者要先看见，才不会在实推时被拒）"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "正文" * 200)
    _set_platform_budget(root, "testplat", 100)
    stat = push(root, "testplat", dry_run=True)
    assert stat["status"] != "ok"
    assert "拒绝写入" in stat["status"]
    assert "新规则" not in (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")


def test_push_refuses_when_platform_budget_is_invalid(tmp_path):
    """上限写错（"16k" / -5 / 0 / True）⇒ **拒绝写入**并明确报配置错误。

    静默当成「不设闸」= **闸悄悄失效** = 生产端零信号 = 本闸要根治的那类事故 ⇒ 必须 fail-closed。
    """
    for bad in ("16k", -5, "0", 0, True):
        root = _root_with_platform(tmp_path / f"case_{bad}", content="## 平台已有小节\n原有内容\n")
        _hub_card(root, "新规则", "正文")
        _set_platform_budget(root, "testplat", bad)
        stat = push(root, "testplat")
        assert stat["status"] != "ok", f"非法上限 {bad!r} 竟未拒绝"
        assert "非法" in stat["status"]
        assert stat["added"] == 0


def test_push_allows_when_projected_size_equals_budget(tmp_path):
    """边界：推后体量**恰好等于**上限 ⇒ 放行（与消费端 `> limit` 的严格大于语义一致）"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    original = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    _hub_card(root, "新规则", "正文")
    _set_platform_budget(root, "testplat", 10**6)
    assert push(root, "testplat")["added"] == 1
    exact = len((tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8"))
    # 复位现场：平台文件回到推前内容 + 台账清空 ⇒ 同一张卡的投影长度可复算
    (tmp_path / "platforms" / "memory.md").write_text(original, encoding="utf-8")
    (root / ".sync" / "state" / "pulled_testplat.json").unlink(missing_ok=True)
    _set_platform_budget(root, "testplat", exact)
    stat = push(root, "testplat")
    assert stat["status"] == "ok", stat["status"]
    assert stat["added"] == 1


def test_push_refuses_when_replacement_would_exceed_budget(tmp_path):
    """替换/更新路径也要计入体量：同一张卡改大后超限 ⇒ 拒绝且文件一字不动"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "短正文")
    _set_platform_budget(root, "testplat", 10**6)
    first = push(root, "testplat")
    assert first["added"] == 1, first  # 首推必须是**新增**（预置文件不得与卡同名）
    before = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    _hub_card(root, "新规则", "长" * 500)
    # dry-run 先确认走的确实是**替换**路径（而非新增/追加）——替换体量同样要计入闸
    plan = push(root, "testplat", dry_run=True)
    assert plan["replaced"] == 1, plan
    assert (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8") == before
    before = (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    _hub_card(root, "新规则", "长" * 500)
    _set_platform_budget(root, "testplat", len(before) + 10)
    stat = push(root, "testplat")
    assert stat["status"] != "ok"
    assert "拒绝写入" in stat["status"]
    assert (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8") == before


def test_push_refusal_leaves_platform_state_untouched(tmp_path):
    """拒绝写入时**台账零污染**（否则下次 push 误判「已推过」而静默跳过 ⇒ 最静的后果）"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "正文")
    _set_platform_budget(root, "testplat", 10)
    state = root / ".sync" / "state" / "pulled_testplat.json"
    before = state.read_text(encoding="utf-8") if state.exists() else None
    assert push(root, "testplat")["status"] != "ok"
    after = state.read_text(encoding="utf-8") if state.exists() else None
    assert after == before


# ---------- 平台级告警预算 memory_char_warn_limit（2026-11-13：只报不拦）----------


def _set_platform_warn_budget(root: Path, name: str, limit) -> None:
    """给测试中枢的平台登记**告警预算**（hub 侧自设告警线，只报不拦，不阻断写入）"""
    cfg_path = root / "hub.config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    data.setdefault("platforms", {}).setdefault(name, {})["memory_char_warn_limit"] = limit
    cfg_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_push_warns_over_warn_limit_but_still_writes(tmp_path):
    """超告警线 ⇒ **照常写入** + stat 出结构化告警 + 中枢日志 retro/log.md 留一行。

    告警线是**只报不拦**的探针（与 memory_char_limit 的阻断语义相反）：
    它服务于「消费端上限无法核验」的平台（mavis / code / workbuddy / deepseek / pi），
    让平台记忆文件「在长胖」这件事不再零信号。
    """
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "中枢规则正文" * 50)
    _set_platform_warn_budget(root, "testplat", 100)
    target = tmp_path / "platforms" / "memory.md"
    before = target.read_text(encoding="utf-8")
    stat = push(root, "testplat")
    assert stat["status"] == "ok", stat
    assert stat["added"] == 1
    text = target.read_text(encoding="utf-8")
    assert text != before, "超告警线必须**照常写入**（只报不拦）"
    assert "新规则" in text
    assert len(stat["warnings"]) == 1, stat
    w = stat["warnings"][0]
    assert w["platform"] == "testplat"
    assert w["warn_limit"] == 100
    assert w["projected_chars"] > 100
    log = (root / "retro" / "log.md").read_text(encoding="utf-8")
    assert "⚠ 告警" in log, "告警必须在中枢日志留痕（stdout 会被吞）"


def test_push_no_warning_when_within_warn_limit(tmp_path):
    """未超告警线 ⇒ 无告警（stat 里空列表 + 日志无告警行）"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "正文")
    _set_platform_warn_budget(root, "testplat", 10**6)
    stat = push(root, "testplat")
    assert stat["status"] == "ok"
    assert stat["added"] == 1
    assert stat["warnings"] == []
    assert "⚠ 告警" not in (root / "retro" / "log.md").read_text(encoding="utf-8")


def test_push_refuses_when_warn_limit_is_invalid(tmp_path):
    """告警线写错（"16k" / -5 / 0 / True）⇒ 显式配置错误 + 拒绝写入（探针不许悄悄失效）。

    判定：告警线**超限**只是提醒、照常写；但告警线**非法**是配置错误 ⇒ fail-closed
    （与 memory_char_limit 同一处置：宁可停下让人修配置，也不能让探针静默失效 ⇒ 生产端零信号）。
    """
    for bad in ("16k", -5, "0", 0, True):
        root = _root_with_platform(tmp_path / f"warn_{bad}", content="## 平台已有小节\n原有内容\n")
        _hub_card(root, "新规则", "正文")
        _set_platform_warn_budget(root, "testplat", bad)
        target = tmp_path / f"warn_{bad}" / "platforms" / "memory.md"
        before = target.read_text(encoding="utf-8")
        stat = push(root, "testplat")
        assert stat["status"] != "ok", f"非法告警线 {bad!r} 竟未报错"
        assert "非法" in stat["status"]
        assert stat["added"] == 0
        assert target.read_text(encoding="utf-8") == before


def test_push_limit_block_takes_precedence_over_warn(tmp_path):
    """两个字段同时存在 ⇒ **limit 阻断优先**：拒绝写入，且**不产生** warn 告警。

    优先级口径：**阻断闸先判**（消费端契约），告警线只在「不阻断」的路径上产生
    ⇒ 避免同一个 push 同时报「拒绝写入」又报「已超告警线」这种自相矛盾的信号。
    """
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "中枢规则正文" * 50)
    _set_platform_budget(root, "testplat", 100)
    _set_platform_warn_budget(root, "testplat", 50)
    target = tmp_path / "platforms" / "memory.md"
    before = target.read_text(encoding="utf-8")
    stat = push(root, "testplat")
    assert stat["status"] != "ok"
    assert "拒绝写入" in stat["status"]
    assert stat["added"] == 0
    assert stat["warnings"] == [], "阻断路径上不得再产生告警"
    assert target.read_text(encoding="utf-8") == before
    assert "⚠ 告警" not in (root / "retro" / "log.md").read_text(encoding="utf-8")


def test_push_warn_fires_when_limit_allows(tmp_path):
    """limit 未超限 + warn 超线 ⇒ 写入照常发生 + 出告警（warn 只在「不阻断」路径上产生）"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "中枢规则正文" * 20)
    _set_platform_budget(root, "testplat", 10**6)
    _set_platform_warn_budget(root, "testplat", 100)
    stat = push(root, "testplat")
    assert stat["status"] == "ok", stat
    assert stat["added"] == 1
    assert len(stat["warnings"]) == 1
    assert "⚠ 告警" in (root / "retro" / "log.md").read_text(encoding="utf-8")


def test_push_without_declared_limits_is_unchanged(tmp_path):
    """未声明任何上限的平台（mavis 等镜像）⇒ 不设闸、不告警、行为与改前逐字一致"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "正文" * 200)
    stat = push(root, "testplat")
    assert stat["status"] == "ok"
    assert stat["added"] == 1
    assert stat["warnings"] == []
    assert "新规则" in (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert "⚠ 告警" not in (root / "retro" / "log.md").read_text(encoding="utf-8")


def test_push_warn_reported_in_dry_run_without_logging(tmp_path):
    """dry-run 也报告警（维护者要先看见），但**不落日志**（dry-run 不许改中枢）"""
    root = _root_with_platform(tmp_path, content="## 平台已有小节\n原有内容\n")
    _hub_card(root, "新规则", "中枢规则正文" * 50)
    _set_platform_warn_budget(root, "testplat", 100)
    log_before = (root / "retro" / "log.md").read_text(encoding="utf-8")
    stat = push(root, "testplat", dry_run=True)
    assert len(stat["warnings"]) == 1
    assert "新规则" not in (tmp_path / "platforms" / "memory.md").read_text(encoding="utf-8")
    assert (root / "retro" / "log.md").read_text(encoding="utf-8") == log_before
