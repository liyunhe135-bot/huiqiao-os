"""M01 单测：适配器离线铁律、亲和队列、思考剥离、省积分路由。全 mock，不联网。"""

import pytest

from packages.llm_gateway.adapters import OllamaAdapter, OutboundBlocked
from packages.llm_gateway.affinity import AffinityJob, ModelAffinityQueue
from packages.llm_gateway.cost_router import CostAwareRouter, RouteTarget, estimate_credits
from packages.llm_gateway.thinking import ThinkingBudget, budget_for_role, strip_think_blocks


def fake_transport(url: str, payload: dict) -> dict:
    """模拟 OpenAI 兼容响应，不发真实请求。"""
    assert url.endswith("/v1/chat/completions")
    return {
        "model": payload["model"],
        "choices": [{"message": {"content": "OK"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 80}},
    }


@pytest.mark.gateway
def test_adapter_rejects_remote_url() -> None:
    with pytest.raises(OutboundBlocked):
        OllamaAdapter(base_url="https://api.example.com/v1", model="m")


@pytest.mark.gateway
def test_adapter_loopback_ok() -> None:
    a = OllamaAdapter(model="qwen3:8b", transport=fake_transport)
    resp = a.chat([{"role": "user", "content": "hi"}])
    assert resp.text == "OK"
    assert resp.cached_tokens == 80
    assert resp.input_tokens == 100


@pytest.mark.gateway
def test_affinity_groups_same_model() -> None:
    q = ModelAffinityQueue()
    for m in ["a", "b", "a", "a", "b"]:
        q.submit(AffinityJob(model=m, payload={}))
    plan = q.plan()
    assert plan.order == ["a", "a", "a", "b", "b"]
    assert plan.model_switches == 2


@pytest.mark.gateway
def test_affinity_drain_handler() -> None:
    q = ModelAffinityQueue()
    q.submit(AffinityJob(model="a", payload={"x": 1}))
    q.submit(AffinityJob(model="a", payload={"x": 2}))
    out = q.drain(lambda job: job.payload["x"])
    assert out == [1, 2]


@pytest.mark.gateway
def test_thinking_budget_by_role() -> None:
    assert budget_for_role("fast_router") == ThinkingBudget.OFF
    assert budget_for_role("reasoner") == ThinkingBudget.HIGH
    assert budget_for_role("unknown") == ThinkingBudget.LOW


@pytest.mark.gateway
def test_strip_think_blocks() -> None:
    text = "<think>内部推理很长</think>最终答案"
    assert strip_think_blocks(text) == "最终答案"


@pytest.mark.gateway
def test_strip_think_unclosed() -> None:
    text = "<think>半截推理"
    assert strip_think_blocks(text) == ""


@pytest.mark.gateway
def test_cost_router_local_for_ab() -> None:
    r = CostAwareRouter(host_tier="8B")
    d = r.decide("A", estimated_tokens=3000)
    assert d.target == RouteTarget.LOCAL
    assert d.estimated_credits == 0.0
    assert "零积分" in d.reason


@pytest.mark.gateway
def test_cost_router_uses_free_model_for_high_layer() -> None:
    r = CostAwareRouter(host_tier="8B")
    d = r.decide("E", estimated_tokens=5000)
    assert d.target == RouteTarget.CLOUD_FREE
    assert d.model == "hy4_flash"
    assert d.estimated_credits == 0.0


@pytest.mark.gateway
def test_cost_router_sorted_by_rate() -> None:
    r = CostAwareRouter(host_tier="8B")
    d_c = r.decide("C", estimated_tokens=50000)
    d_d = r.decide("D", estimated_tokens=50000)
    # 两者都选最低倍率；限免优先逻辑不变
    assert d_c.model == d_d.model == "hy4_flash"


@pytest.mark.gateway
def test_cost_router_unknown_layer_to_human() -> None:
    r = CostAwareRouter(host_tier="8B")
    d = r.decide("Z")
    assert d.target == RouteTarget.HUMAN


@pytest.mark.gateway
def test_estimate_credits_relative_order() -> None:
    """估算只用于排序：低倍率必须更省。"""
    assert estimate_credits(1_000_000, "glm53_flash") < estimate_credits(1_000_000, "glm54")
    assert estimate_credits(1_000_000, "hy4_flash") == 0.0
