"""本地 LLM 健康检测模块：检测 LM Studio / LLM 等本地 LLM 服务状态，支持自动重连。

功能：
1. 快速检测本地 LLM 服务是否在线
2. 检测指定模型是否可用
3. 连接失败时自动重试
4. 提供降级状态管理（记录最近一次失败时间）
5. 兼容 LM Studio (端口 1234) 和 LLM (端口 11434)
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# 健康检测阈值配置
RESPONSE_TIME_WARNING_THRESHOLD = 3000  # 响应时间警告阈值（毫秒）
RESPONSE_TIME_CRITICAL_THRESHOLD = 5000  # 响应时间严重阈值（毫秒）


@dataclass
class LLMStatus:
    """本地 LLM 服务状态。"""
    available: bool
    url: str
    models: list[str] = field(default_factory=list)
    last_check: float = 0.0
    last_error: str = ""
    response_time: float = 0.0


class LLMHealthChecker:
    """本地 LLM 健康检测器。

    支持：
    - 快速检测（超时 3s）
    - 模型可用性检测
    - 失败冷却（避免反复请求已崩溃的服务）
    - 兼容 LM Studio 和 LLM 的 API 端点
    """

    # 单例缓存
    _instance: LLMHealthChecker | None = None

    def __init__(
        self,
        base_url: str = "http://localhost:1234",
        check_timeout: float = 3.0,
        cooldown_after_fail: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.check_timeout = check_timeout
        self.cooldown_after_fail = cooldown_after_fail
        self._last_fail_time: float = 0.0
        self._cached_status: LLMStatus | None = None

    @classmethod
    def get_instance(cls, base_url: str = "http://localhost:1234") -> LLMHealthChecker:
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls(base_url=base_url)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）。"""
        cls._instance = None

    def is_available(self) -> bool:
        """快速检测 LM Studio / LLM 是否在线。"""
        # 冷却期内直接返回不可用
        if time.time() - self._last_fail_time < self.cooldown_after_fail:
            return False

        try:
            # LM Studio /v1/models 作为健康检测端点
            endpoint = f"{self.base_url}/v1/models" if "1234" in self.base_url else f"{self.base_url}/api/tags"
            req = urllib.request.Request(
                endpoint,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.check_timeout) as resp:
                resp.read()
                self._last_fail_time = 0.0  # 重置失败时间
                return True
        except Exception as e:
            self._last_fail_time = time.time()
            self._cached_status = LLMStatus(
                available=False,
                url=self.base_url,
                last_check=time.time(),
                last_error=str(e),
            )
            return False

    def check_model(self, model: str) -> bool:
        """检测指定模型是否可用。"""
        if not self.is_available():
            return False

        try:
            if "1234" in self.base_url:
                # LM Studio: 获取模型列表进行匹配
                status = self.get_status()
                return model in status.models
            
            req = urllib.request.Request(
                f"{self.base_url}/api/show",
                data=f'{{"name":"{model}"}}'.encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.check_timeout) as resp:
                import json
                data = json.loads(resp.read())
                return bool(data.get("model"))
        except Exception:
            return False

    def get_status(self) -> LLMStatus:
        """获取完整状态（含模型列表）。"""
        start = time.time()
        try:
            if "1234" in self.base_url:
                # LM Studio 模型列表获取
                req = urllib.request.Request(
                    f"{self.base_url}/v1/models",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.check_timeout) as resp:
                    import json
                    data = json.loads(resp.read())
                    models = [m["id"] for m in data.get("data", [])]
                    self._last_fail_time = 0.0
                    status = LLMStatus(
                        available=True,
                        url=self.base_url,
                        models=models,
                        last_check=time.time(),
                        response_time=time.time() - start,
                    )
                    self._cached_status = status
                    return status

            req = urllib.request.Request(
                f"{self.base_url}/api/tags",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.check_timeout) as resp:
                import json
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                self._last_fail_time = 0.0
                status = LLMStatus(
                    available=True,
                    url=self.base_url,
                    models=models,
                    last_check=time.time(),
                    response_time=time.time() - start,
                )
                self._cached_status = status
                return status
        except Exception as e:
            self._last_fail_time = time.time()
            status = LLMStatus(
                available=False,
                url=self.base_url,
                last_check=time.time(),
                last_error=str(e),
                response_time=time.time() - start,
            )
            self._cached_status = status
            return status

    def get_cached_status(self) -> LLMStatus | None:
        """获取上次缓存的状态（不发起请求）。"""
        return self._cached_status

    def reset_cooldown(self) -> None:
        """重置冷却期（手动触发重连检测）。"""
        self._last_fail_time = 0.0


def create_llm_health_wrapper(
    fn: Callable[..., str],
    on_unavailable: Callable[..., str] | None = None,
    base_url: str = "http://localhost:11434",
) -> Callable[..., str]:
    """创建 LLM 健康检测包装器。

    用法：
        def my_llm_call():
            # 实际 LLM 调用
            ...

        def fallback_to_gateway():
            # LLM 不可用时的降级方案
            ...

        safe_call = create_llm_health_wrapper(
            my_llm_call,
            on_unavailable=fallback_to_gateway
        )
        result = safe_call()  # 自动检测健康状态
    """
    checker = LLMHealthChecker.get_instance(base_url)

    def wrapper(*args, **kwargs) -> str:
        if not checker.is_available():
            if on_unavailable:
                print("[llm_health] LLM 不可用，执行降级方案")
                return on_unavailable(*args, **kwargs)
            raise ConnectionError(f"LLM 服务不可用: {checker._cached_status.last_error if checker._cached_status else '未知错误'}")
        return fn(*args, **kwargs)

    return wrapper


# 便捷函数
def quick_check(url: str = "http://localhost:11434") -> bool:
    """快速检测 LLM 是否在线。"""
    checker = LLMHealthChecker(base_url=url)
    return checker.is_available()


def check_model(model: str, url: str = "http://localhost:11434") -> bool:
    """检测指定模型是否可用。"""
    checker = LLMHealthChecker(base_url=url)
    return checker.check_model(model)


# ---------- 运行时自愈 ----------

# 开机自启同款 VBS（纯 ASCII，静默隐藏窗口拉起 lms server）
# 路径按当前用户 HOME 推导（不硬编码用户名），环境变量 LM_STUDIO_START_VBS 可显式覆盖
_LMS_AUTOSTART_VBS_DEFAULT = (
    "AppData/Local/Programs/LM Studio"
    "/resources/app/.webpack/start_lm_studio_api.vbs"
)


def _autostart_vbs_path() -> Path:
    """解析自愈拉起用 VBS 路径：环境变量优先，否则按用户 HOME 推导。"""
    override = os.environ.get("LM_STUDIO_START_VBS")
    if override:
        return Path(override)
    return Path.home() / _LMS_AUTOSTART_VBS_DEFAULT


# 每进程只自愈一次（防离线-重试死循环），测试可经 reset_self_heal_state() 重置
_self_heal_attempted = False


def _manual_offline_flag() -> Path:
    """手动下线标记文件（用户故意停服务省显存时，自愈不得救活）。"""
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".lmstudio-manual-offline"


def set_manual_offline(off: bool = True) -> Path:
    """开/关手动下线标记：置位暂停自愈，清除恢复自愈。返回标记路径。"""
    flag = _manual_offline_flag()
    if off:
        flag.touch()
    elif flag.exists():
        flag.unlink()
    return flag


def reset_self_heal_state() -> None:
    """重置自愈尝试标记（测试/长驻进程需要再次自愈时调用）。"""
    global _self_heal_attempted
    _self_heal_attempted = False


def ensure_llm_service(
    base_url: str = "http://localhost:1234",
    probe_timeout: float = 2.0,
    interval: float = 2.0,
    retries: int = 15,
    start_cmd: list[str] | None = None,
) -> bool:
    """检测本地 LLM 服务，离线则自动拉起一次（运行时自愈）。

    流程：在线 → 直接 True；离线 → 执行 start_cmd（默认 wscript 跑开机自启
    同款 VBS）→ 每 interval 秒探测一次、最多 retries 次等就绪。
    每进程生命周期只自愈一次：二次调用若上次失败直接返回 False，防死循环。
    拉起失败/超时的原因不静默吞掉：写 stderr 供巡检日志取证。
    """
    global _self_heal_attempted

    checker = LLMHealthChecker(base_url=base_url, check_timeout=probe_timeout)
    if checker.is_available():
        return True
    if _manual_offline_flag().exists():
        # 用户手动下线（如停服务省显存），视为有意为之，不自愈
        return False
    if _self_heal_attempted:
        return False
    _self_heal_attempted = True

    import subprocess
    import sys

    cmd = start_cmd or ["wscript.exe", str(_autostart_vbs_path())]
    try:
        subprocess.Popen(  # 固定路径 VBS，非用户输入
            cmd,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            ),
        )
    except OSError as e:
        print(f"[llm_health] 自愈拉起命令执行失败: {cmd} err={e}", file=sys.stderr)
        return False

    deadline = time.time() + interval * retries
    while time.time() < deadline:
        time.sleep(interval)
        checker.reset_cooldown()  # 绕开 30s 失败冷却，允许即时复测
        if checker.is_available():
            print(f"[llm_health] 自愈成功：LLM 服务已恢复在线 ({base_url})")
            return True
    print(
        f"[llm_health] 自愈失败：{base_url} 在 {interval * retries:.0f}s 内未就绪",
        file=sys.stderr,
    )
    return False


if __name__ == "__main__":
    # 自测
    checker = LLMHealthChecker()
    print("=== LLM 健康检测 ===")
    status = checker.get_status()
    print(f"可用: {status.available}")
    print(f"模型: {status.models}")
    print(f"响应时间: {status.response_time:.3f}s")
    if status.last_error:
        print(f"错误: {status.last_error}")
