"""secret_sentry 测试：以实测误报为回归网。

## 为什么这个测试最重要

2026-09-24 重写前的旧哨兵**每晚报 26 条"高危"、抽样 6 条全为误报**，任务永久 exit 2。
本测试把**每一个实测误报样本**固化为用例——它们不是假想场景，是从真实中枢扫出来的原文。
少一个用例，就等于把那条误报放回生产。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.secret_sentry import (
    _looks_like_secret,
    _redact,
    main,
)


def _make_hub(tmp_path: Path, cards: dict[str, str]) -> Path:
    """构造最小中枢：cards = {相对路径: 正文}。"""
    root = tmp_path / "AgentMemoryHub"
    for rel, text in cards.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


# ── 实测误报样本（全部来自 2026-09-24 真实扫描） ────────────────────────────
# 每一条都曾经被判为"高危凭证泄漏"。它们必须永远不被命中。
FALSE_POSITIVE_LINES = [
    # ① sk-key 缺 \b 词边界 → 匹配词内 sk-
    "- v1 草稿（superseded）：`task-trigger-phrases-for-orchestration`",
    "| F2 | **未废弃** | 查 README 头部；查 repo 的 archived 字段 | autodesk-forge-forge-api-dotnet-cli |",
    "- opensk-embedded-fido2-firmware-blueprint    - 嵌入式安全密钥：本卡核心主题",
    # ② authorization 只匹配字段名 → 任何鉴权文档必报
    'curl -s -w "http=%{http_code}\\n" -H "Authorization: Bearer $KEY" \\',
    # ③ api-key-field 值不做形态校验 → 厂商名被当密钥
    "  4 键切换写入：peak→`provider=custom:duoyuanx`/`api_key=duoyuanx`",
    # ④ labeled-secret 缺 \b + 值吃进路径
    "**验证方式**：Python 递归下降解析器，隔离沙盒 F:/AgentMemoryT1/craftinginterpreters-blueprint-2026-09-07/",
    # ⑤ 占位符与文档示例
    "- 配置 `api_key: <YOUR_API_KEY_HERE_PLACEHOLDER>` 后重启",
    "- 示例：`sk-1234567890abcdefghijklmnop` 仅为格式示意（example）",
]


@pytest.mark.parametrize("line", FALSE_POSITIVE_LINES)
def test_real_false_positives_are_not_flagged(tmp_path: Path, line: str) -> None:
    """实测误报样本：在权威区也不得被判为高危。"""
    root = _make_hub(tmp_path, {"experience/card.md": f"# 卡\n\n{line}\n"})
    assert main(["--root", str(root), "--quiet"]) == 0, f"误报复现：{line}"


# ── 真泄漏必须被抓住 ────────────────────────────────────────────────────────


def test_real_leak_in_authority_zone_is_high(tmp_path: Path) -> None:
    """权威区里的 labeled secret（真实泄漏原文形态）→ 高危、退出码 2。"""
    root = _make_hub(
        tmp_path,
        {
            "experience/local-vision.md": (
                "# 本地视觉\n\n- Bearer API Key（8081/8082 /v1）：Zx9Qw2Er7Ty4Ui8Op5As3Df6Gh1Jk0Lm\n"
            )
        },
    )
    assert main(["--root", str(root), "--quiet"]) == 2


def test_real_leak_in_archive_zone_is_low(tmp_path: Path) -> None:
    """非权威区（归档）同一泄漏 → 低危、退出码 1。"""
    root = _make_hub(
        tmp_path,
        {
            ".sync/conflicts/_resolved/old.md": (
                "- Bearer API Key（8081/8082 /v1）：Zx9Qw2Er7Ty4Ui8Op5As3Df6Gh1Jk0Lm\n"
            )
        },
    )
    assert main(["--root", str(root), "--quiet"]) == 1


def test_known_key_exact_match_is_high(tmp_path: Path) -> None:
    """provider_keys.yaml 的真值出现在任意卡片 → 高危（最高精度通道）。"""
    root = _make_hub(
        tmp_path, {"experience/card.md": "# 卡\n\n值 = sk-proj-REALKEY1234567890abcd\n"}
    )
    (root / "provider_keys.yaml").write_text(
        "default: sk-proj-REALKEY1234567890abcd\n", encoding="utf-8"
    )
    assert main(["--root", str(root), "--quiet"]) == 2


def test_bare_sk_key_with_digits_is_high(tmp_path: Path) -> None:
    """真正的 sk- 密钥（含数字、有词边界）→ 高危。"""
    root = _make_hub(
        tmp_path,
        {"rules/x.md": "# 规则\n\n配置 sk-proj-AbCd1234EfGh5678IjKl9012 后生效\n"},
    )
    assert main(["--root", str(root), "--quiet"]) == 2


def test_clean_hub_exits_zero(tmp_path: Path) -> None:
    """干净中枢 → 退出码 0。"""
    root = _make_hub(tmp_path, {"rules/x.md": "# 规则\n\n无凭证。\n"})
    assert main(["--root", str(root), "--quiet"]) == 0


def test_missing_root_exits_two(tmp_path: Path) -> None:
    """中枢根不存在 → 退出码 2（不得静默通过）。"""
    assert main(["--root", str(tmp_path / "nope"), "--quiet"]) == 2


def test_report_written(tmp_path: Path) -> None:
    """日报必须落盘（即使干净也留档便于审查）。"""
    root = _make_hub(tmp_path, {"rules/x.md": "# 规则\n"})
    main(["--root", str(root), "--quiet"])
    assert (root / ".sync" / "secret_sentry_report.md").is_file()


# ── 单元：形态校验 ──────────────────────────────────────────────────────────


def test_looks_like_secret_rules() -> None:
    """形态校验的四条判据逐条验证。"""
    # 短 → 否
    assert not _looks_like_secret("duoyuanx")
    # 长但无数字 → 否
    assert not _looks_like_secret("task-trigger-phrases-for-orchestration")
    # 长、含数字，但是连字符 slug → 否
    assert not _looks_like_secret("embedded-fido2-firmware-blueprint")
    # 含路径分隔符 → 否
    assert not _looks_like_secret("/AgentMemoryT1/blueprint-2026-09-07/")
    # 真密钥形态 → 是
    assert _looks_like_secret("Zx9Qw2Er7Ty4Ui8Op5As3Df6Gh1Jk0Lm")
    assert _looks_like_secret("sk-proj-AbCd1234EfGh5678IjKl9012")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Zx9Qw2Er7Ty4Ui8Op5As3Df6Gh1Jk0Lm", "Zx9Q...k0Lm"),
        ("short", "***"),
    ],
)
def test_redact_never_leaks_full_value(value: str, expected: str) -> None:
    """脱敏：日报里不得出现完整凭证（否则等于把泄漏抄了一遍）。"""
    assert _redact(value) == expected
