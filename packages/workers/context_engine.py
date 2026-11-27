"""M09 B05 上下文工程四件套（清理 / 双触发压缩 / 摘要化 / C00 宪章重注 + KV 前缀缓存锁）.

面向本地 14B–32B 有限有效上下文（如 RULER 实测 safe_effective_ctx=8192~16384）：
  1. 清理（Observation Pruning）：剥离历史 <think> 块，并把早期冗长沙箱/工具输出脱水为短锚点；
  2. 双触发压缩（Dual-Trigger Compaction）：Token 占比触发（>= compact_ratio * budget）
     与轮次/消息数触发（>= max_raw_messages）任一命中即自动压缩；
  3. 摘要化（Structured Rolling Summary）：锁定 messages[0] 系统前缀不动（保护 KV Prefix Cache），
     保留最近 keep_recent_messages 条原始对话，中间历史归并为结构化工作记忆摘要；
  4. 宪章强重注（C00 Anti-Amnesia Reinjection）：每次压缩后强制校验并在摘要区锚定 C00 精炼宪章，
     确保长程多轮执行绝不遗忘“助众生和谐增上 / 反人矿 / 透明可逆”底线。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable

from packages.core.constitution import LoadedConstitution, load_constitution
from packages.llm_gateway.thinking import strip_think_blocks

SummarizerFn = Callable[[list[dict[str, str]]], str]

C00_REINJECT_MARKER = "[C00 宪章锚点重注]"
COMPACT_SUMMARY_MARKER = "[Compacted Working Memory]"


def estimate_tokens(text: str) -> int:
    """零依赖中英混合 Token 轻量估算器（避免引入重型 tokenizer 依赖）。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, int(cjk * 0.72 + other * 0.30))


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    return sum(estimate_tokens(m.get("content", "")) + 6 for m in messages)


@dataclass
class CompactionPolicy:
    """上下文四件套参数策略（可对接 M02 CapabilityProfile.safe_effective_ctx）。"""

    safe_effective_ctx: int = 8192
    compact_ratio: float = 0.75
    max_raw_messages: int = 16
    keep_recent_messages: int = 6
    prune_observation_chars: int = 600
    prune_keep_head: int = 180
    prune_keep_tail: int = 120
    max_summary_chars: int = 1800


@dataclass
class ContextTelemetry:
    """上下文工程运行遥测（供可观测性与单测客观核验）。"""

    prune_count: int = 0
    pruned_chars: int = 0
    compaction_count: int = 0
    reinject_count: int = 0
    last_trigger_reason: str | None = None
    last_tokens_before: int = 0
    last_tokens_after: int = 0
    prefix_sha256: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)


class ContextManager:
    """汇桥 OS 上下文四件套引擎（零外部依赖、KV 前缀稳定、C00 零遗忘）。"""

    def __init__(
        self,
        *,
        constitution: LoadedConstitution | None = None,
        policy: CompactionPolicy | None = None,
        summarizer_fn: SummarizerFn | None = None,
    ) -> None:
        self.constitution = constitution or load_constitution()
        self.policy = policy or CompactionPolicy()
        self._summarizer_fn = summarizer_fn
        self.telemetry = ContextTelemetry()
        self._locked_prefix_hash: str | None = None

    def build_system_message(self, role_instructions: str) -> dict[str, str]:
        """构建带 C00 宪章前缀锁的 system 消息，并锁定前缀指纹。"""
        prefix = self.constitution.as_system_prefix()
        content = f"{prefix}\n\n{role_instructions.strip()}" if role_instructions.strip() else prefix
        self._locked_prefix_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.telemetry.prefix_sha256 = self._locked_prefix_hash
        return {"role": "system", "content": content}

    def prune_observations(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """第 1 件套：清理历史 <think> 推理残渣与超长过期工具/沙箱观察输出。"""
        if len(messages) <= 1:
            return [dict(m) for m in messages]

        result = [dict(m) for m in messages]
        # 保留首条 system 与尾部 keep_recent_messages 不做观测截断，保护当前排错现场
        tail_start = max(1, len(result) - self.policy.keep_recent_messages)

        for idx in range(1, tail_start):
            msg = result[idx]
            content = msg.get("content", "")
            orig_len = len(content)

            # 剥离历史 assistant 的 <think> 块
            if msg.get("role") == "assistant" and "<think>" in content:
                cleaned = strip_think_blocks(content)
                if len(cleaned) < orig_len:
                    msg["content"] = cleaned
                    self.telemetry.prune_count += 1
                    self.telemetry.pruned_chars += orig_len - len(cleaned)
                    content = cleaned
                    orig_len = len(content)

            # 清理历史冗长 Observation / Sandbox 输出（跳过已压缩摘要块）
            if (
                orig_len > self.policy.prune_observation_chars
                and COMPACT_SUMMARY_MARKER not in content
                and C00_REINJECT_MARKER not in content
            ):
                head = content[: self.policy.prune_keep_head].rstrip()
                tail = content[-self.policy.prune_keep_tail :].lstrip()
                pruned = (
                    f"[Pruned historical output: {orig_len} chars -> kept head/tail]\n"
                    f"{head}\n... (已清理 {orig_len - len(head) - len(tail)} 字符) ...\n{tail}"
                )
                msg["content"] = pruned
                self.telemetry.prune_count += 1
                self.telemetry.pruned_chars += max(0, orig_len - len(pruned))

        return result

    def _detect_compaction_trigger(self, messages: list[dict[str, str]]) -> str | None:
        """第 2 件套：双触发检测（Token 预算占比 OR 原始消息轮次上限）。"""
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) <= self.policy.keep_recent_messages:
            return None

        toks = estimate_messages_tokens(messages)
        budget_limit = int(self.policy.safe_effective_ctx * self.policy.compact_ratio)
        if toks >= budget_limit:
            return f"TOKEN_RATIO_TRIGGER:{toks}/{self.policy.safe_effective_ctx}"
        if len(non_system) >= self.policy.max_raw_messages:
            return f"MESSAGE_COUNT_TRIGGER:{len(non_system)}/{self.policy.max_raw_messages}"
        return None

    @staticmethod
    def _extract_high_signal_clauses(text: str, *, max_chars: int = 360) -> str:
        """高纯度无损信号提炼：只剥离空白与客套噪音，优先完整保留编号条款、「必保原文」、路径与异常根因行。"""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return ""
        prioritized: list[str] = []
        for ln in lines:
            if (
                "「" in ln
                or "『" in ln
                or ln[:3].lstrip().startswith(("1.", "2.", "3.", "4.", "a)", "b)", "c)", "d)", "- ", "* "))
                or any(k in ln for k in ("Error", "Exception", "AssertionError", "localStorage", ".html", ".py", "不得改动", "必须"))
            ):
                prioritized.append(ln)
        if not prioritized:
            prioritized = lines[:3]
        elif lines[0] not in prioritized:
            prioritized.insert(0, lines[0])
        joined = " ； ".join(prioritized)
        return joined if len(joined) <= max_chars else (joined[: max_chars - 3] + "...")

    def _deterministic_summarize(self, middle: list[dict[str, str]]) -> str:
        """第 3 件套（零模型高纯度确定性摘要器）：结构化锁死不可变原文契约、分项要求、动作、报错根因与产物线索。"""
        goals: list[str] = []
        actions: list[str] = []
        errors: list[str] = []
        artifacts: list[str] = []
        steerings: list[str] = []
        invariants: list[str] = []
        prev_summaries: list[str] = []

        for msg in middle:
            role = msg.get("role", "")
            text = strip_think_blocks(msg.get("content", "")).strip()
            if not text:
                continue
            if COMPACT_SUMMARY_MARKER in text:
                for line in text.splitlines():
                    line_s = line.strip()
                    if line_s.startswith("- ") and len(prev_summaries) < 8:
                        prev_summaries.append(line_s)
                continue

            dense_digest = self._extract_high_signal_clauses(text, max_chars=360)
            if "「" in text or "不得改动" in text or "逐字" in text:
                for ln in text.splitlines():
                    if ("「" in ln or "不得改动" in ln or "逐字" in ln) and ln.strip() not in invariants:
                        invariants.append(ln.strip()[:260])

            if "[中途改向]" in text or "steering" in text.lower():
                steerings.append(dense_digest)
            if role == "user" and not text.startswith(("[Observation", "[Sandbox", "[Pruned")):
                if len(goals) < 4:
                    goals.append(dense_digest)
            if any(k in text for k in ("Error", "Traceback", "AssertionError", "FAIL", "BLOCKED", "失败", "拦截")):
                err_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                tail_err = err_lines[-1][:200] if err_lines else dense_digest
                if len(errors) < 4:
                    errors.append(tail_err)
            if any(k in text for k in ("artifacts", "产出", ".json", ".md", ".py", ".csv", ".html")):
                if len(artifacts) < 4:
                    artifacts.append(dense_digest[:200])
            if role == "assistant" and len(actions) < 5:
                actions.append(text.splitlines()[0].strip()[:160])

        lines: list[str] = [COMPACT_SUMMARY_MARKER]
        if prev_summaries:
            lines.append("【前序压缩要点】")
            lines.extend(prev_summaries[:5])
        if invariants:
            lines.append(f"- 不可变契约与必保原文(严禁丢失): {' || '.join(invariants[:4])}")
        if goals:
            lines.append(f"- 核心目标与分项要求: {' | '.join(goals)}")
        if steerings:
            lines.append(f"- 人类改向与经验约束: {' | '.join(steerings[-2:])}")
        if actions:
            lines.append(f"- 已执行步骤({len(middle)}条历史): {' -> '.join(actions[-3:])}")
        if errors:
            lines.append(f"- 历史错误/拦截根因: {' ; '.join(errors[-3:])}")
        if artifacts:
            lines.append(f"- 相关产物线索: {' ; '.join(artifacts[-3:])}")

        summary = "\n".join(lines)
        if len(summary) > self.policy.max_summary_chars:
            summary = summary[: self.policy.max_summary_chars - 20].rstrip() + "\n... (摘要已定界)"
        return summary

    def _build_constitution_reinject_block(self) -> str:
        """第 4 件套：构建极简 C00 宪章重注锚点（低 Token 损耗、核心公理 100% 在场）。"""
        return (
            f"{C00_REINJECT_MARKER}\n"
            f"{self.constitution.as_system_prefix()}\n"
            "【底线自检】严守本地离线安全、透明可逆与客观验真，拒绝人矿化与虚报完成。"
        )

    def ensure_system_prefix(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """确保 messages[0] 永远持有 C00 前缀且不破坏 KV Prefix Cache。"""
        out = [dict(m) for m in messages]
        prefix = self.constitution.as_system_prefix()
        if not out or out[0].get("role") != "system":
            sys_msg = self.build_system_message("")
            out.insert(0, sys_msg)
        else:
            if "助众生和谐增上" not in out[0].get("content", ""):
                out[0]["content"] = f"{prefix}\n\n{out[0].get('content', '')}"
            cur_hash = hashlib.sha256(out[0]["content"].encode("utf-8")).hexdigest()
            if self._locked_prefix_hash is None:
                self._locked_prefix_hash = cur_hash
                self.telemetry.prefix_sha256 = cur_hash
        return out

    def compact_if_needed(
        self,
        messages: list[dict[str, str]],
        *,
        force: bool = False,
    ) -> tuple[list[dict[str, str]], bool]:
        """执行双触发压缩 + 摘要化 + C00 强重注。返回 (新消息列表, 是否发生了压缩)。"""
        working = self.ensure_system_prefix(messages)
        tokens_before = estimate_messages_tokens(working)
        trigger = "FORCED_COMPACTION" if force else self._detect_compaction_trigger(working)
        if trigger is None:
            self.telemetry.last_tokens_before = tokens_before
            self.telemetry.last_tokens_after = tokens_before
            return working, False

        sys_msg = working[0]
        rest = working[1:]
        keep_n = min(self.policy.keep_recent_messages, max(1, len(rest) - 1))
        middle = rest[:-keep_n] if len(rest) > keep_n else []
        recent = rest[-keep_n:]

        if not middle:
            return working, False

        if self._summarizer_fn is not None:
            raw_summary = strip_think_blocks(self._summarizer_fn(middle)).strip()
            if COMPACT_SUMMARY_MARKER not in raw_summary:
                raw_summary = f"{COMPACT_SUMMARY_MARKER}\n{raw_summary}"
            summary_text = raw_summary[: self.policy.max_summary_chars]
        else:
            summary_text = self._deterministic_summarize(middle)

        # 合并结构化摘要与 C00 宪章锚点重注，保持 messages[0] 纹丝不动（KV Prefix Cache 零失效！）
        reinject_block = self._build_constitution_reinject_block()
        compacted_msg = {
            "role": "user",
            "content": f"{summary_text}\n\n{reinject_block}",
        }
        new_messages = [sys_msg, compacted_msg, *recent]
        tokens_after = estimate_messages_tokens(new_messages)

        self.telemetry.compaction_count += 1
        self.telemetry.reinject_count += 1
        self.telemetry.last_trigger_reason = trigger
        self.telemetry.last_tokens_before = tokens_before
        self.telemetry.last_tokens_after = tokens_after
        self.telemetry.history.append(
            {
                "trigger": trigger,
                "collapsed_messages": len(middle),
                "tokens_before": tokens_before,
                "tokens_after": tokens_after,
            }
        )
        return new_messages, True

    def prepare(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """单入口执行完整四件套：锁定前缀 -> 清理历史观察 -> 双触发压缩+摘要化+C00重注。"""
        anchored = self.ensure_system_prefix(messages)
        pruned = self.prune_observations(anchored)
        compacted, _ = self.compact_if_needed(pruned)
        return compacted

    def verify_constitution_intact(self, messages: list[dict[str, str]]) -> bool:
        """客观核验 C00 核心公理是否在当前上下文前缀（及压缩重注锚点）中完整保留。"""
        if not messages or messages[0].get("role") != "system":
            return False
        sys_text = messages[0].get("content", "")
        has_prefix = "助众生和谐增上" in sys_text and "人矿" in sys_text
        if not has_prefix:
            return False
        if self.telemetry.compaction_count > 0:
            has_reinject = any(
                C00_REINJECT_MARKER in m.get("content", "") and "助众生和谐增上" in m.get("content", "")
                for m in messages[1:]
            )
            return has_reinject
        return True
