"""M00 注册表单测：动态装配、fallback 降级、改配置热替换、体检报告。"""

from pathlib import Path

import pytest

from packages.core.contracts import BrickManifest
from packages.core.errors import BrickNotFoundError
from packages.core.registry import BrickRegistry

BRICKS_YAML = Path(__file__).resolve().parents[1] / "config" / "bricks.yaml"


@pytest.mark.registry
def test_load_all_bricks_from_yaml() -> None:
    reg = BrickRegistry.from_yaml(BRICKS_YAML)
    report = reg.health_report()
    assert report["total"] == 6
    assert len(report["failed"]) == 0
    assert set(report["ok"]) == {"ingest", "router", "orchestrator", "llm_gateway", "gate", "ledger"}


@pytest.mark.registry
def test_primary_impl_loaded() -> None:
    reg = BrickRegistry.from_yaml(BRICKS_YAML)
    ingest = reg.load("ingest")
    assert ingest.variant == "primary"


@pytest.mark.registry
def test_fallback_when_impl_missing() -> None:
    manifest = BrickManifest(
        name="broken",
        role="B01",
        impl="packages.core.no_such_module:NotFound",
        fallback_impl="packages.core.mock_bricks:MockIngestFallback",
    )
    reg = BrickRegistry([manifest])
    brick = reg.load("broken")
    assert brick.variant == "fallback"
    assert "broken" in reg.degraded


@pytest.mark.registry
def test_swap_without_caller_change() -> None:
    reg = BrickRegistry.from_yaml(BRICKS_YAML)
    assert reg.load("ingest").variant == "primary"
    swapped = reg.swap("ingest", "packages.core.mock_bricks:MockIngestSwap")
    assert swapped.variant == "swapped"
    # 再取一次仍是新实现（缓存已更新）
    assert reg.load("ingest").variant == "swapped"


@pytest.mark.registry
def test_unregistered_brick_raises() -> None:
    reg = BrickRegistry.from_yaml(BRICKS_YAML)
    with pytest.raises(BrickNotFoundError):
        reg.load("no_such_brick")


@pytest.mark.registry
def test_health_report_prints() -> None:
    """体检报告可打印，供 CLI 直接输出。"""
    reg = BrickRegistry.from_yaml(BRICKS_YAML)
    report = reg.health_report()
    text = f"积木体检: {len(report['ok'])}/{report['total']} 通过，降级 {len(report['degraded'])}"
    assert "6/6" in text
