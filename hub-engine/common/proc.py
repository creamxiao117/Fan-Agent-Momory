"""跨进程调用统一入口：**全链路钉死 UTF-8**（解码端 + 产出端同时钉）。

2026-10-21 中枢体检实测（Windows 中文环境，ACP=936）：

1. **解码端**：``subprocess.run(..., text=True)`` 不带 ``encoding=`` 时按**本地编码（GBK）**
   解码子进程输出 ⇒ 遇中文即 ``UnicodeDecodeError``。
   实测崩点：``engine.py status --json`` 读 ``git log`` 的中文提交信息
   → ``'gbk' codec can't decode byte 0x92`` → 线程崩 → ``stdout`` 变 ``None``
   → ``AttributeError: 'NoneType' object has no attribute 'strip'``（**退出码 1，日志被截断**）。
2. **产出端**：若子进程是 Python 而未钉 ``PYTHONUTF8``，它写出的 stdout **本身就是 GBK 字节**
   ⇒ 只把解码端钉成 UTF-8，等于把「崩溃」换成「**静默乱码**」（更坏：乱码会被写进卡片/日报）。
   实测：``child stdout encoding = gbk``（去掉 ``PYTHONUTF8``/``PYTHONIOENCODING`` 后）。

所以**两端都要钉**，这与 ``rules/chinese-text-encoding-discipline``（iron）同口径：
「全链路钉死 UTF-8；凡跨进程、跨语言、跨终端边界，**两端都显式声明编码，禁依赖默认值**」。

用法::

    from common.proc import run_utf8
    r = run_utf8([sys.executable, "-m", "scripts.render_index", "--check"],
                 cwd=..., capture_output=True, text=True, timeout=60)

- 解码端：统一 ``encoding="utf-8"`` + ``errors="replace"``（永不因解码崩）。
- 产出端：给子进程注入 ``PYTHONUTF8=1`` / ``PYTHONIOENCODING=utf-8``（**setdefault**：
  调用方显式声明的值优先，尊重显式意图）。
- 显式要二进制（``text=False``）的调用不受影响，只注入产出端环境。
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

__all__ = ["utf8_env", "run_utf8"]

#: 子进程 Python 侧的 UTF-8 开关（产出端；用 setdefault 语义，见 utf8_env 文档）
_UTF8_ENV_KEYS = {
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
}


def utf8_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """返回带 UTF-8 开关的子进程环境变量副本。

    ``base=None`` ⇒ 以当前进程环境为底；否则以 ``base`` 为底（**不修改入参**）。
    已显式声明的 ``PYTHONUTF8`` / ``PYTHONIOENCODING`` **保持调用方的值**——
    「两端都显式声明」意味着显式意图优先于默认值。
    """
    env = dict(os.environ if base is None else base)
    for key, value in _UTF8_ENV_KEYS.items():
        env.setdefault(key, value)
    return env


def run_utf8(argv: Any, *, env: dict[str, str] | None = None, **kwargs: Any) -> subprocess.CompletedProcess:
    """``subprocess.run`` 的 UTF-8 版（解码端 + 产出端同时钉死）。

    - ``encoding``/``errors``/``text`` 用 ``setdefault``：调用方已显式声明的编码**不被覆盖**。
    - ``env`` 始终经 :func:`utf8_env` 处理（子进程产出端钉 UTF-8）。
    """
    kwargs["env"] = utf8_env(env)
    if kwargs.get("text") is False:
        # 调用方显式要二进制：尊重之，只注入产出端环境
        return subprocess.run(argv, **kwargs)
    kwargs.setdefault("text", True)
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    return subprocess.run(argv, **kwargs)
