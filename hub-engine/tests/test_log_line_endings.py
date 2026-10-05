"""append-only 时间线的**行尾**守卫（2026-10-05 立）。

## 为什么

`retro/log.md` 实测 `LF×2239 + CRLF×8` = **混合行尾**，巡检 `encoding` 步 FAIL、退出码 2。
根因不在"某个平台手抖"，在代码：`sync.py::_append_log` 用 `open(log, "a", encoding="utf-8")`
**缺 `newline=`** ⇒ Windows 文本模式下 `\\n` 被翻译成 `\\r\\n`，每次 ingest 向 LF 基础文件
追加 CRLF 行。

为何只有它爆：其它写方都走**整文件重写**（全 CRLF 也算"一致"，`check_encoding` 只判"混合"），
只有 **append-only** 会把两种行尾混在一个文件里。所以本守卫专打"追加写"这一类。
"""

from __future__ import annotations

from sync import _append_log


def test_append_log_writes_lf_only(tmp_path):
    """追加写必须产出纯 LF（Windows 上缺 newline= 会得到 CRLF）。"""
    root = tmp_path / "hub"
    root.mkdir()
    _append_log(root, "ingest", "第一条")
    _append_log(root, "ingest", "第二条")

    raw = (root / "retro" / "log.md").read_bytes()
    assert b"\r\n" not in raw, "append-only 日志出现 CRLF——newline= 又丢了？"
    assert raw == b"## [" + raw[4:]  # 形状未变（首行仍是 ## [ 开头）
    assert raw.count(b"\n") == 2 and raw.endswith(b"\n")
    assert raw.decode("utf-8").count("## [") == 2
