"""M02 Runner：用注入的本地模型 transport 跑微型基准，产出能力档案。

不自己发 HTTP；transport 由调用方注入（允许实测时才接真实 Ollama）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from packages.core.contracts import CapabilityProfile

from .hardware import collect_hardware
from .suite import MiniSuite


class ProfileRunner:
    def __init__(self, suite: MiniSuite | None = None) -> None:
        self.suite = suite or MiniSuite()

    def run(
        self,
        infer: Callable[[str], str],
        *,
        model_name: str = "local",
        ctx_limit_tokens: int = 8192,
    ) -> CapabilityProfile:
        """infer(prompt)->answer；由调用方接本地模型。"""
        results: dict[str, list[bool]] = {}
        for case in self.suite.cases:
            answer = infer(case.prompt)
            results.setdefault(case.category, []).append(case.judge(answer))

        rates = {cat: sum(v) / len(v) for cat, v in results.items()}

        # 安全有效上下文：按 RULER 类通过率反推（起步规则，需真实数据校准）
        safe_ctx = min(ctx_limit_tokens, max(1024, int(ctx_limit_tokens * 0.5)))

        models = {
            model_name: {
                "tool_call_rate": rates.get("bfcl", 0.0),
                "codefix_rate": rates.get("codefix", 0.0),
                "ruler_rate": rates.get("ruler", 0.0),
            }
        }

        enabled: list[Any] = []
        if rates.get("bfcl", 0) >= 0.8:
            enabled.append("L1_FLOW")
        if rates.get("codefix", 0) >= 0.7:
            enabled.append("L2C_CODEACT")
        enabled.append("L2S_SEMANTIC_COCREATE")

        return CapabilityProfile(
            profiled_at=datetime.now(),
            host_hardware=collect_hardware(),
            models=models,
            enabled_channels=enabled,
            safe_effective_ctx={model_name: safe_ctx},
            metadata={"sample_count": len(self.suite.cases), "note": "M02 骨架；真实摸底需接本地模型"},
        )

    @staticmethod
    def human_report(profile: CapabilityProfile) -> str:
        lines = ["# 汇桥 OS 装机能力体检单", ""]
        lines.append(f"- 时间：{profile.profiled_at.isoformat()}")
        lines.append(f"- 系统：{profile.host_hardware.get('os')} {profile.host_hardware.get('arch')}")
        lines.append(f"- 开放通道：{', '.join(c.value for c in profile.enabled_channels)}")
        for model, data in profile.models.items():
            lines.append(f"- 模型 {model}：工具调用 {data['tool_call_rate']:.0%}，代码修复 {data['codefix_rate']:.0%}")
        for model, ctx in profile.safe_effective_ctx.items():
            lines.append(f"- 安全有效上下文 {model}：{ctx} tokens")
        return "\n".join(lines)
