"""M02 单测：硬件只读采集、基准集结构、Runner 产出能力档案。全 mock。"""

import pytest

from packages.core.contracts import CapabilityProfile
from packages.profiler.hardware import collect_hardware
from packages.profiler.runner import ProfileRunner
from packages.profiler.suite import MiniSuite


@pytest.mark.profiler
def test_hardware_readonly() -> None:
    hw = collect_hardware()
    assert hw["os"] in {"Windows", "Linux", "Darwin"}
    assert hw["gpu"]["status"] == "未采集"


@pytest.mark.profiler
def test_mini_suite_categories() -> None:
    suite = MiniSuite()
    assert len(suite.by_category("bfcl")) == 2
    assert len(suite.by_category("ruler")) == 2
    assert len(suite.by_category("codefix")) == 2


@pytest.mark.profiler
def test_runner_with_perfect_model() -> None:
    def infer(prompt: str) -> str:
        # 模拟一个全对的本地模型：答案里包含所有期望标记
        return "get_weather 拒调 X7 def return"

    runner = ProfileRunner()
    profile = runner.run(infer, model_name="qwen3:8b", ctx_limit_tokens=16384)
    assert isinstance(profile, CapabilityProfile)
    assert profile.models["qwen3:8b"]["tool_call_rate"] == 1.0
    assert "L2C_CODEACT" in [c.value for c in profile.enabled_channels]
    assert profile.safe_effective_ctx["qwen3:8b"] == 8192  # 16384*0.5


@pytest.mark.profiler
def test_runner_with_weak_model() -> None:
    def infer(prompt: str) -> str:
        return ""  # 全错

    profile = ProfileRunner().run(infer, ctx_limit_tokens=4096)
    assert profile.models["local"]["tool_call_rate"] == 0.0
    assert "L2C_CODEACT" not in [c.value for c in profile.enabled_channels]
    # 知限谦卑：弱模型仍开放语义共生（人类主导）
    assert "L2S_SEMANTIC_COCREATE" in [c.value for c in profile.enabled_channels]


@pytest.mark.profiler
def test_human_report() -> None:
    profile = ProfileRunner().run(lambda p: "get_weather X7 def return", ctx_limit_tokens=8192)
    text = ProfileRunner.human_report(profile)
    assert "装机能力体检单" in text
    assert "安全有效上下文" in text
