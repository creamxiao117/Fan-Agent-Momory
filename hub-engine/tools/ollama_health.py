"""Ollama 健康检测模块：检测 Ollama 服务状态，支持自动重连。

功能：
1. 快速检测 Ollama 服务是否在线
2. 检测指定模型是否可用
3. 连接失败时自动重试
4. 提供降级状态管理（记录最近一次失败时间）
"""

from __future__ import annotations

import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class OllamaStatus:
    """Ollama 服务状态。"""
    available: bool
    url: str
    models: list[str] = field(default_factory=list)
    last_check: float = 0.0
    last_error: str = ""
    response_time: float = 0.0


class OllamaHealthChecker:
    """Ollama 健康检测器。

    支持：
    - 快速检测（超时 3s）
    - 模型可用性检测
    - 失败冷却（避免反复请求已崩溃的服务）
    """

    # 单例缓存
    _instance: OllamaHealthChecker | None = None

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        check_timeout: float = 3.0,
        cooldown_after_fail: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.check_timeout = check_timeout
        self.cooldown_after_fail = cooldown_after_fail
        self._last_fail_time: float = 0.0
        self._cached_status: OllamaStatus | None = None

    @classmethod
    def get_instance(cls, base_url: str = "http://localhost:1234") -> OllamaHealthChecker:
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls(base_url=base_url)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）。"""
        cls._instance = None

    def is_available(self) -> bool:
        """快速检测 LM Studio / Ollama 是否在线。"""
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
            self._cached_status = OllamaStatus(
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

    def get_status(self) -> OllamaStatus:
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
                    status = OllamaStatus(
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
                status = OllamaStatus(
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
            status = OllamaStatus(
                available=False,
                url=self.base_url,
                last_check=time.time(),
                last_error=str(e),
                response_time=time.time() - start,
            )
            self._cached_status = status
            return status

    def get_cached_status(self) -> OllamaStatus | None:
        """获取上次缓存的状态（不发起请求）。"""
        return self._cached_status

    def reset_cooldown(self) -> None:
        """重置冷却期（手动触发重连检测）。"""
        self._last_fail_time = 0.0


def create_ollama_health_wrapper(
    fn: Callable[..., str],
    on_unavailable: Callable[..., str] | None = None,
    base_url: str = "http://localhost:11434",
) -> Callable[..., str]:
    """创建 Ollama 健康检测包装器。

    用法：
        def my_ollama_call():
            # 实际 Ollama 调用
            ...

        def fallback_to_gateway():
            # Ollama 不可用时的降级方案
            ...

        safe_call = create_ollama_health_wrapper(
            my_ollama_call,
            on_unavailable=fallback_to_gateway
        )
        result = safe_call()  # 自动检测健康状态
    """
    checker = OllamaHealthChecker.get_instance(base_url)

    def wrapper(*args, **kwargs) -> str:
        if not checker.is_available():
            if on_unavailable:
                print(f"[ollama_health] Ollama 不可用，执行降级方案")
                return on_unavailable(*args, **kwargs)
            raise ConnectionError(f"Ollama 服务不可用: {checker._cached_status.last_error if checker._cached_status else '未知错误'}")
        return fn(*args, **kwargs)

    return wrapper


# 便捷函数
def quick_check(url: str = "http://localhost:11434") -> bool:
    """快速检测 Ollama 是否在线。"""
    checker = OllamaHealthChecker(base_url=url)
    return checker.is_available()


def check_model(model: str, url: str = "http://localhost:11434") -> bool:
    """检测指定模型是否可用。"""
    checker = OllamaHealthChecker(base_url=url)
    return checker.check_model(model)


if __name__ == "__main__":
    # 自测
    checker = OllamaHealthChecker()
    print("=== Ollama 健康检测 ===")
    status = checker.get_status()
    print(f"可用: {status.available}")
    print(f"模型: {status.models}")
    print(f"响应时间: {status.response_time:.3f}s")
    if status.last_error:
        print(f"错误: {status.last_error}")
