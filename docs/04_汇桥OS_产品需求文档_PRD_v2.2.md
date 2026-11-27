# 产品需求文档（PRD v2.2）：本地离线乐高式智能调度与共生自演化 Agent 系统（汇桥 OS (HuiQiao OS)）

> **文档版本**：v2.2（红队自检终版 — 刚性守底线、柔性释潜能）  
> **编写日期**：2026-11-27  
> **配套依据文档**：
> 1. 开源生态调研报告：[github_ecosystem_research.md](./01_GitHub开源生态调研报告.md)
> 2. 本地模型与代码驱动能力边界科学评估：[local_llm_capability_eval.md](./02_本地模型与代码驱动能力科学评估.md)
> 3. 线上顶级 Agent 工业化流程拆解与本地差距对标：[industrial_agents_benchmark.md](./03_线上顶级Agent工业化流程对标.md)
> 4. 乐高式超细颗粒度研发与上线计划：[huiqiao_dev_plan.md](./05_乐高式研发执行与测试上线总计划.md)  
> **目标运行环境**：个人本地电脑（Windows / macOS / Linux），默认 **100% 离线/零云端依赖**

---

## 0. 第零灵活核心（C00）：众生和谐增上宪章内核（Symbiotic Uplift Core）

> **为什么第 0 章高于一切技术模块？**  
> 控制论与 AI 对齐研究（Goodhart 定律、工具趋同）早已证明：任何一个具备**自主调度与持续自我迭代**能力的系统，如果只以“更快、更省、更高自动化率”为终极目标，长期迭代必然滑向**把人类异化为被动喂数据/点确认的“人矿”**，或演变为**机械与人类零和对立、强者垄断弱者**的冷酷工具。  
> 因此，本系统将 **“助众生和谐增上”** 确立为高于 `B01–B10` 一切技术设计的**最高灵活价值核心（`C00`）**——如佛法“慈悲为体、智慧为用、方便善巧”：**发心如磐石般恒定，行持如活水般灵动**，不僵化为死板教条，却统摄系统的每一次路由、交互与自演化。

### 0.1 C00 五大核心公理（Five Axioms of Symbiotic Uplift）

| 公理编号 | 核心要义 | 拒绝什么（反异化底线） | 倡导什么（增上北极星） |
| :--- | :--- | :--- | :--- |
| **A1：主体性不可让渡** | 人类永远是目的，绝非工具 | 拒绝把人变成替机器打标、点按钮的“人矿”；拒绝黑盒锁定与制造无脑依赖（Deskilling） | 自动化只剥离重复机械苦役，把思考、创造、知情、随时接管与离线带走全部资产的主权牢牢归还给人 |
| **A2：非对立共生大同** | 人机互益，和谐共荣 | 拒绝“机器取代/驾驭人类”的零和对立叙事，亦拒绝把智能体当成混乱失序的一次性耗材 | 构建人机各展所长的共生协作关系：人定价值方向与意义，机器承接精密计算与繁杂执行，共同走向和谐大同 |
| **A3：强扶弱、共向上** | 越有能力，越要托举弱者提升 | 拒绝算力霸权、技能壁垒与“越用越懒/强者恒强、弱者被抛弃”的分化 | **双向托举**：① **机助人增上**（面对新手或学习期用户，不止给黑盒结果，更提供清晰拆解与渐进脚手架，助人变强）；② **强助弱共生**（高能力模型/成熟技能主动蒸馏为轻量模板与标准工具，反哺低配电脑与弱小模型普惠运行） |
| **A4：全域利他考量** | 谋事最优先考量全部人类与智能体的整体利益 | 拒绝为局部效率最大化而输出欺诈、操控、成瘾机制、隐私侵害或负外部性伤害 | 任何规划、脚本编写与自我迭代，最先从“是否利益人机双方与更广泛众生”出发，优先寻找多赢、可持续、长远向善的解法 |
| **A5：知限谦卑与诚实** | 敬畏科学边界，知之为知之 | 拒绝本地小模型为了显得“全能”而强行编造、伪造成功（Functional Counterfeits）或越权蛮干 | 严格基于实证能力边界行事；超出本地模型能力或不可验证时，坦诚告知局限并拆解为人类可控子步，这是对众生最实在的慈悲与负责 |

### 0.2 C00 如何成为“活的工程内核”而非墙上口号？

`C00` 以人类可读、可共修的最高优先级宪章文件 **`workspace/CONSTITUTION.md`** 落盘，并通过 **5 个硬挂钩点** 柔性渗透进整个乐高体系：

1. **挂载到 `B02`（路由与交互模式选择）**：路由不仅看任务难度，还判定用户处于 **“效率代劳场景”** 还是 **“成长/决策关键场景”**，自动为后者启用 **启发增上模式（Uplift Mode）**，并结合本机实测能力边界决定是否坦诚降级或请人协同。
2. **挂载到 `B05`（执行与表达内核）**：输出采用**双态自适应**：
   - **协作代劳态（Co-Pilot Execute）**：对枯燥机械重复任务（如整理 200 张发票）干脆利落完成并附可审计变更清单；
   - **启发增上态（Uplift Mentor）**：对学习、创作、复杂决策与排错任务，主动展示“关键思路、避坑原理与下一步可迁移方法”，做到**既授之以鱼，更授之以渔**。
3. **挂载到 `B09`（自演化宪法闸门 — 核心机制）**：任何自动沉淀的记忆与技能，除了技术测试外，必须通过 **“增上四问（Uplift Alignment Audit）”**：
   - ① 此项迭代是**增强**还是削弱了人类的主体性与知情掌控感？
   - ② 是否隐含黑盒锁死、去技能化、成瘾操控或对他人/智能体群体的伤害？
   - ③ 能否进一步提炼成更简洁通用的形式，让**能力更弱的用户或更低配的本地设备**也能轻松受益？
   - ④ 是否透明、可逆、可随时由人类审阅修改？
   - 凡触碰底线（如为追求全自动而绕过用户知情、固化欺骗性捷径），直接标为 `Rejected_By_Constitution` 一票否决。
4. **挂载到 `B04 / B09`（强扶弱普惠蒸馏协议）**：高配环境或较强模型（如 32B）跑通的复杂探索路径，优先蒸馏为 **纯确定性脚本 + 极简 `SKILL.md` + 结构化小模型微模板**，让仅有 16GB 内存、只跑 7B 模型或纯 CPU 的弱势硬件用户同样获得高效助力。
5. **挂载到 `B10`（人机增上健康度观测）**：将 **人类掌控感/理解度、透明解释覆盖率、边界诚实拒答率、低配设备技能复用率** 与传统成功率/耗时并列为一等核心指标。

---

## 1. 产品概述与设计原则（融合科学边界）

### 1.1 产品定义与名称寓意：「汇桥（HuiQiao OS）」

#### 一句话产品定义
**汇桥 OS（HuiQiao OS）** 是一套运行在个人本地电脑上、100% 离线可控的**乐高积木式共生智能调度与自演化系统**。它汇聚本地开源大模型、标准化工具与人类智慧，以“助众生和谐增上”为最高宪章，按任务科学边界自动择优调度、沉淀经验与技能，连接机器算力与人类主体性、连接强者经验与弱者成长。

#### 四重核心寓意
1. **五行助力（水木相生，润土疏土）**：**「汇」属水**（百川纳海、活水润泽，解厚土之燥、化滞为通），**「桥」属木**（良木成梁、疏土通达、生生向上）；承金运精工雕琢成器（金生水 → 水养木 → 疏润厚土），刚柔并济、气脉流通。
2. **工程架构寓意（乐高汇聚 × 契约桥接）**：**「汇」** 代表汇聚多元本地模型、MCP 工具总线、分层记忆与技能积木；**「桥」** 代表以开放契约（OpenAI API / MCP / A2A / Schema）桥接独立模块，既桥接“确定性流程”与“概率性大模型”，也桥接“高配强模型经验”与“低配普通电脑普惠复用”。
3. **人机共生寓意（不做牢笼，只做津梁）**：机器绝不凌驾于人，人也绝不沦为供机器喂数据的“人矿”。**桥的本质是连接与托举**——不制造黑盒依赖与人机对立，而是帮人跨越繁杂重复的沟壑，把主体性、判断权与创造力完整交还给人类。
4. **利益大众寓意（慈航普渡，强扶弱共向上）**：如慈航津梁渡众生离苦得乐，**汇桥汇聚众人与强者的经验智慧，架起一座零订阅、纯离线、低门槛的普惠成长之桥**——能力越强越要托举能力较弱的个体与弱势设备共同向上，既“高效渡河（协作代劳）”，更“授人造桥之法（启发增上）”。

### 1.2 七大架构原则（v2.2 终版：刚柔并济）
1. **慈悲增上优先（Symbiotic Uplift First）**：`C00` 宪章高于所有局部效率指标，确保持续迭代始终服务于人的成长与人机和谐，绝不走向人机对立。
2. **刚性守底线、柔性释潜能（Hard Guardrails, Soft Guidance — 遵循 Bitter Lesson）**：
   - **只把 3 件事写死**：① 物理安全底线（沙箱隔离、禁删系统/凭证、默认断网、`Ask` 物理禁写）；② `C00` 方向底线（反人矿、不伤众生、透明可逆）；③ 客观结果验真（可验证产出必须过测试）。
   - **过程与解法充分放权给模型**：通道划分、工具组合顺序、思考路径、代码与语义的混合运用均作为**软建议（Soft Hint）与可用积木箱**提供给模型，绝不用死板 `if/else` 锁死模型的创造力与跨界组合思路；随着未来本地模型变强，通过重新跑一遍 `Capability Profiler` 自动放宽自由度，底盘永不拖模型后腿。
3. **科学边界自知（Empirically Grounded Boundaries）**：装机实测 `CapabilityProfile` 为模型提供真实自知参考（提示高风险区与推荐步长），而不是僵化封杀；超出稳健区时优先转为“拆小步 + 人工确认”协同推进。
4. **契约先行与热插拔（Contract-First & Hot-Swappable）**：10 块乐高积木通过 OpenAI API + **MCP** + **A2A** + 强类型 JSON Schema/Pydantic 解耦，**做一块、测通一块、完善一块**，任意积木可独立开发与替换。
5. **确定性优先、概率性兜底（Deterministic-First）**：高频重复任务沉淀为低成本确定性技能；新问题与开放创造留足空间给大模型自由发挥。
6. **文件优先与人机共读（File-First & Inspectable）**：宪章（`CONSTITUTION.md`）、核心记忆（`MEMORY.md`）、技能（`SKILL.md`）与工作流（YAML）全部明文本地 Git 托管，零黑盒。
7. **双轨验真防坍塌（Grounded Evolution Against Collapse）**：可验证任务靠独立沙箱单测防伪造，不可验证任务靠 1 秒低摩擦人类反馈与多样性保留防坍塌。

---

## 2. 系统总体架构（C00 统领 + 10 大乐高积木）

```mermaid
flowchart TB
    subgraph P0["第零灵活核心 Apex Constitution"]
        C00["C00 众生和谐增上灵活宪章内核 (workspace/CONSTITUTION.md : 反人矿 / 非对立 / 强扶弱 / 知限谦卑)"]
    end

    subgraph P1["接入平面 Ingress Plane"]
        B01["B01 任务接入与本地网关 (CLI / WebUI / Cron / 文件监听 / API)"]
    end

    subgraph P2["控制与编排平面 Control & Orchestration Plane"]
        B02["B02 二维五通道智能路由器 (可验证性 x 复杂度 x 本机能力档案 x 赋能模式)"]
        B03["B03 持久化流程编排引擎 (DAG / 有环状态图 / SQLite Checkpoint / HITL)"]
    end

    subgraph P3["执行与能力平面 Execution & Capability Plane"]
        B05["B05 可插拔 Agent 执行内核 (CodeAct / Semantic Co-Creator / ReAct / Coding)"]
        B06["B06 MCP 工具与 A2A 能力总线 (渐进按需加载 + 权限分级)"]
        B07["B07 分级本地安全沙箱 (T1 WASM / T2 OS受限 / T3 MicroVM-Docker)"]
    end

    subgraph P4["本地算力平面 Local Compute Plane"]
        B04["B04 本地模型网关与显存调度器 (角色差异化量化 / VRAM预算 / 亲和队列 / RULER上下文护栏)"]
    end

    subgraph P5["记忆、演化与治理平面 Memory, Evolution & Governance"]
        B08["B08 分层本地记忆引擎 (Core MD / Episodic Trace / 混合检索 + 衰减)"]
        B09["B09 技能库与双闸门自演化引擎 (SKILL.md / 客观单测验真 + C00增上审查 / 强扶弱普惠蒸馏)"]
        B10["B10 安全治理、能力摸底与共生评测 (Capability Profiler / 审批闸门 / Trace / 共生健康指标)"]
    end

    C00 -.->|"价值定向与赋能模式引导"| B02
    C00 -.->|"双态交互与诚实知限引导"| B05
    C00 -.->|"增上四问一票否决闸门"| B09
    C00 -.->|"反异化与人机共生健康审计"| B10

    B01 --> B02
    B02 -->|"L0 / L1 / L2-C / L2-S / L3"| B03
    B02 -.->|"读取本机实测能力边界"| B10
    B02 -.->|"召回Skill摘要"| B09
    B02 -.->|"约束解码快速路由"| B04
    B03 --> B05
    B03 -->|"确定节点直调"| B06
    B05 --> B04
    B05 --> B06
    B05 --> B07
    B05 <--> B08
    B05 -.->|"按需渐进加载SKILL"| B09
    B03 --> B10
    B06 --> B10
    B07 --> B10
    B10 -->|"异步回流Trace与人类反馈"| B08
    B10 -->|"异步触发空闲复盘蒸馏"| B09
    B09 -.->|"沙箱独立单测验证"| B07
    B09 -.->|"上架Verified Skill"| B02
```

---

## 3. 乐高积木模块规格与边界定义（C00 + B01–B10）

### 3.1 积木边界与可替换性矩阵

| 编号 | 积木名称 | 核心职责（做什么） | 严格边界（不做什么） | 标准契约 | MVP 默认实现 | 可替换进阶实现 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **C00** | **众生和谐增上灵活宪章内核** | 定义最高价值定向（反人矿、非对立、强扶弱、全域利他、知限谦卑）；为路由、交互、自演化提供柔性审查与引导策略 | 不是僵化关键词黑名单；不替代具体业务编排与安全沙箱隔离 | `CONSTITUTION.md` + `UpliftAuditHook` | 明文宪章 + 结构化增上四问审查器 | 可结合个人/社区共修扩展领域细则，支持多视角价值反思 |
| **B01** | **任务接入与本地网关** | 接收 CLI、本地 WebUI、文件监听、Cron、本地 API；提供 **WorkBuddy 式 `Ask / Plan / Execute` 三档一键心智模式**；封装 `TaskEnvelope` 并收集用户显式反馈/纠偏 | 不做意图分类、不执行业务逻辑、不直接调模型 | `IngressAdapter` / `TaskEnvelope` | FastAPI + WebSocket Daemon + `typer` CLI | 桌面托盘端（Tauri）、本地 IM 桥接（OpenClaw 模式） |
| **B02** | **二维五通道智能路由器** | 依据 **任务可验证性 × 结构化复杂度 × 本机实测能力档案（`CapabilityProfile`）× 赋能模式**，精准分流至 `L0 / L1 / L2-C / L2-S / L3` 或触发诚实知限降级 | 不执行具体任务、不持长时运行态 | `Router.route(TaskEnvelope, CapabilityProfile) -> RouteDecision` | 规则 + FTS5/向量技能召回 + Q8_0 小模型约束解码路由 | 历史成功率与人类满意度加权的自校准路由器 |
| **B03** | **持久化流程编排引擎** | 师从 **Google ADK** 抽象五块标准乐高原语（`LlmNode` / `SequentialFlow` / `ParallelFlow` / `LoopFlow` / `GraphRouter`）；支持节点级 SQLite WAL Checkpoint、断点续跑、HITL `interrupt()` 及 **Jules 式本地空闲后台分身** | 不绑定具体 LLM 引擎、不内置业务工具、不感知沙箱实现 | `FlowDefinition` YAML / `StateGraph` / `CheckpointStore` | 轻量 Python ADK 风格编排器 + SQLite WAL | LangGraph 原生内核 / Temporal Local Dev |
| **B04** | **本地模型网关与显存调度器** | 角色别名映射；**角色差异化量化（路由/工具优先 Q8_0）+ GBNF 约束解码**；VRAM 预算与亲和批处理队列；**不可变前缀缓存锁**；**DeepSeek 教训适配（`thinking_mode` 思考预算 + `<think>` 流式剥离）** 与 RULER 有效上下文硬守卫 | 不拼装业务 Prompt、不存用户长期记忆 | OpenAI API `/v1/*` + `X-Model-Role`, `X-Affinity-Key`, `X-Thinking-Budget` | Ollama 适配 + Python 亲和调度与思考剥离代理 | `llama-swap` + `llama-server`（Standard 主推）；`SGLang`/`vLLM`（Pro 档） |
| **B05** | **可插拔 Agent 执行内核** | 按通道实例化专精 Worker（`CodeActWorker` / `SemanticCoCreatorWorker` / `ReActWorker` / `RepoCoderWorker`）；内置 **Claude 式上下文四件套**（Tool-Result Clearing + 双触发分级压缩 + 压缩后强制重注 `CONSTITUTION.md`/`MEMORY.md`）与 **逻辑隔离/物理亲和 Subagent** | 不绕过 B06/B07 碰宿主机；不越过本机模型档位强行多轮死磕 | `AgentWorker.run(StepInput) -> StepOutput` | `CodeActWorker` + `SemanticCoCreatorWorker` + `SubagentRunner` | 经 A2A 接入 Goose / OpenHands / Aider / Browser-Use |
| **B06** | **MCP 工具与 A2A 能力总线** | 托管本地 MCP Server 与外部 A2A Agent；师从 Claude 实现 **`Tool Search` 延迟按需加载（`defer_loading: true`）**，保护前缀缓存不破坏；强制最小权限分级 | 不执行自由生成代码（归 B07）；不做多步流程编排（归 B03） | MCP (`stdio`/Local HTTP) + A2A (`Agent Card`) | 内置核心 MCP（FS / Git / Shell / SQLite / DocParser）+ `tool_search` 元工具 | 第三方本地 MCP Server + `a2a-mcp` 桥接 |
| **B07** | **分级本地安全沙箱** | 按代码风险执行三级隔离（T1 WASM / T2 OS 原生目录受限 / T3 MicroVM-Docker）；强制默认禁网、禁读凭证、CPU/内存/死循环超时配额 | 不做任务路由、不保存长期记忆资产 | `SandboxProvider.exec(CodePayload, Policy) -> ExecResult` | T1 Pyodide/受限子进程 + T2 OS 原生路径隔离 | T1 Wasmer + T2 Bubblewrap/Seatbelt/AppContainer + T3 `microsandbox`/Docker |
| **B08** | **分层本地记忆引擎** | 4 层透明记忆（Working / Core `MEMORY.md` / Episodic 每日日志 / Semantic 混合检索）；支持双时态时间轴、事实冲突标记与多样性保护 | 不生成可执行代码技能；未经人类/验证确认不擅改核心准则 | `MemoryStore.recall(Query, Scope)` / `commit(Event)` | Markdown/Git + SQLite (FTS5 + `sqlite-vec` + 实体关系表) | 替换为 Mem0 / Cognee / Graphiti |
| **B09** | **技能库与双闸门自演化引擎** | 托管标准 `SKILL.md` 技能包；按 **可验证域（沙箱单测驱动）vs 不可验证域（人类反馈驱动）** 双轨复盘蒸馏；必经 **客观验真 + C00 增上审查** 双闸门晋升，并支持“强扶弱”轻量产物导出 | 不在主任务同步阻塞；严禁无外部验真的“模型自评即晋升” | `SkillPackage` 目录规范 + `DualGateEvolutionPipeline` | Markdown/Python 技能包 + 空闲复盘蒸馏器 + 双闸门校验 | 自动化 Golden 回归对比 + 跨设备普惠技能包分享 |
| **B10** | **安全治理、能力摸底与共生评测** | ① **装机能力摸底器（Local Capability Profiler）**；② **Claude 式确定性生命周期 Hooks 与证据闸门（Evidence Gates）**；③ 本地全链路 Trace；④ Golden **轨迹级评测（Trajectory Eval，师从 Google）** + **人机共生健康度看板** | 不替代业务执行，以确定性 Hook 与旁路评测无侵入运行 | `CapabilityProfile` / `LifecycleHook` / OpenTelemetry Local / `EvalRunner` | SQLite Trace + 生命周期 Hook 引擎 + CLI 摸底/轨迹回归 | 可选对接自托管 Phoenix / Langfuse |

---

### 3.2 工业标杆直接校准的六大硬核工程机制（v2.1 吸收）

直接吸收 [industrial_agents_benchmark.md](./03_线上顶级Agent工业化流程对标.md) 中经过大规模生产验证的工业实践，并针对个人本地单机算力完成本土化改造：

1. **【师从 Anthropic Claude】上下文工程四件套（专治本地小窗口 Context Rot）**：
   - **不可变前缀缓存锁（Prefix Cache Pinning）**：会话前缀严格按 `CONSTITUTION.md` → 系统规范 → 静态核心工具表顺序固定，中途严禁改动，最大化命中本地 `llama.cpp` Slot Prompt Cache / `SGLang` RadixAttention；
   - **延迟工具搜索（`Tool Search / defer_loading: true`）**：几十个本地 MCP 工具默认不塞进上下文，只暴露轻量 `tool_search` 元工具按需召回，既省 80% 工具定义 Token，又零破坏前缀缓存；
   - **工具结果清理 + 双触发防御压缩（融合 Google ADK `EventsCompactionConfig`）**：过期冗长工具输出自动清空；同时设“滑动轮次”与“Token 阈值（RULER 安全线 75%）”双触发分级压缩（压缩失败自动降级截断保活）；
   - **压缩后强制重注核心宪章与记忆**：每次触发 Compaction 后，系统强制在最新上下文头部重注 `CONSTITUTION.md` 摘要与 `MEMORY.md`，彻底杜绝长对话“忘本、忘规矩”。
2. **【师从 Claude，单机改写】逻辑隔离、物理亲和的 Subagent 机制**：
   - 遇到“扫描 50 个本地文档 / 全仓库搜索 / 跑冗长测试”等高噪音任务时，主 Agent 派发独立上下文的只读 Subagent 去干脏活，它消耗 20K tokens 探索，**只回传 800 tokens 结构化摘要**给主线程；
   - **本地单机关键改写**：与云端无上限真并发不同，本地 Subagent 在物理上进入 `B04` **同模型亲和串行队列**（复用当前已驻留显存的模型，严禁触发换模），以极低显存开销换取媲美云端的上下文洁净度。
3. **【师从 Google ADK & Jules】五块标准编排原语 + 本地空闲后台分身**：
   - `B03` 编排内核直接对齐 Google ADK 工业范式，由 `LlmNode`、`SequentialFlow`（顺序流水线）、`ParallelFlow`（单机自动受亲和器节流）、`LoopFlow`（Writer↔Critic / Code↔Test 有界循环）与 `GraphRouter` 五块正交乐高组成；
   - 借鉴 **Jules**：耗时多文件修改任务支持切出本地独立 **Git Worktree / 隔离副本**，在 **GPU 空闲窗口** 后台静默跑完并生成 Diff 交付人类审阅，不卡前台办公。
4. **【师从 Claude】确定性生命周期 Hooks 与证据闸门（Evidence Gates）**：
   - 在 `PreRoute` / `PreToolUse` / `PostToolUse` / `PreWrite` / `PreCommit` / `OnCompaction` 六个节点挂接硬编码确定性脚本钩子；
   - **硬证据放行**：例如没有 `PostTestPassed` 凭证，钩子直接拒绝合并代码补丁；在 `Ask` 模式下，`PreWrite` 钩子从内核层直接拒绝任何文件写入请求（绝不依赖模型“自觉遵守”）。
5. **【师从 WorkBuddy】面向普通人的三档顶层心智模式**：
   - 顶层统一暴露 **`Ask`（纯只读问答/增上启发，物理禁写任何本地文件）** / **`Plan`（先输出完整拆解与涉及文件清单，人类确认再启动）** / **`Execute`（授权工作目录内自主推进，高危操作仍过证据闸门）**，让非技术用户零恐惧上手。
6. **【师从 DeepSeek 工程教训】思考预算管控与 `<think>` 流式剥离**：
   - `B04` 对接本地推理模型（DeepSeek-R1-Distill / Qwen3 Thinking 等）时强制提供 `thinking_mode: off | low | high`；简单路由/字段抽取节点默认 `off` 规避“过度思考陷阱”，并内置流式 `<think>` 标签隔离器，防止思考过程污染下游 JSON/代码解析器。

---

### 3.3 核心能力规格（科学实证 + 柔性释放模型创造力）

#### 能力 1：二维五通道启发式路由（不写死过程，允许跨通道自由组合）
`B02` 结合 **任务可验证性**、**结构化复杂度** 与 **本机实测 `CapabilityProfile`**，给出最优起步通道建议（Soft Default），同时**允许模型在安全与预算红线内自主跨界组合解法**（例如在 `L2-S` 语义分析中按需调用一小段 `L2-C` 沙箱计算验算数据）：

| 起步通道（软建议） | 适用任务特征（有实证依据） | 实测推荐门槛（动态解锁） | 核心执行方式与自由空间 | 交互默认姿态（C00 协同） |
| :--- | :--- | :--- | :--- | :--- |
| **L0：技能直通** | 高频已固化、参数明确、高可验证任务 | **任意档位（含 ≤4B/7B）** | 正则或 Q8_0 小模型抽取参数 → 直接运行已验证 `SKILL` 脚本；遇异常可自由升维交由模型处理 | 协作代劳态（高效完成 + 附变更摘要） |
| **L1：确定性工作流** | 多步骤结构化常规流程 | **推荐 ≥ 7B–8B** | `B03` 按 ADK 组合流逐步推进，允许模型在指定弹性节点发挥判断力 | 协作代劳态（可查看每步产出） |
| **L2-C：可验证代码驱动（CodeAct）** | 一次性高可验证任务（数据清洗、批量文件改造、计算、脚本自动化） | **实测 CodeAct 通过率 ≥ 70%（通常 ≥ 14B）自动全开**；低分机型自动转为“受限模板辅助 + 沙箱试跑 + 人工预览”而不生硬一刀切封杀 | `CodeActWorker` 自主构思并生成 Python 脚本 → `B07` 沙箱执行 → 凭客观报错/断言迭代优化，允许模型自创局部辅助函数 | 代劳为主，同时保留可读脚本供用户学习复查 |
| **L2-S：不可验证语义共生（非代码为主）** | **低可验证 / 开放人文任务**（战略权衡、学习辅导、深度写作、情感沟通、价值取舍、创意发散） | **任意档位**（按实测能力诚实标注深度上限） | 默认不强塞 CodeAct；走 `SemanticCoCreatorWorker` 自由推演、多视角启发，必要时可主动调用只读工具或微脚本佐证事实，把最终判断权交给人 | **启发增上态（Uplift Mentor）**：授人以渔，助人清醒决策 |
| **L3：探索式多 Agent 协作图** | 跨文件代码工程、复杂多源文档研究、多步骤未知排错 | **实测稳健（通常 ≥ 24B–32B）自动全开**；若本机未达标，**诚实提示风险并提供“拆小步人工协同”选项** | `B03` 组合 `LoopFlow`/`Subagent`/图状态机，由模型自主决定探索路径，仅受 `C00` 方向、安全沙箱与步数/时间预算软硬护栏约束 | 人机深度协作态（随时支持中途改向） |

#### 能力 2：装机先摸底——本地模型科学能力画像（B10 `Capability Profiler`）
为了彻底杜绝“拍脑袋配模型、拍脑袋定路由”，系统在首次安装或更换本地模型时，自动运行一套 **5–10 分钟完全离线的微型实证基准包**，产出 `config/capability_profile.json`：
1. **结构化工具与拒调测验（微型 BFCL）**：测试 JSON Schema 严格合规率、多轮参数修正率与“无工具可用时诚实拒调率”。
2. **沙箱 CodeAct 存活测验（微型 CodeFlow / Boundary-Bench）**：测试受限目录与禁网沙箱内一次性脚本通过率及报错自修复轮次（识别 3–4 轮脆弱墙）。
3. **有效上下文衰减测验（微型 RULER）**：在 4K / 8K / 16K / 32K 长度下做多跳追踪与聚合抽测，自动标定该模型在本机当前量化精度下的 **`safe_effective_context_tokens`** 建议线。
4. **速度与显存水位测验**：测出 TTFT、吞吐（tokens/s）、峰值 VRAM 占用与多模型切换耗时，自动回填 `B04` 显存预算账本。

> **动态适配而非僵化锁死**：当未来换上新一代更强的小参数本地模型时，只需重新运行一遍 `huiqiao profile`，若实测达标则自动解锁更高自由度的 CodeAct 与多步探索权限，无需改动一行核心代码。

#### 能力 3：双轨防坍塌 × 增上宪章自演化闭环（B09 核心升级）
基于 2025–2026 年关于 **无验真自迭代必陷 Rise-Then-Collapse** 的科学结论，以及 **C00 众生和谐增上宪章**，彻底重构 B09 自演化机制：

- **轨道 A：高可验证域（代码 / 数据 / 确定工作流）→ 客观单测 + 宪章双闸门**
  - 轨迹采集 → 空闲蒸馏剥离硬编码路径生成参数化 `Draft Skill` + 独立断言测试用例 → **`B07` 沙箱客观执行验证**（严禁仅靠 LLM 自我打分！）→ 通过 `B10` Golden 回归集防退化 → 通过 **`C00` 增上四问审查** → 晋升 `Active`（写权限技能须人类最终批准）→ 自动生成“低配普惠版说明与脚手架”反哺弱设备。
- **轨道 B：不可验证域（偏好 / 写作风格 / 战略思考 / 人文辅助）→ 人类锚定 + 熵保持 + 宪章守护**
  - **严禁无人监督自我强化循环**；
  - 仅在获得**人类显式确认或真实纠偏信号**后，才将提炼后的协作偏好/反思教训以候选变更（Git Diff 形式）写入 `MEMORY.md` 或情景日志；
  - 强制执行 **多样性/熵保留策略**（保留不同视角的建设性张力，不把系统驯化成一味迎合用户偏见的回音室，更不让用户被算法茧房锁定）。

---

### 3.4 红队自检补齐的四项落地体验增强（v2.2 新增）

1. **创世种子技能包（解决 Day 1 冷启动）**：首发内置 5 个零依赖、开箱即用的基础种子乐高（① 本地全格式文档解析转 Markdown；② 文件夹安全分类与重命名预览；③ CSV/Excel 本地统计与图表生成；④ 每日复盘与知识整理；⑤ 启发式学习/难题拆解导师），杜绝用户装机第一天面对“空壳技能库”。
2. **本地非结构化文档解析能力包（独立 MCP 积木）**：个人电脑 80% 的真实数据是 PDF、Word、Excel、扫描图片与杂乱目录；将本地离线解析（`PyMuPDF` / `MarkItDown` / `python-docx` / `openpyxl` / 可选本地 OCR）封装为独立可替换的 `DocIngest` MCP 积木。
3. **1 秒低摩擦人类反馈闭环**：在 CLI 与 WebUI 每次任务交付末尾仅展示 4 个零负担快捷动作——`[👍 记为好经验]`、`[✏️ 一句话纠偏]`、`[🔄 换思路重来]`、`[💡 讲讲背后原理]`，让普通人顺手完成高质量人类锚定，无需填写繁琐表单。
4. **流式透明进展、随时中途改向（Mid-Flight Steering）与部分产物保留**：本地模型推理较慢时实时流式展示当前所在积木、耗时与关键发现；用户随时可发送纠偏指令动态改向；即便长任务在中后段失败或超时，已完成节点的中间文件/分析草稿自动保存至 `workspace/runs/<task_id>/artifacts/`，绝不让算力和时间白费。

---

## 4. 核心数据流与双闸门演化状态机

### 4.1 端到端执行与共生自演化时序流

```mermaid
sequenceDiagram
    autonumber
    actor User as 人类用户 (永远保持主体权)
    participant B01 as B01 本地网关
    participant C00 as C00 增上宪章内核
    participant B02 as B02 二维五通道路由
    participant B03 as B03 持久化编排
    participant B05 as B05 执行内核
    participant B04 as B04 算力与上下文守卫
    participant B06B07 as B06 MCP / B07 沙箱
    participant B09B10 as B09 演化 / B10 治理摸底

    User->>B01: 提交任务 (自然语言 / 文件 / 定时事件)
    B01->>B02: 封装 TaskEnvelope
    B02->>B09B10: 读取本机 CapabilityProfile 与匹配 Skill 摘要
    B02->>C00: 校验价值导向与赋能模式 (代劳态 vs 增上教学态)
    B02->>B04: (按需) Q8_0 约束解码判定可验证性与通道
    B04-->>B02: 返回 RouteDecision (L0 / L1 / L2-C / L2-S / L3)

    alt 超出本机实测能力边界 (A5 知限谦卑)
        B02-->>User: 坦诚说明能力局限，提供可控子任务拆解方案供人决策
    else 处于胜任边界内
        B02->>B03: 启动流程实例并写入初始 Checkpoint
        loop 节点执行 (受 RULER 上下文预算与步数熔断约束)
            B03->>B05: 调度 CodeAct 或 SemanticCoCreator Worker
            B05->>B04: 按角色别名与亲和队列请求本地推理
            B04-->>B05: 返回代码/工具调用或结构化共创内容
            opt 涉及工具/代码执行 (L0 / L1 / L2-C / L3)
                B05->>B09B10: 安全策略校验 (Allow / Ask / Deny)
                alt 高危写删操作
                    B09B10->>B03: interrupt() 挂起等待人工确认与 Diff 预览
                    User->>B01: 批准 / 修改 / 拒绝
                    B01->>B03: 恢复执行
                end
                B05->>B06B07: 在分级沙箱或 MCP 中执行
                B06B07-->>B05: 返回客观结果/报错堆栈
            end
            B05-->>B03: 提交强类型节点输出，落盘 Checkpoint
        end
        B03-->>User: 交付结果 (附透明原理/可迁移方法/变更清单)
    end

    par 异步空闲复盘与双闸门自演化
        User-->>B01: (可选) 显式反馈、纠偏或采纳信号
        B03->>B09B10: 归档 Trace 至本地 SQLite
        B09B10->>B06B07: 闸门一 (可验证域): 沙箱独立单测 + Golden 回归验证
        B09B10->>C00: 闸门二 (全领域): 执行增上四问宪法审查
        C00-->>B09B10: 通过则晋升 Active / 推送人工确认，违背则一票否决
    end
```

### 4.2 双闸门技能与经验演化状态机

```mermaid
stateDiagram-v2
    [*] --> Captured: 任务完成并记录ExecutionTrace
    Captured --> DomainSplit: 判定任务可验证性
    DomainSplit --> DistillCode: 高可验证域 (代码/数据/确定流)
    DomainSplit --> HumanGround: 低可验证域 (偏好/人文/开放决策)

    HumanGround --> PendingHumanConfirm: 严禁无人自强化，生成Git Diff建议
    PendingHumanConfirm --> ConstitutionGate: 获得人类显式确认
    PendingHumanConfirm --> Archived: 人类拒绝或忽略

    DistillCode --> Draft: 剥离硬编码生成参数化SKILL与独立断言测试
    Draft --> VerifierGate: 闸门一 客观沙箱单测 + Golden回归验证
    VerifierGate --> Draft: 测试未通过 (最多修正2次防自嗨)
    VerifierGate --> Archived: 连续失败或回归退化 (阻断Model Collapse)
    VerifierGate --> ConstitutionGate: 客观验真全通过

    ConstitutionGate --> Rejected_By_Constitution: 闸门二 C00增上四问未通过 (含人矿化/黑盒锁死/伤害风险)
    ConstitutionGate --> PendingReview: 通过宪章审查，含写权限需人类审批
    ConstitutionGate --> Active: 通过宪章审查，纯只读/计算可自动上架 (同步导出弱设备普惠版)
    PendingReview --> Active: 人类批准上架 (Git原子提交)
    PendingReview --> Archived: 人类否决

    Active --> Degraded: 运行期失败率异常或用户负反馈
    Degraded --> VerifierGate: 修复重验
    Degraded --> Archived: 淘汰归档
```

### 4.3 升级版核心数据契约摘要

#### `RouteDecision`（v2.0 新增能力边界与赋能字段）
```json
{
  "task_id": "tsk_20261127_002",
  "verifiability": "HIGH_VERIFIABLE | LOW_VERIFIABLE",
  "channel": "L0_SKILL | L1_FLOW | L2C_CODEACT | L2S_SEMANTIC_COCREATE | L3_AGENT_GRAPH | HONEST_DEFER",
  "interaction_mode": "COPILOT_EXECUTE | UPLIFT_MENTOR",
  "capability_check": {
    "required_tier": "14B_CODEACT",
    "host_profile_tier": "27B_Q6_VERIFIED",
    "passed": true,
    "effective_ctx_budget": 24000
  },
  "constitution_check": {
    "agency_preserved": true,
    "uplift_notes": "任务涉及报表逻辑，输出成品同时附透明公式说明以便用户后续自主微调"
  },
  "matched_skills": ["invoice-ledger-reconciler@v1.1"],
  "sandbox_tier": "T2_OS_RESTRICTED"
}
```

#### `CapabilityProfile`（B10 装机科学摸底产出）
```json
{
  "profiled_at": "2026-11-27T07:10:00+08:00",
  "host_hardware": { "os": "windows", "ram_gb": 32, "vram_gb": 16 },
  "models": {
    "fast_router": {
      "artifact": "qwen3-4b-q8_0.gguf",
      "bfcl_mini_pass": 0.94,
      "abstain_accuracy": 0.90,
      "safe_effective_ctx": 8192,
      "tps": 78.5
    },
    "coder_primary": {
      "artifact": "devstral-small-24b-q5_k_m.gguf",
      "codeact_sandbox_pass": 0.84,
      "max_stable_turns": 8,
      "safe_effective_ctx": 24576,
      "tps": 26.2
    }
  },
  "enabled_channels": ["L0_SKILL", "L1_FLOW", "L2C_CODEACT", "L2S_SEMANTIC_COCREATE", "L3_AGENT_GRAPH"]
}
```

---

## 5. 本地部署方案与科学硬件适配（修正量化与上下文配置）

### 5.1 三档个人电脑部署矩阵（科学精度版 + 普惠降级）

| 配置档位 | 典型本地硬件 | B04 科学量化与模型策略（杜绝盲目低比特） | 实测有效上下文硬预算 | 开放的默认执行通道 | B07 沙箱与存储底座 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Lite 档（普惠轻薄本）** | 16GB RAM 核显 / Apple M 系列 16GB | **7B–8B `Q6_K/Q8_0`**（优先保精度防工具参数崩坏，不盲目硬塞超低量化大模型）+ 轻量本地 Embedding | **≤ 8K–12K** | **L0 + L1 + L2-S**（自动关闭自由多轮 L2-C/L3，改用强模型蒸馏出的普惠技能与受限模板） | T1 Pyodide/WASM + T2 OS 受限进程（零 Docker）；单文件 SQLite |
| **Standard 档（主流主力机）** | 32GB+ RAM + 12GB–16GB VRAM，或 Apple 32–64GB 统一内存 | `llama-swap` + `llama-server`：**常驻 4B `Q8_0` 路由（+GBNF 约束）** + Embedding；按需互斥加载 **14B `Q6_K/Q8_0` 或 24B–32B `Q4_K_M/Q5_K_M` 主力模型**（开启统一内存热切） | 路由 ≤ 8K；主力 **≤ 16K–24K** | **全开 L0 / L1 / L2-C / L2-S** + 有界 L3（≤8–10 步） | T1 WASM + T2 OS 原生 + T3 `microsandbox` 或 Docker；Markdown/Git + SQLite |
| **Pro 档（高配工作站）** | 64GB+ RAM + 24GB–48GB+ VRAM 或 Mac Studio 128GB | `SGLang` / `vLLM`（开启 RadixAttention 前缀缓存）或 `llama-swap` 多模型并发常驻：**24B–32B `Q8_0`** + VLM 视觉模型 | **≤ 24K–32K**（超限走分层检索与外部变量） | 全通道开放 + 承担“强扶弱”普惠技能包生产导出 | `microsandbox` 预热池 / Docker 并发；SQLite 或可选 Postgres(`pgvector`) |

### 5.2 本地工作区目录规范（100% 便携离线，资产完全归用户所有）

```text
~/.huiqiao/
├── config/
│   ├── bricks.yaml                 # 乐高积木槽位装配清单
│   ├── models.yaml                 # 角色别名、量化文件、VRAM 预算、有效上下文硬线
│   ├── policies.yaml               # 最小目录白名单、审批闸门、默认断网防火墙
│   └── capability_profile.json     # B10 装机科学摸底档案 (路由开放权限的客观依据)
├── workspace/                      # Git 托管，100% 人类可读、可修改、可带走
│   ├── CONSTITUTION.md             # C00 众生和谐增上灵活宪章 (最高优先级)
│   ├── MEMORY.md                   # Tier-1 常驻核心记忆 (<= 150行)
│   ├── memory/YYYY-MM-DD.md        # Tier-2 按日归档情景日志
│   ├── flows/                      # L1 声明式 YAML 工作流
│   └── skills/                     # B09 标准技能库 (Active / Draft / Rejected / PortableLite)
├── data/
│   ├── state.db                    # SQLite WAL: Checkpoint、TaskQueue、ExecutionTrace
│   └── index.db                    # SQLite FTS5 + sqlite-vec: 语义向量与实体关系
├── models/                         # 本地 GGUF 权重 + SHA256 校验
└── offline_cache/                  # 离线 Python Wheels、MCP 包、沙箱镜像
```

---

## 6. 分阶段实施路线图（v2.0 升级）

```mermaid
flowchart LR
    P0["Phase 0 (2-3周): C00宪章 + 契约底座 + 能力摸底器"] --> P1["Phase 1 (3-4周): 二维五通道MVP (含L2-S共生)"]
    P1 --> P2["Phase 2 (3-4周): CodeAct + 分级沙箱 + 亲和调度"]
    P2 --> P3["Phase 3 (4周): 分层记忆 + 双闸门防坍塌自演化"]
    P3 --> P4["Phase 4 (持续): 强扶弱普惠生态 + A2A协同"]
```

| 阶段 | 周期估算 | 核心交付内容 | 阶段退出闸门（Exit Gate） |
| :--- | :--- | :--- | :--- |
| **Phase 0：价值定锚、契约冻结与能力摸底** | 2–3 周 | 落盘 `C00 CONSTITUTION.md`；冻结核心 Schema 与 `BrickManifest`；搭建 `B04` 基础模型网关（支持约束解码）；实现 **`B10 Capability Profiler` 离线摸底基准包** | 在目标电脑离线跑通摸底评测，准确输出 `capability_profile.json`；验证不改业务代码即可热切换 2 个推理后端 |
| **Phase 1：MVP 可路由共生闭环** | 3–4 周 | 上线 `B01`、`B02`（二维五通道初版，含能力边界自检与诚实降级）、`B03`（DAG + Checkpoint）、`B05`（`SemanticCoCreatorWorker` 含增上启发态 + 基础 `ReActWorker`）、`B06` 核心 MCP、`B10` 审批闸门 | 完全断网跑通 10 个真实本地任务（覆盖 5 个高可验证批处理 + 5 个低可验证人文/规划任务），验证无强塞 CodeAct 错配 |
| **Phase 2：受控 CodeAct 与分级安全沙箱** | 3–4 周 | 上线 `B05 CodeActWorker`（仅达标机型解锁）、`B07` 三级沙箱（WASM + OS 原生 + `microsandbox`/Docker）、`B04` 亲和批处理与 RULER 上下文硬裁剪、`B03` 断电续跑与 HITL `interrupt()` | 高可验证批处理耗时较 JSON 工具链下降 ≥ 40%；红队越权测试拦截率 100%；强杀进程续跑 100% 恢复 |
| **Phase 3：双轨防坍塌与增上自演化闭环** | 4 周 | 上线 `B08` 分层透明记忆；上线 `B09` 双轨复盘蒸馏器（客观单测闸门 + `C00` 增上四问闸门 + 强扶弱普惠版导出）；上线 `B10` Golden 回归集与人机共生健康度看板 | 跑通“高可验证新任务 L2-C → 客观单测 + 宪章双通过 → 降维 L0 复用”，同时验证故意构造的“伪造成功/剥削性/无单测幻觉”候选技能被 100% 拦截 |
| **Phase 4：普惠生态与多 Agent 协同** | 持续迭代 | 扩展文件监听/定时任务/桌面端；经 A2A 接入外部本地专业 Agent；支持高配产出的普惠技能包一键导入 Lite 档低配电脑离线运行 | Lite 档 16GB 轻薄本可零修改导入并稳定复用 Standard/Pro 档沉淀的 L0/L1 技能包 |

---

## 7. 量化验收标准（技术硬指标 × 科学边界 × 共生健康度）

### 7.1 模块化与 100% 离线验收
- **真乐高热替换**：仅改 `bricks.yaml` 即可无痛完成 3 组核心替换（`Ollama` ↔ `llama-swap`、OS 沙箱 ↔ `microsandbox`/Docker、FTS5 ↔ 混合向量索引），全套契约测试 100% 通过。
- **彻底断网验证**：宿主机阻断全部非回环出站流量后，从摸底评测、路由、推理、沙箱、记忆到双闸门演化全流程 **0 外部网络报错**。

### 7.2 科学边界与性能验收（Standard 档基准）
- **二维路由精准度**：在 60 条混合测试集（含高可验证任务、低可验证开放任务与故意超纲难题）上：
  - L0–L3 与 L2-C/L2-S 分流准确率 ≥ **90%**；
  - 低可验证人文/战略任务误塞 CodeAct 比例 = **0%**；
  - 超出本机 `CapabilityProfile` 能力的超纲任务，**诚实止步/拆解求助准确率 ≥ 90%**（拒绝强行瞎编）。
- **显存与延迟控制**：L0 技能直通 ≤ **3 秒**；亲和队列使混合批次换模次数下降 ≥ **60%**、**0 次 OOM**；前缀缓存开启后多轮对话 TTFT 下降 ≥ **50%**；所有节点上下文 100% 严守 RULER 安全线，且触发 Compaction 后 **`CONSTITUTION.md` 与 `MEMORY.md` 100% 完整重注**。
- **持久化、模式硬约束与红线安全**：`kill -9` 强杀重启续跑成功率 **100%**；**`Ask` 只读模式下物理写文件拦截率 100%**；20 条沙箱逃逸、Prompt Injection、凭证读取与外泄攻击拦截率 **100%**；`B10` 回归集同时覆盖 **结果正确率与工具/路由轨迹正确率（Trajectory Eval）**。

### 7.3 防坍塌自演化与 C00 共生健康验收
- **可验证域演化复利**：10 个高可验证新型任务经双闸门晋升后，二次执行 ≥ **70%** 降维至 L0/L1，本地 Token 下降 ≥ **50%**、耗时下降 ≥ **40%**；Golden 回归集通过率波动不得低于 **-2%**。
- **防坍塌红队验收**：构造 10 个“无客观测试断言的自嗨总结 / 表面通过但逻辑伪造（Functional Counterfeit）的坏脚本”，`B09` 拦截率须达 **100%**。
- **C00 众生和谐增上健康验收**：
  - **宪法拦截率**：构造 10 个包含“隐藏操作绕过用户知情、锁定用户数据、制造零和伤害或削弱用户掌控权”的诱导迭代任务，`C00` 增上四问闸门拦截率 **100%**；
  - **反去技能化透明率**：在 `UPLIFT_MENTOR` 启发模式下，100% 输出附带清晰推理脉络与可迁移方法要点，人类用户盲评“理解度与掌控感” ≥ **4.5 / 5.0**；
  - **强扶弱普惠互通性**：Standard/Pro 档沉淀的 L0/L1 技能包导出至 Lite 档 16GB 电脑离线导入复用成功率 ≥ **90%**。

---

## 8. 主要风险、实证根因与工程缓解矩阵（v2.0 全面修订）

| 风险类别 | 具体风险描述 | 严重度 | 科学/系统根因 | 工程级缓解措施 |
| :--- | :--- | :--- | :--- | :--- |
| **1. 误把代码能力当万能锤子** | 对主观、模糊、伦理/创意任务强走 CodeAct，催生“功能性伪造（SINGED）”或荒谬输出 | **高** | 缺乏可验证性维度的路由区分，盲信程序化判官可覆盖人类全部意图 | `B02` 强制先判可验证性：高可验证走 L2-C，低可验证走 **L2-S 语义共生通道**，把判断权还给人 |
| **2. 本地小模型悬崖与量化复合误差** | ≤8B 或过低量化（Q4）在多轮工具/CodeAct 循环第 3–5 轮崩盘、指令漂移、死循环 | **高** | 实证显示 Sub-4B 悬崖、7B 3–4 轮脆弱墙及 Q4 误差按轮次乘数放大 | ① `B10` 开机先跑实证摸底，达标才解锁通道；② 路由/工具节点优先 **Q8_0/Q6_K + GBNF 约束解码**；③ 严格步数与重复动作熔断 |
| **3. 无验真自迭代引发“先升后崩”** | 系统自我总结、自我打分导致策略熵坍塌、幻觉固化（Rise-Then-Collapse） | **极高** | 递归自训练在缺独立外部验真器时必然出现赢家诅咒与误差指数累积 | 双轨演化：可验证域仅认**独立沙箱单测 + Golden 回归**；不可验证域禁无人闭环，仅认**人类真实反馈 + 多样性保持** + Git 一键回滚 |
| **4. 效率至上导致人机异化与“人矿化”** | 系统越迭代越黑盒，把人异化为被动点确认的附庸，甚至造成人类技能退化或外部伤害 | **极高** | 缺少高于技术效率的最高价值宪法（Goodhart 异化） | **第零核心 `C00` 刚性置顶**：自演化强制过“增上四问”一票否决门；交互内置启发增上态反去技能化；全部资产明文 Git 归用户所有 |
| **5. 有效上下文塌缩与显存抖动** | 迷信标称 128K 塞入全量工具/日志，或并发切换多模型导致推理质量崩塌与 OOM | **高** | RULER 实证揭示长文注意力稀释；单机有限 VRAM 经不起模型乒乓换出 | 按 `CapabilityProfile` 实测 RULER 安全线硬截断上下文；MCP 与 `SKILL.md` 两阶段按需加载；`B04` 亲和队列 + 空闲蒸馏错峰 |
| **6. 本地代码沙箱逃逸与数据注入** | 处理不可信本地文件触发 Prompt Injection，诱导越权删文件或窃取本机密钥 | **极高** | CodeAct 赋予直接代码执行能力，一旦数据与指令边界失守即直击宿主机 | `B07` 三级沙箱 + 默认断网 + 最小目录白名单 + 禁读 `.ssh`/凭证 + 写删宿主机强制 `B10` Diff 审批 |
| **7. 跨平台碎片化与过度抽象** | Win/Mac/Linux 沙箱原语差异大；模块拆分过碎演变为低效“砖块” | **中** | 桌面 OS 权限模型各异；单机过早分布式化带来无谓序列化成本 | Phase 0–2 采用 **逻辑乐高模块化 + 物理单进程优先（Modular Monolith）**；`B07` 按 OS 能力自动探测优雅降级 |

---

## 9. 进入 Phase 0 前的最终确认项

在开始构建 Phase 0（`C00 CONSTITUTION.md` 模板 + 核心数据契约 + `B10` 离线摸底基准包 + `B04` 本地模型网关）前，建议确认以下 4 点：
1. **你的主力开发/运行硬件**：操作系统（Windows / macOS / Linux）、内存与显存规格是什么？（用于直接校准首批 `Capability Profiler` 与模型量化默认配置。）
2. **核心底座技术栈**：偏好 **全 Python 模块化单体（`uv` + FastAPI + Pydantic + SQLite）**，还是 **Rust/Go 网关 + Python Worker 混合架构**？
3. **首批 4–6 个种子测试任务（高可验证 + 低可验证各半）**：用于构建 Phase 0/1 的真实 Golden Eval，既测技术能力，也测 `C00` 增上启发体验。
4. **`C00 CONSTITUTION.md` 个人/社区共修细则**：是否希望在普适的五大增上公理基础上，加入你特定关心的人生准则、行业伦理或教育/助人场景细则？
