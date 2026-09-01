"""ensure_llm_service 运行时自愈单元测试（WORK.md 第20条）

全部经桩隔离：不发真实 HTTP、不执行真实 VBS、不真实 sleep。
"""

import pytest

from tools import llm_health
from tools.llm_health import ensure_llm_service


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch, tmp_path):
    """每测试重置自愈标记，并把手动下线标记指到临时目录。"""
    llm_health.reset_self_heal_state()
    monkeypatch.setattr(
        llm_health,
        "_manual_offline_flag",
        lambda: tmp_path / ".lmstudio-manual-offline",
    )


def _patch_checker(monkeypatch, avail_sequence):
    """按调用序列控制 is_available 返回值，并记录调用次数。"""
    calls = {"available": 0, "reset": 0}
    seq = list(avail_sequence)

    def fake_is_available(self):
        calls["available"] += 1
        return seq.pop(0) if seq else False  # 序列耗尽视为持续离线（防假绿）

    monkeypatch.setattr(
        llm_health.LLMHealthChecker, "is_available", fake_is_available
    )
    monkeypatch.setattr(
        llm_health.LLMHealthChecker,
        "reset_cooldown",
        lambda self: calls.__setitem__("reset", calls["reset"] + 1),
    )
    return calls


def test_online_returns_true_without_start(monkeypatch):
    """服务在线 → 直接 True，不得触发拉起命令。"""
    _patch_checker(monkeypatch, [True])

    def boom(*a, **k):
        raise AssertionError("在线时不应执行拉起命令")

    monkeypatch.setattr("subprocess.Popen", boom)
    assert (
        ensure_llm_service(
            base_url="http://x:1", interval=0.01, retries=2, start_cmd=["no"]
        )
        is True
    )
    assert llm_health._self_heal_attempted is False


def test_offline_self_heals_once(monkeypatch):
    """离线 → 执行一次 start_cmd → 轮询等到在线 → True。"""
    calls = _patch_checker(monkeypatch, [False, False, True])  # 首探离线,第2探在线
    executed = []

    class FakePopen:
        def __init__(self, cmd, **kw):
            executed.append(cmd)

    monkeypatch.setattr("subprocess.Popen", FakePopen)
    ok = ensure_llm_service(
        base_url="http://x:1",
        interval=0.01,
        retries=5,
        start_cmd=["fake.cmd", "arg"],
    )
    assert ok is True
    assert executed == [["fake.cmd", "arg"]]  # 恰好执行一次
    assert calls["available"] == 3  # 首探 + 轮询2次（第1次仍离线，第2次命中在线）


def test_offline_second_call_no_retry(monkeypatch):
    """防死循环：自愈已尝试过仍离线 → 二次调用直接 False，不再执行 start_cmd。"""
    _patch_checker(monkeypatch, [False, False, False])
    executed = []

    class FakePopen:
        def __init__(self, cmd, **kw):
            executed.append(cmd)

    monkeypatch.setattr("subprocess.Popen", FakePopen)
    # 第一次：轮询耗尽 → False
    r1 = ensure_llm_service(
        base_url="http://x:1",
        interval=0.01,
        retries=2,
        start_cmd=["fake.cmd"],
    )
    assert r1 is False
    assert len(executed) == 1
    # 第二次：直接 False，不再拉起
    r2 = ensure_llm_service(base_url="http://x:1", interval=0.01, retries=2)
    assert r2 is False
    assert len(executed) == 1


def test_manual_offline_flag_blocks_heal(monkeypatch, tmp_path):
    """手动下线标记存在 → 视为用户意图，不自愈。"""
    _patch_checker(monkeypatch, [False])
    executed = []
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda *a, **k: executed.append(a),
    )
    (tmp_path / ".lmstudio-manual-offline").touch()
    assert (
        ensure_llm_service(
            base_url="http://x:1", interval=0.01, retries=2, start_cmd=["fake.cmd"]
        )
        is False
    )
    assert executed == []
    assert llm_health._self_heal_attempted is False  # 标记拦截不计自愈次数


def test_start_cmd_oserror_returns_false(monkeypatch):
    """拉起命令本身失败（OSError）→ False 且不抛异常。"""
    _patch_checker(monkeypatch, [False])

    def boom(*a, **k):
        raise OSError("no wscript")

    monkeypatch.setattr("subprocess.Popen", boom)
    assert (
        ensure_llm_service(
            base_url="http://x:1", interval=0.01, retries=2, start_cmd=["x"]
        )
        is False
    )


def test_set_manual_offline_roundtrip(monkeypatch, tmp_path):
    """标记文件 set(True)/set(False) 创建/删除闭环。"""
    flag = tmp_path / ".lmstudio-manual-offline"
    monkeypatch.setattr(llm_health, "_manual_offline_flag", lambda: flag)
    assert llm_health.set_manual_offline(True) == flag and flag.exists()
    llm_health.set_manual_offline(False)
    assert not flag.exists()
