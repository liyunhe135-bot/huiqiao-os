"""M00 测试用 Mock 积木：验证契约装配与热替换，不依赖任何模型/后台服务。"""

from __future__ import annotations

from typing import Any


class _MockBase:
    def __init__(self, **config: Any) -> None:
        self.config = config

    def run(self, step: Any) -> Any:  # pragma: no cover - 接口占位
        return None


class MockIngest(_MockBase):
    variant = "primary"


class MockIngestFallback(_MockBase):
    variant = "fallback"


class MockIngestSwap(_MockBase):
    variant = "swapped"


class MockRouter(_MockBase):
    variant = "primary"


class MockRouterFallback(_MockBase):
    variant = "fallback"


class MockOrchestrator(_MockBase):
    variant = "primary"


class MockLLMGateway(_MockBase):
    variant = "primary"


class MockGate(_MockBase):
    variant = "primary"


class MockLedger(_MockBase):
    variant = "primary"
