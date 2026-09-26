"""flywheel 日报推送通道单测（2026-09-25 SPLIT2 补网：_cmd_daily_report 原先无任何测试）。

只测拆分出来的纯逻辑/通道函数；真实网络与子进程一律打桩。
"""

import io
import urllib.request
from argparse import Namespace
from contextlib import redirect_stdout
from types import SimpleNamespace

from scripts import flywheel as fw


def _args(**overrides):
    base = {
        "hermes_target": None,
        "serverchan_key": None,
        "pushplus_token": None,
        "wecom_webhook": None,
        "feishu_webhook": None,
        "push_config": None,
    }
    return Namespace(**{**base, **overrides})


def test_collect_push_kwargs_keeps_only_provided(tmp_path):
    kwargs = fw._collect_push_kwargs(_args(wecom_webhook="http://x", push_config=""))
    assert kwargs == {"wecom_webhook": "http://x"}


def test_generate_report_returns_none_on_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr(
        fw.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=3, stdout="", stderr="boom"),
    )
    assert fw._generate_report(tmp_path, tmp_path) is None


def test_generate_report_strips_stdout(monkeypatch, tmp_path):
    monkeypatch.setattr(
        fw.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="  # 日报\n正文\n  ", stderr=""),
    )
    assert fw._generate_report(tmp_path, tmp_path) == "# 日报\n正文"


def test_post_json_failure_is_returned_not_raised(monkeypatch):
    def boom(*a, **k):
        raise OSError("connect refused")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    res = fw._post_json("http://127.0.0.1:9/x", {"a": 1})
    assert res["success"] is False
    assert "connect refused" in res["error"]


class _FakeResp:
    """最小上下文管理器响应桩（urlopen 返回值需支持 with）"""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b"ok"


def test_push_webhook_records_channel_and_prints(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    results: list[dict] = []
    out = io.StringIO()
    with redirect_stdout(out):
        fw._push_webhook("wecom", "企业微信", "http://127.0.0.1:9/w", {"msgtype": "text"}, results)
    assert results == [{"success": True, "channel": "wecom"}]
    assert "正在推送到企业微信" in out.getvalue()
    assert "✅ 成功" in out.getvalue()


def test_push_report_rejects_push_config_but_keeps_others(monkeypatch):
    """--push-config 无源码可考 → 明确报错并剔除，但不影响其它显式通道"""
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    kwargs = {"push_config": "cfg.yaml", "wecom_webhook": "http://127.0.0.1:9/w"}
    out = io.StringIO()
    with redirect_stdout(out):
        results = fw._push_report(kwargs, "标题", "正文")
    assert "push_config" not in kwargs  # 已剔除
    assert [r["channel"] for r in results] == ["wecom"]
