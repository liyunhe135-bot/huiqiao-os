"""VRAM 亲和队列：同一驻留模型的任务聚批先跑，减少换模抖动。

单机铁律：一个时刻只驻留一个模型。队列按 model 分组，同组连续执行。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class AffinityJob:
    model: str
    payload: dict[str, Any]
    tag: str = "default"


@dataclass
class AffinityResult:
    order: list[str] = field(default_factory=list)
    model_switches: int = 0


class ModelAffinityQueue:
    """纯调度器：不执行任务，只决定执行顺序。"""

    def __init__(self, vram_budget_gb: float = 16.0) -> None:
        self.vram_budget_gb = vram_budget_gb
        self._jobs: list[AffinityJob] = []

    def submit(self, job: AffinityJob) -> None:
        self._jobs.append(job)

    def plan(self) -> AffinityResult:
        """按模型分组，同组聚批；组间按首次出现顺序。"""
        groups: dict[str, list[AffinityJob]] = defaultdict(list)
        for job in self._jobs:
            groups[job.model].append(job)
        result = AffinityResult()
        last: str | None = None
        for model, jobs in groups.items():
            for _ in jobs:
                result.order.append(model)
            if last != model:
                result.model_switches += 1
                last = model
        return result

    def drain(self, handler: Callable[[AffinityJob], Any]) -> list[Any]:
        """按亲和顺序执行，返回各任务结果。"""
        groups: dict[str, list[AffinityJob]] = defaultdict(list)
        for job in self._jobs:
            groups[job.model].append(job)
        out: list[Any] = []
        for jobs in groups.values():
            for job in jobs:
                out.append(handler(job))
        self._jobs.clear()
        return out
