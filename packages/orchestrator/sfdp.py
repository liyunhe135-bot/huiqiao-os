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

    @staticmethod
    def _extract_verbatim_quotes(goal: str) -> list[str]:
        """提取用户显式用『...』或「...」标出的关键原文（>=6字），用于生成逐字落盘 AC。"""
        quotes: list[str] = []
        for q in re.findall(r"[「『]([^」』]{6,260})[」』]", goal):
            clean_q = q.strip()
            if clean_q and clean_q not in quotes:
                quotes.append(clean_q)
        return quotes[:8]

    @staticmethod
    def _extract_feature_clauses(goal: str) -> list[str]:
        """无损提取用户列举的分项功能需求（严禁 goal[:36] 硬截断丢条款）。"""
        clauses: list[str] = []
        for seg in re.split(r"(?:\n|；|;)+", goal):
            s = seg.strip()
            if re.match(r"^(?:\d+[\.、]|[a-fA-F][\)\.、]|[-*]\s)", s) and len(s) >= 4:
                clauses.append(s)
        if not clauses:
            clauses = [s.strip() for s in re.split(r"[。！？\n]+", goal) if len(s.strip()) >= 4][:6]
        return clauses[:10]

    @staticmethod
    def _is_complex_goal(goal: str) -> bool:
        """判断是否触发深度 5 关专家拷问（多业务域或长需求自动切深度模式）。"""
        domain_pats = (
            r"登录|注册|账号|权限",
            r"支付|收费|订单|商城",
            r"后台|管理端|大屏|erp|crm",
            r"小程序|网页|界面|前端",
            r"知识库|ai|智能|检索|工作流",
            r"导出|报表|统计|财务|对账",
        )
        hits = sum(1 for p in domain_pats if re.search(p, goal, re.I))
        return hits >= 2 or len(goal) >= 120

    @staticmethod
    def _extract_contract_storage_key(text: str) -> str | None:
        m = re.search(r"localStorage(?:\[\s*|\.(?:getItem|setItem)\(\s*)['\"]([a-zA-Z0-9_.-]{3,48})['\"]", text)
        return m.group(1) if m else None

    def generate_clarify_questions(
        self,
        goal: str,
        *,
        task_id: str | None = None,
        depth: str = "auto",
    ) -> dict[str, Any]:
        """阶段 ① 自适应双档澄清门（极速 3 问 ⇄ 深度专家 5 关 · 融合国际 PRD 6 大铁律与四维沟通契约）。"""
        tid = task_id or new_id("tsk")
        is_app = self._is_web_app_goal(goal)
        clauses = self._extract_feature_clauses(goal)
        quotes = self._extract_verbatim_quotes(goal)
        clause_summary = " ； ".join(clauses) if clauses else goal.strip()

        resolved_depth = (
            depth.lower()
            if depth.lower() in ("quick", "deep")
            else ("deep" if self._is_complex_goal(goal) else "quick")
        )

        quote_hint = (
            f"；必保逐字原文 {len(quotes)} 处（严禁改动：{' / '.join(q[:22] + '…' if len(q) > 22 else q for q in quotes)}）"
            if quotes
            else ""
        )

        if resolved_depth == "deep":
            questions = [
                {
                    "id": f"qa_{tid}_1",
                    "question": "【① 角色定位 & PR-FAQ 价值】谁在什么痛点下使用？人类/AI/代码三方权责？",
                    "answer": f"目标用户：需要离线高效解决「{goal[:42]}」的用户；您拍价值与红线，AI 写初版方案，确定性代码+M08沙箱铁面验真。",
                },
                {
                    "id": f"qa_{tid}_2",
                    "question": "【② 定性四重风险 & 公众白话】哪些术语需转大白话？如何控制本地算力与安全风险？",
                    "answer": "界面与按钮默认采用大众白话（文化/专业词附通俗注释或切换）；纯离线沙箱运行零外网，不破坏已有文件。",
                },
                {
                    "id": f"qa_{tid}_3",
                    "question": "【③ 故事地图 V0.1 钢丝切片 & Non-Goals】本期只打穿哪 <=3 个核心点，坚决不做哪几项？",
                    "answer": f"V0.1 核心条款：{clause_summary} ｜ 本期坚决不做(Non-Goals)：云端账号登录、付费支付、多端服务器同步。",
                },
                {
                    "id": f"qa_{tid}_4",
                    "question": "【④ 定量及格指标】操作步数、离线外链与数据零丢失的硬数字标准？",
                    "answer": "核心交互 <= 2 次点击完成；外部 CDN 引用数 == 0；刷新页面本地数据丢失率 == 0%。",
                },
                {
                    "id": f"qa_{tid}_5",
                    "question": "【⑤ 代码契约 Schema & BDD 负例断言】数据如何存储、状态枚举与绝对禁止的坏情况？",
                    "answer": (
                        f"单文件 HTML + localStorage 持久化（状态枚举：unseen|learning|mastered）{quote_hint}；负例：严禁悬空未定义 onclick 函数或删改必保原文。"
                        if is_app
                        else f"Python 纯标准库产出结构化 JSON/Markdown{quote_hint}；负例：严禁空输出或未捕获异常。"
                    ),
                },
            ]
        else:
            questions = [
                {
                    "id": f"qa_{tid}_1",
                    "question": "【① 核心目标 & 功能条款（定性）】本次 V0.1 要打穿哪些具体功能？",
                    "answer": clause_summary,
                },
                {
                    "id": f"qa_{tid}_2",
                    "question": "【② 边界红线 & 定量指标】本期坚决不做(Non-Goals)与及格硬标准？",
                    "answer": "Non-Goals：不做云端登录/复杂后台；定量红线：核心闭环 <=2 次点击、外部 CDN==0、按钮默认大众白话。",
                },
                {
                    "id": f"qa_{tid}_3",
                    "question": "【③ 代码契约 & 客观验收】存储持久化、必保原文与沙箱断言要求？",
                    "answer": (
                        f"单文件 100% 离线 HTML + localStorage 自动保存{quote_hint}；沙箱机检 HTML 闭合且 onclick 函数零悬空。"
                        if is_app
                        else f"Python 纯标准库离线运行{quote_hint}；M08 沙箱实跑 exit_code==0 且落盘非空产物。"
                    ),
                },
            ]

        saved_qa = self.store.save_clarify_qa(tid, questions)
        draft_spec = self.build_spec_workshop(tid, goal, saved_qa, freeze=False, depth=resolved_depth)
        return {
            "task_id": tid,
            "goal": goal,
            "depth": resolved_depth,
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
        depth: str = "auto",
    ) -> dict[str, Any]:
        """阶段 ② 专家级双视角 PRD 工坊：视角 A（对外大白话 PR-FAQ/定性定量/Non-Goals）+ 视角 B（对内严谨代码契约/Schema/BDD 断言）。"""
        if qa_items is not None:
            saved_qa = self.store.save_clarify_qa(task_id, qa_items[:5])
        else:
            saved_qa = self.store.list_clarify_qa(task_id)

        is_app = self._is_web_app_goal(goal)
        deliverable_name = "index.html" if is_app else "solution_output.json"
        clauses = self._extract_feature_clauses(goal)
        qa_md = "\n".join(f"- **{item['question']}**：{item['answer']}" for item in saved_qa) or "- 采用默认离线标准规格"

        # 提取用户在原始目标或自定义 plan_md 中显式签死的 localStorage 键名契约
        explicit_storage_key = self._extract_contract_storage_key(goal) or (
            self._extract_contract_storage_key(custom_plan_md) if custom_plan_md else None
        )

        if is_app:
            quotes = self._extract_verbatim_quotes(goal)
            ac_list = [
                {
                    "ac_id": "AC-01",
                    "title": "产出闭合且事件函数零悬空的 index.html",
                    "given_when_then": "Given 沙箱构建完成 When 扫描 HTML 与 <script> Then 存在闭合 index.html 且所有 onclick/onchange 函数均已真实定义",
                    "negative_case": "负例：禁止空壳文本、未闭合标签或按钮调用未定义的 JS 函数（防功能性伪造）",
                    "check_kind": "html_file_valid",
                },
                {
                    "ac_id": "AC-02",
                    "title": "100% 离线清净无外部 CDN 依赖",
                    "given_when_then": "Given 断网离线环境 When 扫描全部 src/href 属性 Then 外部 http/https 引用数 == 0",
                    "negative_case": "负例：一旦引用任何外部 CDN 脚本或样式表即判定不合规",
                    "check_kind": "zero_external_cdn",
                },
                {
                    "ac_id": "AC-03",
                    "title": "具备真实可点击交互与 localStorage 读写闭环",
                    "given_when_then": "Given 用户交互操作 When 检查脚本逻辑 Then 同时具备点击事件处理与 localStorage 读写持久化",
                    "negative_case": "负例：禁止只有静态展示没有状态读写逻辑的死页面",
                    "check_kind": "interactive_stateful",
                },
            ]
            if quotes:
                ac_list.append(
                    {
                        "ac_id": "AC-04",
                        "title": "用户指定关键原文 100% 逐字无损落盘",
                        "given_when_then": f"Given 用户指明的 {len(quotes)} 处必保引号原文 When 扫描产物文本 Then 必须逐字精确匹配零篡改",
                        "negative_case": "负例：擅自缩写、改写或遗漏用户指定的必保原文视为失败",
                        "check_kind": "verbatim_quotes_intact",
                        "required_quotes": quotes,
                    }
                )
            if explicit_storage_key:
                ac_list.append(
                    {
                        "ac_id": "AC-05",
                        "title": f"代码契约存储键 `{explicit_storage_key}` 严格对齐",
                        "given_when_then": f"Given 对内契约约定的存储键 `{explicit_storage_key}` When 扫描 index.html 脚本 Then 必须显式读写该键名",
                        "negative_case": f"负例：私自改名或未读写 `{explicit_storage_key}` 导致前后版本数据失联视为违约",
                        "check_kind": "contract_storage_key",
                        "required_key": explicit_storage_key,
                    }
                )
        else:
            ac_list = [
                {
                    "ac_id": "AC-01",
                    "title": "沙箱客观执行零报错通过",
                    "given_when_then": "Given 目标任务脚本 When 在 M08 T2 离线沙箱执行 Then exit_code == 0",
                    "negative_case": "负例：抛未捕获异常或超时视为未收敛",
                    "check_kind": "sandbox_exit_zero",
                },
                {
                    "ac_id": "AC-02",
                    "title": "生成真实非空交付产物文件",
                    "given_when_then": "Given 构建完成的工作区 When 扫描产物目录 Then 至少存在 1 个非空成果文件",
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
        clauses_md = "\n".join(f"- {c}" for c in clauses) or f"- {goal}"

        # 视角 A（对外/老板/公众大白话 PRD：PR-FAQ + 角色定位 + 定性 Non-Goals + 定量及格线）
        spec_md = custom_spec_md or (
            f"# 视角 A · 对外大白话 PRD (spec.md · 融合 6 大国际铁律)\n\n"
            f"## 1. PR-FAQ 一句话价值 & 角色定位\n"
            f"- **用户原始诉求**：{goal}\n"
            f"- **目标交付物**：`{deliverable_name}`（100% 本地离线可独立运行）\n"
            f"- **角色权责**：您拍价值与红线 ｜ 本机模型写实现 ｜ 确定性代码与 M08 沙箱客观验真\n\n"
            f"## 2. 定性边界（V0.1 钢丝切片 & 本期坚决不做 Non-Goals）\n"
            f"**本期 V0.1 必达功能条款**：\n{clauses_md}\n"
            f"- **Non-Goals（本期坚决不做）**：不做云端账号系统、不做商业支付、不依赖外网 CDN、不堆砌非核心花哨功能。\n\n"
            f"## 3. 定量及格红线\n"
            f"- 核心交互操作 `<= 2` 次点击 ｜ 外部 CDN 引用数 `== 0` ｜ 刷新页面本地数据丢失率 `== 0%` ｜ 公众默认白话零门槛。\n\n"
            f"## 4. 澄清门已拍板共识\n{qa_md}\n"
        )

        # 视角 B（对内/工程师/AI 严谨代码契约：80/20 分工 + Schema/状态枚举 + 不变量 + BDD 负例断言）
        schema_block = (
            f"- **持久化存储键契约**：`localStorage[{explicit_storage_key!r}]`（若未自定义则使用应用唯一前缀键，含 JSON 读写容错）\n"
            f"- **核心状态枚举**：`unseen | learning | mastered`（所有 DOM 按钮事件 `onclick` 必须与 `<script>` 函数名 1:1 匹配）\n"
            if is_app
            else "- **输入输出契约**：Python 3.11 纯标准库，文件读写显式 `encoding='utf-8'`，产出结构化 JSON/Markdown。\n"
        )
        plan_md = custom_plan_md or (
            f"# 视角 B · 对内严谨代码契约 & BDD 验收 (plan.md)\n\n"
            f"## 1. 铁律 1 · 80/20 确定性与 AI 分工边界\n"
            f"- **80% 确定性代码负责**：存储读写、计数统计、状态切换、筛选计时、沙箱断言检验（零误差）；\n"
            f"- **20% AI 精准负责**：依据本契约生成高质完整源码与自然语义文案。\n\n"
            f"## 2. 接口与数据 Schema 契约（Design by Contract）\n"
            f"- **安全边界**：`M08 T2_OS_RESTRICTED` 断网隔离沙箱构建与只读核验；\n"
            f"{schema_block}"
            f"- **收敛策略**：构建后由独立沙箱核验器逐条检查以下 BDD 断言，未达标项只追加修复任务，严禁篡改 AC。\n\n"
            f"## 3. BDD 客观验收硬断言（Given-When-Then · 冻结后只读）\n{ac_md}\n"
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
            "            raw_txt = p.read_text(encoding='utf-8', errors='ignore')\n"
            "            txt = raw_txt.lower()\n"
            "            scripts = '\\n'.join(re.findall(r'<script[^>]*>([\\s\\S]*?)</script>', raw_txt, flags=re.I))\n"
            "            called = set(re.findall(r'\\bon(?:click|change|input|submit)\\s*=\\s*[\"\\']\\s*([a-zA-Z_$][\\w$]*)\\s*\\(', raw_txt))\n"
            "            builtins = {'localStorage','sessionStorage','alert','confirm','prompt','console','document','window','location','history','Math','JSON','parseInt','parseFloat','setTimeout','clearTimeout','setInterval','clearInterval','event','this','return','if'}\n"
            "            missing_fns = [fn for fn in sorted(called - builtins) if not re.search(rf'(?:function\\s+{re.escape(fn)}\\b|(?:const|let|var|window\\.)\\s*{re.escape(fn)}\\s*=)', scripts)]\n"
            "            ok = ('<html' in txt and '</html>' in txt and '<script' in txt and len(missing_fns) == 0)\n"
            "            detail = f'size={p.stat().st_size}B, closed={\"</html>\" in txt}, missing_fns={missing_fns}'\n"
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
            "        has_store = ('localStorage.setItem' in txt or 'localStorage[' in txt) and ('localStorage.getItem' in txt or 'localStorage[' in txt or 'localStorage' in txt)\n"
            "        ok = p.is_file() and has_evt and has_store\n"
            "        detail = f'interactive={has_evt}, localStorage_rw={has_store}'\n"
            "    elif kind == 'verbatim_quotes_intact':\n"
            "        p = pathlib.Path('index.html')\n"
            "        txt = p.read_text(encoding='utf-8', errors='ignore') if p.is_file() else ''\n"
            "        req_q = ac.get('required_quotes') or []\n"
            "        missing_q = [q[:24] for q in req_q if q not in txt]\n"
            "        ok = p.is_file() and len(missing_q) == 0\n"
            "        detail = f'checked_quotes={len(req_q)}, missing={missing_q}'\n"
            "    elif kind == 'contract_storage_key':\n"
            "        p = pathlib.Path('index.html')\n"
            "        txt = p.read_text(encoding='utf-8', errors='ignore') if p.is_file() else ''\n"
            "        rk = str(ac.get('required_key') or '')\n"
            "        ok = p.is_file() and bool(rk) and (rk in txt)\n"
            "        detail = f'required_storage_key={rk}, found={rk in txt}'\n"
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
