"""B04 本地模型网关：Ollama / llama-server 适配、显存亲和、思考剥离、前缀缓存。"""

from .adapters import OllamaAdapter, LlamaServerAdapter
from .affinity import ModelAffinityQueue
from .thinking import ThinkingBudget, strip_think_blocks, budget_for_role
from .cost_router import CostAwareRouter, RouteTarget, estimate_credits

__all__ = [
    "OllamaAdapter",
    "LlamaServerAdapter",
    "ModelAffinityQueue",
    "ThinkingBudget",
    "strip_think_blocks",
    "budget_for_role",
    "CostAwareRouter",
    "RouteTarget",
    "estimate_credits",
]
