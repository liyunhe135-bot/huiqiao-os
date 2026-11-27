"""M09 B05 逻辑隔离 / 物理显存亲和 Subagent 调度池（AffinitySubagentPool）.

针对本地单卡有限显存（如 RTX 4070 12GB 一次仅驻留 1 个主力模型）的工业级多代理架构：
  1. 逻辑隔离（Logical Context Isolation）：
     - 每个子代理启动全新的隔离 ContextManager，不接收父代理冗余工具过程日志，
       只接收显式下发的最小任务简报（brief）与 C00 宪章前缀；
     - 子代理结束后只向父代理回传提纯摘要（summary）与产物清单（artifacts），彻底杜绝上下文污染；
  2. 物理显存亲和（Physical VRAM Affinity Scheduling）：
     - 深度联动 M01 ModelAffinityQueue，将混排的多模型子代理按 model 聚批串行调度；
     - 若已知当前显存驻留模型（resident_model），优先调度同模型批次，把高昂的冷换模次数压至理论最低；
  3. 权限向下兼容绝不越权（Non-Escalation）：
     - 子代理的工作模式严禁突破父任务（例如父任务为 Ask 时，子代理被物理降钳在 Ask，绝不能偷偷切 Execute）。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from pydantic import Field

from packages.core.constitution import LoadedConstitution, load_constitution
from packages.core.contracts import (
    BaseContract,
    InteractionMode,
    SandboxTier,
    StepInput,
    StepOutput,
    WorkMode,
    new_id,
)
from packages.core.interfaces import WorkerProtocol
from packages.llm_gateway.affinity import AffinityJob, ModelAffinityQueue
from packages.workers.context_engine import CompactionPolicy, ContextManager

_MODE_RANK: dict[WorkMode, int] = {
    WorkMode.ASK: 0,
    WorkMode.PLAN: 1,
    WorkMode.EXECUTE: 2,
}


def clamp_work_mode(parent_mode: WorkMode, child_mode: WorkMode) -> WorkMode:
    """子代理安全边界锁：严禁权限升级（如父 Ask -> 子 Execute 会被强制钳位回 Ask）。"""
    return child_mode if _MODE_RANK[child_mode] <= _MODE_RANK[parent_mode] else parent_mode


def count_model_switches(models: list[str], *, initial_resident: str | None = None) -> int:
    """统计给定执行序列会触发多少次显存模型切换（若首个模型与驻留模型相同则免冷加载）。"""
    switches = 0
    current = initial_resident
    for model in models:
        if model != current:
            switches += 1
            current = model
    return switches


class SubagentSpec(BaseContract):
    """单个逻辑隔离子代理的任务规范。"""

    subagent_id: str = Field(default_factory=lambda: new_id("sub"))
    role: str = Field(..., min_length=1, description="角色定位，如 code_auditor / doc_extractor")
    model: str = Field(..., min_length=1, description="目标本地模型标识，如 qwen3-4b / qwen3-14b")
    goal: str = Field(..., min_length=1)
    brief: str = Field(default="", description="父代理显式下发的精简背景（绝不透传冗余噪声）")
    work_mode: WorkMode = Field(default=WorkMode.ASK)
    interaction_mode: InteractionMode = Field(default=InteractionMode.COPILOT_EXECUTE)
    sandbox_tier: SandboxTier = Field(default=SandboxTier.T2_OS_RESTRICTED)
    effective_ctx_budget: int = Field(default=8192, ge=1024)
    steering_hint: str | None = Field(default=None)


class SubagentResult(BaseContract):
    """子代理返回给父代理的提纯交付件（零内部冗余噪声）。"""

    subagent_id: str
    role: str
    model: str
    success: bool
    summary: str = ""
    artifacts: list[str] = Field(default_factory=list)
    model_notes: str = ""
    error: str | None = None
    elapsed_ms: int = 0
    isolated_context_tokens: int = 0
    effective_work_mode: WorkMode = WorkMode.ASK


class AffinityBatchReport(BaseContract):
    """多子代理亲和批调度汇总报告与显存换模节能指标。"""

    run_id: str
    parent_work_mode: WorkMode
    resident_model_before: str | None = None
    resident_model_after: str | None = None
    submitted_order: list[str] = Field(default_factory=list)
    executed_order: list[str] = Field(default_factory=list)
    executed_models: list[str] = Field(default_factory=list)
    naive_model_switches: int = 0
    optimized_model_switches: int = 0
    switches_saved: int = 0
    results: dict[str, SubagentResult] = Field(default_factory=dict)
    merged_summary: str = ""
    all_succeeded: bool = True


WorkerFactoryFn = Callable[[SubagentSpec, ContextManager], WorkerProtocol]


class AffinitySubagentPool:
    """逻辑隔离 + 物理显存亲和 Subagent 调度池。"""

    def __init__(
        self,
        *,
        worker_factory: WorkerFactoryFn,
        resident_model: str | None = None,
        vram_budget_gb: float = 12.0,
        constitution: LoadedConstitution | None = None,
    ) -> None:
        self._worker_factory = worker_factory
        self.resident_model = resident_model
        self.vram_budget_gb = vram_budget_gb
        self.constitution = constitution or load_constitution()

    def plan_affinity_order(self, specs: list[SubagentSpec]) -> list[SubagentSpec]:
        """利用 M01 ModelAffinityQueue 按模型聚批，并把当前已驻留显存的模型组排在最前。"""
        if not specs:
            return []

        # 若当前显存已驻留某模型，先提交该模型的任务使其稳居首组（0 次额外冷切）
        prioritized = list(specs)
        if self.resident_model:
            resident_first = [s for s in specs if s.model == self.resident_model]
            others = [s for s in specs if s.model != self.resident_model]
            prioritized = resident_first + others

        queue = ModelAffinityQueue(vram_budget_gb=self.vram_budget_gb)
        for spec in prioritized:
            queue.submit(AffinityJob(model=spec.model, payload={"spec": spec}, tag=spec.subagent_id))

        ordered: list[SubagentSpec] = []
        queue.drain(lambda job: ordered.append(job.payload["spec"]))
        return ordered

    def run_batch(
        self,
        specs: list[SubagentSpec],
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        parent_work_mode: WorkMode = WorkMode.EXECUTE,
    ) -> AffinityBatchReport:
        """以逻辑上下文完全隔离 + 物理显存亲和顺序批量执行子代理。"""
        rid = run_id or new_id("run")
        tid = task_id or new_id("tsk")
        resident_before = self.resident_model

        submitted_ids = [s.subagent_id for s in specs]
        naive_models = [s.model for s in specs]
        naive_switches = count_model_switches(naive_models, initial_resident=resident_before)

        ordered_specs = self.plan_affinity_order(specs)
        executed_ids: list[str] = []
        executed_models: list[str] = []
        results_by_id: dict[str, SubagentResult] = {}
        summary_lines: list[str] = []

        for spec in ordered_specs:
            t0 = time.perf_counter()
            effective_mode = clamp_work_mode(parent_work_mode, spec.work_mode)

            # 为每个子代理分配独立隔离的 ContextManager，绝不共享父/兄弟历史消息
            isolated_ctx = ContextManager(
                constitution=self.constitution,
                policy=CompactionPolicy(safe_effective_ctx=spec.effective_ctx_budget),
            )
            isolated_goal = (
                f"[角色: {spec.role}]\n[背景简报]\n{spec.brief}\n\n[子任务目标]\n{spec.goal}"
                if spec.brief.strip()
                else f"[角色: {spec.role}]\n[子任务目标]\n{spec.goal}"
            )

            step = StepInput(
                run_id=rid,
                task_id=tid,
                goal=isolated_goal,
                work_mode=effective_mode,
                interaction_mode=spec.interaction_mode,
                context_messages=[],  # 硬保证：子代理起始消息空白，逻辑隔离零污染
                effective_ctx_budget=spec.effective_ctx_budget,
                steering_hint=spec.steering_hint,
            )

            # 物理显存槽位切至当前 spec.model（同批次连续执行时不重复切换）
            self.resident_model = spec.model
            executed_ids.append(spec.subagent_id)
            executed_models.append(spec.model)

            try:
                worker = self._worker_factory(spec, isolated_ctx)
                step_out: StepOutput = worker.run(step)
                elapsed_ms = step_out.elapsed_ms or int((time.perf_counter() - t0) * 1000)
                sub_res = SubagentResult(
                    subagent_id=spec.subagent_id,
                    role=spec.role,
                    model=spec.model,
                    success=step_out.success,
                    summary=step_out.summary,
                    artifacts=list(step_out.artifacts),
                    model_notes=step_out.model_notes,
                    error=step_out.error,
                    elapsed_ms=elapsed_ms,
                    isolated_context_tokens=isolated_ctx.telemetry.last_tokens_after,
                    effective_work_mode=effective_mode,
                )
            except Exception as exc:  # noqa: BLE001
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                sub_res = SubagentResult(
                    subagent_id=spec.subagent_id,
                    role=spec.role,
                    model=spec.model,
                    success=False,
                    summary="",
                    error=f"SUBAGENT_EXCEPTION:{type(exc).__name__}: {exc}",
                    elapsed_ms=elapsed_ms,
                    effective_work_mode=effective_mode,
                )

            results_by_id[spec.subagent_id] = sub_res
            status_tag = "OK" if sub_res.success else "FAIL"
            brief_out = (sub_res.summary or sub_res.error or "").splitlines()[0][:140]
            summary_lines.append(f"- [{status_tag}] {spec.role} ({spec.model}): {brief_out}")

        optimized_switches = count_model_switches(executed_models, initial_resident=resident_before)
        all_ok = all(r.success for r in results_by_id.values()) if results_by_id else True

        return AffinityBatchReport(
            run_id=rid,
            parent_work_mode=parent_work_mode,
            resident_model_before=resident_before,
            resident_model_after=self.resident_model,
            submitted_order=submitted_ids,
            executed_order=executed_ids,
            executed_models=executed_models,
            naive_model_switches=naive_switches,
            optimized_model_switches=optimized_switches,
            switches_saved=max(0, naive_switches - optimized_switches),
            results=results_by_id,
            merged_summary="\n".join(summary_lines),
            all_succeeded=all_ok,
        )
