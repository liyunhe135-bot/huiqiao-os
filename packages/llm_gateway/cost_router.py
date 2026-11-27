"""省积分路由：本地优先、限免优先、能力边界兜底。

原则（用户 2026-11-27 明确要求：尽量不消耗积分）：
1. 能力阶梯 A0/A/B 的任务 → 一律本地模型，积分消耗 0。
2. 本地能力不足（C/D/E 或超上下文）→ 才上云；云端按倍率从低到高选。
3. 限免模型（0.00x）优先，但限免期内只能用于聊天类，作图/视频/长文档另算。
4. 路由决策必须写明 reason，进 EventRecord 台账可审计。

注意：倍率→积分不是官方线性公式（官方只说"模型定价×任务复杂度"）。
本模块的 estimate_credits 是【推测】性质的估算，用于排序，不用于账单。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

# 2026-11-27 截图的客户端倍率（会变，配置化后再读文件）
CLOUD_MODELS: dict[str, dict[str, Any]] = {
    "hy4_flash": {
        "rate": 0.00,
        "name": "Hy4 flash",
        "note": "11/16-11/30 限免，每日赠额度；聊天不扣积分，作图/视频/长文档另算",
        "free_until": "2026-11-30",
    },
    "glm53_flash": {"rate": 0.08, "name": "GLM-5.3-Flash", "note": "订阅优先"},
    "deepseek_v41_flash": {"rate": 0.11, "name": "DeepSeek-V4.1-Flash", "note": "夜间折扣"},
    "glm54": {"rate": 0.69, "name": "GLM-5.4", "note": "订阅优先"},
    "glm53": {"rate": 0.69, "name": "GLM-5.3", "note": "订阅优先"},
}

# 第三方实测基准：1 积分 ≈ 22.6 万 token（0.69x 混合模型，95.66% 缓存命中）
TOKENS_PER_CREDIT_AT_069X = 226_333
LINEAR_BASE_1X = TOKENS_PER_CREDIT_AT_069X * 0.69  # 推测：倍率线性外推


class RouteTarget(str, Enum):
    LOCAL = "LOCAL"
    CLOUD_FREE = "CLOUD_FREE"
    CLOUD_LOW = "CLOUD_LOW"
    HUMAN = "HUMAN"


@dataclass(frozen=True)
class CostDecision:
    target: RouteTarget
    model: str
    reason: str
    estimated_credits: float
    layer: str


def estimate_credits(tokens: int, model_key: str) -> float:
    """【推测】按倍率线性外推估算积分，仅用于排序，不做账单依据。"""
    info = CLOUD_MODELS.get(model_key)
    if info is None:
        return 0.0
    rate = float(info["rate"])
    if rate <= 0:
        return 0.0
    tokens_per_credit = LINEAR_BASE_1X / rate
    return tokens / tokens_per_credit


class CostAwareRouter:
    """按能力层与本机档案决定本地/云端/人工。"""

    def __init__(self, host_tier: str = "8B", enabled_channels: set[str] | None = None) -> None:
        self.host_tier = host_tier
        self.enabled_channels = enabled_channels or {"L0_SKILL", "L1_FLOW", "L2S_SEMANTIC"}

    def decide(self, layer: str, estimated_tokens: int = 2000, *, need_vision: bool = False) -> CostDecision:
        # A0/A/B：本地稳，零积分
        if layer in {"A0", "A", "B"}:
            return CostDecision(
                target=RouteTarget.LOCAL,
                model=f"local:{self.host_tier}",
                reason=f"能力层 {layer} 在本地模型稳健区；走本地零积分",
                estimated_credits=0.0,
                layer=layer,
            )

        # 视觉需求：本地无视觉能力则上云（限免优先）
        if need_vision and self.host_tier.startswith("8B"):
            return CostDecision(
                target=RouteTarget.CLOUD_FREE,
                model="hy4_flash",
                reason="本地 8B 无可靠视觉能力；用 0.00x 限免模型（注意作图另计费）",
                estimated_credits=0.0,
                layer=layer,
            )

        # C/D/E：先看本地是否有高配，否则上云最低倍率
        high_local = self.host_tier.startswith(("24B", "27B", "32B"))
        if layer == "C" and high_local:
            return CostDecision(
                target=RouteTarget.LOCAL,
                model=f"local:{self.host_tier}",
                reason="C 层在本地高配档可达，但需闸门；零积分",
                estimated_credits=0.0,
                layer=layer,
            )

        if layer in {"C", "D", "E"}:
            candidates = ["hy4_flash", "glm53_flash", "deepseek_v41_flash", "glm54"]
            best = min(candidates, key=lambda k: estimate_credits(estimated_tokens, k))
            return CostDecision(
                target=RouteTarget.CLOUD_FREE if CLOUD_MODELS[best]["rate"] == 0 else RouteTarget.CLOUD_LOW,
                model=best,
                reason=f"能力层 {layer} 超本地稳健区；选最低倍率云端 {CLOUD_MODELS[best]['name']}",
                estimated_credits=estimate_credits(estimated_tokens, best),
                layer=layer,
            )

        # 未知层：转人工止损，不乱猜
        return CostDecision(
            target=RouteTarget.HUMAN,
            model="none",
            reason=f"未识别能力层 {layer}；按止损原则交人工判断",
            estimated_credits=0.0,
            layer=layer,
        )
