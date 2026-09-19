"""router_sync 单测：平台适配器覆盖度检查（config ↔ platform_bridge 一致性）

回归背景（2026-09-19）：
    scripts/router_sync.py 曾自持硬编码清单 {"hermes","trae","code","workbuddy"}，
    而 mavis / deepseek 早已登记进 hub.config.yaml、记忆文件也已由中枢同步维护，
    检查却持续报"未实现适配器"→ 纯假告警，把巡检退出码从 0 拉到 2。
    修复：覆盖度事实来源收敛到 platform_bridge.ADAPTER_REGISTRY。

本文件锁定两条不变量：
    ① 假告警不得复现 —— 已登记适配器的平台不产生 warning；
    ② 真缺口仍须暴露 —— 登记进 config 但未进注册表的平台必须 warning。
"""

from pathlib import Path

import pytest
import yaml

# 同 test_platform_bridge：依赖 hub-engine 已在 sys.path（由 pytest rootdir/conftest 保证）
from scripts.bootstrap_hub import bootstrap
from scripts.router_sync import _check_platforms, _run
from tools.platform_bridge import SUPPORTED_PLATFORMS

# 中枢真实配置相对 hub-engine/tests/ 的位置（hub-engine/tests → 工程根 → AgentMemoryHub）
_REAL_HUB = Path(__file__).resolve().parents[2] / "AgentMemoryHub"


def _register_platform(root: Path, name: str, mem_dir: Path) -> None:
    """在测试中枢的 hub.config.yaml 登记一个平台"""
    cfg_path = root / "hub.config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    data.setdefault("platforms", {})[name] = {
        "memory_dir": str(mem_dir),
        "target_file": "MEMORY.md",
    }
    cfg_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def test_supported_platforms_covers_mavis_and_deepseek():
    """mavis / deepseek 必须在适配器注册表内（本次修复的核心断言）"""
    assert "mavis" in SUPPORTED_PLATFORMS
    assert "deepseek" in SUPPORTED_PLATFORMS
    # 原有 4 平台不得因重构被误删
    assert {"hermes", "trae", "code", "workbuddy"} <= SUPPORTED_PLATFORMS


def test_check_platforms_no_warning_for_registered_platforms(tmp_path):
    """已登记适配器的平台 → 0 warning（假告警回归护栏）"""
    root = bootstrap(tmp_path / "hub")
    mem = tmp_path / "platforms"
    mem.mkdir(exist_ok=True)
    (mem / "MEMORY.md").write_text("## 卡片\n正文\n", encoding="utf-8")

    for name in ("mavis", "deepseek"):
        _register_platform(root, name, mem)

    warnings, infos = _check_platforms(root)
    assert warnings == []
    assert infos == []


def test_check_platforms_warns_for_unregistered_platform(tmp_path):
    """登记进 config 但未进 ADAPTER_REGISTRY → 必须 warning（真缺口不得被吞）"""
    root = bootstrap(tmp_path / "hub")
    mem = tmp_path / "platforms"
    mem.mkdir(exist_ok=True)
    (mem / "MEMORY.md").write_text("## 卡片\n正文\n", encoding="utf-8")

    _register_platform(root, "testplat", mem)

    warnings, infos = _check_platforms(root)
    assert len(warnings) == 1
    assert "testplat" in warnings[0]
    assert "ADAPTER_REGISTRY" in warnings[0]
    # 未登记平台只报 warn，不额外产生 info（记忆文件本身是可达的）
    assert infos == []


def test_unreachable_memory_file_is_info_not_warning(tmp_path):
    """记忆文件不可达只是 info（不拉高退出码到 2）"""
    root = bootstrap(tmp_path / "hub")
    _register_platform(root, "mavis", tmp_path / "not-exist")

    warnings, infos = _check_platforms(root)
    assert warnings == []
    assert len(infos) == 1
    assert "不可达" in infos[0]


def test_run_exit_code_zero_for_clean_hub(tmp_path):
    """干净中枢 → _run 退出码 0"""
    root = bootstrap(tmp_path / "hub")
    assert _run(root)["exit_code"] == 0


@pytest.mark.skipif(
    not (_REAL_HUB / "hub.config.yaml").is_file(),
    reason="真实 AgentMemoryHub 不在预期位置，跳过（CI/异机环境）",
)
def test_real_hub_config_platforms_all_have_adapters():
    """不变量：真实中枢 config 里登记的每个平台都必须有显式适配器。

    这是本次 bug 的直接护栏 —— 新增平台只改 config 不改注册表时，本测试立刻红。
    """
    data = yaml.safe_load((_REAL_HUB / "hub.config.yaml").read_text(encoding="utf-8"))
    configured = set((data or {}).get("platforms", {}))
    missing = sorted(configured - SUPPORTED_PLATFORMS)
    assert missing == [], (
        f"平台 {missing} 已在 hub.config.yaml 登记但缺适配器登记；"
        f"请在 tools/platform_bridge.ADAPTER_REGISTRY 补一行"
    )
