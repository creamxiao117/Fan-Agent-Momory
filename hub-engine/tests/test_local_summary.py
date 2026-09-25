# @version V1.0 / 2026-09-25 / P1-f 夜间摘要自愈（审计 I-5）
"""`local_summary` 的自愈与判定契约。

## 背景

2026-09-25 审计 I-5：LM Studio 家目录下的 `.internal\\temp` 一旦缺失（重启/升级后未重建，
或被“清临时文件”的例程带走），**所有模型** JIT 加载都会 400：

    Failed to load model "<id>". Error: ENOENT: no such file or directory,
    mkdtemp '<LMSTUDIO_HOME>\\.internal\\temp\\lmstudio-chat-template-XXXXXX'

后果是夜间摘要**每晚静默为空**（exit=2），需人工排查才定位。
现把该故障变成自愈：从错误体解析目录 → 建回 → 重试一次。
"""

from __future__ import annotations

from scripts.local_summary import _heal_missing_temp_dir


def test_heals_by_creating_temp_dir_from_error_body(tmp_path):
    """能从 mkdtemp 错误体里解析出目录并建回来。"""
    body = (
        '{"error": {"message": "Failed to load model \\"qwen3.8-27b-fast\\". '
        f"Error: ENOENT: no such file or directory, mkdtemp '{tmp_path}"
        "\\.internal\\temp\\lmstudio-chat-template-XXXXXX'\"}}"
    )
    assert not (tmp_path / ".internal" / "temp").exists()

    assert _heal_missing_temp_dir(body) is True
    assert (tmp_path / ".internal" / "temp").is_dir()


def test_returns_false_for_unrelated_errors():
    """其它 400（模型未加载 / 上下文超限）不得触发自愈。"""
    assert _heal_missing_temp_dir('{"error":{"message":"No models loaded"}}') is False
    assert _heal_missing_temp_dir("context length exceeded") is False
    assert _heal_missing_temp_dir("") is False


def test_does_not_heal_unrecognized_paths(tmp_path):
    """只认 LM Studio 的 chat-template 临时名：其它路径一律不自愈（不能拿报错当 mkdir 指令）。"""
    assert _heal_missing_temp_dir(f"mkdtemp '{tmp_path}\\.internal'") is False
    assert _heal_missing_temp_dir(f"mkdtemp '{tmp_path}\\whatever'") is False


def test_idempotent_when_dir_already_exists(tmp_path):
    """目录已存在时仍返回 True（调用方据此决定重试）。"""
    target = tmp_path / ".internal" / "temp"
    target.mkdir(parents=True)
    body = f"mkdtemp '{target}\\lmstudio-chat-template-XXXXXX'"
    assert _heal_missing_temp_dir(body) is True
    assert target.is_dir()
