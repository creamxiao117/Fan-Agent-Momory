"""弹性管道（Resilience Pipeline）：为外部调用提供 Retry/Timeout/CircuitBreaker/Fallback 容错策略。

借鉴自 gh-app-vnext-polly 架构，纯 Python 实现，无外部依赖。
管道内策略按配置顺序包裹目标函数，形成责任链。

核心模式：
- Builder 流式配置：ResiliencePipelineBuilder().add_retry(...).add_timeout(...).build()
- 策略链式组合：每个策略包裹下一层，依次执行
- ResilienceContext：跨策略共享状态的上下文对象
"""

from __future__ import annotations

import functools
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 上下文与事件
# ---------------------------------------------------------------------------

@dataclass
class ResilienceContext:
    """管道执行上下文：跨策略共享状态。"""
    attempt: int = 0
    start_time: float = 0.0
    result: Any = None
    exception: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[PipelineEvent] = field(default_factory=list)

    def reset(self) -> None:
        self.attempt = 0
        self.start_time = 0.0
        self.result = None
        self.exception = None
        self.metadata.clear()
        self.events.clear()

    def add_event(self, stage: str, attempt: int, elapsed: float, ok: bool, detail: str = "") -> PipelineEvent:
        """添加事件到上下文（供管道收集）。"""
        evt = PipelineEvent(stage=stage, attempt=attempt, elapsed=elapsed, ok=ok, detail=detail)
        self.events.append(evt)
        return evt


@dataclass
class PipelineEvent:
    """管道事件：可用于日志/遥测。"""
    stage: str
    attempt: int
    elapsed: float
    ok: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# 策略接口
# ---------------------------------------------------------------------------

class ResilienceStrategy:
    """策略基类：包裹下一层调用，实现容错逻辑。"""

    def wrap(
        self,
        next_fn: Callable[..., T],
        ctx: ResilienceContext,
    ) -> Callable[..., T]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 内建策略
# ---------------------------------------------------------------------------

class RetryStrategy(ResilienceStrategy):
    """重试策略：指数退避 + 可选抖动。

    默认配置：3 次尝试，退避 0.5s -> 1s -> 2s，抖动 0-0.5s。
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        jitter: float = 0.5,
        retry_on: tuple[type[Exception], ...] = (Exception,),
        on_retry: Callable[[PipelineEvent], None] | None = None,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retry_on = retry_on
        self.on_retry = on_retry

    def wrap(
        self,
        next_fn: Callable[..., T],
        ctx: ResilienceContext,
    ) -> Callable[..., T]:
        strategy = self

        @functools.wraps(next_fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(1, strategy.max_attempts + 1):
                ctx.attempt = attempt
                try:
                    result = next_fn(*args, **kwargs)
                    ctx.exception = None
                    return result
                except strategy.retry_on as e:
                    last_exc = e
                    ctx.exception = e
                    if attempt >= strategy.max_attempts:
                        break
                    delay = min(
                        strategy.base_delay * (2 ** (attempt - 1)),
                        strategy.max_delay,
                    )
                    if strategy.jitter > 0:
                        delay += random.uniform(0, strategy.jitter * delay)
                    elapsed = time.time() - ctx.start_time
                    evt = ctx.add_event(
                        stage="retry",
                        attempt=attempt,
                        elapsed=elapsed,
                        ok=False,
                        detail=f"第 {attempt} 次失败，{delay:.2f}s 后重试: {e}",
                    )
                    if strategy.on_retry:
                        strategy.on_retry(evt)
                    time.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper


class TimeoutStrategy(ResilienceStrategy):
    """超时策略：在指定时间内未完成则抛 TimeoutError。"""

    def __init__(
        self,
        timeout: float = 30.0,
        on_timeout: Callable[[PipelineEvent], None] | None = None,
    ):
        self.timeout = timeout
        self.on_timeout = on_timeout

    def wrap(
        self,
        next_fn: Callable[..., T],
        ctx: ResilienceContext,
    ) -> Callable[..., T]:
        strategy = self

        @functools.wraps(next_fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            result_holder: dict[str, Any] = {}
            exc_holder: dict[str, BaseException] = {}

            def _run() -> None:
                try:
                    result_holder["result"] = next_fn(*args, **kwargs)
                except BaseException as e:
                    exc_holder["exception"] = e

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            thread.join(timeout=strategy.timeout)

            if thread.is_alive():
                elapsed = time.time() - ctx.start_time
                evt = ctx.add_event(
                    stage="timeout",
                    attempt=ctx.attempt,
                    elapsed=elapsed,
                    ok=False,
                    detail=f"超时 ({strategy.timeout}s)",
                )
                if strategy.on_timeout:
                    strategy.on_timeout(evt)
                raise TimeoutError(
                    f"执行超时 ({strategy.timeout}s)，已在后台继续"
                )

            if "exception" in exc_holder:
                raise exc_holder["exception"]
            return result_holder.get("result")  # type: ignore[return-value]

        return wrapper


class CircuitBreakerStrategy(ResilienceStrategy):
    """熔断器策略：连续失败达阈值后直接失败（Open），冷却后 Half-Open 探测。

    三态：Closed -> Open（连续失败）-> Half-Open（冷却后）-> Closed（成功）。
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown: float = 30.0,
        half_open_max_calls: int = 1,
        on_state_change: Callable[[str], None] | None = None,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.half_open_max_calls = half_open_max_calls
        self.on_state_change = on_state_change
        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        return self._state

    def _transition(self, new_state: str) -> None:
        self._state = new_state
        if self.on_state_change:
            self.on_state_change(new_state)

    def wrap(
        self,
        next_fn: Callable[..., T],
        ctx: ResilienceContext,
    ) -> Callable[..., T]:
        strategy = self

        @functools.wraps(next_fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with strategy._lock:
                now = time.time()
                if strategy._state == "open":
                    if now - strategy._last_failure_time >= strategy.cooldown:
                        strategy._transition("half_open")
                        strategy._half_open_calls = 0
                    else:
                        raise CircuitBreakerOpenError(
                            f"熔断器 Open 状态，{strategy.cooldown - (now - strategy._last_failure_time):.1f}s 后重试"
                        )

                if strategy._state == "half_open":
                    if strategy._half_open_calls >= strategy.half_open_max_calls:
                        raise CircuitBreakerOpenError(
                            "熔断器 Half-Open 状态，当前探测请求已满"
                        )
                    strategy._half_open_calls += 1

            try:
                result = next_fn(*args, **kwargs)
            except Exception:
                with strategy._lock:
                    strategy._failure_count += 1
                    strategy._last_failure_time = time.time()
                    if strategy._state == "half_open":
                        strategy._transition("open")
                    elif strategy._failure_count >= strategy.failure_threshold:
                        strategy._transition("open")
                raise

            with strategy._lock:
                if strategy._state == "half_open":
                    strategy._transition("closed")
                    strategy._failure_count = 0
                    strategy._half_open_calls = 0
            return result

        return wrapper


class CircuitBreakerOpenError(Exception):
    """熔断器 Open 状态异常。"""


class FallbackStrategy(ResilienceStrategy):
    """降级策略：所有前置策略失败后返回替代值或执行替代动作。"""

    def __init__(
        self,
        fallback_value: Any = None,
        fallback_fn: Callable[..., Any] | None = None,
        on_fallback: Callable[[PipelineEvent], None] | None = None,
    ):
        self.fallback_value = fallback_value
        self.fallback_fn = fallback_fn
        self.on_fallback = on_fallback

    def wrap(
        self,
        next_fn: Callable[..., T],
        ctx: ResilienceContext,
    ) -> Callable[..., T]:
        strategy = self

        @functools.wraps(next_fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return next_fn(*args, **kwargs)
            except Exception:
                elapsed = time.time() - ctx.start_time
                evt = ctx.add_event(
                    stage="fallback",
                    attempt=ctx.attempt,
                    elapsed=elapsed,
                    ok=False,
                    detail=f"触发降级: {ctx.exception}",
                )
                if strategy.on_fallback:
                    strategy.on_fallback(evt)
                if strategy.fallback_fn:
                    return strategy.fallback_fn(*args, **kwargs)
                return strategy.fallback_value

        return wrapper


# ---------------------------------------------------------------------------
# 管道与 Builder
# ---------------------------------------------------------------------------

class ResiliencePipeline:
    """弹性管道：按策略链顺序包裹目标函数。"""

    def __init__(self, strategies: list[ResilienceStrategy] | None = None):
        self._strategies = strategies or []
        self._ctx = ResilienceContext()
        self._events: list[PipelineEvent] = []

    @property
    def events(self) -> list[PipelineEvent]:
        # 返回收集的事件（ctx.events 包含所有策略事件 + execute 事件）
        return list(self._ctx.events)

    def execute(
        self,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """执行管道：策略链从外到内包裹 fn。"""
        self._ctx.reset()
        self._ctx.start_time = time.time()

        wrapped = fn
        for strategy in reversed(self._strategies):
            wrapped = strategy.wrap(wrapped, self._ctx)

        @functools.wraps(fn)
        def outer_wrapper(*a: Any, **kw: Any) -> T:
            self._ctx.add_event(
                stage="execute", attempt=0, elapsed=0.0, ok=True,
                detail=f"管道开始执行（{len(self._strategies)} 个策略）",
            )
            return wrapped(*a, **kw)

        try:
            result = outer_wrapper(*args, **kwargs)
            self._ctx.result = result
            self._ctx.add_event(
                stage="execute", attempt=self._ctx.attempt,
                elapsed=time.time() - self._ctx.start_time, ok=True,
                detail="执行成功",
            )
            return result
        except Exception as e:
            self._ctx.exception = e
            self._ctx.add_event(
                stage="execute", attempt=self._ctx.attempt,
                elapsed=time.time() - self._ctx.start_time, ok=False,
                detail=f"执行失败: {e}",
            )
            raise

    def __call__(self, fn: Callable[..., T]) -> Callable[..., T]:
        """作为装饰器使用。"""
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return self.execute(fn, *args, **kwargs)
        return wrapper


class ResiliencePipelineBuilder:
    """管道 Builder：流式配置策略。"""

    def __init__(self) -> None:
        self._strategies: list[ResilienceStrategy] = []

    def add_retry(
        self,
        max_attempts: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 30.0,
        jitter: float = 0.5,
        retry_on: tuple[type[Exception], ...] = (Exception,),
        on_retry: Callable[[PipelineEvent], None] | None = None,
    ) -> ResiliencePipelineBuilder:
        self._strategies.append(RetryStrategy(
            max_attempts=max_attempts, base_delay=base_delay,
            max_delay=max_delay, jitter=jitter,
            retry_on=retry_on, on_retry=on_retry,
        ))
        return self

    def add_timeout(
        self,
        timeout: float = 30.0,
        on_timeout: Callable[[PipelineEvent], None] | None = None,
    ) -> ResiliencePipelineBuilder:
        self._strategies.append(TimeoutStrategy(
            timeout=timeout, on_timeout=on_timeout,
        ))
        return self

    def add_circuit_breaker(
        self,
        failure_threshold: int = 5,
        cooldown: float = 30.0,
        half_open_max_calls: int = 1,
        on_state_change: Callable[[str], None] | None = None,
    ) -> ResiliencePipelineBuilder:
        self._strategies.append(CircuitBreakerStrategy(
            failure_threshold=failure_threshold, cooldown=cooldown,
            half_open_max_calls=half_open_max_calls,
            on_state_change=on_state_change,
        ))
        return self

    def add_fallback(
        self,
        fallback_value: Any = None,
        fallback_fn: Callable[..., Any] | None = None,
        on_fallback: Callable[[PipelineEvent], None] | None = None,
    ) -> ResiliencePipelineBuilder:
        self._strategies.append(FallbackStrategy(
            fallback_value=fallback_value, fallback_fn=fallback_fn,
            on_fallback=on_fallback,
        ))
        return self

    def build(self) -> ResiliencePipeline:
        return ResiliencePipeline(strategies=list(self._strategies))