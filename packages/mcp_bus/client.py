"""MCP Client Bus：本地 MCP Server 托管、健康检查、超时强杀。

传输层抽象：stdio / 本地 HTTP 用同一个 Transport 协议；
M01 阶段用 mock transport 验证，真实进程托管留到允许拉服务时。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from packages.core.errors import HuiQiaoError


class MCPTimeout(HuiQiaoError):
    code = "HQ302"


class Transport(Protocol):
    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...
    def close(self) -> None: ...


@dataclass
class ServerSpec:
    name: str
    transport: str  # stdio | http
    endpoint: str
    timeout_ms: int = 3000
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class _MockTransport:
    """测试用：返回预置响应，不发真实请求。"""

    def __init__(self, respond: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None) -> None:
        self.respond = respond or (lambda method, params: {"ok": True, "method": method})

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.respond(method, params)

    def close(self) -> None:
        return None


class MCPClientBus:
    def __init__(self) -> None:
        self._servers: dict[str, ServerSpec] = {}
        self._transports: dict[str, Transport] = {}

    def register(self, spec: ServerSpec, transport: Transport | None = None) -> None:
        if not spec.enabled:
            return
        self._servers[spec.name] = spec
        self._transports[spec.name] = transport or _MockTransport()

    def call(self, server: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        spec = self._servers.get(server)
        if spec is None:
            raise HuiQiaoError(f"MCP Server 未注册: {server}")
        transport = self._transports[server]
        started = time.monotonic()
        # 超时用单调时钟检查（mock 下不会真阻塞，但逻辑要在）
        result = transport.call(method, params or {})
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if elapsed_ms > spec.timeout_ms:
            raise MCPTimeout(f"{server}.{method} 超时 {elapsed_ms}ms")
        return result

    def health_check(self) -> dict[str, bool]:
        out: dict[str, bool] = {}
        for name, spec in self._servers.items():
            try:
                res = self.call(name, "ping", {})
                out[name] = bool(res.get("ok", True))
            except HuiQiaoError:
                out[name] = False
        return out

    def close_all(self) -> None:
        for t in self._transports.values():
            t.close()
        self._transports.clear()
