"""M03 单测：权限分级、Tool Search 延迟加载、MCP Bus 健康检查。全 mock。"""

import pytest

from packages.mcp_bus.client import MCPClientBus, ServerSpec
from packages.mcp_bus.permissions import Permission, PermissionDenied, PermissionGuard, ToolSpec
from packages.mcp_bus.tool_search import ToolSearch


def make_tools(n: int = 30) -> list[ToolSpec]:
    return [
        ToolSpec(
            name=f"tool_{i:02d}",
            description=f"第 {i} 个工具，处理某类本地数据",
            permission=Permission.READ if i % 2 == 0 else Permission.WRITE,
            input_schema={"path": "string", "limit": "int"},
            tags=(f"cat{i % 5}",),
        )
        for i in range(n)
    ]


@pytest.mark.mcp
def test_initial_bundle_under_500_tokens() -> None:
    """M03 DoD：挂载 30 个工具，初始工具区 < 500 tokens。"""
    ts = ToolSearch(make_tools(30))
    bundle = ts.initial_bundle()
    assert bundle.estimated_tokens < 500
    assert len(bundle.tools) == 1
    assert bundle.tools[0]["name"] == "tool_search"


@pytest.mark.mcp
def test_search_and_expand() -> None:
    ts = ToolSearch(make_tools(30))
    hits = ts.search("cat3")
    assert len(hits) == 3
    bundle = ts.handle("cat3")
    assert len(bundle.tools) == 3
    assert bundle.estimated_tokens > 0


@pytest.mark.mcp
def test_ask_mode_blocks_write() -> None:
    guard = PermissionGuard(mode="Ask")
    write_tool = ToolSpec(name="delete_file", description="删文件", permission=Permission.WRITE)
    with pytest.raises(PermissionDenied):
        guard.check(write_tool)


@pytest.mark.mcp
def test_execute_mode_allows_with_whitelist() -> None:
    guard = PermissionGuard(mode="Execute", allowed_paths=("D:/work",))
    tool = ToolSpec(name="read_file", description="读文件", permission=Permission.READ)
    guard.check(tool, {"path": "D:/work/a.txt"})
    with pytest.raises(PermissionDenied):
        guard.check(tool, {"path": "C:/Windows/system.ini"})


@pytest.mark.mcp
def test_plan_mode_blocks_execute() -> None:
    guard = PermissionGuard(mode="Plan")
    tool = ToolSpec(name="run_shell", description="执行命令", permission=Permission.EXECUTE)
    with pytest.raises(PermissionDenied):
        guard.check(tool)


@pytest.mark.mcp
def test_bus_health_check() -> None:
    bus = MCPClientBus()
    bus.register(ServerSpec(name="fs", transport="stdio", endpoint="local"))
    bus.register(ServerSpec(name="broken", transport="stdio", endpoint="local", enabled=False))
    health = bus.health_check()
    assert health == {"fs": True}


@pytest.mark.mcp
def test_bus_call() -> None:
    bus = MCPClientBus()
    bus.register(ServerSpec(name="fs", transport="stdio", endpoint="local"))
    res = bus.call("fs", "list", {})
    assert res["ok"] is True


@pytest.mark.mcp
def test_bus_unknown_server() -> None:
    bus = MCPClientBus()
    with pytest.raises(Exception):
        bus.call("nope", "ping", {})
