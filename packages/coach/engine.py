"""汇桥 OS 七律架构教练引擎（LawCoachEngine · 严守铁律 1：85% 纯确定性代码规则秒诊 + 15% 按需本地模型点睛）.

管控 7 大工程与产品铁律：
  - L1 确定性与不确定性分离律（80% 确定性代码/规则 + 20% AI 柔性点睛）
  - L2 原子乐高复利律（拒绝一口气造航空母舰，自动切片 V0.1 钢丝闭环 + 匹配复用现有技能）
  - L3 上下文纯度决定智商律（实时探查会话连续性、模糊词噪音、不可变原文锚点与 Token 预算）
  - L4 客观验真高于一切律（自动编译机器可执行硬断言，拒绝口头承诺）
  - L5 经验资产复利律（实时匹配经验防坑库并识别高频场景提示沉淀为 L0 确定性积木）
  - L6 公众零门槛与双语境律（扫描未注释专有词，建议默认大白话 + 文化语境可切换）
  - L7 边界可逆与零破坏律（扫描删除/批量改写高危动作，强制先预览 Diff 与可回滚）
"""

from __future__ import annotations

import html
import pathlib
import re
from typing import Any, Callable

from packages.core.contracts import new_id, utc_now
from packages.hub.manager import extract_immutable_invariants
from packages.workers.context_engine import estimate_tokens

InferFn = Callable[[list[dict[str, str]]], str]

_DETERMINISTIC_KEYWORDS: list[tuple[str, str]] = [
    ("打卡|计数|连胜|连续天数|统计|汇总|百分比|进度", "计数/进度/连续天数统计（纯代码确定性算，零误差）"),
    ("保存|存储|持久化|localStorage|本地数据|不丢失|记忆", "本地持久化存储（localStorage / SQLite，确定性读写）"),
    ("搜索|筛选|查找|过滤|排序|分页", "关键词检索与筛选排序（纯 JS/Python 毫秒级完成）"),
    ("倒计时|计时器|定时器|提醒|闹钟|排期|艾宾浩斯|间隔复习", "计时器与间隔复习日期计算（确定性时间算法）"),
    ("导入|导出|备份|下载|csv|excel|json|表格", "导入导出与表格统计（纯标准库/浏览器 Blob 确定性处理）"),
    ("遮字|抽背|隐藏|填空|逐字|原文", "逐字遮罩与随机抽背算法（确定性字符串掩码，绝不改原文）"),
    ("重命名|归档|分类移动|文件夹|目录", "本地文件系统 Dry-Run 预览与受控批处理（确定性路径校验）"),
    ("校验|断言|单测|格式检查|核验", "客观结构与行为断言校验（M08 沙箱自动机检）"),
]

_AI_KEYWORDS: list[tuple[str, str]] = [
    ("解释|白话|释义|比喻|翻译|讲解|导读", "经典/专业内容通俗白话释义（交给本机模型精准点睛）"),
    ("摘要|提炼|总结|归纳|要点|金句", "非结构化长文意图提炼与摘要（AI 语义理解）"),
    ("启发|提问|复盘|建议|规划|思路|方案|设计|创意|文案|脚本", "模糊诉求拆解、启发式共创与方案生成（AI 柔性推理）"),
    ("构建|开发|编写|生成|制作|写一个", "初版代码/界面原型生成（由 AI 编码 + 沙箱硬断言收口）"),
]

_OVERSIZE_DOMAINS: list[tuple[str, str]] = [
    ("登录|注册|账号|权限|角色|多用户", "账号与多角色权限体系"),
    ("支付|收费|订单|商城|微信支付|支付宝", "商业支付与订单交易"),
    ("后台管理|管理端|大屏|数据中台|erp|crm", "企业级后台管理/大屏"),
    ("小程序|网页|前端|界面|app|桌面端", "用户端交互界面"),
    ("数据库|同步|云端|服务器|分布式|微服务", "多端云同步/服务端集群"),
    ("ai客服|智能推荐|知识库|向量|rag|工作流|agent", "AI 检索与智能体编排"),
    ("报表|财务|对账|发票|审批", "业务财务审批报表"),
]

_VAGUE_WORDS = ("好看点", "好看一点", "智能点", "智能一点", "高端", "大气", "上档次", "差不多", "随便", "弄好", "搞一下", "牛逼", "高级感")
_JARGON_TERMS = (
    "阿赖耶识", "般若", "止观", "四摄", "回向", "俱舍", "随眠", "有漏", "无漏",
    "六经辨证", "五轮眼诊", "CodeAct", "SFDP", "SQLite", "API", "JSON", "localStorage", "RAG", "MCP",
)
_DESTRUCTIVE_HINTS = ("删除", "清空", "覆盖", "彻底移除", "格式化", "批量移动", "重命名全部", "直接改写", "删掉")


def _now_iso() -> str:
    val = utc_now()
    return val.isoformat() if hasattr(val, "isoformat") else str(val)


class LawCoachEngine:
    """汇桥七律架构教练（默认纯代码规则与环境探针秒级分析，可选 15% 本地模型深度点睛）."""

    def analyze(
        self,
        text: str,
        *,
        work_mode: str = "ask",
        session: dict[str, Any] | None = None,
        experiences: list[dict[str, Any]] | None = None,
        skill_plans: list[dict[str, Any]] | None = None,
        active_skills: list[dict[str, Any]] | None = None,
        recent_runs: list[dict[str, Any]] | None = None,
        follow_context: bool = True,
        safe_ctx_budget: int = 8192,
        use_ai: bool = False,
        infer_fn: InferFn | None = None,
    ) -> dict[str, Any]:
        raw = (text or "").strip()
        ses = session or {}
        exps = experiences or []
        plans = skill_plans or []
        skills = active_skills or []
        runs = recent_runs or []
        invariants = extract_immutable_invariants(raw)

        # ------------------------------------------------------------------
        # L1 · 确定性与不确定性分离律（80% 代码 + 20% AI）
        # ------------------------------------------------------------------
        det_parts: list[str] = []
        for pat, desc in _DETERMINISTIC_KEYWORDS:
            if re.search(pat, raw, re.I):
                det_parts.append(desc)
        ai_parts: list[str] = []
        for pat, desc in _AI_KEYWORDS:
            if re.search(pat, raw, re.I):
                ai_parts.append(desc)

        if not det_parts and re.search(r"(小程序|网页|工具|脚本|应用|页面)", raw, re.I):
            det_parts.append("交互事件绑定、本地数据存储与基础校验（应优先用确定性代码 0 误差实现）")
        if not ai_parts and raw:
            ai_parts.append("语义理解与方案/文本生成（仅在模糊推理节点调用本机模型）")

        l1_status = "PASS" if (det_parts and len(det_parts) >= len(ai_parts)) else ("WARN" if raw else "PASS")
        l1_score = 96 if l1_status == "PASS" else 76
        l1_finding = (
            f"已识别 {len(det_parts)} 项确定性代码职责 与 {len(ai_parts)} 项 AI 柔性职责，分工清晰。"
            if l1_status == "PASS"
            else "输入偏笼统或全部丢给 AI 自由发挥，建议显式划出『确定性代码算』与『AI 柔性想』的边界。"
        )
        l1_fix = "将存储、统计、遮罩、日期、筛选等 80% 刚性逻辑固定给代码/L0 技能；仅将释义、创意或初版生成留给 AI。"

        # ------------------------------------------------------------------
        # L2 · 原子乐高复利律（防航空母舰 + 复用体检；自动排除『不做/Non-Goals』否定句防误报！）
        # ------------------------------------------------------------------
        positive_scope = re.sub(
            r"(?:【[^】]*(?:Non-Goals|不做)[^】]*】|(?:暂不做|坚决不做|不做|不要|严禁|禁止|排除|不含|Non-Goals?)[^，,。；;\n]*)",
            " ",
            raw,
            flags=re.I,
        )
        hit_domains = [label for pat, label in _OVERSIZE_DOMAINS if re.search(pat, positive_scope, re.I)]
        clause_cnt = len([s for s in re.split(r"[，,。；;\n]+", positive_scope) if len(s.strip()) >= 4])
        is_oversized = len(hit_domains) >= 3 or (len(positive_scope) > 260 and clause_cnt >= 10)

        reusable_skills: list[str] = []
        for s in skills:
            s_name = str(s.get("name", ""))
            s_desc = str(s.get("description", ""))
            triggers = (s.get("metadata") or {}).get("triggers") or []
            if any(t and str(t).lower() in raw.lower() for t in triggers) or (
                any(k in raw for k in ("摘要", "文档") if "文档" in s_name)
                or any(k in raw for k in ("csv", "表格", "统计") if "表格" in s_name)
                or any(k in raw for k in ("目录", "文件夹", "归档") if "目录" in s_name or "文件" in s_name)
                or any(k in raw for k in ("复盘", "要事", "规划") if "复盘" in s_name)
            ):
                reusable_skills.append(f"{s_name} (`{s.get('skill_id')}`)")

        reusable_plans = [
            f"{p['title']} ({p.get('priority', 'P1')})"
            for p in plans
            if any(str(tr) in raw for tr in (p.get("triggers") or []))
            or (p.get("title", "")[:4] and p.get("title", "")[:4] in raw)
        ]

        if is_oversized:
            l2_status = "RISK"
            l2_score = 55
            v01_wire = f"先只打穿 1 根最小钢丝闭环：{hit_domains[0]} 的单机离线核心流程（1 个页面/脚本 + 本地存储 + 1 条核心交互）"
            later_bricks = hit_domains[1:]
            l2_finding = f"检测到一次塞入 {len(hit_domains)} 个大模块（{' + '.join(hit_domains)}），存在『航空母舰烂尾风险』！"
            l2_fix = f"强烈建议先切出 V0.1 最小钢丝闭环跑通，再逐块拼接：{' → '.join(later_bricks)}。"
        else:
            l2_status = "PASS"
            l2_score = 94
            v01_wire = f"当前颗粒度适中，适合作为单块原子乐高直接打穿（{hit_domains[0] if hit_domains else '单一聚焦微场景'}）。"
            later_bricks = []
            l2_finding = (
                f"任务颗粒度聚焦，符合原子乐高原则"
                + (f"；且可直接复用现有积木：{', '.join(reusable_skills[:2])}" if reusable_skills else "。")
            )
            l2_fix = (
                f"可直接调用左侧已上线技能：{', '.join(reusable_skills[:2])}（0 幻觉秒出）"
                if reusable_skills
                else "先以单文件/单模块跑通闭环，验收满意后一键存为技能种子复利沉淀。"
            )

        # ------------------------------------------------------------------
        # L3 · 上下文纯度决定智商律（实时环境探针）
        # ------------------------------------------------------------------
        vague_hits = [w for w in _VAGUE_WORDS if w in raw]
        turns = ses.get("turns") or []
        pinned_art = ses.get("pinned_artifact_path")
        ses_invs = ses.get("invariants") or []
        est_prompt_tokens = estimate_tokens(raw) + sum(estimate_tokens(str(t.get("goal", ""))) for t in turns[-3:])
        ctx_ratio = round(est_prompt_tokens / max(1, safe_ctx_budget), 3)

        l3_issues: list[str] = []
        if len(raw) < 12:
            l3_issues.append("输入过短（<12字），缺少目标对象与预期输出形式")
        if vague_hits:
            l3_issues.append(f"含模糊形容词（{'/'.join(vague_hits)}），本地 9B 模型易理解偏移")
        if not follow_context and turns:
            l3_issues.append("未开启『跟着改·不断档』，可能导致与当前会话前序产物断链")
        if ctx_ratio > 0.7:
            l3_issues.append(f"当前上下文预算占比偏高（{int(ctx_ratio*100)}%），建议浓缩或开新会话")

        l3_status = "RISK" if len(l3_issues) >= 2 else ("WARN" if l3_issues else "PASS")
        l3_score = max(45, 98 - len(l3_issues) * 20)
        l3_finding = (
            f"上下文纯净不断档：已跟踪 {len(turns)} 轮 · 锁死 {len(set(ses_invs + invariants))} 条不可变锚点"
            + (f" · 已绑定产物 `{pathlib.Path(str(pinned_art)).name}`" if pinned_art else "")
            + f" · 预估 Token 占比 {int(ctx_ratio*100)}%。"
            if not l3_issues
            else "；".join(l3_issues) + "。"
        )
        l3_fix = "用『对象 + 具体动作 + 必保原文「...」 + 存储方式』替代模糊形容词，并保持『跟着改·不断档』开启。"

        # ------------------------------------------------------------------
        # L4 · 客观验真高于一切律（自动编译硬断言）
        # ------------------------------------------------------------------
        is_web = bool(re.search(r"(小程序|网页|页面|前端|打卡|面板|工作台|计算器|html|界面)", raw, re.I)) or (
            bool(pinned_art) and str(pinned_art).lower().endswith(".html") and follow_context
        )
        auto_assertions: list[str] = []
        if is_web:
            auto_assertions.extend(
                [
                    "AC-01 闭合与绑定闭环：生成闭合 index.html，所有 onclick/onchange 调用的函数必须在 <script> 中真实定义（防悬空死按钮）",
                    "AC-02 100% 离线清净：扫描全部 src/href，外部 http/https CDN 引用数 == 0",
                    "AC-03 状态读写闭环：包含真实可点击按钮事件 + localStorage 持久化读写（刷新不丢数据）",
                ]
            )
        else:
            auto_assertions.extend(
                [
                    "AC-01 沙箱客观运行：在 M08 隔离沙箱内执行 exit_code == 0（零未捕获异常）",
                    "AC-02 真实产物落盘：输出非空可复查产物文件（拒绝仅口头总结）",
                ]
            )
        if invariants:
            q_only = [x for x in invariants if x.startswith("必保原文")]
            if q_only:
                auto_assertions.append(f"AC-04 原文逐字零篡改：沙箱逐字核对 {len(q_only)} 处「必保原文」100% 原样存在")

        has_explicit_verify = bool(re.search(r"(验收|测试|验证|断言|检查|不丢失|不得改动|离线|单测)", raw))
        l4_status = "PASS" if has_explicit_verify else "WARN"
        l4_score = 96 if has_explicit_verify else 78
        l4_finding = (
            f"输入已含显式验收约束，教练已同步装配 {len(auto_assertions)} 条机器硬断言。"
            if has_explicit_verify
            else f"原始输入未声明验收标准（AI 易口头敷衍），教练已为您自动补齐 {len(auto_assertions)} 条可机检硬断言。"
        )
        l4_fix = "点击下方『📐 先设计规格』或在优化版中保留上述 AC，交由 M08 沙箱自动机检。"

        # ------------------------------------------------------------------
        # L5 · 经验资产复利律（防坑命中 + 高频固化提示）
        # ------------------------------------------------------------------
        active_exps = [e for e in exps if e.get("auto_inject", True)]
        matched_exps = [
            f"【{e.get('category', '经验')}】{e.get('title', '')}"
            for e in active_exps[:4]
        ]
        # 检查历史运行中是否已高频出现类似词根（>=2 次则提醒沉淀为 L0 确定性技能积木）
        key_probe = re.findall(r"[\u4e00-\u9fff]{2,6}", raw)
        freq_hits = 0
        if key_probe and runs:
            top_kw = key_probe[0]
            freq_hits = sum(1 for r in runs if top_kw in str(r.get("flow_name", "")))
        similar_turns = sum(1 for t in turns if key_probe and key_probe[0] in str(t.get("goal", "")))
        should_crystallize = (similar_turns >= 2) or (freq_hits >= 3)

        l5_status = "PASS" if active_exps else "WARN"
        l5_score = 95 if active_exps else 72
        l5_finding = (
            f"已自动挂载 {len(active_exps)} 条活跃防坑经验护航"
            + ("；⚡ 检测到同类高频场景，强烈建议跑通后点击『存为新技能候选』固化为 L0 确定性积木！" if should_crystallize else "。")
        )
        l5_fix = "每次发现偏差立刻用『纠偏写入记忆』沉淀防坑铁律；高频稳定流程一键孵化进『技能规划库』。"

        # ------------------------------------------------------------------
        # L6 · 公众零门槛与双语境律（补充律）
        # ------------------------------------------------------------------
        hit_jargons = [t for t in _JARGON_TERMS if t.lower() in raw.lower()]
        has_plain_hint = bool(re.search(r"(白话|通俗|解释|对照|切换|公众|新手)", raw))
        if hit_jargons and not has_plain_hint:
            l6_status = "WARN"
            l6_score = 78
            l6_finding = f"检测到 {len(hit_jargons)} 个专业/传统文化术语（{', '.join(hit_jargons[:4])}），若面向公众使用可能存在理解门槛。"
            l6_fix = "建议补充：『界面与按钮默认使用大众白话，专业术语旁附通俗释义或提供双语境切换』。"
        else:
            l6_status = "PASS"
            l6_score = 96
            l6_finding = (
                "已兼顾专业表达与公众白话可读性。"
                if hit_jargons
                else "表述直观通俗，面向普通公众零理解门槛。"
            )
            l6_fix = "保持默认大众白话，文化/专业风味以可选切换或悬停释义呈现。"

        # ------------------------------------------------------------------
        # L7 · 边界可逆与零破坏律（补充律 · 对齐 C00）
        # ------------------------------------------------------------------
        destructive_hits = [w for w in _DESTRUCTIVE_HINTS if w in raw]
        if destructive_hits and work_mode == "execute":
            l7_status = "RISK"
            l7_score = 60
            l7_finding = f"检测到潜在破坏性动作词（{'/'.join(destructive_hits)}）且当前处于 Execute 执行态！"
            l7_fix = "请切至『Plan · 规格预审』先看 Dry-Run 差异清单，确认无误并保留回滚备份后再实际落盘。"
        elif destructive_hits:
            l7_status = "WARN"
            l7_score = 84
            l7_finding = f"含文件变更类动作（{'/'.join(destructive_hits)}），当前处于 {work_mode} 安全保护态。"
            l7_fix = "执行变更前务必确认预览清单（Diff）与备份回滚方案。"
        else:
            l7_status = "PASS"
            l7_score = 98
            l7_finding = "纯建设/只读/隔离沙箱操作，无破坏既有重要资产风险。"
            l7_fix = "保持沙箱隔离与五件套回滚协议护航。"

        # ------------------------------------------------------------------
        # L8 · 沟通契约与定性/定量边界律（Turn-0 防拍脑袋拉满）
        # ------------------------------------------------------------------
        has_role_or_user = bool(re.search(r"(面向|给|用户|公众|新手|团队|老板|学生|自己|个人|客户|角色)", raw))
        has_non_goals = bool(re.search(r"(不做|禁止|不要|严禁|无外部|零外网|不依赖|不得)", raw))
        has_quant_metric = bool(re.search(r"(\d+\s*(?:分钟|秒|次|个|天|品|条|%|字|px|步|轮)|零丢失|0外链|100%)", raw, re.I))
        has_data_contract = bool(re.search(r"(localStorage|sqlite|json|csv|markdown|schema|键名|字段|状态|数据结构|保存|存储)", raw, re.I))
        missing_dims: list[str] = []
        if not has_role_or_user:
            missing_dims.append("角色/目标人群(定性)")
        if not has_non_goals:
            missing_dims.append("本期不做什么 Non-Goals(定性红线)")
        if not has_quant_metric:
            missing_dims.append("可度量数字指标(定量)")
        if not has_data_contract:
            missing_dims.append("数据存储/状态契约(代码合同)")

        l8_status = "PASS" if len(missing_dims) <= 1 else ("WARN" if len(missing_dims) <= 2 else "RISK")
        l8_score = max(56, 98 - len(missing_dims) * 11)
        l8_finding = (
            "初期沟通四维契约（角色/定性/定量/数据合同）清晰完备，可直接进入规格冻结。"
            if not missing_dims
            else f"初期沟通尚缺 {len(missing_dims)} 项边界定义：{'、'.join(missing_dims)}（靠拍脑袋易致返工）。"
        )
        l8_fix = "点击『📐 先设计规格』自动过 30 秒四维契约卡，或在优化版中一键补齐角色、Non-Goals 与定量红线。"

        laws = [
            {"law_id": "L1", "name": "确定性与不确定性分离律 (80/20)", "status": l1_status, "score": l1_score, "finding": l1_finding, "actionable_fix": l1_fix},
            {"law_id": "L2", "name": "原子乐高复利律 (防航空母舰)", "status": l2_status, "score": l2_score, "finding": l2_finding, "actionable_fix": l2_fix},
            {"law_id": "L3", "name": "上下文纯度决定智商律", "status": l3_status, "score": l3_score, "finding": l3_finding, "actionable_fix": l3_fix},
            {"law_id": "L4", "name": "客观验真高于一切律", "status": l4_status, "score": l4_score, "finding": l4_finding, "actionable_fix": l4_fix},
            {"law_id": "L5", "name": "经验资产复利律", "status": l5_status, "score": l5_score, "finding": l5_finding, "actionable_fix": l5_fix},
            {"law_id": "L6", "name": "公众零门槛双语境律 (扩展律)", "status": l6_status, "score": l6_score, "finding": l6_finding, "actionable_fix": l6_fix},
            {"law_id": "L7", "name": "边界可逆与安全底线律 (扩展律)", "status": l7_status, "score": l7_score, "finding": l7_finding, "actionable_fix": l7_fix},
            {"law_id": "L8", "name": "沟通契约与定性/定量边界律 (Turn-0)", "status": l8_status, "score": l8_score, "finding": l8_finding, "actionable_fix": l8_fix},
        ]

        # 结合主人重点盯防盲区：命中 L2 航空母舰红牌时给予 L2 双倍权重，拉响冷静提醒！
        weighted_sum = sum(item["score"] * (2 if (item["law_id"] == "L2" and is_oversized) else 1) for item in laws)
        weighted_cnt = len(laws) + (1 if is_oversized else 0)
        overall_score = round(weighted_sum / weighted_cnt)
        grade = "卓越就绪" if overall_score >= 90 else ("良好可用" if overall_score >= 78 else "建议先采纳优化再执行")

        # 构建 V0.1 最小钢丝一键切片 Prompt（供『🧘 温和智能刹车确认卡』一键听劝套用）
        v01_non_goals = later_bricks[:4] if later_bricks else ["云端多用户账号", "商业支付交易", "复杂多端后台大屏"]
        v01_wire_prompt = (
            f"【V0.1 最小钢丝闭环（已冷静听劝切片）】先只打穿核心单一场景：{hit_domains[0] if hit_domains else (raw[:36] or '核心单点小工具')}。\n"
            f"【本期坚决不做 Non-Goals】暂不做：{'、'.join(v01_non_goals)}（留作 V0.2+ 后续乐高积木逐步拼接）。\n"
            f"【定量与契约红线】单文件 100% 离线零外链 CDN、核心闭环 <=2 次点击、localStorage 刷新零丢失、按钮默认大众白话。\n"
            f"【原始大构想背景参考】{raw}"
        )

        six_gates_checklist = [
            {
                "gate": 1,
                "law": "Bezos PR-FAQ (逆向工作法)",
                "calm_question": "不讲技术词，普通人 30 秒看懂后真愿意天天用吗？",
                "can_do": "10分钟戳穿伪需求与技术自嗨",
                "cannot_do": "不管技术架构与代码实现细节",
                "priority_focus": False,
            },
            {
                "gate": 2,
                "law": "Cagan 四重风险 (价值/可用/可行/安全)",
                "calm_question": "本地 9B 扛得住、大众看得懂、80% 死活剥给代码了吗？",
                "can_do": "开工前排清四大致命暗礁",
                "cannot_do": "本身不画功能切片顺序",
                "priority_focus": False,
            },
            {
                "gate": 3,
                "law": "Patton 故事地图 (纵切 V0.1 钢丝)",
                "calm_question": "今晚 2 小时内必须跑通的 V0.1 最小钢丝是哪 <=3 个点？",
                "can_do": "狠砍航空母舰，立刻打穿可用 V0.1",
                "cannot_do": "管不住中途随手加需求的人性冲动",
                "priority_focus": True,
            },
            {
                "gate": 4,
                "law": "PMI-PBA / ISO 29148 (边界与定量)",
                "calm_question": "本期坚决不做哪 3 件事（Non-Goals）？及格数字是多少？",
                "can_do": "封死范围蔓延与模糊形容词",
                "cannot_do": "切忌写成 50 页没人看的死板 SOP",
                "priority_focus": True,
            },
            {
                "gate": 5,
                "law": "Meyer 契约式设计 DbC (代码合同)",
                "calm_question": "数据存哪个键、有哪几种状态、必保原文签死了吗？",
                "can_do": "前后端/AI/沙箱 0 误差对口咬合",
                "cannot_do": "偏技术枯燥，不可直接给外行客户看",
                "priority_focus": False,
            },
            {
                "gate": 6,
                "law": "North BDD 断言 (Given-When-Then)",
                "calm_question": "断网、刷新、漏字、写错函数名写进沙箱负例了吗？",
                "can_do": "机器铁面自动验真，杜绝 AI 嘴上糊弄",
                "cannot_do": "无法自动评估主观审美高级感",
                "priority_focus": False,
            },
        ]

        calm_brake = {
            "triggered": bool(is_oversized),
            "priority_blind_spot": "反航空母舰：故事地图纵切 V0.1 最小钢丝 + PMI-PBA 写死 Non-Goals",
            "reason": (
                f"检测到一次塞入 {len(hit_domains)} 个大模块（{' + '.join(hit_domains)}），命中您重点盯防的『航空母舰烂尾红牌』！"
                if is_oversized
                else "当前需求颗粒度聚焦，未触发航空母舰刹车，可顺畅推进。"
            ),
            "v01_wire_scope": v01_wire,
            "suggested_non_goals": v01_non_goals,
            "v01_wire_prompt": v01_wire_prompt,
            "six_gates_checklist": six_gates_checklist,
        }

        # ------------------------------------------------------------------
        # 自动生成【高纯度优化版 Prompt】供客户直接左右对比 & 一键套用！
        # ------------------------------------------------------------------
        opt_lines: list[str] = []
        if is_oversized:
            opt_lines.append(f"【V0.1 最小乐高闭环目标】先只打穿核心子场景：{hit_domains[0]}（原始大想法中的其余模块留作后续积木拼接）。")
            opt_lines.append(f"【原始背景参考】{raw}")
        else:
            opt_lines.append(f"【核心目标】{raw or '请补充具体要解决的单一微场景目标'}")

        if missing_dims:
            opt_lines.append(
                "【四维沟通契约补齐】定性边界：面向普通离线用户，本期坚决不做(Non-Goals)云端账号/支付/后台；"
                "定量红线：核心闭环 <=2 次点击、外部 CDN==0、刷新数据丢失率==0%；角色权责：人类拍板，代码+沙箱验真。"
            )
        if det_parts:
            opt_lines.append(f"【80% 确定性代码实现（零误差）】{'；'.join(det_parts[:4])}。")
        if ai_parts:
            opt_lines.append(f"【20% AI 精准点睛】{'；'.join(ai_parts[:2])}。")
        if invariants:
            opt_lines.append("【永久锁死必保条款】" + "；".join(invariants[:6]))
        if hit_jargons and not has_plain_hint:
            opt_lines.append("【公众友好要求】界面默认使用通俗大众白话，专业/文化名词附带白话对照释义或一键切换开关。")
        opt_lines.append("【客观验收标准 (沙箱机检 AC)】" + "；".join(a.split("：", 1)[-1] for a in auto_assertions))
        optimized_prompt = "\n".join(opt_lines)

        # ------------------------------------------------------------------
        # 可选 15% 本地模型深度点睛（仅当用户显式开启 use_ai=True 时才消耗算力！）
        # ------------------------------------------------------------------
        ai_deep_advice = ""
        engine_mode = "deterministic_rules_only"
        if use_ai and infer_fn is not None and raw:
            engine_mode = "rules_85_plus_local_ai_15"
            warn_lines = "\n".join(
                f"- {lw['law_id']}({lw['status']}): {lw['finding']}"
                for lw in laws
                if lw["status"] != "PASS"
            ) or "- 七律体检均已达标"
            try:
                ai_deep_advice = infer_fn(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你是汇桥 OS 的资深业务与架构教练。前置 85% 确定性规则引擎已完成体检，"
                                "请你只做最精华的 15% 业务洞察点睛（严禁废话，控制在 180 字内，分 3 条给出："
                                "1. 商业/场景杠杆点；2. 最易踩的隐形体验坑；3. 下一块可拼接的复利积木）。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"用户输入：{raw}\n前置七律体检告警：\n{warn_lines}",
                        },
                    ]
                ).strip()
            except Exception as exc:
                ai_deep_advice = f"（本机模型深度点睛暂不可用，已自动回退纯规则结论：{exc}）"

        result: dict[str, Any] = {
            "coach_id": new_id("coh"),
            "timestamp": _now_iso(),
            "engine_mode": engine_mode,
            "overall_score": overall_score,
            "grade": grade,
            "pass_count": sum(1 for lw in laws if lw["status"] == "PASS"),
            "warn_count": sum(1 for lw in laws if lw["status"] == "WARN"),
            "risk_count": sum(1 for lw in laws if lw["status"] == "RISK"),
            "laws": laws,
            "comparison": {
                "original_input": raw,
                "optimized_prompt": optimized_prompt,
                "split_80_20": {
                    "deterministic_code_80": det_parts,
                    "ai_reasoning_20": ai_parts,
                },
                "lego_slice": {
                    "is_oversized": is_oversized,
                    "v01_wire_scope": v01_wire,
                    "later_bricks": later_bricks,
                },
                "auto_assertions": auto_assertions,
                "matched_experiences": matched_exps,
                "reusable_skills": reusable_skills,
                "reusable_plans": reusable_plans,
                "should_crystallize_skill": should_crystallize,
            },
            "ai_deep_advice": ai_deep_advice,
            "calm_brake": calm_brake,
        }
        result["share_markdown"] = self.render_share_markdown(result)
        return result

    @staticmethod
    def render_share_markdown(analysis: dict[str, Any]) -> str:
        """生成可直接粘贴微信/飞书/团队群的高密度对比分享报告（Markdown）。"""
        cmp = analysis.get("comparison") or {}
        mode_cn = (
            "85% 确定性规则 + 15% 本机模型深度点睛"
            if analysis.get("engine_mode") == "rules_85_plus_local_ai_15"
            else "100% 纯确定性规则与环境探针（0 显存开销 · 毫秒直出）"
        )
        law_rows = "\n".join(
            f"| **{lw['law_id']} {lw['name']}** | `{lw['status']}` ({lw['score']}分) | {lw['finding']} | {lw['actionable_fix']} |"
            for lw in (analysis.get("laws") or [])
        )
        det_str = "；".join((cmp.get("split_80_20") or {}).get("deterministic_code_80") or ["—"])
        ai_str = "；".join((cmp.get("split_80_20") or {}).get("ai_reasoning_20") or ["—"])
        ac_str = "\n".join(f"- {a}" for a in (cmp.get("auto_assertions") or []))
        deep_sec = f"\n## 五、本机模型 15% 深度业务点睛\n{analysis['ai_deep_advice']}\n" if analysis.get("ai_deep_advice") else ""

        return (
            f"# 🧭 汇桥 OS · 七律架构教练诊断对比报告\n\n"
            f"- **综合评分**：**{analysis.get('overall_score')} / 100（{analysis.get('grade')}）**  \n"
            f"- **诊断引擎**：{mode_cn}  \n"
            f"- **生成时间**：`{analysis.get('timestamp')}`\n\n"
            f"## 一、原始输入 vs 教练高纯度优化版（直接对比）\n\n"
            f"### 1. 原始输入\n> {cmp.get('original_input') or '（空）'}\n\n"
            f"### 2. 教练重构高纯度版（可直接套用执行）\n```text\n{cmp.get('optimized_prompt')}\n```\n\n"
            f"## 二、铁律 1 · 80/20 确定性与 AI 分工建议\n"
            f"- **80% 确定性代码/规则负责**：{det_str}\n"
            f"- **20% AI 精准点睛负责**：{ai_str}\n\n"
            f"## 三、自动装配的客观验收硬断言（铁律 4）\n{ac_str}\n\n"
            f"## 四、七律逐项体检明细\n"
            f"| 规律项 | 评级 | 实时体检发现 | 落地改进建议 |\n"
            f"| :--- | :---: | :--- | :--- |\n"
            f"{law_rows}\n"
            f"{deep_sec}"
        )

    def save_share_report(
        self,
        analysis: dict[str, Any],
        reports_dir: pathlib.Path,
    ) -> dict[str, Any]:
        """将对比报告落盘为独立离线可分享的黑金科技风 HTML 海报页 + Markdown 文档。"""
        reports_dir.mkdir(parents=True, exist_ok=True)
        cid = str(analysis.get("coach_id") or new_id("coh"))
        md_path = reports_dir / f"{cid}.md"
        html_name = f"{cid}.html"
        html_path = reports_dir / html_name

        md_text = analysis.get("share_markdown") or self.render_share_markdown(analysis)
        md_path.write_text(md_text, encoding="utf-8")

        cmp = analysis.get("comparison") or {}
        esc = html.escape
        law_cards = "\n".join(
            f"""<div class="law-row status-{esc(lw['status'].lower())}">
              <div class="law-head"><strong>{esc(lw['law_id'])} · {esc(lw['name'])}</strong><span class="badge">{esc(lw['status'])} · {lw['score']}分</span></div>
              <div class="law-find">{esc(lw['finding'])}</div>
              <div class="law-fix">💡 建议：{esc(lw['actionable_fix'])}</div>
            </div>"""
            for lw in (analysis.get("laws") or [])
        )
        ac_lis = "".join(f"<li>{esc(a)}</li>" for a in (cmp.get("auto_assertions") or []))
        det_lis = "".join(f"<li>{esc(x)}</li>" for x in ((cmp.get("split_80_20") or {}).get("deterministic_code_80") or []))
        ai_lis = "".join(f"<li>{esc(x)}</li>" for x in ((cmp.get("split_80_20") or {}).get("ai_reasoning_20") or []))
        deep_html = (
            f"<div class='card'><h2>🧠 本机模型 15% 深度业务点睛</h2><pre>{esc(analysis['ai_deep_advice'])}</pre></div>"
            if analysis.get("ai_deep_advice")
            else ""
        )

        page_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>汇桥七律架构教练 · 对比诊断报告 ({esc(cid)})</title>
<style>
  body {{ margin:0; padding:24px; background:#050608; color:#f7f3e3; font-family:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; line-height:1.65; }}
  .wrap {{ max-width:960px; margin:0 auto; }}
  .hero {{ border:1px solid #ffd60a; background:linear-gradient(135deg, rgba(255,214,10,0.12), rgba(14,17,24,0.95)); padding:20px 24px; margin-bottom:18px; }}
  h1 {{ margin:0 0 8px 0; color:#ffd60a; font-size:22px; }}
  h2 {{ margin:0 0 10px 0; color:#ffd60a; font-size:15px; border-bottom:1px solid rgba(255,214,10,0.22); padding-bottom:6px; }}
  .score {{ display:inline-block; padding:4px 12px; background:#ffd60a; color:#050608; font-weight:800; margin-right:10px; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:16px; }}
  @media (max-width:720px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  .card {{ border:1px solid rgba(255,214,10,0.25); background:#0d1016; padding:16px; margin-bottom:14px; }}
  pre {{ white-space:pre-wrap; word-break:break-word; background:#07090d; border:1px solid rgba(255,214,10,0.18); padding:12px; color:#f7f3e3; font-size:13px; margin:0; }}
  .law-row {{ padding:10px 12px; margin-bottom:8px; border-left:3px solid #ffd60a; background:rgba(255,255,255,0.02); }}
  .status-pass {{ border-left-color:#34d399; }}
  .status-warn {{ border-left-color:#ffd60a; }}
  .status-risk {{ border-left-color:#ff4d5a; }}
  .law-head {{ display:flex; justify-content:space-between; align-items:center; gap:8px; }}
  .badge {{ font-size:11px; padding:2px 8px; border:1px solid rgba(255,214,10,0.4); color:#ffd60a; }}
  .law-find {{ font-size:13px; margin-top:4px; color:#e5e1d0; }}
  .law-fix {{ font-size:12px; margin-top:3px; color:#a39d87; }}
  ul {{ margin:6px 0 0 18px; padding:0; font-size:13px; }}
  .btn {{ background:#ffd60a; color:#050608; border:none; padding:8px 14px; font-weight:700; cursor:pointer; margin-top:10px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <h1>🧭 汇桥 OS · 七律架构教练诊断对比报告</h1>
    <div>
      <span class="score">{analysis.get('overall_score')} / 100 · {esc(str(analysis.get('grade', '')))}</span>
      <span style="font-size:12.5px;color:#b8b29b;">引擎：{esc('85%确定性规则 + 15%本机AI点睛' if analysis.get('engine_mode') == 'rules_85_plus_local_ai_15' else '100% 纯确定性规则与环境探针（零显存开销）')} ｜ 时间：{esc(str(analysis.get('timestamp', '')))}</span>
    </div>
    <button class="btn" onclick="copyReport()">📋 复制完整对比文本发给团队/客户</button>
  </div>
  <div class="grid2">
    <div class="card"><h2>① 客户/用户原始输入</h2><pre>{esc(str(cmp.get('original_input', '')))}</pre></div>
    <div class="card"><h2>② 教练重构高纯度乐高版（推荐直接执行）</h2><pre id="optPrompt">{esc(str(cmp.get('optimized_prompt', '')))}</pre></div>
  </div>
  <div class="grid2">
    <div class="card"><h2>⚙️ 80% 确定性代码/规则负责（零误差）</h2><ul>{det_lis}</ul></div>
    <div class="card"><h2>✨ 20% AI 精准点睛负责（柔性思考）</h2><ul>{ai_lis}</ul></div>
  </div>
  <div class="card"><h2>🛡️ 自动装配的客观验收硬断言（铁律 4）</h2><ul>{ac_lis}</ul></div>
  {deep_html}
  <div class="card"><h2>📊 七律逐项体检与优化建议</h2>{law_cards}</div>
</div>
<script>
  const RAW_MD = {md_text!r};
  function copyReport() {{
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(RAW_MD).then(() => alert("已复制完整 Markdown 对比报告，可直接粘贴分享！"));
    }} else {{
      alert("请直接 Ctrl+A / Ctrl+C 复制页面内容分享。");
    }}
  }}
</script>
</body>
</html>"""
        html_path.write_text(page_html, encoding="utf-8")
        return {
            "coach_id": cid,
            "preview_url": f"/preview/coach/{html_name}",
            "html_path": str(html_path),
            "markdown_path": str(md_path),
            "share_markdown": md_text,
        }
