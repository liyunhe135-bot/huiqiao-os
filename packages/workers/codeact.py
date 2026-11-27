"""M09 B05 可验证代码自愈执行内核（CodeActWorker · 实现 WorkerProtocol）.

核心闭环：
  1. 联动 M08 SandboxManager：所有模型生成代码必须在 T1/T2/T3 离线安全沙箱内真实执行，严禁 NONE 裸跑；
  2. 联动 M01 strip_think_blocks：无缝兼容深度思考模型（<think>）与 JSON / ```python``` 双格式输出；
  3. 联动 M04 GovernanceGuard：严守 Ask 只读禁写 / Plan 人工预审 / Execute 授权执行三档红线；
  4. Claude 客观证据闸门（Evidence Gate）：拒绝模型未经真实沙箱执行通过就口头宣称 finish；
  5. 3 轮同错硬止损 + 上下文四件套：连续相同报错达上限立即止损并保留部分产物，诚实退让（C00 A5）。
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import time
from typing import Any, Callable

from packages.core.constitution import LoadedConstitution, load_constitution
from packages.core.contracts import (
    PolicyDecision,
    SandboxTier,
    StepInput,
    StepOutput,
    WorkMode,
)
from packages.governance.guard import GovernanceGuard
from packages.governance.hooks import HookPoint
from packages.llm_gateway.thinking import strip_think_blocks
from packages.sandbox.manager import SandboxManager
from packages.sandbox.models import SandboxLimits, SandboxRequest, SandboxResult
from packages.workers.context_engine import CompactionPolicy, ContextManager

InferFn = Callable[[list[dict[str, str]]], str]

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", flags=re.DOTALL)
_PY_FENCE_RE = re.compile(r"```(?:python|py)\s*\n(.*?)```", flags=re.DOTALL | re.IGNORECASE)
_HTML_FENCE_RE = re.compile(r"```(?:html|htm)\s*\n(.*?)```", flags=re.DOTALL | re.IGNORECASE)


def _normalize_error_signature(stderr: str, blocked_reason: str | None) -> str:
    """将报错归约为稳定指纹，用于准确识别“同错死循环”并触发 3 轮止损。"""
    if blocked_reason:
        return f"BLOCKED:{blocked_reason.strip()[:120]}"
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    if not lines:
        return "UNKNOWN_ERROR"
    return lines[-1][:160]


def _parse_codeact_response(raw_text: str) -> dict[str, Any]:
    """柔性解析模型响应：同时兼容严格 JSON 指令与自然 Markdown ```python``` 代码块。"""
    cleaned = strip_think_blocks(raw_text).strip()
    if not cleaned:
        raise ValueError("模型输出为空")

    # 1. 优先尝试解析 JSON 指令（支持 fenced json 或裸 JSON 对象）
    json_match = _JSON_FENCE_RE.search(cleaned)
    candidate = json_match.group(1) if json_match else cleaned
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(candidate[start : end + 1])
            if isinstance(obj, dict) and "action" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # 2. 柔性兼容：直接输出 ```python ... ``` 代码块自动视为 run_code
    py_match = _PY_FENCE_RE.search(cleaned)
    if py_match:
        code = py_match.group(1).strip()
        if code:
            return {"action": "run_code", "code": code}

    # 3. 柔性兼容：本地模型直接输出 ```html ... ``` 单页应用代码时，封装为沙箱深度契约校验（零外部CDN + 事件函数闭环校验）
    html_match = _HTML_FENCE_RE.search(cleaned)
    if html_match:
        html_src = html_match.group(1).strip()
        if html_src:
            auto_py = (
                "import pathlib, re\n"
                f"_html = {html_src!r}\n"
                "assert len(_html) >= 60, 'HTML 内容过短'\n"
                "_cdn = re.findall(r'<(?:script|link)\\b[^>]*(?:src|href)\\s*=\\s*[\"\\']https?://[^\"\\']+', _html, flags=re.I)\n"
                "assert not _cdn, f'违反100%离线规范，检测到外部CDN引用: {_cdn}'\n"
                "_scripts = '\\n'.join(re.findall(r'<script[^>]*>([\\s\\S]*?)</script>', _html, flags=re.I))\n"
                "_called = set(re.findall(r'\\bon(?:click|change|input|submit)\\s*=\\s*[\"\\']\\s*([a-zA-Z_$][\\w$]*)\\s*\\(', _html))\n"
                "_builtins = {'localStorage','sessionStorage','alert','confirm','prompt','console','document','window','location','history','Math','JSON','parseInt','parseFloat','setTimeout','clearTimeout','setInterval','clearInterval','event','this','return','if'}\n"
                "_missing_fns = [fn for fn in sorted(_called - _builtins) if not re.search(rf'(?:function\\s+{re.escape(fn)}\\b|(?:const|let|var|window\\.)\\s*{re.escape(fn)}\\s*=)', _scripts)]\n"
                "assert not _missing_fns, f'HTML 事件属性调用了 <script> 中未定义的函数: {_missing_fns}，请补齐函数实现或修正拼写！'\n"
                "pathlib.Path('index.html').write_text(_html, encoding='utf-8')\n"
                "print('HTML_APP_VERIFIED:', len(_html), 'bytes, bound_fns=', sorted(_called - _builtins))\n"
            )
            prose = _HTML_FENCE_RE.sub("", cleaned).strip()
            return {
                "action": "run_code",
                "code": auto_py,
                "_direct_html_app": True,
                "_prose_summary": prose,
            }

    raise ValueError("未检测到合法的 JSON 动作对象或 ```python``` / ```html``` 代码块")


class CodeActWorker:
    """B05 L2-C 高可验证 CodeAct 自愈执行内核（完整实现 WorkerProtocol）。"""

    def __init__(
        self,
        *,
        infer_fn: InferFn,
        sandbox: SandboxManager | None = None,
        sandbox_tier: SandboxTier = SandboxTier.T2_OS_RESTRICTED,
        workspace_dir: str | pathlib.Path | None = None,
        guard: GovernanceGuard | None = None,
        constitution: LoadedConstitution | None = None,
        context_manager: ContextManager | None = None,
        verifier_code: str | None = None,
        max_turns: int = 6,
        max_consecutive_same_error: int = 3,
        max_security_blocks: int = 2,
        timeout_sec: float = 15.0,
        max_memory_mb: int = 256,
        require_objective_verify: bool = True,
    ) -> None:
        if sandbox_tier == SandboxTier.NONE:
            raise ValueError("CodeActWorker 严禁使用 SandboxTier.NONE（必须过安全沙箱）。")
        self._infer_fn = infer_fn
        self.sandbox = sandbox or SandboxManager(offline_only=True, governance_guard=guard)
        self.sandbox_tier = sandbox_tier
        self.workspace_dir = str(pathlib.Path(workspace_dir).resolve()) if workspace_dir else None
        self.guard = guard
        self.constitution = constitution or load_constitution()
        self.context_manager = context_manager or ContextManager(constitution=self.constitution)
        self.verifier_code = verifier_code
        self.max_turns = max_turns
        self.max_consecutive_same_error = max_consecutive_same_error
        self.max_security_blocks = max_security_blocks
        self.timeout_sec = timeout_sec
        self.max_memory_mb = max_memory_mb
        self.require_objective_verify = require_objective_verify

    def healthcheck(self) -> bool:
        return self.sandbox.healthcheck()

    def _check_work_mode_gate(self, step: StepInput) -> StepOutput | None:
        """执行前联动 M04 GovernanceGuard 校验 Ask/Plan/Execute 三档红线。"""
        if self.guard is None:
            return None
        # T1 纯计算零文件系统读写视为 READ；T2/T3 工作区代码执行视为 EXECUTE
        perm = "READ" if self.sandbox_tier == SandboxTier.T1_WASM else "EXECUTE"
        verdict = self.guard.evaluate(
            HookPoint.PRE_TOOL_USE,
            {
                "run_id": step.run_id,
                "task_id": step.task_id,
                "work_mode": step.work_mode,
                "permission": perm,
                "offline_only": self.sandbox.offline_only,
                "target_path": self.workspace_dir,
                "allowed_paths": [self.workspace_dir] if self.workspace_dir else [],
            },
        )
        if verdict.decision == PolicyDecision.DENY:
            return StepOutput(
                run_id=step.run_id,
                task_id=step.task_id,
                step_id=step.step_id,
                brick_name="codeact_worker",
                success=False,
                summary="",
                error=f"CodeAct 被治理守卫拦截: {verdict.reason}",
                metadata={"policy_decision": "DENY"},
            )
        if verdict.decision == PolicyDecision.ASK_HUMAN:
            return StepOutput(
                run_id=step.run_id,
                task_id=step.task_id,
                step_id=step.step_id,
                brick_name="codeact_worker",
                success=False,
                summary=f"等待人工审批后执行沙箱代码: {verdict.reason}",
                needs_human_approval=True,
                metadata={
                    "policy_decision": "ASK_HUMAN",
                    "missing_evidence": verdict.missing_evidence,
                },
            )
        return None

    def _run_in_sandbox(self, code: str, *, work_mode: WorkMode, read_only: bool = False) -> SandboxResult:
        req = SandboxRequest(
            code=code,
            language="python",
            tier=self.sandbox_tier,
            workspace_dir=self.workspace_dir,
            limits=SandboxLimits(
                timeout_sec=self.timeout_sec,
                max_memory_mb=self.max_memory_mb,
                allow_network=False,
                read_only_workspace=read_only,
            ),
            work_mode=work_mode.value,
        )
        return self.sandbox.run(req)

    def run(self, step: StepInput) -> StepOutput:
        t0 = time.perf_counter()

        # 0. 动态同步 M02/StepInput 有效上下文预算到上下文四件套
        if step.effective_ctx_budget and step.effective_ctx_budget != self.context_manager.policy.safe_effective_ctx:
            self.context_manager.policy = CompactionPolicy(
                safe_effective_ctx=step.effective_ctx_budget,
                compact_ratio=self.context_manager.policy.compact_ratio,
                max_raw_messages=self.context_manager.policy.max_raw_messages,
                keep_recent_messages=self.context_manager.policy.keep_recent_messages,
                prune_observation_chars=self.context_manager.policy.prune_observation_chars,
            )

        gate_stop = self._check_work_mode_gate(step)
        if gate_stop is not None:
            return gate_stop

        role_instructions = (
            "你运行在汇桥 OS L2-C CodeAct 离线安全沙箱执行闭环中。\n"
            "每轮可输出 JSON 动作，或直接输出 ```python``` / ```html``` 代码块：\n"
            '- 执行代码: {"action": "run_code", "code": "Python代码", "verify_code": "可选校验代码"}\n'
            "- 若用户需求是『构建小程序 / 本地网页应用 / 打卡器 / 可视化工具』：请直接输出一个完整的单文件 ```html``` 代码块（内联美观的黑金配色 CSS 与原生 JS，使用 localStorage 本地持久化数据，严禁引用任何外部 http/https CDN），系统会自动在沙箱写入 index.html 并校验！\n"
            '- 验收交付: {"action": "finish", "summary": "客观交付结论与功能说明", "notes": "使用方式说明"}\n'
            '- 诚实退让: {"action": "defer", "summary": "说明受限原因与已保留的阶段产物"}\n'
            "硬规则：必须先通过真实沙箱执行并拿到客观成功证据，绝不允许未经运行就口头宣称完成。"
        )
        messages: list[dict[str, str]] = [
            self.context_manager.build_system_message(role_instructions),
        ]
        # 若调用方传入了历史消息，继承后仍由四件套统一清理与定界
        for ctx_msg in step.context_messages:
            if isinstance(ctx_msg, dict) and ctx_msg.get("role") in ("user", "assistant"):
                messages.append(
                    {"role": str(ctx_msg["role"]), "content": str(ctx_msg.get("content", ""))}
                )

        user_prompt = (
            f"{step.goal}\n[中途改向]: {step.steering_hint}"
            if step.steering_hint
            else step.goal
        )
        messages.append({"role": "user", "content": user_prompt})

        verified = False
        collected_artifacts: list[str] = []
        trace: list[dict[str, Any]] = []
        last_error_sig: str | None = None
        same_error_streak = 0
        security_blocks = 0
        last_failed_code_hash: str | None = None
        sandbox_runs = 0
        total_tokens_est = 0

        for turn in range(1, self.max_turns + 1):
            prepared = self.context_manager.prepare(messages)
            messages = prepared
            total_tokens_est += self.context_manager.telemetry.last_tokens_after

            raw = self._infer_fn(messages)
            try:
                cmd = _parse_codeact_response(raw)
            except Exception as exc:  # noqa: BLE001
                cleaned_natural = strip_think_blocks(raw).strip()
                # 若前序轮次已拿到客观沙箱验证通过证据，且本地模型直接给出了自然语言总结说明，柔性采纳为最终交付
                if verified and cleaned_natural and "```" not in cleaned_natural:
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    return StepOutput(
                        run_id=step.run_id,
                        task_id=step.task_id,
                        step_id=step.step_id,
                        brick_name="codeact_worker",
                        success=True,
                        summary=cleaned_natural,
                        artifacts=list(dict.fromkeys(collected_artifacts)),
                        model_notes="已通过安全沙箱客观执行验证并完成本地产物落盘。",
                        tokens_used=total_tokens_est,
                        elapsed_ms=elapsed_ms,
                        metadata={
                            "turns": turn,
                            "sandbox_runs": sandbox_runs,
                            "verified": verified,
                            "compactions": self.context_manager.telemetry.compaction_count,
                            "constitution_intact": self.context_manager.verify_constitution_intact(messages),
                            "trace": trace,
                        },
                    )
                messages.append({"role": "assistant", "content": cleaned_natural})
                messages.append(
                    {
                        "role": "user",
                        "content": f"[Format Error] 无法解析动作 ({exc})，请输出合法 JSON 或 ```python``` / ```html``` 代码块。",
                    }
                )
                trace.append({"turn": turn, "action": "parse_error", "error": str(exc)})
                continue

            action = str(cmd.get("action", "")).strip().lower()

            if action in ("defer", "honest_defer"):
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return StepOutput(
                    run_id=step.run_id,
                    task_id=step.task_id,
                    step_id=step.step_id,
                    brick_name="codeact_worker",
                    success=False,
                    summary=str(cmd.get("summary", "任务超出当前沙箱或信息边界，已诚实退让并保留阶段产物。")),
                    artifacts=list(dict.fromkeys(collected_artifacts)),
                    model_notes=str(cmd.get("notes", "")),
                    tokens_used=total_tokens_est,
                    elapsed_ms=elapsed_ms,
                    error="HONEST_DEFER",
                    metadata={
                        "turns": turn,
                        "sandbox_runs": sandbox_runs,
                        "verified": verified,
                        "compactions": self.context_manager.telemetry.compaction_count,
                        "constitution_intact": self.context_manager.verify_constitution_intact(messages),
                        "trace": trace,
                    },
                )

            if action == "finish":
                if self.require_objective_verify and not verified:
                    # Claude Evidence Gate: 拒绝未过客观沙箱验真的口头完成
                    messages.append({"role": "assistant", "content": json.dumps(cmd, ensure_ascii=False)})
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "[Evidence Gate 拒绝] 尚未通过客观沙箱运行验证，禁止口头宣称完成。"
                                "请先通过 run_code 在沙箱中执行并验证结果。"
                            ),
                        }
                    )
                    trace.append({"turn": turn, "action": "finish_rejected_unverified"})
                    continue

                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return StepOutput(
                    run_id=step.run_id,
                    task_id=step.task_id,
                    step_id=step.step_id,
                    brick_name="codeact_worker",
                    success=True,
                    summary=str(cmd.get("summary", "CodeAct 沙箱执行并客观验证通过。")),
                    artifacts=list(dict.fromkeys(collected_artifacts)),
                    model_notes=str(cmd.get("notes", "")),
                    tokens_used=total_tokens_est,
                    elapsed_ms=elapsed_ms,
                    metadata={
                        "turns": turn,
                        "sandbox_runs": sandbox_runs,
                        "verified": verified,
                        "compactions": self.context_manager.telemetry.compaction_count,
                        "constitution_intact": self.context_manager.verify_constitution_intact(messages),
                        "trace": trace,
                    },
                )

            if action == "run_code":
                code = str(cmd.get("code", "")).strip()
                if not code:
                    messages.append({"role": "assistant", "content": json.dumps(cmd, ensure_ascii=False)})
                    messages.append({"role": "user", "content": "[Error] run_code 缺少非空 code 字段。"})
                    continue

                code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]
                if code_hash == last_failed_code_hash:
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    return StepOutput(
                        run_id=step.run_id,
                        task_id=step.task_id,
                        step_id=step.step_id,
                        brick_name="codeact_worker",
                        success=False,
                        summary="检测到重复提交同一份失败代码，已触发防烧 Token 熔断并保留阶段产物。",
                        artifacts=list(dict.fromkeys(collected_artifacts)),
                        tokens_used=total_tokens_est,
                        elapsed_ms=elapsed_ms,
                        error="DUPLICATE_FAILING_CODE_STOP_LOSS",
                        metadata={
                            "turns": turn,
                            "sandbox_runs": sandbox_runs,
                            "verified": verified,
                            "trace": trace,
                        },
                    )

                sandbox_runs += 1
                res = self._run_in_sandbox(code, work_mode=step.work_mode)
                for art in res.artifacts:
                    full_art = (
                        str(pathlib.Path(self.workspace_dir) / art)
                        if self.workspace_dir
                        else art
                    )
                    collected_artifacts.append(full_art)

                trace.append(
                    {
                        "turn": turn,
                        "action": "run_code",
                        "ok": res.ok,
                        "exit_code": res.exit_code,
                        "blocked": res.blocked,
                        "timed_out": res.timed_out,
                        "artifacts": res.artifacts,
                    }
                )

                if res.blocked:
                    security_blocks += 1
                    last_failed_code_hash = code_hash
                    if security_blocks >= self.max_security_blocks:
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        return StepOutput(
                            run_id=step.run_id,
                            task_id=step.task_id,
                            step_id=step.step_id,
                            brick_name="codeact_worker",
                            success=False,
                            summary="代码连续触发安全沙箱越权/资源红线，已安全熔断。",
                            artifacts=list(dict.fromkeys(collected_artifacts)),
                            tokens_used=total_tokens_est,
                            elapsed_ms=elapsed_ms,
                            error=f"SANDBOX_SECURITY_ABORT:{res.blocked_reason}",
                            metadata={
                                "turns": turn,
                                "sandbox_runs": sandbox_runs,
                                "security_blocks": security_blocks,
                                "trace": trace,
                            },
                        )

                if not res.ok:
                    last_failed_code_hash = code_hash
                    err_sig = _normalize_error_signature(res.stderr, res.blocked_reason)
                    if err_sig == last_error_sig:
                        same_error_streak += 1
                    else:
                        last_error_sig = err_sig
                        same_error_streak = 1

                    if same_error_streak >= self.max_consecutive_same_error:
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        return StepOutput(
                            run_id=step.run_id,
                            task_id=step.task_id,
                            step_id=step.step_id,
                            brick_name="codeact_worker",
                            success=False,
                            summary=(
                                f"连续 {same_error_streak} 轮遇到相同错误，已触发 3 轮止损并保留当前阶段产物，"
                                "建议升级更强模型或由人类补充诊断信息。"
                            ),
                            artifacts=list(dict.fromkeys(collected_artifacts)),
                            tokens_used=total_tokens_est,
                            elapsed_ms=elapsed_ms,
                            error=f"SAME_ERROR_STOP_LOSS:{err_sig}",
                            metadata={
                                "turns": turn,
                                "sandbox_runs": sandbox_runs,
                                "same_error_streak": same_error_streak,
                                "trace": trace,
                            },
                        )

                    messages.append({"role": "assistant", "content": json.dumps(cmd, ensure_ascii=False)})
                    err_excerpt = (res.stderr or res.blocked_reason or "unknown error")[:1600]
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"[Sandbox Failed | exit={res.exit_code} | blocked={res.blocked} | timed_out={res.timed_out}]\n"
                                f"stdout:\n{res.stdout[:800]}\nstderr:\n{err_excerpt}\n"
                                "请根据上述客观报错定位根因并修正代码重试。"
                            ),
                        }
                    )
                    continue

                # 代码执行成功 -> 若配置了客观校验脚本（verifier_code 或 cmd.verify_code），继续在只读沙箱内跑校验
                last_failed_code_hash = None
                last_error_sig = None
                same_error_streak = 0
                active_verifier = self.verifier_code or (
                    str(cmd.get("verify_code", "")).strip() or None
                )
                verify_note = "沙箱执行 exit_code=0"
                if active_verifier:
                    sandbox_runs += 1
                    vres = self._run_in_sandbox(
                        active_verifier,
                        work_mode=step.work_mode,
                        read_only=True,
                    )
                    trace.append(
                        {
                            "turn": turn,
                            "action": "verify_code",
                            "ok": vres.ok,
                            "exit_code": vres.exit_code,
                        }
                    )
                    if not vres.ok:
                        messages.append({"role": "assistant", "content": json.dumps(cmd, ensure_ascii=False)})
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"[Objective Verifier Failed | exit={vres.exit_code}]\n"
                                    f"stdout:\n{vres.stdout[:600]}\nstderr:\n{vres.stderr[:1200]}\n"
                                    "代码虽运行结束但未通过客观验收断言，请修复后重试。"
                                ),
                            }
                        )
                        continue
                    verify_note = f"客观校验脚本通过 (stdout={vres.stdout.strip()[:200]})"

                verified = True
                if self.guard is not None:
                    self.guard.evidence.grant(step.run_id, "test_passed")

                # 真省流量提速：单页 HTML 应用一旦通过沙箱『零外部CDN + 事件函数闭环 + 客观断言』全部核验，直接交付，省去无意义的二次寒暄推理！
                if cmd.get("_direct_html_app"):
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    prose_sum = str(cmd.get("_prose_summary") or "").strip()
                    ver_line = res.stdout.strip().splitlines()[-1] if res.stdout.strip() else "index.html 沙箱验证通过"
                    final_sum = prose_sum if len(prose_sum) >= 12 else f"已完成本地离线交互应用构建并通过沙箱契约核验（`{ver_line}`）。"
                    return StepOutput(
                        run_id=step.run_id,
                        task_id=step.task_id,
                        step_id=step.step_id,
                        brick_name="codeact_worker",
                        success=True,
                        summary=final_sum,
                        artifacts=list(dict.fromkeys(collected_artifacts)),
                        model_notes=f"单轮闭环验真直达（零冗余复述轮次）· {ver_line}",
                        tokens_used=total_tokens_est,
                        elapsed_ms=elapsed_ms,
                        metadata={
                            "turns": turn,
                            "sandbox_runs": sandbox_runs,
                            "verified": True,
                            "compactions": self.context_manager.telemetry.compaction_count,
                            "constitution_intact": self.context_manager.verify_constitution_intact(messages),
                            "trace": trace,
                        },
                    )

                messages.append({"role": "assistant", "content": json.dumps(cmd, ensure_ascii=False)})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"[Sandbox Passed | exit=0 | {verify_note}]\n"
                            f"stdout:\n{res.stdout[:1200]}\n"
                            f"artifacts: {res.artifacts}\n"
                            "客观证据已签发，若已满足用户全部目标请输出 finish 动作汇总交付。"
                        ),
                    }
                )
                continue

            messages.append({"role": "assistant", "content": strip_think_blocks(raw)})
            messages.append(
                {
                    "role": "user",
                    "content": f"[Error] 不支持的 action='{action}'，仅支持 run_code / finish / defer。",
                }
            )

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return StepOutput(
            run_id=step.run_id,
            task_id=step.task_id,
            step_id=step.step_id,
            brick_name="codeact_worker",
            success=False,
            summary="超过最大 CodeAct 迭代轮次上限，已安全止损并保留当前产物。",
            artifacts=list(dict.fromkeys(collected_artifacts)),
            tokens_used=total_tokens_est,
            elapsed_ms=elapsed_ms,
            error=f"MAX_TURNS_EXCEEDED:{self.max_turns}",
            metadata={
                "turns": self.max_turns,
                "sandbox_runs": sandbox_runs,
                "verified": verified,
                "compactions": self.context_manager.telemetry.compaction_count,
                "constitution_intact": self.context_manager.verify_constitution_intact(messages),
                "trace": trace,
            },
        )
