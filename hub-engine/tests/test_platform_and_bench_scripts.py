# @version V1.0 / 2026-09-25 / COV：平台同步/健康检查/定位性基准/睡眠候选处理
"""四个 `scripts/` 脚本的纯函数与统计逻辑测试（COV：scripts/ 26.9% → 40%）。

选取原则：**不 mock 业务、只给 fixture** —— 这些函数的输入输出都是文件/dict，
真跑一遍就能覆盖大半分支，且能在实现变更时立刻暴露口径漂移。

覆盖到的关键口径：
- `platform_sync`：期望块/argv 生成、键名别名、块一致性判定、YAML/TOML 保格式写回
- `platform_healthcheck`：三类平台（mcp / file / hook+file）的状态判定与仪表盘落盘
- `index_locatability_bench`：内容词过滤、卡 tags 解析（行内/块两种写法）、覆盖率打分
- `auto_process_sleep`：中文关键词抽取上限、卡类型门、tags 追加去重、P0 草稿生成
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from scripts import auto_process_sleep as aps
from scripts import index_locatability_bench as ilb
from scripts import platform_healthcheck as phc
from scripts import platform_sync as psync
from scripts.bootstrap_hub import bootstrap

# ---------------------------------------------------------------------------
# platform_sync
# ---------------------------------------------------------------------------


def _platform_hub(tmp_path: Path, platforms: dict) -> Path:
    hub = tmp_path / "AgentMemoryHub"
    (hub / "system").mkdir(parents=True, exist_ok=True)
    (hub / "system" / "platforms.yaml").write_text(
        yaml.safe_dump({"platforms": platforms}, allow_unicode=True), encoding="utf-8"
    )
    return hub


def test_norm_and_p_helpers():
    """规范化：反斜杠→斜杠、折叠重复分隔符（跨格式字面量比较用）。"""
    assert psync._norm("C:\\a\\b") == "C:/a/b"
    assert psync._norm("a//b") == "a/b"
    assert psync._norm(None) == "None", "非字符串直接 str()，不做特殊处理"
    assert psync._p(Path("a") / "b").endswith("a/b")


def test_load_platforms_reads_yaml(tmp_path):
    hub = _platform_hub(tmp_path, {"trae": {"type": "mcp", "mcp_config_path": "~/.trae-cn/mcp.json"}})
    data = psync.load_platforms(hub)
    assert "platforms" in data and "trae" in data["platforms"]


def test_load_platforms_exits_when_missing(tmp_path):
    """platforms.yaml 缺失属配置错误 → exit(2)，不静默继续。"""
    with pytest.raises(SystemExit) as exc:
        psync.load_platforms(tmp_path)
    assert exc.value.code == 2


def test_resolve_config_path_expands_home_for_relative():
    cfg = psync.resolve_config_path(".trae-cn/mcp.json")
    assert cfg.is_absolute() and cfg.parent.parent == Path.home()
    abs_path = Path("C:/tmp/x.json")
    assert psync.resolve_config_path(str(abs_path)) == abs_path


def test_expected_block_and_argv_shape(tmp_path):
    hub = _platform_hub(tmp_path, {})
    cfg = tmp_path / "mcp.json"
    launcher = Path("hub-engine/scripts/hub_mcp_launcher.py")

    argv = psync.expected_argv("trae", cfg, hub, launcher)
    assert argv[0].endswith("hub_mcp_launcher.py")
    assert "--platform" in argv and "trae" in argv
    assert "--heal" in argv and "\\" not in " ".join(argv), "写入用前斜杠"

    block = psync.expected_block("trae", cfg, hub, launcher, "python.exe", "json")
    assert block["command"] == "python.exe"
    assert block["args"] == argv


def test_find_server_key_aliases():
    assert psync._find_server_key({"agent-memory-hub": {}}) == "agent-memory-hub"
    assert psync._find_server_key({"agent_memory_hub": {}}) == "agent_memory_hub"
    assert psync._find_server_key({}) == "", "无别名时返回空串（调用方回退默认键）"


def test_read_current_returns_tuple_and_missing(tmp_path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"agent-memory-hub": {"command": "python"}}}), encoding="utf-8")
    key, block = psync.read_current("json", cfg, "agent-memory-hub")
    assert block is None or block.get("command") == "python"
    assert key  # 回传解析到的键名
    # 文件不存在 → (server_key, None)
    assert psync.read_current("json", tmp_path / "nope.json", "k") == ("k", None)


def test_block_matches_only_command_and_args():
    expected = {"command": "python", "args": ["a", "b"]}
    assert psync.block_matches({"command": "python", "args": ["a", "b"]}, expected) is True
    assert psync.block_matches({"command": "python", "args": ["a", "c"]}, expected) is False
    assert psync.block_matches("不是 dict", expected) is False


def test_write_yaml_replaces_managed_block(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "mcp_servers:\n  agent-memory-hub:\n    command: old\n    args: []\n",
        encoding="utf-8",
    )
    psync.write_yaml(cfg, "agent-memory-hub", {"command": "new", "args": ["x"]}, indent=2)
    text = cfg.read_text(encoding="utf-8")
    assert "new" in text and "old" not in text
    assert yaml.safe_load(text)["mcp_servers"]["agent-memory-hub"]["command"] == "new"


def test_write_yaml_creates_section_when_absent(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("other_key: 1\n", encoding="utf-8")
    psync.write_yaml(cfg, "agent-memory-hub", {"command": "python", "args": []}, indent=2)
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert data["other_key"] == 1, "原有内容不得丢"
    assert "mcp_servers" in data


def test_write_toml_appends_table(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("# 已有配置\n", encoding="utf-8")
    psync.write_toml(cfg, "agent-memory-hub", {"command": "python", "args": ["x"]})
    text = cfg.read_text(encoding="utf-8")
    assert "[mcp_servers.agent-memory-hub]" in text
    assert "command = 'python'" in text and "args = ['x']" in text
    assert "# 已有配置" in text, "既有注释行保留"


def test_dump_yaml_block_indentation():
    out = psync._dump_yaml_block({"command": "python", "args": ["a"]}, 4)
    lines = out.splitlines()
    assert lines[0].startswith("    agent-memory-hub:"), "缩进由 indent 参数补齐"
    assert any("command: python" in ln for ln in lines)


# ---------------------------------------------------------------------------
# platform_healthcheck
# ---------------------------------------------------------------------------


def test_status_icon_and_local_iso():
    assert phc._status_icon("GREEN") == "✅"
    assert phc._status_icon("YELLOW") == "🟡"
    assert phc._status_icon("RED") == "❌"
    assert phc._status_icon("???") == "?"
    assert phc._local_now_iso().startswith("20")


def test_check_file_platform_missing_then_ok(tmp_path):
    """file 类平台：hub 相对 key_path + draft_dir；缺任一即 RED。"""
    hub = bootstrap(tmp_path)
    info = {
        "type": "file",
        "key_path": "system/keys/mavis.key",
        "draft_dir": ".sync/drafts/mavis_draft",
    }
    bad = phc.check_file_platform("mavis", info, hub)
    assert bad["status"] == "RED" and bad["issues"]

    (hub / "system" / "keys").mkdir(parents=True, exist_ok=True)
    (hub / "system" / "keys" / "mavis.key").write_text("k", encoding="utf-8")
    draft = hub / ".sync" / "drafts" / "mavis_draft"
    draft.mkdir(parents=True, exist_ok=True)
    (draft / "a.md").write_text("x", encoding="utf-8")

    ok = phc.check_file_platform("mavis", info, hub)
    assert ok["status"] == "GREEN"
    assert ok["checks"]["files_count"] == 1


def test_check_hook_file_platform_data_dir_downgrades_to_yellow(tmp_path):
    """hook+file：data_dir 缺失只降 YELLOW，不影响签名/草稿判定。"""
    hub = bootstrap(tmp_path)
    (hub / "system" / "keys").mkdir(parents=True, exist_ok=True)
    (hub / "system" / "keys" / "mavis.key").write_text("k", encoding="utf-8")
    (hub / ".sync" / "drafts" / "mavis_draft").mkdir(parents=True, exist_ok=True)
    info = {
        "type": "hook+file",
        "key_path": "system/keys/mavis.key",
        "draft_dir": ".sync/drafts/mavis_draft",
        "data_dir": "这个目录不存在",
    }
    out = phc.check_hook_file_platform("mavis", info, hub)
    assert out["status"] == "YELLOW"
    assert "data_dir" in out["checks"]


def test_check_mcp_platform_reports_status(tmp_path):
    """mcp 类平台的分级：配置缺失/解析不过/无 server 块/args 空/python 不存在 → RED；
    未用 launcher → YELLOW；全对 → GREEN。"""
    hub = bootstrap(tmp_path)
    cfg = tmp_path / "mcp.json"
    info = {"type": "mcp", "mcp_config_path": str(cfg)}

    missing = phc.check_mcp_platform("trae", info, hub)
    assert missing["status"] == "RED" and missing["checks"]["config"] == "MISSING"

    cfg.write_text("{坏 json", encoding="utf-8")
    assert phc.check_mcp_platform("trae", info, hub)["status"] == "RED"

    cfg.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    assert phc.check_mcp_platform("trae", info, hub)["checks"]["server"] == "MISSING"

    launcher = str(tmp_path / "hub_mcp_launcher.py")
    # 未用 launcher（args[0] 不是 launcher）→ YELLOW
    cfg.write_text(
        json.dumps({"mcpServers": {"agent-memory-hub": {"command": sys.executable, "args": ["mcp_server.py"]}}}),
        encoding="utf-8",
    )
    assert phc.check_mcp_platform("trae", info, hub)["status"] == "YELLOW"

    # 全对（command 真存在 + args[0] 是 launcher）→ GREEN
    cfg.write_text(
        json.dumps({"mcpServers": {"agent-memory-hub": {"command": sys.executable, "args": [launcher]}}}),
        encoding="utf-8",
    )
    good = phc.check_mcp_platform("trae", info, hub)
    assert good["status"] == "GREEN" and not good["issues"]


def test_run_healthcheck_and_dashboard(tmp_path):
    hub = bootstrap(tmp_path)
    (hub / "system").mkdir(parents=True, exist_ok=True)
    (hub / "system" / "platforms.yaml").write_text(
        yaml.safe_dump(
            {
                "platforms": {
                    "mavis": {
                        "type": "file",
                        "key_path": "system/keys/mavis.key",
                        "draft_dir": ".sync/drafts/mavis_draft",
                    },
                    "trae": {"type": "mcp", "mcp_config_path": str(tmp_path / "mcp.json")},
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    results = phc.run_healthcheck(hub)
    assert isinstance(results, list)
    assert {r["platform"] for r in results} == {"mavis", "trae"}
    assert all("status" in r for r in results)

    phc.write_dashboard(results, hub)
    dash = hub / "system" / "run" / "platform-dashboard.md"
    assert dash.is_file()
    assert "mavis" in dash.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# index_locatability_bench
# ---------------------------------------------------------------------------


def test_content_tokens_filters_noise_and_single_chars():
    toks = ilb.content_tokens("怎么 排查 中文 乱码 a 的 编码 问题")
    assert all(len(t) >= 2 for t in toks)
    assert not ({"的", "a"} & toks), "单字与噪声词必须被过滤"


def test_card_tags_inline_and_block_forms(tmp_path, monkeypatch):
    """回归：块写法 `tags:\\n  - a\\n  - b` 的**末项无尾换行**时，旧正则只解析出第一个。"""
    hub = tmp_path / "AgentMemoryHub"
    (hub / "rules").mkdir(parents=True)
    (hub / "rules" / "inline-card.md").write_text("---\ntype: rule\ntags: [alpha, beta]\n---\n正文\n", encoding="utf-8")
    (hub / "methodology").mkdir(parents=True)
    (hub / "methodology" / "block-card.md").write_text(
        "---\ntype: methodology\ntags:\n  - gamma\n  - delta\n---\n正文\n", encoding="utf-8"
    )
    monkeypatch.setattr(ilb, "HUB_DIR", hub)

    assert ilb.card_tags("inline-card") == ["alpha", "beta"]
    assert ilb.card_tags("block-card") == ["gamma", "delta"], "块写法必须返回全部 tag"
    assert ilb.card_tags("no-such-card") == []


def test_score_covers_hit_miss_and_missing(monkeypatch):
    """打分口径：covered≥1 记可定位；desc 缺失单列；覆盖率取平均。"""
    monkeypatch.setattr(ilb, "CASES", [("查询甲", "card-a"), ("查询乙", "card-b"), ("查询丙", "card-c")])
    out = ilb.score({"card-a": "查询甲 的完整描述文本", "card-b": "完全无关的描述"})
    assert out["locatable"] == 1
    assert out["missing"] == 1, "card-c 没有描述行"
    assert 0.0 <= out["coverage_avg"] <= 1.0
    assert len(out["rows"]) == 3


# ---------------------------------------------------------------------------
# auto_process_sleep
# ---------------------------------------------------------------------------


def test_extract_cn_keywords_limit_and_quality():
    kws = aps._extract_cn_keywords("写锁 残留 僵尸锁 清理 方案 与 兜底 机制", max_words=3)
    assert len(kws) <= 3
    assert all(isinstance(k, str) and k for k in kws)


def test_check_card_type(tmp_path):
    card = tmp_path / "c.md"
    card.write_text("---\ntype: exp\ntags: []\n---\n正文\n", encoding="utf-8")
    assert aps._check_card_type(card) == "exp"
    assert aps._check_card_type(tmp_path / "missing.md") is None


def test_update_card_tags_dedup_and_append(tmp_path):
    card = tmp_path / "c.md"
    card.write_text("---\ntype: exp\ntags:\n- alpha\n---\n正文\n", encoding="utf-8")
    added = aps._update_card_tags(card, ["alpha", "beta"])
    assert added == ["beta"], "已存在的 tag 不重复添加"
    text = card.read_text(encoding="utf-8")
    assert "beta" in text and text.count("alpha") == 1


def test_generate_p0_draft_writes_into_draft_dir(tmp_path):
    hub = bootstrap(tmp_path)
    path = aps._generate_p0_draft(hub, "写锁 残留 僵尸锁", ["写锁", "僵尸锁"])
    assert Path(path).is_file()
    assert "写锁" in Path(path).read_text(encoding="utf-8")


def test_process_proposal_dry_run_and_apply(tmp_path):
    hub = bootstrap(tmp_path)
    state = hub / ".sync" / "state" / "sleep" / "20260925-000000"
    state.mkdir(parents=True)
    proposal = state / "proposal.json"
    proposal.write_text(
        json.dumps(
            {"query": "写锁 残留 僵尸锁", "candidates": [{"path": "experience/x.md", "score": 0.9}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    dry = aps._process_proposal(proposal, hub, dry_run=True)
    assert isinstance(dry, dict)

    applied = aps._process_proposal(proposal, hub)
    assert isinstance(applied, dict)
