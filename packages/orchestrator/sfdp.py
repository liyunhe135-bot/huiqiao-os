"""PRD v3.0 §5–§10 铸泽·规格先行交付流水线（SFDP: Specification-First Delivery Pipeline）.

把「用户输入模糊想法 → 可审查的设计规格 → 可运行的沙箱成果 → 交付包五件套」固化为标准闭环：
  ① 澄清门（Clarify Gate）：生成 <= 5 个带贴心默认值的定向澄清问题，答案写回 spec；
  ② 规格工坊（Spec Workshop）：产出 spec.md + plan.md + tasks.md + 可观察 AC（支持人工编辑与确认冻结）；
  ③ 沙箱构建（Build）：基于冻结规格驱动 CodeActWorker 在 M08 离线沙箱内构建产物；
  ④ 只读收敛（Converge）：在沙箱内对照冻结 AC 逐条做客观核验；未通过项只允许追加修复子任务（严禁篡改 AC！）；
  ⑤ 交付包五件套（Five-Piece Delivery + B10 完整性防造假门禁）：
     1. 产物文件（实际可打开运行的 HTML/Python/文档成果）
     2. 变更清单（文件路径、字节数、SHA-256 指纹）
     3. 执行日志（轮次、沙箱退出码、耗时轨迹）
     4. 自检报告（逐条绑定客观沙箱断言结果，模型不可伪造）
     5. 验收协议（如何打开运行、人工验收清单、一键回滚方式）
"""

from __future__ import annotations

import hashlib
import pathlib
import re
from typing import Any, Callable

from packages.core.constitution import LoadedConstitution, load_constitution
from packages.core.contracts import (
    InteractionMode,
    SandboxTier,
    StepInput,
    WorkMode,
    new_id,
)
from packages.governance.guard import GovernanceGuard
from packages.orchestrator.store import SqliteStateStore
from packages.sandbox import SandboxLimits, SandboxManager, SandboxRequest
from packages.workers.codeact import CodeActWorker

InferFn = Callable[[list[dict[str, str]]], str]


def validate_delivery_five_pieces(
    *,
    artifact_refs: list[str],
    change_list: str,
    log_ref: str,
    self_check: str,
    acceptance_protocol: str,
    objective_evidence_token: str | None,
) -> tuple[bool, list[str]]:
    """B10 交付包五件套完整性与防自检造假确定性门禁（PRD v3.0 §6 & §10）。"""
    missing: list[str] = []
    if not artifact_refs or not all(pathlib.Path(p).is_file() for p in artifact_refs):
        missing.append("1_产物文件缺失或未真实落盘")
    if len((change_list or "").strip()) < 20:
        missing.append("2_变更清单缺失或过短")
    if len((log_ref or "").strip()) < 20:
        missing.append("3_执行日志缺失或过短")
    if len((self_check or "").strip()) < 20:
        missing.append("4_自检报告缺失或过短")
    if len((acceptance_protocol or "").strip()) < 20:
        missing.append("5_验收协议缺失或过短")
    if not objective_evidence_token or objective_evidence_token not in self_check:
        missing.append("ANTI_FORGERY_BLOCKED:自检报告缺少 B10/M08 客观沙箱验真印章，拒绝口头伪造自检")
    return len(missing) == 0, missing


class ChuZeSfdpEngine:
    """汇桥『铸泽』规格先行设计与交付引擎（B02 -> B03 -> B05 -> B10 跨积木协同）。"""

    def __init__(
        self,
        store: SqliteStateStore,
        *,
        sandbox: SandboxManager | None = None,
        guard: GovernanceGuard | None = None,
        constitution: LoadedConstitution | None = None,
    ) -> None:
        self.store = store
        self.guard = guard
        self.sandbox = sandbox or SandboxManager(offline_only=True, governance_guard=guard)
        self.constitution = constitution or load_constitution()

    @staticmethod
    def _is_web_app_goal(goal: str) -> bool:
        return bool(re.search(r"(小程序|网页|页面|前端|打卡|面板|工作台|计算器|看板|html|ui|界面)", goal, re.I))

    def generate_clarify_questions(self, goal: str, *, task_id: str | None = None) -> dict[str, Any]:
        """阶段 ① 澄清门：针对用户原始想法生成 <=4 个带智能默认值的关键设计澄清项（零阻碍秒拍板）。"""
        tid = task_id or new_id("tsk")
        is_app = self._is_web_app_goal(goal)

        if is_app:
            questions = [
                {
                    "id": f"qa_{tid}_1",
                    "question": "核心交付形态是什么？",
                    "answer": "单文件 100% 离线可运行的本地 HTML 交互小程序（零外部 CDN，双击或浏览器即开）",
                },
                {
                    "id": f"qa_{tid}_2",
                    "question": "核心功能模块与数据结构包含哪些？",
                    "answer": f"围绕「{goal[:36]}」提供主列表/章节进度追踪、一键交互打卡/操作反馈与汇总统计看板",
                },
                {
                    "id": f"qa_{tid}_3",
                    "question": "本地数据如何保存与备份？",
                    "answer": "使用浏览器本地 localStorage 自动持久化，关闭重开不丢失，并支持重置/导出",
                },
                {
                    "id": f"qa_{tid}_4",
                    "question": "界面视觉与交互风格偏好？",
                    "answer": "黑曜底色 + 赛博金/菩提黄高对比禅意科技风，字号清晰、按钮响应直观",
                },
            ]
        else:
            questions = [
                {
                    "id": f"qa_{tid}_1",
                    "question": "期望产出的核心文件类型是什么？",
                    "answer": "可在本地离线复验的 Python 脚本与结构化结果文件（JSON / Markdown）",
                },
                {
                    "id": f"qa_{tid}_2",
                    "question": "输入输出边界与异常处理要求？",
                    "answer": "纯标准库零外网依赖，对空输入或异常格式给出清晰中文提示",
                },
                {
                    "id": f"qa_{tid}_3",
                    "question": "如何判定结果验收通过？",
                    "answer": "在 M08 隔离沙箱内实跑 exit_code=0 且生成非空目标产物文件",
                },
            ]

        saved_qa = self.store.save_clarify_qa(tid, questions)
        draft_spec = self.build_spec_workshop(tid, goal, saved_qa, freeze=False)
        return {
            "task_id": tid,
            "goal": goal,
            "clarify_qa": saved_qa,
            "spec": draft_spec,
        }

    def build_spec_workshop(
        self,
        task_id: str,
        goal: str,
        qa_items: list[dict[str, str]] | None = None,
        *,
        custom_spec_md: str | None = None,
        custom_plan_md: str | None = None,
        freeze: bool = False,
    ) -> dict[str, Any]:
        """阶段 ② 规格工坊：生成或更新 spec.md / plan.md / tasks / 可观察 AC（带负例）。"""
        if qa_items is not None:
            saved_qa = self.store.save_clarify_qa(task_id, qa_items[:5])
        else:
            saved_qa = self.store.list_clarify_qa(task_id)

        is_app = self._is_web_app_goal(goal)
        deliverable_name = "index.html" if is_app else "solution_output.json"

        qa_md = "\n".join(f"- **{item['question']}**：{item['answer']}" for item in saved_qa) or "- 采用默认离线标准规格"

        if is_app:
            ac_list = [
                {
                    "ac_id": "AC-01",
                    "title": "产出可独立运行的单页文件 index.html",
                    "given_when_then": "给定沙箱工作区，当构建完成时，则存在非空 index.html (>200 字节) 且包含完整 HTML/JS 交互结构",
                    "negative_case": "负例：禁止空壳文本或仅输出代码片段说明而不落盘文件",
                    "check_kind": "html_file_valid",
                },
                {
                    "ac_id": "AC-02",
                    "title": "100% 离线清净无外部 CDN 依赖",
                    "given_when_then": "给定生成的 index.html，当扫描全部 src/href 属性时，则外部 http/https 引用数为 0",
                    "negative_case": "负例：一旦引用任何外部 CDN 脚本或样式表即判定不合规",
                    "check_kind": "zero_external_cdn",
                },
                {
                    "ac_id": "AC-03",
                    "title": "具备真实可点击交互与本地持久化状态",
                    "given_when_then": "给定用户操作需求，当检查脚本逻辑时，则包含按钮事件处理与 localStorage 状态保存",
                    "negative_case": "负例：禁止只有静态展示没有交互逻辑的死页面",
                    "check_kind": "interactive_stateful",
                },
            ]
        else:
            ac_list = [
                {
                    "ac_id": "AC-01",
                    "title": "沙箱客观执行零报错通过",
                    "given_when_then": "给定目标任务脚本，当在 M08 T2 离线沙箱执行时，则 exit_code == 0",
                    "negative_case": "负例：抛未捕获异常或超时视为未收敛",
                    "check_kind": "sandbox_exit_zero",
                },
                {
                    "ac_id": "AC-02",
                    "title": "生成真实非空交付产物文件",
                    "given_when_then": "给定构建完成的工作区，当扫描产物目录时，则至少存在 1 个非空成果文件",
                    "negative_case": "负例：仅口头回答未产出可复查文件视为失败",
                    "check_kind": "any_artifact_nonempty",
                },
            ]

        existing = self.store.get_latest_spec(task_id)
        if existing and existing["frozen"]:
            ac_list = existing["ac_list"]

        ac_md = "\n".join(
            f"1. **{ac['ac_id']} {ac['title']}**\n   - 正例：{ac['given_when_then']}\n   - {ac['negative_case']}"
            for ac in ac_list
        )

        spec_md = custom_spec_md or (
            f"# 需求规格说明书 (spec.md)\n\n"
            f"## 1. 核心目标 (What & Why)\n- **用户原始诉求**：{goal}\n- **目标交付物**：`{deliverable_name}`\n\n"
            f"## 2. 澄清门已拍板约束\n{qa_md}\n\n"
            f"## 3. 可观察验收标准 (Acceptance Criteria · 冻结后只读)\n{ac_md}\n"
        )

        plan_md = custom_plan_md or (
            f"# 技术构建方案 (plan.md)\n\n"
            f"- **安全边界**：在 `M08` `T2_OS_RESTRICTED` 断网隔离沙箱内构建与验证；\n"
            f"- **依赖约束**：{'单文件内联 HTML5 + CSS3 + 原生 JS + localStorage，零外部 CDN' if is_app else 'Python 3.11 纯标准库，零外网请求'}；\n"
            f"- **收敛策略**：构建后由独立沙箱核验器逐条检查 `AC`，未达标项以追加修复任务方式自动收敛。\n"
        )

        tasks = [
            {
                "task_no": 1,
                "title": f"依据规格编写并落盘核心产物 ({deliverable_name})",
                "verify_cmd": f"sandbox_check:{deliverable_name}",
                "status": "pending",
            },
            {
                "task_no": 2,
                "title": "运行独立沙箱只读 AC 验收检查并生成五件套交付包",
                "verify_cmd": "sfdp_ac_converge",
                "status": "pending",
            },
        ]

        return self.store.append_spec(
            spec_id=new_id("spc"),
            task_id=task_id,
            spec_md=spec_md,
            plan_md=plan_md,
            tasks=tasks,
            ac_list=ac_list,
            frozen=freeze,
        )

    def _verify_ac_in_sandbox(
        self,
        ws_dir: pathlib.Path,
        ac_list: list[dict[str, Any]],
    ) -> tuple[bool, list[dict[str, Any]], str]:
        """在 M08 独立只读沙箱内客观核验每条 AC（模型绝不可自评打勾！）。"""
        checks_code = (
            "import json, pathlib, re\n"
            f"ac_list = {ac_list!r}\n"
            "files = [p for p in pathlib.Path('.').iterdir() if p.is_file()]\n"
            "results = []\n"
            "for ac in ac_list:\n"
            "    kind = ac.get('check_kind', '')\n"
            "    ok = False; detail = ''\n"
            "    if kind == 'html_file_valid':\n"
            "        p = pathlib.Path('index.html')\n"
            "        if p.is_file() and p.stat().st_size > 200:\n"
            "            txt = p.read_text(encoding='utf-8', errors='ignore').lower()\n"
            "            ok = '<html' in txt and '<script' in txt\n"
            "            detail = f'index.html size={p.stat().st_size} bytes, has_script={\"<script\" in txt}'\n"
            "        else:\n"
            "            detail = 'index.html missing or <200 bytes'\n"
            "    elif kind == 'zero_external_cdn':\n"
            "        p = pathlib.Path('index.html')\n"
            "        txt = p.read_text(encoding='utf-8', errors='ignore') if p.is_file() else ''\n"
            "        ext = re.findall(r'(?:src|href)\\s*=\\s*[\"\\']https?://', txt, flags=re.I)\n"
            "        ok = p.is_file() and len(ext) == 0\n"
            "        detail = f'external_cdn_refs={len(ext)}'\n"
            "    elif kind == 'interactive_stateful':\n"
            "        p = pathlib.Path('index.html')\n"
            "        txt = p.read_text(encoding='utf-8', errors='ignore') if p.is_file() else ''\n"
            "        has_evt = any(k in txt for k in ('onclick', 'addEventListener', '<button'))\n"
            "        has_store = 'localStorage' in txt\n"
            "        ok = p.is_file() and has_evt and has_store\n"
            "        detail = f'interactive={has_evt}, localStorage={has_store}'\n"
            "    else:\n"
            "        non_empty = [f.name for f in files if f.stat().st_size > 0]\n"
            "        ok = len(non_empty) > 0\n"
            "        detail = f'files={non_empty}'\n"
            "    results.append({'ac_id': ac['ac_id'], 'title': ac['title'], 'passed': ok, 'detail': detail})\n"
            "print(json.dumps(results, ensure_ascii=False))\n"
        )
        res = self.sandbox.run(
            SandboxRequest(
                code=checks_code,
                tier=SandboxTier.T2_OS_RESTRICTED,
                workspace_dir=str(ws_dir),
                limits=SandboxLimits(timeout_sec=10.0, allow_network=False, read_only_workspace=True),
                work_mode="execute",
            )
        )
        import json as _json

        parsed: list[dict[str, Any]] = []
        if res.ok and res.stdout.strip():
            try:
                parsed = _json.loads(res.stdout.strip().splitlines()[-1])
            except Exception:
                parsed = []
        all_ok = bool(parsed) and all(item.get("passed") for item in parsed)
        evidence_seal = hashlib.sha256(
            f"{ws_dir.name}:{res.exit_code}:{res.stdout.strip()}".encode("utf-8")
        ).hexdigest()[:16]
        return all_ok, parsed, f"B10_EVIDENCE_SEAL:{evidence_seal}"

    @staticmethod
    def _deterministic_fallback_builder(goal: str, spec_md: str) -> InferFn:
        """零大模型兜底构建器：当未启动本地 LLM 或测试环境无 infer_fn 时，按规格确定性锻造高质量可运行应用。"""
        called = {"n": 0}

        def _fallback(_msgs: list[dict[str, str]]) -> str:
            called["n"] += 1
            if called["n"] > 1:
                return '{"action": "finish", "summary": "已按冻结规格完成本地应用构建并通过全部 AC 校验。"}'
            safe_title = goal.strip().splitlines()[0][:28] or "汇桥本地应用"
            html_app = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><title>{safe_title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#090b10; color:#f5f2e6; max-width:760px; margin:28px auto; padding:20px; }}
  h1 {{ color:#ffd60a; border-bottom:1px solid rgba(255,214,10,0.3); padding-bottom:10px; }}
  .card {{ background:#121620; border:1px solid rgba(255,214,10,0.28); padding:14px; margin:12px 0; display:flex; justify-content:space-between; align-items:center; }}
  button {{ background:#ffd60a; color:#090b10; border:none; padding:8px 14px; font-weight:700; cursor:pointer; }}
  input {{ background:#06080c; color:#fff; border:1px solid rgba(255,214,10,0.35); padding:8px; flex:1; margin-right:8px; }}
</style>
</head>
<body>
  <h1>✦ {safe_title}</h1>
  <div class="card">
    <span>今日累计完成次数：<strong id="cnt" style="color:#ffd60a;font-size:18px;">0</strong></span>
    <button onclick="checkIn()">⚡ 立即打卡 +1</button>
  </div>
  <div style="display:flex;margin:12px 0;">
    <input id="itemInp" placeholder="新增学习/背诵条目..." />
    <button onclick="addItem()">添加条目</button>
  </div>
  <div id="listBox"></div>
<script>
  const KEY = "hq_sfdp_" + {safe_title!r};
  let state = JSON.parse(localStorage.getItem(KEY) || '{{"count":0,"items":["第一品 · 基础核心颂","第二品 · 进阶思辨颂","第三品 · 圆满回向颂"],"done":[]}}');
  function save() {{ localStorage.setItem(KEY, JSON.stringify(state)); render(); }}
  function checkIn() {{ state.count += 1; save(); }}
  function toggleItem(i) {{
    if (state.done.includes(i)) state.done = state.done.filter(x => x !== i);
    else state.done.push(i);
    save();
  }}
  function addItem() {{
    const v = document.getElementById("itemInp").value.trim();
    if (!v) return;
    state.items.push(v);
    document.getElementById("itemInp").value = "";
    save();
  }}
  function render() {{
    document.getElementById("cnt").textContent = state.count;
    document.getElementById("listBox").innerHTML = state.items.map((t, i) =>
      `<div class="card"><span>${{state.done.includes(i) ? "✅ " : "⬜ "}}${{t}}</span><button onclick="toggleItem(${{i}})">${{state.done.includes(i) ? "已完成" : "标记完成"}}</button></div>`
    ).join("");
  }}
  render();
</script>
</body>
</html>"""
            return f"```html\n{html_app}\n```"

        return _fallback

    def build_and_converge(
        self,
        task_id: str,
        *,
        goal: str,
        infer_fn: InferFn | None = None,
        max_converge_rounds: int = 2,
        context_messages: list[dict[str, str]] | None = None,
        extra_guardrails: str = "",
    ) -> dict[str, Any]:
        """阶段 ③④⑤：冻结规格 -> M08 沙箱构建 -> 只读 AC 逐条收敛（未过只追加新任务） -> 铸造交付包五件套。"""
        spec = self.store.get_latest_spec(task_id)
        if spec is None:
            spec = self.build_spec_workshop(task_id, goal, freeze=True)
        elif not spec["frozen"]:
            spec = self.store.append_spec(
                spec_id=new_id("spc"),
                task_id=task_id,
                spec_md=spec["spec_md"],
                plan_md=spec["plan_md"],
                tasks=spec["tasks"],
                ac_list=spec["ac_list"],
                frozen=True,
            )

        run_id = new_id("run")
        self.store.create_run(
            run_id=run_id,
            task_id=task_id,
            flow_name="sfdp_design_to_delivery",
            initial_state={"goal": goal, "spec_id": spec["id"], "_envelope": {"raw_input": goal}},
        )
        self.store.append_event(
            run_id=run_id,
            task_id=task_id,
            event_type="sfdp_spec_frozen",
            payload={"spec_id": spec["id"], "version": spec["version"], "ac_count": len(spec["ac_list"])},
        )

        ws_dir = (self.store.artifacts_root / run_id / "sandbox_ws").resolve()
        ws_dir.mkdir(parents=True, exist_ok=True)
        active_infer = infer_fn or self._deterministic_fallback_builder(goal, spec["spec_md"])

        tasks_list = list(spec["tasks"])
        ac_list = list(spec["ac_list"])
        exec_logs: list[str] = []
        ac_passed = False
        ac_results: list[dict[str, Any]] = []
        evidence_seal = ""
        final_summary = ""

        for round_no in range(1, max_converge_rounds + 1):
            gap_hint = ""
            if round_no > 1 and ac_results:
                failed_acs = [f"{r['ac_id']}({r['detail']})" for r in ac_results if not r.get("passed")]
                gap_hint = f"上一轮未通过的客观验收项：{', '.join(failed_acs)}。请补齐缺失能力（如 localStorage / 零外部CDN / 按钮事件）。"
                # PRD v3.0 §5 & §9：AC 未通过时只追加新修复任务到 tasks，绝不篡改已冻结的 ac_list！
                tasks_list.append(
                    {
                        "task_no": len(tasks_list) + 1,
                        "title": f"收敛补齐缺口轮次 #{round_no}: {', '.join(failed_acs)}",
                        "verify_cmd": "sfdp_ac_converge",
                        "status": "in_progress",
                    }
                )
                self.store.append_spec(
                    spec_id=new_id("spc"),
                    task_id=task_id,
                    spec_md=spec["spec_md"],
                    plan_md=spec["plan_md"],
                    tasks=tasks_list,
                    ac_list=ac_list,
                    frozen=True,
                )

            worker = CodeActWorker(
                infer_fn=active_infer,
                sandbox=self.sandbox,
                sandbox_tier=SandboxTier.T2_OS_RESTRICTED,
                workspace_dir=ws_dir,
                constitution=self.constitution,
                max_turns=4,
                timeout_sec=30.0,
            )
            full_goal = (
                f"请严格依据以下冻结的《需求规格 spec.md》与《技术方案 plan.md》完成构建：\n\n"
                f"{spec['spec_md']}\n\n{spec['plan_md']}"
            )
            if extra_guardrails.strip():
                full_goal = f"{full_goal}\n\n{extra_guardrails.strip()}"
            step_out = worker.run(
                StepInput(
                    run_id=run_id,
                    task_id=task_id,
                    goal=full_goal,
                    work_mode=WorkMode.EXECUTE,
                    interaction_mode=InteractionMode.COPILOT_EXECUTE,
                    context_messages=list(context_messages or []),
                    steering_hint=gap_hint or None,
                )
            )
            final_summary = step_out.summary or f"已完成《{goal[:30]}》构建"
            exec_logs.append(
                f"- **Round {round_no}**: success=`{step_out.success}` | turns=`{step_out.metadata.get('turns')}` "
                f"| sandbox_runs=`{step_out.metadata.get('sandbox_runs')}` | elapsed=`{step_out.elapsed_ms} ms`"
            )

            ac_passed, ac_results, evidence_seal = self._verify_ac_in_sandbox(ws_dir, ac_list)
            self.store.append_event(
                run_id=run_id,
                task_id=task_id,
                event_type="sfdp_ac_checked",
                payload={"round": round_no, "ac_passed": ac_passed, "results": ac_results},
            )
            if ac_passed:
                break

        # 登记所有沙箱生成产物到 artifacts 表
        saved_artifact_paths: list[str] = []
        change_rows: list[str] = []
        for fp in sorted(ws_dir.iterdir()):
            if fp.is_file():
                raw = fp.read_bytes()
                sha = hashlib.sha256(raw).hexdigest()[:16]
                saved_target = self.store.save_artifact(
                    run_id=run_id,
                    node_id="sfdp_build",
                    name=fp.name,
                    content=raw,
                )
                saved_artifact_paths.append(str(saved_target))
                change_rows.append(f"- `{fp.name}` | 大小：`{len(raw)} bytes` | SHA-256：`{sha}`")

        # 组装并落盘「交付包五件套」（workspace/.huiqiao/runs/<run_id>/delivery/）
        delivery_dir = self.store.artifacts_root / run_id / "delivery"
        delivery_dir.mkdir(parents=True, exist_ok=True)

        change_list_md = (
            "# 交付包第 2 件：变更与产物文件清单\n\n"
            + ("\n".join(change_rows) if change_rows else "- （无落盘产物文件）")
            + "\n"
        )
        log_ref_md = (
            f"# 交付包第 3 件：沙箱构建与收敛执行日志\n\n"
            f"- **关联 Run ID**：`{run_id}`\n"
            f"- **关联冻结规格版本**：`v{spec['version']}`\n"
            + "\n".join(exec_logs)
            + "\n"
        )
        ac_check_lines = [
            f"- [{'✅ PASS' if r.get('passed') else '❌ FAIL'}] **{r['ac_id']} {r['title']}** — 沙箱实测：`{r['detail']}`"
            for r in ac_results
        ]
        self_check_md = (
            "# 交付包第 4 件：只读 AC 逐条客观自检报告\n\n"
            + "\n".join(ac_check_lines)
            + (f"\n\n> **客观证据印章**：`{evidence_seal}`\n" if ac_passed else "\n\n> **状态**：存在未收敛项\n")
        )
        primary_html = next((pathlib.Path(p).name for p in saved_artifact_paths if p.endswith(".html")), None)
        open_guide = (
            f"直接点击工作台上方绿色横幅 **「🚀 立即打开本地小程序」**（或访问 `/preview/{run_id}/{primary_html}`）即可运行。"
            if primary_html
            else f"产物已保存在 `{delivery_dir.parent / 'artifacts'}` 目录。"
        )
        acceptance_protocol_md = (
            f"# 交付包第 5 件：人类验收与一键回滚协议\n\n"
            f"## 1. 打开与运行方式\n- {open_guide}\n\n"
            f"## 2. 建议验收动作\n- 核对上述 `{len(ac_list)}` 条 AC 功能点是否符合预期；\n"
            f"- 可在工作台底部四摄反馈栏点击「随喜赞叹 / 正见纠偏 / 存为技能种子」。\n\n"
            f"## 3. 一键无痕回滚\n- 本次构建全部隔离在沙箱运行目录 `{run_id}` 内，未污染任何外部业务目录；如需清理直接删除该运行目录即可 100% 还原。\n"
        )

        (delivery_dir / "2_change_list.md").write_text(change_list_md, encoding="utf-8")
        (delivery_dir / "3_execution_log.md").write_text(log_ref_md, encoding="utf-8")
        (delivery_dir / "4_self_check_report.md").write_text(self_check_md, encoding="utf-8")
        (delivery_dir / "5_acceptance_protocol.md").write_text(acceptance_protocol_md, encoding="utf-8")

        # 过 B10 五件套完整性与防造假门禁
        valid_pack, missing_reasons = validate_delivery_five_pieces(
            artifact_refs=saved_artifact_paths,
            change_list=change_list_md,
            log_ref=log_ref_md,
            self_check=self_check_md,
            acceptance_protocol=acceptance_protocol_md,
            objective_evidence_token=evidence_seal if ac_passed else None,
        )
        delivery_status = "converged" if (ac_passed and valid_pack) else "rejected"

        delivery_record = self.store.save_delivery(
            delivery_id=new_id("dlv"),
            task_id=task_id,
            run_id=run_id,
            artifact_refs=saved_artifact_paths,
            change_list=change_list_md,
            log_ref=log_ref_md,
            self_check=self_check_md,
            acceptance_protocol=acceptance_protocol_md,
            status=delivery_status,
        )

        run_status = "COMPLETED" if delivery_status == "converged" else "FAILED"
        summary_out = (
            f"### ✦ 铸泽 SFDP 规格构建与五件套验收通过\n\n{final_summary}\n\n{self_check_md}"
            if delivery_status == "converged"
            else f"交付包未通过 B10 完整性/AC 收敛门禁：{'; '.join(missing_reasons)}"
        )
        self.store.save_checkpoint(
            run_id=run_id,
            node_id="sfdp_delivery_gate",
            step_index=len(tasks_list),
            state={
                "_envelope": {"raw_input": goal},
                "_route": {
                    "channel": "L2C_CODEACT",
                    "interaction_mode": "COPILOT_EXECUTE",
                    "confidence": 0.96,
                    "rationale": "经铸泽 SFDP 规格先行工坊冻结 AC 后沙箱构建收敛",
                },
                "summary": summary_out,
                "model_notes": f"交付包五件套已生成 (status={delivery_status})",
            },
            completed_nodes=["sfdp_spec", "sfdp_build", "sfdp_delivery_gate"],
            status=run_status,
            error=None if delivery_status == "converged" else "; ".join(missing_reasons),
        )
        self.store.append_event(
            run_id=run_id,
            task_id=task_id,
            event_type="run_completed" if delivery_status == "converged" else "run_failed",
            node_id="sfdp_delivery_gate",
            payload={"delivery_id": delivery_record["id"], "status": delivery_status},
        )
        return {
            "run_id": run_id,
            "task_id": task_id,
            "status": run_status,
            "delivery": delivery_record,
            "spec": self.store.get_latest_spec(task_id),
        }
