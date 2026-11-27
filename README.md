# 汇桥 OS（HuiQiao OS）· 本地离线共生智能系统

> **第零核心发心（C00 众生和谐增上宪章）**：  
> 助众生和谐增上——不把人类变成“人矿”，不造人机零和对立；越有能力越要搭桥托举能力较弱的人与设备共同向上，以 100% 本地离线、开源透明、刚柔并济的乐高积木架构，构建人机各展所长的和谐大同世界。

---

## 一、产品定义

**汇桥 OS（HuiQiao OS）** 是一套运行在个人本地电脑上、完全离线可控的**乐高积木式共生智能调度与自演化系统**：
- **程序化智能调度**：基于实证能力边界，对不同类型输入任务自动分流（L0 技能直通 / L1 确定流 / L2-C 可验证 CodeAct / L2-S 不可验证语义共生 / L3 探索协作图），刚性守底线、柔性释潜能。
- **乐高式热插拔**：全系统拆分为 `C00` 宪章 + `B01–B10` 共 10 大独立积木，通过 OpenAI API / MCP / A2A / JSON Schema 解耦，做一块、测通一块、可独立替换组合。
- **共生自演化复利**：通过“独立沙箱客观验真 + `C00` 增上四问审查”双闸门沉淀记忆与技能包，将高频探索降维固化，并支持高配反哺低配的普惠导出。

---

## 二、名称寓意：「汇桥」四重深意

| 维度 | 寓意阐释 |
| :--- | :--- |
| **1. 五行助力（水木相生）** | **「汇」属水**，百川汇聚、润物无声，解厚土之燥、化滞为通；**「桥」属木**，良木成梁、疏土生长、通达四方。借金运精工泄秀，形成 **金生水（汇）→ 水生木（桥）→ 疏润厚土** 的顺畅流通之势。 |
| **2. 工程架构（汇木成桥）** | **「汇」** 即汇聚本地开源大模型、全格式文档解析、MCP 工具与可复用技能；**「桥」** 即以标准契约桥接每一块乐高积木，打通“确定性工作流”与“大模型创造力”、打通“强算力沉淀”与“低配电脑普惠”。 |
| **3. 人机关系（托举非驾驭）** | 桥不占据岸边，只渡人过河。系统绝不制造黑盒锁死与“人矿化”依赖，而是承接繁杂重复苦役，把知情权、掌控感、思考与创造的主体性牢牢归还给人。 |
| **4. 利益大众（慈航津梁）** | 如舟桥普济众生：**越有能力，越要帮能力尚弱的人与智能体一起成长**。既高效代劳解燃眉之急（授之以鱼），更透明拆解、启发同行（授之以渔），让没有昂贵云端算力的普通人也能平等享有向上增上的助力。 |

---

## 三、归档文档总索引（按阅读顺序）

| 序号 | 文档名称 | 核心内容 |
| :---: | :--- | :--- |
| 01 | [01_GitHub开源生态调研报告.md](./docs/01_GitHub开源生态调研报告.md) | 本地推理、离线 Agent、CodeAct 沙箱、工作流调度、记忆演化与 MCP/A2A 生态全景拆解 |
| 02 | [02_本地模型与代码驱动能力科学评估.md](./docs/02_本地模型与代码驱动能力科学评估.md) | 基于 SWE-bench / BFCL / RULER / 量化退化与 Model Collapse 实证的能力边界评估 |
| 03 | [03_线上顶级Agent工业化流程对标.md](./docs/03_线上顶级Agent工业化流程对标.md) | Anthropic Claude、Google ADK/Jules、OpenAI、WorkBuddy、豆包、DeepSeek 工业流程拆解与本地差距对标 |
| 04 | [04_汇桥OS_产品需求文档_PRD_v2.2.md](./docs/04_汇桥OS_产品需求文档_PRD_v2.2.md) | C00 众生和谐增上宪章 + 汇桥产品定义与寓意 + 10 大乐高积木边界、工业校准机制、验收标准与风险矩阵 |
| 05 | [05_乐高式研发执行与测试上线总计划.md](./docs/05_乐高式研发执行与测试上线总计划.md) | 12 块可独立验收的乐高施工单元（M00–M11）、双维度 Token/工时预算与 4 轮测试上线计划 |
| 06 | [06_汇桥OS_PRD_v3.0_合并优化版.md](./docs/06_汇桥OS_PRD_v3.0_合并优化版.md) | v3.0 合并优化版：规格先行交付流水线 + 交付包五件套 + 基准证据补充 |
| 07 | [07_开发协作规则与技能包_磨刀篇.md](./docs/07_开发协作规则与技能包_磨刀篇.md) | 磨刀协作补充：角色分工、省积分路由与开发纪律 |

### 磨刀工程工具链（反 Token 吞噬 + 三岗模型切换）
- 项目常驻规则：[AGENTS.md](./AGENTS.md)（打开本目录为 Workspace 自动生效，含严格单写者锁）
- 全局自动技能：`~/.gemini/config/skills/huiqiao-forge-os/SKILL.md`（任意新会话提“汇桥”自动激活）
- 极简总控上下文卡：[forge/BRICK_CONTEXT_CARD.md](./forge/BRICK_CONTEXT_CARD.md)（新会话只读这一张卡，省 45KB 冗余输入）
- 实时进度账本与交接快照：[forge/PROGRESS_LEDGER.md](./forge/PROGRESS_LEDGER.md)
- 三岗分工与模型切换作战手册：[forge/MODEL_SWITCH_PLAYBOOK.md](./forge/MODEL_SWITCH_PLAYBOOK.md)
- 管电脑零 Token 管家脚本：[forge/scripts/forge_guard.py](./forge/scripts/forge_guard.py)（`preflight` / `test` / `brief M05` / `digest`）
- GitHub 一键验测推送脚本：[forge/scripts/push_github.ps1](./forge/scripts/push_github.ps1)

---

## 四、当前工程进度与快速验证（M00–M05 已 89/89 全绿）

| 施工块 | 模块定位 | 状态 | 核心目录 |
| :---: | :--- | :---: | :--- |
| **`M00`** | C00 宪章核心、全局 Pydantic 契约与热插拔 `BrickRegistry` | ✅ Done | `workspace/CONSTITUTION.md`, `packages/core/` |
| **`M01`** | 本地模型网关、显存亲和调度、省积分路由与 `<think>` 剥离 | ✅ Done | `packages/llm_gateway/` |
| **`M02`** | 装机离线科学能力摸底器（微型 BFCL / RULER / CodeFix） | ✅ Done | `packages/profiler/` |
| **`M03`** | 本地 MCP 能力总线、`Tool Search` 延迟加载与全格式文档解析 | ✅ Done | `packages/mcp_bus/`, `packages/doc_ingest/` |
| **`M04`** | 确定性 6 点生命周期 Hooks、`Ask/Plan/Execute` 硬锁与证据闸门 | ✅ Done | `packages/governance/`, `config/policies.yaml` |
| **`M05`** | 持久化 ADK 五原语编排、SQLite WAL 强杀续跑与流式状态机 | ✅ Done | `packages/orchestrator/` |
| **`M06`** | 柔硬结合路由与语义共生执行内核（`L2-S` + `ReActWorker`） | 🔜 Next | `packages/router/`, `packages/workers/` |

### 一分钟本机零 Token 体检与测试
```powershell
# 1. 本机硬件/显存/Ollama 零 Token 体检
python forge/scripts/forge_guard.py preflight

# 2. 跑全量回归测试（当前 M00–M05 合计 89/89 绿灯，失败日志自动脱水 <=35 行）
python forge/scripts/forge_guard.py test tests/

# 3. 积木合规体检 CLI（6/6 通过）
python -m packages.core.cli
```

- **100% 离线便携**：全部交叉引用均已转为相对路径，整目录复制或克隆即可在任意电脑离线查阅、继承与演进。
