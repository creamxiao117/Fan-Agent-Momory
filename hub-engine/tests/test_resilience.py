"""resilience.py 弹性管道单元测试。

覆盖：Retry 重试 / Timeout 超时 / CircuitBreaker 熔断 / Fallback 降级 / 管道组合。
"""

import sys
import time
from pathlib import Path

# 将 hub-engine 加入 sys.path
_ENGINE_DIR = Path(__file__).resolve().parent.parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

import pytest

from tools.resilience import (
    ResilienceContext,
    ResiliencePipelineBuilder,
    PipelineEvent,
    RetryStrategy,
    TimeoutStrategy,
    CircuitBreakerStrategy,
    CircuitBreakerOpenError,
    FallbackStrategy,
)


class TestRetryStrategy:
    """重试策略测试。"""

    def test_retry_success_first_attempt(self):
        """首次尝试成功直接返回。"""
        pipeline = (
            ResiliencePipelineBuilder()
            .add_retry(max_attempts=3, base_delay=0.01, jitter=0)
            .build()
        )
        result = pipeline.execute(lambda: "ok")
        assert result == "ok"
        # 只有 execute 事件，无 retry 事件
        assert all(e.stage != "retry" for e in pipeline.events)

    def test_retry_then_success(self):
        """前几次失败，最终成功。"""
        call_count = 0

        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"失败第 {call_count} 次")
            return "ok"

        pipeline = (
            ResiliencePipelineBuilder()
            .add_retry(max_attempts=5, base_delay=0.01, jitter=0)
            .build()
        )
        result = pipeline.execute(flaky)
        assert result == "ok"
        assert call_count == 3  # 第 3 次成功
        # 应有 retry 事件
        retry_events = [e for e in pipeline.events if e.stage == "retry"]
        assert len(retry_events) == 2  # 前 2 次失败

    def test_retry_all_attempts_fail(self):
        """所有重试耗尽，抛出最后异常。"""
        pipeline = (
            ResiliencePipelineBuilder()
            .add_retry(max_attempts=3, base_delay=0.01, jitter=0)
            .build()
        )
        with pytest.raises(ValueError, match="持续失败"):
            pipeline.execute(lambda: (_ for _ in ()).throw(ValueError("持续失败")))
        # 3 次尝试全失败：attempt 1 失败->retry, attempt 2 失败->retry, attempt 3 失败->抛异常
        retry_events = [e for e in pipeline.events if e.stage == "retry"]
        assert len(retry_events) == 2  # 前 2 次触发重试事件，第 3 次仍失败则抛出


class TestTimeoutStrategy:
    """超时策略测试。"""

    def test_timeout_normal_completion(self):
        """正常完成不触发超时。"""
        pipeline = (
            ResiliencePipelineBuilder()
            .add_timeout(timeout=5.0)
            .build()
        )
        result = pipeline.execute(lambda: "ok")
        assert result == "ok"

    def test_timeout_triggers(self):
        """超时正确触发 TimeoutError。"""
        pipeline = (
            ResiliencePipelineBuilder()
            .add_timeout(timeout=0.1)  # 0.1s 超时
            .build()
        )

        def slow() -> str:
            time.sleep(5)
            return "ok"

        with pytest.raises(TimeoutError):
            pipeline.execute(slow)


class TestCircuitBreakerStrategy:
    """熔断器策略测试。"""

    def test_circuit_starts_closed(self):
        """初始状态为 closed。"""
        cb = CircuitBreakerStrategy(failure_threshold=3, cooldown=0.5)
        assert cb.state == "closed"

    def test_circuit_opens_after_failures(self):
        """连续失败达阈值后熔断。"""
        cb = CircuitBreakerStrategy(
            failure_threshold=2, cooldown=10.0, half_open_max_calls=1
        )
        pipeline = ResiliencePipelineBuilder()._strategies
        # 手动构建管道
        from tools.resilience import ResiliencePipeline

        def always_fail():
            raise ConnectionError("连接失败")

        # 执行 2 次，应在第 2 次进入 open
        for i in range(2):
            try:
                cb.wrap(always_fail, ResilienceContext())()
            except ConnectionError:
                pass
            except CircuitBreakerOpenError:
                pass

        # 第 3 次应触发 open
        with pytest.raises(CircuitBreakerOpenError):
            cb.wrap(always_fail, ResilienceContext())()

    def test_circuit_half_open_recovers(self):
        """冷却时间后进入 half-open，成功后恢复 closed。"""
        cb = CircuitBreakerStrategy(
            failure_threshold=2, cooldown=0.05, half_open_max_calls=1
        )

        def always_fail():
            raise ConnectionError("连接失败")

        # 触发 open
        for i in range(2):
            try:
                cb.wrap(always_fail, ResilienceContext())()
            except (ConnectionError, CircuitBreakerOpenError):
                pass

        assert cb.state == "open"

        # 等待冷却
        time.sleep(0.1)

        # 成功调用应恢复
        ok_fn = lambda: "ok"
        result = cb.wrap(ok_fn, ResilienceContext())()
        assert result == "ok"
        assert cb.state == "closed"

    def test_circuit_half_open_fails_back_to_open(self):
        """Half-Open 失败回到 Open。"""
        cb = CircuitBreakerStrategy(
            failure_threshold=2, cooldown=0.05, half_open_max_calls=1
        )

        def always_fail():
            raise ConnectionError("连接失败")

        # 触发 open
        for i in range(2):
            try:
                cb.wrap(always_fail, ResilienceContext())()
            except (ConnectionError, CircuitBreakerOpenError):
                pass

        # 等待冷却
        time.sleep(0.1)

        # Half-Open 调用失败应回到 Open
        with pytest.raises(ConnectionError):
            cb.wrap(always_fail, ResilienceContext())()

        assert cb.state == "open"


class TestFallbackStrategy:
    """降级策略测试。"""

    def test_fallback_value(self):
        """所有前置失败后返回 fallback_value。"""
        pipeline = (
            ResiliencePipelineBuilder()
            .add_fallback(fallback_value="降级结果")
            .build()
        )
        # Fallback 策略捕获异常并返回 fallback_value，不抛异常
        result = pipeline.execute(lambda: (_ for _ in ()).throw(RuntimeError("失败")))
        assert result == "降级结果"
        # 应记录 fallback 事件
        fallback_events = [e for e in pipeline.events if e.stage == "fallback"]
        assert len(fallback_events) == 1

    def test_fallback_fn(self):
        """使用 fallback_fn 替代。"""
        pipeline = (
            ResiliencePipelineBuilder()
            .add_fallback(fallback_fn=lambda: "替代结果")
            .build()
        )
        result = pipeline.execute(lambda: (_ for _ in ()).throw(RuntimeError("失败")))
        assert result == "替代结果"

    def test_fallback_on_success(self):
        """正常成功时不触发降级。"""
        pipeline = (
            ResiliencePipelineBuilder()
            .add_fallback(fallback_value="降级")
            .build()
        )
        result = pipeline.execute(lambda: "正常结果")
        assert result == "正常结果"


class TestPipelineComposition:
    """管道组合测试。"""

    def test_retry_then_timeout(self):
        """Retry + Timeout 组合。"""
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("失败")
            return "ok"

        pipeline = (
            ResiliencePipelineBuilder()
            .add_retry(max_attempts=5, base_delay=0.01, jitter=0)
            .add_timeout(timeout=10.0)
            .build()
        )
        result = pipeline.execute(flaky)
        assert result == "ok"
        assert call_count == 3

    def test_full_pipeline(self):
        """完整管道：Fallback(外) + Timeout + Retry(内)。"""
        # 正确顺序：Fallback 在外层（最后降级），Retry 在内层（重试实际调用）
        pipeline = (
            ResiliencePipelineBuilder()
            .add_fallback(fallback_value="降级值")
            .add_timeout(timeout=10.0)
            .add_retry(max_attempts=3, base_delay=0.01, jitter=0)
            .build()
        )
        # 全失败时走降级
        result = pipeline.execute(lambda: (_ for _ in ()).throw(RuntimeError("全挂")))
        assert result == "降级值"
        assert any(e.stage == "fallback" for e in pipeline.events)

    def test_pipeline_as_decorator(self):
        """管道可作为装饰器使用。"""
        pipeline = (
            ResiliencePipelineBuilder()
            .add_retry(max_attempts=3, base_delay=0.01, jitter=0)
            .build()
        )

        @pipeline
        def my_func():
            return "decorated"

        result = my_func()
        assert result == "decorated"

    def test_events_are_recorded(self):
        """事件正确记录。"""
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("失败")
            return "ok"

        pipeline = (
            ResiliencePipelineBuilder()
            .add_retry(max_attempts=3, base_delay=0.01, jitter=0)
            .build()
        )
        pipeline.execute(flaky)
        events = pipeline.events
        assert len(events) > 0
        assert events[0].stage == "execute"
        retry_events = [e for e in events if e.stage == "retry"]
        assert len(retry_events) >= 1


class TestBuilder:
    """Builder 流式配置测试。"""

    def test_builder_fluent(self):
        """Builder 支持流式链式调用。"""
        builder = ResiliencePipelineBuilder()
        result = (
            builder.add_retry(max_attempts=3)
            .add_timeout(timeout=30)
            .add_fallback(fallback_value="ok")
            .build()
        )
        assert result is not None
        # 执行一次确保可用
        exec_result = result.execute(lambda: "test")
        assert exec_result == "test"

    def test_empty_pipeline(self):
        """空管道直接透传。"""
        pipeline = ResiliencePipelineBuilder().build()
        result = pipeline.execute(lambda: "empty")
        assert result == "empty"